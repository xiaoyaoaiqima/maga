"""
Prompt optimizer workbench endpoints.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import ResponseData
from app.schemas.prompt_optimizer import (
    OptimizerMode,
    PatchStatus,
    PromptAssetCreate,
    PromptAssetResponse,
    PromptAssetUpdate,
    PromptOptimizerRunCreate,
    PromptOptimizerRunResponse,
    PromptPatchApplyRequest,
    PromptPatchApplyResponse,
    PromptPatchResponse,
    PromptPatchUpdate,
    PromptType,
    PromptVersionCreate,
    PromptVersionResponse,
    RunStatus,
)
from app.services.prompt_optimizer_service import PromptOptimizerService

router = APIRouter()


async def _run_response(service: PromptOptimizerService, run_id: int) -> PromptOptimizerRunResponse:
    run = await service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="优化任务不存在")
    patches = await service.list_patches(run.id)
    data = PromptOptimizerRunResponse.model_validate(run)
    data.patches = [PromptPatchResponse.model_validate(patch) for patch in patches]
    return data


@router.get("/prompts", response_model=ResponseData[list[PromptAssetResponse]])
async def list_prompts(
    prompt_type: Optional[PromptType] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[list[PromptAssetResponse]]:
    service = PromptOptimizerService(db)
    items = await service.list_prompts(prompt_type=prompt_type, skip=skip, limit=limit)
    return ResponseData(data=[PromptAssetResponse.model_validate(item) for item in items])


@router.post("/prompts", response_model=ResponseData[PromptAssetResponse])
async def create_prompt(
    request: PromptAssetCreate,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[PromptAssetResponse]:
    service = PromptOptimizerService(db)
    prompt, _ = await service.create_prompt(request)
    return ResponseData(message="创建成功", data=PromptAssetResponse.model_validate(prompt))


@router.get("/prompts/{prompt_id}", response_model=ResponseData[PromptAssetResponse])
async def get_prompt(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[PromptAssetResponse]:
    service = PromptOptimizerService(db)
    prompt = await service.get_prompt(prompt_id)
    if not prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提示词不存在")
    return ResponseData(data=PromptAssetResponse.model_validate(prompt))


@router.patch("/prompts/{prompt_id}", response_model=ResponseData[PromptAssetResponse])
async def update_prompt(
    prompt_id: int,
    request: PromptAssetUpdate,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[PromptAssetResponse]:
    service = PromptOptimizerService(db)
    prompt = await service.update_prompt(prompt_id, request)
    if not prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提示词不存在")
    return ResponseData(message="更新成功", data=PromptAssetResponse.model_validate(prompt))


@router.get("/prompts/{prompt_id}/versions", response_model=ResponseData[list[PromptVersionResponse]])
async def list_versions(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[list[PromptVersionResponse]]:
    service = PromptOptimizerService(db)
    prompt = await service.get_prompt(prompt_id)
    if not prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提示词不存在")
    versions = await service.list_versions(prompt_id)
    return ResponseData(data=[PromptVersionResponse.model_validate(version) for version in versions])


@router.post("/prompts/{prompt_id}/versions", response_model=ResponseData[PromptVersionResponse])
async def create_version(
    prompt_id: int,
    request: PromptVersionCreate,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[PromptVersionResponse]:
    service = PromptOptimizerService(db)
    try:
        version = await service.create_version(prompt_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ResponseData(message="版本创建成功", data=PromptVersionResponse.model_validate(version))


@router.post("/runs", response_model=ResponseData[PromptOptimizerRunResponse])
async def create_run(
    request: PromptOptimizerRunCreate,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[PromptOptimizerRunResponse]:
    service = PromptOptimizerService(db)
    try:
        run = await service.create_run(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    data = await _run_response(service, run.id)
    return ResponseData(message="优化任务完成" if data.status == "succeeded" else "优化任务失败", data=data)


@router.get("/runs", response_model=ResponseData[list[PromptOptimizerRunResponse]])
async def list_runs(
    prompt_id: Optional[int] = Query(default=None),
    mode: Optional[OptimizerMode] = Query(default=None),
    status_: Optional[RunStatus] = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[list[PromptOptimizerRunResponse]]:
    service = PromptOptimizerService(db)
    runs = await service.list_runs(prompt_id=prompt_id, mode=mode, status=status_, skip=skip, limit=limit)
    data = []
    for run in runs:
        data.append(await _run_response(service, run.id))
    return ResponseData(data=data)


@router.get("/runs/{run_id}", response_model=ResponseData[PromptOptimizerRunResponse])
async def get_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[PromptOptimizerRunResponse]:
    service = PromptOptimizerService(db)
    return ResponseData(data=await _run_response(service, run_id))


@router.get("/runs/{run_id}/patches", response_model=ResponseData[list[PromptPatchResponse]])
async def list_patches(
    run_id: int,
    status_: Optional[PatchStatus] = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[list[PromptPatchResponse]]:
    service = PromptOptimizerService(db)
    run = await service.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="优化任务不存在")
    patches = await service.list_patches(run_id)
    if status_:
        patches = [patch for patch in patches if patch.status == status_]
    return ResponseData(data=[PromptPatchResponse.model_validate(patch) for patch in patches])


@router.patch("/patches/{patch_id}", response_model=ResponseData[PromptPatchResponse])
async def update_patch(
    patch_id: int,
    request: PromptPatchUpdate,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[PromptPatchResponse]:
    service = PromptOptimizerService(db)
    patch = await service.update_patch(patch_id, request)
    if not patch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="patch 不存在")
    return ResponseData(message="更新成功", data=PromptPatchResponse.model_validate(patch))


@router.post("/runs/{run_id}/apply", response_model=ResponseData[PromptPatchApplyResponse])
async def apply_patches(
    run_id: int,
    request: PromptPatchApplyRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[PromptPatchApplyResponse]:
    service = PromptOptimizerService(db)
    try:
        result = await service.apply_patches(run_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ResponseData(message="patch 应用完成", data=result)
