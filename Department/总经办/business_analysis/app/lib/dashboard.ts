export type PeriodKey = "current" | "previous" | "yearAgo";

export interface PeriodMetric {
  sales: number;
  grossProfit: number;
  grossMarginBase: number;
  grossMargin: number | null;
}

export interface Filters {
  department: string;
  operator: string;
  store: string;
  tier?: string;
}

export interface StoreTier {
  store: number;
  tier: string | null;
  tierRank?: number | null;
  currentLevelDays?: number | null;
  department?: string | null;
  leader?: string | null;
  operator?: string | null;
  effectiveDate?: string | null;
}

export interface CategorySegment {
  key: "paired" | "cluster";
  label: "对毛" | "簇毛";
  industryLabel: string;
  company: {
    current: { sales: number; usSales: number };
    previous: { sales: number; usSales: number };
    yearAgo?: { sales: number; usSales: number };
  };
  industry: {
    current: { sales: number; coveredDays: number; dailySales: number | null };
    previous: { sales: number; coveredDays: number; dailySales: number | null };
  };
  departments: Array<{
    department: string;
    currentSales: number;
    previousSales: number;
    yearAgoSales?: number;
    currentUsSales: number;
    previousUsSales: number;
    yearAgoUsSales?: number;
  }>;
  shareDaily?: Array<{
    date: string;
    marketSales: number;
    companySales: number;
    companyShare: number | null;
  }>;
  ratios?: {
    company: {
      currentSales: number | null;
      previousSales: number | null;
      yearAgoSales: number | null;
      currentDailySales: number | null;
      previousDailySales: number | null;
      yearAgoDailySales: number | null;
      dailyMom: number | null;
      dailyYoy: number | null;
      usDailyMom: number | null;
      usDailyYoy: number | null;
      currentUsShare: number | null;
      previousUsShare: number | null;
      yearAgoUsShare: number | null;
    };
    departments: Array<{
      department: string;
      currentSales?: number | null;
      currentDailySales?: number | null;
      currentShare: number | null;
      previousShare: number | null;
      yearAgoShare: number | null;
      dailyMom: number | null;
      dailyYoy: number | null;
      currentUsShare: number | null;
      previousUsShare: number | null;
      yearAgoUsShare: number | null;
    }>;
  };
}

const DEPARTMENT_NAMES: Record<string, string> = {
  周雪: "运营一部",
  王钰媛: "运营二部",
  大张雯: "运营三部",
  郭鑫: "运营六部",
  侯瑞昕: "运营七部",
  侯瑞欣: "运营七部",
};

export const FOCUS_DEPARTMENTS = ["运营一部", "运营二部", "运营三部", "运营六部", "运营七部"] as const;

export function normalizeDepartmentName(department: string | null | undefined) {
  if (!department) return department ?? null;
  return DEPARTMENT_NAMES[department] ?? department;
}

const focusDepartmentSet = new Set<string>(FOCUS_DEPARTMENTS);

export function isFocusDepartment(department: string) {
  return focusDepartmentSet.has(department);
}

export interface BusinessAnalysisAccessScope {
  role: "business_owner" | "department_leader" | "member" | "ratio_viewer";
  department: string | null;
  operator: string | null;
  userName: string;
  canViewAmounts: boolean;
  categoryRatioVisible: boolean;
}

