import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ArrowClockwise,
  ChartLine,
  CheckCircle,
  Database,
  Info,
  MagnifyingGlass,
  Package,
  Question,
  ShieldCheck,
  SlidersHorizontal,
  SortAscending,
  SortDescending,
  Target,
  Warning,
  X,
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
import { fetchDiagnostic, fetchSearchTermsPage } from "./adDiagnosticApi.js";
import { SpControlDrawer } from "./SpControlDrawer.jsx";
import {
  CAMPAIGNS_PER_PAGE,
  DEFAULT_CAMPAIGN_ID,
  PILOT_SHOP,
  acosState,
  buildPublishedCampaignFallbackModel,
  campaignIdOf,
  campaignAdType,
  campaignAdTypeLabel,
  campaignBiddingStrategy,
  campaignBudgetMatrix,
  campaignBudgetStatus,
  campaignLifecycleLabel,
  campaignMetricValue,
  campaignNameOf,
  campaignPerformanceGrade,
  campaignPerformanceLabel,
  campaignPerformanceStatus,
  campaignPlacementAdjustmentLabel,
  campaignPriorityScore,
  campaignStateOf,
  campaignWindowMetrics,
  currentHourCampaign,
  deepReportHighlightRows,
  deepReportRows,
  expandIdentity,
  filterCampaigns,
  focusProducts,
  freshnessLabel,
  grainLabel,
  hourlyMetricDisplay,
  keywordPopoverPosition,
  missingValue,
  mergeDiagnosticModels,
  mergeCampaignDetailMetrics,
  mergePublishedCampaignMetrics,
  normalizeDiagnosticPayload,
  paginateCampaigns,
  placementPerformanceRows,
  placementPerformanceSummary,
  rowsOf,
  searchTermDataRevision,
  searchTermRecommendation,
  searchTermStructureSummary,
  searchTermSuggestion,
  searchTermValue,
  skuControlMetrics,
  sourceLayerLabel,
  sortCampaigns,
  sortCampaignsByMetric,
  valueOf,
} from "./adDiagnosticModel.js";

let echartsLoader;

function loadEcharts() {
  if (!echartsLoader) {
    echartsLoader = Promise.all([
      import("echarts/core"),
      import("echarts/lib/chart/radar.js"),
      import("echarts/lib/component/radar.js"),
      import("echarts/lib/renderer/installCanvasRenderer.js"),
    ]).then(([core, , , canvasRenderer]) => {
      core.use([canvasRenderer.install]);
      return core;
    });
  }
  return echartsLoader;
}

const DETAIL_TABS = [
  { id: "overview", label: "决策总览", help: "汇总成熟14日规则、当日小时信号、冲突和保护条件。先看方向，再决定是否需要人工复核。" },
  { id: "structure", label: "投放结构", help: "查看活动、广告组、广告商品、关键词、商品投放、否定投放及对应表现，用于定位问题发生在哪个层级。" },
];

const CAMPAIGN_WINDOWS = [
  { id: "7d", label: "近7天" },
  { id: "14d", label: "近14天" },
  { id: "30d", label: "近30天" },
];

const CAMPAIGN_SORT_OPTIONS = [
  { id: "default", label: "综合排序" },
  { id: "default_bid", label: "默认竞价" },
  { id: "total_target_count", label: "总投放数" },
  { id: "advertised_product_count", label: "商品" },
  { id: "impressions", label: "展示量" },
  { id: "clicks", label: "点击量" },
  { id: "ctr", label: "点击率" },
  { id: "spend", label: "总成本" },
  { id: "cpc", label: "CPC" },
  { id: "orders", label: "购买量" },
  { id: "cvr", label: "购买率" },
  { id: "sales", label: "销售额" },
  { id: "acos", label: "ACoS" },
  { id: "roas", label: "ROAS" },
];

const CAMPAIGN_MATCH_FILTERS = [
  { id: "all", label: "全部" },
  { id: "exact", label: "精准" },
  { id: "broad", label: "广泛" },
  { id: "phrase", label: "词组" },
  { id: "auto", label: "Auto" },
];

const ACTION_HELP = {
  DECREASE_BID: "建议下调命中的关键词或商品投放竞价，不代表下调整个活动。可在广告调控面板预览并人工确认。",
  INCREASE_BID: "建议提高命中的投放对象竞价，但仍须通过利润、库存和生命周期保护。可在广告调控面板预览并人工确认。",
  INCREASE_BUDGET: "建议评估提高活动日预算。预算不足本身不是充分条件，必须同时确认利润、库存和转化。",
  PAUSE: "建议人工评估暂停对应对象；必须在广告调控面板二次确认后才会提交。",
  REVIEW_TARGET: "该投放对象需要人工检查，现有证据尚未形成明确调价动作。",
  MONITOR_ONLY: "当前没有形成可执行建议，只继续观察成熟层与当日小时层变化。",
};

const METRIC_HELP = {
  "当前小时花费": "站点当天截至最新返回小时的累计花费，不是单独某一个小时。数据仍会回补，只用于监控。",
  "当前小时订单": "站点当天截至最新返回小时的累计归因订单，尚未成熟，不能替代D-2结论。",
  "当前小时 ACoS": "当日暂定花费 ÷ 当日暂定销售额。只用于判断方向是否恶化或改善。",
  "14日成熟花费": "截至D-2的连续14天SP活动花费，是规则判断的主要稳定窗口。",
  "14日成熟销售额": "截至D-2的连续14天广告归因销售额，与成熟花费处于同一窗口。",
  "14日成熟 ACoS": "成熟14日花费 ÷ 成熟14日广告销售额，是调价方向的重要依据，但不是唯一依据。",
  "可售库存": "赛狐Listing接口返回的当前可售数量。库存不足时，即使广告效率好也不应盲目扩量。",
  "在途库存": "正在入仓或调拨、尚未全部转为可售的库存，不能等同于当前可售库存。",
  "近7日销量": "该SKU近7日总销量，用于判断库存消耗速度。",
  "近30日销量": "该SKU近30日全业务销量，用于识别长期销售速度和库存风险。",
  "可售天数": "赛狐产品分析接口返回的库存可售天数，用于判断当前库存是否足以支撑扩量。",
  "毛利率": "该SKU的整体利润率，不是广告活动利润率。它决定广告可承受成本的大致上限。",
  "估算盈亏平衡 ACoS": "按（所选周期SKU利润 + 所选周期全部广告成本）÷ 所选周期SKU销售额估算，是SKU口径的广告承受上限。",
  "估算盈亏 ACoS": "按（所选周期SKU利润 + 所选周期全部广告成本）÷ 所选周期SKU销售额估算，是SKU口径的广告承受上限。",
  "SKU SP ACoS": "该SKU在所选周期内的SP广告成本 ÷ SP广告销售额，不等同于当前单个广告活动的ACoS。",
  "ACoS 安全余量": "所选周期的估算盈亏平衡ACoS减去SKU SP ACoS。正值表示仍低于盈亏线，但不等于可以直接扩量。",
  "SP销售占比": "该SKU在所选周期内的SP广告销售额 ÷ 全部销售额，用于判断销售对SP广告的依赖程度。",
  "退款率": "该SKU在所选利润窗口内的退款比例；退款风险较高时不应盲目扩大广告。",
  "14日利润": "该SKU在成熟窗口内的全业务利润，包含广告与非广告经营结果。",
  "14日SP成本": "SKU成熟窗口内的SP广告成本，是SKU经营成本，不等于当前单个SP活动的成本。",
};

const FACT_HELP = {
  "执行门禁": "BLOCK表示证据不足必须阻断；REVIEW表示只能人工复核；MONITOR_ONLY表示继续观察。系统不会自动执行，只有人工确认的单次操作才会提交。",
  "优先级": "综合成熟规则、花费影响、生命周期和风险决定。高优先级代表应先看，不代表允许自动执行。",
  "置信度": "证据完整度与双时间层一致性的综合评分，不是预测成功率。存在暂定异常时会降低。",
  "小时层站点日期": "按Amazon广告站点时区计算的业务日期，不使用北京时间直接替代。",
  "最新返回小时": "赛狐小时接口当前已回填到的最晚小时；落后于当地当前时间属于正常延迟。",
  "小时层暂定标记": "true表示当日数据仍可能发生归因回补，不能作为最终成熟结果。",
  "成熟数据截止": "成熟层最后一个业务日期。正常情况下应为当前业务日的D-2。",
  "日预算": "活动级每日预算。缺预算只说明流量可能受限，不代表加预算一定有利。",
  "竞价策略": "Amazon SP活动的竞价策略配置，会影响实际竞价调整方式。",
  "SKU上架时间": "用于判断新品阶段的正式上架时间，不使用第一次销售时间替代。",
  "SKU生命周期": "开售90天内为新品；缺少或无法唯一匹配上架时间时为unknown并阻断自动判断。",
  "上架天数": "从Listing上架日期计算到站点业务日，用于新品保护。",
  "新品阶段": "new表示新品保护期，established表示成熟SKU，unknown表示证据不足。",
  "广告组": "当前SKU所属的广告组。广告组可能包含多个SKU，因此组级表现不能直接归因给单个SKU。",
  "广告商品状态": "该adId在Amazon SP中的投放状态，用于判断是否具备展示资格，不代表一定获得流量。",
  "SKU": "卖家自定义库存编码，用于连接广告商品、Listing、库存、销量和利润数据。",
  "ASIN": "Amazon商品标识，用于核对广告商品、Listing及广告归因购买商品。",
  "adId": "Amazon广告商品记录ID，是把广告商品表现精确关联到SKU或ASIN的重要键。",
  "上架时间": "Listing正式上架时间，用于判断新品阶段；不会用第一次销售时间替代。",
  "在线状态": "Listing当前可售或在线状态。不可售时即使广告效率良好，也不应扩量。",
  "售价": "Listing当前售价，属于SKU经营上下文，不是广告活动归因销售额。",
  "整体数据质量": "complete表示必要来源已返回，partial表示至少一项不完整；它不等同于数据绝对正确。",
  "完整度": "必要数据源或字段的覆盖比例，不代表数值准确率。",
  "API抓取时间": "后台任务向赛狐API取得结果的时间，不等于指标对应的业务日期。",
};

const SECTION_HELP = {
  "证据链": "支持当前建议方向的成熟规则与数据依据。没有证据链时，建议自动降级为不可执行。",
  "冲突信号": "与主建议相反、或可能改变决策方向的信号。出现冲突时必须人工复核。",
  "阻断项": "数据缺失、范围不明或安全规则不满足时产生。存在任何阻断项都不能执行调整。",
  "当前小时确认": "用站点当天小时数据核对成熟建议方向。小时层只能确认趋势，不能单独生成最终动作。",
  "保护条件": "新品、库存、利润或映射风险等保护规则，防止机械追求低ACoS。",
  "Top浪费搜索词（0订单按花费）": "成熟窗口内有花费但没有归因订单的搜索词，按花费排序。需结合点击量和生命周期判断，不能仅凭0订单立即否定。",
  "Top转化搜索词": "成熟窗口内产生订单的搜索词，优先帮助识别可保留、提价或单独建组的对象。",
  "关键词价值榜": "优先展示搜索词的价值结论、点击样本、转化率和ACoS，帮助快速识别核心词、潜力词及转化偏贵的词。",
  "待止损搜索词": "成熟窗口内有花费但没有归因订单的搜索词；达到点击样本门槛后才标记为止损候选。",
  "广告位效率": "按搜索顶部、其余搜索位置、商品页等广告位比较成熟花费、订单和ACoS。",
  "当前小时广告位": "站点当天各广告位的小时明细，仍处于暂定回填状态。",
  "当前小时投放对象": "站点当天关键词或商品投放的小时明细，用来验证成熟建议方向。",
  "14日成熟每日趋势": "把成熟窗口拆成每天，避免只看14天合计而忽略近期恶化或改善。",
  "成熟规则建议": "规则引擎在成熟窗口产生的活动级或投放级建议；不同粒度不能互相替代。",
  "广告归因购买商品": "广告点击后买家实际购买的ASIN。它可能与被广告的SKU不同，可用于识别关联购买。",
  "30日FBA退货原因": "该SKU的退货原因聚合，不包含买家敏感信息，用于判断产品质量风险。",
  "数据源与时效": "每行对应一个实时API、小时API、成熟数据或下载报表。先看状态和截止日期，再相信指标。",
  "双时间层表现": "把站点当天小时层与截至D-2的成熟14日层并列查看。成熟层决定主方向，小时层只负责预警和确认。",
  "成熟深度信号": "进一步下钻成熟搜索词、投放和广告位，判断问题发生在哪个层级，避免只看活动总ACoS。",
  "活动与聚焦SKU上下文": "同时展示活动配置与当前SKU经营信息。两者用于共同判断，但不会把活动级数据强行分摊给SKU。",
  "Listing 与生命周期": "核对当前广告商品对应的SKU、ASIN、adId、上架时间和新品阶段，决定是否启用新品保护。",
  "库存、销量与利润护栏": "广告建议必须同时满足库存、销量和利润安全边界；经营字段不足时不生成自动扩量结论。",
  "当前小时广告组表现": "站点当天截至最新返回小时的广告组累计表现，仍可能延迟回填，只用于监控。",
  "当前小时广告商品表现": "站点当天广告商品级累计表现，可用于观察具体adId，但不能替代成熟归因。",
  "当前小时投放表现": "站点当天关键词或商品投放级累计表现，用来检查成熟建议是否出现明显反向信号。",
  "广告组": "活动下的广告组配置与状态，是连接活动、广告商品和投放对象的结构层。",
  "关键词投放": "当前SP广告组中的关键词、匹配方式、竞价和状态配置。",
  "商品投放": "当前SP广告组中的ASIN或类目投放、竞价和状态配置。",
  "成熟广告组表现": "截至D-2的广告组级稳定归因表现，用于定位活动内部差异。",
  "成熟投放表现": "截至D-2的关键词或商品投放级表现，是精准调价与否定建议的主要依据。",
  "成熟搜索词": "买家真实搜索词的D-2成熟表现。它与投放关键词不是同一个概念，需要分别判断。",
  "否定关键词": "当前广告组或活动已配置的否定关键词，用于避免重复建议或误判流量缺失。",
  "否定商品投放": "当前已配置的否定ASIN或类目投放，用于核对商品流量是否被主动排除。",
  "广告位表现": "搜索顶部、其余搜索位置和商品页等位置的表现，用于辅助判断广告位加价比例。",
  "SKU每日销售趋势": "该SKU包含自然单与广告单的每日经营趋势，用于判断库存、利润和生命周期。",
  "成熟广告商品表现": "截至D-2且能匹配当前adId、SKU或ASIN的广告商品级表现；匹配失败时保持未知。",
  "缺失字段": "本次诊断需要但赛狐API或本地成熟数据没有返回的字段。缺失关键字段会降低置信度或触发阻断。",
  "质量预警": "数据已返回，但存在延迟、范围不完整或口径风险，需要人工复核。",
  "接口错误": "调用赛狐API或读取成熟数据失败。错误来源不会由前端猜值补齐。",
};

function dedupeCampaigns(rows) {
  const result = new Map();
  rows.forEach((row) => {
    const id = campaignIdOf(row);
    if (id) result.set(id, { ...result.get(id), ...row });
  });
  return [...result.values()];
}

function formatNumber(value, digits = 0) {
  if (missingValue(value) || !Number.isFinite(Number(value))) return null;
  return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function formatMoney(value, currency = PILOT_SHOP.currency) {
  if (missingValue(value) || !Number.isFinite(Number(value))) return null;
  return new Intl.NumberFormat("zh-CN", { style: "currency", currency, maximumFractionDigits: 2 }).format(Number(value));
}

function formatRatio(value, digits = 1) {
  if (missingValue(value) || !Number.isFinite(Number(value))) return null;
  const numeric = Number(value);
  return `${(Math.abs(numeric) <= 1 ? numeric * 100 : numeric).toFixed(digits)}%`;
}

function formatRatioDelta(value, digits = 1) {
  if (missingValue(value) || !Number.isFinite(Number(value))) return null;
  const numeric = Math.abs(Number(value)) <= 1 ? Number(value) * 100 : Number(value);
  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(digits)}pp`;
}

function formatPercentagePoints(value, digits = 1) {
  if (missingValue(value) || !Number.isFinite(Number(value))) return null;
  return `${Number(value).toFixed(digits)}%`;
}

function formatPercentagePointDelta(value, digits = 1) {
  if (missingValue(value) || !Number.isFinite(Number(value))) return null;
  const numeric = Math.abs(Number(value)) < 0.05 ? 0 : Number(value);
  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(digits)}pp`;
}

