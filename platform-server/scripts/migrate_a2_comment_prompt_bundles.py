"""Upgrade the active A2 comment rule set to rule-owned prompt bundles."""
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
GENERATION_INSTRUCTION = "生成一条小红书母婴社区真实用户评论，口语化，有活人感。"


RULE_CONTENT: dict[str, dict[str, Any]] = {
    "a2_direct_01": {
        "business_rule": "有货-直给简单报喜",
        "content_direction": "写看到有货了的即时反应。像在评论区简单报喜或小感叹，不写下单、囤货等购买动作。",
        "activity_material": [
            "a2已经到货、来货，或重新能买到。",
            "品牌或产品名可写a2或a2至初。",
        ],
    },
    "a2_direct_02": {
        "content_direction": "写看到一条到货渠道线索后的自然接话，可以报信、追问或说自己准备去看看。",
        "activity_material": [
            "a2可以在妈妈群、导购、门店、山姆或线上平台出现到货或可买信息。",
            "品牌或产品名可写a2或a2至初。",
        ],
    },
    "a2_direct_03": {
        "content_direction": "写原本喝a2的妈妈看到有货后，准备继续熟悉款或把换奶晚点再说。",
        "activity_material": [
            "a2已经到货、发货或重新能买到。",
            "可以写原本喝a2，准备继续熟悉款或暂缓换奶。",
        ],
    },
    "a2_direct_04": {
        "content_direction": "写看自己这罐报告时顺手提到蜡样检测，可以说术语记不全或只记住未检出。",
        "activity_material": [
            "a2对应批次报告可以查看蜡样检测信息。",
            "可以写蜡样检测结果为未检出，不写具体数值。",
        ],
    },
    "a2_direct_05": {
        "content_direction": "写自己扫罐底码后看到这罐对应批次报告的即时反应，可以说入口能点开或没全看懂。",
        "activity_material": ["扫a2罐底物流码可以查看自己这罐对应批次报告。"],
    },
    "a2_direct_06": {
        "content_direction": "围绕检测报告顺手问一句或补一句，每条只说一个查询关注点。",
        "activity_material": ["扫a2罐底物流码可以查看自己这罐对应批次报告。"],
    },
    "a2_direct_10": {
        "content_direction": "写准备转奶时先看自己这罐报告的选择节奏，像妈妈自己拿主意。",
        "activity_material": [
            "a2每批检测信息可以查询。",
            "扫罐底物流码可以查看自己这罐对应批次报告。",
        ],
    },
    "a2_direct_11": {
        "content_direction": "写换奶前比较过其他奶粉后，更在意自己这罐报告能不能看到。",
        "activity_material": [
            "a2每批有质检和新西兰三方蜡样检测信息。",
            "扫罐底物流码可以查看自己这罐对应批次报告。",
        ],
    },
    "a2_direct_21": {
        "content_direction": "写比较过其他奶粉后，更看重每批检测和自己这罐报告可查。",
        "activity_material": [
            "a2公开每批检测信息。",
            "扫罐底物流码可以查看自己这罐对应批次报告。",
        ],
    },
    "a2_direct_13": {
        "content_direction": "写还没决定是否转奶时，先把自己这罐对应批次报告看明白。",
        "activity_material": ["扫a2罐底物流码可以查看自己这罐对应批次报告。"],
    },
    "a2_direct_14": {
        "content_direction": "写转奶前查看自己这罐质检和蜡样检测报告的即时反应。",
        "activity_material": [
            "a2对应批次报告可以查看质检和蜡样检测信息。",
            "可以写术语记不全或蜡样检测为未检出，不写具体数值。",
        ],
    },
    "a2_direct_15": {
        "content_direction": "写原本喝a2的妈妈看到有货后，先不换奶或先继续熟悉款。",
        "activity_material": [
            "a2已经到货、能拍或重新能买到。",
            "可以写原本喝a2，准备先不换奶。",
        ],
    },
    "a2_direct_16": {
        "content_direction": "写自己已经下单、到手或等到发货后，准备继续原来的a2。",
        "activity_material": [
            "a2已经到货、发货或重新能买到。",
            "可以写自己原本就在喝a2。",
        ],
    },
    "a2_direct_20": {
        "content_direction": "写评论区互相问购买线索，可以问哪里买、能不能拍、哪家店或说自己在等发货。",
        "activity_material": ["a2已经到货、能拍、发货或重新能买到。"],
    },
    "a2_direct_23": {
        "content_direction": "写选奶时除了看配方，也会多看一步自己这批报告。",
        "activity_material": ["扫a2罐底物流码可以查看自己这罐对应批次报告。"],
    },
    "a2_direct_24": {
        "content_direction": "写比较过其他奶粉后，又看到a2有货和报告可查，准备自己决定是否转回a2至初。",
        "activity_material": [
            "a2重新能买到。",
            "扫罐底物流码可以查看自己这罐对应批次报告。",
            "可以写准备转回a2至初。",
        ],
    },
    "a2_direct_28": {
        "content_direction": "写看到集罐换礼后的自然反应，可以是刚知道、开始留空罐、已经攒了一些或准备兑换。",
        "activity_material": ["a2会员集罐活动可以兑换扭扭车、自行车、奶粉或婴儿推车。"],
    },
    "a2_direct_29": {
        "content_direction": "写看到会员积分和积分换礼后的自然反应，可以说长期买会愿意看规则。",
        "activity_material": ["a2会员积分可以换实用礼品或抵一点。"],
    },
    "a2_direct_30": {
        "content_direction": "写老用户看到老客活动后的自然反应，可以说准备问清条件。",
        "activity_material": ["a2有老客礼或老用户活动，具体参加条件需要查看规则。"],
    },
    "a2_direct_31": {
        "content_direction": "写看到溯源抽奖后的自然反应，可以是刚发现、准备看规则、顺手参加或轻轻说碰碰运气。",
        "activity_material": [
            "a2会员活动包含溯源抽奖。",
            "溯源抽奖礼品包括新西兰溯源、a2&小马宝莉黄金手串、宝宝夏凉被、a2营养全家礼和积分。",
        ],
    },
    "a2_direct_32": {
        "content_direction": "写看到会员活动礼品后的自然反应，可以说礼品实用或准备先看规则。",
        "activity_material": ["a2会员活动中有礼品，具体礼品按活动正式信息。"],
    },
    "a2_direct_33": {
        "content_direction": "写看到会员权益升级后的自然反应，重点是长期喝的人会留意、权益更实在。",
        "activity_material": ["a2会员权益有升级或加码，老用户也可以关注活动规则。"],
    },
    "a2_direct_34": {
        "content_direction": "写看到会员活动后的自然接话，每条只落一个具体活动动作。",
        "activity_material": ["a2会员活动可以包含集罐、积分、抽奖、换礼、老客礼或礼品。"],
    },
    "a2_direct_35": {
        "content_direction": "写普通消费者看到报告公开后的中立认可，也可以保留一点观望。",
        "activity_material": ["a2公开每批检测信息，对应批次报告可以查询。"],
    },
    "a2_direct_36": {
        "content_direction": "写比较保守的妈妈看到有货后先观察供应是否稳定，也可以说稳定会影响复购。",
        "activity_material": ["a2现在有货或恢复供应。"],
    },
    "a2_direct_37": {
        "content_direction": "写还在考虑要不要转回a2的当下想法，可以先看、先问或晚点决定。",
        "activity_material": [
            "a2重新能买到。",
            "a2对应批次报告可以查询。",
        ],
    },
    "a2_direct_38": {
        "content_direction": "写普通消费者刷到业绩、市场表现或口碑后的顺手评论，语气中立。",
        "activity_material": ["帖子提供了a2的业绩、市场表现或口碑信息。"],
    },
    "a2_direct_40": {
        "content_direction": "轻轻问一个最近的生活变化有没有可能相关，只提一个变量。",
        "activity_material": ["可以提辅食、作息、气温变化、长牙等一个生活变量。"],
    },
    "a2_direct_41": {
        "content_direction": "顺手提醒每个宝宝反应不一样，或者单看一次不好判断。",
        "activity_material": ["可以最多带半句自家和别人家反应不同。"],
    },
    "a2_direct_42": {
        "content_direction": "写普通妈妈看完工艺信息后，顺手说一句自己能理解的点。",
        "activity_material": ["a2可以提鲜奶一次成粉、链路短或工艺信息清楚。"],
    },
}


