"""
Content schemas
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import Field

from app.schemas.base import BaseSchema


class ContentCreate(BaseSchema):
    """Create Content schema"""
    job_id: str = Field(..., description="job_id")
    sub_job_id: str = Field(..., description="sub_job_id")
    content_id: str = Field(..., description="content_id")
    tenant_id: Optional[int] = Field(default=None, description="租户ID")
    activity_id: Optional[int] = Field(default=None, description="活动ID")
    agent_code: Optional[str] = Field(default=None, description="Agent编码")
    prompt: Optional[str] = Field(default=None, description="prompt")
    context_list: Optional[Dict[str, str]] = Field(
        default=None, 
        description="结构化变量映射，格式: {变量名: 上下文名}，如: {'写者': '通勤战士', '平台': '小红书'}"
    )
    title: Optional[str] = Field(default=None, description="标题")
    content: Optional[str] = Field(default=None, description="正文内容")
    is_valid: Optional[int] = Field(default=None, description="是否有效（0不可用 1可用 null待定）")
    plan_index: Optional[int] = Field(default=None, description="执行计划索引")
    is_test_case: int = Field(default=0, description="是否测试用例")


class ContentUpdate(BaseSchema):
    """Update Content schema"""
    prompt: Optional[str] = None
    context_list: Optional[Dict[str, str]] = None
    title: Optional[str] = None
    content: Optional[str] = None
    is_valid: Optional[int] = None
    is_test_case: Optional[int] = None


class ContentResponse(BaseSchema):
    """Content response schema"""
    id: int
    job_id: str
    sub_job_id: str
    content_id: str
    tenant_id: Optional[int] = None
    activity_id: Optional[int] = None
    agent_code: Optional[str] = None
    prompt: Optional[str] = None
    context_list: Optional[Dict[str, str]] = None
    title: Optional[str] = None
    content: Optional[str] = None
    is_valid: Optional[int] = None
    plan_index: Optional[int] = None
    is_test_case: int
    online_status: str = "OFFLINE"
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============== 上线状态更新 ==============

class ContentOnlineUpdateRequest(BaseSchema):
    """单篇文章上线状态更新请求"""
    content_id: int = Field(..., description="内容表主键ID")
    online_status: str = Field(..., description="状态: ONLINE/OFFLINE")


class ContentBatchOnlineRequest(BaseSchema):
    """批量文章上线状态更新请求

    支持两种模式：
    1. 按任务ID批量更新：更新该任务下所有有效且非测试的文章
    2. 按文章ID列表批量更新：更新指定的文章列表
    """
    job_id: Optional[str] = Field(None, description="任务ID（与content_ids二选一）")
    content_ids: Optional[List[int]] = Field(None, description="文章ID列表（与job_id二选一）")
    online_status: str = Field(..., description="状态: ONLINE/OFFLINE")


class ContentBatchValidUpdateRequest(BaseSchema):
    """批量更新文章有效状态请求"""
    content_ids: List[int] = Field(..., description="文章ID列表（主键）")
    is_valid: int = Field(..., description="有效状态：0=无效，1=有效")


# ============== 评分筛选 ==============

class ExpertScoreFilter(BaseSchema):
    """专家评分筛选条件"""
    expert_config_code: str = Field(..., description="专家配置编码")
    min_score: Optional[int] = Field(None, description="最小值(CRITIC类型)")
    max_score: Optional[int] = Field(None, description="最大值(CRITIC类型)")
    passed: Optional[bool] = Field(None, description="是否通过(BAN类型)")


# ============== 内容匹配/锁定（按 agent + user_tags）==============

class MatchedContentItem(BaseSchema):
    """匹配到的内容（最小字段）"""
    content_id: int = Field(..., description="内容ID")
    title: str = Field("", description="标题")
    content: str = Field("", description="正文内容")


class TagInfo(BaseSchema):
    """标签信息"""
    tag_name: str = Field(..., description="标签名称")
    tag_weight: float = Field(..., description="标签权重")


class ContentMatchRequest(BaseSchema):
    """获取并锁定内容请求"""
    agent_id: Optional[int] = Field(default=None, description="Agent ID")
    agent_id_list: Optional[List[int]] = Field(default=None, description="Agent ID列表，请求多个agent的时候添加")
    user_id: str = Field(..., description="用户ID（用于锁定）")
    user_tags: List[TagInfo] = Field(..., description="用户标签（用于匹配）")
    count: Optional[int] = Field(default=3, description="获取文章数量")
    lock_minutes: Optional[int] = Field(default=10, description="文章锁定时长（分钟）")


class ContentMatchResponse(BaseSchema):
    """获取并锁定内容响应（按需求的返回结构）"""
    contents: List[MatchedContentItem] = Field(default_factory=list)
    success: bool = Field(True, description="是否成功")
    message: str = Field("", description="提示信息")


# ============== 内容使用 ==============

class ContentUseRequest(BaseSchema):
    """使用内容请求"""
    content_id: int = Field(..., description="内容表主键ID")
    user_id: str = Field(..., description="用户ID")


class ContentUseResponse(BaseSchema):
    """使用内容响应"""
    content_id: int = Field(..., description="内容表主键ID")
    title: Optional[str] = Field(None, description="标题")
    content: Optional[str] = Field(None, description="正文")
    success: bool = Field(True, description="是否成功")
    message: str = Field("", description="提示信息")


# ============== CSV 导入 ==============

class ContentImportResponse(BaseSchema):
    """CSV 导入响应"""
    success_count: int = Field(..., description="成功导入数量")
    failed_count: int = Field(0, description="失败数量")
    job_id: str = Field(..., description="生成的 job_id")
    errors: Optional[List[str]] = Field(None, description="错误信息列表")


# ============== 统计数据 ==============

class ContentStatsResponse(BaseSchema):
    """文章统计数据响应"""
    total: int = Field(..., description="文章总数")
    valid: int = Field(..., description="有效文章数 (is_valid = 1)")
    invalid: int = Field(..., description="无效文章数 (is_valid = 0)")
    pending: int = Field(..., description="待定文章数 (is_valid is null)")
    test: int = Field(..., description="测试文章数 (is_test_case = 1)")
    formal_valid: int = Field(..., description="正式有效文章数 (is_valid = 1 and is_test_case = 0)")
    online: int = Field(..., description="上线文章数 (online_status = 'ONLINE' and is_valid = 1 and is_test_case = 0)")
    locked: int = Field(..., description="锁定文章数 (is_locked = 1 and (lock_expire_time > now() or is_used = 1))")
    unlocked: int = Field(..., description="未被锁定文章数 (online - locked)")
    used: int = Field(..., description="被使用文章数 (is_used = 1)")
    unused: int = Field(..., description="未被使用文章数 (online - used)")

