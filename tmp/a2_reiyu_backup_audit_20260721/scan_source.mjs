import fs from "node:fs/promises";

const inputPath = "/Users/luxifa/maga/tmp/a2_reiyu_backup_audit_20260721/source_rows.json";
const outputPath = "/Users/luxifa/maga/tmp/a2_reiyu_backup_audit_20260721/deterministic_scan.json";

const source = JSON.parse(await fs.readFile(inputPath, "utf8"));
const [headers, ...rows] = source.values;

function effectiveCategory(row) {
  const raw = String(row[7] || "").trim();
  if (raw) return raw;
  const text = `${row[0] || ""}\n${row[1] || ""}`;
  if (/(?:12|十二)罐|买\s*12|买十二|集满\s*12/.test(text)) return "12罐";
  if (/(?:3|三|6|六|18|十八)罐|小车车|自行车|婴儿(?:推)?车/.test(text)) return "其他罐";
  return "其他";
}

function weightedTitleLength(text) {
  let total = 0;
  for (const char of [...String(text || "")]) {
    total += /\p{Extended_Pictographic}/u.test(char) ? 2 : 1;
  }
  return total;
}

const checks = [
  ["missing_title", ({ title }) => !title.trim(), "hard"],
  ["missing_body", ({ body }) => !body.trim(), "hard"],
  ["missing_a2_zhichu", ({ text }) => !text.includes("a2至初") && !text.includes("A2至初"), "hard"],
  ["uppercase_a2_zhichu", ({ text }) => /A2至初/.test(text), "normalize"],
  ["instruction_leakage", ({ text }) => /a2礼遇｜|本篇素材|内容方向|认可依据|产品体验原话|推荐态度原话|夸夸a2|正文[:：]|标题[:：]|卖点|痛点|开始编写|输出格式/.test(text), "light"],
  ["old_can_eligibility", ({ text }) => /旧罐|老罐|空罐|以前(?:买|喝|留|攒|存|囤)[^，。；！\n]{0,16}罐|之前[^，。；！\n]{0,16}罐[^，。；！\n]{0,16}(?:参加|兑换|集罐)|家里(?:正好|刚好|原来|之前)[^，。；！\n]{0,16}(?:几罐|罐子)[^，。；！\n]{0,16}(?:参加|集罐|兑换)|奶粉喝完[^，。；！\n]{0,12}罐子(?:存|留|攒)/.test(text), "hard"],
  ["bottom_code_wrong_mechanism", ({ text }) => /扫(?:罐底码|罐码)[^，。；！\n]{0,24}(?:抽奖|中奖|兑奖|兑换奖品|换奖品)|(?:抽奖|中奖|兑奖|兑换奖品|换奖品)[^，。；！\n]{0,24}扫(?:罐底码|罐码)/.test(text), "hard"],
  ["fabricated_reward_experience", ({ text }) => /(?:已经|成功|真的|刚|终于|当场)?(?:抽中|中奖|兑到|换到|拿到|领到|兑换到)[^，。；！\n]{0,28}(?:旅游|基金|手链|手串|凉被|小车|自行车|奶粉|婴儿车|推车|奖品)|(?:娃|宝宝|孩子)[^，。；！\n]{0,20}(?:拿到|骑上|坐上|看到兑换)[^，。；！\n]{0,20}(?:小车|自行车|婴儿车|推车|奖品)/.test(text), "hard"],
  ["points_collect_prize", ({ text }) => /积分[^，。；！\n]{0,28}(?:换|兑|兑换)[^，。；！\n]{0,20}(?:小车|自行车|奶粉|婴儿车|推车)|(?:小车|自行车|奶粉|婴儿车|推车)[^，。；！\n]{0,24}(?:积分兑换|积分换|积分兑)/.test(text), "hard"],
  ["collect_points_exchange", ({ text }) => /集罐[^，。；！\n]{0,24}(?:换|兑|兑换)[^，。；！\n]{0,16}积分|积分[^，。；！\n]{0,16}(?:集罐兑换|集罐换)/.test(text), "hard"],
  ["lottery_collect_prize", ({ text }) => /(?:抽奖|抽中|中奖)[^，。；！\n]{0,28}(?:小车车|自行车|婴儿车|婴儿推车)|(?:小车车|自行车|婴儿车|婴儿推车)[^，。；！\n]{0,24}(?:抽奖|抽中|中奖)/.test(text), "hard"],
  ["wrong_12_mapping", ({ text }) => /(?:12|十二)罐[^。！\n]{0,24}(?:换|兑|兑换|得|送)[^。！\n]{0,16}(?:自行车|婴儿车|婴儿推车)|(?:换|兑|兑换)[^。！\n]{0,16}(?:自行车|婴儿车|婴儿推车)[^。！\n]{0,24}(?:12|十二)罐/.test(text), "hard"],
  ["wrong_3_mapping", ({ text }) => /(?:3|三)罐[^。！\n]{0,24}(?:换|兑|兑换|得|送)[^。！\n]{0,16}(?:自行车|奶粉|婴儿车|婴儿推车)/.test(text), "hard"],
  ["wrong_6_mapping", ({ text }) => /(?:6|六)罐[^。！\n]{0,24}(?:换|兑|兑换|得|送)[^。！\n]{0,16}(?:奶粉|婴儿车|婴儿推车)/.test(text), "hard"],
  ["wrong_18_mapping", ({ text }) => /(?:18|十八)罐[^。！\n]{0,24}(?:换|兑|兑换|得|送)[^。！\n]{0,16}(?:小车车|自行车|奶粉)/.test(text), "hard"],
  ["registration_claim", ({ text }) => /报名(?:参加|活动)|活动报名|先报名/.test(text), "hard"],
  ["page_flip_detection", ({ text }) => /(?:往下翻|翻着翻着|往下滑|仔细翻|翻了翻|翻到)(?:了)?(?:活动)?页面[^。！\n]{0,40}(?:每批|检测|报告)|从活动规则[^。！\n]{0,40}(?:每批|检测|报告)|(?:兑换|领奖|中奖)[^。！\n]{0,36}(?:才|时|的时候)[^。！\n]{0,20}(?:看到|发现|知道)[^。！\n]{0,20}(?:每批|检测|报告)/.test(text), "light"],
  ["activity_naming_explanation", ({ text }) => /这个活动(?:叫|名称是)|活动名称是|活动是会员(?:体系)?升级|叫会员礼遇活动/.test(text), "light"],
  ["narrative_consistency", ({ text }) => /(?:一直想(?:买|囤|试)|第一次(?:买|喝|尝试)|准备(?:第一次|开始)(?:喝|买|试))/.test(text) && /(?:一直喝|喝了(?:几个月|半年|一年)|长期喝|继续回购|从出生|没换过|老客|老粉)/.test(text), "light"],
  ["birth_no_switch_vs_transition", ({ text }) => /从出生[^。！\n]{0,20}(?:一直喝|没换过)|一直没换过/.test(text) && /转奶|换回来|换了|换过别的/.test(text), "hard"],
  ["source_stacking_three", ({ body }) => {
    const opening = body.split(/\n\n|。|！/).slice(0, 3).join("。");
    const sources = [
      /闺蜜/.test(opening), /邻居|同小区|隔壁|电梯里/.test(opening), /同事/.test(opening),
      /导购|门店/.test(opening), /宝爸/.test(opening), /宝妈群|群里/.test(opening),
      /朋友/.test(opening), /官号/.test(opening), /puq|pyq|朋友圈/.test(opening), /🍠|小红书/.test(opening),
    ].filter(Boolean).length;
    return sources >= 3;
  }, "hard"],
  ["soft_rewrite_terms", ({ text }) => /顺手|顺口|顺便|薅|白嫖|羊毛|真的会谢|彩虹屁|挺逗|Emm|笑哭R|攒罐子|攒着罐子|罐子攒起来|把罐子攒起来|朋友圈|抖音|淘宝|拼多多|东北|北京|四川|重庆|广东|深圳|广州|江浙沪|浙江|江苏|上海|山东|河南|河北|福建|闽南|西安|陕西/.test(text), "light"],
  ["deterministic_normalization", ({ text }) => /小红书|肠胃|脾胃|大脑|敏感|预防针|微信|钱|免费|母乳|A2蛋白质|a2蛋白质|♀️|♂|🎵|#/.test(text), "normalize"],
  ["title_over_20", ({ title }) => weightedTitleLength(title) > 20, "light"],
];

const results = [];
const exactBodyMap = new Map();
const categoryCounts = {};
for (let index = 0; index < rows.length; index += 1) {
  const row = rows[index];
  const sourceRow = index + 2;
  const title = String(row[0] || "");
  const body = String(row[1] || "");
  const text = `${title}\n${body}`;
  const category = effectiveCategory(row);
  categoryCounts[category] = (categoryCounts[category] || 0) + 1;
  exactBodyMap.set(body, [...(exactBodyMap.get(body) || []), sourceRow]);
  const hits = [];
  for (const [code, predicate, level] of checks) {
    if (predicate({ title, body, text, row })) hits.push({ code, level });
  }
  results.push({
    source_row: sourceRow,
    title,
    body,
    source_category: String(row[7] || ""),
    effective_category: category,
    weighted_title_length: weightedTitleLength(title),
    source_values: row,
    hits,
  });
}

const duplicateGroups = [...exactBodyMap.entries()]
  .filter(([body, sourceRows]) => body && sourceRows.length > 1)
  .map(([body, sourceRows]) => ({ body, source_rows: sourceRows }));
const duplicateRows = new Set(duplicateGroups.flatMap((item) => item.source_rows.slice(1)));
for (const item of results) {
  if (duplicateRows.has(item.source_row)) item.hits.push({ code: "exact_duplicate_body", level: "hard" });
}

const hitCounts = {};
for (const item of results) {
  for (const hit of item.hits) hitCounts[`${hit.level}:${hit.code}`] = (hitCounts[`${hit.level}:${hit.code}`] || 0) + 1;
}

const output = { headers, total_rows: results.length, category_counts: categoryCounts, hit_counts: hitCounts, duplicate_groups: duplicateGroups, results };
await fs.writeFile(outputPath, JSON.stringify(output, null, 2), "utf8");
console.log(JSON.stringify({ total_rows: results.length, category_counts: categoryCounts, hit_counts: hitCounts, duplicate_groups: duplicateGroups.length }, null, 2));

