"""Upgrade A2 target comment categories with a diversity instruction and two missing direct rules."""
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
SOURCE_NAME = "a2_UGC评论话术库_20260716_查重修订版.xlsx"
GENERATION_INSTRUCTION = (
    "生成一条小红书母婴社区真实用户评论，口语化，有活人感。"
    "句式结构多样一些，生成同质化的内容是原罪。"
)
TARGET_BUSINESS_PREFIXES = ("有货-", "批批检-", "会员权益-")


NEW_RULES: list[dict[str, Any]] = [
    {
        "rule_id": "a2_direct_48",
        "business_rule": "批批检-罐底扫码直给",
        "content_direction": (
            "写扫a2罐底物流码后看到自己这罐对应批次报告的直接反应。"
            "可以简单说能查到、能对应或入口清楚。"
        ),
        "activity_material": ["扫a2罐底物流码可以查看自己这罐对应批次报告。"],
        "notes": ["不写具体检测项目、数值或安全结论。"],
        "examples": [
            "罐底一扫就能看到，查起来确实不费劲",
            "这罐对应的报告查到了，对应内容看着挺完整",
        ],
    },
    {
        "rule_id": "a2_direct_49",
        "business_rule": "批批检-三方质检报告直给",
        "content_direction": (
            "写查到a2三方质检报告后的直接反应。"
            "简单说报告能查、信息清楚或自己能看。"
        ),
        "activity_material": ["扫a2罐底物流码可以查看自己这罐对应批次的三方质检报告。"],
        "notes": [
            "不写具体检测项目、数值或安全结论。",
            "统一写三方质检报告，不写三方检测报告。",
        ],
        "examples": [
            "查了罐底码，三方质检报告显示得挺直观",
            "三方质检报告能直接查，家长自己也能看明白",
        ],
    },
]


def upgrade_content(content_json: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(content_json)
    items = updated.get("items")
    if not isinstance(items, list):
        raise ValueError("asset content_json.items must be a list")

    existing_ids = {
        str(item.get("rule_id") or "")
        for item in items
        if isinstance(item, dict)
    }
    duplicate_new_ids = sorted({rule["rule_id"] for rule in NEW_RULES} & existing_ids)
    if duplicate_new_ids:
        raise ValueError(f"active asset already contains new rules: {', '.join(duplicate_new_ids)}")

    for item in items:
        if not isinstance(item, dict):
            continue
        business_rule = str(item.get("business_rule") or "")
        bundle = item.get("comment_prompt_bundle")
        if not business_rule.startswith(TARGET_BUSINESS_PREFIXES) or not isinstance(bundle, dict):
            continue
        bundle["generation_instruction"] = GENERATION_INSTRUCTION

    max_source_row_no = max(
        (int(item.get("source_row_no") or 0) for item in items if isinstance(item, dict)),
        default=0,
    )
    for offset, definition in enumerate(NEW_RULES, start=1):
        content_direction = str(definition["content_direction"]).strip()
        activity_material = list(definition["activity_material"])
        notes = list(definition["notes"])
        items.append(
            {
                "rule_id": definition["rule_id"],
                "business_rule": definition["business_rule"],
                "source_row_no": max_source_row_no + offset,
                "corpus": content_direction,
                "content_direction": content_direction,
                "activity_material": activity_material,
                "prompt_mode": "comment_prompt_bundle",
                "comment_prompt_bundle": {
                    "generation_instruction": GENERATION_INSTRUCTION,
                    "content_direction": content_direction,
                    "activity_material": activity_material,
                    "writing_requirements": ["字数在40字以内"],
                    "notes": notes,
                },
                "examples": list(definition["examples"]),
                "supplements": [],
            }
        )

    return updated


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
    parser.add_argument("--created-by", default="a2-four-category-upgrade")
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
            updated_content = upgrade_content(row.content_json)
            updated_metadata = copy.deepcopy(row.metadata_json)
            updated_metadata.update(
                {
                    "rule_count": len(updated_content.get("items") or []),
                    "example_count": _example_count(updated_content),
                    "last_four_category_source": SOURCE_NAME,
                    "last_four_category_generation_instruction": GENERATION_INSTRUCTION,
                    "last_four_category_new_rule_ids": [rule["rule_id"] for rule in NEW_RULES],
                }
            )
            next_version = _next_asset_version(cursor, row)
            updated_instruction_rule_count = sum(
                1
                for item in updated_content.get("items") or []
                if isinstance(item, dict)
                and str(item.get("business_rule") or "").startswith(TARGET_BUSINESS_PREFIXES)
                and isinstance(item.get("comment_prompt_bundle"), dict)
                and item["comment_prompt_bundle"].get("generation_instruction")
                == GENERATION_INSTRUCTION
            )
            summary = {
                "asset_id": row.id,
                "current_version": row.version_no,
                "next_version": next_version,
                "updated_instruction_rule_count": updated_instruction_rule_count,
                "new_rule_ids": [rule["rule_id"] for rule in NEW_RULES],
                "old_rule_count": len(row.content_json.get("items") or []),
                "new_rule_count": len(updated_content.get("items") or []),
                "old_example_count": _example_count(row.content_json),
                "new_example_count": _example_count(updated_content),
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
