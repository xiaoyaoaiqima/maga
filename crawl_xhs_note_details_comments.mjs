#!/usr/bin/env node

import { execFile } from "node:child_process";
import { appendFile, readFile, stat, writeFile } from "node:fs/promises";

const API_ROOT = "https://api.tikhub.io/api/v1/xiaohongshu";
const DEFAULT_KEYWORD = "a2至初";
const DEFAULT_OUTPUT = "xhs_note_details_comments.csv";
const DEFAULT_KEYWORD_EXCEL_SHEET = "调整后综合排序";
const DEFAULT_BATTLE_CATEGORY = "品类信任教育战场";
const DEFAULT_KEYWORD_LIMIT = 20;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function parseArgs(argv) {
  const args = {
    keyword: DEFAULT_KEYWORD,
    output: DEFAULT_OUTPUT,
    full: false,
    limit: 50,
    testNotes: 2,
    searchPageSize: 20,
    delayMs: 800,
    detailCommentLimit: 20,
    maxCommentPagesPerNote: 2,
    maxSubCommentPagesPerRoot: 1,
    fast: false,
    includeSubComments: false,
    onlySubComments: false,
    maxCommentsPerNote: 0,
    concurrency: 1,
    sort: "general",
    noteType: "不限",
    timeFilter: "不限",
    keywordExcel: "",
    keywordExcelSheet: DEFAULT_KEYWORD_EXCEL_SHEET,
    battleCategory: DEFAULT_BATTLE_CATEGORY,
    keywordLimit: DEFAULT_KEYWORD_LIMIT,
    keywordColumn: "搜索词",
    battleColumn: "战场分类",
    sourceRankColumn: "综合排序",
    printKeywords: false,
    printProgress: false,
    resume: false,
    stateOutput: "",
    skipSuccessState: "",
    seedCsv: "",
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];

    if (arg === "--full") args.full = true;
    else if (arg === "--keyword") args.keyword = requiredValue(arg, next, ++i);
    else if (arg === "--output") args.output = requiredValue(arg, next, ++i);
    else if (arg === "--limit") args.limit = parsePositiveInt(arg, next, ++i);
    else if (arg === "--test-notes") args.testNotes = parsePositiveInt(arg, next, ++i);
    else if (arg === "--search-page-size") args.searchPageSize = parsePositiveInt(arg, next, ++i);
    else if (arg === "--delay-ms") args.delayMs = parseNonNegativeInt(arg, next, ++i);
    else if (arg === "--detail-comment-limit") args.detailCommentLimit = parseNonNegativeInt(arg, next, ++i);
    else if (arg === "--max-comment-pages-per-note") args.maxCommentPagesPerNote = parseNonNegativeInt(arg, next, ++i);
    else if (arg === "--max-sub-comment-pages-per-root") args.maxSubCommentPagesPerRoot = parseNonNegativeInt(arg, next, ++i);
    else if (arg === "--fast") args.fast = true;
    else if (arg === "--include-sub-comments") args.includeSubComments = true;
    else if (arg === "--only-sub-comments") args.onlySubComments = true;
    else if (arg === "--max-comments-per-note") args.maxCommentsPerNote = parseNonNegativeInt(arg, next, ++i);
    else if (arg === "--concurrency") args.concurrency = parsePositiveInt(arg, next, ++i);
    else if (arg === "--sort") args.sort = requiredValue(arg, next, ++i);
    else if (arg === "--note-type") args.noteType = requiredValue(arg, next, ++i);
    else if (arg === "--time-filter") args.timeFilter = requiredValue(arg, next, ++i);
    else if (arg === "--keyword-excel" || arg === "--excel") args.keywordExcel = requiredValue(arg, next, ++i);
    else if (arg === "--keyword-excel-sheet" || arg === "--sheet") args.keywordExcelSheet = requiredValue(arg, next, ++i);
    else if (arg === "--battle-category") args.battleCategory = requiredValue(arg, next, ++i);
    else if (arg === "--keyword-limit") args.keywordLimit = parsePositiveInt(arg, next, ++i);
    else if (arg === "--keyword-column") args.keywordColumn = requiredValue(arg, next, ++i);
    else if (arg === "--battle-column") args.battleColumn = requiredValue(arg, next, ++i);
    else if (arg === "--source-rank-column") args.sourceRankColumn = requiredValue(arg, next, ++i);
    else if (arg === "--print-keywords") args.printKeywords = true;
    else if (arg === "--print-progress") args.printProgress = true;
    else if (arg === "--resume") args.resume = true;
    else if (arg === "--state-output") args.stateOutput = requiredValue(arg, next, ++i);
    else if (arg === "--skip-success-state") args.skipSuccessState = requiredValue(arg, next, ++i);
    else if (arg === "--seed-csv") args.seedCsv = requiredValue(arg, next, ++i);
    else if (arg === "--help" || arg === "-h") {
      printHelp();
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return args;
}

function requiredValue(flag, value) {
  if (!value || value.startsWith("--")) throw new Error(`${flag} requires a value`);
  return value;
}

function parsePositiveInt(flag, value) {
  const parsed = Number.parseInt(requiredValue(flag, value), 10);
  if (!Number.isInteger(parsed) || parsed <= 0) throw new Error(`${flag} must be a positive integer`);
  return parsed;
}

function parseNonNegativeInt(flag, value) {
  const parsed = Number.parseInt(requiredValue(flag, value), 10);
  if (!Number.isInteger(parsed) || parsed < 0) throw new Error(`${flag} must be a non-negative integer`);
  return parsed;
}

function printHelp() {
  console.log(`
Usage:
  TIKHUB_AUTHORIZATION="Bearer <token>" node crawl_xhs_note_details_comments.mjs --keyword "a2至初"
  node crawl_xhs_note_details_comments.mjs --keyword "a2至初" --full --limit 50

Output:
  One CSV row per root comment or reply, with note detail fields repeated on every row.

Options:
  --keyword <text>                    Search keyword. Default: ${DEFAULT_KEYWORD}
  --output <path>                     CSV output path. Default: ${DEFAULT_OUTPUT}
  --full                              Fetch --limit notes. Without this flag, fetch --test-notes notes.
  --limit <number>                    Note limit in full mode. Default: 50
  --test-notes <number>               Note limit in test mode. Default: 2
  --search-page-size <number>         Search page size assumption. Default: 20
  --delay-ms <number>                 Delay between API calls. Default: 800
  --fast                              Fast mode: skip note detail and fetch App-V2 first-page comments only.
  --detail-comment-limit <n>          Fast-mode comment cap from App-V2 first page. Default: 20
  --max-comment-pages-per-note <n>    Main comment page cap. 0 means no cap. Default: 2
  --max-sub-comment-pages-per-root <n>
                                      Sub-comment page cap per root comment. 0 means no cap. Default: 1
                                      Ignored unless --include-sub-comments is set.
  --include-sub-comments              Include embedded sub-comments and fetch extra sub-comment pages.
                                      Omit this flag to crawl root comments only.
  --only-sub-comments                 Only write sub-comments/replies. Requires --include-sub-comments.
  --max-comments-per-note <n>         Debug cap. 0 means no cap.
  --concurrency <number>              Notes to fetch in parallel. Default: 1
  --sort <value>                      App-V2 search sort_type. Default: general
  --note-type <value>                 App-V2 search note_type. Default: 不限
  --time-filter <value>               App-V2 search time_filter. Default: 不限
  --keyword-excel <path>              Read batch keywords from an .xlsx file.
  --keyword-excel-sheet <name>        Sheet for batch keywords. Default: ${DEFAULT_KEYWORD_EXCEL_SHEET}
  --battle-category <text>            Battle category filter. Default: ${DEFAULT_BATTLE_CATEGORY}
  --keyword-limit <number>            Keyword limit in Excel batch mode. Default: ${DEFAULT_KEYWORD_LIMIT}
  --keyword-column <name>             Keyword column in Excel. Default: 搜索词
  --battle-column <name>              Battle category column in Excel. Default: 战场分类
  --source-rank-column <name>         Source rank column in Excel. Default: 综合排序
  --print-keywords                    Print resolved keywords and exit without API calls.
  --resume                            Resume this details run and skip already attempted notes.
  --print-progress                    Print detected progress and exit without API calls.
  --state-output <path>               Details progress JSONL path. Default: <output>.state.jsonl
  --skip-success-state <path>         Existing JSONL state whose done notes should be skipped.
  --seed-csv <path>                   Read notes from an existing comment CSV and skip search.
                                      Without --full, only the first --test-notes unique notes are used.
`);
}

async function loadDotEnv(path = ".env") {
  let text = "";
  try {
    text = await readFile(path, "utf8");
  } catch (error) {
    if (error.code === "ENOENT") return;
    throw error;
  }

  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;

    const separatorIndex = trimmed.indexOf("=");
    if (separatorIndex === -1) continue;

    const key = trimmed.slice(0, separatorIndex).trim();
    let value = trimmed.slice(separatorIndex + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (key && process.env[key] === undefined) process.env[key] = value;
  }
}

function execFileAsync(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    execFile(command, args, { maxBuffer: 10 * 1024 * 1024, ...options }, (error, stdout, stderr) => {
      if (error) {
        error.stdout = stdout;
        error.stderr = stderr;
        reject(error);
        return;
      }
      resolve({ stdout, stderr });
    });
  });
}

