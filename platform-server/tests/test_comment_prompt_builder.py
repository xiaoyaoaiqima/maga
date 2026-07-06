import pytest

from app.services.unified_content_generation_service import (
    _comment_prompt_text,
    _select_comment_prompt_slots,
)


def test_comment_prompt_can_render_json_string_array_output_contract():
    prompt = _comment_prompt_text(
        {
            "business_rule": "有货-直给到货情绪",
            "corpus": "像妈妈看到 a2 到货后顺手接一句。",
            "examples": ["a2终于到货了"],
            "output_format_mode": "json_string_array",
            "expansion_count": 20,
        }
    )

    assert "生成 20 条评论。" in prompt
    assert "只输出 JSON 字符串数组，不要标题、编号、解释。" in prompt
    assert "只输出评论正文，不要标题、编号、解释。" not in prompt


def test_a2_comment_prompt_generalizes_competitor_names_in_examples():
    prompt = _comment_prompt_text(
        {
            "asset_key": "a2_sentiment_comment_activity",
            "business_rule": "转奶-换奶顾虑",
            "corpus": "像妈妈聊转奶时顺手提一句。",
            "examples": ["之前喝爱他美，现在想转回a2看看", "雀巢也看过，还是想先扫报告"],
        }
    )

    assert "不要直接说其他奶粉品牌名" in prompt
    assert "爱他美" not in prompt
    assert "雀巢" not in prompt
    assert "之前的奶粉" in prompt
    assert "其他品牌" in prompt


def test_comment_style_slot_rejects_business_terms():
    with pytest.raises(ValueError, match="说话风格槽位不能包含业务元素"):
        _select_comment_prompt_slots(
            {
                "prompt_slots": {
                    "说话风格": ["像一直喝a2的妈妈，语气更像补充经验，不要证明品牌。"]
                }
            }
        )
