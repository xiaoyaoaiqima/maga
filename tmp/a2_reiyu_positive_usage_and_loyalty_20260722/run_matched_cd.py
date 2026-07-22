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
ASSET_C_ID = 1980
ASSET_D_ID = 1981
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
    for candidate_id in (ASSET_C_ID, ASSET_D_ID):
        candidate = await session.get(AssetRegistry, candidate_id)
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


def pair_d_plan(c_plan: dict[str, Any], d_plan: dict[str, Any]) -> dict[str, Any]:
    plan = copy.deepcopy(c_plan)
    for key in (
        "business_rule",
        "hard_boundaries",
        "product_relation",
        "product_appearance_mode",
        "rule_asset_id",
        "rule_asset_version",
    ):
        plan[key] = copy.deepcopy(d_plan.get(key))
    plan["batch_context"] = copy.deepcopy(d_plan.get("batch_context"))
    plan.pop("unified_generation", None)
    return plan


def normalized_plan(plan: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(plan)
    for key in (
        "business_rule",
        "hard_boundaries",
        "product_relation",
        "product_appearance_mode",
        "rule_asset_id",
        "rule_asset_version",
        "batch_context",
        "unified_generation",
    ):
        value.pop(key, None)
    return value


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


async def execute_batch(batch_id: int, label: str) -> dict[str, Any]:
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
                created_by=f"codex-a2-positive-usage-{label}",
            )
            await session.commit()
            session.expire_all()
            report = await ContentBatchReportService(session).get_batch_report(
                batch_id, include_details=True
            )
        finally:
            await client.http_client.aclose()
    payload = {
        "label": label,
        "batch_id": batch_id,
        "execution": {
            "requested_limit": execution.requested_limit,
            "generated_count": execution.generated_count,
            "failed_count": execution.failed_count,
        },
        "report": report.model_dump(mode="json"),
    }
    path = OUTPUT_DIR / f"batch{batch_id}_{label}_report.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(path), **payload}


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    c_batch_id = None
    d_batch_id = None
    try:
        async with async_session_factory() as session:
            asset_c = await set_active_asset(session, ASSET_C_ID)
            planner = ContentBatchPlanner(session)
            c_job = await planner.create_batch_plan(
                asset_key=ASSET_KEY,
                product_topic=None,
                target_audience="普通宝妈",
                style="纯分享",
                count=COUNT,
                model_config=MODEL_CONFIG,
                created_by="codex-a2-positive-usage-C",
            )
            c_batch_id = c_job.id
            c_items = await load_items(session, c_batch_id)

            asset_d = await set_active_asset(session, ASSET_D_ID)
            d_job = await planner.create_batch_plan(
                asset_key=ASSET_KEY,
                product_topic=None,
                target_audience="普通宝妈",
                style="纯分享",
                count=COUNT,
                model_config=MODEL_CONFIG,
                created_by="codex-a2-positive-usage-D",
            )
            d_batch_id = d_job.id
            d_items = await load_items(session, d_batch_id)
            for c_item, d_item in zip(c_items, d_items, strict=True):
                d_item.plan_json = pair_d_plan(
                    dict(c_item.plan_json or {}), dict(d_item.plan_json or {})
                )
            await session.flush()

            diffs = []
            for c_item, d_item in zip(c_items, d_items, strict=True):
                if normalized_plan(dict(c_item.plan_json or {})) != normalized_plan(
                    dict(d_item.plan_json or {})
                ):
                    diffs.append(c_item.item_no)
            if diffs:
                raise RuntimeError(f"non-path plan differences: {diffs}")

            manifest = {
                "c_batch_id": c_batch_id,
                "d_batch_id": d_batch_id,
                "asset_c_id": asset_c.id,
                "asset_d_id": asset_d.id,
                "model_config": MODEL_CONFIG,
                "non_path_plan_diff_count": len(diffs),
                "items": [
                    {
                        "item_no": c_item.item_no,
                        "c_business_rule": (c_item.plan_json or {}).get("business_rule"),
                        "d_business_rule": (d_item.plan_json or {}).get("business_rule"),
                        "info_source": slot_value(dict(c_item.plan_json or {}), "info_source"),
                        "participation_motive": slot_value(
                            dict(c_item.plan_json or {}), "participation_motive"
                        ),
                        "activity_content": slot_value(
                            dict(c_item.plan_json or {}), "activity_content"
                        ),
                        "consumer_recognition": slot_value(
                            dict(c_item.plan_json or {}), "consumer_recognition"
                        ),
                        "positive_expression": slot_value(
                            dict(c_item.plan_json or {}), "positive_expression"
                        ),
                    }
                    for c_item, d_item in zip(c_items, d_items, strict=True)
                ],
            }
            (OUTPUT_DIR / "matched_cd_plan_manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            await session.commit()

        c_result = await execute_batch(c_batch_id, "C_positive_usage")
        d_result = await execute_batch(d_batch_id, "D_loyal_customer_recognition")
        print(
            json.dumps(
                {
                    "c_batch_id": c_batch_id,
                    "d_batch_id": d_batch_id,
                    "c_report": c_result["path"],
                    "d_report": d_result["path"],
                    "c_summary": c_result["report"]["summary"],
                    "d_summary": d_result["report"]["summary"],
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
