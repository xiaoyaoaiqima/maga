from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.core.database import async_session_factory
from app.models.content_agent import ContentBatchItem
from app.models.maga_assets import AssetRegistry
from app.services.content_agent_service import ContentAgentService
from app.services.content_batch_execution_service import ContentBatchExecutionService
from app.services.content_batch_planner import ContentBatchPlanner
from app.services.content_batch_report_service import ContentBatchReportService
from app.services.executor_invocation_service import ExecutorInvocationClient


ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"
PRODUCTION_ASSET_ID = 1988
CANDIDATE_ASSET_ID = 1989
SOURCE_ROW_NO = 9
COUNT = 10
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_risk_polarity_20260722")


async def set_candidate_as_planning_source() -> None:
    async with async_session_factory() as session:
        production = await session.get(AssetRegistry, PRODUCTION_ASSET_ID)
        candidate = await session.get(AssetRegistry, CANDIDATE_ASSET_ID)
        if production is None or candidate is None:
            raise RuntimeError("a2礼遇 production/candidate asset not found")
        production.status = "archived"
        candidate.status = "active"
        candidate.asset_stage = "production"
        await session.commit()


async def restore_asset_stages() -> None:
    async with async_session_factory() as session:
        production = await session.get(AssetRegistry, PRODUCTION_ASSET_ID)
        candidate = await session.get(AssetRegistry, CANDIDATE_ASSET_ID)
        if production is None or candidate is None:
            raise RuntimeError("a2礼遇 production/candidate asset not found")
        production.status = "active"
        production.asset_stage = "production"
        candidate.status = "active"
        candidate.asset_stage = "candidate"
        await session.commit()


async def load_items(batch_id: int) -> list[ContentBatchItem]:
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(ContentBatchItem)
                    .where(ContentBatchItem.batch_id == batch_id)
                    .order_by(ContentBatchItem.item_no)
                )
            )
            .scalars()
            .all()
        )


async def execute_batch(batch_id: int) -> dict:
    async with async_session_factory() as session:
        executor = await ContentAgentService(session).get_executor(DEFAULT_EXECUTOR_CODE)
        if executor is None:
            raise RuntimeError(f"executor not found: {DEFAULT_EXECUTOR_CODE}")
        client = ExecutorInvocationClient()
        try:
            execution = await ContentBatchExecutionService(
                session,
                invocation_client=client,
                callback_base_url="/api/v1/content-agent",
                executor_code=DEFAULT_EXECUTOR_CODE,
            ).execute_batch_items(
                batch_id,
                limit=COUNT,
                created_by="codex-a2-risk-polarity-probe",
            )
            await session.commit()
            session.expire_all()
            report = await ContentBatchReportService(session).get_batch_report(
                batch_id,
                include_details=True,
            )
        finally:
            await client.http_client.aclose()
    return {
        "execution": {
            "requested_limit": execution.requested_limit,
            "generated_count": execution.generated_count,
            "failed_count": execution.failed_count,
        },
        "report": report.model_dump(mode="json"),
    }


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    batch_id: int | None = None
    try:
        await set_candidate_as_planning_source()
        async with async_session_factory() as session:
            job = await ContentBatchPlanner(session).create_batch_plan(
                asset_key=ASSET_KEY,
                source_row_no=SOURCE_ROW_NO,
                product_topic=None,
                target_audience="普通宝妈",
                style="纯分享",
                count=COUNT,
                model_config=None,
                created_by="codex-a2-risk-polarity-probe",
            )
            batch_id = job.id
            await session.commit()

        result = await execute_batch(batch_id)
        items = await load_items(batch_id)
        payload = {
            "batch_id": batch_id,
            "candidate_asset_id": CANDIDATE_ASSET_ID,
            "source_row_no": SOURCE_ROW_NO,
            **result,
            "items": [
                {
                    "item_no": item.item_no,
                    "status": item.status,
                    "title": item.title,
                    "body": item.body,
                    "quality_json": item.quality_json,
                    "plan_json": item.plan_json,
                }
                for item in items
            ],
        }
        output_path = OUTPUT_DIR / f"batch{batch_id}_response.json"
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "batch_id": batch_id,
                    "output_path": str(output_path),
                    "summary": result["report"]["summary"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        await restore_asset_stages()


if __name__ == "__main__":
    asyncio.run(main())
