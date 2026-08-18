import pytest
import pytest_asyncio
from unittest.mock import patch
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.expert_config import ExpertConfig
from app.models.maga_assets import AssetRegistry
from app.services.unified_content_generation_service import (
    DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
    SYSTEM_KEYWORD_ASSET_TYPE,
    UnifiedContentGenerationService,
    _apply_article_slot_coherence,
    _article_output_format_requirement,
    _business_rule_text,
    _comment_prompt_text,
    _layered_article_prompt,
    _select_comment_prompt_slots,
    _select_comment_tone,
    _normalize_model_config,
    _render_comment_prompt_slot,
    _royal_compact_article_prompt,
    _template_variables,
)


@pytest_asyncio.fixture
async def unified_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[AssetRegistry.__table__, ExpertConfig.__table__],
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


def test_article_output_format_supports_explicit_two_items_mode():
    single = _article_output_format_requirement("article", ["title", "body"], {})
    multi = _article_output_format_requirement("article", ["title", "body"], {"multi_output_count": 2})

    assert single == '只输出 JSON：{"title":"...","body":"..."}。'
    assert '只输出 JSON object，格式：{"items":[{"title":"...","body":"..."}]}。' in multi
    assert "items 必须正好 2 个" in multi
    assert "一次生成 2 篇" not in multi


@pytest.mark.asyncio
async def test_complete_comment_prompt_is_model_visible_without_global_prompt_layers(unified_session_factory):
    prompt = "# 任务\n\n一次生成10条评论。\n\n只输出一个 JSON 对象。"
    async with unified_session_factory() as session:
        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={
                "asset_key": "a2_sentiment_comment_activity",
                "prompt_mode": "complete_comment_prompt",
                "complete_comment_prompt": prompt,
                "output_format_mode": "json_object_items",
                "expansion_count": 10,
                "experiment_profile": {"profile_code": "a2_stock_comment_batch10_v1"},
            },
            item_no=1,
            output_fields=["comment"],
        )

    assert snapshot.input_snapshot["rendered_prompt"] == prompt
    assert snapshot.input_snapshot["selected_keywords"] == []
    assert snapshot.input_snapshot["selected_prompt_slots"] == []
    assert snapshot.input_snapshot["comment_tone"] is None
    assert snapshot.input_snapshot["output_format"] == {
        "mode": "json_object_items",
        "count": 10,
    }


def test_rule_corpus_as_prompt_keeps_single_article_output_format():
    from app.services.unified_content_generation_service import _rule_corpus_as_prompt_article_prompt

    prompt = _rule_corpus_as_prompt_article_prompt(
        {
            "business_rule": "任务：写1篇妈妈UGC。",
            "output_format_requirement": _article_output_format_requirement(
                "article",
                ["title", "body"],
                {},
            ),
        },
        selected_keywords=[],
    )

    assert '只输出 JSON：{"title":"...","body":"..."}。' in prompt
    assert "items 必须正好" not in prompt
    assert '"items"' not in prompt
    assert "基于量子态叠加与多重可能性" in prompt


@pytest.mark.asyncio
async def test_rule_corpus_as_prompt_snapshot_does_not_load_expression_keywords(unified_session_factory):
    async with unified_session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type=SYSTEM_KEYWORD_ASSET_TYPE,
                asset_key="wangyue_v3_minimal_generation_keywords",
                display_name="旺玥表达扩散语料",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "categories": [
                        _category("perturbation_rule", "扰动规则", ["不应从资产进入 prompt。"]),
                    ]
                },
            )
        )
        await session.commit()

        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="article",
            business_rule={
                "asset_key": "wangyue_v3_core_storyline_article_rules",
                "keyword_asset_key": "wangyue_v3_minimal_generation_keywords",
                "prompt_mode": "rule_corpus_as_prompt",
                "corpus": "生文指令：写一篇妈妈UGC。",
            },
            item_no=1,
            output_fields=["title", "body"],
        )

    assert snapshot.input_snapshot["selected_keywords"] == []
    assert snapshot.input_snapshot["keyword_asset"] is None
    assert snapshot.asset_refs["keyword_asset"] is None
    assert "不应从资产进入 prompt" not in snapshot.input_snapshot["rendered_prompt"]
    assert "基于量子态叠加与多重可能性" in snapshot.input_snapshot["rendered_prompt"]
    assert '只输出 JSON：{"title":"...","body":"..."}。' in snapshot.input_snapshot["rendered_prompt"]


def test_layered_article_prompt_renders_the_five_layer_framework():
    prompt = _layered_article_prompt(
        {
            "generation_instruction": "写一篇小红书妈妈 UGC 正向记录。",
            "content_direction": "写妈妈在常买门店看到a2至初到货，顺手补上熟悉口粮。",
            "activity_material": ["活动信息：门店已经到货。", "产品事实：现场可以自行查看对应报告。"],
            "selling_expression": "熟悉口粮能接上，家里不用临时换来换去。",
            "selling_expression_note": "只写家庭安排，不扩成产品效果。",
            "selling_painpoint_group": "有货+补充奶量不足",
            "selling_painpoint_expression": "家里口粮能接上，孩子愿意喝，补奶量时省事一些。",
            "hard_boundaries": ["不写成官方到货公告。"],
            "writing_requirements": ["标题从正文自然提炼。"],
            "generation_requirements": ["不要写成官方公告。"],
            "variation_slots": [
                {
                    "slot_code": "inspiration_material",
                    "slot_name": "本篇灵感线索",
                    "value": "和下班顺路有关",
                },
                {
                    "slot_code": "activity_prize",
                    "slot_name": "活动奖品素材",
                    "value": "现场看到一份新客礼盒。",
                },
                {
                    "slot_code": "batch_detection",
                    "slot_name": "批批检素材",
                    "value": "扫罐底码能看对应批次的检测报告。",
                },
            ],
            "examples": ["今天路过常买母婴店，看到a2至初已经到了。"],
        },
        selected_keywords=[
            {
                "category_code": "writing_instruction",
                "corpus": ["像真实妈妈写一段完整分享。"],
            },
            {
                "category_code": "persona",
                "corpus": ["像普通家庭妈妈自然表达。"],
            },
            {
                "category_code": "article_format_control",
                "corpus": ["正文保持紧凑。"],
            },
        ],
        output_format="只输出 JSON 对象，字段只能包含 title 和 body。",
    )

    assert prompt.startswith("生文指令：\n写一篇小红书妈妈 UGC 正向记录。")
    assert "像真实妈妈写一段完整分享。" not in prompt
    assert "内容方向：\n写妈妈在常买门店看到a2至初到货" in prompt
    assert "本篇素材：\n- 灵感线索：和下班顺路有关" in prompt
    assert "- 活动信息：门店已经到货。" in prompt
    assert "- 活动奖品素材：现场看到一份新客礼盒。" in prompt
    assert "- 批批检素材：扫罐底码能看对应批次的检测报告。" in prompt
    assert "- 卖点痛点表达：家里口粮能接上，孩子愿意喝，补奶量时省事一些。" in prompt
    assert "有货+补充奶量不足" not in prompt
    assert "- 卖点表达：熟悉口粮能接上" not in prompt
    assert "写法：\n- 标题从正文自然提炼。" in prompt
    assert "生成要求：\n- 不要写成官方公告。\n- 不写成官方到货公告。" in prompt
    assert "像普通家庭妈妈自然表达。" not in prompt
    assert "正文保持紧凑。" not in prompt
    assert "- 只输出 JSON 对象" in prompt


def test_layered_article_prompt_does_not_duplicate_configured_output_requirement():
    output_format = '只输出 JSON：{"title":"...","body":"..."}。'

    prompt = _layered_article_prompt(
        {
            "content_direction": "记录一个普通日常瞬间。",
            "generation_requirements": [output_format],
        },
        selected_keywords=[],
        output_format=output_format,
    )

    assert prompt.count(output_format) == 1


def test_layered_article_prompt_renders_selected_info_source_as_generation_material():
    prompt = _layered_article_prompt(
        {
            "generation_instruction": "写一篇小红书妈妈 UGC 正向记录。",
            "content_direction": "写妈妈选奶时确认莼悦。",
            "selling_painpoint_expression": "奶源更干净",
            "variation_slots": [
                {
                    "slot_code": "info_source",
                    "slot_name": "信息来源线索",
                    "value": "朋友聊天",
                }
            ],
        },
        selected_keywords=[],
        output_format="只输出 JSON 对象，字段只能包含 title 和 body。",
    )

    assert "本篇素材：\n- 信息来源线索：朋友聊天" in prompt
    assert "- 卖点痛点表达：奶源更干净" in prompt


def test_layered_article_prompt_uses_selected_direction_and_activity_material_slots():
    prompt = _layered_article_prompt(
        {
            "generation_instruction": "写一篇普通宝妈的纯分享笔记。",
            "content_direction": "静态兜底方向。",
            "variation_slots": [
                {
                    "slot_code": "content_direction",
                    "slot_name": "内容方向",
                    "value": "直给参加活动，讲完活动再提每批检测，最后写体验和认可。",
                },
                {
                    "slot_code": "info_source",
                    "slot_name": "活动了解途径",
                    "value": "去门店时导购说起。",
                },
                {
                    "slot_code": "participation_motive",
                    "slot_name": "参加活动原因",
                    "value": "觉得这次升级挺有诚意。",
                },
                {
                    "slot_code": "activity_content",
                    "slot_name": "活动内容",
                    "value": "集12罐兑换1罐奶粉。",
                },
                {
                    "slot_code": "product_experience",
                    "slot_name": "活动后的产品体验",
                    "value": "a2至初粉质细腻，好冲开。",
                },
                {
                    "slot_code": "consumer_praise",
                    "slot_name": "活动后的消费者认可",
                    "value": "觉得a2做得认真，愿意推荐。",
                },
                {
                    "slot_code": "positive_expression",
                    "slot_name": "活动分享正向表达",
                    "value": "品质在线。",
                },
            ],
        },
        selected_keywords=[],
        output_format="只输出 JSON。",
    )

    assert "内容方向：\n直给参加活动，讲完活动再提每批检测" in prompt
    assert "静态兜底方向" not in prompt
    assert "- 活动了解途径：去门店时导购说起。" in prompt
    assert "- 参加活动原因：觉得这次升级挺有诚意。" in prompt
    assert "- 活动内容：集12罐兑换1罐奶粉。" in prompt
    assert "- 活动后的产品体验：a2至初粉质细腻，好冲开。" in prompt
    assert "- 活动后的消费者认可：觉得a2做得认真，愿意推荐。" in prompt
    assert "- 活动分享正向表达：品质在线。" in prompt


def test_layered_article_prompt_renders_merged_consumer_recognition_slot():
    prompt = _layered_article_prompt(
        {
            "generation_instruction": "写一篇普通宝妈分享。",
            "content_direction": "活动后提检测，再写认可。",
            "variation_slots": [
                {
                    "slot_code": "activity_content",
                    "slot_name": "活动内容",
                    "value": "积分、集罐、抽奖、回馈礼都有。",
                },
                {
                    "slot_code": "batch_detection",
                    "slot_name": "批批检素材",
                    "value": "a2至初现在每批都有检测。",
                },
                {
                    "slot_code": "consumer_recognition",
                    "slot_name": "认可表达",
                    "value": "消费者有被重视到，品质也更透明。a2至初奶香自然。",
                    "item_id": "bf_001",
                },
            ],
        },
        selected_keywords=[],
        output_format="只输出 JSON。",
    )

    assert "- 活动内容：积分、集罐、抽奖、回馈礼都有。" in prompt
    assert "- 批批检素材：a2至初现在每批都有检测。" in prompt
    assert "- 认可表达：消费者有被重视到，品质也更透明。a2至初奶香自然。" in prompt


def test_layered_article_prompt_renders_no_source_control_as_generation_material():
    prompt = _layered_article_prompt(
        {
            "generation_instruction": "写一篇小红书妈妈 UGC 正向记录。",
            "content_direction": "写妈妈选奶时确认莼悦。",
            "selling_painpoint_expression": "奶源更干净",
            "variation_slots": [
                {
                    "slot_code": "info_source",
                    "slot_name": "信息来源线索",
                    "value": "正文不写来源",
                }
            ],
        },
        selected_keywords=[],
        output_format="只输出 JSON 对象，字段只能包含 title 和 body。",
    )

    assert "本篇素材：\n- 信息来源线索：正文不写来源" in prompt
    assert "- 卖点痛点表达：奶源更干净" in prompt


@pytest.mark.asyncio
async def test_layered_article_snapshot_does_not_load_default_expression_keywords(unified_session_factory):
    async with unified_session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type=SYSTEM_KEYWORD_ASSET_TYPE,
                asset_key=DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
                display_name="默认表达语料",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "categories": [
                        _category("article_speaking_style", "帖子说话方式", ["又开一听记录"]),
                    ]
                },
            )
        )
        await session.commit()

        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="article",
            business_rule={
                "rule_type": "business_rule",
                "prompt_mode": "layered_article",
                "generation_instruction": "写一篇妈妈班分享。",
                "content_direction": "写待产妈妈听完课后理清第一口奶选择。",
                "inspiration_material": "和课后记下的一句话有关。",
                "activity_material": ["活动发生在妈妈班。"],
                "selling_expression": "a2至初含A2型蛋白质。",
                "hard_boundaries": ["宝宝尚未出生。"],
                "writing_requirements": ["正文130-200字。"],
            },
            item_no=1,
            output_fields=["title", "body"],
        )

    assert snapshot.input_snapshot["selected_keywords"] == []
    assert snapshot.input_snapshot["keyword_asset"] is None
    assert snapshot.asset_refs["keyword_asset"] is None
    assert "又开一听记录" not in snapshot.input_snapshot["rendered_prompt"]
    assert "本篇素材：\n- 灵感线索：和课后记下的一句话有关。" in snapshot.input_snapshot["rendered_prompt"]


def test_comment_prompt_renders_selected_instruction_and_format_layers():
    prompt = _comment_prompt_text(
        {
            "asset_key": "a2_sentiment_comment_activity",
            "business_rule": "批批检-报告查询互动",
            "corpus": "旧规则语料不应优先渲染。",
            "content_direction": "围绕看到一项品牌信息后的自然反应接话。",
            "activity_material": ["a2公开每批检测信息", "对应批次报告可以查询"],
        },
        selected_keywords=[
            {
                "category_code": "comment_generation_requirement",
                "corpus": ["生成一条小红书母婴社区真实用户评论。"],
            },
            {
                "category_code": "comment_writing_instruction",
                "corpus": ["语言像妈妈在评论区顺手补一句。"],
            },
            {
                "category_code": "comment_format_control",
                "corpus": ["评论控制在21到30字。"],
            },
        ],
    )

    assert "任务：" not in prompt
    assert "生评论指令：" not in prompt
    assert (
        "生文指令：\n- 生成一条小红书母婴社区真实用户评论。\n"
        "- 语言像妈妈在评论区顺手补一句。"
    ) in prompt
    assert "内容方向：\n围绕看到一项品牌信息后的自然反应接话。" in prompt
    assert "本篇素材：\n- a2公开每批检测信息\n- 对应批次报告可以查询" in prompt
    assert "旧规则语料不应优先渲染" not in prompt
    assert "写法：\n- 评论控制在21到30字。" in prompt


def test_comment_prompt_bundle_renders_only_its_own_five_layers():
    prompt = _comment_prompt_text(
        {
            "asset_key": "a2_sentiment_comment_activity",
            "business_rule": "有货-直给简单报喜",
            "prompt_mode": "comment_prompt_bundle",
            "comment_prompt_bundle": {
                "generation_instruction": "生成一条小红书母婴社区真实用户评论，口语化，有活人感。",
                "content_direction": "写看到有货了的即时反应，像在评论区简单报喜。",
                "activity_material": ["a2已经到货、来货，或重新能买到。"],
                "writing_requirements": ["字数在20字以内"],
                "notes": ["不要说缺货、断粮等消极词。"],
            },
            "examples": ["不应该进入Prompt"],
            "comment_tone_options": [
                {"tone_code": "confirm", "tone_label": "确认", "prompt": "不应该进入Prompt"}
            ],
        },
        selected_keywords=[
            {
                "category_code": "comment_writing_instruction",
                "corpus": ["不应该进入Prompt"],
            },
            {
                "category_code": "comment_format_control",
                "corpus": ["不应该进入Prompt"],
            },
        ],
        comment_tone={"tone_label": "确认", "prompt": "不应该进入Prompt"},
    )

    assert prompt == (
        "生文指令：\n"
        "- 生成一条小红书母婴社区真实用户评论，口语化，有活人感。\n\n"
        "内容方向：\n"
        "写看到有货了的即时反应，像在评论区简单报喜。\n\n"
        "内容素材：\n"
        "- a2已经到货、来货，或重新能买到。\n\n"
        "写法：\n"
        "- 字数在20字以内\n\n"
        "生成要求：\n"
        "- 不要说缺货、断粮等消极词。\n\n"
        "只输出评论正文，不要标题、编号、解释。"
    )


