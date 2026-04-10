<script setup lang="ts">
import type { NodeLabel, RelationType } from '../types';

import type { GraphCorpusApi } from '#/api/core/graph-corpus';

import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';

import { usePreferences } from '@vben/preferences';

import {
  AimOutlined,
  BranchesOutlined,
  CloseCircleOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  NodeIndexOutlined,
  ReloadOutlined,
  SearchOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
} from '@ant-design/icons-vue';
import {
  Badge,
  Button,
  Descriptions,
  DescriptionsItem,
  Divider,
  Drawer,
  Input,
  message,
  Tag,
  Tooltip,
} from 'ant-design-vue';
import { DataSet, Network } from 'vis-network/standalone';

import {
  getCategoryTreeApi,
  getNodeNeighborsApi,
  listNodesApi,
} from '#/api/core/graph-corpus';

import { NODE_LABEL_CONFIG, RELATION_TYPE_CONFIG } from '../types';
import {
  getEdgeColor,
  getNodeColor,
  getNodeDisplayName,
  getNodeIcon,
  getNodeSize,
  getRelationDisplayName,
  VIS_NETWORK_TREE_OPTIONS,
} from '../vis-network-config';

// =============================================
// 类型定义
// =============================================
interface VisNode {
  id: string;
  label: string;
  group: string;
  title?: string;
  color?: {
    background: string;
    border: string;
    highlight?: { background: string; border: string };
  };
  borderWidth?: number;
  font?: { color: string; size?: number };
  size?: number;
  hidden?: boolean;
  opacity?: number;
  data: GraphCorpusApi.NodeItem;
}

interface VisEdge {
  id: string;
  from: string;
  to: string;
  label?: string;
  title?: string;
  color?: { color: string; highlight?: string };
  arrows?: string;
  hidden?: boolean;
  data: GraphCorpusApi.EdgeItem;
}

// =============================================
// 状态定义
// =============================================
const containerRef = ref<HTMLDivElement | null>(null);
const networkInstance = ref<Network | null>(null);
const nodesDataSet = ref<DataSet<VisNode> | null>(null);
const edgesDataSet = ref<DataSet<VisEdge> | null>(null);

// 组件挂载状态标志（用于防止卸载后的回调更新状态）
let isMounted = false;

// 获取系统主题
const { isDark } = usePreferences();

const isFullscreen = ref(false);
const isDarkMode = computed(() => isDark.value);
const loading = ref(false);
const searchKeyword = ref('');

// 数据状态
const allNodes = ref<VisNode[]>([]);
const allEdges = ref<VisEdge[]>([]);

// 高亮模式
type HighlightMode =
  | 'nodeType'
  | 'none'
  | 'relationType'
  | 'search'
  | 'singleNode';
const highlightMode = ref<HighlightMode>('none');
const highlightedNodeType = ref<NodeLabel | null>(null);
const highlightedRelationType = ref<null | RelationType>(null);
const highlightedSingleNodeId = ref<null | string>(null);

// 节点详情抽屉（边及其关联节点信息，与 3D 图保持一致）
interface EdgeWithNode {
  edge: VisEdge;
  node: null | VisNode; // 关联的节点（出边：目标节点，入边：源节点）
}

const drawerVisible = ref(false);
const selectedNode = ref<null | VisNode>(null);
const selectedNodeEdges = ref<{
  incoming: EdgeWithNode[];
  outgoing: EdgeWithNode[];
}>({
  incoming: [],
  outgoing: [],
});

// 筛选器状态
const activeFilters = ref<Set<string>>(new Set());

// =============================================
// 聚焦模式（只显示某节点及其直接相连的节点）
// 搜索聚焦模式优先级最高，完全无视筛选条件
// =============================================
const focusMode = ref(false); // 是否处于聚焦模式
const focusLoading = ref(false); // 聚焦模式加载中
const focusNodeId = ref<null | string>(null); // 聚焦的中心节点 ID
const focusNodeIds = ref<Set<string>>(new Set()); // 聚焦模式下显示的节点 ID 集合

// 保存聚焦前的原始数据，用于退出时恢复
let originalNodes: VisNode[] = [];
let originalEdges: VisEdge[] = [];

// 进入聚焦模式（最高优先级，无视所有筛选条件，通过高效 API 一次性获取）
async function enterFocusMode(centerNodeId: string) {
  if (focusLoading.value) return;

  focusLoading.value = true;

  try {
    // 【高效】一次 API 调用获取：中心节点 + 所有邻居 + 所有边
    const res = await getNodeNeighborsApi(centerNodeId);

    const centerNodeData = res.center_node;
    const neighborNodes = res.neighbors;
    const allRelatedEdges = res.edges;

    // 保存原始数据（退出时恢复）
    if (!focusMode.value) {
      originalNodes = [...allNodes.value];
      originalEdges = [...allEdges.value];
    }

    // 构建聚焦模式的节点和边数据
    const focusNodes: VisNode[] = [transformApiNodeToVis(centerNodeData)];
    for (const node of neighborNodes) {
      focusNodes.push(transformApiNodeToVis(node));
    }

    const focusEdges: VisEdge[] = allRelatedEdges.map((edge) =>
      transformApiEdgeToVis(edge),
    );

    // 收集所有节点 ID
    const neighborIds = new Set(neighborNodes.map((n) => n.id));

    // 设置聚焦模式状态
    focusMode.value = true;
    focusNodeId.value = centerNodeId;
    focusNodeIds.value = new Set([centerNodeId, ...neighborIds]);

    // 替换图数据
    allNodes.value = focusNodes;
    allEdges.value = focusEdges;

    // 重建 DataSet
    if (nodesDataSet.value && edgesDataSet.value && networkInstance.value) {
      nodesDataSet.value.clear();
      edgesDataSet.value.clear();

      // 为中心节点添加特殊样式
      const styledNodes = focusNodes.map((node) => ({
        ...node,
        hidden: false,
        borderWidth: node.id === centerNodeId ? 4 : 2,
        color:
          node.id === centerNodeId
            ? {
                background: node.color?.background || '#1890ff',
                border: '#ffffff',
                highlight: {
                  background: node.color?.background || '#1890ff',
                  border: '#ffffff',
                },
              }
            : node.color,
      }));

      nodesDataSet.value.add(styledNodes);
      edgesDataSet.value.add(focusEdges.map((e) => ({ ...e, hidden: false })));
    }

    // 更新筛选器以包含所有类型
    const allLabels = new Set(focusNodes.map((n) => n.group));
    for (const label of allLabels) {
      activeFilters.value.add(label);
    }

    // 清空搜索
    searchKeyword.value = '';
    searchResults.value = [];

    // 适应视图
    await nextTick();
    networkInstance.value?.fit({
      animation: { duration: 800, easingFunction: 'easeInOutQuad' },
    });

    message.success(
      `已聚焦到「${centerNodeData.name}」，显示 ${neighborIds.size} 个关联关键词`,
    );
  } catch (error) {
    console.error('[VisNetwork] 进入聚焦模式失败:', error);
    message.error('进入聚焦模式失败，请重试');
  } finally {
    focusLoading.value = false;
  }
}

// 退出聚焦模式，恢复全图
async function exitFocusMode() {
  if (!focusMode.value) return;

  focusMode.value = false;
  focusNodeId.value = null;
  focusNodeIds.value = new Set();

  // 恢复原始数据
  if (originalNodes.length > 0) {
    allNodes.value = originalNodes;
    allEdges.value = originalEdges;

    // 重建 DataSet
    if (nodesDataSet.value && edgesDataSet.value) {
      nodesDataSet.value.clear();
      edgesDataSet.value.clear();

      // 根据筛选器设置可见性
      const visibleLabels = activeFilters.value;
      const nodesToAdd = allNodes.value.map((node) => ({
        ...node,
        hidden: !visibleLabels.has(node.group),
        borderWidth: 2,
      }));
      nodesDataSet.value.add(nodesToAdd);

      const visibleNodeIds = new Set(
        nodesToAdd.filter((n) => !n.hidden).map((n) => n.id),
      );
      const edgesToAdd = allEdges.value.map((edge) => ({
        ...edge,
        hidden: !(visibleNodeIds.has(edge.from) && visibleNodeIds.has(edge.to)),
      }));
      edgesDataSet.value.add(edgesToAdd);
    }

    originalNodes = [];
    originalEdges = [];
  }

  // 清除高亮
  clearHighlight();

  // 适应视图
  await nextTick();
  networkInstance.value?.fit({ animation: true });

  message.info('已恢复全图显示');
}

