"""Import a rs-crawler XHS export directory into a MAGA real-user example pool."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import async_session_factory  # noqa: E402
from app.services.real_user_example_pool_service import (  # noqa: E402
    DEFAULT_REAL_USER_EXAMPLE_POOL_ASSET_KEY,
    dump_import_result,
    import_real_user_example_pool_from_export_dir,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import XHS real-user examples into MAGA asset_registry.")
    parser.add_argument("export_dir", help="Directory containing xhs_notes_full.csv and xhs_comments_full.csv")
    parser.add_argument("--asset-key", default=DEFAULT_REAL_USER_EXAMPLE_POOL_ASSET_KEY)
    parser.add_argument("--display-name", default="母婴小红书真人原句池")
    parser.add_argument("--created-by", default="real-user-pool-importer")
    parser.add_argument("--dry-run", action="store_true")
    return parser


async def async_main() -> None:
    args = build_parser().parse_args()
    async with async_session_factory() as session:
        result = await import_real_user_example_pool_from_export_dir(
            session,
            args.export_dir,
            asset_key=args.asset_key,
            display_name=args.display_name,
            created_by=args.created_by,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            await session.rollback()
        else:
            await session.commit()
        print(dump_import_result(result))


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
