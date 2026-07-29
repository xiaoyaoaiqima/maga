import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const inputPath = "/Users/luxifa/Downloads/PG UGC正向词调整后模型 - 礼遇生文备用 (1).csv";
const outputPath = "/Users/luxifa/maga/tmp/a2_reiyu_backup_audit_20260723/rows.json";

const csvText = await fs.readFile(inputPath, "utf8");
const workbook = await Workbook.fromCSV(csvText, { sheetName: "Articles" });
const sheet = workbook.worksheets.getItemAt(0);
const used = sheet.getUsedRange(true);
await fs.writeFile(outputPath, JSON.stringify(used.values, null, 2));

const preview = await workbook.inspect({
  kind: "table",
  sheetId: "Articles",
  range: "A1:D6",
  include: "values",
  tableMaxRows: 6,
  tableMaxCols: 4,
  maxChars: 5000,
});
console.log(preview.ndjson);
console.log(JSON.stringify({ rowCount: used.values.length, columnCount: used.values[0]?.length ?? 0 }));
