"""Import product-experience business rule packages into MAGA assets."""
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

PRODUCT_EXPERIENCE_RULE_ASSET_TYPE = "product_experience_rule_set"
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
    """Persist 产品使用体验 CSV/XLSX as a versioned business-rule asset."""
    normalized_asset_key = (
        asset_key or DEFAULT_PRODUCT_EXPERIENCE_ASSET_KEY
    ).strip() or DEFAULT_PRODUCT_EXPERIENCE_ASSET_KEY
    source_hash = hashlib.sha256(file_content).hexdigest()
    rows = _read_rule_rows(file_content, source_name=source_name)
    items = [_row_to_rule_item(row, index) for index, row in enumerate(rows, start=1)]
    items = [item for item in items if item is not None]
    if not items:
        raise ValueError("product experience rule set is empty")

    example_count = sum(len(item.get("examples") or []) for item in items)
    warnings = _warnings_for_items(items)
    content_json = {
        "rule_type": "product_experience",
        "rule_package_type": "product_experience",
        "business_rule_package": True,
        "activity_name": DEFAULT_PRODUCT_EXPERIENCE_ACTIVITY_NAME,
        "default_generation_count": DEFAULT_PRODUCT_EXPERIENCE_BATCH_LIMIT,
        "items": items,
    }
    normalized_keyword_asset_key = _normalize_keyword_asset_key(keyword_asset_key)
    if normalized_keyword_asset_key:
        content_json["keyword_asset_key"] = normalized_keyword_asset_key

    await db.execute(
        update(AssetRegistry)
        .where(
            AssetRegistry.asset_type == PRODUCT_EXPERIENCE_RULE_ASSET_TYPE,
            AssetRegistry.asset_key == normalized_asset_key,
            AssetRegistry.status == "active",
        )
        .values(status="archived")
    )
    asset = AssetRegistry(
        asset_type=PRODUCT_EXPERIENCE_RULE_ASSET_TYPE,
        asset_key=normalized_asset_key,
        display_name=display_name or "源悦-业务规则（产品使用体验）",
        version_no=await _next_asset_version(db, PRODUCT_EXPERIENCE_RULE_ASSET_TYPE, normalized_asset_key),
        status="active",
        asset_stage="production",
        source_name=source_name,
        source_uri=f"upload://{source_name}",
        source_hash=source_hash,
        content_json=content_json,
        metadata_json={
            "rule_type": "product_experience",
            "rule_package_type": "product_experience",
            "business_rule_package": True,
            "rule_count": len(items),
            "example_count": example_count,
            "keyword_asset_key": normalized_keyword_asset_key,
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
    product_experience = row.get("产品使用体验", "").strip()
    corpus = row.get("语料", "").strip()
    if not product_experience or not corpus:
        return None
    baby_stage, use_duration, topic = _split_product_experience_key(product_experience)
    return {
        "rule_id": f"product_experience_{index:03d}",
        "product_experience": product_experience,
        "baby_stage": baby_stage,
        "use_duration": use_duration,
        "topic": topic,
        "corpus": corpus,
        "examples": _examples_from_corpus(corpus),
        "source_row_no": index,
    }


def _split_product_experience_key(value: str) -> tuple[str, str, str]:
    parts = [part.strip() for part in re.split(r"[,，]", value or "") if part.strip()]
    if len(parts) >= 3:
        return parts[0], parts[1], "，".join(parts[2:])
    return "", "", ""


def _examples_from_corpus(corpus: str) -> list[str]:
    if "可参考素材" not in corpus:
        return []
    after = re.split(r"可参考素材[:：]", corpus, maxsplit=1)
    if len(after) < 2:
        return []
    body = re.split(r"\n\s*注意[:：]", after[1], maxsplit=1)[0]
    return [_clean_example_line(line) for line in body.splitlines() if _clean_example_line(line)]


def _clean_example_line(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^[\-\*•]\s*", "", text)
    text = re.sub(r"^\d+[、.．]\s*", "", text)
    return text.strip()


def _warnings_for_items(items: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    missing_examples = [item["product_experience"] for item in items if not item.get("examples")]
    if missing_examples:
        warnings.append(f"{len(missing_examples)} 条规则缺少可参考素材")
    malformed_keys = [
        item["product_experience"]
        for item in items
        if not item.get("baby_stage") or not item.get("use_duration") or not item.get("topic")
    ]
    if malformed_keys:
        warnings.append(f"{len(malformed_keys)} 条规则未按“月龄，使用时间，体验主题”填写")
    hard_rule_rows = [
        item["product_experience"]
        for item in items
        if re.search(r"必须|只写|固定数字|生成重点必须|可写方向", item.get("corpus") or "")
    ]
    if hard_rule_rows:
        warnings.append(f"{len(hard_rule_rows)} 条规则含较硬约束，后续可用示例扩展替代加规则")
    return warnings


async def _next_asset_version(db: AsyncSession, asset_type: str, asset_key: str) -> int:
    result = await db.execute(
        select(AssetRegistry.version_no)
        .where(AssetRegistry.asset_type == asset_type, AssetRegistry.asset_key == asset_key)
        .order_by(AssetRegistry.version_no.desc())
        .limit(1)
    )
    current = result.scalar_one_or_none()
    return int(current or 0) + 1
