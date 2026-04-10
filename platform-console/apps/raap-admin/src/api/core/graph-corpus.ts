import { requestClient } from '#/api/request';

export namespace GraphCorpusApi {
  // ==================== Node (图可视化需要) ====================
  export interface NodeItem {
    id: string; // 后端序列化为字符串，避免 JS 大整数精度丢失
    tenant_code: string;
    label: string;
    name: string;
    description?: string;
    corpus?: CorpusValue; // 语料列表
    ai_instruction?: Record<string, unknown>;
    properties?: Record<string, unknown>;
    is_active: number;
    is_deleted: number;
    created_by?: string;
    updated_by?: string;
    created_at?: string;
    updated_at?: string;
  }

  // ==================== Edge (图可视化需要) ====================
  export interface EdgeItem {
    id: string; // 后端序列化为字符串，避免 JS 大整数精度丢失
    tenant_code: string;
    source_node_id: string;
    target_node_id: string;
    relation_type: string;
    explanation?: string;
    meta_data?: Record<string, unknown>;
    is_active: number;
    is_deleted: number;
    created_by?: string;
    updated_by?: string;
    created_at?: string;
    updated_at?: string;
    // 冗余字段
    source_name?: string;
    target_name?: string;
    source_label?: string;
    target_label?: string;
  }

  // ==================== Stats ====================
  export interface GraphStats {
    total_nodes: number;
    total_edges: number;
    nodes_by_label: Record<string, number>;
    edges_by_relation: Record<string, number>;
  }

  // ==================== Visualization ====================
  export interface VisualizationParams {
    tenant_code?: string;
    min_degree?: number;
    limit?: number;
  }

  export interface VisualizationStats {
    total_nodes: number;
    total_edges: number;
    filtered_nodes: number;
    filtered_edges: number;
    min_degree: number;
  }

  export interface VisualizationResponse {
    nodes: NodeItem[];
    edges: EdgeItem[];
    stats: VisualizationStats;
  }

  // ==================== Node Neighbors (聚焦模式专用) ====================
  export interface NodeNeighborsResponse {
    center_node: NodeItem; // 中心节点
    neighbors: NodeItem[]; // 所有直接相连的邻居节点
    edges: EdgeItem[]; // 中心节点与邻居之间的所有边
  }

  // ==================== Corpus Template ====================
  export interface TemplateField {
    key: string;
    label: string;
    type: 'input' | 'select' | 'textarea';
    required: boolean;
    placeholder?: string;
    options?: string[];
  }

  export interface CorpusTemplate {
    id: number;
    code: string;
    name: string;
    category_type: string;
    fields: TemplateField[];
    description?: string;
    tenant_code: string;
    create_time?: string;
    update_time?: string;
    node_count?: number; // 使用该模板的节点数量
  }

  export interface CorpusTemplateListResponse {
    items: CorpusTemplate[];
    total: number;
  }

  // ==================== Structured Corpus (新格式) ====================
  export interface StructuredCorpus {
    template_code: string;
    fields: Record<string, string>;
  }

  // 旧格式语料
  export interface LegacyCorpusItem {
    text: string;
    weight?: number;
  }

  // 兼容新旧格式的语料类型
  export type CorpusValue = LegacyCorpusItem[] | StructuredCorpus;

  // ==================== Tree (树形结构) ====================
  // 树形节点结构
  export interface TreeNodeItem {
    id: string;
    name: string;
    label: string;
    description?: string;
    corpus?: unknown[];
    category_type?: string;
    level: number;
    sort_order: number;
    icon?: string;
    color?: string;
    is_active: number;
    children: TreeNodeItem[];
    // Scope 相关字段（新增）
    scope?: CorpusScope;
    scope_level?: 'brand' | 'global' | 'product';
    semantic_key?: string;
  }

  // ==================== Scope (语料适用范围) ====================
  export type ScopeLevel = 'brand' | 'global' | 'product';

  export interface CorpusScope {
    level: ScopeLevel;
    brand_codes: string[];
    product_names: string[];
  }

  export interface ScopeFilterParams {
    brand_code?: string;
    product_name?: string;
    include_global?: boolean;
    include_brand?: boolean;
    include_product?: boolean;
  }

  export interface ScopeUpgradeRequest {
    target_level: 'brand' | 'global';
  }

  export interface ScopeBatchUpdateRequest {
    node_ids: string[];
    scope: CorpusScope;
  }

  export interface ScopeStatistics {
    total: number;
    global: number;
    brand: number;
    product: number;
    no_scope: number;
    products: Record<string, number>;
  }
}

