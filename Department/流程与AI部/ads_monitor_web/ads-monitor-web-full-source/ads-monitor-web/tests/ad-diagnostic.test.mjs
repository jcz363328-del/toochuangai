import assert from "node:assert/strict";
import test from "node:test";
import { buildDiagnosticShopsUrl, buildDiagnosticUrl, buildSearchTermsUrl, buildSpControlCapabilitiesUrl } from "../src/adDiagnosticApi.js";
import {
  CAMPAIGNS_PER_PAGE,
  DEFAULT_CAMPAIGN_ID,
  acosState,
  buildPublishedCampaignFallbackModel,
  campaignIdOf,
  campaignAdTypeLabel,
  campaignBudgetMatrix,
  campaignLifecycleLabel,
  campaignMetricValue,
  campaignPerformanceGrade,
  campaignPerformanceStatus,
  campaignSpendOf,
  campaignWindowMetrics,
  currentHourCampaign,
  deepReportHighlightRows,
  deepReportRows,
  expandIdentity,
  filterCampaigns,
  focusProducts,
  grainLabel,
  hourlyMetricDisplay,
  isAutomaticCampaign,
  keywordPopoverPosition,
  missingValue,
  mergeDiagnosticDataQuality,
  mergeDiagnosticModels,
  mergeCampaignDetailMetrics,
  mergePublishedCampaignMetrics,
  normalizeDecision,
  normalizeDiagnosticPayload,
  normalizeDiagnosticShops,
  paginateCampaigns,
  placementPerformanceRows,
  placementPerformanceSummary,
  searchTermRecommendation,
  searchTermDataRevision,
  searchTermStructureSummary,
  searchTermSuggestion,
  searchTermValue,
  skuControlMetrics,
  sourceLayerLabel,
  sortCampaigns,
  sortCampaignsByMetric,
} from "../src/adDiagnosticModel.js";

const campaign = (id, overrides = {}) => ({
  campaign_id: String(id),
  campaign_name: `Campaign ${id}`,
  state: "enabled",
  spend: Number(id),
  ...overrides,
});

test("hydrates every catalog campaign from the published mature snapshot", () => {
  const catalogCampaign = campaign("23", {
    shop_id: "476221",
    budget: 1,
    listing_stage: "unknown",
    performance_status: "unknown",
    mature_14d: {},
    performance_windows: {},
  });
  const publishedCampaign = {
    shop_id: "476221",
    campaign_id: "23",
    listing_stage: "established",
    performance_status: "normal",
    budget: 71,
    spend: 140,
    sales: 400,
    clicks: 140,
    impressions: 7000,
    orders: 21,
    ctr: 0.02,
    cvr: 0.16,
    data_days: 14,
    latest_date: "2026-09-01",
    performance_7d: {
      spend: 70,
      sales: 200,
      clicks: 70,
      impressions: 3500,
      orders: 11,
      ctr: 0.02,
      cvr: 0.157,
      data_days: 7,
    },
  };
  const dailyTrend = Array.from({ length: 14 }, (_, index) => ({
    campaign_id: "23",
    date: `2026-08-${String(index + 19).padStart(2, "0")}`,
    spend: 10,
  }));
  const merged = mergePublishedCampaignMetrics(catalogCampaign, publishedCampaign, dailyTrend);

  assert.equal(campaignWindowMetrics(merged, "14d").spend, 140);
  assert.equal(campaignWindowMetrics(merged, "14d").daily_trend.length, 14);
  assert.equal(campaignWindowMetrics(merged, "7d").data_days, 7);
  assert.equal(merged.listing_stage, "established");
  assert.equal(merged.performance_status, "normal");
  assert.equal(merged.budget, 71);
  assert.equal(campaignPerformanceGrade(merged, "14d").key, "excellent");
});

