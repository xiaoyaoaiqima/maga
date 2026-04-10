"""
Trace 相关的 Pydantic Schemas

用于 API 请求/响应的数据验证
"""
from datetime import datetime, date
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field, ConfigDict


# ============ ExpertCallTrace Schemas ============

class TraceSpanCreate(BaseModel):
    """创建追踪 Span 的请求"""
    # 三层标识
    job_id: str = Field(..., description="Job ID")
    sub_job_id: str = Field(..., description="Sub Job ID")
    content_id: Optional[str] = Field(None, description="内容ID")
    trace_id: str = Field(..., description="请求追踪ID")
    span_id: str = Field(..., description="调用ID")
    parent_span_id: Optional[str] = Field(None, description="父调用ID")
    
    # 调用信息
    stage: str = Field(..., description="阶段")
    expert_config_code: Optional[str] = Field(None, description="Expert 编码")
    expert_type: Optional[str] = Field(None, description="Expert 类型")
    service_app: str = Field(..., description="目标服务")
    service_method: str = Field(..., description="调用方法")
    
    # 执行状态
    status: str = Field(..., description="状态")
    error_type: Optional[str] = Field(None, description="错误类型")
    error_message: Optional[str] = Field(None, description="错误信息")
    
    # 时间信息
    start_time_ms: int = Field(..., description="开始时间（毫秒时间戳）")
    end_time_ms: Optional[int] = Field(None, description="结束时间（毫秒时间戳）")
    duration_ms: Optional[int] = Field(None, description="耗时（毫秒）")
    
    # Token 统计
    model_code: Optional[str] = Field(None, description="模型编码")
    provider_code: Optional[str] = Field(None, description="Provider 编码")
    input_tokens: int = Field(0, description="输入 Token 数")
    output_tokens: int = Field(0, description="输出 Token 数")
    total_tokens: int = Field(0, description="总 Token 数")
    
    # 成本信息
    input_cost: Optional[float] = Field(0.0, description="输入成本")
    output_cost: Optional[float] = Field(0.0, description="输出成本")
    total_cost: Optional[float] = Field(0.0, description="总成本")
    currency: Optional[str] = Field("USD", description="计价币种")
    
    # 实验信息
    experiment_id: Optional[str] = Field(None, description="实验ID")
    experiment_group: Optional[str] = Field(None, description="实验分组")
    experiment_variant: Optional[str] = Field(None, description="实验变体")
    
    # 结果
    result_summary_json: Optional[str] = Field(None, description="结果摘要 JSON")
    
    # 源数据
    source_log_id: Optional[str] = Field(None, description="源日志ID")
    source_log_table: Optional[str] = Field(None, description="源日志表")


class TraceSpanResponse(BaseModel):
    """追踪 Span 响应"""
    id: int
    job_id: str
    sub_job_id: str
    content_id: Optional[str]
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    stage: str
    expert_config_code: Optional[str]
    expert_type: Optional[str]
    service_app: str
    service_method: str
    status: str
    error_type: Optional[str]
    error_message: Optional[str]
    start_time: datetime
    end_time: Optional[datetime]
    duration_ms: Optional[int]
    # 细粒度时间指标
    queue_time_ms: Optional[int] = None
    model_time_ms: Optional[int] = None
    render_time_ms: Optional[int] = None
    # 模型和 Token 信息
    model_code: Optional[str]
    model_provider: Optional[str] = None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    experiment_id: Optional[str]
    experiment_group: Optional[str]
    result_summary: Optional[dict]
    plugin_config_snapshot: Optional[list] = None
    rendered_prompt: Optional[str] = None
    created_at: Optional[datetime]
    
    # 成本信息
    input_cost: Optional[float] = None
    output_cost: Optional[float] = None
    total_cost: Optional[float] = None
    currency: Optional[str] = None
    
    # RLHF 扩展字段
    rlhf_feedback_id: Optional[int] = None
    reviewer_id: Optional[str] = None
    reviewer_name: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class TraceListQuery(BaseModel):
    """追踪列表查询参数"""
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页数量")
    job_id: Optional[str] = Field(None, description="Job ID 筛选")
    sub_job_id: Optional[str] = Field(None, description="Sub Job ID 筛选")
    content_id: Optional[str] = Field(None, description="内容ID 筛选")
    trace_id: Optional[str] = Field(None, description="Trace ID 筛选")
    stage: Optional[str] = Field(None, description="阶段筛选")
    status: Optional[str] = Field(None, description="状态筛选")
    expert_config_code: Optional[str] = Field(None, description="Expert 编码筛选")
    experiment_id: Optional[str] = Field(None, description="实验ID 筛选")
    start_date: Optional[date] = Field(None, description="开始日期")
    end_date: Optional[date] = Field(None, description="结束日期")


class TraceListResponse(BaseModel):
    """追踪列表响应"""
    total: int
    page: int
    page_size: int
    items: List[TraceSpanResponse]


