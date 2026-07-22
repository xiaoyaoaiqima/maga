"""Run one reproducible a2 礼遇 v29 candidate release-validation batch."""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.core.database import async_session_factory
from app.models.maga_assets import AssetRegistry
from app.services.content_agent_service import ContentAgentService
from app.services.content_batch_execution_service import ContentBatchExecutionService
from app.services.content_batch_planner import ContentBatchPlanner
from app.services.content_batch_report_service import ContentBatchReportService
from app.services.executor_invocation_service import ExecutorInvocationClient


ASSET_ID = 1989
ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"
ASSET_VERSION = 29
MODEL_CONFIG = {
    "provider_code": "deepseek",
    "model_code": "deepseek-v4-flash",
    "ge_model": "deepseek-v4-flash",
    "ae_model": "deepseek-v4-flash",
    "temperature": 0.8,
    "max_tokens": 2048,
}


def _rotated_asset(
    asset: AssetRegistry,
    offset: int,
    source_row_nos: list[int] | None = None,
) -> SimpleNamespace:
    content = copy.deepcopy(asset.content_json or {})
    items = list(content.get("items") or [])
    if source_row_nos:
        selected = set(source_row_nos)
        items = [item for item in items if item.get("source_row_no") in selected]
    if not items:
        raise RuntimeError("candidate asset has no business-rule items")
    normalized_offset = offset % len(items)
    content["items"] = items[normalized_offset:] + items[:normalized_offset]
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


async def _run(
    *,
    asset_id: int,
    asset_version: int,
    offset: int,
    source_row_no: int | None,
    source_row_nos: list[int] | None,
    count: int,
    output_dir: Path,
) -> dict:
    invocation_client = ExecutorInvocationClient()
    try:
        async with async_session_factory() as db:
            asset = await db.get(AssetRegistry, asset_id)
            if asset is None:
                raise RuntimeError(f"candidate asset {asset_id} not found")
            if (
                asset.asset_key != ASSET_KEY
                or asset.version_no != asset_version
                or asset.asset_stage != "candidate"
                or asset.status != "active"
            ):
                raise RuntimeError(
                    "candidate asset state changed: "
                    f"key={asset.asset_key} version={asset.version_no} "
                    f"stage={asset.asset_stage} status={asset.status}"
                )

            executor = await ContentAgentService(db).get_executor(DEFAULT_EXECUTOR_CODE)
            if executor is None:
                raise RuntimeError(f"executor {DEFAULT_EXECUTOR_CODE} not found")

            job = await ContentBatchPlanner(db)._create_article_business_rule_plan(
                _rotated_asset(asset, offset, source_row_nos),
                requested_count=count,
                rule_id=None,
                source_row_no=source_row_no,
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
                created_by="codex_a2_v29_release_validation",
            )
            job_id = job.id
            await db.commit()

            execution = await ContentBatchExecutionService(
                db,
                invocation_client=invocation_client,
                callback_base_url="/api/v1/content-agent",
                executor_code=DEFAULT_EXECUTOR_CODE,
            ).execute_batch_items(job_id, limit=job.count, created_by="codex_a2_v29_release_validation")
            await db.commit()
            db.expire_all()
            report = await ContentBatchReportService(db).get_batch_report(job_id)

        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"batch{job_id}_report.json"
        report_path.write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result = {
            "batch_id": job_id,
            "asset_id": asset_id,
            "asset_version": asset_version,
            "rotation_offset": offset,
            "source_row_no": source_row_no,
            "source_row_nos": source_row_nos,
            "requested": execution.requested_limit,
            "generated": execution.generated_count,
            "failed": execution.failed_count,
            "report_path": str(report_path),
        }
        print(json.dumps(result, ensure_ascii=False))
        return result
    finally:
        await invocation_client.http_client.aclose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-id", type=int, default=ASSET_ID)
    parser.add_argument("--asset-version", type=int, default=ASSET_VERSION)
    parser.add_argument("--rotation-offset", type=int, required=True)
    parser.add_argument("--source-row-no", type=int)
    parser.add_argument("--source-row-nos")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source_row_nos = (
        [int(value.strip()) for value in args.source_row_nos.split(",") if value.strip()]
        if args.source_row_nos
        else None
    )
    if args.source_row_no is not None and source_row_nos:
        parser.error("--source-row-no and --source-row-nos are mutually exclusive")
    asyncio.run(
        _run(
            asset_id=args.asset_id,
            asset_version=args.asset_version,
            offset=args.rotation_offset,
            source_row_no=args.source_row_no,
            source_row_nos=source_row_nos,
            count=args.count,
            output_dir=args.output_dir,
        )
    )


if __name__ == "__main__":
    main()
