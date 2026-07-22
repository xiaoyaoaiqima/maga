"""Run a focused A/B for merging the two a2 礼遇 recognition paths.

Baseline is the active production v32 asset. Candidate keeps every copied source
option verbatim, merges each activity pair into one rule, and gives every item
both a product-experience slot and an activity/detection recognition slot.
The candidate is in-memory only and never changes AssetRegistry state.
"""
from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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
COUNT = 10
OUTPUT_DIR = Path("/Users/luxifa/maga/outputs/a2_reiyu_v33_usage_merge_20260722")
MODEL_CONFIG = {
    "provider_code": "deepseek",
    "model_code": "deepseek-v4-flash",
    "ge_model": "deepseek-v4-flash",
    "ae_model": "deepseek-v4-flash",
    "temperature": 0.8,
    "max_tokens": 2048,
}


def _slot_map(rule: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(slot.get("slot_code") or ""): slot
        for slot in rule.get("variation_slots") or []
        if isinstance(slot, dict) and slot.get("slot_code")
    }


def _unique(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _options(slot: dict[str, Any] | None) -> list[str]:
    return _unique(list((slot or {}).get("options") or []))


def _merged_slot(
    code: str,
    name: str,
    options: list[str],
    *,
    offset: int | None = 0,
) -> dict[str, Any]:
    slot: dict[str, Any] = {
        "slot_code": code,
        "slot_name": name,
        "options": options,
    }
    if offset is not None:
        slot["offset"] = offset
    return slot


def build_candidate(production: AssetRegistry) -> tuple[SimpleNamespace, dict[str, Any]]:
    content = copy.deepcopy(production.content_json or {})
    source_items = list(content.get("items") or [])
    if len(source_items) != 16:
        raise RuntimeError(f"expected 16 production rules, got {len(source_items)}")

    merged_items: list[dict[str, Any]] = []
    audit_pairs: list[dict[str, Any]] = []
    for pair_index in range(0, len(source_items), 2):
        usage_rule = copy.deepcopy(source_items[pair_index])
        info_rule = copy.deepcopy(source_items[pair_index + 1])
        usage_prefix, usage_path = str(usage_rule["business_rule"]).rsplit("｜", 1)
        info_prefix, info_path = str(info_rule["business_rule"]).rsplit("｜", 1)
        if usage_prefix != info_prefix:
            raise RuntimeError(f"activity pair mismatch: {usage_prefix} != {info_prefix}")
        if usage_path != "老客使用感受" or info_path != "老客了解信息后更认可":
            raise RuntimeError(f"unexpected recognition paths: {usage_path}, {info_path}")

        usage_slots = _slot_map(usage_rule)
        info_slots = _slot_map(info_rule)
        product_experience = _options(usage_slots.get("consumer_recognition"))
        brand_recognition = _options(info_slots.get("consumer_recognition"))
        if not product_experience or not brand_recognition:
            raise RuntimeError(f"missing recognition source options for {usage_prefix}")

        merged = usage_rule
        merged["rule_id"] = f"draft_usage_merge_{pair_index // 2 + 1:03d}"
        merged["source_row_no"] = pair_index // 2 + 1
        merged["business_rule"] = f"{usage_prefix}｜老客使用体验与了解后更认可"
        merged["product_relation"] = f"出现方式：{usage_prefix.removeprefix('a2礼遇｜')}｜老客双重认可"
        merged["product_appearance_mode"] = f"{usage_prefix.removeprefix('a2礼遇｜')}｜老客双重认可"

        boundary = (
            "本条是长期使用a2至初的老客：活动和每批检测带来新的品牌认可，"
            "同时写一处家里真实使用感受；两部分自然接上，不连续堆产品点。"
        )
        merged["hard_boundaries"] = [
            line
            for line in merged.get("hard_boundaries") or []
            if not str(line).startswith("本条认可路径是老客使用感受")
        ]
        merged["hard_boundaries"].insert(3, boundary)
        merged["writing_requirements"] = [
            *(merged.get("writing_requirements") or []),
            "活动内容和每批检测说完后，用一处具体使用体验接住老客为什么更加认可a2；原始体验素材自然转述，不写成卖点清单。",
        ]

        merged["variation_slots"] = [
            _merged_slot(
                "content_direction",
                "内容方向",
                _unique(
                    _options(usage_slots.get("content_direction"))
                    + _options(info_slots.get("content_direction"))
                ),
            ),
            _merged_slot(
                "info_source",
                "活动了解途径",
                _unique(
                    _options(usage_slots.get("info_source"))
                    + _options(info_slots.get("info_source"))
                ),
            ),
            _merged_slot(
                "participation_motive",
                "参加活动原因",
                _unique(
                    _options(usage_slots.get("participation_motive"))
                    + _options(info_slots.get("participation_motive"))
                ),
            ),
            _merged_slot(
                "activity_content",
                "活动内容",
                _unique(
                    _options(usage_slots.get("activity_content"))
                    + _options(info_slots.get("activity_content"))
                ),
            ),
            _merged_slot(
                "batch_detection",
                "批批检素材",
                _unique(
                    _options(usage_slots.get("batch_detection"))
                    + _options(info_slots.get("batch_detection"))
                ),
                offset=None,
            ),
            _merged_slot(
                "consumer_recognition",
                "老客产品使用体验",
                product_experience,
            ),
            _merged_slot(
                "brand_recognition",
                "活动信息后的品牌认可表达",
                brand_recognition,
            ),
            _merged_slot(
                "positive_expression",
                "活动分享正向表达",
                _unique(
                    _options(usage_slots.get("positive_expression"))
                    + _options(info_slots.get("positive_expression"))
                ),
            ),
        ]

        copied_checks = {
            "product_experience_exact": product_experience
            == _options(usage_slots.get("consumer_recognition")),
            "brand_recognition_exact": brand_recognition
            == _options(info_slots.get("consumer_recognition")),
            "source_options_retained": all(
                value
                in _options(_slot_map(merged).get("info_source"))
                for value in (
                    _options(usage_slots.get("info_source"))
                    + _options(info_slots.get("info_source"))
                )
            ),
            "motive_options_retained": all(
                value
                in _options(_slot_map(merged).get("participation_motive"))
                for value in (
                    _options(usage_slots.get("participation_motive"))
                    + _options(info_slots.get("participation_motive"))
                )
            ),
            "activity_options_retained": all(
                value
                in _options(_slot_map(merged).get("activity_content"))
                for value in (
                    _options(usage_slots.get("activity_content"))
                    + _options(info_slots.get("activity_content"))
                )
            ),
        }
        if not all(copied_checks.values()):
            raise RuntimeError(f"raw source retention failed: {usage_prefix}: {copied_checks}")

        merged_items.append(merged)
        audit_pairs.append(
            {
                "activity": usage_prefix,
                "source_rows": [pair_index + 1, pair_index + 2],
                "product_experience_count": len(product_experience),
                "brand_recognition_count": len(brand_recognition),
                "checks": copied_checks,
            }
        )

    content["items"] = merged_items
    content["allow_repeat_generation"] = True
    content["default_generation_count"] = COUNT
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
        content_json=content,
        metadata_json={
            **copy.deepcopy(production.metadata_json or {}),
            "experiment": "a2_reiyu_usage_and_information_recognition_merge",
            "experiment_arm": "draft_v33_usage_merge",
            "rule_count": len(merged_items),
            "allow_repeat_generation": True,
        },
    )
    return candidate, {"pair_count": len(audit_pairs), "pairs": audit_pairs}


