"""Run the next 20 a2 礼遇 audit-loop items with generation concurrency 10."""
from __future__ import annotations

import asyncio
import copy
import json
import secrets
import time
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.core.database import async_session_factory
from app.models.content_agent import ContentAgentStageCall
from app.models.maga_assets import AssetRegistry
from app.services.content_agent_service import ContentAgentService
from app.services.content_batch_execution_service import ContentBatchExecutionService
from app.services.content_batch_planner import ContentBatchPlanner
from app.services.content_batch_report_service import ContentBatchReportService
from app.services.executor_invocation_service import ExecutorInvocationClient


ASSET_ID = 1994
ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"
COUNT = 20
CONCURRENCY = 10
CANDIDATE_PATH = Path(
    "/Users/luxifa/maga/outputs/a2_reiyu_v33_usage_merge_20260722/candidate_v33_usage_merge.json"
)
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_v33_usage_merge_audit_v7_20260722")
MODEL_CONFIG = {
    "provider_code": "deepseek",
    "model_code": "deepseek-v4-flash",
    "ge_model": "deepseek-v4-flash",
    "ae_model": "deepseek-v4-flash",
    "temperature": 0.8,
    "max_tokens": 2048,
}


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    candidate_payload = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
    candidate_content = copy.deepcopy(candidate_payload.get("content_json") or {})
    candidate_metadata = copy.deepcopy(candidate_payload.get("metadata_json") or {})
    if len(candidate_content.get("items") or []) != 8:
        raise RuntimeError("merged candidate must contain exactly 8 business rules")
    if candidate_metadata.get("experiment_arm") != "draft_v33_usage_merge":
        raise RuntimeError("candidate source is not the approved merged-path draft")
    candidate_content["allow_repeat_generation"] = True
    candidate_content["default_generation_count"] = COUNT

    client = ExecutorInvocationClient()
    started = time.monotonic()
    try:
        async with async_session_factory() as db:
            production = await db.get(AssetRegistry, ASSET_ID)
            if production is None:
                raise RuntimeError(f"production asset not found: {ASSET_ID}")
            if (
                production.asset_key != ASSET_KEY
                or production.version_no != 32
                or production.status != "active"
                or production.asset_stage != "production"
            ):
                raise RuntimeError(
                    "production asset changed: "
                    f"key={production.asset_key} version={production.version_no} "
                    f"status={production.status} stage={production.asset_stage}"
                )

            candidate = SimpleNamespace(
                id=production.id,
                asset_type=production.asset_type,
                asset_key=production.asset_key,
                display_name=production.display_name,
                version_no=production.version_no,
                status=production.status,
                asset_stage="candidate",
                source_name=production.source_name,
                source_uri=production.source_uri,
                source_hash=production.source_hash,
                content_json=candidate_content,
                metadata_json={
                    **candidate_metadata,
                    "default_generation_count": COUNT,
                    "allow_repeat_generation": True,
                    "run_count": COUNT,
                    "run_concurrency": CONCURRENCY,
                },
            )

            planner = ContentBatchPlanner(db)
            job = await planner._create_article_business_rule_plan(
                candidate,
                requested_count=COUNT,
                rule_id=None,
                source_row_no=None,
                keyword_asset_key=None,
                prompt_mode=None,
                articles_per_prompt=1,
                postprocess_mode=None,
                draft_corpus=None,
                draft_selling_painpoint_group=None,
                draft_rule_id=None,
                draft_source_row_no=None,
                model_config=MODEL_CONFIG,
                model_config_rotation=None,
                created_by="codex_a2_usage_merge_audit_v7",
            )
            job_id = int(job.id)
            job_count = int(job.count)
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
                limit=job_count,
                concurrency=CONCURRENCY,
                created_by="codex_a2_usage_merge_audit_v7",
            )
            await db.commit()
            db.expire_all()
            report = (await ContentBatchReportService(db).get_batch_report(job_id)).model_dump(mode="json")
            generated = [
                item
                for item in report.get("items") or []
                if item.get("run_id") and item.get("body")
            ]
            selected = secrets.choice(generated)
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

        elapsed_seconds = round(time.monotonic() - started, 3)
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
            "attempted": execution.requested_limit,
            "raw_generated": execution.generated_count,
            "execution_failed": execution.failed_count,
            "concurrency": CONCURRENCY,
            "elapsed_seconds": elapsed_seconds,
            "candidate_persisted": False,
            "candidate_source": str(CANDIDATE_PATH),
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
