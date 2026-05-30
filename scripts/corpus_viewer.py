#!/usr/bin/env python3
"""Local CSV corpus viewer for keyword search and preview."""

from __future__ import annotations

import argparse
import csv
import html
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 8788
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".local",
    ".playwright-mcp",
    "__pycache__",
    "node_modules",
    ".pnpm-store",
}
PRIMARY_COLUMNS = (
    "评论切角",
    "产品使用体验",
    "子关键词",
    "关键词",
    "评论分类",
    "产品使用体验",
)
TEXT_COLUMNS = ("语料", "评论示例", "评论补充", "表述参考", "正文", "标题")


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>语料检索</title>
  <style>
    :root {
      --bg: #f5f7fb;
      --panel: #ffffff;
      --line: #d9e1ec;
      --text: #1f2a37;
      --muted: #64748b;
      --accent: #0f766e;
      --accent-weak: #e8f4f2;
      --warn: #9a3412;
      --mark: #fff1a6;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--text);
      background: var(--bg);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
      letter-spacing: 0;
    }
    header {
      display: flex;
      gap: 16px;
      align-items: center;
      justify-content: space-between;
      padding: 14px 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 {
      margin: 0;
      font-size: 18px;
      font-weight: 650;
    }
    .meta {
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }
    .toolbar {
      display: grid;
      grid-template-columns: minmax(220px, 1fr) minmax(180px, 280px) auto auto;
      gap: 10px;
      padding: 12px 18px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfe;
    }
    .result-bar {
      padding: 8px 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      color: var(--muted);
      font-size: 13px;
    }
    input, select, button {
      min-height: 36px;
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--text);
      font: inherit;
    }
    input, select {
      width: 100%;
      padding: 0 10px;
      border-radius: 6px;
    }
    button {
      padding: 0 12px;
      border-radius: 6px;
      cursor: pointer;
    }
    button.primary {
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
    }
    button:disabled {
      opacity: .45;
      cursor: not-allowed;
    }
    main {
      display: grid;
      grid-template-columns: minmax(360px, 42%) minmax(420px, 1fr);
      min-height: calc(100vh - 143px);
    }
    .results {
      border-right: 1px solid var(--line);
      background: var(--panel);
      overflow: auto;
      max-height: calc(100vh - 143px);
    }
    .detail {
      overflow: auto;
      max-height: calc(100vh - 143px);
      padding: 16px 18px 28px;
    }
    .row {
      display: block;
      width: 100%;
      min-height: 88px;
      padding: 12px 14px;
      text-align: left;
      border: 0;
      border-bottom: 1px solid var(--line);
      border-radius: 0;
      background: var(--panel);
    }
    .row:hover,
    .row.active {
      background: var(--accent-weak);
    }
    .row-title {
      display: flex;
      gap: 8px;
      align-items: baseline;
      font-weight: 650;
      line-height: 1.35;
    }
    .row-title span {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .badge {
      flex: 0 0 auto;
      padding: 2px 6px;
      border: 1px solid var(--line);
      border-radius: 999px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 500;
    }
    .row-sub,
    .row-preview {
      margin-top: 6px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }
    .row-preview {
      color: #475569;
      display: -webkit-box;
      overflow: hidden;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
    }
    .empty {
      padding: 36px 18px;
      color: var(--muted);
      text-align: center;
    }
    .detail-head {
      display: flex;
      gap: 12px;
      align-items: flex-start;
      justify-content: space-between;
      margin-bottom: 12px;
    }
    .detail-title {
      margin: 0;
      font-size: 18px;
      line-height: 1.35;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }
    .info {
      display: grid;
      grid-template-columns: 92px 1fr;
      gap: 6px 10px;
      margin: 12px 0 14px;
      padding: 12px 0;
      border-top: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
      color: var(--muted);
      font-size: 13px;
    }
    .info strong {
      color: var(--text);
      font-weight: 550;
    }
    pre {
      margin: 0;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--text);
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.62;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 13px;
    }
    mark {
      background: var(--mark);
      padding: 0 2px;
      border-radius: 2px;
    }
    .toast {
      position: fixed;
      right: 18px;
      bottom: 18px;
      display: none;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 8px 24px rgb(15 23 42 / 12%);
      color: var(--accent);
    }
    .toast.show { display: block; }
    .status-warn { color: var(--warn); }
    @media (max-width: 860px) {
      header {
        align-items: flex-start;
        flex-direction: column;
        gap: 6px;
      }
      .meta { white-space: normal; }
      .toolbar {
        grid-template-columns: 1fr;
      }
      main {
        grid-template-columns: 1fr;
      }
      .results {
        max-height: 42vh;
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }
      .detail {
        max-height: none;
      }
    }
  </style>
