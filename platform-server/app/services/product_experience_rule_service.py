"""Import article business-rule packages into MAGA assets."""
from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from typing import Any

from openpyxl import load_workbook
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.maga_assets import AssetImportRun, AssetRegistry
from app.services.business_rule_asset_types import (
    ARTICLE_BUSINESS_RULE_ASSET_TYPE,
    ARTICLE_BUSINESS_RULE_ASSET_TYPES,
)

PRODUCT_EXPERIENCE_RULE_ASSET_TYPE = ARTICLE_BUSINESS_RULE_ASSET_TYPE
DEFAULT_PRODUCT_EXPERIENCE_ASSET_KEY = "yuanyue_product_experience"
DEFAULT_PRODUCT_EXPERIENCE_ACTIVITY_NAME = "美素佳儿源悦活动生文"
DEFAULT_PRODUCT_EXPERIENCE_BATCH_LIMIT = 10


@dataclass(slots=True)
class ProductExperienceRuleSetImportResult:
    import_run_id: int
    asset_id: int
    asset_key: str
    keyword_asset_key: str | None
    source_hash: str
    rule_count: int
    example_count: int
    warnings: list[str]


async def import_product_experience_rule_set(
    db: AsyncSession,
    file_content: bytes,
    *,
    source_name: str,
    asset_key: str = DEFAULT_PRODUCT_EXPERIENCE_ASSET_KEY,
    display_name: str | None = None,
    keyword_asset_key: str | None = None,
    created_by: str = "maga-operator",
) -> ProductExperienceRuleSetImportResult:
    """Persist article business-rule CSV/XLSX as a versioned asset."""
    normalized_asset_key = (
        asset_key or DEFAULT_PRODUCT_EXPERIENCE_ASSET_KEY
    ).strip() or DEFAULT_PRODUCT_EXPERIENCE_ASSET_KEY
    source_hash = hashlib.sha256(file_content).hexdigest()
    rows = _read_rule_rows(file_content, source_name=source_name)
    items = [_row_to_rule_item(row, index) for index, row in enumerate(rows, start=1)]
    items = [item for item in items if item is not None]
    if not items:
        raise ValueError("article business rule set is empty")

    example_count = sum(len(item.get("examples") or []) + len(item.get("supplements") or []) for item in items)
    warnings = _warnings_for_items(items)
    activity_name = (
        _infer_activity_name(items)
        or _infer_activity_name_from_display_name(display_name)
        or _infer_activity_name_from_asset_key(normalized_asset_key)
        or DEFAULT_PRODUCT_EXPERIENCE_ACTIVITY_NAME
    )
    word_count = _infer_word_count(items)
    content_json = {
        "rule_type": "business_rule",
        "rule_package_type": "business_rule",
        "business_rule_package": True,
        "activity_name": activity_name,
        "default_generation_count": DEFAULT_PRODUCT_EXPERIENCE_BATCH_LIMIT,
        "items": items,
    }
    if word_count:
        content_json["word_count"] = word_count
    normalized_keyword_asset_key = _normalize_keyword_asset_key(keyword_asset_key)
    if normalized_keyword_asset_key:
        content_json["keyword_asset_key"] = normalized_keyword_asset_key

    await db.execute(
        update(AssetRegistry)
        .where(
            AssetRegistry.asset_type.in_(ARTICLE_BUSINESS_RULE_ASSET_TYPES),
            AssetRegistry.asset_key == normalized_asset_key,
            AssetRegistry.status == "active",
        )
        .values(status="archived")
    )
    asset = AssetRegistry(
        asset_type=PRODUCT_EXPERIENCE_RULE_ASSET_TYPE,
        asset_key=normalized_asset_key,
        display_name=display_name or "源悦生文业务规则",
        version_no=await _next_asset_version(db, ARTICLE_BUSINESS_RULE_ASSET_TYPES, normalized_asset_key),
        status="active",
        asset_stage="production",
        source_name=source_name,
        source_uri=f"upload://{source_name}",
        source_hash=source_hash,
        content_json=content_json,
        metadata_json={
            "rule_type": "business_rule",
            "rule_package_type": "business_rule",
            "business_rule_package": True,
            "rule_count": len(items),
            "example_count": example_count,
            "keyword_asset_key": normalized_keyword_asset_key,
            "activity_name": activity_name,
            "word_count": word_count,
            "default_generation_count": DEFAULT_PRODUCT_EXPERIENCE_BATCH_LIMIT,
            "warnings": warnings,
        },
        created_by=created_by,
    )
    db.add(asset)
    await db.flush()

    run = AssetImportRun(
        source_name=source_name,
        source_uri=f"upload://{source_name}",
        source_hash=source_hash,
        status="succeeded",
        imported_assets=1,
        summary_json={
            "asset_key": normalized_asset_key,
            "asset_type": PRODUCT_EXPERIENCE_RULE_ASSET_TYPE,
            "rule_count": len(items),
            "example_count": example_count,
            "keyword_asset_key": normalized_keyword_asset_key,
            "activity_name": activity_name,
            "word_count": word_count,
            "default_generation_count": DEFAULT_PRODUCT_EXPERIENCE_BATCH_LIMIT,
            "warnings": warnings,
        },
        created_by=created_by,
    )
    db.add(run)
    await db.flush()
    return ProductExperienceRuleSetImportResult(
        import_run_id=run.id,
        asset_id=asset.id,
        asset_key=normalized_asset_key,
        keyword_asset_key=normalized_keyword_asset_key,
        source_hash=source_hash,
        rule_count=len(items),
        example_count=example_count,
        warnings=warnings,
    )


