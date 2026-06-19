"""Tests for executing planned batch content items."""

import asyncio

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
from app.services.content_batch_execution_service import ContentBatchExecutionService
from app.services.executor_invocation_service import InvokeResult, MockExecutorInvocationClient
from app.services.forbidden_term_review_service import ForbiddenTermReviewService, find_forbidden_hits
from app.services.product_experience_phrase_guard_service import (
    review_product_experience_phrase,
    sanitize_adult_self_drinking_phrases,
    sanitize_baby_milk_action_phrases,
    sanitize_common_ai_closure,
    sanitize_odd_product_experience_phrases,
    sanitize_temporal_context,
    sanitize_wangyue_context_phrases,
)


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


def test_forbidden_hits_prefer_longer_overlapping_terms():
    hits = find_forbidden_hits(
        "娃倒没抗拒，价格也能接受。",
        ["没抗拒", "倒没抗拒", "能接", "能接受"],
    )

    assert hits.index("倒没抗拒") < hits.index("没抗拒")
    assert hits.index("能接受") < hits.index("能接")


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


def test_product_experience_baby_milk_action_cleanup_is_narrow_and_varied():
    bottle_text = "早上冲奶时娃自己抱着奶瓶咕嘟咕嘟喝，我偷偷乐了一下。"
    brew_text = "给娃挑旺玥的时候盯着成分看了半天。但看他每天主动去泡奶喝，我只能默默掏钱续上。"
    self_brew_text = "她早上自己冲一杯，两个月下来感觉精气神足了些。"
    scoop_text = "每天早晚一杯旺玥，孩子自己倒水舀粉，我就在旁边看着。"
    spoon_scoop_text = "晚上回家后孩子自己拿勺子舀了三勺，说这杯今天要浓一点。"
    indirect_brew_text = "现在每天早晚自己搬小凳子冲奶，晚上他自己洗完澡就去厨房泡旺玥。"
    can_brew_text = "早起穿校服，自己搬奶粉罐去了。他泡好端着，后来还自己抱着罐子让冲。"
    extra_scoop_text = "她拧开盖子说那好吧，又自己偷偷多舀了一勺。"
    adult_text = "今晚陪娃写作业，给自己冲一杯热水。"
    cup_text = "冲好后娃自己抱着杯子咕嘟咕嘟喝，我偷偷乐了一下。"

    assert sanitize_baby_milk_action_phrases(bottle_text) == "早上冲奶时娃自己抱着杯子咕嘟咕嘟喝，我偷偷乐了一下"
    cleaned_brew = sanitize_baby_milk_action_phrases(brew_text)
    assert "主动去泡奶喝" not in cleaned_brew
    assert "主动要喝" not in cleaned_brew
    assert cleaned_brew != brew_text
    cleaned_self_brew = sanitize_baby_milk_action_phrases(self_brew_text)
    assert "自己冲一杯" not in cleaned_self_brew
    assert "主动要喝" not in cleaned_self_brew
    cleaned_scoop = sanitize_baby_milk_action_phrases(scoop_text)
    assert "自己倒水舀粉" not in cleaned_scoop
    assert "主动要喝" not in cleaned_scoop
    cleaned_spoon_scoop = sanitize_baby_milk_action_phrases(spoon_scoop_text)
    assert "自己拿勺子舀了三勺" not in cleaned_spoon_scoop
    assert "主动要喝" not in cleaned_spoon_scoop
    cleaned_indirect_brew = sanitize_baby_milk_action_phrases(indirect_brew_text)
    assert "自己搬小凳子冲奶" not in cleaned_indirect_brew
    assert "自己洗完澡就去厨房泡旺玥" not in cleaned_indirect_brew
    assert "主动要喝" not in cleaned_indirect_brew
    cleaned_can_brew = sanitize_baby_milk_action_phrases(can_brew_text)
    assert "自己搬奶粉罐" not in cleaned_can_brew
    assert "他泡好端着" not in cleaned_can_brew
    assert "自己抱着罐子让冲" not in cleaned_can_brew
    assert "主动要喝" not in cleaned_can_brew
    cleaned_extra_scoop = sanitize_baby_milk_action_phrases(extra_scoop_text)
    assert "自己偷偷多舀了一勺" not in cleaned_extra_scoop
    assert "主动要喝" not in cleaned_extra_scoop
    assert sanitize_baby_milk_action_phrases(adult_text) == adult_text.strip("。")
    assert sanitize_baby_milk_action_phrases(cup_text) == cup_text.strip("。")


