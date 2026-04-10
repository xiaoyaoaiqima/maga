<script setup lang="ts">
import type { TreeProps } from 'ant-design-vue';

import type { GraphCorpusApi } from '#/api/core/graph-corpus';
import type { LabelValue } from '#/components/label-selector';
import type { TableAction } from '#/components/table';

import { computed, onMounted, ref, watch } from 'vue';

import { Button, Card, CardHeader, Separator } from '@vben-core/shadcn-ui';

import {
  CopyOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  ExportOutlined,
  FileAddOutlined,
  FileTextOutlined,
  FolderAddOutlined,
  FolderOpenOutlined,
  FolderOutlined,
  MoreOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  TagOutlined,
  UploadOutlined,
} from '@ant-design/icons-vue';
import {
  Alert,
  Breadcrumb,
  Checkbox,
  Dropdown,
  Empty,
  Input,
  Menu,
  message,
  Modal,
  Popconfirm,
  Progress,
  Radio,
  RadioGroup,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Tree,
  TreeSelect,
  Upload,
} from 'ant-design-vue';

import {
  exportMigrationDataApi,
  getBrandOptionsApi,
  getCorpusTemplateApi,
  getCorpusTemplateByTypeApi,
  getProductOptionsApi,
  getTagOptionsApi,
  importMigrationDataApi,
  listCorpusTemplatesApi,
} from '#/api/core/graph-corpus';
import { requestClient } from '#/api/request';
import { LabelSelector } from '#/components/label-selector';
import { actionFactories, TableActions } from '#/components/table';
import { logger } from '#/utils/logger';

// 类型定义

// 语料项类型（结构化格式）
type CorpusItem = {
  fields: Record<string, string>;
  template_code: string;
};

interface CategoryTreeNode {
  id: string;
  key: string;
  title: string;
  name: string;
  label: string; // 维度分类标签: 人设, 场景, 卖点 等
  description?: string;
  corpus?: CorpusItem[]; // 节点的语料列表
  level?: number;
  sort_order?: number;
  icon?: string;
  color?: string;
  is_active?: number;
  children?: CategoryTreeNode[];
  // 统一标签结构（新格式）
  labels?: Record<string, string[]>; // 如 { brand: [...], product: [...], tag: [...], campaign: [...] }
  // 兼容旧格式
  tags?: string[]; // 业务标签（已弃用，请使用 labels）
  brands?: string[]; // 品牌名称（已弃用，请使用 labels）
  products?: string[]; // 产品名称（已弃用，请使用 labels）
}

interface KeywordItem {
  id: string;
  name: string;
  label: string;
  description?: string;
  properties?: Record<string, unknown>;
  is_active?: number;
  created_at?: string;
  updated_at?: string;
  _raw?: unknown; // 原始语料数据
  _index?: number; // 原始语料在 corpus 数组中的索引
}

// 状态
const loading = ref(false);
const treeData = ref<CategoryTreeNode[]>([]);
// 节点 ID 到节点的映射，用于快速查找（避免递归遍历）
const nodeMap = ref<Map<string, CategoryTreeNode>>(new Map());
// 节点 ID 到其父节点 ID 的映射，用于快速查找父节点
const parentMap = ref<Map<string, null | string>>(new Map());
const expandedKeys = ref<string[]>([]);
const selectedKeys = ref<string[]>([]);
const selectedNode = ref<CategoryTreeNode | null>(null);
const searchText = ref('');
const corpusSearchText = ref(''); // corpus 内容筛选
const lastUpdateTime = ref('');

// 品牌筛选（从后端动态加载）
const brandCode = ref('default'); // 默认品牌（只有一个品牌）
const brandOptions = ref<Array<{ id?: string; label: string; value: string }>>(
  [],
);
const brandLoading = ref(false);

// 产品选项（用于导入弹窗）
const productOptions = ref<Array<{ label: string; value: string }>>([]);
const productLoading = ref(false);

// 标签选项（用于导入弹窗和筛选）
const tagOptions = ref<Array<{ label: string; value: string }>>([]);
const tagLoading = ref(false);

// 标签筛选器
const selectedFilterTags = ref<string[]>([]);

// Scope 弹窗：产品选项（依赖弹窗选择的品牌）
const scopeProductOptions = ref<Array<{ label: string; value: string }>>([]);
const scopeProductLoading = ref(false);

// 归档状态筛选器
const searchStatus = ref<number | undefined>(1); // 归档状态筛选：undefined=全部, 1=启用, 0=归档

// 获取品牌列表
async function fetchBrandOptions() {
  brandLoading.value = true;
  try {
    const res = await getBrandOptionsApi('default');
    brandOptions.value = (res || []).map((item) => ({
      id: item.id, // 保存 id 字段，用于后续 API 调用
      value: item.value,
      label: item.label,
    }));

    // 不再自动选择第一个品牌，用户需要手动选择
  } catch (error) {
    logger.error('获取品牌列表失败:', error);
    message.error('获取品牌列表失败，请检查权限或服务状态');
    // 降级使用默认值，但不自动选择
    brandOptions.value = [{ value: 'default', label: '默认品牌' }];
  } finally {
    brandLoading.value = false;
  }
}

// 获取产品选项（从元数据 API 获取）
async function fetchProductOptions() {
  productLoading.value = true;
  try {
    // 直接获取所有产品（只有一个品牌，不需要筛选）
    const res = await getProductOptionsApi('default');

    productOptions.value = (res || []).map((item) => ({
      value: item.value,
      label: item.label,
    }));
  } catch (error) {
    logger.error('获取产品选项失败:', error);
    productOptions.value = [];
  } finally {
    productLoading.value = false;
  }
}

// 获取标签选项（从元数据 API 获取所有标签）
async function fetchTagOptions() {
  tagLoading.value = true;
  try {
    // 不传 group_id，获取所有标签组的标签
    const res = await getTagOptionsApi('default');
    // 使用 label 作为 value，因为 node.labels 中存储的是标签名称而非 ID
    tagOptions.value = (res || []).map((item) => ({
      value: item.label, // 使用标签名称作为值（与 node.labels 中的值匹配）
      label: item.label,
    }));
  } catch (error) {
    logger.error('获取标签选项失败:', error);
    tagOptions.value = [];
  } finally {
    tagLoading.value = false;
  }
}

async function fetchScopeProductOptions(brandValue?: string) {
  if (!brandValue) {
    scopeProductOptions.value = [];
    return;
  }
  scopeProductLoading.value = true;
  try {
    const brand = brandOptions.value.find((b) => b.value === brandValue);
    const brandId = brand?.id || brand?.value;
    const res = await getProductOptionsApi('default', brandId);
    scopeProductOptions.value = (res || []).map((item) => ({
      value: item.value,
      label: item.label,
    }));
  } catch (error) {
    logger.error('获取 Scope 产品选项失败:', error);
    scopeProductOptions.value = [];
  } finally {
    scopeProductLoading.value = false;
  }
}

// 关键词列表
const keywordLoading = ref(false);
const keywords = ref<KeywordItem[]>([]);
const keywordTotal = ref(0);
const keywordPage = ref(1);
const keywordPageSize = ref(20);
const keywordSearch = ref('');

// 弹窗
const categoryModalVisible = ref(false);
const categoryModalTitle = ref('新增分类');
const categoryForm = ref({
  id: '',
  name: '',
  label: '',
  description: '',
  parent_id: '',
  parent_name: '', // 父节点名称（仅用于显示）
  labels: {} as Record<string, string[]>, // 统一标签结构
  is_active: 1, // 归档状态：1=启用, 0=归档
});

// 用于 LabelSelector 的响应式数据
const categoryLabels = ref<LabelValue>({ labels: {} });
const categoryModalLoading = ref(false);

// 同步 categoryLabels 到 categoryForm.labels
watch(
  categoryLabels,
  (newVal) => {
    categoryForm.value.labels = newVal.labels || {};
  },
  { deep: true },
);

const siblingLabels = ref<string[]>([]); // 同级节点的 label 列表
const isAddingSubCategory = ref(false); // 是否是新增子节点（显示父节点选择器）

// 语料编辑弹窗
const corpusModalVisible = ref(false);
const corpusModalTitle = ref('新增语料');
const corpusForm = ref({
  nodeId: '', // 节点 ID
  index: -1, // 语料索引，-1 表示新增
  templateCode: '', // 使用的模板编码
  usePlainText: false, // 是否使用纯文本模式
  plainText: '', // 纯文本内容
  fields: {} as Record<string, string>, // 模板字段值
  customFields: [] as Array<{ key: string; value: string }>, // 自定义 key-value 字段
});
const corpusModalLoading = ref(false);
// 语料模板
const corpusTemplate = ref<GraphCorpusApi.CorpusTemplate | null>(null);
const corpusTemplateLoading = ref(false);
const corpusTemplateMissing = ref(false); // 标记模板是否缺失
const missingCategoryType = ref(''); // 缺失模板的分类类型
// 所有可用的语料模板列表
const allCorpusTemplates = ref<GraphCorpusApi.CorpusTemplate[]>([]);

// 快速创建模板状态
const quickCreateTemplateVisible = ref(false);
const quickCreateTemplateLoading = ref(false);
const quickCreateTemplateForm = ref({
  name: '',
  dimensionLabel: '', // 维度标签（如"人设"、"场景"），对应模板的 category_type
  description: '',
  fields: [
    { key: '', label: '', type: 'textarea', required: false, placeholder: '' },
  ] as Array<{
    key: string;
    label: string;
    placeholder: string;
    required: boolean;
    type: string;
  }>,
});

// 维度/分类类型配置（从后端动态加载）
interface DimensionGuide {
  type: string; // label
  name: string; // label 名称
  shortDesc: string; // 描述
  description: string; // 详细描述
  count: number; // 节点数量
  fields: string[]; // 模板字段（从模板获取）
  example: string;
  icon: typeof TagOutlined;
}

// 动态维度列表（从后端 labels API 获取）
const dimensionGuides = ref<DimensionGuide[]>([]);
const dimensionLoading = ref(false);

// 获取维度列表（从后端 labels API）
async function fetchDimensionGuides() {
  dimensionLoading.value = true;
  try {
    const labelsParams: Record<string, unknown> = {
      tenant_code: 'default', // 语料数据在 default 租户下
      exclude_keyword: true, // 排除 KEYWORD 类型
      _t: Date.now(), // 防止浏览器缓存
    };
    if (brandCode.value) {
      labelsParams.brand_code = brandCode.value;
    }
    const res = await requestClient.get<
      Array<{ count: number; description: string; label: string }>
    >('/v1/keyword-corpus/categories/labels', {
      params: labelsParams,
    });

    dimensionGuides.value = (res || []).map((item) => ({
      type: item.label,
      name: item.label,
      shortDesc: item.description || `${item.label} 类型`,
      description: item.description || `${item.label} 类型节点`,
      count: item.count,
      fields: [], // 字段从模板获取
      example: '',
      icon: TagOutlined,
    }));
  } catch (error) {
    logger.error('获取维度列表失败:', error);
  } finally {
    dimensionLoading.value = false;
  }
}

// CSV 导入
const importModalVisible = ref(false);
const importLoading = ref(false);
const importParentNodeId = ref<string | undefined>(undefined); // 目标父节点
const importDimensionType = ref<string>(''); // 导入的维度类型

// 按维度结构化导入
interface StructuredImportRow {
  nodeName: string;
  fields: Record<string, string>;
}
const importStructuredData = ref<StructuredImportRow[]>([]); // 结构化导入预览
const importConflictStrategy = ref<'append' | 'overwrite' | 'skip'>('append'); // 导入冲突策略
const importProgress = ref(0); // 导入进度 0-100

// 层级导入模式
const importMode = ref<'flat' | 'hierarchical'>('flat'); // flat: 单层导入, hierarchical: 层级导入
interface HierarchicalImportRow {
  path: string[]; // 层级路径
  name: string; // 节点名称
  fields: Record<string, string>; // 语料字段
}
const importHierarchicalData = ref<HierarchicalImportRow[]>([]); // 层级导入预览
const hierarchyColumns = ref<string[]>([]); // 检测到的层级列名

// 导入后批量打标签（使用 LabelSelector 组件）
const importLabels = ref<{ labels: Record<string, string[]> }>({ labels: {} });

// 重置导入属性
const resetImportProperties = () => {
  importLabels.value = { labels: {} };
};

// 语料批量操作
const selectedCorpusKeys = ref<string[]>([]);

// 节点多选（批量操作）
const checkedKeys = ref<string[]>([]);
const isCheckMode = ref(false); // 是否启用多选模式

// ==================== 环境迁移（全量导出/导入） ====================

const migrationModalVisible = ref(false); // 迁移弹窗
const migrationLoading = ref(false); // 迁移加载状态
const migrationMode = ref<'export' | 'import'>('export'); // 迁移模式
const migrationIncludeArchived = ref(false); // 是否包含归档数据
const migrationSelectedCategories = ref<string[]>([]); // 选中的分类（label值）
const migrationConflictStrategy = ref<'overwrite' | 'skip'>('skip'); // 冲突策略
const migrationSkipTemplates = ref(false); // 是否跳过模板
const migrationFileList = ref<any[]>([]); // 上传的文件列表

// 获取可选的分类列表（从树数据中提取顶级分类）
const migrationCategoryOptions = computed(() => {
  const options: Array<{ label: string; value: string }> = [];
  for (const node of treeData.value) {
    if (node.label && !options.some((o) => o.value === node.label)) {
      options.push({ label: node.name, value: node.label });
    }
  }
  return options;
});

