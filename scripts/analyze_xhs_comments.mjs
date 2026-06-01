#!/usr/bin/env node

import { basename, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

const DEFAULT_COMMENTS_FILE = 'xhs_品类信任教育战场_top20x200_comments.csv';
const DEFAULT_DETAIL_FILE = 'xhs_品类信任教育战场_top20x200_detail_comments.csv';
const DEFAULT_OUT_DIR = 'local_data/xhs_comment_analysis_sample';

const SENTIMENTS = ['正向', '负向/疑虑', '中性咨询', '混合', '广告交易', '中性'];

const POSITIVE_RULES = [
  '好吸收',
  '好消化',
  '亲和好吸收',
  '好喝',
  '丝滑',
  '浓郁',
  '省心',
  '稳定',
  '能喝',
  '可以喝',
  '继续喝',
  '一直喝',
  '还在喝',
  '正常喝',
  '放心喝',
  '安心喝',
  '没换',
  '不打算换',
  '不换',
  '相信',
  '信官方',
  '以官方消息为准',
  '不传谣不信谣',
  '理性',
  '不恐慌',
  '不转了',
  '换回a2',
  '喝回来',
  '爱喝',
  '宝宝爱喝',
  '不便秘',
  '没有便秘',
  '没有便秘过',
  '没便秘',
  '没便秘过',
  '不会便秘',
  '不上火',
  '没有上火',
  '肚肚舒服',
  '不闹肚',
  '好多了',
  '好点',
  '改善',
  '通畅',
  '状态很好',
  '状态稳定',
  '长得好',
  '体重涨',
  '身高涨',
  '黄金大便',
  '没召回',
  '没有召回',
  '未召回',
  '不是召回',
  '缺货不是召回',
  '不涉及',
  '不影响',
  '批次没问题',
  '澳洲没事',
  '澳版没问题',
  '正常售卖',
  '依旧在卖',
  '依然在卖',
  '一切照常',
  '没有下架',
  '官方声明',
  '辟谣',
  '别信',
  '不用焦虑',
  '不要焦虑',
  '别焦虑',
  '别慌',
  '没必要过度焦虑',
  '没问题',
  '没有问题',
  '没事',
  '一切正常',
  '没有啥不适',
  '没不良反应',
  '不怕拉肚子',
  '不会拉肚子',
  '不拉肚子',
  '没有拉肚子',
  '没拉肚子',
  '便便正常',
  '转奶顺利',
  '睡得香',
  '长肉',
  '长势不错',
  '又壮又健康',
  '抵抗力',
  '免疫力',
  '放心',
  '安心',
  '值得',
  '不错',
  '推荐',
  '好奶粉',
  '消化好',
  '吸收好',
  '好溶解',
  '很好融',
  '很好冲泡',
  '不挂壁',
  '不结块',
  '营养',
  '适应',
  '适应的很好',
  '合适',
  '喜欢喝',
  '睡得好',
  '奶源干净',
  '从出生喝到现在',
  '有货',
  '都有货',
  '买到了',
  '买得到',
  '买的到',
  '到货',
  '补货',
  '来货',
  '上货',
  '下单',
  '已下单',
  '抢到',
  '续上',
  '有卖',
  '山姆有',
  '京东有',
  '淘宝有',
  '母婴店有',
  '价格真的很漂亮',
];

const NEGATIVE_RULES = [
  '便秘',
  '拉羊屎',
  '羊屎蛋',
  '拉不出来',
  '拉屎干',
  '大便干',
  '肛裂',
  '拉肚子',
  '拉稀',
  '水样便',
  '血丝',
  '腹泻',
  '上火',
  '过敏',
  '湿疹',
  '红疹',
  '不适应',
  '喝不惯',
  '不爱喝',
  '拒奶',
  '吐奶',
  '胀气',
  '哭闹',
  '睡不安稳',
  '夜醒',
  '绿便',
  '奶瓣',
  '消化不了',
  '不长肉',
  '不长体重',
  '不长高',
  '踩雷',
  '踩坑',
  '后悔',
  '智商税',
  '太贵',
  '贵',
  '买不到',
  '断货',
  '缺货',
  '抢不到',
  '不好买',
  '下线',
  '停产',
  '假',
  '不放心',
  '不安心',
  '不信任',
  '不信',
  '不敢喝',
  '不敢吃',
  '不敢用',
  '不敢继续',
  '不能喝',
  '不能吃',
  '不敢买',
  '心慌',
  '焦虑',
  '担心',
  '害怕',
  '后怕',
  '恐慌',
  '冒险',
  '风险',
  '健康第一',
  '娃的健康',
  '孩子冒险',
  '可不敢',
  '太吓人',
  '睡不着觉',
  '很难放心',
  '不敢拿孩子',
  '不推荐',
  '别买',
  '坑',
  '难喝',
  '不好喝',
  '寡淡',
  '腥味',
  '不香',
  '发涩',
  '慎点',
  '费钱',
  '召回',
  '悄悄召回',
  '下架',
  '厂家收回',
  '退回',
  '串码',
  '溯源码',
  '求证',
  '该信谁',
  '不知道该信谁',
  '真的吗',
  '真的假的',
  '什么情况',
  '有没有问题',
  '有问题',
  '出问题',
  '爆雷',
  '暴雷',
  '存疑',
  '不清楚',
  '不确定',
  '不知道啥情况',
  '怎么回事',
  '为啥',
  '怎么办',
  '还能喝吗',
  '还能吃吗',
  '可以喝吗',
  '可以吃吗',
  '要继续喝吗',
  '不打算喝',
  '不喝了',
  '退货',
  '退掉',
  '退款',
  '退钱',
  '没有找到合适',
  '不知道换什么',
  '换什么牌子',
  '结果碰到这事',
  '出事',
  '呕吐',
  '呕吐毒素',
  '上吐下泻',
  '嘴角老是红',
  '不良反应',
  '肠胃受不了',
  '发烧',
  '又吐又拉',
  '不习惯',
  '不检测',
  '没有检测报告',
  '没有这个检测报告',
  '态度差',
  '不处理',
  '投诉',
  '维权',
  '接受不了',
  '头疼',
  '无语',
  '真服了',
  '翻车',
  '避雷',
  '负面',
  '太难了',
  '异物',
  '黑色',
  '挂壁',
  '不好泡',
  '难溶',
  '冲不开',
  '结块',
];

const QUESTION_RULES = [
  '为什么',
  '想问',
  '问问',
  '吗',
  '？',
  '?',
  '怎么样',
  '怎么',
  '咋办',
  '怎么选',
  '值得买吗',
  '有没有',
  '会不会',
  '可以喝',
  '适合',
  '哪个好',
  '哪个',
  '哪款',
  '选哪个',
  '区别',
  '几段',
  '哪里买',
  '怎么买',
  '多少钱',
  '求推荐',
  '求问',
  '求',
  '求助',
  '蹲',
  '在线等',
  '该不该',
  '要不要',
  '能不能',
  '纠结',
];

const AD_TRADE_RULES = [
  '回收',
  '收一段',
  '收二段',
  '收三段',
  '出奶粉',
  '转让',
  '代购',
  '未拆封',
  '欢迎打扰',
  '私信',
  '私我',
  '私聊',
  '加我',
  '微信',
  'VX',
  'vx',
  'v我',
  '领券',
  '券',
  '补贴',
  '奶卡',
  '链接',
  '货源',
  '便宜出',
  '求购',
];

const TOPIC_RULES = [
  ['吸收/肠胃', ['吸收', '消化', '肠胃', '肚', '闹肚', '便便', '便秘', '羊屎蛋', '拉肚子', '拉稀', '腹泻', '奶瓣', '胀气', '上火']],
  ['宝宝接受度', ['爱喝', '不爱喝', '拒奶', '口味', '喜欢喝', '喝得', '喝了']],
  ['转奶经验', ['转奶', '换奶', '过渡', '从.*转', '转回']],
  ['A2蛋白/配方', ['A2', 'a2', 'A2蛋白', 'a2蛋白', 'β', '酪蛋白', '配方', '蛋白', '乳铁', 'DHA', 'OPO', '益生元']],
  ['营养成长', ['营养', '长肉', '长高', '抵抗力', '免疫', '发育', '体重']],
  ['段数/月龄', ['一段', '二段', '三段', '1段', '2段', '3段', '月龄', '月子', '十月龄', '一岁', '出生']],
  ['测评推荐', ['推荐', '测评', '怎么选', '怎么样', '值得买吗', '选奶', '哪个好']],
  ['奶源/口味', ['奶源', '味道', '口味', '偏甜', '甜', '腥', '奶味']],
  ['喂养方式', ['母乳', '亲喂', '混合喂养', '纯奶粉', '喂养']],
  ['购买渠道/价格', ['价格', '贵', '活动', '旗舰店', '渠道', '真假', '正品', '购买', '买', '链接', '优惠', '券', '补贴', '囤', '断货', '缺货', '买不到', '有货', '补货', '到货', '下线', '下架', '停产']],
  ['竞品对比', ['蓝臻', '飞鹤', '君乐宝', '至臻', '皇家美素佳儿', '澳优', '佳贝艾特', '启赋', '爱他美', '海普诺凯', '贝因美', '雅培', '雀巢', '合生元', '牛栏', '美赞臣', '源初', '爷爷的农场']],
  ['安全信任', ['安心', '放心', '不放心', '担心', '焦虑', '召回', '声明', '公告', '辟谣', '真假', '正品', '信任', '国产', '进口', '溯源', '安全', '检测报告', '批次']],
  ['售卖/回收', ['回收', '出奶粉', '收一段', '收二段', '收三段', '未拆封', '欢迎打扰', '补贴', '奶卡']],
];

const WEAK_POSITIVE_RULES = new Set(['推荐', '值得', '合适', '适应']);

let activePositiveRules = POSITIVE_RULES;
let activeNegativeRules = NEGATIVE_RULES;
let activeWeakPositiveRules = WEAK_POSITIVE_RULES;

const PHRASES = [
  'a2至初',
  '至初',
  'a2紫白金',
  '蓝臻',
  '飞鹤',
  '源初',
  '皇家美素佳儿',
  '君乐宝',
  '爷爷的农场',
  '爱他美',
  '启赋',
  '好吸收',
  '好消化',
  '亲和好吸收',
  '宝宝爱喝',
  '爱喝',
  '不爱喝',
  '好奶粉',
  '不错',
  '值得',
  '推荐',
  '放心',
  '安心',
  '继续喝',
  '正常喝',
  '放心喝',
  '不换',
  '相信',
  '没召回',
  '不是召回',
  '不影响',
  '不涉及',
  '批次没问题',
  '官方声明',
  '辟谣',
  '别慌',
  '不用焦虑',
  '没问题',
  '没有问题',
  '营养',
  '长肉',
  '长高',
  '抵抗力',
  '免疫力',
  '睡得香',
  '省心',
  '稳定',
  '肚肚舒服',
  '不闹肚',
  '好多了',
  '好点',
  '改善',
  '通畅',
  '状态很好',
  '黄金大便',
  '长得好',
  '体重涨',
  '身高涨',
  '不怕拉肚子',
  '不会拉肚子',
  '便便正常',
  '不便秘',
  '不会便秘',
  '不上火',
  '转奶',
  '换奶',
  '转奶顺利',
  '一段',
  '二段',
  '三段',
  '价格',
  '太贵',
  '断货',
  '下线',
  '停产',
  '缺货',
  '买不到',
  '有货',
  '到货',
  '补货',
  '买到了',
  '真假',
  '正品',
  '渠道',
  '旗舰店',
  '链接',
  '回收',
  '收一段',
  '未拆封',
  '补贴',
  '奶卡',
  '便秘',
  '拉羊屎',
  '羊屎蛋',
  '拉不出来',
  '拉屎干',
  '大便干',
  '肛裂',
  '拉肚子',
  '拉稀',
  '水样便',
  '血丝',
  '上火',
  '过敏',
  '湿疹',
  '红疹',
  '吐奶',
  '胀气',
  '奶瓣',
  '绿便',
  '腹泻',
  '踩雷',
  '踩坑',
  '后悔',
  '智商税',
  '召回',
  '不放心',
  '不敢喝',
  '焦虑',
  '担心',
  '害怕',
  '投诉',
  '维权',
  '翻车',
  '避雷',
  '暴雷',
  '出事',
  '异物',
  '挂壁',
  '不挂壁',
  '难喝',
  '不好喝',
  '喝不惯',
  '不好泡',
  '难溶',
  '冲不开',
  '结块',
  '不结块',
  '好溶解',
  '很好融',
  '很好冲泡',
  '选奶',
  '怎么选',
  '该不该',
  '要不要',
  '咋办',
  '怎么样',
  '值得买吗',
  '哪个好',
  '求推荐',
  '求问',
  '吸收',
  '消化',
  '肠胃',
  '配方',
  'A2蛋白',
  'a2蛋白',
  '蛋白',
  '奶源',
  '母乳',
  '小分子',
  '水解',
  '乳铁蛋白',
  'DHA',
  'OPO',
];

const COLOR_PALETTE = ['#264653', '#2a9d8f', '#e76f51', '#457b9d', '#8d5a97', '#bc6c25', '#5a7d2b'];

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

function parseCsv(text) {
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  const rows = [];
  let row = [];
  let field = '';
  let inQuotes = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];
    if (char === '"') {
      if (inQuotes && next === '"') {
        field += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === ',' && !inQuotes) {
      row.push(field);
      field = '';
    } else if ((char === '\n' || char === '\r') && !inQuotes) {
      if (char === '\r' && next === '\n') i += 1;
      row.push(field);
      if (row.some((value) => value !== '')) rows.push(row);
      row = [];
      field = '';
    } else {
      field += char;
    }
  }
  if (field || row.length) {
    row.push(field);
    if (row.some((value) => value !== '')) rows.push(row);
  }
  return rows;
}

