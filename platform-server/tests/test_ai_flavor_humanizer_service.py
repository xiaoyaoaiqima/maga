"""Tests for the post-generation AI-flavor humanizer review."""

from app.services.ai_flavor_humanizer_service import review_ai_flavor


def test_ai_flavor_review_flags_product_claim_title_and_audit_fence_body():
    review = review_ai_flavor(
        title="拼图那阵，选奶看了眼脑",
        body="之前挑奶粉时对比过几款，旺玥有DHA和燕窝酸。不是要说喝了怎么样，就是日常选择里多一层考虑。",
        plan={"post_type": "选奶选择复盘型"},
    )

    assert review.rewrite_required is True
    assert "title_exposes_product_claim_or_summary" in review.reasons
    assert "audit_fence_phrase" in review.reasons
    assert "title_to_life_entry" in review.rewrite_operations
    assert "remove_audit_fence" in review.rewrite_operations


def test_ai_flavor_review_flags_compliance_uncertainty_as_audit_fence():
    review = review_ai_flavor(
        title="放学后没电的娃",
        body=(
            "后来看别人说日常营养支持也挺重要，就顺手把旺玥加进来了，当个日常安排。"
            "目前还在观察，说不上有没有用，反正他喝得还行，不抗拒。"
            "其他该调的还在调，不能指望一罐奶粉全解决。"
        ),
        plan={"post_type": "问题解决型"},
    )

    assert review.rewrite_required is True
    assert "audit_fence_phrase" in review.reasons
    assert "remove_audit_fence" in review.rewrite_operations
    assert any("目前还在观察" in hit for hit in review.body_hits)
    assert any("说不上有没有用" in hit for hit in review.body_hits)
    assert any("不能指望一罐奶粉" in hit for hit in review.body_hits)


def test_ai_flavor_review_flags_followup_observation_closure():
    review = review_ai_flavor(
        title="饭桌拉锯战",
        body="旺玥这款是我对比过营养表之后选出的，钙铁锌和几种关键营养都在，后续再观察着看吧。",
        plan={"post_type": "问题解决型"},
    )

    assert review.rewrite_required is True
    assert "audit_fence_phrase" in review.reasons
    assert any("后续再观察着看吧" in hit for hit in review.body_hits)


def test_ai_flavor_review_flags_magic_key_disclaimer():
    review = review_ai_flavor(
        title="绿叶菜又翻车了",
        body="旺玥就看中它钙铁锌和关键营养都在。奶粉只是日常补充，不是万能钥匙，我心里有数。",
        plan={"post_type": "问题解决型"},
    )

    assert review.rewrite_required is True
    assert "audit_fence_phrase" in review.reasons
    assert any("不是万能钥匙" in hit for hit in review.body_hits)


def test_ai_flavor_review_flags_risk_effect_title():
    review = review_ai_flavor(
        title="我也没指望喝了就不中招",
        body="娃刚入园那阵，接触的小朋友多，我就开始琢磨儿童奶粉这块。",
        plan={"post_type": "选奶选择复盘型"},
    )

    assert review.rewrite_required is True
    assert "不中招" in review.title_hits
    assert "title_to_life_entry" in review.rewrite_operations


def test_ai_flavor_review_allows_formula_as_human_selection_action_title():
    review = review_ai_flavor(
        title="入园后看配方，纠结",
        body="娃入园后接触的人一下子多了，当妈的心里会多想一步。选儿童奶粉那阵子，翻了好多配方表。",
        plan={"post_type": "选奶选择复盘型"},
    )

    assert review.rewrite_required is False
    assert review.pass_ is True


def test_ai_flavor_review_flags_formula_when_bound_to_marketing_summary_title():
    review = review_ai_flavor(
        title="配方全面，营养更安心",
        body="娃入园后接触的人一下子多了，当妈的心里会多想一步。",
        plan={"post_type": "选奶选择复盘型"},
    )

    assert review.rewrite_required is True
    assert "title_exposes_product_claim_or_summary" in review.reasons


def test_ai_flavor_review_flags_overdense_selection_review():
    review = review_ai_flavor(
        title="吃饭这事，绿叶菜好难",
        body=(
            "孩子最近挑食明显，绿叶菜基本不碰，我选儿童奶粉时就会看营养这块。"
            "旺玥里DHA、HMO、燕窝酸、乳铁蛋白、钙铁锌这些都有，关键营养也写得清楚，"
            "所以日常选择里算是多一层考虑。后来我又看了配方和成分，觉得这个方向还行，"
            "至少营养上有个托底，平时吃饭不稳定的时候，当妈的总会想多安排一点。"
        ),
        plan={"post_type": "选奶选择复盘型"},
    )

    assert review.rewrite_required is True
    assert "marketing_density" in review.reasons
    assert "keep_one_product_basis" in review.rewrite_operations


