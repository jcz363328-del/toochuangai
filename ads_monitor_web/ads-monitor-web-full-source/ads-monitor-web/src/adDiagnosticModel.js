export const DIAGNOSTIC_SHOPS = Object.freeze([
  Object.freeze({ id: "475394", name: "21号站-李娜-US", currency: "USD", defaultCampaignId: "70540977760495" }),
  Object.freeze({ id: "476221", name: "23号店-侯梁-US", currency: "USD", defaultCampaignId: "" }),
]);

export const PILOT_SHOP = DIAGNOSTIC_SHOPS[0];

export function normalizeDiagnosticShops(payload) {
  if (!payload || !Array.isArray(payload.shops)) return [];
  const fallbackById = new Map(DIAGNOSTIC_SHOPS.map((shop) => [shop.id, shop]));
  const seen = new Set();
  return payload.shops.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const id = String(item.id ?? item.shop_id ?? "").trim();
    if (!id || seen.has(id)) return [];
    seen.add(id);
    const fallback = fallbackById.get(id);
    return [{
      id,
      name: String(item.name ?? item.shop_name ?? id).trim() || id,
      currency: String(item.currency ?? fallback?.currency ?? "").trim().toUpperCase(),
      marketplaceId: String(item.marketplace_id ?? item.marketplaceId ?? "").trim(),
      timezone: String(item.timezone ?? "").trim(),
      defaultCampaignId: String(item.default_campaign_id ?? fallback?.defaultCampaignId ?? "").trim(),
    }];
  });
}

export const DEFAULT_CAMPAIGN_ID = "70540977760495";
export const CAMPAIGNS_PER_PAGE = 10;

const ACTIONABLE = new Set([
  "DECREASE_BID",
  "INCREASE_BID",
  "INCREASE_BUDGET",
  "PAUSE",
  "REVIEW_TARGET",
]);

export function rowsOf(value) {
  if (Array.isArray(value)) return value;
  if (!value || typeof value !== "object") return [];
  for (const key of ["items", "item_list", "itemList", "rows", "records", "list"]) {
    if (Array.isArray(value[key])) return value[key];
  }
  return [];
}

