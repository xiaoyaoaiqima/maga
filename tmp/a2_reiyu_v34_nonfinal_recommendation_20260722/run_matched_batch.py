"""Clone batch 808 plans and only remove the forced final recommendation placement."""
from __future__ import annotations

import asyncio
import copy
import json
import uuid
from pathlib import Path

from sqlalchemy import select

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.core.database import async_session_factory
from app.models.content_agent import ContentAgentStageCall, ContentBatchItem, ContentBatchJob
from app.services.content_agent_service import ContentAgentService
from app.services.content_batch_execution_service import ContentBatchExecutionService
from app.services.content_batch_report_service import ContentBatchReportService
from app.services.executor_invocation_service import ExecutorInvocationClient


BASELINE_BATCH_ID = 808
COUNT = 10
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_v34_nonfinal_recommendation_20260722")
NEW_RULE = (
    "活动和使用感受里能自然看出她更认可a2、愿意向熟人推荐即可，"
    "不规定放在结尾，也不要求另起一段集中总结。（直接说a2，不要用品牌指代）"
)

FULL_LINE_REPLACEMENTS = {
    "综上，再结合自己消费者视角的感受自然表达品牌认可，非常愿意推荐a2至初。",
    "结尾自然表达对a2至初的认可和强烈推荐意愿。（直接说a2，不要用品牌指代）",
    "结尾自然表达对a2至初的认可和强烈推荐意愿。",
    "最后自然表达对a2的认可和推荐意愿。（直接说a2，不要用品牌指代）",
    "最后另起一段，表达自己对a2至初的推荐意愿。（直接说a2，不要用品牌指代）",
    "最后自然表达对a2的认可。（直接说a2，不要用品牌指代）",
}


def transform_direction(text: str) -> str:
    result: list[str] = []
    inserted = False
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if line in FULL_LINE_REPLACEMENTS:
            if not inserted:
                result.append(NEW_RULE)
                inserted = True
            continue

        inline_suffixes = [
            "，最后自然表达品牌认可和强烈的推荐意愿。",
            "。结尾自然表达对a2的认可和强烈推荐意愿。",
        ]
        matched = False
        for suffix in inline_suffixes:
            if suffix in line:
                prefix = line.replace(suffix, "。").strip()
                if prefix:
                    result.append(prefix)
                if not inserted:
                    result.append(NEW_RULE)
                    inserted = True
                matched = True
                break
        if not matched:
            result.append(raw_line)

    transformed = "\n".join(result).strip()
    if transformed != str(text or "").strip() and NEW_RULE not in transformed:
        raise RuntimeError("placement rule changed without inserting the replacement")
    return transformed


