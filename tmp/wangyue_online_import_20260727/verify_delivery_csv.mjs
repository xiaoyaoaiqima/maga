import fs from "node:fs/promises";
import { createHash } from "node:crypto";
import { Workbook } from "@oai/artifact-tool";

const candidatePath =
  "/Users/luxifa/maga/outputs/0705_wangyue_product_relation_evidence/" +
  "20260727_wangyue_v92_production_100_online/" +
  "20260727_wangyue_batch876_online_import_incremental.csv";
const onlinePath = "/Users/luxifa/Downloads/note_content_202607271103.csv";
const previewPath =
  "/Users/luxifa/maga/tmp/wangyue_online_import_20260727/" +
  "batch876_delivery_csv_preview.png";

async function loadCsv(path, sheetName) {
  const text = await fs.readFile(path, "utf8");
  return Workbook.fromCSV(text, { sheetName });
}

function rowsFrom(workbook, sheetName) {
  const sheet = workbook.worksheets.getItem(sheetName);
  const values = sheet.getUsedRange(true).values;
  const headers = values[0].map((value) => String(value ?? "").replace(/^\uFEFF/, ""));
  const rows = values.slice(1).filter((row) => row.some((value) => String(value ?? "").trim()));
  return { sheet, headers, rows };
}

function bodyHashes(headers, rows) {
  const bodyIndex = headers.indexOf("正文");
  if (bodyIndex < 0) throw new Error(`missing 正文 column: ${headers.join(",")}`);
  return rows.map((row) =>
    createHash("sha256").update(String(row[bodyIndex] ?? "").trim()).digest("hex"),
  );
}

const candidateWorkbook = await loadCsv(candidatePath, "线上导入");
const onlineWorkbook = await loadCsv(onlinePath, "线上历史");
const candidate = rowsFrom(candidateWorkbook, "线上导入");
const online = rowsFrom(onlineWorkbook, "线上历史");

const expectedHeaders = ["标题", "正文", "上下文变量(context_list)"];
if (JSON.stringify(candidate.headers) !== JSON.stringify(expectedHeaders)) {
  throw new Error(`unexpected headers: ${JSON.stringify(candidate.headers)}`);
}
if (candidate.rows.length !== 77) {
  throw new Error(`unexpected candidate row count: ${candidate.rows.length}`);
}

const candidateHashes = bodyHashes(candidate.headers, candidate.rows);
const onlineHashes = new Set(bodyHashes(online.headers, online.rows));
const internalDuplicateCount = candidateHashes.length - new Set(candidateHashes).size;
const onlineDuplicateCount = candidateHashes.filter((hash) => onlineHashes.has(hash)).length;
if (internalDuplicateCount !== 0 || onlineDuplicateCount !== 0) {
  throw new Error(
    `duplicates found: internal=${internalDuplicateCount}, online=${onlineDuplicateCount}`,
  );
}

const inspect = await candidateWorkbook.inspect({
  kind: "table",
  range: "线上导入!A1:C6",
  include: "values,formulas",
  tableMaxRows: 6,
  tableMaxCols: 3,
  tableMaxCellChars: 80,
  maxChars: 4000,
});

const rendered = await candidateWorkbook.render({
  sheetName: "线上导入",
  range: "A1:C6",
  scale: 1,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await rendered.arrayBuffer()));

console.log(
  JSON.stringify(
    {
      headers: candidate.headers,
      candidateRows: candidate.rows.length,
      onlineRows: online.rows.length,
      internalDuplicateCount,
      onlineDuplicateCount,
      inspect: inspect.ndjson,
      previewPath,
    },
    null,
    2,
  ),
);
