import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const sourcePath = "/Users/luxifa/Downloads/正向词_子关键词导出 (1).csv";
const v17Path =
  "/Users/luxifa/maga/outputs/a2_reiyu_v17_title_hard_drop_20260721/" +
  "a2礼遇UGC分享贴_v17标题超20淘汰.csv";
const outputDir = "/Users/luxifa/maga/outputs/a2_reiyu_positive_path_routing_20260722";
const candidatePath = `${outputDir}/a2礼遇_v17单变量_正向词按认可路径分流.csv`;
const previewPath = `${outputDir}/a2礼遇_v17单变量_正向词按认可路径分流预览.png`;

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
if (originalCorpora.length !== 12) {
  throw new Error(`expected 12 original corpora, got ${originalCorpora.length}`);
}

// 信息认可路径只使用原始语料中无需亲身喂养经历承接的词。
// 这里仅做路由筛选，不改写任何词。
const informationCorpora = [
  "妈妈心理：安心、放心、踏实、靠谱、值得信赖、心里有底、有保障、有底气、经得起研究、经得起比较、让人放心。",
  "妈妈心理：品控在线、品质在线、质量稳定、标准高、细节到位、做得认真、诚意满满、透明放心、让人信服、经得起考验。",
  "妈妈心理：值得推荐、良心品牌、口碑在线、实力在线、表现稳定。",
];

const originalTerms = new Set(
  originalCorpora.flatMap((corpus) =>
    corpus.split("\n").flatMap((line) => {
      const separator = line.indexOf("：");
      return (separator < 0 ? line : line.slice(separator + 1))
        .replace(/。$/, "")
        .split("、")
        .map((term) => term.trim())
        .filter(Boolean);
    }),
  ),
);
const informationTerms = informationCorpora.flatMap((corpus) =>
  corpus
    .split("：", 2)[1]
    .replace(/。$/, "")
    .split("、")
    .map((term) => term.trim())
    .filter(Boolean),
);
const inventedInformationTerms = informationTerms.filter((term) => !originalTerms.has(term));
if (inventedInformationTerms.length) {
  throw new Error(`information pool contains non-source terms: ${inventedInformationTerms.join(",")}`);
}

const v17Text = await fs.readFile(v17Path, "utf8");
const v17Workbook = await Workbook.fromCSV(v17Text, { sheetName: "业务规则" });
const v17Values = v17Workbook.worksheets.getItem("业务规则").getUsedRange(true).values;
const headers = v17Values[0].map((value) => String(value ?? "").replace(/^\uFEFF/, ""));
const nameIndex = headers.indexOf("业务规则名称");
const positiveIndex = headers.indexOf("正向表达素材");
if (nameIndex < 0 || positiveIndex < 0) throw new Error("missing required v17 columns");

const fullOldCustomerPool = originalCorpora.join("||");
const informationPool = informationCorpora.join("||");
let oldCustomerRows = 0;
let informationRows = 0;
const baseRows = v17Values.slice(1).map((row) => headers.map((_, index) => String(row[index] ?? "")));
const candidateRows = baseRows.map((row) => {
  const copy = [...row];
  const name = copy[nameIndex];
  if (name.includes("老客使用感受")) {
    copy[positiveIndex] = fullOldCustomerPool;
    oldCustomerRows += 1;
  } else if (name.includes("信息了解后的认可")) {
    copy[positiveIndex] = informationPool;
    informationRows += 1;
  } else {
    throw new Error(`unknown recognition path: ${name}`);
  }
  return copy;
});

const nonPositiveDiffs = [];
for (let row = 0; row < baseRows.length; row += 1) {
  for (let col = 0; col < headers.length; col += 1) {
    if (col === positiveIndex) continue;
    if (baseRows[row][col] !== candidateRows[row][col]) {
      nonPositiveDiffs.push({ row_no: row + 1, column: headers[col] });
    }
  }
}
if (nonPositiveDiffs.length) {
  throw new Error(`unexpected non-positive diffs: ${JSON.stringify(nonPositiveDiffs)}`);
}

await fs.mkdir(outputDir, { recursive: true });
const matrix = [headers, ...candidateRows];
const csvText = `\uFEFF${matrix.map((row) => row.map(csvEscape).join(",")).join("\n")}\n`;
await fs.writeFile(candidatePath, csvText, "utf8");

const verifyWorkbook = await Workbook.fromCSV(csvText, { sheetName: "业务规则" });
const verifySheet = verifyWorkbook.worksheets.getItem("业务规则");
const verifyValues = verifySheet.getUsedRange(true).values;
if (verifyValues.length !== matrix.length || verifyValues[0].length !== headers.length) {
  throw new Error("candidate CSV shape changed after export/import");
}

verifySheet.getRangeByIndexes(0, 0, 1, headers.length).format = {
  fill: "#5B2C6F",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
};
verifySheet.getRangeByIndexes(1, 0, candidateRows.length, headers.length).format.wrapText = true;
verifySheet.getRangeByIndexes(0, 0, matrix.length, headers.length).format.columnWidth = 24;
verifySheet.freezePanes.freezeRows(1);
verifySheet.showGridLines = false;
const preview = await verifyWorkbook.render({
  sheetName: "业务规则",
  range: `A1:O${matrix.length}`,
  scale: 0.5,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

const inspect = await verifyWorkbook.inspect({
  kind: "table",
  range: `业务规则!A1:O${matrix.length}`,
  include: "values",
  tableMaxRows: 3,
  tableMaxCols: 15,
  tableMaxCellChars: 180,
  maxChars: 10000,
});
process.stdout.write(`${inspect.ndjson}\n`);
process.stdout.write(
  `${JSON.stringify(
    {
      candidate_path: candidatePath,
      preview_path: previewPath,
      business_rule_rows: candidateRows.length,
      old_customer_rows: oldCustomerRows,
      information_rows: informationRows,
      old_customer_source_corpora: originalCorpora.length,
      information_corpora: informationCorpora.length,
      information_term_count: informationTerms.length,
      invented_information_term_count: inventedInformationTerms.length,
      non_positive_diff_count: nonPositiveDiffs.length,
    },
    null,
    2,
  )}\n`,
);
