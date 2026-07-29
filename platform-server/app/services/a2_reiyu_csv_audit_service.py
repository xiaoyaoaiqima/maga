"""Reusable deterministic and gold-judge CSV audit for a2 礼遇 articles."""
from __future__ import annotations

import asyncio
import csv
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.a2_reiyu_batch_detection_guard_service import (
    review_a2_reiyu_batch_detection_fact,
)
from app.services.a2_reiyu_old_can_guard_service import review_a2_reiyu_old_can_eligibility
from app.services.a2_reiyu_text_guard_service import review_a2_reiyu_text_surface
from app.services.business_forbidden_term_service import (
    A2_REIYU_UGC_POST_ASSET_KEY,
    A2_REIYU_UGC_POST_SEED_TERMS,
    BusinessForbiddenTermService,
)
from app.services.forbidden_term_review_service import business_forbidden_entry_matches
from app.services.ai_flavor_humanizer_service import review_ai_flavor
from app.services.content_agent_orchestrator import ContentAgentOrchestrator
from app.services.product_experience_llm_review_service import (
    A2_REIYU_REVIEW_RUBRIC_CODE,
    ProductExperienceLLMReview,
    ProductExperienceLLMReviewService,
)
from app.services.product_experience_phrase_guard_service import review_product_experience_phrase


_PLAN = {"asset_key": A2_REIYU_UGC_POST_ASSET_KEY}
_TITLE_COLUMNS = ("标题", "title")
_BODY_COLUMNS = ("正文", "body", "content")
_CONTENT_ID_COLUMNS = ("content_id", "id")
_CATEGORY_COLUMNS = ("分类", "category")
_PLAN_COLUMNS = ("plan_json", "生成计划")
_AUDIT_COLUMNS = (
    "CSV行号",
    "审核结论",
    "审核档位",
    "审核问题码",
    "审核严重度",
    "审核原因",
    "命中片段",
    "需要改写",
)
_DECISION_LABELS = {
    "direct_pool": "可用",
    "light_fix_usable": "轻修",
    "watch": "待复核",
    "hold_out": "拦截",
}
_TIER_RANK = {"direct_pool": 0, "light_fix_usable": 1, "watch": 2, "hold_out": 3}
_SEVERITY_RANK = {"pass": 0, "minor": 1, "rewrite": 2, "hard": 3}
_DEFAULT_REVIEW_MODEL_CONFIG = {
    "provider_code": "deepseek",
    "model_code": "deepseek-v4-flash",
    "ge_model": "deepseek-v4-flash",
    "ae_model": "deepseek-v4-flash",
}
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\u2600-\u27BF"
    "]+"
)


@dataclass(frozen=True)
class A2ReiyuCsvAuditIssue:
    source: str
    issue_code: str
    severity: str
    business_usability_tier: str
    reason: str
    hits: tuple[str, ...] = ()
    rewrite_required: bool = False


@dataclass(frozen=True)
class A2ReiyuCsvAuditRow:
    csv_row_number: int
    content_id: str
    title: str
    body: str
    category: str
    business_usability_tier: str
    severity: str
    rewrite_required: bool
    issues: tuple[A2ReiyuCsvAuditIssue, ...]

    @property
    def decision_label(self) -> str:
        return _DECISION_LABELS[self.business_usability_tier]


@dataclass(frozen=True)
class A2ReiyuCsvAuditSummary:
    input_path: str
    output_path: str
    total_count: int
    direct_pool_count: int
    light_fix_count: int
    watch_count: int
    hold_out_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_path": self.input_path,
            "output_path": self.output_path,
            "total_count": self.total_count,
            "direct_pool_count": self.direct_pool_count,
            "light_fix_count": self.light_fix_count,
            "watch_count": self.watch_count,
            "hold_out_count": self.hold_out_count,
        }


