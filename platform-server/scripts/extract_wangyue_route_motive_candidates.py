"""Extract route-motive candidates from real XHS/operator note exports.

This review utility looks for note-level posting motives and life entrances,
not isolated mouth phrases. It does not write MAGA assets.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.real_user_example_pool_service import (  # noqa: E402
    PROMPT_VIEW_BLOCK_TERMS,
    TITLE_SHAPE_SOURCE_BLOCK_TERMS,
    _clean_text,
    _normalize_for_match,
    _short_hash,
    infer_real_user_risk_tags,
    infer_real_user_tags,
)


DEFAULT_INPUTS = [
    "/Users/luxifa/Downloads/旺玥-真实ugc-案例.csv",
    "/Users/luxifa/rs-crawler-analysis/exports/xhs_crawl_export_20260619_150746/xhs_notes_full.csv",
    "/Users/luxifa/rs-crawler-analysis/exports/xhs_crawl_export_20260619_165055_wangyue_100_notes/xhs_notes_full.csv",
    "/Users/luxifa/rs-crawler-analysis/exports/xhs_crawl_export_20260619_165252_wangyue_100_notes/xhs_notes_full.csv",
]

RULE_PROFILES: dict[str, dict[str, tuple[str, ...]]] = {
    "row1_easy_sick": {
        "terms": ("中招", "请假", "感冒", "生病", "保护力", "幼儿园", "上学", "接触", "集体"),
        "families": ("school_collective", "protection_state", "outdoor_activity", "plain_record"),
    },
    "row2_energy_state": {
        "terms": ("精力", "精神", "有劲", "累", "活动量", "消耗", "保护力", "眼脑", "DHA", "户外", "跑跳"),
        "families": ("outdoor_activity", "home_activity", "learning_brain", "protection_state", "plain_record"),
    },
    "row3_eye_brain": {
        "terms": ("眼脑", "DHA", "燕窝酸", "看书", "画画", "写字", "用脑", "功课", "成分"),
        "families": ("learning_brain", "plain_selection", "plain_record"),
    },
    "row4_nutrition_growth": {
        "terms": ("营养", "成长", "挑食", "饭量", "胃口", "长肉", "长个", "成分", "选奶"),
        "families": ("nutrition_growth", "plain_selection", "price_bill", "plain_record"),
    },
}

FAMILY_TERMS: dict[str, tuple[str, ...]] = {
    "school_collective": ("幼儿园", "上学", "放学", "老师", "同学", "集体", "兴趣班", "请假"),
    "outdoor_activity": ("户外", "活动量", "疯跑", "跑跳", "玩嗨", "满头汗", "运动", "公园", "露营"),
    "home_activity": ("客厅", "餐桌", "沙发", "积木", "在家", "早上", "晚上", "回家"),
    "learning_brain": ("看书", "画画", "写字", "作业", "用脑", "功课", "眼脑", "DHA", "燕窝酸"),
    "plain_selection": ("选奶", "儿童奶粉", "成长奶粉", "成分", "配方", "做功课", "对比", "看了"),
    "nutrition_growth": ("营养", "成长", "挑食", "饭量", "胃口", "长肉", "长个", "补充"),
    "price_bill": ("贵", "肉疼", "账单", "开销", "价格", "不便宜"),
    "protection_state": ("保护力", "中招", "感冒", "不生病", "少请假", "体质", "状态"),
}

HARD_BLOCK_TERMS = (
    "自己冲",
    "自己泡",
    "自己舀",
    "自己倒水",
    "抱着奶瓶",
    "塞书包",
    "路上喝",
    "随身携带",
    "感冒后",
    "赶紧补救",
    "月子",
    "新生儿",
    "一段",
    "二段",
    "1段",
    "2段",
    "母乳",
    "亲喂",
    "转奶",
    "厌奶",
    "断奶",
    "奶瓶",
    "肚肚",
    "肠胃",
    "脾胃",
    "便便",
    "尿不湿",
    "快闪",
    "联名",
    "礼盒",
    "对讲机",
    "巴克队长",
    "海底小纵队",
    "舰艇",
    "盲盒",
    "橡皮",
    "卷笔刀",
    "保护力联萌",
    "官宣",
    "点击视频",
    "孩子王",
    "育儿顾问",
    "母婴店",
    "门店",
    "蹲活动",
    "搞活动",
    "福利活动",
    "扫码",
    "私信",
    "欢迎留言",
    "断货",
    "缺货",
    "召回",
    "现货",
    "有货",
    "清关",
    "香港",
    "小黄人",
    "杜杜",
    "杏仁",
    "牙牙",
    "晚自习",
    "数理化",
    "难题课",
    "上课能",
    "记知识点",
    "集中精神",
    "专注力提升",
    "父亲节",
    "母亲节",
    "爸爸生日",
    "手机支架",
    "气囊支架",
    "恒温壶",
    "CR报告",
    "cr报告",
    "客服",
    "消毒柜",
    "烘干",
    "紫外线",
    "礼品",
    "冲调",
    "先水后奶",
    "平勺",
    "清洁双手",
    "滚烫",
    "某东",
    "某宝",
    "打开湿湿",
    "湿湿",
    "蛋白粉",
    "高中生",
    "课间",
    "学业繁重",
    "用量",
    "一周喝",
    "结块",
    "认养一头牛",
    "上火",
    "眼屎",
    "有机钙",
    "叶黄素",
    "奶茶",
    "防线",
    "健康小卫士",
    "专门为解决",
    "很多家长",
    "家长们",
    "各位家长",
    "圈粉",
    "直接被",
    "值得试一试",
    "多一份保障",
    "如果你也想",
    "告别",
    "小变化",
    "身体不适",
    "忧心忡忡",
    "脆皮",
    "能量补给站",
    "满满的能量",
    "关键营养",
    "高钙高锌",
    "高钙高铁",
    "妥妥滴",
    "粉质细腻",
    "好冲泡",
    "温水即可冲泡",
    "摇晃几秒",
    "咔哒锁鲜",
    "自然奶香",
    "锁鲜营养",
    "奶罐杯",
    "鲜奶",
    "医药级灌装",
    "刷了几天小红书",
    "跪谢",
    "麻烦推荐",
    "真心推荐",
    "不要广",
    "有没有什么比较好的奶粉推荐",
    "换季",
    "天一冷",
    "冬天",
    "秋冬",
    "夏日",
    "夏天",
    "六一",
    "儿童节",
    "萌宝",
    "新手爸妈",
    "扫盲",
    "踩雷",
    "不花冤枉钱",
    "琳琅满目",
    "认定这款",
    "儿童免疫奶",
    "卓傲",
    "QQ星",
    "纳诺可儿",
    "小最奶粉",
    "小最",
    "粉肌",
    "色板",
    "室内暖光",
    "砂糖",
    "小鹿",
    "彩虹",
    "山巅",
    "妈妈说",
    "大自然",
    "阳光是最好的营养",
    "小麦色",
    "青草的清香",
    "阳光明媚",
    "微风拂面",
    "鲜花飘香",
    "风吹拂脸庞",
    "OPL",
    "OPO",
    "一罐顶两罐",
    "参考来源",
    "参考文献",
    "研究表明",
    "FAO",
    "MFGM",
    "BB536",
    "135亿",
    "硕士妈妈",
    "实测",
    "放养育儿",
    "松弛高端",
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
    "不踩坑",
    "踩雷",
    "顶级",
)

COMPETITOR_TERMS = (
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
    "PediaSure",
    "Pediasure",
    "学优力",
    "小安素",
    "小佳膳",
    "安 mum",
    "安mum",
    "卓傲",
    "QQ星",
    "纳诺可儿",
    "海普诺凯",
)

MATERNAL_TERMS = (
    "旺玥",
    "皇家美素佳儿",
    "奶粉",
    "儿童奶粉",
    "成长奶粉",
    "孩子",
    "娃",
    "妈妈",
    "老母亲",
    "幼儿园",
    "选奶",
    "营养",
    "保护力",
    "眼脑",
)

PROMPT_REPLACEMENTS = (
    ("宝宝", "孩子"),
    ("宝妈", "妈妈"),
    ("宝贝", "孩子"),
    ("抵抗力", "保护力"),
    ("旺钥", "旺玥"),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract Wangyue route motive candidates for review.")
    parser.add_argument("inputs", nargs="*", default=[], help="CSV files. Defaults to known XHS/operator exports.")
    parser.add_argument("--no-default-inputs", action="store_true", help="Only read explicit inputs and/or asset keys.")
    parser.add_argument("--asset-key", action="append", default=[], help="Read active real_user_example_pool asset items.")
    parser.add_argument("--output", required=True, help="Output CSV path.")
    parser.add_argument("--json-summary", help="Optional summary JSON path.")
    parser.add_argument("--per-rule-limit", type=int, default=40)
    parser.add_argument("--include-rejected", action="store_true")
    parser.add_argument("--mysql-host", default=os.environ.get("MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--mysql-port", type=int, default=int(os.environ.get("MYSQL_PORT", "3306")))
    parser.add_argument("--mysql-user", default=os.environ.get("MYSQL_USER", "maga"))
    parser.add_argument("--mysql-password", default=os.environ.get("MYSQL_PASSWORD", "maga123456"))
    parser.add_argument("--mysql-database", default=os.environ.get("MYSQL_DATABASE", "maga"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    input_values = args.inputs if (args.inputs or args.no_default_inputs) else DEFAULT_INPUTS
    paths = [Path(item).expanduser() for item in input_values]
    asset_items = _read_asset_items(
        asset_keys=args.asset_key,
        host=args.mysql_host,
        port=args.mysql_port,
        user=args.mysql_user,
        password=args.mysql_password,
        database=args.mysql_database,
    )
    rows, summary = extract_candidates(
        paths,
        asset_items=asset_items,
        per_rule_limit=args.per_rule_limit,
        include_rejected=args.include_rejected,
    )
    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "suggested_rule",
                "route_family",
                "review_decision",
                "candidate_source_quality",
                "prompt_view_suggestion",
                "candidate_text",
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


def extract_candidates(
    paths: list[Path],
    *,
    asset_items: list[dict[str, Any]] | None = None,
    per_rule_limit: int,
    include_rejected: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    stats: Counter[str] = Counter()
    block_reasons: Counter[str] = Counter()
    for path in paths:
        if not path.exists():
            stats["missing_input"] += 1
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            for row_no, row in enumerate(csv.DictReader(f), 1):
                stats["read_rows"] += 1
                title, content, source_keyword = _normalize_row(row)
                if not _maternal_relevant(title, content, source_keyword):
                    stats["irrelevant_row"] += 1
                    continue
                for text in _route_windows(content):
                    stats["window_seen"] += 1
                    normalized = _normalize_for_match(text)
                    if normalized in seen:
                        stats["duplicate"] += 1
                        continue
                    seen.add(normalized)
                    suggested_rule = _suggest_rule(text, title=title, source_keyword=source_keyword)
                    if not suggested_rule:
                        stats["no_rule_hit"] += 1
                        continue
                    route_family = _route_family(text)
                    block_reason = _block_reason(text, title=title, source_keyword=source_keyword)
                    if block_reason:
                        block_reasons[block_reason] += 1
                    candidate_source_quality = _candidate_source_quality(
                        title=title,
                        text=text,
                        source_keyword=source_keyword,
                        source_path=path,
                    )
                    decision = _review_decision(
                        text,
                        prompt_view=_prompt_view(text),
                        block_reason=block_reason,
                        source_quality=candidate_source_quality,
                    )
                    if decision == "reject_for_prompt" and not include_rejected:
                        continue
                    tags = infer_real_user_tags(f"{title} {text} {source_keyword}")
                    risk_tags = infer_real_user_risk_tags(f"{title} {text} {source_keyword}", source_type="note")
                    rows.append(
                        {
                            "suggested_rule": suggested_rule,
                            "route_family": route_family,
                            "review_decision": decision,
                            "candidate_source_quality": candidate_source_quality,
                            "prompt_view_suggestion": _prompt_view(text),
                            "candidate_text": text,
                            "source_title": title,
                            "source_path": str(path),
                            "source_row_no": row_no,
                            "source_keyword": source_keyword,
                            "tags": "；".join(tags),
                            "risk_tags": "；".join(risk_tags),
                            "block_reason": block_reason,
                            "quality_score": f"{_quality_score(text, suggested_rule=suggested_rule, route_family=route_family, source_quality=candidate_source_quality, block_reason=block_reason):.1f}",
                            "dedupe_hash": _short_hash("wangyue_route_motive_candidate", text),
                        }
                    )
    for source_row_no, item in enumerate(asset_items or [], 1):
        stats["asset_items_read"] += 1
        if str(item.get("source_type") or "") != "note":
            stats["asset_non_note_skipped"] += 1
            continue
        title = _clean_text(item.get("title"), limit=160)
        content = _clean_text(item.get("text"), limit=2600)
        source_keyword = _clean_text(item.get("source_keyword"), limit=120)
        if _looks_synthetic_source(item):
            stats["synthetic_asset_item_skipped"] += 1
            continue
        source_path = str(item.get("_asset_key") or "asset")
        if not _maternal_relevant(title, content, source_keyword):
            stats["irrelevant_asset_item"] += 1
            continue
        for text in _route_windows(content):
            stats["asset_window_seen"] += 1
            normalized = _normalize_for_match(text)
            if normalized in seen:
                stats["duplicate"] += 1
                continue
            seen.add(normalized)
            suggested_rule = _suggest_rule(text, title=title, source_keyword=source_keyword)
            if not suggested_rule:
                stats["no_rule_hit"] += 1
                continue
            route_family = _route_family(text)
            block_reason = _block_reason(text, title=title, source_keyword=source_keyword)
            if block_reason:
                block_reasons[block_reason] += 1
            candidate_source_quality = _candidate_source_quality(
                title=title,
                text=text,
                source_keyword=source_keyword,
                source_path=Path(source_path),
            )
            prompt_view = _prompt_view(text)
            decision = _review_decision(
                text,
                prompt_view=prompt_view,
                block_reason=block_reason,
                source_quality=candidate_source_quality,
            )
            if decision == "reject_for_prompt" and not include_rejected:
                continue
            tags = infer_real_user_tags(f"{title} {text} {source_keyword}")
            risk_tags = infer_real_user_risk_tags(f"{title} {text} {source_keyword}", source_type="note")
            rows.append(
                {
                    "suggested_rule": suggested_rule,
                    "route_family": route_family,
                    "review_decision": decision,
                    "candidate_source_quality": candidate_source_quality,
                    "prompt_view_suggestion": prompt_view,
                    "candidate_text": text,
                    "source_title": title,
                    "source_path": source_path,
                    "source_row_no": source_row_no,
                    "source_keyword": source_keyword,
                    "tags": "；".join(tags),
                    "risk_tags": "；".join(risk_tags),
                    "block_reason": block_reason,
                    "quality_score": f"{_quality_score(text, suggested_rule=suggested_rule, route_family=route_family, source_quality=candidate_source_quality, block_reason=block_reason):.1f}",
                    "dedupe_hash": _short_hash("wangyue_route_motive_candidate", text),
                }
            )
    ranked = _limit_by_rule(_rank(rows), per_rule_limit)
    return ranked, _summary(stats, block_reasons, ranked)


def _read_asset_items(
    *,
    asset_keys: list[str],
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
) -> list[dict[str, Any]]:
    if not asset_keys:
        return []
    try:
        import pymysql
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("pymysql is required to read asset_registry items") from exc
    connection = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        result: list[dict[str, Any]] = []
        with connection.cursor() as cursor:
            for asset_key in asset_keys:
                cursor.execute(
                    """
                    select id, asset_key, version_no, content_json
                    from asset_registry
                    where asset_type='real_user_example_pool'
                      and asset_key=%s
                      and status='active'
                    limit 1
                    """,
                    (asset_key,),
                )
                row = cursor.fetchone()
                if not row:
                    continue
                content_json = row.get("content_json")
                content = json.loads(content_json) if isinstance(content_json, str) else content_json
                for item in list((content or {}).get("items") or []):
                    if not isinstance(item, dict):
                        continue
                    item = dict(item)
                    item["_asset_key"] = row["asset_key"]
                    item["_asset_id"] = row["id"]
                    item["_asset_version"] = row["version_no"]
                    result.append(item)
        return result
    finally:
        connection.close()


def _normalize_row(row: dict[str, Any]) -> tuple[str, str, str]:
    title = _clean_text(row.get("title") or row.get("标题"), limit=160)
    content = _clean_text(row.get("content") or row.get("正文"), limit=2600)
    source_keyword = _clean_text(row.get("source_keyword") or row.get("高频讨论") or row.get("search_keywords"), limit=120)
    return title, content, source_keyword


def _looks_synthetic_source(item: dict[str, Any]) -> bool:
    context = _normalize_for_match(
        " ".join(
            str(item.get(key) or "")
            for key in ("source_keyword", "source_name", "layer_reason", "note_id", "comment_id")
        )
    )
    return any(term in context for term in ("codex", "row1", "row2", "row3", "row4", "realness", "routeexpansion"))


def _route_windows(content: str) -> list[str]:
    cleaned = re.sub(r"#.+?(?:\s|$)", " ", content)
    sentences = [
        item.strip(" \t，,。！？!?；;、")
        for item in re.split(r"[\n\r]+|(?<=[。！？!?；;])", cleaned)
        if item.strip(" \t，,。！？!?；;、")
    ]
    windows: list[str] = []
    for index, sentence in enumerate(sentences):
        compact_len = len(re.sub(r"\s+", "", sentence))
        if 24 <= compact_len <= 180:
            windows.append(sentence)
        if index + 1 < len(sentences):
            pair = f"{sentence} {sentences[index + 1]}".strip()
            pair_len = len(re.sub(r"\s+", "", pair))
            if 50 <= pair_len <= 220:
                windows.append(pair)
    return list(dict.fromkeys(windows))


def _suggest_rule(text: str, *, title: str, source_keyword: str) -> str:
    context = _normalize_for_match(f"{title} {text} {source_keyword}")
    scores: list[tuple[int, str]] = []
    for rule, profile in RULE_PROFILES.items():
        score = sum(1 for term in profile["terms"] if _normalize_for_match(term) in context)
        if rule == "row2_energy_state" and "活动" in context:
            score += 1
        if score:
            scores.append((score, rule))
    if not scores:
        return ""
    scores.sort(reverse=True)
    return scores[0][1]


def _route_family(text: str) -> str:
    normalized = _normalize_for_match(text)
    scored: list[tuple[int, str]] = []
    for family, terms in FAMILY_TERMS.items():
        score = sum(1 for term in terms if _normalize_for_match(term) in normalized)
        if score:
            scored.append((score, family))
    if not scored:
        return "plain_record"
    scored.sort(reverse=True)
    return scored[0][1]


def _block_reason(text: str, *, title: str, source_keyword: str) -> str:
    context = _normalize_for_match(f"{title} {text} {source_keyword}")
    prompt_view = _prompt_view(text)
    normalized_prompt = _normalize_for_match(prompt_view)
    for term in HARD_BLOCK_TERMS:
        if _normalize_for_match(term) in context:
            return f"hard:{term}"
    for term in (*PROMPT_VIEW_BLOCK_TERMS, *TITLE_SHAPE_SOURCE_BLOCK_TERMS):
        normalized_term = _normalize_for_match(term)
        if normalized_term and normalized_term in normalized_prompt:
            return f"prompt_block:{term}"
    for term in MARKETING_SOURCE_TERMS:
        if _normalize_for_match(term) in context:
            return f"marketing_source:{term}"
    if re.search(r"[🌟✨💡🔥💪👀🧠🤧👍🐱✅☑✔😟🤔🤯🛡💖✌🥳😂😷😮😄😍❤️🌻🌳🌿🌸📺🥛🎉🍼]", context):
        return "emoji_marketing_format"
    if re.search(r"(体重|身高|爬行|翻身|辅食|[0-9]+(?:\.[0-9]+)?\s*(?:斤|cm|厘米))", context):
        return "low_age_physical_metrics"
    if re.search(r"[0-9一二三四五六七八九十]+个?月|[0-9一二三四五六七八九十]+岁|[1234]段|[一二三四]段", context):
        return "age_or_stage"
    return ""


def _candidate_source_quality(*, title: str, text: str, source_keyword: str, source_path: Path) -> str:
    context = _normalize_for_match(f"{title} {text} {source_keyword}")
    if "旺玥-真实ugc-案例" in str(source_path):
        return "operator_real_ugc"
    if any(_normalize_for_match(term) in context for term in COMPETITOR_TERMS):
        return "competitor_mixed"
    if any(_normalize_for_match(term) in context for term in MARKETING_SOURCE_TERMS):
        return "marketing_like"
    if "旺玥" in context or "皇家美素佳儿" in context:
        return "wangyue_note"
    return "maternal_note"


def _review_decision(text: str, *, prompt_view: str, block_reason: str, source_quality: str) -> str:
    if block_reason:
        return "reject_for_prompt"
    if source_quality == "marketing_like":
        return "reject_for_prompt"
    normalized = _normalize_for_match(prompt_view)
    if any(term in normalized for term in ("家长", "推荐", "问", "有没有", "广告", "客服", "用量", "攻略")):
        return "reject_for_prompt"
    if len(prompt_view) < 36:
        return "texture_only"
    if source_quality == "competitor_mixed":
        return "needs_manual_rewrite"
    if any(term in normalized for term in ("含有", "搭配", "成分", "配方", "mg", "hmo", "dha")):
        return "texture_only"
    if any(term in normalized for term in ("我想", "感觉", "希望", "看着", "不敢说", "没想到", "谁懂")):
        return "texture_only"
    return "can_add_route"


def _prompt_view(text: str) -> str:
    cleaned = re.sub(r"#.+?(?:\s|$)", "", text)
    cleaned = re.sub(r"[🌟✨💡🔥💪👀🧠🤧👍🐱✅☑✔😟🤔🤯🛡💖✌🥳😂😷😮😄😍❤️🌻🌳🌿🌸📺🥛🎉🍼]", "", cleaned)
    for old, new in PROMPT_REPLACEMENTS:
        cleaned = cleaned.replace(old, new)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t，,。！？!?；;、")
    return cleaned[:180]


def _quality_score(text: str, *, suggested_rule: str, route_family: str, source_quality: str, block_reason: str) -> float:
    normalized = _normalize_for_match(text)
    score = 30.0
    score += len(infer_real_user_tags(text)) * 2
    if source_quality == "operator_real_ugc":
        score += 8
    elif source_quality == "wangyue_note":
        score += 5
    elif source_quality in {"competitor_mixed", "marketing_like"}:
        score -= 15
    if route_family in {"home_activity", "learning_brain", "price_bill", "plain_selection"}:
        score += 5
    if route_family in {"school_collective", "outdoor_activity"}:
        score -= 2
    if suggested_rule in {"row1_easy_sick", "row2_energy_state", "row3_eye_brain"}:
        score += 4
    if any(term in normalized for term in ("接娃", "放学", "最近", "这阵", "省心", "踏实")):
        score -= 5
    if block_reason:
        score -= 30
    return score


def _maternal_relevant(title: str, content: str, source_keyword: str) -> bool:
    context = _normalize_for_match(f"{title} {content} {source_keyword}")
    return any(_normalize_for_match(term) in context for term in MATERNAL_TERMS)


def _rank(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decision_rank = {"can_add_route": 0, "needs_manual_rewrite": 1, "texture_only": 2, "reject_for_prompt": 3}
    return sorted(
        rows,
        key=lambda row: (
            row["suggested_rule"],
            decision_rank.get(row["review_decision"], 9),
            -float(row["quality_score"]),
            row["route_family"],
            row["dedupe_hash"],
        ),
    )


def _limit_by_rule(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    result: list[dict[str, Any]] = []
    for row in rows:
        rule = row["suggested_rule"]
        if counts[rule] >= limit:
            continue
        counts[rule] += 1
        result.append(row)
    return result


def _summary(stats: Counter[str], block_reasons: Counter[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "stats": dict(stats),
        "output_count": len(rows),
        "rule_counts": dict(Counter(row["suggested_rule"] for row in rows).most_common()),
        "decision_counts": dict(Counter(row["review_decision"] for row in rows).most_common()),
        "rule_decision_counts": {
            f"{rule}:{decision}": count
            for (rule, decision), count in Counter((row["suggested_rule"], row["review_decision"]) for row in rows).most_common()
        },
        "route_family_counts": dict(Counter(row["route_family"] for row in rows).most_common()),
        "source_quality_counts": dict(Counter(row["candidate_source_quality"] for row in rows).most_common()),
        "block_reason_top": dict(block_reasons.most_common(20)),
    }


if __name__ == "__main__":
    main()
