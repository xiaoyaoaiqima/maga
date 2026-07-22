import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const workDir = "/Users/luxifa/maga/tmp/a2_reiyu_followup_audit_20260721";
const outputDir = "/Users/luxifa/maga/outputs/a2_reiyu_followup_audit_20260721";
const remaining = JSON.parse(await fs.readFile(`${workDir}/remaining_processed.json`, "utf8"));
const newItems = JSON.parse(await fs.readFile(`${workDir}/new_processed.json`, "utf8"));

const remainingUsable = remaining.filter((item) => item.final_status === "usable");
const newUsable = newItems.filter((item) => item.final_status === "usable");
const newProblems = newItems.filter((item) => item.final_status === "hard_problem");

if (remainingUsable.length !== 294) throw new Error(`remaining usable count: ${remainingUsable.length}`);
if (newUsable.length !== 198) throw new Error(`new usable count: ${newUsable.length}`);
if (newProblems.length !== 2) throw new Error(`new problem count: ${newProblems.length}`);

const remainingMatrix = [
  ["原始行号", "标题", "正文", "分类", "处理结果", "处理说明"],
  ...remainingUsable.map((item) => [
    item.source_row,
    item.title,
    item.body,
    item.category,
    "可用",
    item.was_rewritten ? "已按后链路做最小修复并复审通过" : "审核通过",
  ]),
];

const newMatrix = [
  ["Excel行号", "ID", "Content ID", "标题", "正文", "上下文变量(context_list)", "处理结果", "处理说明", "创建时间"],
  ...newUsable.map((item) => {
    let note = "审核通过";
    if (item.excel_row === 57) {
      note = "人工校准放行：会员升级可同时提抽奖与积分，机制和奖品归属正确";
    } else if (item.was_model_rewritten) {
      note = "已轻修并复审通过";
    } else if (item.deterministic_changed) {
      note = "已做确定性规范化并复审通过";
    }
    return [
      item.excel_row,
      item.ID,
      item["Content ID"],
      item.title,
      item.body,
      item["上下文变量(context_list)"],
      "可用",
      note,
      item["创建时间"],
    ];
  }),
];

const problemReasons = new Map([
  [51, ["积分奖品归属错误", "把夏凉被写成积分兑换的礼品；夏凉被属于抽奖奖品。"]],
  [54, ["抽奖奖品归属错误", "写成‘有人抽到了积分’；积分不是抽奖奖品。"]],
]);
const problemMatrix = [
  ["Excel行号", "ID", "Content ID", "标题", "正文", "活动内容", "问题类型", "问题说明", "处理结果"],
  ...newProblems.map((item) => {
    const reason = problemReasons.get(item.excel_row);
    if (!reason) throw new Error(`missing calibrated reason for row ${item.excel_row}`);
    return [
      item.excel_row,
      item.ID,
      item["Content ID"],
      item.title,
      item.body,
      item.activity_type,
      reason[0],
      reason[1],
      "删除",
    ];
  }),
];

function csvCell(value) {
  return `"${String(value ?? "").replaceAll('"', '""')}"`;
}

function columnName(count) {
  let value = count;
  let name = "";
  while (value > 0) {
    value -= 1;
    name = String.fromCharCode(65 + (value % 26)) + name;
    value = Math.floor(value / 26);
  }
  return name;
}