export function valueOf(row, ...keys) {
  for (const key of keys) {
    const value = row?.[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return null;
}

export function campaignIdOf(row) {
  return String(valueOf(row, "campaign_id", "campaignId", "id") || "");
}

export function campaignNameOf(row) {
  return String(valueOf(row, "campaign_name", "campaignName", "name") || campaignIdOf(row) || "未命名活动");
}

export function campaignStateOf(row) {
  return String(valueOf(row, "state", "status", "serving_status", "servingStatus") || "unknown").toLowerCase();
}


export function campaignLifecycleOf(row) {
  const stage = String(valueOf(row, "listing_stage", "listingStage", "product_lifecycle") || "unknown").toLowerCase();
  return ["new", "established", "mixed", "unknown"].includes(stage) ? stage : "unknown";
}


export function campaignLifecycleLabel(row) {
  return ({ new: "新品", established: "老品", mixed: "混合", unknown: "未知" })[campaignLifecycleOf(row)];
}

export function campaignWindowMetrics(row, window = "14d") {
  const windows = row?.performance_windows && typeof row.performance_windows === "object" ? row.performance_windows : {};
  const selected = windows[window];
  if (selected && typeof selected === "object") return selected;
  if (window === "14d" && row?.mature_14d && typeof row.mature_14d === "object") return row.mature_14d;
  return {};
}

export function campaignSpendOf(row, window = "14d") {
  const metrics = campaignWindowMetrics(row, window);
  const value = valueOf(metrics, "spend", "costs", "cost") ?? valueOf(row, "spend", "costs", "cost", "mature_spend", "today_spend");
  return Number.isFinite(Number(value)) ? Number(value) : 0;
}

const CAMPAIGN_SORT_METRICS = new Set([
  "default_bid",
  "total_target_count",
  "advertised_product_count",
  "impressions",
  "clicks",
  "ctr",
  "spend",
  "cpc",
  "orders",
  "cvr",
  "sales",
  "acos",
  "roas",
]);

function finiteNumber(value) {
  if (missingValue(value) || !Number.isFinite(Number(value))) return null;
  return Number(value);
}

function derivedRatio(metrics, numeratorKey, denominatorKey) {
  const numerator = finiteNumber(valueOf(metrics, numeratorKey));
  const denominator = finiteNumber(valueOf(metrics, denominatorKey));
  return numerator == null || denominator == null || denominator === 0 ? null : numerator / denominator;
}

function percentagePoints(value) {
  const numeric = finiteNumber(value);
  if (numeric == null) return null;
  return Math.abs(numeric) <= 1 ? numeric * 100 : numeric;
}

export function skuControlMetrics({ analysis = {}, financial = {} } = {}) {
  const profit = finiteNumber(valueOf(financial, "profit", "profit_14d", "gross_profit"));
  const totalSales = finiteNumber(valueOf(financial, "salePrice", "sale_price", "sales", "total_sales"));
  const totalAdCost = finiteNumber(valueOf(financial, "adTotalCost", "ad_total_cost", "total_ad_cost"));
  const spSales = finiteNumber(valueOf(financial, "adSpSalePrice", "adTotalSalesSp", "sp_ad_sales"));
  const spCost = finiteNumber(valueOf(financial, "adSpCost", "adTotalCostSp", "sp_ad_cost"));
  const directBreakEven = percentagePoints(valueOf(financial, "break_even_acos", "breakEvenAcos"));
  const directSpAcos = finiteNumber(valueOf(analysis, "acosSp", "sp_acos", "spAcos"));
  const breakEvenAcosPct = directBreakEven ?? (
    profit != null && totalAdCost != null && totalSales != null && totalSales > 0
      ? ((profit + Math.abs(totalAdCost)) / totalSales) * 100
      : null
  );
  const skuSpAcosPct = directSpAcos ?? (
    spCost != null && spSales != null && spSales > 0
      ? (Math.abs(spCost) / spSales) * 100
      : null
  );
  const refundPercent = finiteNumber(valueOf(financial, "refundPercent"));
  return {
    breakEvenAcosPct,
    skuSpAcosPct,
    acosHeadroomPct: breakEvenAcosPct != null && skuSpAcosPct != null ? breakEvenAcosPct - skuSpAcosPct : null,
    availableDays: finiteNumber(valueOf(analysis, "availableDays", "available_days")),
    spSalesSharePct: spSales != null && totalSales != null && totalSales > 0 ? (spSales / totalSales) * 100 : null,
    refundRatePct: refundPercent ?? percentagePoints(valueOf(financial, "refund_rate", "refundRate")),
  };
}

export function campaignMetricValue(row, metric, window = "14d") {
  const metrics = campaignWindowMetrics(row, window);
  const direct = {
    default_bid: valueOf(row, "default_bid", "defaultBid", "default_bid_min", "defaultBidMin"),
    total_target_count: valueOf(row, "total_target_count", "totalTargetCount"),
    advertised_product_count: valueOf(row, "advertised_product_count", "advertisedProductCount"),
    impressions: valueOf(metrics, "impressions"),
    clicks: valueOf(metrics, "clicks"),
    ctr: valueOf(metrics, "ctr"),
    spend: valueOf(metrics, "spend", "costs", "cost"),
    cpc: valueOf(metrics, "cpc"),
    orders: valueOf(metrics, "orders", "purchases"),
    cvr: valueOf(metrics, "cvr", "conversion_rate", "conversionRate", "purchase_rate", "purchaseRate"),
    sales: valueOf(metrics, "sales"),
    acos: valueOf(metrics, "acos"),
    roas: valueOf(metrics, "roas"),
  };
  const value = finiteNumber(direct[metric]);
  if (value != null) return value;
  if (metric === "ctr") return derivedRatio(metrics, "clicks", "impressions");
  if (metric === "cpc") return derivedRatio(metrics, "spend", "clicks");
  if (metric === "cvr") return derivedRatio(metrics, "orders", "clicks");
  if (metric === "acos") return derivedRatio(metrics, "spend", "sales");
  if (metric === "roas") return derivedRatio(metrics, "sales", "spend");
  return null;
}


export function campaignPerformanceStatus(row) {
  const explicit = String(valueOf(row, "performance_status", "performanceStatus") || "").toLowerCase();
  if (["normal", "poor", "new_observation", "insufficient_sample", "unknown"].includes(explicit)) return explicit;
  const lifecycle = campaignLifecycleOf(row);
  if (["new", "mixed"].includes(lifecycle)) return "new_observation";
  if (lifecycle !== "established") return "unknown";
  const metrics = campaignWindowMetrics(row, "7d");
  const days = finiteNumber(valueOf(metrics, "data_days", "dataDays"));
  const clicks = finiteNumber(valueOf(metrics, "clicks"));
  const ctr = campaignMetricValue(row, "ctr", "7d");
  const cvr = campaignMetricValue(row, "cvr", "7d");
  if (days == null || days < 7 || clicks == null || clicks < 10 || ctr == null || cvr == null) return "insufficient_sample";
  return ctr >= 0.01 && cvr >= 0.1 ? "normal" : "poor";
}


export function campaignPerformanceLabel(row) {
  return ({
    normal: "表现好",
    poor: "表现差",
    new_observation: "新品观察",
    insufficient_sample: "样本不足",
    unknown: "表现未知",
  })[campaignPerformanceStatus(row)];
}


export function campaignBudgetStatus(row) {
  const explicit = String(valueOf(row, "budget_status", "budgetStatus") || "").toLowerCase();
  if (["full", "not_full"].includes(explicit)) return explicit;
  if (valueOf(row, "budget_full", "budgetFull") === true) return "full";
  const serving = String(valueOf(row, "serving_status", "servingStatus") || "").toUpperCase();
  if (serving.includes("OUT_OF_BUDGET")) return "full";
  if (valueOf(row, "latest_complete_budget_full", "latestCompleteBudgetFull") === true) return "full";
  const days = finiteNumber(valueOf(row, "budget_utilization_days_7d", "budgetUtilizationDays7d"));
  return days != null && days > 0 ? "full" : "not_full";
}


export function campaignBudgetMatrix(row) {
  const performance = campaignPerformanceStatus(row);
  const budget = campaignBudgetStatus(row);
  if (performance === "normal" && budget === "full") return { key: "normal_full", label: "表现好 · 已跑满", tone: "good", action: "盈利、库存通过后评估加预算" };
  if (performance === "normal") return { key: "normal_not_full", label: "表现好 · 未跑满", tone: "watch", action: "不加预算；检查竞价、广告位和关键词覆盖" };
  if (performance === "poor" && budget === "full") return { key: "poor_full", label: "表现差 · 已跑满", tone: "danger", action: "禁止加预算；优先清理低效投放" };
  if (performance === "poor") return { key: "poor_not_full", label: "表现差 · 未跑满", tone: "warning", action: "保持预算约束并继续优化" };
  if (performance === "new_observation") return { key: performance, label: "新品观察", tone: "new", action: "进入新品诊断和人工复核" };
  return { key: performance, label: campaignPerformanceLabel(row), tone: "neutral", action: "补齐成熟样本后再判断" };
}


export function campaignAdType(row) {
  const explicit = String(valueOf(row, "ad_type", "adType") || "").toLowerCase();
  if (explicit) return explicit;
  if (isAutomaticCampaign(row)) return "auto";
  const matchTypes = rowsOf(valueOf(row, "match_types", "matchTypes")).map((value) => String(value).toLowerCase());
  if (matchTypes.length === 1) return matchTypes[0];
  return matchTypes.length > 1 ? "manual_mixed" : "manual";
}


export function campaignAdTypeLabel(row) {
  return ({
    auto: "自动",
    exact: "精准",
    broad: "广泛",
    phrase: "词组",
    product_target: "商品投放",
    manual_mixed: "手动混合",
    manual: "手动",
  })[campaignAdType(row)] || "类型未知";
}

export function isAutomaticCampaign(row) {
  return String(valueOf(row, "targetingType", "targeting_type") || "").toLowerCase() === "auto";
}

export function searchTermSuggestion(row, campaign) {
  const value = searchTermValue(row);
  if (value.key === "waste") return "评估否定";
  if (value.key === "core" && isAutomaticCampaign(campaign)) return "优质词：新建精准 + 宽泛";
  if (value.key === "core") return "优质词：复核竞价";
  if (value.key === "potential") return "继续收集样本";
  if (value.key === "optimize" && isAutomaticCampaign(campaign)) return "转手动后小预算测试";
  if (value.key === "optimize") return "复核竞价与利润";
  if (value.key === "expensive" && isAutomaticCampaign(campaign)) return "检查相关性，暂不扩量";
  if (value.key === "expensive") return "复核竞价与相关性";
  return "继续观察";
}

export function campaignPriorityScore(row) {
  const primary = row?.primary_action && typeof row.primary_action === "object" ? row.primary_action : {};
  const priority = String(valueOf(primary, "priority", "priority_level") || valueOf(row, "priority", "priority_level", "risk_level") || "").toLowerCase();
  const action = String(valueOf(primary, "action_code", "actionCode", "action") || valueOf(row, "action_code", "actionCode", "action", "recommended_action", "recommendation_action") || "").toUpperCase();
  const blockers = rowsOf(row?.blockers || row?.blocking_reasons).length;
  if (["high", "p0", "p1", "高"].includes(priority)) return 400 + blockers;
  if (ACTIONABLE.has(action)) return 300 + blockers;
  if (["medium", "p2", "中"].includes(priority)) return 200 + blockers;
  if (blockers) return 100 + blockers;
  return 0;
}

export function sortCampaigns(campaigns, preferredId = DEFAULT_CAMPAIGN_ID, window = "14d") {
  return [...rowsOf(campaigns)].sort((left, right) => {
    const leftPreferred = campaignIdOf(left) === String(preferredId);
    const rightPreferred = campaignIdOf(right) === String(preferredId);
    if (leftPreferred !== rightPreferred) return Number(rightPreferred) - Number(leftPreferred);
    const priorityDifference = campaignPriorityScore(right) - campaignPriorityScore(left);
    if (priorityDifference) return priorityDifference;
    const spendDifference = campaignSpendOf(right, window) - campaignSpendOf(left, window);
    if (spendDifference) return spendDifference;
    return campaignNameOf(left).localeCompare(campaignNameOf(right), "zh-CN");
  });
}

export function sortCampaignsByMetric(campaigns, metric, direction = "desc", window = "14d") {
  if (!CAMPAIGN_SORT_METRICS.has(metric)) return sortCampaigns(campaigns, DEFAULT_CAMPAIGN_ID, window);
  const factor = direction === "asc" ? 1 : -1;
  return [...rowsOf(campaigns)].sort((left, right) => {
    const leftValue = campaignMetricValue(left, metric, window);
    const rightValue = campaignMetricValue(right, metric, window);
    if (leftValue == null || rightValue == null) {
      if (leftValue == null && rightValue == null) return campaignNameOf(left).localeCompare(campaignNameOf(right), "zh-CN");
      return leftValue == null ? 1 : -1;
    }
    const difference = (leftValue - rightValue) * factor;
    return difference || campaignNameOf(left).localeCompare(campaignNameOf(right), "zh-CN");
  });
}

export function filterCampaigns(campaigns, query = "", status = "all", adType = "all") {
  const needle = String(query).trim().toLowerCase();
  const requestedAdType = ["exact", "broad", "phrase", "auto"].includes(String(adType).toLowerCase())
    ? String(adType).toLowerCase()
    : "all";
  return rowsOf(campaigns).filter((campaign) => {
    const state = campaignStateOf(campaign);
    const priority = campaignPriorityScore(campaign);
    const matchesState = status === "all"
      || (status === "enabled" && ["enabled", "active", "running"].includes(state))
      || (status === "attention" && priority > 0);
    const adTypes = new Set([
      campaignAdType(campaign),
      ...rowsOf(valueOf(campaign, "match_types", "matchTypes")).map((value) => String(value).toLowerCase()),
    ]);
    const matchesAdType = requestedAdType === "all" || adTypes.has(requestedAdType);
    const products = [...rowsOf(campaign?.skus), ...rowsOf(campaign?.asins)].join(" ");
    const haystack = `${campaignNameOf(campaign)} ${campaignIdOf(campaign)} ${valueOf(campaign, "sku", "asin") || ""} ${products}`.toLowerCase();
    return matchesState && matchesAdType && (!needle || haystack.includes(needle));
  });
}

export function paginateCampaigns(campaigns, page, pageSize = CAMPAIGNS_PER_PAGE) {
  const safeSize = Math.max(1, Number(pageSize) || CAMPAIGNS_PER_PAGE);
  const pageCount = Math.max(1, Math.ceil(rowsOf(campaigns).length / safeSize));
  const currentPage = Math.min(Math.max(1, Number(page) || 1), pageCount);
  const start = (currentPage - 1) * safeSize;
  return {
    currentPage,
    pageCount,
    start,
    rows: rowsOf(campaigns).slice(start, start + safeSize),
  };
}

export function keywordPopoverPosition({
  anchorRect,
  boundaryRect,
  viewportWidth,
  viewportHeight,
  preferredWidth = 400,
  cardHeight = 292,
}) {
  const edge = 12;
  const gap = 10;
  const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));
  const boundaryLeft = Math.max(edge, boundaryRect?.left ?? edge);
  const boundaryRight = Math.min(viewportWidth - edge, boundaryRect?.right ?? viewportWidth - edge);
  const width = Math.min(preferredWidth, viewportWidth - edge * 2, boundaryRight - boundaryLeft);
  const padding = boundaryRight - boundaryLeft >= width + 16 ? 8 : 0;
  const viewportMaxLeft = Math.max(edge, viewportWidth - width - edge);
  const minLeft = clamp(boundaryLeft + padding, edge, viewportMaxLeft);
  const maxLeft = Math.max(minLeft, clamp(boundaryRight - width - padding, edge, viewportMaxLeft));
  const visibleLeft = Math.max(anchorRect.left, boundaryLeft);
  const visibleRight = Math.min(anchorRect.right, boundaryRight);
  const center = visibleRight >= visibleLeft ? (visibleLeft + visibleRight) / 2 : (boundaryLeft + boundaryRight) / 2;
  const left = clamp(center - width / 2, minLeft, maxLeft);
  const spaceBelow = viewportHeight - anchorRect.bottom - edge;
  const spaceAbove = anchorRect.top - edge;
  const rawTop = spaceBelow >= cardHeight || spaceBelow >= spaceAbove
    ? anchorRect.bottom + gap
    : anchorRect.top - cardHeight - gap;
  return {
    left,
    top: clamp(rawTop, edge, Math.max(edge, viewportHeight - cardHeight - edge)),
    width,
  };
}

