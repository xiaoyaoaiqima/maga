/**
 * Legacy graph corpus compatibility surface.
 *
 * The old keyword graph backend has been retired. These exports remain only so
 * historical screens can show a clear failure instead of breaking imports.
 */

const retiredMessage = '旧关键词图谱系统已下线，请使用业务规则包和系统提示词关键词链路。';

function retiredApi<T>(): Promise<T> {
  return Promise.reject(new Error(retiredMessage));
}

export namespace GraphCorpusApi {
  export interface LegacyCorpusItem {
    text: string;
    weight?: number;
  }

  export interface StructuredCorpus {
    fields: Record<string, string>;
    template_code: string;
  }

  export type CorpusValue = LegacyCorpusItem[] | StructuredCorpus | unknown[];

  export interface NodeItem {
    ai_instruction?: Record<string, unknown>;
    corpus?: CorpusValue;
    created_at?: string;
    created_by?: string;
    description?: string;
    id: string;
    is_active: number;
    is_deleted: number;
    label: string;
    name: string;
    properties?: Record<string, unknown>;
    tenant_code: string;
    updated_at?: string;
    updated_by?: string;
  }

  export interface EdgeItem {
    explanation?: string;
    id: string;
    is_active: number;
    is_deleted: number;
    relation_type: string;
    source_node_id: string;
    target_node_id: string;
    tenant_code: string;
  }

  export interface GraphStats {
    edges_by_relation: Record<string, number>;
    nodes_by_label: Record<string, number>;
    total_edges: number;
    total_nodes: number;
  }

  export interface VisualizationParams {
    limit?: number;
    min_degree?: number;
    tenant_code?: string;
  }

  export interface VisualizationResponse {
    edges: EdgeItem[];
    nodes: NodeItem[];
    stats: Record<string, number>;
  }

  export interface NodeNeighborsResponse {
    center_node: NodeItem;
    edges: EdgeItem[];
    neighbors: NodeItem[];
  }

  export interface TemplateField {
    key: string;
    label: string;
    options?: string[];
    placeholder?: string;
    required: boolean;
    type: 'input' | 'select' | 'textarea';
  }

  export interface CorpusTemplate {
    category_type: string;
    code: string;
    create_time?: string;
    description?: string;
    fields: TemplateField[];
    id: number;
    name: string;
    node_count?: number;
    tenant_code: string;
    update_time?: string;
  }

  export interface CorpusTemplateListResponse {
    items: CorpusTemplate[];
    total: number;
  }

  export type ScopeLevel = 'brand' | 'global' | 'product';

  export interface CorpusScope {
    brand_codes: string[];
    level: ScopeLevel;
    product_names: string[];
  }

  export interface TreeNodeItem {
    category_type?: string;
    children: TreeNodeItem[];
    color?: string;
    corpus?: unknown[];
    description?: string;
    icon?: string;
    id: string;
    is_active: number;
    label: string;
    level: number;
    name: string;
    scope?: CorpusScope;
    scope_level?: ScopeLevel;
    semantic_key?: string;
    sort_order: number;
  }

  export interface ScopeBatchUpdateRequest {
    node_ids: string[];
    scope: CorpusScope;
  }

  export interface ScopeStatistics {
    brand: number;
    global: number;
    no_scope: number;
    product: number;
    products: Record<string, number>;
    total: number;
  }
}

export namespace MetadataApi {
  export type MetadataType = 'brand' | 'product' | 'tag' | 'tag_group';

  export interface MetadataItem {
    children_count: number;
    code?: string;
    color?: string;
    corpus_count: number;
    description?: string;
    icon?: string;
    id: string;
    is_active: number;
    item_type: MetadataType;
    name: string;
    parent_id?: string;
    parent_name?: string;
    sort_order: number;
  }

  export interface MetadataTreeNode {
    children: MetadataTreeNode[];
    code?: string;
    color?: string;
    corpus_count: number;
    description?: string;
    icon?: string;
    id: string;
    is_active: number;
    item_type: MetadataType;
    key: string;
    name: string;
    sort_order: number;
    title: string;
  }

  export interface MetadataItemCreate {
    code?: string;
    color?: string;
    description?: string;
    icon?: string;
    item_type: MetadataType;
    name: string;
    parent_id?: string;
    sort_order?: number;
  }

  export interface MetadataItemUpdate {
    code?: string;
    color?: string;
    description?: string;
    icon?: string;
    is_active?: number;
    name?: string;
    sort_order?: number;
  }

  export interface SimpleOption {
    id?: string;
    label: string;
    value: string;
  }

  export interface MetadataStats {
    brand_count: number;
    global_corpus_count: number;
    product_count: number;
    tag_count: number;
    tag_group_count: number;
  }
}

export interface NodeListParams {
  is_active?: number;
  keyword?: string;
  label?: string;
  page?: number;
  page_size?: number;
  tenant_code?: string;
}

