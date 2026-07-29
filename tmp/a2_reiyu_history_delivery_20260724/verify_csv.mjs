import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const csvPath = "/Users/luxifa/maga/outputs/a2_reiyu_history_delivery_20260724/A2礼遇_历史可用200篇_集罐70其他30.csv";
const previewPath = "/Users/luxifa/maga/tmp/a2_reiyu_history_delivery_20260724/final_csv_preview.png";
const csvText = await fs.readFile(csvPath, "utf8");
const workbook = await Workbook.fromCSV(csvText, { sheetName: "A2礼遇" });
const inspection = await workbook.inspect({
  kind: "table",
  range: "A2礼遇!A1:D8",
  include: "values",
  tableMaxRows: 8,
  tableMaxCols: 4,
  maxChars: 5000,
});
const preview = await workbook.render({
  sheetName: "A2礼遇",
  range: "A1:D8",
  scale: 1,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
console.log(inspection.ndjson);