// 更新聚焦模式下的图显示（不再使用 hidden 方式，因为数据已替换）
function updateFocusGraph() {
  // 聚焦模式下数据已替换，只需确保样式正确
  if (!nodesDataSet.value || !edgesDataSet.value || !focusMode.value) return;

  // 为中心节点添加特殊样式
  const nodeUpdates = allNodes.value.map((node) => ({
    id: node.id,
    hidden: false,
    borderWidth: node.id === focusNodeId.value ? 4 : 2,
    color:
      node.id === focusNodeId.value
        ? {
            background: node.color?.background || '#1890ff',
            border: '#ffffff',
            highlight: {
              background: node.color?.background || '#1890ff',
              border: '#ffffff',
            },
          }
        : node.color,
  }));
  nodesDataSet.value.update(nodeUpdates);

  // 边全部可见
  const edgeUpdates = allEdges.value.map((edge) => ({
    id: edge.id,
    hidden: false,
  }));
  edgesDataSet.value.update(edgeUpdates);

  // 适应视图
  nextTick(() => {
    networkInstance.value?.fit({
      animation: { duration: 800, easingFunction: 'easeInOutQuad' },
    });
  });
}

// =============================================
// 计算属性（动态检测后端返回的新类型，与 3D 图保持一致）
// =============================================

// 节点类型统计：从实际数据中动态获取，而不是依赖硬编码配置
const nodeTypeStats = computed(() => {
  const stats: Record<
    string,
    { active: boolean; color: string; count: number; displayName: string }
  > = {};

  // 从实际数据中收集所有 label
  for (const node of allNodes.value) {
    const label = node.group;
    if (!stats[label]) {
      // 使用共享的颜色函数，确保与 3D 图颜色一致
      stats[label] = {
        count: 0,
        active: highlightedNodeType.value === label,
        color: getNodeColor(label),
        displayName: getNodeDisplayName(label),
      };
    }
    stats[label]!.count++;
  }

  // 按数量降序排序
  return Object.fromEntries(
    Object.entries(stats).toSorted((a, b) => b[1].count - a[1].count),
  );
});

// 关系类型统计：从实际数据中动态获取
const relationTypeStats = computed(() => {
  const stats: Record<
    string,
    { active: boolean; color: string; count: number; displayName: string }
  > = {};

  // 从实际数据中收集所有 relationType
  for (const edge of allEdges.value) {
    const type = edge.data.relation_type;
    if (!stats[type]) {
      // 使用共享的颜色函数，确保与 3D 图颜色一致
      stats[type] = {
        count: 0,
        active: highlightedRelationType.value === type,
        color: getEdgeColor(type),
        displayName: getRelationDisplayName(type),
      };
    }
    stats[type]!.count++;
  }

  // 按数量降序排序
  return Object.fromEntries(
    Object.entries(stats).toSorted((a, b) => b[1].count - a[1].count),
  );
});

// 搜索结果（后端 API 搜索 + 本地已加载节点搜索）
const searchResults = ref<GraphCorpusApi.NodeItem[]>([]);
const searchLoading = ref(false);
let searchTimer: null | ReturnType<typeof setTimeout> = null;

// 本地搜索（已加载的节点）
const localSearchResults = computed(() => {
  if (!searchKeyword.value.trim()) return [];
  const keyword = searchKeyword.value.toLowerCase();
  return allNodes.value
    .filter(
      (n) =>
        n.label.toLowerCase().includes(keyword) ||
        n.id.toLowerCase().includes(keyword) ||
        n.data.name.toLowerCase().includes(keyword),
    )
    .slice(0, 5);
});

// 后端 API 搜索（防抖）
async function searchNodesFromApi(keyword: string) {
  if (!keyword.trim()) {
    searchResults.value = [];
    return;
  }

  searchLoading.value = true;
  try {
    const res = await listNodesApi({
      keyword,
      page: 1,
      page_size: 10,
      tenant_code: 'default',
    });
    searchResults.value = res.items;
  } catch (error) {
    console.error('搜索关键词失败:', error);
    searchResults.value = [];
  } finally {
    searchLoading.value = false;
  }
}

// 监听搜索关键词变化，使用防抖
watch(searchKeyword, (val) => {
  if (searchTimer) clearTimeout(searchTimer);

  if (!val.trim()) {
    searchResults.value = [];
    if (highlightMode.value === 'search') {
      highlightMode.value = 'none';
    }
    updateGraph();
    return;
  }

  // 立即更新高亮模式
  highlightMode.value = 'search';
  highlightedNodeType.value = null;
  highlightedRelationType.value = null;
  updateGraph();

  // 防抖调用 API
  searchTimer = setTimeout(() => {
    searchNodesFromApi(val);
  }, 300);
});

// =============================================
// 数据转换（使用与 3D 图一致的颜色算法）
// =============================================
function transformApiNodeToVis(apiNode: GraphCorpusApi.NodeItem): VisNode {
  const label = apiNode.label as NodeLabel;
  // 使用共享的颜色函数，确保与 3D 图颜色一致
  const color = getNodeColor(label);
  const size = getNodeSize(label);

  // 不设置 title，禁用 tooltip，改用 Drawer 显示详情
  return {
    id: apiNode.id,
    label:
      apiNode.name.length > 10
        ? `${apiNode.name.slice(0, 10)}...`
        : apiNode.name,
    group: apiNode.label,
    // title 已移除 - 点击节点打开 Drawer 而不是显示 tooltip
    color: {
      background: color,
      border: color,
      highlight: {
        background: color,
        border: isDarkMode.value ? '#ffffff' : '#1f1f1f',
      },
    },
    borderWidth: 2,
    font: { color: isDarkMode.value ? '#ffffff' : '#1f1f1f' },
    size,
    data: apiNode,
  };
}

function transformApiEdgeToVis(apiEdge: GraphCorpusApi.EdgeItem): VisEdge {
  const relationType = apiEdge.relation_type as RelationType;
  // 使用共享的颜色函数，确保与 3D 图颜色一致
  const color = getEdgeColor(relationType);

  // 不设置 title，禁用 tooltip
  return {
    id: apiEdge.id,
    from: apiEdge.source_node_id,
    to: apiEdge.target_node_id,
    label: '', // 边标签隐藏以提升性能
    // title 已移除 - 不显示边的 tooltip
    color: {
      color,
      highlight: '#ffffff',
    },
    arrows: 'to',
    data: apiEdge,
  };
}

// =============================================
// 数据加载（树形结构）
// =============================================

// 虚拟根节点 ID
const VIRTUAL_ROOT_ID = 'virtual-root';

/**
 * 将树形节点转换为 vis-network 节点格式
 */
function transformTreeNodeToVis(
  treeNode: GraphCorpusApi.TreeNodeItem,
): VisNode {
  const label = treeNode.label;
  const color = treeNode.color || getNodeColor(label);
  const size = getNodeSize(label);

  return {
    id: treeNode.id,
    label:
      treeNode.name.length > 12
        ? `${treeNode.name.slice(0, 12)}...`
        : treeNode.name,
    group: label,
    color: {
      background: color,
      border: color,
      highlight: {
        background: color,
        border: isDarkMode.value ? '#ffffff' : '#1f1f1f',
      },
    },
    borderWidth: 2,
    font: { color: isDarkMode.value ? '#ffffff' : '#1f1f1f' },
    size,
    data: {
      id: treeNode.id,
      tenant_code: '',
      label: treeNode.label,
      name: treeNode.name,
      description: treeNode.description,
      is_active: treeNode.is_active,
      is_deleted: 0,
      properties: {
        category_type: treeNode.category_type,
        level: treeNode.level,
        sort_order: treeNode.sort_order,
        icon: treeNode.icon,
        color: treeNode.color,
      },
    } as GraphCorpusApi.NodeItem,
  };
}

/**
 * 将树形数据递归转换为 vis-network 的节点和边
 */
