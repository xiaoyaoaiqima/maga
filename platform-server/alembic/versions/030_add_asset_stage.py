"""add asset stage to asset registry

Revision ID: 030_add_asset_stage
Revises: 029_add_content_feedback_table
Create Date: 2026-05-13

"""
from alembic import op
import sqlalchemy as sa


revision = "030_add_asset_stage"
down_revision = "029_add_content_feedback_table"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return column_name in [column["name"] for column in inspector.get_columns(table_name)]


def _index_exists(table_name: str, index_name: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return index_name in [idx["name"] for idx in inspector.get_indexes(table_name)]


def upgrade() -> None:
    if not _table_exists("asset_registry"):
        return

    if not _column_exists("asset_registry", "asset_stage"):
        op.add_column(
            "asset_registry",
            sa.Column(
                "asset_stage",
                sa.String(32),
                nullable=False,
                server_default="production",
                comment="资产阶段：production/candidate",
            ),
        )

    if not _index_exists("asset_registry", "idx_asset_registry_asset_stage"):
        op.create_index("idx_asset_registry_asset_stage", "asset_registry", ["asset_stage"])


def downgrade() -> None:
    if not _table_exists("asset_registry"):
        return

    if _index_exists("asset_registry", "idx_asset_registry_asset_stage"):
        op.drop_index("idx_asset_registry_asset_stage", table_name="asset_registry")
    if _column_exists("asset_registry", "asset_stage"):
        op.drop_column("asset_registry", "asset_stage")
