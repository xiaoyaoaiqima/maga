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
from app.services.content_batch_execution_service import (
    ContentBatchExecutionService,
    _body_title_candidates,
    _fallback_wangyue_growth_nutrition_body,
    _fallback_title_for_item,
    _mouth_phrase_budget_hits,
    _mouth_phrase_budget_rewrite_input,
    _title_guard_reasons,
)
from app.services.executor_invocation_service import InvokeResult, MockExecutorInvocationClient
from app.services.forbidden_term_review_service import ForbiddenTermReviewService, find_forbidden_hits
from app.services.product_experience_phrase_guard_service import (
    review_product_experience_phrase,
    sanitize_adult_self_drinking_phrases,
    sanitize_baby_milk_action_phrases,
    sanitize_common_ai_closure,
    sanitize_odd_product_experience_phrases,
    sanitize_product_experience_format,
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
    assert "删除包含“不用再……”的短句" in payload["rewrite_instructions"][3]
    assert "也不要把它们换成其他本篇未分配口癖：除了贵、踏实" in payload["rewrite_instructions"][4]
    assert "不要补新的妈妈总结套话" in payload["rewrite_instructions"][5]
    assert "不要把时间口癖改成换季" in payload["rewrite_instructions"][6]
    assert "最近" not in payload["rewrite_instructions"][0]


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

    assert cleaned == "这种小变化我会记一下"
    assert sanitize_odd_product_experience_phrases("小胳膊小腿看着结实了些，不知道是不是营养跟上了，先") == (
        "小胳膊小腿看着结实了些，不知道是不是营养跟上了"
    )
    assert sanitize_odd_product_experience_phrases("省得我老惦记他营养不均衡。踏实") == "省得我老惦记他营养不均衡"
    assert sanitize_odd_product_experience_phrases("这奶粉喝着还行～（你家娃在忙啥？）") == "这奶粉喝着还行～"
    assert sanitize_odd_product_experience_phrases("谁懂啊，当妈的心里就这点小算盘") == "这种小变化我会记一下"
    assert sanitize_odd_product_experience_phrases("皇家美美佳儿旺玥") == "皇家美素佳儿旺玥"


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
    assert sanitize_odd_product_experience_phrases("冲一杯就搞定。") == "日常补充起来还算顺手"
    assert sanitize_odd_product_experience_phrases("皇家美素佳儿旺玥每天当补给。") == "皇家美素佳儿旺玥作为日常补充"
    assert sanitize_odd_product_experience_phrases("不用老想着今天是不是又缺了啥。") == "不用老想着今天是不是又营养没跟上"
    assert sanitize_odd_product_experience_phrases("成长阶段缺一点少一点，怕他体力跟不上。") == "成长阶段营养没跟上，怕他体力跟不上"
    assert sanitize_wangyue_context_phrases("出门恨不得把辅食机都塞包里。") == "有时会觉得营养安排挺琐碎"
    assert sanitize_wangyue_context_phrases("带娃出门前塞进背包的东西") == "带娃出门前放在家里的东西"
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
    assert "一岁多" not in cleaned
    assert "书包侧袋" not in cleaned
    assert "一盒旺玥" not in cleaned
    assert "兑点温水摇匀" not in cleaned
    assert "旺玥" in cleaned
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
    assert "旺玥" in latest_cleaned
    assert "家里那款" not in latest_cleaned
    water_milk_cleaned = sanitize_wangyue_context_phrases("现在每天当水奶喝着，我也说不清具体哪里好。")
    assert "水奶" not in water_milk_cleaned
    assert "照常喝着" in water_milk_cleaned
    water_like_cleaned = sanitize_wangyue_context_phrases("孩子当顺手的水喝下去就行。")
    assert "当顺手的水喝" not in water_like_cleaned
    assert "照常喝下去" in water_like_cleaned
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
    assert "放在家里" in table_cleaned
    bag_cleaned = sanitize_wangyue_context_phrases("带娃出门，包里一定会塞一袋旺玥。")
    assert "包里一定会塞" not in bag_cleaned
    assert "一袋旺玥" not in bag_cleaned
    assert "旺玥" in bag_cleaned
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
    assert "旺玥" in schoolbag_cleaned
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
    assert "半岁" not in age_cleaned
    one_year_cleaned = sanitize_wangyue_context_phrases("一岁后开始研究儿童奶粉。")
    assert "一岁后" not in one_year_cleaned
    amount_cleaned = sanitize_wangyue_context_phrases("奶量从100ml慢慢喝到180ml，没硬追。")
    assert "100ml" not in amount_cleaned
    assert "180ml" not in amount_cleaned
    assert "奶量慢慢上来" in amount_cleaned
    bottle_cleaned = sanitize_wangyue_context_phrases("现在出门水壶里都是这个。")
    assert "水壶里" not in bottle_cleaned
    assert "在家喝这杯奶" in bottle_cleaned
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

    assert review.temporal_context_hits == ["风大的季节", "换季", "入夏", "天冷"]
    assert "explicit_temporal_context" in review.reasons
    assert review.rewrite_required is True
    assert review.pass_ is False


def test_product_experience_phrase_guard_blocks_event_and_stage_context():
    review = review_product_experience_phrase(
        title="中班后那罐奶粉",
        body="双十一囤的旺玥到了，娃上中班后接触人多，我还是看保护力。",
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "篇幅类型：短文；正文必须40-80字。0705旺玥活动",
        },
    )

    assert review.temporal_context_hits == ["双十一", "中班"]
    assert "explicit_temporal_context" in review.reasons


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
    text = "换季这几天幼儿园容易中招，希望这学期少操点心，冬天也先不写。"

    cleaned = sanitize_temporal_context(text)

    assert cleaned == "这阵这几天幼儿园容易中招，希望这段时间少操点心，最近也先不写。"
    assert not review_product_experience_phrase(title=cleaned, body="", plan={}).temporal_context_hits


