"""Persist A2 batch-check expression paths and batch variation review rules."""
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
TARGET_RULE_IDS = (
    "a2_direct_45",
    "a2_direct_46",
    "a2_direct_47",
    "a2_direct_48",
    "a2_direct_49",
)

EXPRESSION_PATHS: dict[str, list[str]] = {
    "a2_direct_45": [
        "从自己买过后开始留意每批检测切入。",
        "从选奶时开始关注是不是每批检测切入。",
        "从买奶粉前会多问一句检测频率切入。",
        "从母婴店或导购提到批批检切入。",
        "从宝妈群、评论区或朋友分享消息切入。",
        "从家里人提醒多关注检测信息切入。",
        "从长期给宝宝喝奶粉后更在意每批检测切入。",
        "从看配方之外也会看检测信息切入。",
        "用自然疑问确认是不是每批检测。",
        "从每次买奶粉都会顺手看检测信息的习惯切入。",
    ],
    "a2_direct_46": [
        "从收到奶粉后顺手查看对应批次报告切入。",
        "从开新罐前先看对应批次报告切入。",
        "从第一次知道批次报告可以查询切入。",
        "从宝妈群或评论区互相提醒查报告切入。",
        "从查看不同罐的对应批次入口切入，重点写能分别对应。",
        "从买奶粉时越来越关注报告能不能查切入。",
        "从长期给宝宝喝奶粉后想多确认批次信息切入。",
        "从家人或朋友分享报告入口切入。",
        "从母婴店了解到可以查询对应报告切入。",
        "从买回来逐渐形成先看对应报告的习惯切入。",
    ],
    "a2_direct_47": [
        "从自己买过后开始留意每批检测信息公开切入。",
        "从选奶时会把检测透明放进考虑项切入。",
        "从买奶粉前会多看一步批次报告切入。",
        "从第一次知道每批信息和报告都能查切入。",
        "从宝妈群、评论区或朋友分享消息切入。",
        "从查看不同罐的对应批次入口切入，重点写信息能对应。",
        "从长期给宝宝喝奶粉后想多确认检测信息切入。",
        "从家人提醒关注检测透明切入。",
        "从母婴店了解到报告可以查询切入。",
        "从平时买回来会顺手看一下批次信息切入。",
    ],
    "a2_direct_48": [
        "从收到奶粉后顺手扫罐底物流码切入。",
        "从开新罐前先扫一下罐底物流码切入。",
        "从第一次知道罐底物流码还能看报告切入。",
        "从宝妈群或评论区互相提醒扫码切入。",
        "从扫不同罐时都能找到各自对应报告切入。",
        "从买奶粉时越来越关注能不能扫码查报告切入。",
        "从长期给宝宝喝奶粉后想多确认批次信息切入。",
        "从家人或朋友提醒扫一下罐底码切入。",
        "从母婴店了解到罐底码可以查报告切入。",
        "从买回来逐渐形成顺手扫码的习惯切入。",
    ],
    "a2_direct_49": [
        "从收到奶粉后顺手扫码查看三方质检报告切入。",
        "从开新罐前先看三方质检报告切入。",
        "从第一次知道罐底码能看三方质检报告切入。",
        "从宝妈群或评论区互相提醒扫码看报告切入。",
        "从扫不同罐时都能找到各自对应的三方质检报告切入。",
        "从买奶粉时越来越关注三方质检报告能不能查切入。",
        "从长期给宝宝喝奶粉后想多确认质检信息切入。",
        "从家人或朋友分享三方质检报告入口切入。",
        "从母婴店了解到扫码可以看三方质检报告切入。",
        "从买回来逐渐形成顺手查看三方质检报告的习惯切入。",
    ],
}

BATCH_VARIATION_REVIEW = {
    "enabled": True,
    "affects_hard_pass": False,
    "expression_frequency": [
        {
            "group_key": "opener_meipi",
            "label": "每批开头",
            "terms": ["每批"],
            "match_mode": "prefix",
            "max_ratio": 0.2,
        },
        {
            "group_key": "opener_yuanlai",
            "label": "原来开头",
            "terms": ["原来"],
            "match_mode": "prefix",
            "max_ratio": 0.15,
        },
        {
            "group_key": "opener_gang",
            "label": "刚字开头",
            "terms": ["刚"],
            "match_mode": "prefix",
            "max_ratio": 0.2,
        },
        {
            "group_key": "opener_sao",
            "label": "扫字开头",
            "terms": ["扫"],
            "match_mode": "prefix",
            "max_ratio": 0.2,
        },
        {
            "group_key": "closure_tashi",
            "label": "踏实表达",
            "terms": ["踏实"],
            "match_mode": "contains",
            "max_ratio": 0.2,
        },
        {
            "group_key": "clarity_cluster",
            "label": "清楚清晰直观表达",
            "terms": ["清楚", "清晰", "直观"],
            "match_mode": "contains",
            "max_ratio": 0.3,
        },
    ],
    "opening_prefix_frequency": {
        "prefix_chars": 3,
        "max_count": 3,
    },
    "opening_clause_frequency": {
        "max_count": 2,
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
    missing = sorted(set(TARGET_RULE_IDS) - existing_ids)
    if missing:
        raise ValueError(f"active asset is missing expected rules: {', '.join(missing)}")

    for item in items:
        if not isinstance(item, dict):
            continue
        rule_id = str(item.get("rule_id") or "")
        paths = EXPRESSION_PATHS.get(rule_id)
        if not paths:
            continue
        item["prompt_slots"] = {"本条表达路径": list(paths)}
        item["prompt_slot_selection_mode"] = "round_robin"
        item["bundle_prompt_slots_source"] = "rule_asset"
        item["batch_variation_review"] = copy.deepcopy(BATCH_VARIATION_REVIEW)

    return updated


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
    parser.add_argument("--created-by", default="a2-batch-check-expression-paths")
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
                    "last_batch_check_expression_path_rule_ids": list(TARGET_RULE_IDS),
                    "last_batch_check_expression_path_counts": {
                        rule_id: len(EXPRESSION_PATHS[rule_id])
                        for rule_id in TARGET_RULE_IDS
                    },
                }
            )
            next_version = _next_asset_version(cursor, row)
            summary = {
                "asset_id": row.id,
                "current_version": row.version_no,
                "next_version": next_version,
                "updated_rule_ids": list(TARGET_RULE_IDS),
                "expression_path_counts": {
                    rule_id: len(EXPRESSION_PATHS[rule_id])
                    for rule_id in TARGET_RULE_IDS
                },
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
