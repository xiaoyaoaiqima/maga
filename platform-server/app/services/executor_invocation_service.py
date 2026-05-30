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
        if capability == "xhs.interpret_brief":
            generation_snapshot = input_payload.get("generation_snapshot")
            output = {
                "structured_brief": {
                    "brief_type": input_payload.get("brief_type"),
                    "product_topic": input_payload.get("product_topic"),
                    "target_audience": input_payload.get("target_audience") or "小红书用户",
                    "persona_target": input_payload.get("persona_target"),
                    "style": input_payload.get("style") or "自然真实",
                    "tone_hints": [input_payload.get("style") or "自然真实"],
                }
            }
            if generation_snapshot:
                output["generation_snapshot"] = generation_snapshot
                output["runtime_brief"] = _mock_runtime_brief_from_snapshot(generation_snapshot)
            output["brief_warnings"] = []
        elif capability == "xhs.run_ae_analysis":
            structured_brief = input_payload.get("structured_brief") or {}
            output = {
                "analyses": {
                    "business_logic": {
                        "analysis": (
                            f"围绕{structured_brief.get('target_audience', '用户')}对"
                            f"{structured_brief.get('product_topic', '产品/主题')}的关注，建立痛点、卖点因果链和真人感表达"
                        )
                    },
                },
                "failed_aes": [],
            }
        elif capability == "xhs.generate_draft":
            structured_brief = input_payload.get("structured_brief") or {}
            generation_snapshot = input_payload.get("generation_snapshot") or {}
            if generation_snapshot:
                output = {"draft": _mock_xhs_draft_from_snapshot(structured_brief, generation_snapshot)}
            else:
                topic = structured_brief.get("product_topic") or "这个主题"
                audience = structured_brief.get("target_audience") or "你"
                style = structured_brief.get("style") or "自然真实"
                output = {
                    "draft": {
                        "title": f"{topic}怎么选？给{audience}的真实建议",
                        "body": f"如果{audience}正在关注{topic}，可以先从自己的真实需求出发。用{style}的方式表达，重点讲清楚为什么适合、怎么判断、使用时要注意什么。这样写出来的小红书内容更自然，也更容易被收藏。",
                    }
                }
        elif capability == "xhs.run_ae_review":
            report = _mock_review_report(input_payload)
            output = {
                "review_report": report,
                "hard_results": report["hard_results"],
                "soft_scores": report["soft_scores"],
                "failed_aes": report["failed_aes"],
            }
        elif capability == "xhs.review_and_rewrite":
            draft = input_payload.get("draft") or {}
            report = _mock_review_report(input_payload)
            output = {
                "final": {
                    "title": draft.get("title") or "审核后标题",
                    "body": draft.get("body") or "审核后正文",
                },
                "draft": {
                    "title": draft.get("title") or "审核后标题",
                    "body": draft.get("body") or "审核后正文",
                },
                "review_report": report,
                "hard_results": report["hard_results"],
                "soft_scores": report["soft_scores"],
                "failed_aes": report["failed_aes"],
            }
        elif capability == "xhs.rewrite_draft":
            previous_draft = input_payload.get("previous_draft") or {}
            output = {
                "final": {
                    "title": previous_draft.get("title") or "改写后标题",
                    "body": previous_draft.get("body") or "改写后正文",
                }
            }
        elif capability == "asset.import":
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
        elif capability == "comment.generate":
            output = {
                "comment": _mock_comment_from_rule(input_payload),
                "runtime_result": {
                    "mode": "comment_fake",
                    "fake": True,
                    "reason": "mock_executor",
                },
            }
        else:
            output = {}
        return InvokeResult(
            mode="sync",
            stage_call_id=envelope["stage_call_id"],
            output=output,
            stats={"mock": True},
        )


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




