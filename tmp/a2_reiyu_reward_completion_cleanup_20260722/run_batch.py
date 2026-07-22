from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select, update

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE
from app.core.database import async_session_factory
from app.models.content_agent import ContentBatchItem
from app.models.maga_assets import AssetRegistry
from app.services.business_rule_asset_types import ARTICLE_BUSINESS_RULE_ASSET_TYPES
from app.services.content_agent_service import ContentAgentService
from app.services.content_batch_execution_service import ContentBatchExecutionService
from app.services.content_batch_planner import ContentBatchPlanner
from app.services.content_batch_report_service import ContentBatchReportService
from app.services.executor_invocation_service import ExecutorInvocationClient


ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"
PRODUCTION_ASSET_ID = 1972
CANDIDATE_ASSET_ID = 1984
COUNT = 10
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_reward_completion_cleanup_20260722")
MODEL_CONFIG = {
    "provider_code": "deepseek",
    "model_code": "deepseek-v4-flash",
    "ge_model": "deepseek-v4-flash",
    "ae_model": "deepseek-v4-flash",
    "temperature": 0.8,
    "max_tokens": 2048,
}


async def set_active_asset(session: Any) -> AssetRegistry:
    await session.execute(
        update(AssetRegistry)
        .where(
            AssetRegistry.asset_type.in_(ARTICLE_BUSINESS_RULE_ASSET_TYPES),
            AssetRegistry.asset_key == ASSET_KEY,
            AssetRegistry.status == "active",
        )
        .values(status="archived")
    )
    asset = await session.get(AssetRegistry, CANDIDATE_ASSET_ID)
    if asset is None:
        raise RuntimeError(f"asset not found: {CANDIDATE_ASSET_ID}")
    asset.status = "active"
    asset.asset_stage = "production"
    await session.flush()
    return asset


async def restore_production(session: Any) -> None:
    await session.execute(
        update(AssetRegistry)
        .where(
            AssetRegistry.asset_type.in_(ARTICLE_BUSINESS_RULE_ASSET_TYPES),
            AssetRegistry.asset_key == ASSET_KEY,
            AssetRegistry.id != PRODUCTION_ASSET_ID,
            AssetRegistry.status == "active",
        )
        .values(status="archived", asset_stage="candidate")
    )
    candidate = await session.get(AssetRegistry, CANDIDATE_ASSET_ID)
    if candidate is not None:
        candidate.status = "archived"
        candidate.asset_stage = "candidate"
    production = await session.get(AssetRegistry, PRODUCTION_ASSET_ID)
    if production is None:
        raise RuntimeError("production v17 asset not found")
    production.status = "active"
    production.asset_stage = "production"
    await session.flush()


async def load_items(session: Any, batch_id: int) -> list[ContentBatchItem]:
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


def slot_value(plan: dict[str, Any], slot_code: str) -> str:
    return str(
        next(
            (
                slot.get("value")
                for slot in plan.get("variation_slots") or []
                if slot.get("slot_code") == slot_code
            ),
            "",
        )
        or ""
    )


async def execute_batch(batch_id: int) -> dict[str, Any]:
    async with async_session_factory() as session:
        executor = await ContentAgentService(session).get_executor(DEFAULT_EXECUTOR_CODE)
        if executor is None:
            raise RuntimeError(f"executor not found: {DEFAULT_EXECUTOR_CODE}")
        client = ExecutorInvocationClient()
        try:
            service = ContentBatchExecutionService(
                session,
                invocation_client=client,
                callback_base_url="/api/v1/content-agent",
                executor_code=DEFAULT_EXECUTOR_CODE,
            )
            execution = await service.execute_batch_items(
                batch_id,
                limit=COUNT,
                created_by="codex-a2-reward-completion-cleanup",
            )
            await session.commit()
            session.expire_all()
            report = await ContentBatchReportService(session).get_batch_report(
                batch_id, include_details=True
            )
        finally:
            await client.http_client.aclose()
    return {
        "batch_id": batch_id,
        "execution": {
            "requested_limit": execution.requested_limit,
            "generated_count": execution.generated_count,
            "failed_count": execution.failed_count,
        },
        "report": report.model_dump(mode="json"),
    }


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    batch_id = None
    try:
        async with async_session_factory() as session:
            asset = await set_active_asset(session)
            planner = ContentBatchPlanner(session)
            job = await planner.create_batch_plan(
                asset_key=ASSET_KEY,
                product_topic=None,
                target_audience="普通宝妈",
                style="纯分享",
                count=COUNT,
                model_config=MODEL_CONFIG,
                created_by="codex-a2-reward-completion-cleanup",
            )
            batch_id = job.id
            items = await load_items(session, batch_id)
            manifest = {
                "batch_id": batch_id,
                "asset_id": asset.id,
                "asset_version": asset.version_no,
                "model_config": MODEL_CONFIG,
                "items": [
                    {
                        "item_no": item.item_no,
                        "business_rule": str((item.plan_json or {}).get("business_rule") or ""),
                        "source": slot_value(dict(item.plan_json or {}), "activity_source"),
                        "reason": slot_value(dict(item.plan_json or {}), "participation_reason"),
                        "activity_content": slot_value(dict(item.plan_json or {}), "activity_content"),
                        "recognition": slot_value(dict(item.plan_json or {}), "recognition_expression"),
                    }
                    for item in items
                ],
            }
            (OUTPUT_DIR / f"batch{batch_id}_plan_manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            await session.commit()

        result = await execute_batch(batch_id)
        report_path = OUTPUT_DIR / f"batch{batch_id}_reward_completion_cleanup_report.json"
        report_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "batch_id": batch_id,
                    "report_path": str(report_path),
                    "summary": result["report"]["summary"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        async with async_session_factory() as session:
            await restore_production(session)
            await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
