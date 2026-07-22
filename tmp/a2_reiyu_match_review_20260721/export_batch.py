#!/usr/bin/env python3
"""Export A2 reiyu batch reports, item plans, and rendered prompts for review."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from urllib.request import urlopen

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.content_agent import ContentAgentStageCall, ContentBatchItem


async def export_batch(batch_id: int, output_dir: Path, base_url: str) -> None:
    with urlopen(
        f"{base_url.rstrip('/')}/api/v1/content-agent/batches/{batch_id}/report",
        timeout=60,
    ) as response:
        report_response = json.load(response)

    async with async_session_factory() as session:
        items = list(
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
        payload = []
        for item in items:
            stage_call = (
                await session.execute(
                    select(ContentAgentStageCall)
                    .where(
                        ContentAgentStageCall.run_id == item.run_id,
                        ContentAgentStageCall.capability == "content.generate",
                    )
                    .order_by(ContentAgentStageCall.sequence_no)
                    .limit(1)
                )
            ).scalar_one_or_none()
            plan = dict(item.plan_json or {})
            input_snapshot = dict(stage_call.input_snapshot or {}) if stage_call else {}
            unified = dict(plan.get("unified_generation") or {})
            rendered_prompt = str(
                input_snapshot.get("rendered_prompt")
                or unified.get("rendered_prompt")
                or ""
            )
            payload.append(
                {
                    "item_id": item.id,
                    "item_no": item.item_no,
                    "title": item.title or "",
                    "body": item.body or "",
                    "quality": item.quality_json or {},
                    "business_rule": plan.get("business_rule"),
                    "rule_id": plan.get("rule_id"),
                    "source_row_no": plan.get("source_row_no"),
                    "variation_slots": plan.get("variation_slots") or [],
                    "plan_json": plan,
                    "rendered_prompt": rendered_prompt,
                    "model_config": input_snapshot.get("model_config")
                    or unified.get("model_config")
                    or plan.get("model_config")
                    or {},
                }
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"batch{batch_id}_report.json"
    details_path = output_dir / f"batch{batch_id}_details.json"
    report_path.write_text(
        json.dumps(report_response, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    details_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "batch_id": batch_id,
                "items": len(payload),
                "report_path": str(report_path),
                "details_path": str(details_path),
            },
            ensure_ascii=False,
        )
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_ids", nargs="+", type=int)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:5100")
    args = parser.parse_args()
    for batch_id in args.batch_ids:
        await export_batch(batch_id, args.output_dir, args.base_url)


if __name__ == "__main__":
    asyncio.run(main())