function transformTreeToVisData(treeData: GraphCorpusApi.TreeNodeItem[]): {
  edges: VisEdge[];
  nodes: VisNode[];
} {
  const nodes: VisNode[] = [];
  const edges: VisEdge[] = [];

  // 1. 添加虚拟根节点
  const virtualRoot: VisNode = {
    id: VIRTUAL_ROOT_ID,
    label: '关键词库',
    group: 'ROOT',
    color: {
      background: '#666666',
      border: '#999999',
      highlight: {
        background: '#888888',
        border: '#ffffff',
      },
    },
    borderWidth: 3,
    font: { color: isDarkMode.value ? '#ffffff' : '#1f1f1f', size: 14 },
    size: 35,
    data: {
      id: VIRTUAL_ROOT_ID,
      tenant_code: '',
      label: 'ROOT',
      name: '关键词库',
      description: '虚拟根节点',
      is_active: 1,
      is_deleted: 0,
    } as GraphCorpusApi.NodeItem,
  };
  nodes.push(virtualRoot);

  // 2. 递归遍历树，构建节点和边
  let edgeIdCounter = 0;
  function traverse(node: GraphCorpusApi.TreeNodeItem, parentId: string): void {
    const visNode = transformTreeNodeToVis(node);
    nodes.push(visNode);

    // 添加父子边
    edges.push({
      id: `edge-${edgeIdCounter++}`,
      from: parentId,
      to: node.id,
      color: {
        color: '#8c8c8c',
        highlight: '#ffffff',
      },
      arrows: 'to',
      data: {
        id: `edge-${edgeIdCounter}`,
        tenant_code: '',
        source_node_id: parentId,
        target_node_id: node.id,
        relation_type: 'INCLUDES',
        is_active: 1,
        is_deleted: 0,
      } as GraphCorpusApi.EdgeItem,
    });

    // 递归处理子节点
    for (const child of node.children || []) {
      traverse(child, node.id);
    }
  }

  // 3. 顶层节点挂到虚拟根节点下
  for (const root of treeData) {
    traverse(root, VIRTUAL_ROOT_ID);
  }

  return { nodes, edges };
}

async function fetchGraphData() {
  loading.value = true;
  try {
    // 从后端获取树形数据
    const treeData = await getCategoryTreeApi({
      tenant_code: 'default',
    });

    // 转换树形数据为 vis-network 格式
    const { nodes, edges } = transformTreeToVisData(treeData);

    allNodes.value = nodes;
    allEdges.value = edges;

    // 初始化筛选器（全选，使用动态检测的类型）
    const uniqueLabels = new Set(allNodes.value.map((n) => n.group));
    activeFilters.value = uniqueLabels;
  } catch (error) {
    console.error(error);
    message.error('加载树形数据失败');
  } finally {
    loading.value = false;
  }
}

// =============================================
// 图谱操作（树形布局）
// =============================================

async function initGraph() {
  if (!containerRef.value || !isMounted) {
    console.warn('Graph container not ready or component unmounted');
    return;
  }

  await fetchGraphData();

  // 再次检查组件是否仍然挂载
  if (!containerRef.value || !isMounted) {
    console.warn('Graph container destroyed during data fetch');
    return;
  }

  try {
    // 创建 DataSet
    nodesDataSet.value = new DataSet<VisNode>(allNodes.value);
    edgesDataSet.value = new DataSet<VisEdge>(allEdges.value);

    const data = {
      nodes: nodesDataSet.value,
      edges: edgesDataSet.value,
    };

    // 使用树形布局配置
    const options = {
      ...VIS_NETWORK_TREE_OPTIONS,
    };

    // 创建网络
    networkInstance.value = new Network(containerRef.value, data, options);

    // 绑定事件
    networkInstance.value.on('click', onNetworkClick);
    networkInstance.value.on('doubleClick', onNetworkDoubleClick);

    // 树形布局完成后自动适应视图
    await nextTick();
    networkInstance.value.fit({
      animation: { duration: 500, easingFunction: 'easeInOutQuad' },
    });
  } catch (error) {
    console.error('Graph initialization error:', error);
    message.error('树形图渲染失败');
  }
}

function updateGraph() {
  // 检查组件是否仍然挂载，以及数据集是否存在
  if (!isMounted || !nodesDataSet.value || !edgesDataSet.value) return;

  // 【关键】聚焦模式下使用专门的更新逻辑
  if (focusMode.value) {
    updateFocusGraph();
    return;
  }

  const visibleNodeIds = new Set<string>();

  // 【优化】使用批量更新，避免多次触发 vis-network 重绘
  const nodeUpdates: Array<{
    borderWidth: number;
    color: any;
    hidden: boolean;
    id: string;
  }> = [];

  // 收集节点更新
  for (const node of allNodes.value) {
    const visible = activeFilters.value.has(node.group);
    const isHighlighted = getNodeHighlightState(node);

    nodeUpdates.push({
      id: node.id,
      hidden: !visible,
      borderWidth: isHighlighted ? 4 : 2,
      color: isHighlighted
        ? {
            background: node.color?.background || '#8c8c8c',
            border: '#ffffff',
            highlight: {
              background: node.color?.background || '#8c8c8c',
              border: '#ffffff',
            },
          }
        : node.color,
    });

    if (visible) {
      visibleNodeIds.add(node.id);
    }
  }

  // 收集边更新
  const edgeUpdates: Array<{
    color: any;
    hidden: boolean;
    id: string;
    width: number;
  }> = [];

  for (const edge of allEdges.value) {
    const visible =
      visibleNodeIds.has(edge.from) && visibleNodeIds.has(edge.to);
    const isHighlighted = getEdgeHighlightState(edge);

    edgeUpdates.push({
      id: edge.id,
      hidden: !visible,
      width: isHighlighted ? 3 : 1,
      color: isHighlighted
        ? { color: '#ffffff', highlight: '#ffffff' }
        : edge.color,
    });
  }

  // 【关键】批量更新，只触发一次重绘
  nodesDataSet.value.update(nodeUpdates);
  edgesDataSet.value.update(edgeUpdates);
}

// =============================================
// 高亮逻辑
// =============================================
function getNodeHighlightState(node: VisNode): boolean {
  if (highlightMode.value === 'none') return false;

  if (highlightMode.value === 'singleNode' && highlightedSingleNodeId.value) {
    if (node.id === highlightedSingleNodeId.value) return true;
    return allEdges.value.some(
      (e) =>
        (e.from === highlightedSingleNodeId.value && e.to === node.id) ||
        (e.to === highlightedSingleNodeId.value && e.from === node.id),
    );
  }

  if (highlightMode.value === 'nodeType' && highlightedNodeType.value) {
    return node.group === highlightedNodeType.value;
  }

  if (highlightMode.value === 'relationType' && highlightedRelationType.value) {
    return allEdges.value.some(
      (e) =>
        e.data.relation_type === highlightedRelationType.value &&
        (e.from === node.id || e.to === node.id),
    );
  }

  if (highlightMode.value === 'search' && searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase();
    return (
      node.label.toLowerCase().includes(keyword) ||
      node.id.toLowerCase().includes(keyword)
    );
  }

  return false;
}

function getEdgeHighlightState(edge: VisEdge): boolean {
  if (highlightMode.value === 'none') return false;

  if (highlightMode.value === 'singleNode' && highlightedSingleNodeId.value) {
    return (
      edge.from === highlightedSingleNodeId.value ||
      edge.to === highlightedSingleNodeId.value
    );
  }

  if (highlightMode.value === 'relationType' && highlightedRelationType.value) {
    return edge.data.relation_type === highlightedRelationType.value;
  }

  if (highlightMode.value === 'nodeType' && highlightedNodeType.value) {
    const fromNode = allNodes.value.find((n) => n.id === edge.from);
    const toNode = allNodes.value.find((n) => n.id === edge.to);
    return (
      fromNode?.group === highlightedNodeType.value ||
      toNode?.group === highlightedNodeType.value
    );
  }

  return false;
}

// =============================================
// 事件处理
// =============================================

// 用于区分单击和双击的计时器
let clickTimer: null | ReturnType<typeof setTimeout> = null;
let isDoubleClick = false;

