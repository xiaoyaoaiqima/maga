<script setup lang="ts">
import type { ContentStrategyApi } from '#/api/core/content-strategy';

import { computed, h, onMounted, ref, toRaw, watch } from 'vue';

import {
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  FolderOpenOutlined,
  FolderOutlined,
  InfoCircleOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  UndoOutlined,
} from '@ant-design/icons-vue';
import {
  Button,
  Divider,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  Popconfirm,
  Radio,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Tooltip,
  TreeSelect,
} from 'ant-design-vue';

import {
  archiveContentStrategyApi,
  createContentStrategyApi,
  deleteContentStrategyApi,
  generateCombinationsApi,
  getAvailableDimensionsApi,
  getContentStrategiesApi,
  getContentStrategyApi,
  unarchiveContentStrategyApi,
  updateContentStrategyApi,
} from '#/api/core/content-strategy';
import { requestClient } from '#/api/request';

// ==================== 类型定义 ====================

interface CategoryTreeApiNode {
  id?: number | string; // 后端可能返回数字或字符串类型的 ID
  name?: string;
  label?: null | string;
  category_type?: null | string;
  tags?: string[];
  brands?: string[];
  products?: string[];
  properties?: Record<string, unknown>;
  corpus?: unknown[];
  children?: CategoryTreeApiNode[];
}

interface CategoryTreeNode {
  id: string;
  name: string;
  label: null | string;
  category_type?: null | string;
  title: string;
  value: string;
  key: string;
  disabled?: boolean;
  disableCheckbox?: boolean;
  tags?: string[];
  brands?: string[];
  products?: string[];
  properties?: Record<string, unknown>;
  corpus?: unknown[];
  children?: CategoryTreeNode[];
}

interface TagRenderProps {
  label: string;
  value: string;
  closable?: boolean;
  onClose?: (event: MouseEvent) => void;
}

// 扁平化的节点映射表，用于快速查找节点信息
const nodeInfoMap = ref<Map<string, { name: string; value: string }>>(
  new Map(),
);

// ==================== 状态 ====================

// 列表
const loading = ref(false);
const strategies = ref<ContentStrategyApi.ContentStrategy[]>([]);
const pagination = ref({
  current: 1,
  pageSize: 20,
  total: 0,
});

// 租户筛选（固定为 default）
const SELECTED_TENANT_CODE = 'default';

// 搜索筛选状态
const searchName = ref('');
const searchTags = ref<string[]>([]);
const searchIsActive = ref<number | undefined>(1); // 默认显示启用状态
const lastUpdateTime = ref('');

// 可用维度
const availableDimensions = ref<ContentStrategyApi.AvailableDimension[]>([]);

// 分类树（用于选择节点）
const categoryTree = ref<CategoryTreeNode[]>([]);
const categoryTreeLoading = ref(false);

// ==================== 节点筛选状态 ====================

// 节点筛选器选项
const nodeFilterBrandOptions = ref<Array<{ label: string; value: string }>>([]);
const nodeFilterTagOptions = ref<Array<{ label: string; value: string }>>([]);

// 每个维度的筛选状态（按维度索引存储）
interface DimensionFilter {
  brands: string[];
  tags: string[];
}
const dimensionFilters = ref<Record<number, DimensionFilter>>({});

// ==================== 弹窗状态 ====================

const modalVisible = ref(false);
const modalTitle = ref('新增内容策略');
const modalLoading = ref(false);
const formLoading = ref(false); // 弹窗内表单加载状态
const isEditing = ref(false);
const editingId = ref<null | string>(null);

// 表单数据
const form = ref<{
  defined_combinations: ContentStrategyApi.DefinedCombination[];
  description: string;
  dimensions: ContentStrategyApi.DimensionConfig[];
  max_combinations: number;
  name: string;
  node_pools: Record<string, string[]>;
  settings: ContentStrategyApi.StrategySettings;
  tags: string[];
}>({
  name: '',
  description: '',
  dimensions: [],
  node_pools: {},
  defined_combinations: [],
  max_combinations: 200,
  settings: {
    include_corpus: true,
  },
  tags: [],
});

// 辅助函数：从 dimensions 构建符合 v3 schema 的 node_pools 格式
function dimensionsToNodePools(
  dimensions: ContentStrategyApi.DimensionConfig[],
): Record<string, { node_ids: string[]; select_mode: 'multiple' | 'single' }> {
  const result: Record<
    string,
    { node_ids: string[]; select_mode: 'multiple' | 'single' }
  > = {};

  for (const dim of dimensions) {
    if (dim.dimension_type && dim.node_ids) {
      result[dim.dimension_type] = {
        node_ids: dim.node_ids,
        select_mode: dim.select_mode || 'single', // 默认 single
      };
    }
  }

  return result;
}

// 手动组合编辑弹窗
const comboModalVisible = ref(false);
const comboModalTitle = ref('添加组合');
const editingComboIndex = ref<null | number>(null);
const comboForm = ref<{
  name: string;
  nodes: Record<string, string>;
}>({
  name: '',
  nodes: {},
});

// 测试弹窗
const testModalVisible = ref(false);
const testLoading = ref(false);
const testResult = ref<ContentStrategyApi.GenerateResponse | null>(null);
const testCount = ref(5);
const testingStrategyId = ref<null | string>(null);

// 笛卡尔积组合（前端计算，内部使用）
const cartesianCombinations = ref<ContentStrategyApi.CombinationItem[]>([]);

// 撤销功能：保存上一次的组合状态
const previousCombinations = ref<ContentStrategyApi.DefinedCombination[]>([]);
const canUndo = ref(false);

// ==================== 计算属性 ====================

// 检查是否已配置维度且有节点选择

// Popconfirm 弹出层挂载到 body，避免被 Table 容器裁剪
const getPopupContainerBody = () => document.body;
const hasDimensionsConfigured = computed(() => {
  return form.value.dimensions.some(
    (dim) => dim.node_ids && dim.node_ids.length > 0,
  );
});

const columns = [
  { title: '策略名称', dataIndex: 'name', key: 'name', width: 200 },
  {
    title: '描述',
    dataIndex: 'description',
    key: 'description',
    ellipsis: true,
  },
  { title: '标签', key: 'tags', width: 150 },
  { title: '分类数', key: 'dimensions', width: 80 },
  { title: '组合数', key: 'combinations_count', width: 80 },
  { title: '状态', key: 'is_active', width: 80 },
  {
    title: '创建时间',
    dataIndex: 'create_time',
    key: 'create_time',
    width: 180,
  },
  { title: '操作', key: 'actions', width: 200, fixed: 'right' as const },
];

// combinationModeOptions 已移除，统一使用 defined_combinations

// v1 旧选项（保留向后兼容）
const selectStrategyOptions = [
  { value: 'all', label: '全部' },
  { value: 'random', label: '随机' },
  { value: 'weighted', label: '按权重' },
];

// ==================== 方法 ====================

// 从 node_pools 转换为 dimensions 格式（兼容 v3 数据）
const nodePoolsToDimensions = (
  nodePools: Record<string, unknown>,
  availableDims: ContentStrategyApi.AvailableDimension[],
): ContentStrategyApi.DimensionConfig[] => {
  if (!nodePools || Object.keys(nodePools).length === 0) {
    return [];
  }

  const result: ContentStrategyApi.DimensionConfig[] = [];
  let order = 0;

  for (const [dimType, poolData] of Object.entries(nodePools)) {
    // 兼容旧格式（直接是数组）和新格式（dict with node_ids + select_mode）
    let nodeIds: string[] = [];
    let selectMode: 'multiple' | 'single' = 'single'; // 默认 single（与 dimensionsToNodePools 保持一致）

    if (Array.isArray(poolData)) {
      // 旧格式：直接是数组，默认 single（保持一致）
      nodeIds = poolData;
      selectMode = 'single';
    } else if (typeof poolData === 'object' && poolData !== null) {
      // 新格式：{node_ids: [], select_mode: 'single' | 'multiple'}
      const poolObj = poolData as Record<string, unknown>;
      nodeIds = (poolObj.node_ids as string[]) || [];
      selectMode = (poolObj.select_mode as 'multiple' | 'single') || 'single'; // 默认 single
    }

    // 查找维度的显示名称
    const dimInfo = availableDims.find((d) => d.dimension_type === dimType);
    const dimName = dimInfo?.dimension_name || dimType;

    result.push({
      dimension_type: dimType,
      dimension_name: dimName,
      select_mode: selectMode,
      required: true,
      node_ids: nodeIds,
      select_strategy: 'all',
      select_count: 1,
      order: order++,
    });
  }

  return result;
};

