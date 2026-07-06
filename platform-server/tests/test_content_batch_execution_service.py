"""Tests for executing planned batch content items."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.content_agent import (
    ContentAgentRun,
    ContentAgentStageCall,
    ContentAgentTask,
    ContentBatchItem,
    ContentBatchJob,
    ExecutorRegistry,
)
from app.models.expert_config import ExpertConfig
from app.models.maga_assets import AssetRegistry
from app.services.content_batch_execution_service import (
    ContentBatchExecutionService,
    _blocking_product_experience_phrase_hits,
    _body_title_candidates,
    _fallback_wangyue_growth_nutrition_body,
    _fallback_title_for_item,
    _max_product_experience_phrase_rewrite_rounds,
    _mouth_phrase_budget_hits,
    _mouth_phrase_budget_rewrite_input,
    _sanitize_generated_title_format,
    _semantic_wangyue_context_reasons,
    _should_mark_only_product_experience_phrase_review,
    _should_repair_product_experience_llm_quality,
    _should_rewrite_product_experience_llm_quality,
    _should_review_product_experience_llm_quality,
    _title_guard_reasons,
    _title_weighted_len,
    _rewrite_removed_required_wangyue_product,
    _restore_product_permission_wangyue_surface,
    _restore_wangyue_selling_context_surface,
)
from app.services.ai_flavor_humanizer_service import AIFlavorReview
from app.services.executor_invocation_service import InvokeResult, MockExecutorInvocationClient
from app.services.forbidden_term_review_service import ForbiddenTermReviewService, find_forbidden_hits
from app.services.product_experience_phrase_guard_service import (
    review_product_experience_phrase,
    sanitize_adult_self_drinking_phrases,
    sanitize_baby_milk_action_phrases,
    sanitize_common_ai_closure,
    sanitize_formula_dry_powder_ingestion,
    sanitize_odd_product_experience_phrases,
    sanitize_product_experience_format,
    sanitize_temporal_context,
    sanitize_wangyue_context_phrases,
    sanitize_wangyue_formula_usage_form,
    sanitize_wangyue_time_event_context,
)
from app.services.product_experience_llm_review_service import (
    ProductExperienceLLMIssue,
    ProductExperienceLLMReview,
    _SYSTEM_PROMPT,
    _calibrate_review_with_context,
    _review_model_config,
    _user_prompt,
    parse_product_experience_llm_review,
)
from app.services.royal_friso_ugc_structure_guard_service import RoyalFrisoUGCStructureGuardService


def _execution_tables():
    return [
        ContentBatchJob.__table__,
        ContentBatchItem.__table__,
        ExecutorRegistry.__table__,
        ContentAgentTask.__table__,
        ContentAgentRun.__table__,
        ContentAgentStageCall.__table__,
        AssetRegistry.__table__,
        ExpertConfig.__table__,
    ]


def test_royal_friso_structure_guard_catches_expanded_surface_patterns():
    review = RoyalFrisoUGCStructureGuardService().review(
        title="小袜子短了一截",
        body=(
            "娃脚长得真快，家里喝的是皇家美素佳儿。"
            "今天按季节理衣柜，发现小衣服都穿不下了。"
            "下午那顿奶磨蹭得很，最近喝的皇家美素佳儿。"
            "冲好喝了一杯，小家伙接得倒挺自然，把奶瓶往桌上一放。"
            "递过去，他接住喝着，碗往床上一放。只有咕噜咕噜的喝奶声。"
            "她握着奶瓶边喝边翻书，他手里的皇家美素佳儿放下了，又把奶瓶递过来。"
        ),
        plan={"asset_key": "royal_friso_ugc_post_rules_v1"},
    )

    assert review is not None
    codes = {issue.code for issue in review.issues}
    assert codes >= {
        "child_self_handling_formula",
        "cup_quantity_for_formula",
        "formula_container_form_error",
        "growth_or_nutrition_attribution",
        "season_context",
        "current_negative_then_product",
        "milk_residual_or_drinking_claim",
    }


def test_mouth_phrase_budget_hits_only_unassigned_terms():
    item = ContentBatchItem(
        item_no=1,
        title="最近还在喝旺玥",
        body="除了贵点，喝着还算踏实。",
        plan_json={
            "mouth_phrase_budget": {
                "enabled": True,
                "allowed_terms": ["最近"],
                "avoid_terms": ["最近", "除了贵", "踏实"],
            }
        },
    )

    assert _mouth_phrase_budget_hits(item) == ["除了贵", "踏实"]

    payload = _mouth_phrase_budget_rewrite_input(item, ["除了贵", "踏实"])

    assert payload["rewrite_source"] == "mouth_phrase_budget_guard"
    assert payload["review_report"]["mouth_phrase_budget_hits"] == ["除了贵", "踏实"]
    assert "只处理这些本篇未分配的批量高频口癖：除了贵、踏实" in payload["rewrite_instructions"][0]
    assert "硬性验收：改写后的 title/body 里不能再出现这些完整字符串：除了贵、踏实" in payload["rewrite_instructions"][1]
    assert "优先把含口癖的收尾半句或整句删掉" in payload["rewrite_instructions"][2]


def test_article_length_guard_marks_reasoning_leak_unusable_without_rewrite():
    item = ContentBatchItem(
        item_no=1,
        title="旺玥记录",
        body="<think>先分析一下</think>今天就简单写旺玥。",
        quality_json={"review_report": {"rewrite_required": False}, "hard_pass": True},
    )

    result = ContentBatchExecutionService._repair_article_length_if_needed(item)

    assert result == {
        "pass": False,
        "status": "reasoning_leak",
        "body_chars": len("<think>先分析一下</think>今天就简单写旺玥。"),
        "min_chars": 30,
        "max_chars": 600,
        "rewrite_required": False,
        "manual_review_required": True,
        "reason": "正文包含模型推理泄露，疑似生成异常",
    }
    assert item.quality_json["hard_pass"] is False
    assert item.quality_json["review_report"]["rewrite_required"] is True
    assert item.quality_json["review_report"]["rewrite_reason"] == "正文包含模型推理泄露，疑似生成异常"
    assert item.quality_json["postprocess_blocked"]["source"] == "article_length_guard"
    assert item.quality_json["postprocess_blocked"]["reasons"] == ["reasoning_leak"]


def test_wangyue_versioned_assets_enable_product_experience_llm_review():
    assert _should_review_product_experience_llm_quality(
        {
            "rule_type": "business_rule",
            "asset_key": "wangyue_v138_positive_effect_no_safety_attractor_article_rules",
            "corpus": "0705旺玥活动",
        }
    )


def test_wangyue_v152_light_postprocess_marks_non_hard_llm_review_without_rewrite():
    review = ProductExperienceLLMReview(
        pass_=False,
        rewrite_required=True,
        severity="rewrite",
        issues=[
            ProductExperienceLLMIssue(
                code="overcomplete_decision_chain",
                evidence="",
                reason="",
                rewrite_direction="",
            )
        ],
    )

    assert not _should_rewrite_product_experience_llm_quality(
        {
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "corpus": "0705旺玥活动",
        },
        review,
    )


def test_wangyue_claim_risk_and_product_appearance_llm_review_is_mark_only():
    review = ProductExperienceLLMReview(
        pass_=False,
        rewrite_required=True,
        severity="hard",
        issues=[
            ProductExperienceLLMIssue(
                code="claim_risk",
                evidence="",
                reason="",
                rewrite_direction="",
            ),
            ProductExperienceLLMIssue(
                code="unnatural_product_appearance",
                evidence="",
                reason="",
                rewrite_direction="",
            )
        ],
    )

    plan = {
        "rule_type": "business_rule",
        "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
        "corpus": "0705旺玥活动",
    }
    assert not _should_rewrite_product_experience_llm_quality(plan, review)
    assert not _should_repair_product_experience_llm_quality(plan, review)


def test_wangyue_non_mark_only_hard_llm_review_still_rewrites():
    review = ProductExperienceLLMReview(
        pass_=False,
        rewrite_required=True,
        severity="hard",
        issues=[
            ProductExperienceLLMIssue(
                code="formula_usage_form_error",
                evidence="",
                reason="",
                rewrite_direction="",
            )
        ],
    )

    assert _should_rewrite_product_experience_llm_quality(
        {
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "corpus": "0705旺玥活动",
        },
        review,
    )


def test_overcomplete_decision_chain_only_never_triggers_llm_quality_rewrite():
    review = ProductExperienceLLMReview(
        pass_=False,
        rewrite_required=True,
        severity="rewrite",
        issues=[
            ProductExperienceLLMIssue(
                code="overcomplete_decision_chain",
                evidence="",
                reason="",
                rewrite_direction="",
            )
        ],
    )

    assert not _should_rewrite_product_experience_llm_quality(
        {
            "rule_type": "business_rule",
            "asset_key": "wangyue_painpoint_selling_posttype_matrix_v32_20260624",
            "corpus": "0705旺玥活动",
        },
        review,
    )


def test_wangyue_v152_light_postprocess_marks_effect_chain_phrase_guard_only():
    base_review = review_product_experience_phrase(
        title="随手记",
        body="朋友问我家喝什么，我说旺玥。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "corpus": "0705旺玥活动",
        },
    )
    review = replace(
        base_review,
        pass_=False,
        rewrite_required=True,
        reasons=["product_effect_proof_chain"],
    )

    assert _should_mark_only_product_experience_phrase_review(
        {
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "corpus": "0705旺玥活动",
        },
        review,
    )


def test_wangyue_v155_marks_effect_chain_phrase_guard_only():
    base_review = review_product_experience_phrase(
        title="补货日常",
        body="开了一罐新的旺玥，上次那罐喝完接上这罐，孩子放学回来还有精力跑跳，别人问怎么老买这个，我就说孩子愿意喝。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v155_title_rule_slim_article_rules",
            "corpus": "0705旺玥活动",
        },
    )
    review = replace(
        base_review,
        pass_=False,
        rewrite_required=True,
        reasons=["product_effect_proof_chain"],
    )

    assert _should_mark_only_product_experience_phrase_review(
        {
            "rule_type": "business_rule",
            "asset_key": "wangyue_v155_title_rule_slim_article_rules",
            "corpus": "0705旺玥活动",
        },
        review,
    )


def test_wangyue_v2_marks_soft_closure_and_state_template_only():
    review = review_product_experience_phrase(
        title="密集活动周，全勤没掉线",
        body=(
            "最近幼儿园活动扎堆，以前总要担心他回家后的状态。"
            "坚持给他喝旺玥一段时间，发现出勤和精神头都稳得很。"
            "回家还能正常吃饭、玩玩具，老母亲观察了好几回，确实省心。"
            "当初选旺玥就是看中乳铁蛋白的含量，帮助小朋友构建保护力。"
            "现在看他每天状态在线，我也能安心忙自己的事了。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v2_core_storyline_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert set(review.reasons) == {
        "common_ai_closure_phrase",
        "hard_ai_closure_phrase",
        "state_template_phrase",
    }
    assert _should_mark_only_product_experience_phrase_review(
        {
            "rule_type": "business_rule",
            "asset_key": "wangyue_v2_core_storyline_article_rules",
            "corpus": "0705旺玥活动",
        },
        review,
    )


def test_wangyue_v2_keeps_age_context_as_rewrite():
    base_review = review_product_experience_phrase(
        title="一岁多开始喝旺玥",
        body="一岁多开始喝旺玥，后来状态挺稳。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v2_core_storyline_article_rules",
            "corpus": "0705旺玥活动",
        },
    )
    review = replace(
        base_review,
        pass_=False,
        rewrite_required=True,
        reasons=["wangyue_explicit_age_context"],
    )

    assert not _should_mark_only_product_experience_phrase_review(
        {
            "rule_type": "business_rule",
            "asset_key": "wangyue_v2_core_storyline_article_rules",
            "corpus": "0705旺玥活动",
        },
        review,
    )


def test_wangyue_skeleton_hits_are_distribution_signal_not_rewrite_reason():
    review = review_product_experience_phrase(
        title="选奶这事",
        body="选奶时对比了几款，旺玥趁活动补了两罐，孩子口味接受，家里安排起来好执行。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v183_prompt_slot_slim_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert {"selection_process", "price", "kid_acceptance", "ai_closure"}.issubset(
        set(review.skeleton_parts)
    )
    assert "complete_selection_price_acceptance_closure_skeleton" not in review.reasons
    assert review.rewrite_required is False


def test_wangyue_v152_light_phrase_guard_marker_keeps_soft_effect_chain_mark_only():
    base_review = review_product_experience_phrase(
        title="放学回来那杯",
        body="放学回来我给他冲一杯旺玥，孩子喝完会自己去玩一会儿，状态看着比前阵子稳一点，我心里也踏实些。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "corpus": "0705旺玥活动",
        },
    )
    review = replace(
        base_review,
        pass_=False,
        rewrite_required=True,
        reasons=["product_effect_proof_chain"],
    )
    item = ContentBatchItem(
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "corpus": "0705旺玥活动",
        },
        quality_json={},
    )
    service = ContentBatchExecutionService.__new__(ContentBatchExecutionService)

    service._mark_product_experience_phrase_review(item, review)

    quality = item.quality_json
    assert quality["product_experience_phrase_guard"]["rewrite_required"] is True
    assert quality["product_experience_phrase_guard"]["mark_rewrite_required"] is False
    assert quality["review_report"].get("rewrite_required") is not True


def test_wangyue_v152_light_postprocess_keeps_time_event_phrase_guard_as_rewrite():
    base_review = review_product_experience_phrase(
        title="随手记",
        body="朋友问我家喝什么，我说旺玥。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "corpus": "0705旺玥活动",
        },
    )
    review = replace(
        base_review,
        pass_=False,
        rewrite_required=True,
        reasons=["wangyue_time_event_context"],
    )

    assert not _should_mark_only_product_experience_phrase_review(
        {
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "corpus": "0705旺玥活动",
        },
        review,
    )


def test_wangyue_v152_flags_relative_time_effect_feedback_after_comma():
    review = review_product_experience_phrase(
        title="这次补货还是没换",
        body=(
            "翻出快递箱，旺玥罐子正好喝完。这次补货还是没换，家里存货里继续留着。"
            "前两天在外面跑了一下午，回来精神头还足。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert "explicit_temporal_context" in review.reasons
    assert review.rewrite_required is True


def test_wangyue_v152_flags_current_attention_effect_feedback():
    review = review_product_experience_phrase(
        title="选4段时别人问我看什么",
        body=(
            "朋友问我给娃选4段奶粉主要看啥，我说我盯准了DHA。"
            "最近娃坐桌前画画，以前画两笔就跑，现在能安安静静涂完一整张。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert "explicit_temporal_context" in review.reasons
    assert review.rewrite_required is True


def test_wangyue_v152_flags_current_observation_effect_feedback_across_comma():
    review = review_product_experience_phrase(
        title="接娃回来还有精神",
        body=(
            "幼儿园集体环境接触多，之前总担心容易中招。"
            "这段时间观察下来，放学回来还能叽叽喳喳讲班里的事，精神头在线。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert "explicit_temporal_context" in review.reasons
    assert review.rewrite_required is True


def test_wangyue_v152_light_limits_semantic_phrase_guard_to_one_rewrite_round():
    base_review = review_product_experience_phrase(
        title="顺手记",
        body="孩子接触多，我选旺玥也是看中保护力。一杯下去又活过来了，也没有动不动就掉状态。",
        plan={"asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules"},
    )
    odd_review = replace(
        base_review,
        pass_=False,
        rewrite_required=True,
        reasons=["odd_product_experience_phrase"],
    )
    logic_review = replace(
        base_review,
        pass_=False,
        rewrite_required=True,
        reasons=["wangyue_article_logic_drift_context"],
    )
    hard_mixed_review = replace(
        base_review,
        pass_=False,
        rewrite_required=True,
        reasons=["wangyue_article_logic_drift_context", "wangyue_time_event_context"],
    )

    plan = {"asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules"}
    assert _max_product_experience_phrase_rewrite_rounds(plan, odd_review) == 1
    assert _max_product_experience_phrase_rewrite_rounds(plan, logic_review) == 1
    assert _max_product_experience_phrase_rewrite_rounds(plan, hard_mixed_review) == 2
    assert _max_product_experience_phrase_rewrite_rounds({"asset_key": "wangyue_article_business_rules"}, logic_review) == 2


def test_mouth_phrase_budget_hits_ignore_substring_inside_allowed_phrase():
    item = ContentBatchItem(
        item_no=1,
        title="带孩子出门一趟",
        body="旺玥这罐让我心里有底，但这句话里没有其他收口。",
        plan_json={
            "mouth_phrase_budget": {
                "enabled": True,
                "allowed_terms": ["心里有底"],
                "avoid_terms": ["心里", "心里有底", "放心"],
            }
        },
    )

    assert _mouth_phrase_budget_hits(item) == []


def test_generated_title_format_keeps_allowed_surface_emoji_only():
    assert _sanitize_generated_title_format("标题：你家请假多不多😅") == "你家请假多不多"
    assert _sanitize_generated_title_format("标题：你家请假多不多😂") == "你家请假多不多😂"
    assert _sanitize_generated_title_format("补了一波日用品 🙂") == "补了一波日用品 🙂"
    assert _sanitize_generated_title_format("旺玥真香✨🔥🍼") == "旺玥真香"
    assert _sanitize_generated_title_format("又开一罐🥲😅") == "又开一罐🥲"
    assert _sanitize_generated_title_format("刚拆的快递里，🫙") == "刚拆的快递里，"


def test_title_weighted_len_counts_emoji_as_two_and_ignores_spaces():
    assert _title_weighted_len("又开一罐🥲") == 6
    assert _title_weighted_len("补货 😂") == 4
    assert _title_weighted_len("我当时选旺玥也就记得一个很简单的小点😂") == 20


def test_wangyue_title_guard_blocks_dangling_punctuation_after_format_cleanup():
    cleaned = _sanitize_generated_title_format("刚拆的快递里，🫙")

    assert cleaned == "刚拆的快递里，"
    assert "dangling_title_punctuation" in _title_guard_reasons(cleaned, set())


def test_wangyue_title_guard_blocks_weighted_title_length_over_twenty():
    assert "title_too_long" not in _title_guard_reasons("我当时选旺玥也就记得一个很简单的小点😂", set())
    assert "title_too_long" in _title_guard_reasons("我当时选旺玥也就记得一个很简单的小点而已😂", set())


def test_forbidden_hits_prefer_longer_overlapping_terms():
    hits = find_forbidden_hits(
        "娃倒没抗拒，价格也能接受。",
        ["没抗拒", "倒没抗拒", "能接", "能接受"],
    )

    assert hits.index("倒没抗拒") < hits.index("没抗拒")
    assert hits.index("能接受") < hits.index("能接")


def test_forbidden_hits_do_not_block_tianranruzhi_proprietary_term():
    assert find_forbidden_hits("奶粉里的天然乳脂确实帮助吸收了。", ["天然"]) == []
    assert find_forbidden_hits("不要写成天然成分。", ["天然"]) == ["天然"]


def test_product_experience_phrase_guard_allows_single_soft_closure_phrase():
    review = review_product_experience_phrase(
        title="睡前这杯还挺省心",
        body="晚上收拾完书包，顺手给娃冲一杯旺玥。他自己捧着喝完，我也不用再追着饭桌复盘太多，今天就这样记录一下。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：中短文；正文按130字左右写，可在120-150字之间。0705旺玥活动",
        },
    )

    assert review.ai_phrase_hits == ["省心"]
    assert review.rewrite_required is False
    assert review.pass_ is True


def test_product_experience_phrase_guard_blocks_empty_body():
    review = review_product_experience_phrase(
        title="有没有同款孩子",
        body="",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文40-130字。0705旺玥活动",
        },
    )

    assert "empty_body" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_reports_soft_closure_without_rewrite():
    review = review_product_experience_phrase(
        title="选旺玥这事心里有数了",
        body="翻成分表那会确实有点纠结，最后还是选了旺玥。孩子喝着还行，我现在心里有数一点，也踏实一点，但没打算写成什么神奇变化。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：中短文；正文按130字左右写，可在120-150字之间。0705旺玥活动",
        },
    )

    assert review.ai_phrase_hits == ["踏实", "心里有数"]
    assert "repeated_ai_closure_phrases" not in review.reasons
    assert review.rewrite_required is False
    assert review.pass_ is True


def test_product_experience_phrase_guard_blocks_weak_later_observation_tail():
    review = review_product_experience_phrase(
        title="消耗太快又续上了",
        body="旺玥是第三回续了，钙铁锌这些营养全，不用我额外操心补。先喝着，后面再看吧",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v139_example_kernel_slim_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert "common_ai_closure_phrase" in review.reasons
    assert review.rewrite_required is True


def test_product_experience_phrase_guard_blocks_state_template_combo():
    review = review_product_experience_phrase(
        title="换季这波还行",
        body="最近班里好几个请假的，娃每天早晚一杯旺玥，精神头足，状态一直在线，当妈的省心不少。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert review.state_template_hits == ["状态一直在线", "精神头足"]
    assert "state_template_phrase" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_product_effect_proof_chain():
    review = review_product_experience_phrase(
        title="放学后这杯",
        body="放学回来我给他冲一杯旺玥，孩子喝完会自己去玩一会儿，状态看着比前阵子稳一点，我心里也踏实些。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_painpoint_selling_posttype_matrix_v28_20260624",
            "post_type": "使用反馈/继续观察",
            "ugc_post_type": "使用反馈型",
            "corpus": "0705旺玥活动",
        },
    )

    assert "product_effect_proof_chain" in review.reasons
    assert "冲一杯" in review.product_effect_proof_chain_hits["product_action"]
    assert "状态" in review.product_effect_proof_chain_hits["effect_observation"]
    assert "踏实" in review.product_effect_proof_chain_hits["caregiver_closure"]
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_allows_single_product_basis_without_proof_chain():
    review = review_product_experience_phrase(
        title="看配方看晕了",
        body="儿童奶粉配方真的会看晕，我后来只记自己在意的点。旺玥这里我记住的是DHA和燕窝酸，算是选的时候多一层考虑。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_painpoint_selling_posttype_matrix_v28_20260624",
            "post_type": "轻测评/配方关注",
            "ugc_post_type": "轻测评型",
            "corpus": "0705旺玥活动",
        },
    )

    assert review.product_effect_proof_chain_hits == {}
    assert "product_effect_proof_chain" not in review.reasons
    assert review.rewrite_required is False
    assert review.pass_ is True


def test_product_experience_phrase_guard_allows_wangyue_short_effect_proof():
    review = review_product_experience_phrase(
        title="补货又开一罐",
        body="算了下这月的奶粉预算，还是把旺玥续上了。喝了小半年，饭还是有点挑，但营养跟得上，状态一直挺稳。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v140_single_chain_article_rules",
            "post_type": "复购/长期使用",
            "ugc_post_type": "复购/长期使用型",
            "corpus": "0705旺玥活动",
        },
    )

    assert review.product_effect_proof_chain_hits == {}
    assert "product_effect_proof_chain" not in review.reasons


def test_product_experience_phrase_guard_reports_decision_chain_as_signal_only():
    review = review_product_experience_phrase(
        title="晚饭后的补货",
        body=(
            "晚饭后想了想，旺玥又该补货了。我家吃饭一直不大稳定，"
            "奶粉算是长期留下的日常营养补充。主要是它补上饭里差的一块，"
            "孩子也接受，就续上了，当个保底留着。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_painpoint_selling_posttype_matrix_v32_20260624",
            "post_type": "复购/长期使用",
            "ugc_post_type": "复购/长期使用型",
            "corpus": "0705旺玥活动",
        },
    )

    assert set(review.decision_chain_hits) >= {
        "life_problem",
        "product_basis",
        "price_purchase",
        "kid_acceptance",
        "continuity_closure",
    }
    assert "overcomplete_decision_chain" not in review.reasons
    assert review.rewrite_required is False
    assert review.pass_ is True


def test_product_experience_phrase_guard_allows_short_repurchase_chain():
    review = review_product_experience_phrase(
        title="晚饭后的补货",
        body="晚饭后翻了下家里常备的奶粉，旺玥又该补货了。吃饭不太稳定，儿童奶粉就当日常营养补充留着。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_painpoint_selling_posttype_matrix_v32_20260624",
            "post_type": "复购/长期使用",
            "ugc_post_type": "复购/长期使用型",
            "corpus": "0705旺玥活动",
        },
    )

    assert review.decision_chain_hits == {}
    assert "overcomplete_decision_chain" not in review.reasons
    assert review.rewrite_required is False
    assert review.pass_ is True


def test_product_experience_phrase_guard_blocks_soft_product_proof_loop():
    review = review_product_experience_phrase(
        title="绿叶菜饭桌大战",
        body=(
            "晚饭桌上一碗绿叶菜，孩子拨来拨去最后推开。后来不想天天为这事较劲，"
            "儿童奶粉我留了一款旺玥在家里当补充，至少每天喝一杯能补上一些。"
            "孩子喝倒是愿意喝，至少奶粉能帮我兜住一部分营养，心里不那么慌。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_painpoint_selling_posttype_matrix_v29_20260624",
            "post_type": "问题解决/吃饭不稳",
            "ugc_post_type": "问题解决型",
            "corpus": "0705旺玥活动",
        },
    )

    assert "product_effect_proof_chain" in review.reasons
    assert "每天喝一杯" in review.product_effect_proof_chain_hits["product_action"]
    assert "愿意喝" in review.product_effect_proof_chain_hits["kid_acceptance"]
    assert "不那么慌" in review.product_effect_proof_chain_hits["caregiver_closure"]
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_common_ai_closure_variant():
    review = review_product_experience_phrase(
        title="旺玥记录",
        body="喝了两个月，娃个子没停长，摸后背终于有点肉感了，我心里总算踏实点。，先这么喂着",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "common_ai_closure_phrase" in review.reasons
    assert sanitize_common_ai_closure("踏实点。，先这么喂着") == "踏实点"
    assert sanitize_common_ai_closure("我也就当个早起动力吧。长势") == "我也就当个早起动力吧"


def test_product_experience_phrase_guard_still_blocks_hard_ai_closure_phrase():
    review = review_product_experience_phrase(
        title="旺玥记录",
        body="老母亲做了半天功课，最后还是选旺玥，孩子喝完我就觉得这事固定下来了。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：中短文；正文按130字左右写，可在120-150字之间。0705旺玥活动",
        },
    )

    assert "hard_ai_closure_phrase" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_adult_self_drinking_child_formula():
    review = review_product_experience_phrase(
        title="刚开了一罐奶粉",
        body="今晚陪娃写作业，顺手开了新到的旺玥，给自己冲了一杯。孩子在旁边写写画画，我就当日常记录一下。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert review.adult_self_drinking_hits == ["给自己冲了一杯"]
    assert "adult_self_drinking_child_formula" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_formula_dry_powder_ingestion():
    text = (
        "家里奶粉罐见底了，赶紧又开一罐旺玥。"
        "有妈妈问怎么选的，我就说冲着乳铁蛋白去的，孩子愿意喝就行。"
        "刚开罐那会他凑过来看，我舀了一勺放他嘴里，他笑着说好喝。"
    )
    review = review_product_experience_phrase(
        title="又开一罐，接着喝",
        body=text,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。复购/长期使用。",
        },
    )

    assert "formula_dry_powder_ingestion" in review.reasons
    assert review.formula_dry_powder_ingestion_hits == ["刚开罐那会他凑过来看，我舀了一勺放他嘴里，他笑着说好喝"]
    cleaned = sanitize_formula_dry_powder_ingestion(text)
    assert "舀了一勺" not in cleaned
    assert "放他嘴里" not in cleaned
    assert cleaned == "家里奶粉罐见底了，赶紧又开一罐旺玥。有妈妈问怎么选的，我就说冲着乳铁蛋白去的，孩子愿意喝就行"


def test_product_experience_phrase_guard_blocks_wangyue_ingredient_benefit_mismatch():
    text = (
        "我看中这个乳铁蛋白来着。"
        "她当时还纳闷乳铁蛋白是啥，我就说就是那个让娃抱起来沉一点的成分。"
        "最近背上摸着有肉，跑跳也有劲。"
    )
    review = review_product_experience_phrase(
        title="这罐喝着还挺明显",
        body=text,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。复购/长期使用。",
        },
    )

    assert "ingredient_benefit_mismatch" in review.reasons
    assert any(
        "乳铁蛋白是啥，我就说就是那个让娃抱起来沉一点" in hit
        for hit in review.ingredient_benefit_mismatch_hits
    )
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_weak_wangyue_ingredient_growth_bridge():
    review = review_product_experience_phrase(
        title="这罐还挺顺",
        body="朋友问我为什么留旺玥，我说它含有乳铁蛋白，对孩子体格比较友好，最近小身板看着结实些。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。复购/长期使用。",
        },
    )

    assert "ingredient_benefit_mismatch" in review.reasons
    assert any("乳铁蛋白，对孩子体格" in hit for hit in review.ingredient_benefit_mismatch_hits)


def test_product_experience_phrase_guard_blocks_wangyue_product_fact_number_drift():
    plan = {
        "rule_type": "business_rule",
        "asset_key": "wangyue_v347_selling_description_mainline_article_rules",
        "corpus": "写作规则：0705旺玥活动。",
    }

    risky_review = review_product_experience_phrase(
        title="整理衣柜发现娃又穿不下了",
        body="家里现在喝旺玥，钙铁锌和十几种关键营养都安排上了。",
        plan=plan,
    )
    safe_review = review_product_experience_phrase(
        title="活动量上来后选了旺玥",
        body="旺玥的钙铁锌和30多种关键营养，正好接在这个阶段的需求上。",
        plan=plan,
    )

    assert "product_fact_number_drift" in risky_review.reasons
    assert risky_review.product_fact_number_drift_hits == ["十几种关键营养"]
    assert "product_fact_number_drift" not in safe_review.reasons
    assert safe_review.product_fact_number_drift_hits == []


def test_product_experience_phrase_guard_blocks_wangyue_sleep_effect_scope_drift():
    review = review_product_experience_phrase(
        title="今天玩得超累，回来倒头就睡",
        body="结果洗完澡，旺玥喝完后自己爬上床就睡了，一整夜都很安稳。想想这段时间家里一直在喝旺玥，日常活动后的恢复力看得见。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v347_selling_description_mainline_article_rules",
            "painpoint": "保护力关注",
            "selling_point": "进阶保护力",
            "story_spine": "孩子日常活动后的自家状态；正向反馈回到活动后状态。",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )

    assert "effect_scope_drift" in review.reasons
    assert any("旺玥喝完后自己爬上床就睡" in hit for hit in review.effect_scope_drift_hits)


def test_product_experience_phrase_guard_allows_sleep_as_background_context():
    review = review_product_experience_phrase(
        title="看到这个旺玥罐罐",
        body=(
            "今天趁着娃午睡，顺手理了一下家里常备的东西，看到旺玥的罐子。"
            "家里常备它主要是娃不抗拒那点清淡奶香，钙铁锌和好几种营养也能一起顾上。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v351_mainline_positive_landing_article_rules",
            "painpoint": "营养不足",
            "selling_point": "营养丰富",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )

    assert review.effect_scope_drift_hits == []
    assert "effect_scope_drift" not in review.reasons


def test_product_experience_phrase_guard_blocks_nearby_wangyue_ingredient_growth_pairing():
    plan = {
        "rule_type": "business_rule",
        "asset_key": "wangyue_article_business_rules",
        "corpus": "写作规则：0705旺玥活动。复购/长期使用。",
    }

    after_review = review_product_experience_phrase(
        title="被问到奶粉怎么看",
        body="邻居问我怎么选奶粉，我说现在主要看乳铁蛋白。孩子最近抱起来沉了一点，背上肉实实的。",
        plan=plan,
    )
    before_review = review_product_experience_phrase(
        title="继续囤的奶粉",
        body="主要是户外活动回来状态挺稳，跑跳有劲，集体活动后也不蔫。乳铁蛋白这块当初相中之后就一直没换过。",
        plan=plan,
    )

    assert "ingredient_benefit_mismatch" in after_review.reasons
    assert "ingredient_benefit_mismatch" in before_review.reasons


def test_product_experience_phrase_guard_allows_correct_wangyue_benefit_mapping():
    plan = {
        "rule_type": "business_rule",
        "asset_key": "wangyue_article_business_rules",
        "corpus": "写作规则：0705旺玥活动。复购/长期使用。",
    }

    protection_review = review_product_experience_phrase(
        title="最近状态挺稳",
        body="朋友问我家喝什么，我说旺玥。主要看乳铁蛋白和保护力这块，最近状态挺稳，精神头也在线。",
        plan=plan,
    )
    growth_review = review_product_experience_phrase(
        title="三岁后的营养安排",
        body="三岁后这阶段我更看整体营养配置，旺玥钙铁锌这些基础营养给得比较全。最近抱起来沉一点，背上也有肉。",
        plan=plan,
    )

    assert "ingredient_benefit_mismatch" not in protection_review.reasons
    assert protection_review.ingredient_benefit_mismatch_hits == []
    assert "ingredient_benefit_mismatch" not in growth_review.reasons
    assert growth_review.ingredient_benefit_mismatch_hits == []


def test_product_experience_phrase_rewrite_input_preserves_strong_effect_with_correct_bridge():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。复购/长期使用。",
        },
        title="这罐喝着还挺明显",
        body="我看中这个乳铁蛋白来着。乳铁蛋白就是让娃抱起来沉一点的成分，背上摸着有肉，跑跳也有劲。",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    payload = service._product_experience_phrase_rewrite_input(item, review)
    instructions = "\n".join(payload["rewrite_instructions"])

    assert "ingredient_benefit_mismatch" in review.reasons
    assert "保留强正向效果证明" in instructions
    assert "乳铁蛋白/免疫球蛋白/HMO只承接保护力、少中招、状态稳" in instructions
    assert "阶段营养、整体营养配置、钙铁锌或营养丰富承接" in instructions
    assert "不要把强效果洗成“还在观察/不一定/每家不同”" in instructions


def test_product_experience_phrase_rewrite_input_repairs_fact_number_and_effect_scope_without_weakening():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v347_selling_description_mainline_article_rules",
            "painpoint": "保护力关注",
            "selling_point": "进阶保护力",
            "story_spine": "孩子日常活动后的自家状态；正向反馈回到活动后状态。",
            "corpus": "写作规则：0705旺玥活动。",
        },
        title="今天玩得超累",
        body="旺玥喝完后自己爬上床就睡了，一整夜都很安稳。钙铁锌和十几种关键营养都安排上了。",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    payload = service._product_experience_phrase_rewrite_input(item, review)
    instructions = "\n".join(payload["rewrite_instructions"])

    assert "product_fact_number_drift" in review.reasons
    assert "effect_scope_drift" in review.reasons
    assert "保留正向营养价值" in instructions
    assert "不要因为修数字而削弱种草" in instructions
    assert "删掉旺玥/喝奶与睡觉、整夜安稳、不闹腾这类睡眠效果之间的连接" in instructions
    assert "保留本篇业务规则里的正向价值" in instructions


def test_product_experience_formula_dry_powder_cleanup_deletes_hit_segment():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。复购/长期使用。",
        },
        title="又开一罐，接着喝",
        body=(
            "家里奶粉罐见底了，赶紧又开一罐旺玥。"
            "有妈妈问怎么选的，我就说冲着乳铁蛋白去的。"
            "刚开罐那会他凑过来看，我舀了一勺放他嘴里，他笑着说好喝。"
        ),
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    post_review = service._apply_product_experience_phrase_cleanups_once(item, review)

    assert "舀了一勺" not in item.body
    assert "放他嘴里" not in item.body
    assert "product_experience_formula_dry_powder_cleanups" in item.quality_json
    assert "product_experience_phrase_rewrites" not in item.quality_json
    assert "formula_dry_powder_ingestion" not in post_review.reasons


def test_product_experience_phrase_guard_allows_normal_formula_drinking_action():
    review = review_product_experience_phrase(
        title="今天这杯喝完了",
        body="我把旺玥冲好递过去，他自己拿着杯子喝完，又跑去翻贴纸书。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )

    assert "formula_dry_powder_ingestion" not in review.reasons
    assert "child_self_brewing_formula" not in review.reasons


def test_product_experience_phrase_guard_blocks_adult_child_formula_breakfast_milk():
    review = review_product_experience_phrase(
        title="喝奶这事，当妈的算不算瞎操心？",
        body="先试一罐吧，反正喝不完我自己也能当早餐奶。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "我自己也能当早餐奶" in review.adult_self_drinking_hits
    assert "adult_self_drinking_child_formula" in review.reasons
    assert sanitize_adult_self_drinking_phrases("先试一罐吧，反正喝不完我自己也能当早餐奶。") == "先试一罐吧"


def test_product_experience_phrase_guard_blocks_adult_tasting_child_formula():
    review = review_product_experience_phrase(
        title="囤奶粉的快乐谁懂啊",
        body="每次快喝完就赶紧囤，娃现在吃饭也比以前主动了，不知道是不是这奶的功劳，反正我自己喝着觉得挺香。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "我自己喝着觉得挺香" in review.adult_self_drinking_hits
    assert "adult_self_drinking_child_formula" in review.reasons
    assert "我自己喝着" not in sanitize_adult_self_drinking_phrases("反正我自己喝着觉得挺香。")


def test_product_experience_phrase_guard_blocks_adult_tasting_child_formula_variant():
    review = review_product_experience_phrase(
        title="旺玥开罐",
        body="泡了一杯自己先尝，甜味很淡，她倒是吨吨吨喝完了。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "泡了一杯自己先尝" in review.adult_self_drinking_hits
    assert "adult_self_drinking_child_formula" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_adult_try_drinking_title():
    review = review_product_experience_phrase(
        title="我喝着试了试",
        body="给闺女选旺玥这事，还是想先看看孩子日常营养能不能跟上。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )

    assert "我喝着试了试" in review.adult_self_drinking_hits
    assert "adult_self_drinking_child_formula" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_adult_formula_drinking_title():
    review = review_product_experience_phrase(
        title="她每天盯着我喝奶粉",
        body="孩子每天盯着我冲奶粉，嘴里念叨妈妈快点。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert review.adult_self_drinking_hits == ["我喝奶粉"]
    assert "adult_self_drinking_child_formula" in review.reasons
    assert sanitize_adult_self_drinking_phrases("她每天盯着我喝奶粉") == "她每天盯着孩子喝奶粉"


def test_product_experience_phrase_guard_blocks_adult_current_drinking_subject_drift():
    review = review_product_experience_phrase(
        title="现在能待这么久啊",
        body="刚好前阵子给他换了儿童奶粉，我现在喝的是皇家美素佳儿旺玥，主要是看中它眼脑那块营养。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )

    assert "我现在喝的是皇家美素佳儿旺玥" in review.adult_self_drinking_hits
    assert "adult_self_drinking_child_formula" in review.reasons
    assert (
        sanitize_adult_self_drinking_phrases("我现在喝的是皇家美素佳儿旺玥，主要是看中它眼脑那块营养。")
        == "给孩子选的是皇家美素佳儿旺玥，主要是看中它眼脑那块营养"
    )


def test_product_experience_odd_cleanup_removes_ai_lightness_title():
    cleaned = sanitize_odd_product_experience_phrases("谁懂这种当妈的轻松感")

    assert cleaned == "这种小变化我会留意"
    assert sanitize_odd_product_experience_phrases("小胳膊小腿看着结实了些，不知道是不是营养跟上了，先") == (
        "小胳膊小腿看着结实了些，不知道是不是营养跟上了"
    )
    assert sanitize_odd_product_experience_phrases("省得我老惦记他营养不均衡。踏实") == "省得我老惦记他营养不均衡"
    assert sanitize_odd_product_experience_phrases("这奶粉喝着还行～（你家娃在忙啥？）") == "这奶粉喝着还行～"
    assert sanitize_odd_product_experience_phrases("谁懂啊，当妈的心里就这点小算盘") == "这种小变化我会留意"
    assert sanitize_odd_product_experience_phrases("皇家美美佳儿旺玥") == "皇家美素佳儿旺玥"


def test_product_experience_phrase_guard_blocks_record_phrase_attractor():
    review = review_product_experience_phrase(
        title="周末收拾孩子的运动服时顺手记一下",
        body="周末收拾孩子的运动服时顺手记一下，最近她活动量明显变大。家里现在喝旺玥，钙铁锌和多种关键营养都在，看她跑跳状态不错。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v333_record_phrase_attractor_cleanup_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert "顺手记一下" in review.odd_phrase_hits
    assert "odd_product_experience_phrase" in review.reasons
    assert review.rewrite_required is True

    variant_review = review_product_experience_phrase(
        title="记一段用下来的小变化",
        body="后来给孩子选了旺玥，基础营养看着全，饭菜忽好忽坏时，日常营养安排起来不乱。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v333_record_phrase_attractor_cleanup_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert "记一段" in variant_review.odd_phrase_hits
    assert "odd_product_experience_phrase" in variant_review.reasons


def test_product_experience_phrase_guard_blocks_adult_sneaky_tasting_child_formula():
    review = review_product_experience_phrase(
        title="孩子喝了一口那个奶",
        body="我自己偷偷喝了一口，奶味不腥，难怪孩子没嫌弃。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "我自己偷偷喝了一口" in review.adult_self_drinking_hits
    assert "adult_self_drinking_child_formula" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_adult_leftover_tasting_child_formula():
    review = review_product_experience_phrase(
        title="旺玥喝到第三罐了，每次冲奶都偷喝她剩的一口底",
        body="也不是多好喝，就是看那阵奶沫消掉后留下的挂壁，觉得像把今天漏掉的钙和铁给她续上了。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "偷喝她剩的一口底" in review.adult_self_drinking_hits
    assert "adult_self_drinking_child_formula" in review.reasons
    assert "偷喝" not in sanitize_adult_self_drinking_phrases("每次冲奶都偷喝她剩的一口底。")


def test_product_experience_phrase_guard_blocks_child_self_brewing_formula():
    review = review_product_experience_phrase(
        title="今天继续记录旺玥",
        body="最近幼儿园里好几个小朋友请假，我家这个放学回来自己开罐旺玥泡一杯，咕咚咕咚喝完才出门。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert review.child_self_brewing_hits == ["自己开罐旺玥泡一杯"]
    assert "child_self_brewing_formula" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_child_daily_self_brewing_formula():
    review = review_product_experience_phrase(
        title="有在喝旺玥的吗",
        body="我家娃换了旺玥说好喝，现在每天自己冲，偶尔还会自己抱着罐子催我冲。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert review.child_self_brewing_hits == ["自己抱着罐子催我冲", "每天自己冲"]
    assert "child_self_brewing_formula" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_child_self_pouring_formula():
    review = review_product_experience_phrase(
        title="喝了一阵后回看",
        body="喝了旺玥一阵子，回看发现孩子每天自己倒奶粉还挺顺的。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "ugc_post_type": "轻复盘型",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "孩子每天自己倒奶粉" in review.child_self_brewing_hits
    assert "child_self_brewing_formula" in review.reasons
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_light_recap_as_question_post():
    review = review_product_experience_phrase(
        title="旺玥儿童奶粉",
        body="喝了一阵后回看，娃喝得还算顺，但我还在纠结要不要继续。有同样情况的妈妈吗？想听听大家怎么判断的。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "ugc_post_type": "轻复盘型",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "想听听大家" in review.ugc_post_type_drift_hits
    assert "有同样情况" in review.ugc_post_type_drift_hits
    assert "ugc_post_type_drift" in review.reasons
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_light_recap_question_title():
    review = review_product_experience_phrase(
        title="同龄娃怎么安排的",
        body="跟几个同龄妈妈聊完，发现每家安排都不一样。我家现在喝旺玥，先记一下自己观察，后面再看怎么调吧。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "ugc_post_type": "轻复盘型",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "怎么安排的" in review.ugc_post_type_drift_hits
    assert "ugc_post_type_drift" in review.reasons
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_light_recap_purchase_decision_drift():
    review = review_product_experience_phrase(
        title="当妈就是边走边看吧",
        body="旺玥喝了一阵，晚上那杯还算顺。我其实也拿不准，是不是该继续囤，还是再看别的。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "ugc_post_type": "轻复盘型",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "该继续囤" in review.ugc_post_type_drift_hits
    assert "再看别的" in review.ugc_post_type_drift_hits
    assert "ugc_post_type_drift" in review.reasons
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_light_recap_internal_type_leak():
    review = review_product_experience_phrase(
        title="一段轻复盘",
        body="同龄群聊完，自己默默整理了一下。这段时间旺玥喝着，日常安排也没被打乱。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "ugc_post_type": "轻复盘型",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "轻复盘" in review.ugc_post_type_drift_hits
    assert "ugc_post_type_drift" in review.reasons
    assert review.pass_ is False


def test_product_experience_ugc_post_type_cleanup_removes_internal_type_leak():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "ugc_post_type": "轻复盘型",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
        title="一段轻复盘",
        body="喝了一阵轻复盘。家里现在旺玥，每天两杯，一罐大概撑两周。普通日子先这么过着，后续再看情况调整",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    post_review = service._apply_ugc_post_type_drift_cleanup(item, review)

    assert "轻复盘" not in item.title
    assert "轻复盘" not in item.body
    assert post_review.pass_ is True


def test_product_experience_phrase_guard_blocks_child_routine_self_brewing_cup():
    review = review_product_experience_phrase(
        title="旺玥喝了一阵",
        body="之前给娃换奶粉那叫一个头疼。现在每天早晚自己冲一杯咕噜咕噜喝完，当妈的轻松不少。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert review.child_self_brewing_hits == ["现在每天早晚自己冲一杯"]
    assert "child_self_brewing_formula" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_child_daily_cup_self_brewing_order():
    body = "后来给旺玥加进日常，每天一杯自己冲，喝完舔杯子。量了下体重居然涨了快两斤。"
    review = review_product_experience_phrase(
        title="衣服短了一大截",
        body=body,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "每天一杯自己冲" in review.child_self_brewing_hits
    assert "child_self_brewing_formula" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False
    assert "自己冲" not in sanitize_baby_milk_action_phrases(body)


def test_product_experience_phrase_guard_blocks_child_self_initiated_brewing_action():
    review = review_product_experience_phrase(
        title="旺玥喝了一阵",
        body="最后换到旺玥，居然说好喝，天天自己主动去泡。喝了大半年，去年校服裤腿短了不少。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "天天自己主动去泡" in review.child_self_brewing_hits
    assert "child_self_brewing_formula" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_child_self_goes_to_brew():
    review = review_product_experience_phrase(
        title="娃最近放学回来",
        body="拆开旺玥包装，自己就去泡了，奶香味飘过来。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "正文40-130字。",
        },
    )

    assert "自己就去泡" in review.child_self_brewing_hits
    assert "child_self_brewing_formula" in review.reasons


def test_product_experience_phrase_guard_blocks_child_remembers_to_brew():
    review = review_product_experience_phrase(
        title="这罐还在喝",
        body="现在每天早晚自己记得泡，有时候还会催我。我说不出成分好不好，反正她愿意喝。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "正文40-130字。",
        },
    )

    assert "自己记得泡" in review.child_self_brewing_hits
    assert "child_self_brewing_formula" in review.reasons


def test_product_experience_phrase_guard_blocks_child_finished_brewing_wording():
    review = review_product_experience_phrase(
        title="户外回来那杯奶",
        body="娃冲完自己就干杯了，当妈的看着还挺省心。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "正文40-130字。",
        },
    )

    assert "娃冲完" in review.child_self_brewing_hits
    assert "child_self_brewing_formula" in review.reasons


def test_product_experience_phrase_guard_blocks_contextual_self_brew_formula():
    review = review_product_experience_phrase(
        title="喝完自己把杯子放水池了",
        body="每天放学回来自己冲杯奶粉，喝完顺手把杯子放水池了。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "正文40-130字。",
        },
    )

    assert "每天放学回来自己冲杯奶粉" in review.child_self_brewing_hits
    assert "child_self_brewing_formula" in review.reasons


def test_product_experience_phrase_guard_allows_child_holding_cup_to_drink():
    review = review_product_experience_phrase(
        title="杯子自己拿着",
        body="我冲好递过去，孩子自己拿着杯子喝完，放桌上就跑去玩了。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "正文40-130字。",
        },
    )

    assert review.child_self_brewing_hits == []
    assert "child_self_brewing_formula" not in review.reasons


def test_product_experience_phrase_guard_allows_child_fetching_cup_without_formula_operation():
    review = review_product_experience_phrase(
        title="杯子又被拿出来了",
        body="我冲好放桌上，孩子自己跑去拿杯子，喝完就去玩积木了。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "正文40-130字。",
        },
    )

    assert review.child_self_brewing_hits == []
    assert "自己跑去拿杯子" not in review.wangyue_article_logic_drift_hits
    assert "child_self_brewing_formula" not in review.reasons
    assert "wangyue_article_logic_drift_context" not in review.reasons


@pytest.mark.parametrize(
    ("body", "expected_hit"),
    [
        ("新罐到了拆开倒入密封盒，旺玥这段喝着还顺。", "倒入密封盒"),
        ("今天翻冰箱看到那盒奶粉，才想起来旺玥也要补。", "冰箱看到那盒奶粉"),
        ("怕营养跟不上，下午牛奶里加点旺玥，主要是钙铁锌。", "牛奶里加点旺玥"),
        ("每天除了饭菜，我会给他加一顿旺玥，钙铁锌也都带着。", "加一顿旺玥"),
        ("现在每天睡前他自己记得要喝，旺玥这罐接受度还行。", "每天睡前他自己记得要喝"),
        ("开罐时她凑过来看，我说这是你的，她乐呵呵抱走了。旺玥这阵喝着还顺。", "开罐时她凑过来看"),
    ],
)
def test_product_experience_phrase_guard_blocks_wangyue_formula_usage_form_errors(body, expected_hit):
    review = review_product_experience_phrase(
        title="随手记一下",
        body=body,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v155_title_rule_slim_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert "formula_usage_form_error" in review.reasons
    assert any(expected_hit in hit for hit in review.formula_usage_form_hits)


def test_product_experience_phrase_guard_allows_child_holding_cup_without_formula_usage_form_error():
    review = review_product_experience_phrase(
        title="杯子自己拿着",
        body="我冲好递过去，孩子自己拿着杯子喝完，放桌上就跑去玩了。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v155_title_rule_slim_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert review.formula_usage_form_hits == []
    assert "formula_usage_form_error" not in review.reasons
    assert review.child_self_brewing_hits == []
    assert "child_self_brewing_formula" not in review.reasons


@pytest.mark.parametrize(
    ("body", "expected_hit"),
    [
        ("换鞋放书包的功夫，我顺手把旺玥的杯子放桌上。", "旺玥的杯子"),
        ("早上赶时间，顺手把旺玥杯子挪到桌角。", "旺玥杯子"),
    ],
)
def test_product_experience_phrase_guard_blocks_wangyue_brand_as_cup_carrier(body, expected_hit):
    review = review_product_experience_phrase(
        title="随手记一下",
        body=body,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v155_title_rule_slim_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert "physical_action_carrier_mismatch" in review.reasons
    assert any(expected_hit in hit for hit in review.physical_action_carrier_mismatch_hits)
    assert "formula_usage_form_error" not in review.reasons


def test_product_experience_phrase_guard_blocks_wangyue_brand_as_handed_object():
    review = review_product_experience_phrase(
        title="饭菜忽好忽坏，后来选了它",
        body=(
            "刚收完玩具，小家伙又跑过来翻零食盒，"
            "我顺手把旺玥递过去，他接得很自然。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v334_record_replacement_cleanup_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert "physical_action_carrier_mismatch" in review.reasons
    assert "顺手把旺玥递过去" in review.physical_action_carrier_mismatch_hits

    natural_review = review_product_experience_phrase(
        title="冲好递过去",
        body="我冲好递过去，他接过杯子喝了几口，又跑去收拾玩具。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v334_record_replacement_cleanup_article_rules",
            "corpus": "0705旺玥活动",
        },
    )
    assert "physical_action_carrier_mismatch" not in natural_review.reasons
    assert natural_review.physical_action_carrier_mismatch_hits == []


def test_product_experience_phrase_guard_blocks_drink_bag_carrier_artifact():
    review = review_product_experience_phrase(
        title="她突然说画完了整幅画",
        body=(
            "今天接她放学时，有个妈妈看到我们喝东西的袋子问我是什么，"
            "我就顺口提了句家里喝的是旺玥。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v309_keyword_role_narrowing_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert "physical_action_carrier_mismatch" in review.reasons
    assert review.physical_action_carrier_mismatch_hits == ["喝东西的袋子"]
    assert _blocking_product_experience_phrase_hits(review) == ["喝东西的袋子"]


def test_sanitize_wangyue_formula_usage_form_deletes_bad_product_action_without_new_flow():
    body = "新罐到了拆开倒入密封盒，旺玥这段喝着还顺。"

    cleaned = sanitize_wangyue_formula_usage_form(body)

    assert "倒入密封盒" not in cleaned
    assert "冲" not in cleaned
    assert "睡前" not in cleaned
    assert "旺玥这段喝着还顺" in cleaned


def test_sanitize_wangyue_formula_usage_form_keeps_sentence_readable_after_daily_cup_cleanup():
    body = "陪娃拼图，刚坐下两分钟就要跑。家里清单上总有一项叫营养安排，现在旺玥每天一杯，钙铁锌和多种关键营养都配全了。"

    cleaned = sanitize_wangyue_formula_usage_form(body)

    assert "每天一杯" not in cleaned
    assert "现在旺玥" not in cleaned
    assert "现在喝旺玥" in cleaned
    assert "钙铁锌和多种关键营养都配全了" in cleaned


def test_sanitize_wangyue_time_event_context_keeps_sentence_readable():
    cleaned = sanitize_wangyue_time_event_context("别家孩子一换季就请假，我们家这阵状态还行。")

    assert "换季" not in cleaned
    assert "一平时" not in cleaned
    assert "一有状况就请假" in cleaned


def test_product_experience_phrase_guard_blocks_child_product_promo_context():
    review = review_product_experience_phrase(
        title="自己跟旁边的小孩说你也来一杯吧",
        body="那天我们在小区玩，旁边小朋友在喝奶，她突然跑过来跟人家说“我家也有，你要不要来一杯”。我才想起来旺玥是上个月买的。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "正文40-130字。",
        },
    )

    assert "wangyue_child_product_promo_context" in review.reasons
    assert any("要不要来一杯" in hit for hit in review.wangyue_child_product_promo_hits)
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_allows_child_says_tastes_ok():
    review = review_product_experience_phrase(
        title="这罐他倒是愿意喝",
        body="我冲好递过去，孩子说味道还行，自己拿着杯子喝了几口。旺玥这款我主要看保护力和日常营养。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "正文40-130字。",
        },
    )

    assert review.wangyue_child_product_promo_hits == []
    assert "wangyue_child_product_promo_context" not in review.reasons


def test_product_experience_phrase_guard_blocks_child_scooping_formula():
    review = review_product_experience_phrase(
        title="今天继续记录旺玥",
        body="每天早晚一杯旺玥，孩子自己倒水舀粉，我就在旁边看着，喝完还说今天甜一点。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert review.child_self_brewing_hits == ["孩子自己倒水舀粉"]
    assert "child_self_brewing_formula" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_child_spoon_scooping_formula():
    review = review_product_experience_phrase(
        title="今天继续记录旺玥",
        body="晚上回家后孩子自己拿勺子舀了三勺，说这杯今天要浓一点，我才发现这动作不太对。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "自己拿勺子舀了三勺" in review.child_self_brewing_hits
    assert "child_self_brewing_formula" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_child_self_digging_formula():
    review = review_product_experience_phrase(
        title="娃喝奶比吃饭积极",
        body="旺玥这罐是同事推荐的，现在每天自己挖奶粉，喝完还要舔杯沿。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "每天自己挖奶粉" in review.child_self_brewing_hits
    assert "child_self_brewing_formula" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_child_indirect_brewing_formula():
    review = review_product_experience_phrase(
        title="旺玥继续喝着",
        body="现在每天早晚自己搬小凳子冲奶，晚上他自己洗完澡就去厨房泡旺玥，我才发现这个动作不适合写。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "自己搬小凳子冲奶" in review.child_self_brewing_hits
    assert "自己洗完澡就去厨房泡旺玥" in review.child_self_brewing_hits
    assert "child_self_brewing_formula" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_child_formula_can_and_demand():
    review = review_product_experience_phrase(
        title="今天继续记录旺玥",
        body="早起穿校服，自己搬奶粉罐去了。他泡好端着，后来还自己抱着罐子让冲。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "自己搬奶粉罐去了" in review.child_self_brewing_hits
    assert "他泡好端着" in review.child_self_brewing_hits
    assert "自己抱着罐子让冲" in review.child_self_brewing_hits
    assert "child_self_brewing_formula" in review.reasons


def test_product_experience_phrase_guard_blocks_child_drinking_from_formula_can_context():
    review = review_product_experience_phrase(
        title="有点肉疼但还行",
        body="成分表里营养挺全乎，有保护力也有眼脑支持。打开罐子他自己抱着喝，肉疼是真肉疼。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "打开罐子他自己抱着喝" in review.child_self_brewing_hits
    assert "child_self_brewing_formula" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_ambiguous_self_brewing_fragment():
    review = review_product_experience_phrase(
        title="童童绿叶菜不太碰",
        body="挑食娃的妈，懂的都懂。打开新的一罐，自己泡上，我才发现这句不该出现。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "自己泡上" in review.child_self_brewing_hits
    assert "child_self_brewing_formula" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_child_holding_unspecified_drink_after_new_can():
    review = review_product_experience_phrase(
        title="开罐记录 皇家美素佳儿旺玥",
        body="新开一罐，娃自己抱着喝得挺欢。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "娃自己抱着喝" in review.child_self_brewing_hits
    assert "child_self_brewing_formula" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_child_extra_scoop_formula():
    review = review_product_experience_phrase(
        title="翻出奶粉罐的时候，是真的愣住了",
        body="她拧开盖子说那好吧，又自己偷偷多舀了一勺。希望是没错的吧，先喝着看。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "自己偷偷多舀了一勺" in review.child_self_brewing_hits
    assert "child_self_brewing_formula" in review.reasons


def test_product_experience_phrase_guard_blocks_child_dry_eating_formula():
    review = review_product_experience_phrase(
        title="我出门不用老盯着别的小朋友",
        body="每次开罐都得藏好，不然他能偷着干吃好几勺。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "偷着干吃好几勺" in review.child_self_brewing_hits
    assert "child_self_brewing_formula" in review.reasons
    cleaned = sanitize_baby_milk_action_phrases("去菜场回来发现娃把旺玥奶粉干吃了一勺。")
    assert "干吃" not in cleaned
    assert "孩子这阵喝奶还算顺" in cleaned


def test_product_experience_phrase_guard_blocks_child_formula_bottle_context():
    review = review_product_experience_phrase(
        title="给娃喝奶粉的日常小记录",
        body="早上冲奶时娃自己抱着奶瓶咕嘟咕嘟喝，我偷偷乐了一下，旺玥里的营养挺全的。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert review.child_formula_bottle_hits == ["抱着奶瓶"]
    assert "child_formula_bottle_context" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_baby_milk_action_cleanup_only_handles_bottle_context():
    bottle_text = "早上冲奶时娃自己抱着奶瓶咕嘟咕嘟喝，我偷偷乐了一下。"
    brew_text = "给娃挑旺玥的时候盯着成分看了半天。但看他每天主动去泡奶喝，我只能默默掏钱续上。"
    self_brew_text = "她早上自己冲一杯，两个月下来感觉精气神足了些。"
    scoop_text = "每天早晚一杯旺玥，孩子自己倒水舀粉，我就在旁边看着。"
    spoon_scoop_text = "晚上回家后孩子自己拿勺子舀了三勺，说这杯今天要浓一点。"
    indirect_brew_text = "现在每天早晚自己搬小凳子冲奶，晚上他自己洗完澡就去厨房泡旺玥。"
    can_brew_text = "早起穿校服，自己搬奶粉罐去了。他泡好端着，后来还自己抱着罐子让冲。"
    extra_scoop_text = "她拧开盖子说那好吧，又自己偷偷多舀了一勺。"
    model_rotation_text = "今天娃突然自己跑去柜子前，踮脚够奶粉罐，还抱着空罐子在地上滚。"
    model_rotation_text_2 = "每天早上自己搬凳子去够柜子上的罐子，娃自己会去冲。"
    model_rotation_text_3 = "每天早上自己跑去冲一杯，后来又主动去冲，最后自己抱着杯子要冲。"
    model_rotation_text_4 = "孩子拿着自己冲，我一回头还看到他自己抱着罐子看。"
    adult_text = "今晚陪娃写作业，给自己冲一杯热水。"
    cup_text = "冲好后娃自己抱着杯子咕嘟咕嘟喝，我偷偷乐了一下。"

    assert sanitize_baby_milk_action_phrases(bottle_text) == "早上冲奶时娃自己抱着杯子咕嘟咕嘟喝，我偷偷乐了一下"
    assert sanitize_baby_milk_action_phrases(brew_text) == brew_text.strip("。")
    assert sanitize_baby_milk_action_phrases(self_brew_text) == self_brew_text.strip("。")
    assert sanitize_baby_milk_action_phrases(scoop_text) == scoop_text.strip("。")
    assert sanitize_baby_milk_action_phrases(spoon_scoop_text) == spoon_scoop_text.strip("。")
    assert sanitize_baby_milk_action_phrases(indirect_brew_text) == indirect_brew_text.strip("。")
    assert sanitize_baby_milk_action_phrases(can_brew_text) == can_brew_text.strip("。")
    assert sanitize_baby_milk_action_phrases(extra_scoop_text) == extra_scoop_text.strip("。")
    assert sanitize_baby_milk_action_phrases(model_rotation_text) == model_rotation_text.strip("。")
    assert sanitize_baby_milk_action_phrases(model_rotation_text_2) == model_rotation_text_2.strip("。")
    assert sanitize_baby_milk_action_phrases(model_rotation_text_3) == model_rotation_text_3.strip("。")
    assert sanitize_baby_milk_action_phrases(model_rotation_text_4) == model_rotation_text_4.strip("。")
    assert sanitize_baby_milk_action_phrases(adult_text) == adult_text.strip("。")
    assert sanitize_baby_milk_action_phrases(cup_text) == cup_text.strip("。")
    assert sanitize_baby_milk_action_phrases("我女儿居然自己主动去泡奶了。") == "我女儿居然喝奶倒是主动了"
    assert sanitize_baby_milk_action_phrases("刚喝完一杯，自己又跑去倒了半杯。") == "刚喝完一杯，还想再喝半杯"
    assert sanitize_baby_milk_action_phrases("现在自己每天冲一杯。") == "现在每天等我冲一杯"
    assert sanitize_baby_milk_action_phrases("现在每天自己挖奶粉。") == "现在每天等我冲奶"
    assert sanitize_baby_milk_action_phrases("每天自己倒着喝。") == "每天喝得挺顺"
    assert sanitize_baby_milk_action_phrases("他每次自己倒来喝。") == "他每次等我倒好再喝"
    assert sanitize_baby_milk_action_phrases("早上自己捧着旺玥罐子叫妈妈开。") == "早上会提醒我冲奶"
    assert sanitize_baby_milk_action_phrases("每次泡奶她都自己端着小碗蹲旁边等，喝完把碗底舔干净。") == "每次泡奶她都自己端着杯子在旁边等，喝完把杯底喝干净"
    assert sanitize_common_ai_closure("小身体自然有劲。继续观察着，状态挺稳的。") == "小身体自然有劲。状态挺稳的"
    assert sanitize_common_ai_closure("钙铁锌和几种关键营养都在，后续再观察着看吧。") == "钙铁锌和几种关键营养都在"
    assert sanitize_odd_product_experience_phrases("冲一杯就搞定。") == "日常补充起来还算顺手"
    assert sanitize_odd_product_experience_phrases("皇家美素佳儿旺玥每天当补给。") == "皇家美素佳儿旺玥作为日常补充"
    assert sanitize_odd_product_experience_phrases("不用老想着今天是不是又缺了啥。") == "不用老想着今天是不是又营养没跟上"
    assert sanitize_odd_product_experience_phrases("成长阶段缺一点少一点，怕他体力跟不上。") == "成长阶段营养没跟上，怕他体力跟不上"
    assert sanitize_wangyue_context_phrases("出门恨不得把辅食机都塞包里。") == "有时会觉得营养安排挺琐碎"
    assert sanitize_wangyue_context_phrases("带娃出门前塞进背包的东西") == "带娃出门前的东西"
    assert sanitize_adult_self_drinking_phrases("我自己喝了一口，还行。") == "孩子喝着还行"
    assert sanitize_adult_self_drinking_phrases("我自己偷偷喝了一口。") == "孩子喝了一口"
    assert sanitize_adult_self_drinking_phrases("我先喝一口，不甜。") == "先递给孩子喝，不甜"
    assert sanitize_adult_self_drinking_phrases("泡了一杯自己先尝，甜味很淡。") == "冲好后先递给孩子喝，甜味很淡"
    assert sanitize_adult_self_drinking_phrases("我先偷喝了一口。") == "先递给孩子喝"
    assert sanitize_adult_self_drinking_phrases("我自己喝着也觉得还行。") == "孩子喝着还行"
    assert sanitize_adult_self_drinking_phrases("我自己尝了下，奶味不腥。") == "奶味不腥"


def test_product_experience_phrase_guard_blocks_wangyue_context_mistakes():
    review = review_product_experience_phrase(
        title="源悦真实体验分享",
        body="宝宝一岁多后出门多，我就在书包侧袋塞一盒贝博氏旺玥，临时兑点温水摇匀。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert review.wangyue_wrong_brand_hits == ["贝博氏旺玥", "源悦"]
    assert "宝宝一岁多" in review.wangyue_explicit_age_hits
    assert "书包侧袋" in review.wangyue_portable_form_hits
    assert "wangyue_wrong_brand" in review.reasons
    assert "wangyue_explicit_age_context" in review.reasons
    assert "wangyue_portable_form_context" in review.reasons


def test_product_experience_phrase_guard_allows_schoolbag_clothing_context():
    review = review_product_experience_phrase(
        title="接娃回来那点事",
        body="接娃回家路上，书包里外套换了好几件。儿童奶粉还是用的旺玥，主要当初选它就为保护力营养这块，暂时没打算换。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_painpoint_selling_posttype_matrix_v28_20260624",
            "post_type": "使用反馈/阶段观察",
            "product_appearance_mode": "旺玥作为当前安排出现",
        },
    )

    assert review.wangyue_portable_form_hits == []
    assert "wangyue_portable_form_context" not in review.reasons


def test_product_experience_phrase_guard_allows_schoolbag_side_pocket_non_product_detail():
    review = review_product_experience_phrase(
        title="接娃路上聊到请假",
        body="昨天接娃，旁边家长说班里又有人请假了。书包侧袋还塞着没吃完的饼干，旺玥就是家里日常喝的那罐，主要看保护力这块。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "正文40-130字。",
        },
    )

    assert review.wangyue_portable_form_hits == []
    assert "wangyue_portable_form_context" not in review.reasons


def test_product_experience_phrase_guard_blocks_schoolbag_side_pocket_product_detail():
    review = review_product_experience_phrase(
        title="接娃路上聊到请假",
        body="昨天接娃，旁边家长说班里又有人请假了。我顺手在书包侧袋塞了一盒旺玥，想着玩完兑点温水就能喝。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "正文40-130字。",
        },
    )

    assert any("书包侧袋" in hit for hit in review.wangyue_portable_form_hits)
    assert "wangyue_portable_form_context" in review.reasons


def test_product_experience_phrase_guard_blocks_wangyue_low_age_feeding_context():
    review = review_product_experience_phrase(
        title="旺玥记录",
        body="孩子从辅食到正餐一直挑食，我直接备了旺玥。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "辅食" in review.wangyue_explicit_age_hits
    assert "wangyue_explicit_age_context" in review.reasons


def test_product_experience_phrase_guard_blocks_wangyue_under_three_age_variants():
    cases = [
        ("一岁半的娃，饭桌跟战场似的，家里备着旺玥。", "一岁半"),
        ("我家2岁半孩子吃饭不稳，最近看了旺玥。", "2岁半"),
        ("不到三岁就开始喝旺玥，这段时间状态还行。", "不到三岁"),
        ("三岁前一直喝旺玥，后来继续留着。", "三岁前"),
        ("宝宝18个月断奶后，家里就备了旺玥。", "18个月"),
        ("十五个月断奶后，听朋友说旺玥不错。", "十五个月"),
    ]

    for body, expected in cases:
        review = review_product_experience_phrase(
            title="旺玥记录",
            body=body,
            plan={
                "rule_type": "business_rule",
                "asset_key": "wangyue_article_business_rules",
                "corpus": "旺玥是3周岁以上、3-6岁学龄前儿童语境下的4段儿童奶粉。",
            },
        )

        assert expected in review.wangyue_explicit_age_hits
        assert "wangyue_explicit_age_context" in review.reasons
        assert review.rewrite_required is True
        assert review.pass_ is False


def test_product_experience_phrase_guard_does_not_treat_usage_duration_as_under_three_age():
    review = review_product_experience_phrase(
        title="喝了一阵记录",
        body="孩子三岁后开始喝旺玥，喝了两个月，小身板看着结实了点。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "旺玥是3周岁以上、3-6岁学龄前儿童语境下的4段儿童奶粉。",
        },
    )

    assert review.wangyue_explicit_age_hits == []
    assert "wangyue_explicit_age_context" not in review.reasons


def test_product_experience_phrase_guard_blocks_wangyue_any_explicit_age():
    review = review_product_experience_phrase(
        title="七岁娃的奶粉罐",
        body="我家七岁娃活动量大，家里一直喝旺玥。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "七岁娃" in review.wangyue_explicit_age_hits
    assert "wangyue_explicit_age_context" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False
    assert "wangyue_explicit_age_context" in _semantic_wangyue_context_reasons(review)


def test_product_experience_phrase_guard_flags_complete_wangyue_stage_fact_as_unnatural_phrase():
    review = review_product_experience_phrase(
        title="3岁后选奶",
        body="娃一进3岁，我选奶思路变了。旺玥是3岁以上4段儿童奶粉，学龄前这段我会多看钙铁锌。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_selection_review_painpoints_v22_20260624",
            "post_type": "选奶/儿童奶粉选择复盘",
            "product_appearance_mode": "旺玥作为选择依据出现",
            "corpus": "旺玥事实必须正确：3周岁以上专用4段儿童奶粉，适配3-6岁学龄前儿童。",
        },
    )

    assert review.wangyue_explicit_age_hits == []
    assert "wangyue_explicit_age_context" not in review.reasons
    assert "3岁以上4段儿童奶粉" in review.wangyue_article_logic_drift_hits
    assert "wangyue_article_logic_drift_context" in review.reasons
    assert review.rewrite_required is True


def test_product_experience_phrase_guard_uses_explicit_selling_context_not_full_corpus():
    review = review_product_experience_phrase(
        title="儿童奶粉配方看晕了",
        body=(
            "娃到儿童阶段后，既要管日常营养又想着保护力，选奶粉真是翻来覆去对比。"
            "朋友推荐旺玥，我特意看了下配方，发现直接含乳铁蛋白，"
            "跑得多接触人多的时候，日常奶里带着这些就不用我再东拼西凑了。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v125_density_title_fact_tight_article_rules",
            "business_rule": {
                "topic": "V118-20｜保护力关注种草｜轻测评｜成长发育需求",
                "business_rule": "V118-20｜保护力关注种草｜轻测评｜成长发育需求",
                "selling_point": "乳铁蛋白/日常营养配置",
                "product_role": "旺玥是轻测评里被留下的选择",
                "product_appearance_mode": "成长阶段轻测评",
                "corpus": "全局边界：不要把保护力、眼脑、日常营养、阶段成长互相串用。",
            },
            "selling_point": "乳铁蛋白/日常营养配置",
            "product_role": "旺玥是轻测评里被留下的选择",
            "product_appearance_mode": "成长阶段轻测评",
        },
    )

    assert "眼脑营养缺失" not in review.wangyue_article_logic_drift_hits
    assert "wangyue_article_logic_drift_context" not in review.reasons


def test_product_experience_rewrite_input_mentions_wangyue_age_stage_context():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    plan = {
        "rule_type": "business_rule",
        "asset_key": "wangyue_repurchase_diversity_v21_20260623",
        "corpus": "写作规则：0705旺玥活动。复购/长期使用。",
    }
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json=plan,
        title="家里一直喝的",
        body="旺玥从一岁多就开始喝，后来也没怎么换。",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    payload = service._product_experience_phrase_rewrite_input(item, review)
    instructions = "\n".join(payload["rewrite_instructions"])

    assert "旺玥年龄/阶段不匹配" in instructions
    assert "产品年龄边界：旺玥只放在孩子3岁以后的儿童奶粉阶段" in instructions
    assert "正文不要完整复述成“3岁以上4段儿童奶粉”" in instructions
    assert "不要机械删年龄词" in instructions
    assert "不要把“一岁多/两岁/半岁”替换成“孩子/这个阶段”造成残句" in instructions
    assert "拆成“3岁+ / 4段 / 儿童奶粉 / 阶段对得上”" in instructions
    assert "不能写低龄、婴配、断奶、辅食、1-2岁开始喝旺玥" in instructions


def test_product_experience_rewrite_input_mentions_hidden_negative_comparison_context():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    plan = {
        "rule_type": "business_rule",
        "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
        "post_type": "选奶复盘",
        "ugc_post_type": "选奶复盘",
        "corpus": "写作规则：0705旺玥活动。旺玥要保持正面产品价值。",
    }
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json=plan,
        title="看他跟小伙伴玩回来",
        body=(
            "给他选四段奶粉那会儿，就是看中里头有乳铁蛋白。"
            "就是价格比普通牛奶粉贵点，但看他玩得开，就觉得这钱花得还算值。"
        ),
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    payload = service._product_experience_phrase_rewrite_input(item, review)
    instructions = "\n".join(payload["rewrite_instructions"])

    assert "旺玥隐性负面/降级比较" in instructions
    assert "删掉价格、预算、贵不贵、值不值和低配参照物框架" in instructions
    assert "保留旺玥的正向产品价值" in instructions
    assert "不要照抄本提示里的抽象词当正文" in instructions


def test_product_experience_phrase_guard_allows_wangyue_age_question_without_specific_age():
    review = review_product_experience_phrase(
        title="喝到几岁啊",
        body="家里一直喝旺玥，最近在纠结要不要继续。想问问大家一般喝到几岁，主要想听听同龄娃怎么安排。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "求问/轻复盘",
            "product_appearance_mode": "产品是明确讨论对象但不装日记",
        },
    )

    assert review.wangyue_explicit_age_hits == []
    assert "wangyue_explicit_age_context" not in review.reasons


def test_product_experience_phrase_guard_allows_wangyue_use_history_in_regular_article():
    review = review_product_experience_phrase(
        title="幼儿园接触多这事",
        body="幼儿园接触人多，我还是担心孩子容易中招。家里一直喝旺玥，主要看保护力这块，先按日常情况记一笔。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )

    assert "家里一直喝旺玥" not in review.wangyue_article_logic_drift_hits
    assert "wangyue_article_logic_drift_context" not in review.reasons


def test_product_experience_phrase_guard_blocks_wangyue_fixed_drinking_and_child_cup_operation():
    review = review_product_experience_phrase(
        title="又开一罐",
        body=(
            "刚拆开旺玥快递，娃每天早晚自己拿杯子要喝，"
            "那股子钙铁锌味她倒不挑。我顺手倒进密封罐里，省得受潮。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "post_type": "复购/长期使用",
            "product_appearance_mode": "旺玥作为长期保留、补货对象出现",
            "corpus": "0705旺玥活动",
        },
    )

    assert "每天早晚自己拿杯子要喝" in review.wangyue_article_logic_drift_hits
    assert "钙铁锌味" in review.wangyue_article_logic_drift_hits
    assert "倒进密封罐" in review.wangyue_article_logic_drift_hits
    assert "wangyue_article_logic_drift_context" in review.reasons
    assert "child_self_brewing_formula" not in review.reasons


def test_product_experience_phrase_guard_blocks_wangyue_staged_drinking_variants():
    review = review_product_experience_phrase(
        title="又开一罐",
        body=(
            "旺玥这罐家里还留着。他每回都喝光，自己颠颠跑去拿杯子，"
            "喝完还舔杯口。昨晚又抱着空罐子啃，我才想起来要补货。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "post_type": "复购/长期使用",
            "product_appearance_mode": "旺玥作为长期保留、补货对象出现",
            "corpus": "0705旺玥活动",
        },
    )

    assert "每回都喝光" in review.wangyue_article_logic_drift_hits
    assert "自己颠颠跑去拿杯子" not in review.wangyue_article_logic_drift_hits
    assert "舔杯口" in review.wangyue_article_logic_drift_hits
    assert "抱着空罐子啃" in review.wangyue_article_logic_drift_hits
    assert any("抱着空罐子啃" in hit for hit in review.child_self_brewing_hits)
    assert "wangyue_article_logic_drift_context" in review.reasons
    assert "child_self_brewing_formula" in review.reasons


def test_product_experience_phrase_guard_allows_wangyue_repurchase_use_history():
    review = review_product_experience_phrase(
        title="被提醒了下一罐",
        body="孩子爸突然问我旺玥那罐是不是快喝完了，下一罐买了没。我才想起这事，这奶粉娃一直喝着，家里人都习惯了，赶紧补上，免得断档。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_repurchase_diversity_v21_20260623",
            "post_type": "复购/补货记录",
            "ugc_post_type": "家人提醒补货型",
            "product_appearance_mode": "旺玥作为被家里人一句话提醒后要补上的奶粉出现",
        },
    )

    assert "一直喝着" not in review.odd_phrase_hits
    assert "odd_product_experience_phrase" not in review.reasons
    assert review.pass_ is True


def test_product_experience_phrase_guard_allows_wangyue_repurchase_stocking_relation():
    review = review_product_experience_phrase(
        title="顺手补一罐",
        body="买湿巾的时候顺手把旺玥也加上了，家里一直备着这个。孩子喝习惯了，家里备着旺玥也省得临时想起来再补。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_repurchase_diversity_v21_20260623",
            "post_type": "复购/补货记录",
            "ugc_post_type": "顺手加购补货型",
            "product_appearance_mode": "旺玥作为买其他日用品时顺手补上的奶粉出现",
        },
    )

    assert "一直备着" not in review.odd_phrase_hits
    assert "家里备着旺玥" not in review.odd_phrase_hits
    assert "odd_product_experience_phrase" not in review.reasons
    assert review.pass_ is True


def test_product_experience_phrase_guard_blocks_scene_bucket_drift_to_cabinet():
    review = review_product_experience_phrase(
        title="快递开箱",
        body="门口堆了三个快递，拆开一看有一罐旺玥。顺手把包装袋压扁，罐子放进厨房柜子。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "补货/家务清单",
            "product_appearance_mode": "产品是家里库存物件",
            "scene_motive_bucket": "快递到货拆箱",
        },
    )

    assert "厨房柜子" in review.scene_motive_drift_hits
    assert "scene_motive_drift" in review.reasons
    assert review.rewrite_required is True


def test_product_experience_phrase_guard_blocks_usage_record_action_surface_drift():
    review = review_product_experience_phrase(
        title="早上赶时间",
        body="早上赶着出门，桌上那杯旺玥他自己端起来喝了几口，我在旁边翻袜子。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "使用记录",
            "product_appearance_mode": "产品是日常动作的一部分",
            "product_action_surface": "物件在场",
            "scene_motive_bucket": "早上赶时间",
        },
    )

    assert "喝了几口" in review.product_action_surface_hits
    assert "product_action_surface_drift" in review.reasons


def test_product_experience_phrase_guard_blocks_planned_drinking_for_object_presence_surface():
    review = review_product_experience_phrase(
        title="又磨蹭了",
        body="周末早上桌上那杯旺玥放着，我喊他喝，他说等一下。出门前把罐子挪到包边，怕他路上想起来要喝又找不到。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "使用记录",
            "product_appearance_mode": "产品是日常动作的一部分",
            "product_action_surface": "物件在场",
            "scene_motive_bucket": "周末在家磨蹭",
            "life_trigger": "在家磨蹭",
        },
    )

    assert "喊他喝" in review.product_action_surface_hits
    assert "想起来要喝" in review.product_action_surface_hits
    assert "product_action_surface_drift" in review.reasons


def test_product_experience_phrase_guard_blocks_malformed_action_cleanup_residue():
    review = review_product_experience_phrase(
        title="沙发边上",
        body="沙发上有昨天没看了一眼的牛奶盒，桌角还放着那杯旺玥。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "使用记录",
            "product_appearance_mode": "产品是日常动作的一部分",
            "product_action_surface": "物件在场",
            "scene_motive_bucket": "早上赶时间",
        },
    )

    assert "没看了一眼" in review.malformed_fragment_hits
    assert "malformed_fragment" in review.reasons


def test_product_experience_phrase_guard_blocks_malformed_child_stage_fragment():
    review = review_product_experience_phrase(
        title="睡前奶怎么安排",
        body="娃快孩子了，娃快孩子，娃刚满孩子，孩子半娃，娃快这个阶段了。家里喝旺玥，我也拿不准。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "求问/轻复盘",
            "product_appearance_mode": "产品是明确讨论对象但不装日记",
        },
    )

    assert "娃快孩子了" in review.malformed_fragment_hits
    assert "娃快孩子" in review.malformed_fragment_hits
    assert "娃刚满孩子" in review.malformed_fragment_hits
    assert "孩子半娃" in review.malformed_fragment_hits
    assert "娃快这个阶段了" in review.malformed_fragment_hits
    assert "malformed_fragment" in review.reasons


def test_product_experience_phrase_guard_blocks_truncated_tail_fragment():
    review = review_product_experience_phrase(
        title="我默默注意了下作息和状态",
        body="虽说没少折腾，但也没乱换东西。儿童奶粉这块还是沿用旺玥，主要当时看中的是保护力营养这块，暂时",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_painpoint_selling_posttype_matrix_v28_20260624",
            "post_type": "使用反馈/阶段观察",
            "product_appearance_mode": "旺玥作为当前安排出现",
        },
    )

    assert "尾部残句：暂时" in review.malformed_fragment_hits
    assert "malformed_fragment" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


@pytest.mark.parametrize(
    ("title", "body", "expected_hit"),
    [
        (
            "放学后还要玩一会儿",
            "后来别人一问才发现家里挺旺玥，钙铁锌这些关键营养配得全。",
            "家里挺旺玥",
        ),
        (
            "完营养终于不愁了",
            "后来被朋友安利了旺玥，基础营养看着挺全的，现在，日常营养安排起来不乱。",
            "完营养",
        ),
        (
            "回家路上娃说个不停",
            "后来和小区妈妈们聊了聊，选了旺玥。钙铁锌和多种关键营养都挺全，他倒不抗拒，得挺利索。",
            "得挺利索",
        ),
        (
            "选奶粉？我不较真，旺玥就行",
            "娃3岁后一直喝旺玥，奶香淡淡的，他不太挑，得挺顺。钙铁锌和多种关键营养都配全了。",
            "得挺顺",
        ),
        (
            "活动完状态稳住了",
            "我在旁边看着，忽然想到家里一直喝旺玥。也不是刻意去对比，就是着，他活动完的状态稳得住。",
            "就是着",
        ),
        (
            "不怎么容易跟着时候小变化闹腾",
            "看他每次出去玩回来都能稳住状态，不怎么容易跟着时候小变化闹腾，我就知道这个选择挺适合他。",
            "跟着时候",
        ),
        (
            "不怎么容易跟着时候小变化闹腾",
            "看他每次出去玩回来都能稳住状态，不怎么容易跟着时候小变化闹腾，我就知道这个选择挺适合他。",
            "时候小变化",
        ),
    ],
)
def test_product_experience_phrase_guard_blocks_post_rewrite_residue_fragments(title, body, expected_hit):
    review = review_product_experience_phrase(
        title=title,
        body=body,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v309_keyword_role_narrowing_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert expected_hit in review.malformed_fragment_hits
    assert "malformed_fragment" in review.reasons
    assert expected_hit in _blocking_product_experience_phrase_hits(review)


def test_product_experience_phrase_guard_blocks_json_field_residue():
    review = review_product_experience_phrase(
        title="{",
        body='\"title\": \"接娃时被问\", \"body\": \"最近接娃放学，同学妈妈问我家怎么安排的呀\"',
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "post_type": "使用反馈",
            "corpus": "0705旺玥活动",
        },
    )

    assert "JSON字段残留" in review.malformed_fragment_hits
    assert "malformed_fragment" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_unevidenced_wangyue_relation_drift():
    review = review_product_experience_phrase(
        title="新开一听，记录下",
        body=(
            "娃收拾书包，顺手放了一罐新开的旺玥，算是个小陪伴。"
            "学校也能喝。朋友提过皇家旺玥，一个月两罐半，家里还剩大半罐。"
            "身边同龄娃很多都在喝4段，别人家孩子喝4段的也长挺好。"
            "上周到的还没怎么动，带娃出门总得带点东西，这罐就当桌面物件。"
            "我家现在喝皇家旺玥。之前那罐空了好一阵。"
            "一个说配方侧重成长，一个说分段更细致。"
            "放回常用位置，皇家旺玥配方有点不一样。"
            "另一个说分段更细，更适合日常搭配。"
            "两个配方看着都行，但总觉得有点不一样。"
            "家里一直喝皇家旺玥，旺玥这月开销又得记上，算了，孩子要喝，家里耗材就属它最贵，没办法，该买还是得买，掏钱挺爽快。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "使用记录",
            "product_appearance_mode": "产品是新开一听/阶段记录里的低浓度在场",
        },
    )

    assert "wangyue_article_logic_drift_context" in review.reasons
    assert "小陪伴" in review.wangyue_article_logic_drift_hits
    assert "学校也能喝" in review.wangyue_article_logic_drift_hits
    assert "朋友提过" in review.wangyue_article_logic_drift_hits
    assert "两罐半" in review.wangyue_article_logic_drift_hits
    assert "还剩大半罐" in review.wangyue_article_logic_drift_hits
    assert "身边同龄娃" in review.wangyue_article_logic_drift_hits
    assert "很多都在喝4段" in review.wangyue_article_logic_drift_hits
    assert "别人家孩子喝4段" in review.wangyue_article_logic_drift_hits
    assert "长挺好" in review.wangyue_article_logic_drift_hits
    assert "上周到的" in review.wangyue_article_logic_drift_hits
    assert "还没怎么动" in review.wangyue_article_logic_drift_hits
    assert "带娃出门总得带点东西" in review.wangyue_article_logic_drift_hits
    assert "桌面物件" in review.wangyue_article_logic_drift_hits
    assert "之前那罐空了" in review.wangyue_article_logic_drift_hits
    assert "空了好一阵" in review.wangyue_article_logic_drift_hits
    assert "配方侧重成长" in review.wangyue_article_logic_drift_hits
    assert "分段更细致" in review.wangyue_article_logic_drift_hits
    assert "常用位置" in review.wangyue_article_logic_drift_hits
    assert "配方有点不一样" in review.wangyue_article_logic_drift_hits
    assert "两个配方" in review.wangyue_article_logic_drift_hits
    assert "都行" in review.wangyue_article_logic_drift_hits
    assert "更适合日常搭配" in review.wangyue_article_logic_drift_hits
    assert "家里一直喝皇家旺玥" not in review.wangyue_article_logic_drift_hits
    assert "孩子要喝" in review.wangyue_article_logic_drift_hits
    assert "该买还是得买" in review.wangyue_article_logic_drift_hits
    assert "就属它最贵" in review.wangyue_article_logic_drift_hits
    assert "掏钱挺爽快" in review.wangyue_article_logic_drift_hits


def test_product_experience_phrase_guard_allows_stronger_wangyue_story_when_post_type_supports_it():
    review = review_product_experience_phrase(
        title="这次还是继续",
        body=(
            "家里一直喝皇家旺玥，孩子要喝的时候也不太费劲。"
            "对比时也纠结过两个配方，最后还是觉得日常搭配方便一点。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "复购/长期使用反馈",
            "ugc_post_type": "复购/长期喝",
            "product_appearance_mode": "产品履历和产品关系可以成为主线",
            "product_role": "家庭固定使用对象",
        },
    )

    assert "家里一直喝皇家旺玥" not in review.wangyue_article_logic_drift_hits
    assert "孩子要喝" not in review.wangyue_article_logic_drift_hits
    assert "两个配方" not in review.wangyue_article_logic_drift_hits
    assert "日常搭配" not in review.wangyue_article_logic_drift_hits
    assert "wangyue_article_logic_drift_context" not in review.reasons


def test_product_experience_phrase_guard_blocks_wangyue_digestive_effect_even_in_seeded_story():
    review = review_product_experience_phrase(
        title="预算还是没省下来",
        body="换回旺玥后，肚子不适应哭闹少了，半夜翻来翻去也少了，大便也规律了，所以这钱还是继续花。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "预算取舍",
            "ugc_post_type": "预算吐槽/取舍分享型",
            "product_appearance_mode": "产品是家庭开销和取舍对象",
        },
    )

    assert "wangyue_digestive_effect_context" in review.reasons
    assert "肚子不适应" in review.wangyue_digestive_effect_hits
    assert "哭闹" in review.wangyue_digestive_effect_hits
    assert "半夜翻来翻去" in review.wangyue_digestive_effect_hits
    assert "大便也规律" in review.wangyue_digestive_effect_hits


def test_product_experience_phrase_guard_allows_full_drinking_action_surface():
    review = review_product_experience_phrase(
        title="早上那杯",
        body="早上赶着出门，桌上那杯旺玥他自己端起来喝了几口，我在旁边翻袜子。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "使用记录",
            "product_appearance_mode": "产品是日常动作的一部分",
            "product_action_surface": "完整喝奶动作",
            "scene_motive_bucket": "早上赶时间",
        },
    )

    assert review.product_action_surface_hits == []
    assert "product_action_surface_drift" not in review.reasons


def test_product_experience_phrase_guard_allows_animation_background_for_usage_record_surface():
    review = review_product_experience_phrase(
        title="磨蹭半天",
        body="我在地垫上收拾玩具，桌角放着那杯旺玥。他趴着看动画片，喊了两声没动。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "使用记录",
            "product_appearance_mode": "产品是日常动作的一部分",
            "product_action_surface": "物件在场",
            "scene_motive_bucket": "周末在家磨蹭",
        },
    )

    assert "动画片" not in review.wangyue_article_logic_drift_hits
    assert "wangyue_article_logic_drift_context" not in review.reasons


def test_product_experience_phrase_guard_allows_planned_weekend_usage_record_context():
    review = review_product_experience_phrase(
        title="又乱了一早上",
        body="周末早上想多赖会儿，顺手把桌上那杯旺玥挪到柜子边。电视开着，杯子就一直搁那儿没动。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "使用记录",
            "product_appearance_mode": "产品是日常动作的一部分",
            "product_action_surface": "物件在场",
            "scene_motive_bucket": "周末在家磨蹭",
            "life_trigger": "在家磨蹭",
        },
    )

    assert "周末" not in review.wangyue_time_event_context_hits
    assert "wangyue_time_event_context" not in review.reasons


def test_product_experience_phrase_guard_allows_weekend_supermarket_restock_context():
    review = review_product_experience_phrase(
        title="补货清单",
        body="周末去超市顺手补了几样刚需：湿巾、早餐面包，还有旺玥。结账时才发现这个月又超预算了。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "补货/家务清单",
            "product_appearance_mode": "产品是家里库存物件",
            "ugc_post_type": "复购/囤货型",
            "scene_motive_bucket": "超市顺手补刚需",
            "life_trigger": "顺路买刚需",
        },
    )

    assert "周末" not in review.wangyue_time_event_context_hits
    assert "wangyue_time_event_context" not in review.reasons


def test_product_experience_phrase_guard_allows_adult_tea_background_for_usage_record_surface():
    review = review_product_experience_phrase(
        title="玄关旁边的罐子",
        body="放学回来外套校服扔一地，我顺手把旺玥罐子搁桌上。他去翻作业袋，我就在那泡了杯茶。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "使用记录",
            "product_appearance_mode": "产品是日常动作的一部分",
            "product_action_surface": "物件在场",
            "scene_motive_bucket": "放学回家玄关旁",
        },
    )

    assert "泡了杯" not in review.wangyue_article_logic_drift_hits
    assert "wangyue_article_logic_drift_context" not in review.reasons


def test_product_experience_phrase_guard_blocks_scene_bucket_drift_to_empty_inventory():
    review = review_product_experience_phrase(
        title="超市顺手补刚需",
        body="超市顺手拎了袋旺玥回来，这款儿童奶粉见底好几天了，旁边还有半罐没喝完的，另一罐也快空了。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "补货/家务清单",
            "product_appearance_mode": "产品是家里库存物件",
            "scene_motive_bucket": "超市顺手补刚需",
        },
    )

    assert "见底" in review.scene_motive_drift_hits
    assert "半罐" in review.scene_motive_drift_hits
    assert "快空了" in review.scene_motive_drift_hits
    assert "scene_motive_drift" in review.reasons


def test_product_experience_phrase_guard_allows_inventory_bucket_cabinet():
    review = review_product_experience_phrase(
        title="盘一下库存",
        body="晚上翻柜子，旺玥还剩一罐，湿巾只剩两包，顺手记到手机里。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "补货/家务清单",
            "product_appearance_mode": "产品是家里库存物件",
            "scene_motive_bucket": "库存盘点",
        },
    )

    assert review.scene_motive_drift_hits == []
    assert "scene_motive_drift" not in review.reasons


def test_product_experience_phrase_guard_does_not_apply_old_row2_guard_to_product_permission_row2():
    review = review_product_experience_phrase(
        title="盘一下库存",
        body="晚上翻柜子找东西，发现旺玥只剩半罐了，顺手加到手机备忘录里。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "source_row_no": 2,
            "post_type": "补货/家务清单",
            "product_appearance_mode": "产品是家里库存物件",
            "scene_motive_bucket": "库存盘点",
        },
    )

    assert review.wangyue_row2_drinking_action_hits == []
    assert "wangyue_row2_drinking_action_context" not in review.reasons


def test_product_experience_phrase_guard_blocks_wangyue_portable_stick_pack():
    review = review_product_experience_phrase(
        title="旺玥真实体验分享",
        body="清早往书包侧兜塞旺玥小条装，放学回来书包一倒，干掉了三根，说课间喝着香。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "旺玥小条装" in review.wangyue_portable_form_hits
    assert "三根" in review.wangyue_portable_form_hits
    assert "wangyue_portable_form_context" in review.reasons


def test_product_experience_phrase_guard_blocks_wangyue_portable_pack():
    review = review_product_experience_phrase(
        title="娃爱喝的儿童奶粉真的不用瞎找",
        body="平时出门揣两袋便携装也特方便，旺玥喝着还挺顺。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "便携装" in review.wangyue_portable_form_hits
    assert "wangyue_portable_form_context" in review.reasons


def test_product_experience_phrase_guard_blocks_wangyue_backpack_title():
    review = review_product_experience_phrase(
        title="带娃出门前塞进背包的东西",
        body="旺玥这罐其实没多想，就是娃营养得跟上才备的。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "塞进背包" in review.wangyue_portable_form_hits
    assert "wangyue_portable_form_context" in review.reasons
    body_review = review_product_experience_phrase(
        title="接孩子时看别人家书包有奶",
        body="接孩子时看别人家书包有奶，才意识到活动量大。家里备着皇家美素佳儿旺玥当营养补充。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 4,
            "corpus": "写作规则：围绕孩子成长阶段日常营养别落下这件事写。",
        },
    )
    assert "书包有奶" in body_review.wangyue_portable_form_hits


def test_product_experience_phrase_guard_blocks_wangyue_portable_powder_pack_scene():
    review = review_product_experience_phrase(
        title="带娃出门的随身口粮我锁死了",
        body="收拾他外出随身包，总习惯塞两条旺玥儿童奶粉条分装，跑跳疯玩大半天掏出来兑温水就能喝。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "分装" in review.wangyue_portable_form_hits
    assert "外出随身包" in review.wangyue_portable_form_hits
    assert "奶粉条" in review.wangyue_portable_form_hits
    assert "兑温水" in review.wangyue_portable_form_hits
    assert "wangyue_portable_form_context" in review.reasons


def test_product_experience_phrase_guard_blocks_wangyue_bag_and_ready_drink_context():
    review = review_product_experience_phrase(
        title="带孩子出门的包里都装了什么",
        body="包里除了水杯纸巾，还塞了旺玥，孩子回来每天两杯当水喝。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "包里除了水杯纸巾" in review.wangyue_portable_form_hits
    assert "塞了旺玥" in review.wangyue_portable_form_hits
    assert "当水喝" in review.wangyue_portable_form_hits
    assert "wangyue_portable_form_context" in review.reasons


def test_product_experience_phrase_guard_blocks_wangyue_thermos_and_flowerbed_drinking_context():
    body = "保温杯里装了旺玥，玩累了坐花坛边喝完又跑走了。"
    review = review_product_experience_phrase(
        title="今天居然没手忙脚乱",
        body=body,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "保温杯里装了旺玥" in review.wangyue_portable_form_hits
    assert "玩累了坐花坛边喝完" in review.wangyue_portable_form_hits
    assert "wangyue_portable_form_context" in review.reasons
    cleaned = sanitize_wangyue_context_phrases(body)
    assert "保温杯里装了旺玥" not in cleaned
    assert "坐花坛边喝完" not in cleaned


def test_product_experience_phrase_guard_blocks_wangyue_formula_can_in_outing_bag():
    review = review_product_experience_phrase(
        title="带娃出门，我偷偷多带了一样东西",
        body="现在出门包里会多放一罐奶粉，喝完就安心点。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "出门包里会多放一罐奶粉" in review.wangyue_portable_form_hits
    assert "wangyue_portable_form_context" in review.reasons


def test_product_experience_phrase_guard_blocks_wangyue_seen_in_bag_relation():
    review = review_product_experience_phrase(
        title="接娃翻包，旺玥在呢",
        body="等娃放学的十几分钟，我翻了翻包。看到旺玥，想起她最近喝得还行。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert any("翻了翻包" in hit for hit in review.wangyue_portable_form_hits)
    assert "wangyue_portable_form_context" in review.reasons


def test_product_experience_phrase_guard_allows_bag_detail_without_product_carrier_relation():
    review = review_product_experience_phrase(
        title="接娃路上顺手记一下",
        body="包里都是纸巾和水杯，翻了半天才找到钥匙。家里旺玥还在喝，日常营养这块我没太操心。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert review.wangyue_portable_form_hits == []
    assert "wangyue_portable_form_context" not in review.reasons


def test_product_experience_phrase_guard_blocks_wangyue_supplement_replacement():
    review = review_product_experience_phrase(
        title="被问儿童奶粉怎么选",
        body="家里喝了好一阵旺玥，钙铁锌这些配得比较全，日常不用再额外捣鼓营养片，省心。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "不用再额外捣鼓营养片" in review.wangyue_supplement_replacement_hits
    assert "wangyue_supplement_replacement_context" in review.reasons


def test_product_experience_phrase_guard_allows_non_supplement_nutrition_plain_speech():
    review = review_product_experience_phrase(
        title="饭菜乱，营养不乱",
        body="后来给娃喝了旺玥，基础营养看着全，哪怕饭桌上随意了，也不用东补西补。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert review.wangyue_supplement_replacement_hits == []
    assert "wangyue_supplement_replacement_context" not in review.reasons


def test_product_experience_phrase_guard_blocks_wangyue_outing_bag_and_got_it_done():
    review = review_product_experience_phrase(
        title="带娃出门终于能轻便点了",
        body="以前总怕孩子营养跟不上，出门恨不得把辅食机都塞包里。现在备了皇家美素佳儿旺玥，冲一杯就搞定日常营养补充，小家伙自己抱着杯子喝得挺开心。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "辅食机都塞包里" in review.wangyue_portable_form_hits
    assert "冲一杯就搞定" in review.odd_phrase_hits
    assert "wangyue_portable_form_context" in review.reasons
    assert "odd_product_experience_phrase" in review.reasons
    assert "child_self_brewing_formula" not in review.reasons


def test_product_experience_phrase_guard_blocks_wangyue_ready_to_drink_title():
    review = review_product_experience_phrase(
        title="又是开盖即饮的日常啊",
        body="家里每天一杯旺玥，孩子喝着还行。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "开盖即饮" in review.wangyue_portable_form_hits
    assert "wangyue_portable_form_context" in review.reasons


def test_product_experience_phrase_guard_blocks_wangyue_digestive_effect_context():
    review = review_product_experience_phrase(
        title="这罐喝着还顺",
        body="旺玥喝了快两周，孩子肚子软软的，便便也规律了，小肚子看着舒服。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "肚子软软的" in review.wangyue_digestive_effect_hits
    assert "便便也规律" in review.wangyue_digestive_effect_hits
    assert "小肚子" in review.wangyue_digestive_effect_hits
    assert "wangyue_digestive_effect_context" in review.reasons


def test_product_experience_wangyue_context_cleanup_is_narrow():
    title = "源悦真实体验分享"
    body = "宝宝一岁多后出门多，我就在书包侧袋塞一盒旺玥，临时兑点温水摇匀。"

    assert sanitize_wangyue_context_phrases(title) == "旺玥真实体验分享"
    cleaned = sanitize_wangyue_context_phrases(body)
    assert "源悦" not in cleaned
    assert "一岁多" in cleaned
    assert "书包侧袋" not in cleaned
    assert "一盒旺玥" not in cleaned
    assert "兑点温水摇匀" not in cleaned
    assert "家里喝旺玥" not in cleaned
    portable_cleaned = sanitize_wangyue_context_phrases("清早往书包侧兜塞旺玥小条装，放学回来干掉了三根。")
    assert "小条装" not in portable_cleaned
    assert "三根" not in portable_cleaned
    assert "便携装" not in sanitize_wangyue_context_phrases("出门带便携装。")
    portable_pack_cleaned = sanitize_wangyue_context_phrases("收拾他出门背的小双肩包总习惯塞两条旺玥儿童奶粉分装，掏出来兑温水就能喝。")
    assert "小双肩包" not in portable_pack_cleaned
    assert "两条" not in portable_pack_cleaned
    assert "分装" not in portable_pack_cleaned
    assert "兑温水" not in portable_pack_cleaned
    portable_pack_cleaned_2 = sanitize_wangyue_context_phrases("收拾外出随身包，塞一杯旺玥的奶粉条。")
    assert "随身包" not in portable_pack_cleaned_2
    assert "奶粉条" not in portable_pack_cleaned_2
    latest_cleaned = sanitize_wangyue_context_phrases("包里除了水杯纸巾，还塞了旺玥，孩子回来每天两杯当水喝。")
    assert "包里除了水杯纸巾" not in latest_cleaned
    assert "塞了旺玥" not in latest_cleaned
    assert "当水喝" not in latest_cleaned
    assert "照常喝" not in latest_cleaned
    assert "每天两杯" not in latest_cleaned
    assert "家里那款" not in latest_cleaned
    water_milk_cleaned = sanitize_wangyue_context_phrases("现在每天当水奶喝着，我也说不清具体哪里好。")
    assert "水奶" not in water_milk_cleaned
    assert "照常喝着" not in water_milk_cleaned
    water_like_cleaned = sanitize_wangyue_context_phrases("孩子当顺手的水喝下去就行。")
    assert "当顺手的水喝" not in water_like_cleaned
    assert "照常喝下去" not in water_like_cleaned
    outing_can_cleaned = sanitize_wangyue_context_phrases("现在出门包里会多放一罐奶粉，喝完就安心点。")
    assert "出门包里" not in outing_can_cleaned
    assert "多放一罐奶粉" not in outing_can_cleaned
    forgot_can_cleaned = sanitize_wangyue_context_phrases("出门太急忘了带旺玥，回来再喝。")
    assert "忘了带旺玥" not in forgot_can_cleaned
    assert "带旺玥" not in forgot_can_cleaned
    assert "漏了点小事" in forgot_can_cleaned
    table_cleaned = sanitize_wangyue_context_phrases("这罐旺玥我搁在茶几上，他路过就喝几口。")
    assert "搁在茶几上" not in table_cleaned
    assert "路过就喝几口" not in table_cleaned
    assert "放在家里" not in table_cleaned
    assert "喝着还算顺" not in table_cleaned
    bag_cleaned = sanitize_wangyue_context_phrases("带娃出门，包里一定会塞一袋旺玥。")
    assert "包里一定会塞" not in bag_cleaned
    assert "一袋旺玥" not in bag_cleaned
    assert "家里一直喝旺玥" not in bag_cleaned
    assert "家里那款" not in bag_cleaned
    snack_bag_cleaned = sanitize_wangyue_context_phrases("包里除了水杯零食，我还会放一包皇家美素佳儿旺玥，出门前塞几包在包里，随时能泡。")
    assert "包里除了水杯零食" not in snack_bag_cleaned
    assert "一包皇家美素佳儿旺玥" not in snack_bag_cleaned
    assert "塞几包" not in snack_bag_cleaned
    assert "随时能泡" not in snack_bag_cleaned
    assert "皇家美素佳儿旺玥" in snack_bag_cleaned
    assert "家里那款" not in snack_bag_cleaned
    schoolbag_cleaned = sanitize_wangyue_context_phrases("早上急急忙忙出门，塞一罐旺玥到书包里，娃自己路上喝掉。")
    assert "书包" not in schoolbag_cleaned
    assert "路上喝" not in schoolbag_cleaned
    assert "家里喝旺玥" not in schoolbag_cleaned
    assert "家里那款" not in schoolbag_cleaned
    can_cleaned = sanitize_wangyue_context_phrases("他抱着罐子闻了又闻，喝得咂嘴。")
    assert "抱着罐子" not in can_cleaned
    assert "看着罐子" in can_cleaned
    powder_bag_cleaned = sanitize_wangyue_context_phrases("这小包还挺能装，倒进奶粉袋，出门玩一天带两小包冲奶刚好。")
    assert "小包" not in powder_bag_cleaned
    assert "奶粉袋" not in powder_bag_cleaned
    assert "带两小包" not in powder_bag_cleaned
    ready_drink_cleaned = sanitize_wangyue_context_phrases("又是开盖即饮的日常啊")
    assert "即饮" not in ready_drink_cleaned
    assert "日常喝奶" in ready_drink_cleaned
    age_cleaned = sanitize_wangyue_context_phrases("孩子半岁后饭量忽大忽小。")
    assert age_cleaned == "孩子半岁后饭量忽大忽小"
    one_year_cleaned = sanitize_wangyue_context_phrases("一岁后开始研究儿童奶粉。")
    assert one_year_cleaned == "一岁后开始研究儿童奶粉"
    amount_cleaned = sanitize_wangyue_context_phrases("奶量从100ml慢慢喝到180ml，没硬追。")
    assert "100ml" not in amount_cleaned
    assert "180ml" not in amount_cleaned
    assert "奶量慢慢上来" in amount_cleaned
    bottle_cleaned = sanitize_wangyue_context_phrases("现在出门水壶里都是这个。")
    assert "水壶里" not in bottle_cleaned
    assert "在家喝这杯奶" not in bottle_cleaned
    digestive_cleaned = sanitize_wangyue_context_phrases("喝了快两周，肚子软软的，便便也规律了，不是胀气就是不爱喝的情况少了。")
    assert "肚子" not in digestive_cleaned
    assert "便便" not in digestive_cleaned
    assert "胀气" not in digestive_cleaned
    assert "日常状态看着还顺" in digestive_cleaned
    tummy_cleaned = sanitize_wangyue_context_phrases("小朋友喝得挺顺，也没闹过肚肚。")
    assert "肚肚" not in tummy_cleaned
    assert "喝着还算顺" in tummy_cleaned
    tongue_cleaned = sanitize_wangyue_context_phrases("试过几款不是太甜就是舌苔白。")
    assert "舌苔白" not in tongue_cleaned
    assert "不太适应" in tongue_cleaned
    cough_cleaned = sanitize_wangyue_context_phrases("孩子爸说她好像没怎么咳嗽了，我也没特别做什么，就是换成了皇家美素佳儿旺玥。")
    assert "咳嗽" not in cough_cleaned
    assert "换成了" not in cough_cleaned
    assert "皇家美素佳儿旺玥" not in cough_cleaned
    choice_cleaned = sanitize_wangyue_context_phrases("所以给孩子选了皇家美素佳儿旺玥，日常营养补充上能跟上就好。")
    assert "给孩子选了皇家美素佳儿旺玥" in choice_cleaned
    assert "后来留意到皇家美素佳儿旺玥" not in choice_cleaned
    product_switch_cleaned = sanitize_wangyue_context_phrases("干脆把家里喝的儿童奶粉换成了旺玥，冲的就是它主打保护力这块。")
    assert "儿童奶粉换成了旺玥" in product_switch_cleaned
    assert "儿童奶粉后来留意到旺玥" not in product_switch_cleaned
    product_place_cleaned = sanitize_wangyue_context_phrases("我把旺玥放在家里，平时记得就喝。")
    assert "家里喝旺玥" not in product_place_cleaned
    assert "留意到旺玥" not in product_place_cleaned
    brain_cleaned = sanitize_wangyue_context_phrases("她小脑瓜转得快，也不知道是不是用脑太多。")
    assert "小脑瓜" not in brain_cleaned
    assert "用脑太多" not in brain_cleaned
    assert "信息量太多" in brain_cleaned
    self_open_cleaned = sanitize_baby_milk_action_phrases("没想到她自己打开罐子凑近闻了闻。")
    assert "自己打开罐子" not in self_open_cleaned
    assert "等我打开罐子" in self_open_cleaned
    strip_cleaned = sanitize_baby_milk_action_phrases("她自己拆了条冲好，还把杯子放水池。")
    assert "自己拆了条冲好" not in strip_cleaned
    assert "等我冲好" in strip_cleaned
    can_grab_cleaned = sanitize_baby_milk_action_phrases("她伸手拽奶粉罐，一把抱怀里不撒手。")
    assert "伸手拽奶粉罐" not in can_grab_cleaned
    assert "抱怀里不撒手" not in can_grab_cleaned
    assert "在旁边等我看奶粉罐" in can_grab_cleaned
    can_toy_cleaned = sanitize_baby_milk_action_phrases("我那罐皇家旺玥也被她翻出来当积木摆弄。")
    assert "当积木" not in can_toy_cleaned
    assert "放在家里" in can_toy_cleaned


def test_product_experience_phrase_guard_blocks_temporary_remedy_or_overclaim():
    review = review_product_experience_phrase(
        title="换季防风全靠它，娃喝得香身体也稳",
        body="娃最近上学回来老打喷嚏，我赶紧把旺玥安排上，每天早晚一杯，感觉这保护力确实没白养。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "防风全靠" in review.hard_risk_hits
    assert "赶紧把旺玥安排上" in review.hard_risk_hits
    assert "没白养" in review.hard_risk_hits
    assert "hard_risk_expression" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_allows_plain_right_choice_phrase():
    review = review_product_experience_phrase(
        title="今天疯跑一下午",
        body=(
            "下午带娃在小区撒欢，追着球跑了快一小时。"
            "看他蹦跶那劲头，突然觉得家里一直喝的旺玥确实没白选，"
            "钙铁锌和关键营养都跟得上，成长阶段这样正合适。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v349_mainline_unfolding_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert "没白选" not in review.hard_risk_hits
    assert "hard_risk_expression" not in review.reasons


def test_product_experience_phrase_guard_allows_negated_temporary_remedy():
    review = review_product_experience_phrase(
        title="保护力这块我会看",
        body="上学接触的人一多，我就开始盯孩子的日常保护力了。选旺玥是因为它侧重这块，不是临时补救，平时就当基础营养喝着。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "临时补救" not in review.hard_risk_hits
    assert "hard_risk_expression" not in review.reasons
    assert review.rewrite_required is False
    assert review.pass_ is True


def test_product_experience_phrase_guard_blocks_positive_temporary_remedy():
    review = review_product_experience_phrase(
        title="赶紧临时补救一下",
        body="孩子一有状况我就临时补救，回家赶紧泡旺玥。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "临时补救" in review.hard_risk_hits
    assert "hard_risk_expression" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_wangyue_meta_ad_disclaimer():
    review = review_product_experience_phrase(
        title="有点纠结",
        body="喝旺玥一阵了，饭量时好时坏，纠结睡前那杯要不要留。不是种草，就想问问大家怎么判断换或停？",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "求问/轻复盘",
            "product_appearance_mode": "产品是明确讨论对象但不装日记",
        },
    )

    assert "不是种草" in review.hard_risk_hits
    assert "hard_risk_expression" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_allows_not_following_trend_in_selection_context():
    review = review_product_experience_phrase(
        title="又补了旺玥",
        body="家里一直喝的旺玥，这次补货主要还是看它支持保护力。乳铁蛋白和HMO这些，当初选的时候特意了解过，不是跟风。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v280_closure_attractor_cleanup_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert "不是跟风" not in review.hard_risk_hits
    assert "hard_risk_expression" not in review.reasons
    assert review.rewrite_required is False
    assert review.pass_ is True


def test_product_experience_phrase_guard_blocks_wangyue_after_symptom_remedy_chain():
    plan = {
        "rule_type": "business_rule",
        "asset_key": "wangyue_article_business_rules",
        "corpus": "写作规则：孩子接触人多后，妈妈担心容易中招；旺玥支持孩子保护力。",
    }
    cases = [
        (
            "带娃出门后的小担心",
            "带娃出去玩了几天，回来小皮孩就哈啾了两声，我有点紧张。"
            "平常在外面摸这摸那的，接触的人也多，总担心他防不住。"
            "思来想去还是把家里喝的旺玥给他换上了，就图它保护力这块能兜住。",
            "换上",
        ),
        (
            "刚送完娃，今天又是三个小喷嚏",
            "我家姐姐集体生活才一个月，我就发现她小喷嚏不断。"
            "本来想是不是要补点啥，后来一琢磨，还是把家里奶粉选了旺玥了。",
            "选了旺玥",
        ),
        (
            "这小孩真的每天都在社交",
            "我一直悬着心，生怕他哪儿不舒服。后来干脆把他喝的牛奶换成了旺玥儿童奶粉。",
            "换成了旺玥",
        ),
        (
            "幼儿园那几天",
            "有次接娃发现他小脸红红的，手心也热，赶紧带回家观察。"
            "后来跟妈妈们聊，才知道她们早换了奶粉，我也选了旺玥。",
            "选了旺玥",
        ),
    ]

    for title, body, expected_hit in cases:
        review = review_product_experience_phrase(title=title, body=body, plan=plan)
        assert any(expected_hit in hit for hit in review.hard_risk_hits)
        assert "hard_risk_expression" in review.reasons
        assert review.rewrite_required is True
        assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_symptom_disappearance_as_effect_proof():
    review = review_product_experience_phrase(
        title="刚补了一罐旺玥",
        body=(
            "最近身边中招的小朋友特别多，我们倒还算稳。"
            "她每天户外跑跑跳跳，接触面不小，但出勤和状态一直在线。"
            "刚蹲下帮她收拾，她突然说‘妈妈我今天没咳嗽’，我心里一下就软了。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v309_keyword_role_narrowing_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert "hard_risk_expression" in review.reasons
    assert any(hit.startswith("症状效果证明：") and "没咳嗽" in hit for hit in review.hard_risk_hits)
    assert any("没咳嗽" in hit for hit in _blocking_product_experience_phrase_hits(review))


def test_product_experience_phrase_guard_allows_plain_wangyue_selection_after_worry():
    review = review_product_experience_phrase(
        title="娃上幼儿园之后",
        body="娃上幼儿园之后，接触的人多了，我会多想一点。后来给他选了旺玥，主要是看中保护力这块。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：孩子接触人多后，妈妈担心容易中招；旺玥支持孩子保护力。",
        },
    )

    assert review.hard_risk_hits == []
    assert "hard_risk_expression" not in review.reasons
    assert review.rewrite_required is False
    assert review.pass_ is True


def test_product_experience_phrase_guard_blocks_precise_height_proof():
    review = review_product_experience_phrase(
        title="我终于不用天天盯饭桌了",
        body="她喝旺玥刚好三个月，上次体检身高追上来两厘米，我终于不用天天盯饭桌了。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "体检身高追上来" in review.hard_risk_hits
    assert "身高追上来两厘米" in review.hard_risk_hits
    assert "hard_risk_expression" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_medical_authority_proof_chain():
    review = review_product_experience_phrase(
        title="3岁后选奶",
        body="体检完医生说孩子活动量大了，营养得跟上。旺玥是3岁以上4段儿童奶粉，钙铁锌这些我会多看一眼。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_painpoint_selling_posttype_matrix_v28_20260624",
            "post_type": "阶段选择复盘",
            "product_appearance_mode": "旺玥作为阶段选择依据出现",
            "corpus": "旺玥事实必须正确：3周岁以上专用4段儿童奶粉，适配3-6岁学龄前儿童。",
        },
    )

    assert "体检完医生" in review.hard_risk_hits
    assert "医生说" in review.hard_risk_hits
    assert review.wangyue_explicit_age_hits == []
    assert "hard_risk_expression" in review.reasons
    assert "wangyue_explicit_age_context" not in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_explicit_temporal_context():
    review = review_product_experience_phrase(
        title="换季这几天",
        body="最近换季，入夏后又天冷，风大的季节里娃胃口时好时坏，我就把旺玥奶粉安排上了，日常营养能跟上就行。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert review.temporal_context_hits == ["换季这几天", "最近换季"]
    assert "explicit_temporal_context" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_allows_historical_event_and_school_stage_context():
    review = review_product_experience_phrase(
        title="中班后那罐奶粉",
        body="双十一囤的旺玥到了，娃上中班后接触人多，我还是看保护力。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert review.temporal_context_hits == []
    assert "explicit_temporal_context" not in review.reasons


def test_product_experience_phrase_guard_allows_weather_history_and_duration_context():
    review = review_product_experience_phrase(
        title="放学后先去公园跑一圈",
        body="天气好就直接带去小区公园跑一圈。旺玥是去年开始喝的，喝了半年，现在当日常营养补充。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "正文40-130字，标题另写。0705旺玥活动",
        },
    )

    assert review.temporal_context_hits == []
    assert "explicit_temporal_context" not in review.reasons


def test_product_experience_phrase_guard_allows_past_clothing_season_reference():
    review = review_product_experience_phrase(
        title="衣服下摆被撑得有点翘",
        body="周末收拾衣柜，翻出他去年秋天的外套，试着套了一下，肩膀那明显绷着了。现在喝的是旺玥，最近抱他上下台阶，手臂能感觉到后背有肉了。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v155_title_rule_slim_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert review.wangyue_time_event_context_hits == []
    assert "wangyue_time_event_context" not in review.reasons


def test_product_experience_phrase_guard_allows_current_action_with_past_season_reference():
    review = review_product_experience_phrase(
        title="长高了的小变化",
        body="最近翻出去年秋天的裤子，发现短了一截，小腿都在外面晃。小家伙自己都没注意到，就是跑起来更稳当了些。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v155_title_rule_slim_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert review.temporal_context_hits == []
    assert "explicit_temporal_context" not in review.reasons
    assert review.wangyue_time_event_context_hits == []
    assert "wangyue_time_event_context" not in review.reasons


def test_product_experience_phrase_guard_allows_current_school_term_span_without_season():
    review = review_product_experience_phrase(
        title="补货到",
        body="家里旺玥快见底了，又开了一罐新的。这学期下来感觉挺明显的，放学接他那会儿，不像以前那样蔫蔫的，还能在小区里跑几圈再回家。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v155_title_rule_slim_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert review.temporal_context_hits == []
    assert "explicit_temporal_context" not in review.reasons


def test_product_experience_phrase_guard_blocks_current_weather_and_season_anchor():
    review = review_product_experience_phrase(
        title="这几天降温",
        body="现在冬天，现在天气一变就容易担心，我就把旺玥放进日常营养里。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "正文40-130字，标题另写。0705旺玥活动",
        },
    )

    assert review.temporal_context_hits == ["这几天降温", "现在冬天", "现在天气一变"]
    assert "explicit_temporal_context" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_allows_relative_school_event_anchor():
    review = review_product_experience_phrase(
        title="同事问起儿童奶粉",
        body="上周同事问我家娃怎么样，说她们班里最近请假的不少。我说旺玥一直喝着，精神头还行。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert review.temporal_context_hits == []
    assert "explicit_temporal_context" not in review.reasons
    assert review.wangyue_time_event_context_hits == []
    assert "wangyue_time_event_context" not in review.reasons


def test_product_experience_phrase_guard_blocks_wangyue_temporal_effect_mismatch():
    plan = {
        "rule_type": "business_rule",
        "asset_key": "wangyue_article_business_rules",
        "corpus": "活动：0705旺玥活动。",
    }
    samples = {
        "接娃回来翻了翻购物车，顺手又加了一罐旺玥。家里这罐刚开，状态在线，跑跳有劲。": "刚开，状态在线",
        "旺玥一直在喝，乳铁蛋白这块我会看。我家这位放学回来还愿意跟我聊今天玩了什么，精神头在线，没跟着中招。": "今天玩了什么，精神头在线，没跟着中招",
        "这次换旺玥，不知道是不是心理作用，感觉他状态稳了不少。": "这次换旺玥，不知道是不是心理作用，感觉他状态稳",
        "之前选4段奶粉翻了好几天功课，最后还是入了旺玥，昨天抱娃忽然觉着重了好些，摸后背都扎扎实实长肉了。": "昨天抱娃忽然觉着重了好些",
    }

    for body, expected_hit in samples.items():
        review = review_product_experience_phrase(title="旺玥记录", body=body, plan=plan)
        assert "wangyue_article_logic_drift_context" in review.reasons
        assert any(expected_hit in hit for hit in review.wangyue_article_logic_drift_hits)


def test_product_experience_phrase_guard_allows_wangyue_effect_when_time_span_exists():
    plan = {
        "rule_type": "business_rule",
        "asset_key": "wangyue_article_business_rules",
        "corpus": "活动：0705旺玥活动。",
    }
    samples = [
        "旺玥一直在喝，最近没怎么请假，精神头也还行。",
        "昨天接娃排队，听前面妈妈说她家又请假了，我家倒是一直全勤，旺玥也一直喝着。",
        "今天一本找不同自己磨了快半小时，比之前坐得住些，旺玥这罐我会继续留着。",
    ]

    for body in samples:
        review = review_product_experience_phrase(title="旺玥记录", body=body, plan=plan)
        assert "wangyue_article_logic_drift_context" not in review.reasons
        assert review.wangyue_article_logic_drift_hits == []


def test_product_experience_phrase_guard_routes_wangyue_season_anchor_to_time_event():
    review = review_product_experience_phrase(
        title="同事问起儿童奶粉",
        body="入冬那阵班里好几个请假，他倒精神头足。家里旺玥一直喝着，乳铁蛋白这点我会看。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert "入冬" in review.wangyue_time_event_context_hits
    assert "wangyue_time_event_context" in review.reasons


def test_product_experience_phrase_guard_allows_school_absence_event_without_relative_time():
    review = review_product_experience_phrase(
        title="接娃路上才发现的",
        body="班上请假的多了，我心里也跟着紧了一下。家里旺玥一直在喝，放学回来还有劲。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert review.wangyue_time_event_context_hits == []
    assert "wangyue_time_event_context" not in review.reasons


def test_product_experience_phrase_guard_allows_own_child_absence_feedback():
    review = review_product_experience_phrase(
        title="同事问起儿童奶粉",
        body="同事问我家娃请假多不多，我说还好。我家喝旺玥后请假少，精神头也在线。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert review.wangyue_time_event_context_hits == []
    assert "wangyue_time_event_context" not in review.reasons


def test_product_experience_phrase_guard_allows_relative_product_arrival_anchor():
    review = review_product_experience_phrase(
        title="又开一罐",
        body="整理快递箱，扒拉出前两天到的旺玥，顺手拆了放餐边柜。最近刚补了两罐，先这么喝着吧。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert review.temporal_context_hits == []
    assert "explicit_temporal_context" not in review.reasons


def test_product_experience_phrase_guard_allows_relative_effect_and_object_anchor():
    review = review_product_experience_phrase(
        title="抱起来有点分量了",
        body="喝了一阵，最近抱他上楼明显沉了点。昨天他爸随口说娃壮实了，刚才又把空罐丢进收纳箱。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert review.temporal_context_hits == []
    assert "explicit_temporal_context" not in review.reasons


def test_product_experience_phrase_guard_allows_weak_school_stage_without_current_event():
    review = review_product_experience_phrase(
        title="中班后那罐奶粉",
        body="从中班开始喝旺玥，平时接触人多，我会看乳铁蛋白这类保护力营养。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert review.temporal_context_hits == []
    assert "explicit_temporal_context" not in review.reasons
    assert "wangyue_time_event_context" not in review.reasons


def test_product_experience_phrase_guard_routes_wangyue_time_event_to_model_rewrite():
    review = review_product_experience_phrase(
        title="每次去游乐园都怕回家蔫蔫的",
        body="今天幼儿园春游回来，小朋友居然还嚷嚷要骑车。家里喝的旺玥，保护力这块我会多看一眼。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "正文40-130字，标题另写。0705旺玥活动",
        },
    )

    assert review.wangyue_time_event_context_hits == ["春游"]
    assert "wangyue_time_event_context" in review.reasons
    assert "explicit_temporal_context" not in review.reasons
    assert "wangyue_time_event_context" in _semantic_wangyue_context_reasons(review)


def test_product_experience_phrase_guard_routes_wangyue_autumn_outing_to_model_rewrite():
    review = review_product_experience_phrase(
        title="秋游回来还挺有劲",
        body="幼儿园秋游回来，小朋友还嚷嚷要骑车。家里喝的旺玥，保护力这块我会多看一眼。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "正文40-130字，标题另写。0705旺玥活动",
        },
    )

    assert review.wangyue_time_event_context_hits == ["秋游"]
    assert "wangyue_time_event_context" in review.reasons


def test_product_experience_phrase_guard_routes_wangyue_taqing_to_model_rewrite():
    review = review_product_experience_phrase(
        title="户外踏青回来还挺稳",
        body="幼儿园户外踏青回来，小朋友还嚷嚷要骑车。家里喝的旺玥，保护力这块我会多看一眼。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "正文40-130字，标题另写。0705旺玥活动",
        },
    )

    assert review.wangyue_time_event_context_hits == ["踏青"]
    assert "wangyue_time_event_context" in review.reasons
    assert sanitize_wangyue_time_event_context("幼儿园户外踏青回来") == "幼儿园户外活动回来"


def test_product_experience_phrase_guard_routes_wangyue_season_word_to_model_rewrite():
    review = review_product_experience_phrase(
        title="配方翻到眼花",
        body="喝了一阵，小身板结实了不少，换季也没咋请假。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v139_example_kernel_slim_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert review.wangyue_time_event_context_hits == ["换季"]
    assert "wangyue_time_event_context" in review.reasons
    assert "wangyue_time_event_context" in _semantic_wangyue_context_reasons(review)


def test_product_experience_rewrite_input_mentions_wangyue_time_event_context():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "正文40-130字，标题另写。0705旺玥活动",
        },
        title="每次去游乐园都怕回家蔫蔫的",
        body="今天幼儿园春游回来，小朋友居然还嚷嚷要骑车。家里喝的旺玥，保护力这块我会多看一眼。",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    payload = service._product_experience_phrase_rewrite_input(item, review)
    instructions = "\n".join(payload["rewrite_instructions"])

    assert "明确时间/活动节点" in instructions
    assert "用模型改顺上下文，不要硬替换" in instructions
    assert "春游" in instructions
    assert "游乐园" not in instructions


def test_product_experience_phrase_guard_reads_explicit_body_length_range():
    review = review_product_experience_phrase(
        title="旺玥记录",
        body="对比了一堆还是选了旺玥。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：围绕日常营养补充来写。正文40-130字，标题另写。",
        },
    )

    assert review.length_target == ("自定义", 40, 130)


def test_product_experience_phrase_guard_blocks_common_ai_closure_phrase():
    review = review_product_experience_phrase(
        title="旺玥喝了一阵记录",
        body="家里一直喝旺玥，孩子状态也还行。继续观察看看，先这样喂着吧。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert "common_ai_closure_phrase" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_temporal_context_cleanup_removes_explicit_time_words():
    text = "换季这几天幼儿园容易中招，希望这学期少操点心，现在冬天也先不写。"

    cleaned = sanitize_temporal_context(text)

    assert cleaned == "平时幼儿园容易中招，希望这学期少操点心，平时也先不写。"
    assert not review_product_experience_phrase(title=cleaned, body="", plan={}).temporal_context_hits


def test_product_experience_temporal_context_cleanup_keeps_non_current_event_and_stage():
    text = "双十一囤的旺玥到了，娃上中班后接触人多，幼儿园一降温我就紧张。"

    cleaned = sanitize_temporal_context(text)

    assert cleaned == text


def test_product_experience_temporal_context_cleanup_repairs_suffix_after_replacement():
    text = "这次换季后孩子接触人多，现在春天后也容易担心。"

    cleaned = sanitize_temporal_context(text)

    assert cleaned == "平时孩子接触人多，平时也容易担心。"
    assert "最近后" not in cleaned
    assert "平时后" not in cleaned


def test_product_experience_odd_phrase_cleanup_does_not_rewrite_specific_disease_context():
    cleaned = sanitize_odd_product_experience_phrases("学校又是小状况又是手足口，我真是肉疼。")
    review = review_product_experience_phrase(title="", body=cleaned, plan={"asset_key": "wangyue_article_business_rules"})

    assert cleaned == "学校又是小状况又是手足口，我真是肉疼"
    assert review.odd_phrase_hits == ["手足口"]


def test_product_experience_odd_phrase_cleanup_leaves_shutdown_context_for_model_rewrite():
    cleaned = sanitize_odd_product_experience_phrases("他们班最近手足口停课了。")
    review = review_product_experience_phrase(title="", body=cleaned, plan={"asset_key": "wangyue_article_business_rules"})

    assert cleaned == "他们班最近手足口停课了"
    assert review.odd_phrase_hits == ["手足口停课"]


def test_product_experience_odd_phrase_cleanup_replaces_missing_nutrition_tail():
    cleaned = sanitize_odd_product_experience_phrases("不用天天操心缺啥。")

    assert cleaned == "不用天天操心营养不均衡"
    assert "缺啥" not in cleaned


def test_product_experience_odd_phrase_cleanup_replaces_wangyue_wrong_price_claim():
    cleaned = sanitize_odd_product_experience_phrases("朋友推了旺玥，说营养够全，我就试了一罐，反正不贵。")

    assert cleaned == "朋友推了旺玥，说营养够全，我就试了一罐，确实不便宜"
    assert "反正不贵" not in cleaned


def test_product_experience_odd_phrase_cleanup_repairs_manual_sweep_awkward_phrases():
    text = "P磷脂酰丝氨酸S和DHA搭着来，保护力也顺，背着有肉，午睡枕头边还放水杯，喝奶比喝水积极，小状况季也能全勤。"

    cleaned = sanitize_odd_product_experience_phrases(text)

    assert cleaned == "磷脂酰丝氨酸和DHA搭着来，状态也顺，背上有肉，平时喝奶还算积极，小状况多的时候也能全勤"
    assert "P磷脂酰丝氨酸S" not in cleaned
    assert "保护力也顺" not in cleaned
    assert "背着有肉" not in cleaned


def test_product_experience_format_cleanup_keeps_body_one_paragraph():
    cleaned = sanitize_product_experience_format("愣是比来比去比不出个结果\n最后挑了旺玥\n**省心**归省心，省得我我老惦记")

    assert cleaned == "愣是比来比去比不出个结果，最后挑了旺玥，省心归省心，省得我老惦记"


def test_product_experience_format_cleanup_keeps_sentence_punctuation():
    cleaned = sanitize_product_experience_format("刚补了一罐旺玥。")

    assert cleaned == "刚补了一罐旺玥。"


def test_product_experience_phrase_guard_blocks_long_unpunctuated_segment():
    body = (
        "妈耶娃一出去玩回来就容易蔫蔫的当妈的真心累好烦我真的比不来这些小孩子的东西噱头真多啊"
        "挑来挑去还是选了旺玥看中的就是它支持保护力日常喝喝当个营养补给至少心里能稳当点"
        "保护力差的话特别容易中招这个奶目前喝下来还行除了贵没别的毛病省心"
    )

    review = review_product_experience_phrase(
        title="有没有同款孩子",
        body=body,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "正文40-130字。",
        },
    )

    assert "long_unpunctuated_body_segment" in review.reasons
    assert review.run_on_fragment_hits


def test_product_experience_rewrite_input_mentions_run_on_fragment():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    body = (
        "妈耶娃一出去玩回来就容易蔫蔫的当妈的真心累好烦我真的比不来这些小孩子的东西噱头真多啊"
        "挑来挑去还是选了旺玥看中的就是它支持保护力日常喝喝当个营养补给至少心里能稳当点"
        "保护力差的话特别容易中招这个奶目前喝下来还行除了贵没别的毛病省心"
    )
    review = review_product_experience_phrase(
        title="有没有同款孩子",
        body=body,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "正文40-130字。",
        },
    )
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "正文40-130字。",
        },
        title="有没有同款孩子",
        body=body,
    )

    payload = service._product_experience_phrase_rewrite_input(item, review)

    assert any("很长的无标点口语串" in instruction for instruction in payload["rewrite_instructions"])


def test_product_experience_rewrite_input_mentions_title_guard_hits():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    review = review_product_experience_phrase(
        title="娃爸一句话，我又看了一眼奶粉罐",
        body="家里聊天，他爸突然说最近娃好像没怎么喊累。后来给他选了皇家美素佳儿旺玥，营养全面些。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 2,
            "corpus": "写作规则：围绕孩子普通日常状态来写。",
        },
    )
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 2,
            "corpus": "写作规则：围绕孩子普通日常状态来写。",
        },
        title="娃爸一句话，我又看了一眼奶粉罐",
        body="家里聊天，他爸突然说最近娃好像没怎么喊累。后来给他选了皇家美素佳儿旺玥，营养全面些。",
    )

    payload = service._product_experience_phrase_rewrite_input(item, review)

    instructions = "\n".join(payload["rewrite_instructions"])
    assert "标题也命中问题表达" in instructions
    assert "奶粉罐" in instructions
    assert "标题必须同步改掉" in instructions


def test_product_experience_phrase_guard_blocks_malformed_quote_fragment():
    body = "外婆在厨房择菜，突然问：“小宝呢？那副小模样让我愣了下。后来给他选了皇家美素佳儿旺玥。"
    review = review_product_experience_phrase(
        title="孩子突然安静下来",
        body=body,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 2,
            "corpus": "写作规则：围绕孩子普通日常状态来写。",
        },
    )

    assert "malformed_fragment" in review.reasons
    assert "中文引号不成对" in review.malformed_fragment_hits
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 2,
            "corpus": "写作规则：围绕孩子普通日常状态来写。",
        },
        title="孩子突然安静下来",
        body=body,
    )
    payload = service._product_experience_phrase_rewrite_input(item, review)
    assert any("半截引号" in instruction for instruction in payload["rewrite_instructions"])


def test_product_experience_phrase_guard_blocks_wangyue_growth_nutrition_row4_drift():
    review = review_product_experience_phrase(
        title="这罐还真选对了",
        body="孩子饭量上来了，身高体重曲线也好看，每天冲一杯就一步搞定，成长营养这块不用补这补那。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 4,
            "corpus": "写作规则：围绕给孩子选择皇家美素佳儿旺玥儿童奶粉来写，理由是补充营养、支持成长；正文40-130字。",
        },
    )

    assert "wangyue_growth_nutrition_drift_context" in review.reasons
    assert review.rewrite_required is True
    assert "身高体重曲线" in review.wangyue_growth_nutrition_drift_hits
    assert "每天冲一杯" in review.wangyue_growth_nutrition_drift_hits
    assert "一步搞定" in review.wangyue_growth_nutrition_drift_hits


def test_product_experience_phrase_guard_blocks_row4_new_drinking_action_leaks():
    review = review_product_experience_phrase(
        title="凑近一看，姐妹俩抢着喝",
        body=(
            "妹妹看着哥哥喝纯牛奶馋得不行，但她喝奶敏感，我给她选了皇家美素佳儿旺玥，"
            "当早餐补充。昨天收拾零食柜翻出一罐旺玥，姐妹俩抢着喝，我赶紧冲一杯。"
            "坚持喝一喝，精神点就好。后来把皇家美素佳儿旺玥放柜子里，孩子自己记得去喝。"
            "目前用着挺顺手，后续再看效果吧，孩子喝着也接受。"
            "柜子里那罐旺玥还在，孩子偶尔会凑过去看看。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 4,
            "corpus": "写作规则：围绕孩子成长阶段日常营养别落下这件事写。",
        },
    )

    assert "wangyue_growth_nutrition_drift_context" in review.reasons
    assert "纯牛奶" in review.wangyue_growth_nutrition_drift_hits
    assert "喝奶敏感" in review.wangyue_growth_nutrition_drift_hits
    assert "当早餐补充" in review.wangyue_growth_nutrition_drift_hits
    assert "翻出一罐" in review.wangyue_growth_nutrition_drift_hits
    assert "抢着喝" in review.wangyue_growth_nutrition_drift_hits
    assert "冲一杯" in review.wangyue_growth_nutrition_drift_hits
    assert "坚持喝一喝" in review.wangyue_growth_nutrition_drift_hits
    assert "精神点就好" in review.wangyue_growth_nutrition_drift_hits
    assert "放柜子里" in review.wangyue_growth_nutrition_drift_hits
    assert "自己记得去喝" in review.wangyue_growth_nutrition_drift_hits
    assert "用着挺顺手" in review.wangyue_growth_nutrition_drift_hits
    assert "后续再看效果" in review.wangyue_growth_nutrition_drift_hits
    assert "孩子喝着也接受" in review.wangyue_growth_nutrition_drift_hits
    assert "柜子里那罐旺玥" in review.wangyue_growth_nutrition_drift_hits
    assert "凑过去看看" in review.wangyue_growth_nutrition_drift_hits


def test_product_experience_phrase_guard_keeps_growth_nutrition_drift_scoped_to_row4():
    review = review_product_experience_phrase(
        title="日常记录一下",
        body="孩子饭量和身高体重曲线我会记录，喝完以后也看当天状态。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 1,
            "corpus": "写作规则：孩子接触人多，妈妈担心容易中招；旺玥主打支持孩子保护力。",
        },
    )

    assert "wangyue_growth_nutrition_drift_context" not in review.reasons
    assert review.wangyue_growth_nutrition_drift_hits == []


def test_product_experience_phrase_guard_blocks_wangyue_logic_drift_terms():
    review = review_product_experience_phrase(
        title="哎这罐奶粉我先放购物车了",
        body="给娃挑口粮时顺手直接下单了，主要看它护眼和保护力都搭得上。冲出来奶香清淡，孩子眼睛都快冒星星，脸色都亮堂。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 2,
            "corpus": "写作规则：围绕孩子活动量大、日常状态观察来写；旺玥兼顾孩子保护力和眼脑相关营养。",
        },
    )

    assert "wangyue_article_logic_drift_context" in review.reasons
    assert "口粮" in review.wangyue_article_logic_drift_hits
    assert "购物车" in review.wangyue_article_logic_drift_hits
    assert "直接下单" in review.wangyue_article_logic_drift_hits
    assert "护眼" in review.wangyue_article_logic_drift_hits
    assert "眼睛都快冒星星" in review.wangyue_article_logic_drift_hits
    assert "冲出来" in review.wangyue_article_logic_drift_hits
    assert "奶香清淡" in review.wangyue_article_logic_drift_hits
    assert "脸色都亮堂" in review.wangyue_article_logic_drift_hits


def test_product_experience_phrase_guard_blocks_wangyue_hidden_negative_comparison():
    review = review_product_experience_phrase(
        title="看配方时留意到的",
        body=(
            "最后留下旺玥，是看它专门标了钙铁锌，对我家这种绿叶菜吃得勉强的娃来说，"
            "能多补一点是一点。价格比普通牛奶粉略高，但想想配方，还是继续了。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "post_type": "对比选择",
            "ugc_post_type": "对比选择",
            "corpus": "0705旺玥活动",
        },
    )

    assert "wangyue_hidden_negative_comparison_context" in review.reasons
    assert "wangyue_hidden_negative_comparison_context" in _semantic_wangyue_context_reasons(review)
    assert "普通牛奶粉" in review.wangyue_hidden_negative_comparison_hits
    assert any("价格比普通牛奶粉略高" in hit for hit in review.wangyue_hidden_negative_comparison_hits)
    assert review.rewrite_required is True


def test_product_experience_phrase_guard_blocks_wangyue_price_tradeoff_without_downgrade():
    review = review_product_experience_phrase(
        title="看配方时留意到的",
        body="最后留下旺玥，是因为钙铁锌和乳铁蛋白都对得上。价格不是最低，但我更看重配方。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "post_type": "对比选择",
            "ugc_post_type": "对比选择",
            "corpus": "0705旺玥活动",
        },
    )

    assert "价格不是最低" in review.wangyue_hidden_negative_comparison_hits
    assert "wangyue_hidden_negative_comparison_context" in review.reasons


def test_product_experience_phrase_guard_allows_purchase_and_sensory_terms_in_eligible_wangyue_context():
    selection_review = review_product_experience_phrase(
        title="选奶看了几款",
        body="对比几款之后我直接下单了旺玥，冲出来奶香清淡，这点是我后来没换的原因之一。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_selection_review_painpoints_v23_20260624",
            "post_type": "选奶/儿童奶粉选择复盘",
            "ugc_post_type": "选奶复盘型",
            "product_appearance_mode": "旺玥作为选择依据出现",
            "product_role": "选择时看过的依据",
            "corpus": "围绕妈妈选择儿童奶粉时为什么留下旺玥来写。",
        },
    )

    assert "直接下单" not in selection_review.wangyue_article_logic_drift_hits
    assert "冲出来" not in selection_review.wangyue_article_logic_drift_hits
    assert "奶香清淡" not in selection_review.wangyue_article_logic_drift_hits
    restock_review = review_product_experience_phrase(
        title="月底补货",
        body="月底看账单才发现旺玥快没了，顺手直接下单了。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "补货/家务清单",
            "ugc_post_type": "复购/囤货型",
            "product_appearance_mode": "产品是家里库存物件",
            "product_role": "库存物件/补货清单一项",
            "corpus": "围绕家里补货清单来写。",
        },
    )
    assert "直接下单" not in restock_review.wangyue_article_logic_drift_hits


def test_product_experience_phrase_guard_allows_calcium_iron_zinc_light_review_without_protection_term():
    review = review_product_experience_phrase(
        title="被问奶粉配方，我看了下这个",
        body="小区妈妈问我给娃喝什么奶粉，说自家娃挑得头疼。我没直接答，就提了句旺玥。其实也是上次翻罐子时瞄到的，钙铁锌那块配置看着挺顺眼。最近抱他上楼，感觉沉了点，后背摸着有肉，衣服也撑起来了。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v155_title_rule_slim_article_rules",
            "post_type": "轻测评",
            "ugc_post_type": "轻测评",
            "product_appearance_mode": "旺玥作为被问到或看配方时提到的一罐，只保留一个成分关注点",
            "selling_point": "日常营养配置/钙铁锌",
            "corpus": "保护力相关成分只写保护力、少中招、状态稳这类观察；成长发育类身体变化从阶段营养、整体营养配置、钙铁锌或营养丰富来写。0705旺玥活动",
        },
    )

    assert "保护力营养缺失" not in review.wangyue_article_logic_drift_hits
    assert "wangyue_article_logic_drift_context" not in review.reasons


def test_product_experience_phrase_guard_uses_structured_selling_point_over_stale_rule_label():
    review = review_product_experience_phrase(
        title="别人问起时我说了几句",
        body="上周在小区遛娃，旁边妈妈看我崽跑得带劲，问我喝啥奶粉。我说三岁后换的旺玥，当时就是看中它整体营养配得比较全，钙铁锌这些基础都有。喝了大半年，感觉娃背上有肉了，抱起来明显沉手，衣服撑起来一点。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v209_benefit_bridge_article_rules",
            "topic": "V209-20｜保护力关注种草｜轻测评｜成长发育需求",
            "business_rule": "V209-20｜保护力关注种草｜轻测评｜成长发育需求",
            "painpoint": "成长发育需求",
            "selling_point": "营养丰富",
            "post_type": "轻测评",
            "ugc_post_type": "轻测评",
            "product_appearance_mode": "旺玥作为被问到或聊到成分时提到的一罐。",
            "product_role": "旺玥是轻测评里被提到的一罐。",
            "corpus": "痛点=成长发育需求；卖点父类=营养丰富。成长类身体观察从阶段营养、整体营养配置、钙铁锌或营养丰富承接。",
        },
    )

    assert "保护力营养缺失" not in review.wangyue_article_logic_drift_hits
    assert "wangyue_article_logic_drift_context" not in review.reasons


def test_product_experience_phrase_guard_allows_same_brand_continuation_surface():
    review = review_product_experience_phrase(
        title="三岁后感觉真的在抽条",
        body="收拾衣柜翻出她去年秋天的衣服，比划了一下居然都短了一截。三岁后感觉真的在抽条，抱着她明显沉了，背上也有肉了。现在喝的是旺玥，从原来同品牌续过来的，她挺接受的。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v155_title_rule_slim_article_rules",
            "product_appearance_mode": "旺玥作为三岁后阶段安排出现，只承接一个阶段状态",
            "selling_point": "同品牌延续/儿童阶段营养/整体营养配置",
            "corpus": "旺玥按3周岁以上、3-6岁学龄前儿童语境下的4段儿童奶粉写。0705旺玥活动",
        },
    )

    assert "日常营养配置缺失" not in review.wangyue_article_logic_drift_hits
    assert "wangyue_article_logic_drift_context" not in review.reasons


def test_product_experience_phrase_guard_blocks_wangyue_mixed_into_milk():
    review = review_product_experience_phrase(
        title="孩子嗓子干不喝水，试了个法子",
        body="后来往牛奶里加了一勺旺玥，他居然咕咚咕咚喝完了。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 2,
            "corpus": "写作规则：像普通妈妈随手记录孩子平时活动量大、家里日常喝皇家美素佳儿旺玥这件事。",
        },
    )

    assert "wangyue_article_logic_drift_context" in review.reasons
    assert "往牛奶里加" in review.wangyue_article_logic_drift_hits
    assert "加了一勺旺玥" in review.wangyue_article_logic_drift_hits


def test_product_experience_phrase_guard_allows_changed_to_wangyue_wording():
    review = review_product_experience_phrase(
        title="邻居说我儿子壮了",
        body="前两天碰到邻居，看我儿子背上的肉说怎么长这么结实了。我就顺口回说最近给他换了旺玥4段，本来就是打算让他营养跟得上，结果现在状态挺好，跑起来也有劲。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v155_title_rule_slim_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert "换了旺玥" not in review.odd_phrase_hits
    assert "odd_product_experience_phrase" not in review.reasons


def test_product_experience_phrase_guard_blocks_row2_eye_brain_detail_drift():
    review = review_product_experience_phrase(
        title="选奶粉真的不能光看一个点",
        body="我家那只出门滑板车能溜一小时，回家还要翻绘本、画画。我特别在意叶黄素和眼睛营养，怕她以后近视，又怕脑子不够用，挑来挑去选了旺玥。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 2,
            "corpus": "写作规则：围绕孩子活动量大、日常状态观察来写；旺玥兼顾孩子保护力和眼脑相关营养。",
        },
    )

    assert "wangyue_article_logic_drift_context" in review.reasons
    assert "叶黄素" in review.wangyue_article_logic_drift_hits
    assert "眼睛营养" in review.wangyue_article_logic_drift_hits
    assert "近视" in review.wangyue_article_logic_drift_hits
    assert "脑子不够用" in review.wangyue_article_logic_drift_hits
    assert "翻绘本" in review.wangyue_article_logic_drift_hits
    assert "画画" in review.wangyue_article_logic_drift_hits
    eye_review = review_product_experience_phrase(
        title="眼睛不酸了，娃活动量大也不怕",
        body="孩子活动量大，我会顺手看旺玥的保护力和眼脑营养，户外活动时总说眼睛酸，也爱揉眼睛。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 2,
            "corpus": "写作规则：围绕孩子活动量大、日常状态观察来写；旺玥兼顾孩子保护力和眼脑相关营养。",
        },
    )
    assert "眼睛酸" in eye_review.wangyue_article_logic_drift_hits
    assert "眼睛不酸了" in eye_review.wangyue_article_logic_drift_hits
    assert "揉眼睛" in eye_review.wangyue_article_logic_drift_hits
    cleaned = sanitize_wangyue_context_phrases("回家还得拼乐高、翻绘本，我就怕她以后近视、脑子不够用。")
    assert "翻绘本" not in cleaned
    assert "拼乐高" not in cleaned
    assert "近视" not in cleaned
    assert "脑子不够用" not in cleaned
    assert cleaned == ""
    assert "眼睛不酸" not in sanitize_wangyue_context_phrases("眼睛不酸了，娃活动量大也不怕。")


def test_product_experience_phrase_guard_allows_eye_brain_selection_context_without_effect_claim():
    review = review_product_experience_phrase(
        title="拼图堆了一桌",
        body=(
            "娃最近迷上大块拼图，一坐能坐半小时，我站旁边看着有点不放心。"
            "用眼用脑多了，之前换儿童奶粉的时候翻过几个牌子，旺玥里标了DHA和燕窝酸，"
            "不是指望喝了能怎样，就是选的时候多一层考虑。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_selection_review_painpoints_v23_20260624",
            "painpoint": "注意力不集中",
            "post_type": "选奶/儿童奶粉选择复盘",
            "ugc_post_type": "选奶复盘型",
            "product_role": "选择时看过的眼脑营养依据",
            "corpus": "核心痛点是注意力不集中，产品卖点只能写成妈妈选择儿童奶粉时关注眼脑营养的依据。",
        },
    )

    assert "wangyue_article_logic_drift_context" not in review.reasons
    assert "用眼" not in review.wangyue_article_logic_drift_hits
    assert "看绘本" not in review.wangyue_article_logic_drift_hits
    risky_review = review_product_experience_phrase(
        title="眼脑这块",
        body="孩子看绘本后老揉眼睛，我怕以后近视，所以选了旺玥看眼脑营养。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_selection_review_painpoints_v23_20260624",
            "painpoint": "注意力不集中",
            "post_type": "选奶/儿童奶粉选择复盘",
            "ugc_post_type": "选奶复盘型",
            "product_role": "选择时看过的眼脑营养依据",
            "corpus": "核心痛点是注意力不集中，产品卖点只能写成妈妈选择儿童奶粉时关注眼脑营养的依据。",
        },
    )
    assert "wangyue_article_logic_drift_context" in risky_review.reasons
    assert "揉眼睛" in risky_review.wangyue_article_logic_drift_hits
    assert "近视" in risky_review.wangyue_article_logic_drift_hits
    background_review = review_product_experience_phrase(
        title="眼脑这块",
        body="班里有小朋友已经近视了，我现在主要是控制屏幕时间。选儿童奶粉时另一个关注点是眼脑营养，旺玥这块我看过。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_selection_review_painpoints_v23_20260624",
            "painpoint": "注意力不集中",
            "post_type": "选奶/儿童奶粉选择复盘",
            "ugc_post_type": "选奶复盘型",
            "product_role": "选择时看过的眼脑营养依据",
            "corpus": "核心痛点是注意力不集中，产品卖点只能写成妈妈选择儿童奶粉时关注眼脑营养的依据。",
        },
    )
    assert "近视" not in background_review.wangyue_article_logic_drift_hits


def test_product_experience_phrase_guard_blocks_wangyue_selling_point_drift():
    review = review_product_experience_phrase(
        title="别的先不夸太满",
        body="旺玥先放进家里的选择里，别的先不夸太满，日常营养这块先顾住，后面有变化再看。我先记着",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_painpoint_selling_posttype_matrix_v25_20260624",
            "painpoint": "注意力不集中",
            "selling_point": "眼脑营养关注",
            "post_type": "轻测评/配方关注",
            "ugc_post_type": "轻测评型",
            "product_appearance_mode": "旺玥作为配方观察对象出现",
            "product_role": "被轻轻记录的配方依据",
            "corpus": "核心痛点是注意力不集中，产品卖点只能写成妈妈选择儿童奶粉时关注眼脑营养的依据。",
        },
    )

    assert "wangyue_article_logic_drift_context" in review.reasons
    assert "眼脑营养缺失" in review.wangyue_article_logic_drift_hits
    assert "日常营养" in review.wangyue_article_logic_drift_hits


def test_product_experience_phrase_guard_ignores_global_wangyue_fact_in_corpus_for_selling_drift():
    review = review_product_experience_phrase(
        title="买菜顺手补的",
        body="每周买菜列清单，除了蔬菜肉蛋，我会把旺玥加进去。孩子饭吃得不稳，钙铁锌这些容易漏，不用再分开买一堆瓶瓶罐罐。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v121_example_kernel_human_sell_nodrift",
            "painpoint": "营养不足",
            "selling_point": "钙铁锌/关键营养多样",
            "post_type": "家庭清单",
            "ugc_post_type": "家庭清单",
            "product_appearance_mode": "家庭营养清单里出现",
            "product_role": "旺玥是清单里稳定会买的一项",
            "corpus": "全局事实：旺玥按三岁后儿童奶粉/4段儿童奶粉理解。本篇卖点是钙铁锌和关键营养。",
        },
    )

    assert "4段阶段营养缺失" not in review.wangyue_article_logic_drift_hits
    assert "wangyue_article_logic_drift_context" not in review.reasons


def test_product_experience_phrase_guard_accepts_chinese_three_year_stage_for_wangyue_stage_selling_point():
    review = review_product_experience_phrase(
        title="衣服短了一截",
        body="三岁后翻出长袖，好几件袖口都短了。旺玥是这阶段在喝的，跑跳也有劲，饭量时好时坏就先这样安排。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
            "painpoint": "成长发育需求",
            "selling_point": "4段/乳铁蛋白/营养配置",
            "post_type": "阶段选择复盘",
            "ugc_post_type": "阶段选择复盘",
            "product_role": "旺玥是三岁后儿童阶段使用中的产品，不展开完整选奶定义",
        },
    )

    assert "4段阶段营养缺失" not in review.wangyue_article_logic_drift_hits


def test_product_experience_phrase_guard_does_not_treat_matrix_row4_as_legacy_growth_row4():
    review = review_product_experience_phrase(
        title="挑奶粉看得眼花",
        body="看儿童奶粉配方真的会看晕，旺玥这里我记住的是DHA和燕窝酸，孩子桌面时间多了，我会把眼脑营养这块算进去。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_painpoint_selling_posttype_matrix_v25_20260624",
            "source_row_no": 4,
            "painpoint": "注意力不集中",
            "selling_point": "眼脑营养关注",
            "post_type": "轻测评/配方关注",
            "ugc_post_type": "轻测评型",
            "product_appearance_mode": "旺玥作为配方观察对象出现",
            "corpus": "核心痛点是注意力不集中，产品卖点只能写成妈妈选择儿童奶粉时关注眼脑营养的依据。",
        },
    )

    assert "wangyue_growth_nutrition_drift_context" not in review.reasons
    assert review.wangyue_growth_nutrition_drift_hits == []


def test_product_experience_phrase_guard_blocks_row3_product_action_and_eye_drift():
    review = review_product_experience_phrase(
        title="娃突然冒出一句妈妈我眼睛累",
        body=(
            "下午带娃出门，他盯着路边广告牌看了半天，突然说眼睛有点累。"
            "回家给他泡了杯皇家美素佳儿旺玥，后来又瞟了眼奶粉罐。"
            "看绘本动画片时间不少，还老揉眼睛。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 3,
            "corpus": "写作规则：围绕孩子日常里容易走神、看东西多或信息接触多时，妈妈会关注眼脑营养这件事写。",
        },
    )

    assert "wangyue_article_logic_drift_context" in review.reasons
    assert "给他泡了杯" in review.wangyue_article_logic_drift_hits
    assert "奶粉罐" not in review.wangyue_article_logic_drift_hits
    assert "看绘本" in review.wangyue_article_logic_drift_hits
    assert "动画片" in review.wangyue_article_logic_drift_hits
    product_path_review = review_product_experience_phrase(
        title="孩子上了上学以后",
        body=(
            "孩子上了上学后，把皇家美素佳儿旺玥放在家里，平时那杯可能真帮了点忙。"
            "后来给娃试了，下午点心就顺手补补眼脑营养，你们娃也会这样吗？"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 3,
            "corpus": "写作规则：围绕孩子日常里容易走神、信息接触多时，妈妈会关注眼脑营养这件事写。",
        },
    )
    assert "把皇家美素佳儿旺玥放在家里" in product_path_review.wangyue_article_logic_drift_hits
    assert "平时那杯" in product_path_review.wangyue_article_logic_drift_hits
    assert "给娃试了" not in product_path_review.wangyue_article_logic_drift_hits
    assert "下午点心" in product_path_review.wangyue_article_logic_drift_hits
    assert "顺手补补眼脑营养" in product_path_review.wangyue_article_logic_drift_hits
    assert "你们娃也会这样吗" in product_path_review.wangyue_article_logic_drift_hits


def test_wangyue_context_cleanup_keeps_product_mention_when_removing_eye_brain_drift():
    cleaned = sanitize_wangyue_context_phrases(
        "想想她最近看书、拼图都能坐得住，精神头也足，我就给选了皇家美素佳儿旺玥。主要是看里面保护力这块。"
    )

    assert "看书" not in cleaned
    assert "拼图" not in cleaned
    assert "皇家美素佳儿旺玥" in cleaned
    assert "主要是看里面保护力这块" not in cleaned
    assert "主要是看旺玥的保护力这块" in cleaned


def test_product_experience_phrase_guard_blocks_wangyue_missing_product_mention():
    review = review_product_experience_phrase(
        title="我坐旁边听着也乐了",
        body="孩子爸给她讲历史，她突然把爸爸问住了。我坐旁边听着也乐了，主要是看里面保护力这块。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 2,
            "corpus": "写作规则：围绕孩子普通日常状态来写。",
        },
    )

    assert "wangyue_missing_product_mention" in review.reasons
    assert review.rewrite_required is True


def test_wangyue_post_rewrite_rejects_removed_product_mention():
    plan = {
        "rule_type": "business_rule",
        "asset_key": "wangyue_v209_benefit_bridge_article_rules",
        "corpus": "0705旺玥活动",
    }

    assert _rewrite_removed_required_wangyue_product(
        before={"title": "接触多后的观察", "body": "最近给他喝的旺玥，主要看乳铁蛋白和HMO。"},
        after={"title": "周末带娃观察", "body": "周末出去玩了一天，回来精神头还不错。"},
        plan=plan,
    )
    assert not _rewrite_removed_required_wangyue_product(
        before={"title": "接触多后的观察", "body": "最近给他喝的旺玥，主要看乳铁蛋白和HMO。"},
        after={"title": "周末带娃观察", "body": "周末出去玩了一天，旺玥这罐还在日常喝。"},
        plan=plan,
    )


def test_product_experience_rewrite_input_mentions_missing_wangyue_product_name():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 2,
            "corpus": "写作规则：围绕孩子普通日常状态来写。",
        },
        title="我坐旁边听着也乐了",
        body="孩子爸给她讲历史，她突然把爸爸问住了。我坐旁边听着也乐了，主要是看里面保护力这块。",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    payload = service._product_experience_phrase_rewrite_input(item, review)

    assert any("缺少产品名" in instruction for instruction in payload["rewrite_instructions"])


def test_product_experience_rewrite_input_mentions_scene_motive_drift():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "补货/家务清单",
            "product_appearance_mode": "产品是家里库存物件",
            "scene_motive_bucket": "快递到货拆箱",
            "corpus": "写作规则：补货场景里产品只是家中库存物件。",
        },
        title="拆箱记录",
        body="门口堆了一堆快递，拆开纸箱有一罐旺玥，顺手放进柜子。",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    payload = service._product_experience_phrase_rewrite_input(item, review)
    instructions = "\n".join(payload["rewrite_instructions"])

    assert "偏离了指定生活入口" in instructions
    assert "本篇入口是“快递到货拆箱”" in instructions
    assert "放进柜子" in instructions
    assert "不新增产品动作或另一套生活事件" in instructions


def test_product_experience_scene_motive_cleanup_removes_remaining_cabinet_drift():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "补货/家务清单",
            "product_appearance_mode": "产品是家里库存物件",
            "scene_motive_bucket": "早餐区/厨房台面整理",
        },
        title="台面又乱了",
        body="早上做完早餐，台面上堆满面包袋。顺手把旺玥放回柜子，旁边是吸管杯和湿巾。",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    post_review = service._apply_scene_motive_drift_cleanup(item, review)

    assert "柜子" not in item.body
    assert "留在台面边" in item.body
    assert post_review.pass_ is True
    assert item.quality_json["product_experience_scene_motive_cleanups"]


def test_product_experience_scene_motive_cleanup_avoids_leftover_location_suffix():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "补货/家务清单",
            "product_appearance_mode": "产品是家里库存物件",
            "scene_motive_bucket": "快递到货拆箱",
        },
        title="快递到了",
        body="门口堆了三个快递，拆开是旺玥。拆完直接把旺玥放进柜子里，旁边还有半罐没喝完的。",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    post_review = service._apply_scene_motive_drift_cleanup(item, review)

    assert "柜子" not in item.body
    assert "半罐" not in item.body
    assert "收里" not in item.body
    assert post_review.pass_ is True


def test_product_experience_scene_motive_cleanup_removes_empty_inventory_drift():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "补货/家务清单",
            "product_appearance_mode": "产品是家里库存物件",
            "scene_motive_bucket": "早餐区/厨房台面整理",
        },
        title="今天早上又乱",
        body="顺手理了理，发现旺玥那罐也快空了，就留在台面边边上。",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    post_review = service._apply_scene_motive_drift_cleanup(item, review)

    assert "快空了" not in item.body
    assert "台面边边上" not in item.body
    assert "台面边上" in item.body
    assert post_review.pass_ is True


def test_product_experience_scene_motive_cleanup_removes_generic_empty_inventory_for_supermarket_bucket():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "补货/家务清单",
            "product_appearance_mode": "产品是家里库存物件",
            "scene_motive_bucket": "超市顺手补刚需",
        },
        title="但手边还是乱糟糟的",
        body="超市顺手带回来的，旺玥、湿巾、还有两盒牛奶。家里库存清一清发现不少东西都见底了，但手边还是乱糟糟的",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    post_review = service._apply_scene_motive_drift_cleanup(item, review)

    assert "见底" not in item.body
    assert "库存清一清" not in item.body
    assert post_review.pass_ is True


def test_product_experience_usage_record_missing_product_cleanup_does_not_invent_wangyue_surface():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "使用记录",
            "product_appearance_mode": "产品是日常动作的一部分",
            "product_action_surface": "物件在场",
            "scene_motive_bucket": "周末在家磨蹭",
        },
        title="磨蹭一上午",
        body="早上玩具摊一地，我在地垫上叠衣服。他趴着拼积木，我顺手把杯子挪了挪位置。",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    post_review = service._apply_product_permission_missing_product_cleanup(item, review)

    assert "旺玥杯子" not in item.body
    assert "旺玥那罐也在旁边" not in item.body
    assert item.body == "早上玩具摊一地，我在地垫上叠衣服。他趴着拼积木，我顺手把杯子挪了挪位置。"
    assert "wangyue_missing_product_mention" in post_review.reasons
    assert "physical_action_carrier_mismatch" not in post_review.reasons
    assert not (item.quality_json or {}).get("product_experience_missing_product_surface_cleanups")


def test_product_experience_restock_missing_product_cleanup_does_not_invent_wangyue():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "补货/家务清单",
            "product_appearance_mode": "产品是家里库存物件",
            "ugc_post_type": "复购/囤货型",
            "product_role": "库存物件/补货清单一项",
            "scene_motive_bucket": "月底账单/购物车清理",
        },
        title="月底对账单",
        body="湿巾、洗衣凝珠，还有他总弄丢的吸管杯盖。每次月底看账单都觉得没买啥。",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    post_review = service._apply_product_permission_missing_product_cleanup(item, review)

    assert "旺玥也顺手补上" not in item.body
    assert item.body == "湿巾、洗衣凝珠，还有他总弄丢的吸管杯盖。每次月底看账单都觉得没买啥。"
    assert "wangyue_missing_product_mention" in post_review.reasons
    assert not (item.quality_json or {}).get("product_experience_missing_product_surface_cleanups")


def test_wangyue_postprocess_restore_helpers_do_not_append_selling_or_physical_context():
    body = "家里现在喝旺玥，孩子最近状态还行。"
    plan = {"business_rule": "旺玥主打保护力，乳铁蛋白/HMO。"}

    assert _restore_wangyue_selling_context_surface(body, plan) == body
    assert _restore_product_permission_wangyue_surface(
        "我顺手把杯子挪了挪位置。",
        post_type="使用记录",
    ) == "我顺手把杯子挪了挪位置。"


def test_product_experience_scene_motive_cleanup_removes_half_can_inventory_surface():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "补货/家务清单",
            "product_appearance_mode": "产品是家里库存物件",
            "scene_motive_bucket": "早餐区/厨房台面整理",
        },
        title="又堆了一堆",
        body="早餐台面上摊着面包袋、杯子、小碗，还有半罐旺玥。今天收拾顺手归位，才发现这罐也快见底了。",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    post_review = service._apply_scene_motive_drift_cleanup(item, review)

    assert "半罐" not in item.body
    assert "快见底" not in item.body
    assert post_review.pass_ is True


def test_product_experience_product_action_surface_cleanup_lowers_child_drinking_action():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "使用记录",
            "product_appearance_mode": "产品是日常动作的一部分",
            "product_action_surface": "孩子轻微使用",
            "scene_motive_bucket": "早上赶时间",
        },
        title="早上赶时间",
        body="早上忙得跟打仗一样，桌上那杯旺玥他自己端过去喝了几口，我还在翻袜子。",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    post_review = service._apply_product_action_surface_cleanup(item, review)

    assert "自己端过去喝" not in item.body
    assert "喝了几口" not in item.body
    assert "抿了一口" in item.body
    assert post_review.pass_ is True
    assert item.quality_json["product_experience_action_surface_cleanups"]


def test_product_experience_product_action_surface_cleanup_removes_sip_for_object_presence():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "使用记录",
            "product_appearance_mode": "产品是日常动作的一部分",
            "product_action_surface": "物件在场",
            "scene_motive_bucket": "早上赶时间",
        },
        title="早上赶时间",
        body="桌上那杯旺玥搁在吐司盘旁边，他路过时顺手端起来抿了一口，又去追袜子。",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    post_review = service._apply_product_action_surface_cleanup(item, review)

    assert "抿了一口" not in item.body
    assert "看了一眼" in item.body
    assert post_review.pass_ is True


def test_product_experience_product_action_surface_cleanup_removes_malformed_drinking_residue():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "使用记录",
            "product_appearance_mode": "产品是日常动作的一部分",
            "product_action_surface": "物件在场",
            "scene_motive_bucket": "早上赶时间",
        },
        title="早上赶时间",
        body="桌上那杯旺玥就搁那儿，最后自己咕咚几口，我还在催出门。孩子边啃面包边自己看了一眼了两口，又自己看了一眼了几口，我喊他再看了一眼，不知道喝没看了一眼。",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    post_review = service._apply_product_action_surface_cleanup(item, review)

    assert "咕咚几口" not in item.body
    assert "看了一眼了两口" not in item.body
    assert "看了一眼了几口" not in item.body
    assert "喊他再看了一眼" not in item.body
    assert "喝没看了一眼" not in item.body
    assert post_review.pass_ is True


def test_product_experience_product_action_surface_cleanup_removes_malformed_object_residue():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "使用记录",
            "product_appearance_mode": "产品是日常动作的一部分",
            "product_action_surface": "物件在场",
            "scene_motive_bucket": "早上赶时间",
        },
        title="沙发边上",
        body="沙发上有昨天没看了一眼的牛奶盒，桌角还放着那杯旺玥。",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    post_review = service._apply_product_action_surface_cleanup(item, review)

    assert "没看了一眼" not in item.body
    assert "昨天没收的牛奶盒" in item.body
    assert post_review.pass_ is True


def test_product_experience_product_action_surface_cleanup_removes_planned_drinking_intent():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "使用记录",
            "product_appearance_mode": "产品是日常动作的一部分",
            "product_action_surface": "物件在场",
            "scene_motive_bucket": "周末在家磨蹭",
            "life_trigger": "在家磨蹭",
        },
        title="又磨蹭了",
        body="周末早上桌上那杯旺玥放着，我喊他喝，他说等一下。晚饭后收拾桌子，顺手把旺玥那罐挪到柜子里，明天早上冲好拿。出门前把罐子挪到包边，怕他路上想起来要喝又找不到。",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    post_review = service._apply_product_action_surface_cleanup(item, review)

    assert "喊他喝" not in item.body
    assert "冲好拿" not in item.body
    assert "想起来要喝" not in item.body
    assert "喊他快点" in item.body
    assert post_review.pass_ is True


def test_product_experience_product_action_surface_cleanup_removes_one_sip_for_move_surface():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "使用记录",
            "product_appearance_mode": "产品是日常动作的一部分",
            "product_action_surface": "妈妈顺手挪放",
            "scene_motive_bucket": "写作业间隙",
        },
        title="作业本旁边那杯",
        body="顺手把旺玥杯子挪到桌角。他头也没抬，写完一题才端过去喝了一口。小家伙自己端着杯子喝了两口又放回去。",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    post_review = service._apply_product_action_surface_cleanup(item, review)

    assert "端过去喝" not in item.body
    assert "端着杯子喝" not in item.body
    assert "看了一眼" in item.body
    assert post_review.pass_ is True


def test_product_experience_usage_record_portable_cleanup_keeps_product_home_surface():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_product_permission_3x10_20260623",
            "post_type": "使用记录",
            "product_appearance_mode": "产品是日常动作的一部分",
            "product_action_surface": "物件在场",
            "scene_motive_bucket": "出门前检查东西",
        },
        title="娃在那边自己穿鞋",
        body="桌上那罐旺玥就那么放着，最后也没顾上收，直接塞进他书包侧兜里了。",
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    post_review = service._apply_usage_record_portable_cleanup(item, review)

    assert "书包侧兜" not in item.body
    assert "留在桌角" in item.body
    assert post_review.pass_ is True


def test_product_experience_phrase_guard_blocks_wangyue_row2_template_and_object_drift():
    review = review_product_experience_phrase(
        title="他说这怎么是牛奶味",
        body=(
            "孩子活动量大以后，我选奶粉会多看保护力和日常营养。"
            "看着桌上那盒旺玥说这怎么是牛奶味，后来正好他喝得挺顺，我就顺手补补。"
            "以前囤的旺玥也拿出来了，奶粉柜里还剩半罐，空奶粉罐还放桌边。"
            "反正日常喝着顺手，日常里顺手就给了。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 2,
            "corpus": "写作规则：围绕孩子普通日常状态来写。",
        },
    )

    assert "wangyue_row2_drinking_action_context" in review.reasons
    assert "孩子活动量大以后" in review.wangyue_row2_drinking_action_hits
    assert "我选奶粉会多看保护力" in review.wangyue_row2_drinking_action_hits
    assert "桌上那盒旺玥" in review.wangyue_row2_drinking_action_hits
    assert "牛奶味" in review.wangyue_row2_drinking_action_hits
    assert "喝得挺顺" in review.wangyue_row2_drinking_action_hits
    assert "顺手补补" in review.wangyue_row2_drinking_action_hits
    assert "以前囤的" in review.wangyue_row2_drinking_action_hits
    assert "奶粉柜" in review.wangyue_row2_drinking_action_hits
    assert "还剩半罐" in review.wangyue_row2_drinking_action_hits
    assert "空奶粉罐" in review.wangyue_row2_drinking_action_hits
    assert "放桌边" in review.wangyue_row2_drinking_action_hits
    assert "日常喝着顺手" in review.wangyue_article_logic_drift_hits
    assert "日常里顺手就给" in review.wangyue_article_logic_drift_hits


def test_product_experience_phrase_guard_blocks_wangyue_portable_direct_brew_variants():
    review = review_product_experience_phrase(
        title="出门随身带一袋",
        body="出门揣两小袋旺玥，玩累了直接冲，挺方便。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 2,
            "corpus": "写作规则：围绕孩子活动量大、日常状态观察来写；旺玥兼顾孩子保护力和眼脑相关营养。",
        },
    )

    assert "wangyue_portable_form_context" in review.reasons
    assert "出门揣" in review.wangyue_portable_form_hits
    assert "玩累了直接冲" in review.wangyue_portable_form_hits
    portable_review = review_product_experience_phrase(
        title="出门前顺手带一罐",
        body="后来家里常备旺玥，出门前顺手带一罐，说是玩完也能接上。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 1,
            "corpus": "写作规则：孩子接触人多，妈妈担心容易中招；旺玥主打支持孩子保护力。",
        },
    )
    assert "wangyue_portable_form_context" in portable_review.reasons
    assert "出门前顺手带一罐" in portable_review.wangyue_portable_form_hits
    cleaned = sanitize_wangyue_context_phrases("出门揣两小袋旺玥，玩累了直接冲，挺方便。")
    assert "小袋" not in cleaned
    assert "直接冲" not in cleaned
    newer_cleaned = sanitize_wangyue_context_phrases("包里光是奶粉和水壶就塞满了，我最烦一罐罐分开带，出门前顺手抓一罐。")
    assert "包里光是奶粉和水壶" not in newer_cleaned
    assert "一罐罐分开带" not in newer_cleaned
    assert "抓一罐" not in newer_cleaned
    latest_cleaned = sanitize_wangyue_context_phrases("后来家里常备旺玥，出门前顺手带一罐。")
    assert "顺手带一罐" not in latest_cleaned


def test_product_experience_phrase_guard_keeps_row2_eye_brain_core_term():
    review = review_product_experience_phrase(
        title="眼脑营养也会看",
        body="我选旺玥时会看眼脑营养和保护力，别的先不夸太满。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 2,
            "corpus": "写作规则：围绕孩子活动量大、日常状态观察来写；旺玥兼顾孩子保护力和眼脑相关营养。",
        },
    )

    assert "wangyue_article_logic_drift_context" not in review.reasons
    assert review.wangyue_article_logic_drift_hits == []


def test_product_experience_phrase_guard_blocks_row2_drinking_action_residue():
    review = review_product_experience_phrase(
        title="活动量大，营养真不能糊弄",
        body=(
            "孩子每天疯跑，平时就放家里当儿童奶粉备着，把家里的旺玥放桌上备着，"
            "饿了渴了自然会去倒。之前没白囤，反正她喝着也不抵触。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 2,
            "corpus": "写作规则：围绕孩子活动量大、日常状态观察来写；旺玥兼顾孩子保护力和眼脑相关营养。",
        },
    )

    assert "wangyue_row2_drinking_action_context" in review.reasons
    assert "放家里当儿童奶粉备着" in review.wangyue_row2_drinking_action_hits
    assert "放桌上备着" in review.wangyue_row2_drinking_action_hits
    assert "饿了渴了自然会去倒" in review.wangyue_row2_drinking_action_hits
    assert "没白囤" in review.wangyue_row2_drinking_action_hits
    assert "喝着也不抵触" not in review.wangyue_row2_drinking_action_hits
    assert review.rewrite_required is True


def test_product_experience_phrase_guard_keeps_drinking_action_residue_scoped_to_row2():
    review = review_product_experience_phrase(
        title="成长营养记录",
        body="孩子每天疯跑，家里常备旺玥，平时在家随手给他冲一杯，反正孩子愿意喝。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 4,
            "corpus": "写作规则：围绕孩子成长阶段营养补充来写。",
        },
    )

    assert "wangyue_row2_drinking_action_context" not in review.reasons
    assert review.wangyue_row2_drinking_action_hits == []


def test_product_experience_phrase_guard_handles_row2_drinking_action_edge_cases():
    review = review_product_experience_phrase(
        title="活动量大这事",
        body=(
            "她问我给娃喝什么奶粉，我顺口说家里选旺玥。"
            "后来我直接递了杯旺玥过去，平时当早餐喝，家里常备着，他自己记得喝。"
            "放学先喝一杯，我家喝的旺玥，包里装的啥一问，翻出来就是旺玥。"
            "回家路上喊累，正好给他补补保护力。"
            "家里会放一罐旺玥，看他有时候想喝点，就当补充营养了。"
            "家里一直放着旺玥，算是给他白天折腾完的补充吧。"
            "我把旺玥递过去让她自己喝，省得天天追着补。"
            "家里多备了旺玥，之前旺玥喝了几个月。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 2,
            "corpus": "写作规则：围绕孩子活动量大、日常状态观察来写；旺玥兼顾孩子保护力和眼脑相关营养。",
        },
    )

    assert "奶粉，我顺口" not in review.wangyue_row2_drinking_action_hits
    assert "直接递了杯旺玥" in review.wangyue_row2_drinking_action_hits
    assert "当早餐喝" in review.wangyue_row2_drinking_action_hits
    assert "家里常备着" in review.wangyue_row2_drinking_action_hits
    assert "自己记得喝" not in review.wangyue_row2_drinking_action_hits
    assert "放学先喝一杯" in review.wangyue_row2_drinking_action_hits
    assert "我家喝的旺玥" not in review.wangyue_row2_drinking_action_hits
    assert "包里装的啥" in review.wangyue_row2_drinking_action_hits
    assert "翻出来就是旺玥" in review.wangyue_row2_drinking_action_hits
    assert "补补保护力" in review.wangyue_row2_drinking_action_hits
    assert "想喝点" in review.wangyue_row2_drinking_action_hits
    assert "白天折腾完的补充" in review.wangyue_row2_drinking_action_hits
    assert "把旺玥递过去让她自己喝" in review.wangyue_row2_drinking_action_hits
    assert "天天追着补" in review.wangyue_row2_drinking_action_hits
    assert "多备了旺玥" in review.wangyue_row2_drinking_action_hits
    assert "旺玥喝了几个月" in review.wangyue_row2_drinking_action_hits
    assert "wangyue_row2_drinking_action_context" in review.reasons


def test_product_experience_phrase_guard_allows_plain_wangyue_drinking_mention_for_row2():
    review = review_product_experience_phrase(
        title="她衣服兜里那张纸条到底哪来的",
        body="前阵子开始给她喝皇家美素佳儿旺玥，主要是看中眼脑营养这块。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 2,
            "corpus": "写作规则：围绕孩子普通日常状态来写。",
        },
    )

    assert "wangyue_row2_drinking_action_context" not in review.reasons
    assert review.wangyue_row2_drinking_action_hits == []


def test_product_experience_phrase_guard_blocks_child_self_scooping_formula():
    review = review_product_experience_phrase(
        title="娃放学回来就来翻柜子",
        body="接娃回来，书包一扔就去翻零食柜。我以为他要拿饼干，结果摸出那罐旺玥，自己舀了两勺冲水喝。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 2,
            "corpus": "写作规则：围绕孩子活动量大、日常状态观察来写；旺玥兼顾孩子保护力和眼脑相关营养。",
        },
    )

    assert "child_self_brewing_formula" in review.reasons
    assert "自己舀了两勺冲水喝" in review.child_self_brewing_hits
    assert review.rewrite_required is True


def test_product_experience_phrase_guard_blocks_child_handling_formula_can():
    review = review_product_experience_phrase(
        title="白天电量用不完",
        body=(
            "家里大人聊天，说这孩子精神头比大人都足。我索性把皇家美素佳儿旺玥放在餐边柜，"
            "晚上洗完澡自己递过来让我开。她扭头就翻柜子，找出一罐旺玥，抱过来往我手里塞。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 2,
            "corpus": "写作规则：围绕孩子活动量大、日常状态观察来写；旺玥兼顾孩子保护力和眼脑相关营养。",
        },
    )

    assert "child_self_brewing_formula" in review.reasons
    assert "自己递过来让我开" in review.child_self_brewing_hits
    assert "找出一罐旺玥，抱过来往我手里塞" in review.child_self_brewing_hits
    assert review.rewrite_required is True


def test_product_experience_phrase_guard_keeps_wangyue_logic_drift_scoped_to_wangyue():
    review = review_product_experience_phrase(
        title="家里口粮快没了",
        body="家里口粮快没了，顺手放购物车。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "other_article_business_rules",
            "corpus": "普通帖子规则。",
        },
    )

    assert "wangyue_article_logic_drift_context" not in review.reasons
    assert review.wangyue_article_logic_drift_hits == []


def test_sanitize_wangyue_context_phrases_removes_logic_drift_terms():
    title = sanitize_wangyue_context_phrases("冲出来奶香清淡，娃不挑")
    body = sanitize_wangyue_context_phrases(
        "给自己换了个大路灯，给娃挑口粮时顺手直接下单了。主要看它护眼和保护力都搭得上，别写用眼过渡。冲出来奶香清淡，孩子眼睛还亮亮，脸色都亮堂。"
    )

    assert title == "选奶粉这事我记一下"
    assert "口粮" not in body
    assert "直接下单" not in body
    assert "大路灯" not in body
    assert "护眼" not in body
    assert "用眼过渡" not in body
    assert "眼睛还亮亮" not in body
    assert "冲出来" not in body
    assert "奶香" not in body
    assert "脸色" not in body
    assert "眼脑营养" in body


def test_product_experience_phrase_guard_blocks_row4_drinking_acceptance_and_one_can_claims():
    review = review_product_experience_phrase(
        title="她喝旺玥那叫一个投入",
        body="旺玥一罐搞定成长营养，孩子喝得顺口，还主动说要喝奶奶。口感娃也挺爱喝，孩子喝着接受，喝下来挺对路，平时喝着挺实在，孩子每天喝得自然，也喝得习惯。先喝着观察看看后续效果，冲出来也没怪味，娃肯喝、不抗拒，开封时奶香淡淡的。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 4,
            "corpus": "写作规则：围绕给孩子选择皇家美素佳儿旺玥儿童奶粉来写，理由是补充营养、支持成长；正文40-130字。",
        },
    )

    assert "wangyue_growth_nutrition_drift_context" in review.reasons
    assert "一罐搞定" in review.wangyue_growth_nutrition_drift_hits
    assert "喝得顺口" in review.wangyue_growth_nutrition_drift_hits
    assert "主动说要喝奶" in review.wangyue_growth_nutrition_drift_hits
    assert "口感娃也挺爱喝" in review.wangyue_growth_nutrition_drift_hits
    assert "孩子喝着接受" in review.wangyue_growth_nutrition_drift_hits
    assert "喝下来挺对路" in review.wangyue_growth_nutrition_drift_hits
    assert "平时喝着" in review.wangyue_growth_nutrition_drift_hits
    assert "喝着挺实在" in review.wangyue_growth_nutrition_drift_hits
    assert "每天喝得自然" in review.wangyue_growth_nutrition_drift_hits
    assert "喝得习惯" in review.wangyue_growth_nutrition_drift_hits
    assert "先喝着观察" in review.wangyue_growth_nutrition_drift_hits
    assert "后续效果" in review.wangyue_growth_nutrition_drift_hits
    assert "冲出来" in review.wangyue_growth_nutrition_drift_hits
    assert "怪味" in review.wangyue_growth_nutrition_drift_hits
    assert "肯喝" in review.wangyue_growth_nutrition_drift_hits
    assert "不抗拒" in review.wangyue_growth_nutrition_drift_hits
    assert "开封" in review.wangyue_growth_nutrition_drift_hits
    assert "奶香" in review.wangyue_growth_nutrition_drift_hits
    assert "那叫一个投入" in review.wangyue_growth_nutrition_drift_hits


def test_product_experience_phrase_guard_blocks_row4_state_and_drinking_residue():
    review = review_product_experience_phrase(
        title="空罐才想起来",
        body="小孩三岁后每天喝奶就够，早晚要喝，每天喝上。配料里有乳铁蛋白、DHA、ARA和活性蛋白，支持保护力，也给大脑成长加把劲。跑跑跳跳不累，放学还能蹦跶半天，活力满满地跑来跑去，补补成长力，成长有底，成长不掉队。试了段时间，状态还行，囤货时也看了微量元素，跑几步就喊累时才开始喝旺玥，图个方便。我甩了旺玥的链接，还想囤几罐继续买这个。顺手带了一罐，孩子把罐子放回包里，说留着明天喝，主要看眼睛和身体状态。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 4,
            "corpus": "写作规则：围绕给孩子选择皇家美素佳儿旺玥儿童奶粉来写，理由是补充营养、支持成长；正文40-130字。",
        },
    )

    assert "wangyue_growth_nutrition_drift_context" in review.reasons
    assert "每天喝奶" in review.wangyue_growth_nutrition_drift_hits
    assert "早晚要喝" in review.wangyue_growth_nutrition_drift_hits
    assert "每天喝上" in review.wangyue_growth_nutrition_drift_hits
    assert "配料" in review.wangyue_growth_nutrition_drift_hits
    assert "乳铁蛋白" in review.wangyue_growth_nutrition_drift_hits
    assert "DHA" in review.wangyue_growth_nutrition_drift_hits
    assert "ARA" in review.wangyue_growth_nutrition_drift_hits
    assert "活性蛋白" in review.wangyue_growth_nutrition_drift_hits
    assert "支持保护力" in review.wangyue_growth_nutrition_drift_hits
    assert "大脑成长" in review.wangyue_growth_nutrition_drift_hits
    assert "跑跑跳跳" in review.wangyue_growth_nutrition_drift_hits
    assert "蹦跶" in review.wangyue_growth_nutrition_drift_hits
    assert "活力满满" in review.wangyue_growth_nutrition_drift_hits
    assert "跑来跑去" in review.wangyue_growth_nutrition_drift_hits
    assert "成长力" in review.wangyue_growth_nutrition_drift_hits
    assert "成长有底" in review.wangyue_growth_nutrition_drift_hits
    assert "成长不掉队" in review.wangyue_growth_nutrition_drift_hits
    assert "空罐" in review.wangyue_growth_nutrition_drift_hits
    assert "试了段时间" in review.wangyue_growth_nutrition_drift_hits
    assert "囤货" in review.wangyue_growth_nutrition_drift_hits
    assert "微量元素" in review.wangyue_growth_nutrition_drift_hits
    assert "跑几步就喊累" in review.wangyue_growth_nutrition_drift_hits
    assert "开始喝旺玥" in review.wangyue_growth_nutrition_drift_hits
    assert "图个方便" in review.wangyue_growth_nutrition_drift_hits
    assert "甩了旺玥的链接" in review.wangyue_growth_nutrition_drift_hits
    assert "囤几罐" in review.wangyue_growth_nutrition_drift_hits
    assert "继续买这个" in review.wangyue_growth_nutrition_drift_hits
    assert "带了一罐" in review.wangyue_growth_nutrition_drift_hits
    assert "罐子放回包" in review.wangyue_growth_nutrition_drift_hits
    assert "留着明天喝" in review.wangyue_growth_nutrition_drift_hits
    assert "眼睛和身体状态" in review.wangyue_growth_nutrition_drift_hits


def test_product_experience_phrase_guard_blocks_row4_shopping_process_residue():
    review = review_product_experience_phrase(
        title="挑来挑去还是旺玥合适",
        body="给孩子选奶粉怕踩坑，看了半天又看来看去，最后还是觉得旺玥合适。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 4,
            "corpus": "写作规则：围绕给孩子选择皇家美素佳儿旺玥儿童奶粉来写，理由是补充营养、支持成长；正文40-130字。",
        },
    )

    assert "wangyue_growth_nutrition_drift_context" in review.reasons
    assert "挑来挑去" in review.wangyue_growth_nutrition_drift_hits
    assert "怕踩坑" in review.wangyue_growth_nutrition_drift_hits
    assert "看了半天" in review.wangyue_growth_nutrition_drift_hits
    assert "看来看去" in review.wangyue_growth_nutrition_drift_hits


def test_product_experience_phrase_guard_blocks_row4_supplement_proof_residue():
    review = review_product_experience_phrase(
        title="选奶这事别嫌麻烦就行",
        body="用这罐把该补的一次补到位，至于效果啥的先喝喝看。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 4,
            "corpus": "写作规则：围绕给孩子选择皇家美素佳儿旺玥儿童奶粉来写，理由是补充营养、支持成长；正文40-130字。",
        },
    )

    assert "wangyue_growth_nutrition_drift_context" in review.reasons
    assert "该补的" in review.wangyue_growth_nutrition_drift_hits
    assert "一次补到位" in review.wangyue_growth_nutrition_drift_hits
    assert "效果啥" in review.wangyue_growth_nutrition_drift_hits
    assert "先喝喝看" in review.wangyue_growth_nutrition_drift_hits


def test_product_experience_phrase_guard_blocks_row4_brewing_and_powder_residue():
    review = review_product_experience_phrase(
        title="这罐奶粉真没白囤",
        body="给娃泡奶差点手忙脚乱，旺玥随手就能冲，粉质细，冲开没结块，之后每天当奶喝。他天天自己捧着罐子看，也不催我泡。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 4,
            "corpus": "写作规则：围绕给孩子选择皇家美素佳儿旺玥儿童奶粉来写，理由是补充营养、支持成长；正文40-130字。",
        },
    )

    assert "wangyue_growth_nutrition_drift_context" in review.reasons
    assert "泡奶" in review.wangyue_growth_nutrition_drift_hits
    assert "随手就能冲" in review.wangyue_growth_nutrition_drift_hits
    assert "粉质" in review.wangyue_growth_nutrition_drift_hits
    assert "冲开" in review.wangyue_growth_nutrition_drift_hits
    assert "没结块" in review.wangyue_growth_nutrition_drift_hits
    assert "每天当奶喝" in review.wangyue_growth_nutrition_drift_hits
    assert "没白囤" in review.wangyue_growth_nutrition_drift_hits
    assert "捧着罐子" in review.wangyue_growth_nutrition_drift_hits
    assert "催我泡" in review.wangyue_growth_nutrition_drift_hits


def test_fallback_wangyue_growth_nutrition_body_uses_item_route_prompt():
    item = ContentBatchItem(
        item_no=4,
        plan_json={
            "real_user_pool": {
                "prompt_text_by_layer": {
                    "route": ["朋友问我为什么看旺玥，我当时就是一句话带过。"]
                }
            }
        },
    )

    body = _fallback_wangyue_growth_nutrition_body(item)

    assert body.startswith("朋友问我为什么看旺玥")
    assert "选旺玥的理由很简单" not in body
    assert "想把日常营养这块补上" not in body
    assert "营养" in body
    assert "成长阶段需要" not in body


def test_product_experience_rewrite_input_mentions_wangyue_growth_nutrition_drift():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    plan = {
        "rule_type": "business_rule",
        "asset_key": "wangyue_article_business_rules",
        "source_row_no": 4,
        "corpus": "写作规则：围绕给孩子选择皇家美素佳儿旺玥儿童奶粉来写，理由是补充营养、支持成长；正文40-130字。",
    }
    review = review_product_experience_phrase(
        title="这罐还真选对了",
        body="孩子饭量上来了，身高体重曲线也好看，每天冲一杯就一步搞定，成长营养这块不用补这补那。",
        plan=plan,
    )
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json=plan,
        title="这罐还真选对了",
        body="孩子饭量上来了，身高体重曲线也好看，每天冲一杯就一步搞定，成长营养这块不用补这补那。",
    )

    payload = service._product_experience_phrase_rewrite_input(item, review)
    instructions = "\n".join(payload["rewrite_instructions"])

    assert "旺玥营养/成长规则漂移" in instructions
    assert "补充营养、支持成长" in instructions
    assert "不要把问题内容改成放学、户外、书包、杯子放置" in instructions


def test_product_experience_rewrite_input_mentions_product_effect_proof_chain():
    service = ContentBatchExecutionService(None, callback_base_url="http://testserver", session_factory=lambda: None)
    plan = {
        "rule_type": "business_rule",
        "asset_key": "wangyue_painpoint_selling_posttype_matrix_v29_20260624",
        "post_type": "使用反馈/继续观察",
        "ugc_post_type": "使用反馈型",
        "corpus": "0705旺玥活动",
    }
    body = "我给他冲一杯旺玥，孩子喝完就去玩了，状态看着稳一点，我心里也踏实些。"
    review = review_product_experience_phrase(title="放学后这杯", body=body, plan=plan)
    item = ContentBatchItem(
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json=plan,
        title="放学后这杯",
        body=body,
    )

    payload = service._product_experience_phrase_rewrite_input(item, review)
    instructions = "\n".join(payload["rewrite_instructions"])

    assert "产品动作和效果证明链路过满" in instructions
    assert "只保留一个产品关系" in instructions
    assert "不要把它们连成“怎么喝/孩子接受/状态变化/妈妈踏实”的完整闭环" in instructions


def test_wangyue_context_cleanup_leaves_age_stage_for_llm_rewrite():
    cleaned = sanitize_wangyue_context_phrases("从断奶开始就一直在纠结选哪个儿童奶粉。")

    assert cleaned == "从断奶开始就一直在纠结选哪个儿童奶粉"


def test_wangyue_context_cleanup_does_not_make_age_stage_residual_sentence():
    cleaned = sanitize_wangyue_context_phrases("旺玥从一岁多就开始喝。")

    assert cleaned == "旺玥从一岁多就开始喝"
    assert "旺玥从孩子就开始喝" not in cleaned


def test_wangyue_context_cleanup_leaves_two_year_old_context_for_llm_rewrite():
    cleaned = sanitize_wangyue_context_phrases("两岁后开始接触小朋友多的地方。")

    assert cleaned == "两岁后开始接触小朋友多的地方"


def test_product_experience_common_ai_closure_cleanup_removes_generic_tail():
    text = "老母亲家里一直喝旺玥，孩子状态也还行。希望能一直这样省心，继续观察看看，先这样喂着吧。继续观察吧，先这样喝着看看。欢迎留言聊聊。"

    cleaned = sanitize_common_ai_closure(text)

    assert cleaned == "我家里一直喝旺玥，孩子状态也还行。希望后面少折腾点"
    assert "继续观察看看" not in cleaned
    assert "继续观察吧" not in cleaned
    assert "先这样喝着看看" not in cleaned
    assert "先这样喂着吧" not in cleaned
    assert "欢迎留言" not in cleaned
    assert "老母亲" not in cleaned


def test_product_experience_odd_phrase_cleanup_replaces_known_weird_phrases():
    text = "这杯奶一杯下去又活过来了，体格挺打底，也没有动不动就掉状态，半电量永远满格，一杯搞定保护力和眼脑营养，带出门消停了不少，冲好丢过去，打开湿湿的？效果。"

    cleaned = sanitize_odd_product_experience_phrases(text)

    assert cleaned == "这杯奶休息一会儿状态能缓过来，体格看着挺扎实，状态也还可以，精力一直挺足，保护力和眼脑营养这两块我都会看，带出门状态还可以，冲好递过去"
    review = review_product_experience_phrase(
        title="旺玥记录",
        body="孩子最近没有动不动就掉状态，体格挺打底。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )
    assert review.odd_phrase_hits == ["没有动不动就掉状态", "体格挺打底"]
    assert "odd_product_experience_phrase" in review.reasons
    assert review.rewrite_required is True
    odd_review = review_product_experience_phrase(
        title="旺玥记录",
        body="有没有喝皇家旺玥的，打开湿湿的？",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )
    assert odd_review.odd_phrase_hits == ["打开湿湿的？"]


def test_product_experience_odd_phrase_cleanup_removes_body_label_prefix():
    assert sanitize_odd_product_experience_phrases("正文：童童吃饭还行。") == "童童吃饭还行"
    assert sanitize_odd_product_experience_phrases("正文开头她攥着一团皱巴巴的纸片。") == "她攥着一团皱巴巴的纸片"
    assert sanitize_odd_product_experience_phrases("家里那罐皇家美素佳儿旺玥。") == "皇家美素佳儿旺玥"
    assert sanitize_odd_product_experience_phrases("孩子上了上学以后。") == "孩子上学以后"
    assert sanitize_odd_product_experience_phrases("孩子上了上学后。") == "孩子上学后"
    assert sanitize_odd_product_experience_phrases("正好家里有皇家美素佳儿旺玥。") == "正好家里有皇家美素佳儿旺玥"
    assert "你们娃也会这样吗" not in sanitize_odd_product_experience_phrases("顺手补补眼脑营养，你们娃也会这样吗？")


def test_product_experience_odd_phrase_cleanup_replaces_brain_emoji():
    text = "每天两杯营养基础打扎实了，真心觉得对🧠的保护也要看。"

    cleaned = sanitize_odd_product_experience_phrases(text)

    assert cleaned == "每天两杯营养基础打扎实了，真心觉得眼脑营养也要看"
    review = review_product_experience_phrase(
        title="旺玥记录",
        body=text,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )
    assert "对🧠的保护" in review.odd_phrase_hits
    assert "odd_product_experience_phrase" in review.reasons


def test_product_experience_odd_phrase_cleanup_removes_zero_width_emoji_marks():
    text = "上幼儿园后流鼻涕的频率快赶上喝水次数了😮\u200d💨"

    cleaned = sanitize_odd_product_experience_phrases(text)

    assert "\u200d" not in cleaned
    assert "\ufe0f" not in cleaned
    assert cleaned == "上幼儿园后流鼻涕的频率快赶上喝水次数了😮💨"


def test_product_experience_odd_phrase_cleanup_removes_wet_dangling_fragment():
    text = "最近给他换到旺玥，开罐的时候勺子上带着点湿气，我反而。孩子活动量大。"

    cleaned = sanitize_odd_product_experience_phrases(text)

    assert "湿气" not in cleaned
    assert "我反而。" not in cleaned


def test_product_experience_odd_phrase_cleanup_removes_wet_process_claim():
    text = "开盖那会儿有点湿，查了是工艺问题。刚打开罐子湿的，不知道正常不？除了贵，别的真省心。"

    cleaned = sanitize_odd_product_experience_phrases(text)

    assert "有点湿" not in cleaned
    assert "刚打开罐子湿的" not in cleaned
    assert "工艺问题" not in cleaned


def test_product_experience_odd_phrase_cleanup_removes_wet_can_claim_variant():
    text = "打开奶粉罐湿的感觉，还以为受潮了，查了说正常。除了贵，娃喝得挺顺。"

    cleaned = sanitize_odd_product_experience_phrases(text)

    assert cleaned == "除了贵，娃喝得挺顺"
    assert "湿" not in cleaned
    assert "受潮" not in cleaned


def test_product_experience_odd_phrase_cleanup_removes_wet_process_claim_variant():
    text = "开罐那会还湿湿的，问了才知道是工艺原因，喝着没问题。简单分享，这罐先喝着再说。"

    cleaned = sanitize_odd_product_experience_phrases(text)

    assert cleaned == "简单分享，这罐先喝着再说"
    assert "湿" not in cleaned
    assert "工艺原因" not in cleaned


def test_product_experience_odd_phrase_cleanup_removes_dangling_fragments():
    text = "最近季的小担忧，先喝起来看看。我这我算是先着吧"

    cleaned = sanitize_odd_product_experience_phrases(text)

    assert cleaned == "最近的小担忧，先喝起来看看"
    assert sanitize_odd_product_experience_phrases("我这我天天跟着跑。") == "我天天跟着跑"
    assert (
        sanitize_odd_product_experience_phrases("有些变化不敢全归到奶上，但日常喝着我会")
        == "有些变化不敢全归到奶上"
    )
    assert (
        sanitize_odd_product_experience_phrases("没见她跟着小朋友一起中招，日常喝着我会")
        == "没见她跟着小朋友一起中招，日常喝着我会继续观察"
    )
    assert (
        sanitize_odd_product_experience_phrases("有些变化不敢全归到奶上，但喝着我就")
        == "有些变化不敢全归到奶上"
    )
    assert (
        sanitize_odd_product_experience_phrases("日常喝着我会继续观察")
        == "日常喝着我会继续观察"
    )
    review = review_product_experience_phrase(
        title="最近季的小担忧",
        body="希望少中招，效果",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )
    assert "odd_product_experience_phrase" in review.reasons


def test_product_experience_odd_phrase_cleanup_replaces_wangyue_forbidden_product_term():
    text = "挑食宝宝的宝妈发现旺玥营养挺全的，自护力、内护力、底气和抵抗力都提到了，换了旺玥后体质明显比同龄人稳，流感多的时候羊奶粉钱也省了。"

    cleaned = sanitize_odd_product_experience_phrases(text)

    assert cleaned == "挑食娃的妈妈发现旺玥营养挺全的，保护力都提到了，换了旺玥后看着比同龄人结实，流感多的时候这罐奶粉钱也省了"
    review = review_product_experience_phrase(
        title="旺玥记录",
        body=text,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )
    assert set(review.odd_phrase_hits) == {"挑食宝宝", "宝妈", "体质明显比同龄人稳", "自护力", "内护力", "底气", "抵抗力", "流感多的时候", "羊奶粉钱"}
    assert "odd_product_experience_phrase" in review.reasons
    assert review.rewrite_required is True


def test_product_experience_odd_phrase_cleanup_handles_new_wangyue_artifacts():
    text = "出门前检查水壶和奶粉奶粉罐，娃吸管一插自己抱着喝，没白做功課。我俩都行。"

    cleaned = sanitize_odd_product_experience_phrases(text)

    assert cleaned == "出门前检查水壶和奶粉罐，娃自己拿着杯子喝，没白做功课。孩子喝着还行"
    review = review_product_experience_phrase(
        title="旺玥记录",
        body=text,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )
    assert set(review.odd_phrase_hits) == {"吸管一插自己抱着喝", "奶粉奶粉罐", "没白做功課", "我俩都行"}
    assert "odd_product_experience_phrase" in review.reasons


def test_product_experience_odd_phrase_cleanup_handles_wangyue_batch_claim_artifacts():
    text = "一摸后背，居然有肉了，肉疼的那种扎实感。关键是还有乳铁蛋白，免疫力也顺手抓了。"

    cleaned = sanitize_odd_product_experience_phrases(text)

    assert cleaned == "一摸后背，居然有肉了，摸着挺扎实。关键是还有乳铁蛋白，保护力这块也看了"
    review = review_product_experience_phrase(
        title="旺玥记录",
        body=text,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )
    assert set(review.odd_phrase_hits) == {"肉疼的那种扎实感", "免疫力也顺手抓了"}
    assert "odd_product_experience_phrase" in review.reasons


def test_product_experience_odd_phrase_cleanup_handles_wangyue_low_age_and_professional_artifacts():
    text = "营养师朋友说可以日常一杯当辅食，我就给旺玥加进日常。"

    cleaned = sanitize_odd_product_experience_phrases(text)

    assert cleaned == "朋友说可以日常一杯当补充，我就给旺玥加进日常"
    review = review_product_experience_phrase(
        title="旺玥记录",
        body=text,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )
    assert set(review.odd_phrase_hits) == {"日常一杯当辅食", "营养师朋友"}
    assert "odd_product_experience_phrase" in review.reasons


def test_product_experience_baby_milk_action_cleanup_handles_can_fetching_variants():
    text = "现在自己搬小凳子去拿奶粉罐，嘴里说妈妈泡奶泡奶。她还会自己跑去把旺玥罐子抱过来，昨天还自己抱出奶粉罐。"

    cleaned = sanitize_baby_milk_action_phrases(text)

    assert cleaned == "现在等我冲奶，嘴里说想喝奶。她还会提醒我冲奶，昨天还提醒我冲奶"
    review = review_product_experience_phrase(
        title="旺玥记录",
        body=text,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )
    assert set(review.child_self_brewing_hits) == {"自己搬小凳子去拿奶粉罐", "自己跑去把旺玥罐子抱过来", "自己抱出奶粉罐"}
    assert "child_self_brewing_formula" in review.reasons


def test_product_experience_wangyue_cleanup_replaces_wrong_product_name():
    text = "给他喝旺玥小安素那会儿就是看中保护力。"

    cleaned = sanitize_wangyue_context_phrases(text)

    assert cleaned == "给他喝旺玥儿童奶粉那会儿就是看中保护力"
    review = review_product_experience_phrase(
        title="旺玥记录",
        body=text,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )
    assert review.wangyue_wrong_brand_hits == ["小安素"]
    assert "wangyue_wrong_brand" in review.reasons


def test_product_experience_adult_tasting_cleanup_removes_taste_trial_variant():
    text = "到手尝了口，不甜腻，娃倒没嫌弃。"

    cleaned = sanitize_adult_self_drinking_phrases(text)

    assert cleaned == "娃倒没嫌弃"
    review = review_product_experience_phrase(
        title="旺玥记录",
        body=text,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )
    assert review.adult_self_drinking_hits == ["尝了口，不甜腻", "到手尝了口"]
    assert "adult_self_drinking_child_formula" in review.reasons


def test_product_experience_adult_tasting_cleanup_removes_sneaky_tasted_variant():
    text = "我自己偷偷尝过，确实不腥，难怪他肯喝。"

    cleaned = sanitize_adult_self_drinking_phrases(text)

    assert cleaned == "难怪他肯喝"
    review = review_product_experience_phrase(
        title="旺玥记录",
        body=text,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )
    assert review.adult_self_drinking_hits == ["我自己偷偷尝过"]
    assert "adult_self_drinking_child_formula" in review.reasons


def test_product_experience_adult_tasting_cleanup_removes_plain_self_tasted_variant():
    text = "我自己尝过，娃喝得挺顺。"

    cleaned = sanitize_adult_self_drinking_phrases(text)

    assert cleaned == "娃喝得挺顺"
    review = review_product_experience_phrase(
        title="旺玥记录",
        body=text,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )
    assert review.adult_self_drinking_hits == ["我自己尝过"]
    assert "adult_self_drinking_child_formula" in review.reasons


def test_product_experience_adult_tasting_cleanup_removes_self_tasted_one_sip_variant():
    text = "味道嘛，我自己尝了一口，奶味足，不甜腻。"

    cleaned = sanitize_adult_self_drinking_phrases(text)

    assert cleaned == "味道嘛，奶味足，不甜腻"
    review = review_product_experience_phrase(
        title="旺玥记录",
        body=text,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )
    assert review.adult_self_drinking_hits == ["我自己尝了一口"]
    assert "adult_self_drinking_child_formula" in review.reasons


def test_wangyue_title_fallback_prefers_body_clause_before_synthetic_examples():
    item = ContentBatchItem(
        id=1,
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "asset_key": "wangyue_article_business_rules",
            "synthetic_title_examples": ["旺玥", "这罐还在喝"],
        },
        title="皇家美素佳儿旺玥",
        body="孩子奶粉还没定，今天又看了半天。我给他选儿童奶粉时会看保护力。",
    )

    title = _fallback_title_for_item(item, used_titles=set(), history_titles=set())

    assert title in {"孩子奶粉还没定", "今天又看了半天"}


def test_wangyue_title_fallback_ranks_human_question_above_product_summary():
    item = ContentBatchItem(
        id=1,
        batch_id=1,
        item_no=1,
        status="generated",
        plan_json={
            "asset_key": "wangyue_article_business_rules",
            "synthetic_title_examples": ["这罐奶粉除了价格，营养确实到位", "旺玥"],
        },
        title="皇家美素佳儿旺玥一罐搞定",
        body="这罐奶粉除了价格，营养确实到位。有没有在喝这款的呀。",
    )

    title = _fallback_title_for_item(item, used_titles=set(), history_titles=set())

    assert title == "有没有在喝这款的呀"


def test_wangyue_body_title_candidates_skip_awkward_explanation_sentences():
    candidates = _body_title_candidates("比喻不恰当的话还请见谅。孩子奶粉还没定，今天又看了半天。")

    assert "比喻不恰当的话还请见谅" not in candidates
    assert "孩子奶粉还没定" in candidates


def test_wangyue_body_title_candidates_skip_fragment_and_formula_details():
    candidates = _body_title_candidates(
        "喝儿童成长奶粉的话，我会先看孩子接不接受。"
        "开罐旺玥那天发现粉质比想象中细。"
        "可以看看罐身，5种HMO，选奶就看它。"
        "孩子愿意喝，我也少操心。"
        "他们班最近班里请假停课了。"
    )

    assert "喝儿童成长奶粉的话" not in candidates
    assert "他们班最近班里请假停课了" not in candidates
    assert "开罐旺玥那天发现粉质比想象中细" not in candidates
    assert "可以看看罐身" not in candidates
    assert "5种HMO，选奶就看它" not in candidates
    assert "我会先看孩子接不接受" not in candidates
    assert "孩子愿意喝，我也少操心" in candidates


def test_wangyue_title_guard_blocks_marketing_claim_title_patterns():
    bad_titles = [
        "一罐奶粉解决成长营养问题",
        "30多种营养，真没白看成分表",
        "乳铁蛋白加持，娃少跑医院值了",
        "儿童成长奶粉，保护力有门道",
        "5种HMO拉满保护力",
        "保护力跟上没？眼脑营养够不够？当妈后翻遍成分表才放心。",
        "儿童奶粉选到头秃，这次终于闭眼入",
        "儿童奶粉怎么选，抄作业版来了",
        "P磷脂酰丝氨酸S+DHA，这搭配我服气",
        "幼儿园挑食娃的救星",
        "选奶不踩坑",
        "营养超全面 连我都没想到",
        "挖到一款营养超全的儿童奶粉",
        "终于不用再挑儿童奶粉了",
        "5种HMO，选奶就看它",
        "乳铁蛋白这块，旺玥确实没输过",
        "乳铁蛋白含量，真不是智商税",
        "皇家美素佳儿旺玥，我家娃的补给站",
        "皇家美素佳儿旺玥，懒妈选奶实录",
    ]

    for title in bad_titles:
        assert "marketing_claim_title_pattern" in _title_guard_reasons(title, set())

    assert _title_guard_reasons("有喝旺玥的吗", set()) == []


def test_wangyue_title_guard_blocks_forbidden_template_title_phrases():
    reasons = _title_guard_reasons("给娃选奶粉的真实体验", set())

    assert "forbidden_title_phrase:真实体验" in reasons
    assert "forbidden_title_phrase:不用纠结" in _title_guard_reasons("终于不用纠结了", set())


def test_wangyue_title_guard_blocks_low_natural_product_summary_title():
    reasons = _title_guard_reasons("这罐奶粉除了价格，营养确实到位", set())

    assert "low_natural_title_score" in reasons


def test_wangyue_title_guard_blocks_awkward_title_patterns():
    bad_titles = [
        "儿童营养的全面考量",
        "比喻不恰当的话还请见谅",
        "居然是因为这个",
        "挑食娃也有最近",
        "开头直接选奶",
        "旺玥",
        "带娃出门，包里就多了这罐",
        "带孩子出门的包里都装了什么",
        "娃自己蹲地上摸了半天罐子",
        "总算搞明白旺玥好在哪",
        "旺玥，孩子上学后保护力观察",
        "给孩子喝旺玥的第三个原因",
        "今天又被奶粉拿捏",
        "幼儿园小班娃，这罐奶粉救了我",
        "从内到外的营养，这罐奶真给力",
        "旺玥，我的选择",
        "幼儿园的咳嗽季，我换了奶粉",
        "选儿童奶粉我只看脑子这块",
        "现在每天泡奶",
        "正文里有个小观察一直想说",
        "旺玥开罐湿湿的，别人也这样吗",
        "开罐发现是湿的，正常吗？",
        "主要看它保护力和眼脑营养都照顾到了",
        "幼儿园一这阵就中招保护力差是真发愁",
        "喝儿童成长奶粉的话",
        "保护力差的话特别容易中招",
        "换奶粉的观察记录",
        "又是开盖即饮的日常啊",
        "聪明眼脑营养真的太卷了",
        "开罐记录一下",
        "旺玥成分里这个还挺让人心动的",
        "开罐记录 皇家美素佳儿旺玥",
        "嘴巴严实了，我还是继续喝旺玥吧",
        "这罐奶粉是我先递给孩子喝一口",
        "居然被这罐奶粉治住了",
        "我家娃最近饭量上来了，是奶粉的功劳吗",
        "挑个奶粉比挑老公还难",
        "今天真是出奇地没怎么请假",
        "他们班班里请假停课了",
        "他们班最近班里请假停课了",
        "我那时候也是纠结了一阵",
        "尤其看她户外跑跳回来小脸通红",
        "价格差也不算大",
        "先继续喝着吧",
        "省得我天天纠结哪样没补够",
        "旺玥这两样都有",
        "给孩子喝了一段时间",
    ]

    for title in bad_titles:
        assert "awkward_title_pattern" in _title_guard_reasons(title, set())

    assert _title_guard_reasons("孩子奶粉还没定", set()) == []
    assert _title_guard_reasons("最近还在喝旺玥", set()) == []
    assert _title_guard_reasons("三岁后喝什么", set()) == []
    assert _title_guard_reasons("又补了两罐旺玥", set()) == []
    assert _title_guard_reasons("皇家旺玥和4段如何选？", set()) == []
    assert _title_guard_reasons("接娃路上聊到请假", set()) == []
    assert _title_guard_reasons("你家请假多不多😂", set()) == []
    assert _title_guard_reasons("最近没怎么请假", set()) == []


@pytest.mark.asyncio
async def test_batch_execution_marks_overcomplete_decision_chain_without_rewrite():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    reviewer = FakeProductExperienceLLMReviewer(
        [
            ProductExperienceLLMReview(
                pass_=False,
                rewrite_required=True,
                severity="rewrite",
                issues=[
                    ProductExperienceLLMIssue(
                        code="overcomplete_decision_chain",
                        evidence="吃饭不稳定/长期营养补充/孩子也接受/续上/保底",
                        reason="复购帖重新补全了问题、依据、接受度和安心收口",
                        rewrite_direction="保留补货和一个日常营养补充理由，删除接受度和保底收口",
                    )
                ],
                product_appearance_naturalness=2,
                decision_chain_fit=1,
                product_value_strength=4,
                human_realness=2,
                overall_reason="复购帖链路太完整",
            ),
            ProductExperienceLLMReview(pass_=True, rewrite_required=False, severity="pass"),
        ]
    )

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="mock://maga-worker/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_llm_quality",
            asset_key="wangyue_painpoint_selling_posttype_matrix_v32_20260624",
            product_topic="旺玥痛点卖点",
            target_audience="妈妈",
            style="真实UGC",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        session.add(
            ContentBatchItem(
                batch_id=job.id,
                item_no=1,
                status="planned",
                plan_json={
                    "rule_type": "business_rule",
                    "asset_key": "wangyue_painpoint_selling_posttype_matrix_v32_20260624",
                    "post_type": "复购/长期使用",
                    "ugc_post_type": "复购/长期使用型",
                    "corpus": "0705旺玥活动",
                },
            )
        )
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceLLMQualityRewriteClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
            product_experience_llm_reviewer=reviewer,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (
            await session.execute(select(ContentBatchItem).where(ContentBatchItem.batch_id == job.id))
        ).scalar_one()
        rewrite_stages = (
            await session.execute(
                select(ContentAgentStageCall).where(
                    ContentAgentStageCall.capability == "content.rewrite",
                    ContentAgentStageCall.input_snapshot["rewrite_source"].as_string()
                    == "product_experience_llm_quality_review",
                )
            )
        ).scalars().all()

    assert item.title == "晚饭后的补货"
    assert "孩子也接受" in item.body
    assert "保底" in item.body
    assert rewrite_stages == []
    quality = item.quality_json
    assert quality["product_experience_llm_quality_review"]["pass"] is False
    assert quality["product_experience_llm_quality_review"]["rewrite_required"] is True
    assert quality["product_experience_llm_quality_review"]["mark_rewrite_required"] is False
    assert quality["review_report"].get("rewrite_required") is False
    assert "product_experience_llm_quality_rewrites" not in quality
    assert len(reviewer.calls) == 1
    assert reviewer.calls[0]["phrase_review"]["decision_chain_hits"]


@pytest.mark.asyncio
async def test_batch_execution_repairs_light_fix_business_usability_once():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    reviewer = FakeProductExperienceLLMReviewer(
        [
            ProductExperienceLLMReview(
                pass_=False,
                rewrite_required=False,
                severity="minor",
                issues=[
                    ProductExperienceLLMIssue(
                        code="ad_like_closure",
                        evidence="句子有点断，收口像模板",
                        reason="种草内核成立，但需要轻修入池",
                        rewrite_direction="只修断句和模板收口，保留正向产品价值",
                    )
                ],
                business_usability_tier="light_fix_usable",
                business_usability_reason="有局部断句和旧模板词，轻修后可入池",
                product_appearance_naturalness=4,
                decision_chain_fit=4,
                product_value_strength=4,
                human_realness=3,
                overall_reason="轻修可用",
            ),
            ProductExperienceLLMReview(
                pass_=True,
                rewrite_required=False,
                severity="pass",
                business_usability_tier="direct_pool",
                business_usability_reason="文本顺，种草内核保留",
            ),
        ]
    )

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="mock://maga-worker/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_llm_business_light_fix",
            asset_key="wangyue_v209_benefit_bridge_article_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        session.add(
            ContentBatchItem(
                batch_id=job.id,
                item_no=1,
                status="planned",
                plan_json={
                    "rule_type": "business_rule",
                    "asset_key": "wangyue_v209_benefit_bridge_article_rules",
                    "post_type": "复购/长期使用",
                    "ugc_post_type": "复购/长期使用型",
                    "corpus": "0705旺玥活动",
                },
            )
        )
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceLLMQualityRewriteClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
            product_experience_llm_reviewer=reviewer,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (
            await session.execute(select(ContentBatchItem).where(ContentBatchItem.batch_id == job.id))
        ).scalar_one()
        rewrite_stages = (
            await session.execute(
                select(ContentAgentStageCall).where(
                    ContentAgentStageCall.capability == "content.rewrite",
                    ContentAgentStageCall.input_snapshot["rewrite_source"].as_string()
                    == "product_experience_llm_quality_review",
                )
            )
        ).scalars().all()
        rewrite_sources = (
            await session.execute(
                select(ContentAgentStageCall.input_snapshot["rewrite_source"].as_string()).where(
                    ContentAgentStageCall.capability == "content.rewrite",
                )
            )
        ).scalars().all()

    assert item.title == "晚饭后顺手补"
    assert len(rewrite_stages) == 1
    assert "ai_flavor_humanizer" not in rewrite_sources
    quality = item.quality_json
    assert quality["product_experience_llm_quality_review"]["business_usability_tier"] == "direct_pool"
    assert quality["review_report"].get("rewrite_required") is False
    assert "product_experience_llm_quality_rewrites" in quality
    assert len(reviewer.calls) == 2
    assert reviewer.calls[0]["ai_flavor_review"] is not None


@pytest.mark.asyncio
async def test_wangyue_v152_light_postprocess_keeps_llm_quality_review_mark_only():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    reviewer = FakeProductExperienceLLMReviewer(
        [
            ProductExperienceLLMReview(
                pass_=False,
                rewrite_required=True,
                severity="rewrite",
                issues=[
                    ProductExperienceLLMIssue(
                        code="overcomplete_decision_chain",
                        evidence="朋友问起/旺玥/乳铁蛋白",
                        reason="测试用非 hard 问题",
                        rewrite_direction="只标记，不自动改写",
                    )
                ],
                product_appearance_naturalness=3,
                decision_chain_fit=2,
                product_value_strength=4,
                human_realness=3,
            )
        ]
    )

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="mock://maga-worker/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_v152_light_llm_quality",
            asset_key="wangyue_v152_longer_scene_no_meta_record_article_rules",
            product_topic="旺玥痛点卖点",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        session.add(
            ContentBatchItem(
                batch_id=job.id,
                item_no=1,
                status="planned",
                plan_json={
                    "rule_type": "business_rule",
                    "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
                    "post_type": "轻测评",
                    "ugc_post_type": "轻测评",
                    "corpus": "0705旺玥活动",
                },
            )
        )
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceLLMLightGenerateClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
            product_experience_llm_reviewer=reviewer,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (
            await session.execute(select(ContentBatchItem).where(ContentBatchItem.batch_id == job.id))
        ).scalar_one()
        rewrite_stages = (
            await session.execute(
                select(ContentAgentStageCall).where(
                    ContentAgentStageCall.capability == "content.rewrite",
                    ContentAgentStageCall.input_snapshot["rewrite_source"].as_string()
                    == "product_experience_llm_quality_review",
                )
            )
        ).scalars().all()

    assert rewrite_stages == []
    assert "饭桌还是乱" in item.body
    quality = item.quality_json
    assert quality["product_experience_llm_quality_review"]["rewrite_required"] is True
    assert quality["product_experience_llm_quality_review"]["mark_rewrite_required"] is False
    assert quality["review_report"].get("rewrite_required") is False
    assert "product_experience_llm_quality_rewrites" not in quality
    assert len(reviewer.calls) == 1


def test_wangyue_v183_light_postprocess_marks_logic_drift_only():
    base_review = review_product_experience_phrase(
        title="集体活动后发现的",
        body=(
            "上周幼儿园组织去农场，回来好几个小朋友都蔫了。"
            "后来换了旺玥，一直喝着，就是觉得日常口粮里多留意了保护力这块。"
            "乳铁蛋白、HMO这些成分倒没仔细研究，但确实少请假了。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v183_prompt_slot_slim_article_rules",
            "corpus": "0705旺玥活动",
        },
    )
    review = replace(
        base_review,
        pass_=False,
        rewrite_required=True,
        reasons=["wangyue_article_logic_drift_context"],
    )

    assert _should_mark_only_product_experience_phrase_review(
        {
            "rule_type": "business_rule",
            "asset_key": "wangyue_v183_prompt_slot_slim_article_rules",
            "corpus": "0705旺玥活动",
        },
        review,
    )


def test_wangyue_logic_drift_phrase_guard_is_mark_only_for_current_assets():
    base_review = review_product_experience_phrase(
        title="班里请假的多",
        body="班里接触多，家里喝旺玥，状态一直在线。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v266_strong_selling_expression_article_rules",
            "corpus": "0705旺玥活动",
        },
    )
    review = replace(
        base_review,
        pass_=False,
        rewrite_required=True,
        reasons=["wangyue_article_logic_drift_context"],
    )

    assert _should_mark_only_product_experience_phrase_review(
        {
            "rule_type": "business_rule",
            "asset_key": "wangyue_v266_strong_selling_expression_article_rules",
            "corpus": "0705旺玥活动",
        },
        review,
    )


def test_wangyue_v183_light_postprocess_keeps_time_event_as_rewrite():
    review = review_product_experience_phrase(
        title="幼儿园中招季",
        body="幼儿园中招季，她这阵还挺稳，家里喝旺玥。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v183_prompt_slot_slim_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert "wangyue_time_event_context" in review.reasons
    assert not _should_mark_only_product_experience_phrase_review(
        {
            "rule_type": "business_rule",
            "asset_key": "wangyue_v183_prompt_slot_slim_article_rules",
            "corpus": "0705旺玥活动",
        },
        review,
    )


def test_wangyue_phrase_guard_allows_three_plus_stage_wording():
    plan = {
        "rule_type": "business_rule",
        "asset_key": "wangyue_v183_prompt_slot_slim_article_rules",
        "corpus": "0705旺玥活动",
    }
    samples = (
        ("三岁后选奶复盘", "娃三岁后，家里安排变化挺多的，最后看旺玥营养配得挺全。"),
        ("孩子大了反而更费营养", "我家姐姐过了三岁以后，吃饭开始有自己的主意了，家里常备旺玥。"),
        ("选奶粉时的纠结", "朋友说她家孩子也三岁多了，我说我家喝旺玥。"),
        ("最近吃饭跟打仗一样", "我家娃三岁半，最近吃饭跟打仗一样，旺玥就当个营养补充项喝。"),
        ("4岁多这阵子", "家里4岁多的姐姐最近活动量大，旺玥一直放在家里喝。"),
        ("被问到儿童奶粉时我顺口说了几句", "接孩子路上碰到同班妈妈，问我给娃喝的啥。她家孩子刚满三岁，正愁换不换奶粉。我就顺口提了句旺玥。"),
        ("满三岁以后再看儿童奶粉", "孩子满三岁了，家里才开始看旺玥这类儿童奶粉。"),
        ("一进3岁想法变了", "娃一进3岁，儿童奶粉这块我就多看了几眼，后来选了旺玥。"),
        ("到了三岁再说", "到了三岁以后，家里喝奶这件事才慢慢固定到旺玥。"),
    )

    for title, body in samples:
        review = review_product_experience_phrase(title=title, body=body, plan=plan)
        assert "wangyue_explicit_age_context" not in review.reasons


def test_wangyue_child_operation_guard_ignores_mom_fetching_can_after_question():
    review = review_product_experience_phrase(
        title="看配方时停了一下",
        body=(
            "闺蜜问我给娃喝什么奶粉，我顺手翻出柜子里那罐旺玥的配料表。"
            "她凑过来看，我指着成分说，DHA和燕窝酸都放在眼脑营养这块。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v183_prompt_slot_slim_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert "child_self_brewing_formula" not in review.reasons
    assert review.child_self_brewing_hits == []


def test_wangyue_soft_strong_seeding_llm_review_does_not_rewrite():
    review = ProductExperienceLLMReview(
        pass_=False,
        rewrite_required=True,
        severity="rewrite",
        issues=[
            ProductExperienceLLMIssue(
                code="brief_translation_tone",
                evidence="当初选的时候就是冲着保护力去的",
                reason="选品复盘有点完整",
                rewrite_direction="批量控制比例",
            ),
            ProductExperienceLLMIssue(
                code="overcomplete_decision_chain",
                evidence="生活触发/成分依据/反馈/继续喝",
                reason="节点较满",
                rewrite_direction="批量控制比例",
            ),
        ],
        product_appearance_naturalness=3,
        decision_chain_fit=2,
        product_value_strength=5,
        human_realness=3,
    )

    assert not _should_rewrite_product_experience_llm_quality(
        {"asset_key": "wangyue_v183_prompt_slot_slim_article_rules"},
        review,
    )


def test_wangyue_brief_translation_without_overcomplete_still_rewrites():
    review = ProductExperienceLLMReview(
        pass_=False,
        rewrite_required=True,
        severity="rewrite",
        issues=[
            ProductExperienceLLMIssue(
                code="brief_translation_tone",
                evidence="这个方向是我会看的点",
                reason="抽象选品总结",
                rewrite_direction="删掉抽象总结",
            )
        ],
        product_appearance_naturalness=3,
        decision_chain_fit=3,
        product_value_strength=4,
        human_realness=3,
    )

    assert _should_rewrite_product_experience_llm_quality(
        {"asset_key": "wangyue_v183_prompt_slot_slim_article_rules"},
        review,
    )


@pytest.mark.asyncio
async def test_wangyue_v152_light_effect_chain_phrase_guard_does_not_rewrite():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="mock://maga-worker/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_v152_light_phrase_effect_chain",
            asset_key="wangyue_v152_longer_scene_no_meta_record_article_rules",
            product_topic="旺玥痛点卖点",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        session.add(
            ContentBatchItem(
                batch_id=job.id,
                item_no=1,
                status="planned",
                plan_json={
                    "rule_type": "business_rule",
                    "asset_key": "wangyue_v152_longer_scene_no_meta_record_article_rules",
                    "post_type": "使用记录",
                    "ugc_post_type": "使用记录",
                    "corpus": "0705旺玥活动",
                },
            )
        )
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceEffectChainLightGenerateClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
            product_experience_llm_reviewer=FakeProductExperienceLLMReviewer([]),
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (
            await session.execute(select(ContentBatchItem).where(ContentBatchItem.batch_id == job.id))
        ).scalar_one()
        rewrite_stages = (
            await session.execute(select(ContentAgentStageCall).where(ContentAgentStageCall.capability == "content.rewrite"))
        ).scalars().all()

    assert rewrite_stages == []
    assert "冲一杯旺玥" in item.body
    quality = item.quality_json
    assert quality["product_experience_phrase_guard"]["rewrite_required"] is True
    assert quality["product_experience_phrase_guard"]["mark_rewrite_required"] is False
    assert quality["review_report"].get("rewrite_required") is False
    assert "product_experience_phrase_rewrites" not in quality


def test_product_experience_llm_review_parser_accepts_fenced_json():
    review = parse_product_experience_llm_review(
        """```json
        {
          "pass": false,
          "rewrite_required": true,
          "severity": "rewrite",
          "issues": [{"code": "weak_product_value", "evidence": "还在观察", "reason": "不确定声明削弱价值", "rewrite_direction": "保留一个正向产品依据"}],
          "product_appearance_naturalness": 2,
          "decision_chain_fit": 3,
          "product_value_strength": 1,
          "human_realness": 2,
          "overall_reason": "需要改"
        }
        ```"""
    )

    assert review.rewrite_required is True
    assert review.pass_ is False
    assert review.issues[0].code == "weak_product_value"
    assert review.product_value_strength == 1


def test_product_experience_llm_review_parser_treats_minor_as_no_rewrite():
    review = parse_product_experience_llm_review(
        """
        {
          "pass": false,
          "rewrite_required": true,
          "severity": "minor",
          "business_usability_tier": "light_fix_usable",
          "business_usability_reason": "标题略硬但种草内核成立",
          "issues": [{"code": "ad_like_closure", "evidence": "标题略硬", "reason": "轻微问题", "rewrite_direction": "可不改"}],
          "product_appearance_naturalness": 3,
          "decision_chain_fit": 4,
          "product_value_strength": 4,
          "human_realness": 3,
          "overall_reason": "轻微问题，不强制改写"
        }
        """
    )

    assert review.severity == "minor"
    assert review.rewrite_required is False
    assert review.pass_ is False
    assert review.business_usability_tier == "light_fix_usable"
    assert review.business_usability_reason == "标题略硬但种草内核成立"


def test_product_experience_llm_review_parser_defaults_business_tier_from_severity():
    minor_review = parse_product_experience_llm_review(
        """
        {
          "pass": false,
          "rewrite_required": true,
          "severity": "minor",
          "issues": [{"code": "ad_like_closure", "evidence": "有点收口", "reason": "轻微", "rewrite_direction": "可轻修"}],
          "product_appearance_naturalness": 3,
          "decision_chain_fit": 4,
          "product_value_strength": 4,
          "human_realness": 3,
          "overall_reason": "轻修可用"
        }
        """
    )
    hard_review = parse_product_experience_llm_review(
        """
        {
          "pass": false,
          "rewrite_required": true,
          "severity": "hard",
          "issues": [{"code": "wangyue_age_stage_error", "evidence": "一岁半喝旺玥", "reason": "年龄错误", "rewrite_direction": "改到三岁后"}],
          "product_appearance_naturalness": 1,
          "decision_chain_fit": 3,
          "product_value_strength": 4,
          "human_realness": 2,
          "overall_reason": "暂不入池"
        }
        """
    )

    assert minor_review.business_usability_tier == "light_fix_usable"
    assert hard_review.business_usability_tier == "hold_out"


def test_product_experience_llm_review_parser_downgrades_overcomplete_only_to_minor():
    review = parse_product_experience_llm_review(
        """
        {
          "pass": false,
          "rewrite_required": true,
          "severity": "rewrite",
          "issues": [{"code": "overcomplete_decision_chain", "evidence": "问题到复购链路完整", "reason": "节点较满", "rewrite_direction": "批量控制比例"}],
          "product_appearance_naturalness": 4,
          "decision_chain_fit": 2,
          "product_value_strength": 5,
          "human_realness": 4,
          "overall_reason": "单篇可用，批量注意比例"
        }
        """
    )

    assert review.severity == "minor"
    assert review.rewrite_required is False
    assert review.pass_ is False


def test_product_experience_llm_review_parser_accepts_usage_scene_hard_codes():
    review = parse_product_experience_llm_review(
        """
        {
          "pass": false,
          "rewrite_required": true,
          "severity": "hard",
          "issues": [
            {"code": "portable_product_error", "evidence": "书包侧袋塞了一盒旺玥", "reason": "把罐装儿童奶粉写成随身便携产品", "rewrite_direction": "改成家里日常喝或补货场景，保留一个正向依据"},
            {"code": "child_formula_operation_error", "evidence": "孩子自己舀粉冲水", "reason": "孩子自己操作奶粉不符合产品使用场景", "rewrite_direction": "改成家长冲好后递给孩子"}
          ],
          "product_appearance_naturalness": 1,
          "decision_chain_fit": 3,
          "product_value_strength": 4,
          "human_realness": 2,
          "overall_reason": "产品使用场景事实错误"
        }
        """
    )

    assert review.severity == "hard"
    assert review.rewrite_required is True
    assert [issue.code for issue in review.issues] == [
        "portable_product_error",
        "child_formula_operation_error",
    ]


def test_product_experience_llm_context_calibration_allows_adult_cup_action_when_phrase_guard_passes():
    phrase_review = review_product_experience_phrase(
        title="现在每天放学回来",
        body="现在每天放学回来，我给他冲一杯，他在旁边等着，刚给他买了个新水杯，正新鲜着呢。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v280_closure_attractor_cleanup_article_rules",
            "corpus": "0705旺玥活动",
        },
    )
    review = ProductExperienceLLMReview(
        pass_=False,
        rewrite_required=True,
        severity="rewrite",
        issues=[
            ProductExperienceLLMIssue(
                code="ad_like_closure",
                evidence="三岁后选了旺玥日常更省心",
                reason="标题使用省心作为统一收口",
                rewrite_direction="",
            ),
            ProductExperienceLLMIssue(
                code="formula_usage_form_error",
                evidence="现在每天放学回来，我给他冲一杯",
                reason="固定喝法",
                rewrite_direction="",
            ),
        ],
        business_usability_tier="hold_out",
    )

    calibrated = _calibrate_review_with_context(
        review,
        title="现在每天放学回来",
        body="现在每天放学回来，我给他冲一杯，他在旁边等着，刚给他买了个新水杯，正新鲜着呢。",
        phrase_review=phrase_review,
    )

    assert phrase_review.formula_usage_form_hits == []
    assert calibrated.pass_ is True
    assert calibrated.rewrite_required is False
    assert calibrated.issues == []
    assert calibrated.business_usability_tier == "direct_pool"


def test_product_experience_llm_context_calibration_allows_plain_protection_feedback():
    review = ProductExperienceLLMReview(
        pass_=False,
        rewrite_required=True,
        severity="rewrite",
        issues=[
            ProductExperienceLLMIssue(
                code="claim_risk",
                evidence="接触多了，但状态一直稳，出勤率也还行",
                reason="将接触多与状态稳挂钩",
                rewrite_direction="",
            )
        ],
        business_usability_tier="hold_out",
        product_appearance_naturalness=4,
        product_value_strength=4,
        human_realness=4,
    )

    calibrated = _calibrate_review_with_context(
        review,
        title="又补了旺玥",
        body="孩子现在每天出去跟小朋友玩、上兴趣班，接触多了，但状态一直稳，出勤率也还行。",
        phrase_review=None,
    )

    assert calibrated.pass_ is True
    assert calibrated.rewrite_required is False
    assert calibrated.issues == []
    assert calibrated.business_usability_tier == "direct_pool"


def test_product_experience_llm_review_parser_accepts_wangyue_age_stage_error():
    review = parse_product_experience_llm_review(
        """
        {
          "pass": false,
          "rewrite_required": true,
          "severity": "hard",
          "issues": [{
            "code": "wangyue_age_stage_error",
            "evidence": "一岁半的娃，家里备着旺玥",
            "reason": "旺玥只能在3周岁以后儿童阶段使用，低龄使用关系是产品事实错误",
            "rewrite_direction": "把使用关系改到3岁以后或学龄前阶段，保留正向产品价值"
          }],
          "product_appearance_naturalness": 1,
          "decision_chain_fit": 3,
          "product_value_strength": 4,
          "human_realness": 2,
          "overall_reason": "年龄阶段事实错误"
        }
        """
    )

    assert review.severity == "hard"
    assert review.rewrite_required is True
    assert review.issues[0].code == "wangyue_age_stage_error"


def test_product_experience_llm_review_parser_removes_brief_translation_rewrite_examples():
    review = parse_product_experience_llm_review(
        """
        {
          "pass": false,
          "rewrite_required": true,
          "severity": "rewrite",
          "issues": [{
            "code": "brief_translation_tone",
            "evidence": "这个方向我会看",
            "reason": "像复述业务规则",
            "rewrite_direction": "保留一个生活触发和一个产品依据，去掉抽象选品总结，例如直接写看到乳铁蛋白和HMO就记住了"
          }],
          "product_appearance_naturalness": 3,
          "decision_chain_fit": 3,
          "product_value_strength": 4,
          "human_realness": 2,
          "overall_reason": "需要改"
        }
        """
    )

    assert review.issues[0].rewrite_direction == "保留一个生活触发和一个产品依据，去掉抽象选品总结"
    assert "例如" not in review.issues[0].rewrite_direction
    assert "记住" not in review.issues[0].rewrite_direction


def test_product_experience_llm_review_parser_drops_concrete_ingredient_brief_issue():
    review = parse_product_experience_llm_review(
        """
        {
          "pass": false,
          "rewrite_required": true,
          "severity": "rewrite",
          "business_usability_tier": "hold_out",
          "issues": [{
            "code": "brief_translation_tone",
            "evidence": "钙铁锌这些基础营养看着挺全的，30多种关键营养也够日常补充。",
            "reason": "像业务规则的人话版",
            "rewrite_direction": "用更具体的语言表达"
          }],
          "product_appearance_naturalness": 3,
          "decision_chain_fit": 3,
          "product_value_strength": 4,
          "human_realness": 3,
          "overall_reason": "具体成分大白话不应作为brief主罪"
        }
        """
    )

    assert review.issues == []
    assert review.severity == "minor"
    assert review.rewrite_required is False
    assert review.business_usability_tier == "light_fix_usable"


def test_product_experience_llm_review_parser_keeps_ingredient_brief_issue_with_abstract_marker():
    review = parse_product_experience_llm_review(
        """
        {
          "pass": false,
          "rewrite_required": true,
          "severity": "rewrite",
          "business_usability_tier": "hold_out",
          "issues": [{
            "code": "brief_translation_tone",
            "evidence": "乳铁蛋白和HMO这些我会看，最近孩子接触多以后，状态和出勤都挺稳。",
            "reason": "把业务规则翻译成妈妈口吻",
            "rewrite_direction": "保留状态和出勤稳，去掉抽象选品总结"
          }],
          "product_appearance_naturalness": 2,
          "decision_chain_fit": 2,
          "product_value_strength": 3,
          "human_realness": 2,
          "overall_reason": "需要改"
        }
        """
    )

    assert [issue.code for issue in review.issues] == ["brief_translation_tone"]
    assert review.severity == "rewrite"
    assert review.rewrite_required is True
    assert review.business_usability_tier == "hold_out"


def test_product_experience_llm_review_parser_keeps_abstract_brief_issue():
    review = parse_product_experience_llm_review(
        """
        {
          "pass": false,
          "rewrite_required": true,
          "severity": "rewrite",
          "issues": [{
            "code": "brief_translation_tone",
            "evidence": "我会关注保护力这个方向，这个点值得看。",
            "reason": "抽象选品总结",
            "rewrite_direction": "删掉抽象总结"
          }],
          "product_appearance_naturalness": 3,
          "decision_chain_fit": 3,
          "product_value_strength": 4,
          "human_realness": 3,
          "overall_reason": "抽象brief仍需改"
        }
        """
    )

    assert [issue.code for issue in review.issues] == ["brief_translation_tone"]
    assert review.rewrite_required is True


def test_product_experience_llm_review_uses_unified_generation_model_config():
    config = _review_model_config(
        {
            "unified_generation": {
                "model_config": {
                    "provider_code": "deepseek",
                    "model_code": "deepseek-chat",
                    "ge_model": "deepseek-chat",
                    "temperature": 0.9,
                    "max_tokens": 2048,
                }
            }
        }
    )

    assert config["provider"] == "deepseek"
    assert config["model"] == "deepseek-chat"
    assert config["temperature"] == 0.1
    assert config["max_tokens"] == 1200


def test_product_experience_llm_prompt_covers_template_peace_of_mind_closures():
    assert "有个着落" in _SYSTEM_PROMPT
    assert "有谱" in _SYSTEM_PROMPT
    assert "这些词不是绝对禁词" in _SYSTEM_PROMPT
    assert "加进牛奶" in _SYSTEM_PROMPT
    assert "疾病或免疫相关场景" in _SYSTEM_PROMPT
    assert "三天两头跑医院" in _SYSTEM_PROMPT
    assert "没再高烧" in _SYSTEM_PROMPT
    assert "防护/自身防护/肠道" in _SYSTEM_PROMPT
    assert "不能建议删掉所有产品价值" in _SYSTEM_PROMPT
    assert "minor 不触发改写" in _SYSTEM_PROMPT
    assert "真实 UGC 带产品本来就可能有轻微种草感" in _SYSTEM_PROMPT
    assert "强种草问答" in _SYSTEM_PROMPT
    assert "朋友问起 + 成分依据 + 多个自家反馈" in _SYSTEM_PROMPT
    assert "妈妈大白话里的具体成分/配方事实" in _SYSTEM_PROMPT
    assert "节点密度主要是批次分布问题" in _SYSTEM_PROMPT
    assert "高密度种草单篇可以通过" in _SYSTEM_PROMPT
    assert "孩子拿着杯子喝完" in _SYSTEM_PROMPT
    assert "child_formula_operation_error" in _SYSTEM_PROMPT
    assert "portable_product_error" in _SYSTEM_PROMPT
    assert "business_usability_tier" in _SYSTEM_PROMPT
    assert "direct_pool" in _SYSTEM_PROMPT
    assert "light_fix_usable" in _SYSTEM_PROMPT
    assert "hold_out" in _SYSTEM_PROMPT
    assert "唯一人工业务口径" in _SYSTEM_PROMPT
    assert "wangyue_age_stage_error" in _SYSTEM_PROMPT
    assert "低于3周岁时使用、购买、备着、开始喝旺玥" in _SYSTEM_PROMPT
    assert "年龄判断不能只看词表" in _SYSTEM_PROMPT
    assert "书包、侧袋、背包可以只是生活细节" in _SYSTEM_PROMPT
    assert "小条装、便携装、奶粉条、分装" in _SYSTEM_PROMPT
    assert "product_fact_number_drift" in _SYSTEM_PROMPT
    assert "十几种/十多种/20多种/几十种关键营养" in _SYSTEM_PROMPT
    assert "effect_scope_drift" in _SYSTEM_PROMPT
    assert "睡得安稳、一整夜不闹、入睡变好" in _SYSTEM_PROMPT


def test_product_experience_llm_prompt_passes_usage_scene_phrase_hints():
    phrase_review = review_product_experience_phrase(
        title="接娃路上聊到请假",
        body="我顺手在书包侧袋塞了一盒旺玥，想着玩完兑点温水就能喝。孩子自己倒水舀粉。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "0705旺玥活动",
        },
    )

    payload = json.loads(
        _user_prompt(
            title="接娃路上聊到请假",
            body="我顺手在书包侧袋塞了一盒旺玥，想着玩完兑点温水就能喝。孩子自己倒水舀粉。",
            plan={
                "asset_key": "wangyue_article_business_rules",
                "post_type": "使用反馈",
                "corpus": "0705旺玥活动",
            },
            phrase_review=phrase_review,
        )
    )

    hints = payload["deterministic_hints"]
    assert any("书包侧袋" in hit for hit in hints["wangyue_portable_form_hits"])
    assert "孩子自己倒水舀粉" in hints["child_self_brewing_hits"]
    assert "wangyue_portable_form_context" in hints["reasons"]
    assert "child_self_brewing_formula" in hints["reasons"]


def test_product_experience_llm_prompt_passes_age_phrase_hints():
    phrase_review = review_product_experience_phrase(
        title="旺玥记录",
        body="一岁半的娃吃饭不稳，家里备着旺玥。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "旺玥是3周岁以上、3-6岁学龄前儿童语境下的4段儿童奶粉。",
        },
    )

    payload = json.loads(
        _user_prompt(
            title="旺玥记录",
            body="一岁半的娃吃饭不稳，家里备着旺玥。",
            plan={
                "asset_key": "wangyue_article_business_rules",
                "post_type": "使用反馈",
                "corpus": "0705旺玥活动",
            },
            phrase_review=phrase_review,
        )
    )

    hints = payload["deterministic_hints"]
    assert "一岁半" in hints["wangyue_explicit_age_hits"]
    assert "wangyue_explicit_age_context" in hints["reasons"]


def test_product_experience_phrase_guard_blocks_physical_action_carrier_mismatch():
    review = review_product_experience_phrase(
        title="被问起看配方",
        body=(
            "闺蜜问我娃最近坐不坐得住，顺手翻她桌上那罐旺玥的配方表。"
            "DHA和燕窝酸列得挺清楚，她说就是图这个眼脑搭配。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v209_benefit_bridge_article_rules",
            "corpus": "0705旺玥活动",
        },
    )

    assert "physical_action_carrier_mismatch" in review.reasons
    assert "顺手翻她桌上那罐旺玥的配方表" in review.physical_action_carrier_mismatch_hits
    assert review.model_dump()["physical_action_carrier_mismatch_hits"] == [
        "顺手翻她桌上那罐旺玥的配方表"
    ]

    hand_side_review = review_product_experience_phrase(
        title="被问到喝什么",
        body=(
            "昨天朋友来家里聊起娃的伙食，她家孩子刚满三岁，问我现在给娃喝啥。"
            "我正好手边有罐旺玥，就拿起来翻了一下配方表。"
            "三岁后其实更看整体营养配置，钙铁锌这些基础营养得跟上。"
        ),
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v209_benefit_bridge_article_rules",
            "corpus": "0705旺玥活动",
        },
    )
    assert "physical_action_carrier_mismatch" in hand_side_review.reasons
    assert hand_side_review.physical_action_carrier_mismatch_hits == [
        "手边有罐旺玥，就拿起来翻了一下配方表"
    ]

    natural_review = review_product_experience_phrase(
        title="看了眼罐身",
        body="她把桌上那罐旺玥转过来，我扫了眼罐身营养成分，DHA和燕窝酸写得挺清楚。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v209_benefit_bridge_article_rules",
            "corpus": "0705旺玥活动",
        },
    )
    assert "physical_action_carrier_mismatch" not in natural_review.reasons
    assert natural_review.physical_action_carrier_mismatch_hits == []


def test_product_experience_phrase_rewrite_input_handles_physical_action_carrier_mismatch():
    service = ContentBatchExecutionService.__new__(ContentBatchExecutionService)
    item = ContentBatchItem(
        title="被问起看配方",
        body="闺蜜问我娃最近坐不坐得住，顺手翻她桌上那罐旺玥的配方表。DHA和燕窝酸列得挺清楚。",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v209_benefit_bridge_article_rules",
            "corpus": "0705旺玥活动",
        },
        quality_json={},
    )
    review = review_product_experience_phrase(title=item.title, body=item.body, plan=item.plan_json)

    payload = service._product_experience_phrase_rewrite_input(item, review)

    instructions = "\n".join(payload["rewrite_instructions"])
    assert "物理动作/信息载体错配" in instructions
    assert "罐装奶粉和“翻配方表”硬接在一起" in instructions
    assert "只局部处理命中句" in instructions
    assert "不补新的拿罐、翻看、冲泡或喝奶动作" in instructions
    assert "不要新增冲泡、喝奶、下单、对比清单或新的效果证明" in instructions


def test_v209_wangyue_light_formula_slot_does_not_seed_flip_can_action():
    import sys

    scripts_dir = str(Path(__file__).resolve().parents[1] / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    from scripts.build_v209_wangyue_benefit_bridge_import import build_rows

    rows = build_rows()
    joined = "\n".join(
        "\n".join(str(row.get(field) or "") for field in row)
        for row in rows
    )

    assert "被问起后翻看信息" not in joined
    assert "自己翻罐" not in joined
    assert "包装信息" not in joined
    assert "旺玥作为被问到或看配方时提到的一罐" not in joined
    assert "看配方或被问到时，说一个自己看懂的成分点" not in joined
    assert "被问起后说成分印象" in joined


def test_v209_wangyue_slot_compatibility_matrix_blocks_scene_painpoint_drift():
    import sys

    scripts_dir = str(Path(__file__).resolve().parents[1] / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    from scripts.build_v209_wangyue_benefit_bridge_import import (
        _validate_slot_compatibility,
        build_rows,
    )

    rows = build_rows()
    assert _validate_slot_compatibility(rows) == []

    bad_rows = [dict(row) for row in rows]
    bad_rows[2]["scene_motive_bucket"] = "集体活动后自家观察"

    errors = _validate_slot_compatibility(bad_rows)
    assert any("painpoint=营养不足 cannot use scene_motive_bucket=集体活动后自家观察" in error for error in errors)
    assert any("营养丰富 cannot use 集体活动后自家观察" in error for error in errors)


def test_v209_wangyue_effect_proof_slots_do_not_seed_repeated_phrase_packs():
    import sys

    scripts_dir = str(Path(__file__).resolve().parents[1] / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    from scripts.build_v209_wangyue_benefit_bridge_import import build_rows

    rows = build_rows()
    joined = "\n".join(
        "\n".join(str(row.get(field) or "") for field in row)
        for row in rows
    )

    repeated_phrase_packs = (
        "保护力这块",
        "营养不断档",
        "抱起来有分量",
        "背上有肉",
        "衣服撑一点",
        "跑跳有劲",
        "跑跳更有劲",
        "身形结实",
    )
    for phrase in repeated_phrase_packs:
        assert phrase not in joined


def test_product_experience_llm_quality_rewrite_input_handles_age_stage_error():
    service = ContentBatchExecutionService.__new__(ContentBatchExecutionService)
    item = ContentBatchItem(
        title="旺玥记录",
        body="一岁半的娃吃饭不稳，家里备着旺玥。",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "旺玥是3周岁以上、3-6岁学龄前儿童语境下的4段儿童奶粉。",
        },
    )
    review = ProductExperienceLLMReview(
        pass_=False,
        rewrite_required=True,
        severity="hard",
        issues=[
            ProductExperienceLLMIssue(
                code="wangyue_age_stage_error",
                evidence="一岁半的娃，家里备着旺玥",
                reason="低龄使用旺玥是产品事实错误",
                rewrite_direction="改到3岁以后",
            )
        ],
    )

    payload = service._product_experience_llm_quality_rewrite_input(item, review)

    instructions = "\n".join(payload["rewrite_instructions"])
    assert "产品年龄事实硬错误" in instructions
    assert "业务规则允许的年龄阶段" in instructions
    assert "不要完整复述成“3岁以上4段儿童奶粉”" in instructions
    assert "保留原文一个正向产品价值或效果证明" in instructions
    assert "改写后正文必须仍明确保留" in instructions
    assert "不能把产品从正文里洗掉" in instructions


def test_ai_flavor_rewrite_input_keeps_wangyue_product_mention():
    service = ContentBatchExecutionService.__new__(ContentBatchExecutionService)
    item = ContentBatchItem(
        title="选奶看了眼脑",
        body="女儿最近拼图能坐挺久，之前挑奶粉时对比过几款，旺玥有DHA和燕窝酸。",
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_selection_review",
            "corpus": "0705旺玥活动",
            "unified_generation": {"selected_keywords": []},
        },
    )
    review = AIFlavorReview(
        pass_=False,
        rewrite_required=True,
        reasons=["brief_translation_tone"],
        title_hits=["选奶看了眼脑"],
        body_hits=["对比过几款"],
        rewrite_operations=[],
    )

    payload = service._ai_flavor_rewrite_input(item, review)

    instructions = "\n".join(payload["rewrite_instructions"])
    assert "改写后正文必须仍明确保留" in instructions
    assert "真人润色只改表达，不能把产品从正文里洗掉" in instructions


@pytest.mark.asyncio
async def test_product_experience_llm_review_plan_gets_transient_provider_config():
    class FakeOrchestrator:
        async def _input_payload_with_provider_config(self, payload):
            return {
                **payload,
                "model_config": {
                    **payload["model_config"],
                    "api_key": "secret-key",
                    "base_url": "https://api.deepseek.com/v1/chat/completions",
                },
            }

    service = ContentBatchExecutionService.__new__(ContentBatchExecutionService)
    plan = await service._plan_with_provider_config_for_llm_review(
        {
            "unified_generation": {
                "model_config": {
                    "provider_code": "deepseek",
                    "model_code": "deepseek-chat",
                }
            }
        },
        orchestrator=FakeOrchestrator(),
    )

    assert plan["model_config"]["provider_code"] == "deepseek"
    assert plan["model_config"]["model_code"] == "deepseek-chat"
    assert plan["model_config"]["api_key"] == "secret-key"


@pytest.mark.asyncio
async def test_batch_execution_generates_first_n_items_and_links_runs():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="mock://maga-worker/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_test",
            asset_key="yuanyue",
            product_topic="宝宝便便不规律",
            target_audience="新手妈妈",
            style="经验老道型",
            count=3,
            status="planned",
        )
        session.add(job)
        await session.flush()
        for item_no in range(1, 4):
            session.add(
                ContentBatchItem(
                    batch_id=job.id,
                    item_no=item_no,
                    status="planned",
                    plan_json=_plan(item_no),
                )
            )
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=MockExecutorInvocationClient(),
            callback_base_url="http://maga.test/api/v1/executor",
        )
        result = await service.execute_batch_items(job.id, limit=2, created_by="test")
        await session.commit()

    assert result.batch_id == job.id
    assert result.requested_limit == 2
    assert result.generated_count == 2
    assert result.failed_count == 0

    async with session_factory() as session:
        items = (
            await session.execute(select(ContentBatchItem).where(ContentBatchItem.batch_id == job.id).order_by(ContentBatchItem.item_no))
        ).scalars().all()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert [item.status for item in items] == ["generated", "generated", "planned"]
    assert all(item.title and item.body for item in items[:2])
    assert items[0].title != items[1].title
    assert items[0].task_id is not None
    assert items[0].run_id is not None
    assert items[0].quality_json["executor"] == "content_fake"
    review_report = items[0].quality_json["review_report"]
    assert review_report["rewrite_required"] is False
    assert review_report["source"] == "maga_unified_content_generate"
    assert review_report["hard_results"] == []
    assert items[0].quality_json["hard_pass"] is True
    assert items[0].quality_json["soft_score_avg"] is None
    assert items[0].quality_json["expert_config_code"] == "article_generator_v1"
    assert items[0].plan_json["unified_generation"]["capability"] == "content.generate"
    assert "opening_type" not in items[0].diversity_json
    assert "narrative_focus" not in items[0].diversity_json
    assert "selected_keywords" in items[0].diversity_json
    assert "content.generate" in {stage.capability for stage in stage_calls}


@pytest.mark.asyncio
async def test_batch_execution_applies_persona_style_rewrite_after_generation():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="mock://maga-worker/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_persona_rewrite",
            asset_key="yuanyue",
            product_topic="宝宝便便不规律",
            target_audience="新手妈妈",
            style="经验老道型",
            count=2,
            status="planned",
        )
        session.add(job)
        await session.flush()
        legacy_plan = {
            **_plan(1),
            "diversity_slot": {
                "opening_type": "评论区聊到",
                "narrative_focus": "先说评论区讨论",
            },
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=legacy_plan))
        session.add(ContentBatchItem(batch_id=job.id, item_no=2, status="planned", plan_json=_plan(2)))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=PersonaStyleRewriteClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=2, concurrency=2, created_by="test")
        await session.commit()

    assert result.generated_count == 2
    async with session_factory() as session:
        items = (
            await session.execute(select(ContentBatchItem).where(ContentBatchItem.batch_id == job.id).order_by(ContentBatchItem.item_no))
        ).scalars().all()
        rewrite_stages = (
            await session.execute(select(ContentAgentStageCall).where(ContentAgentStageCall.capability == "content.rewrite"))
        ).scalars().all()

    assert items[0].body == "roommate_direct 改写后正文"
    assert items[1].body == "mother_soft_observer 改写后正文"
    assert items[0].quality_json["persona_style_rewrites"][0]["preset_code"] == "roommate_direct"
    assert items[1].quality_json["persona_style_rewrites"][0]["preset_code"] == "mother_soft_observer"
    assert len(rewrite_stages) == 1
    instructions = "\n".join((rewrite_stages[0].input_snapshot or {}).get("rewrite_instructions") or [])
    assert "人设改写风格：爽快、直给" in instructions
    assert "不要改变原文的发帖视角" in instructions
    rewrite_business_rule = (rewrite_stages[0].input_snapshot or {}).get("business_rule") or {}
    assert "diversity_slot" not in rewrite_business_rule
    assert "评论区聊到" not in str(rewrite_business_rule)


@pytest.mark.asyncio
async def test_wangyue_batch_execution_repairs_duplicate_titles():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    class DuplicateTitleClient:
        async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
            input_payload = envelope.get("input") or {}
            business_rule = input_payload.get("business_rule") or {}
            item_no = business_rule.get("item_no") or 1
            return InvokeResult(
                mode="sync",
                stage_call_id=envelope["stage_call_id"],
                output={
                    "title": "旺玥4段怎么选",
                    "body": f"旺玥喝了一阵，孩子口味能接受，选奶时主要看日常补充。第{item_no}次记录。",
                    "runtime_result": {"mode": "content_fake"},
                },
                stats={"fake": True},
            )

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="mock://maga-worker/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_wangyue_title_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=3,
            status="planned",
        )
        session.add(job)
        await session.flush()
        for item_no in range(1, 4):
            plan = {
                **_plan(item_no),
                "asset_key": "wangyue_article_business_rules",
                "business_rule": "容易中招，选奶判断",
                "topic": "容易中招，选奶判断",
                "corpus": "活动：0705旺玥活动。\n痛点词：容易中招；场景：选奶判断；卖点方向：进阶保护力；主题：选奶判断。",
            }
            session.add(ContentBatchItem(batch_id=job.id, item_no=item_no, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=DuplicateTitleClient(),
            callback_base_url="http://maga.test/api/v1/executor",
        )
        result = await service.execute_batch_items(job.id, limit=3, concurrency=3, created_by="test")
        await session.commit()

    assert result.generated_count == 3
    async with session_factory() as session:
        items = (
            await session.execute(select(ContentBatchItem).where(ContentBatchItem.batch_id == job.id).order_by(ContentBatchItem.item_no))
        ).scalars().all()

    titles = [item.title for item in items]
    assert len(set(titles)) == 3
    assert all(title != "旺玥4段怎么选" for title in titles)
    assert "儿童奶粉先这样选" not in titles
    assert "这罐先继续喝" not in titles
    assert "选儿童奶粉这事" not in titles
    assert "儿童成长奶粉小记录" not in titles
    assert "保护力这块我会多看一眼" not in titles
    assert any("forbidden_title_phrase:旺玥4段" in repair["reasons"] for item in items for repair in item.quality_json["title_guard_repairs"])
    assert items[2].quality_json["title_guard"]["pass"] is True


@pytest.mark.asyncio
async def test_wangyue_batch_execution_repairs_copied_reference_titles():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    class CopiedReferenceTitleClient:
        async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
            return InvokeResult(
                mode="sync",
                stage_call_id=envelope["stage_call_id"],
                output={
                    "title": "皇家美素佳儿旺玥",
                    "body": "孩子上学后接触人多，我给他选儿童奶粉时会看保护力。旺玥这罐先喝着记录一下。",
                    "runtime_result": {"mode": "content_fake"},
                },
                stats={"fake": True},
            )

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="mock://maga-worker/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_wangyue_copied_title_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "容易中招，选奶判断",
            "topic": "容易中招，选奶判断",
            "corpus": "写作规则：孩子上学后接触人多，妈妈担心容易中招；选择旺玥这款儿童奶粉，是看中保护力。",
            "title_reference_all_examples": ["皇家美素佳儿旺玥", "儿童成长奶粉哪家好"],
            "title_reference_examples": ["儿童成长奶粉哪家好"],
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=CopiedReferenceTitleClient(),
            callback_base_url="http://maga.test/api/v1/executor",
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()

    assert item.title != "皇家美素佳儿旺玥"
    repairs = item.quality_json["title_guard_repairs"]
    assert repairs[0]["reasons"] == ["copied_reference_title"]


@pytest.mark.asyncio
async def test_wangyue_title_guard_avoids_recent_activity_titles():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    class CopiedReferenceTitleClient:
        async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
            return InvokeResult(
                mode="sync",
                stage_call_id=envelope["stage_call_id"],
                output={
                    "title": "皇家美素佳儿旺玥",
                    "body": "孩子上学后接触人多，我给他选儿童奶粉时会看保护力。旺玥这罐先喝着记录一下。",
                    "runtime_result": {"mode": "content_fake"},
                },
                stats={"fake": True},
            )

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="mock://maga-worker/invoke",
                enabled=1,
                config_json={},
            )
        )
        history_job = ContentBatchJob(
            batch_code="batch_wangyue_title_history",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="generated",
        )
        session.add(history_job)
        await session.flush()
        session.add(
            ContentBatchItem(
                batch_id=history_job.id,
                item_no=1,
                status="generated",
                plan_json=_plan(1),
                title="儿童奶粉挑到最后",
                body="旧批次标题。",
            )
        )

        job = ContentBatchJob(
            batch_code="batch_wangyue_title_history_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "容易中招，选奶判断",
            "topic": "容易中招，选奶判断",
            "corpus": "写作规则：孩子上学后接触人多，妈妈担心容易中招；选择旺玥这款儿童奶粉，是看中保护力。",
            "title_reference_all_examples": ["皇家美素佳儿旺玥"],
            "title_reference_examples": [],
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=CopiedReferenceTitleClient(),
            callback_base_url="http://maga.test/api/v1/executor",
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (
            await session.execute(
                select(ContentBatchItem)
                .where(ContentBatchItem.batch_id == job.id)
                .order_by(ContentBatchItem.item_no)
            )
        ).scalar_one()

    assert item.title != "皇家美素佳儿旺玥"
    assert item.title != "儿童奶粉挑到最后"
    assert item.quality_json["title_guard"]["history_title_count"] == 1
    assert item.quality_json["title_guard_repairs"][0]["reasons"] == ["copied_reference_title"]


@pytest.mark.asyncio
async def test_wangyue_batch_execution_cleans_model_title_format_without_fallback():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    class MarkdownTitleClient:
        def __init__(self):
            self.item_no = 0

        async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
            self.item_no += 1
            item_no = self.item_no
            title = {
                1: "*标题：搁家里奶罐换得比酱油还勤**",
                2: "### 标题：遛弯被问了八百遍的娃口粮分享",
                3: "去年的裤子怎么都短了🤔",
            }[item_no]
            return InvokeResult(
                mode="sync",
                stage_call_id=envelope["stage_call_id"],
                output={
                    "title": title,
                    "body": f"旺玥喝了一阵，孩子口味能接受，日常补充先记一下。第{item_no}次记录。",
                    "runtime_result": {"mode": "content_fake"},
                },
                stats={"fake": True},
            )

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="mock://maga-worker/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_wangyue_title_format_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=3,
            status="planned",
        )
        session.add(job)
        await session.flush()
        for item_no in range(1, 4):
            plan = {
                **_plan(item_no),
                "rule_type": "business_rule",
                "asset_key": "wangyue_article_business_rules",
                "business_rule": "营养不足/成长发育需求，日常补充观察",
                "topic": "营养不足/成长发育需求，日常补充观察",
                "corpus": "活动：0705旺玥活动。\n写作规则：围绕孩子日常营养补充来写。",
            }
            session.add(ContentBatchItem(batch_id=job.id, item_no=item_no, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=MarkdownTitleClient(),
            callback_base_url="http://maga.test/api/v1/executor",
        )
        result = await service.execute_batch_items(job.id, limit=3, concurrency=1, created_by="test")
        await session.commit()

    assert result.generated_count == 3
    async with session_factory() as session:
        items = (
            await session.execute(select(ContentBatchItem).where(ContentBatchItem.batch_id == job.id).order_by(ContentBatchItem.item_no))
        ).scalars().all()

    assert [item.title for item in items] == [
        "搁家里奶罐换得比酱油还勤",
        "遛弯被问了八百遍的娃口粮分享",
        "去年的裤子怎么都短了",
    ]
    assert all("title_format_cleanups" in item.quality_json for item in items)
    assert all("title_guard_repairs" not in item.quality_json for item in items)


@pytest.mark.asyncio
async def test_wangyue_batch_execution_repairs_dangling_title_after_format_cleanup():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    class DanglingTitleClient:
        async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
            return InvokeResult(
                mode="sync",
                stage_call_id=envelope["stage_call_id"],
                output={
                    "title": "刚拆的快递里，🫙",
                    "body": "孩子奶粉还没定，今天又看了半天。旺玥这罐先喝着记录一下。",
                    "runtime_result": {"mode": "content_fake"},
                },
                stats={"fake": True},
            )

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="mock://maga-worker/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_wangyue_dangling_title_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "营养不足/成长发育需求，日常补充观察",
            "topic": "营养不足/成长发育需求，日常补充观察",
            "corpus": "活动：0705旺玥活动。\n写作规则：围绕孩子日常营养补充来写。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=DanglingTitleClient(),
            callback_base_url="http://maga.test/api/v1/executor",
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()

    assert item.title != "刚拆的快递里，"
    assert not item.title.endswith(("，", "、", "：", "；", ",", ";", ":"))
    assert item.quality_json["title_format_cleanups"] == [{"before": "刚拆的快递里，🫙", "after": "刚拆的快递里，"}]
    assert item.quality_json["title_guard_repairs"][0]["before"] == "刚拆的快递里，"
    assert item.quality_json["title_guard_repairs"][0]["reasons"] == ["dangling_title_punctuation"]


@pytest.mark.asyncio
async def test_batch_execution_rewrites_business_forbidden_terms():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="mock://maga-worker/invoke",
                enabled=1,
                config_json={},
            )
        )
        session.add(
            AssetRegistry(
                asset_type="business_forbidden_terms",
                asset_key="yuanyue",
                display_name="源悦业务违禁词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "schema_version": "1",
                    "terms": [{"term": "宝宝", "enabled": True, "replacement": "孩子"}],
                },
            )
        )
        job = ContentBatchJob(
            batch_code="batch_forbidden_rewrite",
            asset_key="yuanyue",
            product_topic="宝宝便便不规律",
            target_audience="新手妈妈",
            style="经验老道型",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=_plan(1)))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=MockExecutorInvocationClient(),
            callback_base_url="http://maga.test/api/v1/executor",
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    full_text = f"{item.title}\n{item.body}"
    assert "宝宝" not in full_text
    assert "孩子" in full_text
    forbidden_review = item.quality_json["forbidden_terms_review"]
    assert forbidden_review["initial_hits"] == ["宝宝"]
    assert forbidden_review["final_hits"] == []
    assert forbidden_review["rewrite_rounds"] == 1
    assert item.quality_json["review_report"]["hard_results"][-1]["ae_code"] == "forbidden_terms_guard"
    assert item.quality_json["review_report"]["hard_results"][-1]["pass"] is True
    assert any(stage.capability == "content.rewrite" for stage in stage_calls)
    rewrite_stage = next(
        stage
        for stage in stage_calls
        if stage.capability == "content.rewrite" and (stage.input_snapshot or {}).get("rewrite_source") != "persona_style_rewrite"
    )
    assert (rewrite_stage.input_snapshot or {})["forbidden_replacements"] == {"宝宝": "孩子"}
    assert "宝宝 -> 孩子" in "\n".join((rewrite_stage.input_snapshot or {})["rewrite_instructions"])


@pytest.mark.asyncio
async def test_batch_execution_blocks_when_forbidden_terms_survive_rewrite():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="mock://maga-worker/invoke",
                enabled=1,
                config_json={},
            )
        )
        session.add(
            AssetRegistry(
                asset_type="business_forbidden_terms",
                asset_key="yuanyue",
                display_name="源悦业务违禁词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "schema_version": "1",
                    "terms": [{"term": "宝宝", "enabled": True, "replacement": "宝宝"}],
                },
            )
        )
        job = ContentBatchJob(
            batch_code="batch_forbidden_residue_blocks",
            asset_key="yuanyue",
            product_topic="普通话题",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {**_plan(1), "persona_style_rewrite_enabled": False}
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ForbiddenResidualRewriteClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert item.status == "failed"
    assert item.quality_json["hard_pass"] is False
    assert item.quality_json["forbidden_terms_review"]["final_hits"] == ["宝宝"]
    assert item.quality_json["postprocess_blocked"]["source"] == "forbidden_terms_guard"
    assert item.quality_json["review_report"]["blocking_failure"]["source"] == "forbidden_terms_guard"
    assert item.error_message == "违禁词自动改写后仍命中：宝宝"
    rewrite_stages = [stage for stage in stage_calls if stage.capability == "content.rewrite"]
    assert len(rewrite_stages) == 2
    assert all((stage.input_snapshot or {})["forbidden_hits"] == ["宝宝"] for stage in rewrite_stages)
    assert all((stage.input_snapshot or {}).get("rewrite_source") is None for stage in rewrite_stages)


@pytest.mark.asyncio
async def test_batch_execution_rewrites_royal_friso_structure_risks():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="mock://maga-worker/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_royal_structure_rewrite",
            asset_key="royal_friso_ugc_post_rules_v1",
            product_topic="2026皇家美素佳儿UGC活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {**_plan(1), "asset_key": "royal_friso_ugc_post_rules_v1", "persona_style_rewrite_enabled": False}
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=RoyalFrisoStructureRewriteClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert item.status == "generated"
    assert item.quality_json["hard_pass"] is True
    guard = item.quality_json["royal_friso_ugc_structure_guard"]
    assert guard["pass"] is True
    assert guard["rewrite_required"] is False
    rewrite = item.quality_json["royal_friso_ugc_structure_rewrites"][0]
    assert {issue["code"] for issue in rewrite["pre_review"]["issues"]} >= {
        "child_self_handling_formula",
        "milk_residual_or_drinking_claim",
    }
    assert "自己跑去拿奶瓶" not in item.body
    assert "自己拿着奶瓶" not in item.body
    assert "喝完" not in item.body
    assert "皇家美素佳儿" in item.body
    rewrite_stage = next(
        stage
        for stage in stage_calls
        if stage.capability == "content.rewrite"
        and (stage.input_snapshot or {}).get("rewrite_source") == "royal_friso_ugc_structure_guard"
    )
    assert "孩子自己接过/拿着/抱着/递回奶瓶或杯子" in "\n".join(
        rewrite_stage.input_snapshot["rewrite_instructions"]
    )


@pytest.mark.asyncio
async def test_batch_execution_blocks_royal_friso_structure_residue_after_rewrite():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="mock://maga-worker/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_royal_structure_residue",
            asset_key="royal_friso_ugc_post_rules_v1",
            product_topic="2026皇家美素佳儿UGC活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {**_plan(1), "asset_key": "royal_friso_ugc_post_rules_v1", "persona_style_rewrite_enabled": False}
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=RoyalFrisoStructureStillBadRewriteClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()

    assert item.status == "failed"
    assert item.quality_json["hard_pass"] is False
    assert item.quality_json["postprocess_blocked"]["source"] == "royal_friso_ugc_structure_guard"
    assert "child_self_handling_formula" in item.quality_json["postprocess_blocked"]["reasons"]
    assert item.quality_json["review_report"]["blocking_failure"]["source"] == "royal_friso_ugc_structure_guard"
    assert item.error_message.startswith("皇家UGC结构风险改写后仍命中：")


@pytest.mark.asyncio
async def test_forbidden_term_review_replaces_static_term_without_model():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        item = ContentBatchItem(
            batch_id=1,
            item_no=1,
            status="generated",
            title="肠胃状态记录",
            body="这段时间先观察肠胃反应，表达要自然一点。",
            quality_json={"review_report": {}, "hard_pass": True},
            plan_json={},
        )

        review = await ForbiddenTermReviewService(session).review_and_rewrite_item(
            item=item,
            asset_key=None,
            orchestrator=None,
            executor_code=None,
            content_type="article",
        )

    full_text = f"{item.title}\n{item.body}"
    assert review["initial_hits"] == ["肠胃"]
    assert review["final_hits"] == []
    assert "肠胃" not in full_text
    assert "肚肚" in full_text


@pytest.mark.asyncio
async def test_forbidden_term_review_applies_wangyue_scoped_terms_without_model():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        item = ContentBatchItem(
            batch_id=1,
            item_no=1,
            status="generated",
            title="换季翻衣服",
            body="前几天换季翻出裤子，顺手记一下旺玥。",
            quality_json={"review_report": {}, "hard_pass": True},
            plan_json={},
        )

        review = await ForbiddenTermReviewService(session).review_and_rewrite_item(
            item=item,
            asset_key="wangyue_v209_benefit_bridge_article_rules",
            orchestrator=None,
            executor_code=None,
            content_type="article",
        )

    full_text = f"{item.title}\n{item.body}"
    assert review["initial_hits"] == ["换季"]
    assert review["final_hits"] == []
    assert "换季" not in full_text


class RuntimeFastDraftReviewClient:
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        capability = envelope.get("capability")
        if capability == "content.generate":
            output = {
                "title": "runtime content 标题",
                "body": "runtime content 正文",
                "runtime_result": {"mode": "content_runtime", "phase": "content_generate"},
            }
        elif capability == "content.rewrite":
            input_payload = envelope.get("input") or {}
            previous = input_payload.get("previous_content") or {"title": "runtime content 标题", "body": "runtime content 正文"}
            output = {
                "title": previous.get("title") or "runtime content 标题",
                "body": previous.get("body") or "runtime content 正文",
                "final": previous,
                "runtime_result": {"mode": "content_rewrite_runtime"},
            }
        else:
            output = {}
        return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})


class ForbiddenResidualRewriteClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "普通记录",
                "body": "宝宝今天喝得还行。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            output = {
                "title": "普通记录",
                "body": "宝宝还是在这句里。",
                "runtime_result": {"mode": "content_rewrite_runtime"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class RoyalFrisoStructureRewriteClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "早上这一顿",
                "body": "小家伙醒了，我照例去冲奶。家里这罐还是皇家美素佳儿，他自己跑去拿奶瓶，自己拿着奶瓶喝完就翻身玩去了。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            input_payload = envelope.get("input") or {}
            if input_payload.get("rewrite_source") == "royal_friso_ugc_structure_guard":
                output = {
                    "title": "早上这一顿",
                    "body": "小家伙醒了，我照例去冲奶。家里这罐还是皇家美素佳儿，这一顿喝着还顺。我转身去收拾小毯子。",
                    "runtime_result": {"mode": "content_rewrite_runtime"},
                }
                return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class RoyalFrisoStructureStillBadRewriteClient(RoyalFrisoStructureRewriteClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.rewrite":
            input_payload = envelope.get("input") or {}
            if input_payload.get("rewrite_source") == "royal_friso_ugc_structure_guard":
                output = {
                    "title": "早上这一顿",
                    "body": "小家伙醒了，我照例去冲奶。家里这罐还是皇家美素佳儿，自己拿着奶瓶喝完就翻身玩去了。",
                    "runtime_result": {"mode": "content_rewrite_runtime"},
                }
                return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class NonProductExtremeShortAIFlavorClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "保护力记录",
                "body": "短",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            raise AssertionError("postprocess_blocked item should not enter AI flavor rewrite")
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class FakeProductExperienceLLMReviewer:
    def __init__(self, reviews: list[ProductExperienceLLMReview]):
        self.reviews = list(reviews)
        self.calls = []

    async def review(
        self,
        *,
        title: str | None,
        body: str | None,
        plan: dict | None,
        phrase_review,
        ai_flavor_review=None,
    ):
        self.calls.append(
            {
                "title": title,
                "body": body,
                "plan": plan,
                "phrase_review": phrase_review.model_dump(),
                "ai_flavor_review": ai_flavor_review.model_dump() if ai_flavor_review else None,
            }
        )
        if len(self.calls) <= len(self.reviews):
            return self.reviews[len(self.calls) - 1]
        return ProductExperienceLLMReview(pass_=True, rewrite_required=False, severity="pass")


class FailingProductExperienceLLMReviewer(FakeProductExperienceLLMReviewer):
    async def review(
        self,
        *,
        title: str | None,
        body: str | None,
        plan: dict | None,
        phrase_review,
        ai_flavor_review=None,
    ):
        self.calls.append(
            {
                "title": title,
                "body": body,
                "plan": plan,
                "phrase_review": phrase_review.model_dump(),
                "ai_flavor_review": ai_flavor_review.model_dump() if ai_flavor_review else None,
            }
        )
        raise ValueError("LLM review did not return a JSON object")


class ProductExperienceLLMQualityRewriteClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        capability = envelope.get("capability")
        if capability == "content.generate":
            output = {
                "title": "晚饭后的补货",
                "body": (
                    "晚饭后想了想，旺玥又该补货了。我家吃饭一直不大稳定，"
                    "奶粉算是长期留下的日常营养补充。主要是它补上饭里差的一块，"
                    "孩子也接受，就续上了，当个保底留着。"
                ),
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if capability == "content.rewrite":
            input_payload = envelope.get("input") or {}
            if input_payload.get("rewrite_source") == "product_experience_llm_quality_review":
                output = {
                    "title": "晚饭后顺手补",
                    "body": "晚饭后买日用品，顺手把旺玥也补上。家里吃饭不算稳定，这罐就继续当日常营养补充留着。",
                    "final": {
                        "title": "晚饭后顺手补",
                        "body": "晚饭后买日用品，顺手把旺玥也补上。家里吃饭不算稳定，这罐就继续当日常营养补充留着。",
                    },
                    "runtime_result": {"mode": "content_rewrite_runtime"},
                }
                return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceLLMLightGenerateClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "朋友问我家喝什么",
                "body": "朋友问我家喝什么，我说旺玥，主要看乳铁蛋白。别的参数我记不住，就这个我能看明白，饭桌还是乱。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceEffectChainLightGenerateClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "放学回来那杯",
                "body": (
                    "放学回来我给他冲一杯旺玥，孩子喝完会自己去玩一会儿，"
                    "状态看着比前阵子稳一点，我心里也踏实些。"
                ),
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class PersonaStyleRewriteClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            input_payload = envelope.get("input") or {}
            business_rule = input_payload.get("business_rule") or {}
            item_no = business_rule.get("item_no") or 1
            return InvokeResult(
                mode="sync",
                stage_call_id=envelope["stage_call_id"],
                output={
                    "title": f"原始标题{item_no}",
                    "body": f"原始正文{item_no}",
                    "runtime_result": {"mode": "runtime_fast"},
                },
                stats={"fake": True},
            )
        if envelope.get("capability") == "content.rewrite":
            input_payload = envelope.get("input") or {}
            previous = input_payload.get("previous_content") or {}
            preset = input_payload.get("rewrite_style_preset") or "unknown"
            return InvokeResult(
                mode="sync",
                stage_call_id=envelope["stage_call_id"],
                output={
                    "title": previous.get("title") or "改写标题",
                    "body": f"{preset} 改写后正文",
                    "final": {"title": previous.get("title") or "改写标题", "body": f"{preset} 改写后正文"},
                    "runtime_result": {"mode": "content_rewrite_runtime"},
                },
                stats={"fake": True},
            )
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class SlowTrackingClient(RuntimeFastDraftReviewClient):
    def __init__(self):
        self.active = 0
        self.max_active = 0

    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class WorkerDownClient:
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        request = httpx.Request("POST", invoke_url)
        raise httpx.ConnectError("connection refused", request=request)


class SimilarDraftRewriteClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        capability = envelope.get("capability")
        if capability == "content.generate":
            output = {
                "title": "相似标题",
                "body": "第一段相同。第二段也相同。第三段继续相同。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if capability == "content.rewrite":
            input_payload = envelope.get("input") or {}
            if input_payload.get("rewrite_source") == "persona_style_rewrite":
                previous = input_payload.get("previous_content") or {}
                return InvokeResult(
                    mode="sync",
                    stage_call_id=envelope["stage_call_id"],
                    output={
                        "title": previous.get("title") or "相似标题",
                        "body": previous.get("body") or "第一段相同。第二段也相同。第三段继续相同。",
                    },
                    stats={"fake": True},
                )
            rewrite_report = input_payload.get("review_report") or {}
            output = {
                "title": "降重后的标题",
                "body": f"换一个开头和结构来写。触发原因：{rewrite_report.get('rewrite_reason')}",
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class StillSimilarRewriteClient(SimilarDraftRewriteClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.rewrite":
            output = {"title": "仍然相似", "body": "第一段相同。第二段也相同。第三段继续相同。"}
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperiencePhraseRewriteClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        capability = envelope.get("capability")
        if capability == "content.generate":
            output = {
                "title": "接娃回来先换件衣服",
                "body": (
                    "接娃回来先换衣服，杯子放餐边柜上。当初选旺玥也是纠结了一阵，跟4段比了半天，"
                    "价格不算便宜，但孩子愿意喝，每次都喝完，最后我就固定下来，心里踏实点。"
                    "最近集体生活接触多，我也没敢说什么效果，先按这个节奏观察。晚饭后再冲一杯，"
                    "孩子捧着杯子坐一会儿。"
                ),
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if capability == "content.rewrite":
            input_payload = envelope.get("input") or {}
            if input_payload.get("rewrite_source") == "persona_style_rewrite":
                previous = input_payload.get("previous_content") or {}
                return InvokeResult(
                    mode="sync",
                    stage_call_id=envelope["stage_call_id"],
                    output={
                        "title": previous.get("title") or "接娃回来先换件衣服",
                        "body": previous.get("body") or "",
                        "final": {"title": previous.get("title") or "接娃回来先换件衣服", "body": previous.get("body") or ""},
                    },
                    stats={"fake": True},
                )
            output = {
                "title": "接娃回来先换件衣服",
                "body": (
                    "接娃回家先换衣服，杯子顺手放餐边柜上。最近集体生活接触的人多，"
                    "我把早上那顿旺玥当日常补给，没敢说什么效果。天气热的时候他会先喝水，"
                    "晚点再看奶量，有时剩半杯我也不催，就按当天状态记一记。饭桌上如果吃得少，"
                    "我会看看一天整体有没有补回来，晚上再顺手记一笔。"
                ),
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceDryPowderCleanupFluencyClient(RuntimeFastDraftReviewClient):
    def __init__(self):
        self.rewrite_inputs: list[dict] = []

    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "又开一罐，接着喝",
                "body": (
                    "家里奶粉罐见底了，赶紧又开一罐旺玥。"
                    "有妈妈问怎么选的，我就说冲着乳铁蛋白去的，孩子愿意喝就行。"
                    "刚开罐那会他凑过来看，我舀了一勺放他嘴里，他笑着说好喝。"
                ),
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            input_payload = envelope.get("input") or {}
            self.rewrite_inputs.append(input_payload)
            if input_payload.get("rewrite_source") == "product_experience_phrase_guard":
                output = {
                    "title": "又开一罐，接着喝",
                    "body": "家里奶粉罐见底了，赶紧又开一罐旺玥。有妈妈问怎么选的，我就说冲着乳铁蛋白去的，孩子愿意喝就行。",
                    "runtime_result": {"mode": "content_rewrite_runtime"},
                }
                return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceDryPowderStillBadRewriteClient(ProductExperienceDryPowderCleanupFluencyClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.rewrite":
            input_payload = envelope.get("input") or {}
            self.rewrite_inputs.append(input_payload)
            if input_payload.get("rewrite_source") == "product_experience_phrase_guard":
                output = {
                    "title": "又开一罐，接着喝",
                    "body": (
                        "家里奶粉罐见底了，赶紧又开一罐旺玥。"
                        "刚开罐那会他凑过来看，我舀了一勺放他嘴里，他笑着说好喝。"
                    ),
                    "runtime_result": {"mode": "content_rewrite_runtime"},
                }
                return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceTemporaryRemedyRewriteClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        capability = envelope.get("capability")
        if capability == "content.generate":
            output = {
                "title": "带娃出门后的小担心",
                "body": (
                    "带娃出去玩了几天，回来小皮孩就哈啾了两声，我有点紧张。"
                    "平常在外面摸这摸那的，接触的人也多，总担心他防不住。"
                    "思来想去还是把家里喝的旺玥给他换上了，就图它保护力这块能兜住。"
                ),
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if capability == "content.rewrite":
            output = {
                "title": "带娃出门后的小担心",
                "body": (
                    "带娃出去玩了几天，我才发现小朋友接触人多这事真会让人多想。"
                    "家里日常喝旺玥，主要就是看中保护力这块，别的我也不敢说满。"
                ),
                "runtime_result": {"mode": "content_rewrite_runtime"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceTemporalContextClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "感冒季这阵旺玥没断",
                "body": "幼儿园接触人多，我还是担心孩子容易中招。天气忽冷忽热时，家里一直喝旺玥，支持保护力，希望这学期少操点心。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            output = {
                "title": "幼儿园接触多这事",
                "body": "幼儿园接触人多，我还是担心孩子容易中招。家里一直喝旺玥，主要看保护力这块，先按日常情况记一笔。",
                "final": {
                    "title": "幼儿园接触多这事",
                    "body": "幼儿园接触人多，我还是担心孩子容易中招。家里一直喝旺玥，主要看保护力这块，先按日常情况记一笔。",
                },
                "runtime_result": {"mode": "content_rewrite_runtime"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceTimeEventStillBadClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "集体活动后状态稳",
                "body": (
                    "上次幼儿园组织秋游，一大群孩子在外面疯跑了一天。"
                    "回来我还担心他会蔫，结果洗完澡精神头还挺足。"
                    "后来选奶粉重点看保护力，旺玥乳铁蛋白和HMO都有。"
                ),
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            input_payload = envelope.get("input") or {}
            if input_payload.get("rewrite_source") == "product_experience_phrase_guard":
                output = {
                    "title": "集体活动后状态稳",
                    "body": (
                        "上次幼儿园组织秋游，一大群孩子在外面疯跑了一天。"
                        "回来我还担心他会蔫，结果洗完澡精神头还挺足。"
                        "后来选奶粉重点看保护力，旺玥乳铁蛋白和HMO都有。"
                    ),
                    "final": {
                        "title": "集体活动后状态稳",
                        "body": (
                            "上次幼儿园组织秋游，一大群孩子在外面疯跑了一天。"
                            "回来我还担心他会蔫，结果洗完澡精神头还挺足。"
                            "后来选奶粉重点看保护力，旺玥乳铁蛋白和HMO都有。"
                        ),
                    },
                    "runtime_result": {"mode": "content_rewrite_runtime"},
                }
                return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
            raise AssertionError("AI flavor should not run after blocking product-experience residue")
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ExtremeShortArticleLengthClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "今天这杯旺玥",
                "body": "旺玥喝着挺顺。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            raise AssertionError("article length guard should mark unusable without LLM rewrite")
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class MouthPhraseRewriteIntroducesProductIssueClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "旺玥记录",
                "body": "旺玥喝了一阵，孩子每天照常喝。最近背上摸着有点肉，饭桌也没那么难聊，我先记一笔，也算顺。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            output = {
                "title": "旺玥记录",
                "body": "旺玥喝了一阵，孩子每天照常喝。换季背上摸着有点肉，饭桌也没那么难聊，我先记一笔，也算顺。",
                "final": {
                    "title": "旺玥记录",
                    "body": "旺玥喝了一阵，孩子每天照常喝。换季背上摸着有点肉，饭桌也没那么难聊，我先记一笔，也算顺。",
                },
                "runtime_result": {"mode": "content_rewrite_runtime"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class MouthPhraseRewriteCleansSoftPhraseClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "旺玥记录",
                "body": "选旺玥主要看眼脑营养和保护力，孩子日常喝着还行，饭桌不算太折腾，孩子也能接受，我图个安心。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            output = {
                "title": "旺玥记录",
                "body": "选旺玥主要看眼脑营养和保护力，孩子日常喝着还行，饭桌不算太折腾，孩子也能接受，我图个实在。",
                "final": {
                    "title": "旺玥记录",
                    "body": "选旺玥主要看眼脑营养和保护力，孩子日常喝着还行，饭桌不算太折腾，孩子也能接受，我图个实在。",
                },
                "runtime_result": {"mode": "content_rewrite_runtime"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceCommonAiClosureClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "娃出门多了，老母亲心里没底",
                "body": "家里一直喝旺玥，孩子状态也还行。希望能一直这样省心，继续观察看看，先这样喂着吧。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            output = {
                "title": "娃接触多了我会多想点",
                "body": "家里一直喝旺玥，孩子状态也还行。集体环境接触多的时候，我会多看一眼保护力这块。",
                "final": {
                    "title": "娃接触多了我会多想点",
                    "body": "家里一直喝旺玥，孩子状态也还行。集体环境接触多的时候，我会多看一眼保护力这块。",
                },
                "runtime_result": {"mode": "content_rewrite_runtime"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceOddPhraseClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "这阵体格挺打底",
                "body": "最近孩子接触人多，我选旺玥也是看中保护力。一杯下去又活过来了，也没有动不动就掉状态。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            output = {
                "title": "孩子接触人多我会多看一眼",
                "body": "孩子接触人多，我选旺玥也是看中保护力。平时状态看着还可以，我就按日常情况记一笔。",
                "final": {
                    "title": "孩子接触人多我会多看一眼",
                    "body": "孩子接触人多，我选旺玥也是看中保护力。平时状态看着还可以，我就按日常情况记一笔。",
                },
                "runtime_result": {"mode": "content_rewrite_runtime"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceSemanticOddRewriteClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "他们班最近手足口停课了",
                "body": (
                    "他们班最近手足口停课了，我居然还有点庆幸。"
                    "我家这个户外疯玩、回家也不怎么蔫的小马达，保护力这块目前看还挺扛得住。"
                    "家里喝的旺玥，算是我当初挑得最对的一笔。"
                ),
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            output = {
                "title": "幼儿园接触多这事",
                "body": (
                    "孩子在幼儿园接触人多，我确实会多留意保护力。"
                    "家里喝旺玥，日常状态还不错，户外玩回来也没怎么蔫，先按这个节奏记一笔。"
                ),
                "final": {
                    "title": "幼儿园接触多这事",
                    "body": (
                        "孩子在幼儿园接触人多，我确实会多留意保护力。"
                        "家里喝旺玥，日常状态还不错，户外玩回来也没怎么蔫，先按这个节奏记一笔。"
                    ),
                },
                "runtime_result": {"mode": "content_rewrite_runtime"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceAdultSelfDrinkingRewriteClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "写作业那晚顺手开了旺玥",
                "body": "晚上陪孩子写作业，顺手开了新到的旺玥，给自己冲一杯尝了下。孩子在旁边写写画画，我就当日常记录一下。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            output = {
                "title": "写作业那晚看了眼旺玥",
                "body": "晚上陪孩子写作业，我顺手看了下新到的旺玥。给孩子选这款，主要还是看日常营养和保护力，别的先不展开。",
                "final": {
                    "title": "写作业那晚看了眼旺玥",
                    "body": "晚上陪孩子写作业，我顺手看了下新到的旺玥。给孩子选这款，主要还是看日常营养和保护力，别的先不展开。",
                },
                "runtime_result": {"mode": "content_rewrite_runtime"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceBabyMilkActionClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "给娃喝奶粉的日常小记录",
                "body": "早上冲奶时娃自己抱着奶瓶咕嘟咕嘟喝。晚上看他每天主动去泡奶喝，孩子自己倒水舀粉，我也就继续给旺玥续上。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            output = {
                "title": "给娃喝奶粉的日常小记录",
                "body": "给孩子选旺玥儿童奶粉，主要是想补充营养、支持成长。喝奶动作不展开，就按儿童奶粉这块记一下。",
                "final": {
                    "title": "给娃喝奶粉的日常小记录",
                    "body": "给孩子选旺玥儿童奶粉，主要是想补充营养、支持成长。喝奶动作不展开，就按儿童奶粉这块记一下。",
                },
                "runtime_result": {"mode": "content_rewrite_runtime"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceGrowthNutritionDriftClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "这罐还真选对了",
                "body": "孩子饭量上来了，身高体重曲线也好看，每天冲一杯就一步搞定，成长营养这块不用补这补那。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            output = {
                "title": "给孩子选旺玥这事",
                "body": "给孩子选旺玥儿童奶粉，我主要是想把成长阶段的营养认真顾到。看下来营养配得比较全，也符合我对日常成长支持的期待。",
                "final": {
                    "title": "给孩子选旺玥这事",
                    "body": "给孩子选旺玥儿童奶粉，我主要是想把成长阶段的营养认真顾到。看下来营养配得比较全，也符合我对日常成长支持的期待。",
                },
                "runtime_result": {"mode": "content_rewrite_runtime"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceGrowthNutritionRetryClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "给孩子选奶粉这事",
                "body": "给孩子选旺玥，就是觉得它配方挺全，一罐搞定成长营养，孩子喝得顺口。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            input_payload = envelope.get("input") or {}
            if input_payload.get("rewrite_round") == 1:
                output = {
                    "title": "给孩子选奶粉这事",
                    "body": "给孩子选旺玥，主要还是看成长阶段营养能不能顾到。配方这块我觉得挺合适。",
                    "final": {
                        "title": "给孩子选奶粉这事",
                        "body": "给孩子选旺玥，主要还是看成长阶段营养能不能顾到。配方这块我觉得挺合适。",
                    },
                    "runtime_result": {"mode": "content_rewrite_runtime"},
                }
            else:
                output = {
                    "title": "给孩子选奶粉这事",
                    "body": "给孩子选旺玥儿童奶粉，主要还是想把成长阶段的营养认真顾到。别的先不展开，适合现阶段就行。",
                    "final": {
                        "title": "给孩子选奶粉这事",
                        "body": "给孩子选旺玥儿童奶粉，主要还是想把成长阶段的营养认真顾到。别的先不展开，适合现阶段就行。",
                    },
                    "runtime_result": {"mode": "content_rewrite_runtime"},
                }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceGrowthNutritionRetryStillFailsClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "给孩子选奶粉这事",
                "body": "给孩子选旺玥，就是觉得它配方挺全，一罐搞定成长营养，孩子喝着顺口。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            output = {
                "title": "给孩子选奶粉这事",
                "body": "给孩子选旺玥儿童奶粉，主要还是看成长阶段营养能不能顾到，配方该有的都有，喝着也挺合适。",
                "final": {
                    "title": "给孩子选奶粉这事",
                    "body": "给孩子选旺玥儿童奶粉，主要还是看成长阶段营养能不能顾到，配方该有的都有，喝着也挺合适。",
                },
                "runtime_result": {"mode": "content_rewrite_runtime"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceBabyMilkActionResidualClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "喝奶这事终于顺了点",
                "body": "每天自己倒着喝，晚上自己每天冲一杯，喝完还把碗底舔干净。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            output = {
                "title": "喝奶这事终于顺了点",
                "body": "晚上自己每天冲一杯，喝完还把碗底舔干净。",
                "final": {
                    "title": "喝奶这事终于顺了点",
                    "body": "晚上自己每天冲一杯，喝完还把碗底舔干净。",
                },
                "runtime_result": {"mode": "content_rewrite_runtime"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceRow2DrinkingActionClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "活动量大，营养真不能糊弄",
                "body": "孩子每天疯跑，家里常备旺玥，平时在家随手给他冲一杯，反正孩子愿意喝。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            output = {
                "title": "家里聊到孩子状态，我才想起这事",
                "body": "家里聊到孩子平时状态，我才想起儿童奶粉这块也该认真点。给孩子选皇家美素佳儿旺玥，主要是日常营养和保护力这块会看一眼。",
                "final": {
                    "title": "家里聊到孩子状态，我才想起这事",
                    "body": "家里聊到孩子平时状态，我才想起儿童奶粉这块也该认真点。给孩子选皇家美素佳儿旺玥，主要是日常营养和保护力这块会看一眼。",
                },
                "runtime_result": {"mode": "content_rewrite_runtime"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceRow2DrinkingActionRetryClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "接娃路上她跟小朋友追跑",
                "body": "接娃路上她跟小朋友追跑，我在后面慢慢跟着。白天消耗这么大，家里旺玥就是给她选的，营养和保护力都搭上了，放学先喝一杯当过渡。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            input_payload = envelope.get("input") or {}
            if input_payload.get("rewrite_round") == 1:
                output = {
                    "title": "接娃路上她跟小朋友追跑",
                    "body": "接娃路上她跟小朋友追跑，我在后面慢慢跟着。白天消耗这么大，家里旺玥就是给她选的，营养和保护力都搭上了，放学先喝一杯。",
                    "final": {
                        "title": "接娃路上她跟小朋友追跑",
                        "body": "接娃路上她跟小朋友追跑，我在后面慢慢跟着。白天消耗这么大，家里旺玥就是给她选的，营养和保护力都搭上了，放学先喝一杯。",
                    },
                    "runtime_result": {"mode": "content_rewrite_runtime"},
                }
            else:
                output = {
                    "title": "接娃路上她跟小朋友追跑",
                    "body": "接娃路上她跟小朋友追跑，我在后面慢慢跟着。白天消耗这么大，家里旺玥就是给她选的，营养和保护力都搭上了。",
                    "final": {
                        "title": "接娃路上她跟小朋友追跑",
                        "body": "接娃路上她跟小朋友追跑，我在后面慢慢跟着。白天消耗这么大，家里旺玥就是给她选的，营养和保护力都搭上了。",
                    },
                    "runtime_result": {"mode": "content_rewrite_runtime"},
                }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceWangyueContextClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "源悦真实体验分享",
                "body": "宝宝一岁多后出门多，我就在书包侧袋塞一盒旺玥，临时兑点温水摇匀。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceChildProductPromoClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "自己跟旁边的小孩说你也来一杯吧",
                "body": (
                    "那天我们在小区玩，旁边小朋友在喝奶，她突然跑过来跟人家说“我家也有，你要不要来一杯”。"
                    "我才想起来旺玥是上个月买的，当时就是看她老往外跑，想着保护力这块得跟上。"
                ),
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            output = {
                "title": "小区玩完回来那一笔",
                "body": (
                    "那天在小区玩到快天黑，她回来还挺有精神。我才想起上个月给孩子选了旺玥，"
                    "主要就是看中儿童奶粉里保护力这块，平时活动多的时候我会多留意一点。"
                ),
                "final": {
                    "title": "小区玩完回来那一笔",
                    "body": (
                        "那天在小区玩到快天黑，她回来还挺有精神。我才想起上个月给孩子选了旺玥，"
                        "主要就是看中儿童奶粉里保护力这块，平时活动多的时候我会多留意一点。"
                    ),
                },
                "runtime_result": {"mode": "content_rewrite_runtime"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ProductExperienceWangyueDigestiveContextClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "这罐喝着还顺",
                "body": "旺玥喝了快两周，孩子肚子软软的，便便也规律了，之前不是胀气就是不爱喝，现在日常状态还可以。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class AIFlavorHumanizerRewriteClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "拼图那阵，选奶看了眼脑",
                "body": (
                    "女儿最近拼图能坐挺久，小眼睛盯着碎片找，我就开始留意儿童奶粉里的眼脑营养。"
                    "之前挑奶粉时对比过几款，旺玥有DHA和燕窝酸，算是当时记住的一个点吧。"
                    "不是要说喝了怎么样，就是日常选择里多一层考虑。"
                ),
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            input_payload = envelope.get("input") or {}
            if input_payload.get("rewrite_source") == "ai_flavor_humanizer":
                output = {
                    "title": "最近迷上拼图",
                    "body": (
                        "最近她迷上拼图，能趴在桌边折腾半天，眼睛离得近我就会提醒一句。"
                        "也是那阵子，我选儿童奶粉时顺手多看了眼脑营养，旺玥里面有DHA和燕窝酸。"
                    ),
                    "final": {
                        "title": "最近迷上拼图",
                        "body": (
                            "最近她迷上拼图，能趴在桌边折腾半天，眼睛离得近我就会提醒一句。"
                            "也是那阵子，我选儿童奶粉时顺手多看了眼脑营养，旺玥里面有DHA和燕窝酸。"
                        ),
                    },
                    "runtime_result": {"mode": "content_rewrite_runtime"},
                }
                return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class AIFlavorHumanizerTitleOnlyRewriteClient(RuntimeFastDraftReviewClient):
    generated_body = (
        "当时选儿童奶粉，最在意的就是保护力。听别人说归听，还是看自家孩子的情况。"
        "后来选了旺玥，它的乳铁蛋白和HMO，刚好能接住我对孩子状态稳的期待。现在喝下来，状态确实稳。"
    )
    weakened_body = (
        "选奶粉那会儿啊，我最在意的就是孩子状态稳不稳。听别人说归听，最后还是看自家娃。"
        "后来选了旺玥，它的乳铁蛋白蛮对路子。现在喝下来，状态确实稳。"
    )

    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "保护力那关，旺玥稳了",
                "body": self.generated_body,
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            input_payload = envelope.get("input") or {}
            if input_payload.get("rewrite_source") == "ai_flavor_humanizer":
                output = {
                    "title": "状态稳了",
                    "body": self.weakened_body,
                    "final": {
                        "title": "状态稳了",
                        "body": self.weakened_body,
                    },
                    "runtime_result": {"mode": "content_rewrite_runtime"},
                }
                return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class AIFlavorHumanizerIntroducesTimeEventClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "选奶复盘，出勤稳了",
                "body": (
                    "上周幼儿园组织户外活动，几个妈妈在一边聊天，我注意到自家娃全程跟着队伍跑跳。"
                    "回想当时选儿童奶粉，我特意看了保护力相关的配方。"
                    "不是要说全是奶粉功劳，就是日常选择里多一层考虑。"
                ),
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            input_payload = envelope.get("input") or {}
            if input_payload.get("rewrite_source") == "ai_flavor_humanizer":
                output = {
                    "title": "春游回来还是那个状态",
                    "body": (
                        "上周幼儿园春游，几个妈妈凑一块聊天，我盯了一眼自家娃，"
                        "全程跟着队伍跑，午饭时也没蔫。"
                        "当初选奶粉那会儿，旺玥就是因为有乳铁蛋白和HMO才留下的。"
                    ),
                    "final": {
                        "title": "春游回来还是那个状态",
                        "body": (
                            "上周幼儿园春游，几个妈妈凑一块聊天，我盯了一眼自家娃，"
                            "全程跟着队伍跑，午饭时也没蔫。"
                            "当初选奶粉那会儿，旺玥就是因为有乳铁蛋白和HMO才留下的。"
                        ),
                    },
                    "runtime_result": {"mode": "content_rewrite_runtime"},
                }
                return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class AIFlavorHumanizerIntroducesForbiddenTermClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "拼图那阵，选奶看了眼脑",
                "body": (
                    "女儿最近拼图能坐挺久，我就开始留意儿童奶粉里的眼脑营养。"
                    "旺玥有DHA和燕窝酸，算是当时记住的一个点。"
                    "不是要说喝了怎么样，就是日常选择里多一层考虑。"
                ),
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            input_payload = envelope.get("input") or {}
            if input_payload.get("rewrite_source") == "ai_flavor_humanizer":
                output = {
                    "title": "最近迷上拼图",
                    "body": (
                        "最近她迷上拼图，能趴在桌边折腾半天。"
                        "也是那阵子，我选儿童奶粉时顺手多看了眼脑营养，"
                        "旺玥里面有DHA和燕窝酸，想着她体质跟得上就行。"
                    ),
                    "final": {
                        "title": "最近迷上拼图",
                        "body": (
                            "最近她迷上拼图，能趴在桌边折腾半天。"
                            "也是那阵子，我选儿童奶粉时顺手多看了眼脑营养，"
                            "旺玥里面有DHA和燕窝酸，想着她体质跟得上就行。"
                        ),
                    },
                    "runtime_result": {"mode": "content_rewrite_runtime"},
                }
                return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
            if input_payload.get("forbidden_hits") == ["体质"]:
                output = {
                    "title": "最近迷上拼图",
                    "body": (
                        "最近她迷上拼图，能趴在桌边折腾半天。"
                        "也是那阵子，我选儿童奶粉时顺手多看了眼脑营养，"
                        "旺玥里面有DHA和燕窝酸，想着她状态跟得上就行。"
                    ),
                    "final": {
                        "title": "最近迷上拼图",
                        "body": (
                            "最近她迷上拼图，能趴在桌边折腾半天。"
                            "也是那阵子，我选儿童奶粉时顺手多看了眼脑营养，"
                            "旺玥里面有DHA和燕窝酸，想着她状态跟得上就行。"
                        ),
                    },
                    "runtime_result": {"mode": "content_rewrite_runtime"},
                }
                return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class AIFlavorHumanizerRetryRewriteClient(RuntimeFastDraftReviewClient):
    def __init__(self):
        self.rewrite_count = 0

    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "入园后看保护力",
                "body": "娃入园后接触的人多，我选奶时看了保护力。不是说喝了就怎样，只是多看一眼。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            input_payload = envelope.get("input") or {}
            if input_payload.get("rewrite_source") == "ai_flavor_humanizer":
                self.rewrite_count += 1
                if self.rewrite_count == 1:
                    output = {
                        "title": "入园后看保护力",
                        "body": "娃入园后接触的人多，我选奶时还是会多看保护力。旺玥当时留下印象。",
                        "final": {
                            "title": "入园后看保护力",
                            "body": "娃入园后接触的人多，我选奶时还是会多看保护力。旺玥当时留下印象。",
                        },
                        "runtime_result": {"mode": "content_rewrite_runtime"},
                    }
                else:
                    output = {
                        "title": "入园后那阵",
                        "body": "娃入园后接触的人多，我选儿童奶粉时会多看保护力这块。旺玥当时让我记住的是乳铁蛋白这个点。",
                        "final": {
                            "title": "入园后那阵",
                            "body": "娃入园后接触的人多，我选儿童奶粉时会多看保护力这块。旺玥当时让我记住的是乳铁蛋白这个点。",
                        },
                        "runtime_result": {"mode": "content_rewrite_runtime"},
                    }
                return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


@pytest.mark.asyncio
async def test_batch_execution_runs_items_with_configured_concurrency():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_concurrent",
            asset_key="yuanyue",
            product_topic="宝宝便便不规律",
            target_audience="新手妈妈",
            style="经验老道型",
            count=6,
            status="planned",
        )
        session.add(job)
        await session.flush()
        for item_no in range(1, 7):
            plan = _plan(((item_no - 1) % 3) + 1)
            plan["item_no"] = item_no
            session.add(ContentBatchItem(batch_id=job.id, item_no=item_no, status="planned", plan_json=plan))
        await session.commit()

        client = SlowTrackingClient()
        service = ContentBatchExecutionService(
            session,
            invocation_client=client,
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=6, concurrency=5, created_by="test")
        await session.commit()

    assert result.generated_count == 6
    assert result.failed_count == 0
    assert client.max_active == 5


@pytest.mark.asyncio
async def test_batch_execution_reports_worker_start_hint_when_executor_is_unreachable():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://127.0.0.1:8766/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_worker_down",
            asset_key="yuanyue",
            product_topic="宝宝便便不规律",
            target_audience="新手妈妈",
            style="经验老道型",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=_plan(1)))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=WorkerDownClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 0
    assert result.failed_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage = (await session.execute(select(ContentAgentStageCall))).scalar_one()

    assert item.status == "failed"
    assert item.run_id == stage.run_id
    assert "make worker-start" in item.error_message
    assert stage.status == "failed"
    assert "make worker-start" in stage.error_message


@pytest.mark.asyncio
async def test_batch_execution_rewrites_later_item_when_similarity_is_too_high():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_similarity",
            asset_key="yuanyue",
            product_topic="宝宝便便不规律",
            target_audience="新手妈妈",
            style="经验老道型",
            count=2,
            status="planned",
        )
        session.add(job)
        await session.flush()
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=_plan(1)))
        session.add(ContentBatchItem(batch_id=job.id, item_no=2, status="planned", plan_json=_plan(2)))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=SimilarDraftRewriteClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=2, concurrency=2, created_by="test")
        await session.commit()

    assert result.generated_count == 2
    async with session_factory() as session:
        items = (
            await session.execute(select(ContentBatchItem).where(ContentBatchItem.batch_id == job.id).order_by(ContentBatchItem.item_no))
        ).scalars().all()
        stage_calls = (
            await session.execute(select(ContentAgentStageCall).order_by(ContentAgentStageCall.sequence_no))
        ).scalars().all()

    assert items[0].body == "第一段相同。第二段也相同。第三段继续相同。"
    assert items[1].title == "降重后的标题"
    assert "触发原因" in items[1].body
    similarity_rewrites = items[1].quality_json["similarity_rewrites"]
    assert similarity_rewrites[0]["similar_item_no"] == 1
    assert similarity_rewrites[0]["similarity_score"] >= 0.42
    assert similarity_rewrites[0]["similarity_rewrite_passed"] is True
    assert similarity_rewrites[0]["post_rewrite_similarity_score"] < 0.42
    assert items[1].quality_json["review_report"]["rewrite_required"] is False
    assert any(stage.capability == "content.rewrite" for stage in stage_calls)
    rewrite_stage = next(
        stage
        for stage in stage_calls
        if stage.capability == "content.rewrite" and (stage.input_snapshot or {}).get("rewrite_source") != "persona_style_rewrite"
    )
    instructions = "\n".join((rewrite_stage.input_snapshot or {}).get("rewrite_instructions") or [])
    assert "优先删除或压缩" in instructions
    assert "不要为了多样化扩写新情节" in instructions


@pytest.mark.asyncio
async def test_batch_execution_checks_recent_history_for_similarity():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        history_job = ContentBatchJob(
            batch_code="batch_history",
            asset_key="yuanyue",
            product_topic="宝宝便便不规律",
            target_audience="新手妈妈",
            style="经验老道型",
            count=1,
            status="generated",
        )
        current_job = ContentBatchJob(
            batch_code="batch_current",
            asset_key="yuanyue",
            product_topic="宝宝便便不规律",
            target_audience="新手妈妈",
            style="经验老道型",
            count=1,
            status="planned",
        )
        session.add_all([history_job, current_job])
        await session.flush()
        session.add(
            ContentBatchItem(
                batch_id=history_job.id,
                item_no=1,
                status="generated",
                plan_json=_plan(1),
                title="历史标题",
                body="第一段相同。第二段也相同。第三段继续相同。",
            )
        )
        session.add(ContentBatchItem(batch_id=current_job.id, item_no=1, status="planned", plan_json=_plan(1)))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=SimilarDraftRewriteClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(current_job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (
            await session.execute(select(ContentBatchItem).where(ContentBatchItem.batch_id == current_job.id))
        ).scalar_one()

    assert item.title == "降重后的标题"
    rewrite = item.quality_json["similarity_rewrites"][0]
    assert rewrite["scope"] == "history"
    assert rewrite["similar_batch_id"] == history_job.id
    assert rewrite["threshold"] == 0.48
    assert item.quality_json["review_report"]["rewrite_required"] is False


@pytest.mark.asyncio
async def test_batch_execution_marks_manual_review_when_similarity_rewrite_still_high():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_still_similar",
            asset_key="yuanyue",
            product_topic="宝宝便便不规律",
            target_audience="新手妈妈",
            style="经验老道型",
            count=2,
            status="planned",
        )
        session.add(job)
        await session.flush()
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=_plan(1)))
        session.add(ContentBatchItem(batch_id=job.id, item_no=2, status="planned", plan_json=_plan(2)))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=StillSimilarRewriteClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=2, concurrency=2, created_by="test")
        await session.commit()

    assert result.generated_count == 2
    async with session_factory() as session:
        item = (
            await session.execute(
                select(ContentBatchItem).where(ContentBatchItem.batch_id == job.id, ContentBatchItem.item_no == 2)
            )
        ).scalar_one()

    assert len(item.quality_json["similarity_rewrites"]) == 2
    assert item.quality_json["similarity_rewrites"][-1]["similarity_rewrite_passed"] is False
    assert item.quality_json["review_report"]["rewrite_required"] is True
    assert "需要人工处理" in item.quality_json["review_report"]["rewrite_reason"]


@pytest.mark.asyncio
async def test_batch_execution_deletes_dry_powder_then_llm_checks_fluency_once():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    client = ProductExperienceDryPowderCleanupFluencyClient()
    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_dry_powder_cleanup_fluency",
            asset_key="article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "article_business_rules",
            "business_rule": "复购/长期使用，容易中招",
            "topic": "复购/长期使用，容易中招",
            "corpus": "写作规则：0705旺玥活动。复购/长期使用。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=client,
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    full_text = f"{item.title}\n{item.body}"
    assert "舀了一勺" not in full_text
    assert "放他嘴里" not in full_text
    assert "product_experience_formula_dry_powder_cleanups" in item.quality_json
    rewrites = item.quality_json["product_experience_phrase_rewrites"]
    assert len(rewrites) == 1
    assert "post_delete_cleanup_fluency_check" in rewrites[0]["pre_review"]["reasons"]
    assert rewrites[0]["passed"] is True
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    phrase_rewrite_stages = [
        stage
        for stage in stage_calls
        if stage.capability == "content.rewrite"
        and (stage.input_snapshot or {}).get("rewrite_source") == "product_experience_phrase_guard"
    ]
    assert len(phrase_rewrite_stages) == 1
    rewrite_input = client.rewrite_inputs[0]
    assert "舀了一勺" not in rewrite_input["previous_content"]["body"]
    assert "放他嘴里" not in rewrite_input["previous_content"]["body"]
    instructions = "\n".join(rewrite_input["rewrite_instructions"])
    assert "删除后的标题和正文是否出现残句" in instructions
    assert "不要新增冲泡、喝奶、试喝" in instructions


@pytest.mark.asyncio
async def test_batch_execution_marks_manual_when_phrase_rewrite_still_fails_rule_review():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    client = ProductExperienceDryPowderStillBadRewriteClient()
    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_dry_powder_still_bad",
            asset_key="article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "article_business_rules",
            "business_rule": "复购/长期使用，容易中招",
            "topic": "复购/长期使用，容易中招",
            "corpus": "写作规则：0705旺玥活动。复购/长期使用。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=client,
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert "舀了一勺" in item.body
    rewrites = item.quality_json["product_experience_phrase_rewrites"]
    assert len(rewrites) == 1
    assert rewrites[0]["passed"] is False
    guard = item.quality_json["product_experience_phrase_guard"]
    assert guard["pass"] is False
    assert guard["rewrite_required"] is True
    assert "formula_dry_powder_ingestion" in guard["reasons"]
    assert item.quality_json["review_report"]["rewrite_required"] is True
    assert item.quality_json["review_report"]["rewrite_reason"] == "业务规则口癖骨架或长度仍需人工处理"
    phrase_rewrite_stages = [
        stage
        for stage in stage_calls
        if stage.capability == "content.rewrite"
        and (stage.input_snapshot or {}).get("rewrite_source") == "product_experience_phrase_guard"
    ]
    assert len(phrase_rewrite_stages) == 1


@pytest.mark.asyncio
async def test_batch_execution_skips_persona_rewrite_for_wangyue_article_business_rule():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_phrase_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "容易中招，日常保护力",
            "topic": "容易中招，日常保护力",
            "corpus": "## 业务规则\n篇幅类型：中短文；正文按130字左右写，可在120-150字之间。\n活动：0705旺玥活动。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperiencePhraseRewriteClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert "价格不算便宜" in item.body
    assert "固定下来" in item.body
    guard = item.quality_json["product_experience_phrase_guard"]
    assert guard["pass"] is False
    assert guard["rewrite_required"] is True
    assert "product_experience_phrase_rewrites" not in item.quality_json
    assert "persona_style_rewrites" not in item.quality_json
    assert item.quality_json["review_report"]["rewrite_required"] is True
    assert sum(1 for stage in stage_calls if stage.capability == "content.rewrite") == 0


@pytest.mark.asyncio
async def test_batch_execution_rewrites_wangyue_after_symptom_remedy_chain():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_temporary_remedy_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "容易中招，日常保护力",
            "topic": "容易中招，日常保护力",
            "corpus": "写作规则：孩子接触人多后，妈妈担心容易中招；旺玥支持孩子保护力。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceTemporaryRemedyRewriteClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    full_text = f"{item.title}\n{item.body}"
    assert "哈啾" not in full_text
    assert "换上" not in full_text
    assert "旺玥" in full_text
    rewrites = item.quality_json["product_experience_phrase_rewrites"]
    assert rewrites[0]["pre_review"]["hard_risk_hits"]
    assert rewrites[0]["passed"] is True
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    assert sum(1 for stage in stage_calls if stage.capability == "content.rewrite") == 1


@pytest.mark.asyncio
async def test_batch_execution_cleans_temporal_context_for_wangyue_article_business_rule():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_temporal_context_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "容易中招，日常保护力",
            "topic": "容易中招，日常保护力",
            "corpus": "写作规则：孩子接触人多后，妈妈担心容易中招；旺玥支持孩子保护力。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceTemporalContextClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    full_text = f"{item.title}\n{item.body}"
    assert "换季" not in full_text
    assert "感冒季" not in full_text
    assert "天气忽冷忽热" not in full_text
    assert "天气一变" not in full_text
    assert "学期" not in full_text
    assert "product_experience_temporal_context_cleanups" not in item.quality_json
    assert "product_experience_phrase_rewrites" in item.quality_json
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    assert sum(1 for stage in stage_calls if stage.capability == "content.rewrite") == 1


@pytest.mark.asyncio
async def test_batch_execution_fails_when_wangyue_time_event_residue_survives_rewrite():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_time_event_residue_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "容易中招，日常保护力",
            "topic": "容易中招，日常保护力",
            "corpus": "写作规则：孩子接触人多后，妈妈担心容易中招；旺玥支持孩子保护力。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceTimeEventStillBadClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert item.status == "failed"
    assert "秋游" in item.body
    assert item.error_message == "硬性规则改写后仍命中：秋游"
    quality = item.quality_json
    assert quality["hard_pass"] is False
    assert quality["postprocess_blocked"]["source"] == "product_experience_phrase_guard"
    assert quality["postprocess_blocked"]["hits"] == ["秋游"]
    assert quality["review_report"]["rewrite_required"] is True
    assert quality["review_report"]["rewrite_reason"] == "硬性规则改写失败，需要人工复核"
    assert "product_experience_wangyue_time_event_cleanups" in quality
    phrase_rewrites = quality["product_experience_phrase_rewrites"]
    assert phrase_rewrites[0]["pre_review"]["reasons"] == ["post_delete_cleanup_fluency_check"]
    assert phrase_rewrites[0]["post_review"]["wangyue_time_event_context_hits"] == ["秋游"]
    rewrite_sources = [
        (stage.input_snapshot or {}).get("rewrite_source")
        for stage in stage_calls
        if stage.capability == "content.rewrite"
    ]
    assert rewrite_sources == ["product_experience_phrase_guard"]


@pytest.mark.asyncio
async def test_batch_execution_marks_extreme_short_article_unusable_without_rewrite():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_short_article_length_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "营养不足/成长发育需求，日常补充观察",
            "topic": "营养不足/成长发育需求，日常补充观察",
            "corpus": "写作规则：围绕日常营养补充来写。\n篇幅类型：短文；正文必须40-80字。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ExtremeShortArticleLengthClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert item.body == "旺玥喝着挺顺。"
    assert item.quality_json["article_length_guard"]["status"] == "extreme_short"
    assert item.quality_json["article_length_guard"]["rewrite_required"] is False
    assert item.quality_json["article_length_guard"]["manual_review_required"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is True
    assert item.quality_json["review_report"]["rewrite_reason"] == "正文过短，疑似生成异常"
    assert item.quality_json["hard_pass"] is False
    assert item.quality_json["postprocess_blocked"]["source"] == "article_length_guard"
    assert item.quality_json["postprocess_blocked"]["reasons"] == ["extreme_short"]
    assert all(
        (stage.input_snapshot or {}).get("rewrite_source") != "article_length_guard"
        for stage in stage_calls
        if stage.capability == "content.rewrite"
    )


@pytest.mark.asyncio
async def test_batch_execution_skips_ai_flavor_after_article_length_block():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_short_article_skips_ai_flavor",
            asset_key="yuanyue",
            product_topic="普通话题",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {**_plan(1), "persona_style_rewrite_enabled": False}
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=NonProductExtremeShortAIFlavorClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert item.status == "generated"
    assert item.quality_json["article_length_guard"]["status"] == "extreme_short"
    assert item.quality_json["postprocess_blocked"]["source"] == "article_length_guard"
    assert item.quality_json["hard_pass"] is False
    assert all(stage.capability != "content.rewrite" for stage in stage_calls)


@pytest.mark.asyncio
async def test_mouth_phrase_rewrite_cannot_reintroduce_product_experience_issue():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_mouth_rewrite_product_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "营养不足/成长发育需求，日常补充观察",
            "topic": "营养不足/成长发育需求，日常补充观察",
            "corpus": "写作规则：围绕孩子成长阶段的日常营养补充来写；正文40-130字。",
            "mouth_phrase_budget": {
                "enabled": True,
                "avoid_terms": ["最近"],
                "allowed_terms": [],
                "batch_item_count": 1,
            },
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=MouthPhraseRewriteIntroducesProductIssueClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    full_text = f"{item.title}\n{item.body}"
    assert "换季" not in full_text
    assert "最近" in full_text
    failures = item.quality_json["mouth_phrase_budget_rewrite_failures"]
    assert failures[0]["error_message"] == "blocked_by_product_experience_phrase_guard"
    assert "explicit_temporal_context" in failures[0]["product_experience_phrase_review"]["reasons"]
    assert item.quality_json["mouth_phrase_budget_guard"]["final_hits"] == ["最近"]
    assert sum(1 for stage in stage_calls if stage.capability == "content.rewrite") == 1


@pytest.mark.asyncio
async def test_mouth_phrase_rewrite_refreshes_product_experience_review():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_mouth_rewrite_refreshes_product_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "注意力不集中，眼脑营养观察",
            "topic": "注意力不集中，眼脑营养观察",
            "corpus": "写作规则：旺玥是妈妈给孩子选的儿童奶粉，选择理由是满足眼脑营养需求，也支持孩子保护力。正文40-130字。",
            "mouth_phrase_budget": {
                "enabled": True,
                "avoid_terms": ["安心"],
                "allowed_terms": [],
                "batch_item_count": 1,
            },
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=MouthPhraseRewriteCleansSoftPhraseClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    review = item.quality_json["review_report"]["product_experience_phrase_review"]
    assert "安心" not in item.body
    assert review["ai_phrase_hits"] == []
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["mouth_phrase_budget_guard"]["final_hits"] == []
    assert sum(1 for stage in stage_calls if stage.capability == "content.rewrite") == 1


@pytest.mark.asyncio
async def test_batch_execution_cleans_common_ai_closure_for_wangyue_article_business_rule():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_common_ai_closure_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "容易中招，日常保护力",
            "topic": "容易中招，日常保护力",
            "corpus": "写作规则：孩子接触人多后，妈妈担心容易中招；旺玥支持孩子保护力。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceCommonAiClosureClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert "继续观察看看" not in item.body
    assert "先这样喂着吧" not in item.body
    assert "老母亲" not in f"{item.title}\n{item.body}"
    assert "希望能一直这样省心" not in item.body
    assert "product_experience_common_ai_closure_cleanups" not in item.quality_json
    assert "product_experience_phrase_rewrites" in item.quality_json
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    assert sum(1 for stage in stage_calls if stage.capability == "content.rewrite") == 1


@pytest.mark.asyncio
async def test_batch_execution_cleans_odd_phrases_for_wangyue_article_business_rule():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_odd_phrase_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "容易中招，日常保护力",
            "topic": "容易中招，日常保护力",
            "corpus": "写作规则：孩子接触人多后，妈妈担心容易中招；旺玥支持孩子保护力。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceOddPhraseClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    full_text = f"{item.title}\n{item.body}"
    assert "体格挺打底" not in full_text
    assert "一杯下去又活过来了" not in full_text
    assert "动不动就掉状态" not in full_text
    assert "体格看着挺扎实" not in full_text
    assert "休息一会儿状态能缓过来" not in full_text
    assert "product_experience_odd_phrase_cleanups" not in item.quality_json
    assert "product_experience_phrase_rewrites" in item.quality_json
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    assert sum(1 for stage in stage_calls if stage.capability == "content.rewrite") == 1


@pytest.mark.asyncio
async def test_batch_execution_rewrites_semantic_odd_phrase_for_wangyue_article_business_rule():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_semantic_odd_phrase_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "容易中招，日常保护力",
            "topic": "容易中招，日常保护力",
            "corpus": "写作规则：孩子接触人多后，妈妈担心容易中招；旺玥支持孩子保护力。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceSemanticOddRewriteClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    full_text = f"{item.title}\n{item.body}"
    assert "手足口" not in full_text
    assert "停课" not in full_text
    assert "班里请假停课" not in full_text
    assert "班里班里" not in full_text
    assert "product_experience_odd_phrase_cleanups" not in item.quality_json
    assert "product_experience_phrase_rewrites" in item.quality_json
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    rewrite_stages = [stage for stage in stage_calls if stage.capability == "content.rewrite"]
    assert len(rewrite_stages) == 1
    instructions = "\n".join((rewrite_stages[0].input_snapshot or {}).get("rewrite_instructions") or [])
    assert "敏感表达" in instructions
    assert "不要把它们固定替换成“班里请假/小状况”" in instructions


@pytest.mark.asyncio
async def test_batch_execution_rewrites_adult_self_drinking_for_wangyue_article_business_rule():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_adult_self_drinking_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "营养不足/成长发育需求，日常补充观察",
            "topic": "营养不足/成长发育需求，日常补充观察",
            "corpus": "写作规则：围绕孩子成长阶段的日常营养补充来写；0705旺玥活动。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceAdultSelfDrinkingRewriteClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    full_text = f"{item.title}\n{item.body}"
    assert "给自己冲" not in full_text
    assert "尝了下" not in full_text
    assert "给孩子选" in full_text
    assert "product_experience_adult_self_drinking_cleanups" not in item.quality_json
    assert "product_experience_phrase_rewrites" in item.quality_json
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    rewrite_stages = [stage for stage in stage_calls if stage.capability == "content.rewrite"]
    assert len(rewrite_stages) == 1
    instructions = "\n".join((rewrite_stages[0].input_snapshot or {}).get("rewrite_instructions") or [])
    assert "成人自己喝儿童奶粉" in instructions


@pytest.mark.asyncio
async def test_batch_execution_rewrites_child_self_brewing_action_for_wangyue_article_business_rule():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_baby_milk_action_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "营养不足/成长发育需求，日常补充观察",
            "topic": "营养不足/成长发育需求，日常补充观察",
            "corpus": "写作规则：围绕孩子成长阶段的日常营养补充来写；0705旺玥活动。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceBabyMilkActionClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    full_text = f"{item.title}\n{item.body}"
    assert "奶瓶" not in full_text
    assert "主动去泡奶喝" not in full_text
    assert "自己倒水舀粉" not in full_text
    assert "这款他不怎么抗拒" not in full_text
    assert "主动要喝" not in full_text
    assert "喝得挺顺" not in full_text
    assert "补充营养、支持成长" in full_text
    assert "product_experience_baby_milk_action_cleanups" not in item.quality_json
    assert "product_experience_phrase_rewrites" in item.quality_json
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    rewrite_stages = [stage for stage in stage_calls if stage.capability == "content.rewrite"]
    assert len(rewrite_stages) == 1
    instructions = (rewrite_stages[0].input_snapshot or {}).get("rewrite_instructions") or []
    assert any("孩子自己冲/泡/舀奶粉" in instruction for instruction in instructions)


@pytest.mark.asyncio
async def test_batch_execution_rewrites_wangyue_growth_nutrition_row4_drift():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_growth_nutrition_drift_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 4,
            "business_rule": "营养不足/成长发育需求，儿童奶粉选择",
            "topic": "营养不足/成长发育需求，儿童奶粉选择",
            "corpus": "写作规则：围绕给孩子选择皇家美素佳儿旺玥儿童奶粉来写，理由是补充营养、支持成长；正文40-130字。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceGrowthNutritionDriftClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    full_text = f"{item.title}\n{item.body}"
    assert "饭量" not in full_text
    assert "身高体重曲线" not in full_text
    assert "每天冲一杯" not in full_text
    assert "一步搞定" not in full_text
    assert "补这补那" not in full_text
    assert "给孩子选旺玥儿童奶粉" in full_text
    assert "product_experience_phrase_rewrites" in item.quality_json
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    rewrite_stages = [stage for stage in stage_calls if stage.capability == "content.rewrite"]
    assert len(rewrite_stages) == 1
    instructions = "\n".join((rewrite_stages[0].input_snapshot or {}).get("rewrite_instructions") or [])
    assert "旺玥营养/成长规则漂移" in instructions
    assert "补充营养、支持成长" in instructions


@pytest.mark.asyncio
async def test_batch_execution_retries_wangyue_growth_nutrition_drift_once():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_growth_nutrition_drift_retry",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 4,
            "business_rule": "营养不足/成长发育需求，儿童奶粉选择",
            "topic": "营养不足/成长发育需求，儿童奶粉选择",
            "corpus": "写作规则：围绕给孩子选择皇家美素佳儿旺玥儿童奶粉来写，理由是补充营养、支持成长；正文40-130字。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceGrowthNutritionRetryClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    full_text = f"{item.title}\n{item.body}"
    assert "配方" not in full_text
    assert "一罐搞定" not in full_text
    assert "放学先喝一杯" not in full_text
    assert "成长阶段的营养认真顾到" in full_text
    rewrites = item.quality_json["product_experience_phrase_rewrites"]
    assert len(rewrites) == 2
    assert rewrites[0]["passed"] is False
    assert rewrites[1]["passed"] is True
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    rewrite_stages = [stage for stage in stage_calls if stage.capability == "content.rewrite"]
    assert len(rewrite_stages) == 1
    second_instructions = "\n".join((rewrite_stages[1].input_snapshot or {}).get("rewrite_instructions") or [])
    assert "再次改写" in second_instructions


@pytest.mark.asyncio
async def test_batch_execution_fallback_cleans_wangyue_growth_nutrition_drift_after_retry():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_growth_nutrition_drift_fallback",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "source_row_no": 4,
            "business_rule": "营养不足/成长发育需求，儿童奶粉选择",
            "topic": "营养不足/成长发育需求，儿童奶粉选择",
            "corpus": "写作规则：围绕给孩子选择皇家美素佳儿旺玥儿童奶粉来写，理由是补充营养、支持成长；正文40-130字。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceGrowthNutritionRetryStillFailsClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    full_text = f"{item.title}\n{item.body}"
    assert "配方" not in full_text
    assert "一罐搞定" not in full_text
    assert "喝着" not in full_text
    assert "该有的都有" not in full_text
    assert "挺合适" not in full_text
    assert "给孩子选旺玥儿童奶粉" in full_text
    assert "product_experience_growth_nutrition_fallback_cleanups" in item.quality_json
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    rewrite_stages = [stage for stage in stage_calls if stage.capability == "content.rewrite"]
    assert len(rewrite_stages) >= 2


@pytest.mark.asyncio
async def test_batch_execution_cleans_child_self_brewing_residue_after_rewrite():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_baby_milk_action_residue_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "营养不足/成长发育需求，日常补充观察",
            "topic": "营养不足/成长发育需求，日常补充观察",
            "corpus": "写作规则：围绕孩子成长阶段的日常营养补充来写；0705旺玥活动。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceBabyMilkActionResidualClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    full_text = f"{item.title}\n{item.body}"
    assert "自己每天冲一杯" not in full_text
    assert "自己倒着喝" not in full_text
    assert "碗底舔干净" not in full_text
    assert "每天等我冲一杯" not in full_text
    assert "杯底喝干净" not in full_text
    assert "给孩子选旺玥儿童奶粉" in full_text
    assert "product_experience_growth_nutrition_fallback_cleanups" in item.quality_json
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    assert sum(1 for stage in stage_calls if stage.capability == "content.rewrite") == 1


@pytest.mark.asyncio
async def test_batch_execution_rewrites_row2_drinking_action_residue_with_model():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_row2_drinking_action_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "精力不足，日常状态观察",
            "topic": "精力不足，日常状态观察",
            "source_row_no": 2,
            "corpus": "写作规则：围绕孩子平时活动量大，妈妈为什么会给儿童奶粉选皇家美素佳儿旺玥来写。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceRow2DrinkingActionClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    full_text = f"{item.title}\n{item.body}"
    assert "孩子活动量大以后" not in full_text
    assert "随手给他冲一杯" not in full_text
    assert "孩子愿意喝" not in full_text
    assert "皇家美素佳儿旺玥" in full_text
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    rewrite_stages = [stage for stage in stage_calls if stage.capability == "content.rewrite"]
    assert len(rewrite_stages) == 1
    review = (rewrite_stages[0].input_snapshot or {})["review_report"]["product_experience_phrase_review"]
    assert "wangyue_row2_drinking_action_context" in review["reasons"]


@pytest.mark.asyncio
async def test_batch_execution_retries_row2_drinking_action_residue_with_model():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_row2_drinking_action_guard_retry",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "精力不足，日常状态观察",
            "topic": "精力不足，日常状态观察",
            "source_row_no": 2,
            "corpus": "写作规则：围绕孩子平时活动量大，妈妈为什么会给儿童奶粉选皇家美素佳儿旺玥来写。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceRow2DrinkingActionRetryClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    full_text = f"{item.title}\n{item.body}"
    assert "喝得顺口" not in full_text
    assert "皇家美素佳儿旺玥" in full_text or "旺玥" in full_text
    rewrites = item.quality_json["product_experience_phrase_rewrites"]
    assert len(rewrites) == 2
    assert rewrites[0]["passed"] is False
    assert rewrites[1]["passed"] is True
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    rewrite_stages = [stage for stage in stage_calls if stage.capability == "content.rewrite"]
    assert len(rewrite_stages) == 2
    second_instructions = "\n".join((rewrite_stages[1].input_snapshot or {}).get("rewrite_instructions") or [])
    assert "再次改写" in second_instructions
    assert "row2 喝奶动作" in second_instructions


@pytest.mark.asyncio
async def test_batch_execution_blocks_unfixed_wangyue_context_mistakes_for_article_business_rule():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_wangyue_context_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "容易中招，日常保护力",
            "topic": "容易中招，日常保护力",
            "corpus": "写作规则：孩子接触人多后，妈妈担心容易中招；旺玥支持孩子保护力。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceWangyueContextClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert item.status == "failed"
    assert item.quality_json["hard_pass"] is False
    blocked = item.quality_json["postprocess_blocked"]
    assert blocked["source"] == "product_experience_phrase_guard"
    assert "源悦" in blocked["hits"]
    assert "一岁多" in blocked["hits"]
    assert "书包侧袋" in blocked["hits"]
    assert "一盒旺玥" in blocked["hits"]
    assert "兑点温水摇匀" in blocked["hits"]
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is False
    review_report = item.quality_json["review_report"]
    assert review_report["rewrite_required"] is True
    assert review_report["rewrite_reason"] == "硬性规则改写失败，需要人工复核"
    rewrite_stages = [stage for stage in stage_calls if stage.capability == "content.rewrite"]
    assert len(rewrite_stages) == 2
    phrase_stage = next(
        stage
        for stage in rewrite_stages
        if (stage.input_snapshot or {}).get("rewrite_source") == "product_experience_phrase_guard"
    )
    instructions = "\n".join((phrase_stage.input_snapshot or {}).get("rewrite_instructions") or [])
    assert "旺玥场景路径错误" in instructions


@pytest.mark.asyncio
async def test_batch_execution_rewrites_child_product_promo_context_for_wangyue_article():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_child_product_promo_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "容易中招，日常保护力",
            "topic": "容易中招，日常保护力",
            "corpus": "写作规则：孩子接触人多后，妈妈担心容易中招；旺玥支持孩子保护力。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceChildProductPromoClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    full_text = f"{item.title}\n{item.body}"
    assert "你也来一杯" not in full_text
    assert "要不要来一杯" not in full_text
    assert "我家也有" not in full_text
    assert "旁边小朋友在喝奶" not in full_text
    assert "给孩子选了旺玥" in full_text
    assert "product_experience_phrase_rewrites" in item.quality_json
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    rewrite_stages = [stage for stage in stage_calls if stage.capability == "content.rewrite"]
    assert len(rewrite_stages) == 1
    review = (rewrite_stages[0].input_snapshot or {})["review_report"]["product_experience_phrase_review"]
    assert "wangyue_child_product_promo_context" in review["reasons"]
    instructions = "\n".join((rewrite_stages[0].input_snapshot or {}).get("rewrite_instructions") or [])
    assert "孩子主动介绍/推荐/邀请别人喝旺玥" in instructions


@pytest.mark.asyncio
async def test_batch_execution_cleans_wangyue_digestive_context_for_article_business_rule():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_product_wangyue_digestive_context_guard",
            asset_key="wangyue_article_business_rules",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "business_rule": "营养不足/成长发育需求，日常补充观察",
            "topic": "营养不足/成长发育需求，日常补充观察",
            "corpus": "写作规则：围绕孩子成长阶段的日常营养补充来写；0705旺玥活动。",
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=ProductExperienceWangyueDigestiveContextClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    full_text = f"{item.title}\n{item.body}"
    assert "肚子软软的" not in full_text
    assert "便便" not in full_text
    assert "胀气" not in full_text
    assert "日常状态看着还顺" in full_text
    assert "product_experience_wangyue_context_cleanups" in item.quality_json
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    assert sum(1 for stage in stage_calls if stage.capability == "content.rewrite") == 0


@pytest.mark.asyncio
async def test_batch_execution_uses_unified_content_generate_runtime_output():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={"executor_token": "test-token"},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_content_generate",
            asset_key="yuanyue",
            product_topic="宝宝便便不规律",
            target_audience="新手妈妈",
            style="经验老道型",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=_plan(1)))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=RuntimeFastDraftReviewClient(),
            callback_base_url="http://maga.test/api/v1/executor",
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert item.status == "generated"
    assert item.title == "runtime content 标题"
    assert item.body == "runtime content 正文"
    review_report = item.quality_json["review_report"]
    assert review_report["source"] == "maga_unified_content_generate"
    assert review_report["rewrite_required"] is False
    assert item.quality_json["hard_pass"] is True
    assert item.quality_json["executor"] == "content_runtime"
    assert item.quality_json["soft_score_avg"] is None
    assert {stage.capability for stage in stage_calls} == {"content.generate", "content.rewrite"}
    assert item.quality_json["persona_style_rewrites"][0]["preset_code"] == "roommate_direct"


@pytest.mark.asyncio
async def test_batch_execution_rewrites_ai_flavor_after_generation():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_ai_flavor_humanizer",
            asset_key="wangyue_selection_review",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_selection_review",
            "corpus": "0705旺玥活动",
            "post_type": "选奶选择复盘型",
            "persona_style_rewrite_enabled": False,
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=AIFlavorHumanizerRewriteClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert item.title == "最近迷上拼图"
    assert "不是要说喝了怎么样" not in item.body
    assert item.quality_json["ai_flavor_humanizer"]["pass"] is True
    rewrites = item.quality_json["ai_flavor_humanizer_rewrites"]
    assert rewrites[0]["pre_review"]["rewrite_required"] is True
    assert rewrites[0]["post_review"]["rewrite_required"] is False
    assert rewrites[0]["before"]["title"] == "拼图那阵，选奶看了眼脑"
    review_report = item.quality_json["review_report"]
    assert review_report["rewrite_required"] is False
    assert review_report["ai_flavor_review"]["pass_"] is True
    ai_rewrite_stages = [
        stage
        for stage in stage_calls
        if stage.capability == "content.rewrite"
        and (stage.input_snapshot or {}).get("rewrite_source") == "ai_flavor_humanizer"
    ]
    assert len(ai_rewrite_stages) == 1
    instructions = "\n".join((ai_rewrite_stages[0].input_snapshot or {}).get("rewrite_instructions") or [])
    assert "great-writer humanizer 四步" in instructions
    assert "标题不要出现产品卖点词" in instructions
    assert "不可新增清单" in instructions
    assert "不要新增时间/季节/季节性活动节点" in instructions
    assert "不要新增产品使用动作" in instructions
    assert "不要新增成分到效果的新因果" in instructions


@pytest.mark.asyncio
async def test_batch_execution_rechecks_forbidden_terms_after_ai_flavor_rewrite():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_ai_flavor_forbidden_recheck",
            asset_key="wangyue_selection_review",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_selection_review",
            "corpus": "0705旺玥活动",
            "post_type": "选奶选择复盘型",
            "persona_style_rewrite_enabled": False,
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=AIFlavorHumanizerIntroducesForbiddenTermClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    full_text = f"{item.title}\n{item.body}"
    assert "体质" not in full_text
    assert "状态跟得上" in full_text
    assert item.quality_json["forbidden_terms_review"]["initial_hits"] == ["体质"]
    assert item.quality_json["forbidden_terms_review"]["final_hits"] == []
    assert item.quality_json["review_report"]["rewrite_required"] is False
    rewrite_stages = [stage for stage in stage_calls if stage.capability == "content.rewrite"]
    assert any((stage.input_snapshot or {}).get("rewrite_source") == "ai_flavor_humanizer" for stage in rewrite_stages)
    assert any((stage.input_snapshot or {}).get("forbidden_hits") == ["体质"] for stage in rewrite_stages)


@pytest.mark.asyncio
async def test_batch_execution_falls_back_to_ai_flavor_when_llm_quality_review_fails():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    reviewer = FailingProductExperienceLLMReviewer([])

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_ai_flavor_fallback_after_llm_review_failure",
            asset_key="wangyue_selection_review",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_selection_review",
            "corpus": "0705旺玥活动",
            "post_type": "选奶选择复盘型",
            "persona_style_rewrite_enabled": False,
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=AIFlavorHumanizerRewriteClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
            product_experience_llm_reviewer=reviewer,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert item.title == "最近迷上拼图"
    assert "不是要说喝了怎么样" not in item.body
    assert item.quality_json["ai_flavor_humanizer"]["pass"] is True
    assert "product_experience_llm_quality_failures" in item.quality_json
    assert item.quality_json["review_report"].get("rewrite_required") is False
    assert len(reviewer.calls) == 1
    assert reviewer.calls[0]["ai_flavor_review"]["rewrite_required"] is True
    ai_rewrite_stages = [
        stage
        for stage in stage_calls
        if stage.capability == "content.rewrite"
        and (stage.input_snapshot or {}).get("rewrite_source") == "ai_flavor_humanizer"
    ]
    assert len(ai_rewrite_stages) == 1


@pytest.mark.asyncio
async def test_batch_execution_preserves_body_for_title_only_ai_flavor_rewrite():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    reviewer = FailingProductExperienceLLMReviewer([])

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_ai_flavor_title_only",
            asset_key="wangyue_selection_review",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_selection_review",
            "corpus": "0705旺玥活动",
            "post_type": "选奶复盘",
            "persona_style_rewrite_enabled": False,
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=AIFlavorHumanizerTitleOnlyRewriteClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
            product_experience_llm_reviewer=reviewer,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert item.title == "状态稳了"
    assert item.body == AIFlavorHumanizerTitleOnlyRewriteClient.generated_body
    assert AIFlavorHumanizerTitleOnlyRewriteClient.weakened_body != item.body
    rewrites = item.quality_json["ai_flavor_humanizer_rewrites"]
    assert rewrites[0]["pre_review"]["title_hits"]
    assert rewrites[0]["pre_review"]["body_hits"] == []
    assert rewrites[0]["after"]["body"] == AIFlavorHumanizerTitleOnlyRewriteClient.generated_body
    assert item.quality_json["ai_flavor_humanizer"]["pass"] is True
    assert item.quality_json["review_report"].get("rewrite_required") is False
    ai_rewrite_stages = [
        stage
        for stage in stage_calls
        if stage.capability == "content.rewrite"
        and (stage.input_snapshot or {}).get("rewrite_source") == "ai_flavor_humanizer"
    ]
    assert len(ai_rewrite_stages) == 1


@pytest.mark.asyncio
async def test_batch_execution_rewrites_ai_flavor_when_llm_quality_review_passes():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    reviewer = FakeProductExperienceLLMReviewer(
        [
            ProductExperienceLLMReview(pass_=True, rewrite_required=False, severity="pass"),
            ProductExperienceLLMReview(pass_=True, rewrite_required=False, severity="pass"),
        ]
    )

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_ai_flavor_rewrite_after_llm_pass",
            asset_key="wangyue_selection_review",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_selection_review",
            "corpus": "0705旺玥活动",
            "post_type": "选奶选择复盘型",
            "persona_style_rewrite_enabled": False,
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=AIFlavorHumanizerRewriteClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
            product_experience_llm_reviewer=reviewer,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert item.title == "最近迷上拼图"
    assert "不是要说喝了怎么样" not in item.body
    assert item.quality_json["ai_flavor_humanizer"]["pass"] is True
    assert item.quality_json["review_report"].get("rewrite_required") is False
    assert len(reviewer.calls) == 2
    assert reviewer.calls[0]["ai_flavor_review"]["rewrite_required"] is True
    assert reviewer.calls[1]["ai_flavor_review"]["rewrite_required"] is False
    ai_rewrite_stages = [
        stage
        for stage in stage_calls
        if stage.capability == "content.rewrite"
        and (stage.input_snapshot or {}).get("rewrite_source") == "ai_flavor_humanizer"
    ]
    assert len(ai_rewrite_stages) == 1


@pytest.mark.asyncio
async def test_batch_execution_cleans_time_event_introduced_by_ai_flavor():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_ai_flavor_time_event_cleanup",
            asset_key="wangyue_selection_review",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "rule_type": "business_rule",
            "asset_key": "wangyue_selection_review",
            "corpus": "0705旺玥活动",
            "post_type": "选奶选择复盘型",
            "persona_style_rewrite_enabled": False,
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        service = ContentBatchExecutionService(
            session,
            invocation_client=AIFlavorHumanizerIntroducesTimeEventClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()

    assert item.status == "generated"
    assert item.error_message is None
    full_text = f"{item.title}\n{item.body}"
    assert "春游" not in full_text
    assert "踏青" not in full_text
    assert "户外活动回来还是那个状态" in item.title
    assert "幼儿园户外活动" in item.body
    quality = item.quality_json
    assert quality["hard_pass"] is True
    assert "postprocess_blocked" not in quality
    cleanup = quality["ai_flavor_wangyue_time_event_cleanups"][0]
    assert cleanup["pre_review"]["wangyue_time_event_context_hits"] == ["春游"]
    assert cleanup["post_review"]["wangyue_time_event_context_hits"] == []
    assert "product_experience_phrase_rewrites" in quality
    assert quality["product_experience_phrase_guard"]["pass"] is True
    async with session_factory() as session:
        rewrite_stages = (
            await session.execute(
                select(ContentAgentStageCall)
                .where(ContentAgentStageCall.capability == "content.rewrite")
                .order_by(ContentAgentStageCall.sequence_no)
            )
        ).scalars().all()
    rewrite_sources = [(stage.input_snapshot or {}).get("rewrite_source") for stage in rewrite_stages]
    assert "ai_flavor_humanizer" in rewrite_sources
    ai_flavor_index = rewrite_sources.index("ai_flavor_humanizer")
    assert rewrite_sources[ai_flavor_index + 1] == "product_experience_phrase_guard"


@pytest.mark.asyncio
async def test_batch_execution_retries_ai_flavor_when_first_rewrite_still_fails():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=_execution_tables(),
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            ExecutorRegistry(
                executor_code="maga_direct_llm_executor",
                executor_type="direct_llm",
                display_name="Hermes MAGA worker",
                invoke_url="http://maga-worker.test/invoke",
                enabled=1,
                config_json={},
            )
        )
        job = ContentBatchJob(
            batch_code="batch_ai_flavor_retry",
            asset_key="wangyue_selection_review",
            product_topic="0705旺玥活动",
            count=1,
            status="planned",
        )
        session.add(job)
        await session.flush()
        plan = {
            **_plan(1),
            "asset_key": "wangyue_selection_review",
            "post_type": "选奶选择复盘型",
            "persona_style_rewrite_enabled": False,
        }
        session.add(ContentBatchItem(batch_id=job.id, item_no=1, status="planned", plan_json=plan))
        await session.commit()

        client = AIFlavorHumanizerRetryRewriteClient()
        service = ContentBatchExecutionService(
            session,
            invocation_client=client,
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert client.rewrite_count == 2
    assert item.title == "入园后那阵"
    assert item.quality_json["ai_flavor_humanizer"]["pass"] is True
    rewrites = item.quality_json["ai_flavor_humanizer_rewrites"]
    assert len(rewrites) == 2
    assert rewrites[0]["passed"] is False
    assert rewrites[1]["passed"] is True
    retry_stages = [
        stage
        for stage in stage_calls
        if stage.capability == "content.rewrite"
        and (stage.input_snapshot or {}).get("rewrite_source") == "ai_flavor_humanizer"
    ]
    assert [stage.input_snapshot["rewrite_round"] for stage in retry_stages] == [1, 2]


def _plan(item_no: int) -> dict:
    return {
        "item_no": item_no,
        "asset_key": "yuanyue",
        "product_topic": "宝宝便便不规律",
        "target_audience": "新手妈妈",
        "style": "经验老道型",
        "painpoint_ref": {
            "asset_type": "painpoint_model",
            "asset_key": "yuanyue",
            "item_index": 0,
            "item_id": f"pain_{item_no}",
            "snapshot": {"painpoint": "便便不规律", "description": "便便状态不稳定", "selling_point": "好消化易吸收"},
        },
        "selling_point_ref": {
            "asset_type": "product_selling_points",
            "asset_key": "yuanyue",
            "item_index": 0,
            "item_id": f"sell_{item_no}",
            "snapshot": {"selling_point": "好消化易吸收", "advantage": "软凝乳"},
        },
        "reference_example_refs": [
            {
                "asset_type": "reference_examples",
                "asset_key": "yuanyue",
                "item_index": item_no - 1,
                "item_id": f"yuanyue_ref_{item_no:03d}",
                "snapshot": {"title": f"参考例文{item_no}", "body": "先观察宝宝便便状态", "painpoint": "便便不规律"},
            }
        ],
        "compliance_rule_refs": [
            {
                "asset_type": "compliance_rules",
                "asset_key": "yuanyue",
                "item_index": 0,
                "item_id": "rule_001",
                "snapshot": {"dimension": "禁止治疗便秘", "risk_level": "high"},
            }
        ],
    }
