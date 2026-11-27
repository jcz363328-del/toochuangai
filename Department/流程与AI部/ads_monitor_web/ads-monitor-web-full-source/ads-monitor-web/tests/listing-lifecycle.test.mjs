import assert from "node:assert/strict";
import test from "node:test";
import {
  LISTING_STAGE,
  aggregateCampaignLifecycles,
  campaignLifecycleFor,
  listingStageMatches,
  productListingStage,
} from "../src/listingLifecycle.js";

const product = (stage, overrides = {}) => ({
  shop_id: "shop-1",
  campaign_id: "campaign-1",
  listing_stage: stage,
  mapping_status: "matched",
  ...overrides,
});

test("keeps unknown lifecycle distinct from established", () => {
  assert.equal(productListingStage(product("unknown")), LISTING_STAGE.UNKNOWN);
  assert.equal(productListingStage(product("established")), LISTING_STAGE.ESTABLISHED);
  assert.equal(productListingStage(product("new", { mapping_status: "unmatched" })), LISTING_STAGE.UNKNOWN);
  assert.equal(productListingStage(product("new", { mapping_status: "source_unavailable" })), LISTING_STAGE.UNKNOWN);
  assert.equal(productListingStage(product("new", { mapping_status: "" })), LISTING_STAGE.UNKNOWN);
  assert.equal(listingStageMatches(LISTING_STAGE.UNKNOWN, LISTING_STAGE.ESTABLISHED), false);
  assert.equal(listingStageMatches(LISTING_STAGE.UNKNOWN, LISTING_STAGE.UNKNOWN), true);
});

test("aggregates every advertised position at shop and campaign grain", () => {
  const index = aggregateCampaignLifecycles([
    product("new", { ad_id: "ad-1" }),
    product("new", { ad_id: "ad-2" }),
  ]);
  const lifecycle = campaignLifecycleFor(index, product("new"));

  assert.equal(lifecycle.stage, LISTING_STAGE.NEW);
  assert.equal(lifecycle.total, 2);
  assert.equal(lifecycle.new_count, 2);
});

test("marks campaigns with different SKU stages as mixed", () => {
  const index = aggregateCampaignLifecycles([
    product("new", { sku: "sku-new" }),
    product("established", { sku: "sku-old" }),
  ]);

  assert.equal(campaignLifecycleFor(index, product("new")).stage, LISTING_STAGE.MIXED);
});

test("does not hide partial unknown mapping behind a known stage", () => {
  const index = aggregateCampaignLifecycles([
    product("new"),
    product("unknown", { sku: "sku-unknown", mapping_status: "not_found" }),
  ]);

  assert.equal(campaignLifecycleFor(index, product("new")).stage, LISTING_STAGE.UNKNOWN);
  assert.equal(campaignLifecycleFor(index, { shop_id: "missing", campaign_id: "missing" }).stage, LISTING_STAGE.UNKNOWN);
});
