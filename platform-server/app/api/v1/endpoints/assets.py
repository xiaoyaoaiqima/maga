"""MAGA Asset Registry and Asset Steward proposal endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import ResponseData
from app.schemas.assets import (
    AssetCandidateCreate,
    AssetChangeProposalApplyResponse,
    AssetChangeProposalCreate,
    AssetChangeProposalResponse,
    AssetChangeRequestCreate,
    AssetChangeRequestResponse,
    AssetGenerationOptionsResponse,
    AssetImportResponse,
    AssetImportRunResponse,
    AssetRegistryResponse,
    AssetRegistrySummaryResponse,
    ReferenceElementExtractRequest,
    ReferenceElementExtractResponse,
    SystemPromptKeywordAssetResponse,
    SystemPromptKeywordExportResponse,
    SystemPromptKeywordPreviewRequest,
    SystemPromptKeywordPreviewResponse,
    SystemPromptKeywordRollback,
    SystemPromptKeywordUpdate,
)
from app.services.asset_service import AssetService, normalize_asset_content
from app.services.asset_import_service import import_yuanyue_training_rules
from app.services.comment_angle_rule_service import (
    COMMENT_ANGLE_RULE_ASSET_TYPE,
    DEFAULT_COMMENT_ANGLE_ASSET_KEY,
    comment_angle_import_summary,
    import_comment_angle_rule_set,
)
from app.services.product_experience_rule_service import (
    DEFAULT_PRODUCT_EXPERIENCE_ASSET_KEY,
    PRODUCT_EXPERIENCE_RULE_ASSET_TYPE,
    import_product_experience_rule_set,
    product_experience_import_summary,
)
from app.services.reference_element_extraction_service import ReferenceElementExtractionService
from app.services.system_prompt_keyword_service import (
    CONTENT_GENERATION_KEYWORDS_ASSET_TYPE,
    DEFAULT_SYSTEM_KEYWORD_ASSET_KEY,
    SystemPromptKeywordService,
    export_keywords_csv,
    fallback_system_prompt_keyword_content,
    normalize_system_prompt_keyword_content,
)
from app.services.unified_content_generation_service import UnifiedContentGenerationService

router = APIRouter()


@router.get("", response_model=ResponseData)
async def list_assets(
    asset_type: str | None = Query(default=None),
    asset_key: str | None = Query(default=None),
    asset_stage: str | None = Query(default="production"),
    db: AsyncSession = Depends(get_db),
):
    service = AssetService(db)
    assets = await service.list_assets(asset_type=asset_type, asset_key=asset_key, asset_stage=asset_stage)
    return ResponseData(
        code=200,
        message="success",
        data=[AssetRegistryResponse.model_validate(asset).model_dump(mode="json") for asset in assets],
    )


@router.get("/summary", response_model=ResponseData)
async def list_asset_summaries(
    asset_type: str | None = Query(default=None),
    asset_key: str | None = Query(default=None),
    asset_stage: str | None = Query(default="production"),
    db: AsyncSession = Depends(get_db),
):
    service = AssetService(db)
    assets = await service.list_assets(asset_type=asset_type, asset_key=asset_key, asset_stage=asset_stage)
    return ResponseData(
        code=200,
        message="success",
        data=[
            AssetRegistrySummaryResponse(
                id=asset.id,
                asset_type=asset.asset_type,
                asset_key=asset.asset_key,
                display_name=asset.display_name,
                version_no=asset.version_no,
                status=asset.status,
                asset_stage=asset.asset_stage,
                source_name=asset.source_name,
                source_hash=asset.source_hash,
                item_count=_asset_item_count(asset.content_json),
                created_by=asset.created_by,
                create_time=asset.create_time,
                update_time=asset.update_time,
            ).model_dump(mode="json")
            for asset in assets
        ],
    )


@router.get("/import-runs", response_model=ResponseData)
async def list_asset_import_runs(
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    service = AssetService(db)
    runs = await service.list_import_runs(limit=limit)
    return ResponseData(
        code=200,
        message="success",
        data=[AssetImportRunResponse.model_validate(run).model_dump(mode="json") for run in runs],
    )


@router.get("/change-requests", response_model=ResponseData)
async def list_asset_change_requests(
    limit: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    service = AssetService(db)
    requests = await service.list_change_requests(limit=limit, status=status)
    return ResponseData(
        code=200,
        message="success",
        data=[AssetChangeRequestResponse.model_validate(request).model_dump(mode="json") for request in requests],
    )


@router.post("/change-requests/{request_id}/propose-compliance-rule", response_model=ResponseData)
async def propose_compliance_rule_from_change_request(
    request_id: int,
    created_by: str = Query(default="maga-asset-steward"),
    db: AsyncSession = Depends(get_db),
):
    service = AssetService(db)
    proposal = await service.create_compliance_rule_proposal_from_request(request_id, created_by=created_by)
    if proposal is None:
        raise HTTPException(status_code=404, detail="change request not found")
    await db.commit()
    await db.refresh(proposal)
    return ResponseData(
        code=200,
        message="success",
        data=AssetChangeProposalResponse.model_validate(proposal).model_dump(mode="json"),
    )


@router.get("/change-proposals", response_model=ResponseData)
async def list_asset_change_proposals(
    limit: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    service = AssetService(db)
    proposals = await service.list_change_proposals(limit=limit, status=status)
    return ResponseData(
        code=200,
        message="success",
        data=[AssetChangeProposalResponse.model_validate(proposal).model_dump(mode="json") for proposal in proposals],
    )


@router.post("/imports/yuanyue-training-rules", response_model=ResponseData)
async def import_yuanyue_training_rules_endpoint(
    file: UploadFile = File(...),
    asset_key: str = Form(default="yuanyue"),
    created_by: str = Form(default="maga-worker"),
    executor_code: str = Form(default="hermes_maga_worker"),
    db: AsyncSession = Depends(get_db),
):
    filename = file.filename or "源悦种草活动-ai训练规则.xlsx"
    if not filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="only .xlsx files are supported")

    workbook_content = await file.read()
    try:
        result = await import_yuanyue_training_rules(
            db,
            workbook_content,
            source_name=filename,
            asset_key=asset_key,
            created_by=created_by,
            executor_code=executor_code,
        )
        await db.commit()
        return ResponseData(
            code=200,
            message="success",
            data=AssetImportResponse(
                import_run_id=result.import_run_id,
                imported_assets=result.imported_assets,
                asset_keys=result.asset_keys,
                source_hash=result.source_hash,
            ).model_dump(mode="json"),
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/imports/comment-angle-rule-set", response_model=ResponseData)
async def import_comment_angle_rule_set_endpoint(
    file: UploadFile = File(...),
    asset_key: str = Form(default=DEFAULT_COMMENT_ANGLE_ASSET_KEY),
    display_name: str | None = Form(default=None),
    created_by: str = Form(default="maga-operator"),
    db: AsyncSession = Depends(get_db),
):
    filename = file.filename or "评论切角_子关键词导出.csv"
    if not filename.lower().endswith((".csv", ".xlsx")):
        raise HTTPException(status_code=400, detail="only .csv and .xlsx files are supported")

    file_content = await file.read()
    try:
        result = await import_comment_angle_rule_set(
            db,
            file_content,
            source_name=filename,
            asset_key=asset_key,
            display_name=display_name,
            created_by=created_by,
        )
        await db.commit()
        return ResponseData(
            code=200,
            message="success",
            data=AssetImportResponse(
                import_run_id=result.import_run_id,
                imported_assets=1,
                asset_keys=[(COMMENT_ANGLE_RULE_ASSET_TYPE, result.asset_key)],
                source_hash=result.source_hash,
                summary_json=comment_angle_import_summary(result),
            ).model_dump(mode="json"),
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/imports/product-experience-rule-set", response_model=ResponseData)
async def import_product_experience_rule_set_endpoint(
    file: UploadFile = File(...),
    asset_key: str = Form(default=DEFAULT_PRODUCT_EXPERIENCE_ASSET_KEY),
    display_name: str | None = Form(default=None),
    created_by: str = Form(default="maga-operator"),
    db: AsyncSession = Depends(get_db),
):
    filename = file.filename or "产品使用体验_子关键词导出.csv"
    if not filename.lower().endswith((".csv", ".xlsx")):
        raise HTTPException(status_code=400, detail="only .csv and .xlsx files are supported")

    file_content = await file.read()
    try:
        result = await import_product_experience_rule_set(
            db,
            file_content,
            source_name=filename,
            asset_key=asset_key,
            display_name=display_name,
            created_by=created_by,
        )
        await db.commit()
        return ResponseData(
            code=200,
            message="success",
            data=AssetImportResponse(
                import_run_id=result.import_run_id,
                imported_assets=1,
                asset_keys=[(PRODUCT_EXPERIENCE_RULE_ASSET_TYPE, result.asset_key)],
                source_hash=result.source_hash,
                summary_json=product_experience_import_summary(result),
            ).model_dump(mode="json"),
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/imports/content-generation-keywords", response_model=ResponseData)
async def import_content_generation_keywords_endpoint(
    file: UploadFile = File(...),
    asset_key: str = Form(default=DEFAULT_SYSTEM_KEYWORD_ASSET_KEY),
    display_name: str | None = Form(default=None),
    created_by: str = Form(default="maga-operator"),
    db: AsyncSession = Depends(get_db),
):
    filename = file.filename or "系统提示词关键词.csv"
    if not filename.lower().endswith((".csv", ".xlsx")):
        raise HTTPException(status_code=400, detail="only .csv and .xlsx files are supported")

    file_content = await file.read()
    service = SystemPromptKeywordService(db)
    try:
        asset, run = await service.import_keywords(
            file_content,
            source_name=filename,
            asset_key=asset_key,
            display_name=display_name,
            created_by=created_by,
        )
        await db.commit()
        await db.refresh(asset)
        return ResponseData(
            code=200,
            message="success",
            data=AssetImportResponse(
                import_run_id=run.id,
                imported_assets=1,
                asset_keys=[(CONTENT_GENERATION_KEYWORDS_ASSET_TYPE, asset.asset_key)],
                source_hash=asset.source_hash or "",
                summary_json=run.summary_json,
            ).model_dump(mode="json"),
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reference-elements/extract", response_model=ResponseData)
async def extract_reference_elements(payload: ReferenceElementExtractRequest, db: AsyncSession = Depends(get_db)):
    service = ReferenceElementExtractionService(db)
    try:
        result = await service.extract_from_latest_asset(
            asset_key=payload.asset_key,
            limit=payload.limit,
            persist=payload.persist,
            created_by=payload.created_by or "reference-element-extractor",
        )
        if payload.persist:
            await db.commit()
            if result.asset is not None:
                await db.refresh(result.asset)
        return ResponseData(
            code=200,
            message="success",
            data=ReferenceElementExtractResponse(
                source_asset_id=result.source_asset_id,
                source_asset_version=result.source_asset_version,
                source_item_count=result.source_item_count,
                extracted_count=len(result.items),
                persisted_asset_id=result.asset.id if result.asset else None,
                persisted_asset_version=result.asset.version_no if result.asset else None,
                items=result.items,
            ).model_dump(mode="json"),
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/generation-options", response_model=ResponseData)
async def get_generation_options(
    asset_key: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    service = AssetService(db)
    options = await service.generation_options(asset_key=asset_key)
    return ResponseData(
        code=200,
        message="success",
        data=AssetGenerationOptionsResponse.model_validate(options).model_dump(mode="json"),
    )


@router.get("/content-generation-keywords", response_model=ResponseData)
async def get_content_generation_keywords(
    asset_key: str = Query(default=DEFAULT_SYSTEM_KEYWORD_ASSET_KEY),
    db: AsyncSession = Depends(get_db),
):
    service = SystemPromptKeywordService(db)
    asset = await service.get_latest_asset(asset_key=asset_key)
    if asset is None:
        content_json = fallback_system_prompt_keyword_content()
        return ResponseData(
            code=200,
            message="success",
            data=SystemPromptKeywordAssetResponse(
                asset_type=CONTENT_GENERATION_KEYWORDS_ASSET_TYPE,
                asset_key=asset_key,
                display_name="系统提示词关键词",
                source="fallback",
                content_json=content_json,
                metadata_json={
                    "schema_version": content_json.get("schema_version"),
                    "category_count": len(content_json.get("categories") or []),
                },
            ).model_dump(mode="json"),
        )

    content_json = normalize_system_prompt_keyword_content(asset.content_json or {})
    return ResponseData(
        code=200,
        message="success",
        data=SystemPromptKeywordAssetResponse(
            id=asset.id,
            asset_type=asset.asset_type,
            asset_key=asset.asset_key,
            display_name=asset.display_name,
            version_no=asset.version_no,
            status=asset.status,
            asset_stage=asset.asset_stage,
            source="asset_registry",
            source_hash=asset.source_hash,
            content_json=content_json,
            metadata_json=asset.metadata_json,
            created_by=asset.created_by,
            create_time=asset.create_time,
            update_time=asset.update_time,
        ).model_dump(mode="json"),
    )


@router.get("/content-generation-keywords/versions", response_model=ResponseData)
async def list_content_generation_keyword_versions(
    asset_key: str = Query(default=DEFAULT_SYSTEM_KEYWORD_ASSET_KEY),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    service = SystemPromptKeywordService(db)
    assets = await service.list_versions(asset_key=asset_key, limit=limit)
    return ResponseData(
        code=200,
        message="success",
        data=[AssetRegistrySummaryResponse(
            id=asset.id,
            asset_type=asset.asset_type,
            asset_key=asset.asset_key,
            display_name=asset.display_name,
            version_no=asset.version_no,
            status=asset.status,
            asset_stage=asset.asset_stage,
            source_name=asset.source_name,
            source_hash=asset.source_hash,
            item_count=None,
            created_by=asset.created_by,
            create_time=asset.create_time,
            update_time=asset.update_time,
        ).model_dump(mode="json") for asset in assets],
    )


@router.put("/content-generation-keywords", response_model=ResponseData)
async def save_content_generation_keywords(
    payload: SystemPromptKeywordUpdate,
    db: AsyncSession = Depends(get_db),
):
    service = SystemPromptKeywordService(db)
    try:
        asset = await service.save_keywords(
            asset_key=payload.asset_key,
            display_name=payload.display_name,
            content_json={
                "selection_policy": payload.selection_policy or {},
                "categories": payload.categories,
            },
            created_by=payload.created_by or "maga-operator",
        )
        await db.commit()
        await db.refresh(asset)
        return ResponseData(
            code=200,
            message="success",
            data=AssetRegistryResponse.model_validate(asset).model_dump(mode="json"),
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/content-generation-keywords/rollback", response_model=ResponseData)
async def rollback_content_generation_keywords(
    payload: SystemPromptKeywordRollback,
    db: AsyncSession = Depends(get_db),
):
    service = SystemPromptKeywordService(db)
    try:
        asset = await service.rollback_to_version(
            asset_key=payload.asset_key,
            version_no=payload.version_no,
            created_by=payload.created_by or "maga-operator",
        )
        await db.commit()
        await db.refresh(asset)
        return ResponseData(
            code=200,
            message="success",
            data=AssetRegistryResponse.model_validate(asset).model_dump(mode="json"),
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/exports/content-generation-keywords", response_model=ResponseData)
async def export_content_generation_keywords(
    asset_key: str = Query(default=DEFAULT_SYSTEM_KEYWORD_ASSET_KEY),
    db: AsyncSession = Depends(get_db),
):
    service = SystemPromptKeywordService(db)
    asset = await service.get_latest_asset(asset_key=asset_key)
    content_json = asset.content_json if asset else fallback_system_prompt_keyword_content()
    filename = f"{asset_key}_系统提示词关键词.csv"
    return ResponseData(
        code=200,
        message="success",
        data=SystemPromptKeywordExportResponse(
            asset_key=asset_key,
            version_no=asset.version_no if asset else None,
            filename=filename,
            csv_text=export_keywords_csv(content_json),
        ).model_dump(mode="json"),
    )


@router.post("/content-generation-keywords/preview", response_model=ResponseData)
async def preview_content_generation_keywords(
    payload: SystemPromptKeywordPreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    business_rule = payload.business_rule or {
        "rule_type": "comment_angle" if payload.content_type == "comment" else "product_experience",
        "comment_angle": "示例评论切角" if payload.content_type == "comment" else None,
        "product_experience": "示例产品使用体验" if payload.content_type != "comment" else None,
        "corpus": "这里是本次业务规则里的语料，用于预览系统关键词会如何进入最终 prompt。",
        "examples": ["这是一条用于预览的参考示例。"],
    }
    keyword_override = (
        {
            "selection_policy": payload.selection_policy or {},
            "categories": payload.categories,
        }
        if payload.categories is not None
        else None
    )
    try:
        snapshot = await UnifiedContentGenerationService(db).build_snapshot(
            content_type=payload.content_type,
            business_rule={key: value for key, value in business_rule.items() if value is not None},
            item_no=payload.item_no,
            output_fields=payload.output_fields or (["comment"] if payload.content_type == "comment" else ["title", "body"]),
            expert_config_code=payload.expert_config_code,
            keyword_asset_key=payload.asset_key,
            keyword_content_override=keyword_override,
            model_config=payload.llm_params,
        )
        return ResponseData(
            code=200,
            message="success",
            data=SystemPromptKeywordPreviewResponse(
                asset_key=payload.asset_key,
                content_type=payload.content_type,
                selected_keywords=snapshot.input_snapshot["selected_keywords"],
                rendered_prompt=snapshot.input_snapshot["rendered_prompt"],
                expert=snapshot.input_snapshot["expert"],
            ).model_dump(mode="json"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/candidates", response_model=ResponseData)
async def create_candidate_asset(payload: AssetCandidateCreate, db: AsyncSession = Depends(get_db)):
    service = AssetService(db)
    asset = await service.create_candidate_asset(payload)
    await db.commit()
    await db.refresh(asset)
    return ResponseData(
        code=200,
        message="success",
        data=AssetRegistryResponse.model_validate(asset).model_dump(mode="json"),
    )


@router.get("/{asset_type}/{asset_key}", response_model=ResponseData)
async def get_latest_asset(
    asset_type: str,
    asset_key: str,
    asset_stage: str | None = Query(default="production"),
    db: AsyncSession = Depends(get_db),
):
    service = AssetService(db)
    asset = await service.get_latest_asset(asset_type, asset_key, asset_stage=asset_stage)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    response_data = AssetRegistryResponse.model_validate(asset).model_dump(mode="json")
    response_data["content_json"] = normalize_asset_content(asset.asset_type, asset.content_json)
    return ResponseData(
        code=200,
        message="success",
        data=response_data,
    )


@router.post("/change-requests", response_model=ResponseData)
async def create_change_request(payload: AssetChangeRequestCreate, db: AsyncSession = Depends(get_db)):
    service = AssetService(db)
    request = await service.create_change_request(payload)
    await db.commit()
    return ResponseData(
        code=200,
        message="success",
        data=AssetChangeRequestResponse.model_validate(request).model_dump(mode="json"),
    )


@router.post("/change-proposals", response_model=ResponseData)
async def create_change_proposal(payload: AssetChangeProposalCreate, db: AsyncSession = Depends(get_db)):
    service = AssetService(db)
    proposal = await service.create_change_proposal(payload)
    await db.commit()
    return ResponseData(
        code=200,
        message="success",
        data=AssetChangeProposalResponse.model_validate(proposal).model_dump(mode="json"),
    )


@router.post("/change-proposals/{proposal_id}/apply", response_model=ResponseData)
async def apply_change_proposal(proposal_id: int, db: AsyncSession = Depends(get_db)):
    service = AssetService(db)
    proposal, created_ids = await service.apply_change_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    await db.commit()
    return ResponseData(
        code=200,
        message="success",
        data=AssetChangeProposalApplyResponse(
            id=proposal.id,
            status=proposal.status,
            created_asset_ids=created_ids,
        ).model_dump(mode="json"),
    )


def _asset_item_count(content: dict | None) -> int | None:
    items = (content or {}).get("items")
    return len(items) if isinstance(items, list) else None
