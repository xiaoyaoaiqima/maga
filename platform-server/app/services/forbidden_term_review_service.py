"""Deterministic forbidden-term review and controlled rewrite flow."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content_agent import ContentBatchItem
from app.services.business_forbidden_term_service import BusinessForbiddenTermService
from app.services.content_agent_orchestrator import ContentAgentOrchestrator
from app.services.content_generation_expert_service import ContentGenerationExpertService
from app.services.content_rewrite_context import rewrite_business_rule_context

STATIC_FORBIDDEN_REPLACEMENTS = {"肠胃": "肚肚"}
WANGYUE_STATIC_FORBIDDEN_REPLACEMENTS = {
    "体质": "状态",
    "脾胃": "肚肚状态",
}
WANGYUE_STATIC_BLOCK_ONLY_TERMS = {"底气"}
STATIC_FORBIDDEN_TERMS = [
    "治疗便秘",
    "治好便秘",
    "改善便秘",
    "解决便秘",
    "根治",
    "疗效",
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
    "4段",
    "源乳",
    "初乳",
    "换季",
    "流感",
    "秋游",
    "春游",
]
WANGYUE_STATIC_FORBIDDEN_TERM_REASONS = {
    "4段": "旺玥不是4段奶粉，品牌定位是儿童奶粉；不能把旺玥和4段奶粉放在一起关联。",
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
        terms = await self.list_terms(asset_key=asset_key)
        replacements = {
            **_static_forbidden_replacements_for_asset(asset_key),
            **(await term_service.list_replacements(asset_key=asset_key)),
        }
        hits = find_forbidden_hits(_text(title, body), terms)
        term_reasons = _static_forbidden_term_reasons_for_asset(asset_key)
        return ForbiddenTermAuditResult(
            terms=terms,
            hits=hits,
            replacements={hit: replacements[hit] for hit in hits if replacements.get(hit)},
            term_reasons={hit: term_reasons[hit] for hit in hits if term_reasons.get(hit)},
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
            )
            item.quality_json = quality
            return quality["forbidden_terms_review"]

        initial_hits = list(audit.hits)
        block_only_hits = [hit for hit in initial_hits if hit in _static_block_only_terms_for_asset(asset_key)]
        if block_only_hits:
            review_payload = _review_payload(
                initial_hits=initial_hits,
                final_hits=block_only_hits,
                rewrite_rounds=0,
                rewrite_method="block_only",
                term_reasons={hit: audit.term_reasons[hit] for hit in initial_hits if audit.term_reasons.get(hit)},
            )
            quality = _quality_with_forbidden_review(item.quality_json or {}, review_payload)
            item.quality_json = quality
            return review_payload

        rewrite_rounds = 0
        rewrite_method = "none"
        last_error: str | None = None
        current_hits = initial_hits
        for round_no in range(1, max_rounds + 1):
            rewrite_rounds = round_no
            try:
                if item.run_id and orchestrator is not None:
                    input_payload = _rewrite_input_payload(
                        item,
                        hits=current_hits,
                        replacements={hit: audit.replacements[hit] for hit in current_hits if audit.replacements.get(hit)},
                        content_type=content_type,
                        rewrite_round=round_no,
                    )
                    # 改写是否触发、命中词扫描和兜底清理由 MAGA 控制；
                    # Expert 只负责把本轮改写的 prompt 模板和模型参数交给 worker。
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
                    result = await orchestrator.run_content_rewrite_stage(
                        run_id=item.run_id,
                        executor_code=executor_code,
                        input_payload=input_payload,
                    )
                    _apply_rewrite_output(item, result.output or {}, content_type=content_type)
                    rewrite_method = "content.rewrite"
                else:
                    rewrite_method = "deterministic_sanitize"
            except Exception as exc:  # noqa: BLE001 - keep review controlled even if worker rewrite fails
                last_error = str(exc)
                rewrite_method = "deterministic_sanitize_after_error"

            post_audit = ForbiddenTermAuditResult(
                terms=audit.terms,
                hits=find_forbidden_hits(_text(item.title, item.body), audit.terms),
                replacements={},
                term_reasons={},
            )
            if post_audit.hits:
                item.title = _remove_or_replace_forbidden_terms(item.title or "", post_audit.hits, audit.replacements)
                item.body = _remove_or_replace_forbidden_terms(item.body or "", post_audit.hits, audit.replacements)
                rewrite_method = (
                    f"{rewrite_method}+deterministic_sanitize"
                    if "deterministic_sanitize" not in rewrite_method
                    else rewrite_method
                )
                post_audit = ForbiddenTermAuditResult(
                    terms=audit.terms,
                    hits=find_forbidden_hits(_text(item.title, item.body), audit.terms),
                    replacements={},
                    term_reasons={},
                )
            current_hits = post_audit.hits
            if not current_hits:
                break

        review_payload = _review_payload(
            initial_hits=initial_hits,
            final_hits=current_hits,
            rewrite_rounds=rewrite_rounds,
            rewrite_method=rewrite_method,
            last_error=last_error,
            term_reasons={hit: audit.term_reasons[hit] for hit in initial_hits if audit.term_reasons.get(hit)},
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


def _mask_allowed_proprietary_terms(text: str) -> str:
    masked = str(text or "")
    for term, placeholder in ALLOWED_PROPRIETARY_TERMS.items():
        masked = masked.replace(term, placeholder)
    return masked


def _static_forbidden_terms_for_asset(asset_key: str | None) -> list[str]:
    terms = list(STATIC_FORBIDDEN_TERMS)
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
        if review_payload.get("rewrite_method") == "block_only":
            review_report["rewrite_reason"] = f"命中硬违禁词：{'、'.join(review_payload['final_hits'])}，直接阻断，不改写"
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
    if review_payload.get("rewrite_method") == "block_only":
        return f"命中硬违禁词，直接阻断不改写：{'、'.join(review_payload['final_hits'])}"
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
    }
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
    for term in hits:
        text = text.replace(term, replacements.get(term, ""))
    return _normalize_text_after_removal(text)


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
