"""
ExpertBusinessResult model - expert 业务返回结果记录表
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, String, Text, DateTime, Integer, BigInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExpertBusinessResult(Base):
    """ExpertBusinessResult model - expert 业务返回结果记录表"""
    
    __tablename__ = "expert_business_result"
    
    # 技术主键
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="技术主键"
    )
    
    job_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="job_id"
    )
    sub_job_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="sub_job_id"
    )
    content_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="content_id"
    )
    
    expert_task_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="对应 expert_task.id"
    )
    expert_config_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="对应 expert_config.expert_config_code"
    )
    expert_config_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="对应 expert_config.expert_config_name"
    )
    
    model_code: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="本次执行实际使用的模型编码"
    )
    
    business_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="业务类型：GENERATION/CRITIC/SCORE/REWRITE 等"
    )
    
    plugin_config_snapshot: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="本次执行实际使用的插件配置快照"
    )
    prompt: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="本次执行使用的最终 prompt"
    )
    
    business_result: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="expert 业务返回整体 json"
    )
    
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="SUCCESS",
        comment="SUCCESS/FAILED/PARTIAL"
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="失败原因（如有）"
    )
    
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        server_default=func.now(),
        comment="创建时间"
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间"
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="创建人")
    updated_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="更新人")
    
    is_deleted: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="是否删除（0否 1是）"
    )
    plan_index: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="执行计划索引（槽位编号，从0开始）"
    )
    remark: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="备注"
    )

