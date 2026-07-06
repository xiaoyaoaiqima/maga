"""Lightweight AI-flavor review for generated article title/body."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


TITLE_CLAIM_TERMS = (
    "保护力",
    "眼脑",
    "DHA",
    "HMO",
    "燕窝酸",
    "乳铁蛋白",
    "免疫球蛋白",
    "钙铁锌",
    "关键营养",
)

TITLE_RISK_OR_EFFECT_TERMS = (
    "不中招",
    "不生病",
    "少请假",
    "注意力",
    "专注",
    "坐得住",
    "长高",
    "长肉",
    "体质稳",
)

TITLE_SUMMARY_PATTERNS = (
    re.compile(r"选奶.{0,6}(?:看|关注|留意|记).{0,8}(?:保护力|眼脑|营养|DHA|HMO|燕窝酸|乳铁蛋白)"),
    re.compile(r"(?:保护力|眼脑|DHA|HMO|燕窝酸|乳铁蛋白).{0,8}(?:这块|方向|选择|复盘|记录)"),
    re.compile(r"(?:配方|成分|营养).{0,8}(?:全面|到位|够全|更安心|心动|真香|选对|没白看)"),
    re.compile(r"选奶.{0,6}(?:重点|主要|认真|特意).{0,8}(?:看|关注|留意|研究).{0,8}(?:营养|配方|成分)"),
)

TITLE_EXPLANATORY_PATTERNS = (
    re.compile(r"(?:选奶|挑奶).{0,8}(?:认真|特意|重点).{0,6}(?:看|留意|关注|研究).{0,8}(?:阶段|方向|选择|依据)"),
    re.compile(r"(?:我|妈妈).{0,4}(?:认真|特意|重点).{0,6}(?:看|留意|关注|研究).{0,8}(?:阶段|方向|选择|依据)"),
    re.compile(r"(?:选奶|挑奶).{0,8}阶段(?:变了|对上|对得上)"),
)

BODY_AUDIT_FENCE_PATTERNS = (
    re.compile(r"不是(?:说|要说).{0,12}喝了.{0,10}(?:怎样|怎么样|就)"),
    re.compile(r"也不是(?:说|要说).{0,12}喝了.{0,10}"),
    re.compile(r"(?:我也)?没指望.{0,12}喝了.{0,10}就"),
    re.compile(r"不会说.{0,12}喝了.{0,10}就"),
    re.compile(r"不敢说.{0,12}喝了.{0,10}就"),
    re.compile(r"喝了.{0,12}(?:吗|么)[？?].{0,8}不敢(?:这么)?(?:说|讲)"),
    re.compile(r"(?:目前|暂时|具体)?.{0,4}还在观察"),
    re.compile(r"后续再观察.{0,4}(?:看吧)?"),
    re.compile(r"说不上.{0,8}(?:有没有用|有没有帮助|有没有变化)"),
    re.compile(r"(?:现在|目前|暂时).{0,8}还说不上来"),
    re.compile(r"不能指望.{0,8}(?:一罐|一杯|一个).{0,8}(?:奶粉|奶)"),
    re.compile(r"(?:奶粉|旺玥).{0,8}不是.{0,4}万能钥匙"),
    re.compile(r"每(?:个|家).{0,4}(?:娃|孩子|情况).{0,6}不一样"),
    re.compile(r"不替别人.{0,8}(?:说|判断|做结论)"),
)

BODY_EXPLANATION_PHRASES = (
    "选择理由",
    "多一层考虑",
    "这个方向",
    "筛选条件",
    "卡在我关注的点",
    "关注的点",
    "值得放进筛选条件",
    "这个点我当时记住了",
    "算是当时记住的一个点",
    "这类营养",
    "保护力那块",
    "眼脑营养这块",
    "跟得上桌面时间",
    "日常选择里",
    "会把这个算进去",
    "把日常营养兜底的事交给儿童奶粉",
    "至少营养上有个托底",
)

BODY_ABSTRACT_BRIDGE_PATTERNS = (
    re.compile(r"(?:这个方向|这类营养|这个点).{0,12}(?:筛选条件|关注|记住|留下|候选|看看)"),
    re.compile(r"(?:保护力|眼脑营养).{0,6}(?:这块|那块|方向).{0,12}(?:看看|关注|筛选|候选)"),
    re.compile(r"(?:DHA|燕窝酸|乳铁蛋白|免疫球蛋白).{0,12}(?:卡在我关注|放进筛选|进入候选)"),
    re.compile(r"跟得上桌面时间"),
)

BODY_MARKETING_TERMS = (
    "保护力",
    "眼脑",
    "DHA",
    "HMO",
    "燕窝酸",
    "乳铁蛋白",
    "免疫球蛋白",
    "钙铁锌",
    "关键营养",
    "30多种",
    "口感比较清淡",
)

BODY_SUMMARY_CLOSURE_PHRASES = (
    "只能说",
    "心里没那么慌",
    "不算满分推荐",
    "每家情况不一样",
    "看自己需求",
    "总没错",
    "有个底",
    "心里稳点",
    "心里不慌",
    "没觉得选错",
    "算是阶段上对得上",
    "营养不能含糊",
    "先选着备着",
    "后面再看情况",
)


@dataclass(slots=True)
class AIFlavorReview:
    pass_: bool
    rewrite_required: bool
    reasons: list[str]
    title_hits: list[str]
    body_hits: list[str]
    rewrite_operations: list[str]

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def review_ai_flavor(title: str | None, body: str | None, plan: dict[str, Any] | None = None) -> AIFlavorReview:
    """Detect AI/marketing texture that should be humanized after generation."""
    title_text = str(title or "").strip()
    body_text = str(body or "").strip()
    plan = plan or {}

    title_hits: list[str] = []
    body_hits: list[str] = []
    reasons: list[str] = []
    operations: list[str] = []

    claim_title_hits: list[str] = []
    claim_title_hits.extend(_substring_hits(title_text, TITLE_CLAIM_TERMS))
    claim_title_hits.extend(_substring_hits(title_text, TITLE_RISK_OR_EFFECT_TERMS))
    claim_title_hits.extend(_regex_hits(title_text, TITLE_SUMMARY_PATTERNS))
    title_explanatory_hits = _regex_hits(title_text, TITLE_EXPLANATORY_PATTERNS)
    title_hits.extend(claim_title_hits)
    title_hits.extend(title_explanatory_hits)
    title_hits = _dedupe(title_hits)
    if claim_title_hits:
        reasons.append("title_exposes_product_claim_or_summary")
        operations.append("title_to_life_entry")
    if title_explanatory_hits:
        reasons.append("title_overexplains_post_logic")
        operations.append("title_to_lower_obligation_fragment")

    audit_hits = _regex_hits(body_text, BODY_AUDIT_FENCE_PATTERNS)
    if audit_hits:
        body_hits.extend(audit_hits)
        reasons.append("audit_fence_phrase")
        operations.append("remove_audit_fence")

    explanation_hits = _substring_hits(body_text, BODY_EXPLANATION_PHRASES)
    abstract_bridge_hits = _regex_hits(body_text, BODY_ABSTRACT_BRIDGE_PATTERNS)
    if len(explanation_hits) >= 2 or abstract_bridge_hits:
        body_hits.extend(explanation_hits)
        body_hits.extend(abstract_bridge_hits)
        reasons.append("explanation_voice")
        operations.append("scene_over_explanation")

    marketing_hits = _substring_hits(body_text, BODY_MARKETING_TERMS)
    if _is_overdense_marketing_text(body_text, marketing_hits, plan):
        body_hits.extend(marketing_hits)
        reasons.append("marketing_density")
        operations.append("keep_one_product_basis")

    if _is_overlong_selection_review(body_text, plan):
        reasons.append("overlong_selection_review")
        operations.append("compress_to_one_scene_one_basis")

    closure_hits = _summary_closure_hits(body_text)
    if _is_overcomplete_summary_closure(body_text, closure_hits, plan):
        body_hits.extend(closure_hits)
        reasons.append("overcomplete_summary_closure")
        operations.append("loosen_or_remove_summary_closure")

    body_hits = _dedupe(body_hits)
    operations = _dedupe(operations)
    return AIFlavorReview(
        pass_=not reasons,
        rewrite_required=bool(reasons),
        reasons=reasons,
        title_hits=title_hits,
        body_hits=body_hits,
        rewrite_operations=operations,
    )


def _substring_hits(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term and term in text]


def _regex_hits(text: str, patterns: tuple[re.Pattern[str], ...]) -> list[str]:
    hits: list[str] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            hit = match.group(0).strip()
            if hit:
                hits.append(hit)
    return hits


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _compact_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _is_selection_review_plan(plan: dict[str, Any]) -> bool:
    marker_text = " ".join(
        str(plan.get(key) or "")
        for key in ("post_type", "ugc_post_type", "business_rule", "product_appearance_mode", "corpus")
    )
    return any(marker in marker_text for marker in ("选奶", "选择复盘", "选择依据", "选择理由", "对比选择"))


def _is_overdense_marketing_text(text: str, hits: list[str], plan: dict[str, Any]) -> bool:
    if len(set(hits)) >= 4:
        return True
    return _is_selection_review_plan(plan) and len(set(hits)) >= 3 and _compact_len(text) >= 180


def _is_overlong_selection_review(text: str, plan: dict[str, Any]) -> bool:
    return _is_selection_review_plan(plan) and _compact_len(text) >= 280


def _summary_closure_hits(text: str) -> list[str]:
    closing = _closing_text(text, chars=90)
    return _substring_hits(closing, BODY_SUMMARY_CLOSURE_PHRASES)


def _closing_text(text: str, *, chars: int) -> str:
    compact = re.sub(r"\s+", "", text or "")
    return compact[-chars:]


def _is_overcomplete_summary_closure(text: str, hits: list[str], plan: dict[str, Any]) -> bool:
    if not _is_selection_review_plan(plan):
        return False
    if len(set(hits)) >= 2:
        return True
    return _compact_len(text) >= 140 and any(hit in {"不算满分推荐", "看自己需求"} for hit in hits)
