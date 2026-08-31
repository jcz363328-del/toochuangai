import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  ArrowsClockwise,
  Buildings,
  CalendarBlank,
  CaretDown,
  ChartBar,
  CheckCircle,
  Flag,
  FunnelSimple,
  Info,
  MagnifyingGlass,
  Package,
  PauseCircle,
  ShieldCheck,
  Target,
} from "@phosphor-icons/react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  LISTING_STAGE,
  aggregateCampaignLifecycles,
  campaignLifecycleFor,
  listingStageLabel,
  listingStageMatches,
  normalizeListingStage,
  productListingStage,
} from "./listingLifecycle.js";
import { AdDiagnosticView } from "./AdDiagnosticView.jsx";
import { fetchDiagnosticShops } from "./adDiagnosticApi.js";
import { DIAGNOSTIC_SHOPS, PILOT_SHOP, normalizeDiagnosticShops } from "./adDiagnosticModel.js";

const APP_BASE_URL = import.meta.env?.BASE_URL || "/";
const DATA_URL = `${APP_BASE_URL}data/ads-monitor.json`;
const REALTIME_DATA_URL = `${APP_BASE_URL}data/ads-realtime.json`;
const REVIEW_KEY = "sellfox-ads-review-state-v1";
const ALL_SHOPS = "__all_shops__";
const UNKNOWN_CURRENCY = "";
const RECOMMENDATIONS_PER_PAGE = 10;
const ALERTS_PER_PAGE = 10;
const SKUS_PER_PAGE = 10;
const CAMPAIGNS_PER_PAGE = 10;
const REVIEWABLE_ACTIONS = new Set(["DECREASE_BID", "INCREASE_BID", "INCREASE_BUDGET", "REVIEW_TARGET"]);

const NAV_ITEMS = [
  { id: "diagnostic", label: "单店诊断" },
  { id: "recommendations", label: "调控建议" },
  { id: "realtime", label: "实时异常" },
  { id: "rules", label: "推荐规则" },
  { id: "campaigns", label: "活动概览" },
  { id: "performance", label: "数据表现" },
];

const FILTERS = [
  { id: "all", label: "全部" },
  { id: "high", label: "高优先级" },
  { id: "pending", label: "待审核" },
];

const ALERT_FILTERS = [
  { id: "all", label: "全部" },
  { id: "high", label: "高风险" },
  { id: "warning", label: "预警" },
  { id: "info", label: "提示" },
];

const CAMPAIGN_LISTING_FILTERS = [
  { id: LISTING_STAGE.ALL, label: "全部上架阶段" },
  { id: LISTING_STAGE.NEW, label: "新上架" },
  { id: LISTING_STAGE.ESTABLISHED, label: "非新品" },
  { id: LISTING_STAGE.MIXED, label: "混合" },
  { id: LISTING_STAGE.UNKNOWN, label: "未知" },
];

const SKU_LISTING_FILTERS = CAMPAIGN_LISTING_FILTERS.filter((item) => item.id !== LISTING_STAGE.MIXED);

