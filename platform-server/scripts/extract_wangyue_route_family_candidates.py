"""Extract Wangyue route-family candidates from real XHS/operator note exports.

This is a review utility: it does not write MAGA assets. The goal is to find
real note-level content entrances before curating prompt views, so row-level
business rules can stay short instead of accumulating one-off fixes.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.real_user_example_pool_service import (  # noqa: E402
    infer_real_user_risk_tags,
    infer_real_user_tags,
    _clean_text,
    _normalize_for_match,
    _short_hash,
)


DEFAULT_INPUTS = [
    "/Users/luxifa/Downloads/旺玥-真实ugc-案例.csv",
    "/Users/luxifa/rs-crawler-analysis/exports/xhs_crawl_export_20260619_150746/xhs_notes_full.csv",
    "/Users/luxifa/rs-crawler-analysis/exports/xhs_crawl_export_20260619_165055_wangyue_100_notes/xhs_notes_full.csv",
    "/Users/luxifa/rs-crawler-analysis/exports/xhs_crawl_export_20260619_165252_wangyue_100_notes/xhs_notes_full.csv",
]

ROW2_TERMS = (
    "精力",
    "精神",
    "活动",
    "消耗",
    "跑",
    "玩",
    "有劲",
    "累",
    "眼脑",
    "DHA",
    "保护力",
    "营养",
)
ROW1_TERMS = ("中招", "请假", "感冒", "不生病", "幼儿园", "上学", "接触", "保护力")
ROW3_TERMS = ("眼脑", "看书", "写字", "画画", "作业", "用脑", "DHA", "燕窝酸")
ROW4_TERMS = ("营养", "成长", "长个", "长肉", "饭量", "挑食", "个子", "身高")

HARD_BLOCK_TERMS = (
    "自己冲",
    "自己泡",
    "自己舀粉",
    "自己倒水",
    "抱着奶瓶",
    "塞书包",
    "路上喝",
    "随身携带",
    "感冒后",
    "赶紧补救",
    "治疗",
    "乳糖不耐受",
    "无乳糖",
    "月子",
    "新生儿",
    "怀孕",
    "亲喂",
    "母乳",
    "一段",
    "二段",
    "1段",
    "2段",
    "0-6个月",
    "快闪",
    "联名",
    "小黄人",
    "草坪",
    "活动区",
    "孩子王育儿顾问",
    "育儿顾问",
    "药剂师",
    "育儿师",
    "攻略",
    "一篇看懂",
    "闭眼入",
    "门店",
    "福利活动",
    "门店活动",
    "蹲活动",
    "搞活动",
    "送礼品",
    "扫码",
    "现货",
    "断货",
    "缺货",
    "召回",
    "有货",
    "没货",
    "跑遍",
    "托付",
    "香港",
    "转奶",
    "厌奶",
    "肚肚",
    "小肚肚",
    "肠道",
    "肠胃",
    "便便",
    "尿不湿",
    "毒奶粉",
    "滴滴我",
    "私信",
    "欢迎留言",
    "宝宝",
    "宝妈",
    "宝贝",
    "冲奶",
    "冲泡",
    "海底小纵队",
    "气球",
    "礼盒",
    "对讲机",
    "巴克队长",
    "保护力联萌",
    "官宣",
    "C位",
    "c位",
    "评论区",
    "点击视频",
    "泼天",
    "杜杜",
    "杏仁",
    "牙牙",
    "小动物",
    "课间",
    "数理化",
    "难题课",
    "晚自习",
    "上课能",
    "老师思路",
    "记知识点",
    "专注力提升",
    "减少67",
    "67%",
    "科学实证",
    "摄入35mg",
    "近视",
    "护眼",
    "视网膜",
    "反应都更灵敏",
    "爸妈代餐",
    "代餐",
)

SOURCE_BRAND_TERMS = (
    "a2",
    "A2",
    "至初",
    "臻智护",
    "合生元",
    "派星",
    "爱他美",
    "启赋",
    "飞鹤",
    "君乐宝",
    "美赞臣",
    "Enfamil",
    "雅培",
    "雅培360",
    "PediaSure",
    "Pediasure",
    "学优力",
    "小安素",
    "小佳膳",
    "安 mum",
    "安mum",
    "皇家三段",
    "皇家四段",
    "康膳佳",
)

PROMOTION_ACTIVITY_TERMS = (
    "蹲活动",
    "搞活动",
    "门店活动",
    "福利活动",
    "活动买",
    "活动价",
    "送礼品",
    "促销",
    "补货",
)

MATERNAL_RELEVANCE_TERMS = (
    "旺玥",
    "奶粉",
    "儿童奶粉",
    "成长奶粉",
    "孩子",
    "娃",
    "妈妈",
    "母婴",
    "幼儿园",
    "选奶",
    "保护力",
    "眼脑",
    "营养",
)

NON_MATERNAL_CONTEXT_TERMS = (
    "AI Agent",
    "A2A",
    "协议",
    "荷兰语",
    "口语",
    "考试",
    "签证",
    "公司",
    "论文",
    "安全测评",
    "路由",
    "蔬菜",
    "职业",
    "周边用品",
)

MARKETING_SOURCE_TERMS = (
    "天花板",
    "神器",
    "干货",
    "指南",
    "怎么选",
    "一篇看懂",
    "闭眼入",
    "小课堂",
    "大比较",
    "测评",
    "推荐✅",
    "黄金期",
    "营养拉满",
    "底气奶粉",
    "本命奶粉",
    "选它准没错",
    "刚需",
)

FAMILY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("school_collective", ("幼儿园", "上学", "放学", "请假", "老师", "同学", "集体", "兴趣班")),
    ("outdoor_play", ("户外", "公园", "露营", "玩水", "疯跑", "跑跳", "满头汗", "草地", "摸爬滚打")),
    ("home_activity", ("客厅", "沙发", "积木", "拆快递", "在家", "闹腾", "停不下来")),
    ("learning_brain", ("看书", "写字", "画画", "作业", "用脑", "数字", "网课", "拼图")),
    ("price_bill", ("贵", "账单", "肉疼", "钱包", "开销", "价格")),
    ("plain_selection", ("选奶", "奶粉", "儿童奶粉", "成分", "配方", "看了", "对比")),
    ("nutrition_growth", ("营养", "成长", "长个", "长肉", "身高", "个子", "饭量")),
    ("protection_state", ("保护力", "中招", "感冒", "不生病", "抵抗力", "身体", "身板")),
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract route-family candidates for Wangyue review.")
    parser.add_argument("inputs", nargs="*", default=[], help="CSV files. Defaults to known Wangyue/XHS exports.")
    parser.add_argument("--output", required=True, help="Output CSV path.")
    parser.add_argument("--json-summary", help="Optional JSON summary path.")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--include-blocked", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    paths = [Path(item).expanduser() for item in (args.inputs or DEFAULT_INPUTS)]
    rows, summary = extract_candidates(paths, limit=args.limit, include_blocked=args.include_blocked)
    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "suggested_rule",
                "route_family",
                "candidate_source_quality",
                "candidate_text",
                "prompt_view_suggestion",
                "source_title",
                "source_path",
                "source_row_no",
                "source_keyword",
                "tags",
                "risk_tags",
                "block_reason",
                "quality_score",
                "dedupe_hash",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    if args.json_summary:
        summary_path = Path(args.json_summary).expanduser()
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**summary, "output": str(output_path)}, ensure_ascii=False, indent=2))


def extract_candidates(paths: list[Path], *, limit: int, include_blocked: bool) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    stats: Counter[str] = Counter()
    block_reasons: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    rule_counts: Counter[str] = Counter()
    for path in paths:
        if not path.exists():
            stats["missing_input"] += 1
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            for row_no, row in enumerate(csv.DictReader(f), 1):
                stats["read_rows"] += 1
                title, content, source_keyword = _normalize_row(row)
                if not _row_is_maternal_relevant(title, content, source_keyword):
                    stats["irrelevant_row"] += 1
                    continue
                for text in _candidate_fragments(content):
                    stats["fragment_seen"] += 1
                    normalized = _normalize_for_match(text)
                    if normalized in seen:
                        stats["duplicate"] += 1
                        continue
                    seen.add(normalized)
                    suggested_rule = _suggest_rule(text)
                    if not suggested_rule:
                        stats["no_rule_hit"] += 1
                        continue
                    block_reason = _block_reason(text, title=title, source_keyword=source_keyword)
                    if block_reason:
                        block_reasons[block_reason] += 1
                        if not include_blocked:
                            continue
                    route_family = _route_family(text)
                    prompt_view = _prompt_view_suggestion(text)
                    candidate_source_quality = _candidate_source_quality(
                        title=title,
                        text=text,
                        source_keyword=source_keyword,
                        source_path=path,
                    )
                    tags = infer_real_user_tags(f"{title} {text} {source_keyword}")
                    risk_tags = infer_real_user_risk_tags(f"{title} {text} {source_keyword}", source_type="note")
                    score = _quality_score(
                        text,
                        suggested_rule=suggested_rule,
                        route_family=route_family,
                        block_reason=block_reason,
                        risk_tags=risk_tags,
                    )
                    rows.append(
                        {
                            "suggested_rule": suggested_rule,
                            "route_family": route_family,
                            "candidate_source_quality": candidate_source_quality,
                            "candidate_text": text,
                            "prompt_view_suggestion": prompt_view,
                            "source_title": title,
                            "source_path": str(path),
                            "source_row_no": row_no,
                            "source_keyword": source_keyword,
                            "tags": "；".join(tags),
                            "risk_tags": "；".join(risk_tags),
                            "block_reason": block_reason,
                            "quality_score": f"{score:.1f}",
                            "dedupe_hash": _short_hash("wangyue_route_candidate", text),
                        }
                    )
                    family_counts[route_family] += 1
                    rule_counts[suggested_rule] += 1
                    if len(rows) >= limit:
                        return _rank_rows(rows), _summary(stats, block_reasons, family_counts, rule_counts, rows)
    return _rank_rows(rows), _summary(stats, block_reasons, family_counts, rule_counts, rows)


def _normalize_row(row: dict[str, Any]) -> tuple[str, str, str]:
    title = _clean_text(row.get("title") or row.get("标题"), limit=120)
    content = _clean_text(row.get("content") or row.get("正文"), limit=1800)
    source_keyword = _clean_text(row.get("source_keyword") or row.get("高频讨论") or row.get("search_keywords"), limit=120)
    return title, content, source_keyword


def _candidate_fragments(content: str) -> list[str]:
    fragments: list[str] = []
    sentences = [
        item.strip(" \t，,。！？!?；;、")
        for item in re.split(r"[\n\r]+|(?<=[。！？!?；;])", content)
        if item.strip(" \t，,。！？!?；;、")
    ]
    for sentence in sentences:
        clauses = [
            item.strip(" \t，,。！？!?；;、")
            for item in re.split(r"[，,；;]", sentence)
            if item.strip(" \t，,。！？!?；;、")
        ]
        for fragment in [sentence, *clauses]:
            compact_len = len(re.sub(r"\s+", "", fragment))
            if _looks_like_topic_tag(fragment):
                continue
            if 10 <= compact_len <= 120:
                fragments.append(fragment)
    return list(dict.fromkeys(fragments))


def _suggest_rule(text: str) -> str:
    normalized = _normalize_for_match(text)
    if any(_normalize_for_match(term) in normalized for term in PROMOTION_ACTIVITY_TERMS):
        return ""
    hits = []
    for rule, terms in (
        ("row1_easy_sick", ROW1_TERMS),
        ("row2_energy_state", ROW2_TERMS),
        ("row3_eye_brain", ROW3_TERMS),
        ("row4_nutrition_growth", ROW4_TERMS),
    ):
        count = sum(1 for term in terms if _normalize_for_match(term) in normalized)
        if rule == "row2_energy_state":
            has_child_activity = any(
                _normalize_for_match(term) in normalized
                for term in (
                    "精力",
                    "精神",
                    "消耗",
                    "有劲",
                    "疯跑",
                    "跑跳",
                    "满头汗",
                    "累",
                    "用脑",
                    "眼脑",
                    "DHA",
                )
            )
            if "活动" in normalized and not has_child_activity:
                count = 0
        if count:
            hits.append((count, rule))
    if not hits:
        return ""
    hits.sort(reverse=True)
    return hits[0][1]


def _route_family(text: str) -> str:
    normalized = _normalize_for_match(text)
    for family, terms in FAMILY_RULES:
        if any(_normalize_for_match(term) in normalized for term in terms):
            return family
    return "plain_record"


def _block_reason(text: str, *, title: str, source_keyword: str) -> str:
    normalized_text = _normalize_for_match(text)
    normalized_context = _normalize_for_match(f"{title} {text} {source_keyword}")
    for term in HARD_BLOCK_TERMS:
        if _normalize_for_match(term) in normalized_context:
            return f"hard:{term}"
    if _looks_like_topic_tag(text):
        return "topic_tag"
    if not _row_is_maternal_relevant(title, text, source_keyword):
        return "irrelevant_context"
    if re.search(r"滴滴|私信|欢迎.*(?:咨询|了解|留言)|门店|福利", text):
        return "sales_or_comment_call"
    for term in SOURCE_BRAND_TERMS:
        if _normalize_for_match(term) in normalized_text:
            return f"brand_in_text:{term}"
    for term in MARKETING_SOURCE_TERMS:
        if _normalize_for_match(term) in normalized_context:
            return f"marketing_source:{term}"
    if re.search(r"[0-9一二三四五六七八九十]+个?月|[0-9一二三四五六七八九十]+岁|[1234]段|[一二三四]段", text):
        return "age_or_stage"
    if sum(1 for mark in ("✅", "☑", "✔", "1️⃣", "2️⃣", "3️⃣", "👉") if mark in text) >= 1:
        return "list_or_marketing_format"
    if re.search(r"[🌟✨💡🔥💪👀🧠🤧👍🐱]", text):
        return "emoji_marketing_format"
    return ""


def _looks_like_topic_tag(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return True
    if compact.startswith("#"):
        return True
    return compact.count("#") >= 2 and len(compact) <= 80


def _row_is_maternal_relevant(title: str, content: str, source_keyword: str) -> bool:
    context = _normalize_for_match(f"{title} {content} {source_keyword}")
    if any(_normalize_for_match(term) in context for term in NON_MATERNAL_CONTEXT_TERMS):
        return False
    return any(_normalize_for_match(term) in context for term in MATERNAL_RELEVANCE_TERMS)


def _prompt_view_suggestion(text: str) -> str:
    cleaned = re.sub(r"#.+?(?:\s|$)", "", text).strip(" \t，,。！？!?；;、")
    cleaned = cleaned.replace("抵抗力", "保护力")
    cleaned = re.sub(r"[🌟✨💡🔥💪👀🧠🤧👍🐱✅☑✔]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    clauses = [
        item.strip(" \t，,。！？!?；;、")
        for item in re.split(r"[，,；;]", cleaned)
        if item.strip(" \t，,。！？!?；;、")
    ]
    for clause in clauses:
        if 8 <= len(clause) <= 52 and not _block_reason(clause, title="", source_keyword=""):
            return clause
    return cleaned[:80]


def _candidate_source_quality(*, title: str, text: str, source_keyword: str, source_path: Path) -> str:
    context = _normalize_for_match(f"{title} {text} {source_keyword}")
    if "旺玥-真实ugc-案例" in str(source_path):
        return "operator_real_ugc"
    if any(_normalize_for_match(term) in context for term in MARKETING_SOURCE_TERMS):
        return "marketing_like"
    if any(_normalize_for_match(term) in context for term in SOURCE_BRAND_TERMS):
        return "competitor_mixed"
    if "旺玥" in context:
        return "wangyue_note"
    return "maternal_note"


def _quality_score(
    text: str,
    *,
    suggested_rule: str,
    route_family: str,
    block_reason: str,
    risk_tags: list[str],
) -> float:
    normalized = _normalize_for_match(text)
    score = 30.0
    score += len(infer_real_user_tags(text)) * 3
    if suggested_rule == "row2_energy_state":
        score += 8
    if route_family in {"home_activity", "price_bill", "learning_brain", "plain_record"}:
        score += 6
    if route_family in {"school_collective", "outdoor_play"}:
        score -= 3
    if any(term in normalized for term in ("今天", "那天", "早上", "晚上", "周末", "回家", "朋友", "队友", "账单")):
        score += 5
    if any(term in normalized for term in ("营养得跟上", "活动量大", "省心", "踏实", "安心")):
        score -= 6
    if block_reason:
        score -= 20
    score -= len(set(risk_tags) & {"广告口吻", "竞品品牌"}) * 5
    return score


def _rank_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda item: (
            bool(item["block_reason"]),
            item["suggested_rule"] != "row2_energy_state",
            -float(item["quality_score"]),
            item["route_family"],
            item["dedupe_hash"],
        ),
    )


def _summary(
    stats: Counter[str],
    block_reasons: Counter[str],
    family_counts: Counter[str],
    rule_counts: Counter[str],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    accepted = [row for row in rows if not row["block_reason"]]
    ranked_accepted = _rank_rows(accepted)
    return {
        "stats": dict(stats),
        "candidate_count": len(rows),
        "accepted_count": len(accepted),
        "blocked_count": len(rows) - len(accepted),
        "rule_counts": dict(rule_counts.most_common()),
        "route_family_counts": dict(family_counts.most_common()),
        "block_reason_top": dict(block_reasons.most_common(20)),
        "top_row2_samples": [
            {
                "family": row["route_family"],
                "text": row["candidate_text"],
                "prompt_view": row["prompt_view_suggestion"],
                "source": row["source_title"],
                "score": row["quality_score"],
            }
            for row in ranked_accepted
            if row["suggested_rule"] == "row2_energy_state"
        ][:30],
    }


if __name__ == "__main__":
    main()
