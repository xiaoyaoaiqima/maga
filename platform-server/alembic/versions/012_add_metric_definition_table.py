"""add_metric_definition_table

Revision ID: 012
Revises: 011
Create Date: 2025-12-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '012'
down_revision: Union[str, None] = '011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create metric_definition table
    op.create_table(
        'metric_definition',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='Primary Key'),
        sa.Column('metric_key', sa.String(length=128), nullable=False, comment='指标 Key (对应代码/SQL中的标识)'),
        sa.Column('metric_name', sa.String(length=255), nullable=False, comment='指标名称 (中文)'),
        sa.Column('description', sa.Text(), nullable=True, comment='指标定义/解释说明'),
        sa.Column('category', sa.String(length=64), nullable=True, comment='指标分类 (Dashboard, Cost, GE, AG, RLHF等)'),
        sa.Column('unit', sa.String(length=32), nullable=True, comment='单位 (e.g. %, $, ms, 个)'),
        sa.Column('display_format', sa.String(length=64), nullable=True, comment='显示格式 (number, currency, percentage)'),
        sa.Column('display_order', sa.Integer(), nullable=False, default=0, comment='显示排序权重'),
        sa.Column('create_time', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='创建时间'),
        sa.Column('update_time', sa.DateTime(), server_default=sa.text('now()'), nullable=True, comment='更新时间'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index(op.f('ix_metric_definition_metric_key'), 'metric_definition', ['metric_key'], unique=True)
    op.create_index(op.f('ix_metric_definition_category'), 'metric_definition', ['category'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index(op.f('ix_metric_definition_category'), table_name='metric_definition')
    op.drop_index(op.f('ix_metric_definition_metric_key'), table_name='metric_definition')
    
    # Drop table
    op.drop_table('metric_definition')

