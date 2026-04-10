"""
Job model
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Boolean, JSON, DateTime, Integer, BigInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Job(Base):
    """Job model"""
    
    __tablename__ = "job"
    
    # 技术主键
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="技术主键"
    )
    
    # 全局唯一 job_id
    job_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        comment="全局唯一 job_id（工具生成）"
    )
    
    job_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="任务名称"
    )
    
    # 多租户与活动关联
    tenant_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="租户ID"
    )
    
    activity_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="活动ID"
    )
    
    agent_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="关联 Agent 编码"
    )
    
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="任务描述"
    )
    
    expert_config_code_list: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        comment="参与的 expert_config.expert_config_code 列表（顺序即流程顺序，可覆盖 Agent 默认编排）"
    )
    
    zero_score_invalid_expert_codes: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="当这些打分型 Expert 返回 score==0 时，将文章判定为不可用（content.is_valid=0）并提前完成 sub_job；None 表示兼容旧逻辑（任意打分 Expert score==0 都判无效）"
    )

    job_generation_plan: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="由 JobCreateDraft 编译得到的执行计划（多组合/分流/Variant），存在时优先生效"
    )
    
    article_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="本次job目标生产文章篇数"
    )
    
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="NOT_DEPLOYED",
        comment="任务状态：NOT_DEPLOYED/DEPLOYED/PAUSED/COMPLETED"
    )
    
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=True,
        comment="是否可用"
    )
    
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=True,
        comment="Create Time"
    )
    
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
        comment="Update Time"
    )
    
    created_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Created By"
    )
    
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Updated By"
    )
    
    is_deleted: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="是否删除（0否 1是）"
    )
    
    remark: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="备注"
    )
    
    def __repr__(self) -> str:
        return f"<Job(job_id={self.job_id}, job_name={self.job_name})>"

