from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, Integer, Text, BigInteger, DateTime, JSON, DECIMAL, func
from sqlalchemy.orm import relationship

from app.models.base import Base

class RLHFFeedback(Base):
    __tablename__ = "rlhf_feedback"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    
    # 关联追踪系统
    job_id = Column(String(64), nullable=False, index=True, comment="Job ID")
    sub_job_id = Column(String(64), nullable=False, index=True, comment="执行批次 ID")
    content_id = Column(String(64), nullable=False, index=True, comment="内容ID（GE 生成）")
    trace_id = Column(String(64), nullable=True, index=True, comment="关联 expert_call_trace.trace_id")
    
    # 内容信息
    title = Column(String(500), nullable=True, comment="文章标题")
    content = Column(Text, nullable=True, comment="原始内容")
    modified_title = Column(String(500), nullable=True, comment="修改后标题")
    modified_content = Column(Text, nullable=True, comment="修改后内容")
    modify_count = Column(Integer, default=0, comment="修改次数")
    
    # Expert 信息
    ge_expert_code = Column(String(64), nullable=True, comment="GE Expert 编码")
    ag_expert_codes = Column(JSON, nullable=True, comment="AG Expert 编码列表")
    model_code = Column(String(64), nullable=True, comment="使用的模型编码")
    
    # 喜欢状态: -1不喜欢 0待操作 1喜欢
    like_status = Column(Integer, default=0, index=True, comment="喜欢状态")
    like_reason = Column(Text, nullable=True, comment="喜欢/不喜欢原因（≥30字）")
    like_user_id = Column(String(64), nullable=True, index=True, comment="喜欢操作人ID")
    like_user_name = Column(String(64), nullable=True, comment="喜欢操作人姓名")
    like_time = Column(DateTime(timezone=True), nullable=True, comment="喜欢操作时间")
    
    # 采纳状态: -1不采纳 0待操作 1采纳 2废弃
    adopt_status = Column(Integer, default=0, index=True, comment="采纳状态")
    adopt_reason = Column(Text, nullable=True, comment="采纳/不采纳原因（≥30字）")
    adopt_user_id = Column(String(64), nullable=True, index=True, comment="采纳操作人ID")
    adopt_user_name = Column(String(64), nullable=True, comment="采纳操作人姓名")
    adopt_time = Column(DateTime(timezone=True), nullable=True, comment="采纳操作时间")
    
    # 废弃信息
    discard_reason_type = Column(String(64), nullable=True, comment="废弃原因类型")
    discard_comment = Column(Text, nullable=True, comment="废弃详细说明")
    
    # 改进建议
    improvement_suggestion = Column(Text, nullable=True, comment="改进建议")
    
    # 评分
    content_score = Column(DECIMAL(3, 1), default=0, comment="内容评分(1-10)")
    model_score = Column(DECIMAL(3, 1), default=0, comment="模型评分(1-10)")
    
    # 问题标签
    issue_tag_ids = Column(JSON, nullable=True, comment="问题标签ID列表（预定义）")
    custom_issue_tags = Column(JSON, nullable=True, comment="自定义问题标签列表")
    
    # 划词评论
    annotations = Column(JSON, nullable=True, comment="划词评论列表")
    
    # 业务标签
    user_tags = Column(JSON, nullable=True, comment="用户标签")
    product_tags = Column(JSON, nullable=True, comment="产品标签")
    activity_tags = Column(JSON, nullable=True, comment="活动标签")
    brand_tags = Column(JSON, nullable=True, comment="品牌标签")
    
    # 锁定信息
    is_locked = Column(Integer, default=0, comment="是否锁定：0否 1是")
    lock_user_id = Column(String(64), nullable=True, comment="锁定人ID")
    lock_user_name = Column(String(64), nullable=True, comment="锁定人姓名")
    lock_time = Column(DateTime(timezone=True), nullable=True, comment="锁定时间")
    lock_expire_time = Column(DateTime(timezone=True), nullable=True, comment="锁定过期时间")
    
    # 审核状态: PENDING/IN_PROGRESS/COMPLETED/IN_INSPECTION/INSPECTION_PASSED/INSPECTION_FAILED
    review_status = Column(String(32), default="PENDING", index=True, comment="审核状态")
    
    # 审核人信息（喜欢/不喜欢操作）
    review_user_id = Column(String(64), nullable=True, index=True, comment="审核人ID")
    review_user_name = Column(String(64), nullable=True, comment="审核人姓名")
    review_time = Column(DateTime(timezone=True), nullable=True, comment="审核时间")
    
    # 抽检信息
    inspection_status = Column(String(32), default="PENDING", index=True, comment="抽检状态: PENDING/IN_PROGRESS/PASSED/FAILED")
    inspection_result = Column(String(32), nullable=True, comment="抽检结果: PASSED/FAILED")
    inspection_comment = Column(Text, nullable=True, comment="抽检修改意见")
    inspection_user_id = Column(String(64), nullable=True, comment="抽检人ID")
    inspection_user_name = Column(String(64), nullable=True, comment="抽检人姓名")
    inspection_time = Column(DateTime(timezone=True), nullable=True, comment="抽检时间")
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
    created_by = Column(String(64), nullable=True, comment="创建人")
    updated_by = Column(String(64), nullable=True, comment="更新人")
    is_deleted = Column(Integer, default=0, comment="是否删除")

    # Relationships
    # operations = relationship("RLHFOperationHistory", back_populates="feedback", cascade="all, delete-orphan")

