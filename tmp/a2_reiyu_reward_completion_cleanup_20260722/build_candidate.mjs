import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const basePath =
  "/Users/luxifa/maga/outputs/a2_reiyu_positive_usage_and_loyalty_20260722/" +
  "a2礼遇_D老客了解信息后更认可.csv";
const outputDir = "/Users/luxifa/maga/outputs/a2_reiyu_reward_completion_cleanup_20260722";
const candidatePath = `${outputDir}/a2礼遇_F强化禁止虚构领奖并删除冗余路径约束.csv`;
const previewPath = `${outputDir}/a2礼遇_F强化禁止虚构领奖并删除冗余路径约束_预览.png`;

const singleSourceRule = "每篇只选择一个活动了解途径，不得把多个了解来源叠加成同一次发现经历。";
const oldInformationRule =
  "本条认可路径是信息了解后的认可：只根据活动和每批检测信息表达品牌感受，不补写宝宝长期使用结果、转奶或回归经历。";
const loyalRecognitionRule =
  "本条认可路径是老客了解信息后更认可：可以自然交代长期购买、老客身份或简短使用背景；本次认可提升要由活动和每批检测信息承接，不必展开宝宝状态或产品效果。";
const rewardCompletionRule =
  "标题和正文只能介绍活动可兑换、可领取或可抽取什么；禁止写自己已经领了、领到、收到、拿到、兑到、换到或中奖，也不要虚构任何已经得到奖品的经历。";

const csvEscape = (value) => {
  const text = String(value ?? "");
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};

const baseText = await fs.readFile(basePath, "utf8");
const baseWorkbook = await Workbook.fromCSV(baseText, { sheetName: "业务规则" });
const baseValues = baseWorkbook.worksheets.getItem("业务规则").getUsedRange(true).values;
const headers = baseValues[0].map((value) => String(value ?? "").replace(/^\uFEFF/, ""));
const nameIndex = headers.indexOf("业务规则名称");
const boundaryIndex = headers.indexOf("硬边界");
if (nameIndex < 0 || boundaryIndex < 0) throw new Error("missing required columns");

const baseRows = baseValues.slice(1).map((row) => headers.map((_, index) => String(row[index] ?? "")));
let singleSourceRemoved = 0;
let loyalRecognitionRemoved = 0;
let rewardRuleAdded = 0;

const candidateRows = baseRows.map((row) => {
  const copy = [...row];
  const boundaries = copy[boundaryIndex].split("||").filter(Boolean);
  const filtered = [];
  for (const boundary of boundaries) {
    if (boundary === singleSourceRule) {
      singleSourceRemoved += 1;
      continue;
    }
    if (boundary === loyalRecognitionRule || boundary === oldInformationRule) {
      loyalRecognitionRemoved += 1;
      continue;
    }
    filtered.push(boundary);
  }
  if (!filtered.includes(rewardCompletionRule)) {
    const activityRuleIndex = filtered.findIndex((value) => value.startsWith("本条主活动是"));
    filtered.splice(activityRuleIndex >= 0 ? activityRuleIndex + 1 : 0, 0, rewardCompletionRule);
    rewardRuleAdded += 1;
  }
  copy[boundaryIndex] = filtered.join("||");
  return copy;
});

if (singleSourceRemoved !== 16) {
  throw new Error(`expected 16 single-source removals, got ${singleSourceRemoved}`);
}
if (loyalRecognitionRemoved !== 8) {
  throw new Error(`expected 8 path-rule removals, got ${loyalRecognitionRemoved}`);
}
if (rewardRuleAdded !== 16) {
  throw new Error(`expected 16 reward-rule additions, got ${rewardRuleAdded}`);
}

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

const rewardInspect = await workbook.inspect({
  kind: "match",
  searchTerm: "禁止写自己已经领了、领到、收到、拿到、兑到、换到或中奖",
  options: { useRegex: false, maxResults: 20 },
  summary: "虚构领奖规则",
  maxChars: 8000,
});
const removedInspect = await workbook.inspect({
  kind: "match",
  searchTerm: "每篇只选择一个活动了解途径|本条认可路径是老客了解信息后更认可|本条认可路径是信息了解后的认可",
  options: { useRegex: true, maxResults: 30 },
  summary: "已删除规则残留扫描",
  maxChars: 5000,
});
process.stdout.write(`${rewardInspect.ndjson}\n`);
process.stdout.write(`${removedInspect.ndjson}\n`);
process.stdout.write(
  `${JSON.stringify(
    {
      candidate_path: candidatePath,
      preview_path: previewPath,
      business_rule_rows: candidateRows.length,
      single_source_removed: singleSourceRemoved,
      recognition_path_removed: loyalRecognitionRemoved,
      reward_rule_added: rewardRuleAdded,
      diff_count: diffs.length,
      diff_columns: [...new Set(diffs.map((diff) => diff.column))],
    },
    null,
    2,
  )}\n`,
);
