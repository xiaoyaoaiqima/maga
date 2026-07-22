import fs from "node:fs/promises";
import path from "node:path";
import { Workbook } from "@oai/artifact-tool";

const root = "/Users/luxifa/maga";
const inputPath = path.join(root, "tmp/a2_old_raap_audit_20260722/extracted_workbooks.json");
const outputPath = path.join(
  root,
  "outputs/a2_old_raap_audit_20260722/A2礼遇_老RAAP两批合并可用393篇.csv",
);

const deletedIds = new Set([
  "content-6648f65ade0e4d2f",
  "content-55c27715de7c471a",
  "content-b7e380cf70164535",
  "content-de29bf38779d4b33",
  "content-1372c570f55d4f35",
  "content-3c4746630cda4615",
  "content-7154065f164241de",
]);

const source = JSON.parse(await fs.readFile(inputPath, "utf8"));
const rows = source.flatMap((workbook) =>
  workbook.sheets[0].values.slice(1).map((row) => {
    const context = JSON.parse(row[4]);
    return {
      content_id: String(row[1] || "").trim(),
      title: String(row[2] || "").trim(),
      body: String(row[3] || "").trim(),
      category: String(context["活动内容"] || "").trim(),
    };
  }),
);

const byId = new Map(rows.map((row) => [row.content_id, row]));

function replaceOnce(contentId, field, before, after) {
  const row = byId.get(contentId);
  if (!row) throw new Error(`missing content_id: ${contentId}`);
  if (!row[field].includes(before)) {
    throw new Error(`missing patch source for ${contentId}.${field}: ${before}`);
  }
  row[field] = row[field].replace(before, after);
}

function replaceAll(contentId, field, before, after) {
  const row = byId.get(contentId);
  if (!row) throw new Error(`missing content_id: ${contentId}`);
  if (!row[field].includes(before)) {
    throw new Error(`missing patch source for ${contentId}.${field}: ${before}`);
  }
  row[field] = row[field].split(before).join(after);
}

replaceOnce(
  "content-6e9deea0fe474bb8",
  "body",
  "集罐12罐就能换1罐，还能换小车车",
  "集罐12罐就能换1罐，其他档位还能换小车车",
);
replaceOnce(
  "content-4b7f97a21c1c4c82",
  "body",
  "我家小宝从出生就喝的a2至初，配方很扎实，只含A2蛋白还有优量乳铁蛋白，营养全面又温和。转奶的时候特别丝滑",
  "我家小宝转奶后就一直喝a2至初，配方很扎实，只含A2蛋白还有优量乳铁蛋白，营养全面又温和。当时转得特别丝滑",
);
replaceOnce("content-c43d11a6f0db4c70", "body", "然后我顺便去了解了下", "后来我又了解了下");
replaceOnce("content-d925156d3554492a", "body", "我眼睛一下就亮了😄", "我一下就来精神了😄");
replaceOnce(
  "content-a36eeaaaa34d4d74",
  "body",
  "集罐能换小车车",
  "集12罐能换1罐正装，其他档位还能换小车车",
);
replaceOnce(
  "content-d3a45764d1194f8b",
  "body",
  "12罐能换1罐，还能换小车车",
  "12罐能换1罐，其他档位还能换小车车",
);
replaceOnce("content-4ccbb57a6a004036", "body", "收到导发消息", "收到导购发消息");
replaceOnce(
  "content-a918a3ed5c674400",
  "body",
  "a2有活动了，罐子攒起来能换东西。",
  "a2有集罐活动了。",
);
replaceOnce(
  "content-13d3afc2abd3407f",
  "body",
  "有个集罐换奶粉的活动，买12罐到手13罐，还能换小车车或者婴儿车，挺实在的吧！",
  "有个集罐换礼活动，集12罐能换1罐奶粉，其他档位还有小车车或婴儿车，挺实在的吧！",
);
replaceOnce("content-a59c7986b5a040fc", "body", "然后我顺手戳了戳活动页面", "后来我点开活动页面");
replaceOnce(
  "content-a59c7986b5a040fc",
  "body",
  "我家娃从出生就喝它，转奶顺利，适应很快",
  "我家娃转奶后就一直喝它，当时适应很快",
);
replaceOnce(
  "content-2f4fdcc20dd445bf",
  "body",
  "集罐送小车车或者奶粉",
  "集12罐能换1罐奶粉，其他档位还能换小车车",
);
replaceOnce(
  "content-6b43b5e153e4456e",
  "body",
  "罐子攒起来能换礼品，12罐就能换1罐奶粉，还有什么小车车、婴儿车啥的。",
  "活动按集罐数量换礼品，12罐就能换1罐奶粉，其他档位还有小车车、婴儿车啥的。",
);
replaceOnce(
  "content-e6914e4663c44ae4",
  "body",
  "活动就是集够12罐能换1罐，还能换小车车、婴儿车那些。",
  "活动就是集够12罐能换1罐，其他档位还有小车车、婴儿车那些。",
);
replaceOnce(
  "content-e6914e4663c44ae4",
  "body",
  "娃喝得香，还能攒礼品，真香！",
  "娃喝得香，还能参加集罐换礼，真香！",
);
replaceOnce("content-bbd169d4434b4bb8", "body", "集罐换一罐", "集12罐换一罐");
replaceAll("content-219d78bfb8db4779", "body", "a2 至初", "a2至初");
replaceOnce("content-219d78bfb8db4779", "body", "集罐换装", "集罐兑换");