def test_comment_prompt_bundle_renders_explicit_batch_expression_path():
    prompt = _comment_prompt_text(
        {
            "asset_key": "a2_sentiment_comment_activity",
            "business_rule": "有货-渠道-不提产品",
            "prompt_mode": "comment_prompt_bundle",
            "bundle_prompt_slots_source": "batch_override",
            "prompt_slots": {
                "本条表达路径": ["不用时间词，从常买渠道切入，用询问句收尾。"]
            },
            "comment_prompt_bundle": {
                "generation_instruction": "生成一条真实用户评论。",
                "content_direction": "写看到有货后的自然反应。",
                "activity_material": ["a2奶粉已经到货，正文不提产品名。"],
                "writing_requirements": ["字数在30字以内"],
                "notes": ["不要说消极词。"],
            },
        },
        selected_prompt_slots=[
            {
                "slot_name": "本条表达路径",
                "text": "不用时间词，从常买渠道切入，用询问句收尾。",
            }
        ],
    )

    assert "本条表达路径：不用时间词，从常买渠道切入，用询问句收尾。" in prompt
    assert "以下参考示例" not in prompt
    assert "本条语气槽" not in prompt


@pytest.mark.asyncio
async def test_comment_prompt_bundle_snapshot_skips_global_keywords_and_tone_slots(unified_session_factory):
    async with unified_session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type=SYSTEM_KEYWORD_ASSET_TYPE,
                asset_key=DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
                display_name="默认表达语料",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "categories": [
                        _category("comment_writing_instruction", "生文指令", ["不应该进入Prompt"]),
                        _category("comment_format_control", "评论格式", ["不应该进入Prompt"]),
                    ]
                },
            )
        )
        await session.commit()

        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={
                "asset_key": "a2_sentiment_comment_activity",
                "business_rule": "有货-直给简单报喜",
                "prompt_mode": "comment_prompt_bundle",
                "comment_prompt_bundle": {
                    "generation_instruction": "生成一条小红书母婴社区真实用户评论。",
                    "content_direction": "写看到有货后的简单报喜。",
                    "activity_material": ["a2已经到货。"],
                    "writing_requirements": ["字数在20字以内"],
                    "notes": ["不要说消极词。"],
                },
                "examples": ["不应该进入Prompt"],
                "comment_tone_options": [
                    {"tone_code": "confirm", "tone_label": "确认", "prompt": "不应该进入Prompt"}
                ],
            },
            item_no=1,
            output_fields=["comment"],
        )

    assert snapshot.input_snapshot["selected_keywords"] == []
    assert snapshot.input_snapshot["selected_prompt_slots"] == []
    assert snapshot.input_snapshot["comment_tone"] is None
    assert snapshot.input_snapshot["keyword_asset"] is None
    assert snapshot.asset_refs["keyword_asset"] is None
    assert "不应该进入Prompt" not in snapshot.input_snapshot["rendered_prompt"]


@pytest.mark.asyncio
async def test_comment_prompt_bundle_snapshot_renders_rule_asset_expression_path(
    unified_session_factory,
):
    async with unified_session_factory() as session:
        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={
                "asset_key": "a2_sentiment_comment_activity",
                "business_rule": "有货-直给-不提产品",
                "prompt_mode": "comment_prompt_bundle",
                "bundle_prompt_slots_source": "rule_asset",
                "prompt_slots": {"本条表达路径": ["像评论区顺手报信。"]},
                "variation_slots": {
                    "旧槽": ["不应该进入Prompt"]
                },
                "comment_prompt_bundle": {
                    "generation_instruction": "生成一条真实用户评论。",
                    "content_direction": "写看到有货后的自然反应。",
                    "activity_material": ["a2奶粉已经到货，正文不提产品名。"],
                    "writing_requirements": ["字数在30字以内"],
                    "notes": ["不要说消极词。"],
                },
                "examples": ["不应该进入Prompt"],
            },
            item_no=1,
            output_fields=["comment"],
        )

    assert snapshot.input_snapshot["selected_prompt_slots"] == [
        {
            "slot_name": "本条表达路径",
            "text": "像评论区顺手报信。",
            "selected_index": 0,
            "candidate_count": 1,
        }
    ]
    assert "本条表达路径：像评论区顺手报信。" in snapshot.input_snapshot["rendered_prompt"]
    assert "不应该进入Prompt" not in snapshot.input_snapshot["rendered_prompt"]


def test_rule_corpus_as_prompt_mode_skips_legacy_article_layers():
    from app.services.unified_content_generation_service import (
        _generation_requirements,
        _keyword_corpus_text,
        _rule_corpus_as_prompt_article_prompt,
    )

    business_rule = {
        "asset_key": "generic_storyline_article_rules",
        "keyword_asset_key": "minimal_generation_keywords",
        "prompt_mode": "rule_corpus_as_prompt",
        "product_name": "旺玥",
        "post_type": "妈妈日记型",
        "product_appearance_mode": "精力不足｜精神状态变化",
        "product_position_mode": "中段自然出现",
        "title_shape_mode": "名词短标题",
        "scene_motive_bucket": "早上赶时间",
        "corpus": (
            "任务：写一篇小红书妈妈UGC正向种草笔记。\n\n"
            "这篇要写的事：\n"
            "给孩子喝了一阵子旺玥奶粉，发现孩子精神头比以前好多了。\n\n"
            "硬边界：\n"
            "- 旺玥是3岁以上儿童喝的。\n\n"
            "写法：\n"
            "- 标题不超过20字。\n"
            "- 正文120-180字左右。"
        ),
    }
    selected_keywords = [
        {
            "category_code": "article_generation_requirement",
            "category_name": "帖子生成要求",
            "keyword_code": "v2_minimal_article_boundary",
            "keyword_name": "v2最小写法边界",
            "corpus": ["标题不超过20字。", "正文120-180字左右。"],
        },
        {
            "category_code": "perturbation_rule",
            "category_name": "扰动规则",
            "keyword_code": "v2_quantum_diversity",
            "keyword_name": "v2发散提醒",
            "corpus": ["生成同质化内容是原罪。"],
        },
    ]

    requirements = _generation_requirements("article", ["title", "body"], business_rule, selected_keywords)
    keyword_corpus = _keyword_corpus_text(
        selected_keywords,
        content_type="article",
        output_fields=["title", "body"],
        business_rule=business_rule,
    )
    rule_text = _business_rule_text(business_rule, content_type="article")

    assert "标题不超过20字" in requirements
    assert "正文120-180字左右" in requirements
    assert "产品事实：旺玥" not in requirements
    assert "产品出现边界" not in requirements
    assert "产品表达边界" not in requirements
    assert "产品出现位置" not in requirements
    assert "时间边界" not in requirements
    assert "标题硬边界" not in requirements
    assert "低权重表达扰动" not in keyword_corpus
    assert "产品事实、成分、正向反馈、产品动作" not in keyword_corpus
    assert "正文事实只按“这篇要写的事”" in keyword_corpus
    assert "产品叙事推进" not in rule_text
    assert "产品进入含义" not in rule_text
    assert "这篇要写的事" in rule_text
    prompt = _rule_corpus_as_prompt_article_prompt(
        {
            "generation_requirements": requirements,
            "business_rule": rule_text,
            "output_format_requirement": '只输出 JSON object，格式：{"items":[{"title":"...","body":"..."}]}。items 必须正好 2 个。',
        },
        selected_keywords=selected_keywords,
    )
    assert prompt.startswith("任务：写一篇小红书妈妈UGC正向种草笔记。")
    assert prompt.count("【生成要求】") == 1
    assert prompt.index("写法：") < prompt.index("【生成要求】")
    assert "你是小红书妈妈UGC写手" not in prompt
    assert "只按给定" not in prompt
    assert "【业务规则】" not in prompt
    assert "【输出格式】" not in prompt
    assert "【发散提醒】" not in prompt
    assert "表达扩散语料" not in prompt
    assert "系统关键词语料" not in prompt
    assert "产品事实：旺玥" not in prompt
    assert "产品出现边界" not in prompt
    assert "产品表达边界" not in prompt


def test_rule_corpus_as_prompt_selects_one_life_entry_slot_by_item_no():
    from app.services.unified_content_generation_service import _rule_corpus_as_prompt_article_prompt

    prompt = _rule_corpus_as_prompt_article_prompt(
        {
            "item_no": 2,
            "slot_rotation_no": 2,
            "business_rule": (
                "生文指令：写妈妈UGC。\n\n"
                "内容方向：\n"
                "从【生活入口】写起，再写孩子比以前更能坐住一点。\n\n"
                "【生活入口槽位】\n"
                "- 妈妈们聊天时提到孩子坐不住\n"
                "- 周末各忙各的，抬头发现孩子还在小桌前\n"
                "- 陪孩子拼图时发现这次没有很快跑开\n\n"
                "【孩子专注事件槽位】\n"
                "- 听绘本时能跟住一段故事\n"
                "- 搭积木倒了以后愿意重新试一次\n"
                "- 玩桌游时能把一轮玩完\n\n"
                "【保护力日常反馈槽位】\n"
                "- 外出回来还愿意讲路上的事\n"
                "- 到饭点照常坐下来吃饭\n"
                "- 回家后继续做自己惦记的事\n\n"
                "【本篇灵感线索】\n"
                "- 和动物相关\n"
                "- 和游戏相关\n"
                "- 和一次出门的小插曲相关\n\n"
                "【卖点表达】\n"
                "- 卖点表达：乳铁蛋白含量优秀\n"
                "  注意：不要讲得太专业\n"
                "- 卖点表达：添加了免疫球蛋白\n"
                "  注意：不要解释免疫机制\n"
                "- 卖点表达：有5大HMO\n"
                "  注意：可以只记得大概\n\n"
                "事实与合规边界：\n"
                "- 不写保证有效。"
            ),
            "output_format_requirement": (
                '只输出 JSON object，格式：{"items":[{"title":"...","body":"..."}]}。'
                "items 必须正好 2 个。"
            ),
        },
        selected_keywords=[],
    )

    assert "从周末各忙各的，抬头发现孩子还在小桌前写起" in prompt
    assert "本篇抽中的生活入口" in prompt
    assert "妈妈们聊天时提到孩子坐不住" not in prompt
    assert "陪孩子拼图时发现这次没有很快跑开" not in prompt
    assert "【生活入口】" not in prompt
    assert "【生活入口槽位】" not in prompt
    assert "搭积木倒了以后愿意重新试一次" in prompt
    assert "听绘本时能跟住一段故事" not in prompt
    assert "玩桌游时能把一轮玩完" not in prompt
    assert "本篇抽中的孩子专注事件" in prompt
    assert "【孩子专注事件槽位】" not in prompt
    assert "到饭点照常坐下来吃饭" in prompt
    assert "外出回来还愿意讲路上的事" not in prompt
    assert "回家后继续做自己惦记的事" not in prompt
    assert "本篇抽中的保护力日常反馈" in prompt
    assert "【保护力日常反馈槽位】" not in prompt
    assert "本篇素材：\n- 灵感线索：和游戏相关" in prompt
    assert "和动物相关" not in prompt
    assert "和一次出门的小插曲相关" not in prompt
    assert "【本篇灵感线索】" not in prompt
    assert "- 卖点表达：添加了免疫球蛋白" in prompt
    assert "- 卖点表达边界：不要解释免疫机制" in prompt
    assert "乳铁蛋白含量优秀" not in prompt
    assert "不要讲得太专业" not in prompt
    assert "有5大HMO" not in prompt
    assert "可以只记得大概" not in prompt
    assert "【卖点表达】" not in prompt
    assert "产品出现位置" not in prompt
    assert "产品叙事推进" not in prompt
    assert "低权重表达扰动" not in prompt
    assert "生成同质化内容是原罪" in prompt
    assert "一次生成 2 篇" not in prompt
    assert '只输出 JSON object，格式：{"items":[{"title":"...","body":"..."}]}。' in prompt
    assert "items 必须正好 2 个。" in prompt


def test_rule_corpus_inspiration_slot_can_render_without_inspiration_material():
    from app.services.unified_content_generation_service import _render_rule_corpus_inspiration_clue_slot

    corpus = (
        "生文指令：写妈妈UGC。\n\n"
        "内容方向：记录一段普通日常，其余内容自行发挥。\n\n"
        "【本篇灵感线索】\n"
        "- 和朋友相关\n"
        "- 不使用灵感线索\n\n"
        "事实与合规边界：\n"
        "- 不写保证有效。"
    )

    rendered = _render_rule_corpus_inspiration_clue_slot(corpus, item_no=2)

    assert "【本篇灵感线索】" not in rendered
    assert "不使用灵感线索" not in rendered
    assert "本篇素材：" not in rendered
    assert "事实与合规边界" in rendered


def test_rule_corpus_selling_expression_can_disable_inspiration_slot():
    from app.services.unified_content_generation_service import _rule_corpus_as_prompt_article_prompt

    prompt = _rule_corpus_as_prompt_article_prompt(
        {
            "item_no": 1,
            "business_rule": (
                "生文指令：写妈妈UGC。\n\n"
                "内容方向：记录一段普通日常。\n\n"
                "【本篇灵感线索】\n"
                "- 和游戏相关\n"
                "- 和朋友相关\n\n"
                "事实与合规边界：\n"
                "- 不写保证有效。"
            ),
            "selling_painpoint_expression": "去年校服裤子短了不少",
            "selling_painpoint_expression_inspiration_mode": "none",
            "output_format_requirement": '只输出 {"title":"...","body":"..."}。',
        },
        selected_keywords=[],
    )

    assert "和游戏相关" not in prompt
    assert "和朋友相关" not in prompt
    assert "灵感线索" not in prompt
    assert "卖点痛点表达：去年校服裤子短了不少" in prompt


def test_rule_corpus_selling_expression_can_select_exact_inspiration_clue():
    from app.services.unified_content_generation_service import _rule_corpus_as_prompt_article_prompt

    prompt = _rule_corpus_as_prompt_article_prompt(
        {
            "item_no": 1,
            "business_rule": (
                "生文指令：写妈妈UGC。\n\n"
                "内容方向：记录一段普通日常。\n\n"
                "【本篇灵感线索】\n"
                "- 和游戏相关\n"
                "- 和整理旧衣服相关\n\n"
                "事实与合规边界：\n"
                "- 不写保证有效。"
            ),
            "selling_painpoint_expression": "营养多样，感觉够娃长身体",
            "selling_painpoint_expression_inspiration_mode": "auto",
            "selling_painpoint_expression_inspiration_clue": "和整理旧衣服相关",
            "output_format_requirement": '只输出 {"title":"...","body":"..."}。',
        },
        selected_keywords=[],
    )

    assert "灵感线索：和整理旧衣服相关" in prompt
    assert "和游戏相关" not in prompt
    assert "卖点痛点表达：营养多样，感觉够娃长身体" in prompt


def test_rule_corpus_selling_expression_note_is_optional():
    from app.services.unified_content_generation_service import _rule_corpus_as_prompt_article_prompt

    prompt = _rule_corpus_as_prompt_article_prompt(
        {
            "item_no": 2,
            "business_rule": (
                "生文指令：写妈妈UGC。\n\n"
                "内容方向：\n记录一件日常。\n\n"
                "【卖点表达】\n"
                "- 卖点表达：乳铁蛋白含量优秀\n"
                "  注意：不要讲得太专业\n"
                "- 卖点表达：不指望它替代一切，但至少钙铁锌这些不会缺\n"
                "- 卖点表达：营养比较丰富\n"
                "  注意：不要照抄\n\n"
                "事实与合规边界：\n- 不写保证有效。"
            ),
            "output_format_requirement": '只输出 {"title":"...","body":"..."}。',
        },
        selected_keywords=[],
    )

    assert "卖点表达：不指望它替代一切，但至少钙铁锌这些不会缺" in prompt
    assert "注意：" not in prompt
    assert "乳铁蛋白含量优秀" not in prompt
    assert "营养比较丰富" not in prompt
    assert "【卖点表达】" not in prompt
    assert "事实与合规边界" in prompt


