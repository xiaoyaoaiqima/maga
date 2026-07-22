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


def test_old_can_guard_does_not_block_stock_without_collection_link() -> None:
    review = review_a2_reiyu_old_can_eligibility(
        title="长期喝的口粮",
        body="家里刚囤了一箱，最近冲泡还是很顺。",
        plan=PLAN,
    )

    assert review.pass_ is True
