"""Add Critic Score tables

Revision ID: 013_critic_score
Revises: 012_add_metric_definition_table
Create Date: 2025-12-12

Critic 评分存储系统数据表：
- critic_score_record: 评分结果明细表
- critic_score_daily_stats: 每日统计聚合表
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '013_critic_score'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 创建 Critic 评分结果明细表
    op.create_table(
        'critic_score_record',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('job_id', sa.String(64), nullable=False, comment='Job ID'),
        sa.Column('sub_job_id', sa.String(64), nullable=False, comment='Sub Job ID'),
        sa.Column('content_id', sa.String(64), nullable=False, comment='内容 ID'),
        sa.Column('expert_task_id', sa.BigInteger(), nullable=True, comment='ExpertTask ID'),
        sa.Column('expert_config_code', sa.String(64), nullable=False, comment='Expert 配置编码'),
        sa.Column('expert_func', sa.String(64), nullable=False, comment='Critic 函数名（CriticIllegal/CriticGrace 等）'),
        sa.Column('model_code', sa.String(64), nullable=True, comment='模型编码'),
        sa.Column('provider_code', sa.String(64), nullable=True, comment='Provider 编码'),
        sa.Column('score', sa.Integer(), nullable=False, server_default='0', comment='评分（0-100）'),
        sa.Column('passed', sa.Integer(), nullable=False, server_default='0', comment='是否通过（1=通过，0=不通过）'),
        sa.Column('reason', sa.Text(), nullable=True, comment='评分理由'),
        sa.Column('problem_context_list', sa.JSON(), nullable=True, comment='问题上下文列表'),
        sa.Column('duration_ms', sa.Integer(), nullable=True, comment='耗时（毫秒）'),
        sa.Column('trace_id', sa.String(64), nullable=True, comment='关联 expert_call_trace'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1', comment='版本号（同 content_id + expert_func 递增）'),
        sa.Column('create_time', sa.DateTime(), server_default=sa.func.now(), nullable=True, comment='创建时间'),
        
        sa.PrimaryKeyConstraint('id'),
        comment='Critic 评分结果明细表'
    )
    
    # 创建索引
    op.create_index('idx_critic_job_id', 'critic_score_record', ['job_id'])
    op.create_index('idx_critic_sub_job_id', 'critic_score_record', ['sub_job_id'])
    op.create_index('idx_critic_content_id', 'critic_score_record', ['content_id'])
    op.create_index('idx_critic_expert_config_code', 'critic_score_record', ['expert_config_code'])
    op.create_index('idx_critic_expert_func', 'critic_score_record', ['expert_func'])
    op.create_index('idx_critic_model_code', 'critic_score_record', ['model_code'])
    op.create_index('idx_critic_score', 'critic_score_record', ['score'])
    op.create_index('idx_critic_passed', 'critic_score_record', ['passed'])
    op.create_index('idx_critic_create_time', 'critic_score_record', ['create_time'])
    # 复合索引
    op.create_index('idx_critic_content_func', 'critic_score_record', ['content_id', 'expert_func'])
    op.create_index('idx_critic_job_func', 'critic_score_record', ['job_id', 'expert_func'])
    op.create_index('idx_critic_model_date', 'critic_score_record', ['model_code', 'create_time'])
    op.create_index('idx_critic_passed_date', 'critic_score_record', ['passed', 'create_time'])
    
    # 2. 创建 Critic 每日统计聚合表
    op.create_table(
        'critic_score_daily_stats',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('stat_date', sa.Date(), nullable=False, comment='统计日期'),
        sa.Column('expert_config_code', sa.String(64), nullable=False, comment='Expert 配置编码'),
        sa.Column('expert_func', sa.String(64), nullable=False, comment='Critic 函数名'),
        sa.Column('model_code', sa.String(64), nullable=True, comment='模型编码'),
        sa.Column('total_count', sa.Integer(), nullable=False, server_default='0', comment='总评分次数'),
        sa.Column('passed_count', sa.Integer(), nullable=False, server_default='0', comment='通过次数'),
        sa.Column('avg_score', sa.Float(), nullable=True, comment='平均分'),
        sa.Column('min_score', sa.Integer(), nullable=True, comment='最低分'),
        sa.Column('max_score', sa.Integer(), nullable=True, comment='最高分'),
        sa.Column('p50_score', sa.Float(), nullable=True, comment='P50 分数'),
        sa.Column('p90_score', sa.Float(), nullable=True, comment='P90 分数'),
        sa.Column('avg_duration_ms', sa.Float(), nullable=True, comment='平均耗时（毫秒）'),
        sa.Column('problem_context_top10', sa.JSON(), nullable=True, comment='Top10 问题上下文及出现次数'),
        sa.Column('create_time', sa.DateTime(), server_default=sa.func.now(), nullable=True, comment='创建时间'),
        sa.Column('update_time', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True, comment='更新时间'),
        
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stat_date', 'expert_config_code', 'expert_func', 'model_code', name='uq_critic_daily_stats'),
        comment='Critic 每日统计聚合表'
    )
    
    # 创建索引
    op.create_index('idx_critic_stats_date', 'critic_score_daily_stats', ['stat_date'])
    op.create_index('idx_critic_stats_config_code', 'critic_score_daily_stats', ['expert_config_code'])
    op.create_index('idx_critic_stats_func', 'critic_score_daily_stats', ['expert_func'])
    op.create_index('idx_critic_stats_model', 'critic_score_daily_stats', ['model_code'])
    op.create_index('idx_critic_stats_date_func', 'critic_score_daily_stats', ['stat_date', 'expert_func'])


def downgrade() -> None:
    op.drop_table('critic_score_daily_stats')
    op.drop_table('critic_score_record')