def test_rule_corpus_as_prompt_injects_structured_selling_painpoint_expression():
    from app.services.unified_content_generation_service import _rule_corpus_as_prompt_article_prompt

    prompt = _rule_corpus_as_prompt_article_prompt(
        {
            "item_no": 1,
            "business_rule": (
                "生文指令：写妈妈UGC。\n\n"
                "内容方向：\n记录一件日常。\n\n"
                "事实与合规边界：\n- 不写保证有效。"
            ),
            "selling_painpoint_group": "进阶保护力+容易中招",
            "selling_painpoint_expression": "选奶时我会比较关注乳铁蛋白和免疫球蛋白。",
            "output_format_requirement": '只输出 {"title":"...","body":"..."}。',
        },
        selected_keywords=[],
    )

    assert "本篇素材：\n- 卖点痛点表达：选奶时我会比较关注乳铁蛋白和免疫球蛋白。" in prompt
    assert "进阶保护力+容易中招" not in prompt
    assert "痛点：容易中招" not in prompt
    assert prompt.index("卖点痛点表达：") < prompt.index("事实与合规边界：")


def test_template_variables_derives_slot_rotation_from_multi_output_group():
    variables = _template_variables(
        content_type="article",
        output_fields=["title", "body"],
        business_rule={
            "item_no": 5,
            "multi_output_group": {"requested_count": 2, "output_index": 0},
        },
        selected_keywords=[],
    )

    assert variables["slot_rotation_no"] == 3


def test_royal_compact_prompt_keeps_rule_mainline_and_drops_random_scenes():
    prompt = _royal_compact_article_prompt(
        {
            "corpus": (
                "写游乐区回来后的一个生活动作。皇家美素佳儿只作为家里这段时间的口粮带一下，"
                "可以轻写这顿接得顺一点。"
            )
        },
        selected_keywords=[
            {
                "category_code": "persona",
                "corpus": ["早上上班前冲奶和收拾孩子都很赶。"],
            },
            {
                "category_code": "article_scene",
                "corpus": ["从电商到货、拆箱、核对清单进入。"],
            },
            {
                "category_code": "article_speaking_style",
                "corpus": ["像边带娃边写的短记录，允许有一点跳跃。"],
            },
            {
                "category_code": "perturbation_rule",
                "corpus": ["同批文章不要写成同一个模板换词。"],
            },
        ],
        output_format="只输出 JSON 对象，字段只能包含 title 和 body。",
    )

    assert prompt.startswith("任务：写一篇小红书妈妈UGC生活记录")
    assert "写游乐区回来后的一个生活动作" in prompt
    assert "像边带娃边写的短记录" in prompt
    assert "业务规则指定的核心卖点要写出来" in prompt
    assert "只展开一个选择理由和一个自家反馈" in prompt
    assert "不自行新增业务规则未指定的专业成分" in prompt
    assert "情绪必须由选择前后的具体事情推动" in prompt
    assert "同批内容只在措辞和节奏上发散" in prompt
    assert "同批文章不要写成同一个模板换词" not in prompt
    assert "早上上班前冲奶" not in prompt
    assert "电商到货" not in prompt
    assert "【生成要求】" not in prompt
    assert "【本次自动选中的表达扩散语料】" not in prompt
    assert "只输出 JSON 对象" in prompt


def test_royal_compact_prompt_renders_only_preselected_rule_variation_slots():
    prompt = _royal_compact_article_prompt(
        {
            "corpus": "写孩子最近活动变多后的一次普通生活观察。",
            "variation_slots": [
                {"slot_code": "info_source", "slot_name": "信息来源", "value": "门店导购"},
                {"slot_code": "life_scene", "slot_name": "生活场景", "value": "家庭聚会"},
            ],
        },
        selected_keywords=[],
        output_format="只输出 JSON 对象，字段只能包含 title 和 body。",
    )

    assert "本篇已抽中的变化条件" in prompt
    assert "- 信息来源：门店导购" in prompt
    assert "- 生活场景：家庭聚会" in prompt
    assert "朋友聊天" not in prompt
    assert "亲子活动" not in prompt
    assert "不要把多个选项写进同一篇" not in prompt


def test_royal_compact_prompt_can_take_task_instruction_from_rule_corpus():
    prompt = _royal_compact_article_prompt(
        {
            "corpus": (
                "任务：写小红书妈妈UGC正向种草笔记。\n\n"
                "写妈妈选奶后的真实使用反馈。"
            ),
        },
        selected_keywords=[],
        output_format="只输出 JSON 对象，字段只能包含 title 和 body。",
    )

    assert prompt.startswith("任务：写小红书妈妈UGC正向种草笔记。")
    assert "写妈妈选奶后的真实使用反馈" in prompt
    assert "UGC生活记录" not in prompt
    assert prompt.count("任务：") == 1


def test_royal_compact_prompt_can_separate_generation_instruction_from_business_rule():
    prompt = _royal_compact_article_prompt(
        {
            "corpus": (
                "## 生文指令\n"
                "写一篇种草文，要求口语化，活人感十足，不分段。"
                "文中必须表述对产品或品牌的推荐。带1-2个emoji\n\n"
                "前段时间选奶粉，妈妈了解到皇家美素佳儿。"
            ),
        },
        selected_keywords=[],
        output_format="只输出 JSON 对象，字段只能包含 title 和 body。",
    )

    assert prompt.startswith("任务：按本篇生文指令写一篇小红书妈妈UGC内容")
    assert "生文指令：\n写一篇种草文" in prompt
    assert "这篇要写的事：\n前段时间选奶粉" in prompt
    assert "是否推荐、是否使用emoji、是否分段，按本篇生文指令执行" in prompt
    assert "不额外补推荐" not in prompt


@pytest.mark.asyncio
async def test_unified_generation_selects_one_sub_keyword_per_category(unified_session_factory):
    async with unified_session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type=SYSTEM_KEYWORD_ASSET_TYPE,
                asset_key=DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
                display_name="默认关键词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "categories": [
                        {
                            "category_code": "comment_generation_requirement",
                            "category_name": "生成要求",
                            "applicable_content_types": ["comment"],
                            "sub_keywords": [
                                {
                                    "keyword_code": "xhs_maternal_comment_requirement",
                                    "keyword_name": "小红书母婴评论生成要求",
                                    "corpus": [
                                        "生成一条小红书母婴社区真实用户评论，口语化，有活人感。只输出评论正文，不要标题、编号、解释。先看业务规则里的参考示例，再换一种自然说法输出。不要复述规则，也不要写成广告口播。"
                                    ],
                                }
                            ],
                        },
                        _category("persona", "人设", ["经验妈妈", "观察妈妈"]),
                        _category("writing_instruction", "生文指令", ["自然表达", "具体问题"]),
                        _category("perturbation_rule", "扰动规则", ["开头扰动", "长短扰动"]),
                        _category("writing_method", "写作手法", ["场景法", "提问法"]),
                    ]
                },
            )
        )
        await session.commit()

        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={
                "rule_type": "business_rule",
                "business_rule": "整体适应",
                "corpus": "像妈妈在评论区聊刚开始喝源悦的观察。",
                "examples": ["我家刚开始也在看源悦，想蹲蹲真实反馈"],
            },
            item_no=2,
            output_fields=["comment"],
        )

    selected = snapshot.input_snapshot["selected_keywords"]
    assert [item["category_code"] for item in selected] == [
        "comment_generation_requirement",
        "persona",
        "comment_writing_instruction",
        "perturbation_rule",
        "writing_method",
    ]
    assert len(selected) == 5
    assert all(len(item["corpus"]) == 1 for item in selected)
    assert snapshot.input_snapshot["content_type"] == "comment"
    prompt = snapshot.input_snapshot["rendered_prompt"]
    assert prompt.startswith("你是一位妈妈，在小红书母婴评论区回复别人关于源悦奶粉的帖子。")
    assert prompt.count("【生成要求】") == 1
    assert prompt.index("注意：") < prompt.index("以下参考示例仅供参考")
    assert prompt.index("以下参考示例仅供参考") < prompt.index("【生成要求】")
    assert "【参考表达】" not in prompt
    assert "【本条要求】" not in prompt
    assert "【业务规则】" not in prompt
    assert "业务规则" not in prompt
    assert "参考表达边界：以下只用于调语气、节奏和生活毛边" not in prompt
    assert "具体信息只按本条要求和参考示例已经给出的范围，不新增事实" not in prompt
    assert "产品事实、成分、正向反馈、产品动作和正文事件只按业务规则里的本篇信息和叙事主线" not in prompt
    assert "不要照搬语料，也不要把语料扩成新的事实、固定结构、现实季节或疾病大环境" not in prompt
    assert "表达扩散语料" not in prompt
    assert "扰动规则 / 长短扰动" not in prompt
    assert "人设 / 经验妈妈" not in prompt
    assert "长短扰动语料" not in prompt
    assert "经验妈妈语料" not in prompt
    assert "整体适应" not in snapshot.input_snapshot["rendered_prompt"]
    assert "经验妈妈" not in snapshot.input_snapshot["rendered_prompt"]
    assert "像妈妈在评论区聊刚开始喝源悦的观察" in snapshot.input_snapshot["rendered_prompt"]
    assert "评论内容不用很丰富，简单表达含义和情绪即可" in snapshot.input_snapshot["rendered_prompt"]
    assert "只输出评论正文，不要标题、编号、解释" in snapshot.input_snapshot["rendered_prompt"]
    assert "标题要像真人随手起的小红书标题" not in snapshot.input_snapshot["rendered_prompt"]
    assert "先看业务规则里的参考示例" not in snapshot.input_snapshot["rendered_prompt"]
    assert "小红书母婴评论生成要求：" not in snapshot.input_snapshot["rendered_prompt"]
    assert "字数按业务规则或系统关键词要求控制" not in snapshot.input_snapshot["rendered_prompt"]
    assert "具体业务信息只跟随【业务规则】" not in snapshot.input_snapshot["rendered_prompt"]
    assert "不像广告、不像客服、不像教程、不像科普公告" not in snapshot.input_snapshot["rendered_prompt"]
    assert "妈妈自己能观察到" not in snapshot.input_snapshot["rendered_prompt"]
    assert "品牌名称只能使用业务规则或参考示例里的品牌" not in snapshot.input_snapshot["rendered_prompt"]
    assert "禁止出现星飞帆、a2、A2、爱他美" not in snapshot.input_snapshot["rendered_prompt"]


def test_model_config_keeps_timeout_and_retry_controls():
    config = _normalize_model_config(
        {
            "provider_code": "aihubmix",
            "model_code": "deepseek-v4-flash",
            "timeout": 12,
            "max_retries": 1,
            "ignored": "x",
        }
    )

    assert config["timeout"] == 12
    assert config["max_retries"] == 1
    assert "ignored" not in config


def test_comment_prompt_can_render_json_string_array_output_contract():
    prompt = _comment_prompt_text(
        {
            "business_rule": "有货-到货分享",
            "corpus": "像妈妈看到 a2 到货后顺手接一句。",
            "examples": ["a2终于到货了", "我也买到了新货了"],
            "output_format_mode": "json_string_array",
            "expansion_count": 20,
        }
    )

    assert "生成 20 条评论。" in prompt
    assert "只输出 JSON 字符串数组，不要标题、编号、解释。" in prompt
    assert "只输出评论正文，不要标题、编号、解释。" not in prompt


def test_a2_comment_prompt_generalizes_competitor_names_in_examples():
    prompt = _comment_prompt_text(
        {
            "asset_key": "a2_sentiment_comment_activity",
            "business_rule": "转奶-泛化竞品",
            "corpus": "转奶前看报告。",
            "examples": ["之前喝爱他美，现在看a2报告。", "也问过雀巢每批检。"],
        }
    )

    assert "不要直接说其他奶粉品牌名" in prompt
    assert "爱他美" not in prompt
    assert "雀巢" not in prompt
    assert "之前的奶粉" in prompt
    assert "其他品牌" in prompt


def test_a2_stock_and_batch_check_prompts_skip_irrelevant_transfer_note():
    stock_prompt = _comment_prompt_text(
        {
            "asset_key": "a2_sentiment_comment_activity",
            "business_rule": "有货-渠道线索",
            "corpus": "像看到a2到货后顺手报个信。",
            "examples": ["a2线上能拍了，我刚看到"],
        }
    )
    batch_prompt = _comment_prompt_text(
        {
            "asset_key": "a2_sentiment_comment_activity",
            "business_rule": "批批检-自己这批报告可查",
            "corpus": "像妈妈扫罐底码看自己这批报告。",
            "examples": ["a2这罐报告能扫出来"],
        }
    )

    assert "转奶对象" not in stock_prompt
    assert "其他奶粉品牌名" not in stock_prompt
    assert "转奶对象" not in batch_prompt
    assert "其他奶粉品牌名" not in batch_prompt


def test_keyword_selection_skips_disabled_categories_before_subkeywords():
    from app.services.unified_content_generation_service import _select_keyword_bundle

    selected = _select_keyword_bundle(
        {
            "categories": [
                {
                    "category_code": "article_speaking_style",
                    "category_name": "帖子说话方式",
                    "enabled": False,
                    "applicable_content_types": ["article"],
                    "sub_keywords": [
                        {
                            "keyword_code": "routine_log",
                            "keyword_name": "松散流水式",
                            "enabled": True,
                            "corpus": ["句子可以像随手写一样松散。"],
                        }
                    ],
                },
                {
                    "category_code": "persona",
                    "category_name": "生活身份机制",
                    "enabled": True,
                    "applicable_content_types": ["article"],
                    "sub_keywords": [
                        {
                            "keyword_code": "wangyue_group_attention_v288",
                            "keyword_name": "群消息牵动注意",
                            "enabled": True,
                            "corpus": ["可借班级群、身边妈妈聊天带来的注意力变化。"],
                        }
                    ],
                },
            ]
        },
        content_type="article",
        item_no=1,
    )

    assert [item["category_code"] for item in selected] == ["persona"]
    assert selected[0]["keyword_code"] == "wangyue_group_attention_v288"


def test_wangyue_slot_coherence_strips_purchase_closure_before_life_action_ending():
    business_rule = {
        "asset_key": "wangyue_v336_protection_entry_cleanup_article_rules",
        "business_rule": "V236-14｜精力状态营养种草｜复购/长期使用｜精力不足",
        "product_name": "旺玥",
        "story_spine": "从外出后或回家路上的精神状态起笔。",
        "product_appearance_mode": "家里一直喝旺玥，这次又补了一罐。",
        "selling_description": "活动后还能有精神玩一会儿，日常营养也配得比较全，这点让我愿意继续买。",
        "selling_kernel": "痛点：精力不足；卖点：营养丰富；卖点描述：活动后还能有精神玩一会儿，日常营养也配得比较全，这点让我愿意继续买。",
    }
    keywords = [
        {
            "category_code": "article_real_ending_texture",
            "category_name": "真人自然结尾",
            "keyword_code": "ending_child_small_reaction_v332",
            "keyword_name": "孩子小反应",
            "corpus": ["真人自然结尾（低权重）：可以停在孩子一个小反应、半句话或动作上。"],
        }
    ]

    patched_rule, patched_keywords, coherence = _apply_article_slot_coherence(
        content_type="article",
        business_rule=business_rule,
        selected_keywords=keywords,
    )

    assert patched_keywords == keywords
    assert patched_rule["selling_description"] == "活动后还能有精神玩一会儿，日常营养也配得比较全。"
    assert "愿意继续买" not in patched_rule["selling_kernel"]
    assert patched_rule["slot_coherence_note"].startswith("已在生文前移除购买决策收口")
    assert coherence["actions"][0]["field"] == "selling_description"


def test_wangyue_slot_coherence_keeps_purchase_closure_without_action_ending():
    business_rule = {
        "asset_key": "wangyue_v336_protection_entry_cleanup_article_rules",
        "business_rule": "V236-14｜精力状态营养种草｜复购/长期使用｜精力不足",
        "product_name": "旺玥",
        "selling_description": "活动后还能有精神玩一会儿，日常营养也配得比较全，这点让我愿意继续买。",
    }
    keywords = [
        {
            "category_code": "article_real_sentence_texture",
            "keyword_code": "sentence_texture_plain_not_expert_v330",
            "corpus": ["真人句子松散度。"],
        }
    ]

    patched_rule, _, coherence = _apply_article_slot_coherence(
        content_type="article",
        business_rule=business_rule,
        selected_keywords=keywords,
    )

    assert patched_rule["selling_description"] == business_rule["selling_description"]
    assert coherence["actions"] == []


def test_business_rule_text_renders_only_supplied_examples_with_usage_boundary():
    text = _business_rule_text(
        {
            "rule_type": "business_rule",
            "business_rule": "奶量补充",
            "topic": "奶量补充",
            "examples": ["抽中示例1", "抽中示例2", "抽中示例3"],
            "example_pool_count": 20,
            "example_sample_count": 3,
        }
    )

    assert "规则内示例边界：以下示例是低权重短句纹理，可以完全不用" in text
    assert "只借语气毛边，不借事实、顺序、因果链或固定句式骨架" in text
    assert "规则内短句纹理（弱参考，可不用）" in text
    assert "抽中示例1" in text
    assert "抽中示例2" in text
    assert "抽中示例3" in text
    assert "example_pool_count" not in text