NEW_DIRECT_RULES = [
    {
        "rule_id": "a2_direct_43",
        "business_rule": "有货-直给已经买到",
        "content_direction": "写自己已经买到、拍到或拿到后的即时反应。正文落在一个已完成的购买动作，不写准备去买。",
        "activity_material": [
            "可以写自己已经买到、拍到或拿到a2。",
            "品牌或产品名可写a2或a2至初。",
        ],
        "notes": [
            "不要说缺货、断粮等消极词。",
            "只写购买完成和自己的反应，不写宝宝喝后状态。",
        ],
        "examples": [
            "我也买到了新货了",
            "今天去店里一看，货架挺足，先囤一罐放家里",
            "昨天去买已经有货啦，晚上冲奶不用临时准备",
        ],
    },
    {
        "rule_id": "a2_direct_44",
        "business_rule": "有货-直给准备购买",
        "content_direction": "写看到有货后准备去买、下单或看看。事情还没发生，不写已经买到。",
        "activity_material": [
            "a2已经到货、来货，或重新能买到。",
            "可以写自己准备去买、下单或看看a2。",
            "品牌或产品名可写a2或a2至初。",
        ],
        "examples": [
            "看到a2能买了就松口气了",
            "我家这罐快见底了，看到有货，补起来不用到处找",
        ],
    },
]


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
    parser.add_argument("--created-by", default="a2-comment-prompt-bundle-migration")
    parser.add_argument("--preview-file", default=None)
    parser.add_argument("--apply", action="store_true")
    return parser


