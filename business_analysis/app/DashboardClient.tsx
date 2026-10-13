"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ECElementEvent, EChartsOption } from "echarts";
import EChart from "./components/EChart";
import FiscalOverview from "./components/FiscalOverview";
import KeyTasksBoard from "./components/KeyTasksBoard";
import { MARKET_OVERVIEW_ROWS } from "./data/marketOverview";
import { useLiveDashboard } from "./hooks/useLiveDashboard";
import {
  aggregateDepartments,
  aggregateMetric,
  buildStoreViews,
  compactMoney,
  FOCUS_DEPARTMENTS,
  integer,
  isFocusDepartment,
  matchesFilters,
  money,
  percent,
  shortDate,
  summarizeOverallPerformance,
  tierRankValue,
  type BusinessAnalysisAccessScope,
  type CategorySegment,
  type Filters,
  type WorkbookData,
} from "./lib/dashboard";

type Theme = "light" | "dark";
type SortMode = "sales" | "growth" | "margin" | "slow" | "tier";
type DashboardTab = "home" | "performance" | "market" | "categories" | "operations" | "stores" | "tasks";
type RiskTab = "inventory" | "fulfillment" | "shipping" | "new";
type FormulaId = "sales.current" | "profit.current" | "margin.current" | "growth.daily_mom";

interface FormulaDetail {
  id: FormulaId;
  label: string;
  value: string;
  expression: string;
  note: string;
  inputs: Array<{ label: string; value: string; source: string }>;
  sql: string;
}

interface RiskDetailRow {
  store: number;
  department: string;
  operator: string;
  primary: string;
  secondary: string;
  sortValue: number;
  comparison?: string;
}

interface StoreTierHistoryRow {
  date: string;
  store: number;
  tier: string;
  tierRank: number | null;
  department: string;
  leader: string;
  operator: string;
}

interface StoreTierHistoryMeta {
  store: number;
  currentTier: string;
  currentLevelDays: number;
  historicalOfficialTier: string | null;
  historicalOfficialTierRank: number | null;
  officialSince: string | null;
  officialSource: string | null;
}

const riskTableLabels: Record<RiskTab, { primary: string; secondary: string; empty: string }> = {
  inventory: { primary: "滞销金额", secondary: "滞销率", empty: "当前范围没有滞销记录" },
  fulfillment: { primary: "未发货金额", secondary: "SKU 次数", empty: "当前范围没有未发货记录" },
  shipping: { primary: "发货件数", secondary: "海运 / 空派", empty: "当前范围没有运输记录" },
  new: { primary: "主 SKU", secondary: "原始记录", empty: "当前范围没有新品记录" },
};

const defaultFilters: Filters = { department: "", operator: "", store: "", tier: "" };

const trendTone = (value: number | null) =>
  value === null ? "neutral" : value >= 0 ? "positive" : "negative";

const growthLabel = (value: number | null, digits = 1) => {
  if (value === null || !Number.isFinite(value)) return "—";
  if (Math.abs(value) > 9.99) return value > 0 ? ">999.00%" : "<-999.00%";
  return percent(value, digits);
};

const movementLabel = (value: number | null) =>
  value === null ? "暂无可比数据" : `${value >= 0 ? "上升" : "下降"} ${percent(Math.abs(value), 2)}`;

const categoryAmountLabel = (value: number | null, visible: boolean) =>
  visible ? (value !== null && Number.isFinite(value) ? compactMoney(value) : "—") : "---";

const pointMovementLabel = (value: number | null) => {
  if (value === null || !Number.isFinite(value)) return "暂无可比数据";
  if (Math.abs(value) < 0.00005) return "基本持平";
  return `${value > 0 ? "上升" : "下降"} ${(Math.abs(value) * 100).toFixed(2)} 个百分点`;
};

const tierTone = (tier: string | null) => {
  if (!tier) return "unknown";
  if (/^[钻鑽]/.test(tier)) return "diamond";
  if (tier.startsWith("金")) return "gold";
  if (/^[银銀]/.test(tier)) return "silver";
  if (/^[铜銅]/.test(tier)) return "bronze";
  return "unknown";
};

const averageComparisonLabel = (value: number, average: number, benchmarkLabel: string) => {
  if (!average) return value ? `高于${benchmarkLabel}` : `与${benchmarkLabel}持平`;
  const difference = value / average - 1;
  if (Math.abs(difference) < 0.0005) return `与${benchmarkLabel}持平`;
  return `${difference > 0 ? "高于" : "低于"}${benchmarkLabel} ${percent(Math.abs(difference), 1)}`;
};

function KpiCard({
  label,
  value,
  note,
  delta,
  tone = "neutral",
  priority = false,
  formulaId,
  onInspect,
}: {
  label: string;
  value: string;
  note: string;
  delta?: string;
  tone?: "neutral" | "positive" | "negative" | "warning";
  priority?: boolean;
  formulaId: FormulaId;
  onInspect: (id: FormulaId) => void;
}) {
  return (
    <article className={`kpi-card kpi-${tone}${priority ? " kpi-primary" : ""}`}>
      <div className="kpi-topline">
        <span>{label}</span>
        <div>
          {delta ? <span className="kpi-delta">{delta}</span> : null}
          <button className="formula-trigger" type="button" onClick={() => onInspect(formulaId)} aria-label={`查看${label}公式`}>fx</button>
        </div>
      </div>
      <button className="kpi-value" type="button" onClick={() => onInspect(formulaId)}>{value}</button>
      <p>{note}</p>
    </article>
  );
}