function number(value, digits = 2) {
  return Number(value || 0).toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function percentage(value) {
  if (value === "" || value == null) return "—";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function compactDate(value) {
  const [, month, day] = String(value || "").split("-");
  return month && day ? `${Number(month)}月${Number(day)}日` : value;
}

function dateTime(value) {
  if (!value) return "尚未采集";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value).replace("T", " ").slice(0, 16);
  return parsed.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function ratioText(covered, eligible) {
  const safeCovered = Number(covered || 0);
  const safeEligible = Number(eligible || 0);
  if (!safeEligible) return `${number(safeCovered, 0)} / 待确认`;
  return `${number(safeCovered, 0)} / ${number(safeEligible, 0)}（${Math.round((safeCovered / safeEligible) * 100)}%）`;
}

function freshnessState(meta) {
  const explicit = String(meta?.status || "").toLowerCase();
  if (explicit === "not_applicable") return "not_applicable";
  if (["missing", "not_collected", "unavailable", "error", "failed"].includes(explicit)) return "missing";
  if (["stale", "expired"].includes(explicit)) return "stale";
  const expiresTime = Date.parse(meta?.expires_at || "");
  if (expiresTime && Date.now() > expiresTime) return "stale";
  if (explicit === "complete") return "complete";
  if (["partial", "degraded", "collecting"].includes(explicit)) return "partial";
  const observedAt = meta?.observed_at || meta?.generated_at;
  const observedTime = Date.parse(observedAt || "");
  const staleMinutes = Number(meta?.stale_after_minutes || 0);
  if (observedTime && staleMinutes && Date.now() - observedTime > staleMinutes * 60 * 1000) return "stale";
  const coveredShops = Number(meta?.covered_shops || 0);
  const eligibleShops = Number(meta?.eligible_shops || 0);
  const coveredCampaigns = Number(meta?.covered_campaigns || 0);
  const eligibleCampaigns = Number(meta?.eligible_campaigns || 0);
  if ((eligibleShops && coveredShops < eligibleShops)
    || (eligibleCampaigns && coveredCampaigns < eligibleCampaigns)
    || Number(meta?.failed_calls || 0) > 0
    || Number(meta?.quality_failures || 0) > 0) return "partial";
  return observedAt ? "complete" : "missing";
}

function severityClass(severity) {
  const value = String(severity || "").toLowerCase();
  if (["critical", "high", "error", "danger"].includes(value)) return "high";
  if (["medium", "warning", "warn"].includes(value)) return "warning";
  return "info";
}

function severityLabel(severity) {
  const level = severityClass(severity);
  return level === "high" ? "高风险" : level === "warning" ? "预警" : "提示";
}

function metricLabel(metric) {
  const labels = {
    acos: "ACoS",
    budget_utilization: "预算使用率",
    cpc: "CPC",
    ctr: "CTR",
    cvr: "CVR",
    clicks: "点击",
    impressions: "曝光",
    orders: "订单",
    projected_spend: "预计全天花费",
    sales: "销售额",
    spend: "花费",
    spend_pace: "花费进度",
    freshness: "实时新鲜度",
  };
  const key = String(metric || "").toLowerCase();
  return labels[key] || metric || "监控指标";
}

function alertMetricValue(alert, key) {
  const value = alert?.[key];
  if (value === "" || value == null) return "—";
  const metric = String(alert?.metric || "").toLowerCase();
  if (metric === "freshness") {
    const labels = { fresh: "新鲜", stale: "已过期", error: "读取失败", never: "尚未采集", empty: "暂无活动行" };
    return labels[String(value).toLowerCase()] || String(value);
  }
  if (["acos", "budget_utilization", "ctr", "cvr", "spend_pace"].includes(metric)) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? `${(Math.abs(numeric) <= 2 ? numeric * 100 : numeric).toFixed(1)}%` : String(value);
  }
  if (["cpc", "projected_spend", "sales", "spend"].includes(metric)) return money(value, currencyOf(alert));
  const numeric = Number(value);
  return Number.isFinite(numeric) ? number(value, Number.isInteger(numeric) ? 0 : 2) : String(value);
}

function handlingLabel(value) {
  return {
    BLOCK: "阻断执行确认",
    WARN: "预警并人工复核",
    WATCH: "继续观察",
  }[String(value || "").toUpperCase()] || "先观察并复核成熟数据";
}

function deviationText(value) {
  if (value === "" || value == null) return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  const normalized = Math.abs(numeric) <= 2 ? numeric * 100 : numeric;
  return `${normalized > 0 ? "+" : ""}${normalized.toFixed(1)}%`;
}

function shopIdOf(item) {
  return String(item?.shop_id || item?.shopId || item?.store_id || item?.storeId || "").trim();
}

function currencyOf(item) {
  return String(item?.currency || item?.currency_code || item?.currencyCode || "").trim().toUpperCase();
}

function currencyLabel(currency) {
  return currency || "币种未知";
}

function money(value, currency, digits = 2) {
  if (value === "" || value == null) return "—";
  return `${currencyLabel(currency)} ${number(value, digits)}`;
}

function rowsOf(value) {
  if (Array.isArray(value)) return value;
  return value && typeof value === "object" ? Object.values(value) : [];
}

function shopRowsOf(value) {
  if (Array.isArray(value)) return value;
  if (!value || typeof value !== "object") return [];
  return Object.entries(value).map(([id, item]) => (
    item && typeof item === "object" ? { id, ...item } : { id, name: String(item || id) }
  ));
}

function recommendationKey(item) {
  return `${shopIdOf(item) || "unknown"}::${item?.entity_key || item?.target_id || item?.campaign_id || "unknown"}`;
}

function recommendationRealtimeGate(realtime, recommendation, loadStatus) {
  if (!isReviewableAction(recommendation)) return { gate: "MONITOR_ONLY", snapshot: null };
  if (!realtime || loadStatus !== "ready") return { gate: "BLOCK", snapshot: null };
  const snapshot = realtime.campaign_snapshots.find(
    (item) => shopIdOf(item) === shopIdOf(recommendation)
      && String(item.campaign_id) === String(recommendation.campaign_id),
  );
  return { gate: snapshot?.execution_gate || "BLOCK", snapshot: snapshot || null };
}

function shopNameFor(shops, item) {
  const id = shopIdOf(item);
  if (!id) return "";
  return shops.find((shop) => shop.id === id)?.name || item.shop_name || id;
}

function shopCurrencyFor(shops, item) {
  const id = shopIdOf(item);
  return shops.find((shop) => shop.id === id)?.currency || currencyOf(item);
}

function reviewValue(reviewState, item) {
  return reviewState[recommendationKey(item)] ?? reviewState[item?.entity_key];
}

function shopOptions(data) {
  if (!data) return [];
  const records = new Map();
  const add = (item, priority, allowGenericId = false) => {
    const id = shopIdOf(item) || (allowGenericId ? String(item?.id || "").trim() : "");
    if (!id) return;
    const name = String(item.shop_name || item.shopName || (allowGenericId ? item.name : "") || "").trim();
    const currency = currencyOf(item);
    const current = records.get(id) || { id, name: id, currency: UNKNOWN_CURRENCY, namePriority: -1, currencyPriority: -1 };
    if (name && priority >= current.namePriority) {
      current.name = name;
      current.namePriority = priority;
    }
    if (currency && priority >= current.currencyPriority) {
      current.currency = currency;
      current.currencyPriority = priority;
    }
    records.set(id, current);
  };
  shopRowsOf(data.shops).forEach((item) => add(item, 5, true));
  rowsOf(data.advertised_products).forEach((item) => add(item, 5));
  rowsOf(data.campaigns).forEach((item) => add(item, 4));
  rowsOf(data.recommendations).forEach((item) => add(item, 3));
  rowsOf(data.rules).forEach((item) => add(item, 2));
  rowsOf(data.campaign_daily_trend).forEach((item) => add(item, 1));
  rowsOf(data.source_data).forEach((item) => add(item, 0));
  rowsOf(data.daily_trend).forEach((item) => add(item, 0));
  return [...records.values()]
    .map(({ id, name, currency }) => ({ id, name, currency }))
    .sort((a, b) => a.name.localeCompare(b.name, "zh-CN"));
}

function aggregateTrend(rows, dateField) {
  const grouped = rows.reduce((result, row) => {
    const date = row[dateField];
    if (!date) return result;
    result[date] ||= { date, spend: 0, sales: 0, orders: 0 };
    result[date].spend += Number(row.spend || 0);
    result[date].sales += Number(row.sales || 0);
    result[date].orders += Number(row.orders || 0);
    return result;
  }, {});
  return Object.values(grouped).sort((a, b) => a.date.localeCompare(b.date));
}

function scopedTrend(data, selectedShop, storeCount, scopedSource, scopedCampaignTrend) {
  const dailyRows = data.daily_trend || [];
  const dailyHasShop = dailyRows.some((row) => shopIdOf(row));
  if (dailyHasShop) {
    const rows = selectedShop === ALL_SHOPS
      ? dailyRows
      : dailyRows.filter((row) => shopIdOf(row) === selectedShop);
    return aggregateTrend(rows, "date");
  }

  const campaignDailyTrend = aggregateTrend(scopedCampaignTrend, "date");
  if (campaignDailyTrend.length) return campaignDailyTrend;

  const campaignRows = scopedSource.filter((row) => row.aggregation_type === "campaign");
  const sourceTrend = aggregateTrend(campaignRows, "report_date");
  if (selectedShop !== ALL_SHOPS && sourceTrend.length) return sourceTrend;
  if (selectedShop === ALL_SHOPS && dailyRows.length) return aggregateTrend(dailyRows, "date");
  if (sourceTrend.length) return sourceTrend;
  return storeCount <= 1 ? aggregateTrend(dailyRows, "date") : [];
}

function scopeData(data, selectedShop, storeCount) {
  if (!data) return null;
  const includes = (item) => selectedShop === ALL_SHOPS || shopIdOf(item) === selectedShop;
  const sourceData = (data.source_data || []).filter(includes);
  const campaignDailyTrend = (data.campaign_daily_trend || []).filter(includes);
  return {
    ...data,
    campaigns: (data.campaigns || []).filter(includes),
    recommendations: (data.recommendations || []).filter(includes),
    advertised_products: (data.advertised_products || []).filter(includes),
    source_data: sourceData,
    campaign_daily_trend: campaignDailyTrend,
    daily_trend: scopedTrend(data, selectedShop, storeCount, sourceData, campaignDailyTrend),
  };
}

function normalizeRealtime(payload) {
  const value = payload && typeof payload === "object" ? payload : {};
  return {
    ...value,
    meta: value.meta || value.realtime_meta || {},
    alerts: rowsOf(value.alerts || value.realtime_alerts),
    shop_coverage: rowsOf(value.shop_coverage || value.realtime_shop_coverage),
    campaign_snapshots: rowsOf(value.campaign_snapshots),
  };
}

function coverageCount(row, field, fallbackField) {
  return Number(row?.[field] ?? row?.[fallbackField] ?? 0);
}

function scopeRealtime(realtime, selectedShop) {
  if (!realtime) return null;
  const includes = (item) => selectedShop === ALL_SHOPS || shopIdOf(item) === selectedShop;
  const alerts = realtime.alerts.filter(includes);
  const snapshots = realtime.campaign_snapshots.filter(includes);
  if (selectedShop === ALL_SHOPS) return { ...realtime, alerts, campaign_snapshots: snapshots };

  const coverage = realtime.shop_coverage.find((item) => shopIdOf(item) === selectedShop);
  const inferredCampaigns = new Set(snapshots.map((item) => item.campaign_id).filter(Boolean)).size;
  const observedAt = coverage?.observed_at || snapshots
    .map((item) => item.observed_at)
    .filter(Boolean)
    .sort()
    .at(-1);
  return {
    ...realtime,
    meta: {
      ...realtime.meta,
      status: coverage?.status || coverage?.coverage_status || (snapshots.length ? "partial" : "missing"),
      observed_at: observedAt || realtime.meta.observed_at,
      covered_shops: coverage || snapshots.length ? 1 : 0,
      eligible_shops: 1,
      covered_campaigns: coverageCount(coverage, "covered_campaigns", "campaigns_covered") || inferredCampaigns,
      eligible_campaigns: coverageCount(coverage, "eligible_campaigns", "campaigns_total"),
      successful_calls: coverageCount(coverage, "successful_calls", "success_calls"),
      failed_calls: coverageCount(coverage, "failed_calls", "failure_calls"),
      quality_failures: coverageCount(coverage, "quality_failures", "invalid_rows"),
    },
    alerts,
    campaign_snapshots: snapshots,
    shop_coverage: coverage ? [coverage] : [],
  };
}

function getStoredReviewState() {
  try {
    return JSON.parse(localStorage.getItem(REVIEW_KEY) || "{}");
  } catch {
    return {};
  }
}

function priorityClass(priority) {
  return priority === "高" ? "high" : priority === "中" ? "medium" : "low";
}

function actionClass(action) {
  return action === "DECREASE_BID"
    ? "decrease"
    : action === "INCREASE_BID" || action === "INCREASE_BUDGET"
      ? "increase"
      : "hold";
}

function isReviewableAction(item) {
  return REVIEWABLE_ACTIONS.has(item?.action_code);
}

function ListingStageBadge({ lifecycle, compact = false }) {
  const stage = lifecycle?.stage || LISTING_STAGE.UNKNOWN;
  const count = Number(lifecycle?.total || 0);
  return (
    <span className={`listing-stage-badge ${stage} ${compact ? "compact" : ""}`}>
      {listingStageLabel(stage)}{!compact && count ? ` · ${count} 位置` : ""}
    </span>
  );
}

function ListingStageSelect({ value, onChange, options = CAMPAIGN_LISTING_FILTERS, label = "上架阶段" }) {
  return (
    <label className="listing-stage-select">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} aria-label={label}>
        {options.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
      </select>
      <CaretDown size={15} aria-hidden="true" />
    </label>
  );
}

function mappingStatusLabel(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) return "未知";
  if (normalized === "matched" || normalized.startsWith("matched_")) return "已匹配";
  if (normalized.includes("ambiguous")) return "匹配冲突";
  if (normalized.includes("not_found") || normalized.includes("unmatched")) return "未匹配";
  return value;
}

function paginationItems(currentPage, pageCount) {
  if (pageCount <= 7) return Array.from({ length: pageCount }, (_, index) => index + 1);
  const items = [1];
  if (currentPage > 3) items.push("left-ellipsis");
  for (let page = Math.max(2, currentPage - 1); page <= Math.min(pageCount - 1, currentPage + 1); page += 1) {
    items.push(page);
  }
  if (currentPage < pageCount - 2) items.push("right-ellipsis");
  items.push(pageCount);
  return items;
}

function campaignTrend(recommendation, campaignDailyTrend, sourceData) {
  const preferredRows = campaignDailyTrend.filter(
    (row) => row.campaign_id === recommendation.campaign_id
      && (!shopIdOf(recommendation) || shopIdOf(row) === shopIdOf(recommendation)),
  );
  if (preferredRows.length) {
    return aggregateTrend(preferredRows, "date").map((row) => ({ ...row, date: row.date.slice(5) }));
  }
  const rows = sourceData.filter(
    (row) => row.aggregation_type === "campaign"
      && row.campaign_id === recommendation.campaign_id
      && (!shopIdOf(recommendation) || shopIdOf(row) === shopIdOf(recommendation)),
  );
  if (!rows.length) {
    return [];
  }
  const byDate = rows.reduce((result, row) => {
    result[row.report_date] ||= { date: row.report_date.slice(5), spend: 0, sales: 0 };
    result[row.report_date].spend += Number(row.spend || 0);
    result[row.report_date].sales += Number(row.sales || 0);
    return result;
  }, {});
  return Object.values(byDate).sort((a, b) => a.date.localeCompare(b.date));
}

function priorityText(recommendation) {
  if (recommendation.action_code === "HOLD") return "无需调控";
  return `${recommendation.priority}优先级`;
}

