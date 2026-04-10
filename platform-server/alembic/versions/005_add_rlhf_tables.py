"""Add RLHF tables

Revision ID: 005_rlhf
Revises: 004_add_llm_provider_tables
Create Date: 2025-12-09

RLHF 喜欢采纳系统数据表：
- rlhf_feedback: RLHF 反馈主表
- rlhf_operation_history: 审核操作历史表
- rlhf_issue_tag: 问题标签配置表
- rlhf_daily_stats: 每日统计表
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = '005_rlhf'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 创建 RLHF 反馈主表
    op.create_table(
        'rlhf_feedback',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键ID'),
        
        # 关联追踪系统
        sa.Column('job_id', sa.String(64), nullable=False, comment='Job ID'),
        sa.Column('sub_job_id', sa.String(64), nullable=False, comment='执行批次 ID'),
        sa.Column('content_id', sa.String(64), nullable=False, comment='内容ID（GE 生成）'),
        sa.Column('trace_id', sa.String(64), nullable=True, comment='关联 expert_call_trace.trace_id'),
        
        # 内容信息
        sa.Column('title', sa.String(500), nullable=True, comment='文章标题'),
        sa.Column('content', sa.Text(), nullable=True, comment='原始内容'),
        sa.Column('modified_title', sa.String(500), nullable=True, comment='修改后标题'),
        sa.Column('modified_content', sa.Text(), nullable=True, comment='修改后内容'),
        sa.Column('modify_count', sa.Integer(), server_default='0', comment='修改次数'),
        
        # Expert 信息
        sa.Column('ge_expert_code', sa.String(64), nullable=True, comment='GE Expert 编码'),
        sa.Column('ag_expert_codes', sa.JSON(), nullable=True, comment='AG Expert 编码列表'),
        sa.Column('model_code', sa.String(64), nullable=True, comment='使用的模型编码'),
        
        # 喜欢状态
        sa.Column('like_status', sa.Integer(), server_default='0', comment='喜欢状态：-1不喜欢 0待操作 1喜欢'),
        sa.Column('like_reason', sa.Text(), nullable=True, comment='喜欢/不喜欢原因（≥30字）'),
        sa.Column('like_user_id', sa.String(64), nullable=True, comment='喜欢操作人ID'),
        sa.Column('like_user_name', sa.String(64), nullable=True, comment='喜欢操作人姓名'),
        sa.Column('like_time', mysql.DATETIME(fsp=3), nullable=True, comment='喜欢操作时间'),
        
        # 采纳状态
        sa.Column('adopt_status', sa.Integer(), server_default='0', comment='采纳状态：-1不采纳 0待操作 1采纳 2废弃'),
        sa.Column('adopt_reason', sa.Text(), nullable=True, comment='采纳/不采纳原因（≥30字）'),
        sa.Column('adopt_user_id', sa.String(64), nullable=True, comment='采纳操作人ID'),
        sa.Column('adopt_user_name', sa.String(64), nullable=True, comment='采纳操作人姓名'),
        sa.Column('adopt_time', mysql.DATETIME(fsp=3), nullable=True, comment='采纳操作时间'),
        
        # 废弃信息
        sa.Column('discard_reason_type', sa.String(64), nullable=True, comment='废弃原因类型'),
        sa.Column('discard_comment', sa.Text(), nullable=True, comment='废弃详细说明'),
        
        # 改进建议
        sa.Column('improvement_suggestion', sa.Text(), nullable=True, comment='改进建议'),
        
        # 评分
        sa.Column('content_score', sa.DECIMAL(3, 1), server_default='0', comment='内容评分(1-10)'),
        sa.Column('model_score', sa.DECIMAL(3, 1), server_default='0', comment='模型评分(1-10)'),
        
        # 问题标签
        sa.Column('issue_tag_ids', sa.JSON(), nullable=True, comment='问题标签ID列表（预定义）'),
        sa.Column('custom_issue_tags', sa.JSON(), nullable=True, comment='自定义问题标签列表'),
        
        # 业务标签
        sa.Column('user_tags', sa.JSON(), nullable=True, comment='用户标签'),
        sa.Column('product_tags', sa.JSON(), nullable=True, comment='产品标签'),
        sa.Column('activity_tags', sa.JSON(), nullable=True, comment='活动标签'),
        sa.Column('brand_tags', sa.JSON(), nullable=True, comment='品牌标签'),
        
        # 锁定信息
        sa.Column('is_locked', sa.Integer(), server_default='0', comment='是否锁定：0否 1是'),
        sa.Column('lock_user_id', sa.String(64), nullable=True, comment='锁定人ID'),
        sa.Column('lock_user_name', sa.String(64), nullable=True, comment='锁定人姓名'),
        sa.Column('lock_time', sa.DateTime(), nullable=True, comment='锁定时间'),
        sa.Column('lock_expire_time', sa.DateTime(), nullable=True, comment='锁定过期时间'),
        
        # 审核状态
        sa.Column('review_status', sa.String(32), server_default='PENDING', comment='审核状态：PENDING/IN_PROGRESS/COMPLETED'),
        
        # 时间戳
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), comment='更新时间'),
        sa.Column('created_by', sa.String(64), nullable=True, comment='创建人'),
        sa.Column('updated_by', sa.String(64), nullable=True, comment='更新人'),
        sa.Column('is_deleted', sa.Integer(), server_default='0', comment='是否删除'),
        
        sa.PrimaryKeyConstraint('id'),
        comment='RLHF 反馈主表'
    )
    
    # 创建索引
    op.create_index('idx_rlhf_job_id', 'rlhf_feedback', ['job_id'])
    op.create_index('idx_rlhf_sub_job_id', 'rlhf_feedback', ['sub_job_id'])
    op.create_index('idx_rlhf_content_id', 'rlhf_feedback', ['content_id'])
    op.create_index('idx_rlhf_trace_id', 'rlhf_feedback', ['trace_id'])
    op.create_index('idx_rlhf_like_status', 'rlhf_feedback', ['like_status'])
    op.create_index('idx_rlhf_adopt_status', 'rlhf_feedback', ['adopt_status'])
    op.create_index('idx_rlhf_review_status', 'rlhf_feedback', ['review_status'])
    op.create_index('idx_rlhf_like_user', 'rlhf_feedback', ['like_user_id'])
    op.create_index('idx_rlhf_adopt_user', 'rlhf_feedback', ['adopt_user_id'])
    op.create_index('idx_rlhf_job_content', 'rlhf_feedback', ['job_id', 'content_id'])
    op.create_index('idx_rlhf_status', 'rlhf_feedback', ['like_status', 'adopt_status'])
    op.create_index('idx_rlhf_created', 'rlhf_feedback', ['created_at'])
    
    # 2. 创建审核操作历史表
    op.create_table(
        'rlhf_operation_history',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键ID'),
        sa.Column('feedback_id', sa.BigInteger(), nullable=False, comment='关联 rlhf_feedback.id'),
        sa.Column('operation_type', sa.String(32), nullable=False, comment='操作类型：LIKE/DISLIKE/ADOPT/REJECT/DISCARD/SCORE/TAG/EDIT/LOCK/UNLOCK'),
        sa.Column('before_value', sa.JSON(), nullable=True, comment='操作前的值'),
        sa.Column('after_value', sa.JSON(), nullable=True, comment='操作后的值'),
        sa.Column('reason', sa.Text(), nullable=True, comment='操作原因'),
        sa.Column('improvement_suggestion', sa.Text(), nullable=True, comment='改进建议'),
        sa.Column('operator_id', sa.String(64), nullable=False, comment='操作人ID'),
        sa.Column('operator_name', sa.String(64), nullable=True, comment='操作人姓名'),
        sa.Column('operation_time', mysql.DATETIME(fsp=3), server_default=sa.func.now(3), comment='操作时间'),
        
        sa.PrimaryKeyConstraint('id'),
        comment='RLHF 审核操作历史表'
    )
    
    op.create_index('idx_rlhf_history_feedback', 'rlhf_operation_history', ['feedback_id'])
    op.create_index('idx_rlhf_history_operator', 'rlhf_operation_history', ['operator_id'])
    op.create_index('idx_rlhf_history_type', 'rlhf_operation_history', ['operation_type'])
    op.create_index('idx_rlhf_history_time', 'rlhf_operation_history', ['operation_time'])
    op.create_index('idx_rlhf_history_feedback_time', 'rlhf_operation_history', ['feedback_id', 'operation_time'])
    
    # 3. 创建问题标签配置表
    op.create_table(
        'rlhf_issue_tag',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='主键ID'),
        sa.Column('tag_code', sa.String(64), nullable=False, unique=True, comment='标签编码'),
        sa.Column('tag_name', sa.String(128), nullable=False, comment='标签名称'),
        sa.Column('tag_category', sa.String(64), nullable=True, comment='标签分类：CONTENT/MODEL/BRAND/COMPLIANCE/OTHER'),
        sa.Column('description', sa.String(500), nullable=True, comment='标签描述'),
        sa.Column('enabled', sa.Integer(), server_default='1', comment='是否启用：0禁用 1启用'),
        sa.Column('sort_order', sa.Integer(), server_default='0', comment='排序'),
        sa.Column('use_count', sa.Integer(), server_default='0', comment='使用次数'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), comment='创建时间'),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), comment='更新时间'),
        sa.Column('created_by', sa.String(64), nullable=True, comment='创建人'),
        sa.Column('updated_by', sa.String(64), nullable=True, comment='更新人'),
        sa.Column('is_deleted', sa.Integer(), server_default='0', comment='是否删除'),
        
        sa.PrimaryKeyConstraint('id'),
        comment='RLHF 问题标签配置表'
    )
    
    op.create_index('idx_rlhf_tag_category', 'rlhf_issue_tag', ['tag_category'])
    op.create_index('idx_rlhf_tag_enabled', 'rlhf_issue_tag', ['enabled'])
    op.create_index('idx_rlhf_tag_sort', 'rlhf_issue_tag', ['sort_order'])
    
    # 4. 创建每日统计表
    op.create_table(
        'rlhf_daily_stats',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='主键ID'),
        sa.Column('stat_date', sa.Date(), nullable=False, unique=True, comment='统计日期'),
        
        # 总体统计
        sa.Column('total_count', sa.Integer(), server_default='0', comment='总反馈数'),
        sa.Column('pending_count', sa.Integer(), server_default='0', comment='待审核数'),
        sa.Column('completed_count', sa.Integer(), server_default='0', comment='已完成数'),
        
        # 喜欢统计
        sa.Column('like_count', sa.Integer(), server_default='0', comment='喜欢数'),
        sa.Column('dislike_count', sa.Integer(), server_default='0', comment='不喜欢数'),
        sa.Column('like_rate', sa.DECIMAL(5, 2), nullable=True, comment='喜欢率(%)'),
        
        # 采纳统计
        sa.Column('adopt_count', sa.Integer(), server_default='0', comment='采纳数'),
        sa.Column('reject_count', sa.Integer(), server_default='0', comment='不采纳数'),
        sa.Column('discard_count', sa.Integer(), server_default='0', comment='废弃数'),
        sa.Column('adopt_rate', sa.DECIMAL(5, 2), nullable=True, comment='采纳率(%)'),
        
        # 修改统计
        sa.Column('edit_count', sa.Integer(), server_default='0', comment='修改数'),
        sa.Column('edit_after_adopt_count', sa.Integer(), server_default='0', comment='采纳后修改数'),
        sa.Column('edit_after_adopt_rate', sa.DECIMAL(5, 2), nullable=True, comment='采纳后修改率(%)'),
        
        # 评分统计
        sa.Column('avg_content_score', sa.DECIMAL(3, 1), nullable=True, comment='平均内容评分'),
        sa.Column('avg_model_score', sa.DECIMAL(3, 1), nullable=True, comment='平均模型评分'),
        
        # JSON 统计
        sa.Column('issue_distribution', sa.JSON(), nullable=True, comment='问题类型分布 {tag_code: count}'),
        sa.Column('reviewer_stats', sa.JSON(), nullable=True, comment='审核人统计 {user_id: {...}}'),
        sa.Column('expert_stats', sa.JSON(), nullable=True, comment='Expert 统计 {expert_code: {...}}'),
        
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), comment='创建时间'),
        
        sa.PrimaryKeyConstraint('id'),
        comment='RLHF 每日统计表'
    )
    
    op.create_index('idx_rlhf_stats_date', 'rlhf_daily_stats', ['stat_date'])
    
    # 5. 插入默认问题标签
    op.execute("""
        INSERT INTO rlhf_issue_tag (tag_code, tag_name, tag_category, description, sort_order) VALUES
        ('CONTENT_DUPLICATE', '内容重复', 'CONTENT', '内容与已有素材重复', 1),
        ('CONTENT_INACCURATE', '信息不准确', 'CONTENT', '内容中存在事实性错误', 2),
        ('CONTENT_INCOMPLETE', '内容不完整', 'CONTENT', '关键信息缺失', 3),
        ('MODEL_RIGID', '表达生硬', 'MODEL', '语言表达不够自然流畅', 10),
        ('MODEL_FORMAT', '格式问题', 'MODEL', '文章结构或格式不符合要求', 11),
        ('MODEL_LENGTH', '长度不适', 'MODEL', '内容过长或过短', 12),
        ('BRAND_TONE', '调性不符', 'BRAND', '不符合品牌调性要求', 20),
        ('BRAND_STYLE', '风格不一致', 'BRAND', '与品牌风格不一致', 21),
        ('COMPLIANCE_SENSITIVE', '敏感内容', 'COMPLIANCE', '包含敏感或违规内容', 30),
        ('OTHER', '其他问题', 'OTHER', '其他未分类问题', 100)
    """)


def downgrade() -> None:
    op.drop_table('rlhf_daily_stats')
    op.drop_table('rlhf_issue_tag')
    op.drop_table('rlhf_operation_history')
    op.drop_table('rlhf_feedback')

