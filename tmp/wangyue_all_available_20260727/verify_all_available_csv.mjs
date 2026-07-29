import fs from "node:fs/promises";
import { createHash } from "node:crypto";
import { Workbook } from "@oai/artifact-tool";

const outputPath =
  "/Users/luxifa/maga/outputs/0705_wangyue_product_relation_evidence/" +
  "20260727_wangyue_all_available_export/20260727_wangyue_all_available_300.csv";
const historicalOnlinePath = "/Users/luxifa/Downloads/note_content_202607271103.csv";
const justImportedPath =
  "/Users/luxifa/maga/outputs/0705_wangyue_product_relation_evidence/" +
  "20260727_wangyue_v92_production_100_online/" +
  "20260727_wangyue_batch876_online_import_incremental.csv";
const previewPath =
  "/Users/luxifa/maga/tmp/wangyue_all_available_20260727/" +
  "all_available_preview.png";

async function loadCsv(path, sheetName) {
  const text = await fs.readFile(path, "utf8");
  return Workbook.fromCSV(text, { sheetName });
}

function readRows(workbook, sheetName) {
  const sheet = workbook.worksheets.getItem(sheetName);
  const values = sheet.getUsedRange(true).values;
  const headers = values[0].map((value) => String(value ?? "").replace(/^\uFEFF/, ""));
  const rows = values.slice(1).filter((row) => row.some((value) => String(value ?? "").trim()));
  return { headers, rows };
}

function hashes(headers, rows) {
  const bodyIndex = headers.indexOf("正文");
  if (bodyIndex < 0) throw new Error(`missing 正文 column: ${headers.join(",")}`);
  return rows.map((row) =>
    createHash("sha256").update(String(row[bodyIndex] ?? "").trim()).digest("hex"),
  );
}

const outputWorkbook = await loadCsv(outputPath, "全部可用");
const historicalWorkbook = await loadCsv(historicalOnlinePath, "线上历史");
const importedWorkbook = await loadCsv(justImportedPath, "刚导入77篇");
const output = readRows(outputWorkbook, "全部可用");
const historical = readRows(historicalWorkbook, "线上历史");
const imported = readRows(importedWorkbook, "刚导入77篇");

const expectedHeaders = ["标题", "正文", "上下文变量(context_list)"];
if (JSON.stringify(output.headers) !== JSON.stringify(expectedHeaders)) {
  throw new Error(`unexpected headers: ${JSON.stringify(output.headers)}`);
}
if (output.rows.length !== 300) {
  throw new Error(`unexpected row count: ${output.rows.length}`);
}

const outputHashes = hashes(output.headers, output.rows);
const historicalHashes = new Set(hashes(historical.headers, historical.rows));
const importedHashes = new Set(hashes(imported.headers, imported.rows));
const internalDuplicateCount = outputHashes.length - new Set(outputHashes).size;
const historicalDuplicateCount = outputHashes.filter((hash) => historicalHashes.has(hash)).length;
const justImportedDuplicateCount = outputHashes.filter((hash) => importedHashes.has(hash)).length;
if (internalDuplicateCount || historicalDuplicateCount || justImportedDuplicateCount) {
  throw new Error(
    `duplicates found: internal=${internalDuplicateCount}, ` +
      `historical=${historicalDuplicateCount}, justImported=${justImportedDuplicateCount}`,
  );
}

const inspect = await outputWorkbook.inspect({
  kind: "table",
  range: "全部可用!A1:C6",
  include: "values,formulas",
  tableMaxRows: 6,
  tableMaxCols: 3,
  tableMaxCellChars: 80,
  maxChars: 4000,
});
const rendered = await outputWorkbook.render({
  sheetName: "全部可用",
  range: "A1:C6",
  scale: 1,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await rendered.arrayBuffer()));

console.log(
  JSON.stringify(
    {
      headers: output.headers,
      outputRows: output.rows.length,
      historicalOnlineRows: historical.rows.length,
      justImportedRows: imported.rows.length,
      internalDuplicateCount,
      historicalDuplicateCount,
      justImportedDuplicateCount,
      inspect: inspect.ndjson,
      previewPath,
    },
    null,
    2,
  ),
);
