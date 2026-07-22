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
ASSET_B_ID = 1977
SOURCE_A_BATCH_ID = 776
COUNT = 10
REMOVED_TERMS = {"放心", "省心", "真香"}
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_positive_words_ab_20260722")
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
    candidate = await session.get(AssetRegistry, ASSET_B_ID)
    if candidate is not None:
        candidate.status = "archived"
        candidate.asset_stage = "candidate"
    production = await session.get(AssetRegistry, PRODUCTION_ASSET_ID)
    if production is None:
        raise RuntimeError("production v17 asset not found")
    production.status = "active"
    production.asset_stage = "production"
    await session.flush()


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    batch_id = None
    try:
        async with async_session_factory() as session:
            asset_b = await session.get(AssetRegistry, ASSET_B_ID)
            if asset_b is None or asset_b.status != "active" or asset_b.asset_stage != "production":
                raise RuntimeError("B high-frequency candidate is not active production for planning")
            source_items = await load_items(session, SOURCE_A_BATCH_ID)
            if len(source_items) != COUNT:
                raise RuntimeError("source A batch does not contain 10 items")
            job = await ContentBatchPlanner(session).create_batch_plan(
                asset_key=ASSET_KEY,
                product_topic=None,
                target_audience="普通宝妈",
                style="纯分享",
                count=COUNT,
                model_config=MODEL_CONFIG,
                created_by="codex-a2-positive-matched-B-highfreq",
            )
            batch_id = job.id
            target_items = await load_items(session, batch_id)
            manifest_items = []
            for source_item, target_item in zip(source_items, target_items, strict=True):
                source_plan = copy.deepcopy(source_item.plan_json or {})
                source_plan.pop("unified_generation", None)
                target_plan = copy.deepcopy(source_plan)
                target_plan["rule_asset_id"] = asset_b.id
                target_plan["rule_asset_version"] = asset_b.version_no
                a_positive = None
                b_positive = None
                for slot in target_plan.get("variation_slots") or []:
                    if slot.get("slot_code") == "positive_expression":
                        a_positive = str(slot.get("value") or "")
                        b_positive = reduce_positive_value(a_positive)
                        slot["value"] = b_positive
                target_item.plan_json = target_plan
                manifest_items.append(
                    {
                        "item_no": source_item.item_no,
                        "business_rule": source_plan.get("business_rule"),
                        "a_positive": a_positive,
                        "b_positive": b_positive,
                        "changed": a_positive != b_positive,
                    }
                )
            await session.flush()
            changed_items = [item["item_no"] for item in manifest_items if item["changed"]]
            if changed_items != [1, 3, 7]:
                raise RuntimeError(f"unexpected changed positive items: {changed_items}")
            manifest = {
                "source_a_batch_id": SOURCE_A_BATCH_ID,
                "b_batch_id": batch_id,
                "asset_b_id": asset_b.id,
                "removed_terms": sorted(REMOVED_TERMS),
                "changed_item_nos": changed_items,
                "non_positive_plan_diff_count": 0,
                "model_config": MODEL_CONFIG,
                "items": manifest_items,
            }
            (OUTPUT_DIR / "matched_ab_highfreq_plan_manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            await session.commit()

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
                    created_by="codex-a2-positive-matched-B-highfreq",
                )
                await session.commit()
                session.expire_all()
                report = await ContentBatchReportService(session).get_batch_report(
                    batch_id, include_details=True
                )
            finally:
                await client.http_client.aclose()
        payload = {
            "label": "B_light_remove_highfreq_3",
            "batch_id": batch_id,
            "execution": {
                "requested_limit": execution.requested_limit,
                "generated_count": execution.generated_count,
                "failed_count": execution.failed_count,
            },
            "report": report.model_dump(mode="json"),
        }
        path = OUTPUT_DIR / f"matched_B_light_remove_highfreq_3_batch{batch_id}_report.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "batch_id": batch_id,
                    "path": str(path),
                    "summary": payload["report"]["summary"],
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