export interface WorkbookData {
  meta: {
    sourceFile: string;
    extractedAt: string;
    sheetCount: number;
    nonEmptySheetCount: number;
    drawingCount: number;
    dateRanges: Record<string, { start: string; end: string }>;
    rowCounts: Record<string, number>;
    sourceTotals: Record<string, number>;
    reconciliation: Record<string, { source: number; calculated: number; match: boolean }>;
    accessScope?: BusinessAnalysisAccessScope;
    storeTier?: {
      effectiveDate: string | null;
      updatedAt: string | null;
      source: string;
      stale: boolean;
      warning: string | null;
    };
  };
  performance: {
    periods: Array<{ key: PeriodKey; year: number; month: number; label: string }>;
    departments: Array<{
      name: string;
      isTotal: boolean;
      current: { sales: number; grossProfit: number; grossMargin: number | null };
      previous: { sales: number; grossMargin: number | null };
      yearAgo: { sales: number; grossMargin: number | null };
      momSalesGrowth: number | null;
      yoySalesGrowth: number | null;
    }>;
    stores: Array<{
      department?: string | null;
      leader: string | null;
      operator: string | null;
      store: number;
      openedOn: string | null;
      ageYears: number | null;
      tier?: string | null;
      tierRank?: number | null;
    }>;
    periodRows: Array<{
      periodKey: PeriodKey;
      year: number;
      month: number;
      period: string;
      store: number;
      operator: string | null;
      department?: string | null;
      leader: string | null;
      sales: number;
      grossProfit: number | null;
      grossMargin: number | null;
    }>;
  };
  slowMoving: Array<{
    department: string | null;
    leader?: string | null;
    operator: string | null;
    store: number;
    inventoryAmount: number;
    slowMovingAmount: number;
    slowMovingShare: number;
    negativeRevenue: number;
  }>;
  shipping: Array<{
    department: string | null;
    leader?: string | null;
    operator: string | null;
    store: number;
    totalUnits: number;
    oceanUnits: number;
    airUnits: number;
    oceanShare: number;
    airShare: number;
    tier?: string | null;
  }>;
  storeTiers?: StoreTier[];
  newProductOrders: Array<{
    orderedOn: string;
    department?: string | null;
    leader?: string | null;
    operator?: string | null;
    store: number;
    sku: string;
    mainSku: string;
  }>;
  unshipped: Array<{
    department?: string | null;
    leader?: string | null;
    operator: string | null;
    store: number;
    skuCount: number;
    amount: number;
  }>;
  magnetDaily: Array<{
    date: string;
    sales: number;
    series: string;
    comparison: string;
  }>;
  categorySegments?: {
    categories: CategorySegment[];
  };
  categorySegmentsByPeriod?: Record<string, { categories: CategorySegment[] }>;
}

export interface StoreView {
  store: number;
  department: string;
  operator: string;
  openedOn: string | null;
  ageYears: number | null;
  tier: string | null;
  tierRank: number | null;
  currentLevelDays: number | null;
  hasPerformance: boolean;
  current: PeriodMetric;
  previous: PeriodMetric;
  yearAgo: PeriodMetric;
  inventoryAmount: number;
  slowMovingAmount: number;
  slowMovingShare: number;
  negativeRevenue: number;
  shippingUnits: number;
  oceanUnits: number;
  airUnits: number;
  oceanShare: number;
  airShare: number;
  unshippedCount: number;
  unshippedAmount: number;
}

export interface DepartmentView {
  name: string;
  stores: number;
  current: PeriodMetric;
  previous: PeriodMetric;
  yearAgo: PeriodMetric;
  dailyMom: number | null;
  yoy: number | null;
}

export interface OverallPerformanceSummary {
  current: PeriodMetric & { dailySales: number | null };
  previous: PeriodMetric & { dailySales: number | null };
  yearAgo: PeriodMetric & { dailySales: number | null };
  dailyMom: number | null;
  dailyYoy: number | null;
  marginMom: number | null;
  marginYoy: number | null;
}

const emptyMetric = (): PeriodMetric => ({
  sales: 0,
  grossProfit: 0,
  grossMarginBase: 0,
  grossMargin: null,
});

const ratio = (value: number, base: number) => (base ? value / base : null);

const TIER_GROUPS: Record<string, number> = {
  铜: 0,
  銅: 0,
  银: 3,
  銀: 3,
  金: 7,
  钻: 16,
  鑽: 16,
};

export function tierRankValue(value: string | null | undefined) {
  const match = value?.replace(/\s+/g, "").match(/^(铜|銅|银|銀|金|钻|鑽)(\d+)$/);
  if (!match) return null;
  const group = TIER_GROUPS[match[1]];
  const level = Number(match[2]);
  return Number.isInteger(group) && Number.isInteger(level) && level > 0
    ? group + level
    : null;
}

