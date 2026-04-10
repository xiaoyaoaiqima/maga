"""
语料模板 API
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionDep, get_db
from app.schemas.base import ResponseData
from app.schemas.corpus_template import (
    CorpusTemplateCreate,
    CorpusTemplateUpdate,
)
from app.services.corpus_template_service import CorpusTemplateService

router = APIRouter(prefix="/corpus-templates", tags=["语料模板"])


@router.get("", summary="获取模板列表")
async def get_templates(
    db: AsyncSessionDep,
    category_type: Optional[str] = Query(None, description="分类类型筛选"),
    tenant_code: Optional[str] = Query(None, description="租户编码"),
):
    """获取语料模板列表"""
    service = CorpusTemplateService(db)
    items = await service.get_list(category_type=category_type, tenant_code=tenant_code)
    return ResponseData(data={"items": [item.model_dump() for item in items], "total": len(items)})


@router.get("/category-types", summary="获取所有分类类型")
async def get_category_types(
    db: AsyncSessionDep,
    tenant_code: Optional[str] = Query(None, description="租户编码"),
):
    """获取所有分类类型（用于下拉选项）"""
    service = CorpusTemplateService(db)
    category_types = await service.get_distinct_category_types(tenant_code=tenant_code)
    return ResponseData(data=category_types)


@router.get("/by-category/{category_type:path}", summary="根据分类类型获取模板")
async def get_template_by_category(
    db: AsyncSessionDep,
    category_type: str = Path(..., description="分类类型（支持包含斜杠的路径，如 'emoji/符号'）"),
    tenant_code: str = Query("default", description="租户编码"),
):
    """根据分类类型获取模板（优先返回租户专属模板，支持 category_type 包含斜杠）"""
    # FastAPI 的 {category_type:path} 会自动解码 URL 编码，category_type 已经是解码后的值
    service = CorpusTemplateService(db)
    template = await service.get_by_category_type(category_type, tenant_code)
    if not template:
        raise HTTPException(
            status_code=404, detail=f"未找到分类类型 {category_type} 的模板"
        )
    return ResponseData(data=template.model_dump())


@router.get("/{code:path}", summary="获取单个模板")
async def get_template(
    code: str,
    db: AsyncSessionDep,
):
    """根据编码获取模板（支持 code 包含斜杠）"""
    service = CorpusTemplateService(db)
    template = await service.get_by_code(code)
    if not template:
        raise HTTPException(status_code=404, detail=f"模板 {code} 不存在")
    return ResponseData(data=template.model_dump())


@router.post("", summary="创建模板")
async def create_template(
    data: CorpusTemplateCreate,
    db: AsyncSessionDep,
):
    """创建语料模板（code 可选，未传则自动生成 template-xxx 格式）"""
    service = CorpusTemplateService(db)

    # 如果提供了 code，检查是否已存在
    if data.code and data.code.strip():
        existing = await service.get_by_code(data.code)
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"模板编码 '{data.code}' 已存在，请修改后重试"
            )

    template = await service.create(data)
    return ResponseData(data=template.model_dump(), message="模板创建成功")


@router.put("/{code:path}", summary="更新模板")
async def update_template(
    code: str,
    data: CorpusTemplateUpdate,
    db: AsyncSessionDep,
):
    """更新语料模板（支持 code 包含斜杠）"""
    service = CorpusTemplateService(db)
    template = await service.update(code, data)
    if not template:
        raise HTTPException(status_code=404, detail=f"模板 {code} 不存在")
    return ResponseData(data=template.model_dump(), message="模板更新成功")


@router.delete("/{code:path}", summary="删除模板")
async def delete_template(
    code: str,
    db: AsyncSessionDep,
):
    """删除语料模板（支持 code 包含斜杠）"""
    service = CorpusTemplateService(db)
    try:
        success = await service.delete(code)
        if not success:
            raise HTTPException(status_code=404, detail=f"模板 {code} 不存在")
        return ResponseData(message="模板删除成功", data=None)
    except ValueError as e:
        # 模板被使用，无法删除
        raise HTTPException(status_code=400, detail=str(e))
