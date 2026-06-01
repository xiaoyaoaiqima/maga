#!/usr/bin/env node

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { readCsv } from './analyze_xhs_comments.mjs';

const DEFAULT_INPUT = 'local_data/xhs_post_monthly_sentiment_0601/post_monthly_sentiment_detail.csv';
const DEFAULT_OUT_DIR = 'local_data/xhs_event_negative_trend_0601';

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const part = argv[i];
    if (!part.startsWith('--')) continue;
    const key = part.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith('--')) {
      args[key] = true;
    } else {
      args[key] = next;
      i += 1;
    }
  }
  return args;
}

function csvEscape(value) {
  const text = value == null ? '' : String(value);
  if (!/[",\n\r]/.test(text)) return text;
  return `"${text.replaceAll('"', '""')}"`;
}

function writeCsv(file, rows, headers) {
  const lines = [headers.join(',')];
  for (const row of rows) {
    lines.push(headers.map((header) => csvEscape(row[header])).join(','));
  }
  writeFileSync(file, `${lines.join('\n')}\n`, 'utf8');
}

function pct(count, total) {
  if (!total) return '0.0%';
  return `${((count / total) * 100).toFixed(1)}%`;
}

function dateKey(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toISOString().slice(0, 10);
}

function weekBucket(dateText) {
  const [, month, dayText] = dateText.match(/^2026-(\d{2})-(\d{2})$/) || [];
  if (!month) return '';
  const day = Number(dayText);
  const start = day <= 7 ? '01' : day <= 14 ? '08' : day <= 21 ? '15' : '22';
  const end = day <= 7 ? '07' : day <= 14 ? '14' : day <= 21 ? '21' : String(new Date(Date.UTC(2026, Number(month), 0)).getUTCDate()).padStart(2, '0');
  return `2026-${month}-${start}~${end}`;
}

function includesAny(text, terms) {
  return terms.some((term) => text.includes(term));
}

function eventTags(text) {
  const tags = [];
  if (includesAny(text, ['召回', '召 回', 'recall', 'Recall'])) tags.push('召回事件');
  if (includesAny(text, ['毒素', '呕吐毒素', 'DON', '霉菌毒素'])) tags.push('毒素/呕吐毒素');
  if (includesAny(text, ['断货', '缺货', '没货', '买不到', '抢不到', '下架', '停产', '断供'])) tags.push('断货/缺货');
  if (includesAny(text, ['官方', '声明', '公告', '回应', '通知', '辟谣', '澄清'])) tags.push('官方回应/声明');
  if (includesAny(text, ['海关', '监管', '市场监管', '食药监', '总署', 'FDA', '美国'])) tags.push('海关/监管/美国');
  if (includesAny(text, ['批次', '批号', '自查', '查批次', '批次号'])) tags.push('批次自查');
  if (includesAny(text, ['转奶', '换奶', '不适应', '拉肚子', '拉稀', '便秘', '吐奶', '胀气', '拒奶', '绿便', '奶瓣'])) tags.push('喂养/转奶体验');
  if (includesAny(text, ['贵', '价格', '涨价', '便宜', '活动', '囤货', '购买', '代购', '山姆', '京东', '淘宝'])) tags.push('价格/购买');
  return Array.from(new Set(tags));
}

function classifyEventTone(text, tags, basePolarity) {
  const strongAlarm = [
    '检出', '呕吐毒素', '毒素', '紧急', '海关提醒', '总署', '召回', '下架', '停产',
    '断货', '断供', '缺货', '没货', '买不到', '不敢喝', '不敢买', '出事', '有问题',
    '怎么解释', '吓人', '天塌', '风险', '涉事', '污染',
  ];
  const reassurance = [
    '不涉及', '没事', '没有问题', '没问题', '放心', '安心', '正常售卖', '正常喝',
    '官方声明', '辟谣', '澄清', '别慌', '不要焦虑', '不传谣', '不信谣', '自查',
  ];
  const eventRelated = tags.some((tag) => ['召回事件', '毒素/呕吐毒素', '断货/缺货', '官方回应/声明', '海关/监管/美国', '批次自查'].includes(tag));
  if (!eventRelated) return 'none';
  const hasAlarm = includesAny(text, strongAlarm);
  const hasReassurance = includesAny(text, reassurance);
  if (hasAlarm && !hasReassurance) return 'strong_negative';
  if (hasAlarm && hasReassurance) return 'mixed_event';
  if (hasReassurance) return 'reassurance';
  if (basePolarity === 'negative') return 'concern';
  return 'event_related_neutral';
}

function isEventNegative(tone) {
  return ['strong_negative', 'mixed_event', 'concern'].includes(tone);
}

function makeTrendRows(rows, keyField) {
  const keys = Array.from(new Set(rows.map((row) => row[keyField]).filter(Boolean))).sort();
  return keys.map((key) => {
    const group = rows.filter((row) => row[keyField] === key);
    const eventRelated = group.filter((row) => row.event_related === '是');
    const eventNegative = group.filter((row) => row.event_negative === '是');
    const baseNegative = group.filter((row) => row.polarity === 'negative');
    return {
      [keyField]: key,
      total_posts: group.length,
      base_negative_posts: baseNegative.length,
      base_negative_rate: pct(baseNegative.length, group.length),
      event_related_posts: eventRelated.length,
      event_related_rate: pct(eventRelated.length, group.length),
      event_negative_posts: eventNegative.length,
      event_negative_rate_all_posts: pct(eventNegative.length, group.length),
      recall_posts: group.filter((row) => row.event_tags.includes('召回事件')).length,
      toxin_posts: group.filter((row) => row.event_tags.includes('毒素/呕吐毒素')).length,
      stockout_posts: group.filter((row) => row.event_tags.includes('断货/缺货')).length,
      official_response_posts: group.filter((row) => row.event_tags.includes('官方回应/声明')).length,
      customs_us_posts: group.filter((row) => row.event_tags.includes('海关/监管/美国')).length,
    };
  });
}

function makeMonthlyTagRows(rows) {
  const months = ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05'];
  const tags = ['召回事件', '毒素/呕吐毒素', '断货/缺货', '官方回应/声明', '海关/监管/美国', '批次自查', '喂养/转奶体验', '价格/购买'];
  const output = [];
  for (const month of months) {
    const group = rows.filter((row) => row.month === month);
    for (const tag of tags) {
      const count = group.filter((row) => row.event_tags.includes(tag)).length;
      output.push({
        month: `${Number(month.slice(5, 7))}月`,
        event_tag: tag,
        post_count: count,
        rate_all_posts: pct(count, group.length),
      });
    }
  }
  return output;
}

function rankExamples(rows) {
  const mayRows = rows.filter((row) => row.month === '2026-05' && row.event_negative === '是');
  const score = (row) => {
    let value = 0;
    if (row.event_tags.includes('毒素/呕吐毒素')) value += 5;
    if (row.event_tags.includes('召回事件')) value += 4;
    if (row.event_tags.includes('断货/缺货')) value += 3;
    if (row.event_tags.includes('海关/监管/美国')) value += 3;
    if (row.event_tone === 'strong_negative') value += 3;
    value += Math.min(Number(row.note_likes || 0) || 0, 100) / 25;
    return value;
  };
  return mayRows
    .sort((a, b) => score(b) - score(a) || a.date.localeCompare(b.date))
    .slice(0, 100);
}

function markdownTable(headers, rows) {
  const line = `| ${headers.join(' | ')} |`;
  const sep = `| ${headers.map(() => '---').join(' | ')} |`;
  const body = rows.map((row) => `| ${headers.map((header) => row[header]).join(' | ')} |`);
  return [line, sep, ...body].join('\n');
}

function buildReport({ dailyRows, weeklyRows, monthlyTagRows, examples }) {
  const lines = [];
  lines.push('# A2 小红书 5 月突发舆情负向趋势');
  lines.push('');
  lines.push('生成时间：2026-06-01');
  lines.push('');
  lines.push('## 口径');
  lines.push('');
  lines.push('- 基于 `post_monthly_sentiment_detail.csv` 的帖子级去重结果。');
  lines.push('- 不再只看泛负向，而是识别召回、毒素/呕吐毒素、断货/缺货、官方回应、海关/监管/美国、批次自查等事件标签。');
  lines.push('- `event_negative` 表示事件相关且语气为强负向、混合事件或疑虑。');
  lines.push('');
  lines.push('## 5 月周趋势');
  lines.push('');
  const mayWeeks = weeklyRows.filter((row) => row.week_bucket.startsWith('2026-05'));
  lines.push(markdownTable([
    'week_bucket',
    'total_posts',
    'base_negative_posts',
    'base_negative_rate',
    'event_related_posts',
    'event_negative_posts',
    'event_negative_rate_all_posts',
    'recall_posts',
    'toxin_posts',
    'stockout_posts',
    'customs_us_posts',
  ], mayWeeks));
  lines.push('');
  lines.push('## 事件标签月度变化');
  lines.push('');
  const keyTags = monthlyTagRows.filter((row) => ['召回事件', '毒素/呕吐毒素', '断货/缺货', '官方回应/声明', '海关/监管/美国'].includes(row.event_tag));
  lines.push(markdownTable(['month', 'event_tag', 'post_count', 'rate_all_posts'], keyTags));
  lines.push('');
  lines.push('## 5 月典型事件负向样本');
  lines.push('');
  for (const row of examples.slice(0, 20)) {
    lines.push(`- ${row.date}｜${row.note_title || row.note_desc.slice(0, 60)}｜${row.event_tags}｜${row.event_tone}`);
  }
  lines.push('');
  lines.push('## 初步判断');
  lines.push('');
  const mayRows = weeklyRows.filter((row) => row.week_bucket.startsWith('2026-05'));
  const maxWeek = mayRows.slice().sort((a, b) => Number(b.event_negative_posts) - Number(a.event_negative_posts))[0];
  if (maxWeek) {
    lines.push(`- 5 月事件负向最高峰出现在 ${maxWeek.week_bucket}，事件负向帖子 ${maxWeek.event_negative_posts} 篇。`);
  }
  lines.push('- 5 月负向增长应优先解释为突发事件舆情增长，而不是普通体验差评增长。');
  lines.push('- 后续如果要对外汇报，建议单独拆“召回/毒素/断货/官方回应”四条线，而不是只报总体负向率。');
  return `${lines.join('\n')}\n`;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const input = args.input || DEFAULT_INPUT;
  const outDir = args['out-dir'] || DEFAULT_OUT_DIR;
  mkdirSync(outDir, { recursive: true });

  const rows = readCsv(input)
    .map((row) => {
      const text = `${row.note_title || ''} ${row.note_desc || ''}`;
      const tags = eventTags(text);
      const tone = classifyEventTone(text, tags, row.polarity);
      const date = dateKey(row.post_time);
      return {
        ...row,
        date,
        week_bucket: weekBucket(date),
        event_tags: tags.join('|'),
        event_related: tags.some((tag) => ['召回事件', '毒素/呕吐毒素', '断货/缺货', '官方回应/声明', '海关/监管/美国', '批次自查'].includes(tag)) ? '是' : '否',
        event_tone: tone,
        event_negative: isEventNegative(tone) ? '是' : '否',
      };
    })
    .filter((row) => row.date);

  const dailyRows = makeTrendRows(rows, 'date');
  const weeklyRows = makeTrendRows(rows, 'week_bucket');
  const monthlyTagRows = makeMonthlyTagRows(rows);
  const examples = rankExamples(rows);

  const eventDetailFile = join(outDir, 'event_negative_post_detail.csv');
  const dailyFile = join(outDir, 'daily_event_negative_trend.csv');
  const weeklyFile = join(outDir, 'weekly_event_negative_trend.csv');
  const monthlyTagFile = join(outDir, 'event_tag_monthly_summary.csv');
  const examplesFile = join(outDir, 'may_event_negative_examples.csv');
  const reportFile = join(outDir, 'event_spike_report.md');
  const metaFile = join(outDir, 'event_spike_summary.json');

  writeCsv(eventDetailFile, rows, [
    'month', 'date', 'week_bucket', 'note_id', 'note_title', 'note_desc', 'sentiment', 'polarity',
    'event_tags', 'event_related', 'event_tone', 'event_negative', 'source_labels', 'source_files',
    'note_likes', 'note_comments_count', 'post_time', 'time_source',
  ]);
  writeCsv(dailyFile, dailyRows, [
    'date', 'total_posts', 'base_negative_posts', 'base_negative_rate', 'event_related_posts',
    'event_related_rate', 'event_negative_posts', 'event_negative_rate_all_posts',
    'recall_posts', 'toxin_posts', 'stockout_posts',
    'official_response_posts', 'customs_us_posts',
  ]);
  writeCsv(weeklyFile, weeklyRows, [
    'week_bucket', 'total_posts', 'base_negative_posts', 'base_negative_rate', 'event_related_posts',
    'event_related_rate', 'event_negative_posts', 'event_negative_rate_all_posts',
    'recall_posts', 'toxin_posts', 'stockout_posts',
    'official_response_posts', 'customs_us_posts',
  ]);
  writeCsv(monthlyTagFile, monthlyTagRows, ['month', 'event_tag', 'post_count', 'rate_all_posts']);
  writeCsv(examplesFile, examples, [
    'date', 'note_id', 'note_title', 'note_desc', 'event_tags', 'event_tone', 'sentiment', 'polarity',
    'source_labels', 'note_likes', 'note_comments_count',
  ]);
  writeFileSync(reportFile, buildReport({ dailyRows, weeklyRows, monthlyTagRows, examples }), 'utf8');
  writeFileSync(metaFile, `${JSON.stringify({
    input,
    input_rows: rows.length,
    outputs: [eventDetailFile, dailyFile, weeklyFile, monthlyTagFile, examplesFile, reportFile],
    may_weekly: weeklyRows.filter((row) => row.week_bucket.startsWith('2026-05')),
    may_top_event_negative_examples: examples.slice(0, 10).map((row) => ({
      date: row.date,
      title: row.note_title,
      event_tags: row.event_tags,
      event_tone: row.event_tone,
    })),
  }, null, 2)}\n`, 'utf8');

  console.log(readFileSync(metaFile, 'utf8'));
}

main();
