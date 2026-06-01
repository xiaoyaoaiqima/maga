#!/usr/bin/env node

import { execFile } from "node:child_process";
import { open, readFile, stat } from "node:fs/promises";

const API_ROOT = "https://api.tikhub.io/api/v1/xiaohongshu";
const DEFAULT_KEYWORD = "a2至初";
const DEFAULT_OUTPUT = "xhs_a2至初_comments.csv";
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
    maxCommentPagesPerNote: 2,
    maxSubCommentPagesPerRoot: 1,
    includeSubComments: false,
    maxCommentsPerNote: 0,
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
    else if (arg === "--max-comment-pages-per-note") args.maxCommentPagesPerNote = parseNonNegativeInt(arg, next, ++i);
    else if (arg === "--max-sub-comment-pages-per-root") args.maxSubCommentPagesPerRoot = parseNonNegativeInt(arg, next, ++i);
    else if (arg === "--include-sub-comments") args.includeSubComments = true;
    else if (arg === "--max-comments-per-note") args.maxCommentsPerNote = parseNonNegativeInt(arg, next, ++i);
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
  if (!value || value.startsWith("--")) {
    throw new Error(`${flag} requires a value`);
  }
  return value;
}

function parsePositiveInt(flag, value) {
  const parsed = Number.parseInt(requiredValue(flag, value), 10);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`${flag} must be a positive integer`);
  }
  return parsed;
}

function parseNonNegativeInt(flag, value) {
  const parsed = Number.parseInt(requiredValue(flag, value), 10);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new Error(`${flag} must be a non-negative integer`);
  }
  return parsed;
}

function printHelp() {
  console.log(`
Usage:
  TIKHUB_AUTHORIZATION="Bearer <token>" node crawl_xhs_comments.mjs
  TIKHUB_BEARER_TOKEN="<token>" node crawl_xhs_comments.mjs --full

Options:
  --keyword <text>                    Search keyword. Default: ${DEFAULT_KEYWORD}
  --output <path>                     CSV output path. Default: ${DEFAULT_OUTPUT}
  --full                              Fetch first 50 notes and all comments.
                                      Without this flag, only 2 notes are fetched for testing.
  --limit <number>                    Note limit in full mode. Default: 50
  --test-notes <number>               Note limit in test mode. Default: 2
  --search-page-size <number>         Search page size assumption. Default: 20
  --delay-ms <number>                 Delay between API calls. Default: 800
  --max-comment-pages-per-note <n>    Main comment page cap. 0 means no cap. Default: 2
  --max-sub-comment-pages-per-root <n>
                                      Sub-comment page cap per root comment. 0 means no cap. Default: 1
  --include-sub-comments              Include embedded sub-comments and fetch extra sub-comment pages.
                                      Omit this flag to skip sub-comments.
  --max-comments-per-note <n>         Debug cap. 0 means no cap.
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
  --resume                            Resume from existing output/progress and skip completed notes.
  --print-progress                    Print detected completed notes and exit without API calls.
  --state-output <path>               Progress JSONL path. Default: <output>.state.jsonl
`);
}

function getAuthorization() {
  const authorization = process.env.TIKHUB_AUTHORIZATION;
  if (authorization) return normalizeAuthorization(authorization);

  const token = process.env.TIKHUB_BEARER_TOKEN || process.env.TIKHUB_TOKEN;
  if (token) return normalizeAuthorization(token);

  throw new Error(
    "Missing auth. Set TIKHUB_AUTHORIZATION=\"Bearer <token>\" or TIKHUB_BEARER_TOKEN=\"<token>\".",
  );
}

function normalizeAuthorization(value) {
  const trimmed = value.trim();
  return trimmed.toLowerCase().startsWith("bearer ") ? trimmed : `Bearer ${trimmed}`;
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
  // 通过 Python/openpyxl 读取 xlsx，避免为这个临时采集脚本额外引入 npm 依赖。
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

  if (payload.error) {
    throw new Error(payload.error);
  }
  if (!Array.isArray(payload.keywords) || payload.keywords.length === 0) {
    throw new Error(`No keywords found for battle category "${battleCategory}" in sheet "${sheetName}".`);
  }

  return payload.keywords;
}

