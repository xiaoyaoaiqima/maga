import asyncio
from pathlib import Path

from app.core.database import async_session_factory
from app.services.product_experience_rule_service import (
    import_product_experience_rule_set,
)


CSV_PATH = Path(
    "/Users/luxifa/maga/outputs/a2_reiyu_full_raw_merged_20260721/"
    "a2礼遇UGC分享贴_原始槽位_认可路径分流.csv"
)
ASSET_KEY = "a2_reiyu_ugc_post_rules_v1"


async def main() -> None:
    async with async_session_factory() as session:
        result = await import_product_experience_rule_set(
            session,
            CSV_PATH.read_bytes(),
            source_name=CSV_PATH.name,
            asset_key=ASSET_KEY,
            display_name="a2礼遇UGC分享贴业务规则",
            created_by="codex-a2-reiyu-source-audit-v13",
        )
        await session.commit()
        print(
            {
                "asset_id": result.asset_id,
                "asset_key": result.asset_key,
                "rule_count": result.rule_count,
                "warnings": result.warnings,
            }
        )


if __name__ == "__main__":
    asyncio.run(main())