async function resolveKeywordItems(args) {
  if (!args.keywordExcel) {
    return [
      {
        keyword: args.keyword,
        keyword_rank: 1,
        battle_category: "",
        source_rank: "",
        sheet_row: "",
      },
    ];
  }

  return readKeywordsFromExcel({
    excelPath: args.keywordExcel,
    sheetName: args.keywordExcelSheet,
    battleCategory: args.battleCategory,
    keywordLimit: args.keywordLimit,
    keywordColumn: args.keywordColumn,
    battleColumn: args.battleColumn,
    sourceRankColumn: args.sourceRankColumn,
  });
}

async function readKeywordsFromExcel({
  excelPath,
  sheetName,
  battleCategory,
  keywordLimit,
  keywordColumn,
  battleColumn,
  sourceRankColumn,
}) {
  // 复用本地 openpyxl 读 xlsx，避免给采集脚本再引入 npm 依赖。
  const pythonCode = String.raw`
import json
import sys
from openpyxl import load_workbook

path, sheet_name, battle_category, keyword_limit, keyword_column, battle_column, source_rank_column = sys.argv[1:]
keyword_limit = int(keyword_limit)

def fail(message, **extra):
    payload = {"error": message}
    payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(2)

workbook = load_workbook(path, read_only=True, data_only=True)
if sheet_name not in workbook.sheetnames:
    fail(f"Sheet not found: {sheet_name}", sheets=workbook.sheetnames)

worksheet = workbook[sheet_name]
rows = worksheet.iter_rows(values_only=True)
try:
    headers = [str(value).strip() if value is not None else "" for value in next(rows)]
except StopIteration:
    fail(f"Sheet is empty: {sheet_name}")

def column_index(column_name, required=True):
    try:
        return headers.index(column_name)
    except ValueError:
        if required:
            fail(f"Column not found: {column_name}", headers=headers)
        return -1

keyword_index = column_index(keyword_column)
battle_index = column_index(battle_column)
source_rank_index = column_index(source_rank_column, required=False) if source_rank_column else -1

items = []
seen_keywords = set()
for sheet_row, row in enumerate(rows, start=2):
    battle_value = row[battle_index] if battle_index < len(row) else None
    if str(battle_value).strip() != battle_category:
        continue

    keyword_value = row[keyword_index] if keyword_index < len(row) else None
    keyword = str(keyword_value).strip() if keyword_value is not None else ""
    if not keyword or keyword in seen_keywords:
        continue

    seen_keywords.add(keyword)
    source_rank = row[source_rank_index] if source_rank_index >= 0 and source_rank_index < len(row) else ""
    items.append({
        "keyword": keyword,
        "keyword_rank": len(items) + 1,
        "battle_category": battle_category,
        "source_rank": source_rank,
        "sheet_row": sheet_row,
    })
    if len(items) >= keyword_limit:
        break

print(json.dumps({"keywords": items, "sheet": sheet_name}, ensure_ascii=False))
`;

  let stdout;
  try {
    ({ stdout } = await execFileAsync("python3", [
      "-c",
      pythonCode,
      excelPath,
      sheetName,
      battleCategory,
      String(keywordLimit),
      keywordColumn,
      battleColumn,
      sourceRankColumn,
    ]));
  } catch (error) {
    const message = [error.stdout, error.stderr, error.message].filter(Boolean).join("\n").trim();
    throw new Error(`Failed to read Excel keywords from ${excelPath}: ${message}`);
  }

  let payload;
  try {
    payload = JSON.parse(stdout);
  } catch (error) {
    throw new Error(`Failed to parse Excel keyword output: ${error.message}\n${stdout.slice(0, 800)}`);
  }

  if (payload.error) throw new Error(payload.error);
  if (!Array.isArray(payload.keywords) || payload.keywords.length === 0) {
    throw new Error(`No keywords found for battle category "${battleCategory}" in sheet "${sheetName}".`);
  }

  return payload.keywords;
}

function parseCsv(text) {
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);

  const rows = [];
  let row = [];
  let field = "";
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
    } else if (char === "," && !inQuotes) {
      row.push(field);
      field = "";
    } else if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && next === "\n") i += 1;
      row.push(field);
      if (row.some((value) => value !== "")) rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }

  if (field || row.length > 0) {
    row.push(field);
    if (row.some((value) => value !== "")) rows.push(row);
  }

  return rows;
}

function csvRowsToObjects(rows) {
  const headers = rows[0] || [];
  return rows.slice(1).map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index] || ""])));
}

function toNumberOrString(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : String(value || "");
}

