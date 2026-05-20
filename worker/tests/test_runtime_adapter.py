"""Tests for MAGA xhs-writer runtime adapter."""
from __future__ import annotations

import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import yaml

from maga_worker.runtime_adapter import (
    build_runtime_brief_from_snapshot,
    default_output_dir,
    invoke_runtime_fast_generate_draft,
    invoke_runtime_fast_review_and_rewrite,
    invoke_runtime_generate_draft,
)
from maga_worker import xhs_runtime
from maga_worker.xhs_runtime import call_ae, call_legal_review


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
            "xhs_writer.ge.system": {"version_id": 1, "content": "BUNDLE_SYSTEM"},
            "xhs_writer.ge.style_templates": {"version_id": 2, "content": "BUNDLE_STYLE"},
            "xhs_writer.ge.voice_dictionary": {"version_id": 3, "content": "BUNDLE_VOICE"},
            "xhs_writer.ae.compliance_redline.system": {"version_id": 4, "content": "BUNDLE_AE_SYSTEM"},
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


def _legal_pass(brief, draft, debug_dir=None, tag=""):
    return {"score": 1, "verdict": "pass", "hard_hits": [], "suggestions": []}


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


def test_invoke_runtime_fast_generate_draft_returns_initial_draft_only(tmp_path):
    def fake_call_ge(brief, spec_md, system, style, voice, debug_dir=None, tag=""):
        assert system
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

    result = invoke_runtime_fast_generate_draft(
        _snapshot(),
        call_ge_func=fake_call_ge,
        work_dir=tmp_path,
    )

    assert result["draft"] == {"title": "源悦观察便便状态别着急", "body": "先看便便软硬和肚肚舒不舒服。"}
    assert result["runtime_result"]["mode"] == "runtime_fast"
    assert result["runtime_result"]["phase"] == "generate_draft"
    assert Path(result["runtime_result"]["draft_path"]).exists()
    assert "review_report" not in result


def test_runtime_fast_generate_draft_uses_compiled_runtime_brief(tmp_path):
    compiled_brief = build_runtime_brief_from_snapshot(_snapshot())
    compiled_brief["brief_id"] = "compiled-brief-001"
    compiled_brief["product_topic"] = "编译后的主题"
    compiled_brief["campaign"]["topic"] = "编译后的主题"

    def fake_call_ge(brief, spec_md, system, style, voice, debug_dir=None, tag=""):
        assert brief["brief_id"] == "compiled-brief-001"
        assert brief["product_topic"] == "编译后的主题"
        assert "编译后的主题" in spec_md
        return "编译后的标题\n\n编译后的正文"

    result = invoke_runtime_fast_generate_draft(
        _snapshot(),
        runtime_brief=compiled_brief,
        call_ge_func=fake_call_ge,
        work_dir=tmp_path,
    )

    assert result["draft"]["title"] == "编译后的标题"
    assert Path(result["runtime_result"]["brief_path"]).name == "compiled-brief-001.brief.yaml"


def test_invoke_runtime_fast_prefers_prompt_bundle_for_ge_prompt_parts(tmp_path):
    snapshot = _snapshot()
    snapshot["prompt_bundle_snapshot"] = _prompt_bundle()

    def fake_call_ge(brief, spec_md, system, style, voice, debug_dir=None, tag="", **kwargs):
        assert system == "BUNDLE_SYSTEM"
        assert style == "BUNDLE_STYLE"
        assert voice == "BUNDLE_VOICE"
        return "源悦观察便便状态别着急\n\n先看便便软硬和肚肚舒不舒服。"

    result = invoke_runtime_fast_generate_draft(
        snapshot,
        call_ge_func=fake_call_ge,
        work_dir=tmp_path,
    )

    assert result["draft"]["title"] == "源悦观察便便状态别着急"


def test_call_ae_prefers_prompt_bundle_for_system_corpus_and_rubric(monkeypatch, tmp_path):
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
    assert captured["system"] == "BUNDLE_AE_SYSTEM"
    assert "BUNDLE_CORPUS_ITEM" in captured["user"]
    assert "BUNDLE_RUBRIC" in captured["user"]


