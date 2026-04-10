/**
 * Expert 调试 API
 */
import { requestClient } from '#/api/request';

// ==================== 类型定义 ====================

export namespace ExpertDebugApi {
  /** Token 使用情况 */
  export interface TokenUsage {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  }

  /** Plugin 配置快照项 */
  export interface PluginConfigSnapshotItem {
    plugin_code: string;
    variable_mapping: Record<string, string>;
  }

  /** 调试请求 */
  export interface DebugRequest {
    expert_config_code: string;
    content: string;
    plugin_config_snapshot?: PluginConfigSnapshotItem[];
    model_code?: string;
    model_config_override?: Record<string, any>;
    prompt_override?: string;
  }

  /** 调试响应 */
  export interface DebugResponse {
    id?: number;
    success: boolean;
    expert_config_code: string;
    expert_config_name?: string;
    model_code?: string;
    model_config_used?: Record<string, any>;
    prompt_template?: string;
    plugin_config_snapshot?: PluginConfigSnapshotItem[];
    rendered_prompt?: string;
    prompt_override?: string;
    input_content: string;
    output_content?: string;
    expert_total_output?: Record<string, any>; // Expert 返回的完整结果
    execution_time_ms: number;
    token_usage?: TokenUsage;
    error_message?: string;
    trace_id?: string;
    create_time?: string;
  }

  /** 预览 Prompt 请求 */
  export interface PreviewPromptRequest {
    expert_config_code: string;
    plugin_config_snapshot?: PluginConfigSnapshotItem[];
  }

  /** 插件渲染段 */
  export interface PluginSegment {
    plugin_code: string;
    plugin_name?: string;
    content: string;
  }

  /** 预览 Prompt 响应 */
  export interface PreviewPromptResponse {
    expert_config_code: string;
    prompt_template?: string;
    plugin_config?: PluginConfigSnapshotItem[];
    plugin_config_snapshot?: PluginConfigSnapshotItem[];
    rendered_prompt: string;
    plugin_segments: PluginSegment[];
    variables_used: Record<string, string>;
  }

  /** Plugin 变量选项 */
  export interface PluginVariableOption {
    context_name: string;
    context_preview?: string;
  }

  /** 用户画像配置 */
  export interface UserProfileConfig {
    source: 'user_profile';
    label?: string;
    strategy?: 'all' | 'random' | 'weighted';
  }

  /** 策略节点信息（含语料预览） */
  export interface StrategyNodeInfo {
    node_id: string;
    node_name: string;
    corpus_count: number;
    corpus_preview?: string;
  }

  /** 策略绑定信息 */
  export interface StrategyInfo {
    strategy_id: number;
    strategy_name: string;
    label: string;
    node_count: number;
  }

  /** Plugin 变量 */
  export interface PluginVariable {
    variable_name: string;
    options: PluginVariableOption[];
    selected?: string;
    // 模式字段
    source?: 'plugin_context' | 'strategy';
    // 策略绑定模式字段
    strategy_info?: StrategyInfo;
    strategy_nodes?: StrategyNodeInfo[];
  }

  /** Plugin 变量响应 */
  export interface PluginVariablesResponse {
    plugin_code: string;
    plugin_name?: string;
    variables: PluginVariable[];
    strategy_info?: {
      label: string;
      node_count: number;
      strategy_id: number;
      strategy_name: string;
    };
  }

  /** Expert Plugin 变量响应 */
  export interface ExpertPluginVariablesResponse {
    expert_config_code: string;
    plugins: PluginVariablesResponse[];
  }

  /** 调试历史列表响应 */
  export interface DebugHistoryListResponse {
    items: DebugResponse[];
    total: number;
    page: number;
    page_size: number;
  }

  /** 历史列表查询参数 */
  export interface HistoryListParams {
    expert_config_code?: string;
    success?: boolean;
    is_starred?: boolean;
    page?: number;
    page_size?: number;
  }

  /** 批量随机调试请求 */
  export interface BatchDebugRequest {
    expert_config_code: string;
    content?: string;
    count?: number;
    include_current?: boolean;
    current_plugin_config_snapshot?: PluginConfigSnapshotItem[];
    model_code?: string;
    model_config_override?: Record<string, any>;
    prompt_override?: string;
  }

  /** 批量调试单条结果 */
  export interface BatchDebugResultItem {
    index: number;
    success: boolean;
    plugin_config_snapshot?: PluginConfigSnapshotItem[];
    variable_summary: string;
    title?: string;
    output_preview: string;
    output_content?: string;
    execution_time_ms: number;
    error_message?: string;
    history_id?: number;
  }

  /** 批量随机调试响应 */
  export interface BatchDebugResponse {
    expert_config_code: string;
    expert_config_name?: string;
    total: number;
    success_count: number;
    failed_count: number;
    total_time_ms: number;
    results: BatchDebugResultItem[];
  }

