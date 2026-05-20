"""Worker-backed import service for MAGA marketing assets."""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import yaml
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.content_agent_defaults import DEFAULT_EXECUTOR_CODE, normalize_executor_code
from app.models.content_agent import ExecutorRegistry
from app.models.maga_assets import AssetImportRun, AssetRegistry
from app.models.prompt_optimizer import PromptAsset, PromptEvaluation, PromptIssue, PromptOptimizerRun, PromptVersion
from app.services.executor_invocation_service import (
    ExecutorInvocationClient,
    MockExecutorInvocationClient,
    build_invoke_envelope,
)


ASSET_IMPORT_CAPABILITY = "asset.import"
ASSET_IMPORT_SCHEMA_VERSION = "1"
WORKER_STATIC_ASSET_SOURCE_NAME = "maga-worker-static-assets"


@dataclass(slots=True)
class AssetImportResult:
    import_run_id: int | None
    imported_assets: int
    asset_keys: list[tuple[str, str]]
    source_hash: str


@dataclass(slots=True)
class WorkerStaticAssetImportResult:
    import_run_id: int | None
    imported_prompts: int
    imported_assets: int
    prompt_names: list[str]
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


async def import_maga_worker_static_assets(
    db: AsyncSession,
    workspace_path: str | Path,
    *,
    source_name: str = WORKER_STATIC_ASSET_SOURCE_NAME,
    created_by: str = "maga-asset-steward",
) -> WorkerStaticAssetImportResult:
    """Import stable maga-worker prompt/corpus files into MAGA-managed stores.

    Worker outputs and executable code are intentionally excluded. This first
    import layer gives MAGA versioned ownership of static prompt assets while
    the worker can keep reading local fallback files until the runtime contract
    starts carrying prompt bundles.
    """
    workspace = Path(workspace_path).expanduser().resolve()
    if not workspace.exists() or not workspace.is_dir():
        raise ValueError(f"worker workspace not found: {workspace}")

    active_expert_codes = _active_worker_expert_codes(workspace)
    prompt_files = _discover_worker_prompt_files(workspace, active_expert_codes)
    registry_files = _discover_worker_registry_files(workspace, active_expert_codes)
    source_hash = _combined_file_hash([*prompt_files, *registry_files])

    prompt_names: list[str] = []
    asset_keys: list[tuple[str, str]] = []
    changed_prompts = 0
    changed_assets = 0

    await _purge_legacy_worker_prompt_assets(db)
    await _archive_inactive_worker_expert_assets(db, active_expert_codes)

    for path in prompt_files:
        prompt = await _upsert_prompt_file(db, workspace, path, source_name=source_name, created_by=created_by)
        prompt_names.append(prompt.name)
        if getattr(prompt, "_maga_import_changed", False):
            changed_prompts += 1

    for path in registry_files:
        asset = await _upsert_registry_file(db, workspace, path, source_name=source_name, created_by=created_by)
        asset_keys.append((asset.asset_type, asset.asset_key))
        if getattr(asset, "_maga_import_changed", False):
            changed_assets += 1

    run = AssetImportRun(
        source_name=source_name,
        source_uri=f"file://{workspace}",
        source_hash=source_hash,
        status="succeeded",
        imported_assets=changed_prompts + changed_assets,
        summary_json={
            "workspace": str(workspace),
            "imported_prompts": changed_prompts,
            "imported_assets": changed_assets,
            "prompt_names": prompt_names,
            "asset_keys": asset_keys,
            "excluded_dirs": ["outputs", "tests", "__pycache__", ".pytest_cache"],
        },
        created_by=created_by,
    )
    db.add(run)
    await db.flush()

    return WorkerStaticAssetImportResult(
        import_run_id=run.id,
        imported_prompts=changed_prompts,
        imported_assets=changed_assets,
        prompt_names=prompt_names,
        asset_keys=asset_keys,
        source_hash=source_hash,
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


def _active_worker_expert_codes(workspace: Path) -> set[str]:
    registry_path = workspace / "experts" / "_registry.yaml"
    if not registry_path.exists():
        return set()
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    experts = data.get("experts") if isinstance(data, dict) else {}
    if not isinstance(experts, dict):
        return set()
    return {
        code
        for code, item in experts.items()
        if isinstance(code, str) and isinstance(item, dict) and item.get("type") == "AE" and item.get("must") is True
    }


def _discover_worker_prompt_files(workspace: Path, active_expert_codes: set[str] | None = None) -> list[Path]:
    candidates: list[Path] = []
    active_expert_codes = active_expert_codes or set()
    system_prompt = workspace / "system.md"
    if system_prompt.exists():
        candidates.append(system_prompt)
    candidates.extend(sorted((workspace / "ge_writer").glob("*.md")))
    for expert_dir in sorted((workspace / "experts").glob("*")):
        if not expert_dir.is_dir() or expert_dir.name.startswith("_"):
            continue
        if active_expert_codes and expert_dir.name not in active_expert_codes:
            continue
        for file_name in ("system.md", "score_rubric.md"):
            path = expert_dir / file_name
            if path.exists():
                candidates.append(path)
    return candidates


def _discover_worker_registry_files(workspace: Path, active_expert_codes: set[str] | None = None) -> list[Path]:
    candidates: list[Path] = []
    active_expert_codes = active_expert_codes or set()
    for path in [workspace / "experts" / "_registry.yaml", workspace / "experts" / "_brief_types.yaml"]:
        if path.exists():
            candidates.append(path)
    for expert_dir in sorted((workspace / "experts").glob("*")):
        if not expert_dir.is_dir() or expert_dir.name.startswith("_"):
            continue
        if active_expert_codes and expert_dir.name not in active_expert_codes:
            continue
        path = expert_dir / "corpus.yaml"
        if path.exists():
            candidates.append(path)
    return candidates


async def _upsert_prompt_file(
    db: AsyncSession,
    workspace: Path,
    path: Path,
    *,
    source_name: str,
    created_by: str,
) -> PromptAsset:
    rel = _relative_worker_path(workspace, path)
    content = path.read_text(encoding="utf-8")
    source_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    name = _prompt_name_for_path(rel)
    prompt_type = _prompt_type_for_path(rel)
    tags = _prompt_tags_for_path(rel)
    description = f"Imported from maga-worker static file: {rel}"

    result = await db.execute(select(PromptAsset).where(PromptAsset.name == name, PromptAsset.is_deleted == 0))
    prompt = result.scalar_one_or_none()
    if prompt is None:
        prompt = PromptAsset(
            name=name,
            prompt_type=prompt_type,
            description=description,
            tags=tags,
        )
        db.add(prompt)
        await db.flush()
        version = PromptVersion(
            prompt_id=prompt.id,
            version_no=1,
            content=content,
            change_summary=f"导入 {rel}",
            created_by=created_by,
        )
        db.add(version)
        await db.flush()
        prompt.current_version_id = version.id
        prompt._maga_import_changed = True
        return prompt

    current = await db.get(PromptVersion, prompt.current_version_id) if prompt.current_version_id else None
    if current is not None and hashlib.sha256(current.content.encode("utf-8")).hexdigest() == source_hash:
        prompt._maga_import_changed = False
        return prompt

    next_version_no = await _next_prompt_version(db, prompt.id)
    version = PromptVersion(
        prompt_id=prompt.id,
        version_no=next_version_no,
        content=content,
        parent_version_id=prompt.current_version_id,
        change_summary=f"同步 {rel}",
        created_by=created_by,
    )
    db.add(version)
    await db.flush()
    prompt.prompt_type = prompt_type
    prompt.description = description
    prompt.tags = tags
    prompt.current_version_id = version.id
    prompt._maga_import_changed = True
    return prompt


async def _purge_legacy_worker_prompt_assets(db: AsyncSession) -> None:
    """Remove prompt names that were replaced by the system.md scheme."""
    result = await db.execute(
        select(PromptAsset).where(
            (PromptAsset.name == "xhs_writer.ge.soul") | (PromptAsset.name.like("xhs_writer.ae.%.persona")),
        )
    )
    legacy_prompt_ids = [prompt.id for prompt in result.scalars().all()]
    if not legacy_prompt_ids:
        return
    await db.execute(delete(PromptEvaluation).where(PromptEvaluation.prompt_id.in_(legacy_prompt_ids)))
    await db.execute(delete(PromptOptimizerRun).where(PromptOptimizerRun.prompt_id.in_(legacy_prompt_ids)))
    await db.execute(delete(PromptIssue).where(PromptIssue.prompt_id.in_(legacy_prompt_ids)))
    await db.execute(delete(PromptVersion).where(PromptVersion.prompt_id.in_(legacy_prompt_ids)))
    await db.execute(delete(PromptAsset).where(PromptAsset.id.in_(legacy_prompt_ids)))


async def _archive_inactive_worker_expert_assets(db: AsyncSession, active_expert_codes: set[str]) -> None:
    """Retire worker AE prompt/corpus assets that are not in the active AE set."""
    result = await db.execute(select(PromptAsset).where(PromptAsset.name.like("xhs_writer.ae.%")))
    inactive_prompts = [
        prompt
        for prompt in result.scalars().all()
        if _expert_code_from_prompt_name(prompt.name) not in active_expert_codes
    ]
    prompt_ids = [prompt.id for prompt in inactive_prompts]
    if prompt_ids:
        await db.execute(delete(PromptEvaluation).where(PromptEvaluation.prompt_id.in_(prompt_ids)))
        await db.execute(delete(PromptOptimizerRun).where(PromptOptimizerRun.prompt_id.in_(prompt_ids)))
        await db.execute(delete(PromptIssue).where(PromptIssue.prompt_id.in_(prompt_ids)))
        await db.execute(delete(PromptVersion).where(PromptVersion.prompt_id.in_(prompt_ids)))
        await db.execute(delete(PromptAsset).where(PromptAsset.id.in_(prompt_ids)))

    result = await db.execute(
        select(AssetRegistry).where(AssetRegistry.asset_type == "expert_corpus", AssetRegistry.status == "active")
    )
    inactive_asset_ids = [
        asset.id for asset in result.scalars().all() if asset.asset_key not in active_expert_codes
    ]
    if inactive_asset_ids:
        await db.execute(update(AssetRegistry).where(AssetRegistry.id.in_(inactive_asset_ids)).values(status="archived"))


def _expert_code_from_prompt_name(name: str) -> str | None:
    parts = name.split(".")
    if len(parts) < 4 or parts[:2] != ["xhs_writer", "ae"]:
        return None
    return parts[2]


async def _upsert_registry_file(
    db: AsyncSession,
    workspace: Path,
    path: Path,
    *,
    source_name: str,
    created_by: str,
) -> AssetRegistry:
    rel = _relative_worker_path(workspace, path)
    raw = path.read_text(encoding="utf-8")
    source_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    asset_type, asset_key, display_name = _registry_asset_identity(rel)
    content_json = _yaml_file_content(raw, rel)

    current = await _latest_registry_asset_any_stage(db, asset_type, asset_key)
    if current is not None and current.source_hash == source_hash and current.status == "active":
        current._maga_import_changed = False
        return current

    await db.execute(
        update(AssetRegistry)
        .where(
            AssetRegistry.asset_type == asset_type,
            AssetRegistry.asset_key == asset_key,
            AssetRegistry.status == "active",
        )
        .values(status="archived")
    )
    asset = AssetRegistry(
        asset_type=asset_type,
        asset_key=asset_key,
        display_name=display_name,
        version_no=await _next_version(db, asset_type, asset_key),
        status="active",
        asset_stage="production",
        source_name=source_name,
        source_uri=f"file://{path}",
        source_hash=source_hash,
        content_json=content_json,
        metadata_json={
            "importer": "worker_static_assets_v1",
            "worker_path": rel,
        },
        created_by=created_by,
    )
    db.add(asset)
    await db.flush()
    asset._maga_import_changed = True
    return asset


async def _latest_registry_asset_any_stage(db: AsyncSession, asset_type: str, asset_key: str) -> AssetRegistry | None:
    result = await db.execute(
        select(AssetRegistry)
        .where(
            AssetRegistry.asset_type == asset_type,
            AssetRegistry.asset_key == asset_key,
        )
        .order_by(AssetRegistry.version_no.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _next_prompt_version(db: AsyncSession, prompt_id: int) -> int:
    result = await db.execute(select(func.max(PromptVersion.version_no)).where(PromptVersion.prompt_id == prompt_id))
    return int(result.scalar_one_or_none() or 0) + 1


def _relative_worker_path(workspace: Path, path: Path) -> str:
    try:
        return str(path.relative_to(workspace))
    except ValueError:
        return f"../{path.name}"


def _prompt_name_for_path(rel: str) -> str:
    parts = Path(rel).parts
    if rel == "system.md":
        return "xhs_writer.ge.system"
    if len(parts) >= 2 and parts[0] == "ge_writer":
        return f"xhs_writer.ge.{Path(rel).stem}"
    if len(parts) >= 3 and parts[0] == "experts":
        return f"xhs_writer.ae.{parts[1]}.{Path(rel).stem}"
    return f"xhs_writer.{Path(rel).stem}"


def _prompt_type_for_path(rel: str) -> str:
    if rel.startswith("ge_writer/") or rel == "system.md":
        return "generation"
    if rel.endswith("/system.md") or rel.endswith("/score_rubric.md"):
        return "critic"
    return "other"


def _prompt_tags_for_path(rel: str) -> list[str]:
    tags = ["maga-worker", "xhs-writer"]
    parts = Path(rel).parts
    if rel == "system.md":
        return [*tags, "ge", "system"]
    if len(parts) >= 2 and parts[0] == "ge_writer":
        return [*tags, "ge", Path(rel).stem]
    if len(parts) >= 3 and parts[0] == "experts":
        return [*tags, "ae", parts[1], Path(rel).stem]
    return tags


def _registry_asset_identity(rel: str) -> tuple[str, str, str]:
    parts = Path(rel).parts
    if rel == "experts/_registry.yaml":
        return "expert_registry", "xhs_writer", "xhs-writer Expert 注册表"
    if rel == "experts/_brief_types.yaml":
        return "brief_type_registry", "xhs_writer", "xhs-writer Brief 类型注册表"
    if len(parts) >= 3 and parts[0] == "experts" and parts[2] == "corpus.yaml":
        expert_code = parts[1]
        return "expert_corpus", expert_code, f"{expert_code} Expert 语料"
    return "worker_static_yaml", rel.replace("/", "."), rel


def _yaml_file_content(raw: str, rel: str) -> dict[str, Any]:
    parsed = yaml.safe_load(raw) if raw.strip() else {}
    return {
        "worker_path": rel,
        "content": parsed if isinstance(parsed, (dict, list)) else raw,
    }


def _combined_file_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: str(item)):
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


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
