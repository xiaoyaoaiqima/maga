"""
SubJob model - 一次文章生产流程的子任务表

v2 重构：
- 新增 plugin_snapshots 字段：插件快照缓存（SubJob 级，保证一致性）
"""
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import JSON, String, Text, DateTime, BigInteger, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SubJob(Base):
    """
    SubJob model - 一次文章生产流程的子任务表
    
    v2 重构说明：
    - plugin_snapshots: 插件快照缓存，保证同一 SubJob 中同一插件的输出一致性
      格式: {"plugin_code": {"变量名": {"source": "strategy", "node_id": "xxx", ...}}}
    """
    
    __tablename__ = "sub_job"
    
    # 技术主键
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="技术主键"
    )
    
    job_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="job_id（全局唯一）"
    )
    sub_job_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="sub_job_id（全局唯一）"
    )
    content_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="content_id（全局唯一）"
    )
    
    expert_list: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        comment="本次 sub_job 需要执行的 expert_config_code 列表（顺序）"
    )
    expert_complete_list: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="已经完成执行的 expert_config_code 列表"
    )
    
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="RUNNING",
        comment="RUNNING/FAILED/COMPLETED"
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="整体失败原因（如有）"
    )
    
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        server_default=func.now(),
        comment="创建时间"
    )
    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间"
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="创建人")
    updated_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="更新人")
    
    is_deleted: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="是否删除（0否 1是）"
    )
    plan_index: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="执行计划索引（槽位编号，从0开始）"
    )
    remark: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="备注"
    )
    
    # ========== v2 新增字段 ==========
    
    # 插件快照缓存（SubJob 级，保证一致性）
    plugin_snapshots: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="""
        插件快照缓存（SubJob 级，保证一致性），格式:
        {
            "writer_plugin": {
                "写者": {
                    "source": "strategy",
                    "strategy_id": 1,
                    "label": "人设",
                    "node_id": "3001004101",
                    "node_name": "精致妈妈",
                    "corpus_id": 0,
                    "corpus_text": "作为一个精致妈妈..."
                },
                "场景": {...},
                "卖点": {...}
            }
        }
        """
    )
    
    def get_plugin_snapshot(self, plugin_code: str) -> Optional[Dict[str, Any]]:
        """获取指定插件的快照"""
        if not self.plugin_snapshots:
            return None
        return self.plugin_snapshots.get(plugin_code)
    
    def set_plugin_snapshot(self, plugin_code: str, snapshot: Dict[str, Any]) -> None:
        """设置指定插件的快照"""
        if self.plugin_snapshots is None:
            self.plugin_snapshots = {}
        self.plugin_snapshots[plugin_code] = snapshot