test("builds a matching published fallback detail when live campaign detail is unavailable", () => {
  const published = mergePublishedCampaignMetrics(
    campaign("344188052942742", { shop_id: "476221" }),
    {
      shop_id: "476221",
      campaign_id: "344188052942742",
      spend: 6568.48,
      sales: 1739.56,
      clicks: 816,
      impressions: 28535,
      orders: 121,
      ctr: 0.029,
      cvr: 0.148,
      data_days: 14,
    },
    [{ campaign_id: "344188052942742", date: "2026-09-01", spend: 50 }],
  );
  const fallback = buildPublishedCampaignFallbackModel(published);

  assert.equal(campaignIdOf(fallback.campaign), "344188052942742");
  assert.equal(fallback.meta.detail_status, "summary_only");
  assert.equal(fallback.performance.mature_14d.campaign.spend, 6568.48);
  assert.equal(fallback.performance.mature_14d.daily_trend.length, 1);
  assert.deepEqual(fallback.structure, {});
});

test("builds diagnostic and SP-control URLs scoped to the selected shop", () => {
  assert.equal(buildDiagnosticShopsUrl(), "/api/diagnostic/shops");
  assert.equal(
    buildDiagnosticUrl({ campaignId: "70540977760495", refresh: true, section: "overview" }),
    "/api/diagnostic?shop_id=475394&campaign_id=70540977760495&refresh=1&section=overview",
  );
  assert.equal(
    buildSearchTermsUrl({ campaignId: "7", kind: "conversion", page: 2, pageSize: 10 }),
    "/api/diagnostic/search-terms?shop_id=475394&campaign_id=7&kind=conversion&page=2&page_size=10",
  );
  assert.equal(
    buildSpControlCapabilitiesUrl({ campaignId: "7", refresh: true }),
    "/api/diagnostic/sp-controls/capabilities?shop_id=475394&campaign_id=7&refresh=1",
  );
  assert.equal(
    buildDiagnosticUrl({ shopId: "476221", campaignId: "8" }),
    "/api/diagnostic?shop_id=476221&campaign_id=8",
  );
  assert.equal(
    buildSpControlCapabilitiesUrl({ shopId: "476221", campaignId: "8" }),
    "/api/diagnostic/sp-controls/capabilities?shop_id=476221&campaign_id=8",
  );
});

test("normalizes every diagnostic shop returned by the backend", () => {
  assert.deepEqual(
    normalizeDiagnosticShops({
      shops: [
        { id: 475394, name: "21号站-李娜-US", currency: "usd", marketplace_id: "ATVPDKIKX0DER", timezone: "America/Los_Angeles" },
        { id: 476221, name: "23号店-侯梁-US", currency: "usd" },
        { shop_id: "999", shop_name: "新店-DE", currency: "eur" },
        { id: "999", name: "重复店铺" },
        null,
      ],
    }),
    [
      { id: "475394", name: "21号站-李娜-US", currency: "USD", marketplaceId: "ATVPDKIKX0DER", timezone: "America/Los_Angeles", defaultCampaignId: "70540977760495" },
      { id: "476221", name: "23号店-侯梁-US", currency: "USD", marketplaceId: "", timezone: "", defaultCampaignId: "390041487563225" },
      { id: "999", name: "新店-DE", currency: "EUR", marketplaceId: "", timezone: "", defaultCampaignId: "" },
    ],
  );
});

test("puts the preferred campaign first, then actionable and high-spend campaigns", () => {
  const rows = sortCampaigns([
    campaign("1", { spend: 999 }),
    campaign("2", { spend: 5, priority: "high" }),
    campaign(DEFAULT_CAMPAIGN_ID, { spend: 0 }),
  ]);
  assert.deepEqual(rows.map(campaignIdOf), [DEFAULT_CAMPAIGN_ID, "2", "1"]);
});

test("puts enabled campaigns ahead of archived campaigns when no preferred campaign matches", () => {
  const rows = sortCampaigns([
    campaign("1", { state: "archived", spend: 999, campaign_name: "Archived" }),
    campaign("2", { state: "enabled", spend: 1, campaign_name: "Enabled" }),
  ], "missing");
  assert.deepEqual(rows.map(campaignIdOf), ["2", "1"]);
});

test("selects campaign performance by mature window without fabricating missing windows", () => {
  const row = campaign("7", {
    performance_windows: {
      "7d": { spend: 70, clicks: 100 },
      "14d": { spend: 140, clicks: 200 },
    },
  });
  assert.equal(campaignWindowMetrics(row, "7d").clicks, 100);
  assert.equal(campaignSpendOf(row, "14d"), 140);
  assert.deepEqual(campaignWindowMetrics(row, "30d"), {});
});

