"""Update one comment-angle rule item inside an asset_registry rule-set asset.

Examples:
    PYTHONPATH=. ../.venv/bin/python scripts/update_comment_angle_rule_item.py \
      --asset-key a2_sentiment_comment_activity \
      --rule-id comment_angle_015 \
      --corpus-file /tmp/comment_angle_015.txt

    PYTHONPATH=. ../.venv/bin/python scripts/update_comment_angle_rule_item.py \
      --asset-key a2_sentiment_comment_activity \
      --source-row-no 15 \
      --corpus-file /tmp/comment_angle_015.txt \
      --apply
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.update_asset_config import (  # type: ignore
        DEFAULT_BACKUP_DIR,
        _connect,
        _db_config_from_args,
        _insert_new_version,
        _load_active_asset,
        _update_in_place,
        _write_backup,
    )
except ModuleNotFoundError:
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from scripts.update_asset_config import (  # type: ignore
        DEFAULT_BACKUP_DIR,
        _connect,
        _db_config_from_args,
        _insert_new_version,
        _load_active_asset,
        _update_in_place,
        _write_backup,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update one comment-angle corpus item safely.")
    parser.add_argument("--database-url", default=None, help="MySQL URL; overrides MYSQL_* envs")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--database", default=None)
    parser.add_argument("--asset-key", required=True)
    parser.add_argument("--asset-type", default="comment_angle_rule_set")
    parser.add_argument("--asset-stage", default="production")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--rule-id", default=None)
    selector.add_argument("--source-row-no", type=int, default=None)
    selector.add_argument("--comment-angle", default=None)
    corpus = parser.add_mutually_exclusive_group()
    corpus.add_argument("--corpus-file", default=None, help="Plain text file containing the new corpus block")
    corpus.add_argument("--corpus-text", default=None, help="Inline corpus text")
    parser.add_argument(
        "--sync-examples-from-corpus",
        action="store_true",
        help="Extract '- ...' lines under '示例：' from the corpus block and write item.examples too.",
    )
    parser.add_argument("--show-current", action="store_true", help="Print the matched current item and exit")
    parser.add_argument("--mode", choices=("new-version", "in-place"), default="new-version")
    parser.add_argument("--apply", action="store_true", help="Actually write changes; omitted means dry-run")
    parser.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--created-by", default="comment-angle-rule-item-tool")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _apply_env_defaults(build_parser().parse_args(argv))
    try:
        run(args)
    except Exception as exc:  # noqa: BLE001 - CLI should return clear failures
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def run(args: argparse.Namespace) -> None:
    db_config = _db_config_from_args(args)
    conn = _connect(db_config)
    try:
        with conn.cursor() as cursor:
            row = _load_active_asset(
                cursor,
                asset_key=args.asset_key,
                asset_type=args.asset_type,
                asset_stage=args.asset_stage,
            )
            if args.show_current:
                _, summary = _content_with_updated_corpus(row.content_json, args, new_corpus=None)
                print(json.dumps({"asset": _asset_summary(row), "matched_item": summary}, ensure_ascii=False, indent=2))
                return

            new_corpus = _load_new_corpus(args)
            updated_content, item_summary = _content_with_updated_corpus(row.content_json, args, new_corpus=new_corpus)
            summary = {
                "asset": _asset_summary(row),
                "mode": args.mode,
                "next_version": row.version_no + 1 if args.mode == "new-version" else row.version_no,
                "matched_item": item_summary,
                "metadata_unchanged": True,
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            if not args.apply:
                print("DRY-RUN: add --apply to write this change.")
                return

            backup_path = _write_backup(row, Path(args.backup_dir))
            if args.mode == "new-version":
                new_id = _insert_new_version(
                    cursor,
                    row,
                    content_json=updated_content,
                    metadata_json=copy.deepcopy(row.metadata_json),
                    created_by=args.created_by,
                )
                conn.commit()
                print(f"APPLIED: archived asset id={row.id}, created new active asset id={new_id}.")
            else:
                _update_in_place(
                    cursor,
                    row.id,
                    content_json=updated_content,
                    metadata_json=copy.deepcopy(row.metadata_json),
                )
                conn.commit()
                print(f"APPLIED: updated active asset id={row.id} in place.")
            print(f"BACKUP: {backup_path}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _apply_env_defaults(args: argparse.Namespace) -> argparse.Namespace:
    import os

    args.database_url = args.database_url or os.getenv("DATABASE_URL")
    args.host = args.host or os.getenv("MYSQL_HOST", "127.0.0.1")
    args.port = args.port or int(os.getenv("MYSQL_PORT", "3306"))
    args.user = args.user or os.getenv("MYSQL_USER", "maga")
    args.password = args.password or os.getenv("MYSQL_PASSWORD", "maga123456")
    args.database = args.database or os.getenv("MYSQL_DATABASE", "maga")
    return args


def _load_new_corpus(args: argparse.Namespace) -> str:
    if bool(args.corpus_file) == bool(args.corpus_text):
        raise ValueError("pass exactly one of --corpus-file or --corpus-text unless --show-current is used")
    if args.corpus_file:
        return Path(args.corpus_file).read_text(encoding="utf-8").rstrip("\n")
    return str(args.corpus_text).rstrip("\n")


def _content_with_updated_corpus(
    content_json: dict[str, Any],
    args: argparse.Namespace,
    *,
    new_corpus: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    updated = copy.deepcopy(content_json)
    items = updated.get("items")
    if not isinstance(items, list):
        raise ValueError("asset content_json.items must be a list")
    index, item = _find_item(items, args)
    old_corpus = str(item.get("corpus") or "")
    old_examples = list(item.get("examples") or []) if isinstance(item.get("examples"), list) else []
    if new_corpus is not None:
        item["corpus"] = new_corpus
        if getattr(args, "sync_examples_from_corpus", False):
            item["examples"] = _extract_examples_from_corpus(new_corpus)
    summary = {
        "index": index,
        "rule_id": item.get("rule_id"),
        "source_row_no": item.get("source_row_no"),
        "comment_angle": item.get("comment_angle"),
        "old_corpus": old_corpus,
        "new_corpus": item.get("corpus"),
        "old_example_count": len(old_examples),
        "new_example_count": len(item.get("examples") or []) if isinstance(item.get("examples"), list) else 0,
        "changed": new_corpus is not None and old_corpus != new_corpus,
    }
    return updated, summary


def _extract_examples_from_corpus(corpus: str) -> list[str]:
    """Extract operator examples from the standard comment-angle corpus block."""
    examples: list[str] = []
    in_examples = False
    for raw_line in corpus.splitlines():
        line = raw_line.strip()
        if line == "示例：":
            in_examples = True
            continue
        if in_examples and line.startswith("注意："):
            break
        if not in_examples:
            continue
        if line.startswith("- "):
            example = line[2:].strip()
            if example:
                examples.append(example)
    return examples


def _find_item(items: list[Any], args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    matches: list[tuple[int, dict[str, Any]]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if args.rule_id is not None and str(item.get("rule_id") or "") == str(args.rule_id):
            matches.append((index, item))
        elif args.source_row_no is not None and _int_or_none(item.get("source_row_no")) == args.source_row_no:
            matches.append((index, item))
        elif args.comment_angle is not None and str(item.get("comment_angle") or "") == str(args.comment_angle):
            matches.append((index, item))
    if not matches:
        raise ValueError("no matching comment-angle item found")
    if len(matches) > 1:
        candidates = [
            {
                "index": index,
                "rule_id": item.get("rule_id"),
                "source_row_no": item.get("source_row_no"),
                "comment_angle": item.get("comment_angle"),
            }
            for index, item in matches
        ]
        raise ValueError(f"selector matched multiple items; use --rule-id or --source-row-no. candidates={candidates}")
    return matches[0]


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _asset_summary(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "asset_type": row.asset_type,
        "asset_key": row.asset_key,
        "version_no": row.version_no,
        "asset_stage": row.asset_stage,
    }


if __name__ == "__main__":
    main()
