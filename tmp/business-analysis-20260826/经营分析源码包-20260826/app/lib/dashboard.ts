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
}

export interface CategorySegment {
  key: "paired" | "cluster";
  label: "对毛" | "簇毛";
  industryLabel: string;
  company: {
    current: { sales: number; usSales: number };
    previous: { sales: number; usSales: number };
  };
  industry: {
    current: { sales: number; coveredDays: number; dailySales: number | null };
    previous: { sales: number; coveredDays: number; dailySales: number | null };
  };
  departments: Array<{
    department: string;
    currentSales: number;
    previousSales: number;
    currentUsSales: number;
    previousUsSales: number;
  }>;
  shareDaily?: Array<{
    date: string;
    marketSales: number;
    companySales: number;
    companyShare: number | null;
  }>;
}

export const FOCUS_DEPARTMENTS = ["周雪", "郭鑫", "侯瑞昕", "大张雯", "王钰媛"] as const;

const focusDepartmentSet = new Set<string>(FOCUS_DEPARTMENTS);

export function isFocusDepartment(department: string) {
  return focusDepartmentSet.has(department);
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
  }>;
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
}

export interface StoreView {
  store: number;
  department: string;
  operator: string;
  openedOn: string | null;
  ageYears: number | null;
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

export function buildStoreViews(data: WorkbookData): StoreView[] {
  const rows = new Map<number, StoreView>();
  const periodByLabel = new Map(
    data.performance.periods.map(({ key, year, month }) => [`${year}-${month}`, key]),
  );
  const details = new Map(data.performance.stores.map((row) => [row.store, row]));

  const ensure = (store: number) => {
    if (!rows.has(store)) {
      const detail = details.get(store);
      rows.set(store, {
        store,
        department: detail?.department ?? detail?.leader ?? "未分组",
        operator: detail?.operator ?? "未分配",
        openedOn: detail?.openedOn ?? null,
        ageYears: detail?.ageYears ?? null,
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
      target.department = row.department ?? target.department;
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
    if (row.department) target.department = row.department;
    if (target.operator === "未分配" && row.operator) target.operator = row.operator;
    target.inventoryAmount = row.inventoryAmount;
    target.slowMovingAmount = row.slowMovingAmount;
    target.slowMovingShare = row.slowMovingShare;
    target.negativeRevenue = row.negativeRevenue;
  }

  for (const row of data.shipping) {
    const target = ensure(row.store);
    if (row.department) target.department = row.department;
    if (target.operator === "未分配" && row.operator) target.operator = row.operator;
    target.shippingUnits = row.totalUnits;
    target.oceanUnits = row.oceanUnits;
    target.airUnits = row.airUnits;
    target.oceanShare = row.oceanShare;
    target.airShare = row.airShare;
  }

  for (const row of data.unshipped) {
    const target = ensure(row.store);
    if (row.department) target.department = row.department;
    if (target.operator === "未分配" && row.operator) target.operator = row.operator;
    target.unshippedCount += row.skuCount;
    target.unshippedAmount += row.amount;
  }

  for (const row of data.newProductOrders) {
    const target = ensure(row.store);
    if (row.department) target.department = row.department;
    if (target.operator === "未分配" && row.operator) target.operator = row.operator;
  }

  return [...rows.values()].sort((a, b) => b.current.sales - a.current.sales);
}

export function matchesFilters(row: StoreView, filters: Filters) {
  return (
    (!filters.department || row.department === filters.department) &&
    (!filters.operator || row.operator === filters.operator) &&
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
  if (Math.abs(value) >= 10000) return `${(value / 10000).toFixed(value >= 1000000 ? 1 : 2)}万`;
  return money(value);
};

export const integer = (value: number) => new Intl.NumberFormat("zh-CN").format(Math.round(value));

export const percent = (value: number | null, digits = 1) =>
  value === null || !Number.isFinite(value) ? "—" : `${(value * 100).toFixed(digits)}%`;

export const shortDate = (value: string) => value.slice(5).replace("-", "/");
