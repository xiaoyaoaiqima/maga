"""merge multiple heads

Revision ID: 4d55483af7d9
Revises: 024_inspection_data, 20251217_add_expert_debug_batch_task
Create Date: 2025-12-23 00:22:23.047159

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d55483af7d9'
down_revision: Union[str, None] = ('025_add_rlhf_review_user_fields', '20251217_debug_batch')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