function onNetworkClick(params: any) {
  if (!isMounted) return;

  if (params.nodes && params.nodes.length > 0) {
    const nodeId = params.nodes[0];

    // 清除之前的计时器
    if (clickTimer) {
      clearTimeout(clickTimer);
      clickTimer = null;
    }

    // 延迟执行单击操作，等待可能的双击
    clickTimer = setTimeout(() => {
      // 再次检查组件是否仍然挂载
      if (!isMounted) return;

      if (!isDoubleClick) {
        const node = allNodes.value.find((n) => n.id === nodeId);
        if (node) {
          showNodeDetail(node);
        }
      }
      isDoubleClick = false;
    }, 250); // 250ms 内如果有双击，则取消单击操作
  }
}

function onNetworkDoubleClick(params: any) {
  if (!isMounted) return;

  // 标记为双击，阻止单击操作
  isDoubleClick = true;
  if (clickTimer) {
    clearTimeout(clickTimer);
    clickTimer = null;
  }

  if (params.nodes && params.nodes.length > 0) {
    const nodeId = params.nodes[0];
    handleSingleNodeHighlight(nodeId);
  }
}

function showNodeDetail(node: VisNode) {
  selectedNode.value = node;

  // 获取出边及其目标节点（与 3D 图保持一致）
  const outgoingEdges = allEdges.value.filter((e) => e.from === node.id);
  const outgoingWithNodes: EdgeWithNode[] = outgoingEdges.map((edge) => ({
    edge,
    node: allNodes.value.find((n) => n.id === edge.to) || null,
  }));

  // 获取入边及其源节点
  const incomingEdges = allEdges.value.filter((e) => e.to === node.id);
  const incomingWithNodes: EdgeWithNode[] = incomingEdges.map((edge) => ({
    edge,
    node: allNodes.value.find((n) => n.id === edge.from) || null,
  }));

  selectedNodeEdges.value = {
    incoming: incomingWithNodes,
    outgoing: outgoingWithNodes,
  };

  drawerVisible.value = true;
}

function handleNodeTypeClick(label: NodeLabel) {
  highlightedSingleNodeId.value = null;

  if (highlightedNodeType.value === label) {
    highlightedNodeType.value = null;
    highlightMode.value = 'none';
  } else {
    highlightedNodeType.value = label;
    highlightedRelationType.value = null;
    highlightMode.value = 'nodeType';
  }
  updateGraph();
}

function handleRelationTypeClick(type: RelationType) {
  highlightedSingleNodeId.value = null;

  if (highlightedRelationType.value === type) {
    highlightedRelationType.value = null;
    highlightMode.value = 'none';
  } else {
    highlightedRelationType.value = type;
    highlightedNodeType.value = null;
    highlightMode.value = 'relationType';
  }
  updateGraph();
}

function handleSingleNodeHighlight(nodeId: string) {
  if (!isMounted) return;

  if (highlightedSingleNodeId.value === nodeId) {
    highlightedSingleNodeId.value = null;
    highlightMode.value = 'none';
  } else {
    highlightedSingleNodeId.value = nodeId;
    highlightedNodeType.value = null;
    highlightedRelationType.value = null;
    highlightMode.value = 'singleNode';
  }
  updateGraph();

  // 聚焦到节点
  if (highlightedSingleNodeId.value && networkInstance.value && isMounted) {
    networkInstance.value.focus(nodeId, {
      scale: 1.5,
      animation: { duration: 500, easingFunction: 'easeInOutQuad' },
    });
  }
}

// 以节点为中心探索（聚焦并高亮）
function focusOnNode(nodeId: string) {
  if (!isMounted || !networkInstance.value) return;

  // 高亮此节点的所有关系
  highlightedSingleNodeId.value = nodeId;
  highlightedNodeType.value = null;
  highlightedRelationType.value = null;
  highlightMode.value = 'singleNode';
  updateGraph();

  // 聚焦并放大
  networkInstance.value.focus(nodeId, {
    scale: 2,
    animation: { duration: 800, easingFunction: 'easeInOutQuad' },
  });

  // 选中节点
  networkInstance.value.selectNodes([nodeId]);
}

function handleSearchSelect(nodeId: string) {
  const node = allNodes.value.find((n) => n.id === nodeId);
  if (node && networkInstance.value) {
    networkInstance.value.focus(nodeId, {
      scale: 1.5,
      animation: { duration: 500, easingFunction: 'easeInOutQuad' },
    });
    highlightMode.value = 'singleNode';
    highlightedNodeType.value = null;
    highlightedRelationType.value = null;
    highlightedSingleNodeId.value = nodeId;
    updateGraph();
    showNodeDetail(node);
  }
}

// 处理后端搜索结果选择（如果节点不在图中则添加）
async function handleApiSearchSelect(apiNode: GraphCorpusApi.NodeItem) {
  const existingNode = allNodes.value.find((n) => n.id === apiNode.id);

  if (existingNode) {
    // 节点已在图中，直接聚焦
    handleSearchSelect(apiNode.id);
  } else {
    // 节点不在图中，添加到图中
    const newVisNode = transformApiNodeToVis(apiNode);
    allNodes.value.push(newVisNode);

    // 更新 DataSet
    if (nodesDataSet.value) {
      nodesDataSet.value.add(newVisNode);
    }

    // 更新筛选器
    if (!activeFilters.value.has(apiNode.label)) {
      activeFilters.value.add(apiNode.label);
    }

    message.success(`已将「${apiNode.name}」添加到图中`);

    // 等待下一帧后聚焦
    await nextTick();
    if (networkInstance.value) {
      networkInstance.value.focus(apiNode.id, {
        scale: 1.5,
        animation: { duration: 500, easingFunction: 'easeInOutQuad' },
      });
      highlightedSingleNodeId.value = apiNode.id;
      highlightedNodeType.value = null;
      highlightedRelationType.value = null;
      highlightMode.value = 'singleNode';
      updateGraph();
      showNodeDetail(newVisNode);
    }
  }
}

function clearHighlight() {
  highlightMode.value = 'none';
  highlightedNodeType.value = null;
  highlightedRelationType.value = null;
  highlightedSingleNodeId.value = null;
  searchKeyword.value = '';
  updateGraph();
}

function handleFilterChange(label: string, checked: boolean) {
  if (checked) {
    activeFilters.value.add(label);
  } else {
    activeFilters.value.delete(label);
  }
  updateGraph();
}

function selectAllFilters(selectAll: boolean) {
  if (selectAll) {
    // 使用动态检测的类型，而不是硬编码配置
    activeFilters.value = new Set(Object.keys(nodeTypeStats.value));
  } else {
    activeFilters.value.clear();
  }
  updateGraph();
}

// =============================================
// 工具操作
// =============================================
function handleZoomIn() {
  if (networkInstance.value) {
    const scale = networkInstance.value.getScale();
    networkInstance.value.moveTo({ scale: scale * 1.3 });
  }
}

function handleZoomOut() {
  if (networkInstance.value) {
    const scale = networkInstance.value.getScale();
    networkInstance.value.moveTo({ scale: scale / 1.3 });
  }
}

function handleFitView() {
  networkInstance.value?.fit({ animation: true });
}

async function handleRefresh() {
  clearHighlight();
  await initGraph();
  message.success('已刷新');
}

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value;
  nextTick(() => {
    networkInstance.value?.fit();
  });
}

// 主题已跟随系统设置，不再需要手动切换

// =============================================
// 辅助函数（使用与 3D 图一致的颜色算法）
// =============================================
function getLabelConfig(label: string) {
  const config = NODE_LABEL_CONFIG[label as NodeLabel];
  // 使用共享的颜色函数，确保与 3D 图颜色一致
  return {
    displayName: config?.displayName || getNodeDisplayName(label),
    color: getNodeColor(label),
    icon: config?.icon || 'NodeIndexOutlined',
  };
}

function getRelationConfig(type: string) {
  const config = RELATION_TYPE_CONFIG[type as RelationType];
  // 使用共享的颜色函数，确保与 3D 图颜色一致
  return {
    displayName: config?.displayName || getRelationDisplayName(type),
    lineColor: getEdgeColor(type),
  };
}

/**
 * 格式化 JSON 对象为可读字符串
 */
