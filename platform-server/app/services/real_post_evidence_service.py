"""Turn real XHS posts into reviewable evidence rows for MAGA.

The service outputs mechanisms and risk labels. It does not put raw posts into
generation prompts and does not write assets by itself.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from app.services.xhs_real_post_acquisition_service import XhsRealPostRecord


EMOJI_MAP = {
    "[笑哭R]": "😂",
    "[叹气R]": "😮‍💨",
    "[石化R]": "🫠",
    "[失望R]": "😞",
    "[强]": "👍",
}

WANGYUE_FORBIDDEN_TERMS = (
    "🍼",
    "厌奶",
    "体质",
    "肠胃",
    "脾胃",
    "天然",
    "儿保",
    "抵抗力",
    "宝宝",
    "宝妈",
    "自护力",
    "底气",
    "源乳",
    "初乳",
    "换季",
    "流感",
    "春游",
    "秋游",
)

PATTERNS = {
    "store_kol_ad": re.compile(
        r"从事母婴|母婴店|顾客|复购率|TOP|私藏|宝藏奶粉|实力派|看过来|闭眼|"
        r"锁死|拉满|必入|推荐|测评|攻略|清单|科普|干货|功课|对比N款|"
        r"官方|活动|性价比|天花板|不踩雷|整理了|选奶攻略|一张图|门店"
    ),
    "strong_claim": re.compile(
        r"增强免疫力|提高免疫力|免疫力|抵抗力|自护力|体质|少生病|不生病|"
        r"长高|长个|追高|身高|增高|体检|医生|护士|儿保|护视力|近视|"
        r"促进骨骼|生长因子|快速长高|长肉|体重|偏矮|矮娃"
    ),
    "digestive_medical": re.compile(r"肠胃|脾胃|不上火|便秘|腹泻|过敏|敏宝|吸收差|消化"),
    "explicit_low_age": re.compile(
        r"(^|[^0-9])([01]\s*岁|2\s*岁|一岁|两岁|二岁|半岁|月龄|新生儿|婴幼儿|婴儿)|"
        r"([123]\s*段奶粉|[一二三]段奶粉)"
    ),
    "wrong_context_transfer": re.compile(r"转奶|换奶|断奶|母乳|辅食"),
    "time_current_risk": re.compile(r"换季|流感|春游|秋游|开学季|最近天气|这阵子天气|现在.*(春天|夏天|秋天|冬天)"),
    "tutorial": re.compile(r"攻略|科普|怎么选|避坑|测评|对比|成分表|配料表|一张图|建议收藏|整理|懂行"),
    "bad_product_action": re.compile(r"书包侧袋|自己冲|自己泡|泡了一杯带去|翻配方表|包装信息|罐身信息|奶粉袋"),
    "wrong_product_form": re.compile(r"奶粉做的|做麻辣烫|拿奶粉(做|煮|拌)|奶粉.*(做菜|煮汤|麻辣烫)"),
    "price_negative": re.compile(r"太贵|不便宜|割韭菜|花冤枉钱|实惠|价格比|到手价|活动价|贵啊"),
    "rebuy_entry": re.compile(r"复购|回购|补货|囤|喝完|最后一袋|开新罐|空罐|空瓶|一整箱|又买|下单"),
    "compare_entry": re.compile(r"纠结|对比|比对|哪款|怎么选择|选了|选奶|看了一圈|翻了一天|头都看晕"),
    "child_acceptance": re.compile(r"爱喝|喜欢喝|主动喝|愿意喝|口感|奶味|接受"),
    "ask_conversation": re.compile(r"被问|问我|姐妹|大家|同款|懂行|不懂就问|有没有"),
    "life_texture": re.compile(r"大雨|商场|店里|排队|幼儿园|班级|老师|桌上|回家|出门|水壶|画|玩|跑|跳|饭"),
}

FIELDNAMES = [
    "source_row_no",
    "source_keyword",
    "note_id",
    "url",
    "category",
    "title",
    "original_snippet",
    "ending_snippet",
    "usable_layers",
    "risk_tags",
    "allow_asset",
    "suggested_wangyue_use",
    "likes",
    "comments_count",
    "publish_time",
    "dedupe_key",
]


@dataclass(frozen=True)
class RealPostEvidenceRow:
    source_row_no: int
    source_keyword: str
    note_id: str
    url: str
    category: str
    title: str
    original_snippet: str
    ending_snippet: str
    usable_layers: list[str]
    risk_tags: list[str]
    allow_asset: str
    suggested_wangyue_use: str
    likes: int | str
    comments_count: int | str
    publish_time: str
    dedupe_key: str

    def to_csv_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["usable_layers"] = ";".join(self.usable_layers)
        row["risk_tags"] = ";".join(self.risk_tags)
        return row


@dataclass(frozen=True)
class RealPostEvidenceResult:
    rows: list[RealPostEvidenceRow]
    stats: dict[str, Any]


class RealPostEvidenceService:
    def analyze(
        self,
        records: Iterable[XhsRealPostRecord | dict[str, Any]],
        *,
        profile: str = "wangyue_child_milk",
    ) -> RealPostEvidenceResult:
        normalized = [normalize_record(record) for record in records]
        deduped = dedupe_records(normalized)
        rows: list[RealPostEvidenceRow] = []
        category_counts: Counter[str] = Counter()
        flag_counts: Counter[str] = Counter()
        layer_counts: Counter[str] = Counter()

        for index, record in enumerate(deduped, start=1):
            title = normalize_text(record.title)
            content = normalize_text(record.content)
            ending = ending_snippet(content)
            text = f"{title} {content}"
            flags = flags_for(text)
            category = classify_record(text, content, record.detail_status, profile=profile)
            layers = usable_layers(title, content, ending, profile=profile)
            allow_asset, suggested_use = asset_decision(category, flags, layers)
            dedupe_key = record.note_id or content_hash(title, content)

            category_counts[category] += 1
            flag_counts.update(flags)
            layer_counts.update(layers)

            rows.append(
                RealPostEvidenceRow(
                    source_row_no=index,
                    source_keyword=record.source_keyword,
                    note_id=record.note_id,
                    url=record.note_url,
                    category=category,
                    title=title,
                    original_snippet=snippet(content or title, 120),
                    ending_snippet=snippet(ending, 90),
                    usable_layers=layers,
                    risk_tags=flags,
                    allow_asset=allow_asset,
                    suggested_wangyue_use=suggested_use,
                    likes=record.likes,
                    comments_count=record.comments_count,
                    publish_time=record.publish_time,
                    dedupe_key=dedupe_key,
                )
            )

        stats = {
            "profile": profile,
            "input_count": len(normalized),
            "deduped_count": len(deduped),
            "row_count": len(rows),
            "category_counts": dict(category_counts),
            "risk_tag_counts": dict(flag_counts),
            "usable_layer_counts": dict(layer_counts),
            "stable_candidate_count": sum(1 for row in rows if row.allow_asset == "stable_candidate"),
            "texture_only_count": sum(1 for row in rows if row.allow_asset == "texture_only"),
            "risk_reference_count": sum(1 for row in rows if row.allow_asset == "risk_reference"),
            "exclude_count": sum(1 for row in rows if row.allow_asset == "exclude"),
        }
        return RealPostEvidenceResult(rows=rows, stats=stats)

    def write_csv(self, result: RealPostEvidenceResult, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(row.to_csv_row() for row in result.rows)
        return path

    def write_markdown(self, result: RealPostEvidenceResult, path: Path, *, source_label: str = "") -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown(result, source_label=source_label), encoding="utf-8")
        return path


def normalize_record(record: XhsRealPostRecord | dict[str, Any]) -> XhsRealPostRecord:
    if isinstance(record, XhsRealPostRecord):
        return record
    return XhsRealPostRecord.from_mapping(record)


def dedupe_records(records: list[XhsRealPostRecord]) -> list[XhsRealPostRecord]:
    seen: set[str] = set()
    deduped: list[XhsRealPostRecord] = []
    for record in records:
        key = record.note_id or content_hash(record.title, record.content)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    for source, target in EMOJI_MAP.items():
        text = text.replace(source, target)
    text = re.sub(r"#([^#\[]+)\[话题\]#", r"#\1", text)
    return re.sub(r"\s+", " ", text).strip()


def flags_for(text: str) -> list[str]:
    flags: list[str] = []
    for name, pattern in PATTERNS.items():
        if pattern.search(text):
            flags.append(name)
    for term in WANGYUE_FORBIDDEN_TERMS:
        if term in text:
            flags.append(f"forbidden:{term}")
    return sorted(set(flags))


def classify_record(text: str, content: str, detail_status: str, *, profile: str) -> str:
    if detail_status and detail_status != "ok":
        return "bad_empty"
    if len(content.strip()) < 8:
        return "bad_empty"
    if profile == "wangyue_child_milk":
        if PATTERNS["explicit_low_age"].search(text):
            return "wrong_stage_low_age"
        if PATTERNS["wrong_context_transfer"].search(text):
            return "wrong_context_transfer"
    if PATTERNS["store_kol_ad"].search(text):
        return "store_kol_ad_or_kol"
    if PATTERNS["strong_claim"].search(text) or PATTERNS["digestive_medical"].search(text):
        return "risk_claim_reference_only"
    if PATTERNS["tutorial"].search(text):
        return "format_tutorial_or_guide"
    if len(content.strip()) < 45:
        return "texture_only_short"
    return "real_user_candidate"


def usable_layers(title: str, content: str, ending: str, *, profile: str) -> list[str]:
    text = f"{title} {content} {ending}"
    layers: set[str] = set()
    title_without_emoji = re.sub(r"[\U00010000-\U0010ffff]", "", title)
    if len(title_without_emoji) <= 14:
        layers.add("title_shape:short_fragment")
    if "？" in title or "?" in title or PATTERNS["ask_conversation"].search(title):
        layers.add("title_shape:question_or_conversation")
    if PATTERNS["rebuy_entry"].search(title):
        layers.add("title_shape:rebuy_restock")
    if PATTERNS["compare_entry"].search(title):
        layers.add("title_shape:compare_choice")
    if re.search(r"反馈|随手|日常|记录|喝了|一直", title):
        layers.add("title_shape:record_feedback")
    if PATTERNS["rebuy_entry"].search(text):
        layers.add("product_entry:rebuy_restock")
    if PATTERNS["compare_entry"].search(text):
        layers.add("product_entry:compare_confusion")
    if PATTERNS["child_acceptance"].search(text):
        layers.add("proof_surface:child_acceptance")
    if PATTERNS["ask_conversation"].search(text):
        layers.add("ending_or_entry:question_conversation")
    if PATTERNS["life_texture"].search(text):
        layers.add("life_entry:ordinary_scene")
    if ending and ("？" in ending or "?" in ending):
        layers.add("ending:soft_question")
    if ending and PATTERNS["rebuy_entry"].search(ending):
        layers.add("ending:object_or_restock_stop")
    if ending and PATTERNS["child_acceptance"].search(ending):
        layers.add("ending:child_state_stop")
    if profile == "mom_daily_texture" and not any(layer.startswith("product_entry") for layer in layers):
        layers.add("texture:non_product_life_rhythm")
    return sorted(layers)


def asset_decision(category: str, flags: list[str], layers: list[str]) -> tuple[str, str]:
    hard_flags = {
        "explicit_low_age",
        "wrong_context_transfer",
        "time_current_risk",
        "bad_product_action",
        "wrong_product_form",
    }
    if category in {"bad_empty", "wrong_stage_low_age", "wrong_context_transfer"}:
        return "exclude", "排除：年龄阶段或使用语境不适配旺玥"
    if any(flag in hard_flags or flag.startswith("forbidden:") for flag in flags):
        return "texture_only", "有禁词/时间/动作风险，只能借口气肌理，不能迁移事实"
    if category == "store_kol_ad_or_kol":
        return "texture_only", "只抽结构/标题/收尾节奏，不抽事实和卖点原句"
    if category == "risk_claim_reference_only":
        return "risk_reference", "只做风险样本和强种草表达参照，不直接入 prompt"
    if category == "format_tutorial_or_guide":
        return "texture_only", "只借问题节奏/标题形态，不抽判断事实"
    if layers:
        return "stable_candidate", "可进入证据表，人工筛后转为低权重表达参考"
    return "texture_only", "信息弱，仅作低权重口气观察"


def ending_snippet(content: str) -> str:
    parts = [part.strip() for part in re.split(r"(?<=[。！？!?])|\n+", content) if part.strip()]
    if not parts:
        return ""
    return "".join(parts[-2:]) if len(parts[-1]) < 8 and len(parts) >= 2 else parts[-1]


def snippet(text: str, limit: int = 92) -> str:
    text = normalize_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def content_hash(title: str, content: str) -> str:
    text = normalize_text(f"{title}\n{content}")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def render_markdown(result: RealPostEvidenceResult, *, source_label: str = "") -> str:
    stats = result.stats
    lines = [
        "# 真人帖证据拆解报告",
        "",
        f"- profile: `{stats['profile']}`",
        f"- source: `{source_label}`" if source_label else "- source: 未填写",
        f"- input: {stats['input_count']}；deduped: {stats['deduped_count']}；rows: {stats['row_count']}",
        f"- stable_candidate: {stats['stable_candidate_count']}；texture_only: {stats['texture_only_count']}；risk_reference: {stats['risk_reference_count']}；exclude: {stats['exclude_count']}",
        "",
        "## Category Counts",
        "",
        "```json",
        json.dumps(stats["category_counts"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Usable Layer Counts",
        "",
        "```json",
        json.dumps(stats["usable_layer_counts"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Rows",
        "",
    ]
    for row in result.rows:
        layers = "、".join(row.usable_layers) or "-"
        risks = "、".join(row.risk_tags) or "-"
        lines.extend(
            [
                f"### {row.source_row_no}. {row.title or row.note_id}",
                "",
                f"- keyword: `{row.source_keyword}`",
                f"- category: `{row.category}`；allow_asset: `{row.allow_asset}`",
                f"- layers: {layers}",
                f"- risks: {risks}",
                f"- suggested: {row.suggested_wangyue_use}",
                f"- url: {row.url or '-'}",
                "",
                row.original_snippet or "-",
                "",
                f"> ending: {row.ending_snippet or '-'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
