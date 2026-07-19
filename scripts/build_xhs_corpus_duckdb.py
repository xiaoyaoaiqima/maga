#!/usr/bin/env python3
"""Build a fast, derived DuckDB index from the canonical XHS JSONL corpus."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import duckdb
except ImportError as exc:
    raise SystemExit(
        "duckdb is required; run with: "
        "uv run --with 'duckdb>=1.4,<1.5' scripts/build_xhs_corpus_duckdb.py"
    ) from exc


DEFAULT_CORPUS_DIR = Path("/Users/luxifa/maga/local_data/xhs_corpus_pool")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a DuckDB query index without changing the source JSONL files."
    )
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--output", type=Path)
    return parser


def expected_counts(manifest_path: Path) -> dict[str, int]:
    if not manifest_path.exists():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    counts = manifest.get("output_counts")
    if not isinstance(counts, dict):
        return {}
    return {
        name: int(counts[name])
        for name in ("notes", "comments")
        if isinstance(counts.get(name), int)
    }


def validate_source(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise SystemExit(f"Missing source JSONL: {resolved}")
    return resolved


def main() -> None:
    args = build_parser().parse_args()
    corpus_dir = args.corpus_dir.expanduser().resolve()
    output = (args.output or corpus_dir / "corpus.duckdb").expanduser().resolve()
    notes_path = validate_source(corpus_dir / "notes.jsonl")
    comments_path = validate_source(corpus_dir / "comments.jsonl")
    expected = expected_counts(corpus_dir / "manifest.json")

    output.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output.with_suffix(output.suffix + ".tmp")
    temp_output.unlink(missing_ok=True)
    started_at = time.perf_counter()

    connection = duckdb.connect(str(temp_output))
    try:
        connection.execute(
            "CREATE TABLE notes AS SELECT * FROM read_json_auto(?, format = 'newline_delimited')",
            [str(notes_path)],
        )
        connection.execute(
            "CREATE TABLE comments AS SELECT * FROM read_json_auto(?, format = 'newline_delimited')",
            [str(comments_path)],
        )
        connection.execute("CREATE UNIQUE INDEX notes_key_idx ON notes (key)")
        connection.execute("CREATE INDEX notes_note_id_idx ON notes (note_id)")
        connection.execute("CREATE UNIQUE INDEX comments_key_idx ON comments (key)")
        connection.execute(
            "CREATE INDEX comments_comment_id_idx ON comments (comment_id)"
        )
        connection.execute("CREATE INDEX comments_note_id_idx ON comments (note_id)")
        connection.execute(
            """
            CREATE TABLE corpus_meta AS
            SELECT
                ?::TIMESTAMPTZ AS generated_at,
                ?::VARCHAR AS notes_path,
                ?::VARCHAR AS comments_path,
                (SELECT count(*) FROM notes)::BIGINT AS note_count,
                (SELECT count(*) FROM comments)::BIGINT AS comment_count
            """,
            [
                datetime.now(timezone.utc).isoformat(),
                str(notes_path),
                str(comments_path),
            ],
        )
        connection.execute("ANALYZE")

        counts = {
            "notes": connection.execute("SELECT count(*) FROM notes").fetchone()[0],
            "comments": connection.execute("SELECT count(*) FROM comments").fetchone()[
                0
            ],
        }
        unique_counts = {
            "notes": connection.execute(
                "SELECT count(DISTINCT key) FROM notes"
            ).fetchone()[0],
            "comments": connection.execute(
                "SELECT count(DISTINCT key) FROM comments"
            ).fetchone()[0],
        }
        for name, count in counts.items():
            if unique_counts[name] != count:
                raise RuntimeError(f"Duplicate {name} keys found in DuckDB index")
            if name in expected and expected[name] != count:
                raise RuntimeError(
                    f"{name} count mismatch: manifest={expected[name]}, duckdb={count}"
                )
        connection.execute("CHECKPOINT")
    except Exception:
        connection.close()
        temp_output.unlink(missing_ok=True)
        raise
    else:
        connection.close()

    os.replace(temp_output, output)
    result = {
        "output": str(output),
        "size_bytes": output.stat().st_size,
        "notes": counts["notes"],
        "comments": counts["comments"],
        "build_seconds": round(time.perf_counter() - started_at, 3),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
