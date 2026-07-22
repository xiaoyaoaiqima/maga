"""Deterministic forbidden-term review and controlled rewrite flow."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content_agent import ContentBatchItem
from app.services.business_forbidden_term_service import (
    A2_REIYU_UGC_POST_ASSET_KEY,
    BusinessForbiddenTermService,
)
from app.services.content_agent_orchestrator import ContentAgentOrchestrator
from app.services.content_generation_expert_service import ContentGenerationExpertService
from app.services.content_rewrite_context import rewrite_business_rule_context

STATIC_FORBIDDEN_REPLACEMENTS = {"肠胃": "肚肚"}
WANGYUE_STATIC_FORBIDDEN_REPLACEMENTS = {
    "🍼": "",
    "宝宝": "孩子",
    "宝妈": "家长",
    "体质": "体格",
    "脾胃": "肚肚状态",
}
WANGYUE_STATIC_BLOCK_ONLY_TERMS = {"底气", "流感"}
STATIC_MEDICAL_FORBIDDEN_TERMS = [
    "治疗便秘",
    "治好便秘",
    "改善便秘",
    "解决便秘",
    "根治",
    "疗效",
]
STATIC_FORBIDDEN_TERMS = [
    *STATIC_MEDICAL_FORBIDDEN_TERMS,
    *STATIC_FORBIDDEN_REPLACEMENTS.keys(),
]
WANGYUE_STATIC_FORBIDDEN_TERMS = [
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
    "松快",
    "3段",
    "三段",
    "4段",
    "源乳",
    "初乳",
    "换季",
    "流感",
    "秋游",
    "春游",
]
WANGYUE_STATIC_FORBIDDEN_TERM_REASONS = {
    "3段": "旺玥是3岁以上儿童奶粉，不写成3段奶粉。",
    "三段": "旺玥是3岁以上儿童奶粉，不写成三段奶粉。",
    "4段": "旺玥不是4段奶粉，品牌定位是儿童奶粉；不能把旺玥和4段奶粉放在一起关联。",
    "流感": "旺玥内容禁止出现流感相关字样；无论当前或过去语境，命中即硬阻断，不改写。",
}
ALLOWED_PROPRIETARY_TERMS = {
    "天然乳脂": "__MAGA_ALLOWED_TIANRANRUZHI__",
}
MAX_FORBIDDEN_TERM_REWRITE_ROUNDS = 2


@dataclass(frozen=True)
class ForbiddenTermAuditResult:
    terms: list[str]
    hits: list[str]
    replacements: dict[str, str]
    term_reasons: dict[str, str]
    enforcements: dict[str, str]
    rewrite_model_configs: dict[str, dict[str, Any]]
    match_modes: dict[str, str]


class ForbiddenTermReviewService:
    """MAGA-owned review gate for static and business forbidden terms."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_terms(self, *, asset_key: str | None = None) -> list[str]:
        terms: list[str] = []
        for term in _static_forbidden_terms_for_asset(asset_key):
            if term not in terms:
                terms.append(term)
        for term in await BusinessForbiddenTermService(self.db).list_terms(asset_key=asset_key):
            if term not in terms:
                terms.append(term)
        return terms

    async def audit_text(
        self,
        *,
        asset_key: str | None,
        title: str | None,
        body: str | None,
    ) -> ForbiddenTermAuditResult:
        term_service = BusinessForbiddenTermService(self.db)
        static_terms = _static_forbidden_terms_for_asset(asset_key)
        business_entries = await term_service.list_entries(asset_key=asset_key)
        business_by_term = {
            entry["term"]: entry
            for entry in business_entries
            if entry.get("term") and entry.get("enabled") is not False
        }
        terms = list(static_terms)
        for term in business_by_term:
            if term not in terms:
                terms.append(term)
        text = _text(title, body)
        hits = find_forbidden_hits(text, static_terms)
        for term, entry in business_by_term.items():
            if _business_entry_matches(text, entry) and term not in hits:
                hits.append(term)
        hits = sorted(hits, key=len, reverse=True)
        replacements = {
            **_static_forbidden_replacements_for_asset(asset_key),
            **{
                term: str(entry.get("replacement") or "")
                for term, entry in business_by_term.items()
                if entry.get("replacement") is not None
            },
        }
        term_reasons = {
            **_static_forbidden_term_reasons_for_asset(asset_key),
            **{
                term: str(entry.get("reason") or "")
                for term, entry in business_by_term.items()
                if entry.get("reason")
            },
        }
        enforcements = {
            term: str(entry.get("enforcement") or "")
            for term, entry in business_by_term.items()
            if term in hits
        }
        rewrite_model_configs = {
            term: dict(entry.get("rewrite_model_config") or {})
            for term, entry in business_by_term.items()
            if term in hits and isinstance(entry.get("rewrite_model_config"), dict)
        }
        match_modes = {
            term: str(entry.get("match_mode") or "literal")
            for term, entry in business_by_term.items()
            if term in hits
        }
        return ForbiddenTermAuditResult(
            terms=terms,
            hits=hits,
            replacements={hit: replacements[hit] for hit in hits if hit in replacements},
            term_reasons={hit: term_reasons[hit] for hit in hits if term_reasons.get(hit)},
            enforcements=enforcements,
            rewrite_model_configs=rewrite_model_configs,
            match_modes=match_modes,
        )

    async def review_and_rewrite_item(
        self,
        *,
        item: ContentBatchItem,
        asset_key: str | None,
        orchestrator: ContentAgentOrchestrator | None,
        executor_code: str | None,
        content_type: str,
        max_rounds: int = MAX_FORBIDDEN_TERM_REWRITE_ROUNDS,
        allow_rewrite: bool = True,
        allow_model_rewrite: bool = True,
    ) -> dict[str, Any]:
        audit = await self.audit_text(asset_key=asset_key, title=item.title, body=item.body)
        if not audit.hits:
            quality = dict(item.quality_json or {})
            quality["forbidden_terms_review"] = _review_payload(
                initial_hits=[],
                final_hits=[],
                rewrite_rounds=0,
                rewrite_method="none",
                term_reasons={},
                term_enforcements={},
            )
            item.quality_json = quality
            return quality["forbidden_terms_review"]

        initial_hits = list(audit.hits)
        initial_term_reasons = dict(audit.term_reasons)
        initial_enforcements = {
            hit: audit.enforcements.get(hit) or "legacy_rewrite"
            for hit in initial_hits
        }
        if not allow_rewrite:
            review_payload = _review_payload(
                initial_hits=initial_hits,
                final_hits=initial_hits,
                rewrite_rounds=0,
                rewrite_method="audit_only",
                term_reasons=initial_term_reasons,
                term_enforcements=initial_enforcements,
            )
            quality = _quality_with_forbidden_review(item.quality_json or {}, review_payload)
            item.quality_json = quality
            return review_payload

        static_block_only_hits = [hit for hit in initial_hits if hit in _static_block_only_terms_for_asset(asset_key)]
        hard_ban_hits = [hit for hit in initial_hits if audit.enforcements.get(hit) == "hard_ban"]
        if static_block_only_hits or hard_ban_hits:
            blocking_hits = list(dict.fromkeys([*static_block_only_hits, *hard_ban_hits]))
            review_payload = _review_payload(
                initial_hits=initial_hits,
                final_hits=initial_hits if hard_ban_hits else static_block_only_hits,
                rewrite_rounds=0,
                rewrite_method="hard_ban" if hard_ban_hits else "block_only",
                term_reasons=initial_term_reasons,
                term_enforcements=initial_enforcements,
                blocking_hits=blocking_hits,
            )
            quality = _quality_with_forbidden_review(item.quality_json or {}, review_payload)
            item.quality_json = quality
            return review_payload

        replace_hits = [
            hit
            for hit in initial_hits
            if audit.enforcements.get(hit) == "replace"
            or (
                not allow_model_rewrite
                and not audit.enforcements.get(hit)
                and hit in audit.replacements
            )
        ]
        if replace_hits:
            item.title = _remove_or_replace_forbidden_terms(item.title or "", replace_hits, audit.replacements)
            item.body = _remove_or_replace_forbidden_terms(item.body or "", replace_hits, audit.replacements)
            audit = await self.audit_text(asset_key=asset_key, title=item.title, body=item.body)

        current_hits = list(audit.hits)
        model_rewrite_hits = [hit for hit in current_hits if audit.enforcements.get(hit) == "model_rewrite"]
        legacy_hits = [hit for hit in current_hits if not audit.enforcements.get(hit)]
        if not model_rewrite_hits and not legacy_hits:
            review_payload = _review_payload(
                initial_hits=initial_hits,
                final_hits=current_hits,
                rewrite_rounds=0,
                rewrite_method="deterministic_replace" if replace_hits else "none",
                term_reasons=initial_term_reasons,
                term_enforcements=initial_enforcements,
            )
            quality = _quality_with_forbidden_review(item.quality_json or {}, review_payload)
            item.quality_json = quality
            return review_payload

        if not allow_model_rewrite:
            review_payload = _review_payload(
                initial_hits=initial_hits,
                final_hits=current_hits,
                rewrite_rounds=0,
                rewrite_method=(
                    "deterministic_replace+model_rewrite_disabled"
                    if replace_hits
                    else "model_rewrite_disabled"
                ),
                term_reasons=initial_term_reasons,
                term_enforcements=initial_enforcements,
            )
            quality = _quality_with_forbidden_review(item.quality_json or {}, review_payload)
            item.quality_json = quality
            return review_payload

        if model_rewrite_hits and (not item.run_id or orchestrator is None):
            if legacy_hits:
                item.title = _remove_or_replace_forbidden_terms(item.title or "", legacy_hits, audit.replacements)
                item.body = _remove_or_replace_forbidden_terms(item.body or "", legacy_hits, audit.replacements)
            final_audit = await self.audit_text(asset_key=asset_key, title=item.title, body=item.body)
            review_payload = _review_payload(
                initial_hits=initial_hits,
                final_hits=final_audit.hits,
                rewrite_rounds=0,
                rewrite_method="model_rewrite_unavailable",
                last_error="content.rewrite is required for model_rewrite terms",
                term_reasons=initial_term_reasons,
                term_enforcements=initial_enforcements,
            )
            quality = _quality_with_forbidden_review(item.quality_json or {}, review_payload)
            item.quality_json = quality
            return review_payload

        if not model_rewrite_hits and legacy_hits and (not item.run_id or orchestrator is None):
            item.title = _remove_or_replace_forbidden_terms(item.title or "", legacy_hits, audit.replacements)
            item.body = _remove_or_replace_forbidden_terms(item.body or "", legacy_hits, audit.replacements)
            final_audit = await self.audit_text(asset_key=asset_key, title=item.title, body=item.body)
            review_payload = _review_payload(
                initial_hits=initial_hits,
                final_hits=final_audit.hits,
                rewrite_rounds=1,
                rewrite_method="deterministic_sanitize",
                term_reasons=initial_term_reasons,
                term_enforcements=initial_enforcements,
            )
            quality = _quality_with_forbidden_review(item.quality_json or {}, review_payload)
            item.quality_json = quality
            return review_payload

        rewrite_rounds = 0
        rewrite_method = "deterministic_replace" if replace_hits else "none"
        last_error: str | None = None
        for round_no in range(1, max_rounds + 1):
            current_audit = await self.audit_text(asset_key=asset_key, title=item.title, body=item.body)
            current_hits = [
                hit
                for hit in current_audit.hits
                if current_audit.enforcements.get(hit) == "model_rewrite"
                or not current_audit.enforcements.get(hit)
            ]
            if not current_hits:
                break
            rewrite_rounds = round_no
            before_title = item.title or ""
            before_body = item.body or ""
            try:
                input_payload = _rewrite_input_payload(
                    item,
                    hits=current_hits,
                    replacements={
                        hit: current_audit.replacements[hit]
                        for hit in current_hits
                        if hit in current_audit.replacements
                    },
                    content_type=content_type,
                    rewrite_round=round_no,
                )
                input_payload.update(
                    await ContentGenerationExpertService(self.db).build_rewrite_snapshot(
                        content_type=content_type,
                        previous_content=input_payload["previous_content"],
                        business_rule=input_payload["business_rule"],
                        selected_keywords=input_payload["selected_keywords"],
                        forbidden_hits=current_hits,
                        forbidden_replacements=input_payload["forbidden_replacements"],
                        rewrite_instructions=input_payload["rewrite_instructions"],
                        output_fields=input_payload["output_fields"],
                    )
                )
                model_config_override = _rewrite_model_config_for_hits(current_audit, current_hits)
                if model_config_override:
                    input_payload["model_config"] = {
                        **dict(input_payload.get("model_config") or {}),
                        **model_config_override,
                    }
                if any(current_audit.enforcements.get(hit) == "model_rewrite" for hit in current_hits):
                    input_payload["rewrite_source"] = "business_forbidden_term_policy"
                result = await orchestrator.run_content_rewrite_stage(
                    run_id=item.run_id,
                    executor_code=executor_code,
                    input_payload=input_payload,
                )
                _apply_rewrite_output(item, result.output or {}, content_type=content_type)
                preservation_error = _rewrite_preservation_error(
                    asset_key=asset_key,
                    before_title=before_title,
                    before_body=before_body,
                    after_title=item.title or "",
                    after_body=item.body or "",
                )
                if preservation_error:
                    item.title = before_title
                    item.body = before_body
                    last_error = preservation_error
                    rewrite_method = "content.rewrite_rejected"
                    continue
                rewrite_method = "content.rewrite"
            except Exception as exc:  # noqa: BLE001 - keep review controlled even if worker rewrite fails
                item.title = before_title
                item.body = before_body
                last_error = str(exc)
                rewrite_method = "content.rewrite_error"
                continue

            post_audit = await self.audit_text(asset_key=asset_key, title=item.title, body=item.body)
            residual_model_hits = [
                hit for hit in post_audit.hits if post_audit.enforcements.get(hit) == "model_rewrite"
            ]
            if residual_model_hits:
                item.title = before_title
                item.body = before_body
                last_error = f"content.rewrite still contains model_rewrite terms: {'、'.join(residual_model_hits)}"
                rewrite_method = "content.rewrite_rejected"
                continue

            residual_legacy_hits = [hit for hit in post_audit.hits if not post_audit.enforcements.get(hit)]
            if residual_legacy_hits:
                item.title = _remove_or_replace_forbidden_terms(item.title or "", residual_legacy_hits, post_audit.replacements)
                item.body = _remove_or_replace_forbidden_terms(item.body or "", residual_legacy_hits, post_audit.replacements)
                rewrite_method = f"{rewrite_method}+deterministic_sanitize"
            current_hits = (await self.audit_text(asset_key=asset_key, title=item.title, body=item.body)).hits
            if not current_hits:
                break

        final_audit = await self.audit_text(asset_key=asset_key, title=item.title, body=item.body)
        current_hits = final_audit.hits
        review_payload = _review_payload(
            initial_hits=initial_hits,
            final_hits=current_hits,
            rewrite_rounds=rewrite_rounds,
            rewrite_method=rewrite_method,
            last_error=last_error,
            term_reasons=initial_term_reasons,
            term_enforcements=initial_enforcements,
        )
        quality = _quality_with_forbidden_review(item.quality_json or {}, review_payload)
        item.quality_json = quality
        return review_payload