export function normalizeDiagnosticPayload(payload) {
  const source = payload && typeof payload === "object" ? payload : {};
  const detail = source.detail && typeof source.detail === "object" ? source.detail : {};
  const catalog = source.catalog && typeof source.catalog === "object" ? source.catalog : {};
  const campaign = source.campaign || detail.campaign || null;
  let campaigns = rowsOf(source.campaigns || source.campaign_list || catalog.campaigns);
  if (!campaigns.length && campaign) campaigns = [campaign];
  const rawSources = source.sources || detail.sources;
  const sources = rowsOf(rawSources).length
    ? rowsOf(rawSources)
    : rawSources && typeof rawSources === "object"
      ? Object.entries(rawSources).map(([name, item]) => ({ name, ...(item && typeof item === "object" ? item : { status: item }) }))
      : [];
  return {
    raw: source,
    meta: source.meta || detail.meta || {},
    campaigns,
    campaign,
    structure: source.structure || detail.structure || {},
    listingContext: source.listing_context || detail.listing_context || {},
    performance: source.performance || detail.performance || {},
    decision: source.decision || detail.decision || {},
    adjustmentReviews: rowsOf(source.adjustment_reviews || detail.adjustment_reviews),
    dataQuality: source.data_quality || detail.data_quality || {},
    sources,
  };
}

