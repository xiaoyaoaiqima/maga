import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "/Users/luxifa/maga/outputs/a2_four_categories_20260719_passed";
const outputPath = `${outputDir}/a2_四类评论_本轮机器通过358条_20260719.xlsx`;

const categories = [
  { name: "有货-直给", sheetName: "有货-直给", batchId: 657 },
  { name: "批批检、批次报告、检测透明", sheetName: "批批检-报告透明", batchId: 658 },
  { name: "罐底扫码、三方质检报告", sheetName: "罐底扫码-三方质检", batchId: 656 },
  { name: "会员权益、集罐换奶粉、抽奖、礼遇升级", sheetName: "会员权益", batchId: 655 },
];

async function fetchReport(batchId) {
  const response = await fetch(`http://127.0.0.1:5100/api/v1/content-agent/batches/${batchId}/report`);
  if (!response.ok) {
    throw new Error(`batch ${batchId} report failed: ${response.status}`);
  }
  const payload = await response.json();
  return payload.data;
}

const reports = new Map();
for (const category of categories) {
  reports.set(category.batchId, await fetchReport(category.batchId));
}

const categoryRows = categories.map((category) => {
  const report = reports.get(category.batchId);
  const passed = (report.items || []).filter(
    (item) => item && item.status === "generated" && item.hard_pass === true && String(item.body || "").trim(),
  );
  return {
    ...category,
    generatedCount: Number(report.summary?.generated_count || 0),
    passed,
  };
});

const workbook = Workbook.create();
const summarySheet = workbook.worksheets.add("质检汇总");
const allSheet = workbook.worksheets.add("全部通过");
for (const category of categoryRows) workbook.worksheets.add(category.sheetName);

const titleFormat = {
  fill: "#174A5B",
  font: { bold: true, color: "#FFFFFF", size: 16 },
  horizontalAlignment: "left",
  verticalAlignment: "center",
};
const subtitleFormat = {
  fill: "#DDEBF0",
  font: { color: "#244A57", italic: true },
  wrapText: true,
  verticalAlignment: "center",
};
const headerFormat = {
  fill: "#2F7588",
  font: { bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "outside", style: "thin", color: "#B7C9CF" },
};

function styleDetailSheet(sheet, title, rowCount) {
  sheet.showGridLines = false;
  sheet.mergeCells("A1:H1");
  sheet.getRange("A1:H1").format = titleFormat;
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A1:H1").format.rowHeightPx = 34;
  sheet.mergeCells("A2:H2");
  sheet.getRange("A2:H2").format = subtitleFormat;
  sheet.getRange("A2").values = [["仅导出本轮 hard_pass=true 的机器通过项；未进行额外人工筛选或相似度过滤。"]];
  sheet.getRange("A2:H2").format.rowHeightPx = 30;
  sheet.getRange("A4:H4").format = headerFormat;
  sheet.getRange("A4:H4").format.rowHeightPx = 28;
  sheet.getRange(`A5:H${Math.max(5, rowCount + 4)}`).format = {
    verticalAlignment: "center",
    borders: { insideHorizontal: { style: "thin", color: "#E2E8EA" } },
  };
  sheet.getRange(`F5:F${Math.max(5, rowCount + 4)}`).format.wrapText = true;
  sheet.getRange(`H5:H${Math.max(5, rowCount + 4)}`).format.wrapText = true;
  sheet.getRange("A:A").format.columnWidthPx = 64;
  sheet.getRange("B:B").format.columnWidthPx = 80;
  sheet.getRange("C:C").format.columnWidthPx = 82;
  sheet.getRange("D:D").format.columnWidthPx = 90;
  sheet.getRange("E:E").format.columnWidthPx = 180;
  sheet.getRange("F:F").format.columnWidthPx = 480;
  sheet.getRange("G:G").format.columnWidthPx = 82;
  sheet.getRange("H:H").format.columnWidthPx = 260;
  sheet.freezePanes.freezeRows(4);
}

function rowsForCategory(category) {
  return category.passed.map((item, index) => [
    index + 1,
    category.batchId,
    Number(item.item_no || 0),
    Number(item.item_id || 0),
    String(item.title || ""),
    String(item.body || "").trim(),
    true,
    String(item.rewrite_reason || ""),
  ]);
}