def product_experience_import_summary(result: ProductExperienceRuleSetImportResult) -> dict[str, Any]:
    return {
        "asset_type": PRODUCT_EXPERIENCE_RULE_ASSET_TYPE,
        "asset_key": result.asset_key,
        "keyword_asset_key": result.keyword_asset_key,
        "rule_count": result.rule_count,
        "example_count": result.example_count,
        "default_generation_count": DEFAULT_PRODUCT_EXPERIENCE_BATCH_LIMIT,
        "warnings": result.warnings,
    }


def _normalize_keyword_asset_key(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _infer_activity_name(items: list[dict[str, Any]]) -> str | None:
    for item in items:
        corpus = str(item.get("corpus") or "")
        match = re.search(r"活动[:：]\s*([^。\n；;]+)", corpus)
        if match:
            return match.group(1).strip()
    return None


def _infer_activity_name_from_display_name(display_name: str | None) -> str | None:
    text = str(display_name or "").strip()
    if not text:
        return None
    match = re.search(r"(\d{4}[^-_\s，,]*活动)", text)
    if match:
        return match.group(1).strip()
    if "旺玥" in text:
        return "0705旺玥活动"
    return None


def _infer_activity_name_from_asset_key(asset_key: str) -> str | None:
    if "wangyue" in str(asset_key or ""):
        return "0705旺玥活动"
    return None


def _infer_word_count(items: list[dict[str, Any]]) -> str | None:
    corpora = [str(item.get("corpus") or "") for item in items]
    has_mid = any("篇幅类型：中短文" in corpus for corpus in corpora)
    has_short = any("篇幅类型：短文" in corpus for corpus in corpora)
    mid_range = _first_match(
        corpora,
        r"(?:正文大约|可在)\s*(\d+)\s*-\s*(\d+)\s*字",
    )
    short_range = _first_match(corpora, r"篇幅类型：短文[\s\S]*?(?:正文大约|正文必须)?\s*(\d+)\s*-\s*(\d+)\s*字")
    if has_mid and has_short and mid_range and short_range:
        mid_start, mid_end = mid_range
        short_start, short_end = short_range
        return (
            f"逐条参考：中短文约{mid_start}-{mid_end}字，短一点但像真人不要硬扩写；"
            f"短文{short_start}-{short_end}字；标题不计；正文单段不换行"
        )
    return None


def _first_match(corpora: list[str], pattern: str) -> tuple[str, str] | None:
    for corpus in corpora:
        match = re.search(pattern, corpus)
        if match:
            return match.group(1), match.group(2)
    return None


def _read_rule_rows(file_content: bytes, *, source_name: str) -> list[dict[str, str]]:
    lower_name = source_name.lower()
    if lower_name.endswith(".xlsx"):
        return _read_xlsx_rows(file_content)
    if lower_name.endswith(".csv"):
        return _read_csv_rows(file_content)
    raise ValueError("only .csv and .xlsx files are supported")


def _read_csv_rows(file_content: bytes) -> list[dict[str, str]]:
    text = file_content.decode("utf-8-sig")
    content = "".join(line for line in text.splitlines(True) if not line.startswith("#"))
    return [
        {str(key or "").strip(): str(value or "").strip() for key, value in row.items()}
        for row in csv.DictReader(io.StringIO(content))
        if any(str(value or "").strip() for value in row.values())
    ]


def _read_xlsx_rows(file_content: bytes) -> list[dict[str, str]]:
    wb = load_workbook(io.BytesIO(file_content), data_only=True)
    ws = wb.active
    headers = [str(cell.value or "").strip() for cell in ws[1]]
    rows: list[dict[str, str]] = []
    for raw in ws.iter_rows(min_row=2, values_only=True):
        row = {header: str(value or "").strip() for header, value in zip(headers, raw) if header}
        if any(row.values()):
            rows.append(row)
    return rows


def _row_to_rule_item(row: dict[str, str], index: int) -> dict[str, Any] | None:
    raw_rule = (
        row.get("业务规则名称")
        or row.get("业务规则")
        or row.get("规则名称")
        or row.get("business_rule")
        or ""
    ).strip()
    corpus = (row.get("规则语料") or row.get("语料") or row.get("corpus") or "").strip()
    if not raw_rule or not corpus:
        return None
    has_canonical_examples = "示例" in row
    examples = (
        _line_examples(row.get("示例"))
        if has_canonical_examples
        else _line_examples(row.get("参考示例")) or _examples_from_corpus(corpus)
    )
    if not has_canonical_examples:
        examples.extend(_line_examples(row.get("补充参考")))
    return {
        "rule_id": f"business_rule_{index:03d}",
        "business_rule": raw_rule,
        "topic": raw_rule,
        "corpus": corpus,
        "examples": examples,
        "supplements": [],
        "source_row_no": index,
    }


def _examples_from_corpus(corpus: str) -> list[str]:
    if "可参考素材" not in corpus:
        return []
    after = re.split(r"可参考素材[:：]", corpus, maxsplit=1)
    if len(after) < 2:
        return []
    body = re.split(r"\n\s*注意[:：]", after[1], maxsplit=1)[0]
    return [_clean_example_line(line) for line in body.splitlines() if _clean_example_line(line)]


def _line_examples(value: str | None) -> list[str]:
    examples: list[str] = []
    for raw in (value or "").splitlines():
        line = _clean_example_line(raw)
        if line:
            examples.append(line)
    return examples


def _clean_example_line(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^[\-\*•]\s*", "", text)
    text = re.sub(r"^\d+[、.．]\s*", "", text)
    return text.strip()


def _warnings_for_items(items: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    missing_examples = [
        item["business_rule"]
        for item in items
        if not item.get("examples") and not item.get("supplements")
    ]
    if missing_examples:
        warnings.append(f"{len(missing_examples)} 条规则缺少示例")
    sparse_examples = [
        item["business_rule"]
        for item in items
        if 0 < len(item.get("examples") or []) + len(item.get("supplements") or []) < 3
    ]
    if sparse_examples:
        warnings.append(f"{len(sparse_examples)} 条规则示例少于3条")
    malformed_keys = [
        item["business_rule"]
        for item in items
        if not item.get("topic")
    ]
    if malformed_keys:
        warnings.append(f"{len(malformed_keys)} 条规则未填写体验主题")
    return warnings


async def _next_asset_version(db: AsyncSession, asset_types: tuple[str, ...], asset_key: str) -> int:
    result = await db.execute(
        select(AssetRegistry.version_no)
        .where(AssetRegistry.asset_type.in_(asset_types), AssetRegistry.asset_key == asset_key)
        .order_by(AssetRegistry.version_no.desc())
        .limit(1)
    )
    current = result.scalar_one_or_none()
    return int(current or 0) + 1