// 全量导出数据
const handleExportAllData = async () => {
  logger.debug('[Export] 开始执行导出');
  migrationLoading.value = true;
  try {
    // 获取选中的分类，如果没有选中则导出全部
    const selectedCategories =
      migrationSelectedCategories.value.length > 0
        ? migrationSelectedCategories.value
        : undefined;

    logger.debug('[Export] 导出参数:', {
      tenantCode: 'default',
      includeArchived: migrationIncludeArchived.value,
      selectedCategories,
    });

    logger.debug('[Export] 正在调用 exportMigrationDataApi...');
    const res = await exportMigrationDataApi(
      'default',
      migrationIncludeArchived.value,
      selectedCategories,
    );

    logger.debug('[Export] API 返回结果:', res);

    if (!res) {
      logger.error('[Export] API 返回为空');
      message.error('导出失败：未返回数据');
      return;
    }

    // 生成 JSON 文件（requestClient 已经自动解包了 ResponseData.data）
    const jsonContent = JSON.stringify(res, null, 2);
    logger.debug('[Export] JSON 内容长度:', jsonContent.length);

    const blob = new Blob([jsonContent], {
      type: 'application/json;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const timestamp = new Date()
      .toISOString()
      .slice(0, 19)
      .replaceAll(':', '-');
    link.download = `keyword-corpus-migration-${timestamp}.json`;

    logger.debug('[Export] 触发下载:', link.download);
    link.click();
    URL.revokeObjectURL(url);

    logger.info('[Export] 导出成功');
    message.success('导出成功');
    migrationModalVisible.value = false;
  } catch (error) {
    logger.error('[Export] 导出失败:', error);
    message.error(`导出失败，请检查网络连接: ${error}`);
  } finally {
    logger.debug('[Export] 结束，migrationLoading = false');
    migrationLoading.value = false;
  }
};

// 全量导入数据
const handleImportAllData = async () => {
  logger.debug('[Import] 开始执行导入');
  if (migrationFileList.value.length === 0) {
    message.warning('请先选择要导入的 JSON 文件');
    return;
  }

  const file = migrationFileList.value[0].originFileObj;
  if (!file) {
    message.warning('文件读取失败');
    return;
  }

  logger.debug('[Import] 文件信息:', { name: file.name, size: file.size });

  migrationLoading.value = true;
  try {
    // 读取 JSON 文件
    const content = await file.text();
    logger.debug('[Import] 文件内容长度:', content.length);

    if (!content || typeof content !== 'string') {
      throw new Error('文件内容为空');
    }

    const data = JSON.parse(content) as any;
    logger.debug('[Import] 解析后的数据:', {
      treeCount: data.tree?.length,
      templatesCount: data.templates?.length,
    });

    // 验证数据格式
    if (
      !data.tree ||
      !Array.isArray(data.tree) ||
      !data.templates ||
      !Array.isArray(data.templates)
    ) {
      message.error('文件格式错误：缺少 tree 或 templates 字段');
      return;
    }

    logger.debug('[Import] 正在调用导入 API...');
    // 调用导入 API
    const res = await importMigrationDataApi('default', {
      tree: data.tree,
      templates: data.templates,
      conflict_strategy: migrationConflictStrategy.value,
      skip_templates: migrationSkipTemplates.value,
    });

    logger.debug('[Import] API 返回结果:', res);

    if (!res) {
      message.error('导入失败');
      return;
    }

    // 显示导入结果
    const result = res as any;
    const successParts = [];
    if (result.templates_created > 0)
      successParts.push(`创建模板 ${result.templates_created} 个`);
    if (result.templates_updated > 0)
      successParts.push(`更新模板 ${result.templates_updated} 个`);
    if (result.nodes_created > 0)
      successParts.push(`创建节点 ${result.nodes_created} 个`);
    if (result.nodes_updated > 0)
      successParts.push(`更新节点 ${result.nodes_updated} 个`);
    if (result.nodes_skipped > 0)
      successParts.push(`跳过节点 ${result.nodes_skipped} 个`);

    let successMsg = successParts.join('，');
    if (result.errors && result.errors.length > 0) {
      successMsg += `，但有 ${result.errors.length} 个错误`;
      logger.error('[Import] 导入错误:', result.errors);
    }

    logger.info('[Import] 导入成功:', successMsg);
    message.success(successMsg || '导入完成');

    // 等待一小段时间确保数据库事务完全提交
    await new Promise((resolve) => setTimeout(resolve, 500));

    console.warn('🔄 [Import] 正在刷新树数据...');
    // 刷新树数据（强制刷新，不使用缓存）
    loading.value = true;
    const params: Record<string, unknown> = {
      tenant_code: 'default',
      include_global: true,
      is_active: 1, // 只显示启用的节点
      _t: Date.now(),
      _force_refresh: true, // 添加强制刷新标记
    };

    try {
      const res = await requestClient.get<ApiTreeNode[]>(
        '/v1/keyword-corpus/categories/tree',
        { params },
      );
      treeData.value = transformTreeData(res || []);
      console.warn(
        '✅ [Import] 树数据刷新完成，节点数量:',
        treeData.value.length,
      );
    } catch (error) {
      logger.error('[Import] 刷新树数据失败:', error);
    } finally {
      loading.value = false;
    }

    // 关闭弹窗
    migrationModalVisible.value = false;
    migrationFileList.value = [];
  } catch (parseError) {
    logger.error('[Import] 导入失败:', parseError);
    message.error(`文件解析失败，请检查 JSON 格式是否正确: ${parseError}`);
  } finally {
    logger.debug('[Import] 结束，migrationLoading = false');
    migrationLoading.value = false;
  }
};

// 打开迁移弹窗
const handleOpenMigrationModal = (mode: 'export' | 'import') => {
  logger.debug('[OpenMigration] 设置模式为:', mode);
  migrationMode.value = mode;
  logger.debug('[OpenMigration] migrationMode.value:', migrationMode.value);
  migrationModalVisible.value = true;
};

// 批量设置 Scope
const batchScopeModalVisible = ref(false);
const batchScopeLoading = ref(false);
const batchScopeForm = ref<{
  brand_codes: string[];
  level: 'brand' | 'global' | 'product';
  product_names: string[];
}>({
  level: 'global',
  brand_codes: [],
  product_names: [],
});

// 节点复制
const copyModalVisible = ref(false);
const copyTargetNodeId = ref<string | undefined>(undefined);
const copyNodeData = ref<CategoryTreeNode | null>(null);
const copyLoading = ref(false);

// 注：Scope 升级变量已移除（properties 中不再使用 scope 字段）

// Scope 设置
const setScopeModalVisible = ref(false);
const setScopeNodeData = ref<CategoryTreeNode | null>(null);
const setScopeLoading = ref(false);
const setScopeForm = ref<{
  brand_codes: string[];
  level: 'brand' | 'global' | 'product';
  product_names: string[];
}>({
  level: 'global',
  brand_codes: [],
  product_names: [],
});

// 删除单个节点
const deleteNodeModalVisible = ref(false);
const deleteNodeLoading = ref(false);
const deleteNodeTarget = ref<CategoryTreeNode | null>(null);

// 删除子关键词
const deleteChildrenModalVisible = ref(false);
const deleteChildrenLoading = ref(false);
const deleteChildrenParent = ref<CategoryTreeNode | null>(null);
const deleteChildrenSelectedIds = ref<string[]>([]);

// 辅助函数：提取错误信息
function getErrorMessage(error: unknown): string {
  if (error && typeof error === 'object') {
    const err = error as Record<string, any>;

    // 直接从 error 对象提取（某些情况下 error 就是响应数据）
    if (err.detail) return err.detail;
    if (err.message && typeof err.message === 'string') return err.message;
    if (err.error) return err.error;

    // 尝试从 response.data 中提取
    const data = err.response?.data;
    if (typeof data === 'string') return data;
    if (data && typeof data === 'object') {
      if (data.detail) return data.detail;
      if (data.message) return data.message;
      if (data.error) return data.error;
    }
  }
  return '未知错误';
}

function getHttpStatus(error: unknown): number | undefined {
  if (!error || typeof error !== 'object') return;
  const err = error as Record<string, any>;
  const status = err.response?.status ?? err.status;
  if (typeof status === 'number') return status;
}

// 面包屑路径
const breadcrumbPath = computed(() => {
  if (!selectedNode.value) return [];

  const path: CategoryTreeNode[] = [];
  const findPath = (nodes: CategoryTreeNode[], target: string): boolean => {
    for (const node of nodes) {
      if (node.id === target) {
        path.push(node);
        return true;
      }
      if (
        node.children &&
        node.children.length > 0 &&
        findPath(node.children, target)
      ) {
        path.unshift(node);
        return true;
      }
    }
    return false;
  };

  findPath(treeData.value, selectedNode.value.id);
  return path;
});

// 过滤后的树数据（支持搜索文本、标签筛选和 corpus 内容筛选）
const filteredTreeData = computed(() => {
  const hasSearchText = !!searchText.value;
  const hasCorpusSearchText = !!corpusSearchText.value;
  const hasTagFilter = selectedFilterTags.value.length > 0;

  // 没有任何筛选条件
  if (!hasSearchText && !hasCorpusSearchText && !hasTagFilter)
    return treeData.value;

  const filterTree = (nodes: CategoryTreeNode[]): CategoryTreeNode[] => {
    return nodes
      .map((node) => {
        // 名称匹配
        const matchName =
          hasSearchText &&
          node.name.toLowerCase().includes(searchText.value.toLowerCase());

        // 标签匹配：检查节点的所有标签类型是否包含选中的任一标签
        let matchTags = false;
        if (hasTagFilter && node.labels) {
          // 遍历所有标签类型（tag、文章类型等）
          for (const tagType of Object.values(node.labels)) {
            if (
              Array.isArray(tagType) && // 检查该类型下的标签是否包含选中的任一标签
              selectedFilterTags.value.some((tag) => tagType.includes(tag))
            ) {
              matchTags = true;
              break;
            }
          }
        }

        // corpus 内容匹配
        let matchCorpus = false;
        if (hasCorpusSearchText && node.corpus) {
          const searchLower = corpusSearchText.value.toLowerCase();
          matchCorpus = node.corpus.some((corpus) => {
            const displayText = getCorpusDisplayText(
              corpus as Record<string, unknown>,
            );
            return displayText.toLowerCase().includes(searchLower);
          });
        }

        // 判断节点是否匹配
        const nodeMatches =
          (!hasSearchText || matchName) &&
          (!hasTagFilter || matchTags) &&
          (!hasCorpusSearchText || matchCorpus);

        // 如果当前节点匹配，保留所有子节点；否则递归过滤子节点
        let filteredChildren: CategoryTreeNode[];
        if (nodeMatches) {
          // 节点匹配，保留所有子节点
          filteredChildren = node.children || [];
        } else if (node.children) {
          // 节点不匹配，递归过滤子节点
          filteredChildren = filterTree(node.children);
        } else {
          // 没有子节点
          filteredChildren = [];
        }

        // 节点本身匹配，或者子节点有匹配
        if (nodeMatches || filteredChildren.length > 0) {
          return {
            ...node,
            children: filteredChildren,
          };
        }
        return null;
      })
      .filter(Boolean) as CategoryTreeNode[];
  };

  return filterTree(treeData.value);
});

// 父节点选择器的数据（转换为 TreeSelect 格式）
interface TreeSelectNode {
  value: string;
  title: string;
  label: string; // 维度标签
  children?: TreeSelectNode[];
}

const parentTreeData = computed((): TreeSelectNode[] => {
  const convert = (nodes: CategoryTreeNode[]): TreeSelectNode[] => {
    return nodes.map((node) => ({
      value: node.id,
      title: `${node.name} (${node.label})`,
      label: node.label,
      children:
        node.children && node.children.length > 0
          ? convert(node.children)
          : undefined,
    }));
  };
  return convert(treeData.value);
});

// 过滤后的父节点数据（只显示同一维度的节点）- 预留供后续使用
// const filteredParentTreeData = computed((): TreeSelectNode[] => {
//   const currentLabel = categoryForm.value.label;
//   if (!currentLabel) {
//     return parentTreeData.value; // 如果没有指定标签，返回全部
//   }
//   // 只返回匹配 label 的顶级节点及其子节点
//   return parentTreeData.value.filter((node) => node.label === currentLabel);
// });

// 父节点变化时获取同级 label - 预留供后续使用
// const handleParentChange = async (parentId: null | string) => {
//   if (parentId) {
//     await fetchSiblingLabels(parentId);
//     // 找到父节点，默认使用父节点的 label
//     const findNode = (
//       nodes: CategoryTreeNode[],
//       id: string,
//     ): CategoryTreeNode | null => {
//       for (const node of nodes) {
//         if (node.id === id) return node;
//         if (node.children) {
//           const found = findNode(node.children, id);
//           if (found) return found;
//         }
//       }
//       return null;
//     };
//     const parent = findNode(treeData.value, parentId);
//     if (parent) {
//       categoryForm.value.label = parent.label;
//     }
//   } else {
//     await fetchSiblingLabels(null);
//   }
// };

// 转换后端数据为 Tree 需要的格式
interface ApiTreeNode {
  id: string;
  name: string;
  label: string; // 维度分类标签: 人设, 场景, 卖点 等
  description?: string;
  corpus?: CorpusItem[]; // 节点的语料列表（结构化格式）
  level?: number;
  sort_order?: number;
  icon?: string;
  color?: string;
  is_active?: number;
  tags?: string[]; // 业务标签，如 ["高净值"]
  brands?: string[]; // 品牌名称，如 ["皇家美素佳儿"]
  products?: string[]; // 产品名称，如 ["旺玥"]
  children?: ApiTreeNode[];
}

const transformTreeData = (nodes: ApiTreeNode[]): CategoryTreeNode[] => {
  return nodes.map((node) => {
    // 转换旧格式（tags, brands, products）为新格式（labels）
    const convertedLabels: Record<string, string[]> = {};
    if (node.tags?.length) convertedLabels.tag = node.tags;
    if (node.brands?.length) convertedLabels.brand = node.brands;
    if (node.products?.length) convertedLabels.product = node.products;

    // 合并：保留原始 labels，用转换的 labels 补充
    const finalLabels = {
      ...(node as any).labels,
      ...convertedLabels,
    };

    return {
      ...node,
      key: node.id,
      title: node.name,
      labels: Object.keys(finalLabels).length > 0 ? finalLabels : undefined,
      children: node.children ? transformTreeData(node.children) : [],
    };
  });
};

// 构建节点 ID 到节点的映射（用于快速查找）
// 同时构建父节点映射
const buildNodeMap = (nodes: CategoryTreeNode[]) => {
  const map = new Map<string, CategoryTreeNode>();
  const pMap = new Map<string, null | string>();
  const traverse = (
    nodeList: CategoryTreeNode[],
    parentId: null | string = null,
  ) => {
    for (const node of nodeList) {
      map.set(node.id, node);
      pMap.set(node.id, parentId);
      if (node.children?.length) {
        traverse(node.children, node.id);
      }
    }
  };
  traverse(nodes);
  return { map, pMap };
};

// 获取关键词树（获取所有数据，筛选在前端做）
const fetchTree = async () => {
  loading.value = true;
  try {
    const params: Record<string, unknown> = {
      tenant_code: 'default', // 所有关键词数据都在 default 租户下
      include_global: true, // 始终获取全部数据，筛选在前端做
      is_active: searchStatus.value, // 归档状态筛选
      _t: Date.now(), // 防止浏览器缓存
    };

    const res = await requestClient.get<ApiTreeNode[]>(
      '/v1/keyword-corpus/categories/tree',
      { params },
    );
    treeData.value = transformTreeData(res || []);
    // 同步更新节点映射（用于快速查找）
    const { map, pMap } = buildNodeMap(treeData.value);
    nodeMap.value = map;
    parentMap.value = pMap;
    // 更新时间显示
    lastUpdateTime.value = new Date().toLocaleString('zh-CN', {
      hour12: false,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch (error) {
    logger.error('获取关键词树失败:', error);
    message.error('获取关键词树失败');
  } finally {
    loading.value = false;
  }
};

// 获取语料列表
// 将语料转换为显示文本（按模板字段顺序显示）
const getCorpusDisplayText = (
  corpus: Record<string, unknown> | string,
): string => {
  // 处理纯文本语料（字符串）
  if (typeof corpus === 'string') {
    return corpus;
  }

  // 处理结构化语料（有 template_code 和 fields）
  if ('fields' in corpus && corpus.fields) {
    const fields = corpus.fields as Record<string, string>;
    const templateCode = (corpus as { template_code?: string }).template_code;

    // 如果有模板，按模板定义的字段顺序显示
    if (templateCode) {
      const template = allCorpusTemplates.value.find(
        (t) => t.code === templateCode,
      );
      if (template && template.fields) {
        return template.fields
          .map((field) => {
            const value = fields[field.key];
            return value ? `【${field.label}】${value}` : '';
          })
          .filter(Boolean)
          .join('\n');
      }
    }

    // 没有模板时，按对象原顺序显示（兜底）
    return Object.entries(fields)
      .filter(([, v]) => v)
      .map(([k, v]) => `【${k}】${v}`)
      .join('\n');
  }
  // 处理旧格式语料（text 字段）
  if ('text' in corpus && corpus.text) {
    return String(corpus.text);
  }
  // 处理其他格式：尝试直接序列化
  try {
    const entries = Object.entries(corpus)
      .filter(([k, v]) => v && k !== 'template_code' && k !== 'id')
      .map(([k, v]) => `【${k}】${v}`);
    return entries.length > 0 ? entries.join('\n') : JSON.stringify(corpus);
  } catch {
    return '[无法解析的语料格式]';
  }
};

const fetchKeywords = async () => {
  if (!selectedNode.value) {
    keywords.value = [];
    keywordTotal.value = 0;
    return;
  }

  keywordLoading.value = true;
  try {
    // 使用节点自身的 corpus 字段
    const nodeCorpus = selectedNode.value.corpus;
    if (nodeCorpus && nodeCorpus.length > 0) {
      // 将语料转换为显示格式
      const items = nodeCorpus.map((c, index) => {
        const displayText = getCorpusDisplayText(c as Record<string, unknown>);
        return {
          id: `${selectedNode.value!.id}-corpus-${index}`,
          name: displayText, // 语料内容
          label: '语料',
          description: displayText,
          is_active: 1,
          // 保留原始数据用于编辑和删除
          _raw: c,
          _index: index, // 保存原始索引，用于删除操作
        };
      });

      // 简单的搜索过滤
      const filtered = keywordSearch.value
        ? items.filter((item) =>
            item.name.toLowerCase().includes(keywordSearch.value.toLowerCase()),
          )
        : items;

      keywords.value = filtered;
      keywordTotal.value = filtered.length;
    } else {
      keywords.value = [];
      keywordTotal.value = 0;
    }
  } catch (error) {
    logger.error('获取语料列表失败:', error);
    message.error('获取语料列表失败');
  } finally {
    keywordLoading.value = false;
  }
};

// 防抖搜索语料（watcher 必须在 fetchKeywords 定义之后）
let keywordSearchTimer: null | ReturnType<typeof setTimeout> = null;
watch(
  () => keywordSearch.value,
  () => {
    if (keywordSearchTimer) clearTimeout(keywordSearchTimer);
    keywordSearchTimer = setTimeout(() => {
      fetchKeywords();
    }, 300);
  },
);

// 选中节点
const onSelect: TreeProps['onSelect'] = (keys, info) => {
  if (keys.length > 0) {
    selectedKeys.value = keys as string[];
    selectedNode.value = info.node as unknown as CategoryTreeNode;
    keywordPage.value = 1;
    fetchKeywords();
  }
};

// 展开节点
const onExpand: TreeProps['onExpand'] = (keys) => {
  expandedKeys.value = keys as string[];
};

// 树节点图标
const getNodeIcon = (node: CategoryTreeNode) => {
  const hasChildren = node.children && node.children.length > 0;

  if (!hasChildren) {
    // 没有子节点，显示文件图标
    return FileTextOutlined;
  }

  // 有子节点，显示文件夹图标（展开/关闭状态）
  return expandedKeys.value.includes(node.id)
    ? FolderOpenOutlined
    : FolderOutlined;
};

// 计算节点的语料数量（包含子节点）
const getCorpusCount = (node: CategoryTreeNode): number => {
  let count = node.corpus?.length || 0;
  if (node.children) {
    for (const child of node.children) {
      count += getCorpusCount(child);
    }
  }
  return count;
};

// 复制节点名称到剪贴板
function handleCopyNodeName(name: string, event: MouseEvent) {
  event.stopPropagation();
  navigator.clipboard
    .writeText(name)
    .then(() => {
      message.success(`已复制: ${name}`);
    })
    .catch(() => {
      message.error('复制失败');
    });
}

const expandedTagNodes = ref<Record<string, boolean>>({});

function isNodeTagsExpanded(nodeId: string): boolean {
  return !!expandedTagNodes.value[nodeId];
}

function toggleNodeTags(nodeId: string) {
  expandedTagNodes.value[nodeId] = !expandedTagNodes.value[nodeId];
}

function getVisibleItems(
  items: string[] | undefined,
  maxCount: number,
  isExpanded: boolean,
): string[] {
  const safeItems = items || [];
  return isExpanded ? safeItems : safeItems.slice(0, maxCount);
}

function getHiddenCount(
  items: string[] | undefined,
  maxCount: number,
  isExpanded: boolean,
): number {
  const safeItems = items || [];
  return isExpanded ? 0 : Math.max(0, safeItems.length - maxCount);
}

// 将 tag 数组返回（用于树节点显示）
// 后端现在直接返回标签名称，不再需要 ID 转换
function getTagNames(tagIds: string[] | undefined): string[] {
  return tagIds || [];
}

// 检查节点名称是否匹配搜索（用于高亮）
const isNodeMatch = (node: CategoryTreeNode): boolean => {
  if (!searchText.value) return false;
  return node.name.toLowerCase().includes(searchText.value.toLowerCase());
};

// 拖拽排序
const handleDrop: TreeProps['onDrop'] = async (info) => {
  const dragNode = info.dragNode as unknown as CategoryTreeNode;
  const dropNode = info.node as unknown as CategoryTreeNode;
  const dropPosition = info.dropPosition;
  const dropToGap = info.dropToGap;

  // 计算目标父节点
  let targetParentId: null | string = null;

  if (dropToGap) {
    // 拖到节点之间（同级）
    // 使用 parentMap 快速查找父节点
    targetParentId = parentMap.value.get(dropNode.id) || null;

    // 调试：如果找不到父节点，记录日志并阻止操作
    if (!targetParentId) {
      console.error(
        '[拖拽排序] 无法找到目标节点的父节点，这可能是因为数据结构问题',
        {
          dropNodeId: dropNode.id,
          dropNodeName: dropNode.name,
          dragNodeId: dragNode.id,
          dragNodeName: dragNode.name,
        },
      );
      message.error('无法完成移动：找不到目标父节点，请刷新页面后重试');
      return;
    }
  } else {
    // 拖到节点上（成为子节点）
    targetParentId = dropNode.id;
  }

  try {
    // 使用 parentMap 快速查找原始父节点
    const originalParentId = parentMap.value.get(dragNode.id) || null;

    // 业务约束：一个 label 只能有一个顶级节点（root）
    // 只有当真正"从非顶层移动到顶层"时才检查
    const isMovingToRoot = targetParentId === null && originalParentId !== null;
    if (isMovingToRoot) {
      const dragLabel = (dragNode.label || '').trim();
      const existingRoot = treeData.value.find(
        (n) => n.label === dragLabel && n.id !== dragNode.id,
      );
      if (dragLabel && existingRoot) {
        message.warning(
          `禁止移动到顶层：label「${dragLabel}」已存在顶级节点「${existingRoot.name}」，一个 label 只能有一个顶级节点`,
        );
        return;
      }
    }

    // 业务约束：禁止跨 label 拖动
    // 获取目标父节点的 label
    let targetParentLabel = '';
    if (targetParentId === null) {
      // 移动到顶层，目标 label 为节点自己的 label
      targetParentLabel = dragNode.label || '';
    } else {
      // 使用 nodeMap 快速查找目标父节点的 label
      const targetParent = nodeMap.value.get(targetParentId);
      targetParentLabel = targetParent?.label || '';
    }

    // 比较 label，不同则禁止拖动
    const dragLabel = (dragNode.label || '').trim();
    if (targetParentLabel && dragLabel !== targetParentLabel) {
      message.warning(
        `禁止跨 label 拖动：节点 label 为「${dragLabel}」，目标位置 label 为「${targetParentLabel}」`,
      );
      return;
    }

    await requestClient.post('/v1/keyword-corpus/categories/move', {
      node_id: dragNode.id,
      target_parent_id: targetParentId,
      drop_node_id: dropNode.id,
      drop_position: dropPosition,
    });
    message.success('移动成功');
    fetchTree();
  } catch (error) {
    logger.error('移动失败:', error);
    const errorMsg = getErrorMessage(error);
    message.error(`移动失败：${errorMsg}`);
  }
};

// 获取同级节点的 label 列表
const fetchSiblingLabels = async (parentId: null | string) => {
  try {
    const params: Record<string, string> = {
      tenant_code: 'default', // 语料数据在 default 租户下
    };
    if (brandCode.value) {
      params.brand_code = brandCode.value;
    }
    if (parentId) {
      params.parent_id = parentId;
    }
    const res = await requestClient.get<string[]>(
      '/v1/keyword-corpus/categories/sibling-labels',
      { params },
    );
    siblingLabels.value = res || [];
  } catch (error) {
    logger.error('获取同级 label 失败:', error);
    siblingLabels.value = [];
  }
};

// 新增顶层节点
const handleAddRootCategory = async () => {
  isAddingSubCategory.value = false;
  categoryModalTitle.value = '新增顶层节点';
  categoryForm.value = {
    id: '',
    name: '',
    label: '',
    description: '',
    parent_id: '',
    parent_name: '',
    labels: {},
    is_active: 1,
  };
  // 同时初始化 LabelSelector 的数据
  categoryLabels.value = { labels: {} };
  await fetchSiblingLabels(null);
  categoryModalVisible.value = true;
};

// 新增子节点（从树节点菜单触发）
const handleAddSubCategory = async (parent: CategoryTreeNode) => {
  isAddingSubCategory.value = true;
  categoryModalTitle.value = `新增子节点 - ${parent.name}`;
  categoryForm.value = {
    id: '',
    name: '',
    label: parent.label || '', // 自动使用父节点的关键词类型
    description: '',
    parent_id: parent.id,
    parent_name: parent.name, // 保存父节点名称用于显示
    labels: {},
    is_active: 1,
  };
  // 同时初始化 LabelSelector 的数据
  categoryLabels.value = { labels: {} };
  await fetchSiblingLabels(parent.id);
  categoryModalVisible.value = true;
};

// 获取父节点名称（用于显示）
const getParentNodeName = (parentId: string | undefined): string => {
  if (!parentId) return '';
  const findNode = (
    nodes: CategoryTreeNode[],
    targetId: string,
  ): CategoryTreeNode | null => {
    for (const node of nodes) {
      if (node.id === targetId) return node;
      if (node.children) {
        const found = findNode(node.children, targetId);
        if (found) return found;
      }
    }
    return null;
  };
  const node = findNode(treeData.value, parentId);
  return node?.name || categoryForm.value.parent_name || '';
};

// 编辑分类
const handleEditCategory = (node: CategoryTreeNode) => {
  categoryModalTitle.value = '编辑分类';
  categoryForm.value = {
    id: node.id,
    name: node.name,
    label: node.label || '',
    description: node.description || '',
    parent_id: '',
    parent_name: '',
    labels: node.labels || {},
    is_active: node.is_active ?? 1,
  };
  // 同时更新 LabelSelector 的数据
  categoryLabels.value = { labels: node.labels || {} };
  siblingLabels.value = []; // 编辑时不需要同级 label 建议
  categoryModalVisible.value = true;
};

// 保存分类
const handleSaveCategory = async () => {
  if (!categoryForm.value.name.trim()) {
    message.warning('请输入名称');
    return;
  }

  if (!categoryForm.value.label.trim()) {
    message.warning('请输入关键词类型');
    return;
  }

  categoryModalLoading.value = true;
  try {
    if (categoryForm.value.id) {
      // 更新
      // 业务约束：一个 label 只能有一个顶级节点（root）
      // 编辑时如果当前节点是顶层节点，且 label 变更为另一个顶层节点的 label，则阻止
      const currentNode = treeData.value.find(
        (n) => n.id === categoryForm.value.id,
      );
      const isRootNode = !!currentNode;
      if (isRootNode) {
        const nextLabel = categoryForm.value.label.trim();
        const conflictRoot = treeData.value.find(
          (n) => n.label === nextLabel && n.id !== categoryForm.value.id,
        );
        if (nextLabel && conflictRoot) {
          message.warning(
            `禁止保存：label「${nextLabel}」已存在顶级节点「${conflictRoot.name}」，一个 label 只能有一个顶级节点`,
          );
          return;
        }
      }

      await requestClient.put(
        `/v1/keyword-corpus/categories/${categoryForm.value.id}`,
        {
          name: categoryForm.value.name,
          label: categoryForm.value.label || undefined,
          description: categoryForm.value.description,
          labels: categoryForm.value.labels,
          is_active: categoryForm.value.is_active,
        },
      );
      message.success('分类更新成功');

      // 优化：只更新对应节点的数据，不重新加载整个树
      const updateNodeInTree = (nodes: CategoryTreeNode[]): boolean => {
        for (const node of nodes) {
          if (node.id === categoryForm.value.id) {
            // 更新节点的数据
            node.name = categoryForm.value.name;
            node.label = categoryForm.value.label || node.label;
            node.description = categoryForm.value.description;
            node.labels = categoryForm.value.labels;
            node.is_active = categoryForm.value.is_active;
            // 同时更新 selectedNode（如果当前选中的是这个节点）
            if (selectedNode.value && selectedNode.value.id === node.id) {
              selectedNode.value.name = node.name;
              selectedNode.value.label = node.label;
              selectedNode.value.description = node.description;
              selectedNode.value.labels = node.labels;
              selectedNode.value.is_active = node.is_active;
            }
            return true;
          }
          if (node.children && updateNodeInTree(node.children)) {
            return true;
          }
        }
        return false;
      };

      updateNodeInTree(treeData.value);
    } else {
      // 创建
      // 注意：label 唯一性校验由后端处理，避免因前端筛选导致的不准确判断

      const createParams: Record<string, string> = { tenant_code: 'default' };
      if (brandCode.value) {
        createParams.brand_code = brandCode.value;
      }
      await requestClient.post(
        '/v1/keyword-corpus/categories',
        {
          name: categoryForm.value.name,
          label: categoryForm.value.label || undefined,
          description: categoryForm.value.description,
          parent_id: categoryForm.value.parent_id || undefined,
          labels: categoryForm.value.labels,
        },
        { params: createParams }, // 语料数据在 default 租户下
      );
      message.success('分类创建成功');

      // 创建顶级节点时，检测是否存在对应的语料模板（用 label 匹配）
      const isTopLevel = !categoryForm.value.parent_id;
      const newLabel = categoryForm.value.label?.trim();
      if (isTopLevel && newLabel) {
        try {
          await getCorpusTemplateByTypeApi(newLabel, 'default');
          // 模板存在，不需要额外操作
        } catch {
          // 模板不存在，引导用户创建
          categoryModalVisible.value = false;
          fetchTree();

          // 延迟提示，让用户先看到创建成功
          setTimeout(() => {
            Modal.confirm({
              title: '是否创建语料模板？',
              content: `您创建了新的维度「${newLabel}」，该维度尚未配置语料模板。创建模板后才能添加结构化语料。`,
              okText: '立即创建',
              cancelText: '稍后再说',
              onOk: () => {
                openQuickCreateTemplate(newLabel);
              },
            });
          }, 300);
          return; // 提前返回，避免重复执行后续代码
        }
      }
    }

    categoryModalVisible.value = false;

    // 只有创建新节点时才需要重新加载整个树（因为新增了节点）
    // 更新操作已经在上面处理了，不需要重新加载
    if (!categoryForm.value.id) {
      const isTopLevel = !categoryForm.value.parent_id;
      const newLabel = categoryForm.value.label?.trim();
      fetchTree();
      // 如果是顶级节点，刷新维度列表（因为新增了新的维度）
      if (isTopLevel && newLabel) {
        fetchDimensionGuides();
      }
    }
  } catch (error) {
    logger.error('保存分类失败:', error);
    const httpStatus = getHttpStatus(error);
    if (httpStatus === 409) {
      const name = categoryForm.value.name.trim();
      const label = categoryForm.value.label.trim();
      message.warning(
        `分类重名：在「${label}」下已存在「${name}」。请修改名称或先删除/重命名旧分类后再试。`,
      );
      return;
    }
    const errorMsg = getErrorMessage(error);
    // "已存在"类错误已由全局拦截器用 warning 处理，这里不重复提示
    if (!errorMsg.includes('已存在')) {
      message.error(`保存分类失败：${errorMsg}`);
    }
  } finally {
    categoryModalLoading.value = false;
  }
};

// 归档分类
const handleArchiveNode = async (node: CategoryTreeNode) => {
  if (!node) return;

  deleteNodeLoading.value = true;
  try {
    const response = await requestClient.put(
      `/v1/keyword-corpus/categories/${node.id}`,
      {
        is_active: 0, // 设置为归档状态
      },
    );

    // 检查响应，确认更新成功
    if (response?.data?.is_active === 0) {
      message.success('分类已归档');
    } else {
      message.warning('归档操作可能未生效，请刷新页面查看');
    }

    // 如果归档的是当前选中的节点，清空选中状态
    if (selectedNode.value?.id === node.id) {
      selectedNode.value = null;
      selectedKeys.value = [];
      keywords.value = [];
    }

    // 重新获取树数据（使用当前筛选状态）
    await fetchTree();

    // 如果当前筛选的是"启用"状态，提示用户切换到"归档"查看
    if (searchStatus.value === 1) {
      message.info('已归档，切换到"归档"状态可查看');
    }
  } catch (error) {
    logger.error('归档分类失败:', error);
    const errorMsg = getErrorMessage(error);
    message.error(`归档分类失败：${errorMsg}`);
  } finally {
    deleteNodeLoading.value = false;
  }
};

// 恢复归档分类
const handleUnarchiveNode = async (node: CategoryTreeNode) => {
  if (!node) return;

  deleteNodeLoading.value = true;
  try {
    const response = await requestClient.put(
      `/v1/keyword-corpus/categories/${node.id}`,
      {
        is_active: 1, // 设置为启用状态
      },
    );

    // 检查响应，确认更新成功
    if (response?.data?.is_active === 1) {
      message.success('分类已恢复');
    } else {
      message.warning('恢复操作可能未生效，请刷新页面查看');
    }

    // 重新获取树数据（使用当前筛选状态）
    await fetchTree();

    // 如果当前筛选的是"归档"状态，提示用户切换到"启用"查看
    if (searchStatus.value === 0) {
      message.info('已恢复，切换到"启用"状态可查看');
    }
  } catch (error) {
    logger.error('恢复分类失败:', error);
    const errorMsg = getErrorMessage(error);
    message.error(`恢复分类失败：${errorMsg}`);
  } finally {
    deleteNodeLoading.value = false;
  }
};

// 打开删除分类确认弹窗（仅归档状态可删除）
const handleOpenDeleteModal = (node: CategoryTreeNode) => {
  if (node.is_active !== 0) {
    message.warning('只能删除已归档的分类');
    return;
  }
  deleteNodeTarget.value = node;
  deleteNodeModalVisible.value = true;
};

// 确认删除分类（仅归档状态）
const handleConfirmDeleteNode = async () => {
  if (!deleteNodeTarget.value) return;

  // 再次检查是否为归档状态
  if (deleteNodeTarget.value.is_active !== 0) {
    message.warning('只能删除已归档的分类');
    return;
  }

  deleteNodeLoading.value = true;
  try {
    await requestClient.delete(
      `/v1/keyword-corpus/categories/${deleteNodeTarget.value.id}`,
    );
    message.success('分类删除成功');

    // 如果删除的是当前选中的节点，清空选中状态
    if (selectedNode.value?.id === deleteNodeTarget.value.id) {
      selectedNode.value = null;
      selectedKeys.value = [];
      keywords.value = [];
    }

    deleteNodeModalVisible.value = false;
    fetchTree();
  } catch (error) {
    logger.error('删除分类失败:', error);
    const errorMsg = getErrorMessage(error);
    message.error(`删除分类失败：${errorMsg}`);
  } finally {
    deleteNodeLoading.value = false;
  }
};

// 打开删除子关键词弹窗
const handleOpenDeleteChildrenModal = (node: CategoryTreeNode) => {
  deleteChildrenParent.value = node;
  deleteChildrenSelectedIds.value = [];
  deleteChildrenModalVisible.value = true;
};

// 确认删除选中的子节点
const handleDeleteSelectedChildren = async () => {
  if (deleteChildrenSelectedIds.value.length === 0) {
    message.warning('请选择要删除的子节点');
    return;
  }

  deleteChildrenLoading.value = true;
  try {
    // 使用批量删除 API
    const res = await requestClient.post<{
      deleted_count: number;
      total_nodes: number;
    }>('/v1/keyword-corpus/categories/batch-delete', {
      ids: deleteChildrenSelectedIds.value,
    });

    message.success(`删除完成：共删除 ${res?.total_nodes ?? 0} 个节点`);

    // 如果删除的包含当前选中的节点，清空选中状态
    if (
      selectedNode.value &&
      deleteChildrenSelectedIds.value.includes(selectedNode.value.id)
    ) {
      selectedNode.value = null;
      selectedKeys.value = [];
      keywords.value = [];
    }

    deleteChildrenModalVisible.value = false;
    fetchTree();
  } catch (error) {
    logger.error('删除子关键词失败:', error);
    message.error('删除子关键词失败');
  } finally {
    deleteChildrenLoading.value = false;
  }
};

// ==================== 语料编辑 ====================

// 获取指定 category_type 的语料模板列表
const fetchCorpusTemplatesByType = async (categoryType: string) => {
  corpusTemplateLoading.value = true;
  try {
    const res = await listCorpusTemplatesApi({
      tenant_code: 'default',
      page: 1,
      page_size: 100,
      category_type: categoryType,
    });
    allCorpusTemplates.value = res.items || [];

    // 如果有模板，默认选中第一个
    if (allCorpusTemplates.value.length > 0) {
      const defaultTemplate = allCorpusTemplates.value[0];
      corpusTemplate.value = defaultTemplate;
      corpusTemplateMissing.value = false;
      return defaultTemplate;
    }

    // 没有模板时，不标记缺失，允许用户选择纯文本或自定义字段模式
    corpusTemplate.value = null;
    corpusTemplateMissing.value = false;
    return null;
  } catch {
    allCorpusTemplates.value = [];
    corpusTemplate.value = null;
    corpusTemplateMissing.value = false;
    return null;
  } finally {
    corpusTemplateLoading.value = false;
  }
};

// 根据节点获取对应的语料模板
const fetchCorpusTemplate = async (node: CategoryTreeNode) => {
  const categoryType = node.label;
  if (!categoryType) return null;
  return await fetchCorpusTemplatesByType(categoryType);
};

// 新增语料
const handleAddCorpus = async () => {
  if (!selectedNode.value) {
    message.warning('请先选择一个节点');
    return;
  }

  // 使用节点的 label 作为 category_type 筛选模板
  const categoryType = selectedNode.value.label;
  if (!categoryType) {
    message.warning('当前节点没有设置标签，无法匹配语料模板');
    return;
  }

  // 获取该 category_type 下的所有模板
  const defaultTemplate = await fetchCorpusTemplatesByType(categoryType);

  corpusModalTitle.value = '新增语料';

  if (defaultTemplate) {
    // 有默认模板，使用模板模式
    corpusTemplate.value = defaultTemplate;
    corpusTemplateMissing.value = false;

    // 先初始化模板字段，确保响应式
    const initializedFields: Record<string, string> = {};
    for (const field of defaultTemplate.fields) {
      initializedFields[field.key] = '';
    }

    corpusForm.value = {
      nodeId: selectedNode.value.id,
      index: -1,
      templateCode: defaultTemplate.code,
      usePlainText: false,
      plainText: '',
      fields: initializedFields,
      customFields: [],
    };
  } else {
    // 没有模板，允许用户选择纯文本或自定义字段模式
    corpusTemplate.value = null;
    corpusTemplateMissing.value = false;

    corpusForm.value = {
      nodeId: selectedNode.value.id,
      index: -1,
      templateCode: '',
      usePlainText: false,
      plainText: '',
      fields: {},
      customFields: [],
    };
  }

  corpusModalVisible.value = true;
};

// 切换语料模板
const handleCorpusTemplateChange = async (templateCode: string) => {
  // 如果选择"不使用模板（纯文本）"（空字符串）
  if (templateCode === '') {
    corpusTemplate.value = null;
    corpusForm.value.templateCode = '';
    corpusForm.value.usePlainText = true;
    corpusForm.value.fields = {};
    corpusTemplateMissing.value = false;
    return;
  }

  // 如果选择"不使用模板（自定义字段）"
  if (templateCode === '__custom__') {
    corpusTemplate.value = null;
    corpusForm.value.templateCode = '__custom__';
    corpusForm.value.usePlainText = false;
    corpusForm.value.fields = {};
    corpusTemplateMissing.value = false;
    return;
  }

  // 选择具体模板
  const template = allCorpusTemplates.value.find(
    (t) => t.code === templateCode,
  );
  if (!template) return;

  corpusTemplate.value = template;
  corpusForm.value.templateCode = templateCode;
  corpusForm.value.usePlainText = false;

  // 重新初始化字段，保留已有字段的值
  const oldFields = corpusForm.value.fields;
  const initializedFields: Record<string, string> = {};

  for (const field of template.fields) {
    // 保留原有字段的值（如果字段名相同）
    initializedFields[field.key] = oldFields[field.key] || '';
  }

  corpusForm.value.fields = initializedFields;
};

// 跳过模板，使用纯文本模式
const handleSkipPlainText = () => {
  corpusTemplate.value = null;
  corpusForm.value.templateCode = '';
  corpusForm.value.usePlainText = true;
  corpusForm.value.plainText = '';
  corpusForm.value.fields = {};
  corpusTemplateMissing.value = false;
};

// 跳过模板，使用自定义字段模式
const handleSkipTemplate = () => {
  corpusTemplate.value = null;
  corpusForm.value.templateCode = '__custom__';
  corpusForm.value.usePlainText = false;
  corpusForm.value.fields = {};
  corpusTemplateMissing.value = false;
};

// 编辑语料
const handleEditCorpus = async (_record: KeywordItem, index: number) => {
  if (!selectedNode.value) return;

  // 获取语料
  const corpus = selectedNode.value.corpus?.[index];
  if (!corpus) {
    message.error('语料数据未找到');
    return;
  }

  // 判断语料类型
  const isPlainText = typeof corpus === 'string';

  if (isPlainText) {
    // 纯文本语料
    corpusTemplate.value = null;
    corpusTemplateMissing.value = false;
    corpusModalTitle.value = '编辑语料（纯文本）';

    corpusForm.value = {
      nodeId: selectedNode.value.id,
      index,
      templateCode: '',
      usePlainText: true,
      plainText: String(corpus),
      fields: {},
      customFields: [],
    };
  } else if (corpus.template_code) {
    // 结构化语料，使用模板
    // 先确保该节点类型的所有模板都已加载（用于模板选择器）
    const categoryType = selectedNode.value.label;
    await fetchCorpusTemplatesByType(categoryType);

    // 优先根据语料的 template_code 获取正确的模板（保证字段顺序一致）
    try {
      const template = await getCorpusTemplateApi(corpus.template_code);
      if (template) {
        corpusTemplate.value = template;
        corpusTemplateMissing.value = false;
      } else {
        // 如果通过 code 获取不到，尝试从已加载的模板中查找
        const fallbackTemplate = allCorpusTemplates.value.find(
          (t) => t.code === corpus.template_code,
        );
        if (fallbackTemplate) {
          corpusTemplate.value = fallbackTemplate;
          corpusTemplateMissing.value = false;
        } else {
          // 模板真的不存在，给出提示
          message.warning(
            `语料模板「${corpus.template_code}」已删除，将使用现有字段数据编辑`,
          );
          corpusTemplate.value = null;
          corpusTemplateMissing.value = true;
        }
      }
    } catch {
      // 如果获取失败，尝试从已加载的模板中查找
      const fallbackTemplate = allCorpusTemplates.value.find(
        (t) => t.code === corpus.template_code,
      );
      if (fallbackTemplate) {
        corpusTemplate.value = fallbackTemplate;
        corpusTemplateMissing.value = false;
      } else {
        message.warning(
          `语料模板「${corpus.template_code}」已删除，将使用现有字段数据编辑`,
        );
        corpusTemplate.value = null;
        corpusTemplateMissing.value = true;
      }
    }

    corpusModalTitle.value = '编辑语料';
  } else {
    // 自定义字段模式
    corpusTemplate.value = null;
    corpusTemplateMissing.value = false;
    corpusModalTitle.value = '编辑语料（自定义字段）';
  }

  // 分离模板字段和自定义字段
  const templateFields: Record<string, string> = {};
  const customFields: Array<{ key: string; value: string }> = [];

  if (!isPlainText) {
    // 先用模板中的所有字段初始化，确保响应式
    if (corpusTemplate.value) {
      corpusTemplate.value.fields.forEach((field) => {
        templateFields[field.key] = '';
      });
    }

    const templateFieldKeys = corpusTemplate.value
      ? new Set(corpusTemplate.value.fields.map((f) => f.key))
      : new Set<string>();

    for (const [key, value] of Object.entries(corpus.fields || {})) {
      if (templateFieldKeys.has(key)) {
        templateFields[key] = String(value);
      } else {
        customFields.push({ key, value: String(value) });
      }
    }
  }

  corpusForm.value = {
    ...corpusForm.value,
    nodeId: selectedNode.value.id,
    index,
    templateCode: corpus.template_code || '__custom__',
    usePlainText: isPlainText,
    fields: templateFields,
    customFields,
  };

  corpusModalVisible.value = true;
};

// 保存语料
const handleSaveCorpus = async () => {
  // 纯文本模式
  if (corpusForm.value.usePlainText) {
    if (!corpusForm.value.plainText?.trim()) {
      message.warning('请输入文本内容');
      return;
    }

    corpusModalLoading.value = true;
    try {
      // 纯文本包装成 CorpusItemCreate 格式
      const plainTextData = {
        text: corpusForm.value.plainText.trim(),
        weight: 1,
      };

      if (corpusForm.value.index >= 0) {
        // 更新纯文本语料
        await requestClient.put(
          `/v1/keyword-corpus/categories/${corpusForm.value.nodeId}/corpus/${corpusForm.value.index}`,
          plainTextData,
        );
        message.success('语料更新成功');
      } else {
        // 新增纯文本语料
        await requestClient.post(
          `/v1/keyword-corpus/categories/${corpusForm.value.nodeId}/corpus`,
          plainTextData,
        );
        message.success('语料添加成功');
      }

      corpusModalVisible.value = false;
      await reloadNodeAfterSave();
    } catch (error) {
      logger.error('保存语料失败:', error);
      message.error('保存语料失败');
    } finally {
      corpusModalLoading.value = false;
    }
    return;
  }

  // 结构化模式（模板或自定义字段）
  // 验证模板必填字段
  if (corpusTemplate.value && corpusForm.value.templateCode !== '__custom__') {
    for (const field of corpusTemplate.value.fields) {
      if (field.required && !corpusForm.value.fields[field.key]?.trim()) {
        message.warning(`请填写 ${field.label}`);
        return;
      }
    }
  }

  // 验证至少有一些内容
  const hasTemplateFields = Object.values(corpusForm.value.fields).some((v) =>
    v?.trim(),
  );
  const hasCustomFields = corpusForm.value.customFields.some(
    (f) => f.key.trim() && f.value.trim(),
  );

  if (!hasTemplateFields && !hasCustomFields) {
    message.warning('请至少填写一个字段');
    return;
  }

  // 合并模板字段和自定义字段
  const fieldEntries: [string, string][] = [];

  // 先按模板顺序添加模板字段
  if (corpusTemplate.value && corpusTemplate.value.fields) {
    for (const field of corpusTemplate.value.fields) {
      const value = corpusForm.value.fields[field.key];
      if (value !== undefined) {
        fieldEntries.push([field.key, value]);
      }
    }
  }

  // 再添加自定义字段
  for (const customField of corpusForm.value.customFields) {
    if (customField.key.trim() && customField.value.trim()) {
      fieldEntries.push([customField.key.trim(), customField.value.trim()]);
    }
  }

  const mergedFields = Object.fromEntries(fieldEntries);

  // 构建语料数据
  const corpusData: {
    fields: Record<string, string>;
    template_code?: string;
  } = {
    fields: mergedFields,
  };

  // 只有使用模板时才添加 template_code
  if (
    corpusForm.value.templateCode &&
    corpusForm.value.templateCode !== '__custom__'
  ) {
    corpusData.template_code = corpusForm.value.templateCode;
  }

  corpusModalLoading.value = true;
  try {
    if (corpusForm.value.index >= 0) {
      // 更新
      await requestClient.put(
        `/v1/keyword-corpus/categories/${corpusForm.value.nodeId}/corpus/${corpusForm.value.index}`,
        corpusData,
      );
      message.success('语料更新成功');
    } else {
      // 新增
      await requestClient.post(
        `/v1/keyword-corpus/categories/${corpusForm.value.nodeId}/corpus`,
        corpusData,
      );
      message.success('语料添加成功');
    }

    corpusModalVisible.value = false;
    await reloadNodeAfterSave();
  } catch (error) {
    logger.error('保存语料失败:', error);
    message.error('保存语料失败');
  } finally {
    corpusModalLoading.value = false;
  }
};

// 保存后重新加载节点数据
const reloadNodeAfterSave = async () => {
  if (selectedNode.value && selectedNode.value.id === corpusForm.value.nodeId) {
    // 重新获取当前节点的最新数据
    const res = await requestClient.get(
      `/v1/keyword-corpus/categories/${corpusForm.value.nodeId}`,
    );
    const updatedNode = res as CategoryTreeNode;

    // 更新 selectedNode
    if (selectedNode.value) {
      selectedNode.value.corpus = updatedNode.corpus || [];
    }

    // 同时更新树中对应节点的数据
    const updateNodeInTree = (nodes: CategoryTreeNode[]): boolean => {
      for (const node of nodes) {
        if (node.id === corpusForm.value.nodeId) {
          node.corpus = updatedNode.corpus || [];
          return true;
        }
        if (node.children && updateNodeInTree(node.children)) {
          return true;
        }
      }
      return false;
    };

    updateNodeInTree(treeData.value);

    // 刷新语料列表
    fetchKeywords();
  } else {
    // 如果当前选中的不是被更新的节点，需要重新加载树
    await fetchTree();
  }
};

// 打开快速创建模板弹窗
const openQuickCreateTemplate = (dimensionLabel: string) => {
  quickCreateTemplateForm.value = {
    name: `${dimensionLabel}语料模板`,
    dimensionLabel,
    description: `${dimensionLabel}维度的语料模板`,
    fields: [
      {
        key: dimensionLabel,
        label: dimensionLabel,
        type: 'textarea',
        required: true,
        placeholder: `请输入${dimensionLabel}内容`,
      },
    ],
  };
  quickCreateTemplateVisible.value = true;
};

// 添加模板字段
const addTemplateField = () => {
  quickCreateTemplateForm.value.fields.push({
    key: '',
    label: '',
    type: 'textarea',
    required: false,
    placeholder: '',
  });
};

// 删除模板字段
const removeTemplateField = (index: number) => {
  if (quickCreateTemplateForm.value.fields.length > 1) {
    quickCreateTemplateForm.value.fields.splice(index, 1);
  }
};

// 提交快速创建模板
const submitQuickCreateTemplate = async () => {
  const form = quickCreateTemplateForm.value;

  // 验证
  if (!form.name.trim()) {
    message.warning('请输入模板名称');
    return;
  }
  if (!form.dimensionLabel.trim()) {
    message.warning('请输入维度标签');
    return;
  }
  // 验证字段
  const validFields = form.fields.filter((f) => f.key.trim() && f.label.trim());
  if (validFields.length === 0) {
    message.warning('请至少添加一个有效字段');
    return;
  }

  quickCreateTemplateLoading.value = true;
  try {
    // 生成模板 code（与后端保持一致：分类类型-template-随机ID）
    const randomStr = Math.random().toString(36).slice(2, 10);
    const code = `${form.dimensionLabel}-template-${randomStr}`;

    await requestClient.post('/v1/keyword-corpus/corpus-templates', {
      code,
      name: form.name,
      category_type: form.dimensionLabel, // API 仍使用 category_type 字段名
      description: form.description,
      fields: validFields.map((f) => ({
        key: f.key,
        label: f.label,
        type: f.type,
        required: f.required,
        placeholder: f.placeholder || `请输入${f.label}`,
      })),
      tenant_code: 'default',
    });

    message.success('模板创建成功');
    quickCreateTemplateVisible.value = false;

    // 重新获取模板（如果当前有选中节点）
    if (selectedNode.value) {
      await fetchCorpusTemplate(selectedNode.value);
    }

    // 刷新维度列表
    fetchDimensionGuides();
  } catch (error) {
    logger.error('创建模板失败:', error);
    const errorMsg = getErrorMessage(error);
    message.error(`创建模板失败：${errorMsg}`);
  } finally {
    quickCreateTemplateLoading.value = false;
  }
};

// 删除语料
const handleDeleteCorpus = async (index: number) => {
  if (!selectedNode.value) return;

  try {
    await requestClient.delete(
      `/v1/keyword-corpus/categories/${selectedNode.value.id}/corpus/${index}`,
    );
    message.success('语料删除成功');
    // 重新获取树数据
    await fetchTree();
    // 重新选中当前节点
    const node = findNodeById(treeData.value, selectedNode.value.id);
    if (node) {
      selectedNode.value = node;
      fetchKeywords();
    }
  } catch (error) {
    logger.error('删除语料失败:', error);
    message.error('删除语料失败');
  }
};

// 获取语料表格操作按钮配置
const getCorpusActions = (record: unknown): TableAction[] => {
  const keywordRecord = record as KeywordItem;
  // 使用保存的原始索引，而不是过滤后的索引
  const index = keywordRecord._index ?? keywords.value.indexOf(keywordRecord);

  return [
    actionFactories.edit({
      onClick: () => handleEditCorpus(keywordRecord, index),
    }),
    actionFactories.delete({
      confirm: {
        title: '确定删除该语料吗？',
      },
      onClick: () => handleDeleteCorpus(index),
    }),
  ];
};

// 递归查找节点
const findNodeById = (
  nodes: CategoryTreeNode[],
  id: string,
): CategoryTreeNode | null => {
  for (const node of nodes) {
    if (node.id === id) return node;
    if (node.children) {
      const found = findNodeById(node.children, id);
      if (found) return found;
    }
  }
  return null;
};

// 语料表格列（node.name 是关键词，显示的是 corpus 语料）
const keywordColumns = [
  {
    title: '语料内容',
    dataIndex: 'name',
    key: 'name',
    ellipsis: false, // 不截断，显示完整内容
  },
  {
    title: '语料模版编码',
    key: 'format',
    width: 100,
  },
  {
    title: '操作',
    key: 'action',
    width: 120,
    fixed: 'right' as const,
  },
];

// 判断是否是结构化语料
const isStructuredCorpus = (item: KeywordItem): boolean => {
  const raw = (item as KeywordItem & { _raw?: CorpusItem | string })._raw;
  // 纯文本字符串不是结构化语料
  if (typeof raw === 'string') {
    return false;
  }
  return !!(raw && ('template_code' in raw || 'fields' in raw));
};

// 获取结构化语料的字段（按模板字段顺序排序）
const getStructuredFields = (
  item: KeywordItem,
): { key: string; value: string }[] => {
  const raw = (item as KeywordItem & { _raw?: CorpusItem | string })._raw;
  // 纯文本字符串没有结构化字段
  if (typeof raw === 'string') {
    return [];
  }
  if (raw && 'fields' in raw && raw.fields) {
    const corpusFields = raw.fields;
    const templateCode = raw.template_code;

    // 如果有 template_code，从所有模板中找到对应的模板，按模板字段顺序遍历
    if (templateCode) {
      const template = allCorpusTemplates.value.find(
        (t) => t.code === templateCode,
      );
      if (template?.fields) {
        return template.fields
          .map((templateField) => ({
            key: templateField.key,
            value: corpusFields[templateField.key] || '',
          }))
          .filter((field) => field.value); // 只显示有值的字段
      }
    }

    // 没有模板时，回退到 Object.entries（保持原有逻辑）
    return Object.entries(corpusFields)
      .filter(([, v]) => v)
      .map(([k, v]) => ({ key: k, value: v }));
  }

  // 如果没有 fields 属性，尝试从原始对象中提取字段
  if (raw && typeof raw === 'object') {
    return Object.entries(raw)
      .filter(([k, v]) => v && k !== 'template_code' && k !== 'id')
      .map(([k, v]) => ({ key: k, value: String(v) }));
  }

  return [];
};

// 获取结构化语料的模板编码
const getTemplateCode = (item: KeywordItem): string => {
  const raw = (item as KeywordItem & { _raw?: CorpusItem | string })._raw;
  // 纯文本字符串没有模板编码
  if (typeof raw === 'string') {
    return '';
  }
  if (raw && 'template_code' in raw) {
    return raw.template_code;
  }
  return '';
};

// 打开导入弹窗（指定节点作为父节点）
const handleImportToNode = (node: CategoryTreeNode) => {
  importStructuredData.value = [];
  importParentNodeId.value = node.id; // 设置当前节点为父节点
  // 使用节点的 label 作为维度选择
  importDimensionType.value = node.label || '';
  importModalVisible.value = true;
};

// 父节点变化时自动获取分类类型
const handleParentNodeChange = (value: string) => {
  if (!value) {
    importDimensionType.value = '';
    return;
  }
  // 从树数据中查找选中的节点
  const findNode = (nodes: CategoryTreeNode[]): CategoryTreeNode | null => {
    for (const node of nodes) {
      if (node.id === value) return node;
      if (node.children) {
        const found = findNode(node.children);
        if (found) return found;
      }
    }
    return null;
  };
  const selectedNode = findNode(treeData.value);
  if (selectedNode) {
    importDimensionType.value = selectedNode.label || '';
  }
};

// 解析 CSV 行（支持引号包裹的字段）
const parseCsvLine = (line: string, delimiter: string): string[] => {
  const result: string[] = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    const nextChar = line[i + 1];

    if (char === '"') {
      if (inQuotes && nextChar === '"') {
        // 转义的引号
        current += '"';
        i++;
      } else {
        // 切换引号状态
        inQuotes = !inQuotes;
      }
    } else if (char === delimiter && !inQuotes) {
      result.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }
  result.push(current.trim());
  return result;
};

// 将 CSV 文本分割成行，正确处理引号内的换行符
const splitCsvLines = (text: string): string[] => {
  const lines: string[] = [];
  let currentLine = '';
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    const nextChar = text[i + 1];

    if (char === '"') {
      currentLine += char;
      if (inQuotes && nextChar === '"') {
        // 转义的引号，跳过下一个字符
        i++;
        currentLine += nextChar;
      } else {
        // 切换引号状态
        inQuotes = !inQuotes;
      }
    } else if (char === '\n' && !inQuotes) {
      // 引号外的换行符，分割行
      lines.push(currentLine);
      currentLine = '';
    } else if (char === '\r' && nextChar === '\n' && !inQuotes) {
      // Windows 风格的换行符 \r\n
      lines.push(currentLine);
      currentLine = '';
      i++; // 跳过 \n
    } else if (char !== '\r') {
      // 忽略单独的 \r，其他字符添加到当前行
      currentLine += char;
    }
  }

  // 添加最后一行
  if (currentLine) {
    lines.push(currentLine);
  }

  return lines;
};

// 导入时使用的模板（与 selectedDimensionTemplate 分离，避免相互影响）
const importTemplateList = ref<GraphCorpusApi.CorpusTemplate[]>([]); // 可用模板列表
const importSelectedTemplateCode = ref<string>(''); // 用户选中的模板编码
const importTemplateLoading = ref(false);

// 当前选中的导入模板（computed 从列表中获取）
const importTemplate = computed(() => {
  if (!importSelectedTemplateCode.value) return null;
  return (
    importTemplateList.value.find(
      (t) => t.code === importSelectedTemplateCode.value,
    ) || null
  );
});

// 监听导入维度变化，自动加载对应模板列表
watch(importDimensionType, async (newType) => {
  if (!newType) {
    importTemplateList.value = [];
    importSelectedTemplateCode.value = '';
    return;
  }

  // 使用 label 匹配模板（模板表的 category_type 存储的就是 label）
  // 语料模板使用 default 租户（模板是全局共享的）
  importTemplateLoading.value = true;
  try {
    const res = await listCorpusTemplatesApi({
      category_type: newType,
      tenant_code: 'default',
    });
    const templates = res?.items || [];
    importTemplateList.value = templates;

    if (templates.length === 0) {
      importSelectedTemplateCode.value = '';
      message.warning(
        `维度 "${newType}" 还没有配置语料模板，导入时将只包含关键词`,
      );
    } else if (templates.length === 1) {
      // 只有一个模板时自动选中
      importSelectedTemplateCode.value = templates[0]?.code || '';
    } else {
      // 多个模板时，默认选中第一个，用户可以切换
      importSelectedTemplateCode.value = templates[0]?.code || '';
    }
  } catch {
    importTemplateList.value = [];
    importSelectedTemplateCode.value = '';
    message.warning(
      `维度 "${newType}" 还没有配置语料模板，导入时将只包含关键词`,
    );
  } finally {
    importTemplateLoading.value = false;
  }
});

// 获取当前导入维度的模板字段
const importDimensionFields = computed(() => {
  // 优先从导入模板获取字段
  if (importTemplate.value?.fields?.length) {
    return importTemplate.value.fields.map((f) => f.label);
  }
  // 回退到 dimensionGuides
  const dim = dimensionGuides.value.find(
    (d) => d.type === importDimensionType.value,
  );
  return dim?.fields || [];
});

// 获取当前导入维度的 label（用于匹配模板）
// importDimensionType 存储的就是 label，直接使用即可
const importDimensionLabel = computed(() => {
  if (!importDimensionType.value) return '';
  // 从树节点中查找匹配的根节点，确认 label
  const rootNode = treeData.value.find(
    (n) =>
      n.name === importDimensionType.value ||
      n.label === importDimensionType.value,
  );
  return rootNode?.label || importDimensionType.value;
});

// 解析 CSV 文件
// 支持两种格式：
// 1. 单层格式：关键词, 字段1, 字段2, ...
// 2. 层级格式：一级分类, 二级分类, ..., 关键词, 字段1, 字段2, ...
const handleCsvUpload = (file: File) => {
  const reader = new FileReader();
  reader.addEventListener('load', (e) => {
    const text = e.target?.result as string;
    if (!text) {
      message.error('读取文件失败');
      return;
    }

    // 正确分割 CSV 行（处理引号内的换行符）
    const allLines = splitCsvLines(text);
    // 过滤掉注释行（以#开头）和空行
    const lines = allLines.filter(
      (line) => line.trim() && !line.trim().startsWith('#'),
    );
    if (lines.length < 2) {
      message.error('CSV 文件格式错误：至少需要表头和一行数据');
      return;
    }

    // 检测分隔符（支持逗号和制表符）
    const firstLine = lines[0] ?? '';
    const delimiter = firstLine.includes('\t') ? '\t' : ',';

    // 解析表头
    const headers = parseCsvLine(firstLine, delimiter).map((h) =>
      h.replaceAll(/^"+|"+$/g, '').trim(),
    );

    // 检测是否是层级导入格式
    // 层级列的特征：包含"分类"、"级"等关键词，或者是连续的层级命名（一级、二级、三级）
    const hierarchyKeywords = ['分类', '级', 'level', 'category', 'industry'];
    const detectedHierarchyColumns: string[] = [];
    let nodeNameColumnIndex = -1;

    for (const [i, header_] of headers.entries()) {
      const header = header_?.toLowerCase() || '';
      const isHierarchyColumn = hierarchyKeywords.some((kw) =>
        header.includes(kw),
      );
      if (isHierarchyColumn) {
        detectedHierarchyColumns.push(header_ || '');
      } else if (
        nodeNameColumnIndex === -1 &&
        (header.includes('节点') ||
          header.includes('名称') ||
          header === 'keyword')
      ) {
        nodeNameColumnIndex = i;
        break; // 关键词列之后都是语料字段
      }
    }

    // 如果检测到层级列，使用层级导入模式
    if (detectedHierarchyColumns.length > 0 && nodeNameColumnIndex > 0) {
      importMode.value = 'hierarchical';
      hierarchyColumns.value = detectedHierarchyColumns;

      // 解析层级数据
      const data: HierarchicalImportRow[] = [];
      const fieldStartIndex = nodeNameColumnIndex + 1;
      const fieldHeaders = headers.slice(fieldStartIndex);

      for (let i = 1; i < lines.length; i++) {
        const line = lines[i];
        if (!line?.trim()) continue;

        const values = parseCsvLine(line, delimiter);
        const cleanedValues = values.map((v) =>
          v.replaceAll(/^"+|"+$/g, '').trim(),
        );

        if (cleanedValues.length < nodeNameColumnIndex + 1) continue;

        // 提取层级路径（去除空值）
        const path = cleanedValues
          .slice(0, nodeNameColumnIndex)
          .filter(Boolean);
        const nodeName = cleanedValues[nodeNameColumnIndex] ?? '';

        if (!nodeName || path.length === 0) continue;

        // 提取语料字段
        const fields: Record<string, string> = {};
        for (const [j, fieldName] of fieldHeaders.entries()) {
          const fieldValue = cleanedValues[fieldStartIndex + j] || '';
          if (fieldName && fieldValue) {
            fields[fieldName] = fieldValue;
          }
        }

        data.push({ path, name: nodeName, fields });
      }

      if (data.length === 0) {
        message.error('未解析到有效数据');
        return;
      }

      importHierarchicalData.value = data;
      importStructuredData.value = []; // 清空单层数据
      message.success(
        `成功解析 ${data.length} 条层级数据（${detectedHierarchyColumns.length} 层分类）`,
      );
      return;
    }

    // 单层导入模式
    importMode.value = 'flat';
    hierarchyColumns.value = [];
    importHierarchicalData.value = [];

    // 检查是否是结构化导入格式（第一列是关键词，后续是模板字段）
    const expectedFields = importDimensionFields.value;
    const isStructuredFormat =
      expectedFields.length > 0 &&
      headers.length >= 2 &&
      expectedFields.some((f) => headers.includes(f));

    if (!isStructuredFormat) {
      // 格式不匹配，给出友好的错误提示
      const dimName =
        dimensionGuides.value.find((d) => d.type === importDimensionType.value)
          ?.name || importDimensionType.value;
      Modal.error({
        title: 'CSV 格式不匹配',
        content: `【${dimName}】维度 CSV 格式不匹配

📋 期望的列名：关键词, ${expectedFields.join(', ') || '(该维度未配置模板)'}

📄 您的文件列名：${headers.join(', ')}

💡 建议：点击「下载模板」获取正确格式的 CSV 模板，按模板格式填写数据后重新导入。`,
        okText: '我知道了',
      });
      return;
    }

    // 结构化导入：关键词 + 模板字段
    const data: StructuredImportRow[] = [];

    for (let i = 1; i < lines.length; i++) {
      const line = lines[i];
      if (!line?.trim()) continue;

      const values = parseCsvLine(line, delimiter);
      const cleanedValues = values.map((v) =>
        v.replaceAll(/^"+|"+$/g, '').trim(),
      );

      if (cleanedValues.length < 2) continue;

      const nodeName = cleanedValues[0] ?? '';
      if (!nodeName) continue;

      // 根据表头映射字段值
      const fields: Record<string, string> = {};
      for (let j = 1; j < headers.length; j++) {
        const fieldName = headers[j];
        const fieldValue = cleanedValues[j] || '';
        if (fieldName && fieldValue) {
          fields[fieldName] = fieldValue;
        }
      }

      if (Object.keys(fields).length > 0) {
        data.push({ nodeName, fields });
      }
    }

    if (data.length === 0) {
      message.error('未解析到有效数据');
      return;
    }

    importStructuredData.value = data;
    message.success(`成功解析 ${data.length} 条结构化语料`);
  });
  reader.readAsText(file, 'utf8');
  return false; // 阻止自动上传
};

// 执行导入
const handleImportSubmit = async () => {
  // 检查是否有数据
  const hasData =
    importMode.value === 'hierarchical'
      ? importHierarchicalData.value.length > 0
      : importStructuredData.value.length > 0;

  if (!hasData) {
    message.error('请先上传 CSV 文件');
    return;
  }

  importLoading.value = true;
  importProgress.value = 0;

  // 模拟进度更新（渐进式减速，永不到 99%）
  const progressInterval = setInterval(() => {
    const remaining = 99 - importProgress.value;
    if (remaining > 1) {
      // 剩余越少，增加越慢
      importProgress.value += remaining * 0.05;
    }
  }, 200);

  try {
    let res: {
      created_edges?: number;
      created_nodes: number;
      errors: string[];
      total_corpus: number;
      updated_nodes: number;
    };

    if (importMode.value === 'hierarchical') {
      // 层级导入模式
      const dimensionLabel =
        importDimensionLabel.value || importDimensionType.value;
      const templateCode = dimensionLabel
        ? `${dimensionLabel.toLowerCase().replaceAll(/\s+/g, '_')}_v1`
        : 'default';

      // 转换为层级导入 API 格式
      const items = importHierarchicalData.value.map((row) => ({
        path: row.path,
        name: row.name,
        corpus: {
          template_code: templateCode,
          fields: row.fields,
        },
      }));

      res = await requestClient.post(
        '/v1/keyword-corpus/categories/batch-import-hierarchical',
        {
          dimension_type: dimensionLabel,
          items,
          conflict_strategy: importConflictStrategy.value,
        },
        {
          params: { tenant_code: 'default' },
          timeout: 180_000, // 3分钟超时，层级数据量可能很大
        },
      );

      message.success(
        `层级导入完成：创建 ${res?.created_nodes ?? 0} 个节点，${res?.created_edges ?? 0} 条关系，共 ${res?.total_corpus ?? 0} 条语料`,
      );
    } else {
      // 单层结构化导入模式
      // 按关键词分组，每个节点可能有多条语料
      const nodeMap = new Map<string, Record<string, string>[]>();
      for (const row of importStructuredData.value) {
        const existing = nodeMap.get(row.nodeName) || [];
        existing.push(row.fields);
        nodeMap.set(row.nodeName, existing);
      }

      // 获取模板编码 - 使用用户选择的模板
      const dimensionLabel = importDimensionLabel.value;
      const templateCode =
        importSelectedTemplateCode.value ||
        (dimensionLabel
          ? `${dimensionLabel.toLowerCase().replaceAll(/\s+/g, '_')}_v1`
          : '');

      // 转换为 API 格式
      const items = [...nodeMap.entries()].map(([nodeName, fieldsList]) => ({
        name: nodeName,
        corpus: fieldsList.map((fields) => ({
          template_code: templateCode,
          fields,
        })),
      }));

      // 构建导入属性（使用 LabelSelector 的 labels 格式）
      const importProperties = importLabels.value.labels || {};

      const importParams: Record<string, string> = { tenant_code: 'default' };
      if (brandCode.value) {
        importParams.brand_code = brandCode.value;
      }
      res = await requestClient.post(
        '/v1/keyword-corpus/categories/batch-import-structured',
        {
          parent_node_id: importParentNodeId.value || null,
          dimension_type: dimensionLabel, // 使用 label 作为维度类型
          items,
          conflict_strategy: importConflictStrategy.value,
          properties: importProperties, // 使用新的属性设计
        },
        {
          params: importParams,
          timeout: 120_000,
        }, // 2分钟超时，语料数据在 default 租户下
      );

      message.success(
        `导入完成：创建 ${res?.created_nodes ?? 0} 个节点，共 ${res?.total_corpus ?? 0} 条语料`,
      );
    }

    if (res?.errors && res.errors.length > 0) {
      logger.warn('导入部分失败:', res.errors);
    }

    clearInterval(progressInterval);
    importProgress.value = 100;
    // 短暂显示 100% 后关闭弹窗
    setTimeout(() => {
      importModalVisible.value = false;
      importLoading.value = false;
      importProgress.value = 0;
      resetImportProperties(); // 重置属性选择
      // 重置导入数据
      importStructuredData.value = [];
      importHierarchicalData.value = [];
      importMode.value = 'flat';
    }, 500);
    fetchTree(); // 刷新关键词树
  } catch (error) {
    logger.error('导入失败:', error);
    const errorMsg = getErrorMessage(error);
    message.error(`导入失败：${errorMsg}`);
    clearInterval(progressInterval);
    importLoading.value = false;
    importProgress.value = 0;
  }
};

// 下载导入弹窗的模板（使用 importTemplate）
const handleDownloadImportTemplate = () => {
  if (!importDimensionType.value) return;

  const dimName =
    dimensionGuides.value.find((d) => d.type === importDimensionType.value)
      ?.name || importDimensionType.value;
  const template = importTemplate.value;

  // 使用模板字段，如果模板不存在则使用空数组
  const templateFields = template?.fields || [];
  const fieldLabels = templateFields.map((f) => f.label);

  // 新格式：关键词 + 模板字段
  const headers = ['关键词', ...fieldLabels];

  // 生成示例数据
  const exampleRows = [
    [
      `示例${dimName}1`,
      ...templateFields.map((f) => f.placeholder || `${f.label}内容1`),
    ],
    [
      `示例${dimName}1`,
      ...templateFields.map((f) => f.placeholder || `${f.label}内容2`),
    ],
    [
      `示例${dimName}2`,
      ...templateFields.map((f) => f.placeholder || `${f.label}内容1`),
    ],
  ];

  const instructions = [
    `# ${template?.name || dimName}导入模板`,
    `# 第一列：关键词`,
    `# 后续列：语料字段（${fieldLabels.join('、')}）`,
    `# 同一关键词可多行，每行是一条语料`,
    `# 导入时会自动创建节点并添加语料`,
  ];

  const csvContent = [
    ...instructions,
    headers.join(','),
    ...exampleRows.map((row) =>
      row.map((cell) => `"${cell.replaceAll('"', '""')}"`).join(','),
    ),
  ].join('\n');

  const blob = new Blob([`\uFEFF${csvContent}`], {
    type: 'text/csv;charset=utf-8;',
  });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `${template?.name || dimName}_导入模板.csv`;
  link.click();
  message.success('模板下载成功');
};

// 导出子关键词及语料（可用于导入）
const handleExportWithChildren = async (node: CategoryTreeNode) => {
  // 获取节点的维度（label）对应的模板
  const dimensionLabel = node.label;
  let templateFields: string[] = [];

  if (dimensionLabel) {
    try {
      const res = await listCorpusTemplatesApi({
        category_type: dimensionLabel,
        tenant_code: 'default',
      });
      const templates = res?.items || [];
      if (templates.length > 0 && templates[0]?.fields) {
        templateFields = templates[0].fields.map((f) => f.label);
      }
    } catch {
      // 模板加载失败，使用空字段
    }
  }

  // 递归收集子分类及语料
  interface ExportRow {
    path: string[]; // 层级路径（不含当前节点）
    nodeName: string; // 节点名称
    fields: Record<string, string>; // 语料字段
  }
  const collectHierarchicalData = (
    currentNode: CategoryTreeNode,
    parentPath: string[],
  ): ExportRow[] => {
    const result: ExportRow[] = [];

    // 收集当前节点的语料
    if (currentNode.corpus && currentNode.corpus.length > 0) {
      for (const c of currentNode.corpus) {
        result.push({
          path: parentPath,
          nodeName: currentNode.name,
          fields: c.fields || {},
        });
      }
    } else {
      // 没有语料的节点也导出（用于保留分类结构）
      result.push({
        path: parentPath,
        nodeName: currentNode.name,
        fields: {},
      });
    }

    // 递归收集子节点
    if (currentNode.children) {
      for (const child of currentNode.children) {
        result.push(
          ...collectHierarchicalData(child, [...parentPath, currentNode.name]),
        );
      }
    }

    return result;
  };

  // 从选中节点的子节点开始收集（不包含选中节点本身作为数据行）
  const exportData: ExportRow[] = [];
  if (node.children) {
    for (const child of node.children) {
      exportData.push(...collectHierarchicalData(child, []));
    }
  }

  if (exportData.length === 0) {
    message.warning('该节点下暂无子分类');
    return;
  }

  // 计算最大层级深度
  const maxDepth = Math.max(...exportData.map((d) => d.path.length));

  // 收集所有出现的字段名
  const allFieldKeys = new Set<string>();
  for (const row of exportData) {
    for (const key of Object.keys(row.fields)) {
      allFieldKeys.add(key);
    }
  }
  // 优先使用模板字段顺序，然后补充其他字段
  const orderedFieldKeys = [...templateFields];
  for (const key of allFieldKeys) {
    if (!orderedFieldKeys.includes(key)) {
      orderedFieldKeys.push(key);
    }
  }

  // 生成表头：分类列 + 关键词 + 语料字段
  const headers: string[] = [];
  for (let i = 1; i <= maxDepth; i++) {
    headers.push(`分类${i}`);
  }
  headers.push('关键词', ...orderedFieldKeys);

  // 生成数据行
  const escapeCsvCell = (value: string): string => {
    if (!value) return '';
    // 如果包含逗号、换行或引号，用引号包裹并转义内部引号
    if (value.includes(',') || value.includes('\n') || value.includes('"')) {
      return `"${value.replaceAll('"', '""')}"`;
    }
    return value;
  };

  const rows = exportData.map((row) => {
    const cells: string[] = [];
    // 填充分类列
    for (let i = 0; i < maxDepth; i++) {
      cells.push(escapeCsvCell(row.path[i] || ''));
    }
    // 关键词
    cells.push(escapeCsvCell(row.nodeName));
    // 语料字段
    for (const key of orderedFieldKeys) {
      cells.push(escapeCsvCell(row.fields[key] || ''));
    }
    return cells.join(',');
  });

  // 添加说明注释
  const instructions = [
    `# 导出自：${node.name}`,
    `# 维度：${dimensionLabel || '未知'}`,
    `# 导出时间：${new Date().toLocaleString('zh-CN')}`,
    `# 可直接用于层级导入功能`,
  ];

  const csvContent = [...instructions, headers.join(','), ...rows].join('\n');
  const blob = new Blob([`\uFEFF${csvContent}`], {
    type: 'text/csv;charset=utf-8',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${node.name}_子关键词导出.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);

  const corpusCount = exportData.filter(
    (d) => Object.keys(d.fields).length > 0,
  ).length;
  const nodeCount = new Set(exportData.map((d) => d.nodeName)).size;
  message.success(`导出成功：共 ${nodeCount} 个节点，${corpusCount} 条语料`);
};

// 批量删除语料
const handleBatchDeleteCorpus = async () => {
  if (selectedCorpusKeys.value.length === 0) {
    message.warning('请先选择要删除的语料');
    return;
  }

  if (!selectedNode.value) return;

  // 获取索引（倒序删除避免索引偏移）
  const indices = selectedCorpusKeys.value
    .map((key) => {
      const match = key.match(/-corpus-(\d+)$/);
      return match?.[1] ? Number.parseInt(match[1], 10) : -1;
    })
    .filter((i) => i >= 0)
    .toSorted((a, b) => b - a);

  try {
    for (const index of indices) {
      await requestClient.delete(
        `/v1/keyword-corpus/categories/${selectedNode.value.id}/corpus/${index}`,
      );
    }
    message.success(`成功删除 ${indices.length} 条语料`);
    selectedCorpusKeys.value = [];
    await fetchTree();
    const node = findNodeById(treeData.value, selectedNode.value.id);
    if (node) {
      selectedNode.value = node;
      fetchKeywords();
    }
  } catch (error) {
    logger.error('批量删除语料失败:', error);
    message.error('批量删除语料失败');
  }
};

// 打开复制节点弹窗
const handleOpenCopyModal = (node: CategoryTreeNode) => {
  copyNodeData.value = node;
  copyTargetNodeId.value = undefined;
  copyModalVisible.value = true;
};

// 执行复制节点
const handleCopyNode = async () => {
  if (!copyNodeData.value) return;

  copyLoading.value = true;
  try {
    const copyParams: Record<string, string> = { tenant_code: 'default' };
    if (brandCode.value) {
      copyParams.brand_code = brandCode.value;
    }
    await requestClient.post(
      '/v1/keyword-corpus/categories/copy',
      {
        source_node_id: copyNodeData.value.id,
        target_parent_id: copyTargetNodeId.value || null,
      },
      { params: copyParams }, // 语料数据在 default 租户下
    );
    message.success('复制成功');
    copyModalVisible.value = false;
    fetchTree();
  } catch (error) {
    logger.error('复制失败:', error);
    message.error('复制失败');
  } finally {
    copyLoading.value = false;
  }
};

// 注：Scope 相关功能已迁移：不再使用 scope 字段，改为写入 properties.brands / properties.products

// 执行设置 Scope
const handleSetScope = async () => {
  if (!setScopeNodeData.value) return;

  setScopeLoading.value = true;
  try {
    const scopeLevel = setScopeForm.value.level;
    if (
      scopeLevel !== 'global' &&
      setScopeForm.value.brand_codes.length === 0
    ) {
      message.warning('请选择至少 1 个品牌');
      return;
    }

    if (
      scopeLevel === 'product' &&
      setScopeForm.value.brand_codes.length !== 1
    ) {
      message.warning('产品级范围仅支持选择 1 个品牌');
      return;
    }

    if (
      scopeLevel === 'product' &&
      setScopeForm.value.product_names.length === 0
    ) {
      message.warning('请选择至少 1 个产品');
      return;
    }

    const brandsToSet =
      scopeLevel === 'global' ? [] : setScopeForm.value.brand_codes;
    const productsToSet =
      scopeLevel === 'product' ? setScopeForm.value.product_names : [];

    await requestClient.put(
      `/v1/keyword-corpus/categories/${setScopeNodeData.value.id}`,
      { brands: brandsToSet, products: productsToSet },
    );
    message.success('范围设置成功');
    setScopeModalVisible.value = false;
    fetchTree();
  } catch (error) {
    logger.error('设置范围失败:', error);
    message.error(`设置范围失败：${getErrorMessage(error)}`);
  } finally {
    setScopeLoading.value = false;
  }
};

// 切换多选模式
const toggleCheckMode = () => {
  isCheckMode.value = !isCheckMode.value;
  if (!isCheckMode.value) {
    checkedKeys.value = [];
  }
};

// 处理节点勾选
const onCheck = (
  checked:
    | (number | string)[]
    | { checked: (number | string)[]; halfChecked: (number | string)[] },
) => {
  checkedKeys.value = Array.isArray(checked)
    ? checked.map(String)
    : checked.checked.map(String);
};

// 打开批量设置 Scope 弹窗
const handleOpenBatchScopeModal = () => {
  if (checkedKeys.value.length === 0) {
    message.warning('请先选择要设置范围的节点');
    return;
  }
  batchScopeForm.value = {
    level: 'global',
    brand_codes: [],
    product_names: [],
  };
  batchScopeModalVisible.value = true;
};

// 执行批量设置 Scope
const handleBatchSetScope = async () => {
  if (checkedKeys.value.length === 0) return;

  batchScopeLoading.value = true;
  try {
    const scopeLevel = batchScopeForm.value.level;
    if (
      scopeLevel !== 'global' &&
      batchScopeForm.value.brand_codes.length === 0
    ) {
      message.warning('请选择至少 1 个品牌');
      return;
    }
    if (
      scopeLevel === 'product' &&
      batchScopeForm.value.product_names.length === 0
    ) {
      message.warning('请选择至少 1 个产品');
      return;
    }

    const brandsToSet =
      scopeLevel === 'global' ? [] : batchScopeForm.value.brand_codes;
    const productsToSet =
      scopeLevel === 'product' ? batchScopeForm.value.product_names : [];

    // 简单可靠：逐个更新（一般勾选数量不大）
    for (const nodeId of checkedKeys.value) {
      await requestClient.put(`/v1/keyword-corpus/categories/${nodeId}`, {
        brands: brandsToSet,
        products: productsToSet,
      });
    }
    message.success(`成功为 ${checkedKeys.value.length} 个节点设置范围`);
    batchScopeModalVisible.value = false;
    checkedKeys.value = [];
    isCheckMode.value = false;
    fetchTree();
  } catch (error) {
    logger.error('批量设置范围失败:', error);
    message.error(`批量设置范围失败：${getErrorMessage(error)}`);
  } finally {
    batchScopeLoading.value = false;
  }
};

// 初始化
onMounted(async () => {
  // 加载品牌列表（保持兼容，虽然只有一个品牌）
  await fetchBrandOptions();
  // 加载产品选项（只有一个品牌，直接加载）
  fetchProductOptions();
  // 加载标签选项
  fetchTagOptions();
  // 加载数据
  fetchTree();
  fetchDimensionGuides();
});
</script>

<template>
  <div class="category-container">
    <!-- 粘性筛选头部 -->
    <div
      class="sticky top-0 z-10 -mx-4 -mt-4 mb-3 bg-background/90 px-4 pb-4 pt-2 shadow-lg backdrop-blur-md"
      style="border-bottom: 1px solid hsl(var(--border) / 30%)"
    >
      <!-- 标题行 -->
      <div class="mb-2 flex items-center gap-3">
        <span
          class="bg-gradient-to-r from-[hsl(var(--primary))] to-[#22c55e] bg-clip-text text-xl font-bold text-transparent"
        >
          关键词语料管理
        </span>
        <span v-if="lastUpdateTime" class="text-xs text-muted-foreground">
          数据更新时间：{{ lastUpdateTime }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <Space :size="20">
          <Input
            v-model:value="searchText"
            placeholder="搜索分类名称..."
            allow-clear
            style="width: 200px"
          >
            <template #prefix><SearchOutlined /></template>
          </Input>
          <Input
            v-model:value="corpusSearchText"
            placeholder="搜索语料内容..."
            allow-clear
            style="width: 200px"
          >
            <template #prefix><SearchOutlined /></template>
          </Input>
          <Select
            v-model:value="searchStatus"
            placeholder="状态"
            style="width: 120px"
            allow-clear
            :options="[
              { label: '全部状态', value: undefined },
              { label: '启用', value: 1 },
              { label: '归档', value: 0 },
            ]"
            @change="fetchTree"
          />
          <Select
            v-model:value="selectedFilterTags"
            :options="tagOptions"
            :loading="tagLoading"
            mode="multiple"
            :max-tag-count="1"
            placeholder="标签筛选"
            allow-clear
            show-search
            :filter-option="true"
            style="width: 200px"
          />
        </Space>
        <div class="filter-actions">
          <Button
            class="action-btn"
            variant="ghost"
            size="sm"
            @click="fetchTree"
          >
            <ReloadOutlined class="btn-icon" />
            <span class="btn-label">刷新</span>
          </Button>
          <Dropdown>
            <Button class="action-btn" size="sm" variant="ghost">
              <DownloadOutlined class="btn-icon" />
              <span class="btn-label">迁移</span>
            </Button>
            <template #overlay>
              <Menu>
                <Menu.Item @click="handleOpenMigrationModal('export')">
                  <ExportOutlined /> 导出数据
                </Menu.Item>
                <Menu.Item @click="handleOpenMigrationModal('import')">
                  <UploadOutlined /> 导入数据
                </Menu.Item>
              </Menu>
            </template>
          </Dropdown>
        </div>
      </div>
    </div>

    <div class="main-content">
      <!-- 左侧关键词树 -->
      <Card :bordered="false" class="tree-card">
        <CardHeader class="tree-card-header">
          <div class="tree-header-content">
            <div class="tree-header-left">
              <div class="tree-header-icon">
                <FolderOutlined />
              </div>
              <span class="tree-header-title">分类目录</span>
            </div>
            <div class="tree-header-actions">
              <Button
                class="action-btn"
                size="sm"
                :variant="isCheckMode ? 'default' : 'ghost'"
                :class="{ active: isCheckMode }"
                @click="toggleCheckMode"
              >
                <TagOutlined class="btn-icon" />
                <span class="btn-label">{{
                  isCheckMode ? '退出多选' : '多选'
                }}</span>
              </Button>
              <Button
                class="action-btn primary-action"
                size="sm"
                @click="handleAddRootCategory"
              >
                <PlusOutlined class="btn-icon" />
                <span class="btn-label">新增</span>
              </Button>
            </div>
          </div>
        </CardHeader>

        <!-- 多选操作栏 -->
        <div
          v-if="isCheckMode && checkedKeys.length > 0"
          class="batch-action-bar"
        >
          <span class="selected-count"> 已选 {{ checkedKeys.length }} 项 </span>
          <Space>
            <Button
              variant="default"
              size="small"
              @click="handleOpenBatchScopeModal"
            >
              <template #icon><TagOutlined /></template>
              批量设置范围
            </Button>
            <Button size="small" @click="checkedKeys = []"> 取消选择 </Button>
          </Space>
        </div>

        <Spin :spinning="loading">
          <div v-if="filteredTreeData.length === 0" class="empty-tree">
            <Empty description="暂无分类数据">
              <Button variant="default" @click="handleAddRootCategory">
                <template #icon><PlusOutlined /></template>
                创建第一个节点
              </Button>
            </Empty>
          </div>
          <Tree
            v-else
            :tree-data="filteredTreeData"
            :selected-keys="selectedKeys"
            :expanded-keys="expandedKeys"
            :checked-keys="checkedKeys"
            :checkable="isCheckMode"
            :field-names="{ title: 'name', key: 'id', children: 'children' }"
            show-icon
            block-node
            draggable
            @select="onSelect"
            @expand="onExpand"
            @drop="handleDrop"
            @check="onCheck"
          >
            <template #icon="{ dataRef }">
              <component
                :is="getNodeIcon(dataRef as unknown as CategoryTreeNode)"
                :style="{
                  color: (dataRef as unknown as CategoryTreeNode).color,
                }"
              />
            </template>
            <template #title="{ dataRef }">
              <div class="tree-node-title">
                <span
                  class="node-name"
                  :class="{
                    'search-highlight': isNodeMatch(
                      dataRef as unknown as CategoryTreeNode,
                    ),
                  }"
                  >{{ (dataRef as unknown as CategoryTreeNode).name }}</span
                >
                <CopyOutlined
                  class="node-copy-btn"
                  @click.stop="
                    handleCopyNodeName(
                      (dataRef as unknown as CategoryTreeNode).name,
                      $event,
                    )
                  "
                />
                <Tag
                  v-if="
                    (dataRef as unknown as CategoryTreeNode).label &&
                    ((dataRef as unknown as CategoryTreeNode).level === 0 ||
                      (dataRef as unknown as CategoryTreeNode).level ===
                        undefined)
                  "
                  color="blue"
                  size="small"
                  class="label-tag"
                >
                  {{ (dataRef as unknown as CategoryTreeNode).label }}
                </Tag>
                <Tag
                  v-if="
                    (dataRef as unknown as CategoryTreeNode).is_active === 0
                  "
                  color="default"
                  size="small"
                >
                  归档
                </Tag>
                <div
                  class="node-tags"
                  :class="{
                    'node-tags-expanded': isNodeTagsExpanded(
                      (dataRef as unknown as CategoryTreeNode).id,
                    ),
                  }"
                >
                  <!-- 品牌标签 -->
                  <Tag
                    v-for="brand in getVisibleItems(
                      (dataRef as unknown as CategoryTreeNode).brands,
                      2,
                      isNodeTagsExpanded(
                        (dataRef as unknown as CategoryTreeNode).id,
                      ),
                    )"
                    :key="brand"
                    color="green"
                    size="small"
                    class="brand-tag"
                  >
                    {{ brand }}
                  </Tag>
                  <!-- 产品标签 -->
                  <Tag
                    v-for="product in getVisibleItems(
                      (dataRef as unknown as CategoryTreeNode).products,
                      2,
                      isNodeTagsExpanded(
                        (dataRef as unknown as CategoryTreeNode).id,
                      ),
                    )"
                    :key="product"
                    color="orange"
                    size="small"
                    class="product-tag"
                  >
                    {{ product }}
                  </Tag>
                  <!-- 业务标签 -->
                  <Tag
                    v-for="tagName in getVisibleItems(
                      getTagNames(
                        (dataRef as unknown as CategoryTreeNode).tags,
                      ),
                      2,
                      isNodeTagsExpanded(
                        (dataRef as unknown as CategoryTreeNode).id,
                      ),
                    )"
                    :key="tagName"
                    color="purple"
                    size="small"
                    class="business-tag"
                  >
                    {{ tagName }}
                  </Tag>

                  <span
                    v-if="
                      !isNodeTagsExpanded(
                        (dataRef as unknown as CategoryTreeNode).id,
                      ) &&
                      getHiddenCount(
                        (dataRef as unknown as CategoryTreeNode).brands,
                        2,
                        false,
                      ) +
                        getHiddenCount(
                          (dataRef as unknown as CategoryTreeNode).products,
                          2,
                          false,
                        ) +
                        getHiddenCount(
                          (dataRef as unknown as CategoryTreeNode).tags,
                          2,
                          false,
                        ) >
                        0
                    "
                    class="more-tags more-tags-action"
                    @click.stop="
                      toggleNodeTags(
                        (dataRef as unknown as CategoryTreeNode).id,
                      )
                    "
                  >
                    +{{
                      getHiddenCount(
                        (dataRef as unknown as CategoryTreeNode).brands,
                        2,
                        false,
                      ) +
                      getHiddenCount(
                        (dataRef as unknown as CategoryTreeNode).products,
                        2,
                        false,
                      ) +
                      getHiddenCount(
                        (dataRef as unknown as CategoryTreeNode).tags,
                        2,
                        false,
                      )
                    }}
                  </span>
                  <span
                    v-else-if="
                      isNodeTagsExpanded(
                        (dataRef as unknown as CategoryTreeNode).id,
                      )
                    "
                    class="more-tags more-tags-action"
                    @click.stop="
                      toggleNodeTags(
                        (dataRef as unknown as CategoryTreeNode).id,
                      )
                    "
                  >
                    收起
                  </span>
                </div>
                <span
                  v-if="
                    getCorpusCount(dataRef as unknown as CategoryTreeNode) > 0
                  "
                  class="corpus-count"
                >
                  ({{
                    getCorpusCount(dataRef as unknown as CategoryTreeNode)
                  }}条)
                </span>
                <Dropdown :trigger="['click']" placement="bottomRight">
                  <MoreOutlined class="node-action" @click.stop />
                  <template #overlay>
                    <Menu>
                      <Menu.Item
                        key="addSub"
                        @click="
                          handleAddSubCategory(
                            dataRef as unknown as CategoryTreeNode,
                          )
                        "
                      >
                        <FolderAddOutlined /> 新增子关键词
                      </Menu.Item>
                      <Menu.Item
                        key="importSub"
                        @click="
                          handleImportToNode(
                            dataRef as unknown as CategoryTreeNode,
                          )
                        "
                      >
                        <UploadOutlined /> 导入子关键词
                      </Menu.Item>
                      <Menu.Item
                        key="addCorpus"
                        @click="
                          () => {
                            selectedNode =
                              dataRef as unknown as CategoryTreeNode;
                            selectedKeys = [
                              (dataRef as unknown as CategoryTreeNode).id,
                            ];
                            handleAddCorpus();
                          }
                        "
                      >
                        <FileAddOutlined /> 新增语料
                      </Menu.Item>
                      <Menu.Divider />
                      <Menu.Item
                        key="edit"
                        @click="
                          handleEditCategory(
                            dataRef as unknown as CategoryTreeNode,
                          )
                        "
                      >
                        <EditOutlined /> 编辑
                      </Menu.Item>
                      <Menu.Item
                        key="copy"
                        @click="
                          handleOpenCopyModal(
                            dataRef as unknown as CategoryTreeNode,
                          )
                        "
                      >
                        <CopyOutlined /> 复制到...
                      </Menu.Item>
                      <Menu.Item
                        v-if="
                          (dataRef as unknown as CategoryTreeNode).children
                            ?.length
                        "
                        key="exportChildren"
                        @click="
                          handleExportWithChildren(
                            dataRef as unknown as CategoryTreeNode,
                          )
                        "
                      >
                        <DownloadOutlined /> 导出子关键词
                      </Menu.Item>
                      <!-- 设置范围和升级范围功能已移除（properties 中不再使用 scope 字段） -->
                      <Menu.Divider />
                      <Menu.Item
                        v-if="
                          (dataRef as unknown as CategoryTreeNode).children
                            ?.length
                        "
                        key="deleteChildren"
                        @click="
                          handleOpenDeleteChildrenModal(
                            dataRef as unknown as CategoryTreeNode,
                          )
                        "
                      >
                        <DeleteOutlined /> 删除子关键词...
                      </Menu.Item>
                      <!-- 归档操作：仅在启用状态显示 -->
                      <Menu.Item
                        v-if="
                          (dataRef as unknown as CategoryTreeNode).is_active ===
                          1
                        "
                        key="archive"
                        @click="
                          handleArchiveNode(
                            dataRef as unknown as CategoryTreeNode,
                          )
                        "
                      >
                        <FolderOutlined /> 归档
                      </Menu.Item>
                      <!-- 恢复操作：仅在归档状态显示 -->
                      <Menu.Item
                        v-if="
                          (dataRef as unknown as CategoryTreeNode).is_active ===
                          0
                        "
                        key="unarchive"
                        @click="
                          handleUnarchiveNode(
                            dataRef as unknown as CategoryTreeNode,
                          )
                        "
                      >
                        <FolderOpenOutlined /> 恢复
                      </Menu.Item>
                      <!-- 删除操作：仅在归档状态显示 -->
                      <Menu.Item
                        v-if="
                          (dataRef as unknown as CategoryTreeNode).is_active ===
                          0
                        "
                        key="delete"
                        @click="
                          handleOpenDeleteModal(
                            dataRef as unknown as CategoryTreeNode,
                          )
                        "
                      >
                        <span class="text-red-500">
                          <DeleteOutlined /> 删除
                        </span>
                      </Menu.Item>
                    </Menu>
                  </template>
                </Dropdown>
              </div>
            </template>
          </Tree>
        </Spin>
      </Card>

      <!-- 右侧关键词列表 -->
      <Card :bordered="false" class="keyword-card">
        <CardHeader class="keyword-card-header">
          <div class="keyword-header-content">
            <div class="breadcrumb-section">
              <div class="breadcrumb-icon">
                <FileTextOutlined />
              </div>
              <div class="breadcrumb-wrapper">
                <Breadcrumb v-if="breadcrumbPath.length > 0">
                  <Breadcrumb.Item
                    v-for="item in breadcrumbPath"
                    :key="item.id"
                  >
                    {{ item.name }}
                  </Breadcrumb.Item>
                </Breadcrumb>
                <span v-else class="breadcrumb-placeholder"
                  >请选择左侧分类</span
                >
              </div>
            </div>
            <div v-if="selectedNode" class="header-actions">
              <Button
                class="add-corpus-btn"
                type="primary"
                size="sm"
                @click="handleAddCorpus"
              >
                <PlusOutlined />
                新增语料
              </Button>
              <div class="toolbar-divider"></div>
              <div class="search-wrapper">
                <SearchOutlined class="search-icon" />
                <Input
                  v-model:value="keywordSearch"
                  placeholder="搜索语料..."
                  class="search-input"
                  allow-clear
                />
              </div>
              <Popconfirm
                v-if="selectedCorpusKeys.length > 0"
                :title="`确定删除选中的 ${selectedCorpusKeys.length} 条语料吗？`"
                @confirm="handleBatchDeleteCorpus"
              >
                <Button danger size="sm">
                  <DeleteOutlined />
                  删除 ({{ selectedCorpusKeys.length }})
                </Button>
              </Popconfirm>
            </div>
          </div>
        </CardHeader>

        <div v-if="!selectedNode" class="empty-content p-5">
          <Empty description="请在左侧选择一个分类" />
        </div>

        <Table
          v-else
          :columns="keywordColumns"
          :data-source="keywords"
          :loading="keywordLoading"
          :pagination="{
            current: keywordPage,
            pageSize: keywordPageSize,
            total: keywordTotal,
            showSizeChanger: true,
            showTotal: (total: number) => `共 ${total} 条`,
          }"
          :row-selection="{
            selectedRowKeys: selectedCorpusKeys,
            onChange: (keys: (string | number)[]) => {
              selectedCorpusKeys = keys.map(String);
            },
          }"
          row-key="id"
          size="small"
          @change="
            (pag: { current?: number; pageSize?: number }) => {
              keywordPage = pag.current || 1;
              keywordPageSize = pag.pageSize || 20;
              fetchKeywords();
            }
          "
        >
          <template #bodyCell="{ column, record }">
            <!-- 语料内容列：区分结构化和普通格式 -->
            <template v-if="column.key === 'name'">
              <div
                v-if="isStructuredCorpus(record as KeywordItem)"
                class="structured-corpus"
              >
                <div
                  v-for="field in getStructuredFields(record as KeywordItem)"
                  :key="field.key"
                  class="corpus-field"
                >
                  <span class="field-label">{{ field.key }}</span>
                  <span class="field-value">{{ field.value }}</span>
                </div>
              </div>
              <div v-else class="plain-corpus">
                {{ (record as KeywordItem).name }}
              </div>
            </template>
            <!-- 格式列 -->
            <template v-else-if="column.key === 'format'">
              <Tag
                v-if="isStructuredCorpus(record as KeywordItem)"
                color="blue"
              >
                {{ getTemplateCode(record as KeywordItem) || '结构化' }}
              </Tag>
              <Tag v-else color="default">文本</Tag>
            </template>
            <!-- 操作列 -->
            <template v-else-if="column.key === 'action'">
              <TableActions
                :actions="getCorpusActions(record)"
                :record="record"
              />
            </template>
          </template>
        </Table>
      </Card>
    </div>

    <!-- 分类编辑弹窗 -->
    <Modal
      v-model:open="categoryModalVisible"
      :title="categoryModalTitle"
      :confirm-loading="categoryModalLoading"
      @ok="handleSaveCategory"
    >
      <div class="form-item">
        <label class="form-label">名称 *</label>
        <Input v-model:value="categoryForm.name" placeholder="如：全职妈妈" />
      </div>
      <!-- 新增子节点时，关键词类型继承父节点，只读显示 -->
      <div v-if="isAddingSubCategory" class="form-item">
        <label class="form-label">关键词类型</label>
        <Input :value="categoryForm.label" disabled style="flex: 1" />
        <p class="mt-1 text-xs text-muted-foreground">
          子节点继承父节点的关键词类型
        </p>
      </div>
      <!-- 正常新增或编辑时，可以选择关键词类型 -->
      <div v-else class="form-item">
        <label class="form-label">关键词类型 *</label>
        <div class="label-input-row">
          <Input
            v-model:value="categoryForm.label"
            placeholder="如：人设、品牌、平台、内容结构、违禁词"
            style="flex: 1"
          />
        </div>
      </div>
      <!-- 新增子节点时显示父节点信息 -->
      <div v-if="isAddingSubCategory" class="form-item">
        <label class="form-label">父节点</label>
        <Input
          :value="getParentNodeName(categoryForm.parent_id)"
          disabled
          style="flex: 1"
        />
      </div>
      <div class="form-item">
        <label class="form-label">描述</label>
        <Input.TextArea
          v-model:value="categoryForm.description"
          placeholder="请输入描述（可选）"
          :rows="2"
        />
      </div>

      <!-- 统一标签选择器 -->
      <div class="form-item">
        <label class="form-label">标签</label>
        <LabelSelector v-model="categoryLabels" tenant-code="default" />
        <p class="mt-1 text-xs text-muted-foreground">
          为节点添加品牌、产品、业务标签等属性，支持动态扩展新类型。
        </p>
      </div>

      <div class="form-item">
        <label class="form-label">归档状态</label>
        <div class="flex items-center gap-2">
          <Switch
            v-model:checked="categoryForm.is_active"
            :checked-value="1"
            :un-checked-value="0"
          />
          <span>{{ categoryForm.is_active === 1 ? '启用' : '归档' }}</span>
        </div>
        <p class="mt-1 text-xs text-muted-foreground">
          归档后的分类不会在关键词树中显示（可通过筛选器查看）。
        </p>
      </div>
    </Modal>

    <!-- 语料编辑弹窗 -->
    <Modal
      v-model:open="corpusModalVisible"
      :title="corpusModalTitle"
      :confirm-loading="corpusModalLoading"
      :width="corpusForm.usePlainText ? 500 : 600"
      @ok="handleSaveCorpus"
    >
      <Spin :spinning="corpusTemplateLoading">
        <!-- 加载完成就显示内容（无论是否有模板） -->
        <template v-if="!corpusTemplateLoading">
          <!-- 模板选择器（总是显示） -->
          <div class="form-item mb-4">
            <label class="form-label">语料模板</label>
            <Select
              v-model:value="corpusForm.templateCode"
              :options="[
                { value: '', label: '不使用模板（纯文本）' },
                { value: '__custom__', label: '不使用模板（自定义字段）' },
                ...allCorpusTemplates.map((t) => ({
                  value: t.code,
                  label: t.name,
                })),
              ]"
              placeholder="选择语料模板或不使用"
              allow-clear
              show-search
              :filter-option="true"
              @change="handleCorpusTemplateChange"
            />
            <p
              v-if="corpusTemplate && corpusTemplate.description"
              class="mt-1 text-xs text-muted-foreground"
            >
              {{ corpusTemplate.description }}
            </p>
            <p
              v-if="corpusForm.usePlainText"
              class="mt-1 text-xs text-muted-foreground"
            >
              纯文本模式：直接添加文本内容，无需结构化字段
            </p>
            <p
              v-if="!corpusForm.templateCode && !corpusForm.usePlainText"
              class="mt-1 text-xs text-muted-foreground"
            >
              不使用模板，仅添加自定义字段
            </p>
          </div>

          <!-- 纯文本模式 -->
          <template v-if="corpusForm.usePlainText">
            <div class="form-item">
              <label class="form-label">文本内容 *</label>
              <Input.TextArea
                v-model:value="corpusForm.plainText"
                placeholder="请输入语料内容..."
                :rows="6"
                :maxlength="5000"
                show-count
              />
            </div>
          </template>

          <!-- 模板字段（仅当选择了模板时显示） -->
          <template v-if="corpusTemplate">
            <div
              v-for="field in corpusTemplate.fields"
              :key="field.key"
              class="form-item"
            >
              <label class="form-label">
                {{ field.label }}
                <span v-if="field.required" class="text-red-500">*</span>
              </label>
              <Input.TextArea
                v-if="field.type === 'textarea'"
                v-model:value="corpusForm.fields[field.key]"
                :placeholder="field.placeholder || `请输入${field.label}`"
                :rows="3"
              />
              <Input
                v-else-if="field.type === 'input'"
                v-model:value="corpusForm.fields[field.key]"
                :placeholder="field.placeholder || `请输入${field.label}`"
              />
              <Select
                v-else-if="field.type === 'select'"
                v-model:value="corpusForm.fields[field.key]"
                :placeholder="field.placeholder || `请选择${field.label}`"
                :options="
                  field.options?.map((opt) => ({ value: opt, label: opt })) ||
                  []
                "
                allow-clear
                show-search
                :filter-option="true"
              />
            </div>
          </template>

          <!-- 自定义字段区域（仅在非纯文本模式显示） -->
          <Separator v-if="!corpusForm.usePlainText" class="my-4">
            <span class="text-xs text-gray-500">
              {{ corpusTemplate ? '自定义字段（可选）' : '自定义字段' }}
            </span>
          </Separator>

          <template v-if="!corpusForm.usePlainText">
            <div
              v-for="(customField, idx) in corpusForm.customFields"
              :key="idx"
              class="custom-field-row"
            >
              <Input
                v-model:value="customField.key"
                placeholder="字段名"
                style="width: 120px"
              />
              <Input
                v-model:value="customField.value"
                placeholder="字段值"
                style="flex: 1; margin: 0 8px"
              />
              <Button
                type="text"
                danger
                size="small"
                @click="corpusForm.customFields.splice(idx, 1)"
              >
                <template #icon><DeleteOutlined /></template>
              </Button>
            </div>

            <Button
              variant="ghost"
              block
              size="small"
              class="mt-2"
              @click="corpusForm.customFields.push({ key: '', value: '' })"
            >
              <template #icon><PlusOutlined /></template>
              添加自定义字段
            </Button>
          </template>
        </template>

        <!-- 模板缺失：友好提示和创建入口 -->
        <template v-else-if="corpusTemplateMissing">
          <div class="template-missing-container">
            <Empty description="">
              <template #image>
                <div class="missing-icon">📋</div>
              </template>
            </Empty>
            <div class="missing-title">该分类尚未配置语料模板</div>
            <div class="missing-desc">
              分类类型「<strong>{{ missingCategoryType }}</strong
              >」需要先创建语料模板，才能添加结构化语料。
            </div>
            <div class="missing-actions">
              <Button
                class="mr-2"
                variant="default"
                @click="handleSkipPlainText"
              >
                纯文本模式
              </Button>
              <Button
                class="mr-2"
                variant="default"
                @click="handleSkipTemplate"
              >
                自定义字段
              </Button>
              <Button
                variant="default"
                @click="
                  () => {
                    corpusModalVisible = false;
                    openQuickCreateTemplate(missingCategoryType);
                  }
                "
              >
                <template #icon><PlusOutlined /></template>
                创建语料模板
              </Button>
            </div>
            <div class="missing-hint">
              💡 创建模板后，可以为该分类添加带字段的结构化语料
            </div>
          </div>
        </template>

        <!-- 加载中 -->
        <template v-else>
          <div class="loading-placeholder">正在加载模板信息...</div>
        </template>
      </Spin>
    </Modal>

    <!-- 快速创建语料模板弹窗 -->
    <Modal
      v-model:open="quickCreateTemplateVisible"
      title="创建语料模板"
      :confirm-loading="quickCreateTemplateLoading"
      width="600px"
      @ok="submitQuickCreateTemplate"
    >
      <div class="quick-template-form">
        <Alert type="info" show-icon class="mb-4">
          <template #message>什么是语料模板？</template>
          <template #description>
            语料模板定义了该分类下语料的字段结构。例如「人设」分类可能包含：基础身份、行文风格、育儿理念等字段。
          </template>
        </Alert>

        <div class="form-item">
          <label class="form-label">模板名称 *</label>
          <Input
            v-model:value="quickCreateTemplateForm.name"
            placeholder="如：人设语料模板"
          />
        </div>

        <div class="form-item">
          <label class="form-label">维度标签 *</label>
          <Input
            v-model:value="quickCreateTemplateForm.dimensionLabel"
            placeholder="如：人设、场景、卖点"
            disabled
          />
          <p class="mt-1 text-xs text-muted-foreground">
            维度标签需与节点的 label 一致
          </p>
        </div>

        <div class="form-item">
          <label class="form-label">模板描述</label>
          <Input.TextArea
            v-model:value="quickCreateTemplateForm.description"
            placeholder="描述这个模板的用途"
            :rows="2"
          />
        </div>

        <Separator class="my-4">
          <span class="text-sm text-gray-600">模板字段配置</span>
        </Separator>

        <div
          v-for="(field, idx) in quickCreateTemplateForm.fields"
          :key="idx"
          class="template-field-row"
        >
          <div class="field-inputs">
            <Input
              v-model:value="field.key"
              placeholder="字段 key"
              style="width: 100px"
              @blur="
                () => {
                  if (!field.label) field.label = field.key;
                }
              "
            />
            <Input
              v-model:value="field.label"
              placeholder="显示名称"
              style="width: 100px"
            />
            <Select
              v-model:value="field.type"
              style="width: 100px"
              :options="[
                { value: 'textarea', label: '多行文本' },
                { value: 'input', label: '单行文本' },
                { value: 'select', label: '下拉选择' },
              ]"
            />
            <label class="required-checkbox">
              <input v-model="field.required" type="checkbox" />
              必填
            </label>
          </div>
          <Button
            v-if="quickCreateTemplateForm.fields.length > 1"
            danger
            @click="removeTemplateField(idx)"
          >
            <template #icon><DeleteOutlined /></template>
            删除
          </Button>
        </div>

        <Button
          variant="ghost"
          block
          size="small"
          class="mt-3"
          @click="addTemplateField"
        >
          <template #icon><PlusOutlined /></template>
          添加字段
        </Button>
      </div>
    </Modal>

    <!-- CSV 导入弹窗 -->
    <Modal
      v-model:open="importModalVisible"
      title="批量导入语料"
      :confirm-loading="importLoading"
      width="800px"
      @ok="handleImportSubmit"
    >
      <!-- 父节点选择（自动获取分类类型） -->
      <div v-if="importTemplateList.length > 1" class="form-item">
        <label class="form-label">
          选择模板 *
          <span class="label-hint">（该分类有多个模板可用）</span>
        </label>
        <Select
          v-model:value="importSelectedTemplateCode"
          placeholder="请选择要使用的模板"
          style="width: 100%"
          :loading="importTemplateLoading"
          show-search
          :filter-option="true"
          @change="
            () => {
              importStructuredData = [];
            }
          "
        >
          <Select.Option
            v-for="tpl in importTemplateList"
            :key="tpl.code"
            :value="tpl.code"
          >
            {{ tpl.name }} ({{ tpl.code }})
          </Select.Option>
        </Select>
      </div>

      <!-- 导入说明 -->
      <Alert v-if="importDimensionType" type="info" show-icon class="mb-4">
        <template #message>
          {{
            dimensionGuides.find((d) => d.type === importDimensionType)?.name
          }}
          导入格式
        </template>
        <template #description>
          <div class="text-sm">
            <p class="mb-2">
              CSV 格式：<code
                >关键词, {{ importDimensionFields.join(', ') }}</code
              >
            </p>
            <ul class="list-disc pl-4">
              <li>第一列是关键词</li>
              <li>后续列对应模板字段</li>
              <li>同一关键词可多行，每行是一条语料</li>
              <li>如果内容包含逗号，需用英文双引号包裹</li>
            </ul>
            <Button
              type="primary"
              class="mt-2"
              :loading="importTemplateLoading"
              @click="handleDownloadImportTemplate"
            >
              <template #icon><DownloadOutlined /></template>
              下载
              {{
                dimensionGuides.find((d) => d.type === importDimensionType)
                  ?.name
              }}
              模板
            </Button>
          </div>
        </template>
      </Alert>

      <!-- 父节点选择 -->
      <div class="form-item">
        <label class="form-label">
          目标父节点
          <span class="label-hint">（导入的节点将作为此节点的子节点）</span>
        </label>
        <TreeSelect
          v-model:value="importParentNodeId"
          :tree-data="parentTreeData"
          placeholder="选择父节点（自动使用其分类类型）"
          allow-clear
          show-search
          tree-node-filter-prop="title"
          style="width: 100%"
          :dropdown-style="{
            maxHeight: '300px',
            minWidth: '400px',
            overflow: 'auto',
          }"
          @change="handleParentNodeChange"
        />
      </div>

      <!-- 文件上传 -->
      <div class="form-item">
        <label class="form-label">上传 CSV 文件 *</label>
        <Upload accept=".csv" :max-count="1" :before-upload="handleCsvUpload">
          <Button :disabled="!importParentNodeId">
            <template #icon><UploadOutlined /></template>
            选择文件
          </Button>
        </Upload>
      </div>

      <!-- 冲突策略 -->
      <div class="form-item">
        <label class="form-label">重复语料处理</label>
        <Radio.Group v-model:value="importConflictStrategy">
          <Radio value="append">追加（保留已有，添加新的）</Radio>
          <Radio value="skip">跳过（忽略重复）</Radio>
          <Radio value="overwrite">覆盖（清空后重新导入）</Radio>
        </Radio.Group>
      </div>

      <!-- 导入后批量打标签 -->
      <Separator>导入后批量打标签</Separator>
      <div class="import-properties-section">
        <p class="mb-3 text-sm text-muted-foreground">
          为<strong>本批次所有关键词</strong>统一打上标签，用于后续筛选和变量绑定
        </p>

        <!-- 统一标签选择器 -->
        <LabelSelector v-model="importLabels" tenant-code="default" />
      </div>

      <!-- 进度条 -->
      <div v-if="importLoading" class="form-item">
        <Progress :percent="Math.round(importProgress)" status="active" />
        <div class="mt-1 text-sm text-muted-foreground">
          正在导入，请勿关闭页面...
        </div>
      </div>

      <!-- 层级数据预览 -->
      <div
        v-if="
          importMode === 'hierarchical' &&
          importHierarchicalData.length > 0 &&
          !importLoading
        "
        class="form-item"
      >
        <label class="form-label">
          <Tag color="purple">层级导入</Tag>
          预览数据（共 {{ importHierarchicalData.length }} 条，{{
            hierarchyColumns.length
          }}
          层分类）
        </label>
        <Table
          :columns="[
            ...hierarchyColumns.map((col, idx) => ({
              title: col,
              dataIndex: ['path', idx],
              width: 120,
              ellipsis: true,
            })),
            { title: '关键词', dataIndex: 'name', width: 120 },
            ...Object.keys(importHierarchicalData[0]?.fields || {}).map(
              (f) => ({
                title: f,
                dataIndex: ['fields', f],
                ellipsis: true,
              }),
            ),
          ]"
          :data-source="importHierarchicalData.slice(0, 10)"
          :pagination="false"
          size="small"
          :scroll="{ x: 800, y: 200 }"
        />
        <div
          v-if="importHierarchicalData.length > 10"
          class="mt-2 text-sm text-muted-foreground"
        >
          ... 还有 {{ importHierarchicalData.length - 10 }} 条数据
        </div>
      </div>

      <!-- 结构化数据预览（单层模式） -->
      <div
        v-if="
          importMode === 'flat' &&
          importStructuredData.length > 0 &&
          !importLoading
        "
        class="form-item"
      >
        <label class="form-label">
          预览数据（共 {{ importStructuredData.length }} 条语料）
        </label>
        <Table
          :columns="[
            { title: '关键词', dataIndex: 'nodeName', width: 150 },
            ...importDimensionFields.map((f) => ({
              title: f,
              dataIndex: ['fields', f],
              ellipsis: true,
            })),
          ]"
          :data-source="importStructuredData.slice(0, 10)"
          :pagination="false"
          size="small"
          :scroll="{ x: 600, y: 200 }"
        />
        <div
          v-if="importStructuredData.length > 10"
          class="mt-2 text-sm text-muted-foreground"
        >
          ... 还有 {{ importStructuredData.length - 10 }} 条数据
        </div>
      </div>
    </Modal>

    <!-- 删除单个节点确认弹窗 -->
    <Modal
      v-model:open="deleteNodeModalVisible"
      title="确认删除"
      :confirm-loading="deleteNodeLoading"
      ok-text="确认删除"
      :ok-button-props="{ danger: true }"
      @ok="handleConfirmDeleteNode"
    >
      <Alert type="error" show-icon>
        <template #message>⚠️ 此操作不可撤销</template>
        <template #description>
          删除后，该分类下的所有子分类和语料都将被永久删除，无法恢复。
        </template>
      </Alert>
      <div v-if="deleteNodeTarget" class="delete-node-info mt-4">
        <p><strong>分类名称：</strong>{{ deleteNodeTarget.name }}</p>
        <p><strong>维度类型：</strong>{{ deleteNodeTarget.label || '-' }}</p>
        <p v-if="deleteNodeTarget.children?.length">
          <strong>包含子节点：</strong>
          <Tag color="orange">{{ deleteNodeTarget.children.length }} 个</Tag>
        </p>
        <p v-if="deleteNodeTarget.corpus?.length">
          <strong>包含语料：</strong>
          <Tag color="red">{{ deleteNodeTarget.corpus.length }} 条</Tag>
        </p>
        <p
          v-if="
            !deleteNodeTarget.children?.length &&
            !deleteNodeTarget.corpus?.length
          "
        >
          <Tag color="green">该节点下没有子节点和语料</Tag>
        </p>
      </div>
    </Modal>

    <!-- 删除子关键词弹窗 -->
    <Modal
      v-model:open="deleteChildrenModalVisible"
      title="删除子关键词"
      :confirm-loading="deleteChildrenLoading"
      @ok="handleDeleteSelectedChildren"
    >
      <Alert type="warning" show-icon class="mb-4">
        <template #message>请选择要删除的子节点</template>
        <template #description>
          删除后，该节点及其所有子节点和语料都将被永久删除。
        </template>
      </Alert>

      <div v-if="deleteChildrenParent?.children?.length" class="children-list">
        <div
          v-for="child in deleteChildrenParent.children"
          :key="child.id"
          class="child-item"
          :class="{ selected: deleteChildrenSelectedIds.includes(child.id) }"
          @click="
            deleteChildrenSelectedIds.includes(child.id)
              ? (deleteChildrenSelectedIds = deleteChildrenSelectedIds.filter(
                  (id) => id !== child.id,
                ))
              : deleteChildrenSelectedIds.push(child.id)
          "
        >
          <input
            type="checkbox"
            :checked="deleteChildrenSelectedIds.includes(child.id)"
            class="mr-2"
          />
          <span class="child-name">{{ child.name }}</span>
          <Tag size="small" class="ml-2">{{ child.label }}</Tag>
          <span v-if="child.children?.length" class="child-count">
            ({{ child.children.length }} 个子节点)
          </span>
          <span v-if="child.corpus?.length" class="corpus-count">
            ({{ child.corpus.length }} 条语料)
          </span>
        </div>
      </div>

      <div class="mt-3 flex justify-between text-sm text-gray-500">
        <span>已选择 {{ deleteChildrenSelectedIds.length }} 项</span>
        <Space>
          <Button
            @click="
              deleteChildrenSelectedIds =
                deleteChildrenParent?.children?.map((c) => c.id) || []
            "
          >
            全选
          </Button>
          <Button @click="deleteChildrenSelectedIds = []"> 清空 </Button>
        </Space>
      </div>
    </Modal>

    <!-- 复制节点弹窗 -->
    <Modal
      v-model:open="copyModalVisible"
      title="复制节点"
      :confirm-loading="copyLoading"
      @ok="handleCopyNode"
    >
      <Alert type="info" show-icon class="mb-4">
        <template #message>
          复制 "{{ copyNodeData?.name }}" 及其所有子节点和语料
        </template>
      </Alert>

      <div class="form-item">
        <label class="form-label">
          目标位置
          <span class="label-hint">（留空则复制为顶层节点）</span>
        </label>
        <TreeSelect
          v-model:value="copyTargetNodeId"
          :tree-data="parentTreeData"
          placeholder="选择目标父节点"
          allow-clear
          show-search
          tree-node-filter-prop="title"
          :dropdown-style="{ maxHeight: '300px', overflow: 'auto' }"
        />
      </div>
    </Modal>

    <!-- 升级 Scope 弹窗已移除（properties 中不再使用 scope 字段） -->

    <!-- 批量设置 Scope 弹窗 -->
    <Modal
      v-model:open="batchScopeModalVisible"
      title="批量设置语料范围"
      :confirm-loading="batchScopeLoading"
      @ok="handleBatchSetScope"
    >
      <Alert type="info" show-icon class="mb-4">
        <template #message>
          为 {{ checkedKeys.length }} 个节点统一设置范围
        </template>
        <template #description>
          <p>设置后，所选节点的范围将被统一更新。</p>
        </template>
      </Alert>

      <div class="form-item">
        <label class="form-label">范围级别</label>
        <Radio.Group v-model:value="batchScopeForm.level" class="w-full">
          <div class="flex flex-col gap-2">
            <Radio value="global">
              <Tag color="blue">全局通用</Tag>
              <span class="ml-2 text-sm text-muted-foreground">
                所有品牌/产品可用
              </span>
            </Radio>
            <Radio value="brand">
              <Tag color="green">品牌级</Tag>
              <span class="ml-2 text-sm text-muted-foreground">
                特定品牌下所有产品可用
              </span>
            </Radio>
            <Radio value="product">
              <Tag color="orange">产品级</Tag>
              <span class="ml-2 text-sm text-muted-foreground">
                仅特定产品可用
              </span>
            </Radio>
          </div>
        </Radio.Group>
      </div>

      <div v-if="batchScopeForm.level !== 'global'" class="form-item mt-4">
        <label class="form-label">品牌</label>
        <Select
          v-model="batchScopeForm.brand_codes"
          mode="multiple"
          :options="brandOptions"
          placeholder="选择品牌（可多选）"
          style="width: 100%"
          allow-clear
          show-search
          :filter-option="true"
        />
        <p class="mt-1 text-xs text-muted-foreground">
          产品级范围建议只选择 1 个品牌（用于加载对应产品列表）
        </p>
      </div>

      <div v-if="batchScopeForm.level === 'product'" class="form-item mt-4">
        <label class="form-label">产品名称</label>
        <Select
          v-model="batchScopeForm.product_names"
          :mode="scopeProductOptions.length > 0 ? 'multiple' : 'tags'"
          :options="scopeProductOptions"
          placeholder="选择或输入产品名称"
          style="width: 100%"
          allow-clear
          show-search
          :filter-option="true"
          :loading="scopeProductLoading"
          @focus="
            fetchScopeProductOptions(
              batchScopeForm.brand_codes[0] || brandCode || undefined,
            )
          "
        />
        <p class="mt-1 text-xs text-muted-foreground">
          {{
            productOptions.length > 0
              ? '选择产品（可多选）'
              : '输入产品名称后按回车添加，可添加多个'
          }}
        </p>
      </div>
    </Modal>

    <!-- 设置 Scope 弹窗 -->
    <Modal
      v-model:open="setScopeModalVisible"
      title="设置语料范围"
      :confirm-loading="setScopeLoading"
      @ok="handleSetScope"
    >
      <Alert type="info" show-icon class="mb-4">
        <template #message>
          设置 "{{ setScopeNodeData?.name }}" 的适用范围
        </template>
        <template #description>
          <p>范围决定了这条语料可以被哪些产品/品牌使用：</p>
          <ul class="mt-2 list-disc pl-4">
            <li><Tag color="blue">全局</Tag> - 所有品牌/产品均可使用</li>
            <li><Tag color="green">品牌级</Tag> - 特定品牌下所有产品可用</li>
            <li><Tag color="orange">产品级</Tag> - 仅特定产品可用</li>
          </ul>
        </template>
      </Alert>

      <div class="form-item">
        <label class="form-label">范围级别</label>
        <Radio.Group v-model:value="setScopeForm.level" class="w-full">
          <div class="flex flex-col gap-2">
            <Radio value="global">
              <Tag color="blue">全局通用</Tag>
              <span class="ml-2 text-sm text-muted-foreground">
                所有品牌/产品可用
              </span>
            </Radio>
            <Radio value="brand">
              <Tag color="green">品牌级</Tag>
              <span class="ml-2 text-sm text-muted-foreground">
                特定品牌下所有产品可用
              </span>
            </Radio>
            <Radio value="product">
              <Tag color="orange">产品级</Tag>
              <span class="ml-2 text-sm text-muted-foreground">
                仅特定产品可用
              </span>
            </Radio>
          </div>
        </Radio.Group>
      </div>

      <div v-if="setScopeForm.level !== 'global'" class="form-item mt-4">
        <label class="form-label">品牌</label>
        <Select
          v-model="setScopeForm.brand_codes"
          mode="multiple"
          :options="brandOptions"
          placeholder="选择品牌（可多选）"
          style="width: 100%"
          allow-clear
        />
        <p class="mt-1 text-xs text-muted-foreground">
          产品级范围仅支持选择 1 个品牌（用于加载对应产品列表）
        </p>
      </div>

      <div v-if="setScopeForm.level === 'product'" class="form-item mt-4">
        <label class="form-label">产品名称</label>
        <Select
          v-model="setScopeForm.product_names"
          :mode="scopeProductOptions.length > 0 ? 'multiple' : 'tags'"
          :options="scopeProductOptions"
          placeholder="选择或输入产品名称"
          style="width: 100%"
          allow-clear
          :loading="scopeProductLoading"
          @focus="
            fetchScopeProductOptions(
              setScopeForm.brand_codes[0] || brandCode || undefined,
            )
          "
        />
        <p class="mt-1 text-xs text-muted-foreground">
          {{
            productOptions.length > 0
              ? '选择产品（可多选）'
              : '输入产品名称后按回车添加，可添加多个'
          }}
        </p>
      </div>
    </Modal>

    <!-- 迁移弹窗（导出/导入） -->
    <Modal
      v-model:open="migrationModalVisible"
      :title="migrationMode === 'export' ? '导出数据' : '导入数据'"
      :confirm-loading="migrationLoading"
      width="600px"
      @ok="
        () => {
          logger.debug('Modal OK button clicked, mode:', migrationMode);
          migrationMode === 'export'
            ? handleExportAllData()
            : handleImportAllData();
        }
      "
    >
      <!-- 导出模式 -->
      <div v-if="migrationMode === 'export'">
        <div class="form-item">
          <label class="form-label">选择分类</label>
          <Select
            v-model:value="migrationSelectedCategories"
            mode="multiple"
            placeholder="全部分类（默认）"
            :options="migrationCategoryOptions"
            allow-clear
            style="width: 100%"
            :get-popup-container="(triggerNode) => triggerNode.parentNode"
          />
          <p class="mt-1 text-xs text-muted-foreground">
            选择要导出的分类，不选则导出全部
          </p>
        </div>
        <div class="form-item">
          <label class="form-label">导出选项</label>
          <div class="flex items-center gap-2">
            <Checkbox v-model:checked="migrationIncludeArchived">
              包含已归档的数据
            </Checkbox>
          </div>
          <p class="mt-1 text-xs text-muted-foreground">
            导出将包含完整的分类树、语料模板和语料数据
          </p>
        </div>
      </div>

      <!-- 导入模式 -->
      <div v-else>
        <div class="form-item">
          <label class="form-label">选择文件 *</label>
          <Upload
            v-model:file-list="migrationFileList"
            :max-count="1"
            :before-upload="() => false"
            accept=".json"
          >
            <Button v-if="migrationFileList.length === 0">
              <UploadOutlined /> 选择 JSON 文件
            </Button>
          </Upload>
          <p class="mt-1 text-xs text-muted-foreground">
            请选择之前导出的 JSON 文件
          </p>
        </div>

        <div class="form-item">
          <label class="form-label">冲突策略</label>
          <RadioGroup v-model:value="migrationConflictStrategy">
            <Radio value="skip">跳过已存在（默认）</Radio>
            <Radio value="overwrite">覆盖已存在</Radio>
          </RadioGroup>
          <p class="mt-1 text-xs text-muted-foreground">
            skip：已存在的节点和模板将被跳过
            <br />
            overwrite：已存在的节点和模板将被覆盖
          </p>
        </div>

        <div class="form-item">
          <label class="form-label">高级选项</label>
          <div class="flex items-center gap-2">
            <Checkbox v-model:checked="migrationSkipTemplates">
              跳过模板创建（仅导入节点）
            </Checkbox>
          </div>
          <p class="mt-1 text-xs text-muted-foreground">
            如果目标环境已有模板，可勾此项跳过模板创建
          </p>
        </div>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
