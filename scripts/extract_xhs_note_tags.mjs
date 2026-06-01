#!/usr/bin/env node

import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { basename, join } from "node:path";

const API_ROOT = "https://api.tikhub.io/api/v1/xiaohongshu";

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const part = argv[i];
    if (!part.startsWith("--")) continue;
    const key = part.slice(2);
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) args[key] = true;
    else {
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
  let field = "";
  let inQuotes = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];
    if (char === "\"") {
      if (inQuotes && next === "\"") {
        field += "\"";
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
  if (field || row.length) {
    row.push(field);
    if (row.some((value) => value !== "")) rows.push(row);
  }
  return rows;
}

function readCsv(file) {
  const rows = parseCsv(readFileSync(file, "utf8"));
  const headers = rows[0] || [];
  return rows.slice(1).map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index] || ""])));
}

function csvEscape(value) {
  const text = value == null ? "" : String(value);
  if (!/[",\n\r]/.test(text)) return text;
  return `"${text.replaceAll("\"", "\"\"")}"`;
}

function writeCsv(file, rows, headers) {
  const lines = [headers.join(",")];
  for (const row of rows) lines.push(headers.map((header) => csvEscape(row[header])).join(","));
  writeFileSync(file, `${lines.join("\n")}\n`, "utf8");
}

function getAuthorization() {
  const value = process.env.TIKHUB_AUTHORIZATION || process.env.TIKHUB_BEARER_TOKEN || process.env.TIKHUB_TOKEN;
  if (!value) throw new Error("Missing TIKHUB_AUTHORIZATION.");
  return value.trim().toLowerCase().startsWith("bearer ") ? value.trim() : `Bearer ${value.trim()}`;
}

function pick(object, keys) {
  for (const key of keys) {
    const value = object?.[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return "";
}

function getPath(object, path) {
  return path.split(".").reduce((current, key) => current?.[key], object);
}

function firstArrayAtAnyPath(object, paths) {
  for (const path of paths) {
    const value = getPath(object, path);
    if (Array.isArray(value)) return value;
  }
  return null;
}

function deepFindArray(object, keyNames, depth = 0) {
  if (!object || typeof object !== "object" || depth > 8) return null;
  if (Array.isArray(object)) {
    for (const item of object) {
      const found = deepFindArray(item, keyNames, depth + 1);
      if (found) return found;
    }
    return null;
  }
  for (const [key, value] of Object.entries(object)) {
    if (keyNames.includes(key) && Array.isArray(value)) return value;
    const found = deepFindArray(value, keyNames, depth + 1);
    if (found) return found;
  }
  return null;
}

function extractDetailNote(json) {
  const noteList = firstArrayAtAnyPath(json, [
    "data.items",
    "data.notes",
    "data.note_list",
    "data.data.items",
    "data.data.notes",
  ]) || deepFindArray(json, ["items", "notes", "note_list"]);
  if (Array.isArray(noteList) && noteList.length > 0) return noteList[0]?.note_card || noteList[0]?.note || noteList[0];
  const direct = getPath(json, "data.data.note") || getPath(json, "data.note") || getPath(json, "note") || getPath(json, "data");
  return direct && typeof direct === "object" ? direct : null;
}

async function apiGet(path, query, authorization) {
  const url = new URL(`${API_ROOT}/${path}`);
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
  }
  let lastError;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      const response = await fetch(url, { headers: { Authorization: authorization } });
      const text = await response.text();
      let json;
      try {
        json = text ? JSON.parse(text) : {};
      } catch {
        json = { raw_text: text };
      }
      if (!response.ok) throw new Error(`HTTP ${response.status} ${response.statusText}`);
      return json;
    } catch (error) {
      lastError = error;
      await sleep(400 * attempt);
    }
  }
  throw lastError;
}

async function fetchNoteDetail(note, authorization) {
  const endpoints = ["app_v2/get_image_note_detail", "app_v2/get_video_note_detail"];
  const errors = [];
  for (const endpoint of endpoints) {
    try {
      const json = await apiGet(endpoint, { note_id: note.note_id }, authorization);
      const detail = extractDetailNote(json);
      if (detail) return { detail_status: "ok", detail, raw: json };
      errors.push(`${endpoint}: no detail`);
    } catch (error) {
      errors.push(`${endpoint}: ${error.message}`);
    }
  }
  return { detail_status: "failed", detail: null, raw: null, error: errors.join(" | ") };
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function normalizeTag(tag) {
  return String(tag || "")
    .replace(/\[话题\]/g, "")
    .replace(/^#+|#+$/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function extractTagName(object) {
  if (!object || typeof object !== "object") return "";
  return normalizeTag(pick(object, [
    "name",
    "tag_name",
    "tagName",
    "title",
    "topic_name",
    "topicName",
    "hashtag_name",
    "hashtagName",
    "text",
  ]));
}

function collectStructuredTags(object, output = []) {
  if (!object || typeof object !== "object") return output;
  if (Array.isArray(object)) {
    for (const item of object) collectStructuredTags(item, output);
    return output;
  }
  for (const [key, value] of Object.entries(object)) {
    if (/tag|topic|hash/i.test(key)) {
      if (Array.isArray(value)) {
        for (const item of value) {
          const name = typeof item === "string" ? normalizeTag(item) : extractTagName(item);
          if (name) output.push(name);
        }
      } else if (typeof value === "string") {
        const name = normalizeTag(value);
        if (name && name.length <= 40) output.push(name);
      } else if (value && typeof value === "object") {
        const name = extractTagName(value);
        if (name) output.push(name);
      }
    }
    collectStructuredTags(value, output);
  }
  return output;
}

function extractHashTagsFromText(text) {
  const tags = [];
  const value = String(text || "");
  for (const match of value.matchAll(/#([^#\n\r]{1,50}?)(?:\[话题\])?#/g)) tags.push(normalizeTag(match[1]));
  for (const match of value.matchAll(/#([^\s#，。；;！!？?、]{1,40})/g)) tags.push(normalizeTag(match[1]));
  return tags.filter((tag) => tag && tag.length <= 40 && !/^https?:/i.test(tag));
}

function extractTags(detail) {
  const desc = pick(detail, ["desc", "description"]) || "";
  const structuredTags = collectStructuredTags(detail);
  const textTags = extractHashTagsFromText(desc);
  return [...new Set([...structuredTags, ...textTags].map(normalizeTag).filter(Boolean))];
}

function extractDesc(detail) {
  return pick(detail, ["desc", "description"]) || "";
}

function uniqueNotes(rows) {
  const notes = new Map();
  for (const row of rows) {
    if (!row.note_id) continue;
    if (notes.has(row.note_id)) {
      const note = notes.get(row.note_id);
      for (const text of [row.note_title || "", row.note_desc || ""].filter(Boolean)) {
        if (!note.visible_texts.includes(text)) note.visible_texts.push(text);
      }
      continue;
    }
    notes.set(row.note_id, {
      keyword: row.keyword || "",
      keyword_rank: row.keyword_rank || "",
      battle_category: row.battle_category || "",
      search_rank: row.search_rank || "",
      note_id: row.note_id,
      note_url: row.note_url || "",
      note_title: row.note_title || "",
      note_author_name: row.note_author_name || "",
      visible_texts: [row.note_title || "", row.note_desc || ""].filter(Boolean),
    });
  }
  return [...notes.values()];
}

function loadCache(file) {
  const cache = new Map();
  if (!existsSync(file)) return cache;
  for (const line of readFileSync(file, "utf8").split(/\n/).filter(Boolean)) {
    try {
      const item = JSON.parse(line);
      if (item.note_id) cache.set(item.note_id, item);
    } catch {
      // Ignore broken cache lines so a partial run can still resume.
    }
  }
  return cache;
}

function appendCache(file, item) {
  writeFileSync(file, `${JSON.stringify(item)}\n`, { flag: "a" });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const input = args.input;
  if (!input) throw new Error("Usage: node scripts/extract_xhs_note_tags.mjs --input comments.csv --out-dir local_data/xhs_note_tag_analysis");
  const outDir = args["out-dir"] || "local_data/xhs_note_tag_analysis";
  const limit = Number.parseInt(args.limit || "0", 10);
  const delayMs = Number.parseInt(args["delay-ms"] || "300", 10);
  const concurrency = Math.max(1, Number.parseInt(args.concurrency || "2", 10));
  const visibleOnly = Boolean(args["visible-only"]);
  mkdirSync(outDir, { recursive: true });

  const notes = uniqueNotes(readCsv(input));
  const targetNotes = limit > 0 ? notes.slice(0, limit) : notes;
  const cacheFile = args.cache || join(outDir, `${basename(input)}.note_detail_tags.jsonl`);
  const cache = loadCache(cacheFile);
  const authorization = visibleOnly ? "" : getAuthorization();
  let nextIndex = 0;

  async function worker(workerId) {
    while (true) {
      const note = targetNotes[nextIndex];
      nextIndex += 1;
      if (!note) break;
      if (cache.has(note.note_id)) continue;
      if (visibleOnly) {
        const item = {
          ...note,
          detail_status: "visible_only",
          error: "",
          note_desc: "",
          tags: [...new Set(note.visible_texts.flatMap(extractHashTagsFromText))],
        };
        cache.set(note.note_id, item);
        appendCache(cacheFile, item);
        continue;
      }
      const result = await fetchNoteDetail(note, authorization);
      const detail = result.detail || {};
      const item = {
        ...note,
        detail_status: result.detail_status,
        error: result.error || "",
        note_desc: extractDesc(detail),
        tags: result.detail ? extractTags(detail) : [],
      };
      cache.set(note.note_id, item);
      appendCache(cacheFile, item);
      console.log(`[worker ${workerId}] ${cache.size}/${targetNotes.length} ${note.note_id} tags=${item.tags.length} ${item.tags.slice(0, 5).join("|")}`);
      await sleep(delayMs);
    }
  }

  await Promise.all(Array.from({ length: Math.min(concurrency, targetNotes.length) }, (_, index) => worker(index + 1)));

  const analyzed = targetNotes.map((note) => cache.get(note.note_id)).filter(Boolean);
  const tagToNotes = new Map();
  const noteTagRows = [];
  for (const note of analyzed) {
    const tags = [...new Set(note.tags || [])];
    noteTagRows.push({
      note_id: note.note_id,
      note_title: note.note_title,
      keyword: note.keyword,
      tag_count: tags.length,
      tags: tags.join(";"),
      note_url: note.note_url,
      note_desc: note.note_desc || "",
      detail_status: note.detail_status || "",
    });
    for (const tag of tags) {
      if (!tagToNotes.has(tag)) tagToNotes.set(tag, new Set());
      tagToNotes.get(tag).add(note.note_id);
    }
  }

  const topRows = [...tagToNotes.entries()]
    .map(([tag, ids]) => ({ tag, note_count: ids.size, percent: `${((ids.size / analyzed.length) * 100).toFixed(1)}%` }))
    .sort((a, b) => b.note_count - a.note_count || a.tag.localeCompare(b.tag, "zh-CN"));

  const topFile = join(outDir, "tag_top.csv");
  const noteTagsFile = join(outDir, "note_tags.csv");
  const reportFile = join(outDir, "tag_top_report.md");
  writeCsv(topFile, topRows, ["tag", "note_count", "percent"]);
  writeCsv(noteTagsFile, noteTagRows, ["note_id", "note_title", "keyword", "tag_count", "tags", "note_url", "note_desc", "detail_status"]);

  const report = [
    "# 小红书帖子话题 Top",
    "",
    `- 来源：\`${input}\``,
    `- 去重帖子数：${notes.length}`,
    `- 本次分析帖子数：${analyzed.length}`,
    `- 有话题帖子数：${noteTagRows.filter((row) => row.tag_count > 0).length}`,
    "",
    "| 排名 | 话题 | 帖子数 | 占比 |",
    "| --- | --- | ---: | ---: |",
    ...topRows.slice(0, 20).map((row, index) => `| ${index + 1} | ${row.tag} | ${row.note_count} | ${row.percent} |`),
    "",
    "## 产物",
    `- \`${topFile}\``,
    `- \`${noteTagsFile}\``,
    `- \`${cacheFile}\``,
    "",
  ].join("\n");
  writeFileSync(reportFile, report, "utf8");

  console.log(JSON.stringify({
    source: input,
    unique_notes: notes.length,
    analyzed_notes: analyzed.length,
    notes_with_tags: noteTagRows.filter((row) => row.tag_count > 0).length,
    top5: topRows.slice(0, 5),
    outputs: { topFile, noteTagsFile, reportFile, cacheFile },
  }, null, 2));
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
