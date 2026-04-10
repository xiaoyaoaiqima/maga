from datetime import date, datetime
from sqlalchemy import Column, Integer, Date, JSON, DECIMAL, DateTime, func

from app.models.base import Base

class RLHFDailyStats(Base):
    __tablename__ = "rlhf_daily_stats"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    stat_date = Column(Date, nullable=False, unique=True, index=True, comment="统计日期")
    
    # 总体统计
    total_count = Column(Integer, default=0, comment="总反馈数")
    pending_count = Column(Integer, default=0, comment="待审核数")
    completed_count = Column(Integer, default=0, comment="已完成数")
    
    # 喜欢统计
    like_count = Column(Integer, default=0, comment="喜欢数")
    dislike_count = Column(Integer, default=0, comment="不喜欢数")
    like_rate = Column(DECIMAL(5, 2), nullable=True, comment="喜欢率(%)")
    
    # 采纳统计
    adopt_count = Column(Integer, default=0, comment="采纳数")
    reject_count = Column(Integer, default=0, comment="不采纳数")
    discard_count = Column(Integer, default=0, comment="废弃数")
    adopt_rate = Column(DECIMAL(5, 2), nullable=True, comment="采纳率(%)")
    
    # 修改统计
    edit_count = Column(Integer, default=0, comment="修改数")
    edit_after_adopt_count = Column(Integer, default=0, comment="采纳后修改数")
    edit_after_adopt_rate = Column(DECIMAL(5, 2), nullable=True, comment="采纳后修改率(%)")
    
    # 评分统计
    avg_content_score = Column(DECIMAL(3, 1), nullable=True, comment="平均内容评分")
    avg_model_score = Column(DECIMAL(3, 1), nullable=True, comment="平均模型评分")
    
    # JSON 统计
    issue_distribution = Column(JSON, nullable=True, comment="问题类型分布 {tag_code: count}")
    reviewer_stats = Column(JSON, nullable=True, comment="审核人统计 {user_id: {...}}")
    expert_stats = Column(JSON, nullable=True, comment="Expert 统计 {expert_code: {...}}")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")

