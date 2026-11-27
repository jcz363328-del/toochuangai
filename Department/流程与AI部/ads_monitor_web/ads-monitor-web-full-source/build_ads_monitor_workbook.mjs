import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";


const [payloadPath, outputPath, previewDir] = process.argv.slice(2);
if (!payloadPath || !outputPath) {
  throw new Error("Usage: node build_ads_monitor_workbook.mjs payload.json output.xlsx [preview-dir]");
}

const payload = JSON.parse(await fs.readFile(payloadPath, "utf8"));
const workbook = Workbook.create();
const dashboard = workbook.worksheets.add("监控总览");
const recommendations = workbook.worksheets.add("调控建议");
const campaigns = workbook.worksheets.add("活动监控");
const targets = workbook.worksheets.add("投放监控");
const rules = workbook.worksheets.add("规则配置");
const logs = workbook.worksheets.add("接口日志");
const source = workbook.worksheets.add("源数据");

const colors = {
  navy: "#17365D",
  blue: "#2F75B5",
  paleBlue: "#D9EAF7",
  orange: "#ED7D31",
  paleOrange: "#FCE4D6",
  green: "#70AD47",
  paleGreen: "#E2F0D9",
  red: "#C00000",
  paleRed: "#F4CCCC",
  yellow: "#FFF2CC",
  gray: "#E7E6E6",
  darkGray: "#595959",
  white: "#FFFFFF",
};

function asNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function asLocalTimestamp(value) {
  if (!value) return "";
  return String(value).slice(0, 19).replace("T", " ");
}

function excelColumn(index) {
  let value = index + 1;
  let result = "";
  while (value > 0) {
    value -= 1;
    result = String.fromCharCode(65 + (value % 26)) + result;
    value = Math.floor(value / 26);
  }
  return result;
}

function titleBand(sheet, title, subtitle, lastColumn) {
  const titleRange = sheet.getRange(`A1:${lastColumn}1`);
  titleRange.merge();
  titleRange.values = [[title]];
  titleRange.format = {
    fill: colors.navy,
    font: { bold: true, color: colors.white },
    horizontalAlignment: "left",
    verticalAlignment: "center",
  };
  titleRange.format.rowHeight = 30;
  const subtitleRange = sheet.getRange(`A2:${lastColumn}2`);
  subtitleRange.merge();
  subtitleRange.values = [[subtitle]];
  subtitleRange.format = {
    fill: colors.paleBlue,
    font: { color: colors.darkGray },
    wrapText: true,
    verticalAlignment: "center",
  };
  subtitleRange.format.rowHeight = 28;
  sheet.showGridLines = false;
}

function headerStyle(range) {
  range.format = {
    fill: colors.blue,
    font: { bold: true, color: colors.white },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "outside", style: "thin", color: colors.navy },
  };
  range.format.rowHeight = 28;
}

function addTable(sheet, name, headerRow, headers, rows) {
  const safeRows = rows.length ? rows : [headers.map(() => null)];
  const startColumn = "A";
  const endColumn = excelColumn(headers.length - 1);
  const endRow = headerRow + safeRows.length;
  sheet.getRange(`${startColumn}${headerRow}:${endColumn}${endRow}`).values = [
    headers,
    ...safeRows,
  ];
  headerStyle(sheet.getRange(`${startColumn}${headerRow}:${endColumn}${headerRow}`));
  const table = sheet.tables.add(
    `${startColumn}${headerRow}:${endColumn}${endRow}`,
    true,
    name,
  );
  table.style = "TableStyleMedium2";
  table.showFilterButton = true;
  table.showBandedRows = true;
  return { endRow, dataStartRow: headerRow + 1, dataEndRow: endRow };
}

function setWidths(sheet, widths) {
  Object.entries(widths).forEach(([column, width]) => {
    sheet.getRange(`${column}:${column}`).format.columnWidth = width;
  });
}

