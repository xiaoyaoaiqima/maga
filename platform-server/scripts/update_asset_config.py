"""Update JSON config fields on asset_registry assets.

Examples:
    python scripts/update_asset_config.py \
      --asset-key a2_plot_discussion_comment \
      --field batch_variation_review \
      --file prompts/a2_plot_discussion_batch_variation_review.json

    python scripts/update_asset_config.py \
      --asset-key a2_plot_discussion_comment \
      --field batch_variation_review \
      --file prompts/a2_plot_discussion_batch_variation_review.json \
      --apply
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import pymysql


DEFAULT_BACKUP_DIR = ".local/asset-config-backups"


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


@dataclass(frozen=True)
class AssetRow:
    id: int
    asset_type: str
    asset_key: str
    display_name: str | None
    version_no: int
    status: str
    asset_stage: str
    source_name: str | None
    source_uri: str | None
    source_hash: str | None
    content_json: dict[str, Any]
    metadata_json: dict[str, Any]
    created_by: str | None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update asset_registry JSON config fields safely.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"), help="MySQL URL; overrides MYSQL_* envs")
    parser.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    parser.add_argument("--user", default=os.getenv("MYSQL_USER", "maga"))
    parser.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", "maga123456"))
    parser.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "maga"))
    parser.add_argument("--asset-key", required=True)
    parser.add_argument("--asset-type", default=None, help="Optional; required only when asset_key is ambiguous")
    parser.add_argument("--asset-stage", default="production")
    parser.add_argument("--field", required=True, help="Dotted JSON field path, e.g. batch_variation_review")
    parser.add_argument("--file", default=None, help="JSON file containing the new field value")
    parser.add_argument("--value-json", default=None, help="Inline JSON string containing the new field value")
    parser.add_argument("--target", choices=("content", "metadata", "both"), default="both")
    parser.add_argument("--mode", choices=("new-version", "in-place"), default="new-version")
    parser.add_argument("--apply", action="store_true", help="Actually write changes; omitted means dry-run")
    parser.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--created-by", default="asset-config-tool")
    parser.add_argument("--show-current", action="store_true", help="Print current field value and exit")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        run(args)
    except Exception as exc:  # noqa: BLE001 - CLI should return clear failures
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def run(args: argparse.Namespace) -> None:
    db_config = _db_config_from_args(args)
    field_path = _parse_field_path(args.field)
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
                _print_current(row, field_path, target=args.target)
                return
            new_value = _load_new_value(args)
            updated_content = copy.deepcopy(row.content_json)
            updated_metadata = copy.deepcopy(row.metadata_json)
            if args.target in {"content", "both"}:
                _set_dotted_value(updated_content, field_path, new_value)
            if args.target in {"metadata", "both"}:
                _set_dotted_value(updated_metadata, field_path, new_value)
            next_version = _next_asset_version(cursor, row) if args.mode == "new-version" else row.version_no

            summary = _build_summary(
                row,
                field_path=field_path,
                target=args.target,
                mode=args.mode,
                next_version=next_version,
                content_json=updated_content,
                metadata_json=updated_metadata,
            )
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            if not args.apply:
                print("DRY-RUN: add --apply to write this change.")
                return

            backup_path = _write_backup(row, Path(args.backup_dir))
            if args.mode == "new-version":
                new_id = _insert_new_version(
                    cursor,
                    row,
                    next_version=next_version,
                    content_json=updated_content,
                    metadata_json=updated_metadata,
                    created_by=args.created_by,
                )
                conn.commit()
                print(f"APPLIED: archived asset id={row.id}, created new active asset id={new_id}.")
            else:
                _update_in_place(cursor, row.id, content_json=updated_content, metadata_json=updated_metadata)
                conn.commit()
                print(f"APPLIED: updated active asset id={row.id} in place.")
            print(f"BACKUP: {backup_path}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _connect(config: DbConfig) -> pymysql.Connection:
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        charset="utf8mb4",
        connect_timeout=5,
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _db_config_from_args(args: argparse.Namespace) -> DbConfig:
    if args.database_url:
        parsed = _parse_mysql_url(args.database_url)
        if parsed:
            return parsed
    return DbConfig(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
    )


def _parse_mysql_url(value: str) -> DbConfig | None:
    raw = value.strip()
    if not raw:
        return None
    if raw.startswith("mysql+"):
        raw = "mysql://" + raw.split("://", 1)[1]
    parsed = urlparse(raw)
    if parsed.scheme not in {"mysql", "mariadb"}:
        raise ValueError(f"unsupported database url scheme: {parsed.scheme}")
    return DbConfig(
        host=parsed.hostname or "127.0.0.1",
        port=int(parsed.port or 3306),
        user=unquote(parsed.username or "maga"),
        password=unquote(parsed.password or ""),
        database=(parsed.path or "/maga").lstrip("/") or "maga",
    )


def _load_active_asset(
    cursor: Any,
    *,
    asset_key: str,
    asset_type: str | None,
    asset_stage: str,
) -> AssetRow:
    filters = ["asset_key=%s", "asset_stage=%s", "status='active'"]
    params: list[Any] = [asset_key, asset_stage]
    if asset_type:
        filters.append("asset_type=%s")
        params.append(asset_type)
    cursor.execute(
        f"""
        SELECT id, asset_type, asset_key, display_name, version_no, status, asset_stage,
               source_name, source_uri, source_hash, content_json, metadata_json, created_by
        FROM asset_registry
        WHERE {" AND ".join(filters)}
        ORDER BY version_no DESC, id DESC
        """,
        params,
    )
    rows = cursor.fetchall()
    if not rows:
        raise ValueError(f"active asset not found: asset_key={asset_key}, asset_type={asset_type or '*'}")
    asset_types = {row["asset_type"] for row in rows}
    if not asset_type and len(asset_types) > 1:
        raise ValueError(f"asset_key is ambiguous; pass --asset-type. candidates={sorted(asset_types)}")
    row = rows[0]
    return AssetRow(
        id=int(row["id"]),
        asset_type=row["asset_type"],
        asset_key=row["asset_key"],
        display_name=row.get("display_name"),
        version_no=int(row["version_no"]),
        status=row["status"],
        asset_stage=row["asset_stage"],
        source_name=row.get("source_name"),
        source_uri=row.get("source_uri"),
        source_hash=row.get("source_hash"),
        content_json=_json_obj(row.get("content_json")),
        metadata_json=_json_obj(row.get("metadata_json")),
        created_by=row.get("created_by"),
    )


def _insert_new_version(
    cursor: Any,
    row: AssetRow,
    *,
    next_version: int,
    content_json: dict[str, Any],
    metadata_json: dict[str, Any],
    created_by: str,
) -> int:
    cursor.execute(
        """
        UPDATE asset_registry
        SET status='archived'
        WHERE asset_type=%s AND asset_key=%s AND asset_stage=%s AND status='active'
        """,
        (row.asset_type, row.asset_key, row.asset_stage),
    )
    cursor.execute(
        """
        INSERT INTO asset_registry (
            asset_type, asset_key, display_name, version_no, status, asset_stage,
            source_name, source_uri, source_hash, content_json, metadata_json, created_by
        )
        VALUES (%s, %s, %s, %s, 'active', %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            row.asset_type,
            row.asset_key,
            row.display_name,
            next_version,
            row.asset_stage,
            "asset_config_tool",
            f"asset_registry://{row.id}",
            row.source_hash,
            json.dumps(content_json, ensure_ascii=False),
            json.dumps(metadata_json, ensure_ascii=False),
            created_by,
        ),
    )
    return int(cursor.lastrowid)


