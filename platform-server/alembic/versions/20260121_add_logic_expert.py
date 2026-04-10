"""add logic_expert table

Revision ID: 20260121_add_logic_expert
Revises: 20251224_add_admin_tools_task
Create Date: 2026-01-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260121_add_logic_expert"
down_revision: Union[str, Sequence[str], None] = "20251224_add_admin_tools_task"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_NAME = "logic_expert"

SEED_ROWS = (
    {
        "expert_group": "活人真实感评分专家组",
        "expert_name": "拟人化真实感专家",
        "expert_type": "CRITIC",
        "expert_app": "raap-service-ag",
        "expert_service": "critic.CriticService",
        "expert_func": "CriticPersonaAuth",
        "description": "评估内容是否符合预设的人物设定",
    },
    {
        "expert_group": "内容丰富度专家组",
        "expert_name": "文章优雅度专家",
        "expert_type": "CRITIC",
        "expert_app": "raap-service-ag",
        "expert_service": "critic.CriticService",
        "expert_func": "CriticGrace",
        "description": "评估内容的语法规范性、用词准确性和表达流畅度、完整性、逻辑性和可读性",
    },
    {
        "expert_group": "内容丰富度专家组",
        "expert_name": "创造力评分专家",
        "expert_type": "CRITIC",
        "expert_app": "raap-service-ag",
        "expert_service": "critic.CriticService",
        "expert_func": "CriticCreativity",
        "description": "评估内容的原创性、新颖度和吸引力",
    },
    {
        "expert_group": "内容丰富度专家组",
        "expert_name": "品牌调性匹配专家",
        "expert_type": "CRITIC",
        "expert_app": "raap-service-ag",
        "expert_service": "critic.CriticService",
        "expert_func": "CriticBrandAlign",
        "description": "评估内容是否与品牌形象、价值观保持一致",
    },
    {
        "expert_group": "内容丰富度专家组",
        "expert_name": "平台适应度专家",
        "expert_type": "CRITIC",
        "expert_app": "raap-service-ag",
        "expert_service": "critic.CriticService",
        "expert_func": "CriticMarket",
        "description": "评估内容是否符合目标平台的调性、风格和用户习惯",
    },
)


def _ensure_indexes(inspector: sa.Inspector) -> None:
    existing_indexes = {ix.get("name") for ix in inspector.get_indexes(TABLE_NAME)}
    if "idx_logic_expert_type" not in existing_indexes:
        op.create_index("idx_logic_expert_type", TABLE_NAME, ["expert_type"])
    if "idx_logic_expert_func" not in existing_indexes:
        op.create_index("idx_logic_expert_func", TABLE_NAME, ["expert_func"])
    if "idx_logic_expert_enabled" not in existing_indexes:
        op.create_index("idx_logic_expert_enabled", TABLE_NAME, ["enabled"])
    if "idx_logic_expert_deleted" not in existing_indexes:
        op.create_index("idx_logic_expert_deleted", TABLE_NAME, ["is_deleted"])


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if TABLE_NAME not in tables:
        op.create_table(
            TABLE_NAME,
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, comment="主键"),
            sa.Column("expert_group", sa.String(128), nullable=False, comment="专家组名称"),
            sa.Column("expert_name", sa.String(128), nullable=False, comment="专家名称"),
            sa.Column("expert_type", sa.String(32), nullable=False, comment="专家类型（CRITIC/BAN/REWRITE等）"),
            sa.Column("expert_app", sa.String(128), nullable=False, comment="专家所属 App（Dapr app id）"),
            sa.Column("expert_service", sa.String(128), nullable=False, comment="专家服务名称"),
            sa.Column("expert_func", sa.String(128), nullable=False, comment="专家函数名"),
            sa.Column("description", sa.Text(), nullable=True, comment="专家说明"),
            sa.Column("enabled", sa.Integer(), nullable=False, server_default="1", comment="是否启用(1/0)"),
            sa.Column("is_deleted", sa.Integer(), nullable=False, server_default="0", comment="软删(1/0)"),
            sa.Column("create_time", sa.DateTime(), server_default=sa.func.now(), nullable=True, comment="创建时间"),
            sa.Column(
                "update_time",
                sa.DateTime(),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=True,
                comment="更新时间",
            ),
            sa.Column("created_by", sa.String(64), nullable=True, comment="创建人"),
            sa.Column("updated_by", sa.String(64), nullable=True, comment="更新人"),
            sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
            sa.UniqueConstraint("expert_type", "expert_func", name="uq_logic_expert_type_func"),
            comment="逻辑专家配置表",
        )
        _ensure_indexes(inspector)
    else:
        _ensure_indexes(inspector)

    insert_sql = f"""
    INSERT INTO {TABLE_NAME} (
        expert_group, expert_name, expert_type, expert_app, expert_service, expert_func,
        description, enabled, is_deleted, create_time, update_time, created_by, updated_by, remark
    ) VALUES (
        :expert_group, :expert_name, :expert_type, :expert_app, :expert_service, :expert_func,
        :description, 1, 0, NOW(), NOW(), :created_by, :updated_by, :remark
    )
    ON DUPLICATE KEY UPDATE
        expert_group=VALUES(expert_group),
        expert_name=VALUES(expert_name),
        expert_app=VALUES(expert_app),
        expert_service=VALUES(expert_service),
        description=VALUES(description),
        enabled=VALUES(enabled),
        is_deleted=VALUES(is_deleted),
        updated_by=VALUES(updated_by),
        remark=VALUES(remark),
        update_time=NOW()
    """
    for seed in SEED_ROWS:
        payload = dict(seed)
        payload.update({"created_by": None, "updated_by": None, "remark": None})
        conn.execute(sa.text(insert_sql), payload)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if TABLE_NAME in inspector.get_table_names():
        op.drop_table(TABLE_NAME)
