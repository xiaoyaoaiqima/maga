"""
AB测试相关的Schema定义
统一支持 Expert 维度和 Agent/Job 维度
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


# ========== 对比组相关 ==========

class ABTestGroup(BaseModel):
    """对比组信息"""
    group_name: str = Field(..., description="组名称（如 control, experiment_1）")
    description: Optional[str] = Field(default=None, description="组描述")
    config_snapshot: Optional[Dict[str, Any]] = Field(
        default=None, 
        description="配置快照（model, prompt_version, expert_config等）"
    )


# ========== 创建请求 ==========

class ABTestCreateExpert(BaseModel):
    """创建 Expert 维度 AB 测试"""
    test_name: str = Field(..., description="测试名称")
    debug_history_ids: Dict[str, List[int]] = Field(
        ..., 
        description="调试历史关联，key 为组名，value 为 debug_history_id 数组",
        json_schema_extra={"example": {"control": [101, 103], "experiment_1": [102, 104]}}
    )
    groups: List[ABTestGroup] = Field(
        ..., 
        min_length=2, 
        description="对比组信息（至少2个组）"
    )
    remark: Optional[str] = Field(default=None, description="备注")


class ABTestCreateJob(BaseModel):
    """创建 Job 维度 AB 测试"""
    test_name: str = Field(..., description="测试名称")
    job_ids: Dict[str, str] = Field(
        ..., 
        description="Job 关联，key 为组名，value 为 job_id",
        json_schema_extra={"example": {"control": "job_001", "experiment_1": "job_002"}}
    )
    groups: List[ABTestGroup] = Field(
        ..., 
        min_length=2, 
        description="对比组信息（至少2个组）"
    )
    remark: Optional[str] = Field(default=None, description="备注")


class ABTestUpdate(BaseModel):
    """更新AB测试请求"""
    test_name: Optional[str] = Field(default=None, description="测试名称")
    remark: Optional[str] = Field(default=None, description="备注")


# ========== 指标相关 ==========

class ABTestMetrics(BaseModel):
    """AB测试聚合指标"""
    # 基础性能指标
    avg_time_ms: float = Field(default=0, description="平均执行时间(毫秒)")
    avg_tokens: int = Field(default=0, description="平均Token使用量")
    avg_cost: float = Field(default=0.0, description="平均费用")
    success_rate: float = Field(default=0.0, description="成功率(0-100)")
    run_count: int = Field(default=0, description="执行/样本数")
    
    # 质量指标（来自 critic score）
    avg_score: Optional[float] = Field(default=None, description="平均审核分数")
    pass_rate: Optional[float] = Field(default=None, description="通过率(0-100)")


class CriticScoreDetail(BaseModel):
    """Critic 评分明细"""
    expert_func: str = Field(..., description="Critic 函数名")
    expert_config_code: str = Field(..., description="Expert 配置编码")
    model_code: Optional[str] = Field(default=None, description="模型编码")
    total_count: int = Field(default=0, description="总评分数")
    avg_score: float = Field(default=0, description="平均分")
    pass_count: int = Field(default=0, description="通过数")
    fail_count: int = Field(default=0, description="不通过数")
    pass_rate: float = Field(default=0, description="通过率(0-100)")


class GroupMetricsDetail(BaseModel):
    """组指标详情"""
    group_name: str
    description: Optional[str] = None
    job_id: Optional[str] = Field(default=None, description="Job ID（Job类型时）")
    metrics: ABTestMetrics
    # 样本详情
    sample_ids: List[Any] = Field(default_factory=list, description="样本ID列表（debug_history_id 或 content_id）")
    # Critic 评分明细（Job 类型时有值）
    critic_details: Optional[List[CriticScoreDetail]] = Field(
        default=None, 
        description="各 Critic Expert 的评分明细（仅 Job 类型）"
    )


# ========== 响应 ==========

class ABTestResponse(BaseModel):
    """AB测试响应"""
    id: int
    test_id: str
    test_name: str
    test_type: str  # EXPERT_CONFIG, AGENT_JOB
    
    # 关联数据
    debug_history_ids: Optional[Dict[str, List[int]]] = None
    job_ids: Optional[Dict[str, str]] = None
    
    # 对比组
    groups: List[Dict[str, Any]]
    
    # 统计与结果
    metrics: Optional[Dict[str, Any]] = None
    winner: Optional[str] = None
    recommendation: Optional[str] = None
    
    # 状态
    status: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    create_time: datetime
    update_time: Optional[datetime] = None
    created_by: Optional[str] = None
    remark: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ABTestListResponse(BaseModel):
    """AB测试列表响应"""
    items: List[ABTestResponse]
    total: int
    page: int
    page_size: int


class ABTestDetailResponse(BaseModel):
    """AB测试详情响应（包含各组详细指标）"""
    test: ABTestResponse
    group_details: List[GroupMetricsDetail]  # 各组详细指标
    comparison: Dict[str, Any]  # 对比结论


class ABTestAnalyzeResponse(BaseModel):
    """分析结果响应"""
    test_id: str
    status: str
    message: str
    metrics: Optional[Dict[str, ABTestMetrics]] = None
    winner: Optional[str] = None
    recommendation: Optional[str] = None


# ========== 添加关联请求 ==========

class AddDebugHistoryRequest(BaseModel):
    """向 Expert 测试添加调试历史"""
    group_name: str = Field(..., description="组名称")
    debug_history_ids: List[int] = Field(..., description="要添加的 debug_history_id 列表")


class AddJobRequest(BaseModel):
    """向 Job 测试添加 Job（通常不需要，Job 一般一次性确定）"""
    group_name: str = Field(..., description="组名称")
    job_id: str = Field(..., description="Job ID")


# ========== 执行模式请求（保留原有流程）==========

class ABTestGroupConfig(BaseModel):
    """AB测试组配置（用于执行模式）"""
    group_name: str = Field(..., description="组名称（如 control, experiment_1）")
    config_code: str = Field(..., description="Expert 配置编码")
    config_name: Optional[str] = Field(default=None, description="配置名称")
    variables: Optional[List[Dict[str, Any]]] = Field(default=None, description="变量配置（插件配置快照）")
    model_code: Optional[str] = Field(default=None, description="模型编码")
    llm_config: Optional[Dict[str, Any]] = Field(default=None, description="模型配置覆盖")


class ABTestExecuteExpert(BaseModel):
    """创建并执行 Expert AB 测试（保留原有流程）"""
    test_name: str = Field(..., description="测试名称")
    configs: List[ABTestGroupConfig] = Field(..., min_length=2, description="配置组列表（至少2个）")
    traffic_allocation: Dict[str, int] = Field(
        ..., 
        description="流量分配 {group_name: ratio}，比例之和为100"
    )
    test_content: Optional[str] = Field(default=None, description="测试输入内容")
    execution_count: int = Field(default=5, ge=1, le=50, description="执行次数")
    auto_execute: bool = Field(default=True, description="是否自动执行")
    remark: Optional[str] = Field(default=None, description="备注")


class ABTestExecuteResponse(BaseModel):
    """执行模式响应"""
    test_id: str
    status: str
    message: str
    total_runs: int
    completed_runs: int
