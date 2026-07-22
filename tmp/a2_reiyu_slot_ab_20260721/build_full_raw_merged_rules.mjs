import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const sourceRules = "/Users/luxifa/maga/tmp/a2_reiyu_slot_ab_20260721/current_rules.json";
const sourceSlots = "/Users/luxifa/maga/tmp/a2_reiyu_slot_ab_20260721/original_slots.json";
const outputDir = "/Users/luxifa/maga/outputs/a2_reiyu_full_raw_merged_20260721";
const outputCsv = `${outputDir}/a2礼遇UGC分享贴_原始槽位_认可路径分流.csv`;
const previewPng = `${outputDir}/a2礼遇UGC分享贴_原始槽位_认可路径分流预览.png`;

const current = JSON.parse(await fs.readFile(sourceRules, "utf8"));
const original = JSON.parse(await fs.readFile(sourceSlots, "utf8"));
const removedColumns = new Set(["产品体验素材", "消费者认可素材"]);
const headers = [];
for (const header of current.headers) {
  if (header === "产品体验素材") headers.push("认可表达素材");
  if (!removedColumns.has(header)) headers.push(header);
}
const recognitionRoutes = [
  { code: "loyal", label: "老客使用感受" },
  { code: "informed", label: "信息了解后的认可" },
];
const rows = current.rows.flatMap((row) =>
  recognitionRoutes.map((route) => ({
    ...row,
    _baseRuleName: row["业务规则名称"],
    _recognitionRoute: route.code,
    _recognitionRouteLabel: route.label,
  })),
);

const valuesFor = (rows, key, value) => rows.filter((row) => row[key] === value).map((row) => row["语料"]);
const unique = (items) => [...new Set(items.filter(Boolean))];
const join = (items) => unique(items).join("||");
const jsonCell = (items) => JSON.stringify(unique(items));
const moveFirst = (items, predicate) => {
  const index = items.findIndex(predicate);
  if (index <= 0) return [...items];
  return [items[index], ...items.slice(0, index), ...items.slice(index + 1)];
};

const rawContentDirections = valuesFor(original.content_direction, "内容方向", "礼遇").map((text) =>
  text.replace(
    "不要说翻页面、仔细看页面",
    "不要说翻看页面、往下翻页面",
  ),
);
const informationDirectionMarkers = [
  "从哪里得知了a2的什么活动",
  "品实用，价值感在线",
  "发现福利不是单层的",
];
const informationDirections = rawContentDirections.filter((text) =>
  informationDirectionMarkers.some((marker) => text.includes(marker)),
);
const loyalDirections = rawContentDirections.filter((text) => !informationDirections.includes(text));
const preferredDirectionByRoute = new Map([
  ["loyal", "直给点说自己参加了活动"],
  ["informed", "从哪里得知了a2的什么活动"],
]);

const activityRows = original.activity_content;
const lottery = moveFirst(
  valuesFor(activityRows, "活动内容", "溯源抽奖").filter(
    (text) =>
      !text.includes("有集罐礼还有抽奖") &&
      !text.includes("全家产品") &&
      !text.includes("a2全家桶"),
  ),
  (text) => text.includes("看看品质溯源信息就能参与抽奖"),
);
const membership = moveFirst(
  valuesFor(activityRows, "活动内容", "会员体系/积分").filter(
    (text) =>
      !text.includes("罐子能换") &&
      !text.includes("集罐") &&
      !text.includes("回馈") &&
      !text.includes("抽奖"),
  ),
  (text) => text.includes("每次下单都能攒积分"),
);
const returning = moveFirst(
  valuesFor(activityRows, "活动内容", "老客回馈 / 回归礼"),
  (text) => text === "有老客回归礼，可以领取小听粉。",
);
const stacked = moveFirst(
  valuesFor(activityRows, "活动内容", "多重福利叠加"),
  (text) => text.includes("积分、集罐、抽奖、回馈礼都有"),
);
const cans12 = moveFirst(
  valuesFor(activityRows, "活动内容", "集罐礼-12罐兑1罐").filter(
    (text) =>
      !text.includes("罐子攒起来") &&
      !text.includes("入手12罐") &&
      !text.includes("买12罐") &&
      !text.includes("买 12 罐"),
  ),
  (text) => text.startsWith("我认真算了一下"),
);
const otherCans = valuesFor(activityRows, "活动内容", "集罐礼-其他");
const activityByRule = new Map([
  ["a2礼遇｜溯源抽奖", lottery],
  ["a2礼遇｜会员体系积分", membership],
  ["a2礼遇｜老客回归礼", returning],
  ["a2礼遇｜多重福利叠加", stacked],
  ["a2礼遇｜集罐3罐换小车车", otherCans.filter((text) => text.includes("集3罐兑换可以得小车车"))],
  ["a2礼遇｜集罐6罐换自行车", otherCans.filter((text) => text.includes("集6罐兑换可以得自行车"))],
  ["a2礼遇｜集罐12罐换奶粉", cans12],
  [
    "a2礼遇｜集罐18罐换婴儿车",
    otherCans
      .filter((text) => text.includes("集18罐兑换可以得推车"))
      .map((text) => text.replace("推车", "婴儿车")),
  ],
]);

