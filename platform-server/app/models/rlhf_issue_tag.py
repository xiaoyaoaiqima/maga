from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, func

from app.models.base import Base

class RLHFIssueTag(Base):
    __tablename__ = "rlhf_issue_tag"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键ID")
    
    tag_code = Column(String(64), nullable=False, unique=True, comment="标签编码")
    tag_name = Column(String(128), nullable=False, comment="标签名称")
    tag_category = Column(String(64), nullable=True, index=True, comment="标签分类：CONTENT/MODEL/BRAND/COMPLIANCE/OTHER")
    description = Column(String(500), nullable=True, comment="标签描述")
    
    enabled = Column(Integer, default=1, index=True, comment="是否启用：0禁用 1启用")
    sort_order = Column(Integer, default=0, index=True, comment="排序")
    use_count = Column(Integer, default=0, comment="使用次数")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
    created_by = Column(String(64), nullable=True, comment="创建人")
    updated_by = Column(String(64), nullable=True, comment="更新人")
    is_deleted = Column(Integer, default=0, comment="是否删除")

