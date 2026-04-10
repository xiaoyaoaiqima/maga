"""add config_snapshot update_time

Revision ID: 009
Revises: 008
Create Date: 2025-12-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '009'
down_revision: Union[str, None] = '008_expert_total_output'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add update_time column
    op.add_column('config_snapshot', sa.Column('update_time', sa.DateTime(), server_default=sa.func.now(), nullable=True, comment='更新时间'))
    
    # Add updated_by column
    op.add_column('config_snapshot', sa.Column('updated_by', sa.String(64), nullable=True, comment='更新人'))
    
    # Add remark column
    op.add_column('config_snapshot', sa.Column('remark', sa.Text(), nullable=True, comment='备注'))


def downgrade() -> None:
    op.drop_column('config_snapshot', 'remark')
    op.drop_column('config_snapshot', 'updated_by')
    op.drop_column('config_snapshot', 'update_time')
