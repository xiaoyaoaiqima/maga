from __future__ import annotations

import asyncio
import copy
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
BASE_ASSET_ID = 1978
C_BATCH_ID = 781
COUNT = 10
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_positive_usage_and_loyalty_20260722")
MODEL_CONFIG = {
    "provider_code": "deepseek",
    "model_code": "deepseek-v4-flash",
    "ge_model": "deepseek-v4-flash",
    "ae_model": "deepseek-v4-flash",
    "temperature": 0.8,
    "max_tokens": 2048,
}


async def set_active_asset(session: Any, asset_id: int) -> AssetRegistry:
    await session.execute(
        update(AssetRegistry)
        .where(
            AssetRegistry.asset_type.in_(ARTICLE_BUSINESS_RULE_ASSET_TYPES),
            AssetRegistry.asset_key == ASSET_KEY,
            AssetRegistry.status == "active",
        )
        .values(status="archived")
    )
    asset = await session.get(AssetRegistry, asset_id)
    if asset is None:
        raise RuntimeError(f"asset not found: {asset_id}")
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
    base = await session.get(AssetRegistry, BASE_ASSET_ID)
    if base is not None:
        base.status = "archived"
        base.asset_stage = "candidate"
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


def pair_base_plan(c_plan: dict[str, Any], base_plan: dict[str, Any]) -> dict[str, Any]:
    plan = copy.deepcopy(c_plan)
    for key in (
        "business_rule",
        "hard_boundaries",
        "writing_requirements",
        "product_relation",
        "product_appearance_mode",
        "rule_asset_id",
        "rule_asset_version",
    ):
        plan[key] = copy.deepcopy(base_plan.get(key))
    plan["batch_context"] = copy.deepcopy(base_plan.get("batch_context"))
    plan.pop("unified_generation", None)
    return plan


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
                created_by="codex-a2-positive-usage-base",
            )
            await session.commit()
            session.expire_all()
            report = await ContentBatchReportService(session).get_batch_report(
                batch_id, include_details=True
            )
        finally:
            await client.http_client.aclose()
    return {
        "label": "B_old_one_or_two_rule",
        "batch_id": batch_id,
        "execution": {
            "requested_limit": execution.requested_limit,
            "generated_count": execution.generated_count,
            "failed_count": execution.failed_count,
        },
        "report": report.model_dump(mode="json"),
    }


async def main() -> None:
    batch_id = None
    try:
        async with async_session_factory() as session:
            asset = await set_active_asset(session, BASE_ASSET_ID)
            c_items = await load_items(session, C_BATCH_ID)
            planner = ContentBatchPlanner(session)
            job = await planner.create_batch_plan(
                asset_key=ASSET_KEY,
                product_topic=None,
                target_audience="普通宝妈",
                style="纯分享",
                count=COUNT,
                model_config=MODEL_CONFIG,
                created_by="codex-a2-positive-usage-base",
            )
            batch_id = job.id
            base_items = await load_items(session, batch_id)
            for c_item, base_item in zip(c_items, base_items, strict=True):
                base_item.plan_json = pair_base_plan(
                    dict(c_item.plan_json or {}), dict(base_item.plan_json or {})
                )
            await session.flush()
            manifest = {
                "base_batch_id": batch_id,
                "c_batch_id": C_BATCH_ID,
                "base_asset_id": asset.id,
                "items": [
                    {
                        "item_no": base_item.item_no,
                        "business_rule": (base_item.plan_json or {}).get("business_rule"),
                        "base_writing_requirements": (base_item.plan_json or {}).get(
                            "writing_requirements"
                        ),
                        "c_writing_requirements": (c_item.plan_json or {}).get(
                            "writing_requirements"
                        ),
                    }
                    for c_item, base_item in zip(c_items, base_items, strict=True)
                ],
            }
            (OUTPUT_DIR / "matched_base_c_manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            await session.commit()

        result = await execute_batch(batch_id)
        report_path = OUTPUT_DIR / f"batch{batch_id}_B_old_one_or_two_rule_report.json"
        report_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "base_batch_id": batch_id,
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
