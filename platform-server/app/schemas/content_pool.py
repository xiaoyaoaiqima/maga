"""
Content Pool Schemas
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import Field, BaseModel

from app.schemas.base import BaseSchema, ResponseData


class ContentAcquireRequest(BaseSchema):
    """请求获取内容参数"""
    activity_code: str = Field(..., description="活动编码")
    external_order_id: str = Field(..., description="外部请求ID（幂等）")
    count: int = Field(..., ge=1, le=100, description="需求数量")
    agent_code: Optional[str] = Field(None, description="指定 Agent")
    min_score: Optional[int] = Field(60, ge=0, le=100, description="最低质量分")
    required_tags: Optional[List[str]] = Field(None, description="必须包含的标签")


class ContentItem(BaseSchema):
    """内容项"""
    content_id: str
    title: Optional[str]
    text: Optional[str] = Field(..., alias="content") # Map DB 'content' to 'text' or keep content
    images: Optional[List[str]] = Field(default=[], description="图片列表")
    quality_score: int
    tags: Optional[Dict[str, Any]]
    lock_expire_at: Optional[datetime] = Field(None, description="锁过期时间")

    class Config:
        from_attributes = True
        populate_by_name = True


class ContentAcquireResponse(BaseSchema):
    """获取内容响应"""
    acquired_count: int
    contents: List[ContentItem]


class ContentAckRequest(BaseSchema):
    """确认消费参数"""
    content_ids: List[str] = Field(..., description="内容ID列表")


class ContentAckResponse(BaseSchema):
    """确认消费响应"""
    success_count: int


class ContentAvailabilityResponse(BaseSchema):
    """库存查询响应"""
    available_count: int


class ContentTransferRequest(BaseSchema):
    """文章转移请求参数"""
    # source_agent_code 和 target_agent_code 通过 Query 参数传递，不在 Body 中
    content_ids: Optional[List[str]] = Field(None, description="要转移的文章 ID 列表（为空则按条件筛选转移）")
    # 筛选条件（当 content_ids 为空时使用）
    tenant_id: Optional[int] = Field(None, description="租户 ID")
    activity_id: Optional[int] = Field(None, description="活动 ID")
    job_id: Optional[str] = Field(None, description="任务 ID")
    is_valid: Optional[int] = Field(None, description="是否有效（0=无效，1=有效）")
    is_test_case: Optional[int] = Field(None, description="是否测试用例（0=业务，1=测试）")
    online_status: Optional[str] = Field(None, description="上线状态（ONLINE/OFFLINE）")
    # 转移限制
    max_count: Optional[int] = Field(1000, ge=1, le=10000, description="最多转移数量（按条件筛选时生效）")
    skip_locked: bool = Field(True, description="是否跳过已锁定的文章")
    skip_used: bool = Field(True, description="是否跳过已使用的文章")


class ContentTransferResponse(BaseSchema):
    """文章转移响应"""
    success_count: int = Field(..., description="成功转移数量")
    skipped_locked_count: int = Field(..., description="跳过已锁定数量")
    skipped_used_count: int = Field(..., description="跳过已使用数量")
    failed_count: int = Field(..., description="失败数量")
    skipped_content_ids: Optional[List[str]] = Field(None, description="被跳过的文章 ID 列表")

