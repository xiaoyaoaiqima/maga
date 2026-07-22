"""Tests for prompt-debug history grouping and detail recovery."""

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.prompt_debug_history_service import PromptDebugHistoryService


class _FakeScalars:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class _FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return _FakeScalars(self.rows)


class _FakeDb:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _query):
        return _FakeResult(self.rows)


def _row(record_id, group_id, panel_key, item_index, success=True):
    return SimpleNamespace(
        id=record_id,
        run_group_id=group_id,
        workbench_mode="compare",
        panel_key=panel_key,
        item_index=item_index,
        batch_size=2,
        prompt=f"prompt-{panel_key}",
        system_prompt=f"system-{panel_key}",
        requested_model_code="deepseek-v4-flash",
        temperature=0.7,
        max_tokens=1500,
        success=success,
        content=f"output-{panel_key}-{item_index}",
        model_code="deepseek-v4-flash",
        provider_code="deepseek",
        provider_model="deepseek-v4-flash",
        token_usage={"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
        latency_ms=123,
        error_message=None if success else "failed",
        create_time=datetime(2026, 7, 22, 12, record_id),
    )


@pytest.mark.asyncio
async def test_history_groups_batch_and_compare_records():
    rows = [
        _row(4, "group-2", "left", 0),
        _row(3, "group-1", "right", 1, success=False),
        _row(2, "group-1", "right", 0),
        _row(1, "group-1", "left", 0),
    ]
    service = PromptDebugHistoryService(_FakeDb(rows))

    groups = await service.list_groups(limit=30)

    assert [group.run_group_id for group in groups] == ["group-2", "group-1"]
    assert groups[1].total_count == 3
    assert groups[1].success_count == 2
    assert groups[1].failed_count == 1
    assert groups[1].panel_keys == ["right", "left"]


@pytest.mark.asyncio
async def test_history_detail_retains_prompt_parameters_and_outputs():
    rows = [
        _row(1, "group-1", "left", 0),
        _row(2, "group-1", "right", 0),
    ]
    service = PromptDebugHistoryService(_FakeDb(rows))

    detail = await service.get_group("group-1")

    assert detail is not None
    assert detail.run_group_id == "group-1"
    assert len(detail.records) == 2
    assert detail.records[0].system_prompt == "system-left"
    assert detail.records[1].content == "output-right-0"
