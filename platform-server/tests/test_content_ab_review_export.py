import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.export_content_ab_review import render_experiment_preview  # noqa: E402


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
    assert "LLM review：hold_out；llm reason" in preview
    assert "运营判断：needs_fix；operator reason" in preview
    assert "运营判断：not run" in preview
    assert "| A control | 2 | 2 | 0 | 2 | 1 | 1 | 0 | 0 |" in preview
    assert "| B candidate | 2 | 2 | 0 | 1 | 0 | 0 | 1 | 1 |" in preview


def test_paired_preview_groups_items_by_pair_id():
    preview = render_experiment_preview(_experiment(comparison_mode="paired"))

    assert "## 配对 Review" in preview
    assert "### 💣 pair case-1｜至少一组需修" in preview
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