</head>
<body>
  <header>
    <h1>语料检索</h1>
    <div class="meta" id="stats">正在扫描 CSV...</div>
  </header>
  <section class="toolbar">
    <input id="query" autocomplete="off" placeholder="搜关键词、标题、语料内容，例如：容易生病 品牌忠实老客" />
    <select id="fileFilter" aria-label="筛选文件"></select>
    <button id="reload">重新扫描</button>
    <button id="copyLocation" class="primary" disabled>复制定位</button>
  </section>
  <section class="result-bar" id="resultCount">当前匹配 0 条</section>
  <main>
    <section class="results" id="results"></section>
    <section class="detail" id="detail">
      <div class="empty">输入关键词，或从左侧选择一条语料。</div>
    </section>
  </main>
  <div class="toast" id="toast"></div>
  <script>
    const state = {
      rows: [],
      files: [],
      selectedId: null,
      visible: [],
    };
    const els = {
      stats: document.querySelector("#stats"),
      query: document.querySelector("#query"),
      fileFilter: document.querySelector("#fileFilter"),
      reload: document.querySelector("#reload"),
      copyLocation: document.querySelector("#copyLocation"),
      resultCount: document.querySelector("#resultCount"),
      results: document.querySelector("#results"),
      detail: document.querySelector("#detail"),
      toast: document.querySelector("#toast"),
    };

    const escapeHtml = (value) => String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");

    const terms = () => els.query.value
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .map((term) => term.toLowerCase());

    const highlight = (text) => {
      let html = escapeHtml(text);
      for (const term of terms()) {
        const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        if (!escaped) continue;
        html = html.replace(new RegExp(`(${escaped})`, "ig"), "<mark>$1</mark>");
      }
      return html;
    };

    const rowText = (row) => [
      row.file,
      row.key,
      row.title,
      row.corpus,
      row.extra_text,
    ].join("\n").toLowerCase();

    const showToast = (message) => {
      els.toast.textContent = message;
      els.toast.classList.add("show");
      window.setTimeout(() => els.toast.classList.remove("show"), 1400);
    };

    const copyText = async (text, label) => {
      await navigator.clipboard.writeText(text);
      showToast(`${label}已复制`);
    };

    const selectedRow = () => state.rows.find((row) => row.id === state.selectedId);

    const applyFilters = () => {
      const q = terms();
      const file = els.fileFilter.value;
      state.visible = state.rows.filter((row) => {
        if (file && row.file !== file) return false;
        if (!q.length) return true;
        const text = rowText(row);
        return q.every((term) => text.includes(term));
      });
      const fileText = els.fileFilter.value ? ` · ${els.fileFilter.value}` : "";
      els.resultCount.textContent = `当前匹配 ${state.visible.length} 条${fileText}`;
      renderResults();
      if (!state.visible.find((row) => row.id === state.selectedId)) {
        state.selectedId = state.visible[0]?.id ?? null;
      }
      renderDetail();
    };

    const renderFileFilter = () => {
      const current = els.fileFilter.value;
      els.fileFilter.innerHTML = '<option value="">全部 CSV 文件</option>' + state.files
        .map((file) => `<option value="${escapeHtml(file)}">${escapeHtml(file)}</option>`)
        .join("");
      if (state.files.includes(current)) els.fileFilter.value = current;
    };

    const renderResults = () => {
      if (!state.visible.length) {
        els.results.innerHTML = '<div class="empty">没有匹配结果。</div>';
        return;
      }
      els.results.innerHTML = state.visible.map((row) => `
        <button class="row ${row.id === state.selectedId ? "active" : ""}" data-id="${row.id}">
          <div class="row-title">
            <span>${highlight(row.key || "(空关键词)")}</span>
            <em class="badge">#${row.csv_row}</em>
          </div>
          <div class="row-sub">${escapeHtml(row.file)} · 行 ${row.line}</div>
          <div class="row-preview">${highlight(row.title || row.corpus_preview || row.corpus)}</div>
        </button>
      `).join("");
    };

    const renderDetail = () => {
      const row = selectedRow();
      els.copyLocation.disabled = !row;
      if (!row) {
        els.detail.innerHTML = '<div class="empty">没有选中的语料。</div>';
        return;
      }
      const location = `${row.file}:${row.line} · CSV第${row.csv_row}条`;
      els.detail.innerHTML = `
        <div class="detail-head">
          <h2 class="detail-title">${highlight(row.title || row.key || "(空标题)")}</h2>
          <div class="actions">
            <button data-action="copy-key">复制关键词</button>
            <button data-action="copy-corpus">复制语料</button>
            <button data-action="copy-row">复制整行</button>
          </div>
        </div>
        <div class="info">
          <span>关键词</span><strong>${highlight(row.key)}</strong>
          <span>文件</span><strong>${escapeHtml(row.file)}</strong>
          <span>位置</span><strong>${escapeHtml(location)}</strong>
          <span>列</span><strong>${escapeHtml(row.columns.join("、"))}</strong>
        </div>
        <pre>${highlight(row.corpus || row.full_text)}</pre>
      `;
    };

    const loadRows = async () => {
      els.stats.textContent = "正在扫描 CSV...";
      const response = await fetch("/api/rows");
      const payload = await response.json();
      state.rows = payload.rows;
      state.files = payload.files;
      renderFileFilter();
      els.stats.innerHTML = `已加载 ${payload.rows.length} 条 · ${payload.files.length} 个文件 · ${escapeHtml(payload.updated_at)}`;
      applyFilters();
    };

    els.results.addEventListener("click", (event) => {
      const button = event.target.closest(".row");
      if (!button) return;
      state.selectedId = button.dataset.id;
      renderResults();
      renderDetail();
    });

    els.detail.addEventListener("click", async (event) => {
      const action = event.target.dataset.action;
      if (!action) return;
      const row = selectedRow();
      if (!row) return;
      if (action === "copy-key") await copyText(row.key, "关键词");
      if (action === "copy-corpus") await copyText(row.corpus || row.full_text, "语料");
      if (action === "copy-row") await copyText(row.raw_joined, "整行");
    });

    els.copyLocation.addEventListener("click", async () => {
      const row = selectedRow();
      if (!row) return;
      await copyText(`${row.file}:${row.line}`, "定位");
    });
    els.query.addEventListener("input", applyFilters);
    els.fileFilter.addEventListener("change", applyFilters);
    els.reload.addEventListener("click", loadRows);
    window.addEventListener("keydown", (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "f") {
        event.preventDefault();
        els.query.focus();
        els.query.select();
      }
    });
    loadRows().catch((error) => {
      els.stats.innerHTML = `<span class="status-warn">加载失败：${escapeHtml(error.message)}</span>`;
    });
  </script>
