"""add_tenant_ak_sk

Revision ID: 011
Revises: 010
Create Date: 2025-12-14 03:01:53.186616

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '011'
down_revision: Union[str, None] = '010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add access_key and secret_key columns to tenant table
    op.add_column('tenant', sa.Column('access_key', sa.String(length=64), nullable=True, comment='Access Key (AK)'))
    op.add_column('tenant', sa.Column('secret_key', sa.String(length=128), nullable=True, comment='Secret Key (SK)'))
    
    # Create indexes for access_key
    op.create_index(op.f('ix_tenant_access_key'), 'tenant', ['access_key'], unique=True)


def downgrade() -> None:
    # Drop index
    op.drop_index(op.f('ix_tenant_access_key'), table_name='tenant')
    
    # Drop columns
    op.drop_column('tenant', 'secret_key')
    op.drop_column('tenant', 'access_key')
