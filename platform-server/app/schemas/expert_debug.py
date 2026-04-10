"""
Expert 调试相关的 Schema
"""
from datetime import datetime
from typing import Optional, Dict, Any, List

from pydantic import Field

from app.schemas.base import BaseSchema


class ExpertDebugRequest(BaseSchema):
    """Expert 调试请求"""
    expert_config_code: str = Field(..., description="要调试的 expert_config_code")
    content: str = Field(..., description="测试内容")
    plugin_config_snapshot: Optional[List[Dict[str, Any]]] = Field(
        default=None, 
        description="可选：覆盖 plugin_config_snapshot，格式: [{plugin_code, variable_mapping}]"
    )
    model_code: Optional[str] = Field(
        default=None, 
        description="可选：覆盖模型编码"
    )
    model_cfg_override: Optional[Dict[str, Any]] = Field(
        default=None,
        alias="model_config_override",
        description="可选：覆盖模型配置 (temperature, max_tokens 等)"
    )
    prompt_override: Optional[str] = Field(
        default=None, 
        description="可选：完全覆盖渲染后的 Prompt"
    )


class TokenUsage(BaseSchema):
    """Token 使用情况"""
    prompt_tokens: int = Field(default=0, description="Prompt tokens")
    completion_tokens: int = Field(default=0, description="Completion tokens")
    total_tokens: int = Field(default=0, description="Total tokens")


class ExpertDebugResponse(BaseSchema):
    """Expert 调试响应"""
    id: Optional[int] = Field(default=None, description="调试记录 ID")
    success: bool = Field(..., description="执行是否成功")
    expert_config_code: str = Field(..., description="Expert 配置编码")
    expert_config_name: Optional[str] = Field(default=None, description="Expert 配置名称")
    model_code: Optional[str] = Field(default=None, description="使用的模型")
    model_config_used: Optional[Dict[str, Any]] = Field(default=None, description="实际使用的模型配置")
    prompt_template: Optional[str] = Field(default=None, description="原始 Prompt 模板")
    plugin_config_snapshot: Optional[List[Dict[str, Any]]] = Field(default=None, description="使用的变量快照，格式: [{plugin_code, variable_mapping}]")
    rendered_prompt: Optional[str] = Field(default=None, description="渲染后的 Prompt")
    prompt_override: Optional[str] = Field(default=None, description="用户覆盖的 Prompt")
    input_content: str = Field(..., description="输入内容")
    output_content: Optional[str] = Field(default=None, description="AI 输出内容（主要内容）")
    expert_total_output: Optional[Dict[str, Any]] = Field(default=None, description="Expert 返回的完整结果")
    execution_time_ms: int = Field(default=0, description="执行时间(毫秒)")
    token_usage: Optional[TokenUsage] = Field(default=None, description="Token 使用情况")
    error_message: Optional[str] = Field(default=None, description="错误信息")
    trace_id: Optional[str] = Field(default=None, description="追踪 ID")
    create_time: Optional[datetime] = Field(default=None, description="创建时间")
    is_starred: bool = Field(default=False, description="是否收藏")


class PreviewPromptRequest(BaseSchema):
    """预览 Prompt 渲染请求"""
    expert_config_code: str = Field(..., description="Expert 配置编码")
    plugin_config_snapshot: Optional[List[Dict[str, Any]]] = Field(
        default=None, 
        description="可选：指定变量快照，格式: [{plugin_code, variable_mapping}]，不传则随机选择"
    )


class PluginSegment(BaseSchema):
    """插件渲染段"""
    plugin_code: str = Field(..., description="Plugin 编码")
    plugin_name: Optional[str] = Field(default=None, description="Plugin 名称")
    content: str = Field(..., description="该插件渲染的内容")


