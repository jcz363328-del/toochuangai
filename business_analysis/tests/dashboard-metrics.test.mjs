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
  shapeStoreTiers,
  tierRank,
  shapeUnshipped,
} from "../server/queries/shape-workbook.mjs";
import { createDailyRefreshScheduler, delayUntilNextLocalDay, localDateKey } from "../server/store-tiers.mjs";

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
    YearAgoCompanySales: 800,
    CurrentCompanyUsSales: 600,
    PreviousCompanyUsSales: 500,
    YearAgoCompanyUsSales: 400,
  };
  const shaped = shapeCategorySegments([
    {
      ...base,
      Department: "周雪",
      CurrentDepartmentSales: 100,
      PreviousDepartmentSales: 90,
      YearAgoDepartmentSales: 80,
      CurrentDepartmentUsSales: 60,
      PreviousDepartmentUsSales: 50,
      YearAgoDepartmentUsSales: 40,
    },
    {
      ...base,
      Department: "郭鑫",
      CurrentDepartmentSales: 200,
      PreviousDepartmentSales: 180,
      YearAgoDepartmentSales: 160,
      CurrentDepartmentUsSales: 120,
      PreviousDepartmentUsSales: 100,
      YearAgoDepartmentUsSales: 80,
    },
  ]);
  const paired = shaped.categories[0];

  assert.equal(shaped.categories.length, 2);
  assert.deepEqual([paired.key, paired.label, paired.industryLabel], ["paired", "对毛", "对毛-化纤"]);
  assert.deepEqual(paired.company.current, { sales: 1_000, usSales: 600 });
  assert.deepEqual(paired.company.yearAgo, { sales: 800, usSales: 400 });
  assert.deepEqual(paired.industry.current, { sales: 0, coveredDays: 0, dailySales: null });
  assert.deepEqual(
    paired.departments.map((row) => row.department),
    ["运营一部", "运营二部", "运营三部", "运营六部", "运营七部"],
  );
  assert.equal(paired.departments[3].currentUsSales, 120);
  assert.equal(paired.departments[3].yearAgoSales, 160);
  assert.equal(paired.departments[2].currentSales, 0);
  assert.deepEqual(paired.shareDaily, []);
  assert.equal(shaped.categories[1].industry.current.dailySales, null);
  assert.deepEqual(shaped.categories[1].shareDaily, []);
});

