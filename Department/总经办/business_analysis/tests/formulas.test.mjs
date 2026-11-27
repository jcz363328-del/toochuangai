import assert from "node:assert/strict";
import test from "node:test";
import { evaluateFormulaMetrics } from "../server/formulas/evaluate.mjs";
import { buildQueryContext } from "../server/queries/catalog.mjs";
import { getEffectivePeriodContext } from "../server/queries/shape-workbook.mjs";

const baseMetrics = {
  salesCurrent: 310,
  profitCurrent: 62,
  marginBaseCurrent: 248,
  salesPrevious: 300,
  salesYearAgo: 250,
  daysCurrent: 31,
  daysPrevious: 30,
  daysYearAgo: 31,
  inventoryAmount: 1_000,
  slowMovingAmount: 100,
  shippingTotalUnits: 500,
  oceanUnits: 200,
  airUnits: 50,
};

test("evaluates normal KPI formulas", () => {
  const traces = evaluateFormulaMetrics(baseMetrics, { evaluatedAt: "2026-08-11T00:00:00.000Z" });
  const byId = new Map(traces.map((trace) => [trace.id, trace]));
  assert.equal(byId.get("sales.current").value, 310);
  assert.equal(byId.get("margin.current").value, 0.25);
  assert.equal(byId.get("growth.daily_mom").value, 0);
  assert.equal(byId.get("growth.yoy").value, 0.24);
  assert.equal(byId.get("shipping.ocean_share").value, 0.4);
  assert.equal(byId.get("shipping.air_share").value, 0.1);
  assert.equal(byId.get("inventory.slow_share").value, 0.1);
});

test("returns explicit divide-by-zero and missing-input states", () => {
  const zero = evaluateFormulaMetrics({ ...baseMetrics, marginBaseCurrent: 0, shippingTotalUnits: 0 });
  assert.equal(zero.find((trace) => trace.id === "margin.current").status, "divide-by-zero");
  assert.equal(zero.find((trace) => trace.id === "shipping.ocean_share").value, null);

  const missing = evaluateFormulaMetrics({ ...baseMetrics, salesYearAgo: null });
  assert.equal(missing.find((trace) => trace.id === "growth.yoy").status, "missing-input");
});

test("marks successful formulas stale without hiding their values", () => {
  const trace = evaluateFormulaMetrics(baseMetrics, { stale: true })
    .find((item) => item.id === "sales.current");
  assert.equal(trace.status, "stale");
  assert.equal(trace.value, 310);
});

test("auto basis uses loaded days for an unfinished month", () => {
  const context = buildQueryContext({ period: "2024-02", basis: "auto" });
  const rows = [
    { PeriodKey: "current", BusinessDate: "2024-02-01" },
    { PeriodKey: "current", BusinessDate: "2024-02-10" },
  ];
  const effective = getEffectivePeriodContext(context, rows, "Asia/Shanghai", new Date("2024-02-15T04:00:00Z"));
  assert.equal(effective.mode, "mtd");
  assert.equal(effective.daysCurrent, 10);
  assert.equal(effective.daysPrevious, 10);
});

test("full basis respects leap-year calendar days", () => {
  const context = buildQueryContext({ period: "2024-02", basis: "full" });
  const effective = getEffectivePeriodContext(context, [], "Asia/Shanghai", new Date("2024-02-15T04:00:00Z"));
  assert.equal(effective.mode, "full");
  assert.equal(effective.daysCurrent, 29);
  assert.equal(effective.daysPrevious, 31);
});