function getStateOutputPath(args) {
  return args.stateOutput || `${args.output}.state.jsonl`;
}

function createProgress() {
  return {
    doneByKeyword: new Map(),
    failedByKeyword: new Map(),
    doneCountFromCsv: 0,
    doneCountFromState: 0,
    failedCountFromState: 0,
    source: "none",
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

function getAttemptedNoteIds(progress, keyword) {
  return new Set([...getDoneNoteIds(progress, keyword), ...getFailedNoteIds(progress, keyword)]);
}

async function loadExistingProgress({ output, stateOutput }) {
  const progress = createProgress();

  await loadProgressFromState(progress, stateOutput);
  if (progress.doneCountFromState > 0 || progress.failedCountFromState > 0) {
    progress.source = "state";
    return progress;
  }

  await loadProgressFromCsv(progress, output);
  if (progress.doneCountFromCsv > 0) progress.source = "csv";
  return progress;
}

async function loadProgressFromState(progress, stateOutput) {
  let text = "";
  try {
    text = await readFile(stateOutput, "utf8");
  } catch (error) {
    if (error.code === "ENOENT") return;
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
      if (
        item.migrated_from !== "csv" &&
        item.allow_zero_comment_done !== true &&
        Number(item.comment_count || 0) <= 0
      ) {
        continue;
      }
      if (addDoneNote(progress, item.keyword, item.note_id)) {
        progress.doneCountFromState += 1;
      }
    } else if (item.status === "failed") {
      if (addFailedNote(progress, item.keyword, item.note_id)) {
        progress.failedCountFromState += 1;
      }
    }
  }
}

async function loadProgressFromCsv(progress, output) {
  let text = "";
  try {
    text = await readFile(output, "utf8");
  } catch (error) {
    if (error.code === "ENOENT") return;
    throw error;
  }

  const rows = parseCsv(text);
  if (rows.length < 2) return;

  const headers = rows[0];
  const keywordIndex = headers.indexOf("keyword");
  const noteIdIndex = headers.indexOf("note_id");
  if (keywordIndex === -1 || noteIdIndex === -1) return;

  for (const row of rows.slice(1)) {
    const keyword = row[keywordIndex] || "";
    const noteId = row[noteIdIndex] || "";
    if (addDoneNote(progress, keyword, noteId)) {
      progress.doneCountFromCsv += 1;
    }
  }
}

function parseCsv(text) {
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

async function fileHasContent(path) {
  try {
    const info = await stat(path);
    return info.size > 0;
  } catch (error) {
    if (error.code === "ENOENT") return false;
    throw error;
  }
}

function printProgressReport(keywordItems, progress, targetCount) {
  console.log(`Progress source: ${progress.source}`);
  for (const item of keywordItems) {
    const doneCount = getDoneNoteIds(progress, item.keyword).size;
    const failedCount = getFailedNoteIds(progress, item.keyword).size;
    const attemptedCount = getAttemptedNoteIds(progress, item.keyword).size;
    const remaining = Math.max(0, targetCount - attemptedCount);
    console.log(
      `${item.keyword_rank}. ${item.keyword}: done=${doneCount}, failed=${failedCount}, attempted=${attemptedCount}, remaining=${remaining}, target=${targetCount}`,
    );
  }
}

async function writeNoteState(stateFile, note, status, commentCount, errorMessage = "") {
  const payload = {
    status,
    keyword: note.keyword,
    keyword_rank: note.keyword_rank,
    keyword_source_rank: note.keyword_source_rank,
    battle_category: note.battle_category,
    search_rank: note.search_rank,
    note_id: note.note_id,
    note_title: note.note_title,
    comment_count: commentCount,
    allow_zero_comment_done: status === "done",
    error: errorMessage,
    finished_at: new Date().toISOString(),
  };
  await stateFile.write(`${JSON.stringify(payload)}\n`, "utf8");
}

async function writeProgressSnapshotToState(stateFile, keywordItems, progress) {
  for (const item of keywordItems) {
    for (const noteId of getDoneNoteIds(progress, item.keyword)) {
      const payload = {
        status: "done",
        keyword: item.keyword,
        keyword_rank: item.keyword_rank,
        keyword_source_rank: item.source_rank,
        battle_category: item.battle_category,
        note_id: noteId,
        comment_count: "",
        migrated_from: "csv",
        finished_at: new Date().toISOString(),
      };
      await stateFile.write(`${JSON.stringify(payload)}\n`, "utf8");
    }
  }
}

async function apiGet(path, query, authorization) {
  const url = new URL(`${API_ROOT}/${path}`);
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }

  let lastError;
  for (let attempt = 1; attempt <= 4; attempt += 1) {
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
        const retryable = response.status === 408 || response.status === 429 || response.status >= 500;
        const error = new Error(`HTTP ${response.status} ${response.statusText} for ${redactUrl(url)}\n${summarizeApiError(text)}`);
        if (!retryable) throw Object.assign(error, { nonRetryable: true });
        if (attempt === 4) throw error;
        lastError = error;
      } else if (!json) {
        throw new Error(`Expected JSON response for ${redactUrl(url)}, got:\n${text.slice(0, 800)}`);
      } else {
        return { url: url.toString(), json };
      }
    } catch (error) {
      lastError = error;
      if (error.nonRetryable) throw error;
      if (attempt === 4) throw error;
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

function extractCommentItems(json) {
  return (
    firstArrayAtAnyPath(json, [
      "data.comments",
      "data.comment_list",
      "data.list",
      "data.items",
      "data.data.comments",
      "data.data.comment_list",
      "comments",
      "comment_list",
      "items",
    ]) || deepFindArray(json, ["comments", "comment_list", "items", "list"])
  );
}

function extractNote(raw, index) {
  const source = raw?.note_card || raw?.note || raw?.model || raw;
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
    xsec_token: xsecToken || "",
    note_url: buildNoteUrl(noteId, xsecToken),
    note_title: pick(source, ["title", "display_title", "desc"]) || "",
    note_author_id: pick(source?.user || source?.user_info || raw?.user || raw?.user_info, ["user_id", "id", "userid"]) || "",
    note_author_name: pick(source?.user || source?.user_info || raw?.user || raw?.user_info, ["nickname", "nick_name", "name"]) || "",
    raw,
  };
}

function buildNoteUrl(noteId, xsecToken) {
  if (!noteId) return "";
  const url = new URL(`https://www.xiaohongshu.com/explore/${noteId}`);
  if (xsecToken) url.searchParams.set("xsec_token", xsecToken);
  url.searchParams.set("xsec_source", "pc_search");
  return url.toString();
}

function extractComment(raw, note, index) {
  const user = raw?.user_info || raw?.userInfo || raw?.user || raw?.author || {};
  const parentComment = raw?.targetComment || {};
  const parentCommentId =
    pick(raw, ["parent_comment_id", "parentCommentId", "parent_id", "parentId"]) ||
    pick(parentComment, ["id", "comment_id", "commentId"]) ||
    "";
  return {
    keyword_rank: note.keyword_rank,
    keyword_source_rank: note.keyword_source_rank,
    keyword_sheet_row: note.keyword_sheet_row,
    battle_category: note.battle_category,
    keyword: note.keyword,
    search_rank: note.search_rank,
    note_id: note.note_id,
    note_url: note.note_url,
    note_title: note.note_title,
    note_author_id: note.note_author_id,
    note_author_name: note.note_author_name,
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
      if (notes.length === 0) throw error;
      console.warn(
        `Search page ${page} failed for keyword "${keyword}"; using ${notes.length} already collected notes. ${error.message}`,
      );
      break;
    }
    const items = extractSearchItems(json);

    if (!Array.isArray(items)) {
      console.error("Could not find notes array in search response. Top-level keys:", Object.keys(json));
      console.error("Request URL:", url);
      throw new Error("Search response shape is not recognized. Inspect the response and update extractSearchItems().");
    }

    if (items.length === 0) break;

    for (const item of items) {
      const note = extractNote(item, candidateIndex);
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

async function fetchCommentsForNote({
  authorization,
  note,
  delayMs,
  maxCommentPagesPerNote,
  maxSubCommentPagesPerRoot,
  includeSubComments,
  maxCommentsPerNote,
}) {
  const rows = [];
  const seenCommentIds = new Set();
  const fetchedSubCommentRoots = new Set();
  let hadRequestError = false;
  let cursor = "";
  let page = 1;

  const addComment = (comment) => {
    const commentId = pick(comment, ["id", "comment_id", "commentId"]);
    if (commentId) {
      if (seenCommentIds.has(commentId)) return false;
      seenCommentIds.add(commentId);
    }
    rows.push(extractComment(comment, note, rows.length));
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
      console.log(`  Comments page ${page} for note ${note.search_rank}/${note.note_id}: +0, total ${rows.length}, hasMore=false`);
      break;
    }

    const beforeRowCount = rows.length;
    for (const item of items) {
      addComment(item);
      // 楼中楼开销较大，默认关闭；保留开关供后续需要时恢复抓取。
      if (includeSubComments) {
        for (const subComment of item?.subComments || item?.sub_comments || []) {
          addComment(subComment);
        }
      }
      const rootCommentId = pick(item, ["id", "comment_id", "commentId"]);
      if (
        includeSubComments &&
        (item?.subCommentHasMore || item?.sub_comment_has_more) &&
        !fetchedSubCommentRoots.has(rootCommentId)
      ) {
        if (rootCommentId) fetchedSubCommentRoots.add(rootCommentId);
        try {
          const subRows = await fetchSubCommentsForRoot({
            authorization,
            note,
            rootComment: item,
            delayMs,
            maxSubCommentPagesPerRoot,
          });
          for (const subComment of subRows) {
            addComment(subComment);
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
    if (addedRows === 0) {
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

const CSV_HEADERS = [
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
  "raw_comment_json",
];

function rowsToCsv(rows) {
  return rows.map((row) => CSV_HEADERS.map((header) => csvEscape(row[header])).join(",")).join("\n");
}

function csvEscape(value) {
  const text = value === undefined || value === null ? "" : String(value).replace(/\r?\n/g, " ");
  if (/[",\n\r]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
  return text;
}

async function main() {
  await loadDotEnv();
  const args = parseArgs(process.argv.slice(2));
  const keywordItems = await resolveKeywordItems(args);
  const targetCount = args.full ? args.limit : args.testNotes;
  const stateOutput = getStateOutputPath(args);

  if (args.printKeywords) {
    console.log(JSON.stringify(keywordItems, null, 2));
    return;
  }
  if (args.printProgress) {
    const progress = await loadExistingProgress({ output: args.output, stateOutput });
    printProgressReport(keywordItems, progress, targetCount);
    return;
  }

  const authorization = getAuthorization();
  const existingOutputHasContent = await fileHasContent(args.output);
  const progress = args.resume && existingOutputHasContent
    ? await loadExistingProgress({ output: args.output, stateOutput })
    : createProgress();

  console.log(
    `Mode: ${args.full ? "full" : "test"}; keywords=${keywordItems.length}; target notes per keyword=${targetCount}`,
  );
  if (args.keywordExcel) {
    console.log(`Keyword Excel: ${args.keywordExcel}; sheet="${args.keywordExcelSheet}"; battle="${args.battleCategory}"`);
    console.log(`Keywords: ${keywordItems.map((item) => `${item.keyword_rank}.${item.keyword}`).join(" | ")}`);
  } else {
    console.log(`Keyword: "${args.keyword}"`);
  }
  if (!args.full) {
    console.log("Test mode is on. Add --full after validating 1-2 notes per keyword.");
  }
  if (args.resume) {
    if (existingOutputHasContent) {
      console.log(`Resume mode is on. Progress source=${progress.source}; state=${stateOutput}`);
      printProgressReport(keywordItems, progress, targetCount);
    } else {
      console.warn("Resume mode is on, but output file is empty or missing. Starting fresh and resetting progress state.");
    }
  }

  // 4000 篇量级下评论原始 JSON 很占内存，因此按笔记增量写入 CSV。
  const shouldAppendOutput = args.resume && existingOutputHasContent;
  const outputFile = await open(args.output, shouldAppendOutput ? "a" : "w");
  const stateFile = await open(stateOutput, shouldAppendOutput ? "a" : "w");
  let totalRows = 0;
  let totalNotes = 0;
  try {
    if (!shouldAppendOutput) {
      await outputFile.write(`${CSV_HEADERS.join(",")}\n`, "utf8");
    }
    if (args.resume && progress.source === "csv") {
      await writeProgressSnapshotToState(stateFile, keywordItems, progress);
      console.log(`Migrated detected CSV progress to ${stateOutput}`);
    }

    for (const keywordItem of keywordItems) {
      const doneNoteIds = getDoneNoteIds(progress, keywordItem.keyword);
      const failedNoteIds = getFailedNoteIds(progress, keywordItem.keyword);
      const attemptedNoteIds = getAttemptedNoteIds(progress, keywordItem.keyword);
      const remainingCount = Math.max(0, targetCount - attemptedNoteIds.size);
      console.log(
        `Searching keyword ${keywordItem.keyword_rank}/${keywordItems.length}: "${keywordItem.keyword}" target=${targetCount}, done=${doneNoteIds.size}, failed=${failedNoteIds.size}, remaining=${remainingCount}`,
      );
      if (remainingCount === 0) {
        console.log(`Keyword "${keywordItem.keyword}" already reached target. Skipping.`);
        continue;
      }

      let notes = [];
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
          skipNoteIds: attemptedNoteIds,
        });
      } catch (error) {
        console.error(`Failed to search keyword "${keywordItem.keyword}":`, error.message);
        continue;
      }

      if (notes.length === 0) {
        console.log(`No notes found for keyword "${keywordItem.keyword}".`);
        continue;
      }

      totalNotes += notes.length;
      const missingTokenCount = notes.filter((note) => !note.xsec_token).length;
      if (missingTokenCount > 0) {
        console.warn(
          `${missingTokenCount} note(s) for keyword "${keywordItem.keyword}" do not have xsec_token. Comment requests for those notes may fail.`,
        );
      }

      for (const note of notes) {
        console.log(
          `Fetching comments for keyword ${keywordItem.keyword_rank}/${keywordItems.length}, note #${note.search_rank}: ${note.note_id} ${note.note_title || ""}`.trim(),
        );
        try {
          const { rows, completed } = await fetchCommentsForNote({
            authorization,
            note,
            delayMs: args.delayMs,
            maxCommentPagesPerNote: args.maxCommentPagesPerNote,
            maxSubCommentPagesPerRoot: args.maxSubCommentPagesPerRoot,
            includeSubComments: args.includeSubComments,
            maxCommentsPerNote: args.maxCommentsPerNote,
          });
          if (!completed) {
            await writeNoteState(stateFile, note, "failed", rows.length, "comment request failed before page limit");
            addFailedNote(progress, note.keyword, note.note_id);
            continue;
          }
          if (rows.length > 0) {
            await outputFile.write(`${rowsToCsv(rows)}\n`, "utf8");
            totalRows += rows.length;
          }
          await writeNoteState(stateFile, note, "done", rows.length);
          addDoneNote(progress, note.keyword, note.note_id);
        } catch (error) {
          console.error(`Failed to fetch comments for note ${note.note_id}:`, error.message);
          await writeNoteState(stateFile, note, "failed", 0, error.message);
          addFailedNote(progress, note.keyword, note.note_id);
        }
        await sleep(args.delayMs);
      }
    }
  } finally {
    await outputFile.close();
    await stateFile.close();
  }

  console.log(`Done. Exported ${totalRows} comments from ${totalNotes} notes across ${keywordItems.length} keyword(s) to ${args.output}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
