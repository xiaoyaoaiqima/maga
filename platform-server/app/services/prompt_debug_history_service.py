"""Persistence and lookup for the raw prompt-debug workbench."""

from collections import OrderedDict
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content_agent import ContentPromptDebugHistory
from app.schemas.prompt_debug import (
    PromptDebugHistoryGroupDetail,
    PromptDebugHistoryGroupSummary,
    PromptDebugHistoryItem,
    PromptDebugRequest,
    PromptDebugResponse,
)


class PromptDebugHistoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        request: PromptDebugRequest,
        response: PromptDebugResponse,
        run_group_id: str | None = None,
    ) -> ContentPromptDebugHistory:
        history = ContentPromptDebugHistory(
            run_group_id=run_group_id or request.run_group_id or uuid4().hex,
            workbench_mode=request.workbench_mode,
            panel_key=request.panel_key,
            item_index=request.item_index,
            batch_size=request.batch_size,
            prompt=request.prompt,
            system_prompt=request.system_prompt,
            requested_model_code=request.model_code,
            temperature=request.temperature if request.temperature is not None else 0.9,
            max_tokens=request.max_tokens if request.max_tokens is not None else 1500,
            thinking_mode=request.thinking_mode,
            success=response.success,
            content=response.content,
            model_code=response.model_code,
            provider_code=response.provider_code,
            provider_model=response.provider_model,
            token_usage=response.usage.model_dump() if response.usage else None,
            latency_ms=response.latency_ms,
            error_message=response.error_message,
        )
        self.db.add(history)
        await self.db.flush()
        return history

    async def list_groups(self, *, limit: int = 30) -> list[PromptDebugHistoryGroupSummary]:
        result = await self.db.execute(
            select(ContentPromptDebugHistory)
            .order_by(ContentPromptDebugHistory.id.desc())
            .limit(limit * 40)
        )
        rows = list(result.scalars().all())
        grouped: OrderedDict[str, list[ContentPromptDebugHistory]] = OrderedDict()
        for row in rows:
            if row.run_group_id not in grouped and len(grouped) >= limit:
                continue
            grouped.setdefault(row.run_group_id, []).append(row)

        summaries: list[PromptDebugHistoryGroupSummary] = []
        for group_id, records in grouped.items():
            newest = records[0]
            panel_keys = list(dict.fromkeys(record.panel_key for record in records))
            model_codes = list(
                dict.fromkeys(record.requested_model_code for record in records)
            )
            summaries.append(
                PromptDebugHistoryGroupSummary(
                    run_group_id=group_id,
                    workbench_mode=newest.workbench_mode,
                    create_time=newest.create_time,
                    total_count=len(records),
                    success_count=sum(1 for record in records if record.success),
                    failed_count=sum(1 for record in records if not record.success),
                    panel_keys=panel_keys,
                    model_codes=model_codes,
                    prompt_preview=newest.prompt[:120].replace("\n", " "),
                )
            )
        return summaries

    async def get_group(self, run_group_id: str) -> PromptDebugHistoryGroupDetail | None:
        result = await self.db.execute(
            select(ContentPromptDebugHistory)
            .where(ContentPromptDebugHistory.run_group_id == run_group_id)
            .order_by(
                ContentPromptDebugHistory.panel_key.asc(),
                ContentPromptDebugHistory.item_index.asc(),
                ContentPromptDebugHistory.id.asc(),
            )
        )
        records = list(result.scalars().all())
        if not records:
            return None
        newest = max(records, key=lambda record: record.id)
        return PromptDebugHistoryGroupDetail(
            run_group_id=run_group_id,
            workbench_mode=newest.workbench_mode,
            create_time=newest.create_time,
            records=[PromptDebugHistoryItem.model_validate(record) for record in records],
        )
