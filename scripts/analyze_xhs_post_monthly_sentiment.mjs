#!/usr/bin/env node

import { mkdirSync, writeFileSync } from 'node:fs';
import { basename, join } from 'node:path';
import {
  classifyComment,
  configureLexicon,
  normalizeText,
  readCsv,
} from './analyze_xhs_comments.mjs';

const DEFAULT_OUT_DIR = 'local_data/xhs_post_monthly_sentiment_0601';
const DEFAULT_LEXICON = '0601-a2评论-正负向词库.xlsx';

const INPUTS = [
  {
    source_key: 'a2_out_of_stock',
    source_label: 'A2 评论数据表 - 缺货断货类',
    file: 'A2 评论数据表 - 缺货断货类.csv',
  },
  {
    source_key: 'a2_safety_question',
    source_label: 'A2 评论数据表 - 安全求证类',
    file: 'A2 评论数据表 - 安全求证类.csv',
  },
  {
    source_key: 'transfer',
    source_label: '转奶争夺战场',
    file: 'xhs_转奶争夺战场_top20x200_fast_comments_with_body.csv',
  },
  {
    source_key: 'trust',
    source_label: '品类信任教育战场',
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
  for (const row of rows) {
    lines.push(headers.map((header) => csvEscape(row[header])).join(','));
  }
  writeFileSync(file, `${lines.join('\n')}\n`, 'utf8');
}

function parseExcelSerialDate(value) {
  const num = Number(value);
  if (!Number.isFinite(num) || num < 1) return null;
  // Excel serial date uses 1899-12-30 as practical epoch, including fractional days.
  const timestamp = Date.UTC(1899, 11, 30) + num * 24 * 60 * 60 * 1000;
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return null;
  return date;
}

function parseExplicitTime(value) {
  const text = String(value || '').trim();
  if (!text) return null;
  const excelDate = parseExcelSerialDate(text);
  if (excelDate) return { date: excelDate, source: 'note_publish_time_excel_serial' };

  const date = new Date(text);
  if (!Number.isNaN(date.getTime())) return { date, source: 'note_publish_time' };

  const match = text.match(/^(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?/);
  if (match) {
    return {
      date: new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3] || '1'))),
      source: 'note_publish_time',
    };
  }
  return null;
}

function parseNoteIdTime(noteId) {
  const text = String(noteId || '').trim();
  if (!/^[0-9a-fA-F]{8}/.test(text)) return null;
  const seconds = Number.parseInt(text.slice(0, 8), 16);
  if (!Number.isFinite(seconds)) return null;
  const date = new Date(seconds * 1000);
  if (Number.isNaN(date.getTime())) return null;
  return { date, source: 'note_id_hex_timestamp' };
}

function resolvePostTime(row) {
  return parseExplicitTime(row.note_publish_time) || parseNoteIdTime(row.note_id);
}

