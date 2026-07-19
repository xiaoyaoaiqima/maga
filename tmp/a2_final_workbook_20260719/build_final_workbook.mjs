import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "/Users/luxifa/maga";
const sourcePath = path.join(root, "tmp/a2_final_selection_20260719.json");
const outputDir = path.join(root, "outputs/a2_four_categories_final_20260719");
const outputPath = path.join(outputDir, "a2_四类评论_人工筛选相似度过滤_各105条_20260719.xlsx");
const previewDir = path.join(root, "tmp/a2_final_workbook_20260719/previews");
const data = JSON.parse(await fs.readFile(sourcePath, "utf8"));

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const categorySheets = [
  ["有货-直给", "有货-直给"],
  ["批批检、批次报告、检测透明", "批批检-报告透明"],
  ["罐底扫码、三方质检报告", "罐底扫码-三方质检"],
  ["会员权益、集罐换奶粉、抽奖、礼遇升级", "会员权益"],
];

const colors = {
  dark: "#174A5B",
  header: "#2F7588",
  light: "#DDEBF0",
  line: "#D7E2E6",
  text: "#17323A",
  muted: "#52666E",
  warning: "#FFF3CD",
  falseFill: "#FDE2E2",
};

const workbook = Workbook.create();
const summary = workbook.worksheets.add("交付汇总");
const allSheet = workbook.worksheets.add("全部评论");
for (const [, sheetName] of categorySheets) workbook.worksheets.add(sheetName);
const rejectedSheet = workbook.worksheets.add("筛选记录");

function styleTitle(sheet, title, subtitle, endColumn) {
  sheet.showGridLines = false;
  sheet.getRange(`A1:${endColumn}1`).merge();
  sheet.getRange("A1").values = [[title]];
  sheet.getRange(`A1:${endColumn}1`).format = {
    fill: colors.dark,
    font: { bold: true, color: "#FFFFFF", fontSize: 16 },
    rowHeight: 30,
    verticalAlignment: "center",
  };
  sheet.getRange(`A2:${endColumn}2`).merge();
  sheet.getRange("A2").values = [[subtitle]];
  sheet.getRange(`A2:${endColumn}2`).format = {
    fill: colors.light,
    font: { color: colors.text, italic: true, fontSize: 10 },
    wrapText: true,
    rowHeight: 34,
    verticalAlignment: "center",
  };
}

function styleHeader(range) {
  range.format = {
    fill: colors.header,
    font: { bold: true, color: "#FFFFFF", fontSize: 10 },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: "#B7C9CF" },
    rowHeight: 28,
  };
}

function sourceLabel(source) {
  return source === "old_358" ? "旧358条" : "新多样批次";
}