const is_content_strategy = (
  record: unknown,
): record is ContentStrategyApi.ContentStrategy => {
  if (!record || typeof record !== 'object') return false;
  const r = record as Record<string, unknown>;
  return (
    typeof r.id === 'string' &&
    typeof r.name === 'string' &&
    typeof r.tenant_code === 'string'
  );
};

// 获取策略列表
const fetchStrategies = async () => {
  loading.value = true;
  try {
    const res = await getContentStrategiesApi({
      page: pagination.value.current,
      page_size: pagination.value.pageSize,
      tenant_code: SELECTED_TENANT_CODE,
      name: searchName.value || undefined,
      tags: searchTags.value.length > 0 ? searchTags.value : undefined,
      is_active: searchIsActive.value,
    });
    strategies.value = res?.items || [];
    pagination.value.total = res?.page_info?.total || 0;
    // 更新时间
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
    logger.error('获取策略列表失败:', error);
    message.error('获取策略列表失败');
  } finally {
    loading.value = false;
  }
};

// 重置搜索
const handleResetSearch = () => {
  searchName.value = '';
  searchTags.value = [];
  searchIsActive.value = undefined;
  pagination.value.current = 1;
  fetchStrategies();
};

// 获取可用维度
const fetchAvailableDimensions = async () => {
  try {
    const res = await getAvailableDimensionsApi('default');
    availableDimensions.value = res?.dimensions || [];
  } catch (error) {
    logger.error('获取可用维度失败:', error);
    availableDimensions.value = [];
  }
};

// 获取分类树
const fetchCategoryTree = async () => {
  categoryTreeLoading.value = true;
  try {
    const res = await requestClient.get<CategoryTreeApiNode[]>(
      '/v1/keyword-corpus/categories/tree',
      {
        params: {
          tenant_code: 'default',
          include_global: true,
          is_active: 1,
        },
      },
    );

    // 清空旧的映射表
    nodeInfoMap.value.clear();

    const normalize_tree_nodes = (
      nodes: CategoryTreeApiNode[],
      parent_key: string,
    ): CategoryTreeNode[] => {
      return nodes
        .map((raw, idx) => {
          // 支持字符串和数字类型的 ID
          const raw_id = raw.id === null ? '' : String(raw.id).trim();
          const has_valid_id = Boolean(raw_id);

          const name = typeof raw.name === 'string' ? raw.name : '';
          const label = typeof raw.label === 'string' ? raw.label : null;
          const category_type =
            typeof raw.category_type === 'string' ? raw.category_type : null;

          const title = name || label || raw_id || '未命名节点';
          const value = has_valid_id ? raw_id : `${parent_key}__group__${idx}`;
          const key = value;

          // 保存节点信息到映射表
          if (has_valid_id && name) {
            nodeInfoMap.value.set(value, { name, value });
          }

          const children = Array.isArray(raw.children)
            ? normalize_tree_nodes(raw.children, `${key}/`)
            : undefined;

          // TreeSelect 必须保证每个节点都有唯一且非空的 value，否则会报警告：
          // - Same `value` exist in the tree
          // - TreeNode `value` is invalidate
          return {
            id: has_valid_id ? raw_id : value,
            name: name || title,
            label,
            category_type,
            title,
            value,
            key,
            // 没有 id 的节点无法参与 node_ids 提交，禁选避免脏值进入表单
            disabled: !has_valid_id,
            disableCheckbox: !has_valid_id,
            // 保留筛选相关字段
            tags: raw.tags || [],
            brands: raw.brands || [],
            products: raw.products || [],
            properties: raw.properties || {},
            corpus: raw.corpus,
            children,
          };
        })
        .filter((n) => Boolean(n.value));
    };

    categoryTree.value = normalize_tree_nodes(res || [], 'root/');
  } catch (error) {
    logger.error('获取分类树失败:', error);
    categoryTree.value = [];
  } finally {
    categoryTreeLoading.value = false;
  }
};

// 打开新增弹窗
const handleAdd = async () => {
  // 先加载必要的数据（可用维度和分类树）
  await Promise.all([
    fetchAvailableDimensions(),
    fetchCategoryTree(),
    fetchNodeFilterOptions(),
  ]);
  // 重置节点筛选条件
  dimensionFilters.value = {};

  isEditing.value = false;
  editingId.value = null;
  modalTitle.value = '新增内容策略';
  form.value = {
    name: '',
    description: '',
    dimensions: [],
    node_pools: {},
    defined_combinations: [],
    max_combinations: 200,
    settings: { include_corpus: true },
    tags: [],
  };
  modalVisible.value = true;
};

// 打开编辑弹窗
const handleEdit = async (record: unknown) => {
  if (!is_content_strategy(record)) {
    message.error('数据格式异常：无法编辑');
    return;
  }

  // 先打开弹窗，设置基本信息和 loading 状态
  isEditing.value = true;
  editingId.value = record.id;
  modalTitle.value = '编辑关键词策略';
  formLoading.value = true;
  modalVisible.value = true;

  form.value = {
    name: record.name,
    description: record.description || '',
    dimensions:
      (record.dimensions as ContentStrategyApi.DimensionConfig[]) || [],
    node_pools: (record.node_pools as Record<string, string[]>) || {},
    defined_combinations:
      (record.defined_combinations as ContentStrategyApi.DefinedCombination[]) ||
      [],
    max_combinations: record.max_combinations || 100,
    settings: (record.settings as ContentStrategyApi.StrategySettings) || {
      include_corpus: true,
      shuffle: false,
    },
    tags: (record.tags as string[]) || [],
  };

  try {
    // 后台并行加载必要的数据（可用维度和分类树）
    await Promise.all([
      fetchAvailableDimensions(),
      fetchCategoryTree(),
      fetchNodeFilterOptions(),
    ]);

    // 兼容 v3 数据：如果 dimensions 为空但 node_pools 有数据，则转换
    if (
      (!form.value.dimensions || form.value.dimensions.length === 0) &&
      form.value.node_pools &&
      Object.keys(form.value.node_pools).length > 0
    ) {
      form.value.dimensions = nodePoolsToDimensions(
        form.value.node_pools as Record<string, unknown>,
        availableDimensions.value,
      );
    }

    // 重置节点筛选条件
    dimensionFilters.value = {};

    // v3 简化：如果 defined_combinations 为空，自动生成组合
    if (
      !form.value.defined_combinations ||
      form.value.defined_combinations.length === 0
    ) {
      computeCartesianCombinations();
      if (cartesianCombinations.value.length > 0) {
        generateDefinedCombinationsFromCartesian(true);
      }
    }
  } finally {
    formLoading.value = false;
  }
};

// 添加维度
const handleAddDimension = () => {
  // 确保 dimensions 是一个数组
  if (!Array.isArray(form.value.dimensions)) {
    form.value.dimensions = [];
  }

  const newIndex = form.value.dimensions.length;

  form.value.dimensions.push({
    dimension_type: '',
    dimension_name: '',
    select_mode: 'single',
    required: true,
    node_ids: [],
    select_strategy: 'all',
    select_count: 1,
    order: newIndex,
  });
};

// 删除维度
const handleRemoveDimension = (index: number) => {
  if (!Array.isArray(form.value.dimensions)) {
    return;
  }
  form.value.dimensions.splice(index, 1);
};

// ==================== 手动组合管理 ====================

// 打开添加组合弹窗
const handleAddCombo = () => {
  comboModalTitle.value = '添加组合';
  editingComboIndex.value = null;
  comboForm.value = {
    name: '',
    nodes: {},
  };
  // 初始化各维度为空
  const dimensions = form.value.dimensions || [];
  for (const dim of dimensions) {
    comboForm.value.nodes[dim.dimension_type] = '';
  }
  comboModalVisible.value = true;
};

// 打开编辑组合弹窗
const handleEditCombo = (index: number) => {
  const combo = form.value.defined_combinations[index];
  if (!combo) return;

  comboModalTitle.value = '编辑组合';
  editingComboIndex.value = index;
  comboForm.value = {
    name: combo.name,
    nodes: { ...combo.nodes },
  };
  comboModalVisible.value = true;
};

