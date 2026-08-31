import snapshot from "../app/data/workbook-data.json" with { type: "json" };
import { PartitionCache } from "./cache.mjs";
import { buildFormulaTraces } from "./formulas/evaluate.mjs";
import { buildQueryContext, daysInPeriod, queryCatalog } from "./queries/catalog.mjs";
import {
  shapeCategorySegments,
  shapeMagnetDaily,
  shapeNewProductOrders,
  shapePerformance,
  shapeShipping,
  shapeSlowMoving,
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
  return rows.filter((row) => {
    if (department && request.department && row.department !== request.department && row.leader !== request.department) return false;
    if (operator && request.operator && row.operator !== request.operator) return false;
    return !(store && request.store != null && Number(row.store) !== request.store);
  });
}

function filterSnapshotPerformance(request) {
  if (!request.department && !request.operator && request.store == null) return structuredClone(snapshot.performance);
  const stores = filterRows(snapshot.performance.stores, request);
  const selected = new Set(stores.map((store) => store.store));
  const periodRows = snapshot.performance.periodRows.filter((row) => selected.has(row.store));
  const grouped = new Map();
  for (const row of periodRows) {
    const name = row.leader || "未分组";
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
  if (name === "categorySegments") {
    return structuredClone(snapshot.categorySegments || { categories: [] });
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

export function createDashboardService({ adapter, cacheOptions, timezone, refreshAfterMs }) {
  const cache = new PartitionCache(cacheOptions);
  let lastSuccessAt = null;

  async function loadDatabasePartition(name, request) {
    const categoryPartition = name === "categorySegments";
    const cacheScope = categoryPartition ? { period: request.context.period } : request.cacheScope;
    const cacheTtlMs = categoryPartition ? 300_000 : cache.ttlMs;
    const key = `${name}:${JSON.stringify(cacheScope)}`;
    const fresh = request.force ? null : cache.get(key, { ttlMs: cacheTtlMs });
    if (fresh) {
      return { value: fresh.value.value, effective: fresh.value.effective, source: source("memory-cache", false, fresh.fetchedAt) };
    }
    if (!request.configured) {
      return {
        value: snapshotPartition(name, request),
        effective: null,
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
        const fetchedAt = new Date().toISOString();
        cache.set(key, shaped, fetchedAt);
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
      return {
        value: snapshotPartition(name, request),
        effective: null,
        source: { ...source("workbook-snapshot", true, snapshot.meta.extractedAt, null, warning), lastSuccessAt },
      };
    }
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
    const [performance, categorySegments, slowMoving, shipping, newProductOrders, unshipped, magnetDaily] = await Promise.all([
      loadDatabasePartition("performance", request),
      loadDatabasePartition("categorySegments", request),
      loadDatabasePartition("slowMoving", request),
      loadDatabasePartition("shipping", request),
      loadDatabasePartition("newProductOrders", request),
      loadDatabasePartition("unshipped", request),
      loadDatabasePartition("magnetDaily", request),
    ]);
    const staticFetchedAt = snapshot.meta.extractedAt;
    const sources = {
      performance: performance.source,
      categorySegments: categorySegments.source,
      slowMoving: slowMoving.source,
      shipping: shipping.source,
      newProductOrders: newProductOrders.source,
      unshipped: unshipped.source,
      magnetDaily: magnetDaily.source,
    };
    const data = {
      ...structuredClone(snapshot),
      performance: performance.value,
      categorySegments: categorySegments.value,
      slowMoving: slowMoving.value,
      shipping: shipping.value,
      newProductOrders: newProductOrders.value,
      unshipped: unshipped.value,
      magnetDaily: magnetDaily.value,
    };
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
        categorySegments: data.categorySegments.categories.length,
        shipping: data.shipping.length,
        unshipped: data.unshipped.length,
        magnetDaily: data.magnetDaily.length,
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
    lastSuccessAt: () => lastSuccessAt,
    newestCache: () => cache.newest(),
  };
}
