from app.services.a2_reiyu_text_guard_service import review_a2_reiyu_text_surface


PLAN = {"asset_key": "a2_reiyu_ugc_post_rules_v1"}


def test_text_guard_blocks_uppercase_brand_but_allows_a2_protein() -> None:
    uppercase_brand = review_a2_reiyu_text_surface(
        title="A2老粉福利",
        body="家里一直喝a2至初。",
        plan=PLAN,
    )
    ingredient = review_a2_reiyu_text_surface(
        title="a2老粉福利",
        body="a2至初主打A2蛋白。",
        plan=PLAN,
    )

    assert uppercase_brand.pass_ is False
    assert uppercase_brand.issue_code == "brand_case_error"
    assert ingredient.pass_ is True


def test_text_guard_does_not_hardcode_corpus_tone_wording() -> None:
    review = review_a2_reiyu_text_surface(
        title="a2活动分享",
        body="a2确实在用心建立信任。",
        plan=PLAN,
    )

    assert review.pass_ is True


def test_text_guard_blocks_claimed_lottery_win_in_title() -> None:
    review = review_a2_reiyu_text_surface(
        title="新西兰旅游大奖抽到啦",
        body="抽奖里有新西兰旅游大奖。",
        plan=PLAN,
    )

    assert review.pass_ is False
    assert review.issue_code == "fabricated_reward_experience"
    assert "抽到" in review.hits[0]


def test_text_guard_allows_hypothetical_or_third_party_lottery_results() -> None:
    for body in (
        "要是中了奖，带娃去新西兰看牧场。",
        "希望能抽到旅游大奖。",
        "听说朋友抽中了金手链。",
        "我还没中奖，就当试试手气。",
    ):
        review = review_a2_reiyu_text_surface(title="a2抽奖活动", body=body, plan=PLAN)
        assert review.pass_ is True


def test_text_guard_allows_claimed_deterministic_member_benefits() -> None:
    for title, body in (
        ("a2至初小听拿到手", "老客还能领小听。"),
        ("a2老客礼领到了", "我领到了老客回归礼。"),
        ("a2会员权益", "这次权益也拿到了。"),
        ("a2集罐换礼", "攒够后换来的自行车很实用。"),
    ):
        review = review_a2_reiyu_text_surface(title=title, body=body, plan=PLAN)
        assert review.pass_ is True


def test_text_guard_allows_reward_rule_without_claiming_receipt() -> None:
    review = review_a2_reiyu_text_surface(
        title="集罐可以换自行车",
        body="集6罐可以换自行车，活动挺实在。",
        plan=PLAN,
    )

    assert review.pass_ is True


def test_text_guard_allows_comparing_deterministic_exchange_with_lottery() -> None:
    review = review_a2_reiyu_text_surface(
        title="集罐兑换更实在",
        body="集12罐直接换一罐奶粉，这不比中奖靠谱多了。",
        plan=PLAN,
    )

    assert review.pass_ is True


def test_text_guard_blocks_one_box_as_equivalent_to_twelve_can_threshold() -> None:
    for body in (
        "集12罐就能换1罐，一箱差不多就够。",
        "集满12个罐子可以兑一罐奶粉。整箱刚好是12罐。",
        "12罐换1罐挺实在的，一箱能凑够12罐。",
    ):
        review = review_a2_reiyu_text_surface(title="a2至初集罐礼", body=body, plan=PLAN)
        assert review.pass_ is False
        assert review.severity == "hard"
        assert review.business_usability_tier == "hold_out"
        assert review.issue_code == "activity_quantity_error"


def test_text_guard_allows_box_purchase_without_twelve_can_equivalence() -> None:
    for body in (
        "集12罐就能换1罐，活动期间打算再补一箱。",
        "12罐换1罐挺实在的，一箱差不多够家里喝一个月。",
        "一箱就先喝着，按活动规则集够12罐再换1罐。",
    ):
        review = review_a2_reiyu_text_surface(title="a2至初集罐礼", body=body, plan=PLAN)
        assert review.pass_ is True


def test_text_guard_blocks_unsupported_activity_benefit_claims() -> None:
    for body in (
        "多重福利一起上，又是积分翻倍又是专属赠品。",
        "这次会员活动有双倍积分，还有会员专属礼品。",
    ):
        review = review_a2_reiyu_text_surface(title="a2至初会员活动", body=body, plan=PLAN)
        assert review.pass_ is False
        assert review.severity == "hard"
        assert review.business_usability_tier == "hold_out"
        assert review.issue_code == "fabricated_activity_benefit"


def test_text_guard_allows_confirmed_generic_activity_mechanisms() -> None:
    review = review_a2_reiyu_text_surface(
        title="a2至初会员活动",
        body="下单会累计积分，积分按会员规则兑换礼品。还有抽奖、集罐兑换和老客回馈礼。",
        plan=PLAN,
    )

    assert review.pass_ is True


def test_text_guard_marks_dense_positive_expression_stacking_for_rewrite() -> None:
    review = review_a2_reiyu_text_surface(
        title="a2至初会员升级",
        body=(
            "而且现在a2至初每批都有检测，品质更透明了。"
            "品控在线，质量稳定，标准高，细节到位，诚意满满，让人信服。"
        ),
        plan=PLAN,
    )

    assert review.pass_ is False
    assert review.severity == "rewrite"
    assert review.business_usability_tier == "light_fix_usable"
    assert review.issue_code == "positive_expression_stacking"
    assert review.rewrite_required is True
    assert "品控在线" in review.hits[0]