async function readSeedNotesFromCsv(seedCsv, { full, testNotes }) {
  const rows = csvRowsToObjects(parseCsv(await readFile(seedCsv, "utf8")));
  const notes = [];
  const seen = new Set();
  const maxNotes = full ? Infinity : testNotes;

  for (const row of rows) {
    const keyword = String(row.keyword || "").trim();
    const noteId = String(row.note_id || "").trim();
    if (!keyword || !noteId) continue;

    const dedupeKey = `${keyword}::${noteId}`;
    if (seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);

    const xsecToken = row.xsec_token || extractXsecToken(row.note_url);
    notes.push({
      keyword_rank: toNumberOrString(row.keyword_rank),
      keyword_source_rank: row.keyword_source_rank || "",
      keyword_sheet_row: row.keyword_sheet_row || "",
      battle_category: row.battle_category || "",
      keyword,
      search_rank: toNumberOrString(row.search_rank),
      note_id: noteId,
      source_note_id: noteId,
      xsec_token: xsecToken,
      note_url: row.note_url || buildNoteUrl(noteId, xsecToken),
      note_title: row.note_title || "",
      note_author_id: row.note_author_id || "",
      note_author_name: row.note_author_name || "",
      note_desc: row.note_desc || "",
      note_type: row.note_type || "",
      note_likes: row.note_likes || "",
      note_comments_count: row.note_comments_count || "",
      note_collected_count: row.note_collected_count || "",
      note_shared_count: row.note_shared_count || "",
      note_publish_time: row.note_publish_time || "",
      note_ip_location: row.note_ip_location || "",
      note_image_url: row.note_image_url || "",
      detail_status: "seed_csv",
      raw_search_note: {},
    });

    if (notes.length >= maxNotes) break;
  }

  if (notes.length === 0) throw new Error(`No seed notes found in ${seedCsv}. Expected keyword and note_id columns.`);
  return notes;
}

function groupSeedNotesByKeyword(seedNotes) {
  const grouped = new Map();
  for (const note of seedNotes) {
    if (!grouped.has(note.keyword)) grouped.set(note.keyword, []);
    grouped.get(note.keyword).push(note);
  }
  return grouped;
}

function keywordItemsFromSeedNotes(seedNotes) {
  const byKeyword = new Map();
  for (const note of seedNotes) {
    if (byKeyword.has(note.keyword)) continue;
    byKeyword.set(note.keyword, {
      keyword: note.keyword,
      keyword_rank: note.keyword_rank || byKeyword.size + 1,
      battle_category: note.battle_category || "",
      source_rank: note.keyword_source_rank || "",
      sheet_row: note.keyword_sheet_row || "",
    });
  }
  return [...byKeyword.values()].sort((a, b) => Number(a.keyword_rank) - Number(b.keyword_rank));
}

function getStateOutputPath(args) {
  return args.stateOutput || `${args.output}.state.jsonl`;
}

function createProgress() {
  return {
    doneByKeyword: new Map(),
    failedByKeyword: new Map(),
    doneCount: 0,
    failedCount: 0,
  };
}

function addNoteToMap(map, keyword, noteId) {
  if (!keyword || !noteId) return false;
  let noteIds = map.get(keyword);
  if (!noteIds) {
    noteIds = new Set();
    map.set(keyword, noteIds);
  }
  const before = noteIds.size;
  noteIds.add(noteId);
  return noteIds.size > before;
}

function addDoneNote(progress, keyword, noteId) {
  return addNoteToMap(progress.doneByKeyword, keyword, noteId);
}

function addFailedNote(progress, keyword, noteId) {
  return addNoteToMap(progress.failedByKeyword, keyword, noteId);
}

function getDoneNoteIds(progress, keyword) {
  return progress.doneByKeyword.get(keyword) || new Set();
}

function getFailedNoteIds(progress, keyword) {
  return progress.failedByKeyword.get(keyword) || new Set();
}

function unionSets(...sets) {
  return new Set(sets.flatMap((set) => [...set]));
}

async function loadProgressFromState(statePath, { includeFailed = true } = {}) {
  const progress = createProgress();
  if (!statePath) return progress;

  let text = "";
  try {
    text = await readFile(statePath, "utf8");
  } catch (error) {
    if (error.code === "ENOENT") return progress;
    throw error;
  }

  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    let item;
    try {
      item = JSON.parse(trimmed);
    } catch {
      continue;
    }

    if (item.status === "done") {
      const added = addDoneNote(progress, item.keyword, item.note_id);
      if (item.source_note_id && item.source_note_id !== item.note_id) addDoneNote(progress, item.keyword, item.source_note_id);
      if (added) progress.doneCount += 1;
    } else if (includeFailed && item.status === "failed") {
      const added = addFailedNote(progress, item.keyword, item.note_id);
      if (item.source_note_id && item.source_note_id !== item.note_id) addFailedNote(progress, item.keyword, item.source_note_id);
      if (added) progress.failedCount += 1;
    }
  }

  return progress;
}

async function fileHasContent(path) {
  try {
    const info = await stat(path);
    return info.size > 0;
  } catch (error) {
    if (error.code === "ENOENT") return false;
    throw error;
  }
}

function printProgressReport(keywordItems, currentProgress, skipSuccessProgress, targetCount) {
  for (const item of keywordItems) {
    const externalDone = getDoneNoteIds(skipSuccessProgress, item.keyword);
    const currentDone = getDoneNoteIds(currentProgress, item.keyword);
    const currentFailed = getFailedNoteIds(currentProgress, item.keyword);
    const skipDone = unionSets(externalDone, currentDone);
    const attempted = unionSets(skipDone, currentFailed);
    console.log(
      `${item.keyword_rank}. ${item.keyword}: historical_done=${externalDone.size}, detail_done=${currentDone.size}, detail_failed=${currentFailed.size}, skip_or_attempted=${attempted.size}, remaining=${Math.max(0, targetCount - attempted.size)}, target=${targetCount}`,
    );
  }
}

function printSeedProgressReport(keywordItems, seedNotesByKeyword, currentProgress, skipSuccessProgress) {
  for (const item of keywordItems) {
    const seedCount = seedNotesByKeyword.get(item.keyword)?.length || 0;
    const externalDone = getDoneNoteIds(skipSuccessProgress, item.keyword);
    const currentDone = getDoneNoteIds(currentProgress, item.keyword);
    const currentFailed = getFailedNoteIds(currentProgress, item.keyword);
    const skipDone = unionSets(externalDone, currentDone);
    const attempted = unionSets(skipDone, currentFailed);
    console.log(
      `${item.keyword_rank}. ${item.keyword}: seed=${seedCount}, historical_done=${externalDone.size}, detail_done=${currentDone.size}, detail_failed=${currentFailed.size}, skip_or_attempted=${attempted.size}, remaining=${Math.max(0, seedCount - attempted.size)}`,
    );
  }
}

async function writeNoteState(statePath, note, status, commentCount, errorMessage = "") {
  const payload = {
    status,
    keyword: note.keyword,
    keyword_rank: note.keyword_rank,
    keyword_source_rank: note.keyword_source_rank,
    battle_category: note.battle_category,
    search_rank: note.search_rank,
    source_note_id: note.source_note_id || "",
    note_id: note.note_id,
    xsec_token: note.xsec_token || "",
    note_url: note.note_url || "",
    note_title: note.note_title,
    note_author_id: note.note_author_id || "",
    note_author_name: note.note_author_name || "",
    keyword_sheet_row: note.keyword_sheet_row || "",
    detail_status: note.detail_status || "",
    comment_count: commentCount,
    error: errorMessage,
    finished_at: new Date().toISOString(),
  };
  await appendFile(statePath, `${JSON.stringify(payload)}\n`, "utf8");
}