// 保存组合
const handleSaveCombo = () => {
  // 生成组合名称（如果没填）
  let comboName = comboForm.value.name;
  if (!comboName) {
    const parts: string[] = [];
    for (const nodeId of Object.values(comboForm.value.nodes)) {
      if (nodeId) {
        const info = nodeInfoMap.value.get(nodeId);
        parts.push(info?.name || nodeId);
      }
    }
    comboName = parts.join(' + ');
  }

  const combo: ContentStrategyApi.DefinedCombination = {
    id:
      editingComboIndex.value === null
        ? `combo_${Date.now()}`
        : form.value.defined_combinations[editingComboIndex.value]?.id ||
          `combo_${Date.now()}`,
    name: comboName,
    nodes: { ...comboForm.value.nodes },
  };

  if (editingComboIndex.value === null) {
    form.value.defined_combinations.push(combo);
  } else {
    form.value.defined_combinations[editingComboIndex.value] = combo;
  }

  comboModalVisible.value = false;
};

// 删除组合（支持撤销）
const handleRemoveCombo = (index: number) => {
  // 保存当前状态以便撤销（BUG-002：使用 structuredClone 避免响应式对象问题）
  try {
    previousCombinations.value = structuredClone(
      toRaw(form.value.defined_combinations),
    );
    canUndo.value = true;
  } catch (error) {
    logger.warn('保存撤销状态失败:', error);
  }

  form.value.defined_combinations.splice(index, 1);
  message.success('已删除组合，如需恢复请点击「撤销」');
};

// 获取组合中节点的显示名称（支持逗号分隔的多节点 ID）
const getComboNodeName = (nodeId: string): string => {
  // 检查是否是多选模式（逗号分隔的多节点）
  if (nodeId.includes(',')) {
    const nodeIds = nodeId.split(',').map((id) => id.trim());
    const names = nodeIds
      .map((id) => nodeInfoMap.value.get(id)?.name || id)
      .filter(Boolean);
    return names.join(', ');
  }
  // 单选模式
  const info = nodeInfoMap.value.get(nodeId);
  return info?.name || nodeId;
};

// 计算笛卡尔积组合（前端计算）
// 支持 select_mode: 单选模式参与笛卡尔积，多选模式所有节点合并为一组
const computeCartesianCombinations = () => {
  const dimensions = form.value.dimensions || [];

  // 分离单选和多选维度
  const singleSelectDims: Array<{
    dimType: string;
    nodeIds: string[];
  }> = [];
  const multiSelectDims: Array<{
    dimType: string;
    nodeIds: string[];
  }> = [];

  for (const dim of dimensions) {
    if (dim.dimension_type && dim.node_ids && dim.node_ids.length > 0) {
      if (dim.select_mode === 'multiple') {
        // 多选模式：所有节点作为一组
        multiSelectDims.push({
          dimType: dim.dimension_type,
          nodeIds: dim.node_ids,
        });
      } else {
        // 单选模式：每个节点参与笛卡尔积
        singleSelectDims.push({
          dimType: dim.dimension_type,
          nodeIds: dim.node_ids,
        });
      }
    }
  }

  // 如果没有任何节点，返回空
  if (singleSelectDims.length === 0 && multiSelectDims.length === 0) {
    cartesianCombinations.value = [];
    return;
  }

  // 计算单选维度的笛卡尔积
  const cartesianProduct = (arrays: string[][]): string[][] => {
    if (arrays.length === 0) return [[]];
    let result: string[][] = [[]];
    for (const arr of arrays) {
      result = result.flatMap((prevItem) =>
        arr.map((currItem) => [...prevItem, currItem]),
      );
    }
    return result;
  };

  const singleNodeLists = singleSelectDims.map((d) => d.nodeIds);
  const singleDimTypes = singleSelectDims.map((d) => d.dimType);
  const cartesianResults = cartesianProduct(singleNodeLists);

  // 组装结果：笛卡尔积结果 + 多选维度（每个组合都包含多选维度的所有节点）
  cartesianCombinations.value = cartesianResults.map((singleNodeIds, idx) => {
    const nodes: Record<string, ContentStrategyApi.NodeInfo> = {};
    const nameParts: string[] = [];

    // 添加单选维度的节点
    singleNodeIds.forEach((nodeId, i) => {
      const info = nodeInfoMap.value.get(nodeId);
      if (info) {
        const dimType = singleDimTypes[i]!;
        nodes[dimType] = {
          id: nodeId,
          name: info.name,
          label: dimType,
        };
        nameParts.push(info.name);
      }
    });

    // 添加多选维度的所有节点（合并为一个字符串，用逗号分隔）
    for (const multiDim of multiSelectDims) {
      const nodeNames: string[] = [];
      const nodeIdsJoined = multiDim.nodeIds.join(',');
      for (const nodeId of multiDim.nodeIds) {
        const info = nodeInfoMap.value.get(nodeId);
        if (info) {
          nodeNames.push(info.name);
        }
      }
      nodes[multiDim.dimType] = {
        id: nodeIdsJoined, // 多个节点ID用逗号分隔
        name: nodeNames.join(', '),
        label: multiDim.dimType,
      };
      if (nodeNames.length > 0) {
        nameParts.push(`[${nodeNames.join(', ')}]`);
      }
    }

    return {
      id: `combo_${idx}`,
      name: nameParts.join(' + '),
      nodes,
    };
  });
};

// 维度类型变化时更新显示名
const handleDimensionTypeChange = (index: number, value: string) => {
  const dim = availableDimensions.value.find((d) => d.dimension_type === value);
  if (!dim) return;
  const target = form.value.dimensions[index];
  if (!target) return;
  target.dimension_name = dim.dimension_name;
  // 清空已选择的节点
  target.node_ids = [];
  // 清空该维度的筛选条件
  dimensionFilters.value[index] = {
    brands: [],
    tags: [],
  };
};

// 选择模式变化时保留已选节点
const handleSelectModeChange = (_index: number, _value: string) => {
  // v-model:value 会自动更新 dimensions[index].select_mode
  // 注意：保存时会从 defined_combinations 重新构建 node_pools，所以不需要手动同步
  // 模式切换时保留所有已选节点，不清空
  // TreeSelect 会根据 multiple 属性自动适配单选/多选行为
};

// 获取节点筛选选项（从元数据 API）
const fetchNodeFilterOptions = async () => {
  try {
    // 获取品牌选项
    const brandRes = await requestClient.get<
      Array<{ id?: string; label: string; value: string }>
    >('/v1/keyword-corpus/metadata/brands/options', {
      params: { tenant_code: 'default' },
    });
    nodeFilterBrandOptions.value = (brandRes || []).map((item) => ({
      value: item.value,
      label: item.label,
    }));

    // 获取标签选项
    const tagRes = await requestClient.get<
      Array<{ id?: string; label: string; value: string }>
    >('/v1/keyword-corpus/metadata/tags/options', {
      params: { tenant_code: 'default' },
    });
    nodeFilterTagOptions.value = (tagRes || []).map((item) => ({
      value: item.value,
      label: item.label,
    }));
  } catch (error) {
    logger.error('获取筛选选项失败:', error);
  }
};

// 获取维度的筛选条件
const getDimensionFilter = (index: number): DimensionFilter => {
  return dimensionFilters.value[index] || { brands: [], tags: [] };
};

// 收集树中所有节点的 ID（用于验证已选节点是否仍在筛选后的树中）
const collectTreeNodeIds = (nodes: CategoryTreeNode[]): Set<string> => {
  const ids = new Set<string>();
  const traverse = (nodeList: CategoryTreeNode[]) => {
    for (const node of nodeList) {
      if (node.value && !node.disabled) {
        ids.add(node.value);
      }
      if (node.children) {
        traverse(node.children);
      }
    }
  };
  traverse(nodes);
  return ids;
};

