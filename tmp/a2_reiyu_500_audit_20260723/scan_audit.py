from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path("/Users/luxifa/maga")
sys.path.insert(0, str(ROOT / "platform-server"))

from app.services.a2_reiyu_batch_detection_guard_service import (  # noqa: E402
    review_a2_reiyu_batch_detection_fact,
)
from app.services.a2_reiyu_old_can_guard_service import (  # noqa: E402
    review_a2_reiyu_old_can_eligibility,
)
from app.services.a2_reiyu_text_guard_service import review_a2_reiyu_text_surface  # noqa: E402
from app.services.business_forbidden_term_service import (  # noqa: E402
    A2_REIYU_UGC_POST_SEED_TERMS,
)


ASSET_PLAN = {"asset_key": "a2_reiyu_ugc_post_rules_v1"}
INPUT = Path(os.environ.get("A2_AUDIT_INPUT", ROOT / "tmp/a2_reiyu_500_audit_20260723/input_rows.json"))
OUTPUT = Path(os.environ.get("A2_AUDIT_OUTPUT", ROOT / "tmp/a2_reiyu_500_audit_20260723/scan_results.json"))


def title_weighted_len(title: str) -> int:
    total = 0
    for char in re.sub(r"\s+", "", title.strip()):
        if char in ("\u200d", "\ufe0f"):
            continue
        total += 2 if ord(char) >= 0x1F000 else 1
    return total


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[\n。！？!?；;]+", text) if s.strip()]


def add(issues: list[dict], code: str, evidence: str, severity: str = "candidate") -> None:
    key = (code, evidence)
    if any((i["code"], i["evidence"]) == key for i in issues):
        return
    issues.append({"code": code, "severity": severity, "evidence": evidence})


def business_entry_matches(text: str, entry: dict) -> bool:
    term = str(entry.get("term") or "")
    if not term or term not in text:
        return False
    mode = str(entry.get("match_mode") or "literal")
    ss = sentences(text)
    if mode == "registration_required_context":
        allowed = re.compile(
            rf"(?:不用|无需|不需要|不必|免)(?:先)?{re.escape(term)}"
            rf"|{re.escape(term)}(?:并)?(?:不需要|不是必须|非必须)"
        )
        return any(term in s and term in allowed.sub("", s) for s in ss)
    if mode == "risk_polarity_context":
        allowed = re.compile(
            rf"(?:完全|根本|并|也|真心|亲测|闭眼入)?"
            rf"(?:不|没|没有|不会|不太会|不容易|从没|从来没|从未|不算|算不上|谈不上)"
            rf"(?:再)?{re.escape(term)}"
        )
        return any(term in s and term in allowed.sub("", s) for s in ss)
    if mode == "detection_page_context":
        return any(term in s and any(marker in s for marker in ("每批", "批批", "检测")) for s in ss)
    if mode == "activity_prize_context":
        for s in ss:
            if term in s and any(
                cue in s
                for cue in ("奖品", "礼品", "兑换", "换到", "换个", "换一", "抽奖", "中奖", "集罐", "能领", "可以领", "活动送", "活动有", "福利有")
            ):
                return True
        return False
    if mode == "old_can_collection_context":
        collection = re.search(
            r"集罐|罐码累计|扫码累计|扫罐码集罐|集\s*\d+\s*罐|"
            r"凑\s*\d+\s*罐|集满\s*\d+\s*罐|罐数|"
            r"(?:换|兑|兑换)(?:小车|自行车|奶粉|正装|婴儿车)",
            text,
        )
        if collection is None:
            return False
        recent_purchase = re.search(
            rf"(?:活动期间|活动期内|参加活动后|看到活动后|知道活动后|发现活动后|按活动规则)"
            rf"[^。！？；;\n]{{0,16}}{re.escape(term)}",
            text,
        )
        return recent_purchase is None
    return True