function getAuthorization() {
  const authorization = process.env.TIKHUB_AUTHORIZATION;
  if (authorization) return normalizeAuthorization(authorization);

  const token = process.env.TIKHUB_BEARER_TOKEN || process.env.TIKHUB_TOKEN;
  if (token) return normalizeAuthorization(token);

  throw new Error(
    'Missing auth. Set TIKHUB_AUTHORIZATION="Bearer <token>" or TIKHUB_BEARER_TOKEN="<token>".',
  );
}

function normalizeAuthorization(value) {
  const trimmed = value.trim();
  return trimmed.toLowerCase().startsWith("bearer ") ? trimmed : `Bearer ${trimmed}`;
}

async function apiGet(path, query, authorization) {
  const url = new URL(`${API_ROOT}/${path}`);
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
  }

  let lastError;
  const maxAttempts = 4;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      const response = await fetch(url, {
        method: "GET",
        headers: { Authorization: authorization },
        redirect: "follow",
      });

      const text = await response.text();
      let json;
      try {
        json = text ? JSON.parse(text) : null;
      } catch {
        json = null;
      }

      if (!response.ok) {
        const retryable400 =
          response.status === 400 && /请求失败|请重试|Request failed|Please retry/i.test(text);
        const retryable =
          response.status === 408 || response.status === 429 || response.status >= 500 || retryable400;
        const error = new Error(`HTTP ${response.status} ${response.statusText} for ${redactUrl(url)}\n${summarizeApiError(text)}`);
        if (!retryable) throw Object.assign(error, { nonRetryable: true });
        const attemptLimit = retryable400 ? 2 : maxAttempts;
        if (attempt >= attemptLimit) throw Object.assign(error, { stopRetry: true });
        lastError = error;
      } else if (!json) {
        throw new Error(`Expected JSON response for ${redactUrl(url)}, got:\n${text.slice(0, 800)}`);
      } else {
        return { url: url.toString(), json };
      }
    } catch (error) {
      lastError = error;
      if (error.nonRetryable || error.stopRetry || attempt === maxAttempts) throw error;
    }

    const waitMs = 1000 * attempt * attempt;
    console.warn(`Retrying ${redactUrl(url)} after error: ${lastError.message.split("\n")[0]}`);
    await sleep(waitMs);
  }

  throw lastError;
}

function summarizeApiError(text) {
  const redacted = redactSecrets(text);
  try {
    const json = JSON.parse(redacted);
    const detail = json?.detail || json;
    const parts = [
      detail?.message_zh,
      detail?.message,
      detail?.router ? `router: ${detail.router}` : "",
      detail?.request_id ? `request_id: ${detail.request_id}` : "",
    ].filter(Boolean);
    if (parts.length > 0) return parts.join("\n");
  } catch {
    // Fall through to a short redacted snippet.
  }
  return redacted.slice(0, 800);
}