const meta = payload.meta || {};
const ruleByShop = new Map((payload.rules || []).map((item) => [item.shop_id, item]));
const currencyByShop = new Map([
  ...(payload.shops || []).map((item) => [item.shop_id, item.currency]),
  ...(payload.rules || []).map((item) => [item.shop_id, item.currency]),
]);
const currencyOf = (item) => item.currency || currencyByShop.get(item.shop_id) || "";
const currencies = [...new Set([
  ...(meta.currencies || []),
  ...(payload.shops || []).map(currencyOf),
  ...(payload.campaigns || []).map(currencyOf),
].filter(Boolean))].sort();
const isMixedCurrency = currencies.length > 1;
const subtitle = [
  `运行：${meta.run_id || ""}`,
  `数据：${meta.source_start_date || "-"} 至 ${meta.source_end_date || "-"}`,
  `生成：${meta.generated_at || ""}`,
  `状态：${meta.status || "unknown"}`,
  meta.mode === "demo" ? "演示数据" : "赛狐 API 实际数据",
].join("  |  ");

titleBand(campaigns, "SP 广告活动监控", subtitle, "T");
const campaignHeaders = [
  "店铺",
  "币种",
  "活动名称",
  "活动ID",
  "状态",
  "日预算",
  "成熟数据天数",
  "花费",
  "广告销售额",
  "广告订单",
  "点击",
  "展现",
  "ACoS",
  "ROAS",
  "CTR",
  "CVR",
  "CPC",
  "近7天预算高消耗天数",
  "最新数据日",
  "目标ACoS",
];
const campaignRows = (payload.campaigns || []).map((item) => [
  item.shop_name || item.shop_id,
  currencyOf(item),
  item.campaign_name,
  item.campaign_id,
  item.state,
  asNumber(item.budget),
  asNumber(item.data_days),
  asNumber(item.spend),
  asNumber(item.sales),
  asNumber(item.orders),
  asNumber(item.clicks),
  asNumber(item.impressions),
  null,
  null,
  null,
  null,
  null,
  asNumber(item.budget_utilization_days_7d),
  item.latest_date,
  asNumber(ruleByShop.get(item.shop_id)?.target_acos),
]);
const campaignTable = addTable(campaigns, "CampaignMonitorTable", 4, campaignHeaders, campaignRows);
campaigns.getRange("M5").formulas = [["=IFERROR(H5/I5,\"\")"]];
campaigns.getRange("N5").formulas = [["=IFERROR(I5/H5,\"\")"]];
campaigns.getRange("O5").formulas = [["=IFERROR(K5/L5,\"\")"]];
campaigns.getRange("P5").formulas = [["=IFERROR(J5/K5,\"\")"]];
campaigns.getRange("Q5").formulas = [["=IFERROR(H5/K5,\"\")"]];
for (const column of ["M", "N", "O", "P", "Q"]) {
  campaigns.getRange(`${column}5:${column}${campaignTable.dataEndRow}`).fillDown();
}
campaigns.getRange(`F5:F${campaignTable.dataEndRow}`).format.numberFormat = "#,##0.00";
campaigns.getRange(`H5:I${campaignTable.dataEndRow}`).format.numberFormat = "#,##0.00";
campaigns.getRange(`J5:L${campaignTable.dataEndRow}`).format.numberFormat = "#,##0";
campaigns.getRange(`M5:M${campaignTable.dataEndRow}`).format.numberFormat = "0.0%";
campaigns.getRange(`N5:N${campaignTable.dataEndRow}`).format.numberFormat = "0.00";
campaigns.getRange(`O5:P${campaignTable.dataEndRow}`).format.numberFormat = "0.0%";
campaigns.getRange(`Q5:Q${campaignTable.dataEndRow}`).format.numberFormat = "#,##0.00";
campaigns.getRange(`T5:T${campaignTable.dataEndRow}`).format.numberFormat = "0.0%";
campaigns.getRange(`M5:M${campaignTable.dataEndRow}`).conditionalFormats.add("colorScale", {
  colors: [colors.paleGreen, colors.yellow, colors.paleRed],
  thresholds: ["min", "50%", "max"],
});
campaigns.freezePanes.freezeRows(4);
setWidths(campaigns, {
  A: 14, B: 9, C: 30, D: 22, E: 12, F: 12, G: 12, H: 12, I: 14, J: 11,
  K: 10, L: 12, M: 10, N: 10, O: 10, P: 10, Q: 11, R: 17, S: 13, T: 11,
});

