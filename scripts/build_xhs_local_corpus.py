#!/usr/bin/env python3
"""Build one lightweight local XHS corpus from the active pool and raw exports."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_ASSET_URL = (
    "http://127.0.0.1:5100/api/v1/assets/"
    "real_user_example_pool/maternal_infant_xhs_real_user_pool"
)
DEFAULT_OUTPUT_DIR = Path("/Users/luxifa/maga/local_data/xhs_corpus_pool")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a deduped local XHS note/comment corpus.")
    parser.add_argument("--asset-url", default=DEFAULT_ASSET_URL)
    parser.add_argument("--skip-asset", action="store_true")
    parser.add_argument("--source-dir", action="append", default=[], type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def clean(value: Any) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return "" if text.lower() in {"none", "null", "nan"} else text


def split_keywords(value: Any) -> list[str]:
    text = clean(value)
    if not text:
        return []
    return sorted({part.strip() for part in re.split(r"[;,，；\n]+", text) if part.strip()})


def text_hash(*parts: str) -> str:
    normalized = "\n".join(clean(part).lower() for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def note_key(note_id: str, title: str, text: str) -> str:
    return f"note:{note_id}" if note_id else f"note_hash:{text_hash(title, text)}"


def comment_key(comment_id: str, note_id: str, text: str) -> str:
    return f"comment:{comment_id}" if comment_id else f"comment_hash:{text_hash(note_id, text)}"


def source_ref(source_type: str, reference: str) -> dict[str, str]:
    return {"source_type": source_type, "reference": reference}


def normalize_note(
    row: dict[str, Any], *, source_type: str, reference: str
) -> dict[str, Any] | None:
    note_id = clean(row.get("note_id"))
    title = clean(row.get("title") or row.get("note_title"))
    text = clean(row.get("text") or row.get("content") or row.get("note_desc"))
    if not note_id and not title and not text:
        return None
    return {
        "key": note_key(note_id, title, text),
        "record_type": "note",
        "note_id": note_id,
        "title": title,
        "text": text,
        "url": clean(row.get("url") or row.get("note_url")),
        "keywords": split_keywords(
            row.get("source_keyword") or row.get("search_keywords") or row.get("keyword")
        ),
        "sources": [source_ref(source_type, reference)],
        "tags": sorted({clean(item) for item in (row.get("tags") or []) if clean(item)})
        if isinstance(row.get("tags"), list)
        else [],
        "risk_tags": sorted({clean(item) for item in (row.get("risk_tags") or []) if clean(item)})
        if isinstance(row.get("risk_tags"), list)
        else [],
        "extra": row.get("extra") if isinstance(row.get("extra"), dict) else {},
    }


def normalize_comment(
    row: dict[str, Any], *, source_type: str, reference: str
) -> dict[str, Any] | None:
    comment_id = clean(row.get("comment_id"))
    note_id = clean(row.get("note_id"))
    text = clean(row.get("text") or row.get("content") or row.get("comment_text"))
    if not comment_id and not text:
        return None
    return {
        "key": comment_key(comment_id, note_id, text),
        "record_type": "comment",
        "comment_id": comment_id,
        "parent_comment_id": clean(row.get("parent_comment_id")),
        "note_id": note_id,
        "note_title": clean(row.get("title") or row.get("note_title")),
        "text": text,
        "url": clean(row.get("url") or row.get("note_url")),
        "keywords": split_keywords(
            row.get("source_keyword")
            or row.get("note_source_keyword")
            or row.get("search_keywords")
            or row.get("keyword")
        ),
        "sources": [source_ref(source_type, reference)],
        "tags": sorted({clean(item) for item in (row.get("tags") or []) if clean(item)})
        if isinstance(row.get("tags"), list)
        else [],
        "risk_tags": sorted({clean(item) for item in (row.get("risk_tags") or []) if clean(item)})
        if isinstance(row.get("risk_tags"), list)
        else [],
        "extra": row.get("extra") if isinstance(row.get("extra"), dict) else {},
    }


def fetch_asset(url: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = json.load(response)
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise RuntimeError(f"Asset response missing data: {url}")
    content = data.get("content_json") if isinstance(data.get("content_json"), dict) else {}
    items = content.get("items") if isinstance(content.get("items"), list) else []
    meta = {
        "asset_key": clean(data.get("asset_key")),
        "asset_id": data.get("id"),
        "version_no": data.get("version_no"),
        "item_count": len(items),
    }
    return [item for item in items if isinstance(item, dict)], meta


def read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def iter_export_rows(source_dirs: Iterable[Path]) -> Iterable[tuple[str, dict[str, Any], str]]:
    for source_dir in source_dirs:
        resolved = source_dir.expanduser().resolve()
        note_path = resolved / "xhs_notes_full.csv"
        comment_path = resolved / "xhs_comments_full.csv"
        raw_records_path = resolved / "raw_records.jsonl"
        if note_path.exists():
            for row in read_csv(note_path):
                yield "note", row, str(note_path)
        if raw_records_path.exists():
            with raw_records_path.open("r", encoding="utf-8") as file:
                for line in file:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    if isinstance(row, dict):
                        yield "note", row, str(raw_records_path)
        if comment_path.exists():
            for row in read_csv(comment_path):
                yield "comment", row, str(comment_path)


def richer_text(current: str, incoming: str) -> str:
    return incoming if len(incoming) > len(current) else current


def merge_item(current: dict[str, Any], incoming: dict[str, Any]) -> None:
    for field in ("title", "text", "note_title"):
        if field in current or field in incoming:
            current[field] = richer_text(clean(current.get(field)), clean(incoming.get(field)))
    for field in ("url", "note_id", "comment_id", "parent_comment_id"):
        if not clean(current.get(field)) and clean(incoming.get(field)):
            current[field] = clean(incoming.get(field))
    for field in ("keywords", "tags", "risk_tags"):
        current[field] = sorted({*(current.get(field) or []), *(incoming.get(field) or [])})
    seen_sources = {
        (clean(item.get("source_type")), clean(item.get("reference")))
        for item in current.get("sources", [])
        if isinstance(item, dict)
    }
    for item in incoming.get("sources", []):
        if not isinstance(item, dict):
            continue
        key = (clean(item.get("source_type")), clean(item.get("reference")))
        if key not in seen_sources:
            current.setdefault("sources", []).append(item)
            seen_sources.add(key)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(path)


def write_readme(path: Path, manifest: dict[str, Any]) -> None:
    counts = manifest["output_counts"]
    text = f"""# 本地小红书语料池

