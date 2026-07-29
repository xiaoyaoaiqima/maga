#!/usr/bin/env python3
"""Publish Wangyue expression routes scoped by article post type."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pymysql


ASSET_TYPE = "article_business_rule_set"
ASSET_KEY = "wangyue_v3_core_storyline_article_rules"
EXPRESSION_POST_TYPE_ROUTES = {
    97: ["问题解决", "对比选择"],
    99: ["对比选择"],
    100: ["对比选择"],
    107: ["问题解决", "家庭清单", "对比选择", "复购/长期使用"],
    110: ["问题解决", "家庭清单", "对比选择", "复购/长期使用"],
    112: ["问题解决", "家庭清单", "对比选择", "复购/长期使用"],
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="发布旺玥卖点表达内容方向路由。")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    parser.add_argument("--user", default=os.getenv("MYSQL_USER", "maga"))
    parser.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", "maga123456"))
    parser.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "maga"))
    parser.add_argument("--backup-dir", type=Path, default=Path(".local/asset-config-backups"))
    return parser


def _json_value(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def build_next_content(source_content: dict[str, Any]) -> dict[str, Any]:
    content = copy.deepcopy(source_content)
    expressions = content.get("selling_painpoint_expressions") or []
    expressions_by_row = {
        int(item.get("source_row_no")): item
        for item in expressions
        if isinstance(item, dict) and item.get("source_row_no") is not None
    }
    missing_rows = sorted(set(EXPRESSION_POST_TYPE_ROUTES) - set(expressions_by_row))
    if missing_rows:
        raise RuntimeError(f"missing expression rows: {missing_rows}")

    for source_row_no, post_types in EXPRESSION_POST_TYPE_ROUTES.items():
        expression = expressions_by_row[source_row_no]
        if expression.get("selling_painpoint_group") != "营养丰富+营养不足-ugc":
            raise RuntimeError(f"unexpected group for expression row {source_row_no}")
        expression["applicable_post_types"] = list(post_types)
    return content


def main() -> None:
    args = build_parser().parse_args()
    conn = pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select id, display_name, version_no, source_name, source_uri,
                       content_json, metadata_json
                from asset_registry
                where asset_type=%s and asset_key=%s
                  and asset_stage='production' and status='active'
                order by version_no desc, id desc
                limit 1
                """,
                (ASSET_TYPE, ASSET_KEY),
            )
            current = cursor.fetchone()
            if not current:
                raise RuntimeError(f"active asset not found: {ASSET_KEY}")
            cursor.execute(
                """
                select coalesce(max(version_no), 0) as max_version
                from asset_registry
                where asset_type=%s and asset_key=%s
                """,
                (ASSET_TYPE, ASSET_KEY),
            )
            next_version = int((cursor.fetchone() or {}).get("max_version") or 0) + 1

        source_content = _json_value(current.get("content_json")) or {}
        content = build_next_content(source_content)
        metadata = copy.deepcopy(_json_value(current.get("metadata_json")) or {})
        metadata.update(
            {
                "expression_post_type_routing_base_asset_id": int(current["id"]),
                "expression_post_type_routing_base_version_no": int(current["version_no"]),
                "expression_post_type_routing_published_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        for field in ("items", "hard_boundaries", "variation_slots"):
            if source_content.get(field) != content.get(field):
                raise RuntimeError(f"{field} changed unexpectedly")

        result = {
            "source_asset_id": int(current["id"]),
            "source_version_no": int(current["version_no"]),
            "target_version_no": next_version,
            "routed_expression_rows": EXPRESSION_POST_TYPE_ROUTES,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not args.apply:
            conn.rollback()
            print("DRY-RUN: add --apply to create the new active production version.")
            return

        args.backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = args.backup_dir / (
            f"{ASSET_KEY}-v{current['version_no']}-"
            f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        )
        backup_path.write_text(
            json.dumps(current, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        source_hash = hashlib.sha256(
            json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

        with conn.cursor() as cursor:
            cursor.execute(
                """
                update asset_registry
                set status='archived'
                where asset_type=%s and asset_key=%s
                  and asset_stage='production' and status='active'
                """,
                (ASSET_TYPE, ASSET_KEY),
            )
            cursor.execute(
                """
                insert into asset_registry (
                    asset_type, asset_key, display_name, version_no, status, asset_stage,
                    source_name, source_uri, source_hash, content_json, metadata_json, created_by
                ) values (%s,%s,%s,%s,'active','production',%s,%s,%s,cast(%s as json),cast(%s as json),%s)
                """,
                (
                    ASSET_TYPE,
                    ASSET_KEY,
                    f"0705旺玥活动-V3-卖点表达方向路由-v{next_version}",
                    next_version,
                    current.get("source_name"),
                    current.get("source_uri"),
                    source_hash,
                    json.dumps(content, ensure_ascii=False),
                    json.dumps(metadata, ensure_ascii=False),
                    "codex_wangyue_expression_post_type_routing_20260727",
                ),
            )
            new_asset_id = int(cursor.lastrowid)
        conn.commit()
        print(f"APPLIED: created asset id={new_asset_id}, version={next_version}")
        print(f"BACKUP: {backup_path.resolve()}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