titleBand(targets, "SP 投放监控", subtitle, "W");
const targetHeaders = [
  "店铺",
  "币种",
  "活动名称",
  "活动ID",
  "投放词/商品",
  "投放ID",
  "类型",
  "匹配方式",
  "状态",
  "当前竞价",
  "成熟数据天数",
  "花费",
  "广告销售额",
  "广告订单",
  "点击",
  "展现",
  "ACoS",
  "ROAS",
  "CTR",
  "CVR",
  "CPC",
  "目标ACoS",
  "最新数据日",
];
const targetRows = (payload.targets || []).map((item) => [
  item.shop_name || item.shop_id,
  currencyOf(item),
  item.campaign_name,
  item.campaign_id,
  item.targeting,
  item.target_id,
  item.entity_type,
  item.match_type,
  item.state,
  asNumber(item.current_bid),
  asNumber(item.data_days),
  asNumber(item.spend),
  asNumber(item.sales),
  asNumber(item.orders),
  asNumber(item.clicks),
  asNumber(item.impressions),
  null,
  null,
  null,
  null,
  null,
  asNumber(ruleByShop.get(item.shop_id)?.target_acos),
  item.latest_date,
]);
const targetTable = addTable(targets, "TargetMonitorTable", 4, targetHeaders, targetRows);
targets.getRange("Q5").formulas = [["=IFERROR(L5/M5,\"\")"]];
targets.getRange("R5").formulas = [["=IFERROR(M5/L5,\"\")"]];
targets.getRange("S5").formulas = [["=IFERROR(O5/P5,\"\")"]];
targets.getRange("T5").formulas = [["=IFERROR(N5/O5,\"\")"]];
targets.getRange("U5").formulas = [["=IFERROR(L5/O5,\"\")"]];
for (const column of ["Q", "R", "S", "T", "U"]) {
  targets.getRange(`${column}5:${column}${targetTable.dataEndRow}`).fillDown();
}
targets.getRange(`J5:J${targetTable.dataEndRow}`).format.numberFormat = "#,##0.00";
targets.getRange(`L5:M${targetTable.dataEndRow}`).format.numberFormat = "#,##0.00";
targets.getRange(`N5:P${targetTable.dataEndRow}`).format.numberFormat = "#,##0";
targets.getRange(`Q5:Q${targetTable.dataEndRow}`).format.numberFormat = "0.0%";
targets.getRange(`R5:R${targetTable.dataEndRow}`).format.numberFormat = "0.00";
targets.getRange(`S5:T${targetTable.dataEndRow}`).format.numberFormat = "0.0%";
targets.getRange(`U5:U${targetTable.dataEndRow}`).format.numberFormat = "#,##0.00";
targets.getRange(`V5:V${targetTable.dataEndRow}`).format.numberFormat = "0.0%";
targets.getRange(`Q5:Q${targetTable.dataEndRow}`).conditionalFormats.add("colorScale", {
  colors: [colors.paleGreen, colors.yellow, colors.paleRed],
  thresholds: ["min", "50%", "max"],
});
targets.freezePanes.freezeRows(4);
setWidths(targets, {
  A: 14, B: 9, C: 28, D: 21, E: 28, F: 20, G: 10, H: 12, I: 11, J: 11,
  K: 12, L: 12, M: 14, N: 11, O: 10, P: 12, Q: 10, R: 10, S: 10, T: 10,
  U: 11, V: 11, W: 13,
});

