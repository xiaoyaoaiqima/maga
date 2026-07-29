import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const inputPath = process.argv[2];
const csvText = await fs.readFile(inputPath, "utf8");
const workbook = await Workbook.fromCSV(csvText, { sheetName: "Source" });
const result = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 12000,
  tableMaxRows: 8,
  tableMaxCols: 16,
  tableMaxCellChars: 180,
});
process.stdout.write(result.ndjson);
