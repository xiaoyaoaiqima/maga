import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const csvPath = "/Users/luxifa/maga/outputs/a2_reiyu_history_delivery_300_20260724/A2礼遇_历史可用300篇_集罐70其他30.csv";
const previewPath = "/Users/luxifa/maga/tmp/a2_reiyu_history_delivery_300_20260724/final_csv_preview.png";
const csvText = (await fs.readFile(csvPath, "utf8")).replace(/^\uFEFF/, "");
const workbook = await Workbook.fromCSV(csvText, { sheetName: "A2礼遇" });
const sheet = workbook.worksheets.getItem("A2礼遇");
sheet.getRange("A1:A7").format.columnWidth = 28;
sheet.getRange("B1:B7").format.columnWidth = 32;
sheet.getRange("C1:C7").format.columnWidth = 90;
sheet.getRange("D1:D7").format.columnWidth = 14;
sheet.getRange("A1:D7").format.wrapText = true;
sheet.getRange("A1:D1").format = {
  fill: "#E2E8F0",
  font: { bold: true, color: "#0F172A" },
};
const inspection = await workbook.inspect({
  kind: "table",
  range: "A2礼遇!A1:D7",
  include: "values",
  tableMaxRows: 7,
  tableMaxCols: 4,
  maxChars: 5000,
});
const preview = await workbook.render({
  sheetName: "A2礼遇",
  range: "A1:D7",
  scale: 1,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
console.log(inspection.ndjson);
