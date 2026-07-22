import crypto from "node:crypto";
import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const workDir = "/Users/luxifa/maga/tmp/a2_reiyu_backup_audit_20260721";
const outputDir = "/Users/luxifa/maga/outputs/a2_reiyu_backup_audit_20260721";
const usablePath = `${outputDir}/A2礼遇_可用500篇_集罐70其他30.csv`;
const remainingPath = `${outputDir}/A2礼遇_剩余301篇_含问题.csv`;

const source = JSON.parse(await fs.readFile(`${workDir}/source_rows.json`, "utf8"));
const scan = JSON.parse(await fs.readFile(`${workDir}/deterministic_scan.json`, "utf8"));
const businessReviews = JSON.parse(await fs.readFile(`${workDir}/llm_review.json`, "utf8"));
const logicReviews = JSON.parse(await fs.readFile(`${workDir}/common_logic_review.json`, "utf8"));
const forbiddenEntries = JSON.parse(await fs.readFile(`${workDir}/forbidden_terms_response.json`, "utf8")).data.items.filter(
  (item) => item.enabled !== false,
);

const businessByRow = new Map(businessReviews.map((item) => [Number(item.source_row), item]));
const logicByRow = new Map(logicReviews.map((item) => [Number(item.source_row), item]));
const scanByRow = new Map(scan.results.map((item) => [Number(item.source_row), item]));

function entryMatches(text, entry) {
  const term = String(entry.term || "");
  if (!term || !text.includes(term)) return false;
  if (entry.match_mode === "activity_prize_context") {
    const cues = ["奖品", "礼品", "兑换", "换到", "换个", "换一", "抽奖", "中奖", "集罐", "能领", "可以领", "活动送", "活动有", "福利有"];
    return text.split(/[\n。！？!?；;]/).some((sentence) => sentence.includes(term) && cues.some((cue) => sentence.includes(cue)));
  }
  if (entry.match_mode === "detection_page_context") {
    return text
      .split(/[\n。！？!?；;]/)
      .some((sentence) => sentence.includes(term) && ["每批", "批批", "检测"].some((cue) => sentence.includes(cue)));
  }
  return true;
}

function formalHits(item) {
  const text = `${item.title}\n${item.body}`;
  return forbiddenEntries.filter((entry) => entryMatches(text, entry));
}

function stableRank(item) {
  return crypto
    .createHash("sha256")
    .update(`a2-reiyu-500-20260721|${item.source_row}|${item.title}`)
    .digest("hex");
}

function isCleanCandidate(item) {
  const business = businessByRow.get(item.source_row);
  const logic = logicByRow.get(item.source_row);
  return (
    business?.review?.business_usability_tier === "direct_pool" &&
    item.hits.length === 0 &&
    formalHits(item).length === 0 &&
    logic?.review?.pass === true &&
    !logic?.error
  );
}

const allItems = scan.results;
const cleanCandidates = allItems.filter(isCleanCandidate);
const byCategory = {
  "12罐": cleanCandidates.filter((item) => item.effective_category === "12罐").sort((a, b) => stableRank(a).localeCompare(stableRank(b))),
  "其他罐": cleanCandidates.filter((item) => item.effective_category === "其他罐").sort((a, b) => stableRank(a).localeCompare(stableRank(b))),
  "其他": cleanCandidates.filter((item) => item.effective_category === "其他").sort((a, b) => stableRank(a).localeCompare(stableRank(b))),
};

if (byCategory["12罐"].length < 297 || byCategory["其他罐"].length < 53 || byCategory["其他"].length < 150) {
  throw new Error(`insufficient clean candidates: ${JSON.stringify(Object.fromEntries(Object.entries(byCategory).map(([key, value]) => [key, value.length])))}`);
}

const selectedRows = new Set([
  ...byCategory["12罐"].slice(0, 297).map((item) => item.source_row),
  ...byCategory["其他罐"].slice(0, 53).map((item) => item.source_row),
  ...byCategory["其他"].slice(0, 150).map((item) => item.source_row),
]);
const selected = allItems.filter((item) => selectedRows.has(item.source_row)).sort((a, b) => a.source_row - b.source_row);
const remaining = allItems.filter((item) => !selectedRows.has(item.source_row)).sort((a, b) => a.source_row - b.source_row);

