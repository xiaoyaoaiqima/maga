import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const sourcePath = "/Users/luxifa/Downloads/正向词_子关键词导出 (1).csv";
const v17Path =
  "/Users/luxifa/maga/outputs/a2_reiyu_v17_title_hard_drop_20260721/" +
  "a2礼遇UGC分享贴_v17标题超20淘汰.csv";

const stripComments = (text) =>
  text
    .split(/\r?\n/)
    .filter((line) => !line.startsWith("#"))
    .join("\n");

const loadCsv = async (path, sheetName, stripLeadingComments = false) => {
  const raw = await fs.readFile(path, "utf8");
  const text = stripLeadingComments ? stripComments(raw.replace(/^\uFEFF/, "")) : raw;
  const workbook = await Workbook.fromCSV(text, { sheetName });
  const sheet = workbook.worksheets.getItem(sheetName);
  const values = sheet.getUsedRange(true).values;
  const headers = values[0].map((value) => String(value ?? "").replace(/^\uFEFF/, ""));
  const rows = values.slice(1).map((row) =>
    Object.fromEntries(headers.map((header, index) => [header, String(row[index] ?? "")]))
  );
  return { workbook, headers, rows };
};

const source = await loadCsv(sourcePath, "原始正向词", true);
const v17 = await loadCsv(v17Path, "v17业务规则");

const sourceRows = source.rows.map((row, index) => ({
  row_no: index + 1,
  keyword: row["正向词"],
  corpus: row["语料"],
}));
const v17Positive = [...new Set(v17.rows.map((row) => row["正向表达素材"]).filter(Boolean))];

const splitTerms = (corpus) =>
  corpus
    .split(/\n/)
    .flatMap((line) => line.replace(/^[^：]+：/, "").replace(/[。；]$/g, "").split(/[、，；]/))
    .map((term) => term.trim())
    .filter(Boolean);

const sourceTerms = sourceRows.flatMap((row) => splitTerms(row.corpus));
const termCounts = new Map();
for (const term of sourceTerms) termCounts.set(term, (termCounts.get(term) ?? 0) + 1);
const duplicateTerms = [...termCounts.entries()]
  .filter(([, count]) => count > 1)
  .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "zh-CN"));

const result = {
  source: {
    path: sourcePath,
    headers: source.headers,
    row_count: sourceRows.length,
    rows: sourceRows,
    total_term_occurrences: sourceTerms.length,
    unique_terms: termCounts.size,
    duplicate_terms: duplicateTerms,
  },
  v17: {
    path: v17Path,
    headers: v17.headers,
    row_count: v17.rows.length,
    unique_positive_slot_count: v17Positive.length,
    positive_slots: v17Positive,
  },
};

const inspection = await source.workbook.inspect({
  kind: "table",
  range: `原始正向词!A1:B${sourceRows.length + 1}`,
  include: "values",
  tableMaxRows: sourceRows.length + 1,
  tableMaxCols: 2,
  tableMaxCellChars: 1000,
  maxChars: 30000,
});

process.stdout.write(`${inspection.ndjson}\n`);
process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
