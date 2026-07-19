import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workbookPath = "/Users/luxifa/Downloads/a2_UGC评论话术库_20260716_查重修订版.xlsx";
const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const sheets = [];
for (const sheet of workbook.worksheets.items) {
  const used = sheet.getUsedRange(true);
  sheets.push({
    name: sheet.name,
    values: used ? used.values : [],
  });
}

process.stdout.write(JSON.stringify(sheets));