const confirmedHardRows = new Map([
  [47, ["旧罐资格与虚构领奖", "暗示原有囤货可参加，且写了娃已拿到小车。"]],
  [272, ["积分奖品归属错误", "把夏凉被、金手链等抽奖奖品写成积分兑换。"]],
  [315, ["积分奖品归属错误", "把夏凉被写成积分兑换礼品。"]],
  [318, ["集罐兑换积分错误", "写成集罐可以兑换积分。"]],
  [414, ["积分奖品归属错误", "把小车车写成积分兑换奖品。"]],
  [487, ["旧罐资格错误", "暗示家里原有罐子可参加本次集罐。"]],
  [523, ["集罐档位错误", "写成18罐换小车车，正确应为18罐换婴儿车。"]],
  [627, ["旧罐资格错误", "写成奶粉喝完后把罐子存着参加活动。"]],
]);
const businessFalsePositiveRows = new Set([141, 455, 626, 631, 696, 728]);
const lightScanCodes = new Set([
  "instruction_leakage",
  "page_flip_detection",
  "activity_naming_explanation",
  "narrative_consistency",
  "birth_no_switch_vs_transition",
  "soft_rewrite_terms",
]);

function remainingReview(item) {
  const hardOverride = confirmedHardRows.get(item.source_row);
  if (hardOverride) return { status: "有问题", issueType: hardOverride[0], reason: hardOverride[1] };

  const logic = logicByRow.get(item.source_row);
  if (logic?.review?.pass === false) {
    const issues = logic.review.issues || [];
    return {
      status: "有问题",
      issueType: issues.map((issue) => issue.code).join("；") || "通用逻辑问题",
      reason: issues.map((issue) => `${issue.evidence}：${issue.reason}`).join("；") || logic.review.overall_reason || "通用逻辑审核未通过",
    };
  }

  const formal = formalHits(item);
  const hardFormal = formal.filter((entry) => entry.enforcement === "hard_ban");
  if (hardFormal.length) {
    return {
      status: "有问题",
      issueType: `硬拦截：${hardFormal.map((entry) => entry.term).join("、")}`,
      reason: hardFormal.map((entry) => entry.reason || entry.term).join("；"),
    };
  }
  const rewriteFormal = formal.filter((entry) => entry.enforcement === "model_rewrite");
  const replaceFormal = formal.filter((entry) => entry.enforcement === "replace");
  if (rewriteFormal.length || replaceFormal.length) {
    const terms = [...rewriteFormal, ...replaceFormal].map((entry) => entry.term);
    return {
      status: "需轻修",
      issueType: `后链路词项：${terms.join("、")}`,
      reason: "可按现行后链路规则做语义改写或确定性规范化。",
    };
  }

  const lightHits = item.hits.filter((hit) => lightScanCodes.has(hit.code));
  if (lightHits.length) {
    return {
      status: "需轻修",
      issueType: lightHits.map((hit) => hit.code).join("；"),
      reason: "存在指令痕迹、避用表达或局部身份/页面承接问题，建议最小改写。",
    };
  }

  const business = businessByRow.get(item.source_row);
  if (
    business?.review?.business_usability_tier &&
    business.review.business_usability_tier !== "direct_pool" &&
    !businessFalsePositiveRows.has(item.source_row)
  ) {
    const issues = business.review.issues || [];
    return {
      status: business.review.business_usability_tier === "light_fix_usable" ? "需轻修" : "待复核",
      issueType: issues.map((issue) => issue.code).join("；") || business.review.business_usability_tier,
      reason: issues.map((issue) => `${issue.evidence}：${issue.reason}`).join("；") || business.review.business_usability_reason || "模型提示需复核。",
    };
  }

  return { status: "可用未入选", issueType: "配额外", reason: "审核通过，但未进入本次500篇配额。" };
}

