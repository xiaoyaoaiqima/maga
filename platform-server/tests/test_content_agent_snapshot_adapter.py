"""Tests for converting MAGA content-agent snapshots into xhs-writer brief.yaml."""
from pathlib import Path

import pytest
import yaml

from app.services.content_agent_snapshot_adapter import (
    build_xhs_brief,
    dump_xhs_brief_yaml,
    write_xhs_brief_yaml,
)


def test_build_xhs_brief_from_explicit_xhs_brief_snapshot():
    snapshot = {
        "task_id": 1001,
        "run_id": 2002,
        "task_type": "xhs_generate",
        "input": {
            "xhs_brief": {
                "brief_id": "brief-a2-001",
                "brief_type": "xhs_product_seeding_professional_advisor",
                "brand": "meadjohnson",
                "products": ["a2_dueltz"],
                "campaign": {
                    "name": "美素佳儿 a2 待产包",
                    "must_keywords": ["美素佳儿", "a2"],
                },
                "painpoint_ratio": {"喂养进食问题": 0.4, "肠胃消化问题": 0.4, "生长发育问题": 0.2},
                "persona_target": {"identity": "二胎经验妈妈", "voice": "经验老道型"},
                "content_structure": {"word_count": "150-250字", "title_style": "情绪共情标题"},
                "score_threshold": 80,
                "max_rewrites": 2,
                "soft_weights": {"painpoint_selling": 2, "ai_smell": 1.5},
            }
        },
        "asset_refs": {"source": "maga"},
    }

    brief = build_xhs_brief(snapshot)

    assert brief["brief_id"] == "brief-a2-001"
    assert brief["brief_type"] == "xhs_product_seeding_professional_advisor"
    assert brief["brand"] == "meadjohnson"
    assert brief["products"] == ["a2_dueltz"]
    assert brief["campaign"]["must_keywords"] == ["美素佳儿", "a2"]
    assert brief["painpoint_ratio"]["喂养进食问题"] == 0.4
    assert brief["persona_target"]["identity"] == "二胎经验妈妈"
    assert brief["content_structure"]["title_style"] == "情绪共情标题"
    assert brief["score_threshold"] == 80
    assert brief["max_rewrites"] == 2
    assert brief["soft_weights"]["painpoint_selling"] == 2
    assert brief["maga"]["task_id"] == 1001
    assert brief["maga"]["run_id"] == 2002
    assert brief["maga"]["asset_refs"] == {"source": "maga"}


def test_build_xhs_brief_from_flat_snapshot_fields():
    snapshot = {
        "task_id": 1002,
        "run_id": 2003,
        "task_type": "xhs_generate",
        "input": {
            "brief_type": "xhs_product_seeding_professional_advisor",
            "brand": "meadjohnson",
            "product_code": "a2_dueltz",
            "campaign_name": "美素佳儿 a2 待产包",
            "must_keywords": ["美素佳儿", "a2"],
            "target_persona": "二胎经验妈妈",
            "voice": "经验老道型",
            "word_count": "150-250字",
            "title_style": "情绪共情标题",
            "score_threshold": 85,
        },
        "asset_refs": {},
    }

    brief = build_xhs_brief(snapshot)

    assert brief["brief_id"] == "maga-task-1002-run-2003"
    assert brief["brief_type"] == "xhs_product_seeding_professional_advisor"
    assert brief["brand"] == "meadjohnson"
    assert brief["products"] == ["a2_dueltz"]
    assert brief["campaign"] == {
        "name": "美素佳儿 a2 待产包",
        "must_keywords": ["美素佳儿", "a2"],
        "must_messages": [],
    }
    assert brief["persona_target"] == {"identity": "二胎经验妈妈", "voice": "经验老道型"}
    assert brief["content_structure"] == {"word_count": "150-250字", "title_style": "情绪共情标题"}
    assert brief["score_threshold"] == 85


def test_dump_xhs_brief_yaml_round_trips_unicode():
    brief = {
        "brief_id": "brief-a2-001",
        "brief_type": "xhs_product_seeding_professional_advisor",
        "brand": "meadjohnson",
        "products": ["a2_dueltz"],
        "campaign": {"name": "美素佳儿 a2 待产包", "must_keywords": ["美素佳儿"]},
    }

    text = dump_xhs_brief_yaml(brief)
    loaded = yaml.safe_load(text)

    assert "美素佳儿" in text
    assert loaded == brief


def test_write_xhs_brief_yaml_creates_parent_directory(tmp_path: Path):
    snapshot = {
        "task_id": 1003,
        "run_id": 2004,
        "task_type": "xhs_generate",
        "input": {
            "brief_type": "xhs_product_seeding_professional_advisor",
            "brand": "meadjohnson",
            "products": ["a2_dueltz"],
        },
        "asset_refs": {},
    }
    output_path = tmp_path / "campaigns" / "_current" / "brief.yaml"

    written = write_xhs_brief_yaml(snapshot, output_path)

    assert written == output_path
    assert yaml.safe_load(output_path.read_text(encoding="utf-8"))["products"] == ["a2_dueltz"]


def test_build_xhs_brief_requires_brand_and_products():
    snapshot = {"task_id": 1004, "run_id": None, "task_type": "xhs_generate", "input": {}, "asset_refs": {}}

    with pytest.raises(ValueError, match="brand"):
        build_xhs_brief(snapshot)
