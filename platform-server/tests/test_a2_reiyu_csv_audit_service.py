import csv
import json

import pytest

from app.services.a2_reiyu_csv_audit_service import (
    audit_a2_reiyu_article,
    audit_a2_reiyu_csv_file,
    audit_a2_reiyu_csv_file_strict,
)
from app.services.product_experience_llm_review_service import (
    ProductExperienceLLMIssue,
    ProductExperienceLLMReview,
)


class FakeGoldReviewer:
    def __init__(self) -> None:
        self.calls = 0

    async def review(self, *, title, body, plan, phrase_review, ai_flavor_review):
        self.calls += 1
        if "语义问题" in body:
            return ProductExperienceLLMReview(
                pass_=False,
                rewrite_required=True,
                severity="rewrite",
                business_usability_tier="hold_out",
                business_usability_reason="金标语义审核未通过",
                issues=[
                    ProductExperienceLLMIssue(
                        code="common_sense_error",
                        evidence="语义问题",
                        reason="存在通用逻辑问题",
                        rewrite_direction="局部改写",
                    )
                ],
                review_rubric_code="a2_reiyu_business_usability_v1",
            )
        return ProductExperienceLLMReview(
            pass_=True,
            rewrite_required=False,
            severity="pass",
            business_usability_tier="direct_pool",
            business_usability_reason="通过",
            review_rubric_code="a2_reiyu_business_usability_v1",
        )


def test_csv_audit_aggregates_production_guards_without_api() -> None:
    direct = audit_a2_reiyu_article(
        title="a2至初老客礼拿到了",
        body="我领到了老客回归礼，a2至初现在每批都有检测。",
        csv_row_number=2,
    )
    conflict = audit_a2_reiyu_article(
        title="a2至初活动分享",
        body="我家娃从出生就喝a2至初，当初转奶也很顺利。",
        csv_row_number=3,
    )
    old_can = audit_a2_reiyu_article(
        title="a2集罐活动",
        body="正好家里囤了好几罐，集3罐能换小车车。",
        csv_row_number=4,
    )
    quantity_error = audit_a2_reiyu_article(
        title="a2至初集罐礼",
        body="集12罐就能换1罐，一箱差不多就够。",
        csv_row_number=5,
    )
    fabricated_benefit = audit_a2_reiyu_article(
        title="a2至初会员活动",
        body="多重福利一起上，又是积分翻倍又是专属赠品。",
        csv_row_number=6,
    )

    assert direct.business_usability_tier == "direct_pool"
    assert conflict.business_usability_tier == "light_fix_usable"
    assert {issue.issue_code for issue in conflict.issues} == {"narrative_consistency"}
    assert old_can.business_usability_tier == "hold_out"
    assert "old_can_eligibility_error" in {issue.issue_code for issue in old_can.issues}
    assert "forbidden_term_hard_ban" in {issue.issue_code for issue in old_can.issues}
    assert quantity_error.business_usability_tier == "hold_out"
    assert {issue.issue_code for issue in quantity_error.issues} == {"activity_quantity_error"}
    assert fabricated_benefit.business_usability_tier == "hold_out"
    assert {issue.issue_code for issue in fabricated_benefit.issues} == {
        "fabricated_activity_benefit"
    }


def test_csv_audit_uses_contextual_forbidden_term_rules() -> None:
    allowed = audit_a2_reiyu_article(
        title="a2活动分享",
        body="这活动不用报名，闭眼入不踩雷。我反正是囤了好几罐。",
        csv_row_number=2,
    )
    rewrite = audit_a2_reiyu_article(
        title="a2活动分享",
        body="先报名参加活动，这波羊毛可以看看。",
        csv_row_number=3,
    )

    assert allowed.business_usability_tier == "direct_pool"
    assert rewrite.business_usability_tier == "light_fix_usable"
    assert "forbidden_term_model_rewrite" in {issue.issue_code for issue in rewrite.issues}


def test_csv_audit_accepts_active_business_entries() -> None:
    review = audit_a2_reiyu_article(
        title="a2活动分享",
        body="这里有一个当前资产专用词。",
        csv_row_number=2,
        business_entries=(
            {
                "term": "当前资产专用词",
                "enabled": True,
                "enforcement": "hard_ban",
                "match_mode": "literal",
                "reason": "测试当前资产注入",
            },
        ),
    )

    assert review.business_usability_tier == "hold_out"
    assert review.issues[0].hits == ("当前资产专用词",)


def test_csv_audit_writes_real_source_row_numbers_and_summary(tmp_path) -> None:
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "audited.csv"
    with input_path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=["content_id", "标题", "正文", "分类"])
        writer.writeheader()
        writer.writerow(
            {
                "content_id": "c1",
                "标题": "a2至初活动分享",
                "正文": "a2至初现在每批都有检测。",
                "分类": "其他",
            }
        )
        writer.writerow(
            {
                "content_id": "c2",
                "标题": "a2至初活动分享",
                "正文": "a2至初现在每罐都有检测。",
                "分类": "其他",
            }
        )

    summary = audit_a2_reiyu_csv_file(input_path, output_path)
    with output_path.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    summary_payload = json.loads(output_path.with_suffix(".summary.json").read_text(encoding="utf-8"))

    assert [row["CSV行号"] for row in rows] == ["2", "3"]
    assert rows[0]["审核结论"] == "可用"
    assert rows[1]["审核结论"] == "拦截"
    assert rows[1]["审核问题码"] == "batch_detection_fact_error"
    assert summary.total_count == 2
    assert summary.direct_pool_count == 1
    assert summary.hold_out_count == 1
    assert summary_payload["output_path"] == str(output_path.resolve())


@pytest.mark.asyncio
async def test_strict_csv_audit_runs_gold_judge_in_parallel_after_deterministic_guards(tmp_path) -> None:
    input_path = tmp_path / "strict-input.csv"
    output_path = tmp_path / "strict-audited.csv"
    with input_path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=["content_id", "标题", "正文", "分类"])
        writer.writeheader()
        writer.writerows(
            [
                {"content_id": "c1", "标题": "a2活动", "正文": "a2至初每批都有检测。", "分类": "其他"},
                {"content_id": "c2", "标题": "a2活动", "正文": "这篇有语义问题。", "分类": "其他"},
                {
                    "content_id": "c3",
                    "标题": "a2集罐",
                    "正文": "回家把旧罐子收拾好，集够数就能换。",
                    "分类": "集罐",
                },
            ]
        )

    reviewer = FakeGoldReviewer()
    summary = await audit_a2_reiyu_csv_file_strict(
        input_path,
        output_path,
        business_entries=(),
        review_plan={
            "asset_key": "a2_reiyu_ugc_post_rules_v1",
            "model_config": {"provider_code": "fake", "model_code": "fake"},
        },
        concurrency=2,
        reviewer=reviewer,
    )
    with output_path.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))

    assert reviewer.calls == 2
    assert rows[0]["审核结论"] == "可用"
    assert rows[1]["审核问题码"] == "common_sense_error"
    assert rows[1]["审核结论"] == "拦截"
    assert rows[2]["审核问题码"] == "old_can_eligibility_error"
    assert summary.direct_pool_count == 1
    assert summary.hold_out_count == 2
