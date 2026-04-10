"""
ActivityQuestionOption model - 活动问题选项表
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Integer, DateTime, BigInteger, DECIMAL, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.activity_question import ActivityQuestion


class ActivityQuestionOption(Base):
    """活动问题选项表 - 问题的标签选项配置"""
    
    __tablename__ = "activity_question_option"
    
    # 主键
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="技术主键"
    )
    
    # 关联问题
    question_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("activity_question.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="问题ID"
    )
    
    # 标签配置
    display_label: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="小程序展示可替换标签"
    )
    
    aigc_tag: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
        comment="AIGC对应标签"
    )
    
    weight: Mapped[Decimal] = mapped_column(
        DECIMAL(5, 2),
        nullable=False,
        default=1.0,
        comment="标签对应权重"
    )
    
    # 排序
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="排序"
    )
    
    # 元信息
    enabled: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=True,
        comment="是否启用：0禁用 1启用"
    )
    
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=True,
        comment="创建时间"
    )
    
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
        comment="更新时间"
    )
    
    created_by: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="创建人"
    )
    
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="更新人"
    )
    
    is_deleted: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=True,
        comment="是否删除：0否 1是"
    )
    
    # 关联关系
    question: Mapped["ActivityQuestion"] = relationship(
        "ActivityQuestion",
        back_populates="options"
    )
    
    __table_args__ = (
        {"comment": "活动问题选项表"},
    )
    
    def __repr__(self) -> str:
        return f"<ActivityQuestionOption(id={self.id}, question_id={self.question_id}, aigc_tag={self.aigc_tag})>"