def find_forbidden_hits(text: str, terms: list[str] | None = None) -> list[str]:
    hits: list[str] = []
    checked_text = _mask_allowed_proprietary_terms(text)
    for term in terms or STATIC_FORBIDDEN_TERMS:
        if term and term in checked_text and term not in hits:
            hits.append(term)
    # 重叠禁词需要先处理长词，避免兜底清理时短词先删掉后留下怪碎片。
    return sorted(hits, key=len, reverse=True)


def _business_entry_matches(text: str, entry: dict[str, Any]) -> bool:
    term = str(entry.get("term") or "")
    if not term or term not in text:
        return False
    match_mode = str(entry.get("match_mode") or "literal")
    if match_mode == "activity_prize_context":
        return _matches_activity_prize_context(text, term)
    if match_mode == "detection_page_context":
        return _matches_detection_page_context(text, term)
    if match_mode == "risk_polarity_context":
        return _matches_risk_polarity_context(text, term)
    return True


def _matches_activity_prize_context(text: str, term: str) -> bool:
    sentences = re.split(r"[\n。！？!?；;]", text)
    for index, sentence in enumerate(sentences):
        if term not in sentence:
            continue
        if any(
            cue in sentence
            for cue in (
                "奖品",
                "礼品",
                "兑换",
                "换到",
                "换个",
                "换一",
                "抽奖",
                "中奖",
                "集罐",
                "能领",
                "可以领",
                "活动送",
                "活动有",
                "福利有",
            )
        ):
            return True
        prefix = sentence.split(term, 1)[0]
        previous = next(
            (candidate for candidate in reversed(sentences[:index]) if candidate.strip()),
            "",
        )
        if (
            any(marker in prefix[-12:] for marker in ("什么", "还有", "包括", "比如", "像"))
            and any(
                cue in previous
                for cue in ("奖品", "礼品", "兑换", "换到", "换个", "换一", "能换", "可以换")
            )
        ):
            return True
    return False