function formatSignedRatio(value, digits = 1) {
  if (missingValue(value) || !Number.isFinite(Number(value))) return null;
  const numeric = Number(value) * 100;
  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(digits)}%`;
}

function formatAcos(value, row, digits = 1) {
  const state = acosState(row, value);
  if (state === "available") return formatRatio(value, digits);
  if (state === "no_sales") return "∞（销售额为 0）";
  if (state === "no_activity") return "—（无花费/销售额）";
  return null;
}

function formatRoas(value) {
  if (missingValue(value) || !Number.isFinite(Number(value))) return null;
  return `${Number(value).toFixed(2)}x`;
}

function formatDateTime(value) {
  if (missingValue(value)) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value).replace("T", " ");
  return parsed.toLocaleString("zh-CN", { hour12: false });
}

function displayValue(value, formatter) {
  const formatted = formatter ? formatter(value) : missingValue(value) ? null : String(value);
  return formatted ?? "未知（API未返回）";
}

function metricValue(row, ...keys) {
  return valueOf(row, ...keys);
}

function firstPresent(...values) {
  return values.find((value) => !missingValue(value)) ?? null;
}

function skuOperatingContext(model, selectedProduct) {
  const product = selectedProduct || {};
  const listing = model?.listingContext || {};
  const online = product.online_product || product.onlineProduct || {};
  const analysis = product.product_analysis || product.productAnalysis || {};
  const inventory = product.inventory || listing.inventory || online;
  const financial = product.finance || product.financial || product.financials || listing.finance || listing.financial || listing.financials || {};
  const sales = product.sales || listing.sales || online;
  return { product, listing, online, analysis, inventory, financial, sales };
}

function campaignWindowDays(window = "14d") {
  const days = Number.parseInt(String(window), 10);
  return [7, 14, 30].includes(days) ? days : 14;
}

function windowedSkuOperatingContext(model, selectedProduct, window = "14d") {
  const context = skuOperatingContext(model, selectedProduct);
  const operating = context.product?.operating_windows?.[window] || context.product?.operatingWindows?.[window];
  const financial = operating?.finance && typeof operating.finance === "object"
    ? operating.finance
    : window === "14d"
      ? context.financial
      : {};
  return { ...context, financial };
}

function metricHelp(label) {
  if (METRIC_HELP[label]) return METRIC_HELP[label];
  if (/^近(?:7|14|30)日销量$/.test(String(label))) return "所选时间窗口内该SKU的全业务销量，包含自然单与广告单。";
  if (label === "日均销量") return "所选时间窗口销量 ÷ 窗口天数，用于比较不同周期的销售速度。";
  if (/^(?:7|14|30)日利润$/.test(String(label))) return "该SKU在所选时间窗口内的全业务利润，包含广告与非广告经营结果。";
  if (/^(?:7|14|30)日SP成本$/.test(String(label))) return "该SKU在所选时间窗口内的SP广告成本，不等于当前单个SP活动的成本。";
  if (String(label).includes("广告成本")) return "SKU成熟窗口内对应广告类型的实际成本。它是SKU经营成本，不等于当前SP活动单独产生的成本。";
  return "";
}

function actionHelp(value) {
  return ACTION_HELP[String(value || "").toUpperCase()] || "这是基于现有证据生成的建议方向；执行前仍需核对门禁、冲突和保护条件。";
}

function grainHelp(grain) {
  const key = String(grain || "unknown").toLowerCase();
  return ({
    campaign: "活动级：指标属于整个广告活动，不能直接分摊到单个SKU。",
    ad_group: "广告组级：指标属于活动内的广告组，仍不能自动等同于某个关键词或SKU。",
    adgroup: "广告组级：指标属于活动内的广告组，仍不能自动等同于某个关键词或SKU。",
    ad_product: "广告商品级：指标与具体adId、SKU或ASIN关联。",
    advertised_product: "广告商品级：指标与具体adId、SKU或ASIN关联。",
    target: "投放级：指标属于关键词或商品投放对象，是竞价调整的主要粒度。",
    keyword: "投放级：指标属于具体关键词及匹配方式。",
    product_target: "投放级：指标属于具体ASIN或类目商品投放。",
    sku: "SKU经营数据：包含自然单和广告单，用于判断库存和利润。",
    listing: "SKU经营数据：来自Listing或经营接口，不是广告活动指标。",
    placement: "广告位级：按搜索顶部、其余搜索位置、商品页等位置聚合。",
  })[key] || "粒度未知：API没有返回足够的归属信息，不能向下分摊。";
}

function freshnessHelp(value) {
  const key = String(value || "unknown").toLowerCase();
  if (["today", "hour", "hourly", "current_hour", "provisional"].includes(key)) return "当日小时层：站点当天已返回小时行的累计值，仍会延迟和回补，只用于监控与方向确认。";
  if (["recent_hour", "recent_complete_hour"].includes(key)) return "当日小时接口尚未回填时，展示最近一个可用营业日的小时明细；标题会标注实际日期，不参与当天预算和调控判断。";
  if (["mature", "mature_14d", "d-2", "d2"].includes(key)) return "D-2成熟层：截至D-2的稳定归因数据，当前规则主要依据这一层判断。";
  if (["live", "configuration", "config"].includes(key)) return "当前活动、Listing或经营数据。";
  return "时间层未知：API未返回可验证的抓取时间或业务截止日期。";
}

function FloatingHelp({ title, text, label = null, className = "", iconSize = 14 }) {
  const tooltipId = useId();
  const triggerRef = useRef(null);
  const tooltipRef = useRef(null);
  const [position, setPosition] = useState(null);
  const open = Boolean(position);

  function show() {
    const trigger = triggerRef.current;
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    const width = Math.min(320, window.innerWidth - 24);
    setPosition({
      measured: false,
      placement: "bottom",
      left: Math.max(12, Math.min(window.innerWidth - width - 12, rect.left + rect.width / 2 - width / 2)),
      top: rect.bottom + 10,
      width,
    });
  }

  function hide() {
    setPosition(null);
  }

  useLayoutEffect(() => {
    if (!position || position.measured || !triggerRef.current || !tooltipRef.current) return;
    const triggerRect = triggerRef.current.getBoundingClientRect();
    const tooltipRect = tooltipRef.current.getBoundingClientRect();
    const gap = 10;
    const edge = 12;
    const spaceBelow = window.innerHeight - triggerRect.bottom - gap - edge;
    const spaceAbove = triggerRect.top - gap - edge;
    const placement = tooltipRect.height <= spaceBelow || spaceBelow >= spaceAbove ? "bottom" : "top";
    const rawTop = placement === "bottom" ? triggerRect.bottom + gap : triggerRect.top - gap - tooltipRect.height;
    const maxTop = Math.max(edge, window.innerHeight - edge - Math.min(tooltipRect.height, window.innerHeight - edge * 2));
    setPosition({
      measured: true,
      placement,
      left: Math.max(edge, Math.min(window.innerWidth - tooltipRect.width - edge, triggerRect.left + triggerRect.width / 2 - tooltipRect.width / 2)),
      top: Math.max(edge, Math.min(maxTop, rawTop)),
      width: position.width,
    });
  }, [position]);

  useEffect(() => {
    if (!open) return undefined;
    const close = () => setPosition(null);
    const closeOutside = (event) => {
      if (!triggerRef.current?.contains(event.target) && !tooltipRef.current?.contains(event.target)) close();
    };
    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, true);
    document.addEventListener("pointerdown", closeOutside);
    return () => {
      window.removeEventListener("resize", close);
      window.removeEventListener("scroll", close, true);
      document.removeEventListener("pointerdown", closeOutside);
    };
  }, [open]);

  return (
    <span className={`floating-help ${label ? "floating-help-text" : ""}`}>
      <button
        aria-describedby={open ? tooltipId : undefined}
        aria-label={`${title}说明`}
        className={`floating-help-trigger ${className}`}
        onBlur={hide}
        onClick={(event) => { event.stopPropagation(); show(); }}
        onFocus={show}
        onKeyDown={(event) => { if (event.key === "Escape") hide(); }}
        onMouseEnter={show}
        onMouseLeave={hide}
        ref={triggerRef}
        type="button"
      >
        {label || <Question size={iconSize} weight="bold" />}
      </button>
      {open && createPortal(
        <span
          className="floating-help-popover"
          data-placement={position.placement}
          id={tooltipId}
          ref={tooltipRef}
          role="tooltip"
          style={{ left: position.left, top: position.top, width: position.width }}
        >
          <b>{title}</b>
          <span>{text}</span>
        </span>,
        document.body,
      )}
    </span>
  );
}

function ExplainedLabel({ label, help = "" }) {
  return (
    <span className="explained-label">
      {label}
      {help && <FloatingHelp title={label} text={help} />}
    </span>
  );
}

function MetricCard({ label, value, formatter, grain, freshness, tone = "default", showMeta = true }) {
  const unknown = missingValue(value) || (formatter && formatter(value) === null);
  return (
    <article className={`diagnostic-metric ${tone} ${unknown ? "unknown" : ""} ${showMeta ? "" : "no-meta"}`}>
      <div><ExplainedLabel label={label} help={metricHelp(label)} /><b>{displayValue(value, formatter)}</b></div>
      {showMeta && <footer><ScopeTag grain={grain} /><FreshnessTag value={freshness} /></footer>}
    </article>
  );
}

function ScopeTag({ grain }) {
  if (["sku", "listing"].includes(String(grain || "").toLowerCase())) return null;
  const label = grainLabel(grain);
  return <FloatingHelp className={`scope-tag ${String(grain || "unknown").replaceAll("_", "-")}`} label={label} text={grainHelp(grain)} title={label} />;
}

function FreshnessTag({ value }) {
  if (["live", "configuration", "config"].includes(String(value || "").toLowerCase())) return null;
  const label = freshnessLabel(value);
  const className = label.startsWith("当前小时") || label.startsWith("最近可用小时") ? "provisional" : label.startsWith("D-2") ? "mature" : label.startsWith("实时读取") ? "live" : "unknown";
  return <FloatingHelp className={`freshness-tag ${className}`} label={label} text={freshnessHelp(value)} title={label} />;
}

function StatusPill({ value }) {
  const state = String(value || "unknown").toLowerCase();
  const positive = ["enabled", "active", "running", "complete", "success", "ok", "投放中"].includes(state);
  const warning = ["partial", "warning", "stale", "review"].includes(state);
  return <span className={`diagnostic-status ${positive ? "positive" : warning ? "warning" : "neutral"}`}><i />{value || "未知"}</span>;
}

function EmptyPanel({ icon: Icon = Info, title, copy }) {
  return (
    <div className="diagnostic-empty">
      <Icon size={34} weight="duotone" />
      <b>{title}</b>
      <span>{copy}</span>
    </div>
  );
}

function FactGrid({ items, showMeta = true }) {
  return (
    <dl className={`diagnostic-fact-grid ${showMeta ? "" : "no-meta"}`}>
      {items.map((item) => (
        <div key={item.label}>
          <dt><ExplainedLabel label={item.label} help={item.help || FACT_HELP[item.label] || ""} /></dt>
          <dd className={missingValue(item.value) ? "unknown-value" : ""}>{displayValue(item.value, item.formatter)}</dd>
          {showMeta && <small><ScopeTag grain={item.grain} />{item.freshness && <FreshnessTag value={item.freshness} />}</small>}
        </div>
      ))}
    </dl>
  );
}

function rowText(row, ...keys) {
  if (typeof row === "string") return row;
  return String(valueOf(row, ...keys) || "未知（API未返回）");
}

function EvidenceList({ title, rows, kind = "evidence" }) {
  if (!rows.length) return <EmptyPanel icon={Info} title={<ExplainedLabel label={`${title}未返回`} help={SECTION_HELP[title] || ""} />} copy="该部分不会由前端猜测补齐，并会影响建议可信度。" />;
  return (
    <section className={`evidence-list ${kind}`}>
      <h4><ExplainedLabel label={title} help={SECTION_HELP[title] || ""} /></h4>
      {rows.map((row, index) => {
        const grain = typeof row === "object" ? valueOf(row, "grain", "scope", "level") : null;
        const freshness = typeof row === "object" ? valueOf(row, "freshness", "time_layer", "window") : null;
        return (
          <article key={valueOf(row, "code", "id") || `${kind}-${index}`}>
            {kind === "blocker" ? <Warning size={18} weight="fill" /> : kind === "conflict" ? <Info size={18} weight="fill" /> : <CheckCircle size={18} weight="fill" />}
            <span>
              <b>{rowText(row, "label", "title", "code", "signal", "status")}</b>
              <small>{rowText(row, "message", "description", "reason", "value")}</small>
              <em>{grain && <ScopeTag grain={grain} />}{freshness && <FreshnessTag value={freshness} />}</em>
            </span>
          </article>
        );
      })}
    </section>
  );
}

function CompactDecisionSummary({ decision, today, todayLayer, currentHour, mature, matureLayer }) {
  const primaryAction = decision.primaryAction || {};
  const recommendation = valueOf(primaryAction, "label", "title", "action_name") || valueOf(decision, "title", "recommendation_text", "summary") || decision.action || "未知（API未返回）";
  const reason = valueOf(primaryAction, "reason", "rationale", "message") || valueOf(decision, "reason", "rationale", "description") || "建议必须由成熟数据、当前信号与经营护栏共同解释。";
  const confidence = Number(decision.confidence);
  const confidenceValue = Number.isFinite(confidence) ? (confidence <= 1 ? `${Math.round(confidence * 100)}%` : `${Math.round(confidence)}%`) : "未知";
  const sections = [
    { title: "证据链", rows: rowsOf(decision.evidence), kind: "evidence" },
    { title: "冲突信号", rows: rowsOf(decision.conflicts), kind: "conflict" },
    { title: "阻断项", rows: rowsOf(decision.blockers), kind: "blocker" },
    { title: "当前小时确认", rows: rowsOf(decision.todayConfirmation), kind: "conflict" },
    { title: "保护条件", rows: rowsOf(decision.protections), kind: "blocker" },
  ].filter((section) => section.rows.length);
  const sectionSummary = sections.length ? sections.map((section) => `${section.title} ${section.rows.length}`).join(" · ") : "暂无补充依据";
  const latestHour = missingValue(currentHour.latestHour) ? "最新小时未返回" : `最新返回 ${currentHour.latestHour} 时`;
  const currentDate = valueOf(todayLayer, "report_date", "date") || "站点日期未返回";
  const matureDate = valueOf(matureLayer, "data_through", "source_end_date", "report_end_date") || "截止日期未返回";
  const metricGroups = [
    {
      title: "当前小时·暂定",
      meta: `${currentDate} · ${latestHour}`,
      values: [
        { label: "花费", value: metricValue(today, "spend", "costs", "cost"), formatter: formatMoney },
        { label: "订单", value: metricValue(today, "orders", "order_count"), formatter: (value) => formatNumber(value, 0) },
        { label: "ACoS", value: metricValue(today, "acos"), formatter: formatRatio },
      ],
    },
    {
      title: "D-2成熟·14日",
      meta: `数据截止 ${matureDate}`,
      values: [
        { label: "花费", value: metricValue(mature, "spend", "costs", "cost"), formatter: formatMoney },
        { label: "销售额", value: metricValue(mature, "sales", "attributed_sales"), formatter: formatMoney },
        { label: "ACoS", value: metricValue(mature, "acos"), formatter: formatRatio },
      ],
    },
  ];

  return (
    <section className={`decision-summary-compact ${String(decision.gate || "block").toLowerCase()}`}>
      <header>
        <div className="decision-summary-copy">
          <span className="decision-eyebrow"><ExplainedLabel label="判断摘要" help="这是原决策审计区的精简版。此处只展示结论与依据，实际修改需进入调控面板确认。" /></span>
          <h4><ExplainedLabel label={recommendation} help={actionHelp(decision.action || recommendation)} /></h4>
          <p>{reason}</p>
        </div>
        <dl className="decision-summary-status">
          <div><dt><ExplainedLabel label="门禁" help={FACT_HELP["执行门禁"]} /></dt><dd>{decision.gate}</dd></div>
          <div><dt><ExplainedLabel label="优先级" help={FACT_HELP["优先级"]} /></dt><dd>{valueOf(decision, "priority", "priority_level") || "未知"}</dd></div>
          <div><dt><ExplainedLabel label="置信度" help={FACT_HELP["置信度"]} /></dt><dd>{confidenceValue}</dd></div>
        </dl>
      </header>

      <div className="decision-summary-metrics">
        {metricGroups.map((group) => (
          <article key={group.title}>
            <div><b>{group.title}</b><small>{group.meta}</small></div>
            <dl>
              {group.values.map((metric) => (
                <div key={metric.label}><dt>{metric.label}</dt><dd className={missingValue(metric.value) ? "unknown-value" : ""}>{displayValue(metric.value, metric.formatter)}</dd></div>
              ))}
            </dl>
          </article>
        ))}
      </div>

      <details className="decision-summary-rationale">
        <summary><span><b>为什么这样建议</b><small>{sectionSummary}</small></span></summary>
        {sections.length ? (
          <div className="decision-summary-evidence">
            {sections.map((section) => <EvidenceList key={section.title} title={section.title} rows={section.rows} kind={section.kind} />)}
          </div>
        ) : <p>本次没有返回可展开的补充依据，请先完成数据复核。</p>}
      </details>
    </section>
  );
}

function DataTable({ title, rows, columns, grain, freshness, emptyCopy, rowTone, summaryRow = null, tableClassName = "", showMeta = true }) {
  const records = rowsOf(rows);
  const cells = (row) => columns.map((column) => {
    const value = column.keys ? valueOf(row, ...column.keys) : column.value?.(row);
    const formatted = column.rowFormatter ? column.rowFormatter(value, row) : column.formatter ? column.formatter(value) : missingValue(value) ? null : String(value);
    return <td className={formatted === null ? "unknown-value" : ""} key={column.label}>{formatted ?? "未知（API未返回）"}</td>;
  });
  return (
    <section className="diagnostic-table-section">
      <div className="diagnostic-section-title"><h4><ExplainedLabel label={title} help={SECTION_HELP[title] || ""} /></h4><span>{records.length} 条{showMeta && <> · <ScopeTag grain={grain} />{freshness && <FreshnessTag value={freshness} />}</>}</span></div>
      {records.length ? (
        <div className="diagnostic-table-scroll">
          <table className={tableClassName}>
            <thead><tr>{columns.map((column) => <th key={column.label}>{column.label}</th>)}</tr></thead>
            <tbody>
              {records.map((row, index) => (
                <tr className={rowTone ? `search-term-${rowTone(row) || "neutral"}` : undefined} key={`${valueOf(row, "id", "campaign_id", "group_id", "targeting_id", "keyword_id", "ad_id") || "row"}-${index}`}>
                  {cells(row)}
                </tr>
              ))}
            </tbody>
            {summaryRow && <tfoot><tr>{cells(summaryRow)}</tr></tfoot>}
          </table>
        </div>
      ) : <EmptyPanel icon={Database} title={`${title}暂无数据`} copy={emptyCopy || "赛狐 API 本次未返回该层级记录。"} />}
    </section>
  );
}

function MatureTrendChart({ rows, window = "14d" }) {
  const windowDays = campaignWindowDays(window);
  const records = rowsOf(rows).map((row) => {
    const date = valueOf(row, "date", "report_date", "statDate", "day");
    const numberOrNull = (...keys) => {
      const value = valueOf(row, ...keys);
      return missingValue(value) || !Number.isFinite(Number(value)) ? null : Number(value);
    };
    return {
      date: String(date || "未知日期"),
      spend: numberOrNull("spend", "costs", "cost"),
      sales: numberOrNull("sales", "attributed_sales"),
      orders: numberOrNull("orders", "order_count", "purchases"),
    };
  }).sort((left, right) => left.date.localeCompare(right.date));

  return (
    <section className="diagnostic-table-section diagnostic-trend-section">
      <div className="diagnostic-section-title">
        <h4><ExplainedLabel label={`${windowDays}日成熟每日趋势`} help={`截至D-2的近${windowDays}天活动每日表现，用于观察所选周期内的变化。`} /></h4>
        <span>{records.length}/{windowDays} 天 · <ScopeTag grain="campaign" /><FreshnessTag value="mature_14d" /></span>
      </div>
      {records.length ? (
        <div className="diagnostic-trend-card">
          <div className="diagnostic-trend-note">左轴：花费、销售额 · 右轴：订单 · ACoS 未返回时不补算</div>
          <ResponsiveContainer width="100%" height={270}>
            <LineChart data={records} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#e8edf3" strokeDasharray="4 4" vertical={false} />
              <XAxis dataKey="date" axisLine={false} tickLine={false} minTickGap={18} tick={{ fill: "#6b7280", fontSize: 10 }} tickFormatter={(value) => String(value).slice(5)} />
              <YAxis yAxisId="money" axisLine={false} tickLine={false} width={46} tick={{ fill: "#6b7280", fontSize: 10 }} tickFormatter={(value) => `$${formatNumber(value, 0)}`} />
              <YAxis yAxisId="orders" orientation="right" allowDecimals={false} axisLine={false} tickLine={false} width={28} tick={{ fill: "#6b7280", fontSize: 10 }} />
              <Tooltip
                contentStyle={{ border: "1px solid #dfe5ec", borderRadius: 12, boxShadow: "0 10px 28px rgba(28, 39, 54, 0.12)", fontSize: 11 }}
                labelFormatter={(value) => `日期 ${value}`}
                formatter={(value, name) => [name === "订单" ? `${formatNumber(value, 0)} 单` : formatMoney(value), name]}
              />
              <Legend wrapperStyle={{ paddingTop: 8, fontSize: 10 }} />
              <Line yAxisId="money" name="销售额" dataKey="sales" type="linear" stroke="#1473e6" strokeWidth={2.5} dot={{ r: 2.5, fill: "#1473e6" }} activeDot={{ r: 4 }} connectNulls={false} />
              <Line yAxisId="money" name="花费" dataKey="spend" type="linear" stroke="#ff7a1a" strokeWidth={2.5} dot={{ r: 2.5, fill: "#ff7a1a" }} activeDot={{ r: 4 }} connectNulls={false} />
              <Line yAxisId="orders" name="订单" dataKey="orders" type="linear" stroke="#18a66f" strokeWidth={2} dot={{ r: 2.5, fill: "#18a66f" }} activeDot={{ r: 4 }} connectNulls={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : <EmptyPanel icon={ChartLine} title={`${windowDays}日成熟每日趋势暂无数据`} copy={`未取得该活动的近${windowDays}日成熟趋势。`} />}
    </section>
  );
}

function relatedRows(rows, product) {
  const records = rowsOf(rows);
  const groupId = valueOf(product, "group_id", "groupId", "ad_group_id", "adGroupId");
  if (!groupId) return records;
  const scoped = records.filter((row) => {
    const rowGroup = valueOf(row, "group_id", "groupId", "ad_group_id", "adGroupId");
    return !rowGroup || String(rowGroup) === String(groupId);
  });
  return scoped.length ? scoped : records;
}

function matureDeepReports(model) {
  const mature = model?.performance?.mature_14d || model?.performance?.mature || {};
  return mature.deep_reports || mature.deepReports || {};
}

function firstRows(...sources) {
  for (const source of sources) {
    const rows = rowsOf(source);
    if (rows.length) return rows;
  }
  return [];
}

function campaignScopedRows(rows, campaignId) {
  const records = rowsOf(rows);
  if (!campaignId) return records;
  const scoped = records.filter((row) => {
    const rowCampaignId = campaignIdOf(row);
    return !rowCampaignId || rowCampaignId === String(campaignId);
  });
  return scoped.length ? scoped : records;
}

function searchTermHighlights(report) {
  const records = deepReportRows(report);
  const explicitWaste = deepReportHighlightRows(report, "waste");
  const explicitConversion = deepReportHighlightRows(report, "conversion");
  const spend = (row) => Number(valueOf(row, "spend", "costs", "cost") || 0);
  const orders = (row) => Number(valueOf(row, "orders", "order_count", "purchases") || 0);
  return {
    waste: explicitWaste.length ? explicitWaste : [...records].filter((row) => orders(row) === 0 && spend(row) > 0).sort((left, right) => spend(right) - spend(left)).slice(0, 10),
    conversion: explicitConversion.length ? explicitConversion : [...records].filter((row) => orders(row) > 0).sort((left, right) => orders(right) - orders(left) || spend(right) - spend(left)).slice(0, 10),
  };
}

function lifecycleLabel(product) {
  const stage = String(valueOf(product, "listing_stage", "lifecycle_stage") || "").toLowerCase();
  if (stage === "new") return { label: "新品", tone: "new" };
  if (stage === "established") return { label: "老品", tone: "established" };
  const days = Number(valueOf(product, "listing_age_days", "listingAgeDays"));
  if (Number.isFinite(days)) return days <= 90 ? { label: "新品", tone: "new" } : { label: "老品", tone: "established" };
  return { label: "上架状态未知", tone: "unknown" };
}

function pagedRows(payload) {
  return rowsOf(payload?.rows || payload?.items || payload?.data || payload?.result || payload).map(expandIdentity);
}

function searchTermTotal(payload, fallback) {
  const value = valueOf(payload, "total", "total_count", "count") ?? valueOf(payload?.pagination, "total", "total_count", "count");
  return Number.isFinite(Number(value)) ? Number(value) : fallback;
}

function searchTermMetrics(row) {
  const numberOf = (...keys) => {
    const value = valueOf(row, ...keys);
    return missingValue(value) || !Number.isFinite(Number(value)) ? null : Number(value);
  };
  const impressions = numberOf("impressions", "impression_count", "广告曝光量") || 0;
  const clicks = numberOf("clicks", "click_count", "广告点击量") || 0;
  const orders = numberOf("orders", "order_count", "purchases", "广告订单量") || 0;
  const spend = numberOf("spend", "costs", "cost", "广告花费") || 0;
  const sales = numberOf("sales", "revenue", "广告销售额") || 0;
  const rawAcos = numberOf("acos", "ACoS");
  const rawCtr = numberOf("ctr", "click_through_rate", "广告点击率");
  const rawCvr = numberOf("cvr", "conversion_rate", "广告转化率");
  const rawRoas = numberOf("roas", "ROAS");
  return {
    impressions,
    clicks,
    orders,
    spend,
    sales,
    ctr: rawCtr == null ? (impressions > 0 ? clicks / impressions : null) : rawCtr,
    acos: rawAcos == null ? (sales > 0 ? spend / sales : null) : rawAcos,
    cvr: rawCvr == null ? (clicks > 0 ? orders / clicks : null) : rawCvr,
    roas: rawRoas == null ? (spend > 0 ? sales / spend : null) : rawRoas,
  };
}

function clampScore(value) {
  return Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
}

function keywordScore(metrics, peerMetrics, kind) {
  const maxSpend = Math.max(1, ...peerMetrics.map((item) => item.spend));
  const maxClicks = Math.max(1, ...peerMetrics.map((item) => item.clicks));
  const maxOrders = Math.max(1, ...peerMetrics.map((item) => item.orders));
  const ctr = clampScore((metrics.ctr || 0) / 0.05 * 100);
  const sample = clampScore(metrics.clicks / 20 * 100);

  if (kind === "waste") {
    const axes = [
      { name: "花费", value: clampScore(metrics.spend / maxSpend * 100) },
      { name: "点击", value: clampScore(metrics.clicks / maxClicks * 100) },
      { name: "点击率", value: ctr },
      { name: "无单风险", value: metrics.orders === 0 ? 100 : 0 },
      { name: "样本量", value: sample },
    ];
    return { axes, score: Math.round(axes[0].value * 0.35 + axes[1].value * 0.3 + axes[2].value * 0.1 + axes[3].value * 0.15 + axes[4].value * 0.1) };
  }

  const axes = [
    { name: "订单量", value: clampScore(metrics.orders / maxOrders * 100) },
    { name: "点击率", value: ctr },
    { name: "转化率", value: clampScore((metrics.cvr || 0) / 0.2 * 100) },
    { name: "ROAS", value: clampScore((metrics.roas || 0) / 5 * 100) },
    { name: "样本量", value: sample },
  ];
  return { axes, score: Math.round(axes[0].value * 0.3 + axes[1].value * 0.15 + axes[2].value * 0.25 + axes[3].value * 0.2 + axes[4].value * 0.1) };
}

function keywordInsight(row, records, kind) {
  const metrics = searchTermMetrics(row);
  const peerMetrics = records.map(searchTermMetrics);
  const scored = records.map((item, index) => ({ index, ...keywordScore(searchTermMetrics(item), peerMetrics, kind) }));
  const currentIndex = records.indexOf(row);
  const current = scored[currentIndex] || keywordScore(metrics, peerMetrics, kind);
  const rank = [...scored].sort((a, b) => b.score - a.score || a.index - b.index).findIndex((item) => item.index === currentIndex) + 1;
  const value = searchTermValue(row);
  const reasons = {
    core: "单量、转化效率和点击样本同时较强，值得优先沉淀。",
    potential: "已有转化，但样本仍偏少，先小预算继续验证。",
    optimize: "转化有效但成本仍有优化空间，先复核利润与竞价。",
    expensive: "能出单但转化成本偏高，暂不适合直接扩量。",
    waste: "已有足够点击仍未出单，应优先核对相关性并评估否定。",
    watch: "无单但点击样本不足，暂时不能下止损结论。",
  };
  return {
    ...current,
    metrics,
    rank: Math.max(1, rank),
    total: records.length,
    value,
    reason: reasons[value.key],
    scoreLabel: kind === "waste" ? "止损关注" : "综合价值",
  };
}

function KeywordRadar({ insight }) {
  const rootRef = useRef(null);
  const chartRef = useRef(null);
  const insightRef = useRef(insight);
  insightRef.current = insight;

  const chartOption = (currentInsight) => ({
    animation: false,
    radar: {
      center: ["50%", "52%"],
      radius: "62%",
      splitNumber: 4,
      indicator: currentInsight.axes.map((item) => ({ name: item.name, max: 100 })),
      axisName: { color: "#596372", fontSize: 10, fontWeight: 600 },
      axisLine: { lineStyle: { color: "#d7e4f4" } },
      splitLine: { lineStyle: { color: "#d7e4f4" } },
      splitArea: { areaStyle: { color: ["#fbfdff", "#f4f8fd"] } },
    },
    series: [{
      type: "radar",
      symbol: "circle",
      symbolSize: 4,
      lineStyle: { color: "#1473e6", width: 2 },
      itemStyle: { color: "#1473e6" },
      areaStyle: { color: "rgba(20, 115, 230, 0.22)" },
      data: [{ value: currentInsight.axes.map((item) => item.value) }],
    }],
  });

  useEffect(() => {
    if (!rootRef.current) return undefined;
    let active = true;
    const resize = () => chartRef.current?.resize();
    loadEcharts().then((echarts) => {
      if (!active || !rootRef.current) return;
      const chart = echarts.init(rootRef.current, null, { renderer: "canvas" });
      chartRef.current = chart;
      chart.setOption(chartOption(insightRef.current), true);
    });
    window.addEventListener("resize", resize);
    return () => {
      active = false;
      window.removeEventListener("resize", resize);
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(chartOption(insight), true);
  }, [insight]);

  const summary = insight.axes.map((item) => `${item.name}${Math.round(item.value)}`).join("，");
  return <div className="keyword-radar" ref={rootRef} role="img" aria-label={`关键词综合雷达图：${summary}`} />;
}

function KeywordInsightPopover({ active, records, campaign, kind }) {
  if (!active || typeof document === "undefined") return null;
  const insight = keywordInsight(active.row, records, kind);
  const { metrics, value } = insight;
  const term = valueOf(active.row, "search_term", "searchTerm", "query", "用户搜索词", "targeting", "投放") || "未知搜索词";
  const position = keywordPopoverPosition({
    anchorRect: active.rect,
    boundaryRect: active.boundaryRect,
    viewportWidth: window.innerWidth,
    viewportHeight: window.innerHeight,
  });
  return createPortal(
    <aside className="keyword-insight-popover" id="keyword-insight-active" style={position} role="tooltip">
      <header>
        <div><small>关键词综合判断</small><strong>{term}</strong></div>
        <span className={`search-term-value ${value.tone}`}>{value.label}</span>
      </header>
      <div className="keyword-insight-main">
        <KeywordRadar insight={insight} />
        <div className="keyword-insight-score">
          <small>{insight.scoreLabel}</small>
          <b>{insight.score}<em>/100</em></b>
          <span>当前页第 {insight.rank}/{insight.total}</span>
          <p>{insight.reason}</p>
        </div>
      </div>
      <dl>
        <div><dt>订单</dt><dd>{formatNumber(metrics.orders)} 单</dd></div>
        <div><dt>点击 / CTR</dt><dd>{formatNumber(metrics.clicks)} / {formatRatio(metrics.ctr) || "—"}</dd></div>
        <div><dt>CVR</dt><dd>{formatRatio(metrics.cvr) || "—"}</dd></div>
        <div><dt>ACoS / ROAS</dt><dd>{formatRatio(metrics.acos) || "—"} / {formatRoas(metrics.roas) || "—"}</dd></div>
      </dl>
      <footer><span>建议</span><strong>{searchTermSuggestion(active.row, campaign)}</strong></footer>
    </aside>,
    document.body,
  );
}

const SEARCH_TERM_COLUMNS = [
  { label: "搜索词", keys: ["search_term", "searchTerm", "query", "用户搜索词", "targeting", "投放"] },
  { label: "展示量", keys: ["impressions", "impression_count", "广告曝光量"], formatter: (value) => formatNumber(value, 0) },
  { label: "点击", keys: ["clicks", "click_count", "广告点击量"], formatter: (value) => formatNumber(value, 0) },
  { label: "点击率", keys: ["ctr", "click_through_rate", "广告点击率"], formatter: formatRatio },
  { label: "总成本", keys: ["spend", "costs", "cost", "广告花费"], formatter: formatMoney },
  { label: "CPC", keys: ["cpc"], formatter: formatMoney },
  { label: "订单", keys: ["orders", "order_count", "purchases", "广告订单量"], formatter: (value) => formatNumber(value, 0) },
  { label: "销售额", keys: ["sales", "revenue", "广告销售额"], formatter: formatMoney },
  { label: "ACoS", keys: ["acos", "ACoS"], rowFormatter: formatAcos },
  { label: "ROAS", keys: ["roas", "ROAS"], formatter: formatRoas },
];

function SearchTermPager({ shopId, campaign, kind, title, initialRows, total, emptyCopy, dataRevision }) {
  const campaignId = campaignIdOf(campaign);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(() => ({ 1: rowsOf(initialRows) }));
  const [knownTotal, setKnownTotal] = useState(Number(total) || rowsOf(initialRows).length);
  const [loadingPage, setLoadingPage] = useState(false);
  const [pageError, setPageError] = useState("");
  const [activeTerm, setActiveTerm] = useState(null);
  const requestRef = useRef(null);
  const campaignRef = useRef(campaignId);
  campaignRef.current = campaignId;

  useEffect(() => {
    requestRef.current?.abort();
    setPage(1);
    setPages({ 1: rowsOf(initialRows) });
    setKnownTotal(Number(total) || rowsOf(initialRows).length);
    setPageError("");
    setActiveTerm(null);
    return () => requestRef.current?.abort();
  }, [campaignId, kind, dataRevision]);

  async function goToPage(nextPage) {
    if (nextPage < 1 || loadingPage) return;
    if (pages[nextPage]) {
      setActiveTerm(null);
      setPage(nextPage);
      return;
    }
    setLoadingPage(true);
    setPageError("");
    const requestedCampaignId = campaignId;
    const controller = new AbortController();
    requestRef.current = controller;
    try {
      const payload = await fetchSearchTermsPage({ shopId, campaignId, kind, page: nextPage, pageSize: 10, signal: controller.signal });
      if (controller.signal.aborted || campaignRef.current !== requestedCampaignId) return;
      const nextRows = pagedRows(payload);
      setPages((current) => ({ ...current, [nextPage]: nextRows }));
      setKnownTotal(searchTermTotal(payload, knownTotal));
      setActiveTerm(null);
      setPage(nextPage);
    } catch (requestError) {
      if (requestError?.name !== "AbortError") setPageError(requestError?.message || "下一页读取失败");
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null;
        setLoadingPage(false);
      }
    }
  }

  const records = pages[page] || [];
  const pageCount = Math.max(1, Math.ceil(knownTotal / 10));
  return (
    <section className="diagnostic-table-section diagnostic-search-pager">
      <div className="diagnostic-section-title">
        <h4><ExplainedLabel label={title} help={SECTION_HELP[title] || ""} /></h4>
        <span>{knownTotal} 条 · 第 {page}/{pageCount} 页 · <ScopeTag grain="target" /><FreshnessTag value="mature_14d" /></span>
      </div>
      {records.length ? (
        <div className="diagnostic-table-scroll">
          <table className="diagnostic-search-term-table">
            <thead><tr>{SEARCH_TERM_COLUMNS.map((column) => <th key={column.label}>{column.label}</th>)}<th>建议</th></tr></thead>
            <tbody>{records.map((row, index) => {
              const term = valueOf(row, "search_term", "searchTerm", "query", "用户搜索词", "targeting", "投放") || "未知搜索词";
              const recommendation = searchTermRecommendation(row);
              const value = searchTermValue(row);
              const showInsight = (event) => {
                const boundary = event.currentTarget.closest(".diagnostic-search-pager");
                setActiveTerm({
                  row,
                  index,
                  rect: event.currentTarget.getBoundingClientRect(),
                  boundaryRect: boundary?.getBoundingClientRect(),
                });
              };
              return (
                <tr
                  className={recommendation ? `search-term-${recommendation}` : undefined}
                  key={`${term}-${index}`}
                  tabIndex={0}
                  aria-describedby={activeTerm?.index === index ? "keyword-insight-active" : undefined}
                  onMouseEnter={showInsight}
                  onMouseLeave={() => setActiveTerm(null)}
                  onFocus={showInsight}
                  onBlur={() => setActiveTerm(null)}
                >
                  {SEARCH_TERM_COLUMNS.map((column) => {
                    const raw = valueOf(row, ...column.keys);
                    const formatted = column.rowFormatter ? column.rowFormatter(raw, row) : column.formatter ? column.formatter(raw) : missingValue(raw) ? null : String(raw);
                    return <td className={column.label === "搜索词" ? "search-term-keyword" : formatted === null ? "unknown-value" : undefined} title={column.label === "搜索词" ? String(term) : undefined} key={column.label}>{formatted ?? "—"}</td>;
                  })}
                  <td><span className={`search-term-suggestion ${value.tone}`}>{searchTermSuggestion(row, campaign)}</span></td>
                </tr>
              );
            })}</tbody>
          </table>
          <KeywordInsightPopover active={activeTerm} records={records} campaign={campaign} kind={kind} />
        </div>
      ) : <EmptyPanel icon={Database} title={`${title}暂无数据`} copy={emptyCopy} />}
      <footer className="search-term-page-controls">
        <span>悬浮或聚焦任一行，查看 ECharts 综合雷达与当前页排名。</span>
        <div>
          <button type="button" disabled={page <= 1 || loadingPage} onClick={() => goToPage(page - 1)}>上一页</button>
          <button type="button" disabled={page >= pageCount || loadingPage} onClick={() => goToPage(page + 1)}>{loadingPage ? "读取中…" : "下一页"}</button>
        </div>
      </footer>
      {pageError && <small className="search-term-page-error">{pageError}</small>}
    </section>
  );
}

function skuSalesTrendRows(trend) {
  if (Array.isArray(trend)) return trend;
  if (!trend || typeof trend !== "object") return [];
  const grouped = new Map();
  for (const metric of ["salePrice", "orderNum", "productNum"]) {
    rowsOf(trend[metric]).forEach((row, index) => {
      const date = String(valueOf(row, "date", "report_date", "statDate", "day") || index);
      const value = valueOf(row, metric, "value", "num", "quantity", "amount");
      grouped.set(date, { ...grouped.get(date), ...row, date, [metric]: value });
    });
  }
  return [...grouped.values()].sort((left, right) => String(left.date).localeCompare(String(right.date)));
}

function campaignStatusLabel(campaign) {
  const state = campaignStateOf(campaign);
  if (["enabled", "active", "running"].includes(state)) return "投放中";
  if (["paused", "archived", "disabled"].includes(state)) return "已暂停";
  return state === "unknown" ? "状态未返回" : state;
}

function defaultBidLabel(campaign) {
  const minimum = valueOf(campaign, "default_bid_min", "defaultBidMin", "default_bid", "defaultBid");
  const maximum = valueOf(campaign, "default_bid_max", "defaultBidMax", "default_bid", "defaultBid");
  if (missingValue(minimum) || missingValue(maximum)) return "未返回";
  if (Number(minimum) === Number(maximum)) return formatMoney(minimum);
  return `${formatMoney(minimum)}–${formatMoney(maximum)}`;
}

function CampaignCard({ campaign, selected, onSelect, window }) {
  const metrics = campaignWindowMetrics(campaign, window);
  const skus = rowsOf(campaign?.skus);
  const productCount = valueOf(campaign, "advertised_product_count", "advertisedProductCount");
  const targetCount = valueOf(campaign, "total_target_count", "totalTargetCount");
  const coverage = Number(valueOf(metrics, "data_days", "dataDays") || 0);
  const windowDays = Number(valueOf(metrics, "window_days", "windowDays") || window.replace("d", ""));
  const performanceGrade = campaignPerformanceGrade(campaign, window);
  const fullDays = valueOf(campaign, "budget_utilization_days_7d", "budgetUtilizationDays7d");
  const todayBudgetProgress = valueOf(campaign, "today_budget_progress", "todayBudgetProgress");
  const todayBudgetStatus = String(valueOf(campaign, "today_budget_status", "todayBudgetStatus") || "");
  const biddingStrategy = campaignBiddingStrategy(campaign);
  const placementAdjustments = campaignPlacementAdjustmentLabel(campaign);
  const cardMetrics = [
    ["展示量", valueOf(metrics, "impressions"), (value) => formatNumber(value, 0)],
    ["点击量", valueOf(metrics, "clicks"), (value) => formatNumber(value, 0)],
    ["点击率", valueOf(metrics, "ctr"), formatRatio],
    ["总成本", valueOf(metrics, "spend", "costs"), formatMoney],
    ["CPC", valueOf(metrics, "cpc"), formatMoney],
    ["购买量", valueOf(metrics, "orders"), (value) => formatNumber(value, 0)],
    ["销售额", valueOf(metrics, "sales"), formatMoney],
    ["ACoS", valueOf(metrics, "acos"), (value) => formatAcos(value, metrics)],
    ["ROAS", valueOf(metrics, "roas"), formatRoas],
    ["购买率", campaignMetricValue(campaign, "cvr", window), formatRatio],
  ];
  return (
    <button className={`diagnostic-campaign-card ${selected ? "selected" : ""}`} type="button" onClick={onSelect}>
      <span className="diagnostic-card-head">
        <StatusPill value={campaignStatusLabel(campaign)} />
        <small>{coverage}/{windowDays}天成熟数据</small>
        {campaignPriorityScore(campaign) > 0 && <em>需关注</em>}
      </span>
      <span className="campaign-classification-row">
        <em className="lifecycle">{campaignLifecycleLabel(campaign)}</em>
        <em className={`performance ${performanceGrade.tone}`}>{performanceGrade.label}</em>
        <em className="ad-type">{campaignAdTypeLabel(campaign)}</em>
      </span>
      <b title={campaignNameOf(campaign)}>{campaignNameOf(campaign)}</b>
      <small className="diagnostic-campaign-id">ID {campaignIdOf(campaign)}</small>
      <dl className="diagnostic-campaign-config">
        <div><dt>默认竞价</dt><dd>{defaultBidLabel(campaign)}</dd></div>
        <div><dt>总投放数</dt><dd>{displayValue(targetCount, (value) => formatNumber(value, 0))}</dd></div>
        <div><dt>商品</dt><dd>{displayValue(productCount, (value) => formatNumber(value, 0))}</dd></div>
      </dl>
      <span className="campaign-budget-context">
        <small>{biddingStrategy || "竞价方案未返回"}</small>
        <small>{missingValue(todayBudgetProgress)
          ? ({ stale: "今日预算数据过期", never: "今日预算待采集", empty: "今日预算暂无数据" })[todayBudgetStatus] || "今日预算选择后加载"
          : `今日预算 ${formatRatio(todayBudgetProgress, 0)}`}</small>
        <small>{missingValue(fullDays) ? "近7天跑满待回填" : `近7天跑满 ${formatNumber(fullDays, 0)} 天`}</small>
      </span>
      <span className="campaign-placement-adjustments">{placementAdjustments || "广告位加价比例未返回"}</span>
      <span className="diagnostic-campaign-products" title={skus.join("、")}><Package size={14} />{skus.length ? skus.join("、") : "SKU未返回"}</span>
      {Number(productCount) > 1 && <span className="shared-budget-note">{productCount}个SKU共享活动预算，非平均分配</span>}
      <dl className="diagnostic-campaign-metrics">
        {cardMetrics.map(([label, value, formatter]) => <div key={label}><dt>{label}</dt><dd className={missingValue(value) ? "unknown-value" : ""}>{displayValue(value, formatter)}</dd></div>)}
      </dl>
    </button>
  );
}

function CampaignHeader({ shop, model, catalogCampaign, selectedProduct, onOpenControls }) {
  const campaign = model.campaign || {};
  const campaignContext = { ...campaign, ...(catalogCampaign || {}) };
  const meta = model.meta || {};
  const snapshot = Boolean(valueOf(meta, "snapshot_generated_at"));
  const stale = Boolean(valueOf(meta, "snapshot_stale"));
  const pending = Boolean(valueOf(meta, "refresh_pending"));
  const status = pending ? "活动数据更新中" : stale ? "数据待更新" : snapshot ? "数据可用" : valueOf(meta, "status", "coverage_status") || "live";
  const observedAt = snapshot
    ? valueOf(meta, "snapshot_generated_at", "generated_at")
    : valueOf(meta, "fetched_at", "generated_at", "observed_at");
  return (
    <header className="diagnostic-detail-header">
      <div>
        <span className="pilot-kicker">{shop.name} · SP</span>
        <h2>{campaignNameOf(campaign)}</h2>
        <p>活动 {campaignIdOf(campaign) || "未知"}{selectedProduct ? ` · SKU ${valueOf(selectedProduct, "sku", "msku") || "未知"} · ASIN ${valueOf(selectedProduct, "asin") || "未知"}` : " · 未返回广告商品"}</p>
        <p className="diagnostic-campaign-facts">{campaignAdTypeLabel(campaignContext)} · {campaignBiddingStrategy(campaignContext) || "竞价方案未返回"} · {campaignPlacementAdjustmentLabel(campaignContext) || "广告位加价比例未返回"} · {campaignLifecycleLabel(campaignContext)} · {campaignPerformanceLabel(campaignContext)}</p>
      </div>
      <div className="diagnostic-fetch-meta">
        <StatusPill value={status} />
        <span><small>数据更新时间</small>{displayValue(observedAt, formatDateTime)}</span>
        <span className="read-only-chip"><ShieldCheck size={16} weight="fill" />需二次确认</span>
        <button className="sp-control-open-button" type="button" onClick={onOpenControls}><SlidersHorizontal size={17} weight="bold" />调控广告</button>
      </div>
    </header>
  );
}

function HourlyAlertStrip({ decision, currentHour }) {
  const confirmation = rowsOf(decision.todayConfirmation).find((row) => {
    const status = String(valueOf(row, "status", "result") || "").toLowerCase();
    return !["confirmed", "complete", "healthy", "normal", "ok"].includes(status);
  });
  const blocker = rowsOf(decision.blockers)[0];
  const conflict = rowsOf(decision.conflicts)[0];
  const alert = blocker || conflict || confirmation;
  const tone = blocker ? "danger" : alert ? "warning" : "quiet";
  const latestHour = missingValue(currentHour.latestHour) ? "最新小时未返回" : `已回填至 ${currentHour.latestHour} 时`;
  const title = alert ? rowText(alert, "label", "title", "code", "status") : "当前小时暂无关键预警";
  const reason = alert ? rowText(alert, "message", "reason", "description", "value") : `${latestHour}，继续监控回填变化。`;
  return (
    <section className={`hourly-alert-strip ${tone}`}>
      {alert ? <Warning size={17} weight="fill" /> : <CheckCircle size={17} weight="fill" />}
      <b>{title}</b><span>{reason}</span><small>{latestHour} · 暂定</small>
    </section>
  );
}

function productHourlySummary(model, product) {
  const rows = rowsOf(model?.performance?.today?.ad_products || model?.performance?.current_hour?.ad_products);
  const adId = String(valueOf(product, "ad_id", "adId") || "");
  const sku = String(valueOf(product, "sku", "msku") || "");
  const asin = String(valueOf(product, "asin") || "").toUpperCase();
  const matched = rows.filter((row) => {
    const rowAdId = String(valueOf(row, "ad_id", "adId") || "");
    const rowSku = String(valueOf(row, "sku", "msku") || "");
    const rowAsin = String(valueOf(row, "asin") || "").toUpperCase();
    const identitiesAgree = (!sku || !rowSku || rowSku === sku) && (!asin || !rowAsin || rowAsin === asin);
    if (adId) return rowAdId === adId && identitiesAgree;
    if (sku && asin) return rowSku === sku && rowAsin === asin;
    return sku ? rowSku === sku : Boolean(asin && rowAsin === asin);
  });
  const numberOf = (row, ...keys) => Number(valueOf(row, ...keys) || 0);
  return matched.reduce((summary, row) => ({
    spend: summary.spend + numberOf(row, "spend", "costs", "cost"),
    sales: summary.sales + numberOf(row, "sales", "attributed_sales"),
    clicks: summary.clicks + numberOf(row, "clicks"),
    orders: summary.orders + numberOf(row, "orders", "order_count"),
    matched: matched.length,
  }), { spend: 0, sales: 0, clicks: 0, orders: 0, matched: matched.length });
}

function DiagnosticInsightRail({ model, selectedProduct }) {
  if (!model) return <aside className="diagnostic-insight-rail diagnostic-insight-loading"><ArrowClockwise className="spin" size={22} /><span>首屏数据读取中</span></aside>;
  const hourly = productHourlySummary(model, selectedProduct);
  const lifecycle = lifecycleLabel(selectedProduct);
  return (
    <aside className="diagnostic-insight-rail">
      <section>
        <header><span>本 SKU · 当前小时</span><em className={`diagnostic-lifecycle-chip ${lifecycle.tone}`}>{lifecycle.label}</em></header>
        <b className="insight-sku">{valueOf(selectedProduct, "sku", "msku") || "SKU 未返回"}</b>
        <dl className="insight-hourly-grid">
          <div><dt>花费</dt><dd>{displayValue(hourly.spend, formatMoney)}</dd></div>
          <div><dt>销售额</dt><dd>{displayValue(hourly.sales, formatMoney)}</dd></div>
          <div><dt>点击</dt><dd>{formatNumber(hourly.clicks, 0) || "0"}</dd></div>
          <div><dt>订单</dt><dd>{formatNumber(hourly.orders, 0) || "0"}</dd></div>
        </dl>
        <small>{hourly.matched ? "今日截至最新返回小时累计，仍会回填。" : "当前小时未匹配到该 adId，不用活动数据代填。"}</small>
      </section>
      <section className="insight-listing">
        <header><span>上架判断</span><em>{lifecycle.label}</em></header>
        <p>{valueOf(selectedProduct, "open_date", "openDate", "listing_date") || "上架时间未返回"}{!missingValue(valueOf(selectedProduct, "listing_age_days")) ? ` · 已上架 ${valueOf(selectedProduct, "listing_age_days")} 天` : ""}</p>
      </section>
    </aside>
  );
}

function SkuOperatingSummary({ model, selectedProduct, window = "14d" }) {
  const windowDays = campaignWindowDays(window);
  const { analysis, inventory, financial, sales, online } = windowedSkuOperatingContext(model, selectedProduct, window);
  const controlAnalysis = window === "14d" ? analysis : { availableDays: valueOf(analysis, "availableDays", "available_days") };
  const control = skuControlMetrics({ analysis: controlAnalysis, financial });
  const periodSales = firstPresent(
    metricValue(financial, "saleNum", "sale_num", "units", "quantity"),
    window === "14d" ? metricValue(analysis, "productTotalNumThis", "units") : null,
    metricValue(online, `day${windowDays}SaleNum`),
    metricValue(sales, `units_${windowDays}d`, `sales_${windowDays}d`, `quantity_${windowDays}d`, `day${windowDays}SaleNum`),
  );
  const dailySales = missingValue(periodSales) || !Number.isFinite(Number(periodSales)) ? null : Number(periodSales) / windowDays;
  const headroomTone = control.acosHeadroomPct == null
    ? ""
    : control.acosHeadroomPct < 0
      ? "risk"
      : control.acosHeadroomPct < 3
        ? "warning"
        : "safe";
  const items = [
    { label: "可售库存", value: metricValue(inventory, "available", "available_quantity", "sellable", "quantity", "totalInventory"), formatter: (value) => formatNumber(value, 0) },
    { label: "在途库存", value: metricValue(inventory, "inbound", "inbound_quantity", "warehousing"), formatter: (value) => formatNumber(value, 0) },
    { label: `近${windowDays}日销量`, value: periodSales, formatter: (value) => formatNumber(value, 0) },
    { label: "日均销量", value: dailySales, formatter: (value) => formatNumber(value, 1) },
    { label: "可售天数", value: control.availableDays, formatter: (value) => {
      const formatted = formatNumber(value, 1);
      return formatted === null ? null : `${formatted}天`;
    } },
    { label: "退款率", value: control.refundRatePct, formatter: formatPercentagePoints },
    { label: "毛利率", value: metricValue(financial, "gross_margin_rate", "profit_rate", "profitRate", "margin_rate"), formatter: formatRatio },
    { label: `${windowDays}日利润`, value: metricValue(financial, "profit", "gross_profit"), formatter: formatMoney, className: "compact-value" },
    { label: `${windowDays}日SP成本`, value: metricValue(financial, "sp_cost", "sp_ads_cost", "sp_ad_cost", "adSpCost", "adTotalCostSp"), formatter: formatMoney, className: "compact-value" },
    { label: "SKU SP ACoS", value: control.skuSpAcosPct, formatter: formatPercentagePoints },
    { label: "SP销售占比", value: control.spSalesSharePct, formatter: formatPercentagePoints },
    { label: "估算盈亏 ACoS", value: control.breakEvenAcosPct, formatter: formatPercentagePoints },
    { label: "ACoS 安全余量", value: control.acosHeadroomPct, formatter: formatPercentagePointDelta, className: headroomTone },
  ];
  return (
    <section className="diagnostic-operating-card">
      <div className="diagnostic-section-title"><h4>库存、销量与利润</h4><span>{valueOf(selectedProduct, "sku", "msku") || "SKU未返回"} · 近{windowDays}日</span></div>
      <div className={`operating-metric-grid ${items.length % 2 ? "has-odd-last" : ""}`}>
        {items.map((item) => {
          const formatted = item.formatter(item.value);
          const className = [formatted === null ? "unknown" : "", item.className || ""].filter(Boolean).join(" ");
          return <div className={className} key={item.label}><ExplainedLabel label={item.label} help={metricHelp(item.label)} /><b>{formatted ?? "—"}</b></div>;
        })}
      </div>
    </section>
  );
}

function BudgetTrafficPanel({ campaign, mature, today, todayLayer, matureDailyTrend, selectedProduct, model, window = "14d" }) {
  const windowDays = campaignWindowDays(window);
  const { analysis, financial } = windowedSkuOperatingContext(model, selectedProduct, window);
  const controlAnalysis = window === "14d" ? analysis : { availableDays: valueOf(analysis, "availableDays", "available_days") };
  const control = skuControlMetrics({ analysis: controlAnalysis, financial });
  const budgetMatrix = campaignBudgetMatrix(campaign);
  const budgetStatus = campaignBudgetStatus(campaign);
  const pacing = todayLayer?.pacing && typeof todayLayer.pacing === "object" ? todayLayer.pacing : {};
  const pacingToday = pacing.today || {};
  const yesterdaySameHour = pacing.yesterday_same_hour || pacing.yesterdaySameHour || {};
  const prior7SameHour = pacing.prior_7d_same_hour || pacing.prior7SameHour || {};
  const yesterdayFullDay = pacing.yesterday_full_day || pacing.yesterdayFullDay || {};
  const historyRows = rowsOf(pacing.history);
  const dailyBudget = metricValue(campaign, "daily_budget", "dailyBudget", "budget");
  const todaySpend = firstPresent(metricValue(pacingToday, "spend"), metricValue(today, "spend", "costs", "cost"));
  const budgetNumber = Number(dailyBudget);
  const spendNumber = Number(todaySpend);
  const progress = Number.isFinite(budgetNumber) && budgetNumber > 0 && Number.isFinite(spendNumber) ? spendNumber / budgetNumber : null;
  const recentRows = rowsOf(matureDailyTrend).slice(-7);
  const pacingLimitedDays = Number.isFinite(budgetNumber) && budgetNumber > 0 && historyRows.length === 7
    ? historyRows.filter((row) => Number(valueOf(row, "full_day_spend", "fullDaySpend") || 0) >= budgetNumber * 0.98).length
    : null;
  const matureLimitedDays = Number.isFinite(budgetNumber) && budgetNumber > 0
    ? recentRows.filter((row) => Number(valueOf(row, "spend", "costs", "cost") || 0) >= budgetNumber * 0.98).length
    : null;
  const limitedDays = firstPresent(
    metricValue(mature, "budget_utilization_days_7d", "budget_limited_days_7d", "budget_exhausted_days_7d"),
    metricValue(campaign, "budget_utilization_days_7d", "budget_limited_days_7d", "budget_exhausted_days_7d"),
    pacingLimitedDays,
    recentRows.length === 7 ? matureLimitedDays : null,
  );
  const latestHour = metricValue(pacing, "latest_complete_hour", "latestCompleteHour");
  const reportDate = metricValue(pacing, "report_date", "reportDate") || metricValue(todayLayer, "report_date", "reportDate");
  const reportTimezone = metricValue(pacing, "report_timezone", "reportTimezone") || metricValue(todayLayer, "report_timezone", "reportTimezone");
  const cutoff = Number.isFinite(Number(latestHour)) ? `${String(Number(latestHour)).padStart(2, "0")}:59` : "小时未返回";
  const comparisonReady = valueOf(pacing, "comparison_ready", "comparisonReady") === true;
  const availableDays = metricValue(prior7SameHour, "available_days", "availableDays");
  const dayText = (value) => {
    const formatted = formatNumber(value, 0);
    return formatted === null ? null : `${formatted}天`;
  };
  const todayMetrics = [
    { label: `截至${cutoff}花费`, value: todaySpend, formatter: formatMoney },
    { label: "日预算", value: dailyBudget, formatter: formatMoney },
    { label: "预算使用率", value: progress, formatter: (value) => formatRatio(value, 0) },
    { label: "较昨日同小时", value: metricValue(yesterdaySameHour, "change"), formatter: formatSignedRatio },
    { label: "较近7日同小时", value: metricValue(prior7SameHour, "change"), formatter: formatSignedRatio },
  ];
  const referenceMetrics = [
    { label: "昨日全天花费", value: metricValue(yesterdayFullDay, "spend"), formatter: formatMoney },
    { label: "近7天预算耗尽", value: limitedDays, formatter: (value) => {
      return dayText(value);
    } },
    { label: "同小时历史样本", value: availableDays, formatter: dayText },
    { label: `近${windowDays}日 ACoS`, value: metricValue(mature, "acos"), formatter: formatRatio },
    { label: "估算盈亏平衡 ACoS", value: control.breakEvenAcosPct, formatter: formatPercentagePoints },
  ];
  const renderMetrics = (metrics) => metrics.map((item) => {
    const formatted = item.formatter(item.value);
    return <div className={formatted === null ? "unknown" : ""} key={item.label}><span>{item.label}</span><b>{formatted ?? "—"}</b></div>;
  });
  return (
    <section className="budget-traffic-panel">
      <div className="diagnostic-section-title"><h4>预算与流量</h4><span>{budgetMatrix.label} · 账号时区 {reportTimezone || "未返回"}</span></div>
      <div className={`budget-matrix-callout ${budgetMatrix.tone}`}><b>{budgetMatrix.label}</b><span>{budgetMatrix.action}</span><small>{budgetStatus === "full" ? "预算已形成跑满" : "预算尚未形成跑满"}</small></div>
      <div className="budget-pacing-group">
        <header>
          <div><b>美国站今日进度</b><span>{reportDate || "站点日期未返回"} · 数据截至 {cutoff} · 暂定</span></div>
          <em className={comparisonReady ? "ready" : "early"}>{comparisonReady ? "同小时可比" : "仅展示进度"}</em>
        </header>
        <div className="budget-traffic-grid budget-today-grid">{renderMetrics(todayMetrics)}</div>
        <div className="budget-progress" aria-label="美国站今日预算消耗进度"><i style={{ width: `${Math.min(100, Math.max(0, Number(progress || 0) * 100))}%` }} /></div>
      </div>
      <div className="budget-pacing-group budget-reference-group">
        <header><div><b>完整日与成熟参考</b><span>昨日完整日 + D-2近{windowDays}日效率</span></div></header>
        <div className="budget-traffic-grid">{renderMetrics(referenceMetrics)}</div>
      </div>
      <p>{comparisonReady ? "今日消耗已达到同小时比较门槛。" : "当前不足4个完整小时，仅展示消耗与差值，不判断快慢。"} 所有对比均按广告账号时区对齐，不按美国各州取均值；预算耗尽只表示流量可能受限。</p>
    </section>
  );
}

function adjustmentValueText(value) {
  if (!value || typeof value !== "object") return "—";
  const entries = Object.entries(value).filter(([key]) => !["created", "removed"].includes(key));
  if (!entries.length) return value.created ? "新建" : value.removed ? "移除" : "—";
  return entries.map(([key, item]) => `${key}: ${typeof item === "object" ? JSON.stringify(item) : item}`).join("；");
}

function AdjustmentReviewPanel({ reviews }) {
  const items = rowsOf(reviews).slice(0, 5);
  if (!items.length) return (
    <section className="adjustment-review-panel empty">
      <div className="diagnostic-section-title"><h4>调价前后7天复盘</h4><span>尚无已执行调控</span></div>
      <p>后续通过调控面板执行的预算、竞价或状态调整，会在成熟归因后自动形成前7天与后7天对比。</p>
    </section>
  );
  const metrics = [
    ["展示", "impressions", (value) => formatNumber(value, 0)],
    ["点击", "clicks", (value) => formatNumber(value, 0)],
    ["CTR", "ctr", formatRatio],
    ["花费", "spend", formatMoney],
    ["CPC", "cpc", formatMoney],
    ["订单", "orders", (value) => formatNumber(value, 0)],
    ["购买率", "cvr", formatRatio],
    ["销售额", "sales", formatMoney],
    ["ACoS", "acos", formatRatio],
    ["ROAS", "roas", formatRoas],
    ["头部广告位占比", "top_placement_click_share", formatRatio],
    ["跑满天数", "budget_full_days", (value) => missingValue(value) ? null : `${formatNumber(value, 0)}天`],
  ];
  return (
    <section className="adjustment-review-panel">
      <div className="diagnostic-section-title"><h4>调价前后7天复盘</h4><span>以调整日为锚点 · 成熟D-2</span></div>
      <div className="adjustment-review-list">
        {items.map((item) => {
          const before = item.before || {};
          const after = item.after || {};
          const complete = item.status === "complete";
          return (
            <article key={item.plan_id || `${item.operation}-${item.changed_at}`}>
              <header>
                <div><b>{item.operation_label || item.operation}</b><span>{formatDateTime(item.changed_at) || item.changed_at}</span></div>
                <em className={complete ? "complete" : "collecting"}>{complete ? "后7天已成熟" : `后7天 ${after.mature_days || 0}/7`}</em>
              </header>
              <p className="adjustment-value-change"><span>{adjustmentValueText(item.before_value)}</span><strong>→</strong><span>{adjustmentValueText(item.after_value)}</span></p>
              <div className="adjustment-metric-table">
                <div className="header"><span>指标</span><b>调整前7天</b><b>调整后7天</b></div>
                {metrics.map(([label, key, formatter]) => (
                  <div key={key}><span>{label}</span><b>{displayValue(before[key], formatter)}</b><b>{displayValue(after[key], formatter)}</b></div>
                ))}
              </div>
              {!complete && <small>后7天尚未全部达到D-2成熟日期，当前只展示进度，不提前下结论。</small>}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function placementTopShare(rows) {
  const records = rowsOf(rows);
  const clicks = records.reduce((total, row) => total + Number(valueOf(row, "clicks") || 0), 0);
  const topClicks = records.reduce((total, row) => {
    const name = String(valueOf(row, "placement", "placement_name", "name", "广告位") || "").toLowerCase();
    return total + (name.includes("顶部") || name.includes("top of search") ? Number(valueOf(row, "clicks") || 0) : 0);
  }, 0);
  return clicks > 0 ? topClicks / clicks : null;
}

function DiagnosticFlowPanel({ campaign, selectedProduct, todayPlacements, maturePlacements }) {
  const matrix = campaignBudgetMatrix(campaign);
  const adType = campaignAdType(campaign);
  const lifecycle = campaignLifecycleOfProduct(selectedProduct, campaign);
  if (!["poor", "new_observation"].includes(campaignPerformanceStatus(campaign))) return null;
  const topToday = placementTopShare(todayPlacements);
  const topMature = placementTopShare(maturePlacements);
  const topDelta = topToday == null || topMature == null ? null : topToday - topMature;
  const branches = {
    auto: ["检查自动投放类型与搜索词相关性", "清理达到样本门槛的无效词", "把优质搜索词转入手动精准和广泛测试"],
    exact: lifecycle === "established"
      ? ["优先检查关键词、搜索词与CPC变化", "核对搜索顶部流量占比和广告位加价", "Listing仅作为次级检查"]
      : ["检查主图、价格、评价数量和评分", "人工核对顶部差评与同生态位竞品Listing", "确认关键词相关性后再判断竞价"],
    broad: ["检查搜索词是否漂移", "补充否定关键词并收窄低相关流量", "优质词转精准，小预算验证"],
    phrase: ["检查词组扩展后的搜索词相关性", "补充否词并拆分有效词", "避免通过加预算放大低相关流量"],
    product_target: ["检查投放ASIN或类目相关性", "比较商品页流量和转化", "清理高点击低购买率商品投放"],
    manual_mixed: ["按精准、广泛、词组和商品投放分别下钻", "不要用活动平均值替代投放级判断", "优先处理表现差且已跑满的对象"],
    manual: ["核对具体投放类型与搜索词", "检查CPC、广告位和相关性", "样本不足时继续观察"],
  };
  return (
    <section className="diagnostic-flow-panel">
      <div className="diagnostic-section-title"><h4>分类型诊断路径</h4><span>{campaignAdTypeLabel(campaign)} · {campaignLifecycleLabel(campaign)}</span></div>
      <div className="diagnostic-flow-grid">
        <article><b>{matrix.label}</b><p>{matrix.action}</p></article>
        <article><b>{campaignAdTypeLabel(campaign)}检查重点</b><ol>{(branches[adType] || branches.manual).map((item) => <li key={item}>{item}</li>)}</ol></article>
        <article><b>竞争与广告位信号</b><p>{topDelta == null ? "头部广告位占比数据不足。" : `当前小时头部点击占比较成熟窗口${topDelta >= 0 ? "高" : "低"} ${formatRatio(Math.abs(topDelta), 1)}。`}</p><small>这里只反映自身CPC和广告位流量变化，不等同于已取得竞品CPC或实际排名。</small></article>
      </div>
      {adType === "exact" && lifecycle !== "established" && <div className="manual-competitor-checklist"><b>新品人工检查清单</b><span>主图吸引力</span><span>价格差异</span><span>评分与评价量</span><span>顶部差评</span><span>同生态位竞品Listing</span></div>}
    </section>
  );
}

function campaignLifecycleOfProduct(product, campaign) {
  const stage = String(valueOf(product, "listing_stage", "lifecycle_stage") || "").toLowerCase();
  return ["new", "established", "mixed", "unknown"].includes(stage) ? stage : String(valueOf(campaign, "listing_stage") || "unknown");
}

function MainProductAlertPanel({ campaign, model, selectedProduct, todayPlacements, maturePlacements }) {
  const { product, listing, sales } = skuOperatingContext(model, selectedProduct);
  const policy = model?.performance?.mature_14d?.policy?.main_product || {};
  const windowDays = Number(valueOf(policy, "window_days", "windowDays") || 7);
  const minOrders = Number(valueOf(policy, "min_orders", "minOrders") || 50);
  const maxDailyCv = Number(valueOf(policy, "max_daily_cv", "maxDailyCv") || 0.35);
  const suddenDropRatio = Number(valueOf(policy, "sudden_drop_ratio", "suddenDropRatio") || 0.6);
  const trend = skuSalesTrendRows(product.sales_trend || product.salesTrend || sales.trend || listing.sales_trend || listing.salesTrend).slice(-windowDays);
  const dailyOrders = trend.map((row) => Number(valueOf(row, "orderNum", "orders", "order_count"))).filter(Number.isFinite);
  const totalOrders = dailyOrders.reduce((total, value) => total + value, 0);
  const average = dailyOrders.length ? totalOrders / dailyOrders.length : 0;
  const variance = dailyOrders.length ? dailyOrders.reduce((total, value) => total + (value - average) ** 2, 0) / dailyOrders.length : 0;
  const cv = average > 0 ? Math.sqrt(variance) / average : null;
  const mainProduct = dailyOrders.length === windowDays && totalOrders >= minOrders && cv != null && cv <= maxDailyCv;
  const previous = dailyOrders.slice(0, -1).sort((left, right) => left - right);
  const median = previous.length ? (previous[Math.floor((previous.length - 1) / 2)] + previous[Math.ceil((previous.length - 1) / 2)]) / 2 : null;
  const latest = dailyOrders.at(-1);
  const suddenDrop = mainProduct && median > 0 && latest <= median * suddenDropRatio;
  const pacing = model?.performance?.today?.pacing || {};
  const currentHour = currentHourCampaign(model?.performance || {});
  const todaySpend = Number(valueOf(currentHour.summary, "spend", "costs"));
  const dailyBudget = Number(valueOf(campaign, "budget", "daily_budget", "dailyBudget"));
  const latestHour = Number(currentHour.latestHour);
  const earlyBudgetExhaustion = Number.isFinite(todaySpend) && dailyBudget > 0 && Number.isFinite(latestHour)
    ? todaySpend >= dailyBudget * 0.98 && latestHour < 20
    : null;
  const changes = pacing.prior_7d_same_hour?.changes || pacing.prior7SameHour?.changes || {};
  const topToday = placementTopShare(todayPlacements);
  const topMature = placementTopShare(maturePlacements);
  const topDelta = topToday == null || topMature == null ? null : topToday - topMature;
  const signals = [
    ["同小时展示", valueOf(changes, "impressions"), (value) => formatSignedRatio(value)],
    ["同小时点击", valueOf(changes, "clicks"), (value) => formatSignedRatio(value)],
    ["同小时订单", valueOf(changes, "orders"), (value) => formatSignedRatio(value)],
    ["同小时CPC", valueOf(changes, "cpc"), (value) => formatSignedRatio(value)],
    ["头部点击占比", topDelta, (value) => formatSignedRatio(value)],
    ["预算过早耗尽", earlyBudgetExhaustion, (value) => value ? "是" : "否"],
  ];
  const risk = suddenDrop || earlyBudgetExhaustion === true || Number(changes.clicks) <= -0.3 || Number(changes.orders) <= -0.3 || Number(changes.cpc) >= 0.3 || Number(topDelta) <= -0.15;
  return (
    <section className={`main-product-alert-panel ${risk ? "risk" : "quiet"}`}>
      <div className="diagnostic-section-title"><h4>主力产品异常监控</h4><span>配置口径：近{windowDays}日≥{minOrders}单且日销量CV≤{formatRatio(maxDailyCv, 0)}</span></div>
      <div className="main-product-summary"><b>{mainProduct ? "主力产品" : dailyOrders.length === windowDays ? "未达到主力条件" : "主力样本不足"}</b><span>近{windowDays}日 {formatNumber(totalOrders, 0)} 单</span><span>稳定系数 {cv == null ? "—" : formatRatio(cv, 0)}</span><em>{suddenDrop ? "最新日销量突降" : risk ? "发现异常信号" : "暂无突降结论"}</em></div>
      <div className="main-product-signals">{signals.map(([label, value, formatter]) => <div key={label}><span>{label}</span><b>{displayValue(value, formatter)}</b></div>)}</div>
      <p>“头部广告位占比下降”仅表示流量结构变化，不表述为实际广告排名从第几位跌到第几位。</p>
    </section>
  );
}

function SearchTermStructurePanel({ report, matureOrders }) {
  const summary = searchTermStructureSummary(report, matureOrders);
  const text = (value, formatter) => summary.available ? formatter(value) ?? "—" : "—";
  return (
    <section className="search-structure-summary">
      <div className="diagnostic-section-title"><h4>搜索词结构</h4><span>有效词与0订单词对照</span></div>
      <div className="search-summary-grid">
        <article className="conversion">
          <header><b>有效词贡献</b><span>{text(summary.conversion.terms, (value) => `${formatNumber(value, 0)}个词`)}</span></header>
          <dl>
            <div><dt>订单</dt><dd>{text(summary.conversion.orders, (value) => formatNumber(value, 0))}</dd></div>
            <div><dt>销售额</dt><dd>{text(summary.conversion.sales, formatMoney)}</dd></div>
            <div><dt>订单占比</dt><dd>{text(summary.conversion.orderShare, formatRatio)}</dd></div>
          </dl>
        </article>
        <article className="waste">
          <header><b>0订单词消耗</b><span>{text(summary.waste.terms, (value) => `${formatNumber(value, 0)}个词`)}</span></header>
          <dl>
            <div><dt>花费</dt><dd>{text(summary.waste.spend, formatMoney)}</dd></div>
            <div><dt>花费占比</dt><dd>{text(summary.waste.spendShare, formatRatio)}</dd></div>
            <div className="max-click-term"><dt>最大点击无单词</dt><dd title={summary.waste.maxClicksTerm || undefined}>{summary.available && summary.waste.maxClicksTerm ? `${summary.waste.maxClicksTerm} · ${summary.waste.maxClicks}次` : "—"}</dd></div>
          </dl>
        </article>
      </div>
      <div className="sample-summary">
        <span>达到有效样本 <b>{text(summary.sample.effective, (value) => formatNumber(value, 0))}</b></span>
        <span>值得重点查看 <b>{text(summary.sample.attention, (value) => formatNumber(value, 0))}</b></span>
        <span>样本不足 <b>{text(summary.sample.insufficient, (value) => formatNumber(value, 0))}</b></span>
        <small>有效样本按点击≥10统计，用于降低偶然性。</small>
      </div>
    </section>
  );
}

function OverviewTab({ shopId, model, catalogCampaign, selectedProduct, window = "14d", windowMetrics = {}, refreshToken, secondaryLoading, secondaryError }) {
  const campaign = model.campaign || {};
  const campaignContext = { ...campaign, ...(catalogCampaign || {}) };
  const campaignId = campaignIdOf(campaign);
  const performance = model.performance || {};
  const matureLayer = performance.mature_14d || performance.mature || {};
  const deepReports = matureDeepReports(model);
  const matureCampaignRows = campaignScopedRows(firstRows(matureLayer.campaigns, deepReportRows(deepReports.campaigns)), campaignId);
  const mature = matureLayer.campaign || matureLayer.metrics || matureCampaignRows[0] || matureLayer;
  const selectedMature = Object.keys(windowMetrics || {}).length ? windowMetrics : window === "14d" ? mature : {};
  const currentHour = currentHourCampaign(performance);
  const todayLayer = currentHour.layer;
  const today = currentHour.summary;
  const todayPlacements = campaignScopedRows(todayLayer.placements, campaignId);
  const todayTargets = campaignScopedRows(todayLayer.targets, campaignId);
  const placementHour = hourlyMetricDisplay(performance, "placements");
  const targetHour = hourlyMetricDisplay(performance, "targets");
  const displayedHourPlacements = campaignScopedRows(placementHour.rows, campaignId);
  const displayedHourTargets = campaignScopedRows(targetHour.rows, campaignId);
  const placementHourTitle = placementHour.isFallback ? `最近可用小时广告位（${placementHour.reportDate}）` : "当前小时广告位";
  const targetHourTitle = targetHour.isFallback ? `最近可用小时投放对象（${targetHour.reportDate}）` : "当前小时投放对象";
  const matureDailyTrend = campaignScopedRows(
    firstRows(windowMetrics?.daily_trend, windowMetrics?.dailyTrend, window === "14d" ? matureLayer.daily_trend || matureLayer.dailyTrend : []),
    campaignId,
  );
  const searchReport = deepReports.search_terms || deepReports.searchTerms || {};
  const searchHighlights = searchTermHighlights(searchReport);
  const searchRevision = (kind) => searchTermDataRevision({
    campaignId,
    kind,
    refreshToken,
    report: searchReport,
    sources: model.sources,
    meta: model.meta,
  });
  const placementRows = placementPerformanceRows(deepReports.placements, campaign);
  const placementSummary = placementPerformanceSummary(placementRows);
  return (
    <div className="diagnostic-tab-body">
      <div className="diagnostic-overview-top-grid">
        <MatureTrendChart rows={matureDailyTrend} window={window} />
        <SkuOperatingSummary model={model} selectedProduct={selectedProduct} window={window} />
      </div>

      <BudgetTrafficPanel campaign={campaignContext} mature={selectedMature} today={today} todayLayer={todayLayer} matureDailyTrend={matureDailyTrend} selectedProduct={selectedProduct} model={model} window={window} />
      <DiagnosticFlowPanel campaign={campaignContext} selectedProduct={selectedProduct} todayPlacements={todayPlacements} maturePlacements={placementRows} />
      <MainProductAlertPanel campaign={campaignContext} model={model} selectedProduct={selectedProduct} todayPlacements={todayPlacements} maturePlacements={placementRows} />
      <AdjustmentReviewPanel reviews={model.adjustmentReviews} />

      <section className="diagnostic-metric-section">
        <div className="diagnostic-section-title"><h4><ExplainedLabel label="成熟深度信号" help={SECTION_HELP["成熟深度信号"]} /></h4><span>固定14日D-2成熟 · 搜索词为投放级，广告位为广告位级</span></div>
        <div className="diagnostic-search-term-guide" aria-label="关键词悬浮分析说明">
          <strong>悬浮看综合价值</strong>
          <span>表格保留全部明细，雷达综合单量、点击率、转化率、效率和样本量</span>
          <span>评分与排名仅用于当前页横向比较</span>
        </div>
        <SearchTermStructurePanel report={searchReport} matureOrders={metricValue(mature, "orders", "order_count")} />
        <div className="diagnostic-two-column diagnostic-search-term-grid">
          <SearchTermPager key={`${campaignId}-conversion`} shopId={shopId} campaign={campaign} kind="conversion" title="Top转化搜索词" initialRows={searchHighlights.conversion} total={valueOf(searchReport, "conversion_count", "conversionCount") || searchHighlights.conversion.length} emptyCopy="未取得成熟搜索词转化报告。" dataRevision={searchRevision("conversion")} />
          <SearchTermPager key={`${campaignId}-waste`} shopId={shopId} campaign={campaign} kind="waste" title="Top浪费搜索词（0订单按花费）" initialRows={searchHighlights.waste} total={valueOf(searchReport, "waste_count", "wasteCount") || searchHighlights.waste.length} emptyCopy="未取得成熟搜索词报告，不能判断无单浪费。" dataRevision={searchRevision("waste")} />
        </div>
        <DataTable title="广告位效率" rows={placementRows} summaryRow={placementSummary} grain="placement" freshness="mature_14d" tableClassName="diagnostic-placement-table" columns={[
          { label: "广告位名称", keys: ["placement", "placement_name", "name", "广告位"] },
          { label: "广告活动竞价方案", keys: ["bidding_strategy"] },
          { label: "竞价调整", keys: ["bid_adjustment"], formatter: (value) => value === "—" ? value : `${formatNumber(value, 0)}%` },
          { label: "展示量", keys: ["impressions"], formatter: (value) => formatNumber(value, 0) },
          { label: "点击量", keys: ["clicks"], formatter: (value) => formatNumber(value, 0) },
          { label: "点击率", keys: ["ctr"], formatter: (value) => formatRatio(value, 2) },
          { label: "总成本", keys: ["spend", "costs"], formatter: formatMoney },
          { label: "花费占比", keys: ["spend_share"], formatter: formatRatio },
          { label: "CPC", keys: ["cpc"], formatter: formatMoney },
          { label: "购买量", keys: ["orders"], formatter: (value) => formatNumber(value, 0) },
          { label: "订单占比", keys: ["order_share"], formatter: formatRatio },
          { label: "CVR", keys: ["cvr"], formatter: formatRatio },
          { label: "销售额", keys: ["sales"], formatter: formatMoney },
          { label: "ACoS", keys: ["acos"], rowFormatter: (value, row) => formatAcos(value, row, 2) },
          { label: "较整体ACoS", keys: ["acos_delta"], formatter: formatRatioDelta },
          { label: "样本可信度", keys: ["sample_confidence"] },
        ]} emptyCopy="未取得D-2成熟广告位报告。" />
        <div className="diagnostic-two-column">
          <DataTable title={placementHourTitle} rows={displayedHourPlacements} grain="placement" freshness={placementHour.freshness} columns={[
            { label: "小时", keys: ["hour"], formatter: (value) => `${formatNumber(value, 0)}:00` },
            { label: "广告位", keys: ["placement", "placement_name", "name"] },
            { label: "花费", keys: ["spend", "costs"], formatter: formatMoney },
            { label: "点击", keys: ["clicks"], formatter: (value) => formatNumber(value, 0) },
            { label: "订单", keys: ["orders"], formatter: (value) => formatNumber(value, 0) },
          ]} emptyCopy="当前小时广告位数据尚未回填。" />
          <DataTable title={targetHourTitle} rows={displayedHourTargets} grain="target" freshness={targetHour.freshness} columns={[
            { label: "小时", keys: ["hour"], formatter: (value) => `${formatNumber(value, 0)}:00` },
            { label: "投放对象", keys: ["targeting", "keyword_text", "asin"] },
            { label: "花费", keys: ["spend", "costs"], formatter: formatMoney },
            { label: "点击", keys: ["clicks"], formatter: (value) => formatNumber(value, 0) },
            { label: "订单", keys: ["orders"], formatter: (value) => formatNumber(value, 0) },
          ]} emptyCopy="当前小时投放数据尚未回填。" />
        </div>
      </section>
      {secondaryLoading ? (
        <section className="diagnostic-sku-overview diagnostic-sku-loading">
          <div className="diagnostic-sku-overview-header"><span>经营信息</span><h3>SKU经营概况</h3><p>正在补充库存、销量、利润和退货数据…</p></div>
          <ArrowClockwise className="spin" size={28} />
        </section>
      ) : (
        <>
          {secondaryError && <div className="diagnostic-inline-error"><Warning size={18} weight="fill" />{secondaryError}</div>}
          <SkuOverview model={model} selectedProduct={selectedProduct} window={window} />
        </>
      )}
    </div>
  );
}

function StructureTab({ model, selectedProduct, window = "14d" }) {
  const structure = model.structure || {};
  const campaignId = campaignIdOf(model.campaign);
  const matureLayer = model.performance?.mature_14d || {};
  const deepReports = matureDeepReports(model);
  const adGroups = relatedRows(structure.ad_groups || structure.groups, selectedProduct);
  const keywords = relatedRows(structure.keywords, selectedProduct);
  const targets = relatedRows(structure.product_targets || structure.targets, selectedProduct);
  const negativeKeywords = relatedRows(structure.negative_keywords, selectedProduct);
  const negativeTargets = relatedRows(structure.negative_product_targets || structure.negative_targets, selectedProduct);
  const placements = relatedRows(firstRows(structure.placements, structure.placement_performance, deepReportRows(deepReports.placements)), selectedProduct);
  const searchTerms = relatedRows(deepReportRows(deepReports.search_terms || deepReports.searchTerms), selectedProduct);
  const purchasedItems = relatedRows(deepReportRows(deepReports.purchased_items || deepReports.purchasedItems), selectedProduct);
  const groupHour = hourlyMetricDisplay(model.performance, "ad_groups");
  const productHour = hourlyMetricDisplay(model.performance, "ad_products");
  const targetHour = hourlyMetricDisplay(model.performance, "targets");
  const displayedHourGroups = relatedRows(campaignScopedRows(groupHour.rows, campaignId), selectedProduct);
  const displayedHourProducts = relatedRows(campaignScopedRows(productHour.rows, campaignId), selectedProduct);
  const displayedHourTargets = relatedRows(campaignScopedRows(targetHour.rows, campaignId), selectedProduct);
  const hourTitle = (entry, noun) => entry.isFallback ? `最近可用小时${noun}（${entry.reportDate}）` : `当前小时${noun}`;
  const matureTargets = relatedRows(firstRows(matureLayer.targets, deepReportRows(deepReports.targets)), selectedProduct);
  const matureGroups = relatedRows(deepReportRows(deepReports.groups), selectedProduct);
  const matureRecommendations = campaignScopedRows(matureLayer.recommendations, campaignId);
  return (
    <div className="diagnostic-tab-body structure-stack">
      <div className="granularity-note"><Info size={19} weight="fill" /><span>当前SKU只用于筛选同广告组的相关结构。若广告组包含多个SKU，关键词和商品投放表现仍是投放级上下文，不能直接归因给单个SKU。</span></div>
      {window !== "14d" && <div className="granularity-note"><Info size={19} weight="fill" /><span>当前选择近{campaignWindowDays(window)}天；经营趋势按所选周期展示，投放结构的成熟深度报告仍固定为14日D-2口径。</span></div>}
      <div className="diagnostic-two-column">
        <DataTable title={hourTitle(groupHour, "广告组表现")} rows={displayedHourGroups} grain="ad_group" freshness={groupHour.freshness} columns={[
          { label: "小时", keys: ["hour"], formatter: (value) => `${formatNumber(value, 0)}:00` },
          { label: "广告组", keys: ["group_name", "groupName", "group_id", "groupId", "广告组"] },
          { label: "花费", keys: ["spend", "costs"], formatter: formatMoney },
          { label: "点击", keys: ["clicks"], formatter: (value) => formatNumber(value, 0) },
          { label: "订单", keys: ["orders"], formatter: (value) => formatNumber(value, 0) },
        ]} emptyCopy="当前小时广告组数据尚未回填。" />
        <DataTable title={hourTitle(productHour, "广告商品表现")} rows={displayedHourProducts} grain="ad_product" freshness={productHour.freshness} columns={[
          { label: "小时", keys: ["hour"], formatter: (value) => `${formatNumber(value, 0)}:00` },
          { label: "SKU / ASIN", value: (row) => `${valueOf(row, "sku", "msku") || "SKU未知"} / ${valueOf(row, "asin") || "ASIN未知"}` },
          { label: "花费", keys: ["spend", "costs"], formatter: formatMoney },
          { label: "点击", keys: ["clicks"], formatter: (value) => formatNumber(value, 0) },
          { label: "订单", keys: ["orders"], formatter: (value) => formatNumber(value, 0) },
        ]} emptyCopy="当前小时广告商品数据尚未回填。" />
      </div>
      <DataTable title={hourTitle(targetHour, "投放表现")} rows={displayedHourTargets} grain="target" freshness={targetHour.freshness} columns={[
        { label: "小时", keys: ["hour"], formatter: (value) => `${formatNumber(value, 0)}:00` },
        { label: "投放对象", keys: ["targeting", "keyword_text", "asin"] },
        { label: "匹配", keys: ["match_type", "matchType"] },
        { label: "花费", keys: ["spend", "costs"], formatter: formatMoney },
        { label: "订单", keys: ["orders"], formatter: (value) => formatNumber(value, 0) },
        { label: "ACoS", keys: ["acos"], rowFormatter: formatAcos },
      ]} emptyCopy="当前小时投放数据尚未回填。" />
      <DataTable title="广告组" rows={adGroups} grain="ad_group" freshness="config" columns={[
        { label: "广告组", keys: ["group_name", "groupName", "name"] },
        { label: "groupId", keys: ["group_id", "groupId", "id"] },
        { label: "状态", keys: ["state", "status", "servingStatus"] },
        { label: "默认竞价", keys: ["default_bid", "defaultBid", "bid"], formatter: formatMoney },
      ]} />
      <DataTable title="关键词投放" rows={keywords} grain="keyword" freshness="config" columns={[
        { label: "关键词", keys: ["keyword_text", "keywordText", "targeting", "text"] },
        { label: "匹配", keys: ["match_type", "matchType"] },
        { label: "竞价", keys: ["bid"], formatter: formatMoney },
        { label: "状态", keys: ["state", "status"] },
        { label: "ACoS", keys: ["acos"], rowFormatter: formatAcos },
      ]} />
      <DataTable title="商品投放" rows={targets} grain="product_target" freshness="config" columns={[
        { label: "投放对象", keys: ["targeting", "expression", "asin"] },
        { label: "targetingId", keys: ["targeting_id", "targetingId", "id"] },
        { label: "竞价", keys: ["bid"], formatter: formatMoney },
        { label: "状态", keys: ["state", "status"] },
        { label: "ACoS", keys: ["acos"], rowFormatter: formatAcos },
      ]} />
      <div className="diagnostic-two-column">
        <DataTable title="成熟广告组表现" rows={matureGroups} grain="ad_group" freshness="mature_14d" columns={[
          { label: "广告组", keys: ["group_name", "groupName", "group_id", "groupId"] },
          { label: "花费", keys: ["spend", "costs"], formatter: formatMoney },
          { label: "销售额", keys: ["sales"], formatter: formatMoney },
          { label: "ACoS", keys: ["acos"], rowFormatter: formatAcos },
        ]} emptyCopy="未取得D-2成熟广告组报告。" />
        <DataTable title="成熟投放表现" rows={matureTargets} grain="target" freshness="mature_14d" columns={[
          { label: "投放对象", keys: ["targeting", "keyword_text", "asin", "投放"] },
          { label: "花费", keys: ["spend", "costs"], formatter: formatMoney },
          { label: "订单", keys: ["orders"], formatter: (value) => formatNumber(value, 0) },
          { label: "ACoS", keys: ["acos"], rowFormatter: formatAcos },
        ]} emptyCopy="未取得D-2成熟投放报告。" />
      </div>
      <DataTable title="成熟规则建议" rows={matureRecommendations} grain="target" freshness="mature_14d" columns={[
        { label: "对象", keys: ["target_text", "targeting", "entity_name", "entity_id"] },
        { label: "建议", keys: ["action", "recommended_action"] },
        { label: "优先级", keys: ["priority", "priority_level"] },
        { label: "依据", keys: ["reason", "rationale", "message"] },
      ]} emptyCopy="成熟层未返回该活动的规则建议。" />
      <DataTable title="成熟搜索词" rows={searchTerms} grain="target" freshness="mature_14d" columns={[
        { label: "搜索词", keys: ["search_term", "searchTerm", "query", "用户搜索词", "targeting"] },
        { label: "投放词", keys: ["keyword_text", "keywordText", "target", "投放"] },
        { label: "花费", keys: ["spend", "costs"], formatter: formatMoney },
        { label: "订单", keys: ["orders", "order_count"], formatter: (value) => formatNumber(value, 0) },
        { label: "ACoS", keys: ["acos"], rowFormatter: formatAcos },
      ]} emptyCopy="未取得D-2成熟搜索词报告。" />
      <DataTable title="广告归因购买商品" rows={purchasedItems} grain="target" freshness="mature_14d" columns={[
        { label: "购买ASIN", keys: ["purchased_asin", "purchasedAsin", "其他ASIN", "asin", "ASIN"] },
        { label: "购买SKU", keys: ["purchased_sku", "purchasedSku", "sku", "SKU"] },
        { label: "订单", keys: ["orders", "order_count"], formatter: (value) => formatNumber(value, 0) },
        { label: "销售额", keys: ["sales"], formatter: formatMoney },
      ]} emptyCopy="未取得D-2成熟购买商品报告。" />
      <div className="diagnostic-two-column">
        <DataTable title="否定关键词" rows={negativeKeywords} grain="keyword" freshness="config" columns={[
          { label: "关键词", keys: ["keyword_text", "keywordText", "targeting"] },
          { label: "匹配", keys: ["match_type", "matchType"] },
          { label: "状态", keys: ["state", "status"] },
        ]} />
        <DataTable title="否定商品投放" rows={negativeTargets} grain="product_target" freshness="config" columns={[
          { label: "投放对象", keys: ["targeting", "expression", "asin"] },
          { label: "状态", keys: ["state", "status"] },
        ]} />
      </div>
      <DataTable title="广告位表现" rows={placements} grain="placement" freshness="mature_14d" columns={[
        { label: "广告位", keys: ["placement", "placement_name", "name", "广告位"] },
        { label: "花费", keys: ["spend", "costs"], formatter: formatMoney },
        { label: "销售额", keys: ["sales"], formatter: formatMoney },
        { label: "订单", keys: ["orders"], formatter: (value) => formatNumber(value, 0) },
        { label: "ACoS", keys: ["acos"], rowFormatter: formatAcos },
      ]} />
    </div>
  );
}

function SkuOverview({ model, selectedProduct, window = "14d" }) {
  const windowDays = campaignWindowDays(window);
  const { product, listing, online, sales } = skuOperatingContext(model, selectedProduct);
  const returns = product.returns || listing.returns || {};
  const salesTrend = skuSalesTrendRows(product.sales_trend || product.salesTrend || sales.trend || listing.sales_trend || listing.salesTrend).slice(-windowDays);
  const returnRows = firstRows(returns.top_reasons, returns.topReasons, returns.top_rows, returns.topRows, returns.reasons, returns.rows, returns);
  const deepProducts = deepReportRows(matureDeepReports(model).products);
  const sku = String(valueOf(product, "sku", "msku") || "");
  const asin = String(valueOf(product, "asin") || "").toUpperCase();
  const focusedDeepProducts = deepProducts.filter((row) => {
    const rowSku = String(valueOf(row, "sku", "msku") || "");
    const rowAsin = String(valueOf(row, "asin") || "").toUpperCase();
    return (!sku || rowSku === sku) && (!asin || rowAsin === asin);
  });
  return (
    <section className="diagnostic-sku-overview">
      <div className="diagnostic-sku-overview-header">
        <span>经营信息</span>
        <h3>商品明细</h3>
        <p>补充商品身份、每日销量、退货与成熟广告商品表现。</p>
      </div>
      {!selectedProduct && <EmptyPanel icon={Package} title="没有广告商品" copy="赛狐 API 未返回 adId、SKU 或 ASIN，相关经营信息暂时未知。" />}
      <section className="diagnostic-metric-section">
        <div className="diagnostic-section-title"><h4><ExplainedLabel label="SKU基础信息" help={SECTION_HELP["Listing 与生命周期"]} /></h4><span>当前聚焦商品</span></div>
        <FactGrid items={[
          { label: "SKU", value: metricValue(product, "sku", "msku", "seller_sku"), grain: "sku", freshness: "live" },
          { label: "ASIN", value: metricValue(product, "asin"), grain: "sku", freshness: "live" },
          { label: "adId", value: metricValue(product, "ad_id", "adId"), grain: "ad_product", freshness: "config" },
          { label: "上架时间", value: metricValue(product, "open_date", "openDate", "listing_date"), grain: "sku", freshness: "live" },
          { label: "上架天数", value: metricValue(product, "listing_age_days", "age_days"), formatter: (value) => formatNumber(value, 0), grain: "sku", freshness: "live" },
          { label: "新品阶段", value: lifecycleLabel(product).label, grain: "sku", freshness: "live" },
          { label: "在线状态", value: firstPresent(metricValue(product, "online_status", "onlineStatus"), metricValue(online, "onlineStatus", "online_status")), grain: "sku", freshness: "live" },
          { label: "售价", value: firstPresent(metricValue(product, "price", "sale_price", "listing_price"), metricValue(online, "listingPrice", "standardPrice", "price")), formatter: formatMoney, grain: "sku", freshness: "live" },
        ]} showMeta={false} />
      </section>
      <DataTable title={`${windowDays}日SKU每日销售趋势`} rows={salesTrend} showMeta={false} columns={[
        { label: "日期", keys: ["date", "report_date", "day"] },
        { label: "销售额", keys: ["sales", "revenue", "salePrice"], formatter: formatMoney },
        { label: "订单", keys: ["orders", "order_count", "orderNum"], formatter: (value) => formatNumber(value, 0) },
        { label: "销量", keys: ["units", "quantity", "productNum"], formatter: (value) => formatNumber(value, 0) },
      ]} emptyCopy="未取得该SKU的每日销售趋势。" />
      <DataTable title="30日FBA退货原因" rows={returnRows} showMeta={false} columns={[
        { label: "退货原因", keys: ["reason", "return_reason", "reason_name", "name"] },
        { label: "退货数量", keys: ["quantity", "return_quantity", "count"], formatter: (value) => formatNumber(value, 0) },
        { label: "占比", keys: ["rate", "ratio", "share"], formatter: formatRatio },
      ]} emptyCopy="未取得30日FBA退货原因聚合。" />
      <DataTable title="成熟广告商品表现" rows={focusedDeepProducts} showMeta={false} columns={[
        { label: "SKU", keys: ["sku", "msku"] },
        { label: "ASIN", keys: ["asin"] },
        { label: "花费", keys: ["spend", "costs"], formatter: formatMoney },
        { label: "销售额", keys: ["sales"], formatter: formatMoney },
        { label: "订单", keys: ["orders"], formatter: (value) => formatNumber(value, 0) },
        { label: "ACoS", keys: ["acos"], rowFormatter: formatAcos },
      ]} emptyCopy="未取得D-2成熟广告商品报告，不能把活动数据下推到该SKU。" />
    </section>
  );
}

function SourcesTab({ model }) {
  const quality = model.dataQuality || {};
  const deepSources = Object.entries(matureDeepReports(model)).flatMap(([name, report]) => {
    const source = report?.source;
    if (!source) return [];
    return [{ name: `mature_14d.${name}`, ...(typeof source === "object" ? source : { source }) }];
  });
  const sourceRows = [...model.sources, ...deepSources];
  const missing = rowsOf(quality.missing_fields || quality.missing);
  const warnings = rowsOf(quality.warnings || quality.issues);
  const errors = rowsOf(quality.errors || quality.failures);
  return (
    <div className="diagnostic-tab-body">
      <section className="diagnostic-quality-summary">
        <div><Database size={27} weight="duotone" /><span><small><ExplainedLabel label="整体数据质量" help={FACT_HELP["整体数据质量"]} /></small><b>{valueOf(quality, "status", "coverage_status") || "未知"}</b></span></div>
        <div><small><ExplainedLabel label="完整度" help={FACT_HELP["完整度"]} /></small><b>{displayValue(valueOf(quality, "completeness", "coverage_rate"), formatRatio)}</b></div>
        <div><small><ExplainedLabel label="API抓取时间" help={FACT_HELP["API抓取时间"]} /></small><b>{displayValue(valueOf(model.meta, "fetched_at", "generated_at", "observed_at"), formatDateTime)}</b></div>
      </section>
      <DataTable title="数据源与时效" rows={sourceRows} grain="unknown" columns={[
        { label: "来源ID", keys: ["source_id", "name", "source"] },
        { label: "端点 / 来源", keys: ["endpoint", "source"] },
        { label: "状态", keys: ["status", "coverage_status"] },
        { label: "来源层", value: sourceLayerLabel },
        { label: "抓取 / 文件时间", keys: ["fetched_at", "requested_at", "observed_at"], formatter: formatDateTime },
        { label: "有效数据日期", keys: ["effective_date", "data_through", "source_end_date", "report_date", "latest_hour"] },
        { label: "返回行数", keys: ["row_count", "rows", "count"], formatter: (value) => formatNumber(value, 0) },
        { label: "provisional", keys: ["provisional"] },
        { label: "realtime", keys: ["realtime"] },
      ]} emptyCopy="后端未返回 sources，无法核对每个字段来自哪个赛狐接口。" />
      <div className="diagnostic-three-column">
        <EvidenceList title="缺失字段" rows={missing} kind="blocker" />
        <EvidenceList title="质量预警" rows={warnings} kind="conflict" />
        <EvidenceList title="接口错误" rows={errors} kind="blocker" />
      </div>
      <div className="granularity-note"><Info size={19} weight="fill" /><span>结构、Listing、经营信息和当前小时数据会在后台更新。成熟归因截至 D-2；当前小时数据为暂定值，可能延迟并回补。</span></div>
    </div>
  );
}

function DetailPanel({ shop, shopId, model, catalogCampaign, selectedCampaignId, selectedProductKey, onSelectProduct, onOpenControls, activeTab, onTabChange, window, windowMetrics, loading, secondaryLoading, secondaryError, error, refreshToken }) {
  const modelCampaignId = campaignIdOf(model?.campaign);
  const matches = model && (!modelCampaignId || modelCampaignId === String(selectedCampaignId));
  const products = useMemo(() => focusProducts(model), [model]);
  const selectedProduct = products.find((product) => product._key === selectedProductKey) || products[0] || null;
  const activeTabInfo = DETAIL_TABS.find((tab) => tab.id === activeTab) || DETAIL_TABS[0];

  useEffect(() => {
    if (selectedProduct && selectedProduct._key !== selectedProductKey) onSelectProduct(selectedProduct._key);
  }, [selectedProduct, selectedProductKey, onSelectProduct]);

  useEffect(() => {
    if (!DETAIL_TABS.some((tab) => tab.id === activeTab)) onTabChange("overview");
  }, [activeTab, onTabChange]);

  if (!matches && loading) return (
    <article className="detail-panel diagnostic-detail-state">
      <span className="diagnostic-loading-selection">{shop.name} · {campaignNameOf(catalogCampaign)} · ID {selectedCampaignId}</span>
      <ArrowClockwise className="spin" size={34} />
      <b>活动已选中，正在读取首屏诊断…</b>
      <span>该活动没有本地详情时会实时补取；首屏返回后，其余投放结构继续在后台加载。</span>
    </article>
  );
  if (!matches) return <article className="detail-panel diagnostic-detail-state error"><Warning size={34} weight="duotone" /><b>所选活动详情暂不可用</b><span>{error || "赛狐 API 未返回该活动，未使用其他活动数据代替。"}</span></article>;

  return (
    <article className="detail-panel diagnostic-detail-panel">
      {error && <div className="diagnostic-inline-error"><Warning size={18} weight="fill" />{error}</div>}
      <CampaignHeader shop={shop} model={model} catalogCampaign={catalogCampaign} selectedProduct={selectedProduct} onOpenControls={onOpenControls} />
      <nav className="diagnostic-detail-tabs" aria-label="广告诊断详情">
        {DETAIL_TABS.map((tab) => <button className={activeTab === tab.id ? "active" : ""} key={tab.id} type="button" onClick={() => onTabChange(tab.id)}>{tab.label}</button>)}
        <FloatingHelp className="diagnostic-tab-help" title={activeTabInfo.label} text={activeTabInfo.help} />
      </nav>
      {activeTab === "overview" && <OverviewTab shopId={shopId} model={model} catalogCampaign={catalogCampaign} selectedProduct={selectedProduct} window={window} windowMetrics={windowMetrics} refreshToken={refreshToken} secondaryLoading={secondaryLoading} secondaryError={secondaryError} />}
      {activeTab !== "overview" && secondaryLoading && <div className="diagnostic-secondary-loading"><ArrowClockwise className="spin" size={28} /><b>首屏已就绪，正在后台补充投放结构</b><span>完成后会自动显示，无需刷新页面。</span></div>}
      {activeTab !== "overview" && !secondaryLoading && secondaryError && <div className="diagnostic-inline-error"><Warning size={18} weight="fill" />{secondaryError}</div>}
      {activeTab === "structure" && !secondaryLoading && <StructureTab model={model} selectedProduct={selectedProduct} window={window} />}
    </article>
  );
}

export function AdDiagnosticView({
  shop = PILOT_SHOP,
  refreshToken = 0,
  onLoadingChange,
  onWindowChange,
  publishedCampaigns = [],
  publishedCampaignDailyTrend = [],
}) {
  const shopId = shop.id;
  const preferredCampaignId = shop.defaultCampaignId || DEFAULT_CAMPAIGN_ID;
  const [model, setModel] = useState(null);
  const [catalog, setCatalog] = useState([]);
  // Hydrate the campaign rail from the hourly shop snapshot before requesting
  // a detail. Otherwise an uncached preferred detail leaves the whole page at
  // 0/0 while the request waits on Sellfox.
  const [selectedCampaignId, setSelectedCampaignId] = useState("");
  const [selectedProductKey, setSelectedProductKey] = useState("");
  const [activeTab, setActiveTab] = useState("overview");
  const [query, setQuery] = useState("");
  const [campaignWindow, setCampaignWindow] = useState("14d");
  const [matchTypeFilter, setMatchTypeFilter] = useState("all");
  const [sortKey, setSortKey] = useState("default");
  const [sortDirection, setSortDirection] = useState("desc");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [secondaryLoading, setSecondaryLoading] = useState(true);
  const [secondaryError, setSecondaryError] = useState("");
  const [error, setError] = useState("");
  const [controlOpen, setControlOpen] = useState(false);
  const refreshGenerationRef = useRef(refreshToken);

  useEffect(() => { onLoadingChange?.(loading); }, [loading, onLoadingChange]);
  useEffect(() => { onWindowChange?.(campaignWindow); }, [campaignWindow, onWindowChange]);

  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;
    const forceRefresh = refreshToken !== refreshGenerationRef.current;
    refreshGenerationRef.current = refreshToken;
    setLoading(true);
    setSecondaryLoading(true);
    setSecondaryError("");
    setError("");

    async function load() {
      if (!selectedCampaignId) {
        const catalogPayload = await fetchDiagnostic({ shopId, refresh: forceRefresh, signal: controller.signal });
        if (disposed) return;
        const catalogModel = normalizeDiagnosticPayload(catalogPayload);
        const fallbackCampaignId = campaignIdOf(sortCampaigns(catalogModel.campaigns, preferredCampaignId)[0]);
        setCatalog(sortCampaigns(catalogModel.campaigns, preferredCampaignId));
        if (fallbackCampaignId) setSelectedCampaignId(fallbackCampaignId);
        return;
      }
      let payload;
      try {
        payload = await fetchDiagnostic({ shopId, campaignId: selectedCampaignId, section: "overview", refresh: forceRefresh, signal: controller.signal });
      } catch (requestError) {
        const canFallback = selectedCampaignId === DEFAULT_CAMPAIGN_ID && [400, 404].includes(requestError?.status);
        if (!canFallback) throw requestError;
        const catalogPayload = await fetchDiagnostic({ shopId, signal: controller.signal });
        const catalogModel = normalizeDiagnosticPayload(catalogPayload);
        const fallbackCampaignId = campaignIdOf(sortCampaigns(catalogModel.campaigns, preferredCampaignId)[0]);
        if (!fallbackCampaignId) throw requestError;
        if (!disposed) setCatalog((current) => sortCampaigns(dedupeCampaigns([...current, ...catalogModel.campaigns]), preferredCampaignId));
        payload = await fetchDiagnostic({ shopId, campaignId: fallbackCampaignId, section: "overview", refresh: forceRefresh, signal: controller.signal });
      }
      if (disposed) return;
      const next = normalizeDiagnosticPayload(payload);
      const responseCampaignId = campaignIdOf(next.campaign);
      setCatalog((current) => sortCampaigns(dedupeCampaigns([...current, ...next.campaigns]), preferredCampaignId));
      setModel(next);
      setLoading(false);
      if (responseCampaignId && responseCampaignId !== String(selectedCampaignId)) setSelectedCampaignId(responseCampaignId);
      if (!responseCampaignId) return;

      const catalogRequest = fetchDiagnostic({ shopId, signal: controller.signal }).then((catalogPayload) => {
        if (disposed) return;
        const catalogModel = normalizeDiagnosticPayload(catalogPayload);
        setCatalog((current) => sortCampaigns(dedupeCampaigns([...current, ...catalogModel.campaigns]), preferredCampaignId));
      });
      const fullRequest = fetchDiagnostic({ shopId, campaignId: responseCampaignId, section: "full", refresh: forceRefresh, signal: controller.signal }).then((fullPayload) => {
        if (disposed) return;
        const fullModel = normalizeDiagnosticPayload(fullPayload);
        if (campaignIdOf(fullModel.campaign) === String(responseCampaignId)) {
          setModel((current) => mergeDiagnosticModels(current, fullModel));
          setCatalog((current) => sortCampaigns(dedupeCampaigns([...current, ...fullModel.campaigns]), preferredCampaignId));
        }
      });
      const results = await Promise.allSettled([catalogRequest, fullRequest]);
      if (!disposed && results[1].status === "rejected" && results[1].reason?.name !== "AbortError") {
        setSecondaryError(results[1].reason?.message || "后台详情读取失败，可继续查看已加载的总览。 ");
      }
    }

    load().catch((requestError) => {
      if (requestError?.name !== "AbortError" && !disposed) {
        const showingPublishedFallback = campaignIdOf(model?.campaign) === String(selectedCampaignId);
        setError(showingPublishedFallback
          ? "实时详情暂不可用，当前展示该活动的已发布成熟快照；深层结构缺失项以“—”显示。"
          : requestError?.message || "本地诊断数据服务暂不可用。");
      }
    }).finally(() => {
      if (!disposed) {
        setLoading(false);
        setSecondaryLoading(false);
      }
    });
    return () => {
      disposed = true;
      controller.abort();
    };
  }, [shopId, preferredCampaignId, selectedCampaignId, refreshToken]);

  const publishedCampaignById = useMemo(() => new Map(
    publishedCampaigns
      .filter((campaign) => String(valueOf(campaign, "shop_id", "shopId") || "") === String(shopId))
      .map((campaign) => [campaignIdOf(campaign), campaign]),
  ), [publishedCampaigns, shopId]);
  const publishedTrendByCampaignId = useMemo(() => {
    const grouped = new Map();
    publishedCampaignDailyTrend.forEach((row) => {
      if (String(valueOf(row, "shop_id", "shopId") || "") !== String(shopId)) return;
      const campaignId = campaignIdOf(row);
      if (!campaignId) return;
      if (!grouped.has(campaignId)) grouped.set(campaignId, []);
      grouped.get(campaignId).push(row);
    });
    return grouped;
  }, [publishedCampaignDailyTrend, shopId]);
  const hydratedCatalog = useMemo(() => catalog.map((campaign) => {
    const campaignId = campaignIdOf(campaign);
    return mergePublishedCampaignMetrics(
      campaign,
      publishedCampaignById.get(campaignId),
      publishedTrendByCampaignId.get(campaignId) || [],
    );
  }), [catalog, publishedCampaignById, publishedTrendByCampaignId]);

  const orderedCampaigns = useMemo(() => (
    sortKey === "default"
      ? sortCampaigns(hydratedCatalog, preferredCampaignId, campaignWindow)
      : sortCampaignsByMetric(hydratedCatalog, sortKey, sortDirection, campaignWindow)
  ), [hydratedCatalog, campaignWindow, preferredCampaignId, sortDirection, sortKey]);
  const filteredCampaigns = useMemo(
    () => filterCampaigns(orderedCampaigns, query, "all", matchTypeFilter),
    [matchTypeFilter, orderedCampaigns, query],
  );
  const pagination = paginateCampaigns(filteredCampaigns, page, CAMPAIGNS_PER_PAGE);
  const insightProducts = useMemo(() => focusProducts(model), [model]);
  const insightProduct = insightProducts.find((product) => product._key === selectedProductKey) || insightProducts[0] || null;
  const rawSelectedCatalogCampaign = hydratedCatalog.find((campaign) => campaignIdOf(campaign) === String(selectedCampaignId)) || model?.campaign || {};
  const selectedCatalogCampaign = mergeCampaignDetailMetrics(rawSelectedCatalogCampaign, model);
  const selectedWindowMetrics = campaignWindowMetrics(selectedCatalogCampaign, campaignWindow);
  const selectedToday = currentHourCampaign(model?.performance || {}).summary || {};
  const selectedTodaySpend = Number(valueOf(selectedToday, "spend", "costs"));
  const selectedDailyBudget = Number(valueOf(selectedCatalogCampaign, "budget", "daily_budget", "dailyBudget"));
  const selectedTodayBudgetProgress = Number.isFinite(selectedTodaySpend) && selectedDailyBudget > 0
    ? selectedTodaySpend / selectedDailyBudget
    : null;
  const SortDirectionIcon = sortDirection === "asc" ? SortAscending : SortDescending;

  useEffect(() => { setPage(1); }, [campaignWindow, matchTypeFilter, query, sortDirection, sortKey]);
  useEffect(() => {
    if (sortKey !== "default") return;
    if (pagination.rows.length && !pagination.rows.some((campaign) => campaignIdOf(campaign) === String(selectedCampaignId))) {
      const selectedIndex = filteredCampaigns.findIndex((campaign) => campaignIdOf(campaign) === String(selectedCampaignId));
      if (selectedIndex >= 0) setPage(Math.floor(selectedIndex / CAMPAIGNS_PER_PAGE) + 1);
    }
  }, [filteredCampaigns, pagination.rows, selectedCampaignId, sortKey]);

  function selectCampaign(campaign) {
    const id = campaignIdOf(campaign);
    if (!id || id === String(selectedCampaignId)) return;
    setModel(buildPublishedCampaignFallbackModel(campaign));
    setSelectedCampaignId(id);
    setSelectedProductKey("");
    setActiveTab("overview");
    setControlOpen(false);
  }

  return (
    <main className="workspace-grid diagnostic-workspace">
      <aside className="queue-panel diagnostic-campaign-rail">
        <div className="queue-title">
          <span className="pilot-kicker">当前店铺 · {shop.name}</span>
          <h2 className="diagnostic-rail-heading">全部广告 <small>（{filteredCampaigns.length} / {orderedCampaigns.length}）</small><FloatingHelp title="全部广告" text={`展示${shop.name}的全部SP活动，数据会在后台持续更新。`} /></h2>
        </div>
        <div className="campaign-period-switch" role="tablist" aria-label="活动成熟数据时间窗口">
          {CAMPAIGN_WINDOWS.map((item) => <button className={campaignWindow === item.id ? "active" : ""} key={item.id} type="button" role="tab" aria-selected={campaignWindow === item.id} onClick={() => setCampaignWindow(item.id)}>{item.label}</button>)}
        </div>
        <div className="search-row">
          <label><MagnifyingGlass size={20} /><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索活动名 / campaignId" aria-label="搜索试点活动" /></label>
          <button className="icon-button" type="button" onClick={() => { setQuery(""); setPage(1); }} aria-label="清除搜索"><X size={22} /></button>
        </div>
        <div className="campaign-match-filter" role="group" aria-label="匹配状态筛选">
          <span>匹配</span>
          {CAMPAIGN_MATCH_FILTERS.map((item) => (
            <button className={matchTypeFilter === item.id ? "active" : ""} type="button" key={item.id} aria-pressed={matchTypeFilter === item.id} onClick={() => setMatchTypeFilter(item.id)}>{item.label}</button>
          ))}
        </div>
        <div className="campaign-sort-row">
          <label>
            <span>排序</span>
            <select value={sortKey} onChange={(event) => setSortKey(event.target.value)} aria-label="选择广告活动排序指标">
              {CAMPAIGN_SORT_OPTIONS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
          </label>
          <button
            className={sortKey === "default" ? "" : "active"}
            type="button"
            disabled={sortKey === "default"}
            onClick={() => setSortDirection((current) => current === "asc" ? "desc" : "asc")}
            aria-label={sortKey === "default" ? "综合排序使用固定顺序" : `切换为${sortDirection === "asc" ? "降序" : "升序"}`}
            title={sortKey === "default" ? "综合排序使用固定顺序" : `当前${sortDirection === "asc" ? "升序" : "降序"}，点击切换`}
          >
            <SortDirectionIcon size={19} weight="bold" />
          </button>
        </div>
        <div className="diagnostic-campaign-list">
          {pagination.rows.map((campaign) => {
            const selected = campaignIdOf(campaign) === String(selectedCampaignId);
            const visibleCampaign = selected ? mergeCampaignDetailMetrics(campaign, model) : campaign;
            const cardCampaign = selected && selectedTodayBudgetProgress != null
              ? { ...visibleCampaign, today_budget_progress: selectedTodayBudgetProgress, today_budget_status: "live_detail" }
              : visibleCampaign;
            return <CampaignCard campaign={cardCampaign} selected={selected} window={campaignWindow} key={campaignIdOf(campaign)} onSelect={() => selectCampaign(campaign)} />;
          })}
          {!pagination.rows.length && !loading && <EmptyPanel icon={Target} title="没有匹配活动" copy={error || "调整搜索条件后重试。"} />}
          {!catalog.length && loading && <EmptyPanel icon={ArrowClockwise} title={`正在读取${shop.name}活动`} copy="优先读取最近一次成功数据，缺失时由后端访问赛狐API。" />}
        </div>
        {!!filteredCampaigns.length && (
          <nav className="pagination-bar diagnostic-pagination" aria-label="试点活动分页">
            <span className="pagination-summary">第 {pagination.currentPage} / {pagination.pageCount} 页 · 每页10条</span>
            <div className="pagination-controls">
              <button type="button" disabled={pagination.currentPage === 1} onClick={() => setPage(pagination.currentPage - 1)} aria-label="上一页">‹</button>
              <span>{pagination.start + 1}–{Math.min(pagination.start + CAMPAIGNS_PER_PAGE, filteredCampaigns.length)} / {filteredCampaigns.length}</span>
              <button type="button" disabled={pagination.currentPage === pagination.pageCount} onClick={() => setPage(pagination.currentPage + 1)} aria-label="下一页">›</button>
            </div>
          </nav>
        )}
        <div className="diagnostic-rail-note"><ChartLine size={18} weight="duotone" /><span>当前小时为暂定数据；活动指标与SKU经营数据按上方周期联动；成熟深度报告固定为14日D-2口径。</span></div>
      </aside>
      <DetailPanel
        shop={shop}
        shopId={shopId}
        model={model}
        catalogCampaign={selectedCatalogCampaign}
        selectedCampaignId={selectedCampaignId}
        selectedProductKey={selectedProductKey}
        onSelectProduct={setSelectedProductKey}
        onOpenControls={() => setControlOpen(true)}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        window={campaignWindow}
        windowMetrics={selectedWindowMetrics}
        loading={loading}
        secondaryLoading={secondaryLoading}
        secondaryError={secondaryError}
        error={error}
        refreshToken={refreshToken}
      />
      <DiagnosticInsightRail model={model} selectedProduct={insightProduct} />
      <SpControlDrawer open={controlOpen} shopId={shopId} model={model} selectedProduct={insightProduct} onClose={() => setControlOpen(false)} />
    </main>
  );
}
