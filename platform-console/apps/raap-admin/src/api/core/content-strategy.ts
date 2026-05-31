/**
 * Legacy content strategy compatibility surface.
 *
 * The old strategy backend has been retired. These exports remain only so
 * historical Job/Expert debugging screens can fail with a clear message
 * instead of breaking the console bundle.
 */

const retiredMessage = '旧关键词策略系统已下线，请使用业务规则包和系统提示词关键词链路。';

function retiredApi<T>(): Promise<T> {
  return Promise.reject(new Error(retiredMessage));
}

export namespace ContentStrategyApi {
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

  export interface NodePoolConfig {
    node_ids: string[];
    select_mode: 'multiple' | 'single';
  }

  export interface DefinedCombination {
    id: string;
    name: string;
    nodes: Record<string, string>;
  }

  export interface StrategySettings {
    include_corpus?: boolean;
  }

  export interface ContentStrategy {
    combinations_count?: number;
    create_time?: string;
    created_by?: string;
    defined_combinations?: DefinedCombination[];
    description?: string;
    dimensions?: DimensionConfig[];
    id: string;
    is_active: number;
    max_combinations: number;
    name: string;
    node_pools?: Record<string, NodePoolConfig>;
    settings?: StrategySettings;
    tags?: string[];
    tenant_code: string;
    update_time?: string;
    updated_by?: string;
  }

  export interface CreateRequest {
    defined_combinations?: DefinedCombination[];
    description?: string;
    dimensions?: DimensionConfig[];
    max_combinations?: number;
    name: string;
    node_pools?: Record<string, NodePoolConfig>;
    settings?: StrategySettings;
    tags?: string[];
    tenant_code?: string;
  }

  export interface UpdateRequest {
    defined_combinations?: DefinedCombination[];
    description?: string;
    dimensions?: DimensionConfig[];
    is_active?: number;
    max_combinations?: number;
    name?: string;
    node_pools?: Record<string, NodePoolConfig>;
    settings?: StrategySettings;
    tags?: string[];
  }

  export interface ListResponse {
    items: ContentStrategy[];
    page_info: {
      page: number;
      page_size: number;
      total: number;
      total_pages: number;
    };
  }

  export interface NodeInfo {
    corpus?: Array<Record<string, unknown>>;
    description?: string;
    id: string;
    label: string;
    name: string;
  }

  export interface CombinationItem {
    id: string;
    name: string;
    nodes: Record<string, NodeInfo>;
  }

  export interface GetCombinationsResponse {
    combination_mode: 'manual';
    combinations: CombinationItem[];
    strategy_id: string;
    strategy_name: string;
    total_count: number;
  }

  export interface AvailableDimension {
    brands?: string[];
    dimension_name: string;
    dimension_type: string;
    icon?: string;
    is_global?: boolean;
    node_id?: string;
    tags?: string[];
    tenant_code?: string;
  }

  export interface GenerateRequest {
    count?: number;
    overrides?: Record<string, string[]>;
  }

  export interface GenerateResponse {
    combinations: Array<{ nodes: Record<string, NodeInfo> }>;
    strategy_id: string;
    strategy_name: string;
    total_count: number;
  }

  export interface StrategySelectionItem {
    selected_combo_ids?: null | string[];
    strategy_id: string;
  }

  export interface SourceComboRef {
    combo_id: string;
    strategy_id: string;
  }

  export interface SourceStrategyRef {
    strategy_id: string;
    strategy_name: string;
  }

  export interface MergedCombinationItem {
    id: string;
    merged_nodes: Record<string, NodeInfo>;
    name: string;
    source_combos: SourceComboRef[];
  }

  export interface MergeRequest {
    include_corpus?: boolean;
    primary_strategy_id?: number;
    sample_mode?: 'first' | 'primary_strategy' | 'random';
    strategy_selections: StrategySelectionItem[];
    target_count?: number;
  }

  export interface MergeResponse {
    dimension_conflicts: Array<Record<string, string>>;
    merged_combinations: MergedCombinationItem[];
    merged_dimensions: string[];
    source_strategies: SourceStrategyRef[];
    total_count: number;
  }
}

export async function getContentStrategiesApi(..._args: any[]): Promise<ContentStrategyApi.ListResponse> {
  return retiredApi();
}

export async function getContentStrategyApi(..._args: any[]): Promise<ContentStrategyApi.ContentStrategy> {
  return retiredApi();
}

export async function createContentStrategyApi(..._args: any[]): Promise<ContentStrategyApi.ContentStrategy> {
  return retiredApi();
}

export async function updateContentStrategyApi(..._args: any[]): Promise<ContentStrategyApi.ContentStrategy> {
  return retiredApi();
}

export async function deleteContentStrategyApi(..._args: any[]): Promise<unknown> {
  return retiredApi();
}

export async function getAvailableDimensionsApi(..._args: any[]): Promise<{
  dimensions: ContentStrategyApi.AvailableDimension[];
}> {
  return retiredApi();
}

export async function getCombinationsApi(..._args: any[]): Promise<ContentStrategyApi.GetCombinationsResponse> {
  return retiredApi();
}

export async function generateCombinationsApi(..._args: any[]): Promise<ContentStrategyApi.GenerateResponse> {
  return retiredApi();
}

export async function copyContentStrategyApi(..._args: any[]): Promise<ContentStrategyApi.ContentStrategy> {
  return retiredApi();
}

export async function archiveContentStrategyApi(..._args: any[]): Promise<ContentStrategyApi.ContentStrategy> {
  return retiredApi();
}

export async function unarchiveContentStrategyApi(..._args: any[]): Promise<ContentStrategyApi.ContentStrategy> {
  return retiredApi();
}

export async function mergeStrategyCombinationsApi(..._args: any[]): Promise<ContentStrategyApi.MergeResponse> {
  return retiredApi();
}
