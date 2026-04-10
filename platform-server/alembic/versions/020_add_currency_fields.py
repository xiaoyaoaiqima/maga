"""add currency fields

Revision ID: 020
Revises: 019
Create Date: 2025-12-18

为费用统计相关表增加币种字段：
- llm_model_route: 增加 currency 字段
- expert_call_trace: 增加 currency 字段
- trace_daily_stats: 增加 currency 字段并更新唯一约束
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '020_add_currency_fields'
down_revision: Union[str, None] = '019_create_graph_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. llm_model_route 增加 currency 字段
    op.add_column('llm_model_route', sa.Column('currency', sa.String(length=10), nullable=False, server_default='USD', comment='计价币种（USD/CNY）'))
    
    # 2. expert_call_trace 增加 currency 字段
    op.add_column('expert_call_trace', sa.Column('currency', sa.String(length=10), nullable=True, comment='计价币种（USD/CNY）'))
    
    # 3. trace_daily_stats 增加 currency 字段
    op.add_column('trace_daily_stats', sa.Column('currency', sa.String(length=10), nullable=False, server_default='USD', comment='计价币种（USD/CNY）'))
    
    # 4. 更新 trace_daily_stats 唯一约束
    # 注意：之前的约束名可能是 uk_date_stage_expert_exp (来自 003) 或 uk_date_stage_expert_exp_provider (如果后续手动改过)
    # 我们先尝试删除已知的两个可能名字
    try:
        op.drop_constraint('uk_date_stage_expert_exp_provider', 'trace_daily_stats', type_='unique')
    except Exception:
        pass
        
    try:
        op.drop_constraint('uk_date_stage_expert_exp', 'trace_daily_stats', type_='unique')
    except Exception:
        pass
        
    op.create_unique_constraint(
        'uk_date_stage_expert_exp_provider_currency',
        'trace_daily_stats',
        ['stat_date', 'stage', 'expert_config_code', 'experiment_id', 'experiment_group', 'provider_code', 'currency']
    )


def downgrade() -> None:
    # 1. 恢复 trace_daily_stats 唯一约束
    op.drop_constraint('uk_date_stage_expert_exp_provider_currency', 'trace_daily_stats', type_='unique')
    op.create_unique_constraint(
        'uk_date_stage_expert_exp_provider',
        'trace_daily_stats',
        ['stat_date', 'stage', 'expert_config_code', 'experiment_id', 'experiment_group', 'provider_code']
    )
    
    # 2. 删除 currency 字段
    op.drop_column('trace_daily_stats', 'currency')
    op.drop_column('expert_call_trace', 'currency')
    op.drop_column('llm_model_route', 'currency')

