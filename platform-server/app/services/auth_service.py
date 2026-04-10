"""
Authentication service
"""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.sys_user import SysUser
from app.models.sys_role import SysRole
from app.models.sys_menu import SysMenu
from app.models.sys_user_role import SysUserRole
from app.models.sys_role_menu import SysRoleMenu
from app.utils.jwt_utils import JWTUtils, create_token
from app.utils.password_utils import hash_password, verify_password
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    UserInfoResponse,
    MenuTreeItem,
)
from app.core.logger import logger


class AuthService:
    """认证服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def login(self, login_req: LoginRequest) -> Optional[LoginResponse]:
        """
        用户登录
        
        Args:
            login_req: 登录请求
        
        Returns:
            登录响应或 None（如果认证失败）
        """
        # 查询用户
        stmt = select(SysUser).where(
            and_(
                SysUser.username == login_req.username,
                SysUser.is_deleted == 0,
                SysUser.status == 1
            )
        )
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.warning(f"用户不存在或已禁用: {login_req.username}")
            return None
        
        # 验证密码
        if not verify_password(login_req.password, user.password):
            logger.warning(f"密码错误: {login_req.username}")
            return None
        
        # 生成 token，支持自定义过期时间
        expire_minutes = login_req.token_expire_minutes
        if expire_minutes:
            from datetime import timedelta
            expires_delta = timedelta(minutes=expire_minutes)
            token = JWTUtils.create_access_token(
                user.id, user.username, user.name, expires_delta=expires_delta
            )
            expire_time = int(datetime.utcnow().timestamp()) + expire_minutes * 60
            logger.info(f"用户登录成功: {user.username}, 自定义过期时间: {expire_minutes} 分钟")
        else:
            token = create_token(user.id, user.username, user.name)
            expire_time = int(datetime.utcnow().timestamp()) + JWTUtils.get_token_expire_time()
            logger.info(f"用户登录成功: {user.username}, 默认过期时间: {JWTUtils.ACCESS_TOKEN_EXPIRE_MINUTES} 分钟")
        
        return LoginResponse(
            id=user.id,
            username=user.username,
            name=user.name,
            avatar=user.avatar,
            token=token,
            access_token=token,
            expire_time=expire_time
        )
    
    async def get_user_info(self, user_id: str) -> Optional[UserInfoResponse]:
        """
        获取用户信息
        
        Args:
            user_id: 用户ID
        
        Returns:
            用户信息响应
        """
        try:
            # 查询用户（包含角色）
            stmt = select(SysUser).options(
                selectinload(SysUser.roles).selectinload(SysUserRole.role)
            ).where(
                and_(
                    SysUser.id == user_id,
                    SysUser.is_deleted == 0
                )
            )
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                return None
            
            # 获取角色编码列表
            role_codes = []
            role_ids = []
            for user_role in user.roles:
                if user_role.role and user_role.role.status == 1:
                    role_codes.append(user_role.role.role_code)
                    role_ids.append(user_role.role.id)
            
            # 获取权限码列表
            permissions = await self._get_user_permissions(role_ids)
            
            return UserInfoResponse(
                id=user.id,
                username=user.username,
                name=user.name,
                email=user.email,
                phone=user.phone,
                avatar=user.avatar,
                dept_id=user.dept_id,
                status=user.status,
                roles=role_codes,
                permissions=permissions
            )
        except Exception as e:
            logger.error(f"Error getting user info for {user_id}: {str(e)}", exc_info=True)
            raise
    
    async def get_user_menus(self, user_id: str) -> List[MenuTreeItem]:
        """
        获取用户菜单树
        
        Args:
            user_id: 用户ID
        
        Returns:
            菜单树列表
        """
        # 查询用户角色
        stmt = select(SysUserRole).where(SysUserRole.user_id == user_id)
        result = await self.db.execute(stmt)
        user_roles = result.scalars().all()
        
        if not user_roles:
            return []
        
        role_ids = [ur.role_id for ur in user_roles]
        
        # 查询角色菜单
        stmt = select(SysRoleMenu).where(SysRoleMenu.role_id.in_(role_ids))
        result = await self.db.execute(stmt)
        role_menus = result.scalars().all()
        
        if not role_menus:
            return []
        
        # 防御性检查：过滤掉 None 值
        menu_ids = list(set([rm.menu_id for rm in role_menus if rm is not None and rm.menu_id is not None]))
        
        if not menu_ids:
            return []
        
        # 查询菜单详情（包含隐藏菜单，前端根据 visible 字段决定是否显示）
        stmt = select(SysMenu).where(
            and_(
                SysMenu.id.in_(menu_ids),
                SysMenu.is_deleted == 0,
                SysMenu.status == 1
                # 移除 visible==1 过滤，允许返回隐藏菜单（详情页等）
            )
        ).order_by(SysMenu.sort_order)
        result = await self.db.execute(stmt)
        menus = result.scalars().all()
        
        # 构建菜单树
        return self._build_menu_tree(menus)
    
    async def get_user_perm_codes(self, user_id: str) -> List[str]:
        """
        获取用户权限码列表
        
        Args:
            user_id: 用户ID
        
        Returns:
            权限码列表
        """
        # 查询用户角色
        stmt = select(SysUserRole).where(SysUserRole.user_id == user_id)
        result = await self.db.execute(stmt)
        user_roles = result.scalars().all()
        
        if not user_roles:
            return []
        
        role_ids = [ur.role_id for ur in user_roles]
        
        return await self._get_user_permissions(role_ids)
    
    async def _get_user_permissions(self, role_ids: List[str]) -> List[str]:
        """获取角色权限码"""
        if not role_ids:
            return []
        
        # 查询角色菜单
        stmt = select(SysRoleMenu).where(SysRoleMenu.role_id.in_(role_ids))
        result = await self.db.execute(stmt)
        role_menus = result.scalars().all()
        
        if not role_menus:
            return []
        
        # 防御性检查：过滤掉 None 值，避免 'NoneType' object has no attribute 'menu_id' 错误
        menu_ids = list(set([rm.menu_id for rm in role_menus if rm is not None and rm.menu_id is not None]))
        
        # 查询菜单权限码
        stmt = select(SysMenu.perm_code).where(
            and_(
                SysMenu.id.in_(menu_ids),
                SysMenu.is_deleted == 0,
                SysMenu.perm_code.isnot(None)
            )
        )
        result = await self.db.execute(stmt)
        perm_codes = [row[0] for row in result.all() if row[0]]
        
        return list(set(perm_codes))
    
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
    
    async def create_default_admin(self) -> Optional[SysUser]:
        """
        创建默认管理员账号（如果不存在）
        
        Returns:
            创建的用户或 None
        """
        # 检查是否已存在
        stmt = select(SysUser).where(SysUser.username == "admin")
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            return None
        
        # 创建管理员用户
        admin_user = SysUser(
            id=str(uuid.uuid4()),
            username="admin",
            password=hash_password("Admin@123"),
            name="超级管理员",
            status=1
        )
        self.db.add(admin_user)
        
        # 创建管理员角色
        admin_role = SysRole(
            id=str(uuid.uuid4()),
            role_code="admin",
            role_name="超级管理员",
            description="系统超级管理员",
            status=1
        )
        self.db.add(admin_role)
        
        # 关联用户角色
        user_role = SysUserRole(
            user_id=admin_user.id,
            role_id=admin_role.id
        )
        self.db.add(user_role)
        
        await self.db.commit()
        
        logger.info("默认管理员账号创建成功: admin / Admin@123")
        
        return admin_user

