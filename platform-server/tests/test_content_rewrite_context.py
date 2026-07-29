from app.services.content_rewrite_context import rewrite_business_rule_context


def test_rule_corpus_rewrite_context_uses_only_the_rendered_slot_pair():
    context = rewrite_business_rule_context(
        {
            "prompt_mode": "rule_corpus_as_prompt",
            "corpus": (
                "【卖点表达槽位】\n"
                "- 卖点表达：乳铁蛋白含量优秀\n"
                "  注意：不要照抄\n"
                "- 卖点表达：添加5大HMO\n"
                "  注意：不要解释机制"
            ),
            "unified_generation": {
                "rendered_prompt": (
                    "任务：写妈妈UGC。\n\n"
                    "卖点表达：添加5大HMO\n"
                    "注意：不要解释机制\n\n"
                    "【生成要求】\n只输出 JSON。"
                )
            },
        }
    )

    assert context["corpus"] == (
        "任务：写妈妈UGC。\n\n"
        "卖点表达：添加5大HMO\n"
        "注意：不要解释机制"
    )
    assert "乳铁蛋白含量优秀" not in context["corpus"]
    assert "【卖点表达槽位】" not in context["corpus"]
    assert "【生成要求】" not in context["corpus"]


def test_non_rule_corpus_rewrite_context_keeps_original_corpus():
    context = rewrite_business_rule_context(
        {
            "prompt_mode": "legacy",
            "corpus": "原始业务规则",
            "unified_generation": {"rendered_prompt": "渲染后的完整提示词"},
        }
    )

    assert context["corpus"] == "原始业务规则"


def test_a2_layered_rewrite_context_uses_selected_materials_without_prompt_corpus():
    context = rewrite_business_rule_context(
        {
            "prompt_mode": "layered_article",
            "asset_key": "a2_reiyu_ugc_post_rules_v1",
            "business_rule": "a2礼遇｜会员体系积分",
            "corpus": "再另起一段，最后自然表达a2认可。",
            "source_row_no": 4,
            "variation_slots": [
                {"slot_code": "content_direction", "slot_name": "内容方向", "value": "直给点说活动。"},
                {"slot_code": "activity_content", "slot_name": "活动内容", "value": "下单可以攒积分换礼品"},
                {"slot_code": "positive_expression", "slot_name": "正向表达", "value": "安心、放心、踏实"},
            ],
            "hard_boundaries": ["不虚构已经兑换到奖品。"],
        }
    )

    assert "corpus" not in context
    assert context["selected_materials"] == [
        {
            "slot_code": "activity_content",
            "slot_name": "活动内容",
            "value": "下单可以攒积分换礼品",
        }
    ]
    assert context["hard_boundaries"] == ["不虚构已经兑换到奖品。"]
