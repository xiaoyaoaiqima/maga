"""Worker-backed import service for MAGA marketing assets."""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE, normalize_executor_code
from app.models.content_agent import ExecutorRegistry
from app.models.maga_assets import AssetImportRun, AssetRegistry
from app.services.executor_invocation_service import (
    ExecutorInvocationClient,
    MockExecutorInvocationClient,
    build_invoke_envelope,
)


ASSET_IMPORT_CAPABILITY = "asset.import"
ASSET_IMPORT_SCHEMA_VERSION = "1"


@dataclass(slots=True)
class AssetImportResult:
    import_run_id: int | None
    imported_assets: int
    asset_keys: list[tuple[str, str]]
    source_hash: str


class AssetImportInvocationClient(Protocol):
    async def invoke(
        self,
        *,
        invoke_url: str,
        envelope: dict[str, Any],
        executor_token: str | None = None,
    ) -> Any:
        ...


async def import_yuanyue_training_rules(
    db: AsyncSession,
    workbook_content: bytes,
    *,
    source_name: str = "源悦种草活动-ai训练规则.xlsx",
    asset_key: str = "yuanyue",
    created_by: str = "maga-worker",
    executor_code: str | None = DEFAULT_EXECUTOR_CODE,
    invocation_client: AssetImportInvocationClient | None = None,
) -> AssetImportResult:
    """Import the 源悦 training-rule workbook through maga-worker asset.import.

    MAGA owns persistence and versioning, while the worker owns workbook parsing.
    This keeps future corpus layout changes inside the profile instead of
    spreading spreadsheet-specific logic through the platform API.
    """
    source_hash = hashlib.sha256(workbook_content).hexdigest()
    executor = await _require_executor(db, executor_code)
    client = invocation_client or _invocation_client_for_invoke_url(executor.invoke_url)
    envelope = build_invoke_envelope(
        run_id=0,
        task_id=0,
        stage_call_id=f"asset-import-{uuid4().hex[:12]}",
        capability=ASSET_IMPORT_CAPABILITY,
        schema_version=ASSET_IMPORT_SCHEMA_VERSION,
        run_token=f"asset-import-{uuid4().hex}",
        input_payload={
            "asset_key": asset_key,
            "source_name": source_name,
            "source_hash": source_hash,
            "source_content_base64": base64.b64encode(workbook_content).decode("ascii"),
            "parser_hint": "yuanyue_training_rules",
            "created_by": created_by,
        },
        callback_base_url="/api/v1/assets",
        deadline_at=None,
    )
    result = await client.invoke(
        invoke_url=executor.invoke_url or "",
        envelope=envelope,
        executor_token=_executor_token(executor),
    )
    if getattr(result, "status", "succeeded") != "succeeded":
        message = getattr(result, "error_message", None) or "asset.import failed"
        raise ValueError(message)

    output = getattr(result, "output", None) or {}
    package = _validate_asset_import_output(output, fallback_asset_key=asset_key, fallback_source_hash=source_hash)
    assets = await _persist_asset_package(
        db,
        package,
        source_name=source_name,
        source_uri=f"upload://{source_name}",
        created_by=created_by,
    )

    run = AssetImportRun(
        source_name=source_name,
        source_uri=f"upload://{source_name}",
        source_hash=package["source_hash"],
        status="succeeded",
        imported_assets=len(assets),
        summary_json={
            "asset_key": package["asset_key"],
            "asset_types": [asset.asset_type for asset in assets],
            "warnings": package["warnings"],
            "executor_code": executor.executor_code,
            "capability": ASSET_IMPORT_CAPABILITY,
        },
        created_by=created_by,
    )
    db.add(run)
    await db.flush()

    return AssetImportResult(
        import_run_id=run.id,
        imported_assets=len(assets),
        asset_keys=[(asset.asset_type, asset.asset_key) for asset in assets],
        source_hash=package["source_hash"],
    )


