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
