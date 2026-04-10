/**
 * 关键词策略 API
 *
 * v3 简化：
 * - 统一使用 defined_combinations 存储组合（前端直接管理）
 * - 删除 dimensions 和 combination_mode 字段
 */
import { requestClient } from '#/api/request';

export namespace ContentStrategyApi {
  // ==================== 前端内部 UI 类型 ====================

  /**
   * 维度配置（仅用于前端 UI 编辑）
   * 注意：此类型不会发送到后端，仅用于前端的维度编辑界面
   * 后端使用 node_pools + defined_combinations 结构
   */
  export interface DimensionConfig {
    dimension_type: string;
    dimension_name: string;
    select_mode: 'multiple' | 'single';
    required: boolean;
    node_ids: string[];
    select_strategy: 'all' | 'random' | 'weighted';
    select_count: number;
    weights?: Record<string, number>;
    order: number;
  }

  // ==================== 节点池和组合配置 ====================

  // 节点池配置（v3 新结构）
  export interface NodePoolConfig {
    node_ids: string[];
    select_mode: 'multiple' | 'single'; // single-节点分开使用 / multiple-节点合在一起使用
  }

  // 手动定义的组合
  export interface DefinedCombination {
    id: string;
    name: string;
    nodes: Record<string, string>; // {dimension_type: node_id}
  }

  // 高级设置
  export interface StrategySettings {
    include_corpus?: boolean;
  }

  // 关键词策略
  export interface ContentStrategy {
    id: string;
    name: string;
    description?: string;

    // 节点池和组合配置
    node_pools?: Record<string, NodePoolConfig>;
    defined_combinations?: DefinedCombination[];
    combinations_count?: number;

    // 组合规则
    max_combinations: number;
    settings?: StrategySettings;

    // 标签
    tags?: string[];

    // 其他
    tenant_code: string;
    is_active: number;
    created_by?: string;
    updated_by?: string;
    create_time?: string;
    update_time?: string;
  }

  // 创建请求
  export interface CreateRequest {
    name: string;
    description?: string;

    // 节点池和组合配置
    node_pools?: Record<string, NodePoolConfig>;
    defined_combinations?: DefinedCombination[];

    max_combinations?: number;
    settings?: StrategySettings;
    tags?: string[];
    tenant_code?: string;
  }

  // 更新请求
  export interface UpdateRequest {
    name?: string;
    description?: string;

    // 节点池和组合配置
    node_pools?: Record<string, NodePoolConfig>;
    defined_combinations?: DefinedCombination[];

    max_combinations?: number;
    settings?: StrategySettings;
    tags?: string[];
    is_active?: number;
  }

  // 列表响应
  export interface ListResponse {
    items: ContentStrategy[];
    page_info: {
      page: number;
      page_size: number;
      total: number;
      total_pages: number;
    };
  }

  // 节点信息
  export interface NodeInfo {
    id: string;
    name: string;
    label: string;
    corpus?: Array<Record<string, unknown>>;
    description?: string;
  }

  // 组合项（v2）
  export interface CombinationItem {
    id: string;
    name: string;
    nodes: Record<string, NodeInfo>;
  }

  // 获取组合响应
  export interface GetCombinationsResponse {
    strategy_id: string;
    strategy_name: string;
    combination_mode: 'manual'; // v3 统一使用 manual
    total_count: number;
    combinations: CombinationItem[];
  }

  // 可用分类（顶级分类节点）
  export interface AvailableDimension {
    dimension_type: string; // label 值
    dimension_name: string; // 显示名称
    node_id?: string;
    icon?: string;
    is_global?: boolean;
    tenant_code?: string;
    // 筛选属性
    brands?: string[]; // 品牌标签
    tags?: string[]; // 自由标签（活动、季节等）
  }

  // ==================== 旧版接口（保留向后兼容）====================

  export interface GenerateRequest {
    count?: number;
    overrides?: Record<string, string[]>;
  }

  export interface GenerateResponse {
    strategy_id: string;
    strategy_name: string;
    total_count: number;
    combinations: Array<{ nodes: Record<string, NodeInfo> }>;
  }
}

/**
 * 获取关键词策略列表
 */
export async function getContentStrategiesApi(params: {
  brand_code?: string;
  is_active?: number;
  name?: string;
  page?: number;
  page_size?: number;
  tags?: string[];
  tenant_code?: string;
}) {
  return requestClient.get<ContentStrategyApi.ListResponse>(
    '/v1/keyword-corpus/content-strategies',
    { params, paramsSerializer: 'repeat' },
  );
}

/**
 * 获取关键词策略详情
 */
export async function getContentStrategyApi(id: string) {
  return requestClient.get<ContentStrategyApi.ContentStrategy>(
    `/v1/keyword-corpus/content-strategies/${id}`,
  );
}