def _next_asset_version(cursor: Any, row: AssetRow) -> int:
    cursor.execute(
        "SELECT COALESCE(MAX(version_no), 0) AS max_version FROM asset_registry WHERE asset_type=%s AND asset_key=%s",
        (row.asset_type, row.asset_key),
    )
    result = cursor.fetchone() or {}
    return int(result.get("max_version") or 0) + 1


def _update_in_place(
    cursor: Any,
    asset_id: int,
    *,
    content_json: dict[str, Any],
    metadata_json: dict[str, Any],
) -> None:
    cursor.execute(
        "UPDATE asset_registry SET content_json=%s, metadata_json=%s WHERE id=%s",
        (json.dumps(content_json, ensure_ascii=False), json.dumps(metadata_json, ensure_ascii=False), asset_id),
    )


def _write_backup(row: AssetRow, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = backup_dir / f"asset-{row.asset_key}-v{row.version_no}-{row.id}-{stamp}.json"
    payload = {
        "id": row.id,
        "asset_type": row.asset_type,
        "asset_key": row.asset_key,
        "version_no": row.version_no,
        "status": row.status,
        "asset_stage": row.asset_stage,
        "content_json": row.content_json,
        "metadata_json": row.metadata_json,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _load_new_value(args: argparse.Namespace) -> Any:
    if bool(args.file) == bool(args.value_json):
        raise ValueError("pass exactly one of --file or --value-json")
    if args.file:
        return json.loads(Path(args.file).read_text(encoding="utf-8"))
    return json.loads(args.value_json)


def _build_summary(
    row: AssetRow,
    *,
    field_path: list[str],
    target: str,
    mode: str,
    next_version: int,
    content_json: dict[str, Any],
    metadata_json: dict[str, Any],
) -> dict[str, Any]:
    return {
        "asset": {
            "id": row.id,
            "asset_type": row.asset_type,
            "asset_key": row.asset_key,
            "version_no": row.version_no,
        },
        "mode": mode,
        "target": target,
        "field": ".".join(field_path),
        "next_version": next_version,
        "content_value": _get_dotted_value(content_json, field_path) if target in {"content", "both"} else None,
        "metadata_value": _get_dotted_value(metadata_json, field_path) if target in {"metadata", "both"} else None,
    }


def _print_current(row: AssetRow, field_path: list[str], *, target: str) -> None:
    payload = {
        "asset": {
            "id": row.id,
            "asset_type": row.asset_type,
            "asset_key": row.asset_key,
            "version_no": row.version_no,
        },
        "field": ".".join(field_path),
    }
    if target in {"content", "both"}:
        payload["content_value"] = _get_dotted_value(row.content_json, field_path)
    if target in {"metadata", "both"}:
        payload["metadata_value"] = _get_dotted_value(row.metadata_json, field_path)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _parse_field_path(value: str) -> list[str]:
    parts = [part.strip() for part in value.split(".") if part.strip()]
    if not parts:
        raise ValueError("--field cannot be empty")
    return parts


def _set_dotted_value(target: dict[str, Any], path: list[str], value: Any) -> None:
    current: dict[str, Any] = target
    for part in path[:-1]:
        existing = current.get(part)
        if not isinstance(existing, dict):
            existing = {}
            current[part] = existing
        current = existing
    current[path[-1]] = value


def _get_dotted_value(source: dict[str, Any], path: list[str]) -> Any:
    current: Any = source
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _json_obj(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("asset JSON column must be a JSON object")


if __name__ == "__main__":
    main()
