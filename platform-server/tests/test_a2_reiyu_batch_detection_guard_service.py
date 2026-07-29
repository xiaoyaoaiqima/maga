from app.services.a2_reiyu_batch_detection_guard_service import review_a2_reiyu_batch_detection_fact


PLAN = {"asset_key": "a2_reiyu_ugc_post_rules_v1"}


def test_batch_detection_guard_blocks_per_can_fact_expansion() -> None:
    every_can = review_a2_reiyu_batch_detection_fact(
        title="批次检测",
        body="a2至初现在每批都有检测，每罐都查，做事挺认真。",
        plan=PLAN,
    )
    one_can_one_test = review_a2_reiyu_batch_detection_fact(
        title="批次检测",
        body="a2至初坚持一罐一检，标准确实高。",
        plan=PLAN,
    )

    assert every_can.pass_ is False
    assert "每罐都查" in every_can.hits[0]
    assert one_can_one_test.pass_ is False
    assert "一罐一检" in one_can_one_test.hits[0]


def test_batch_detection_guard_blocks_unsupported_process_detail() -> None:
    review = review_a2_reiyu_batch_detection_fact(
        title="批次检测",
        body="a2至初现在每批都有检测，从奶源到罐装都查一遍。",
        plan=PLAN,
    )

    assert review.pass_ is False
    assert review.issue_code == "batch_detection_fact_error"
    assert "从奶源到罐装都查一遍" in review.hits[0]


def test_batch_detection_guard_allows_can_code_used_for_detection_lookup() -> None:
    review = review_a2_reiyu_batch_detection_fact(
        title="批次检测",
        body="a2至初现在每批都有检测，扫罐码就能看到信息。",
        plan=PLAN,
    )

    assert review.pass_ is True


def test_batch_detection_guard_allows_can_code_collection_and_bottom_code_report_lookup() -> None:
    review = review_a2_reiyu_batch_detection_fact(
        title="扫码参加活动",
        body="买完奶粉扫罐码集罐，扫罐底码可以看对应批次的检测报告。",
        plan=PLAN,
    )

    assert review.pass_ is True


def test_batch_detection_guard_allows_batch_detection_and_report_lookup() -> None:
    strict_batch = review_a2_reiyu_batch_detection_fact(
        title="批次检测",
        body="a2至初现在每批都有检测，批次检测做得挺严格，我看着更安心。",
        plan=PLAN,
    )
    report_lookup = review_a2_reiyu_batch_detection_fact(
        title="查报告",
        body="扫罐底码可以查对应批次的检测报告，每罐都能查到报告。",
        plan=PLAN,
    )

    assert strict_batch.pass_ is True
    assert report_lookup.pass_ is True


def test_batch_detection_guard_allows_per_can_traceability_wording() -> None:
    for body in (
        "扫罐底码可以查对应批次报告，每一罐都能查到报告。",
        "扫罐底码能看到每罐来源，每一罐都能溯源。",
    ):
        review = review_a2_reiyu_batch_detection_fact(
            title="查报告和溯源",
            body=body,
            plan=PLAN,
        )
        assert review.pass_ is True


def test_batch_detection_guard_blocks_direct_effect_causality() -> None:
    review = review_a2_reiyu_batch_detection_fact(
        title="批次检测",
        body="a2至初现在每批都有检测，怪不得宝宝喝了以后长肉快。",
        plan=PLAN,
    )

    assert review.pass_ is False
    assert review.issue_code == "batch_detection_effect_causality"
    assert "怪不得" in review.hits[0]


def test_batch_detection_guard_blocks_cross_sentence_effect_causality() -> None:
    review = review_a2_reiyu_batch_detection_fact(
        title="批次检测",
        body="a2至初现在每批都有检测。难怪一直喝着放心，宝宝肚肚舒服得很。",
        plan=PLAN,
    )

    assert review.pass_ is False
    assert review.issue_code == "batch_detection_effect_causality"
    assert "每批都有检测。难怪" in review.hits[0]


def test_batch_detection_guard_blocks_every_batch_variant_with_intervening_report_sentence() -> None:
    review = review_a2_reiyu_batch_detection_fact(
        title="批次检测",
        body=(
            "a2至初现在每一批都会做检测。"
            "我扫罐底码看了报告，显示未检出。"
            "难怪宝宝最近胃口好、长肉快。"
        ),
        plan=PLAN,
    )

    assert review.pass_ is False
    assert review.issue_code == "batch_detection_effect_causality"
    assert "每一批都会做检测" in review.hits[0]
    assert "难怪宝宝最近胃口好" in review.hits[0]


def test_batch_detection_guard_blocks_detection_as_cause_of_acceptance() -> None:
    review = review_a2_reiyu_batch_detection_fact(
        title="批次检测",
        body="a2至初现在每一批都会检测。报告也能查。难怪宝宝转回来后爱喝。",
        plan=PLAN,
    )

    assert review.pass_ is False
    assert review.issue_code == "batch_detection_effect_causality"
    assert "难怪宝宝转回来后爱喝" in review.hits[0]


def test_batch_detection_guard_allows_recognition_then_separate_usage_experience() -> None:
    separate_sentence = review_a2_reiyu_batch_detection_fact(
        title="批次检测",
        body="a2至初现在每批都有检测，a2做事挺认真。我家喝了一阵，宝宝小脸慢慢圆了。",
        plan=PLAN,
    )
    recognition_bridge = review_a2_reiyu_batch_detection_fact(
        title="批次检测",
        body="a2至初现在每批都有检测，所以我更安心，宝宝喝了一阵小脸也圆了。",
        plan=PLAN,
    )

    assert separate_sentence.pass_ is True
    assert recognition_bridge.pass_ is True


def test_batch_detection_guard_ignores_other_assets() -> None:
    review = review_a2_reiyu_batch_detection_fact(
        title="其他活动",
        body="每罐都查。",
        plan={"asset_key": "other_asset"},
    )

    assert review.pass_ is True
