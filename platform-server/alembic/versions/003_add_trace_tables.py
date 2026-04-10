"""add trace tables

Revision ID: 003
Revises: 002
Create Date: 2025-12-07

创建追踪系统相关表：
- expert_call_trace: 统一调用追踪表
- ab_experiment: A/B 实验配置表
- trace_daily_stats: 追踪每日统计表
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建追踪系统相关表"""
    
    # ============ 创建 expert_call_trace 表 ============
    op.create_table(
        'expert_call_trace',
        # 主键
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='技术主键'),
        
        # 三层标识体系
        sa.Column('job_id', sa.String(64), nullable=False, comment='Job ID（任务级）'),
        sa.Column('sub_job_id', sa.String(64), nullable=False, comment='Sub Job ID（执行侧视角）'),
        sa.Column('content_id', sa.String(64), nullable=True, comment='内容ID（内容侧视角，与 sub_job_id 1:1 对等）'),
        sa.Column('trace_id', sa.String(64), nullable=False, comment='请求追踪ID'),
        sa.Column('span_id', sa.String(32), nullable=False, comment='调用ID'),
        sa.Column('parent_span_id', sa.String(32), nullable=True, comment='父调用ID'),
        
        # 调用信息
        sa.Column('stage', sa.String(32), nullable=False, comment='阶段：plugin_render/prompt_render/ge_generation/ag_ban/ag_critic/debug'),
        sa.Column('expert_config_code', sa.String(64), nullable=True, comment='ExpertConfig 编码'),
        sa.Column('expert_type', sa.String(32), nullable=True, comment='Expert 类型'),
        sa.Column('service_app', sa.String(64), nullable=False, comment='目标服务 app-id'),
        sa.Column('service_method', sa.String(64), nullable=False, comment='调用方法'),
        
        # 执行状态
        sa.Column('status', sa.String(16), nullable=False, comment='pending/running/success/failed/timeout'),
        sa.Column('error_type', sa.String(32), nullable=True, comment='错误类型'),
        sa.Column('error_message', sa.Text(), nullable=True, comment='错误信息'),
        
        # 性能指标
        sa.Column('start_time', mysql.DATETIME(fsp=3), nullable=False, comment='开始时间（毫秒精度）'),
        sa.Column('end_time', mysql.DATETIME(fsp=3), nullable=True, comment='结束时间'),
        sa.Column('duration_ms', sa.Integer(), nullable=True, comment='总耗时（毫秒）'),
        sa.Column('queue_time_ms', sa.Integer(), nullable=True, comment='排队时间'),
        sa.Column('model_time_ms', sa.Integer(), nullable=True, comment='模型调用时间'),
        sa.Column('render_time_ms', sa.Integer(), nullable=True, comment='渲染时间'),
        
        # Token 统计
        sa.Column('model_code', sa.String(64), nullable=True, comment='模型编码'),
        sa.Column('model_provider', sa.String(32), nullable=True, comment='模型提供商'),
        sa.Column('input_tokens', sa.Integer(), nullable=False, default=0, comment='输入 Token 数'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, default=0, comment='输出 Token 数'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, default=0, comment='总 Token 数'),
        
        # A/B Test 支持
        sa.Column('experiment_id', sa.String(64), nullable=True, comment='实验ID'),
        sa.Column('experiment_group', sa.String(32), nullable=True, comment='实验分组'),
        sa.Column('experiment_variant', sa.String(64), nullable=True, comment='实验变体'),
        sa.Column('experiment_source', sa.String(16), nullable=True, comment='实验来源'),
        
        # 业务结果
        sa.Column('result_summary', sa.JSON(), nullable=True, comment='结果摘要'),
        sa.Column('plugin_config_snapshot', sa.JSON(), nullable=True, comment='Plugin 配置快照'),
        sa.Column('rendered_prompt', sa.Text(), nullable=True, comment='渲染后的 Prompt'),
        
        # 调用者信息
        sa.Column('caller_service', sa.String(64), nullable=True, comment='调用方服务'),
        sa.Column('caller_user_id', sa.String(64), nullable=True, comment='调用者用户ID'),
        sa.Column('client_ip', sa.String(50), nullable=True, comment='客户端IP'),
        
        # 源数据引用
        sa.Column('source_log_id', sa.String(64), nullable=True, comment='源服务日志ID'),
        sa.Column('source_log_table', sa.String(64), nullable=True, comment='源日志表名'),
        
        # 时间戳
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True, comment='创建时间'),
        
        sa.PrimaryKeyConstraint('id')
    )
    
    # expert_call_trace 索引
    op.create_index('idx_trace_job_id', 'expert_call_trace', ['job_id'])
    op.create_index('idx_trace_job_sub', 'expert_call_trace', ['job_id', 'sub_job_id'])
    op.create_index('idx_trace_sub_job_id', 'expert_call_trace', ['sub_job_id'])
    op.create_index('idx_trace_content_id', 'expert_call_trace', ['content_id'])
    op.create_index('idx_trace_content_stage', 'expert_call_trace', ['content_id', 'stage'])
    op.create_index('idx_trace_trace_id', 'expert_call_trace', ['trace_id'])
    op.create_index('idx_trace_span_parent', 'expert_call_trace', ['span_id', 'parent_span_id'])
    op.create_index('idx_trace_stage_status', 'expert_call_trace', ['stage', 'status'])
    op.create_index('idx_trace_expert_code', 'expert_call_trace', ['expert_config_code'])
    op.create_index('idx_trace_experiment', 'expert_call_trace', ['experiment_id', 'experiment_group'])
    op.create_index('idx_trace_created', 'expert_call_trace', ['created_at'])
    op.create_index('idx_trace_model_created', 'expert_call_trace', ['model_code', 'created_at'])
    
    # ============ 创建 ab_experiment 表 ============
    op.create_table(
        'ab_experiment',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='技术主键'),
        sa.Column('experiment_id', sa.String(64), nullable=False, unique=True, comment='实验ID'),
        sa.Column('experiment_name', sa.String(128), nullable=False, comment='实验名称'),
        sa.Column('description', sa.Text(), nullable=True, comment='实验描述'),
        sa.Column('target_type', sa.String(32), nullable=False, comment='目标类型'),
        sa.Column('target_code', sa.String(64), nullable=True, comment='目标编码'),
        sa.Column('groups', sa.JSON(), nullable=False, comment='分组配置'),
        sa.Column('traffic_ratio', sa.Integer(), nullable=False, default=100, comment='流量占比'),
        sa.Column('status', sa.String(16), nullable=False, default='draft', comment='状态'),
        sa.Column('start_time', sa.DateTime(), nullable=True, comment='开始时间'),
        sa.Column('end_time', sa.DateTime(), nullable=True, comment='结束时间'),
        sa.Column('metrics_config', sa.JSON(), nullable=True, comment='指标配置'),
        sa.Column('created_by', sa.String(64), nullable=True, comment='创建人'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True, comment='更新时间'),
        sa.Column('is_deleted', sa.BigInteger(), nullable=True, default=0, comment='是否删除'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # ab_experiment 索引
    op.create_index('idx_exp_status', 'ab_experiment', ['status'])
    op.create_index('idx_exp_target', 'ab_experiment', ['target_type', 'target_code'])
    op.create_index('idx_exp_created', 'ab_experiment', ['created_at'])
    
    # ============ 创建 trace_daily_stats 表 ============
    op.create_table(
        'trace_daily_stats',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='技术主键'),
        sa.Column('stat_date', sa.Date(), nullable=False, comment='统计日期'),
        sa.Column('stage', sa.String(32), nullable=False, comment='阶段'),
        sa.Column('expert_config_code', sa.String(64), nullable=True, comment='Expert 编码'),
        sa.Column('experiment_id', sa.String(64), nullable=True, comment='实验ID'),
        sa.Column('experiment_group', sa.String(32), nullable=True, comment='实验分组'),
        
        # 调用计数
        sa.Column('total_count', sa.Integer(), nullable=False, default=0, comment='总调用数'),
        sa.Column('success_count', sa.Integer(), nullable=False, default=0, comment='成功数'),
        sa.Column('failed_count', sa.Integer(), nullable=False, default=0, comment='失败数'),
        sa.Column('timeout_count', sa.Integer(), nullable=False, default=0, comment='超时数'),
        
        # 耗时统计
        sa.Column('avg_duration_ms', sa.Float(), nullable=True, comment='平均耗时'),
        sa.Column('p50_duration_ms', sa.Float(), nullable=True, comment='P50 耗时'),
        sa.Column('p95_duration_ms', sa.Float(), nullable=True, comment='P95 耗时'),
        sa.Column('p99_duration_ms', sa.Float(), nullable=True, comment='P99 耗时'),
        sa.Column('min_duration_ms', sa.Integer(), nullable=True, comment='最小耗时'),
        sa.Column('max_duration_ms', sa.Integer(), nullable=True, comment='最大耗时'),
        
        # Token 统计
        sa.Column('total_input_tokens', sa.BigInteger(), nullable=False, default=0, comment='总输入 Token'),
        sa.Column('total_output_tokens', sa.BigInteger(), nullable=False, default=0, comment='总输出 Token'),
        sa.Column('avg_input_tokens', sa.Float(), nullable=True, comment='平均输入 Token'),
        sa.Column('avg_output_tokens', sa.Float(), nullable=True, comment='平均输出 Token'),
        
        # 时间戳
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True, comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True, comment='更新时间'),
        
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stat_date', 'stage', 'expert_config_code', 'experiment_id', 'experiment_group', name='uk_date_stage_expert_exp')
    )
    
    # trace_daily_stats 索引
    op.create_index('idx_stats_date', 'trace_daily_stats', ['stat_date'])
    op.create_index('idx_stats_stage', 'trace_daily_stats', ['stage'])
    op.create_index('idx_stats_expert', 'trace_daily_stats', ['expert_config_code'])
    op.create_index('idx_stats_experiment', 'trace_daily_stats', ['experiment_id', 'experiment_group'])