test("hydrates the selected campaign card from its downloaded report summary", () => {
  const catalogCampaign = campaign("7", {
    budget: 50,
    performance_windows: {},
    mature_14d: {},
  });
  const model = {
    campaign: { campaign_id: "7", campaign_name: "Detailed campaign" },
    performance: {
      mature_14d: {
        preferred_campaign_summary: {
          spend: 140,
          clicks: 200,
          impressions: 10000,
          orders: 20,
          sales: 400,
          data_days: 14,
        },
      },
    },
  };

  const hydrated = mergeCampaignDetailMetrics(catalogCampaign, model);

  assert.equal(hydrated.budget, 50);
  assert.equal(campaignWindowMetrics(hydrated, "14d").spend, 140);
  assert.equal(campaignMetricValue(hydrated, "acos", "14d"), 0.35);
  assert.equal(campaignWindowMetrics(hydrated, "14d").data_days, 14);
});

test("restores selected campaign performance from resolved listing context", () => {
  const catalogCampaign = campaign("7", {
    listing_stage: "unknown",
    performance_status: "unknown",
    performance_windows: {
      "7d": { data_days: 7, impressions: 1000, clicks: 20, orders: 3, ctr: 0.02, cvr: 0.15 },
    },
  });
  const model = {
    campaign: { campaign_id: "7", campaign_name: "Detailed campaign" },
    listingContext: [
      { campaign_id: "7", sku: "sku-1", listing_stage: "established" },
      { campaign_id: "7", sku: "sku-2", listing_stage: "established" },
    ],
  };

  const hydrated = mergeCampaignDetailMetrics(catalogCampaign, model);

  assert.equal(hydrated.listing_stage, "established");
  assert.equal(hydrated.performance_status, "normal");
  assert.equal(campaignLifecycleLabel(hydrated), "老品");
  assert.equal(campaignPerformanceStatus(hydrated), "normal");
});

test("keeps campaign performance unknown when any listing remains unresolved", () => {
  const hydrated = mergeCampaignDetailMetrics(
    campaign("7", {
      listing_stage: "unknown",
      performance_status: "unknown",
      performance_windows: {
        "7d": { data_days: 7, impressions: 1000, clicks: 20, orders: 3, ctr: 0.02, cvr: 0.15 },
      },
    }),
    {
      campaign: { campaign_id: "7" },
      listingContext: [
        { campaign_id: "7", listing_stage: "established" },
        { campaign_id: "7", listing_stage: "unknown" },
      ],
    },
  );

  assert.equal(hydrated.listing_stage, "unknown");
  assert.equal(hydrated.performance_status, "unknown");
});

test("classifies established campaign performance and the budget matrix from seven mature days", () => {
  const base = campaign("7", {
    listing_stage: "established",
    budget_utilization_days_7d: 3,
    targetingType: "manual",
    match_types: ["exact"],
    performance_windows: {
      "7d": { data_days: 7, impressions: 1000, clicks: 20, orders: 2, ctr: 0.02, cvr: 0.1 },
    },
  });
  assert.equal(campaignLifecycleLabel(base), "老品");
  assert.equal(campaignPerformanceStatus(base), "normal");
  assert.equal(campaignBudgetMatrix(base).key, "normal_full");
  assert.equal(campaignAdTypeLabel(base), "精准");

  assert.equal(campaignPerformanceStatus({ ...base, performance_windows: { "7d": { data_days: 7, clicks: 9 } } }), "insufficient_sample");
  assert.equal(campaignPerformanceStatus({ ...base, listing_stage: "new" }), "new_observation");
  assert.equal(campaignBudgetMatrix({ ...base, performance_status: "poor" }).key, "poor_full");
});

test("grades every campaign directly from the selected mature window", () => {
  const graded = (ctr, cvr, overrides = {}) => campaign("7", {
    listing_stage: "unknown",
    performance_status: "unknown",
    performance_windows: {
      "7d": { data_days: 7, impressions: 1000, clicks: 100, orders: 10, ctr, cvr },
    },
    ...overrides,
  });

  assert.equal(campaignPerformanceGrade(graded(0.02, 0.16)).label, "表现优秀");
  assert.equal(campaignPerformanceGrade(graded(0.015, 0.12)).label, "表现良好");
  assert.equal(campaignPerformanceGrade(graded(0.008, 0.08)).label, "表现一般");
  assert.equal(campaignPerformanceGrade(graded(0.005, 0.12)).label, "表现较差");
  assert.equal(campaignPerformanceGrade(graded(0.02, 0.16, {
    performance_windows: { "7d": { data_days: 6, clicks: 100, ctr: 0.02, cvr: 0.16 } },
  })).label, "样本不足");
  assert.equal(campaignPerformanceGrade(graded(0.02, 0.16), "14d").label, "暂无数据");
});

