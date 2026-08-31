import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { aggregateMetric, buildStoreViews, summarizeOverallPerformance } from "../app/lib/dashboard.ts";
import { PartitionCache } from "../server/cache.mjs";
import { createDashboardService } from "../server/dashboard.mjs";
import { buildQueryContext, queryCatalog } from "../server/queries/catalog.mjs";
import { toDisplayDepartment, toSourceDepartment } from "../server/departments.mjs";
import {
  shapeCategorySegments,
  shapeNewProductOrders,
  shapePerformance,
  shapeUnshipped,
} from "../server/queries/shape-workbook.mjs";

const data = JSON.parse(
  await readFile(new URL("../app/data/workbook-data.json", import.meta.url), "utf8"),
);

test("完整业绩店口径保留 58 号店", () => {
  const stores = buildStoreViews(data).filter((row) => row.hasPerformance);
  const current = aggregateMetric(stores, "current");
  const previous = aggregateMetric(stores, "previous");

  assert.equal(stores.length, 39);
  assert.equal(current.sales, 13_948_141);
  assert.equal(previous.sales, 13_431_349);
  assert.equal(current.grossProfit, 2_945_017);
  assert.ok(stores.some((row) => row.store === 58 && row.current.sales === 9_410));
});

test("整体业绩按可比日均和加权毛利率计算三期变化", () => {
  const rows = [{
    current: { sales: 290, grossProfit: 40, grossMarginBase: 400, grossMargin: 0.1 },
    previous: { sales: 310, grossProfit: 36, grossMarginBase: 200, grossMargin: 0.18 },
    yearAgo: { sales: 280, grossProfit: 42, grossMarginBase: 210, grossMargin: 0.2 },
  }];
  const summary = summarizeOverallPerformance(rows, { current: 29, previous: 31, yearAgo: 28 });

  assert.equal(summary.current.dailySales, 10);
  assert.equal(summary.dailyMom, 0);
  assert.equal(summary.dailyYoy, 0);
  assert.ok(Math.abs(summary.marginMom + 0.08) < 1e-12);
  assert.ok(Math.abs(summary.marginYoy + 0.1) < 1e-12);
});

test("运营明细重复店铺按金额与次数累加", () => {
  const stores = buildStoreViews(data);
  const store26 = stores.find((row) => row.store === 26);

  assert.equal(stores.length, 52);
  assert.equal(store26?.unshippedCount, 3);
  assert.equal(store26?.unshippedAmount, 6_394.2);
});

test("实时整形保留部门口径，不用组长替代部门", () => {
  const snapshot = { performance: { stores: [] } };
  const context = {
    period: "2026-08",
    previous: "2026-07",
    yearAgo: "2025-08",
    basis: "full",
  };
  const rows = [{
    PeriodKey: "current",
    BusinessDate: "2026-08-01",
    Department: "侯瑞昕",
    Leader: "孙洁",
    Operator: "测试运营",
    Store: 20,
    Sales: 100,
    GrossProfit: 20,
    MarginBase: 80,
  }];
  const result = shapePerformance(rows, context, snapshot, "Asia/Shanghai").value;

  assert.equal(result.stores[0].department, "运营七部");
  assert.equal(result.stores[0].leader, "孙洁");
  assert.equal(result.periodRows[0].department, "运营七部");
});

test("风险分区保留部门、组长和运营映射", () => {
  const unshipped = shapeUnshipped([{
    Department: "郭鑫",
    Leader: "侯梁",
    Operator: "测试运营",
    Store: 23,
    SkuCount: 2,
    Amount: 300,
  }])[0];
  const order = shapeNewProductOrders([{
    OrderedOn: "2026-08-02",
    Department: "周雪",
    Leader: "刘蓉蓉",
    Operator: "测试运营",
    Store: 52,
    Sku: "SKU-1",
  }])[0];

  assert.deepEqual(
    [unshipped.department, unshipped.leader, order.department, order.leader],
    ["运营六部", "侯梁", "运营一部", "刘蓉蓉"],
  );
});

test("品类阵营整形只保留公司与五部门口径", () => {
  const base = {
    SegmentKey: "paired",
    CategoryLabel: "对毛",
    IndustryLabel: "对毛-化纤",
    CurrentCompanySales: 1_000,
    PreviousCompanySales: 900,
    CurrentCompanyUsSales: 600,
    PreviousCompanyUsSales: 500,
  };
  const shaped = shapeCategorySegments([
    {
      ...base,
      Department: "周雪",
      CurrentDepartmentSales: 100,
      PreviousDepartmentSales: 90,
      CurrentDepartmentUsSales: 60,
      PreviousDepartmentUsSales: 50,
    },
    {
      ...base,
      Department: "郭鑫",
      CurrentDepartmentSales: 200,
      PreviousDepartmentSales: 180,
      CurrentDepartmentUsSales: 120,
      PreviousDepartmentUsSales: 100,
    },
  ]);
  const paired = shaped.categories[0];

  assert.equal(shaped.categories.length, 2);
  assert.deepEqual([paired.key, paired.label, paired.industryLabel], ["paired", "对毛", "对毛-化纤"]);
  assert.deepEqual(paired.company.current, { sales: 1_000, usSales: 600 });
  assert.deepEqual(paired.industry.current, { sales: 0, coveredDays: 0, dailySales: null });
  assert.deepEqual(
    paired.departments.map((row) => row.department),
    ["运营一部", "运营二部", "运营三部", "运营六部", "运营七部"],
  );
  assert.equal(paired.departments[3].currentUsSales, 120);
  assert.equal(paired.departments[2].currentSales, 0);
  assert.deepEqual(paired.shareDaily, []);
  assert.equal(shaped.categories[1].industry.current.dailySales, null);
  assert.deepEqual(shaped.categories[1].shareDaily, []);
});