function readCsv(file) {
  const rows = parseCsv(readFileSync(file, 'utf8'));
  const headers = rows[0] || [];
  return rows.slice(1).map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index] || ''])));
}

function normalizePolarity(value) {
  const text = String(value || '').trim().toLowerCase();
  if (['positive', 'pos', '正向', '正面'].includes(text)) return 'positive';
  if (['negative', 'neg', '负向', '负面'].includes(text)) return 'negative';
  return '';
}

function normalizeWeakPositive(value) {
  const text = String(value || '').trim().toLowerCase();
  return ['yes', 'y', 'true', '1', '是'].includes(text);
}

function collectLexiconRows(rows, source) {
  const items = [];
  for (const row of rows) {
    const polarity = normalizePolarity(row.polarity || row['正负向'] || row.sentiment || row.type || row[0]);
    const term = String(row.term || row['词'] || row.keyword || row.word || row[1] || '').trim();
    if (!polarity || !term || term === 'term') continue;
    items.push({
      polarity,
      term,
      weak_positive: normalizeWeakPositive(row.weak_positive || row['弱正向'] || row.weak || row[2]),
      source,
    });
  }
  return items;
}

function readLexiconCsv(file) {
  const rawRows = parseCsv(readFileSync(file, 'utf8'));
  const headers = rawRows[0] || [];
  const hasHeader = headers.some((header) => ['polarity', 'term', 'weak_positive'].includes(String(header || '').trim()));
  const rows = hasHeader
    ? rawRows.slice(1).map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index] || ''])))
    : rawRows.map((row) => Object.fromEntries(row.map((value, index) => [index, value || ''])));
  return collectLexiconRows(rows, file);
}

function readLexiconXlsx(file) {
  const code = `
import json
import sys
from openpyxl import load_workbook

workbook = load_workbook(sys.argv[1], data_only=True)
rows = []
for sheet in workbook.worksheets:
    for row in sheet.iter_rows(values_only=True):
        values = ["" if value is None else str(value).strip() for value in row]
        if not any(values):
            continue
        rows.append({
            "polarity": values[0] if len(values) > 0 else "",
            "term": values[1] if len(values) > 1 else "",
            "weak_positive": values[2] if len(values) > 2 else "",
        })
print(json.dumps(rows, ensure_ascii=False))
`;
  // xlsx 解析交给仓库既有 Python/openpyxl 环境，避免为一个离线词库文件新增 Node 依赖。
  const result = spawnSync('python3', ['-c', code, file], { encoding: 'utf8' });
  if (result.status !== 0) {
    throw new Error(`Failed to read xlsx lexicon: ${result.stderr || result.stdout}`);
  }
  return collectLexiconRows(JSON.parse(result.stdout), file);
}

function loadLexicon(file) {
  if (!file) return null;
  const lower = file.toLowerCase();
  const items = lower.endsWith('.xlsx') ? readLexiconXlsx(file) : readLexiconCsv(file);
  const positiveRules = uniq(items.filter((item) => item.polarity === 'positive').map((item) => item.term));
  const negativeRules = uniq(items.filter((item) => item.polarity === 'negative').map((item) => item.term));
  const weakPositiveRules = new Set(items
    .filter((item) => item.polarity === 'positive' && item.weak_positive)
    .map((item) => item.term));
  if (!positiveRules.length || !negativeRules.length) {
    throw new Error(`Lexicon must include positive and negative terms: ${file}`);
  }
  return {
    file,
    positiveRules,
    negativeRules,
    weakPositiveRules,
  };
}