def audit_a2_reiyu_article(
    *,
    title: str | None,
    body: str | None,
    csv_row_number: int,
    content_id: str | None = None,
    category: str | None = None,
    business_entries: Iterable[Mapping[str, Any]] | None = None,
) -> A2ReiyuCsvAuditRow:
    normalized_title = str(title or "")
    normalized_body = str(body or "")
    issues: list[A2ReiyuCsvAuditIssue] = []

    weighted_len = a2_reiyu_title_weighted_len(normalized_title)
    if weighted_len > 20:
        issues.append(
            A2ReiyuCsvAuditIssue(
                source="a2_reiyu_title_guard",
                issue_code="title_too_long",
                severity="hard",
                business_usability_tier="hold_out",
                reason=f"标题加权长度{weighted_len}超过20，直接拦截且不改标题。",
                hits=(normalized_title,),
            )
        )

    for source, payload in (
        (
            "a2_reiyu_text_guard",
            review_a2_reiyu_text_surface(
                title=normalized_title,
                body=normalized_body,
                plan=_PLAN,
            ).to_payload(),
        ),
        (
            "a2_reiyu_batch_detection_guard",
            review_a2_reiyu_batch_detection_fact(
                title=normalized_title,
                body=normalized_body,
                plan=_PLAN,
            ).to_payload(),
        ),
        (
            "a2_reiyu_old_can_guard",
            review_a2_reiyu_old_can_eligibility(
                title=normalized_title,
                body=normalized_body,
                plan=_PLAN,
            ).to_payload(),
        ),
    ):
        if payload.get("pass") is not False:
            continue
        issues.append(
            A2ReiyuCsvAuditIssue(
                source=source,
                issue_code=str(payload.get("issue_code") or source),
                severity=str(payload.get("severity") or "hard"),
                business_usability_tier=str(
                    payload.get("business_usability_tier") or "hold_out"
                ),
                reason=str(payload.get("reason") or "确定性审核未通过。"),
                hits=tuple(str(hit) for hit in payload.get("hits") or []),
                rewrite_required=bool(payload.get("rewrite_required")),
            )
        )

    issues.extend(
        _audit_business_forbidden_terms(
            normalized_title,
            normalized_body,
            business_entries=business_entries,
        )
    )
    tier = max(
        (issue.business_usability_tier for issue in issues),
        key=lambda value: _TIER_RANK.get(value, 2),
        default="direct_pool",
    )
    severity = max(
        (issue.severity for issue in issues),
        key=lambda value: _SEVERITY_RANK.get(value, 3),
        default="pass",
    )
    return A2ReiyuCsvAuditRow(
        csv_row_number=csv_row_number,
        content_id=str(content_id or ""),
        title=normalized_title,
        body=normalized_body,
        category=str(category or ""),
        business_usability_tier=tier,
        severity=severity,
        rewrite_required=any(issue.rewrite_required for issue in issues),
        issues=tuple(issues),
    )


def audit_a2_reiyu_csv_file(
    input_path: Path,
    output_path: Path,
    *,
    business_entries: Iterable[Mapping[str, Any]] | None = None,
) -> A2ReiyuCsvAuditSummary:
    input_path = Path(input_path).expanduser().resolve()
    output_path = Path(output_path).expanduser().resolve()
    fieldnames, source_rows = _read_csv_source(input_path)

    normalized_business_entries = (
        tuple(dict(entry) for entry in business_entries) if business_entries is not None else None
    )
    audited_rows = [
        audit_a2_reiyu_article(
            title=_first_value(row, _TITLE_COLUMNS),
            body=_first_value(row, _BODY_COLUMNS),
            content_id=_first_value(row, _CONTENT_ID_COLUMNS),
            category=_first_value(row, _CATEGORY_COLUMNS),
            csv_row_number=index,
            business_entries=normalized_business_entries,
        )
        for index, row in enumerate(source_rows, start=2)
    ]

    return _write_audit_output(
        input_path=input_path,
        output_path=output_path,
        fieldnames=fieldnames,
        source_rows=source_rows,
        audited_rows=audited_rows,
    )