titleBand(recommendations, "自动调控建议（仅供审核，不会写回广告）", subtitle, "X");
const recommendationHeaders = [
  "优先级",
  "建议动作",
  "店铺",
  "币种",
  "对象类型",
  "活动名称",
  "活动ID",
  "投放词/商品",
  "投放ID",
  "当前值",
  "建议值",
  "变化比例",
  "花费",
  "广告销售额",
  "订单",
  "点击",
  "ACoS",
  "目标ACoS",
  "规则",
  "判断原因",
  "数据状态",
  "审核状态",
  "匹配方式",
  "运行ID",
];
const recommendationRows = (payload.recommendations || []).map((item) => [
  item.priority,
  item.action_code,
  item.shop_name || item.shop_id,
  currencyOf(item),
  item.entity_type,
  item.campaign_name,
  item.campaign_id,
  item.target_text,
  item.target_id,
  asNumber(item.current_value),
  asNumber(item.proposed_value),
  asNumber(item.change_pct),
  asNumber(item.spend),
  asNumber(item.sales),
  asNumber(item.orders),
  asNumber(item.clicks),
  asNumber(item.acos),
  asNumber(item.target_acos),
  item.rule_id,
  item.reason,
  item.data_status,
  item.review_status,
  item.match_type,
  item.run_id,
]);
const recommendationTable = addTable(
  recommendations,
  "RecommendationTable",
  4,
  recommendationHeaders,
  recommendationRows,
);
recommendations.getRange(`J5:K${recommendationTable.dataEndRow}`).format.numberFormat = "#,##0.00";
recommendations.getRange(`L5:L${recommendationTable.dataEndRow}`).format.numberFormat = "0.0%";
recommendations.getRange(`M5:N${recommendationTable.dataEndRow}`).format.numberFormat = "#,##0.00";
recommendations.getRange(`O5:P${recommendationTable.dataEndRow}`).format.numberFormat = "#,##0";
recommendations.getRange(`Q5:R${recommendationTable.dataEndRow}`).format.numberFormat = "0.0%";
recommendations.getRange(`T5:T${recommendationTable.dataEndRow}`).format.wrapText = true;
recommendations.getRange(`V5:V${recommendationTable.dataEndRow}`).dataValidation = {
  rule: { type: "list", values: ["待审核", "已接受", "已拒绝", "已执行"] },
};
const actionRange = recommendations.getRange(`B5:B${recommendationTable.dataEndRow}`);
actionRange.conditionalFormats.add("containsText", {
  text: "DECREASE",
  format: { fill: colors.paleRed, font: { color: colors.red, bold: true } },
});
actionRange.conditionalFormats.add("containsText", {
  text: "INCREASE",
  format: { fill: colors.paleGreen, font: { color: "#375623", bold: true } },
});
actionRange.conditionalFormats.add("containsText", {
  text: "BLOCKED",
  format: { fill: colors.gray, font: { color: colors.darkGray } },
});
actionRange.conditionalFormats.add("containsText", {
  text: "OBSERVE",
  format: { fill: colors.yellow, font: { color: "#7F6000" } },
});
recommendations.freezePanes.freezeRows(4);
setWidths(recommendations, {
  A: 10, B: 18, C: 18, D: 9, E: 11, F: 28, G: 21, H: 28, I: 20, J: 11,
  K: 11, L: 11, M: 12, N: 14, O: 9, P: 9, Q: 10, R: 11, S: 24, T: 48,
  U: 12, V: 12, W: 12, X: 24,
});

titleBand(rules, "规则配置与口径", "黄色单元格为需要运营确认的阈值；本工作簿不会自动执行这些建议。", "R");
const ruleHeaders = [
  "店铺ID",
  "店铺名称",
  "币种",
  "目标ACoS",
  "最小订单",
  "扩量最小订单",
  "最小点击",
  "最小花费",
  "0单花费上限",
  "高ACoS倍数",
  "低ACoS倍数",
  "降价比例",
  "加价比例",
  "预算增加比例",
  "单次最大变化",
  "最小成熟天数",
  "保护活动",
  "保护投放",
];
const ruleRows = (payload.rules || []).map((item) => [
  item.shop_id,
  item.shop_name,
  item.currency,
  asNumber(item.target_acos),
  asNumber(item.min_orders),
  asNumber(item.scale_min_orders),
  asNumber(item.min_clicks),
  asNumber(item.min_spend),
  asNumber(item.max_zero_order_spend),
  asNumber(item.high_acos_multiplier),
  asNumber(item.low_acos_multiplier),
  asNumber(item.bid_decrease_pct),
  asNumber(item.bid_increase_pct),
  asNumber(item.budget_increase_pct),
  asNumber(item.max_change_pct),
  asNumber(item.min_mature_days),
  (item.protected_campaign_ids || []).join(","),
  (item.protected_target_ids || []).join(","),
]);
const ruleTable = addTable(rules, "RuleConfigTable", 4, ruleHeaders, ruleRows);
rules.getRange(`D5:D${ruleTable.dataEndRow}`).format.numberFormat = "0.0%";
rules.getRange(`J5:K${ruleTable.dataEndRow}`).format.numberFormat = "0.00";
rules.getRange(`L5:O${ruleTable.dataEndRow}`).format.numberFormat = "0.0%";
rules.getRange(`D5:R${ruleTable.dataEndRow}`).format.fill = colors.yellow;
const sourceStart = ruleTable.dataEndRow + 3;
rules.getRange(`A${sourceStart}:C${sourceStart}`).values = [["数据来源", "文档地址", "用途"]];
headerStyle(rules.getRange(`A${sourceStart}:C${sourceStart}`));
const sourceLinks = (payload.sources || []).map((item) => [item.name, item.url, "字段和接口口径"]);
if (sourceLinks.length) {
  rules.getRange(`A${sourceStart + 1}:C${sourceStart + sourceLinks.length}`).values = sourceLinks;
}
rules.freezePanes.freezeRows(4);
setWidths(rules, {
  A: 20, B: 50, C: 16, D: 12, E: 11, F: 13, G: 11, H: 11, I: 13,
  J: 12, K: 12, L: 11, M: 11, N: 13, O: 13, P: 13, Q: 26, R: 26,
});