def test_product_experience_temporal_context_cleanup_generalizes_event_and_stage():
    text = "双十一囤的旺玥到了，娃上中班后接触人多，幼儿园一降温我就紧张。"

    cleaned = sanitize_temporal_context(text)

    assert cleaned == "之前囤的旺玥到了，娃上学后接触人多，幼儿园一有状况我就紧张。"
    assert "双十一" not in cleaned
    assert "中班" not in cleaned
    assert "降温" not in cleaned


def test_product_experience_temporal_context_cleanup_repairs_suffix_after_replacement():
    text = "换季后孩子接触人多，春天后也容易担心。"

    cleaned = sanitize_temporal_context(text)

    assert cleaned == "这阵子孩子接触人多，最近也容易担心。"
    assert "最近后" not in cleaned


def test_product_experience_odd_phrase_cleanup_generalizes_specific_disease():
    cleaned = sanitize_odd_product_experience_phrases("学校又是小状况又是手足口，我真是肉疼。")

    assert cleaned == "学校又是小状况又是班里请假，我真是肉疼"
    assert "手足口" not in cleaned


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
    assert "眼睛有点累" in review.wangyue_article_logic_drift_hits
    assert "给他泡了杯" in review.wangyue_article_logic_drift_hits
    assert "奶粉罐" in review.wangyue_article_logic_drift_hits
    assert "看绘本" in review.wangyue_article_logic_drift_hits
    assert "动画片" in review.wangyue_article_logic_drift_hits
    assert "揉眼睛" in review.wangyue_article_logic_drift_hits
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
    assert "给娃试了" in product_path_review.wangyue_article_logic_drift_hits
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
    assert "主要是看皇家美素佳儿旺玥的保护力这块" in cleaned


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
    assert "精力足" in review.wangyue_growth_nutrition_drift_hits
    assert "活力满满" in review.wangyue_growth_nutrition_drift_hits
    assert "跑来跑去" in review.wangyue_growth_nutrition_drift_hits
    assert "成长力" in review.wangyue_growth_nutrition_drift_hits
    assert "成长有底" in review.wangyue_growth_nutrition_drift_hits
    assert "成长不掉队" in review.wangyue_growth_nutrition_drift_hits
    assert "空罐" in review.wangyue_growth_nutrition_drift_hits
    assert "试了段时间" in review.wangyue_growth_nutrition_drift_hits
    assert "状态还行" in review.wangyue_growth_nutrition_drift_hits
    assert "囤货" in review.wangyue_growth_nutrition_drift_hits
    assert "微量元素" in review.wangyue_growth_nutrition_drift_hits
    assert "跑几步就喊累" in review.wangyue_growth_nutrition_drift_hits
    assert "开始喝旺玥" in review.wangyue_growth_nutrition_drift_hits
    assert "图个方便" in review.wangyue_growth_nutrition_drift_hits
    assert "甩了旺玥的链接" in review.wangyue_growth_nutrition_drift_hits
    assert "链接" in review.wangyue_growth_nutrition_drift_hits
    assert "囤几罐" in review.wangyue_growth_nutrition_drift_hits
    assert "继续买这个" in review.wangyue_growth_nutrition_drift_hits
    assert "带了一罐" in review.wangyue_growth_nutrition_drift_hits
    assert "罐子放回包" in review.wangyue_growth_nutrition_drift_hits
    assert "留着明天喝" in review.wangyue_growth_nutrition_drift_hits
    assert "眼睛和身体状态" in review.wangyue_growth_nutrition_drift_hits
    assert any("三岁" in hit for hit in review.wangyue_explicit_age_hits)


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


