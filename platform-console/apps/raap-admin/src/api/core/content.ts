import type {
  ContentDetail,
  ExpertBusinessResultDetail,
} from './job-execution';

import { requestClient } from '#/api/request';

export namespace ContentApi {
  /**
   * 评分通过状态枚举
   * - all_passed: 全部通过
   * - has_ban: 存在违规
   * - partial: 部分通过
   * - no_score: 未评分
   */
  export type ScoreStatus = 'all_passed' | 'has_ban' | 'no_score' | 'partial';

  export interface ContentListParams {
    tenant_id?: number;
    activity_id?: number;
    job_id?: string;
    /** Agent 编码筛选 */
    agent_code?: string;
    /** 专家编码筛选（前端用于标记筛选来源） */
    expert_config_code?: string;
    is_valid?: number;
    is_test_case?: number;
    online_status?: string;
    keyword?: string;
    /** 评分通过状态筛选 */
    score_status?: ScoreStatus;
    /** 平均分最小值 */
    avg_score_min?: number;
    /** 平均分最大值 */
    avg_score_max?: number;
    /** 细化专家评分筛选 (JSON 字符串) */
    expert_score_filters?: string;
    /** ID 范围筛选 - 最小ID */
    id_min?: number;
    /** ID 范围筛选 - 最大ID */
    id_max?: number;
    page?: number;
    page_size?: number;
    offset?: number;
    limit?: number;
  }

  export interface ContentListResponse {
    items: ContentDetail[];
    total: number;
    page: number;
    page_size: number;
    offset?: number;
    limit?: number;
  }

  export interface ContextStatsParams {
    tenant_id?: number;
    activity_id?: number;
    job_id?: string;
    agent_code?: string;
    is_valid?: number;
    is_test_case?: number;
    variable_name?: string;
  }

  export interface ContextDistributionItem {
    name: string;
    value: number;
  }

  export interface ContextStatsResponse {
    keys: string[];
    distribution: ContextDistributionItem[];
    sample_count?: number; // 实际统计的记录数
    total_count?: number; // 总记录数
    is_sampled?: boolean; // 是否使用了采样
  }

  export interface ContentStatsParams {
    tenant_id?: number;
    activity_id?: number;
    job_id?: string;
    agent_code?: string;
  }

  export interface ContentStatsResponse {
    total: number; // 文章总数
    valid: number; // 有效文章数
    invalid: number; // 无效文章数
    pending: number; // 待定文章数
    test: number; // 测试文章数
    formal_valid: number; // 正式有效文章数 (is_valid = 1 and is_test_case = 0)
    online: number; // 上线文章数
    locked: number; // 锁定文章数
    unlocked: number; // 未被锁定文章数
    used: number; // 被使用文章数
    unused: number; // 未被使用文章数
  }
}

/**
 * 获取文章内容列表
 */
export async function listContentsApi(params: ContentApi.ContentListParams) {
  return requestClient.get<ContentApi.ContentListResponse>('/v1/contents', {
    params,
  });
}

/**
 * 获取 Context 变量分布统计
 */
export async function getContextStatsApi(
  params: ContentApi.ContextStatsParams,
) {
  return requestClient.get<ContentApi.ContextStatsResponse>(
    '/v1/contents/context-stats',
    { params },
  );
}

/**
 * 获取文章统计数据
 */
export async function getContentStatsApi(
  params: ContentApi.ContentStatsParams,
) {
  return requestClient.get<ContentApi.ContentStatsResponse>(
    '/v1/contents/stats',
    { params },
  );
}

/**
 * 根据 Job ID 和 Content ID 获取 Expert 业务结果（用于获取 CRITIC 审核结果）
 */
export async function getContentExpertResultsApi(
  jobId: string,
  contentId: string,
) {
  return requestClient.get<ExpertBusinessResultDetail[]>(
    `/v1/job-execution/${jobId}/business-results`,
    { params: { content_id: contentId } },
  );
}