titleBand(logs, "接口同步与数据质量日志", subtitle, "I");
const logHeaders = ["时间", "店铺", "接口", "报告日", "活动ID", "状态", "行数", "信息", "运行ID"];
const logRows = (payload.sync_logs || []).map((item) => [
  asLocalTimestamp(item.logged_at),
  item.shop_id,
  item.endpoint,
  item.report_date,
  item.campaign_id,
  item.status,
  asNumber(item.row_count),
  item.message,
  item.run_id,
]);
const logTable = addTable(logs, "ApiSyncLogTable", 4, logHeaders, logRows);
logs.getRange(`A5:A${logTable.dataEndRow}`).format.numberFormat = "yyyy-mm-dd hh:mm:ss";
logs.getRange(`F5:F${logTable.dataEndRow}`).conditionalFormats.add("containsText", {
  text: "error",
  format: { fill: colors.paleRed, font: { color: colors.red, bold: true } },
});
logs.getRange(`H5:H${logTable.dataEndRow}`).format.wrapText = true;
logs.freezePanes.freezeRows(4);
setWidths(logs, { A: 21, B: 16, C: 38, D: 13, E: 21, F: 11, G: 9, H: 48, I: 25 });

titleBand(source, "源数据（当前运行）", "原始接口 JSON 保存在 SQLite；此页保留监控工作簿需要的可核对字段。", "V");
const trendByCurrencyDate = new Map();
for (const item of payload.daily_trend || []) {
  const currency = currencyOf(item) || "未标注";
  const key = `${currency}\u0000${item.date}`;
  const row = trendByCurrencyDate.get(key) || { currency, date: item.date, spend: 0, sales: 0, orders: 0 };
  row.spend += asNumber(item.spend) || 0;
  row.sales += asNumber(item.sales) || 0;
  row.orders += asNumber(item.orders) || 0;
  trendByCurrencyDate.set(key, row);
}
const trendHeaders = ["日期", "币种", "花费", "广告销售额", "广告订单"];
const trendRows = [...trendByCurrencyDate.values()]
  .sort((a, b) => a.date.localeCompare(b.date) || a.currency.localeCompare(b.currency))
  .map((item) => [item.date, item.currency, item.spend, item.sales, item.orders]);
