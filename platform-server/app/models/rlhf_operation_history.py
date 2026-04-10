from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, BigInteger, DateTime, JSON, func
from sqlalchemy.orm import relationship

from app.models.base import Base

class RLHFOperationHistory(Base):
    __tablename__ = "rlhf_operation_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")
    
    feedback_id = Column(BigInteger, nullable=False, index=True, comment="关联 rlhf_feedback.id")
    
    # 操作信息
    operation_type = Column(String(32), nullable=False, index=True, comment="操作类型：LIKE/DISLIKE/ADOPT/REJECT/DISCARD/SCORE/TAG/EDIT/LOCK/UNLOCK")
    
    # 操作前后值
    before_value = Column(JSON, nullable=True, comment="操作前的值")
    after_value = Column(JSON, nullable=True, comment="操作后的值")
    
    # 操作详情
    reason = Column(Text, nullable=True, comment="操作原因")
    improvement_suggestion = Column(Text, nullable=True, comment="改进建议")
    
    # 操作人
    operator_id = Column(String(64), nullable=False, index=True, comment="操作人ID")
    operator_name = Column(String(64), nullable=True, comment="操作人姓名")
    
    # 时间
    operation_time = Column(DateTime(timezone=True), server_default=func.now(), index=True, comment="操作时间")

    # Relationships
    # feedback = relationship("RLHFFeedback", back_populates="operations")