def test_comment_business_rule_text_uses_direct_requirement_without_internal_labels():
    text = _business_rule_text(
        {
            "rule_type": "business_rule",
            "business_rule": "会员权益-积分老客",
            "corpus": "像妈妈顺手提一句老客积分能换礼，礼品只在奶粉、礼盒、小车车、小自行车范围内。",
            "examples": ["我刚看积分还能换礼，老客这点还挺实在"],
        },
        content_type="comment",
    )

    assert text.startswith("像妈妈顺手提一句老客积分能换礼")
    assert "会员权益-积分老客" not in text
    assert "业务规则" not in text
    assert "业务语料" not in text
    assert "参考示例只学习真人语气和评论形态" in text
    assert "我刚看积分还能换礼，老客这点还挺实在" in text


def test_article_business_rule_text_renders_corpus_directly():
    text = _business_rule_text(
        {
            "rule_type": "business_rule",
            "business_rule": "容易中招，集体生活那杯奶",
            "corpus": "写作规则：像妈妈随口记录孩子上幼儿园后的状态，不说成确定效果。",
            "examples": ["请病假的时间会有，但真的不多。"],
        },
        content_type="article",
    )

    assert text.startswith("写作规则：像妈妈随口记录")
    assert "- 业务规则：" not in text
    assert "- 业务语料：" not in text
    assert "请病假的时间会有，但真的不多。" in text


def test_article_business_rule_text_renders_structured_context_before_corpus():
    text = _business_rule_text(
        {
            "rule_type": "business_rule",
            "business_rule": "V155-01｜保护力关注种草｜使用反馈｜容易中招",
            "product_name": "旺玥",
            "post_type": "使用反馈",
            "ugc_post_type": "使用反馈",
            "painpoint": "容易中招",
            "selling_point": "乳铁蛋白/HMO",
            "positive_evidence": "少请假、户外回来不蔫",
            "selling_point_surface": "像妈妈说看中保护力支持，喝下来这段时间状态稳。",
            "ingredient_surface": "乳铁蛋白、HMO只承接保护力相关观察。",
            "benefit_surface": "少请假、少中招、精神头在线里选一个方向。",
            "expression_mechanism": "从自家状态或一直留下来的理由进入。",
            "product_appearance_mode": "旺玥作为正在喝的保护力选择出现",
            "corpus": "写作规则：先让保护力关注在生活画面里成立。",
        },
        content_type="article",
    )

    assert text.startswith("本篇信息：\n- 产品名：旺玥\n- 痛点：容易中招")
    assert "- 帖子类型：使用反馈" not in text
    assert "- UGC类型：使用反馈" not in text
    assert "- 痛点：容易中招" in text
    assert "- 卖点：乳铁蛋白/HMO" not in text
    assert "正向证据：少请假、户外回来不蔫" in text
    assert "好处表达：少请假、少中招、精神头在线里选一个方向" not in text
    assert "产品叙事推进：" in text
    assert "旺玥作为正在喝的保护力选择出现" in text
    assert "产品进入含义：旺玥作为正在喝的保护力选择出现" in text
    assert "这是语义任务，不是正文句子" in text
    assert "不要硬塞产品名" in text
    assert "- 产品入场关系：" not in text
    assert "种草内核" not in text
    assert "卖点表达参考" not in text
    assert "表达边界：" not in text
    assert "- 表达口吻：像妈妈说看中保护力支持" not in text
    assert "- 表达机制：从自家状态或一直留下来的理由进入" not in text
    assert "成分承接：乳铁蛋白、HMO只承接保护力相关观察" not in text
    assert "只借表达方向，不照抄词句" not in text
    assert "UGC类型=使用反馈" not in text
    assert text.index("本篇信息") < text.index("写作规则")


def test_article_business_rule_text_renders_selling_description_without_old_surfaces():
    text = _business_rule_text(
        {
            "rule_type": "business_rule",
            "business_rule": "V236-01｜卖点描述池",
            "post_type": "家庭清单",
            "painpoint": "营养不足",
            "selling_point": "营养丰富",
            "selling_description": "饭菜有波动时，旺玥的价值落在基础营养更好接住，钙铁锌可以自然提一嘴。",
            "product_appearance_mode": "旺玥作为家里会继续留的一罐儿童奶粉出现",
            "corpus": "写作规则：像妈妈随口记录。",
        },
        content_type="article",
    )

    assert "本篇信息：" in text
    assert "- 痛点：营养不足" in text
    assert "产品叙事推进：" in text
    assert "饭菜有波动时，旺玥的价值落在基础营养更好接住" in text
    assert "产品价值任务：" not in text
    assert "正向证据：" not in text
    assert "成分承接：" not in text
    assert "好处表达：" not in text


def test_wangyue_article_business_rule_text_renders_structured_context_without_corpus():
    text = _business_rule_text(
        {
            "rule_type": "business_rule",
            "asset_key": "wangyue_v305_prompt_corpus_dedupe_article_rules",
            "business_rule": "V236-02｜进阶保护力种草｜选奶复盘｜容易中招",
            "product_name": "旺玥",
            "painpoint": "容易中招",
            "selling_description": "当时挑儿童奶粉时看中旺玥对保护力的支持，也留意了乳铁蛋白和HMO；喝到现在孩子状态挺稳。",
            "product_appearance_mode": "最后选择了旺玥。",
        },
        content_type="article",
    )

    assert "本篇信息：" in text
    assert "- 产品名：旺玥" in text
    assert "- 痛点：容易中招" in text
    assert "产品叙事推进：" in text
    assert "主线内产品信息：最后选择了旺玥；当时挑儿童奶粉时看中旺玥" in text
    assert "产品进入含义：最后选择了旺玥" not in text
    assert "产品价值含义：当时挑儿童奶粉时看中旺玥" not in text
    assert "不要拆成产品进入、成分和反馈的并列清单" in text
    assert "按“最后选择了旺玥”进入" not in text
    assert "产品入场关系：" not in text
    assert "产品价值任务：" not in text
    assert "当时挑儿童奶粉时看中旺玥" in text
    assert "使用方式：这是语义任务，不是正文句子" in text
    assert "## 本篇表达路径" not in text
    assert "表达纹理" not in text


def test_wangyue_article_business_rule_renames_texture_layer():
    text = _business_rule_text(
        {
            "rule_type": "business_rule",
            "business_rule": "V236-01｜卖点描述池",
            "post_type": "家庭清单",
            "painpoint": "营养不足",
            "selling_point": "营养丰富",
            "selling_description": "饭菜有波动时，旺玥的价值落在基础营养更好接住。",
            "product_appearance_mode": "旺玥作为家里会继续留的一罐儿童奶粉出现",
            "corpus": "\n".join(
                [
                    "## 表达纹理",
                    "本段只给发帖节奏、语气松散度和生活毛边；本篇的痛点、卖点和产品价值以本篇信息和卖点描述为准。",
                    "- 规则内示例边界：以下示例是低权重短句纹理，可以完全不用；只借语气毛边，不借事实、顺序、因果链或固定句式骨架。",
                    "- 规则内短句纹理（弱参考，可不用）：",
                    "  - 家里常备那几样里，旺玥算是会继续留的。",
                ]
            ),
        },
        content_type="article",
    )

    assert "## 本篇表达路径" in text
    assert "只借本篇表达路径里的行文节奏" in text
    assert "产品逻辑按本篇信息和产品叙事推进" in text
    assert "短句可不用；不借事实、顺序和固定句式" in text
    assert "本篇短句口气（可不用）" in text
    assert "## 表达纹理" not in text
    assert "低权重短句纹理" not in text
    assert "本段只给发帖节奏、语气松散度和生活毛边" not in text


def test_wangyue_article_examples_render_as_expression_reference():
    text = _business_rule_text(
        {
            "rule_type": "business_rule",
            "business_rule": "V236-01｜卖点描述池",
            "post_type": "家庭清单",
            "painpoint": "营养不足",
            "selling_point": "营养丰富",
            "product_appearance_mode": "旺玥作为家里会继续留的一罐儿童奶粉出现",
            "corpus": "写作规则：像妈妈随口记录。",
            "examples": ["家里这罐旺玥算是会继续留的。"],
        },
        content_type="article",
    )

    assert "表达参考：以下内容可以不用；只借说话方式，不照搬事实和句式。" in text
    assert "参考短句：" in text
    assert "家里这罐旺玥算是会继续留的" in text
    assert "规则内示例边界" not in text
    assert "短句纹理" not in text


def test_wangyue_article_long_examples_render_as_reference_content():
    text = _business_rule_text(
        {
            "rule_type": "business_rule",
            "business_rule": "V243｜full ref probe",
            "post_type": "使用反馈",
            "painpoint": "容易中招",
            "selling_point": "保护力",
            "product_appearance_mode": "旺玥作为正在喝的保护力选择出现",
            "corpus": "写作规则：像妈妈随口记录。",
            "examples": ["幼儿园班级群里一开始接龙请假，我就跟着紧张。每天送孩子上学，看她和小伙伴们贴贴抱抱，我心里就七上八下的。"],
        },
        content_type="article",
    )

    assert "表达参考：以下内容可以不用；只借说话方式，不照搬事实和句式。" in text
    assert "参考内容：" in text
    assert "参考短句：" not in text
    assert "规则内示例边界" not in text


def test_wangyue_article_expression_reference_fields_replace_examples():
    text = _business_rule_text(
        {
            "rule_type": "business_rule",
            "business_rule": "V244｜hybrid expression probe",
            "post_type": "使用反馈",
            "painpoint": "容易中招",
            "selling_point": "保护力",
            "product_appearance_mode": "旺玥作为正在喝的保护力选择出现",
            "corpus": "写作规则：像妈妈随口记录。",
            "expression_reference_paths": [
                "先从妈妈当天注意到的小状态写起，中间自然提到旺玥，再落一个具体正向观察。"
            ],
            "expression_reference_phrases": ["今天就顺手记一下", "这段时间看下来还挺稳"],
            "examples": ["旧短句不应该再渲染"],
        },
        content_type="article",
    )

    assert "本篇节奏（可不用；" in text
    assert "本篇短句口气（可不用；" in text
    assert "本篇节奏边界" not in text
    assert "今天就顺手记一下" in text
    assert "旧短句不应该再渲染" not in text
    assert "参考短句：" not in text
    assert "参考内容：" not in text


def test_article_business_rule_text_renders_real_user_pool_separately():
    text = _business_rule_text(
        {
            "rule_type": "business_rule",
            "business_rule": "营养不足/成长发育需求",
            "corpus": "写作规则：围绕孩子成长阶段营养补充来写。",
            "examples": ["规则内示例"],
            "real_user_examples": [
                {
                    "source_type": "note",
                    "title": "挑奶粉挑到头大",
                    "text": "对比几款奶粉后还是看营养和孩子愿不愿意喝。",
                    "tags": ["选奶", "营养"],
                    "risk_tags": [],
                },
                {
                    "source_type": "comment",
                    "title": "挑奶粉挑到头大",
                    "text": "不是有点贵，是太贵了。",
                    "tags": ["价格"],
                    "risk_tags": ["评论口吻"],
                },
            ],
        },
        content_type="article",
    )

    assert "全量真人原句池使用边界" in text
    assert "本次抽到的帖子原句纹理" in text
    assert "本次抽到的评论短句纹理" in text
    assert "评论原句只能提供口气和真实短句感，不能写成评论区回复" in text
    assert "规则内示例" in text
    assert "对比几款奶粉后还是看营养" in text
    assert "不是有点贵，是太贵了" in text


def test_article_business_rule_text_renders_layered_real_user_pool_sections():
    text = _business_rule_text(
        {
            "rule_type": "business_rule",
            "business_rule": "容易中招，日常保护力观察",
            "corpus": "写作规则：围绕孩子接触人多后妈妈关注保护力来写。",
            "real_user_examples": [
                {
                    "source_type": "note",
                    "example_layer": "route",
                    "prompt_text": "上幼儿园后接触人多，选旺玥就是看中日常保护力。",
                    "text": "上幼儿园后接触人多，选旺玥就是看中日常保护力。",
                    "tags": ["幼儿园", "保护力"],
                    "risk_tags": [],
                },
                {
                    "source_type": "note",
                    "example_layer": "texture",
                    "prompt_text": "除了贵点没毛病。",
                    "text": "除了贵点没毛病。",
                    "tags": ["价格"],
                    "risk_tags": [],
                },
                {
                    "source_type": "note",
                    "example_layer": "detail",
                    "prompt_text": "放学回来先看餐盘，饭量和以前比能看出点变化。",
                    "text": "放学回来先看餐盘，饭量和以前比能看出点变化。",
                    "tags": ["幼儿园", "挑食"],
                    "risk_tags": [],
                },
                {
                    "source_type": "note",
                    "example_layer": "ending",
                    "prompt_text": "不吹不黑，先喝着记录一下。",
                    "text": "不吹不黑，先喝着记录一下。",
                    "tags": ["喝奶接受度"],
                    "risk_tags": [],
                },
            ],
        },
        content_type="article",
    )

    assert "真人素材使用边界" in text
    assert "业务规则优先" in text
    assert "低权重参考，可以完全不用" in text
    assert "内容入口只借切入启发" in text
    assert "低权重内容入口（可不用，只借切入方式）" in text
    assert "可借生活细节颗粒" in text
    assert "可借说话口气" in text
    assert "可借开头/收尾" in text
    assert "不要照搬事实、顺序、因果链" in text
    assert "上幼儿园后接触人多" in text
    assert "放学回来先看餐盘" in text
    assert "除了贵点没毛病" in text
    assert "不吹不黑，先喝着记录一下" in text
    assert "本次抽到的帖子原句纹理" not in text


def test_article_business_rule_text_filters_examples_by_content_path_control_terms():
    text = _business_rule_text(
        {
            "rule_type": "business_rule",
            "business_rule": "精力不足，日常状态观察",
            "corpus": "写作规则：像普通妈妈随手记录孩子状态。",
            "content_path_control": {
                "enabled": True,
                "exclude_example_terms": ["喝", "冲", "杯子"],
            },
            "real_user_examples": [
                {
                    "source_type": "note",
                    "example_layer": "route",
                    "prompt_text": "放学回来还闲不住，旺玥就是家里日常喝的那罐。",
                    "text": "放学回来还闲不住，旺玥就是家里日常喝的那罐。",
                    "tags": ["营养"],
                    "risk_tags": [],
                },
                {
                    "source_type": "note",
                    "example_layer": "route",
                    "prompt_text": "接娃路上聊到孩子状态，我顺手记一下旺玥。",
                    "text": "接娃路上聊到孩子状态，我顺手记一下旺玥。",
                    "tags": ["幼儿园"],
                    "risk_tags": [],
                },
            ],
            "examples": ["他喝得挺顺。", "接娃路上聊了两句。"],
        },
        content_type="article",
    )

    assert "接娃路上聊到孩子状态" in text
    assert "接娃路上聊了两句" in text
    assert "日常喝的那罐" not in text
    assert "他喝得挺顺" not in text


def test_article_business_rule_text_renders_title_shape_and_opening_sections():
    text = _business_rule_text(
        {
            "rule_type": "business_rule",
            "business_rule": "容易中招，日常保护力观察",
            "corpus": "写作规则：围绕孩子接触人多后妈妈关注保护力来写。",
            "real_user_examples": [
                {
                    "source_type": "note",
                    "example_layer": "title_shape",
                    "prompt_text": "当妈后才懂",
                    "text": "当妈后才懂",
                    "tags": ["选奶"],
                    "risk_tags": [],
                },
                {
                    "source_type": "note",
                    "example_layer": "opening_texture",
                    "prompt_text": "说实话，选奶这件事真的会越看越纠结。",
                    "text": "说实话，选奶这件事真的会越看越纠结。",
                    "tags": ["选奶"],
                    "risk_tags": [],
                },
            ],
        },
        content_type="article",
    )

    assert "可借标题形态" in text
    assert "可借开头/收尾" in text
    assert "不借产品词、年龄、功效承诺或测评栏目感" in text
    assert "当妈后才懂" in text
    assert "说实话，选奶这件事真的会越看越纠结" in text