function writeCommentSheet(sheetName, category, items, tableName) {
  const sheet = workbook.worksheets.getItem(sheetName);
  styleTitle(
    sheet,
    `A2 四类评论｜${category}｜人工筛选后 ${items.length} 条`,
    "已完成业务人工筛选、完全去重和类内相似度过滤；30字仅作生成参考，轻微超字不作为拒绝条件。",
    "J",
  );
  const headers = [["序号", "评论正文", "来源", "批次ID", "批内序号", "业务规则", "规则ID", "字数", "最大相似度", "机器通过"]];
  sheet.getRange("A4:J4").values = headers;
  styleHeader(sheet.getRange("A4:J4"));
  const rows = items.map((item) => [
    item.delivery_no,
    item.body,
    sourceLabel(item.source),
    item.batch_id,
    item.item_no,
    item.business_rule,
    item.rule_id,
    item.body.length,
    item.max_similarity_to_selected,
    item.machine_hard_pass ? "是" : "否（人工复核保留）",
  ]);
  if (rows.length) {
    const endRow = 4 + rows.length;
    sheet.getRange(`A5:J${endRow}`).values = rows;
    sheet.getRange(`A5:J${endRow}`).format = {
      font: { color: colors.text, fontSize: 10 },
      verticalAlignment: "center",
      borders: {
        insideHorizontal: { style: "thin", color: colors.line },
      },
    };
    sheet.getRange(`B5:B${endRow}`).format.wrapText = true;
    sheet.getRange(`A5:A${endRow}`).format.numberFormat = "0";
    sheet.getRange(`D5:E${endRow}`).format.numberFormat = "0";
    sheet.getRange(`H5:H${endRow}`).format.numberFormat = "0";
    sheet.getRange(`I5:I${endRow}`).format.numberFormat = "0.0000";
    sheet.getRange(`H5:H${endRow}`).conditionalFormats.add("cellIs", {
      operator: "greaterThan",
      formula: 30,
      format: { fill: colors.warning, font: { color: "#7A5B00" } },
    });
    sheet.getRange(`J5:J${endRow}`).conditionalFormats.add("containsText", {
      text: "否",
      format: { fill: colors.falseFill, font: { color: "#8A1C1C" } },
    });
    const table = sheet.tables.add(`A4:J${endRow}`, true, tableName);
    table.style = "TableStyleMedium2";
  }
  sheet.freezePanes.freezeRows(4);
  sheet.getRange("A:A").format.columnWidth = 7;
  sheet.getRange("B:B").format.columnWidth = 48;
  sheet.getRange("C:C").format.columnWidth = 13;
  sheet.getRange("D:E").format.columnWidth = 10;
  sheet.getRange("F:F").format.columnWidth = 24;
  sheet.getRange("G:G").format.columnWidth = 16;
  sheet.getRange("H:H").format.columnWidth = 8;
  sheet.getRange("I:I").format.columnWidth = 12;
  sheet.getRange("J:J").format.columnWidth = 17;
}

const allItems = [];
for (const [category] of categorySheets) {
  allItems.push(...data.categories[category].items.map((item) => ({ ...item, category })));
}

styleTitle(
  allSheet,
  `A2 四类评论｜最终交付 ${allItems.length} 条`,
  "四类各105条；来源包含旧358条人工保留项与本轮多样化补量。",
  "K",
);
allSheet.getRange("A4:K4").values = [["类别", "序号", "评论正文", "来源", "批次ID", "批内序号", "业务规则", "规则ID", "字数", "最大相似度", "机器通过"]];
styleHeader(allSheet.getRange("A4:K4"));
const allRows = allItems.map((item) => [
  item.category,
  item.delivery_no,
  item.body,
  sourceLabel(item.source),
  item.batch_id,
  item.item_no,
  item.business_rule,
  item.rule_id,
  item.body.length,
  item.max_similarity_to_selected,
  item.machine_hard_pass ? "是" : "否（人工复核保留）",
]);
allSheet.getRange(`A5:K${4 + allRows.length}`).values = allRows;
allSheet.getRange(`A5:K${4 + allRows.length}`).format = {
  font: { color: colors.text, fontSize: 10 },
  verticalAlignment: "center",
  borders: { insideHorizontal: { style: "thin", color: colors.line } },
};
allSheet.getRange(`C5:C${4 + allRows.length}`).format.wrapText = true;
allSheet.getRange(`B5:B${4 + allRows.length}`).format.numberFormat = "0";
allSheet.getRange(`E5:F${4 + allRows.length}`).format.numberFormat = "0";
allSheet.getRange(`I5:I${4 + allRows.length}`).format.numberFormat = "0";
allSheet.getRange(`J5:J${4 + allRows.length}`).format.numberFormat = "0.0000";
allSheet.getRange(`I5:I${4 + allRows.length}`).conditionalFormats.add("cellIs", {
  operator: "greaterThan",
  formula: 30,
  format: { fill: colors.warning, font: { color: "#7A5B00" } },
});
const allTable = allSheet.tables.add(`A4:K${4 + allRows.length}`, true, "AllFinalComments");
allTable.style = "TableStyleMedium2";
allSheet.freezePanes.freezeRows(4);
allSheet.getRange("A:A").format.columnWidth = 30;
allSheet.getRange("B:B").format.columnWidth = 7;
allSheet.getRange("C:C").format.columnWidth = 48;
allSheet.getRange("D:D").format.columnWidth = 13;
allSheet.getRange("E:F").format.columnWidth = 10;
allSheet.getRange("G:G").format.columnWidth = 24;
allSheet.getRange("H:H").format.columnWidth = 16;
allSheet.getRange("I:I").format.columnWidth = 8;
allSheet.getRange("J:J").format.columnWidth = 12;
allSheet.getRange("K:K").format.columnWidth = 17;

