import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const basePath =
  "/Users/luxifa/maga/outputs/a2_reiyu_positive_path_routing_20260722/" +
  "a2礼遇_v17单变量_正向词按认可路径分流.csv";
const outputDir = "/Users/luxifa/maga/outputs/a2_reiyu_positive_usage_and_loyalty_20260722";
const cPath = `${outputDir}/a2礼遇_C仅放宽正向词使用数量.csv`;
const dPath = `${outputDir}/a2礼遇_D老客了解信息后更认可.csv`;

const oldPositiveRule = "正向表达只挑和本篇体验贴合的一两个自然带入，不必覆盖整组词。";
const newPositiveRule = "使用适合融入文章的正向词。";
const oldPathRule =
  "本条认可路径是信息了解后的认可：只根据活动和每批检测信息表达品牌感受，不补写宝宝长期使用结果、转奶或回归经历。";
const newPathRule =
  "本条认可路径是老客了解信息后更认可：可以自然交代长期购买、老客身份或简短使用背景；本次认可提升要由活动和每批检测信息承接，不必展开宝宝状态或产品效果。";

const csvEscape = (value) => {
  const text = String(value ?? "");
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};

const baseText = await fs.readFile(basePath, "utf8");
const baseWorkbook = await Workbook.fromCSV(baseText, { sheetName: "业务规则" });
const baseValues = baseWorkbook.worksheets.getItem("业务规则").getUsedRange(true).values;
const headers = baseValues[0].map((value) => String(value ?? "").replace(/^\uFEFF/, ""));
const nameIndex = headers.indexOf("业务规则名称");
const writingIndex = headers.indexOf("写法");
const boundaryIndex = headers.indexOf("硬边界");
if ([nameIndex, writingIndex, boundaryIndex].some((index) => index < 0)) {
  throw new Error("missing required columns");
}
const baseRows = baseValues.slice(1).map((row) => headers.map((_, index) => String(row[index] ?? "")));

let cReplacementCount = 0;
const cRows = baseRows.map((row) => {
  const copy = [...row];
  if (copy[writingIndex].includes(oldPositiveRule)) {
    copy[writingIndex] = copy[writingIndex].replace(oldPositiveRule, newPositiveRule);
    cReplacementCount += 1;
  }
  return copy;
});
if (cReplacementCount !== 8) {
  throw new Error(`expected 8 positive-rule replacements, got ${cReplacementCount}`);
}

let dNameCount = 0;
let dBoundaryCount = 0;
const dRows = cRows.map((row) => {
  const copy = [...row];
  if (copy[nameIndex].includes("信息了解后的认可")) {
    copy[nameIndex] = copy[nameIndex].replace("信息了解后的认可", "老客了解信息后更认可");
    dNameCount += 1;
  }
  if (copy[boundaryIndex].includes(oldPathRule)) {
    copy[boundaryIndex] = copy[boundaryIndex].replace(oldPathRule, newPathRule);
    dBoundaryCount += 1;
  }
  return copy;
});
if (dNameCount !== 8 || dBoundaryCount !== 8) {
  throw new Error(`unexpected D replacements: name=${dNameCount}, boundary=${dBoundaryCount}`);
}

const diffColumns = (leftRows, rightRows) => {
  const diffs = [];
  for (let row = 0; row < leftRows.length; row += 1) {
    for (let col = 0; col < headers.length; col += 1) {
      if (leftRows[row][col] !== rightRows[row][col]) {
        diffs.push({ row_no: row + 1, column: headers[col] });
      }
    }
  }
  return diffs;
};
const cDiffs = diffColumns(baseRows, cRows);
const dDiffs = diffColumns(cRows, dRows);
const unexpectedCDiffs = cDiffs.filter((diff) => diff.column !== "写法");
const unexpectedDDiffs = dDiffs.filter(
  (diff) => !["业务规则名称", "硬边界"].includes(diff.column),
);
if (unexpectedCDiffs.length || unexpectedDDiffs.length) {
  throw new Error(
    `unexpected diffs: ${JSON.stringify({ unexpectedCDiffs, unexpectedDDiffs })}`,
  );
}

const exportCandidate = async (path, rows, previewName) => {
  const matrix = [headers, ...rows];
  const csvText = `\uFEFF${matrix.map((row) => row.map(csvEscape).join(",")).join("\n")}\n`;
  await fs.writeFile(path, csvText, "utf8");
  const workbook = await Workbook.fromCSV(csvText, { sheetName: "业务规则" });
  const sheet = workbook.worksheets.getItem("业务规则");
  const values = sheet.getUsedRange(true).values;
  if (values.length !== matrix.length || values[0].length !== headers.length) {
    throw new Error(`shape mismatch after export: ${path}`);
  }
  sheet.getRangeByIndexes(0, 0, 1, headers.length).format = {
    fill: "#5B2C6F",
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
  };
  sheet.getRangeByIndexes(1, 0, rows.length, headers.length).format.wrapText = true;
  sheet.getRangeByIndexes(0, 0, matrix.length, headers.length).format.columnWidth = 24;
  sheet.freezePanes.freezeRows(1);
  sheet.showGridLines = false;
  const preview = await workbook.render({
    sheetName: "业务规则",
    range: `A1:O${matrix.length}`,
    scale: 0.5,
    format: "png",
  });
  const previewPath = `${outputDir}/${previewName}`;
  await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
  const inspect = await workbook.inspect({
    kind: "match",
    searchTerm: "使用适合融入文章的正向词|老客了解信息后更认可",
    options: { useRegex: true, maxResults: 40 },
    summary: previewName,
    maxChars: 8000,
  });
  process.stdout.write(`${inspect.ndjson}\n`);
  return previewPath;
};

await fs.mkdir(outputDir, { recursive: true });
const cPreview = await exportCandidate(cPath, cRows, "C仅放宽正向词使用数量_预览.png");
const dPreview = await exportCandidate(dPath, dRows, "D老客了解信息后更认可_预览.png");

process.stdout.write(
  `${JSON.stringify(
    {
      base_path: basePath,
      c_path: cPath,
      d_path: dPath,
      c_preview: cPreview,
      d_preview: dPreview,
      c_replacements: cReplacementCount,
      c_diff_count: cDiffs.length,
      c_diff_columns: [...new Set(cDiffs.map((diff) => diff.column))],
      d_name_replacements: dNameCount,
      d_boundary_replacements: dBoundaryCount,
      d_diff_count: dDiffs.length,
      d_diff_columns: [...new Set(dDiffs.map((diff) => diff.column))],
    },
    null,
    2,
  )}\n`,
);
