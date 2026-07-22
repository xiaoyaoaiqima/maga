import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const sourcePath = "/Users/luxifa/Downloads/正向词_子关键词导出 (1).csv";
const v17Path =
  "/Users/luxifa/maga/outputs/a2_reiyu_v17_title_hard_drop_20260721/" +
  "a2礼遇UGC分享贴_v17标题超20淘汰.csv";
const outputDir = "/Users/luxifa/maga/outputs/a2_reiyu_positive_words_ab_20260722";
const removedTerms = ["放心", "省心", "真香"];

const stripComments = (text) =>
  text
    .replace(/^\uFEFF/, "")
    .split(/\r?\n/)
    .filter((line) => !line.startsWith("#"))
    .join("\n");

const csvEscape = (value) => {
  const text = String(value ?? "");
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};

const exportCsv = async (path, matrix) => {
  const text = `\uFEFF${matrix.map((row) => row.map(csvEscape).join(",")).join("\n")}\n`;
  await fs.writeFile(path, text, "utf8");
};

const sourceText = stripComments(await fs.readFile(sourcePath, "utf8"));
const sourceWorkbook = await Workbook.fromCSV(sourceText, { sheetName: "原始正向词" });
const sourceValues = sourceWorkbook.worksheets.getItem("原始正向词").getUsedRange(true).values;
const sourceHeaders = sourceValues[0].map((value) => String(value ?? "").replace(/^\uFEFF/, ""));
const sourceCorpusIndex = sourceHeaders.indexOf("语料");
if (sourceCorpusIndex < 0) throw new Error("missing source corpus column");
const originalCorpora = sourceValues
  .slice(1)
  .map((row) => String(row[sourceCorpusIndex] ?? "").trim())
  .filter(Boolean);

const lightlyReduceCorpus = (corpus) =>
  corpus
    .split("\n")
    .map((line) => {
      const separator = line.indexOf("：");
      if (separator < 0) return line;
      const label = line.slice(0, separator + 1);
      const hadPeriod = line.endsWith("。");
      const terms = line
        .slice(separator + 1)
        .replace(/。$/, "")
        .split("、")
        .map((term) => term.trim())
        .filter((term) => term && !removedTerms.includes(term));
      return `${label}${terms.join("、")}${hadPeriod ? "。" : ""}`;
    })
    .join("\n");

const reducedCorpora = originalCorpora.map(lightlyReduceCorpus);

const v17Text = await fs.readFile(v17Path, "utf8");
const v17Workbook = await Workbook.fromCSV(v17Text, { sheetName: "业务规则" });
const v17Values = v17Workbook.worksheets.getItem("业务规则").getUsedRange(true).values;
const headers = v17Values[0].map((value) => String(value ?? "").replace(/^\uFEFF/, ""));
const positiveIndex = headers.indexOf("正向表达素材");
if (positiveIndex < 0) throw new Error("missing positive expression column");
const baseRows = v17Values.slice(1).map((row) => headers.map((_, index) => String(row[index] ?? "")));

const buildMatrix = (corpora) => {
  const positivePool = corpora.join("||");
  return [headers, ...baseRows.map((row) => row.map((value, index) => (index === positiveIndex ? positivePool : value)))];
};

const matrixA = buildMatrix(originalCorpora);
const matrixB = buildMatrix(reducedCorpora);
const pathA = `${outputDir}/a2礼遇_v17单变量_A原始正向词完整语料.csv`;
const pathB = `${outputDir}/a2礼遇_v17单变量_B原始正向词轻删3个高频泛词.csv`;
const previewA = `${outputDir}/a2礼遇_v17单变量_A原始正向词完整语料预览.png`;
const previewB = `${outputDir}/a2礼遇_v17单变量_B原始正向词轻删3个高频泛词预览.png`;

await fs.mkdir(outputDir, { recursive: true });
await exportCsv(pathA, matrixA);
await exportCsv(pathB, matrixB);

const renderMatrix = async (matrix, path) => {
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add("业务规则");
  sheet.getRangeByIndexes(0, 0, matrix.length, headers.length).values = matrix;
  sheet.getRangeByIndexes(0, 0, 1, headers.length).format = {
    fill: "#5B2C6F",
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
  };
  sheet.getRangeByIndexes(1, 0, matrix.length - 1, headers.length).format.wrapText = true;
  sheet.getRangeByIndexes(0, 0, matrix.length, headers.length).format.columnWidth = 26;
  sheet.freezePanes.freezeRows(1);
  sheet.showGridLines = false;
  const image = await workbook.render({
    sheetName: "业务规则",
    range: `A1:O${matrix.length}`,
    scale: 0.55,
    format: "png",
  });
  await fs.writeFile(path, new Uint8Array(await image.arrayBuffer()));
  return workbook;
};

const workbookA = await renderMatrix(matrixA, previewA);
const workbookB = await renderMatrix(matrixB, previewB);

const nonPositiveDiffs = [];
for (let row = 0; row < baseRows.length; row += 1) {
  for (let col = 0; col < headers.length; col += 1) {
    if (col === positiveIndex) continue;
    const base = baseRows[row][col];
    if (matrixA[row + 1][col] !== base || matrixB[row + 1][col] !== base) {
      nonPositiveDiffs.push({ row_no: row + 1, column: headers[col] });
    }
  }
}
if (nonPositiveDiffs.length) throw new Error(`unexpected non-positive diffs: ${JSON.stringify(nonPositiveDiffs)}`);

const inspectA = await workbookA.inspect({
  kind: "table",
  range: `业务规则!A1:O${matrixA.length}`,
  include: "values",
  tableMaxRows: 3,
  tableMaxCols: 15,
  tableMaxCellChars: 180,
  maxChars: 10000,
});
const inspectB = await workbookB.inspect({
  kind: "match",
  searchTerm: removedTerms.join("|"),
  options: { useRegex: true, maxResults: 20 },
  summary: "轻删项残留扫描",
  maxChars: 6000,
});

process.stdout.write(`${inspectA.ndjson}\n`);
process.stdout.write(`${inspectB.ndjson}\n`);
process.stdout.write(
  `${JSON.stringify(
    {
      source_row_count: originalCorpora.length,
      business_rule_row_count: baseRows.length,
      positive_column: headers[positiveIndex],
      candidate_a: pathA,
      candidate_b: pathB,
      preview_a: previewA,
      preview_b: previewB,
      candidate_a_corpora: originalCorpora.length,
      candidate_b_corpora: reducedCorpora.length,
      candidate_b_removed_terms: removedTerms,
      non_positive_diff_count: nonPositiveDiffs.length,
    },
    null,
    2,
  )}\n`,
);
