"use client";

import type { EChartsOption } from "echarts";
import { useCallback, useEffect, useMemo, useState } from "react";
import EChart from "./EChart";

type MonthEntry = {
  month: string;
  date: string;
  metrics: Record<string, number | null>;
  extras?: Record<string, number | null>;
  values?: Record<string, number | string | null>;
  importedAt?: string | null;
  sourceFile?: string | null;
};

type ColumnDefinition = {
  label: string;
  format: string;
};

type OverviewPayload = {
  updatedAt?: string | null;
  months: Array<{ month: string; date: string }>;
  selected: MonthEntry | null;
  previous: MonthEntry | null;
  metrics: Array<{ key: string; label: string; unit: string; format: "integer" | "money" }>;
  columns?: ColumnDefinition[];
  history: MonthEntry[];
  growth?: Record<string, number | null>;
};

const ENDPOINT = "/api/ai/business-analysis/company-market";
const ENTRY_ENDPOINT = `${ENDPOINT}/entry`;

const integerFormat = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 });
const moneyFormat = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 });
const decimalFormat = new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const monthLabel = (month: string) => {
  const [year, monthNumber] = month.split("-");
  return `${year} 年 ${Number(monthNumber)} 月`;
};

const formatColumnValue = (value: number | string | null | undefined, format: string) => {
  if (value === null || value === undefined || value === "") return "—";
  if (format === "date") return String(value);
  if (typeof value === "string") {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return value;
    value = parsed;
  }
  if (!Number.isFinite(value)) return "—";
  switch (format) {
    case "ratio":
      return `${(value * 100).toFixed(2)}%`;
    case "money":
      return `¥${moneyFormat.format(value)}`;
    case "integer":
      return integerFormat.format(value);
    case "decimal":
      return decimalFormat.format(value);
    default:
      return integerFormat.format(value);
  }
};

const unitHint = (format: string) => {
  switch (format) {
    case "date":
      return "年月日";
    case "ratio":
      return "%";
    case "money":
      return "元";
    case "integer":
      return "件";
    case "decimal":
      return "元";
    default:
      return "";
  }
};

const toInputValue = (raw: number | string | null | undefined, format: string) => {
  if (raw === null || raw === undefined || raw === "") return "";
  if (format === "date") return String(raw);
  const number = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(number)) return String(raw);
  if (format === "ratio") return String(Number((number * 100).toFixed(4)));
  if (format === "integer") return String(Math.round(number));
  return String(Number(number.toFixed(4)));
};

const tooltipValue = (value: unknown, formatter: (number: number) => string) => {
  const number = typeof value === "number" ? value : Number(value);
  if (value === null || value === undefined || value === "" || !Number.isFinite(number)) return "—";
  return formatter(number);
};

const compactMoney = (value: number) => {
  if (!Number.isFinite(value)) return "—";
  if (Math.abs(value) >= 100000000) return `${(value / 100000000).toFixed(2)} 亿`;
  if (Math.abs(value) >= 10000) return `${(value / 10000).toFixed(0)} 万`;
  return `${Math.round(value)}`;
};

// 系统自动计算的列：不需要手工填写
const DERIVED_LABELS = [
  "类目环比上月增长率",
  "美国市场日均环比增长率",
  "大盘客单价",
  "公司结算环比上月增长率",
  "公司销量环比上月增长率",
  "假睫毛大盘占比",
  "公司客单价",
];

// 「类目」在页面上统一称为「美国站市场」，存储列名保持不变
const DISPLAY_LABEL_OVERRIDES: Record<string, string> = {
  类目销量: "美国站市场销量",
  类目销售额: "美国站市场销售额",
  大盘客单价: "美国站市场客单价",
  类目环比上月增长率: "美国站市场环比上月增长率",
  假睫毛大盘占比: "假睫毛美国站市场占比",
};

const displayLabel = (label: string) => DISPLAY_LABEL_OVERRIDES[label] || label;

const previousMonth = (month: string) => {
  const [year, monthNumber] = month.split("-").map((part) => Number(part));
  if (!Number.isFinite(year) || !Number.isFinite(monthNumber)) return "";
  if (monthNumber === 1) return `${year - 1}-12`;
  return `${year}-${String(monthNumber - 1).padStart(2, "0")}`;
};

const daysInMonth = (month: string) => {
  const [year, monthNumber] = month.split("-").map((part) => Number(part));
  if (!Number.isFinite(year) || !Number.isFinite(monthNumber)) return 0;
  return new Date(year, monthNumber, 0).getDate();
};

