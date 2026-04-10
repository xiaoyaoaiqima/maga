"""add admin_tool_task table and admin-tools menu

Revision ID: 20251224_add_admin_tools_task
Revises: 4d55483af7d9
Create Date: 2025-12-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = "20251224_add_admin_tools_task"
down_revision: Union[str, Sequence[str], None] = ("4d55483af7d9", "025_add_rlhf_review_user_fields")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "admin_tool_task" not in tables:
        op.create_table(
            "admin_tool_task",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, comment="主键"),
            sa.Column("task_type", sa.String(64), nullable=False, comment="任务类型"),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending", comment="状态"),
            sa.Column("progress", sa.Integer(), nullable=False, server_default="0", comment="进度 0~100"),
            sa.Column("message", sa.String(512), nullable=True, comment="提示信息"),
            sa.Column("params", mysql.JSON(), nullable=True, comment="任务参数"),
            sa.Column("result", mysql.JSON(), nullable=True, comment="任务结果"),
            sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"),
            sa.Column("created_by", sa.String(64), nullable=True, comment="创建人 user_id"),
            sa.Column("started_at", sa.DateTime(), nullable=True, comment="开始时间"),
            sa.Column("finished_at", sa.DateTime(), nullable=True, comment="结束时间"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True, comment="创建时间"),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=True,
                comment="更新时间",
            ),
            comment="管理工具异步任务表",
        )
        op.create_index("idx_admin_tool_task_type", "admin_tool_task", ["task_type"])
        op.create_index("idx_admin_tool_task_status", "admin_tool_task", ["status", "created_at"])
        op.create_index("idx_admin_tool_task_created_by", "admin_tool_task", ["created_by", "created_at"])

    # 插入菜单：系统设置 -> 管理工具（若不存在）
    if "sys_menu" in tables:
        # 仅当 system 根菜单存在时插入
        exists_system = conn.execute(sa.text("SELECT COUNT(*) FROM sys_menu WHERE id='system' AND is_deleted=0")).scalar()
        exists_menu = conn.execute(
            sa.text("SELECT COUNT(*) FROM sys_menu WHERE id='system:admin-tools' AND is_deleted=0")
        ).scalar()
        if exists_system and not exists_menu:
            conn.execute(
                sa.text(
                    """
INSERT INTO sys_menu (
  id, parent_id, menu_name, menu_type, path, component, icon, perm_code, sort_order, visible, status, is_deleted, created_at, updated_at
) VALUES (
  'system:admin-tools', 'system', '管理工具', 'C', '/system/admin-tools', 'system/admin-tools/index',
  'lucide:tool', 'system:admin-tools', 99, 1, 1, 0, NOW(), NOW()
);
"""
                )
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "sys_menu" in tables:
        conn.execute(sa.text("UPDATE sys_menu SET is_deleted=1 WHERE id='system:admin-tools';"))

    if "admin_tool_task" in tables:
        op.drop_index("idx_admin_tool_task_created_by", table_name="admin_tool_task")
        op.drop_index("idx_admin_tool_task_status", table_name="admin_tool_task")
        op.drop_index("idx_admin_tool_task_type", table_name="admin_tool_task")
        op.drop_table("admin_tool_task")


