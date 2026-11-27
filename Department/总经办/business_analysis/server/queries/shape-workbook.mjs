import { daysInPeriod } from "./catalog.mjs";
import { DEPARTMENT_MAPPINGS, toDisplayDepartment } from "../departments.mjs";

function finite(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function nullableText(value) {
  const text = value == null ? "" : String(value).trim();
  return text || null;
}

const TIER_GROUP_RANK = Object.freeze({
  铜: 0,
  銅: 0,
  银: 3,
  銀: 3,
  金: 7,
  钻: 16,
  鑽: 16,
});

/**
 * Keep the level label as displayed by the source system while exposing a
 * stable numeric rank for sorting and summaries. Unknown labels are valid
 * (the business can add levels without a code deployment) and receive null.
 */
export function tierRank(value) {
  const text = nullableText(value)?.replace(/\s+/g, "") || "";
  const match = text.match(/^(铜|銅|银|銀|金|钻|鑽)\s*(\d+)$/);
  if (!match) return null;
  const group = TIER_GROUP_RANK[match[1]];
  const level = Number(match[2]);
  return Number.isInteger(group) && Number.isInteger(level) && level > 0
    ? group + level
    : null;
}

function tierFallbackMap(snapshot) {
  const rows = Array.isArray(snapshot?.storeTiers)
    ? snapshot.storeTiers
    : Array.isArray(snapshot?.performance?.stores)
      ? snapshot.performance.stores
      : [];
  return new Map(rows.map((row) => [finite(row.store), row]));
}

/** Shape authoritative CengJi history rows into the dashboard store contract. */
export function shapeStoreTiers(rows, snapshot = null, effectiveDate = null) {
  const fallback = tierFallbackMap(snapshot);
  const shaped = new Map();
  for (const row of Array.isArray(rows) ? rows : []) {
    const store = finite(row.Store ?? row.Dian ?? row.store);
    if (!store) continue;
    const old = fallback.get(store);
    const item = shaped.get(store) || {
      store,
      tier: null,
      tierRank: null,
      currentLevelDays: null,
      department: null,
      leader: null,
      operator: null,
      effectiveDate: effectiveDate || null,
    };
    const tier = nullableText(row.Tier ?? row.CengJi1 ?? row.tier) || old?.tier || item.tier;
    item.tier = tier;
    const sourceRank = Number(row.TierRank ?? row.CengJiID ?? row.tierRank);
    item.tierRank = Number.isFinite(sourceRank) && sourceRank > 0 ? sourceRank : tierRank(tier);
    const sourceDays = Number(row.CurrentLevelDays ?? row.currentLevelDays);
    item.currentLevelDays = Number.isInteger(sourceDays) && sourceDays > 0
      ? sourceDays
      : (old?.currentLevelDays ?? item.currentLevelDays);
    item.department = toDisplayDepartment(row.Department ?? row.department) || old?.department || item.department;
    item.leader = nullableText(row.Leader ?? row.leader) || old?.leader || item.leader;
    item.operator = nullableText(row.Operator ?? row.operator) || old?.operator || item.operator;
    const rawEffectiveDate = row.EffectiveDate ?? row.AsOf ?? row.RiQi;
    item.effectiveDate = rawEffectiveDate != null && String(rawEffectiveDate).trim()
      ? isoDay(rawEffectiveDate)
      : (old?.effectiveDate || item.effectiveDate || null);
    shaped.set(store, item);
  }
  return [...shaped.values()].sort((a, b) => a.store - b.store);
}

function isoDay(value) {
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  return String(value).slice(0, 10);
}

function dayOfMonth(value) {
  return Number.parseInt(isoDay(value).slice(8, 10), 10);
}

function currentPeriodIn(timezone, now = new Date()) {
  const parts = new Intl.DateTimeFormat("en", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
  }).formatToParts(now);
  const year = parts.find((part) => part.type === "year")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  return `${year}-${month}`;
}

export function getEffectivePeriodContext(context, rows, timezone, now = new Date()) {
  const fullDays = daysInPeriod(context.period);
  const latestDay = rows
    .filter((row) => row.PeriodKey === "current")
    .reduce((maximum, row) => Math.max(maximum, dayOfMonth(row.BusinessDate)), 0);
  const isCurrent = context.period === currentPeriodIn(timezone, now);
  const useMtd = context.basis === "mtd" || (context.basis === "auto" && isCurrent);
  const daysCurrent = useMtd ? Math.max(1, latestDay || now.getDate()) : fullDays;
  return {
    mode: useMtd ? "mtd" : "full",
    daysCurrent,
    daysPrevious: useMtd ? Math.min(daysCurrent, daysInPeriod(context.previous)) : daysInPeriod(context.previous),
    daysYearAgo: useMtd ? Math.min(daysCurrent, daysInPeriod(context.yearAgo)) : daysInPeriod(context.yearAgo),
    latestBusinessDate: latestDay ? `${context.period}-${String(latestDay).padStart(2, "0")}` : null,
  };
}

