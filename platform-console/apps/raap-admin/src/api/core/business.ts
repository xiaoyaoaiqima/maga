import { requestClient } from '#/api/request';

// ==================== 租户管理 API ====================

export namespace TenantApi {
  /** 租户状态 */
  export type TenantStatus = 'ACTIVE' | 'INACTIVE' | 'SUSPENDED';

  /** 租户 */
  export interface Tenant {
    id: number;
    tenant_code: string;
    tenant_name: string;
    contact_name: null | string;
    contact_phone: null | string;
    contact_email: null | string;
    quota_config: null | Record<string, any>;
    access_key?: null | string;
    secret_key?: null | string;
    status: TenantStatus;
    expire_time: null | string;
    remark: null | string;
    enabled: number;
    create_time: string;
    update_time: string;
    created_by: null | string;
    updated_by: null | string;
  }

  /** 创建租户参数 */
  export interface CreateParams {
    tenant_code: string;
    tenant_name: string;
    contact_name?: string;
    contact_phone?: string;
    contact_email?: string;
    quota_config?: Record<string, any>;
    status?: TenantStatus;
    expire_time?: string;
    remark?: string;
  }

  /** 更新租户参数 */
  export interface UpdateParams {
    tenant_name?: string;
    contact_name?: string;
    contact_phone?: string;
    contact_email?: string;
    quota_config?: Record<string, any>;
    status?: TenantStatus;
    expire_time?: string;
    remark?: string;
  }

  /** 简单项（用于下拉选择） */
  export interface SimpleItem {
    id: number;
    tenant_code: string;
    tenant_name: string;
  }

  /** 列表响应 */
  export interface ListResponse {
    total: number;
    items: Tenant[];
  }
}

/** 获取租户列表 */
export async function getTenantListApi(params?: {
  keyword?: string;
  limit?: number;
  skip?: number;
  status?: string;
}) {
  return requestClient.get<TenantApi.ListResponse>('/v1/tenants', { params });
}

/** 获取租户详情 */
export async function getTenantApi(id: number) {
  return requestClient.get<TenantApi.Tenant>(`/v1/tenants/${id}`);
}

/** 创建租户 */
export async function createTenantApi(data: TenantApi.CreateParams) {
  return requestClient.post<TenantApi.Tenant>('/v1/tenants', data);
}

/** 更新租户 */
export async function updateTenantApi(
  id: number,
  data: TenantApi.UpdateParams,
) {
  return requestClient.put<TenantApi.Tenant>(`/v1/tenants/${id}`, data);
}

/** 删除租户 */
export async function deleteTenantApi(id: number) {
  return requestClient.delete(`/v1/tenants/${id}`);
}

/** 获取租户简单列表（用于下拉选择） */
export async function getTenantSimpleListApi() {
  return requestClient.get<TenantApi.SimpleItem[]>('/v1/tenants/simple');
}

// ==================== 活动管理 API ====================

export namespace ActivityApi {
  /** 活动状态 */
  export type ActivityStatus =
    | 'CANCELLED'
    | 'COMPLETED'
    | 'DRAFT'
    | 'PAUSED'
    | 'PENDING'
    | 'RUNNING';

  /** 上线状态 */
  export type PublishStatus = 'DRAFT' | 'PUBLISHED';

  /** 问题选项 */
  export interface QuestionOption {
    id?: number;
    question_id?: number;
    /** 小程序展示可替换标签 */
    display_label: string;
    /** AIGC对应标签 */
    aigc_tag: string;
    /** 标签对应权重 */
    weight: number;
    /** 排序 */
    sort_order?: number;
    enabled?: number;
  }

  /** 活动问题 */
  export interface Question {
    id?: number;
    activity_id?: number;
    /** 问题内容 */
    question_text: string;
    /** 最小选择数（空则不限制） */
    min_select?: null | number;
    /** 最大选择数（空则不限制） */
    max_select?: null | number;
    /** 排序 */
    sort_order?: number;
    enabled?: number;
    /** 问题选项列表 */
    options: QuestionOption[];
  }

