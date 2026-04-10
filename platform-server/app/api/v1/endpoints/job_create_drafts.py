"""
JobCreateDraft endpoints（草稿）

路径前缀由 api_router 注册为：/api/v1/job-create/drafts
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import ResponseData
from app.schemas.job import JobResponse
from app.schemas.job_create_draft import (
    JobCreateDraftCompileResponse,
    JobCreateDraftCreate,
    JobCreateDraftPatch,
    JobCreateDraftResponse,
    JobCreateDraftValidateResponse,
)
from app.services.job_create_draft_service import JobCreateDraftService

router = APIRouter()


def get_service(db: AsyncSession = Depends(get_db)) -> JobCreateDraftService:
    return JobCreateDraftService(db)


@router.post("", response_model=ResponseData[JobCreateDraftResponse])
async def create_draft(
    data: JobCreateDraftCreate,
    service: JobCreateDraftService = Depends(get_service),
) -> ResponseData[JobCreateDraftResponse]:
    try:
        draft = await service.create(data)
        return ResponseData(code=200, message="创建成功", data=JobCreateDraftResponse.model_validate(draft))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{draft_id}", response_model=ResponseData[JobCreateDraftResponse])
async def get_draft(
    draft_id: str,
    service: JobCreateDraftService = Depends(get_service),
) -> ResponseData[JobCreateDraftResponse]:
    draft = await service.get(draft_id)
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    return ResponseData(data=JobCreateDraftResponse.model_validate(draft))


@router.patch("/{draft_id}", response_model=ResponseData[JobCreateDraftResponse])
async def patch_draft(
    draft_id: str,
    data: JobCreateDraftPatch,
    service: JobCreateDraftService = Depends(get_service),
) -> ResponseData[JobCreateDraftResponse]:
    try:
        draft = await service.patch(draft_id, data)
        return ResponseData(code=200, message="更新成功", data=JobCreateDraftResponse.model_validate(draft))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{draft_id}/validate", response_model=ResponseData[JobCreateDraftValidateResponse])
async def validate_draft(
    draft_id: str,
    service: JobCreateDraftService = Depends(get_service),
) -> ResponseData[JobCreateDraftValidateResponse]:
    try:
        validation = await service.validate(draft_id)
        return ResponseData(
            code=200,
            message="校验完成",
            data=JobCreateDraftValidateResponse(draft_id=draft_id, validation=validation),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{draft_id}/compile", response_model=ResponseData[JobCreateDraftCompileResponse])
async def compile_draft(
    draft_id: str,
    service: JobCreateDraftService = Depends(get_service),
) -> ResponseData[JobCreateDraftCompileResponse]:
    try:
        compiled = await service.compile(draft_id)
        return ResponseData(
            code=200,
            message="编译完成",
            data=JobCreateDraftCompileResponse(draft_id=draft_id, compiled_json=compiled),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{draft_id}/create-job", response_model=ResponseData[JobResponse])
async def create_job_from_draft(
    draft_id: str,
    service: JobCreateDraftService = Depends(get_service),
) -> ResponseData[JobResponse]:
    try:
        job = await service.create_job(draft_id)
        return ResponseData(code=200, message="创建成功", data=JobResponse.model_validate(job))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))



