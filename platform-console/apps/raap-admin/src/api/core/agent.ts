import { requestClient } from '#/api/request';

/**
 * Agent API
 */

/** Agent 列表项 */
export interface AgentListItem {
  /** Agent 编码 */
  code: string;
  /** Agent 名称 */
  name: string;
  /** 描述 */
  description: string;
  /** 状态 */
  status: 'active' | 'archived' | 'draft';
  /** 包含的 Expert 数量 */
  expert_count: number;
  /** 最后执行时间 */
  last_exec_time?: string;
  /** 最后执行结果 */
  last_exec_result?: {
    failed: number;
    success: number;
    total: number;
  };
  /** 配置完成度 */
  progress: number;
  /** 创建时间 */
  created_at: string;
  /** 更新时间 */
  updated_at: string;
}

/** Agent 详情 */
export interface AgentInfo {
  /** Agent 编码 */
  code: string;
  /** Agent 名称 */
  name: string;
  /** 描述 */
  description: string;
  /** 状态 */
  status: 'active' | 'archived' | 'draft';
  /** 配置 */
  config: {
    /** 执行顺序 */
    execution_order: string[];
    /** Expert 配置 */
    experts: Array<{
      code: string;
      name: string;
      plugin_config?: Record<string, unknown>;
      type: 'ANALYSIS' | 'CRITIC' | 'CUSTOM' | 'GENERATION' | 'SCORING';
    }>;
    /** 关键词配置 */
    keywords: Array<{
      dimension_id: string;
      dimension_name: string;
      selected_keywords: string[];
    }>;
    /** 策略配置 */
    strategies: Array<{
      combinations: Array<Record<string, string>>;
      id?: string;
      name: string;
    }>;
  };
  /** 创建时间 */
  created_at: string;
  /** 更新时间 */
  updated_at: string;
}

/** Agent 草稿 */
export interface AgentDraft {
  /** 草稿 ID */
  id: string;
  /** Agent 编码（最终创建时使用） */
  code?: string;
  /** 草稿名称 */
  name: string;
  /** 草稿描述 */
  description: string;
  /** 配置数据 */
  config: AgentInfo['config'];
  /** 创建时间 */
  created_at: string;
  /** 更新时间 */
  updated_at: string;
}

/** 分页响应 */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

/** 列表查询参数 */
export interface AgentListParams {
  page?: number;
  page_size?: number;
  status?: 'active' | 'all' | 'archived' | 'draft';
  keyword?: string;
}

/**
 * 获取 Agent 列表
 */
export async function getAgentListApi(params: AgentListParams = {}) {
  return requestClient.get<PaginatedResponse<AgentListItem>>('/v1/agent', {
    params,
  });
}

/**
 * 获取 Agent 详情
 */
export async function getAgentApi(code: string) {
  return requestClient.get<AgentInfo>(`/v1/agent/${code}`);
}

/**
 * 创建 Agent
 */
export async function createAgentApi(data: {
  config: AgentInfo['config'];
  description: string;
  name: string;
}) {
  return requestClient.post<AgentInfo>('/v1/agent', data);
}

/**
 * 更新 Agent
 */
export async function updateAgentApi(code: string, data: Partial<AgentInfo>) {
  return requestClient.put<AgentInfo>(`/v1/agent/${code}`, data);
}

/**
 * 删除 Agent
 */
export async function deleteAgentApi(code: string) {
  return requestClient.delete(`/v1/agent/${code}`);
}

/**
 * 归档 Agent
 */
export async function archiveAgentApi(code: string) {
  return requestClient.post(`/v1/agent/${code}/archive`);
}

/**
 * 取消归档 Agent
 */
export async function unarchiveAgentApi(code: string) {
  return requestClient.post(`/v1/agent/${code}/unarchive`);
}

/**
 * 复制 Agent
 */
export async function duplicateAgentApi(code: string, newName?: string) {
  return requestClient.post<AgentInfo>(`/v1/agent/${code}/duplicate`, {
    name: newName,
  });
}

/**
 * 获取 Agent 草稿列表
 */
export async function getAgentDraftsApi() {
  return requestClient.get<AgentDraft[]>('/v1/agent/drafts');
}

/**
 * 创建 Agent 草稿
 */
export async function createAgentDraftApi(data: {
  config: AgentInfo['config'];
  description?: string;
  name?: string;
}) {
  return requestClient.post<AgentDraft>('/v1/agent/drafts', data);
}

/**
 * 更新 Agent 草稿
 */
export async function updateAgentDraftApi(
  id: string,
  data: Partial<AgentDraft>,
) {
  return requestClient.put<AgentDraft>(`/v1/agent/drafts/${id}`, data);
}

/**
 * 删除 Agent 草稿
 */
export async function deleteAgentDraftApi(id: string) {
  return requestClient.delete(`/v1/agent/drafts/${id}`);
}

/**
 * 从草稿创建 Agent
 */
export async function createAgentFromDraftApi(
  id: string,
  data: {
    description: string;
    name: string;
  },
) {
  return requestClient.post<AgentInfo>(`/v1/agent/drafts/${id}/publish`, data);
}

/**
 * 获取 Agent 模板列表
 */
export async function getAgentTemplatesApi() {
  return requestClient.get<
    Array<{
      category: string;
      config: AgentInfo['config'];
      description: string;
      icon: string;
      id: string;
      name: string;
    }>
  >('/v1/agent/templates');
}

/**
 * 从模板创建 Agent 草稿
 */
export async function createAgentFromTemplateApi(templateId: string) {
  return requestClient.post<AgentDraft>(
    `/v1/agent/templates/${templateId}/draft`,
  );
}

/** 用户自定义模板 */
export interface UserTemplate {
  /** 模板 ID */
  id: string;
  /** 模板名称 */
  name: string;
  /** 模板描述 */
  description: string;
  /** 分类 */
  category: string;
  /** 图标 */
  icon: string;
  /** 默认配置 */
  defaultConfig: {
    experts?: Array<{ code: string; type: string }>;
    keywords?: Record<string, string[]>;
    strategies?: Array<{ id?: string; name: string }>;
  };
  /** 创建者 */
  created_by: string;
  /** 创建时间 */
  created_at: string;
  /** 使用次数 */
  usage_count: number;
}

/**
 * 获取用户自定义模板列表
 */
export async function getMyTemplatesApi() {
  return requestClient.get<UserTemplate[]>('/v1/agent/user-templates');
}

/**
 * 创建用户模板
 */
export async function createTemplateApi(data: {
  category: string;
  config: UserTemplate['defaultConfig'];
  description: string;
  name: string;
}) {
  return requestClient.post<UserTemplate>('/v1/agent/user-templates', data);
}

/**
 * 更新用户模板
 */
export async function updateTemplateApi(
  id: string,
  data: Partial<UserTemplate>,
) {
  return requestClient.put<UserTemplate>(
    `/v1/agent/user-templates/${id}`,
    data,
  );
}

/**
 * 删除用户模板
 */
export async function deleteTemplateApi(id: string) {
  return requestClient.delete(`/v1/agent/user-templates/${id}`);
}

/**
 * 从 Agent 创建模板
 */
export async function saveAsTemplateApi(agentCode: string) {
  return requestClient.post<UserTemplate>(
    `/v1/agent/${agentCode}/save-as-template`,
  );
}
