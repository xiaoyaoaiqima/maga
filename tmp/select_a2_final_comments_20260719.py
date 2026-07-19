"""Human-quality and similarity selection for the 2026-07-19 A2 four-category delivery."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pymysql


OLD_BATCHES = {655, 656, 657, 658}
NEW_BATCHES = set(range(668, 691))
ALL_BATCHES = OLD_BATCHES | NEW_BATCHES
TARGET_PER_CATEGORY = 105

CATEGORY_RULES = {
    "有货-直给": {"a2_direct_01", "a2_direct_43"},
    "批批检、批次报告、检测透明": {"a2_direct_45", "a2_direct_46", "a2_direct_47"},
    "罐底扫码、三方质检报告": {"a2_direct_48", "a2_direct_49"},
    "会员权益、集罐换奶粉、抽奖、礼遇升级": {"a2_direct_28", "a2_direct_31", "a2_direct_33", "a2_direct_34"},
}

SUPPLY_RE = re.compile(r"到货|来货|补货|有货|上架|能买|买到|摆出来|摆上|补上|又有了|回来了|到了")
SCAN_RE = re.compile(r"扫|扫码|物流码|罐底|二维码|码")
REPORT_RE = re.compile(r"报告|质检")
MEMBER_RE = re.compile(r"会员|集罐|空罐|攒罐|积分|抽奖|换礼|权益|老客礼|礼品")

MANUAL_REJECTS = {
    (668, 8): "OMG开头和整体语气不够自然",
    (688, 28): "引入准备更换其他产品的负面前提",
    (688, 20): "幸福来得太突然，情绪过满",
    (677, 28): "口粮续上暗含断供焦虑",
    (677, 59): "到了到了快冲，语气过度催促",
    (688, 5): "我天加先囤，情绪偏满",
    (658, 10): "敢全公开品牌口号感过重",
    (658, 65): "硬核果断粉，口号感过重",
    (678, 23): "品牌敢公开，宣传腔明显",
    (658, 96): "翻来覆去看多遍，虚构动作过重",
    (678, 44): "下血本属于无依据品牌评价",
    (690, 7): "真挺放的，明显病句",
    (656, 100): "吓一跳不符合正向自然反应",
    (681, 9): "扫了扫，明显重复病句",
    (682, 51): "先写不放心，负面前提过重",
    (656, 8): "当妈的放心了，宣传模板感偏重",
    (676, 28): "写成已经积分换礼的兑换结果",
    (687, 5): "空罐换礼和会员积分混在一句",
    (673, 3): "囤罐子说法不自然",
    (655, 46): "虚构娃天天催兑换的家庭情节",
    (686, 14): "留个心眼带负面戒备语义",
    (655, 32): "先喝起来攒空罐，消费诱导感过强",
}


def brand_case(text: str) -> str:
    return re.sub(r"A2(?!蛋白)", "a2", text)


def normalized(text: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", brand_case(text).lower())


def ngrams(text: str, size: int = 2) -> set[str]:
    value = normalized(text)
    if len(value) <= size:
        return {value} if value else set()
    return {value[index : index + size] for index in range(len(value) - size + 1)}


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def opening_prefix(text: str, chars: int = 3) -> str:
    value = re.sub(r"^[\s，。！？!?,～~；;：:]+", "", text)
    return value[:chars]


def opening_clause(text: str) -> str:
    value = re.sub(r"^[\s，。！？!?,～~；;：:]+", "", text)
    return re.split(r"[，。！？!?,～~；;：:]", value, maxsplit=1)[0].strip()


def category_for(rule_id: str) -> str | None:
    for category, rule_ids in CATEGORY_RULES.items():
        if rule_id in rule_ids:
            return category
    return None


def hard_reasons(item: dict[str, Any]) -> list[str]:
    text = item["body"]
    category = item["category"]
    rule_id = item["rule_id"]
    reasons: list[str] = []

    manual_reason = MANUAL_REJECTS.get((item["batch_id"], item["item_no"]))
    if manual_reason:
        reasons.append(f"人工筛选：{manual_reason}")

    if len(normalized(text)) < 5:
        reasons.append("正文不足5字符")
    if re.search(r"先先|批报告|看报告的码|(^|[，。！？])现在$|[，。！？]放$|嗯？现在$", text):
        reasons.append("残句或明显病句")
    if re.search(r"尖叫|手抖|眼泪|开心到飞起|方便到我想哭|感动到想哭", text):
        reasons.append("情绪或肢体反应过度")
    if "😭" in text:
        reasons.append("情绪表达过度")

    if category == "有货-直给":
        supply_text = text.replace("看到了", "").replace("听到了", "")
        if not SUPPLY_RE.search(supply_text):
            reasons.append("缺少供货语义")
        if re.search(r"缺货|断粮|抢不到", text):
            reasons.append("出现消极缺货词")
        if re.search(r"[一二两三四五六七八九十\d]+(?:包|袋|盒|件|桶)|拿了两个|买了两个|拎了两个", text):
            reasons.append("奶粉数量单位不合适")
    elif category == "批批检、批次报告、检测透明":
        if not re.search(r"批|检测|报告|透明|公开|能查|可查|查到", text):
            reasons.append("批批检业务信息不足")
        if SCAN_RE.search(text):
            reasons.append("混入罐底扫码方向")
        if re.search(r"放心喝|闭眼|绝对安全|百分百|保证安全|包过", text):
            reasons.append("检测信息被写成绝对安全结论")
        if re.search(r"开罐|冲奶|喂奶|奶量|宝宝喝|娃喝", text):
            reasons.append("虚构喂养或使用经历")
        if re.search(r"有点担心|担心批次|终于有品牌|终于找到|品牌敢|敢.*公开|当妈的|yyds|狠狠|硬核|第一次觉得", text, flags=re.IGNORECASE):
            reasons.append("负面前提或品牌口号感过重")
    elif category == "罐底扫码、三方质检报告":
        if not SCAN_RE.search(text) or not REPORT_RE.search(text):
            reasons.append("扫码或报告业务信息不足")
        if re.search(r"放心喝|闭眼|绝对安全|百分百|保证安全|包过", text):
            reasons.append("报告信息被写成绝对安全结论")
        if re.search(r"盒子上的码|第三方检测数据|第三方质检报告|三方检测报告|二维码", text):
            reasons.append("扫码位置或报告名称不准确")
        if re.search(r"试了好几次|之前.*(?:担心|不放心)|第一次扫|终于找到入口|开罐|码住码住|扫了扫|真挺放的", text):
            reasons.append("新增负面体验或无关使用经历")
        if rule_id == "a2_direct_49" and "三方质检报告" not in text:
            reasons.append("三方质检报告名称不完整")
    elif category == "会员权益、集罐换奶粉、抽奖、礼遇升级":
        if not re.search(r"a2|至初", text, flags=re.IGNORECASE):
            reasons.append("缺少a2品牌锚点")
        if not MEMBER_RE.search(text):
            reasons.append("会员权益动作不清楚")
        if re.search(r"免费游|新西兰游|新西兰行|新西兰之旅|旅行|旅游", text):
            reasons.append("把新西兰溯源误写成旅行")
        if re.search(r"优惠券|折扣|返现|现金|抵钱|更便宜|划算", text):
            reasons.append("新增未确认优惠权益")
        if re.search(r"(?:积分|集罐).*(?:换了|兑了)|(?:换了|兑了).*(?:礼|车|奶粉|推车)|中奖|收到(?:了)?(?:礼|奖)|宝宝.*(?:骑|玩)|娃.*(?:骑|玩|不撒手|两眼发光)|玩疯了|超爱骑|已经集齐", text):
            reasons.append("虚构兑换中奖或礼品使用结果")
        if re.search(r"积分抽奖|集罐.*攒积分|空罐.*积分|集罐.*积分|送了个小罐子|颜色挺好看|积分换礼了", text):
            reasons.append("会员活动事实混写或新增素材")
        if rule_id == "a2_direct_31" and not re.search(r"抽奖|碰运气|参与", text):
            reasons.append("抽奖动作不清楚")
        if rule_id == "a2_direct_28" and not re.search(r"集罐|空罐|攒罐|换", text):
            reasons.append("集罐换礼动作不清楚")
        if rule_id == "a2_direct_33" and not re.search(r"权益|升级|加码", text):
            reasons.append("权益升级信息不清楚")

    return list(dict.fromkeys(reasons))


def quality_score(item: dict[str, Any]) -> int:
    text = item["body"]
    score = 100
    length = len(text)
    if 8 <= length <= 36:
        score += 5
    elif length > 60:
        score -= 20
    elif length > 45:
        score -= 10
    if item["source"] == "new_diverse":
        score += 3
    if "？" in text or "?" in text:
        score += 2
    for pattern, penalty in (
        (r"当妈的|这波操作|yyds|狠狠|锁了", 6),
        (r"天呐|天哪|妈呀|哇塞|OMG|狂喜", 3),
        (r"瞬间安心|太安心|直接放心|安心到不行", 4),
        (r"果断粉|路转粉|直接爱", 3),
    ):
        if re.search(pattern, text, flags=re.IGNORECASE):
            score -= penalty
    return score


def stable_key(item: dict[str, Any]) -> str:
    raw = f"{item['batch_id']}:{item['item_no']}:{item['body']}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def select_diverse(
    category: str,
    candidates: list[dict[str, Any]],
    target: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    remaining = sorted(candidates, key=lambda item: (-item["quality_score"], stable_key(item)))
    prefix3_counts: Counter[str] = Counter()
    prefix1_counts: Counter[str] = Counter()
    clause_counts: Counter[str] = Counter()
    deferred: list[dict[str, Any]] = []

    caps = {
        "有货-直给": {"prefix3": 4, "prefix1": 20, "clause": 2},
        "批批检、批次报告、检测透明": {"prefix3": 5, "prefix1": 35, "clause": 3},
        "罐底扫码、三方质检报告": {"prefix3": 5, "prefix1": 55, "clause": 2},
        "会员权益、集罐换奶粉、抽奖、礼遇升级": {"prefix3": 5, "prefix1": 60, "clause": 2},
    }[category]

    for threshold in (0.42, 0.46, 0.50, 0.54, 0.58, 0.62):
        progress = True
        while progress and remaining and len(selected) < target:
            progress = False
            ranked: list[tuple[float, int, str, dict[str, Any]]] = []
            for item in remaining:
                prefix3 = opening_prefix(item["body"], 3)
                prefix1 = opening_prefix(item["body"], 1)
                clause = opening_clause(item["body"])
                if (
                    prefix3_counts[prefix3] >= caps["prefix3"]
                    or prefix1_counts[prefix1] >= caps["prefix1"]
                    or clause_counts[clause] >= caps["clause"]
                ):
                    continue
                max_similarity = max(
                    (jaccard(item["ngrams"], chosen["ngrams"]) for chosen in selected),
                    default=0.0,
                )
                if max_similarity >= threshold:
                    continue
                ranked.append((max_similarity, -item["quality_score"], stable_key(item), item))
            if not ranked:
                break
            _, _, _, chosen = min(ranked)
            remaining.remove(chosen)
            selected.append(chosen)
            prefix3_counts[opening_prefix(chosen["body"], 3)] += 1
            prefix1_counts[opening_prefix(chosen["body"], 1)] += 1
            clause_counts[opening_clause(chosen["body"])] += 1
            progress = True

    for item in remaining:
        max_similarity = max(
            (jaccard(item["ngrams"], chosen["ngrams"]) for chosen in selected),
            default=0.0,
        )
        item["rejection_reasons"] = [f"与已选评论相似度过高({max_similarity:.3f})"]
        item["max_similarity_to_selected"] = round(max_similarity, 4)
        deferred.append(item)
    return selected, deferred


def fetch_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    conn = pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        placeholders = ",".join(["%s"] * len(ALL_BATCHES))
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id AS item_id, batch_id, item_no, status, body,
                       JSON_UNQUOTE(JSON_EXTRACT(plan_json, '$.rule_id')) AS rule_id,
                       JSON_UNQUOTE(JSON_EXTRACT(plan_json, '$.business_rule')) AS business_rule,
                       JSON_EXTRACT(quality_json, '$.hard_pass') = true AS machine_hard_pass,
                       JSON_UNQUOTE(JSON_EXTRACT(quality_json, '$.review_report.rewrite_reason')) AS rewrite_reason
                FROM content_batch_item
                WHERE batch_id IN ({placeholders}) AND status = 'generated'
                ORDER BY batch_id, item_no
                """,
                sorted(ALL_BATCHES),
            )
            return list(cursor.fetchall())
    finally:
        conn.close()


