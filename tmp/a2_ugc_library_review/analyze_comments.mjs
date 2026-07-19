import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const inputPath = '/Users/luxifa/Downloads/a2_UGC评论话术库_20260716_查重修订版.xlsx';
const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItem('话术库');
const values = sheet.getRange('A3:D103').values;
const headers = values[0];
const columns = headers.map((header, colIndex) => ({
  header,
  colIndex,
  comments: values.slice(1).map((row, rowIndex) => ({
    cell: `${String.fromCharCode(65 + colIndex)}${rowIndex + 4}`,
    text: String(row[colIndex] || '').trim(),
  })),
}));

function topCounts(items, limit = 12) {
  const counts = new Map();
  for (const item of items) {
    if (!item) continue;
    counts.set(item, (counts.get(item) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'zh-CN'))
    .slice(0, limit)
    .map(([text, count]) => ({ text, count }));
}

function repeatedNgrams(comments, n = 6, limit = 12) {
  const owners = new Map();
  for (const { cell, text } of comments) {
    const normalized = text.replace(/[，。！？、~～😂哈哈\s]/g, '');
    const seen = new Set();
    for (let i = 0; i <= normalized.length - n; i += 1) {
      seen.add(normalized.slice(i, i + n));
    }
    for (const gram of seen) {
      if (!owners.has(gram)) owners.set(gram, []);
      owners.get(gram).push(cell);
    }
  }
  return [...owners.entries()]
    .filter(([, cells]) => cells.length >= 3)
    .sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0], 'zh-CN'))
    .slice(0, limit)
    .map(([text, cells]) => ({ text, count: cells.length, cells: cells.slice(0, 8) }));
}

const report = columns.map(({ header, comments }) => {
  const texts = comments.map((item) => item.text);
  const firstClauses = texts.map((text) => text.split('，')[0]);
  const lastClauses = texts.map((text) => text.split('，').at(-1));
  const lengths = texts.map((text) => [...text].length);
  const quarterRepeat = comments.slice(0, 75).filter((item, index) => {
    const later = comments[index + 25];
    return later && item.text.split('，')[0] === later.text.split('，')[0];
  }).length;
  return {
    header,
    count: texts.length,
    unique_exact: new Set(texts).size,
    avg_length: Number((lengths.reduce((sum, length) => sum + length, 0) / lengths.length).toFixed(1)),
    unique_first_clause: new Set(firstClauses).size,
    unique_last_clause: new Set(lastClauses).size,
    repeated_first_clause_pairs_at_25_row_gap: quarterRepeat,
    top_first_clauses: topCounts(firstClauses),
    top_last_clauses: topCounts(lastClauses),
    repeated_6grams: repeatedNgrams(comments),
  };
});

const suspiciousPatterns = [
  /(.{2,8})\1/,
  /我看到就看到就/,
  /买完奶粉买完/,
  /随即.*随即/,
  /抽奖我都会.*我都会/,
  /对着罐底.*对着/,
  /刚点.*点一下/,
];
const suspicious = columns.flatMap(({ header, comments }) =>
  comments
    .filter(({ text }) => suspiciousPatterns.some((pattern) => pattern.test(text)))
    .map((item) => ({ header, ...item })),
);

process.stdout.write(`${JSON.stringify({ report, suspicious }, null, 2)}\n`);