const rawSources = valuesFor(original.info_source, "了解途径", "礼遇").filter(
  (text) => !text.includes("电梯里听邻居说"),
);
const sourceOverrideByRule = new Map([
  ["a2礼遇｜多重福利叠加", "宝爸刷到后跟我说"],
]);
const firstSourceByRule = new Map([
  ["a2礼遇｜溯源抽奖", "🍠上看到"],
  ["a2礼遇｜会员体系积分", "宝妈群里有人提"],
  ["a2礼遇｜老客回归礼", "闺蜜看到和我说"],
  ["a2礼遇｜多重福利叠加", "宝爸刷到后跟我说"],
  ["a2礼遇｜集罐3罐换小车车", "邻居宝妈说起"],
  ["a2礼遇｜集罐6罐换自行车", "同事宝妈说起"],
  ["a2礼遇｜集罐12罐换奶粉", "去门店的时候导购说的"],
  ["a2礼遇｜集罐18罐换婴儿车", "同小区宝妈说起"],
]);

const lotteryMotives = valuesFor(original.motive, "动机", "抽奖触发");
const collectionMotives = valuesFor(original.motive, "动机", "集罐触发").filter((text) => !text.includes("FL"));
const genericMotives = valuesFor(original.motive, "动机", "礼遇不提及")
  .filter((text) => !text.includes("现在a2至初挺活动也实在的"));
const loyalMotives = valuesFor(original.motive, "动机", "老客型");
const informedMotiveByRule = new Map([
  ["a2礼遇｜溯源抽奖", moveFirst([...lotteryMotives, ...genericMotives], (text) => text.startsWith("说真的"))],
  [
    "a2礼遇｜会员体系积分",
    moveFirst(genericMotives, (text) => text.includes("花这么大力气升级")),
  ],
  ["a2礼遇｜老客回归礼", moveFirst(loyalMotives, (text) => text.startsWith("家里本来就一直喝"))],
  [
    "a2礼遇｜多重福利叠加",
    ["发现这次不是单层福利，想把能参加的都了解清楚。", ...genericMotives],
  ],
  ["a2礼遇｜集罐3罐换小车车", moveFirst(collectionMotives, (text) => text.startsWith("比起单纯抽个奖"))],
  ["a2礼遇｜集罐6罐换自行车", moveFirst(collectionMotives, (text) => text.startsWith("集罐福利太棒了"))],
  [
    "a2礼遇｜集罐12罐换奶粉",
    moveFirst([...genericMotives, ...collectionMotives], (text) => text.includes("花这么大力气升级")),
  ],
  ["a2礼遇｜集罐18罐换婴儿车", moveFirst(collectionMotives, (text) => text.startsWith("比起单纯抽个奖"))],
]);

const productExperience = valuesFor(original.praise, "夸奖", "消费者视角切入点");
const recommendationIntents = valuesFor(original.praise, "夸奖", "推荐意愿提升");
const loyalRecognition = productExperience.map((experience, index) =>
  [
    "认可依据：家里长期喝a2至初后的实际感受。",
    `产品体验原话：${experience}`,
    `推荐态度原话：${recommendationIntents[index % recommendationIntents.length]}`,
  ].join("\n"),
);
const informationRecognitionRaw = unique([
  ...valuesFor(original.praise, "夸奖", "深度认可").filter(
    (text) => !text.includes("准备马上下单"),
  ),
  ...valuesFor(original.praise, "夸奖", "安心感具体化").filter(
    (text) => !text.includes("从“听别人说”变成“自己感受到”"),
  ),
  ...valuesFor(original.praise, "夸奖", "不提及").filter(
    (text) => text !== "不会踩雷",
  ),
]);
const informationRecognition = informationRecognitionRaw.map((recognition) =>
  [
    "认可依据：从本次活动和a2至初每批检测信息形成的品牌感受。",
    `品牌感受原话：${recognition}`,
  ].join("\n"),
);