function formatJson(obj: null | Record<string, any> | undefined): string {
  if (!obj || Object.keys(obj).length === 0) return '-';
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

// =============================================
// 监听器
// =============================================

// 监听主题变化，更新节点样式
watch(isDark, () => {
  if (!nodesDataSet.value || !networkInstance.value) return;

  const fontColor = isDarkMode.value ? '#ffffff' : '#1f1f1f';
  const highlightBorder = isDarkMode.value ? '#ffffff' : '#1f1f1f';

  // 更新所有节点的字体颜色
  const updates = allNodes.value.map((node) => ({
    id: node.id,
    font: { color: fontColor },
    color: {
      ...node.color,
      highlight: {
        background: node.color?.background || '#1890ff',
        border: highlightBorder,
      },
    },
  }));
  nodesDataSet.value.update(updates);
});

onMounted(async () => {
  isMounted = true;
  await initGraph();
});

onUnmounted(() => {
  // 标记组件已卸载，阻止后续回调更新状态
  isMounted = false;

  // 清理定时器
  if (clickTimer) {
    clearTimeout(clickTimer);
    clickTimer = null;
  }
  if (searchTimer) {
    clearTimeout(searchTimer);
    searchTimer = null;
  }

  // 销毁网络实例
  if (networkInstance.value) {
    // 先停止物理模拟，防止在销毁过程中触发更新
    try {
      networkInstance.value.stopSimulation();
      // 移除所有事件监听器
      networkInstance.value.off('click');
      networkInstance.value.off('doubleClick');
      networkInstance.value.off('stabilizationProgress');
      networkInstance.value.off('stabilizationIterationsDone');
    } catch {
      // 忽略可能的错误
    }
    networkInstance.value.destroy();
    networkInstance.value = null;
  }

  // 清理数据集
  if (nodesDataSet.value) {
    nodesDataSet.value.clear();
    nodesDataSet.value = null;
  }
  if (edgesDataSet.value) {
    edgesDataSet.value.clear();
    edgesDataSet.value = null;
  }
});
</script>

<template>
  <div
    class="vis-network-view"
    :class="{ fullscreen: isFullscreen, dark: isDarkMode }"
  >
    <!-- 左侧控制面板 -->
    <div class="control-panel left-panel">
      <!-- 搜索框 -->
      <div class="panel-section">
        <div class="section-title"><SearchOutlined /> 搜索关键词</div>
        <Input
          v-model:value="searchKeyword"
          placeholder="输入关键词名称..."
          allow-clear
          size="small"
          class="search-input"
          :disabled="focusMode || focusLoading"
        >
          <template #prefix><SearchOutlined /></template>
        </Input>

        <!-- 聚焦加载中 -->
        <div v-if="focusLoading" class="focus-loading-panel">
          <div class="focus-loading-spinner"></div>
          <span>正在加载关联数据...</span>
        </div>

        <!-- 聚焦模式提示 -->
        <div v-else-if="focusMode" class="focus-mode-panel">
          <div class="focus-mode-info">
            <AimOutlined class="focus-icon" />
            <span>聚焦模式</span>
          </div>
          <div class="focus-node-name">
            {{
              allNodes.find((n) => n.id === focusNodeId)?.data.name ||
              '未知关键词'
            }}
          </div>
          <div class="focus-stats">显示 {{ focusNodeIds.size }} 个关键词</div>
          <Button type="primary" size="small" block @click="exitFocusMode">
            <ReloadOutlined /> 恢复全图
          </Button>
        </div>

        <!-- 本地已加载节点结果 -->
        <div
          v-else-if="localSearchResults.length > 0 || searchResults.length > 0"
          class="search-results"
        >
          <!-- 本地结果（已在图中） -->
          <template v-if="localSearchResults.length > 0">
            <div class="search-section-title">图中关键词</div>
            <div
              v-for="node in localSearchResults"
              :key="`local-${node.id}`"
              class="search-item-wrapper"
            >
              <div class="search-item" @click="handleSearchSelect(node.id)">
                <span
                  class="search-icon"
                  :style="{ background: getLabelConfig(node.group).color }"
                >
                  {{ getNodeIcon(node.group) }}
                </span>
                <span class="search-text">{{ node.data.name }}</span>
              </div>
              <Tooltip title="聚焦：只显示此关键词及其直接关联">
                <Button
                  type="primary"
                  size="small"
                  class="focus-btn"
                  :loading="focusLoading"
                  @click.stop="enterFocusMode(node.id)"
                >
                  <AimOutlined v-if="!focusLoading" />
                </Button>
              </Tooltip>
            </div>
          </template>

          <!-- 后端搜索结果（可能不在图中） -->
          <template v-if="searchResults.length > 0">
            <div class="search-section-title">
              全库搜索
              <span v-if="searchLoading" class="search-loading">搜索中...</span>
            </div>
            <div
              v-for="node in searchResults"
              :key="`api-${node.id}`"
              class="search-item-wrapper"
            >
              <div class="search-item" @click="handleApiSearchSelect(node)">
                <span
                  class="search-icon"
                  :style="{ background: getLabelConfig(node.label).color }"
                >
                  {{ getNodeIcon(node.label) }}
                </span>
                <span class="search-text">{{ node.name }}</span>
                <span
                  v-if="allNodes.some((n) => n.id === node.id)"
                  class="search-tag in-graph"
                >
                  图中
                </span>
                <span v-else class="search-tag add-to-graph">添加</span>
              </div>
              <Tooltip title="聚焦：只显示此关键词及其直接关联">
                <Button
                  type="primary"
                  size="small"
                  class="focus-btn"
                  :loading="focusLoading"
                  @click.stop="enterFocusMode(node.id)"
                >
                  <AimOutlined v-if="!focusLoading" />
                </Button>
              </Tooltip>
            </div>
          </template>
        </div>
        <div v-else-if="searchLoading" class="search-loading-hint">
          搜索中...
        </div>
      </div>

      <!-- 关键词类型筛选（动态从数据中获取） -->
      <div class="panel-section">
        <div class="section-title">
          <NodeIndexOutlined /> 关键词类型
          <span class="section-hint">
            <Button type="link" size="small" @click="selectAllFilters(true)">
              全选
            </Button>
            |
            <Button type="link" size="small" @click="selectAllFilters(false)">
              清空
            </Button>
          </span>
        </div>
        <div class="type-list">
          <template v-for="(stats, label) in nodeTypeStats" :key="label">
            <div
              class="type-item"
              :class="{
                active: highlightedNodeType === label,
                dimmed:
                  highlightMode !== 'none' && highlightedNodeType !== label,
              }"
            >
              <input
                type="checkbox"
                :checked="activeFilters.has(label as string)"
                @change="
                  (e) =>
                    handleFilterChange(
                      label as string,
                      (e.target as HTMLInputElement).checked,
                    )
                "
              />
              <span
                class="type-dot"
                :style="{ background: stats.color }"
                @click="handleNodeTypeClick(label as NodeLabel)"
              ></span>
              <span
                class="type-name"
                @click="handleNodeTypeClick(label as NodeLabel)"
              >
                {{ stats.displayName }}
              </span>
              <Badge
                :count="stats.count"
                :number-style="{
                  backgroundColor: stats.active ? stats.color : '#666',
                  fontSize: '10px',
                  minWidth: '18px',
                  height: '18px',
                  lineHeight: '18px',
                }"
              />
            </div>
          </template>
        </div>
      </div>

      <!-- 关系类型（动态从数据中获取） -->
      <div class="panel-section">
        <div class="section-title">
          <BranchesOutlined /> 关系类型
          <span class="section-hint">点击高亮</span>
        </div>
        <div class="type-list relation-list">
          <div
            v-for="(stats, type) in relationTypeStats"
            :key="type"
            class="type-item relation-item"
            :class="{
              active: highlightedRelationType === type,
              dimmed:
                highlightMode !== 'none' && highlightedRelationType !== type,
            }"
            @click="handleRelationTypeClick(type as RelationType)"
          >
            <span class="type-line" :style="{ background: stats.color }"></span>
            <span class="type-name">{{ stats.displayName }}</span>
            <Badge
              :count="stats.count"
              :number-style="{
                backgroundColor: stats.active ? stats.color : '#666',
                fontSize: '10px',
                minWidth: '18px',
                height: '18px',
                lineHeight: '18px',
              }"
            />
          </div>
        </div>
      </div>

      <!-- 清除高亮按钮 -->
      <div v-if="highlightMode !== 'none'" class="clear-highlight">
        <Button
          type="primary"
          danger
          size="small"
          block
          @click="clearHighlight"
        >
          <CloseCircleOutlined /> 清除高亮
        </Button>
      </div>
    </div>

    <!-- 顶部工具栏 -->
    <div class="top-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <Tooltip title="放大">
          <Button type="text" size="small" @click="handleZoomIn">
            <ZoomInOutlined />
          </Button>
        </Tooltip>
        <Tooltip title="缩小">
          <Button type="text" size="small" @click="handleZoomOut">
            <ZoomOutOutlined />
          </Button>
        </Tooltip>
        <Tooltip title="适应画布">
          <Button type="text" size="small" @click="handleFitView">
            <AimOutlined />
          </Button>
        </Tooltip>
        <Tooltip title="刷新数据">
          <Button type="text" size="small" @click="handleRefresh">
            <ReloadOutlined />
          </Button>
        </Tooltip>
        <Divider type="vertical" />
        <Tooltip :title="isFullscreen ? '退出全屏' : '全屏'">
          <Button type="text" size="small" @click="toggleFullscreen">
            <FullscreenExitOutlined v-if="isFullscreen" />
            <FullscreenOutlined v-else />
          </Button>
        </Tooltip>
      </div>
    </div>

    <!-- 聚焦模式提示（顶部横幅） -->
    <div v-if="focusMode" class="focus-mode-bar">
      <AimOutlined />
      <span>
        聚焦模式：「{{
          allNodes.find((n) => n.id === focusNodeId)?.data.name
        }}」及 {{ focusNodeIds.size - 1 }} 个关联关键词
      </span>
      <Button type="link" size="small" @click="exitFocusMode">
        恢复全图
      </Button>
    </div>

    <!-- 高亮信息提示 -->
    <div v-else-if="highlightMode !== 'none'" class="highlight-info">
      <template
        v-if="highlightMode === 'singleNode' && highlightedSingleNodeId"
      >
        高亮显示: 关键词「{{
          allNodes.find((n) => n.id === highlightedSingleNodeId)?.data.name
        }}」的直接关系
      </template>
      <template v-else-if="highlightMode === 'nodeType' && highlightedNodeType">
        高亮显示:
        <Tag :color="getLabelConfig(highlightedNodeType).color">
          {{ getLabelConfig(highlightedNodeType).displayName }}
        </Tag>
        类型的 {{ nodeTypeStats[highlightedNodeType]?.count || 0 }} 个关键词
      </template>
      <template
        v-else-if="highlightMode === 'relationType' && highlightedRelationType"
      >
        高亮显示:
        <Tag :color="getRelationConfig(highlightedRelationType).lineColor">
          {{ getRelationConfig(highlightedRelationType).displayName }}
        </Tag>
        类型的 {{ relationTypeStats[highlightedRelationType]?.count || 0 }} 条边
      </template>
      <template v-else-if="highlightMode === 'search'">
        搜索: "{{ searchKeyword }}" 匹配到 {{ searchResults.length }} 个关键词
      </template>
      <Button type="link" size="small" @click="clearHighlight">清除</Button>
    </div>

    <!-- 图容器 -->
    <div ref="containerRef" class="graph-container"></div>

    <!-- Loading 遮罩层 -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <div class="loading-text">加载数据中...</div>
    </div>

    <!-- 右下角统计信息 -->
    <div class="stats-panel">
      <div class="stats-item">
        <span class="stats-value">
          {{ focusMode ? focusNodeIds.size : allNodes.length }}
        </span>
        <span class="stats-label">{{
          focusMode ? '聚焦关键词' : '关键词'
        }}</span>
      </div>
      <div class="stats-item">
        <span class="stats-value">
          {{
            focusMode
              ? allEdges.filter(
                  (e) => focusNodeIds.has(e.from) && focusNodeIds.has(e.to),
                ).length
              : allEdges.length
          }}
        </span>
        <span class="stats-label">{{ focusMode ? '聚焦关系' : '关系' }}</span>
      </div>
    </div>

    <!-- 关键词详情抽屉 -->
    <Drawer
      v-model:open="drawerVisible"
      title="关键词详情"
      placement="right"
      :width="420"
      :body-style="{
        padding: '16px',
        background: isDarkMode ? '#141414' : '#fff',
      }"
      :header-style="{
        background: isDarkMode ? '#1f1f1f' : '#fff',
        borderBottom: isDarkMode ? '1px solid #303030' : '1px solid #f0f0f0',
      }"
      :root-class-name="isDarkMode ? 'dark-drawer' : ''"
    >
      <template v-if="selectedNode">
        <!-- 关键词头部信息 -->
        <div class="drawer-node-header">
          <div
            class="drawer-node-avatar"
            :style="{ background: getLabelConfig(selectedNode.group).color }"
          >
            {{ getNodeIcon(selectedNode.group) }}
          </div>
          <div class="drawer-node-info">
            <div
              class="drawer-node-name"
              :style="{ color: isDarkMode ? '#fff' : '#1f1f1f' }"
            >
              {{ selectedNode.data.name }}
            </div>
            <Tag :color="getLabelConfig(selectedNode.group).color" size="small">
              {{ getLabelConfig(selectedNode.group).displayName }}
            </Tag>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="drawer-action-buttons">
          <Button
            type="primary"
            ghost
            size="small"
            block
            @click="
              handleSingleNodeHighlight(selectedNode.id);
              drawerVisible = false;
            "
          >
            <BranchesOutlined /> 高亮此关键词的所有关系
          </Button>
          <Button
            type="primary"
            size="small"
            block
            @click="
              enterFocusMode(selectedNode.id);
              drawerVisible = false;
            "
          >
            <AimOutlined /> 聚焦模式（只显示关联关键词）
          </Button>
          <Button
            size="small"
            block
            @click="
              focusOnNode(selectedNode.id);
              drawerVisible = false;
            "
          >
            <AimOutlined /> 以此关键词为中心探索
          </Button>
        </div>

        <!-- 基本信息 -->
        <Descriptions
          :column="1"
          size="small"
          bordered
          class="drawer-descriptions"
        >
          <DescriptionsItem label="关键词ID">
            <code class="drawer-code-text">{{ selectedNode.id }}</code>
          </DescriptionsItem>
          <DescriptionsItem label="关键词名称">
            {{ selectedNode.data.name }}
          </DescriptionsItem>
          <DescriptionsItem label="关键词类型">
            <Tag :color="getLabelConfig(selectedNode.group).color">
              {{ getNodeIcon(selectedNode.group) }}
              {{ getLabelConfig(selectedNode.group).displayName }}
            </Tag>
          </DescriptionsItem>
          <DescriptionsItem label="描述">
            {{ selectedNode.data.description || '-' }}
          </DescriptionsItem>
          <DescriptionsItem label="租户">
            {{ selectedNode.data.tenant_code || '-' }}
          </DescriptionsItem>
          <DescriptionsItem label="状态">
            <Tag
              :color="selectedNode.data.is_active === 1 ? 'green' : 'default'"
              size="small"
            >
              {{ selectedNode.data.is_active === 1 ? '启用' : '禁用' }}
            </Tag>
          </DescriptionsItem>
        </Descriptions>

        <!-- AI 指令 -->
        <div
          v-if="
            selectedNode.data.ai_instruction &&
            Object.keys(selectedNode.data.ai_instruction).length > 0
          "
          class="drawer-json-section"
        >
          <div
            class="drawer-json-title"
            :style="{ color: isDarkMode ? '#999' : '#666' }"
          >
            🤖 AI 指令
          </div>
          <pre class="drawer-json-content" :class="{ dark: isDarkMode }">{{
            formatJson(selectedNode.data.ai_instruction)
          }}</pre>
        </div>

        <!-- Properties 属性 -->
        <div
          v-if="
            selectedNode.data.properties &&
            Object.keys(selectedNode.data.properties).length > 0
          "
          class="drawer-json-section"
        >
          <div
            class="drawer-json-title"
            :style="{ color: isDarkMode ? '#999' : '#666' }"
          >
            📋 属性 (Properties)
          </div>
          <pre class="drawer-json-content" :class="{ dark: isDarkMode }">{{
            formatJson(selectedNode.data.properties)
          }}</pre>
        </div>

        <!-- 关联关系 -->
        <div class="relation-section" :class="{ dark: isDarkMode }">
          <div class="relation-section-title">关联关系</div>

          <div
            v-if="
              selectedNodeEdges.outgoing.length === 0 &&
              selectedNodeEdges.incoming.length === 0
            "
            class="relation-empty"
          >
            暂无关联关系
          </div>

          <!-- 出边关联 -->
          <div
            v-for="item in selectedNodeEdges.outgoing"
            :key="`out-${item.edge.id}`"
            class="relation-item"
            :class="{ dark: isDarkMode }"
            @click="item.node && showNodeDetail(item.node)"
          >
            <div class="relation-item-content">
              <span class="relation-node-icon">{{
                item.node ? getNodeIcon(item.node.group) : '📄'
              }}</span>
              <span class="relation-node-name">
                {{
                  item.node?.data.name ||
                  item.edge.data.target_name ||
                  item.edge.to
                }}
              </span>
            </div>
            <span class="relation-type-tag">
              {{ item.edge.data.relation_type }}
            </span>
          </div>

          <!-- 入边关联 -->
          <div
            v-for="item in selectedNodeEdges.incoming"
            :key="`in-${item.edge.id}`"
            class="relation-item"
            :class="{ dark: isDarkMode }"
            @click="item.node && showNodeDetail(item.node)"
          >
            <div class="relation-item-content">
              <span class="relation-node-icon">{{
                item.node ? getNodeIcon(item.node.group) : '📄'
              }}</span>
              <span class="relation-node-name">
                {{
                  item.node?.data.name ||
                  item.edge.data.source_name ||
                  item.edge.from
                }}
              </span>
            </div>
            <span class="relation-type-tag">
              {{ item.edge.data.relation_type }}
            </span>
          </div>
        </div>
      </template>
    </Drawer>
  </div>
