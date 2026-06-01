#!/usr/bin/env node

import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

const API_ROOT = "https://api.tikhub.io/api/v1/xiaohongshu";
const DEFAULT_KEYWORD = "a2";
const DEFAULT_OUTPUT = "xhs_a2_notes.csv";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function parseArgs(argv) {
  const args = {
    keyword: DEFAULT_KEYWORD,
    output: DEFAULT_OUTPUT,
    limit: 0,
    maxPages: 0,
    searchPageSize: 20,
    delayMs: 800,
    sort: "general",
    noteType: "不限",
    timeFilter: "不限",
    source: "explore_feed",
    aiMode: 0,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];

    if (arg === "--keyword") args.keyword = requiredValue(arg, next, ++i);
    else if (arg === "--output") args.output = requiredValue(arg, next, ++i);
    else if (arg === "--limit") args.limit = parseNonNegativeInt(arg, next, ++i);
    else if (arg === "--max-pages") args.maxPages = parseNonNegativeInt(arg, next, ++i);
    else if (arg === "--search-page-size") args.searchPageSize = parsePositiveInt(arg, next, ++i);
    else if (arg === "--delay-ms") args.delayMs = parseNonNegativeInt(arg, next, ++i);
    else if (arg === "--sort") args.sort = requiredValue(arg, next, ++i);
    else if (arg === "--note-type") args.noteType = requiredValue(arg, next, ++i);
    else if (arg === "--time-filter") args.timeFilter = requiredValue(arg, next, ++i);
    else if (arg === "--source") args.source = requiredValue(arg, next, ++i);
    else if (arg === "--ai-mode") args.aiMode = parseNonNegativeInt(arg, next, ++i);
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
  TIKHUB_BEARER_TOKEN="<token>" node crawl_xhs_notes.mjs --keyword "a2" --limit 0 --max-pages 0 --output batch_a2_all/a2_notes.csv

Options:
  --keyword <text>             Search keyword. Default: ${DEFAULT_KEYWORD}
  --output <path>              CSV output path. Default: ${DEFAULT_OUTPUT}
  --limit <n>                  Unique note limit. 0 means no cap. Default: 0
  --max-pages <n>              Search page cap. 0 means no cap. Default: 0
  --search-page-size <n>       Search page size assumption. Default: 20
  --delay-ms <n>               Delay between API calls. Default: 800
  --sort <value>               App-V2 search sort_type. Default: general
  --note-type <value>          App-V2 search note_type. Default: 不限
  --time-filter <value>        App-V2 search time_filter. Default: 不限
  --source <value>             App-V2 search source. Default: explore_feed
  --ai-mode <n>                App-V2 search ai_mode. Default: 0
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
      if (error.nonRetryable || attempt === 4) throw error;
    }

    console.warn(`Retrying ${redactUrl(url)} after error: ${lastError.message.split("\n")[0]}`);
    await sleep(1000 * attempt * attempt);
  }

  throw lastError;
}

function summarizeApiError(text) {
  try {
    const json = JSON.parse(text);
    const detail = json?.detail || json;
    const parts = [
      detail?.message_zh,
      detail?.message,
      detail?.router ? `router: ${detail.router}` : "",
      detail?.request_id ? `request_id: ${detail.request_id}` : "",
    ].filter(Boolean);
    if (parts.length > 0) return parts.join("\n");
  } catch {
    // Fall through.
  }
  return text.slice(0, 800);
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

function extractNote(raw, index) {
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
    xsec_token: xsecToken || "",
    note_url: buildNoteUrl(noteId, xsecToken),
    note_title: pick(source, ["title", "display_title", "desc"]) || "",
    note_author_id: pick(user, ["user_id", "userId", "id", "userid"]) || "",
    note_author_name: pick(user, ["nickname", "nick_name", "nickName", "name"]) || "",
    raw_search_json: JSON.stringify(raw),
  };
}

function pick(object, keys) {
  if (!object || typeof object !== "object") return undefined;
  for (const key of keys) {
    if (object[key] !== undefined && object[key] !== null) return object[key];
  }
  return undefined;
}

function buildNoteUrl(noteId, xsecToken) {
  if (!noteId) return "";
  const url = new URL(`https://www.xiaohongshu.com/explore/${noteId}`);
  if (xsecToken) url.searchParams.set("xsec_token", xsecToken);
  url.searchParams.set("xsec_source", "pc_search");
  return url.toString();
}

function extractHasMore(json) {
  const candidates = [
    "data.has_more",
    "data.hasMore",
    "data.has_next",
    "data.data.has_more",
    "data.data.hasMore",
    "data.data.has_next",
    "has_more",
    "hasMore",
    "has_next",
  ];

  for (const path of candidates) {
    const value = getPath(json, path);
    if (typeof value === "boolean") return value;
    if (value === 0 || value === 1) return Boolean(value);
  }

  return undefined;
}