const trendTable = addTable(source, "DailyTrendSourceTable", 4, trendHeaders, trendRows);
source.getRange(`C5:D${trendTable.dataEndRow}`).format.numberFormat = "#,##0.00";
source.getRange(`E5:E${trendTable.dataEndRow}`).format.numberFormat = "#,##0";
const rawStart = trendTable.dataEndRow + 3;
const rawHeaders = [
  "聚合类型", "店铺ID", "币种", "日期", "小时", "活动ID", "广告组ID", "广告ID", "投放ID",
  "投放词", "匹配方式", "广告位", "MSKU", "ASIN", "花费", "点击", "展现", "订单", "销售额", "件数", "导入时间",
];
const rawRows = (payload.source_data || []).map((item) => [
  item.aggregation_type,
  item.shop_id,
  currencyOf(item),
  item.report_date,
  asNumber(item.report_hour),
  item.campaign_id,
  item.ad_group_id,
  item.ad_id,
  item.targeting_id,
  item.targeting,
  item.match_type,
  item.placement,
  item.msku,
  item.asin,
  asNumber(item.spend),
  asNumber(item.clicks),
  asNumber(item.impressions),
  asNumber(item.orders),
  asNumber(item.sales),
  asNumber(item.units),
  asLocalTimestamp(item.ingested_at),
]);
const rawTable = addTable(source, "HourlySourceTable", rawStart, rawHeaders, rawRows);
source.getRange(`O${rawTable.dataStartRow}:O${rawTable.dataEndRow}`).format.numberFormat = "#,##0.00";
source.getRange(`P${rawTable.dataStartRow}:R${rawTable.dataEndRow}`).format.numberFormat = "#,##0";
source.getRange(`S${rawTable.dataStartRow}:S${rawTable.dataEndRow}`).format.numberFormat = "#,##0.00";
source.getRange(`T${rawTable.dataStartRow}:T${rawTable.dataEndRow}`).format.numberFormat = "#,##0";
source.getRange(`U${rawTable.dataStartRow}:U${rawTable.dataEndRow}`).format.numberFormat = "yyyy-mm-dd hh:mm:ss";
source.freezePanes.freezeRows(4);
setWidths(source, {
  A: 13, B: 16, C: 9, D: 13, E: 8, F: 21, G: 21, H: 21, I: 21, J: 28,
  K: 12, L: 18, M: 18, N: 18, O: 12, P: 10, Q: 12, R: 10, S: 13, T: 9, U: 21,
});

titleBand(dashboard, "赛狐广告监控与自动调控建议", subtitle, "M");
const cards = [
  ["A4:B4", "A5:B6", "成熟窗口花费", isMixedCurrency ? "见分币种表" : `=SUM('活动监控'!H5:H${campaignTable.dataEndRow})`, isMixedCurrency ? "@" : "#,##0.00"],
  ["C4:D4", "C5:D6", "广告销售额", isMixedCurrency ? "见分币种表" : `=SUM('活动监控'!I5:I${campaignTable.dataEndRow})`, isMixedCurrency ? "@" : "#,##0.00"],
  ["E4:F4", "E5:F6", "整体 ACoS", isMixedCurrency ? "不可跨币种计算" : "=IFERROR(A5/C5,\"\")", isMixedCurrency ? "@" : "0.0%"],
  ["G4:H4", "G5:H6", "广告订单", `=SUM('活动监控'!J5:J${campaignTable.dataEndRow})`, "#,##0"],
  ["I4:J4", "I5:J6", "开启活动", `=COUNTIF('活动监控'!E5:E${campaignTable.dataEndRow},\"enabled\")`, "#,##0"],
  [
    "K4:L4",
    "K5:L6",
    "待审核动作",
    `=COUNTIF('调控建议'!B5:B${recommendationTable.dataEndRow},\"DECREASE_BID\")+COUNTIF('调控建议'!B5:B${recommendationTable.dataEndRow},\"INCREASE_BID\")+COUNTIF('调控建议'!B5:B${recommendationTable.dataEndRow},\"INCREASE_BUDGET\")+COUNTIF('调控建议'!B5:B${recommendationTable.dataEndRow},\"REVIEW_TARGET\")`,
    "#,##0",
  ],
];
for (const [labelRange, valueRange, label, formula, numberFormat] of cards) {
  const labelCell = dashboard.getRange(labelRange);
  labelCell.merge();
  labelCell.values = [[label]];
  labelCell.format = {
    fill: colors.blue,
    font: { bold: true, color: colors.white },
    horizontalAlignment: "center",
    verticalAlignment: "center",
  };
  const valueCell = dashboard.getRange(valueRange);
  valueCell.merge();
  if (formula.startsWith("=")) valueCell.formulas = [[formula]];
  else valueCell.values = [[formula]];
  valueCell.format = {
    fill: colors.paleBlue,
    font: { bold: true, color: colors.navy },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    numberFormat,
    borders: { preset: "outside", style: "thin", color: colors.blue },
  };
}

