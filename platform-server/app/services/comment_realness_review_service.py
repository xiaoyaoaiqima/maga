"""Comment realness review and rewrite guard."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.content_agent import ContentBatchItem
from app.services.content_agent_orchestrator import ContentAgentOrchestrator
from app.services.content_generation_expert_service import ContentGenerationExpertService

MAX_COMMENT_REALNESS_REWRITE_ROUNDS = 2

STATIC_COMMENT_REALNESS_REPLACEMENTS: dict[str, str] = {
    "换季必病": "以前总容易病",
    "换季没中招": "最近没中招",
    "换季那阵子": "前阵子",
    "换季": "最近这阵子",
    "老母亲": "当妈的",
    "谁懂啊": "懂的都懂",
    "🍼": "",
    "同款稳": "同款，少折腾",
    "拉得挺顺畅": "拉的时候没那么费劲",
    "拉得顺畅": "拉的时候没那么费劲",
    "拉起来顺": "拉的时候没那么费劲",
    "拉得顺": "拉的时候没那么费劲",
    "拉屎顺": "拉的时候没那么费劲",
    "拉粑粑顺": "拉的时候没那么费劲",
    "便便顺畅": "便便没那么费劲",
    "便便挺顺": "便便没那么费劲",
    "便便顺": "便便没那么费劲",
    "挺顺畅": "没那么费劲",
    "挺顺": "没那么费劲",
    "顺多了": "没那么费劲",
    "顺畅": "没那么费劲",
    "喝得顺": "喝得下去",
    "喝的顺": "喝得下去",
    "金黄糊糊": "金黄色糊糊",
    "金黄软": "金黄色，软软的",
    "黄软便": "黄黄软软的便便",
    "黄软": "黄黄软软",
    "没抗拒": "喝了几口",
    "没拒绝": "喝了几口",
    "娃没躲": "娃喝得挺痛快",
    "能接受": "还行",
    "接受度": "喝奶反应",
    "接得住": "愿意接着喝",
    "承接住": "愿意接着喝",
    "能接几口": "愿意喝几口",
    "接几口": "喝几口",
    "能接": "愿意喝",
    "接上": "接着喝",
    "接住": "接着喝",
    "转奶头": "转奶",
    "换奶头": "换奶",
    "小量试": "奶量少一点试",
    "少冲": "奶量少一点",
    "冲少": "奶量少一点",
    "闻一口": "喝几口",
    "第一口能喝进去几口": "第一口愿意喝几口",
    "没犹豫": "愿意喝几口",
    "喝得挺利索": "喝得挺痛快",
    "加量挺痛快": "奶量没掉",
    "挺安稳": "没怎么闹",
    "挺稳": "还可以",
    "便便节奏挺稳": "便便次数还可以",
    "软硬也稳": "软硬也还行",
    "便便也稳": "便便还可以",
    "状态也稳": "状态还可以",
    "继续观察中": "再看看",
    "翻尿布": "看纸尿裤",
    "白粒": "奶瓣",
}

# 重要逻辑：这些不是风险禁词，而是评论真人感的旧雷。
# 单独维护可以避免后续“风险治理”和“口语质量治理”互相污染。
STATIC_COMMENT_REALNESS_TERMS: list[str] = [
    *STATIC_COMMENT_REALNESS_REPLACEMENTS.keys(),
    "接得住",
    "接住",
    "接上",
    "能接",
    "接几口",
    "承接住",
    "没抗拒",
    "没拒绝",
    "娃没躲",
    "能接受",
    "接受度",
    "黄软便",
    "金黄软",
    "黄软",
    "金黄糊糊",
    "顺畅",
    "挺顺",
    "挺稳",
    "转奶头",
    "换奶头",
    "小量试",
    "少冲",
    "冲少",
    "老母亲",
    "谁懂啊",
    "🍼",
    "同款稳",
]


@dataclass(frozen=True)
class CommentRealnessAuditResult:
    terms: list[str]
    hits: list[str]
    replacements: dict[str, str]


class CommentRealnessReviewService:
    """MAGA-side guard for AI-ish comment wording before operator review."""

    async def audit_text(
        self,
        *,
        title: str | None,
        body: str | None,
    ) -> CommentRealnessAuditResult:
        terms = _unique_terms(STATIC_COMMENT_REALNESS_TERMS)
        hits = find_comment_realness_hits(_text(title, body), terms)
        return CommentRealnessAuditResult(
            terms=terms,
            hits=hits,
            replacements={hit: STATIC_COMMENT_REALNESS_REPLACEMENTS[hit] for hit in hits if hit in STATIC_COMMENT_REALNESS_REPLACEMENTS},
        )

    async def review_and_rewrite_item(
        self,
        *,
        item: ContentBatchItem,
        orchestrator: ContentAgentOrchestrator | None,
        executor_code: str | None,
        max_rounds: int = MAX_COMMENT_REALNESS_REWRITE_ROUNDS,
    ) -> dict[str, Any]:
        audit = await self.audit_text(title=item.title, body=item.body)
        if not audit.hits:
            review_payload = _review_payload(
                initial_hits=[],
                final_hits=[],
                rewrite_rounds=0,
                rewrite_method="none",
            )
            item.quality_json = _quality_with_realness_review(item.quality_json or {}, review_payload)
            return review_payload

        initial_hits = list(audit.hits)
        rewrite_rounds = 0
        rewrite_method = "none"
        last_error: str | None = None
        current_hits = initial_hits
        current_replacements = dict(audit.replacements)
        for round_no in range(1, max_rounds + 1):
            rewrite_rounds = round_no
            try:
                if item.run_id and orchestrator is not None:
                    input_payload = _rewrite_input_payload(
                        item,
                        hits=current_hits,
                        replacements={hit: current_replacements[hit] for hit in current_hits if current_replacements.get(hit)},
                        rewrite_round=round_no,
                    )
                    input_payload.update(
                        await ContentGenerationExpertService(orchestrator.db).build_rewrite_snapshot(
                            content_type="comment",
                            previous_content=input_payload["previous_content"],
                            business_rule=input_payload["business_rule"],
                            selected_keywords=input_payload["selected_keywords"],
                            forbidden_hits=[],
                            forbidden_replacements={},
                            rewrite_instructions=input_payload["rewrite_instructions"],
                            output_fields=input_payload["output_fields"],
                        )
                    )
                    _loosen_realness_rewrite_model(input_payload)
                    result = await orchestrator.run_content_rewrite_stage(
                        run_id=item.run_id,
                        executor_code=executor_code,
                        input_payload=input_payload,
                    )
                    _apply_rewrite_output(item, result.output or {})
                    rewrite_method = "content.rewrite"
                else:
                    rewrite_method = "deterministic_sanitize"
            except Exception as exc:  # noqa: BLE001 - keep comment review deterministic on worker failure
                last_error = str(exc)
                rewrite_method = "deterministic_sanitize_after_error"

            post_audit = await self.audit_text(title=item.title, body=item.body)
            if post_audit.hits:
                item.body = _remove_or_replace_realness_terms(item.body or "", post_audit.hits, post_audit.replacements)
                rewrite_method = (
                    f"{rewrite_method}+deterministic_sanitize"
                    if "deterministic_sanitize" not in rewrite_method
                    else rewrite_method
                )
                post_audit = await self.audit_text(title=item.title, body=item.body)
            current_hits = post_audit.hits
            current_replacements = post_audit.replacements
            if not current_hits:
                break

        review_payload = _review_payload(
            initial_hits=initial_hits,
            final_hits=current_hits,
            rewrite_rounds=rewrite_rounds,
            rewrite_method=rewrite_method,
            last_error=last_error,
        )
        item.quality_json = _quality_with_realness_review(item.quality_json or {}, review_payload)
        return review_payload


def find_comment_realness_hits(text: str, terms: list[str] | None = None) -> list[str]:
    hits: list[str] = []
    for term in terms or STATIC_COMMENT_REALNESS_TERMS:
        if term and term in text and term not in hits:
            hits.append(term)
    return sorted(hits, key=len, reverse=True)


def _rewrite_input_payload(
    item: ContentBatchItem,
    *,
    hits: list[str],
    replacements: dict[str, str],
    rewrite_round: int,
) -> dict[str, Any]:
    instructions = [
        f"命中这些AI感或不口语表达：{'、'.join(hits)}",
        "这不是风控替换，要按评论区真人说法重写命中句，不要只做同义词替换",
        "优先换成一个具体小事实、动作或观察，比如拉的时候没那么费劲、喝得挺痛快、愿意喝几口",
        "改写后不要再出现上述命中表达",
        "只输出一条评论正文，不要解释改写过程",
    ]
    if replacements:
        instructions.insert(
            1,
            "可参考替代表达：" + "；".join(f"{term} -> {replacement}" for term, replacement in replacements.items()),
        )
    return {
        "previous_content": {"comment": item.body or ""},
        "content_type": "comment",
        "output_fields": ["comment"],
        "business_rule": dict(item.plan_json or {}),
        "selected_keywords": _selected_keywords_from_item(item),
        "forbidden_hits": [],
        "forbidden_replacements": {},
        "style_hits": hits,
        "style_replacements": replacements,
        "rewrite_source": "comment_realness_review",
        "review_report": {
            "hard_results": [
                {
                    "ae_code": "comment_realness_guard",
                    "pass": False,
                    "risk_level": "medium",
                    "feedback": f"命中AI感表达：{'、'.join(hits)}",
                    "evidence": hits,
                }
            ],
            "soft_scores": [],
            "failed_aes": [],
            "comment_realness_review": {"hits": hits},
            "rewrite_required": True,
            "rewrite_reason": f"真人感改写：{'、'.join(hits)}",
        },
        "rewrite_round": rewrite_round,
        "rewrite_instructions": instructions,
    }


def _quality_with_realness_review(quality_json: dict[str, Any], review_payload: dict[str, Any]) -> dict[str, Any]:
    quality = dict(quality_json or {})
    review_report = dict(quality.get("review_report") or {})
    hard_results = _hard_results_with_realness_guard(review_report.get("hard_results") or [], review_payload)
    previous_rounds = int(review_report.get("rewrite_rounds") or 0)
    review_report.update(
        {
            "hard_results": hard_results,
            "comment_realness_review": review_payload,
            "rewrite_required": bool(review_report.get("rewrite_required")) or bool(review_payload["final_hits"]),
            "rewrite_rounds": max(previous_rounds, int(review_payload["rewrite_rounds"] or 0)),
        }
    )
    if review_payload["initial_hits"]:
        review_report["rewrite_reason"] = (
            f"命中AI感表达已自动改写：{'、'.join(review_payload['initial_hits'])}"
            if not review_payload["final_hits"]
            else f"命中AI感表达：{'、'.join(review_payload['final_hits'])}，自动改写后仍需人工处理"
        )
    quality["review_report"] = review_report
    quality["comment_realness_review"] = review_payload
    existing_hard_pass = quality.get("hard_pass")
    realness_pass = not review_payload["final_hits"]
    quality["hard_pass"] = realness_pass if existing_hard_pass is None else bool(existing_hard_pass and realness_pass)
    return quality


def _hard_results_with_realness_guard(
    hard_results: list[Any],
    review_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    normalized = [dict(item) for item in hard_results if isinstance(item, dict) and item.get("ae_code") != "comment_realness_guard"]
    if not review_payload["initial_hits"]:
        return normalized
    normalized.append(
        {
            "ae_code": "comment_realness_guard",
            "pass": not review_payload["final_hits"],
            "risk_level": "medium",
            "feedback": (
                f"命中AI感表达已自动改写：{'、'.join(review_payload['initial_hits'])}"
                if not review_payload["final_hits"]
                else f"自动改写后仍命中AI感表达：{'、'.join(review_payload['final_hits'])}"
            ),
            "evidence": review_payload["final_hits"] or review_payload["initial_hits"],
        }
    )
    return normalized


def _review_payload(
    *,
    initial_hits: list[str],
    final_hits: list[str],
    rewrite_rounds: int,
    rewrite_method: str,
    last_error: str | None = None,
) -> dict[str, Any]:
    payload = {
        "source": "maga_comment_realness_review",
        "pass": not final_hits,
        "initial_hits": initial_hits,
        "final_hits": final_hits,
        "rewrite_required": bool(final_hits),
        "rewrite_rounds": rewrite_rounds,
        "rewrite_method": rewrite_method,
    }
    if last_error:
        payload["last_error"] = last_error
    return payload


def _loosen_realness_rewrite_model(input_payload: dict[str, Any]) -> None:
    model_config = dict(input_payload.get("model_config") or {})
    temperature = model_config.get("temperature")
    try:
        current_temperature = float(temperature)
    except (TypeError, ValueError):
        current_temperature = 0.0
    model_config["temperature"] = max(current_temperature, 0.72)
    input_payload["model_config"] = model_config


def _apply_rewrite_output(item: ContentBatchItem, output: dict[str, Any]) -> None:
    final = output.get("final") if isinstance(output.get("final"), dict) else {}
    comment = str(output.get("comment") or final.get("comment") or output.get("body") or final.get("body") or "").strip()
    if not comment:
        raise ValueError("content.rewrite returned empty comment")
    item.body = comment


def _remove_or_replace_realness_terms(value: str, hits: list[str], replacements: dict[str, str]) -> str:
    text = value
    for term in hits:
        text = text.replace(term, replacements.get(term, ""))
    return _normalize_text_after_removal(text)


def _normalize_text_after_removal(value: str) -> str:
    text = value
    while "  " in text:
        text = text.replace("  ", " ")
    for before, after in [
        ("金黄黄软软", "金黄色软软"),
        ("金黄黄的，软一点软的", "金黄色软软的"),
        ("黄黄黄的，软一点软的", "黄黄软软的"),
        ("黄黄的，软一点软的", "黄黄软软的"),
        ("软一点软的", "软软的"),
        ("黄黄黄", "黄黄"),
    ]:
        text = text.replace(before, after)
    for duplicate in ["、、", "，，", "。。", "～～", "；；"]:
        while duplicate in text:
            text = text.replace(duplicate, duplicate[0])
    return text.strip(" ，。；、")


def _selected_keywords_from_item(item: ContentBatchItem) -> list[Any]:
    plan = item.plan_json or {}
    unified = plan.get("unified_generation") if isinstance(plan, dict) else {}
    if isinstance(unified, dict) and isinstance(unified.get("selected_keywords"), list):
        return unified["selected_keywords"]
    quality = item.quality_json or {}
    if isinstance(quality, dict) and isinstance(quality.get("selected_keywords"), list):
        return quality["selected_keywords"]
    return []


def _unique_terms(terms: list[str]) -> list[str]:
    result: list[str] = []
    for term in terms:
        if term and term not in result:
            result.append(term)
    return result


def _text(title: str | None, body: str | None) -> str:
    return f"{title or ''}\n{body or ''}"
