"""
菜单管理 API
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.sys_menu_service import SysMenuService
from app.schemas.sys_menu import (
    MenuCreate,
    MenuUpdate,
    MenuResponse,
    MenuFilters,
    MenuTreeItem,
    MenuTreeSimple,
    MenuImportRequest,
    MenuImportResult,
)
from app.schemas.base import ResponseModel

router = APIRouter(prefix="/menus", tags=["菜单管理"])


def get_menu_service(db: AsyncSession = Depends(get_db)) -> SysMenuService:
    """获取菜单服务实例"""
    return SysMenuService(db)


@router.post("", response_model=ResponseModel, summary="创建菜单")
async def create_menu(
    data: MenuCreate,
    service: SysMenuService = Depends(get_menu_service)
):
    """
    创建菜单
    
    - **menu_name**: 菜单名称
    - **menu_type**: 类型（M目录 C菜单 F按钮）
    - **parent_id**: 父菜单ID（0表示根菜单）
    - **path**: 路由路径
    - **component**: 组件路径
    - **icon**: 图标
    - **perm_code**: 权限标识
    - **sort_order**: 排序
    """
    try:
        menu = await service.create_menu(data)
        return ResponseModel(code=200, message="创建成功", data=menu.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{menu_id}", response_model=ResponseModel, summary="更新菜单")
async def update_menu(
    menu_id: str,
    data: MenuUpdate,
    service: SysMenuService = Depends(get_menu_service)
):
    """更新菜单信息"""
    try:
        menu = await service.update_menu(menu_id, data)
        if not menu:
            raise HTTPException(status_code=404, detail="菜单不存在")
        return ResponseModel(code=200, message="更新成功", data=menu.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{menu_id}", response_model=ResponseModel, summary="删除菜单")
async def delete_menu(
    menu_id: str,
    service: SysMenuService = Depends(get_menu_service)
):
    """
    删除菜单（软删除）
    
    注意：有子菜单的菜单不能直接删除
    """
    try:
        success = await service.delete_menu(menu_id)
        if not success:
            raise HTTPException(status_code=404, detail="菜单不存在")
        return ResponseModel(code=200, message="删除成功")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{menu_id}", response_model=ResponseModel, summary="获取菜单详情")
async def get_menu(
    menu_id: str,
    service: SysMenuService = Depends(get_menu_service)
):
    """获取菜单详情"""
    menu = await service.get_menu(menu_id)
    if not menu:
        raise HTTPException(status_code=404, detail="菜单不存在")
    return ResponseModel(code=200, message="success", data=menu.model_dump())


@router.get("", response_model=ResponseModel, summary="获取菜单列表")
async def get_menus(
    menu_name: Optional[str] = Query(None, description="菜单名称"),
    menu_type: Optional[str] = Query(None, description="类型"),
    status: Optional[int] = Query(None, description="状态"),
    service: SysMenuService = Depends(get_menu_service)
):
    """获取菜单列表（扁平）"""
    filters = MenuFilters(
        menu_name=menu_name,
        menu_type=menu_type,
        status=status
    )
    menus = await service.get_menu_list(filters)
    return ResponseModel(
        code=200,
        message="success",
        data=[menu.model_dump() for menu in menus]
    )


@router.get("/tree/full", response_model=ResponseModel, summary="获取菜单树")
async def get_menu_tree(
    service: SysMenuService = Depends(get_menu_service)
):
    """获取完整菜单树"""
    tree = await service.get_menu_tree()
    return ResponseModel(
        code=200,
        message="success",
        data=[item.model_dump() for item in tree]
    )


@router.get("/tree/simple", response_model=ResponseModel, summary="获取简化菜单树（权限配置用）")
async def get_menu_tree_simple(
    service: SysMenuService = Depends(get_menu_service)
):
    """获取简化菜单树，用于角色权限配置"""
    tree = await service.get_menu_tree_simple()
    return ResponseModel(
        code=200,
        message="success",
        data=[item.model_dump() for item in tree]
    )


@router.post("/init", response_model=ResponseModel, summary="初始化默认菜单")
async def init_default_menus(
    service: SysMenuService = Depends(get_menu_service)
):
    """初始化默认菜单（如果数据库为空）"""
    count = await service.init_default_menus()
    if count > 0:
        return ResponseModel(code=200, message=f"初始化成功，创建 {count} 条菜单")
    else:
        return ResponseModel(code=200, message="菜单已存在，无需初始化")


@router.post("/import", response_model=ResponseModel, summary="批量导入菜单")
async def import_menus(
    data: MenuImportRequest,
    service: SysMenuService = Depends(get_menu_service)
):
    """
    批量导入菜单
    
    - **menus**: 菜单列表（从导出的 JSON 中获取）
    - **mode**: 导入模式
      - `append`: 追加模式，跳过已存在的菜单（按 path 判断）
      - `replace`: 覆盖模式，删除所有现有菜单后导入（危险操作！）
    - **role_codes**: 分配给哪些角色（默认 ["admin"]）
    """
    try:
        result = await service.import_menus(
            menus=data.menus,
            mode=data.mode,
            role_codes=data.role_codes,
        )
        return ResponseModel(
            code=200,
            message=f"导入成功：创建 {result.created} 条，跳过 {result.skipped} 条",
            data=result.model_dump()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

