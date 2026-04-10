"""add is_deleted to message_recipient

Revision ID: 022_msg_recipient_del
Revises: 021_add_message_tables
Create Date: 2025-12-21

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
# 注意：alembic_version.version_num 在集群里是 varchar(32)，这里必须 <= 32 字符
revision: str = "022_msg_recipient_del"
down_revision: Union[str, None] = "021_add_message_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("message_recipient")}
    if "is_deleted" in cols:
        return

    op.add_column(
        "message_recipient",
        sa.Column(
            "is_deleted",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="是否删除（0否 1是）",
        ),
    )
    op.create_index(
        "ix_message_recipient_is_deleted",
        "message_recipient",
        ["is_deleted"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("message_recipient")}
    if "is_deleted" not in cols:
        return

    op.drop_index("ix_message_recipient_is_deleted", table_name="message_recipient")
    op.drop_column("message_recipient", "is_deleted")