dashboard.getRange("A8:H8").merge();
dashboard.getRange("A8:H8").values = [[isMixedCurrency ? "分币种金额汇总（不同币种不可相加）" : "每日花费与广告销售额"]];
dashboard.getRange("A8:H8").format = { fill: colors.gray, font: { bold: true, color: colors.navy } };
if (isMixedCurrency) {
  dashboard.getRange("A9:E9").values = [["币种", "花费", "广告销售额", "广告订单", "ACoS"]];
  headerStyle(dashboard.getRange("A9:E9"));
  if (currencies.length) {
    const currencyEndRow = 9 + currencies.length;
    dashboard.getRange(`A10:A${currencyEndRow}`).values = currencies.map((currency) => [currency]);
    dashboard.getRange("B10:E10").formulas = [[
      `=SUMIF('活动监控'!$B$5:$B$${campaignTable.dataEndRow},$A10,'活动监控'!$H$5:$H$${campaignTable.dataEndRow})`,
      `=SUMIF('活动监控'!$B$5:$B$${campaignTable.dataEndRow},$A10,'活动监控'!$I$5:$I$${campaignTable.dataEndRow})`,
      `=SUMIF('活动监控'!$B$5:$B$${campaignTable.dataEndRow},$A10,'活动监控'!$J$5:$J$${campaignTable.dataEndRow})`,
      "=IFERROR(B10/C10,\"\")",
    ]];
    dashboard.getRange(`B10:E${currencyEndRow}`).fillDown();
    dashboard.getRange(`B10:C${currencyEndRow}`).format.numberFormat = "#,##0.00";
    dashboard.getRange(`D10:D${currencyEndRow}`).format.numberFormat = "#,##0";
    dashboard.getRange(`E10:E${currencyEndRow}`).format.numberFormat = "0.0%";
    dashboard.getRange(`A10:E${currencyEndRow}`).format.borders = {
      preset: "outside", style: "thin", color: colors.gray,
    };
  }
} else if (trendRows.length) {
  const chart = dashboard.charts.add("line", {
    chartType: "line",
    title: "每日花费与广告销售额",
    hasLegend: true,
  });
  const endRow = trendTable.dataEndRow;
  const spendSeries = chart.series.add("花费");
  spendSeries.categoryFormula = `'源数据'!$A$5:$A$${endRow}`;
  spendSeries.formula = `'源数据'!$C$5:$C$${endRow}`;
  spendSeries.fill = colors.orange;
  const salesSeries = chart.series.add("广告销售额");
  salesSeries.categoryFormula = `'源数据'!$A$5:$A$${endRow}`;
  salesSeries.formula = `'源数据'!$D$5:$D$${endRow}`;
  salesSeries.fill = colors.blue;
  chart.title = "每日花费与广告销售额";
  chart.titleTextStyle.fontSize = 12;
  chart.hasLegend = true;
  chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
  chart.yAxis = { numberFormatCode: "#,##0.00" };
  chart.setPosition("A9", "H24");
}

dashboard.getRange("J8:L8").merge();
dashboard.getRange("J8:L8").values = [["建议动作分布"]];
dashboard.getRange("J8:L8").format = { fill: colors.gray, font: { bold: true, color: colors.navy } };
dashboard.getRange("J9:K9").values = [["动作", "数量"]];
headerStyle(dashboard.getRange("J9:K9"));
const actionRows = (payload.action_counts || []).map((item) => [item.action_code, asNumber(item.count)]);
if (actionRows.length) {
  dashboard.getRange(`J10:K${9 + actionRows.length}`).values = actionRows;
}

