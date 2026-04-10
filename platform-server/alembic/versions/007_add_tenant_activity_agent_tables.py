"""Add Tenant, Activity, Agent tables and Job fields

Revision ID: 007_tenant_activity_agent
Revises: 006_add_rlhf_trace_fields
Create Date: 2025-12-10

多租户与 Agent 产品模板数据表：
- tenant: 租户表（多甲方数据隔离）
- activity: 活动表（运营活动管理）
- agent: Agent 产品表（Expert 编排模板）
- job: 新增 tenant_id, activity_id, agent_code 字段
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = '007_tenant_activity_agent'
down_revision = '006_rlhf_trace'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 创建租户表
    op.create_table(
        'tenant',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='技术主键'),
        sa.Column('tenant_code', sa.String(64), nullable=False, comment='租户编码（唯一标识）'),
        sa.Column('tenant_name', sa.String(255), nullable=False, comment='租户名称'),
        
        # 联系信息
        sa.Column('contact_name', sa.String(64), nullable=True, comment='联系人姓名'),
        sa.Column('contact_phone', sa.String(32), nullable=True, comment='联系电话'),
        sa.Column('contact_email', sa.String(128), nullable=True, comment='联系邮箱'),
        
        # 配额与状态
        sa.Column('quota_config', sa.JSON(), nullable=True, comment='配额配置（日限额、月限额、并发数等）'),
        sa.Column('status', sa.String(32), nullable=False, server_default='ACTIVE', comment='状态：ACTIVE/SUSPENDED/EXPIRED'),
        sa.Column('expire_time', mysql.DATETIME(), nullable=True, comment='服务到期时间'),
        
        # 元信息
        sa.Column('enabled', sa.Integer(), server_default='1', comment='是否启用：0禁用 1启用'),
        sa.Column('create_time', mysql.DATETIME(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.Column('update_time', mysql.DATETIME(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), comment='更新时间'),
        sa.Column('created_by', sa.String(64), nullable=True, comment='创建人'),
        sa.Column('updated_by', sa.String(64), nullable=True, comment='更新人'),
        sa.Column('is_deleted', sa.Integer(), server_default='0', comment='是否删除：0否 1是'),
        sa.Column('remark', sa.Text(), nullable=True, comment='备注'),
        
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_code', name='uk_tenant_code'),
        comment='租户表'
    )
    op.create_index('idx_tenant_status', 'tenant', ['status'])
    
    # 2. 创建活动表
    op.create_table(
        'activity',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='技术主键'),
        sa.Column('activity_code', sa.String(64), nullable=False, comment='活动编码'),
        sa.Column('activity_name', sa.String(255), nullable=False, comment='活动名称'),
        
        # 关联租户
        sa.Column('tenant_id', sa.BigInteger(), nullable=False, comment='租户ID'),
        
        # 活动配置
        sa.Column('channel', sa.String(64), nullable=True, comment='渠道（xiaohongshu/douyin/taobao）'),
        sa.Column('target_audience', sa.String(255), nullable=True, comment='目标人群'),
        sa.Column('budget', sa.DECIMAL(12, 2), nullable=True, comment='预算'),
        sa.Column('config_json', sa.JSON(), nullable=True, comment='活动配置（Agent选择、产量目标等）'),
        
        # 时间范围
        sa.Column('start_time', mysql.DATETIME(), nullable=True, comment='活动开始时间'),
        sa.Column('end_time', mysql.DATETIME(), nullable=True, comment='活动结束时间'),
        
        # 状态
        sa.Column('status', sa.String(32), nullable=False, server_default='DRAFT', comment='状态：DRAFT/RUNNING/PAUSED/COMPLETED'),
        
        # 元信息
        sa.Column('enabled', sa.Integer(), server_default='1', comment='是否启用：0禁用 1启用'),
        sa.Column('create_time', mysql.DATETIME(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.Column('update_time', mysql.DATETIME(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), comment='更新时间'),
        sa.Column('created_by', sa.String(64), nullable=True, comment='创建人'),
        sa.Column('updated_by', sa.String(64), nullable=True, comment='更新人'),
        sa.Column('is_deleted', sa.Integer(), server_default='0', comment='是否删除：0否 1是'),
        sa.Column('remark', sa.Text(), nullable=True, comment='备注'),
        
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'activity_code', name='uk_tenant_activity'),
        comment='活动表'
    )
    op.create_index('idx_activity_tenant', 'activity', ['tenant_id'])
    op.create_index('idx_activity_status', 'activity', ['status'])
    
    # 3. 创建 Agent 表
    op.create_table(
        'agent',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='技术主键'),
        sa.Column('agent_code', sa.String(64), nullable=False, comment='Agent 编码（唯一标识）'),
        sa.Column('agent_name', sa.String(255), nullable=False, comment='Agent 名称'),
        
        # Agent 类型
        sa.Column('agent_type', sa.String(32), nullable=False, server_default='BATCH_GENERATION', 
                  comment='类型：BATCH_GENERATION/REALTIME_CHAT/REPORT_ANALYSIS'),
        
        # Expert 编排
        sa.Column('expert_config_code_list', sa.JSON(), nullable=False, comment='Expert 编排顺序'),
        
        # 默认配置
        sa.Column('default_model_code', sa.String(64), nullable=True, comment='默认模型编码'),
        sa.Column('default_config', sa.JSON(), nullable=True, comment='默认参数配置'),
        
        # 能力描述
        sa.Column('description', sa.Text(), nullable=True, comment='功能描述'),
        sa.Column('input_schema', sa.JSON(), nullable=True, comment='输入参数 schema'),
        sa.Column('output_schema', sa.JSON(), nullable=True, comment='输出格式 schema'),
        
        # 归属
        sa.Column('tenant_id', sa.BigInteger(), nullable=True, comment='租户ID（NULL 表示全局共享）'),
        
        # 限流
        sa.Column('rate_limit', sa.JSON(), nullable=True, comment='限流配置'),
        
        # 元信息
        sa.Column('enabled', sa.Integer(), server_default='1', comment='是否启用：0禁用 1启用'),
        sa.Column('create_time', mysql.DATETIME(), server_default=sa.text('CURRENT_TIMESTAMP'), comment='创建时间'),
        sa.Column('update_time', mysql.DATETIME(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), comment='更新时间'),
        sa.Column('created_by', sa.String(64), nullable=True, comment='创建人'),
        sa.Column('updated_by', sa.String(64), nullable=True, comment='更新人'),
        sa.Column('is_deleted', sa.Integer(), server_default='0', comment='是否删除：0否 1是'),
        sa.Column('remark', sa.Text(), nullable=True, comment='备注'),
        
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('agent_code', name='uk_agent_code'),
        comment='Agent 产品表'
    )
    op.create_index('idx_agent_type', 'agent', ['agent_type'])
    op.create_index('idx_agent_tenant', 'agent', ['tenant_id'])
    
    # 4. 为 job 表添加新字段
    op.add_column('job', sa.Column('tenant_id', sa.BigInteger(), nullable=True, comment='租户ID'))
    op.add_column('job', sa.Column('activity_id', sa.BigInteger(), nullable=True, comment='活动ID'))
    op.add_column('job', sa.Column('agent_code', sa.String(64), nullable=True, comment='关联 Agent 编码'))
    
    op.create_index('idx_job_tenant', 'job', ['tenant_id'])
    op.create_index('idx_job_activity', 'job', ['activity_id'])
    op.create_index('idx_job_agent', 'job', ['agent_code'])


def downgrade() -> None:
    # 1. 删除 job 表的新字段和索引
    op.drop_index('idx_job_agent', table_name='job')
    op.drop_index('idx_job_activity', table_name='job')
    op.drop_index('idx_job_tenant', table_name='job')
    op.drop_column('job', 'agent_code')
    op.drop_column('job', 'activity_id')
    op.drop_column('job', 'tenant_id')
    
    # 2. 删除 agent 表
    op.drop_index('idx_agent_tenant', table_name='agent')
    op.drop_index('idx_agent_type', table_name='agent')
    op.drop_table('agent')
    
    # 3. 删除 activity 表
    op.drop_index('idx_activity_status', table_name='activity')
    op.drop_index('idx_activity_tenant', table_name='activity')
    op.drop_table('activity')
    
    # 4. 删除 tenant 表
    op.drop_index('idx_tenant_status', table_name='tenant')
    op.drop_table('tenant')
