#!/usr/bin/env node

import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  classifyComment,
  configureLexicon,
  normalizeText,
  readCsv,
} from './analyze_xhs_comments.mjs';

const DEFAULT_OUT_DIR = 'local_data/xhs_monthly_sentiment_by_battle_0601';
const DEFAULT_LEXICON = '0601-a2评论-正负向词库.xlsx';
const MONTHS = ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05'];

const INPUTS = [
  {
    battle_key: 'out_of_stock',
    battle_category: '缺货断货类',
    file: 'A2 评论数据表 - 缺货断货类.csv',
  },
  {
    battle_key: 'safety_question',
    battle_category: '安全求证类',
    file: 'A2 评论数据表 - 安全求证类.csv',
  },
  {
    battle_key: 'transfer',
    battle_category: '转奶争夺战场',
    file: 'xhs_转奶争夺战场_top20x200_fast_comments_with_body.csv',
  },
  {
    battle_key: 'trust',
    battle_category: '品类信任教育战场',
    file: 'xhs_品类信任教育战场_top20x200_detail_comments_with_body.csv',
  },
];

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
  for (const row of rows) lines.push(headers.map((header) => csvEscape(row[header])).join(','));
  writeFileSync(file, `${lines.join('\n')}\n`, 'utf8');
}

function parseExcelSerialDate(value) {
  const num = Number(value);
  if (!Number.isFinite(num) || num < 1) return null;
  const timestamp = Date.UTC(1899, 11, 30) + num * 24 * 60 * 60 * 1000;
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? null : date;
}

function parseAnyTime(value, sourceName) {
  const text = String(value || '').trim();
  if (!text) return null;
  const excelDate = parseExcelSerialDate(text);
  if (excelDate) return { date: excelDate, source: `${sourceName}_excel_serial` };
  const isoDate = new Date(text);
  if (!Number.isNaN(isoDate.getTime())) return { date: isoDate, source: sourceName };
  const match = text.match(/^(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?/);
  if (match) {
    return {
      date: new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3] || '1'))),
      source: sourceName,
    };
  }
  return null;
}

function parseNoteIdTime(noteId) {
  const text = String(noteId || '').trim();
  if (!/^[0-9a-fA-F]{8}/.test(text)) return null;
  const seconds = Number.parseInt(text.slice(0, 8), 16);
  const date = new Date(seconds * 1000);
  return Number.isNaN(date.getTime()) ? null : { date, source: 'note_id_hex_timestamp' };
}