test("品类阵营查询仅访问公司销售与五部门映射", () => {
  const spec = queryCatalog.categorySegments;

  assert.deepEqual(
    spec.params.map((parameter) => parameter.name),
    ["currentStart", "currentEnd", "previousStart", "previousEnd", "yearAgoStart", "yearAgoEnd"],
  );
  assert.equal(spec.minimumTimeoutMs, 45_000);
  assert.match(spec.text, /FROM v_MaoLiLv ml/);
  assert.match(spec.text, /FROM v_PinPaiDianPu/);
  assert.match(spec.text, /N'对毛'/);
  assert.match(spec.text, /N'簇毛'/);
  assert.match(spec.text, /N'yearAgo'/);
  assert.match(spec.text, /YearAgoCompanySales/);
  assert.match(spec.text, /YearAgoDepartmentSales/);
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

test("店铺层级查询使用 CengJi 历史口径并计算当前等级连续天数", () => {
  const spec = queryCatalog.storeTiers;
  assert.deepEqual(spec.params.map((parameter) => parameter.name), ["department", "operator", "store"]);
  assert.match(spec.text, /FROM CengJi cj/);
  assert.match(spec.text, /cj\.CengJi1/);
  assert.match(spec.text, /cj\.CengJi2/);
  assert.match(spec.text, /cj\.CengJiID AS TierRank/);
  assert.match(spec.text, /AS CurrentLevelDays/);
  assert.match(spec.text, /LastDifferentDate/);
  assert.match(spec.text, /LEFT JOIN v_PinPaiDianPu/);
});

test("店铺层级整形保留显示值并生成稳定排序", () => {
  const rows = shapeStoreTiers([
    { Store: 4, Tier: "钻3", CurrentLevelDays: 3, Department: "大张雯", Leader: "大张雯", Operator: "刘蓉蓉" },
    { Store: 21, Tier: "金9", Department: "王钰媛", Leader: "王钰媛", Operator: "李娜" },
  ], null, "2026-09-22");

  assert.deepEqual(rows.map((row) => [row.store, row.tier, row.effectiveDate]), [
    [4, "钻3", "2026-09-22"],
    [21, "金9", "2026-09-22"],
  ]);
  assert.ok(tierRank("钻1") > tierRank("金9"));
  assert.equal(rows[0].currentLevelDays, 3);
  assert.equal(rows[0].department, "运营三部");
});

test("未配置数据库时仍返回模板层级并合并到店铺明细", async () => {
  const service = createDashboardService({
    adapter: { query: async () => assert.fail("unconfigured service must not query") },
    cacheOptions: { ttlMs: 30_000, maxKeys: 20 },
    timezone: "Asia/Shanghai",
    refreshAfterMs: 60_000,
  });
  const result = await service.dashboard({
    period: "2026-09",
    basis: "auto",
    department: null,
    operator: null,
    store: null,
    force: false,
  }, false);

  assert.equal(result.data.storeTiers.length, 37);
  assert.equal(result.data.performance.stores.find((row) => row.store === 4)?.tier, "钻3");
  assert.equal(result.data.meta.storeTier.effectiveDate, "2026-09-20");
  assert.equal(result.sources.storeTiers.mode, "workbook-snapshot");
});

test("数据库层级先成功后返回空结果时保留最后成功数据", async () => {
  let tierQueries = 0;
  const service = createDashboardService({
    adapter: {
      query: async (spec) => {
        if (spec !== queryCatalog.storeTiers) return [];
        tierQueries += 1;
        return tierQueries === 1
          ? [{
              Store: 4,
              Tier: "钻4",
              TierRank: 20,
              EffectiveDate: "2026-09-22",
              Department: "大张雯",
              Leader: "大张雯",
              Operator: "刘蓉蓉",
            }]
          : [];
      },
    },
    // A single entry forces the first tier partition out of the ordinary
    // cache so the second request exercises the dedicated last-good store.
    cacheOptions: { ttlMs: 30_000, maxKeys: 1 },
    timezone: "Asia/Shanghai",
    refreshAfterMs: 60_000,
  });
  const request = {
    period: "2026-09",
    basis: "auto",
    department: null,
    operator: null,
    store: null,
    force: true,
  };

  const first = await service.dashboard(request, true);
  const second = await service.dashboard(request, true);

  assert.equal(tierQueries, 2);
  assert.equal(first.sources.storeTiers.mode, "database");
  assert.deepEqual(
    first.data.storeTiers.map(({ store, tier, tierRank, effectiveDate }) => ({ store, tier, tierRank, effectiveDate })),
    [{ store: 4, tier: "钻4", tierRank: 20, effectiveDate: "2026-09-22" }],
  );
  assert.deepEqual(second.data.storeTiers, first.data.storeTiers);
  assert.equal(second.sources.storeTiers.mode, "memory-cache");
  assert.equal(second.sources.storeTiers.stale, true);
  assert.equal(second.sources.storeTiers.warning, "STORE_TIERS_EMPTY");
  assert.equal(second.sources.storeTiers.lastSuccessAt, first.sources.storeTiers.fetchedAt);
  assert.equal(second.data.meta.storeTier.effectiveDate, "2026-09-22");
});

test("数据库层级首次返回空结果时退回工作簿快照", async () => {
  const service = createDashboardService({
    adapter: {
      query: async () => [],
    },
    cacheOptions: { ttlMs: 30_000, maxKeys: 20 },
    timezone: "Asia/Shanghai",
    refreshAfterMs: 60_000,
  });
  const result = await service.dashboard({
    period: "2026-09",
    basis: "auto",
    department: null,
    operator: null,
    store: null,
    force: true,
  }, true);

  assert.equal(result.data.storeTiers.length, 37);
  assert.equal(result.data.storeTiers.find((row) => row.store === 4)?.tier, "钻3");
  assert.equal(result.sources.storeTiers.mode, "workbook-snapshot");
  assert.equal(result.sources.storeTiers.stale, true);
  assert.equal(result.sources.storeTiers.warning, "STORE_TIERS_EMPTY");
  assert.equal(result.data.meta.storeTier.effectiveDate, "2026-09-20");
});

test("店铺层级缓存键按上海自然日切换", () => {
  const beforeMidnight = new Date("2026-09-22T15:59:20.000Z");
  const afterMidnight = new Date("2026-09-22T16:00:20.000Z");
  assert.equal(localDateKey("Asia/Shanghai", beforeMidnight), "2026-09-22");
  assert.equal(localDateKey("Asia/Shanghai", afterMidnight), "2026-09-23");
  assert.equal(delayUntilNextLocalDay("Asia/Shanghai", beforeMidnight), 60_000);
});

test("店铺层级调度器在本地零点触发刷新并继续排程", async () => {
  let refreshes = 0;
  const timers = [];
  const scheduler = createDailyRefreshScheduler({
    timezone: "Asia/Shanghai",
    now: () => new Date("2026-09-22T15:59:20.000Z"),
    refresh: async () => { refreshes += 1; },
    setTimer: (callback, delay) => {
      const timer = { callback, delay, unref() {} };
      timers.push(timer);
      return timer;
    },
  });

  scheduler.start();
  assert.equal(scheduler.active, true);
  assert.equal(timers[0].delay, 60_000);
  await timers[0].callback();
  assert.equal(refreshes, 1);
  assert.equal(timers.length, 2);
  scheduler.stop();
  assert.equal(scheduler.active, false);
});
