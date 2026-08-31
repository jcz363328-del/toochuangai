"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ECElementEvent, EChartsOption } from "echarts";
import EChart from "./components/EChart";
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
  type CategorySegment,
  type Filters,
  type WorkbookData,
} from "./lib/dashboard";

type Theme = "light" | "dark";
type SortMode = "sales" | "growth" | "margin" | "slow" | "unshipped";
type DashboardTab = "performance" | "categories" | "operations" | "stores";
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
}

const riskTableLabels: Record<RiskTab, { primary: string; secondary: string; empty: string }> = {
  inventory: { primary: "滞销金额", secondary: "滞销率", empty: "当前范围没有滞销记录" },
  fulfillment: { primary: "未发货金额", secondary: "SKU 次数", empty: "当前范围没有未发货记录" },
  shipping: { primary: "发货件数", secondary: "海运 / 空派", empty: "当前范围没有运输记录" },
  new: { primary: "主 SKU", secondary: "原始记录", empty: "当前范围没有新品记录" },
};

const defaultFilters: Filters = { department: "", operator: "", store: "" };

const trendTone = (value: number | null) =>
  value === null ? "neutral" : value >= 0 ? "positive" : "negative";

const growthLabel = (value: number | null, digits = 1) => {
  if (value === null || !Number.isFinite(value)) return "—";
  if (Math.abs(value) > 9.99) return value > 0 ? ">999%" : "<-999%";
  return percent(value, digits);
};

const growth = (current: number | null, previous: number | null) =>
  current === null || previous === null || !previous ? null : current / previous - 1;

const movementLabel = (value: number | null) =>
  value === null ? "暂无可比数据" : `${value >= 0 ? "上升" : "下降"} ${percent(Math.abs(value), 2)}`;