  /** 批量调试任务创建响应（异步模式） */
  export interface BatchDebugTaskResponse {
    task_id: string;
    status: string;
    expert_config_code: string;
    total: number;
    message: string;
  }

  /** 批量调试任务状态响应 */
  export interface BatchDebugTaskStatusResponse {
    task_id: string;
    status: string;
    expert_config_code: string;
    expert_config_name?: string;
    total: number;
    completed: number;
    success_count: number;
    failed_count: number;
    results: BatchDebugResultItem[];
    error_message?: string;
    start_time?: string;
    end_time?: string;
    create_time?: string;
  }

  /** SSE 进度事件数据 */
  export interface BatchDebugProgressEvent {
    task_id: string;
    status: string;
    total: number;
    completed: number;
    success_count: number;
    failed_count: number;
    results: BatchDebugResultItem[];
  }

  /** 批量调试任务列表项 */
  export interface BatchDebugTaskListItem {
    id: number;
    task_id: string;
    expert_config_code: string;
    expert_config_name?: string;
    status: string;
    total: number;
    completed: number;
    success_count: number;
    failed_count: number;
    start_time?: string;
    end_time?: string;
    create_time: string;
  }

  /** 批量调试任务历史列表响应 */
  export interface BatchDebugTaskListResponse {
    items: BatchDebugTaskListItem[];
    total: number;
    page: number;
    page_size: number;
  }
}

// ==================== API 函数 ====================

/**
 * 执行 Expert 调试
 */
export async function debugExpertApi(data: ExpertDebugApi.DebugRequest) {
  return requestClient.post<ExpertDebugApi.DebugResponse>(
    '/v1/expert-configs/debug',
    data,
    {
      timeout: 180_000, // 3 分钟超时
    },
  );
}

/**
 * 预览 Prompt 渲染结果
 */
export async function previewPromptApi(
  data: ExpertDebugApi.PreviewPromptRequest,
) {
  return requestClient.post<ExpertDebugApi.PreviewPromptResponse>(
    '/v1/expert-configs/preview-prompt',
    data,
  );
}

/**
 * 获取 Expert 关联的 Plugin 变量选项
 */
export async function getPluginVariablesApi(expertConfigCode: string) {
  return requestClient.get<ExpertDebugApi.ExpertPluginVariablesResponse>(
    `/v1/expert-configs/${expertConfigCode}/plugin-variables`,
    {
      // 添加时间戳参数避免浏览器缓存
      params: {
        _t: Date.now(),
      },
    },
  );
}

/**
 * 获取调试历史列表
 */
export async function getDebugHistoryApi(
  params?: ExpertDebugApi.HistoryListParams,
) {
  return requestClient.get<ExpertDebugApi.DebugHistoryListResponse>(
    '/v1/expert-configs/debug-history',
    { params },
  );
}

/**
 * 获取单条调试历史详情
 */
export async function getDebugHistoryDetailApi(historyId: number) {
  return requestClient.get<ExpertDebugApi.DebugResponse>(
    `/v1/expert-configs/debug-history/${historyId}`,
  );
}

/**
 * 收藏/取消收藏调试历史
 */
export async function starDebugHistoryApi(
  historyId: number,
  isStarred: boolean,
) {
  return requestClient.put(
    `/v1/expert-configs/debug-history/${historyId}/star`,
    {
      is_starred: isStarred,
    },
  );
}

/**
 * 删除调试历史
 */
export async function deleteDebugHistoryApi(historyId: number) {
  return requestClient.delete(`/v1/expert-configs/debug-history/${historyId}`);
}

/**
 * 批量随机调试（异步模式）
 * 立即返回 task_id，通过 SSE 接收实时进度
 */
export async function batchDebugExpertApi(
  data: ExpertDebugApi.BatchDebugRequest,
) {
  return requestClient.post<ExpertDebugApi.BatchDebugTaskResponse>(
    '/v1/expert-configs/debug-batch',
    data,
  );
}

/**
 * 查询批量调试任务状态
 */
export async function getBatchDebugTaskStatusApi(taskId: string) {
  return requestClient.get<ExpertDebugApi.BatchDebugTaskStatusResponse>(
    `/v1/expert-configs/debug-batch/${taskId}`,
  );
}

/**
 * 获取批量调试任务历史列表
 */
export async function listBatchDebugTasksApi(params?: {
  expert_config_code?: string;
  page?: number;
  page_size?: number;
  status?: string;
}) {
  return requestClient.get<ExpertDebugApi.BatchDebugTaskListResponse>(
    '/v1/expert-configs/debug-batch',
    { params },
  );
}

// ==================== 批量评分（test_case / expert_eval_*） ====================