class TraceDetailResponse(BaseModel):
    """追踪详情响应（含完整链路）"""
    trace: TraceSpanResponse
    spans: List[TraceSpanResponse] = Field(default_factory=list, description="同一 trace_id 下的所有 span")
    
    class Config:
        from_attributes = True


class TraceStatsQuery(BaseModel):
    """追踪统计查询参数"""
    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    stage: Optional[str] = Field(None, description="阶段筛选")
    expert_config_code: Optional[str] = Field(None, description="Expert 编码筛选")
    experiment_id: Optional[str] = Field(None, description="实验ID 筛选")
    group_by: str = Field("date", description="分组维度：date/stage/expert/experiment")


class TraceStatsItem(BaseModel):
    """单条统计数据"""
    dimension: str = Field(..., description="维度值")
    total_count: int = Field(0, description="总调用数")
    success_count: int = Field(0, description="成功数")
    failed_count: int = Field(0, description="失败数")
    timeout_count: int = Field(0, description="超时数")
    success_rate: float = Field(0, description="成功率")
    avg_duration_ms: Optional[float] = Field(None, description="平均耗时")
    total_tokens: int = Field(0, description="总 Token 数")


class TraceStatsResponse(BaseModel):
    """追踪统计响应"""
    start_date: date
    end_date: date
    group_by: str
    items: List[TraceStatsItem]
    summary: TraceStatsItem = Field(..., description="汇总数据")


# ============ ABExperiment Schemas ============

class ExperimentGroupConfig(BaseModel):
    """实验分组配置"""
    group: str = Field(..., description="分组名称")
    weight: int = Field(..., ge=0, le=100, description="权重")
    variant: Optional[str] = Field(None, description="变体标识")


class ABExperimentCreate(BaseModel):
    """创建 A/B 实验"""
    experiment_name: str = Field(..., min_length=1, max_length=128, description="实验名称")
    description: Optional[str] = Field(None, description="实验描述")
    target_type: str = Field(..., description="目标类型")
    target_code: Optional[str] = Field(None, description="目标编码")
    groups: List[ExperimentGroupConfig] = Field(..., min_length=1, description="分组配置")
    traffic_ratio: int = Field(100, ge=0, le=100, description="流量占比")
    metrics_config: Optional[dict] = Field(None, description="指标配置")


class ABExperimentUpdate(BaseModel):
    """更新 A/B 实验"""
    experiment_name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = None
    groups: Optional[List[ExperimentGroupConfig]] = None
    traffic_ratio: Optional[int] = Field(None, ge=0, le=100)
    metrics_config: Optional[dict] = None


class ABExperimentResponse(BaseModel):
    """A/B 实验响应"""
    id: int
    experiment_id: str
    experiment_name: str
    description: Optional[str]
    target_type: str
    target_code: Optional[str]
    groups: List[dict]
    traffic_ratio: int
    status: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    metrics_config: Optional[dict]
    created_by: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class ABExperimentListResponse(BaseModel):
    """A/B 实验列表响应"""
    total: int
    items: List[ABExperimentResponse]


class ExperimentResultItem(BaseModel):
    """实验结果项"""
    group: str
    variant: Optional[str]
    total_count: int
    success_count: int
    success_rate: float
    avg_duration_ms: Optional[float]
    total_tokens: int
    avg_tokens: Optional[float]


class ABExperimentResultResponse(BaseModel):
    """A/B 实验结果响应"""
    experiment: ABExperimentResponse
    start_date: date
    end_date: date
    results: List[ExperimentResultItem]
    winner: Optional[str] = Field(None, description="胜出分组")
    confidence: Optional[float] = Field(None, description="置信度")


# ============ TraceDailyStats Schemas ============

class TraceDailyStatsResponse(BaseModel):
    """每日统计响应"""
    id: int
    stat_date: date
    stage: str
    expert_config_code: Optional[str]
    experiment_id: Optional[str]
    experiment_group: Optional[str]
    total_count: int
    success_count: int
    failed_count: int
    timeout_count: int
    success_rate: float
    avg_duration_ms: Optional[float]
    p50_duration_ms: Optional[float]
    p95_duration_ms: Optional[float]
    p99_duration_ms: Optional[float]
    total_input_tokens: int
    total_output_tokens: int
    avg_input_tokens: Optional[float]
    avg_output_tokens: Optional[float]
    total_cost: Optional[float] = None
    avg_cost: Optional[float] = None
    currency: str
    
    class Config:
        from_attributes = True


# ============ 历史兼容 Schemas ============

