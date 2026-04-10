"""Add test_set table and modify test_case table

Revision ID: 026_add_test_set_table
Revises: 4d55483af7d9
Create Date: 2024-12-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "026_add_test_set_table"
down_revision = "4d55483af7d9"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    """检查表是否存在"""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    """检查列是否存在"""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns(table_name)]
    return column_name in columns


def _index_exists(table_name: str, index_name: str) -> bool:
    """检查索引是否存在"""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    indexes = [i['name'] for i in inspector.get_indexes(table_name)]
    return index_name in indexes


def upgrade() -> None:
    # 1. 创建 test_set 表
    if not _table_exists("test_set"):
        op.create_table(
            "test_set",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
            sa.Column("code", sa.String(64), nullable=False, comment="唯一编码"),
            sa.Column("name", sa.String(128), nullable=False, comment="测试集名称"),
            sa.Column("type", sa.String(16), nullable=False, server_default="text", comment="类型: text/image"),
            sa.Column("description", sa.String(500), nullable=True, comment="描述"),
            sa.Column("enabled", sa.Integer(), nullable=False, server_default="1", comment="是否启用(1/0)"),
            sa.Column("is_deleted", sa.Integer(), nullable=False, server_default="0", comment="软删除(1/0)"),
            sa.Column("created_by", sa.String(64), nullable=True, comment="创建人"),
            sa.Column("create_time", sa.DateTime(), nullable=False, server_default=sa.func.now(), comment="创建时间"),
            sa.Column("update_time", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now(), comment="更新时间"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code", name="uq_test_set_code"),
        )
    
    # 创建索引
    if not _index_exists("test_set", "idx_test_set_code"):
        op.create_index("idx_test_set_code", "test_set", ["code"])
    if not _index_exists("test_set", "idx_test_set_type"):
        op.create_index("idx_test_set_type", "test_set", ["type"])
    if not _index_exists("test_set", "idx_test_set_enabled"):
        op.create_index("idx_test_set_enabled", "test_set", ["enabled"])

    # 2. 修改 test_case 表
    # 添加 test_set_code 字段（使用 code 关联而非 id）
    if not _column_exists("test_case", "test_set_code"):
        op.add_column(
            "test_case",
            sa.Column("test_set_code", sa.String(64), nullable=True, comment="测试集编码（应用层关联）"),
        )
    
    # 添加 image_url 字段
    if not _column_exists("test_case", "image_url"):
        op.add_column(
            "test_case",
            sa.Column("image_url", sa.String(1024), nullable=True, comment="图片URL（图片类型）"),
        )
    
    # 创建 test_set_code 索引
    if not _index_exists("test_case", "idx_test_case_test_set_code"):
        op.create_index("idx_test_case_test_set_code", "test_case", ["test_set_code"])
    
    # 将 content 字段改为可空（图片类型时 content 可能为空）
    # 注意：alter_column 如果已经是目标状态会安全执行
    op.alter_column(
        "test_case",
        "content",
        existing_type=sa.Text(),
        nullable=True,
    )
    
    # 将 content_md5 字段改为可空
    op.alter_column(
        "test_case",
        "content_md5",
        existing_type=sa.String(32),
        nullable=True,
    )


def downgrade() -> None:
    # 删除 test_case 表的新字段
    op.drop_index("idx_test_case_test_set_code", table_name="test_case")
    op.drop_column("test_case", "image_url")
    op.drop_column("test_case", "test_set_code")
    
    # 恢复 content 字段为非空
    op.alter_column(
        "test_case",
        "content",
        existing_type=sa.Text(),
        nullable=False,
    )
    
    # 恢复 content_md5 字段为非空
    op.alter_column(
        "test_case",
        "content_md5",
        existing_type=sa.String(32),
        nullable=False,
    )
    
    # 删除 test_set 表
    op.drop_index("idx_test_set_enabled", table_name="test_set")
    op.drop_index("idx_test_set_type", table_name="test_set")
    op.drop_index("idx_test_set_code", table_name="test_set")
    op.drop_table("test_set")

