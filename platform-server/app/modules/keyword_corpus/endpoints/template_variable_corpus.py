"""Operator-facing template variable corpus endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import PageInfo, ResponseData
from app.schemas.template_variable_corpus import (
    PromptPreviewRequest,
    PromptPreviewResponse,
    TemplateVariableCorpusCreate,
    TemplateVariableCorpusItem,
    TemplateVariableCorpusListResponse,
    TemplateVariableCorpusUpdate,
    TemplateVariableListResponse,
)
from app.services.template_variable_corpus_service import TemplateVariableCorpusService

router = APIRouter(prefix="/template-variable-corpus", tags=["template-variable-corpus"])


@router.get("/variables", response_model=ResponseData[TemplateVariableListResponse])
async def list_template_variables(
    tenant_code: str = Query(default="default"),
    db: AsyncSession = Depends(get_db),
):
    service = TemplateVariableCorpusService(db)
    variables = await service.list_variables(tenant_code=tenant_code)
    return ResponseData(
        code=200,
        message="success",
        data=TemplateVariableListResponse(
            template_path=str(service.template_path),
            variables=variables,
        ),
    )


@router.get("", response_model=ResponseData[TemplateVariableCorpusListResponse])
async def list_template_variable_corpus(
    variable_name: str | None = Query(default=None),
    tenant_code: str = Query(default="default"),
    status: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    service = TemplateVariableCorpusService(db)
    items, total = await service.list_corpus(
        variable_name=variable_name,
        tenant_code=tenant_code,
        status=status,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    total_pages = int((total + page_size - 1) // page_size) if page_size else 1
    return ResponseData(
        code=200,
        message="success",
        data=TemplateVariableCorpusListResponse(
            items=items,
            page_info=PageInfo(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
            ),
        ),
    )


@router.post("", response_model=ResponseData[TemplateVariableCorpusItem])
async def create_template_variable_corpus(
    payload: TemplateVariableCorpusCreate,
    db: AsyncSession = Depends(get_db),
):
    service = TemplateVariableCorpusService(db)
    item = await service.create_corpus(payload)
    return ResponseData(code=200, message="success", data=item)


@router.put("/{item_id}", response_model=ResponseData[TemplateVariableCorpusItem])
async def update_template_variable_corpus(
    item_id: int,
    payload: TemplateVariableCorpusUpdate,
    db: AsyncSession = Depends(get_db),
):
    service = TemplateVariableCorpusService(db)
    item = await service.update_corpus(item_id, payload)
    if item is None:
        raise HTTPException(status_code=404, detail="template variable corpus item not found")
    return ResponseData(code=200, message="success", data=item)


@router.delete("/{item_id}", response_model=ResponseData[dict[str, bool]])
async def archive_template_variable_corpus(
    item_id: int,
    db: AsyncSession = Depends(get_db),
):
    service = TemplateVariableCorpusService(db)
    archived = await service.archive_corpus(item_id)
    if not archived:
        raise HTTPException(status_code=404, detail="template variable corpus item not found")
    return ResponseData(code=200, message="success", data={"archived": True})


@router.post("/preview", response_model=ResponseData[PromptPreviewResponse])
async def preview_template_prompt(
    payload: PromptPreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    service = TemplateVariableCorpusService(db)
    preview = await service.preview_prompt(payload)
    return ResponseData(code=200, message="success", data=preview)
