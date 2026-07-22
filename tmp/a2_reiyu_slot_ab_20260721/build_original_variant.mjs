import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const sourceRules = "/Users/luxifa/maga/tmp/a2_reiyu_slot_ab_20260721/current_rules.json";
const sourceSlots = "/Users/luxifa/maga/tmp/a2_reiyu_slot_ab_20260721/original_slots.json";
const outputDir = "/Users/luxifa/maga/outputs/a2_reiyu_slot_ab_20260721";
const outputCsv = `${outputDir}/a2礼遇UGC分享贴_原始语料槽位对照.csv`;
const previewPng = `${outputDir}/a2礼遇UGC分享贴_原始语料槽位对照预览.png`;

const current = JSON.parse(await fs.readFile(sourceRules, "utf8"));
const headers = current.headers;
const rows = current.rows.map((row) => headers.map((header) => row[header] ?? ""));
const column = Object.fromEntries(headers.map((name, index) => [String(name), index]));
const original = JSON.parse(await fs.readFile(sourceSlots, "utf8"));

const activityRows = original.activity_content;
const praiseRows = original.praise;
const valuesFor = (rows, key, value) => rows.filter((row) => row[key] === value).map((row) => row["语料"]);
const moveFirst = (items, predicate) => {
  const index = items.findIndex(predicate);
  if (index <= 0) return [...items];
  return [items[index], ...items.slice(0, index), ...items.slice(index + 1)];
};
const unique = (items) => [...new Set(items.filter(Boolean))];
const join = (items) => unique(items).join("||");

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
    (text) => !text.includes("罐子能换") && !text.includes("积分、集罐、回馈、抽奖"),
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
const cans3 = otherCans.filter((text) => text.includes("集3罐兑换可以得小车车"));
const cans6 = otherCans.filter((text) => text.includes("集6罐兑换可以得自行车"));
const cans18 = otherCans
  .filter((text) => text.includes("集18罐兑换可以得推车"))
  .map((text) => text.replace("推车", "婴儿车"));

const productExperience = valuesFor(praiseRows, "夸奖", "消费者视角切入点");
const praisePool = unique([
  ...valuesFor(praiseRows, "夸奖", "推荐意愿提升"),
  ...valuesFor(praiseRows, "夸奖", "愿意回归").filter((text) => text !== "夸夸"),
  ...valuesFor(praiseRows, "夸奖", "深度认可"),
  ...valuesFor(praiseRows, "夸奖", "安心感具体化"),
  ...valuesFor(praiseRows, "夸奖", "不提及").filter((text) => text !== "不会踩雷"),
]);

const activityByRule = new Map([
  ["a2礼遇｜溯源抽奖", lottery],
  ["a2礼遇｜会员体系积分", membership],
  ["a2礼遇｜老客回归礼", returning],
  ["a2礼遇｜多重福利叠加", stacked],
  ["a2礼遇｜集罐3罐换小车车", cans3],
  ["a2礼遇｜集罐6罐换自行车", cans6],
  ["a2礼遇｜集罐12罐换奶粉", cans12],
  ["a2礼遇｜集罐18罐换婴儿车", cans18],
]);

for (const row of rows) {
  const ruleName = String(row[column["业务规则名称"]]);
  const currentProduct = String(row[column["产品体验素材"]]).split("||")[0];
  const currentPraise = String(row[column["消费者认可素材"]]).split("||")[0];
  let productPredicate = (text) => text.startsWith("冲奶最怕结块");
  if (currentProduct.includes("奶香自然")) {
    productPredicate = (text) => text.includes("淡淡奶香");
  } else if (currentProduct.includes("不挂壁")) {
    productPredicate = (text) => text.startsWith("a2粉质特别细腻");
  }
  let praisePredicate = (text) => text === "原来a2真的有在认真做事";
  if (currentPraise.startsWith("活动福利实在")) {
    praisePredicate = (text) => text === "消费者有被重视到，品质也更透明";
  } else if (currentPraise.startsWith("福利和日常体验")) {
    praisePredicate = (text) => text.includes("实实在在给用户回馈");
  }
  row[column["活动内容素材"]] = join(activityByRule.get(ruleName) || []);
  row[column["产品体验素材"]] = join(moveFirst(productExperience, productPredicate));
  row[column["消费者认可素材"]] = join(moveFirst(praisePool, praisePredicate));
}

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("业务规则");
sheet.getRangeByIndexes(0, 0, rows.length + 1, headers.length).values = [headers, ...rows];
sheet.getRangeByIndexes(0, 0, 1, headers.length).format = {
  fill: "#7F6000",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
};
sheet.getRangeByIndexes(1, 0, rows.length, headers.length).format.wrapText = true;
sheet.freezePanes.freezeRows(1);
sheet.showGridLines = false;
sheet.getRange("A:P").format.columnWidth = 24;
sheet.getRange("H:K").format.columnWidth = 52;

const inspection = await workbook.inspect({
  kind: "table",
  range: "业务规则!A1:P9",
  include: "values",
  tableMaxRows: 9,
  tableMaxCols: 16,
  tableMaxCellChars: 180,
  maxChars: 12000,
});
process.stdout.write(`${inspection.ndjson}\n`);

await fs.mkdir(outputDir, { recursive: true });
const preview = await workbook.render({
  sheetName: "业务规则",
  range: "A1:P9",
  scale: 0.7,
  format: "png",
});
await fs.writeFile(previewPng, new Uint8Array(await preview.arrayBuffer()));

const csvEscape = (value) => {
  const text = String(value ?? "");
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};
const outputMatrix = [headers, ...rows];
const csvText = `\uFEFF${outputMatrix.map((row) => row.map(csvEscape).join(",")).join("\n")}\n`;
await fs.writeFile(outputCsv, csvText, "utf8");
process.stdout.write(
  JSON.stringify(
    {
      outputCsv,
      previewPng,
      activityCounts: Object.fromEntries([...activityByRule].map(([key, values]) => [key, values.length])),
      productExperienceCount: productExperience.length,
      praiseCount: praisePool.length,
    },
    null,
    2,
  ) + "\n",
);
