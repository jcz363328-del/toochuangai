function rowsOf(value) {
  return Array.isArray(value) ? value : [];
}

function finiteNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function campaignWindow(campaign, windowDays) {
  const windows = campaign?.performance_windows;
  const selected = windows && typeof windows === "object" ? windows[`${windowDays}d`] : null;
  if (selected && typeof selected === "object" && Object.keys(selected).length) return selected;
  const mature = campaign?.mature_14d;
  if (windowDays === 14 && mature && typeof mature === "object" && Object.keys(mature).length) return mature;
  return {};
}

function normalizeCampaign(campaign, shop, windowDays) {
  const performance = campaignWindow(campaign, windowDays);
  const campaignId = String(campaign?.campaign_id || campaign?.campaignId || "");
  return {
    ...campaign,
    shop_id: String(shop.shop_id || shop.id || campaign?.shop_id || campaign?.shopId || ""),
    shop_name: shop.shop_name || shop.name || campaign?.shop_name || "",
    currency: shop.currency || campaign?.currency || "",
    campaign_id: campaignId,
    campaign_name: campaign?.campaign_name || campaign?.name || campaignId,
    state: campaign?.state || campaign?.servingStatus || "unknown",
    serving_status: campaign?.serving_status || campaign?.servingStatus || campaign?.state || "unknown",
    spend: finiteNumber(performance.spend),
    sales: finiteNumber(performance.sales),
    orders: finiteNumber(performance.orders),
    clicks: finiteNumber(performance.clicks),
    impressions: finiteNumber(performance.impressions),
    acos: performance.acos == null ? null : finiteNumber(performance.acos),
    roas: performance.roas == null ? null : finiteNumber(performance.roas),
    ctr: performance.ctr == null ? null : finiteNumber(performance.ctr),
    cpc: performance.cpc == null ? null : finiteNumber(performance.cpc),
    daily_trend: rowsOf(performance.daily_trend),
  };
}

function normalizeRecommendations(payload, shop) {
  return rowsOf(payload?.recommendations).map((item) => ({
    ...item,
    shop_id: String(item.shop_id || item.shopId || shop.shop_id || shop.id || ""),
    shop_name: item.shop_name || shop.shop_name || shop.name || "",
    currency: item.currency || shop.currency || "",
    campaign_id: String(item.campaign_id || item.campaignId || ""),
    campaign_name: item.campaign_name || item.name || String(item.campaign_id || item.campaignId || ""),
    action_code: item.action_code || item.actionCode || item.action || "MONITOR_ONLY",
  }));
}

function aggregateDailyTrend(rows) {
  const byDate = new Map();
  rows.forEach((row) => {
    const date = String(row?.date || "");
    if (!date) return;
    const current = byDate.get(date) || { date, spend: 0, sales: 0, orders: 0 };
    current.spend += finiteNumber(row.spend);
    current.sales += finiteNumber(row.sales);
    current.orders += finiteNumber(row.orders);
    byDate.set(date, current);
  });
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
}

function advertisedProducts(campaigns) {
  return campaigns.flatMap((campaign) => {
    const skus = rowsOf(campaign.skus);
    const asins = rowsOf(campaign.asins);
    const count = Math.max(skus.length, asins.length);
    return Array.from({ length: count }, (_, index) => ({
      shop_id: campaign.shop_id,
      shop_name: campaign.shop_name,
      currency: campaign.currency,
      campaign_id: campaign.campaign_id,
      campaign_name: campaign.campaign_name,
      sku: skus[index] || skus[0] || "",
      asin: asins[index] || asins[0] || "",
      listing_stage: campaign.listing_stage || "unknown",
      mapping_status: campaign.listing_stage && campaign.listing_stage !== "unknown" ? "matched" : "unknown",
    }));
  });
}

export function adaptDiagnosticMonitorData(payload, { windowDays = 14 } = {}) {
  const source = payload && typeof payload === "object" ? payload : {};
  const shop = source.shop && typeof source.shop === "object" ? source.shop : {};
  const campaigns = rowsOf(source.campaigns).map((campaign) => normalizeCampaign(campaign, shop, windowDays));
  const campaignDailyTrend = campaigns.flatMap((campaign) => rowsOf(campaign.daily_trend).map((row) => ({
    ...row,
    shop_id: campaign.shop_id,
    shop_name: campaign.shop_name,
    currency: campaign.currency,
    campaign_id: campaign.campaign_id,
    campaign_name: campaign.campaign_name,
  })));
  const dailyTrend = aggregateDailyTrend(campaignDailyTrend);
  const sourceStartDate = dailyTrend[0]?.date || "";
  const sourceEndDate = dailyTrend.at(-1)?.date || "";
  const generatedAt = source.meta?.snapshot_generated_at || source.meta?.generated_at || new Date().toISOString();
  const dataQuality = source.data_quality && typeof source.data_quality === "object" ? source.data_quality : {};
  const shopId = String(shop.shop_id || shop.id || source.meta?.shop_id || "");

  return {
    meta: {
      ...source.meta,
      mode: "live",
      layer: "diagnostic_snapshot",
      status: dataQuality.status === "complete" ? "complete" : "partial",
      source_start_date: sourceStartDate,
      source_end_date: sourceEndDate,
      lookback_days: windowDays,
      maturity_lag_days: 2,
      generated_at: generatedAt,
      rule_version: source.meta?.rule_version || "诊断快照安全规则",
      failed_calls: finiteNumber(source.meta?.failed_calls),
      quality_failures: rowsOf(dataQuality.issues).length,
    },
    shops: shopId ? [{ id: shopId, name: shop.shop_name || shop.name || shopId, currency: shop.currency || "" }] : [],
    campaigns,
    recommendations: normalizeRecommendations(source, shop),
    advertised_products: advertisedProducts(campaigns),
    daily_trend: dailyTrend,
    campaign_daily_trend: campaignDailyTrend,
    source_data: [],
    shop_coverage: shopId ? [{
      shop_id: shopId,
      shop_name: shop.shop_name || shop.name || shopId,
      status: dataQuality.status || "partial",
    }] : [],
    policy: source.policy || {},
    diagnostic_fallback: true,
  };
}
