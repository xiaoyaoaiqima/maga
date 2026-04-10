import { requestClient } from '#/api/request';

export namespace JobApi {
  /** Job 状态 */
  export type JobStatus =
    | 'COMPLETED'
    | 'DEPLOYED'
    | 'NOT_DEPLOYED'
    | 'PAUSED'
    | 'RUNNING';

  /** Job 基础信息 */
  export interface Job {
    job_id: string;
    job_name: string;
    tenant_id?: null | number;
    activity_id?: null | number;
    agent_code?: null | string;
    tenant_name?: string;
    activity_name?: string;
    agent_name?: string;
    description: null | string;
    expert_config_code_list: string[];
    /**
     * 当这些打分型 Expert 返回 score==0 时，将文章判定为不可用（content.is_valid=0）并提前完成 sub_job；
     * - null/undefined：兼容旧逻辑（任意打分 Expert score==0 都判无效）
     * - []：不启用 score==0 判无效
     * - [..]：仅命中列表内 expert 才会触发
     */
    zero_score_invalid_expert_codes?: null | string[];
    /** 由 JobCreateDraft 编译得到的执行计划（多组合/分流/Variant），存在时优先生效 */
    job_generation_plan?: null | Record<string, any>;
    article_count: null | number;
    status: JobStatus;
    enabled: boolean;
    remark: null | string;
    create_time: string;
    update_time: string;
    created_by: null | string;
    updated_by: null | string;
    is_deleted: number;
  }

  /** 创建 Job 参数 */
  export interface CreateParams {
    job_name: string;
    tenant_id?: number;
    activity_id?: number;
    agent_code?: string;
    description?: string;
    /** 创建时可省略，由后端从 Agent 复制 */
    expert_config_code_list?: string[];
    /** 创建时可省略，由后端从 Agent 复制 */
    zero_score_invalid_expert_codes?: null | string[];
    /** 由前端生成的执行计划（多组合/分流/Variant），可选；不传/传 null 表示随机 */
    job_generation_plan?: null | Record<string, any>;
    /** 目标文章篇数（必填，最小 1） */
    article_count: number;
    status?: JobStatus;
    enabled?: boolean;
    remark?: string;
  }

  /** 更新 Job 参数 */
  export interface UpdateParams {
    job_name?: string;
    tenant_id?: number;
    agent_code?: string;
    description?: string;
    expert_config_code_list?: string[];
    zero_score_invalid_expert_codes?: null | string[];
    /** 传 null 可清空 plan（回退到随机） */
    job_generation_plan?: null | Record<string, any>;
    article_count?: number;
    status?: JobStatus;
    enabled?: boolean;
    remark?: string;
  }

  /** ExpertConfig plugin_config 项（候选上下文为数组） */
  export interface ExpertPluginConfigItem {
    plugin_code: string;
    variable_mapping: Record<string, string | string[]>;
  }

  /** Plugin 配置快照项 */
  export interface PluginConfigSnapshotItem {
    plugin_code: string;
    variable_mapping: Record<string, string>;
  }

  /** 测试请求参数 */
  export interface TestRequest {
    experts_plugin_config_snapshot?: Record<string, PluginConfigSnapshotItem[]>;
    count?: number;
  }

  /** 单个 Expert 测试结果 */
  export interface ExpertTestResult {
    error?: string;
    error_type?: string;
    generatedContent?: string;
    content?: string;
    [key: string]: any;
  }

  /** 测试响应 */
  export interface TestResponse {
    results: Record<string, ExpertTestResult>;
  }

  /** ExpertTask */
  export interface ExpertTask {
    id: number;
    job_id: string;
    expert_config_code: string;
    cron_expression: string;
    misfire_policy: number;
    concurrent: number;
    status: number;
    remark: null | string;
    create_time: string;
    update_time: string;
    created_by: null | string;
    updated_by: null | string;
  }

  /** 部署任务配置 */
  export interface ExpertTaskConfig {
    expert_config_code: string;
    cron_expression: string;
    misfire_policy: number;
    concurrent: number;
  }

  /** 部署请求参数 */
  export interface DeployRequest {
    task_configs: ExpertTaskConfig[];
  }

  /** ExpertConfig 简要信息 */
  export interface ExpertConfigBrief {
    id: number;
    expert_config_code: string;
    expert_config_name: string;
    description: null | string;
    expert_type: string;
    expert_app: string;
    expert_service: string;
    expert_func: string;
    model_code: null | string;
    enabled: boolean;
    plugin_config: ExpertPluginConfigItem[] | null;
    prompt_template: null | string;
  }

  /** Plugin 选项 */
  export interface PluginContextOption {
    context_name: string;
    context_content: string;
  }
}

export namespace JobCreateDraftApi {
  export type DraftMode =
    | 'ai'
    | 'allocation_rules'
    | 'explicit_combinations'
    | 'variants';

  export interface Draft {
    draft_id: string;
    tenant_id?: null | number;
    mode: DraftMode;
    draft_json: Record<string, any>;
    compiled_json?: null | Record<string, any>;
    validation_json?: null | Record<string, any>;
    remark?: null | string;
    create_time?: string;
    update_time?: string;
    created_by?: null | string;
    updated_by?: null | string;
    is_deleted?: number;
  }

