import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = path.dirname(fileURLToPath(import.meta.url));

const allDepartments = "全体已登录用户";
const core = [
  ["创新提案管理", "", allDepartments],
  ["差评分析系统", "", "运营部及子部门（不含新人组）；技术部；AI部；总经办"],
  ["亚马逊站内信回复智能体", "", "运营部及子部门（不含新人组）；AI部；总经办；亚马逊"],
  ["定时邮件", "", "内容生产工厂及子部门（不含新人组）；TK部门；TK直播部；BD部；短视频部；客服；产品&店铺运营；AI部；总经办；深圳团队；技术部"],
  ["实时视频数据", "", "内容生产工厂及子部门（不含新人组）；TK部门；TK直播部；BD部；短视频部；客服；产品&店铺运营；摄影部；AI部；总经办；财务部；深圳团队；技术部"],
  ["OKAYLOVE数据看板", "", "内容生产工厂及子部门（不含新人组）；TK部门；TK直播部；BD部；短视频部；客服；产品&店铺运营；AI部；总经办；财务部；深圳团队"],
  ["数据看板汇总", "", "内容生产工厂及子部门（不含新人组）；TK部门；TK直播部；BD部；短视频部；客服；产品&店铺运营；AI部；总经办；财务部；深圳团队"],
  ["小图问答", "", allDepartments],
  ["客服", "", allDepartments],
  ["内容生产工厂", "", "内容生产工厂及子部门（不含新人组）；TK部门；TK直播部；BD部；短视频部；客服；产品&店铺运营；新人组；AI部；总经办；财务部；亚马逊"],
  ["仓储部组功能", "", "仓储部；质检；文员；桌长；库管；AI部；总经办"],
  ["总经办功能", "", "总经办；AI部"],
  ["运营一部功能", "孙洁；侯梁", "运营一部；新人组；AI部；总经办"],
  ["运营二部功能", "孙洁；侯梁", "运营二部；新人组；AI部；总经办"],
  ["运营三部功能", "孙洁；侯梁", "运营三部；新人组；AI部；总经办"],
  ["运营六部功能", "孙洁；侯梁", "运营六部；新人组；AI部；总经办"],
  ["运营七部功能", "孙洁；侯梁；赵瑜", "运营七部；新人组；AI部；总经办"],
  ["采购部功能", "", "采购部；AI部；总经办"],
  ["研发部功能", "", "研发部；AI部；总经办"],
  ["技术部功能", "", "技术部；AI部；总经办"],
  ["视觉设计部功能", "", allDepartments],
  ["摄影部功能", "", "摄影部；AI部；总经办"],
  ["AI部功能", "", "AI部；总经办"],
  ["财务部功能", "", "财务部；AI部；总经办"],
  ["人力行政部功能", "", "人力行政部；AI部；总经办"],
  ["新人组功能", "", "新人组；AI部；总经办"],
  ["深圳功能模块", "", "深圳团队；总经办；AI部；亚马逊"],
  ["脚本生成器", "", "BD部；TK部门；TK直播部；短视频部；AI部；总经办；深圳团队"],
  ["TK达人管理", "", "BD部；TK部门；TK直播部；短视频部；AI部；总经办；深圳团队"],
  ["模特库管理", "", "技术部；AI部；总经办"],
  ["模特排队", "", allDepartments],
  ["管理员功能", "", "总经办；AI部"],
  ["性能监控", "", "AI部；总经办"],
];

