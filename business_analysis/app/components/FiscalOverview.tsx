"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { EChartsOption } from "echarts";
import EChart from "./EChart";
import { compactMoney, percent } from "../lib/dashboard";
import {
  fetchFiscalOverview,
  type FiscalOverviewPayload,
  type FiscalRankingRow,
} from "../lib/fiscal-overview";

type Theme = "light" | "dark";
type PeriodType = "annual" | "quarter" | "month";

type ProgressTooltipEntry = {
  axisValueLabel?: string;
  dataIndex?: number;
  marker?: string;
  seriesName?: string;
  value?: unknown;
};

const monthLabel = (period: string) => `${Number(period.slice(5, 7))}月`;
const amountLabel = (value: number | null, visible: boolean) =>
  visible ? (value !== null && Number.isFinite(value) ? compactMoney(value) : "—") : "---";
const gapLabel = (value: number | null, visible: boolean, gapRate: number | null = null) => {
  if (!visible) {
    if (gapRate === null) return "—";
    return gapRate <= 0 ? `超额 ${percent(Math.abs(gapRate), 1)}` : `差额 ${percent(gapRate, 1)}`;
  }
  if (value === null) return "—";
  return value <= 0 ? `超额 ${compactMoney(Math.abs(value))}` : `缺口 ${compactMoney(value)}`;
};

const DAY_MS = 24 * 60 * 60 * 1000;

function buildPeriodTimeline(
  start: string | null,
  finalMonth: string | null,
  latestActualDate: string | null,
  completionProgressRate: number | null,
) {
  if (!start || !finalMonth || !latestActualDate || completionProgressRate === null) return null;

  const startMs = Date.parse(`${start}T00:00:00Z`);
  const finalMonthMs = Date.parse(`${finalMonth}T00:00:00Z`);
  const latestExclusiveMs = Date.parse(`${latestActualDate}T00:00:00Z`) + DAY_MS;
  if (![startMs, finalMonthMs, latestExclusiveMs].every(Number.isFinite)) return null;

  const endExclusive = new Date(finalMonthMs);
  endExclusive.setUTCMonth(endExclusive.getUTCMonth() + 1);
  const endExclusiveMs = endExclusive.getTime();
  if (endExclusiveMs <= startMs) return null;

  const clampRate = (value: number) => Math.min(Math.max(value, 0), 1);
  const timeProgress = clampRate((latestExclusiveMs - startMs) / (endExclusiveMs - startMs));
  const completionProgress = clampRate(completionProgressRate);

  return {
    timeProgress,
    completionProgress,
    variance: completionProgress - timeProgress,
    startLabel: start.replaceAll("-", "/"),
    endLabel: new Date(endExclusiveMs - DAY_MS).toISOString().slice(0, 10).replaceAll("-", "/"),
  };
}

function LoadingState() {
  return (
    <div className="fiscal-state" role="status">
      <span className="fiscal-loader" aria-hidden="true" />
      <b>正在读取财年首页</b>
      <small>数据按月缓存，生成后将直接加载</small>
    </div>
  );
}

