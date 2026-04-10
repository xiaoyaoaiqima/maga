"""add auth tables

Revision ID: 001_add_auth_tables
Revises: 
Create Date: 2025-12-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_add_auth_tables'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 创建系统用户表
    op.create_table(
        'sys_user',
        sa.Column('id', sa.String(64), primary_key=True, comment='用户ID'),
        sa.Column('username', sa.String(64), unique=True, nullable=False, index=True, comment='用户名'),
        sa.Column('password', sa.String(255), nullable=False, comment='密码(bcrypt)'),
        sa.Column('name', sa.String(64), nullable=True, comment='姓名'),
        sa.Column('email', sa.String(128), nullable=True, comment='邮箱'),
        sa.Column('phone', sa.String(20), nullable=True, comment='手机号'),
        sa.Column('avatar', sa.String(255), nullable=True, comment='头像URL'),
        sa.Column('dept_id', sa.String(64), nullable=True, comment='部门ID'),
        sa.Column('status', sa.Integer(), default=1, comment='状态: 0禁用 1启用'),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now(), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now(), comment='更新时间'),
        sa.Column('is_deleted', sa.Integer(), default=0, comment='是否删除: 0否 1是'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
        comment='系统用户表'
    )
    
    # 创建系统角色表
    op.create_table(
        'sys_role',
        sa.Column('id', sa.String(64), primary_key=True, comment='角色ID'),
        sa.Column('role_code', sa.String(64), unique=True, nullable=False, index=True, comment='角色编码'),
        sa.Column('role_name', sa.String(64), nullable=False, comment='角色名称'),
        sa.Column('description', sa.String(255), nullable=True, comment='描述'),
        sa.Column('status', sa.Integer(), default=1, comment='状态: 0禁用 1启用'),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now(), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now(), comment='更新时间'),
        sa.Column('is_deleted', sa.Integer(), default=0, comment='是否删除: 0否 1是'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
        comment='系统角色表'
    )
    
    # 创建系统菜单表
    op.create_table(
        'sys_menu',
        sa.Column('id', sa.String(64), primary_key=True, comment='菜单ID'),
        sa.Column('parent_id', sa.String(64), default='0', comment='父菜单ID'),
        sa.Column('menu_name', sa.String(64), nullable=False, comment='菜单名称'),
        sa.Column('menu_type', sa.String(1), nullable=False, comment='类型: M目录 C菜单 F按钮'),
        sa.Column('path', sa.String(255), nullable=True, comment='路由路径'),
        sa.Column('component', sa.String(255), nullable=True, comment='组件路径'),
        sa.Column('icon', sa.String(64), nullable=True, comment='图标'),
        sa.Column('perm_code', sa.String(128), nullable=True, comment='权限标识'),
        sa.Column('sort_order', sa.Integer(), default=0, comment='排序'),
        sa.Column('visible', sa.Integer(), default=1, comment='是否可见: 0否 1是'),
        sa.Column('status', sa.Integer(), default=1, comment='状态: 0禁用 1启用'),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now(), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now(), comment='更新时间'),
        sa.Column('is_deleted', sa.Integer(), default=0, comment='是否删除: 0否 1是'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
        comment='系统菜单表'
    )
    
    # 创建用户角色关联表
    op.create_table(
        'sys_user_role',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True, comment='主键'),
        sa.Column('user_id', sa.String(64), sa.ForeignKey('sys_user.id'), nullable=False, index=True, comment='用户ID'),
        sa.Column('role_id', sa.String(64), sa.ForeignKey('sys_role.id'), nullable=False, index=True, comment='角色ID'),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now(), comment='创建时间'),
        sa.UniqueConstraint('user_id', 'role_id', name='uk_user_role'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
        comment='用户角色关联表'
    )
    
    # 创建角色菜单关联表
    op.create_table(
        'sys_role_menu',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True, comment='主键'),
        sa.Column('role_id', sa.String(64), sa.ForeignKey('sys_role.id'), nullable=False, index=True, comment='角色ID'),
        sa.Column('menu_id', sa.String(64), sa.ForeignKey('sys_menu.id'), nullable=False, index=True, comment='菜单ID'),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now(), comment='创建时间'),
        sa.UniqueConstraint('role_id', 'menu_id', name='uk_role_menu'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
        comment='角色菜单关联表'
    )


def downgrade() -> None:
    op.drop_table('sys_role_menu')
    op.drop_table('sys_user_role')
    op.drop_table('sys_menu')
    op.drop_table('sys_role')
    op.drop_table('sys_user')
