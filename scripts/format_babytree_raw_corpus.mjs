#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_INPUTS = [
  path.join(ROOT, "outputs/babytree_raw_20260615_150642"),
  path.join(ROOT, "outputs/babytree_raw_20260615_151015"),
];

const POST_COLUMNS = [
  "source_platform",
  "post_id",
  "post_url",
  "source_seed_url",
  "topic_path",
  "title",
  "description",
  "create_time",
  "create_timestamp",
  "province_or_city",
  "reply_count",
  "html_file",
  "html_sha256",
  "html_bytes",
  "fetched_at",
  "is_ad_like",
  "is_editorial_like",
  "raw_anchor_text",
  "author_uid_hash",
];

const SEGMENT_COLUMNS = [
  "segment_id",
  "post_id",
  "post_url",
  "segment_type",
  "floor",
  "content",
  "content_length",
  "create_time",
  "province_or_city",
  "speaker_uid_hash",
  "is_louzhu",
  "is_candidate_realness",
  "filter_reason",
  "html_file",
];

const AD_TERMS = [
  "种草",
  "下单",
  "购买",
  "入手",
  "晒单",
  "旗舰店",
  "官方",
  "产品",
  "推荐",
  "好吸收",
  "营养很充足",
  "致敏性低",
  "爱他美",
  "诺优能",
  "黑金帮",
  "帮宝适",
  "松达",
  "小皮",
  "爱蕴美",
  "美囤",
];

const EDITORIAL_TERMS = [
  "果果园丁",
  "看这一篇",
  "你需要知道",
  "原因是什么",
  "知识",
  "预防",
  "一般来说",
  "需要注意",
  "以下是",
  "建议",
  "因此",
];

const REALNESS_TERMS = [
  "我家",
  "宝宝",
  "宝妈",
  "姐妹",
  "你们",
  "有没有",
  "怎么",
  "咋",
  "正常吗",
  "处理",
  "可以",
  "不要",
  "先",
  "试",
  "看",
  "睡",
  "奶",
  "便便",
  "湿疹",
  "宫缩",
  "哭闹",
];