def test_product_experience_phrase_guard_blocks_wangyue_context_mistakes():
    review = review_product_experience_phrase(
        title="源悦真实体验分享",
        body="宝宝一岁多后出门多，我就在书包侧袋塞一盒旺玥，临时兑点温水摇匀。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert review.wangyue_wrong_brand_hits == ["源悦"]
    assert "宝宝一岁多" in review.wangyue_explicit_age_hits
    assert "书包侧袋" in review.wangyue_portable_form_hits
    assert "wangyue_wrong_brand" in review.reasons
    assert "wangyue_explicit_age_context" in review.reasons
    assert "wangyue_portable_form_context" in review.reasons


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


def test_product_experience_wangyue_context_cleanup_is_narrow():
    title = "源悦真实体验分享"
    body = "宝宝一岁多后出门多，我就在书包侧袋塞一盒旺玥，临时兑点温水摇匀。"

    assert sanitize_wangyue_context_phrases(title) == "旺玥真实体验分享"
    cleaned = sanitize_wangyue_context_phrases(body)
    assert "源悦" not in cleaned
    assert "一岁多" not in cleaned
    assert "书包侧袋" not in cleaned
    assert "一盒旺玥" not in cleaned
    assert "兑点温水摇匀" not in cleaned
    assert "旺玥" in cleaned
    portable_cleaned = sanitize_wangyue_context_phrases("清早往书包侧兜塞旺玥小条装，放学回来干掉了三根。")
    assert "小条装" not in portable_cleaned
    assert "三根" not in portable_cleaned


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


def test_product_experience_phrase_guard_blocks_explicit_temporal_context():
    review = review_product_experience_phrase(
        title="换季这几天",
        body="最近换季，娃胃口时好时坏，我就把旺玥奶粉安排上了，日常营养能跟上就行。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert review.temporal_context_hits == ["换季"]
    assert "explicit_temporal_context" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


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
    text = "换季这几天幼儿园容易中招，希望这学期少操点心，冬天也先不写。"

    cleaned = sanitize_temporal_context(text)

    assert cleaned == "这阵这几天幼儿园容易中招，希望这段时间少操点心，最近也先不写。"
    assert not review_product_experience_phrase(title=cleaned, body="", plan={}).temporal_context_hits


def test_product_experience_temporal_context_cleanup_repairs_suffix_after_replacement():
    text = "换季后孩子接触人多，春天后也容易担心。"

    cleaned = sanitize_temporal_context(text)

    assert cleaned == "这阵子孩子接触人多，最近也容易担心。"
    assert "最近后" not in cleaned


def test_product_experience_common_ai_closure_cleanup_removes_generic_tail():
    text = "老母亲家里一直喝旺玥，孩子状态也还行。希望能一直这样省心，继续观察看看，先这样喂着吧。继续观察吧，先这样喝着看看。"

    cleaned = sanitize_common_ai_closure(text)

    assert cleaned == "我家里一直喝旺玥，孩子状态也还行。希望后面少折腾点"
    assert "继续观察看看" not in cleaned
    assert "继续观察吧" not in cleaned
    assert "先这样喝着看看" not in cleaned
    assert "先这样喂着吧" not in cleaned
    assert "老母亲" not in cleaned


def test_product_experience_odd_phrase_cleanup_replaces_known_weird_phrases():
    text = "这杯奶一杯下去又活过来了，体格挺打底，也没有动不动就掉状态，效果。"

    cleaned = sanitize_odd_product_experience_phrases(text)

    assert cleaned == "这杯奶休息一会儿状态能缓过来，体格看着挺扎实，状态也还可以"
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


def test_product_experience_odd_phrase_cleanup_removes_dangling_fragments():
    text = "最近季的小担忧，先喝起来看看。我这我算是先着吧"

    cleaned = sanitize_odd_product_experience_phrases(text)

    assert cleaned == "最近的小担忧，先喝起来看看"
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
    assert len(rewrite_stages) == 2
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
                    "title": "旺玥和4段怎么选",
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
    assert all(title != "旺玥和4段怎么选" for title in titles)
    assert any("forbidden_title_phrase:4段" in repair["reasons"] for item in items for repair in item.quality_json["title_guard_repairs"])
    assert items[2].quality_json["title_guard"]["pass"] is True


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


class ProductExperienceTemporalContextClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "换季这阵旺玥没断",
                "body": "幼儿园接触人多，我还是担心孩子容易中招。家里一直喝旺玥，支持保护力，希望这学期少操点心。",
                "runtime_result": {"mode": "runtime_fast"},
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
                "body": "早上冲好旺玥递过去，他捧着杯子喝得挺顺。晚上到点也会坐过来等，我就继续给旺玥续上。",
                "final": {
                    "title": "给娃喝奶粉的日常小记录",
                    "body": "早上冲好旺玥递过去，他捧着杯子喝得挺顺。晚上到点也会坐过来等，我就继续给旺玥续上。",
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
    assert "学期" not in full_text
    assert "product_experience_temporal_context_cleanups" in item.quality_json
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    assert sum(1 for stage in stage_calls if stage.capability == "content.rewrite") == 0


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
    assert "product_experience_common_ai_closure_cleanups" in item.quality_json
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    assert sum(1 for stage in stage_calls if stage.capability == "content.rewrite") == 0


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
    assert "体格看着挺扎实" in full_text
    assert "休息一会儿状态能缓过来" in full_text
    assert "product_experience_odd_phrase_cleanups" in item.quality_json
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    assert sum(1 for stage in stage_calls if stage.capability == "content.rewrite") == 0


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
    assert "冲好旺玥递过去" in full_text
    assert "product_experience_baby_milk_action_cleanups" not in item.quality_json
    assert "product_experience_phrase_rewrites" in item.quality_json
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    rewrite_stages = [stage for stage in stage_calls if stage.capability == "content.rewrite"]
    assert len(rewrite_stages) == 1
    instructions = (rewrite_stages[0].input_snapshot or {}).get("rewrite_instructions") or []
    assert any("孩子自己冲/泡/舀奶粉" in instruction for instruction in instructions)


@pytest.mark.asyncio
async def test_batch_execution_cleans_wangyue_context_mistakes_for_article_business_rule():
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

    full_text = f"{item.title}\n{item.body}"
    assert "源悦" not in full_text
    assert "一岁多" not in full_text
    assert "书包侧袋" not in full_text
    assert "一盒旺玥" not in full_text
    assert "兑点温水摇匀" not in full_text
    assert "旺玥真实体验分享" in item.title
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