dashboard.getRange("A27:M27").merge();
dashboard.getRange("A27:M27").values = [["优先处理建议"]];
dashboard.getRange("A27:M27").format = { fill: colors.orange, font: { bold: true, color: colors.white } };
const priorityOrder = new Map([["高", 0], ["中", 1], ["低", 2]]);
const topRecommendations = [...(payload.recommendations || [])]
  .filter((item) => !["HOLD", "OBSERVE", "PROTECTED"].includes(item.action_code))
  .sort((a, b) => (priorityOrder.get(a.priority) ?? 9) - (priorityOrder.get(b.priority) ?? 9))
  .slice(0, 10)
  .map((item) => [
    item.priority,
    item.action_code,
    currencyOf(item),
    item.campaign_name,
    item.target_text || "-",
    asNumber(item.current_value),
    asNumber(item.proposed_value),
    asNumber(item.acos),
    asNumber(item.target_acos),
    asNumber(item.spend),
    asNumber(item.orders),
    item.reason,
    item.data_status,
  ]);
const topHeaders = ["优先级", "动作", "币种", "活动", "投放词/商品", "当前", "建议", "ACoS", "目标", "花费", "订单", "原因", "数据状态"];
const topTable = addTable(dashboard, "TopRecommendationTable", 28, topHeaders, topRecommendations);
dashboard.getRange(`F29:G${topTable.dataEndRow}`).format.numberFormat = "#,##0.00";
dashboard.getRange(`H29:I${topTable.dataEndRow}`).format.numberFormat = "0.0%";
dashboard.getRange(`J29:J${topTable.dataEndRow}`).format.numberFormat = "#,##0.00";
dashboard.getRange(`K29:K${topTable.dataEndRow}`).format.numberFormat = "#,##0";
dashboard.getRange(`L29:L${topTable.dataEndRow}`).format.wrapText = true;
dashboard.getRange(`B29:B${topTable.dataEndRow}`).conditionalFormats.add("containsText", {
  text: "DECREASE",
  format: { fill: colors.paleRed, font: { color: colors.red, bold: true } },
});
dashboard.getRange(`B29:B${topTable.dataEndRow}`).conditionalFormats.add("containsText", {
  text: "INCREASE",
  format: { fill: colors.paleGreen, font: { color: "#375623", bold: true } },
});
const noteRow = topTable.dataEndRow + 3;
dashboard.getRange(`A${noteRow}:M${noteRow + 1}`).merge();
dashboard.getRange(`A${noteRow}:M${noteRow + 1}`).values = [[
  `说明：本版只读取赛狐 SP 广告数据并生成建议，不会修改竞价、预算或启停状态。` +
  `归因成熟期为 D-${meta.maturity_lag_days ?? 2}；状态为 partial、样本不足或对象未开启时不应执行建议。` +
  (isMixedCurrency ? " 金额只按币种分别汇总，禁止跨币种相加或计算整体 ACoS。" : ""),
]];
dashboard.getRange(`A${noteRow}:M${noteRow + 1}`).format = {
  fill: colors.yellow,
  font: { color: "#7F6000" },
  wrapText: true,
  verticalAlignment: "center",
  borders: { preset: "outside", style: "thin", color: colors.orange },
};
dashboard.getRange(`A${noteRow}:M${noteRow + 1}`).format.rowHeight = 42;
dashboard.freezePanes.freezeRows(2);
setWidths(dashboard, {
  A: 11, B: 18, C: 15, D: 22, E: 24, F: 11, G: 11, H: 10, I: 10, J: 18, K: 10, L: 46, M: 12,
});

const overview = await workbook.inspect({
  kind: "table",
  sheetId: "监控总览",
  range: "A1:M40",
  include: "values,formulas",
  tableMaxRows: 40,
  tableMaxCols: 13,
  maxChars: 12000,
});
const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(overview.ndjson);
console.log(formulaErrors.ndjson);

if (previewDir) {
  await fs.mkdir(previewDir, { recursive: true });
  const previewSheets = {
    "监控总览": "A1:M40",
    "调控建议": "A1:X20",
    "活动监控": "A1:T20",
    "投放监控": "A1:W20",
    "规则配置": "A1:R20",
    "接口日志": "A1:I20",
    "源数据": "A1:V25",
  };
  for (const [sheetName, range] of Object.entries(previewSheets)) {
    const preview = await workbook.render({
      sheetName,
      range,
      scale: 1,
      format: "png",
    });
    const bytes = new Uint8Array(await preview.arrayBuffer());
    await fs.writeFile(path.join(previewDir, `${sheetName}.png`), bytes);
  }
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