@keyframes expand-tags {
  from {
    opacity: 0;
    transform: scaleY(0.95) translateY(-4px);
  }

  to {
    opacity: 1;
    transform: scaleY(1) translateY(0);
  }
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }

  50% {
    opacity: 0.8;
    transform: scale(1.05);
  }
}

/* ==================== 树形搜索与筛选区域 ==================== */

.tree-search-section {
  margin-bottom: 16px;
}

.search-input-main {
  width: 100%;
}

.search-input-main :deep(.ant-input) {
  height: 44px;
  padding: 0 16px 0 44px;
  font-size: 14px;
  background: hsl(var(--background) / 80%);
  border: 1.5px solid hsl(var(--border) / 60%);
  border-radius: 12px;
  box-shadow: 0 1px 3px hsl(var(--foreground) / 5%);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.search-input-main :deep(.ant-input:focus),
.search-input-main :deep(.ant-input:hover) {
  background: hsl(var(--background));
  border-color: hsl(var(--primary) / 60%);
  box-shadow:
    0 0 0 4px hsl(var(--primary) / 8%),
    0 4px 12px hsl(var(--foreground) / 8%);
}

.search-input-main :deep(.ant-input-prefix) {
  margin-right: 12px;
  font-size: 16px;
  color: hsl(var(--muted-foreground));
}

.tree-filter-section {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 12px 16px;
  margin-bottom: 16px;
  background: hsl(var(--muted) / 30%);
  border: 1px solid hsl(var(--border) / 50%);
  border-radius: 10px;
}

.tree-filter-section .filter-label {
  font-size: 12px;
  font-weight: 600;
  color: hsl(var(--muted-foreground));
  text-transform: uppercase;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.tree-filter-section .filter-items {
  display: flex;
  flex: 1;
  gap: 10px;
  align-items: center;
}

.tree-filter-section .filter-select {
  width: 110px;
}

.tree-filter-section .filter-select-wide {
  flex: 1;
  min-width: 160px;
  max-width: 240px;
}

.tree-filter-section .filter-select :deep(.ant-select-selector),
.tree-filter-section .filter-select-wide :deep(.ant-select-selector) {
  height: 36px !important;
  padding: 0 12px !important;
  font-size: 13px;
  background: hsl(var(--background));
  border: 1px solid hsl(var(--border) / 60%);
  border-radius: 8px;
  transition: all 0.2s ease;
}

.tree-filter-section .filter-select :deep(.ant-select-selector:hover),
.tree-filter-section .filter-select-wide :deep(.ant-select-selector:hover) {
  border-color: hsl(var(--primary) / 50%);
}

.tree-filter-section
  .filter-select
  :deep(.ant-select-focused .ant-select-selector),
.tree-filter-section
  .filter-select-wide
  :deep(.ant-select-focused .ant-select-selector) {
  border-color: hsl(var(--primary) / 60%) !important;
  box-shadow: 0 0 0 3px hsl(var(--primary) / 6%) !important;
}

.tree-filter-section .filter-divider {
  width: 1px;
  height: 20px;
  background: hsl(var(--border) / 50%);
}

/* 响应式 - 维度标签自动适应 */

.category-container {
  padding: 16px;
}

/* 筛选行布局 */
.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
}

.filter-item {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
}

.filter-label {
  font-weight: 500;
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.filter-actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
  margin-left: auto;
}

.dimension-selector-inline {
  display: flex;
  gap: 8px;
  align-items: center;
}

.dimension-selector-inline .selector-label {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
}

/* 按钮样式 */

.main-content {
  display: flex;
  gap: 16px;
  height: calc(100vh - 180px);
}

.tree-card {
  flex: 0 0 360px;
  overflow: auto;
}

.keyword-card {
  flex: 1;
  overflow: auto;
}

/* ==================== Card Header 样式优化 ==================== */

.tree-card-header,
.keyword-card-header {
  padding: 16px;
  background: linear-gradient(
    180deg,
    hsl(var(--muted) / 30%) 0%,
    transparent 100%
  );
  border-bottom: 1px solid hsl(var(--border) / 60%);
}

/* 左侧树形卡片头部 */
.tree-header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.tree-header-left {
  display: flex;
  gap: 10px;
  align-items: center;
}

.tree-header-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  font-size: 16px;
  color: hsl(var(--primary));
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 15%) 0%,
    hsl(var(--primary) / 5%) 100%
  );
  border-radius: 8px;
}