class PreviewPromptResponse(BaseSchema):
    """预览 Prompt 渲染响应"""
    expert_config_code: str = Field(..., description="Expert 配置编码")
    prompt_template: Optional[str] = Field(default=None, description="原始 Prompt 模板")
    plugin_config: Optional[List[Dict[str, Any]]] = Field(default=None, description="原始 plugin_config 数组")
    plugin_config_snapshot: Optional[List[Dict[str, Any]]] = Field(default=None, description="使用的变量快照，格式: [{plugin_code, variable_mapping}]")
    rendered_prompt: str = Field(..., description="渲染后的 Prompt")
    plugin_segments: List[PluginSegment] = Field(default_factory=list, description="插件分段信息，按顺序显示每个插件渲染的内容")
    variables_used: Dict[str, str] = Field(default_factory=dict, description="使用的变量映射")


class PluginVariableOption(BaseSchema):
    """Plugin 变量选项"""
    context_name: str = Field(..., description="上下文名称/节点名称")
    context_preview: Optional[str] = Field(default=None, description="内容预览")
    node_id: Optional[str] = Field(default=None, description="节点 ID（关键词树模式）")


class KeywordTreeNode(BaseSchema):
    """关键词树节点"""
    node_id: str = Field(..., description="节点 ID")
    node_name: str = Field(..., description="节点名称")
    label: Optional[str] = Field(default=None, description="节点 label")
    corpus_count: int = Field(default=0, description="语料数量")


class StrategyNodeInfo(BaseSchema):
    """策略节点信息（含语料预览）"""
    node_id: str = Field(..., description="节点 ID")
    node_name: str = Field(..., description="节点名称")
    corpus_count: int = Field(default=0, description="语料数量")
    corpus_preview: Optional[str] = Field(default=None, description="语料内容预览")
    select_mode: Optional[str] = Field(default=None, description="节点选择模式：single-分开使用 / multiple-合在一起使用")


class StrategyInfo(BaseSchema):
    """策略绑定信息"""
    strategy_id: int = Field(..., description="策略 ID")
    strategy_name: str = Field(..., description="策略名称")
    label: str = Field(..., description="映射的维度标签")
    node_count: int = Field(default=0, description="可选节点数量")


class PluginVariable(BaseSchema):
    """Plugin 变量"""
    variable_name: str = Field(..., description="变量名")
    source: str = Field(default="plugin_context", description="变量来源: plugin_context, keyword_tree, strategy")
    # 旧模式 (plugin_context) 相关字段
    options: List[PluginVariableOption] = Field(default_factory=list, description="可选值列表（plugin_context 模式）")
    selected: Optional[str] = Field(default=None, description="当前选中的值（plugin_context 模式）")
    # keyword_tree 模式相关字段
    keyword_tree_config: Optional[Dict[str, Any]] = Field(default=None, description="关键词树配置（keyword_tree 模式）")
    keyword_tree_nodes: List[KeywordTreeNode] = Field(default_factory=list, description="已选节点列表（keyword_tree 模式）")
    strategy: Optional[str] = Field(default=None, description="选择策略: random, weighted, all")
    # 策略绑定模式 (strategy) 相关字段
    strategy_info: Optional[StrategyInfo] = Field(default=None, description="策略绑定信息")
    strategy_nodes: List[StrategyNodeInfo] = Field(default_factory=list, description="可选节点列表（策略模式）")


class PluginVariablesResponse(BaseSchema):
    """Plugin 变量列表响应"""
    plugin_code: str = Field(..., description="Plugin 编码")
    plugin_name: Optional[str] = Field(default=None, description="Plugin 名称")
    variables: List[PluginVariable] = Field(default_factory=list, description="变量列表")
    strategy_info: Optional[StrategyInfo] = Field(default=None, description="策略绑定信息（插件级别）")


class ExpertPluginVariablesResponse(BaseSchema):
    """Expert 关联的所有 Plugin 变量"""
    expert_config_code: str = Field(..., description="Expert 配置编码")
    plugins: List[PluginVariablesResponse] = Field(default_factory=list, description="Plugin 列表")


class DebugHistoryListRequest(BaseSchema):
    """调试历史列表请求"""
    expert_config_code: Optional[str] = Field(default=None, description="筛选特定 Expert")
    success: Optional[bool] = Field(default=None, description="筛选成功/失败")
    is_starred: Optional[bool] = Field(default=None, description="筛选收藏")
    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量")