def test_article_business_rule_text_renders_real_title_references():
    text = _business_rule_text(
        {
            "corpus": "写作规则：围绕孩子日常喝旺玥来写。",
            "title_reference_examples": [
                "皇家美素佳儿旺玥",
                "儿童奶粉＋皇家旺玥，两罐喝1年的真实反馈",
                "马上3周岁，纠结喝什么奶粉",
            ],
        },
        content_type="article",
    )

    assert "真人标题参考" in text
    assert "真实标题样本" in text
    assert "皇家美素佳儿旺玥" in text
    assert "儿童奶粉＋皇家旺玥，两罐喝1年的真实反馈" in text
    assert "只借标题形式" in text
    assert "不得与任一真实标题样本完全一致" in text
    assert "旺玥真实体验分享" in text


def test_generation_requirements_render_mouth_phrase_budget_as_light_control():
    from app.services.unified_content_generation_service import _generation_requirements

    text = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "mouth_phrase_budget": {
                "enabled": True,
                "allowed_terms": ["最近"],
                "avoid_terms": ["省心", "踏实", "不知道是不是心理作用"],
            }
        },
        [],
    )

    assert "批量口癖控制" in text
    assert "真人表达，不是禁词" in text
    assert "本篇口癖预算优先级高于示例和说话方式" in text
    assert "最近" not in text
    assert "本篇不要主动套用批量高频口头禅" in text
    assert "省心" not in text
    assert "踏实" not in text
    assert "不知道是不是心理作用" not in text
    assert "只输出 JSON 对象" not in text
    assert "不要写“标题：”“正文：”“### 标题”“### 正文”" not in text


def test_generation_requirements_render_content_path_control_before_title_rule():
    from app.services.unified_content_generation_service import _generation_requirements

    text = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "content_path_control": {
                "enabled": True,
                "instruction": "先确定生活入口，再决定产品只作为背景还是轻带一句。",
                "avoid_path": "不要把正文写成选奶、喝奶接受、状态证明、妈妈收口四段。",
                "prefer_path": "优先写接娃、收拾书包、饭桌旁聊天这类生活片段。",
                "avoid_components": ["喝奶接受度", "导购选择过程"],
                "max_product_components": 1,
            }
        },
        [],
    )

    assert "内容路径控制" in text
    assert "先确定生活入口" in text
    assert "选奶、喝奶接受、状态证明、妈妈收口四段" in text
    assert "喝奶接受度、导购选择过程" in text
    assert "只输出 JSON 对象" not in text
    assert "最多展开 1 个产品相关环节" in text
    assert text.index("内容路径控制") < text.index("标题硬边界")
    assert "最多不超过20字，emoji 按 2 字计" in text
    assert "不要硬截读不通的正文半句" in text
    assert text.count("标题硬边界") == 1
    assert "从正文里挑一个自然短句" not in text


def test_generation_requirements_render_product_appearance_permission_before_content_path():
    from app.services.unified_content_generation_service import _generation_requirements, _keyword_corpus_text

    business_rule = {
        "post_type": "补货/家务清单",
        "product_appearance_mode": "产品是家里库存物件",
        "title_shape_mode": "清单/库存标签",
        "scene_motive_bucket": "快递到货拆箱",
        "content_path_control": {
            "enabled": True,
            "instruction": "先写生活入口，再轻带产品。",
        },
    }
    text = _generation_requirements(
        "article",
        ["title", "body"],
        business_rule,
        [],
    )

    assert "产品出现许可" in text
    assert "帖子类型=补货/家务清单" in text
    assert "产品出现方式=产品是家里库存物件" in text
    assert "不要超出业务规则给定的产品内容" in text
    assert "不要写成选奶、换奶、看中产品、推荐购买" in text
    assert "不是种草/不是跟风" in text
    assert text.index("产品出现许可") < text.index("内容路径控制")
    assert text.index("内容路径控制") < text.index("正文取景")
    assert text.index("正文取景") < text.index("标题形态")
    assert "从“快递到货拆箱”找一个生活画面进入" in text
    assert "写门口快递、拆纸箱、核对快递、包装袋" in text
    assert "不写翻柜子、快见底或购物清单" in text
    assert "除非本篇入口明确是库存盘点，否则不要默认写整理柜子、翻柜子、快见底、购物清单、纸巾洗衣液袜子这一套" not in text
    assert "标题形态和松散感放在表达扩散语料里低权重参考" in text
    assert "写成家务清单或补东西语境" not in text
    assert "补货”“又要买了”“月底清单" not in text
    assert "不要让标题形成产品到孩子状态、睡眠、成长、保护力或妈妈安心的因果" not in text
    assert text.index("产品出现许可") < text.index("标题规则")
    assert text.count("标题规则") == 1
    assert "标题要像真人随手起的小红书标题" not in text
    keyword_text = _keyword_corpus_text([], content_type="article", output_fields=["title", "body"], business_rule=business_rule)
    assert "低权重表达扰动 / 主链路不变" in keyword_text
    assert "标题形态可写成家务清单或补东西语境" in keyword_text
    assert "不要默认回到整理柜子、翻柜子、快见底、购物清单这一套" in keyword_text


def test_generation_requirements_do_not_render_wangyue_copyable_scene_bucket():
    from app.services.unified_content_generation_service import _generation_requirements

    text = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "asset_key": "wangyue_v3_core_storyline_article_rules",
            "post_type": "使用反馈",
            "painpoint": "容易中招",
            "selling_point": "进阶保护力",
            "scene_motive_bucket": "集体活动后自家观察",
            "corpus": "旺玥",
        },
        [],
    )

    assert "从“集体活动后自家观察”找一个生活画面进入" not in text
    assert "接触多后的自家状态观察" not in text
    assert "正文入口：先从一个普通生活现场起笔" not in text
    assert "生活入口只负责让帖子像真人生活，不负责证明卖点" not in text
    assert "入口可以参考系统关键词，也可以自然发散" not in text
    assert "不照搬内部槽位词" not in text
    assert "不要照搬这个观察来源标签" not in text
    assert "集体活动" not in text
    assert "活动后" not in text
    assert "标题硬边界" in text

    imported_text = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "asset_key": "wangyue_v3_core_storyline_article_rules",
            "post_type": "使用反馈",
            "painpoint": "容易中招",
            "selling_point": "进阶保护力",
            "scene_motive_bucket": "接触多后的自家观察",
            "corpus": "旺玥",
        },
        [],
    )

    assert "从“接触多后的自家观察”找一个生活画面进入" not in imported_text
    assert "接触多后的自家状态观察" not in imported_text
    assert "正文入口：先从一个普通生活现场起笔" not in imported_text
    assert "标题硬边界" in imported_text


def test_generation_requirements_allow_selection_review_product_basis():
    from app.services.unified_content_generation_service import _generation_requirements

    text = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "post_type": "选奶/儿童奶粉选择复盘",
            "product_appearance_mode": "旺玥作为选择依据出现",
            "title_shape_mode": "纠结/看成分/简单记录",
        },
        [],
    )

    assert "产品出现边界" in text
    assert "正文要自然出现本篇指定产品名" in text
    assert "正文必须明确写出旺玥" not in text
    assert "另起一套产品关系" not in text
    assert "具体产品内容只按业务规则给定方向出现" not in text
    assert "只能写成选择时的具体依据或后来没换的原因" not in text
    assert "不要写成喝后确定改善孩子状态、保护力、注意力、身高或成长结果" not in text
    assert "不要写成选奶、换奶、看中卖点、推荐购买" not in text


def test_generation_requirements_render_matrix_post_type_product_permissions():
    from app.services.unified_content_generation_service import _generation_requirements

    light_review = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "post_type": "轻测评/配方关注",
            "product_appearance_mode": "旺玥作为配方观察对象出现",
        },
        [],
    )
    assert "产品出现边界" in light_review
    assert "正文要自然出现本篇指定产品名" in light_review
    assert "正文必须明确写出旺玥" not in light_review
    assert "另起一套产品关系" not in light_review
    assert "被轻轻观察的配方/选择对象" not in light_review
    assert "可以从被问起选择产品的原因、对产品成分的印象、简单对比或家里正在喝的情况进入" not in light_review
    assert "必须有一个具体看配方" not in light_review
    assert "不必每次安排看配方动作" not in light_review
    assert "不能只写“先放进选择里”“先顾住日常营养”这种空结论" not in light_review
    assert "产品信息只能贴着这个入口顺手出现" not in light_review
    assert "不要把它翻译成妈妈的选品总结" not in light_review
    assert "在轻测评/配方关注这类低解释义务内容里，不要写成品牌讲解稿、参数清单、测评模板、攻略答案或满分推荐" not in light_review
    assert "记住成分点" not in light_review
    assert "多看一眼" not in light_review
    problem_solution = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "post_type": "问题解决/放学后状态",
            "product_appearance_mode": "旺玥作为其中一个调整方式出现",
        },
        [],
    )
    assert "产品可以回答一个小处理问题，比如日常营养补充这项怎么安排" not in problem_solution
    assert "但不能成为整个生活困扰的答案" not in problem_solution
    assert "具体产品内容只按业务规则给定方向出现" not in problem_solution
    assert "不要写成产品解决挑食、精力、保护力、注意力或成长问题" not in problem_solution
    assert "不要用“不能光靠奶粉/光靠这个不行/每家不一样/还在观察/不指望一罐奶粉/先喝着观察/兜底/补漏”式防守句" not in problem_solution
    seeded_problem_solution = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "post_type": "强种草问题解决/吃饭不稳",
            "ugc_post_type": "问题种草型",
            "product_appearance_mode": "旺玥作为日常营养补充的答案出现",
        },
        [],
    )
    assert "产品可以成为小问题的答案" not in seeded_problem_solution
    assert "怎么安排日常营养补充" not in seeded_problem_solution
    assert "但不能成为整个生活困扰的万能答案" not in seeded_problem_solution
    assert "具体产品内容只按业务规则给定方向出现" not in seeded_problem_solution
    assert "不要写成旺玥解决挑食、精力不足、容易中招、注意力不集中或成长发育问题" not in seeded_problem_solution
    assert "不完美感写在生活问题仍有反复" not in seeded_problem_solution
    feedback = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "post_type": "使用反馈/继续观察",
            "product_appearance_mode": "旺玥作为观察中的当前安排出现",
        },
        [],
    )
    assert "产品出现边界" in feedback
    assert "当前还在保留的安排" not in feedback
    assert "允许正面反馈" not in feedback
    assert "不能把孩子状态变化归因给产品" not in feedback
    family_list = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "post_type": "家庭清单/阶段用品",
            "product_appearance_mode": "旺玥作为学龄前清单项出现",
        },
        [],
    )
    assert "产品出现边界" in family_list
    assert "和其他家庭安排或清单项并列" not in family_list
    assert "不能站成正文C位" not in family_list
    assert "不要写成一天作息表、教程、打卡清单或带话题标签" not in family_list
    assert "标题也不要直接写“清单/攻略/几件事”" not in family_list


def test_generation_requirements_blocks_unverified_temporal_context():
    from app.services.unified_content_generation_service import _generation_requirements

    text = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "post_type": "使用反馈/阶段观察",
            "product_appearance_mode": "旺玥作为当前安排出现",
            "scene_motive_bucket": "入园后接触人多",
        },
        [],
    )

    assert "时间边界：可以有真实生活时间口吻" in text
    assert "不要依赖当前季节、天气、公共疾病或季节性活动节点成立" in text
    assert "换季、流感、感冒季" not in text
    assert "最近、现在、昨天、前两天、刚拆快递、刚补货、家里还剩半罐" not in text


def test_generation_requirements_render_product_action_surface_for_usage_record():
    from app.services.unified_content_generation_service import _generation_requirements

    text = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "post_type": "使用记录",
            "product_appearance_mode": "产品是日常动作的一部分",
            "product_action_surface": "物件在场",
            "scene_motive_bucket": "早上赶时间",
        },
        [],
    )

    assert "产品动作表面：本篇按“物件在场”写" in text
    assert "不要写孩子端起来喝、喝两口、喝完、主动喝" in text
    assert text.index("产品出现许可") < text.index("产品动作表面")
    assert text.index("产品动作表面") < text.index("正文取景")


def test_generation_requirements_render_ugc_strategy_before_action_surface():
    from app.services.unified_content_generation_service import _generation_requirements, _keyword_corpus_text

    business_rule = {
        "asset_key": "wangyue_painpoint_selling_posttype_matrix_v33_20260624",
        "post_type": "使用记录",
        "product_appearance_mode": "产品是日常动作的一部分",
        "ugc_post_type": "日常使用记录型",
        "painpoint": "容易中招",
        "selling_point": "保护力营养关注",
        "positive_evidence": "少请假、户外回来不蔫",
        "life_trigger": "早上赶时间",
        "product_role": "低浓度在场物件",
        "product_density": "低",
        "imperfection": "当天还是一地乱",
        "structure_slot": "先反馈后补产品",
        "product_action_surface": "物件在场",
        "scene_motive_bucket": "早上赶时间",
        "scene_constraint": "围绕身边反馈或集体活动后的自家状态观察；生活入口只交代观察来源",
        "product_position_mode": "中段桌面物件里出现",
        "ending_mode": "没总结",
    }
    text = _generation_requirements(
        "article",
        ["title", "body"],
        business_rule,
        [],
    )

    assert "字段使用" not in text
    assert "产品表达边界" in text
    assert "产品事实、成分和正向反馈只按业务规则里的产品信息" in text
    assert "表达扩散语料只调语气和节奏" in text
    assert "不新增痛点、卖点、成分、效果证明或产品动作" not in text
    assert "正文入口：先从一个普通生活现场起笔" not in text
    assert "生活入口只负责让帖子像真人生活，不负责证明卖点" not in text
    assert "具体产品逻辑只按业务规则里的本篇信息写" not in text
    assert "痛点 -> 卖点 -> 对应成分" not in text
    assert "进阶保护力才可写乳铁蛋白/免疫球蛋白/HMO" not in text
    assert "痛点、卖点、成分和正向证据只按业务规则里的本篇信息写" not in text
    assert "UGC类型策略" not in text
    assert "UGC类型=日常使用记录型" not in text
    assert "核心痛点=容易中招" not in text
    assert "卖点方向=保护力营养关注" not in text
    assert "主正向证据=少请假、户外回来不蔫" not in text
    assert "帖子类型决定发帖原因和产品参与深度" not in text
    assert "不要从通用写作要求里另补一套产品逻辑" not in text
    assert "产品表达不写成参数清单或夸张承诺" not in text
    assert "正文只展开一个产品关系" not in text
    assert "旺玥价值要写到位" in text
    assert "不用防守式弱化" in text
    assert "不要自行新增业务规则外的选择理由或效果证明" in text
    assert "结构关系：生活观察在前，产品在后作为背景或原因之一" not in text
    assert "结构槽位：先反馈后补产品" not in text
    assert "结构槽只规定信息顺序和关系，不提供可复制素材" not in text
    assert "场景约束：围绕身边反馈或集体活动后的自家状态观察" not in text
    assert "不要列举包、路上、随身、容器携带或可复制物件清单" not in text
    assert "产品出现位置：本篇按“中段桌面物件里出现”处理" in text
    assert "先写人和场景，中段作为桌面/台面/餐边柜旁物件出现" in text
    assert "末句收法" not in text
    assert "允许没漂亮结尾，停在具体动作或反馈上" not in text
    assert "收尾方式：本篇按“没总结”结束" not in text
    assert "产品出现许可" not in text
    assert "产品出现边界" in text
    assert text.index("产品出现边界") < text.index("产品表达边界")
    assert text.index("产品表达边界") < text.index("产品出现位置")
    assert text.index("产品出现位置") < text.index("产品动作表面")
    keyword_text = _keyword_corpus_text([], content_type="article", output_fields=["title", "body"], business_rule=business_rule)
    assert "结构关系可生活观察在前、产品在后作为背景或原因之一" in keyword_text
    assert "正文入口按本篇痛点和发帖动机自然起笔" in keyword_text
    assert "正文入口可从" not in keyword_text
    assert "生活现场余味" not in keyword_text
    assert "收尾方式" not in keyword_text
    assert "不要为了收尾机械追加省心" not in keyword_text


def test_wangyue_end_reply_boundary_guides_to_fact_action_or_observation():
    from app.services.unified_content_generation_service import _keyword_corpus_text

    keyword_text = _keyword_corpus_text(
        [],
        content_type="article",
        output_fields=["title", "body"],
        business_rule={
            "asset_key": "wangyue_v254_expression_phrase_source_cleanup_article_rules",
            "product_name": "旺玥",
            "post_type": "对比选择",
            "painpoint": "注意力不集中",
            "product_appearance_mode": "对比后选择了旺玥。",
            "ending_mode": "END_REPLY_BOUNDARY",
            "corpus": "旺玥",
        },
    )

    assert "收尾落在正文里的一个事实补充、生活动作或具体观察上" not in keyword_text
    assert "自家情况回应" not in keyword_text
    assert "收尾保留问答或聊天现场的余味" not in keyword_text


