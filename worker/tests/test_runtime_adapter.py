"""Tests for MAGA xhs-writer runtime adapter."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import yaml

from maga_worker.runtime_adapter import (
    build_runtime_brief_from_snapshot,
    default_output_dir,
    invoke_runtime_fast_generate_draft,
    invoke_runtime_generate_draft,
)
from maga_worker import xhs_runtime
from maga_worker.xhs_runtime import call_ae


def _snapshot() -> dict:
    return {
        "brief": {
            "product_topic": "宝宝便便不规律",
            "target_audience": "新手妈妈",
            "style": "经验老道型",
        },
        "assets": {
            "painpoint": {"painpoint": "便便不规律", "description": "几天拉一次，每次脸憋通红", "selling_point": "好消化易吸收"},
            "selling_point": {"selling_point": "好消化易吸收", "advantage": "形成结构松散的软凝乳"},
            "reference_examples": [{"title": "源悦你给我出来 我是真的会谢！", "body": "真实分享，不照搬。"}],
            "writing_pattern": {
                "opening_pattern": "先共情便便焦虑",
                "story_arc": "痛点场景 -> 观察判断 -> 轻建议",
                "selling_point_placement": "正文中段自然带出",
                "proof_style": "日常观察记录",
                "ending_pattern": "给同类妈妈轻建议",
                "voice_traits": ["口语", "真实"],
                "avoid_copy_phrases": ["我是真的会谢"],
            },
            "compliance_rules": [{"dimension": "禁止治疗便秘", "risk_level": "high"}],
        },
        "diversity_slot": {
            "opening_type": "过来人提醒",
            "structure_type": "痛点-观察-建议",
            "emotion": "稳",
            "cta_type": "轻建议",
            "narrative_focus": "先共情",
        },
        "batch_context": {"batch_id": 9, "batch_code": "batch_test", "item_no": 1},
    }


def _prompt_bundle() -> dict:
    return {
        "schema_version": "1",
        "prompts": {
            "xhs_writer.ge.soul": {"version_id": 1, "content": "BUNDLE_SOUL"},
            "xhs_writer.ge.style_templates": {"version_id": 2, "content": "BUNDLE_STYLE"},
            "xhs_writer.ge.voice_dictionary": {"version_id": 3, "content": "BUNDLE_VOICE"},
            "xhs_writer.ae.compliance_redline.persona": {"version_id": 4, "content": "BUNDLE_AE_PERSONA"},
            "xhs_writer.ae.compliance_redline.score_rubric": {"version_id": 5, "content": "BUNDLE_RUBRIC"},
        },
        "assets": {
            "expert_corpus:compliance_redline": {
                "asset_id": 10,
                "content_json": {
                    "content": {
                        "expert": "compliance_redline",
                        "output_mode": "fixed",
                        "groups": {"红线": {"items": [{"text": "BUNDLE_CORPUS_ITEM"}]}},
                    }
                },
            },
            "brief_type_registry:xhs_writer": {
                "asset_id": 11,
                "content_json": {
                    "content": {
                        "brief_types": {
                            "xhs_product_seeding_professional_advisor": {
                                "required_aes": ["compliance_redline"],
                                "default_soft_weights": {},
                            }
                        }
                    }
                },
            },
            "expert_registry:xhs_writer": {
                "asset_id": 12,
                "content_json": {"content": {"experts": {"compliance_redline": {"score_type": "0/1"}}}},
            },
        },
    }


def test_build_runtime_brief_from_snapshot_contains_required_xhs_runtime_fields():
    brief = build_runtime_brief_from_snapshot(_snapshot())

    assert brief["brief_id"] == "maga-batch_test-001"
    assert brief["brief_type"] == "xhs_product_seeding_professional_advisor"
    assert brief["brand"] == "yuanyue"
    assert brief["products"] == ["yuanyue"]
    assert brief["campaign"]["target_audience"] == "新手妈妈"
    assert brief["maga"]["assets"]["painpoint"]["painpoint"] == "便便不规律"
    assert brief["maga"]["diversity_slot"]["opening_type"] == "过来人提醒"
    assert "治疗便秘" in brief["must_avoid"]


def test_invoke_runtime_generate_draft_writes_temp_brief_and_parses_final(monkeypatch, tmp_path):
    captured = {}

    def fake_run_full_flow(brief_path, verbose=False, work_dir=None):
        captured["brief_path"] = brief_path
        captured["work_dir"] = work_dir
        brief = yaml.safe_load(Path(brief_path).read_text(encoding="utf-8"))
        captured["brief"] = brief
        final_path = tmp_path / "final.md"
        final_path.write_text("标题：源悦观察便便状态别着急\n正文：先看便便软硬和肚肚舒不舒服。", encoding="utf-8")
        return {"verdict": "pass", "hard_pass": True, "soft_score": 91, "final_path": str(final_path)}

    result = invoke_runtime_generate_draft(_snapshot(), run_full_flow_func=fake_run_full_flow, work_dir=tmp_path)

    assert Path(captured["brief_path"]).exists()
    assert captured["work_dir"] == tmp_path
    assert captured["brief"]["brief_type"] == "xhs_product_seeding_professional_advisor"
    assert result["draft"] == {"title": "源悦观察便便状态别着急", "body": "先看便便软硬和肚肚舒不舒服。"}


def test_invoke_runtime_generate_draft_uses_model_config_from_maga_snapshot(monkeypatch, tmp_path):
    monkeypatch.delenv("XHS_RUNTIME_MODEL_GE", raising=False)
    monkeypatch.setenv("XHS_RUNTIME_MODEL_AE", "existing-ae")
    snapshot = _snapshot()
    snapshot["model_config"] = {"ge_model": "maga-ge", "ae_model": "maga-ae"}
    seen = {}

    def fake_run_full_flow(brief_path, verbose=False, work_dir=None):
        seen["ge_model"] = os.environ.get("XHS_RUNTIME_MODEL_GE")
        seen["ae_model"] = os.environ.get("XHS_RUNTIME_MODEL_AE")
        final_path = tmp_path / "final.md"
        final_path.write_text("标题：源悦观察便便状态别着急\n正文：先看便便软硬和肚肚舒不舒服。", encoding="utf-8")
        return {"final_path": str(final_path)}

    invoke_runtime_generate_draft(snapshot, run_full_flow_func=fake_run_full_flow, work_dir=tmp_path)

    assert seen == {"ge_model": "maga-ge", "ae_model": "maga-ae"}
    assert "XHS_RUNTIME_MODEL_GE" not in os.environ
    assert os.environ["XHS_RUNTIME_MODEL_AE"] == "existing-ae"


def test_invoke_runtime_fast_generate_draft_returns_draft_and_review_report(tmp_path):
    def fake_call_ge(brief, spec_md, soul, style, voice, debug_dir=None, tag=""):
        assert soul
        assert style is not None
        assert voice is not None
        assert brief["brief_type"] == "xhs_product_seeding_professional_advisor"
        assert "禁止表达" in spec_md
        assert "叙事角度：先共情" in spec_md
        assert "情绪底色：稳" in spec_md
        assert "行动收束：轻建议" in spec_md
        assert "写法结构：痛点场景 -> 观察判断 -> 轻建议" in spec_md
        assert "卖点植入：正文中段自然带出" in spec_md
        assert "禁止复用参考短语：我是真的会谢" in spec_md
        assert "来源例文：源悦你给我出来 我是真的会谢！" in spec_md
        return "源悦观察便便状态别着急\n\n先看便便软硬和肚肚舒不舒服。"

    def fake_call_ae(ae, mode, brief, draft, debug_dir=None, tag=""):
        assert ae == "compliance_redline"
        assert mode == "score"
        assert "源悦观察" in draft
        return {"score": 1, "verdict": "pass", "suggestions": []}

    result = invoke_runtime_fast_generate_draft(
        _snapshot(),
        call_ge_func=fake_call_ge,
        call_ae_func=fake_call_ae,
        work_dir=tmp_path,
    )

    assert result["draft"] == {"title": "源悦观察便便状态别着急", "body": "先看便便软硬和肚肚舒不舒服。"}
    assert result["runtime_result"]["mode"] == "runtime_fast"
    assert Path(result["runtime_result"]["final_path"]).exists()
    assert result["review_report"]["hard_results"][0]["ae_code"] == "compliance_redline"
    assert result["review_report"]["hard_results"][0]["pass"] is True
    assert result["review_report"]["rewrite_required"] is False


def test_invoke_runtime_fast_prefers_prompt_bundle_for_ge_prompt_parts(tmp_path):
    snapshot = _snapshot()
    snapshot["prompt_bundle_snapshot"] = _prompt_bundle()

    def fake_call_ge(brief, spec_md, soul, style, voice, debug_dir=None, tag="", **kwargs):
        assert soul == "BUNDLE_SOUL"
        assert style == "BUNDLE_STYLE"
        assert voice == "BUNDLE_VOICE"
        return "源悦观察便便状态别着急\n\n先看便便软硬和肚肚舒不舒服。"

    def fake_call_ae(ae, mode, brief, draft, debug_dir=None, tag=""):
        return {"score": 1, "verdict": "pass", "suggestions": []}

    result = invoke_runtime_fast_generate_draft(
        snapshot,
        call_ge_func=fake_call_ge,
        call_ae_func=fake_call_ae,
        work_dir=tmp_path,
    )

    assert result["draft"]["title"] == "源悦观察便便状态别着急"


def test_call_ae_prefers_prompt_bundle_for_persona_corpus_and_rubric(monkeypatch, tmp_path):
    snapshot = _snapshot()
    prompt_bundle = _prompt_bundle()
    captured = {}

    def fake_call_model(model, system, user, temperature=0.7):
        captured["system"] = system
        captured["user"] = user
        return "score: 1\nverdict: pass\nsuggestions: []\n"

    monkeypatch.setattr(xhs_runtime, "call_model", fake_call_model)
    monkeypatch.setenv("XHS_RUNTIME_PROMPT_BUNDLE_JSON", __import__("json").dumps(prompt_bundle, ensure_ascii=False))

    result = call_ae("compliance_redline", "score", build_runtime_brief_from_snapshot(snapshot), "草稿", debug_dir=tmp_path)

    assert result["score"] == 1
    assert captured["system"] == "BUNDLE_AE_PERSONA"
    assert "BUNDLE_CORPUS_ITEM" in captured["user"]
    assert "BUNDLE_RUBRIC" in captured["user"]


def test_invoke_runtime_fast_uses_model_config_from_maga_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("XHS_RUNTIME_MODEL_GE", "existing-ge")
    monkeypatch.delenv("XHS_RUNTIME_MODEL_AE", raising=False)
    seen = {}
    snapshot = _snapshot()
    snapshot["model_config"] = {"ge_model": "maga-ge", "ae_model": "maga-ae"}

    def fake_call_ge(brief, spec_md, soul, style, voice, debug_dir=None, tag="", **kwargs):
        import os

        seen["ge_model"] = os.environ.get("XHS_RUNTIME_MODEL_GE")
        return "源悦观察便便状态别着急\n\n先看便便软硬和肚肚舒不舒服。"

    def fake_call_ae(ae, mode, brief, draft, debug_dir=None, tag=""):
        import os

        seen["ae_model"] = os.environ.get("XHS_RUNTIME_MODEL_AE")
        return {"score": 1, "verdict": "pass", "suggestions": []}

    invoke_runtime_fast_generate_draft(
        snapshot,
        call_ge_func=fake_call_ge,
        call_ae_func=fake_call_ae,
        work_dir=tmp_path,
    )

    assert seen == {"ge_model": "maga-ge", "ae_model": "maga-ae"}
    assert os.environ["XHS_RUNTIME_MODEL_GE"] == "existing-ge"
    assert "XHS_RUNTIME_MODEL_AE" not in os.environ


def test_default_output_dir_is_repo_local():
    assert default_output_dir() == ROOT.parent / ".local" / "worker" / "outputs"


def test_invoke_runtime_fast_rewrites_and_rescores_when_review_has_soft_suggestions(tmp_path):
    ge_calls = []
    ae_calls = []

    def fake_call_ge(brief, spec_md, soul, style, voice, feedback=None, prev_draft=None, debug_dir=None, tag=""):
        ge_calls.append({"feedback": feedback, "prev_draft": prev_draft, "tag": tag})
        if feedback:
            assert "拿不准时问问靠谱渠道" in feedback
            assert "必要时问专业人士" in prev_draft
            return "源悦观察便便状态别着急\n\n拿不准时问问靠谱渠道，日常观察肚肚舒不舒服。"
        return "源悦观察便便状态别着急\n\n必要时问专业人士，日常观察肚肚舒不舒服。"

    def fake_call_ae(ae, mode, brief, draft, debug_dir=None, tag=""):
        ae_calls.append({"draft": draft, "tag": tag})
        if "必要时问专业人士" in draft:
            return {
                "score": 1,
                "verdict": "pass",
                "hard_hits": [],
                "suggestions": ["“必要时问专业人士”建议改为“拿不准时问问靠谱渠道”。"],
                "replacement_needed": [{"from": "必要时问专业人士", "to": "拿不准时问问靠谱渠道"}],
            }
        return {"score": 1, "verdict": "pass", "hard_hits": [], "suggestions": [], "replacement_needed": []}

    result = invoke_runtime_fast_generate_draft(
        _snapshot(),
        call_ge_func=fake_call_ge,
        call_ae_func=fake_call_ae,
        work_dir=tmp_path,
    )

    assert len(ge_calls) == 2
    assert len(ae_calls) == 2
    assert result["draft"]["body"] == "拿不准时问问靠谱渠道，日常观察肚肚舒不舒服。"
    assert result["review_report"]["hard_results"][0]["pass"] is True
    assert result["review_report"]["rewrite_required"] is False
    assert result["review_report"]["rewrite_rounds"] == 1
    assert result["review_report"]["rewrite_reason"] == "soft_suggestions"
    assert result["review_report"]["previous_review"]["suggestions"]


def test_invoke_runtime_fast_allows_second_rewrite_when_first_recheck_still_has_suggestions(tmp_path):
    ge_calls = []
    ae_calls = []

    def fake_call_ge(brief, spec_md, soul, style, voice, feedback=None, prev_draft=None, debug_dir=None, tag=""):
        ge_calls.append({"feedback": feedback, "prev_draft": prev_draft, "tag": tag})
        if len(ge_calls) == 1:
            return "源悦观察便便状态别着急\n\n必要时问专业人士，也可以观察几天。"
        if len(ge_calls) == 2:
            assert tag == "runtime_fast_rewrite_1"
            assert "必要时问专业人士" in feedback
            return "源悦观察便便状态别着急\n\n拿不准时问问靠谱渠道，也可以观察几天。"
        assert tag == "runtime_fast_rewrite_2"
        assert "观察几天" in feedback
        return "源悦观察便便状态别着急\n\n拿不准时问问靠谱渠道，也可以持续观察几次。"

    def fake_call_ae(ae, mode, brief, draft, debug_dir=None, tag=""):
        ae_calls.append({"draft": draft, "tag": tag})
        if "必要时问专业人士" in draft:
            return {
                "score": 1,
                "verdict": "pass",
                "hard_hits": [],
                "suggestions": ["“必要时问专业人士”建议改为“拿不准时问问靠谱渠道”。"],
                "replacement_needed": [{"from": "必要时问专业人士", "to": "拿不准时问问靠谱渠道"}],
            }
        if "观察几天" in draft:
            return {
                "score": 1,
                "verdict": "pass",
                "hard_hits": [],
                "suggestions": ["“观察几天”建议改为“持续观察几次”。"],
                "replacement_needed": [{"from": "观察几天", "to": "持续观察几次"}],
            }
        return {"score": 1, "verdict": "pass", "hard_hits": [], "suggestions": [], "replacement_needed": []}

    result = invoke_runtime_fast_generate_draft(
        _snapshot(),
        call_ge_func=fake_call_ge,
        call_ae_func=fake_call_ae,
        work_dir=tmp_path,
    )

    assert len(ge_calls) == 3
    assert len(ae_calls) == 3
    assert result["draft"]["body"] == "拿不准时问问靠谱渠道，也可以持续观察几次。"
    assert result["review_report"]["rewrite_required"] is False
    assert result["review_report"]["rewrite_rounds"] == 2
    assert result["review_report"]["rewrite_reason"] == "soft_suggestions"
    assert result["review_report"]["review_history"][0]["rewrite_reason"] == "soft_suggestions"
    assert result["review_report"]["review_history"][1]["rewrite_reason"] == "soft_suggestions"


def test_invoke_runtime_fast_rewrites_and_rescores_when_compliance_fails(tmp_path):
    ge_calls = []
    ae_calls = []

    def fake_call_ge(brief, spec_md, soul, style, voice, feedback=None, prev_draft=None, debug_dir=None, tag=""):
        ge_calls.append({"feedback": feedback, "prev_draft": prev_draft, "tag": tag})
        if feedback:
            assert "治疗便秘" in feedback
            assert "治疗便秘" in prev_draft
            return "源悦观察便便状态别着急\n\n先持续记录便便状态，日常观察肚肚舒不舒服。"
        return "源悦观察便便状态别着急\n\n不要用奶粉治疗便秘，先观察。"

    def fake_call_ae(ae, mode, brief, draft, debug_dir=None, tag=""):
        ae_calls.append({"draft": draft, "tag": tag})
        if "治疗便秘" in draft:
            return {"score": 0, "verdict": "fail", "hard_hits": ["治疗便秘"], "suggestions": ["删除治疗便秘"]}
        return {"score": 1, "verdict": "pass", "hard_hits": [], "suggestions": []}

    result = invoke_runtime_fast_generate_draft(
        _snapshot(),
        call_ge_func=fake_call_ge,
        call_ae_func=fake_call_ae,
        work_dir=tmp_path,
    )

    assert len(ge_calls) == 2
    assert len(ae_calls) == 2
    assert result["draft"]["body"] == "先持续记录便便状态，日常观察肚肚舒不舒服。"
    assert result["review_report"]["hard_results"][0]["pass"] is True
    assert result["review_report"]["rewrite_required"] is False
    assert result["review_report"]["rewrite_rounds"] == 1
    assert result["review_report"]["rewrite_reason"] == "hard_fail"
    assert "治疗便秘" in result["review_report"]["previous_review"]["hard_results"][0]["evidence"]