// 设置维度的筛选条件（同时清理不再匹配的已选节点）
const setDimensionFilter = (
  index: number,
  field: 'brands' | 'tags',
  value: string[],
) => {
  if (!dimensionFilters.value[index]) {
    dimensionFilters.value[index] = { brands: [], tags: [] };
  }
  dimensionFilters.value[index][field] = value;

  // 获取当前维度
  const dim = form.value.dimensions[index];
  if (!dim || !dim.node_ids || dim.node_ids.length === 0) {
    return;
  }

  // 获取筛选后的树
  const filteredTree = getDimensionNodeTree(dim.dimension_type, index);
  if (filteredTree.length === 0) {
    // 筛选后没有节点，清空已选
    dim.node_ids = [];
    return;
  }

  // 收集筛选后树中的所有有效节点 ID
  const validIds = collectTreeNodeIds(filteredTree);

  // 过滤掉不在筛选后树中的已选节点
  const originalCount = dim.node_ids.length;
  dim.node_ids = dim.node_ids.filter((id) => validIds.has(id));

  if (dim.node_ids.length < originalCount) {
    // 清理了不匹配的节点，数量差: ${originalCount - dim.node_ids.length}
  }
};

// 根据 properties 筛选树节点
const filterTreeByProperties = (
  nodes: CategoryTreeNode[],
  filter: DimensionFilter,
): CategoryTreeNode[] => {
  const hasBrandFilter = filter.brands.length > 0;
  const hasTagFilter = filter.tags.length > 0;

  // 如果没有筛选条件，返回原始节点
  if (!hasBrandFilter && !hasTagFilter) {
    return nodes;
  }

  // 递归过滤树节点
  const filterTree = (nodeList: CategoryTreeNode[]): CategoryTreeNode[] => {
    return nodeList
      .map((node) => {
        // 品牌匹配：节点的 brands 包含任一选中的品牌，或没有 brands（全局节点）
        const matchBrand = hasBrandFilter
          ? !node.brands ||
            node.brands.length === 0 ||
            node.brands.some((b) => filter.brands.includes(b))
          : true;

        // 标签匹配：节点的 tags 包含所有选中的标签
        const matchTags = hasTagFilter
          ? filter.tags.every((tag) => (node.tags || []).includes(tag))
          : true;

        // 递归过滤子节点
        const filteredChildren = node.children ? filterTree(node.children) : [];

        // 节点本身匹配，或者子节点有匹配
        if ((matchBrand && matchTags) || filteredChildren.length > 0) {
          return {
            ...node,
            children: filteredChildren,
          };
        }
        return null;
      })
      .filter(Boolean) as CategoryTreeNode[];
  };

  return filterTree(nodes);
};

// 格式化语料内容为可读文本
const formatCorpusContent = (corpus: unknown[]): string => {
  if (!corpus || corpus.length === 0) {
    return '暂无语料内容';
  }
  const items = corpus as Record<string, unknown>[];
  return items
    .map((item) => {
      const parts: string[] = [];
      for (const [key, value] of Object.entries(item)) {
        // 跳过 code、field_keys 等元数据字段
        if (
          key === 'code' ||
          key === 'template_code' ||
          key === 'field' ||
          key === 'field_keys' ||
          key === 'id'
        ) {
          continue;
        }
        if (value === null || value === undefined || value === '') {
          continue;
        }
        // 特殊处理 fields 字段（可能是对象或数组）
        if (key === 'fields') {
          if (Array.isArray(value)) {
            // 数组格式：[{key: "scene", label: "场景", value: "客厅"}]
            const fieldParts = (value as Record<string, unknown>[])
              .filter((f) => {
                return Object.entries(f).some(
                  ([k, v]) =>
                    k !== 'key' &&
                    k !== 'field' &&
                    k !== 'id' &&
                    v !== null &&
                    v !== undefined &&
                    v !== '',
                );
              })
              .map((f) => {
                const fParts = Object.entries(f)
                  .filter(
                    ([k, v]) =>
                      k !== 'key' &&
                      k !== 'field' &&
                      k !== 'id' &&
                      v !== null &&
                      v !== undefined &&
                      v !== '',
                  )
                  .map(([k, v]) => `${k}: ${v}`);
                return fParts.join('，');
              });
            if (fieldParts.length > 0) {
              parts.push(fieldParts.join('；'));
            }
          } else if (typeof value === 'object' && value !== null) {
            // 对象格式：{"场景": "居家", "风格": "现代"}
            const fieldParts = Object.entries(value as Record<string, unknown>)
              .filter(([, v]) => v !== null && v !== undefined && v !== '')
              .map(([k, v]) => `${k}: ${v}`);
            if (fieldParts.length > 0) {
              parts.push(fieldParts.join('；'));
            }
          }
        } else if (typeof value === 'object' && value !== null) {
          parts.push(`${key}: ${JSON.stringify(value)}`);
        } else {
          parts.push(`${key}: ${value}`);
        }
      }
      return parts.join('\n');
    })
    .join('\n--------------------\n');
};

// 获取维度对应的节点树（根据维度索引应用筛选）
const getDimensionNodeTree = (dimensionType: string, dimIndex?: number) => {
  // 从分类树中找到对应维度的节点
  const rootNode = categoryTree.value.find(
    (n) =>
      n.category_type === dimensionType ||
      n.label === dimensionType ||
      n.name === dimensionType ||
      n.id === dimensionType ||
      n.value === dimensionType,
  );

  if (!rootNode) {
    return [];
  }

  // 如果提供了维度索引，应用该维度的筛选条件
  if (dimIndex !== undefined) {
    const filter = getDimensionFilter(dimIndex);
    return filterTreeByProperties([rootNode], filter);
  }

  return [rootNode];
};

// 获取维度中已选中节点的树（用于手动组合选择）
const getSelectedNodesTree = (
  dimension: ContentStrategyApi.DimensionConfig,
) => {
  if (!dimension.node_ids || dimension.node_ids.length === 0) {
    return [];
  }

  // 从分类树中找到对应维度的根节点
  const rootNode = categoryTree.value.find(
    (n) =>
      n.category_type === dimension.dimension_type ||
      n.label === dimension.dimension_type ||
      n.name === dimension.dimension_type ||
      n.id === dimension.dimension_type ||
      n.value === dimension.dimension_type,
  );

  if (!rootNode) {
    return [];
  }

  // 递归提取已选中的节点（保留完整的树结构路径）
  const extractSelectedNodes = (
    node: CategoryTreeNode,
    depth = 0,
  ): CategoryTreeNode | null => {
    // 检查当前节点是否被选中
    const isSelected = dimension.node_ids!.includes(node.value);

    // 递归处理子节点
    const filteredChildren: CategoryTreeNode[] = [];
    if (node.children && node.children.length > 0) {
      for (const child of node.children) {
        const result = extractSelectedNodes(child, depth + 1);
        if (result) {
          filteredChildren.push(result);
        }
      }
    }

    // 如果当前节点被选中，或者有被选中的子节点，则保留
    if (isSelected || filteredChildren.length > 0) {
      return {
        ...node,
        children: filteredChildren.length > 0 ? filteredChildren : undefined,
      };
    }

    return null;
  };

  const result = extractSelectedNodes(rootNode);
  return result ? [result] : [];
};

// 从树中查找节点的标签
const findNodeLabel = (nodes: CategoryTreeNode[], nodeId: string): string => {
  for (const node of nodes) {
    if (node.value === nodeId) {
      // 按优先级返回最友好的名称
      // 1. 优先使用 name（如果存在且不为空）
      if (node.name && node.name.trim()) {
        return node.name;
      }
      // 2. 使用 title（如果存在且不为空）
      if (node.title && node.title.trim()) {
        return node.title;
      }
      // 3. 使用 label（如果存在且不为空）
      if (node.label && node.label.trim()) {
        return node.label;
      }
      // 4. 最后才使用 value（ID）
      return node.value;
    }
    if (node.children) {
      const found = findNodeLabel(node.children, nodeId);
      if (found) return found;
    }
  }

  // 如果找不到节点，返回 ID
  return nodeId;
};

// 获取节点显示名称
const getNodeLabel = (dimensionType: string, nodeId: string) => {
  // 处理多选模式：逗号分隔的多个节点 ID
  if (nodeId.includes(',')) {
    const nodeIds = nodeId.split(',').map((id) => id.trim());
    const names = nodeIds
      .map((id) => {
        const info = nodeInfoMap.value.get(id);
        return info?.name || id;
      })
      .filter(Boolean);
    return names.join(', ');
  }

  // 单选模式：直接从映射表中查找节点信息
  const nodeInfo = nodeInfoMap.value.get(nodeId);

  if (nodeInfo) {
    return nodeInfo.name;
  }

  // 如果映射表中找不到，回退到原来的方法（理论上不应该发生）
  logger.debug('[getNodeLabel] 映射表中未找到节点，尝试从树中查找:', {
    dimensionType,
    nodeId,
    mapSize: nodeInfoMap.value.size,
  });

  const tree = getDimensionNodeTree(dimensionType);
  const label = findNodeLabel(tree, nodeId);

  // 如果返回的仍然是 ID，打印日志帮助调试
  if (label === nodeId) {
    logger.debug('[getNodeLabel] 未找到友好的节点名称:', {
      dimensionType,
      nodeId,
      tree: JSON.stringify(tree, null, 2),
    });
  }

  return label;
};

