"""
ExpertBatchScore schemas
"""
from typing import Optional, List

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampSchema


class ExpertBatchScoreRequest(BaseSchema):
    """批量评分请求"""
    expert_config_code: str = Field(..., description="expert_config 配置 code")
    content_ids: Optional[List[str]] = Field(default=None, description="指定 content_id 列表（为空则获取所有符合条件的文章）")
    max_count: Optional[int] = Field(default=None, description="最大审核数量（0 或不传表示不限制）")
    test_case_only: bool = Field(default=True, description="是否只查询测试用例（默认 True，False 则查询所有文章）")


class ExpertBatchScoreResultResponse(TimestampSchema):
    """批量评分结果响应"""
    id: int
    expert_config_code: str
    content_id: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    score: Optional[int] = None
    reason: Optional[str] = None
    highlights: Optional[str] = None
    problem_tags: Optional[List[str]] = None
    problem_snippets: Optional[List[str]] = None
    model_code: Optional[str] = None
    execution_time_ms: Optional[int] = None
    error_message: Optional[str] = None
    success: bool
    created_by: Optional[str] = None


class ExpertBatchScoreResponse(BaseSchema):
    """批量评分响应"""
    expert_config_code: str
    total: int = Field(..., description="总文章数")
    success_count: int = Field(..., description="成功数量")
    failed_count: int = Field(..., description="失败数量")
    results: List[ExpertBatchScoreResultResponse] = Field(..., description="评分结果列表")


class ExpertBatchScoreListParams(BaseSchema):
    """批量评分结果列表查询参数"""
    expert_config_code: Optional[str] = Field(default=None, description="expert_config 配置 code")
    content_id: Optional[str] = Field(default=None, description="测试用例 content_id")
    success: Optional[bool] = Field(default=None, description="是否成功")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")


class ExpertBatchScoreListResponse(BaseSchema):
    """批量评分结果列表响应"""
    items: List[ExpertBatchScoreResultResponse]
    total: int
    page: int
    page_size: int


# ==================== 异步批量评分（任务模式） ====================

class BatchScoreTaskRequest(BaseSchema):
    """异步批量评分任务请求（支持多专家）"""
    expert_config_codes: List[str] = Field(..., description="expert_config 配置 code 列表（支持多选）")
    content_ids: List[str] = Field(..., description="要评分的 content_id 列表")
    test_case_only: bool = Field(default=False, description="是否只查询测试用例")
    concurrency: int = Field(default=3, ge=1, le=20, description="并发数（1-20，默认3）")


class BatchScoreTaskItem(BaseSchema):
    """单个专家任务信息"""
    task_id: str = Field(..., description="任务 ID")
    expert_config_code: str = Field(..., description="专家配置 code")
    expert_config_name: str = Field(default="", description="专家配置名称")
    status: str = Field(default="pending", description="任务状态")
    total: int = Field(default=0, description="文章数量")


class BatchScoreTaskResponse(BaseSchema):
    """异步批量评分任务创建响应（支持多专家）"""
    tasks: List[BatchScoreTaskItem] = Field(default_factory=list, description="创建的任务列表")
    total_experts: int = Field(default=0, description="专家数量")
    total_contents: int = Field(default=0, description="文章数量")
    message: str = Field(default="任务已创建", description="消息")


class BatchScoreTaskResultItem(BaseSchema):
    """单条评分结果"""
    content_id: str = Field(..., description="content_id")
    title: Optional[str] = Field(default=None, description="标题")
    score: Optional[int] = Field(default=None, description="评分")
    reason: Optional[str] = Field(default=None, description="评分理由")
    success: bool = Field(default=False, description="是否成功")
    error_message: Optional[str] = Field(default=None, description="错误信息")
    execution_time_ms: Optional[int] = Field(default=None, description="执行耗时(ms)")


class BatchScoreTaskStatusResponse(BaseSchema):
    """批量评分任务状态查询响应"""
    task_id: str = Field(..., description="任务 ID")
    status: str = Field(..., description="任务状态: pending/running/completed/failed")
    total: int = Field(default=0, description="总任务数")
    completed: int = Field(default=0, description="已完成数")
    success_count: int = Field(default=0, description="成功数")
    failed_count: int = Field(default=0, description="失败数")
    results: List[BatchScoreTaskResultItem] = Field(default_factory=list, description="评分结果列表")
    error_message: Optional[str] = Field(default=None, description="错误信息")
    start_time: Optional[str] = Field(default=None, description="开始时间")
    end_time: Optional[str] = Field(default=None, description="结束时间")