test("derives purchase rate and sorts every campaign metric with missing values last", () => {
  const metricKeys = [
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
  ];
  const row = (id, value) => campaign(id, {
    default_bid: value,
    total_target_count: value,
    advertised_product_count: value,
    performance_windows: {
      "14d": Object.fromEntries(metricKeys.slice(3).map((key) => [key, value])),
    },
  });
  const rows = [row("1", 1), row("2", 2), campaign("3", { performance_windows: { "14d": {} } })];
  const derived = campaign("4", { performance_windows: { "14d": { clicks: 20, orders: 2 } } });

  assert.equal(campaignMetricValue(derived, "cvr", "14d"), 0.1);
  for (const metric of metricKeys) {
    assert.deepEqual(sortCampaignsByMetric(rows, metric, "asc", "14d").map(campaignIdOf), ["1", "2", "3"]);
    assert.deepEqual(sortCampaignsByMetric(rows, metric, "desc", "14d").map(campaignIdOf), ["2", "1", "3"]);
  }
});

test("derives SKU advertising guardrails from the existing profit payload", () => {
  const metrics = skuControlMetrics({
    analysis: { acosSp: "37.72", availableDays: "53.3" },
    financial: {
      profit: "6837.83",
      salePrice: "31151.68",
      adTotalCost: "5167.27",
      adSpCost: "4153.32",
      adSpSalePrice: "11010.36",
      refundPercent: "2.09",
    },
  });

  assert.ok(Math.abs(metrics.breakEvenAcosPct - 38.5375684393) < 1e-9);
  assert.equal(metrics.skuSpAcosPct, 37.72);
  assert.ok(Math.abs(metrics.acosHeadroomPct - 0.8175684393) < 1e-9);
  assert.equal(metrics.availableDays, 53.3);
  assert.ok(Math.abs(metrics.spSalesSharePct - 35.3443538198) < 1e-9);
  assert.equal(metrics.refundRatePct, 2.09);
});

test("falls back to SP cost and sales without fabricating unavailable guardrails", () => {
  const metrics = skuControlMetrics({
    financial: {
      profit: 2,
      salePrice: 10,
      adTotalCost: -1,
      adSpCost: -2,
      adSpSalePrice: 5,
    },
  });

  assert.equal(metrics.breakEvenAcosPct, 30);
  assert.equal(metrics.skuSpAcosPct, 40);
  assert.equal(metrics.acosHeadroomPct, -10);
  assert.equal(metrics.spSalesSharePct, 50);
  assert.equal(metrics.availableDays, null);
  assert.equal(metrics.refundRatePct, null);
});

test("filters campaigns and paginates exactly ten per page", () => {
  const campaigns = Array.from({ length: 23 }, (_, index) => campaign(index + 1, {
    state: index === 0 ? "paused" : "enabled",
    priority: index === 1 ? "high" : "low",
  }));
  assert.equal(filterCampaigns(campaigns, "Campaign 2", "all").length, 5);
  assert.equal(filterCampaigns(campaigns, "", "enabled").length, 22);
  assert.equal(filterCampaigns(campaigns, "", "attention").length, 1);

  const first = paginateCampaigns(campaigns, 1, CAMPAIGNS_PER_PAGE);
  const last = paginateCampaigns(campaigns, 3, CAMPAIGNS_PER_PAGE);
  assert.equal(first.rows.length, 10);
  assert.equal(last.rows.length, 3);
  assert.equal(last.pageCount, 3);
});