function SelectField({
  label,
  value,
  options,
  allLabel = "全部",
  disabled = false,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  allLabel?: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="filter-field">
      <span>{label}</span>
      <select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
        <option value="">{allLabel}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function PanelTitle({
  title,
  copy,
  tag,
  metric,
}: {
  title: string;
  copy: string;
  tag?: string;
  metric?: string;
}) {
  return (
    <div className="panel-title">
      <div>
        <div className="panel-title-heading">
          <h3>{title}</h3>
          {metric ? <span className="panel-title-metric">{metric}</span> : null}
        </div>
        <p>{copy}</p>
      </div>
      {tag ? <span className="panel-tag">{tag}</span> : null}
    </div>
  );
}

function CategoryArena({
  segment,
  currentLabel,
  previousLabel,
  yearAgoLabel,
  canViewAmounts,
}: {
  segment: CategorySegment;
  currentLabel: string;
  previousLabel: string;
  yearAgoLabel: string;
  canViewAmounts: boolean;
}) {
  const companyRatios = segment.ratios?.company;
  const ratioByDepartment = new Map(
    (segment.ratios?.departments ?? []).map((row) => [row.department, row]),
  );
  const departmentRows = FOCUS_DEPARTMENTS
    .map((department) => ratioByDepartment.get(department))
    .filter((row): row is NonNullable<CategorySegment["ratios"]>["departments"][number] => Boolean(row));
  const companyMom = companyRatios?.dailyMom ?? null;
  const companyYoy = companyRatios?.dailyYoy ?? null;
  const usMom = companyRatios?.usDailyMom ?? null;
  const usYoy = companyRatios?.usDailyYoy ?? null;

  return (
    <article className={`category-arena category-${segment.key}`}>
      <header className="category-arena-head">
        <div>
          <span className="eyebrow">Category arena</span>
          <h3>{segment.label}</h3>
          <p>{canViewAmounts ? "展示总体销售额、日均销售额、增长与美国口径占比" : "绝对金额已隐藏，仅展示增长、销售结构与美国口径占比"}</p>
        </div>
        <span className={`trend-pill ${trendTone(companyMom)}`}>图创日均 {growthLabel(companyMom, 2)}</span>
      </header>

      <div className="category-compare-grid company-only">
        <section className="category-data-block">
          <div className="category-block-title"><b>图创公司{segment.label}</b><span>比例公开</span></div>
          <div className="table-scroll table-scroll-compact">
            <table className="compact-table category-metric-table company-category-table">
              <thead><tr><th>期间</th><th>总体销售额</th><th>日均销售额</th><th>美国销售占比</th><th>占比变化</th></tr></thead>
              <tbody>
                <tr><td>{yearAgoLabel}</td><td>{categoryAmountLabel(companyRatios?.yearAgoSales ?? null, canViewAmounts)}</td><td>{categoryAmountLabel(companyRatios?.yearAgoDailySales ?? null, canViewAmounts)}</td><td>{percent(companyRatios?.yearAgoUsShare ?? null, 2)}</td><td>同比基期</td></tr>
                <tr><td>{previousLabel}</td><td>{categoryAmountLabel(companyRatios?.previousSales ?? null, canViewAmounts)}</td><td>{categoryAmountLabel(companyRatios?.previousDailySales ?? null, canViewAmounts)}</td><td>{percent(companyRatios?.previousUsShare ?? null, 2)}</td><td>环比基期</td></tr>
                <tr><td>{currentLabel}</td><td><b>{categoryAmountLabel(companyRatios?.currentSales ?? null, canViewAmounts)}</b></td><td><b>{categoryAmountLabel(companyRatios?.currentDailySales ?? null, canViewAmounts)}</b></td><td><b>{percent(companyRatios?.currentUsShare ?? null, 2)}</b></td><td>{pointMovementLabel(
                  companyRatios?.currentUsShare != null && companyRatios.previousUsShare != null
                    ? companyRatios.currentUsShare - companyRatios.previousUsShare
                    : null,
                )}</td></tr>
              </tbody>
              <tfoot>
                <tr><td colSpan={2}>日均环比</td><td><span className={`trend-pill ${trendTone(companyMom)}`}>{growthLabel(companyMom, 2)}</span></td><td colSpan={2}>美国口径 {growthLabel(usMom, 2)}</td></tr>
                <tr><td colSpan={2}>日均同比</td><td><span className={`trend-pill ${trendTone(companyYoy)}`}>{growthLabel(companyYoy, 2)}</span></td><td colSpan={2}>美国口径 {growthLabel(usYoy, 2)}</td></tr>
              </tfoot>
            </table>
          </div>
        </section>
      </div>

      <p className="category-insight">
        图创公司较上月{movementLabel(companyMom)}，较去年同期{movementLabel(companyYoy)}；美国口径环比{movementLabel(usMom)}、同比{movementLabel(usYoy)}。
      </p>

      <section className="category-department-block">
        <div className="category-block-title"><b>五部门{segment.label}比例</b><span>所有成员可见</span></div>
        <div className="table-scroll table-scroll-compact">
          <table className="compact-table category-department-table">
            <thead><tr><th>部门</th><th>{currentLabel}总体销售额</th><th>{currentLabel}日均销售额</th><th>{yearAgoLabel}占比</th><th>{previousLabel}占比</th><th>{currentLabel}占比</th><th>占比变化</th><th>日均环比</th><th>日均同比</th><th>美国销售占比</th></tr></thead>
            <tbody>
              {departmentRows.map((row) => {
                const shareChange = row.currentShare != null && row.previousShare != null
                  ? row.currentShare - row.previousShare
                  : null;
                return (
                  <tr key={row.department}>
                    <td><b>{row.department}</b></td>
                    <td>{categoryAmountLabel(row.currentSales ?? null, row.currentSales != null)}</td>
                    <td>{categoryAmountLabel(row.currentDailySales ?? null, row.currentDailySales != null)}</td>
                    <td>{percent(row.yearAgoShare, 2)}</td>
                    <td>{percent(row.previousShare, 2)}</td>
                    <td><b>{percent(row.currentShare, 2)}</b></td>
                    <td><span className={`trend-text ${trendTone(shareChange)}`}>{pointMovementLabel(shareChange)}</span></td>
                    <td><span className={`trend-pill ${trendTone(row.dailyMom)}`}>{growthLabel(row.dailyMom, 2)}</span></td>
                    <td><span className={`trend-pill ${trendTone(row.dailyYoy)}`}>{growthLabel(row.dailyYoy, 2)}</span></td>
                    <td>{percent(row.currentUsShare, 2)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      <p className="category-method">
        金额字段由服务端脱敏；日均同比按本月日均销售 ÷ 去年同月日均销售 − 1 计算，去年同月占比作为同比基期展示。
      </p>
    </article>
  );
}

function FormulaDrawer({
  detail,
  mode,
  evaluatedAt,
  onClose,
}: {
  detail: FormulaDetail;
  mode: string;
  evaluatedAt: string;
  onClose: () => void;
}) {
  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <aside className="formula-drawer" role="dialog" aria-modal="true" aria-labelledby="formula-title">
        <div className="drawer-head">
          <div><span className="eyebrow">Formula trace</span><h2 id="formula-title">{detail.label}</h2></div>
          <button type="button" onClick={onClose} aria-label="关闭公式面板">×</button>
        </div>
        <div className="formula-result">
          <strong>{detail.value}</strong>
          <span className={`source-badge source-${mode}`}>{mode === "daily-snapshot" ? "每日快照" : mode === "database" ? "实时数据库" : mode === "memory-cache" ? "最近成功缓存" : "Excel 快照"}</span>
        </div>
        <section className="formula-block">
          <span>计算公式</span>
          <code>{detail.expression}</code>
          <p>{detail.note}</p>
        </section>
        <section className="formula-block">
          <span>本次输入</span>
          <dl className="formula-inputs">
            {detail.inputs.map((input) => (
              <div key={input.label}><dt>{input.label}<small>{input.source}</small></dt><dd>{input.value}</dd></div>
            ))}
          </dl>
        </section>
        <details className="query-detail">
          <summary>查看数据库聚合</summary>
          <pre>{detail.sql}</pre>
        </details>
        <footer>计算于 {new Date(evaluatedAt).toLocaleString("zh-CN", { hour12: false })}</footer>
      </aside>
    </div>
  );
}

function metricFromEvent(event: ECElementEvent, index: number) {
  return Array.isArray(event.data) ? String(event.data[index] ?? "") : "";
}

function makeDateRange(start: string, end: string) {
  const dates: string[] = [];
  const cursor = new Date(`${start}T00:00:00Z`);
  const last = new Date(`${end}T00:00:00Z`);
  while (cursor <= last) {
    dates.push(cursor.toISOString().slice(0, 10));
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return dates;
}

export default function DashboardClient({ data: initialData }: { data: WorkbookData }) {
  const initialPeriod = initialData.performance.periods.find((row) => row.key === "current");
  const today = new Date();
  const [period, setPeriod] = useState(
    initialData.meta.sourceFile && initialPeriod
      ? `${initialPeriod.year}-${String(initialPeriod.month).padStart(2, "0")}`
      : `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`,
  );
  const live = useLiveDashboard(initialData, period);
  const data = live.data;
  const [resolvedAccessScope, setResolvedAccessScope] = useState<BusinessAnalysisAccessScope | null>(
    initialData.meta.accessScope ?? null,
  );
  useEffect(() => {
    if (data.meta.accessScope || resolvedAccessScope) return;
    const controller = new AbortController();
    const scopeApi = document.documentElement.dataset.scopeApi || "/api/ai/business-analysis/scope";
    void fetch(scopeApi, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`scope request failed: ${response.status}`);
        return response.json() as Promise<{ scope?: BusinessAnalysisAccessScope }>;
      })
      .then((payload) => {
        if (payload.scope) setResolvedAccessScope(payload.scope);
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          console.warn("Business analysis scope request failed", error);
        }
      });
    return () => controller.abort();
  }, [data.meta.accessScope, resolvedAccessScope]);
  const accessScope = data.meta.accessScope ?? resolvedAccessScope ?? undefined;
  const canViewAmounts = accessScope?.canViewAmounts === true;
  const displayMoney = useCallback(
    (value: number) => canViewAmounts ? money(value) : "---",
    [canViewAmounts],
  );
  const displayCompactMoney = useCallback(
    (value: number) => canViewAmounts ? compactMoney(value) : "---",
    [canViewAmounts],
  );
  const displayIntegerAmount = (value: number | null) =>
    canViewAmounts && value !== null ? integer(value) : "---";
  const [theme, setTheme] = useState<Theme>("light");
  const [filters, setFilters] = useState<Filters>(defaultFilters);
  const [sortMode, setSortMode] = useState<SortMode>("margin");
  const [showAll, setShowAll] = useState(false);
  const [showTierHistory, setShowTierHistory] = useState(false);
  const [tierHistoryDays, setTierHistoryDays] = useState(90);
  const [tierHistoryStore, setTierHistoryStore] = useState("");
  const [tierHistoryRows, setTierHistoryRows] = useState<StoreTierHistoryRow[]>([]);
  const [tierHistoryMeta, setTierHistoryMeta] = useState<StoreTierHistoryMeta[]>([]);
  const [tierHistoryLoading, setTierHistoryLoading] = useState(false);
  const [tierHistoryError, setTierHistoryError] = useState("");
  const [activeTab, setActiveTab] = useState<DashboardTab>("home");
  const [riskTab, setRiskTab] = useState<RiskTab>("inventory");
  const [activeFormula, setActiveFormula] = useState<FormulaId | null>(null);
  const themeReady = useRef(false);
  const visibleTab: DashboardTab = activeTab;

  const loadTierHistory = useCallback(async (days: number, store: string) => {
    setTierHistoryLoading(true);
    setTierHistoryError("");
    try {
      const query = new URLSearchParams({ days: String(days) });
      if (store) query.set("store", store);
      const response = await fetch(`/api/ai/business-analysis/store-tier-history?${query}`, {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      const payload = await response.json() as { rows?: StoreTierHistoryRow[]; storeMeta?: StoreTierHistoryMeta[]; error?: { message?: string } };
      if (!response.ok) throw new Error(payload.error?.message || "店铺等级历史读取失败");
      setTierHistoryRows(payload.rows ?? []);
      setTierHistoryMeta(payload.storeMeta ?? []);
    } catch (error) {
      setTierHistoryError(error instanceof Error ? error.message : "店铺等级历史读取失败");
    } finally {
      setTierHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    const saved = localStorage.getItem("sales-dashboard-theme") as Theme | null;
    const next = saved ?? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const frame = requestAnimationFrame(() => {
      document.documentElement.dataset.theme = next;
      setTheme(next);
      themeReady.current = true;
    });
    return () => cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    if (!themeReady.current) return;
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("sales-dashboard-theme", theme);
  }, [theme]);

  useEffect(() => {
    if (!activeFormula) return;
    const close = (event: KeyboardEvent) => event.key === "Escape" && setActiveFormula(null);
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [activeFormula]);

  useEffect(() => {
    if (!showTierHistory) return;
    const close = (event: KeyboardEvent) => event.key === "Escape" && setShowTierHistory(false);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", close);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", close);
    };
  }, [showTierHistory]);

  const allStores = useMemo(() => buildStoreViews(data), [data]);
  const stores = useMemo(
    () => allStores.filter((row) => isFocusDepartment(row.department)),
    [allStores],
  );
  const tierHistoryDates = useMemo(
    () => [...new Set(tierHistoryRows.map((row) => row.date))].sort((a, b) => b.localeCompare(a)),
    [tierHistoryRows],
  );
  const tierHistoryMatrix = useMemo(() => {
    const metaByStore = new Map(tierHistoryMeta.map((item) => [item.store, item]));
    const grouped = new Map<number, { store: number; department: string; operator: string; tiers: Map<string, string>; meta?: StoreTierHistoryMeta }>();
    for (const row of tierHistoryRows) {
      const item = grouped.get(row.store) ?? {
        store: row.store,
        department: row.department,
        operator: row.operator,
        tiers: new Map<string, string>(),
        meta: metaByStore.get(row.store),
      };
      item.tiers.set(row.date, row.tier);
      grouped.set(row.store, item);
    }
    return [...grouped.values()].sort((a, b) => a.store - b.store);
  }, [tierHistoryMeta, tierHistoryRows]);
  const overallStores = useMemo(
    () => allStores.filter((row) => row.hasPerformance || row.current.sales || row.previous.sales || row.yearAgo.sales),
    [allStores],
  );
  const departmentOptions = useMemo(
    () => FOCUS_DEPARTMENTS.filter((name) => stores.some((row) => row.department === name)),
    [stores],
  );
  const operatorOptions = useMemo(
    () =>
      [...new Set(stores
        .filter((row) => !filters.department || row.department === filters.department)
        .filter((row) => !filters.tier || row.tier === filters.tier)
        .map((row) => row.operator))]
        .sort((a, b) => a.localeCompare(b, "zh-CN")),
    [filters.department, filters.tier, stores],
  );
  const storeOptions = useMemo(
    () =>
      stores
        .filter(
          (row) =>
            (!filters.department || row.department === filters.department) &&
            (!filters.operator || row.operator === filters.operator) &&
            (!filters.tier || row.tier === filters.tier),
        )
        .sort((a, b) => a.store - b.store),
    [filters.department, filters.operator, filters.tier, stores],
  );
  const tierOptions = useMemo(
    () => [...new Set(stores.map((row) => row.tier).filter((value): value is string => Boolean(value)))]
      .sort((a, b) => (tierRankValue(b) ?? -1) - (tierRankValue(a) ?? -1)),
    [stores],
  );
  const tierSummary = useMemo(() => {
    const counts = new Map<string, number>();
    for (const row of stores) {
      if (row.tier) counts.set(row.tier, (counts.get(row.tier) ?? 0) + 1);
    }
    return tierOptions.map((tier) => ({ tier, count: counts.get(tier) ?? 0 }));
  }, [stores, tierOptions]);
  const tierAssignedCount = tierSummary.reduce((sum, item) => sum + item.count, 0);
  const tierUnratedCount = Math.max(0, stores.length - tierAssignedCount);
  const filteredStores = useMemo(
    () => stores.filter((row) => matchesFilters(row, filters)),
    [filters, stores],
  );
  const performanceStores = useMemo(
    () => filteredStores.filter((row) => row.hasPerformance),
    [filteredStores],
  );
  const companyPerformanceStores = useMemo(
    () => stores.filter((row) => row.hasPerformance),
    [stores],
  );
  const companySlowMovingAverage = useMemo(
    () => companyPerformanceStores.length
      ? companyPerformanceStores.reduce((sum, row) => sum + row.slowMovingAmount, 0) / companyPerformanceStores.length
      : 0,
    [companyPerformanceStores],
  );
  const slowMovingBenchmarkLabel = accessScope?.role === "business_owner"
    ? "公司均值"
    : accessScope?.role === "department_leader"
      ? "部门均值"
      : "权限范围均值";
  const filteredIds = useMemo(() => new Set(filteredStores.map((row) => row.store)), [filteredStores]);
  const currentPeriod = data.performance.periods.find((row) => row.key === "current");
  const previousPeriod = data.performance.periods.find((row) => row.key === "previous");
  const yearAgoPeriod = data.performance.periods.find((row) => row.key === "yearAgo");
  const traceDays = (key: string) => live.formulas
    .flatMap((formula) => formula.inputs)
    .find((input) => input.key === key)?.value;
  const currentDays = traceDays("daysCurrent") ?? (currentPeriod ? new Date(currentPeriod.year, currentPeriod.month, 0).getDate() : 31);
  const previousDays = traceDays("daysPrevious") ?? (previousPeriod ? new Date(previousPeriod.year, previousPeriod.month, 0).getDate() : 30);
  const yearAgoDays = traceDays("daysYearAgo") ?? (yearAgoPeriod ? new Date(yearAgoPeriod.year, yearAgoPeriod.month, 0).getDate() : 31);
  const categorySegments = data.categorySegments?.categories ?? [];
  const departments = useMemo(
    () => aggregateDepartments(performanceStores, currentDays, previousDays),
    [currentDays, performanceStores, previousDays],
  );
  const current = useMemo(() => aggregateMetric(performanceStores, "current"), [performanceStores]);
  const previous = useMemo(() => aggregateMetric(performanceStores, "previous"), [performanceStores]);
  const yearAgo = useMemo(() => aggregateMetric(performanceStores, "yearAgo"), [performanceStores]);
  const overallPerformance = useMemo(
    () => summarizeOverallPerformance(overallStores, {
      current: currentDays,
      previous: previousDays,
      yearAgo: yearAgoDays,
    }),
    [currentDays, overallStores, previousDays, yearAgoDays],
  );

  const dailyMom = previous.sales ? current.sales / currentDays / (previous.sales / previousDays) - 1 : null;
  const totalMom = previous.sales ? current.sales / previous.sales - 1 : null;
  const yoy = yearAgo.sales ? current.sales / yearAgo.sales - 1 : null;
  const inventory = filteredStores.reduce((sum, row) => sum + row.inventoryAmount, 0);
  const slowMoving = filteredStores.reduce((sum, row) => sum + row.slowMovingAmount, 0);
  const slowShare = inventory ? slowMoving / inventory : null;
  const shippingUnits = filteredStores.reduce((sum, row) => sum + row.shippingUnits, 0);
  const oceanUnits = filteredStores.reduce((sum, row) => sum + row.oceanUnits, 0);
  const airUnits = filteredStores.reduce((sum, row) => sum + row.airUnits, 0);
  const unshippedAmount = filteredStores.reduce((sum, row) => sum + row.unshippedAmount, 0);
  const unshippedCount = filteredStores.reduce((sum, row) => sum + row.unshippedCount, 0);
  const newOrders = useMemo(
    () => data.newProductOrders.filter((row) => filteredIds.has(row.store)),
    [data.newProductOrders, filteredIds],
  );
  const uniqueNewOrders = useMemo(
    () => new Set(newOrders.map((row) => `${row.orderedOn}|${row.store}|${row.mainSku}`)).size,
    [newOrders],
  );
  const newOrdersByStore = useMemo(() => {
    const grouped = new Map<number, { records: number; skus: Set<string> }>();
    for (const row of newOrders) {
      const currentRow = grouped.get(row.store) ?? { records: 0, skus: new Set<string>() };
      currentRow.records += 1;
      currentRow.skus.add(row.mainSku);
      grouped.set(row.store, currentRow);
    }
    return grouped;
  }, [newOrders]);
  const riskDetailRows = useMemo<RiskDetailRow[]>(() => {
    const rows = filteredStores.flatMap((row) => {
      if (riskTab === "inventory") {
        return row.slowMovingAmount > 0 ? [{
          store: row.store,
          department: row.department,
          operator: row.operator,
          primary: displayMoney(row.slowMovingAmount),
          secondary: percent(row.slowMovingShare, 2),
          sortValue: canViewAmounts ? row.slowMovingAmount : row.slowMovingShare,
          comparison: canViewAmounts
            ? averageComparisonLabel(row.slowMovingAmount, companySlowMovingAverage, slowMovingBenchmarkLabel)
            : undefined,
        }] : [];
      }
      if (riskTab === "fulfillment") {
        return row.unshippedCount > 0 ? [{
          store: row.store,
          department: row.department,
          operator: row.operator,
          primary: displayMoney(row.unshippedAmount),
          secondary: `${integer(row.unshippedCount)} 次`,
          sortValue: canViewAmounts ? row.unshippedAmount : row.unshippedCount,
        }] : [];
      }
      if (riskTab === "shipping") {
        return row.shippingUnits > 0 ? [{
          store: row.store,
          department: row.department,
          operator: row.operator,
          primary: `${integer(row.shippingUnits)} 件`,
          secondary: `${percent(row.oceanShare)} / ${percent(row.airShare)}`,
          sortValue: row.shippingUnits,
        }] : [];
      }
      const summary = newOrdersByStore.get(row.store);
      return summary ? [{
        store: row.store,
        department: row.department,
        operator: row.operator,
        primary: `${integer(summary.skus.size)} 个`,
        secondary: `${integer(summary.records)} 条`,
        sortValue: summary.skus.size,
      }] : [];
    });
    return rows.sort((a, b) => b.sortValue - a.sortValue);
  }, [canViewAmounts, companySlowMovingAverage, displayMoney, filteredStores, newOrdersByStore, riskTab, slowMovingBenchmarkLabel]);

  const colors = useMemo(
    () =>
      theme === "dark"
        ? {
            text: "#edf2fb",
            muted: "#9aa8bd",
            line: "#29364b",
            accent: "#8da8ff",
            accentSoft: "rgba(141,168,255,.18)",
            blue: "#62aef7",
            coral: "#ff8a91",
            amber: "#f0b66a",
            slate: "#9aa8bd",
            tooltip: "#111827",
          }
        : {
            text: "#172033",
            muted: "#647187",
            line: "#dce3ef",
            accent: "#3f63d8",
            accentSoft: "rgba(63,99,216,.12)",
            blue: "#2f7fd4",
            coral: "#a63f4b",
            amber: "#8a4f0d",
            slate: "#64748b",
            tooltip: "#ffffff",
          },
    [theme],
  );

  const marketLatestComplete = MARKET_OVERVIEW_ROWS.findLast((row) => !row.partial && row.salesVolume !== null);
  const marketLatest = MARKET_OVERVIEW_ROWS[MARKET_OVERVIEW_ROWS.length - 1];
  const marketScaleOption = useMemo<EChartsOption>(() => ({
    animationDuration: 600,
    color: [colors.accent, colors.blue],
    aria: { enabled: true },
    grid: { left: 18, right: 24, top: 44, bottom: 48, containLabel: true },
    legend: { top: 4, textStyle: { color: colors.muted } },
    tooltip: {
      trigger: "axis",
      backgroundColor: colors.tooltip,
      borderColor: colors.line,
      textStyle: { color: colors.text },
    },
    xAxis: {
      type: "category",
      data: MARKET_OVERVIEW_ROWS.map((row) => row.period.slice(2)),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: colors.line } },
      axisLabel: { color: colors.muted, interval: 2, rotate: 35 },
    },
    yAxis: [
      {
        type: "value",
        name: "销售额",
        axisLabel: { color: colors.muted, formatter: (value: number) => compactMoney(value) },
        splitLine: { lineStyle: { color: colors.line, type: "dashed" } },
      },
      {
        type: "value",
        name: "销量",
        axisLabel: { color: colors.muted, formatter: (value: number) => `${(value / 10000).toFixed(0)}万` },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "类目销售额",
        type: "bar",
        data: MARKET_OVERVIEW_ROWS.map((row) => ({ value: row.salesAmount, itemStyle: row.partial ? { opacity: 0.5 } : undefined })),
        barMaxWidth: 20,
        itemStyle: { borderRadius: [4, 4, 0, 0] },
        tooltip: { valueFormatter: (value: unknown) => money(Number(value)) },
      },
      {
        name: "类目销量",
        type: "line",
        yAxisIndex: 1,
        data: MARKET_OVERVIEW_ROWS.map((row) => row.salesVolume),
        connectNulls: false,
        showSymbol: false,
        smooth: 0.18,
        lineStyle: { width: 2.5 },
        tooltip: { valueFormatter: (value: unknown) => `${integer(Number(value))}` },
      },
    ],
  }), [colors]);

  const marketEfficiencyOption = useMemo<EChartsOption>(() => ({
    animationDuration: 600,
    color: [colors.amber, colors.coral],
    aria: { enabled: true },
    grid: { left: 18, right: 24, top: 44, bottom: 48, containLabel: true },
    legend: { top: 4, textStyle: { color: colors.muted } },
    tooltip: { trigger: "axis", backgroundColor: colors.tooltip, borderColor: colors.line, textStyle: { color: colors.text } },
    xAxis: {
      type: "category",
      data: MARKET_OVERVIEW_ROWS.map((row) => row.period.slice(2)),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: colors.line } },
      axisLabel: { color: colors.muted, interval: 2, rotate: 35 },
    },
    yAxis: [
      { type: "value", name: "客单价", min: 9.5, axisLabel: { color: colors.muted, formatter: (value: number) => value.toFixed(1) }, splitLine: { lineStyle: { color: colors.line, type: "dashed" } } },
      { type: "value", name: "环比", axisLabel: { color: colors.muted, formatter: (value: number) => `${Math.round(value * 100)}%` }, splitLine: { show: false } },
    ],
    series: [
      { name: "大盘客单价", type: "line", data: MARKET_OVERVIEW_ROWS.map((row) => row.averageOrderValue), showSymbol: false, smooth: 0.2, lineStyle: { width: 2.5 }, tooltip: { valueFormatter: (value: unknown) => Number(value).toFixed(2) } },
      { name: "销售额环比", type: "line", yAxisIndex: 1, data: MARKET_OVERVIEW_ROWS.map((row) => row.monthOverMonthGrowth), showSymbol: false, smooth: 0.15, lineStyle: { width: 2, type: "dashed" }, tooltip: { valueFormatter: (value: unknown) => percent(Number(value), 2) } },
    ],
  }), [colors]);

  const departmentOption = useMemo<EChartsOption>(() => {
    const names = departments.map((row) => row.name);
    return {
      animationDuration: 600,
      color: [colors.accent, colors.slate, colors.blue, colors.coral],
      aria: { enabled: true, decal: { show: false } },
      grid: { left: 12, right: 22, top: 54, bottom: 12, containLabel: true },
      legend: { top: 4, left: 0, textStyle: { color: colors.muted } },
      tooltip: {
        trigger: "axis",
        backgroundColor: colors.tooltip,
        borderColor: colors.line,
        textStyle: { color: colors.text },
        valueFormatter: (value: unknown) => displayMoney(Number(value)),
      },
      xAxis: {
        type: "category",
        data: names,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: colors.line } },
        axisLabel: { color: colors.muted, interval: 0 },
      },
      yAxis: [
        {
          type: "value",
          axisLabel: { color: colors.muted, formatter: (value: number) => integer(value) },
          splitLine: { lineStyle: { color: colors.line, type: "dashed" } },
        },
        {
          type: "value",
          min: 0,
          max: Math.max(35, Math.ceil(Math.max(...departments.map((row) => (row.current.grossMargin ?? 0) * 100)) / 5) * 5),
          axisLabel: { color: colors.muted, formatter: (value: number) => percent(value / 100) },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: currentPeriod?.label ?? "本期",
          type: "bar",
          data: departments.map((row) => row.current.sales),
          barMaxWidth: 28,
          itemStyle: { borderRadius: [6, 6, 0, 0] },
        },
        {
          name: previousPeriod?.label ?? "上期",
          type: "bar",
          data: departments.map((row) => row.previous.sales),
          barMaxWidth: 24,
          itemStyle: { borderRadius: [5, 5, 0, 0], opacity: 0.82 },
        },
        {
          name: yearAgoPeriod?.label ?? "去年同期",
          type: "bar",
          data: departments.map((row) => row.yearAgo.sales),
          barMaxWidth: 20,
          itemStyle: { borderRadius: [5, 5, 0, 0], opacity: 0.72 },
        },
        {
          name: "毛利率",
          type: "line",
          yAxisIndex: 1,
          data: departments.map((row) => (row.current.grossMargin ?? 0) * 100),
          symbol: "circle",
          symbolSize: 8,
          lineStyle: { width: 2.5 },
          tooltip: { valueFormatter: (value: unknown) => percent(Number(value) / 100) },
        },
      ],
    };
  }, [colors, currentPeriod?.label, departments, displayMoney, previousPeriod?.label, yearAgoPeriod?.label]);

  const scatterOption = useMemo<EChartsOption>(() => {
    const rows = performanceStores.filter((row) => row.current.sales > 0 && row.current.grossMargin !== null);
    const groups = [...new Set(rows.map((row) => row.department))];
    const seriesColors = [colors.accent, colors.blue, colors.coral, colors.amber, "#9067c6", "#4b6f9e", "#7f8ca1"];
    return {
      animationDuration: 600,
      aria: { enabled: true },
      color: seriesColors,
      grid: { left: 14, right: 18, top: 48, bottom: 12, containLabel: true },
      legend: { top: 2, left: 0, type: "scroll", textStyle: { color: colors.muted } },
      tooltip: {
        trigger: "item",
        backgroundColor: colors.tooltip,
        borderColor: colors.line,
        textStyle: { color: colors.text },
        formatter: (params: unknown) => {
          const point = (params as { data?: unknown[] }).data ?? [];
          return `<strong>${point[2]}号店 · ${point[3]}</strong><br/>销售额：${displayMoney(Number(point[0]))}<br/>毛利率：${percent(Number(point[1]) / 100)}<br/>毛利润：${displayMoney(Number(point[4]))}`;
        },
      },
      xAxis: {
        type: "value",
        name: "销售额（元）",
        nameTextStyle: { color: colors.muted },
        axisLabel: { color: colors.muted },
        splitLine: { lineStyle: { color: colors.line, type: "dashed" } },
      },
      yAxis: {
        type: "value",
        name: "毛利率",
        nameTextStyle: { color: colors.muted },
        axisLabel: { color: colors.muted, formatter: (value: number) => percent(value / 100) },
        splitLine: { lineStyle: { color: colors.line, type: "dashed" } },
      },
      series: groups.map((group) => ({
        name: group,
        type: "scatter",
        data: rows
          .filter((row) => row.department === group)
          .map((row) => [
            Math.round(row.current.sales),
            (row.current.grossMargin ?? 0) * 100,
            row.store,
            row.operator,
            Math.round(row.current.grossProfit),
          ]),
        symbolSize: (value: unknown) => Math.max(10, Math.min(34, Math.sqrt(Number((value as number[])[0])) * 4.5)),
        emphasis: { focus: "series", scale: 1.25 },
      })),
    };
  }, [colors, displayMoney, performanceStores]);

  const shippingOption = useMemo<EChartsOption>(() => {
    const other = Math.max(0, shippingUnits - oceanUnits - airUnits);
    return {
      animationDuration: 600,
      color: [colors.accent, colors.coral, colors.slate],
      aria: { enabled: true },
      title: {
        text: integer(shippingUnits),
        subtext: "总发货量",
        left: "center",
        top: "35%",
        textStyle: { color: colors.text, fontSize: 22, fontWeight: 650 },
        subtextStyle: { color: colors.muted, fontSize: 12 },
      },
      tooltip: {
        trigger: "item",
        backgroundColor: colors.tooltip,
        borderColor: colors.line,
        textStyle: { color: colors.text },
        formatter: (params: unknown) => {
          const item = params as { name?: string; value?: number; percent?: number };
          return `${item.name ?? ""}<br/>${integer(Number(item.value ?? 0))} 件 · ${Number(item.percent ?? 0).toFixed(2)}%`;
        },
      },
      legend: { bottom: 0, left: "center", textStyle: { color: colors.muted } },
      series: [
        {
          type: "pie",
          radius: ["58%", "78%"],
          center: ["50%", "43%"],
          avoidLabelOverlap: true,
          itemStyle: { borderColor: theme === "dark" ? "#111827" : "#ffffff", borderWidth: 3 },
          label: { show: false },
          emphasis: { label: { show: false }, scaleSize: 6 },
          data: [
            { name: "海运", value: oceanUnits },
            { name: "空派", value: airUnits },
            { name: "其他", value: other },
          ],
        },
      ],
    };
  }, [airUnits, colors, oceanUnits, shippingUnits, theme]);

  const slowOption = useMemo<EChartsOption>(() => {
    const rows = [...filteredStores]
      .filter((row) => row.slowMovingAmount > 0)
      .sort((a, b) => b.slowMovingAmount - a.slowMovingAmount)
      .slice(0, 10)
      .reverse();
    return {
      animationDuration: 600,
      color: [colors.coral],
      aria: { enabled: true },
      grid: { left: 8, right: 52, top: 14, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: colors.tooltip,
        borderColor: colors.line,
        textStyle: { color: colors.text },
        valueFormatter: (value: unknown) => displayMoney(Number(value)),
      },
      xAxis: {
        type: "value",
        axisLabel: { color: colors.muted, formatter: (value: number) => integer(value) },
        splitLine: { lineStyle: { color: colors.line, type: "dashed" } },
      },
      yAxis: {
        type: "category",
        data: rows.map((row) => `${row.store}号 · ${row.operator}`),
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: { color: colors.muted, width: 92, overflow: "truncate" },
      },
      series: [
        {
          type: "bar",
          data: rows.map((row) => row.slowMovingAmount),
          barWidth: 12,
          itemStyle: { borderRadius: [0, 6, 6, 0] },
          label: {
            show: true,
            position: "right",
            color: colors.muted,
            formatter: (params: unknown) => displayCompactMoney(Number((params as { value?: number }).value ?? 0)),
          },
        },
      ],
    };
  }, [colors, displayCompactMoney, displayMoney, filteredStores]);

  const unshippedOption = useMemo<EChartsOption>(() => {
    const rows = [...filteredStores]
      .filter((row) => row.unshippedCount > 0)
      .sort((a, b) => b.unshippedAmount - a.unshippedAmount)
      .slice(0, 10)
      .reverse();
    return {
      animationDuration: 600,
      color: [colors.amber, colors.blue],
      aria: { enabled: true },
      grid: { left: 8, right: 20, top: 28, bottom: 8, containLabel: true },
      legend: { top: 0, left: 0, textStyle: { color: colors.muted } },
      tooltip: {
        trigger: "axis",
        backgroundColor: colors.tooltip,
        borderColor: colors.line,
        textStyle: { color: colors.text },
      },
      xAxis: [
        {
          type: "value",
          axisLabel: { color: colors.muted, formatter: (value: number) => `${Math.round(value / 1000)}k` },
          splitLine: { lineStyle: { color: colors.line, type: "dashed" } },
        },
        { type: "value", show: false },
      ],
      yAxis: {
        type: "category",
        data: rows.map((row) => `${row.store}号 · ${row.operator}`),
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: { color: colors.muted, width: 92, overflow: "truncate" },
      },
      series: [
        {
          name: "未发货金额",
          type: "bar",
          data: rows.map((row) => row.unshippedAmount),
          barWidth: 12,
          itemStyle: { borderRadius: [0, 6, 6, 0] },
          tooltip: { valueFormatter: (value: unknown) => displayMoney(Number(value)) },
        },
        {
          name: "SKU 次数",
          type: "line",
          xAxisIndex: 1,
          data: rows.map((row) => row.unshippedCount),
          symbolSize: 7,
          lineStyle: { width: 2 },
          tooltip: { valueFormatter: (value: unknown) => `${integer(Number(value))} 次` },
        },
      ],
    };
  }, [colors, displayMoney, filteredStores]);

  const timelineOption = useMemo<EChartsOption>(() => {
    const range = data.meta.dateRanges.newProductOrders;
    const dates = makeDateRange(range.start, range.end);
    const daily = new Map<string, Set<string>>();
    for (const row of newOrders) {
      if (!daily.has(row.orderedOn)) daily.set(row.orderedOn, new Set());
      daily.get(row.orderedOn)!.add(`${row.store}|${row.mainSku}`);
    }
    const labels = dates.map(shortDate);
    const values = dates.map((date) => daily.get(date)?.size ?? 0);
    return {
      animationDuration: 600,
      color: [colors.accent],
      aria: { enabled: true },
      grid: { left: 10, right: 18, top: 30, bottom: 12, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: colors.tooltip,
        borderColor: colors.line,
        textStyle: { color: colors.text },
        valueFormatter: (value: unknown) => `${integer(Number(value))} 个主 SKU`,
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: labels,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: colors.line } },
        axisLabel: { color: colors.muted, interval: 4 },
      },
      yAxis: {
        type: "value",
        minInterval: 1,
        axisLabel: { color: colors.muted },
        splitLine: { lineStyle: { color: colors.line, type: "dashed" } },
      },
      series: [
        {
          name: "新品主 SKU",
          type: "line",
          data: values,
          smooth: 0.25,
          symbol: "circle",
          showSymbol: false,
          lineStyle: { width: 2.5 },
          areaStyle: { color: colors.accentSoft },
          markPoint: {
            symbolSize: 44,
            label: { color: "#fff", fontSize: 10 },
            data: [{ type: "max", name: "峰值" }],
          },
        },
      ],
    };
  }, [colors, data.meta.dateRanges.newProductOrders, newOrders]);

  const tableRows = useMemo(() => {
    const rows = [...performanceStores];
    rows.sort((a, b) => {
      if (sortMode === "growth") {
        const aValue = a.previous.sales ? a.current.sales / currentDays / (a.previous.sales / previousDays) - 1 : -Infinity;
        const bValue = b.previous.sales ? b.current.sales / currentDays / (b.previous.sales / previousDays) - 1 : -Infinity;
        return bValue - aValue;
      }
      if (sortMode === "margin") return (b.current.grossMargin ?? -Infinity) - (a.current.grossMargin ?? -Infinity);
      if (sortMode === "tier") return (b.tierRank ?? -Infinity) - (a.tierRank ?? -Infinity);
      if (sortMode === "slow") return b.slowMovingAmount - a.slowMovingAmount;
      return b.current.sales - a.current.sales;
    });
    return rows;
  }, [currentDays, performanceStores, previousDays, sortMode]);

  const topDepartment = departments[0];
  const strongestGrowth = [...departments]
    .filter((row) => row.dailyMom !== null)
    .sort((a, b) => (b.dailyMom ?? -Infinity) - (a.dailyMom ?? -Infinity))[0];
  const weakestGrowth = [...departments]
    .filter((row) => row.dailyMom !== null)
    .sort((a, b) => (a.dailyMom ?? Infinity) - (b.dailyMom ?? Infinity))[0];
  const hasFilters = Boolean(filters.department || filters.operator || filters.store || filters.tier);
  const sourceMode = live.source?.mode ?? "workbook-snapshot";
  const evaluatedAt = live.source?.fetchedAt ?? data.meta.extractedAt;
  const tierMeta = data.meta.storeTier;
  const tierAsOf = tierMeta?.effectiveDate
    ?? data.storeTiers?.find((row) => row.effectiveDate)?.effectiveDate
    ?? null;
  const statusLabel = live.phase === "refreshing"
    ? "更新中"
    : sourceMode === "workbook-snapshot"
      ? "快照"
      : live.source?.stale
        ? "部分缓存"
    : sourceMode === "daily-snapshot"
      ? "每日快照"
      : sourceMode === "database"
      ? "实时"
      : sourceMode === "memory-cache"
        ? "缓存"
        : "断开";
  const overallPeriodRows = [
    { key: "current", year: currentPeriod?.year ?? Number(period.slice(0, 4)), month: currentPeriod?.month ?? Number(period.slice(5)), days: currentDays, metric: overallPerformance.current },
    { key: "previous", year: previousPeriod?.year ?? 0, month: previousPeriod?.month ?? 0, days: previousDays, metric: overallPerformance.previous },
    { key: "yearAgo", year: yearAgoPeriod?.year ?? 0, month: yearAgoPeriod?.month ?? 0, days: yearAgoDays, metric: overallPerformance.yearAgo },
  ] as const;
  const formulaDetails = useMemo<Record<FormulaId, FormulaDetail>>(() => ({
    "sales.current": {
      id: "sales.current",
      label: "销售额",
      value: displayMoney(current.sales),
      expression: "销售额 = Σ 当前筛选店铺销售额",
      note: "与 Excel 的 DBTORS 汇总口径一致；切换部门、运营或店铺后立即重算。",
      inputs: [
        { label: currentPeriod?.label ?? "本期销售明细", value: displayMoney(current.sales), source: "v_MaoLiLv.XiaoShouE" },
        { label: "纳入店铺", value: `${performanceStores.length} 家`, source: "当前筛选" },
      ],
      sql: "SUM(v_MaoLiLv.XiaoShouE)\nWHERE RiQi >= @start AND RiQi < @end",
    },
    "profit.current": {
      id: "profit.current",
      label: "毛利润",
      value: displayMoney(current.grossProfit),
      expression: "毛利润 = Σ 店铺毛利润",
      note: "按逐店明细累加，避免沿用 Excel 页脚漏行的问题。",
      inputs: [
        { label: "毛利润明细", value: displayMoney(current.grossProfit), source: "v_MaoLiLv.MaoLiRun" },
        { label: "纳入店铺", value: `${performanceStores.length} 家`, source: "当前筛选" },
      ],
      sql: "SUM(v_MaoLiLv.MaoLiRun)\nWHERE RiQi >= @start AND RiQi < @end",
    },
    "margin.current": {
      id: "margin.current",
      label: "毛利率",
      value: percent(current.grossMargin, 2),
      expression: "毛利率 = 毛利润 ÷ 毛利率分母",
      note: "先汇总分子和分母再相除，不对各店毛利率做简单平均。",
      inputs: [
        { label: "毛利润", value: displayMoney(current.grossProfit), source: "v_MaoLiLv.MaoLiRun" },
        { label: "毛利率分母", value: displayMoney(current.grossMarginBase), source: "v_MaoLiLv.MaoLiLvFenMu" },
      ],
      sql: "SUM(MaoLiRun) / NULLIF(SUM(MaoLiLvFenMu), 0)",
    },
    "growth.daily_mom": {
      id: "growth.daily_mom",
      label: "日均环比",
      value: growthLabel(dailyMom),
      expression: "日均环比 = (本期销售 ÷ 本期天数) ÷ (上期销售 ÷ 上期天数) − 1",
      note: "天数来自所选自然月；数据库接口按所选期间重新读取三期明细。",
      inputs: [
        { label: `${currentPeriod?.label ?? "本期"}销售`, value: displayMoney(current.sales), source: "实时聚合" },
        { label: "本期天数", value: `${currentDays} 天`, source: "期间公式" },
        { label: `${previousPeriod?.label ?? "上期"}销售`, value: displayMoney(previous.sales), source: "实时聚合" },
        { label: "上期天数", value: `${previousDays} 天`, source: "期间公式" },
      ],
      sql: "(SUM(current.XiaoShouE) / @currentDays)\n/ (SUM(previous.XiaoShouE) / @previousDays) - 1",
    },
  }), [current, currentDays, currentPeriod?.label, dailyMom, displayMoney, performanceStores.length, previous.sales, previousDays, previousPeriod?.label]);

  const selectStore = (store: string) => {
    const row = stores.find((item) => String(item.store) === store);
    setFilters({
      department: row?.department ?? filters.department,
      operator: row?.operator ?? filters.operator,
      store,
      tier: row?.tier ?? filters.tier ?? "",
    });
  };

  return (
    <main className="dashboard-shell">
      <header className="app-bar" id="top">
        <div className="app-bar-inner">
          <a className="brand" href="#top" aria-label="返回顶部">
            <span className="brand-mark">BA</span>
            <span><b>经营分析</b><small>BUSINESS ANALYTICS</small></span>
          </a>
          <div className="app-actions">
            {visibleTab === "home" ? (
              <span className="period-control fiscal-year-control"><span>财年</span><b>2026-2027</b></span>
            ) : (
              <label className="period-control"><span>期间</span><input type="month" value={period} onChange={(event) => setPeriod(event.target.value)} /></label>
            )}
            {visibleTab !== "home" ? <>
              <div className={`data-status status-${sourceMode}${live.source?.stale ? " is-stale" : ""}${live.phase === "refreshing" ? " is-refreshing" : ""}`} title={live.source?.warning ?? "数据连接状态"}>
                <i /><span>{statusLabel}</span>
              </div>
              <span className="updated-at">{new Date(evaluatedAt).toLocaleTimeString("zh-CN", { hour12: false })}</span>
              <button className="icon-button refresh-button" type="button" onClick={() => void live.refresh(true)} disabled={live.phase === "refreshing"} aria-label="立即刷新">↻</button>
            </> : null}
            <button className="icon-button" type="button" onClick={() => setTheme(theme === "light" ? "dark" : "light")} aria-label={`切换为${theme === "light" ? "深色" : "浅色"}模式`}>{theme === "light" ? "暗" : "明"}</button>
          </div>
        </div>
      </header>

      {visibleTab !== "home" ? <>
      <section className="dashboard-toolbar" aria-label="数据筛选">
        <div className="filter-fields">
          <SelectField
            label="部门"
            value={filters.department}
            options={departmentOptions.map((value) => ({ value, label: value }))}
            allLabel={accessScope?.role === "business_owner" ? "全部部门" : accessScope?.department ?? "权限范围"}
            disabled={Boolean(accessScope) && accessScope?.role !== "business_owner"}
            onChange={(department) => setFilters({ department, operator: "", store: "", tier: "" })}
          />
          <SelectField
            label="运营"
            value={filters.operator}
            options={operatorOptions.map((value) => ({ value, label: value }))}
            allLabel={accessScope?.role === "business_owner" ? "全部运营" : accessScope?.operator ?? "本部门全部运营"}
            disabled={accessScope?.role === "member"}
            onChange={(operator) => setFilters((currentFilters) => ({ ...currentFilters, operator, store: "" }))}
          />
          <SelectField
            label="店铺"
            value={filters.store}
            options={storeOptions.map((row) => ({ value: String(row.store), label: `${row.store} 号店` }))}
            onChange={selectStore}
          />
          <SelectField
            label="店铺层级"
            value={filters.tier ?? ""}
            options={tierOptions.map((value) => ({ value, label: value }))}
            allLabel="全部层级"
            onChange={(tier) => setFilters((currentFilters) => ({ ...currentFilters, tier, store: "" }))}
          />
          <button
            className="reset-button"
            type="button"
            disabled={!hasFilters}
            onClick={() => setFilters(defaultFilters)}
          >
            重置筛选
          </button>
        </div>
        <div className="filter-result">
          <span className="scope-label">
            {accessScope?.role === "business_owner"
              ? "经营分析全量负责人视角"
              : accessScope?.role === "department_leader"
              ? `${accessScope.department}负责人视角`
              : accessScope?.role === "ratio_viewer"
                ? "全员比例视图"
              : accessScope?.operator
                ? `${accessScope.department} · ${accessScope.operator}本人视角`
                : "正在校验权限"}
          </span>
          <i />
          <span>{performanceStores.length}</span> 家业绩店
          <i />
          <span>{filteredStores.length}</span> 家数据店
        </div>
      </section>

      <section className="kpi-grid" aria-label="关键指标">
        <KpiCard
          label="销售额"
          value={displayCompactMoney(current.sales)}
          delta={`同比 ${growthLabel(yoy)}`}
          note={`${currentPeriod?.label ?? "本期"} · 日均 ${displayCompactMoney(current.sales / currentDays)}`}
          tone={trendTone(totalMom)}
          priority
          formulaId="sales.current"
          onInspect={setActiveFormula}
        />
        <KpiCard
          label="毛利润"
          value={displayCompactMoney(current.grossProfit)}
          delta="实时汇总"
          note={`${performanceStores.length} 家业绩店逐店累加`}
          tone="positive"
          formulaId="profit.current"
          onInspect={setActiveFormula}
        />
        <KpiCard
          label="毛利率"
          value={percent(current.grossMargin, 2)}
          delta="加权口径"
          note="毛利润 ÷ 毛利率分母"
          tone="positive"
          formulaId="margin.current"
          onInspect={setActiveFormula}
        />
        <KpiCard
          label="日均环比"
          value={growthLabel(dailyMom)}
          delta={`月总额 ${growthLabel(totalMom)}`}
          note={`${currentDays} 天 vs ${previousDays} 天`}
          tone={trendTone(dailyMom)}
          formulaId="growth.daily_mom"
          onInspect={setActiveFormula}
        />
      </section>
      </> : null}

      <nav className="dashboard-tabs" role="tablist" aria-label="分析模块">
        {([
          ["home", "首页"],
          ["performance", "业绩分析"],
          ["market", "大盘趋势"],
          ["categories", `品类阵营 · ${categorySegments.length}`],
          ["operations", `运营风险 · ${integer(unshippedCount)}`],
          ["stores", `店铺层级 · ${performanceStores.length}`],
          ["tasks", "关键任务"],
        ] as const).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={visibleTab === id}
            className={visibleTab === id ? "active" : ""}
            onClick={() => {
              setActiveTab(id);
              if (id === "categories") setFilters((currentFilters) => ({ ...currentFilters, operator: "", store: "" }));
            }}
          >
            {label}
          </button>
        ))}
      </nav>

      <section className={`dashboard-section${visibleTab === "home" ? "" : " tab-hidden"}`} id="home" role="tabpanel">
        <FiscalOverview visible={visibleTab === "home"} theme={theme} />
      </section>

      <section className={`dashboard-section${visibleTab === "performance" ? "" : " tab-hidden"}`} id="performance" role="tabpanel">
        <div className="section-bar">
          <div><span className="eyebrow">Performance</span><h2>增长与毛利</h2><p>三期同口径对比；点击部门或店铺可联动筛选。</p></div>
          <span className="data-chip">{performanceStores.length} 家业绩店</span>
        </div>

        <div className="panel-grid panel-grid-main">
          <article className="panel panel-span-12 performance-overview">
            <PanelTitle
              title="整体业绩"
              copy="当前权限范围三期汇总；普通成员金额自动隐藏"
              tag={accessScope?.role === "business_owner" ? "全公司口径" : accessScope?.role === "department_leader" ? "本部门口径" : "本人比例口径"}
            />
            <div className="performance-overview-grid">
              <div className="table-scroll table-scroll-compact">
                <table className="compact-table period-comparison-table">
                  <caption className="sr-only">全公司本期、上期与去年同期业绩对比</caption>
                  <thead>
                    <tr>
                      <th scope="col">年</th>
                      <th scope="col">月</th>
                      <th scope="col">销售额</th>
                      <th scope="col">日均销售</th>
                      <th scope="col">毛利率</th>
                    </tr>
                  </thead>
                  <tbody>
                    {overallPeriodRows.map((row) => (
                      <tr key={row.key} className={row.key === "current" ? "is-current" : undefined}>
                        <td>{row.year || "—"}</td>
                        <td>{row.month || "—"}{row.key === "current" ? <small>本期</small> : null}</td>
                        <td><b>{displayIntegerAmount(row.metric.sales)}</b></td>
                        <td>{displayIntegerAmount(row.metric.dailySales)}<small>{row.days} 天</small></td>
                        <td>{percent(row.metric.grossMargin, 2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <aside className="performance-conclusion" aria-label="整体业绩经营结论">
                <div className="performance-comparison">
                  <div>
                    <span>日均环比</span>
                    <strong className={`trend-text ${trendTone(overallPerformance.dailyMom)}`}>{growthLabel(overallPerformance.dailyMom, 2)}</strong>
                    <small>本期 vs 上期</small>
                  </div>
                  <div>
                    <span>日均同比</span>
                    <strong className={`trend-text ${trendTone(overallPerformance.dailyYoy)}`}>{growthLabel(overallPerformance.dailyYoy, 2)}</strong>
                    <small>本期 vs 去年同期</small>
                  </div>
                </div>
                <div className="performance-narrative">
                  <p>
                    当前权限范围本期销售额 <strong>{displayCompactMoney(overallPerformance.current.sales)}</strong>，日均 <strong>{overallPerformance.current.dailySales === null ? "—" : displayCompactMoney(overallPerformance.current.dailySales)}</strong>；日均环比较上期
                    <b className={`trend-text ${trendTone(overallPerformance.dailyMom)}`}>{movementLabel(overallPerformance.dailyMom)}</b>，同比
                    <b className={`trend-text ${trendTone(overallPerformance.dailyYoy)}`}>{movementLabel(overallPerformance.dailyYoy)}</b>。
                  </p>
                  <p>
                    整体毛利率 <strong>{percent(overallPerformance.current.grossMargin, 2)}</strong>，较去年同期
                    <b className={`trend-text ${trendTone(overallPerformance.marginYoy)}`}>{pointMovementLabel(overallPerformance.marginYoy)}</b>，较上期
                    <b className={`trend-text ${trendTone(overallPerformance.marginMom)}`}>{pointMovementLabel(overallPerformance.marginMom)}</b>。
                  </p>
                </div>
                <p className="performance-method">销售额与毛利率来自 v_MaoLiLv；日均按三期有效天数实时换算，毛利率按分子分母加权。</p>
              </aside>
            </div>
          </article>
        </div>

        <div className="panel-grid">
          <article className="panel panel-span-8">
            <PanelTitle title="部门业绩对比" copy="柱形为三期销售额，折线为本期毛利率" tag="可点击筛选" />
            {canViewAmounts && departments.length ? (
              <EChart
                option={departmentOption}
                theme={theme === "dark" ? "dark" : undefined}
                height={304}
                ariaLabel="部门三期销售额与本期毛利率图"
                onClick={(event) => {
                  if (!event.name) return;
                  setFilters({ department: String(event.name), operator: "", store: "" });
                }}
              />
            ) : <div className="empty-state">普通成员不展示金额图，毛利率与增长比例可在明细中查看</div>}
          </article>

          <aside className="panel insight-panel panel-span-4">
            <PanelTitle title="需要关注" copy="按当前筛选自动更新" tag="实时公式" />
            <ol className="insight-list">
              <li>
                <span>01</span>
                <div><small>销售贡献最高</small><strong>{topDepartment?.name ?? "—"}</strong><p>{topDepartment ? `${displayCompactMoney(topDepartment.current.sales)} · 占比 ${percent(current.sales ? topDepartment.current.sales / current.sales : null)}` : "暂无数据"}</p></div>
              </li>
              <li>
                <span>02</span>
                <div><small>日均环比领先</small><strong>{strongestGrowth?.name ?? "—"}</strong><p>{strongestGrowth ? growthLabel(strongestGrowth.dailyMom) : "暂无数据"}</p></div>
              </li>
              <li>
                <span>03</span>
                <div><small>需要关注</small><strong>{weakestGrowth?.name ?? "—"}</strong><p>{weakestGrowth ? `日均环比 ${growthLabel(weakestGrowth.dailyMom)}` : "暂无数据"}</p></div>
              </li>
            </ol>
            <div className="audit-note scope-note">
              <b>固定查看范围</b>
              {FOCUS_DEPARTMENTS.join("、")}；卡片、图表和表格均按同一范围实时重算。
            </div>
          </aside>
        </div>

        <div className="panel-grid">
          <article className="panel panel-span-12 compact-table-panel">
            <PanelTitle title="部门业绩明细" copy="5 个指定部门的销售、利润与增长口径对齐" tag="按销售额排序" />
            <div className="table-scroll table-scroll-compact">
              <table className="compact-table department-table">
                <thead>
                  <tr>
                    <th>部门</th>
                    <th>店铺数</th>
                    <th>本期销售额</th>
                    <th>销售占比</th>
                    <th>毛利润</th>
                    <th>毛利率</th>
                    <th>日均环比</th>
                    <th>同比</th>
                  </tr>
                </thead>
                <tbody>
                  {departments.map((row) => (
                    <tr key={row.name}>
                      <td><button className="store-link" type="button" onClick={() => setFilters({ department: row.name, operator: "", store: "" })}>{row.name}</button></td>
                      <td>{integer(row.stores)}</td>
                      <td><b>{displayMoney(row.current.sales)}</b></td>
                      <td>{percent(current.sales ? row.current.sales / current.sales : null, 2)}</td>
                      <td>{displayMoney(row.current.grossProfit)}</td>
                      <td>{percent(row.current.grossMargin, 2)}</td>
                      <td><span className={`trend-pill ${trendTone(row.dailyMom)}`}>{growthLabel(row.dailyMom)}</span></td>
                      <td><span className={`trend-text ${trendTone(row.yoy)}`}>{growthLabel(row.yoy)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </div>

        <div className="panel-grid">
          <article className="panel panel-span-12">
            <PanelTitle title="店铺效率象限" copy="销售金额仅部门负责人可见" tag={canViewAmounts ? "点击气泡定位店铺" : "金额已隐藏"} />
            {canViewAmounts ? <EChart
                option={scatterOption}
                theme={theme === "dark" ? "dark" : undefined}
                height={256}
                ariaLabel="店铺销售额和毛利率散点图"
                onClick={(event) => {
                  const store = metricFromEvent(event, 2);
                  if (store) selectStore(store);
                }}
              /> : <div className="empty-state">当前仅展示本人店铺的毛利率、增长率和风险比例</div>}
          </article>
        </div>
      </section>

      <section className={`dashboard-section${visibleTab === "market" ? "" : " tab-hidden"}`} id="market" role="tabpanel">
        <div className="section-bar">
          <div><span className="eyebrow">Market overview</span><h2>大盘趋势</h2><p>2024 年 6 月起的类目销量、销售额、环比与客单价。</p></div>
          <span className="data-chip">所有成员可见 · 用户提供</span>
        </div>

        <div className="market-kpis">
          <div><span>最新完整月</span><strong>{marketLatestComplete?.period ?? "—"}</strong><small>截至完整口径</small></div>
          <div><span>类目销量</span><strong>{marketLatestComplete?.salesVolume == null ? "—" : integer(marketLatestComplete.salesVolume)}</strong><small>{marketLatestComplete?.period ?? "—"}</small></div>
          <div><span>类目销售额</span><strong>{marketLatestComplete ? compactMoney(marketLatestComplete.salesAmount) : "—"}</strong><small>{marketLatestComplete?.monthOverMonthGrowth == null ? "暂无环比" : `环比 ${percent(marketLatestComplete.monthOverMonthGrowth, 2)}`}</small></div>
          <div><span>大盘客单价</span><strong>{marketLatestComplete?.averageOrderValue == null ? "—" : marketLatestComplete.averageOrderValue.toFixed(2)}</strong><small>{marketLatestComplete?.period ?? "—"}</small></div>
          <div className="is-partial"><span>{marketLatest.period} 已有销售额</span><strong>{compactMoney(marketLatest.salesAmount)}</strong><small>其他指标待补充，不作零值处理</small></div>
        </div>

        <div className="panel-grid market-chart-grid">
          <article className="panel panel-span-7">
            <PanelTitle title="类目规模趋势" copy="柱形为销售额，折线为销量" tag={`${MARKET_OVERVIEW_ROWS.length} 个月`} />
            <EChart option={marketScaleOption} theme={theme === "dark" ? "dark" : undefined} height={310} ariaLabel="大盘类目销售额与销量月度趋势" />
          </article>
          <article className="panel panel-span-5">
            <PanelTitle title="价格与增长" copy="客单价与销售额环比" tag="月度" />
            <EChart option={marketEfficiencyOption} theme={theme === "dark" ? "dark" : undefined} height={310} ariaLabel="大盘客单价与销售额环比趋势" />
          </article>
        </div>

        <article className="panel compact-table-panel market-table-panel">
          <PanelTitle title="大盘月度明细" copy="按最新月份优先展示；空值表示原始数据未提供" tag="全量历史" />
          <div className="table-scroll market-table-scroll">
            <table className="compact-table market-table">
              <thead><tr><th>日期</th><th>类目销量</th><th>类目销售额</th><th>类目环比上月增长率</th><th>大盘客单价</th><th>数据状态</th></tr></thead>
              <tbody>{[...MARKET_OVERVIEW_ROWS].reverse().map((row) => (
                <tr key={row.period} className={row.partial ? "is-partial" : ""}>
                  <td><b>{row.period}</b></td>
                  <td>{row.salesVolume == null ? "—" : integer(row.salesVolume)}</td>
                  <td><b>{money(row.salesAmount)}</b></td>
                  <td>{row.monthOverMonthGrowth == null ? "—" : <span className={`trend-pill ${trendTone(row.monthOverMonthGrowth)}`}>{percent(row.monthOverMonthGrowth, 2)}</span>}</td>
                  <td>{row.averageOrderValue == null ? "—" : row.averageOrderValue.toFixed(2)}</td>
                  <td>{row.partial ? <span className="market-partial-badge">待补充</span> : "已完整"}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </article>
      </section>

      <section className={`dashboard-section${visibleTab === "categories" ? "" : " tab-hidden"}`} id="categories" role="tabpanel">
        <div className="section-bar">
          <div><span className="eyebrow">Category arena</span><h2>对毛与簇毛</h2><p>五部门共享比例视图，绝对金额由服务端脱敏。</p></div>
          <span className="data-chip">实时公式 · {categorySegments.length} 个品类</span>
        </div>
        {categorySegments.length ? (
          <div className="category-stack">
            {categorySegments.map((segment) => (
              <CategoryArena
                key={segment.key}
                segment={segment}
                currentLabel={currentPeriod?.label ?? period}
                previousLabel={previousPeriod?.label ?? "上月"}
                yearAgoLabel={yearAgoPeriod?.label ?? "去年同月"}
                canViewAmounts={canViewAmounts}
              />
            ))}
          </div>
        ) : (
          <div className="panel category-empty">
            <b>品类数据正在等待实时数据库</b>
            <span>当前 Excel 快照不含可复算缓存；数据库恢复后将自动显示。</span>
          </div>
        )}
      </section>

      <section className={`dashboard-section${visibleTab === "operations" ? "" : " tab-hidden"}`} id="operations" role="tabpanel">
        <div className="section-bar">
          <div><span className="eyebrow">Operations & risk</span><h2>运营风险</h2><p>一次只看一类风险，保留同一店铺筛选。</p></div>
          <span className="data-chip data-chip-warn">{integer(unshippedCount)} 次未及时发货</span>
        </div>

        <div className="ops-strip">
          <div><span>新品主 SKU 记录</span><strong>{integer(uniqueNewOrders)}</strong><small>原始明细 {integer(newOrders.length)} 条</small></div>
          <div><span>滞销率</span><strong>{percent(slowShare, 2)}</strong><small>{displayCompactMoney(slowMoving)} / {displayCompactMoney(inventory)}</small></div>
          <div><span>未发货金额</span><strong>{displayCompactMoney(unshippedAmount)}</strong><small>{integer(unshippedCount)} 次 SKU 记录</small></div>
          <div><span>运输总件数</span><strong>{integer(shippingUnits)}</strong><small>海运 {percent(shippingUnits ? oceanUnits / shippingUnits : null)}</small></div>
        </div>

        <nav className="risk-tabs" aria-label="运营风险分类">
          {([
            ["inventory", "库存"],
            ["fulfillment", "履约"],
            ["shipping", "运输"],
            ["new", "新品"],
          ] as const).map(([id, label]) => (
            <button key={id} type="button" className={riskTab === id ? "active" : ""} onClick={() => setRiskTab(id)}>{label}</button>
          ))}
        </nav>

        <div className="panel-grid risk-grid">
          <article className={`panel panel-span-7${riskTab === "new" ? "" : " tab-hidden"}`}>
            <PanelTitle title="新品上新节奏" copy="按日期统计去重后的店铺 × 主 SKU" tag="指定部门" />
            <EChart option={timelineOption} theme={theme === "dark" ? "dark" : undefined} height={248} ariaLabel="新品或磁铁销售日趋势图" />
          </article>
          <article className={`panel panel-span-7${riskTab === "inventory" ? "" : " tab-hidden"}`}>
            <PanelTitle
              title="滞销金额 Top 10"
              copy="优先处理金额高、占比高的店铺"
              metric={canViewAmounts ? `平均滞销 ${displayCompactMoney(companySlowMovingAverage)}` : undefined}
              tag={displayCompactMoney(slowMoving)}
            />
            {canViewAmounts
              ? <EChart option={slowOption} theme={theme === "dark" ? "dark" : undefined} height={248} ariaLabel="店铺滞销金额前十名" />
              : <div className="empty-state">金额已隐藏，请在右侧查看本人店铺滞销率</div>}
          </article>
          <article className={`panel panel-span-7${riskTab === "fulfillment" ? "" : " tab-hidden"}`}>
            <PanelTitle title="未及时发货风险" copy="柱形为金额，折线为 SKU 次数" tag={`${integer(unshippedCount)} 次`} />
            {canViewAmounts
              ? <EChart option={unshippedOption} theme={theme === "dark" ? "dark" : undefined} height={248} ariaLabel="店铺未及时发货金额与SKU次数图" />
              : <div className="empty-state">金额已隐藏，SKU 次数仍可查看</div>}
          </article>
          <article className={`panel panel-span-7${riskTab === "shipping" ? "" : " tab-hidden"}`}>
            <PanelTitle title="运输结构" copy="海运、空派与其他发货方式" tag={currentPeriod?.label ?? "本期"} />
            <EChart option={shippingOption} theme={theme === "dark" ? "dark" : undefined} height={220} ariaLabel="发货运输方式占比图" />
          </article>
          <article className="panel panel-span-5 compact-table-panel risk-table-panel">
            <PanelTitle title="具体风险明细" copy="与左侧当前风险分类同步，按影响值降序" tag={`${riskDetailRows.length} 家`} />
            {riskDetailRows.length ? (
              <div className="table-scroll table-scroll-compact risk-table-scroll">
                <table className="compact-table risk-detail-table">
                  <thead>
                    <tr>
                      <th>店铺</th>
                      <th>部门 / 运营</th>
                      <th>
                        {riskTableLabels[riskTab].primary}
                        {riskTab === "inventory" && canViewAmounts
                          ? <small className="table-benchmark">{slowMovingBenchmarkLabel} {displayCompactMoney(companySlowMovingAverage)}</small>
                          : null}
                      </th>
                      <th>{riskTableLabels[riskTab].secondary}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {riskDetailRows.map((row) => (
                      <tr key={`${riskTab}-${row.store}`}>
                        <td><button className="store-link" type="button" onClick={() => selectStore(String(row.store))}>{row.store} 号店</button></td>
                        <td><b>{row.department}</b><small>{row.operator}</small></td>
                        <td><b>{row.primary}</b>{row.comparison ? <small className="risk-average-comparison">{row.comparison}</small> : null}</td>
                        <td>{row.secondary}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <div className="risk-table-empty">{riskTableLabels[riskTab].empty}</div>}
          </article>
        </div>
      </section>

      <section className={`dashboard-section${visibleTab === "stores" ? "" : " tab-hidden"}`} id="stores" role="tabpanel">
        <div className="section-bar">
          <div><span className="eyebrow">Store detail</span><h2>店铺明细</h2><p>销售、毛利、增长与风险在一张表内对齐。</p></div>
          <div>
            <label className="sort-control">
              <span>排序</span>
              <select value={sortMode} onChange={(event) => setSortMode(event.target.value as SortMode)}>
                {canViewAmounts ? <option value="sales">销售额</option> : null}
                <option value="growth">日均环比</option>
                <option value="margin">毛利率</option>
                <option value="tier">店铺层级</option>
                {canViewAmounts ? <option value="slow">滞销金额</option> : null}
              </select>
            </label>
          </div>
        </div>
        <div className="tier-overview" aria-label="店铺层级概览">
          <div className="tier-overview-lead">
            <span>店铺层级</span>
            <strong>{tierAssignedCount} / {stores.length} 家</strong>
            <small>
              {tierAsOf ? `截至 ${tierAsOf}` : "等待层级数据"}
              {tierMeta ? (tierMeta.stale ? " · 使用快照" : " · 每日自动更新") : " · 状态待确认"}
            </small>
          </div>
          <div className="tier-overview-items">
            {tierSummary.length ? tierSummary.map((item) => (
              <button
                key={item.tier}
                type="button"
                className={`tier-summary-item tier-${tierTone(item.tier)}${filters.tier === item.tier ? " active" : ""}`}
                onClick={() => setFilters((currentFilters) => ({ ...currentFilters, tier: currentFilters.tier === item.tier ? "" : item.tier, store: "" }))}
              >
                <b>{item.tier}</b><span>{item.count} 家</span>
              </button>
            )) : <span className="tier-summary-empty">当前范围暂无层级记录</span>}
            {tierUnratedCount ? <span className="tier-summary-unrated">未定级 {tierUnratedCount} 家</span> : null}
          </div>
          <button className="tier-history-trigger" type="button" onClick={() => {
            const next = !showTierHistory;
            setShowTierHistory(next);
            if (next && !tierHistoryRows.length) void loadTierHistory(tierHistoryDays, tierHistoryStore);
          }}>全屏查看每日等级</button>
        </div>
        {showTierHistory ? (
          <div className="tier-history-overlay" role="dialog" aria-modal="true" aria-label="店铺每日等级矩阵">
            <div className="tier-history-panel">
              <div className="tier-history-toolbar">
                <div><b>店铺每日等级矩阵</b><small>横轴为日期，纵轴为店铺；描边单元格表示当天发生等级变化</small></div>
                <label><span>店铺</span><select value={tierHistoryStore} onChange={(event) => {
                  const value = event.target.value;
                  setTierHistoryStore(value);
                  void loadTierHistory(tierHistoryDays, value);
                }}><option value="">全部店铺</option>{stores.map((row) => <option key={row.store} value={row.store}>{row.store} 号店</option>)}</select></label>
                <label><span>范围</span><select value={tierHistoryDays} onChange={(event) => {
                  const value = Number(event.target.value);
                  setTierHistoryDays(value);
                  void loadTierHistory(value, tierHistoryStore);
                }}><option value={30}>最近 30 天</option><option value={90}>最近 90 天</option><option value={180}>最近 180 天</option><option value={365}>最近 365 天</option></select></label>
                <button className="tier-history-close" type="button" onClick={() => setShowTierHistory(false)} aria-label="关闭每日等级全屏视图">×</button>
              </div>
              {tierHistoryLoading ? <div className="tier-history-state">正在读取每日等级记录…</div>
                : tierHistoryError ? <div className="tier-history-state error">{tierHistoryError}</div>
                : tierHistoryRows.length ? <div className="table-scroll tier-history-scroll"><table className="tier-history-matrix"><thead><tr><th className="tier-history-store-head">店铺 / 运营</th><th className="tier-history-meta-head">历史正式最高</th><th className="tier-history-meta-head tier-history-days-head">当前层级已满</th>{tierHistoryDates.map((date) => <th key={date} title={date}><span>{date.slice(5).replace("-", "/")}</span></th>)}</tr></thead><tbody>{tierHistoryMatrix.map((row) => <tr key={row.store}><th className="tier-history-store-cell"><b>{row.store}号店</b><small>{row.operator || row.department || "—"}</small></th><td className="tier-history-meta-cell" title={row.meta?.officialSource || ""}><span className={`tier-history-cell tier-${tierTone(row.meta?.historicalOfficialTier || null)}`}>{row.meta?.historicalOfficialTier || "暂无"}</span><small>{row.meta?.officialSince ? `${row.meta.officialSince}确认` : "未确认晋级"}</small></td><td className="tier-history-meta-cell tier-history-days-cell"><b>{row.meta?.currentLevelDays ?? 0} 天</b><small>{row.meta?.currentTier || "暂无等级"}</small></td>{tierHistoryDates.map((date, index) => {
                  const tier = row.tiers.get(date) || "";
                  const previousTier = index < tierHistoryDates.length - 1 ? row.tiers.get(tierHistoryDates[index + 1]) || "" : "";
                  const changed = Boolean(tier && previousTier && tier !== previousTier);
                  return <td key={date} className={changed ? "tier-history-changed" : ""} title={`${date} · ${row.store}号店 · ${tier || "无记录"}${changed ? `（由 ${previousTier} 变为 ${tier}）` : ""}`}><span className={`tier-history-cell tier-${tierTone(tier || null)}`}>{tier || "—"}</span></td>;
                })}</tr>)}</tbody></table></div>
                : <div className="tier-history-state">当前范围暂无等级记录</div>}
            </div>
          </div>
        ) : null}
        <div className="table-panel">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>店铺</th>
                  <th>部门 / 运营</th>
                  <th>店铺层级</th>
                  <th>当前等级满</th>
                  <th>销售额</th>
                  <th>毛利率</th>
                  <th>日均环比</th>
                  <th>同比</th>
                  <th>滞销金额</th>
                  <th>海运占比</th>
                </tr>
              </thead>
              <tbody>
                {(showAll ? tableRows : tableRows.slice(0, 12)).map((row) => {
                  const mom = row.previous.sales ? row.current.sales / currentDays / (row.previous.sales / previousDays) - 1 : null;
                  const storeYoy = row.yearAgo.sales ? row.current.sales / row.yearAgo.sales - 1 : null;
                  return (
                    <tr key={row.store}>
                      <td><button className="store-link" type="button" onClick={() => selectStore(String(row.store))}>{row.store} 号店</button></td>
                      <td><b>{row.department}</b><small>{row.operator}</small></td>
                      <td>{row.tier ? <button className={`tier-badge tier-${tierTone(row.tier)}`} type="button" onClick={() => setFilters((currentFilters) => ({ ...currentFilters, tier: row.tier ?? "", store: "" }))}>{row.tier}</button> : <span className="muted-value">未定级</span>}</td>
                      <td>{row.currentLevelDays ? `${integer(row.currentLevelDays)} 天` : <span className="muted-value">暂无</span>}</td>
                      <td><b>{displayCompactMoney(row.current.sales)}</b><small>毛利 {displayCompactMoney(row.current.grossProfit)}</small></td>
                      <td>{percent(row.current.grossMargin)}</td>
                      <td><span className={`trend-pill ${trendTone(mom)}`}>{growthLabel(mom)}</span></td>
                      <td><span className={`trend-text ${trendTone(storeYoy)}`}>{growthLabel(storeYoy)}</span></td>
                      <td>{row.slowMovingAmount ? displayCompactMoney(row.slowMovingAmount) : "—"}<small>{row.slowMovingShare ? percent(row.slowMovingShare, 2) : ""}</small></td>
                      <td>{row.shippingUnits ? percent(row.oceanShare) : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {tableRows.length > 12 ? (
            <button className="expand-table" type="button" onClick={() => setShowAll((value) => !value)}>
              {showAll ? "收起明细" : `展开全部 ${tableRows.length} 家店铺`}
            </button>
          ) : null}
        </div>
      </section>

      <section className={`dashboard-section${visibleTab === "tasks" ? "" : " tab-hidden"}`} id="tasks" role="tabpanel">
        <KeyTasksBoard visible={visibleTab === "tasks"} />
      </section>

      {visibleTab !== "home" ? <footer className="dashboard-footer">
        <div>
          <span className="brand-mark">BA</span>
          <p><b>经营分析</b><small>SQL Server 实时查询 · ECharts 本地经营分析</small></p>
        </div>
        <p>当前来源：{sourceMode === "daily-snapshot" ? "每日快照" : sourceMode === "database" ? "数据库" : sourceMode === "memory-cache" ? "最近成功缓存" : "Excel 快照"} · 更新于 {new Date(evaluatedAt).toLocaleString("zh-CN", { hour12: false })}</p>
      </footer> : null}
      {activeFormula ? <FormulaDrawer detail={formulaDetails[activeFormula]} mode={sourceMode} evaluatedAt={evaluatedAt} onClose={() => setActiveFormula(null)} /> : null}
    </main>
  );
}
