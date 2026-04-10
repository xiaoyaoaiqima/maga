"""
Agent model - Agent 产品表
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, JSON, BigInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Agent(Base):
    """Agent 产品表 - Expert 编排模板"""
    
    __tablename__ = "agent"
    
    # 主键
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="技术主键"
    )
    
    # Agent 标识
    agent_code: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="Agent 编码（唯一标识）"
    )
    
    agent_name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        comment="Agent 名称"
    )
    
    # Agent 类型
    agent_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="BATCH_GENERATION",
        comment="类型：BATCH_GENERATION/REALTIME_CHAT/REPORT_ANALYSIS/REVIEW_IMAGE/REVIEW_CONTENT"
    )
    
    # Expert 编排（核心）
    expert_config_code_list: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        comment="Expert 编排顺序（expert_config_code 列表）"
    )

    zero_score_invalid_expert_codes: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            "当这些打分型 Expert 返回 score==0 时，将内容判定为不可用；"
            "None 表示兼容旧逻辑（任意打分 Expert score==0 都判无效）；[] 表示不启用 score==0 判无效"
        )
    )

    tags_config: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="要素标签配置，例：{\"brand_tag_list\": [{\"tag_list\": [{\"tag_name\": \"荷兰\", \"tag_temperature\": 1}], \"tag_type\": \"国别\", \"tag_choose_type\": 1}], \"product_tag_list\": [...], \"activity_tag_list\": [...]}"
    )

    expert_prepared_job_list: Mapped[list] = mapped_column(
        JSON,
        nullable=True,
        comment="Expert 预备好的任务列表（job_id 列表）"
    )
    
    # 默认配置
    default_model_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="默认模型编码"
    )
    
    default_config: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="默认参数配置（temperature、max_tokens 等）"
    )
    
    # 能力描述
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="功能描述"
    )
    
    input_schema: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="输入参数 schema（供前端/调用方参考）"
    )
    
    output_schema: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="输出格式 schema"
    )
    
    # 归属（可选：租户专属或全局共享）
    tenant_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        index=True,
        comment="租户ID（NULL 表示全局共享）"
    )
    
    # 配额与限制
    rate_limit: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="限流配置（QPS、并发、日限额）"
    )
    
    # 上线状态
    publish_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="DRAFT",
        index=True,
        comment="上线状态：DRAFT(草稿)/PUBLISHED(已上线)"
    )
    
    publish_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="上线时间"
    )
    
    publish_by: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="上线人"
    )
    
    # 元信息
    enabled: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=True,
        comment="是否启用：0禁用 1启用"
    )
    
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=True,
        comment="创建时间"
    )
    
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
        comment="更新时间"
    )
    
    created_by: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="创建人"
    )
    
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="更新人"
    )
    
    is_deleted: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=True,
        comment="是否删除：0否 1是"
    )
    
    remark: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="备注"
    )
    
    def __repr__(self) -> str:
        return f"<Agent(id={self.id}, agent_code={self.agent_code}, agent_type={self.agent_type})>"