def downgrade() -> None:
    """删除追踪系统相关表"""
    
    # 删除 trace_daily_stats
    op.drop_index('idx_stats_experiment', table_name='trace_daily_stats')
    op.drop_index('idx_stats_expert', table_name='trace_daily_stats')
    op.drop_index('idx_stats_stage', table_name='trace_daily_stats')
    op.drop_index('idx_stats_date', table_name='trace_daily_stats')
    op.drop_table('trace_daily_stats')
    
    # 删除 ab_experiment
    op.drop_index('idx_exp_created', table_name='ab_experiment')
    op.drop_index('idx_exp_target', table_name='ab_experiment')
    op.drop_index('idx_exp_status', table_name='ab_experiment')
    op.drop_table('ab_experiment')
    
    # 删除 expert_call_trace
    op.drop_index('idx_trace_model_created', table_name='expert_call_trace')
    op.drop_index('idx_trace_created', table_name='expert_call_trace')
    op.drop_index('idx_trace_experiment', table_name='expert_call_trace')
    op.drop_index('idx_trace_expert_code', table_name='expert_call_trace')
    op.drop_index('idx_trace_stage_status', table_name='expert_call_trace')
    op.drop_index('idx_trace_span_parent', table_name='expert_call_trace')
    op.drop_index('idx_trace_trace_id', table_name='expert_call_trace')
    op.drop_index('idx_trace_content_stage', table_name='expert_call_trace')
    op.drop_index('idx_trace_content_id', table_name='expert_call_trace')
    op.drop_index('idx_trace_sub_job_id', table_name='expert_call_trace')
    op.drop_index('idx_trace_job_sub', table_name='expert_call_trace')
    op.drop_index('idx_trace_job_id', table_name='expert_call_trace')
    op.drop_table('expert_call_trace')

