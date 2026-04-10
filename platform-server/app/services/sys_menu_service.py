"""
System Menu service
"""
import uuid
from typing import Optional, List, Dict

from sqlalchemy import select, and_, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sys_menu import SysMenu
from app.models.sys_role import SysRole
from app.models.sys_role_menu import SysRoleMenu
from app.schemas.sys_menu import (
    MenuCreate,
    MenuUpdate,
    MenuResponse,
    MenuFilters,
    MenuTreeItem,
    MenuTreeSimple,
    MenuImportItem,
    MenuImportResult,
)
from app.core.logger import logger


class SysMenuService:
    """菜单服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _validate_menu_payload(
        self,
        *,
        menu_id: Optional[str],
        menu_type: str,
        parent_id: str,
        path: Optional[str],
        component: Optional[str],
    ) -> None:
        """
        菜单数据强校验（防止脏数据进入 DB）

        规则：
        - M/C 必须有 path
        - C 必须有 component
        - parent_id 不能指向自身，且必须存在（除 0）
        - path 在未删除菜单中必须唯一（避免路由冲突）
        """
        if menu_type in {"M", "C"} and not path:
            raise ValueError("菜单类型为 M/C 时必须配置 path")

        if menu_type == "C" and not component:
            raise ValueError("菜单类型为 C 时必须配置 component")

        if parent_id and parent_id != "0":
            if menu_id and parent_id == menu_id:
                raise ValueError("父菜单不能设置为自身")

            stmt = select(func.count()).select_from(SysMenu).where(
                and_(SysMenu.id == parent_id, SysMenu.is_deleted == 0)
            )
            parent_count = (await self.db.execute(stmt)).scalar()
            if not parent_count:
                raise ValueError("父菜单不存在")

        if path:
            stmt = select(func.count()).select_from(SysMenu).where(
                and_(SysMenu.path == path, SysMenu.is_deleted == 0)
            )
            if menu_id:
                stmt = stmt.where(SysMenu.id != menu_id)
            dup_count = (await self.db.execute(stmt)).scalar()
            if dup_count:
                raise ValueError(f"路由路径已存在：{path}")
    
    async def create_menu(self, data: MenuCreate) -> MenuResponse:
        """
        创建菜单
        
        Args:
            data: 菜单创建数据
        
        Returns:
            创建的菜单
        """
        await self._validate_menu_payload(
            menu_id=None,
            menu_type=data.menu_type,
            parent_id=data.parent_id,
            path=data.path,
            component=data.component,
        )
        menu = SysMenu(
            id=str(uuid.uuid4()),
            menu_name=data.menu_name,
            menu_type=data.menu_type,
            parent_id=data.parent_id,
            path=data.path,
            component=data.component,
            icon=data.icon,
            perm_code=data.perm_code,
            sort_order=data.sort_order,
            visible=data.visible,
            status=data.status
        )
        self.db.add(menu)
        await self.db.commit()
        await self.db.refresh(menu)
        
        # 自动将新菜单分配给 admin 角色
        await self._auto_assign_to_admin(menu.id)
        
        logger.info(f"创建菜单成功: {menu.menu_name}")
        
        return self._to_response(menu)
    
    async def update_menu(self, menu_id: str, data: MenuUpdate) -> Optional[MenuResponse]:
        """
        更新菜单
        
        Args:
            menu_id: 菜单ID
            data: 更新数据
        
        Returns:
            更新后的菜单或 None
        """
        stmt = select(SysMenu).where(
            and_(
                SysMenu.id == menu_id,
                SysMenu.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        menu = result.scalar_one_or_none()
        
        if not menu:
            return None

        # 计算更新后的目标值（用于校验）
        target_menu_type = data.menu_type if data.menu_type is not None else menu.menu_type
        target_parent_id = data.parent_id if data.parent_id is not None else menu.parent_id
        target_path = data.path if data.path is not None else menu.path
        target_component = (
            data.component if data.component is not None else menu.component
        )

        await self._validate_menu_payload(
            menu_id=menu_id,
            menu_type=target_menu_type,
            parent_id=target_parent_id,
            path=target_path,
            component=target_component,
        )
        
        # 更新字段
        if data.menu_name is not None:
            menu.menu_name = data.menu_name
        if data.menu_type is not None:
            menu.menu_type = data.menu_type
        if data.parent_id is not None:
            menu.parent_id = data.parent_id
        if data.path is not None:
            menu.path = data.path
        if data.component is not None:
            menu.component = data.component
        if data.icon is not None:
            menu.icon = data.icon
        if data.perm_code is not None:
            menu.perm_code = data.perm_code
        if data.sort_order is not None:
            menu.sort_order = data.sort_order
        if data.visible is not None:
            menu.visible = data.visible
        if data.status is not None:
            menu.status = data.status
        
        await self.db.commit()
        await self.db.refresh(menu)
        
        logger.info(f"更新菜单成功: {menu.menu_name}")
        
        return self._to_response(menu)
    
    async def delete_menu(self, menu_id: str) -> bool:
        """
        删除菜单（软删除）
        
        Args:
            menu_id: 菜单ID
        
        Returns:
            是否删除成功
        """
        stmt = select(SysMenu).where(
            and_(
                SysMenu.id == menu_id,
                SysMenu.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        menu = result.scalar_one_or_none()
        
        if not menu:
            return False
        
        # 检查是否有子菜单
        child_stmt = select(func.count()).select_from(SysMenu).where(
            and_(
                SysMenu.parent_id == menu_id,
                SysMenu.is_deleted == 0
            )
        )
        child_count = (await self.db.execute(child_stmt)).scalar()
        
        if child_count > 0:
            raise ValueError(f"该菜单下还有 {child_count} 个子菜单，请先删除子菜单")
        
        # 软删除
        menu.is_deleted = 1
        
        # 删除角色菜单关联
        await self.db.execute(
            delete(SysRoleMenu).where(SysRoleMenu.menu_id == menu_id)
        )
        
        await self.db.commit()
        
        logger.info(f"删除菜单成功: {menu.menu_name}")
        
        return True
    
    async def get_menu(self, menu_id: str) -> Optional[MenuResponse]:
        """
        获取菜单详情
        
        Args:
            menu_id: 菜单ID
        
        Returns:
            菜单详情或 None
        """
        stmt = select(SysMenu).where(
            and_(
                SysMenu.id == menu_id,
                SysMenu.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        menu = result.scalar_one_or_none()
        
        if not menu:
            return None
        
        return self._to_response(menu)
    
    async def get_menu_list(self, filters: MenuFilters) -> List[MenuResponse]:
        """
        获取菜单列表（扁平）
        
        Args:
            filters: 查询过滤条件
        
        Returns:
            菜单列表
        """
        conditions = [SysMenu.is_deleted == 0]
        
        if filters.menu_name:
            conditions.append(SysMenu.menu_name.like(f"%{filters.menu_name}%"))
        if filters.menu_type:
            conditions.append(SysMenu.menu_type == filters.menu_type)
        if filters.status is not None:
            conditions.append(SysMenu.status == filters.status)
        
        stmt = select(SysMenu).where(and_(*conditions)).order_by(SysMenu.sort_order)
        result = await self.db.execute(stmt)
        menus = result.scalars().all()
        
        return [self._to_response(menu) for menu in menus]
    
    async def get_menu_tree(self) -> List[MenuTreeItem]:
        """
        获取菜单树
        
        Returns:
            菜单树
        """
        stmt = select(SysMenu).where(
            and_(
                SysMenu.is_deleted == 0,
                SysMenu.status == 1
            )
        ).order_by(SysMenu.sort_order)
        result = await self.db.execute(stmt)
        menus = result.scalars().all()
        
        return self._build_menu_tree(menus)
    
    async def get_menu_tree_simple(self) -> List[MenuTreeSimple]:
        """
        获取简化菜单树（用于角色权限配置）
        
        Returns:
            简化菜单树
        """
        stmt = select(SysMenu).where(
            and_(
                SysMenu.is_deleted == 0,
                SysMenu.status == 1
            )
        ).order_by(SysMenu.sort_order)
        result = await self.db.execute(stmt)
        menus = result.scalars().all()
        
        return self._build_simple_tree(menus)
    
    def _build_menu_tree(self, menus: List[SysMenu]) -> List[MenuTreeItem]:
        """构建菜单树"""
        menu_map: Dict[str, MenuTreeItem] = {}
        root_menus: List[MenuTreeItem] = []
        
        # 转换为 MenuTreeItem
        for menu in menus:
            item = MenuTreeItem(
                id=menu.id,
                parent_id=menu.parent_id,
                menu_name=menu.menu_name,
                menu_type=menu.menu_type,
                path=menu.path,
                component=menu.component,
                icon=menu.icon,
                perm_code=menu.perm_code,
                sort_order=menu.sort_order,
                visible=menu.visible,
                children=[]
            )
            menu_map[menu.id] = item
        
        # 构建树结构
        for item in menu_map.values():
            if item.parent_id == "0" or item.parent_id not in menu_map:
                root_menus.append(item)
            else:
                parent = menu_map.get(item.parent_id)
                if parent:
                    parent.children.append(item)
        
        return root_menus
    
    def _build_simple_tree(self, menus: List[SysMenu]) -> List[MenuTreeSimple]:
        """构建简化菜单树"""
        menu_map: Dict[str, MenuTreeSimple] = {}
        root_menus: List[MenuTreeSimple] = []
        
        # 转换为 MenuTreeSimple
        for menu in menus:
            item = MenuTreeSimple(
                key=menu.id,
                title=menu.menu_name,
                children=[]
            )
            menu_map[menu.id] = item
        
        # 构建树结构
        for menu in menus:
            item = menu_map[menu.id]
            if menu.parent_id == "0" or menu.parent_id not in menu_map:
                root_menus.append(item)
            else:
                parent = menu_map.get(menu.parent_id)
                if parent:
                    parent.children.append(item)
        
        return root_menus
    
    async def _auto_assign_to_admin(self, menu_id: str) -> None:
        """
        自动将菜单分配给 admin 角色
        
        Args:
            menu_id: 菜单ID
        """
        try:
            # 查找 admin 角色（role_code = 'admin'）
            stmt = select(SysRole).where(
                and_(
                    SysRole.role_code == 'admin',
                    SysRole.is_deleted == 0
                )
            )
            result = await self.db.execute(stmt)
            admin_role = result.scalar_one_or_none()
            
            if not admin_role:
                logger.warning("未找到 admin 角色，跳过自动分配菜单权限")
                return
            
            # 检查是否已存在关联
            check_stmt = select(SysRoleMenu).where(
                and_(
                    SysRoleMenu.role_id == admin_role.id,
                    SysRoleMenu.menu_id == menu_id
                )
            )
            existing = await self.db.execute(check_stmt)
            if existing.scalar_one_or_none():
                return  # 已存在，无需重复添加
            
            # 创建关联
            role_menu = SysRoleMenu(
                role_id=admin_role.id,
                menu_id=menu_id
            )
            self.db.add(role_menu)
            await self.db.commit()
            
            logger.info(f"自动将菜单 {menu_id} 分配给 admin 角色")
        except Exception as e:
            logger.error(f"自动分配菜单权限失败: {e}")
            # 不抛出异常，避免影响菜单创建
    
    def _to_response(self, menu: SysMenu) -> MenuResponse:
        """转换为响应模型"""
        return MenuResponse(
            id=menu.id,
            menu_name=menu.menu_name,
            menu_type=menu.menu_type,
            parent_id=menu.parent_id,
            path=menu.path,
            component=menu.component,
            icon=menu.icon,
            perm_code=menu.perm_code,
            sort_order=menu.sort_order,
            visible=menu.visible,
            status=menu.status,
            created_at=menu.created_at,
            updated_at=menu.updated_at
        )
    
    async def init_default_menus(self) -> int:
        """
        初始化默认菜单（如果不存在）
        
        Returns:
            创建的菜单数量
        """
        # 检查是否已有菜单
        stmt = select(func.count()).select_from(SysMenu).where(SysMenu.is_deleted == 0)
        count = (await self.db.execute(stmt)).scalar()
        
        if count > 0:
            logger.info(f"菜单已存在 {count} 条，跳过初始化")
            return 0
        
        # 默认菜单数据
        default_menus = [
            # Dashboard
            {"id": "dashboard", "parent_id": "0", "menu_name": "Dashboard", "menu_type": "M", "path": "/dashboard", "icon": "lucide:layout-dashboard", "sort_order": 1},
            {"id": "dashboard:workspace", "parent_id": "dashboard", "menu_name": "工作台", "menu_type": "C", "path": "/dashboard/workspace", "component": "dashboard/workspace/index", "icon": "lucide:home", "sort_order": 1},
            
            # 配置管理
            {"id": "config", "parent_id": "0", "menu_name": "配置管理", "menu_type": "M", "path": "/config", "icon": "lucide:settings", "sort_order": 2},
            {"id": "config:plugin", "parent_id": "config", "menu_name": "Plugin 管理", "menu_type": "C", "path": "/config/plugin", "component": "config/plugin/index", "icon": "lucide:puzzle", "perm_code": "config:plugin", "sort_order": 1},
            {"id": "config:expert-config", "parent_id": "config", "menu_name": "ExpertConfig 管理", "menu_type": "C", "path": "/config/expert-config", "component": "config/expert-config/index", "icon": "lucide:flask-conical", "perm_code": "config:expert-config", "sort_order": 2},
            
            # Job 工作台
            {"id": "job", "parent_id": "0", "menu_name": "Job 工作台", "menu_type": "M", "path": "/job", "icon": "lucide:workflow", "sort_order": 3},
            {"id": "job:list", "parent_id": "job", "menu_name": "任务列表", "menu_type": "C", "path": "/job/list", "component": "job/list/index", "icon": "lucide:list", "perm_code": "job:list", "sort_order": 1},
            {"id": "job:create", "parent_id": "job", "menu_name": "创建任务", "menu_type": "C", "path": "/job/create", "component": "job/create/index", "icon": "lucide:plus-circle", "perm_code": "job:create", "sort_order": 2},
            {"id": "job:variant-library", "parent_id": "job", "menu_name": "方案库（Variant）", "menu_type": "C", "path": "/job/variant-library", "component": "job/variant-library/index", "icon": "lucide:layers", "perm_code": "job:variant-library", "sort_order": 3},
            
            # Expert 调试
            {"id": "expert", "parent_id": "0", "menu_name": "Expert 调试", "menu_type": "M", "path": "/expert", "icon": "lucide:bug", "sort_order": 4},
            {"id": "expert:debug", "parent_id": "expert", "menu_name": "调试面板", "menu_type": "C", "path": "/expert/debug", "component": "expert/debug/index", "icon": "lucide:wrench", "perm_code": "expert:debug", "sort_order": 1},
            
            # 调用追踪
            {"id": "trace", "parent_id": "0", "menu_name": "调用追踪", "menu_type": "M", "path": "/trace", "icon": "lucide:activity", "sort_order": 5},
            {"id": "trace:list", "parent_id": "trace", "menu_name": "调用记录", "menu_type": "C", "path": "/trace/list", "component": "trace/list/index", "icon": "lucide:scroll-text", "perm_code": "trace:list", "sort_order": 1},
            
            # 系统设置
            {"id": "system", "parent_id": "0", "menu_name": "系统设置", "menu_type": "M", "path": "/system", "icon": "lucide:shield", "sort_order": 6},
            {"id": "system:user", "parent_id": "system", "menu_name": "用户管理", "menu_type": "C", "path": "/system/user", "component": "system/user/index", "icon": "lucide:users", "perm_code": "system:user", "sort_order": 1},
            {"id": "system:role", "parent_id": "system", "menu_name": "角色管理", "menu_type": "C", "path": "/system/role", "component": "system/role/index", "icon": "lucide:shield", "perm_code": "system:role", "sort_order": 2},
            {"id": "system:menu", "parent_id": "system", "menu_name": "菜单管理", "menu_type": "C", "path": "/system/menu", "component": "system/menu/index", "icon": "lucide:menu", "perm_code": "system:menu", "sort_order": 3},
            {"id": "system:info", "parent_id": "system", "menu_name": "系统信息", "menu_type": "C", "path": "/system/info", "component": "system/info/index", "icon": "lucide:info", "perm_code": "system:info", "sort_order": 4},
        ]
        
        created = 0
        created_menu_ids: List[str] = []
        for menu_data in default_menus:
            menu = SysMenu(
                id=menu_data["id"],
                parent_id=menu_data["parent_id"],
                menu_name=menu_data["menu_name"],
                menu_type=menu_data["menu_type"],
                path=menu_data.get("path"),
                component=menu_data.get("component"),
                icon=menu_data.get("icon"),
                perm_code=menu_data.get("perm_code"),
                sort_order=menu_data.get("sort_order", 0),
                visible=1,
                status=1
            )
            self.db.add(menu)
            created += 1
            created_menu_ids.append(menu.id)
        
        await self.db.commit()

        # 将默认菜单分配给 admin 角色
        try:
            stmt = select(SysRole).where(
                and_(
                    SysRole.role_code == "admin",
                    SysRole.is_deleted == 0,
                )
            )
            result = await self.db.execute(stmt)
            admin_role = result.scalar_one_or_none()

            if admin_role:
                for menu_id in created_menu_ids:
                    role_menu = SysRoleMenu(role_id=admin_role.id, menu_id=menu_id)
                    self.db.add(role_menu)
                await self.db.commit()
                logger.info(f"默认菜单已分配给 admin 角色，共 {len(created_menu_ids)} 条")
            else:
                logger.warning("未找到 admin 角色，默认菜单未分配权限")
        except Exception as e:
            logger.error(f"分配默认菜单给 admin 角色失败: {e}")
        
        logger.info(f"初始化默认菜单成功，创建 {created} 条")
        
        return created

    async def import_menus(
        self,
        menus: List[MenuImportItem],
        mode: str = "append",
        role_codes: List[str] = None,
    ) -> MenuImportResult:
        """
        批量导入菜单
        
        Args:
            menus: 菜单列表
            mode: 导入模式 (append=追加, replace=覆盖)
            role_codes: 分配给哪些角色
        
        Returns:
            导入结果
        """
        if role_codes is None:
            role_codes = ["admin"]
        
        created = 0
        skipped = 0
        skipped_paths: List[str] = []
        new_menu_ids: List[str] = []
        
        # 构建原 ID 到新 ID 的映射（用于处理 parent_id）
        id_mapping: Dict[str, str] = {"0": "0"}
        
        # 覆盖模式：先删除所有现有菜单及其角色关联
        if mode == "replace":
            # 获取所有现有菜单 ID（包括已软删除的）
            stmt = select(SysMenu).where(SysMenu.is_deleted == 0)
            result = await self.db.execute(stmt)
            existing_menus = result.scalars().all()
            existing_menu_ids = [m.id for m in existing_menus]
            
            # 获取已软删除的菜单 ID（用于清理历史数据）
            deleted_stmt = select(SysMenu.id).where(SysMenu.is_deleted == 1)
            deleted_result = await self.db.execute(deleted_stmt)
            deleted_menu_ids = [row[0] for row in deleted_result.fetchall()]
            
            # 删除角色菜单关联（包括活跃菜单和已软删除菜单的关联）
            all_menu_ids_to_clean = existing_menu_ids + deleted_menu_ids
            if all_menu_ids_to_clean:
                await self.db.execute(
                    delete(SysRoleMenu).where(SysRoleMenu.menu_id.in_(all_menu_ids_to_clean))
                )
                logger.info(f"覆盖模式：已删除 {len(all_menu_ids_to_clean)} 条菜单的角色关联")
            
            # 物理删除已软删除的菜单（清理历史数据）
            if deleted_menu_ids:
                await self.db.execute(
                    delete(SysMenu).where(SysMenu.is_deleted == 1)
                )
                logger.info(f"覆盖模式：已物理删除 {len(deleted_menu_ids)} 条历史软删除菜单")
            
            # 软删除现有活跃菜单
            for menu in existing_menus:
                menu.is_deleted = 1
            
            # 必须先 commit，否则新菜单会和软删除的记录产生 path 唯一索引冲突
            await self.db.commit()
            logger.info(f"覆盖模式：已软删除 {len(existing_menus)} 条现有菜单")
        
        # 按层级排序：使用拓扑排序确保父菜单总是在子菜单之前处理
        # 1. 建立 id -> menu 映射
        menu_by_id = {m.id: m for m in menus if m.id}
        
        # 2. 计算每个菜单的层级深度
        def get_depth(menu_item, depth_cache: dict) -> int:
            if menu_item.id in depth_cache:
                return depth_cache[menu_item.id]
            if menu_item.parent_id == "0" or menu_item.parent_id not in menu_by_id:
                depth_cache[menu_item.id] = 0
                return 0
            parent = menu_by_id.get(menu_item.parent_id)
            if parent:
                depth = get_depth(parent, depth_cache) + 1
            else:
                depth = 0
            depth_cache[menu_item.id] = depth
            return depth
        
        depth_cache: dict = {}
        # 3. 按层级深度排序，同层级按 sort_order 排序
        sorted_menus = sorted(menus, key=lambda m: (get_depth(m, depth_cache), m.sort_order))
        
        for menu_item in sorted_menus:
            # 检查 path 是否已存在（仅追加模式）
            if mode == "append" and menu_item.path:
                stmt = select(func.count()).select_from(SysMenu).where(
                    and_(SysMenu.path == menu_item.path, SysMenu.is_deleted == 0)
                )
                existing_count = (await self.db.execute(stmt)).scalar()
                if existing_count > 0:
                    skipped += 1
                    skipped_paths.append(menu_item.path)
                    # 保留原 ID 映射，以便子菜单能找到父菜单
                    if menu_item.id:
                        # 查找现有菜单的 ID
                        existing_stmt = select(SysMenu).where(
                            and_(SysMenu.path == menu_item.path, SysMenu.is_deleted == 0)
                        )
                        existing_menu = (await self.db.execute(existing_stmt)).scalar_one_or_none()
                        if existing_menu:
                            id_mapping[menu_item.id] = existing_menu.id
                    continue
            
            # 解析 parent_id
            new_parent_id = id_mapping.get(menu_item.parent_id, "0")
            
            # 生成新 ID
            new_id = str(uuid.uuid4())
            
            # 创建菜单
            menu = SysMenu(
                id=new_id,
                parent_id=new_parent_id,
                menu_name=menu_item.menu_name,
                menu_type=menu_item.menu_type,
                path=menu_item.path,
                component=menu_item.component,
                icon=menu_item.icon,
                perm_code=menu_item.perm_code,
                sort_order=menu_item.sort_order,
                visible=menu_item.visible,
                status=1,
            )
            self.db.add(menu)
            
            # 记录 ID 映射
            if menu_item.id:
                id_mapping[menu_item.id] = new_id
            
            new_menu_ids.append(new_id)
            created += 1
        
        await self.db.commit()
        
        # 分配权限给指定角色
        assigned_roles: List[str] = []
        for role_code in role_codes:
            try:
                stmt = select(SysRole).where(
                    and_(SysRole.role_code == role_code, SysRole.is_deleted == 0)
                )
                result = await self.db.execute(stmt)
                role = result.scalar_one_or_none()
                
                if not role:
                    logger.warning(f"角色 {role_code} 不存在，跳过权限分配")
                    continue
                
                # 批量创建角色菜单关联
                for menu_id in new_menu_ids:
                    # 检查是否已存在
                    check_stmt = select(SysRoleMenu).where(
                        and_(
                            SysRoleMenu.role_id == role.id,
                            SysRoleMenu.menu_id == menu_id,
                        )
                    )
                    existing = await self.db.execute(check_stmt)
                    if not existing.scalar_one_or_none():
                        role_menu = SysRoleMenu(role_id=role.id, menu_id=menu_id)
                        self.db.add(role_menu)
                
                await self.db.commit()
                assigned_roles.append(role_code)
                logger.info(f"已将 {len(new_menu_ids)} 个菜单分配给角色 {role_code}")
            except Exception as e:
                logger.error(f"分配权限给角色 {role_code} 失败: {e}")
        
        logger.info(f"菜单导入完成: 总数={len(menus)}, 创建={created}, 跳过={skipped}")
        
        return MenuImportResult(
            total=len(menus),
            created=created,
            skipped=skipped,
            skipped_paths=skipped_paths,
            assigned_roles=assigned_roles,
        )