def test_call_legal_review_checks_title_and_body_with_tencent_semantics(monkeypatch, tmp_path):
    seen_texts = []

    def fake_verify_text_content(text, biztype=None):
        seen_texts.append((text, biztype))
        if "治疗便秘" in text:
            return {
                "suggestion": "Block",
                "raw": {"Suggestion": "Block", "Label": "Illegal", "Keywords": ["治疗便秘"]},
                "mock": False,
            }
        return {"suggestion": "Pass", "raw": {"Suggestion": "Pass"}, "mock": False}

    monkeypatch.setattr(xhs_runtime, "_load_tencent_text_verifier", lambda: fake_verify_text_content)
    monkeypatch.setenv("TENCENT_TEXT_BIZTYPE", "article_review")

    result = call_legal_review(
        build_runtime_brief_from_snapshot(_snapshot()),
        "标题：源悦观察便便状态别着急\n正文：不要用奶粉治疗便秘。",
        debug_dir=tmp_path,
        tag="unit",
    )

    assert seen_texts == [
        ("源悦观察便便状态别着急", "article_review"),
        ("不要用奶粉治疗便秘。", "article_review"),
    ]
    assert result["score"] == 0
    assert result["verdict"] == "fail"
    assert "治疗便秘" in result["hard_hits"][0]
    assert (tmp_path / "legal-tencent_review-unit.json").exists()


def test_runtime_fast_reviews_run_with_timeout_and_fixed_output_order(monkeypatch, tmp_path):
    monkeypatch.setenv("XHS_RUNTIME_REVIEW_TIMEOUT_SECONDS", "0.01")
    monkeypatch.setenv("XHS_RUNTIME_LEGAL_REVIEW_TIMEOUT_SECONDS", "0.01")

    def fake_call_ge(brief, spec_md, system, style, voice, debug_dir=None, tag="", **kwargs):
        return "源悦观察便便状态别着急\n\n先看便便软硬和肚肚舒不舒服。"

    def fake_call_ae(ae, mode, brief, draft, debug_dir=None, tag=""):
        if ae == "expression_writing":
            time.sleep(0.05)
        return {"score": 1, "verdict": "pass", "hard_hits": [], "suggestions": []}

    def slow_legal_review(brief, draft, debug_dir=None, tag=""):
        time.sleep(0.05)
        return {"score": 0, "verdict": "fail", "hard_hits": ["should be fail-open"], "suggestions": []}

    result = invoke_runtime_fast_review_and_rewrite(
        _snapshot(),
        {"title": "源悦观察便便状态别着急", "body": "先看便便软硬和肚肚舒不舒服。"},
        call_ge_func=fake_call_ge,
        call_ae_func=fake_call_ae,
        call_legal_review_func=slow_legal_review,
        work_dir=tmp_path,
    )

    hard_results = result["review_report"]["hard_results"]
    assert [item["ae_code"] for item in hard_results] == [
        "compliance_redline",
        "expression_writing",
        "time_logic",
        "legal_tencent",
    ]
    assert hard_results[1]["pass"] is False
    assert "timeout after 0.01s" in hard_results[1]["evidence"][0]
    assert hard_results[3]["pass"] is True
    assert result["review_report"]["rewrite_required"] is True


def test_runtime_fast_review_and_rewrite_uses_compiled_runtime_brief(tmp_path):
    compiled_brief = build_runtime_brief_from_snapshot(_snapshot())
    compiled_brief["brief_id"] = "compiled-review-001"
    seen = {}

    def fake_call_ge(brief, spec_md, system, style, voice, debug_dir=None, tag="", **kwargs):
        seen["ge_brief_id"] = brief["brief_id"]
        return "源悦观察便便状态别着急\n\n改写后的正文。"

    def fake_call_ae(ae, mode, brief, draft, debug_dir=None, tag=""):
        seen.setdefault("ae_brief_ids", set()).add(brief["brief_id"])
        if ae == "compliance_redline" and "需要改写" in draft:
            return {"score": 1, "verdict": "pass", "hard_hits": [], "suggestions": ["改写一下"]}
        return {"score": 1, "verdict": "pass", "hard_hits": [], "suggestions": []}

    result = invoke_runtime_fast_review_and_rewrite(
        _snapshot(),
        {"title": "源悦观察便便状态别着急", "body": "需要改写。"},
        runtime_brief=compiled_brief,
        call_ge_func=fake_call_ge,
        call_ae_func=fake_call_ae,
        call_legal_review_func=_legal_pass,
        work_dir=tmp_path,
    )

    assert result["final"]["body"] == "改写后的正文。"
    assert seen["ge_brief_id"] == "compiled-review-001"
    assert seen["ae_brief_ids"] == {"compiled-review-001"}