</template>

<style scoped>
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.vis-network-view {
  position: relative;
  height: calc(100vh - 280px);
  min-height: 600px;
  overflow: hidden;
  background: #0a0a0a;
  border-radius: 12px;
  transition: all 0.3s ease;
}

.vis-network-view.fullscreen {
  position: fixed;
  inset: 0;
  z-index: 1000;
  height: 100vh;
  border-radius: 0;
}

.vis-network-view:not(.dark) {
  background: #f8f9fa;
}

/* 左侧控制面板 */
.left-panel {
  position: absolute;
  top: 60px;
  bottom: 16px;
  left: 16px;
  z-index: 20;
  width: 220px;
  padding: 16px;
  overflow-y: auto;
  background: rgb(20 20 20 / 95%);
  border: 1px solid rgb(255 255 255 / 8%);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgb(0 0 0 / 40%);
  backdrop-filter: blur(20px);
}

.vis-network-view:not(.dark) .left-panel {
  background: rgb(255 255 255 / 95%);
  border-color: rgb(0 0 0 / 8%);
  box-shadow: 0 8px 32px rgb(0 0 0 / 10%);
}

.panel-section {
  margin-bottom: 20px;
}

.section-title {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 12px;
  font-size: 12px;
  font-weight: 600;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.section-hint {
  margin-left: auto;
  font-size: 10px;
  font-weight: 400;
  color: #666;
  text-transform: none;
}

/* 搜索框 */
.search-input {
  background: rgb(255 255 255 / 5%) !important;
  border-color: rgb(255 255 255 / 10%) !important;
  border-radius: 8px;
}

.search-results {
  max-height: 200px;
  margin-top: 8px;
  overflow-y: auto;
}

.search-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px;
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.2s;
}

