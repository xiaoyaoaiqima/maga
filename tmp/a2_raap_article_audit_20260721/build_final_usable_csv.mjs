import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const inputPath = "/Users/luxifa/Downloads/文章池导出_2026-07-21.xlsx";
const outputDir = "/Users/luxifa/maga/outputs/a2_raap_article_audit_20260721";
const outputPath = `${outputDir}/A2礼遇_RAAP文章池_最终可用186篇.csv`;
const rewriteLogPath = `${outputDir}/A2礼遇_RAAP文章池_轻修记录.json`;
const baseUrl = "http://127.0.0.1:5100";

const holdRows = new Set([6, 22, 31, 32, 66, 77, 82, 101, 102, 104, 145, 150, 164, 182]);

const rewriteInstructions = new Map([
  [8, "删除并自然改写‘顺手’，保留邻居宝妈、集罐12罐换1罐、每批检测和产品体验。"],
  [35, "本篇主活动必须改回集罐12罐兑换1罐奶粉；不要以抽奖或老客回馈作为主活动。保留每批检测和原有产品体验，不新增奖品，也绝对不要新增老客新客都能参加、参与资格等规则。不得写攒罐、攒罐子、喝完攒罐，直接说参加集罐。"],
  [62, "删除并自然改写‘顺手’，保留同事宝妈来源、买12罐到手13罐的含义、每批检测和产品体验。"],
  [88, "不要写罐子攒起来或攒罐子，直接说参加集罐；不要暗示旧罐或活动前购买可以参加。保留12罐兑1罐、罐底码查报告和产品体验。"],
  [111, "本篇主活动必须改回集罐12罐兑换1罐奶粉；不要只写抽奖和老客回馈。保留朋友来源、每批检测和原有产品体验，不新增奖品或中奖经历。"],
  [122, "不要写把罐子攒起来或攒罐子，直接说参加集罐；不要暗示旧罐。保留官号来源、12罐兑1罐、页面演示罐底码查报告和产品体验。"],
  [137, "不要写罐子攒起来、攒罐或攒罐子，直接说集罐；不要暗示旧罐。必须明确写12罐兑换1罐奶粉；可以泛提其他正确集罐奖品，保留每批检测和产品体验。"],
  [151, "不要写罐子攒起来或攒罐子，直接说集罐；不要暗示旧罐。保留邻居来源、12罐兑1罐、页面演示罐底码查报告和产品体验。"],
  [155, "删除‘翻到页面’的动作，直接自然承接活动页面提到a2至初每批都有检测；保留puq、12罐兑1罐和产品体验。"],
  [160, "删除‘翻到活动页面’的动作，直接写活动页面提到a2至初每批都有检测；保留原活动机制、来源和产品体验。"],
  [173, "只调整标题，使其与正文的集罐12罐兑1罐活动一致；标题不要写抢到、中奖或稀缺。正文尽量不改。"],
  [197, "不要写罐子攒起来或攒罐子，直接说集罐；不要暗示旧罐。保留🌍来源、12罐兑1罐、罐底码查报告和产品体验。"],
]);

function normalizeDeterministic(title, body) {
  title = title.replaceAll("眼睛👀", "👀").replaceAll("👀眼睛", "👀");
  body = body
    .replaceAll("眼睛👀", "👀")
    .replaceAll("👀眼睛", "👀")
    .replaceAll("💩一直软便便", "💩一直很软");
  const replacements = [
    ["便便", "💩"],
    ["眼睛", "👀"],
    ["免费", "🆓"],
    ["FL", "福利"],
    ["a2蛋白", "A2蛋白"],
    ["母r", "母R"],
  ];
  let nextTitle = title;
  let nextBody = body;
  for (const [from, to] of replacements) {
    nextTitle = nextTitle.split(from).join(to);
    nextBody = nextBody.split(from).join(to);
  }
  nextTitle = nextTitle.replaceAll("👀👀", "👀").replaceAll("💩💩", "💩");
  nextBody = nextBody.replaceAll("👀👀", "👀").replaceAll("💩💩", "💩").replaceAll("💩一直软💩", "💩一直很软");
  return { title: nextTitle, body: nextBody };
}

