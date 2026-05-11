"""MAGA Asset Registry and Asset Steward proposal endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.assets import (
    AssetChangeProposalApplyResponse,
    AssetChangeProposalCreate,
    AssetChangeProposalResponse,
    AssetChangeRequestCreate,
    AssetChangeRequestResponse,
    AssetRegistryResponse,
)
from app.services.asset_service import AssetService

router = APIRouter()


@router.get("", response_model=dict)
async def list_assets(
    asset_type: str | None = Query(default=None),
    asset_key: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    service = AssetService(db)
    assets = await service.list_assets(asset_type=asset_type, asset_key=asset_key)
    return {"data": [AssetRegistryResponse.model_validate(asset).model_dump(mode="json") for asset in assets]}


@router.get("/{asset_type}/{asset_key}", response_model=dict)
async def get_latest_asset(asset_type: str, asset_key: str, db: AsyncSession = Depends(get_db)):
    service = AssetService(db)
    asset = await service.get_latest_asset(asset_type, asset_key)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return {"data": AssetRegistryResponse.model_validate(asset).model_dump(mode="json")}


@router.post("/change-requests", response_model=dict)
async def create_change_request(payload: AssetChangeRequestCreate, db: AsyncSession = Depends(get_db)):
    service = AssetService(db)
    request = await service.create_change_request(payload)
    await db.commit()
    return {"data": AssetChangeRequestResponse.model_validate(request).model_dump(mode="json")}


@router.post("/change-proposals", response_model=dict)
async def create_change_proposal(payload: AssetChangeProposalCreate, db: AsyncSession = Depends(get_db)):
    service = AssetService(db)
    proposal = await service.create_change_proposal(payload)
    await db.commit()
    return {"data": AssetChangeProposalResponse.model_validate(proposal).model_dump(mode="json")}


@router.post("/change-proposals/{proposal_id}/apply", response_model=dict)
async def apply_change_proposal(proposal_id: int, db: AsyncSession = Depends(get_db)):
    service = AssetService(db)
    proposal, created_ids = await service.apply_change_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    await db.commit()
    return {"data": AssetChangeProposalApplyResponse(id=proposal.id, status=proposal.status, created_asset_ids=created_ids).model_dump(mode="json")}
