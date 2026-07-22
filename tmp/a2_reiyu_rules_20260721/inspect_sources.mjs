import fs from "node:fs/promises";
import path from "node:path";
import { Workbook } from "@oai/artifact-tool";

const files = [
  "/Users/luxifa/Downloads/了解途径_子关键词导出-礼遇.csv",
  "/Users/luxifa/Downloads/正向词_子关键词导出.csv",
  "/Users/luxifa/Downloads/动机_礼遇_子关键词导出.csv",
  "/Users/luxifa/Downloads/夸奖_礼遇_子关键词导出.csv",
  "/Users/luxifa/Downloads/活动内容_子关键词导出-礼遇.csv",
  "/Users/luxifa/Downloads/内容方向_子关键词导出-礼遇.csv",
];

for (const file of files) {
  const raw = await fs.readFile(file, "utf8");
  const cleaned = raw
    .split(/(?<=\n)/)
    .filter((line) => !line.startsWith("#"))
    .join("");
  const workbook = await Workbook.fromCSV(cleaned, { sheetName: "Source" });
  const inspected = await workbook.inspect({
    kind: "table",
    range: "Source!A1:F120",
    include: "values",
    tableMaxRows: 120,
    tableMaxCols: 6,
    tableMaxCellChars: 600,
    maxChars: 30000,
  });
  process.stdout.write(`\nFILE ${path.basename(file)}\n${inspected.ndjson}\n`);
}

const probe = Workbook.create();
for (const query of ["Workbook.toCSV", "SpreadsheetFile.exportCsv"]) {
  process.stdout.write(
    `\nCSV_HELP ${query}\n${probe.help(query, {
      include: "index,examples,notes",
      maxChars: 6000,
    }).ndjson}\n`,
  );
}
