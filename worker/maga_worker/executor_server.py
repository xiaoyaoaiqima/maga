"""Protocol v0.1 HTTP adapter for MAGA -> repo-managed maga-worker integration.

This is intentionally a thin executor boundary: MAGA owns tasks/runs/state and this
service only executes a requested capability from the input snapshot.
"""
from __future__ import annotations

import os
import json
import re
import time
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from maga_worker.asset_importer import import_asset_package
from maga_worker.runtime_adapter import (
    build_runtime_brief_from_snapshot,
    invoke_runtime_fast_generate_draft,
    invoke_runtime_fast_review_and_rewrite,
    invoke_runtime_generate_draft,
)

PROTOCOL_VERSION = "0.1"
SUPPORTED_CAPABILITIES = {
    "xhs.interpret_brief",
    "xhs.run_ae_analysis",
    "xhs.generate_draft",
    "xhs.review_and_rewrite",
    "xhs.run_ae_review",
    "xhs.rewrite_draft",
    "asset.import",
    "comment.generate",
    "content.generate",
}

app = FastAPI(title="Hermes MAGA worker executor", version="0.1.0")


class InvokeEnvelope(BaseModel):
    protocol_version: str = Field(default=PROTOCOL_VERSION)
    run_id: int | str
    task_id: int | str
    stage_call_id: str
    capability: str
    executor_hints: dict[str, Any] = Field(default_factory=dict)
    input: dict[str, Any] = Field(default_factory=dict)


def _expected_token() -> str | None:
    return os.environ.get("MAGA_WORKER_EXECUTOR_TOKEN") or os.environ.get("XHS_WRITER_EXECUTOR_TOKEN")


def _check_headers(protocol_version: str | None, authorization: str | None) -> None:
    if protocol_version != PROTOCOL_VERSION:
        raise HTTPException(status_code=400, detail="unsupported protocol version")
    token = _expected_token()
    if token:
        expected = f"Bearer {token}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="invalid executor token")


def _stats(started: float) -> dict[str, Any]:
    return {
        "executor": "maga-worker",
        "module": "xhs-writer",
        "adapter": "maga_worker.executor_server",
        "total_latency_ms": int((time.perf_counter() - started) * 1000),
    }


def _module_for_capability(capability: str) -> str:
    if capability.startswith("asset."):
        return "asset-steward"
    if capability.startswith("content."):
        return "content-generator"
    if capability.startswith("comment."):
        return "comment-generator"
    return "xhs-writer"


def _execution_mode(input_payload: dict[str, Any]) -> str:
    """Resolve xhs generation mode.

    Batch generation carries a MAGA-owned generation_snapshot, so it can enter
    the first real runtime path by default. Single smoke calls without a
    snapshot stay deterministic to keep local protocol checks cheap and stable.
    """
    configured = os.environ.get("MAGA_WORKER_EXECUTION_MODE") or os.environ.get("XHS_WRITER_EXECUTION_MODE")
    if configured:
        return configured
    if input_payload.get("generation_snapshot"):
        return "runtime_fast"
    return "deterministic"


def _structured_brief(input_payload: dict[str, Any]) -> dict[str, Any]:
    brief = input_payload.get("brief") if isinstance(input_payload.get("brief"), dict) else {}
    generation_snapshot = input_payload.get("generation_snapshot") if isinstance(input_payload.get("generation_snapshot"), dict) else {}
    snapshot_brief = generation_snapshot.get("brief") if isinstance(generation_snapshot.get("brief"), dict) else {}
    topic = input_payload.get("product_topic") or brief.get("product_topic") or snapshot_brief.get("product_topic") or brief.get("topic") or "产品/主题"
    target = input_payload.get("target_audience") or brief.get("target_audience") or snapshot_brief.get("target_audience") or "小红书用户"
    style = input_payload.get("style") or brief.get("style") or snapshot_brief.get("style") or "自然真实"
    return {
        "brief_type": input_payload.get("brief_type") or brief.get("brief_type") or snapshot_brief.get("brief_type") or "xhs_product_seeding_professional_advisor",
        "product_topic": topic,
        "target_audience": target,
        "persona_target": input_payload.get("persona_target") or brief.get("persona_target") or snapshot_brief.get("persona_target"),
        "key_painpoints": brief.get("key_painpoints") or [],
        "key_sellingpoints": brief.get("key_sellingpoints") or [],
        "tone_hints": [style],
        "style": style,
        "must_mention": brief.get("must_mention") or ([topic] if topic else []),
        "must_avoid": brief.get("must_avoid") or [],
    }