const adminUsers = "周俊成；毕景春；陶晓飞；李昌翰；孙军；李春；宋亚倩；王丰慧；陈梦昭";
const partialAdminUsers = "张莉；周俊成；毕景春；陶晓飞；李昌翰；孙军；李春；宋亚倩；王丰慧；陈梦昭";
const special = [
  ["TK汇总看板（全量）", adminUsers, "需同时具备“数据看板汇总”的部门权限"],
  ["TK联营看板（全部联营店铺）", partialAdminUsers, "登录用户；完整管理员同样拥有"],
  ["TK联营看板（店铺82）", "侯梁", "登录用户"],
  ["TK联营看板（店铺88）", "刘俊霞", "登录用户"],
  ["TK联营看板（店铺90）", "孙洁", "登录用户"],
  ["TK联营看板（店铺87）", "刘蓉蓉", "登录用户"],
  ["TK联营看板（店铺89）", "柳琳", "登录用户"],
  ["TK联营看板（店铺91）", "叶雨菲", "登录用户"],
  ["TK联营看板（店铺92）", "刘星辰", "登录用户"],
  ["TK联营看板（店铺93）", "赵璐华", "登录用户"],
  ["TK联营看板（店铺95）", "杨明月", "登录用户"],
  ["TK联营看板（店铺96）", "周雪", "登录用户"],
  ["TK联营看板（店铺106）", "李娜", "登录用户"],
  ["TK联营看板（店铺97）", "郭婷", "登录用户"],
  ["TK联营看板（店铺101）", "侯瑞昕", "登录用户"],
  ["TK联营看板（店铺84）", "大张雯", "登录用户"],
  ["TK联营看板（店铺107）", "郭鑫", "登录用户"],
  ["TK联营看板（店铺108）", "张彦微", "登录用户"],
  ["TK联营看板（店铺109）", "王钰媛", "登录用户"],
  ["TK 82看板", "张莉；周俊成；毕景春；陶晓飞；李昌翰；孙军；李春；宋亚倩；王丰慧；陈梦昭；朱晓禹；侯梁", "登录用户"],
  ["TK 88看板", "张莉；周俊成；毕景春；陶晓飞；李昌翰；孙军；李春；宋亚倩；王丰慧；陈梦昭；朱晓禹；侯梁；刘俊霞；李晓明", "登录用户"],
  ["TK 90看板", "张莉；周俊成；毕景春；陶晓飞；李昌翰；孙军；李春；宋亚倩；王丰慧；陈梦昭；朱晓禹；侯梁；孙洁", "登录用户"],
  ["旧版TK数据看板（全组数据）", adminUsers, "需同时具备“内容生产工厂”的部门权限"],
  ["小图报告历史（全量上传记录）", "陶晓飞；周俊成；毕景春", "小图问答对全体已登录用户开放；其他用户默认仅本人"],
  ["小图报告历史（运营部门范围）", "刘蓉蓉；孙洁；侯梁", "范围：运营一部；运营二部；运营三部；运营六部；运营七部"],
  ["小图报告历史（运营三部范围）", "大张雯", "范围：运营三部"],
  ["小图报告历史（部门负责人范围）", "", "飞书部门负责人（leader_user_id）；范围：所负责部门成员"],
  ["小图报告历史（权限调试视角）", "周俊成", "可切换本人、全量、运营部门受限视角"],
  ["创新委员会打分", "周俊成；陶晓飞；孙军；毕景春；李昌瀚；蔡晶；韩雅俊；孙洁；陈子烨", "创新提案管理对全体已登录用户开放"],
  ["创新之星内容管理", "韩雅俊", "AI部成员也拥有"],
  ["图片工具生成历史（查看全部账号）", "周俊成", "视觉设计部功能对全体已登录用户开放；其他用户仅看本人历史"],
];

const rows = [...core, ...special];
rows.sort((a, b) => (a[2] || "").localeCompare(b[2] || "", "zh-CN") || a[0].localeCompare(b[0], "zh-CN"));

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("权限表");
sheet.showGridLines = false;
sheet.getRange("A1:C1").values = [["gongneng", "yonghu", "bumen"]];
sheet.getRange(`A2:C${rows.length + 1}`).values = rows;

const used = sheet.getRange(`A1:C${rows.length + 1}`);
used.format.font = { name: "Microsoft YaHei", size: 10, color: "#1F2937" };
used.format.verticalAlignment = "center";
used.format.wrapText = true;
used.format.borders = {
  insideHorizontal: { style: "thin", color: "#E5E7EB" },
  bottom: { style: "thin", color: "#D1D5DB" },
};

const header = sheet.getRange("A1:C1");
header.format = {
  fill: "#1F4E78",
  font: { name: "Microsoft YaHei", size: 11, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  rowHeight: 28,
  borders: { preset: "all", style: "thin", color: "#1F4E78" },
};

sheet.getRange(`A2:A${rows.length + 1}`).format.font = { name: "Microsoft YaHei", size: 10, bold: true, color: "#1F2937" };
sheet.getRange(`A2:C${core.length + 1}`).format.fill = "#F8FAFC";
sheet.getRange(`B2:B${rows.length + 1}`).conditionalFormats.add("notContainsBlanks", {
  format: { fill: "#FFF4CC", font: { color: "#7C4A03" } },
});

sheet.getRange(`A1:A${rows.length + 1}`).format.columnWidth = 31;
sheet.getRange(`B1:B${rows.length + 1}`).format.columnWidth = 58;
sheet.getRange(`C1:C${rows.length + 1}`).format.columnWidth = 80;
sheet.getRange(`A2:C${rows.length + 1}`).format.autofitRows();
sheet.getRange(`A2:C${rows.length + 1}`).format.rowHeight = 34;
sheet.freezePanes.freezeRows(1);
const table = sheet.tables.add(`A1:C${rows.length + 1}`, true, "PermissionInventoryTable");
table.style = "TableStyleMedium2";
table.showBandedRows = false;
table.showFilterButton = true;

const preview = await workbook.render({
  sheetName: "权限表",
  range: `A1:C25`,
  scale: 1.4,
  format: "png",
});
await fs.writeFile(`${outputDir}/permission_inventory_preview.png`, new Uint8Array(await preview.arrayBuffer()));

const previewBottom = await workbook.render({
  sheetName: "权限表",
  range: `A26:C${rows.length + 1}`,
  scale: 1.2,
  format: "png",
});
await fs.writeFile(`${outputDir}/permission_inventory_preview_bottom.png`, new Uint8Array(await previewBottom.arrayBuffer()));

const inspect = await workbook.inspect({
  kind: "table",
  range: `权限表!A1:C${rows.length + 1}`,
  include: "values,formulas",
  tableMaxRows: 12,
  tableMaxCols: 3,
  maxChars: 7000,
});
console.log(inspect.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(`${outputDir}/权限汇总表_20260813.xlsx`);

console.log(JSON.stringify({ rowCount: rows.length, coreCount: core.length, specialCount: special.length }, null, 2));
