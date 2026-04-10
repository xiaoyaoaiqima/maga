"""add message tables

Revision ID: 021_add_message_tables
Revises: 020_add_currency_fields
Create Date: 2025-12-21

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "021_add_message_tables"
down_revision: Union[str, None] = "020_add_currency_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "message",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, comment="技术主键"),
        sa.Column("title", sa.String(255), nullable=False, comment="消息标题"),
        sa.Column("content", sa.Text(), nullable=False, comment="消息内容"),
        sa.Column("message_type", sa.String(32), nullable=False, server_default="system", comment="消息类型（system/todo/...）"),
        sa.Column("link", sa.String(255), nullable=True, comment="跳转链接（站内 path 或外部 URL）"),
        sa.Column("sender_id", sa.String(64), nullable=True, comment="发送人ID（sys_user.id）"),
        sa.Column("sender_name", sa.String(64), nullable=True, comment="发送人名称（冗余字段，便于展示）"),
        sa.Column("create_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
        sa.Column("update_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), onupdate=sa.func.now(), comment="更新时间"),
        sa.Column("is_deleted", sa.Integer(), nullable=False, server_default="0", comment="是否删除（0否 1是）"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="站内消息表（消息主体）",
    )

    op.create_table(
        "message_recipient",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, comment="技术主键"),
        sa.Column("message_id", sa.BigInteger(), sa.ForeignKey("message.id"), nullable=False, index=True, comment="消息ID（message.id）"),
        sa.Column("user_id", sa.String(64), nullable=False, index=True, comment="接收用户ID（sys_user.id）"),
        sa.Column("is_read", sa.Integer(), nullable=False, server_default="0", index=True, comment="是否已读（0否 1是）"),
        sa.Column("read_time", sa.DateTime(), nullable=True, comment="阅读时间"),
        sa.Column("create_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
        sa.Column("update_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), onupdate=sa.func.now(), comment="更新时间"),
        sa.Column("is_deleted", sa.Integer(), nullable=False, server_default="0", comment="是否删除（0否 1是）"),
        sa.UniqueConstraint("message_id", "user_id", name="uk_message_user"),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_unicode_ci",
        comment="站内消息接收表（已读状态）",
    )

    # 初始化“消息中心”菜单，并赋权给 admin 角色（role_code=admin）
    # 说明：前端通过 /api/v1/auth/menus 拉取 sys_menu，并把 component 映射为 ../views/<component>.vue
    # 这里 component 不带 .vue，保持与现有默认菜单一致（例如 dashboard/workspace/index）
    op.execute(
        sa.text(
            """
            INSERT INTO sys_menu (id, parent_id, menu_name, menu_type, path, component, icon, perm_code, sort_order, visible, status, created_at, updated_at, is_deleted)
            SELECT :id, :parent_id, :menu_name, :menu_type, :path, :component, :icon, :perm_code, :sort_order, 1, 1, NOW(), NOW(), 0
            WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE id = :id AND is_deleted = 0);
            """
        ).bindparams(
            id="message",
            parent_id="0",
            menu_name="消息中心",
            menu_type="M",
            path="/message",
            component=None,
            icon="lucide:bell",
            perm_code=None,
            sort_order=7,
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO sys_menu (id, parent_id, menu_name, menu_type, path, component, icon, perm_code, sort_order, visible, status, created_at, updated_at, is_deleted)
            SELECT :id, :parent_id, :menu_name, :menu_type, :path, :component, :icon, :perm_code, :sort_order, 1, 1, NOW(), NOW(), 0
            WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE id = :id AND is_deleted = 0);
            """
        ).bindparams(
            id="message:center",
            parent_id="message",
            menu_name="全部消息",
            menu_type="C",
            path="/message/center",
            component="message-center/index",
            icon="lucide:mail",
            perm_code="message:center:view",
            sort_order=1,
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO sys_menu (id, parent_id, menu_name, menu_type, path, component, icon, perm_code, sort_order, visible, status, created_at, updated_at, is_deleted)
            SELECT :id, :parent_id, :menu_name, :menu_type, NULL, NULL, NULL, :perm_code, :sort_order, 0, 1, NOW(), NOW(), 0
            WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE id = :id AND is_deleted = 0);
            """
        ).bindparams(
            id="message:publish",
            parent_id="message:center",
            menu_name="发布系统消息",
            menu_type="F",
            perm_code="message:publish",
            sort_order=1,
        )
    )

    # 给 admin 角色赋权：插入 sys_role_menu（如果已存在则跳过）
    op.execute(
        sa.text(
            """
            INSERT INTO sys_role_menu (role_id, menu_id, created_at)
            SELECT r.id, m.id, NOW()
            FROM sys_role r
            JOIN sys_menu m ON m.id IN ('message', 'message:center', 'message:publish') AND m.is_deleted = 0
            WHERE r.role_code = 'admin'
              AND NOT EXISTS (
                SELECT 1 FROM sys_role_menu rm
                WHERE rm.role_id = r.id AND rm.menu_id = m.id
              );
            """
        )
    )


def downgrade() -> None:
    # 回滚菜单与授权（不删除 sys_menu 记录本身，做软删除以避免历史依赖）
    op.execute(
        sa.text(
            """
            UPDATE sys_menu
            SET is_deleted = 1, updated_at = NOW()
            WHERE id IN ('message', 'message:center', 'message:publish');
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM sys_role_menu
            WHERE menu_id IN ('message', 'message:center', 'message:publish');
            """
        )
    )

    op.drop_table("message_recipient")
    op.drop_table("message")