.tree-header-title {
  font-size: 15px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.tree-header-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

/* 右侧语料卡片头部 */
.keyword-header-content {
  display: flex;
  gap: 20px;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.breadcrumb-section {
  display: flex;
  flex: 1;
  gap: 10px;
  align-items: center;
  min-width: 0;
}

.breadcrumb-icon {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  font-size: 16px;
  color: hsl(var(--primary));
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 15%) 0%,
    hsl(var(--primary) / 5%) 100%
  );
  border-radius: 8px;
}

.breadcrumb-wrapper {
  display: flex;
  flex: 1;
  gap: 8px;
  align-items: center;
  min-width: 0;
}

.breadcrumb-wrapper :deep(.ant-breadcrumb) {
  font-size: 14px;
}

.breadcrumb-wrapper :deep(.ant-breadcrumb-link) {
  color: hsl(var(--muted-foreground));
  transition: color 0.2s;
}

.breadcrumb-wrapper :deep(.ant-breadcrumb-link:hover) {
  color: hsl(var(--primary));
}

.breadcrumb-wrapper :deep(.ant-breadcrumb-separator) {
  color: hsl(var(--muted-foreground) / 50%);
}

.breadcrumb-placeholder {
  font-size: 14px;
  color: hsl(var(--muted-foreground));
}