function parseArgs(argv) {
  const args = { inputs: [], outDir: "", skipXlsx: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--input") {
      args.inputs.push(path.resolve(argv[++i]));
    } else if (arg === "--out-dir") {
      args.outDir = path.resolve(argv[++i]);
    } else if (arg === "--skip-xlsx") {
      args.skipXlsx = true;
    } else if (arg === "--help" || arg === "-h") {
      printHelp();
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (!args.inputs.length) {
    args.inputs = DEFAULT_INPUTS;
  }
  if (!args.outDir) {
    const stamp = new Date()
      .toISOString()
      .replace(/[-:]/g, "")
      .replace(/\..+/, "")
      .replace("T", "_");
    args.outDir = path.join(ROOT, `outputs/babytree_corpus_formatted_${stamp}`);
  }
  return args;
}

function printHelp() {
  console.log(`Usage: node scripts/format_babytree_raw_corpus.mjs [--input DIR ...] [--out-dir DIR] [--skip-xlsx]

Formats authorized Babytree raw samples into posts/segments JSONL and an Excel workbook.
`);
}

async function readJsonl(filePath) {
  const text = await fs.readFile(filePath, "utf8");
  return text
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

async function writeJsonl(filePath, rows) {
  const text = rows.map((row) => JSON.stringify(row, null, 0)).join("\n") + "\n";
  await fs.writeFile(filePath, text, "utf8");
}

function decodeHtml(text) {
  if (!text) return "";
  const named = {
    amp: "&",
    lt: "<",
    gt: ">",
    quot: '"',
    apos: "'",
    nbsp: " ",
    mdash: "-",
  };
  return text
    .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number(code)))
    .replace(/&#x([0-9a-fA-F]+);/g, (_, code) => String.fromCodePoint(parseInt(code, 16)))
    .replace(/&([a-zA-Z]+);/g, (_, name) => named[name] ?? `&${name};`);
}

function stripTags(html) {
  return decodeHtml(
    html
      .replace(/<script\b[\s\S]*?<\/script>/gi, " ")
      .replace(/<style\b[\s\S]*?<\/style>/gi, " ")
      .replace(/<button\b[\s\S]*?<\/button>/gi, " ")
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/p>|<\/div>|<\/li>|<\/h1>|<\/h2>/gi, "\n")
      .replace(/<[^>]+>/g, " "),
  )
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n\s+/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function compactText(text) {
  return (text ?? "")
    .replace(/_宝宝树$/u, "")
    .replace(/\s*展开阅读全文\s*/g, " ")
    .replace(/\s*APP内打开\s*/g, " ")
    .replace(/\s*举报\s*$/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function parsePostId(url, html) {
  const fromUrl = url.match(/topic_(\d+)/);
  if (fromUrl) return fromUrl[1];
  const fromHtml = html.match(/discussId\s*=\s*['"](\d+)['"]/);
  if (fromHtml) return fromHtml[1];
  return crypto.createHash("sha1").update(url).digest("hex").slice(0, 12);
}

function parseTopicPath(url) {
  const { pathname } = new URL(url);
  return pathname.replace(/\/topic_\d+\.html$/, "").replace(/^\/+|\/+$/g, "");
}

function parseReplyCount(anchorText) {
  const match = (anchorText ?? "").match(/(\d+)\s*回复/);
  return match ? Number(match[1]) : null;
}

function sanitizeAnchorText(anchorText, fallbackTitle, replyCount) {
  const title = compactText(fallbackTitle);
  if (!anchorText) {
    return replyCount == null ? title : `${title} ${replyCount} 回复`;
  }
  const replySuffix = replyCount == null ? "" : ` ${replyCount} 回复`;
  return `${title}${replySuffix}`.trim();
}

function stableHash(value) {
  if (!value) return "";
  return crypto.createHash("sha256").update(`babytree:${value}`).digest("hex").slice(0, 16);
}

function firstMatch(text, regex) {
  const match = text.match(regex);
  return match ? match[1] : "";
}

function parseCreateTimestamp(html) {
  const raw = firstMatch(html, /window\.create\s*=\s*\+?['"]?(\d+)['"]?/);
  return raw ? Number(raw) : null;
}

function parseMainUserHash(html) {
  const topArea = html.split(/<section[^>]+model-tpother/i)[0] ?? html;
  const uid = firstMatch(topArea, /home\/\?uid=([^"']+)/);
  return stableHash(uid);
}

function parseMainDateAndLocation(html) {
  const topArea = html.split(/<section[^>]+model-tpother/i)[0] ?? html;
  const dateBlock = firstMatch(topArea, /<li class="detail-date">\s*([\s\S]*?)<\/li>/);
  return parseDateAndLocation(stripTags(dateBlock));
}

function parseDateAndLocation(text) {
  const clean = compactText(text);
  const date = firstMatch(clean, /(\d{4}-\d{2}-\d{2}(?:\s+\d{1,2}:\d{2})?)/);
  const provinceOrCity = clean
    .replace(date, "")
    .replace(/\bIP未知\b/g, "IP未知")
    .trim();
  return { date, provinceOrCity };
}

function inferFlags(text, anchorText = "") {
  const joined = `${text} ${anchorText}`;
  const isAdLike = AD_TERMS.some((term) => joined.includes(term));
  const isEditorialLike =
    EDITORIAL_TERMS.some((term) => joined.includes(term)) ||
    (joined.length > 220 && /宝宝.*(?:需要|可以|建议|一般|因此|注意)/.test(joined));
  return { isAdLike, isEditorialLike };
}

function inferSegmentRealness(content, type, postFlags) {
  const text = compactText(content);
  const reasons = [];
  if (!text) reasons.push("empty");
  if (postFlags.isAdLike || inferFlags(text).isAdLike) reasons.push("ad_like");
  if (postFlags.isEditorialLike || inferFlags(text).isEditorialLike) reasons.push("editorial_like");
  if (text.length > 140) reasons.push("long_text");
  if (text.length < 4) reasons.push("too_short");

  const hasRealSignal =
    /[？?]/.test(text) ||
    REALNESS_TERMS.some((term) => text.includes(term)) ||
    (type === "reply" && text.length <= 60);
  const isCandidate = reasons.length === 0 && hasRealSignal;
  if (isCandidate) reasons.push("candidate_realness");
  if (!isCandidate && reasons.length === 0) reasons.push("weak_realness_signal");
  return { isCandidate, filterReason: reasons.join("|") };
}

function extractTitle(html, fallback) {
  const h1 = firstMatch(html, /<h1[^>]*>([\s\S]*?)<\/h1>/i);
  const title = compactText(stripTags(h1) || fallback);
  return title.replace(/^(新|精)\s*/u, "").trim();
}

function extractMainTextFromDescription(title, description) {
  const cleanTitle = compactText(title);
  const cleanDescription = compactText(description);
  if (!cleanTitle || !cleanDescription || cleanDescription === cleanTitle) return "";
  if (!cleanDescription.startsWith(cleanTitle)) return "";
  const remainder = cleanDescription.slice(cleanTitle.length).trim();
  if (!remainder || remainder === cleanTitle || cleanTitle.includes(remainder)) return "";
  return remainder;
}

function extractReplyBlocks(html) {
  const section = html.match(/<section[^>]+model-tpother[\s\S]*?<\/section>/i)?.[0] ?? "";
  const blocks = section.match(/<div class="detail-box\s*">[\s\S]*?(?=<div class="detail-box\s*">|<\/section>)/gi) ?? [];
  return blocks
    .map((block, index) => {
      const uid = firstMatch(block, /home\/\?uid=([^"']+)/);
      const floorRaw =
        firstMatch(block, /document\.write\(['"]([^'"]*楼)['"]\)/) ||
        stripTags(firstMatch(block, /<li class="detail-floor"[^>]*>([\s\S]*?)<\/li>/));
      const dateRaw = stripTags(firstMatch(block, /<li class="detail-date"[^>]*>([\s\S]*?)<\/li>/));
      const { date, provinceOrCity } = parseDateAndLocation(dateRaw);
      const contentHtml = firstMatch(block, /<div class="detail-content[^"]*"[^>]*>([\s\S]*?)<\/div>/);
      const content = compactText(stripTags(contentHtml));
      return {
        uidHash: stableHash(uid),
        floor: compactText(floorRaw) || `${index + 1}楼`,
        date,
        provinceOrCity,
        content,
      };
    })
    .filter((reply) => reply.content && !reply.content.includes("举报"));
}

function makeSegment({ post, type, floor, content, createTime, provinceOrCity, speakerUidHash, isLouzhu, index }) {
  const flags = {
    isAdLike: Boolean(post.is_ad_like),
    isEditorialLike: Boolean(post.is_editorial_like),
  };
  const { isCandidate, filterReason } = inferSegmentRealness(content, type, flags);
  return {
    segment_id: `${post.post_id}_${String(index).padStart(3, "0")}_${type}`,
    post_id: post.post_id,
    post_url: post.post_url,
    segment_type: type,
    floor,
    content,
    content_length: content.length,
    create_time: createTime ?? "",
    province_or_city: provinceOrCity ?? "",
    speaker_uid_hash: speakerUidHash ?? "",
    is_louzhu: isLouzhu ? 1 : 0,
    is_candidate_realness: isCandidate ? 1 : 0,
    filter_reason: filterReason,
    html_file: post.html_file,
  };
}

async function buildCorpus(inputDirs) {
  const byPostId = new Map();
  const inputStats = [];

  for (const inputDir of inputDirs) {
    const itemsPath = path.join(inputDir, "items.jsonl");
    const items = await readJsonl(itemsPath);
    inputStats.push({ input_dir: inputDir, item_count: items.length });

    for (const item of items) {
      const htmlPath = path.join(inputDir, item.html_file);
      const html = await fs.readFile(htmlPath, "utf8");
      const postId = parsePostId(item.url, html);
      if (byPostId.has(postId)) continue;

      const title = extractTitle(html, item.title ?? "");
      const description = compactText(item.description ?? "");
      const mainText = extractMainTextFromDescription(title, description);
      const replyCount = parseReplyCount(item.anchor_text);
      const { date: createTime, provinceOrCity } = parseMainDateAndLocation(html);
      const createTimestamp = parseCreateTimestamp(html);
      const authorUidHash = parseMainUserHash(html);
      const flags = inferFlags(`${title} ${description}`, item.anchor_text ?? "");

      const post = {
        source_platform: "babytree",
        post_id: postId,
        post_url: item.url,
        source_seed_url: item.source_url ?? "",
        topic_path: parseTopicPath(item.url),
        title,
        description,
        create_time: createTime,
        create_timestamp: createTimestamp,
        province_or_city: provinceOrCity,
        reply_count: replyCount ?? extractReplyBlocks(html).length,
        html_file: `${path.basename(inputDir)}/${item.html_file}`,
        html_sha256: item.html_sha256 ?? "",
        html_bytes: item.html_bytes ?? "",
        fetched_at: item.fetched_at ?? "",
        is_ad_like: flags.isAdLike ? 1 : 0,
        is_editorial_like: flags.isEditorialLike ? 1 : 0,
        raw_anchor_text: sanitizeAnchorText(item.anchor_text, title, replyCount),
        author_uid_hash: authorUidHash,
      };

      const replies = extractReplyBlocks(html);
      byPostId.set(postId, { post, replies, mainText });
    }
  }

  const posts = [];
  const segments = [];
  for (const { post, replies, mainText } of byPostId.values()) {
    posts.push(post);
    let segmentIndex = 1;
    if (post.title) {
      segments.push(
        makeSegment({
          post,
          type: "title",
          floor: "楼主",
          content: post.title,
          createTime: post.create_time,
          provinceOrCity: post.province_or_city,
          speakerUidHash: post.author_uid_hash,
          isLouzhu: true,
          index: segmentIndex++,
        }),
      );
    }
    if (post.description && post.description !== post.title) {
      segments.push(
        makeSegment({
          post,
          type: "description",
          floor: "楼主",
          content: post.description,
          createTime: post.create_time,
          provinceOrCity: post.province_or_city,
          speakerUidHash: post.author_uid_hash,
          isLouzhu: true,
          index: segmentIndex++,
        }),
      );
    }
    if (mainText) {
      segments.push(
        makeSegment({
          post,
          type: "main_text",
          floor: "楼主",
          content: mainText,
          createTime: post.create_time,
          provinceOrCity: post.province_or_city,
          speakerUidHash: post.author_uid_hash,
          isLouzhu: true,
          index: segmentIndex++,
        }),
      );
    }
    for (const reply of replies) {
      segments.push(
        makeSegment({
          post,
          type: "reply",
          floor: reply.floor,
          content: reply.content,
          createTime: reply.date,
          provinceOrCity: reply.provinceOrCity,
          speakerUidHash: reply.uidHash,
          isLouzhu: false,
          index: segmentIndex++,
        }),
      );
    }
  }

  return { posts, segments, inputStats };
}

function rowsFor(columns, rows) {
  return [columns, ...rows.map((row) => columns.map((column) => row[column] ?? ""))];
}

function colName(index) {
  let n = index + 1;
  let name = "";
  while (n > 0) {
    const mod = (n - 1) % 26;
    name = String.fromCharCode(65 + mod) + name;
    n = Math.floor((n - mod) / 26);
  }
  return name;
}

function addSheet(workbook, sheetName, columns, rows, tableName) {
  const sheet = workbook.worksheets.add(sheetName);
  const matrix = rowsFor(columns, rows);
  const range = sheet.getRangeByIndexes(0, 0, matrix.length, columns.length);
  range.values = matrix;
  const header = sheet.getRangeByIndexes(0, 0, 1, columns.length);
  header.format = {
    fill: "#1F4E79",
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
  };
  range.format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
  range.format.wrapText = true;
  sheet.freezePanes.freezeRows(1);

  const lastCol = colName(columns.length - 1);
  sheet.tables.add(`A1:${lastCol}${matrix.length}`, true, tableName).style = "TableStyleMedium2";
  return sheet;
}

function formatWorkbook(workbook, postsSheet, segmentsSheet, summarySheet, postCount, segmentCount) {
  summarySheet.getRange("A1:D1").format = {
    fill: "#1F4E79",
    font: { bold: true, color: "#FFFFFF" },
  };
  summarySheet.getRange("A1:D7").format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
  summarySheet.getRange("A1:D7").format.columnWidthPx = 180;
  summarySheet.getRange("B2:B7").format.columnWidthPx = 120;

  postsSheet.getRange("A:S").format.columnWidthPx = 120;
  postsSheet.getRange("F:G").format.columnWidthPx = 300;
  postsSheet.getRange("L:M").format.columnWidthPx = 220;
  postsSheet.getRange("R:R").format.columnWidthPx = 260;
  postsSheet.getRange("A1:S1").format.rowHeightPx = 36;

  segmentsSheet.getRange("A:N").format.columnWidthPx = 120;
  segmentsSheet.getRange("F:F").format.columnWidthPx = 460;
  segmentsSheet.getRange("M:M").format.columnWidthPx = 220;
  segmentsSheet.getRange("A1:N1").format.rowHeightPx = 36;
  if (postCount === 0 || segmentCount === 0) {
    throw new Error("No corpus rows generated.");
  }
}

async function buildWorkbook(outDir, posts, segments, manifest) {
  const workbook = Workbook.create();
  const summary = workbook.worksheets.add("summary");
  summary.getRange("A1:D7").values = [
    ["metric", "value", "note", "created_at"],
    ["posts", posts.length, "去重后帖子数", manifest.created_at],
    ["segments", segments.length, "标题/描述/回帖片段数", ""],
    ["candidate_realness", segments.filter((row) => row.is_candidate_realness === 1).length, "真人感候选片段", ""],
    ["ad_like_posts", posts.filter((row) => row.is_ad_like === 1).length, "疑似广告/种草帖", ""],
    ["editorial_like_posts", posts.filter((row) => row.is_editorial_like === 1).length, "疑似园丁/科普帖", ""],
    ["input_dirs", manifest.inputs.length, "原始采样目录数量", ""],
  ];

  const postsSheet = addSheet(workbook, "posts", POST_COLUMNS, posts, "PostsTable");
  const segmentsSheet = addSheet(workbook, "segments", SEGMENT_COLUMNS, segments, "SegmentsTable");
  formatWorkbook(workbook, postsSheet, segmentsSheet, summary, posts.length, segments.length);

  await workbook.inspect({
    kind: "table",
    range: "summary!A1:D7",
    include: "values,formulas",
    tableMaxRows: 8,
    tableMaxCols: 4,
  });
  await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 300 },
    summary: "final formula error scan",
  });
  await workbook.render({ sheetName: "summary", autoCrop: "all", scale: 1, format: "png" });
  await workbook.render({ sheetName: "segments", range: "A1:N12", scale: 1, format: "png" });

  const xlsx = await SpreadsheetFile.exportXlsx(workbook);
  const xlsxPath = path.join(outDir, "babytree_corpus.xlsx");
  await xlsx.save(xlsxPath);
  await fs.rm(`${xlsxPath}.inspect.ndjson`, { force: true });
  return xlsxPath;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const { posts, segments, inputStats } = await buildCorpus(args.inputs);
  await fs.mkdir(args.outDir, { recursive: true });

  const manifest = {
    created_at: new Date().toISOString(),
    source: "babytree_raw_samples",
    inputs: inputStats,
    post_count: posts.length,
    segment_count: segments.length,
    candidate_realness_count: segments.filter((row) => row.is_candidate_realness === 1).length,
    ad_like_post_count: posts.filter((row) => row.is_ad_like === 1).length,
    editorial_like_post_count: posts.filter((row) => row.is_editorial_like === 1).length,
    weak_deidentification: {
      exported_usernames: false,
      exported_profile_urls: false,
      exported_avatar_urls: false,
      uid_strategy: "sha256(babytree:<uid>) first 16 hex chars",
    },
  };

  await writeJsonl(path.join(args.outDir, "posts.jsonl"), posts);
  await writeJsonl(path.join(args.outDir, "segments.jsonl"), segments);
  await fs.writeFile(path.join(args.outDir, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n", "utf8");

  let xlsxPath = "";
  if (!args.skipXlsx) {
    xlsxPath = await buildWorkbook(args.outDir, posts, segments, manifest);
  }

  console.log(
    JSON.stringify(
      {
        out_dir: args.outDir,
        posts: posts.length,
        segments: segments.length,
        candidate_realness: manifest.candidate_realness_count,
        xlsx: xlsxPath,
      },
      null,
      2,
    ),
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
