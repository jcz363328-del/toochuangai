import { toSourceDepartment } from "../departments.mjs";

const commonParams = [
  { name: "currentStart", type: "date" },
  { name: "currentEnd", type: "date" },
  { name: "previousStart", type: "date" },
  { name: "previousEnd", type: "date" },
  { name: "yearAgoStart", type: "date" },
  { name: "yearAgoEnd", type: "date" },
  { name: "department", type: "text" },
  { name: "operator", type: "text" },
  { name: "store", type: "int" },
];

export const queryCatalog = Object.freeze({
  performance: {
    params: commonParams,
    text: `
WITH Performance AS (
SELECT
  CASE
    WHEN ml.RiQi >= @currentStart AND ml.RiQi < @currentEnd THEN 'current'
    WHEN ml.RiQi >= @previousStart AND ml.RiQi < @previousEnd THEN 'previous'
    ELSE 'yearAgo'
  END AS PeriodKey,
  CAST(ml.RiQi AS date) AS BusinessDate,
  ml.BuMen AS Department,
  ml.YunYing AS Operator,
  ml.Dian AS Store,
  SUM(CAST(ml.XiaoShouE AS decimal(19,4))) AS Sales,
  SUM(CAST(ml.MaoLiRun AS decimal(19,4))) AS GrossProfit,
  SUM(CAST(ml.MaoLiLvFenMu AS decimal(19,4))) AS MarginBase
FROM v_MaoLiLv ml
WHERE (
      (ml.RiQi >= @currentStart AND ml.RiQi < @currentEnd)
   OR (ml.RiQi >= @previousStart AND ml.RiQi < @previousEnd)
   OR (ml.RiQi >= @yearAgoStart AND ml.RiQi < @yearAgoEnd)
  )
  AND (@department IS NULL OR ml.BuMen = @department)
  AND (@operator IS NULL OR ml.YunYing = @operator)
  AND (@store IS NULL OR ml.Dian = @store)
GROUP BY
  CASE
    WHEN ml.RiQi >= @currentStart AND ml.RiQi < @currentEnd THEN 'current'
    WHEN ml.RiQi >= @previousStart AND ml.RiQi < @previousEnd THEN 'previous'
    ELSE 'yearAgo'
  END,
  CAST(ml.RiQi AS date), ml.BuMen, ml.YunYing, ml.Dian
), Organization AS (
  SELECT Dian, MAX(BuMen) AS Department, MAX(ZuZhang) AS Leader, MAX(YunYing) AS Operator
  FROM v_PinPaiDianPu
  GROUP BY Dian
)
SELECT
  p.PeriodKey,
  p.BusinessDate,
  COALESCE(p.Department, o.Department) AS Department,
  o.Leader,
  COALESCE(p.Operator, o.Operator) AS Operator,
  p.Store,
  p.Sales,
  p.GrossProfit,
  p.MarginBase
FROM Performance p
LEFT JOIN Organization o ON p.Store = o.Dian`,
  },
  categorySegments: {
    minimumTimeoutMs: 45_000,
    params: [
      { name: "currentStart", type: "date" },
      { name: "currentEnd", type: "date" },
      { name: "previousStart", type: "date" },
      { name: "previousEnd", type: "date" },
    ],
    text: `
WITH Periods AS (
  SELECT N'current' AS PeriodKey, @currentStart AS StartDate, @currentEnd AS EndDate
  UNION ALL
  SELECT N'previous', @previousStart, @previousEnd
), Segments AS (
  SELECT 1 AS SortOrder, N'paired' AS SegmentKey, N'对毛' AS CategoryLabel,
    N'对毛-化纤' AS IndustryLabel
  UNION ALL
  SELECT 2, N'cluster', N'簇毛', N'簇毛'
), Departments AS (
  SELECT 1 AS SortOrder, N'周雪' AS Department
  UNION ALL SELECT 2, N'郭鑫'
  UNION ALL SELECT 3, N'侯瑞昕'
  UNION ALL SELECT 4, N'大张雯'
  UNION ALL SELECT 5, N'王钰媛'
), Organization AS (
  SELECT Dian, MAX(BuMen) AS Department
  FROM v_PinPaiDianPu
  WHERE BuMen IN (N'周雪', N'郭鑫', N'侯瑞昕', N'大张雯', N'王钰媛')
  GROUP BY Dian
), CompanyRaw AS (
  SELECT
    s.SegmentKey,
    p.PeriodKey,
    SUM(CAST(ml.XiaoShouE AS decimal(19,4))) AS Sales,
    SUM(CASE WHEN ml.Guo = N'美国' THEN CAST(ml.XiaoShouE AS decimal(19,4)) ELSE 0 END) AS UsSales
  FROM v_MaoLiLv ml
  INNER JOIN Periods p ON ml.RiQi >= p.StartDate AND ml.RiQi < p.EndDate
  INNER JOIN Segments s ON ml.FenLei = s.CategoryLabel
  GROUP BY s.SegmentKey, p.PeriodKey
), DepartmentRaw AS (
  SELECT
    s.SegmentKey,
    p.PeriodKey,
    o.Department,
    SUM(CAST(ml.XiaoShouE AS decimal(19,4))) AS Sales,
    SUM(CASE WHEN ml.Guo = N'美国' THEN CAST(ml.XiaoShouE AS decimal(19,4)) ELSE 0 END) AS UsSales
  FROM v_MaoLiLv ml
  INNER JOIN Periods p ON ml.RiQi >= p.StartDate AND ml.RiQi < p.EndDate
  INNER JOIN Segments s ON ml.FenLei = s.CategoryLabel
  INNER JOIN Organization o ON ml.Dian = o.Dian
  GROUP BY s.SegmentKey, p.PeriodKey, o.Department
), CompanyPivot AS (
  SELECT
    SegmentKey,
    SUM(CASE WHEN PeriodKey = N'current' THEN Sales ELSE 0 END) AS CurrentSales,
    SUM(CASE WHEN PeriodKey = N'previous' THEN Sales ELSE 0 END) AS PreviousSales,
    SUM(CASE WHEN PeriodKey = N'current' THEN UsSales ELSE 0 END) AS CurrentUsSales,
    SUM(CASE WHEN PeriodKey = N'previous' THEN UsSales ELSE 0 END) AS PreviousUsSales
  FROM CompanyRaw
  GROUP BY SegmentKey
), DepartmentPivot AS (
  SELECT
    SegmentKey,
    Department,
    SUM(CASE WHEN PeriodKey = N'current' THEN Sales ELSE 0 END) AS CurrentSales,
    SUM(CASE WHEN PeriodKey = N'previous' THEN Sales ELSE 0 END) AS PreviousSales,
    SUM(CASE WHEN PeriodKey = N'current' THEN UsSales ELSE 0 END) AS CurrentUsSales,
    SUM(CASE WHEN PeriodKey = N'previous' THEN UsSales ELSE 0 END) AS PreviousUsSales
  FROM DepartmentRaw
  GROUP BY SegmentKey, Department
)
SELECT
  s.SortOrder AS SegmentSort,
  1 AS RowSort,
  d.SortOrder AS DepartmentSort,
  N'summary' AS RowType,
  s.SegmentKey,
  s.CategoryLabel,
  s.IndustryLabel,
  d.Department,
  ISNULL(c.CurrentSales, 0) AS CurrentCompanySales,
  ISNULL(c.PreviousSales, 0) AS PreviousCompanySales,
  ISNULL(c.CurrentUsSales, 0) AS CurrentCompanyUsSales,
  ISNULL(c.PreviousUsSales, 0) AS PreviousCompanyUsSales,
  ISNULL(dp.CurrentSales, 0) AS CurrentDepartmentSales,
  ISNULL(dp.PreviousSales, 0) AS PreviousDepartmentSales,
  ISNULL(dp.CurrentUsSales, 0) AS CurrentDepartmentUsSales,
  ISNULL(dp.PreviousUsSales, 0) AS PreviousDepartmentUsSales,
  CAST(0 AS decimal(19,4)) AS CurrentIndustrySales,
  CAST(0 AS decimal(19,4)) AS PreviousIndustrySales,
  CAST(0 AS int) AS CurrentCoveredDays,
  CAST(0 AS int) AS PreviousCoveredDays,
  CAST(NULL AS date) AS ShareDate,
  CAST(NULL AS decimal(19,4)) AS ShareMarketSales,
  CAST(NULL AS decimal(19,4)) AS ShareCompanySales,
  CAST(NULL AS decimal(19,8)) AS CompanyShare
FROM Segments s
CROSS JOIN Departments d
LEFT JOIN CompanyPivot c ON s.SegmentKey = c.SegmentKey
LEFT JOIN DepartmentPivot dp ON s.SegmentKey = dp.SegmentKey AND d.Department = dp.Department
ORDER BY SegmentSort, RowSort, DepartmentSort, ShareDate
OPTION (RECOMPILE)`,
  },
  slowMoving: {
    params: [
      { name: "department", type: "text" },
      { name: "operator", type: "text" },
      { name: "store", type: "int" },
    ],
    text: `
SELECT
  dp.BuMen AS Department,
  dp.ZuZhang AS Leader,
  dp.YunYing AS Operator,
  zx.Dian AS Store,
  SUM(CAST(zx.KuCunE AS decimal(19,4))) AS InventoryAmount,
  SUM(CAST(zx.ZhiXiaoE AS decimal(19,4))) AS SlowMovingAmount
FROM v_ZhiXiao zx
LEFT JOIN v_PinPaiDianPu dp ON zx.Dian = dp.Dian
WHERE (@department IS NULL OR dp.BuMen = @department)
  AND (@operator IS NULL OR dp.YunYing = @operator)
  AND (@store IS NULL OR zx.Dian = @store)
GROUP BY zx.Dian, dp.BuMen, dp.ZuZhang, dp.YunYing
ORDER BY SlowMovingAmount DESC`,
  },
  shipping: {
    params: [
      { name: "currentStart", type: "date" },
      { name: "currentEnd", type: "date" },
      { name: "department", type: "text" },
      { name: "operator", type: "text" },
      { name: "store", type: "int" },
    ],
    text: `
WITH Outbound AS (
  SELECT Dian, SUM(CAST(ShuLiang AS decimal(19,4))) AS TotalUnits
  FROM ChuKu
  WHERE RiQi >= @currentStart AND RiQi < @currentEnd AND LeiXing = N'FBA出库'
  GROUP BY Dian
), Shipping AS (
  SELECT
    Dian,
    SUM(CASE WHEN YunShuFangShi2 = N'海运' THEN CAST(FaHuoLiang AS decimal(19,4)) ELSE 0 END) AS OceanUnits,
    SUM(CASE WHEN YunShuFangShi2 = N'空派' THEN CAST(FaHuoLiang AS decimal(19,4)) ELSE 0 END) AS AirUnits
  FROM v_FBAHuoJian
  WHERE ChuangJianShiJian >= @currentStart AND ChuangJianShiJian < @currentEnd
  GROUP BY Dian
)
SELECT
  dp.BuMen AS Department,
  dp.ZuZhang AS Leader,
  dp.YunYing AS Operator,
  cj.CengJi1 AS Tier,
  o.Dian AS Store,
  o.TotalUnits,
  ISNULL(s.OceanUnits, 0) AS OceanUnits,
  ISNULL(s.AirUnits, 0) AS AirUnits
FROM Outbound o
LEFT JOIN v_CengJi cj ON o.Dian = cj.Dian
LEFT JOIN v_PinPaiDianPu dp ON o.Dian = dp.Dian
LEFT JOIN Shipping s ON o.Dian = s.Dian
WHERE (@department IS NULL OR dp.BuMen = @department)
  AND (@operator IS NULL OR dp.YunYing = @operator)
  AND (@store IS NULL OR o.Dian = @store)
ORDER BY dp.BuMen, dp.ZuZhang, dp.YunYing, o.Dian`,
  },
  unshipped: {
    params: [
      { name: "currentStart", type: "date" },
      { name: "currentEnd", type: "date" },
      { name: "operator", type: "text" },
      { name: "store", type: "int" },
    ],
    text: `
WITH Dictionary AS (
  SELECT SKU, MAX(CAST(CaiGouJia AS decimal(19,4))) AS PurchasePrice
  FROM ZiDian
  GROUP BY SKU
), Organization AS (
  SELECT Dian, MAX(BuMen) AS Department, MAX(ZuZhang) AS Leader, MAX(YunYing) AS Operator
  FROM v_PinPaiDianPu
  GROUP BY Dian
)
SELECT
  o.Department,
  o.Leader,
  COALESCE(wfh.YunYing, o.Operator) AS Operator,
  wfh.Dian AS Store,
  COUNT_BIG(*) AS SkuCount,
  SUM(CAST(wfh.ShuLiang AS decimal(19,4)) * ISNULL(zd.PurchasePrice, 0)) AS Amount
FROM XinPinWeiFaHuo wfh
LEFT JOIN Dictionary zd ON wfh.SKU = zd.SKU
LEFT JOIN Organization o ON wfh.Dian = o.Dian
WHERE wfh.DaoRuShiJian >= @currentStart AND wfh.DaoRuShiJian < @currentEnd
  AND (@operator IS NULL OR wfh.YunYing = @operator)
  AND (@store IS NULL OR wfh.Dian = @store)
GROUP BY o.Department, o.Leader, COALESCE(wfh.YunYing, o.Operator), wfh.Dian
ORDER BY wfh.Dian`,
  },
  newProductOrders: {
    params: [
      { name: "currentStart", type: "date" },
      { name: "currentEnd", type: "date" },
      { name: "department", type: "text" },
      { name: "operator", type: "text" },
      { name: "store", type: "int" },
    ],
    text: `
WITH Organization AS (
  SELECT Dian, MAX(BuMen) AS Department, MAX(ZuZhang) AS Leader, MAX(YunYing) AS Operator
  FROM v_PinPaiDianPu
  GROUP BY Dian
)
SELECT
  sx.MinDate AS OrderedOn,
  o.Department,
  o.Leader,
  o.Operator,
  sx.Dian AS Store,
  sx.ZhuSKU AS Sku
FROM v_ShangXin sx
LEFT JOIN Organization o ON sx.Dian = o.Dian
WHERE sx.MinDate >= @currentStart AND sx.MinDate < @currentEnd
  AND (@department IS NULL OR o.Department = @department)
  AND (@operator IS NULL OR o.Operator = @operator)
  AND (@store IS NULL OR sx.Dian = @store)
ORDER BY sx.MinDate, sx.Dian, sx.ZhuSKU`,
  },
  magnetDaily: {
    params: [
      { name: "currentStart", type: "date" },
      { name: "currentEnd", type: "date" },
      { name: "store", type: "int" },
    ],
    text: `
SELECT
  CAST(RiQi AS date) AS BusinessDate,
  SUM(CAST(XiaoShouE AS decimal(19,4))) AS Sales
FROM v_MaoLiLv
WHERE RiQi >= @currentStart AND RiQi < @currentEnd
  AND FenLei = N'磁铁睫毛'
  AND (@store IS NULL OR Dian = @store)
GROUP BY CAST(RiQi AS date)
ORDER BY CAST(RiQi AS date)`,
  },
});

export function shiftPeriod(period, deltaMonths) {
  const [year, month] = period.split("-").map(Number);
  const shifted = new Date(Date.UTC(year, month - 1 + deltaMonths, 1));
  return `${shifted.getUTCFullYear()}-${String(shifted.getUTCMonth() + 1).padStart(2, "0")}`;
}

export function periodStart(period) {
  return `${period}-01`;
}

export function daysInPeriod(period) {
  const [year, month] = period.split("-").map(Number);
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

export function buildQueryContext({ period, basis, department, operator, store }) {
  const previous = shiftPeriod(period, -1);
  const yearAgo = shiftPeriod(period, -12);
  return {
    period,
    previous,
    yearAgo,
    basis,
    department: toSourceDepartment(department),
    operator: operator || null,
    store: store ?? null,
    currentStart: periodStart(period),
    currentEnd: periodStart(shiftPeriod(period, 1)),
    previousStart: periodStart(previous),
    previousEnd: periodStart(period),
    yearAgoStart: periodStart(yearAgo),
    yearAgoEnd: periodStart(shiftPeriod(yearAgo, 1)),
  };
}
