from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest

from app.services.xhs_real_post_acquisition_service import XhsRealPostRecord


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "run_wangyue_real_post_evidence_ppl.py"
SPEC = importlib.util.spec_from_file_location("run_wangyue_real_post_evidence_ppl", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeAcquisitionService:
    def __init__(self) -> None:
        self.fetch_called = False

    def estimate_calls(self, keywords: list[str], *, per_keyword: int, page_size: int = 20) -> dict[str, int]:
        return {
            "keywords": len(keywords),
            "per_keyword": per_keyword,
            "search_calls": len(keywords),
            "detail_calls": len(keywords) * per_keyword,
            "total_calls": len(keywords) * (per_keyword + 1),
        }

    async def fetch_keywords(self, requests):
        self.fetch_called = True
        return [
            XhsRealPostRecord.from_mapping(
                {
                    "source_keyword": requests[0].keyword,
                    "note_id": "note-1",
                    "title": "放学回来还去画画",
                    "content": "孩子喝了一段时间，放学回来还去画画，先记录一下。",
                    "note_url": "https://www.xiaohongshu.com/explore/note-1",
                    "detail_status": "ok",
                }
            ),
            XhsRealPostRecord.from_mapping(
                {
                    "source_keyword": requests[0].keyword,
                    "note_id": "note-1",
                    "title": "重复笔记",
                    "content": "重复内容",
                    "detail_status": "ok",
                }
            ),
        ]


class FailingAcquisitionService(FakeAcquisitionService):
    async def fetch_keywords(self, requests):
        self.fetch_called = True
        raise RuntimeError("HTTP 401")


def make_args(**overrides):
    values = {
        "keyword": [" 孩子放学  回家画画 ", "孩子放学 回家画画"],
        "per_keyword": 5,
        "sort": "general",
        "note_type": "不限",
        "time_filter": "不限",
        "delay_ms": 0,
        "detail_concurrency": 2,
        "output_dir": None,
        "apply": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


@pytest.mark.asyncio
async def test_dry_run_only_estimates_and_does_not_fetch(tmp_path):
    service = FakeAcquisitionService()

    result = await MODULE.run(make_args(), acquisition_service=service, outputs_root=tmp_path)

    assert result["mode"] == "dry_run"
    assert result["keywords"] == ["孩子放学 回家画画"]
    assert result["estimate"]["total_calls"] == 6
    assert result["writes_database"] is False
    assert result["writes_assets"] is False
    assert service.fetch_called is False
    assert list(tmp_path.iterdir()) == []


def test_output_dir_must_stay_below_outputs_root(tmp_path):
    outputs_root = tmp_path / "outputs"
    outputs_root.mkdir()

    with pytest.raises(ValueError, match="must be a child directory"):
        MODULE.resolve_output_dir(tmp_path / "outside", outputs_root=outputs_root)


def test_default_service_is_locked_to_tikhub_direct(monkeypatch):
    monkeypatch.setattr(MODULE, "DEFAULT_TIKHUB_BASE_URL", "https://api.tikhub.io")

    service = MODULE.build_acquisition_service()

    assert service.base_url == "https://api.tikhub.io"


@pytest.mark.asyncio
async def test_failed_fetch_does_not_create_output_directory(tmp_path):
    outputs_root = tmp_path / "outputs"
    outputs_root.mkdir()
    output_dir = outputs_root / "failed-run"

    with pytest.raises(RuntimeError, match="HTTP 401"):
        await MODULE.run(
            make_args(apply=True, output_dir=output_dir),
            acquisition_service=FailingAcquisitionService(),
            outputs_root=outputs_root,
        )

    assert output_dir.exists() is False


@pytest.mark.asyncio
async def test_apply_writes_only_local_review_artifacts(tmp_path):
    outputs_root = tmp_path / "outputs"
    outputs_root.mkdir()
    output_dir = outputs_root / "run-1"
    service = FakeAcquisitionService()

    result = await MODULE.run(
        make_args(apply=True, output_dir=output_dir),
        acquisition_service=service,
        outputs_root=outputs_root,
    )

    assert service.fetch_called is True
    assert result["fetched_count"] == 2
    assert result["deduped_count"] == 1
    assert sorted(path.name for path in output_dir.iterdir()) == [
        "evidence.csv",
        "evidence.md",
        "raw_notes.jsonl",
        "summary.json",
    ]
    assert result["writes_database"] is False
    assert result["writes_assets"] is False


def test_script_has_no_rsca_dependency_or_asset_write_path():
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "rs-crawler-analysis" not in source
    assert "create_candidate_asset" not in source
    assert "asset_registry" not in source
    assert "pymysql" not in source