.search-item:hover {
  background: rgb(255 255 255 / 10%);
}

.search-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  font-size: 12px;
  border-radius: 6px;
}

.search-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  color: #ddd;
  white-space: nowrap;
}

.vis-network-view:not(.dark) .search-text {
  color: #333;
}

.search-section-title {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 0;
  font-size: 11px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid rgb(255 255 255 / 8%);
}

.search-loading {
  font-weight: 400;
  color: #1890ff;
  text-transform: none;
}

.search-loading-hint {
  padding: 12px;
  font-size: 12px;
  color: #888;
  text-align: center;
}

.search-tag {
  flex-shrink: 0;
  padding: 2px 6px;
  font-size: 10px;
  font-weight: 500;
  border-radius: 4px;
}

.search-tag.in-graph {
  color: #52c41a;
  background: rgb(82 196 26 / 15%);
}

.search-tag.add-to-graph {
  color: #1890ff;
  background: rgb(24 144 255 / 15%);
}

/* 搜索结果项容器（包含聚焦按钮） */
.search-item-wrapper {
  display: flex;
  gap: 6px;
  align-items: center;
}

.search-item-wrapper .search-item {
  flex: 1;
  min-width: 0;
}

.focus-btn {
  flex-shrink: 0;
  padding: 0 6px !important;
}

/* 聚焦模式面板 */
.focus-loading-panel {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  padding: 12px;
  margin-top: 8px;
  font-size: 12px;
  color: #1890ff;
  background: rgb(24 144 255 / 10%);
  border: 1px solid rgb(24 144 255 / 30%);
  border-radius: 8px;
}

.focus-loading-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgb(24 144 255 / 30%);
  border-top-color: #1890ff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.focus-mode-panel {
  padding: 12px;
  margin-top: 8px;
  text-align: center;
  background: rgb(24 144 255 / 10%);
  border: 1px solid rgb(24 144 255 / 30%);
  border-radius: 8px;
}

.focus-mode-info {
  display: flex;
  gap: 6px;
  align-items: center;
  justify-content: center;
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 600;
  color: #1890ff;
}

.focus-icon {
  font-size: 16px;
}

.focus-node-name {
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  white-space: nowrap;
}

.vis-network-view:not(.dark) .focus-node-name {
  color: #1f1f1f;
}

.focus-stats {
  margin-bottom: 12px;
  font-size: 12px;
  color: #888;
}

/* 类型列表 */
.type-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.type-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 10px;
  cursor: pointer;
  border: 1px solid transparent;
  border-radius: 8px;
  transition: all 0.2s;
}

.type-item:hover {
  background: rgb(255 255 255 / 8%);
}

.type-item.active {
  background: rgb(255 255 255 / 12%);
  border-color: rgb(255 255 255 / 20%);
}

.type-item.dimmed {
  opacity: 0.4;
}

.type-item input[type='checkbox'] {
  width: 14px;
  height: 14px;
  cursor: pointer;
}

.type-dot {
  flex-shrink: 0;
  width: 12px;
  height: 12px;
  cursor: pointer;
  border-radius: 50%;
  box-shadow: 0 0 8px currentcolor;
}

.type-line {
  flex-shrink: 0;
  width: 20px;
  height: 3px;
  border-radius: 2px;
}

.type-name {
  flex: 1;
  font-size: 12px;
  color: #ccc;
}

.vis-network-view:not(.dark) .type-name {
  color: #444;
}

.clear-highlight {
  margin-top: 16px;
}

/* 顶部工具栏 */
.top-toolbar {
  position: absolute;
  top: 12px;
  right: 16px;
  left: 250px;
  z-index: 15;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: rgb(20 20 20 / 90%);
  border: 1px solid rgb(255 255 255 / 8%);
  border-radius: 10px;
  backdrop-filter: blur(20px);
}

.vis-network-view:not(.dark) .top-toolbar {
  background: rgb(255 255 255 / 95%);
  border-color: rgb(0 0 0 / 8%);
}

.toolbar-left,
.toolbar-right {
  display: flex;
  gap: 8px;
  align-items: center;
}

.toolbar-label {
  font-size: 12px;
  color: #888;
}

.toolbar-value {
  min-width: 20px;
  font-size: 12px;
  font-weight: 600;
  color: #1890ff;
  text-align: center;
}

.toolbar-right .active {
  color: #1890ff;
}

/* 聚焦模式横幅 */
.focus-mode-bar {
  position: absolute;
  top: 70px;
  left: 250px;
  z-index: 12;
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
  color: #52c41a;
  background: rgb(82 196 26 / 15%);
  border: 1px solid rgb(82 196 26 / 30%);
  border-radius: 8px;
  backdrop-filter: blur(10px);
}

/* 高亮信息提示 */
.highlight-info {
  position: absolute;
  top: 70px;
  left: 250px;
  z-index: 12;
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 16px;
  font-size: 13px;
  color: #69c0ff;
  background: rgb(24 144 255 / 15%);
  border: 1px solid rgb(24 144 255 / 30%);
  border-radius: 8px;
  backdrop-filter: blur(10px);
}