categorySheets.forEach(([category, sheetName], index) => {
  writeCommentSheet(sheetName, category, data.categories[category].items, `CategoryComments${index + 1}`);
});

styleTitle(
  rejectedSheet,
  `A2 四类评论｜筛选记录 ${data.rejected.length} 条`,
  "记录业务人工筛选、完全重复和相似度过滤原因；用于追溯，不属于最终交付正文。",
  "H",
);
rejectedSheet.getRange("A4:H4").values = [["类别", "来源", "批次ID", "批内序号", "业务规则", "评论正文", "拒绝原因", "机器通过"]];
styleHeader(rejectedSheet.getRange("A4:H4"));
const rejectedRows = data.rejected.map((item) => [
  item.category,
  sourceLabel(item.source),
  item.batch_id,
  item.item_no,
  item.business_rule,
  item.body,
  (item.rejection_reasons || []).join("；"),
  item.machine_hard_pass ? "是" : "否",
]);
if (rejectedRows.length) {
  const endRow = 4 + rejectedRows.length;
  rejectedSheet.getRange(`A5:H${endRow}`).values = rejectedRows;
  rejectedSheet.getRange(`A5:H${endRow}`).format = {
    font: { color: colors.text, fontSize: 10 },
    verticalAlignment: "top",
    borders: { insideHorizontal: { style: "thin", color: colors.line } },
  };
  rejectedSheet.getRange(`F5:G${endRow}`).format.wrapText = true;
  rejectedSheet.getRange(`C5:D${endRow}`).format.numberFormat = "0";
  const table = rejectedSheet.tables.add(`A4:H${endRow}`, true, "RejectedComments");
  table.style = "TableStyleMedium4";
}
rejectedSheet.freezePanes.freezeRows(4);
rejectedSheet.getRange("A:A").format.columnWidth = 30;
rejectedSheet.getRange("B:B").format.columnWidth = 13;
rejectedSheet.getRange("C:D").format.columnWidth = 10;
rejectedSheet.getRange("E:E").format.columnWidth = 24;
rejectedSheet.getRange("F:F").format.columnWidth = 48;
rejectedSheet.getRange("G:G").format.columnWidth = 46;
rejectedSheet.getRange("H:H").format.columnWidth = 10;

styleTitle(
  summary,
  "A2 四类评论｜人工筛选与相似度过滤交付",
  "最终420条，四类各105条。30字为生成参考，不作硬拦；人工优先剔除业务越界、病句、虚构结果和高相似表达。",
  "I",
);
summary.getRange("A4:I4").values = [["类别", "最终条数", "旧358保留", "新多样批次", "人工/相似度剔除", "平均字数", "超过30字", "最大类内相似度", "结论"]];
styleHeader(summary.getRange("A4:I4"));

