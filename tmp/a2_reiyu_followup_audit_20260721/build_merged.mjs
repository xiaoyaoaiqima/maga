import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const workDir = "/Users/luxifa/maga/tmp/a2_reiyu_followup_audit_20260721";
const outputDir = "/Users/luxifa/maga/outputs/a2_reiyu_followup_audit_20260721";
const outputPath = `${outputDir}/A2礼遇_合并可用492篇.csv`;

const remaining = JSON.parse(await fs.readFile(`${workDir}/remaining_processed.json`, "utf8"))
  .filter((item) => item.final_status === "usable")
  .map((item) => ({
    contentId: "",
    title: item.title,
    body: item.body,
    category: item.category,
  }));

const newItems = JSON.parse(await fs.readFile(`${workDir}/new_processed.json`, "utf8"))
  .filter((item) => item.final_status === "usable")
  .map((item) => ({
    contentId: item["Content ID"],
    title: item.title,
    body: item.body,
    category: "其他",
  }));

const articles = [...remaining, ...newItems];
if (remaining.length !== 294 || newItems.length !== 198 || articles.length !== 492) {
  throw new Error(`row count mismatch: ${remaining.length} + ${newItems.length}`);
}

const bodySet = new Set(articles.map((item) => item.body));
if (bodySet.size !== articles.length) throw new Error("duplicate body found");
const populatedIds = articles.map((item) => item.contentId).filter(Boolean);
if (new Set(populatedIds).size !== populatedIds.length) throw new Error("duplicate content_id found");

const matrix = [
  ["content_id", "标题", "正文", "分类"],
  ...articles.map((item) => [item.contentId, item.title, item.body, item.category]),
];

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("合并可用492篇");
sheet.getRangeByIndexes(0, 0, matrix.length, matrix[0].length).values = matrix;
sheet.freezePanes.freezeRows(1);
sheet.getRange("A1:D1").format = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF" },
};
sheet.getRangeByIndexes(0, 0, 5, 4).format.wrapText = true;
sheet.getRangeByIndexes(0, 0, matrix.length, 1).format.columnWidthPx = 210;
sheet.getRangeByIndexes(0, 1, matrix.length, 1).format.columnWidthPx = 230;
sheet.getRangeByIndexes(0, 2, matrix.length, 1).format.columnWidthPx = 620;
sheet.getRangeByIndexes(0, 3, matrix.length, 1).format.columnWidthPx = 110;

const preview = await workbook.render({
  sheetName: "合并可用492篇",
  range: "A1:D5",
  scale: 1,
  format: "png",
});
await fs.writeFile(`${workDir}/merged_preview.png`, new Uint8Array(await preview.arrayBuffer()));

function csvCell(value) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

const values = sheet.getUsedRange(true).values;
const csvText = `\uFEFF${values.map((row) => row.map(csvCell).join(",")).join("\r\n")}\r\n`;
await fs.mkdir(outputDir, { recursive: true });
await fs.writeFile(outputPath, csvText, "utf8");

const verified = await Workbook.fromCSV(csvText.replace(/^\uFEFF/, ""), { sheetName: "验证" });
const verifyValues = verified.worksheets.getItem("验证").getUsedRange(true).values;
if (verifyValues.length !== 493 || verifyValues[0]?.length !== 4) {
  throw new Error(`CSV verification failed: ${verifyValues.length}x${verifyValues[0]?.length || 0}`);
}

console.log(JSON.stringify({
  outputPath,
  articleCount: articles.length,
  remainingWithoutContentId: remaining.length,
  populatedContentIds: populatedIds.length,
  categoryCounts: articles.reduce((counts, item) => {
    counts[item.category] = (counts[item.category] || 0) + 1;
    return counts;
  }, {}),
  verifyShape: [verifyValues.length, verifyValues[0].length],
}, null, 2));