// ==================== Node APIs (图可视化专用) ====================

export interface NodeListParams {
  page?: number;
  page_size?: number;
  tenant_code?: string;
  label?: string;
  keyword?: string;
  is_active?: number;
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
  name: string;
  label: string;
  corpus?: unknown[];
  description?: string;
}

/**
 * 搜索节点列表（图可视化搜索功能需要）
 */
export async function listNodesApi(params?: NodeListParams) {
  return requestClient.get<NodeListResponse>('/v1/keyword-corpus/graph/nodes', {
    params,
  });
}

/**
 * 获取节点筛选选项（租户列表等）
 */
export async function getNodeOptionsApi() {
  return requestClient.get<{ labels: string[]; tenant_codes: string[] }>(
    '/v1/keyword-corpus/graph/nodes/options',
  );
}

export async function batchGetKeywordsApi(params: {
  include_children?: boolean;
  node_ids: string[];
  tenant_code?: string;
}) {
  const { tenant_code, ...body } = params;
  return requestClient.post<Record<string, BatchKeywordItem>>(
    '/v1/keyword-corpus/categories/keywords/batch-get',
    body,
    {
      params: tenant_code ? { tenant_code } : undefined,
    },
  );
}

/**
 * 获取节点及其所有直接邻居（聚焦模式专用，一次性返回）
 * 高效 API：一次请求返回中心节点 + 所有邻居节点 + 所有边
 */
export async function getNodeNeighborsApi(node_id: string) {
  return requestClient.get<GraphCorpusApi.NodeNeighborsResponse>(
    `/v1/keyword-corpus/graph/nodes/${node_id}/neighbors`,
    {
      timeout: 15_000, // 15 秒超时
    },
  );
}

// ==================== Stats APIs ====================
export async function getGraphStatsApi(tenant_code?: string) {
  return requestClient.get<GraphCorpusApi.GraphStats>(
    '/v1/keyword-corpus/graph/stats',
    {
      params: { tenant_code },
    },
  );
}

// ==================== Visualization APIs ====================
export async function getGraphVisualizationApi(
  params?: GraphCorpusApi.VisualizationParams,
) {
  return requestClient.get<GraphCorpusApi.VisualizationResponse>(
    '/v1/keyword-corpus/graph/visualization',
    {
      params,
      timeout: 30_000, // 30 秒超时，图数据可能较大
    },
  );
}

// ==================== Corpus Template APIs ====================
export async function listCorpusTemplatesApi(params?: {
  category_type?: string;
  tenant_code?: string;
}) {
  return requestClient.get<GraphCorpusApi.CorpusTemplateListResponse>(
    '/v1/keyword-corpus/corpus-templates',
    { params },
  );
}

/**
 * 获取所有分类类型（用于下拉选项）
 */
export async function getCorpusTemplateCategoryTypesApi(params?: {
  tenant_code?: string;
}) {
  return requestClient.get<string[]>(
    '/v1/keyword-corpus/corpus-templates/category-types',
    { params },
  );
}

export async function getCorpusTemplateApi(code: string) {
  return requestClient.get<GraphCorpusApi.CorpusTemplate>(
    `/v1/keyword-corpus/corpus-templates/${code}`,
  );
}

export async function getCorpusTemplateByTypeApi(
  categoryType: string,
  tenantCode?: string,
) {
  return requestClient.get<GraphCorpusApi.CorpusTemplate>(
    `/v1/keyword-corpus/corpus-templates/by-category/${categoryType}`,
    { params: { tenant_code: tenantCode } },
  );
}

// ==================== Category Tree APIs (树形结构) ====================

/**
 * 获取分类树（树形结构展示）
 */
export async function getCategoryTreeApi(params?: {
  // Scope 过滤参数（新增）
  brand_code?: string;
  category_type?: string;
  include_global?: boolean;
  product_name?: string;
  tenant_code?: string;
}) {
  return requestClient.get<GraphCorpusApi.TreeNodeItem[]>(
    '/v1/keyword-corpus/categories/tree',
    {
      params,
      timeout: 30_000, // 30 秒超时
    },
  );
}

// ==================== Scope APIs (语料范围管理) ====================

/**
 * 按 Scope 筛选语料节点
 */
export async function getNodesWithScopeFilterApi(params: {
  apply_fallback_dedup?: boolean;
  brand_code?: string;
  category_id?: string;
  include_brand?: boolean;
  include_global?: boolean;
  include_product?: boolean;
  product_name?: string;
  tenant_code: string;
}) {
  return requestClient.get<GraphCorpusApi.NodeItem[]>(
    '/v1/keyword-corpus/scope/nodes',
    { params },
  );
}