def test_generation_requirements_render_wangyue_internal_ending_mode_only():
    from app.services.unified_content_generation_service import _generation_requirements

    text = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "asset_key": "wangyue_v342_single_flow_cleanup_article_rules",
            "product_name": "旺玥",
            "ending_mode": "END_FEEDBACK_STOP",
        },
        [],
    )
    legacy_text = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "asset_key": "wangyue_painpoint_selling_posttype_matrix_v33_20260624",
            "ending_mode": "没总结",
        },
        [],
    )

    assert "末句收法：最后一句停在本篇已有具体状态或正向反馈上" in text
    assert "不再补省心、选对、没选错、推荐或“最好的证明”式总结" in text
    assert "末句收法" not in legacy_text


def test_generation_requirements_render_product_chain_budget_for_wangyue_problem_solution():
    from app.services.unified_content_generation_service import _generation_requirements

    text = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "asset_key": "wangyue_painpoint_selling_posttype_matrix_v33_20260624",
            "post_type": "问题解决/放学后状态",
            "product_appearance_mode": "旺玥作为其中一个调整方式出现",
            "ugc_post_type": "问题解决型",
            "painpoint": "精力不足",
            "selling_point": "日常营养补充",
        },
        [],
    )

    assert "产品表达边界" in text
    assert "旺玥价值要写到位" in text
    assert "正文厚度" not in text
    assert "发帖原因和生活现场成立" not in text
    assert "生活余波不负责证明卖点" not in text
    assert "产品链路预算" not in text
    assert "批量分布提醒" not in text
    assert "不是单篇削弱种草力的硬规则" not in text
    assert "不要自行新增业务规则外的选择理由或效果证明" in text
    assert "不要自动扩成完整广告闭环" not in text
    assert "生活困扰→选购/对比/看成分→价格/预算→孩子接受/好喝→继续喝/复购→妈妈安心/省心" not in text
    assert "先按帖子类型判断产品链路强度" not in text
    assert "生活问题处理记录" not in text
    assert "产品可以回答一个小处理问题" not in text
    assert "但不能成为整个生活困扰的答案" not in text
    assert "不要用“不能光靠奶粉/光靠这个不行/每家孩子不一样/还在观察/不指望一罐奶粉/先喝着观察/兜底/补漏”这类防守句" not in text
    assert "不完美感写在生活问题仍有反复，不要通过否定产品价值来证明真实" not in text
    assert "具体产品内容只按业务规则给定方向出现" not in text
    assert "涉及精力不足时，产品只能回答日常营养支持" not in text
    assert "不要从困扰接到旺玥后，再补孩子接受度、继续喝/没换或妈妈松口气" not in text
    assert "不要用“每家孩子不一样/不能光靠奶粉/还在观察”来制造真实感" not in text
    assert "标题按生活问题记录型判断" not in text


def test_generation_requirements_render_product_chain_budget_for_seeded_problem_solution():
    from app.services.unified_content_generation_service import _generation_requirements

    text = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "asset_key": "wangyue_painpoint_selling_posttype_matrix_v33_20260624",
            "post_type": "强种草问题解决/吃饭不稳",
            "product_appearance_mode": "旺玥作为日常营养补充的答案出现",
            "ugc_post_type": "问题种草型",
            "painpoint": "营养不足",
            "selling_point": "日常营养补充",
        },
        [],
    )

    assert "强种草/问题解决复盘" not in text
    assert "产品可以成为小问题的答案" not in text
    assert "怎么选儿童奶粉、怎么安排日常营养补充、为什么把旺玥留下来" not in text
    assert "但不能成为整个生活困扰的万能答案" not in text
    assert "具体产品内容只按业务规则给定方向出现" not in text
    assert "不要写成旺玥解决挑食、精力不足、容易中招、注意力不集中或成长发育问题" not in text
    assert "不要写成“不能光靠奶粉/光靠这个不行/不指望一罐奶粉/还在观察/先喝着观察/兜底/补漏”" not in text
    assert "标题按问题种草/复盘型判断" not in text


def test_generation_requirements_render_product_chain_budget_for_wangyue_repurchase():
    from app.services.unified_content_generation_service import _generation_requirements

    text = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "asset_key": "wangyue_painpoint_selling_posttype_matrix_v33_20260624",
            "post_type": "复购/长期使用",
            "product_appearance_mode": "旺玥作为长期保留、补货对象出现",
            "ugc_post_type": "复购/囤货型",
            "product_role": "补货对象",
        },
        [],
    )

    assert "产品表达边界" in text
    assert "旺玥价值要写到位" in text
    assert "产品链路预算" not in text
    assert "复购/长期使用" not in text
    assert "允许写复购动作、消耗、口感/接受度和一个留下来的理由" not in text
    assert "不要同篇再补完整选择过程、孩子接受度、状态变化和妈妈安心收口" not in text
    assert "强种草、选奶复盘、复购或长期使用可以写得更完整" not in text
    assert "标题按复购型判断" not in text


def test_generation_requirements_product_chain_budget_uses_type_specific_selection_scale():
    from app.services.unified_content_generation_service import _generation_requirements

    text = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "asset_key": "wangyue_painpoint_selling_posttype_matrix_v33_20260624",
            "post_type": "对比选择/选奶标准",
            "product_appearance_mode": "旺玥作为选择依据出现",
            "ugc_post_type": "对比选择型",
            "painpoint": "注意力不集中",
            "selling_point": "眼脑营养关注",
        },
        [],
    )

    assert "选择/对比复盘" not in text
    assert "产品可以作为妈妈选儿童奶粉时看过的依据出现" not in text
    assert "具体产品内容只按业务规则给定方向出现" not in text
    assert "旺玥这里不要写价格、预算、贵不贵或值不值" not in text
    assert "产品出现边界" in text
    assert "另起一套产品关系" not in text
    assert "选奶链可以成立，使用反馈链不要同时成立" not in text
    assert "标题按选择/对比型判断" not in text
    assert "可以出现选奶、配方、4段、儿童奶粉这类主题词" not in text


def test_generation_requirements_product_chain_budget_prioritizes_family_list_over_restock_word():
    from app.services.unified_content_generation_service import _generation_requirements

    text = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "asset_key": "wangyue_painpoint_selling_posttype_matrix_v33_20260624",
            "post_type": "家庭清单/隐形家务补货",
            "product_appearance_mode": "旺玥作为学龄前清单项出现",
            "ugc_post_type": "家庭清单型",
            "painpoint": "成长发育需求",
            "selling_point": "3-6岁4段阶段营养",
        },
        [],
    )

    assert "家庭清单/隐形家务" not in text
    assert "产品出现边界" in text
    assert "正文要自然出现本篇指定产品名" in text
    assert "正文必须明确写出旺玥" not in text
    assert "即使标题或场景里有补货，也按清单型处理" not in text
    assert "不要升级成复购复盘" not in text
    assert "本篇是复购/长期使用" not in text
    assert "标题按清单型判断" not in text


def test_generation_requirements_product_chain_budget_is_scoped_to_wangyue_articles():
    from app.services.unified_content_generation_service import _generation_requirements

    unrelated_article = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "asset_key": "generic_article_rules",
            "post_type": "问题解决/普通分享",
            "ugc_post_type": "问题解决型",
            "painpoint": "出门忘东西",
        },
        [],
    )
    comment = _generation_requirements(
        "comment",
        ["comment"],
        {
            "asset_key": "wangyue_painpoint_selling_posttype_matrix_v33_20260624",
            "ugc_post_type": "问题解决型",
            "painpoint": "精力不足",
        },
        [],
    )

    assert "产品链路预算" not in unrelated_article
    assert "产品链路预算" not in comment


def test_generation_requirements_demotes_front_loaded_product_examples_for_late_position():
    from app.services.unified_content_generation_service import _generation_requirements

    text = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "post_type": "求问/轻复盘",
            "product_appearance_mode": "产品是明确讨论对象但不装日记",
            "ugc_post_type": "求建议后的反馈型",
            "product_position_mode": "先抛问题后出现",
        },
        [],
    )

    assert "产品出现位置：本篇按“先抛问题后出现”处理" in text
    assert "不要一上来就说产品" in text
    assert "只能当背景信息，不要照搬成正文第一句" in text
    assert "正文第一句不要出现产品名或品牌名" in text
    assert "旺玥" not in text


def test_generation_requirements_skips_disabled_product_position():
    from app.services.unified_content_generation_service import _generation_requirements

    text = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "post_type": "使用反馈",
            "product_appearance_mode": "旺玥作为正在喝的保护力选择出现，只保留一个自家状态",
            "product_position_mode": "PRODUCT_POSITION_DISABLED",
        },
        [],
    )

    assert "产品出现位置" not in text
    assert "PRODUCT_POSITION_DISABLED" not in text


def test_generation_requirements_render_light_recap_anti_question_hint():
    from app.services.unified_content_generation_service import _generation_requirements

    text = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "post_type": "求问/轻复盘",
            "product_appearance_mode": "产品是明确讨论对象但不装日记",
            "ugc_post_type": "轻复盘型",
            "life_trigger": "喝了一阵后回看",
            "product_role": "观察对象/反馈对象",
            "product_density": "中",
            "imperfection": "我也还在摸索",
        },
        [],
    )

    assert "字段使用" in text
    assert "UGC类型=轻复盘型" not in text
    assert "不要在标题或正文里直接写“轻复盘”" in text
    assert "不要写成测评模板、推荐购买、求建议帖或购买替换决策" in text
    assert "想问大家/求经验/怎么判断/怎么安排/继续囤/再看别的" not in text


def test_generation_requirements_title_shape_uses_evidence_backed_stage_examples():
    from app.services.unified_content_generation_service import _generation_requirements, _keyword_corpus_text

    business_rule = {
        "post_type": "求问/轻复盘",
        "product_appearance_mode": "产品是明确讨论对象但不装日记",
        "title_shape_mode": "使用阶段短标题",
    }
    text = _generation_requirements(
        "article",
        ["title", "body"],
        business_rule,
        [],
    )

    assert "使用阶段或当前安排" not in text
    assert "又开一听" not in text
    assert "睡前那杯" not in text
    keyword_text = _keyword_corpus_text([], content_type="article", output_fields=["title", "body"], business_rule=business_rule)
    assert "标题形态可写成使用阶段或当前安排" in keyword_text


def test_generation_requirements_title_shape_controls_emoji_surface():
    from app.services.unified_content_generation_service import _generation_requirements

    emoji_text = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "post_type": "复购/长期使用",
            "product_appearance_mode": "旺玥作为补货对象出现",
            "title_shape_mode": "TITLE_OBJECT_ACTION",
            "title_emoji_mode": "TITLE_EMOJI_LIGHT",
        },
        [],
    )
    plain_text = _generation_requirements(
        "article",
        ["title", "body"],
        {
            "post_type": "使用反馈",
            "product_appearance_mode": "保护力理由加一个状态反馈",
            "title_shape_mode": "TITLE_SCENE_FRAGMENT",
            "title_emoji_mode": "TITLE_EMOJI_NONE",
        },
        [],
    )

    assert "标题可以不用 emoji" not in emoji_text
    assert "标题最多加 1 个普通生活口气 emoji" not in emoji_text
    assert "最多不超过20字，emoji 按 2 字计" in emoji_text
    assert "优先 4-12 字" not in emoji_text
    assert "不主动交代完整背景" not in emoji_text
    assert emoji_text.count("标题硬边界") == 1
    assert "标题要像真人随手起的小红书标题" not in emoji_text
    assert "😂/🥲/🙃/🤏/🙂" not in emoji_text
    assert "不要使用 😅/✨/🔥/✅/💯/👍/🍼" not in emoji_text
    assert "优先用 😂" not in emoji_text
    assert "优先用 😅" not in emoji_text
    assert "正文不要加 emoji" not in emoji_text
    assert "本篇标题不加 emoji" in plain_text
    assert "TITLE_OBJECT_ACTION" not in emoji_text
    assert "TITLE_SCENE_FRAGMENT" not in plain_text


def test_wangyue_product_value_task_drops_duplicate_entry_prefix():
    from app.services.unified_content_generation_service import (
        _article_selling_surface_context_line,
        _drop_product_relation_prefix,
    )

    text = _article_selling_surface_context_line(
        {
            "product_appearance_mode": "三岁后给孩子选了旺玥。",
            "selling_description": "三岁后选了旺玥；更看重钙铁锌和多种关键营养配得全。",
        }
    )

    assert "三岁后选了旺玥；" not in text
    assert "更看重钙铁锌和多种关键营养配得全" in text
    assert (
        _drop_product_relation_prefix(
            "当时挑儿童奶粉时看中旺玥对保护力的支持，也留意了乳铁蛋白和HMO；喝到现在孩子状态挺稳。",
            "最后选择了旺玥。",
        )
        == "当时挑儿童奶粉时看中旺玥对保护力的支持，也留意了乳铁蛋白和HMO；喝到现在孩子状态挺稳。"
    )


@pytest.mark.asyncio
async def test_unified_article_generation_renders_article_requirement_before_business_rule(unified_session_factory):
    requirement = "生成前先在心里把业务规则拆成核心痛点/卖点、不能碰的边界、可自由变化的生活入口。"
    async with unified_session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type=SYSTEM_KEYWORD_ASSET_TYPE,
                asset_key=DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
                display_name="旺玥帖子关键词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "categories": [
                        {
                            "category_code": "article_generation_requirement",
                            "category_name": "帖子生成要求",
                            "applicable_content_types": ["article"],
                            "sub_keywords": [
                                {
                                    "keyword_code": "business_core_path_expansion",
                                    "keyword_name": "业务内核发散",
                                    "corpus": [requirement],
                                }
                            ],
                        },
                        _category("perturbation_rule", "扰动规则", ["随机发散"]),
                    ]
                },
            )
        )
        await session.commit()

        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="article",
            business_rule={
                "rule_type": "business_rule",
                "business_rule": "营养不足/成长发育需求",
                "corpus": "写作规则：围绕旺玥日常营养补充来写。",
                "examples": ["对比了很多家奶粉，最终选了旺玥。"],
            },
            item_no=1,
            output_fields=["title", "body"],
        )

    prompt = snapshot.input_snapshot["rendered_prompt"]
    selected = snapshot.input_snapshot["selected_keywords"]
    assert selected[0]["category_code"] == "article_generation_requirement"
    assert selected[0]["keyword_name"] == "业务内核发散"
    assert prompt.startswith("你是小红书母婴内容生成 expert。\n根据生成要求、业务规则和表达扩散语料生成内容。\n\n【生成要求】")
    assert "标题硬边界" in prompt
    assert "最多不超过20字，emoji 按 2 字计" in prompt
    assert "从正文里挑一个自然短句" not in prompt
    assert prompt.index("标题硬边界") < prompt.index(requirement)
    assert prompt.index(requirement) < prompt.index("【业务规则】")
    assert prompt.index("【业务规则】") < prompt.index("【表达扩散语料】")
    assert "表达扩散语料使用边界：以下只用于调语气、节奏、生活毛边和标题松散感" in prompt
    assert "产品事实、成分、正向反馈、产品动作和正文事件只按业务规则里的本篇信息和叙事主线" in prompt
    assert "不要照搬语料，也不要把语料扩成新的事实、第二个生活入口、第二个收尾现场" in prompt
    assert "业务内核发散" not in prompt[prompt.index("【表达扩散语料】") :]
    assert prompt.rstrip().endswith(
        '【输出格式】\n只输出 JSON：{"title":"...","body":"..."}。'
    )
    assert "表达参考：以下内容可以不用；只借说话方式，不照搬事实和句式" in prompt
    assert "参考短句" in prompt
    assert "规则内示例边界：以下示例是低权重短句纹理，可以完全不用" not in prompt


@pytest.mark.asyncio
async def test_unified_article_generation_renders_mouth_phrase_budget_before_keyword_requirements(unified_session_factory):
    requirement = "生成前先在心里把业务规则拆成核心痛点/卖点、不能碰的边界、可自由变化的生活入口。"
    async with unified_session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type=SYSTEM_KEYWORD_ASSET_TYPE,
                asset_key=DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
                display_name="旺玥帖子关键词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "categories": [
                        {
                            "category_code": "article_generation_requirement",
                            "category_name": "帖子生成要求",
                            "applicable_content_types": ["article"],
                            "sub_keywords": [
                                {
                                    "keyword_code": "business_core_path_expansion",
                                    "keyword_name": "业务内核发散",
                                    "corpus": [requirement],
                                }
                            ],
                        },
                    ]
                },
            )
        )
        await session.commit()

        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="article",
            business_rule={
                "rule_type": "business_rule",
                "business_rule": "营养不足/成长发育需求",
                "corpus": "写作规则：围绕旺玥日常营养补充来写。",
                "mouth_phrase_budget": {
                    "enabled": True,
                    "allowed_terms": ["最近"],
                    "avoid_terms": ["省心"],
                },
            },
            item_no=1,
            output_fields=["title", "body"],
        )

    prompt = snapshot.input_snapshot["rendered_prompt"]
    assert prompt.index("批量口癖控制") < prompt.index(requirement)
    assert prompt.index(requirement) < prompt.index("【输出格式】")
    assert prompt.rstrip().endswith('只输出 JSON：{"title":"...","body":"..."}。')