/* 搜索框样式 */
.search-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.search-wrapper .search-icon {
  position: absolute;
  left: 12px;
  z-index: 1;
  font-size: 14px;
  color: hsl(var(--muted-foreground));
  pointer-events: none;
}

.search-wrapper .search-input {
  width: 180px;
}

.search-wrapper .search-input :deep(.ant-input) {
  height: 36px;
  padding-left: 36px;
  background: hsl(var(--background));
  border-color: hsl(var(--border) / 60%);
  border-radius: 8px;
  transition: all 0.2s;
}

.search-wrapper .search-input :deep(.ant-input:focus) {
  border-color: hsl(var(--primary));
  box-shadow: 0 0 0 3px hsl(var(--primary) / 10%);
}

/* 右侧工具栏 */
.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.toolbar-divider {
  width: 1px;
  height: 24px;
  background: hsl(var(--border) / 50%);
}

/* 新增语料主按钮 */
.add-corpus-btn {
  display: flex;
  gap: 6px;
  align-items: center;
  font-weight: 500;
}

/* ==================== 按钮样式优化 ==================== */

.action-btn {
  position: relative;
  display: inline-flex;
  gap: 6px;
  align-items: center;
  height: 36px;
  padding: 0 14px;
  overflow: hidden;
  font-size: 13px;
  font-weight: 500;
  border-radius: 8px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.action-btn .btn-icon {
  font-size: 14px;
}

.action-btn .btn-label {
  line-height: 1;
}

/* Ghost 变体按钮 */
.action-btn:where(:not(.primary-action):not(.danger-btn)) {
  color: hsl(var(--foreground));
  background: transparent;
  border: 1px solid hsl(var(--border) / 50%);
}

.action-btn:where(:not(.primary-action):not(.danger-btn)):hover {
  background: hsl(var(--muted) / 50%);
  border-color: hsl(var(--border));
  transform: translateY(-1px);
}

.action-btn:where(:not(.primary-action):not(.danger-btn)):active {
  transform: translateY(0);
}

/* 主要操作按钮 */
.primary-action {
  color: white;
  background: linear-gradient(
    135deg,
    hsl(var(--primary)) 0%,
    hsl(var(--primary) / 85%) 100%
  );
  border-color: transparent;
  box-shadow: 0 2px 8px hsl(var(--primary) / 25%);
}

.primary-action:hover {
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 90%) 0%,
    hsl(var(--primary) / 75%) 100%
  );
  box-shadow: 0 4px 12px hsl(var(--primary) / 35%);
  transform: translateY(-1px);
}

