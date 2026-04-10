"""
语料模板模型
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CorpusTemplate(Base):
    """
    语料模板表 - 定义不同 category_type 的语料结构
    """
    __tablename__ = "corpus_templates"

    # 主键与标识
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="模板ID")
    code: Mapped[str] = mapped_column(String(50), nullable=False, comment="模板编码，如 persona_v1")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="模板名称")
    
    # 模板定义
    # NOTE: category_type 存储的是维度标签（label），关联 nodes 表中相同 label 的节点
    #       例如：persona、brand、product 等
    #       前端使用 label 变量名，API 请求时转换为 category_type
    #       决策记录：保持字段名不变，避免大规模重构（详见 AGENTS.md）
    category_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="维度标签，关联 nodes.label（如 persona/brand/product）")
    fields: Mapped[list] = mapped_column(JSON, nullable=False, comment="字段定义，格式: [{key, label, type, required, placeholder, order}]")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="模板描述")
    
    # 租户隔离
    tenant_code: Mapped[str] = mapped_column(String(50), nullable=False, default="default", comment="租户编码")
    
    # 状态控制
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="软删除: 0-正常 1-已删除")
    
    # 审计字段
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("idx_category_type", "category_type"),
        Index("idx_tenant", "tenant_code"),
        Index("idx_code", "code"),
        # 复合唯一索引：允许相同 code 存在于不同的 is_deleted 状态
        # 例如：code='persona_v1', is_deleted=0 和 code='persona_v1', is_deleted=1 可以共存
        Index("idx_code_unique", "code", "is_deleted", unique=True),
    )
