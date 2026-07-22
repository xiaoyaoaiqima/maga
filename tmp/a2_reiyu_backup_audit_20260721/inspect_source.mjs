import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const inputPath = "/Users/luxifa/Downloads/礼遇生文备用.csv";
const outputDir = "/Users/luxifa/maga/tmp/a2_reiyu_backup_audit_20260721";
const extractedPath = `${outputDir}/source_rows.json`;

const csvText = (await fs.readFile(inputPath, "utf8")).replace(/^\uFEFF/, "");
const workbook = await Workbook.fromCSV(csvText, { sheetName: "礼遇生文备用" });
const sheet = workbook.worksheets.getItem("礼遇生文备用");
const values = sheet.getUsedRange(true).values;
const inspection = await workbook.inspect({
  kind: "table",
  range: `礼遇生文备用!A1:${String.fromCharCode(64 + Math.min(values[0]?.length || 1, 26))}${Math.min(values.length, 8)}`,
  include: "values",
  tableMaxRows: 8,
  tableMaxCols: 12,
  tableMaxCellChars: 240,
  maxChars: 12000,
});

await fs.mkdir(outputDir, { recursive: true });
await fs.writeFile(extractedPath, JSON.stringify({ values }, null, 2), "utf8");

console.log(JSON.stringify({
  rowCountIncludingHeader: values.length,
  dataRows: Math.max(0, values.length - 1),
  columns: values[0]?.length || 0,
  headers: values[0] || [],
  extractedPath,
}, null, 2));
console.log(inspection.ndjson);
