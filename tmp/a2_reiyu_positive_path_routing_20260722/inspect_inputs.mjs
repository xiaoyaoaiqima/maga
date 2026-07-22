import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const files = [
  {
    label: "v17",
    path: "/Users/luxifa/maga/outputs/a2_reiyu_v17_title_hard_drop_20260721/a2礼遇UGC分享贴_v17标题超20淘汰.csv",
    sheetName: "业务规则",
  },
  {
    label: "positive_source",
    path: "/Users/luxifa/Downloads/正向词_子关键词导出 (1).csv",
    sheetName: "正向词",
  },
];

for (const file of files) {
  const raw = await fs.readFile(file.path, "utf8");
  const cleaned = raw
    .replace(/^\uFEFF/, "")
    .split(/\r?\n/)
    .filter((line) => !line.startsWith("#"))
    .join("\n");
  const workbook = await Workbook.fromCSV(cleaned, { sheetName: file.sheetName });
  const sheet = workbook.worksheets.getItem(file.sheetName);
  const used = sheet.getUsedRange(true);
  const values = used.values;
  const headers = values[0].map((value) => String(value ?? "").replace(/^\uFEFF/, ""));
  const inspect = await workbook.inspect({
    kind: "table",
    range: `${file.sheetName}!A1:O${Math.min(values.length, 15)}`,
    include: "values",
    tableMaxRows: 15,
    tableMaxCols: 15,
    tableMaxCellChars: 800,
    maxChars: 30000,
  });
  process.stdout.write(`${JSON.stringify({ label: file.label, rows: values.length - 1, headers })}\n`);
  process.stdout.write(`${inspect.ndjson}\n`);
}
