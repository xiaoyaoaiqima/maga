from __future__ import annotations

import asyncio
import copy
import json
import random
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.core.database import async_session_factory
from app.models.maga_assets import AssetRegistry
from app.services.a2_reiyu_batch_audit_service import A2ReiyuBatchAuditService
from app.services.content_agent_orchestrator import ContentAgentOrchestrator
from app.services.content_agent_service import ContentAgentService
from app.services.content_batch_execution_service import ContentBatchExecutionService
from app.services.content_batch_planner import ContentBatchPlanner
from app.services.content_batch_report_service import (
    ContentBatchReportService,
    _article_pool_export_items,
    _build_article_pool_csv,
)
from app.services.executor_invocation_service import ExecutorInvocationClient


ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"
SOURCE_ROWS = set(range(9, 17))
COUNT = 20
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_v41_20_20260723")
MODEL_CONFIG = {
    "provider_code": "deepseek",
    "model_code": "deepseek-v4-flash",
    "ge_model": "deepseek-v4-flash",
    "ae_model": "deepseek-v4-flash",
    "temperature": 0.8,
    "max_tokens": 2048,
}


def filtered_asset(asset: AssetRegistry) -> SimpleNamespace:
    content = copy.deepcopy(asset.content_json or {})
    items = [
        item
        for item in content.get("items") or []
        if int(item.get("source_row_no") or 0) in SOURCE_ROWS
    ]
    if len(items) != len(SOURCE_ROWS):
        raise RuntimeError(f"expected {len(SOURCE_ROWS)} can rules, found {len(items)}")
    content["items"] = items
    return SimpleNamespace(
        id=asset.id,
        asset_type=asset.asset_type,
        asset_key=asset.asset_key,
        display_name=asset.display_name,
        version_no=asset.version_no,
        status=asset.status,
        asset_stage=asset.asset_stage,
        source_name=asset.source_name,
        source_uri=asset.source_uri,
        source_hash=asset.source_hash,
        content_json=content,
        metadata_json=copy.deepcopy(asset.metadata_json or {}),
    )


async def main() -> None:
    invocation_client = ExecutorInvocationClient()
    try:
        async with async_session_factory() as db:
            result = await db.execute(
                select(AssetRegistry)
                .where(
                    AssetRegistry.asset_key == ASSET_KEY,
                    AssetRegistry.asset_stage == "production",
                    AssetRegistry.status == "active",
                )
                .order_by(AssetRegistry.version_no.desc(), AssetRegistry.id.desc())
                .limit(1)
            )
            asset = result.scalar_one()
            if asset.id != 2007 or asset.version_no != 41:
                raise RuntimeError(
                    f"production asset changed: id={asset.id}, version={asset.version_no}"
                )
            executor = await ContentAgentService(db).get_executor(DEFAULT_EXECUTOR_CODE)
            if executor is None:
                raise RuntimeError(f"executor {DEFAULT_EXECUTOR_CODE} not found")
            model_config = await ContentAgentOrchestrator(
                db,
                callback_base_url="/api/v1/content-agent",
            ).hydrate_model_config(dict(MODEL_CONFIG))
            job = await ContentBatchPlanner(db)._create_article_business_rule_plan(
                filtered_asset(asset),
                requested_count=COUNT,
                rule_id=None,
                source_row_no=None,
                keyword_asset_key=None,
                prompt_mode=None,
                articles_per_prompt=1,
                postprocess_mode="generate_only",
                draft_corpus=None,
                draft_selling_painpoint_group=None,
                draft_rule_id=None,
                draft_source_row_no=None,
                model_config=model_config,
                model_config_rotation=None,
                created_by="codex_a2_reiyu_v41_can_20",
            )
            batch_id = job.id
            await db.commit()
            print(json.dumps({"stage": "planned", "batch_id": batch_id}, ensure_ascii=False), flush=True)

            execution = await ContentBatchExecutionService(
                db,
                invocation_client=invocation_client,
                callback_base_url="/api/v1/content-agent",
                executor_code=DEFAULT_EXECUTOR_CODE,
            ).execute_batch_items(
                batch_id,
                limit=job.count,
                created_by="codex_a2_reiyu_v41_can_20",
            )
            await db.commit()
            print(
                json.dumps(
                    {
                        "stage": "generated",
                        "batch_id": batch_id,
                        "generated": execution.generated_count,
                        "failed": execution.failed_count,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

            audit_service = A2ReiyuBatchAuditService(db)
            await audit_service.queue(batch_id, concurrency=10)
            await db.commit()
            audit_result = await audit_service.run(batch_id)
            print(
                json.dumps(
                    {
                        "stage": "audited",
                        "batch_id": batch_id,
                        "audit_result": asdict(audit_result) if audit_result else None,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

            db.expire_all()
            report = await ContentBatchReportService(db).get_batch_report(
                batch_id,
                include_details=True,
            )

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = OUTPUT_DIR / f"batch{batch_id}_full_report.json"
        report_path.write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        article_pool_path = OUTPUT_DIR / f"batch{batch_id}_machine_direct_pool.csv"
        article_pool_path.write_bytes(_build_article_pool_csv(report))

        exportable = _article_pool_export_items(report.items)
        prompt_item = random.Random(20260723).choice(exportable or report.items)
        snapshot = prompt_item.generation_snapshot or {}
        prompt_path = OUTPUT_DIR / f"batch{batch_id}_随机完整Prompt_item{prompt_item.item_no}.md"
        prompt_path.write_text(
            "\n".join(
                [
                    f"# A2礼遇v41集罐20篇随机完整Prompt",
                    "",
                    f"- batch_id: {batch_id}",
                    f"- item_no: {prompt_item.item_no}",
                    f"- title: {prompt_item.title or ''}",
                    "",
                    "## 完整生文 Prompt",
                    "",
                    str(snapshot.get("rendered_prompt") or ""),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        summary = {
            "batch_id": batch_id,
            "batch_code": report.batch_code,
            "asset_id": 2007,
            "asset_version": 41,
            "source_rows": sorted(SOURCE_ROWS),
            "attempted": COUNT,
            "raw_generated": execution.generated_count,
            "generation_failed": execution.failed_count,
            "machine_final_pass": report.summary.hard_pass_count,
            "machine_direct_pool_csv_rows": len(exportable),
            "report_path": str(report_path),
            "article_pool_path": str(article_pool_path),
            "prompt_path": str(prompt_path),
        }
        (OUTPUT_DIR / f"batch{batch_id}_run_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"stage": "complete", **summary}, ensure_ascii=False), flush=True)
    finally:
        await invocation_client.http_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
