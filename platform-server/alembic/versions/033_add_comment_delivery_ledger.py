"""add comment delivery ledger

Revision ID: 033_add_comment_delivery_ledger
Revises: 032_merge_business_logic_ae_assets
Create Date: 2026-06-13

"""
from alembic import op
import sqlalchemy as sa


revision = "033_add_comment_delivery_ledger"
down_revision = "032_merge_business_logic_ae_assets"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return index_name in [idx["name"] for idx in inspector.get_indexes(table_name)]


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if _table_exists(table_name) and not _index_exists(table_name, index_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    if not _table_exists("comment_delivery_ledger"):
        op.create_table(
            "comment_delivery_ledger",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("asset_key", sa.String(128), nullable=False, comment="资产键"),
            sa.Column("category", sa.String(255), nullable=True, comment="评论分类"),
            sa.Column("comment_text", sa.Text(), nullable=False, comment="原始评论内容"),
            sa.Column("normalized_comment", sa.Text(), nullable=False, comment="归一化评论内容"),
            sa.Column("comment_hash", sa.String(64), nullable=False, comment="归一化评论 sha256"),
            sa.Column("source_type", sa.String(32), nullable=False, comment="来源类型"),
            sa.Column("source_uri", sa.Text(), nullable=True, comment="来源 URI"),
            sa.Column("batch_id", sa.BigInteger(), nullable=True, comment="批次ID"),
            sa.Column("item_id", sa.BigInteger(), nullable=True, comment="批次文章ID"),
            sa.Column("delivered_by", sa.String(100), nullable=True, comment="交付人"),
            sa.Column("delivered_at", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="交付时间"),
            sa.Column("metadata_json", sa.JSON(), nullable=True, comment="扩展数据"),
            sa.Column("create_time", sa.DateTime(), nullable=True, server_default=sa.func.now(), comment="创建时间"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("asset_key", "comment_hash", name="uq_comment_delivery_ledger_asset_hash"),
        )
    for index_name, columns in (
        ("idx_comment_delivery_ledger_asset_key", ["asset_key"]),
        ("idx_comment_delivery_ledger_comment_hash", ["comment_hash"]),
        ("idx_comment_delivery_ledger_source_type", ["source_type"]),
        ("idx_comment_delivery_ledger_batch_id", ["batch_id"]),
        ("idx_comment_delivery_ledger_item_id", ["item_id"]),
        ("idx_comment_delivery_ledger_delivered_by", ["delivered_by"]),
    ):
        _create_index_if_missing(index_name, "comment_delivery_ledger", columns)


def downgrade() -> None:
    for index_name in (
        "idx_comment_delivery_ledger_delivered_by",
        "idx_comment_delivery_ledger_item_id",
        "idx_comment_delivery_ledger_batch_id",
        "idx_comment_delivery_ledger_source_type",
        "idx_comment_delivery_ledger_comment_hash",
        "idx_comment_delivery_ledger_asset_key",
    ):
        if _table_exists("comment_delivery_ledger") and _index_exists("comment_delivery_ledger", index_name):
            op.drop_index(index_name, table_name="comment_delivery_ledger")
    if _table_exists("comment_delivery_ledger"):
        op.drop_table("comment_delivery_ledger")
