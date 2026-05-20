"""Adapter from MAGA generation_snapshot to repo-managed xhs_runtime."""
from __future__ import annotations

import time
import os
import json
import concurrent.futures
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

import yaml

RUNTIME_FAST_AE_REVIEW_CODES = ("compliance_redline", "expression_writing", "time_logic")
RUNTIME_FAST_LEGAL_REVIEW_CODE = "legal_tencent"
RUNTIME_FAST_REVIEW_CODES = (*RUNTIME_FAST_AE_REVIEW_CODES, RUNTIME_FAST_LEGAL_REVIEW_CODE)


def build_runtime_brief_from_snapshot(generation_snapshot: dict[str, Any]) -> dict[str, Any]:
    brief = generation_snapshot.get("brief") or {}
    assets = generation_snapshot.get("assets") or {}
    diversity = generation_snapshot.get("diversity_slot") or {}
    batch = generation_snapshot.get("batch_context") or {}
    batch_code = batch.get("batch_code") or "manual"
    item_no = int(batch.get("item_no") or 1)
    product_topic = brief.get("product_topic") or "源悦"
    target_audience = brief.get("target_audience") or "小红书用户"
    style = brief.get("style") or "自然真实"
    painpoint = assets.get("painpoint") or {}
    selling_point = assets.get("selling_point") or {}
    examples = assets.get("reference_examples") or []
    compliance_rules = assets.get("compliance_rules") or []
    must_avoid = sorted(
        {
            str(rule.get("dimension") or "").replace("禁止", "").strip()
            for rule in compliance_rules
            if isinstance(rule, dict) and (rule.get("dimension") or "").strip()
        }
    )

    return {
        "brief_id": f"maga-{batch_code}-{item_no:03d}",
        "brief_type": "xhs_product_seeding_professional_advisor",
        "brand": "yuanyue",
        "products": ["yuanyue"],
        "campaign": {
            "topic": product_topic,
            "target_audience": target_audience,
            "style": style,
            "opening_type": diversity.get("opening_type"),
            "structure_type": diversity.get("structure_type"),
        },
        "product_topic": product_topic,
        "target_audience": target_audience,
        "style": style,
        "key_painpoints": [painpoint.get("painpoint") or product_topic],
        "key_sellingpoints": [selling_point.get("selling_point") or painpoint.get("selling_point") or "好消化易吸收"],
        "reference_examples": [
            {"title": ex.get("title"), "body": ex.get("body"), "painpoint": ex.get("painpoint")}
            for ex in examples
            if isinstance(ex, dict)
        ],
        "must_avoid": must_avoid,
        "score_threshold": 85,
        "max_rewrites": 1,
        "soft_floor": 70,
        "maga": {
            "source": "maga_generation_snapshot",
            "brief": brief,
            "assets": assets,
            "diversity_slot": diversity,
            "batch_context": batch,
        },
    }


def invoke_runtime_generate_draft(
    generation_snapshot: dict[str, Any],
    *,
    runtime_brief: dict[str, Any] | None = None,
    run_full_flow_func: Callable[..., dict[str, Any]] | None = None,
    work_dir: str | Path | None = None,
) -> dict[str, Any]:
    if run_full_flow_func is None:
        from maga_worker.xhs_runtime import run_full_flow as run_full_flow_func

    brief = _resolve_runtime_brief(generation_snapshot, runtime_brief)
    if work_dir is None:
        base = default_output_dir() / f"runtime_{brief['brief_id']}_{int(time.time())}"
    else:
        base = Path(work_dir)
    base.mkdir(parents=True, exist_ok=True)
    brief_path = base / f"{brief['brief_id']}.brief.yaml"
    brief_path.write_text(yaml.dump(brief, allow_unicode=True, sort_keys=False, default_flow_style=False), encoding="utf-8")
    with _runtime_env(generation_snapshot):
        runtime_result = run_full_flow_func(str(brief_path), verbose=False, work_dir=base)
    final_path = runtime_result.get("final_path")
    final_text = Path(final_path).read_text(encoding="utf-8") if final_path else ""
    return {"draft": _title_body_from_text(final_text), "runtime_result": runtime_result, "brief_path": str(brief_path)}


