"""
Job schemas
"""
from datetime import datetime
from typing import Optional, Dict, Any, List

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampSchema


class JobBase(BaseSchema):
    """Job base schema"""
    job_name: str = Field(..., max_length=255, description="任务名称")
    # 多租户与活动关联
    tenant_id: Optional[int] = Field(default=None, description="租户ID")
    tenant_name: Optional[str] = Field(default=None, description="租户名称")
    activity_id: Optional[int] = Field(default=None, description="活动ID")
    activity_name: Optional[str] = Field(default=None, description="活动名称")
    agent_code: Optional[str] = Field(default=None, max_length=64, description="关联 Agent 编码")
    agent_name: Optional[str] = Field(default=None, description="Agent 名称")
    description: Optional[str] = Field(default=None, description="任务描述")
    expert_config_code_list: list[str] = Field(
        default_factory=list,
        description="参与的 expert_config.expert_config_code 列表（创建时可省略，由 Agent 继承）",
    )
    zero_score_invalid_expert_codes: Optional[list[str]] = Field(
        default=None,
        description=(
            "当这些打分型 Expert 返回 score==0 时，将文章判定为不可用（content.is_valid=0）并提前完成 sub_job；"
            "None 表示兼容旧逻辑（任意打分 Expert score==0 都判无效）；[] 表示不启用 score==0 判无效"
        ),
    )
    job_generation_plan: Optional[Dict[str, Any]] = Field(
        default=None,
        description="由 JobCreateDraft 编译得到的执行计划（多组合/分流/Variant），存在时优先生效",
    )
    article_count: Optional[int] = Field(default=None, description="本次job目标生产文章篇数")
    status: str = Field(default="NOT_DEPLOYED", max_length=32, description="任务状态")
    enabled: bool = Field(default=True, description="是否可用")
    remark: Optional[str] = Field(default=None, description="备注")


class JobListBase(BaseSchema):
    """Job list base schema - excludes large fields for list queries"""
    job_name: str = Field(..., max_length=255, description="任务名称")
    # 多租户与活动关联
    tenant_id: Optional[int] = Field(default=None, description="租户ID")
    tenant_name: Optional[str] = Field(default=None, description="租户名称")
    activity_id: Optional[int] = Field(default=None, description="活动ID")
    activity_name: Optional[str] = Field(default=None, description="活动名称")
    agent_code: Optional[str] = Field(default=None, max_length=64, description="关联 Agent 编码")
    agent_name: Optional[str] = Field(default=None, description="Agent 名称")
    description: Optional[str] = Field(default=None, description="任务描述")
    expert_config_code_list: list[str] = Field(
        default_factory=list,
        description="参与的 expert_config.expert_config_code 列表（创建时可省略，由 Agent 继承）",
    )
    zero_score_invalid_expert_codes: Optional[list[str]] = Field(
        default=None,
        description=(
            "当这些打分型 Expert 返回 score==0 时，将文章判定为不可用（content.is_valid=0）并提前完成 sub_job；"
            "None 表示兼容旧逻辑（任意打分 Expert score==0 都判无效）；[] 表示不启用 score==0 判无效"
        ),
    )
    # 列表接口不返回 job_generation_plan（避免大字段导致内存问题）
    article_count: Optional[int] = Field(default=None, description="本次job目标生产文章篇数")
    status: str = Field(default="NOT_DEPLOYED", max_length=32, description="任务状态")
    enabled: bool = Field(default=True, description="是否可用")
    remark: Optional[str] = Field(default=None, description="备注")


class JobCreate(JobBase):
    """Job create schema"""
    pass


class JobUpdate(BaseSchema):
    """Job update schema"""
    job_name: Optional[str] = Field(default=None, max_length=255)
    tenant_id: Optional[int] = None
    activity_id: Optional[int] = None
    agent_code: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = None
    expert_config_code_list: Optional[list[str]] = None
    zero_score_invalid_expert_codes: Optional[list[str]] = None
    job_generation_plan: Optional[Dict[str, Any]] = None
    article_count: Optional[int] = None
    status: Optional[str] = Field(default=None, max_length=32)
    enabled: Optional[bool] = None
    remark: Optional[str] = None


