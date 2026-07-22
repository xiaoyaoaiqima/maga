import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const inputPath = "/Users/luxifa/maga/outputs/a2_reiyu_backup_audit_20260721/A2礼遇_剩余301篇_含问题.csv";
const csvText = (await fs.readFile(inputPath, "utf8")).replace(/^\uFEFF/, "");
const workbook = await Workbook.fromCSV(csvText, { sheetName: "剩余文章" });
const values = workbook.worksheets.getItem("剩余文章").getUsedRange(true).values;
const headers = values[0].map((value) => String(value || ""));
const rows = values.slice(1).map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index] ?? ""])));
const problems = rows.filter((row) => row["审核结论"] === "有问题");

if (problems.length !== 11) throw new Error(`expected 11 problem rows, got ${problems.length}`);

console.log(JSON.stringify(problems.map((row) => ({
  sourceRow: row["原始行号"],
  category: row["审核分类"],
  title: row["标题"],
  body: row["正文"],
  issueType: row["问题类型"],
  issueReason: row["问题说明"],
})), null, 2));