/**
 * 更新节点 Scope
 */
export async function updateNodeScopeApi(
  nodeId: string,
  scope: GraphCorpusApi.CorpusScope,
) {
  return requestClient.put(`/v1/keyword-corpus/scope/nodes/${nodeId}`, {
    scope,
  });
}

/**
 * 批量更新节点 Scope
 */
export async function batchUpdateScopeApi(
  data: GraphCorpusApi.ScopeBatchUpdateRequest,
) {
  return requestClient.post(
    '/v1/keyword-corpus/scope/nodes/batch-update',
    data,
  );
}

/**
 * 升级节点 Scope 级别（产品→品牌→全局）
 */
export async function upgradeNodeScopeApi(
  nodeId: string,
  targetLevel: 'brand' | 'global',
) {
  return requestClient.post(
    `/v1/keyword-corpus/scope/nodes/${nodeId}/upgrade`,
    {
      target_level: targetLevel,
    },
  );
}

/**
 * 获取 Scope 统计信息
 */
export async function getScopeStatisticsApi(tenantCode: string) {
  return requestClient.get<GraphCorpusApi.ScopeStatistics>(
    '/v1/keyword-corpus/scope/statistics',
    { params: { tenant_code: tenantCode } },
  );
}

/**
 * 获取可复用语料（被多个产品使用过的语料）
 */
export async function getReusableCorpusApi(
  tenantCode: string,
  minUsageCount: number = 2,
) {
  return requestClient.get<GraphCorpusApi.NodeItem[]>(
    '/v1/keyword-corpus/scope/reusable',
    { params: { tenant_code: tenantCode, min_usage_count: minUsageCount } },
  );
}

// ==================== Metadata APIs (关键词属性管理) ====================

export namespace MetadataApi {
  export type MetadataType = 'brand' | 'product' | 'tag' | 'tag_group';

  export interface MetadataItem {
    id: string;
    item_type: MetadataType;
    name: string;
    code?: string;
    description?: string;
    icon?: string;
    color?: string;
    sort_order: number;
    parent_id?: string;
    parent_name?: string;
    is_active: number;
    corpus_count: number;
    children_count: number;
    created_at?: string;
    updated_at?: string;
  }

  export interface MetadataTreeNode {
    id: string;
    key: string;
    title: string;
    name: string;
    code?: string;
    item_type: MetadataType;
    description?: string;
    icon?: string;
    color?: string;
    sort_order: number;
    is_active: number;
    corpus_count: number;
    children: MetadataTreeNode[];
  }

  export interface MetadataItemCreate {
    item_type: MetadataType;
    name: string;
    code?: string;
    description?: string;
    icon?: string;
    color?: string;
    sort_order?: number;
    parent_id?: string;
  }

  export interface MetadataItemUpdate {
    name?: string;
    code?: string;
    description?: string;
    icon?: string;
    color?: string;
    sort_order?: number;
    is_active?: number;
  }

  export interface SimpleOption {
    value: string;
    label: string;
    id?: string;
  }

  export interface MetadataStats {
    brand_count: number;
    product_count: number;
    tag_group_count: number;
    tag_count: number;
    global_corpus_count: number;
    brand_corpus_count: number;
    product_corpus_count: number;
  }
}

/**
 * 创建元数据项
 */
export async function createMetadataItemApi(
  tenantCode: string,
  data: MetadataApi.MetadataItemCreate,
) {
  return requestClient.post<MetadataApi.MetadataItem>(
    '/v1/keyword-corpus/metadata/items',
    data,
    { params: { tenant_code: tenantCode } },
  );
}

/**
 * 更新元数据项
 */
export async function updateMetadataItemApi(
  itemId: string,
  data: MetadataApi.MetadataItemUpdate,
) {
  return requestClient.put<MetadataApi.MetadataItem>(
    `/v1/keyword-corpus/metadata/items/${itemId}`,
    data,
  );
}

/**
 * 删除元数据项
 */
export async function deleteMetadataItemApi(itemId: string) {
  return requestClient.delete(`/v1/keyword-corpus/metadata/items/${itemId}`);
}

/**
 * 获取单个元数据项
 */
export async function getMetadataItemApi(itemId: string) {
  return requestClient.get<MetadataApi.MetadataItem>(
    `/v1/keyword-corpus/metadata/items/${itemId}`,
  );
}

/**
 * 列出元数据项
 */