这是 MAGA 当前唯一的本地小红书语料池入口，只做类型分开、来源保留和去重。

- 帖子：`notes.jsonl`，{counts['notes']} 条
- 评论：`comments.jsonl`，{counts['comments']} 条
- 帖子去重键：优先 `note_id`，缺失时使用标题和正文哈希
- 评论去重键：优先 `comment_id`，缺失时使用 `note_id + 评论正文` 哈希
- 原始新增批次：保存在 `imports/`，不要直接修改主池 JSONL
- 构建报告：`manifest.json`
- 快速查询索引：`corpus.duckdb`，由 JSONL 派生，可随时重建

重新构建时运行 `scripts/build_xhs_local_corpus.py`，并通过 `--source-dir` 传入新增导出目录。
JSONL 更新后，运行 `uv run --with 'duckdb>=1.4,<1.5' scripts/build_xhs_corpus_duckdb.py` 刷新查询索引。
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    args = build_parser().parse_args()
    notes: dict[str, dict[str, Any]] = {}
    comments: dict[str, dict[str, Any]] = {}
    input_counts = {"asset_notes": 0, "asset_comments": 0, "export_notes": 0, "export_comments": 0}
    duplicate_counts = {"notes": 0, "comments": 0}
    asset_meta: dict[str, Any] = {}

    if not args.skip_asset:
        asset_items, asset_meta = fetch_asset(args.asset_url)
        reference = f"{asset_meta.get('asset_key')}@v{asset_meta.get('version_no')}"
        for row in asset_items:
            record_type = clean(row.get("source_type"))
            normalized = (
                normalize_note(row, source_type="maga_asset", reference=reference)
                if record_type == "note"
                else normalize_comment(row, source_type="maga_asset", reference=reference)
            )
            if normalized is None:
                continue
            target = notes if normalized["record_type"] == "note" else comments
            count_key = "asset_notes" if normalized["record_type"] == "note" else "asset_comments"
            duplicate_key = "notes" if normalized["record_type"] == "note" else "comments"
            input_counts[count_key] += 1
            if normalized["key"] in target:
                duplicate_counts[duplicate_key] += 1
                merge_item(target[normalized["key"]], normalized)
            else:
                target[normalized["key"]] = normalized

    for record_type, row, reference in iter_export_rows(args.source_dir):
        normalized = (
            normalize_note(row, source_type="raw_export", reference=reference)
            if record_type == "note"
            else normalize_comment(row, source_type="raw_export", reference=reference)
        )
        if normalized is None:
            continue
        target = notes if record_type == "note" else comments
        input_counts[f"export_{record_type}s"] += 1
        if normalized["key"] in target:
            duplicate_counts[f"{record_type}s"] += 1
            merge_item(target[normalized["key"]], normalized)
        else:
            target[normalized["key"]] = normalized

    args.output_dir.mkdir(parents=True, exist_ok=True)
    note_rows = sorted(notes.values(), key=lambda row: row["key"])
    comment_rows = sorted(comments.values(), key=lambda row: row["key"])
    write_jsonl(args.output_dir / "notes.jsonl", note_rows)
    write_jsonl(args.output_dir / "comments.jsonl", comment_rows)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "asset": asset_meta,
        "source_dirs": [str(path.expanduser().resolve()) for path in args.source_dir],
        "dedupe_keys": {
            "note": "note_id; fallback sha256(title + text)",
            "comment": "comment_id; fallback sha256(note_id + text)",
        },
        "input_counts": input_counts,
        "duplicate_counts": duplicate_counts,
        "output_counts": {"notes": len(note_rows), "comments": len(comment_rows)},
        "unique_note_contexts": len(
            {clean(row.get("note_id")) for row in [*note_rows, *comment_rows] if clean(row.get("note_id"))}
        ),
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_readme(args.output_dir / "README.md", manifest)

    if len({row["key"] for row in note_rows}) != len(note_rows):
        raise RuntimeError("Duplicate note keys remain after build")
    if len({row["key"] for row in comment_rows}) != len(comment_rows):
        raise RuntimeError("Duplicate comment keys remain after build")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