const summaryRows = categorySheets.map(([category, sheetName]) => [category, null, null, null, null, null, null, null, "可交付"]);
summary.getRange("A5:I8").values = summaryRows;
categorySheets.forEach(([category, sheetName], index) => {
  const row = 5 + index;
  const endRow = 4 + data.categories[category].items.length;
  summary.getRange(`B${row}`).formulas = [[`=COUNTA('${sheetName}'!$B$5:$B$${endRow})`]];
  summary.getRange(`C${row}`).formulas = [[`=COUNTIF('${sheetName}'!$C$5:$C$${endRow},"旧358条")`]];
  summary.getRange(`D${row}`).formulas = [[`=COUNTIF('${sheetName}'!$C$5:$C$${endRow},"新多样批次")`]];
  summary.getRange(`E${row}`).formulas = [[`=COUNTIF('筛选记录'!$A$5:$A$${4 + rejectedRows.length},A${row})`]];
  summary.getRange(`F${row}`).formulas = [[`=AVERAGE('${sheetName}'!$H$5:$H$${endRow})`]];
  summary.getRange(`G${row}`).formulas = [[`=COUNTIF('${sheetName}'!$H$5:$H$${endRow},">30")`]];
  summary.getRange(`H${row}`).formulas = [[`=MAX('${sheetName}'!$I$5:$I$${endRow})`]];
});
summary.getRange("A9:I9").values = [["合计", null, null, null, null, null, null, null, ""]];
summary.getRange("B9").formulas = [["=SUM(B5:B8)"]];
summary.getRange("C9").formulas = [["=SUM(C5:C8)"]];
summary.getRange("D9").formulas = [["=SUM(D5:D8)"]];
summary.getRange("E9").formulas = [["=SUM(E5:E8)"]];
summary.getRange("F9").formulas = [["=AVERAGE(F5:F8)"]];
summary.getRange("G9").formulas = [["=SUM(G5:G8)"]];
summary.getRange("H9").formulas = [["=MAX(H5:H8)"]];
summary.getRange("A5:I8").format = {
  font: { color: colors.text, fontSize: 10 },
  verticalAlignment: "center",
  borders: { insideHorizontal: { style: "thin", color: colors.line } },
};
summary.getRange("A9:I9").format = {
  fill: colors.light,
  font: { bold: true, color: colors.dark },
  borders: { bottom: { style: "double", color: "#7A9DA7" } },
};
summary.getRange("B5:E9").format.numberFormat = "0";
summary.getRange("F5:F9").format.numberFormat = "0.0";
summary.getRange("G5:G9").format.numberFormat = "0";
summary.getRange("H5:H9").format.numberFormat = "0.0000";
summary.getRange("A12:I12").merge();
summary.getRange("A12").values = [["筛选口径"]];
summary.getRange("A12:I12").format = { fill: colors.header, font: { bold: true, color: "#FFFFFF" }, rowHeight: 24 };
summary.getRange("A13:I17").merge(true);
summary.getRange("A13:A17").values = [
  ["1. 旧358条只保留原机器通过项，再进行人工业务筛选。"],
  ["2. 新多样批次允许机器因批次开头配额未通过的单条进入人工复核，但最终仍需过业务和相似度筛选。"],
  ["3. 严格校正品牌大小写：品牌/产品统一写a2，只有A2蛋白可大写。"],
  ["4. 30字不是硬门槛；只把明显长段、残句、病句、事实混写和虚构结果剔除。"],
  ["5. 类内进行完全去重、开头频次限制和2-gram Jaccard相似度过滤。"],
];
summary.getRange("A13:I17").format = { fill: "#F7FAFB", font: { color: colors.muted, fontSize: 10 }, wrapText: true, rowHeight: 24 };
summary.freezePanes.freezeRows(4);
summary.getRange("A:A").format.columnWidth = 34;
summary.getRange("B:E").format.columnWidth = 13;
summary.getRange("F:H").format.columnWidth = 14;
summary.getRange("I:I").format.columnWidth = 12;

const summaryInspect = await workbook.inspect({
  kind: "table",
  range: "交付汇总!A1:I17",
  include: "values,formulas",
  tableMaxRows: 20,
  tableMaxCols: 10,
  maxChars: 8000,
});
console.log(summaryInspect.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 200 },
  summary: "final formula error scan",
  maxChars: 4000,
});
console.log(errors.ndjson);

const previewTargets = [
  ["交付汇总", "A1:I17"],
  ["全部评论", "A1:K18"],
  ["有货-直给", "A1:J18"],
  ["批批检-报告透明", "A1:J18"],
  ["罐底扫码-三方质检", "A1:J18"],
  ["会员权益", "A1:J18"],
  ["筛选记录", "A1:H18"],
];
for (const [sheetName, range] of previewTargets) {
  const blob = await workbook.render({ sheetName, range, scale: 1.25, format: "png" });
  const safeName = sheetName.replaceAll("/", "-");
  await fs.writeFile(path.join(previewDir, `${safeName}.png`), new Uint8Array(await blob.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath, previewDir, selected: allItems.length, rejected: rejectedRows.length }));