.primary-action:active {
  box-shadow: 0 2px 6px hsl(var(--primary) / 25%);
  transform: translateY(0);
}

/* 危险按钮 */
.danger-btn {
  color: white;
  background: linear-gradient(
    135deg,
    hsl(var(--destructive)) 0%,
    hsl(var(--destructive) / 85%) 100%
  );
  border-color: transparent;
  box-shadow: 0 2px 8px hsl(var(--destructive) / 25%);
}

.danger-btn:hover {
  background: linear-gradient(
    135deg,
    hsl(var(--destructive) / 90%) 0%,
    hsl(var(--destructive) / 75%) 100%
  );
  box-shadow: 0 4px 12px hsl(var(--destructive) / 35%);
  transform: translateY(-1px);
}

/* 激活状态 */
.action-btn.active {
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 15%);
  border-color: hsl(var(--primary));
}

/* 按钮涟漪效果 */
.action-btn::before {
  position: absolute;
  inset: 0;
  pointer-events: none;
  content: '';
  background: radial-gradient(
    circle at var(--x, 50%) var(--y, 50%),
    hsl(var(--foreground) / 10%),
    transparent 60%
  );
  opacity: 0;
  transition: opacity 0.3s;
}

.action-btn:active::before {
  opacity: 1;
  transition: opacity 0s;
}

