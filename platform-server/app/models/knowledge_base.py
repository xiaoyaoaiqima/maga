"""
知识库模型 - 文档容器概念

用于组织和管理多个上传的文件（KnowledgeBaseFile）
一个 KnowledgeBase 可以包含多个 KnowledgeBaseFile（上传的文件）

注意：知识库只是纯粹的文件容器，与关键词类型无关
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KnowledgeBase(Base):
    """
    知识库表 - 文档容器，用于组织和管理多个上传文件

    业务含义：
    - 一个 KnowledgeBase 代表一个"知识库"或"项目"
    - 知识库是纯粹的文件容器，不关联关键词类型和租户
    - 用户可以向 KnowledgeBase 上传多个文件（每个文件是一个 KnowledgeBaseFile）
    """
    __tablename__ = "knowledge_bases"

    # 主键与标识
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="知识库ID")
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, comment="编码（唯一标识）")

    # 基本信息
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="知识库名称")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="描述")

    # 状态控制
    enabled: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="启用状态: 0-禁用 1-启用"
    )

    # 统计信息（冗余字段，便于查询）
    file_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="关联的文件数量"
    )
    total_parsed_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="总解析记录数"
    )

    # 审计字段
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="创建人ID")

    # 软删除
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="软删除: 0-正常 1-已删除")

    __table_args__ = (
        Index("idx_kb_enabled", "enabled"),
    )
