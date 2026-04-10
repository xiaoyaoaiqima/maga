"""
基础模型类，包含所有模型共有的字段
"""
from datetime import datetime
from sqlalchemy import Column, BigInteger, DateTime, Integer, String, func
from app.models.base import Base


class BaseModel(Base):
    """
    基础模型类，包含所有模型共有的字段
    """
    __abstract__ = True  # 声明这是一个抽象基类，不会创建实际的数据表

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment='自增id')
    is_deleted = Column(Integer, nullable=False, default=0, comment='是否删除：0-未删除 1-已删除')
    create_time = Column(DateTime, server_default=func.now(), comment='创建时间')
    update_time = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment='更新时间')
    created_by = Column(String(100), default="system", comment='创建者')
    updated_by = Column(String(100), default="system", comment='更新者')

    @classmethod
    def not_deleted(cls):
        """返回未删除条件"""
        return cls.is_deleted == 0

