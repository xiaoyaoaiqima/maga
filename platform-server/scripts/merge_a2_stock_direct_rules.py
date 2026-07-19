"""Merge A2 stock-direct comments into with-product and without-product rules."""
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
        _next_asset_version,
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
        _next_asset_version,
        _write_backup,
    )


ASSET_KEY = "a2_sentiment_comment_activity"
ASSET_TYPE = "comment_business_rule_set"
WITH_PRODUCT_RULE_ID = "a2_direct_01"
WITHOUT_PRODUCT_RULE_ID = "a2_direct_43"
REMOVED_RULE_ID = "a2_direct_44"
GENERATION_INSTRUCTION = "生成一条小红书的真实用户评论，口语化，有活人感"
CONTENT_DIRECTION = (
    "写直接的，自然的反应。\n"
    "信息渠道多样化，句式结构多样，随机使用生活场景，生成同质化的内容是原罪。"
)
WRITING_REQUIREMENTS = ["字数在20字以内"]
NOTES = ["不要说缺货、断粮等消极词。"]
RULE_DEFINITIONS = {
    WITH_PRODUCT_RULE_ID: {
        "business_rule": "有货-直给-提产品",
        "activity_material": ["a2或a2至初已经到货、来货，或重新能买到。"],
    },
    WITHOUT_PRODUCT_RULE_ID: {
        "business_rule": "有货-直给-不提产品",
        "activity_material": ["a2已经到货、来货，或重新能买到。生成的时候不要提产品名。"],
    },
}


def merge_content(content_json: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(content_json)
    items = updated.get("items")
    if not isinstance(items, list):
        raise ValueError("asset content_json.items must be a list")

    existing_ids = {
        str(item.get("rule_id") or "")
        for item in items
        if isinstance(item, dict)
    }
    required_ids = {WITH_PRODUCT_RULE_ID, WITHOUT_PRODUCT_RULE_ID, REMOVED_RULE_ID}
    missing = sorted(required_ids - existing_ids)
    if missing:
        raise ValueError(f"active asset is missing expected rules: {', '.join(missing)}")

    merged_items: list[dict[str, Any]] = []
    for source_item in items:
        if not isinstance(source_item, dict):
            continue
        rule_id = str(source_item.get("rule_id") or "")
        if rule_id == REMOVED_RULE_ID:
            continue
        item = copy.deepcopy(source_item)
        definition = RULE_DEFINITIONS.get(rule_id)
        if definition:
            activity_material = list(definition["activity_material"])
            item.update(
                {
                    "business_rule": definition["business_rule"],
                    "corpus": CONTENT_DIRECTION,
                    "content_direction": CONTENT_DIRECTION,
                    "activity_material": activity_material,
                    "prompt_mode": "comment_prompt_bundle",
                    "comment_prompt_bundle": {
                        "generation_instruction": GENERATION_INSTRUCTION,
                        "content_direction": CONTENT_DIRECTION,
                        "activity_material": activity_material,
                        "writing_requirements": list(WRITING_REQUIREMENTS),
                        "notes": list(NOTES),
                    },
                    "supplements": [],
                }
            )
        merged_items.append(item)

    for source_row_no, item in enumerate(merged_items, start=1):
        item["source_row_no"] = source_row_no
    updated["items"] = merged_items
    _add_without_product_rule_to_stock_scenarios(updated)
    return updated


def _add_without_product_rule_to_stock_scenarios(content_json: dict[str, Any]) -> None:
    for scenario in content_json.get("comment_scenarios") or []:
        if not isinstance(scenario, dict):
            continue
        for direction in scenario.get("directions") or []:
            if not isinstance(direction, dict):
                continue
            rule_ids = direction.get("rule_ids")
            if not isinstance(rule_ids, list) or WITH_PRODUCT_RULE_ID not in rule_ids:
                continue
            next_rule_ids: list[str] = []
            for rule_id in rule_ids:
                if rule_id not in next_rule_ids:
                    next_rule_ids.append(rule_id)
                if rule_id == WITH_PRODUCT_RULE_ID and WITHOUT_PRODUCT_RULE_ID not in next_rule_ids:
                    next_rule_ids.append(WITHOUT_PRODUCT_RULE_ID)
            direction["rule_ids"] = next_rule_ids


def _example_count(content_json: dict[str, Any]) -> int:
    return sum(
        len(item.get("examples") or []) + len(item.get("supplements") or [])
        for item in content_json.get("items") or []
        if isinstance(item, dict)
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="maga")
    parser.add_argument("--password", default="maga123456")
    parser.add_argument("--database", default="maga")
    parser.add_argument("--asset-stage", default="production")
    parser.add_argument("--backup-dir", default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--created-by", default="a2-stock-direct-two-rule-merge")
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    conn = _connect(_db_config_from_args(args))
    try:
        with conn.cursor() as cursor:
            row = _load_active_asset(
                cursor,
                asset_key=ASSET_KEY,
                asset_type=ASSET_TYPE,
                asset_stage=args.asset_stage,
            )
            updated_content = merge_content(row.content_json)
            updated_metadata = copy.deepcopy(row.metadata_json)
            updated_metadata.update(
                {
                    "rule_count": len(updated_content.get("items") or []),
                    "example_count": _example_count(updated_content),
                    "last_stock_direct_rule_ids": [WITH_PRODUCT_RULE_ID, WITHOUT_PRODUCT_RULE_ID],
                    "last_stock_direct_removed_rule_ids": [REMOVED_RULE_ID],
                    "last_stock_direct_generation_instruction": GENERATION_INSTRUCTION,
                }
            )
            next_version = _next_asset_version(cursor, row)
            summary = {
                "asset_id": row.id,
                "current_version": row.version_no,
                "next_version": next_version,
                "old_rule_count": len(row.content_json.get("items") or []),
                "new_rule_count": len(updated_content.get("items") or []),
                "old_example_count": _example_count(row.content_json),
                "new_example_count": _example_count(updated_content),
                "active_stock_direct_rule_ids": [WITH_PRODUCT_RULE_ID, WITHOUT_PRODUCT_RULE_ID],
                "removed_rule_ids": [REMOVED_RULE_ID],
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            if not args.apply:
                print("DRY-RUN: add --apply to create the new active version.")
                return
            backup_path = _write_backup(row, Path(args.backup_dir))
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
            print(f"BACKUP: {backup_path}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