/**
 * 创建关键词策略
 */
export async function createContentStrategyApi(
  data: ContentStrategyApi.CreateRequest,
) {
  return requestClient.post<ContentStrategyApi.ContentStrategy>(
    '/v1/keyword-corpus/content-strategies',
    data,
  );
}

/**
 * 更新关键词策略
 */
export async function updateContentStrategyApi(
  id: string,
  data: ContentStrategyApi.UpdateRequest,
) {
  return requestClient.put<ContentStrategyApi.ContentStrategy>(
    `/v1/keyword-corpus/content-strategies/${id}`,
    data,
  );
}

/**
 * 删除关键词策略
 */
export async function deleteContentStrategyApi(id: string) {
  return requestClient.delete(`/v1/keyword-corpus/content-strategies/${id}`);
}

/**
 * 获取可用维度列表
 */
export async function getAvailableDimensionsApi(tenant_code?: string) {
  return requestClient.get<{
    dimensions: ContentStrategyApi.AvailableDimension[];
  }>('/v1/keyword-corpus/content-strategies/dimensions', {
    params: { tenant_code },
  });
}

/**
 * 获取策略组合列表（v2 新接口）
 */
export async function getCombinationsApi(
  id: string,
  include_corpus: boolean = true,
) {
  return requestClient.get<ContentStrategyApi.GetCombinationsResponse>(
    `/v1/keyword-corpus/content-strategies/${id}/combinations`,
    { params: { include_corpus } },
  );
}

/**
 * 生成关键词组合（旧接口，保留向后兼容）
 */
export async function generateCombinationsApi(
  id: string,
  data: ContentStrategyApi.GenerateRequest,
) {
  return requestClient.post<ContentStrategyApi.GenerateResponse>(
    `/v1/keyword-corpus/content-strategies/${id}/generate`,
    data,
  );
}

/**
 * 复制关键词策略
 */
export async function copyContentStrategyApi(
  id: string,
  data?: { new_description?: string; new_name?: string },
) {
  return requestClient.post<ContentStrategyApi.ContentStrategy>(
    `/v1/keyword-corpus/content-strategies/${id}/copy`,
    data || {},
  );
}

/**
 * 归档关键词策略（设置 is_active = 0）
 */
export async function archiveContentStrategyApi(id: string) {
  return requestClient.put<ContentStrategyApi.ContentStrategy>(
    `/v1/keyword-corpus/content-strategies/${id}`,
    { is_active: 0 },
  );
}

/**
 * 取消归档（启用）关键词策略（设置 is_active = 1）
 */
export async function unarchiveContentStrategyApi(id: string) {
  return requestClient.put<ContentStrategyApi.ContentStrategy>(
    `/v1/keyword-corpus/content-strategies/${id}`,
    { is_active: 1 },
  );
}

// ==================== 多策略合并（strategy_v3）====================

export namespace ContentStrategyApi {
  // 策略选择项
  export interface StrategySelectionItem {
    strategy_id: string;
    selected_combo_ids?: null | string[];
  }

  // 来源组合引用
  export interface SourceComboRef {
    strategy_id: string;
    combo_id: string;
  }

  // 来源策略引用
  export interface SourceStrategyRef {
    strategy_id: string;
    strategy_name: string;
  }

  // 合并后的组合项
  export interface MergedCombinationItem {
    id: string;
    name: string;
    source_combos: SourceComboRef[];
    merged_nodes: Record<string, NodeInfo>;
  }

  // 多策略合并请求
  export interface MergeRequest {
    strategy_selections: StrategySelectionItem[];
    include_corpus?: boolean;
    target_count?: number; // 目标组合数量（默认100，范围1-2000）
    sample_mode?: 'first' | 'primary_strategy' | 'random'; // 采样模式
    primary_strategy_id?: number; // 主策略ID（sample_mode=primary_strategy时必填）
  }

  // 多策略合并响应
  export interface MergeResponse {
    merged_dimensions: string[];
    dimension_conflicts: Array<{
      dimension: string;
      strategy_1_id: string;
      strategy_1_name: string;
      strategy_2_id: string;
      strategy_2_name: string;
    }>;
    source_strategies: SourceStrategyRef[];
    total_count: number;
    merged_combinations: MergedCombinationItem[];
  }
}

/**
 * 合并多个策略的组合（strategy_v3）
 */
export async function mergeStrategyCombinationsApi(
  data: ContentStrategyApi.MergeRequest,
) {
  return requestClient.post<ContentStrategyApi.MergeResponse>(
    '/v1/keyword-corpus/content-strategies/merge-combinations',
    data,
  );
}