/* 兼容旧的样式 */
.card-title-content {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.action-buttons {
  display: flex;
  gap: 8px;
  align-items: center;
}

.search-input-compact {
  width: 200px;
}

.tree-node-title {
  display: flex;
  gap: 6px;
  align-items: center;
  width: 100%;
  min-width: 0;
  overflow: hidden;

  /* 确保标签不会撑开容器 */
  .ant-tag {
    max-width: fit-content;
  }
}

.node-name {
  flex-shrink: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-copy-btn {
  flex-shrink: 0;
  margin-left: 4px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  cursor: pointer;
  opacity: 0;
  transition:
    opacity 0.2s,
    color 0.2s;
}

.tree-node-title:hover .node-copy-btn {
  opacity: 1;
}

.node-copy-btn:hover {
  color: hsl(var(--primary));
}

.node-name.search-highlight {
  padding: 0 4px;
  color: #000;
  background: linear-gradient(120deg, #ffd54f 0%, #ffecb3 100%);
  border-radius: 3px;
}

.corpus-count {
  flex-shrink: 0;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
  opacity: 0.8;
}

.node-action {
  padding: 4px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s;
}

.tree-node-title:hover .node-action {
  opacity: 1;
}

.empty-tree,
.empty-content {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}

.batch-action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  margin-bottom: 12px;
  background: hsl(var(--primary) / 10%);
  border: 1px solid hsl(var(--primary) / 30%);
  border-radius: 6px;
}

.batch-action-bar .selected-count {
  font-weight: 500;
  color: hsl(var(--primary));
}

.import-scope-custom {
  padding: 12px;
  margin-top: 12px;
  background: hsl(var(--muted) / 30%);
  border-radius: 8px;
}

.form-item {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
}

.form-select {
  width: 100%;
  height: 32px;
  padding: 4px 11px;
  color: hsl(var(--foreground));
  background: hsl(var(--background));
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
}

.form-select:focus {
  outline: none;
  border-color: hsl(var(--primary));
}

.label-hint {
  font-size: 12px;
  font-weight: normal;
  color: hsl(var(--muted-foreground));
}

.label-input-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sibling-labels {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.sibling-hint {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.sibling-label-tag {
  cursor: pointer;
  transition: transform 0.2s;
}

.sibling-label-tag:hover {
  transform: scale(1.05);
}

.label-tag {
  flex-shrink: 0;
  padding: 1px 4px;
  margin-left: 4px;
  font-size: 10px;
  line-height: 1;
  opacity: 0.85;
  transition: all 0.2s ease;

  &:hover {
    box-shadow: rgb(0 0 0 / 10%) 0 2px 4px;
    transform: translateY(-1px);
  }
}

.system-intro {
  margin-bottom: 16px;
}

.intro-title {
  font-weight: 600;
}

.intro-content {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 4px;
}

.intro-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.intro-label {
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 500;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 10%);
  border-radius: 4px;
}

.intro-desc {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

/* 结构化语料展示 */
.structured-corpus {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 0;
}

.corpus-field {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 4px 8px;
  background: hsl(var(--muted) / 30%);
  border-radius: 4px;
}

.corpus-field .field-label {
  flex-shrink: 0;
  min-width: 80px;
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 500;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 10%);
  border-radius: 4px;
}

.corpus-field .field-value {
  flex: 1;
  font-size: 13px;
  line-height: 1.5;
  color: hsl(var(--foreground));
  overflow-wrap: break-word;
}

.plain-corpus {
  padding: 4px 0;
  font-size: 13px;
  line-height: 1.5;
  overflow-wrap: break-word;
  white-space: pre-wrap;
}

/* 分类卡片 */

/* 维度选择器 */
.dimension-selector {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 16px;
}

.selector-label {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.dimension-option {
  display: flex;
  gap: 8px;
  align-items: center;
}

.option-icon {
  font-size: 14px;
  color: hsl(var(--primary));
}

.option-count {
  padding: 1px 6px;
  margin-left: auto;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted));
  border-radius: 10px;
}

.stat-count {
  padding: 2px 6px;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 10%);
  border-radius: 4px;
}

/* 分类指南 */
.dimension-guide {
  margin-bottom: 16px;
}

.guide-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 8px;
}

