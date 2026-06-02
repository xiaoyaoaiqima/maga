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

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.core.content_agent_defaults import (
    MAGA_WORKER_INVOKE_URL,
)
from app.core.config import settings
from app.models.base import Base
from app.models.maga_core import MAGA_CORE_TABLE_NAMES  # noqa: F401 - importing registers clean models
from app.services.content_agent_bootstrap_service import seed_default_content_agent_executors


def _selected_tables() -> list:
    return [Base.metadata.tables[name] for name in MAGA_CORE_TABLE_NAMES]


async def seed_clean_schema(
    conn: AsyncConnection,
    *,
    maga_worker_invoke_url: str = MAGA_WORKER_INVOKE_URL,
    executor_token: str | None = "test-token",
) -> None:
    """Seed baseline executor registry rows for the clean schema."""
    await seed_default_content_agent_executors(
        conn,
        maga_worker_invoke_url=maga_worker_invoke_url,
        executor_token=executor_token,
        overwrite=True,
    )


async def create_clean_schema(
    engine: AsyncEngine,
    *,
    drop: bool = False,
    seed: bool = False,
    maga_worker_invoke_url: str = MAGA_WORKER_INVOKE_URL,
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
            executor_token=args.executor_token or None,
        )
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