const renderNodeTag = (dimensionType: string, tag: TagRenderProps) => {
  return h(
    Tag,
    {
      closable: tag.closable,
      onClose: (event: Event) => {
        event.stopPropagation();
        tag.onClose?.(event as MouseEvent);
      },
      onMouseDown: (event: MouseEvent) => {
        event.preventDefault();
      },
      class: 'node-selection-tag',
    },
    () => getNodeLabel(dimensionType, tag.value),
  );
};

// 获取节点权重
const getNodeWeight = (
  dim: ContentStrategyApi.DimensionConfig,
  nodeId: string,
): number => {
  if (!dim.weights) {
    return 1;
  }
  return dim.weights[nodeId] || 1;
};

// 设置节点权重
const setNodeWeight = (
  dim: ContentStrategyApi.DimensionConfig,
  nodeId: string,
  weight: null | number | undefined = 1,
) => {
  if (!dim.weights) {
    dim.weights = {};
  }
  dim.weights[nodeId] = weight ?? 1;
};

// 保存策略
const handleSave = async () => {
  if (!form.value.name.trim()) {
    message.warning('请输入策略名称');
    return;
  }

  // 两种模式都需要 dimensions
  const dimensions = form.value.dimensions || [];
  if (dimensions.length === 0) {
    message.warning('请至少添加一个维度');
    return;
  }

  // v3 简化后必须有组合
  if (
    !form.value.defined_combinations ||
    form.value.defined_combinations.length === 0
  ) {
    message.warning('请至少保留一个组合');
    return;
  }

  // 从 dimensions 构建 node_pools（v3 格式）
  /* @ts-ignore */ // 暂时保留 nodePools 变量，避免 "declared but never used" 警告
  const nodePools = dimensionsToNodePools(dimensions);

  modalLoading.value = true;
  try {
    // 构建保存数据（v3 简化：不发送 dimensions）
    const saveData = {
      name: form.value.name,
      description: form.value.description,
      node_pools: nodePools, // 从 defined_combinations 构建的 node_pools
      max_combinations: form.value.max_combinations,
      settings: form.value.settings,
      defined_combinations: form.value.defined_combinations,
      tags: form.value.tags,
    };

    if (isEditing.value && editingId.value) {
      await updateContentStrategyApi(editingId.value, saveData);
      message.success('更新成功');
    } else {
      await createContentStrategyApi({
        ...saveData,
        tenant_code: 'default',
      });
      message.success('创建成功');
    }
    modalVisible.value = false;
    fetchStrategies();
  } catch (error) {
    logger.error('保存失败:', error);
    message.error('保存失败');
  } finally {
    modalLoading.value = false;
  }
};

// 删除策略
const handleDelete = async (id: string) => {
  try {
    await deleteContentStrategyApi(id);
    message.success('删除成功');
    fetchStrategies();
  } catch (error) {
    logger.error('删除失败:', error);
    message.error('删除失败');
  }
};

// 复制策略
const copyLoading = ref(false);
const handleCopy = async (record: ContentStrategyApi.ContentStrategy) => {
  copyLoading.value = true;
  try {
    // 获取完整策略详情
    const strategy = await getContentStrategyApi(String(record.id));

    if (!strategy) {
      message.error('策略不存在');
      return;
    }

    // 打开编辑弹窗，设置为复制模式
    isEditing.value = false; // 复制 = 新建模式
    editingId.value = null;
    modalTitle.value = '复制策略';
    formLoading.value = false; // 已有数据，不需要 loading
    modalVisible.value = true;

    // 设置表单数据
    form.value = {
      name: `${strategy.name} - 副本`,
      description: strategy.description || '',
      dimensions: [], // 从 node_pools 重建（后续在 fetchAvailableDimensions 后处理）
      node_pools:
        (strategy.node_pools as unknown as Record<string, string[]>) || {},
      defined_combinations:
        (strategy.defined_combinations as ContentStrategyApi.DefinedCombination[]) ||
        [],
      max_combinations: strategy.max_combinations || 100,
      settings: (strategy.settings as ContentStrategyApi.StrategySettings) || {
        include_corpus: true,
        shuffle: false,
      },
      tags: (strategy.tags as string[]) || [],
    };

    // 加载必要数据
    await Promise.all([
      fetchAvailableDimensions(),
      fetchCategoryTree(),
      fetchNodeFilterOptions(),
    ]);

    // 从 node_pools 重建 dimensions（用于 UI 编辑）
    if (strategy.node_pools && Object.keys(strategy.node_pools).length > 0) {
      form.value.dimensions = nodePoolsToDimensions(
        strategy.node_pools as unknown as Record<string, unknown>,
        availableDimensions.value,
      );
    }

    // 重置节点筛选条件
    dimensionFilters.value = {};
  } catch (error) {
    logger.error('加载策略失败:', error);
    message.error('加载策略失败');
  } finally {
    copyLoading.value = false;
  }
};

// 归档/取消归档策略
const archiveLoading = ref(false);
const handleArchive = async (record: ContentStrategyApi.ContentStrategy) => {
  archiveLoading.value = true;
  try {
    if (record.is_active === 1) {
      await archiveContentStrategyApi(record.id);
      message.success('策略已归档');
    } else {
      await unarchiveContentStrategyApi(record.id);
      message.success('策略已启用');
    }
    fetchStrategies();
  } catch (error) {
    console.error('操作失败:', error);
    message.error('操作失败');
  } finally {
    archiveLoading.value = false;
  }
};

// 执行测试
const handleRunTest = async () => {
  if (!testingStrategyId.value) return;

  testLoading.value = true;
  try {
    const res = await generateCombinationsApi(testingStrategyId.value, {
      count: testCount.value,
    });
    testResult.value = res;
  } catch (error) {
    logger.error('生成组合失败:', error);
    message.error('生成组合失败');
  } finally {
    testLoading.value = false;
  }
};

// 分页变化
const handleTableChange = (pag: { current?: number; pageSize?: number }) => {
  pagination.value.current = pag.current || 1;
  pagination.value.pageSize = pag.pageSize || 20;
  fetchStrategies();
};

// 从笛卡尔积生成 defined_combinations
const generateDefinedCombinationsFromCartesian = (skipConfirm = false) => {
  // 如果当前已有组合且不是跳过确认，则保存当前状态用于撤销
  if (
    form.value.defined_combinations &&
    form.value.defined_combinations.length > 0 &&
    !skipConfirm
  ) {
    // 保存当前状态（BUG-002：使用 structuredClone 避免响应式对象深拷贝问题）
    try {
      previousCombinations.value = structuredClone(
        toRaw(form.value.defined_combinations),
      );
      canUndo.value = true;
    } catch (error) {
      logger.warn('保存撤销状态失败:', error);
      canUndo.value = false;
    }
  }

  // 始终重新计算笛卡尔积组合（确保基于最新的 dimensions 配置）
  computeCartesianCombinations();

  // 将笛卡尔积组合转换为 defined_combinations 格式
  form.value.defined_combinations = cartesianCombinations.value.map(
    (combo, idx) => {
      const nodes: Record<string, string> = {};
      for (const [dimType, nodeInfo] of Object.entries(combo.nodes)) {
        nodes[dimType] = nodeInfo.id;
      }
      return {
        id: `combo_${idx}_${Date.now()}`,
        name: combo.name,
        nodes,
      };
    },
  );

  if (!skipConfirm && previousCombinations.value.length > 0) {
    message.success('已重新生成全部组合，如需恢复请点击「撤销」');
  }
};

// 撤销：恢复上一次的组合状态
const handleUndoRegenerate = () => {
  if (!canUndo.value || previousCombinations.value.length === 0) {
    message.warning('没有可撤销的操作');
    return;
  }

  // 深拷贝恢复（BUG-002：使用 structuredClone 避免响应式对象问题）
  try {
    form.value.defined_combinations = structuredClone(
      toRaw(previousCombinations.value),
    );
    canUndo.value = false;
    previousCombinations.value = [];
    message.success('已恢复到上一次的组合状态');
  } catch (error) {
    logger.error('恢复组合状态失败:', error);
    message.error('恢复失败，请重试');
  }
};

