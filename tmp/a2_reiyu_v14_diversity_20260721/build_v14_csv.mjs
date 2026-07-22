import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const inputCsv =
  "/Users/luxifa/maga/outputs/a2_reiyu_full_raw_merged_20260721/" +
  "a2礼遇UGC分享贴_原始槽位_认可路径分流.csv";
const outputDir =
  "/Users/luxifa/maga/outputs/a2_reiyu_v18_concise_prompt_20260721";
const outputCsv = `${outputDir}/a2礼遇UGC分享贴_v18精简生成要求.csv`;
const previewPng = `${outputDir}/a2礼遇UGC分享贴_v18精简生成要求预览.png`;

const csvText = await fs.readFile(inputCsv, "utf8");
const workbook = await Workbook.fromCSV(csvText, { sheetName: "业务规则" });
const sheet = workbook.worksheets.getItem("业务规则");
const values = sheet.getUsedRange(true).values;
const headers = values[0].map((value) => String(value ?? "").replace(/^\uFEFF/, ""));
const rows = values.slice(1).map((row) => [...row]);

const columnIndex = (name) => {
  const index = headers.indexOf(name);
  if (index < 0) throw new Error(`missing column: ${name}`);
  return index;
};
const activityIndex = columnIndex("活动内容素材");
const detectionIndex = columnIndex("批批检素材");
const directionIndex = columnIndex("内容方向");
const directionOptionsIndex = columnIndex("内容方向素材");
const ruleNameIndex = columnIndex("业务规则名称");
const writingIndex = columnIndex("写法");
const generationIndex = columnIndex("生成要求");
const hardBoundaryIndex = columnIndex("硬边界");
const recognitionIndex = columnIndex("认可表达素材");
const instructionIndex = columnIndex("生文指令");

const ambiguousPointsContent =
  "以前没认真研究过积分，现在发现能换东西，感觉之前错过了几个亿😂";
const enumeratedNegativeBoundary =
  "禁止出现或暗示质量问题、风险澄清、召回、断货、没货、买不到、失败、踩雷、焦虑、担心、翻车、避雷、维权、投诉、问题批次、塌房、爆雷、断粮、缺货、抢不到、不安、不放心、有问题、出事、真伪、假货、代购不确定、被迫转奶。";
const abstractNegativeBoundary =
  "不要把a2、a2至初或本次活动写成存在质量、安全、供应、真伪或售后争议。自然情绪表达可以保留，只有形成明确的品牌或产品负面经历时才处理。";
const corporateRecognitionCandidate =
  "认可依据：从本次活动和a2至初每批检测信息形成的品牌感受。\n品牌感受原话：用实际行动得到用户认可";
const conciseInstruction =
  "写成普通宝妈的自然分享，以活动内容为主，来源和参加原因简单交代。标题贴合正文，正文约200字，可自然分段并使用少量emoji。";
const conciseBoundaries = [
  "只围绕本篇素材里的主活动和认可路径写，素材用自然口语转述。",
  "主产品是a2至初奶粉，品牌是a2，a始终小写。",
  "先讲活动，再自然带出a2至初现在每批都有检测，不新增检测细节。",
  "罐底码只用于查询检测或溯源；集罐不写旧罐、空罐参与，因为老罐子不能用来集罐。",
  "除非素材明确提供，不写自己已经中奖、兑换或拿到奖品。",
  "认可表达顺着本篇活动信息或真实使用感受自然说出来。",
];

const splitOptions = (value) =>
  String(value ?? "")
    .split("||")
    .map((item) => item.trim())
    .filter(Boolean);
const joinOptions = (items) => [...new Set(items.filter(Boolean))].join("||");
const parseJsonOptions = (value) => {
  const parsed = JSON.parse(String(value ?? "[]"));
  return Array.isArray(parsed) ? parsed.map((item) => String(item).trim()).filter(Boolean) : [];
};
const allDirections = [
  ...new Set(rows.flatMap((row) => parseJsonOptions(row[directionOptionsIndex]))),
];
const directDirection = allDirections.find((item) =>
  item.startsWith("直给点说自己参加了活动"),
);
const informedDirection = allDirections.find((item) =>
  item.startsWith("从哪里得知了a2的什么活动"),
);
const stackedDirection = allDirections.find((item) =>
  item.includes("发现福利不是单层的"),
);