function RecommendationCard({ recommendation, selected, state, shopLabel, currency, lifecycle, onSelect }) {
  const change = percentage(recommendation.change_pct);
  const reviewed = state === "reviewed";
  const deferred = state === "deferred";

  return (
    <button
      className={`recommendation-card ${selected ? "selected" : ""}`}
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
    >
      <span className={`priority-badge ${priorityClass(recommendation.priority)}`}>
        {recommendation.priority}
      </span>
      <span className="recommendation-copy">
        <span className="recommendation-title-row">
          <strong>{recommendation.target_text || recommendation.campaign_name}</strong>
          <span className={`action-badge ${actionClass(recommendation.action_code)}`}>
            {recommendation.action_code}
          </span>
        </span>
        <span className="recommendation-meta">
          {recommendation.campaign_name} · {recommendation.entity_type}
          {recommendation.match_type ? ` · ${recommendation.match_type}` : ""}
          {shopLabel ? ` · ${shopLabel}` : ""}
          <ListingStageBadge lifecycle={lifecycle} compact />
        </span>
        <span className="recommendation-stats">
          <span>
            <small>ACoS</small>
            <b>{percentage(recommendation.acos)}</b>
          </span>
          <span>
            <small>当前 → 建议</small>
            <b>
              {recommendation.current_value === "" || recommendation.current_value == null ? "—" : money(recommendation.current_value, currency)} → {recommendation.proposed_value ? money(recommendation.proposed_value, currency) : "维持"}
            </b>
          </span>
          <span>
            <small>变化</small>
            <b className={Number(recommendation.change_pct) < 0 ? "positive" : "negative"}>
              {recommendation.change_pct ? change : "—"}
            </b>
          </span>
        </span>
        {(reviewed || deferred) && (
          <span className={`review-state ${reviewed ? "reviewed" : "deferred"}`}>
            {reviewed ? <CheckCircle size={14} weight="fill" /> : <PauseCircle size={14} weight="fill" />}
            {reviewed ? "已审核" : "暂不处理"}
          </span>
        )}
      </span>
    </button>
  );
}

function campaignCurrencyGroups(data, shops, scopeShops) {
  const groups = new Map(scopeShops.map((shop) => [shop.currency, {
    currency: shop.currency,
    spend: 0,
    sales: 0,
    orders: 0,
  }]));
  data.campaigns.forEach((item) => {
    const currency = shopCurrencyFor(shops, item);
    const group = groups.get(currency) || { currency, spend: 0, sales: 0, orders: 0 };
    group.spend += Number(item.spend || 0);
    group.sales += Number(item.sales || 0);
    group.orders += Number(item.orders || 0);
    groups.set(currency, group);
  });
  return [...groups.values()].sort((a, b) => currencyLabel(a.currency).localeCompare(currencyLabel(b.currency)));
}

function SummaryStrip({ data, pendingCount, scopeLabel, shops, scopeShops }) {
  const currencyGroups = campaignCurrencyGroups(data, shops, scopeShops);
  const mixedCurrency = currencyGroups.length > 1;
  const totals = currencyGroups.reduce(
    (sum, item) => ({ orders: sum.orders + item.orders }),
    { orders: 0 },
  );
  const group = currencyGroups[0] || { currency: UNKNOWN_CURRENCY, spend: 0, sales: 0 };
  const singleCurrencyItems = [
    ["成熟窗口花费", data.campaigns.length ? money(group.spend, group.currency) : "—"],
    ["广告销售额", data.campaigns.length ? money(group.sales, group.currency) : "—"],
    ["整体 ACoS", data.campaigns.length ? percentage(group.sales ? group.spend / group.sales : 0) : "—"],
  ];

  return (
    <section className={`summary-strip ${mixedCurrency ? "mixed-currency" : ""}`} aria-label="广告监控摘要">
      <div className="summary-period">
        <span>数据周期</span>
        <b>
          {data.meta.source_start_date} 至 {data.meta.source_end_date}
        </b>
        <small>共 {data.meta.lookback_days} 天 · {data.meta.mode === "demo" ? "演示数据" : "真实数据"} · {data.meta.status === "partial" ? "部分覆盖" : "完整覆盖"} · {scopeLabel}</small>
      </div>
      {mixedCurrency ? (
        <div className="currency-summary">
          <span>分币种金额与 ACoS</span>
          <div className="currency-summary-groups">
            {currencyGroups.map((item) => (
              <div key={item.currency || "unknown"}>
                <b>{currencyLabel(item.currency)}</b>
                <small>花费 {number(item.spend)} · 销售 {number(item.sales)} · ACoS {percentage(item.sales ? item.spend / item.sales : 0)}</small>
              </div>
            ))}
          </div>
        </div>
      ) : singleCurrencyItems.map(([label, value]) => (
        <div className="summary-item" key={label}>
          <span>{label}</span>
          <b>{value}</b>
        </div>
      ))}
      <div className="summary-item"><span>广告订单</span><b>{number(totals.orders, 0)}</b></div>
      <div className="summary-item"><span>开启活动</span><b>{number(data.campaigns.length, 0)}</b></div>
      <div className="summary-item pending-summary">
        <span>待审核动作</span>
        <b>{pendingCount}</b>
      </div>
    </section>
  );
}

function DataHealthNotice({ data }) {
  const meta = data.meta || {};
  const partialShopCount = rowsOf(data.shop_coverage).filter((item) => item?.status === "partial").length;
  const partial = meta.status === "partial";
  const truncated = Boolean(meta.source_rows_truncated);
  if (!partial && !truncated) return null;

  return (
    <section className={`data-health-notice ${partial ? "partial" : "complete"}`} aria-label="数据覆盖状态">
      <span className="data-health-state">
        <Info size={18} weight="fill" />
        <b>{partial ? "部分覆盖" : "完整覆盖"}</b>
      </span>
      {partial && (
        <span className="data-health-counts">
          接口失败 <b>{number(meta.failed_calls, 0)}</b>
          <i />对账异常店铺 <b>{number(meta.quality_failures, 0)}</b>
          <i />部分店铺 <b>{number(partialShopCount, 0)}</b>
        </span>
      )}
      {truncated && (
        <span className="data-health-detail">
          诊断明细仅展示 {number(meta.source_rows_published, 0)}/{number(meta.source_rows_total, 0)} 行，趋势和建议仍基于完整数据
        </span>
      )}
    </section>
  );
}

function realtimeViewState(realtime, loadStatus) {
  if (!realtime || loadStatus === "missing" || loadStatus === "error") return "missing";
  if (loadStatus === "refresh-error") return "stale";
  return freshnessState(realtime.meta);
}

function DualTimeStatus({ data, realtime, realtimeLoadStatus, scopeLabel }) {
  const meta = realtime?.meta || {};
  const state = realtimeViewState(realtime, realtimeLoadStatus);
  const alerts = realtime?.alerts || [];
  const unavailable = realtimeLoadStatus === "error";
  const statusCopy = {
    complete: alerts.length ? `发现 ${alerts.length} 条实时异常` : "当前覆盖范围未发现异常",
    partial: alerts.length ? `部分覆盖中发现 ${alerts.length} 条异常` : "未发现异常，但仅部分覆盖",
    stale: "实时快照已过期，不可作为当前判断",
    missing: unavailable ? "实时层读取失败，不能判断是否异常" : "实时层尚未采集，不能判断是否异常",
    not_applicable: "当前没有启用 SP 活动，无需采集",
  };
  const statusLabel = {
    complete: "正常",
    partial: "部分覆盖",
    stale: "已过期",
    missing: unavailable ? "不可用" : "未采集",
    not_applicable: "不适用",
  }[state];

  return (
    <section className="dual-time-status" aria-label="双时间层状态">
      <article className="time-layer-card mature">
        <div className="layer-heading">
          <span className="layer-icon"><ChartBar size={20} weight="duotone" /></span>
          <div><small>成熟归因层</small><b>{data.meta.source_start_date} 至 {data.meta.source_end_date}</b></div>
          <span className="layer-role">用于调控建议</span>
        </div>
        <p>按 {number(data.meta.lookback_days, 0)} 个成熟日计算完整归因，最新日期保留 T-{number(data.meta.maturity_lag_days ?? 2, 0)} 延迟，避免当天转化未回传造成误判。</p>
        <footer><span>生成 {dateTime(data.meta.generated_at)}</span><span>{scopeLabel}</span></footer>
      </article>
      <article className={`time-layer-card realtime ${state}`}>
        <div className="layer-heading">
          <span className="layer-icon"><ArrowsClockwise size={20} weight="duotone" /></span>
          <div><small>实时监控层</small><b>{statusCopy[state]}</b></div>
          <span className={`layer-state ${state}`}>{statusLabel}</span>
        </div>
        <div className="coverage-grid">
          <span><small>店铺覆盖</small><b>{state === "missing" ? "不可用" : state === "not_applicable" ? "无需采集" : ratioText(meta.covered_shops, meta.eligible_shops)}</b></span>
          <span><small>活动覆盖</small><b>{state === "missing" ? "不可用" : state === "not_applicable" ? "无启用活动" : ratioText(meta.covered_campaigns, meta.eligible_campaigns)}</b></span>
          <span><small>观测时间</small><b>{dateTime(meta.observed_at || meta.generated_at)}</b></span>
        </div>
        <footer><span>仅用于预警与阻断，不直接调价{meta.total_shops ? ` · 总店铺 ${number(meta.total_shops, 0)}，不适用 ${number(meta.not_applicable_shops, 0)}` : ""}</span><span>{scopeLabel}</span></footer>
      </article>
    </section>
  );
}

function RealtimeAlertRow({ alert, showShop, lifecycle }) {
  const level = severityClass(alert.severity);
  return (
    <article className={`realtime-alert-row ${level}`}>
      <div className="alert-identity">
        <span className={`severity-badge ${level}`}>{severityLabel(alert.severity)}</span>
        <span>
          <b>{alert.campaign_name || alert.campaign_id || "未命名活动"}</b>
          <small>{showShop ? `${alert.shop_name || shopIdOf(alert) || "未知店铺"} · ` : ""}{alert.alert_code || metricLabel(alert.metric)} · {dateTime(alert.observed_at)}</small>
          <ListingStageBadge lifecycle={lifecycle} compact />
        </span>
      </div>
      <div className="alert-metric">
        <small>{metricLabel(alert.metric)}</small>
        <b>{alertMetricValue(alert, "current_value")}</b>
      </div>
      <div className="alert-metric baseline">
        <small>成熟基线</small>
        <b>{alertMetricValue(alert, "baseline_value")}</b>
      </div>
      <div className="alert-metric deviation">
        <small>偏离</small>
        <b>{deviationText(alert.deviation_pct)}</b>
      </div>
      <div className="alert-guidance">
        <b>{alert.reason || "实时指标偏离成熟基线"}</b>
        <small>{handlingLabel(alert.handling)}；实时层不会直接修改广告。</small>
      </div>
    </article>
  );
}