export function mergeCampaignDetailMetrics(campaign, model) {
  const source = campaign && typeof campaign === "object" ? campaign : {};
  const detailCampaign = model?.campaign && typeof model.campaign === "object" ? model.campaign : {};
  const sourceId = campaignIdOf(source);
  const detailId = campaignIdOf(detailCampaign);
  if (!sourceId || !detailId || sourceId !== detailId) return source;

  const mature = model?.performance?.mature_14d || model?.performance?.mature || {};
  const reportSummary = mature?.deep_reports?.campaigns?.summary
    || mature?.deepReports?.campaigns?.summary
    || mature?.preferred_campaign_summary
    || mature?.preferredCampaignSummary
    || {};
  const existingMature = campaignWindowMetrics(source, "14d");
  const matureMetrics = reportSummary && typeof reportSummary === "object"
    ? { ...reportSummary, ...existingMature }
    : existingMature;
  const hasMatureMetrics = Object.keys(matureMetrics).length > 0;
  const performanceWindows = source.performance_windows && typeof source.performance_windows === "object"
    ? { ...source.performance_windows }
    : {};
  if (hasMatureMetrics) performanceWindows["14d"] = matureMetrics;

  return {
    ...detailCampaign,
    ...source,
    ...(hasMatureMetrics ? {
      performance_windows: performanceWindows,
      mature_14d: { ...reportSummary, ...(source.mature_14d || {}) },
    } : {}),
  };
}