/**
 * CSV 导入文章
 */
export namespace ContentImportApi {
  export interface ImportParams {
    file: File;
    tenant_id: number;
    agent_code: string;
    is_test_case?: number;
  }

  export interface ImportResponse {
    success_count: number;
    failed_count: number;
    job_id: string;
    errors?: string[];
  }
}

export async function importContentsApi(params: ContentImportApi.ImportParams) {
  const formData = new FormData();
  formData.append('file', params.file);
  formData.append('tenant_id', String(params.tenant_id));
  formData.append('agent_code', params.agent_code);
  formData.append('is_test_case', String(params.is_test_case ?? 0));

  return requestClient.post<ContentImportApi.ImportResponse>(
    '/v1/contents/import',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    },
  );
}

/**
 * 上线状态更新响应
 */
export namespace OnlineStatusApi {
  /** 单篇文章更新响应 */
  export interface SingleUpdateResult {
    skipped_reason?: 'locked' | 'used' | null;
  }

  /** 批量更新响应 */
  export interface BatchUpdateResult {
    updated_count: number;
    skipped_locked: number;
    skipped_used: number;
    total: number;
  }
}

/**
 * 更新单篇文章上线状态
 * 注意：下线时会检查文章状态
 * - 已锁定(is_locked=1)的文章不允许下线
 * - 已使用(is_used=1)的文章不允许下线
 */
export async function updateContentOnlineStatusApi(data: {
  content_id: number;
  online_status: 'OFFLINE' | 'ONLINE';
}) {
  return requestClient.post<OnlineStatusApi.SingleUpdateResult>(
    '/v1/contents/online',
    data,
  );
}

/**
 * 批量更新文章上线状态
 * 支持两种模式：
 * 1. 按任务ID批量更新：更新该任务下所有有效且非测试的文章
 * 2. 按文章ID列表批量更新：更新指定的文章列表
 * 注意：下线时会检查文章状态
 * - 已锁定(is_locked=1)的文章会被跳过
 * - 已使用(is_used=1)的文章会被跳过
 */
export async function batchUpdateContentOnlineStatusApi(data: {
  content_ids?: number[];
  job_id?: string;
  online_status: 'OFFLINE' | 'ONLINE';
}) {
  return requestClient.post<OnlineStatusApi.BatchUpdateResult>(
    '/v1/contents/batch-online',
    data,
  );
}

/**
 * 批量评分 API
 */
export namespace BatchScoreApi {
  export interface BatchScoreParams {
    /** Expert 配置编码 */
    expert_config_code: string;
    /** Content ID 列表 */
    content_ids: string[];
    /** 是否只查询测试用例（传 false 支持业务文章） */
    test_case_only?: boolean;
  }

  export interface BatchScoreResultItem {
    id: number;
    expert_config_code: string;
    content_id: null | string;
    title: null | string;
    score: null | number;
    reason: null | string;
    success: boolean;
    error_message: null | string;
  }

  export interface BatchScoreResponse {
    expert_config_code: string;
    total: number;
    success_count: number;
    failed_count: number;
    results: BatchScoreResultItem[];
  }
}

/**
 * 批量评分（支持业务文章）- 同步版本（已弃用）
 */
export async function batchScoreContentsApi(
  params: BatchScoreApi.BatchScoreParams,
) {
  return requestClient.post<BatchScoreApi.BatchScoreResponse>(
    '/v1/expert-configs/batch-score',
    params,
  );
}

/**
 * 异步批量评分 API（任务模式，支持多专家）
 */
export namespace BatchScoreTaskApi {
  /** 创建批量评分任务请求（支持多专家） */
  export interface CreateTaskParams {
    expert_config_codes: string[];
    content_ids: string[];
    test_case_only?: boolean;
    concurrency?: number; // 并发数（1-20，默认3）
  }

  /** 单个专家任务信息 */
  export interface TaskItem {
    task_id: string;
    expert_config_code: string;
    expert_config_name: string;
    status: string;
    total: number;
  }

