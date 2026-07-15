from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.models.content_agent import ContentBatchItem
from app.services import content_batch_execution_service as execution_module
from app.services import rewrite_quality_validator_service as validator_module
from app.services.content_batch_execution_service import (
    POST_DELETE_CLEANUP_FLUENCY_REASON,
    ContentBatchExecutionService,
)
from app.services.product_experience_phrase_guard_service import review_product_experience_phrase
from app.services.rewrite_quality_validator_service import (
    RewriteQualityJudgment,
    RewriteQualityValidatorService,
    parse_rewrite_quality_judgment,
)


def test_parse_rewrite_quality_judgment_accepts_valid_contract() -> None:
    judgment = parse_rewrite_quality_judgment(
        '{"label":"reject","issue_code":"fluency_regression","evidence":"时候交替搭配错误"}'
    )

    assert judgment is not None
    assert judgment.label == "reject"
    assert judgment.issue_code == "fluency_regression"
    assert judgment.evidence == "时候交替搭配错误"


def test_parse_rewrite_quality_judgment_rejects_invalid_contract() -> None:
    assert parse_rewrite_quality_judgment('{"label":"pass","issue_code":"none","evidence":""}') is None


def test_rewrite_quality_validation_failure_prevents_hard_pass() -> None:
    item = ContentBatchItem(
        status="generated",
        quality_json={"hard_pass": True, "review_report": {}},
    )

    ContentBatchExecutionService._mark_rewrite_quality_validation_failure(
        item,
        reason="改写后验收不可用，禁止自动放行",
    )

    assert item.quality_json["hard_pass"] is False
    assert item.quality_json["rewrite_quality_validation_watch"] is True
    assert item.quality_json["review_report"]["rewrite_required"] is True
    assert item.quality_json["review_report"]["rewrite_quality_validation_failed"] is True


@pytest.mark.asyncio
async def test_rewrite_quality_validator_uses_direct_llm_path(monkeypatch) -> None:
    calls = []

    async def fake_call_direct_llm_text(**kwargs):
        calls.append(kwargs)
        return '{"label":"accept","issue_code":"none","evidence":"候选通顺"}'

    monkeypatch.setattr(validator_module, "call_direct_llm_text", fake_call_direct_llm_text)

    judgment = await RewriteQualityValidatorService().review(
        before={"title": "原题", "body": "原文"},
        after={"title": "原题", "body": "改写后正文"},
        rewrite_source="product_experience_phrase_guard",
        target_issue="formula_usage_form_error",
        plan={"model_config": {"provider_code": "test-provider", "model_code": "test-model"}},
    )

    assert judgment.label == "accept"
    assert len(calls) == 1
    assert calls[0]["model_config"]["provider"] == "test-provider"
    assert calls[0]["model_config"]["model"] == "test-model"


class _RejectRewriteQualityValidator:
    async def review(self, **_kwargs):
        return RewriteQualityJudgment(
            label="reject",
            issue_code="fluency_regression",
            evidence="时候交替不是自然中文搭配",
        )


class _FakeDB:
    async def flush(self) -> None:
        return None


class _FakeOrchestrator:
    def __init__(self, db, **_kwargs):
        self.db = db

    async def _input_payload_with_provider_config(self, payload):
        return payload

    async def run_content_rewrite_stage(self, **_kwargs):
        return SimpleNamespace(
            output={
                "title": "随口一句，他指了指柜子",
                "body": "回想之前时候交替总要请几天假，今年倒全勤了。",
            },
            stage_calls=[SimpleNamespace(stage_call_id="stage-rewrite-item5")],
            run=SimpleNamespace(status="succeeded"),
        )


@pytest.mark.asyncio
async def test_item5_rejected_candidate_is_not_written_back(monkeypatch) -> None:
    monkeypatch.setattr(execution_module, "ContentAgentOrchestrator", _FakeOrchestrator)
    before_body = "回想之前总要请几天假，今年倒全勤了。"
    item = ContentBatchItem(
        run_id=1,
        status="generated",
        title="随口一句，他指了指柜子",
        body=before_body,
        plan_json={
            "rule_type": "business_rule",
            "asset_key": "wangyue_v3_core_storyline_article_rules",
            "corpus": "0705旺玥活动",
            "model_config": {"provider_code": "test", "model_code": "test"},
        },
        quality_json={"hard_pass": True, "review_report": {}},
    )
    base_review = review_product_experience_phrase(
        title=item.title,
        body=item.body,
        plan=item.plan_json,
    )
    review = replace(
        base_review,
        pass_=False,
        rewrite_required=True,
        reasons=[POST_DELETE_CLEANUP_FLUENCY_REASON],
    )
    service = ContentBatchExecutionService.__new__(ContentBatchExecutionService)
    service.invocation_client = None
    service.callback_base_url = "http://testserver"
    service.executor_code = "test-executor"
    service.rewrite_quality_validator = _RejectRewriteQualityValidator()

    rewritten = await service._rewrite_item_for_product_experience_phrase(_FakeDB(), item, review)

    assert rewritten is False
    assert item.body == before_body
    assert item.quality_json["hard_pass"] is False
    assert item.quality_json["rewrite_quality_validations"][0]["judgment"] == {
        "label": "reject",
        "issue_code": "fluency_regression",
        "evidence": "时候交替不是自然中文搭配",
    }
    assert "product_experience_phrase_rewrites" not in item.quality_json