  /** 活动 */
  export interface Activity {
    id: number;
    activity_code: string;
    activity_name: string;
    tenant_id: number;
    tenant_name?: string;
    tenant_code?: string;
    /** Agent 编码列表（支持多个） */
    agent_code_list?: null | string[];
    channel: null | string;
    target_audience: null | string;
    budget: null | number;
    config_json: null | Record<string, any>;
    start_time: null | string;
    end_time: null | string;
    status: ActivityStatus;
    /** 上线状态 */
    publish_status?: PublishStatus;
    /** 上线时间 */
    publish_time?: null | string;
    /** 上线人 */
    publish_by?: null | string;
    remark: null | string;
    enabled: number;
    create_time: string;
    update_time: string;
    created_by: null | string;
    updated_by: null | string;
    /** 活动问题列表 */
    questions?: Question[];
  }

  /** 创建活动参数 */
  export interface CreateParams {
    activity_code: string;
    activity_name: string;
    tenant_id: number;
    /** Agent 编码列表（支持多个） */
    agent_code_list?: string[];
    channel?: string;
    target_audience?: string;
    budget?: number;
    config_json?: Record<string, any>;
    start_time?: string;
    end_time?: string;
    status?: ActivityStatus;
    remark?: string;
    /** 活动问题列表 */
    questions?: Question[];
  }

  /** 更新活动参数 */
  export interface UpdateParams {
    activity_name?: string;
    /** Agent 编码列表（支持多个） */
    agent_code_list?: string[];
    channel?: string;
    target_audience?: string;
    budget?: number;
    config_json?: Record<string, any>;
    start_time?: string;
    end_time?: string;
    status?: ActivityStatus;
    remark?: string;
    /** 活动问题列表（全量替换） */
    questions?: Question[];
  }

  /** 简单项 */
  export interface SimpleItem {
    id: number;
    activity_code: string;
    activity_name: string;
    tenant_id: number;
  }

  /** 列表响应 */
  export interface ListResponse {
    total: number;
    items: Activity[];
  }
}

/** 获取活动列表 */
export async function getActivityListApi(params?: {
  keyword?: string;
  limit?: number;
  skip?: number;
  status?: string;
  tenant_id?: number;
}) {
  return requestClient.get<ActivityApi.ListResponse>('/v1/activities', {
    params,
  });
}

/** 获取活动详情 */
export async function getActivityApi(id: number) {
  return requestClient.get<ActivityApi.Activity>(`/v1/activities/${id}`);
}

/** 创建活动 */
export async function createActivityApi(data: ActivityApi.CreateParams) {
  return requestClient.post<ActivityApi.Activity>('/v1/activities', data);
}

/** 更新活动 */
export async function updateActivityApi(
  id: number,
  data: ActivityApi.UpdateParams,
) {
  return requestClient.put<ActivityApi.Activity>(`/v1/activities/${id}`, data);
}

/** 更新活动状态 */
export async function updateActivityStatusApi(
  id: number,
  status: ActivityApi.ActivityStatus,
) {
  return requestClient.put<ActivityApi.Activity>(
    `/v1/activities/${id}/status`,
    { status },
  );
}

/** 删除活动 */
export async function deleteActivityApi(id: number) {
  return requestClient.delete(`/v1/activities/${id}`);
}

/** 获取活动简单列表 */
export async function getActivitySimpleListApi(tenantId?: number) {
  return requestClient.get<ActivityApi.SimpleItem[]>('/v1/activities/simple', {
    params: tenantId ? { tenant_id: tenantId } : undefined,
  });
}

// ==================== Agent 管理 API ====================

export namespace AgentApi {
  /** Agent 类型 */
  export type AgentType =
    | 'BATCH_GENERATION'
    | 'REALTIME_CHAT'
    | 'REPORT_ANALYSIS'
    | 'REVIEW_IMAGE';

  /** 上线状态 */
  export type PublishStatus = 'DRAFT' | 'PUBLISHED';