async function buildCsv({ sheetName, matrix, outputPath, previewPath }) {
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add(sheetName);
  sheet.getRangeByIndexes(0, 0, matrix.length, matrix[0].length).values = matrix;
  sheet.freezePanes.freezeRows(1);
  sheet.getRangeByIndexes(0, 0, 1, matrix[0].length).format = {
    fill: "#1F4E78",
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
  };
  sheet.getRangeByIndexes(0, 0, Math.min(matrix.length, 10), matrix[0].length).format.wrapText = true;
  matrix[0].forEach((header, index) => {
    let widthPx = 105;
    if (header === "标题") widthPx = 220;
    if (header === "正文") widthPx = 520;
    if (header === "上下文变量(context_list)") widthPx = 300;
    if (header === "处理说明" || header === "问题说明") widthPx = 300;
    sheet.getRangeByIndexes(0, index, matrix.length, 1).format.columnWidthPx = widthPx;
  });
  sheet.getRangeByIndexes(0, 0, 1, matrix[0].length).format.rowHeightPx = 34;
  const lastColumn = columnName(matrix[0].length);
  const preview = await workbook.render({
    sheetName,
    range: `A1:${lastColumn}${Math.min(matrix.length, 5)}`,
    scale: 1,
    format: "png",
  });
  await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
  const values = sheet.getUsedRange(true).values;
  const csvText = `\uFEFF${values.map((row) => row.map(csvCell).join(",")).join("\r\n")}\r\n`;
  await fs.writeFile(outputPath, csvText, "utf8");

  const verified = await Workbook.fromCSV(csvText.replace(/^\uFEFF/, ""), { sheetName: "验证" });
  const verifyValues = verified.worksheets.getItem("验证").getUsedRange(true).values;
  const inspection = await verified.inspect({
    kind: "table",
    range: `验证!A1:${lastColumn}${Math.min(verifyValues.length, 5)}`,
    include: "values",
    tableMaxRows: 5,
    tableMaxCols: matrix[0].length,
    maxChars: 5000,
  });
  return {
    rowCount: verifyValues.length,
    columnCount: verifyValues[0]?.length || 0,
    inspection: inspection.ndjson,
  };
}

const combinedUsable = [...remainingUsable, ...newUsable];
const bodyCounts = new Map();
for (const item of combinedUsable) bodyCounts.set(item.body, (bodyCounts.get(item.body) || 0) + 1);
const duplicateBodies = [...bodyCounts.entries()].filter(([, count]) => count > 1);
const missingKeyword = combinedUsable.filter((item) => !item.body.includes("a2至初"));
const residualFormal = [
  ...remainingUsable.filter((item) => (item.formal_hits || []).length),
  ...newUsable.filter((item) => (item.residual_formal_hits || []).length),
];
if (duplicateBodies.length) throw new Error(`duplicate bodies: ${duplicateBodies.length}`);
if (missingKeyword.length) throw new Error(`missing a2至初: ${missingKeyword.length}`);
if (residualFormal.length) throw new Error(`formal residuals: ${residualFormal.length}`);

await fs.mkdir(outputDir, { recursive: true });
const remainingPath = `${outputDir}/A2礼遇_剩余301篇_清理后可用294篇.csv`;
const newPath = `${outputDir}/A2礼遇_新200篇_审核后可用198篇.csv`;
const problemPath = `${outputDir}/A2礼遇_新200篇_明确问题2篇.csv`;
const remainingVerify = await buildCsv({
  sheetName: "剩余可用294篇",
  matrix: remainingMatrix,
  outputPath: remainingPath,
  previewPath: `${workDir}/remaining_usable_preview.png`,
});
const newVerify = await buildCsv({
  sheetName: "新增可用198篇",
  matrix: newMatrix,
  outputPath: newPath,
  previewPath: `${workDir}/new_usable_preview.png`,
});
const problemVerify = await buildCsv({
  sheetName: "新增问题2篇",
  matrix: problemMatrix,
  outputPath: problemPath,
  previewPath: `${workDir}/new_problem_preview.png`,
});

if (remainingVerify.rowCount !== 295 || remainingVerify.columnCount !== 6) throw new Error("remaining CSV verification failed");
if (newVerify.rowCount !== 199 || newVerify.columnCount !== 9) throw new Error("new CSV verification failed");
if (problemVerify.rowCount !== 3 || problemVerify.columnCount !== 9) throw new Error("problem CSV verification failed");

const summary = {
  remaining_source: remaining.length,
  remaining_usable: remainingUsable.length,
  remaining_deleted_rows: remaining.filter((item) => item.final_status === "deleted_hard").map((item) => item.source_row),
  new_source: newItems.length,
  new_usable: newUsable.length,
  new_problem_rows: newProblems.map((item) => item.excel_row),
  combined_duplicate_bodies: duplicateBodies.length,
  missing_required_keyword: missingKeyword.length,
  residual_formal_hits: residualFormal.length,
  verify_shapes: {
    remaining: [remainingVerify.rowCount, remainingVerify.columnCount],
    new_usable: [newVerify.rowCount, newVerify.columnCount],
    new_problems: [problemVerify.rowCount, problemVerify.columnCount],
  },
  outputs: { remainingPath, newPath, problemPath },
};
await fs.writeFile(`${workDir}/output_summary.json`, JSON.stringify(summary, null, 2), "utf8");
console.log(JSON.stringify(summary, null, 2));