def test_invoke_runtime_fast_uses_model_config_from_maga_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("XHS_RUNTIME_MODEL_GE", "existing-ge")
    monkeypatch.delenv("XHS_RUNTIME_MODEL_AE", raising=False)
    seen = {}
    snapshot = _snapshot()
    snapshot["model_config"] = {"ge_model": "maga-ge", "ae_model": "maga-ae"}

    def fake_call_ge(brief, spec_md, system, style, voice, debug_dir=None, tag="", **kwargs):
        import os

        seen["ge_model"] = os.environ.get("XHS_RUNTIME_MODEL_GE")
        return "源悦观察便便状态别着急\n\n先看便便软硬和肚肚舒不舒服。"

    def fake_call_ae(ae, mode, brief, draft, debug_dir=None, tag=""):
        import os

        seen["ae_model"] = os.environ.get("XHS_RUNTIME_MODEL_AE")
        if ae == "compliance_redline":
            return {"score": 1, "verdict": "pass", "suggestions": ["轻微修订"]}
        return {"score": 1, "verdict": "pass", "suggestions": []}

    invoke_runtime_fast_review_and_rewrite(
        snapshot,
        {"title": "源悦观察便便状态别着急", "body": "先看便便软硬和肚肚舒不舒服。"},
        call_ge_func=fake_call_ge,
        call_ae_func=fake_call_ae,
        call_legal_review_func=_legal_pass,
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

    def fake_call_ge(brief, spec_md, system, style, voice, feedback=None, prev_draft=None, debug_dir=None, tag=""):
        ge_calls.append({"feedback": feedback, "prev_draft": prev_draft, "tag": tag})
        if feedback:
            assert "拿不准时问问靠谱渠道" in feedback
            assert "必要时问专业人士" in prev_draft
            return "源悦观察便便状态别着急\n\n拿不准时问问靠谱渠道，日常观察肚肚舒不舒服。"
        return "源悦观察便便状态别着急\n\n必要时问专业人士，日常观察肚肚舒不舒服。"

    def fake_call_ae(ae, mode, brief, draft, debug_dir=None, tag=""):
        ae_calls.append({"draft": draft, "tag": tag})
        if ae != "compliance_redline":
            return {"score": 1, "verdict": "pass", "hard_hits": [], "suggestions": [], "replacement_needed": []}
        if "必要时问专业人士" in draft:
            return {
                "score": 1,
                "verdict": "pass",
                "hard_hits": [],
                "suggestions": ["“必要时问专业人士”建议改为“拿不准时问问靠谱渠道”。"],
                "replacement_needed": [{"from": "必要时问专业人士", "to": "拿不准时问问靠谱渠道"}],
            }
        return {"score": 1, "verdict": "pass", "hard_hits": [], "suggestions": [], "replacement_needed": []}

    result = invoke_runtime_fast_review_and_rewrite(
        _snapshot(),
        {"title": "源悦观察便便状态别着急", "body": "必要时问专业人士，日常观察肚肚舒不舒服。"},
        call_ge_func=fake_call_ge,
        call_ae_func=fake_call_ae,
        call_legal_review_func=_legal_pass,
        work_dir=tmp_path,
    )

    assert len(ge_calls) == 1
    assert len(ae_calls) == 6
    assert result["final"]["body"] == "拿不准时问问靠谱渠道，日常观察肚肚舒不舒服。"
    assert result["review_report"]["hard_results"][0]["pass"] is True
    assert result["review_report"]["rewrite_required"] is False
    assert result["review_report"]["rewrite_rounds"] == 1
    assert result["review_report"]["rewrite_reason"] == "soft_suggestions"
    assert result["review_report"]["previous_review"]["suggestions"]


def test_invoke_runtime_fast_allows_second_rewrite_when_first_recheck_still_has_suggestions(tmp_path):
    ge_calls = []
    ae_calls = []

    def fake_call_ge(brief, spec_md, system, style, voice, feedback=None, prev_draft=None, debug_dir=None, tag=""):
        ge_calls.append({"feedback": feedback, "prev_draft": prev_draft, "tag": tag})
        if len(ge_calls) == 1:
            assert tag == "runtime_fast_rewrite_1"
            assert "必要时问专业人士" in feedback
            return "源悦观察便便状态别着急\n\n拿不准时问问靠谱渠道，也可以观察几天。"
        assert tag == "runtime_fast_rewrite_2"
        assert "观察几天" in feedback
        return "源悦观察便便状态别着急\n\n拿不准时问问靠谱渠道，也可以持续观察几次。"

    def fake_call_ae(ae, mode, brief, draft, debug_dir=None, tag=""):
        ae_calls.append({"draft": draft, "tag": tag})
        if ae != "compliance_redline":
            return {"score": 1, "verdict": "pass", "hard_hits": [], "suggestions": [], "replacement_needed": []}
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

    result = invoke_runtime_fast_review_and_rewrite(
        _snapshot(),
        {"title": "源悦观察便便状态别着急", "body": "必要时问专业人士，也可以观察几天。"},
        call_ge_func=fake_call_ge,
        call_ae_func=fake_call_ae,
        call_legal_review_func=_legal_pass,
        work_dir=tmp_path,
    )

    assert len(ge_calls) == 2
    assert len(ae_calls) == 9
    assert result["final"]["body"] == "拿不准时问问靠谱渠道，也可以持续观察几次。"
    assert result["review_report"]["rewrite_required"] is False
    assert result["review_report"]["rewrite_rounds"] == 2
    assert result["review_report"]["rewrite_reason"] == "soft_suggestions"
    assert result["review_report"]["review_history"][0]["rewrite_reason"] == "soft_suggestions"
    assert result["review_report"]["review_history"][1]["rewrite_reason"] == "soft_suggestions"


def test_invoke_runtime_fast_rewrites_and_rescores_when_compliance_fails(tmp_path):
    ge_calls = []
    ae_calls = []

    def fake_call_ge(brief, spec_md, system, style, voice, feedback=None, prev_draft=None, debug_dir=None, tag=""):
        ge_calls.append({"feedback": feedback, "prev_draft": prev_draft, "tag": tag})
        if feedback:
            assert "治疗便秘" in feedback
            assert "治疗便秘" in prev_draft
            return "源悦观察便便状态别着急\n\n先持续记录便便状态，日常观察肚肚舒不舒服。"
        return "源悦观察便便状态别着急\n\n不要用奶粉治疗便秘，先观察。"

    def fake_call_ae(ae, mode, brief, draft, debug_dir=None, tag=""):
        ae_calls.append({"draft": draft, "tag": tag})
        if ae != "compliance_redline":
            return {"score": 1, "verdict": "pass", "hard_hits": [], "suggestions": []}
        if "治疗便秘" in draft:
            return {"score": 0, "verdict": "fail", "hard_hits": ["治疗便秘"], "suggestions": ["删除治疗便秘"]}
        return {"score": 1, "verdict": "pass", "hard_hits": [], "suggestions": []}

    result = invoke_runtime_fast_review_and_rewrite(
        _snapshot(),
        {"title": "源悦观察便便状态别着急", "body": "不要用奶粉治疗便秘，先观察。"},
        call_ge_func=fake_call_ge,
        call_ae_func=fake_call_ae,
        call_legal_review_func=_legal_pass,
        work_dir=tmp_path,
    )

    assert len(ge_calls) == 1
    assert len(ae_calls) == 6
    assert result["final"]["body"] == "先持续记录便便状态，日常观察肚肚舒不舒服。"
    assert result["review_report"]["hard_results"][0]["pass"] is True
    assert result["review_report"]["rewrite_required"] is False
    assert result["review_report"]["rewrite_rounds"] == 1
    assert result["review_report"]["rewrite_reason"] == "hard_fail"
    assert "治疗便秘" in result["review_report"]["previous_review"]["hard_results"][0]["evidence"]