def test_text_guard_marks_prompt_instruction_leakage_for_rewrite() -> None:
    review = review_a2_reiyu_text_surface(
        title="a2至初会员积分",
        body="活动福利挺实用。再另起一段，最后自然表达对a2的认可。",
        plan=PLAN,
    )

    assert review.pass_ is False
    assert review.issue_code == "prompt_instruction_leakage"
    assert review.rewrite_required is True


def test_text_guard_marks_birth_continuity_and_transfer_history_conflict() -> None:
    for body in (
        "我家娃从出生就喝a2至初，转奶也顺利，无缝衔接。",
        "我家娃从出生就喝这个，清淡不腥。后来转奶很顺利。",
    ):
        review = review_a2_reiyu_text_surface(title="a2至初活动分享", body=body, plan=PLAN)
        assert review.pass_ is False
        assert review.issue_code == "narrative_consistency"
        assert review.business_usability_tier == "light_fix_usable"
        assert review.rewrite_required is True


def test_text_guard_blocks_birth_continuity_when_product_is_named_before_it() -> None:
    review = review_a2_reiyu_text_surface(
        title="a2至初老客分享",
        body="我本来就是a2至初老用户，从娃出生就一直喝。转奶那会儿也特别顺利。",
        plan=PLAN,
    )

    assert review.pass_ is False
    assert review.issue_code == "narrative_consistency"


def test_text_guard_allows_continued_use_after_prior_transfer() -> None:
    review = review_a2_reiyu_text_surface(
        title="a2至初老客分享",
        body="我家一直喝a2至初，宝宝当时喝这个转奶挺顺利，适应得也快。",
        plan=PLAN,
    )

    assert review.pass_ is True


def test_text_guard_blocks_mom_as_drinker_and_malformed_return_wording() -> None:
    mom_as_drinker = review_a2_reiyu_text_surface(
        title="a2至初老客分享",
        body="我自己喝下来感受就是，粉质挺细腻。",
        plan=PLAN,
    )
    malformed_return = review_a2_reiyu_text_surface(
        title="a2老客回归礼",
        body="活动挺简单，老客回去就能领个小听粉。",
        plan=PLAN,
    )

    assert mom_as_drinker.pass_ is False
    assert mom_as_drinker.issue_code == "malformed_text"
    assert malformed_return.pass_ is False
    assert malformed_return.issue_code == "malformed_text"


def test_text_guard_blocks_brand_retention_summary_tone() -> None:
    review = review_a2_reiyu_text_surface(
        title="a2至初会员活动",
        body="感觉品牌是真的想让我们这些老顾客留下来。",
        plan=PLAN,
    )

    assert review.pass_ is False
    assert review.issue_code == "corporate_summary_tone"


def test_text_guard_marks_known_malformed_article_text() -> None:
    for body in (
        "这牌子经得起研究，我反正是值得长期回购了。",
        "品实用价值感在线，完全不是走过场。",
    ):
        review = review_a2_reiyu_text_surface(title="a2至初活动分享", body=body, plan=PLAN)
        assert review.pass_ is False
        assert review.issue_code == "malformed_text"
        assert review.business_usability_tier == "light_fix_usable"
        assert review.rewrite_required is True


def test_text_guard_marks_adjacent_positive_expression_stacking_for_rewrite() -> None:
    review = review_a2_reiyu_text_surface(
        title="a2这活动挺实在",
        body=(
            "品质在线，质量稳定，标准高，做得认真，让人信服。"
            "a2确实诚意满满，细节到位。"
            "这种透明放心的感觉挺好。"
        ),
        plan=PLAN,
    )

    assert review.pass_ is False
    assert review.issue_code == "positive_expression_stacking"


def test_text_guard_marks_dense_product_experience_stacking_for_rewrite() -> None:
    review = review_a2_reiyu_text_surface(
        title="a2至初活动分享",
        body=(
            "a2至初清淡不腥，淡淡奶香，不甜腻，好冲泡不挂壁，"
            "粉质细腻，宝宝每次都喝光，转奶顺利。"
        ),
        plan=PLAN,
    )

    assert review.pass_ is False
    assert review.issue_code == "positive_expression_stacking"


def test_text_guard_allows_natural_positive_expressions_without_dense_stacking() -> None:
    review = review_a2_reiyu_text_surface(
        title="a2这活动有点意思",
        body="真心觉得他们做得认真，标准高，细节也到位，买着放心。",
        plan=PLAN,
    )
    separated = review_a2_reiyu_text_surface(
        title="a2活动分享",
        body="品控在线。质量稳定。标准高。细节到位。诚意满满。",
        plan=PLAN,
    )

    assert review.pass_ is True
    assert separated.pass_ is True


def test_text_guard_allows_five_in_one_sentence_and_seven_in_window() -> None:
    five_in_one = review_a2_reiyu_text_surface(
        title="a2活动分享",
        body="品质在线，质量稳定，标准高，细节到位，做得认真。",
        plan=PLAN,
    )
    seven_in_window = review_a2_reiyu_text_surface(
        title="a2活动分享",
        body=(
            "品质在线，质量稳定，标准高。"
            "细节到位，做得认真。"
            "诚意满满，让人信服。"
        ),
        plan=PLAN,
    )

    assert five_in_one.pass_ is True
    assert seven_in_window.pass_ is True
