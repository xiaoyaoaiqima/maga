import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const basePath =
  "/Users/luxifa/maga/outputs/a2_reiyu_reward_completion_cleanup_20260722/" +
  "a2礼遇_F强化禁止虚构领奖并删除冗余路径约束.csv";
const outputDir = "/Users/luxifa/maga/outputs/a2_reiyu_title_under_19_20260722";
const candidatePath = `${outputDir}/a2礼遇_G标题少于19字.csv`;
const previewPath = `${outputDir}/a2礼遇_G标题少于19字_预览.png`;
const titleRule = "标题按中文、字母、数字各1字、emoji算2字，必须少于19字。";

const csvEscape = (value) => {
  const text = String(value ?? "");
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};

const baseText = await fs.readFile(basePath, "utf8");
const baseWorkbook = await Workbook.fromCSV(baseText, { sheetName: "业务规则" });
const baseValues = baseWorkbook.worksheets.getItem("业务规则").getUsedRange(true).values;
const headers = baseValues[0].map((value) => String(value ?? "").replace(/^\uFEFF/, ""));
const boundaryIndex = headers.indexOf("硬边界");
if (boundaryIndex < 0) throw new Error("missing 硬边界 column");

const baseRows = baseValues.slice(1).map((row) =>
  headers.map((_, index) => String(row[index] ?? "")),
);
let added = 0;
const candidateRows = baseRows.map((row) => {
  const copy = [...row];
  const boundaries = copy[boundaryIndex].split("||").filter(Boolean);
  if (!boundaries.includes(titleRule)) {
    boundaries.unshift(titleRule);
    added += 1;
  }
  copy[boundaryIndex] = boundaries.join("||");
  return copy;
});

if (baseRows.length !== 16) throw new Error(`expected 16 rows, got ${baseRows.length}`);
if (added !== 16) throw new Error(`expected 16 title rules, got ${added}`);

const diffs = [];
for (let row = 0; row < baseRows.length; row += 1) {
  for (let col = 0; col < headers.length; col += 1) {
    if (baseRows[row][col] !== candidateRows[row][col]) {
      diffs.push({ row_no: row + 1, column: headers[col] });
    }
  }
}
const unexpectedDiffs = diffs.filter((diff) => diff.column !== "硬边界");
if (unexpectedDiffs.length) {
  throw new Error(`unexpected non-boundary diffs: ${JSON.stringify(unexpectedDiffs)}`);
}

await fs.mkdir(outputDir, { recursive: true });
const matrix = [headers, ...candidateRows];
const csvText = `\uFEFF${matrix.map((row) => row.map(csvEscape).join(",")).join("\n")}\n`;
await fs.writeFile(candidatePath, csvText, "utf8");

const workbook = await Workbook.fromCSV(csvText, { sheetName: "业务规则" });
const sheet = workbook.worksheets.getItem("业务规则");
const verifyValues = sheet.getUsedRange(true).values;
if (verifyValues.length !== matrix.length || verifyValues[0].length !== headers.length) {
  throw new Error("candidate shape changed after export/import");
}
sheet.getRangeByIndexes(0, 0, 1, headers.length).format = {
  fill: "#5B2C6F",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
};
sheet.getRangeByIndexes(1, 0, candidateRows.length, headers.length).format.wrapText = true;
sheet.getRangeByIndexes(0, 0, matrix.length, headers.length).format.columnWidth = 24;
sheet.freezePanes.freezeRows(1);
sheet.showGridLines = false;
const preview = await workbook.render({
  sheetName: "业务规则",
  range: `A1:O${matrix.length}`,
  scale: 0.5,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

const titleInspect = await workbook.inspect({
  kind: "match",
  searchTerm: "标题按中文、字母、数字各1字、emoji算2字，必须少于19字",
  options: { useRegex: false, maxResults: 20 },
  summary: "标题少于19字规则",
  maxChars: 5000,
});
process.stdout.write(`${titleInspect.ndjson}\n`);
process.stdout.write(
  `${JSON.stringify(
    {
      candidate_path: candidatePath,
      preview_path: previewPath,
      business_rule_rows: candidateRows.length,
      title_rule_added: added,
      diff_count: diffs.length,
      diff_columns: [...new Set(diffs.map((diff) => diff.column))],
    },
    null,
    2,
  )}\n`,
);