async def audit_a2_reiyu_csv_file_strict(
    input_path: Path,
    output_path: Path,
    *,
    business_entries: Iterable[Mapping[str, Any]],
    review_plan: Mapping[str, Any],
    concurrency: int = 10,
    reviewer: ProductExperienceLLMReviewService | None = None,
) -> A2ReiyuCsvAuditSummary:
    if concurrency <= 0:
        raise ValueError("concurrency must be positive")
    input_path = Path(input_path).expanduser().resolve()
    output_path = Path(output_path).expanduser().resolve()
    fieldnames, source_rows = _read_csv_source(input_path)
    normalized_business_entries = tuple(dict(entry) for entry in business_entries)
    base_review_plan = dict(review_plan)
    base_review_plan["asset_key"] = A2_REIYU_UGC_POST_ASSET_KEY
    semaphore = asyncio.Semaphore(concurrency)
    gold_reviewer = reviewer or ProductExperienceLLMReviewService()

    async def worker(index: int, source_row: Mapping[str, Any]) -> A2ReiyuCsvAuditRow:
        title = _first_value(source_row, _TITLE_COLUMNS)
        body = _first_value(source_row, _BODY_COLUMNS)
        deterministic = audit_a2_reiyu_article(
            title=title,
            body=body,
            content_id=_first_value(source_row, _CONTENT_ID_COLUMNS),
            category=_first_value(source_row, _CATEGORY_COLUMNS),
            csv_row_number=index,
            business_entries=normalized_business_entries,
        )
        if deterministic.business_usability_tier == "hold_out":
            return deterministic

        row_plan = {
            **_parse_row_plan(source_row),
            **base_review_plan,
            "asset_key": A2_REIYU_UGC_POST_ASSET_KEY,
        }
        phrase_review = review_product_experience_phrase(title=title, body=body, plan=row_plan)
        ai_flavor_review = review_ai_flavor(title=title, body=body, plan=row_plan)
        try:
            async with semaphore:
                gold_review = await gold_reviewer.review(
                    title=title,
                    body=body,
                    plan=row_plan,
                    phrase_review=phrase_review,
                    ai_flavor_review=ai_flavor_review,
                )
        except Exception as exc:  # noqa: BLE001 - unavailable gold judge must not pass content
            return _with_gold_review_failure(deterministic, str(exc))
        return _with_gold_review(deterministic, gold_review)

    audited_rows = await asyncio.gather(
        *(worker(index, row) for index, row in enumerate(source_rows, start=2))
    )
    return _write_audit_output(
        input_path=input_path,
        output_path=output_path,
        fieldnames=fieldnames,
        source_rows=source_rows,
        audited_rows=audited_rows,
    )


def a2_reiyu_title_weighted_len(title: str | None) -> int:
    total = 0
    for char in re.sub(r"\s+", "", str(title or "").strip()):
        if char in ("\u200d", "\ufe0f"):
            continue
        total += 2 if _EMOJI_PATTERN.fullmatch(char) else 1
    return total


async def load_active_a2_reiyu_business_entries(
    db: AsyncSession,
) -> tuple[dict[str, Any], ...]:
    entries = await BusinessForbiddenTermService(db).list_entries(
        asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
        include_default=True,
    )
    return tuple(entries) or tuple(dict(entry) for entry in A2_REIYU_UGC_POST_SEED_TERMS)


async def load_active_a2_reiyu_review_plan(db: AsyncSession) -> dict[str, Any]:
    orchestrator = ContentAgentOrchestrator(
        db,
        callback_base_url="http://maga.local/api/v1/executor",
    )
    payload = await orchestrator.hydrate_model_config(dict(_DEFAULT_REVIEW_MODEL_CONFIG))
    model_config = payload if isinstance(payload, dict) else dict(_DEFAULT_REVIEW_MODEL_CONFIG)
    return {
        "asset_key": A2_REIYU_UGC_POST_ASSET_KEY,
        "model_config": model_config,
    }


def _audit_business_forbidden_terms(
    title: str,
    body: str,
    *,
    business_entries: Iterable[Mapping[str, Any]] | None,
) -> list[A2ReiyuCsvAuditIssue]:
    text = f"{title}\n{body}"
    entries_to_check = (
        business_entries if business_entries is not None else A2_REIYU_UGC_POST_SEED_TERMS
    )
    matched_entries = [
        dict(entry)
        for entry in entries_to_check
        if entry.get("enabled") is not False and business_forbidden_entry_matches(text, entry)
    ]
    issues: list[A2ReiyuCsvAuditIssue] = []
    for enforcement, tier, severity, rewrite_required in (
        ("hard_ban", "hold_out", "hard", False),
        ("model_rewrite", "light_fix_usable", "rewrite", True),
        ("replace", "light_fix_usable", "minor", True),
    ):
        entries = [entry for entry in matched_entries if entry.get("enforcement") == enforcement]
        if not entries:
            continue
        terms = tuple(dict.fromkeys(str(entry.get("term") or "") for entry in entries))
        reasons = [str(entry.get("reason") or "") for entry in entries if entry.get("reason")]
        issues.append(
            A2ReiyuCsvAuditIssue(
                source="forbidden_terms_review",
                issue_code=f"forbidden_term_{enforcement}",
                severity=severity,
                business_usability_tier=tier,
                reason="；".join(dict.fromkeys(reasons)) or "命中A2礼遇业务词规则。",
                hits=terms,
                rewrite_required=rewrite_required,
            )
        )
    return issues


def _validate_headers(fieldnames: Iterable[str]) -> None:
    fields = set(fieldnames)
    if not fields.intersection(_TITLE_COLUMNS):
        raise ValueError("CSV缺少标题列，支持：标题/title")
    if not fields.intersection(_BODY_COLUMNS):
        raise ValueError("CSV缺少正文列，支持：正文/body/content")


