"""Chat API schemas."""
from typing import Any, Literal

from pydantic import BaseModel, Field, constr


class ChatHistoryMessage(BaseModel):
    """前端当前会话内的历史消息。"""

    role: Literal["user", "assistant"] = Field(..., description="消息角色")
    content: constr(strip_whitespace=True, min_length=1) = Field(..., description="消息内容")


class ChatContext(BaseModel):
    """页面传给 Chat 的业务上下文。"""

    page: str | None = Field(default=None, description="页面标识")
    asset_key: str | None = Field(default=None, description="业务规则 asset key")
    asset_type: str | None = Field(default=None, description="业务规则 asset type")
    asset_version: int | str | None = Field(default=None, description="业务规则版本")
    rule_id: str | None = Field(default=None, description="单条规则 ID")
    source_row_no: int | None = Field(default=None, description="源表行号")
    business_rule: str | None = Field(default=None, description="业务规则")
    corpus: str | None = Field(default=None, description="正式语料")
    draft_corpus: str | None = Field(default=None, description="当前草稿语料")
    examples: list[str] = Field(default_factory=list, description="已有示例")
    supplements: list[str] = Field(default_factory=list, description="历史补充示例，兼容字段")
    test_report_summary: dict[str, Any] | None = Field(default=None, description="最近测试报告摘要")


class ChatAction(BaseModel):
    """Chat 可返回给前端执行的安全动作。"""

    type: Literal["fill_business_rule_draft", "fill_business_rule_examples"] = Field(..., description="动作类型")
    label: str = Field(default="填入草稿", description="按钮文案")
    payload: dict[str, Any] = Field(default_factory=dict, description="动作参数")


class ChatMessageRequest(BaseModel):
    """发送聊天消息请求。"""

    message: constr(strip_whitespace=True, min_length=1) = Field(..., description="用户消息")
    history: list[ChatHistoryMessage] = Field(default_factory=list, description="当前前端会话历史")
    context: ChatContext | None = Field(default=None, description="页面上下文；首版仅业务规则副驾使用")


class ChatMessageResponse(BaseModel):
    """聊天消息响应。"""

    agent_code: str = Field(..., description="Agent 编码")
    agent_name: str = Field(..., description="Agent 名称")
    reply: str = Field(..., description="模型回复")
    actions: list[ChatAction] = Field(default_factory=list, description="前端可展示的安全动作")
