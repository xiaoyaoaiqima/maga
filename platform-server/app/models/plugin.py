"""
Plugin model

v2 重构：
- 新增 strategy_id 字段：绑定的内容策略ID（来自 keyword-corpus 服务）
- 新增 variable_mappings 字段：变量到 label 的映射配置
"""
from datetime import datetime
from typing import Optional, List, Any

from sqlalchemy import String, Text, Boolean, Integer, BigInteger, JSON, DateTime, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Plugin(Base):
    """
    Plugin model
    
    v2 重构说明：
    - strategy_id: 绑定的内容策略ID，换活动时切换这个值
    - variable_mappings: 变量映射配置，只定义变量到 label 的映射
      格式: [{"variable_name": "写者", "label": "人设"}]
    """
    
    __tablename__ = "plugin"
    
    # 主键ID
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Primary Key"
    )
    
    plugin_code: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="插件的code"
    )
    
    plugin_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="插件的名称"
    )
    
    plugin_type: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        comment="插件的类型，用于区分：上下文拼接、工具调用等"
    )
    
    variable_list: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="context_template 中的变量列表"
    )
    
    context_template: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="该插件的内容模板（待插入上下文），最终成为提示词的一部分"
    )
    
    # ========== v2 新增字段 ==========
    
    # 绑定的内容策略ID（来自 keyword-corpus 服务的 content_strategies 表）
    strategy_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="绑定的内容策略ID（来自 keyword-corpus 服务，换活动时切换）"
    )
    
    # 变量映射配置（只定义变量到 label 的映射，不绑定具体节点）
    variable_mappings: Mapped[Optional[List[dict]]] = mapped_column(
        JSON,
        nullable=True,
        comment="""
        变量映射配置，格式:
        [
            {"variable_name": "写者", "label": "人设"},
            {"variable_name": "场景", "label": "场景"},
            {"variable_name": "卖点", "label": "卖点"}
        ]
        """
    )
    
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=True,
        comment="是否激活"
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
        String(255),
        nullable=True,
        comment="上线人"
    )
    
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=True,
        comment="Create Time"
    )
    
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
        comment="Update Time"
    )
    
    created_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Created By"
    )
    
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Updated By"
    )
    
    is_deleted: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="是否删除（0否 1是）"
    )
    
    remark: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="备注"
    )
    
    # ========== 表级索引 ==========
    __table_args__ = (
        Index("idx_plugin_strategy", "strategy_id"),
    )
    
    def __repr__(self) -> str:
        return f"<Plugin(id={self.id}, plugin_code={self.plugin_code})>"
    
    def get_variable_mapping_by_name(self, variable_name: str) -> Optional[dict]:
        """根据变量名获取映射配置"""
        if not self.variable_mappings:
            return None
        for mapping in self.variable_mappings:
            if mapping.get("variable_name") == variable_name:
                return mapping
        return None
    
    def get_label_for_variable(self, variable_name: str) -> Optional[str]:
        """获取变量对应的 label"""
        mapping = self.get_variable_mapping_by_name(variable_name)
        return mapping.get("label") if mapping else None

