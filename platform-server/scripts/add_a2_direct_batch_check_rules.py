"""Add three zero-shot direct batch-check comment rules to the active A2 asset."""
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
GENERATION_INSTRUCTION = "生成一条小红书母婴社区真实用户评论，口语化，有活人感。"
WRITING_REQUIREMENTS = ["字数在40字以内"]
COMMON_NOTES = ["不写具体检测项目、数值或安全结论。"]


NEW_RULES: list[dict[str, Any]] = [
    {
        "rule_id": "a2_direct_45",
        "business_rule": "批批检-直给认可",
        "content_direction": "写看到a2批批检后的直接反应。像在评论区顺手认可一下，情绪积极，可以带小感叹。",
        "activity_material": ["a2公开每批检测信息。"],
        "notes": COMMON_NOTES,
        "examples": [
            "批批检这点挺加分，检测项目一项项列得明白",
            "批批检能查看，检测记录清楚看着更踏实",
        ],
    },
    {
        "rule_id": "a2_direct_46",
        "business_rule": "批批检-批次报告直给",
        "content_direction": "写看到a2对应批次报告可以查询后的直接反应。简单说报告能查、内容看得见或信息能对应。",
        "activity_material": ["a2对应批次报告可以查询。"],
        "notes": COMMON_NOTES,
        "examples": [
            "看到能查报告就放心些，报告和实物能对应上",
            "拿到手先看报告，报告内容看着挺直观",
        ],
    },
    {
        "rule_id": "a2_direct_47",
        "business_rule": "批批检-检测透明直给",
        "content_direction": "写对a2公开每批检测信息、对应报告可以查询这件事的直接认可。情绪积极，不保留观望。",
        "activity_material": ["a2公开每批检测信息，对应批次报告可以查询。"],
        "notes": [
            "不写具体检测项目、数值或安全结论。",
            "不要写观望、再观察或质疑。",
        ],
        "examples": [
            "我也关注检测透明，报告和实物能对应上",
            "我也关注检测透明，检测记录清楚看着更踏实",
        ],
    },
]


def add_direct_rules(content_json: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(content_json)
    items = updated.get("items")
    if not isinstance(items, list):
        raise ValueError("asset content_json.items must be a list")
    existing_ids = {
        str(item.get("rule_id") or "")
        for item in items
        if isinstance(item, dict)
    }
    duplicates = sorted({rule["rule_id"] for rule in NEW_RULES} & existing_ids)
    if duplicates:
        raise ValueError(f"active asset already contains new rules: {', '.join(duplicates)}")

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
                    "writing_requirements": list(WRITING_REQUIREMENTS),
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
    parser.add_argument("--created-by", default="a2-direct-batch-check-rules")
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
            updated_content = add_direct_rules(row.content_json)
            updated_metadata = copy.deepcopy(row.metadata_json)
            updated_metadata.update(
                {
                    "rule_count": len(updated_content.get("items") or []),
                    "example_count": _example_count(updated_content),
                    "last_direct_rule_source": SOURCE_NAME,
                    "last_direct_rule_ids": [rule["rule_id"] for rule in NEW_RULES],
                }
            )
            next_version = _next_asset_version(cursor, row)
            summary = {
                "asset_id": row.id,
                "current_version": row.version_no,
                "next_version": next_version,
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