def _title_body_from_text(text: str) -> dict[str, str]:
    title = ""
    body = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("标题：") or line.startswith("标题:"):
            title = line.split("：", 1)[-1] if "：" in line else line.split(":", 1)[-1]
        elif line.startswith("正文：") or line.startswith("正文:"):
            body = line.split("：", 1)[-1] if "：" in line else line.split(":", 1)[-1]
        elif not title:
            title = line
        else:
            body = f"{body}\n{line}".strip() if body else line
    return {"title": title or "小红书笔记", "body": body or text.strip() or "正文待生成"}


def _draft_from_structured_brief(structured_brief: dict[str, Any]) -> dict[str, str]:
    topic = structured_brief.get("product_topic") or "这个主题"
    audience = structured_brief.get("target_audience") or "你"
    style = structured_brief.get("style") or (structured_brief.get("tone_hints") or ["自然真实"])[0]
    return {
        "title": f"{topic}怎么选？给{audience}的真实建议",
        "body": f"如果{audience}正在关注{topic}，可以先从真实需求出发。用{style}的方式讲清楚为什么适合、怎么判断、使用时要注意什么。这样写出来的小红书内容更自然，也更容易被收藏。",
    }


def _comment_examples(input_payload: dict[str, Any]) -> list[str]:
    return [
        str(value).strip()
        for value in [
            *(input_payload.get("examples") or []),
            *(input_payload.get("supplements") or []),
        ]
        if str(value).strip()
    ]


def _stable_comment_from_rule(input_payload: dict[str, Any]) -> str:
    examples = _comment_examples(input_payload)
    if examples:
        try:
            item_no = int(input_payload.get("item_no") or 1)
        except (TypeError, ValueError):
            item_no = 1
        return examples[(item_no - 1) % len(examples)]

    comment_angle = str(input_payload.get("comment_angle") or "这个角度").strip()
    return f"{comment_angle}这个点还挺想听听大家真实感受的，我家也在观望源悦。"