function redactSecrets(text) {
  return text.replace(/("Authorization"\s*:\s*")([^"]+)(")/gi, "$1[REDACTED]$3");
}

function redactUrl(url) {
  const safeUrl = new URL(url.toString());
  if (safeUrl.searchParams.has("xsec_token")) safeUrl.searchParams.set("xsec_token", "[REDACTED]");
  return safeUrl.toString();
}

function firstArrayAtAnyPath(root, candidatePaths) {
  for (const path of candidatePaths) {
    const value = getPath(root, path);
    if (Array.isArray(value)) return value;
  }
  return null;
}

function getPath(root, path) {
  return path.split(".").reduce((value, key) => {
    if (value === undefined || value === null) return undefined;
    return value[key];
  }, root);
}

function deepFindArray(root, keyNames) {
  const queue = [root];
  const seen = new Set();

  while (queue.length > 0) {
    const current = queue.shift();
    if (!current || typeof current !== "object" || seen.has(current)) continue;
    seen.add(current);

    for (const [key, value] of Object.entries(current)) {
      if (keyNames.includes(key) && Array.isArray(value)) return value;
      if (value && typeof value === "object") queue.push(value);
    }
  }

  return null;
}

function extractSearchItems(json) {
  return (
    firstArrayAtAnyPath(json, [
      "data.items",
      "data.notes",
      "data.note_list",
      "data.feeds",
      "data.list",
      "data.data.items",
      "data.data.notes",
      "data.data.note_list",
      "items",
      "notes",
      "note_list",
    ]) || deepFindArray(json, ["items", "notes", "note_list", "feeds", "list"])
  );
}

function extractDetailNote(json) {
  const noteList =
    firstArrayAtAnyPath(json, [
      "data.data.0.note_list",
      "data.data.data.0.note_list",
      "data.note_list",
      "data.data.note_list",
      "note_list",
    ]) || deepFindArray(json, ["note_list"]);

  if (Array.isArray(noteList) && noteList.length > 0) return noteList[0];

  const direct = getPath(json, "data.data.note") || getPath(json, "data.note") || getPath(json, "note");
  return direct && typeof direct === "object" ? direct : null;
}

function extractCommentItems(json) {
  return (
    firstArrayAtAnyPath(json, [
      "data.comments",
      "data.comment_list",
      "data.commentList",
      "data.data.comments",
      "data.data.comment_list",
      "comments",
      "comment_list",
    ]) || deepFindArray(json, ["comments", "comment_list", "commentList"])
  );
}

function extractSearchNote(raw, index) {
  const source = raw?.note_card || raw?.note || raw?.model || raw;
  const user = source?.user || source?.user_info || source?.userInfo || raw?.user || raw?.user_info || raw?.userInfo || {};
  const noteId =
    pick(source, ["note_id", "id", "noteId"]) ||
    pick(raw, ["note_id", "id", "noteId"]) ||
    pick(source?.note, ["id", "note_id"]);
  const xsecToken =
    pick(source, ["xsec_token", "xsecToken"]) ||
    pick(raw, ["xsec_token", "xsecToken"]) ||
    pick(source?.note, ["xsec_token", "xsecToken"]);

  return {
    search_rank: index + 1,
    note_id: noteId || "",
    source_note_id: noteId || "",
    xsec_token: xsecToken || "",
    note_url: buildNoteUrl(noteId, xsecToken),
    note_title: pick(source, ["title", "display_title", "desc"]) || "",
    note_author_id: pick(user, ["user_id", "userId", "id", "userid"]) || "",
    note_author_name: pick(user, ["nickname", "nick_name", "nickName", "name"]) || "",
    raw_search_note: raw,
  };
}

function mergeDetailIntoNote(note, detailRaw) {
  if (!detailRaw) return { ...note, detail_status: "missing" };

  const user = detailRaw?.user || detailRaw?.user_info || detailRaw?.userInfo || {};
  const shareLink = detailRaw?.share_info?.link || "";
  const shareXsecToken = extractXsecToken(shareLink);
  const images = detailRaw?.images_list || detailRaw?.image_list || detailRaw?.images || [];

  return {
    ...note,
    detail_status: "ok",
    source_note_id: note.source_note_id || note.note_id,
    note_id: pick(detailRaw, ["id", "note_id", "noteId"]) || note.note_id,
    xsec_token: shareXsecToken || note.xsec_token,
    note_url: shareLink || note.note_url,
    note_title: pick(detailRaw, ["title", "display_title"]) || note.note_title,
    note_author_id: pick(user, ["user_id", "userId", "id", "userid"]) || note.note_author_id,
    note_author_name: pick(user, ["nickname", "nick_name", "nickName", "name"]) || note.note_author_name,
    note_type: pick(detailRaw, ["type", "note_type", "noteType", "model_type"]) || "",
    note_desc: pick(detailRaw, ["desc", "description"]) || "",
    note_likes: pick(detailRaw, ["liked_count", "likedCount", "like_count", "likeCount"]) || "",
    note_comments_count: pick(detailRaw, ["comments_count", "comment_count", "commentsCount", "commentCount"]) || "",
    note_collected_count: pick(detailRaw, ["collected_count", "collectedCount", "collect_count", "collectCount"]) || "",
    note_shared_count: pick(detailRaw, ["shared_count", "sharedCount", "share_count", "shareCount"]) || "",
    note_publish_time: normalizeTime(pick(detailRaw, ["time", "timestamp", "create_time", "createTime", "created_at", "createdAt"])),
    note_ip_location: pick(detailRaw, ["ip_location", "ipLocation"]) || "",
    note_image_url: firstImageUrl(images) || detailRaw?.share_info?.image || "",
    raw_note_json: JSON.stringify(detailRaw),
  };
}

function firstImageUrl(images) {
  if (!Array.isArray(images)) return "";
  for (const image of images) {
    const url =
      image?.url ||
      image?.url_default ||
      image?.origin_url ||
      image?.info_list?.[0]?.url ||
      image?.live_photo_file_id;
    if (url) return url;
  }
  return "";
}

function extractXsecToken(url) {
  if (!url) return "";
  try {
    return new URL(url).searchParams.get("xsec_token") || "";
  } catch {
    return "";
  }
}

function buildNoteUrl(noteId, xsecToken) {
  if (!noteId) return "";
  const url = new URL(`https://www.xiaohongshu.com/explore/${noteId}`);
  if (xsecToken) url.searchParams.set("xsec_token", xsecToken);
  url.searchParams.set("xsec_source", "pc_search");
  return url.toString();
}

function makeCommentRow(raw, note, index) {
  const user = raw?.user_info || raw?.userInfo || raw?.user || raw?.author || {};
  const parentComment = raw?.targetComment || {};
  const parentCommentId =
    pick(raw, ["parent_comment_id", "parentCommentId", "parent_id", "parentId"]) ||
    pick(parentComment, ["id", "comment_id", "commentId"]) ||
    "";

  return {
    keyword_rank: note.keyword_rank || "",
    keyword_source_rank: note.keyword_source_rank || "",
    keyword_sheet_row: note.keyword_sheet_row || "",
    battle_category: note.battle_category || "",
    keyword: note.keyword,
    search_rank: note.search_rank,
    note_id: note.note_id,
    note_url: note.note_url,
    note_title: note.note_title,
    note_author_id: note.note_author_id,
    note_author_name: note.note_author_name,
    note_desc: note.note_desc || "",
    note_type: note.note_type || "",
    note_likes: note.note_likes || "",
    note_comments_count: note.note_comments_count || "",
    note_collected_count: note.note_collected_count || "",
    note_shared_count: note.note_shared_count || "",
    note_publish_time: note.note_publish_time || "",
    note_ip_location: note.note_ip_location || "",
    note_image_url: note.note_image_url || "",
    detail_status: note.detail_status || "",
    comment_index: index + 1,
    comment_type: parentCommentId ? "reply" : "root",
    parent_comment_id: parentCommentId,
    comment_id: pick(raw, ["id", "comment_id", "commentId"]) || "",
    comment_text: pick(raw, ["content", "text", "comment_content"]) || "",
    comment_likes: pick(raw, ["like_count", "likeCount", "liked_count", "likedCount", "likes"]) || "",
    comment_time: normalizeTime(pick(raw, ["create_time", "createTime", "created_at", "createdAt", "time", "timestamp"])),
    comment_user_id: pick(user, ["user_id", "userId", "id", "userid"]) || "",
    comment_user_name: pick(user, ["nickname", "nick_name", "nickName", "name"]) || "",
    comment_user_profile: pick(user, ["profile_url", "user_link", "link"]) || "",
    raw_note_json: "",
    raw_comment_json: JSON.stringify(raw),
  };
}

function pick(object, keys) {
  if (!object || typeof object !== "object") return undefined;
  for (const key of keys) {
    if (object[key] !== undefined && object[key] !== null) return object[key];
  }
  return undefined;
}

function normalizeTime(value) {
  if (value === undefined || value === null || value === "") return "";
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    const ms = numeric > 10_000_000_000 ? numeric : numeric * 1000;
    return new Date(ms).toISOString();
  }
  return String(value);
}

function extractNextCursor(json) {
  const candidates = [
    "data.cursor",
    "data.next_cursor",
    "data.nextCursor",
    "data.data.cursor",
    "data.data.next_cursor",
    "cursor",
    "next_cursor",
    "nextCursor",
  ];

  for (const path of candidates) {
    const value = getPath(json, path);
    if (value !== undefined && value !== null && value !== "") return String(value);
  }

  return "";
}

function extractHasMore(json, itemCount) {
  const candidates = [
    "data.has_more",
    "data.hasMore",
    "data.has_next",
    "data.data.has_more",
    "has_more",
    "hasMore",
    "has_next",
  ];

  for (const path of candidates) {
    const value = getPath(json, path);
    if (typeof value === "boolean") return value;
    if (value === 0 || value === 1) return Boolean(value);
  }

  return itemCount > 0 && Boolean(extractNextCursor(json));
}