def _mock_review_report(input_payload: dict[str, Any]) -> dict[str, Any]:
    generation_snapshot = input_payload.get("generation_snapshot") or {}
    compliance_rules = ((generation_snapshot.get("assets") or {}).get("compliance_rules") or [])
    risk_level = "high" if any(rule.get("risk_level") == "high" for rule in compliance_rules if isinstance(rule, dict)) else "medium"
    hard_results = [
        {
            "ae_code": "brand_product_guard",
            "pass": True,
            "risk_level": risk_level,
            "feedback": "品牌与产品表达保持克制，未发现明显事实越界",
            "evidence": [],
        },
        {
            "ae_code": "compliance_redline",
            "pass": True,
            "risk_level": risk_level,
            "feedback": "未出现治疗、改善便秘、解决肠胃问题等医疗化红线表达",
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


def _mock_xhs_draft_from_snapshot(structured_brief: dict[str, Any], generation_snapshot: dict[str, Any]) -> dict[str, str]:
    assets = generation_snapshot.get("assets") or {}
    diversity = generation_snapshot.get("diversity_slot") or {}
    painpoint = assets.get("painpoint") or {}
    selling_point = assets.get("selling_point") or {}
    examples = assets.get("reference_examples") or []
    writing_pattern = assets.get("writing_pattern") or {}

    topic = _clean_topic(structured_brief.get("product_topic") or "源悦")
    audience = structured_brief.get("target_audience") or "妈妈"
    persona = structured_brief.get("persona_target") or (generation_snapshot.get("brief") or {}).get("persona_target")
    painpoint_text = painpoint.get("painpoint") or topic
    painpoint_desc = painpoint.get("description") or "宝宝状态不稳定"
    selling_text = selling_point.get("selling_point") or painpoint.get("selling_point") or "好消化易吸收"
    advantage = selling_point.get("advantage") or "喝起来温和、接受度比较友好"
    opening_type = diversity.get("opening_type") or "真实经历"
    structure_type = writing_pattern.get("story_arc") or diversity.get("structure_type") or "痛点-观察-建议"
    example_title = examples[0].get("title") if examples and isinstance(examples[0], dict) else "真实转奶经验"
    proof_style = writing_pattern.get("proof_style") or "观察记录"
    ending_pattern = writing_pattern.get("ending_pattern") or "轻建议收束"

    title = f"{painpoint_text}别急，源悦这样观察更稳"
    if opening_type == "真实经历":
        title = f"我家{painpoint_text}那阵子，转源悦后的真实感受"
    elif opening_type == "误区澄清":
        title = f"{painpoint_text}不等于乱换奶，源悦我是这样看的"
    elif opening_type == "清单式建议":
        title = f"宝宝{painpoint_text}，选奶先看这3点"
    elif opening_type == "场景共鸣":
        title = f"懂{audience}看到{painpoint_text}时的焦虑"

    body = (
        f"{persona or '过来人'}提醒：看到宝宝{painpoint_text}，先别急着给自己扣帽子。\n\n"
        f"我会先看几个日常信号：便便软硬、拉臭臭费不费劲、喝奶后肚肚舒不舒服。像{painpoint_desc}这种情况，"
        f"更适合用观察记录去判断，而不是一上来就下结论。\n\n"
        f"这篇参考的是「{example_title}」这类真实分享的节奏，但不照搬原句。我的选择逻辑是：奶粉要温和，宝宝愿意喝，"
        f"也要看{selling_text}。源悦打动我的点就是{selling_text}，{advantage}，对新手妈妈来说判断成本低一点。\n\n"
        f"如果你家也在纠结{topic}，可以按“{structure_type}”的思路慢慢看，用{proof_style}把判断说清楚，"
        f"最后用“{ending_pattern}”收住，不用把话说满。"
        f"持续明显不舒服还是要问专业人士，日常分享不替代专业建议。"
    )
    return {"title": title, "body": body}


def _mock_runtime_brief_from_snapshot(generation_snapshot: dict[str, Any]) -> dict[str, Any]:
    brief = generation_snapshot.get("brief") or {}
    assets = generation_snapshot.get("assets") or {}
    diversity = generation_snapshot.get("diversity_slot") or {}
    batch = generation_snapshot.get("batch_context") or {}
    painpoint = assets.get("painpoint") or {}
    selling_point = assets.get("selling_point") or {}
    item_no = int(batch.get("item_no") or 1)
    return {
        "brief_id": f"maga-{batch.get('batch_code') or 'manual'}-{item_no:03d}",
        "brief_type": "xhs_product_seeding_professional_advisor",
        "product_topic": brief.get("product_topic") or "源悦",
        "target_audience": brief.get("target_audience") or "小红书用户",
        "style": brief.get("style") or "自然真实",
        "key_painpoints": [painpoint.get("painpoint") or brief.get("product_topic") or "源悦"],
        "key_sellingpoints": [selling_point.get("selling_point") or painpoint.get("selling_point") or "好消化易吸收"],
        "maga": {
            "source": "maga_generation_snapshot",
            "brief": brief,
            "assets": assets,
            "diversity_slot": diversity,
            "batch_context": batch,
        },
    }


def _clean_topic(topic: str) -> str:
    return str(topic).split("｜", 1)[0]

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