const pointMovementLabel = (value: number | null) => {
  if (value === null || !Number.isFinite(value)) return "暂无可比数据";
  if (Math.abs(value) < 0.00005) return "基本持平";
  return `${value > 0 ? "上升" : "下降"} ${(Math.abs(value) * 100).toFixed(2)} 个百分点`;
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
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  allLabel?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="filter-field">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
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
}: {
  title: string;
  copy: string;
  tag?: string;
}) {
  return (
    <div className="panel-title">
      <div>
        <h3>{title}</h3>
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
  currentDays,
  previousDays,
  departmentFilter,
  onSelectDepartment,
}: {
  segment: CategorySegment;
  currentLabel: string;
  previousLabel: string;
  currentDays: number;
  previousDays: number;
  departmentFilter: string;
  onSelectDepartment: (department: string) => void;
}) {
  const byDepartment = new Map(segment.departments.map((row) => [row.department, row]));
  const selected = departmentFilter ? byDepartment.get(departmentFilter) : null;
  const company = selected
    ? {
        current: { sales: selected.currentSales, usSales: selected.currentUsSales },
        previous: { sales: selected.previousSales, usSales: selected.previousUsSales },
      }
    : segment.company;
  const departmentRows = FOCUS_DEPARTMENTS
    .map((name) => byDepartment.get(name))
    .filter((row): row is CategorySegment["departments"][number] => Boolean(row))
    .filter((row) => !departmentFilter || row.department === departmentFilter);
  const companyCurrentDaily = company.current.sales / currentDays;
  const companyPreviousDaily = company.previous.sales / previousDays;
  const usCurrentDaily = company.current.usSales / currentDays;
  const usPreviousDaily = company.previous.usSales / previousDays;
  const companyMom = growth(companyCurrentDaily, companyPreviousDaily);
  const usMom = growth(usCurrentDaily, usPreviousDaily);
  const departmentDaily = departmentRows.reduce((totals, row) => ({
    previous: totals.previous + Math.round(row.previousSales / previousDays),
    current: totals.current + Math.round(row.currentSales / currentDays),
    sales: totals.sales + row.currentSales,
  }), { previous: 0, current: 0, sales: 0 });
  const departmentMom = growth(departmentDaily.current, departmentDaily.previous);

  return (
    <article className={`category-arena category-${segment.key}`}>
      <header className="category-arena-head">
        <div>
          <span className="eyebrow">Category arena</span>
          <h3>{segment.label}</h3>
          <p>图创公司与指定五部门同月日均对比</p>
        </div>
        <span className={`trend-pill ${trendTone(companyMom)}`}>图创日均 {growthLabel(companyMom, 2)}</span>
      </header>

      <div className="category-compare-grid company-only">
        <section className="category-data-block">
          <div className="category-block-title"><b>图创公司{segment.label}</b><span>{departmentFilter || "全公司"}</span></div>
          <div className="table-scroll table-scroll-compact">
            <table className="compact-table category-metric-table company-category-table">
              <thead><tr><th>期间</th><th>销售额</th><th>日均</th><th>美国日均</th></tr></thead>
              <tbody>
                <tr><td>{previousLabel}</td><td>{integer(company.previous.sales)}</td><td><b>{integer(companyPreviousDaily)}</b></td><td>{integer(usPreviousDaily)}</td></tr>
                <tr><td>{currentLabel}</td><td>{integer(company.current.sales)}</td><td><b>{integer(companyCurrentDaily)}</b></td><td>{integer(usCurrentDaily)}</td></tr>
              </tbody>
              <tfoot><tr><td>日均环比</td><td>—</td><td><span className={`trend-pill ${trendTone(companyMom)}`}>{growthLabel(companyMom, 2)}</span></td><td><span className={`trend-text ${trendTone(usMom)}`}>{growthLabel(usMom, 2)}</span></td></tr></tfoot>
            </table>
          </div>
        </section>
      </div>

      <p className="category-insight">
        图创公司较上月{movementLabel(companyMom)}，美国口径{movementLabel(usMom)}。
      </p>

      <section className="category-department-block">
        <div className="category-block-title"><b>按部门维度统计{segment.label}增长</b><span>日均口径</span></div>
        <div className="table-scroll table-scroll-compact">
          <table className="compact-table category-department-table">
            <thead><tr><th>部门</th><th>{previousLabel}日均</th><th>{currentLabel}日均</th><th>环比</th><th>{currentLabel}销售额</th></tr></thead>
            <tbody>
              {departmentRows.map((row) => {
                const previousDaily = Math.round(row.previousSales / previousDays);
                const currentDaily = Math.round(row.currentSales / currentDays);
                const dailyMom = growth(currentDaily, previousDaily);
                return (
                  <tr key={row.department}>
                    <td><button className="store-link" type="button" onClick={() => onSelectDepartment(row.department)}>{row.department}</button></td>
                    <td>{integer(previousDaily)}</td>
                    <td><b>{integer(currentDaily)}</b></td>
                    <td><span className={`trend-pill ${trendTone(dailyMom)}`}>{growthLabel(dailyMom, 2)}</span></td>
                    <td>{integer(row.currentSales)}</td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot><tr><td>{departmentFilter ? `${departmentFilter}合计` : "五部门合计"}</td><td>{integer(departmentDaily.previous)}</td><td>{integer(departmentDaily.current)}</td><td><span className={`trend-pill ${trendTone(departmentMom)}`}>{growthLabel(departmentMom, 2)}</span></td><td>{integer(departmentDaily.sales)}</td></tr></tfoot>
          </table>
        </div>
      </section>
      <p className="category-method">
        图创日均：v_MaoLiLv 月销售额 ÷ 对应自然月天数；美国口径：Guo=美国；部门表仅统计指定五部门。
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
          <span className={`source-badge source-${mode}`}>{mode === "database" ? "实时数据库" : mode === "memory-cache" ? "最近成功缓存" : "Excel 快照"}</span>
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
  const [period, setPeriod] = useState(
    initialPeriod ? `${initialPeriod.year}-${String(initialPeriod.month).padStart(2, "0")}` : "2026-07",
  );
  const live = useLiveDashboard(initialData, period);
  const data = live.data;
  const [theme, setTheme] = useState<Theme>("light");
  const [filters, setFilters] = useState<Filters>(defaultFilters);
  const [sortMode, setSortMode] = useState<SortMode>("sales");
  const [showAll, setShowAll] = useState(false);
  const [activeTab, setActiveTab] = useState<DashboardTab>("performance");
  const [riskTab, setRiskTab] = useState<RiskTab>("inventory");
  const [activeFormula, setActiveFormula] = useState<FormulaId | null>(null);
  const themeReady = useRef(false);

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

  const allStores = useMemo(() => buildStoreViews(data), [data]);
  const stores = useMemo(
    () => allStores.filter((row) => isFocusDepartment(row.department)),
    [allStores],
  );
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
      [...new Set(stores.filter((row) => !filters.department || row.department === filters.department).map((row) => row.operator))]
        .sort((a, b) => a.localeCompare(b, "zh-CN")),
    [filters.department, stores],
  );
  const storeOptions = useMemo(
    () =>
      stores
        .filter(
          (row) =>
            (!filters.department || row.department === filters.department) &&
            (!filters.operator || row.operator === filters.operator),
        )
        .sort((a, b) => a.store - b.store),
    [filters.department, filters.operator, stores],
  );
  const filteredStores = useMemo(
    () => stores.filter((row) => matchesFilters(row, filters)),
    [filters, stores],
  );
  const performanceStores = useMemo(
    () => filteredStores.filter((row) => row.hasPerformance),
    [filteredStores],
  );
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
          primary: money(row.slowMovingAmount),
          secondary: percent(row.slowMovingShare, 2),
          sortValue: row.slowMovingAmount,
        }] : [];
      }
      if (riskTab === "fulfillment") {
        return row.unshippedCount > 0 ? [{
          store: row.store,
          department: row.department,
          operator: row.operator,
          primary: money(row.unshippedAmount),
          secondary: `${integer(row.unshippedCount)} 次`,
          sortValue: row.unshippedAmount,
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
  }, [filteredStores, newOrdersByStore, riskTab]);

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
        valueFormatter: (value: unknown) => money(Number(value)),
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
          axisLabel: { color: colors.muted, formatter: (value: number) => `${Math.round(value / 10000)}万` },
          splitLine: { lineStyle: { color: colors.line, type: "dashed" } },
        },
        {
          type: "value",
          min: 0,
          max: Math.max(35, Math.ceil(Math.max(...departments.map((row) => (row.current.grossMargin ?? 0) * 100)) / 5) * 5),
          axisLabel: { color: colors.muted, formatter: "{value}%" },
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
          data: departments.map((row) => Number(((row.current.grossMargin ?? 0) * 100).toFixed(2))),
          symbol: "circle",
          symbolSize: 8,
          lineStyle: { width: 2.5 },
          tooltip: { valueFormatter: (value: unknown) => `${Number(value).toFixed(1)}%` },
        },
      ],
    };
  }, [colors, currentPeriod?.label, departments, previousPeriod?.label, yearAgoPeriod?.label]);

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
          return `<strong>${point[2]}号店 · ${point[3]}</strong><br/>销售额：${money(Number(point[0]) * 10000)}<br/>毛利率：${Number(point[1]).toFixed(1)}%<br/>毛利润：${money(Number(point[4]) * 10000)}`;
        },
      },
      xAxis: {
        type: "value",
        name: "销售额（万元）",
        nameTextStyle: { color: colors.muted },
        axisLabel: { color: colors.muted },
        splitLine: { lineStyle: { color: colors.line, type: "dashed" } },
      },
      yAxis: {
        type: "value",
        name: "毛利率",
        nameTextStyle: { color: colors.muted },
        axisLabel: { color: colors.muted, formatter: "{value}%" },
        splitLine: { lineStyle: { color: colors.line, type: "dashed" } },
      },
      series: groups.map((group) => ({
        name: group,
        type: "scatter",
        data: rows
          .filter((row) => row.department === group)
          .map((row) => [
            Number((row.current.sales / 10000).toFixed(2)),
            Number(((row.current.grossMargin ?? 0) * 100).toFixed(2)),
            row.store,
            row.operator,
            Number((row.current.grossProfit / 10000).toFixed(2)),
          ]),
        symbolSize: (value: unknown) => Math.max(10, Math.min(34, Math.sqrt(Number((value as number[])[0])) * 4.5)),
        emphasis: { focus: "series", scale: 1.25 },
      })),
    };
  }, [colors, performanceStores]);

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
        formatter: "{b}<br/>{c} 件 · {d}%",
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
        valueFormatter: (value: unknown) => money(Number(value)),
      },
      xAxis: {
        type: "value",
        axisLabel: { color: colors.muted, formatter: (value: number) => `${Math.round(value / 10000)}万` },
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
            formatter: (params: unknown) => compactMoney(Number((params as { value?: number }).value ?? 0)),
          },
        },
      ],
    };
  }, [colors, filteredStores]);

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
          tooltip: { valueFormatter: (value: unknown) => money(Number(value)) },
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
  }, [colors, filteredStores]);

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
      if (sortMode === "slow") return b.slowMovingAmount - a.slowMovingAmount;
      if (sortMode === "unshipped") return b.unshippedAmount - a.unshippedAmount;
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
  const hasFilters = Boolean(filters.department || filters.operator || filters.store);
  const sourceMode = live.source?.mode ?? "workbook-snapshot";
  const evaluatedAt = live.source?.fetchedAt ?? data.meta.extractedAt;
  const statusLabel = live.phase === "refreshing"
    ? "更新中"
    : sourceMode === "workbook-snapshot"
      ? "快照"
      : live.source?.stale
        ? "部分缓存"
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
      value: money(current.sales),
      expression: "销售额 = Σ 当前筛选店铺销售额",
      note: "与 Excel 的 DBTORS 汇总口径一致；切换部门、运营或店铺后立即重算。",
      inputs: [
        { label: currentPeriod?.label ?? "本期销售明细", value: money(current.sales), source: "v_MaoLiLv.XiaoShouE" },
        { label: "纳入店铺", value: `${performanceStores.length} 家`, source: "当前筛选" },
      ],
      sql: "SUM(v_MaoLiLv.XiaoShouE)\nWHERE RiQi >= @start AND RiQi < @end",
    },
    "profit.current": {
      id: "profit.current",
      label: "毛利润",
      value: money(current.grossProfit),
      expression: "毛利润 = Σ 店铺毛利润",
      note: "按逐店明细累加，避免沿用 Excel 页脚漏行的问题。",
      inputs: [
        { label: "毛利润明细", value: money(current.grossProfit), source: "v_MaoLiLv.MaoLiRun" },
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
        { label: "毛利润", value: money(current.grossProfit), source: "v_MaoLiLv.MaoLiRun" },
        { label: "毛利率分母", value: money(current.grossMarginBase), source: "v_MaoLiLv.MaoLiLvFenMu" },
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
        { label: `${currentPeriod?.label ?? "本期"}销售`, value: money(current.sales), source: "实时聚合" },
        { label: "本期天数", value: `${currentDays} 天`, source: "期间公式" },
        { label: `${previousPeriod?.label ?? "上期"}销售`, value: money(previous.sales), source: "实时聚合" },
        { label: "上期天数", value: `${previousDays} 天`, source: "期间公式" },
      ],
      sql: "(SUM(current.XiaoShouE) / @currentDays)\n/ (SUM(previous.XiaoShouE) / @previousDays) - 1",
    },
  }), [current, currentDays, currentPeriod?.label, dailyMom, performanceStores.length, previous.sales, previousDays, previousPeriod?.label]);

  const selectStore = (store: string) => {
    const row = stores.find((item) => String(item.store) === store);
    setFilters({
      department: row?.department ?? filters.department,
      operator: row?.operator ?? filters.operator,
      store,
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
            <label className="period-control"><span>期间</span><input type="month" value={period} onChange={(event) => setPeriod(event.target.value)} /></label>
            <div className={`data-status status-${sourceMode}${live.source?.stale ? " is-stale" : ""}${live.phase === "refreshing" ? " is-refreshing" : ""}`} title={live.source?.warning ?? "数据连接状态"}>
              <i /><span>{statusLabel}</span>
            </div>
            <span className="updated-at">{new Date(evaluatedAt).toLocaleTimeString("zh-CN", { hour12: false })}</span>
            <button className="icon-button refresh-button" type="button" onClick={() => void live.refresh(true)} disabled={live.phase === "refreshing"} aria-label="立即刷新">↻</button>
            <button className="icon-button" type="button" onClick={() => setTheme(theme === "light" ? "dark" : "light")} aria-label={`切换为${theme === "light" ? "深色" : "浅色"}模式`}>{theme === "light" ? "暗" : "明"}</button>
          </div>
        </div>
      </header>

      <section className="dashboard-toolbar" aria-label="数据筛选">
        <div className="filter-fields">
          <SelectField
            label="部门"
            value={filters.department}
            options={departmentOptions.map((value) => ({ value, label: value }))}
            allLabel="五部门汇总"
            onChange={(department) => setFilters({ department, operator: "", store: "" })}
          />
          <SelectField
            label="运营"
            value={filters.operator}
            options={operatorOptions.map((value) => ({ value, label: value }))}
            onChange={(operator) => setFilters((currentFilters) => ({ ...currentFilters, operator, store: "" }))}
          />
          <SelectField
            label="店铺"
            value={filters.store}
            options={storeOptions.map((row) => ({ value: String(row.store), label: `${row.store} 号店` }))}
            onChange={selectStore}
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
          <span className="scope-label">固定范围：5 个部门</span>
          <i />
          <span>{performanceStores.length}</span> 家业绩店
          <i />
          <span>{filteredStores.length}</span> 家数据店
        </div>
      </section>

      <section className="kpi-grid" aria-label="关键指标">
        <KpiCard
          label="销售额"
          value={compactMoney(current.sales)}
          delta={`同比 ${growthLabel(yoy)}`}
          note={`${currentPeriod?.label ?? "本期"} · 日均 ${compactMoney(current.sales / currentDays)}`}
          tone={trendTone(totalMom)}
          priority
          formulaId="sales.current"
          onInspect={setActiveFormula}
        />
        <KpiCard
          label="毛利润"
          value={compactMoney(current.grossProfit)}
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

      <nav className="dashboard-tabs" role="tablist" aria-label="分析模块">
        {([
          ["performance", "业绩分析"],
          ["categories", `品类阵营 · ${categorySegments.length}`],
          ["operations", `运营风险 · ${integer(unshippedCount)}`],
          ["stores", `店铺明细 · ${performanceStores.length}`],
        ] as const).map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={activeTab === id}
            className={activeTab === id ? "active" : ""}
            onClick={() => {
              setActiveTab(id);
              if (id === "categories") setFilters((currentFilters) => ({ ...currentFilters, operator: "", store: "" }));
            }}
          >
            {label}
          </button>
        ))}
      </nav>

      <section className={`dashboard-section${activeTab === "performance" ? "" : " tab-hidden"}`} id="performance" role="tabpanel">
        <div className="section-bar">
          <div><span className="eyebrow">Performance</span><h2>增长与毛利</h2><p>三期同口径对比；点击部门或店铺可联动筛选。</p></div>
          <span className="data-chip">{performanceStores.length} 家业绩店</span>
        </div>

        <div className="panel-grid panel-grid-main">
          <article className="panel panel-span-12 performance-overview">
            <PanelTitle
              title="整体业绩"
              copy="全公司三期汇总；部门筛选仅作用于下方分析"
              tag="全公司口径"
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
                        <td><b>{integer(row.metric.sales)}</b></td>
                        <td>{row.metric.dailySales === null ? "—" : integer(row.metric.dailySales)}<small>{row.days} 天</small></td>
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
                    全公司本期销售额 <strong>{compactMoney(overallPerformance.current.sales)}</strong>，日均 <strong>{overallPerformance.current.dailySales === null ? "—" : compactMoney(overallPerformance.current.dailySales)}</strong>；日均环比较上期
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
            {departments.length ? (
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
            ) : <div className="empty-state">当前筛选没有部门业绩数据</div>}
          </article>

          <aside className="panel insight-panel panel-span-4">
            <PanelTitle title="需要关注" copy="按当前筛选自动更新" tag="实时公式" />
            <ol className="insight-list">
              <li>
                <span>01</span>
                <div><small>销售贡献最高</small><strong>{topDepartment?.name ?? "—"}</strong><p>{topDepartment ? `${compactMoney(topDepartment.current.sales)} · 占比 ${percent(current.sales ? topDepartment.current.sales / current.sales : null)}` : "暂无数据"}</p></div>
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
                      <td><b>{money(row.current.sales)}</b></td>
                      <td>{percent(current.sales ? row.current.sales / current.sales : null, 2)}</td>
                      <td>{money(row.current.grossProfit)}</td>
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
            <PanelTitle title="店铺效率象限" copy="横轴销售额，纵轴毛利率，气泡大小反映销售规模" tag="点击气泡定位店铺" />
            <EChart
              option={scatterOption}
              theme={theme === "dark" ? "dark" : undefined}
              height={256}
              ariaLabel="店铺销售额和毛利率散点图"
              onClick={(event) => {
                const store = metricFromEvent(event, 2);
                if (store) selectStore(store);
              }}
            />
          </article>
        </div>
      </section>

      <section className={`dashboard-section${activeTab === "categories" ? "" : " tab-hidden"}`} id="categories" role="tabpanel">
        <div className="section-bar">
          <div><span className="eyebrow">Category arena</span><h2>对毛与簇毛</h2><p>图创全公司销售、美国口径和指定五部门日均增长。</p></div>
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
                currentDays={currentDays}
                previousDays={previousDays}
                departmentFilter={filters.department}
                onSelectDepartment={(department) => setFilters({ department, operator: "", store: "" })}
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

      <section className={`dashboard-section${activeTab === "operations" ? "" : " tab-hidden"}`} id="operations" role="tabpanel">
        <div className="section-bar">
          <div><span className="eyebrow">Operations & risk</span><h2>运营风险</h2><p>一次只看一类风险，保留同一店铺筛选。</p></div>
          <span className="data-chip data-chip-warn">{integer(unshippedCount)} 次未及时发货</span>
        </div>

        <div className="ops-strip">
          <div><span>新品主 SKU 记录</span><strong>{integer(uniqueNewOrders)}</strong><small>原始明细 {integer(newOrders.length)} 条</small></div>
          <div><span>滞销率</span><strong>{percent(slowShare, 2)}</strong><small>{compactMoney(slowMoving)} / {compactMoney(inventory)}</small></div>
          <div><span>未发货金额</span><strong>{compactMoney(unshippedAmount)}</strong><small>{integer(unshippedCount)} 次 SKU 记录</small></div>
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
            <PanelTitle title="滞销金额 Top 10" copy="优先处理金额高、占比高的店铺" tag={compactMoney(slowMoving)} />
            <EChart option={slowOption} theme={theme === "dark" ? "dark" : undefined} height={248} ariaLabel="店铺滞销金额前十名" />
          </article>
          <article className={`panel panel-span-7${riskTab === "fulfillment" ? "" : " tab-hidden"}`}>
            <PanelTitle title="未及时发货风险" copy="柱形为金额，折线为 SKU 次数" tag={`${integer(unshippedCount)} 次`} />
            <EChart option={unshippedOption} theme={theme === "dark" ? "dark" : undefined} height={248} ariaLabel="店铺未及时发货金额与SKU次数图" />
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
                      <th>{riskTableLabels[riskTab].primary}</th>
                      <th>{riskTableLabels[riskTab].secondary}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {riskDetailRows.map((row) => (
                      <tr key={`${riskTab}-${row.store}`}>
                        <td><button className="store-link" type="button" onClick={() => selectStore(String(row.store))}>{row.store} 号店</button></td>
                        <td><b>{row.department}</b><small>{row.operator}</small></td>
                        <td><b>{row.primary}</b></td>
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

      <section className={`dashboard-section${activeTab === "stores" ? "" : " tab-hidden"}`} id="stores" role="tabpanel">
        <div className="section-bar">
          <div><span className="eyebrow">Store detail</span><h2>店铺明细</h2><p>销售、毛利、增长与风险在一张表内对齐。</p></div>
          <div>
            <label className="sort-control">
              <span>排序</span>
              <select value={sortMode} onChange={(event) => setSortMode(event.target.value as SortMode)}>
                <option value="sales">销售额</option>
                <option value="growth">日均环比</option>
                <option value="margin">毛利率</option>
                <option value="slow">滞销金额</option>
                <option value="unshipped">未发货金额</option>
              </select>
            </label>
          </div>
        </div>
        <div className="table-panel">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>店铺</th>
                  <th>部门 / 运营</th>
                  <th>销售额</th>
                  <th>毛利率</th>
                  <th>日均环比</th>
                  <th>同比</th>
                  <th>滞销金额</th>
                  <th>海运占比</th>
                  <th>未发货</th>
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
                      <td><b>{compactMoney(row.current.sales)}</b><small>毛利 {compactMoney(row.current.grossProfit)}</small></td>
                      <td>{percent(row.current.grossMargin)}</td>
                      <td><span className={`trend-pill ${trendTone(mom)}`}>{growthLabel(mom)}</span></td>
                      <td><span className={`trend-text ${trendTone(storeYoy)}`}>{growthLabel(storeYoy)}</span></td>
                      <td>{row.slowMovingAmount ? compactMoney(row.slowMovingAmount) : "—"}<small>{row.slowMovingShare ? percent(row.slowMovingShare, 2) : ""}</small></td>
                      <td>{row.shippingUnits ? percent(row.oceanShare) : "—"}</td>
                      <td>{row.unshippedAmount ? <><b className="warning-text">{compactMoney(row.unshippedAmount)}</b><small>{integer(row.unshippedCount)} 次</small></> : "—"}</td>
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

      <footer className="dashboard-footer">
        <div>
          <span className="brand-mark">BA</span>
          <p><b>经营分析</b><small>SQL Server 实时查询 · ECharts 本地经营分析</small></p>
        </div>
        <p>当前来源：{sourceMode === "database" ? "数据库" : sourceMode === "memory-cache" ? "最近成功缓存" : "Excel 快照"} · 更新于 {new Date(evaluatedAt).toLocaleString("zh-CN", { hour12: false })}</p>
      </footer>
      {activeFormula ? <FormulaDrawer detail={formulaDetails[activeFormula]} mode={sourceMode} evaluatedAt={evaluatedAt} onClose={() => setActiveFormula(null)} /> : null}
    </main>
  );
}
