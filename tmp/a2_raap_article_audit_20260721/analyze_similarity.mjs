import fs from "node:fs/promises";

const inputPath = "/Users/luxifa/maga/tmp/a2_raap_article_audit_20260721/extracted_workbooks.json";
const outputPath = "/Users/luxifa/maga/tmp/a2_raap_article_audit_20260721/similarity_analysis.json";
const workbooks = JSON.parse(await fs.readFile(inputPath, "utf8"));
const rows = workbooks[0].sheets[0].values.slice(1).map((row, index) => ({
  excelRow: index + 2,
  title: String(row[2] || ""),
  body: String(row[3] || ""),
}));

function bigrams(text) {
  const normalized = text.replace(/\s+/g, "");
  const result = new Set();
  for (let index = 0; index < normalized.length - 1; index += 1) {
    result.add(normalized.slice(index, index + 2));
  }
  return result;
}

function jaccard(left, right) {
  let intersection = 0;
  for (const value of left) if (right.has(value)) intersection += 1;
  return intersection / (left.size + right.size - intersection || 1);
}

const grams = rows.map((row) => bigrams(row.body));
const pairs = [];
for (let left = 0; left < rows.length; left += 1) {
  for (let right = left + 1; right < rows.length; right += 1) {
    const score = jaccard(grams[left], grams[right]);
    if (score >= 0.3) {
      pairs.push({
        score: Number(score.toFixed(4)),
        leftRow: rows[left].excelRow,
        rightRow: rows[right].excelRow,
        leftTitle: rows[left].title,
        rightTitle: rows[right].title,
      });
    }
  }
}
pairs.sort((a, b) => b.score - a.score);

const phrases = [
  "集12罐",
  "12罐就能",
  "每批都检测",
  "扫罐底码",
  "闭眼入不踩雷",
  "继续回购",
  "值得长期回购",
  "小麻杆",
  "小肉球",
  "一口接一口",
  "肚肚舒服",
  "心里踏实",
  "实力在线",
  "值得囤",
  "活动太实在",
  "粉质细腻",
  "不结块",
  "长肉",
];
const phraseCounts = Object.fromEntries(
  phrases.map((phrase) => [phrase, rows.filter((row) => row.body.includes(phrase)).length]),
);

const result = {
  totalRows: rows.length,
  maxPairwiseJaccard2gram: pairs[0]?.score || 0,
  pairCountAtOrAbove03: pairs.length,
  pairCountAtOrAbove035: pairs.filter((pair) => pair.score >= 0.35).length,
  topPairs: pairs.slice(0, 20),
  phraseCounts,
};
await fs.writeFile(outputPath, JSON.stringify(result, null, 2), "utf8");
console.log(JSON.stringify(result, null, 2));