test("filters campaigns by exact, broad, phrase and auto match types", () => {
  const campaigns = [
    campaign(1, { ad_type: "exact", match_types: ["exact"] }),
    campaign(2, { ad_type: "broad", match_types: ["broad"] }),
    campaign(3, { ad_type: "phrase", match_types: ["phrase"] }),
    campaign(4, { ad_type: "auto", targetingType: "auto" }),
    campaign(5, { ad_type: "manual_mixed", match_types: ["broad", "exact"] }),
    campaign(6, { ad_type: "product_target" }),
  ];

  assert.deepEqual(filterCampaigns(campaigns, "", "all", "exact").map(campaignIdOf), ["1", "5"]);
  assert.deepEqual(filterCampaigns(campaigns, "", "all", "broad").map(campaignIdOf), ["2", "5"]);
  assert.deepEqual(filterCampaigns(campaigns, "", "all", "phrase").map(campaignIdOf), ["3"]);
  assert.deepEqual(filterCampaigns(campaigns, "", "all", "auto").map(campaignIdOf), ["4"]);
  assert.equal(filterCampaigns(campaigns, "", "all", "all").length, 6);
});

test("keeps keyword insight inside the hovered search-term panel", () => {
  const viewport = { viewportWidth: 2048, viewportHeight: 1024 };
  const left = keywordPopoverPosition({
    ...viewport,
    anchorRect: { left: 492, right: 1612, top: 632, bottom: 670 },
    boundaryRect: { left: 492, right: 1195 },
  });
  const right = keywordPopoverPosition({
    ...viewport,
    anchorRect: { left: 1210, right: 2330, top: 632, bottom: 670 },
    boundaryRect: { left: 1210, right: 1918 },
  });

  assert.ok(left.left >= 500);
  assert.ok(left.left + left.width <= 1187);
  assert.ok(right.left >= 1218);
  assert.ok(right.left + right.width <= 1910);

  const narrow = keywordPopoverPosition({
    anchorRect: { left: 428, right: 1548, top: 340, bottom: 381 },
    boundaryRect: { left: 427, right: 819.8125, top: 278, bottom: 558 },
    viewportWidth: 1280,
    viewportHeight: 720,
  });
  assert.equal(narrow.left, 427);
  assert.equal(narrow.width, 392.8125);
  assert.equal(narrow.left + narrow.width, 819.8125);
});

test("blocks budget increases until the explicit budget guardrail passes", () => {
  const blocked = normalizeDecision({
    action: "INCREASE_BUDGET",
    evidence: [{ label: "预算耗尽" }],
  });
  assert.equal(blocked.gate, "BLOCK");
  assert.ok(blocked.blockers.some((item) => item.code === "BUDGET_GUARDRAIL"));

  const reviewable = normalizeDecision({
    action: "INCREASE_BUDGET",
    budget_guardrail_passed: true,
    evidence: [{ label: "利润、库存、转化和整店预算均通过" }],
    execution_gate: "REVIEW",
  });
  assert.equal(reviewable.gate, "REVIEW");
});

test("blocks a decision with no evidence and labels every supported grain", () => {
  assert.equal(normalizeDecision({ action: "DECREASE_BID" }).gate, "BLOCK");
  assert.equal(grainLabel("campaign"), "活动级");
  assert.equal(grainLabel("ad_group"), "广告组级");
  assert.equal(grainLabel("ad_product"), "广告商品级");
  assert.equal(grainLabel("sku"), "SKU全业务级");
  assert.equal(grainLabel("keyword"), "投放级");
  assert.equal(grainLabel("placement"), "广告位级");
  assert.equal(grainLabel("unexpected"), "粒度未知");
  assert.equal(missingValue(null), true);
  assert.equal(missingValue(0), false);
});

test("distinguishes unavailable ACoS from zero-sales and inactive rows", () => {
  assert.equal(acosState({ spend: 1.12, sales: 0, acos: null }), "no_sales");
  assert.equal(acosState({ spend: 0, sales: 0, acos: null }), "no_activity");
  assert.equal(acosState({ spend: 3, sales: 10, acos: 0.3 }), "available");
  assert.equal(acosState({ spend: 3, acos: null }), "missing");
});