class DebugHistoryListResponse(BaseSchema):
    """调试历史列表响应"""
    items: List[ExpertDebugResponse] = Field(default_factory=list, description="历史记录列表")
    total: int = Field(default=0, description="总数")
    page: int = Field(default=1, description="当前页")
    page_size: int = Field(default=20, description="每页数量")


class StarHistoryRequest(BaseSchema):
    """收藏/取消收藏请求"""
    is_starred: bool = Field(..., description="是否收藏")


class BatchDebugRequest(BaseSchema):
    """批量随机调试请求"""
    expert_config_code: str = Field(..., description="要调试的 expert_config_code")
    content: str = Field(default="", description="测试内容（CRITIC 类型用）")
    count: int = Field(default=5, ge=1, le=20, description="执行次数（1-20）")
    include_current: bool = Field(default=True, description="是否将当前变量作为首次测试")
    current_plugin_config_snapshot: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="当前变量快照（include_current=true 时使用）"
    )
    model_code: Optional[str] = Field(default=None, description="可选：覆盖模型编码")
    model_cfg_override: Optional[Dict[str, Any]] = Field(
        default=None,
        alias="model_config_override",
        description="可选：覆盖模型配置"
    )
    prompt_override: Optional[str] = Field(default=None, description="可选：覆盖 Prompt")


class BatchDebugResultItem(BaseSchema):
    """批量调试单条结果"""
    index: int = Field(..., description="执行序号（从 1 开始）")
    success: bool = Field(..., description="执行是否成功")
    plugin_config_snapshot: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="使用的变量快照"
    )
    variable_summary: str = Field(default="", description="变量组合摘要")
    title: str = Field(default="", description="生成内容的标题")
    output_preview: str = Field(default="", description="输出预览（前 200 字）")
    output_content: Optional[str] = Field(default=None, description="完整输出")
    execution_time_ms: int = Field(default=0, description="执行时间(毫秒)")
    error_message: Optional[str] = Field(default=None, description="错误信息")
    history_id: Optional[int] = Field(default=None, description="历史记录 ID")


class BatchDebugResponse(BaseSchema):
    """批量随机调试响应"""
    expert_config_code: str = Field(..., description="Expert 配置编码")
    expert_config_name: Optional[str] = Field(default=None, description="Expert 配置名称")
    total: int = Field(default=0, description="执行总数")
    success_count: int = Field(default=0, description="成功数")
    failed_count: int = Field(default=0, description="失败数")
    total_time_ms: int = Field(default=0, description="总耗时(毫秒)")
    results: List[BatchDebugResultItem] = Field(default_factory=list, description="结果列表")


class BatchDebugTaskResponse(BaseSchema):
    """批量调试任务创建响应（异步模式）"""
    task_id: str = Field(..., description="任务 ID")
    status: str = Field(..., description="任务状态: pending/running/completed/failed")
    expert_config_code: str = Field(..., description="Expert 配置编码")
    total: int = Field(..., description="总任务数")
    message: str = Field(..., description="提示信息")


class BatchDebugTaskStatusResponse(BaseSchema):
    """批量调试任务状态响应"""
    task_id: str = Field(..., description="任务 ID")
    status: str = Field(..., description="任务状态: pending/running/completed/failed")
    expert_config_code: str = Field(..., description="Expert 配置编码")
    expert_config_name: Optional[str] = Field(default=None, description="Expert 配置名称")
    total: int = Field(default=0, description="总任务数")
    completed: int = Field(default=0, description="已完成数")
    success_count: int = Field(default=0, description="成功数")
    failed_count: int = Field(default=0, description="失败数")
    results: List[BatchDebugResultItem] = Field(default_factory=list, description="结果列表")
    error_message: Optional[str] = Field(default=None, description="错误信息")
    start_time: Optional[datetime] = Field(default=None, description="开始时间")
    end_time: Optional[datetime] = Field(default=None, description="结束时间")
    create_time: Optional[datetime] = Field(default=None, description="创建时间")

