import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.expert_config import ExpertConfig
from app.models.maga_assets import AssetRegistry
from app.services.unified_content_generation_service import (
    DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
    SYSTEM_KEYWORD_ASSET_TYPE,
    UnifiedContentGenerationService,
    _business_rule_text,
    _normalize_model_config,
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
    assert prompt.startswith("【生成要求】\n生成一条小红书母婴社区真实用户评论")
    assert prompt.count("【生成要求】") == 1
    assert prompt.index("【生成要求】") < prompt.index("【系统关键词语料】")
    assert prompt.index("【系统关键词语料】") < prompt.index("【业务规则】")
    assert prompt.index("- 扰动规则 / 长短扰动") < prompt.index("- 人设 / 经验妈妈")
    assert "整体适应" in snapshot.input_snapshot["rendered_prompt"]
    assert "经验妈妈" in snapshot.input_snapshot["rendered_prompt"]
    assert "生成一条小红书母婴社区真实用户评论" in snapshot.input_snapshot["rendered_prompt"]
    assert "只输出评论正文，不要标题、编号、解释" in snapshot.input_snapshot["rendered_prompt"]
    assert "标题要像真人随手起的小红书标题" not in snapshot.input_snapshot["rendered_prompt"]
    assert "先看业务规则里的参考示例，再换一种自然说法输出" in snapshot.input_snapshot["rendered_prompt"]
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

    assert "规则内示例使用边界：以下示例是弱参考，只借短句质感和真人毛边，可以完全不用" in text
    assert "不能决定正文路线" in text
    assert "以写作规则为准" in text
    assert "不要照搬示例里的原句、数字、配比、问句、结构、事实主张或固定句式骨架" in text
    assert "不要把多个示例细节拼成一篇" in text
    assert "如果示例让内容变窄或重复，就忽略示例" in text
    assert "规则内短句纹理（弱参考，可不用）" in text
    assert "抽中示例1" in text
    assert "抽中示例2" in text
    assert "抽中示例3" in text
    assert "example_pool_count" not in text


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
    assert "最近" in text
    assert "除上面列出的可用口癖外，本篇不要使用其他批量高频口头禅" in text
    assert "省心" not in text
    assert "踏实" not in text
    assert "不知道是不是心理作用" not in text
    assert "输出 JSON 对象" not in text


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
    assert "最多展开 1 个产品相关环节" in text
    assert text.index("内容路径控制") < text.index("标题要像真人随手起的小红书标题")


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
    assert prompt.startswith("你是小红书母婴内容生成 expert。\n请根据业务规则和系统内置关键词语料，生成一篇自然种草内容。\n\n【生成要求】")
    assert "标题要像真人随手起的小红书标题" in prompt
    assert "不要总结正文卖点" in prompt
    assert prompt.index("标题要像真人随手起的小红书标题") < prompt.index(requirement)
    assert prompt.index(requirement) < prompt.index("【业务规则】")
    assert prompt.index("【业务规则】") < prompt.index("【系统关键词语料】")
    assert "业务内核发散" not in prompt[prompt.index("【系统关键词语料】") :]
    assert "规则内示例边界：以下示例是低权重短句纹理，可以完全不用" in prompt


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
    assert "生成一条小红书母婴社区真实用户评论" in prompt
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
    assert "comment_generation_requirement" in comment_codes
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
    assert "正文按业务规则控制篇幅和表达" in article_prompt


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
    assert "剧情妈妈语料" in snapshot.input_snapshot["rendered_prompt"]


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
    assert "短句语料" in snapshot.input_snapshot["rendered_prompt"]
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
    assert "观察妈妈语料" in snapshot.input_snapshot["rendered_prompt"]


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


@pytest.mark.asyncio
async def test_unified_generation_uses_expert_template_and_model_config(unified_session_factory):
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
    assert snapshot.input_snapshot["rendered_prompt"].startswith("业务=")


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
