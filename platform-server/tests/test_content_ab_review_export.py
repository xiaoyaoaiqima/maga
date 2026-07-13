import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from scripts.export_content_ab_review import render_experiment_preview  # noqa: E402
from scripts.review_a2_ab_comments_with_llm import (  # noqa: E402
    REVIEW_SYSTEM_PROMPT,
    align_review_item_numbers,
    extract_json_array,
    review_prompt,
)
from scripts.export_a2_ab_candidate_pool import candidate_rows, mark_exact_duplicates  # noqa: E402


WANGYUE_ADAPTER_PATH = REPO_ROOT / "platform-server/scripts/export_wangyue_rule_ab_preview.py"
spec = importlib.util.spec_from_file_location("export_wangyue_rule_ab_preview", WANGYUE_ADAPTER_PATH)
wangyue_adapter = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(wangyue_adapter)


def _item(item_no, content, *, machine_pass=True, tier="direct_pool", operator=None):
    item = {
        "item_no": item_no,
        "pair_id": f"case-{item_no}",
        "category": "A2舆情改善",
        "content": content,
        "machine_review": {"pass": machine_pass, "reason": "machine reason"},
        "llm_review": {
            "tier": tier,
            "reason": "llm reason",
            "issue_codes": ["generic_brief_tone"] if tier != "direct_pool" else [],
            "rewrite_direction": "rewrite it" if tier != "direct_pool" else "无需修改",
        },
    }
    if operator is not None:
        item["operator_review"] = operator
    return item


def _experiment(*, comparison_mode="aggregate"):
    return {
        "experiment_id": "exp-001",
        "title": "Generic A/B Review",
        "content_type": "comment",
        "comparison_mode": comparison_mode,
        "changed_dimensions": [
            {
                "name": "model",
                "values": {"control": "deepseek-v4-flash", "candidate": "qwen3-4b"},
            },
            {
                "name": "temperature",
                "values": {"control": 0.7, "candidate": 0.3},
            },
        ],
        "controlled_dimensions": [{"name": "prompt", "value": "same prompt"}],
        "arms": [
            {
                "arm_id": "control",
                "label": "A control",
                "items": [
                    _item(1, "control ok"),
                    _item(2, "control watch", tier="light_fix_usable"),
                ],
            },
            {
                "arm_id": "candidate",
                "label": "B candidate",
                "items": [
                    _item(
                        1,
                        "candidate needs fix",
                        machine_pass=False,
                        tier="hold_out",
                        operator={"status": "needs_fix", "reason": "operator reason"},
                    ),
                    _item(2, "candidate not reviewed", tier="unknown"),
                ],
            },
        ],
    }


def test_aggregate_preview_separates_machine_llm_and_operator_reviews():
    preview = render_experiment_preview(_experiment())

    assert "## 唯一变量" in preview
    assert "| model | deepseek-v4-flash | qwen3-4b |" in preview
    assert "| temperature | 0.7 | 0.3 |" in preview
    assert "- prompt：same prompt" in preview
    assert "机器审核：未通过：machine reason" in preview
    assert "机器拦截" in preview
    assert "LLM review：not_run；llm reason" in preview
    assert "运营判断：needs_fix；operator reason" in preview
    assert "运营判断：not run" in preview
    assert "machine-blocked `case-1`" in preview
    assert "| A control | 2 | 2 | 0 | 2 | 0 | 1 | 1 | 0 | 0 |" in preview
    assert "| B candidate | 2 | 2 | 0 | 1 | 1 | 0 | 0 | 0 | 1 |" in preview


def test_paired_preview_groups_items_by_pair_id():
    preview = render_experiment_preview(_experiment(comparison_mode="paired"))

    assert "## 配对 Review" in preview
    assert "### 💣 pair case-1｜至少一组机器拦截" in preview
    assert "#### A control" in preview
    assert "#### B candidate" in preview


def test_preview_requires_at_least_two_unique_arms():
    experiment = _experiment()
    experiment["arms"][1]["arm_id"] = "control"

    with pytest.raises(ValueError, match="arm_id must be unique"):
        render_experiment_preview(experiment)