function extractJson(text) {
  const clean = String(text || "").trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  try {
    return JSON.parse(clean);
  } catch {
    const start = clean.indexOf("{");
    const end = clean.lastIndexOf("}");
    if (start < 0 || end <= start) throw new Error("rewrite did not return JSON");
    return JSON.parse(clean.slice(start, end + 1));
  }
}

async function rewriteOne(item) {
  const instruction = rewriteInstructions.get(item.excelRow);
  const response = await fetch(`${baseUrl}/api/v1/content-agent/prompt-debug/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model_code: "qwen-plus",
      temperature: 0.2,
      max_tokens: 1800,
      system_prompt: [
        "你是a2礼遇UGC后链路编辑，只做最小必要修改。",
        "必须保留原人物、活动来源、集罐机制、每批检测信息和产品体验。",
        "不得新增奖品、中奖、兑换成功、旧罐参与或新的了解来源。",
        "不得写攒罐、攒罐子、罐子攒起来或喝完攒罐，直接写集罐。",
        "puq、pyq、🆓均允许保留。a2和a2至初中的a必须小写。",
        "只输出JSON：{\"title\":\"...\",\"body\":\"...\"}。",
      ].join("\n"),
      prompt: JSON.stringify({
        instruction,
        title: item.title,
        body: item.body,
      }),
    }),
  });
  if (!response.ok) throw new Error(`rewrite HTTP ${response.status}`);
  const payload = await response.json();
  if (!payload?.data?.success) throw new Error(payload?.data?.error_message || "rewrite failed");
  const result = extractJson(payload.data.content);
  if (!String(result.title || "").trim() || !String(result.body || "").trim()) {
    throw new Error("rewrite returned empty title/body");
  }
  return { title: String(result.title).trim(), body: String(result.body).trim() };
}

function csvCell(value) {
  const text = String(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItem("文章池数据");
const values = sheet.getUsedRange(true).values;
const articles = values.slice(1).map((row, index) => {
  const context = String(row[4] || "");
  const normalized = normalizeDeterministic(String(row[2] || ""), String(row[3] || ""));
  return {
    excelRow: index + 2,
    title: normalized.title,
    body: normalized.body,
    context,
  };
});

const rewriteResults = new Map();
const forceRerunRows = new Set([35, 137]);
try {
  const cached = JSON.parse(await fs.readFile(rewriteLogPath, "utf8"));
  for (const item of cached.rewrites || []) {
    if (rewriteInstructions.has(item.excelRow) && !forceRerunRows.has(item.excelRow)) {
      rewriteResults.set(item.excelRow, { title: item.title, body: item.body });
    }
  }
} catch {}
const rewriteTargets = articles.filter((item) => rewriteInstructions.has(item.excelRow) && !rewriteResults.has(item.excelRow));
let cursor = 0;
const workers = Array.from({ length: 5 }, async () => {
  while (cursor < rewriteTargets.length) {
    const current = rewriteTargets[cursor];
    cursor += 1;
    let lastError;
    for (let attempt = 1; attempt <= 3; attempt += 1) {
      try {
        rewriteResults.set(current.excelRow, await rewriteOne(current));
        lastError = undefined;
        break;
      } catch (error) {
        lastError = error;
        if (attempt < 3) await new Promise((resolve) => setTimeout(resolve, 500 * attempt));
      }
    }
    if (lastError) throw new Error(`row ${current.excelRow}: ${lastError.message}`);
  }
});
await Promise.all(workers);

for (const item of articles) {
  const rewritten = rewriteResults.get(item.excelRow);
  if (rewritten) {
    const normalizedRewrite = normalizeDeterministic(rewritten.title, rewritten.body);
    item.title = normalizedRewrite.title;
    item.body = normalizedRewrite.body;
  }
}

const usable = articles.filter((item) => !holdRows.has(item.excelRow));
const residualRules = [
  ["便便", /便便/],
  ["眼睛", /眼睛/],
  ["免费", /免费/],
  ["FL", /(^|[^A-Za-z])FL([^A-Za-z]|$)/],
  ["顺手", /顺手/],
  ["攒罐子", /攒罐|攒罐子|攒着罐子|罐子攒起来|把罐子攒起来/],
  ["翻页发现检测", /翻到(?:活动)?页面[^。！\n]{0,30}(?:每批|检测)/],
];
const residuals = [];
for (const item of usable) {
  const text = `${item.title}\n${item.body}`;
  for (const [code, pattern] of residualRules) {
    if (pattern.test(text)) residuals.push({ excelRow: item.excelRow, code });
  }
  if (rewriteResults.has(item.excelRow)) {
    if (!item.body.includes("a2至初")) residuals.push({ excelRow: item.excelRow, code: "missing_a2至初" });
    if (!/(?:12罐|买12)[^。！\n]{0,35}(?:1罐|一罐|整罐|正装|13罐)/.test(item.body)) {
      residuals.push({ excelRow: item.excelRow, code: "missing_12_to_1_activity" });
    }
    if (!/(?:检测|报告|溯源)/.test(item.body)) {
      residuals.push({ excelRow: item.excelRow, code: "missing_batch_detection" });
    }
    if (/老客新客|新客老客|都能参与|都可以参与/.test(item.body)) {
      residuals.push({ excelRow: item.excelRow, code: "invented_eligibility_rule" });
    }
  }
}
if (residuals.length) {
  throw new Error(`residual review issues: ${JSON.stringify(residuals)}`);
}

const headers = ["标题", "正文", "上下文变量(context_list)"];
const csvLines = [headers.map(csvCell).join(",")];
for (const item of usable) {
  csvLines.push([item.title, item.body, item.context].map(csvCell).join(","));
}
const csvText = `\uFEFF${csvLines.join("\r\n")}\r\n`;
await fs.mkdir(outputDir, { recursive: true });
await fs.writeFile(outputPath, csvText, "utf8");

const verified = await Workbook.fromCSV(csvText.replace(/^\uFEFF/, ""), { sheetName: "可用文章" });
const verifySheet = verified.worksheets.getItem("可用文章");
const verifyValues = verifySheet.getUsedRange(true).values;
if (verifyValues.length !== 187 || verifyValues[0].length !== 3) {
  throw new Error(`CSV verification failed: ${verifyValues.length}x${verifyValues[0]?.length || 0}`);
}
const inspection = await verified.inspect({
  kind: "table",
  range: "可用文章!A1:C6",
  include: "values",
  tableMaxRows: 6,
  tableMaxCols: 3,
  maxChars: 6000,
});

await fs.writeFile(
  rewriteLogPath,
  JSON.stringify({
    excludedRows: [...holdRows].sort((a, b) => a - b),
    rewrittenRows: [...rewriteResults.keys()].sort((a, b) => a - b),
    outputRows: usable.length,
    inspection: inspection.ndjson,
    rewrites: [...rewriteResults.entries()].map(([excelRow, after]) => {
      const before = articles.find((item) => item.excelRow === excelRow);
      return { excelRow, title: after.title, body: after.body, context: before?.context || "" };
    }),
  }, null, 2),
  "utf8",
);

console.log(JSON.stringify({
  outputPath,
  outputRows: usable.length,
  excludedRows: [...holdRows].sort((a, b) => a - b),
  rewrittenRows: [...rewriteResults.keys()].sort((a, b) => a - b),
  verifyShape: [verifyValues.length, verifyValues[0].length],
}, null, 2));
