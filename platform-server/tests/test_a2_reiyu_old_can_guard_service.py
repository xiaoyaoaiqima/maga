from app.services.a2_reiyu_old_can_guard_service import review_a2_reiyu_old_can_eligibility


PLAN = {"asset_key": "a2_reiyu_ugc_post_rules_v1"}


def test_old_can_guard_blocks_existing_home_stock_linked_to_collection() -> None:
    same_sentence = review_a2_reiyu_old_can_eligibility(
        title="集罐活动",
        body="集满3罐就能换小车车，正好家里刚囤了一箱，娃天天催我扫码。",
        plan=PLAN,
    )
    cross_sentence = review_a2_reiyu_old_can_eligibility(
        title="集罐活动",
        body="家里正好存了几罐。现在集3罐就能换小车车。",
        plan=PLAN,
    )

    assert same_sentence.pass_ is False
    assert "家里刚囤了一箱" in same_sentence.hits[0]
    assert cross_sentence.pass_ is False
    assert "家里正好存了几罐" in cross_sentence.hits[0]


def test_old_can_guard_allows_future_or_activity_period_purchase() -> None:
    future_restock = review_a2_reiyu_old_can_eligibility(
        title="集罐活动",
        body="刚好家里又该补货了，活动期间买完后扫罐码累计，集3罐可以换小车车。",
        plan=PLAN,
    )
    activity_purchase = review_a2_reiyu_old_can_eligibility(
        title="集罐活动",
        body="活动期间买好几罐，买完奶粉扫罐码集罐。",
        plan=PLAN,
    )

    assert future_restock.pass_ is True
    assert activity_purchase.pass_ is True


def test_old_can_guard_blocks_collecting_old_cans_for_the_activity() -> None:
    review = review_a2_reiyu_old_can_eligibility(
        title="a2集罐活动",
        body="回家立马把旧罐子收拾了一下，参加活动集够数就能换。",
        plan=PLAN,
    )

    assert review.pass_ is False
    assert "旧罐子" in review.hits[0]


def test_old_can_guard_blocks_finishing_existing_box_then_collecting() -> None:
    review = review_a2_reiyu_old_can_eligibility(
        title="集罐换自行车",
        body=(
            "刷pyq看到a2至初有新活动，集6罐可以兑换自行车。"
            "正好家里快喝完一箱，感觉能攒一攒。"
        ),
        plan=PLAN,
    )

    assert review.pass_ is False
    assert "家里快喝完一箱" in review.hits[0]


def test_old_can_guard_blocks_finished_home_cans_linked_to_immediate_participation() -> None:
    review = review_a2_reiyu_old_can_eligibility(
        title="集罐换自行车",
        body="集6罐就能兑自行车，正好家里喝完好几罐，直接参加不费劲。",
        plan=PLAN,
    )

    assert review.pass_ is False
    assert "家里喝完好几罐" in review.hits[0]


def test_old_can_guard_does_not_block_stock_without_collection_link() -> None:
    stocked = review_a2_reiyu_old_can_eligibility(
        title="长期喝的口粮",
        body="家里刚囤了一箱，最近冲泡还是很顺。",
        plan=PLAN,
    )
    nearly_finished = review_a2_reiyu_old_can_eligibility(
        title="长期喝的口粮",
        body="家里快喝完一箱了，最近冲泡还是很顺。",
        plan=PLAN,
    )

    assert stocked.pass_ is True
    assert nearly_finished.pass_ is True


def test_old_can_guard_blocks_existing_stock_even_when_collection_is_several_sentences_away() -> None:
    review = review_a2_reiyu_old_can_eligibility(
        title="集罐换婴儿车",
        body=(
            "集18罐可以换婴儿车。活动页面还提到每批都有检测。"
            "粉质细腻，冲泡也方便。家里已经囤了好几箱了。"
        ),
        plan=PLAN,
    )

    assert review.pass_ is False
    assert "家里已经囤了好几箱" in review.hits[0]


def test_old_can_guard_allows_natural_collect_wording_but_blocks_habitual_stock_link() -> None:
    natural_collect_wording = review_a2_reiyu_old_can_eligibility(
        title="集罐换小车车",
        body="集3罐能换小车车，攒几个罐子就能换。",
        plan=PLAN,
    )
    habitual_stock = review_a2_reiyu_old_can_eligibility(
        title="集罐换奶粉",
        body="集12罐能换奶粉，平时囤货正好能用上。",
        plan=PLAN,
    )

    assert natural_collect_wording.pass_ is True
    assert habitual_stock.pass_ is False


def test_old_can_guard_allows_collecting_toward_a_future_reward() -> None:
    review = review_a2_reiyu_old_can_eligibility(
        title="a2集罐换礼",
        body="攒一攒就能给娃兑礼物，这个活动还挺实在的。",
        plan=PLAN,
    )

    assert review.pass_ is True


def test_old_can_guard_keeps_future_restock_wording() -> None:
    review = review_a2_reiyu_old_can_eligibility(
        title="集罐换小车车",
        body="集3罐能换小车车，正好最近要囤货。",
        plan=PLAN,
    )

    assert review.pass_ is True


def test_old_can_guard_does_not_treat_future_purchase_as_existing_stock() -> None:
    review = review_a2_reiyu_old_can_eligibility(
        title="集罐换小车车",
        body="活动期间准备买好几罐a2至初，买完按规则扫码集罐。",
        plan=PLAN,
    )

    assert review.pass_ is True


def test_old_can_guard_allows_past_activity_threshold_comparison() -> None:
    review = review_a2_reiyu_old_can_eligibility(
        title="集罐换奶粉",
        body="以前这些活动都是集3罐、集6罐换小礼品，这次集12罐能换奶粉。",
        plan=PLAN,
    )

    assert review.pass_ is True