test("品类阵营查询仅访问公司销售与五部门映射", () => {
  const spec = queryCatalog.categorySegments;

  assert.deepEqual(
    spec.params.map((parameter) => parameter.name),
    ["currentStart", "currentEnd", "previousStart", "previousEnd"],
  );
  assert.equal(spec.minimumTimeoutMs, 45_000);
  assert.match(spec.text, /FROM v_MaoLiLv ml/);
  assert.match(spec.text, /FROM v_PinPaiDianPu/);
  assert.match(spec.text, /N'对毛'/);
  assert.match(spec.text, /N'簇毛'/);
  assert.doesNotMatch(spec.text, /(?:\bv_ABS\b|\bABS_LeiBie\b|\bABS\b)/i);
  assert.doesNotMatch(spec.text, /YueXiaoShouE|BSRPaiMing|ShareDaily/i);
  assert.doesNotMatch(spec.text, /\$\{/);
});

test("部门展示名、源名称和侯瑞欣别名可以双向映射", () => {
  assert.equal(toDisplayDepartment("周雪"), "运营一部");
  assert.equal(toDisplayDepartment("侯瑞欣"), "运营七部");
  assert.equal(toSourceDepartment("运营七部"), "侯瑞昕");
  assert.equal(buildQueryContext({
    period: "2026-08",
    basis: "full",
    department: "运营七部",
    operator: null,
    store: null,
  }).department, "侯瑞昕");
});

test("数据库未配置时品类阵营沿用快照分区来源", async () => {
  const service = createDashboardService({
    adapter: { query: async () => assert.fail("unconfigured service must not query") },
    cacheOptions: { ttlMs: 30_000, maxKeys: 20 },
    timezone: "Asia/Shanghai",
    refreshAfterMs: 60_000,
  });
  const result = await service.dashboard({
    period: "2026-07",
    basis: "full",
    department: null,
    operator: null,
    store: null,
    force: false,
  }, false);

  assert.ok(Array.isArray(result.data.categorySegments.categories));
  assert.equal("categorySegmentsByPeriod" in result.data, false);
  assert.equal(result.sources.categorySegments.mode, "workbook-snapshot");
  assert.equal(result.sources.categorySegments.warning, "DB_NOT_CONFIGURED");
});

test("近半年每个月均可按请求月份回退品类快照", async () => {
  const service = createDashboardService({
    adapter: { query: async () => assert.fail("unconfigured service must not query") },
    cacheOptions: { ttlMs: 30_000, maxKeys: 20 },
    timezone: "Asia/Shanghai",
    refreshAfterMs: 60_000,
  });
  for (const period of ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]) {
    const result = await service.dashboard({
      period,
      basis: "full",
      department: null,
      operator: null,
      store: null,
      force: false,
    }, false);
    assert.equal(result.data.categorySegments.categories.length, 2, period);
    assert.deepEqual(
      result.data.categorySegments.categories[0].departments.map((row) => row.department),
      ["运营一部", "运营二部", "运营三部", "运营六部", "运营七部"],
      period,
    );
  }
});

test("快照回退能把负责人旧名称映射为受限运营部门", async () => {
  const service = createDashboardService({
    adapter: { query: async () => assert.fail("unconfigured service must not query") },
    cacheOptions: { ttlMs: 30_000, maxKeys: 20 },
    timezone: "Asia/Shanghai",
    refreshAfterMs: 60_000,
  });
  const result = await service.dashboard({
    period: "2026-07",
    basis: "full",
    department: "运营一部",
    operator: null,
    store: null,
    force: false,
  }, false);

  assert.ok(result.data.performance.stores.length > 0);
  assert.ok(result.data.performance.stores.every((row) => row.department === "运营一部"));
});

test("分区缓存允许品类重查询使用更长 TTL", () => {
  const cache = new PartitionCache({ ttlMs: 30_000, maxKeys: 8 });
  const originalNow = Date.now;
  let now = 1_000;
  Date.now = () => now;
  try {
    cache.set("category", { value: 1 }, "2026-08-25T00:00:00.000Z");
    now += 60_000;
    assert.equal(cache.get("category"), null);
    assert.equal(cache.get("category", { ttlMs: 300_000 })?.value.value, 1);
  } finally {
    Date.now = originalNow;
  }
});