class ReportTraceSpanRequest(BaseModel):
    """历史兼容：追踪上报请求（旧回调协议，当前统一走 HTTP）"""
    # 三层标识
    job_id: str
    sub_job_id: str
    content_id: Optional[str] = None
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    
    # 调用信息
    stage: str
    status: str
    expert_config_code: Optional[str] = None
    service_app: Optional[str] = None
    service_method: Optional[str] = None
    
    # 时间
    start_time_ms: Optional[int] = None
    end_time_ms: Optional[int] = None
    duration_ms: Optional[int] = None
    
    # Token
    model_code: Optional[str] = None
    provider_code: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    
    # 成本信息
    input_cost: Optional[float] = Field(0.0, description="输入成本")
    output_cost: Optional[float] = Field(0.0, description="输出成本")
    total_cost: Optional[float] = Field(0.0, description="总成本")
    currency: Optional[str] = Field("USD", description="计价币种")
    
    # 实验
    experiment_id: Optional[str] = None
    experiment_group: Optional[str] = None
    experiment_variant: Optional[str] = None
    
    # 结果
    result_summary_json: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    
    # 源数据
    source_log_id: Optional[str] = None
    source_log_table: Optional[str] = None


class BatchReportTraceSpansRequest(BaseModel):
    """历史兼容：批量追踪上报请求"""
    spans: List[ReportTraceSpanRequest]


class ReportTraceSpanResponse(BaseModel):
    """追踪上报响应"""
    success: bool
    message: Optional[str] = None
    trace_id: Optional[int] = None


# ============ Generation Context Schemas ============

class BusinessBackground(BaseModel):
    """业务背景信息"""
    job_name: str
    job_description: Optional[str] = None
    agent_code: Optional[str] = None
    tenant_id: Optional[int] = None
    activity_id: Optional[int] = None
    platform_code: Optional[str] = None
    brand_id: Optional[int] = None
    campaign_id: Optional[int] = None
    extra_context: Optional[dict] = None


class GenerationDetail(BaseModel):
    """生成详情"""
    expert_config_code: Optional[str] = None
    model_code: Optional[str] = None
    rendered_prompt: Optional[str] = None
    result_summary: Optional[dict] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    duration_ms: int = 0
    total_cost: float = 0.0
    currency: Optional[str] = None


class ExpertResultSummary(BaseModel):
    """Expert 执行结果摘要（用于生成背景溯源）"""
    id: int
    expert_config_code: str
    expert_config_name: Optional[str] = None
    expert_func: Optional[str] = None
    expert_type: Optional[str] = None
    model_code: Optional[str] = None
    business_type: Optional[str] = None
    plugin_config_snapshot: Optional[List[Any]] = None
    prompt: Optional[str] = None
    business_result: Optional[Any] = None
    status: Optional[str] = None
    error_message: Optional[str] = None
    create_time: Optional[datetime] = None


class GenerationContextResponse(BaseModel):
    """生成背景完整响应"""
    content_id: str
    job_id: str
    background: BusinessBackground
    generation: Optional[GenerationDetail] = None
    spans: List[TraceSpanResponse] = []
    expert_results: List[ExpertResultSummary] = []


# ============ Admin Backfill Schemas ============

class TraceCostRecalcRequest(BaseModel):
    """管理：按 DB 定价回算 trace 成本（分批游标）"""

    start_time: Optional[datetime] = Field(None, description="开始时间（包含）")
    end_time: Optional[datetime] = Field(None, description="结束时间（不包含）")

    batch_size: int = Field(2000, ge=1, le=20000, description="每批处理数量")
    last_id: int = Field(0, ge=0, description="游标：仅处理 id > last_id")

    dry_run: bool = Field(False, description="仅计算不落库")
    only_if_price_found: bool = Field(True, description="仅在 DB 命中定价时才覆盖成本字段")


class TraceCostRecalcSummary(BaseModel):
    """回算结果摘要（便于对账）"""

    processed: int = Field(0, description="本批读取的记录数")
    updated: int = Field(0, description="本批实际更新的记录数")
    missing_price: int = Field(0, description="本批缺失定价的记录数（按 only_if_price_found 策略可能未更新）")

    next_last_id: Optional[int] = Field(None, description="用于下一批调用的游标；为空表示已处理完")

    old_total_cost_sum: str = Field("0", description="旧总成本之和（字符串，避免浮点误差）")
    new_total_cost_sum: str = Field("0", description="新总成本之和（字符串，避免浮点误差）")
    delta_total_cost_sum: str = Field("0", description="新旧差值之和（字符串）")

    missing_price_top: Dict[str, int] = Field(default_factory=dict, description="缺失定价 Top（key=provider|model）")


class TraceDailyStatsRebuildRequest(BaseModel):
    """管理：重建 trace_daily_stats（按日）"""

    start_date: date = Field(..., description="开始日期（包含）")
    end_date: date = Field(..., description="结束日期（包含）")


class TraceDailyStatsRebuildSummary(BaseModel):
    """重建每日聚合结果摘要"""

    start_date: date
    end_date: date
    days: int = Field(0, description="处理天数")
    total_rows_affected: int = Field(0, description="累计插入/更新行数（rowcount 求和）")

