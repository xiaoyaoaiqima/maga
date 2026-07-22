import asyncio

from app.core.database import async_session_factory, engine
from app.services.business_forbidden_term_service import (
    A2_REIYU_UGC_POST_ASSET_KEY,
    BusinessForbiddenTermService,
)
from app.services.content_agent_bootstrap_service import seed_a2_reiyu_forbidden_terms


async def main() -> None:
    async with engine.begin() as conn:
        await seed_a2_reiyu_forbidden_terms(conn)

    async with async_session_factory() as session:
        service = BusinessForbiddenTermService(session)
        entries = await service.list_entries(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            include_default=False,
        )
        anxiety_entry = next((entry for entry in entries if entry["term"] == "焦虑"), None)
        if anxiety_entry and anxiety_entry.get("enabled") is not False:
            await service.set_enabled(
                asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
                term="焦虑",
                enabled=False,
                created_by="codex-a2-reiyu-negative-boundary-v16",
            )
            await session.commit()

        active_entries = await service.list_entries(
            asset_key=A2_REIYU_UGC_POST_ASSET_KEY,
            include_default=False,
        )
        by_term = {entry["term"]: entry for entry in active_entries}
        print(
            {
                "焦虑_enabled": by_term.get("焦虑", {}).get("enabled"),
                "质量问题": by_term.get("质量问题", {}).get("enforcement"),
                "踩雷": by_term.get("踩雷", {}).get("enforcement"),
                "active_term_count": sum(
                    entry.get("enabled") is not False for entry in active_entries
                ),
            }
        )


if __name__ == "__main__":
    asyncio.run(main())