function monthKey(date) {
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}`;
}

function monthLabel(key) {
  const [, month] = key.split('-');
  return `${Number(month)}月`;
}

function isTargetMonth(key) {
  return ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05'].includes(key);
}

function classifyPost(title, desc) {
  const cleanText = normalizeText([title, desc].filter(Boolean).join(' '));
  if (!cleanText) {
    return {
      sentiment: '中性',
      polarity: 'none',
      primary_intent: '',
      positive_tags: '',
      risk_tags: '',
      question_tags: '',
      ad_trade_tags: '',
    };
  }
  const result = classifyComment({ clean_comment_text: cleanText });
  let polarity = 'none';
  if (result.sentiment === '正向') polarity = 'positive';
  if (result.sentiment === '负向/疑虑' || result.sentiment === '混合') polarity = 'negative';
  return { ...result, polarity };
}

function pct(count, total) {
  if (!total) return '0.0%';
  return `${((count / total) * 100).toFixed(1)}%`;
}

function netPositiveScore(positive, negative) {
  const valid = positive + negative;
  if (!valid) return '0.0';
  return (((positive - negative) / valid) * 100).toFixed(1);
}

function betterPostCandidate(current, next) {
  if (!current) return next;
  const currentTextLength = `${current.note_title || ''}${current.note_desc || ''}`.length;
  const nextTextLength = `${next.note_title || ''}${next.note_desc || ''}`.length;
  if (nextTextLength > currentTextLength) return { ...next, source_files: current.source_files };
  return current;
}

function collectPosts() {
  const posts = new Map();
  const stats = {
    input_rows: 0,
    missing_note_id_rows: 0,
    out_of_month_posts: 0,
    unparsed_time_posts: 0,
    source_files: {},
  };

  for (const input of INPUTS) {
    const rows = readCsv(input.file);
    stats.source_files[input.file] = { rows: rows.length, source_label: input.source_label };
    for (const row of rows) {
      stats.input_rows += 1;
      const noteId = String(row.note_id || '').trim();
      if (!noteId) {
        stats.missing_note_id_rows += 1;
        continue;
      }
      const resolved = resolvePostTime(row);
      if (!resolved) {
        stats.unparsed_time_posts += 1;
        continue;
      }
      const month = monthKey(resolved.date);
      if (!isTargetMonth(month)) {
        stats.out_of_month_posts += 1;
        continue;
      }

      const candidate = {
        source_keys: input.source_key,
        source_labels: input.source_label,
        source_files: input.file,
        month,
        month_label: monthLabel(month),
        note_id: noteId,
        note_url: row.note_url || '',
        note_title: row.note_title || '',
        note_desc: row.note_desc || '',
        note_tags: row.note_tags || '',
        keyword: row.keyword || '',
        note_likes: row.note_likes || '',
        note_comments_count: row.note_comments_count || '',
        post_time: resolved.date.toISOString(),
        time_source: resolved.source,
      };

      const existing = posts.get(noteId);
      if (existing) {
        const merged = betterPostCandidate(existing, candidate);
        merged.source_keys = Array.from(new Set(`${existing.source_keys}|${candidate.source_keys}`.split('|'))).join('|');
        merged.source_labels = Array.from(new Set(`${existing.source_labels}|${candidate.source_labels}`.split('|'))).join('|');
        merged.source_files = Array.from(new Set(`${existing.source_files}|${candidate.source_files}`.split('|'))).join('|');
        posts.set(noteId, merged);
      } else {
        posts.set(noteId, candidate);
      }
    }
  }
  return { posts: Array.from(posts.values()), stats };
}

function buildSummaryRows(detailRows) {
  const months = ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05'];
  return months.map((month) => {
    const rows = detailRows.filter((row) => row.month === month);
    const positive = rows.filter((row) => row.polarity === 'positive').length;
    const negative = rows.filter((row) => row.polarity === 'negative').length;
    const valid = positive + negative;
    const neutral = rows.length - valid;
    return {
      month: monthLabel(month),
      total_posts: rows.length,
      positive_count: positive,
      negative_count: negative,
      neutral_or_excluded_count: neutral,
      positive_rate_all_posts: pct(positive, rows.length),
      negative_rate_all_posts: pct(negative, rows.length),
      valid_sentiment_posts: valid,
      positive_rate_valid: pct(positive, valid),
      negative_rate_valid: pct(negative, valid),
      net_positive_score: netPositiveScore(positive, negative),
    };
  });
}

function markdownTable(headers, rows) {
  const line = `| ${headers.join(' | ')} |`;
  const sep = `| ${headers.map(() => '---').join(' | ')} |`;
  const body = rows.map((row) => `| ${headers.map((header) => row[header]).join(' | ')} |`);
  return [line, sep, ...body].join('\n');
}

function pickExamples(detailRows, month, polarity, limit = 5) {
  return detailRows
    .filter((row) => row.month === month && row.polarity === polarity)
    .sort((a, b) => Number(b.note_likes || 0) - Number(a.note_likes || 0))
    .slice(0, limit);
}

function buildReport({ detailRows, summaryRows, stats, lexiconInfo }) {
  const lines = [];
  lines.push('# 小红书/A2 帖子正负向月度趋势（整体先看版）');
  lines.push('');
  lines.push('生成时间：2026-06-01');
  lines.push('');
  lines.push('## 口径');
  lines.push('');
  lines.push('- 四张表合并后按 `note_id` 去重到帖子级，不分战场看整体趋势。');
  lines.push('- 时间按帖子发布时间；显式 `note_publish_time` 优先，缺失时用 `note_id` 前 8 位 hex 推导发布时间。');
  lines.push('- 情感只看 `note_title + note_desc`，不混入评论区情绪。');
  lines.push('- 正向计入 positive；`负向/疑虑` 和 `混合` 计入 negative；其他计入中性/排除。');
  if (lexiconInfo) {
    lines.push(`- 情感词库：\`${lexiconInfo.file}\`（正向 ${lexiconInfo.positive_count} 条，负向 ${lexiconInfo.negative_count} 条，弱正向 ${lexiconInfo.weak_positive_count} 条）。`);
  }
  lines.push('');
  lines.push('## 月度总览');
  lines.push('');
  lines.push(markdownTable([
    'month',
    'total_posts',
    'positive_count',
    'negative_count',
    'neutral_or_excluded_count',
    'positive_rate_all_posts',
    'negative_rate_all_posts',
    'valid_sentiment_posts',
    'positive_rate_valid',
    'negative_rate_valid',
    'net_positive_score',
  ], summaryRows));
  lines.push('');
  lines.push('## 初步观察');
  lines.push('');
  const may = summaryRows.find((row) => row.month === '5月');
  const jan = summaryRows.find((row) => row.month === '1月');
  if (jan && may) {
    lines.push(`- 帖子量从 1 月 ${jan.total_posts} 篇增加到 5 月 ${may.total_posts} 篇，5 月样本显著放大。`);
    lines.push(`- 有效情感口径下，1 月净正向分为 ${jan.net_positive_score}，5 月为 ${may.net_positive_score}。`);
    lines.push(`- 全帖子口径下，5 月正向占比 ${may.positive_rate_all_posts}，负向/疑虑占比 ${may.negative_rate_all_posts}。`);
  }
  lines.push('- 该报告是整体先看版；如果某个月出现明显波动，下一步再按四大战场拆分。');
  lines.push('');
  lines.push('## 抽查样本');
  for (const month of ['2026-01', '2026-02', '2026-03', '2026-04', '2026-05']) {
    lines.push('');
    lines.push(`### ${monthLabel(month)}`);
    for (const [label, polarity] of [['正向', 'positive'], ['负向/疑虑', 'negative']]) {
      const examples = pickExamples(detailRows, month, polarity, 5);
      lines.push('');
      lines.push(`#### ${label}`);
      if (!examples.length) {
        lines.push('- 无');
      } else {
        for (const row of examples) {
          lines.push(`- ${row.note_title || row.note_desc.slice(0, 60)}（${row.sentiment}，来源：${row.source_labels}）`);
        }
      }
    }
  }
  lines.push('');
  lines.push('## 数据处理统计');
  lines.push('');
  lines.push(`- 输入评论行：${stats.input_rows}`);
  lines.push(`- 输出去重帖子：${detailRows.length}`);
  lines.push(`- 过滤非 2026 年 1-5 月行：${stats.out_of_month_posts}`);
  lines.push(`- 时间无法解析行：${stats.unparsed_time_posts}`);
  lines.push(`- 缺 note_id 行：${stats.missing_note_id_rows}`);
  return `${lines.join('\n')}\n`;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const outDir = args['out-dir'] || DEFAULT_OUT_DIR;
  const lexicon = configureLexicon(args.lexicon || DEFAULT_LEXICON);
  mkdirSync(outDir, { recursive: true });

  const { posts, stats } = collectPosts();
  const detailRows = posts
    .map((post) => {
      const classified = classifyPost(post.note_title, post.note_desc);
      return {
        ...post,
        sentiment: classified.sentiment,
        polarity: classified.polarity,
        primary_intent: classified.primary_intent || '',
        positive_tags: classified.positive_tags || '',
        risk_tags: classified.risk_tags || '',
        question_tags: classified.question_tags || '',
        ad_trade_tags: classified.ad_trade_tags || '',
      };
    })
    .sort((a, b) => a.month.localeCompare(b.month) || a.note_id.localeCompare(b.note_id));

  const summaryRows = buildSummaryRows(detailRows);
  const lexiconInfo = lexicon
    ? {
        file: lexicon.file,
        positive_count: lexicon.positiveRules.length,
        negative_count: lexicon.negativeRules.length,
        weak_positive_count: lexicon.weakPositiveRules.size,
      }
    : null;

  const detailFile = join(outDir, 'post_monthly_sentiment_detail.csv');
  const summaryFile = join(outDir, 'post_monthly_sentiment_overall_summary.csv');
  const reportFile = join(outDir, 'post_monthly_sentiment_overall_report.md');
  const metaFile = join(outDir, 'post_monthly_sentiment_summary.json');

  writeCsv(detailFile, detailRows, [
    'month',
    'month_label',
    'note_id',
    'note_url',
    'note_title',
    'note_desc',
    'note_tags',
    'keyword',
    'note_likes',
    'note_comments_count',
    'post_time',
    'time_source',
    'sentiment',
    'polarity',
    'primary_intent',
    'positive_tags',
    'risk_tags',
    'question_tags',
    'ad_trade_tags',
    'source_keys',
    'source_labels',
    'source_files',
  ]);
  writeCsv(summaryFile, summaryRows, [
    'month',
    'total_posts',
    'positive_count',
    'negative_count',
    'neutral_or_excluded_count',
    'positive_rate_all_posts',
    'negative_rate_all_posts',
    'valid_sentiment_posts',
    'positive_rate_valid',
    'negative_rate_valid',
    'net_positive_score',
  ]);
  writeFileSync(reportFile, buildReport({ detailRows, summaryRows, stats, lexiconInfo }), 'utf8');
  writeFileSync(metaFile, `${JSON.stringify({
    inputs: INPUTS.map((input) => ({ ...input, file: basename(input.file) })),
    output_files: [detailFile, summaryFile, reportFile],
    stats,
    detail_rows: detailRows.length,
    lexicon: lexiconInfo || 'builtin',
  }, null, 2)}\n`, 'utf8');

  console.log(JSON.stringify({
    detail_rows: detailRows.length,
    outputs: [detailFile, summaryFile, reportFile, metaFile],
    summary: summaryRows,
  }, null, 2));
}

main();