export function buildStoreViews(data: WorkbookData): StoreView[] {
  const rows = new Map<number, StoreView>();
  const periodByLabel = new Map(
    data.performance.periods.map(({ key, year, month }) => [`${year}-${month}`, key]),
  );
  const details = new Map(data.performance.stores.map((row) => [row.store, row]));
  const tierDetails = new Map((data.storeTiers ?? []).map((row) => [row.store, row]));

  const ensure = (store: number) => {
    if (!rows.has(store)) {
      const detail = details.get(store);
      const tierDetail = tierDetails.get(store);
      rows.set(store, {
        store,
        department: normalizeDepartmentName(detail?.department ?? detail?.leader) ?? "未分组",
        operator: detail?.operator ?? "未分配",
        openedOn: detail?.openedOn ?? null,
        ageYears: detail?.ageYears ?? null,
        tier: tierDetail?.tier ?? detail?.tier ?? null,
        tierRank: tierDetail?.tierRank ?? detail?.tierRank ?? tierRankValue(tierDetail?.tier ?? detail?.tier),
        currentLevelDays: tierDetail?.currentLevelDays ?? detail?.currentLevelDays ?? null,
        hasPerformance: false,
        current: emptyMetric(),
        previous: emptyMetric(),
        yearAgo: emptyMetric(),
        inventoryAmount: 0,
        slowMovingAmount: 0,
        slowMovingShare: 0,
        negativeRevenue: 0,
        shippingUnits: 0,
        oceanUnits: 0,
        airUnits: 0,
        oceanShare: 0,
        airShare: 0,
        unshippedCount: 0,
        unshippedAmount: 0,
      });
    }
    return rows.get(store)!;
  };

  for (const row of data.performance.periodRows) {
    const key = row.periodKey ?? periodByLabel.get(`${row.year}-${row.month}`);
    if (!key) continue;
    const target = ensure(row.store);
    if (key === "current") {
      target.hasPerformance = true;
      target.department = normalizeDepartmentName(row.department) ?? target.department;
      target.operator = row.operator ?? target.operator;
    }
    const grossProfit = row.grossProfit ?? 0;
    const grossMarginBase = grossProfit && row.grossMargin ? grossProfit / row.grossMargin : 0;
    target[key] = {
      sales: row.sales,
      grossProfit,
      grossMarginBase,
      grossMargin: grossMarginBase ? row.grossMargin : null,
    };
  }

  for (const row of data.slowMoving) {
    const target = ensure(row.store);
    if (row.department) target.department = normalizeDepartmentName(row.department) ?? target.department;
    if (target.operator === "未分配" && row.operator) target.operator = row.operator;
    target.inventoryAmount = row.inventoryAmount;
    target.slowMovingAmount = row.slowMovingAmount;
    target.slowMovingShare = row.slowMovingShare;
    target.negativeRevenue = row.negativeRevenue;
  }

  for (const row of data.shipping) {
    const target = ensure(row.store);
    if (row.department) target.department = normalizeDepartmentName(row.department) ?? target.department;
    if (target.operator === "未分配" && row.operator) target.operator = row.operator;
    target.shippingUnits = row.totalUnits;
    target.oceanUnits = row.oceanUnits;
    target.airUnits = row.airUnits;
    target.oceanShare = row.oceanShare;
    target.airShare = row.airShare;
    if (row.tier && !target.tier) {
      target.tier = row.tier;
      target.tierRank = target.tierRank ?? tierRankValue(row.tier);
    }
  }

  for (const row of data.unshipped) {
    const target = ensure(row.store);
    if (row.department) target.department = normalizeDepartmentName(row.department) ?? target.department;
    if (target.operator === "未分配" && row.operator) target.operator = row.operator;
    target.unshippedCount += row.skuCount;
    target.unshippedAmount += row.amount;
  }

  for (const row of data.newProductOrders) {
    const target = ensure(row.store);
    if (row.department) target.department = normalizeDepartmentName(row.department) ?? target.department;
    if (target.operator === "未分配" && row.operator) target.operator = row.operator;
  }

  // Tier-only stores (for example a newly opened store with no sales rows)
  // still need to be visible in the store-level view.
  for (const row of data.storeTiers ?? []) {
    const target = ensure(row.store);
    if (row.department) target.department = normalizeDepartmentName(row.department) ?? target.department;
    if (row.operator && target.operator === "未分配") target.operator = row.operator;
    target.tier = row.tier ?? target.tier;
    target.tierRank = row.tierRank ?? target.tierRank ?? tierRankValue(row.tier);
    target.currentLevelDays = row.currentLevelDays ?? target.currentLevelDays;
  }

  return [...rows.values()].sort((a, b) => b.current.sales - a.current.sales);
}

