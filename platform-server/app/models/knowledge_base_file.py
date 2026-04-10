"""
知识库文件模型 - 管理语料导入文件

注意：这里指的是单个上传的文件，不是文档容器概念。
文档容器是 KnowledgeBase，一个 KnowledgeBase 可以包含多个 KnowledgeBaseFile（文件）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KnowledgeBaseFile(Base):
    """
    知识库文件表 - 管理单个上传文件

    业务含义：
    - 代表一个上传的文件（Excel/PDF/Word等）
    - 属于某个 KnowledgeBase（知识库）
    - 文件解析后会产生多条 NodePendingAudit 记录
    """
    __tablename__ = "knowledge_base_files"

    # 主键与标识
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, comment="文件ID")

    # 所属文档池（逻辑外键，不设数据库外键约束）
    knowledge_base_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="所属知识库ID（逻辑关联到 knowledge_bases.id）"
    )

    # 文件信息
    file_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="原始文件名")
    file_path: Mapped[str] = mapped_column(String(500), nullable=False, comment="文件存储路径")
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="文件大小（字节）")
    file_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="文件类型: excel/csv/pdf/word")

    # 处理状态
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="状态: pending-待解析 | parsing-解析中 | parsed-已解析 | failed-解析失败",
    )
    parsed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="成功解析的行数")
    total_count: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="文件总行数")
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True, comment="错误信息")

    # 审计字段
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="创建人ID")

    # 软删除
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="软删除: 0-正常 1-已删除")

    __table_args__ = (
        Index("idx_kbf_knowledge_base", "knowledge_base_id"),
        Index("idx_kbf_status", "status"),
    )