export namespace ExpertEvalApi {
  /** 测试集选项（用于下拉选择） */
  export interface TestSetOption {
    id: number;
    code: string;
    name: string;
    type: 'image' | 'text';
    case_count?: number;
  }

  export interface TestCaseItem {
    id: number;
    test_set_code: string;
    title?: null | string;
    content?: null | string;
    image_url?: null | string;
    enabled: number;
    create_time?: string;
    update_time?: string;
  }

  export interface TestCaseListResponse {
    items: TestCaseItem[];
    total: number;
    page: number;
    page_size: number;
  }

  export interface EvalRunItem {
    id: number;
    run_code: string;
    expert_config_code: string;
    test_set_code?: null | string;
    status: 'cancelled' | 'failed' | 'running' | 'success';
    total_count: number;
    success_count: number;
    failed_count: number;
    start_time?: string;
    end_time?: null | string;
    created_by?: null | string;
  }

  export interface EvalRunListResponse {
    items: EvalRunItem[];
    total: number;
    page: number;
    page_size: number;
  }

  export interface CreateEvalRunRequest {
    expert_config_code: string;
    test_set_code?: string;
    test_case_ids?: number[];
    max_count?: number;
    start_no?: number;
    end_no?: number;
    // 前端可选：并发/超时等，后端可忽略
    article_concurrency?: number;
  }

  export interface CreateEvalRunResponse {
    run_id: number;
    run_code: string;
  }

  export interface EvalResultItem {
    id: number;
    run_id: number;
    test_case_id: number;
    score?: null | number;
    reason?: null | string;
    highlights?: null | string;
    problem_tags?: null | string[];
    problem_snippets?: null | string[];
    problem_context_list?: null | string[];
    success: boolean;
    error_message?: null | string;
    latency_ms?: null | number;
    model_code?: null | string;
    trace_id?: null | string;
    create_time?: string;
  }

  export interface EvalResultListResponse {
    items: EvalResultItem[];
    total: number;
    page: number;
    page_size: number;
  }

  export interface EvalResultDetailTestCase {
    id: number;
    test_set_code: string;
    title?: null | string;
    content?: null | string;
    image_url?: null | string;
  }

  export interface EvalResultDetail {
    id: number;
    run_id: number;
    test_case_id: number;
    score?: null | number;
    reason?: null | string;
    highlights?: null | string;
    problem_tags?: null | string[];
    problem_snippets?: null | string[];
    problem_context_list?: null | string[];
    success: boolean;
    error_message?: null | string;
    latency_ms?: null | number;
    model_code?: null | string;
    provider_code?: null | string;
    token_usage?: null | Record<string, any>;
    trace_id?: null | string;
    rendered_prompt?: null | string;
    raw_output?: null | Record<string, any>;
    create_time?: string;
    test_case?: EvalResultDetailTestCase | null;
  }
}

/**
 * 获取测试用例列表（test_case）
 */
export async function listTestCasesApi(params?: {
  enabled?: boolean;
  keyword?: string;
  page?: number;
  page_size?: number;
  test_set_code?: string;
}) {
  return requestClient.get<ExpertEvalApi.TestCaseListResponse>(
    '/v1/test-cases',
    {
      params,
    },
  );
}

/**
 * 获取测试集选项列表（用于批量评分下拉）
 */
export async function listTestSetOptionsApi() {
  return requestClient.get<ExpertEvalApi.TestSetOption[]>(
    '/v1/test-sets/options',
  );
}

/**
 * 创建并触发一次评测 run（后端应从 test_case 取数并写入 expert_eval_result）
 */
export async function createEvalRunApi(
  data: ExpertEvalApi.CreateEvalRunRequest,
) {
  return requestClient.post<ExpertEvalApi.CreateEvalRunResponse>(
    '/v1/expert-evals/runs',
    data,
    {
      timeout: 600_000, // 10 分钟
    },
  );
}

/**
 * 查询评测 run 列表
 */
export async function listEvalRunsApi(params?: {
  expert_config_code?: string;
  page?: number;
  page_size?: number;
  status?: string;
  test_set_code?: string;
}) {
  return requestClient.get<ExpertEvalApi.EvalRunListResponse>(
    '/v1/expert-evals/runs',
    { params },
  );
}

/**
 * 查询评测结果列表
 */
export async function listEvalResultsApi(params: {
  page?: number;
  page_size?: number;
  run_id: number;
  success?: boolean;
}) {
  return requestClient.get<ExpertEvalApi.EvalResultListResponse>(
    '/v1/expert-evals/results',
    { params },
  );
}

/**
 * 查询单条评测结果详情（用于抽屉/弹窗）
 */
export async function getEvalResultDetailApi(resultId: number) {
  return requestClient.get<ExpertEvalApi.EvalResultDetail>(
    `/v1/expert-evals/results/${resultId}`,
  );
}
