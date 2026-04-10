"""
创建 nodes 和 edges 图数据表

Revision ID: 019_create_graph_tables
Revises: 018_add_critic_score_expert_type
Create Date: 2024-12-17
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '019_create_graph_tables'
down_revision = '018_expert_type'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建 nodes 表
    op.create_table(
        'nodes',
        sa.Column('id', sa.BigInteger, primary_key=True, comment='节点唯一ID (雪花ID)'),
        sa.Column('tenant_id', sa.String(64), nullable=False, server_default='default', comment='租户/品牌ID'),
        sa.Column('label', sa.String(50), nullable=False, comment='节点类型'),
        sa.Column('name', sa.String(255), nullable=False, comment='节点值'),
        sa.Column('description', sa.String(500), nullable=True, comment='节点描述'),
        sa.Column('ai_instruction', sa.JSON, nullable=True, comment='AI 指令'),
        sa.Column('properties', sa.JSON, nullable=True, comment='扩展数据'),
        sa.Column('is_active', sa.Integer, nullable=False, server_default='1', comment='状态: 0-禁用 1-启用'),
        sa.Column('is_deleted', sa.Integer, nullable=False, server_default='0', comment='软删除'),
        sa.Column('created_by', sa.String(64), nullable=True, comment='创建人ID'),
        sa.Column('updated_by', sa.String(64), nullable=True, comment='最后修改人ID'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now(), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now(), comment='更新时间'),
    )
    
    # nodes 表索引
    op.create_index('idx_tenant', 'nodes', ['tenant_id'])
    op.create_index('idx_label', 'nodes', ['label'])
    op.create_index('idx_tenant_label', 'nodes', ['tenant_id', 'label'])
    op.create_index('idx_status', 'nodes', ['is_active'])
    op.create_index('idx_name', 'nodes', ['name'])
    op.create_index('uk_tenant_label_name', 'nodes', ['tenant_id', 'label', 'name', 'is_active', 'is_deleted'], unique=True)
    
    # 创建 edges 表
    op.create_table(
        'edges',
        sa.Column('id', sa.BigInteger, primary_key=True, comment='边唯一ID (雪花ID)'),
        sa.Column('tenant_id', sa.String(64), nullable=False, server_default='default', comment='租户/品牌ID'),
        sa.Column('source_node_id', sa.BigInteger, nullable=False, comment='起点节点ID'),
        sa.Column('target_node_id', sa.BigInteger, nullable=False, comment='终点节点ID'),
        sa.Column('relation_type', sa.String(50), nullable=False, comment='关系类型'),
        sa.Column('explanation', sa.String(255), nullable=True, comment='关系描述'),
        sa.Column('meta_data', sa.JSON, nullable=True, comment='扩展约束 (weight, priority 等)'),
        sa.Column('is_active', sa.Integer, nullable=False, server_default='1', comment='状态: 0-禁用 1-启用'),
        sa.Column('is_deleted', sa.Integer, nullable=False, server_default='0', comment='软删除'),
        sa.Column('created_by', sa.String(64), nullable=True, comment='创建人ID'),
        sa.Column('updated_by', sa.String(64), nullable=True, comment='最后修改人ID'),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now(), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.func.now(), onupdate=sa.func.now(), comment='更新时间'),
    )
    
    # edges 表索引
    op.create_index('uk_edge', 'edges', ['tenant_id', 'source_node_id', 'target_node_id', 'relation_type', 'is_active', 'is_deleted'], unique=True)
    op.create_index('idx_edge_tenant', 'edges', ['tenant_id'])
    op.create_index('idx_source', 'edges', ['source_node_id'])
    op.create_index('idx_target', 'edges', ['target_node_id'])
    op.create_index('idx_relation', 'edges', ['relation_type'])
    op.create_index('idx_source_relation', 'edges', ['source_node_id', 'relation_type'])
    op.create_index('idx_tenant_source_relation', 'edges', ['tenant_id', 'source_node_id', 'relation_type'])


def downgrade() -> None:
    op.drop_table('edges')
    op.drop_table('nodes')