  /** Agent */
  export interface Agent {
    id: number;
    agent_code: string;
    agent_name: string;
    agent_type: AgentType;
    expert_config_code_list: string[];
    /**
     * 当这些打分型 Expert 返回 score==0 时，将内容判定为不可用；
     * - null/undefined：兼容旧逻辑（任意打分 Expert score==0 都判无效）
     * - []：不启用 score==0 判无效
     * - [..]：仅命中列表内 expert 才会触发
     */
    zero_score_invalid_expert_codes?: null | string[];
    default_model_code: null | string;
    default_config: null | Record<string, any>;
    description: null | string;
    input_schema: null | Record<string, any>;
    output_schema: null | Record<string, any>;
    tenant_id: null | number;
    tenant_name?: null | string;
    tenant_code?: null | string;
    rate_limit: null | Record<string, any>;
    /** 上线状态 */
    publish_status?: PublishStatus;
    /** 上线时间 */
    publish_time?: null | string;
    /** 上线人 */
    publish_by?: null | string;
    remark: null | string;
    enabled: number;
    create_time: string;
    update_time: string;
    created_by: null | string;
    updated_by: null | string;
  }

  /** 创建 Agent 参数 */
  export interface CreateParams {
    agent_code: string;
    agent_name: string;
    agent_type: AgentType;
    expert_config_code_list: string[];
    zero_score_invalid_expert_codes?: null | string[];
    default_model_code?: string;
    default_config?: Record<string, any>;
    description?: string;
    input_schema?: Record<string, any>;
    output_schema?: Record<string, any>;
    tenant_id?: number;
    rate_limit?: Record<string, any>;
    remark?: string;
  }

  /** 更新 Agent 参数 */
  export interface UpdateParams {
    agent_name?: string;
    agent_type?: AgentType;
    expert_config_code_list?: string[];
    zero_score_invalid_expert_codes?: null | string[];
    default_model_code?: string;
    default_config?: Record<string, any>;
    description?: string;
    input_schema?: Record<string, any>;
    output_schema?: Record<string, any>;
    rate_limit?: Record<string, any>;
    remark?: string;
  }

  /** 简单项 */
  export interface SimpleItem {
    id: number;
    agent_code: string;
    agent_name: string;
    agent_type: AgentType;
  }

  /** 列表响应 */
  export interface ListResponse {
    total: number;
    items: Agent[];
  }
}

/** 获取 Agent 列表 */
export async function getAgentListApi(params?: {
  agent_code?: string;
  agent_name?: string;
  agent_type?: string;
  page?: number;
  page_size?: number;
  tenant_id?: number;
}) {
  return requestClient.get<AgentApi.ListResponse>('/v1/agents', { params });
}

/** 获取 Agent 详情（通过编码） */
export async function getAgentApi(agentCode: string) {
  return requestClient.get<AgentApi.Agent>(`/v1/agents/${agentCode}`);
}

/** 获取 Agent 详情（通过 ID） */
export async function getAgentByIdApi(agentId: number) {
  return requestClient.get<AgentApi.Agent>(
    `/v1/agents/agent/detail/${agentId}`,
  );
}

/** 创建 Agent */
export async function createAgentApi(data: AgentApi.CreateParams) {
  return requestClient.post<AgentApi.Agent>('/v1/agents', data);
}

/** 更新 Agent */
export async function updateAgentApi(
  agentCode: string,
  data: AgentApi.UpdateParams,
) {
  return requestClient.put<AgentApi.Agent>(`/v1/agents/${agentCode}`, data);
}

/** 删除 Agent */
export async function deleteAgentApi(agentCode: string) {
  return requestClient.delete(`/v1/agents/${agentCode}`);
}

/** 获取 Agent 简单列表 */
export async function getAgentSimpleListApi(tenantId?: number) {
  return requestClient.get<AgentApi.SimpleItem[]>('/v1/agents/simple', {
    params: tenantId ? { tenant_id: tenantId } : undefined,
  });
}

/** 获取 Agent 类型列表 */
export async function getAgentTypesApi() {
  return requestClient.get<
    Array<{ description: string; name: string; type: AgentApi.AgentType }>
  >('/v1/agents/types');
}