.guide-desc {
  margin: 0;
  font-size: 13px;
  color: hsl(var(--foreground));
}

.guide-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.guide-example {
  padding: 8px 12px;
  font-size: 13px;
  background: hsl(var(--muted) / 30%);
  border-radius: 4px;
}

.example-text {
  color: hsl(var(--muted-foreground));
}

.guide-actions {
  display: flex;
  gap: 8px;
}

.custom-field-row {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

/* Scope 筛选样式 */
.scope-filter-label {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 4px 8px;
  font-size: 13px;
  color: hsl(var(--foreground));
  cursor: pointer;
  background: hsl(var(--muted) / 30%);
  border-radius: 4px;
  transition: background 0.2s;
}

.scope-filter-label:hover {
  background: hsl(var(--muted) / 50%);
}

.scope-filter-label input[type='checkbox'] {
  width: 14px;
  height: 14px;
  accent-color: hsl(var(--primary));
  cursor: pointer;
}

/* 品牌标签样式 */
.brand-tag {
  flex-shrink: 1;
  max-width: 120px;
  margin-left: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 10px;
  white-space: nowrap;
  transition: all 0.2s ease;

  &:hover {
    box-shadow: rgb(0 0 0 / 10%) 0 2px 4px;
    transform: translateY(-1px);
  }
}

/* 产品标签样式 */
.product-tag {
  flex-shrink: 1;
  max-width: 120px;
  margin-left: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 10px;
  white-space: nowrap;
  transition: all 0.2s ease;

  &:hover {
    box-shadow: rgb(0 0 0 / 10%) 0 2px 4px;
    transform: translateY(-1px);
  }
}

.node-tags {
  position: relative;
  display: flex;
  flex: 1;
  gap: 4px;
  align-items: center;
  min-width: 0;
  max-width: calc(100% - 60px);
  overflow: hidden;
  white-space: nowrap;

  /* 渐变遮罩 - 隐藏溢出的标签 */
  &::after {
    position: absolute;
    top: 0;
    right: 0;
    z-index: 1;
    width: 32px;
    height: 100%;
    pointer-events: none;
    content: '';
    background: linear-gradient(to right, transparent 0%, hsl(var(--bg)) 100%);
    transition: opacity 0.3s ease;
  }

  /* 展开状态下隐藏渐变遮罩 */
  &.node-tags-expanded::after {
    opacity: 0;
  }
}

.node-tags-expanded {
  flex-wrap: wrap;
  max-width: 100%;
  overflow: visible;
  white-space: normal;
  animation: expand-tags 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}

/* 业务标签样式 */
.business-tag {
  flex-shrink: 1;
  max-width: 120px;
  margin-left: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 10px;
  white-space: nowrap;
  transition: all 0.2s ease;

  &:hover {
    box-shadow: rgb(0 0 0 / 10%) 0 2px 4px;
    transform: translateY(-1px);
  }
}

.more-tags {
  position: relative;
  z-index: 2;
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  min-width: 32px;
  height: 20px;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 600;
  color: hsl(var(--primary-foreground));
  background: hsl(var(--primary));
  border-radius: 6px;
  box-shadow: 0 1px 3px rgb(0 0 0 / 12%);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.more-tags-action {
  cursor: pointer;
  user-select: none;

  &:hover {
    box-shadow: 0 4px 8px rgb(0 0 0 / 15%);
    transform: translateY(-1px) scale(1.05);
  }

  &:active {
    transform: translateY(0) scale(0.98);
  }
}

/* 模板缺失提示样式 */
.template-missing-container {
  padding: 24px 16px;
  text-align: center;
}

.template-missing-container .missing-icon {
  margin-bottom: 12px;
  font-size: 48px;
}

.template-missing-container .missing-title {
  margin-bottom: 8px;
  font-size: 16px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.template-missing-container .missing-desc {
  margin-bottom: 16px;
  font-size: 14px;
  line-height: 1.5;
  color: hsl(var(--muted-foreground));
}

.template-missing-container .missing-actions {
  margin-bottom: 16px;
}

.template-missing-container .missing-hint {
  display: inline-block;
  padding: 8px 12px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted) / 50%);
  border-radius: 6px;
}

.loading-placeholder {
  padding: 40px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

/* 快速创建模板弹窗样式 */
.quick-template-form .form-item {
  margin-bottom: 16px;
}

.quick-template-form .form-label {
  display: block;
  margin-bottom: 6px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.template-field-row {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px;
  margin-bottom: 8px;
  background: hsl(var(--muted) / 30%);
  border-radius: 6px;
}

.template-field-row .field-inputs {
  display: flex;
  flex: 1;
  gap: 8px;
  align-items: center;
}

.template-field-row .required-checkbox {
  display: flex;
  gap: 4px;
  align-items: center;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
  cursor: pointer;
}

.template-field-row .required-checkbox input {
  width: 14px;
  height: 14px;
  accent-color: hsl(var(--primary));
}
</style>
