"""add prompt debug thinking mode

Revision ID: 035_add_prompt_debug_thinking_mode
Revises: 034_add_prompt_debug_history
Create Date: 2026-08-18

"""
from alembic import op
import sqlalchemy as sa


revision = "035_add_prompt_debug_thinking_mode"
down_revision = "034_add_prompt_debug_history"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    columns = sa.inspect(op.get_bind()).get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def upgrade() -> None:
    if not _column_exists("content_prompt_debug_history", "thinking_mode"):
        op.add_column(
            "content_prompt_debug_history",
            sa.Column(
                "thinking_mode",
                sa.String(length=16),
                nullable=False,
                server_default="default",
                comment="模型思考模式：default/enabled/disabled",
            ),
        )


def downgrade() -> None:
    if _column_exists("content_prompt_debug_history", "thinking_mode"):
        op.drop_column("content_prompt_debug_history", "thinking_mode")
