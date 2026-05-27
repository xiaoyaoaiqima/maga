"""Extract reusable content elements from reference examples.

The extractor intentionally keeps raw examples as traceable source material and
stores only abstracted, recombinable elements for generation.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.maga_assets import AssetRegistry


REFERENCE_EXAMPLES_ASSET_TYPE = "reference_examples"
REFERENCE_CONTENT_ELEMENTS_ASSET_TYPE = "reference_content_elements"


TITLE_HOOK_RULES = [
    ("求助感", ["怎么办", "求助", "有没有", "能不能", "要不要", "怎么选", "纠结"]),
    ("情绪困扰", ["焦虑", "崩溃", "头疼", "担心", "心累", "害怕", "急"]),
    ("结果反差", ["没想到", "竟然", "原来", "才发现", "后悔", "早知道"]),
    ("场景冲突", ["不喝奶", "不长肉", "便秘", "拉肚子", "吐奶", "夜醒", "转奶"]),
    ("信息差", ["别乱", "避坑", "真相", "区别", "看懂", "功课", "建议"]),
]

OPENING_RULES = [
    ("具体场景开头", ["最近", "这几天", "前段时间", "晚上", "每次", "刚开始", "转奶"]),
    ("痛点直入", ["不喝奶", "不长肉", "便秘", "吐奶", "拉肚子", "夜醒", "奶量"]),
    ("情绪共鸣", ["焦虑", "崩溃", "担心", "心累", "纠结", "害怕"]),
    ("经验提醒", ["别急", "别乱", "建议", "一定要", "先看", "过来人"]),
    ("结果反差", ["没想到", "竟然", "原来", "后来", "才发现"]),
]

SCENE_KEYWORDS = {
    "月龄/阶段": ["月龄", "个月", "一岁", "两岁", "断奶", "转奶", "混合喂养", "三段", "二段"],
    "奶量/喂养": ["奶量", "喝奶", "冲奶", "喂奶", "奶粉", "母婴店", "不爱喝"],
    "便便观察": ["便便", "臭臭", "拉臭", "羊屎", "干硬", "软便", "腹泻"],
    "体重生长": ["体重", "长肉", "长高", "身高", "瘦", "发育"],
    "睡眠状态": ["夜醒", "睡觉", "哭闹", "睡不踏实", "哄睡"],
    "家庭决策": ["婆婆", "队友", "老公", "家里人", "朋友", "妈妈群"],
    "购买选择": ["价格", "活动", "试用", "大罐", "小罐", "囤货", "换奶"],
}

PAINPOINT_RULES = {
    "A1": ("吸收/长肉焦虑", ["不长肉", "长肉", "体重", "偏瘦", "吸收", "吃进去"]),
    "A2": ("肚肚/便便问题", ["便便", "臭臭", "吐奶", "肚肚", "腹泻", "便秘", "哭闹", "夜醒"]),
    "A3": ("保护力/状态不稳", ["保护力", "抵抗力", "中招", "脆皮", "生病", "恢复慢"]),
    "B": ("家长判断问题", ["奶量", "吃饱", "怎么选", "纠结", "不知道", "混合喂养", "转奶"]),
}

PROOF_STYLE_RULES = [
    ("数字细节", [r"\d+\s*(ml|毫升|斤|个月|天|周|次|罐)"]),
    ("前后对比", ["之前", "后来", "现在", "换了", "对比", "变化"]),
    ("日常观察记录", ["观察", "记录", "每天", "这几天", "状态", "便便"]),
    ("第三方意见", ["医生", "母婴店", "朋友", "妈妈群", "婆婆", "客服"]),
    ("选择逻辑", ["看配方", "成分", "价格", "清淡", "好消化", "适合"]),
]

RISK_RULES = [
    ("功效确定化风险", ["治", "治疗", "改善便秘", "立马", "马上好", "一定会", "保证"]),
    ("医疗判断风险", ["过敏", "湿疹", "腹泻", "便秘", "医生说", "医院"]),
    ("夸张效果风险", ["神了", "绝了", "奇迹", "暴涨", "肉眼可见"]),
    ("平台复制风险", ["同款标题/原句高辨识度，生成时只可抽象结构"]),
]

VOICE_TRAITS = [
    ("口语", ["娃", "宝", "我家", "真的", "蛮", "挺", "有点"]),
    ("求助", ["姐妹", "求助", "有没有", "怎么办", "给点意见"]),
    ("过来人", ["过来人", "建议", "别急", "别乱", "踩坑"]),
    ("细节控", ["配方", "成分", "DHA", "OPO", "乳铁", "HMO"]),
    ("反焦虑", ["别焦虑", "慢慢", "先观察", "不用急"]),
]


@dataclass(frozen=True)
class ExtractionResult:
    asset: AssetRegistry | None
    items: list[dict[str, Any]]
    source_asset_id: int
    source_asset_version: int
    source_item_count: int


class ReferenceElementExtractionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def extract_from_latest_asset(
        self,
        *,
        asset_key: str,
        limit: int | None = None,
        persist: bool = False,
        created_by: str = "reference-element-extractor",
    ) -> ExtractionResult:
        source_asset = await self._latest_reference_asset(asset_key)
        if source_asset is None:
            raise ValueError(f"missing {REFERENCE_EXAMPLES_ASSET_TYPE} asset for {asset_key}")
        source_items = _content_items(source_asset.content_json)
        selected_items = source_items[:limit] if limit else source_items
        if not selected_items:
            raise ValueError(f"empty {REFERENCE_EXAMPLES_ASSET_TYPE} asset for {asset_key}")

        extracted_items = [
            extract_reference_content_elements(example, index=index)
            for index, example in enumerate(selected_items, start=1)
        ]
        asset = None
        if persist:
            asset = await self._create_candidate_asset(
                asset_key=asset_key,
                source_asset=source_asset,
                items=extracted_items,
                created_by=created_by,
            )
        return ExtractionResult(
            asset=asset,
            items=extracted_items,
            source_asset_id=source_asset.id,
            source_asset_version=source_asset.version_no,
            source_item_count=len(source_items),
        )

    async def _latest_reference_asset(self, asset_key: str) -> AssetRegistry | None:
        result = await self.db.execute(
            select(AssetRegistry)
            .where(
                AssetRegistry.asset_type == REFERENCE_EXAMPLES_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.asset_stage == "production",
                AssetRegistry.status == "active",
            )
            .order_by(AssetRegistry.version_no.desc(), AssetRegistry.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _create_candidate_asset(
        self,
        *,
        asset_key: str,
        source_asset: AssetRegistry,
        items: list[dict[str, Any]],
        created_by: str,
    ) -> AssetRegistry:
        await self.db.execute(
            update(AssetRegistry)
            .where(
                AssetRegistry.asset_type == REFERENCE_CONTENT_ELEMENTS_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
                AssetRegistry.asset_stage == "candidate",
                AssetRegistry.status == "active",
            )
            .values(status="archived")
        )
        asset = AssetRegistry(
            asset_type=REFERENCE_CONTENT_ELEMENTS_ASSET_TYPE,
            asset_key=asset_key,
            display_name="参考例文可用元素",
            version_no=await self._next_asset_version(asset_key),
            status="active",
            asset_stage="candidate",
            source_name=f"{REFERENCE_EXAMPLES_ASSET_TYPE}:{source_asset.id}",
            source_uri=None,
            source_hash=source_asset.source_hash,
            content_json={
                "items": items,
                "source_asset_id": source_asset.id,
                "source_asset_version": source_asset.version_no,
                "source_item_count": len(_content_items(source_asset.content_json)),
            },
            metadata_json={"extractor": "reference_content_elements_rules_v1"},
            created_by=created_by,
        )
        self.db.add(asset)
        await self.db.flush()
        return asset

    async def _next_asset_version(self, asset_key: str) -> int:
        result = await self.db.execute(
            select(AssetRegistry.version_no)
            .where(
                AssetRegistry.asset_type == REFERENCE_CONTENT_ELEMENTS_ASSET_TYPE,
                AssetRegistry.asset_key == asset_key,
            )
            .order_by(AssetRegistry.version_no.desc())
            .limit(1)
        )
        current = result.scalar_one_or_none()
        return int(current or 0) + 1


def extract_reference_content_elements(example: dict[str, Any], *, index: int) -> dict[str, Any]:
    source_example_id = str(example.get("example_id") or f"reference_example_{index}")
    title = _clean_text(example.get("title"))
    body = _clean_text(example.get("body") or example.get("content"))
    text = f"{title}\n{body}".strip()
    first_unit = _first_text_unit(body)
    painpoint_signals = _matched_keywords(text, [word for _, words in PAINPOINT_RULES.values() for word in words])
    scene_atoms = _scene_atoms(text)
    proof_styles = _proof_styles(text)
    voice_traits = _voice_traits(text)
    avoid_copy_phrases = _avoid_copy_phrases(title, body)
    risk_notes = _risk_notes(text)

    # 这些元素会进入生文调度，不保留原文长段，避免后续生成直接复写例文。
    return {
        "element_id": f"rce_{_short_hash(source_example_id, title, body)}",
        "source_example_id": source_example_id,
        "source_title": title,
        "title_hook": {
            "hook_type": _first_rule_match(title, TITLE_HOOK_RULES, default="生活经验"),
            "title_formula": _title_formula(title),
            "rewrite_angle": _rewrite_angle(title),
        },
        "narrative": {
            "opening_pattern": _opening_pattern(first_unit),
            "opening_type": _first_rule_match(first_unit or body, OPENING_RULES, default="真实经历开头"),
            "story_arc": _story_arc(text),
            "emotion_curve": _emotion_curve(text),
            "ending_pattern": _ending_pattern(body),
        },
        "content_atoms": {
            "scene_atoms": scene_atoms,
            "painpoint_signals": painpoint_signals,
            "painpoint_categories": _painpoint_categories(text),
            "persona_signals": _persona_signals(text),
            "time_stage": _time_stage(text),
        },
        "writing_strategy": {
            "proof_style": proof_styles[0] if proof_styles else "日常观察记录",
            "proof_styles": proof_styles,
            "selling_point_placement": _selling_point_placement(text),
            "voice_traits": voice_traits,
            "emotion_intensity": _emotion_intensity(text),
        },
        "safety": {
            "avoid_copy_phrases": avoid_copy_phrases,
            "risk_notes": risk_notes,
        },
        "quality": {
            "extract_confidence": _extract_confidence(
                scene_atoms=scene_atoms,
                painpoint_signals=painpoint_signals,
                proof_styles=proof_styles,
                body=body,
            ),
            "source_body_chars": len(body),
        },
        "review_status": "pending",
        "element_source": "rules_v1",
    }


def _content_items(content: dict[str, Any] | None) -> list[dict[str, Any]]:
    items = (content or {}).get("items")
    return [item for item in items or [] if isinstance(item, dict)]


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _short_hash(*values: str) -> str:
    digest = hashlib.sha1("|".join(values).encode("utf-8")).hexdigest()
    return digest[:12]


def _first_rule_match(text: str, rules: list[tuple[str, list[str]]], *, default: str) -> str:
    for label, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return label
    return default


def _matched_keywords(text: str, keywords: list[str], *, limit: int = 10) -> list[str]:
    matched: list[str] = []
    for keyword in keywords:
        if keyword and keyword in text and keyword not in matched:
            matched.append(keyword)
        if len(matched) >= limit:
            break
    return matched


def _first_text_unit(text: str) -> str:
    compact = _clean_text(text)
    parts = re.split(r"[。！？!?；;\n]", compact)
    return next((part.strip() for part in parts if part.strip()), compact[:80])


def _title_formula(title: str) -> str:
    if not title:
        return "具体场景 + 妈妈判断"
    has_question = any(mark in title for mark in ["?", "？", "吗", "怎么办", "求助"])
    has_number = bool(re.search(r"\d", title))
    hook_type = _first_rule_match(title, TITLE_HOOK_RULES, default="生活经验")
    if has_question:
        return f"{hook_type} + 具体问题"
    if has_number:
        return f"数字细节 + {hook_type}"
    if len(title) <= 16:
        return f"短标题 + {hook_type}"
    return f"具体状态 + {hook_type}"


def _rewrite_angle(title: str) -> str:
    hook_type = _first_rule_match(title, TITLE_HOOK_RULES, default="生活经验")
    return f"保留“{hook_type}”的吸引方式，替换具体经历和原句表达"


def _opening_pattern(first_unit: str) -> str:
    if not first_unit:
        return "用妈妈视角的具体喂养/观察场景开头"
    return f"先抛出类似“{first_unit[:28]}”的具体妈妈场景，但更换人物、状态和措辞"


def _story_arc(text: str) -> str:
    if any(word in text for word in ["纠结", "怎么选", "不知道", "对比"]):
        return "选择困惑 -> 判断依据 -> 产品/方案出现 -> 轻建议"
    if any(word in text for word in ["没想到", "后来", "现在", "之前"]):
        return "状态反差 -> 回看原因 -> 重建判断 -> 温和收束"
    if any(word in text for word in ["便便", "奶量", "体重", "夜醒"]):
        return "痛点场景 -> 连续观察 -> 选择逻辑 -> 同类提醒"
    return "真实经历 -> 关键观察 -> 个人判断 -> 轻建议"


def _emotion_curve(text: str) -> list[str]:
    curve: list[str] = []
    if any(word in text for word in ["焦虑", "担心", "害怕", "急", "心累"]):
        curve.append("焦虑")
    if any(word in text for word in ["纠结", "不知道", "犹豫", "怎么选"]):
        curve.append("犹豫")
    if any(word in text for word in ["观察", "对比", "发现", "看了"]):
        curve.append("观察判断")
    if any(word in text for word in ["接受", "适合", "放心", "轻松", "还不错"]):
        curve.append("确认方向")
    return curve or ["真实记录", "逐步判断", "轻建议"]


def _ending_pattern(body: str) -> str:
    tail = body[-80:]
    if any(word in tail for word in ["评论", "姐妹", "有没有", "求"]):
        return "以评论互动或求助收尾"
    if any(word in tail for word in ["建议", "可以", "别急", "先"]):
        return "以给同类妈妈的轻建议收尾"
    if any(word in tail for word in ["活动", "抽奖", "冲"]):
        return "以活动/行动提醒收尾"
    return "以个人感受或状态观察收尾"


def _scene_atoms(text: str) -> list[str]:
    atoms: list[str] = []
    for scene, keywords in SCENE_KEYWORDS.items():
        matches = _matched_keywords(text, keywords, limit=3)
        if matches:
            atoms.append(f"{scene}: {'/'.join(matches)}")
    return atoms


def _painpoint_categories(text: str) -> list[dict[str, str]]:
    categories: list[dict[str, str]] = []
    for code, (name, keywords) in PAINPOINT_RULES.items():
        matches = _matched_keywords(text, keywords, limit=3)
        if matches:
            categories.append({"category_code": code, "category_name": name, "matched_signals": "、".join(matches)})
    return categories


def _persona_signals(text: str) -> list[str]:
    signals = []
    if any(word in text for word in ["新手", "一胎", "第一次"]):
        signals.append("新手妈妈")
    if any(word in text for word in ["二胎", "老二", "大宝"]):
        signals.append("二胎妈妈")
    if any(word in text for word in ["纠结", "对比", "功课", "成分"]):
        signals.append("谨慎研究型妈妈")
    if any(word in text for word in ["焦虑", "担心", "怕"]):
        signals.append("容易焦虑的妈妈")
    return signals or ["真实分享型妈妈"]


def _time_stage(text: str) -> list[str]:
    patterns = [
        r"\d+\s*个月",
        r"\d+\s*岁",
        r"[一二三四五六七八九十两]+个月",
        r"[一二三四五六七八九十两]+岁",
        r"转奶期",
        r"断奶后",
        r"混合喂养",
    ]
    stages: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, text):
            if match not in stages:
                stages.append(match)
    return stages[:6]


def _proof_styles(text: str) -> list[str]:
    styles: list[str] = []
    for label, rules in PROOF_STYLE_RULES:
        if any(re.search(rule, text, flags=re.IGNORECASE) for rule in rules):
            styles.append(label)
    return styles


def _selling_point_placement(text: str) -> str:
    product_words = ["配方", "成分", "奶粉", "源悦", "OPO", "HMO", "乳铁", "天然乳脂", "清淡"]
    positions = [text.find(word) for word in product_words if text.find(word) >= 0]
    if not positions:
        return "未明显植入卖点，适合只借鉴场景和语气"
    first = min(positions)
    ratio = first / max(len(text), 1)
    if ratio < 0.25:
        return "开头较早出现产品/卖点，生成时需弱化硬广感"
    if ratio < 0.7:
        return "正文中段结合判断逻辑自然带出"
    return "结尾补充式带出产品/卖点"


def _voice_traits(text: str) -> list[str]:
    traits = [label for label, keywords in VOICE_TRAITS if any(keyword in text for keyword in keywords)]
    return traits or ["真实", "妈妈视角"]


def _emotion_intensity(text: str) -> str:
    high_words = ["崩溃", "绝了", "真的会谢", "太难", "急死", "心累"]
    medium_words = ["焦虑", "担心", "纠结", "害怕", "不放心"]
    if any(word in text for word in high_words):
        return "high"
    if any(word in text for word in medium_words):
        return "medium"
    return "low"


def _avoid_copy_phrases(title: str, body: str) -> list[str]:
    phrases: list[str] = []
    if title:
        phrases.append(title[:28])
    for sentence in re.split(r"[。！？!?；;\n]", body):
        phrase = sentence.strip()
        if 8 <= len(phrase) <= 34 and phrase not in phrases:
            phrases.append(phrase)
        if len(phrases) >= 8:
            break
    return phrases


def _risk_notes(text: str) -> list[str]:
    notes = []
    for label, keywords in RISK_RULES:
        if any(keyword in text for keyword in keywords):
            notes.append(label)
    return notes or ["只可复用结构、场景类型和表达策略，不复用原文具体经历"]


def _extract_confidence(
    *,
    scene_atoms: list[str],
    painpoint_signals: list[str],
    proof_styles: list[str],
    body: str,
) -> float:
    score = 0.2
    score += min(len(scene_atoms), 4) * 0.12
    score += min(len(painpoint_signals), 5) * 0.06
    score += min(len(proof_styles), 3) * 0.08
    score += 0.15 if len(body) >= 80 else 0
    return round(min(score, 0.95), 2)
