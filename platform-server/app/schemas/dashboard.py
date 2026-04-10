"""
Dashboard schemas
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class SystemStatus(BaseModel):
    """系统状态"""
    orchestrator: bool = Field(..., description="Orchestrator 服务状态")
    database: bool = Field(..., description="数据库连接状态")
    redis: bool = Field(..., description="Redis 连接状态")


class DashboardStats(BaseModel):
    """仪表盘统计数据"""
    total_plugins: int = Field(..., description="Plugin 总数")
    total_expert_configs: int = Field(..., description="ExpertConfig 总数")
    total_jobs: int = Field(..., description="Job 总数")
    deployed_jobs: int = Field(..., description="已部署 Job 数量")
    running_jobs: int = Field(..., description="运行中 Job 数量")
    today_executions: int = Field(..., description="今日执行次数")
    success_rate: float = Field(..., description="成功率（百分比）")


class RecentExecution(BaseModel):
    """最近执行记录"""
    id: str = Field(..., description="任务ID")
    job_name: str = Field(..., description="Job 名称")
    job_id: Optional[str] = Field(None, description="Job ID")
    expert_config_code: str = Field(..., description="Expert 配置编码")
    status: str = Field(..., description="状态: success/failed/running")
    created_at: datetime = Field(..., description="创建时间")
    execution_time_ms: Optional[int] = Field(None, description="执行耗时（毫秒）")
    error: Optional[str] = Field(None, description="错误信息")


class DashboardResponse(BaseModel):
    """仪表盘完整响应"""
    stats: DashboardStats = Field(..., description="统计数据")
    system_status: SystemStatus = Field(..., description="系统状态")
    recent_executions: List[RecentExecution] = Field(..., description="最近执行记录")


class DashboardSummary(BaseModel):
    """仪表盘摘要数据（精简版）"""
    total_jobs: int = Field(..., description="Job 总数")
    running_jobs: int = Field(..., description="运行中 Job 数量")
    today_executions: int = Field(..., description="今日执行次数")
    success_rate: float = Field(..., description="成功率（百分比）")


class DashboardSummaryResponse(BaseModel):
    """仪表盘摘要响应（轻量级）"""
    summary: DashboardSummary = Field(..., description="摘要统计数据")
    system_status: SystemStatus = Field(..., description="系统状态")
    last_updated: datetime = Field(..., description="最后更新时间")

