"""
System User service
"""
import uuid
import time
from typing import Optional, List, Tuple

from sqlalchemy import select, and_, func, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sys_user import SysUser
from app.models.sys_role import SysRole
from app.models.sys_user_role import SysUserRole
from app.schemas.sys_user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserFilters,
    UserSimpleItem,
    PasswordUpdate,
    PasswordChange,
)
from app.utils.password_utils import hash_password, verify_password
from app.core.logger import logger


class SysUserService:
    """用户服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_user(self, data: UserCreate) -> UserResponse:
        """
        创建用户
        
        Args:
            data: 用户创建数据
        
        Returns:
            创建的用户
        
        Raises:
            ValueError: 用户名已存在
        """
        # 检查用户名是否已存在
        stmt = select(SysUser).where(
            and_(
                SysUser.username == data.username,
                SysUser.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            raise ValueError(f"用户名 '{data.username}' 已存在")
        
        # 检查邮箱是否已存在
        if data.email:
            stmt = select(SysUser).where(
                and_(
                    SysUser.email == data.email,
                    SysUser.is_deleted == 0
                )
            )
            result = await self.db.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                raise ValueError(f"邮箱 '{data.email}' 已被使用")
        
        # 创建用户
        user = SysUser(
            id=str(uuid.uuid4()),
            username=data.username,
            password=hash_password(data.password),
            name=data.name,
            email=data.email,
            phone=data.phone,
            avatar=data.avatar,
            dept_id=data.dept_id,
            status=data.status
        )
        self.db.add(user)
        
        # 分配角色
        if data.role_ids:
            for role_id in data.role_ids:
                user_role = SysUserRole(
                    user_id=user.id,
                    role_id=role_id
                )
                self.db.add(user_role)
        
        await self.db.commit()
        await self.db.refresh(user)
        
        logger.info(f"创建用户成功: {user.username}")
        
        return await self._to_response(user)
    
    async def update_user(self, user_id: str, data: UserUpdate) -> Optional[UserResponse]:
        """
        更新用户
        
        Args:
            user_id: 用户ID
            data: 更新数据
        
        Returns:
            更新后的用户或 None
        """
        # 查询用户
        stmt = select(SysUser).where(
            and_(
                SysUser.id == user_id,
                SysUser.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return None
        
        # 检查邮箱是否已被其他用户使用
        if data.email is not None and data.email != user.email:
            stmt = select(SysUser).where(
                and_(
                    SysUser.email == data.email,
                    SysUser.id != user_id,
                    SysUser.is_deleted == 0
                )
            )
            result = await self.db.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                raise ValueError(f"邮箱 '{data.email}' 已被使用")
        
        # 更新字段
        if data.name is not None:
            user.name = data.name
        if data.email is not None:
            user.email = data.email
        if data.phone is not None:
            user.phone = data.phone
        if data.avatar is not None:
            user.avatar = data.avatar
        if data.dept_id is not None:
            user.dept_id = data.dept_id
        if data.status is not None:
            user.status = data.status
        
        # 更新角色关联
        if data.role_ids is not None:
            # 删除旧的关联
            await self.db.execute(
                delete(SysUserRole).where(SysUserRole.user_id == user_id)
            )
            # 添加新的关联
            for role_id in data.role_ids:
                user_role = SysUserRole(
                    user_id=user_id,
                    role_id=role_id
                )
                self.db.add(user_role)
        
        await self.db.commit()
        await self.db.refresh(user)
        
        logger.info(f"更新用户成功: {user.username}")
        
        return await self._to_response(user)
    
    async def delete_user(self, user_id: str) -> bool:
        """
        删除用户（软删除）
        
        Args:
            user_id: 用户ID
        
        Returns:
            是否删除成功
        """
        # 查询用户
        stmt = select(SysUser).where(
            and_(
                SysUser.id == user_id,
                SysUser.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return False
        
        # 检查是否为系统内置用户（admin 不允许删除）
        if user.username == "admin":
            raise ValueError("系统管理员账户不允许删除")
        
        # 软删除：同时修改 username 避免唯一索引冲突
        original_username = user.username
        user.is_deleted = 1
        user.username = f"{user.username}_deleted_{int(time.time())}"
        
        # 删除角色关联
        await self.db.execute(
            delete(SysUserRole).where(SysUserRole.user_id == user_id)
        )
        
        await self.db.commit()
        
        logger.info(f"删除用户成功: {original_username}")
        
        return True
    
    async def get_user(self, user_id: str) -> Optional[UserResponse]:
        """
        获取用户详情
        
        Args:
            user_id: 用户ID
        
        Returns:
            用户详情或 None
        """
        stmt = select(SysUser).where(
            and_(
                SysUser.id == user_id,
                SysUser.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return None
        
        return await self._to_response(user)
    
    async def get_user_by_username(self, username: str) -> Optional[SysUser]:
        """
        根据用户名获取用户
        
        Args:
            username: 用户名
        
        Returns:
            用户或 None
        """
        stmt = select(SysUser).where(
            and_(
                SysUser.username == username,
                SysUser.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_users(
        self, filters: UserFilters
    ) -> Tuple[int, List[UserResponse]]:
        """
        获取用户列表
        
        Args:
            filters: 查询过滤条件
        
        Returns:
            (总数, 用户列表)
        """
        # 构建查询条件
        conditions = [SysUser.is_deleted == 0]
        
        if filters.username:
            conditions.append(SysUser.username.like(f"%{filters.username}%"))
        if filters.name:
            conditions.append(SysUser.name.like(f"%{filters.name}%"))
        if filters.email:
            conditions.append(SysUser.email.like(f"%{filters.email}%"))
        if filters.phone:
            conditions.append(SysUser.phone.like(f"%{filters.phone}%"))
        if filters.status is not None:
            conditions.append(SysUser.status == filters.status)
        
        # 如果需要按角色过滤
        if filters.role_id:
            # 获取该角色下的用户ID列表
            role_user_stmt = select(SysUserRole.user_id).where(
                SysUserRole.role_id == filters.role_id
            )
            role_user_result = await self.db.execute(role_user_stmt)
            user_ids = [row[0] for row in role_user_result.all()]
            if user_ids:
                conditions.append(SysUser.id.in_(user_ids))
            else:
                # 没有用户属于该角色，直接返回空
                return 0, []
        
        # 查询总数
        count_stmt = select(func.count()).select_from(SysUser).where(and_(*conditions))
        total = (await self.db.execute(count_stmt)).scalar()
        
        # 查询列表
        offset = (filters.page - 1) * filters.page_size
        stmt = (
            select(SysUser)
            .where(and_(*conditions))
            .offset(offset)
            .limit(filters.page_size)
            .order_by(SysUser.created_at.desc())
        )
        result = await self.db.execute(stmt)
        users = result.scalars().all()
        
        items = []
        for user in users:
            items.append(await self._to_response(user))
        
        return total, items
    
    async def get_all_users(self) -> List[UserSimpleItem]:
        """
        获取所有用户（简单列表，用于下拉框）
        
        Returns:
            用户简单列表
        """
        stmt = select(SysUser).where(
            and_(
                SysUser.is_deleted == 0,
                SysUser.status == 1
            )
        ).order_by(SysUser.created_at)
        result = await self.db.execute(stmt)
        users = result.scalars().all()
        
        return [
            UserSimpleItem(
                id=user.id,
                username=user.username,
                name=user.name
            )
            for user in users
        ]
    
    async def reset_password(self, user_id: str, data: PasswordUpdate) -> bool:
        """
        重置用户密码（管理员操作）
        
        Args:
            user_id: 用户ID
            data: 新密码数据
        
        Returns:
            是否成功
        """
        # 查询用户
        stmt = select(SysUser).where(
            and_(
                SysUser.id == user_id,
                SysUser.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return False
        
        # 更新密码
        user.password = hash_password(data.new_password)
        
        await self.db.commit()
        
        logger.info(f"重置用户密码成功: {user.username}")
        
        return True
    
    async def change_password(self, user_id: str, data: PasswordChange) -> bool:
        """
        修改密码（用户自己操作，需要验证旧密码）
        
        Args:
            user_id: 用户ID
            data: 密码修改数据
        
        Returns:
            是否成功
        
        Raises:
            ValueError: 旧密码错误
        """
        # 查询用户
        stmt = select(SysUser).where(
            and_(
                SysUser.id == user_id,
                SysUser.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise ValueError("用户不存在")
        
        # 验证旧密码
        if not verify_password(data.old_password, user.password):
            raise ValueError("旧密码错误")
        
        # 更新密码
        user.password = hash_password(data.new_password)
        
        await self.db.commit()
        
        logger.info(f"用户修改密码成功: {user.username}")
        
        return True
    
    async def assign_roles(self, user_id: str, role_ids: List[str]) -> bool:
        """
        分配用户角色
        
        Args:
            user_id: 用户ID
            role_ids: 角色ID列表
        
        Returns:
            是否成功
        """
        # 检查用户是否存在
        stmt = select(SysUser).where(
            and_(
                SysUser.id == user_id,
                SysUser.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return False
        
        # 删除旧的关联
        await self.db.execute(
            delete(SysUserRole).where(SysUserRole.user_id == user_id)
        )
        
        # 添加新的关联
        for role_id in role_ids:
            user_role = SysUserRole(
                user_id=user_id,
                role_id=role_id
            )
            self.db.add(user_role)
        
        await self.db.commit()
        
        logger.info(f"分配用户角色成功: user_id={user_id}, roles={len(role_ids)}")
        
        return True
    
    async def get_user_roles(self, user_id: str) -> List[str]:
        """
        获取用户角色ID列表
        
        Args:
            user_id: 用户ID
        
        Returns:
            角色ID列表
        """
        stmt = select(SysUserRole.role_id).where(SysUserRole.user_id == user_id)
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]
    
    async def _to_response(self, user: SysUser) -> UserResponse:
        """转换为响应模型"""
        # 获取用户角色信息
        stmt = select(SysRole).join(
            SysUserRole, SysRole.id == SysUserRole.role_id
        ).where(
            and_(
                SysUserRole.user_id == user.id,
                SysRole.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        roles = result.scalars().all()
        
        role_codes = [role.role_code for role in roles]
        role_names = [role.role_name for role in roles]
        
        return UserResponse(
            id=user.id,
            username=user.username,
            name=user.name,
            email=user.email,
            phone=user.phone,
            avatar=user.avatar,
            dept_id=user.dept_id,
            status=user.status,
            created_at=user.created_at,
            updated_at=user.updated_at,
            roles=role_codes,
            role_names=role_names
        )

