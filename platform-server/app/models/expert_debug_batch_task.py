"""Expert 批量调试任务模型"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.sql import func

from app.models.base import Base


class ExpertDebugBatchTask(Base):
    """Expert 批量调试任务"""
    __tablename__ = "expert_debug_batch_task"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键")
    task_id = Column(String(64), unique=True, nullable=False, index=True, comment="任务唯一标识")
    expert_config_code = Column(String(128), nullable=False, index=True, comment="Expert 配置编码")
    expert_config_name = Column(String(256), nullable=True, comment="Expert 配置名称")
    status = Column(String(32), nullable=False, index=True, comment="任务状态: pending/running/completed/failed")
    total = Column(Integer, nullable=False, default=0, comment="总任务数")
    completed = Column(Integer, nullable=False, default=0, comment="已完成数")
    success_count = Column(Integer, nullable=False, default=0, comment="成功数")
    failed_count = Column(Integer, nullable=False, default=0, comment="失败数")
    request_params = Column(JSON, nullable=True, comment="请求参数")
    results = Column(JSON, nullable=True, comment="结果列表")
    error_message = Column(Text, nullable=True, comment="错误信息")
    start_time = Column(DateTime, nullable=True, comment="开始时间")
    end_time = Column(DateTime, nullable=True, comment="结束时间")
    create_time = Column(DateTime, server_default=func.now(), nullable=False, comment="创建时间")
    update_time = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False, comment="更新时间")

    __table_args__ = (
        Index('idx_expert_config_code', 'expert_config_code'),
        Index('idx_status', 'status'),
        Index('idx_create_time', 'create_time'),
        {'comment': 'Expert 批量调试任务表'}
    )

