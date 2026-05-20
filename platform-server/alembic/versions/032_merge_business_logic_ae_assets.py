"""merge business logic ae assets

Revision ID: 032_merge_business_logic_ae_assets
Revises: 031_remove_legacy_prompt_system_names
Create Date: 2026-05-14

"""
from alembic import op
import sqlalchemy as sa


revision = "032_merge_business_logic_ae_assets"
down_revision = "031_remove_legacy_prompt_system_names"
branch_labels = None
depends_on = None


ACTIVE_AE_CODES = ("brand_product_guard", "business_logic", "compliance_redline")


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()


def _active_asset_filter() -> str:
    return ", ".join(f"'{code}'" for code in ACTIVE_AE_CODES)


def upgrade() -> None:
    if _table_exists("prompt_asset") and _table_exists("prompt_version"):
        for table_name in ("prompt_evaluation", "prompt_optimizer_run", "prompt_issue", "prompt_version"):
            if not _table_exists(table_name):
                continue
            op.execute(
                sa.text(
                    f"""
                    DELETE FROM {table_name}
                    WHERE prompt_id IN (
                        SELECT id
                        FROM prompt_asset
                        WHERE name LIKE 'xhs_writer.ae.%'
                          AND name NOT LIKE 'xhs_writer.ae.brand_product_guard.%'
                          AND name NOT LIKE 'xhs_writer.ae.business_logic.%'
                          AND name NOT LIKE 'xhs_writer.ae.compliance_redline.%'
                    )
                    """
                )
            )
        op.execute(
            sa.text(
                """
                DELETE FROM prompt_asset
                WHERE name LIKE 'xhs_writer.ae.%'
                  AND name NOT LIKE 'xhs_writer.ae.brand_product_guard.%'
                  AND name NOT LIKE 'xhs_writer.ae.business_logic.%'
                  AND name NOT LIKE 'xhs_writer.ae.compliance_redline.%'
                """
            )
        )

    if _table_exists("asset_registry"):
        asset_keys = _active_asset_filter()
        op.execute(
            sa.text(
                f"""
                UPDATE asset_registry
                SET status = 'archived'
                WHERE asset_type = 'expert_corpus'
                  AND asset_key NOT IN ({asset_keys})
                  AND status = 'active'
                """
            )
        )


def downgrade() -> None:
    # Split business AE prompt/corpus assets are intentionally not restored.
    pass
