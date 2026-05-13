"""Schemas for MAGA marketing asset registry and Asset Steward proposals."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AssetRegistryResponse(BaseModel):
    id: int
    asset_type: str
    asset_key: str
    display_name: str | None = None
    version_no: int
    status: str
    asset_stage: str = "production"
    source_name: str | None = None
    source_uri: str | None = None
    source_hash: str | None = None
    content_json: dict[str, Any]
    metadata_json: dict[str, Any] | None = None
    created_by: str | None = None
    create_time: datetime | None = None
    update_time: datetime | None = None

    class Config:
        from_attributes = True


class AssetRegistrySummaryResponse(BaseModel):
    id: int
    asset_type: str
    asset_key: str
    display_name: str | None = None
    version_no: int
    status: str
    asset_stage: str = "production"
    source_name: str | None = None
    source_hash: str | None = None
    item_count: int | None = None
    created_by: str | None = None
    create_time: datetime | None = None
    update_time: datetime | None = None


class AssetImportRunResponse(BaseModel):
    id: int
    source_name: str
    source_uri: str | None = None
    source_hash: str | None = None
    status: str
    imported_assets: int
    summary_json: dict[str, Any] | None = None
    created_by: str | None = None
    create_time: datetime | None = None

    class Config:
        from_attributes = True


class AssetImportResponse(BaseModel):
    import_run_id: int | None
    imported_assets: int
    asset_keys: list[tuple[str, str]]
    source_hash: str


class AssetGenerationOptionsResponse(BaseModel):
    asset_key: str | None = None
    asset_keys: list[str]
    product_topics: list[str]
    target_audiences: list[str]
    persona_profiles: list[str] = Field(default_factory=list)
    styles: list[str]


class AssetCandidateCreate(BaseModel):
    asset_type: str = Field(..., min_length=1)
    asset_key: str = Field(..., min_length=1)
    display_name: str | None = None
    source_name: str | None = None
    source_uri: str | None = None
    source_hash: str | None = None
    content_json: dict[str, Any]
    metadata_json: dict[str, Any] | None = None
    created_by: str | None = "maga-worker"


class AssetChangeRequestCreate(BaseModel):
    source_text: str = Field(..., min_length=1)
    requester: str | None = None
    context_json: dict[str, Any] | None = None
    created_by: str | None = "maga-asset-steward"


class AssetChangeRequestResponse(BaseModel):
    id: int
    source_text: str
    requester: str | None = None
    context_json: dict[str, Any] | None = None
    status: str
    created_by: str | None = None
    create_time: datetime | None = None
    update_time: datetime | None = None

    class Config:
        from_attributes = True


class AssetChangeProposalCreate(BaseModel):
    request_id: int
    risk_level: str = "medium"
    summary: str | None = None
    affected_assets_json: list[dict[str, Any]] | None = None
    proposed_changes_json: dict[str, Any]
    risk_notes_json: list[str] | None = None
    smoke_test_json: dict[str, Any] | None = None
    created_by: str | None = "maga-asset-steward"


class AssetChangeProposalResponse(BaseModel):
    id: int
    request_id: int
    risk_level: str
    summary: str | None = None
    affected_assets_json: list[dict[str, Any]] | None = None
    proposed_changes_json: dict[str, Any]
    risk_notes_json: list[str] | None = None
    smoke_test_json: dict[str, Any] | None = None
    status: str
    applied_asset_ids_json: list[int] | None = None
    created_by: str | None = None
    applied_by: str | None = None
    create_time: datetime | None = None
    update_time: datetime | None = None

    class Config:
        from_attributes = True


class AssetChangeProposalApplyResponse(BaseModel):
    id: int
    status: str
    created_asset_ids: list[int]
