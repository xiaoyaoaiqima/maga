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
ASSET_A_ID = 1975
ASSET_B_ID = 1976
COUNT = 10
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_positive_words_ab_20260722")
REMOVED_TERMS = {"沉甸旬", "不白喝肉乎乎", "追肉成功结实"}
MODEL_CONFIG = {
    "provider_code": "deepseek",
    "model_code": "deepseek-v4-flash",
    "ge_model": "deepseek-v4-flash",
    "ae_model": "deepseek-v4-flash",
    "temperature": 0.8,
    "max_tokens": 2048,
}


def reduce_positive_value(value: str) -> str:
    separator = value.find("：")
    if separator < 0:
        return value
    label = value[: separator + 1]
    had_period = value.endswith("。")
    terms = [
        term.strip()
        for term in value[separator + 1 :].removesuffix("。").split("、")
        if term.strip() and term.strip() not in REMOVED_TERMS
    ]
    return f"{label}{'、'.join(terms)}{'。' if had_period else ''}"


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
    for candidate_id in (ASSET_A_ID, ASSET_B_ID):
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


def matched_b_plan(a_plan: dict[str, Any], asset_b: AssetRegistry) -> dict[str, Any]:
    plan = copy.deepcopy(a_plan)
    plan["rule_asset_id"] = asset_b.id
    plan["rule_asset_version"] = asset_b.version_no
    for slot in plan.get("variation_slots") or []:
        if slot.get("slot_code") == "positive_expression":
            slot["value"] = reduce_positive_value(str(slot.get("value") or ""))
    plan.pop("unified_generation", None)
    return plan


def compare_plans(a_items: list[ContentBatchItem], b_items: list[ContentBatchItem]) -> list[dict[str, Any]]:
    diffs = []
    for a_item, b_item in zip(a_items, b_items, strict=True):
        a_plan = copy.deepcopy(a_item.plan_json or {})
        b_plan = copy.deepcopy(b_item.plan_json or {})
        for plan in (a_plan, b_plan):
            plan.pop("rule_asset_id", None)
            plan.pop("rule_asset_version", None)
            for slot in plan.get("variation_slots") or []:
                if slot.get("slot_code") == "positive_expression":
                    slot["value"] = "<positive-expression>"
        if a_plan != b_plan:
            diffs.append({"item_no": a_item.item_no})
    return diffs


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
                created_by=f"codex-a2-positive-matched-{label}",
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
    path = OUTPUT_DIR / f"matched_{label}_batch{batch_id}_report.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(path), **payload}


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    a_batch_id = None
    b_batch_id = None
    try:
        async with async_session_factory() as session:
            asset_a = await set_active_asset(session, ASSET_A_ID)
            planner = ContentBatchPlanner(session)
            a_job = await planner.create_batch_plan(
                asset_key=ASSET_KEY,
                product_topic=None,
                target_audience="普通宝妈",
                style="纯分享",
                count=COUNT,
                model_config=MODEL_CONFIG,
                created_by="codex-a2-positive-matched-A",
            )
            a_batch_id = a_job.id
            a_items = await load_items(session, a_batch_id)

            asset_b = await set_active_asset(session, ASSET_B_ID)
            b_job = await planner.create_batch_plan(
                asset_key=ASSET_KEY,
                product_topic=None,
                target_audience="普通宝妈",
                style="纯分享",
                count=COUNT,
                model_config=MODEL_CONFIG,
                created_by="codex-a2-positive-matched-B",
            )
            b_batch_id = b_job.id
            b_items = await load_items(session, b_batch_id)
            for a_item, b_item in zip(a_items, b_items, strict=True):
                b_item.plan_json = matched_b_plan(dict(a_item.plan_json or {}), asset_b)
            await session.flush()
            diffs = compare_plans(a_items, b_items)
            if diffs:
                raise RuntimeError(f"non-positive plan differences: {diffs}")
            plan_manifest = {
                "a_batch_id": a_batch_id,
                "b_batch_id": b_batch_id,
                "asset_a_id": asset_a.id,
                "asset_b_id": asset_b.id,
                "non_positive_plan_diff_count": len(diffs),
                "model_config": MODEL_CONFIG,
                "items": [
                    {
                        "item_no": a_item.item_no,
                        "business_rule": (a_item.plan_json or {}).get("business_rule"),
                        "a_positive": next(
                            (
                                slot.get("value")
                                for slot in (a_item.plan_json or {}).get("variation_slots") or []
                                if slot.get("slot_code") == "positive_expression"
                            ),
                            None,
                        ),
                        "b_positive": next(
                            (
                                slot.get("value")
                                for slot in (b_item.plan_json or {}).get("variation_slots") or []
                                if slot.get("slot_code") == "positive_expression"
                            ),
                            None,
                        ),
                    }
                    for a_item, b_item in zip(a_items, b_items, strict=True)
                ],
            }
            (OUTPUT_DIR / "matched_ab_plan_manifest.json").write_text(
                json.dumps(plan_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            await session.commit()

        a_result = await execute_batch(a_batch_id, "A_full_raw")
        b_result = await execute_batch(b_batch_id, "B_light_remove_3")
        print(
            json.dumps(
                {
                    "a_batch_id": a_batch_id,
                    "b_batch_id": b_batch_id,
                    "a_report": a_result["path"],
                    "b_report": b_result["path"],
                    "a_summary": a_result["report"]["summary"],
                    "b_summary": b_result["report"]["summary"],
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