function metric(sales = 0, grossProfit = 0, marginBase = 0) {
  return {
    sales,
    grossProfit,
    marginBase,
    grossMargin: marginBase ? grossProfit / marginBase : null,
  };
}

function add(target, row) {
  target.sales += finite(row.Sales);
  target.grossProfit += finite(row.GrossProfit);
  target.marginBase += finite(row.MarginBase);
  target.grossMargin = target.marginBase ? target.grossProfit / target.marginBase : null;
}

function growth(current, previous, currentDays, previousDays) {
  if (!Number.isFinite(current) || !Number.isFinite(previous) || previous === 0) return null;
  return (current / currentDays) / (previous / previousDays) - 1;
}

function simpleGrowth(current, previous) {
  if (!Number.isFinite(current) || !Number.isFinite(previous) || previous === 0) return null;
  return current / previous - 1;
}

function includeRow(row, effective) {
  if (effective.mode === "full") return true;
  const limit = row.PeriodKey === "current"
    ? effective.daysCurrent
    : row.PeriodKey === "previous"
      ? effective.daysPrevious
      : effective.daysYearAgo;
  return dayOfMonth(row.BusinessDate) <= limit;
}

export function shapePerformance(rows, context, snapshot, timezone) {
  const effective = getEffectivePeriodContext(context, rows, timezone);
  const scoped = rows.filter((row) => includeRow(row, effective));
  const snapshotByStore = new Map(snapshot.performance.stores.map((store) => [store.store, store]));
  const stores = new Map();

  for (const row of scoped) {
    const storeId = finite(row.Store);
    const fallback = snapshotByStore.get(storeId);
    const item = stores.get(storeId) || {
      store: storeId,
      department: toDisplayDepartment(row.Department),
      leader: nullableText(row.Leader) || fallback?.leader || "未分组",
      operator: nullableText(row.Operator) || fallback?.operator || "未分配",
      openedOn: fallback?.openedOn || null,
      ageYears: fallback?.ageYears ?? null,
      tier: fallback?.tier || null,
      current: metric(),
      previous: metric(),
      yearAgo: metric(),
    };
    add(item[row.PeriodKey], row);
    stores.set(storeId, item);
  }

  const storeRows = [...stores.values()].map((store) => ({
    department: store.department,
    leader: store.leader,
    operator: store.operator,
    store: store.store,
    current: {
      sales: store.current.sales,
      grossProfit: store.current.grossProfit,
      grossMargin: store.current.grossMargin,
    },
    previous: { sales: store.previous.sales, grossMargin: store.previous.grossMargin },
    yearAgo: { sales: store.yearAgo.sales, grossMargin: store.yearAgo.grossMargin },
    momSalesGrowth: growth(
      store.current.sales,
      store.previous.sales,
      effective.daysCurrent,
      effective.daysPrevious,
    ),
    yoySalesGrowth: simpleGrowth(store.current.sales, store.yearAgo.sales),
    openedOn: store.openedOn,
    ageYears: store.ageYears,
    tier: store.tier || null,
  })).sort((a, b) => b.current.sales - a.current.sales);

  const departmentMap = new Map();
  for (const store of stores.values()) {
    const name = store.department || store.leader || "未分组";
    const department = departmentMap.get(name) || {
      name,
      isTotal: false,
      current: metric(),
      previous: metric(),
      yearAgo: metric(),
    };
    for (const key of ["current", "previous", "yearAgo"]) {
      add(department[key], {
        Sales: store[key].sales,
        GrossProfit: store[key].grossProfit,
        MarginBase: store[key].marginBase,
      });
    }
    departmentMap.set(name, department);
  }

  const total = {
    name: "合计",
    isTotal: true,
    current: metric(),
    previous: metric(),
    yearAgo: metric(),
  };
  for (const store of stores.values()) {
    for (const key of ["current", "previous", "yearAgo"]) {
      add(total[key], {
        Sales: store[key].sales,
        GrossProfit: store[key].grossProfit,
        MarginBase: store[key].marginBase,
      });
    }
  }

  const departments = [...departmentMap.values(), total].map((department) => ({
    name: department.name,
    isTotal: department.isTotal,
    current: {
      sales: department.current.sales,
      grossProfit: department.current.grossProfit,
      grossMargin: department.current.grossMargin,
    },
    previous: { sales: department.previous.sales, grossMargin: department.previous.grossMargin },
    yearAgo: { sales: department.yearAgo.sales, grossMargin: department.yearAgo.grossMargin },
    momSalesGrowth: growth(
      department.current.sales,
      department.previous.sales,
      effective.daysCurrent,
      effective.daysPrevious,
    ),
    yoySalesGrowth: simpleGrowth(department.current.sales, department.yearAgo.sales),
  }));

  const periods = [
    ["current", context.period],
    ["previous", context.previous],
    ["yearAgo", context.yearAgo],
  ].map(([key, period]) => {
    const [year, month] = period.split("-").map(Number);
    return { key, year, month, label: period };
  });
  const periodRows = storeRows.flatMap((store) => periods.map((period) => ({
    period: period.label,
    periodKey: period.key,
    year: period.year,
    month: period.month,
    department: store.department,
    leader: store.leader,
    operator: store.operator,
    store: store.store,
    sales: store[period.key].sales,
    grossProfit: stores.get(store.store)[period.key].grossProfit,
    grossMargin: store[period.key].grossMargin,
  })));

  return { value: { periods, departments, stores: storeRows, periodRows }, effective };
}