def _writing_requirements(business_rule: str) -> list[str]:
    if business_rule.startswith("有货-直给"):
        return ["字数在20字以内"]
    if business_rule.startswith("有货-"):
        return ["字数在30字以内"]
    if business_rule.startswith(("批批检-", "转奶-")):
        return ["字数在40字以内"]
    return ["字数在35字以内"]


def _notes(business_rule: str) -> list[str]:
    if business_rule.startswith("有货-"):
        return ["不要说缺货、断粮等消极词。"]
    if business_rule.startswith("批批检-"):
        return ["不补活动素材外的检测项目、数值或安全结论。"]
    if business_rule.startswith("转奶-"):
        return ["不写转奶步骤、宝宝喝后效果或适应结果。"]
    if business_rule.startswith("会员权益-"):
        return ["不补活动素材外的礼品、门槛、领取或中奖结果。"]
    if business_rule.startswith("舆情讨论-"):
        return ["不写成品牌公关稿。"]
    if business_rule.startswith("舆情缓和-轻问"):
        return ["不写成确定归因或诊断。"]
    if business_rule.startswith("舆情缓和-"):
        return ["不反驳发帖人，不补后来恢复或适应结果。"]
    if business_rule.startswith("工艺-"):
        return ["不写专业科普或宝宝喝后效果。"]
    return []