def test_wangyue_context_cleanup_generalizes_weaning_context():
    cleaned = sanitize_wangyue_context_phrases("从断奶开始就一直在纠结选哪个儿童奶粉。")

    assert cleaned == "孩子大点后就一直在纠结选哪个儿童奶粉"
    assert "断奶" not in cleaned


def test_wangyue_context_cleanup_generalizes_two_year_old_context():
    cleaned = sanitize_wangyue_context_phrases("两岁后开始接触小朋友多的地方。")

    assert cleaned == "孩子大点后开始接触小朋友多的地方"
    assert "两岁" not in cleaned


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
    assert sanitize_odd_product_experience_phrases("正好家里有皇家美素佳儿旺玥。") == "正好留意到皇家美素佳儿旺玥"
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

    assert cleaned == "挑食娃的妈妈发现旺玥营养挺全的，保护力都提到了，选了旺玥后看着比同龄人结实，请假多的时候这罐奶粉钱也省了"
    review = review_product_experience_phrase(
        title="旺玥记录",
        body=text,
        plan={
            "rule_type": "business_rule",
            "asset_key": "wangyue_article_business_rules",
            "corpus": "写作规则：0705旺玥活动。",
        },
    )
    assert set(review.odd_phrase_hits) == {"挑食宝宝", "宝妈", "体质明显比同龄人稳", "自护力", "内护力", "底气", "抵抗力", "换了旺玥", "流感多的时候", "羊奶粉钱"}
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
    )

    assert "喝儿童成长奶粉的话" not in candidates
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
    ]

    for title in bad_titles:
        assert "awkward_title_pattern" in _title_guard_reasons(title, set())

    assert _title_guard_reasons("孩子奶粉还没定", set()) == []
    assert _title_guard_reasons("最近还在喝旺玥", set()) == []


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
    assert "儿童奶粉先这样选" not in titles
    assert "这罐先继续喝" not in titles
    assert "选儿童奶粉这事" not in titles
    assert "儿童成长奶粉小记录" not in titles
    assert "保护力这块我会多看一眼" not in titles
    assert any("forbidden_title_phrase:4段" in repair["reasons"] for item in items for repair in item.quality_json["title_guard_repairs"])
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
                "title": "感冒季这阵旺玥没断",
                "body": "幼儿园接触人多，我还是担心孩子容易中招。天气忽冷忽热时，家里一直喝旺玥，支持保护力，希望这学期少操点心。",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        return await super().invoke(invoke_url=invoke_url, envelope=envelope, executor_token=executor_token)


