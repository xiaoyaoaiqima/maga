"""Select four diverse 100-comment A2 delivery sets from recent generated batches."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pymysql


CATEGORY_CONFIG = {
    "有货到货": {
        "batch_ids": {580, 586, 590, 598},
        "item_allowlist": {},
        "excluded_rule_ids": set(),
    },
    "批批检、批次报告、检测透明": {
        "batch_ids": {581, 583, 584, 585, 587, 591, 594, 595, 597, 599, 601, 602},
        "item_allowlist": {581: {3, 5, 7, 8, 9}},
        "excluded_rule_ids": set(),
    },
    "罐底扫码、三方质检报告": {
        "batch_ids": {581, 588, 592},
        "item_allowlist": {581: {1, 2, 4, 6, 10}},
        "excluded_rule_ids": set(),
    },
    "会员权益、集罐换奶粉、抽奖、礼遇升级": {
        "batch_ids": {582, 589, 593, 596, 600},
        "item_allowlist": {582: {2, 3, 4, 5, 7, 8, 10}},
        "excluded_rule_ids": {"a2_direct_30"},
    },
}

RISK_PATTERNS = {
    "有货到货": re.compile(r"断粮|缺货|抢不到"),
    "批批检、批次报告、检测透明": re.compile(
        r"绝对安全|放心喝|闭眼喝|保证安全|百分百安全|给娃喝就一个字"
    ),
    "罐底扫码、三方质检报告": re.compile(
        r"绝对安全|放心喝|闭眼|包过|百分百|懵|没看懂|看不明白|怎么没写|啥也没"
    ),
    "会员权益、集罐换奶粉、抽奖、礼遇升级": re.compile(
        r"抵钱|返现|现金|优惠券|折扣|免费|积分能抽奖"
    ),
}


def _brand_case(text: str) -> str:
    return re.sub(r"A2(?!蛋白)", "a2", text)


def _normalized(text: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", _brand_case(text).lower())


def _ngrams(text: str, n: int = 2) -> set[str]:
    normalized = _normalized(text)
    if len(normalized) <= n:
        return {normalized} if normalized else set()
    return {normalized[index : index + n] for index in range(len(normalized) - n + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _stable_key(item: dict[str, Any]) -> str:
    raw = f"{item['batch_id']}:{item['item_no']}:{item['body']}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _select_diverse(
    candidates: list[dict[str, Any]],
    limit: int,
    *,
    max_similarity_limit: float | None = None,
) -> list[dict[str, Any]]:
    remaining = sorted(candidates, key=_stable_key)
    selected: list[dict[str, Any]] = []
    rule_counts: Counter[str] = Counter()
    while remaining and len(selected) < limit:
        if not selected:
            chosen = remaining.pop(0)
        else:
            def score(item: dict[str, Any]) -> tuple[float, int, str]:
                max_similarity = max(
                    _jaccard(item["ngrams"], selected_item["ngrams"])
                    for selected_item in selected
                )
                return (
                    max_similarity,
                    rule_counts[item["rule_id"]],
                    _stable_key(item),
                )

            chosen = min(remaining, key=score)
            if max_similarity_limit is not None:
                chosen_max_similarity = max(
                    _jaccard(chosen["ngrams"], selected_item["ngrams"])
                    for selected_item in selected
                )
                if chosen_max_similarity >= max_similarity_limit:
                    break
            remaining.remove(chosen)
        selected.append(chosen)
        rule_counts[chosen["rule_id"]] += 1
    return selected


def _pairwise_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    max_similarity = 0.0
    warning_pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(items):
        for right in items[left_index + 1 :]:
            similarity = _jaccard(left["ngrams"], right["ngrams"])
            max_similarity = max(max_similarity, similarity)
            if similarity >= 0.6:
                warning_pairs.append(
                    {
                        "left_no": left["delivery_no"],
                        "right_no": right["delivery_no"],
                        "similarity": round(similarity, 4),
                    }
                )
    return {
        "max_pairwise_jaccard_2gram": round(max_similarity, 4),
        "similarity_warning_pair_count": len(warning_pairs),
        "similarity_warning_pairs": warning_pairs,
    }


def _fetch_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
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
        batch_ids = sorted(
            {batch_id for config in CATEGORY_CONFIG.values() for batch_id in config["batch_ids"]}
        )
        placeholders = ",".join(["%s"] * len(batch_ids))
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    batch_id,
                    item_no,
                    body,
                    JSON_UNQUOTE(JSON_EXTRACT(plan_json, '$.rule_id')) AS rule_id,
                    JSON_UNQUOTE(JSON_EXTRACT(plan_json, '$.business_rule')) AS business_rule,
                    JSON_EXTRACT(quality_json, '$.hard_pass') = true AS hard_pass
                FROM content_batch_item
                WHERE batch_id IN ({placeholders})
                ORDER BY batch_id, item_no
                """,
                batch_ids,
            )
            return list(cursor.fetchall())
    finally:
        conn.close()


