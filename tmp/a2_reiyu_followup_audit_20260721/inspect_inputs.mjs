import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const workDir = "/Users/luxifa/maga/tmp/a2_reiyu_followup_audit_20260721";
const xlsxPath = "/Users/luxifa/Downloads/文章池导出_2026-07-21 (4).xlsx";
const remainingPath = "/Users/luxifa/maga/outputs/a2_reiyu_backup_audit_20260721/A2礼遇_剩余301篇_含问题.csv";

await fs.mkdir(workDir, { recursive: true });

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(xlsxPath));
const workbookInspection = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 12000,
  tableMaxRows: 6,
  tableMaxCols: 12,
  tableMaxCellChars: 180,
});
const sheets = [];
for (const sheet of workbook.worksheets.items) {
  const values = sheet.getUsedRange(true)?.values || [];
  sheets.push({ name: sheet.name, values });
  if (values.length) {
    const preview = await workbook.render({
      sheetName: sheet.name,
      range: `A1:${String.fromCharCode(64 + Math.min(values[0].length, 26))}${Math.min(values.length, 10)}`,
      scale: 1,
      format: "png",
    });
    await fs.writeFile(`${workDir}/${sheet.name.replaceAll("/", "_")}_preview.png`, new Uint8Array(await preview.arrayBuffer()));
  }
}

const remainingText = (await fs.readFile(remainingPath, "utf8")).replace(/^\uFEFF/, "");
const remainingWorkbook = await Workbook.fromCSV(remainingText, { sheetName: "剩余301篇" });
const remainingValues = remainingWorkbook.worksheets.getItem("剩余301篇").getUsedRange(true).values;

await fs.writeFile(`${workDir}/new_workbook.json`, JSON.stringify({ sheets }, null, 2), "utf8");
await fs.writeFile(`${workDir}/remaining_301.json`, JSON.stringify({ values: remainingValues }, null, 2), "utf8");

console.log(workbookInspection.ndjson);
console.log(JSON.stringify({
  newSheets: sheets.map((sheet) => ({
    name: sheet.name,
    rowsIncludingHeader: sheet.values.length,
    columns: sheet.values[0]?.length || 0,
    headers: sheet.values[0] || [],
  })),
  remainingRowsIncludingHeader: remainingValues.length,
  remainingColumns: remainingValues[0]?.length || 0,
  remainingHeaders: remainingValues[0] || [],
}, null, 2));