export function matchesFilters(row: StoreView, filters: Filters) {
  return (
    (!filters.department || row.department === filters.department) &&
    (!filters.operator || row.operator === filters.operator) &&
    (!filters.tier || row.tier === filters.tier) &&
    (!filters.store || String(row.store) === filters.store)
  );
}

export function aggregateMetric(rows: StoreView[], key: PeriodKey): PeriodMetric {
  const metric = rows.reduce(
    (sum, row) => ({
      sales: sum.sales + row[key].sales,
      grossProfit: sum.grossProfit + row[key].grossProfit,
      grossMarginBase: sum.grossMarginBase + row[key].grossMarginBase,
      grossMargin: null,
    }),
    emptyMetric(),
  );
  metric.grossMargin = ratio(metric.grossProfit, metric.grossMarginBase);
  return metric;
}

export function summarizeOverallPerformance(
  rows: StoreView[],
  days: Record<PeriodKey, number>,
): OverallPerformanceSummary {
  const withDaily = (key: PeriodKey) => {
    const metric = aggregateMetric(rows, key);
    return { ...metric, dailySales: days[key] > 0 ? metric.sales / days[key] : null };
  };
  const current = withDaily("current");
  const previous = withDaily("previous");
  const yearAgo = withDaily("yearAgo");
  const compare = (value: number | null, base: number | null) =>
    value === null || base === null || !base ? null : value / base - 1;
  const difference = (value: number | null, base: number | null) =>
    value === null || base === null ? null : value - base;

  return {
    current,
    previous,
    yearAgo,
    dailyMom: compare(current.dailySales, previous.dailySales),
    dailyYoy: compare(current.dailySales, yearAgo.dailySales),
    marginMom: difference(current.grossMargin, previous.grossMargin),
    marginYoy: difference(current.grossMargin, yearAgo.grossMargin),
  };
}

export function aggregateDepartments(
  rows: StoreView[],
  currentDays = 31,
  previousDays = 30,
): DepartmentView[] {
  const grouped = new Map<string, StoreView[]>();
  for (const row of rows) grouped.set(row.department, [...(grouped.get(row.department) ?? []), row]);
  return [...grouped.entries()]
    .map(([name, stores]) => {
      const current = aggregateMetric(stores, "current");
      const previous = aggregateMetric(stores, "previous");
      const yearAgo = aggregateMetric(stores, "yearAgo");
      return {
        name,
        stores: stores.length,
        current,
        previous,
        yearAgo,
        dailyMom: ratio(current.sales / currentDays, previous.sales / previousDays),
        yoy: ratio(current.sales, yearAgo.sales),
      };
    })
    .map((row) => ({
      ...row,
      dailyMom: row.dailyMom === null ? null : row.dailyMom - 1,
      yoy: row.yoy === null ? null : row.yoy - 1,
    }))
    .sort((a, b) => b.current.sales - a.current.sales);
}

export const money = (value: number) =>
  new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY", maximumFractionDigits: 0 }).format(value);

export const compactMoney = (value: number) => {
  return money(value);
};

export const integer = (value: number) => new Intl.NumberFormat("zh-CN").format(Math.round(value));

export const percent = (value: number | null, _digits = 2) => {
  if (value === null || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(2)}%`;
};

export const shortDate = (value: string) => value.slice(5).replace("-", "/");