export async function listMetadataItemsApi(params: {
  include_inactive?: boolean;
  item_type?: MetadataApi.MetadataType;
  parent_id?: string;
  tenant_code: string;
}) {
  return requestClient.get<MetadataApi.MetadataItem[]>(
    '/v1/keyword-corpus/metadata/items',
    { params },
  );
}

/**
 * 获取品牌-产品树
 */
export async function getBrandTreeApi(tenantCode: string) {
  return requestClient.get<MetadataApi.MetadataTreeNode[]>(
    '/v1/keyword-corpus/metadata/brands/tree',
    { params: { tenant_code: tenantCode } },
  );
}

/**
 * 获取品牌选项（下拉选择用）
 */
export async function getBrandOptionsApi(tenantCode: string) {
  return requestClient.get<MetadataApi.SimpleOption[]>(
    '/v1/keyword-corpus/metadata/brands/options',
    { params: { tenant_code: tenantCode } },
  );
}

/**
 * 获取产品选项（下拉选择用）
 */
export async function getProductOptionsApi(
  tenantCode: string,
  brandId?: string,
) {
  return requestClient.get<MetadataApi.SimpleOption[]>(
    '/v1/keyword-corpus/metadata/products/options',
    { params: { tenant_code: tenantCode, brand_id: brandId } },
  );
}

/**
 * 获取标签组-标签树
 */
export async function getTagTreeApi(tenantCode: string) {
  return requestClient.get<MetadataApi.MetadataTreeNode[]>(
    '/v1/keyword-corpus/metadata/tags/tree',
    { params: { tenant_code: tenantCode } },
  );
}

/**
 * 获取统一的标签树（合并品牌-产品树和标签组-标签树）
 */
export async function getMetadataTreeApi(tenantCode: string) {
  return requestClient.get<MetadataApi.MetadataTreeNode[]>(
    '/v1/keyword-corpus/metadata/tree',
    { params: { tenant_code: tenantCode } },
  );
}

/**
 * 获取标签选项（下拉选择用）
 */
export async function getTagOptionsApi(tenantCode: string, groupId?: string) {
  return requestClient.get<MetadataApi.SimpleOption[]>(
    '/v1/keyword-corpus/metadata/tags/options',
    { params: { tenant_code: tenantCode, group_id: groupId } },
  );
}

/**
 * 获取元数据统计
 */
export async function getMetadataStatsApi(tenantCode: string) {
  return requestClient.get<MetadataApi.MetadataStats>(
    '/v1/keyword-corpus/metadata/stats',
    { params: { tenant_code: tenantCode } },
  );
}

/**
 * AI 生成编码
 */
export interface GenerateCodeRequest {
  name: string;
}

export interface GenerateCodeResponse {
  code: string;
  name: string;
}

export async function generateCodeApi(request: GenerateCodeRequest) {
  return requestClient.post<GenerateCodeResponse>(
    '/v1/dapr/invoke/raap-service-ag/api/v1/generate',
    request,
  );
}

// ==================== Migration (环境迁移) ====================

/**
 * 迁移导出请求数据
 */
export interface MigrationExportRequest {
  include_archived: boolean;
}

/**
 * 迁移导出响应数据
 */
export interface MigrationExportResponse {
  tree: any[];
  templates: CorpusTemplate[];
  export_time: null | string;
  tenant_code: string;
}

/**
 * 迁移导入请求数据
 */
export interface MigrationImportRequest {
  tree: any[];
  templates: CorpusTemplate[];
  conflict_strategy: 'overwrite' | 'skip';
  skip_templates: boolean;
}

/**
 * 迁移导入响应数据
 */
export interface MigrationImportResponse {
  templates_created: number;
  templates_updated: number;
  templates_skipped: number;
  nodes_created: number;
  nodes_updated: number;
  nodes_skipped: number;
  errors: string[];
}

/**
 * 导出全部数据（用于环境迁移）
 */
export async function exportMigrationDataApi(
  tenantCode: string,
  includeArchived = false,
  categoryTypes?: string[],
) {
  return requestClient.post<MigrationExportResponse>(
    '/v1/keyword-corpus/categories/migration/export',
    {
      include_archived: includeArchived,
      category_types: categoryTypes,
    },
    { params: { tenant_code: tenantCode } },
  );
}

/**
 * 导入全部数据（用于环境迁移）
 */
export async function importMigrationDataApi(
  tenantCode: string,
  data: MigrationImportRequest,
) {
  return requestClient.post<MigrationImportResponse>(
    '/v1/keyword-corpus/categories/migration/import',
    data,
    { params: { tenant_code: tenantCode } },
  );
}
