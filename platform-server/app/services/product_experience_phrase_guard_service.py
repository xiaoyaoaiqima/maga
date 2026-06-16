"""QA guard for repeated article business-rule phrase patterns."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


SKELETON_PARTS: dict[str, tuple[str, ...]] = {
    "selection_process": (
        "纠结",
        "犹豫",
        "做功课",
        "翻成分表",
        "看成分表",
        "对比",
        "看评价",
        "问朋友",
        "问店员",
        "选奶",
        "换奶",
        "4段",
    ),
    "price": (
        "贵",
        "不便宜",
        "价格",
        "肉疼",
        "趁活动",
        "不算便宜",
        "闭眼买",
        "心疼",
    ),
    "kid_acceptance": (
        "愿意喝",
        "不排斥",
        "不抗拒",
        "接受",
        "喝完",
        "咕咚",
        "顺口",
        "口味",
        "主动要喝",
        "喝光",
    ),
    "ai_closure": (
        "省心",
        "踏实",
        "固定",
        "固定下来",
        "心里有数",
        "好执行",
        "省得",
        "先这样",
        "继续喝着",
        "不用额外操心",
    ),
}

AI_PHRASES = (
    "省心",
    "踏实",
    "固定下来",
    "这事先这么放着",
    "不用每天临时凑",
    "不用临时凑",
    "不用额外想一堆",
    "不用额外想",
    "孩子愿意喝就好执行",
    "早上冲得快",
    "价格不算友好",
    "心里有数",
    "安心",
    "老母亲",
    "神药",
    "收藏起来",
    "收藏",
    "没那么焦虑",
    "放进日常",
    "固定在日常",
)

HARD_AI_CLOSURE_PHRASES = (
    "省心",
    "踏实",
    "安心",
    "老母亲",
    "神药",
    "收藏起来",
    "收藏",
    "固定下来",
    "这事先这么放着",
)

STRONG_REAL_PHRASES = (
    "没再半夜闹腾",
    "不容易中招",
    "精力恢复得快",
    "一直挺稳",
    "可能跟每天那杯旺玥有关系",
    "可能跟每天那杯有关系",
    "坐不住",
    "坐不久",
    "少请假",
    "长个",
    "窜个",
    "抵抗力",
)

HARD_RISK_PHRASES = (
    "保证长高",
    "一定长高",
    "喝了就不生病",
    "不生病了",
    "再也不生病",
    "提高免疫力",
    "增强免疫力",
    "免疫力提高",
    "治疗",
    "改善乳糖不耐受",
    "乳糖不耐受好转",
    "专注力提升",
    "专注力变好",
)


@dataclass(frozen=True)
class ProductExperiencePhraseReview:
    pass_: bool
    rewrite_required: bool
    reasons: list[str]
    skeleton_parts: list[str]
    skeleton_hits: dict[str, list[str]]
    ai_phrase_hits: list[str]
    strong_real_expression_hits: list[str]
    hard_risk_hits: list[str]
    body_chars: int
    length_target: tuple[str, int, int] | None = None

    def model_dump(self) -> dict[str, Any]:
        return {
            "pass": self.pass_,
            "rewrite_required": self.rewrite_required,
            "reasons": self.reasons,
            "skeleton_parts": self.skeleton_parts,
            "skeleton_hits": self.skeleton_hits,
            "ai_phrase_hits": self.ai_phrase_hits,
            "strong_real_expression_hits": self.strong_real_expression_hits,
            "hard_risk_hits": self.hard_risk_hits,
            "body_chars": self.body_chars,
            "length_target": self.length_target,
        }


def should_review_product_experience(plan: dict[str, Any] | None) -> bool:
    plan = plan or {}
    corpus = str(plan.get("corpus") or "")
    return (
        plan.get("rule_type") == "business_rule"
        and (
            str(plan.get("asset_key") or "").startswith("wangyue_")
            or "0705旺玥活动" in corpus
        )
    )


def review_product_experience_phrase(
    *,
    title: str | None,
    body: str | None,
    plan: dict[str, Any] | None,
) -> ProductExperiencePhraseReview:
    body_text = str(body or "")
    text = f"{title or ''}\n{body_text}"
    skeleton_hits = {
        part: _hits(body_text, phrases)
        for part, phrases in SKELETON_PARTS.items()
        if _hits(body_text, phrases)
    }
    skeleton_parts = sorted(skeleton_hits)
    ai_hits = _hits(text, AI_PHRASES)
    strong_real_hits = _hits(text, STRONG_REAL_PHRASES)
    hard_risk_hits = _hits(text, HARD_RISK_PHRASES)
    body_chars = _compact_len(body_text)
    length_target = _article_length_target(plan or {})

    reasons: list[str] = []
    if len(skeleton_parts) >= 3:
        reasons.append("complete_selection_price_acceptance_closure_skeleton")
    if len(ai_hits) >= 2:
        reasons.append("repeated_ai_closure_phrases")
    if _hits(text, HARD_AI_CLOSURE_PHRASES):
        reasons.append("hard_ai_closure_phrase")
    if hard_risk_hits:
        reasons.append("hard_risk_expression")

    rewrite_required = bool(reasons)
    return ProductExperiencePhraseReview(
        pass_=not rewrite_required,
        rewrite_required=rewrite_required,
        reasons=reasons,
        skeleton_parts=skeleton_parts,
        skeleton_hits=skeleton_hits,
        ai_phrase_hits=ai_hits,
        strong_real_expression_hits=strong_real_hits,
        hard_risk_hits=hard_risk_hits,
        body_chars=body_chars,
        length_target=length_target,
    )


def _hits(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [phrase for phrase in phrases if phrase and phrase in text]


def _compact_len(value: str | None) -> int:
    return len(re.sub(r"\s+", "", str(value or "")))


def _article_length_target(plan: dict[str, Any]) -> tuple[str, int, int] | None:
    corpus = str(plan.get("corpus") or "")
    if "篇幅类型：中短文" in corpus:
        return "中短文", 120, 150
    if "篇幅类型：短文" in corpus:
        return "短文", 40, 80
    return None