async def _run_batch(asset: Any, *, label: str) -> dict[str, Any]:
    client = ExecutorInvocationClient()
    try:
        async with async_session_factory() as db:
            executor = await ContentAgentService(db).get_executor(DEFAULT_EXECUTOR_CODE)
            if executor is None:
                raise RuntimeError(f"executor not found: {DEFAULT_EXECUTOR_CODE}")
            planner = ContentBatchPlanner(db)
            job = await planner._create_article_business_rule_plan(
                asset,
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
                created_by=f"codex_a2_usage_merge_{label}",
            )
            job_id = int(job.id)
            job_count = int(job.count)
            await db.commit()
            execution = await ContentBatchExecutionService(
                db,
                invocation_client=client,
                callback_base_url="/api/v1/content-agent",
                executor_code=DEFAULT_EXECUTOR_CODE,
            ).execute_batch_items(
                job_id,
                limit=job_count,
                created_by=f"codex_a2_usage_merge_{label}",
            )
            await db.commit()
            db.expire_all()
            report = await ContentBatchReportService(db).get_batch_report(job_id)
            result = report.model_dump(mode="json")
            generated = [item for item in result.get("items") or [] if item.get("run_id")]
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
        return {
            "batch_id": job_id,
            "execution": {
                "requested": execution.requested_limit,
                "generated": execution.generated_count,
                "failed": execution.failed_count,
            },
            "report": result,
            "sample": {
                "item_no": selected["item_no"],
                "title": selected.get("title") or "",
                "rendered_prompt": str((stage.input_snapshot or {}).get("rendered_prompt") or ""),
            },
        }
    finally:
        await client.http_client.aclose()


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    async with async_session_factory() as db:
        production = await db.get(AssetRegistry, ASSET_ID)
        if production is None:
            raise RuntimeError(f"asset not found: {ASSET_ID}")
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
        candidate, retention_audit = build_candidate(production)
        candidate_json = {
            "content_json": candidate.content_json,
            "metadata_json": candidate.metadata_json,
            "retention_audit": retention_audit,
        }
        (OUTPUT_DIR / "candidate_v33_usage_merge.json").write_text(
            json.dumps(candidate_json, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    baseline = await _run_batch(production, label="baseline_v32")
    (OUTPUT_DIR / f"batch{baseline['batch_id']}_baseline_report.json").write_text(
        json.dumps(baseline["report"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT_DIR / f"batch{baseline['batch_id']}_baseline_prompt_item{baseline['sample']['item_no']}.md").write_text(
        baseline["sample"]["rendered_prompt"].strip() + "\n", encoding="utf-8"
    )

    candidate_result = await _run_batch(candidate, label="candidate_v33")
    (OUTPUT_DIR / f"batch{candidate_result['batch_id']}_candidate_report.json").write_text(
        json.dumps(candidate_result["report"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT_DIR / f"batch{candidate_result['batch_id']}_candidate_prompt_item{candidate_result['sample']['item_no']}.md").write_text(
        candidate_result["sample"]["rendered_prompt"].strip() + "\n", encoding="utf-8"
    )

    manifest = {
        "production_asset": {"id": ASSET_ID, "version": 32},
        "candidate_persisted": False,
        "model_config": MODEL_CONFIG,
        "baseline": {
            "batch_id": baseline["batch_id"],
            "execution": baseline["execution"],
            "sample_item_no": baseline["sample"]["item_no"],
        },
        "candidate": {
            "batch_id": candidate_result["batch_id"],
            "execution": candidate_result["execution"],
            "sample_item_no": candidate_result["sample"]["item_no"],
        },
        "retention_audit": retention_audit,
    }
    manifest_path = OUTPUT_DIR / "experiment_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