export default function CompanyMarketPanel({ visible = true, theme = "light" }: { visible?: boolean; theme?: string }) {
  const [overview, setOverview] = useState<OverviewPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [formMonth, setFormMonth] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  });
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [loadedMonth, setLoadedMonth] = useState("");
  const [entryOpen, setEntryOpen] = useState(false);

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch(ENDPOINT, {
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload?.error?.message || `数据读取失败（HTTP ${response.status}）`);
      }
      setOverview(payload as OverviewPayload);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "数据读取失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!visible) return;
    void loadOverview();
  }, [visible, loadOverview]);

  const sourceColumns = useMemo(() => overview?.columns || [], [overview?.columns]);
  const history = overview?.history || [];

  const entryByMonth = useMemo(() => {
    const map = new Map<string, MonthEntry>();
    history.forEach((entry) => map.set(entry.month, entry));
    return map;
  }, [history]);

  // 选中月份变化时，把已有数据回填到表单（便于覆盖修改）
  useEffect(() => {
    if (!visible || !sourceColumns.length) return;
    const existing = entryByMonth.get(formMonth);
    const nextValues: Record<string, string> = {};
    sourceColumns.forEach((column) => {
      nextValues[column.label] = toInputValue(existing?.values?.[column.label], column.format);
    });
    setFormValues(nextValues);
    setLoadedMonth(existing ? existing.month : "");
  }, [formMonth, sourceColumns, entryByMonth, visible]);

  const handleValueChange = (label: string, value: string) => {
    setFormValues((current) => ({ ...current, [label]: value }));
  };

  const rawColumns = useMemo(
    () => sourceColumns.filter((column) => !DERIVED_LABELS.includes(column.label)),
    [sourceColumns],
  );
  const derivedColumns = useMemo(
    () => sourceColumns.filter((column) => DERIVED_LABELS.includes(column.label)),
    [sourceColumns],
  );

  const derivedPreview = useMemo(() => {
    const readValue = (label: string) => {
      const raw = (formValues[label] || "").trim().replace(/,/g, "").replace(/，/g, "");
      if (!raw) return null;
      const number = Number(raw.replace(/%/g, ""));
      return Number.isFinite(number) ? number : null;
    };
    const previousEntry = entryByMonth.get(previousMonth(formMonth));
    const readPrevious = (label: string) => {
      const raw = previousEntry?.values?.[label];
      if (raw === null || raw === undefined || raw === "") return null;
      const number = typeof raw === "number" ? raw : Number(raw);
      return Number.isFinite(number) ? number : null;
    };
    const growth = (current: number | null, base: number | null) =>
      current === null || base === null || base === 0 ? null : current / base - 1;

    const categorySales = readValue("类目销售额");
    const categoryVolume = readValue("类目销量");
    const orderSales = readValue("公司订单销售额");
    const orderVolume = readValue("公司订单销量");
    const settlementSales = readValue("公司结算销售额");
    const previousCategorySales = readPrevious("类目销售额");
    const previousPeriod = previousMonth(formMonth);
    const currentDays = daysInMonth(formMonth);
    const previousDays = daysInMonth(previousPeriod);
    const dailyCategoryGrowth = categorySales !== null && previousCategorySales !== null && currentDays && previousDays
      ? growth(categorySales / currentDays, previousCategorySales / previousDays)
      : null;

    return {
      "大盘客单价": categorySales && categoryVolume ? categorySales / categoryVolume : null,
      "公司客单价": orderSales && orderVolume ? orderSales / orderVolume : null,
      "类目环比上月增长率": growth(categorySales, previousCategorySales),
      "美国市场日均环比增长率": dailyCategoryGrowth,
      "公司结算环比上月增长率": growth(settlementSales, readPrevious("公司结算销售额")),
      "公司销量环比上月增长率": growth(orderVolume, readPrevious("公司订单销量")),
      "假睫毛大盘占比": orderSales && categorySales ? orderSales / categorySales : null,
    } as Record<string, number | null>;
  }, [formValues, entryByMonth, formMonth]);

  const submitEntry = async () => {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const payloadValues: Record<string, string | number> = {};
      for (const column of rawColumns) {
        const raw = (formValues[column.label] || "").trim();
        if (!raw) continue;
        if (column.format === "date") {
          payloadValues[column.label] = raw;
          continue;
        }
        const normalized = raw.replace(/,/g, "").replace(/，/g, "").replace(/%/g, "");
        const number = Number(normalized);
        if (!Number.isFinite(number)) {
          throw new Error(`${column.label} 填写的不是有效数字：${raw}`);
        }
        payloadValues[column.label] = column.format === "ratio" ? number / 100 : number;
      }
      if (!Object.keys(payloadValues).some((label) => label !== "日期")) {
        throw new Error("请至少填写一个数值后再保存");
      }
      const response = await fetch(ENTRY_ENDPOINT, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ month: formMonth, values: payloadValues }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload?.error?.message || `保存失败（HTTP ${response.status}）`);
      }
      setOverview(payload as OverviewPayload);
      setNotice(`${monthLabel(formMonth)} 已保存${loadedMonth ? "（覆盖原数据）" : ""}`);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const chartColors = theme === "dark"
    ? { text: "#aebbd0", line: "#34435c", market: "#8fa1c4", order: "#6da8ff", settlement: "#5ec991", accent: "#e1b84b" }
    : { text: "#65728a", line: "#e1e7f0", market: "#93a4c5", order: "#315dc9", settlement: "#2f9b68", accent: "#d9a323" };

  const series = useMemo(() => {
    const ascending = [...history].sort((a, b) => (a.month < b.month ? -1 : 1));
    const labels = ascending.map((entry) => entry.month);
    const pick = (entry: MonthEntry, label: string) => {
      const value = entry.values?.[label];
      if (value === null || value === undefined || value === "") return null;
      const number = typeof value === "number" ? value : Number(value);
      return Number.isFinite(number) ? number : null;
    };
    return {
      labels,
      categorySales: ascending.map((entry) => pick(entry, "类目销售额")),
      orderSales: ascending.map((entry) => pick(entry, "公司订单销售额")),
      categoryVolume: ascending.map((entry) => pick(entry, "类目销量")),
      orderVolume: ascending.map((entry) => pick(entry, "公司订单销量")),
      categoryPrice: ascending.map((entry) => pick(entry, "大盘客单价")),
      companyPrice: ascending.map((entry) => pick(entry, "公司客单价")),
      orderShare: ascending.map((entry) => {
        const category = pick(entry, "类目销售额");
        const order = pick(entry, "公司订单销售额");
        return category && order ? order / category : null;
      }),
    };
  }, [history]);

  const baseAxis = useMemo(
    () => ({
      axisLabel: { color: chartColors.text, fontSize: 10 },
      axisLine: { lineStyle: { color: chartColors.line } },
      splitLine: { lineStyle: { color: chartColors.line, type: "dashed" as const } },
    }),
    [chartColors],
  );

  const salesOption = useMemo<EChartsOption>(() => ({
    color: [chartColors.market, chartColors.order],
    legend: { top: 0, right: 8, itemWidth: 14, itemHeight: 6, textStyle: { color: chartColors.text, fontSize: 11 } },
    grid: { left: 56, right: 16, top: 38, bottom: 28 },
    tooltip: {
      trigger: "axis",
      valueFormatter: (value: unknown) => tooltipValue(value, (number) => `¥${moneyFormat.format(number)}`),
    },
    xAxis: { type: "category", data: series.labels, ...baseAxis, axisLabel: { ...baseAxis.axisLabel, formatter: (value: string) => value.slice(2) } },
    yAxis: { type: "value", ...baseAxis, axisLabel: { ...baseAxis.axisLabel, formatter: (value: number) => compactMoney(value) } },
    series: [
      { name: "美国站市场销售额", type: "line", smooth: true, showSymbol: false, data: series.categorySales },
      { name: "公司订单销售额", type: "line", smooth: true, showSymbol: false, data: series.orderSales },
    ],
  }), [series, baseAxis, chartColors]);

  const volumeOption = useMemo<EChartsOption>(() => ({
    color: [chartColors.market, chartColors.order],
    legend: { top: 0, right: 8, itemWidth: 14, itemHeight: 6, textStyle: { color: chartColors.text, fontSize: 11 } },
    grid: { left: 56, right: 16, top: 38, bottom: 28 },
    tooltip: { trigger: "axis", valueFormatter: (value: unknown) => tooltipValue(value, (number) => `${integerFormat.format(number)} 件`) },
    xAxis: { type: "category", data: series.labels, ...baseAxis, axisLabel: { ...baseAxis.axisLabel, formatter: (value: string) => value.slice(2) } },
    yAxis: { type: "value", ...baseAxis, axisLabel: { ...baseAxis.axisLabel, formatter: (value: number) => (Math.abs(value) >= 10000 ? `${(value / 10000).toFixed(0)} 万` : `${Math.round(value)}`) } },
    series: [
      { name: "美国站市场销量", type: "line", smooth: true, showSymbol: false, data: series.categoryVolume },
      { name: "公司订单销量", type: "line", smooth: true, showSymbol: false, data: series.orderVolume },
    ],
  }), [series, baseAxis, chartColors]);

  const shareOption = useMemo<EChartsOption>(() => ({
    color: [chartColors.order],
    legend: { top: 0, right: 8, itemWidth: 14, itemHeight: 6, textStyle: { color: chartColors.text, fontSize: 11 } },
    grid: { left: 52, right: 16, top: 38, bottom: 28 },
    tooltip: { trigger: "axis", valueFormatter: (value: unknown) => tooltipValue(value, (number) => `${(number * 100).toFixed(2)}%`) },
    xAxis: { type: "category", data: series.labels, ...baseAxis, axisLabel: { ...baseAxis.axisLabel, formatter: (value: string) => value.slice(2) } },
    yAxis: { type: "value", ...baseAxis, axisLabel: { ...baseAxis.axisLabel, formatter: (value: number) => `${(value * 100).toFixed(0)}%` } },
    series: [
      { name: "公司订单销售额占美国站市场", type: "line", smooth: true, showSymbol: false, areaStyle: { opacity: 0.12 }, data: series.orderShare },
    ],
  }), [series, baseAxis, chartColors]);

  const priceOption = useMemo<EChartsOption>(() => ({
    color: [chartColors.market, chartColors.accent],
    legend: { top: 0, right: 8, itemWidth: 14, itemHeight: 6, textStyle: { color: chartColors.text, fontSize: 11 } },
    grid: { left: 52, right: 16, top: 38, bottom: 28 },
    tooltip: { trigger: "axis", valueFormatter: (value: unknown) => tooltipValue(value, (number) => `${decimalFormat.format(number)} 元`) },
    xAxis: { type: "category", data: series.labels, ...baseAxis, axisLabel: { ...baseAxis.axisLabel, formatter: (value: string) => value.slice(2) } },
    yAxis: { type: "value", ...baseAxis, scale: true, axisLabel: { ...baseAxis.axisLabel, formatter: (value: number) => `${value.toFixed(0)}` } },
    series: [
      { name: "美国站市场客单价", type: "line", smooth: true, showSymbol: false, data: series.categoryPrice },
      { name: "公司客单价", type: "line", smooth: true, showSymbol: false, data: series.companyPrice },
    ],
  }), [series, baseAxis, chartColors]);

  if (!visible) return null;

  return (
    <section className="cm-shell">
      <div className="section-bar">
        <div>
          <span className="eyebrow">US Market vs Company</span>
          <h2>美国站市场与大盘对比</h2>
          <p>按月手动录入并覆盖保存，图表对比公司与美国站市场的销售、销量、占比与客单价；美国站市场销量和销售额会同步到「大盘趋势」。</p>
        </div>
        <span className="data-chip">{overview ? `${history.length} 个月数据` : "加载中"}</span>
      </div>

      {error ? <p className="cm-alert cm-alert-error">{error}</p> : null}
      {notice ? <p className="cm-alert cm-alert-success">{notice}</p> : null}

      <article className={entryOpen ? "panel cm-entry-panel cm-entry-open" : "panel cm-entry-panel"}>
        <div className="panel-title cm-entry-title">
          <div>
            <div className="panel-title-heading">
              <h3>按月录入</h3>
            </div>
            <p>选择月份后填写各项数值；同一月份再次保存会直接覆盖旧数据。</p>
          </div>
          <div className="cm-entry-title-actions">
            <span className="panel-tag">{loadedMonth ? "该月已有数据 · 可覆盖" : "新建月份"}</span>
            <button
              className="cm-button cm-button-ghost"
              type="button"
              aria-expanded={entryOpen}
              onClick={() => setEntryOpen((open) => !open)}
            >
              {entryOpen ? "收起" : "展开录入"}
            </button>
          </div>
        </div>

        {entryOpen ? (
          <>
            <div className="cm-entry-head">
              <label className="cm-month-field">
                <span>月份</span>
                <input
                  type="month"
                  value={formMonth}
                  onChange={(event) => setFormMonth(event.target.value || formMonth)}
                />
              </label>
              <button className="cm-button cm-button-ghost" type="button" onClick={() => void loadOverview()} disabled={loading || saving}>
                {loading ? "刷新中…" : "刷新数据"}
              </button>
              <button
                className="cm-button cm-button-ghost"
                type="button"
                onClick={() => {
                  const empty: Record<string, string> = {};
                  sourceColumns.forEach((column) => {
                    empty[column.label] = "";
                  });
                  setFormValues(empty);
                  setNotice("");
                }}
                disabled={saving}
              >
                清空表单
              </button>
            </div>

            <div className="cm-entry-grid">
              {rawColumns.map((column) => (
                <label key={column.label} className="cm-entry-field">
                  <span>
                    {displayLabel(column.label)}
                    <em>{unitHint(column.format)}</em>
                  </span>
                  <input
                    type={column.format === "date" ? "date" : "text"}
                    inputMode={column.format === "date" ? undefined : "decimal"}
                    value={formValues[column.label] || ""}
                    placeholder={column.format === "ratio" ? "例如 3.5 表示 3.5%" : column.format === "date" ? "" : "0"}
                    onChange={(event) => handleValueChange(column.label, event.target.value)}
                  />
                </label>
              ))}
            </div>

            {derivedColumns.length ? (
              <div className="cm-derived-block">
                <div className="cm-derived-title">
                  <span>自动计算（无需填写）</span>
                  <em>根据上面填写的原始数据与上月数据实时计算，保存时以后端计算结果为准</em>
                </div>
                <div className="cm-derived-grid">
                  {derivedColumns.map((column) => (
                    <div key={column.label} className="cm-derived-field">
                      <span>{displayLabel(column.label)}</span>
                      <strong>{formatColumnValue(derivedPreview[column.label], column.format)}</strong>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="cm-entry-actions">
              <button className="cm-button" type="button" onClick={() => void submitEntry()} disabled={saving || !sourceColumns.length}>
                {saving ? "保存中…" : loadedMonth ? `覆盖保存 ${monthLabel(formMonth)}` : `保存 ${monthLabel(formMonth)}`}
              </button>
              <span className="cm-hint">百分比列填 3.5 表示 3.5%，会自动换算成小数存储。</span>
            </div>
          </>
        ) : (
          <button className="cm-entry-collapsed" type="button" onClick={() => setEntryOpen(true)}>
            <span>当前月份：{monthLabel(formMonth)}</span>
            <span className="cm-entry-collapsed-hint">点击展开，填写或覆盖 {rawColumns.length} 项原始数据（增长率、客单价自动计算）</span>
          </button>
        )}
      </article>

      <div className="cm-chart-grid">
        <article className="panel">
          <div className="panel-title">
            <div>
              <div className="panel-title-heading"><h3>销售额：公司与美国站市场</h3></div>
              <p>美国站市场销售额与公司订单销售额的月度走势。</p>
            </div>
          </div>
          <EChart option={salesOption} theme={theme === "dark" ? "dark" : undefined} height={260} ariaLabel="销售额公司与美国站市场对比" />
        </article>

        <article className="panel">
          <div className="panel-title">
            <div>
              <div className="panel-title-heading"><h3>销量：公司与美国站市场</h3></div>
              <p>美国站市场销量与公司订单销量的月度走势。</p>
            </div>
          </div>
          <EChart option={volumeOption} theme={theme === "dark" ? "dark" : undefined} height={260} ariaLabel="销量公司与美国站市场对比" />
        </article>

        <article className="panel">
          <div className="panel-title">
            <div>
              <div className="panel-title-heading"><h3>公司占美国站市场比重</h3></div>
              <p>公司订单销售额占美国站市场销售额的比例。</p>
            </div>
          </div>
          <EChart option={shareOption} theme={theme === "dark" ? "dark" : undefined} height={260} ariaLabel="公司占美国站市场比重" />
        </article>

        <article className="panel">
          <div className="panel-title">
            <div>
              <div className="panel-title-heading"><h3>客单价对比</h3></div>
              <p>美国站市场客单价与公司客单价的月度走势。</p>
            </div>
          </div>
          <EChart option={priceOption} theme={theme === "dark" ? "dark" : undefined} height={260} ariaLabel="客单价对比" />
        </article>
      </div>

      <article className="panel cm-history-panel">
        <div className="panel-title">
          <div>
            <div className="panel-title-heading">
              <h3>历史月份</h3>
            </div>
            <p>按录入的全部列展开（共 {sourceColumns.length} 列），可左右滑动查看；日均环比按当月自然日折算销售额后与上月比较。</p>
          </div>
          <span className="panel-tag">{history.length} 个月</span>
        </div>
        <div className="table-scroll cm-history-scroll">
          <table className="compact-table cm-history-table">
            <thead>
              <tr>
                <th className="cm-sticky-col">月份</th>
                {sourceColumns.map((column) => (
                  <th key={column.label}>{displayLabel(column.label)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {history.map((entry) => (
                <tr
                  key={entry.month}
                  className={entry.month === formMonth ? "cm-row-active" : ""}
                >
                  <td className="cm-sticky-col">{monthLabel(entry.month)}</td>
                  {sourceColumns.map((column) => (
                    <td key={column.label}>{formatColumnValue(entry.values?.[column.label], column.format)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