export interface NodeListResponse {
  items: GraphCorpusApi.NodeItem[];
  page_info: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
}

export interface BatchKeywordItem {
  corpus?: unknown[];
  description?: string;
  label: string;
  name: string;
}

export interface GenerateCodeRequest {
  name: string;
}

export interface GenerateCodeResponse {
  code: string;
  name: string;
}

export async function listNodesApi(..._args: any[]): Promise<NodeListResponse> {
  return retiredApi();
}

export async function getNodeOptionsApi(..._args: any[]): Promise<{ labels: string[]; tenant_codes: string[] }> {
  return retiredApi();
}

export async function batchGetKeywordsApi(..._args: any[]): Promise<Record<string, BatchKeywordItem>> {
  return Promise.resolve({});
}

export async function getNodeNeighborsApi(..._args: any[]): Promise<GraphCorpusApi.NodeNeighborsResponse> {
  return retiredApi();
}

export async function getGraphStatsApi(..._args: any[]): Promise<GraphCorpusApi.GraphStats> {
  return retiredApi();
}

export async function getGraphVisualizationApi(..._args: any[]): Promise<GraphCorpusApi.VisualizationResponse> {
  return retiredApi();
}

export async function listCorpusTemplatesApi(..._args: any[]): Promise<GraphCorpusApi.CorpusTemplateListResponse> {
  return Promise.resolve({ items: [], total: 0 });
}

export async function getCorpusTemplateCategoryTypesApi(..._args: any[]): Promise<string[]> {
  return Promise.resolve([]);
}

export async function getCorpusTemplateApi(..._args: any[]): Promise<GraphCorpusApi.CorpusTemplate> {
  return retiredApi();
}

export async function getCorpusTemplateByTypeApi(..._args: any[]): Promise<GraphCorpusApi.CorpusTemplate> {
  return retiredApi();
}

export async function getCategoryTreeApi(..._args: any[]): Promise<GraphCorpusApi.TreeNodeItem[]> {
  return retiredApi();
}

export async function getNodesWithScopeFilterApi(..._args: any[]): Promise<GraphCorpusApi.NodeItem[]> {
  return retiredApi();
}

export async function updateNodeScopeApi(..._args: any[]): Promise<unknown> {
  return retiredApi();
}

export async function batchUpdateScopeApi(..._args: any[]): Promise<unknown> {
  return retiredApi();
}

export async function upgradeNodeScopeApi(..._args: any[]): Promise<unknown> {
  return retiredApi();
}

export async function getScopeStatisticsApi(..._args: any[]): Promise<GraphCorpusApi.ScopeStatistics> {
  return retiredApi();
}

export async function getReusableCorpusApi(..._args: any[]): Promise<GraphCorpusApi.NodeItem[]> {
  return retiredApi();
}

export async function createMetadataItemApi(..._args: any[]): Promise<MetadataApi.MetadataItem> {
  return retiredApi();
}

export async function updateMetadataItemApi(..._args: any[]): Promise<MetadataApi.MetadataItem> {
  return retiredApi();
}

export async function deleteMetadataItemApi(..._args: any[]): Promise<unknown> {
  return retiredApi();
}

export async function getMetadataItemApi(..._args: any[]): Promise<MetadataApi.MetadataItem> {
  return retiredApi();
}

export async function listMetadataItemsApi(..._args: any[]): Promise<MetadataApi.MetadataItem[]> {
  return retiredApi();
}

export async function getBrandTreeApi(..._args: any[]): Promise<MetadataApi.MetadataTreeNode[]> {
  return retiredApi();
}

export async function getBrandOptionsApi(..._args: any[]): Promise<MetadataApi.SimpleOption[]> {
  return retiredApi();
}

export async function getProductOptionsApi(..._args: any[]): Promise<MetadataApi.SimpleOption[]> {
  return retiredApi();
}

export async function getTagTreeApi(..._args: any[]): Promise<MetadataApi.MetadataTreeNode[]> {
  return Promise.resolve([]);
}

export async function getMetadataTreeApi(..._args: any[]): Promise<MetadataApi.MetadataTreeNode[]> {
  return retiredApi();
}

export async function getTagOptionsApi(..._args: any[]): Promise<MetadataApi.SimpleOption[]> {
  return retiredApi();
}

export async function getMetadataStatsApi(..._args: any[]): Promise<MetadataApi.MetadataStats> {
  return retiredApi();
}

export async function generateCodeApi(..._args: any[]): Promise<GenerateCodeResponse> {
  return retiredApi();
}

export async function exportMigrationDataApi(..._args: any[]): Promise<unknown> {
  return retiredApi();
}

export async function importMigrationDataApi(..._args: any[]): Promise<unknown> {
  return retiredApi();
}