def custom_checks(title: str, body: str, issues: list[dict]) -> None:
    text = f"{title}\n{body}"
    ss = sentences(text)

    weighted = title_weighted_len(title)
    if weighted > 20:
        add(issues, "title_too_long", f"加权{weighted}：{title}", "hard")

    for entry in A2_REIYU_UGC_POST_SEED_TERMS:
        if business_entry_matches(text, entry):
            add(
                issues,
                f"forbidden_{entry.get('enforcement')}",
                f"{entry.get('term')}｜{next((s for s in ss if str(entry.get('term')) in s), title)}",
                str(entry.get("enforcement")),
            )

    # Exact collect-can tiers. Generic mentions without a number are allowed.
    expected = {
        3: ("小车",),
        6: ("自行车", "小车"),
        12: ("奶粉", "正装"),
        18: ("婴儿车",),
    }
    reward_words = "小车车|小车|自行车|奶粉|正装|婴儿车"
    for s in ss:
        if not any(cue in s for cue in ("集罐", "兑换", "兑", "换", "集满", "集到", "集够")):
            continue
        for match in re.finditer(rf"(3|6|12|18)\s*罐[^，。！？；;\n]{{0,18}}?({reward_words})", s):
            count = int(match.group(1))
            reward = match.group(2)
            if not any(word in reward for word in expected[count]):
                add(issues, "collect_can_tier_error", s, "hard")
        for match in re.finditer(rf"({reward_words})[^，。！？；;\n]{{0,18}}?(?:要|需|得|集|攒|凑)?\s*(3|6|12|18)\s*罐", s):
            reward = match.group(1)
            count = int(match.group(2))
            if not any(word in reward for word in expected[count]):
                add(issues, "collect_can_tier_error", s, "hard")

    # Mechanism crossing.
    for s in ss:
        if "积分" in s and re.search(r"(?:换|兑|兑换)[^，。！？；;\n]{0,12}(?:小车|自行车|奶粉|婴儿车|旅游|手链|手串|夏凉被)", s):
            add(issues, "points_reward_crossing", s, "hard")
        if re.search(r"集罐[^，。！？；;\n]{0,10}(?:换|兑|兑换)[^，。！？；;\n]{0,5}积分|积分[^，。！？；;\n]{0,10}(?:集罐|罐数)", s):
            add(issues, "collect_can_points_crossing", s, "hard")
        if re.search(r"(?:罐底码|扫罐底|扫码)[^，。！？；;\n]{0,18}(?:抽奖|中奖|集罐|兑换|兑奖|攒罐)", s):
            # Keep generic “扫罐码集罐” allowed; only explicit bottom-code wording is wrong.
            if "罐底" in s:
                add(issues, "bottom_code_activity_entry", s, "hard")

    # Additional fabricated possession/child-sees-item phrasings not covered by the core guard.
    for s in ss:
        if re.search(r"(?:娃|宝宝|孩子)[^，。！？；;\n]{0,12}(?:看到|拿着|骑着|坐上|玩着)[^，。！？；;\n]{0,10}(?:实物|小车|自行车|婴儿车|奖品|礼物)", s):
            add(issues, "fabricated_reward_child_experience", s, "hard")
        if re.search(r"(?:已经|成功|终于)[^，。！？；;\n]{0,8}(?:兑换|兑|换|领取|领|拿)[^，。！？；;\n]{0,10}(?:小车|自行车|奶粉|正装|婴儿车|旅游|手链|夏凉被|奖品|礼品)", s):
            add(issues, "fabricated_reward_experience", s, "hard")

    for s in ss:
        if re.search(r"(?:这个活动叫|活动名称(?:是|叫)|活动是)(?:[^，。！？；;\n]{0,12})(?:会员|礼遇|升级)", s):
            add(issues, "activity_naming_explanation", s, "minor")
        if re.search(r"(?:冷水|凉水)[^，。！？；;\n]{0,8}(?:冲|泡)", s):
            add(issues, "cold_water_formula", s, "minor")
        if re.search(r"(?:喝完|吃完)[^，。！？；;\n]{0,10}(?:罐子|奶粉罐)[^，。！？；;\n]{0,8}(?:留|存|攒)", s):
            add(issues, "empty_can_storage_wording", s, "minor")

    # Candidate source stacking; requires manual review.
    source_groups = (
        ("宝爸", "爸爸", "孩子爸", "老公"),
        ("闺蜜", "朋友", "同事"),
        ("导购", "店员", "门店", "店里"),
        ("宝妈群", "妈妈群", "群里"),
        ("官号", "官方", "公众号"),
        ("刷到", "看到", "🍠", "pyq", "puq"),
    )
    for s in ss:
        group_count = sum(any(token in s for token in group) for group in source_groups)
        if group_count >= 3:
            add(issues, "source_stacking_candidate", s, "candidate")

    # Product-fact phrases worth manual factual verification, not automatic failure.
    for s in ss:
        if re.search(r"(?:纯|只含|百分百|100%)[^，。！？；;\n]{0,4}A2蛋白", s, re.I):
            add(issues, "pure_a2_protein_fact_candidate", s, "candidate")


def main() -> None:
    rows = json.loads(INPUT.read_text(encoding="utf-8"))
    results = []
    for csv_row, row in enumerate(rows[1:], start=2):
        title = str(row[1] or "").strip()
        body = str(row[2] or "").strip()
        category = str(row[3] or "").strip()
        issues: list[dict] = []

        for review in (
            review_a2_reiyu_text_surface(title=title, body=body, plan=ASSET_PLAN),
            review_a2_reiyu_batch_detection_fact(title=title, body=body, plan=ASSET_PLAN),
            review_a2_reiyu_old_can_eligibility(title=title, body=body, plan=ASSET_PLAN),
        ):
            payload = review.to_payload()
            if not payload["pass"]:
                for evidence in payload.get("hits") or [payload.get("reason") or ""]:
                    add(issues, str(payload.get("issue_code")), str(evidence), str(payload.get("severity")))

        custom_checks(title, body, issues)
        results.append(
            {
                "csv_row": csv_row,
                "title": title,
                "body": body,
                "category": category,
                "issues": issues,
            }
        )

    OUTPUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = Counter(issue["code"] for result in results for issue in result["issues"])
    print(json.dumps({"rows": len(results), "flagged_rows": sum(bool(r["issues"]) for r in results), "issue_counts": counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
