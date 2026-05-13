"""Import marketing workbook files into MAGA asset_registry.

This is a local/dev bootstrap utility for turning client training-rule workbooks
into MAGA-owned versioned assets. It uses the latest SQLAlchemy clean models and
should be replaced by Asset Steward API flows as the product surface matures.
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
from app.services.asset_import_service import import_yuanyue_training_rules


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import a marketing training-rule workbook into MAGA assets.")
    parser.add_argument("workbook", help="Path to .xlsx workbook")
    parser.add_argument("--database-url", default=None, help="Async SQLAlchemy database URL")
    parser.add_argument("--source-name", default=None, help="Human-readable source name")
    parser.add_argument("--asset-key", default="yuanyue", help="Asset key to write")
    parser.add_argument("--created-by", default="maga-asset-steward", help="Creator/audit label")
    parser.add_argument("--create-tables", action="store_true", help="Create asset tables before importing")
    return parser


async def _amain() -> None:
    args = build_parser().parse_args()
    workbook = Path(args.workbook).expanduser().resolve()
    database_url = args.database_url or settings.MYSQL_DATABASE_URL
    engine = create_async_engine(database_url, echo=False, future=True)
    try:
        if args.create_tables:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all, tables=[AssetRegistry.__table__, AssetImportRun.__table__])
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            result = await import_yuanyue_training_rules(
                session,
                workbook.read_bytes(),
                source_name=args.source_name or workbook.name,
                asset_key=args.asset_key,
                created_by=args.created_by,
            )
            await session.commit()
        print(
            json.dumps(
                {
                    "import_run_id": result.import_run_id,
                    "imported_assets": result.imported_assets,
                    "asset_keys": result.asset_keys,
                    "source_hash": result.source_hash,
                },
                ensure_ascii=False,
            )
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_amain())
