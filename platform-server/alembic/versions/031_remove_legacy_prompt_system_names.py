"""remove legacy prompt system names

Revision ID: 031_remove_legacy_prompt_system_names
Revises: 030_add_asset_stage
Create Date: 2026-05-14

"""
from alembic import op
import sqlalchemy as sa


revision = "031_remove_legacy_prompt_system_names"
down_revision = "030_add_asset_stage"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("prompt_asset") or not _table_exists("prompt_version"):
        return

    op.execute(
        sa.text(
            """
            DELETE FROM prompt_evaluation
            WHERE prompt_id IN (
                SELECT id
                FROM prompt_asset
                WHERE name = 'xhs_writer.ge.soul'
                   OR name LIKE 'xhs_writer.ae.%.persona'
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM prompt_optimizer_run
            WHERE prompt_id IN (
                SELECT id
                FROM prompt_asset
                WHERE name = 'xhs_writer.ge.soul'
                   OR name LIKE 'xhs_writer.ae.%.persona'
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM prompt_issue
            WHERE prompt_id IN (
                SELECT id
                FROM prompt_asset
                WHERE name = 'xhs_writer.ge.soul'
                   OR name LIKE 'xhs_writer.ae.%.persona'
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM prompt_version
            WHERE prompt_id IN (
                SELECT id
                FROM prompt_asset
                WHERE name = 'xhs_writer.ge.soul'
                   OR name LIKE 'xhs_writer.ae.%.persona'
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM prompt_asset
            WHERE name = 'xhs_writer.ge.soul'
               OR name LIKE 'xhs_writer.ae.%.persona'
            """
        )
    )


def downgrade() -> None:
    # Legacy SOUL/persona prompt rows are intentionally not recreated.
    pass