  export interface CreateParams {
    tenant_id?: number;
    mode: DraftMode;
    draft_json?: Record<string, any>;
    remark?: string;
    created_by?: string;
  }

  export interface PatchParams {
    patch: Record<string, any>;
    note?: string;
    updated_by?: string;
  }

  export interface CompileResponse {
    draft_id: string;
    compiled_json: Record<string, any>;
  }
}

export namespace JobVariantApi {
  export interface JobVariant {
    variant_id: string;
    tenant_id?: null | number;
    agent_code?: null | string;
    variant_name: string;
    tags: string[];
    expert_config_code_list: string[];
    expert_param_config: Record<string, any>;
    enabled: boolean;
    remark?: null | string;
    create_time?: string;
    update_time?: string;
    created_by?: null | string;
    updated_by?: null | string;
    is_deleted?: number;
  }

  export interface CreateParams {
    tenant_id?: number;
    agent_code?: string;
    variant_name: string;
    tags?: string[];
    expert_config_code_list?: string[];
    expert_param_config: Record<string, any>;
    enabled?: boolean;
    remark?: string;
    created_by?: string;
  }

  export interface UpdateParams {
    tenant_id?: number;
    agent_code?: string;
    variant_name?: string;
    tags?: string[];
    expert_config_code_list?: string[];
    expert_param_config?: Record<string, any>;
    enabled?: boolean;
    remark?: string;
    updated_by?: string;
  }
}

/**
 * 获取 Job 列表
 */
export async function getJobListApi(params?: {
  agent_code?: string;
  enabled?: boolean;
  limit?: number;
  skip?: number;
  status?: string;
  tenant_id?: number;
}) {
  return requestClient.get<JobApi.Job[]>('/v1/jobs', { params });
}

/** Job 简单项（用于下拉选择） */
export interface JobSimpleItem {
  job_id: string;
  job_name: string;
  tenant_id?: null | number;
  activity_id?: null | number;
}

/**
 * 获取 Job 详情
 */
export async function getJobApi(jobId: string) {
  return requestClient.get<JobApi.Job>(`/v1/jobs/${jobId}`);
}

/**
 * 创建 Job
 */
export async function createJobApi(data: JobApi.CreateParams) {
  return requestClient.post<JobApi.Job>('/v1/jobs', data);
}

/**
 * 复制 Job（包含 job_generation_plan）
 */
export async function copyJobApi(jobId: string, new_job_name?: string) {
  return requestClient.post<JobApi.Job>(`/v1/jobs/${jobId}/copy`, {
    new_job_name,
  });
}

/**
 * ==================== JobCreateDraft（草稿）API ====================
 */
export async function createJobCreateDraftApi(
  data: JobCreateDraftApi.CreateParams,
) {
  return requestClient.post<JobCreateDraftApi.Draft>(
    '/v1/job-create/drafts',
    data,
  );
}

export async function getJobCreateDraftApi(draftId: string) {
  return requestClient.get<JobCreateDraftApi.Draft>(
    `/v1/job-create/drafts/${draftId}`,
  );
}

export async function patchJobCreateDraftApi(
  draftId: string,
  data: JobCreateDraftApi.PatchParams,
) {
  // @vben/request 的 RequestClient 使用 request(url, config) 形态
  return (requestClient as any).request(`/v1/job-create/drafts/${draftId}`, {
    method: 'PATCH',
    data,
  }) as Promise<JobCreateDraftApi.Draft>;
}

export async function compileJobCreateDraftApi(draftId: string) {
  return requestClient.post<JobCreateDraftApi.CompileResponse>(
    `/v1/job-create/drafts/${draftId}/compile`,
  );
}

export async function createJobFromDraftApi(draftId: string) {
  return requestClient.post<JobApi.Job>(
    `/v1/job-create/drafts/${draftId}/create-job`,
  );
}

/**
 * ==================== JobVariant（方案库）API ====================
 */
export async function getJobVariantListApi(params?: {
  agent_code?: string;
  enabled?: boolean;
  keyword?: string;
  limit?: number;
  skip?: number;
  tenant_id?: number;
}) {
  return requestClient.get<JobVariantApi.JobVariant[]>('/v1/job-variants', {
    params,
  });
}

export async function getJobVariantApi(variantId: string) {
  return requestClient.get<JobVariantApi.JobVariant>(
    `/v1/job-variants/${variantId}`,
  );
}

export async function createJobVariantApi(data: JobVariantApi.CreateParams) {
  return requestClient.post<JobVariantApi.JobVariant>('/v1/job-variants', data);
}

export async function updateJobVariantApi(
  variantId: string,
  data: JobVariantApi.UpdateParams,
) {
  return requestClient.put<JobVariantApi.JobVariant>(
    `/v1/job-variants/${variantId}`,
    data,
  );
}

export async function disableJobVariantApi(
  variantId: string,
  params?: { updated_by?: string },
) {
  return requestClient.post<JobVariantApi.JobVariant>(
    `/v1/job-variants/${variantId}/disable`,
    undefined,
    { params },
  );
}

