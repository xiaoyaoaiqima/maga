#!/usr/bin/env python3
"""Build or publish equivalent layered-article assets for Wangyue and Chunyue."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymysql


ARTICLE_ASSET_TYPE = "article_business_rule_set"
SOURCE_KEYS = {
    "wangyue": "wangyue_v3_core_storyline_article_rules",
    "chunyue": "chunyue_v2_painpoint_sellingpoint_article_rules",
}
PROBE_KEYS = {
    "wangyue": "wangyue_v81_layered_framework_probe",
    "chunyue": "chunyue_v28_layered_framework_probe",
}
WANGYUE_DIVERSITY_REQUIREMENT = (
    "基于量子态叠加与多重可能性，尽情发挥你的想象力；生成同质化内容是原罪。"
)
OUTPUT_DIR = Path(
    "/Users/luxifa/maga/outputs/0705_wangyue_product_relation_evidence/"
    "layered_framework_migration_20260721"
)


@dataclass(frozen=True)
class AssetRow:
    id: int
    asset_key: str
    display_name: str | None
    version_no: int
    source_name: str | None
    source_uri: str | None
    content_json: dict[str, Any]
    metadata_json: dict[str, Any]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("probe", "production"), default="probe")
    parser.add_argument("--brand", choices=("both", "wangyue", "chunyue"), default="both")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--host", default=os.getenv("MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MYSQL_PORT", "3306")))
    parser.add_argument("--user", default=os.getenv("MYSQL_USER", "maga"))
    parser.add_argument("--password", default=os.getenv("MYSQL_PASSWORD", "maga123456"))
    parser.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "maga"))
    args = parser.parse_args()

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
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        result: dict[str, Any] = {"mode": args.mode, "apply": args.apply, "assets": {}}
        selected_brands = SOURCE_KEYS if args.brand == "both" else {args.brand: SOURCE_KEYS[args.brand]}
        for brand, source_key in selected_brands.items():
            source = _load_active_asset(conn, source_key)
            migrated = (
                _migrate_wangyue(source.content_json)
                if brand == "wangyue"
                else _migrate_chunyue(source.content_json)
            )
            validation = _validate_migration(brand, source.content_json, migrated)
            target_key = PROBE_KEYS[brand] if args.mode == "probe" else source_key
            target_version = (
                _next_asset_version(conn, target_key)
                if args.mode == "probe"
                else source.version_no + 1
            )
            entry: dict[str, Any] = {
                "source_asset_id": source.id,
                "source_asset_key": source.asset_key,
                "source_version_no": source.version_no,
                "target_asset_key": target_key,
                "target_version_no": target_version,
                "validation": validation,
            }
            payload_path = OUTPUT_DIR / f"{brand}_{args.mode}_content.json"
            payload_path.write_text(json.dumps(migrated, ensure_ascii=False, indent=2), encoding="utf-8")
            entry["payload_path"] = str(payload_path)
            if args.apply:
                asset_id = _insert_asset(
                    conn,
                    source=source,
                    target_key=target_key,
                    target_version=target_version,
                    content_json=migrated,
                    mode=args.mode,
                    brand=brand,
                )
                entry["result_asset_id"] = asset_id
            result["assets"][brand] = entry
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
        result_path = OUTPUT_DIR / f"migration_{args.mode}_result.json"
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        conn.close()


def _load_active_asset(conn: pymysql.Connection, asset_key: str) -> AssetRow:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            select id, asset_key, display_name, version_no, source_name, source_uri,
                   content_json, metadata_json
            from asset_registry
            where asset_type=%s and asset_key=%s and asset_stage='production' and status='active'
            order by version_no desc, id desc
            limit 1
            """,
            (ARTICLE_ASSET_TYPE, asset_key),
        )
        row = cursor.fetchone()
    if not row:
        raise RuntimeError(f"active asset not found: {asset_key}")
    return AssetRow(
        id=int(row["id"]),
        asset_key=str(row["asset_key"]),
        display_name=row.get("display_name"),
        version_no=int(row["version_no"]),
        source_name=row.get("source_name"),
        source_uri=row.get("source_uri"),
        content_json=_json_value(row.get("content_json")) or {},
        metadata_json=_json_value(row.get("metadata_json")) or {},
    )