const globalSourceBoundary = "每篇只选择一个活动了解途径，不得把多个了解来源叠加成同一次发现经历。";
const prizeReviewOnlyBoundary = "抽奖奖品只有旅游基金大奖、金手链、夏凉被；集罐奖品只有3罐小车车、6罐自行车、12罐奶粉、18罐婴儿车。不得新增、串换奖品，不写自己中了什么，也不写中奖难度和概率。";
const downstreamLexicalNormalizationBoundary = "禁止写小红书、肠胃、肚子、敏感、便便、粑粑、钱、预防针、大脑、眼睛、母乳、微信、QQ；如确需表达，分别改为🍠、肚肚、敏敏、💩、💰、💉、🧠、👀、母R、🌍。";
const generationAnchorByRule = new Map([
  ["a2礼遇｜溯源抽奖", "本条主活动是溯源抽奖。"],
  ["a2礼遇｜会员体系积分", "本条主活动是会员体系和积分。"],
  ["a2礼遇｜老客回归礼", "本条主活动是老客回归礼。"],
  ["a2礼遇｜多重福利叠加", "本条主活动是多重福利叠加，可以同时概括抽奖、集罐、积分、老客回馈。"],
  ["a2礼遇｜集罐3罐换小车车", "本条主活动是集罐礼。"],
  ["a2礼遇｜集罐6罐换自行车", "本条主活动是集罐礼。"],
  ["a2礼遇｜集罐12罐换奶粉", "本条主活动是集罐礼。"],
  ["a2礼遇｜集罐18罐换婴儿车", "本条主活动是集罐礼。"],
]);
for (const row of rows) {
  const ruleName = row._baseRuleName;
  const recognitionRoute = row._recognitionRoute;
  row["业务规则名称"] = `${ruleName}｜${row._recognitionRouteLabel}`;
  const routeDirections = recognitionRoute === "loyal" ? loyalDirections : informationDirections;
  const preferredDirection =
    ruleName === "a2礼遇｜老客回归礼" && recognitionRoute === "loyal"
      ? "开头结合本篇素材写"
      : ruleName === "a2礼遇｜多重福利叠加" && recognitionRoute === "informed"
        ? "发现福利不是单层的"
        : preferredDirectionByRoute.get(recognitionRoute);
  const contentDirectionOptions = moveFirst(routeDirections, (text) =>
      text.includes(preferredDirection || ""),
  );
  row["内容方向"] = contentDirectionOptions[0] || "";
  row["内容方向素材"] = jsonCell(contentDirectionOptions);
  const sourceOverride = sourceOverrideByRule.get(ruleName);
  const sourceOptions = sourceOverride ? [sourceOverride, ...rawSources] : rawSources;
  row["活动了解途径素材"] = join(
    moveFirst(sourceOptions, (text) => text === firstSourceByRule.get(ruleName)),
  );
  const motiveOptions =
    recognitionRoute === "loyal"
      ? moveFirst(loyalMotives, (text) => text.startsWith("家里本来就一直喝"))
      : informedMotiveByRule.get(ruleName) || [];
  row["参加活动原因素材"] = join(motiveOptions);
  row["活动内容素材"] = join(activityByRule.get(ruleName) || []);
  row["认可表达素材"] = jsonCell(
    recognitionRoute === "loyal" ? loyalRecognition : informationRecognition,
  );
  row["批批检素材"] = String(row["批批检素材"] || "").replace(
    "但不要展开检测细节",
    "可以概括说检测严格或标准高，但不要编具体检测项目、数量、结果或报告细节",
  );
  if (recognitionRoute === "informed") {
    row["正向表达素材"] = "";
    row["写法"] = join(
      String(row["写法"] || "")
        .split("||")
        .filter((text) => !text.includes("从本条抽中的正向表达")),
    );
  }
  delete row["产品体验素材"];
  delete row["消费者认可素材"];
  row["生文素材"] = join([
    "活动名称：会员体系升级。",
    "检测承接：活动内容讲完后，才能自然带出a2至初现在每批都有检测。",
  ]);
  const boundaries = String(row["硬边界"] || "")
    .split("||")
    .map((text) => text.trim())
    .filter(Boolean)
    .map((text) =>
      text.replace("；不得把多个了解来源叠加成同一次发现经历。", "。"),
    )
    .map((text) =>
      text
        .replace(
          "也禁止写翻页面、仔细研究页面或从活动规则里发现检测",
          "也禁止写翻看页面、往下翻页面或从活动规则里发现检测",
        )
        .replace(
          "没有自然需要时不要写罐底码，不展开检测细节",
          "没有自然需要时不要写罐底码；可以概括说检测严格或标准高，但不要编具体检测项目、数量、结果或报告细节",
        ),
    )
    .filter(
      (text) =>
        text !== prizeReviewOnlyBoundary &&
        text !== downstreamLexicalNormalizationBoundary &&
        !text.includes("报名活动"),
    );
  if (generationAnchorByRule.has(ruleName)) boundaries[0] = generationAnchorByRule.get(ruleName);
  const routeBoundary =
    recognitionRoute === "loyal"
      ? "本条认可路径是老客使用感受：写家里长期喝a2至初后的实际产品体验，再自然表达推荐意愿。"
      : "本条认可路径是信息了解后的认可：只根据活动和每批检测信息表达品牌感受，不补写宝宝长期使用结果、转奶或回归经历。";
  const oldExperienceBoundary = boundaries.findIndex((text) =>
    text.includes("可以积极推荐，但必须由自家冲泡体验和消费者感受承接"),
  );
  if (recognitionRoute === "informed" && oldExperienceBoundary >= 0) {
    boundaries[oldExperienceBoundary] =
      "不要写成品牌背书、品牌公告、客服话术、导购话术或卖点堆叠；品牌认可由本次活动和每批检测信息承接。";
  }
  boundaries.splice(1, 0, routeBoundary);
  if (!boundaries.includes(globalSourceBoundary)) boundaries.splice(1, 0, globalSourceBoundary);
  row["硬边界"] = join(boundaries);
}