test("reads the backend primary action and both decision time layers", () => {
  const decision = normalizeDecision({
    primary_action: { action_code: "DECREASE_BID", label: "降低竞价", priority: "高" },
    execution_gate: "REVIEW",
    mature_evidence: [{ label: "成熟ACoS偏高" }],
    today_confirmation: { status: "passed", message: "当前小时未反转" },
    protections: [{ status: "passed", message: "库存保护通过" }],
  });
  assert.equal(decision.action, "DECREASE_BID");
  assert.equal(decision.priority, "高");
  assert.equal(decision.gate, "REVIEW");
  assert.equal(decision.evidence[0].freshness, "mature_14d");
  assert.equal(decision.todayConfirmation[0].freshness, "current_hour");
  assert.equal(decision.protections.length, 1);
});

test("adapts the live backend report, hourly and source contracts", () => {
  const report = {
    top: [{ identity: { 用户搜索词: "lash clusters", 投放: "broad" }, spend: 12.3 }],
    top_converting: [{ identity: { 用户搜索词: "cluster lashes" }, orders: 4 }],
  };
  assert.equal(deepReportRows(report)[0]["用户搜索词"], "lash clusters");
  assert.equal(deepReportRows(report)[0].spend, 12.3);
  assert.equal(deepReportHighlightRows(report, "conversion")[0]["用户搜索词"], "cluster lashes");
  assert.equal(expandIdentity({ identity: { 用户搜索词: "page two" }, clicks: 7 })["用户搜索词"], "page two");

  const current = currentHourCampaign({
    today: {
      report_date: "2026-08-20",
      is_provisional: true,
      campaign: { summary: { spend: 21.5, orders: 3, acos: 0.31, latest_hour: 14 }, rows: [] },
    },
  });
  assert.equal(current.summary.spend, 21.5);
  assert.equal(current.latestHour, 14);
  assert.equal(current.layer.is_provisional, true);

  const delayed = hourlyMetricDisplay({
    today: { report_date: "2026-08-21", targets: { rows: [] } },
    recent_hour: {
      report_date: "2026-08-20",
      targets: { summary: { latest_hour: 23 }, rows: [{ hour: 23, targeting: "lash clusters" }] },
    },
  }, "targets");
  assert.equal(delayed.isFallback, true);
  assert.equal(delayed.reportDate, "2026-08-20");
  assert.equal(delayed.rows[0].hour, 23);
  assert.equal(delayed.freshness, "recent_hour");

  assert.equal(sourceLayerLabel({ source_id: "hour_campaign", provisional: true }), "当前小时暂定");
  assert.equal(sourceLayerLabel({ source_id: "deep_search_terms", realtime: false, cache_status: "file_cache" }), "D-2 本地 XLSX 快照");
  assert.equal(sourceLayerLabel({ source_id: "sp_campaign", realtime: true, cache_status: "persistent_snapshot" }), "定时本地快照");
});

test("builds the standard placement table with bidding settings and totals", () => {
  const report = { top: [
    { identity: { 广告位: "搜索结果顶部(首页)" }, impressions: 1736, clicks: 262, spend: 252.8, orders: 54, sales: 519.15, ctr: 0.1509, cpc: 0.96, acos: 0.4869 },
    { identity: { 广告位: "搜索结果其余位置" }, impressions: 4056, clicks: 65, spend: 49.64, orders: 14, sales: 131.06, ctr: 0.016, cpc: 0.76, acos: 0.3788 },
    { identity: { 广告位: "产品页面" }, impressions: 5895, clicks: 27, spend: 19.91, orders: 3, sales: 33.07, ctr: 0.0046, cpc: 0.74, acos: 0.6021 },
    { identity: { 广告位: "Off Amazon" }, impressions: 278, clicks: 0, spend: 0, orders: 0, sales: 0 },
  ] };
  const rows = placementPerformanceRows(report, {
    strategy: "manual",
    adjustments: '[{"predicate":"placementRestOfSearch","percentage":10},{"predicate":"placementTop","percentage":17}]',
  });
  assert.equal(rows.length, 3);
  assert.equal(rows[0].bidding_strategy, "固定竞价");
  assert.equal(rows[0].bid_adjustment, 17);
  assert.equal(rows[1].bid_adjustment, 10);
  assert.equal(rows[2].bid_adjustment, 0);
  assert.equal(rows[0].spend_share, 252.8 / 322.35);
  assert.equal(rows[0].order_share, 54 / 71);
  assert.equal(rows[0].cvr, 54 / 262);
  assert.equal(rows[0].acos, 252.8 / 519.15);
  assert.ok(Math.abs(rows[0].acos_delta - ((252.8 / 519.15) - (322.35 / 683.28))) < 1e-12);
  assert.equal(rows[0].sample_confidence, "较充分");
  assert.deepEqual(
    placementPerformanceSummary(rows),
    {
      placement: "总计：3",
      bidding_strategy: "—",
      bid_adjustment: "—",
      impressions: 11687,
      clicks: 354,
      ctr: 354 / 11687,
      spend: 322.35,
      cpc: 322.35 / 354,
      orders: 71,
      sales: 683.28,
      acos: 322.35 / 683.28,
      spend_share: 1,
      order_share: 1,
      cvr: 71 / 354,
      acos_delta: 0,
      sample_confidence: "汇总",
    },
  );
});

