"""Create the MAGA clean schema from the latest core SQLAlchemy models.

This intentionally bypasses the historical Alembic chain from the legacy system.
Use it only for clean local/dev databases or controlled baseline setup.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Iterable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy import insert

from app.core.content_agent_defaults import (
    DEFAULT_EXECUTOR_CODE,
    LEGACY_XHS_WRITER_DISPLAY_NAME,
    LEGACY_XHS_WRITER_EXECUTOR_CODE,
    MAGA_WORKER_DISPLAY_NAME,
    MAGA_WORKER_INVOKE_URL,
    MAGA_WORKER_PROFILE_NAME,
    MAGA_WORKER_SUPPORTED_CAPABILITY_SPECS,
    XHS_CAPABILITY_SPECS,
)
from app.core.config import settings
from app.models.content_agent import ExecutorRegistry
from app.models.base import Base
from app.models.maga_core import MAGA_CORE_TABLE_NAMES  # noqa: F401 - importing registers clean models


def _selected_tables() -> list:
    return [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]


async def seed_clean_schema(
    conn: AsyncConnection,
    *,
    maga_worker_invoke_url: str = MAGA_WORKER_INVOKE_URL,
    xhs_writer_invoke_url: str | None = None,
    executor_token: str | None = "test-token",
) -> None:
    """Seed baseline executor registry rows for the clean schema."""
    legacy_invoke_url = xhs_writer_invoke_url or maga_worker_invoke_url
    config_json = {"executor_token": executor_token} if executor_token else None
    rows = [
        {
            "executor_code": DEFAULT_EXECUTOR_CODE,
            "display_name": MAGA_WORKER_DISPLAY_NAME,
            "executor_type": "hermes_profile",
            "profile_name": MAGA_WORKER_PROFILE_NAME,
            "protocol_version": "0.1",
            "invoke_url": maga_worker_invoke_url,
            "supported_capabilities_json": MAGA_WORKER_SUPPORTED_CAPABILITY_SPECS,
            "config_json": config_json,
            "enabled": 1,
        },
        {
            "executor_code": LEGACY_XHS_WRITER_EXECUTOR_CODE,
            "display_name": LEGACY_XHS_WRITER_DISPLAY_NAME,
            "executor_type": "hermes_profile",
            "profile_name": MAGA_WORKER_PROFILE_NAME,
            "protocol_version": "0.1",
            "invoke_url": legacy_invoke_url,
            "supported_capabilities_json": XHS_CAPABILITY_SPECS,
            "config_json": config_json,
            "enabled": 1,
        },
    ]
    for values in rows:
        if conn.dialect.name == "mysql":
            stmt = mysql_insert(ExecutorRegistry).values(**values)
            stmt = stmt.on_duplicate_key_update(**values)
        else:
            stmt = insert(ExecutorRegistry).values(**values)
        await conn.execute(stmt)


async def create_clean_schema(
    engine: AsyncEngine,
    *,
    drop: bool = False,
    seed: bool = False,
    maga_worker_invoke_url: str = MAGA_WORKER_INVOKE_URL,
    xhs_writer_invoke_url: str | None = None,
    executor_token: str | None = "test-token",
) -> None:
    """Create the clean MAGA core schema using current SQLAlchemy model metadata."""
    tables = _selected_tables()
    async with engine.begin() as conn:
        if drop:
            await conn.run_sync(lambda sync_conn: Base.metadata.drop_all(sync_conn, tables=tables))
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
        if seed:
            await seed_clean_schema(
                conn,
                maga_worker_invoke_url=maga_worker_invoke_url,
                xhs_writer_invoke_url=xhs_writer_invoke_url,
                executor_token=executor_token,
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create MAGA clean core schema without historical migrations.")
    parser.add_argument("--database-url", default=None, help="Async SQLAlchemy database URL")
    parser.add_argument("--drop", action="store_true", help="Drop clean core tables before creating them")
    parser.add_argument("--seed", action="store_true", help="Seed baseline executor registry rows")
    parser.add_argument("--maga-worker-invoke-url", default=MAGA_WORKER_INVOKE_URL, help="Invoke URL for hermes_maga_worker executor seed")
    parser.add_argument(
        "--executor-token",
        default="test-token",
        help="Local dev executor token written to executor_registry.config_json; pass an empty string to omit",
    )
    parser.add_argument(
        "--xhs-writer-invoke-url",
        default=None,
        help="Deprecated legacy alias invoke URL; defaults to --maga-worker-invoke-url",
    )
    return parser


async def _amain(argv: Iterable[str] | None = None) -> None:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    database_url = args.database_url or settings.MYSQL_DATABASE_URL
    engine = create_async_engine(database_url, echo=False, future=True)
    try:
        await create_clean_schema(
            engine,
            drop=args.drop,
            seed=args.seed,
            maga_worker_invoke_url=args.maga_worker_invoke_url,
            xhs_writer_invoke_url=args.xhs_writer_invoke_url,
            executor_token=args.executor_token or None,
        )
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
