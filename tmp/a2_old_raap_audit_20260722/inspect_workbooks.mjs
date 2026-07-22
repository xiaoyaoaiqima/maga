import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputs = [
  "/Users/luxifa/Downloads/文章池导出_2026-07-22.xlsx",
  "/Users/luxifa/Downloads/文章池导出_2026-07-22 (1).xlsx",
];
const outputDir = "/Users/luxifa/maga/tmp/a2_old_raap_audit_20260722";

await fs.mkdir(outputDir, { recursive: true });
const extracted = [];

for (const inputPath of inputs) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
  const overview = await workbook.inspect({
    kind: "workbook,sheet,table",
    maxChars: 6000,
    tableMaxRows: 5,
    tableMaxCols: 10,
    tableMaxCellChars: 120,
  });
  const sheets = [];
  for (const sheet of workbook.worksheets.items) {
    const used = sheet.getUsedRange(true);
    const values = used ? used.values : [];
    sheets.push({
      name: sheet.name,
      rowCount: values.length,
      columnCount: values.length ? values[0].length : 0,
      values,
    });
  }
  const firstSheet = workbook.worksheets.getItemAt(0);
  const preview = await workbook.render({
    sheetName: firstSheet.name,
    range: "A1:H12",
    scale: 1.25,
    format: "png",
  });
  const base = path.basename(inputPath, ".xlsx").replaceAll(" ", "_").replaceAll("(", "").replaceAll(")", "");
  await fs.writeFile(path.join(outputDir, `${base}_preview.png`), new Uint8Array(await preview.arrayBuffer()));
  extracted.push({ inputPath, overview: overview.ndjson, sheets });
}

await fs.writeFile(
  path.join(outputDir, "extracted_workbooks.json"),
  JSON.stringify(extracted, null, 2),
  "utf8",
);

for (const workbook of extracted) {
  console.log(JSON.stringify({
    inputPath: workbook.inputPath,
    sheets: workbook.sheets.map((sheet) => ({
      name: sheet.name,
      rowCount: sheet.rowCount,
      columnCount: sheet.columnCount,
      headers: sheet.values[0] || [],
      firstDataRow: sheet.values[1] || [],
    })),
  }, null, 2));
}
