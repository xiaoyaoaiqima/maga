"""MAGA -> Executor protocol v0.1 invocation helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from typing import Any

import httpx

PROTOCOL_VERSION = "0.1"


@dataclass(frozen=True)
class InvokeResult:
    """Normalized result of calling an executor /invoke endpoint."""

    mode: str
    stage_call_id: str
    status: str = "succeeded"
    output: dict[str, Any] | None = None
    stats: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def build_invoke_envelope(
    *,
    run_id: int,
    task_id: int,
    stage_call_id: str,
    capability: str,
    schema_version: str,
    run_token: str,
    input_payload: dict[str, Any],
    callback_base_url: str,
    deadline_at: datetime | None,
) -> dict[str, Any]:
    """Build the protocol v0.1 invocation envelope sent from MAGA to Executor."""
    callback_base = callback_base_url.rstrip("/")
    return {
        "protocol_version": PROTOCOL_VERSION,
        "run_id": run_id,
        "task_id": task_id,
        "stage_call_id": stage_call_id,
        "capability": capability,
        "schema_version": schema_version,
        "deadline_at": _iso_or_none(deadline_at),
        "executor_hints": {"timeout_seconds": 60},
        "input": input_payload or {},
        "callback": {
            "events_url": f"{callback_base}/runs/{run_id}/events",
            "artifacts_url": f"{callback_base}/runs/{run_id}/artifacts",
            "human_review_url": f"{callback_base}/runs/{run_id}/human-review",
        },
    }


class MockExecutorInvocationClient:
    """Local deterministic mock for early API smoke before Hermes /invoke exists."""

    async def invoke(self, *, invoke_url: str, envelope: dict[str, Any], executor_token: str | None = None) -> InvokeResult:
        input_payload = envelope.get("input") or {}
        capability = envelope.get("capability")
        output: dict[str, Any]
        if capability == "asset.import":
            asset_key = input_payload.get("asset_key") or "yuanyue"
            source_hash = input_payload.get("source_hash") or "mock-source-hash"
            output = {
                "asset_key": asset_key,
                "source_hash": source_hash,
                "warnings": ["mock asset.import output; start real maga-worker for workbook parsing"],
                "assets": [
                    {
                        "asset_type": "brand_profile",
                        "asset_key": asset_key,
                        "display_name": "源悦品牌资料",
                        "content_json": {
                            "brand_key": asset_key,
                            "brand_name": "源悦",
                            "content_focus": "好消化易吸收，对应便便好，不上火",
                            "content_style": "高质量真实用户ugc",
                        },
                    },
                    {
                        "asset_type": "product_selling_points",
                        "asset_key": asset_key,
                        "display_name": "源悦产品卖点",
                        "content_json": {
                            "items": [
                                {
                                    "level": "核心卖点",
                                    "selling_point": "好消化易吸收",
                                    "ingredient": "软分子蛋白",
                                    "advantage": "形成结构松散的软凝乳",
                                    "expressions": ["喝起来温和，宝宝接受度更友好"],
                                }
                            ]
                        },
                    },
                    {
                        "asset_type": "painpoint_model",
                        "asset_key": asset_key,
                        "display_name": "源悦主题/痛点模型",
                        "content_json": {
                            "topics": [
                                {
                                    "topic": "便便不规律",
                                    "painpoint": "便便不规律",
                                    "descriptions": ["羊屎蛋/干硬", "便便又干又硬"],
                                    "selling_points": [
                                        {
                                            "selling_point": "好消化易吸收",
                                            "descriptions": ["软分子蛋白形成结构松散的软凝乳"],
                                            "expressions": ["便便基本一天一次，拉起来也不费劲"],
                                        }
                                    ],
                                }
                            ],
                            "items": [
                                {
                                    "painpoint": "便便不规律",
                                    "description": "羊屎蛋/干硬；便便又干又硬",
                                    "selling_point": "好消化易吸收",
                                    "selling_points": ["好消化易吸收"],
                                }
                            ],
                        },
                    },
                    {
                        "asset_type": "reference_examples",
                        "asset_key": asset_key,
                        "display_name": "源悦参考例文",
                        "content_json": {
                            "items": [
                                {
                                    "example_id": "yuanyue_ref_mock_001",
                                    "title": "真实经验！转奶终于不踩坑",
                                    "body": "新手妈妈别急着焦虑，先看宝宝喝奶和便便状态。",
                                    "reference_type": "用后分享",
                                    "style_tags": ["用后分享"],
                                }
                            ]
                        },
                    },
                    {
                        "asset_type": "ugc_expression_corpus",
                        "asset_key": asset_key,
                        "display_name": "源悦 UGC 卖点表述语料",
                        "content_json": {
                            "items": [
                                {
                                    "painpoint_or_selling_point": "便便不规律",
                                    "expression": "便便基本一天一次，拉起来也不费劲",
                                    "owner": "mock",
                                }
                            ]
                        },
                    },
                    {
                        "asset_type": "compliance_rules",
                        "asset_key": asset_key,
                        "display_name": "源悦审核规则",
                        "content_json": {
                            "items": [
                                {
                                    "dimension": "不得宣称治疗便秘",
                                    "feedback": "避免医疗化、绝对化表述",
                                }
                            ]
                        },
                    },
                ],
            }
        elif capability == "content.generate":
            output = _mock_unified_content_generation(input_payload)
        elif capability == "content.rewrite":
            output = _mock_content_rewrite(input_payload)
        else:
            return InvokeResult(
                mode="sync",
                stage_call_id=envelope["stage_call_id"],
                status="failed",
                error_code="input_invalid",
                error_message=f"unsupported capability: {capability}",
                stats={"mock": True},
            )
        return InvokeResult(
            mode="sync",
            stage_call_id=envelope["stage_call_id"],
            output=output,
            stats={"mock": True},
        )


def _mock_unified_content_generation(input_payload: dict[str, Any]) -> dict[str, Any]:
    output_fields = input_payload.get("output_fields") or []
    if output_fields == ["comment"] or input_payload.get("content_type") == "comment":
        business_rule = input_payload.get("business_rule") or {}
        comment = _mock_comment_from_rule(business_rule)
        if not comment:
            comment = _mock_comment_from_rule(input_payload)
        return {
            "comment": comment,
            "runtime_result": {
                "mode": "content_fake",
                "fake": True,
                "reason": "mock_executor",
                "expert_config_code": ((input_payload.get("expert") or {}).get("expert_config_code")),
            },
        }

    business_rule = input_payload.get("business_rule") or {}
    selected = input_payload.get("selected_keywords") or []
    topic = business_rule.get("product_topic") or business_rule.get("product_experience") or "源悦体验"
    target = business_rule.get("target_audience") or business_rule.get("baby_stage") or "妈妈"
    persona = _selected_keyword_name(selected, "persona") or "真实妈妈"
    method = _selected_keyword_name(selected, "writing_method") or "自然表达"
    return {
        "title": f"{topic}，{persona}的真实分享",
        "body": f"围绕{topic}，写给{target}，用{persona}的口吻承接业务规则，再用{method}把具体感受讲清楚。整体表达保持自然克制，不夸大、不照搬示例。",
        "runtime_result": {
            "mode": "content_fake",
            "fake": True,
            "reason": "mock_executor",
            "expert_config_code": ((input_payload.get("expert") or {}).get("expert_config_code")),
        },
    }


def _mock_content_rewrite(input_payload: dict[str, Any]) -> dict[str, Any]:
    previous = input_payload.get("previous_content") or input_payload.get("previous_draft") or {}
    if not isinstance(previous, dict):
        previous = {}
    hits = [str(value).strip() for value in input_payload.get("forbidden_hits") or [] if str(value).strip()]
    replacements = _mock_replacements(input_payload)
    operator_feedback = str(
        input_payload.get("operator_feedback")
        or (input_payload.get("review_report") or {}).get("operator_feedback")
        or ""
    ).strip()
    output_fields = input_payload.get("output_fields") or []
    if output_fields == ["comment"] or input_payload.get("content_type") == "comment":
        comment = _mock_remove_or_replace_terms(str(previous.get("comment") or previous.get("body") or ""), hits, replacements)
        if operator_feedback and comment:
            comment = f"{comment} 我会按这个方向再具体一点。"
        return {
            "comment": comment or "这个点我也在关注，想看看大家真实反馈。",
            "runtime_result": {
                "mode": "content_rewrite_fake",
                "fake": True,
                "reason": "mock_executor",
            },
        }
    similarity = (input_payload.get("review_report") or {}).get("similarity")
    if isinstance(similarity, dict):
        reason = str((input_payload.get("review_report") or {}).get("rewrite_reason") or similarity.get("reason") or "")
        return {
            "title": "降重后的标题",
            "body": f"换一个开头和结构来写。触发原因：{reason}",
            "final": {"title": "降重后的标题", "body": f"换一个开头和结构来写。触发原因：{reason}"},
            "runtime_result": {
                "mode": "content_rewrite_fake",
                "fake": True,
                "reason": "mock_executor",
            },
        }
    title = _mock_remove_or_replace_terms(str(previous.get("title") or ""), hits, replacements) or "改写后标题"
    body = _mock_remove_or_replace_terms(str(previous.get("body") or ""), hits, replacements) or "改写后正文"
    if operator_feedback:
        body = f"{body}\n\n按运营反馈调整：{operator_feedback}"
    return {
        "title": title,
        "body": body,
        "final": {"title": title, "body": body},
        "runtime_result": {
            "mode": "content_rewrite_fake",
            "fake": True,
            "reason": "mock_executor",
        },
    }


def _mock_replacements(input_payload: dict[str, Any]) -> dict[str, str]:
    raw = input_payload.get("forbidden_replacements") or {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(term).strip(): str(replacement).strip()
        for term, replacement in raw.items()
        if str(term).strip() and str(replacement).strip()
    }


def _mock_remove_or_replace_terms(value: str, hits: list[str], replacements: dict[str, str]) -> str:
    text = value
    for term in hits:
        text = text.replace(term, replacements.get(term, ""))
    while "  " in text:
        text = text.replace("  ", " ")
    for duplicate in ["、、", "，，", "。。", "；；"]:
        while duplicate in text:
            text = text.replace(duplicate, duplicate[0])
    return text.strip(" ，。；、")


def _selected_keyword_name(selected_keywords: list[dict[str, Any]], category_code: str) -> str | None:
    for item in selected_keywords:
        if item.get("category_code") == category_code:
            value = item.get("keyword_name")
            return str(value) if value else None
    return None


def _mock_comment_from_rule(input_payload: dict[str, Any]) -> str:
    examples = [
        str(value).strip()
        for value in [
            *(input_payload.get("examples") or []),
            *(input_payload.get("supplements") or []),
        ]
        if str(value).strip()
    ]
    if examples:
        try:
            item_no = int(input_payload.get("item_no") or 1)
        except (TypeError, ValueError):
            item_no = 1
        return examples[(item_no - 1) % len(examples)]

    comment_angle = str(input_payload.get("comment_angle") or "这个角度").strip()
    return f"这个{comment_angle}我还挺有共鸣的，想看看其他妈妈怎么说。"




def _default_timeout_seconds() -> float:
    raw = os.getenv("MAGA_EXECUTOR_INVOKE_TIMEOUT_SECONDS", "180")
    try:
        return float(raw)
    except ValueError:
        return 180.0


class ExecutorInvocationClient:
    """HTTP client for MAGA push invocation of an executor capability."""

    def __init__(self, http_client: Any | None = None, timeout_seconds: float | None = None):
        self.http_client = http_client or httpx.AsyncClient()
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else _default_timeout_seconds()

    async def invoke(self, *, invoke_url: str, envelope: dict[str, Any], executor_token: str | None = None) -> InvokeResult:
        headers = {"X-Maga-Protocol-Version": PROTOCOL_VERSION}
        if executor_token:
            headers["Authorization"] = f"Bearer {executor_token}"
        response = await self.http_client.post(
            invoke_url,
            json=envelope,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        payload = response.json()

        if response.status_code == 200:
            status = payload.get("status") or "succeeded"
            return InvokeResult(
                mode="sync",
                stage_call_id=payload.get("stage_call_id") or envelope["stage_call_id"],
                status=status,
                output=payload.get("output") if status == "succeeded" else None,
                stats=payload.get("stats"),
                error_code=payload.get("error_code"),
                error_message=payload.get("error_message"),
            )

        if response.status_code == 202:
            raise RuntimeError("MVP protocol requires sync /invoke response; async ack is not supported")

        raise RuntimeError(f"Executor invoke failed: status={response.status_code} body={response.text}")
