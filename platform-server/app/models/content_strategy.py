"""
内容策略模型 - 定义不同维度关键词的组合规则

v3 简化：
- 统一使用 defined_combinations 存储组合（前端直接管理）
- 前端统一渲染全部组合 + 删减操作 + 重新生成（后悔药）
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ContentStrategy(Base):
    """
    内容策略表 - 定义关键词维度组合规则
    
    v3 简化后：
    - 统一使用 defined_combinations 存储组合
    - 前端负责生成笛卡尔积并管理删减
    """
    __tablename__ = "content_strategies"

    # 主键与标识
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="策略ID")
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="策略名称，如：秋冬换季种草策略")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="策略描述")
    
    # ========== 新结构（v3）==========
    
    # 节点池：各维度可用的节点（v3 包含 select_mode）
    node_pools: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="""
        节点池配置（v3 新结构），格式:
        {
            "persona": {
                "node_ids": ["node_id_1", "node_id_2"],
                "select_mode": "multiple"  // "single" | "multiple"
            },
            "scenario": {
                "node_ids": ["node_id_3", "node_id_4"],
                "select_mode": "single"
            }
        }
        """
    )
    
    # 组合列表（主要存储字段，v3 后统一使用）
    defined_combinations: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment="""
        组合列表（前端管理笛卡尔积生成和删减），格式:
        [
            {
                "id": "combo_0",
                "name": "创业妈妈 + 换季",
                "nodes": {
                    "persona": "node_id_1",
                    "scenario": "node_id_3"
                }
            }
        ]
        """
    )
    
    # ========== 组合规则 ==========
    
    # 最大组合数（笛卡尔积模式下限制返回数量）
    max_combinations: Mapped[int] = mapped_column(
        Integer, 
        nullable=False, 
        default=100,
        comment="最大组合数量（笛卡尔积模式下的上限）"
    )
    
    # 高级配置（简化）
    settings: Mapped[dict | None] = mapped_column(
        JSON, 
        nullable=True, 
        comment="""
        高级设置:
        {
            "include_corpus": true  # 获取组合时是否包含语料
        }
        """
    )
    
    # Scope 上下文（策略绑定的产品/品牌信息）
    scope_context: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="""
        Scope 上下文，用于策略的产品/品牌绑定:
        {
            "level": "product",  # global / brand / product
            "brand_code": "2000001",
            "brand_name": "皇家美素佳儿",
            "product_name": "旺玥",
            "fallback_enabled": true  # 是否启用回退机制（Product > Brand > Global）
        }
        """
    )

    # 租户隔离
    tenant_code: Mapped[str] = mapped_column(String(50), nullable=False, default="default", comment="租户编码")
    
    # 标签（用于分类和快速筛选）
    tags: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        comment="""
        策略标签，用于分类和快速筛选:
        ["换季", "双11", "新品上市"]
        """
    )
    
    # 状态控制
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="状态：0-禁用/归档 1-启用")
    is_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="软删除：0-正常 1-已删除")
    
    # 审计字段
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="创建人")
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="修改人")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    __table_args__ = (
        Index("idx_cs_tenant", "tenant_code"),
        Index("idx_cs_name", "name"),
        Index("idx_cs_status", "is_active", "is_deleted"),
    )

    def get_node_ids_for_dimension(self, dimension_type: str) -> list[str]:
        """获取指定维度的节点ID列表（兼容新旧格式）"""
        if not self.node_pools:
            return []

        pool = self.node_pools.get(dimension_type)
        if pool is None:
            return []

        # 兼容旧格式（直接是 list）和新格式（dict with node_ids）
        if isinstance(pool, list):
            return pool
        elif isinstance(pool, dict):
            return pool.get("node_ids", [])
        elif isinstance(pool, str):
            # 兼容简写格式：直接是节点ID字符串
            return [pool]
        return []
    
    def get_select_mode_for_dimension(self, dimension_type: str) -> str:
        """获取指定维度的选择模式（默认 multiple，即节点分开使用）"""
        if not self.node_pools:
            return "multiple"

        pool = self.node_pools.get(dimension_type)
        if pool is None:
            return "multiple"

        # 兼容旧格式（直接是 list，默认 multiple）和新格式（dict with select_mode）
        if isinstance(pool, list):
            return "multiple"
        elif isinstance(pool, dict):
            return pool.get("select_mode", "multiple")
        return "multiple"