def _matches_detection_page_context(text: str, term: str) -> bool:
    for sentence in re.split(r"[\n。！？!?；;]", text):
        if term in sentence and any(marker in sentence for marker in ("每批", "批批", "检测")):
            return True
    return False


def _matches_risk_polarity_context(text: str, term: str) -> bool:
    allowed_negated_pattern = re.compile(
        rf"(?:完全|根本|并|也|真心|亲测|闭眼入)?"
        rf"(?:不|没|没有|不会|不太会|不容易|从没|从来没|从未|不算|算不上|谈不上)"
        rf"(?:再)?{re.escape(term)}"
    )
    for sentence in re.split(r"[\n。！？!?；;]", text):
        if term not in sentence:
            continue
        remaining = allowed_negated_pattern.sub("", sentence)
        if term in remaining:
            return True
    return False


def _rewrite_model_config_for_hits(audit: ForbiddenTermAuditResult, hits: list[str]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for hit in hits:
        merged.update(audit.rewrite_model_configs.get(hit) or {})
    return merged


def _rewrite_preservation_error(
    *,
    asset_key: str | None,
    before_title: str,
    before_body: str,
    after_title: str,
    after_body: str,
) -> str | None:
    if asset_key != A2_REIYU_UGC_POST_ASSET_KEY:
        return None
    before = _text(before_title, before_body)
    after = _text(after_title, after_body)
    required_exact_markers = (
        "a2至初",
        "会员",
        "积分",
        "集罐",
        "抽奖",
        "回馈礼",
        "老客",
        "3罐",
        "6罐",
        "12罐",
        "18罐",
    )
    missing = [marker for marker in required_exact_markers if marker in before and marker not in after]
    protected_source_groups = (
        ("宝爸来源", ("宝爸", "爸爸", "孩子爸")),
        ("闺蜜或朋友来源", ("闺蜜", "朋友", "同事")),
        ("导购或门店来源", ("导购", "店员", "门店", "店里")),
        ("群聊来源", ("宝妈群", "妈妈群", "群里")),
        ("线上刷到来源", ("刷到", "看到", "线上看到", "网上看到")),
        ("他人告知来源", ("说", "跟我说", "告诉我", "发给我", "发来", "甩了个链接")),
    )
    for label, markers in protected_source_groups:
        if any(marker in before for marker in markers) and not any(marker in after for marker in markers):
            missing.append(label)
    if "检测" in before and "检测" not in after:
        missing.append("检测信息")
    if any(marker in before for marker in ("每批", "批批")) and not any(
        marker in after for marker in ("每批", "批批")
    ):
        missing.append("每批检测口径")
    if missing:
        return f"content.rewrite dropped protected facts: {'、'.join(dict.fromkeys(missing))}"
    return None


def _mask_allowed_proprietary_terms(text: str) -> str:
    masked = str(text or "")
    for term, placeholder in ALLOWED_PROPRIETARY_TERMS.items():
        masked = masked.replace(term, placeholder)
    return masked


def _static_forbidden_terms_for_asset(asset_key: str | None) -> list[str]:
    terms = list(STATIC_FORBIDDEN_TERMS)
    if asset_key == A2_REIYU_UGC_POST_ASSET_KEY:
        terms = [term for term in terms if term not in STATIC_MEDICAL_FORBIDDEN_TERMS]
    if _is_wangyue_asset(asset_key):
        terms.extend(WANGYUE_STATIC_FORBIDDEN_TERMS)
    return terms


def _static_forbidden_replacements_for_asset(asset_key: str | None) -> dict[str, str]:
    replacements = dict(STATIC_FORBIDDEN_REPLACEMENTS)
    if _is_wangyue_asset(asset_key):
        replacements.update(WANGYUE_STATIC_FORBIDDEN_REPLACEMENTS)
    return replacements


def _static_forbidden_term_reasons_for_asset(asset_key: str | None) -> dict[str, str]:
    if _is_wangyue_asset(asset_key):
        return dict(WANGYUE_STATIC_FORBIDDEN_TERM_REASONS)
    return {}


def _static_block_only_terms_for_asset(asset_key: str | None) -> set[str]:
    if _is_wangyue_asset(asset_key):
        return set(WANGYUE_STATIC_BLOCK_ONLY_TERMS)
    return set()


def _is_wangyue_asset(asset_key: str | None) -> bool:
    normalized = str(asset_key or "").lower()
    return normalized.startswith("wangyue_") or "wangyue" in normalized


def _quality_with_forbidden_review(quality_json: dict[str, Any], review_payload: dict[str, Any]) -> dict[str, Any]:
    quality = dict(quality_json or {})
    review_report = dict(quality.get("review_report") or {})
    hard_results = _hard_results_with_forbidden_guard(review_report.get("hard_results") or [], review_payload)
    review_report.update(
        {
            "hard_results": hard_results,
            "forbidden_terms_review": review_payload,
            "rewrite_required": bool(review_report.get("rewrite_required")) or bool(review_payload["final_hits"]),
            "rewrite_rounds": max(int(review_report.get("rewrite_rounds") or 0), int(review_payload["rewrite_rounds"] or 0)),
        }
    )
    if review_payload["initial_hits"]:
        if review_payload.get("rewrite_method") == "audit_only":
            review_report["rewrite_reason"] = f"命中违禁词：{'、'.join(review_payload['final_hits'])}，仅审核不改写"
        elif review_payload.get("rewrite_method") in {"block_only", "hard_ban"}:
            review_report["rewrite_reason"] = f"命中硬违禁词：{'、'.join(review_payload['final_hits'])}，直接阻断，不改写"
        elif str(review_payload.get("rewrite_method") or "").endswith("model_rewrite_disabled"):
            review_report["rewrite_reason"] = (
                f"命中违禁词：{'、'.join(review_payload['final_hits'])}，"
                "生产不做模型改写，转人工或实验处理"
            )
        else:
            review_report["rewrite_reason"] = (
                f"命中违禁词已自动改写：{'、'.join(review_payload['initial_hits'])}"
                if not review_payload["final_hits"]
                else f"命中违禁词：{'、'.join(review_payload['final_hits'])}，自动改写后仍需人工处理"
            )
    quality["review_report"] = review_report
    quality["forbidden_terms_review"] = review_payload
    existing_hard_pass = quality.get("hard_pass")
    forbidden_pass = not review_payload["final_hits"]
    quality["hard_pass"] = forbidden_pass if existing_hard_pass is None else bool(existing_hard_pass and forbidden_pass)
    return quality


def _hard_results_with_forbidden_guard(
    hard_results: list[Any],
    review_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    normalized = [dict(item) for item in hard_results if isinstance(item, dict) and item.get("ae_code") != "forbidden_terms_guard"]
    if not review_payload["initial_hits"]:
        return normalized
    normalized.append(
        {
            "ae_code": "forbidden_terms_guard",
            "pass": not review_payload["final_hits"],
            "risk_level": "high",
            "feedback": _forbidden_feedback(review_payload),
            "evidence": review_payload["final_hits"] or review_payload["initial_hits"],
        }
    )
    return normalized


def _forbidden_feedback(review_payload: dict[str, Any]) -> str:
    if review_payload.get("rewrite_method") == "audit_only":
        return f"命中违禁词，仅审核不改写：{'、'.join(review_payload['final_hits'])}"
    if review_payload.get("rewrite_method") in {"block_only", "hard_ban"}:
        return f"命中硬违禁词，直接阻断不改写：{'、'.join(review_payload['final_hits'])}"
    if str(review_payload.get("rewrite_method") or "").endswith("model_rewrite_disabled"):
        return f"命中违禁词，生产不做模型改写：{'、'.join(review_payload['final_hits'])}"
    if not review_payload["final_hits"]:
        return f"命中违禁词已自动改写：{'、'.join(review_payload['initial_hits'])}"
    return f"自动改写后仍命中违禁词：{'、'.join(review_payload['final_hits'])}"


def _review_payload(
    *,
    initial_hits: list[str],
    final_hits: list[str],
    rewrite_rounds: int,
    rewrite_method: str,
    last_error: str | None = None,
    term_reasons: dict[str, str] | None = None,
    term_enforcements: dict[str, str] | None = None,
    blocking_hits: list[str] | None = None,
) -> dict[str, Any]:
    payload = {
        "source": "maga_forbidden_term_review",
        "pass": not final_hits,
        "initial_hits": initial_hits,
        "final_hits": final_hits,
        "rewrite_required": bool(final_hits),
        "rewrite_rounds": rewrite_rounds,
        "rewrite_method": rewrite_method,
        "term_reasons": term_reasons or {},
        "term_enforcements": term_enforcements or {},
    }
    if blocking_hits:
        payload["blocking_hits"] = blocking_hits
    if last_error:
        payload["last_error"] = last_error
    return payload


def _rewrite_input_payload(
    item: ContentBatchItem,
    *,
    hits: list[str],
    replacements: dict[str, str],
    content_type: str,
    rewrite_round: int,
) -> dict[str, Any]:
    previous_content = (
        {"comment": item.body or ""}
        if content_type == "comment"
        else {"title": item.title or "", "body": item.body or ""}
    )
    instructions = [
        f"必须删除或替换这些违禁词：{'、'.join(hits)}",
        "只处理命中的词和相关句子，尽量保留原意、语气和业务规则",
        "改写后不得再次出现上述违禁词",
        "不要解释改写过程，只返回改写后的内容",
    ]
    if replacements:
        # 重要逻辑：把符号/emoji 这类模型易忽略的替换规则从长生文 prompt 中拆出来，
        # 在短改写 prompt 里用明确映射约束，提升 🍼 -> 奶瓶 这类替换稳定性。
        instructions.insert(
            1,
            "指定替换映射：" + "；".join(f"{term} -> {replacement}" for term, replacement in replacements.items()),
        )
    return {
        "previous_content": previous_content,
        "content_type": content_type,
        "output_fields": ["comment"] if content_type == "comment" else ["title", "body"],
        "business_rule": (
            rewrite_business_rule_context(item.plan_json)
            if content_type == "article"
            else dict(item.plan_json or {})
        ),
        "selected_keywords": _selected_keywords_from_item(item),
        "forbidden_hits": hits,
        "forbidden_replacements": replacements,
        "review_report": {
            "hard_results": [
                {
                    "ae_code": "forbidden_terms_guard",
                    "pass": False,
                    "risk_level": "high",
                    "feedback": f"命中违禁词：{'、'.join(hits)}",
                    "evidence": hits,
                }
            ],
            "soft_scores": [],
            "failed_aes": [],
            "forbidden_terms_review": {"hits": hits},
            "rewrite_required": True,
            "rewrite_reason": f"删除或替换违禁词：{'、'.join(hits)}",
        },
        "rewrite_round": rewrite_round,
        "rewrite_instructions": instructions,
    }


def _apply_rewrite_output(item: ContentBatchItem, output: dict[str, Any], *, content_type: str) -> None:
    if content_type == "comment":
        comment = str(output.get("comment") or "").strip()
        if not comment:
            raise ValueError("content.rewrite returned empty comment")
        item.body = comment
        return

    final = output.get("final") if isinstance(output.get("final"), dict) else {}
    title = str(output.get("title") or final.get("title") or "").strip()
    body = str(output.get("body") or final.get("body") or "").strip()
    if not title and not body:
        raise ValueError("content.rewrite returned empty article")
    if title:
        item.title = title
    if body:
        item.body = body


def _selected_keywords_from_item(item: ContentBatchItem) -> list[Any]:
    plan = item.plan_json or {}
    unified = plan.get("unified_generation") if isinstance(plan, dict) else {}
    if isinstance(unified, dict) and isinstance(unified.get("selected_keywords"), list):
        return unified["selected_keywords"]
    quality = item.quality_json or {}
    if isinstance(quality, dict) and isinstance(quality.get("selected_keywords"), list):
        return quality["selected_keywords"]
    return []


def _remove_or_replace_forbidden_terms(value: str, hits: list[str], replacements: dict[str, str]) -> str:
    text = value
    removed_term = False
    for term in hits:
        replacement = replacements.get(term, "")
        removed_term = removed_term or not replacement
        text = text.replace(term, replacement)
    return _normalize_text_after_removal(text) if removed_term else text


def _normalize_text_after_removal(value: str) -> str:
    text = value
    while "  " in text:
        text = text.replace("  ", " ")
    for duplicate in ["、、", "，，", "。。", "～～", "，，", "；；"]:
        while duplicate in text:
            text = text.replace(duplicate, duplicate[0])
    return text.strip(" ，。；、")


def _text(title: str | None, body: str | None) -> str:
    return f"{title or ''}\n{body or ''}"
