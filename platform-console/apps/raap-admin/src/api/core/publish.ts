/**
 * 上线管理 API
 *
 * 提供实体上线/下线管理功能
 */
import { requestClient } from '#/api/request';

// ==================== 类型定义 ====================

export namespace PublishApi {
  /** 上线状态 */
  export type PublishStatus = 'DRAFT' | 'PUBLISHED';

  /** 实体类型 */
  export type EntityType =
    | 'Activity'
    | 'Agent'
    | 'ExpertConfig'
    | 'Plugin'
    | 'PluginContext';

  /** 操作动作 */
  export type ModifyAction = 'allow' | 'confirm' | 'reject';

  /** 上线请求参数 */
  export interface PublishRequest {
    operator: string;
  }

  /** 下线请求参数 */
  export interface UnpublishRequest {
    operator: string;
  }

  /** 上线结果 */
  export interface PublishResult {
    success: boolean;
    message: string;
    errors?: string[];
    warnings?: string[];
    published_entities?: {
      activity?: string[];
      agent?: string[];
      expert_config?: string[];
      plugin?: string[];
      plugin_context?: string[];
    };
    publish_time?: string;
  }

  /** 下线结果 */
  export interface UnpublishResult {
    success: boolean;
    message: string;
    blockers?: string[];
  }

  /** 编辑/删除检查结果 */
  export interface ModifyCheckResult {
    allowed: boolean;
    action: ModifyAction;
    reason: string;
    references?: Array<{
      entity_id: number | string;
      entity_name: string;
      entity_type: string;
      reference_field: string;
    }>;
  }

  /** 上线状态查询结果 */
  export interface StatusResult {
    entity_id: string;
    entity_type: EntityType;
    is_published: boolean;
    publish_status: PublishStatus;
  }

  /** 依赖实体信息 */
  export interface DependencyEntity {
    code?: string;
    context_name?: string;
    current_status: PublishStatus;
    id?: number | string;
    name: string;
  }

  /** 上线预检查结果 */
  export interface PreviewResult {
    can_publish: boolean;
    dependencies?: {
      activity?: DependencyEntity;
      agent?: DependencyEntity;
      expert_configs?: DependencyEntity[];
      plugin_contexts?: DependencyEntity[];
      plugins?: DependencyEntity[];
    };
    errors?: string[];
    validation?: {
      errors: string[];
      is_valid: boolean;
      warnings: string[];
    };
  }

  /** 批量状态查询请求 */
  export interface BatchStatusRequest {
    entities: Array<{
      entity_id: string;
      entity_type: EntityType;
    }>;
  }

  /** 批量状态查询结果项 */
  export interface BatchStatusItem {
    entity_id: string;
    entity_type: EntityType;
    error?: string;
    is_published?: boolean;
    publish_status?: PublishStatus;
  }
}

// ==================== Activity 上线/下线 ====================

/** 上线 Activity 及其所有依赖 */
export async function publishActivityApi(
  activityId: number,
  data: PublishApi.PublishRequest,
) {
  return requestClient.post<PublishApi.PublishResult>(
    `/v1/publish/activity/${activityId}/publish`,
    data,
  );
}

/** 下线 Activity */
export async function unpublishActivityApi(
  activityId: number,
  data: PublishApi.UnpublishRequest,
) {
  return requestClient.post<PublishApi.UnpublishResult>(
    `/v1/publish/activity/${activityId}/unpublish`,
    data,
  );
}

/** 预检查 Activity 上线 */
export async function previewPublishActivityApi(activityId: number) {
  return requestClient.get<PublishApi.PreviewResult>(
    `/v1/publish/activity/${activityId}/preview`,
  );
}

// ==================== Agent 上线/下线 ====================

/** 上线 Agent 及其依赖 */
export async function publishAgentApi(
  agentCode: string,
  data: PublishApi.PublishRequest,
) {
  return requestClient.post<PublishApi.PublishResult>(
    `/v1/publish/agent/${agentCode}/publish`,
    data,
  );
}

/** 下线 Agent */
export async function unpublishAgentApi(
  agentCode: string,
  data: PublishApi.UnpublishRequest,
) {
  return requestClient.post<PublishApi.UnpublishResult>(
    `/v1/publish/agent/${agentCode}/unpublish`,
    data,
  );
}

// ==================== 编辑/删除权限检查 ====================

/** 检查实体是否可以编辑/删除 */
export async function checkCanModifyApi(
  entityType: PublishApi.EntityType,
  entityId: number | string,
) {
  return requestClient.get<PublishApi.ModifyCheckResult>(
    '/v1/publish/can-modify',
    {
      params: {
        entity_id: String(entityId),
        entity_type: entityType,
      },
    },
  );
}

// ==================== 状态查询 ====================

/** 查询实体上线状态 */
export async function getPublishStatusApi(
  entityType: PublishApi.EntityType,
  entityId: number | string,
) {
  return requestClient.get<PublishApi.StatusResult>('/v1/publish/status', {
    params: {
      entity_id: String(entityId),
      entity_type: entityType,
    },
  });
}

/** 批量查询实体上线状态 */
export async function batchGetPublishStatusApi(
  data: PublishApi.BatchStatusRequest,
) {
  return requestClient.post<PublishApi.BatchStatusItem[]>(
    '/v1/publish/status/batch',
    data,
  );
}