def invoke_runtime_fast_generate_draft(
    generation_snapshot: dict[str, Any],
    *,
    runtime_brief: dict[str, Any] | None = None,
    call_ge_func: Callable[..., str] | None = None,
    work_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Fast runtime path for MAGA /invoke.

    This stage only generates the first draft. Review, rewrite, and recheck are
    handled by invoke_runtime_fast_review_and_rewrite so platform traces can
    explain generation time separately from review/rewrite time.
    """
    from maga_worker.xhs_runtime import call_ge as runtime_call_ge
    from maga_worker.xhs_runtime import ge_prompt_parts

    call_ge_func = call_ge_func or runtime_call_ge

    brief = _resolve_runtime_brief(generation_snapshot, runtime_brief)
    base = Path(work_dir) if work_dir is not None else default_output_dir() / f"runtime_fast_{int(time.time())}"
    base.mkdir(parents=True, exist_ok=True)
    brief_path = base / f"{brief['brief_id']}.brief.yaml"
    brief_path.write_text(yaml.dump(brief, allow_unicode=True, sort_keys=False, default_flow_style=False), encoding="utf-8")

    spec_md = _fast_writing_spec(brief)
    with _runtime_env(generation_snapshot):
        system, style, voice = ge_prompt_parts()
        draft_text = call_ge_func(brief, spec_md, system, style, voice, debug_dir=base, tag="runtime_fast")
    draft = _title_body_from_text(draft_text)
    draft_path = base / "draft.md"
    draft_path.write_text(draft_text, encoding="utf-8")
    return {
        "draft": draft,
        "runtime_result": {
            "mode": "runtime_fast",
            "phase": "generate_draft",
            "draft_path": str(draft_path),
            "brief_path": str(brief_path),
            "debug_dir": str(base),
        },
        "brief_path": str(brief_path),
    }


def invoke_runtime_fast_review_and_rewrite(
    generation_snapshot: dict[str, Any],
    draft: dict[str, Any] | str,
    *,
    runtime_brief: dict[str, Any] | None = None,
    call_ge_func: Callable[..., str] | None = None,
    call_ae_func: Callable[..., dict[str, Any]] | None = None,
    call_legal_review_func: Callable[..., dict[str, Any]] | None = None,
    work_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Review a draft, rewrite when needed, and recheck with runtime_fast reviewers."""
    from maga_worker.xhs_runtime import call_ae as runtime_call_ae
    from maga_worker.xhs_runtime import call_ge as runtime_call_ge
    from maga_worker.xhs_runtime import call_legal_review as runtime_call_legal_review
    from maga_worker.xhs_runtime import ge_prompt_parts

    call_ge_func = call_ge_func or runtime_call_ge
    call_ae_func = call_ae_func or runtime_call_ae
    call_legal_review_func = call_legal_review_func or runtime_call_legal_review

    brief = _resolve_runtime_brief(generation_snapshot, runtime_brief)
    base = Path(work_dir) if work_dir is not None else default_output_dir() / f"runtime_fast_review_{int(time.time())}"
    base.mkdir(parents=True, exist_ok=True)
    brief_path = base / f"{brief['brief_id']}.brief.yaml"
    brief_path.write_text(yaml.dump(brief, allow_unicode=True, sort_keys=False, default_flow_style=False), encoding="utf-8")

    spec_md = _fast_writing_spec(brief)
    draft_text = _draft_text(draft)
    with _runtime_env(generation_snapshot):
        system, style, voice = ge_prompt_parts()
        review_report = _run_runtime_fast_reviews(
            brief,
            draft_text,
            call_ae_func=call_ae_func,
            call_legal_review_func=call_legal_review_func,
            debug_dir=base,
            tag="runtime_fast",
        )
        review_history: list[dict[str, Any]] = []
        rewrite_rounds = 0
        max_rewrite_rounds = 2
        while rewrite_rounds < max_rewrite_rounds:
            rewrite_reason = _fast_review_rewrite_reason(review_report)
            if rewrite_reason is None:
                break
            next_round = rewrite_rounds + 1
            review_history.append({"round": next_round, "rewrite_reason": rewrite_reason, "review": review_report})
            feedback = _feedback_from_fast_review(review_report)
            draft_text = call_ge_func(
                brief,
                spec_md,
                system,
                style,
                voice,
                feedback=feedback,
                prev_draft=draft_text,
                debug_dir=base,
                tag=f"runtime_fast_rewrite_{next_round}",
            )
            rewrite_rounds = next_round
            review_report = _run_runtime_fast_reviews(
                brief,
                draft_text,
                call_ae_func=call_ae_func,
                call_legal_review_func=call_legal_review_func,
                debug_dir=base,
                tag=f"runtime_fast_recheck_{next_round}",
            )
    if review_history:
        review_report["previous_review"] = review_history[0]["review"]
        review_report["rewrite_rounds"] = rewrite_rounds
        review_report["rewrite_reason"] = review_history[0]["rewrite_reason"]
        review_report["review_history"] = review_history
    final_path = base / "final.md"
    final_path.write_text(draft_text, encoding="utf-8")
    final = _title_body_from_text(draft_text)
    return {
        "final": final,
        "draft": final,
        "runtime_result": {
            "mode": "runtime_fast",
            "phase": "review_and_rewrite",
            "final_path": str(final_path),
            "brief_path": str(brief_path),
            "debug_dir": str(base),
        },
        "review_report": review_report,
        "brief_path": str(brief_path),
    }


def _draft_text(draft: dict[str, Any] | str) -> str:
    if isinstance(draft, str):
        return draft
    title = str(draft.get("title") or "小红书笔记").strip()
    body = str(draft.get("body") or "").strip()
    return f"标题：{title}\n正文：{body}".strip()


def _resolve_runtime_brief(
    generation_snapshot: dict[str, Any],
    runtime_brief: dict[str, Any] | None,
) -> dict[str, Any]:
    """Use the compiled brief from interpret_brief, with snapshot fallback for old callers."""
    if isinstance(runtime_brief, dict) and runtime_brief.get("brief_id"):
        return runtime_brief
    return build_runtime_brief_from_snapshot(generation_snapshot)


def _run_runtime_fast_reviews(
    brief: dict[str, Any],
    draft_text: str,
    *,
    call_ae_func: Callable[..., dict[str, Any]],
    call_legal_review_func: Callable[..., dict[str, Any]],
    debug_dir: Path,
    tag: str,
) -> dict[str, Any]:
    review_timeout = _runtime_fast_review_timeout()
    legal_timeout = _runtime_fast_legal_review_timeout()
    review_deadline = time.monotonic() + review_timeout
    legal_deadline = time.monotonic() + legal_timeout
    max_workers = len(RUNTIME_FAST_REVIEW_CODES)
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="runtime-fast-review")
    futures: dict[str, concurrent.futures.Future] = {}
    try:
        for ae_code in RUNTIME_FAST_AE_REVIEW_CODES:
            futures[ae_code] = executor.submit(
                call_ae_func,
                ae_code,
                "score",
                brief,
                draft_text,
                debug_dir=debug_dir,
                tag=tag,
            )
        futures[RUNTIME_FAST_LEGAL_REVIEW_CODE] = executor.submit(
            call_legal_review_func,
            brief,
            draft_text,
            debug_dir=debug_dir,
            tag=tag,
        )

        ae_reviews = {
            ae_code: _review_result_or_error(
                ae_code,
                futures[ae_code],
                max(0.0, review_deadline - time.monotonic()),
                timeout_label=review_timeout,
            )
            for ae_code in RUNTIME_FAST_AE_REVIEW_CODES
        }
        legal_review = _review_result_or_error(
            RUNTIME_FAST_LEGAL_REVIEW_CODE,
            futures[RUNTIME_FAST_LEGAL_REVIEW_CODE],
            max(0.0, legal_deadline - time.monotonic()),
            timeout_label=legal_timeout,
            fail_open=_legal_review_fail_open(),
        )
    finally:
        for future in futures.values():
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
    return _review_report_from_fast_reviews(ae_reviews, legal_review)


