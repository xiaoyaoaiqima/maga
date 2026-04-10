"""Add rlhf annotations

Revision ID: 023_rlhf_annotations
Revises: 022
Create Date: 2025-12-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '023_rlhf_annotations'
down_revision = '022_msg_recipient_del'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('rlhf_feedback', sa.Column('annotations', sa.JSON(), nullable=True, comment='划词评论列表'))


def downgrade() -> None:
    op.drop_column('rlhf_feedback', 'annotations')

