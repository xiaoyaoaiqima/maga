"""Tests for MAGA batch content planner."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.maga_assets import AssetRegistry
from app.models.content_agent import ContentBatchJob, ContentBatchItem
from app.services.content_batch_planner import ContentBatchPlanner, _resolve_real_user_pool_config, _rotated_model_config


def test_article_business_generation_limit_prefers_requested_count():
    service = ContentBatchPlanner.__new__(ContentBatchPlanner)
    asset = AssetRegistry(
        metadata_json={"default_generation_count": 10},
        content_json={"default_generation_count": 20},
    )
    rules = [
        {"business_rule": f"体验{i}", "corpus": "像真实妈妈分享业务规则。"}
        for i in range(1200)
    ]

    limit = service._product_experience_generation_limit(asset, rules, requested_count=1000)

    assert limit == 1000


def test_article_business_rule_plan_samples_three_examples_from_pool():
    service = ContentBatchPlanner.__new__(ContentBatchPlanner)
    rule = {
        "rule_id": "business_rule_001",
        "business_rule": "奶量补充",
        "corpus": "围绕奶量补充写真实使用体验。",
        "examples": [f"参考示例{i}" for i in range(20)],
        "supplements": ["补充参考1"],
        "source_row_no": 1,
    }
    asset = AssetRegistry(
        asset_type="article_business_rule_set",
        asset_key="yuanyue_product_experience",
        content_json={"rule_type": "business_rule"},
        metadata_json={},
    )

    plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="default_system_prompt_keywords",
        quality_guard_profile_key=None,
        model_config=None,
    )

    assert len(plan["examples"]) == 3
    assert set(plan["examples"]).issubset(set(rule["examples"]))
    assert plan["supplements"] == []
    assert plan["example_pool_count"] == 20
    assert plan["supplement_pool_count"] == 1
    assert plan["example_sample_count"] == 3
    assert plan["selected_example_source"] == "examples"
    assert len(plan["selected_example_indices"]) == 3


def test_article_business_rule_plan_uses_asset_model_config_with_request_override():
    service = ContentBatchPlanner.__new__(ContentBatchPlanner)
    rule = {
        "rule_id": "business_rule_001",
        "business_rule": "奶量补充",
        "corpus": "围绕奶量补充写真实使用体验。",
        "examples": ["参考示例1", "参考示例2", "参考示例3"],
        "source_row_no": 1,
    }
    asset = AssetRegistry(
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        content_json={
            "rule_type": "business_rule",
            "model_config": {"temperature": 0.9, "max_tokens": 2048},
        },
        metadata_json={},
    )

    default_plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
    )
    override_plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config={"temperature": 0.7},
    )

    assert default_plan["model_config"]["temperature"] == 0.9
    assert default_plan["model_config"]["max_tokens"] == 2048
    assert override_plan["model_config"]["temperature"] == 0.7
    assert override_plan["model_config"]["max_tokens"] == 2048


def test_article_business_rule_plan_merges_content_path_control_from_asset_and_rule():
    service = ContentBatchPlanner.__new__(ContentBatchPlanner)
    rule = {
        "rule_id": "business_rule_002",
        "business_rule": "精力不足，日常状态观察",
        "corpus": "像普通妈妈随手记录孩子日常状态。",
        "content_path_control": {
            "avoid_path": "不要走喝奶接受度路线。",
            "max_product_components": 1,
        },
        "source_row_no": 2,
    }
    asset = AssetRegistry(
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        content_json={
            "rule_type": "business_rule",
            "content_path_control": {
                "enabled": True,
                "instruction": "先拆生活入口和产品背景。",
                "avoid_path": "不要走完整导购骨架。",
            },
        },
        metadata_json={},
    )

    plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
    )

    assert plan["content_path_control"] == {
        "enabled": True,
        "instruction": "先拆生活入口和产品背景。",
        "avoid_path": "不要走喝奶接受度路线。",
        "max_product_components": 1,
    }


def test_article_business_rule_plan_uses_content_path_control_to_filter_real_user_pool_selection():
    service = ContentBatchPlanner(None)
    rule = {
        "rule_id": "business_rule_002",
        "source_row_no": 2,
        "business_rule": "精力不足，日常状态观察",
        "topic": "精力不足，日常状态观察",
        "corpus": "围绕孩子活动量大、日常状态观察来写。",
        "content_path_control": {
            "enabled": True,
            "exclude_example_terms": ["喝", "杯"],
        },
        "examples": [],
    }
    asset = AssetRegistry(
        id=10,
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        version_no=1,
        content_json={"rule_type": "business_rule"},
        metadata_json={},
    )
    pool_asset = AssetRegistry(
        id=20,
        asset_type="real_user_example_pool",
        asset_key="wangyue_child_growth_xhs_real_user_pool",
        version_no=1,
        content_json={},
        metadata_json={},
    )
    pool_items = [
        {
            "source_type": "note",
            "example_layer": "route",
            "route_family": "routine_record",
            "dedupe_hash": "drinking-route",
            "prompt_text": "每天那杯奶喝着还算顺",
            "text": "每天那杯奶喝着还算顺",
            "tags": ["喝奶接受度"],
            "risk_tags": [],
            "quality_score": 90,
        },
        {
            "source_type": "note",
            "example_layer": "route",
            "route_family": "outdoor_activity",
            "dedupe_hash": "activity-route",
            "prompt_text": "孩子户外活动多、活动量大，选儿童奶粉时会关注保护力",
            "text": "孩子户外活动多、活动量大，选儿童奶粉时会关注保护力",
            "tags": ["户外", "保护力"],
            "risk_tags": [],
            "quality_score": 20,
        },
    ]

    plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
        real_user_pool_asset=pool_asset,
        real_user_pool_items=pool_items,
        real_user_pool_config={"route_count": 1, "texture_count": 0, "comment_count": 0},
    )

    assert [item["prompt_text"] for item in plan["real_user_examples"]] == ["户外活动多、活动量大；担心容易中招，关注保护力"]
    assert plan["real_user_pool"]["filters"]["exclude_terms"] == ["喝", "杯"]
    assert plan["real_user_pool"]["route_prompt_exclude_terms"] == ["喝", "杯"]


def test_article_business_rule_plan_uses_asset_example_sample_count():
    service = ContentBatchPlanner.__new__(ContentBatchPlanner)
    rule = {
        "rule_id": "business_rule_001",
        "business_rule": "容易中招",
        "corpus": "围绕旺玥保护力写真实使用体验。",
        "examples": [f"真人纹理{i}" for i in range(20)],
        "source_row_no": 1,
    }
    asset = AssetRegistry(
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        content_json={
            "rule_type": "business_rule",
            "example_sample_count": 8,
        },
        metadata_json={},
    )

    plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
        real_user_pool_config=_resolve_real_user_pool_config(asset),
    )

    assert len(plan["examples"]) == 8
    assert plan["example_sample_count"] == 8
    assert set(plan["examples"]).issubset(set(rule["examples"]))


def test_article_business_rule_plan_caps_asset_example_sample_count():
    service = ContentBatchPlanner.__new__(ContentBatchPlanner)
    rule = {
        "rule_id": "business_rule_001",
        "business_rule": "容易中招",
        "corpus": "围绕旺玥保护力写真实使用体验。",
        "examples": [f"真人纹理{i}" for i in range(20)],
        "source_row_no": 1,
    }
    asset = AssetRegistry(
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        content_json={
            "rule_type": "business_rule",
            "example_sample_count": 50,
        },
        metadata_json={},
    )

    plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
    )

    assert len(plan["examples"]) == 8
    assert plan["example_sample_count"] == 8


def test_article_business_rule_plan_adds_real_user_examples_when_pool_configured():
    service = ContentBatchPlanner.__new__(ContentBatchPlanner)
    rule = {
        "rule_id": "business_rule_001",
        "business_rule": "营养不足/成长发育需求",
        "corpus": "围绕孩子成长阶段营养补充和选奶来写。",
        "examples": ["业务规则内示例"],
        "source_row_no": 4,
    }
    asset = AssetRegistry(
        id=10,
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        version_no=1,
        content_json={
            "rule_type": "business_rule",
            "real_user_pool_sampling": {"note_count": 5, "comment_count": 2},
        },
        metadata_json={},
    )
    pool_asset = AssetRegistry(
        id=20,
        asset_type="real_user_example_pool",
        asset_key="maternal_infant_xhs_real_user_pool",
        version_no=3,
        content_json={},
        metadata_json={},
    )
    pool_items = [
        {
            "source_type": "note",
            "text": f"选奶看营养和成长，第{i}条",
            "title": "选奶记录",
            "tags": ["选奶", "营养", "成长"],
            "risk_tags": [],
            "quality_score": 15,
            "dedupe_hash": f"n{i}",
        }
        for i in range(8)
    ] + [
        {
            "source_type": "comment",
            "text": f"有点贵但孩子爱喝，第{i}条",
            "title": "评论",
            "tags": ["价格", "喝奶接受度"],
            "risk_tags": ["评论口吻"],
            "quality_score": 12,
            "dedupe_hash": f"c{i}",
        }
        for i in range(4)
    ]

    plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
        real_user_pool_asset=pool_asset,
        real_user_pool_items=pool_items,
        real_user_pool_config={
            "note_count": 5,
            "comment_count": 2,
            "exclude_risk_tags": ["竞品品牌"],
            "exclude_terms": ["断货", "召回"],
        },
    )

    assert len(plan["real_user_examples"]) == 7
    assert plan["real_user_pool"]["asset_key"] == "maternal_infant_xhs_real_user_pool"
    assert plan["real_user_pool"]["selected"] == {"note": 5, "comment": 2}
    assert plan["real_user_pool"]["source_type_counts"] == {"note": 5, "comment": 2}
    assert plan["real_user_pool"]["filters"]["exclude_risk_tags"] == ["竞品品牌"]
    assert plan["real_user_pool"]["filters"]["exclude_terms"] == ["断货", "召回"]


def test_article_business_rule_plan_selects_layered_real_user_examples():
    service = ContentBatchPlanner(None)
    rule = {
        "rule_id": "business_rule_001",
        "business_rule": "容易中招，日常保护力观察",
        "topic": "容易中招，日常保护力观察",
        "corpus": "孩子上幼儿园后接触人多，妈妈关注保护力。",
        "examples": [],
    }
    asset = AssetRegistry(
        id=10,
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        version_no=1,
        content_json={"rule_type": "business_rule"},
        metadata_json={},
    )
    pool_asset = AssetRegistry(
        id=20,
        asset_type="real_user_example_pool",
        asset_key="wangyue_child_growth_xhs_real_user_pool",
        version_no=1,
        content_json={},
        metadata_json={},
    )
    pool_items = [
        {
            "source_type": "note",
            "text": "上幼儿园后接触人多，选旺玥就是看中日常保护力。",
            "title": "入园记录",
            "tags": ["幼儿园", "保护力"],
            "risk_tags": [],
            "quality_score": 16,
            "dedupe_hash": "route-1",
        },
        {
            "source_type": "note",
            "text": "除了贵点没毛病。",
            "title": "短句",
            "tags": ["价格"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "texture-1",
        },
        {
            "source_type": "note",
            "text": "我不是很懂，先喝着吧。",
            "title": "短句",
            "tags": ["价格"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "texture-2",
        },
        {
            "source_type": "note",
            "text": "肉疼但认了。",
            "title": "短句",
            "tags": ["价格"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "texture-3",
        },
        {
            "source_type": "note",
            "text": "孩子上学后接触人多，我开始认真看儿童奶粉。",
            "title": "孩子上学后我才懂",
            "tags": ["幼儿园", "选奶"],
            "risk_tags": [],
            "quality_score": 20,
            "dedupe_hash": "title-1",
        },
        {
            "source_type": "note",
            "text": "这类标题不适合直接做标题参考。",
            "title": "3岁宝宝奶粉攻略",
            "tags": ["选奶"],
            "risk_tags": [],
            "quality_score": 30,
            "dedupe_hash": "title-bad-age",
        },
        {
            "source_type": "note",
            "text": "栏目感太重的标题不适合进入帖子标题参考。",
            "title": "旺玥保护小课堂开课啦",
            "tags": ["保护力"],
            "risk_tags": [],
            "quality_score": 40,
            "example_layer": "reject",
            "dedupe_hash": "title-bad-column",
        },
        {
            "source_type": "comment",
            "text": "评论标题不进帖子标题池。",
            "title": "有姐妹喝过吗",
            "tags": ["选奶"],
            "risk_tags": [],
            "quality_score": 30,
            "dedupe_hash": "title-comment",
        },
    ]

    plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
        real_user_pool_asset=pool_asset,
        real_user_pool_items=pool_items,
        real_user_pool_config={"route_count": 1, "texture_count": 3, "comment_count": 0, "title_reference_count": 3},
    )

    assert [item["example_layer"] for item in plan["real_user_examples"]] == ["route", "texture", "texture", "texture"]
    assert plan["real_user_pool"]["asset_key"] == "wangyue_child_growth_xhs_real_user_pool"
    assert plan["real_user_pool"]["selected"]["route"] == 1
    assert plan["real_user_pool"]["selected"]["texture"] == 3
    assert plan["real_user_pool"]["layer_counts"] == {"route": 1, "texture": 3}
    assert plan["real_user_pool"]["route_family_counts"] == {"school_collective": 1}
    assert "孩子上学后我才懂" in plan["title_reference_examples"]
    assert "3岁宝宝奶粉攻略" not in plan["title_reference_examples"]
    assert "旺玥保护小课堂开课啦" not in plan["title_reference_examples"]
    assert "有姐妹喝过吗" not in plan["title_reference_examples"]
    assert plan["real_user_pool"]["title_reference"]["selected"] >= 1


def test_wangyue_real_user_pool_defaults_sample_prompt_layers_without_static_titles():
    service = ContentBatchPlanner(None)
    rule = {
        "rule_id": "business_rule_001",
        "business_rule": "容易中招，日常保护力观察",
        "topic": "容易中招，日常保护力观察",
        "corpus": "孩子上幼儿园后接触人多，妈妈关注保护力。",
        "examples": [],
    }
    asset = AssetRegistry(
        id=10,
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        version_no=1,
        content_json={
            "rule_type": "business_rule",
            "title_reference_examples": ["孩子上学后我才懂"],
        },
        metadata_json={},
    )
    pool_asset = AssetRegistry(
        id=20,
        asset_type="real_user_example_pool",
        asset_key="maternal_infant_xhs_real_user_pool",
        version_no=1,
        content_json={},
        metadata_json={},
    )
    pool_items = [
        {
            "source_type": "note",
            "text": "上幼儿园后接触人多，选旺玥就是看中日常保护力。",
            "title": "入园记录",
            "tags": ["幼儿园", "保护力"],
            "risk_tags": [],
            "quality_score": 30,
            "dedupe_hash": "route-1",
        },
        {
            "source_type": "note",
            "text": "除了贵点没毛病。",
            "title": "短句",
            "tags": ["价格"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "texture-1",
        },
        {
            "source_type": "note",
            "text": "我不是很懂，先喝着吧。",
            "title": "短句二",
            "tags": ["价格"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "texture-2",
        },
        {
            "source_type": "note",
            "text": "上学以后才发现，孩子每天那杯奶我还挺认真看的。",
            "title": "当妈后才懂",
            "tags": ["幼儿园", "选奶"],
            "risk_tags": [],
            "quality_score": 20,
            "dedupe_hash": "title-opening-1",
            "example_layer": "opening_texture",
            "layer_reason": "curated_opening:test",
        },
        {
            "source_type": "note",
            "text": "说实话，选奶这件事真的会越看越纠结。",
            "title": "选奶看花眼",
            "tags": ["选奶"],
            "risk_tags": [],
            "quality_score": 18,
            "dedupe_hash": "title-opening-2",
            "example_layer": "opening_texture",
            "layer_reason": "curated_opening:test",
        },
    ]

    plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
        real_user_pool_asset=pool_asset,
        real_user_pool_items=pool_items,
        real_user_pool_config={
            "route_count": 1,
            "texture_count": 2,
            "title_shape_count": 2,
            "opening_or_ending_count": 1,
            "comment_count": 0,
            "title_reference_count": 0,
            "disable_static_title_reference": True,
        },
    )

    assert plan["title_reference_examples"] == []
    assert plan["real_user_pool"]["requested"]["title_shape"] == 2
    assert plan["real_user_pool"]["requested"]["texture"] == 2
    assert plan["real_user_pool"]["requested"]["opening_or_ending"] == 1
    assert plan["real_user_pool"]["selected"]["title_shape"] == 2
    assert plan["real_user_pool"]["selected"]["opening_texture"] == 1


def test_wangyue_real_user_pool_source_row_override_can_disable_route_layer():
    service = ContentBatchPlanner(None)
    rule = {
        "rule_id": "business_rule_003",
        "source_row_no": 3,
        "business_rule": "注意力不集中，眼脑营养观察",
        "topic": "注意力不集中，眼脑营养观察",
        "corpus": "妈妈给孩子选儿童奶粉时，会关注保护力和眼脑营养；正文可以从选奶、看成分或日常记录里自然带出。",
        "examples": [],
    }
    asset = AssetRegistry(
        id=10,
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        version_no=1,
        content_json={"rule_type": "business_rule"},
        metadata_json={},
    )
    pool_asset = AssetRegistry(
        id=20,
        asset_type="real_user_example_pool",
        asset_key="wangyue_child_growth_xhs_real_user_pool",
        version_no=1,
        content_json={},
        metadata_json={},
    )
    pool_items = [
        {
            "source_type": "note",
            "text": "选奶时看成分，也会关注保护力和眼脑营养。",
            "title": "选奶记录",
            "tags": ["选奶", "成分", "保护力"],
            "risk_tags": [],
            "quality_score": 30,
            "dedupe_hash": "route-1",
        },
        {
            "source_type": "note",
            "text": "当妈后才知道，孩子喝的东西真不能随便。",
            "title": "随手记",
            "tags": ["选奶"],
            "risk_tags": [],
            "quality_score": 20,
            "dedupe_hash": "opening-1",
        },
        {
            "source_type": "note",
            "text": "说实话，我不是很懂这些成分。",
            "title": "随手记",
            "tags": ["成分"],
            "risk_tags": [],
            "quality_score": 18,
            "dedupe_hash": "opening-2",
        },
        {
            "source_type": "note",
            "text": "我不是很懂，先看成分。",
            "title": "短句",
            "tags": ["成分"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "texture-1",
            "example_layer": "texture",
        },
        {
            "source_type": "note",
            "text": "除了贵点没毛病。",
            "title": "短句",
            "tags": ["选奶"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "texture-2",
            "example_layer": "texture",
        },
    ]

    plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
        real_user_pool_asset=pool_asset,
        real_user_pool_items=pool_items,
        real_user_pool_config={
            "route_count": 1,
            "texture_count": 1,
            "opening_or_ending_count": 1,
            "comment_count": 0,
            "source_row_overrides": {
                "3": {
                    "route_count": 0,
                    "texture_count": 2,
                    "opening_or_ending_count": 2,
                }
            },
        },
    )

    assert plan["real_user_pool"]["requested"]["route"] == 0
    assert plan["real_user_pool"]["requested"]["texture"] == 2
    assert plan["real_user_pool"]["requested"]["opening_or_ending"] == 2
    assert plan["real_user_pool"]["selected"]["route"] == 0
    assert plan["real_user_pool"]["selected"]["texture"] == 2
    assert plan["real_user_pool"]["selected"]["opening_texture"] == 2
    assert all(item["example_layer"] != "route" for item in plan["real_user_examples"])


def test_wangyue_real_user_pool_source_row_override_can_disable_all_layers():
    service = ContentBatchPlanner(None)
    rule = {
        "rule_id": "business_rule_004",
        "source_row_no": 4,
        "business_rule": "营养不足/成长发育需求，日常补充观察",
        "topic": "营养不足/成长发育需求，日常补充观察",
        "corpus": "妈妈关注日常营养能不能跟上，选择旺玥补充营养、支持成长。",
        "examples": ["儿童奶粉这块，我主要看适不适合日常补充。"],
    }
    asset = AssetRegistry(
        id=10,
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        version_no=1,
        content_json={"rule_type": "business_rule"},
        metadata_json={},
    )
    pool_asset = AssetRegistry(
        id=20,
        asset_type="real_user_example_pool",
        asset_key="wangyue_child_growth_xhs_real_user_pool",
        version_no=1,
        content_json={},
        metadata_json={},
    )
    pool_items = [
        {
            "source_type": "note",
            "text": "孩子看着壮实点，我就会记一下这罐奶粉。",
            "title": "随手记",
            "tags": ["营养", "成长"],
            "risk_tags": [],
            "quality_score": 30,
            "dedupe_hash": "route-1",
            "example_layer": "route",
        }
    ]

    plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
        real_user_pool_asset=pool_asset,
        real_user_pool_items=pool_items,
        real_user_pool_config={
            "route_count": 1,
            "texture_count": 1,
            "comment_count": 0,
            "source_row_overrides": {
                "4": {
                    "route_count": 0,
                    "detail_count": 0,
                    "title_shape_count": 0,
                    "opening_count": 0,
                    "opening_or_ending_count": 0,
                    "texture_count": 0,
                    "ending_count": 0,
                    "comment_count": 0,
                }
            },
        },
    )

    assert plan["real_user_examples"] == []
    assert plan["real_user_pool"]["requested"]["note"] == 0
    assert plan["real_user_pool"]["selected"]["note"] == 0


def test_wangyue_title_shape_can_use_fallback_pool_without_changing_route_pool():
    service = ContentBatchPlanner(None)
    rule = {
        "rule_id": "business_rule_001",
        "business_rule": "容易中招，日常保护力观察",
        "topic": "容易中招，日常保护力观察",
        "corpus": "孩子上幼儿园后接触人多，妈妈关注保护力。",
        "examples": [],
    }
    asset = AssetRegistry(
        id=10,
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        version_no=1,
        content_json={"rule_type": "business_rule"},
        metadata_json={},
    )
    primary_pool_asset = AssetRegistry(
        id=20,
        asset_type="real_user_example_pool",
        asset_key="wangyue_child_growth_xhs_real_user_pool",
        version_no=1,
        content_json={},
        metadata_json={},
    )
    title_pool_asset = AssetRegistry(
        id=21,
        asset_type="real_user_example_pool",
        asset_key="maternal_infant_xhs_real_user_pool",
        version_no=3,
        content_json={},
        metadata_json={},
    )
    primary_items = [
        {
            "source_type": "note",
            "text": "上幼儿园后接触人多，选旺玥就是看中日常保护力。",
            "title": "入园记录",
            "tags": ["幼儿园", "保护力"],
            "risk_tags": [],
            "quality_score": 30,
            "dedupe_hash": "route-1",
        },
        {
            "source_type": "note",
            "text": "除了贵点没毛病。",
            "title": "短句",
            "tags": ["价格"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "texture-1",
        },
    ]
    title_items = [
        {
            "source_type": "note",
            "text": "普通标题形态来源一。",
            "title": "当妈后才懂",
            "tags": ["选奶"],
            "risk_tags": [],
            "quality_score": 20,
            "dedupe_hash": "title-shape-1",
        },
        {
            "source_type": "note",
            "text": "普通标题形态来源二。",
            "title": "奶粉看花眼",
            "tags": ["选奶"],
            "risk_tags": [],
            "quality_score": 18,
            "dedupe_hash": "title-shape-2",
        },
    ]

    plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
        real_user_pool_asset=primary_pool_asset,
        real_user_pool_items=primary_items,
        real_user_pool_config={"route_count": 1, "texture_count": 1, "title_shape_count": 2, "comment_count": 0},
        title_shape_pool_asset=title_pool_asset,
        title_shape_pool_items=title_items,
    )

    title_shapes = [
        item["prompt_text"]
        for item in plan["real_user_examples"]
        if item.get("example_layer") == "title_shape"
    ]
    assert title_shapes == ["当妈后才懂", "奶粉看花眼"]
    assert plan["real_user_examples"][0]["route_family"] == "school_collective"
    assert plan["real_user_pool"]["fallback_pools"]["title_shape"]["asset_key"] == "maternal_infant_xhs_real_user_pool"
    assert plan["real_user_pool"]["selected"]["title_shape"] == 2


def test_wangyue_real_user_pool_defaults_rule_examples_to_one_unless_configured():
    service = ContentBatchPlanner(None)
    rule = {
        "rule_id": "business_rule_001",
        "examples": ["示例1", "示例2", "示例3"],
    }
    asset = AssetRegistry(
        id=10,
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        version_no=1,
        content_json={
            "rule_type": "business_rule",
            "real_user_pool_asset_key": "wangyue_child_growth_xhs_real_user_pool",
        },
        metadata_json={},
    )

    assert service._article_business_example_sample_count(asset, rule) == 1

    configured_asset = AssetRegistry(
        id=11,
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        version_no=1,
        content_json={
            "rule_type": "business_rule",
            "real_user_pool_asset_key": "wangyue_child_growth_xhs_real_user_pool",
            "example_sample_count": 2,
        },
        metadata_json={},
    )

    assert service._article_business_example_sample_count(configured_asset, rule) == 2

    disabled_asset = AssetRegistry(
        id=12,
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        version_no=1,
        content_json={
            "rule_type": "business_rule",
            "real_user_pool_asset_key": "wangyue_child_growth_xhs_real_user_pool",
            "example_sample_count": 0,
        },
        metadata_json={},
    )

    assert service._article_business_example_sample_count(disabled_asset, rule) == 0


def test_article_business_rule_plan_adds_title_reference_examples():
    service = ContentBatchPlanner(None)
    rule = {
        "rule_id": "business_rule_001",
        "business_rule": "容易中招，日常保护力观察",
        "topic": "容易中招，日常保护力观察",
        "corpus": "孩子上幼儿园后接触人多，妈妈关注保护力。",
        "examples": [],
    }
    asset = AssetRegistry(
        id=10,
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        version_no=1,
        content_json={
            "rule_type": "business_rule",
            "title_reference_examples": [
                "皇家美素佳儿旺玥",
                "儿童成长奶粉哪家好",
                "又开一听新的旺玥奶粉",
            ],
            "synthetic_title_examples": [
                "旺玥",
                "这罐还在喝",
                "给孩子选奶粉选到头懵",
                "三周岁后奶粉怎么喝",
                "校服裤子又短了",
                "早上那杯奶",
            ],
            "title_reference_sample_count": 2,
        },
        metadata_json={},
    )

    plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
    )

    assert plan["title_reference_all_examples"] == [
        "皇家美素佳儿旺玥",
        "儿童成长奶粉哪家好",
        "又开一听新的旺玥奶粉",
    ]
    assert plan["synthetic_title_examples"] == [
        "旺玥",
        "这罐还在喝",
        "给孩子选奶粉选到头懵",
    ]
    assert plan["title_reference_examples"] == []
    assert "皇家美素佳儿旺玥" in plan["title_reference_all_examples"]
    assert "儿童成长奶粉哪家好" in plan["title_reference_all_examples"]
    assert "又开一听新的旺玥奶粉" in plan["title_reference_all_examples"]


def test_article_business_rule_plan_avoids_repeated_static_title_references():
    service = ContentBatchPlanner(None)
    rule = {
        "rule_id": "business_rule_001",
        "business_rule": "营养不足/成长发育需求，日常补充观察",
        "topic": "营养不足/成长发育需求，日常补充观察",
        "corpus": "围绕给孩子选择儿童奶粉来写。",
        "examples": [],
    }
    asset = AssetRegistry(
        id=10,
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        version_no=1,
        content_json={
            "rule_type": "business_rule",
            "title_reference_examples": ["选奶记录", "普通妈妈选奶", "随手记"],
            "title_reference_sample_count": 1,
            "real_user_pool_sampling": {"disable_static_title_reference": False},
        },
        metadata_json={},
    )
    used_titles: set[str] = set()

    first = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
        real_user_pool_config={"disable_static_title_reference": False},
        used_title_reference_examples=used_titles,
    )
    second = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=2,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
        real_user_pool_config={"disable_static_title_reference": False},
        used_title_reference_examples=used_titles,
    )

    assert first["title_reference_examples"]
    assert second["title_reference_examples"]
    assert first["title_reference_examples"][0] != second["title_reference_examples"][0]
    assert used_titles == set(first["title_reference_examples"] + second["title_reference_examples"])


def test_article_business_rule_plan_avoids_stacked_title_prompt_family_when_possible():
    service = ContentBatchPlanner(None)
    rule = {
        "rule_id": "business_rule_002",
        "source_row_no": 2,
        "business_rule": "精力不足，户外活动后日常观察",
        "topic": "精力不足，户外活动后日常观察",
        "corpus": "围绕皇家美素佳儿旺玥儿童奶粉的保护力和眼脑营养来写。",
        "examples": [],
    }
    asset = AssetRegistry(
        id=10,
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        version_no=1,
        content_json={
            "rule_type": "business_rule",
            "real_user_pool_asset_key": "wangyue_child_growth_xhs_real_user_pool",
            "title_reference_examples": ["选奶记录", "随手记一下"],
            "title_reference_sample_count": 1,
            "real_user_pool_sampling": {
                "disable_static_title_reference": False,
                "route_count": 1,
                "texture_count": 0,
                "comment_count": 0,
                "prompt_family_stack_avoid": ["selection_process"],
            },
        },
        metadata_json={},
    )
    real_user_pool_asset = AssetRegistry(
        id=20,
        asset_type="real_user_example_pool",
        asset_key="wangyue_child_growth_xhs_real_user_pool",
        version_no=1,
        content_json={},
        metadata_json={},
    )
    real_user_items = [
        {
            "source_type": "note",
            "example_layer": "route",
            "route_family": "selection_research",
            "dedupe_hash": "route-selection",
            "prompt_text": "做功课选儿童奶粉时，我会先看保护力和眼脑营养",
            "text": "做功课选儿童奶粉时，我会先看保护力和眼脑营养",
            "tags": ["选奶", "保护力", "眼脑"],
            "risk_tags": [],
            "quality_score": 10,
        }
    ]

    plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
        real_user_pool_asset=real_user_pool_asset,
        real_user_pool_items=real_user_items,
        real_user_pool_config=asset.content_json["real_user_pool_sampling"],
    )

    assert plan["real_user_pool"]["prompt_family_counts"] == {"selection_process": 1}
    assert plan["title_reference_examples"] == ["随手记一下"]


def test_article_business_rule_plan_keeps_stacked_title_prompt_family_when_no_alternative():
    service = ContentBatchPlanner(None)
    rule = {
        "rule_id": "business_rule_002",
        "source_row_no": 2,
        "business_rule": "精力不足，户外活动后日常观察",
        "topic": "精力不足，户外活动后日常观察",
        "corpus": "围绕皇家美素佳儿旺玥儿童奶粉的保护力和眼脑营养来写。",
        "examples": [],
    }
    asset = AssetRegistry(
        id=10,
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        version_no=1,
        content_json={
            "rule_type": "business_rule",
            "real_user_pool_asset_key": "wangyue_child_growth_xhs_real_user_pool",
            "title_reference_examples": ["选奶记录"],
            "title_reference_sample_count": 1,
            "real_user_pool_sampling": {
                "disable_static_title_reference": False,
                "route_count": 1,
                "texture_count": 0,
                "comment_count": 0,
                "prompt_family_stack_avoid": ["selection_process"],
            },
        },
        metadata_json={},
    )
    real_user_pool_asset = AssetRegistry(
        id=20,
        asset_type="real_user_example_pool",
        asset_key="wangyue_child_growth_xhs_real_user_pool",
        version_no=1,
        content_json={},
        metadata_json={},
    )
    real_user_items = [
        {
            "source_type": "note",
            "example_layer": "route",
            "route_family": "selection_research",
            "dedupe_hash": "route-selection",
            "prompt_text": "做功课选儿童奶粉时，我会先看保护力和眼脑营养",
            "text": "做功课选儿童奶粉时，我会先看保护力和眼脑营养",
            "tags": ["选奶", "保护力", "眼脑"],
            "risk_tags": [],
            "quality_score": 10,
        }
    ]

    plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
        real_user_pool_asset=real_user_pool_asset,
        real_user_pool_items=real_user_items,
        real_user_pool_config=asset.content_json["real_user_pool_sampling"],
    )

    assert plan["real_user_pool"]["prompt_family_counts"] == {"selection_process": 1}
    assert plan["title_reference_examples"] == ["选奶记录"]


def test_wangyue_growth_rule_filters_drinking_synthetic_title_examples():
    service = ContentBatchPlanner(None)
    rule = {
        "rule_id": "business_rule_004",
        "source_row_no": 4,
        "business_rule": "营养不足/成长发育需求，日常补充观察",
        "topic": "营养不足/成长发育需求，日常补充观察",
        "corpus": "围绕给孩子选择皇家美素佳儿旺玥儿童奶粉来写。",
        "examples": [],
    }
    asset = AssetRegistry(
        id=10,
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        version_no=1,
        content_json={
            "rule_type": "business_rule",
            "synthetic_title_examples": [
                "旺玥",
                "这罐还在喝",
                "又开一听旺玥",
                "吃完了才想起来拍个空罐",
                "这罐粉质还行",
                "绿叶菜还是不碰",
                "不爱吃菜怎么办",
                "接触多了有点慌",
                "跑了一天还行",
                "买奶粉这事儿我算想通了",
                "给孩子选奶粉选到头懵",
            ],
        },
        metadata_json={},
    )

    plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
    )

    assert plan["synthetic_title_examples"] == [
        "旺玥",
        "买奶粉这事儿我算想通了",
        "给孩子选奶粉选到头懵",
    ]


def test_article_business_rule_plan_filters_synthetic_titles_from_row_override():
    service = ContentBatchPlanner(None)
    rule = {
        "rule_id": "business_rule_002",
        "source_row_no": 2,
        "business_rule": "精力不足，日常状态观察",
        "topic": "精力不足，日常状态观察",
        "corpus": "围绕孩子活动量大、日常状态观察来写。",
        "examples": [],
    }
    asset = AssetRegistry(
        id=10,
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        version_no=1,
        content_json={
            "rule_type": "business_rule",
            "synthetic_title_examples": [
                "给孩子选奶粉选到头懵",
                "看配料表看困了",
                "要不要换儿童奶粉",
                "跑了一天还行",
                "户外回来还行",
            ],
            "real_user_pool_sampling": {
                "source_row_overrides": {
                    "2": {
                        "synthetic_title_exclude_terms": [
                            "选奶",
                            "配料表",
                            "要不要",
                            "换儿童奶粉",
                        ]
                    }
                }
            },
        },
        metadata_json={},
    )

    plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
        real_user_pool_config=_resolve_real_user_pool_config(asset),
    )

    assert plan["synthetic_title_examples"] == ["跑了一天还行", "户外回来还行"]


def test_article_business_rule_plan_selects_detail_and_ending_real_user_examples():
    service = ContentBatchPlanner(None)
    rule = {
        "rule_id": "business_rule_001",
        "business_rule": "容易中招，日常保护力观察",
        "topic": "容易中招，日常保护力观察",
        "corpus": "孩子上幼儿园后接触人多，妈妈关注保护力。",
        "examples": [],
    }
    asset = AssetRegistry(
        id=10,
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        version_no=1,
        content_json={"rule_type": "business_rule"},
        metadata_json={},
    )
    pool_asset = AssetRegistry(
        id=20,
        asset_type="real_user_example_pool",
        asset_key="wangyue_child_growth_xhs_real_user_pool",
        version_no=1,
        content_json={},
        metadata_json={},
    )
    pool_items = [
        {
            "source_type": "note",
            "text": "上幼儿园后接触人多，选旺玥就是看中日常保护力。",
            "title": "入园记录",
            "tags": ["幼儿园", "保护力"],
            "risk_tags": [],
            "quality_score": 20,
            "dedupe_hash": "route-1",
        },
        {
            "source_type": "note",
            "text": "餐桌边那个杯子总放在老位置，晚上收的时候还能看到一点奶渍。",
            "title": "日常细节",
            "tags": ["喝奶接受度"],
            "risk_tags": [],
            "quality_score": 18,
            "dedupe_hash": "detail-1",
        },
        {
            "source_type": "note",
            "text": "除了贵点没毛病。",
            "title": "短句",
            "tags": ["价格"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "texture-1",
        },
        {
            "source_type": "note",
            "text": "后面能少折腾点就行。",
            "title": "收尾",
            "tags": ["喝奶接受度"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "ending-1",
        },
    ]

    plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
        real_user_pool_asset=pool_asset,
        real_user_pool_items=pool_items,
        real_user_pool_config={"route_count": 1, "detail_count": 1, "texture_count": 1, "ending_count": 1, "comment_count": 0},
    )

    assert [item["example_layer"] for item in plan["real_user_examples"]] == ["route", "detail", "texture", "ending"]
    assert plan["real_user_pool"]["selected"]["detail"] == 1
    assert plan["real_user_pool"]["selected"]["ending"] == 1
    assert plan["real_user_pool"]["requested"]["note"] == 4


def test_article_business_rule_plan_passes_detail_family_filter():
    service = ContentBatchPlanner(None)
    rule = {
        "rule_id": "business_rule_002",
        "business_rule": "精力不足，户外活动和保护力观察",
        "topic": "精力不足，户外活动和保护力观察",
        "corpus": "孩子活动量大，妈妈关注旺玥的保护力和眼脑营养。",
        "examples": [],
    }
    asset = AssetRegistry(
        id=10,
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        version_no=1,
        content_json={"rule_type": "business_rule"},
        metadata_json={},
    )
    pool_asset = AssetRegistry(
        id=20,
        asset_type="real_user_example_pool",
        asset_key="wangyue_child_growth_xhs_real_user_pool",
        version_no=1,
        content_json={},
        metadata_json={},
    )
    pool_items = [
        {
            "source_type": "note",
            "text": "看成分表看到头大，配料到底干嘛用的我也没看懂。",
            "title": "记录",
            "tags": ["营养"],
            "risk_tags": [],
            "quality_score": 90,
            "dedupe_hash": "ingredient-detail",
            "example_layer": "detail",
            "detail_family": "ingredient_note",
        },
        {
            "source_type": "note",
            "text": "玩嗨了回来，状态还能继续在线。",
            "title": "记录",
            "tags": ["户外", "保护力"],
            "risk_tags": [],
            "quality_score": 20,
            "dedupe_hash": "activity-detail",
            "example_layer": "detail",
            "detail_family": "row2_real_life_grain",
        },
    ]

    plan = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
        real_user_pool_asset=pool_asset,
        real_user_pool_items=pool_items,
        real_user_pool_config={
            "route_count": 0,
            "detail_count": 1,
            "texture_count": 0,
            "comment_count": 0,
            "detail_family_include": ["row2_real_life_grain"],
        },
    )

    assert plan["real_user_examples"][0]["dedupe_hash"] == "activity-detail"
    assert plan["real_user_pool"]["detail_family_include"] == ["row2_real_life_grain"]
    assert plan["real_user_pool"]["detail_family_counts"] == {"row2_real_life_grain": 1}


def test_article_business_rule_plan_avoids_reusing_route_family_across_batch():
    service = ContentBatchPlanner(None)
    rule = {
        "rule_id": "business_rule_001",
        "business_rule": "容易中招，日常保护力观察",
        "topic": "容易中招，日常保护力观察",
        "corpus": "孩子上幼儿园后接触人多，妈妈关注保护力。",
        "examples": [],
    }
    asset = AssetRegistry(
        id=10,
        asset_type="article_business_rule_set",
        asset_key="wangyue_article_business_rules",
        version_no=1,
        content_json={"rule_type": "business_rule"},
        metadata_json={},
    )
    pool_asset = AssetRegistry(
        id=20,
        asset_type="real_user_example_pool",
        asset_key="wangyue_child_growth_xhs_real_user_pool",
        version_no=1,
        content_json={},
        metadata_json={},
    )
    pool_items = [
        {
            "source_type": "note",
            "text": "上幼儿园后接触人多，选旺玥就是看中日常保护力。",
            "title": "入园记录",
            "tags": ["幼儿园", "保护力"],
            "risk_tags": [],
            "quality_score": 30,
            "dedupe_hash": "school-route",
        },
        {
            "source_type": "note",
            "text": "户外活动量大以后，妈妈更关注孩子每天那杯奶。",
            "title": "户外记录",
            "tags": ["户外", "营养"],
            "risk_tags": [],
            "quality_score": 20,
            "dedupe_hash": "outdoor-route",
        },
        {
            "source_type": "note",
            "text": "除了贵点没毛病。",
            "title": "短句",
            "tags": ["价格"],
            "risk_tags": [],
            "quality_score": 12,
            "dedupe_hash": "texture-1",
        },
    ]
    used_hashes: set[str] = set()
    used_families: set[str] = set()

    first = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=1,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
        real_user_pool_asset=pool_asset,
        real_user_pool_items=pool_items,
        real_user_pool_config={"route_count": 1, "texture_count": 1, "comment_count": 0},
        used_real_user_hashes=used_hashes,
        used_real_user_route_families=used_families,
    )
    second = service._product_experience_plan_from_rule(
        rule,
        asset=asset,
        item_no=2,
        keyword_asset_key="wangyue_article_generation_keywords",
        quality_guard_profile_key=None,
        model_config=None,
        real_user_pool_asset=pool_asset,
        real_user_pool_items=pool_items,
        real_user_pool_config={"route_count": 1, "texture_count": 1, "comment_count": 0},
        used_real_user_hashes=used_hashes,
        used_real_user_route_families=used_families,
    )

    assert first["real_user_examples"][0]["route_family"] == "school_collective"
    assert second["real_user_examples"][0]["route_family"] == "outdoor_activity"
    assert [item["example_layer"] for item in first["real_user_examples"]] == ["route", "texture"]
    assert [item["example_layer"] for item in second["real_user_examples"]] == ["route"]
    assert first["real_user_pool"]["selected"]["texture"] == 1
    assert second["real_user_pool"]["selected"]["texture"] == 0
    assert second["real_user_pool"]["fallback_reused_dedupe_hashes"] == []


def test_mouth_phrase_budget_assigns_allowed_and_avoid_terms():
    from app.services.content_batch_planner import _build_mouth_phrase_budget_items

    items = _build_mouth_phrase_budget_items(
        {
            "enabled": True,
            "batch_size": 20,
            "groups": [
                {"code": "time_recent", "terms": ["最近"], "max_per_20": 3},
                {"code": "peace_closure", "terms": ["省心", "踏实"], "max_per_20": 4},
                {
                    "code": "real_texture",
                    "terms": ["谁懂", "老母亲"],
                    "max_per_term_per_20": 2,
                },
            ],
        },
        item_count=20,
    )

    assert len(items) == 20
    assert all(item and item["enabled"] is True for item in items)
    recent_allowed = sum(1 for item in items if "最近" in item["allowed_terms"])
    peace_allowed = sum(1 for item in items if set(item["allowed_terms"]) & {"省心", "踏实"})
    assert recent_allowed <= 3
    assert peace_allowed <= 4
    assert all("最近" not in item["avoid_terms"] for item in items if "最近" in item["allowed_terms"])
    assert any("最近" in item["avoid_terms"] for item in items if "最近" not in item["allowed_terms"])


def test_rule_can_remove_mouth_phrase_group_from_allowed_terms():
    from app.services.content_batch_planner import _mouth_phrase_budget_for_rule

    budget = {
        "enabled": True,
        "allowed_terms": ["最近", "跟得上"],
        "avoid_terms": ["省心"],
        "groups": [
            {"code": "time_recent", "terms": ["最近"], "max_count": 1},
            {"code": "support_metaphor", "terms": ["跟得上", "撑住"], "term_limits": {"跟得上": 1, "撑住": 1}},
        ],
    }

    resolved = _mouth_phrase_budget_for_rule(
        {"mouth_phrase_budget_no_allow_groups": ["support_metaphor"]},
        budget,
    )

    assert resolved["allowed_terms"] == ["最近"]
    assert "跟得上" in resolved["avoid_terms"]
    assert "撑住" in resolved["avoid_terms"]


def test_mouth_phrase_budget_config_merges_content_groups_over_stale_metadata():
    from app.services.content_batch_planner import _resolve_mouth_phrase_budget_config

    asset = AssetRegistry(
        content_json={
            "mouth_phrase_budget": {
                "enabled": True,
                "batch_size": 20,
                "groups": [
                    {"code": "peace_closure", "terms": ["省心", "踏实"], "max_per_20": 3},
                    {"code": "state_template", "terms": ["精神头", "状态稳"], "max_per_20": 3},
                ],
            }
        },
        metadata_json={
            "mouth_phrase_budget": {
                "enabled": True,
                "batch_size": 20,
                "groups": [
                    {"code": "peace_closure", "terms": ["省心", "踏实"], "max_per_20": 4},
                    {"code": "rare_hedge", "terms": ["不知道是不是心理作用"], "max_per_20": 1},
                ],
            }
        },
    )

    config = _resolve_mouth_phrase_budget_config(asset)

    groups = {group["code"]: group for group in config["groups"]}
    assert set(groups) == {"peace_closure", "state_template", "rare_hedge"}
    assert groups["peace_closure"]["max_per_20"] == 3
    assert groups["state_template"]["terms"] == ["精神头", "状态稳"]


@pytest.mark.asyncio
async def test_latest_real_user_pool_asset_queries_id_before_loading_full_json():
    class FakeResult:
        def scalar_one_or_none(self):
            return 20

    class FakeSession:
        def __init__(self):
            self.statement = None
            self.loaded_id = None

        async def execute(self, statement):
            self.statement = statement
            return FakeResult()

        async def get(self, model, asset_id):
            self.loaded_id = asset_id
            return AssetRegistry(
                id=asset_id,
                asset_type="real_user_example_pool",
                asset_key="maternal_infant_xhs_real_user_pool",
                version_no=3,
                content_json={"items": [{"source_type": "note", "text": "真人原句"}]},
            )

    session = FakeSession()
    service = ContentBatchPlanner(session)
    rule_asset = AssetRegistry(
        content_json={"real_user_pool_asset_key": "maternal_infant_xhs_real_user_pool"},
        metadata_json={},
    )

    asset = await service._latest_real_user_pool_asset(rule_asset)

    selected_columns = list(session.statement.selected_columns)
    assert [column.name for column in selected_columns] == ["id"]
    assert session.loaded_id == 20
    assert asset.asset_key == "maternal_infant_xhs_real_user_pool"


def test_model_config_rotation_merges_base_by_item_no():
    base = {"provider_code": "aihubmix", "temperature": 0.9}
    rotation = [
        {"model_code": "deepseek-v4-flash", "ge_model": "deepseek-v4-flash", "ae_model": "deepseek-v4-flash"},
        {"model_code": "glm-5.2", "ge_model": "glm-5.2", "ae_model": "glm-5.2"},
    ]

    first = _rotated_model_config(1, base, rotation)
    second = _rotated_model_config(2, base, rotation)
    third = _rotated_model_config(3, base, rotation)

    assert first == {
        "provider_code": "aihubmix",
        "temperature": 0.9,
        "model_code": "deepseek-v4-flash",
        "ge_model": "deepseek-v4-flash",
        "ae_model": "deepseek-v4-flash",
    }
    assert second["model_code"] == "glm-5.2"
    assert second["provider_code"] == "aihubmix"
    assert second["temperature"] == 0.9
    assert third["model_code"] == "deepseek-v4-flash"


@pytest.mark.asyncio
async def test_content_batch_planner_creates_100_diverse_yuanyue_plans():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[AssetRegistry.__table__, ContentBatchJob.__table__, ContentBatchItem.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add_all(
            [
                AssetRegistry(
                    asset_type="painpoint_model",
                    asset_key="yuanyue",
                    display_name="源悦痛点模型",
                    version_no=1,
                    status="active",
                    content_json={
                        "items": [
                            {"painpoint": "便便不规律", "symptom": "拉臭费劲", "description": "便便状态不稳定", "selling_point": "好消化易吸收"},
                            {"painpoint": "肚肚不舒服", "symptom": "胀气", "description": "喝奶后肚肚闹腾", "selling_point": "温和"},
                            {"painpoint": "换奶适应", "symptom": "适应慢", "description": "换奶期担心不适应", "selling_point": "软分子蛋白"},
                        ]
                    },
                ),
                AssetRegistry(
                    asset_type="product_selling_points",
                    asset_key="yuanyue",
                    display_name="源悦产品卖点",
                    version_no=1,
                    status="active",
                    content_json={
                        "items": [
                            {"selling_point": "好消化易吸收", "advantage": "软凝乳"},
                            {"selling_point": "温和", "advantage": "亲和宝宝肚肚"},
                            {"selling_point": "软分子蛋白", "advantage": "结构松散"},
                        ]
                    },
                ),
                AssetRegistry(
                    asset_type="reference_examples",
                    asset_key="yuanyue",
                    display_name="源悦参考例文",
                    version_no=1,
                    status="active",
                    content_json={
                        "items": [
                            {"example_id": "ex1", "title": "过来人经验", "body": "先观察宝宝便便状态", "style_tags": ["经验笔记"]},
                            {"example_id": "ex2", "title": "场景共鸣", "body": "新手妈妈别焦虑", "style_tags": ["场景共鸣"]},
                            {"example_id": "ex3", "title": "选择清单", "body": "看消化和适应", "style_tags": ["清单型"]},
                        ]
                    },
                ),
                AssetRegistry(
                    asset_type="reference_writing_patterns",
                    asset_key="yuanyue",
                    display_name="源悦写法资产",
                    version_no=1,
                    status="active",
                    asset_stage="candidate",
                    content_json={
                        "items": [
                            {
                                "pattern_id": "wp1",
                                "topic_fit": ["便便不规律"],
                                "audience_fit": ["新手妈妈"],
                                "style_fit": ["经验老道型"],
                                "opening_pattern": "先共情便便焦虑",
                                "story_arc": "痛点场景 -> 观察判断 -> 轻建议",
                                "proof_style": "日常观察记录",
                            },
                            {
                                "pattern_id": "wp2",
                                "topic_fit": ["换奶适应"],
                                "audience_fit": ["转奶期宝宝家长"],
                                "style_fit": ["清单型"],
                                "opening_pattern": "先列换奶清单",
                                "story_arc": "清单 -> 对比 -> 收束",
                                "proof_style": "清单建议",
                            },
                        ]
                    },
                ),
                AssetRegistry(
                    asset_type="compliance_rules",
                    asset_key="yuanyue",
                    display_name="源悦审核规则",
                    version_no=1,
                    status="active",
                    content_json={"items": [{"dimension": "禁止治疗便秘", "risk_level": "high"}]},
                ),
            ]
        )
        await session.commit()

        planner = ContentBatchPlanner(session)
        job = await planner.create_batch_plan(
            asset_key="yuanyue",
            product_topic="宝宝便便不规律",
            target_audience="新手妈妈",
            style="经验老道型",
            count=100,
            created_by="test",
        )
        await session.commit()

    async with session_factory() as session:
        items = (
            await session.execute(
                select(ContentBatchItem).where(ContentBatchItem.batch_id == job.id).order_by(ContentBatchItem.item_no)
            )
        ).scalars().all()

    assert job.count == 100
    assert len(items) == 100
    assert all(item.status == "planned" for item in items)
    assert all(item.plan_json["asset_key"] == "yuanyue" for item in items)
    assert all(item.plan_json["painpoint_ref"] for item in items)
    assert all(item.plan_json["reference_example_refs"] for item in items)
    assert all(item.plan_json["writing_pattern_ref"] for item in items)
    assert all(item.plan_json["compliance_rule_refs"] for item in items)
    assert all(item.plan_json["brief_constraints"]["word_count"] == "150-250" for item in items)
    assert all(item.plan_json["brief_constraints"]["emoji"] == "少量" for item in items)
    assert job.diversity_plan_json == {}
    assert all("diversity_slot" not in item.plan_json for item in items)

    asset_combo_keys = [item.plan_json["asset_combo_key"] for item in items]
    plan_signatures = {
        (
            item.plan_json["painpoint_ref"]["item_index"],
            item.plan_json["selling_point_ref"]["item_index"],
            item.plan_json["reference_example_refs"][0]["item_index"],
        )
        for item in items
    }

    assert len(plan_signatures) == 27
    assert len(set(asset_combo_keys[:27])) == 27
    assert items[27].plan_json["asset_reuse_reason"] == "素材组合池已用完，按轮换策略复用"
    assert items[0].plan_json["writing_pattern_ref"]["item_id"] == "wp1"


@pytest.mark.asyncio
async def test_content_batch_planner_accepts_topic_based_painpoint_model():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[AssetRegistry.__table__, ContentBatchJob.__table__, ContentBatchItem.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add_all(
            [
                AssetRegistry(
                    asset_type="painpoint_model",
                    asset_key="yuanyue",
                    display_name="源悦主题/痛点模型",
                    version_no=1,
                    status="active",
                    content_json={
                        "topics": [
                            {
                                "topic": "便便不规律",
                                "descriptions": ["羊屎蛋/干硬", "便便又干又硬"],
                                "selling_points": [{"selling_point": "好消化易吸收"}],
                            }
                        ]
                    },
                ),
                AssetRegistry(
                    asset_type="product_selling_points",
                    asset_key="yuanyue",
                    display_name="源悦产品卖点",
                    version_no=1,
                    status="active",
                    content_json={"items": [{"selling_point": "好消化易吸收", "advantage": "软凝乳"}]},
                ),
                AssetRegistry(
                    asset_type="reference_examples",
                    asset_key="yuanyue",
                    display_name="源悦参考例文",
                    version_no=1,
                    status="active",
                    content_json={"items": [{"example_id": "ex1", "title": "过来人经验", "body": "新手妈妈别焦虑"}]},
                ),
                AssetRegistry(
                    asset_type="reference_writing_patterns",
                    asset_key="yuanyue",
                    display_name="源悦写法资产",
                    version_no=1,
                    status="active",
                    asset_stage="candidate",
                    content_json={
                        "items": [
                            {
                                "pattern_id": "wp_topic",
                                "topic_fit": ["便便不规律"],
                                "audience_fit": ["新手妈妈"],
                                "style_fit": ["经验老道型"],
                                "opening_pattern": "先共情便便焦虑",
                            }
                        ]
                    },
                ),
            ]
        )
        await session.commit()

        job = await ContentBatchPlanner(session).create_batch_plan(
            asset_key="yuanyue",
            product_topic="便便不规律",
            target_audience="新手妈妈",
            style="经验老道型",
            count=1,
            created_by="test",
        )
        await session.commit()
        item = await session.scalar(select(ContentBatchItem).where(ContentBatchItem.batch_id == job.id))

    assert item is not None
    painpoint = item.plan_json["painpoint_ref"]["snapshot"]
    assert painpoint["painpoint"] == "便便不规律"
    assert painpoint["description"] == "羊屎蛋/干硬；便便又干又硬"
    assert painpoint["selling_point"] == "好消化易吸收"
    assert item.plan_json["writing_pattern_ref"]["item_id"] == "wp_topic"


@pytest.mark.asyncio
async def test_content_batch_planner_accepts_article_business_rule_set_focus_rule():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[AssetRegistry.__table__, ContentBatchJob.__table__, ContentBatchItem.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type="article_business_rule_set",
                asset_key="a2_sentiment_post_activity",
                display_name="A2舆情相关帖子业务规则",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "rule_type": "article_business",
                    "activity_name": "A2舆情相关帖子",
                    "quality_guard_profile_key": "a2_sentiment_post_202606",
                    "generation_requirements": "输出 JSON 对象，字段为 title 和 body。",
                    "items": [
                        {
                            "rule_id": "post_rule_001",
                            "business_rule": "门店到货",
                            "corpus": "写a2到货后的真实短帖。",
                            "source_row_no": 1,
                        },
                        {
                            "rule_id": "post_rule_002",
                            "business_rule": "线上有货",
                            "corpus": "写线上看到a2有货后的真实短帖。",
                            "source_row_no": 2,
                        },
                    ],
                },
            )
        )
        await session.commit()

        job = await ContentBatchPlanner(session).create_batch_plan(
            asset_key="a2_sentiment_post_activity",
            rule_id="post_rule_002",
            product_topic=None,
            target_audience=None,
            style=None,
            count=10,
            created_by="test",
        )
        await session.commit()
        items = (
            await session.execute(
                select(ContentBatchItem).where(ContentBatchItem.batch_id == job.id).order_by(ContentBatchItem.item_no)
            )
        ).scalars().all()

    assert job.product_topic == "A2舆情相关帖子"
    assert job.strategy_json["source"] == "article_business_rule_set"
    assert job.strategy_json["quality_guard_profile_key"] == "a2_sentiment_post_202606"
    assert len(items) == 10
    assert {item.plan_json["rule_id"] for item in items} == {"post_rule_002"}
    assert all(item.plan_json["output_fields"] == ["title", "body"] for item in items)
    assert all(item.plan_json["quality_guard_profile_key"] == "a2_sentiment_post_202606" for item in items)
    assert job.diversity_plan_json == {}
    assert all("diversity_slot" not in item.plan_json for item in items)
