"""
TestCase endpoints - 测试用例 CRUD
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.base import ResponseData
from app.schemas.expert_eval import (
    TestCaseCreate,
    TestCaseImportRequest,
    TestCaseImportResponse,
    TestCaseItem,
    TestCaseListResponse,
    TestCaseUpdate,
)
from app.services.test_case_service import TestCaseService


router = APIRouter()


@router.get("", response_model=ResponseData[TestCaseListResponse])
async def list_test_cases(
    test_set_code: str = Query(..., description="测试集编码"),
    keyword: Optional[str] = Query(None, description="关键词（title/content/image_url 模糊）"),
    enabled: Optional[bool] = Query(None, description="是否启用"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> ResponseData[TestCaseListResponse]:
    """获取指定测试集下的测试用例列表"""
    service = TestCaseService(db)
    total, items = await service.list_test_cases(
        test_set_code=test_set_code,
        keyword=keyword,
        enabled=enabled,
        page=page,
        page_size=page_size,
    )

    return ResponseData(
        data=TestCaseListResponse(
            items=[TestCaseItem.model_validate(x) for x in items],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{test_case_id}", response_model=ResponseData[TestCaseItem])
async def get_test_case(
    test_case_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[TestCaseItem]:
    """获取单个测试用例详情"""
    service = TestCaseService(db)
    test_case = await service.get_by_id(test_case_id)
    if not test_case:
        raise HTTPException(status_code=404, detail="测试用例不存在")
    return ResponseData(data=TestCaseItem.model_validate(test_case))


@router.post("", response_model=ResponseData[TestCaseItem])
async def create_test_case(
    data: TestCaseCreate,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[TestCaseItem]:
    """创建测试用例"""
    service = TestCaseService(db)
    test_case = await service.create(data)
    return ResponseData(data=TestCaseItem.model_validate(test_case))


@router.put("/{test_case_id}", response_model=ResponseData[TestCaseItem])
async def update_test_case(
    test_case_id: int,
    data: TestCaseUpdate,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[TestCaseItem]:
    """更新测试用例"""
    service = TestCaseService(db)
    test_case = await service.update(test_case_id, data)
    if not test_case:
        raise HTTPException(status_code=404, detail="测试用例不存在")
    return ResponseData(data=TestCaseItem.model_validate(test_case))


@router.delete("/{test_case_id}", response_model=ResponseData[dict])
async def delete_test_case(
    test_case_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[dict]:
    """删除测试用例（软删除）"""
    service = TestCaseService(db)
    success = await service.delete(test_case_id)
    if not success:
        raise HTTPException(status_code=404, detail="测试用例不存在")
    return ResponseData(data={"deleted": True})


@router.put("/{test_case_id}/toggle", response_model=ResponseData[TestCaseItem])
async def toggle_test_case_enabled(
    test_case_id: int,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[TestCaseItem]:
    """切换测试用例启用状态"""
    service = TestCaseService(db)
    test_case = await service.toggle_enabled(test_case_id)
    if not test_case:
        raise HTTPException(status_code=404, detail="测试用例不存在")
    return ResponseData(data=TestCaseItem.model_validate(test_case))


@router.post("/import", response_model=ResponseData[TestCaseImportResponse])
async def import_test_cases(
    data: TestCaseImportRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseData[TestCaseImportResponse]:
    """批量导入测试用例"""
    service = TestCaseService(db)
    success_count, skip_count = await service.batch_import(
        test_set_code=data.test_set_code,
        items=data.items,
        enabled=data.enabled,
    )
    return ResponseData(
        data=TestCaseImportResponse(
            success_count=success_count,
            skip_count=skip_count,
            total=len(data.items),
        )
    )

