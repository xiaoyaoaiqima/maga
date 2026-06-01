#!/usr/bin/env node

import { appendFile, readFile, writeFile } from "node:fs/promises";

const API_ROOT = "https://api.tikhub.io/api/v1/xiaohongshu";
const DEFAULT_KEYWORD = "a2至初到货了";
const DEFAULT_OUTPUT = "xhs_note_details_comments.csv";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function parseArgs(argv) {
  const args = {
    keyword: DEFAULT_KEYWORD,
    output: DEFAULT_OUTPUT,
    full: false,
    limit: 200,
    testNotes: 2,
    searchPageSize: 20,
    delayMs: 800,
    maxCommentPagesPerNote: 2,
    maxCommentsPerNote: 0,
    concurrency: 1,
    sort: "general",
    noteType: "不限",
    timeFilter: "不限",
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
    else if (arg === "--max-comments-per-note") args.maxCommentsPerNote = parseNonNegativeInt(arg, next, ++i);
    else if (arg === "--concurrency") args.concurrency = parsePositiveInt(arg, next, ++i);
    else if (arg === "--sort") args.sort = requiredValue(arg, next, ++i);
    else if (arg === "--note-type") args.noteType = requiredValue(arg, next, ++i);
    else if (arg === "--time-filter") args.timeFilter = requiredValue(arg, next, ++i);
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
  --max-comment-pages-per-note <n>    Main comment page cap. 0 means no cap. Default: 2
  --max-comments-per-note <n>         Cap exported comments/replies per note. 0 means no cap.
  --concurrency <number>              Notes to fetch in parallel. Default: 1
  --sort <value>                      App-V2 search sort_type. Default: general
  --note-type <value>                 App-V2 search note_type. Default: 不限
  --time-filter <value>               App-V2 search time_filter. Default: 不限
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

async function fetchNotes({ authorization, keyword, targetCount, searchPageSize, sort, noteType, timeFilter, delayMs }) {
  const notes = [];
  const seen = new Set();
  let page = 1;
  let searchId = "";
  let searchSessionId = "";

  while (notes.length < targetCount) {
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
      },
      authorization,
    );
    const items = extractSearchItems(json);

    if (!Array.isArray(items)) {
      console.error("Could not find notes array in search response. Top-level keys:", Object.keys(json));
      console.error("Request URL:", url);
      throw new Error("Search response shape is not recognized. Inspect the response and update extractSearchItems().");
    }

    if (items.length === 0) break;

    for (const item of items) {
      const note = extractSearchNote(item, notes.length);
      note.keyword = keyword;
      if (!note.note_id) {
        console.warn("Skipping a search item without note_id:", JSON.stringify(item).slice(0, 300));
        continue;
      }
      if (seen.has(note.note_id)) continue;
      seen.add(note.note_id);
      notes.push(note);
      if (notes.length >= targetCount) break;
    }

    searchId = getPath(json, "data.search_id") || searchId;
    searchSessionId = getPath(json, "data.search_session_id") || searchSessionId;
    const nextPage = getPath(json, "data.next_page");

    console.log(`Search page ${page}: ${items.length} items, ${notes.length}/${targetCount} usable notes.`);
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
      if (detail) {
        return {
          note: mergeDetailIntoNote(note, detail),
          comments: extractCommentItems(json) || [],
        };
      }
      errors.push(`${endpoint}: response had no note detail`);
    } catch (error) {
      errors.push(`${endpoint}: ${error.message.split("\n")[0]}`);
    }
  }

  console.warn(`  Failed note detail for #${note.search_rank}/${note.note_id}; using search result only. ${errors.join(" | ")}`);
  return {
    note: {
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
    },
    comments: [],
  };
}

async function fetchCommentsForNote({ authorization, note, delayMs, maxCommentPagesPerNote, maxCommentsPerNote }) {
  const rows = [];
  const seenCommentIds = new Set();
  let cursor = "";
  let page = 1;

  if (!note.xsec_token) {
    console.warn(`  Note ${note.search_rank}/${note.note_id} has no xsec_token; skipping comments.`);
    return rows;
  }

  const addComment = (comment) => {
    const commentId = pick(comment, ["id", "comment_id", "commentId"]);
    if (commentId) {
      if (seenCommentIds.has(commentId)) return false;
      seenCommentIds.add(commentId);
    }
    rows.push(makeCommentRow(comment, note, rows.length));
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
      addComment(item);
      for (const subComment of item?.subComments || item?.sub_comments || []) addComment(subComment);
      if (maxCommentsPerNote > 0 && rows.length >= maxCommentsPerNote) break;
    }

    const nextCursor = extractNextCursor(json);
    const hasMore = extractHasMore(json, items.length);
    const addedRows = rows.length - beforeRowCount;
    console.log(
      `  Comments page ${page} for note ${note.search_rank}/${note.note_id}: +${items.length}, added ${addedRows}, total ${rows.length}, hasMore=${hasMore}`,
    );

    if (!hasMore || !nextCursor || nextCursor === cursor) break;
    if (addedRows === 0) break;
    if (maxCommentsPerNote > 0 && rows.length >= maxCommentsPerNote) break;
    if (maxCommentPagesPerNote > 0 && page >= maxCommentPagesPerNote) break;

    cursor = nextCursor;
    page += 1;
    await sleep(delayMs);
  }

  return rows;
}

function getCsvHeaders() {
  return [
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
  const authorization = getAuthorization();
  const targetCount = args.full ? args.limit : args.testNotes;

  console.log(`Mode: ${args.full ? "full" : "test"}; keyword="${args.keyword}"; target notes=${targetCount}`);
  if (!args.full) {
    console.log("Test mode is on. Add --full after validating 1-2 notes to fetch more notes.");
  }

  const notes = await fetchNotes({
    authorization,
    keyword: args.keyword,
    targetCount,
    searchPageSize: args.searchPageSize,
    sort: args.sort,
    noteType: args.noteType,
    timeFilter: args.timeFilter,
    delayMs: args.delayMs,
  });

  if (notes.length === 0) {
    console.log("No notes found. Nothing to export.");
    return;
  }

  const headers = getCsvHeaders();
  await writeFile(args.output, `${headers.join(",")}\n`, "utf8");

  let nextNoteIndex = 0;
  const workerCount = Math.min(args.concurrency, notes.length);

  async function runWorker(workerId) {
    while (true) {
      const searchNote = notes[nextNoteIndex];
      nextNoteIndex += 1;
      if (!searchNote) break;

      console.log(`[worker ${workerId}] Fetching detail for #${searchNote.search_rank}: ${searchNote.note_id} ${searchNote.note_title || ""}`.trim());
      const { note } = await fetchNoteDetail({ authorization, note: searchNote });

      console.log(`[worker ${workerId}] Fetching comments for #${note.search_rank}: ${note.note_id} ${note.note_title || ""}`.trim());
      const rows = await fetchCommentsForNote({
        authorization,
        note,
        delayMs: args.delayMs,
        maxCommentPagesPerNote: args.maxCommentPagesPerNote,
        maxCommentsPerNote: args.maxCommentsPerNote,
      });

      if (rows.length > 0) {
        await appendFile(args.output, `${rows.map((row) => rowToCsvLine(row, headers)).join("\n")}\n`, "utf8");
      }
      await sleep(args.delayMs);
    }
  }

  await Promise.all(Array.from({ length: workerCount }, (_, index) => runWorker(index + 1)));

  console.log(`Done. Processed ${notes.length} notes to ${args.output}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