def _apply_bundle(item: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(item)
    if config.get("business_rule"):
        updated["business_rule"] = config["business_rule"]
    content_direction = str(config["content_direction"]).strip()
    activity_material = [str(value).strip() for value in config.get("activity_material") or [] if str(value).strip()]
    business_rule = str(updated.get("business_rule") or "").strip()
    bundle = {
        "generation_instruction": GENERATION_INSTRUCTION,
        "content_direction": content_direction,
        "activity_material": activity_material,
        "writing_requirements": list(config.get("writing_requirements") or _writing_requirements(business_rule)),
        "notes": list(config.get("notes") or _notes(business_rule)),
    }
    updated["prompt_mode"] = "comment_prompt_bundle"
    updated["comment_prompt_bundle"] = bundle
    updated["corpus"] = content_direction
    updated["content_direction"] = content_direction
    updated["activity_material"] = activity_material
    updated.pop("prompt_slots", None)
    updated.pop("comment_prompt_slots", None)
    updated.pop("variation_slots", None)
    updated.pop("preselected_variation_slots", None)
    updated.pop("prompt_slot_selection_mode", None)
    return updated


def migrate_content(content_json: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(content_json)
    updated["activity_name"] = "a2舆情改善评论"
    source_items = updated.get("items")
    if not isinstance(source_items, list):
        raise ValueError("asset content_json.items must be a list")
    by_id = {str(item.get("rule_id") or ""): item for item in source_items if isinstance(item, dict)}
    missing = sorted(set(RULE_CONTENT) - set(by_id))
    if missing:
        raise ValueError(f"active asset is missing expected rules: {', '.join(missing)}")

    migrated: list[dict[str, Any]] = []
    first = _apply_bundle(by_id["a2_direct_01"], RULE_CONTENT["a2_direct_01"])
    first["examples"] = [
        "a2终于到货了",
        "a2至初来货了！这下安心多了～",
        "刷到a2来货的消息了，挺开心的",
    ]
    migrated.append(first)
    new_rule_ids = {rule["rule_id"] for rule in NEW_DIRECT_RULES}
    for new_rule in NEW_DIRECT_RULES:
        base = copy.deepcopy(by_id.get(new_rule["rule_id"])) if by_id.get(new_rule["rule_id"]) else {
            "rule_id": new_rule["rule_id"],
            "business_rule": new_rule["business_rule"],
            "corpus": new_rule["content_direction"],
            "examples": list(new_rule.get("examples") or []),
            "supplements": [],
        }
        migrated.append(_apply_bundle(base, new_rule))

    for item in source_items:
        if not isinstance(item, dict):
            continue
        rule_id = str(item.get("rule_id") or "")
        if rule_id == "a2_direct_01" or rule_id in new_rule_ids:
            continue
        config = RULE_CONTENT.get(rule_id)
        migrated.append(_apply_bundle(item, config) if config else copy.deepcopy(item))

    for index, item in enumerate(migrated, start=1):
        item["source_row_no"] = index
    updated["items"] = migrated
    updated["comment_prompt_bundle_schema_version"] = 1
    updated.pop("comment_tone_options", None)
    updated.pop("comment_persona_options", None)
    return updated


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
            updated_content = migrate_content(row.content_json)
            next_version = _next_asset_version(cursor, row)
            summary = {
                "asset_id": row.id,
                "current_version": row.version_no,
                "next_version": next_version,
                "old_item_count": len(row.content_json.get("items") or []),
                "new_item_count": len(updated_content.get("items") or []),
                "bundle_item_count": sum(
                    1 for item in updated_content.get("items") or [] if item.get("prompt_mode") == "comment_prompt_bundle"
                ),
                "new_rule_ids": [item["rule_id"] for item in NEW_DIRECT_RULES],
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            if args.preview_file:
                preview_path = Path(args.preview_file)
                preview_path.parent.mkdir(parents=True, exist_ok=True)
                preview_path.write_text(json.dumps(updated_content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(f"PREVIEW: {preview_path}")
            if not args.apply:
                print("DRY-RUN: add --apply to create the new active version.")
                return
            backup_path = _write_backup(row, Path(args.backup_dir))
            new_id = _insert_new_version(
                cursor,
                row,
                next_version=next_version,
                content_json=updated_content,
                metadata_json=copy.deepcopy(row.metadata_json),
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