// 监听 dimensions 变化，实时更新笛卡尔积组合（内部用于生成）
watch(
  () => form.value.dimensions,
  () => {
    // 确保数组存在
    if (!Array.isArray(form.value.defined_combinations)) {
      form.value.defined_combinations = [];
    }
    // 仅更新内部的笛卡尔积计算，不自动替换用户已选组合
    computeCartesianCombinations();
  },
  { deep: true },
);

// 防抖搜索（名称）
let searchTimer: null | ReturnType<typeof setTimeout> = null;
watch(
  () => searchName.value,
  () => {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      pagination.value.current = 1;
      fetchStrategies();
    }, 300);
  },
);

// 监听状态和标签筛选变化
watch(
  () => [searchIsActive.value, searchTags.value],
  () => {
    pagination.value.current = 1;
    fetchStrategies();
  },
);

// 初始化
onMounted(async () => {
  // 初始加载数据
  fetchStrategies();
  fetchAvailableDimensions();
  fetchCategoryTree();
  fetchNodeFilterOptions();
});
</script>

<template>
  <div class="content-strategy-page">
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
          关键词策略管理
        </span>
        <span v-if="lastUpdateTime" class="text-xs text-muted-foreground">
          数据更新时间：{{ lastUpdateTime }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <Space size="middle">
          <Input
            v-model:value="searchName"
            placeholder="输入策略名称搜索"
            allow-clear
            style="width: 200px"
          />
          <Select
            v-model:value="searchTags"
            mode="multiple"
            placeholder="选择标签筛选"
            allow-clear
            show-search
            :filter-option="true"
            style="width: 200px"
            :options="nodeFilterTagOptions"
          />
          <Select
            v-model:value="searchIsActive"
            placeholder="选择状态"
            allow-clear
            show-search
            :filter-option="true"
            style="width: 120px"
            :options="[
              { label: '启用', value: 1 },
              { label: '归档', value: 0 },
            ]"
          />
          <Button
            class="action-btn"
            variant="ghost"
            size="small"
            @click="handleResetSearch"
          >
            <span class="btn-label">重置</span>
          </Button>
          <Button
            class="action-btn"
            variant="ghost"
            size="small"
            @click="fetchStrategies"
          >
            <ReloadOutlined class="btn-icon" />
            <span class="btn-label">刷新</span>
          </Button>
          <Button
            class="action-btn primary-action"
            size="small"
            @click="handleAdd"
          >
            <PlusOutlined class="btn-icon" />
            <span class="btn-label">新增策略</span>
          </Button>
        </Space>
      </div>
    </div>

    <Table
      :columns="columns"
      :data-source="strategies"
      :loading="loading"
      :pagination="{
        current: pagination.current,
        pageSize: pagination.pageSize,
        total: pagination.total,
        showSizeChanger: true,
        showTotal: (total: number) => `共 ${total} 条`,
      }"
      :scroll="{ x: 1000 }"
      row-key="id"
      @change="handleTableChange"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'tags'">
          <Space v-if="record.tags?.length" :size="4" wrap>
            <Tag
              v-for="tag in record.tags.slice(0, 3)"
              :key="tag"
              color="purple"
            >
              {{ tag }}
            </Tag>
            <Tooltip
              v-if="record.tags.length > 3"
              :title="record.tags.slice(3).join('、')"
            >
              <Tag>+{{ record.tags.length - 3 }}</Tag>
            </Tooltip>
          </Space>
          <span v-else class="text-muted">-</span>
        </template>
        <template v-else-if="column.key === 'dimensions'">
          <Tag color="blue">
            {{ Object.keys(record.node_pools || {}).length || 0 }} 个
          </Tag>
        </template>
        <template v-else-if="column.key === 'combinations_count'">
          <Tag color="green">
            {{ record.defined_combinations?.length || 0 }} 个
          </Tag>
        </template>
        <template v-else-if="column.key === 'is_active'">
          <Tag :color="record.is_active === 1 ? 'green' : 'default'">
            {{ record.is_active === 1 ? '启用' : '归档' }}
          </Tag>
        </template>
        <template v-else-if="column.key === 'actions'">
          <Space>
            <Tooltip title="编辑">
              <Button size="small" type="link" @click="handleEdit(record)">
                <template #icon><EditOutlined /></template>
              </Button>
            </Tooltip>
            <Tooltip title="复制策略">
              <Button
                size="small"
                type="link"
                :loading="copyLoading"
                @click="
                  handleCopy(record as ContentStrategyApi.ContentStrategy)
                "
              >
                <template #icon><CopyOutlined /></template>
              </Button>
            </Tooltip>
            <Tooltip :title="record.is_active === 1 ? '归档' : '取消归档'">
              <Button
                size="small"
                type="link"
                :loading="archiveLoading"
                @click="
                  handleArchive(record as ContentStrategyApi.ContentStrategy)
                "
              >
                <template #icon>
                  <FolderOutlined v-if="record.is_active === 1" />
                  <FolderOpenOutlined v-else />
                </template>
              </Button>
            </Tooltip>
            <Popconfirm
              title="确定要删除这个策略吗？"
              @confirm="handleDelete(String(record.id))"
              :get-popup-container="getPopupContainerBody"
            >
              <Button size="small" type="link" danger>
                <template #icon><DeleteOutlined /></template>
              </Button>
            </Popconfirm>
          </Space>
        </template>
      </template>
    </Table>

    <!-- 新增/编辑弹窗 -->
    <Modal
      v-model:open="modalVisible"
      :title="modalTitle"
      :confirm-loading="modalLoading"
      width="800px"
      ok-text="保存策略"
      cancel-text="取消"
      @ok="handleSave"
    >
      <Spin :spinning="formLoading" tip="加载中...">
        <Form layout="vertical">
          <Form.Item label="策略名称" required>
            <Input
              v-model:value="form.name"
              placeholder="请输入策略名称，如：秋冬换季种草策略"
            />
          </Form.Item>

          <Form.Item label="策略描述">
            <Input.TextArea
              v-model:value="form.description"
              placeholder="请输入策略描述"
              :rows="2"
            />
          </Form.Item>

          <Form.Item label="策略标签">
            <Select
              v-model:value="form.tags"
              mode="tags"
              placeholder="输入标签后回车添加，如：换季、双11、新品上市"
              show-search
              :filter-option="true"
              style="width: 100%"
              :token-separators="[',', '，', ' ']"
              :get-popup-container="(trigger) => trigger.parentElement"
            />
            <div class="form-hint">用于分类和快速筛选策略，可输入多个标签</div>
          </Form.Item>

          <Divider>关键词分类配置</Divider>

          <div
            v-for="(dim, index) in form.dimensions"
            :key="index"
            class="dimension-item"
          >
            <div class="dimension-header">
              <span class="dimension-index">分类 {{ index + 1 }}</span>
              <Button
                type="text"
                danger
                size="small"
                @click="handleRemoveDimension(index)"
              >
                <template #icon><DeleteOutlined /></template>
              </Button>
            </div>

            <div class="dimension-form">
              <div class="form-row">
                <Form.Item label="分类标签" class="form-item">
                  <Select
                    v-model:value="dim.dimension_type"
                    placeholder="选择分类标签（如：人设、场景、卖点）"
                    show-search
                    :filter-option="true"
                    style="width: 100%"
                    :get-popup-container="(trigger) => trigger.parentElement"
                    @change="
                      (v) => handleDimensionTypeChange(index, String(v ?? ''))
                    "
                  >
                    <Select.Option
                      v-for="d in availableDimensions"
                      :key="d.dimension_type"
                      :value="d.dimension_type"
                    >
                      {{ d.dimension_name }}
                    </Select.Option>
                  </Select>
                </Form.Item>

                <Form.Item class="form-item">
                  <template #label>
                    <Space :size="4">
                      <span>选择模式</span>
                      <Tooltip placement="top">
                        <template #title>
                          <div style="line-height: 1.6">
                            <p style="margin: 0 0 4px">
                              <strong>单选</strong
                              >：每个组合中该维度只取一个节点
                            </p>
                            <p style="margin: 0">
                              <strong>多选</strong
                              >：每个组合中该维度可取多个节点
                            </p>
                          </div>
                        </template>
                        <InfoCircleOutlined
                          style="
                            font-size: 14px;
                            color: hsl(var(--muted-foreground));
                            cursor: help;
                          "
                        />
                      </Tooltip>
                    </Space>
                  </template>
                  <Radio.Group
                    v-model:value="dim.select_mode"
                    @change="
                      (value: any) =>
                        handleSelectModeChange(index, value as string)
                    "
                  >
                    <Radio value="single">单选</Radio>
                    <Radio value="multiple">多选</Radio>
                  </Radio.Group>
                </Form.Item>

                <Form.Item label="必选" class="form-item-small">
                  <Switch v-model:checked="dim.required" />
                </Form.Item>
              </div>

              <div class="form-row">
                <Form.Item label="选择策略" class="form-item">
                  <Select
                    v-model:value="dim.select_strategy"
                    :options="selectStrategyOptions"
                    show-search
                    :filter-option="true"
                    style="width: 100%"
                  >
                    <template #suffixIcon>
                      <Tooltip title="选择节点的策略方式">
                        <InfoCircleOutlined style="color: rgb(0 0 0 / 45%)" />
                      </Tooltip>
                    </template>
                  </Select>
                  <div class="field-hint">
                    <span v-if="dim.select_strategy === 'all'">
                      从已选节点中选择全部节点参与组合
                    </span>
                    <span v-else-if="dim.select_strategy === 'random'">
                      从已选节点中随机抽取指定数量的节点参与组合
                    </span>
                    <span v-else-if="dim.select_strategy === 'weighted'">
                      按照节点权重进行选择，权重高的节点更容易被选中
                    </span>
                  </div>
                </Form.Item>

                <Form.Item
                  v-if="dim.select_strategy === 'random'"
                  label="选择数量"
                  class="form-item-small"
                >
                  <InputNumber
                    v-model:value="dim.select_count"
                    :min="1"
                    :max="100"
                  />
                </Form.Item>
              </div>

              <!-- 权重配置区域 -->
              <div
                v-if="
                  dim.select_strategy === 'weighted' &&
                  dim.node_ids &&
                  dim.node_ids.length > 0
                "
                class="weight-config-section"
              >
                <div class="weight-config-title">
                  节点权重配置
                  <Tooltip title="权重越高，该节点在组合生成时被选中的概率越大">
                    <InfoCircleOutlined
                      style="margin-left: 4px; color: rgb(0 0 0 / 45%)"
                    />
                  </Tooltip>
                </div>
                <div class="weight-config-list">
                  <div
                    v-for="nodeId in dim.node_ids"
                    :key="nodeId"
                    class="weight-config-item"
                  >
                    <span class="node-label">{{
                      getNodeLabel(dim.dimension_type, nodeId)
                    }}</span>
                    <div class="weight-input-wrapper">
                      <span class="weight-label">权重:</span>
                      <InputNumber
                        :value="getNodeWeight(dim, nodeId)"
                        :min="1"
                        :max="100"
                        :default-value="1"
                        size="small"
                        style="width: 80px"
                        @change="(v) => setNodeWeight(dim, nodeId, Number(v))"
                      />
                    </div>
                  </div>
                </div>
              </div>

              <!-- 节点筛选器（按维度） -->
              <div v-if="dim.dimension_type" class="node-filter-section">
                <div class="node-filter-row">
                  <Form.Item label="按品牌筛选" class="filter-item">
                    <Select
                      :value="getDimensionFilter(index).brands"
                      mode="multiple"
                      :options="nodeFilterBrandOptions"
                      placeholder="筛选品牌"
                      allow-clear
                      show-search
                      :filter-option="true"
                      style="width: 160px"
                      size="small"
                      @change="
                        (v) =>
                          setDimensionFilter(
                            index,
                            'brands',
                            (v as string[]) || [],
                          )
                      "
                    />
                  </Form.Item>
                  <Form.Item label="按标签筛选" class="filter-item">
                    <Select
                      :value="getDimensionFilter(index).tags"
                      mode="multiple"
                      :options="nodeFilterTagOptions"
                      placeholder="筛选标签"
                      allow-clear
                      show-search
                      :filter-option="true"
                      style="width: 160px"
                      size="small"
                      @change="
                        (v) =>
                          setDimensionFilter(
                            index,
                            'tags',
                            (v as string[]) || [],
                          )
                      "
                    />
                  </Form.Item>
                  <div
                    v-if="
                      getDimensionFilter(index).brands.length > 0 ||
                      getDimensionFilter(index).tags.length > 0
                    "
                    class="filter-hint"
                  >
                    <Tag color="blue" size="small"> 筛选中 </Tag>
                  </div>
                </div>
              </div>

              <Form.Item label="选择关键词">
                <Spin :spinning="categoryTreeLoading">
                  <TreeSelect
                    v-model:value="dim.node_ids"
                    :tree-data="getDimensionNodeTree(dim.dimension_type, index)"
                    placeholder="选择要包含的关键词"
                    multiple
                    tree-checkable
                    show-search
                    tree-node-filter-prop="title"
                    tree-node-label-prop="title"
                    :dropdown-style="{ maxHeight: '300px', overflow: 'auto' }"
                    style="width: 100%"
                    :get-popup-container="(trigger) => trigger.parentElement"
                    :tag-render="
                      (tag) => renderNodeTag(dim.dimension_type, tag)
                    "
                  >
                    <template #title="{ title, corpus }">
                      <span class="tree-node-title">
                        {{ title }}
                        <Tooltip
                          v-if="corpus && corpus.length > 0"
                          :title="formatCorpusContent(corpus)"
                        >
                          <QuestionCircleOutlined class="corpus-help-icon" />
                        </Tooltip>
                      </span>
                    </template>
                  </TreeSelect>
                </Spin>
              </Form.Item>
            </div>
          </div>

          <Button type="dashed" block @click="handleAddDimension">
            <template #icon><PlusOutlined /></template>
            添加分类
          </Button>

          <Divider>组合规则</Divider>

          <!-- 组合管理（统一界面） -->
          <div class="combos-section">
            <div class="section-header">
              <span
                >已选组合 ({{
                  form.defined_combinations?.length || 0
                }}
                个)</span
              >
              <span class="max-combinations-hint">
                最大限制：{{ form.max_combinations }} 个
              </span>
              <Space>
                <!-- 撤销按钮 -->
                <Tooltip v-if="canUndo" title="恢复上一次的组合状态">
                  <Button
                    size="small"
                    type="default"
                    @click="handleUndoRegenerate"
                  >
                    <template #icon><UndoOutlined /></template>
                    撤销
                  </Button>
                </Tooltip>
                <!-- 重新生成按钮（带确认） -->
                <Popconfirm
                  title="确定要重新生成全部组合吗？"
                  description="当前的删减操作将被覆盖，但可以通过「撤销」恢复"
                  ok-text="确定"
                  cancel-text="取消"
                  @confirm="
                    () => generateDefinedCombinationsFromCartesian(false)
                  "
                >
                  <Button size="small">
                    <template #icon><ReloadOutlined /></template>
                    重新生成全部
                  </Button>
                </Popconfirm>
                <Button type="primary" size="small" @click="handleAddCombo">
                  <template #icon><PlusOutlined /></template>
                  添加组合
                </Button>
              </Space>
            </div>

            <div
              v-if="
                !form.defined_combinations ||
                form.defined_combinations.length === 0
              "
              class="empty-hint"
            >
              <p>暂无组合，请先配置维度并选择节点</p>
              <Button
                type="primary"
                :disabled="!hasDimensionsConfigured"
                @click="() => generateDefinedCombinationsFromCartesian(true)"
              >
                生成全部组合
              </Button>
            </div>

            <div v-else class="combo-list">
              <div
                v-for="(combo, idx) in form.defined_combinations"
                :key="combo.id"
                class="combo-item"
              >
                <div class="combo-index">#{{ idx + 1 }}</div>
                <div class="combo-name">{{ combo.name }}</div>
                <div class="combo-nodes">
                  <Tag
                    v-for="(nodeId, dimType) in combo.nodes"
                    :key="dimType"
                    color="blue"
                  >
                    {{ dimType }}: {{ getComboNodeName(nodeId) }}
                  </Tag>
                </div>
                <div class="combo-actions">
                  <Tooltip title="编辑此组合">
                    <Button
                      size="small"
                      type="link"
                      @click="handleEditCombo(idx)"
                    >
                      <EditOutlined />
                    </Button>
                  </Tooltip>
                  <Tooltip title="删除此组合">
                    <Button
                      size="small"
                      type="link"
                      danger
                      @click="handleRemoveCombo(idx)"
                    >
                      <DeleteOutlined />
                    </Button>
                  </Tooltip>
                </div>
              </div>
            </div>

            <!-- 组合状态提示 -->
            <div class="combo-status-bar">
              <div class="combo-status-info">
                <span class="combo-count">
                  ✓ 已配置
                  <strong>{{ form.defined_combinations?.length || 0 }}</strong>
                  个组合
                </span>
                <span
                  v-if="form.defined_combinations?.length"
                  class="combo-hint"
                >
                  点击弹窗底部「确定」按钮保存策略
                </span>
              </div>
            </div>
          </div>

          <div class="form-row" style="margin-top: 16px">
            <Form.Item label="包含语料" class="form-item-small">
              <Switch v-model:checked="form.settings.include_corpus" />
            </Form.Item>
          </div>
        </Form>
      </Spin>
    </Modal>

    <!-- 组合编辑弹窗 -->
    <Modal
      v-model:open="comboModalVisible"
      :title="comboModalTitle"
      width="600px"
      @ok="handleSaveCombo"
    >
      <Form layout="vertical">
        <Form.Item label="组合名称（可选，留空自动生成）">
          <Input
            v-model:value="comboForm.name"
            placeholder="如：创业妈妈 + 换季场景"
          />
        </Form.Item>

        <Divider>选择各维度节点</Divider>

        <Form.Item
          v-for="dim in form.dimensions"
          :key="dim.dimension_type"
          :label="dim.dimension_name || dim.dimension_type"
        >
          <TreeSelect
            v-model:value="comboForm.nodes[dim.dimension_type]"
            :tree-data="getSelectedNodesTree(dim)"
            placeholder="从已选节点中选择一个"
            show-search
            tree-node-filter-prop="title"
            :dropdown-style="{ maxHeight: '300px', overflow: 'auto' }"
            style="width: 100%"
            :disabled="!dim.node_ids || dim.node_ids.length === 0"
            :get-popup-container="(trigger) => trigger.parentElement"
          >
            <template #title="{ title, corpus }">
              <span class="tree-node-title">
                {{ title }}
                <Tooltip
                  v-if="corpus && corpus.length > 0"
                  :title="formatCorpusContent(corpus)"
                >
                  <QuestionCircleOutlined class="corpus-help-icon" />
                </Tooltip>
              </span>
            </template>
          </TreeSelect>
          <div
            v-if="!dim.node_ids || dim.node_ids.length === 0"
            class="field-hint"
          >
            请先在上方维度配置中选择节点
          </div>
        </Form.Item>
      </Form>
    </Modal>

    <!-- 测试弹窗 -->
    <Modal
      v-model:open="testModalVisible"
      title="测试生成组合"
      width="800px"
      :footer="null"
    >
      <div class="test-controls">
        <Space>
          <span>生成数量：</span>
          <InputNumber v-model:value="testCount" :min="1" :max="100" />
          <Button type="primary" :loading="testLoading" @click="handleRunTest">
            生成
          </Button>
        </Space>
      </div>

      <div v-if="testResult" class="test-result">
        <div class="result-header">
          共生成 {{ testResult.total_count }} 个组合
        </div>
        <div class="combinations-list">
          <div
            v-for="(combo, idx) in testResult.combinations"
            :key="idx"
            class="combination-item"
          >
            <div class="combo-index">#{{ idx + 1 }}</div>
            <div class="combo-nodes">
              <div
                v-for="(node, dimType) in combo.nodes"
                :key="dimType"
                class="combo-node"
              >
                <Tag color="blue">{{ dimType }}</Tag>
                <span class="node-name">{{ node.name }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.content-strategy-page {
  padding: 16px;
}

/* 搜索表单样式 */
.search-form {
  margin-bottom: 16px;
}

/* 节点筛选器样式 */
.node-filter-section {
  padding: 12px 16px;
  margin-bottom: 16px;
  background: hsl(var(--muted) / 20%);
  border: 1px dashed hsl(var(--border));
  border-radius: 8px;
}

.node-filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
}

