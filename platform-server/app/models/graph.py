"""
图节点和边关系模型
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GraphNode(Base):
    """
    图节点表 - 存储所有业务实体
    """
    __tablename__ = "nodes"

    # 主键与标识
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="节点唯一ID (雪花ID)")
    tenant_code: Mapped[str] = mapped_column(String(64), nullable=False, default="default", comment="租户编码，支持多品牌隔离")

    # 核心属性
    label: Mapped[str] = mapped_column(String(50), nullable=False, comment="节点类型/语义标签 (人设, 大人设, 小人设, 场景, 表达结构 等)")
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="节点名称 (如: 理性科学型妈妈, 发育关注型妈妈)")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="节点描述/定义")
    corpus: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="语料列表，格式: [{\"text\": \"语料内容\", \"weight\": 1.0}]")
    ai_instruction: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="AI 指令 (用于指导 AI 生成内容)")
    properties: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="扩展数据 (如: tags, risk_level, category)")

    # 状态控制
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="状态: 0-禁用 1-启用")
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="软删除: 0-正常 1-已删除")

    # 审计字段
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="创建人ID")
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="最后修改人ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("idx_tenant", "tenant_code"),
        Index("idx_label", "label"),
        Index("idx_tenant_label", "tenant_code", "label"),
        Index("idx_status", "is_active"),
        Index("idx_name", "name"),
        Index("uk_tenant_label_name", "tenant_code", "label", "name", "is_deleted", unique=True),
    )


class GraphEdge(Base):
    """
    图边表 - 存储所有节点间的逻辑关系
    """
    __tablename__ = "edges"

    # 主键与标识
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="边唯一ID (雪花ID)")
    tenant_code: Mapped[str] = mapped_column(String(64), nullable=False, default="default", comment="租户编码")

    # 关系定义
    source_node_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="起点节点ID")
    target_node_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="终点节点ID")
    relation_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="关系类型 (INCLUDES, FITS_WITH, ENCOUNTERS, ...)")
    explanation: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="关系描述")
    meta_data: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="扩展约束 (如: required, exclusive, weight, priority)")

    # 状态控制
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="状态: 0-禁用 1-启用")
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="软删除: 0-正常 1-已删除")

    # 审计字段
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="创建人ID")
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="最后修改人ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("uk_edge", "tenant_code", "source_node_id", "target_node_id", "relation_type", "is_active", "is_deleted", unique=True),
        Index("idx_edge_tenant", "tenant_code"),
        Index("idx_source", "source_node_id"),
        Index("idx_target", "target_node_id"),
        Index("idx_relation", "relation_type"),
        Index("idx_source_relation", "source_node_id", "relation_type"),
        Index("idx_tenant_source_relation", "tenant_code", "source_node_id", "relation_type"),
    )


class NodePropertyMeta(Base):
    """
    节点属性元数据表 - 存储品牌、产品、标签组、标签等配置信息
    与 nodes 表解耦，nodes 表只存储关键词分类（人设/场景/卖点等）
    """
    __tablename__ = "node_property_meta"

    # 主键与标识
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="主键ID")
    tenant_code: Mapped[str] = mapped_column(String(50), nullable=False, default="default", comment="租户编码")

    # 类型：brand / product / tag_group / tag
    item_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="属性类型")

    # 基础信息
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="名称")
    code: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="编码（如品牌编码，用于程序引用）")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="描述")

    # 层级关系（brand->product, tag_group->tag）
    parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="父级ID")

    # 样式配置
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="图标")
    color: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="颜色")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="排序顺序")

    # 状态
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="是否启用")
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="是否删除")

    # 审计字段
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    created_by: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="创建人")

    __table_args__ = (
        Index("idx_npm_tenant_type", "tenant_code", "item_type"),
        Index("idx_npm_parent", "parent_id"),
        Index("idx_npm_code", "code"),
    )