class ShortArticleLengthRewriteClient(RuntimeFastDraftReviewClient):
    async def invoke(self, *, invoke_url: str, envelope: dict, executor_token: str | None = None) -> InvokeResult:
        if envelope.get("capability") == "content.generate":
            output = {
                "title": "对比了一堆还是选了旺玥",
                "body": "乳铁蛋白含量高的奶粉，对比了一堆还是选了旺玥",
                "runtime_result": {"mode": "runtime_fast"},
            }
            return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
        if envelope.get("capability") == "content.rewrite":
            input_payload = envelope.get("input") or {}
            if input_payload.get("rewrite_source") == "article_length_guard":
                output = {
                    "title": "对比了一堆还是选了旺玥",
                    "body": "对比了一堆儿童奶粉，最后还是选了旺玥。主要看中乳铁蛋白和日常保护力，孩子愿意喝，我就先定下来了。",
                    "runtime_result": {"mode": "content_rewrite_runtime"},
                }
                return InvokeResult(mode="sync", stage_call_id=envelope["stage_call_id"], output=output, stats={"fake": True})
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
                "body": "给孩子选皇家美素佳儿旺玥儿童奶粉，主要是想补充营养、支持成长。喝奶动作不展开，就按儿童奶粉这块记一下。",
                "final": {
                    "title": "给娃喝奶粉的日常小记录",
                    "body": "给孩子选皇家美素佳儿旺玥儿童奶粉，主要是想补充营养、支持成长。喝奶动作不展开，就按儿童奶粉这块记一下。",
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
                "body": "给孩子选皇家美素佳儿旺玥儿童奶粉，我主要是想把成长阶段的营养认真顾到。看下来营养配得比较全，也符合我对日常成长支持的期待。",
                "final": {
                    "title": "给孩子选旺玥这事",
                    "body": "给孩子选皇家美素佳儿旺玥儿童奶粉，我主要是想把成长阶段的营养认真顾到。看下来营养配得比较全，也符合我对日常成长支持的期待。",
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
                    "body": "给孩子选皇家美素佳儿旺玥儿童奶粉，主要还是想把成长阶段的营养认真顾到。别的先不展开，适合现阶段就行。",
                    "final": {
                        "title": "给孩子选奶粉这事",
                        "body": "给孩子选皇家美素佳儿旺玥儿童奶粉，主要还是想把成长阶段的营养认真顾到。别的先不展开，适合现阶段就行。",
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
                "body": "给孩子选皇家美素佳儿旺玥儿童奶粉，主要还是看成长阶段营养能不能顾到，配方该有的都有，喝着也挺合适。",
                "final": {
                    "title": "给孩子选奶粉这事",
                    "body": "给孩子选皇家美素佳儿旺玥儿童奶粉，主要还是看成长阶段营养能不能顾到，配方该有的都有，喝着也挺合适。",
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
    assert "感冒季" not in full_text
    assert "天气忽冷忽热" not in full_text
    assert "天气一变" not in full_text
    assert "学期" not in full_text
    assert "product_experience_temporal_context_cleanups" in item.quality_json
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    assert sum(1 for stage in stage_calls if stage.capability == "content.rewrite") == 0


@pytest.mark.asyncio
async def test_batch_execution_repairs_short_wangyue_article_to_min_length():
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
            invocation_client=ShortArticleLengthRewriteClient(),
            callback_base_url="http://maga.test/api/v1/executor",
            session_factory=session_factory,
        )
        result = await service.execute_batch_items(job.id, limit=1, created_by="test")
        await session.commit()

    assert result.generated_count == 1
    async with session_factory() as session:
        item = (await session.execute(select(ContentBatchItem))).scalar_one()
        stage_calls = (await session.execute(select(ContentAgentStageCall))).scalars().all()

    assert len(item.body) >= 40
    assert item.quality_json["article_length_guard"]["status"] == "passed"
    assert item.quality_json["review_report"]["rewrite_required"] is False
    assert sum(1 for stage in stage_calls if stage.capability == "content.rewrite") >= 2


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
    assert sum(1 for stage in stage_calls if stage.capability == "content.rewrite") == 2


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
    assert "给孩子选皇家美素佳儿旺玥儿童奶粉" in full_text
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
    assert len(rewrite_stages) == 2
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
    assert "给孩子选皇家美素佳儿旺玥儿童奶粉" in full_text
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
    assert "给孩子选皇家美素佳儿旺玥儿童奶粉" in full_text
    assert "product_experience_growth_nutrition_fallback_cleanups" in item.quality_json
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    assert sum(1 for stage in stage_calls if stage.capability == "content.rewrite") == 2


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
    assert "旺玥真实体验分享" not in item.title
    assert "title_guard_repairs" in item.quality_json
    assert "product_experience_wangyue_context_cleanups" in item.quality_json
    assert item.quality_json["product_experience_phrase_guard"]["pass"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is False
    assert sum(1 for stage in stage_calls if stage.capability == "content.rewrite") == 0


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