test("summarizes conversion value, waste exposure and sample quality", () => {
  const summary = searchTermStructureSummary({
    status: "available",
    conversion_count: 2,
    waste_count: 2,
    summary: { spend: 50, orders: 10 },
    conversion_summary: { orders: 6, sales: 90, effective_sample_count: 1, attention_count: 2, sample_insufficient_count: 1 },
    waste_summary: {
      spend: 12,
      effective_sample_count: 1,
      attention_count: 1,
      sample_insufficient_count: 1,
      max_clicks_term: { identity: { 用户搜索词: "zero order" }, clicks: 18 },
    },
  }, 12);
  assert.equal(summary.conversion.orders, 6);
  assert.equal(summary.conversion.orderShare, 0.5);
  assert.equal(summary.waste.spendShare, 0.24);
  assert.equal(summary.waste.maxClicksTerm, "zero order");
  assert.equal(summary.waste.maxClicks, 18);
  assert.deepEqual(summary.sample, { effective: 2, attention: 3, insufficient: 2 });
});

test("classifies mature search terms for CPC adjustment and negative review", () => {
  assert.equal(searchTermRecommendation({ orders: 2, spend: 6, sales: 30, clicks: 8 }), "adjust-cpc");
  assert.equal(searchTermRecommendation({ orders: 2, spend: 20, sales: 10, acos: 2, clicks: 8 }), null);
  assert.equal(searchTermRecommendation({ orders: 0, spend: 5.47, clicks: 10 }), "negative");
  assert.equal(searchTermRecommendation({ orders: 1, spend: 3, sales: 10, clicks: 6 }), null);
  assert.equal(searchTermRecommendation({ orders: 0, clicks: 2, recommendation: "NEGATIVE_EXACT" }), "negative");
});

test("summarizes search-term value without hiding sample quality", () => {
  assert.deepEqual(searchTermValue({ orders: 3, spend: 6, sales: 30, clicks: 10 }), {
    key: "core", label: "核心词", tone: "core", sample: "样本较足",
  });
  assert.equal(searchTermValue({ orders: 2, spend: 0.56, sales: 17.58, clicks: 1 }).key, "potential");
  assert.equal(searchTermValue({ orders: 8, spend: 42, sales: 100, clicks: 60 }).key, "optimize");
  assert.equal(searchTermValue({ orders: 3, spend: 25, sales: 36, clicks: 29 }).key, "expensive");
  assert.equal(searchTermValue({ orders: 0, spend: 5.47, clicks: 10 }).key, "waste");
  assert.equal(searchTermValue({ orders: 0, spend: 2, clicks: 4 }).key, "watch");
});

test("uses targetingType to turn an automatic campaign winner into exact and broad harvesting", () => {
  const automatic = { targetingType: "auto", campaign_name: "name does not matter" };
  const manual = { targetingType: "manual" };
  const winner = { orders: 3, spend: 6, sales: 30, clicks: 8 };
  assert.equal(isAutomaticCampaign(automatic), true);
  assert.equal(isAutomaticCampaign({ campaign_name: "AUTO campaign", strategy: "manual" }), false);
  assert.equal(searchTermSuggestion(winner, automatic), "优质词：新建精准 + 宽泛");
  assert.equal(searchTermSuggestion(winner, manual), "优质词：复核竞价");
});

test("accepts top-level action_code without inventing a different action", () => {
  const decision = normalizeDecision({
    action_code: "HOLD",
    evidence: [{ code: "NO_CHANGE", message: "保持观察" }],
    execution_gate: "MONITOR_ONLY",
  });
  assert.equal(decision.action, "HOLD");
  assert.equal(decision.gate, "MONITOR_ONLY");
});

