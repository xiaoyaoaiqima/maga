"""
AB测试数据模型
统一支持 Expert 维度和 Agent/Job 维度的对比实验
单表设计，通过 test_type 区分维度
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, BigInteger, JSON, DateTime, func, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ABTest(Base):
    """
    AB测试记录表 - 统一 Expert/Job 维度
    
    设计原则：
    - 通过 test_type 区分 EXPERT_CONFIG 和 AGENT_JOB 两种维度
    - EXPERT_CONFIG：关联 debug_history_ids，从调试历史获取 trace 数据
    - AGENT_JOB：关联 job_ids，从 Job 下的 content 获取 trace 数据
    - 不再有执行逻辑，只做已有数据的关联和聚合
    
    数据关联路径：
    - EXPERT_CONFIG: debug_history_id → expert_debug_history.trace_id → expert_call_trace
    - AGENT_JOB: job_id → content.job_id → expert_call_trace.content_id
    """

    __tablename__ = "ab_test"

    # 主键ID
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="技术主键"
    )

    # 测试唯一标识
    test_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="测试唯一标识"
    )

    # 测试名称
    test_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="测试名称"
    )

    # 测试类型
    test_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        comment="测试类型: EXPERT_CONFIG, AGENT_JOB"
    )

    # ========== 关联数据（根据 test_type 使用不同字段）==========
    
    # EXPERT_CONFIG 类型：关联调试历史（支持同一组多次执行）
    # 格式: {"control": [101, 103, 105], "experiment_1": [102, 104, 106]}
    debug_history_ids: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Expert 调试历史关联，key 为组名，value 为 debug_history_id 数组"
    )

    # AGENT_JOB 类型：关联 Job
    # 格式: {"control": "job_001", "experiment_1": "job_002", "experiment_2": "job_003"}
    job_ids: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Job 关联，key 为组名，value 为 job_id"
    )

    # ========== 对比组描述 ==========
    # 格式: [{"group_name": "control", "description": "原始配置", "config_snapshot": {...}}, ...]
    groups: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        comment="对比组信息，包含组名、描述、配置快照"
    )

    # ========== 统计与结果 ==========
    # 格式: {"control": {"success_rate": 0.95, "avg_score": 85, "avg_cost": 0.02, ...}, ...}
    metrics: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="各组聚合指标"
    )

    # 推荐胜出方
    winner: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="推荐胜出方: group_name 或 TIE 或 INCONCLUSIVE"
    )

    # 推荐理由
    recommendation: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="推荐理由"
    )

    # ========== 状态与元数据 ==========
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        index=True,
        comment="状态: pending, analyzing, completed, failed"
    )

    start_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="开始分析时间"
    )

    end_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="完成时间"
    )

    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="创建时间"
    )

    update_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        onupdate=func.now(),
        comment="更新时间"
    )

    created_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="创建人"
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

    def __repr__(self) -> str:
        return f"<ABTest(id={self.id}, test_id={self.test_id}, test_type={self.test_type}, status={self.status})>"
