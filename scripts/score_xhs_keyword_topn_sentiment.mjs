#!/usr/bin/env node

import { basename, join } from 'node:path';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import {
  classifyComment,
  configureLexicon,
  normalizeText,
  readCsv,
} from './analyze_xhs_comments.mjs';

const DEFAULT_INPUT = 'xhs_转奶争夺战场_top20x200_fast_comments.csv';
const DEFAULT_NOTE_CACHE = 'local_data/xhs_note_body_transfer_full/xhs_转奶争夺战场_top20x200_fast_comments.csv.note_detail_tags.jsonl';
const DEFAULT_LEXICON = '0601-a2评论-正负向词库.xlsx';
const DEFAULT_OUT_DIR = 'local_data/xhs_keyword_topn_sentiment_0601';
const DEFAULT_TOP_NS = [20, 50];

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

function readJsonl(file) {
  if (!file) return [];
  return readFileSync(file, 'utf8')
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function readExistingJsonl(files) {
  return files.filter(Boolean).filter((file) => existsSync(file)).flatMap((file) => readJsonl(file));
}

function keywordKey(row) {
  return `${row.keyword_rank || ''}\t${row.keyword || ''}`;
}

function commentWindowKey(row, topN) {
  const dedupe = row.comment_id
    ? `${row.note_id || ''}::${row.comment_id}`
    : `${row.note_id || ''}::text::${normalizeText(row.comment_text).replace(/\s+/g, '')}`;
  return `${topN}\t${keywordKey(row)}\t${dedupe}`;
}

function binaryPolarity(sentiment) {
  if (sentiment === '正向') return 'positive';
  if (sentiment === '负向/疑虑' || sentiment === '混合') return 'negative';
  return 'none';
}

function makeScoreBucket() {
  return {
    total: 0,
    positive: 0,
    negative: 0,
  };
}

function addPolarity(bucket, polarity) {
  bucket.total += 1;
  if (polarity === 'positive') bucket.positive += 1;
  if (polarity === 'negative') bucket.negative += 1;
}

function pct(count, total) {
  if (!total) return '0.0%';
  return `${((count / total) * 100).toFixed(1)}%`;
}

function netScore(bucket) {
  if (!bucket.total) return '0.0';
  return (((bucket.positive - bucket.negative) / bucket.total) * 100).toFixed(1);
}

function classifyText(text) {
  const cleanText = normalizeText(text);
  if (!cleanText) return 'none';
  const result = classifyComment({ clean_comment_text: cleanText });
  return binaryPolarity(result.sentiment);
}

function splitTags(value) {
  return String(value || '').split(';').filter(Boolean);
}

const NOTE_TOPIC_ONLY_RISK_RULES = new Set([
  '转奶',
  '换奶',
  '为什么',
  '怕',
  '急',
  '不好',
  '不喝',
  '高价',
  '贵',
  '雷',
  '坑',
]);

const NOTE_PAIN_INTRO_RISK_RULES = new Set([
  '便秘',
  '拉羊屎',
  '羊屎蛋',
  '拉肚子',
  '拉稀',
  '腹泻',
  '上火',
  '过敏',
  '湿疹',
  '红疹',
  '吐奶',
  '胀气',
  '奶瓣',
  '绿便',
  '不长肉',
  '不长体重',
  '不长高',
  '消化不了',
  '不适应',
  '哭闹',
  '睡不安稳',
  '夜醒',
  '发烧',
  '焦虑',
  '担心',
  '慌',
  '怕',
  '急',
  '不好',
]);

function hasTargetedNoteNegative(text) {
  const target = '(?:A2|a2|至初|紫白金|紫曜|这个A2|这个a2|这个奶粉|这款|这罐|喝它|喝这个)';
  const strongRisk = '(?:便秘|拉肚子|拉稀|腹泻|吐奶|胀气|过敏|湿疹|红疹|拒奶|不爱喝|不喝|不适应|难喝|不好喝|不好泡|难溶|冲不开|结块|挂壁|断货|断供|缺货|没货|买不到|召回|下架|停产|不敢喝|不放心|出问题|有问题|爆雷|暴雷|翻车|假货|踩雷)';
  return new RegExp(`${target}[^，。；;!?！？]{0,48}${strongRisk}`, 'i').test(text)
    || new RegExp(`${strongRisk}[^，。；;!?！？]{0,36}${target}`, 'i').test(text)
    || /(?:至初|A2|a2|紫白金)[^，。；;!?！？]{0,24}(?:转|换)(?:皇家|爱他美|启赋|飞鹤|合生元|澳爱|蓝臻)/i.test(text)
    || /(?:A2|a2|至初|紫白金)[^，。；;!?！？]{0,24}(?:召回|断供|断货|没货|买不到|出问题|爆雷|暴雷)/i.test(text);
}

function hasNoteSolutionFrame(text) {
  const target = '(?:A2|a2|至初|紫白金|紫曜)';
  const positiveOutcome = '(?:好吸收|好消化|吸收好|消化好|丝滑|顺利|成功|好多了|好点|改善|正常|规律|通畅|长肉|长高|体重|睡得香|省心|放心|安心|接受|适应|爱喝|喜欢喝|挺好|很好|不错|推荐|营养)';
  return new RegExp(`${target}.{0,96}${positiveOutcome}`, 'i').test(text)
    || new RegExp(`(?:选择|选了|换了|转成|喝了|安排|入手|试了|推荐|可以看看).{0,24}${target}.{0,96}${positiveOutcome}`, 'i').test(text)
    || new RegExp(`(?:痛点|焦虑|不长肉|吐奶|胀气|奶瓣|便秘|消化不好|吸收不好|闹肚).{0,80}${target}.{0,120}${positiveOutcome}`, 'i').test(text)
    || /(?:破局|逆袭|解决|救场|下车|成功|丝滑上岸|顺利上岸)/.test(text);
}

function isNoteQuestionOnly(text) {
  if (hasTargetedNoteNegative(text)) return false;
  return /(?:吗|嘛|么|\?|？|怎么|如何|哪个好|选哪|区别|为什么|求推荐|求问|有没有|要不要|能不能|可不可以|该不该|适合吗)/.test(text);
}

function classifyNoteText(text) {
  const cleanText = normalizeText(text);
  if (!cleanText) return 'none';
  const result = classifyComment({ clean_comment_text: cleanText });
  const positiveTags = splitTags(result.positive_tags);
  let riskTags = splitTags(result.risk_tags);

  if (result.sentiment === '广告交易') return 'none';
  if (result.sentiment === '正向') return 'positive';
  if (result.sentiment === '中性' || result.sentiment === '中性咨询') return 'none';

  const targetedNegative = hasTargetedNoteNegative(cleanText);
  if (!targetedNegative) {
    riskTags = riskTags.filter((tag) => !NOTE_TOPIC_ONLY_RISK_RULES.has(tag));
    // 帖子正文经常先写宝宝痛点，再把 A2/至初作为解决方案；这类不应因为痛点词直接算 A2 负面。
    if (hasNoteSolutionFrame(cleanText) && positiveTags.length) {
      riskTags = riskTags.filter((tag) => !NOTE_PAIN_INTRO_RISK_RULES.has(tag));
    }
    if (isNoteQuestionOnly(cleanText)) {
      riskTags = riskTags.filter((tag) => !NOTE_TOPIC_ONLY_RISK_RULES.has(tag) && !NOTE_PAIN_INTRO_RISK_RULES.has(tag));
    }
  }

  if (riskTags.length) return 'negative';
  if (positiveTags.length) return 'positive';
  return 'none';
}

function buildNoteCache(notes) {
  const cache = new Map();
  for (const note of notes) {
    const key = `${note.keyword_rank || ''}\t${note.keyword || ''}\t${note.search_rank || ''}\t${note.note_id || ''}`;
    const text = [note.note_title || '', note.note_desc || ''].filter(Boolean).join(' ');
    if (text.trim()) cache.set(key, text);
  }
  return cache;
}

function collectKeywordRows(rows, stateRows) {
  const byKeyword = new Map();
  for (const row of [...stateRows, ...rows]) {
    const key = keywordKey(row);
    if (!byKeyword.has(key)) {
      byKeyword.set(key, {
        keyword_rank: Number(row.keyword_rank || 0),
        keyword: row.keyword || '',
        battle_category: row.battle_category || '',
      });
    }
  }
  return [...byKeyword.values()].sort((a, b) => a.keyword_rank - b.keyword_rank || a.keyword.localeCompare(b.keyword, 'zh-CN'));
}

function collectRankedNotes(rawRows, stateRows) {
  const byKeyword = new Map();
  for (const row of [...stateRows, ...rawRows]) {
    const searchRank = Number(row.search_rank || 0);
    const noteId = row.note_id || row.source_note_id || '';
    if (!row.keyword || !noteId || !searchRank) continue;
    const key = keywordKey(row);
    if (!byKeyword.has(key)) byKeyword.set(key, new Map());
    const notes = byKeyword.get(key);
    const noteKey = noteId;
    const current = notes.get(noteKey);
    const next = {
      keyword_rank: row.keyword_rank || '',
      keyword: row.keyword || '',
      battle_category: row.battle_category || '',
      search_rank: searchRank,
      note_id: noteId,
      note_title: row.note_title || '',
      note_desc: row.note_desc || '',
    };
    if (!current || searchRank < current.search_rank || (searchRank === current.search_rank && next.note_title.length > current.note_title.length)) {
      notes.set(noteKey, next);
    }
  }

  const ranked = new Map();
  for (const [key, notes] of byKeyword.entries()) {
    ranked.set(key, [...notes.values()].sort((a, b) => a.search_rank - b.search_rank || a.note_id.localeCompare(b.note_id)));
  }
  return ranked;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const inputFile = args.input || DEFAULT_INPUT;
  const noteCacheFile = args['note-cache'] || DEFAULT_NOTE_CACHE;
  const stateFiles = args['state-files']
    ? String(args['state-files']).split(',').map((value) => value.trim()).filter(Boolean)
    : [`${inputFile}.state.jsonl`, inputFile.replace(/\.csv$/i, '.resume_after_recharge.state.jsonl')];
  const lexiconFile = args.lexicon || DEFAULT_LEXICON;
  const outDir = args['out-dir'] || DEFAULT_OUT_DIR;
  const topNs = (args['top-ns'] ? String(args['top-ns']).split(',').map((value) => Number(value.trim())) : DEFAULT_TOP_NS)
    .filter((value) => Number.isFinite(value) && value > 0);

  mkdirSync(outDir, { recursive: true });
  const lexicon = configureLexicon(lexiconFile);
  const rawRows = readCsv(inputFile);
  const stateRows = readExistingJsonl(stateFiles);
  const noteCache = buildNoteCache(readJsonl(noteCacheFile));
  const keywords = collectKeywordRows(rawRows, stateRows);
  const rankedNotesByKeyword = collectRankedNotes(rawRows, stateRows);

  const commentsByWindow = new Map();
  const notesByWindow = new Map();
  const selectedNoteIds = new Map();

  for (const keyword of keywords) {
    const key = `${keyword.keyword_rank || ''}\t${keyword.keyword || ''}`;
    const rankedNotes = rankedNotesByKeyword.get(key) || [];
    for (const topN of topNs) {
      const selected = rankedNotes.slice(0, topN);
      const selectedSet = new Set(selected.map((note) => note.note_id));
      selectedNoteIds.set(`${topN}\t${key}`, selectedSet);
      for (const note of selected) {
        const cacheKey = `${note.keyword_rank || ''}\t${note.keyword || ''}\t${note.search_rank || ''}\t${note.note_id || ''}`;
        const noteText = noteCache.get(cacheKey) || [note.note_title || '', note.note_desc || ''].filter(Boolean).join(' ');
        notesByWindow.set(`${topN}\t${key}\t${note.note_id}`, {
          topN,
          keywordKey: key,
          polarity: classifyNoteText(noteText),
        });
      }
    }
  }

  for (const row of rawRows) {
    const searchRank = Number(row.search_rank || 0);
    if (!searchRank || !row.keyword || !row.note_id) continue;
    for (const topN of topNs) {
      const selectedSet = selectedNoteIds.get(`${topN}\t${keywordKey(row)}`);
      if (!selectedSet?.has(row.note_id)) continue;

      const commentKey = commentWindowKey(row, topN);
      if (!commentsByWindow.has(commentKey) && normalizeText(row.comment_text)) {
        commentsByWindow.set(commentKey, {
          topN,
          keywordKey: keywordKey(row),
          polarity: classifyText(row.comment_text),
        });
      }
    }
  }

  const resultRows = [];
  for (const keyword of keywords) {
    const key = `${keyword.keyword_rank || ''}\t${keyword.keyword || ''}`;
    for (const topN of topNs) {
      const commentBucket = makeScoreBucket();
      const noteBucket = makeScoreBucket();

      for (const item of commentsByWindow.values()) {
        if (item.topN === topN && item.keywordKey === key) addPolarity(commentBucket, item.polarity);
      }
      for (const item of notesByWindow.values()) {
        if (item.topN === topN && item.keywordKey === key) addPolarity(noteBucket, item.polarity);
      }

      const combinedBucket = {
        total: commentBucket.total + noteBucket.total,
        positive: commentBucket.positive + noteBucket.positive,
        negative: commentBucket.negative + noteBucket.negative,
      };

      resultRows.push({
        battle_category: keyword.battle_category,
        keyword_rank: keyword.keyword_rank,
        keyword: keyword.keyword,
        top_n: topN,
        note_total: noteBucket.total,
        note_positive: noteBucket.positive,
        note_negative: noteBucket.negative,
        note_positive_score: pct(noteBucket.positive, noteBucket.total),
        note_negative_score: pct(noteBucket.negative, noteBucket.total),
        note_net_score: netScore(noteBucket),
        comment_total: commentBucket.total,
        comment_positive: commentBucket.positive,
        comment_negative: commentBucket.negative,
        comment_positive_score: pct(commentBucket.positive, commentBucket.total),
        comment_negative_score: pct(commentBucket.negative, commentBucket.total),
        comment_net_score: netScore(commentBucket),
        combined_total: combinedBucket.total,
        combined_positive: combinedBucket.positive,
        combined_negative: combinedBucket.negative,
        combined_positive_score: pct(combinedBucket.positive, combinedBucket.total),
        combined_negative_score: pct(combinedBucket.negative, combinedBucket.total),
        combined_net_score: netScore(combinedBucket),
      });
    }
  }

  const headers = [
    'battle_category',
    'keyword_rank',
    'keyword',
    'top_n',
    'note_total',
    'note_positive',
    'note_negative',
    'note_positive_score',
    'note_negative_score',
    'note_net_score',
    'comment_total',
    'comment_positive',
    'comment_negative',
    'comment_positive_score',
    'comment_negative_score',
    'comment_net_score',
    'combined_total',
    'combined_positive',
    'combined_negative',
    'combined_positive_score',
    'combined_negative_score',
    'combined_net_score',
  ];
  const scoreFile = join(outDir, 'keyword_topn_sentiment_scores.csv');
  writeCsv(scoreFile, resultRows, headers);

  const metaFile = join(outDir, 'keyword_topn_sentiment_scores.meta.json');
  writeFileSync(metaFile, `${JSON.stringify({
    input: basename(inputFile),
    state_files: stateFiles.map((file) => basename(file)),
    note_cache: basename(noteCacheFile),
    lexicon: lexicon
      ? {
          file: lexicon.file,
          positive_count: lexicon.positiveRules.length,
          negative_count: lexicon.negativeRules.length,
          weak_positive_count: lexicon.weakPositiveRules.size,
        }
      : null,
    top_ns: topNs,
    rows: resultRows.length,
    note_sentiment_mode: 'tuned_note_context',
    score_formula: 'net_score = (positive_count - negative_count) / total_count * 100; combined_total = note_total + comment_total',
  }, null, 2)}\n`, 'utf8');

  console.log(JSON.stringify({
    rows: resultRows.length,
    outputs: [scoreFile, metaFile],
    score_formula: 'net_score = (positive_count - negative_count) / total_count * 100',
  }, null, 2));
}

main();
