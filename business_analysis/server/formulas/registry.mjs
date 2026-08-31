const sum = (values) => values.reduce((total, value) => total + value, 0);

export const formulaRegistry = Object.freeze([
  {
    id: "sales.current",
    label: "本期销售额",
    expression: "SUM(本期销售额)",
    unit: "CNY",
    precision: 0,
    dependencies: ["salesCurrent"],
    compute: ({ salesCurrent }) => salesCurrent,
  },
  {
    id: "profit.current",
    label: "本期毛利润",
    expression: "SUM(本期毛利润)",
    unit: "CNY",
    precision: 0,
    dependencies: ["profitCurrent"],
    compute: ({ profitCurrent }) => profitCurrent,
  },
  {
    id: "margin.current",
    label: "本期毛利率",
    expression: "本期毛利润 ÷ 毛利率分母",
    unit: "ratio",
    precision: 4,
    dependencies: ["profitCurrent", "marginBaseCurrent"],
    denominator: "marginBaseCurrent",
    compute: ({ profitCurrent, marginBaseCurrent }) => profitCurrent / marginBaseCurrent,
  },
  {
    id: "growth.daily_mom",
    label: "日均环比",
    expression: "(本期销售额 ÷ 本期天数) ÷ (上期销售额 ÷ 上期天数) − 1",
    unit: "ratio",
    precision: 4,
    dependencies: ["salesCurrent", "daysCurrent", "salesPrevious", "daysPrevious"],
    denominator: "salesPrevious",
    compute: ({ salesCurrent, daysCurrent, salesPrevious, daysPrevious }) =>
      (salesCurrent / daysCurrent) / (salesPrevious / daysPrevious) - 1,
  },
  {
    id: "growth.yoy",
    label: "销售额同比",
    expression: "(本期销售额 ÷ 本期天数) ÷ (去年同期销售额 ÷ 同期天数) − 1",
    unit: "ratio",
    precision: 4,
    dependencies: ["salesCurrent", "daysCurrent", "salesYearAgo", "daysYearAgo"],
    denominator: "salesYearAgo",
    compute: ({ salesCurrent, daysCurrent, salesYearAgo, daysYearAgo }) =>
      (salesCurrent / daysCurrent) / (salesYearAgo / daysYearAgo) - 1,
  },
  {
    id: "inventory.slow_share",
    label: "滞销占比",
    expression: "滞销金额 ÷ 库存金额",
    unit: "ratio",
    precision: 4,
    dependencies: ["slowMovingAmount", "inventoryAmount"],
    denominator: "inventoryAmount",
    compute: ({ slowMovingAmount, inventoryAmount }) => slowMovingAmount / inventoryAmount,
  },
  {
    id: "shipping.ocean_share",
    label: "海运占比",
    expression: "海运发货量 ÷ 总发货量",
    unit: "ratio",
    precision: 4,
    dependencies: ["oceanUnits", "shippingTotalUnits"],
    denominator: "shippingTotalUnits",
    compute: ({ oceanUnits, shippingTotalUnits }) => oceanUnits / shippingTotalUnits,
  },
  {
    id: "shipping.air_share",
    label: "空派占比",
    expression: "空派发货量 ÷ 总发货量",
    unit: "ratio",
    precision: 4,
    dependencies: ["airUnits", "shippingTotalUnits"],
    denominator: "shippingTotalUnits",
    compute: ({ airUnits, shippingTotalUnits }) => airUnits / shippingTotalUnits,
  },
]);

export const inputLabels = Object.freeze({
  salesCurrent: "本期销售额",
  profitCurrent: "本期毛利润",
  marginBaseCurrent: "毛利率分母",
  salesPrevious: "上期销售额",
  salesYearAgo: "去年同期销售额",
  daysCurrent: "本期有效天数",
  daysPrevious: "上期可比天数",
  daysYearAgo: "同期可比天数",
  inventoryAmount: "库存金额",
  slowMovingAmount: "滞销金额",
  shippingTotalUnits: "总发货量",
  oceanUnits: "海运发货量",
  airUnits: "空派发货量",
});

export function metricsFromWorkbook(data, effective) {
  const periodRows = data.performance?.periodRows || [];
  const slowMoving = data.slowMoving || [];
  const shipping = data.shipping || [];
  const current = periodRows.filter((row) => row.periodKey === "current");
  const previous = periodRows.filter((row) => row.periodKey === "previous");
  const yearAgo = periodRows.filter((row) => row.periodKey === "yearAgo");
  const currentMargins = current.map((row) => {
    const profit = Number(row.grossProfit);
    const margin = Number(row.grossMargin);
    return Number.isFinite(profit) && Number.isFinite(margin) && margin !== 0 ? profit / margin : 0;
  });
  return {
    salesCurrent: sum(current.map((row) => Number(row.sales) || 0)),
    profitCurrent: sum(current.map((row) => Number(row.grossProfit) || 0)),
    marginBaseCurrent: sum(currentMargins),
    salesPrevious: sum(previous.map((row) => Number(row.sales) || 0)),
    salesYearAgo: sum(yearAgo.map((row) => Number(row.sales) || 0)),
    daysCurrent: effective?.daysCurrent ?? null,
    daysPrevious: effective?.daysPrevious ?? null,
    daysYearAgo: effective?.daysYearAgo ?? null,
    inventoryAmount: sum(slowMoving.map((row) => Number(row.inventoryAmount) || 0)),
    slowMovingAmount: sum(slowMoving.map((row) => Number(row.slowMovingAmount) || 0)),
    shippingTotalUnits: sum(shipping.map((row) => Number(row.totalUnits) || 0)),
    oceanUnits: sum(shipping.map((row) => Number(row.oceanUnits) || 0)),
    airUnits: sum(shipping.map((row) => Number(row.airUnits) || 0)),
  };
}