replaceOnce(
  "content-555e94f34c314e45",
  "body",
  "不光是抽旅游大奖、金手链、夏凉被那些，还有额外回馈，多重福利叠一起",
  "不光是抽旅游大奖、金手链、夏凉被那些，集12罐还能兑1罐正装，还有额外回馈，多重福利叠一起",
);
replaceOnce(
  "content-3001bb7d4ce84dc3",
  "body",
  "有抽奖拿到旅游基金大奖、金手链那些，  \n还有回馈能集罐兑奶粉和小车车",
  "抽奖有旅游基金大奖、金手链那些，  \n集罐则是12罐兑1罐奶粉，其他档位还有小车车",
);
replaceOnce("content-eaef39c65d184e4d", "title", "带娃顺便参加了个大活动🤣", "带娃参加了个大活动🤣");
replaceOnce(
  "content-eaef39c65d184e4d",
  "body",
  "参加下来感觉真不错，兑换的东西都超实用！",
  "活动内容看下来真不错，能兑换的东西都超实用！",
);
replaceOnce("content-eaef39c65d184e4d", "body", "扫罐底就能看报告", "扫罐底码就能看报告");
replaceOnce(
  "content-564523c6eb9c476f",
  "body",
  "看到有抽奖，旅游基金大奖、金手链、夏凉被，还有额外回馈，真香！",
  "看到有抽奖，旅游基金大奖、金手链、夏凉被，集12罐还能兑1罐正装，还有额外回馈，真香！",
);
replaceOnce("content-564523c6eb9c476f", "body", "从女儿童年小麻杆养到现在肉嘟嘟", "从以前的小麻杆养到现在肉嘟嘟");
replaceOnce("content-a52ab94f61a54b30", "body", "12集1兑换一罐", "集12罐兑换1罐");
replaceOnce("content-4773893e33ea434c", "body", "之前转奶失败", "之前转别的牌子没适应");
replaceOnce(
  "content-70e43e4496b54c19",
  "body",
  "抽奖有旅游基金、金手链、夏凉被，还有老客回馈啥的",
  "抽奖有旅游基金、金手链、夏凉被，集12罐还能兑1罐正装，还有老客回馈啥的",
);
replaceOnce(
  "content-bc6c185194de4c82",
  "body",
  "活动说罐子攒起来可以换礼品，12罐就能换1罐，还有小车车、婴儿车这些",
  "活动按集罐数量换礼品，12罐就能换1罐，其他档位还有小车车、婴儿车这些",
);
replaceOnce(
  "content-b40341c73e9b4150",
  "body",
  "我家宝从出生就喝这个，当初转奶适应很快",
  "我家宝转奶后就一直喝这个，当初适应很快",
);
replaceOnce("content-4ff1174e83b84c48", "body", "然后我顺便看了下", "后来我又看了下");
replaceOnce("content-bd5b59e109de4876", "body", "集罐能换小车车，我眼睛一亮！", "集罐能换小车车，我一下就来精神了！");
replaceOnce("content-400d42acf6f247c1", "body", "当初转别的牌子失败过", "当初转别的牌子没适应");
replaceOnce(
  "content-8d79e9e2d3564dd7",
  "body",
  "买12罐参与集罐就能🆓再兑1罐，还有小车车、婴儿车、自行车这些可以选",
  "集12罐就能🆓兑1罐，其他集罐档位还有小车车、婴儿车、自行车",
);
replaceOnce(
  "content-cdce54ecb12f43a8",
  "body",
  "这个活动是集罐换礼，集够罐子就能解锁豪礼，有小车车、婴儿车、自行车，还有奶粉🤩",
  "这个活动按集罐数量换礼，有小车车、婴儿车、自行车，还有奶粉🤩",
);
replaceOnce(
  "content-cdce54ecb12f43a8",
  "body",
  "感觉挺划算的，反正奶粉天天要喝，顺手攒点权益多实在。",
  "感觉挺划算的，反正奶粉天天要喝，参与集罐换礼也挺实在。",
);
replaceOnce(
  "content-5ffe36e5503749c3",
  "body",
  "集罐能🆓兑一罐，还有至高2499的好礼可以换，婴儿车啥的也太诱人了吧～",
  "集12罐能🆓兑1罐，其他档位还有至高2499的好礼，婴儿车啥的也太诱人了吧～",
);
replaceOnce("content-a7596f56822c4ad9", "body", "然后我顺便看了下", "后来我又看了下");
replaceOnce(
  "content-64140625fe0a4fd5",
  "body",
  "我家小宝从出生就喝它，转奶顺利没遭罪",
  "我家小宝转奶后就一直喝它，当时适应很快没遭罪",
);