@pytest.mark.asyncio
async def test_unified_comment_generation_keeps_yuanyue_brand_guard_asset_scoped(unified_session_factory):
    generation_requirements = (
        "源悦评论只写源悦、这款或它家，禁止出现星飞帆、a2、A2、爱他美等任何其他奶粉品牌名。"
    )
    async with unified_session_factory() as session:
        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={
                "asset_key": "yuanyue_comment_activity",
                "rule_type": "business_rule",
                "business_rule": "整体适应",
                "generation_requirements": generation_requirements,
            },
            item_no=1,
            output_fields=["comment"],
        )

    assert "源悦评论只写源悦、这款或它家" in snapshot.input_snapshot["rendered_prompt"]
    assert "禁止出现星飞帆、a2、A2、爱他美" in snapshot.input_snapshot["rendered_prompt"]


@pytest.mark.asyncio
async def test_unified_comment_generation_does_not_add_a2_business_boundaries(unified_session_factory):
    async with unified_session_factory() as session:
        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={
                "asset_key": "a2_sentiment_comment_activity",
                "quality_guard_profile_key": "a2_sentiment_comment_202606",
                "rule_type": "business_rule",
                "business_rule": "A2舆情改善评论",
                "corpus": "关键词方向是有货+转奶。",
            },
            item_no=1,
            output_fields=["comment"],
    )

    prompt = snapshot.input_snapshot["rendered_prompt"]
    assert prompt.startswith("生文指令：")
    assert "你正在小红书母婴评论区" not in prompt
    assert "评论内容不用很丰富，简单表达含义和情绪即可" not in prompt
    assert "【生成要求】" not in prompt
    assert "只输出评论正文，不要标题、编号、解释" in prompt
    assert "A2评论不要为了凑组合关键词强行补信息" not in prompt
    assert "不要自行补具体检测数值" not in prompt
    assert "只有业务规则写了具体数值时才可跟随" not in prompt
    assert "检测数值要和蜡样检测、报告里那项或检测数值连起来说" not in prompt
    assert "扫码说法用扫罐底物流码、扫物流码看报告、罐底一扫这类自然说法" not in prompt
    assert "正文必须自然带一个竞品名" not in prompt
    assert "提到爱他美时不能只写也看过" not in prompt
    assert "美素/皇家美素/皇美" not in prompt
    assert "讲清a2的具体优势" not in prompt
    assert "A2评论写成20到45字左右" not in prompt
    assert "不要把检测数值拿去和宝宝肚肚反应或竞品品牌直接对比" not in prompt
    assert "检测数值只用口语写法" not in prompt
    assert "0.03" not in prompt


@pytest.mark.asyncio
async def test_unified_a2_member_comment_keeps_brand_anchor_requirement(unified_session_factory):
    async with unified_session_factory() as session:
        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={
                "asset_key": "a2_sentiment_comment_activity",
                "quality_guard_profile_key": "a2_sentiment_comment_202606",
                "rule_type": "business_rule",
                "business_rule": "会员权益-积分换礼",
                "corpus": "评论里要出现 a2 或至初，不要只写泛泛的会员活动。",
                "examples": ["a2积分可以换礼品，我准备去看看"],
            },
            item_no=1,
            output_fields=["comment"],
        )

    prompt = snapshot.input_snapshot["rendered_prompt"]
    assert "评论里要出现 a2 或至初，不要只写泛泛的会员活动" in prompt
    assert "评论正文必须自然出现a2或至初，不要只写泛泛的会员活动" not in prompt


@pytest.mark.asyncio
async def test_unified_a2_member_comment_keeps_full_rule_detail_and_fact_boundary(unified_session_factory):
    corpus = "像妈妈看到a2会员活动里可以集罐换奶粉、攒罐换礼、空罐先留着之后的评论。评论里要出现a2或至初，不要只写泛泛的会员活动。"
    async with unified_session_factory() as session:
        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={
                "asset_key": "a2_sentiment_comment_activity",
                "quality_guard_profile_key": "a2_sentiment_comment_202606",
                "rule_type": "business_rule",
                "business_rule": "会员权益-集罐换礼",
                "corpus": corpus,
                "examples": ["a2集罐能换奶粉，我先把空罐留着。"],
            },
            item_no=1,
            output_fields=["comment"],
        )

    prompt = snapshot.input_snapshot["rendered_prompt"]
    assert "内容方向：" in prompt
    assert corpus in prompt
    assert "可以围绕会员权益、集罐、积分、换礼或老客活动这些信息来写。" not in prompt
    assert "会员权益、集罐或积分活动" not in prompt
    assert "本条方向：" not in prompt
    assert "具体长短参考示例" not in prompt
    assert "【生成要求】" not in prompt
    assert "不把礼品、门槛、领取或中奖结果扩成新事实" in prompt
    assert "其他奶粉品牌名" not in prompt
    assert "转奶对象" not in prompt


def test_a2_comment_does_not_render_scenario_post_context():
    task_keyword = {
        "category_code": "comment_generation_requirement",
        "corpus": ["生成一条小红书母婴社区真实用户评论，口语化，有活人感。"],
    }
    rule = {
        "asset_key": "a2_sentiment_comment_activity",
        "business_rule": "会员权益-集罐换礼",
        "corpus": "像评论区顺手聊 a2 集罐换礼。",
    }

    generic_prompt = _comment_prompt_text(rule, selected_keywords=[task_keyword])
    specific_context = "你正在小红书母婴评论区，回复一篇消费者吐槽会员活动的帖子。"
    specific_prompt = _comment_prompt_text(
        {**rule, "scenario_post_context": specific_context},
        selected_keywords=[task_keyword],
    )

    assert generic_prompt.startswith("生文指令：")
    assert "你正在小红书母婴评论区" not in generic_prompt
    assert specific_prompt.startswith("生文指令：")
    assert specific_context not in specific_prompt


def test_a2_stock_comment_uses_task_instruction_without_scenario_context():
    context = "你正在小红书母婴评论区，回复一篇聊a2奶粉到货或能否买到的帖子。"
    prompt = _comment_prompt_text(
        {
            "asset_key": "a2_sentiment_comment_activity",
            "business_rule": "有货-直给到货情绪",
            "corpus": "像刷到a2到货后的一句自然接话。",
            "examples": ["a2终于到货了，我去看看"],
            "scenario_post_context": context,
        }
    )

    assert prompt.startswith("内容方向：")
    assert context not in prompt
    assert "前段时间a2奶粉没货" not in prompt
    assert "今天突然发现有货" not in prompt
    assert "字数不要超过80字" in prompt
    assert "字数在10到20字之间" not in prompt


def test_a2_comment_tone_rotates_and_renders_without_creating_facts():
    rule = {
        "asset_key": "a2_sentiment_comment_activity",
        "business_rule": "有货-直给到货情绪",
        "corpus": "像刷到a2到货后顺手接一句。",
        "comment_tone_options": [
            {
                "tone_code": "confirming_tone",
                "tone_label": "先确认",
                "prompt": "有点好奇，会先确认一下",
            },
            {
                "tone_code": "direct_tone",
                "tone_label": "直接说",
                "prompt": "语气直接，不铺垫",
            },
        ],
    }

    first = _select_comment_tone(rule, item_no=1)
    second = _select_comment_tone(rule, item_no=2)
    third = _select_comment_tone(rule, item_no=3)
    prompt = _comment_prompt_text(rule, comment_tone=first)

    assert first["tone_code"] == "confirming_tone"
    assert second["tone_code"] == "direct_tone"
    assert third == first
    assert "本条语气槽：\n先确认：有点好奇，会先确认一下" in prompt
    assert "语气槽只控制说法，不提供事实" in prompt
    assert "不要因此新增购买经历、喂养方式、宝宝状态或使用结果" in prompt


def test_legacy_comment_persona_options_are_read_as_tone_options():
    selected = _select_comment_tone(
        {
            "comment_persona_options": [
                {
                    "persona_code": "legacy_style",
                    "persona_label": "旧标签",
                    "prompt": "语气简短。",
                }
            ]
        },
        item_no=1,
    )

    assert selected == {
        "tone_code": "legacy_style",
        "tone_label": "旧标签",
        "prompt": "语气简短。",
    }


def test_comment_variation_slots_are_selected_and_rendered():
    rule = {
        "variation_slots": [
            {
                "slot_code": "comment_entry",
                "slot_name": "接法槽",
                "options": ["追问：先问一句", "报信：直接补一句信息"],
            },
            {
                "slot_code": "info_source",
                "slot_name": "来源槽",
                "options": ["信息来自妈妈群", "信息来自导购通知"],
            },
        ]
    }

    with patch(
        "app.services.unified_content_generation_service._random_choice_index",
        side_effect=[1, 0],
    ):
        selected = _select_comment_prompt_slots(rule)

    assert selected == [
        {
            "slot_name": "接法槽",
            "text": "报信：直接补一句信息",
            "selected_index": 1,
            "candidate_count": 2,
        },
        {
            "slot_name": "来源槽",
            "text": "信息来自妈妈群",
            "selected_index": 0,
            "candidate_count": 2,
        },
    ]
    prompt = _comment_prompt_text(rule, selected_prompt_slots=selected)
    assert "接法槽：报信：直接补一句信息" in prompt
    assert "来源槽：信息来自妈妈群" in prompt


@pytest.mark.parametrize(
    "business_rule",
    [
        "批批检-自己这批报告可查",
        "转奶-按自家节奏慢慢试",
        "会员权益-集罐换礼",
    ],
)
def test_a2_comment_context_does_not_fall_back_to_business_category(business_rule):
    prompt = _comment_prompt_text(
        {
            "asset_key": "a2_sentiment_comment_activity",
            "business_rule": business_rule,
            "corpus": "本条测试语料。",
        }
    )

    assert prompt.startswith("内容方向：")
    assert "你正在小红书母婴评论区" not in prompt


@pytest.mark.asyncio
async def test_unified_generation_splits_article_and_comment_instructions(unified_session_factory):
    async with unified_session_factory() as session:
        comment_snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={"rule_type": "business_rule", "business_rule": "整体适应"},
            item_no=1,
            output_fields=["comment"],
        )
        article_snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="article",
            business_rule={
                "rule_type": "business_rule",
                "business_rule": "宝宝便便不规律",
                "corpus": "写作规则：围绕宝宝便便不规律写一段真实观察。",
            },
            item_no=1,
            output_fields=["title", "body"],
        )

    comment_codes = [
        item["category_code"]
        for item in comment_snapshot.input_snapshot["selected_keywords"]
    ]
    article_codes = [
        item["category_code"]
        for item in article_snapshot.input_snapshot["selected_keywords"]
    ]
    assert "comment_writing_instruction" in comment_codes
    assert "comment_generation_requirement" not in comment_codes
    assert "comment_speaking_style" in comment_codes
    assert "writing_instruction" not in comment_codes
    assert "comment_format_control" in comment_codes
    assert "article_format_control" not in comment_codes
    assert "writing_instruction" in article_codes
    assert "comment_writing_instruction" not in article_codes
    assert "comment_generation_requirement" not in article_codes
    assert "comment_speaking_style" not in article_codes
    assert "article_format_control" in article_codes
    assert "comment_format_control" not in article_codes
    article_prompt = article_snapshot.input_snapshot["rendered_prompt"]
    assert "多样性槽位" not in article_prompt
    assert "格式/篇幅约束" not in article_prompt
    assert "帖子格式控制" not in article_prompt
    assert "- 业务规则：" not in article_prompt
    assert "- 业务语料：" not in article_prompt
    assert "标题硬边界" in article_prompt


@pytest.mark.asyncio
async def test_unified_generation_does_not_put_business_forbidden_terms_in_prompt(unified_session_factory):
    async with unified_session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type="business_forbidden_terms",
                asset_key="yuanyue_comment_activity",
                display_name="源悦评论业务违禁词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "schema_version": "1",
                    "terms": [{"term": "绝对好", "enabled": True}],
                },
            )
        )
        await session.commit()

        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={
                "asset_key": "yuanyue_comment_activity",
                "rule_type": "business_rule",
                "business_rule": "整体适应",
            },
            item_no=1,
            output_fields=["comment"],
        )

    assert "business_forbidden_terms" not in snapshot.input_snapshot
    assert "business_forbidden_terms" not in snapshot.asset_refs
    assert "绝对好" not in snapshot.input_snapshot["rendered_prompt"]


@pytest.mark.asyncio
async def test_unified_generation_uses_keyword_asset_key_from_business_rule(unified_session_factory):
    async with unified_session_factory() as session:
        session.add_all(
            [
                AssetRegistry(
                    asset_type=SYSTEM_KEYWORD_ASSET_TYPE,
                    asset_key=DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
                    display_name="默认关键词",
                    version_no=1,
                    status="active",
                    asset_stage="production",
                    content_json={"categories": [_category("persona", "人设", ["默认妈妈"])]},
                ),
                AssetRegistry(
                    asset_type=SYSTEM_KEYWORD_ASSET_TYPE,
                    asset_key="a2_plot_discussion_comment_keywords",
                    display_name="A2剧情讨论评论语料包",
                    version_no=1,
                    status="active",
                    asset_stage="production",
                    content_json={"categories": [_category("persona", "人设", ["剧情妈妈"])]},
                ),
            ]
        )
        await session.commit()

        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={
                "rule_type": "business_rule",
                "business_rule": "剧情讨论",
                "keyword_asset_key": "a2_plot_discussion_comment_keywords",
            },
            item_no=1,
            output_fields=["comment"],
        )

    assert snapshot.input_snapshot["keyword_asset"]["asset_key"] == "a2_plot_discussion_comment_keywords"
    assert snapshot.input_snapshot["keyword_asset"]["source"] == "asset_registry"
    assert snapshot.input_snapshot["selected_keywords"][0]["keyword_name"] == "剧情妈妈"
    assert "默认妈妈语料" not in snapshot.input_snapshot["rendered_prompt"]
    assert "剧情妈妈语料" not in snapshot.input_snapshot["rendered_prompt"]


@pytest.mark.asyncio
async def test_unified_generation_uses_light_requirements_for_a2_plot_discussion(unified_session_factory):
    generation_requirements = (
        "只输出一条评论正文，不要标题、编号、解释；"
        "正文控制在21到35字；"
        "每条都同时带一个剧情锚点和一个妈妈侧门店活动/补货动作。"
    )
    async with unified_session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type=SYSTEM_KEYWORD_ASSET_TYPE,
                asset_key=DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
                display_name="默认关键词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={"categories": [_category("persona", "人设", ["家庭妈妈"])]},
            )
        )
        await session.commit()

        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={
                "rule_type": "business_rule",
                "business_rule": "剧情讨论",
                "quality_guard_profile_key": "a2_plot_discussion_comment_202606",
                "generation_requirements": generation_requirements,
                "corpus": "剧情事实答复型：\n像妈妈聊奶宝找到妈妈后顺路去门店问活动。\n\n示例：\n- 找到了，我补货前去门店问问活动",
            },
            item_no=1,
            output_fields=["comment"],
        )

    prompt = snapshot.input_snapshot["rendered_prompt"]
    assert generation_requirements in prompt
    assert "遇到便便、生病这类业务规则" not in prompt
    assert "品牌名称只能使用业务规则或参考示例里的品牌" not in prompt


@pytest.mark.asyncio
async def test_unified_generation_handles_extensible_keyword_categories(unified_session_factory):
    async with unified_session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type=SYSTEM_KEYWORD_ASSET_TYPE,
                asset_key=DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
                display_name="扩展关键词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "categories": [
                        _category("persona", "人设", ["经验妈妈"]),
                        _category("rhythm", "句式节奏", ["短句"]),
                        {
                            **_category("article_only", "文章专用", ["长文结构"]),
                            "applicable_content_types": ["article"],
                        },
                        {
                            **_category("disabled_category", "停用类别", ["不应出现"]),
                            "enabled": False,
                        },
                    ]
                },
            )
        )
        await session.commit()

        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={"rule_type": "business_rule", "business_rule": "互动提问"},
            item_no=1,
            output_fields=["comment"],
        )

    selected = snapshot.input_snapshot["selected_keywords"]
    assert [item["category_code"] for item in selected] == ["persona", "rhythm"]
    assert selected[1]["keyword_name"] == "短句"
    assert "短句语料" not in snapshot.input_snapshot["rendered_prompt"]
    assert "长文结构语料" not in snapshot.input_snapshot["rendered_prompt"]
    assert "不应出现语料" not in snapshot.input_snapshot["rendered_prompt"]


