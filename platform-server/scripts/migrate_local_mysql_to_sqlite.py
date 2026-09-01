"""Migrate the current MAGA clean-schema data from local MySQL to SQLite."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import MetaData, Table, func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.content_agent_defaults import (
    DEFAULT_EXECUTOR_CODE,
    DIRECT_LLM_EXECUTOR_DISPLAY_NAME,
    DIRECT_LLM_EXECUTOR_INVOKE_URL,
    DIRECT_LLM_SUPPORTED_CAPABILITY_SPECS,
)
from app.models.base import Base
from app.models.maga_core import MAGA_STARTUP_TABLE_NAMES
from app.services.content_agent_bootstrap_service import seed_default_realtime_chat_agent


LEGACY_EXECUTOR_CODES = {"hermes_xhs_writer", "hermes_maga_worker"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-url",
        default="mysql+aiomysql://root@127.0.0.1:3306/maga",
        help="Local source MySQL URL",
    )
    parser.add_argument("--target-path", type=Path, required=True, help="SQLite file to replace")
    parser.add_argument("--batch-size", type=int, default=500)
    return parser


async def reflect_source_table(conn: AsyncConnection, table_name: str) -> Table:
    metadata = MetaData()
    return await conn.run_sync(
        lambda sync_conn: Table(table_name, metadata, autoload_with=sync_conn)
    )


def normalize_row(table_name: str, row: dict[str, Any]) -> dict[str, Any] | None:
    if table_name == "executor_registry":
        if row.get("executor_code") != DEFAULT_EXECUTOR_CODE:
            return None
        row.update(
            {
                "display_name": DIRECT_LLM_EXECUTOR_DISPLAY_NAME,
                "executor_type": "direct_llm",
                "profile_name": None,
                "invoke_url": DIRECT_LLM_EXECUTOR_INVOKE_URL,
                "supported_capabilities_json": DIRECT_LLM_SUPPORTED_CAPABILITY_SPECS,
                "config_json": None,
                "enabled": 1,
            }
        )
    elif table_name in {"content_agent_task", "content_agent_run"}:
        if row.get("executor_code") in LEGACY_EXECUTOR_CODES:
            row["executor_code"] = DEFAULT_EXECUTOR_CODE
        if table_name == "content_agent_run" and row.get("executor_type") == "hermes_profile":
            row["executor_type"] = "direct_llm"
    return row


async def migrate_table(
    source_conn: AsyncConnection,
    target_conn: AsyncConnection,
    table_name: str,
    *,
    batch_size: int,
) -> tuple[int, int]:
    source_table = await reflect_source_table(source_conn, table_name)
    target_table = Base.metadata.tables[table_name]
    common_columns = [column.name for column in target_table.columns if column.name in source_table.c]
    result = await source_conn.stream(select(*(source_table.c[name] for name in common_columns)))
    copied = 0
    skipped = 0
    batch: list[dict[str, Any]] = []

    async for source_row in result.mappings():
        normalized = normalize_row(table_name, dict(source_row))
        if normalized is None:
            skipped += 1
            continue
        batch.append(normalized)
        if len(batch) >= batch_size:
            await target_conn.execute(insert(target_table), batch)
            copied += len(batch)
            batch.clear()

    if batch:
        await target_conn.execute(insert(target_table), batch)
        copied += len(batch)
    return copied, skipped


async def migrate(source_url: str, target_path: Path, *, batch_size: int) -> None:
    target_path = target_path.resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path = target_path.with_name(f"{target_path.name}.migrating")
    if staging_path.exists():
        staging_path.unlink()

    source_engine = create_async_engine(source_url, future=True)
    target_engine = create_async_engine(f"sqlite+aiosqlite:///{staging_path}", future=True)
    counts: dict[str, int] = {}
    try:
        async with target_engine.begin() as target_conn:
            await target_conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    sync_conn,
                    tables=[Base.metadata.tables[name] for name in MAGA_STARTUP_TABLE_NAMES],
                )
            )
            await target_conn.execute(text("PRAGMA foreign_keys=OFF"))

        async with source_engine.connect() as source_conn:
            for table_name in MAGA_STARTUP_TABLE_NAMES:
                async with target_engine.begin() as target_conn:
                    copied, skipped = await migrate_table(
                        source_conn,
                        target_conn,
                        table_name,
                        batch_size=batch_size,
                    )
                counts[table_name] = copied
                suffix = f", skipped={skipped}" if skipped else ""
                print(f"{table_name}: copied={copied}{suffix}")

        async with target_engine.begin() as target_conn:
            await seed_default_realtime_chat_agent(target_conn, overwrite=False)

        async with target_engine.connect() as target_conn:
            for table_name, expected in counts.items():
                actual = int(
                    await target_conn.scalar(
                        select(func.count()).select_from(Base.metadata.tables[table_name])
                    )
                    or 0
                )
                if actual < expected:
                    raise RuntimeError(
                        f"row-count validation failed for {table_name}: expected at least {expected}, got {actual}"
                    )
            integrity = await target_conn.scalar(text("PRAGMA integrity_check"))
            if integrity != "ok":
                raise RuntimeError(f"SQLite integrity_check failed: {integrity}")
    finally:
        await source_engine.dispose()
        await target_engine.dispose()

    os.replace(staging_path, target_path)
    print(f"migration complete: {target_path}")


async def _amain() -> None:
    args = build_parser().parse_args()
    await migrate(args.source_url, args.target_path, batch_size=max(1, args.batch_size))


if __name__ == "__main__":
    asyncio.run(_amain())