.filter-item {
  margin-bottom: 0;
}

.filter-hint {
  display: flex;
  align-items: center;
}

.dimension-item {
  padding: 16px;
  margin-bottom: 16px;
  background: hsl(var(--muted) / 30%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.dimension-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.dimension-index {
  font-weight: 600;
  color: hsl(var(--primary));
}

.dimension-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-row {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.form-item {
  flex: 1;
}

.form-item-small {
  width: 120px;
}

.test-controls {
  margin-bottom: 16px;
}

.test-result {
  max-height: 500px;
  overflow-y: auto;
}

.result-header {
  margin-bottom: 12px;
  font-weight: 600;
}

.combinations-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.combination-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  background: hsl(var(--muted) / 20%);
  border-radius: 6px;
}

.combo-index {
  width: 40px;
  font-weight: 600;
  color: hsl(var(--muted-foreground));
}

.combo-nodes {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  gap: 8px;
}

.combo-node {
  display: flex;
  gap: 4px;
  align-items: center;
}

.node-name {
  color: hsl(var(--foreground));
}

.field-hint {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.4;
  color: hsl(var(--muted-foreground));
}

.weight-config-section {
  padding: 12px;
  margin-top: 12px;
  background: hsl(var(--muted) / 20%);
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
}

.weight-config-title {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.weight-config-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.weight-config-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px;
  background: hsl(var(--background));
  border: 1px solid hsl(var(--border));
  border-radius: 4px;
}

.node-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.weight-input-wrapper {
  display: flex;
  gap: 8px;
  align-items: center;
}

.weight-label {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

/* 组合管理区域样式 */
.combos-section {
  padding: 16px;
  margin-bottom: 16px;
  background: hsl(var(--muted) / 20%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-weight: 600;
}

.empty-hint {
  padding: 24px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.max-combinations-hint {
  padding: 2px 8px;
  margin-left: 8px;
  font-size: 12px;
  font-weight: normal;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted) / 30%);
  border-radius: 4px;
}

.combo-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.combo-item {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 10px 12px;
  background: hsl(var(--background));
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
}

.combo-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
  white-space: nowrap;
}

.combo-actions {
  display: flex;
  gap: 4px;
}

/* 组合状态提示条样式 */
.combo-status-bar {
  padding: 12px 16px;
  margin-top: 16px;
  background: hsl(var(--success) / 8%);
  border: 1px solid hsl(var(--success) / 30%);
  border-radius: 6px;
}

.combo-status-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.combo-count {
  font-size: 14px;
  color: hsl(var(--success));
}

.combo-count strong {
  margin: 0 2px;
  font-size: 16px;
}

.combo-hint {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

/* Scope 上下文配置区域样式 */
.scope-context-section {
  padding: 16px;
  margin-bottom: 16px;
  background: hsl(var(--accent) / 8%);
  border: 1px solid hsl(var(--accent) / 30%);
  border-radius: 8px;
}

.scope-context-section .form-row {
  margin-bottom: 8px;
}

.scope-context-section .form-row:last-child {
  margin-bottom: 0;
}

/* 表单提示文字 */
.form-hint {
  margin-top: 4px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

/* 表格中的无数据文字 */
.text-muted {
  color: hsl(var(--muted-foreground));
}

/* 品牌下无关键词警告样式 */
.no-keywords-warning {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  margin-top: 12px;
  background: hsl(var(--warning) / 10%);
  border: 1px solid hsl(var(--warning) / 40%);
  border-radius: 8px;
}

.warning-icon {
  flex-shrink: 0;
  font-size: 20px;
}

.warning-content {
  flex: 1;
}

.warning-title {
  margin-bottom: 4px;
  font-weight: 600;
  color: hsl(var(--warning));
}

.warning-desc {
  font-size: 13px;
  line-height: 1.5;
  color: hsl(var(--foreground) / 80%);
}

/* TreeSelect 节点语料问号图标 */
.tree-node-title {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}

.corpus-help-icon {
  font-size: 12px;
  color: hsl(var(--primary) / 60%);
  cursor: help;
  transition: color 0.2s;
}

.corpus-help-icon:hover {
  color: hsl(var(--primary));
}
</style>