async def _require_executor(db: AsyncSession, executor_code: str | None) -> ExecutorRegistry:
    normalized = normalize_executor_code(executor_code)
    result = await db.execute(select(ExecutorRegistry).where(ExecutorRegistry.executor_code == normalized))
    executor = result.scalar_one_or_none()
    if executor is None or not executor.enabled:
        raise ValueError(f"executor not found: {normalized}")
    return executor


def _invocation_client_for_invoke_url(invoke_url: str | None):
    if invoke_url and invoke_url.startswith("mock://"):
        return MockExecutorInvocationClient()
    return ExecutorInvocationClient()


def _executor_token(executor: ExecutorRegistry) -> str | None:
    config = executor.config_json or {}
    token = config.get("executor_token") if isinstance(config, dict) else None
    return token if isinstance(token, str) and token else None


async def _persist_asset_package(
    db: AsyncSession,
    package: dict[str, Any],
    *,
    source_name: str,
    source_uri: str,
    created_by: str,
) -> list[AssetRegistry]:
    assets: list[AssetRegistry] = []
    for item in package["assets"]:
        asset_type = item["asset_type"]
        item_asset_key = item.get("asset_key") or package["asset_key"]
        version_no = await _next_version(db, asset_type, item_asset_key)
        # Each successful workbook import becomes the active source of truth for
        # that asset type/key. Older active versions stay queryable by id, but
        # are archived so UI options and generation planning do not mix schemas.
        await db.execute(
            update(AssetRegistry)
            .where(
                AssetRegistry.asset_type == asset_type,
                AssetRegistry.asset_key == item_asset_key,
                AssetRegistry.status == "active",
            )
            .values(status="archived")
        )
        asset = AssetRegistry(
            asset_type=asset_type,
            asset_key=item_asset_key,
            display_name=item.get("display_name"),
            version_no=version_no,
            status="active",
            asset_stage=item.get("asset_stage") or "production",
            source_name=source_name,
            source_uri=source_uri,
            source_hash=package["source_hash"],
            content_json=item["content_json"],
            metadata_json={
                "importer": "worker_asset_import_v1",
                "capability": ASSET_IMPORT_CAPABILITY,
                **(item.get("metadata_json") or {}),
            },
            created_by=created_by,
        )
        db.add(asset)
        assets.append(asset)
    await db.flush()
    return assets


async def _next_version(db: AsyncSession, asset_type: str, asset_key: str) -> int:
    result = await db.execute(
        select(AssetRegistry.version_no)
        .where(AssetRegistry.asset_type == asset_type, AssetRegistry.asset_key == asset_key)
        .order_by(AssetRegistry.version_no.desc())
        .limit(1)
    )
    current = result.scalar_one_or_none()
    return int(current or 0) + 1


def _validate_asset_import_output(
    output: dict[str, Any],
    *,
    fallback_asset_key: str,
    fallback_source_hash: str,
) -> dict[str, Any]:
    asset_key = _clean_text(output.get("asset_key")) or fallback_asset_key
    source_hash = _clean_text(output.get("source_hash")) or fallback_source_hash
    warnings = output.get("warnings") if isinstance(output.get("warnings"), list) else []
    raw_assets = output.get("assets")
    if not isinstance(raw_assets, list) or not raw_assets:
        raise ValueError("asset.import returned no assets")

    assets: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_assets, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"asset.import asset #{index} is not an object")
        asset_type = _clean_text(raw.get("asset_type"))
        content_json = raw.get("content_json")
        if not asset_type:
            raise ValueError(f"asset.import asset #{index} missing asset_type")
        if not isinstance(content_json, dict):
            raise ValueError(f"asset.import asset #{index} missing content_json")
        assets.append(
            {
                "asset_type": asset_type,
                "asset_key": _clean_text(raw.get("asset_key")) or asset_key,
                "display_name": _clean_text(raw.get("display_name")),
                "asset_stage": _clean_text(raw.get("asset_stage")) or "production",
                "content_json": content_json,
                "metadata_json": raw.get("metadata_json") if isinstance(raw.get("metadata_json"), dict) else {},
            }
        )

    return {
        "asset_key": asset_key,
        "source_hash": source_hash,
        "assets": assets,
        "warnings": [str(item) for item in warnings],
    }


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
