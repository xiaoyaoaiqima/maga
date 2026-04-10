"""
ExpertDebugHistory model - 存储 Expert 调试历史记录
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Boolean, BigInteger, JSON, DateTime, func, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExpertDebugHistory(Base):
    """Expert 调试历史记录"""
    
    __tablename__ = "expert_debug_history"
    
    # 主键ID
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="技术主键"
    )
    
    # 调试的 Expert 配置
    expert_config_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="调试的 expert_config_code"
    )
    
    expert_config_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="调试时的 expert_config 名称"
    )
    
    # 执行状态
    success: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="执行是否成功"
    )
    
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="错误信息"
    )
    
    # 模型配置
    model_code: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="使用的模型编码"
    )
    
    model_config_used: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="实际使用的模型配置"
    )
    
    # Prompt 相关
    prompt_template: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="原始 prompt 模板"
    )
    
    plugin_config_snapshot: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        comment="使用的 plugin_config_snapshot，格式: [{plugin_code, variable_mapping}]"
    )
    
    rendered_prompt: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="渲染后的 prompt"
    )
    
    prompt_override: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="用户手动覆盖的 prompt（如果有）"
    )
    
    # 输入输出
    input_content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="输入的测试内容"
    )
    
    output_content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="AI 输出的内容（主要内容，如 generatedContent）"
    )
    
    expert_total_output: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Expert 返回的完整结果（包含 title、contentId、tokens 等所有字段）"
    )
    
    # 执行统计
    execution_time_ms: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="执行时间（毫秒）"
    )
    
    token_usage: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment="Token 使用情况: {prompt_tokens, completion_tokens, total_tokens}"
    )
    
    # 追踪信息
    trace_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="调用追踪 ID"
    )
    
    # 标记和备注
    is_starred: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="是否收藏"
    )
    
    remark: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="备注"
    )
    
    # 时间戳
    create_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=True,
        comment="创建时间"
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
    
    def __repr__(self) -> str:
        return f"<ExpertDebugHistory(id={self.id}, expert_config_code={self.expert_config_code}, success={self.success})>"

