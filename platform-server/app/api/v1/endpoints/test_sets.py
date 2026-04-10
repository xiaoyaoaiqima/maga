"""
TestSet endpoints - 测试集 CRUD
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import ResponseData
from app.schemas.expert_eval import (
    TestSetCreate,
    TestSetDetail,
    TestSetItem,
    TestSetListResponse,
    TestSetUpdate,
)
from app.services.test_set_service import TestSetService


router = APIRouter()


@router.get("", response_model=ResponseData[TestSetListResponse])
async def list_test_sets(
    keyword: Optional[str] = Query(None, description="关键词（name/code 模糊）"),
    type: Optional[str] = Query(None, description="类型: text/image"),
    enabled: Optional[bool] = Query(None, description="是否启用"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[TestSetListResponse]:
    """获取测试集列表"""
    service = TestSetService(db)
    total, items = await service.list_test_sets(
        keyword=keyword,
        type_filter=type,
        enabled=enabled,
        page=page,
        page_size=page_size,
    )

    return ResponseData(
        data=TestSetListResponse(
            items=[TestSetItem(**x) for x in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/options", response_model=ResponseData[list[dict]])
async def list_test_set_options(
    db: AsyncSession = Depends(get_db),
) -> ResponseData[list[dict]]:
    """获取所有测试集选项（用于下拉选择）"""
    service = TestSetService(db)
    options = await service.get_all_options()
    return ResponseData(data=options)


@router.get("/code/{code}", response_model=ResponseData[TestSetDetail])
async def get_test_set_by_code(
    code: str,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[TestSetDetail]:
    """根据 code 获取测试集详情"""
    service = TestSetService(db)
    detail = await service.get_detail_by_code(code)
    if not detail:
        raise HTTPException(status_code=404, detail="测试集不存在")
    return ResponseData(data=TestSetDetail(**detail))


@router.get("/{test_set_id}", response_model=ResponseData[TestSetDetail])
async def get_test_set(
    test_set_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[TestSetDetail]:
    """获取测试集详情"""
    service = TestSetService(db)
    detail = await service.get_detail(test_set_id)
    if not detail:
        raise HTTPException(status_code=404, detail="测试集不存在")
    return ResponseData(data=TestSetDetail(**detail))


@router.post("", response_model=ResponseData[TestSetItem])
async def create_test_set(
    data: TestSetCreate,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[TestSetItem]:
    """创建测试集"""
    service = TestSetService(db)
    try:
        test_set = await service.create(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 获取详情（含 case_count）
    detail = await service.get_detail(test_set.id)
    return ResponseData(data=TestSetItem(**detail))


@router.put("/{test_set_id}", response_model=ResponseData[TestSetItem])
async def update_test_set(
    test_set_id: int,
    data: TestSetUpdate,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[TestSetItem]:
    """更新测试集"""
    service = TestSetService(db)
    test_set = await service.update(test_set_id, data)
    if not test_set:
        raise HTTPException(status_code=404, detail="测试集不存在")

    # 获取详情（含 case_count）
    detail = await service.get_detail(test_set.id)
    return ResponseData(data=TestSetItem(**detail))


@router.delete("/{test_set_id}", response_model=ResponseData[dict])
async def delete_test_set(
    test_set_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[dict]:
    """删除测试集（软删除）"""
    service = TestSetService(db)
    success = await service.delete(test_set_id)
    if not success:
        raise HTTPException(status_code=404, detail="测试集不存在")
    return ResponseData(data={"deleted": True})


@router.put("/{test_set_id}/toggle", response_model=ResponseData[TestSetItem])
async def toggle_test_set_enabled(
    test_set_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[TestSetItem]:
    """切换测试集启用状态"""
    service = TestSetService(db)
    test_set = await service.toggle_enabled(test_set_id)
    if not test_set:
        raise HTTPException(status_code=404, detail="测试集不存在")

    # 获取详情（含 case_count）
    detail = await service.get_detail(test_set.id)
    return ResponseData(data=TestSetItem(**detail))