async function fetchNotes({
  authorization,
  keyword,
  limit,
  maxPages,
  searchPageSize,
  sort,
  noteType,
  timeFilter,
  source,
  aiMode,
  delayMs,
  onRowChange,
}) {
  const notes = [];
  const seen = new Set();
  const duplicateCountsByNoteId = new Map();
  const notesById = new Map();
  let duplicateCount = 0;
  let page = 1;
  let searchId = "";
  let searchSessionId = "";

  while (true) {
    if (limit > 0 && notes.length >= limit) break;
    if (maxPages > 0 && page > maxPages) break;

    const { url, json } = await apiGet(
      "app_v2/search_notes",
      {
        keyword,
        page,
        sort_type: sort,
        note_type: noteType,
        time_filter: timeFilter,
        search_id: searchId,
        search_session_id: searchSessionId,
        source,
        ai_mode: aiMode,
      },
      authorization,
    );
    const items = extractSearchItems(json);

    if (!Array.isArray(items)) {
      console.error("Could not find notes array in search response. Top-level keys:", Object.keys(json));
      console.error("Request URL:", url);
      throw new Error("Search response shape is not recognized. Inspect the response and update extractSearchItems().");
    }

    if (items.length === 0) {
      console.log(`Search page ${page}: 0 items. Stop.`);
      break;
    }

    let added = 0;
    for (const item of items) {
      const note = extractNote(item, notes.length);
      if (!note.note_id) {
        console.warn("Skipping a search item without note_id:", JSON.stringify(item).slice(0, 300));
        continue;
      }
      if (seen.has(note.note_id)) {
        duplicateCount += 1;
        const noteDuplicateCount = (duplicateCountsByNoteId.get(note.note_id) || 0) + 1;
        duplicateCountsByNoteId.set(note.note_id, noteDuplicateCount);
        const existingNote = notesById.get(note.note_id);
        if (existingNote) existingNote.duplicate_count = noteDuplicateCount;
        if (onRowChange) await onRowChange({ type: "duplicate", row: existingNote, rows: notes });
        continue;
      }
      seen.add(note.note_id);
      const row = {
        keyword,
        sort,
        note_type_filter: noteType,
        time_filter: timeFilter,
        search_page: page,
        duplicate_count: 0,
        ...note,
      };
      notes.push(row);
      notesById.set(note.note_id, row);
      if (onRowChange) await onRowChange({ type: "add", row, rows: notes });
      added += 1;
      if (limit > 0 && notes.length >= limit) break;
    }

    searchId = searchId || getPath(json, "data.search_id") || getPath(json, "data.data.search_id") || "";
    searchSessionId =
      searchSessionId ||
      getPath(json, "data.search_session_id") ||
      getPath(json, "data.data.search_session_id") ||
      "";
    const nextPage = getPath(json, "data.next_page");
    const hasMore = extractHasMore(json);
    const nextPageNumber = Number(nextPage);
    const hasUsableNextPage =
      nextPage !== undefined && nextPage !== null && nextPage !== "" && Number.isFinite(nextPageNumber) && nextPageNumber !== page;

    console.log(
      `Search page ${page}: ${items.length} items, added ${added}, unique ${notes.length}, duplicates ${duplicateCount}, hasMore=${hasMore ?? "unknown"}, nextPage=${nextPage ?? "unknown"}.`,
    );

    if (hasMore === false) break;
    if (hasUsableNextPage) {
      page = nextPageNumber;
    } else if (hasMore === true) {
      page += 1;
    } else if (items.length < searchPageSize) {
      break;
    } else {
      page += 1;
    }
    await sleep(delayMs);
  }

  return { notes, duplicateCount, duplicateCountsByNoteId, lastPage: page };
}

function getCsvHeaders() {
  return [
    "keyword",
    "sort",
    "note_type_filter",
    "time_filter",
    "search_page",
    "search_rank",
    "duplicate_count",
    "note_id",
    "xsec_token",
    "note_url",
    "note_title",
    "note_author_id",
    "note_author_name",
    "raw_search_json",
  ];
}

function toCsv(rows, headers = getCsvHeaders()) {
  return [
    headers.join(","),
    ...rows.map((row) => headers.map((header) => csvEscape(row[header])).join(",")),
  ].join("\n");
}

function rowToCsvLine(row, headers = getCsvHeaders()) {
  return headers.map((header) => csvEscape(row[header])).join(",");
}

async function prepareCsvOutput(output, headers = getCsvHeaders()) {
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, `${headers.join(",")}\n`, "utf8");
}

async function rewriteCsvOutput(output, rows, headers = getCsvHeaders()) {
  await writeFile(output, `${toCsv(rows, headers)}\n`, "utf8");
}

function csvEscape(value) {
  const text = value === undefined || value === null ? "" : String(value).replace(/\r?\n/g, " ");
  if (/[",\n\r]/.test(text)) return `"${text.replaceAll('"', '""')}"`;
  return text;
}

async function main() {
  await loadDotEnv();
  const args = parseArgs(process.argv.slice(2));
  const authorization = getAuthorization();

  console.log(
    `Notes-only mode; keyword="${args.keyword}"; limit=${args.limit || "no cap"}; maxPages=${args.maxPages || "no cap"}; sort=${args.sort}; noteType=${args.noteType}; timeFilter=${args.timeFilter}; source=${args.source}; aiMode=${args.aiMode}`,
  );

  const headers = getCsvHeaders();
  await prepareCsvOutput(args.output, headers);

  const { notes, duplicateCount, duplicateCountsByNoteId, lastPage } = await fetchNotes({
    authorization,
    keyword: args.keyword,
    limit: args.limit,
    maxPages: args.maxPages,
    searchPageSize: args.searchPageSize,
    sort: args.sort,
    noteType: args.noteType,
    timeFilter: args.timeFilter,
    source: args.source,
    aiMode: args.aiMode,
    delayMs: args.delayMs,
    onRowChange: async ({ type, row, rows }) => {
      if (type === "add") {
        await appendFile(args.output, `${rowToCsvLine(row, headers)}\n`, "utf8");
      } else if (type === "duplicate" && row) {
        await rewriteCsvOutput(args.output, rows, headers);
      }
    },
  });

  console.log(
    `Done. Exported ${notes.length} unique notes to ${args.output}. Duplicates skipped: ${duplicateCount}. Repeated note_ids: ${duplicateCountsByNoteId.size}. Last page: ${lastPage}.`,
  );
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
