export const LISTING_STAGE = Object.freeze({
  ALL: "all",
  NEW: "new",
  ESTABLISHED: "established",
  MIXED: "mixed",
  UNKNOWN: "unknown",
});

const NEW_VALUES = new Set(["new", "new_listing", "newly_listed", "launch", "新品", "新上架"]);
const ESTABLISHED_VALUES = new Set(["established", "mature", "existing", "non_new", "old", "非新品", "成熟"]);
export function shopIdOfLifecycle(item) {
  return String(item?.shop_id || item?.shopId || item?.store_id || item?.storeId || "").trim();
}

export function campaignLifecycleKey(item) {
  return `${shopIdOfLifecycle(item) || "unknown"}::${String(item?.campaign_id || item?.campaignId || "unknown")}`;
}

export function normalizeListingStage(value) {
  const normalized = String(value || "").trim().toLowerCase().replaceAll("-", "_").replaceAll(" ", "_");
  if (NEW_VALUES.has(normalized)) return LISTING_STAGE.NEW;
  if (ESTABLISHED_VALUES.has(normalized)) return LISTING_STAGE.ESTABLISHED;
  if (normalized === LISTING_STAGE.MIXED) return LISTING_STAGE.MIXED;
  return LISTING_STAGE.UNKNOWN;
}

export function productListingStage(product) {
  const mapping = String(product?.mapping_status || "").trim().toLowerCase().replaceAll("-", "_");
  if (mapping !== "matched") return LISTING_STAGE.UNKNOWN;
  return normalizeListingStage(product?.listing_stage);
}

export function aggregateCampaignLifecycles(products = []) {
  const grouped = new Map();
  products.forEach((product) => {
    const key = campaignLifecycleKey(product);
    const stage = productListingStage(product);
    const current = grouped.get(key) || {
      stage: LISTING_STAGE.UNKNOWN,
      total: 0,
      new_count: 0,
      established_count: 0,
      unknown_count: 0,
    };
    current.total += 1;
    current[`${stage}_count`] = Number(current[`${stage}_count`] || 0) + 1;
    grouped.set(key, current);
  });

  grouped.forEach((current) => {
    if (current.unknown_count) current.stage = LISTING_STAGE.UNKNOWN;
    else if (current.new_count && current.established_count) current.stage = LISTING_STAGE.MIXED;
    else if (current.new_count) current.stage = LISTING_STAGE.NEW;
    else if (current.established_count) current.stage = LISTING_STAGE.ESTABLISHED;
    else current.stage = LISTING_STAGE.UNKNOWN;
  });
  return grouped;
}

export function campaignLifecycleFor(index, item) {
  return index.get(campaignLifecycleKey(item)) || {
    stage: LISTING_STAGE.UNKNOWN,
    total: 0,
    new_count: 0,
    established_count: 0,
    unknown_count: 0,
  };
}

export function listingStageMatches(stage, filter) {
  return filter === LISTING_STAGE.ALL || normalizeListingStage(stage) === filter;
}

export function listingStageLabel(stage) {
  return {
    [LISTING_STAGE.NEW]: "新上架",
    [LISTING_STAGE.ESTABLISHED]: "非新品",
    [LISTING_STAGE.MIXED]: "混合",
    [LISTING_STAGE.UNKNOWN]: "未知",
  }[normalizeListingStage(stage)] || "未知";
}
