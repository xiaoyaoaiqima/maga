"""Services for MAGA asset registry and Asset Steward proposal workflow."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.maga_assets import AssetChangeProposal, AssetChangeRequest, AssetRegistry
from app.schemas.assets import AssetChangeProposalCreate, AssetChangeRequestCreate


class AssetService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_assets(self, *, asset_type: str | None = None, asset_key: str | None = None, status: str = "active") -> list[AssetRegistry]:
        stmt = select(AssetRegistry)
        if asset_type:
            stmt = stmt.where(AssetRegistry.asset_type == asset_type)
        if asset_key:
            stmt = stmt.where(AssetRegistry.asset_key == asset_key)
        if status:
            stmt = stmt.where(AssetRegistry.status == status)
        stmt = stmt.order_by(AssetRegistry.asset_type, AssetRegistry.asset_key, AssetRegistry.version_no.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_asset(self, asset_type: str, asset_key: str) -> AssetRegistry | None:
        result = await self.db.execute(
            select(AssetRegistry)
            .where(AssetRegistry.asset_type == asset_type, AssetRegistry.asset_key == asset_key, AssetRegistry.status == "active")
            .order_by(AssetRegistry.version_no.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_change_request(self, payload: AssetChangeRequestCreate) -> AssetChangeRequest:
        request = AssetChangeRequest(
            source_text=payload.source_text,
            requester=payload.requester,
            context_json=payload.context_json,
            status="pending",
            created_by=payload.created_by,
        )
        self.db.add(request)
        await self.db.flush()
        return request

    async def create_change_proposal(self, payload: AssetChangeProposalCreate) -> AssetChangeProposal:
        proposal = AssetChangeProposal(
            request_id=payload.request_id,
            risk_level=payload.risk_level,
            summary=payload.summary,
            affected_assets_json=payload.affected_assets_json,
            proposed_changes_json=payload.proposed_changes_json,
            risk_notes_json=payload.risk_notes_json,
            smoke_test_json=payload.smoke_test_json,
            status="proposed",
            created_by=payload.created_by,
        )
        self.db.add(proposal)
        await self.db.flush()
        return proposal

    async def apply_change_proposal(self, proposal_id: int, *, applied_by: str = "maga-asset-steward") -> tuple[AssetChangeProposal | None, list[int]]:
        result = await self.db.execute(select(AssetChangeProposal).where(AssetChangeProposal.id == proposal_id))
        proposal = result.scalar_one_or_none()
        if proposal is None:
            return None, []
        if proposal.status == "applied":
            return proposal, list(proposal.applied_asset_ids_json or [])

        created_ids: list[int] = []
        for item in _proposed_assets(proposal.proposed_changes_json):
            asset = AssetRegistry(
                asset_type=item["asset_type"],
                asset_key=item["asset_key"],
                display_name=item.get("display_name"),
                version_no=await self._next_asset_version(item["asset_type"], item["asset_key"]),
                status="active",
                source_name=f"asset_change_proposal:{proposal.id}",
                source_uri=None,
                source_hash=None,
                content_json=item.get("content_json") or {},
                metadata_json={"proposal_id": proposal.id, "request_id": proposal.request_id},
                created_by=applied_by,
            )
            self.db.add(asset)
            await self.db.flush()
            created_ids.append(asset.id)

        proposal.status = "applied"
        proposal.applied_by = applied_by
        proposal.applied_asset_ids_json = created_ids
        request = await self.db.get(AssetChangeRequest, proposal.request_id)
        if request is not None:
            request.status = "applied"
        await self.db.flush()
        return proposal, created_ids

    async def _next_asset_version(self, asset_type: str, asset_key: str) -> int:
        result = await self.db.execute(
            select(AssetRegistry.version_no)
            .where(AssetRegistry.asset_type == asset_type, AssetRegistry.asset_key == asset_key)
            .order_by(AssetRegistry.version_no.desc())
            .limit(1)
        )
        current = result.scalar_one_or_none()
        return int(current or 0) + 1


def _proposed_assets(changes: dict[str, Any]) -> list[dict[str, Any]]:
    assets = changes.get("assets") if isinstance(changes, dict) else None
    return [item for item in assets or [] if isinstance(item, dict) and item.get("asset_type") and item.get("asset_key")]