async function fetchNotes({
  authorization,
  keywordItem,
  targetCount,
  searchPageSize,
  sort,
  noteType,
  timeFilter,
  delayMs,
  skipNoteIds = new Set(),
}) {
  const notes = [];
  const seen = new Set();
  const keyword = keywordItem.keyword;
  let candidateIndex = 0;
  let skippedExistingCount = 0;
  let page = 1;
  let searchId = "";
  let searchSessionId = "";

  if (targetCount <= 0) return notes;

  while (notes.length < targetCount) {
    let url;
    let json;
    try {
      ({ url, json } = await apiGet(
        "app_v2/search_notes",
        {
          keyword,
          page,
          sort_type: sort,
          note_type: noteType,
          time_filter: timeFilter,
          search_id: searchId,
          search_session_id: searchSessionId,
        },
        authorization,
      ));
    } catch (error) {
      if (notes.length > 0) {
        console.warn(
          `Search page ${page} failed for "${keyword}"; keeping ${notes.length}/${targetCount} collected notes. ${error.message.split("\n")[0]}`,
        );
        break;
      }
      throw error;
    }
    const items = extractSearchItems(json);

    if (!Array.isArray(items)) {
      console.error("Could not find notes array in search response. Top-level keys:", Object.keys(json));
      console.error("Request URL:", url);
      throw new Error("Search response shape is not recognized. Inspect the response and update extractSearchItems().");
    }

    if (items.length === 0) break;

    for (const item of items) {
      const note = extractSearchNote(item, candidateIndex);
      candidateIndex += 1;
      note.keyword = keyword;
      if (!note.note_id) {
        console.warn("Skipping a search item without note_id:", JSON.stringify(item).slice(0, 300));
        continue;
      }
      if (skipNoteIds.has(note.note_id)) {
        skippedExistingCount += 1;
        continue;
      }
      if (seen.has(note.note_id)) continue;
      seen.add(note.note_id);
      note.keyword_rank = keywordItem.keyword_rank || "";
      note.keyword_source_rank = keywordItem.source_rank || "";
      note.keyword_sheet_row = keywordItem.sheet_row || "";
      note.battle_category = keywordItem.battle_category || "";
      notes.push(note);
      if (notes.length >= targetCount) break;
    }

    searchId = getPath(json, "data.search_id") || searchId;
    searchSessionId = getPath(json, "data.search_session_id") || searchSessionId;
    const nextPage = getPath(json, "data.next_page");

    console.log(
      `Search page ${page}: ${items.length} items, ${notes.length}/${targetCount} new notes, skipped_existing=${skippedExistingCount}.`,
    );
    if (items.length < searchPageSize) break;
    if (!nextPage || Number(nextPage) === page) break;

    page = Number(nextPage);
    await sleep(delayMs);
  }

  return notes;
}

async function fetchNoteDetail({ authorization, note }) {
  const endpoints = ["app_v2/get_image_note_detail", "app_v2/get_video_note_detail"];
  const errors = [];

  for (const endpoint of endpoints) {
    try {
      const { json } = await apiGet(endpoint, { note_id: note.note_id }, authorization);
      const detail = extractDetailNote(json);
      if (detail) return mergeDetailIntoNote(note, detail);
      errors.push(`${endpoint}: response had no note detail`);
    } catch (error) {
      errors.push(`${endpoint}: ${error.message.split("\n")[0]}`);
    }
  }

  console.warn(`  Failed note detail for #${note.search_rank}/${note.note_id}; using search result only. ${errors.join(" | ")}`);
  return {
    ...note,
    detail_status: "failed",
    note_type: "",
    note_desc: "",
    note_likes: "",
    note_comments_count: "",
    note_collected_count: "",
    note_shared_count: "",
    note_publish_time: "",
    note_ip_location: "",
    note_image_url: "",
    raw_note_json: JSON.stringify(note.raw_search_note || {}),
  };
}

function extractDetailCommentItems(detailJson, detailRaw) {
  const candidateArrays = [
    extractCommentItems(detailRaw),
    extractCommentItems(detailJson),
    getPath(detailRaw, "comments.list"),
    getPath(detailRaw, "comment_list.list"),
    getPath(detailJson, "data.comments.list"),
    getPath(detailJson, "data.comment_list.list"),
    getPath(detailJson, "data.data.comments.list"),
    getPath(detailJson, "data.data.comment_list.list"),
  ].filter(Array.isArray);

  for (const items of candidateArrays) {
    const comments = items.filter((item) => {
      if (!item || typeof item !== "object") return false;
      return Boolean(
        pick(item, ["content", "text", "comment_content"]) ||
          pick(item, ["comment_id", "commentId"]) ||
          item?.user_info ||
          item?.userInfo ||
          item?.user,
      );
    });
    if (comments.length > 0) return comments;
  }

  return [];
}

async function fetchDetailCommentsForNote({ authorization, note, detailCommentLimit }) {
  const endpoints = ["app_v2/get_image_note_detail", "app_v2/get_video_note_detail"];
  const errors = [];

  for (const endpoint of endpoints) {
    try {
      const { json } = await apiGet(endpoint, { note_id: note.note_id }, authorization);
      const detailRaw = extractDetailNote(json);
      const detailComments = extractDetailCommentItems(json, detailRaw);
      const mergedNote = detailRaw ? mergeDetailIntoNote(note, detailRaw) : note;
      const rows = detailComments
        .slice(0, detailCommentLimit > 0 ? detailCommentLimit : detailComments.length)
        .map((comment, index) => makeCommentRow(comment, mergedNote, index));

      if (detailRaw || detailComments.length > 0) {
        return {
          note: mergedNote,
          rows,
          completed: true,
          endpoint,
        };
      }
      errors.push(`${endpoint}: response had no note detail or detail comments`);
    } catch (error) {
      errors.push(`${endpoint}: ${error.message.split("\n")[0]}`);
    }
  }

  return {
    note,
    rows: [],
    completed: false,
    endpoint: "",
    error: errors.join(" | "),
  };
}

async function fetchAppV2FirstPageCommentsForNote({ authorization, note, detailCommentLimit }) {
  const { json } = await apiGet(
    "app_v2/get_note_comments",
    {
      note_id: note.note_id,
      cursor: "",
      index: 0,
      pageArea: "UNFOLDED",
      sort_strategy: "latest_v2",
    },
    authorization,
  );
  const items = extractCommentItems(json);

  if (!Array.isArray(items)) {
    throw new Error(`App-V2 comment response had no comments array for note ${note.note_id}`);
  }

  const cappedItems = items.slice(0, detailCommentLimit > 0 ? detailCommentLimit : items.length);
  const noteForRows = {
    ...note,
    detail_status: "app_v2_comments",
  };
  return cappedItems.map((comment, index) => makeCommentRow(comment, noteForRows, index));
}

