from app.services.executor_invocation_service import _normalize_unified_content_output


def test_normalize_comment_output_accepts_json_string_array_mode():
    output = _normalize_unified_content_output(
        '["a2终于到货了", "我也买到了新货"]',
        {
            "content_type": "comment",
            "output_fields": ["comment"],
            "output_format_mode": "json_string_array",
        },
    )

    assert output["comment"] == "a2终于到货了"
    assert output["comments"] == ["a2终于到货了", "我也买到了新货"]
    assert output["items"] == [{"comment": "a2终于到货了"}, {"comment": "我也买到了新货"}]


def test_normalize_comment_output_accepts_json_object_array_mode():
    output = _normalize_unified_content_output(
        '[{"内容":"报告能扫出来"}, {"comment":"礼盒里的东西挺实在"}]',
        {
            "content_type": "comment",
            "output_fields": ["comment"],
            "output_format": {"mode": "json_object_array", "count": 2},
        },
    )

    assert output["comment"] == "报告能扫出来"
    assert output["comments"] == ["报告能扫出来", "礼盒里的东西挺实在"]