function RealtimeAlertsView({ realtime, loadStatus, scopeLabel, refreshVersion, showShop, advertisedProducts }) {
  const [filter, setFilter] = useState("all");
  const [listingFilter, setListingFilter] = useState(LISTING_STAGE.ALL);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const alerts = realtime?.alerts || [];
  const lifecycleIndex = useMemo(
    () => aggregateCampaignLifecycles(advertisedProducts),
    [advertisedProducts],
  );
  const state = realtimeViewState(realtime, loadStatus);
  const alertLifecycle = (alert) => {
    const explicitStage = String(alert?.listing_stage || "").trim();
    return explicitStage
      ? { stage: normalizeListingStage(explicitStage), total: 0 }
      : campaignLifecycleFor(lifecycleIndex, alert);
  };
  const lifecycleScopedAlerts = alerts.filter((alert) => (
    listingStageMatches(alertLifecycle(alert).stage, listingFilter)
  ));
  const counts = ALERT_FILTERS.reduce((result, item) => {
    result[item.id] = item.id === "all"
      ? lifecycleScopedAlerts.length
      : lifecycleScopedAlerts.filter((alert) => severityClass(alert.severity) === item.id).length;
    return result;
  }, {});
  const filtered = lifecycleScopedAlerts.filter((alert) => {
    const text = [
      alert.shop_name,
      shopIdOf(alert),
      alert.campaign_name,
      alert.campaign_id,
      alert.alert_code,
      alert.metric,
      alert.reason,
      alert.handling,
    ].join(" ").toLowerCase();
    return (filter === "all" || severityClass(alert.severity) === filter)
      && text.includes(query.trim().toLowerCase());
  });
  const pageCount = Math.max(1, Math.ceil(filtered.length / ALERTS_PER_PAGE));
  const currentPage = Math.min(page, pageCount);
  const pageStart = (currentPage - 1) * ALERTS_PER_PAGE;
  const visible = filtered.slice(pageStart, pageStart + ALERTS_PER_PAGE);
  const pageButtons = paginationItems(currentPage, pageCount);

  useEffect(() => { setPage(1); }, [filter, listingFilter, query, alerts, refreshVersion]);

  const emptyCopy = state === "missing"
    ? loadStatus === "error" ? "实时层读取失败，当前无法判断是否存在异常。" : "实时层尚未采集，当前无法判断是否存在异常。"
    : state === "not_applicable"
      ? "本店当前没有启用 SP 活动，因此不需要实时采集。"
      : state === "stale"
      ? "实时快照已经过期，当前列表不能代表此刻的广告状态。"
      : state === "partial"
        ? "当前已采集范围未发现异常，但仅部分覆盖，不能等同于全部正常。"
        : "当前完整覆盖范围未发现实时异常。";

  return (
    <main className="single-panel realtime-panel">
      <div className="section-heading realtime-heading">
        <div><span>{scopeLabel} · 仅用于预警与阻断</span><h2>实时异常监控</h2></div>
        <div className={`realtime-heading-state ${state}`}><i />{state === "complete" ? "数据可用" : state === "partial" ? "部分覆盖" : state === "not_applicable" ? "无需采集" : state === "stale" ? "数据过期" : loadStatus === "error" ? "暂不可用" : "尚未采集"}</div>
      </div>
      <div className="realtime-toolbar">
        <label>
          <MagnifyingGlass size={20} />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索店铺 / 活动 / 异常原因"
            aria-label="搜索实时异常"
          />
        </label>
        <div className="filter-row realtime-filters" role="tablist" aria-label="实时异常筛选">
          {ALERT_FILTERS.map((item) => (
            <button
              className={filter === item.id ? "active" : ""}
              key={item.id}
              role="tab"
              aria-selected={filter === item.id}
              type="button"
              onClick={() => { setFilter(item.id); setPage(1); }}
            >
              {item.label} <span>{counts[item.id]}</span>
            </button>
          ))}
        </div>
        <ListingStageSelect value={listingFilter} onChange={(value) => { setListingFilter(value); setPage(1); }} label="异常上架阶段" />
        <button className="clear-realtime-filter" type="button" onClick={() => { setFilter("all"); setListingFilter(LISTING_STAGE.ALL); setQuery(""); setPage(1); }}>
          <FunnelSimple size={18} />清除筛选
        </button>
      </div>

      {(loadStatus === "refresh-error" || state === "partial" || state === "stale") && (
        <div className="realtime-caveat"><Info size={17} weight="fill" />{
          loadStatus === "refresh-error"
            ? "本次刷新失败，当前保留上一次成功快照；在重新采集成功前禁止把它作为实时确认。"
            : state === "stale"
              ? "实时快照已超过有效时限；历史异常仍可查看，但不能代表当前状态。"
              : "实时采集仅覆盖部分店铺或活动；未覆盖范围未知，不能视为正常。"
        }</div>
      )}

      <div className="realtime-alert-list">
        {visible.map((alert, index) => (
          <RealtimeAlertRow key={alert.alert_id || `${shopIdOf(alert)}:${alert.campaign_id}:${alert.alert_code}:${index}`} alert={alert} showShop={showShop} lifecycle={alertLifecycle(alert)} />
        ))}
        {!visible.length && (
          <div className={`realtime-empty ${state}`}>
            {state === "complete" ? <CheckCircle size={42} weight="duotone" /> : <Info size={42} weight="duotone" />}
            <b>{query || filter !== "all" || listingFilter !== LISTING_STAGE.ALL ? "没有匹配的实时异常" : emptyCopy}</b>
            <small>{query || filter !== "all" || listingFilter !== LISTING_STAGE.ALL ? "请清除筛选查看当前范围的全部实时异常。" : "实时数据不会直接生成广告修改动作；调控仍以成熟归因层为准。"}</small>
          </div>
        )}
      </div>

      {!!filtered.length && (
        <nav className="pagination-bar realtime-pagination" aria-label="实时异常分页">
          <span className="pagination-summary">第 {currentPage} / {pageCount} 页 · 每页 {ALERTS_PER_PAGE} 条 · 当前 {pageStart + 1}–{Math.min(pageStart + ALERTS_PER_PAGE, filtered.length)} 条</span>
          <div className="pagination-controls">
            <button type="button" disabled={currentPage === 1} onClick={() => setPage(Math.max(1, currentPage - 1))} aria-label="上一页">‹</button>
            {pageButtons.map((item) => typeof item === "number" ? (
              <button className={item === currentPage ? "active" : ""} key={item} type="button" aria-current={item === currentPage ? "page" : undefined} onClick={() => setPage(item)}>{item}</button>
            ) : <span className="pagination-ellipsis" key={item}>…</span>)}
            <button type="button" disabled={currentPage === pageCount} onClick={() => setPage(Math.min(pageCount, currentPage + 1))} aria-label="下一页">›</button>
          </div>
        </nav>
      )}
    </main>
  );
}