const matrix = [headers, ...rows.map((row) => headers.map((header) => row[header] ?? ""))];
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("业务规则");
sheet.getRangeByIndexes(0, 0, matrix.length, headers.length).values = matrix;
sheet.getRangeByIndexes(0, 0, 1, headers.length).format = {
  fill: "#5B2C6F",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
};
sheet.getRangeByIndexes(1, 0, rows.length, headers.length).format.wrapText = true;
sheet.freezePanes.freezeRows(1);
sheet.showGridLines = false;
sheet.getRangeByIndexes(0, 0, matrix.length, headers.length).format.columnWidth = 34;

const inspection = await workbook.inspect({
  kind: "table",
  range: `业务规则!A1:O17`,
  include: "values",
  tableMaxRows: 17,
  tableMaxCols: 15,
  tableMaxCellChars: 180,
  maxChars: 12000,
});
process.stdout.write(`${inspection.ndjson}\n`);
const targetInspection = await workbook.inspect({
  kind: "match",
  searchTerm: "开头结合本篇素材写",
  options: { maxResults: 20 },
  maxChars: 6000,
});
process.stdout.write(`${targetInspection.ndjson}\n`);

await fs.mkdir(outputDir, { recursive: true });
const preview = await workbook.render({
  sheetName: "业务规则",
  range: "A1:O17",
  scale: 0.7,
  format: "png",
});
await fs.writeFile(previewPng, new Uint8Array(await preview.arrayBuffer()));

const csvEscape = (value) => {
  const text = String(value ?? "");
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};
const csvText = `\uFEFF${matrix.map((row) => row.map(csvEscape).join(",")).join("\n")}\n`;
await fs.writeFile(outputCsv, csvText, "utf8");

process.stdout.write(
  JSON.stringify(
    {
      outputCsv,
      previewPng,
      columns: headers,
      infoSourceCount: rawSources.length,
      recognitionRouteCounts: Object.fromEntries(
        recognitionRoutes.map((route) => [
          route.label,
          rows.filter((row) => row._recognitionRoute === route.code).length,
        ]),
      ),
      activityCounts: Object.fromEntries([...activityByRule].map(([key, values]) => [key, unique(values).length])),
      recognitionCounts: {
        老客使用感受: loyalRecognition.length,
        信息了解后的认可: informationRecognition.length,
      },
    },
    null,
    2,
  ) + "\n",
);
