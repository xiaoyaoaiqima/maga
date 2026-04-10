"""
配置快照模型
用于存储 Plugin 和 ExpertConfig 的草稿和版本历史
"""
from sqlalchemy import Column, BigInteger, String, Integer, DateTime, Text, JSON
from sqlalchemy.sql import func

from app.models.base import Base


class ConfigSnapshot(Base):
    """配置快照表"""
    __tablename__ = "config_snapshot"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # 实体标识
    entity_type = Column(String(50), nullable=False, comment="实体类型: plugin, expert_config, plugin_context")
    entity_id = Column(BigInteger, nullable=True, comment="实体ID，新增草稿时为 NULL")
    entity_code = Column(String(255), nullable=False, comment="实体编码，用于关联")
    
    # 快照类型
    snapshot_type = Column(String(20), nullable=False, comment="快照类型: draft(草稿), version(版本)")
    
    # 快照内容
    content = Column(JSON, nullable=False, comment="快照内容(完整的配置JSON)")
    
    # 版本信息
    version = Column(Integer, default=0, comment="版本号，draft为0，version从1开始")
    description = Column(String(500), nullable=True, comment="版本描述")
    
    # 审计字段
    create_time = Column(DateTime, server_default=func.now(), comment="创建时间")
    update_time = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    created_by = Column(String(64), nullable=True, comment="创建人")
    updated_by = Column(String(64), nullable=True, comment="更新人")
    is_deleted = Column(Integer, default=0, nullable=False, comment="是否删除（0否 1是）")
    remark = Column(Text, nullable=True, comment="备注")

