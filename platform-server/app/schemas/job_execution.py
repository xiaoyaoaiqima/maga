"""
Job Execution Tracking schemas
用于追踪 Job 执行情况的 schema 定义
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import Field

from app.schemas.base import BaseSchema


class JobExecutionStats(BaseSchema):
    """Job 执行统计信息"""
    job_id: str = Field(..., description="Job ID")
    job_name: Optional[str] = Field(default=None, description="Job 名称")
    status: Optional[str] = Field(default=None, description="Job 状态")
    
    # 统计数据
    total_sub_jobs: int = Field(default=0, description="总 sub_job 数量")
    running_sub_jobs: int = Field(default=0, description="运行中的 sub_job 数量")
    completed_sub_jobs: int = Field(default=0, description="已完成的 sub_job 数量")
    failed_sub_jobs: int = Field(default=0, description="失败的 sub_job 数量")
    
    total_contents: int = Field(default=0, description="总文章数量")
    valid_contents: int = Field(default=0, description="有效文章数量")
    invalid_contents: int = Field(default=0, description="无效文章数量")
    pending_contents: int = Field(default=0, description="待确定文章数量")
    test_contents: int = Field(default=0, description="测试文章数量")
    
    # 目标与进度
    target_article_count: Optional[int] = Field(default=None, description="目标文章数")
    progress_percentage: Optional[float] = Field(default=None, description="完成百分比")
    
    # 时间信息
    first_sub_job_time: Optional[datetime] = Field(default=None, description="首个 sub_job 创建时间")
    last_sub_job_time: Optional[datetime] = Field(default=None, description="最新 sub_job 创建时间")
    
    class Config:
        from_attributes = True


class SubJobDetail(BaseSchema):
    """SubJob 详情（包含关联的 content 信息）"""
    id: int
    job_id: str
    sub_job_id: str
    content_id: str
    expert_list: List[str]
    expert_complete_list: Optional[List[str]] = None
    status: str
    error_message: Optional[str] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    plan_index: Optional[int] = Field(default=None, description="执行计划索引")

    # 关联的 content 信息
    content_title: Optional[str] = Field(default=None, description="文章标题")
    content_is_valid: Optional[int] = Field(default=None, description="文章是否有效")
    content_is_test: Optional[int] = Field(default=None, description="是否测试文章")
    
    class Config:
        from_attributes = True


class CriticScoreItem(BaseSchema):
    """单个专家的评分详情"""
    expert_func: str = Field(..., description="专家函数名")
    expert_type: str = Field(default="CRITIC", description="专家类型：BAN/CRITIC")
    score: int = Field(..., description="评分 0-100")
    passed: bool = Field(..., description="是否通过")
    reason: Optional[str] = Field(default=None, description="评分理由")


class ContentCriticSummary(BaseSchema):
    """Critic 评分汇总"""
    total_critics: int = Field(default=0, description="Critic 专家数量")
    passed_count: int = Field(default=0, description="通过数量")
    failed_count: int = Field(default=0, description="不通过数量")
    avg_score: Optional[float] = Field(default=None, description="平均分")
    min_score: Optional[int] = Field(default=None, description="最低分")
    has_ban_issue: bool = Field(default=False, description="是否有合规问题（BAN 类专家不通过）")
    problem_count: int = Field(default=0, description="问题总数")
    # 每个专家的评分详情
    scores: List[CriticScoreItem] = Field(default_factory=list, description="各专家评分详情")


class ContentDetail(BaseSchema):
    """Content 详情"""
    id: int
    job_id: str
    sub_job_id: str
    content_id: str
    agent_code: Optional[str] = Field(None, description="Agent 编码")
    prompt: Optional[str] = None
    context_list: Optional[Dict[str, str]] = Field(
        default=None,
        description="结构化变量映射，格式: {变量名: 上下文名}"
    )
    title: Optional[str] = None
    content: Optional[str] = None
    is_valid: Optional[int] = None
    is_test_case: int
    online_status: Optional[str] = Field(default="OFFLINE", description="上线状态")
    is_locked: int = Field(default=0, description="是否锁定：0否 1是")
    is_used: int = Field(default=0, description="是否被使用：0否 1是")
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None

    # SubJob 状态
    sub_job_status: Optional[str] = Field(default=None, description="关联的 sub_job 状态")

    # Critic 评分汇总
    critic_summary: Optional[ContentCriticSummary] = Field(default=None, description="Critic 评分汇总")

    class Config:
        from_attributes = True


class JobExecutionDetail(BaseSchema):
    """Job 执行详情（包含统计、sub_job 列表、content 列表）"""
    stats: JobExecutionStats
    sub_jobs: List[SubJobDetail] = Field(default_factory=list, description="SubJob 列表")
    contents: List[ContentDetail] = Field(default_factory=list, description="Content 列表")


class ExpertBusinessResultDetail(BaseSchema):
    """Expert 业务结果详情"""
    id: int
    job_id: str
    sub_job_id: str
    content_id: str
    expert_task_id: Optional[int] = None
    expert_config_code: str
    expert_config_name: Optional[str] = None
    expert_func: Optional[str] = None  # 专家函数名（CriticIllegal 等）
    expert_type: Optional[str] = None  # 专家类型：BAN/CRITIC
    model_code: Optional[str] = None
    business_type: Optional[str] = None
    plugin_config_snapshot: Optional[List[Any]] = None
    prompt: Optional[str] = None
    business_result: Optional[Any] = None
    status: Optional[str] = None
    error_message: Optional[str] = None
    create_time: Optional[datetime] = None
    
    class Config:
        from_attributes = True

