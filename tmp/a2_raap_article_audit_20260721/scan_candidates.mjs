import fs from "node:fs/promises";

const inputPath = "/Users/luxifa/maga/tmp/a2_raap_article_audit_20260721/extracted_workbooks.json";
const outputPath = "/Users/luxifa/maga/tmp/a2_raap_article_audit_20260721/deterministic_scan.json";
const workbooks = JSON.parse(await fs.readFile(inputPath, "utf8"));
const rows = workbooks[0].sheets[0].values.slice(1);

const checks = [
  ["instruction_leakage", /a2礼遇｜|本篇素材|内容方向|认可依据|产品体验原话|推荐态度原话|夸夸a2|正文[:：]|标题[:：]|卖点|痛点/],
  ["old_can_eligibility", /旧罐|老罐|空罐|以前(?:买|喝|留|攒|存|囤)[^，。；\n]{0,12}罐|之前[^，。；\n]{0,12}罐[^，。；\n]{0,12}(参加|兑换|集罐)/],
  ["bottom_code_activity_entry", /扫罐底码[^，。；\n]{0,20}(抽奖|中奖|集罐|兑换|积分)|(?:抽奖|中奖|集罐|兑换|积分)[^，。；\n]{0,20}扫罐底码/],
  ["fabricated_reward_experience", /(?:已经|成功|真的|刚|终于)?(?:抽中|中奖|兑到|换到|拿到|领到|兑换到)[^，。；\n]{0,20}(旅游|基金|手链|手串|凉被|小车|自行车|奶粉|婴儿车|奖品)/],
  ["activity_naming_explanation", /这个活动(?:叫|名称是)|活动名称是|活动是会员(?:体系)?升级|叫会员礼遇活动/],
  ["source_stacking_surface", /(?:闺蜜|邻居|同事|导购|宝妈|宝爸|朋友)[^，。；\n]{0,20}(?:又|还|同时)[^，。；\n]{0,20}(?:闺蜜|邻居|同事|导购|宝妈|宝爸|朋友|官号|页面)/],
  ["identity_first_try", /一直想(?:买|囤|试)|第一次(?:买|喝|尝试)|准备(?:第一次|开始)(?:喝|买|试)/],
  ["identity_long_term", /一直喝|喝了(?:几个月|半年|一年)|长期喝|继续回购|从出生|没换过|老客|老粉/],
  ["uppercase_a2", /A2至初|A2蛋白|A2源乳|A2蛋白质/],
  ["forbidden_surface", /顺手|顺便|薅羊毛|白嫖|空罐|攒罐子|攒着罐子|小红书|抖音|微信|朋友圈|肠胃|脾胃|母乳|预防针|便秘|厌奶|敏感/],
  ["rule_label_punctuation", /｜/],
];

const findings = [];
const activityCounts = new Map();
const exactBodies = new Map();
const exactTitles = new Map();

for (let index = 0; index < rows.length; index += 1) {
  const row = rows[index];
  const excelRow = index + 2;
  const [id, contentId, title, body, contextText, status, isTest, createdAt] = row;
  let context = {};
  try {
    context = JSON.parse(contextText || "{}");
  } catch {}
  const activity = context["活动内容"] || "未标注";
  activityCounts.set(activity, (activityCounts.get(activity) || 0) + 1);
  exactBodies.set(body, [...(exactBodies.get(body) || []), excelRow]);
  exactTitles.set(title, [...(exactTitles.get(title) || []), excelRow]);

  const hits = [];
  for (const [code, regex] of checks) {
    const match = `${title}\n${body}`.match(regex);
    if (match) hits.push({ code, evidence: match[0] });
  }
  if (hits.some((hit) => hit.code === "identity_first_try") && hits.some((hit) => hit.code === "identity_long_term")) {
    hits.push({ code: "narrative_consistency", evidence: "首次/想尝试与长期使用身份同时出现" });
  }
  if (hits.length) {
    findings.push({ excelRow, id, contentId, title, body, context, status, isTest, createdAt, hits });
  }
}

const duplicateBodies = [...exactBodies.entries()].filter(([, lineNos]) => lineNos.length > 1);
const duplicateTitles = [...exactTitles.entries()].filter(([, lineNos]) => lineNos.length > 1);
const hitCounts = {};
for (const item of findings) {
  for (const hit of item.hits) hitCounts[hit.code] = (hitCounts[hit.code] || 0) + 1;
}

const result = {
  totalRows: rows.length,
  activityCounts: Object.fromEntries([...activityCounts.entries()].sort((a, b) => b[1] - a[1])),
  findingRows: findings.length,
  hitCounts,
  duplicateBodyGroups: duplicateBodies.length,
  duplicateTitleGroups: duplicateTitles.length,
  duplicateBodies: duplicateBodies.slice(0, 20).map(([body, lineNos]) => ({ lineNos, body })),
  duplicateTitles: duplicateTitles.slice(0, 20).map(([title, lineNos]) => ({ lineNos, title })),
  findings,
};

await fs.writeFile(outputPath, JSON.stringify(result, null, 2), "utf8");
console.log(JSON.stringify({
  totalRows: result.totalRows,
  activityCounts: result.activityCounts,
  findingRows: result.findingRows,
  hitCounts: result.hitCounts,
  duplicateBodyGroups: result.duplicateBodyGroups,
  duplicateTitleGroups: result.duplicateTitleGroups,
}, null, 2));