function TriggerExplanation({ recommendation, currency }) {
  const excess = recommendation.acos
    ? Math.max(0, (Number(recommendation.acos) / Number(recommendation.target_acos) - 1) * 100)
    : 0;
  const content = recommendation.rule_id === "profitable_budget_limited"
    ? [
        [Target, "预算接近上限", recommendation.reason || "近期多个成熟日的花费接近活动预算上限。", "green"],
        [ChartBar, "效率达标", `当前 ACoS ${percentage(recommendation.acos)}，不高于目标 ${percentage(recommendation.target_acos)}。`, "purple"],
        [Info, "建议动作", `将活动日预算从 ${money(recommendation.current_value, currency)} 调整至 ${money(recommendation.proposed_value, currency)}，提高 ${percentage(Math.abs(Number(recommendation.change_pct)))}。`, "blue"],
        [Flag, "风险控制", "审核后手动调整，并在下一个成熟周期重新评估花费与转化。", "green"],
      ]
    : recommendation.rule_id === "zero_order_spend"
    ? [
        [Target, "零订单花费", `14 天点击 ${recommendation.clicks}、花费 ${money(recommendation.spend, currency)}，但没有产生订单。`, "danger"],
        [ChartBar, "规则触发", "点击和花费均已达到零订单观察门槛，当前流量暂未转化。", "purple"],
        [Info, "建议动作", `将竞价从 ${money(recommendation.current_value, currency)} 调整至 ${money(recommendation.proposed_value, currency)}，先降低 ${percentage(Math.abs(Number(recommendation.change_pct)))}。`, "blue"],
        [Flag, "后续观察", "下一成熟周期仍无订单时，再评估暂停该投放词。", "green"],
      ]
    : recommendation.rule_id === "low_acos_scale"
      ? [
          [Target, "低于目标", `当前 ACoS ${percentage(recommendation.acos)}，明显低于目标 ${percentage(recommendation.target_acos)}。`, "green"],
          [ChartBar, "成熟度已足够", `14 天获得 ${recommendation.orders} 单、${recommendation.clicks} 次点击，具备扩量判断基础。`, "purple"],
          [Info, "建议动作", `将竞价从 ${money(recommendation.current_value, currency)} 调整至 ${money(recommendation.proposed_value, currency)}，小幅增加流量。`, "blue"],
          [Flag, "风险控制", `单次提高控制在 ${percentage(Math.abs(Number(recommendation.change_pct)))}，下一周期重新评估。`, "green"],
        ]
      : [
          [Target, "ACoS 高于目标", `当前 ACoS ${percentage(recommendation.acos)}，高于目标 ${percentage(recommendation.target_acos)}，超出 ${excess.toFixed(1)}%。`, "danger"],
          [ChartBar, "成熟度已足够", `14 天获得 ${recommendation.orders} 单、${recommendation.clicks} 次点击，已达到高 ACoS 判断门槛。`, "purple"],
          [Info, "建议动作", `将竞价从 ${money(recommendation.current_value, currency)} 调整至 ${money(recommendation.proposed_value, currency)}，降低 ${percentage(Math.abs(Number(recommendation.change_pct)))}。`, "blue"],
          [Flag, "规则参考", `当前目标 ACoS 为 ${percentage(recommendation.target_acos)}，下一周期重新评估。`, "green"],
        ];

  return (
    <section className="why-panel">
      <h3>为何触发此建议</h3>
      <div className="explanation-list">
        {content.map(([Icon, title, description, color]) => (
          <div className="explanation-row" key={title}>
            <Icon className={`explanation-icon ${color}`} size={24} weight="duotone" />
            <span>
              <b>{title}</b>
              <small>{description}</small>
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function RecommendationDetail({ recommendation, campaignDailyTrend, sourceData, state, shopLabel, currency, lifecycle, realtimeGate, onReview, onDefer }) {
  const chartData = useMemo(
    () => campaignTrend(recommendation, campaignDailyTrend, sourceData),
    [recommendation, campaignDailyTrend, sourceData],
  );
  const reviewed = state === "reviewed";
  const deferred = state === "deferred";
  const proposed = recommendation.proposed_value || recommendation.current_value;
  const valueLabel = recommendation.action_code === "INCREASE_BUDGET" ? "预算" : "出价";
  const gate = realtimeGate?.gate || "BLOCK";
  const gateCopy = {
    BLOCK: ["实时层阻断", "实时数据缺失、过期或存在冲突，不能进入执行确认。"],
    REVIEW: ["需要人工复核", "实时层发现需结合生命周期与成熟指标判断的信号。"],
    NO_OBJECTION: ["实时层无阻断", "只表示当前未发现冲突，不代表系统批准执行。"],
    MONITOR_ONLY: ["仅监控", "此项当前不属于可执行调控动作。"],
  }[gate] || ["实时状态未知", "不能进入执行确认。"];

  return (
    <article className="detail-panel">
      <header className="detail-header">
        <div>
          <span className={`detail-priority ${priorityClass(recommendation.priority)}`}>
            {priorityText(recommendation)}
          </span>
          <h2>{recommendation.target_text || recommendation.campaign_name}</h2>
        </div>
        <span className={`action-badge large ${actionClass(recommendation.action_code)}`}>
          {recommendation.action_code}
        </span>
      </header>

      <dl className={`entity-meta-grid ${shopLabel ? "with-shop" : ""}`}>
        {shopLabel && <div><dt>店铺</dt><dd>{shopLabel}</dd></div>}
        <div><dt>活动</dt><dd>{recommendation.campaign_name}</dd></div>
        <div><dt>投放类型</dt><dd>{recommendation.entity_type}</dd></div>
        <div><dt>匹配方式</dt><dd>{recommendation.match_type || "—"}</dd></div>
        <div><dt>活动 ID</dt><dd>{recommendation.campaign_id}</dd></div>
        <div><dt>投放 ID</dt><dd>{recommendation.target_id || "—"}</dd></div>
        <div><dt>SKU 上架阶段</dt><dd><ListingStageBadge lifecycle={lifecycle} /></dd></div>
      </dl>

      <section className={`recommendation-gate ${gate.toLowerCase()}`}>
        <ShieldCheck size={19} weight="duotone" />
        <span><b>{gateCopy[0]}</b><small>{gateCopy[1]}</small></span>
        <em>{realtimeGate?.snapshot?.freshness?.status || "missing"}</em>
      </section>

      <section className="bid-metrics">
        <div className="bid-change">
          <span><small>当前{valueLabel}</small><b>{recommendation.current_value || "—"}</b><i>{currencyLabel(currency)}</i></span>
          <ArrowRight size={31} color="#9ca3af" />
          <span><small>建议{valueLabel}</small><b className="accent">{proposed || "—"}</b><i>{currencyLabel(currency)}</i></span>
          <span className="change-value">
            <small>变化比例</small>
            <b className={Number(recommendation.change_pct) < 0 ? "positive" : "negative"}>
              {recommendation.change_pct ? percentage(recommendation.change_pct) : "0.0%"}
            </b>
          </span>
        </div>
        <div className="metric-grid">
          <span><small>ACoS</small><b>{percentage(recommendation.acos)}</b></span>
          <span><small>目标 ACoS</small><b>{percentage(recommendation.target_acos)}</b></span>
          <span><small>花费</small><b>{money(recommendation.spend, currency)}</b></span>
          <span><small>销售额</small><b>{money(recommendation.sales, currency)}</b></span>
          <span><small>订单</small><b>{number(recommendation.orders, 0)}</b></span>
          <span><small>点击</small><b>{number(recommendation.clicks, 0)}</b></span>
        </div>
      </section>

      <div className="detail-lower-grid">
        <section className="chart-panel">
          <h3>所属活动花费与销售额 <small>（近 14 天）</small></h3>
          {chartData.length ? (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={chartData} margin={{ top: 18, right: 16, left: -8, bottom: 0 }}>
                <CartesianGrid stroke="#e5e7eb" strokeDasharray="4 4" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: "#6b7280", fontSize: 12 }} axisLine={false} tickLine={false} minTickGap={28} />
                <YAxis tick={{ fill: "#6b7280", fontSize: 12 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ borderRadius: 12, border: "1px solid #e5e7eb" }} />
                <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
                <Line name={`花费（${currencyLabel(currency)}）`} dataKey="spend" type="monotone" stroke="#ff6b1a" strokeWidth={2.5} dot={{ r: 3, fill: "#ff6b1a" }} />
                <Line name={`广告销售额（${currencyLabel(currency)}）`} dataKey="sales" type="monotone" stroke="#1473e6" strokeWidth={2.5} dot={{ r: 3, fill: "#1473e6" }} />
              </LineChart>
            </ResponsiveContainer>
          ) : <div className="chart-inline-empty">暂无该活动的每日趋势数据</div>}
        </section>
        <TriggerExplanation recommendation={recommendation} currency={currency} />
      </div>

      <footer className="detail-footer">
        <p>说明：本版为自动生成的只读建议，审核不会修改广告。建议结合业务目标与市场情况决定后续操作。</p>
        <div>
          <button className={`secondary-button ${deferred ? "active" : ""}`} type="button" onClick={onDefer}>
            {deferred ? "已标记暂不处理" : "暂不处理"}
          </button>
          <button className={`primary-button ${reviewed ? "reviewed" : ""}`} type="button" onClick={onReview} disabled={gate === "BLOCK"}>
            <CheckCircle size={20} weight={reviewed ? "fill" : "regular"} />
            {gate === "BLOCK" ? "实时层阻断" : reviewed ? "已审核" : gate === "REVIEW" ? "标记已人工复核" : "标记为已审核"}
          </button>
        </div>
      </footer>
    </article>
  );
}

function ReviewWorkspace({ data, realtime, realtimeLoadStatus, reviewState, setReviewState, notify, showShop, shops }) {
  const [filter, setFilter] = useState("all");
  const [listingFilter, setListingFilter] = useState(LISTING_STAGE.ALL);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const lifecycleIndex = useMemo(
    () => aggregateCampaignLifecycles(data.advertised_products),
    [data.advertised_products],
  );
  const orderedRecommendations = useMemo(
    () => [...data.recommendations].sort((a, b) => Number(isReviewableAction(b)) - Number(isReviewableAction(a))),
    [data.recommendations],
  );
  const actionable = orderedRecommendations.filter(isReviewableAction);
  const firstKey = recommendationKey(actionable[0] || data.recommendations[0]);
  const [selectedKey, setSelectedKey] = useState(firstKey);
  const selected = data.recommendations.find((item) => recommendationKey(item) === selectedKey)
    || data.recommendations[0];
  const selectedState = reviewValue(reviewState, selected);
  const realtimeGate = recommendationRealtimeGate(realtime, selected, realtimeLoadStatus);
  const selectedLifecycle = campaignLifecycleFor(lifecycleIndex, selected);

  const lifecycleScopedRecommendations = orderedRecommendations.filter((item) => (
    listingStageMatches(campaignLifecycleFor(lifecycleIndex, item).stage, listingFilter)
  ));

  const counts = {
    all: lifecycleScopedRecommendations.length,
    high: lifecycleScopedRecommendations.filter((item) => item.priority === "高").length,
    pending: lifecycleScopedRecommendations.filter((item) => isReviewableAction(item) && !reviewValue(reviewState, item)).length,
  };

  const filtered = lifecycleScopedRecommendations.filter((item) => {
    const text = `${item.target_text} ${item.campaign_name} ${item.target_id}`.toLowerCase();
    const matchesSearch = text.includes(query.trim().toLowerCase());
    const matchesFilter = filter === "all"
      || (filter === "high" && item.priority === "高")
      || (filter === "pending" && isReviewableAction(item) && !reviewValue(reviewState, item));
    return matchesSearch && matchesFilter;
  });
  const pageCount = Math.max(1, Math.ceil(filtered.length / RECOMMENDATIONS_PER_PAGE));
  const currentPage = Math.min(page, pageCount);
  const pageStart = (currentPage - 1) * RECOMMENDATIONS_PER_PAGE;
  const visible = filtered.slice(pageStart, pageStart + RECOMMENDATIONS_PER_PAGE);
  const pageButtons = paginationItems(currentPage, pageCount);

  useEffect(() => { setPage(1); }, [filter, listingFilter, query, data.recommendations]);
  useEffect(() => {
    if (visible.length && !visible.some((item) => recommendationKey(item) === selectedKey)) {
      setSelectedKey(recommendationKey(visible[0]));
    }
  }, [visible, selectedKey]);

  function goToPage(nextPage) {
    const targetPage = Math.max(1, Math.min(pageCount, nextPage));
    setPage(targetPage);
    const firstItem = filtered[(targetPage - 1) * RECOMMENDATIONS_PER_PAGE];
    if (firstItem) setSelectedKey(recommendationKey(firstItem));
  }

  function updateReviewState(value) {
    if (value === "reviewed" && realtimeGate.gate === "BLOCK") {
      notify("实时层已阻断：请先补齐或刷新当前活动的小时数据。");
      return;
    }
    setReviewState((current) => {
      const nextState = { ...current };
      const key = recommendationKey(selected);
      if (value) nextState[key] = value;
      else delete nextState[key];
      return nextState;
    });
    if (value === "reviewed") {
      const next = visible.find((item) => recommendationKey(item) !== recommendationKey(selected) && isReviewableAction(item) && !reviewValue(reviewState, item));
      if (next) setSelectedKey(recommendationKey(next));
      notify("已标记为审核完成；广告未被修改。");
    } else if (value === "deferred") {
      notify("已标记为暂不处理；再次点击可以恢复。");
    } else {
      notify("已恢复为待审核状态。");
    }
  }

  return (
    <main className="workspace-grid">
      <aside className="queue-panel">
        <div className="queue-title">
          <h2>调控建议列表 <small>（当前 {filtered.length} / 总 {data.recommendations.length} 条）</small></h2>
        </div>
        <div className="search-row">
          <label>
            <MagnifyingGlass size={20} />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索活动 / 投放词 / 商品"
              aria-label="搜索建议"
            />
          </label>
          <button className="icon-button" type="button" onClick={() => { setFilter("all"); setListingFilter(LISTING_STAGE.ALL); setQuery(""); setPage(1); }} aria-label="清除筛选">
            <FunnelSimple size={22} />
          </button>
        </div>
        <ListingStageSelect value={listingFilter} onChange={(value) => { setListingFilter(value); setPage(1); }} label="建议上架阶段" />
        <div className="filter-row" role="tablist" aria-label="建议筛选">
          {FILTERS.map((item) => (
            <button
              className={filter === item.id ? "active" : ""}
              key={item.id}
              role="tab"
              aria-selected={filter === item.id}
              type="button"
              onClick={() => { setFilter(item.id); setPage(1); }}
            >
              {item.label} <span>{counts[item.id]}</span>
            </button>
          ))}
        </div>
        <div className="recommendation-list">
          {visible.map((item) => (
            <RecommendationCard
              key={recommendationKey(item)}
              recommendation={item}
              selected={recommendationKey(selected) === recommendationKey(item)}
              state={reviewValue(reviewState, item)}
              shopLabel={showShop ? shopNameFor(shops, item) : ""}
              currency={shopCurrencyFor(shops, item)}
              lifecycle={campaignLifecycleFor(lifecycleIndex, item)}
              onSelect={() => setSelectedKey(recommendationKey(item))}
            />
          ))}
          {!visible.length && <div className="empty-state">没有匹配的建议</div>}
        </div>
        {!!filtered.length && (
          <nav className="pagination-bar" aria-label="调控建议分页">
            <span className="pagination-summary">
              第 {currentPage} / {pageCount} 页 · 每页 {RECOMMENDATIONS_PER_PAGE} 条 · 当前 {pageStart + 1}–{Math.min(pageStart + RECOMMENDATIONS_PER_PAGE, filtered.length)} 条
            </span>
            <div className="pagination-controls">
              <button type="button" disabled={currentPage === 1} onClick={() => goToPage(currentPage - 1)} aria-label="上一页">‹</button>
              {pageButtons.map((item) => typeof item === "number" ? (
                <button
                  className={item === currentPage ? "active" : ""}
                  key={item}
                  type="button"
                  aria-current={item === currentPage ? "page" : undefined}
                  onClick={() => goToPage(item)}
                >
                  {item}
                </button>
              ) : <span className="pagination-ellipsis" key={item}>…</span>)}
              <button type="button" disabled={currentPage === pageCount} onClick={() => goToPage(currentPage + 1)} aria-label="下一页">›</button>
            </div>
          </nav>
        )}
      </aside>
      {filtered.length ? (
        <RecommendationDetail
          recommendation={selected}
          campaignDailyTrend={data.campaign_daily_trend || []}
          sourceData={data.source_data || []}
          state={selectedState}
          realtimeGate={realtimeGate}
          shopLabel={showShop ? shopNameFor(shops, selected) : ""}
          currency={shopCurrencyFor(shops, selected)}
          lifecycle={selectedLifecycle}
          onReview={() => updateReviewState(selectedState === "reviewed" ? null : "reviewed")}
          onDefer={() => updateReviewState(selectedState === "deferred" ? null : "deferred")}
        />
      ) : (
        <article className="detail-panel detail-filter-empty">
          <Package size={46} weight="duotone" />
          <h2>当前筛选没有调控建议</h2>
          <p>未知上架状态会单独保留；清除筛选后可查看全部建议。</p>
        </article>
      )}
    </main>
  );
}

function EmptyRecommendationsView() {
  return (
    <main className="single-panel empty-recommendations">
      <CheckCircle size={44} weight="duotone" />
      <h2>当前没有需要审核的调控建议</h2>
      <p>数据仍会按成熟窗口持续监控；出现满足规则的投放对象后会自动显示在这里。</p>
    </main>
  );
}

function RulesView({ data }) {
  return (
    <main className="single-panel">
      <div className="section-heading"><div><span>规则版本</span><h2>{data.meta.rule_version}</h2></div><ShieldCheck size={38} weight="duotone" /></div>
      <div className="rules-list">
        <div><b>高 ACoS 降价</b><span>成熟窗口订单不少于 3，且 ACoS 高于目标值 20%</span><em>竞价降低 10%</em></div>
        <div><b>低 ACoS 扩量</b><span>订单不少于 5，且 ACoS 低于目标值 20%</span><em>竞价提高 5%</em></div>
        <div><b>有花费无订单</b><span>点击不少于 10，花费达到零订单门槛</span><em>竞价降低 10%</em></div>
        <div><b>数据安全门禁</b><span>过期、缺失、部分返回或停用对象不会给出可执行建议</span><em>自动阻断</em></div>
      </div>
    </main>
  );
}

function CampaignView({ data, showShop, shops }) {
  const [listingFilter, setListingFilter] = useState(LISTING_STAGE.ALL);
  const [page, setPage] = useState(1);
  const lifecycleIndex = useMemo(
    () => aggregateCampaignLifecycles(data.advertised_products),
    [data.advertised_products],
  );
  const campaigns = data.campaigns.filter((item) => (
    listingStageMatches(campaignLifecycleFor(lifecycleIndex, item).stage, listingFilter)
  ));
  const pageCount = Math.max(1, Math.ceil(campaigns.length / CAMPAIGNS_PER_PAGE));
  const currentPage = Math.min(page, pageCount);
  const pageStart = (currentPage - 1) * CAMPAIGNS_PER_PAGE;
  const visible = campaigns.slice(pageStart, pageStart + CAMPAIGNS_PER_PAGE);
  const pageButtons = paginationItems(currentPage, pageCount);

  useEffect(() => { setPage(1); }, [listingFilter, data.campaigns]);

  return (
    <main className="single-panel">
      <div className="section-heading">
        <div><span>同一成熟窗口 · 当前 {campaigns.length} / 总 {data.campaigns.length} 个活动</span><h2>广告活动概览</h2></div>
        <div className="section-heading-tools"><ListingStageSelect value={listingFilter} onChange={(value) => { setListingFilter(value); setPage(1); }} label="活动上架阶段" /><Target size={38} weight="duotone" /></div>
      </div>
      <div className="campaign-table">
        <div className="campaign-row header"><span>活动</span><span>上架阶段</span><span>花费</span><span>销售额</span><span>订单</span><span>ACoS</span><span>状态</span></div>
        {visible.map((item) => (
          <div className="campaign-row" key={`${shopIdOf(item)}:${item.campaign_id}`}>
            <span>
              <b>{item.campaign_name}</b>
              <small>{item.campaign_id}{showShop ? ` · ${shopNameFor(shops, item)}` : ""}</small>
            </span>
            <span><ListingStageBadge lifecycle={campaignLifecycleFor(lifecycleIndex, item)} /></span>
            <span>{money(item.spend, shopCurrencyFor(shops, item))}</span><span>{money(item.sales, shopCurrencyFor(shops, item))}</span><span>{number(item.orders, 0)}</span>
            <span className={item.acos > 0.3 ? "negative" : "positive"}>{percentage(item.acos)}</span>
            <span><i className="status-dot" />运行中</span>
          </div>
        ))}
        {!campaigns.length && <div className="table-empty">当前店铺与上架阶段下没有广告活动数据</div>}
      </div>
      {!!campaigns.length && (
        <nav className="pagination-bar" aria-label="活动概览分页">
          <span className="pagination-summary">第 {currentPage} / {pageCount} 页 · 每页 {CAMPAIGNS_PER_PAGE} 条 · 当前 {pageStart + 1}–{Math.min(pageStart + CAMPAIGNS_PER_PAGE, campaigns.length)} 条</span>
          <div className="pagination-controls">
            <button type="button" disabled={currentPage === 1} onClick={() => setPage(Math.max(1, currentPage - 1))} aria-label="上一页">‹</button>
            {pageButtons.map((item) => typeof item === "number" ? (
              <button className={item === currentPage ? "active" : ""} key={item} type="button" aria-current={item === currentPage ? "page" : undefined} onClick={() => setPage(item)}>{item}</button>
            ) : <span className="pagination-ellipsis" key={item}>…</span>)}
            <button type="button" disabled={currentPage === pageCount} onClick={() => setPage(Math.min(pageCount, currentPage + 1))} aria-label="下一页">›</button>
          </div>
        </nav>
      )}
    </main>
  );
}

function SkuLifecycleView({ products, scopeLabel, showShop, listingCoverage, selectedShop }) {
  const [listingFilter, setListingFilter] = useState(LISTING_STAGE.ALL);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const ordered = useMemo(() => [...products].sort((a, b) => {
    const stageOrder = { [LISTING_STAGE.NEW]: 0, [LISTING_STAGE.ESTABLISHED]: 1, [LISTING_STAGE.UNKNOWN]: 2 };
    const stageDifference = (stageOrder[productListingStage(a)] ?? 3) - (stageOrder[productListingStage(b)] ?? 3);
    if (stageDifference) return stageDifference;
    return Number(a.listing_age_days ?? Number.MAX_SAFE_INTEGER) - Number(b.listing_age_days ?? Number.MAX_SAFE_INTEGER);
  }), [products]);
  const counts = SKU_LISTING_FILTERS.reduce((result, item) => {
    result[item.id] = item.id === LISTING_STAGE.ALL
      ? ordered.length
      : ordered.filter((product) => productListingStage(product) === item.id).length;
    return result;
  }, {});
  const filtered = ordered.filter((product) => {
    const text = [
      product.shop_name,
      shopIdOf(product),
      product.sku,
      product.asin,
      product.campaign_id,
      product.group_id,
      product.ad_id,
      product.online_status,
      product.mapping_status,
    ].join(" ").toLowerCase();
    return listingStageMatches(productListingStage(product), listingFilter)
      && text.includes(query.trim().toLowerCase());
  });
  const pageCount = Math.max(1, Math.ceil(filtered.length / SKUS_PER_PAGE));
  const currentPage = Math.min(page, pageCount);
  const pageStart = (currentPage - 1) * SKUS_PER_PAGE;
  const visible = filtered.slice(pageStart, pageStart + SKUS_PER_PAGE);
  const pageButtons = paginationItems(currentPage, pageCount);
  const scopedCoverage = selectedShop === ALL_SHOPS
    ? listingCoverage
    : (listingCoverage?.shop_coverage || []).find((item) => shopIdOf(item) === selectedShop);
  const emptySourceCopy = scopedCoverage?.status === "unavailable"
    ? "在线产品或广告商品数据源不可用，当前新品状态未知"
    : scopedCoverage?.status === "not_applicable"
      ? "当前范围没有启用的 SP 广告 SKU"
      : "成熟数据尚未发布广告 SKU 上架信息";

  useEffect(() => { setPage(1); }, [listingFilter, query, products]);

  return (
    <main className="single-panel sku-lifecycle-panel">
      <div className="section-heading">
        <div><span>{scopeLabel} · 每条对应一个广告位置</span><h2>广告 SKU 上新状态</h2></div>
        <Package size={38} weight="duotone" />
      </div>
      <div className="sku-toolbar">
        <label>
          <MagnifyingGlass size={20} />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索 SKU / ASIN / 活动 / 广告组 / adId"
            aria-label="搜索广告SKU"
          />
        </label>
        <button className="clear-realtime-filter" type="button" onClick={() => { setListingFilter(LISTING_STAGE.ALL); setQuery(""); setPage(1); }}>
          <FunnelSimple size={18} />清除筛选
        </button>
      </div>
      <div className="filter-row sku-stage-filters" role="tablist" aria-label="SKU上架阶段筛选">
        {SKU_LISTING_FILTERS.map((item) => (
          <button
            className={listingFilter === item.id ? "active" : ""}
            key={item.id}
            role="tab"
            aria-selected={listingFilter === item.id}
            type="button"
            onClick={() => { setListingFilter(item.id); setPage(1); }}
          >
            {item.label.replace("全部上架阶段", "全部")} <span>{counts[item.id]}</span>
          </button>
        ))}
      </div>

      <div className="sku-lifecycle-table">
        <div className="sku-lifecycle-row header">
          <span>SKU / ASIN</span><span>上架信息</span><span>阶段</span><span>活动</span><span>广告组</span><span>广告位置</span><span>匹配状态</span>
        </div>
        {visible.map((product, index) => {
          const stage = productListingStage(product);
          return (
            <article className="sku-lifecycle-row" key={`${shopIdOf(product)}:${product.campaign_id}:${product.group_id}:${product.ad_id}:${product.sku}:${index}`}>
              <span className="sku-identity"><b>{product.sku || "SKU 未知"}</b><small>{product.asin || "ASIN 未知"}{showShop ? ` · ${product.shop_name || shopIdOf(product)}` : ""}</small></span>
              <span><b>{product.open_date ? compactDate(String(product.open_date).slice(0, 10)) : "上架时间未知"}</b><small>{product.listing_age_days == null ? "天数未知" : `已上架 ${number(product.listing_age_days, 0)} 天`} · {product.online_status || "状态未知"}</small></span>
              <span><ListingStageBadge lifecycle={{ stage }} /></span>
              <span><b>{product.campaign_id || "—"}</b></span>
              <span><b>{product.group_id || "—"}</b></span>
              <span><b>{product.ad_id || "—"}</b></span>
              <span><b>{mappingStatusLabel(product.mapping_status)}</b></span>
            </article>
          );
        })}
        {!visible.length && (
          <div className="table-empty">
            {products.length ? "当前搜索和上架阶段下没有匹配的广告 SKU" : emptySourceCopy}
          </div>
        )}
      </div>

      {!!filtered.length && (
        <nav className="pagination-bar sku-pagination" aria-label="SKU上新分页">
          <span className="pagination-summary">第 {currentPage} / {pageCount} 页 · 每页 {SKUS_PER_PAGE} 条 · 当前 {pageStart + 1}–{Math.min(pageStart + SKUS_PER_PAGE, filtered.length)} 条</span>
          <div className="pagination-controls">
            <button type="button" disabled={currentPage === 1} onClick={() => setPage(Math.max(1, currentPage - 1))} aria-label="上一页">‹</button>
            {pageButtons.map((item) => typeof item === "number" ? (
              <button className={item === currentPage ? "active" : ""} key={item} type="button" aria-current={item === currentPage ? "page" : undefined} onClick={() => setPage(item)}>{item}</button>
            ) : <span className="pagination-ellipsis" key={item}>…</span>)}
            <button type="button" disabled={currentPage === pageCount} onClick={() => setPage(Math.min(pageCount, currentPage + 1))} aria-label="下一页">›</button>
          </div>
        </nav>
      )}
    </main>
  );
}

function PerformanceView({ data, scopeShops }) {
  const startDate = data.daily_trend[0]?.date || data.meta.source_start_date;
  const endDate = data.daily_trend.at(-1)?.date || data.meta.source_end_date;
  const currencies = [...new Set(scopeShops.map((shop) => shop.currency))];
  const mixedCurrency = currencies.length > 1;
  const currency = currencies[0] || UNKNOWN_CURRENCY;
  const canChartMoney = !mixedCurrency && Boolean(currency);
  return (
    <main className="single-panel performance-view">
      <div className="section-heading"><div><span>{startDate} 至 {endDate}</span><h2>每日广告表现</h2></div><ChartBar size={38} weight="duotone" /></div>
      {mixedCurrency ? (
        <div className="currency-safety-state">
          <ShieldCheck size={46} weight="duotone" />
          <h3>当前范围包含多种币种</h3>
          <p>{currencies.map(currencyLabel).join("、")} 的金额不能直接相加，因此未绘制跨币种花费和销售额趋势。请在顶部选择单个店铺查看。</p>
        </div>
      ) : !canChartMoney ? (
        <div className="currency-safety-state">
          <Info size={42} weight="duotone" />
          <h3>暂时无法确认金额币种</h3>
          <p>当前店铺数据没有提供 currency；为避免误读，金额趋势暂不绘制。</p>
        </div>
      ) : data.daily_trend.length ? (
        <ResponsiveContainer width="100%" height={470}>
          <LineChart data={data.daily_trend} margin={{ top: 28, right: 24, left: 0, bottom: 8 }}>
            <CartesianGrid stroke="#e5e7eb" strokeDasharray="4 4" vertical={false} />
            <XAxis dataKey="date" tickFormatter={(value) => value.slice(5)} tick={{ fill: "#6b7280", fontSize: 12 }} axisLine={false} tickLine={false} minTickGap={28} />
            <YAxis tick={{ fill: "#6b7280", fontSize: 12 }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={{ borderRadius: 12, border: "1px solid #e5e7eb" }} />
            <Legend />
            <Line name={`花费（${currency}）`} dataKey="spend" type="monotone" stroke="#ff6b1a" strokeWidth={3} />
            <Line name={`广告销售额（${currency}）`} dataKey="sales" type="monotone" stroke="#1473e6" strokeWidth={3} />
          </LineChart>
        </ResponsiveContainer>
      ) : <div className="chart-empty">当前店铺范围没有可汇总的每日趋势数据</div>}
    </main>
  );
}

export function App() {
  const [data, setData] = useState(null);
  const [realtime, setRealtime] = useState(null);
  const [status, setStatus] = useState("idle");
  const [realtimeLoadStatus, setRealtimeLoadStatus] = useState("loading");
  const [activeNav, setActiveNav] = useState("diagnostic");
  const [reviewState, setReviewState] = useState(getStoredReviewState);
  const [toast, setToast] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [diagnosticRefreshVersion, setDiagnosticRefreshVersion] = useState(0);
  const [diagnosticRefreshing, setDiagnosticRefreshing] = useState(true);
  const [diagnosticShopId, setDiagnosticShopId] = useState(PILOT_SHOP.id);
  const [diagnosticShops, setDiagnosticShops] = useState(DIAGNOSTIC_SHOPS);
  const [diagnosticWindow, setDiagnosticWindow] = useState("14d");
  const [selectedShop, setSelectedShop] = useState(ALL_SHOPS);

  async function loadData() {
    const hadData = Boolean(data);
    const hadRealtime = Boolean(realtime);
    if (hadData) setRefreshing(true);
    else setStatus("loading");
    const stamp = Date.now();
    const matureRequest = fetch(`${DATA_URL}?t=${stamp}`).then(async (response) => {
      if (!response.ok) throw new Error("mature data request failed");
      return response.json();
    });
    const realtimeRequest = fetch(`${REALTIME_DATA_URL}?t=${stamp}`).then(async (response) => {
      const contentType = response.headers.get("content-type") || "";
      if (response.status === 404 || response.status === 204) return null;
      if (!response.ok) throw new Error("realtime data request failed");
      if (!contentType.includes("json")) return null;
      return response.json();
    });

    try {
      const [matureResult, realtimeResult] = await Promise.allSettled([matureRequest, realtimeRequest]);
      if (matureResult.status === "rejected") {
        if (!hadData) setStatus("error");
        else setToast("成熟归因层刷新失败，已保留上一次成功数据。");
      } else {
        const payload = matureResult.value;
        setData({
          ...payload,
          campaigns: payload.campaigns || [],
          recommendations: payload.recommendations || [],
          advertised_products: payload.advertised_products || [],
          daily_trend: payload.daily_trend || [],
          campaign_daily_trend: payload.campaign_daily_trend || [],
          source_data: payload.source_data || [],
        });
        setStatus("ready");
      }

      if (realtimeResult.status === "fulfilled" && realtimeResult.value) {
        setRealtime(normalizeRealtime(realtimeResult.value));
        setRealtimeLoadStatus("ready");
        if (hadData && matureResult.status === "fulfilled") setToast("成熟归因层与实时监控层已刷新。");
      } else if (realtimeResult.status === "fulfilled") {
        setRealtime(null);
        setRealtimeLoadStatus("missing");
        if (hadData && matureResult.status === "fulfilled") setToast("成熟归因层已刷新；实时层尚未采集。");
      } else if (hadRealtime) {
        setRealtimeLoadStatus("refresh-error");
        if (hadData && matureResult.status === "fulfilled") setToast("成熟层已刷新；实时层刷新失败，保留上次快照。");
      } else {
        setRealtime(null);
        setRealtimeLoadStatus("error");
        if (hadData && matureResult.status === "fulfilled") setToast("成熟层已刷新；实时层暂时不可用。");
      }
    } finally {
      setRefreshing(false);
      setRefreshVersion((value) => value + 1);
    }
  }

  useEffect(() => {
    if (activeNav !== "diagnostic" && status === "idle") loadData();
  }, [activeNav, status]);
  useEffect(() => {
    const controller = new AbortController();
    fetchDiagnosticShops({ signal: controller.signal })
      .then((payload) => {
        const nextShops = normalizeDiagnosticShops(payload);
        if (!nextShops.length) return;
        setDiagnosticShops(nextShops);
        setDiagnosticShopId((current) => {
          if (nextShops.some((shop) => shop.id === current)) return current;
          const preferred = String(payload.default_shop_id || "");
          return nextShops.some((shop) => shop.id === preferred)
            ? preferred
            : nextShops[0].id;
        });
      })
      .catch((error) => {
        if (error?.name !== "AbortError") setDiagnosticShops(DIAGNOSTIC_SHOPS);
      });
    return () => controller.abort();
  }, []);
  useEffect(() => { localStorage.setItem(REVIEW_KEY, JSON.stringify(reviewState)); }, [reviewState]);
  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(""), 2600);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const shops = useMemo(() => shopOptions(data), [data]);
  const visibleData = useMemo(
    () => scopeData(data, selectedShop, shops.length),
    [data, selectedShop, shops.length],
  );
  const visibleRealtime = useMemo(
    () => scopeRealtime(realtime, selectedShop),
    [realtime, selectedShop],
  );

  useEffect(() => {
    if (selectedShop !== ALL_SHOPS && !shops.some((shop) => shop.id === selectedShop)) {
      setSelectedShop(ALL_SHOPS);
    }
  }, [selectedShop, shops]);

  const diagnosticActive = activeNav === "diagnostic";
  const diagnosticShop = diagnosticShops.find((shop) => shop.id === diagnosticShopId) || diagnosticShops[0] || PILOT_SHOP;

  if (!diagnosticActive && (status === "idle" || status === "loading")) {
    return <div className="system-state"><ArrowsClockwise className="spin" size={30} /><b>正在读取广告监控数据…</b></div>;
  }
  if (!diagnosticActive && (status === "error" || !data || !visibleData)) {
    return <div className="system-state"><Info size={30} /><b>暂时无法读取监控数据</b><button type="button" onClick={loadData}>重新加载</button></div>;
  }

  const pendingCount = (visibleData?.recommendations || []).filter(
    (item) => isReviewableAction(item) && !reviewValue(reviewState, item),
  ).length;
  const activeShop = shops.find((shop) => shop.id === selectedShop);
  const scopeShops = selectedShop === ALL_SHOPS ? shops : shops.filter((shop) => shop.id === selectedShop);
  const scopeLabel = diagnosticActive ? diagnosticShop.name : selectedShop === ALL_SHOPS
    ? `全部店铺（${shops.length}）`
    : activeShop?.name || selectedShop;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <strong>MAGIC AD</strong>
          <span className="header-divider" />
          <h1>{activeNav === "recommendations" ? "调控建议" : NAV_ITEMS.find((item) => item.id === activeNav)?.label}</h1>
        </div>
        <div className="header-controls">
          {diagnosticActive ? (
            <label className="shop-selector pilot-shop-selector">
              <Buildings size={18} weight="duotone" />
              <span className="sr-only">选择诊断店铺</span>
              <select
                value={diagnosticShop.id}
                onChange={(event) => {
                  const next = diagnosticShops.find((shop) => shop.id === event.target.value) || diagnosticShops[0] || PILOT_SHOP;
                  setDiagnosticShopId(next.id);
                  setToast(`已切换为${next.name}快照。`);
                }}
                aria-label="选择诊断店铺"
              >
                {diagnosticShops.map((shop) => <option key={shop.id} value={shop.id}>{shop.name} · {shop.currency}</option>)}
              </select>
              <CaretDown size={16} aria-hidden="true" />
            </label>
          ) : (
            <label className="shop-selector">
              <Buildings size={18} weight="duotone" />
              <span className="sr-only">店铺范围</span>
              <select
                value={selectedShop}
                onChange={(event) => {
                  setSelectedShop(event.target.value);
                  const nextShop = shops.find((shop) => shop.id === event.target.value);
                  setToast(`已切换为${event.target.value === ALL_SHOPS ? "全部店铺" : nextShop?.name || event.target.value}数据。`);
                }}
                aria-label="选择店铺范围"
              >
                <option value={ALL_SHOPS}>全部店铺（{shops.length}）</option>
                {shops.map((shop) => <option key={shop.id} value={shop.id}>{shop.name} · {currencyLabel(shop.currency)}</option>)}
              </select>
              <CaretDown size={16} aria-hidden="true" />
            </label>
          )}
          {diagnosticActive ? (
            <>
              <span className="date-control"><small>小时层</small>当前小时 · 暂定 <CalendarBlank size={18} /></span>
              <span className="generated-time"><small>成熟归因层</small>D-2 · {Number.parseInt(diagnosticWindow, 10) || 14}日窗口</span>
            </>
          ) : (
            <>
              <span className="date-control"><small>数据来源</small>{compactDate(data.meta.source_start_date)}–{compactDate(data.meta.source_end_date)} <CalendarBlank size={18} /></span>
              <span className="generated-time"><small>生成时间</small>{data.meta.generated_at.slice(0, 16).replace("T", " ")}</span>
            </>
          )}
          <button
            className="sync-button"
            type="button"
            onClick={diagnosticActive ? () => setDiagnosticRefreshVersion((value) => value + 1) : loadData}
            disabled={diagnosticActive ? diagnosticRefreshing : refreshing}
            aria-label={diagnosticActive ? `实时刷新${diagnosticShop.name}诊断` : "刷新数据"}
          >
            <i className="status-dot" />
            {diagnosticActive ? diagnosticRefreshing ? "正在直连API" : "实时刷新" : refreshing ? "正在同步" : "数据已同步"}
            <ArrowsClockwise className={(diagnosticActive ? diagnosticRefreshing : refreshing) ? "spin" : ""} size={17} />
          </button>
          <span className="safety-pill"><Info size={17} weight="fill" />{diagnosticActive ? "人工确认后才会修改广告" : "只读建议 · 审核不会修改广告"}</span>
        </div>
      </header>

      <nav className="tabbar" aria-label="广告监控导航">
        {NAV_ITEMS.map((item) => (
          <button
            className={activeNav === item.id ? "active" : ""}
            key={item.id}
            type="button"
            aria-current={activeNav === item.id ? "page" : undefined}
            onClick={() => setActiveNav(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <div className={`content-shell ${diagnosticActive ? "diagnostic-content-shell" : ""}`}>
        <div className="mobile-safety"><Info size={17} weight="fill" />{diagnosticActive ? "人工确认后才会修改广告" : "只读建议 · 审核不会修改广告"}</div>
        {diagnosticActive ? (
          <AdDiagnosticView key={diagnosticShop.id} shop={diagnosticShop} refreshToken={diagnosticRefreshVersion} onLoadingChange={setDiagnosticRefreshing} onWindowChange={setDiagnosticWindow} />
        ) : (
          <>
            <DataHealthNotice data={data} />
            <DualTimeStatus data={data} realtime={visibleRealtime} realtimeLoadStatus={realtimeLoadStatus} scopeLabel={scopeLabel} />
            <SummaryStrip data={visibleData} pendingCount={pendingCount} scopeLabel={scopeLabel} shops={shops} scopeShops={scopeShops} />
            {activeNav === "recommendations" && (visibleData.recommendations.length
              ? <ReviewWorkspace key={selectedShop} data={visibleData} realtime={visibleRealtime} realtimeLoadStatus={realtimeLoadStatus} reviewState={reviewState} setReviewState={setReviewState} notify={setToast} showShop={selectedShop === ALL_SHOPS && shops.length > 1} shops={shops} />
              : <EmptyRecommendationsView />)}
            {activeNav === "realtime" && <RealtimeAlertsView key={selectedShop} realtime={visibleRealtime} loadStatus={realtimeLoadStatus} scopeLabel={scopeLabel} refreshVersion={refreshVersion} showShop={selectedShop === ALL_SHOPS && shops.length > 1} advertisedProducts={visibleData.advertised_products} />}
            {activeNav === "rules" && <RulesView data={visibleData} />}
            {activeNav === "campaigns" && <CampaignView data={visibleData} showShop={selectedShop === ALL_SHOPS && shops.length > 1} shops={shops} />}
            {activeNav === "performance" && <PerformanceView data={visibleData} scopeShops={scopeShops} />}
          </>
        )}
      </div>

      {toast && <div className="toast" role="status"><CheckCircle size={19} weight="fill" />{toast}</div>}
    </div>
  );
}