function configureLexicon(file) {
  const lexicon = loadLexicon(file);
  if (!lexicon) return null;
  activePositiveRules = lexicon.positiveRules;
  activeNegativeRules = lexicon.negativeRules;
  activeWeakPositiveRules = lexicon.weakPositiveRules;
  return lexicon;
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

function normalizeText(text) {
  return String(text || '')
    .replace(/\[搜索高亮\]/g, '')
    .replace(/\[[^\]]{1,16}R?\]/g, '')
    .replace(/#/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function dedupeText(text) {
  return normalizeText(text).replace(/\s+/g, '');
}

function parseLikeCount(value) {
  const text = String(value || '').trim().toLowerCase();
  if (!text) return 0;
  const number = Number.parseFloat(text.replace(/[^\d.]/g, ''));
  if (!Number.isFinite(number)) return 0;
  if (text.includes('w') || text.includes('万')) return Math.round(number * 10000);
  return Math.round(number);
}

function stableHash(text) {
  let hash = 2166136261;
  for (const char of String(text)) {
    hash ^= char.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function uniq(values) {
  return [...new Set(values.filter(Boolean))];
}

function mergeCommentRows(inputGroups) {
  const merged = new Map();
  for (const group of inputGroups) {
    for (const row of group.rows) {
      const cleanText = normalizeText(row.comment_text);
      if (!row.note_id || !cleanText) continue;
      // 这里用 note_id + comment_id 做主去重；没有 comment_id 时才退回到正文，避免跨文章同文案误合并。
      const dedupeKey = row.comment_id
        ? `${row.note_id}::${row.comment_id}`
        : `${row.note_id}::text::${dedupeText(row.comment_text)}`;
      const current = merged.get(dedupeKey);
      if (!current) {
        merged.set(dedupeKey, {
          dedupe_key: dedupeKey,
          duplicate_count: 1,
          source_files: [group.source],
          keywords: uniq([row.keyword]),
          search_ranks: uniq([row.search_rank]),
          keyword_ranks: uniq([row.keyword_rank]),
          note_id: row.note_id,
          note_title: row.note_title || '',
          note_author_name: row.note_author_name || '',
          comment_id: row.comment_id || '',
          comment_text: row.comment_text || '',
          clean_comment_text: cleanText,
          comment_likes: parseLikeCount(row.comment_likes),
          comment_time: row.comment_time || '',
          comment_user_name: row.comment_user_name || '',
        });
        continue;
      }
      current.duplicate_count += 1;
      current.source_files = uniq([...current.source_files, group.source]);
      current.keywords = uniq([...current.keywords, row.keyword]);
      current.search_ranks = uniq([...current.search_ranks, row.search_rank]);
      current.keyword_ranks = uniq([...current.keyword_ranks, row.keyword_rank]);
      current.comment_likes = Math.max(current.comment_likes, parseLikeCount(row.comment_likes));
      if (cleanText.length > current.clean_comment_text.length) {
        current.comment_text = row.comment_text || '';
        current.clean_comment_text = cleanText;
      }
      if (!current.note_title && row.note_title) current.note_title = row.note_title;
      if (!current.note_author_name && row.note_author_name) current.note_author_name = row.note_author_name;
      if (!current.comment_user_name && row.comment_user_name) current.comment_user_name = row.comment_user_name;
    }
  }
  return [...merged.values()].sort((a, b) => a.dedupe_key.localeCompare(b.dedupe_key));
}

function ruleToRegex(rule) {
  if (rule.includes('.*')) return new RegExp(rule, 'i');
  return new RegExp(rule.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i');
}

function findMatches(text, rules) {
  return rules.filter((rule) => ruleToRegex(rule).test(text));
}

const TARGET_BRAND_RE = /(?:A2|a2|至初|紫白金|紫曜|a2紫|A2紫)/i;
const COMPETITOR_BRAND_RE = /(?:悦白|皇家|皇家3段|皇家美素|美素|美素力|卓睿|派星|德爱|爱他美|领熠|至熠|飞鹤|合生元|澳爱|澳优|佳贝艾特|启赋|蕴初|能恩|雀巢|蓝臻|君乐宝|完达山|金领冠|珍护|源初|贝拉米|山羊奶|羊奶|港版皇家|旧奶粉|老奶粉|之前喝|原来喝|上个奶粉)/i;
const RISK_WORD_RE = /(?:便秘|拉羊屎|羊屎蛋|拉不出来|拉屎干|大便干|肛裂|拉肚子|拉稀|水样便|血丝|腹泻|上火|过敏|湿疹|红疹|不适应|喝不惯|不爱喝|拒奶|吐奶|胀气|哭闹|睡不安稳|夜醒|绿便|奶瓣|消化不了|不长肉|不长体重|不长高|不好买|断货|缺货|抢不到|买不到)/i;

function hasNearbyTargetRisk(text, riskRule) {
  const escapedRule = riskRule.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const target = '(?:A2|a2|至初|紫白金|紫曜|a2紫|A2紫|这个A2|这个a2|这个奶粉|这款)';
  return new RegExp(`${target}.{0,32}${escapedRule}|${escapedRule}.{0,32}${target}`, 'i').test(text);
}

function isCompetitorOnlyRiskContext(text, riskRule) {
  if (hasNearbyTargetRisk(text, riskRule)) return false;
  const escapedRule = riskRule.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const competitorNearRisk = new RegExp(`${COMPETITOR_BRAND_RE.source}.{0,32}${escapedRule}|${escapedRule}.{0,32}${COMPETITOR_BRAND_RE.source}`, 'i').test(text);
  if (!competitorNearRisk) return false;
  return true;
}

function isSwitchingToTargetFromCompetitorRisk(text) {
  // 竞品或旧奶粉先出问题、再考虑转 A2/至初，是换奶需求，不应算作 A2 品牌负向。
  return new RegExp(`${COMPETITOR_BRAND_RE.source}[^，。；;!?！？]{0,32}${RISK_WORD_RE.source}[^，。；;!?！？]{0,36}(?:想|准备|打算|考虑|要|已经|后来)?(?:换|转|喝回|换成|转成|转到)[^，。；;!?！？]{0,20}${TARGET_BRAND_RE.source}`, 'i').test(text)
    || new RegExp(`${RISK_WORD_RE.source}[^，。；;!?！？]{0,24}${COMPETITOR_BRAND_RE.source}[^，。；;!?！？]{0,36}(?:想|准备|打算|考虑|要|已经|后来)?(?:换|转|喝回|换成|转成|转到)[^，。；;!?！？]{0,20}${TARGET_BRAND_RE.source}`, 'i').test(text)
    || new RegExp(`${COMPETITOR_BRAND_RE.source}[^，。；;!?！？]{0,32}老是[^，。；;!?！？]{0,12}${RISK_WORD_RE.source}[^，。；;!?！？]{0,24}(?:想|准备|打算|考虑|要)?(?:换|转)[^，。；;!?！？]{0,20}${TARGET_BRAND_RE.source}`, 'i').test(text)
    || new RegExp(`${COMPETITOR_BRAND_RE.source}[^，。；;!?！？]{0,24}(?:想|准备|打算|考虑|要)?(?:换|转)[^，。；;!?！？]{0,20}${TARGET_BRAND_RE.source}.{0,40}${COMPETITOR_BRAND_RE.source}[^，。；;!?！？]{0,16}${RISK_WORD_RE.source}`, 'i').test(text);
}

function isAntiAnxietyContext(text) {
  const explicitDistrust = /(?:还是|仍然|依然|实在|真的?|很|太|有点|不太|无法|很难)?不放心|不敢(?:喝|吃|用|继续|买)|担心死|焦虑|害怕|心慌|睡不着/.test(text)
    && !/(?:不用|不要|别|没必要).{0,8}(?:担心|焦虑|恐慌|慌)|(?:有什么|有啥|没什么).{0,6}好担心|担心什么/.test(text);
  if (explicitDistrust) return false;
  return /(?:不用|不要|别|没必要).{0,8}(?:焦虑|担心|恐慌|慌)/.test(text)
    || /(?:别慌|放心喝|放心买|安心喝|没问题|没有问题|没事|一切正常|不影响|不涉及|批次没问题|以官方消息为准|不传谣不信谣|官方声明|发声明|公告说|辟谣|正常售卖|正常喝|澳版没问题|澳洲没事|只是美版|没召回|没有召回|未召回|不是召回|缺货不是召回)/.test(text)
    || /(?:有什么|有啥|没什么).{0,6}好担心|担心什么/.test(text);
}

function isAvailabilityResolvedContext(text) {
  if (/(?:还是|仍然|依然|一直).{0,8}(?:买不到|断货|缺货|抢不到|不好买)/.test(text)) return false;
  return /(?:有货|都有货|买到了|买得到|买的到|到货|补货|来货|上货|下单|已下单|抢到|续上|有卖|山姆有|京东有|淘宝有|母婴店有|线下门店都有货)/.test(text);
}

function hasTargetedDigestiveComplaint(text) {
  const targetThenRisk = /(?:A2|a2|至初|紫白金|这个A2|这个a2|这个品|这个奶粉|这款|它|喝这个|喝它|就这个)([^，。；;!?！？]{0,24})(?:拉肚子|拉稀|水样便|腹泻|跑厕所)/ig;
  for (const match of text.matchAll(targetThenRisk)) {
    if (!/(?:不怕|不会|不|没|没有|未)\s*$/.test(match[1])) return true;
  }
  return /(?:拉肚子|拉稀|水样便|腹泻|跑厕所).{0,24}(?:是咋回事|好严重|受不了|垃圾|放弃|不敢|就这个|A2.{0,8}会|a2.{0,8}会|至初.{0,8}会|紫白金.{0,8}会)/i.test(text)
    || /(?:拉肚子|拉稀|水样便|腹泻).{0,24}(?:A2|a2|至初|紫白金).{0,8}(?:会|也会|喝完会)/i.test(text);
}

function isResolvedDigestiveBenefitContext(text) {
  if (/会不会(?:拉肚子|拉稀|腹泻|胀气)|(?:拉肚子|拉稀|腹泻|胀气).{0,4}(?:吗|嘛|么|\?|？)/.test(text)) return false;
  if (hasTargetedDigestiveComplaint(text)) return false;

  // 这类语境是在表达 A2 更温和或喝后无不适，不应把“拉肚子/胀气”等词直接当负向。
  return /(?:不怕|不会|不|没|没有|未)(?:拉肚子|拉稀|腹泻|胀气)/.test(text)
    || /(?:乳糖不耐受|喝普通牛奶|喝牛奶|普通牛奶).{0,24}(?:胀气|拉肚子|拉稀|腹泻|不舒服).{0,24}(?:A2|a2|这个|它|更友好|可以试试|可试试|建议试试|推荐试试)/i.test(text)
    || /(?:胀气|拉肚子|拉稀|腹泻|不舒服).{0,16}(?:可以|可|建议|推荐).{0,8}试试.{0,8}(?:A2|a2|这个|它)/i.test(text);
}

function hasTargetedConstipationComplaint(text) {
  const targetThenRisk = /(?:A2|a2|至初|紫白金|这个A2|这个a2|这个奶粉|这款|喝这个|喝它|全奶粉A2|全奶粉a2)([^，。；;!?！？]{0,24})(?:便秘|拉羊屎|羊屎蛋|拉不出来|拉屎干|大便干|肛裂)([^，。；;!?！？]{0,6})/ig;
  for (const match of text.matchAll(targetThenRisk)) {
    if (/(?:不容易|不|没|没有|未|不会|不要|希望不要)\s*$/.test(match[1])) continue;
    // “这款有便秘吗”是在求证风险，不是已经发生的 A2 负向反馈。
    const isRiskQuestion = /(?:会不会|会|容易|有|有没有|是否|是不是|会导致|导致|怎么样啊?\s*有|到底)\s*$/.test(match[1])
      && /(?:吗|嘛|么|\?|？|不)/.test(match[2]);
    if (isRiskQuestion) continue;
    return true;
  }
  return /(?:A2|a2|至初|紫白金)[^，。；;!?！？]{0,16}(?:喝了|吃了|喝完)[^，。；;!?！？]{0,16}(?:便秘|拉羊屎|羊屎蛋|拉不出来|拉屎干|大便干|肛裂)/i.test(text)
    || /(?:便秘越来越严重|还是便秘|仍是没改善|一点用没有|拉羊屎|羊屎蛋|肛裂)/.test(text);
}

function isDigestiveRiskQuestionContext(text) {
  if (hasTargetedConstipationComplaint(text)) return false;
  return /(?:会不会|会|容易|是不是|有没有|有)[^，。；;!?！？]{0,16}(?:便秘|拉肚子|拉稀|腹泻|上火|绿便|奶瓣|吐奶|哭闹|过敏|湿疹|红疹|胀气|不适应)[^，。；;!?！？]{0,6}(?:吗|嘛|么|\?|？|不)/.test(text)
    || /(?:希望不要|不要)[^，。；;!?！？]{0,16}(?:便秘|拉肚子|拉稀|腹泻|上火|绿便|奶瓣|吐奶|哭闹|过敏|湿疹|红疹|胀气|不适应)/.test(text)
    || /(?:便秘|拉肚子|拉稀|腹泻|上火|绿便|奶瓣|吐奶|哭闹|过敏|湿疹|红疹|胀气|不适应)[^，。；;!?！？]{0,4}(?:吗|嘛|么|\?|？|不)/.test(text)
    || /(?:担心|怕|害怕)[^，。；;!?！？]{0,8}(?:便秘|拉肚子|拉稀|腹泻|上火|绿便|奶瓣|吐奶|哭闹|过敏|湿疹|红疹|胀气|不适应)/.test(text);
}

function isResolvedConstipationBenefitContext(text) {
  if (hasTargetedConstipationComplaint(text)) return false;

  // 竞品/旧奶粉引发便秘，转到 A2 后改善，是 A2 的正向证据，不应归为 A2 负向。
  return /(?:皇家|皇家3段|皇家美素|美素|美素力|卓睿|派星|德爱|爱他美|飞鹤|合生元|旧奶粉|之前喝|原来喝|上个奶粉)[^，。；;!?！？]{0,24}便秘[^，。；;!?！？]{0,24}(?:转|换|喝回|换成|转成|转到)[^，。；;!?！？]{0,16}(?:A2|a2|至初|紫白金)[^，。；;!?！？]{0,24}(?:好多了|好点|好了|改善|正常|通畅|不便秘|没有便秘|黄金大便|状态很好|会好点吗)/i.test(text)
    || /(?:便秘|奶瓣|吸收不好)[^，。；;!?！？]{0,24}(?:转|换|喝回|换成|转成|转到)[^，。；;!?！？]{0,16}(?:A2|a2|至初|紫白金)[^，。；;!?！？]{0,24}(?:好多了|好点|好了|改善|正常|通畅|不便秘|没有便秘|黄金大便|状态很好|会好点吗)/i.test(text)
    || /(?:换成|喝回|转成)[^，。；;!?！？]{0,12}(?:A2|a2|至初|紫白金)[^，。；;!?！？]{0,12}便秘好了/i.test(text)
    || /(?:为什么都说便秘|都说便秘)[^，。；;!?！？]{0,36}(?:不会便秘|不便秘|没便秘|没有便秘|黄金大便|黄金超标)/.test(text);
}

function isResolvedRecallContext(text) {
  const competitorRecallSwitch = /(?:德爱|爱他美|美素|皇家美素佳儿|飞鹤|君乐宝|启赋|雀巢|能恩|蓝臻|澳爱|派星).{0,24}召回.{0,36}(?:想|准备|打算|考虑|换|转).{0,16}(?:A2|a2|至初|紫白金)/i.test(text);
  const competitorOnlyRecall = /(?:德爱|爱他美|美素|皇家美素佳儿|飞鹤|君乐宝|启赋|雀巢|能恩|蓝臻|澳爱|派星).{0,24}召回/i.test(text)
    && !/(?:A2|a2|至初|紫白金)/i.test(text);
  const reassurance = /(?:被召回的)?美版(?:的)?(?:A2|a2)?.{0,16}(?:不是澳版|不影响|无关|怕个啥|担心什么)/i.test(text)
    || /(?:召回的)?只有美版.{0,12}(?:别慌|不影响|放心|没事)/.test(text)
    || /(?:不是之前召回的那批|缺货.{0,6}不是召回|不涉及|非召回批次|不属于召回批次)/.test(text)
    || /(?:敢召回说明|机制透明才召回|标准高才会有召回|大排查过|更安全|没必要乱换|继续喝非召回批次)/.test(text)
    || /(?:国版无关|和国版无关|国内版无关|和国内版无关|没召回|没有召回|未召回|无召回|没被召回|没有被召回)/.test(text)
    || /(?:美版|美国).{0,12}(?:批次|几个批次).{0,18}(?:无关|不影响|不涉及)/.test(text)
    || /(?:召回的也是|召回的是|召回).{0,12}(?:美版|美国).{0,12}(?:几个批次|批次)/.test(text)
    || /(?:没必要|不用|不要|别).{0,8}(?:过度)?焦虑.{0,24}召回/.test(text);
  return competitorRecallSwitch || competitorOnlyRecall || reassurance;
}

function hasExplicitSolubilityComplaint(text) {
  return /(?:容易|总是|还是|特别|非常|太|不好|不能|无法).{0,8}(?:挂壁|结块|难溶|冲不开|摇不开|泡不开)/.test(text)
    || /还(?!好不).{0,8}(?:挂壁|结块|难溶|冲不开|摇不开|泡不开)/.test(text)
    || /(?:很|最)难溶/.test(text)
    || /(?:挂壁|结块|难溶|冲不开|摇不开|泡不开).{0,10}(?:严重|问题|抵触|放弃|抽奖|解决不了|太多)/.test(text)
    || /(?:一团一团|摇不开|泡不开)/.test(text);
}

function isResolvedSolubilityContext(text, rule) {
  if (hasExplicitSolubilityComplaint(text)) return false;
  const generalResolved = /(?:亲测有效|很好冲泡|好溶解|很好融|全部溶解|完全溶解|泡得开|十秒匀好|不是坏事|没有添加助溶剂)/.test(text);
  if (rule === '挂壁') {
    return generalResolved
      || /(?:没有|没|不会|不|无|一点都不|基本不|还好不)挂壁/.test(text)
      || /挂壁.{0,8}(?:没有|没了|都没|一律没有)/.test(text)
      || /(?:无结块无挂壁|不结块不挂壁|不结块挂壁|搅匀不挂壁)/.test(text);
  }
  if (rule === '结块') {
    return generalResolved
      || /(?:没有|没|不会|不|无|一点都不|基本不|还好不|几乎不会)结块/.test(text)
      || /结块.{0,8}(?:没有|没了|都没|一律没有)/.test(text)
      || /(?:无结块无挂壁|不结块不挂壁|不结块挂壁|不留渣)/.test(text);
  }
  if (rule === '难溶') return generalResolved || /难溶.{0,6}(?:不是坏事|没有添加助溶剂)/.test(text);
  if (rule === '冲不开') return generalResolved || /(?:容易冲开|很好冲泡|泡得开|全部溶解|完全溶解)/.test(text);
  return false;
}

function isSafetyQuestionContext(text) {
  return /(?:有没有|有无|是否|是不是|会不会|请问|想问|求问|蹲)[^，。；;!?！？]{0,24}(?:问题|召回|涉及|影响|安全|名单|批次|能喝|还能喝|可以喝)/.test(text)
    || /(?:有问题|没问题|没有问题|在名单里|在不在名单|召回|涉及|不涉及|影响|安全|能喝|还能喝|可以喝)[^，。；;!?！？]{0,8}(?:吗|嘛|么|\?|？|吧)/.test(text)
    || /(?:这个|这款|这批|这个批次|我家|刚买|刚到|收到货)[^，。；;!?！？]{0,24}(?:在名单里|有没有问题|有问题吗|没问题吧|召回吗|安全吗)/.test(text);
}

function hasSafetyAnxietySignal(text) {
  return /(?:害怕|怕|慌|心慌|焦虑|担心|吓|心跳|睡不着|不敢|不能喝|可不敢|天塌|怎么办|咋办)/.test(text);
}

function isCurrentUseSafetyConcernContext(text) {
  const currentUse = /(?:一直喝|还在喝|正在喝|继续喝|刚买|刚到|收到货|囤了|家里有|在喝|喝着|吃着|喝的|喝了|宝宝才|娃才|月子里|新生儿|刚出生)/.test(text);
  const safetyEvent = /(?:召回|批次|毒素|污染|下架|风险|名单|有问题|出问题|塌房|公告|声明)/.test(text);
  const switchRisk = /(?:担心|怕|慌|焦虑|不踏实|膈应|不放心|不敢|要不要换|要不要转|该不该转|换奶|转奶|换不换|转不转|怎么办|咋办|挺住|还能喝|能不能喝|可以喝吗)/.test(text);
  const explicitReassurance = /(?:放心了|不用担心|别担心|别慌|没必要慌|没必要焦虑|可以放心|正常喝就行|继续喝没问题)/.test(text);
  return currentUse && safetyEvent && switchRisk && !explicitReassurance;
}

function isPlainSafetyQuestion(text, negativeMatches) {
  if (!isSafetyQuestionContext(text) || hasSafetyAnxietySignal(text)) return false;
  const safetyQuestionRisks = new Set([
    '召回',
    '悄悄召回',
    '有问题',
    '出问题',
    '有没有问题',
    '不确定',
    '不清楚',
    '存疑',
    '假',
    '真假',
    '真的假的',
    '真的吗',
    '该信谁',
  ]);
  return negativeMatches.length === 0 || negativeMatches.every((rule) => safetyQuestionRisks.has(rule));
}

function isSafetyEventInformationContext(text) {
  return /(?:召回|毒素|批次|警惕|紧急|速查|下架|停售|污染|风险|回收|官方通知|公告|声明|名单|自查)/.test(text);
}

function isNegativeTransferContext(text) {
  const risk = '(?:被迫|无奈|不得不|断粮|挺不住|来不及|慌|怕|焦虑|纠结|召回|断货|缺货|买不到|抢不到|喝不了|不敢喝|不能喝|不适应|便秘|拉肚子|拉稀|吐奶|胀气|湿疹|过敏|不长肉|有问题|出问题|不放心)';
  return new RegExp(`${risk}.{0,40}(?:转奶|换奶|转|换)|(?:转奶|换奶|转|换).{0,40}${risk}`).test(text);
}

function isSwitchedToCompetitorContext(text) {
  return new RegExp(`(?:我|我们|娃|宝宝|家里)?[^，。；;!?！？]{0,12}(?:转了|转到|转成|换了|换到|换成|改喝|现在喝|目前喝|已经喝)[^，。；;!?！？]{0,16}${COMPETITOR_BRAND_RE.source}`, 'i').test(text)
    || new RegExp(`(?:转的|换的|喝的)[^，。；;!?！？]{0,12}${COMPETITOR_BRAND_RE.source}`, 'i').test(text);
}

function isCompetitorPreferenceContext(text) {
  return new RegExp(`(?:坚持喝|一直喝|一直在喝|继续喝|还喝|还是喝|选择|选了|推荐|认准|不换)[^，。；;!?！？]{0,16}${COMPETITOR_BRAND_RE.source}`, 'i').test(text)
    || new RegExp(`${COMPETITOR_BRAND_RE.source}.{0,40}(?:价格公道|品质有保证|更放心|更安全|没跟风|不跟风|挺好|不错|靠谱|好喝|适应|正常|品质好)`, 'i').test(text)
    || /(?:爱他美|领熠|悦白|澳爱|皇家美素|美素佳儿)[^，。；;!?！？]{0,20}(?:没跟风|品质有保证|价格公道)/i.test(text);
}

function filterPositiveMatches(text, matches) {
  const blocked = new Set();
  if (/不长肉|没长肉|没有长肉|不见长肉/.test(text)) blocked.add('长肉');
  if (/不长高|没长高|没有长高/.test(text)) blocked.add('长高');
  if (/不好吸收|不吸收|吸收不了/.test(text)) blocked.add('好吸收');
  if (/不好消化|消化不好|消化不了/.test(text)) blocked.add('好消化');
  if (/没营养|没有营养|无营养/.test(text)) blocked.add('营养');
  if (/神化|没那么神|喝啥也涨|喝啥都涨|喝了不行|喝着不行/.test(text)) {
    blocked.add('长肉');
    blocked.add('长高');
  }
  if (/没有改善|没改善|无改善|毫无改善|一点用没有|好点了吗|会好点吗/.test(text)) {
    blocked.add('改善');
    blocked.add('好点');
    blocked.add('好多了');
  }
  if (/难喝|不好喝|寡淡|腥味|不香|发涩|慎点|后悔|踩雷/.test(text)) {
    blocked.add('推荐');
    blocked.add('值得');
    blocked.add('合适');
    blocked.add('不错');
  }
  if (/不爱喝|拒奶/.test(text)) {
    blocked.add('爱喝');
    blocked.add('宝宝爱喝');
    blocked.add('喜欢喝');
  }
  if (/不放心|不安心|不信任|不信|不敢(?:喝|吃|用|继续|买)|不能(?:喝|吃)/.test(text) && !isAntiAnxietyContext(text)) {
    blocked.add('放心');
    blocked.add('安心');
    blocked.add('放心喝');
    blocked.add('安心喝');
    blocked.add('相信');
    blocked.add('信官方');
    blocked.add('能喝');
    blocked.add('可以喝');
  }
  if (hasTargetedDigestiveComplaint(text) || /会不会(?:拉肚子|腹泻|胀气)/.test(text)) {
    blocked.add('不怕拉肚子');
    blocked.add('不会拉肚子');
    blocked.add('不拉肚子');
    blocked.add('没有拉肚子');
    blocked.add('没拉肚子');
  }
  if (hasExplicitSolubilityComplaint(text)) {
    blocked.add('好溶解');
    blocked.add('很好融');
    blocked.add('很好冲泡');
    blocked.add('不挂壁');
    blocked.add('不结块');
  }
  if (/不适应/.test(text) && !/(?:没有|没|无|不会|未).{0,3}不适应|没有啥不适|没啥不适|无不适/.test(text)) blocked.add('适应');
  if (isSafetyQuestionContext(text)) {
    for (const rule of ['没问题', '没有问题', '批次没问题', '澳版没问题', '没事', '没召回', '没有召回', '未召回', '不是召回', '缺货不是召回', '不涉及', '不影响', '安全', '放心', '安心', '能喝', '可以喝', '到货', '正常', '正常售卖']) {
      blocked.add(rule);
    }
  }
  if (isSafetyEventInformationContext(text)) {
    // 安全事件信息帖里的“安全/推荐/放心”常是科普话术，不等同于品牌正向反馈。
    for (const rule of ['安全', '推荐', '放心', '安心', '正常', '正常喝', '继续喝', '一直喝', '还在喝', '很好', '到货', '理性', '值得', '没问题', '没有问题', '批次没问题', '澳版没问题', '没事', '没召回', '没有召回', '未召回', '不是召回', '缺货不是召回', '不涉及', '不影响', '正常售卖', '官方声明', '辟谣', '不传谣不信谣', '以官方消息为准', '信官方', '别慌', '不用焦虑', '不要焦虑', '别焦虑', '没必要过度焦虑']) {
      blocked.add(rule);
    }
  }
  if (isSwitchedToCompetitorContext(text) || isCompetitorPreferenceContext(text)) {
    // 转到竞品后“吐奶正常/打嗝正常/挺好”是竞品正向，但对目标产品是流失信号。
    for (const rule of matches) blocked.add(rule);
  }
  return matches.filter((rule) => !blocked.has(rule));
}

function filterNegativeMatches(text, matches) {
  const resolved = new Set();
  if (/没有便秘|没便秘|不便秘|未便秘|不会便秘/.test(text) && !hasTargetedConstipationComplaint(text)) resolved.add('便秘');
  if (/便秘人士.*爽|便秘.*通畅|治便秘|缓解便秘|便秘.*(?:能|可以).*喝/.test(text)) resolved.add('便秘');
  if (isResolvedConstipationBenefitContext(text)) resolved.add('便秘');
  if (isDigestiveRiskQuestionContext(text)) {
    for (const rule of ['便秘', '拉肚子', '拉稀', '腹泻', '上火', '绿便', '奶瓣', '吐奶', '哭闹', '过敏', '湿疹', '红疹', '胀气', '不适应', '担心']) {
      resolved.add(rule);
    }
  }
  if (isResolvedDigestiveBenefitContext(text)) {
    resolved.add('拉肚子');
    resolved.add('腹泻');
    resolved.add('胀气');
  }
  if (/没有拉肚子|没拉肚子|不拉肚子|未拉肚子/.test(text) && !hasTargetedDigestiveComplaint(text)) resolved.add('拉肚子');
  if (/没有腹泻|没腹泻|不腹泻|未腹泻/.test(text) && !hasTargetedDigestiveComplaint(text)) resolved.add('腹泻');
  if (/没有上火|没上火|不上火|未上火/.test(text)) resolved.add('上火');
  if (/没有过敏|没过敏|不过敏|未过敏/.test(text)) resolved.add('过敏');
  if (/没有湿疹|没湿疹|不湿疹|未湿疹/.test(text)) resolved.add('湿疹');
  if (/没有吐奶|没吐奶|不吐奶|未吐奶/.test(text)) resolved.add('吐奶');
  if (/没有胀气|没胀气|不胀气|未胀气/.test(text) && !hasTargetedDigestiveComplaint(text)) resolved.add('胀气');
  if (/没有奶瓣|没奶瓣|无奶瓣|不拉奶瓣/.test(text)) resolved.add('奶瓣');
  if (/没有绿便|没绿便|无绿便|不拉绿便/.test(text)) resolved.add('绿便');
  if (/(?:没有|没|无|不会|未).{0,3}不适应|没有啥不适|没有什么不适|没啥不适|无不适/.test(text)) resolved.add('不适应');
  if (/(?:没有|没|无|不会|未).{0,3}不良反应|没不良反应|无不良反应/.test(text)) resolved.add('不良反应');
  if (/(?:没有|没|无).{0,3}(?:问题|出问题)|没问题|没有问题|问题不大/.test(text)) {
    resolved.add('有问题');
    resolved.add('出问题');
    resolved.add('有没有问题');
  }
  for (const rule of ['为啥', '怎么办', '什么情况', '怎么回事']) {
    resolved.add(rule);
  }
  if (/不能喝(?:冰|冷|凉|常温)|不能吃(?:冰|冷|凉)|不敢喝(?:冰|冷|凉)/.test(text)) {
    resolved.add('不能喝');
    resolved.add('不能吃');
    resolved.add('不敢喝');
  }
  if (/不踩雷|没踩雷|没有踩雷|避雷成功/.test(text)) resolved.add('踩雷');
  if (/不踩坑|没踩坑|没有踩坑/.test(text)) resolved.add('踩坑');
  if (/入坑|坑位|不能坑自己人|不坑/.test(text)) resolved.add('坑');
  if (/贵有贵的道理|贵就是好|买贵一点|贵一点的|不贵|没那么贵/.test(text)) resolved.add('贵');
  if (/(?:价格|这个价格|多少钱).{0,12}贵(?:吗|嘛|么|\?|？)|贵(?:吗|嘛|么|\?|？)|值不值/.test(text)
    && !/(?:太贵|超贵|好贵|贵太多|贵死|巨贵|老贵|贵得|费钱)/.test(text)) {
    resolved.add('贵');
    resolved.add('太贵');
  }
  const currentUseSafetyConcern = isCurrentUseSafetyConcernContext(text);
  if (isResolvedRecallContext(text) && !currentUseSafetyConcern) {
    resolved.add('召回');
    resolved.add('担心');
  }
  if (isAntiAnxietyContext(text) && !currentUseSafetyConcern) {
    for (const rule of ['不放心', '不安心', '不信任', '不信', '担心', '焦虑', '害怕', '后怕', '恐慌', '冒险', '风险', '太吓人', '睡不着觉', '很难放心', '召回', '悄悄召回', '下架', '有问题', '出问题', '爆雷', '暴雷', '存疑', '不清楚', '不确定', '不知道啥情况']) {
      resolved.add(rule);
    }
  }
  if (isAvailabilityResolvedContext(text)) {
    for (const rule of ['买不到', '断货', '缺货', '抢不到', '不好买', '下架', '停产']) resolved.add(rule);
  }
  if (!isNegativeTransferContext(text)) {
    resolved.add('转奶');
    resolved.add('换奶');
  }
  if (/好不好喝|难喝(?:吗|嘛|么|\?|？)|不好喝(?:吗|嘛|么|\?|？)|没有难喝|没难喝|不难喝|没有不好喝|没不好喝/.test(text)) {
    resolved.add('难喝');
    resolved.add('不好喝');
  }
  if (/(?:真的)?(?:没|没有|有)?奶?腥味(?:吗|嘛|么|\?|？)/.test(text)) resolved.add('腥味');
  if (/(?:会不会|是否|是不是|请问|想问|求问).{0,18}(?:挂壁|结块|难溶|冲不开|不好泡)|(?:挂壁|结块|难溶|冲不开|不好泡).{0,8}(?:吗|嘛|么|\?|？)/.test(text)) {
    for (const rule of ['挂壁', '结块', '难溶', '冲不开', '不好泡']) resolved.add(rule);
  }
  for (const rule of ['挂壁', '结块', '难溶', '冲不开']) {
    if (isResolvedSolubilityContext(text, rule)) resolved.add(rule);
  }
  if (!/(?:黑色|黑).*?(?:异物|颗粒|东西|虫|点)|(?:异物|颗粒|东西|虫|点).*?(?:黑色|黑)/.test(text)) resolved.add('黑色');
  if (/真的假的|真假的|真假|真伪|辩真伪|辨真伪/.test(text) && !/假货|买到假|假的|假奶粉|假冒/.test(text)) {
    resolved.add('假');
  }
  if (isSwitchingToTargetFromCompetitorRisk(text)) {
    for (const rule of matches) {
      if (RISK_WORD_RE.test(rule)) resolved.add(rule);
    }
  }
  for (const rule of matches) {
    if (isCompetitorOnlyRiskContext(text, rule)) resolved.add(rule);
  }
  const filtered = matches.filter((rule) => !resolved.has(rule));
  if (isSwitchedToCompetitorContext(text) && !filtered.length) return ['转牌竞品'];
  if (isCompetitorPreferenceContext(text) && !filtered.length) return ['竞品偏好'];
  return filtered;
}

function isSwitchingToTargetAfterConcern(text) {
  return /(?:正想|想|准备|打算|考虑|要)(?:换|转)(?:至初|A2至初|a2至初)/i.test(text);
}

function isAskingAboutPositiveOutcome(text, positiveMatches, questionMatches) {
  if (!positiveMatches.length || !questionMatches.length) return false;
  return positiveMatches.some((rule) => {
    const escapedRule = rule.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const directQuestion = new RegExp(`${escapedRule}.{0,3}(?:吗|嘛|么|\\?|？)`, 'i');
    const leadingQuestion = new RegExp(`(?:有没有|有.*吗|求问|想问|问问|怎么样|如何|会不会|能不能|可以不可以|是不是).{0,24}${escapedRule}`, 'i');
    return directQuestion.test(text) || leadingQuestion.test(text);
  });
}

function classifyComment(row) {
  const text = row.clean_comment_text;
  const adMatches = findMatches(text, AD_TRADE_RULES);
  const positiveMatches = filterPositiveMatches(text, findMatches(text, activePositiveRules));
  const negativeMatches = filterNegativeMatches(text, findMatches(text, activeNegativeRules));
  const questionMatches = findMatches(text, QUESTION_RULES);
  const topics = [];
  for (const [topic, rules] of TOPIC_RULES) {
    if (findMatches(text, rules).length) topics.push(topic);
  }

  // 情感先剥离广告交易，再判断正负混合；母婴评论里“求链接/回收”常不是消费情绪。
  let sentiment = '中性';
  const onlyWeakPositive = positiveMatches.length > 0 && positiveMatches.every((rule) => activeWeakPositiveRules.has(rule));
  if (adMatches.length) sentiment = '广告交易';
  // 安全/召回/批次求证按泛负向处理，因为它代表信任风险和潜在转牌风险。
  else if (isPlainSafetyQuestion(text, negativeMatches)) sentiment = '负向/疑虑';
  else if (positiveMatches.length && negativeMatches.length && !onlyWeakPositive) sentiment = '混合';
  else if (negativeMatches.length && isSwitchingToTargetAfterConcern(text)) sentiment = '中性咨询';
  else if (negativeMatches.length) sentiment = '负向/疑虑';
  else if (isAskingAboutPositiveOutcome(text, positiveMatches, questionMatches)) sentiment = '中性咨询';
  else if (questionMatches.length && (!positiveMatches.length || onlyWeakPositive)) sentiment = '中性咨询';
  else if (positiveMatches.length) sentiment = '正向';
  else if (questionMatches.length) sentiment = '中性咨询';

  let primaryIntent = '普通反馈';
  if (adMatches.length) primaryIntent = '广告/交易';
  else if (questionMatches.length) primaryIntent = '咨询求证';
  else if (topics.includes('转奶经验')) primaryIntent = '转奶经验';
  else if (topics.includes('购买渠道/价格')) primaryIntent = '购买决策';
  else if (topics.includes('吸收/肠胃')) primaryIntent = '喂养反馈';
  else if (topics.includes('竞品对比')) primaryIntent = '品牌对比';

  const isHighValue = !adMatches.length && text.length >= 6 && !['不错', '好奶粉', '好喝', '可以'].includes(text);

  return {
    sentiment,
    primary_intent: primaryIntent,
    topics: topics.length ? topics : ['其他'],
    is_ad_trade: adMatches.length ? '是' : '否',
    is_high_value: isHighValue ? '是' : '否',
    positive_tags: positiveMatches.join(';'),
    risk_tags: negativeMatches.join(';'),
    question_tags: questionMatches.join(';'),
    ad_trade_tags: adMatches.join(';'),
  };
}

function stratifiedSample(rows, sampleSize) {
  if (!sampleSize || sampleSize >= rows.length) return rows;
  const groups = new Map();
  for (const row of rows) {
    const key = row.keywords[0] || 'unknown';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }
  const selected = new Map();
  const sortedGroups = [...groups.values()].sort((a, b) => b.length - a.length);
  for (const group of sortedGroups) {
    const quota = Math.max(1, Math.floor((group.length / rows.length) * sampleSize));
    const sorted = [...group].sort((a, b) => stableHash(a.dedupe_key) - stableHash(b.dedupe_key));
    for (const row of sorted.slice(0, quota)) selected.set(row.dedupe_key, row);
  }
  const rest = rows
    .filter((row) => !selected.has(row.dedupe_key))
    .sort((a, b) => stableHash(a.dedupe_key) - stableHash(b.dedupe_key));
  for (const row of rest) {
    if (selected.size >= sampleSize) break;
    selected.set(row.dedupe_key, row);
  }
  return [...selected.values()].sort((a, b) => a.dedupe_key.localeCompare(b.dedupe_key));
}

function pct(count, total) {
  if (!total) return '0.0%';
  return `${((count / total) * 100).toFixed(1)}%`;
}

function countBy(rows, getKeys) {
  const counts = new Map();
  for (const row of rows) {
    const keys = Array.isArray(getKeys(row)) ? getKeys(row) : [getKeys(row)];
    for (const key of keys.filter(Boolean)) counts.set(key, (counts.get(key) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'zh-CN'));
}

function writeCountSummaryCsv(file, counts, total, keyHeader) {
  writeCsv(file, counts.map(([key, count]) => ({
    [keyHeader]: key,
    count,
    percent: pct(count, total),
  })), [keyHeader, 'count', 'percent']);
}

function writeKeywordSentimentSummaryCsv(file, rows) {
  const byKeyword = new Map();
  for (const row of rows) {
    for (const keyword of row.keywords) {
      if (!byKeyword.has(keyword)) byKeyword.set(keyword, Object.fromEntries(SENTIMENTS.map((sentiment) => [sentiment, 0])));
      const current = byKeyword.get(keyword);
      current[row.sentiment] = (current[row.sentiment] || 0) + 1;
    }
  }

  const summaryRows = [...byKeyword.entries()].map(([keyword, counts]) => {
    const total = SENTIMENTS.reduce((sum, sentiment) => sum + (counts[sentiment] || 0), 0);
    const positive = counts['正向'] || 0;
    const negative = counts['负向/疑虑'] || 0;
    return {
      keyword,
      total,
      positive,
      positive_percent: pct(positive, total),
      negative_concern: negative,
      negative_percent: pct(negative, total),
      mixed: counts['混合'] || 0,
      neutral_consult: counts['中性咨询'] || 0,
      ad_trade: counts['广告交易'] || 0,
      neutral: counts['中性'] || 0,
    };
  }).sort((a, b) => b.total - a.total || a.keyword.localeCompare(b.keyword, 'zh-CN'));

  writeCsv(file, summaryRows, [
    'keyword',
    'total',
    'positive',
    'positive_percent',
    'negative_concern',
    'negative_percent',
    'mixed',
    'neutral_consult',
    'ad_trade',
    'neutral',
  ]);
}

function collectPhraseCounts(rows) {
  const counts = new Map();
  for (const row of rows) {
    const text = row.clean_comment_text;
    for (const phrase of PHRASES) {
      const matches = text.match(new RegExp(phrase.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi'));
      if (matches) counts.set(phrase, (counts.get(phrase) || 0) + matches.length);
    }
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'zh-CN'));
}

function truncate(text, length = 86) {
  const value = String(text || '');
  return value.length > length ? `${value.slice(0, length)}...` : value;
}

function mdTable(headers, rows) {
  const lines = [
    `| ${headers.join(' | ')} |`,
    `| ${headers.map(() => '---').join(' | ')} |`,
  ];
  for (const row of rows) {
    lines.push(`| ${row.map((cell) => String(cell).replace(/\|/g, '/')).join(' | ')} |`);
  }
  return lines.join('\n');
}

function renderWordCloudSvg(title, phraseCounts) {
  const words = phraseCounts.slice(0, 55);
  const width = 960;
  const height = 560;
  const max = words[0]?.[1] || 1;
  let x = 42;
  let y = 92;
  let rowHeight = 0;
  const items = [];
  words.forEach(([word, count], index) => {
    const fontSize = Math.round(16 + (Math.log(count + 1) / Math.log(max + 1)) * 40);
    const textWidth = Math.max(54, word.length * fontSize * 0.82);
    if (x + textWidth > width - 40) {
      x = 42;
      y += rowHeight + 22;
      rowHeight = 0;
    }
    if (y > height - 36) return;
    const color = COLOR_PALETTE[index % COLOR_PALETTE.length];
    items.push(`<text x="${x}" y="${y}" font-size="${fontSize}" fill="${color}" font-weight="${fontSize > 38 ? 700 : 500}">${escapeXml(word)}</text>`);
    x += textWidth + 24;
    rowHeight = Math.max(rowHeight, fontSize);
  });
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <rect width="100%" height="100%" fill="#fbfbf8"/>
  <text x="40" y="44" font-size="24" font-weight="700" fill="#222">${escapeXml(title)}</text>
  <text x="40" y="70" font-size="13" fill="#666">字号按词频缩放；已基于规则短语抽取，不含原始 JSON。</text>
  ${items.join('\n  ')}
</svg>
`;
}

function renderBarSvg(title, rows) {
  const width = 880;
  const height = 360;
  const marginLeft = 110;
  const max = Math.max(...rows.map((row) => row.count), 1);
  const barHeight = 28;
  const gap = 16;
  const items = rows.map((row, index) => {
    const y = 76 + index * (barHeight + gap);
    const barWidth = Math.round((row.count / max) * 620);
    const color = COLOR_PALETTE[index % COLOR_PALETTE.length];
    return `<text x="32" y="${y + 20}" font-size="14" fill="#333">${escapeXml(row.label)}</text>
  <rect x="${marginLeft}" y="${y}" width="${barWidth}" height="${barHeight}" rx="3" fill="${color}"/>
  <text x="${marginLeft + barWidth + 10}" y="${y + 20}" font-size="14" fill="#333">${row.count} (${row.percent})</text>`;
  });
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <rect width="100%" height="100%" fill="#fbfbf8"/>
  <text x="32" y="42" font-size="24" font-weight="700" fill="#222">${escapeXml(title)}</text>
  ${items.join('\n  ')}
</svg>
`;
}

function escapeXml(text) {
  return String(text)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function makeExamples(rows, sentiment, limit = 8) {
  return rows
    .filter((row) => row.sentiment === sentiment && row.is_high_value === '是')
    .sort((a, b) => b.comment_likes - a.comment_likes || b.clean_comment_text.length - a.clean_comment_text.length)
    .slice(0, limit)
    .map((row) => [
      row.comment_likes,
      row.keywords.join(' / '),
      row.topics.join(';'),
      truncate(row.clean_comment_text),
    ]);
}

function buildReport({
  sourceFiles,
  lexiconInfo,
  allRows,
  sampledRows,
  sampleSize,
  sentimentCounts,
  topicCounts,
  keywordCounts,
  phraseCounts,
  outputFiles,
}) {
  const total = sampledRows.length;
  const highValue = sampledRows.filter((row) => row.is_high_value === '是').length;
  const adTrade = sampledRows.filter((row) => row.is_ad_trade === '是').length;
  const duplicateRows = sampledRows.reduce((sum, row) => sum + row.duplicate_count - 1, 0);
  const report = [];
  report.push('# 小红书评论情感与主题分析试跑');
  report.push('');
  report.push('## 数据范围');
  report.push(`- 来源文件：${sourceFiles.map((file) => `\`${file}\``).join('、')}`);
  if (lexiconInfo) {
    report.push(`- 情感词库：\`${lexiconInfo.file}\`（正向 ${lexiconInfo.positive_count} 条，负向 ${lexiconInfo.negative_count} 条，弱正向 ${lexiconInfo.weak_positive_count} 条）`);
  }
  report.push(`- 合并去重后全量评论：${allRows.length} 条`);
  report.push(`- 本次分析样本：${total} 条${sampleSize ? `（目标样本 ${sampleSize} 条，按关键词做确定性抽样）` : '（全量）'}`);
  report.push(`- 样本内由多关键词/多文件重复合并掉的原始重复行：${duplicateRows} 行`);
  report.push(`- 高价值评论：${highValue} 条（${pct(highValue, total)}）`);
  report.push(`- 广告/交易类评论：${adTrade} 条（${pct(adTrade, total)}）`);
  report.push('');
  report.push('## 情感分布');
  report.push(mdTable(['情感', '数量', '占比'], SENTIMENTS.map((sentiment) => {
    const count = sentimentCounts.get(sentiment) || 0;
    return [sentiment, count, pct(count, total)];
  })));
  report.push('');
  report.push('## 主题分布');
  report.push(mdTable(['主题', '数量', '占比'], topicCounts.slice(0, 12).map(([topic, count]) => [topic, count, pct(count, total)])));
  report.push('');
  report.push('## 关键词覆盖');
  report.push('按评论命中过的关键词统计；一条去重评论如果被多个关键词命中，会分别计入对应关键词。');
  report.push('');
  report.push(mdTable(['关键词', '评论数'], keywordCounts.slice(0, 15).map(([keyword, count]) => [keyword, count])));
  report.push('');
  report.push('## 高频短语');
  report.push(mdTable(['短语', '次数'], phraseCounts.slice(0, 25).map(([phrase, count]) => [phrase, count])));
  report.push('');
  report.push('## 代表评论');
  for (const sentiment of ['正向', '负向/疑虑', '中性咨询', '混合', '广告交易']) {
    const examples = makeExamples(sampledRows, sentiment, 6);
    if (!examples.length) continue;
    report.push(`### ${sentiment}`);
    report.push(mdTable(['赞数', '关键词', '主题', '评论'], examples));
    report.push('');
  }
  report.push('## 初步判断');
  report.push('- 这版是规则口径试跑，适合快速判断结构；如果口径确认，可以直接跑全量并扩展人工校准样本。');
  report.push('- 合并去重必须继续保留，否则同一篇文章/同一条评论被多个关键词命中，会放大正向或广告噪音。');
  report.push('- 建议后续把“广告/交易”从情感分析主样本里剥离，单独作为评论区治理或噪音指标看。');
  report.push('');
  report.push('## 产物');
  for (const file of outputFiles) {
    report.push(`- \`${file}\``);
  }
  report.push('');
  return `${report.join('\n')}\n`;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const commentsFile = args.comments || DEFAULT_COMMENTS_FILE;
  const detailFile = args.detail || DEFAULT_DETAIL_FILE;
  const outDir = args['out-dir'] || DEFAULT_OUT_DIR;
  const sampleSize = args.full ? 0 : Number.parseInt(args.sample || '500', 10);
  const lexicon = configureLexicon(args.lexicon || args['lexicon-csv']);
  mkdirSync(outDir, { recursive: true });

  const inputGroups = [{ source: basename(commentsFile), rows: readCsv(commentsFile) }];
  if (detailFile && detailFile !== commentsFile) {
    inputGroups.push({ source: basename(detailFile), rows: readCsv(detailFile) });
  }
  const allMergedRows = mergeCommentRows(inputGroups);
  const sampledRows = stratifiedSample(allMergedRows, sampleSize);

  for (const row of sampledRows) Object.assign(row, classifyComment(row));

  const suffix = sampleSize ? `sample${sampledRows.length}` : 'full';
  const enrichedRows = sampledRows.map((row) => ({
    dedupe_key: row.dedupe_key,
    duplicate_count: row.duplicate_count,
    source_files: row.source_files.join(';'),
    keywords: row.keywords.join(';'),
    search_ranks: row.search_ranks.join(';'),
    note_id: row.note_id,
    note_title: row.note_title,
    note_author_name: row.note_author_name,
    comment_id: row.comment_id,
    comment_text: row.comment_text,
    clean_comment_text: row.clean_comment_text,
    comment_likes: row.comment_likes,
    comment_time: row.comment_time,
    sentiment: row.sentiment,
    primary_intent: row.primary_intent,
    topics: row.topics.join(';'),
    is_ad_trade: row.is_ad_trade,
    is_high_value: row.is_high_value,
    positive_tags: row.positive_tags,
    risk_tags: row.risk_tags,
    question_tags: row.question_tags,
    ad_trade_tags: row.ad_trade_tags,
  }));

  const enrichedFile = join(outDir, `xhs_comments_enriched_${suffix}.csv`);
  const reportFile = join(outDir, `xhs_comment_analysis_report_${suffix}.md`);
  const wordCloudAllFile = join(outDir, `wordcloud_all_${suffix}.svg`);
  const wordCloudPositiveFile = join(outDir, `wordcloud_positive_${suffix}.svg`);
  const wordCloudConcernFile = join(outDir, `wordcloud_concern_${suffix}.svg`);
  const sentimentSvgFile = join(outDir, `sentiment_distribution_${suffix}.svg`);
  const sentimentSummaryFile = join(outDir, `sentiment_summary_${suffix}.csv`);
  const topicSummaryFile = join(outDir, `topic_summary_${suffix}.csv`);
  const keywordSentimentSummaryFile = join(outDir, `keyword_sentiment_summary_${suffix}.csv`);
  const riskTagSummaryFile = join(outDir, `risk_tag_summary_${suffix}.csv`);

  const headers = Object.keys(enrichedRows[0] || {});
  writeCsv(enrichedFile, enrichedRows, headers);

  const sentimentCounts = new Map(countBy(sampledRows, (row) => row.sentiment));
  const topicCounts = countBy(sampledRows, (row) => row.topics);
  const keywordCounts = countBy(sampledRows, (row) => row.keywords);
  const phraseCounts = collectPhraseCounts(sampledRows);
  const positivePhraseCounts = collectPhraseCounts(sampledRows.filter((row) => row.sentiment === '正向'));
  const concernPhraseCounts = collectPhraseCounts(sampledRows.filter((row) => row.sentiment === '负向/疑虑' || row.sentiment === '混合'));
  const riskTagCounts = countBy(sampledRows, (row) => row.risk_tags.split(';').filter(Boolean));

  writeCountSummaryCsv(sentimentSummaryFile, SENTIMENTS.map((sentiment) => [sentiment, sentimentCounts.get(sentiment) || 0]), sampledRows.length, 'sentiment');
  writeCountSummaryCsv(topicSummaryFile, topicCounts, sampledRows.length, 'topic');
  writeCountSummaryCsv(riskTagSummaryFile, riskTagCounts, sampledRows.length, 'risk_tag');
  writeKeywordSentimentSummaryCsv(keywordSentimentSummaryFile, sampledRows);

  writeFileSync(wordCloudAllFile, renderWordCloudSvg('全量样本高频短语', phraseCounts), 'utf8');
  writeFileSync(wordCloudPositiveFile, renderWordCloudSvg('正向评论高频短语', positivePhraseCounts), 'utf8');
  writeFileSync(wordCloudConcernFile, renderWordCloudSvg('负向/疑虑评论高频短语', concernPhraseCounts), 'utf8');

  const sentimentRows = SENTIMENTS.map((label) => {
    const count = sentimentCounts.get(label) || 0;
    return { label, count, percent: pct(count, sampledRows.length) };
  });
  writeFileSync(sentimentSvgFile, renderBarSvg('情感分布', sentimentRows), 'utf8');

  const outputFiles = [
    enrichedFile,
    reportFile,
    wordCloudAllFile,
    wordCloudPositiveFile,
    wordCloudConcernFile,
    sentimentSvgFile,
    sentimentSummaryFile,
    topicSummaryFile,
    keywordSentimentSummaryFile,
    riskTagSummaryFile,
  ];
  const report = buildReport({
    sourceFiles: inputGroups.map((group) => group.source),
    lexiconInfo: lexicon
      ? {
          file: lexicon.file,
          positive_count: lexicon.positiveRules.length,
          negative_count: lexicon.negativeRules.length,
          weak_positive_count: lexicon.weakPositiveRules.size,
        }
      : null,
    allRows: allMergedRows,
    sampledRows,
    sampleSize,
    sentimentCounts,
    topicCounts,
    keywordCounts,
    phraseCounts,
    outputFiles,
  });
  writeFileSync(reportFile, report, 'utf8');

  console.log(JSON.stringify({
    total_deduped_comments: allMergedRows.length,
    analyzed_comments: sampledRows.length,
    sample_size: sampleSize || 'full',
    lexicon: lexicon
      ? {
          file: lexicon.file,
          positive_count: lexicon.positiveRules.length,
          negative_count: lexicon.negativeRules.length,
          weak_positive_count: lexicon.weakPositiveRules.size,
        }
      : 'builtin',
    outputs: outputFiles,
    sentiment: Object.fromEntries(sentimentRows.map((row) => [row.label, row.count])),
  }, null, 2));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}

export {
  classifyComment,
  configureLexicon,
  loadLexicon,
  normalizeText,
  parseLikeCount,
  readCsv,
};