/* 图容器 */
.graph-container {
  position: relative;
  width: 100%;
  height: 100%;
}

.loading-overlay {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 30;
  text-align: center;
  transform: translate(-50%, -50%);
}

.loading-spinner {
  width: 48px;
  height: 48px;
  margin: 0 auto 16px;
  border: 3px solid rgb(255 255 255 / 10%);
  border-top-color: #1890ff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.loading-text {
  font-size: 14px;
  color: #888;
}

.loading-progress {
  width: 200px;
  height: 4px;
  margin-top: 12px;
  overflow: hidden;
  background: rgb(255 255 255 / 10%);
  border-radius: 2px;
}

.loading-progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #1890ff, #52c41a);
  border-radius: 2px;
  transition: width 0.1s ease-out;
}

/* 统计面板 */
.stats-panel {
  position: absolute;
  bottom: 16px;
  left: 250px;
  z-index: 15;
  display: flex;
  gap: 16px;
  padding: 12px 20px;
  background: rgb(20 20 20 / 90%);
  border: 1px solid rgb(255 255 255 / 8%);
  border-radius: 10px;
  backdrop-filter: blur(20px);
}

.vis-network-view:not(.dark) .stats-panel {
  background: rgb(255 255 255 / 95%);
  border-color: rgb(0 0 0 / 8%);
}

.stats-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stats-value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1;
  color: #fff;
}

.vis-network-view:not(.dark) .stats-value {
  color: #1890ff;
}

.stats-label {
  margin-top: 4px;
  font-size: 11px;
  color: #666;
}

/* =============================================
   抽屉样式（节点详情）
   ============================================= */

/* 抽屉节点头部 */
.drawer-node-header {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-bottom: 20px;
}

.drawer-node-avatar {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  font-size: 28px;
  color: #fff;
  border-radius: 14px;
  box-shadow: 0 4px 16px rgb(0 0 0 / 25%);
}

.drawer-node-info {
  flex: 1;
  min-width: 0;
}

.drawer-node-name {
  margin-bottom: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 20px;
  font-weight: 600;
  white-space: nowrap;
}

/* 操作按钮 */
.drawer-action-buttons {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 20px;
}

/* 描述表格 */
.drawer-descriptions {
  margin-bottom: 20px;
}

.drawer-code-text {
  padding: 3px 8px;
  font-family: 'SF Mono', Monaco, Menlo, monospace;
  font-size: 11px;
  color: #1890ff;
  background: rgb(24 144 255 / 10%);
  border-radius: 4px;
}

/* 空边提示 */
.drawer-empty-edges {
  padding: 20px;
  font-size: 13px;
  color: #999;
  text-align: center;
  background: rgb(0 0 0 / 3%);
  border-radius: 8px;
}

/* 边详情卡片 */
.drawer-edge-card {
  padding: 12px;
  margin-bottom: 12px;
  background: rgb(0 0 0 / 3%);
  border: 1px solid rgb(0 0 0 / 8%);
  border-radius: 10px;
  transition: all 0.2s ease;
}

.drawer-edge-card:hover {
  background: rgb(0 0 0 / 6%);
  box-shadow: 0 2px 12px rgb(0 0 0 / 8%);
}

.drawer-edge-card.dark {
  background: rgb(255 255 255 / 5%);
  border-color: rgb(255 255 255 / 10%);
}

.drawer-edge-card.dark:hover {
  background: rgb(255 255 255 / 10%);
  box-shadow: 0 2px 12px rgb(0 0 0 / 30%);
}

/* 边关系标签 */
.drawer-edge-relation {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.drawer-arrow {
  font-size: 16px;
  font-weight: bold;
}

/* 目标/源节点信息 */
.drawer-target-node,
.drawer-source-node {
  padding: 10px;
  background: rgb(0 0 0 / 3%);
  border-radius: 8px;
}

.drawer-target-node.dark,
.drawer-source-node.dark {
  background: rgb(255 255 255 / 3%);
}

.drawer-node-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.drawer-node-icon {
  flex-shrink: 0;
  font-size: 18px;
}

.drawer-node-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
}

.drawer-node-desc {
  padding: 8px 10px;
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.6;
  color: #666;
  background: rgb(0 0 0 / 4%);
  border-radius: 6px;
}

.drawer-node-desc.dark {
  color: #999;
  background: rgb(255 255 255 / 5%);
}

/* JSON 内容区域 */
.drawer-json-section {
  margin-bottom: 16px;
}

.drawer-json-title {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}

.drawer-json-content {
  max-height: 200px;
  padding: 12px;
  margin: 0;
  overflow: auto;
  font-family: 'SF Mono', Monaco, Menlo, 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.6;
  color: #333;
  word-break: break-all;
  white-space: pre-wrap;
  background: rgb(0 0 0 / 4%);
  border: 1px solid rgb(0 0 0 / 8%);
  border-radius: 8px;
}

.drawer-json-content.dark {
  color: #a6e22e;
  background: rgb(255 255 255 / 5%);
  border-color: rgb(255 255 255 / 10%);
}

/* =============================================
   关联关系列表样式（新设计）
   ============================================= */
.relation-section {
  margin-top: 16px;
}

.relation-section-title {
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: #888;
}

.relation-section.dark .relation-section-title {
  color: #666;
}

.relation-empty {
  padding: 24px;
  font-size: 13px;
  color: #999;
  text-align: center;
  background: rgb(255 255 255 / 3%);
  border: 1px dashed rgb(255 255 255 / 10%);
  border-radius: 12px;
}

.relation-item {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  margin-bottom: 8px;
  cursor: pointer;
  background: rgb(0 0 0 / 5%);
  border-radius: 12px;
  transition: all 0.2s ease;
}

.relation-item.dark {
  background: rgb(255 255 255 / 5%);
}

.relation-item:hover {
  background: rgb(0 0 0 / 10%);
  transform: translateX(4px);
}

.relation-item.dark:hover {
  background: rgb(255 255 255 / 10%);
}

.relation-item:active {
  transform: translateX(2px);
}

.relation-item-content {
  display: flex;
  flex: 1;
  gap: 12px;
  align-items: center;
  min-width: 0;
}

.relation-node-icon {
  flex-shrink: 0;
  font-size: 20px;
  filter: drop-shadow(0 2px 4px rgb(0 0 0 / 20%));
}

.relation-node-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 15px;
  font-weight: 500;
  color: #333;
  white-space: nowrap;
}

.relation-item.dark .relation-node-name {
  color: #e0e0e0;
}

.relation-type-tag {
  flex-shrink: 0;
  padding: 4px 12px;
  font-family: 'SF Mono', Monaco, Menlo, monospace;
  font-size: 11px;
  font-weight: 600;
  color: #00d4aa;
  letter-spacing: 0.5px;
  background: rgb(0 212 170 / 12%);
  border-radius: 6px;
  transition: all 0.2s ease;
}

.relation-item:hover .relation-type-tag {
  background: rgb(0 212 170 / 20%);
  box-shadow: 0 0 12px rgb(0 212 170 / 30%);
}

/* 暗色抽屉全局样式 */
:global(.dark-drawer .ant-drawer-header) {
  background: #1f1f1f !important;
  border-bottom-color: #303030 !important;
}

:global(.dark-drawer .ant-drawer-title) {
  color: #fff !important;
}

:global(.dark-drawer .ant-drawer-close) {
  color: #888 !important;
}

:global(.dark-drawer .ant-drawer-close:hover) {
  color: #fff !important;
}

:global(.dark-drawer .ant-drawer-body) {
  background: #141414 !important;
}

:global(.dark-drawer .ant-descriptions) {
  background: transparent !important;
}

:global(.dark-drawer .ant-descriptions-bordered .ant-descriptions-item-label) {
  color: #888 !important;
  background: rgb(255 255 255 / 5%) !important;
  border-color: #303030 !important;
}

:global(
  .dark-drawer .ant-descriptions-bordered .ant-descriptions-item-content
) {
  color: #ddd !important;
  background: transparent !important;
  border-color: #303030 !important;
}

:global(.dark-drawer .ant-descriptions-bordered .ant-descriptions-view) {
  border-color: #303030 !important;
}

:global(.dark-drawer .ant-divider) {
  border-color: #303030 !important;
}

:global(.dark-drawer .ant-divider-inner-text) {
  color: #999 !important;
}
</style>
