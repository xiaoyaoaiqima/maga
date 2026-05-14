"""Import maga-worker static prompts and corpora into MAGA-managed stores.

By default this runs against an in-memory database as a safe dry-run. Pass
--commit to write into the configured MAGA database.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.base import Base
from app.models.maga_assets import AssetImportRun, AssetRegistry
from app.models.prompt_optimizer import PromptAsset, PromptVersion
from app.services.asset_import_service import (
    WORKER_STATIC_ASSET_SOURCE_NAME,
    import_maga_worker_static_assets,
)


DEFAULT_WORKER_WORKSPACE = str(Path(__file__).resolve().parents[2] / "worker" / "profiles" / "maga-worker")
STATIC_ASSET_TABLES = [
    PromptAsset.__table__,
    PromptVersion.__table__,
    AssetRegistry.__table__,
    AssetImportRun.__table__,
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import maga-worker static prompts/corpora into MAGA.")
    parser.add_argument("--workspace", default=DEFAULT_WORKER_WORKSPACE, help="maga-worker workspace path")
    parser.add_argument("--database-url", default=None, help="Async SQLAlchemy database URL, used only with --commit")
    parser.add_argument("--source-name", default=WORKER_STATIC_ASSET_SOURCE_NAME, help="Import source name")
    parser.add_argument("--created-by", default="maga-asset-steward", help="Creator/audit label")
    parser.add_argument("--create-tables", action="store_true", help="Create target tables before importing")
    parser.add_argument("--commit", action="store_true", help="Persist import into the MAGA database")
    return parser


async def _amain() -> None:
    args = build_parser().parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    if args.commit:
        database_url = args.database_url or settings.MYSQL_DATABASE_URL
    else:
        database_url = "sqlite+aiosqlite:///:memory:"

    engine = create_async_engine(database_url, echo=False, future=True)
    try:
        if args.create_tables or not args.commit:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all, tables=STATIC_ASSET_TABLES)

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            result = await import_maga_worker_static_assets(
                session,
                workspace,
                source_name=args.source_name,
                created_by=args.created_by,
            )
            if args.commit:
                await session.commit()
            else:
                await session.rollback()

        print(
            json.dumps(
                {
                    "mode": "commit" if args.commit else "dry_run",
                    "committed": bool(args.commit),
                    "workspace": str(workspace),
                    "import_run_id": result.import_run_id if args.commit else None,
                    "imported_prompts": result.imported_prompts,
                    "imported_assets": result.imported_assets,
                    "prompt_names": result.prompt_names,
                    "asset_keys": result.asset_keys,
                    "source_hash": result.source_hash,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_amain())