function DepartmentRankingList({ rows, canViewAmounts, periodLabel, targetProrated }: {
  rows: FiscalRankingRow[];
  canViewAmounts: boolean;
  periodLabel: string;
  targetProrated?: boolean;
}) {
  return (
    <div className="fiscal-department-list" aria-label={`${periodLabel}部门达成率与缺口排名`}>
      <div className="fiscal-department-head"><span>排名</span><span>部门</span><span>达成额</span><span>{targetProrated ? "进度指标" : "指标"}</span><span>达成率</span><span>缺口</span></div>
      <ol>
        {rows.map((row) => (
          <li key={row.key}>
            <span className={`fiscal-rank fiscal-rank-${Math.min(row.rank, 4)}`}>{String(row.rank).padStart(2, "0")}</span>
            <span className="fiscal-department-name"><b>{row.name}</b><small>{row.stores} 家店</small></span>
            <span className="fiscal-department-amount">{amountLabel(row.actual, canViewAmounts)}</span>
            <span className="fiscal-department-amount">{amountLabel(row.ytdTarget, canViewAmounts)}</span>
            <strong className={(row.achievementRate ?? 0) >= 1 ? "is-achieved" : "is-unmet"}>{percent(row.achievementRate, 1)}</strong>
            <span className={(row.gapRate ?? row.gap ?? 0) <= 0 ? "is-ahead" : "is-gap"}>{gapLabel(row.gap, canViewAmounts, row.gapRate)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function StoreRankingGrid({ rows, canViewAmounts }: {
  rows: FiscalRankingRow[];
  canViewAmounts: boolean;
}) {
  const progressScale = Math.max(1, ...rows.map((row) => row.achievementRate ?? 0));
  const goalPosition = Math.min(100 / progressScale, 100);

  return (
    <div className="fiscal-person-list" aria-label="店铺达成率完整排名">
      <div className="fiscal-person-head"><span>排名</span><span>店铺 / 负责人 / 所属部门</span><span>达成进度（标线 100%）</span><span>实际金额</span><span>达成率</span><span>缺口</span></div>
      <ol>
        {rows.map((row) => {
          const progressWidth = Math.min(Math.max(((row.achievementRate ?? 0) / progressScale) * 100, 0), 100);
          return (
            <li key={row.key}>
              <span className={`fiscal-rank fiscal-rank-${Math.min(row.rank, 4)}`}>{String(row.rank).padStart(2, "0")}</span>
              <span className="fiscal-person-name">
                <b>{row.name}</b>
                <small>{row.operator || "未分配负责人"}</small>
                <small>{row.department || "—"}</small>
              </span>
              <span className={`fiscal-person-progress ${(row.achievementRate ?? 0) >= 1 ? "is-achieved" : "is-unmet"}`} aria-label={`${row.name}达成进度 ${percent(row.achievementRate, 1)}，目标线 100%`}>
                <i style={{ width: `${progressWidth}%` }} />
                <em style={{ left: `${goalPosition}%` }} aria-hidden="true" />
              </span>
              <span className="fiscal-person-actual">{amountLabel(row.actual, canViewAmounts)}</span>
              <strong className={(row.achievementRate ?? 0) >= 1 ? "is-achieved" : "is-unmet"}>{percent(row.achievementRate, 1)}</strong>
              <span className={(row.gapRate ?? row.gap ?? 0) <= 0 ? "is-ahead" : "is-gap"}>{gapLabel(row.gap, canViewAmounts, row.gapRate)}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export default function FiscalOverview({ visible, theme }: { visible: boolean; theme: Theme }) {
  const [data, setData] = useState<FiscalOverviewPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [periodType, setPeriodType] = useState<PeriodType>("annual");
  const [periodKey, setPeriodKey] = useState("");
  const requestIdRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const next = await fetchFiscalOverview({
        department: departmentFilter,
        periodType,
        period: periodKey,
      });
      if (requestId === requestIdRef.current) setData(next);
    } catch (reason) {
      if (requestId === requestIdRef.current) {
        setError(reason instanceof Error ? reason.message : "财年首页加载失败");
      }
    } finally {
      if (requestId === requestIdRef.current) setLoading(false);
    }
  }, [departmentFilter, periodKey, periodType]);

  useEffect(() => {
    if (!visible) return;
    const frame = requestAnimationFrame(() => void load());
    return () => cancelAnimationFrame(frame);
  }, [load, visible]);

  const chartColors = theme === "dark"
    ? { text: "#aebbd0", line: "#34435c", target: "#92a8dd", actual: "#6da8ff", accent: "#80a2ff", achieved: "#5ec991", unmet: "#e1b84b" }
    : { text: "#65728a", line: "#e1e7f0", target: "#93a4c5", actual: "#315dc9", accent: "#496fdc", achieved: "#2f9b68", unmet: "#d9a323" };
  const statusColor = (data?.overall.achievementRate ?? 0) >= 1 ? chartColors.achieved : chartColors.unmet;
  const departmentRows = useMemo(() => {
    const rows = data?.departments ?? [];
    if (data?.scope.role !== "member" || !data.scope.operator) return rows;
    return rows.map((row) => ({ ...row, name: data.scope.operator || row.name }));
  }, [data]);

  const progressOption = useMemo<EChartsOption>(() => {
    if (!data?.scope.canViewAmounts) return {};
    return {
      animationDuration: 500,
      color: [chartColors.target, chartColors.accent, statusColor],
      grid: { left: 12, right: 18, top: 26, bottom: 8, containLabel: true },
      legend: { top: 0, right: 8, itemWidth: 14, itemHeight: 6, textStyle: { color: chartColors.text, fontSize: 10 } },
      tooltip: {
        trigger: "axis",
        formatter: (params: unknown) => {
          const entries = (Array.isArray(params) ? params : [params]) as ProgressTooltipEntry[];
          const firstEntry = entries[0];
          if (!firstEntry) return "";

          const row = typeof firstEntry.dataIndex === "number"
            ? data.monthly[firstEntry.dataIndex]
            : null;
          const cumulativeActual = row?.cumulativeActual;
          const cumulativeTarget = row?.cumulativeTarget;
          const completionRate = cumulativeActual !== null
            && cumulativeActual !== undefined
            && cumulativeTarget !== null
            && cumulativeTarget !== undefined
            && Number.isFinite(cumulativeActual)
            && Number.isFinite(cumulativeTarget)
            && cumulativeTarget > 0
            ? cumulativeActual / cumulativeTarget
            : null;
          const amountRows = entries.map((entry) => {
            const rawValue = Array.isArray(entry.value)
              ? entry.value[entry.value.length - 1]
              : entry.value;
            const amount = rawValue === null || rawValue === undefined ? Number.NaN : Number(rawValue);
            const value = Number.isFinite(amount) ? compactMoney(amount) : "—";
            return `${entry.marker ?? ""}${entry.seriesName ?? ""}<span style="float:right;margin-left:24px;font-weight:600">${value}</span>`;
          });

          return [
            `<strong>${firstEntry.axisValueLabel ?? ""}</strong>`,
            ...amountRows,
            `完成占比<span style="float:right;margin-left:24px;font-weight:700">${percent(completionRate, 1)}</span>`,
          ].join("<br/>");
        },
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: data.monthly.map((row) => monthLabel(row.period)),
        axisLine: { lineStyle: { color: chartColors.line } },
        axisTick: { show: false },
        axisLabel: { color: chartColors.text, fontSize: 10 },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: chartColors.text, fontSize: 9, formatter: (value: number) => compactMoney(value) },
        splitLine: { lineStyle: { color: chartColors.line, type: "dashed" } },
      },
      series: [
        {
          name: "月末累计目标",
          type: "line",
          symbol: "none",
          lineStyle: { width: 2, type: "dashed" },
          data: data.monthly.map((row) => row.cumulativeTarget),
        },
        {
          name: "截至当日进度目标",
          type: "line",
          symbol: "diamond",
          symbolSize: 7,
          lineStyle: { width: 2 },
          data: data.monthly.map((row) => row.cumulativeTargetToDate),
        },
        {
          name: "累计实绩",
          type: "line",
          symbol: "circle",
          symbolSize: 6,
          lineStyle: { width: 3 },
          areaStyle: { opacity: 0.08 },
          data: data.monthly.map((row) => row.cumulativeActual),
        },
      ],
    };
  }, [chartColors.accent, chartColors.line, chartColors.target, chartColors.text, data, statusColor]);

  const monthlyRateOption = useMemo<EChartsOption>(() => ({
    animationDuration: 500,
    grid: { left: 8, right: 24, top: 12, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      valueFormatter: (value) => {
        const rate = Number(value);
        return Number.isFinite(rate) ? percent(rate / 100) : "—";
      },
    },
    xAxis: {
      type: "category",
      data: (data?.monthly ?? []).map((row) => monthLabel(row.period)),
      axisLine: { lineStyle: { color: chartColors.line } },
      axisTick: { show: false },
      axisLabel: { color: chartColors.text, fontSize: 10 },
    },
    yAxis: {
      type: "value",
      min: 0,
      axisLabel: { color: chartColors.text, fontSize: 9, formatter: (value: number) => percent(value / 100) },
      splitLine: { lineStyle: { color: chartColors.line, type: "dashed" } },
    },
    series: [{
      type: "bar",
      barMaxWidth: 24,
      label: { show: true, position: "top", color: chartColors.text, fontSize: 9, formatter: (params) => percent(Number(params.value) / 100) },
      markLine: {
        silent: true,
        symbol: "none",
        label: { show: false },
        lineStyle: { color: chartColors.target, type: "dashed", width: 1 },
        data: [{ yAxis: 100 }],
      },
      data: (data?.monthly ?? []).map((row) => row.achievementRate === null ? null : ({
        value: row.achievementRate * 100,
        itemStyle: {
          color: row.achievementRate >= 1 ? chartColors.achieved : chartColors.unmet,
          borderRadius: [4, 4, 0, 0],
        },
      })),
    }],
  }), [chartColors.achieved, chartColors.line, chartColors.target, chartColors.text, chartColors.unmet, data]);

  const monthlyAmountOption = useMemo<EChartsOption>(() => {
    const month = data?.monthly[0];
    const comparison = month
      ? data?.filters.periodType === "month"
        ? [
            { label: "整月总指标", value: month.target, color: chartColors.target },
            { label: "当月已完成", value: month.actual, color: statusColor },
          ]
        : [
            { label: "完整月指标", value: month.target, color: chartColors.target },
            ...(data?.period.targetProrated
              ? [{ label: "截至当日进度指标", value: month.targetToDate, color: chartColors.accent }]
              : []),
            { label: "实际完成", value: month.actual, color: statusColor },
          ]
      : [];
    return {
      animationDuration: 500,
      grid: { left: 8, right: 24, top: 18, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        valueFormatter: (value) => {
          const amount = Number(value);
          return Number.isFinite(amount) ? compactMoney(amount) : "—";
        },
      },
      xAxis: {
        type: "category",
        data: comparison.map((item) => item.label),
        axisLine: { lineStyle: { color: chartColors.line } },
        axisTick: { show: false },
        axisLabel: { color: chartColors.text, fontSize: 10, interval: 0 },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: chartColors.text, fontSize: 9, formatter: (value: number) => compactMoney(value) },
        splitLine: { lineStyle: { color: chartColors.line, type: "dashed" } },
      },
      series: [{
        type: "bar",
        barMaxWidth: 44,
        label: {
          show: true,
          position: "top",
          color: chartColors.text,
          fontSize: 10,
          formatter: (params) => compactMoney(Number(params.value)),
        },
        data: comparison.map((item) => ({
          value: item.value,
          itemStyle: { color: item.color, borderRadius: [5, 5, 0, 0] },
        })),
      }],
    };
  }, [chartColors.accent, chartColors.line, chartColors.target, chartColors.text, data, statusColor]);

  const departmentOption = useMemo<EChartsOption>(() => {
    const rows = [...departmentRows].reverse();
    return {
      animationDuration: 500,
      grid: { left: 8, right: 52, top: 8, bottom: 8, containLabel: true },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value) => percent(Number(value) / 100) },
      xAxis: {
        type: "value",
        max: (value: { max: number }) => Math.max(110, Math.ceil(value.max / 10) * 10),
        axisLabel: { show: false },
        splitLine: { lineStyle: { color: chartColors.line, type: "dashed" } },
      },
      yAxis: {
        type: "category",
        data: rows.map((row) => row.name),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: chartColors.text, fontSize: 10 },
      },
      series: [{
        type: "bar",
        barWidth: 12,
        label: { show: true, position: "right", color: chartColors.text, fontSize: 10, formatter: (params) => percent(Number(params.value) / 100) },
        markLine: {
          silent: true,
          symbol: "none",
          label: { show: false },
          lineStyle: { color: chartColors.target, type: "dashed", width: 1 },
          data: [{ xAxis: 100 }],
        },
        data: rows.map((row) => ({
          value: row.achievementRate === null ? 0 : row.achievementRate * 100,
          itemStyle: {
            color: (row.achievementRate ?? 0) >= 1 ? chartColors.achieved : chartColors.unmet,
            borderRadius: [0, 4, 4, 0],
          },
        })),
      }],
    };
  }, [chartColors.achieved, chartColors.line, chartColors.target, chartColors.text, chartColors.unmet, departmentRows]);

  const departmentGapOption = useMemo<EChartsOption>(() => {
    const rows = [...departmentRows]
      .sort((left, right) => (right.gap ?? 0) - (left.gap ?? 0))
      .reverse();
    return {
      animationDuration: 500,
      grid: { left: 8, right: 70, top: 8, bottom: 22, containLabel: true },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        valueFormatter: (value) => gapLabel(Number(value), true),
      },
      xAxis: {
        type: "value",
        axisLine: { show: true, lineStyle: { color: chartColors.line } },
        axisTick: { show: false },
        axisLabel: { color: chartColors.text, fontSize: 8, formatter: (value: number) => compactMoney(value) },
        splitLine: { lineStyle: { color: chartColors.line, type: "dashed" } },
      },
      yAxis: {
        type: "category",
        data: rows.map((row) => row.name),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: chartColors.text, fontSize: 10 },
      },
      series: [{
        type: "bar",
        barWidth: 12,
        label: {
          show: true,
          position: "right",
          color: chartColors.text,
          fontSize: 9,
          formatter: (params) => gapLabel(Number(params.value), true),
        },
        markLine: {
          silent: true,
          symbol: "none",
          label: { show: false },
          lineStyle: { color: chartColors.text, width: 1 },
          data: [{ xAxis: 0 }],
        },
        data: rows.map((row) => ({
          value: row.gap ?? 0,
          itemStyle: {
            color: (row.gap ?? 0) <= 0 ? chartColors.achieved : chartColors.unmet,
            borderRadius: (row.gap ?? 0) <= 0 ? [4, 0, 0, 4] : [0, 4, 4, 0],
          },
        })),
      }],
    };
  }, [chartColors.achieved, chartColors.line, chartColors.text, chartColors.unmet, departmentRows]);

  if (!data && loading) return <LoadingState />;
  if (!data && error) {
    return (
      <div className="fiscal-state fiscal-state-error" role="alert">
        <b>财年首页暂时无法读取</b>
        <small>{error}</small>
        <button type="button" onClick={() => void load()}>重新加载</button>
      </div>
    );
  }
  if (!data) return null;

  const canViewAmounts = data.scope.canViewAmounts;
  const storeRows = data.stores ?? [];
  const isMonthView = data.filters.periodType === "month";
  const usesProratedTarget = data.period.targetProrated && !isMonthView;
  const rankingRateLabel = isMonthView ? "完成率" : `${usesProratedTarget ? "进度" : ""}达成率`;
  const latest = data.period.latestActualDate ?? "暂无实绩";
  const latestMonth = data.period.latestActualDate
    ? `${data.period.latestActualDate.slice(0, 4)}年${Number(data.period.latestActualDate.slice(5, 7))}月`
    : "当前月份";
  const targetProgressNote = isMonthView
    ? "完成占比 = 当月实绩 ÷ 整月指标，不按数据日折算"
    : usesProratedTarget
      ? `当前月指标按数据日折算：${data.period.targetElapsedDays}/${data.period.targetMonthDays} 天`
      : "当前筛选周期使用完整指标";
  const cumulativePeriodLabel = data.filters.periodType === "annual"
    ? `截至 ${usesProratedTarget ? latest : latestMonth} 累计`
    : data.filters.periodLabel;
  const selectedDepartmentLabel = data.filters.department || (data.filters.departments.length > 1 ? "全部部门" : data.filters.departments[0] || "权限范围");
  const scopeDisplayLabel = data.scope.role === "member" && data.scope.operator
    ? data.scope.operator
    : selectedDepartmentLabel;
  const isMemberScope = data.scope.role === "member";
  const scopeMetricLabel = isMemberScope ? scopeDisplayLabel : "部门";
  const canFilterDepartments = data.filters.departments.length > 1;
  const selectedPeriodValue = periodKey || (data.filters.periodType === periodType ? data.filters.period : "");
  const periodName = data.filters.periodType === "annual"
    ? "财年"
    : data.filters.periodType === "quarter" ? "季度" : "月度";
  const mainTargetLabel = data.filters.periodType === "annual"
    ? "财年总目标"
    : data.filters.periodType === "quarter"
      ? `${data.filters.periodLabel.split(" · ")[0]}整季指标`
      : `${data.filters.periodLabel}整月指标`;
  const timeline = buildPeriodTimeline(
    data.period.start,
    data.period.end,
    data.period.latestActualDate,
    data.overall.periodCompletionRate,
  );

  return (
    <div className="fiscal-overview">
      <div className="fiscal-heading">
        <div>
          <span className="eyebrow">Fiscal command center</span>
          <h1>2026-2027 财年目标总览</h1>
          <p>{scopeDisplayLabel} · {cumulativePeriodLabel} · {targetProgressNote}；数据日期 {latest}</p>
        </div>
        <div className="fiscal-heading-visual">
          <span className="fiscal-cache-badge">{loading ? "筛选计算中" : "按月缓存 · 自动更新"}</span>
        </div>
      </div>

      <div className="fiscal-home-filters" aria-label="首页数据筛选">
        <label className="fiscal-filter-field">
          <span>部门</span>
          <select
            value={departmentFilter}
            disabled={!canFilterDepartments || loading}
            onChange={(event) => setDepartmentFilter(event.target.value)}
          >
            <option value="">{canFilterDepartments ? "全部部门" : selectedDepartmentLabel}</option>
            {canFilterDepartments ? data.filters.departments.map((department) => (
              <option key={department} value={department}>{department}</option>
            )) : null}
          </select>
        </label>

        <div className="fiscal-period-filter">
          <span>统计周期</span>
          <div className="fiscal-period-tabs" role="group" aria-label="年度季度月度筛选">
            {([
              ["annual", "年度"],
              ["quarter", "季度"],
              ["month", "月度"],
            ] as Array<[PeriodType, string]>).map(([value, label]) => (
              <button
                type="button"
                key={value}
                className={periodType === value ? "active" : ""}
                disabled={loading}
                aria-pressed={periodType === value}
                onClick={() => {
                  setPeriodType(value);
                  setPeriodKey("");
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {periodType !== "annual" ? (
          <label className="fiscal-filter-field fiscal-filter-period-value">
            <span>{periodType === "quarter" ? "财年季度" : "月份"}</span>
            <select value={selectedPeriodValue} disabled={loading} onChange={(event) => setPeriodKey(event.target.value)}>
              {data.filters.periodOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
        ) : null}

        <div className="fiscal-status-legend" aria-label="达标状态颜色说明">
          <span><i className="is-achieved" />达标 ≥ 100.00%</span>
          <span><i className="is-unmet" />未达标 &lt; 100.00%</span>
        </div>
      </div>

      <div className="fiscal-kpis">
        <article className="fiscal-kpi fiscal-kpi-main">
          <span>{canViewAmounts ? mainTargetLabel : "目标基准"}</span>
          <strong>{canViewAmounts ? amountLabel(data.overall.periodTarget, true) : "100.00%"}</strong>
          <small>{scopeDisplayLabel} · 完整{periodName}目标基准</small>
        </article>
        <article className="fiscal-kpi"><span>{canViewAmounts ? `${cumulativePeriodLabel}实绩` : "公司财年达成率"}</span><strong>{canViewAmounts ? amountLabel(data.overall.actual, true) : percent(data.overall.companyFiscalAchievementRate ?? data.overall.annualProgressRate, 1)}</strong><small>{canViewAmounts ? undefined : "财年累计实绩 ÷ 公司全年目标"}</small></article>
        <article className={`fiscal-kpi${(data.overall.gapRate ?? data.overall.gap ?? 0) <= 0 ? " is-ahead" : " is-gap"}`}><span>{canViewAmounts ? `${cumulativePeriodLabel}${usesProratedTarget ? "进度缺口" : "缺口"}` : "目标差额占比"}</span><strong>{gapLabel(data.overall.gap, canViewAmounts, data.overall.gapRate)}</strong></article>
        <article className="fiscal-kpi"><span>{canViewAmounts ? "距年度目标" : "年度目标剩余占比"}</span><strong>{canViewAmounts ? amountLabel(data.overall.remainingToAnnual, true) : percent(data.overall.remainingRate, 1)}</strong><small>财年累计完成进度 {percent(data.overall.annualProgressRate, 1)}</small></article>
      </div>

      {timeline ? (
        <section className="fiscal-timeline-panel" aria-label={`${periodName}目标完成进度与时间进度对比`}>
          <div className="fiscal-timeline-head">
            <div>
              <span className="eyebrow">Fiscal timeline</span>
              <h2>{periodName}时间与目标完成对比</h2>
              <p>两条进度线采用相同的 0.00–100.00% 刻度，可直接判断目标完成是否跟上时间进度</p>
            </div>
            <span className={`fiscal-timeline-status ${timeline.variance >= 0 ? "is-ahead" : "is-behind"}`}>
              目标进度{timeline.variance >= 0 ? "领先" : "落后"} {Math.abs(timeline.variance * 100).toFixed(2)} 个百分点
            </span>
          </div>

          <div className="fiscal-progress-compare">
            <div className="fiscal-progress-row is-time">
              <div>
                <span><b>{periodName}时间进度</b><small>{timeline.startLabel} — {timeline.endLabel} · 数据日 {latest}</small></span>
                <strong>{percent(timeline.timeProgress, 1)}</strong>
              </div>
              <span className="fiscal-progress-bar">
                <i style={{ width: `${timeline.timeProgress * 100}%` }} />
                <em style={{ left: `${Math.min(Math.max(timeline.timeProgress * 100, 0.8), 99.2)}%` }} aria-hidden="true" />
              </span>
            </div>
            <div className="fiscal-progress-row is-target">
              <div>
                <span><b>目标完成进度</b><small>{periodName}实绩 ÷ 完整{periodName}目标</small></span>
                <strong>{percent(timeline.completionProgress, 1)}</strong>
              </div>
              <span className="fiscal-progress-bar"><i style={{ width: `${timeline.completionProgress * 100}%` }} /></span>
            </div>
          </div>
        </section>
      ) : null}

      <div className="fiscal-chart-grid">
        {canViewAmounts && data.monthly.length > 1 ? (
          <article className="fiscal-panel fiscal-panel-wide">
            <div className="fiscal-panel-title"><div><h2>{data.filters.periodType === "annual" ? "财年" : "季度"}累计进度</h2><p>{cumulativePeriodLabel}；月末目标与截至当日进度目标分开展示</p></div><span>单位：人民币</span></div>
            <EChart option={progressOption} theme={theme} height={286} ariaLabel={`${data.filters.periodLabel}累计目标与累计实绩折线图`} />
          </article>
        ) : canViewAmounts ? (
          <article className="fiscal-panel fiscal-panel-wide">
            <div className="fiscal-panel-title"><div><h2>{isMonthView ? `${data.filters.periodLabel}完成进度` : `${data.filters.periodLabel}整体指标与完成`}</h2><p>{isMonthView ? `整月总指标 ${amountLabel(data.overall.periodTarget, true)} · 当月已完成 ${amountLabel(data.overall.actual, true)}` : data.period.targetProrated ? "完整月指标、截至数据日进度指标与实绩对照" : "完整月指标与月末实绩对照"}</p></div><span>{isMonthView ? `完成占比 ${percent(data.overall.periodCompletionRate, 1)}` : "单位：人民币"}</span></div>
            <EChart option={monthlyAmountOption} theme={theme} height={286} ariaLabel={isMonthView ? `${data.filters.periodLabel}整月指标与已完成金额对比柱状图` : `${data.filters.periodLabel}完整月指标、进度指标与实绩对照柱状图`} />
          </article>
        ) : (
          <article className="fiscal-panel fiscal-panel-wide">
            <div className="fiscal-panel-title"><div><h2>{data.filters.periodLabel}{isMonthView ? "完成进度" : "进度达成率"}</h2><p>{isMonthView ? "完成占比 = 当月实绩 ÷ 整月指标，不按数据日折算；金额按权限隐藏" : "金额按权限隐藏；实绩与进度指标采用同一口径"}</p></div><span>{isMonthView ? `完成占比 ${percent(data.overall.periodCompletionRate, 1)}` : "绿色达标 · 黄色未达标"}</span></div>
            <EChart option={monthlyRateOption} theme={theme} height={286} ariaLabel={`${data.filters.periodLabel}${isMonthView ? "整月完成占比" : "进度达成率"}柱状图`} />
          </article>
        )}
        <article className="fiscal-panel">
          <div className="fiscal-panel-title"><div><h2>{cumulativePeriodLabel}{scopeMetricLabel}{rankingRateLabel}</h2><p>{isMemberScope ? "本人指标" : `按${rankingRateLabel}从高到低`} · {targetProgressNote}</p></div><span>绿色达标 · 黄色未达标</span></div>
          <EChart option={departmentOption} theme={theme} height={286} ariaLabel={`${data.filters.periodLabel}${scopeMetricLabel}达成率条形图`} />
        </article>
      </div>

      <div className="fiscal-ranking-grid">
        <article className="fiscal-panel fiscal-department-panel">
          <div className="fiscal-panel-title"><div><h2>{scopeMetricLabel}{rankingRateLabel}与缺口</h2><p>{cumulativePeriodLabel} · {targetProgressNote}</p></div><span>{isMemberScope ? scopeDisplayLabel : `${departmentRows.length} 个部门`}</span></div>
          <div className="fiscal-department-content">
            <div className="fiscal-ranking-table">
              <div className="fiscal-detail-label"><b>{isMemberScope ? "个人指标明细" : "部门明细表"}</b><span>达成率与缺口完整数据</span></div>
              <DepartmentRankingList rows={departmentRows} canViewAmounts={canViewAmounts} periodLabel={cumulativePeriodLabel} targetProrated={usesProratedTarget} />
            </div>
            <div className="fiscal-ranking-chart">
              <div className="fiscal-detail-label"><b>{canViewAmounts ? `${scopeMetricLabel}${isMonthView ? "月度" : usesProratedTarget ? "进度" : "累计"}缺口` : `${scopeMetricLabel}${rankingRateLabel}`}</b><span>{canViewAmounts ? "正值为缺口，负值为超额" : "金额按权限隐藏"}</span></div>
              <EChart
                option={canViewAmounts ? departmentGapOption : departmentOption}
                theme={theme}
                height={246}
                ariaLabel={canViewAmounts ? `${scopeMetricLabel}累计缺口横向条形图` : `${scopeMetricLabel}累计达成率横向条形图`}
              />
            </div>
          </div>
        </article>
        <article className="fiscal-panel">
          <div className="fiscal-panel-title"><div><h2>店铺{rankingRateLabel}与缺口</h2><p>{cumulativePeriodLabel} · {targetProgressNote}</p></div><span>{storeRows.length} 家店铺</span></div>
          <div className="fiscal-detail-label fiscal-person-table-label"><b>店铺完整明细表</b><span>{storeRows.length} 家店铺全部展开</span></div>
          <StoreRankingGrid rows={storeRows} canViewAmounts={canViewAmounts} />
        </article>
      </div>
    </div>
  );
}
