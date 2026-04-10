"""add llm provider tables

Revision ID: 004
Revises: 003
Create Date: 2025-12-08

创建 LLM Provider 配置管理相关表：
- llm_provider_config: LLM 提供商配置表
- llm_model_route: 模型路由表（支持 failover）
- llm_circuit_breaker: 熔断状态表
- job_business_context: Job 业务上下文关联表

扩展已有表：
- expert_call_trace: 新增 provider_code, cost, failover 字段
- trace_daily_stats: 新增 cost 统计字段
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 LLM Provider 配置管理相关表"""
    
    # ============ 创建 llm_provider_config 表 ============
    op.create_table(
        'llm_provider_config',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('provider_code', sa.String(64), nullable=False, unique=True, comment='提供商编码（唯一标识）'),
        sa.Column('provider_name', sa.String(128), nullable=False, comment='提供商名称'),
        sa.Column('provider_type', sa.String(32), nullable=False, default='openai_compatible', 
                  comment='类型：openai_compatible/gemini_native/azure'),
        sa.Column('base_url', sa.String(512), nullable=False, comment='API 端点地址'),
        sa.Column('api_key', sa.String(512), nullable=True, comment='API Key（Vault 模式存占位符，DB 模式存密文）'),
        sa.Column('api_key_encrypted', sa.SmallInteger(), nullable=False, default=0, 
                  comment='是否已加密（0=明文/占位符，1=已加密）'),
        sa.Column('default_model', sa.String(128), nullable=True, comment='默认模型'),
        sa.Column('available_models', sa.JSON(), nullable=True, comment='可用模型列表'),
        sa.Column('default_params', sa.JSON(), nullable=True, 
                  comment='默认参数（temperature/max_tokens/top_p）'),
        sa.Column('rate_limit', sa.JSON(), nullable=True, comment='速率限制配置'),
        sa.Column('timeout', sa.Integer(), nullable=False, default=120, comment='超时时间（秒）'),
        sa.Column('priority', sa.Integer(), nullable=False, default=0, comment='优先级（越大越优先）'),
        sa.Column('enabled', sa.SmallInteger(), nullable=False, default=1, comment='是否启用'),
        sa.Column('description', sa.Text(), nullable=True, comment='描述'),
        sa.Column('create_time', sa.DateTime(), server_default=sa.func.now(), nullable=True, comment='创建时间'),
        sa.Column('update_time', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), 
                  nullable=True, comment='更新时间'),
        sa.Column('is_deleted', sa.BigInteger(), nullable=True, default=0, comment='软删除标记'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # llm_provider_config 索引
    op.create_index('idx_provider_code', 'llm_provider_config', ['provider_code'])
    op.create_index('idx_provider_enabled', 'llm_provider_config', ['enabled', 'priority'])
    op.create_index('idx_provider_type', 'llm_provider_config', ['provider_type'])
    
    # ============ 创建 llm_model_route 表 ============
    op.create_table(
        'llm_model_route',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('model_code', sa.String(64), nullable=False, comment='统一模型编码（业务使用）'),
        sa.Column('model_name', sa.String(128), nullable=False, comment='模型显示名称'),
        sa.Column('provider_code', sa.String(64), nullable=False, comment='端点编码（关联 llm_provider_config）'),
        sa.Column('provider_model', sa.String(128), nullable=False, comment='该端点的实际模型名'),
        sa.Column('priority', sa.Integer(), nullable=False, default=0, comment='优先级（越大越优先，用于 failover）'),
        sa.Column('enabled', sa.SmallInteger(), nullable=False, default=1, comment='是否启用'),
        sa.Column('max_context_length', sa.Integer(), nullable=True, comment='最大上下文长度'),
        sa.Column('features', sa.JSON(), nullable=True, comment='支持的功能（vision/function_calling/json_mode）'),
        sa.Column('cost_per_1k_input', sa.DECIMAL(10, 6), nullable=True, comment='输入成本（每 1K tokens，美元）'),
        sa.Column('cost_per_1k_output', sa.DECIMAL(10, 6), nullable=True, comment='输出成本（每 1K tokens，美元）'),
        sa.Column('timeout_seconds', sa.Integer(), nullable=True, comment='超时时间（秒）'),
        sa.Column('description', sa.Text(), nullable=True, comment='描述'),
        sa.Column('create_time', sa.DateTime(), server_default=sa.func.now(), nullable=True, comment='创建时间'),
        sa.Column('update_time', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), 
                  nullable=True, comment='更新时间'),
        sa.Column('is_deleted', sa.BigInteger(), nullable=True, default=0, comment='软删除标记'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('model_code', 'provider_code', 'is_deleted', name='uk_model_provider_deleted')
    )
    
    # llm_model_route 索引
    op.create_index('idx_route_model_code', 'llm_model_route', ['model_code'])
    op.create_index('idx_route_provider_code', 'llm_model_route', ['provider_code'])
    op.create_index('idx_route_model_priority', 'llm_model_route', ['model_code', 'priority'])
    op.create_index('idx_route_enabled', 'llm_model_route', ['enabled'])
    
    # ============ 创建 llm_circuit_breaker 表 ============
    op.create_table(
        'llm_circuit_breaker',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('provider_code', sa.String(64), nullable=False, unique=True, comment='端点编码'),
        sa.Column('state', sa.String(16), nullable=False, default='closed', 
                  comment='状态：closed/open/half_open'),
        sa.Column('failure_count', sa.Integer(), nullable=False, default=0, comment='连续失败次数'),
        sa.Column('success_count', sa.Integer(), nullable=False, default=0, comment='半开状态下成功次数'),
        sa.Column('last_failure_time', sa.DateTime(), nullable=True, comment='最后失败时间'),
        sa.Column('last_failure_reason', sa.String(256), nullable=True, comment='最后失败原因'),
        sa.Column('open_until', sa.DateTime(), nullable=True, comment='熔断截止时间'),
        sa.Column('update_time', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), 
                  nullable=True, comment='更新时间'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # llm_circuit_breaker 索引
    op.create_index('idx_breaker_provider', 'llm_circuit_breaker', ['provider_code'])
    op.create_index('idx_breaker_state', 'llm_circuit_breaker', ['state'])
    
    # ============ 创建 job_business_context 表 ============
    op.create_table(
        'job_business_context',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('job_id', sa.String(64), nullable=False, unique=True, comment='关联 job.job_id'),
        sa.Column('platform_code', sa.String(64), nullable=True, comment='平台编码'),
        sa.Column('brand_id', sa.BigInteger(), nullable=True, comment='品牌 ID'),
        sa.Column('campaign_id', sa.BigInteger(), nullable=True, comment='活动 ID'),
        sa.Column('extra_context', sa.JSON(), nullable=True, comment='扩展业务上下文'),
        sa.Column('create_time', sa.DateTime(), server_default=sa.func.now(), nullable=True, comment='创建时间'),
        sa.Column('update_time', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), 
                  nullable=True, comment='更新时间'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # job_business_context 索引
    op.create_index('idx_context_job_id', 'job_business_context', ['job_id'])
    op.create_index('idx_context_platform', 'job_business_context', ['platform_code'])
    op.create_index('idx_context_brand', 'job_business_context', ['brand_id'])
    op.create_index('idx_context_campaign', 'job_business_context', ['campaign_id'])
    
    # ============ 扩展 expert_call_trace 表 ============
    # 新增 provider_code 字段
    op.add_column('expert_call_trace', 
                  sa.Column('provider_code', sa.String(64), nullable=True, 
                           comment='LLM Provider 编码'))
    
    # 新增成本字段
    op.add_column('expert_call_trace',
                  sa.Column('input_cost', sa.DECIMAL(10, 6), nullable=True,
                           comment='输入成本（美元）'))
    op.add_column('expert_call_trace',
                  sa.Column('output_cost', sa.DECIMAL(10, 6), nullable=True,
                           comment='输出成本（美元）'))
    op.add_column('expert_call_trace',
                  sa.Column('total_cost', sa.DECIMAL(10, 6), nullable=True,
                           comment='总成本（美元）'))
    
    # 新增 failover 字段
    op.add_column('expert_call_trace',
                  sa.Column('failover_count', sa.Integer(), nullable=True, default=0,
                           comment='failover 次数'))
    
    # 新增索引
    op.create_index('idx_trace_provider', 'expert_call_trace', ['provider_code', 'created_at'])
    op.create_index('idx_trace_cost', 'expert_call_trace', ['total_cost', 'created_at'])
    
    # ============ 扩展 trace_daily_stats 表 ============
    # 新增 provider_code 字段
    op.add_column('trace_daily_stats',
                  sa.Column('provider_code', sa.String(64), nullable=True,
                           comment='LLM Provider 编码'))
    
    # 新增成本统计字段
    op.add_column('trace_daily_stats',
                  sa.Column('total_cost', sa.DECIMAL(10, 4), nullable=True,
                           comment='总成本'))
    op.add_column('trace_daily_stats',
                  sa.Column('avg_cost', sa.DECIMAL(10, 4), nullable=True,
                           comment='平均成本'))
    
    # 新增索引
    op.create_index('idx_stats_provider', 'trace_daily_stats', ['provider_code'])


def downgrade() -> None:
    """删除 LLM Provider 配置管理相关表"""
    
    # ============ 回滚 trace_daily_stats 扩展 ============
    op.drop_index('idx_stats_provider', table_name='trace_daily_stats')
    op.drop_column('trace_daily_stats', 'avg_cost')
    op.drop_column('trace_daily_stats', 'total_cost')
    op.drop_column('trace_daily_stats', 'provider_code')
    
    # ============ 回滚 expert_call_trace 扩展 ============
    op.drop_index('idx_trace_cost', table_name='expert_call_trace')
    op.drop_index('idx_trace_provider', table_name='expert_call_trace')
    op.drop_column('expert_call_trace', 'failover_count')
    op.drop_column('expert_call_trace', 'total_cost')
    op.drop_column('expert_call_trace', 'output_cost')
    op.drop_column('expert_call_trace', 'input_cost')
    op.drop_column('expert_call_trace', 'provider_code')
    
    # ============ 删除 job_business_context ============
    op.drop_index('idx_context_campaign', table_name='job_business_context')
    op.drop_index('idx_context_brand', table_name='job_business_context')
    op.drop_index('idx_context_platform', table_name='job_business_context')
    op.drop_index('idx_context_job_id', table_name='job_business_context')
    op.drop_table('job_business_context')
    
    # ============ 删除 llm_circuit_breaker ============
    op.drop_index('idx_breaker_state', table_name='llm_circuit_breaker')
    op.drop_index('idx_breaker_provider', table_name='llm_circuit_breaker')
    op.drop_table('llm_circuit_breaker')
    
    # ============ 删除 llm_model_route ============
    op.drop_index('idx_route_enabled', table_name='llm_model_route')
    op.drop_index('idx_route_model_priority', table_name='llm_model_route')
    op.drop_index('idx_route_provider_code', table_name='llm_model_route')
    op.drop_index('idx_route_model_code', table_name='llm_model_route')
    op.drop_table('llm_model_route')
    
    # ============ 删除 llm_provider_config ============
    op.drop_index('idx_provider_type', table_name='llm_provider_config')
    op.drop_index('idx_provider_enabled', table_name='llm_provider_config')
    op.drop_index('idx_provider_code', table_name='llm_provider_config')
    op.drop_table('llm_provider_config')