def build(args: argparse.Namespace) -> dict[str, Any]:
    rows = fetch_rows(args)
    accepted_by_category: dict[str, list[dict[str, Any]]] = {category: [] for category in CATEGORY_RULES}
    rejected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for row in rows:
        batch_id = int(row["batch_id"])
        if batch_id in OLD_BATCHES and not bool(row["machine_hard_pass"]):
            continue
        rule_id = str(row.get("rule_id") or "")
        category = category_for(rule_id)
        if not category:
            continue
        body = brand_case(str(row.get("body") or "").strip())
        item = {
            "category": category,
            "source": "old_358" if batch_id in OLD_BATCHES else "new_diverse",
            "batch_id": batch_id,
            "item_no": int(row["item_no"]),
            "item_id": int(row["item_id"]),
            "rule_id": rule_id,
            "business_rule": str(row.get("business_rule") or ""),
            "body": body,
            "machine_hard_pass": bool(row["machine_hard_pass"]),
            "machine_rewrite_reason": str(row.get("rewrite_reason") or ""),
            "normalized": normalized(body),
            "ngrams": ngrams(body),
        }
        duplicate_key = (category, item["normalized"])
        if duplicate_key in seen:
            item["rejection_reasons"] = ["完全重复"]
            rejected.append(item)
            continue
        seen.add(duplicate_key)
        reasons = hard_reasons(item)
        if reasons:
            item["rejection_reasons"] = reasons
            rejected.append(item)
            continue
        item["quality_score"] = quality_score(item)
        accepted_by_category[category].append(item)

    result: dict[str, Any] = {"categories": {}, "rejected": []}
    for category, candidates in accepted_by_category.items():
        selected, similarity_rejected = select_diverse(category, candidates, TARGET_PER_CATEGORY)
        for delivery_no, item in enumerate(selected, start=1):
            item["delivery_no"] = delivery_no
            item["max_similarity_to_selected"] = round(
                max(
                    (jaccard(item["ngrams"], other["ngrams"]) for other in selected if other is not item),
                    default=0.0,
                ),
                4,
            )
        rejected.extend(similarity_rejected)
        result["categories"][category] = {
            "candidate_count_after_human_rules": len(candidates),
            "selected_count": len(selected),
            "old_selected_count": sum(item["source"] == "old_358" for item in selected),
            "new_selected_count": sum(item["source"] == "new_diverse" for item in selected),
            "max_pairwise_similarity": max((item["max_similarity_to_selected"] for item in selected), default=0.0),
            "items": selected,
        }

    def serializable(item: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in item.items() if key not in {"ngrams", "normalized"}}

    result["categories"] = {
        category: {**data, "items": [serializable(item) for item in data["items"]]}
        for category, data in result["categories"].items()
    }
    result["rejected"] = [serializable(item) for item in rejected]
    result["summary"] = {
        "source_row_count": len(rows),
        "selected_total": sum(data["selected_count"] for data in result["categories"].values()),
        "rejected_total": len(rejected),
        "target_per_category": TARGET_PER_CATEGORY,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="maga")
    parser.add_argument("--password", default="maga123456")
    parser.add_argument("--database", default="maga")
    parser.add_argument("--output", default="tmp/a2_final_selection_20260719.json")
    args = parser.parse_args()
    result = build(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(output.resolve()),
        "summary": result["summary"],
        "categories": {category: {key: value for key, value in data.items() if key != "items"} for category, data in result["categories"].items()},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