const categoryDefinitions = [
  { key: "paired", label: "对毛", industryLabel: "对毛-化纤" },
  { key: "cluster", label: "簇毛", industryLabel: "簇毛" },
];

export function shapeCategorySegments(rows) {
  const bySegment = new Map();
  for (const row of rows) {
    const key = String(row.SegmentKey || "");
    if (!bySegment.has(key)) bySegment.set(key, new Map());
    bySegment.get(key).set(nullableText(row.Department), row);
  }

  return {
    categories: categoryDefinitions.map((definition) => {
      const segmentRows = bySegment.get(definition.key) || new Map();
      const representative = segmentRows.values().next().value || {};
      return {
        ...definition,
        company: {
          current: {
            sales: finite(representative.CurrentCompanySales),
            usSales: finite(representative.CurrentCompanyUsSales),
          },
          previous: {
            sales: finite(representative.PreviousCompanySales),
            usSales: finite(representative.PreviousCompanyUsSales),
          },
          yearAgo: {
            sales: finite(representative.YearAgoCompanySales),
            usSales: finite(representative.YearAgoCompanyUsSales),
          },
        },
        industry: {
          current: { sales: 0, coveredDays: 0, dailySales: null },
          previous: { sales: 0, coveredDays: 0, dailySales: null },
        },
        shareDaily: [],
        departments: DEPARTMENT_MAPPINGS.map(({ source, aliases, display }) => {
          const row = [source, ...aliases]
            .map((department) => segmentRows.get(department))
            .find(Boolean) || {};
          return {
            department: display,
            currentSales: finite(row.CurrentDepartmentSales),
            previousSales: finite(row.PreviousDepartmentSales),
            yearAgoSales: finite(row.YearAgoDepartmentSales),
            currentUsSales: finite(row.CurrentDepartmentUsSales),
            previousUsSales: finite(row.PreviousDepartmentUsSales),
            yearAgoUsSales: finite(row.YearAgoDepartmentUsSales),
          };
        }),
      };
    }),
  };
}

export function shapeShipping(rows, snapshot) {
  const fallback = new Map(snapshot.shipping.map((row) => [row.store, row]));
  return rows.map((row) => {
    const totalUnits = finite(row.TotalUnits);
    const oceanUnits = finite(row.OceanUnits);
    const airUnits = finite(row.AirUnits);
    const old = fallback.get(finite(row.Store));
    return {
      department: toDisplayDepartment(row.Department) || toDisplayDepartment(old?.department),
      leader: nullableText(row.Leader) || old?.leader || null,
      operator: nullableText(row.Operator) || old?.operator || null,
      store: finite(row.Store),
      totalUnits,
      oceanUnits,
      airUnits,
      oceanShare: totalUnits ? oceanUnits / totalUnits : 0,
      airShare: totalUnits ? airUnits / totalUnits : 0,
      tier: nullableText(row.Tier) || old?.tier || null,
    };
  });
}

export function shapeSlowMoving(rows) {
  const totals = rows.reduce((result, row) => ({
    inventory: result.inventory + finite(row.InventoryAmount),
    slow: result.slow + finite(row.SlowMovingAmount),
  }), { inventory: 0, slow: 0 });
  return rows.map((row) => {
    const inventoryAmount = finite(row.InventoryAmount);
    const slowMovingAmount = finite(row.SlowMovingAmount);
    return {
      department: toDisplayDepartment(row.Department),
      leader: nullableText(row.Leader),
      operator: nullableText(row.Operator),
      store: finite(row.Store),
      inventoryAmount,
      slowMovingAmount,
      slowMovingShare: inventoryAmount ? slowMovingAmount / inventoryAmount : null,
      negativeRevenue: totals.inventory
        ? Math.round((slowMovingAmount - inventoryAmount * totals.slow / totals.inventory) * 0.03)
        : null,
    };
  });
}

export function shapeUnshipped(rows) {
  return rows.map((row) => ({
    department: toDisplayDepartment(row.Department),
    leader: nullableText(row.Leader),
    operator: nullableText(row.Operator),
    store: finite(row.Store),
    skuCount: finite(row.SkuCount),
    amount: finite(row.Amount),
  }));
}

export function shapeNewProductOrders(rows) {
  return rows.map((row) => ({
    orderedOn: isoDay(row.OrderedOn),
    department: toDisplayDepartment(row.Department),
    leader: nullableText(row.Leader),
    operator: nullableText(row.Operator),
    store: finite(row.Store),
    sku: String(row.Sku || ""),
    mainSku: String(row.Sku || ""),
  }));
}

export function shapeMagnetDaily(rows) {
  return rows.map((row) => ({
    date: isoDay(row.BusinessDate),
    sales: finite(row.Sales),
    series: "图创磁铁销售额",
    comparison: "current",
  }));
}
