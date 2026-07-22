from __future__ import annotations

import asyncio
import argparse
import json
import random
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.api.v1.endpoints.content_agent import _model_config_with_maga_defaults
from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.core.database import async_session_factory
from app.models.content_agent import ContentBatchItem
from app.services.content_agent_service import ContentAgentService
from app.services.content_batch_execution_service import ContentBatchExecutionService
from app.services.content_batch_planner import ContentBatchPlanner
from app.services.content_batch_report_service import ContentBatchReportService
from app.services.executor_invocation_service import ExecutorInvocationClient
from app.services.unified_content_generation_service import UnifiedContentGenerationService
from scripts.migrate_wangyue_chunyue_layered_framework import _parse_wangyue_corpus


COUNT = 10
OUTPUT_ROOT = Path(
    "/Users/luxifa/maga/outputs/0705_wangyue_product_relation_evidence/"
    "layered_framework_migration_20260721"
)
PAIRS = {
    "wangyue": (
        "wangyue_v3_core_storyline_article_rules",
        "wangyue_v81_layered_framework_probe",
    ),
    "chunyue": (
        "chunyue_v2_painpoint_sellingpoint_article_rules",
        "chunyue_v28_layered_framework_probe",
    ),
}


async def _items(session: Any, batch_id: int) -> list[ContentBatchItem]:
    result = await session.execute(
        select(ContentBatchItem)
        .where(ContentBatchItem.batch_id == batch_id)
        .order_by(ContentBatchItem.item_no)
    )
    return list(result.scalars().all())


def _fixed_inputs(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        key: plan.get(key)
        for key in (
            "rule_id",
            "selling_painpoint_group",
            "selling_painpoint_expression",
            "selling_painpoint_expression_source_row_no",
        )
    }


def _prompt_semantics(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        key: plan.get(key)
        for key in (
            "generation_instruction",
            "content_direction",
            "activity_material",
            "selling_expression",
            "selling_expression_note",
            "hard_boundaries",
            "writing_requirements",
            "generation_requirements",
            "variation_slots",
        )
    }


def _normalized_prompt_text(value: str) -> str:
    return value.replace("本篇素材中的灵感线索", "本篇灵感线索")