for (const row of rows) {
  const ruleName = String(row[ruleNameIndex] ?? "");
  const isInformed = ruleName.endsWith("｜信息了解后的认可");
  const isStacked = ruleName.includes("｜多重福利叠加｜");
  let directionOptions;
  if (isInformed) {
    directionOptions = [
      informedDirection,
      directDirection,
      ...(isStacked ? [stackedDirection] : []),
    ].filter(Boolean);
  } else {
    directionOptions = allDirections.filter(
      (item) =>
        !item.startsWith("先说自己之前就各种渠道听说了a2至初每批") &&
        !item.includes("活动页面中演示了如何扫罐底码") &&
        !item.includes("发现福利不是单层的") &&
        !item.startsWith("从哪里得知了a2的什么活动"),
    );
  }
  row[directionIndex] = directionOptions[0] ?? String(row[directionIndex] ?? "");
  row[directionOptionsIndex] = JSON.stringify(directionOptions);

  row[activityIndex] = joinOptions(
    splitOptions(row[activityIndex]).filter(
      (item) =>
        !item.includes("看看品质溯源信息就能参与抽奖") &&
        item !== ambiguousPointsContent,
    ),
  );
  row[detectionIndex] = "a2至初现在每批都有检测。";
  row[recognitionIndex] = JSON.stringify(
    parseJsonOptions(row[recognitionIndex]).filter(
      (item) => item !== corporateRecognitionCandidate,
    ),
  );

  row[instructionIndex] = conciseInstruction;
  row[writingIndex] = "";
  row[generationIndex] = "";
  row[hardBoundaryIndex] = joinOptions(conciseBoundaries);

}

const outputMatrix = [headers, ...rows];
sheet.getRangeByIndexes(0, 0, outputMatrix.length, headers.length).values = outputMatrix;
sheet.getRangeByIndexes(0, 0, 1, headers.length).format = {
  fill: "#5B2C6F",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
};
sheet.getRangeByIndexes(1, 0, rows.length, headers.length).format.wrapText = true;
sheet.freezePanes.freezeRows(1);
sheet.showGridLines = false;
sheet.getRangeByIndexes(0, 0, outputMatrix.length, headers.length).format.columnWidth = 30;

const inspection = await workbook.inspect({
  kind: "table",
  range: `业务规则!A1:P${outputMatrix.length}`,
  include: "values",
  tableMaxRows: 5,
  tableMaxCols: 16,
  tableMaxCellChars: 160,
  maxChars: 10000,
});
process.stdout.write(`${inspection.ndjson}\n`);

for (const searchTerm of [
  "看看品质溯源信息就能参与抽奖",
  ambiguousPointsContent,
  enumeratedNegativeBoundary,
  abstractNegativeBoundary,
  corporateRecognitionCandidate,
  conciseInstruction,
  ...conciseBoundaries,
  "a2至初现在每批都有检测。",
  "本来以为—结果一看—而且—反正",
]) {
  const check = await workbook.inspect({
    kind: "match",
    searchTerm,
    options: { maxResults: 30 },
    maxChars: 6000,
  });
  process.stdout.write(`${check.ndjson}\n`);
}

await fs.mkdir(outputDir, { recursive: true });
const preview = await workbook.render({
  sheetName: "业务规则",
  range: `A1:P${outputMatrix.length}`,
  scale: 0.65,
  format: "png",
});
await fs.writeFile(previewPng, new Uint8Array(await preview.arrayBuffer()));

const csvEscape = (value) => {
  const text = String(value ?? "");
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};
const outputText = `\uFEFF${outputMatrix
  .map((row) => row.map(csvEscape).join(","))
  .join("\n")}\n`;
await fs.writeFile(outputCsv, outputText, "utf8");

process.stdout.write(
  `${JSON.stringify({ outputCsv, previewPng, rowCount: rows.length, columnCount: headers.length })}\n`,
);