def _review_result_or_error(
    review_code: str,
    future: concurrent.futures.Future,
    timeout_seconds: float,
    *,
    timeout_label: float,
    fail_open: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = future.result(timeout=timeout_seconds)
        if not isinstance(result, dict):
            raise TypeError(f"{review_code} returned non-dict result")
        result.setdefault("duration_ms", int((time.monotonic() - started) * 1000))
        return result
    except concurrent.futures.TimeoutError:
        return _review_error_result(review_code, f"timeout after {timeout_label:g}s", fail_open=fail_open)
    except Exception as exc:  # noqa: BLE001 - review failures must be reported as structured review output
        return _review_error_result(review_code, str(exc), fail_open=fail_open)


def _review_error_result(review_code: str, reason: str, *, fail_open: bool) -> dict[str, Any]:
    verdict = "pass" if fail_open else "fail"
    return {
        "score": 1 if fail_open else 0,
        "verdict": verdict,
        "hard_hits": [] if fail_open else [f"{review_code} 审核异常：{reason}"],
        "suggestions": [] if fail_open else [f"请人工确认 {review_code} 审核异常：{reason}"],
        "replacement_needed": [],
        "error": reason,
        "fail_open": fail_open,
    }


def _runtime_fast_review_timeout() -> float:
    return _float_env("XHS_RUNTIME_REVIEW_TIMEOUT_SECONDS", 90.0)


def _runtime_fast_legal_review_timeout() -> float:
    return _float_env("XHS_RUNTIME_LEGAL_REVIEW_TIMEOUT_SECONDS", 15.0)


def _legal_review_fail_open() -> bool:
    return os.environ.get("XHS_RUNTIME_LEGAL_REVIEW_FAIL_OPEN", "1") != "0"


def _float_env(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def default_output_dir() -> Path:
    """Return the repo-local runtime output directory.

    The worker profile directory is versioned static input. Runtime prompts,
    responses, briefs, and final drafts are operational artifacts and must stay
    under `.local` so deploying the profile does not depend on mutable outputs.
    """
    configured = os.environ.get("MAGA_WORKER_OUTPUT_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / ".local" / "worker" / "outputs"


@contextmanager
def _runtime_env(generation_snapshot: dict[str, Any]):
    """Apply MAGA-owned model and prompt bundle overrides for one invocation."""
    model_config = generation_snapshot.get("model_config") or {}
    overrides = {
        "XHS_RUNTIME_MODEL_GE": model_config.get("ge_model"),
        "XHS_RUNTIME_MODEL_AE": model_config.get("ae_model"),
        "XHS_RUNTIME_PROMPT_BUNDLE_JSON": _prompt_bundle_json(generation_snapshot.get("prompt_bundle_snapshot")),
    }
    previous = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            if value:
                os.environ[key] = str(value)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _prompt_bundle_json(prompt_bundle: Any) -> str | None:
    if not isinstance(prompt_bundle, dict) or not prompt_bundle:
        return None
    return json.dumps(prompt_bundle, ensure_ascii=False)


def _fast_writing_spec(brief: dict[str, Any]) -> str:
    campaign = brief.get("campaign") or {}
    maga = brief.get("maga") or {}
    assets = maga.get("assets") or {}
    brief_fields = maga.get("brief") or {}
    diversity = maga.get("diversity_slot") or {}
    painpoint = assets.get("painpoint") or {}
    selling_point = assets.get("selling_point") or {}
    constraints = brief_fields.get("content_constraints") or {}
    safe_expressions = painpoint.get("safe_expressions") or []
    forbidden_terms = _forbidden_terms(assets.get("compliance_rules")) or brief.get("must_avoid") or []
    reference_examples = assets.get("reference_examples") or []
    writing_pattern = assets.get("writing_pattern") or {}
    reference_hint = _reference_hint(reference_examples, writing_pattern)
    return "\n".join(
        line for line in [
            "# Writing Spec",
            "- 品牌/产品：源悦",
            f"- 主题：{campaign.get('topic') or brief.get('product_topic') or ''}",
            f"- 目标人群：{campaign.get('target_audience') or brief.get('target_audience') or ''}",
            f"- 风格：{campaign.get('style') or brief.get('style') or '自然真实'}、{diversity.get('opening_type') or campaign.get('opening_type') or ''}",
            f"- 结构：{diversity.get('structure_type') or campaign.get('structure_type') or '痛点-观察-建议'}",
            f"- 叙事角度：{diversity.get('narrative_focus') or '先共情'}",
            f"- 情绪底色：{diversity.get('emotion') or '真实'}",
            f"- 行动收束：{diversity.get('cta_type') or '轻建议'}",
            f"- 避免同批重复：不要使用 {diversity.get('forbidden_overlap_group') or '同一类'} 的开头套路。",
            f"- 痛点：{painpoint.get('painpoint') or (brief.get('key_painpoints') or [''])[0]}",
            f"- 卖点：{selling_point.get('selling_point') or (brief.get('key_sellingpoints') or [''])[0]}",
            f"- 安全表达：{'、'.join(map(str, safe_expressions))}",
            f"- 禁止表达：{'、'.join(map(str, forbidden_terms))}",
            f"- 字数：{constraints.get('word_count') or '450-650'} 中文字",
            f"- emoji：{constraints.get('emoji') or '少量'}",
            reference_hint,
        ]
        if line and not line.endswith("：")
    )


def _reference_hint(reference_examples: Any, writing_pattern: dict[str, Any]) -> str:
    lines: list[str] = []
    if writing_pattern:
        lines.extend(
            [
                f"- 写法开头：{writing_pattern.get('opening_pattern') or ''}",
                f"- 写法结构：{writing_pattern.get('story_arc') or ''}",
                f"- 卖点植入：{writing_pattern.get('selling_point_placement') or ''}",
                f"- 证据方式：{writing_pattern.get('proof_style') or ''}",
                f"- 收尾方式：{writing_pattern.get('ending_pattern') or ''}",
                f"- 语气特征：{'、'.join(map(str, writing_pattern.get('voice_traits') or []))}",
                f"- 禁止复用参考短语：{'、'.join(map(str, writing_pattern.get('avoid_copy_phrases') or []))}",
            ]
        )
    if reference_examples and isinstance(reference_examples[0], dict):
        lines.extend(
            [
                f"- 来源例文：{reference_examples[0].get('title') or ''}；只用于追溯和辅助理解，不照抄参考标题或正文。",
                f"- 来源例文节奏摘录：{_compact_text(reference_examples[0].get('body'), 90)}",
            ]
        )
    return "\n".join(line for line in lines if line and not line.endswith("："))


def _compact_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _forbidden_terms(compliance_rules: Any) -> list[str]:
    if isinstance(compliance_rules, dict):
        terms = compliance_rules.get("forbidden_terms") or compliance_rules.get("must_avoid") or []
        return [str(term) for term in terms if str(term).strip()]
    if isinstance(compliance_rules, list):
        terms: list[str] = []
        for rule in compliance_rules:
            if not isinstance(rule, dict):
                continue
            if rule.get("forbidden_terms"):
                terms.extend(str(term) for term in rule.get("forbidden_terms") or [])
            elif rule.get("dimension"):
                terms.append(str(rule.get("dimension")).replace("禁止", "").strip())
        return [term for term in terms if term]
    return []


def _fast_review_passed(review: dict[str, Any]) -> bool:
    hard_results = review.get("hard_results")
    if isinstance(hard_results, list):
        return all(bool(item.get("pass")) for item in hard_results if isinstance(item, dict))
    return review.get("score") == 1 or review.get("verdict") in {"pass", "approved"} or review.get("passed") is True


def _fast_review_rewrite_reason(review: dict[str, Any]) -> str | None:
    if not _fast_review_passed(review):
        return "hard_fail"
    if _fast_review_has_soft_suggestions(review):
        return "soft_suggestions"
    return None


def _fast_review_has_soft_suggestions(review: dict[str, Any]) -> bool:
    return bool(review.get("suggestions") or review.get("replacement_needed"))


def _feedback_from_fast_review(review_report: dict[str, Any]) -> str:
    hard_results = review_report.get("hard_results") or []
    suggestions = review_report.get("suggestions") or []
    replacement_needed = review_report.get("replacement_needed") or []
    failed_lines: list[str] = []
    passed_with_evidence_lines: list[str] = []
    for item in hard_results:
        if not isinstance(item, dict):
            continue
        ae_code = item.get("ae_code") or "review"
        evidence = "、".join(str(hit) for hit in item.get("evidence") or [])
        feedback = item.get("feedback") or ""
        line = f"- {ae_code}: {feedback}"
        if evidence:
            line = f"{line}；证据：{evidence}"
        if item.get("pass") is False:
            failed_lines.append(line)
        elif evidence:
            passed_with_evidence_lines.append(line)
    lines = ["请按以下审核反馈做精准修订，只修改问题位置，不要整体重写："]
    if failed_lines:
        lines.append("\n## 硬失败")
        lines.extend(failed_lines)
    if passed_with_evidence_lines:
        lines.append("\n## 已通过但需关注的证据")
        lines.extend(passed_with_evidence_lines)
    if replacement_needed:
        lines.append("\n## 替换建议")
        lines.extend(f"- {_format_replacement(item)}" for item in replacement_needed)
    if suggestions:
        lines.append("\n## 修订建议")
        lines.extend(f"- {item}" for item in suggestions)
    lines.append("\n## 改写边界")
    lines.append("- 禁止新增治疗、改善、治好、解决疾病等医疗化表达。")
    lines.append("- 禁止新增新的时间效果链、专业术语、奶粉成分或未提供的产品事实。")
    lines.append("- 保留原主题、目标人群和已有安全表达，只修正被审核命中的位置。")
    return "\n".join(lines)


def _format_replacement(item: Any) -> str:
    if isinstance(item, dict):
        source = item.get("from") or item.get("source") or item.get("text") or item.get("term") or ""
        target = item.get("to") or item.get("target") or item.get("replacement") or item.get("suggestion") or ""
        if source and target:
            return f"{source} -> {target}"
    return str(item)


def _review_report_from_fast_reviews(
    ae_reviews: dict[str, dict[str, Any]],
    legal_review: dict[str, Any],
) -> dict[str, Any]:
    hard_results = [
        _hard_result_from_fast_review(ae_code, review)
        for ae_code, review in ae_reviews.items()
    ]
    hard_results.append(_hard_result_from_fast_review(RUNTIME_FAST_LEGAL_REVIEW_CODE, legal_review))

    suggestions: list[Any] = []
    replacement_needed: list[Any] = []
    for ae_code, review in [*ae_reviews.items(), (RUNTIME_FAST_LEGAL_REVIEW_CODE, legal_review)]:
        suggestions.extend(_tagged_items(ae_code, review.get("suggestions") or []))
        replacement_needed.extend(_tagged_items(ae_code, review.get("replacement_needed") or []))

    passed = all(item["pass"] for item in hard_results)
    return {
        "hard_results": hard_results,
        "soft_scores": [],
        "rewrite_required": bool(not passed or suggestions or replacement_needed),
        "suggestions": suggestions,
        "replacement_needed": replacement_needed,
        "raw": {
            "ae_reviews": ae_reviews,
            RUNTIME_FAST_LEGAL_REVIEW_CODE: legal_review,
        },
    }


def _hard_result_from_fast_review(ae_code: str, review: dict[str, Any]) -> dict[str, Any]:
    passed = _fast_review_passed(review)
    return {
        "ae_code": ae_code,
        "pass": bool(passed),
        "risk_level": "low" if passed else "high",
        "feedback": review.get("verdict") or review.get("reason") or ("pass" if passed else "fail"),
        "evidence": review.get("hard_hits")
        or review.get("conditional_hits")
        or review.get("keywords")
        or review.get("hit_details")
        or [],
    }


def _tagged_items(ae_code: str, items: list[Any]) -> list[Any]:
    tagged: list[Any] = []
    for item in items:
        if isinstance(item, dict):
            tagged.append({"ae_code": ae_code, **item})
        else:
            tagged.append(f"{ae_code}: {item}")
    return tagged


def _review_report_from_fast_review(review: dict[str, Any]) -> dict[str, Any]:
    passed = review.get("score") == 1 or review.get("verdict") == "pass"
    suggestions = review.get("suggestions") or []
    replacement_needed = review.get("replacement_needed") or []
    return {
        "hard_results": [
            {
                "ae_code": "compliance_redline",
                "pass": bool(passed),
                "risk_level": "low" if passed else "high",
                "feedback": review.get("verdict") or ("pass" if passed else "fail"),
                "evidence": review.get("hard_hits") or review.get("conditional_hits") or [],
            }
        ],
        "soft_scores": [],
        "rewrite_required": bool(not passed or suggestions or replacement_needed),
        "suggestions": suggestions,
        "replacement_needed": replacement_needed,
        "raw": review,
    }


def _title_body_from_text(text: str) -> dict[str, str]:
    title = ""
    body_lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("标题：") or line.startswith("标题:"):
            title = line.split("：", 1)[-1] if "：" in line else line.split(":", 1)[-1]
            title = title.strip()
        elif line.startswith("正文：") or line.startswith("正文:"):
            value = line.split("：", 1)[-1] if "：" in line else line.split(":", 1)[-1]
            body_lines.append(value.strip())
        elif not title:
            title = line.lstrip("# ").strip()
        else:
            body_lines.append(line)
    return {"title": title or "小红书笔记", "body": "\n".join(body_lines).strip() or text.strip() or "正文待生成"}