def _read_csv_source(input_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with input_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        fieldnames = list(reader.fieldnames or [])
        _validate_headers(fieldnames)
        return fieldnames, list(reader)


def _write_audit_output(
    *,
    input_path: Path,
    output_path: Path,
    fieldnames: list[str],
    source_rows: list[Mapping[str, Any]],
    audited_rows: list[A2ReiyuCsvAuditRow],
) -> A2ReiyuCsvAuditSummary:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_fields = [*fieldnames, *[field for field in _AUDIT_COLUMNS if field not in fieldnames]]
    with output_path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=output_fields)
        writer.writeheader()
        for source_row, audit_row in zip(source_rows, audited_rows, strict=True):
            writer.writerow({**source_row, **_audit_columns(audit_row)})

    summary = A2ReiyuCsvAuditSummary(
        input_path=str(input_path),
        output_path=str(output_path),
        total_count=len(audited_rows),
        direct_pool_count=sum(row.business_usability_tier == "direct_pool" for row in audited_rows),
        light_fix_count=sum(
            row.business_usability_tier == "light_fix_usable" for row in audited_rows
        ),
        watch_count=sum(row.business_usability_tier == "watch" for row in audited_rows),
        hold_out_count=sum(row.business_usability_tier == "hold_out" for row in audited_rows),
    )
    output_path.with_suffix(".summary.json").write_text(
        json.dumps(summary.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def _parse_row_plan(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = _first_value(row, _PLAN_COLUMNS).strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _with_gold_review(
    row: A2ReiyuCsvAuditRow,
    review: ProductExperienceLLMReview,
) -> A2ReiyuCsvAuditRow:
    issues = list(row.issues)
    for issue in review.issues:
        issues.append(
            A2ReiyuCsvAuditIssue(
                source="a2_reiyu_gold_judge",
                issue_code=issue.code,
                severity=review.severity,
                business_usability_tier=review.business_usability_tier,
                reason=issue.reason or review.business_usability_reason or review.overall_reason,
                hits=(issue.evidence,) if issue.evidence else (),
                rewrite_required=review.rewrite_required,
            )
        )
    if review.business_usability_tier != "direct_pool" and not review.issues:
        issues.append(
            A2ReiyuCsvAuditIssue(
                source="a2_reiyu_gold_judge",
                issue_code="gold_semantic_review",
                severity=review.severity,
                business_usability_tier=review.business_usability_tier,
                reason=review.business_usability_reason or review.overall_reason,
                rewrite_required=review.rewrite_required,
            )
        )
    return _row_with_issues(row, issues)


def _with_gold_review_failure(row: A2ReiyuCsvAuditRow, error_message: str) -> A2ReiyuCsvAuditRow:
    return _row_with_issues(
        row,
        [
            *row.issues,
            A2ReiyuCsvAuditIssue(
                source="a2_reiyu_gold_judge",
                issue_code="gold_judge_unavailable",
                severity="rewrite",
                business_usability_tier="watch",
                reason=f"金标语义审核不可用：{error_message}",
            ),
        ],
    )


def _row_with_issues(
    row: A2ReiyuCsvAuditRow,
    issues: Iterable[A2ReiyuCsvAuditIssue],
) -> A2ReiyuCsvAuditRow:
    normalized_issues = tuple(issues)
    tier = max(
        (issue.business_usability_tier for issue in normalized_issues),
        key=lambda value: _TIER_RANK.get(value, 3),
        default="direct_pool",
    )
    severity = max(
        (issue.severity for issue in normalized_issues),
        key=lambda value: _SEVERITY_RANK.get(value, 3),
        default="pass",
    )
    return replace(
        row,
        business_usability_tier=tier,
        severity=severity,
        rewrite_required=any(issue.rewrite_required for issue in normalized_issues),
        issues=normalized_issues,
    )


def _first_value(row: Mapping[str, Any], names: Iterable[str]) -> str:
    for name in names:
        if name in row:
            return str(row.get(name) or "")
    return ""


def _audit_columns(row: A2ReiyuCsvAuditRow) -> dict[str, Any]:
    return {
        "CSV行号": row.csv_row_number,
        "审核结论": row.decision_label,
        "审核档位": row.business_usability_tier,
        "审核问题码": "|".join(issue.issue_code for issue in row.issues),
        "审核严重度": row.severity,
        "审核原因": "；".join(issue.reason for issue in row.issues),
        "命中片段": " || ".join(
            hit for issue in row.issues for hit in issue.hits if hit
        ),
        "需要改写": "是" if row.rewrite_required else "否",
    }
