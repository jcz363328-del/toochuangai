import snapshot from "../app/data/workbook-data.json" with { type: "json" };
import tierSnapshot from "../app/data/store-tiers.json" with { type: "json" };
import { PartitionCache } from "./cache.mjs";
import { toDisplayDepartment } from "./departments.mjs";
import { buildFormulaTraces } from "./formulas/evaluate.mjs";
import { buildQueryContext, daysInPeriod, queryCatalog } from "./queries/catalog.mjs";
import { createDailyRefreshScheduler, localDateKey } from "./store-tiers.mjs";
import {
  shapeCategorySegments,
  shapeMagnetDaily,
  shapeNewProductOrders,
  shapePerformance,
  shapeShipping,
  shapeSlowMoving,
  shapeStoreTiers,
  shapeUnshipped,
} from "./queries/shape-workbook.mjs";

function finite(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function ratio(numerator, denominator) {
  return denominator ? numerator / denominator : null;
}

function filterRows(rows, request, { department = true, operator = true, store = true } = {}) {
  const requestedDepartment = toDisplayDepartment(request.department);
  return rows.filter((row) => {
    const rowDepartment = toDisplayDepartment(row.department || row.leader);
    if (department && requestedDepartment && rowDepartment !== requestedDepartment) return false;
    if (operator && request.operator && row.operator !== request.operator) return false;
    return !(store && request.store != null && Number(row.store) !== request.store);
  }).map((row) => ({ ...row, department: toDisplayDepartment(row.department || row.leader) }));
}

function filterSnapshotPerformance(request) {
  if (!request.department && !request.operator && request.store == null) return structuredClone(snapshot.performance);
  const stores = filterRows(snapshot.performance.stores, request);
  const selected = new Set(stores.map((store) => store.store));
  const periodRows = snapshot.performance.periodRows.filter((row) => selected.has(row.store));
  const grouped = new Map();
  for (const row of periodRows) {
    const name = toDisplayDepartment(row.department) || row.leader || "未分组";
    const item = grouped.get(name) || { name, periods: new Map() };
    const metric = item.periods.get(row.periodKey) || { sales: 0, grossProfit: 0, marginBase: 0 };
    metric.sales += finite(row.sales);
    metric.grossProfit += finite(row.grossProfit);
    if (row.grossMargin) metric.marginBase += finite(row.grossProfit) / finite(row.grossMargin);
    item.periods.set(row.periodKey, metric);
    grouped.set(name, item);
  }
  const totals = new Map();
  for (const item of grouped.values()) {
    for (const [key, value] of item.periods) {
      const total = totals.get(key) || { sales: 0, grossProfit: 0, marginBase: 0 };
      total.sales += value.sales;
      total.grossProfit += value.grossProfit;
      total.marginBase += value.marginBase;
      totals.set(key, total);
    }
  }
  const makeDepartment = (name, periods, isTotal = false) => {
    const current = periods.get("current") || { sales: 0, grossProfit: 0, marginBase: 0 };
    const previous = periods.get("previous") || { sales: 0, grossProfit: 0, marginBase: 0 };
    const yearAgo = periods.get("yearAgo") || { sales: 0, grossProfit: 0, marginBase: 0 };
    const currentDays = daysInPeriod(request.period);
    const previousDays = daysInPeriod(request.context.previous);
    return {
      name,
      isTotal,
      current: { sales: current.sales, grossProfit: current.grossProfit, grossMargin: ratio(current.grossProfit, current.marginBase) },
      previous: { sales: previous.sales, grossMargin: ratio(previous.grossProfit, previous.marginBase) },
      yearAgo: { sales: yearAgo.sales, grossMargin: ratio(yearAgo.grossProfit, yearAgo.marginBase) },
      momSalesGrowth: previous.sales ? (current.sales / currentDays) / (previous.sales / previousDays) - 1 : null,
      yoySalesGrowth: yearAgo.sales ? current.sales / yearAgo.sales - 1 : null,
    };
  };
  const departments = [...grouped.values()].map((item) => makeDepartment(item.name, item.periods));
  departments.push(makeDepartment("合计", totals, true));
  return { periods: structuredClone(snapshot.performance.periods), departments, stores, periodRows };
}

function snapshotPartition(name, request) {
  if (name === "performance") return filterSnapshotPerformance(request);
  if (name === "storeTiers") {
    const rows = Array.isArray(tierSnapshot.rows) ? tierSnapshot.rows : [];
    const scoped = filterRows(rows, request);
    return shapeStoreTiers(scoped, null, tierSnapshot.effectiveDate || null);
  }
  if (name === "categorySegments") {
    const cached = snapshot.categorySegmentsByPeriod?.[request.context.period];
    if (cached) return structuredClone(cached);
    const defaultPeriod = snapshot.performance.periods.find((period) => period.key === "current")?.label;
    return structuredClone(
      request.context.period === defaultPeriod
        ? snapshot.categorySegments || { categories: [] }
        : { categories: [] },
    );
  }
  if (name === "slowMoving") return filterRows(snapshot.slowMoving, request);
  if (name === "shipping") return filterRows(snapshot.shipping, request);
  if (name === "newProductOrders") {
    return request.store == null
      ? structuredClone(snapshot.newProductOrders)
      : snapshot.newProductOrders.filter((row) => row.store === request.store);
  }
  if (name === "unshipped") return filterRows(snapshot.unshipped, request, { department: false });
  return structuredClone(snapshot.magnetDaily);
}

function source(mode, stale, fetchedAt, latencyMs = null, warning = null) {
  return { mode, stale, fetchedAt, lastSuccessAt: mode === "database" ? fetchedAt : null, latencyMs, warning };
}

function shapeStoreTierPartition(rows, fallbackDate) {
  const value = shapeStoreTiers(rows, null, fallbackDate);
  const asOf = value
    .map((row) => row.effectiveDate)
    .filter(Boolean)
    .sort()
    .at(-1) || fallbackDate;
  return { value, effective: { asOf } };
}

export function createDashboardService({ adapter, cacheOptions, timezone, refreshAfterMs }) {
  const cache = new PartitionCache(cacheOptions);
  const lastGoodStoreTiers = new Map();
  let lastSuccessAt = null;
  let tierScheduler = null;

  function tierScopeKey(request) {
    return JSON.stringify({
      department: request.context.department || null,
      operator: request.context.operator || null,
      store: request.context.store ?? null,
    });
  }

  function rememberStoreTiers(request, shaped, fetchedAt) {
    const key = tierScopeKey(request);
    lastGoodStoreTiers.delete(key);
    lastGoodStoreTiers.set(key, {
      value: structuredClone(shaped.value),
      effective: structuredClone(shaped.effective),
      fetchedAt,
    });
    while (lastGoodStoreTiers.size > 80) {
      lastGoodStoreTiers.delete(lastGoodStoreTiers.keys().next().value);
    }
  }

  function findLastGoodStoreTiers(request) {
    const exact = lastGoodStoreTiers.get(tierScopeKey(request));
    if (exact) return structuredClone(exact);
    const global = lastGoodStoreTiers.get(JSON.stringify({ department: null, operator: null, store: null }));
    if (!global) return null;
    return {
      value: filterRows(global.value, request),
      effective: structuredClone(global.effective),
      fetchedAt: global.fetchedAt,
    };
  }

  async function loadDatabasePartition(name, request) {
    const categoryPartition = name === "categorySegments";
    const tierPartition = name === "storeTiers";
    const tierDate = tierPartition ? localDateKey(timezone) : null;
    const cacheScope = categoryPartition
      ? { period: request.context.period }
      : tierPartition
        ? {
            department: request.context.department,
            operator: request.context.operator,
            store: request.context.store,
            tierDate,
          }
        : request.cacheScope;
    // The date is part of the key as well as the long TTL. This guarantees a
    // new query after local midnight even when the API process stayed alive.
    const cacheTtlMs = categoryPartition ? 300_000 : tierPartition ? 86_400_000 : cache.ttlMs;
    const key = `${name}:${JSON.stringify(cacheScope)}`;
    const fresh = request.force ? null : cache.get(key, { ttlMs: cacheTtlMs });
    if (fresh) {
      return { value: fresh.value.value, effective: fresh.value.effective, source: source("memory-cache", false, fresh.fetchedAt) };
    }
    if (!request.configured) {
      return {
        value: snapshotPartition(name, request),
        effective: tierPartition ? { asOf: tierSnapshot.effectiveDate || tierDate } : null,
        source: source("workbook-snapshot", true, snapshot.meta.extractedAt, null, "DB_NOT_CONFIGURED"),
      };
    }
    try {
      return await cache.dedupe(key, async () => {
        const startedAt = performance.now();
        const rows = await adapter.query(queryCatalog[name], request.context);
        const shaped = name === "performance"
          ? shapePerformance(rows, request.context, snapshot, timezone)
          : name === "categorySegments"
            ? { value: shapeCategorySegments(rows), effective: null }
            : name === "storeTiers"
              ? shapeStoreTierPartition(rows, tierDate)
            : {
              value: name === "shipping"
                ? shapeShipping(rows, snapshot)
                : name === "slowMoving"
                  ? shapeSlowMoving(rows)
                : name === "unshipped"
                  ? shapeUnshipped(rows)
                  : name === "newProductOrders"
                    ? shapeNewProductOrders(rows)
                    : shapeMagnetDaily(rows),
              effective: null,
            };
        if (tierPartition && shaped.value.length === 0) {
          const error = new Error("Store tier query returned no rows");
          error.code = "STORE_TIERS_EMPTY";
          throw error;
        }
        const fetchedAt = new Date().toISOString();
        cache.set(key, shaped, fetchedAt);
        if (tierPartition) rememberStoreTiers(request, shaped, fetchedAt);
        lastSuccessAt = fetchedAt;
        return {
          value: shaped.value,
          effective: shaped.effective,
          source: source("database", false, fetchedAt, Math.round(performance.now() - startedAt)),
        };
      });
    } catch (error) {
      const stale = cache.get(key, { allowStale: true, ttlMs: cacheTtlMs });
      const warning = error?.code || "DB_UNAVAILABLE";
      if (stale) {
        return {
          value: stale.value.value,
          effective: stale.value.effective,
          source: { ...source("memory-cache", true, stale.fetchedAt, null, warning), lastSuccessAt: stale.fetchedAt },
        };
      }
      const lastGoodTier = tierPartition ? findLastGoodStoreTiers(request) : null;
      if (lastGoodTier) {
        return {
          value: lastGoodTier.value,
          effective: lastGoodTier.effective,
          source: {
            ...source("memory-cache", true, lastGoodTier.fetchedAt, null, warning),
            lastSuccessAt: lastGoodTier.fetchedAt,
          },
        };
      }
      return {
        value: snapshotPartition(name, request),
        effective: tierPartition ? { asOf: tierSnapshot.effectiveDate || tierDate } : null,
        source: { ...source("workbook-snapshot", true, snapshot.meta.extractedAt, null, warning), lastSuccessAt },
      };
    }
  }

  function mergePerformanceTiers(performance, tierRows) {
    const byStore = new Map((tierRows || []).map((row) => [Number(row.store), row]));
    return {
      ...performance,
      stores: (performance?.stores || []).map((row) => {
        const tier = byStore.get(Number(row.store));
        return {
          ...row,
          tier: tier?.tier ?? row.tier ?? null,
          tierRank: tier?.tierRank ?? row.tierRank ?? null,
          currentLevelDays: tier?.currentLevelDays ?? row.currentLevelDays ?? null,
        };
      }),
    };
  }

  async function refreshStoreTiers(configured) {
    if (!configured) return null;
    const period = localDateKey(timezone).slice(0, 7);
    const context = buildQueryContext({
      period,
      basis: "auto",
      department: null,
      operator: null,
      store: null,
    });
    return loadDatabasePartition("storeTiers", {
      configured,
      context,
      force: true,
      department: null,
      operator: null,
      store: null,
      cacheScope: {
        period: context.period,
        basis: context.basis,
        department: null,
        operator: null,
        store: null,
      },
    });
  }

  function startDailyRefresh(configured) {
    if (!configured || tierScheduler) return;
    tierScheduler = createDailyRefreshScheduler({
      timezone,
      refresh: () => refreshStoreTiers(configured),
    });
    tierScheduler.start();
  }

  function stopDailyRefresh() {
    tierScheduler?.stop();
    tierScheduler = null;
  }

  async function dashboard(input, configured) {
    const context = buildQueryContext(input);
    const request = {
      ...input,
      configured,
      context,
      cacheScope: {
        period: context.period,
        basis: context.basis,
        department: context.department,
        operator: context.operator,
        store: context.store,
      },
    };
    const [performance, categorySegments, storeTiers, slowMoving, shipping, newProductOrders, unshipped, magnetDaily] = await Promise.all([
      loadDatabasePartition("performance", request),
      loadDatabasePartition("categorySegments", request),
      loadDatabasePartition("storeTiers", request),
      loadDatabasePartition("slowMoving", request),
      loadDatabasePartition("shipping", request),
      loadDatabasePartition("newProductOrders", request),
      loadDatabasePartition("unshipped", request),
      loadDatabasePartition("magnetDaily", request),
    ]);
    const performanceValue = mergePerformanceTiers(performance.value, storeTiers.value);
    const staticFetchedAt = snapshot.meta.extractedAt;
    const sources = {
      performance: performance.source,
      categorySegments: categorySegments.source,
      storeTiers: storeTiers.source,
      slowMoving: slowMoving.source,
      shipping: shipping.source,
      newProductOrders: newProductOrders.source,
      unshipped: unshipped.source,
      magnetDaily: magnetDaily.source,
    };
    const data = {
      ...structuredClone(snapshot),
      performance: performanceValue,
      categorySegments: categorySegments.value,
      storeTiers: storeTiers.value,
      slowMoving: slowMoving.value,
      shipping: shipping.value,
      newProductOrders: newProductOrders.value,
      unshipped: unshipped.value,
      magnetDaily: magnetDaily.value,
    };
    delete data.categorySegmentsByPeriod;
    const liveSources = Object.values(sources);
    const anyDatabase = liveSources.some((item) => item.mode === "database");
    const anyMemory = liveSources.some((item) => item.mode === "memory-cache");
    const stale = liveSources.some((item) => item.stale);
    const fetchedAt = liveSources.map((item) => item.fetchedAt).sort().at(-1) || staticFetchedAt;
    const warnings = [...new Set(liveSources.map((item) => item.warning).filter(Boolean))];
    const aggregateSource = {
      mode: anyDatabase ? "database" : anyMemory ? "memory-cache" : "workbook-snapshot",
      stale,
      fetchedAt,
      lastSuccessAt,
      latencyMs: anyDatabase
        ? Math.max(...liveSources.map((item) => item.latencyMs || 0))
        : null,
      warning: warnings.length ? warnings.join(",") : null,
      database: {
        configured,
        status: anyDatabase ? "up" : "down",
        latencyMs: anyDatabase
          ? Math.max(...liveSources.map((item) => item.latencyMs || 0))
          : null,
      },
    };
    data.meta = {
      ...data.meta,
      extractedAt: fetchedAt,
      valueSource: anyDatabase
        ? "SQL Server live partitions with workbook snapshot fallback"
        : "Workbook snapshot fallback",
      dateRanges: {
        ...data.meta.dateRanges,
        shipping: { start: context.currentStart, end: context.currentEnd },
        unshipped: { start: context.currentStart, end: context.currentEnd },
      },
      rowCounts: {
        ...data.meta.rowCounts,
        departments: data.performance.departments.length,
        stores: data.performance.stores.length,
        periodRows: data.performance.periodRows.length,
        storeTiers: data.storeTiers.length,
        categorySegments: data.categorySegments.categories.length,
        shipping: data.shipping.length,
        unshipped: data.unshipped.length,
        magnetDaily: data.magnetDaily.length,
      },
      storeTier: {
        effectiveDate: storeTiers.effective?.asOf
          || data.storeTiers.find((row) => row.effectiveDate)?.effectiveDate
          || localDateKey(timezone),
        updatedAt: storeTiers.source.fetchedAt,
        source: storeTiers.source.mode,
        stale: storeTiers.source.stale,
        warning: storeTiers.source.warning,
      },
    };
    const effective = performance.effective || {
      mode: "full",
      daysCurrent: daysInPeriod(context.period),
      daysPrevious: daysInPeriod(context.previous),
      daysYearAgo: daysInPeriod(context.yearAgo),
      latestBusinessDate: null,
    };
    const inputSources = {
      salesCurrent: sources.performance.mode,
      profitCurrent: sources.performance.mode,
      marginBaseCurrent: sources.performance.mode,
      salesPrevious: sources.performance.mode,
      salesYearAgo: sources.performance.mode,
      daysCurrent: "formula-period",
      daysPrevious: "formula-period",
      daysYearAgo: "formula-period",
      inventoryAmount: sources.slowMoving.mode,
      slowMovingAmount: sources.slowMoving.mode,
      shippingTotalUnits: sources.shipping.mode,
      oceanUnits: sources.shipping.mode,
      airUnits: sources.shipping.mode,
    };
    const formulas = buildFormulaTraces(data, effective, {
      stale,
      evaluatedAt: new Date().toISOString(),
      inputSources,
    });
    return { data, formulas, source: aggregateSource, sources, refreshAfterMs };
  }

  return {
    dashboard,
    startDailyRefresh,
    stopDailyRefresh,
    tierRefreshStatus: () => ({
      active: Boolean(tierScheduler?.active),
      timezone,
      businessDate: localDateKey(timezone),
    }),
    lastSuccessAt: () => lastSuccessAt,
    newestCache: () => cache.newest(),
  };
}