class ExpertTaskConfig(BaseSchema):
    """单个 Expert Task 配置"""
    expert_config_code: str = Field(..., description="expert_config_code")
    cron_expression: str = Field(default="0 * * * * *", description="cron 表达式")
    misfire_policy: int = Field(default=1, description="计划执行错误策略：1立即执行 2执行一次 3放弃执行")
    concurrent: int = Field(default=0, description="是否并发执行：0允许 1禁止")


class JobDeployRequest(BaseSchema):
    """Job deploy request schema - 用于部署 job，创建 expert_task"""
    task_configs: List[ExpertTaskConfig] = Field(..., description="每个 expert 的任务配置")


class JobInDB(JobBase, TimestampSchema):
    """Job in database schema"""
    job_id: str
    # 关联信息（响应时展示）
    tenant_name: Optional[str] = Field(default=None, description="租户名称")
    activity_name: Optional[str] = Field(default=None, description="活动名称")
    agent_name: Optional[str] = Field(default=None, description="Agent 名称")
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    is_deleted: int = 0


class JobResponse(JobInDB):
    """Job response schema"""
    pass


class JobListResponse(JobListBase, TimestampSchema):
    """Job list response schema - excludes job_generation_plan for performance"""
    job_id: str
    # 关联信息（响应时展示）
    tenant_name: Optional[str] = Field(default=None, description="租户名称")
    activity_name: Optional[str] = Field(default=None, description="活动名称")
    agent_name: Optional[str] = Field(default=None, description="Agent 名称")
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    is_deleted: int = 0


class JobTestRequest(BaseSchema):
    """Job test request schema"""
    experts_plugin_config_snapshot: Optional[Dict[str, List[Dict[str, Any]]]] = Field(
        default=None,
        description="Experts plugin config snapshot, format: {expert_config_code: [{plugin_code, variable_mapping}]}"
    )
    count: int = Field(default=1, ge=1, le=50, description="执行次数")


class JobTestResponse(BaseSchema):
    """Job test response schema"""
    results: Dict[str, Any] = Field(..., description="Test results, key is expert_config_code, value is response_data")


class JobExportRequest(BaseSchema):
    """Job export request schema"""
    format: str = Field(default="json", description="导出格式：json/csv")
    include_details: bool = Field(default=False, description="是否包含详细信息（rendered_prompt, plugin_config_snapshot）")


class JobExportSummary(BaseSchema):
    """Job export summary"""
    total_executions: int = Field(..., description="总执行次数")
    success_count: int = Field(..., description="成功次数")
    failed_count: int = Field(..., description="失败次数")
    timeout_count: int = Field(..., description="超时次数")
    success_rate: float = Field(..., description="成功率")
    total_tokens: int = Field(..., description="总 Token 数")
    total_input_tokens: int = Field(..., description="总输入 Token 数")
    total_output_tokens: int = Field(..., description="总输出 Token 数")
    avg_duration_ms: float = Field(..., description="平均耗时（毫秒）")


class JobExportExecution(BaseSchema):
    """Job export execution item"""
    id: int
    sub_job_id: str
    content_id: Optional[str] = None
    trace_id: str
    span_id: str
    stage: str
    expert_config_code: Optional[str] = None
    expert_type: Optional[str] = None
    status: str
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_ms: Optional[int] = None
    model_code: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    result_summary: Optional[Dict[str, Any]] = None
    rendered_prompt: Optional[str] = None
    plugin_config_snapshot: Optional[Dict[str, Any]] = None


class JobExportResponse(BaseSchema):
    """Job export response schema"""
    job_id: str
    job_name: str
    export_time: str
    summary: JobExportSummary
    executions: list[JobExportExecution]


class JobExecutionListResponse(BaseSchema):
    """Job execution list response"""
    total: int
    page: int
    page_size: int
    items: list[JobExportExecution]

