import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const sourcePath = "/Users/luxifa/Downloads/正向词_子关键词导出.csv";
const csvText = await fs.readFile(sourcePath, "utf8");
const workbook = await Workbook.fromCSV(csvText, { sheetName: "正向词" });

const overview = await workbook.inspect({
  kind: "table",
  range: "正向词!A1:F40",
  include: "values",
  tableMaxRows: 40,
  tableMaxCols: 6,
  tableMaxCellChars: 300,
  maxChars: 16000,
});

process.stdout.write(`${overview.ndjson}\n`);
