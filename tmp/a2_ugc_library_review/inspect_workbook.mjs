import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';
import fs from 'node:fs/promises';

const inputPath = '/Users/luxifa/Downloads/a2_UGC评论话术库_20260716_查重修订版.xlsx';
const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const overview = await workbook.inspect({
  kind: 'workbook,sheet,table',
  maxChars: 12000,
  tableMaxRows: 8,
  tableMaxCols: 12,
  tableMaxCellChars: 160,
});

process.stdout.write(overview.ndjson);

for (const [sheetName, range] of [
  ['话术库', 'A1:D35'],
  ['生成提示词', 'A1:A3'],
  ['质检', 'A1:E9'],
]) {
  const preview = await workbook.render({
    sheetName,
    range,
    scale: 1.25,
    format: 'png',
  });
  const safeName = sheetName.replaceAll('/', '_');
  await fs.writeFile(
    `/Users/luxifa/maga/tmp/a2_ugc_library_review/${safeName}.png`,
    new Uint8Array(await preview.arrayBuffer()),
  );
}