def _validate_pair(
    brand: str,
    source_items: list[ContentBatchItem],
    probe_items: list[ContentBatchItem],
    source_prompts: list[str],
    probe_prompts: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_item, probe_item, source_prompt, probe_prompt in zip(
        source_items, probe_items, source_prompts, probe_prompts, strict=True
    ):
        source_plan = source_item.plan_json or {}
        probe_plan = probe_item.plan_json or {}
        if _fixed_inputs(source_plan) != _fixed_inputs(probe_plan):
            raise RuntimeError(f"{brand} item {source_item.item_no} fixed inputs drifted")
        if "不使用灵感线索" in probe_prompt:
            raise RuntimeError(f"{brand} item {probe_item.item_no} leaked inspiration sentinel")

        if brand == "chunyue" or source_plan.get("prompt_mode") == "layered_article":
            if _prompt_semantics(source_plan) != _prompt_semantics(probe_plan):
                raise RuntimeError(f"{brand} item {source_item.item_no} prompt semantics drifted")
        else:
            parsed = _parse_wangyue_corpus(str(source_plan.get("corpus") or ""))
            expected = {
                "generation_instruction": parsed["generation_instruction"],
                "content_direction": parsed["content_direction"],
                "hard_boundaries": parsed["hard_boundaries"],
                "writing_requirements": parsed["writing_requirements"],
            }
            actual = {key: probe_plan.get(key) for key in expected}
            if actual != expected:
                raise RuntimeError(f"wangyue item {source_item.item_no} migrated fields drifted")
            normalized_source_prompt = _normalized_prompt_text(source_prompt)
            normalized_probe_prompt = _normalized_prompt_text(probe_prompt)
            for value in (
                expected["generation_instruction"],
                expected["content_direction"],
                *expected["hard_boundaries"],
                *expected["writing_requirements"],
                *(probe_plan.get("generation_requirements") or []),
                str(probe_plan.get("selling_painpoint_expression") or ""),
            ):
                normalized_value = _normalized_prompt_text(str(value))
                if normalized_value and (
                    normalized_value not in normalized_source_prompt
                    or normalized_value not in normalized_probe_prompt
                ):
                    raise RuntimeError(
                        f"wangyue item {source_item.item_no} rendered prompt lost: {value[:40]}"
                    )

        rows.append(
            {
                "item_no": source_item.item_no,
                "rule_id": source_plan.get("rule_id"),
                "selling_expression_source_row_no": source_plan.get(
                    "selling_painpoint_expression_source_row_no"
                ),
                "source_prompt_chars": len(source_prompt),
                "probe_prompt_chars": len(probe_prompt),
                "probe_variation_slots": probe_plan.get("variation_slots") or [],
                "semantic_validation": "pass",
            }
        )
    return rows


async def _plan_pair(brand: str, source_key: str, probe_key: str) -> dict[str, Any]:
    async with async_session_factory() as session:
        model_config = await _model_config_with_maga_defaults(session, {})
        planner = ContentBatchPlanner(session)
        jobs = []
        for label, asset_key in (("source", source_key), ("probe", probe_key)):
            job = await planner.create_batch_plan(
                asset_key=asset_key,
                product_topic=None,
                target_audience=None,
                persona_target=None,
                style=None,
                count=COUNT,
                articles_per_prompt=1,
                postprocess_mode="audit_only",
                keyword_asset_key=None,
                prompt_mode=None,
                model_config=model_config,
                created_by=f"codex-layered-framework-ab-{brand}-{label}",
            )
            jobs.append(job)
        await session.commit()

        source_items = await _items(session, jobs[0].id)
        probe_items = await _items(session, jobs[1].id)
        generation = UnifiedContentGenerationService(session)
        source_prompts = []
        probe_prompts = []
        for item in source_items:
            snapshot = await generation.build_snapshot(
                content_type="article",
                business_rule=item.plan_json or {},
                item_no=item.item_no,
                output_fields=["title", "body"],
                model_config=model_config,
            )
            source_prompts.append(str(snapshot.input_snapshot.get("rendered_prompt") or ""))
        for item in probe_items:
            snapshot = await generation.build_snapshot(
                content_type="article",
                business_rule=item.plan_json or {},
                item_no=item.item_no,
                output_fields=["title", "body"],
                model_config=model_config,
            )
            probe_prompts.append(str(snapshot.input_snapshot.get("rendered_prompt") or ""))

        validation = _validate_pair(
            brand, source_items, probe_items, source_prompts, probe_prompts
        )
        return {
            "brand": brand,
            "source_key": source_key,
            "probe_key": probe_key,
            "source_batch_id": jobs[0].id,
            "probe_batch_id": jobs[1].id,
            "validation": validation,
        }


async def _execute(
    batch_id: int,
    label: str,
    output_dir: Path,
    *,
    run_business_review: bool,
) -> dict[str, Any]:
    async with async_session_factory() as session:
        executor = await ContentAgentService(session).get_executor(DEFAULT_EXECUTOR_CODE)
        if executor is None:
            raise RuntimeError(f"executor not found: {DEFAULT_EXECUTOR_CODE}")
        invocation_client = ExecutorInvocationClient()
        try:
            service = ContentBatchExecutionService(
                session,
                invocation_client=invocation_client,
                callback_base_url="/api/v1/content-agent",
                executor_code=DEFAULT_EXECUTOR_CODE,
            )
            execution = await service.execute_batch_items(
                batch_id,
                limit=COUNT,
                created_by=f"codex-layered-framework-ab-{label}",
            )
            await session.commit()
            review = None
            if run_business_review:
                review = await service.review_business_usability_items(
                    batch_id,
                    force=True,
                    limit=COUNT,
                    concurrency=4,
                )
                await session.commit()
            session.expire_all()
            report = await ContentBatchReportService(session).get_batch_report(
                batch_id, include_details=True
            )
        finally:
            await invocation_client.http_client.aclose()

    payload = {
        "batch_id": batch_id,
        "label": label,
        "execution": {
            "requested_limit": execution.requested_limit,
            "generated_count": execution.generated_count,
            "failed_count": execution.failed_count,
        },
        "business_usability_review": asdict(review) if review is not None else None,
        "report": report.model_dump(mode="json"),
    }
    response_path = output_dir / f"{label}_batch{batch_id}_report.json"
    response_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    generated = [
        item
        for item in payload["report"].get("items") or []
        if item.get("status") == "generated"
        and str((item.get("generation_snapshot") or {}).get("rendered_prompt") or "").strip()
    ]
    sampled = random.Random(batch_id).choice(generated)
    prompt_path = output_dir / f"{label}_batch{batch_id}_item{sampled['item_no']}_rendered_prompt.md"
    prompt_path.write_text(
        "\n".join(
            [
                f"# {label} complete rendered prompt",
                "",
                f"- batch_id: `{batch_id}`",
                f"- item_no: `{sampled['item_no']}`",
                f"- title: {sampled.get('title') or ''}",
                "",
                "```text",
                str((sampled.get("generation_snapshot") or {}).get("rendered_prompt") or ""),
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "batch_id": batch_id,
        "label": label,
        "report_path": str(response_path),
        "prompt_path": str(prompt_path),
        "execution": payload["execution"],
        "business_usability_review": payload["business_usability_review"],
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand", choices=("both", "wangyue", "chunyue"), default="both")
    parser.add_argument("--skip-business-review", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    started_at = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = OUTPUT_ROOT / f"ab_{started_at}"
    output_dir.mkdir(parents=True, exist_ok=True)
    planned = []
    selected_pairs = PAIRS if args.brand == "both" else {args.brand: PAIRS[args.brand]}
    for brand, (source_key, probe_key) in selected_pairs.items():
        planned.append(await _plan_pair(brand, source_key, probe_key))
    validation_path = output_dir / "prompt_semantic_validation.json"
    validation_path.write_text(json.dumps(planned, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.validate_only:
        result = {
            "output_dir": str(output_dir),
            "validation_path": str(validation_path),
            "runs": [],
        }
        result_path = output_dir / "ab_result.json"
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({**result, "result_path": str(result_path)}, ensure_ascii=False, indent=2))
        return

    runs = []
    for pair in planned:
        runs.append(
            await _execute(
                int(pair["source_batch_id"]),
                f"{pair['brand']}_source",
                output_dir,
                run_business_review=not args.skip_business_review,
            )
        )
        runs.append(
            await _execute(
                int(pair["probe_batch_id"]),
                f"{pair['brand']}_probe",
                output_dir,
                run_business_review=not args.skip_business_review,
            )
        )
    result = {
        "output_dir": str(output_dir),
        "validation_path": str(validation_path),
        "runs": runs,
    }
    result_path = output_dir / "ab_result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**result, "result_path": str(result_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