def build_delivery(rows: list[dict[str, Any]], limit: int = 100) -> dict[str, Any]:
    delivery: dict[str, Any] = {"categories": {}, "summary": {}}
    shortfalls: dict[str, int] = {}
    for category, config in CATEGORY_CONFIG.items():
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in rows:
            batch_id = int(row["batch_id"])
            item_no = int(row["item_no"])
            if batch_id not in config["batch_ids"] or not bool(row["hard_pass"]):
                continue
            allowlist = config["item_allowlist"].get(batch_id)
            if allowlist is not None and item_no not in allowlist:
                continue
            rule_id = str(row.get("rule_id") or "")
            if rule_id in config["excluded_rule_ids"]:
                continue
            body = _brand_case(str(row.get("body") or "").strip())
            normalized = _normalized(body)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            risk_hit = RISK_PATTERNS[category].search(body)
            candidates.append(
                {
                    "batch_id": batch_id,
                    "item_no": item_no,
                    "rule_id": rule_id,
                    "business_rule": str(row.get("business_rule") or ""),
                    "body": body,
                    "normalized": normalized,
                    "ngrams": _ngrams(body),
                    "human_risk": risk_hit.group(0) if risk_hit else None,
                }
            )
        clean_candidates = [item for item in candidates if not item["human_risk"]]
        risky_candidates = [item for item in candidates if item["human_risk"]]
        if category == "罐底扫码、三方质检报告":
            scan_rule_ids = {"a2_direct_05", "a2_direct_06", "a2_direct_48"}
            scan_clean = [item for item in clean_candidates if item["rule_id"] in scan_rule_ids]
            third_party_clean = [item for item in clean_candidates if item["rule_id"] == "a2_direct_49"]
            selected = _select_diverse(
                scan_clean,
                min(50, len(scan_clean)),
                max_similarity_limit=0.6,
            )
            third_party_selected = _select_diverse(
                third_party_clean,
                min(50, len(third_party_clean)),
                max_similarity_limit=0.6,
            )
            selected.extend(third_party_selected)
        else:
            selected = _select_diverse(
                clean_candidates,
                min(limit, len(clean_candidates)),
                max_similarity_limit=0.6,
            )
        if len(selected) < limit:
            shortfalls[category] = limit - len(selected)
        for index, item in enumerate(selected, start=1):
            item["delivery_no"] = index
        pairwise = _pairwise_metrics(selected)
        serialized = [
            {key: value for key, value in item.items() if key not in {"ngrams", "normalized"}}
            for item in selected
        ]
        delivery["categories"][category] = {
            "items": serialized,
            "candidate_count": len(candidates),
            "clean_candidate_count": len(clean_candidates),
            "risky_candidate_count": len(risky_candidates),
            "selected_risk_count": sum(bool(item["human_risk"]) for item in selected),
            **pairwise,
        }
    if shortfalls:
        raise ValueError(f"strict diversity shortfalls: {json.dumps(shortfalls, ensure_ascii=False)}")
    delivery["summary"] = {
        "category_count": len(delivery["categories"]),
        "delivered_comment_count": sum(
            len(category["items"]) for category in delivery["categories"].values()
        ),
    }
    return delivery


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="maga")
    parser.add_argument("--password", default="maga123456")
    parser.add_argument("--database", default="maga")
    parser.add_argument(
        "--output",
        default="../outputs/a2_four_categories_20260717/selected_delivery.json",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    delivery = build_delivery(_fetch_rows(args))
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(delivery, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(output_path),
        "summary": delivery["summary"],
        "categories": {
            category: {
                key: value
                for key, value in data.items()
                if key != "items" and key != "similarity_warning_pairs"
            }
            for category, data in delivery["categories"].items()
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
