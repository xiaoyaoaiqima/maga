"""Deterministic guard for implicit old-can eligibility in a2 礼遇 articles."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


A2_REIYU_ARTICLE_ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"

_SENTENCE_SPLIT_RE = re.compile(r"[\n。！？!?；;]+")
_EXISTING_STOCK_PATTERNS = (
    re.compile(
        r"(?:旧罐|老罐)(?:子)?|"
        r"(?:以前|之前)(?:的|买|囤|喝完|吃完|用完|留|存|剩|攒|收)"
        r"[^，。！？；;\n]{0,8}罐(?:子)?"
    ),
    re.compile(
        r"(?:家里|家中)[^，。！？；;\n]{0,8}"
        r"(?:快|马上|眼看)?[^，。！？；;\n]{0,4}"
        r"(?:喝完|吃完|见底)[^，。！？；;\n]{0,6}"
        r"(?:一箱|几箱|好几箱|几罐|好几罐|几个罐|\d+\s*罐|\d+\s*箱)"
    ),
    re.compile(
        r"(?:家里|家中|手头|柜子里|奶粉柜里)[^，。！？；;\n]{0,14}"
        r"(?:刚|已经|正好|刚好|本来就|还|现成)?[^，。！？；;\n]{0,5}"
        r"(?:囤了|买了|存了|备了|留了|放着|留着|有|剩着)[^，。！？；;\n]{0,10}"
        r"(?:一箱|几箱|好几箱|几罐|好几罐|几个罐|\d+\s*罐|\d+\s*箱|这些罐)"
    ),
    re.compile(
        r"(?:正好|刚好|刚)[^，。！？；;\n]{0,8}"
        r"(?:囤了|买了|存了|备了|留了|有)[^，。！？；;\n]{0,10}"
        r"(?:一箱|几箱|好几箱|几罐|好几罐|几个罐|\d+\s*罐|\d+\s*箱)"
    ),
)
_COLLECT_CAN_CUES = re.compile(
    r"集罐|扫罐码|罐码累计|集\s*\d+\s*罐|凑\s*\d+\s*罐|"
    r"集满\s*\d+\s*罐|罐数|换小车|换自行车|换奶粉|换婴儿车|兑小车|兑自行车|兑奶粉|兑婴儿车"
)
_EXPLICIT_NEW_PURCHASE_CUES = re.compile(
    r"(?:活动期间|活动期内|参加活动后|看到活动后|知道活动后|发现活动后|按活动规则)"
    r"[^，。！？；;\n]{0,12}(?:买|补货|囤)"
)
_IMPLICIT_OLD_CAN_WORDING_PATTERNS = (
    re.compile(
        r"(?:平时|日常)[^，。！？；;\n]{0,5}(?:囤货|囤奶粉)"
        r"[^，。！？；;\n]{0,8}(?:正好|刚好)?[^，。！？；;\n]{0,4}(?:能|可以)?用上"
    ),
)


@dataclass(frozen=True)
class A2ReiyuOldCanGuardReview:
    pass_: bool
    hits: list[str]

    def to_payload(self) -> dict[str, Any]:
        return {
            "pass": self.pass_,
            "rewrite_required": False,
            "severity": "pass" if self.pass_ else "hard",
            "business_usability_tier": "direct_pool" if self.pass_ else "hold_out",
            "issue_code": None if self.pass_ else "old_can_eligibility_error",
            "hits": self.hits,
            "reason": (
                "未发现家庭现有库存与本次集罐资格相连。"
                if self.pass_
                else "正文把活动前已在家中的库存奶粉或罐子与本次集罐、扫码或兑换连接起来。"
            ),
        }


def review_a2_reiyu_old_can_eligibility(
    *,
    title: str | None,
    body: str | None,
    plan: dict[str, Any] | None,
) -> A2ReiyuOldCanGuardReview:
    if str((plan or {}).get("asset_key") or "") != A2_REIYU_ARTICLE_ASSET_KEY:
        return A2ReiyuOldCanGuardReview(pass_=True, hits=[])

    text = f"{title or ''}\n{body or ''}"
    sentences = [sentence.strip() for sentence in _SENTENCE_SPLIT_RE.split(text) if sentence.strip()]
    has_collect_can_context = any(_COLLECT_CAN_CUES.search(sentence) for sentence in sentences)
    if not has_collect_can_context:
        return A2ReiyuOldCanGuardReview(pass_=True, hits=[])

    hits: list[str] = []
    for index, sentence in enumerate(sentences):
        if _EXPLICIT_NEW_PURCHASE_CUES.search(sentence):
            continue
        has_existing_stock = any(pattern.search(sentence) for pattern in _EXISTING_STOCK_PATTERNS)
        has_implicit_old_can_wording = any(
            pattern.search(sentence) for pattern in _IMPLICIT_OLD_CAN_WORDING_PATTERNS
        )
        if not has_existing_stock and not has_implicit_old_can_wording:
            continue
        context = "。".join(sentences[max(0, index - 1) : min(len(sentences), index + 2)])
        hits.append(context)

    return A2ReiyuOldCanGuardReview(pass_=not hits, hits=list(dict.fromkeys(hits)))
