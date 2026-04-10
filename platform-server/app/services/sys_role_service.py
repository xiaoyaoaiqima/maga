"""
System Role service
"""
# pylint: disable=not-callable
import uuid
import time
from typing import Optional, List, Tuple

from sqlalchemy import select, and_, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sys_role import SysRole
from app.models.sys_role_menu import SysRoleMenu
from app.models.sys_user_role import SysUserRole
from app.models.sys_user import SysUser
from app.schemas.sys_role import (
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    RoleFilters,
    RoleUserItem,
    RoleSimpleItem,
)
from app.core.logger import logger


class SysRoleService:
    """角色服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_role(self, data: RoleCreate) -> RoleResponse:
        """
        创建角色
        
        Args:
            data: 角色创建数据
        
        Returns:
            创建的角色
        
        Raises:
            ValueError: 角色编码已存在
        """
        # 检查角色编码是否已存在
        stmt = select(SysRole).where(
            and_(
                SysRole.role_code == data.role_code,
                SysRole.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            raise ValueError(f"角色编码 '{data.role_code}' 已存在")
        
        # 创建角色
        role = SysRole(
            id=str(uuid.uuid4()),
            role_code=data.role_code,
            role_name=data.role_name,
            description=data.description,
            status=data.status
        )
        self.db.add(role)
        
        # 分配菜单
        if data.menu_ids:
            for menu_id in data.menu_ids:
                role_menu = SysRoleMenu(
                    role_id=role.id,
                    menu_id=menu_id
                )
                self.db.add(role_menu)
        
        await self.db.commit()
        await self.db.refresh(role)
        
        logger.info(f"创建角色成功: {role.role_code}")
        
        return await self._to_response(role)
    
    async def update_role(self, role_id: str, data: RoleUpdate) -> Optional[RoleResponse]:
        """
        更新角色
        
        Args:
            role_id: 角色ID
            data: 更新数据
        
        Returns:
            更新后的角色或 None
        """
        # 查询角色
        stmt = select(SysRole).where(
            and_(
                SysRole.id == role_id,
                SysRole.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        role = result.scalar_one_or_none()
        
        if not role:
            return None
        
        # 更新字段
        if data.role_name is not None:
            role.role_name = data.role_name
        if data.description is not None:
            role.description = data.description
        if data.status is not None:
            role.status = data.status
        
        # 更新菜单关联
        if data.menu_ids is not None:
            # 删除旧的关联
            await self.db.execute(
                delete(SysRoleMenu).where(SysRoleMenu.role_id == role_id)
            )
            # 添加新的关联
            for menu_id in data.menu_ids:
                role_menu = SysRoleMenu(
                    role_id=role_id,
                    menu_id=menu_id
                )
                self.db.add(role_menu)
        
        await self.db.commit()
        await self.db.refresh(role)
        
        logger.info(f"更新角色成功: {role.role_code}")
        
        return await self._to_response(role)
    
    async def delete_role(self, role_id: str) -> bool:
        """
        删除角色（软删除）
        
        Args:
            role_id: 角色ID
        
        Returns:
            是否删除成功
        """
        # 查询角色
        stmt = select(SysRole).where(
            and_(
                SysRole.id == role_id,
                SysRole.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        role = result.scalar_one_or_none()
        
        if not role:
            return False
        
        # 检查是否为系统内置角色（admin 不允许删除）
        if role.role_code == "admin":
            raise ValueError("系统管理员角色不允许删除")
        
        # 检查是否有用户关联
        stmt = select(func.count()).select_from(SysUserRole).where(
            SysUserRole.role_id == role_id
        )
        result = await self.db.execute(stmt)
        user_count = result.scalar()
        
        if user_count > 0:
            raise ValueError(f"该角色下还有 {user_count} 个用户，请先移除用户后再删除角色")
        
        # 软删除：同时修改 role_code 避免唯一索引冲突
        original_code = role.role_code
        role.is_deleted = 1
        role.role_code = f"{role.role_code}_deleted_{int(time.time())}"
        
        # 删除菜单关联
        await self.db.execute(
            delete(SysRoleMenu).where(SysRoleMenu.role_id == role_id)
        )
        
        await self.db.commit()
        
        logger.info(f"删除角色成功: {original_code}")
        
        return True
    
    async def get_role(self, role_id: str) -> Optional[RoleResponse]:
        """
        获取角色详情
        
        Args:
            role_id: 角色ID
        
        Returns:
            角色详情或 None
        """
        stmt = select(SysRole).where(
            and_(
                SysRole.id == role_id,
                SysRole.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        role = result.scalar_one_or_none()
        
        if not role:
            return None
        
        return await self._to_response(role)
    
    async def get_roles(
        self, filters: RoleFilters
    ) -> Tuple[int, List[RoleResponse]]:
        """
        获取角色列表
        
        Args:
            filters: 查询过滤条件
        
        Returns:
            (总数, 角色列表)
        """
        # 构建查询条件
        conditions = [SysRole.is_deleted == 0]
        
        if filters.role_code:
            conditions.append(SysRole.role_code == filters.role_code)
        if filters.role_name:
            conditions.append(SysRole.role_name.like(f"%{filters.role_name}%"))
        if filters.status is not None:
            conditions.append(SysRole.status == filters.status)
        
        # 查询总数
        count_stmt = select(func.count()).select_from(SysRole).where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar()
        
        # 查询列表
        offset = (filters.page - 1) * filters.page_size
        stmt = select(SysRole).where(and_(*conditions)).offset(offset).limit(filters.page_size).order_by(SysRole.created_at.desc())
        result = await self.db.execute(stmt)
        roles = result.scalars().all()
        
        items = []
        for role in roles:
            items.append(await self._to_response(role))
        
        return total, items
    
    async def get_all_roles(self) -> List[RoleSimpleItem]:
        """
        获取所有角色（简单列表，用于下拉框）
        
        Returns:
            角色简单列表
        """
        stmt = select(SysRole).where(
            and_(
                SysRole.is_deleted == 0,
                SysRole.status == 1
            )
        ).order_by(SysRole.created_at)
        result = await self.db.execute(stmt)
        roles = result.scalars().all()
        
        return [
            RoleSimpleItem(
                id=role.id,
                role_code=role.role_code,
                role_name=role.role_name
            )
            for role in roles
        ]
    
    async def assign_menus(self, role_id: str, menu_ids: List[str]) -> bool:
        """
        分配角色菜单
        
        Args:
            role_id: 角色ID
            menu_ids: 菜单ID列表
        
        Returns:
            是否成功
        """
        # 检查角色是否存在
        stmt = select(SysRole).where(
            and_(
                SysRole.id == role_id,
                SysRole.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        role = result.scalar_one_or_none()
        
        if not role:
            return False
        
        # 删除旧的关联
        await self.db.execute(
            delete(SysRoleMenu).where(SysRoleMenu.role_id == role_id)
        )
        
        # 添加新的关联
        for menu_id in menu_ids:
            role_menu = SysRoleMenu(
                role_id=role_id,
                menu_id=menu_id
            )
            self.db.add(role_menu)
        
        await self.db.commit()
        
        logger.info(f"分配角色菜单成功: role_id={role_id}, menus={len(menu_ids)}")
        
        return True

    async def assign_menus_by_role_code(
        self,
        *,
        role_code: str,
        menu_ids: List[str],
        mode: str = "merge",
    ) -> Tuple[str, List[str]]:
        """
        按 role_code 分配菜单（merge/replace）

        Args:
            role_code: 角色编码（如 admin）
            menu_ids: 需要授予的菜单ID列表
            mode: merge 追加；replace 覆盖

        Returns:
            (role_id, 最终菜单ID列表)
        """
        if mode not in {"merge", "replace"}:
            raise ValueError("mode 仅支持 merge 或 replace")

        stmt = select(SysRole).where(
            and_(
                SysRole.role_code == role_code,
                SysRole.is_deleted == 0,
            )
        )
        result = await self.db.execute(stmt)
        role = result.scalar_one_or_none()
        if not role:
            raise ValueError("角色不存在")

        def _dedupe_keep_order(ids: List[str]) -> List[str]:
            seen = set()
            out: List[str] = []
            for item in ids:
                if item in seen:
                    continue
                seen.add(item)
                out.append(item)
            return out

        target_menu_ids = _dedupe_keep_order(menu_ids)
        if mode == "merge":
            existing_menu_ids = await self.get_role_menus(role.id)
            target_menu_ids = _dedupe_keep_order(existing_menu_ids + target_menu_ids)

        success = await self.assign_menus(role.id, target_menu_ids)
        if not success:
            raise ValueError("分配失败")

        return role.id, target_menu_ids
    
    async def get_role_menus(self, role_id: str) -> List[str]:
        """
        获取角色菜单ID列表
        
        Args:
            role_id: 角色ID
        
        Returns:
            菜单ID列表
        """
        stmt = select(SysRoleMenu.menu_id).where(SysRoleMenu.role_id == role_id)
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]
    
    async def get_role_users(
        self, role_id: str, page: int = 1, page_size: int = 10
    ) -> Tuple[int, List[RoleUserItem]]:
        """
        获取角色下的用户
        
        Args:
            role_id: 角色ID
            page: 页码
            page_size: 每页数量
        
        Returns:
            (总数, 用户列表)
        """
        # 查询总数
        count_stmt = select(func.count()).select_from(SysUserRole).where(
            SysUserRole.role_id == role_id
        )
        total = (await self.db.execute(count_stmt)).scalar()
        
        # 查询用户ID
        offset = (page - 1) * page_size
        stmt = select(SysUserRole.user_id).where(
            SysUserRole.role_id == role_id
        ).offset(offset).limit(page_size)
        result = await self.db.execute(stmt)
        user_ids = [row[0] for row in result.all()]
        
        if not user_ids:
            return 0, []
        
        # 查询用户详情
        stmt = select(SysUser).where(
            and_(
                SysUser.id.in_(user_ids),
                SysUser.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        users = result.scalars().all()
        
        items = [
            RoleUserItem(
                id=user.id,
                username=user.username,
                name=user.name,
                email=user.email,
                avatar=user.avatar
            )
            for user in users
        ]
        
        return total, items
    
    async def add_users_to_role(self, role_id: str, user_ids: List[str]) -> int:
        """
        添加用户到角色
        
        Args:
            role_id: 角色ID
            user_ids: 用户ID列表
        
        Returns:
            成功添加的数量
        """
        # 检查角色是否存在
        stmt = select(SysRole).where(
            and_(
                SysRole.id == role_id,
                SysRole.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        role = result.scalar_one_or_none()
        
        if not role:
            raise ValueError("角色不存在")
        
        # 查询已存在的关联
        stmt = select(SysUserRole.user_id).where(
            and_(
                SysUserRole.role_id == role_id,
                SysUserRole.user_id.in_(user_ids)
            )
        )
        result = await self.db.execute(stmt)
        existing_user_ids = set(row[0] for row in result.all())
        
        # 添加新的关联
        added_count = 0
        for user_id in user_ids:
            if user_id not in existing_user_ids:
                user_role = SysUserRole(
                    user_id=user_id,
                    role_id=role_id
                )
                self.db.add(user_role)
                added_count += 1
        
        await self.db.commit()
        
        logger.info(f"添加用户到角色成功: role_id={role_id}, added={added_count}")
        
        return added_count
    
    async def remove_user_from_role(self, role_id: str, user_id: str) -> bool:
        """
        从角色中移除用户
        
        Args:
            role_id: 角色ID
            user_id: 用户ID
        
        Returns:
            是否成功
        """
        await self.db.execute(
            delete(SysUserRole).where(
                and_(
                    SysUserRole.role_id == role_id,
                    SysUserRole.user_id == user_id
                )
            )
        )
        await self.db.commit()
        
        logger.info(f"从角色移除用户成功: role_id={role_id}, user_id={user_id}")
        
        return True
    
    async def _to_response(self, role: SysRole) -> RoleResponse:
        """转换为响应模型"""
        # 获取菜单ID列表
        menu_ids = await self.get_role_menus(role.id)
        
        return RoleResponse(
            id=role.id,
            role_code=role.role_code,
            role_name=role.role_name,
            description=role.description,
            status=role.status,
            created_at=role.created_at,
            updated_at=role.updated_at,
            menu_ids=menu_ids
        )

