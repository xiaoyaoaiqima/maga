import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const inputPath = "/Users/luxifa/Downloads/PG UGC正向词调整后模型 - ✅🤖礼遇预交付-500篇（0723）.csv";
const outputPath = "/Users/luxifa/maga/tmp/a2_reiyu_500_audit_20260723/input_rows.json";

const csvText = await fs.readFile(inputPath, "utf8");
const workbook = await Workbook.fromCSV(csvText, { sheetName: "Articles" });
const overview = await workbook.inspect({
  kind: "workbook,sheet,region",
  sheetId: "Articles",
  range: "A1:Z8",
  maxChars: 8000,
  tableMaxRows: 8,
  tableMaxCols: 26,
  tableMaxCellChars: 240,
});
const sheet = workbook.worksheets.getItem("Articles");
const usedRange = sheet.getUsedRange(true);
const values = usedRange.values;
await fs.writeFile(outputPath, JSON.stringify(values), "utf8");
console.log(JSON.stringify({
  overview: overview.ndjson,
  rowCount: values.length,
  columnCount: values[0]?.length ?? 0,
  headers: values[0] ?? [],
  outputPath,
}, null, 2));