export async function deleteJobVariantApi(variantId: string) {
  return requestClient.delete(`/v1/job-variants/${variantId}`);
}

/**
 * 更新 Job
 */
export async function updateJobApi(jobId: string, data: JobApi.UpdateParams) {
  return requestClient.put<JobApi.Job>(`/v1/jobs/${jobId}`, data);
}

/**
 * 删除 Job
 */
export async function deleteJobApi(jobId: string) {
  return requestClient.delete(`/v1/jobs/${jobId}`);
}

/**
 * 部署 Job
 */
export async function deployJobApi(jobId: string, data: JobApi.DeployRequest) {
  return requestClient.post<JobApi.ExpertTask[]>(
    `/v1/jobs/${jobId}/deploy`,
    data,
  );
}

/**
 * 暂停 Job
 */
export async function pauseJobApi(jobId: string) {
  return requestClient.post<JobApi.Job>(`/v1/jobs/${jobId}/pause`);
}

/**
 * 恢复 Job
 */
export async function resumeJobApi(jobId: string) {
  return requestClient.post<JobApi.Job>(`/v1/jobs/${jobId}/resume`);
}

/**
 * 完成 Job
 */
export async function completeJobApi(jobId: string) {
  return requestClient.post<JobApi.Job>(`/v1/jobs/${jobId}/complete`);
}

/**
 * 测试 Job
 * 注意：AI 生成内容可能需要较长时间，设置 120 秒超时
 */
export async function testJobApi(jobId: string, data?: JobApi.TestRequest) {
  return requestClient.post<JobApi.TestResponse>(
    `/v1/jobs/${jobId}/test`,
    data || {},
    {
      timeout: 120_000, // 120 秒超时
    },
  );
}

/**
 * 获取 Job 关联的 ExpertTask 列表
 */
export async function getJobExpertTasksApi(jobId: string) {
  return requestClient.get<JobApi.ExpertTask[]>(
    `/v1/expert-tasks/job/${jobId}`,
  );
}

/**
 * 获取 ExpertConfig 详情（通过 code）
 */
export async function getExpertConfigApi(code: string) {
  return requestClient.get<JobApi.ExpertConfigBrief>(
    `/v1/expert-configs/code/${code}`,
  );
}

/**
 * 获取 ExpertConfig 列表
 */
export async function getExpertConfigListApi() {
  return requestClient.get<JobApi.ExpertConfigBrief[]>('/v1/expert-configs');
}

/**
 * 获取 Plugin 上下文列表
 */
export async function getPluginContextListApi(params?: {
  plugin_code?: string;
  variable_name?: string;
}) {
  return requestClient.get<JobApi.PluginContextOption[]>(
    `/v1/plugin-contexts`,
    { params },
  );
}

/**
 * 更新 ExpertTask
 */
export async function updateExpertTaskApi(
  taskId: number,
  data: {
    concurrent?: number;
    cron_expression?: string;
    misfire_policy?: number;
    remark?: string;
    status?: number;
  },
) {
  return requestClient.put<JobApi.ExpertTask>(
    `/v1/expert-tasks/${taskId}`,
    data,
  );
}

/**
 * 删除 ExpertTask
 */
export async function deleteExpertTaskApi(taskId: number) {
  return requestClient.delete(`/v1/expert-tasks/${taskId}`);
}

// ==================== 调度器管理 API ====================

export namespace SchedulerApi {
  /** 已注册的定时任务信息 */
  export interface ScheduledJob {
    id: string;
    name: string;
    next_run_time: null | string;
    trigger: string;
  }
}

/**
 * 获取所有已注册的定时任务
 */
export async function getScheduledJobsApi() {
  return requestClient.get<SchedulerApi.ScheduledJob[]>(
    '/v1/expert-tasks/scheduler/jobs',
  );
}

/**
 * 手动注册任务到调度器
 */
export async function registerTaskToSchedulerApi(taskId: number) {
  return requestClient.post(`/v1/expert-tasks/${taskId}/scheduler/register`);
}

/**
 * 从调度器移除任务
 */
export async function removeTaskFromSchedulerApi(taskId: number) {
  return requestClient.delete(`/v1/expert-tasks/${taskId}/scheduler/remove`);
}

/**
 * 暂停定时任务
 */
export async function pauseScheduledTaskApi(taskId: number) {
  return requestClient.post(`/v1/expert-tasks/${taskId}/scheduler/pause`);
}

/**
 * 恢复定时任务
 */
export async function resumeScheduledTaskApi(taskId: number) {
  return requestClient.post(`/v1/expert-tasks/${taskId}/scheduler/resume`);
}

/**
 * 立即执行一次任务
 */
export async function executeTaskNowApi(taskId: number) {
  return requestClient.post(`/v1/expert-tasks/${taskId}/execute`);
}

/**
 * 获取 ExpertTask 列表
 */
export async function getExpertTaskListApi(params?: {
  expert_config_code?: string;
  job_id?: string;
  limit?: number;
  skip?: number;
  status?: number;
}) {
  return requestClient.get<JobApi.ExpertTask[]>('/v1/expert-tasks', { params });
}
