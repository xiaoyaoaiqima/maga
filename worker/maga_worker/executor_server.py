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

PROTOCOL_VERSION = "0.1"
SUPPORTED_CAPABILITIES = {
    "asset.import",
    "content.generate",
    "content.rewrite",
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
    return os.environ.get("MAGA_WORKER_EXECUTOR_TOKEN")


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
        "module": "content-generator",
        "adapter": "maga_worker.executor_server",
        "total_latency_ms": int((time.perf_counter() - started) * 1000),
    }


def _module_for_capability(capability: str) -> str:
    if capability.startswith("asset."):
        return "asset-steward"
    if capability.startswith("content."):
        return "content-generator"
    return "content-generator"


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

    business_rule = str(input_payload.get("business_rule") or "这个规则").strip()
    return f"{business_rule}这个点还挺想听听大家真实感受的，我家也在观望源悦。"


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

    from maga_worker.llm_runtime import call_model, default_content_model, normalize_content_model

    model_config = input_payload.get("model_config") or {}
    model = normalize_content_model(model_config.get("model_code") or model_config.get("ge_model") or default_content_model())
    temperature = _float_or_default(model_config.get("temperature"), 0.8)
    max_tokens = _int_or_none(model_config.get("max_tokens"))
    system = str(
        model_config.get("system_prompt")
        or "你是中文小红书内容生成器，严格按用户提示输出，不解释过程。"
    )
    prompt = str(input_payload.get("rendered_prompt") or "").strip()
    if not prompt:
        prompt = _fallback_rendered_prompt(input_payload)
    output = _generate_content_with_runtime_fallback(
        input_payload,
        call_model=call_model,
        model_config=model_config,
        model=model,
        system=system,
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    output["runtime_result"] = {
        "mode": "content_runtime",
        "fake": False,
        "expert_config_code": (input_payload.get("expert") or {}).get("expert_config_code"),
        "provider_code": model_config.get("provider_code"),
        "model_code": model,
        **(output.pop("_runtime_meta", {})),
    }
    return output


def _generate_content_with_runtime_fallback(
    input_payload: dict[str, Any],
    *,
    call_model,
    model_config: dict[str, Any],
    model: str,
    system: str,
    prompt: str,
    temperature: float,
    max_tokens: int | None,
) -> dict[str, Any]:
    """Retry empty model outputs, then return an explicit empty result."""
    attempts = [
        prompt,
        (
            f"{prompt}\n\n"
            f"{_nonempty_output_reminder(input_payload)}"
        ),
    ]
    last_raw = ""
    last_error: ValueError | None = None
    for attempt_no, attempt_prompt in enumerate(attempts, start=1):
        raw = call_model(
            model,
            system=system,
            user=attempt_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=model_config.get("api_key"),
            base_url=model_config.get("base_url") or model_config.get("endpoint"),
            timeout=model_config.get("timeout"),
            max_retries=model_config.get("max_retries"),
        )
        last_raw = str(raw or "")
        try:
            output = _normalize_unified_content_output(last_raw, input_payload)
        except ValueError as exc:
            last_error = exc
            if "empty" in str(exc):
                continue
            raise
        output["_runtime_meta"] = {
            "fallback": False,
            "model_attempts": attempt_no,
            "raw_output_length": len(last_raw),
        }
        return output

    # Do not reuse rule examples after runtime empties; duplicate generated rows
    # are worse than an explicit empty result that upstream can mark for retry.
    output = _empty_content_from_unified_input(input_payload)
    output["_runtime_meta"] = {
        "fallback": False,
        "empty_output": True,
        "empty_reason": str(last_error or "empty_model_output"),
        "model_attempts": len(attempts),
        "raw_output_length": len(last_raw),
    }
    return output


def _nonempty_output_reminder(input_payload: dict[str, Any]) -> str:
    if str(input_payload.get("content_type") or "") == "comment":
        mode = str(input_payload.get("output_format_mode") or "").strip()
        try:
            count = int(input_payload.get("expansion_count") or 1)
        except (TypeError, ValueError):
            count = 1
        if mode == "json_string_array" and count > 1:
            return f"再次提醒：必须输出非空结果，并且只输出正好 {count} 条评论组成的 JSON 字符串数组。"
        if mode == "json_object_array" and count > 1:
            return f'再次提醒：必须输出非空结果，并且只输出正好 {count} 个含 "comment" 字段的 JSON 对象数组。'
        return "再次提醒：必须输出非空结果。评论只输出一条评论正文。"
    return "再次提醒：必须输出非空结果。文章输出标题和正文。"


def _handle_content_rewrite(input_payload: dict[str, Any]) -> dict[str, Any]:
    previous = _rewrite_previous_content(input_payload)
    content_type = str(input_payload.get("content_type") or ("comment" if previous.get("comment") else "article"))
    output_fields = input_payload.get("output_fields") or (["comment"] if content_type == "comment" else ["title", "body"])
    forbidden_hits = _rewrite_forbidden_hits(input_payload)
    forbidden_replacements = _rewrite_forbidden_replacements(input_payload)

    if os.environ.get("MAGA_WORKER_RUNTIME_FAST_FAKE") == "1":
        output = _stable_rewrite_from_previous(
            previous,
            forbidden_hits,
            forbidden_replacements,
            content_type=content_type,
            output_fields=output_fields,
            input_payload=input_payload,
        )
        output["runtime_result"] = {
            "mode": "content_rewrite_fake",
            "fake": True,
            "reason": "MAGA_WORKER_RUNTIME_FAST_FAKE",
            "forbidden_hits": forbidden_hits,
            "expert_config_code": (input_payload.get("expert") or {}).get("expert_config_code"),
        }
        return output

    from maga_worker.llm_runtime import call_model, default_content_model, normalize_content_model

    model_config = input_payload.get("model_config") or input_payload.get("rewrite_model_config") or {}
    model = normalize_content_model(
        model_config.get("model_code")
        or model_config.get("ge_model")
        or os.environ.get("MAGA_WORKER_REWRITE_MODEL")
        or default_content_model()
    )
    temperature = _float_or_default(model_config.get("temperature"), 0.35)
    max_tokens = _int_or_none(model_config.get("max_tokens"))
    system = str(
        model_config.get("system_prompt")
        or "你是中文内容审核后的自然改写助手，只按要求改写，不解释过程。"
    )
    prompt = str(input_payload.get("rendered_prompt") or "").strip()
    if not prompt:
        prompt = _rewrite_prompt(
            input_payload,
            previous=previous,
            forbidden_hits=forbidden_hits,
            forbidden_replacements=forbidden_replacements,
            content_type=content_type,
        )
        raw = call_model(
            model,
            system=system,
            user=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=model_config.get("api_key"),
            base_url=model_config.get("base_url") or model_config.get("endpoint"),
            timeout=model_config.get("timeout"),
            max_retries=model_config.get("max_retries"),
        )
    output = _normalize_rewrite_output(raw, input_payload, content_type=content_type, output_fields=output_fields)
    output["runtime_result"] = {
        "mode": "content_rewrite_runtime",
        "fake": False,
        "provider_code": model_config.get("provider_code"),
        "model_code": model,
        "forbidden_hits": forbidden_hits,
        "expert_config_code": (input_payload.get("expert") or {}).get("expert_config_code"),
    }
    return output


def _rewrite_previous_content(input_payload: dict[str, Any]) -> dict[str, str]:
    previous = input_payload.get("previous_content") or input_payload.get("previous_draft") or {}
    content_type = str(input_payload.get("content_type") or "")
    if isinstance(previous, str):
        if content_type == "comment" or (input_payload.get("output_fields") or []) == ["comment"]:
            return {"comment": previous}
        title, body = _title_body_from_text(previous)
        return {"title": title, "body": body}
    if not isinstance(previous, dict):
        previous = {}
    if content_type == "comment" or (input_payload.get("output_fields") or []) == ["comment"]:
        return {"comment": str(previous.get("comment") or previous.get("body") or input_payload.get("comment") or "").strip()}
    return {
        "title": str(previous.get("title") or input_payload.get("title") or "").strip(),
        "body": str(previous.get("body") or previous.get("comment") or input_payload.get("body") or "").strip(),
    }


def _rewrite_forbidden_hits(input_payload: dict[str, Any]) -> list[str]:
    values = input_payload.get("forbidden_hits")
    if values is None:
        values = ((input_payload.get("review_report") or {}).get("forbidden_terms_review") or {}).get("hits")
    if values is None:
        values = (((input_payload.get("review_report") or {}).get("hard_results") or [{}])[0] or {}).get("evidence")
    return [str(value).strip() for value in values or [] if str(value).strip()]


def _rewrite_forbidden_replacements(input_payload: dict[str, Any]) -> dict[str, str]:
    raw = input_payload.get("forbidden_replacements") or input_payload.get("replacement_map") or {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(term).strip(): str(replacement).strip()
        for term, replacement in raw.items()
        if str(term).strip() and str(replacement).strip()
    }


def _stable_rewrite_from_previous(
    previous: dict[str, str],
    forbidden_hits: list[str],
    forbidden_replacements: dict[str, str],
    *,
    content_type: str,
    output_fields: list[Any],
    input_payload: dict[str, Any],
) -> dict[str, str]:
    operator_feedback = _operator_feedback(input_payload)
    if content_type == "comment" or output_fields == ["comment"]:
        comment = _remove_or_replace_terms_from_text(
            previous.get("comment") or previous.get("body") or "",
            forbidden_hits,
            forbidden_replacements,
        )
        if operator_feedback and comment:
            comment = f"{comment} 我会按这个方向再具体一点。"
        comment = _normalize_comment_text(comment) or "这个点我也在关注，想看看大家真实反馈。"
        return {"comment": comment}

    similarity = (input_payload.get("review_report") or {}).get("similarity")
    if isinstance(similarity, dict):
        reason = str((input_payload.get("review_report") or {}).get("rewrite_reason") or similarity.get("reason") or "")
        body = f"换一个开头和结构来写。触发原因：{reason}"
        return {"title": "降重后的标题", "body": body, "final": {"title": "降重后的标题", "body": body}}
    title = _remove_or_replace_terms_from_text(previous.get("title") or "", forbidden_hits, forbidden_replacements) or "真实体验分享"
    body = _remove_or_replace_terms_from_text(previous.get("body") or "", forbidden_hits, forbidden_replacements) or "围绕真实使用感受自然表达，保持克制，不夸大。"
    if operator_feedback:
        body = f"{body}\n\n按运营反馈调整：{operator_feedback}"
    return {"title": title, "body": body, "final": {"title": title, "body": body}}


def _operator_feedback(input_payload: dict[str, Any]) -> str:
    value = input_payload.get("operator_feedback") or (input_payload.get("review_report") or {}).get("operator_feedback")
    return str(value or "").strip()


def _remove_or_replace_terms_from_text(value: str, forbidden_hits: list[str], forbidden_replacements: dict[str, str]) -> str:
    text = str(value or "")
    for term in forbidden_hits:
        text = text.replace(term, forbidden_replacements.get(term, ""))
    while "  " in text:
        text = text.replace("  ", " ")
    for duplicate in ["、、", "，，", "。。", "；；"]:
        while duplicate in text:
            text = text.replace(duplicate, duplicate[0])
    return text.strip(" ，。；、")


def _rewrite_prompt(
    input_payload: dict[str, Any],
    *,
    previous: dict[str, str],
    forbidden_hits: list[str],
    forbidden_replacements: dict[str, str],
    content_type: str,
) -> str:
    output_instruction = (
        "输出要求：只输出改写后的评论正文，不要标题、编号、解释。"
        if content_type == "comment"
        else '输出要求：只输出 JSON，格式为 {"title": "...", "body": "..."}，不要解释。'
    )
    parts = [
        f"内容类型：{content_type}",
        "原内容：\n" + json.dumps(previous, ensure_ascii=False, indent=2),
        f"必须删除或自然替换的违禁词：{'、'.join(forbidden_hits) if forbidden_hits else '无'}",
        "指定替换映射：\n"
        + (
            "\n".join(f"- {term} -> {replacement}" for term, replacement in forbidden_replacements.items())
            if forbidden_replacements
            else "无"
        ),
        "改写原则：只改命中词和相关句子，尽量保留原意、语气、结构和业务规则；不得新增功效承诺、医疗诊断或绝对化表达。",
        output_instruction,
    ]
    instructions = input_payload.get("rewrite_instructions") or []
    if instructions:
        parts.append("补充指令：\n" + "\n".join(f"- {item}" for item in instructions if str(item).strip()))
    business_rule = input_payload.get("business_rule")
    if business_rule:
        parts.append("业务规则：\n" + json.dumps(business_rule, ensure_ascii=False, indent=2))
    selected_keywords = input_payload.get("selected_keywords")
    if selected_keywords:
        parts.append("已选系统关键词：\n" + json.dumps(selected_keywords, ensure_ascii=False, indent=2))
    return "\n\n".join(parts)


def _normalize_rewrite_output(
    raw: str,
    input_payload: dict[str, Any],
    *,
    content_type: str,
    output_fields: list[Any],
) -> dict[str, str]:
    if content_type == "comment" or output_fields == ["comment"]:
        parsed = _parse_json_object(raw)
        comment = str(parsed.get("comment") or parsed.get("评论") or "").strip() if parsed else ""
        comment = _normalize_comment_text(comment or raw)
        if not comment:
            raise ValueError("content.rewrite produced empty comment")
        return {"comment": comment}

    parsed = _parse_json_object(raw)
    title = str(parsed.get("title") or parsed.get("标题") or "").strip()
    body = str(parsed.get("body") or parsed.get("正文") or "").strip()
    if not title or not body:
        title, body = _title_body_from_text(raw)
    if not body:
        previous = _rewrite_previous_content(input_payload)
        body = previous.get("body") or ""
    if not body:
        raise ValueError("content.rewrite produced empty body")
    title = title or (_rewrite_previous_content(input_payload).get("title") or "改写后标题")
    return {"title": title, "body": body, "final": {"title": title, "body": body}}


def _stable_content_from_unified_input(input_payload: dict[str, Any]) -> dict[str, str]:
    output_fields = input_payload.get("output_fields") or []
    if output_fields == ["comment"] or input_payload.get("content_type") == "comment":
        business_rule = input_payload.get("business_rule") or {}
        return {"comment": _stable_comment_from_rule(business_rule)}

    business_rule = input_payload.get("business_rule") or {}
    selected_keywords = input_payload.get("selected_keywords") or []
    topic = business_rule.get("product_topic") or business_rule.get("product_experience") or "源悦体验"
    target = business_rule.get("target_audience") or business_rule.get("baby_stage") or "妈妈"
    persona = _selected_keyword_name(selected_keywords, "persona") or "真实妈妈"
    method = _selected_keyword_name(selected_keywords, "writing_method") or "自然写法"
    return {
        "title": f"{topic}，{persona}的真实分享",
        "body": f"围绕{topic}，写给{target}，用{persona}的口吻承接业务规则，再用{method}把具体感受讲清楚。整体表达保持自然克制，不夸大、不照搬示例。",
    }


def _empty_content_from_unified_input(input_payload: dict[str, Any]) -> dict[str, str]:
    output_fields = input_payload.get("output_fields") or []
    if output_fields == ["comment"] or input_payload.get("content_type") == "comment":
        return {"comment": ""}
    return {"title": "", "body": ""}


def _normalize_unified_content_output(raw: str, input_payload: dict[str, Any]) -> dict[str, Any]:
    output_fields = input_payload.get("output_fields") or []
    if output_fields == ["comment"] or input_payload.get("content_type") == "comment":
        comment = _normalize_comment_text(raw)
        if not comment:
            raise ValueError("content.generate produced empty comment")
        return {"comment": comment}

    parsed = _parse_json_object(raw)
    multi_items = _article_items_from_parsed_json(parsed)
    if multi_items:
        first = multi_items[0]
        return {"title": first["title"], "body": first["body"], "items": multi_items}

    title = _clean_generated_article_text(parsed.get("title") or parsed.get("标题"))
    body = _clean_generated_article_text(parsed.get("body") or parsed.get("正文"))
    if not title or not body:
        title, body = _title_body_from_text(raw)
    title = _clean_generated_article_text(title)
    body = _clean_generated_article_text(body)
    if not body:
        raise ValueError("content.generate produced empty body")
    return {"title": title or "源悦真实体验分享", "body": body}


def _article_items_from_parsed_json(parsed: dict[str, Any]) -> list[dict[str, str]]:
    raw_items = parsed.get("items") or parsed.get("文章列表") or parsed.get("内容列表")
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, str]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        title = _clean_generated_article_text(raw_item.get("title") or raw_item.get("标题"))
        body = _clean_generated_article_text(raw_item.get("body") or raw_item.get("正文"))
        if body:
            items.append({"title": title or "源悦真实体验分享", "body": body})
    return items


def _clean_generated_article_text(value: Any) -> str:
    text = str(value or "").strip()
    text = _strip_topic_tags(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def _strip_topic_tags(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"#[^\s#，。！？、；;]{1,40}\[话题\]#?", "", text)
    cleaned = re.sub(r"#[^\s#，。！？、；;]{1,40}#", "", cleaned)
    cleaned = re.sub(r"(?:\s*#[^\s#，。！？、；;]{1,40})+\s*$", "", cleaned)
    cleaned = re.sub(r"\[[^\[\]]{1,12}话题[^\[\]]{0,12}\]", "", cleaned)
    return cleaned.strip()


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


def _handle_capability(capability: str, input_payload: dict[str, Any]) -> dict[str, Any]:
    if capability == "asset.import":
        return import_asset_package(input_payload)
    if capability == "content.generate":
        return _handle_content_generate(input_payload)
    if capability == "content.rewrite":
        return _handle_content_rewrite(input_payload)
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