def test_wangyue_adapter_marks_missing_llm_review_as_not_run():
    report = {
        "summary": {"total_count": 1},
        "items": [
            {
                "item_no": 1,
                "title": "sample",
                "body": "旺玥只是日常动作的一部分。",
                "hard_pass": True,
                "quality": {},
                "generation_snapshot": {
                    "business_rule": {"business_rule": "使用记录｜产品是日常动作的一部分"}
                },
            }
        ],
    }

    arm = wangyue_adapter._normalized_wangyue_arm(report, arm_id="candidate", label="B")

    assert arm["items"][0]["machine_review"]["pass"] is True
    assert arm["items"][0]["llm_review"]["tier"] == "not_run"
    assert arm["items"][0]["llm_review"]["reason"] == "not run"


def test_llm_review_json_parser_allows_raw_control_characters():
    payload = '[{"item_no": 1, "reason": "line one\nline two"}]'

    assert extract_json_array(payload) == [{"item_no": 1, "reason": "line one\nline two"}]


def test_a2_llm_review_only_judges_business_usability_after_machine_audit():
    prompt = review_prompt(
        {
            "category": "批批检-报告查询互动",
            "focus": "围绕报告查询做自然追问",
            "examples": "这个在哪里看呀？",
        },
        [{"item_no": "1", "内容": "能查到更多信息吗？想看看源头。"}],
    )

    assert "不要复核违禁词、硬禁词、长度、重复或分类关键词命中" in prompt
    assert "不得仅凭单个词语判错" in prompt
    assert "分类贴合" in prompt
    assert "事实支持" in prompt
    assert "评论质感" in prompt
    assert "修改成本" in prompt
    assert "hard_forbidden" not in prompt
    assert "negative_context" not in prompt
    assert '"severity": "pass|minor|rewrite|hard"' not in prompt
    assert "微信、小程序、断货、缺货" not in prompt
    assert "没找到、找不到" not in prompt
    assert "供应链、源头、溯源、奶源地" not in prompt
    assert "不要复核违禁词或其他机器硬规则" in REVIEW_SYSTEM_PROMPT


def test_a2_deescalation_llm_review_checks_semantics_not_forbidden_words():
    prompt = review_prompt(
        {
            "category": "舆情缓和-个人经历与个体差异",
            "focus": "分享个人经历并保留其他可能",
            "examples": "我家那阵也有变化，也说不准是哪一个",
        },
        [{"item_no": "1", "内容": "我家之前也碰到过，会不会和辅食变化也有点关系呀？"}],
    )

    assert "是否主要贴合当前子方向" in prompt
    assert "问句、“可能/说不准”的陈述句、个人时间顺序都可以" in prompt
    assert "确定因果" in prompt
    assert "brand_defense_tone" in prompt
    assert "不要复核违禁词" in prompt
    assert "不要求每条提到 a2" in prompt


def test_a2_candidate_pool_prefers_direct_qwen_copy_and_keeps_audit_rows():
    rows = [
        {
            "candidate_id": "deepseek-light",
            "arm": "deepseek",
            "content": "同一条评论",
            "machine_pass": True,
            "llm_tier": "light_fix_usable",
        },
        {
            "candidate_id": "qwen-direct",
            "arm": "qwen",
            "content": "同一条评论",
            "machine_pass": True,
            "llm_tier": "direct_pool",
        },
        {
            "candidate_id": "blocked",
            "arm": "qwen",
            "content": "机器未过",
            "machine_pass": False,
            "llm_tier": "not_run",
        },
    ]

    mark_exact_duplicates(rows)

    assert len(rows) == 3
    assert candidate_rows(rows, "direct_pool") == [rows[1]]
    assert rows[0]["duplicate_of"] == "qwen-direct"
    assert rows[1]["duplicate_of"] == ""
    assert candidate_rows(rows, "not_run") == []


def test_a2_llm_review_restores_source_item_numbers_after_sequential_renumbering():
    reviews = [{"item_no": 1}, {"item_no": 2}, {"item_no": 3}]

    aligned = align_review_item_numbers(reviews, [1, 4, 7])

    assert [item["item_no"] for item in aligned] == [1, 4, 7]


def test_a2_llm_review_rejects_non_sequential_wrong_order():
    with pytest.raises(ValueError, match="review item order mismatch"):
        align_review_item_numbers([{"item_no": 2}, {"item_no": 1}], [1, 4])