replaceOnce(
  "content-2856b6e15d3d4fcd",
  "body",
  "集罐能换小车车、婴儿车，12罐还能直接换1罐奶粉",
  "其他集罐档位能换小车车、婴儿车，12罐还能直接换1罐奶粉",
);
replaceOnce(
  "content-56f41c16105344a8",
  "body",
  "集12罐就能换一罐正装，还有小车车、婴儿车这些实用奖品",
  "集12罐就能换一罐正装，其他档位还有小车车、婴儿车这些实用奖品",
);
replaceOnce(
  "content-73b78c94eef34ca5",
  "body",
  "集满12罐能多得一罐，奖品还都是实用的小车车那些",
  "集满12罐能多得一罐，其他档位还有实用的小车车那些",
);
replaceOnce(
  "content-0935b1bb62a44100",
  "body",
  "集满12罐就能换整罐奶粉，小车车、婴儿车也有",
  "集满12罐就能换整罐奶粉，其他档位也有小车车、婴儿车",
);
replaceOnce(
  "content-44ff22145a7c4713",
  "body",
  "12罐就能换1罐，还有小车车、婴儿车那些",
  "12罐就能换1罐，其他档位还有小车车、婴儿车那些",
);
replaceOnce(
  "content-38de99ec99234155",
  "body",
  "集罐能换小车车、婴儿车，还有12罐换1罐奶粉",
  "其他档位能换小车车、婴儿车，12罐则能换1罐奶粉",
);
replaceOnce(
  "content-5b327597050749c9",
  "body",
  "买12罐能🆓换1罐，还有小车车、婴儿车这些实用奖品",
  "集12罐能🆓换1罐，其他档位还有小车车、婴儿车这些实用奖品",
);
replaceOnce(
  "content-540ac2fb934946f4",
  "body",
  "12罐能换1罐，还有小车车等奖品",
  "12罐能换1罐，其他档位还有小车车等奖品",
);
replaceOnce(
  "content-d19745cfd0ee4fb2",
  "body",
  "集够12罐能换奶粉或者小车车",
  "集够12罐能换奶粉，其他档位能换小车车",
);
replaceOnce(
  "content-3acfe30b2afc4943",
  "body",
  "集12罐就能换一罐正装，还有小车车、婴儿车啥的",
  "集12罐就能换一罐正装，其他档位还有小车车、婴儿车啥的",
);
replaceOnce(
  "content-78cfa5a16fae4bc0",
  "body",
  "集12罐能兑1罐，奖品还有小车车、婴儿车啥的",
  "集12罐能兑1罐，其他档位还有小车车、婴儿车啥的",
);
replaceOnce(
  "content-3c8e416146444bd3",
  "body",
  "集12罐就能换1罐奶粉，还有小车车啥的",
  "集12罐就能换1罐奶粉，其他档位还有小车车啥的",
);
replaceOnce(
  "content-1949cffa77af4bfe",
  "body",
  "12罐换1罐奶粉，算下来省好多💰啊，奖品还实用（小车车啥的）",
  "12罐换1罐奶粉，算下来省好多💰啊，其他档位的奖品也实用（小车车啥的）",
);
replaceOnce(
  "content-cdaf919e801648a3",
  "body",
  "小车车、婴儿车都实用",
  "其他档位的小车车、婴儿车都实用",
);
replaceOnce(
  "content-ba660c5c65954eec",
  "body",
  "买12罐集罐能🆓兑1罐，还有小车车、婴儿车那些大奖",
  "集12罐能🆓兑1罐，其他档位还有小车车、婴儿车那些大奖",
);

const outputRows = rows.filter((row) => !deletedIds.has(row.content_id));
if (outputRows.length !== 393) throw new Error(`expected 393 rows, got ${outputRows.length}`);
if (new Set(outputRows.map((row) => row.content_id)).size !== outputRows.length) {
  throw new Error("duplicate content_id found");
}
if (outputRows.some((row) => !row.content_id || !row.title || !row.body || !row.category)) {
  throw new Error("blank required field found");
}

function csvCell(value) {
  const text = String(value ?? "");
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

const csvLines = [
  ["content_id", "标题", "正文", "分类"],
  ...outputRows.map((row) => [row.content_id, row.title, row.body, row.category]),
].map((row) => row.map(csvCell).join(","));
const csvText = `\uFEFF${csvLines.join("\r\n")}\r\n`;

await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.writeFile(outputPath, csvText, "utf8");

const verifiedWorkbook = await Workbook.fromCSV(csvText.replace(/^\uFEFF/, ""), { sheetName: "合并可用文章" });
const verification = await verifiedWorkbook.inspect({
  kind: "sheet,table",
  maxChars: 3000,
  tableMaxRows: 4,
  tableMaxCols: 4,
  tableMaxCellChars: 80,
});

const categoryCounts = outputRows.reduce((counts, row) => {
  counts[row.category] = (counts[row.category] || 0) + 1;
  return counts;
}, {});

console.log(JSON.stringify({ outputPath, rowCount: outputRows.length, categoryCounts, verification: verification.ndjson }, null, 2));