async function fetchCommentsForNote({
  authorization,
  note,
  delayMs,
  maxCommentPagesPerNote,
  maxSubCommentPagesPerRoot,
  includeSubComments,
  onlySubComments,
  maxCommentsPerNote,
}) {
  const rows = [];
  const seenCommentIds = new Set();
  const fetchedSubCommentRoots = new Set();
  let hadRequestError = false;
  let cursor = "";
  let page = 1;

  if (!note.xsec_token) {
    console.warn(`  Note ${note.search_rank}/${note.note_id} has no xsec_token; skipping comments.`);
    return {
      rows,
      completed: false,
      error: "missing xsec_token",
    };
  }

  const addComment = (comment, parentCommentId = "") => {
    const commentId = pick(comment, ["id", "comment_id", "commentId"]);
    if (commentId) {
      if (seenCommentIds.has(commentId)) return false;
      seenCommentIds.add(commentId);
    }
    const commentForRow = parentCommentId && !pick(comment, ["parent_comment_id", "parentCommentId", "parent_id", "parentId"])
      ? { ...comment, parent_comment_id: parentCommentId }
      : comment;
    rows.push(makeCommentRow(commentForRow, note, rows.length));
    return true;
  };

  while (true) {
    let json;
    try {
      ({ json } = await apiGet(
        "web_v3/fetch_note_comments",
        {
          note_id: note.note_id,
          cursor,
          xsec_token: note.xsec_token,
        },
        authorization,
      ));
    } catch (error) {
      hadRequestError = true;
      console.warn(
        `  Failed comments page ${page} for note ${note.search_rank}/${note.note_id}; keeping ${rows.length} collected rows. ${error.message}`,
      );
      break;
    }

    const items = extractCommentItems(json);
    if (!Array.isArray(items)) {
      console.warn(
        `  No comments array on page ${page} for note ${note.search_rank}/${note.note_id}; treating this page as empty.`,
      );
      break;
    }

    const beforeRowCount = rows.length;
    for (const item of items) {
      const rootCommentId = pick(item, ["id", "comment_id", "commentId"]);
      if (!onlySubComments) addComment(item);

      // 楼中楼很耗请求量，默认只抓主评论；需要完整覆盖时用 --include-sub-comments 打开。
      if (includeSubComments) {
        for (const subComment of item?.subComments || item?.sub_comments || []) addComment(subComment, rootCommentId);
      }

      if (
        includeSubComments &&
        (item?.subCommentHasMore || item?.sub_comment_has_more) &&
        !fetchedSubCommentRoots.has(rootCommentId)
      ) {
        if (rootCommentId) fetchedSubCommentRoots.add(rootCommentId);
        try {
          const subComments = await fetchSubCommentsForRoot({
            authorization,
            note,
            rootComment: item,
            delayMs,
            maxSubCommentPagesPerRoot,
          });
          for (const subComment of subComments) {
            addComment(subComment, rootCommentId);
            if (maxCommentsPerNote > 0 && rows.length >= maxCommentsPerNote) break;
          }
        } catch (error) {
          console.warn(`    Failed to fetch sub-comments for root ${rootCommentId}: ${error.message}`);
        }
      }

      if (maxCommentsPerNote > 0 && rows.length >= maxCommentsPerNote) break;
    }

    const nextCursor = extractNextCursor(json);
    const hasMore = extractHasMore(json, items.length);
    const addedRows = rows.length - beforeRowCount;
    console.log(
      `  Comments page ${page} for note ${note.search_rank}/${note.note_id}: +${items.length}, added ${addedRows}, total ${rows.length}, hasMore=${hasMore}`,
    );

    if (!hasMore || !nextCursor || nextCursor === cursor) break;
    if (addedRows === 0 && !onlySubComments) {
      console.warn(`  No new unique comments on page ${page}; stopping pagination for note ${note.note_id}.`);
      break;
    }
    if (maxCommentsPerNote > 0 && rows.length >= maxCommentsPerNote) break;
    if (maxCommentPagesPerNote > 0 && page >= maxCommentPagesPerNote) break;

    cursor = nextCursor;
    page += 1;
    await sleep(delayMs);
  }

  return {
    rows,
    completed: !hadRequestError,
    error: hadRequestError ? "comment request failed before page limit" : "",
  };
}

async function fetchSubCommentsForRoot({ authorization, note, rootComment, delayMs, maxSubCommentPagesPerRoot }) {
  const rows = [];
  const rootCommentId = pick(rootComment, ["id", "comment_id", "commentId"]);
  let cursor = pick(rootComment, ["subCommentCursor", "sub_comment_cursor"]) || "";
  let page = 1;

  if (!rootCommentId) return rows;

  while (true) {
    await sleep(delayMs);
    const { json } = await apiGet(
      "web_v3/fetch_sub_comments",
      {
        note_id: note.note_id,
        root_comment_id: rootCommentId,
        num: 10,
        cursor,
        xsec_token: note.xsec_token,
      },
      authorization,
    );
    const items = extractCommentItems(json);
    if (!Array.isArray(items) || items.length === 0) break;

    rows.push(...items);

    const nextCursor = extractNextCursor(json);
    const hasMore = extractHasMore(json, items.length);
    console.log(
      `    Sub-comments page ${page} for root ${rootCommentId}: +${items.length}, total ${rows.length}, hasMore=${hasMore}`,
    );

    if (!hasMore || !nextCursor || nextCursor === cursor) break;
    if (maxSubCommentPagesPerRoot > 0 && page >= maxSubCommentPagesPerRoot) break;
    cursor = nextCursor;
    page += 1;
  }

  return rows;
}

function getCsvHeaders() {
  return [
    "keyword_rank",
    "keyword_source_rank",
    "keyword_sheet_row",
    "battle_category",
    "keyword",
    "search_rank",
    "note_id",
    "note_url",
    "note_title",
    "note_author_id",
    "note_author_name",
    "note_desc",
    "note_type",
    "note_likes",
    "note_comments_count",
    "note_collected_count",
    "note_shared_count",
    "note_publish_time",
    "note_ip_location",
    "note_image_url",
    "detail_status",
    "comment_index",
    "comment_type",
    "parent_comment_id",
    "comment_id",
    "comment_text",
    "comment_likes",
    "comment_time",
    "comment_user_id",
    "comment_user_name",
    "comment_user_profile",
    "raw_note_json",
    "raw_comment_json",
  ];
}

function rowToCsvLine(row, headers = getCsvHeaders()) {
  return headers.map((header) => csvEscape(row[header])).join(",");
}

