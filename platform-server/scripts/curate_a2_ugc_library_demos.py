"""Curate a small set of reusable demos from the 2026-07-16 A2 UGC workbook."""
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

RULE_UPDATES: dict[str, dict[str, Any]] = {
    "a2_direct_43": {
        "examples": [
            "我也买到了新货了",
            "今天去店里一看，货架挺足，先囤一罐放家里",
            "昨天去买已经有货啦，晚上冲奶不用临时准备",
        ],
    },
    "a2_direct_28": {
        "content_direction": (
            "写看到集罐换礼后的自然反应，可以是刚知道、开始留空罐、"
            "已经攒了一些或准备兑换。"
        ),
        "activity_material": [
            "a2会员集罐活动可以兑换扭扭车、自行车、奶粉或婴儿推车。",
        ],
        "examples": [
            "妈妈群在说a2集罐能换奶粉，我已经开始留空罐了",
            "a2会员活动这么弄挺好，能攒罐换奶粉，家里空罐先不扔了",
            "a2会员活动有点东西，集罐能换奶粉我记住了",
            "我最近才知道空罐还能攒，准备慢慢存起来😂",
            "家里已经攒了几个罐，留着还能换点东西",
            "我也开始留空罐了，长期下来确实有点用",
            "会员福利里集罐换奶粉挺实在，正好一起参加",
            "a2这次会员活动我翻了下，集罐可以换自行车，空罐先留着",
            "群里姐妹说a2集罐可以换扭扭车，空罐先不扔了",
            "看到a2集罐可以换婴儿推车，我先把空罐留着",
        ],
    },
    "a2_direct_31": {
        "content_direction": (
            "写看到溯源抽奖后的自然反应，可以是刚发现、准备看规则、"
            "顺手参加或轻轻说碰碰运气。"
        ),
        "activity_material": [
            "a2会员活动包含溯源抽奖。",
            "溯源抽奖礼品包括新西兰溯源、a2&小马宝莉黄金手串、宝宝夏凉被、a2营养全家礼和积分。",
        ],
        "examples": [
            "a2这波溯源抽奖里有宝宝夏凉被，我刚看到",
            "我看a2活动页写着，溯源抽奖里有a2&小马宝莉黄金手串",
            "看到a2会员升级才知道，溯源抽奖里有a2营养全家礼",
            "看到a2会员升级才知道，溯源抽奖里还有积分",
            "刚看到a2活动，抽奖和换礼都有，我先看下规则",
            "看活动页发现a2还有抽奖，我先把规则看明白再参加",
            "刚刷到a2会员活动，抽奖这块我会先看规则",
            "买奶粉时导购提醒看a2抽奖，我回家点开了规则",
            "刚发现还有溯源抽奖，顺便参加活动也不错",
        ],
    },
    "a2_direct_33": {
        "examples": [
            "a2会员权益升级还挺好，家里一直喝的话蛮实在",
            "a2这次会员权益加码挺明显，集罐能换奶粉，家里一直喝的确实用得上",
            "a2这次像整体升级了，会员活动也多了",
            "看活动页发现长期买也能参加，这点我觉得挺好",
            "朋友说a2这次老用户也有活动，我准备去看规则",
            "a2这波会员权益加码挺明显，常买的人会愿意研究下",
            "最近a2活动还挺多，集罐换奶粉算下来也能省点",
            "a2会员升级这波我看到了，活动规则写得还挺清楚",
            "这次a2会员权益加码了，家里一直喝的会多看一眼",
            "a2这波像在认真做老用户权益，补货时我会顺便问问",
            "刚看了会员页面，发现里面的福利还挺多",
        ],
    },
}


def curate_content(content_json: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(content_json)
    items = updated.get("items")
    if not isinstance(items, list):
        raise ValueError("asset content_json.items must be a list")
    by_id = {str(item.get("rule_id") or ""): item for item in items if isinstance(item, dict)}
    missing = sorted(set(RULE_UPDATES) - set(by_id))
    if missing:
        raise ValueError(f"active asset is missing expected rules: {', '.join(missing)}")

    for rule_id, changes in RULE_UPDATES.items():
        item = by_id[rule_id]
        if "content_direction" in changes:
            content_direction = str(changes["content_direction"]).strip()
            item["corpus"] = content_direction
            item["content_direction"] = content_direction
            bundle = item.get("comment_prompt_bundle")
            if not isinstance(bundle, dict):
                raise ValueError(f"rule is missing comment_prompt_bundle: {rule_id}")
            bundle["content_direction"] = content_direction
        if "activity_material" in changes:
            activity_material = list(changes["activity_material"])
            item["activity_material"] = activity_material
            bundle = item.get("comment_prompt_bundle")
            if not isinstance(bundle, dict):
                raise ValueError(f"rule is missing comment_prompt_bundle: {rule_id}")
            bundle["activity_material"] = activity_material
        item["examples"] = list(changes["examples"])
        item["supplements"] = []
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
    parser.add_argument("--created-by", default="a2-ugc-library-demo-curation")
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
            updated_content = curate_content(row.content_json)
            updated_metadata = copy.deepcopy(row.metadata_json)
            updated_metadata.update(
                {
                    "example_count": _example_count(updated_content),
                    "last_demo_curation_source": SOURCE_NAME,
                    "last_demo_curation_rule_ids": sorted(RULE_UPDATES),
                }
            )
            next_version = _next_asset_version(cursor, row)
            summary = {
                "asset_id": row.id,
                "current_version": row.version_no,
                "next_version": next_version,
                "updated_rule_ids": sorted(RULE_UPDATES),
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