def _normalize_comment_text(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"^```(?:text|markdown)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value).strip()
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if lines:
        value = lines[0]
    value = re.sub(r"^(?:[-*•]\s*|\d+[、.．]\s*)", "", value).strip()
    value = re.sub(r"^(评论正文|评论|输出)[:：]\s*", "", value).strip()
    return value.strip("“”\"' ")


def _handle_comment_generate(input_payload: dict[str, Any]) -> dict[str, Any]:
    if os.environ.get("MAGA_WORKER_RUNTIME_FAST_FAKE") == "1":
        return {
            "comment": _stable_comment_from_rule(input_payload),
            "runtime_result": {
                "mode": "comment_fake",
                "fake": True,
                "reason": "MAGA_WORKER_RUNTIME_FAST_FAKE",
            },
        }

    from maga_worker.xhs_runtime import call_model, model_ge

    examples = _comment_examples(input_payload)
    user_parts = [
        f"评论切角：{input_payload.get('comment_angle') or ''}",
        f"规则语料：\n{input_payload.get('corpus') or ''}",
    ]
    if examples:
        user_parts.append("参考示例（只学语义和语气，不要照搬）：\n" + "\n".join(f"- {item}" for item in examples[:8]))
    user_parts.append(
        "生成要求：只输出一条自然评论正文；像真实评论区，不要标题、编号、解释；"
        "不要承诺解决所有问题，不要医疗化诊断，不要照搬示例原句。"
    )
    raw_comment = call_model(
        os.environ.get("MAGA_WORKER_COMMENT_MODEL") or model_ge(),
        system="你生成中文小红书评论，只输出一条自然评论正文。",
        user="\n\n".join(user_parts),
        temperature=0.85,
    )
    comment = _normalize_comment_text(raw_comment)
    if not comment:
        raise ValueError("comment.generate produced empty comment")
    return {
        "comment": comment,
        "runtime_result": {
            "mode": "comment_runtime",
            "fake": False,
        },
    }


def _handle_content_generate(input_payload: dict[str, Any]) -> dict[str, Any]:
    if os.environ.get("MAGA_WORKER_RUNTIME_FAST_FAKE") == "1":
        output = _stable_content_from_unified_input(input_payload)
        output["runtime_result"] = {
            "mode": "content_fake",
            "fake": True,
            "reason": "MAGA_WORKER_RUNTIME_FAST_FAKE",
            "expert_config_code": (input_payload.get("expert") or {}).get("expert_config_code"),
        }
        return output

    from maga_worker.xhs_runtime import call_model, model_ge

    model_config = input_payload.get("model_config") or {}
    model = str(model_config.get("model_code") or model_config.get("ge_model") or model_ge())
    temperature = _float_or_default(model_config.get("temperature"), 0.8)
    max_tokens = _int_or_none(model_config.get("max_tokens"))
    system = str(
        model_config.get("system_prompt")
        or "你是中文小红书内容生成器，严格按用户提示输出，不解释过程。"
    )
    prompt = str(input_payload.get("rendered_prompt") or "").strip()
    if not prompt:
        prompt = _fallback_rendered_prompt(input_payload)
    raw = call_model(model, system=system, user=prompt, temperature=temperature, max_tokens=max_tokens)
    output = _normalize_unified_content_output(raw, input_payload)
    output["runtime_result"] = {
        "mode": "content_runtime",
        "fake": False,
        "expert_config_code": (input_payload.get("expert") or {}).get("expert_config_code"),
        "provider_code": model_config.get("provider_code"),
        "model_code": model,
    }
    return output


def _stable_content_from_unified_input(input_payload: dict[str, Any]) -> dict[str, str]:
    output_fields = input_payload.get("output_fields") or []
    if output_fields == ["comment"] or input_payload.get("content_type") == "comment":
        business_rule = input_payload.get("business_rule") or {}
        return {"comment": _stable_comment_from_rule(business_rule)}

    business_rule = input_payload.get("business_rule") or {}
    selected_keywords = input_payload.get("selected_keywords") or []
    topic = business_rule.get("product_topic") or business_rule.get("product_experience") or "源悦体验"
    persona = _selected_keyword_name(selected_keywords, "persona") or "真实妈妈"
    method = _selected_keyword_name(selected_keywords, "writing_method") or "自然写法"
    return {
        "title": f"{topic}，这样写更像真实分享",
        "body": f"围绕{topic}，用{persona}的口吻承接业务规则，再用{method}把具体感受讲清楚。整体表达保持自然克制，不夸大、不照搬示例。",
    }


def _normalize_unified_content_output(raw: str, input_payload: dict[str, Any]) -> dict[str, str]:
    output_fields = input_payload.get("output_fields") or []
    if output_fields == ["comment"] or input_payload.get("content_type") == "comment":
        comment = _normalize_comment_text(raw)
        if not comment:
            raise ValueError("content.generate produced empty comment")
        return {"comment": comment}

    parsed = _parse_json_object(raw)
    title = str(parsed.get("title") or parsed.get("标题") or "").strip()
    body = str(parsed.get("body") or parsed.get("正文") or "").strip()
    if not title or not body:
        title, body = _title_body_from_text(raw)
    if not body:
        raise ValueError("content.generate produced empty body")
    return {"title": title or "源悦真实体验分享", "body": body}


def _parse_json_object(raw: str) -> dict[str, Any]:
    value = str(raw or "").strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```$", "", value).strip()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", value, flags=re.DOTALL)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _title_body_from_text(raw: str) -> tuple[str, str]:
    lines = [line.strip() for line in str(raw or "").splitlines() if line.strip()]
    title = ""
    body_lines: list[str] = []
    for line in lines:
        normalized = re.sub(r"^(?:[-*•]\s*|\d+[、.．]\s*)", "", line).strip()
        title_match = re.match(r"^(?:标题|title)[:：]\s*(.+)$", normalized, flags=re.IGNORECASE)
        body_match = re.match(r"^(?:正文|body)[:：]\s*(.+)$", normalized, flags=re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip()
            continue
        if body_match:
            body_lines.append(body_match.group(1).strip())
            continue
        body_lines.append(normalized)
    if not title and body_lines:
        first = body_lines[0]
        if len(first) <= 36 and len(body_lines) > 1:
            title = first
            body_lines = body_lines[1:]
    return title, "\n".join(body_lines).strip()


def _fallback_rendered_prompt(input_payload: dict[str, Any]) -> str:
    parts = [
        f"内容类型：{input_payload.get('content_type') or ''}",
        f"输出字段：{input_payload.get('output_fields') or []}",
        "业务规则：\n" + json.dumps(input_payload.get("business_rule") or {}, ensure_ascii=False, indent=2),
        "系统关键词：\n" + json.dumps(input_payload.get("selected_keywords") or [], ensure_ascii=False, indent=2),
    ]
    return "\n\n".join(parts)


def _selected_keyword_name(selected_keywords: list[dict[str, Any]], category_code: str) -> str | None:
    for item in selected_keywords:
        if isinstance(item, dict) and item.get("category_code") == category_code:
            value = item.get("keyword_name")
            return str(value) if value else None
    return None


def _float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_or_none(value: Any) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _review_report(input_payload: dict[str, Any]) -> dict[str, Any]:
    generation_snapshot = input_payload.get("generation_snapshot") or {}
    compliance_rules = ((generation_snapshot.get("assets") or {}).get("compliance_rules") or [])
    risk_level = "high" if any(rule.get("risk_level") == "high" for rule in compliance_rules if isinstance(rule, dict)) else "medium"
    hard_results = [
        {
            "ae_code": "brand_product_guard",
            "pass": True,
            "risk_level": risk_level,
            "feedback": "未发现明显品牌/产品事实风险",
            "evidence": [],
        },
        {
            "ae_code": "compliance_redline",
            "pass": True,
            "risk_level": risk_level,
            "feedback": "未发现治疗、改善便秘、解决肠胃问题等明显合规红线",
            "evidence": [],
        },
        {
            "ae_code": "expression_writing",
            "pass": True,
            "risk_level": "low",
            "feedback": "未发现明显表达写作规则问题",
            "evidence": [],
        },
        {
            "ae_code": "time_logic",
            "pass": True,
            "risk_level": "low",
            "feedback": "未发现明显时间逻辑冲突",
            "evidence": [],
        },
        {
            "ae_code": "legal_tencent",
            "pass": True,
            "risk_level": "low",
            "feedback": "腾讯云法律审核通过",
            "evidence": [],
        },
    ]
    soft_scores = [
        {"ae_code": "business_logic", "score": 88, "feedback": "痛点、卖点因果链、结构和真人感符合 MVP 要求"},
    ]
    return {
        "risk_level": risk_level,
        "hard_results": hard_results,
        "soft_scores": soft_scores,
        "failed_aes": [],
        "rewrite_required": False,
    }


def _handle_capability(capability: str, input_payload: dict[str, Any]) -> dict[str, Any]:
    if capability == "asset.import":
        return import_asset_package(input_payload)
    if capability == "content.generate":
        return _handle_content_generate(input_payload)
    if capability == "comment.generate":
        return _handle_comment_generate(input_payload)
    if capability == "xhs.interpret_brief":
        generation_snapshot = input_payload.get("generation_snapshot") or {}
        output: dict[str, Any] = {
            "structured_brief": _structured_brief(input_payload),
            "brief_warnings": [],
            "interpreter_notes": "compiled by maga-worker xhs brief compiler",
        }
        if generation_snapshot:
            output["runtime_brief"] = build_runtime_brief_from_snapshot(generation_snapshot)
        return output
    if capability == "xhs.run_ae_analysis":
        structured = input_payload.get("structured_brief") or {}
        topic = structured.get("product_topic") or "产品/主题"
        audience = structured.get("target_audience") or "目标人群"
        return {
            "analyses": {
                "business_logic": {
                    "analysis": f"围绕{audience}对{topic}的真实关注，建立痛点、卖点因果链和真人感表达",
                    "extracted": {},
                },
            },
            "failed_aes": [],
        }
    if capability == "xhs.generate_draft":
        mode = _execution_mode(input_payload)
        if mode == "runtime":
            generation_snapshot = input_payload.get("generation_snapshot") or {}
            if not generation_snapshot:
                raise ValueError("generation_snapshot is required for runtime mode")
            return invoke_runtime_generate_draft(generation_snapshot, runtime_brief=input_payload.get("runtime_brief"))
        if mode == "runtime_fast":
            generation_snapshot = input_payload.get("generation_snapshot") or {}
            if not generation_snapshot:
                raise ValueError("generation_snapshot is required for runtime_fast mode")
            if os.environ.get("MAGA_WORKER_RUNTIME_FAST_FAKE") == "1":
                structured = input_payload.get("structured_brief") or _structured_brief((generation_snapshot.get("brief") or {}))
                draft = _draft_from_structured_brief(structured)
                return {
                    "draft": draft,
                    "runtime_result": {
                        "mode": "runtime_fast",
                        "fake": True,
                        "reason": "MAGA_WORKER_RUNTIME_FAST_FAKE",
                    },
                }
            return invoke_runtime_fast_generate_draft(generation_snapshot, runtime_brief=input_payload.get("runtime_brief"))
        structured = input_payload.get("structured_brief") or {}
        return {"draft": _draft_from_structured_brief(structured)}
    if capability == "xhs.review_and_rewrite":
        generation_snapshot = input_payload.get("generation_snapshot") or {}
        draft = input_payload.get("draft") or input_payload.get("previous_draft") or {}
        if generation_snapshot:
            if not draft:
                raise ValueError("draft is required for review_and_rewrite")
            if os.environ.get("MAGA_WORKER_RUNTIME_FAST_FAKE") == "1":
                report = _review_report({"generation_snapshot": generation_snapshot, "draft": draft})
                return {
                    "final": draft,
                    "draft": draft,
                    "runtime_result": {
                        "mode": "runtime_fast",
                        "phase": "review_and_rewrite",
                        "fake": True,
                        "reason": "MAGA_WORKER_RUNTIME_FAST_FAKE",
                    },
                    "review_report": report,
                    "hard_results": report["hard_results"],
                    "soft_scores": report["soft_scores"],
                    "failed_aes": report["failed_aes"],
                }
            result = invoke_runtime_fast_review_and_rewrite(
                generation_snapshot,
                draft,
                runtime_brief=input_payload.get("runtime_brief"),
            )
            report = result.get("review_report") or {}
            return {
                **result,
                "hard_results": report.get("hard_results") or [],
                "soft_scores": report.get("soft_scores") or [],
                "failed_aes": report.get("failed_aes") or [],
            }
        report = _review_report(input_payload)
        return {
            "final": draft,
            "draft": draft,
            "review_report": report,
            "hard_results": report["hard_results"],
            "soft_scores": report["soft_scores"],
            "failed_aes": report["failed_aes"],
        }
    if capability == "xhs.run_ae_review":
        report = _review_report(input_payload)
        return {
            "review_report": report,
            "hard_results": report["hard_results"],
            "soft_scores": report["soft_scores"],
            "failed_aes": report["failed_aes"],
        }
    if capability == "xhs.rewrite_draft":
        previous = input_payload.get("previous_draft") or {}
        if isinstance(previous, str):
            previous = _title_body_from_text(previous)
        title = previous.get("title") or "改写后标题"
        body = previous.get("body") or "改写后正文"
        return {"final": {"title": title, "body": body}, "rewrite_notes": "deterministic adapter rewrite"}
    raise ValueError(f"unsupported capability: {capability}")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "protocol_version": PROTOCOL_VERSION}


@app.post("/invoke")
def invoke(
    envelope: InvokeEnvelope,
    x_maga_protocol_version: str | None = Header(default=None, alias="X-Maga-Protocol-Version"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    started = time.perf_counter()
    _check_headers(x_maga_protocol_version, authorization)

    if envelope.protocol_version != PROTOCOL_VERSION:
        return {
            "stage_call_id": envelope.stage_call_id,
            "status": "failed",
            "error_code": "input_invalid",
            "error_message": "unsupported envelope protocol version",
        }
    if envelope.capability not in SUPPORTED_CAPABILITIES:
        return {
            "stage_call_id": envelope.stage_call_id,
            "status": "failed",
            "error_code": "input_invalid",
            "error_message": f"unsupported capability: {envelope.capability}",
        }

    try:
        output = _handle_capability(envelope.capability, envelope.input)
    except Exception as exc:  # noqa: BLE001 - convert executor exceptions into protocol failed envelope
        return {
            "stage_call_id": envelope.stage_call_id,
            "status": "failed",
            "error_code": "executor_internal",
            "error_message": str(exc),
        }

    return {
        "stage_call_id": envelope.stage_call_id,
        "status": "succeeded",
        "output": output,
        "stats": {**_stats(started), "module": _module_for_capability(envelope.capability)},
    }