function csvCell(value) {
  const text = String(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}

async function buildCsv({ sheetName, matrix, outputPath, previewPath }) {
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add(sheetName);
  sheet.getRangeByIndexes(0, 0, matrix.length, matrix[0].length).values = matrix;
  sheet.freezePanes.freezeRows(1);
  sheet.getRangeByIndexes(0, 0, 1, matrix[0].length).format = {
    fill: "#1F4E78",
    font: { bold: true, color: "#FFFFFF" },
  };
  sheet.getRangeByIndexes(0, 0, Math.min(matrix.length, 12), matrix[0].length).format.wrapText = true;
  const preview = await workbook.render({ sheetName, range: `A1:${String.fromCharCode(64 + Math.min(matrix[0].length, 26))}${Math.min(matrix.length, 12)}`, scale: 1, format: "png" });
  await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
  const values = sheet.getUsedRange(true).values;
  const csvText = `\uFEFF${values.map((row) => row.map(csvCell).join(",")).join("\r\n")}\r\n`;
  await fs.writeFile(outputPath, csvText, "utf8");
  const verifyWorkbook = await Workbook.fromCSV(csvText.replace(/^\uFEFF/, ""), { sheetName: "验证" });
  const verifyValues = verifyWorkbook.worksheets.getItem("验证").getUsedRange(true).values;
  return { rowCount: verifyValues.length, columnCount: verifyValues[0]?.length || 0 };
}

const usableMatrix = [
  ["原始行号", "标题", "正文", "分类"],
  ...selected.map((item) => [item.source_row, item.title, item.body, item.effective_category]),
];
const remainingMatrix = [
  ["原始行号", "标题", "正文", "原始分类", "审核分类", "审核结论", "问题类型", "问题说明", "抽检标记", "反馈意见", "正向词出现次数", "正文字数", "标题字数"],
  ...remaining.map((item) => {
    const review = remainingReview(item);
    const original = item.source_values;
    return [
      item.source_row,
      item.title,
      item.body,
      item.source_category,
      item.effective_category,
      review.status,
      review.issueType,
      review.reason,
      original[2] ?? "",
      original[3] ?? "",
      original[4] ?? "",
      original[5] ?? "",
      original[6] ?? "",
    ];
  }),
];

await fs.mkdir(outputDir, { recursive: true });
const usableVerify = await buildCsv({
  sheetName: "可用500篇",
  matrix: usableMatrix,
  outputPath: usablePath,
  previewPath: `${workDir}/usable_preview.png`,
});
const remainingVerify = await buildCsv({
  sheetName: "剩余301篇",
  matrix: remainingMatrix,
  outputPath: remainingPath,
  previewPath: `${workDir}/remaining_preview.png`,
});

const selectedCategoryCounts = Object.fromEntries(
  ["12罐", "其他罐", "其他"].map((category) => [category, selected.filter((item) => item.effective_category === category).length]),
);
const remainingStatusCounts = {};
for (const item of remaining) {
  const status = remainingReview(item).status;
  remainingStatusCounts[status] = (remainingStatusCounts[status] || 0) + 1;
}
const selectedFormalResiduals = selected.flatMap((item) => formalHits(item).map((entry) => ({ source_row: item.source_row, term: entry.term })));
const selectedLogicFailures = selected.filter((item) => logicByRow.get(item.source_row)?.review?.pass !== true).map((item) => item.source_row);
const selectedScanHits = selected.filter((item) => item.hits.length).map((item) => ({ source_row: item.source_row, hits: item.hits }));
const selectedBusinessFailures = selected
  .filter((item) => businessByRow.get(item.source_row)?.review?.business_usability_tier !== "direct_pool")
  .map((item) => item.source_row);
const selectedBodies = new Set();
const duplicateSelectedRows = [];
for (const item of selected) {
  if (selectedBodies.has(item.body)) duplicateSelectedRows.push(item.source_row);
  selectedBodies.add(item.body);
}

if (selected.length !== 500 || remaining.length !== 301 || selectedRows.size !== 500) throw new Error("delivery row count mismatch");
if (selectedCategoryCounts["12罐"] + selectedCategoryCounts["其他罐"] !== 350 || selectedCategoryCounts["其他"] !== 150) {
  throw new Error(`delivery ratio mismatch: ${JSON.stringify(selectedCategoryCounts)}`);
}
if (usableVerify.rowCount !== 501 || remainingVerify.rowCount !== 302) throw new Error("CSV parse verification failed");
if (selectedFormalResiduals.length || selectedLogicFailures.length || selectedScanHits.length || selectedBusinessFailures.length || duplicateSelectedRows.length) {
  throw new Error(JSON.stringify({ selectedFormalResiduals, selectedLogicFailures, selectedScanHits, selectedBusinessFailures, duplicateSelectedRows }));
}

const summary = {
  source_rows: allItems.length,
  selected_rows: selected.length,
  remaining_rows: remaining.length,
  selected_category_counts: selectedCategoryCounts,
  collect_can_total: selectedCategoryCounts["12罐"] + selectedCategoryCounts["其他罐"],
  other_total: selectedCategoryCounts["其他"],
  remaining_status_counts: remainingStatusCounts,
  usable_csv_shape: [usableVerify.rowCount, usableVerify.columnCount],
  remaining_csv_shape: [remainingVerify.rowCount, remainingVerify.columnCount],
  selected_formal_residuals: selectedFormalResiduals.length,
  selected_logic_failures: selectedLogicFailures.length,
  selected_scan_hits: selectedScanHits.length,
  selected_business_failures: selectedBusinessFailures.length,
  duplicate_selected_rows: duplicateSelectedRows.length,
  usable_path: usablePath,
  remaining_path: remainingPath,
};
await fs.writeFile(`${outputDir}/delivery_summary.json`, JSON.stringify(summary, null, 2), "utf8");
console.log(JSON.stringify(summary, null, 2));
