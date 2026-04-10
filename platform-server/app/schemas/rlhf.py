from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

# --- Issue Tag Schemas ---

class RLHFIssueTagBase(BaseModel):
    tag_code: str = Field(..., description="标签编码")
    tag_name: str = Field(..., description="标签名称")
    tag_category: Optional[str] = Field(None, description="标签分类：CONTENT/MODEL/BRAND/COMPLIANCE/OTHER")
    description: Optional[str] = None
    enabled: int = Field(1, description="是否启用：0禁用 1启用")
    sort_order: int = Field(0, description="排序")

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

class RLHFIssueTagCreate(RLHFIssueTagBase):
    pass

class RLHFIssueTagUpdate(BaseModel):
    tag_name: Optional[str] = None
    tag_category: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[int] = None
    sort_order: Optional[int] = None

class RLHFIssueTagOut(RLHFIssueTagBase):
    id: int
    use_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

# --- Operation History Schemas ---

class RLHFOperationHistoryOut(BaseModel):
    id: int
    feedback_id: int
    operation_type: str
    before_value: Optional[Dict[str, Any]] = None
    after_value: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    improvement_suggestion: Optional[str] = None
    operator_id: str
    operator_name: Optional[str] = None
    operation_time: datetime

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

# --- Feedback Schemas ---

class RLHFFeedbackBase(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    modified_title: Optional[str] = None
    modified_content: Optional[str] = None
    
    ge_expert_code: Optional[str] = None
    ag_expert_codes: Optional[List[str]] = None
    model_code: Optional[str] = None
    
    like_status: int = 0
    like_reason: Optional[str] = None
    adopt_status: int = 0
    adopt_reason: Optional[str] = None
    discard_reason_type: Optional[str] = None
    discard_comment: Optional[str] = None
    improvement_suggestion: Optional[str] = None
    
    content_score: float = 0
    model_score: float = 0
    
    issue_tag_ids: Optional[List[int]] = None
    custom_issue_tags: Optional[List[str]] = None
    
    annotations: Optional[List[Dict[str, Any]]] = None
    
    review_status: str = "PENDING"
    inspection_comment: Optional[str] = None
    inspection_user_id: Optional[str] = None
    inspection_user_name: Optional[str] = None
    inspection_time: Optional[datetime] = None
    
    model_config = ConfigDict(protected_namespaces=())

class RLHFFeedbackCreate(BaseModel):
    job_id: str
    sub_job_id: str
    content_id: str
    trace_id: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    ge_expert_code: Optional[str] = None
    model_code: Optional[str] = None
    review_status: str = "PENDING"
    created_by: Optional[str] = None

    model_config = ConfigDict(protected_namespaces=())

class RLHFFeedbackUpdate(BaseModel):
    modified_title: Optional[str] = None
    modified_content: Optional[str] = None
    annotations: Optional[List[Dict[str, Any]]] = None
    # AI 意见和标签（支持自动保存）
    improvement_suggestion: Optional[str] = Field(None, description="AI 生成的修改意见")
    issue_tag_names: Optional[List[str]] = Field(None, description="问题标签名称列表")

    model_config = ConfigDict(protected_namespaces=())

class RLHFFeedbackOut(RLHFFeedbackBase):
    id: int
    job_id: str
    sub_job_id: str
    content_id: str
    trace_id: Optional[str] = None
    
    modify_count: int = 0
    
    like_user_id: Optional[str] = None
    like_user_name: Optional[str] = None
    like_time: Optional[datetime] = None
    
    adopt_user_id: Optional[str] = None
    adopt_user_name: Optional[str] = None
    adopt_time: Optional[datetime] = None
    
    is_locked: int = 0
    lock_user_id: Optional[str] = None
    lock_user_name: Optional[str] = None
    lock_time: Optional[datetime] = None
    lock_expire_time: Optional[datetime] = None
    
    created_at: datetime
    updated_at: datetime
    
    # 审核人信息
    review_user_id: Optional[str] = None
    review_user_name: Optional[str] = None
    review_time: Optional[datetime] = None
    
    # 抽检相关
    inspection_status: Optional[str] = "PENDING"
    inspection_result: Optional[str] = None
    inspection_comment: Optional[str] = None
    inspection_user_id: Optional[str] = None
    inspection_user_name: Optional[str] = None
    inspection_time: Optional[datetime] = None
    
    # 上下文变量 (从 Content 表关联获取)
    context_list: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

# --- Operation Request Schemas ---

class RLHFLikeRequest(BaseModel):
    status: int = Field(..., description="1: 喜欢, -1: 不喜欢")
    reason: str = Field(..., min_length=30, description="原因（≥30字）")
    improvement_suggestion: Optional[str] = Field(None, description="改进建议（不喜欢时必填）")

class RLHFAdoptRequest(BaseModel):
    status: int = Field(..., description="1: 采纳, -1: 不采纳, 2: 废弃")
    reason: str = Field(..., min_length=30, description="原因（≥30字）")
    discard_reason_type: Optional[str] = None
    improvement_suggestion: Optional[str] = Field(None, description="改进建议（不采纳时必填）")

class RLHFScoreRequest(BaseModel):
    content_score: float = Field(..., ge=1, le=10, description="内容评分(1-10)")
    model_score: float = Field(..., ge=1, le=10, description="模型评分(1-10)")
    issue_tag_ids: Optional[List[int]] = None
    custom_issue_tags: Optional[List[str]] = None
    modified_title: Optional[str] = None
    modified_content: Optional[str] = None
    
    model_config = ConfigDict(protected_namespaces=())

class RLHFTagRequest(BaseModel):
    issue_tag_ids: Optional[List[int]] = None
    custom_issue_tags: Optional[List[str]] = None

class RLHFInspectionRequest(BaseModel):
    result: str = Field(..., description="PASSED 或 FAILED")
    comment: Optional[str] = Field(None, description="抽检意见")
    issue_tag_names: Optional[List[str]] = Field(None, description="问题标签名称列表（可选，支持自动新增）")

    model_config = ConfigDict(protected_namespaces=())

class RLHFSummaryRequest(BaseModel):
    comment: Optional[str] = Field(None, description="抽检人填写的初步修改意见")

    model_config = ConfigDict(protected_namespaces=())

class RLHFSummaryResponse(BaseModel):
    tags: List[str] = Field(..., description="AI 建议的问题标签")

    model_config = ConfigDict(protected_namespaces=())


class RLHFSummarizeCommentRequest(BaseModel):
    """AI 总结意见请求"""
    model_code: str = Field("gpt-4o", description="使用的模型编码")

    model_config = ConfigDict(protected_namespaces=())


class RLHFSummarizeCommentResponse(BaseModel):
    """AI 总结意见响应"""
    comment: str = Field(..., description="AI 生成的修改意见")

    model_config = ConfigDict(protected_namespaces=())

class RLHFLockResponse(BaseModel):
    success: bool
    message: str
    lock_expire_time: Optional[datetime] = None


# --- Stats Schemas ---

class RLHFStatsSummary(BaseModel):
    total_count: int
    pending_count: int
    completed_count: int
    like_rate: float
    adopt_rate: float
    avg_content_score: float
    
class RLHFReviewerStats(BaseModel):
    reviewer_id: str
    reviewer_name: str
    total_count: int
    like_count: int
    adopt_count: int
    avg_score: float

class RLHFDailyStatsOut(BaseModel):
    stat_date: str
    total_count: int
    like_rate: float
    adopt_rate: float
    avg_content_score: float
    
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

