"""
Expert Eval schemas (test_set / test_case / expert_eval_run / expert_eval_result)
"""

from typing import Optional, Literal

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampSchema


# ==================== TestSet Schemas ====================

TestSetType = Literal["text", "image"]


class TestSetItem(TimestampSchema):
    """测试集详情"""
    id: int = Field(..., description="主键")
    code: str = Field(..., description="唯一编码")
    name: str = Field(..., description="测试集名称")
    type: TestSetType = Field(..., description="类型: text/image")
    description: Optional[str] = Field(None, description="描述")
    enabled: int = Field(..., description="是否启用(1/0)")
    case_count: int = Field(default=0, description="测试用例数量")


class TestSetListResponse(BaseSchema):
    """测试集列表响应"""
    items: list[TestSetItem]
    total: int
    page: int
    page_size: int


class TestSetCreate(BaseSchema):
    """创建测试集"""
    code: Optional[str] = Field(None, description="唯一编码（不填则自动生成）", max_length=64)
    name: str = Field(..., description="测试集名称", min_length=1, max_length=128)
    type: TestSetType = Field(default="text", description="类型: text/image")
    description: Optional[str] = Field(None, description="描述", max_length=500)
    enabled: int = Field(default=1, description="是否启用(1/0)")


class TestSetUpdate(BaseSchema):
    """更新测试集"""
    name: Optional[str] = Field(None, description="测试集名称", max_length=128)
    description: Optional[str] = Field(None, description="描述", max_length=500)
    enabled: Optional[int] = Field(None, description="是否启用(1/0)")


class TestSetDetail(TestSetItem):
    """测试集详情（含统计）"""
    pass


# ==================== TestCase Schemas ====================

class TestCaseItem(TimestampSchema):
    """测试用例详情"""
    id: int = Field(..., description="主键")
    test_set_code: str = Field(..., description="测试集编码")
    title: Optional[str] = Field(None, description="标题")
    content: Optional[str] = Field(None, description="正文（文本类型）")
    image_url: Optional[str] = Field(None, description="图片URL（图片类型）")
    enabled: int = Field(..., description="是否启用(1/0)")


class TestCaseListResponse(BaseSchema):
    """测试用例列表响应"""
    items: list[TestCaseItem]
    total: int
    page: int
    page_size: int


class TestCaseCreate(BaseSchema):
    """创建测试用例"""
    test_set_code: str = Field(..., description="测试集编码", max_length=64)
    title: Optional[str] = Field(None, description="标题", max_length=512)
    content: Optional[str] = Field(None, description="正文（文本类型）")
    image_url: Optional[str] = Field(None, description="图片URL（图片类型）", max_length=1024)
    enabled: int = Field(default=1, description="是否启用(1/0)")


class TestCaseUpdate(BaseSchema):
    """更新测试用例"""
    title: Optional[str] = Field(None, description="标题", max_length=512)
    content: Optional[str] = Field(None, description="正文（文本类型）")
    image_url: Optional[str] = Field(None, description="图片URL（图片类型）", max_length=1024)
    enabled: Optional[int] = Field(None, description="是否启用(1/0)")


class TestCaseImportItem(BaseSchema):
    """批量导入单条"""
    title: Optional[str] = Field(None, description="标题", max_length=512)
    content: Optional[str] = Field(None, description="正文（文本类型）")
    image_url: Optional[str] = Field(None, description="图片URL（图片类型）", max_length=1024)


class TestCaseImportRequest(BaseSchema):
    """批量导入请求"""
    test_set_code: str = Field(..., description="测试集编码", max_length=64)
    items: list[TestCaseImportItem] = Field(..., description="测试用例列表", min_length=1)
    enabled: int = Field(default=1, description="是否启用(1/0)")


class TestCaseImportResponse(BaseSchema):
    """批量导入响应"""
    success_count: int = Field(..., description="成功导入数量")
    skip_count: int = Field(..., description="跳过（重复）数量")
    total: int = Field(..., description="总数量")


EvalRunStatus = Literal["running", "success", "failed", "cancelled"]


class EvalRunItem(BaseSchema):
    id: int
    run_code: str
    expert_config_code: str
    test_set_code: Optional[str] = None
    status: EvalRunStatus
    total_count: int
    success_count: int
    failed_count: int
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    created_by: Optional[str] = None


class EvalRunListResponse(BaseSchema):
    items: list[EvalRunItem]
    total: int
    page: int
    page_size: int


class CreateEvalRunRequest(BaseSchema):
    expert_config_code: str
    test_set_code: Optional[str] = None
    test_case_ids: Optional[list[int]] = None
    max_count: Optional[int] = Field(default=50, ge=1, le=5000)
    # 1-based 范围（按当前数据集默认排序：create_time DESC）
    start_no: Optional[int] = Field(default=None, ge=1, description="第几篇开始（包含）")
    end_no: Optional[int] = Field(default=None, ge=1, description="第几篇结束（包含）")
    article_concurrency: Optional[int] = Field(default=4, ge=1, le=200)


class CreateEvalRunResponse(BaseSchema):
    run_id: int
    run_code: str


class EvalResultItem(BaseSchema):
    id: int
    run_id: int
    test_case_id: int
    score: Optional[int] = None
    reason: Optional[str] = None
    highlights: Optional[str] = None
    problem_tags: Optional[list[str]] = None
    problem_snippets: Optional[list[str]] = None
    success: bool
    error_message: Optional[str] = None
    latency_ms: Optional[int] = None
    model_code: Optional[str] = None
    trace_id: Optional[str] = None
    create_time: Optional[str] = None


class EvalResultListResponse(BaseSchema):
    items: list[EvalResultItem]
    total: int
    page: int
    page_size: int


class EvalResultDetailTestCase(BaseSchema):
    id: int
    test_set_code: str
    title: Optional[str] = None
    content: Optional[str] = None
    image_url: Optional[str] = None


class EvalResultDetailResponse(BaseSchema):
    id: int
    run_id: int
    test_case_id: int
    score: Optional[int] = None
    reason: Optional[str] = None
    highlights: Optional[str] = None
    problem_tags: Optional[list[str]] = None
    problem_snippets: Optional[list[str]] = None
    success: bool
    error_message: Optional[str] = None
    latency_ms: Optional[int] = None
    model_code: Optional[str] = None
    provider_code: Optional[str] = None
    token_usage: Optional[dict] = None
    trace_id: Optional[str] = None
    rendered_prompt: Optional[str] = None
    raw_output: Optional[dict] = None
    create_time: Optional[str] = None

    test_case: Optional[EvalResultDetailTestCase] = None