def transformed_plan(plan: dict) -> tuple[dict, dict]:
    original = copy.deepcopy(plan)
    updated = copy.deepcopy(plan)
    changed_fields: list[str] = []

    for field in ("content_direction", "corpus"):
        before = str(updated.get(field) or "")
        after = transform_direction(before)
        if after != before:
            updated[field] = after
            changed_fields.append(field)

    for slot in updated.get("variation_slots") or []:
        if str(slot.get("slot_code") or "") != "content_direction":
            continue
        before = str(slot.get("value") or "")
        after = transform_direction(before)
        if after != before:
            slot["value"] = after
            changed_fields.append("variation_slots.content_direction")

    if "variation_slots.content_direction" not in changed_fields:
        raise RuntimeError("selected content direction did not contain a final-placement rule")

    allowed_top_level = {"content_direction", "corpus", "variation_slots"}
    top_level_diffs = {
        key
        for key in set(original) | set(updated)
        if original.get(key) != updated.get(key)
    }
    unexpected = top_level_diffs - allowed_top_level
    if unexpected:
        raise RuntimeError(f"unexpected top-level plan diffs: {sorted(unexpected)}")

    original_slots = original.get("variation_slots") or []
    updated_slots = updated.get("variation_slots") or []
    if len(original_slots) != len(updated_slots):
        raise RuntimeError("variation slot count changed")
    for before, after in zip(original_slots, updated_slots):
        if str(before.get("slot_code") or "") == "content_direction":
            before_copy = {**before, "value": after.get("value")}
            if before_copy != after:
                raise RuntimeError("content direction slot metadata changed")
        elif before != after:
            raise RuntimeError(f"non-target slot changed: {before.get('slot_code')}")

    return updated, {"changed_fields": changed_fields}


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    client = ExecutorInvocationClient()
    try:
        async with async_session_factory() as db:
            baseline_job = await db.get(ContentBatchJob, BASELINE_BATCH_ID)
            if baseline_job is None:
                raise RuntimeError(f"baseline batch not found: {BASELINE_BATCH_ID}")
            baseline_items = list(
                (
                    await db.execute(
                        select(ContentBatchItem)
                        .where(ContentBatchItem.batch_id == BASELINE_BATCH_ID)
                        .order_by(ContentBatchItem.item_no)
                    )
                )
                .scalars()
                .all()
            )
            if len(baseline_items) != COUNT:
                raise RuntimeError(f"expected {COUNT} baseline plans, got {len(baseline_items)}")

            job = ContentBatchJob(
                batch_code=f"batch_{uuid.uuid4().hex[:12]}",
                asset_key=baseline_job.asset_key,
                product_topic=baseline_job.product_topic,
                target_audience=baseline_job.target_audience,
                style=baseline_job.style,
                count=COUNT,
                status="planned",
                strategy_json={
                    **copy.deepcopy(baseline_job.strategy_json or {}),
                    "experiment": "a2_reiyu_nonfinal_recommendation_placement",
                    "matched_baseline_batch_id": BASELINE_BATCH_ID,
                    "candidate_persisted": False,
                },
                diversity_plan_json=copy.deepcopy(baseline_job.diversity_plan_json or {}),
                created_by="codex_a2_nonfinal_recommendation_matched",
            )
            db.add(job)
            await db.flush()
            job_id = int(job.id)

            audit_items: list[dict] = []
            for source_item in baseline_items:
                plan, audit = transformed_plan(source_item.plan_json or {})
                db.add(
                    ContentBatchItem(
                        batch_id=job_id,
                        item_no=source_item.item_no,
                        status="planned",
                        plan_json=plan,
                    )
                )
                audit_items.append({"item_no": source_item.item_no, **audit})
            await db.commit()

            executor = await ContentAgentService(db).get_executor(DEFAULT_EXECUTOR_CODE)
            if executor is None:
                raise RuntimeError(f"executor not found: {DEFAULT_EXECUTOR_CODE}")
            execution = await ContentBatchExecutionService(
                db,
                invocation_client=client,
                callback_base_url="/api/v1/content-agent",
                executor_code=DEFAULT_EXECUTOR_CODE,
            ).execute_batch_items(
                job_id,
                limit=COUNT,
                created_by="codex_a2_nonfinal_recommendation_matched",
            )
            await db.commit()
            db.expire_all()
            report = (await ContentBatchReportService(db).get_batch_report(job_id)).model_dump(mode="json")
            generated = [item for item in report.get("items") or [] if item.get("run_id") and item.get("body")]
            selected = generated[len(generated) // 2]
            stage = (
                await db.execute(
                    select(ContentAgentStageCall)
                    .where(
                        ContentAgentStageCall.run_id == int(selected["run_id"]),
                        ContentAgentStageCall.capability == "content.generate",
                    )
                    .order_by(ContentAgentStageCall.sequence_no.asc())
                    .limit(1)
                )
            ).scalar_one()

        report_path = OUTPUT_DIR / f"batch{job_id}_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        prompt_path = OUTPUT_DIR / f"batch{job_id}_随机完整Prompt_item{selected['item_no']}.md"
        prompt_path.write_text(
            f"# batch {job_id}｜item {selected['item_no']}｜{selected.get('title') or ''}\n\n"
            f"{str((stage.input_snapshot or {}).get('rendered_prompt') or '').strip()}\n",
            encoding="utf-8",
        )
        manifest = {
            "batch_id": job_id,
            "baseline_batch_id": BASELINE_BATCH_ID,
            "attempted": execution.requested_limit,
            "raw_generated": execution.generated_count,
            "execution_failed": execution.failed_count,
            "candidate_persisted": False,
            "changed_rule": NEW_RULE,
            "plan_audit": audit_items,
            "report_path": str(report_path),
            "prompt_path": str(prompt_path),
        }
        (OUTPUT_DIR / "experiment_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    finally:
        await client.http_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