def _migrate_wangyue(content: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(content)
    source_items = [item for item in content.get("items") or [] if isinstance(item, dict)]
    if not source_items:
        raise RuntimeError("Wangyue items are empty")

    parsed = [_parse_wangyue_corpus(str(item.get("corpus") or "")) for item in source_items]
    common_instruction = parsed[0]["generation_instruction"]
    common_hard_boundaries = parsed[0]["hard_boundaries"]
    common_writing_requirements = parsed[0]["writing_requirements"]
    if any(item["generation_instruction"] != common_instruction for item in parsed):
        raise RuntimeError("Wangyue generation instruction is not common")
    if any(item["hard_boundaries"] != common_hard_boundaries for item in parsed):
        raise RuntimeError("Wangyue hard boundaries are not common")

    next_items: list[dict[str, Any]] = []
    for source_item, parts in zip(source_items, parsed):
        item = copy.deepcopy(source_item)
        item["corpus"] = parts["content_direction"]
        item["content_direction"] = parts["content_direction"]
        item.pop("prompt_mode", None)
        item.pop("generation_instruction", None)
        item.pop("hard_boundaries", None)
        item.pop("generation_requirements", None)
        if parts["inspiration_options"]:
            item["variation_slots"] = [
                {
                    "slot_code": "inspiration_material",
                    "slot_name": "灵感线索",
                    "options": parts["inspiration_options"],
                    "offset": 0,
                }
            ]
        else:
            item.pop("variation_slots", None)
        if parts["writing_requirements"] == common_writing_requirements:
            item.pop("writing_requirements", None)
        else:
            item["writing_requirements"] = parts["writing_requirements"]
        next_items.append(item)

    migrated["generation_prompt_mode"] = "layered_article"
    migrated["generation_instruction"] = common_instruction
    migrated["hard_boundaries"] = common_hard_boundaries
    migrated["writing_requirements"] = common_writing_requirements
    migrated["generation_requirements"] = [WANGYUE_DIVERSITY_REQUIREMENT]
    migrated["items"] = next_items
    migrated["prompt_framework"] = "painpoint_selling_layered_v1"
    return migrated


def _migrate_chunyue(content: dict[str, Any]) -> dict[str, Any]:
    migrated = copy.deepcopy(content)
    items = [copy.deepcopy(item) for item in content.get("items") or [] if isinstance(item, dict)]
    if not items:
        raise RuntimeError("Chunyue items are empty")
    common_fields = {
        field: copy.deepcopy(items[0].get(field))
        for field in (
            "generation_instruction",
            "writing_requirements",
            "generation_requirements",
            "variation_slots",
        )
    }
    for field, value in common_fields.items():
        if any(item.get(field) != value for item in items):
            raise RuntimeError(f"Chunyue field is not common: {field}")
    for item in items:
        for field in (
            "prompt_mode",
            "generation_instruction",
            "writing_requirements",
            "generation_requirements",
            "variation_slots",
        ):
            item.pop(field, None)
    migrated["generation_prompt_mode"] = "layered_article"
    migrated.update(common_fields)
    migrated["items"] = items
    migrated["prompt_framework"] = "painpoint_selling_layered_v1"
    return migrated


def _parse_wangyue_corpus(corpus: str) -> dict[str, Any]:
    instruction_match = re.search(r"生文指令：(?P<value>[^\n]+)", corpus)
    direction_match = re.search(
        r"内容方向：\n(?P<value>[\s\S]*?)(?=\n\n【本篇灵感线索】|\n\n事实与合规边界：)",
        corpus,
    )
    inspiration_match = re.search(
        r"【本篇灵感线索】\n(?P<value>(?:- [^\n]+\n?)+)",
        corpus,
    )
    hard_match = re.search(
        r"事实与合规边界：\n(?P<value>[\s\S]*?)(?=\n\n成文要求：)",
        corpus,
    )
    writing_match = re.search(r"成文要求：\n(?P<value>[\s\S]*)$", corpus)
    if not instruction_match or not direction_match or not hard_match or not writing_match:
        raise RuntimeError("unrecognized Wangyue rule corpus")
    return {
        "generation_instruction": instruction_match.group("value").strip(),
        "content_direction": direction_match.group("value").strip(),
        "inspiration_options": _bullet_lines(
            inspiration_match.group("value") if inspiration_match else ""
        ),
        "hard_boundaries": _bullet_lines(hard_match.group("value")),
        "writing_requirements": _bullet_lines(writing_match.group("value")),
    }


def _bullet_lines(text: str) -> list[str]:
    return [
        line.strip()[2:].strip()
        for line in str(text or "").splitlines()
        if line.strip().startswith("- ") and line.strip()[2:].strip()
    ]


def _validate_migration(
    brand: str,
    source: dict[str, Any],
    migrated: dict[str, Any],
) -> dict[str, Any]:
    source_items = source.get("items") or []
    migrated_items = migrated.get("items") or []
    if len(source_items) != len(migrated_items):
        raise RuntimeError(f"{brand} item count changed")
    source_rule_ids = [item.get("rule_id") for item in source_items]
    migrated_rule_ids = [item.get("rule_id") for item in migrated_items]
    if source_rule_ids != migrated_rule_ids:
        raise RuntimeError(f"{brand} rule ids changed")
    if source.get("selling_painpoint_expressions") != migrated.get("selling_painpoint_expressions"):
        raise RuntimeError(f"{brand} selling expression pool changed")
    return {
        "item_count": len(migrated_items),
        "rule_ids_preserved": True,
        "selling_expression_pool_preserved": True,
        "prompt_framework": migrated.get("prompt_framework"),
        "asset_level_fields": [
            field
            for field in (
                "generation_instruction",
                "hard_boundaries",
                "writing_requirements",
                "generation_requirements",
                "variation_slots",
            )
            if field in migrated
        ],
    }


def _insert_asset(
    conn: pymysql.Connection,
    *,
    source: AssetRow,
    target_key: str,
    target_version: int,
    content_json: dict[str, Any],
    mode: str,
    brand: str,
) -> int:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            update asset_registry
            set status='archived'
            where asset_type=%s and asset_key=%s and asset_stage='production' and status='active'
            """,
            (ARTICLE_ASSET_TYPE, target_key),
        )
        metadata = copy.deepcopy(source.metadata_json)
        metadata.update(
            {
                "prompt_framework": "painpoint_selling_layered_v1",
                "framework_migration_mode": mode,
                "framework_migration_brand": brand,
                "framework_migration_base_asset_id": source.id,
                "framework_migration_base_version_no": source.version_no,
            }
        )
        cursor.execute(
            """
            insert into asset_registry (
                asset_type, asset_key, display_name, version_no, status, asset_stage,
                source_name, source_uri, source_hash, content_json, metadata_json, created_by
            ) values (%s,%s,%s,%s,'active','production',%s,%s,null,cast(%s as json),cast(%s as json),%s)
            """,
            (
                ARTICLE_ASSET_TYPE,
                target_key,
                source.display_name,
                target_version,
                f"layered_framework_migration:{source.asset_key}:v{source.version_no}",
                source.source_uri,
                json.dumps(content_json, ensure_ascii=False),
                json.dumps(metadata, ensure_ascii=False),
                "codex_layered_framework_20260721",
            ),
        )
        return int(cursor.lastrowid)


def _next_asset_version(conn: pymysql.Connection, asset_key: str) -> int:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            select coalesce(max(version_no), 0) as max_version
            from asset_registry
            where asset_type=%s and asset_key=%s and asset_stage='production'
            """,
            (ARTICLE_ASSET_TYPE, asset_key),
        )
        row = cursor.fetchone() or {}
    return int(row.get("max_version") or 0) + 1


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


if __name__ == "__main__":
    main()
