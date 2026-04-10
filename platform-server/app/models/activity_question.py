"""
ActivityQuestion model - 活动问题表
"""
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Integer, DateTime, BigInteger, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.activity_question_option import ActivityQuestionOption


class ActivityQuestion(Base):
    """活动问题表 - 活动问题配置"""
    
    __tablename__ = "activity_question"
    
    # 主键
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="技术主键"
    )
    
    # 关联活动
    activity_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("activity.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="活动ID"
    )
    
    # 问题内容
    question_text: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="问题内容"
    )
    
    # 选择限制
    min_select: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="最小选择数（空则不限制）"
    )
    
    max_select: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="最大选择数（空则不限制）"
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
    options: Mapped[List["ActivityQuestionOption"]] = relationship(
        "ActivityQuestionOption",
        back_populates="question",
        lazy="selectin",
        cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        {"comment": "活动问题表"},
    )
    
    def __repr__(self) -> str:
        return f"<ActivityQuestion(id={self.id}, activity_id={self.activity_id}, question_text={self.question_text[:20]}...)>"

