import fs from "node:fs/promises";
import path from "node:path";
import { Workbook } from "@oai/artifact-tool";

const sources = {
  content_direction: "/Users/luxifa/Downloads/内容方向_子关键词导出-礼遇.csv",
  activity_content: "/Users/luxifa/Downloads/活动内容_子关键词导出-礼遇.csv",
  praise: "/Users/luxifa/Downloads/夸奖_礼遇_子关键词导出.csv",
  info_source: "/Users/luxifa/Downloads/了解途径_子关键词导出-礼遇.csv",
  motive: "/Users/luxifa/Downloads/动机_礼遇_子关键词导出.csv",
};

const output = {};
for (const [key, file] of Object.entries(sources)) {
  const raw = await fs.readFile(file, "utf8");
  const cleaned = raw
    .replace(/^\uFEFF/, "")
    .split(/\r?\n/)
    .filter((line) => !line.startsWith("#"))
    .join("\n");
  const workbook = await Workbook.fromCSV(cleaned, { sheetName: "Source" });
  const sheet = workbook.worksheets.getItem("Source");
  const values = sheet.getUsedRange(true).values;
  const [headers, ...data] = values;
  output[key] = data
    .filter((row) => row.some((value) => String(value ?? "").trim()))
    .map((row, index) => ({
      source_row: index + 2,
      ...Object.fromEntries(
        headers.map((header, column) => [String(header ?? "").trim(), String(row[column] ?? "").trim()]),
      ),
    }));
  const inspection = await workbook.inspect({
    kind: "table",
    range: `Source!A1:B${Math.min(values.length, 80)}`,
    include: "values",
    tableMaxRows: 80,
    tableMaxCols: 2,
    tableMaxCellChars: 500,
    maxChars: 30000,
  });
  process.stdout.write(`FILE ${path.basename(file)} ROWS ${output[key].length}\n${inspection.ndjson}\n`);
}

await fs.writeFile(
  "/Users/luxifa/maga/tmp/a2_reiyu_slot_ab_20260721/original_slots.json",
  JSON.stringify(output, null, 2),
  "utf8",
);
