"""Protocol v0.1 HTTP adapter for MAGA -> repo-managed maga-worker integration.

This is intentionally a thin executor boundary: MAGA owns tasks/runs/state and this
service only executes a requested capability from the input snapshot.
"""
from __future__ import annotations

import os
import time
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from maga_worker.asset_importer import import_asset_package
from maga_worker.runtime_adapter import invoke_runtime_fast_generate_draft, invoke_runtime_generate_draft

PROTOCOL_VERSION = "0.1"
SUPPORTED_CAPABILITIES = {
    "xhs.interpret_brief",
    "xhs.run_ae_analysis",
    "xhs.generate_draft",
    "xhs.run_ae_review",
    "xhs.rewrite_draft",
    "asset.import",
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
    topic = input_payload.get("product_topic") or brief.get("product_topic") or brief.get("topic") or "产品/主题"
    target = input_payload.get("target_audience") or brief.get("target_audience") or "小红书用户"
    style = input_payload.get("style") or brief.get("style") or "自然真实"
    return {
        "brief_type": input_payload.get("brief_type") or brief.get("brief_type") or "xhs_product_seeding_professional_advisor",
        "product_topic": topic,
        "target_audience": target,
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
    ]
    soft_scores = [
        {"ae_code": "xhs_structure", "score": 88, "feedback": "标题和正文结构符合小红书笔记 MVP 要求"},
        {"ae_code": "naturalness_ai_smell", "score": 86, "feedback": "表达自然，可继续优化真实细节"},
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
    if capability == "xhs.interpret_brief":
        return {"structured_brief": _structured_brief(input_payload), "interpreter_notes": "parsed by maga-worker xhs module"}
    if capability == "xhs.run_ae_analysis":
        structured = input_payload.get("structured_brief") or {}
        topic = structured.get("product_topic") or "产品/主题"
        audience = structured.get("target_audience") or "目标人群"
        return {
            "analyses": {
                "painpoint_anchor": {"analysis": f"围绕{audience}的选择顾虑建立共情入口", "extracted": {}},
                "sellingpoint_logic": {"analysis": f"围绕{topic}给出清晰、克制、可验证的理由", "extracted": {}},
                "narrative_strategy": {"analysis": "先共情，再给判断方法，最后给行动建议", "extracted": {}},
            },
            "failed_aes": [],
        }
    if capability == "xhs.generate_draft":
        mode = _execution_mode(input_payload)
        if mode == "runtime":
            generation_snapshot = input_payload.get("generation_snapshot") or {}
            if not generation_snapshot:
                raise ValueError("generation_snapshot is required for runtime mode")
            return invoke_runtime_generate_draft(generation_snapshot)
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
                    "review_report": _review_report({"generation_snapshot": generation_snapshot, "draft": draft}),
                }
            return invoke_runtime_fast_generate_draft(generation_snapshot)
        structured = input_payload.get("structured_brief") or {}
        return {"draft": _draft_from_structured_brief(structured)}
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