function isRecord(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function mergePreferredFields(preferred, fallback) {
  if (!isRecord(preferred)) return isRecord(fallback) ? { ...fallback } : preferred ?? fallback;
  if (!isRecord(fallback)) return { ...preferred };
  const merged = { ...fallback };
  Object.entries(preferred).forEach(([key, value]) => {
    merged[key] = isRecord(value) && isRecord(fallback[key])
      ? mergePreferredFields(value, fallback[key])
      : value;
  });
  return merged;
}

function mergedValues(left, right) {
  const seen = new Set();
  return [...rowsOf(left), ...rowsOf(right)].filter((item) => {
    const key = typeof item === "object" ? JSON.stringify(item) : String(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function qualityRank(status) {
  const key = String(status || "").toLowerCase();
  if (["error", "failed", "unavailable", "critical"].includes(key)) return 3;
  if (["partial", "degraded", "warning"].includes(key)) return 2;
  if (["complete", "ok", "healthy", "passed"].includes(key)) return 0;
  return 1;
}

export function mergeDiagnosticDataQuality(current, full) {
  const merged = mergePreferredFields(current || {}, full || {});
  for (const key of ["issues", "source_errors", "partial_sources"]) {
    const values = mergedValues(full?.[key], current?.[key]);
    if (values.length || key in (full || {}) || key in (current || {})) merged[key] = values;
  }
  const currentStatus = valueOf(current, "status");
  const fullStatus = valueOf(full, "status");
  merged.status = qualityRank(fullStatus) > qualityRank(currentStatus)
    ? fullStatus
    : currentStatus || fullStatus;
  return merged;
}

export function mergeDiagnosticModels(current, full) {
  if (!current || campaignIdOf(current.campaign) !== campaignIdOf(full?.campaign)) return current || full;
  const currentPerformance = current.performance || {};
  const fullPerformance = full.performance || {};
  const currentMature = currentPerformance.mature_14d || {};
  const fullMature = fullPerformance.mature_14d || {};
  return {
    ...full,
    meta: current.meta,
    campaign: current.campaign,
    decision: current.decision,
    adjustmentReviews: current.adjustmentReviews?.length ? current.adjustmentReviews : full.adjustmentReviews,
    dataQuality: mergeDiagnosticDataQuality(current.dataQuality, full.dataQuality),
    performance: {
      ...fullPerformance,
      ...currentPerformance,
      today: mergePreferredFields(currentPerformance.today || {}, fullPerformance.today || {}),
      mature_14d: {
        ...fullMature,
        ...currentMature,
        deep_reports: {
          ...(fullMature.deep_reports || {}),
          ...(currentMature.deep_reports || {}),
        },
      },
    },
  };
}

export function searchTermDataRevision({ campaignId, kind, refreshToken = 0, report, sources, meta } = {}) {
  const source = rowsOf(sources).find((row) => String(valueOf(row, "source_id", "name") || "").toLowerCase().includes("search_term")) || {};
  return JSON.stringify({
    campaignId: String(campaignId || ""),
    kind: String(kind || ""),
    refreshToken,
    effectiveDate: valueOf(report, "effective_date", "effectiveDate") || valueOf(source, "effective_date", "effectiveDate") || "",
    sourceStart: valueOf(report, "source_start_date", "sourceStartDate") || valueOf(source, "source_start_date", "sourceStartDate") || "",
    sourceEnd: valueOf(report, "source_end_date", "sourceEndDate") || valueOf(source, "source_end_date", "sourceEndDate") || "",
    indexVersion: valueOf(report, "index_version", "indexVersion", "generated_at", "generatedAt")
      || valueOf(source, "index_version", "indexVersion", "file_generated_at", "fetched_at", "generated_at")
      || valueOf(meta, "search_term_index_version", "searchTermIndexVersion")
      || "",
  });
}

function productKey(row, index = 0) {
  const adId = valueOf(row, "ad_id", "adId");
  if (adId) return `ad:${adId}`;
  const sku = valueOf(row, "sku", "msku", "seller_sku", "sellerSku") || "";
  const asin = valueOf(row, "asin", "child_asin", "childAsin") || "";
  return `${sku}::${asin}::${index}`;
}

export function focusProducts(model) {
  const structure = model?.structure || {};
  const listing = model?.listingContext || {};
  const ads = rowsOf(structure.ad_products || structure.advertised_products || structure.products);
  let listings = rowsOf(listing.products || listing.items || listing.listings || listing);
  if (!listings.length && valueOf(listing, "sku", "msku", "asin")) listings = [listing];
  const listingIndex = new Map();
  listings.forEach((row) => {
    const exact = `${valueOf(row, "sku", "msku", "seller_sku", "sellerSku") || ""}::${String(valueOf(row, "asin") || "").toUpperCase()}`;
    if (exact !== "::" && !listingIndex.has(exact)) listingIndex.set(exact, row);
  });
  const source = ads.length ? ads : listings;
  return source.map((row, index) => {
    const exact = `${valueOf(row, "sku", "msku", "seller_sku", "sellerSku") || ""}::${String(valueOf(row, "asin") || "").toUpperCase()}`;
    return { ...listingIndex.get(exact), ...row, _key: productKey(row, index) };
  });
}

export function expandIdentity(row) {
  if (!row || typeof row !== "object" || Array.isArray(row)) return row;
  const identity = row.identity;
  return identity && typeof identity === "object" && !Array.isArray(identity)
    ? { ...identity, ...row }
    : row;
}

export function deepReportRows(report, preferredKeys = []) {
  if (Array.isArray(report)) return report.map(expandIdentity);
  if (!report || typeof report !== "object") return [];
  for (const key of [...preferredKeys, "top", "top_rows", "topRows", "rows"]) {
    if (Array.isArray(report[key])) return report[key].map(expandIdentity);
  }
  return rowsOf(report).map(expandIdentity);
}

export function campaignBiddingStrategy(row) {
  const strategy = String(valueOf(row, "strategy", "bidding_strategy", "biddingStrategy") || "");
  return ({
    manual: "固定竞价",
    legacyforsales: "动态竞价（只降低）",
    autoforsales: "动态竞价（提高和降低）",
  })[strategy.toLowerCase()] || strategy || null;
}

function placementPredicate(name) {
  const placement = String(name || "");
  if (placement.includes("顶部")) return "placementTop";
  if (placement.includes("其余")) return "placementRestOfSearch";
  if (placement.includes("商品") || placement.includes("产品页面")) return "placementProductPage";
  return "";
}

function campaignAdjustments(row) {
  const raw = valueOf(row, "adjustments", "placement_adjustments", "placementAdjustments");
  if (Array.isArray(raw)) return raw;
  if (typeof raw !== "string" || !raw.trim()) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function campaignPlacementAdjustmentLabel(row) {
  const labels = {
    placementTop: "搜索顶部",
    placementRestOfSearch: "其余搜索位",
    placementProductPage: "商品页",
  };
  const parts = campaignAdjustments(row).map((item) => {
    const predicate = String(valueOf(item, "predicate") || "");
    const percentage = finiteNumber(valueOf(item, "percentage", "adjustment", "value"));
    return labels[predicate] && percentage != null ? `${labels[predicate]} +${percentage}%` : "";
  }).filter(Boolean);
  return parts.join(" · ") || null;
}

export function placementPerformanceRows(report, campaign) {
  const strategy = campaignBiddingStrategy(campaign);
  const adjustments = campaignAdjustments(campaign);
  const records = deepReportRows(report)
    .filter((row) => {
      const name = String(valueOf(row, "placement", "placement_name", "name", "广告位") || "");
      return name && !name.toLowerCase().includes("off amazon") && !name.includes("企业购");
    })
    .map((row) => {
      const name = valueOf(row, "placement", "placement_name", "name", "广告位");
      const predicate = placementPredicate(name);
      const adjustment = adjustments.find((item) => String(valueOf(item, "predicate") || "") === predicate);
      const numberOf = (...keys) => Number(valueOf(row, ...keys) || 0);
      const impressions = numberOf("impressions");
      const clicks = numberOf("clicks");
      const spend = numberOf("spend", "costs", "cost");
      const orders = numberOf("orders", "order_count", "purchases");
      const sales = numberOf("sales", "attributed_sales");
      return {
        ...row,
        impressions,
        clicks,
        spend,
        orders,
        sales,
        ctr: impressions ? clicks / impressions : null,
        cpc: clicks ? spend / clicks : null,
        cvr: clicks ? orders / clicks : null,
        acos: sales ? spend / sales : null,
        bidding_strategy: strategy,
        bid_adjustment: Number(valueOf(adjustment, "percentage") || 0),
      };
    });
  const totalSpend = records.reduce((total, row) => total + row.spend, 0);
  const totalOrders = records.reduce((total, row) => total + row.orders, 0);
  const totalSales = records.reduce((total, row) => total + row.sales, 0);
  const overallAcos = totalSales ? totalSpend / totalSales : null;
  return records.map((row) => ({
    ...row,
    spend_share: totalSpend ? row.spend / totalSpend : null,
    order_share: totalOrders ? row.orders / totalOrders : null,
    acos_delta: row.acos == null || overallAcos == null ? null : row.acos - overallAcos,
    sample_confidence: row.clicks >= 30 || row.orders >= 5 ? "较充分" : row.clicks >= 10 || row.orders >= 2 ? "初步" : "偏少",
  }));
}

export function placementPerformanceSummary(rows) {
  const records = rowsOf(rows);
  if (!records.length) return null;
  const sum = (...keys) => records.reduce((total, row) => total + Number(valueOf(row, ...keys) || 0), 0);
  const money = (value) => Math.round((value + Number.EPSILON) * 100) / 100;
  const impressions = sum("impressions");
  const clicks = sum("clicks");
  const spend = money(sum("spend", "costs", "cost"));
  const orders = sum("orders", "order_count", "purchases");
  const sales = money(sum("sales", "attributed_sales"));
  return {
    placement: `总计：${records.length}`,
    bidding_strategy: "—",
    bid_adjustment: "—",
    impressions,
    clicks,
    ctr: impressions ? clicks / impressions : null,
    spend,
    cpc: clicks ? spend / clicks : null,
    orders,
    sales,
    acos: sales ? spend / sales : null,
    spend_share: spend ? 1 : null,
    order_share: orders ? 1 : null,
    cvr: clicks ? orders / clicks : null,
    acos_delta: sales ? 0 : null,
    sample_confidence: "汇总",
  };
}

function summarizeSearchRows(rows) {
  const records = rowsOf(rows);
  const numberOf = (row, ...keys) => Number(valueOf(row, ...keys) || 0);
  const totals = records.reduce((result, row) => ({
    spend: result.spend + numberOf(row, "spend", "costs", "cost", "广告花费"),
    sales: result.sales + numberOf(row, "sales", "revenue", "广告销售额"),
    orders: result.orders + numberOf(row, "orders", "order_count", "purchases", "广告订单量"),
  }), { spend: 0, sales: 0, orders: 0 });
  const maxClicksRow = records.reduce((best, row) => (
    numberOf(row, "clicks", "click_count", "广告点击量") > numberOf(best, "clicks", "click_count", "广告点击量") ? row : best
  ), {});
  return {
    ...totals,
    effective_sample_count: records.filter((row) => numberOf(row, "clicks", "click_count", "广告点击量") >= 10).length,
    attention_count: records.filter((row) => numberOf(row, "orders", "order_count", "purchases", "广告订单量") >= 2 || numberOf(row, "clicks", "click_count", "广告点击量") >= 10).length,
    sample_insufficient_count: records.filter((row) => numberOf(row, "clicks", "click_count", "广告点击量") < 10).length,
    max_clicks_term: maxClicksRow,
  };
}

export function searchTermStructureSummary(report, matureOrders = null) {
  const source = report && typeof report === "object" ? report : {};
  const conversionRows = deepReportHighlightRows(source, "conversion");
  const wasteRows = deepReportHighlightRows(source, "waste");
  const conversion = { ...summarizeSearchRows(conversionRows), ...(source.conversion_summary || source.conversionSummary || {}) };
  const waste = { ...summarizeSearchRows(wasteRows), ...(source.waste_summary || source.wasteSummary || {}) };
  const overall = source.summary && typeof source.summary === "object" ? source.summary : {};
  const totalOrders = Number(matureOrders ?? valueOf(overall, "orders", "order_count") ?? 0);
  const totalSpend = Number(valueOf(overall, "spend", "costs", "cost") || 0);
  const maxClicksRow = expandIdentity(waste.max_clicks_term);
  const maxClicks = Number(valueOf(maxClicksRow, "clicks", "click_count", "广告点击量") || 0);
  const maxClicksTerm = valueOf(maxClicksRow, "search_term", "searchTerm", "query", "用户搜索词", "targeting", "投放") || null;
  const available = String(valueOf(source, "status") || "").toLowerCase() === "available" || conversionRows.length > 0 || wasteRows.length > 0;
  return {
    available,
    conversion: {
      terms: Number(valueOf(source, "conversion_count", "conversionCount") || conversionRows.length),
      orders: Number(valueOf(conversion, "orders", "order_count") || 0),
      sales: Number(valueOf(conversion, "sales", "revenue") || 0),
      orderShare: totalOrders ? Number(valueOf(conversion, "orders", "order_count") || 0) / totalOrders : null,
    },
    waste: {
      terms: Number(valueOf(source, "waste_count", "wasteCount") || wasteRows.length),
      spend: Number(valueOf(waste, "spend", "costs", "cost") || 0),
      spendShare: totalSpend ? Number(valueOf(waste, "spend", "costs", "cost") || 0) / totalSpend : null,
      maxClicks,
      maxClicksTerm,
    },
    sample: {
      effective: Number(valueOf(conversion, "effective_sample_count") || 0) + Number(valueOf(waste, "effective_sample_count") || 0),
      attention: Number(valueOf(conversion, "attention_count") || 0) + Number(valueOf(waste, "attention_count") || 0),
      insufficient: Number(valueOf(conversion, "sample_insufficient_count") || 0) + Number(valueOf(waste, "sample_insufficient_count") || 0),
    },
  };
}

export function deepReportHighlightRows(report, kind) {
  const keys = kind === "conversion"
    ? ["top_converting", "top_conversion", "conversion_rows", "converting"]
    : ["top_waste", "waste_rows", "waste"];
  if (!report || typeof report !== "object") return [];
  for (const key of keys) {
    if (Array.isArray(report[key])) return report[key].map(expandIdentity);
  }
  return [];
}

export function searchTermRecommendation(row, options = {}) {
  const explicit = String(valueOf(row, "recommendation", "action_code", "actionCode", "suggestion") || "").toUpperCase();
  if (explicit.includes("NEGATIVE") || explicit.includes("否定")) return "negative";
  if (explicit.includes("BID") || explicit.includes("CPC") || explicit.includes("竞价")) return "adjust-cpc";

  const numberOf = (...keys) => {
    const value = valueOf(row, ...keys);
    return missingValue(value) || !Number.isFinite(Number(value)) ? null : Number(value);
  };
  const orders = numberOf("orders", "order_count", "purchases", "广告订单量") || 0;
  const clicks = numberOf("clicks", "click_count", "广告点击量") || 0;
  const spend = numberOf("spend", "costs", "cost", "广告花费") || 0;
  const sales = numberOf("sales", "revenue", "广告销售额") || 0;
  const rawAcos = numberOf("acos", "ACoS");
  const acos = rawAcos == null ? (sales > 0 ? spend / sales : null) : rawAcos;
  const targetAcos = Number(options.targetAcos ?? 0.3);
  const minPositiveOrders = Number(options.minPositiveOrders ?? 2);
  const minNegativeClicks = Number(options.minNegativeClicks ?? 10);

  if (orders === 0 && clicks >= minNegativeClicks) return "negative";
  if (orders >= minPositiveOrders && acos != null && acos <= targetAcos) return "adjust-cpc";
  return null;
}

export function searchTermValue(row, options = {}) {
  const numberOf = (...keys) => {
    const value = valueOf(row, ...keys);
    return missingValue(value) || !Number.isFinite(Number(value)) ? null : Number(value);
  };
  const orders = numberOf("orders", "order_count", "purchases", "广告订单量") || 0;
  const clicks = numberOf("clicks", "click_count", "广告点击量") || 0;
  const spend = numberOf("spend", "costs", "cost", "广告花费") || 0;
  const sales = numberOf("sales", "revenue", "广告销售额") || 0;
  const rawAcos = numberOf("acos", "ACoS");
  const acos = rawAcos == null ? (sales > 0 ? spend / sales : null) : rawAcos;
  const targetAcos = Number(options.targetAcos ?? 0.3);
  const minCoreOrders = Number(options.minCoreOrders ?? 2);
  const minCoreClicks = Number(options.minCoreClicks ?? 8);
  const minWasteClicks = Number(options.minWasteClicks ?? 10);
  const sample = clicks >= 10 ? "样本较足" : clicks >= 5 ? "初步样本" : "样本偏少";

  if (orders === 0 && clicks >= minWasteClicks) return { key: "waste", label: "止损候选", tone: "negative", sample };
  if (orders === 0) return { key: "watch", label: "继续观察", tone: "neutral", sample };
  if (clicks < minCoreClicks || orders < minCoreOrders) return { key: "potential", label: "潜力待验证", tone: "potential", sample };
  if (orders >= minCoreOrders && acos != null && acos <= targetAcos) return { key: "core", label: "核心词", tone: "core", sample };
  if (acos != null && acos <= targetAcos * 1.5) return { key: "optimize", label: "有效待优化", tone: "potential", sample };
  return { key: "expensive", label: "转化偏贵", tone: "warning", sample };
}

export function currentHourCampaign(performance) {
  const source = performance && typeof performance === "object" ? performance : {};
  const layer = source.today || source.current_hour || source.hourly || {};
  const campaign = layer.campaign && typeof layer.campaign === "object" ? layer.campaign : {};
  const summary = campaign.summary && typeof campaign.summary === "object"
    ? campaign.summary
    : campaign.metrics && typeof campaign.metrics === "object"
      ? campaign.metrics
      : campaign;
  return {
    layer,
    summary,
    latestHour: valueOf(summary, "latest_hour", "latestHour") ?? valueOf(campaign, "latest_hour", "latestHour") ?? valueOf(layer, "latest_hour", "latestHour", "hour"),
  };
}

export function sourceLayerLabel(row) {
  const cache = String(valueOf(row, "cache_status") || "");
  if (["persistent_snapshot", "stale_snapshot"].includes(cache)) return "定时本地快照";
  if (row?.provisional === true) return "当前小时暂定";
  if (row?.realtime === false) {
    const sourceId = String(valueOf(row, "source_id", "name") || "");
    return sourceId.startsWith("deep_") || cache === "file_cache" ? "D-2 本地 XLSX 快照" : "D-2 本地成熟快照";
  }
  if (row?.realtime === true) return "实时 API";
  return "本次请求读取";
}

function decisionRows(value, defaults = {}) {
  const rows = rowsOf(value);
  if (rows.length) return rows.map((row) => typeof row === "object" ? { ...defaults, ...row } : { ...defaults, message: row });
  if (!value) return [];
  if (typeof value !== "object") return [{ ...defaults, message: value }];
  const looksLikeRow = ["code", "label", "title", "message", "reason", "status", "value"].some((key) => value[key] !== undefined);
  if (looksLikeRow) return [{ ...defaults, ...value }];
  return Object.entries(value).map(([code, row]) => typeof row === "object" ? { ...defaults, code, ...row } : { ...defaults, code, message: row });
}

export function normalizeDecision(decision) {
  const source = decision && typeof decision === "object" ? decision : {};
  const primaryAction = source.primary_action && typeof source.primary_action === "object" ? source.primary_action : {};
  const rawAction = valueOf(primaryAction, "action_code", "actionCode", "action") || valueOf(source, "action_code", "actionCode", "action", "recommended_action", "recommendation");
  const action = rawAction ? String(rawAction).toUpperCase() : null;
  const matureEvidence = source.mature_evidence;
  const evidence = decisionRows(matureEvidence?.actions || matureEvidence || source.evidence_chain || source.evidence || source.signals, {
    freshness: "mature_14d",
    source_end_date: matureEvidence?.source_end_date,
    generated_at: matureEvidence?.generated_at,
  });
  const todayConfirmation = decisionRows(source.today_confirmation, { freshness: "current_hour" });
  const conflicts = decisionRows(source.conflicts || source.conflict_signals);
  const protections = decisionRows(source.protections || source.guardrails);
  const blockers = decisionRows(source.blockers || source.blocking_reasons || source.blocked_by);
  protections.forEach((item) => {
    const status = String(valueOf(item, "status", "result") || "").toLowerCase();
    if (item.blocking === true || ["block", "blocked", "failed", "missing", "unknown"].includes(status)) blockers.push(item);
  });
  const budgetPassed = source.budget_guardrail_passed === true || source.budget_validation === "passed";
  if (action === "INCREASE_BUDGET" && !budgetPassed) {
    blockers.push({
      code: "BUDGET_GUARDRAIL",
      message: "预算不足不等于应直接加预算；利润、库存、转化和整店预算尚未全部通过。",
      grain: "campaign",
    });
  }
  if (!evidence.length) {
    blockers.push({ code: "EVIDENCE_MISSING", message: "API 未返回完整决策证据链，不能形成可执行结论。", grain: "campaign" });
  }
  if (!action) {
    blockers.push({ code: "ACTION_MISSING", message: "API 未返回 primary_action.action_code，前端不会猜测调控动作。", grain: "campaign" });
  }
  const rawGate = String(valueOf(source, "gate", "execution_gate") || "REVIEW").toUpperCase();
  if (rawGate === "BLOCK" && !blockers.length) {
    blockers.push({ code: "EXECUTION_GATE", message: "后端决策门禁为 BLOCK；在解除前仅允许观察。", grain: "campaign" });
  }
  return {
    ...source,
    action,
    primaryAction,
    priority: valueOf(primaryAction, "priority", "priority_level") || valueOf(source, "priority", "priority_level"),
    evidence,
    todayConfirmation,
    conflicts,
    protections,
    blockers,
    gate: blockers.length ? "BLOCK" : rawGate,
    confidence: valueOf(source, "confidence", "confidence_score", "score"),
  };
}

export function grainLabel(value) {
  const key = String(value || "unknown").toLowerCase();
  return ({
    campaign: "活动级",
    ad_group: "广告组级",
    adgroup: "广告组级",
    ad_product: "广告商品级",
    advertised_product: "广告商品级",
    sku: "SKU全业务级",
    listing: "SKU全业务级",
    target: "投放级",
    keyword: "投放级",
    product_target: "投放级",
    placement: "广告位级",
  })[key] || "粒度未知";
}

export function freshnessLabel(value) {
  const key = String(value || "unknown").toLowerCase();
  if (["today", "hour", "hourly", "current_hour", "provisional"].includes(key)) return "当前小时·暂定";
  if (["mature", "mature_14d", "d-2", "d2"].includes(key)) return "D-2成熟";
  if (["live", "configuration", "config"].includes(key)) return "定时快照·配置";
  return "时间层未知";
}

export function missingValue(value) {
  return value === undefined || value === null || value === "";
}

export function acosState(row, explicitValue = valueOf(row, "acos", "ACoS")) {
  if (!missingValue(explicitValue) && Number.isFinite(Number(explicitValue))) return "available";
  const spend = valueOf(row, "spend", "costs", "cost", "广告花费");
  const sales = valueOf(row, "sales", "revenue", "广告销售额");
  if (missingValue(spend) || missingValue(sales) || !Number.isFinite(Number(spend)) || !Number.isFinite(Number(sales)) || Number(sales) !== 0) return "missing";
  return Number(spend) > 0 ? "no_sales" : "no_activity";
}