test("normalizes partial payloads without inventing unavailable sections", () => {
  const model = normalizeDiagnosticPayload({
    campaign: campaign("7"),
    listing_context: [{ sku: "SKU-1", asin: "B001", openDate: "2026-08-01" }],
    sources: { campaign: { status: "complete", row_count: 1 } },
  });
  assert.equal(model.campaigns.length, 1);
  assert.deepEqual(model.structure, {});
  assert.deepEqual(model.performance, {});
  assert.equal(model.sources[0].name, "campaign");
  assert.equal(focusProducts(model)[0].sku, "SKU-1");
});

test("merges background detail without replacing overview hourly fields", () => {
  const overview = {
    campaign: campaign("7"),
    meta: { fetched_at: "overview-now" },
    decision: { action: "MONITOR_ONLY" },
    dataQuality: { status: "complete", issues: ["OVERVIEW_NOTE"] },
    performance: {
      today: {
        report_date: "2026-08-21",
        campaign: { summary: { spend: 9, latest_hour: 12 } },
        targets: [{ targeting: "overview-target" }],
      },
      mature_14d: { deep_reports: { search_terms: { effective_date: "window-a" } } },
    },
  };
  const full = {
    campaign: campaign("7", { campaign_name: "stale full name" }),
    meta: { fetched_at: "full-later" },
    decision: { action: "DECREASE_BID" },
    dataQuality: { status: "partial", issues: ["FULL_ISSUE"], source_errors: ["hour_target"], partial_sources: ["listing"] },
    performance: {
      today: {
        report_date: "2026-08-20",
        campaign: { summary: { spend: 5, orders: 2 } },
        ad_groups: [{ ad_group_id: "ag-1" }],
      },
      mature_14d: { deep_reports: { campaigns: { rows: [{ campaign_id: "7" }] } } },
    },
  };
  const merged = mergeDiagnosticModels(overview, full);
  assert.equal(merged.meta.fetched_at, "overview-now");
  assert.equal(merged.performance.today.report_date, "2026-08-21");
  assert.equal(merged.performance.today.campaign.summary.spend, 9);
  assert.equal(merged.performance.today.campaign.summary.orders, 2);
  assert.equal(merged.performance.today.ad_groups[0].ad_group_id, "ag-1");
  assert.equal(merged.performance.today.targets[0].targeting, "overview-target");
  assert.equal(merged.dataQuality.status, "partial");
  assert.deepEqual(merged.dataQuality.issues, ["FULL_ISSUE", "OVERVIEW_NOTE"]);
  assert.deepEqual(merged.dataQuality.source_errors, ["hour_target"]);
  assert.deepEqual(merged.dataQuality.partial_sources, ["listing"]);
});

test("keeps the worse data quality status and unions diagnostic issues", () => {
  const merged = mergeDiagnosticDataQuality(
    { status: "partial", issues: ["A"], source_errors: ["x"] },
    { status: "error", issues: ["A", "B"], partial_sources: ["y"] },
  );
  assert.equal(merged.status, "error");
  assert.deepEqual(merged.issues, ["A", "B"]);
  assert.deepEqual(merged.source_errors, ["x"]);
  assert.deepEqual(merged.partial_sources, ["y"]);
});

test("changes the search pager revision on refresh, effective window, or index version", () => {
  const base = {
    campaignId: "7",
    kind: "waste",
    refreshToken: 1,
    report: { effective_date: "2026-08-06..2026-08-19" },
    sources: [{ source_id: "deep_search_terms_index", fetched_at: "v1" }],
  };
  const revision = searchTermDataRevision(base);
  assert.notEqual(searchTermDataRevision({ ...base, refreshToken: 2 }), revision);
  assert.notEqual(searchTermDataRevision({ ...base, report: { effective_date: "2026-08-07..2026-08-20" } }), revision);
  assert.notEqual(searchTermDataRevision({ ...base, sources: [{ source_id: "deep_search_terms_index", fetched_at: "v2" }] }), revision);
  assert.equal(searchTermDataRevision({ ...base, meta: { unrelated: "ignored" } }), revision);
});
