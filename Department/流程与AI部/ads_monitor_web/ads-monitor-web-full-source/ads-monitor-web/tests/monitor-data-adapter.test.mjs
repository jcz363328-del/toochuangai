import assert from "node:assert/strict";
import test from "node:test";

import { adaptDiagnosticMonitorData } from "../src/monitorDataAdapter.js";

test("adapts a real diagnostic campaign list for the legacy monitor tabs", () => {
  const result = adaptDiagnosticMonitorData({
    meta: {
      shop_id: "475394",
      generated_at: "2026-09-02T07:32:57+00:00",
      snapshot_generated_at: "2026-09-02T07:30:00+00:00",
    },
    shop: {
      shop_id: "475394",
      shop_name: "21号站-李娜-US",
      currency: "USD",
    },
    data_quality: { status: "partial", issues: ["mature snapshot missing"] },
    campaigns: [
      {
        shopId: "475394",
        campaignId: "70540977760495",
        name: "21-180B lash clusters up-4.22",
        state: "enabled",
        skus: ["21-180B"],
        asins: ["B0CQKVFVHH"],
        performance_windows: {
          "14d": {
            spend: 700.5,
            sales: 1681,
            orders: 161,
            clicks: 803,
            impressions: 41458,
            acos: 0.4167,
            daily_trend: [
              { date: "2026-08-18", spend: 50.5, sales: 107.49, orders: 7 },
              { date: "2026-08-19", spend: 50.14, sales: 127.57, orders: 13 },
            ],
          },
        },
      },
      {
        shopId: "475394",
        campaignId: "second",
        name: "Second campaign",
        state: "paused",
        skus: ["SKU-2"],
        asins: ["ASIN-2"],
        performance_windows: {
          "14d": {
            spend: 10,
            sales: 20,
            orders: 2,
            daily_trend: [
              { date: "2026-08-18", spend: 10, sales: 20, orders: 2 },
            ],
          },
        },
      },
    ],
  });

  assert.equal(result.diagnostic_fallback, true);
  assert.equal(result.meta.mode, "live");
  assert.equal(result.meta.layer, "diagnostic_snapshot");
  assert.equal(result.meta.source_start_date, "2026-08-18");
  assert.equal(result.meta.source_end_date, "2026-08-19");
  assert.equal(result.meta.generated_at, "2026-09-02T07:30:00+00:00");
  assert.deepEqual(result.shops, [{ id: "475394", name: "21号站-李娜-US", currency: "USD" }]);
  assert.equal(result.campaigns[0].campaign_id, "70540977760495");
  assert.equal(result.campaigns[0].campaign_name, "21-180B lash clusters up-4.22");
  assert.equal(result.campaigns[0].spend, 700.5);
  assert.equal(result.campaigns[0].orders, 161);
  assert.equal(result.campaign_daily_trend.length, 3);
  assert.deepEqual(result.daily_trend[0], { date: "2026-08-18", spend: 60.5, sales: 127.49, orders: 9 });
  assert.equal(result.advertised_products[0].sku, "21-180B");
  assert.equal(result.advertised_products[0].campaign_id, "70540977760495");
  assert.deepEqual(result.recommendations, []);
});

test("does not invent mature performance or recommendations", () => {
  const result = adaptDiagnosticMonitorData({
    shop: { shop_id: "1", shop_name: "Store", currency: "USD" },
    campaigns: [{ campaignId: "2", name: "No mature data", performance_windows: {} }],
  });

  assert.equal(result.campaigns[0].spend, 0);
  assert.equal(result.campaigns[0].acos, null);
  assert.deepEqual(result.daily_trend, []);
  assert.deepEqual(result.recommendations, []);
});