function monthKey(date) {
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`;
}

function monthLabel(month) {
  return `${Number(month.slice(5, 7))}月`;
}

function classifyText(text) {
  const cleanText = normalizeText(text);
  if (!cleanText) return { sentiment: '中性', polarity: 'neutral' };
  const result = classifyComment({ clean_comment_text: cleanText });
  let polarity = 'neutral';
  if (result.sentiment === '正向') polarity = 'positive';
  if (result.sentiment === '负向/疑虑' || result.sentiment === '混合') polarity = 'negative';
  return { ...result, polarity };
}

function pct(count, total) {
  if (!total) return '0.0%';
  return `${((count / total) * 100).toFixed(1)}%`;
}

function netScore(positive, negative, total) {
  if (!total) return '0.0';
  return (((positive - negative) / total) * 100).toFixed(1);
}

function pickBetterPost(current, next) {
  if (!current) return next;
  const currentLen = `${current.note_title || ''}${current.note_desc || ''}`.length;
  const nextLen = `${next.note_title || ''}${next.note_desc || ''}`.length;
  return nextLen > currentLen ? { ...next, duplicate_rows: current.duplicate_rows } : current;
}

function collectSamples() {
  const posts = new Map();
  const comments = new Map();
  const stats = {
    input_rows: 0,
    skipped_post_time_rows: 0,
    skipped_comment_time_rows: 0,
    skipped_missing_note_id_rows: 0,
    skipped_missing_comment_id_rows: 0,
    source_files: {},
  };

  for (const input of INPUTS) {
    const rows = readCsv(input.file);
    stats.source_files[input.file] = { rows: rows.length, battle_category: input.battle_category };
    for (const row of rows) {
      stats.input_rows += 1;
      const noteId = String(row.note_id || '').trim();
      if (!noteId) {
        stats.skipped_missing_note_id_rows += 1;
        continue;
      }

      const postTime = parseAnyTime(row.note_publish_time, 'note_publish_time') || parseNoteIdTime(noteId);
      if (postTime) {
        const postMonth = monthKey(postTime.date);
        if (MONTHS.includes(postMonth)) {
          const postKey = `${input.battle_key}::${noteId}`;
          const candidate = {
            sample_type: 'post',
            battle_key: input.battle_key,
            battle_category: input.battle_category,
            month: postMonth,
            month_label: monthLabel(postMonth),
            note_id: noteId,
            comment_id: '',
            note_title: row.note_title || '',
            note_desc: row.note_desc || '',
            comment_text: '',
            keyword: row.keyword || '',
            note_likes: row.note_likes || '',
            comment_likes: '',
            time: postTime.date.toISOString(),
            time_source: postTime.source,
            source_file: input.file,
            duplicate_rows: 1,
          };
          const existing = posts.get(postKey);
          const chosen = pickBetterPost(existing, candidate);
          chosen.duplicate_rows = existing ? existing.duplicate_rows + 1 : 1;
          posts.set(postKey, chosen);
        }
      } else {
        stats.skipped_post_time_rows += 1;
      }

      const commentId = String(row.comment_id || '').trim();
      if (!commentId) {
        stats.skipped_missing_comment_id_rows += 1;
        continue;
      }
      const commentTime = parseAnyTime(row.comment_time, 'comment_time');
      if (!commentTime) {
        stats.skipped_comment_time_rows += 1;
        continue;
      }
      const commentMonth = monthKey(commentTime.date);
      if (!MONTHS.includes(commentMonth)) continue;
      const commentKey = `${input.battle_key}::${commentId}`;
      if (comments.has(commentKey)) continue;
      comments.set(commentKey, {
        sample_type: 'comment',
        battle_key: input.battle_key,
        battle_category: input.battle_category,
        month: commentMonth,
        month_label: monthLabel(commentMonth),
        note_id: noteId,
        comment_id: commentId,
        note_title: row.note_title || '',
        note_desc: row.note_desc || '',
        comment_text: row.comment_text || '',
        keyword: row.keyword || '',
        note_likes: row.note_likes || '',
        comment_likes: row.comment_likes || '',
        time: commentTime.date.toISOString(),
        time_source: commentTime.source,
        source_file: input.file,
        duplicate_rows: 1,
      });
    }
  }

  return { posts: Array.from(posts.values()), comments: Array.from(comments.values()), stats };
}

function classifySamples(samples) {
  return samples.map((sample) => {
    const text = sample.sample_type === 'post'
      ? `${sample.note_title || ''} ${sample.note_desc || ''}`
      : sample.comment_text || '';
    const classified = classifyText(text);
    return {
      ...sample,
      sentiment: classified.sentiment,
      polarity: classified.polarity,
      primary_intent: classified.primary_intent || '',
      positive_tags: classified.positive_tags || '',
      risk_tags: classified.risk_tags || '',
      question_tags: classified.question_tags || '',
      ad_trade_tags: classified.ad_trade_tags || '',
    };
  });
}

function summarize(samples, sampleType) {
  const rows = [];
  for (const input of INPUTS) {
    for (const month of MONTHS) {
      const group = samples.filter((row) => row.battle_key === input.battle_key && row.month === month);
      const positive = group.filter((row) => row.polarity === 'positive').length;
      const negative = group.filter((row) => row.polarity === 'negative').length;
      const neutral = group.length - positive - negative;
      rows.push({
        sample_type: sampleType,
        battle_key: input.battle_key,
        battle_category: input.battle_category,
        month: monthLabel(month),
        total_count: group.length,
        positive_count: positive,
        negative_count: negative,
        neutral_or_excluded_count: neutral,
        positive_rate_all: pct(positive, group.length),
        negative_rate_all: pct(negative, group.length),
        neutral_or_excluded_rate_all: pct(neutral, group.length),
        net_positive_score_all: netScore(positive, negative, group.length),
      });
    }
  }
  return rows;
}

function combinedSamples(posts, comments) {
  return [
    ...posts.map((row) => ({ ...row, combined_unit_type: 'post' })),
    ...comments.map((row) => ({ ...row, combined_unit_type: 'comment' })),
  ];
}

function markdownTable(headers, rows) {
  const line = `| ${headers.join(' | ')} |`;
  const sep = `| ${headers.map(() => '---').join(' | ')} |`;
  const body = rows.map((row) => `| ${headers.map((header) => row[header]).join(' | ')} |`);
  return [line, sep, ...body].join('\n');
}

function buildReport({ postSummary, commentSummary, combinedSummary, stats, lexiconInfo }) {
  const lines = [];
  lines.push('# 小红书/A2 四大战场月度正负向趋势');
  lines.push('');
  lines.push('生成时间：2026-06-01');
  lines.push('');
  lines.push('## 口径');
  lines.push('');
  lines.push('- 按四大战场分别统计：缺货断货类、安全求证类、转奶争夺战场、品类信任教育战场。');
  lines.push('- 帖子趋势：按 `battle + note_id` 去重，情感只看 `note_title + note_desc`，月份按帖子发布时间；缺失时用 `note_id` 前 8 位推导。');
  lines.push('- 评论趋势：按 `battle + comment_id` 去重，情感只看 `comment_text`，月份按评论时间。');
  lines.push('- 综合趋势：帖子样本和评论样本相加作为总分母，不使用“有效情感”口径。');
  lines.push('- 负向包括 `负向/疑虑` 和 `混合`；比例分母均为当前战场当前月份的全部样本。');
  if (lexiconInfo) {
    lines.push(`- 情感词库：\`${lexiconInfo.file}\`（正向 ${lexiconInfo.positive_count} 条，负向 ${lexiconInfo.negative_count} 条，弱正向 ${lexiconInfo.weak_positive_count} 条）。`);
  }
  lines.push('');
  lines.push('## 综合趋势');
  lines.push('');
  lines.push(markdownTable([
    'battle_category',
    'month',
    'total_count',
    'positive_count',
    'negative_count',
    'neutral_or_excluded_count',
    'positive_rate_all',
    'negative_rate_all',
    'net_positive_score_all',
  ], combinedSummary));
  lines.push('');
  lines.push('## 帖子趋势');
  lines.push('');
  lines.push(markdownTable([
    'battle_category',
    'month',
    'total_count',
    'positive_count',
    'negative_count',
    'neutral_or_excluded_count',
    'positive_rate_all',
    'negative_rate_all',
    'net_positive_score_all',
  ], postSummary));
  lines.push('');
  lines.push('## 评论趋势');
  lines.push('');
  lines.push(markdownTable([
    'battle_category',
    'month',
    'total_count',
    'positive_count',
    'negative_count',
    'neutral_or_excluded_count',
    'positive_rate_all',
    'negative_rate_all',
    'net_positive_score_all',
  ], commentSummary));
  lines.push('');
  lines.push('## 初步观察');
  for (const input of INPUTS) {
    const may = combinedSummary.find((row) => row.battle_key === input.battle_key && row.month === '5月');
    const apr = combinedSummary.find((row) => row.battle_key === input.battle_key && row.month === '4月');
    if (!may || !apr) continue;
    lines.push(`- ${input.battle_category}：综合负向率从 4 月 ${apr.negative_rate_all} 到 5 月 ${may.negative_rate_all}，5 月样本量 ${may.total_count}。`);
  }
  lines.push('');
  lines.push('## 数据处理统计');
  lines.push('');
  lines.push(`- 输入行：${stats.input_rows}`);
  lines.push(`- 缺 note_id 行：${stats.skipped_missing_note_id_rows}`);
  lines.push(`- 缺 comment_id 行：${stats.skipped_missing_comment_id_rows}`);
  lines.push(`- 帖子时间无法解析行：${stats.skipped_post_time_rows}`);
  lines.push(`- 评论时间无法解析行：${stats.skipped_comment_time_rows}`);
  return `${lines.join('\n')}\n`;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const outDir = args['out-dir'] || DEFAULT_OUT_DIR;
  const lexicon = configureLexicon(args.lexicon || DEFAULT_LEXICON);
  mkdirSync(outDir, { recursive: true });

  const { posts, comments, stats } = collectSamples();
  const postDetails = classifySamples(posts).sort((a, b) => a.battle_key.localeCompare(b.battle_key) || a.month.localeCompare(b.month) || a.note_id.localeCompare(b.note_id));
  const commentDetails = classifySamples(comments).sort((a, b) => a.battle_key.localeCompare(b.battle_key) || a.month.localeCompare(b.month) || a.comment_id.localeCompare(b.comment_id));
  const combinedDetails = combinedSamples(postDetails, commentDetails);

  const postSummary = summarize(postDetails, 'post');
  const commentSummary = summarize(commentDetails, 'comment');
  const combinedSummary = summarize(combinedDetails, 'combined');
  const allSummary = [...postSummary, ...commentSummary, ...combinedSummary];
  const lexiconInfo = lexicon
    ? {
        file: lexicon.file,
        positive_count: lexicon.positiveRules.length,
        negative_count: lexicon.negativeRules.length,
        weak_positive_count: lexicon.weakPositiveRules.size,
      }
    : null;

  const detailHeaders = [
    'sample_type', 'battle_key', 'battle_category', 'month', 'month_label', 'note_id', 'comment_id',
    'note_title', 'note_desc', 'comment_text', 'keyword', 'time', 'time_source', 'sentiment', 'polarity',
    'positive_tags', 'risk_tags', 'question_tags', 'ad_trade_tags', 'source_file',
  ];
  const summaryHeaders = [
    'sample_type', 'battle_key', 'battle_category', 'month', 'total_count', 'positive_count',
    'negative_count', 'neutral_or_excluded_count', 'positive_rate_all', 'negative_rate_all',
    'neutral_or_excluded_rate_all', 'net_positive_score_all',
  ];

  const postDetailFile = join(outDir, 'monthly_post_sentiment_detail.csv');
  const commentDetailFile = join(outDir, 'monthly_comment_sentiment_detail.csv');
  const postSummaryFile = join(outDir, 'monthly_post_sentiment_summary.csv');
  const commentSummaryFile = join(outDir, 'monthly_comment_sentiment_summary.csv');
  const combinedSummaryFile = join(outDir, 'monthly_combined_sentiment_summary.csv');
  const allSummaryFile = join(outDir, 'monthly_sentiment_all_summary.csv');
  const reportFile = join(outDir, 'monthly_sentiment_by_battle_report.md');
  const metaFile = join(outDir, 'monthly_sentiment_by_battle_summary.json');

  writeCsv(postDetailFile, postDetails, detailHeaders);
  writeCsv(commentDetailFile, commentDetails, detailHeaders);
  writeCsv(postSummaryFile, postSummary, summaryHeaders);
  writeCsv(commentSummaryFile, commentSummary, summaryHeaders);
  writeCsv(combinedSummaryFile, combinedSummary, summaryHeaders);
  writeCsv(allSummaryFile, allSummary, summaryHeaders);
  writeFileSync(reportFile, buildReport({ postSummary, commentSummary, combinedSummary, stats, lexiconInfo }), 'utf8');
  writeFileSync(metaFile, `${JSON.stringify({
    inputs: INPUTS,
    stats,
    post_detail_rows: postDetails.length,
    comment_detail_rows: commentDetails.length,
    outputs: [
      postDetailFile,
      commentDetailFile,
      postSummaryFile,
      commentSummaryFile,
      combinedSummaryFile,
      allSummaryFile,
      reportFile,
    ],
    lexicon: lexiconInfo || 'builtin',
  }, null, 2)}\n`, 'utf8');

  console.log(JSON.stringify({
    post_detail_rows: postDetails.length,
    comment_detail_rows: commentDetails.length,
    outputs: [postSummaryFile, commentSummaryFile, combinedSummaryFile, reportFile, metaFile],
    combined_summary: combinedSummary,
  }, null, 2));
}

main();