  /** 创建批量评分任务响应（返回多个任务） */
  export interface CreateTaskResponse {
    tasks: TaskItem[];
    total_experts: number;
    total_contents: number;
    message: string;
  }

  /** 单条评分结果 */
  export interface TaskResultItem {
    content_id: string;
    title: null | string;
    score: null | number;
    reason: null | string;
    success: boolean;
    error_message: null | string;
    execution_time_ms: null | number;
  }

  /** 任务状态响应 */
  export interface TaskStatusResponse {
    task_id: string;
    status: 'completed' | 'failed' | 'pending' | 'running';
    total: number;
    completed: number;
    success_count: number;
    failed_count: number;
    results: TaskResultItem[];
    error_message: null | string;
    start_time: null | string;
    end_time: null | string;
  }
}

/**
 * 创建异步批量评分任务
 */
export async function createBatchScoreTaskApi(
  params: BatchScoreTaskApi.CreateTaskParams,
) {
  return requestClient.post<BatchScoreTaskApi.CreateTaskResponse>(
    '/v1/expert-configs/batch-score-async',
    params,
  );
}

/**
 * 查询批量评分任务状态
 */
export async function getBatchScoreTaskStatusApi(taskId: string) {
  return requestClient.get<BatchScoreTaskApi.TaskStatusResponse>(
    `/v1/expert-configs/batch-score-task/${taskId}`,
  );
}

/**
 * 批量更新文章有效状态 API
 */
export namespace BatchValidUpdateApi {
  export interface BatchValidUpdateParams {
    /** 文章 ID 列表（主键） */
    content_ids: number[];
    /** 有效状态：0=无效，1=有效 */
    is_valid: number;
  }

  export interface BatchValidUpdateResponse {
    updated_count: number;
    total: number;
  }
}

/**
 * 批量更新文章有效状态（批量下线/上线）
 */
export async function batchUpdateContentValidApi(
  params: BatchValidUpdateApi.BatchValidUpdateParams,
) {
  return requestClient.post<BatchValidUpdateApi.BatchValidUpdateResponse>(
    '/v1/contents/batch-valid',
    params,
  );
}

/**
 * 文章转移 API
 */
export namespace ContentTransferApi {
  /** 转移请求参数 */
  export interface TransferRequest {
    /** 文章 ID 列表（指定时直接转移这些文章） */
    content_ids?: string[];
    /** 租户 ID */
    tenant_id?: number;
    /** 活动 ID */
    activity_id?: number;
    /** 任务 ID */
    job_id?: string;
    /** 是否有效 */
    is_valid?: number;
    /** 是否测试用例 */
    is_test_case?: number;
    /** 上线状态 */
    online_status?: 'OFFLINE' | 'ONLINE';
    /** 最多转移数量 */
    max_count?: number;
    /** 是否跳过已锁定的文章 */
    skip_locked?: boolean;
    /** 是否跳过已使用的文章 */
    skip_used?: boolean;
  }

  /** 转移响应 */
  export interface TransferResponse {
    /** 成功转移数量 */
    success_count: number;
    /** 跳过已锁定数量 */
    skipped_locked_count: number;
    /** 跳过已使用数量 */
    skipped_used_count: number;
    /** 失败数量 */
    failed_count: number;
    /** 被跳过的文章 ID 列表 */
    skipped_content_ids?: string[];
  }
}

/**
 * 转移文章到另一个 Agent
 * @param sourceAgentCode 源 Agent 编码
 * @param targetAgentCode 目标 Agent 编码
 * @param params 转移参数
 */
export async function transferContentsApi(
  sourceAgentCode: string,
  targetAgentCode: string,
  params: ContentTransferApi.TransferRequest,
) {
  return requestClient.post<ContentTransferApi.TransferResponse>(
    `/v1/contents/transfer?source_agent_code=${sourceAgentCode}&target_agent_code=${targetAgentCode}`,
    params,
  );
}