const headers = ["序号", "批次ID", "批内序号", "明细ID", "业务规则", "评论正文", "hard_pass", "改写说明"];
const allRows = [];
for (const category of categoryRows) {
  const sheet = workbook.worksheets.getItem(category.sheetName);
  const rows = rowsForCategory(category);
  styleDetailSheet(sheet, `${category.name}｜机器通过 ${rows.length} 条`, rows.length);
  sheet.getRange("A4:H4").values = [headers];
  if (rows.length) sheet.getRange(`A5:H${rows.length + 4}`).values = rows;
  const table = sheet.tables.add(`A4:H${rows.length + 4}`, true, `Passed_${category.batchId}`);
  table.style = "TableStyleMedium2";
  allRows.push(...rows.map((row) => [category.name, ...row.slice(1)]));
}

styleDetailSheet(allSheet, `A2 四类评论｜本轮机器通过 ${allRows.length} 条`, allRows.length);
allSheet.getRange("A4:H4").values = [["类别", "批次ID", "批内序号", "明细ID", "业务规则", "评论正文", "hard_pass", "改写说明"]];
if (allRows.length) allSheet.getRange(`A5:H${allRows.length + 4}`).values = allRows;
const allTable = allSheet.tables.add(`A4:H${allRows.length + 4}`, true, "AllPassedComments");
allTable.style = "TableStyleMedium2";

summarySheet.showGridLines = false;
summarySheet.mergeCells("A1:F1");
summarySheet.getRange("A1:F1").format = titleFormat;
summarySheet.getRange("A1").values = [["A2 四类评论｜本轮机器通过导出"]];
summarySheet.getRange("A1:F1").format.rowHeightPx = 36;
summarySheet.mergeCells("A2:F2");
summarySheet.getRange("A2:F2").format = subtitleFormat;
summarySheet.getRange("A2").values = [["口径：四个新批次中 status=generated 且 hard_pass=true；不含机器未通过项。"]];
summarySheet.getRange("A4:F4").values = [["类别", "批次ID", "生成数", "机器通过数", "未通过数", "通过率"]];
summarySheet.getRange("A4:F4").format = headerFormat;

categoryRows.forEach((category, index) => {
  const row = index + 5;
  summarySheet.getRange(`A${row}:C${row}`).values = [[category.name, category.batchId, category.generatedCount]];
  summarySheet.getRange(`D${row}`).formulas = [[`=COUNTA('${category.sheetName}'!$F$5:$F$${category.passed.length + 4})`]];
  summarySheet.getRange(`E${row}`).formulas = [[`=C${row}-D${row}`]];
  summarySheet.getRange(`F${row}`).formulas = [[`=D${row}/C${row}`]];
});
summarySheet.getRange("A9:C9").values = [["合计", null, null]];
summarySheet.getRange("C9").formulas = [["=SUM(C5:C8)"]];
summarySheet.getRange("D9").formulas = [["=SUM(D5:D8)"]];
summarySheet.getRange("E9").formulas = [["=SUM(E5:E8)"]];
summarySheet.getRange("F9").formulas = [["=D9/C9"]];
summarySheet.getRange("A9:F9").format = {
  fill: "#DDEBF0",
  font: { bold: true, color: "#174A5B" },
  borders: { preset: "doubleBottom", style: "medium", color: "#7A9DA7" },
};
summarySheet.getRange("B5:E9").format.numberFormat = "#,##0";
summarySheet.getRange("F5:F9").format.numberFormat = "0.0%";
summarySheet.getRange("A:A").format.columnWidthPx = 330;
summarySheet.getRange("B:E").format.columnWidthPx = 100;
summarySheet.getRange("F:F").format.columnWidthPx = 92;
summarySheet.freezePanes.freezeRows(4);

await fs.mkdir(outputDir, { recursive: true });

const summaryInspect = await workbook.inspect({
  kind: "table",
  range: "质检汇总!A1:F9",
  include: "values,formulas",
  tableMaxRows: 12,
  tableMaxCols: 8,
  maxChars: 5000,
});
console.log(summaryInspect.ndjson);

const errorInspect = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log(errorInspect.ndjson);

for (const sheetName of ["质检汇总", "全部通过", ...categoryRows.map((item) => item.sheetName)]) {
  const preview = await workbook.render({
    sheetName,
    range: sheetName === "质检汇总" ? "A1:F9" : "A1:H14",
    scale: 1,
    format: "png",
  });
  const safeName = sheetName.replaceAll(/[\\/:*?"<>|]/g, "_");
  await fs.writeFile(`${outputDir}/preview_${safeName}.png`, new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath, totalPassed: allRows.length, counts: categoryRows.map((item) => [item.name, item.passed.length]) }));