def test_ai_flavor_review_flags_overexplained_title_logic():
    review = review_ai_flavor(
        title="3岁后选奶，我认真看了阶段",
        body="娃一过3岁，衣服鞋子半年一换，我就想儿童奶粉这块是不是该认真挑一下。",
        plan={"post_type": "选奶选择复盘型"},
    )

    assert review.rewrite_required is True
    assert "title_overexplains_post_logic" in review.reasons
    assert "title_to_lower_obligation_fragment" in review.rewrite_operations


def test_ai_flavor_review_flags_stage_changed_title_logic():
    review = review_ai_flavor(
        title="3岁后选奶，阶段变了",
        body="孩子大一点后活动量多了，我开始关注学龄前营养怎么跟得上。",
        plan={"post_type": "选奶选择复盘型"},
    )

    assert review.rewrite_required is True
    assert "title_overexplains_post_logic" in review.reasons


def test_ai_flavor_review_flags_overcomplete_summary_closure():
    review = review_ai_flavor(
        title="西兰花小拼图",
        body=(
            "晚饭桌上又只剩菜叶了，娃把西兰花一粒粒挑出来摆在碗边。"
            "后来选儿童奶粉，我就想着日常营养能不能兜个底，旺玥是看营养表觉得比较全。"
            "不过吃饭还是老样子，不会因为喝奶粉就突然爱吃菜了。"
            "只能说有个奶粉顶着，我心里没那么慌。蔬菜战斗还得继续。不算满分推荐，每家情况不一样吧。"
        ),
        plan={"post_type": "选奶选择复盘型"},
    )

    assert review.rewrite_required is True
    assert "overcomplete_summary_closure" in review.reasons
    assert "loosen_or_remove_summary_closure" in review.rewrite_operations


def test_ai_flavor_review_flags_soft_summary_combo_without_hard_recommendation():
    review = review_ai_flavor(
        title="晚饭桌上的绿叶菜",
        body=(
            "晚饭桌上的绿叶菜，推来推去，最后凉掉。"
            "选儿童奶粉那会儿我特意看了下日常营养，菜吃不好，钙铁锌总得有个底。"
            "旺玥的30多种营养和钙铁锌配得还行，口味淡，孩子试了接受，就一直喝着。"
            "现在菜叶子还是会剩。没想靠一杯奶解决挑食，就是觉得有个底，心里稳点。"
        ),
        plan={"post_type": "选奶选择复盘型"},
    )

    assert review.rewrite_required is True
    assert "overcomplete_summary_closure" in review.reasons


def test_ai_flavor_review_allows_life_entry_with_one_product_basis():
    review = review_ai_flavor(
        title="最近迷上拼图",
        body=(
            "最近她迷上拼图，能趴在桌边折腾半天，眼睛离得近我就会提醒一句。"
            "也是那阵子，我把旺玥留下来，里面有 DHA 和燕窝酸，奶里顺带有这些我就不用额外折腾。"
        ),
        plan={"post_type": "选奶选择复盘型"},
    )

    assert review.rewrite_required is False
    assert review.pass_ is True


def test_ai_flavor_review_allows_positive_single_product_basis():
    review = review_ai_flavor(
        title="又补了一罐",
        body=(
            "晚饭后顺手把旺玥加进购物车。"
            "这款留下来主要是阶段对得上，配方里钙铁锌我也看过，孩子喝着不抗拒。"
            "价格不算最低，但家里用着顺，就先续上。"
        ),
        plan={"post_type": "复购/长期使用型"},
    )

    assert review.rewrite_required is False
    assert review.pass_ is True


def test_ai_flavor_review_flags_abstract_bridge_phrases():
    review = review_ai_flavor(
        title="拼图桌边的配方观察",
        body=(
            "娃最近迷上拼图和贴纸书，一坐能待半小时。"
            "我就在边上翻他奶粉的配料，看DHA和燕窝酸这块是不是跟得上桌面时间。"
            "旺玥的配置刚好卡在我关注的点上，价格比预想高一点，但这个方向我愿意接着看看。"
        ),
        plan={"post_type": "轻测评"},
    )

    assert review.rewrite_required is True
    assert "explanation_voice" in review.reasons
    assert "scene_over_explanation" in review.rewrite_operations
    assert any("跟得上桌面时间" in hit for hit in review.body_hits)
    assert any("这个方向" in hit for hit in review.body_hits)