@pytest.mark.asyncio
async def test_unified_generation_respects_fixed_keyword_selection(unified_session_factory):
    async with unified_session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type=SYSTEM_KEYWORD_ASSET_TYPE,
                asset_key=DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
                display_name="固定关键词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "categories": [
                        {
                            **_category("persona", "人设", ["经验妈妈", "观察妈妈"]),
                            "selection_mode": "fixed",
                            "selected_keyword_code": "persona_2",
                        }
                    ]
                },
            )
        )
        await session.commit()

        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={"rule_type": "business_rule", "business_rule": "互动提问"},
            item_no=1,
            output_fields=["comment"],
        )

    selected = snapshot.input_snapshot["selected_keywords"]
    assert selected[0]["keyword_code"] == "persona_2"
    assert selected[0]["keyword_name"] == "观察妈妈"
    assert "观察妈妈语料" not in snapshot.input_snapshot["rendered_prompt"]


@pytest.mark.asyncio
async def test_unified_generation_filters_persona_by_business_rule_keyword_selection(unified_session_factory):
    async with unified_session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type=SYSTEM_KEYWORD_ASSET_TYPE,
                asset_key=DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
                display_name="全局关键词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "categories": [
                        _category("persona", "人设", ["家庭妈妈", "成分妈妈", "职场妈妈"]),
                        _category("comment_writing_instruction", "生评论指令", ["自然表达"]),
                    ]
                },
            )
        )
        await session.commit()

        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={
                "rule_type": "business_rule",
                "business_rule": "剧情讨论",
                "keyword_selection": {"persona": ["persona_1", "persona_3"]},
            },
            item_no=2,
            output_fields=["comment"],
        )

    selected_persona = [
        item for item in snapshot.input_snapshot["selected_keywords"] if item["category_code"] == "persona"
    ][0]
    assert selected_persona["keyword_code"] == "persona_3"
    assert selected_persona["keyword_name"] == "职场妈妈"
    assert "成分妈妈语料" not in snapshot.input_snapshot["rendered_prompt"]


@pytest.mark.asyncio
async def test_unified_generation_uses_a2_asset_keyword_selection_for_sentiment_comment(unified_session_factory):
    async with unified_session_factory() as session:
        session.add(
            AssetRegistry(
                asset_type=SYSTEM_KEYWORD_ASSET_TYPE,
                asset_key=DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
                display_name="全局关键词",
                version_no=1,
                status="active",
                asset_stage="production",
                content_json={
                    "categories": [
                        {
                            "category_code": "persona",
                            "category_name": "人设",
                            "applicable_content_types": ["comment"],
                            "sub_keywords": [
                                {
                                    "keyword_code": "careful_observer",
                                    "keyword_name": "细节观察型妈妈",
                                    "corpus": ["表达时多写具体观察和真实顾虑，少下结论，保留一点继续观望的感觉。"],
                                },
                                {
                                    "keyword_code": "rational_comparer",
                                    "keyword_name": "理性比较型妈妈",
                                    "corpus": ["用克制的比较口吻表达，关注选择依据，不做绝对化推荐。"],
                                },
                            ],
                        },
                        {
                            "category_code": "comment_writing_instruction",
                            "category_name": "生评论指令",
                            "applicable_content_types": ["comment"],
                            "sub_keywords": [
                                {
                                    "keyword_code": "natural_comment",
                                    "keyword_name": "自然评论区表达",
                                    "corpus": ["语言像妈妈在评论区顺手补一句，不写成广告口播。"],
                                },
                                {
                                    "keyword_code": "specific_comment_question",
                                    "keyword_name": "带着具体问题来",
                                    "corpus": ["把泛泛兴趣落到纸尿裤、擦屁屁、转奶第几天、喝奶后状态这类小观察上。"],
                                },
                                {
                                    "keyword_code": "light_comment_experience",
                                    "keyword_name": "轻经验互动",
                                    "corpus": ["可以带一点轻量经验感，不必凑成完整总结。"],
                                },
                            ],
                        },
                        {
                            "category_code": "writing_method",
                            "category_name": "写作手法",
                            "applicable_content_types": ["comment"],
                            "sub_keywords": [
                                {
                                    "keyword_code": "scene_detail",
                                    "keyword_name": "场景细节法",
                                    "corpus": ["用一个纸尿裤、擦屁屁、奶瓶剩余、早晚臭臭之类的小细节承接业务规则。"],
                                },
                                {
                                    "keyword_code": "plain_explain",
                                    "keyword_name": "白话解释法",
                                    "corpus": ["把复杂点说得更白话，但不扩写成硬科普。"],
                                },
                            ],
                        },
                    ]
                },
            )
        )
        await session.commit()

        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={
                "rule_type": "business_rule",
                "business_rule": "批批检+转奶，转奶前看蜡样那项",
                "quality_guard_profile_key": "a2_sentiment_comment_202606",
                "keyword_selection": {
                    "persona": ["rational_comparer"],
                    "comment_writing_instruction": ["natural_comment"],
                    "writing_method": ["plain_explain"],
                },
                "corpus": "转奶前看a2这罐对应批次的质检和蜡样检测报告。",
            },
            item_no=1,
            output_fields=["comment"],
        )

    selected_codes = {item["keyword_code"] for item in snapshot.input_snapshot["selected_keywords"]}
    assert "careful_observer" not in selected_codes
    assert "rational_comparer" in selected_codes
    assert "specific_comment_question" not in selected_codes
    assert "scene_detail" not in selected_codes
    assert "light_comment_experience" not in selected_codes
    assert "natural_comment" in selected_codes
    assert "plain_explain" in selected_codes
    prompt = snapshot.input_snapshot["rendered_prompt"]
    assert "臭臭" not in prompt
    assert "喝奶后状态" not in prompt


def test_wangyue_keyword_corpus_filters_article_speaking_style_slot():
    from app.services.unified_content_generation_service import _keyword_corpus_text

    selected_keywords = [
        {
            "category_code": "article_speaking_style",
            "category_name": "帖子说话方式",
            "keyword_code": "routine_log",
            "keyword_name": "日常流水账式",
            "corpus": ["像记录一天里的喝奶、吃饭、上学、睡前这些小安排，句子可以松散一点。"],
        },
        {
            "category_code": "writing_method",
            "category_name": "写作手法",
            "keyword_code": "scene_detail",
            "keyword_name": "场景细节法",
            "corpus": ["用一个自然小细节承接业务规则。"],
        },
        {
            "category_code": "persona",
            "category_name": "人设",
            "keyword_code": "working_rush_mom",
            "keyword_name": "职场赶时间妈妈",
            "corpus": ["只借时间被工作和带娃挤压的节奏，不新增产品事实。"],
        },
    ]

    wangyue_text = _keyword_corpus_text(
        selected_keywords,
        content_type="article",
        output_fields=["title", "body"],
        business_rule={"asset_key": "wangyue_v3_core_storyline_article_rules", "corpus": "旺玥"},
    )
    generic_text = _keyword_corpus_text(
        selected_keywords,
        content_type="article",
        output_fields=["title", "body"],
        business_rule={"corpus": "普通文章"},
    )

    assert "帖子说话方式" not in wangyue_text
    assert "日常流水账式" not in wangyue_text
    assert "喝奶、吃饭、上学" not in wangyue_text
    assert "场景细节法" in wangyue_text
    assert "人设 / 职场赶时间妈妈" in wangyue_text
    assert "只借时间被工作和带娃挤压的节奏" in wangyue_text
    assert "日常流水账式" in generic_text


def test_wangyue_keyword_corpus_contract_keeps_expression_layer_low_weight():
    from app.services.unified_content_generation_service import _keyword_corpus_text

    selected_keywords = [
        {
            "category_code": "article_generation_requirement",
            "category_name": "生成要求补充",
            "keyword_code": "wangyue_value_with_life_v288",
            "keyword_name": "价值和生活同在",
            "corpus": ["生活现场从本篇痛点自然生发，不固定压在产品使用流程或同一类家务动作上。"],
        },
        {
            "category_code": "perturbation_rule",
            "category_name": "扰动规则",
            "keyword_code": "random_thinking_shift",
            "keyword_name": "随机发散",
            "corpus": ["同一批里让发帖切入、妈妈想法和收尾语气分散。"],
        },
        {
            "category_code": "article_format_control",
            "category_name": "帖子格式控制",
            "keyword_code": "article_compact_clean",
            "keyword_name": "短帖干净",
            "corpus": ["正文篇幅和段落优先服从业务规则；整体表达干净紧凑。"],
        },
        {
            "category_code": "article_speaking_style",
            "category_name": "帖子说话方式",
            "keyword_code": "routine_log",
            "keyword_name": "松散流水式",
            "corpus": ["句子可以像随手写一样松散，有跳跃和省略。"],
        },
        {
            "category_code": "persona",
            "category_name": "生活身份机制",
            "keyword_code": "wangyue_group_attention_v288",
            "keyword_name": "群消息牵动注意",
            "corpus": ["可借班级群、身边妈妈聊天带来的注意力变化，再回到自家观察。"],
        },
    ]

    text = _keyword_corpus_text(
        selected_keywords,
        content_type="article",
        output_fields=["title", "body"],
        business_rule={"asset_key": "wangyue_v309_keyword_role_narrowing_article_rules", "corpus": "旺玥"},
    )

    assert "表达扩散语料使用边界" in text
    assert "产品事实、成分、正向反馈、产品动作和正文事件只按业务规则里的本篇信息和叙事主线" in text
    assert "扰动规则 / 随机发散" in text
    assert "同一批里让发帖切入、妈妈想法和收尾语气分散" in text
    assert "生活身份机制 / 群消息牵动注意" in text
    assert "班级群、身边妈妈聊天" in text
    assert "生成要求补充" not in text
    assert "生活现场从本篇痛点自然生发" not in text
    assert "帖子格式控制" not in text
    assert "正文篇幅和段落优先服从业务规则" not in text
    assert "帖子说话方式" not in text
    assert "松散流水式" not in text
    assert "正文同时有旺玥的正向价值" not in text
    assert "字段名、槽位名、内部分类" not in text
    assert "随机性服务生活感，不新增产品事实或孩子状态" not in text


def test_wangyue_keyword_corpus_binds_scene_and_ending_texture_to_story_spine():
    from app.services.unified_content_generation_service import _keyword_corpus_text

    selected_keywords = [
        {
            "category_code": "persona",
            "category_name": "生活身份机制",
            "keyword_code": "housework_list",
            "keyword_name": "家务脑内清单",
            "corpus": ["可借真实帖子里家务、常备带来的生活压力。"],
        },
        {
            "category_code": "article_real_ending_texture",
            "category_name": "真人自然结尾",
            "keyword_code": "ending_return_current_scene",
            "keyword_name": "回到当前现场",
            "corpus": ["结尾回到正文已经出现的那个现场或动作。"],
        },
        {
            "category_code": "perturbation_rule",
            "category_name": "扰动规则",
            "keyword_code": "random_thinking_shift",
            "keyword_name": "随机发散",
            "corpus": ["同一批里让发帖切入、妈妈想法和收尾语气分散。"],
        },
    ]

    text = _keyword_corpus_text(
        selected_keywords,
        content_type="article",
        output_fields=["title", "body"],
        business_rule={
            "asset_key": "wangyue_v337_row14_purchase_tail_cleanup_article_rules",
            "story_spine": "从外出后或回家路上的精神状态起笔。",
        },
    )

    assert "使用边界：只借生活感和说话角度；正文事件仍从叙事主线出，不新增第二个入口。" in text
    assert "使用边界：只借收尾方式；结尾回到叙事主线已有现场，不新增第二个结尾。" in text
    assert "扰动规则 / 随机发散" in text
    perturbation_section = text.split("- 扰动规则 / 随机发散", 1)[1].split("\n- 生活身份机制", 1)[0]
    assert "使用边界：只借生活感和说话角度" not in perturbation_section


@pytest.mark.asyncio
async def test_unified_generation_keeps_expert_model_config_but_uses_comment_prompt_builder(unified_session_factory):
    async with unified_session_factory() as session:
        session.add(
            ExpertConfig(
                id=1,
                expert_config_code="comment_generator_v1",
                expert_config_name="评论生成 Expert",
                expert_type="GENERATION",
                expert_app="maga-worker",
                expert_service="content.Generate",
                expert_func="Generate",
                model_code="deepseek-test",
                model_config={"provider_code": "aihubmix", "temperature": 0.6, "max_tokens": 128},
                prompt_template="业务={{ business_rule }}\n关键词={{ keyword_corpus }}",
                enabled=1,
            )
        )
        await session.commit()

        snapshot = await UnifiedContentGenerationService(session).build_snapshot(
            content_type="comment",
            business_rule={"rule_type": "business_rule", "business_rule": "互动提问", "corpus": "问问大家"},
            item_no=1,
            output_fields=["comment"],
        )

    expert = snapshot.input_snapshot["expert"]
    assert expert["source"] == "expert_config"
    assert expert["model_config"] == {
        "provider_code": "aihubmix",
        "model_code": "deepseek-test",
        "temperature": 0.6,
        "max_tokens": 128,
    }
    assert snapshot.input_snapshot["rendered_prompt"].startswith("你是一位妈妈，在小红书母婴评论区回复别人关于这款奶粉的帖子。")
    assert "业务=" not in snapshot.input_snapshot["rendered_prompt"]
    assert "问问大家" in snapshot.input_snapshot["rendered_prompt"]


@pytest.mark.asyncio
async def test_comment_prompt_slot_randomizes_corpus_inside_fixed_slot(unified_session_factory):
    business_rule = {
        "rule_type": "business_rule",
        "business_rule": "互动提问",
        "corpus": "问问大家",
        "prompt_slots": {
            "说话风格": [
                "适当加几个网络热词，不要过度。",
                "像评论区接楼，短一点，顺手补一句。",
            ]
        },
    }
    async with unified_session_factory() as session:
        service = UnifiedContentGenerationService(session)
        with patch(
            "app.services.unified_content_generation_service._random_choice_index",
            side_effect=[0, 1],
        ):
            first = await service.build_snapshot(
                content_type="comment",
                business_rule=business_rule,
                item_no=1,
                output_fields=["comment"],
            )
            second = await service.build_snapshot(
                content_type="comment",
                business_rule=business_rule,
                item_no=1,
                output_fields=["comment"],
            )

    assert first.input_snapshot["selected_prompt_slots"] == [
        {
            "slot_name": "说话风格",
            "text": "适当加几个网络热词，不要过度。",
            "selected_index": 0,
            "candidate_count": 2,
        }
    ]
    assert second.input_snapshot["selected_prompt_slots"][0]["text"] == "像评论区接楼，短一点，顺手补一句。"
    assert "说话风格：适当加几个网络热词，不要过度。" in first.input_snapshot["rendered_prompt"]
    assert "说话风格：像评论区接楼，短一点，顺手补一句。" in second.input_snapshot["rendered_prompt"]


def test_comment_activity_fact_slot_renders_without_redundant_label():
    assert _render_comment_prompt_slot(
        {
            "slot_name": "本条活动事实",
            "text": "集罐可换：扭扭车",
        }
    ) == "集罐可换：扭扭车"


@pytest.mark.asyncio
async def test_comment_style_slot_rejects_business_terms(unified_session_factory):
    async with unified_session_factory() as session:
        with pytest.raises(ValueError, match="说话风格槽位不能包含业务元素"):
            await UnifiedContentGenerationService(session).build_snapshot(
                content_type="comment",
                business_rule={
                    "rule_type": "business_rule",
                    "business_rule": "互动提问",
                    "corpus": "问问大家",
                    "prompt_slots": {"说话风格": ["像一直喝a2的妈妈，补一句经验。"]},
                },
                item_no=1,
                output_fields=["comment"],
            )


def _category(category_code: str, category_name: str, keyword_names: list[str]) -> dict:
    return {
        "category_code": category_code,
        "category_name": category_name,
        "sub_keywords": [
            {
                "keyword_code": f"{category_code}_{index}",
                "keyword_name": keyword_name,
                "corpus": [f"{keyword_name}语料"],
            }
            for index, keyword_name in enumerate(keyword_names, start=1)
        ],
    }