function csvEscape(value) {
  const text = value === undefined || value === null ? "" : String(value).replace(/\r?\n/g, " ");
  if (/[",\n\r]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
  return text;
}

async function main() {
  await loadDotEnv();
  const args = parseArgs(process.argv.slice(2));
  const seedNotes = args.seedCsv ? await readSeedNotesFromCsv(args.seedCsv, args) : [];
  const seedNotesByKeyword = args.seedCsv ? groupSeedNotesByKeyword(seedNotes) : new Map();
  const keywordItems = args.seedCsv ? keywordItemsFromSeedNotes(seedNotes) : await resolveKeywordItems(args);
  const targetCount = args.full ? args.limit : args.testNotes;
  const stateOutput = getStateOutputPath(args);
  const currentProgress = args.resume ? await loadProgressFromState(stateOutput, { includeFailed: true }) : createProgress();
  const skipSuccessProgress = await loadProgressFromState(args.skipSuccessState, { includeFailed: false });

  if (args.printKeywords) {
    console.log(JSON.stringify(keywordItems, null, 2));
    return;
  }

  if (args.printProgress) {
    if (args.seedCsv) printSeedProgressReport(keywordItems, seedNotesByKeyword, currentProgress, skipSuccessProgress);
    else printProgressReport(keywordItems, currentProgress, skipSuccessProgress, targetCount);
    return;
  }

  const authorization = getAuthorization();

  console.log(
    args.seedCsv
      ? `Mode: ${args.full ? "full" : "test"} seed-csv; keywords=${keywordItems.length}; seed notes=${seedNotes.length}`
      : `Mode: ${args.full ? "full" : "test"}; keywords=${keywordItems.length}; target notes per keyword=${targetCount}`,
  );
  console.log(
    args.fast
      ? `Comment source: fast app_v2/get_note_comments first ${args.detailCommentLimit} comment(s); concurrency=${args.concurrency}`
      : `Comment source: detail + web_v3/fetch_note_comments pages=${args.maxCommentPagesPerNote || "all"}, sub_comments=${args.includeSubComments ? `on pages=${args.maxSubCommentPagesPerRoot || "all"}${args.onlySubComments ? ", only replies" : ""}` : "off"}; concurrency=${args.concurrency}`,
  );
  if (args.seedCsv) {
    console.log(`Seed CSV: ${args.seedCsv}`);
    console.log(`Seed keywords: ${keywordItems.map((item) => `${item.keyword_rank}.${item.keyword}(${seedNotesByKeyword.get(item.keyword)?.length || 0})`).join(" | ")}`);
  } else if (args.keywordExcel) {
    console.log(`Keyword Excel: ${args.keywordExcel}; sheet="${args.keywordExcelSheet}"; battle="${args.battleCategory}"`);
    console.log(`Keywords: ${keywordItems.map((item) => `${item.keyword_rank}.${item.keyword}`).join(" | ")}`);
  } else {
    console.log(`Keyword: "${args.keyword}"`);
  }
  if (args.skipSuccessState) {
    console.log(`Skipping historical done notes from ${args.skipSuccessState}`);
  }
  if (args.resume) {
    console.log(`Resume mode is on. Details state=${stateOutput}`);
    if (args.seedCsv) printSeedProgressReport(keywordItems, seedNotesByKeyword, currentProgress, skipSuccessProgress);
    else printProgressReport(keywordItems, currentProgress, skipSuccessProgress, targetCount);
  }
  if (!args.full) {
    console.log("Test mode is on. Add --full after validating 1-2 notes to fetch more notes.");
  }

  const headers = getCsvHeaders();
  const appendOutput = args.resume && await fileHasContent(args.output);
  if (!appendOutput) await writeFile(args.output, `${headers.join(",")}\n`, "utf8");
  if (!args.resume || !await fileHasContent(stateOutput)) await writeFile(stateOutput, "", "utf8");

  let totalRows = 0;
  let totalNotes = 0;
  for (const keywordItem of keywordItems) {
    const externalDone = getDoneNoteIds(skipSuccessProgress, keywordItem.keyword);
    const currentDone = getDoneNoteIds(currentProgress, keywordItem.keyword);
    const currentFailed = getFailedNoteIds(currentProgress, keywordItem.keyword);
    const skipNoteIds = unionSets(externalDone, currentDone, currentFailed);
    const seedNotesForKeyword = seedNotesByKeyword.get(keywordItem.keyword) || [];
    const targetCountForKeyword = args.seedCsv ? seedNotesForKeyword.length : targetCount;
    const remainingCount = args.seedCsv
      ? seedNotesForKeyword.filter((note) => !skipNoteIds.has(note.note_id)).length
      : Math.max(0, targetCount - skipNoteIds.size);

    console.log(
      `${args.seedCsv ? "Seeding" : "Searching"} keyword ${keywordItem.keyword_rank}/${keywordItems.length}: "${keywordItem.keyword}" target=${targetCountForKeyword}, historical_done=${externalDone.size}, detail_done=${currentDone.size}, detail_failed=${currentFailed.size}, remaining=${remainingCount}`,
    );
    if (remainingCount === 0) {
      console.log(`Keyword "${keywordItem.keyword}" already reached target after skips. Skipping.`);
      continue;
    }

    let notes = [];
    if (args.seedCsv) {
      notes = seedNotesForKeyword.filter((note) => !skipNoteIds.has(note.note_id));
    } else {
      try {
        notes = await fetchNotes({
          authorization,
          keywordItem,
          targetCount: remainingCount,
          searchPageSize: args.searchPageSize,
          sort: args.sort,
          noteType: args.noteType,
          timeFilter: args.timeFilter,
          delayMs: args.delayMs,
          skipNoteIds,
        });
      } catch (error) {
        console.error(`Failed to search keyword "${keywordItem.keyword}":`, error.message);
        continue;
      }
    }

    if (notes.length === 0) {
      console.log(`No new notes found for keyword "${keywordItem.keyword}".`);
      continue;
    }

    totalNotes += notes.length;
    let nextNoteIndex = 0;
    const workerCount = Math.min(args.concurrency, notes.length);

    async function runWorker(workerId) {
      while (true) {
        const searchNote = notes[nextNoteIndex];
        nextNoteIndex += 1;
        if (!searchNote) break;

        console.log(
          `[worker ${workerId}] Fetching ${args.fast ? "fast App-V2 comments" : "detail + Web-V3 comments"} for keyword ${keywordItem.keyword_rank}/${keywordItems.length}, note #${searchNote.search_rank}: ${searchNote.note_id} ${searchNote.note_title || ""}`.trim(),
        );
        try {
          const result = args.fast
            ? {
                note: searchNote,
                rows: await fetchAppV2FirstPageCommentsForNote({
                  authorization,
                  note: searchNote,
                  detailCommentLimit: args.detailCommentLimit,
                }),
                completed: true,
                error: "",
              }
            : await (async () => {
                const detailNote = await fetchNoteDetail({ authorization, note: searchNote });
                const commentsResult = await fetchCommentsForNote({
                  authorization,
                  note: detailNote,
                  delayMs: args.delayMs,
                  maxCommentPagesPerNote: args.maxCommentPagesPerNote,
                  maxSubCommentPagesPerRoot: args.maxSubCommentPagesPerRoot,
                  includeSubComments: args.includeSubComments,
                  onlySubComments: args.onlySubComments,
                  maxCommentsPerNote: args.maxCommentsPerNote,
                });
                return {
                  note: detailNote,
                  ...commentsResult,
                };
              })();

          if (!result.completed) {
            await writeNoteState(stateOutput, result.note, "failed", result.rows.length, result.error || "comment request failed");
            addFailedNote(currentProgress, result.note.keyword, result.note.note_id);
          } else {
            if (result.rows.length > 0) {
              await appendFile(args.output, `${result.rows.map((row) => rowToCsvLine(row, headers)).join("\n")}\n`, "utf8");
              totalRows += result.rows.length;
            }
            console.log(`  ${args.fast ? "App-V2 first-page" : "Web-V3"} comments: +${result.rows.length}, note=${result.note.note_id}`);
            await writeNoteState(stateOutput, result.note, "done", result.rows.length);
            addDoneNote(currentProgress, result.note.keyword, result.note.note_id);
          }
        } catch (error) {
          console.error(`Failed to fetch note detail/comments for note ${searchNote.note_id}:`, error.message);
          await writeNoteState(stateOutput, searchNote, "failed", 0, error.message);
          addFailedNote(currentProgress, searchNote.keyword, searchNote.note_id);
        }
        await sleep(args.delayMs);
      }
    }

    await Promise.all(Array.from({ length: workerCount }, (_, index) => runWorker(index + 1)));
  }

  console.log(`Done. Exported ${totalRows} comments from ${totalNotes} new notes across ${keywordItems.length} keyword(s) to ${args.output}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