</body>
</html>
"""


def should_skip(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)


def pick_column(headers: list[str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in headers:
            return candidate
    return None


def first_non_empty(*values: str | None) -> str:
    for value in values:
        if value:
            stripped = value.strip()
            if stripped:
                return stripped
    return ""


def corpus_title(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("##"):
            return stripped
    return ""


def read_csv_rows(path: Path, root: Path, start_id: int) -> tuple[list[dict], int]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        headers: list[str] | None = None
        previous_line = 0
        csv_row = 0
        for raw in reader:
            end_line = reader.line_num
            start_line = previous_line + 1
            previous_line = end_line
            if not raw:
                continue
            if raw[0].startswith("#"):
                continue
            if headers is None:
                headers = [cell.strip() for cell in raw]
                continue

            csv_row += 1
            values = raw + [""] * max(0, len(headers) - len(raw))
            record = dict(zip(headers, values))
            key_col = pick_column(headers, PRIMARY_COLUMNS) or headers[0]
            corpus_col = pick_column(headers, TEXT_COLUMNS)
            corpus = record.get(corpus_col, "") if corpus_col else ""
            extra_text = "\n".join(
                record.get(col, "")
                for col in TEXT_COLUMNS
                if col in record and col != corpus_col
            ).strip()
            full_text = "\n".join(cell for cell in raw if cell.strip())
            key = record.get(key_col, "").strip()
            title = corpus_title(corpus) or corpus_title(full_text)
            rel_path = path.relative_to(root).as_posix()
            row_id = f"row-{start_id}"
            start_id += 1
            rows.append(
                {
                    "id": row_id,
                    "file": rel_path,
                    "line": start_line,
                    "csv_row": csv_row,
                    "key": key,
                    "key_column": key_col,
                    "title": title,
                    "corpus": corpus,
                    "corpus_preview": corpus.replace("\n", " ")[:180],
                    "extra_text": extra_text,
                    "full_text": full_text,
                    "raw_joined": ",".join(raw),
                    "columns": headers,
                }
            )
    return rows, start_id


def scan_rows(root: Path) -> list[dict]:
    rows: list[dict] = []
    row_id = 1
    for path in sorted(root.rglob("*.csv")):
        if should_skip(path.relative_to(root)):
            continue
        try:
            file_rows, row_id = read_csv_rows(path, root, row_id)
        except (csv.Error, UnicodeDecodeError, OSError):
            continue
        rows.extend(file_rows)
    return rows


def json_response(handler: BaseHTTPRequestHandler, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def html_response(handler: BaseHTTPRequestHandler) -> None:
    body = HTML.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class CorpusViewerHandler(BaseHTTPRequestHandler):
    root: Path = ROOT

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            html_response(self)
            return
        if parsed.path == "/api/rows":
            query = parse_qs(parsed.query)
            root = Path(query.get("root", [str(self.root)])[0]).resolve()
            rows = scan_rows(root)
            files = sorted({row["file"] for row in rows})
            json_response(
                self,
                {
                    "rows": rows,
                    "files": files,
                    "updated_at": "刷新即重扫",
                    "root": str(root),
                },
            )
            return
        self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        return


def find_port(host: str, preferred: int) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free port found from {preferred} to {preferred + 19}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Start local CSV corpus viewer.")
    parser.add_argument("--root", default=str(ROOT), help="repo root to scan")
    parser.add_argument("--host", default="127.0.0.1", help="server host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="server port")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    port = find_port(args.host, args.port)
    CorpusViewerHandler.root = root
    server = ThreadingHTTPServer((args.host, port), CorpusViewerHandler)
    url = f"http://{args.host}:{port}/"
    print(f"Corpus viewer: {url}", flush=True)
    print(f"Scanning root: {root}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
