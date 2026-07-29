import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const csvPath = "/Users/luxifa/maga/outputs/a2_reiyu_inventory_import_20260725/A2礼遇_新增可用198篇_20260725.csv";
const previewPath = "/Users/luxifa/maga/tmp/a2_reiyu_inventory_import_20260725/artifact_check/preview.png";
const csvText = await fs.readFile(csvPath, "utf8");
const workbook = await Workbook.fromCSV(csvText, { sheetName: "新增库存" });
const sheet = workbook.worksheets.getItem("新增库存");
const used = sheet.getUsedRange(true);
const values = used.values;

if (values.length !== 199) {
  throw new Error(`expected 199 rows including header, got ${values.length}`);
}
const expectedHeader = ["content_id", "标题", "正文", "分类", "审核档位"];
const actualHeader = values[0].map((value, index) =>
  index === 0 ? String(value ?? "").replace(/^\uFEFF/, "") : value,
);
if (JSON.stringify(actualHeader) !== JSON.stringify(expectedHeader)) {
  throw new Error(`unexpected header: ${JSON.stringify(values[0])}`);
}
const ids = values.slice(1).map((row) => String(row[0] ?? ""));
const bodies = values.slice(1).map((row) => String(row[2] ?? ""));
if (new Set(ids).size !== 198 || new Set(bodies).size !== 198) {
  throw new Error("content_id or body duplicates found");
}
const counts = Object.fromEntries(
  ["12罐", "其他罐", "其他"].map((category) => [
    category,
    values.slice(1).filter((row) => row[3] === category).length,
  ]),
);
if (counts["12罐"] !== 24 || counts["其他罐"] !== 70 || counts["其他"] !== 104) {
  throw new Error(`unexpected category counts: ${JSON.stringify(counts)}`);
}
if (values.slice(1).some((row) => row[4] !== "direct_pool")) {
  throw new Error("non-direct_pool row found");
}

const inspection = await workbook.inspect({
  kind: "table",
  range: "新增库存!A1:E6",
  include: "values",
  tableMaxRows: 6,
  tableMaxCols: 5,
  maxChars: 3000,
});
const preview = await workbook.render({
  sheetName: "新增库存",
  range: "A1:E6",
  scale: 1,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
console.log(JSON.stringify({ rows: 198, counts, inspection: inspection.ndjson, previewPath }));
