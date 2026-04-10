<script setup lang="ts">
import type { GraphEdge, GraphNode, NodeLabel, RelationType } from '../types';

import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';

import {
  AimOutlined,
  BgColorsOutlined,
  BranchesOutlined,
  CloseCircleOutlined,
  DownloadOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  InfoCircleOutlined,
  NodeIndexOutlined,
  ReloadOutlined,
  SearchOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
} from '@ant-design/icons-vue';
import { Graph } from '@antv/g6';
import {
  Badge,
  Button,
  Descriptions,
  DescriptionsItem,
  Divider,
  Drawer,
  Input,
  message,
  Select,
  Slider,
  Switch,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import { getGraphVisualizationApi } from '#/api/core/graph-corpus';

import { NODE_LABEL_CONFIG, RELATION_TYPE_CONFIG } from '../types';

// =============================================
// 状态定义
// =============================================
const containerRef = ref<HTMLDivElement | null>(null);
const graphInstance = ref<Graph | null>(null);
const isFullscreen = ref(false);
const isDarkMode = ref(true);
const showLabels = ref(true);
const nodeSize = ref(36);
const loading = ref(false);
const searchKeyword = ref('');

// 数据状态
const allNodes = ref<GraphNode[]>([]);
const allEdges = ref<GraphEdge[]>([]);

// 布局
const selectedLayout = ref<string>('circular');
const layoutOptions = [
  { value: 'circular', label: '环形' },
  { value: 'radial', label: '辐射' },
  { value: 'dagre', label: '层次' },
  { value: 'concentric', label: '同心圆' },
];

// 节点度数过滤（只展示边数 >= minDegree 的节点）
// 注意：如果边表中的节点ID与节点表不匹配，设为0可显示所有节点
const minDegree = ref<number>(6);

// 高亮模式
type HighlightMode =
  | 'combined'
  | 'nodeType'
  | 'none'
  | 'relationType'
  | 'search'
  | 'singleNode';
const highlightMode = ref<HighlightMode>('none');
const highlightedNodeType = ref<NodeLabel | null>(null);
const highlightedRelationType = ref<null | RelationType>(null);
const highlightedSingleNodeId = ref<null | string>(null); // 单个节点高亮

// 节点详情抽屉
const drawerVisible = ref(false);
const selectedNode = ref<GraphNode | null>(null);
const selectedNodeEdges = ref<{ incoming: GraphEdge[]; outgoing: GraphEdge[] }>(
  {
    incoming: [],
    outgoing: [],
  },
);

// =============================================
// 计算属性
// =============================================

// 节点类型统计
const nodeTypeStats = computed(() => {
  const stats: Record<NodeLabel, { active: boolean; count: number }> =
    {} as any;
  const activeNodes = allNodes.value.filter(
    (n: any) => n.is_deleted === 0 && n.is_active === 1,
  );

  for (const label of Object.keys(NODE_LABEL_CONFIG) as NodeLabel[]) {
    const count = activeNodes.filter((n) => n.label === label).length;
    stats[label] = {
      count,
      active: highlightedNodeType.value === label,
    };
  }
  return stats;
});

// 关系类型统计
const relationTypeStats = computed(() => {
  const stats: Record<RelationType, { active: boolean; count: number }> =
    {} as any;
  const activeEdges = allEdges.value.filter(
    (e: any) => e.is_deleted === 0 && e.is_active === 1,
  );

  for (const type of Object.keys(RELATION_TYPE_CONFIG) as RelationType[]) {
    const count = activeEdges.filter((e) => e.relationType === type).length;
    stats[type] = {
      count,
      active: highlightedRelationType.value === type,
    };
  }
  return stats;
});

// 搜索结果
const searchResults = computed(() => {
  if (!searchKeyword.value.trim()) return [];
  const keyword = searchKeyword.value.toLowerCase();
  return allNodes.value
    .filter((n: any) => n.is_deleted === 0 && n.is_active === 1)
    .filter(
      (n) =>
        n.name.toLowerCase().includes(keyword) ||
        n.id.toLowerCase().includes(keyword),
    )
    .slice(0, 10);
});

// =============================================
// 图数据构建
// =============================================
const buildGraphData = () => {
  // 后端已根据 min_degree 过滤，前端只需过滤掉 PERSONA_ROOT
  const activeNodes = allNodes.value.filter((n: any) => {
    return n.label !== 'PERSONA_ROOT';
  });
  const activeNodeIds = new Set(activeNodes.map((n) => n.id));

  // 默认节点样式（用于未定义的 label 类型）
  const DEFAULT_NODE_CONFIG = {
    color: '#8c8',
    displayName: '未知类型',
    icon: 'QuestionOutlined',
  };

  // 性能优化：大数据量时简化样式
  const isLargeDataset = activeNodes.length > 200;

  const nodes = activeNodes.map((node) => {
    const config =
      NODE_LABEL_CONFIG[node.label as NodeLabel] || DEFAULT_NODE_CONFIG;
    const isHighlighted = getNodeHighlightState(node);

    return {
      id: node.id,
      data: {
        ...node,
      },
      style: {
        fill: config.color,
        stroke: isHighlighted ? '#fff' : config.color,
        lineWidth: isHighlighted ? 2 : 1,
        // 大数据量时禁用阴影以提升性能
        ...(isLargeDataset
          ? {}
          : {
              shadowColor: isHighlighted ? '#fff' : config.color,
              shadowBlur: isHighlighted ? 15 : 6,
            }),
        opacity: getNodeOpacity(node),
        // 大数据量时隐藏标签
        labelText: showLabels.value && !isLargeDataset ? node.name : '',
        labelFill: isDarkMode.value ? '#fff' : '#333',
        labelFontSize: 10,
        labelOffsetY: nodeSize.value / 2 + 10,
        size: getNodeSize(node.label),
        // 大数据量时不显示图标
        ...(isLargeDataset
          ? {}
          : {
              iconText: getNodeIcon(node.label),
              iconFill: '#fff',
              iconFontSize: 12,
            }),
      },
    };
  });

  const edges = allEdges.value
    .filter(
      (e: any) =>
        e.is_deleted === 0 &&
        e.is_active === 1 &&
        activeNodeIds.has(e.source_node_id) &&
        activeNodeIds.has(e.target_node_id),
    )
    .map((edge: any) => {
      const relationType = (edge.relation_type ||
        edge.relationType) as RelationType;
      const config = RELATION_TYPE_CONFIG[relationType];
      const isHighlighted = getEdgeHighlightState(edge);

      // 性能优化：大数据量时简化边样式
      return {
        id: edge.id,
        source: edge.source_node_id,
        target: edge.target_node_id,
        data: {
          relationType,
          relationName: config?.displayName || relationType,
        },
        style: {
          stroke: isHighlighted ? '#fff' : config?.lineColor || '#555',
          lineWidth: isHighlighted ? 2 : 1,
          endArrow: !isLargeDataset, // 大数据量时禁用箭头
          endArrowSize: 5,
          opacity: isLargeDataset ? 0.4 : getEdgeOpacity(edge),
          // 大数据量时不显示边标签
          ...(isLargeDataset
            ? {}
            : {
                labelText: isHighlighted ? config?.displayName || '' : '',
                labelFill: '#fff',
                labelFontSize: 9,
              }),
        },
      };
    });

  return { nodes, edges };
};

// 获取节点高亮状态
const getNodeHighlightState = (node: GraphNode): boolean => {
  // 单个节点高亮模式：高亮选中的节点及其直接连接的节点
  if (highlightMode.value === 'singleNode' && highlightedSingleNodeId.value) {
    if (node.id === highlightedSingleNodeId.value) return true;
    // 检查是否是直接连接的节点
    return allEdges.value.some(
      (e) =>
        (e.sourceNodeId === highlightedSingleNodeId.value &&
          e.targetNodeId === node.id) ||
        (e.targetNodeId === highlightedSingleNodeId.value &&
          e.sourceNodeId === node.id),
    );
  }

  // 组合模式：Node 类型 + Relation 类型
  if (
    highlightMode.value === 'combined' &&
    highlightedNodeType.value &&
    highlightedRelationType.value
  ) {
    // 高亮选中类型的节点
    if (node.label === highlightedNodeType.value) return true;
    // 高亮该关系类型的边连接的 source/target 节点
    return allEdges.value.some(
      (e) =>
        e.relationType === highlightedRelationType.value &&
        (e.sourceNodeId === node.id || e.targetNodeId === node.id) &&
        (allNodes.value.find((n) => n.id === e.sourceNodeId)?.label ===
          highlightedNodeType.value ||
          allNodes.value.find((n) => n.id === e.targetNodeId)?.label ===
            highlightedNodeType.value),
    );
  }

  if (highlightMode.value === 'nodeType' && highlightedNodeType.value) {
    return node.label === highlightedNodeType.value;
  }
  if (highlightMode.value === 'relationType' && highlightedRelationType.value) {
    return allEdges.value.some(
      (e) =>
        e.relationType === highlightedRelationType.value &&
        (e.sourceNodeId === node.id || e.targetNodeId === node.id),
    );
  }
  if (highlightMode.value === 'search' && searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase();
    return (
      node.name.toLowerCase().includes(keyword) ||
      node.id.toLowerCase().includes(keyword)
    );
  }
  return false;
};

// 获取节点透明度
const getNodeOpacity = (node: GraphNode): number => {
  if (highlightMode.value === 'none') return 1;

  // 单个节点高亮模式
  if (highlightMode.value === 'singleNode' && highlightedSingleNodeId.value) {
    if (node.id === highlightedSingleNodeId.value) return 1;
    const isConnected = allEdges.value.some(
      (e) =>
        (e.sourceNodeId === highlightedSingleNodeId.value &&
          e.targetNodeId === node.id) ||
        (e.targetNodeId === highlightedSingleNodeId.value &&
          e.sourceNodeId === node.id),
    );
    return isConnected ? 1 : 0.15;
  }

  // 组合模式
  if (
    highlightMode.value === 'combined' &&
    highlightedNodeType.value &&
    highlightedRelationType.value
  ) {
    // 选中类型的节点
    if (node.label === highlightedNodeType.value) return 1;
    // 该关系类型边连接的节点（且边的另一端是选中类型）
    const isConnected = allEdges.value.some(
      (e) =>
        e.relationType === highlightedRelationType.value &&
        ((e.sourceNodeId === node.id &&
          allNodes.value.find((n) => n.id === e.targetNodeId)?.label ===
            highlightedNodeType.value) ||
          (e.targetNodeId === node.id &&
            allNodes.value.find((n) => n.id === e.sourceNodeId)?.label ===
              highlightedNodeType.value)),
    );
    return isConnected ? 1 : 0.15;
  }

  if (highlightMode.value === 'nodeType' && highlightedNodeType.value) {
    return node.label === highlightedNodeType.value ? 1 : 0.15;
  }
  if (highlightMode.value === 'relationType' && highlightedRelationType.value) {
    const isConnected = allEdges.value.some(
      (e) =>
        e.relationType === highlightedRelationType.value &&
        (e.sourceNodeId === node.id || e.targetNodeId === node.id),
    );
    return isConnected ? 1 : 0.15;
  }
  if (highlightMode.value === 'search' && searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase();
    const matches =
      node.name.toLowerCase().includes(keyword) ||
      node.id.toLowerCase().includes(keyword);
    return matches ? 1 : 0.15;
  }
  return 1;
};

// 获取边高亮状态
const getEdgeHighlightState = (edge: GraphEdge): boolean => {
  // 单个节点高亮模式：高亮与该节点直接连接的所有边
  if (highlightMode.value === 'singleNode' && highlightedSingleNodeId.value) {
    return (
      edge.sourceNodeId === highlightedSingleNodeId.value ||
      edge.targetNodeId === highlightedSingleNodeId.value
    );
  }

  // 组合模式：Node 类型 + Relation 类型
  if (
    highlightMode.value === 'combined' &&
    highlightedNodeType.value &&
    highlightedRelationType.value
  ) {
    if (edge.relationType !== highlightedRelationType.value) return false;
    // 边的 source 或 target 必须是选中的节点类型
    const sourceNode = allNodes.value.find((n) => n.id === edge.sourceNodeId);
    const targetNode = allNodes.value.find((n) => n.id === edge.targetNodeId);
    return (
      sourceNode?.label === highlightedNodeType.value ||
      targetNode?.label === highlightedNodeType.value
    );
  }

  if (highlightMode.value === 'relationType' && highlightedRelationType.value) {
    return edge.relationType === highlightedRelationType.value;
  }
  if (highlightMode.value === 'nodeType' && highlightedNodeType.value) {
    const sourceNode = allNodes.value.find((n) => n.id === edge.sourceNodeId);
    const targetNode = allNodes.value.find((n) => n.id === edge.targetNodeId);
    return (
      sourceNode?.label === highlightedNodeType.value ||
      targetNode?.label === highlightedNodeType.value
    );
  }
  return false;
};

// 获取边透明度
const getEdgeOpacity = (edge: GraphEdge): number => {
  if (highlightMode.value === 'none') return 0.6;

  // 单个节点高亮模式
  if (highlightMode.value === 'singleNode' && highlightedSingleNodeId.value) {
    const isConnected =
      edge.sourceNodeId === highlightedSingleNodeId.value ||
      edge.targetNodeId === highlightedSingleNodeId.value;
    return isConnected ? 1 : 0.08;
  }

  // 组合模式
  if (
    highlightMode.value === 'combined' &&
    highlightedNodeType.value &&
    highlightedRelationType.value
  ) {
    if (edge.relationType !== highlightedRelationType.value) return 0.08;
    const sourceNode = allNodes.value.find((n) => n.id === edge.sourceNodeId);
    const targetNode = allNodes.value.find((n) => n.id === edge.targetNodeId);
    const isConnected =
      sourceNode?.label === highlightedNodeType.value ||
      targetNode?.label === highlightedNodeType.value;
    return isConnected ? 1 : 0.08;
  }

  if (highlightMode.value === 'relationType' && highlightedRelationType.value) {
    return edge.relationType === highlightedRelationType.value ? 1 : 0.08;
  }
  if (highlightMode.value === 'nodeType' && highlightedNodeType.value) {
    const sourceNode = allNodes.value.find((n) => n.id === edge.sourceNodeId);
    const targetNode = allNodes.value.find((n) => n.id === edge.targetNodeId);
    const isConnected =
      sourceNode?.label === highlightedNodeType.value ||
      targetNode?.label === highlightedNodeType.value;
    return isConnected ? 0.8 : 0.08;
  }
  if (highlightMode.value === 'search' && searchKeyword.value) {
    return 0.15;
  }
  return 0.6;
};

// 获取节点大小（人设突出，其他维度次之，业务节点正常）
const getNodeSize = (label: NodeLabel | string): number => {
  const base = nodeSize.value;
  switch (label) {
    case 'DIM_EMOTION':
    case 'DIM_LANG':
    case 'DIM_MOTIVE': {
      return base * 1.1;
    } // 其他维度稍大
    case 'DIM_IDENTITY': {
      return base * 2;
    } // 人设最大，突出重要性
    case 'PERSONA_ROOT': {
      return base * 1.4;
    }
    default: {
      return base;
    } // 场景、痛点、卖点、语料正常大小
  }
};

// 获取节点图标
const getNodeIcon = (label: NodeLabel | string): string => {
  const iconMap: Record<string, string> = {
    PERSONA_ROOT: '👥',
    DIM_IDENTITY: '👤',
    DIM_EMOTION: '💭',
    DIM_MOTIVE: '🎯',
    DIM_LANG: '💬',
    SCENE: '🌍',
    PAIN: '⚡',
    FEATURE: '⭐',
    FEATURE_CORPUS: '📝',
  };
  return iconMap[label] || '●';
};

// 获取布局配置
const getLayoutConfig = (type: string) => {
  const configs: Record<string, object> = {
    circular: {
      type: 'circular',
      radius: 280,
      startAngle: 0,
      endAngle: 2 * Math.PI,
      clockwise: true,
    },
    radial: {
      type: 'radial',
      unitRadius: 80,
      linkDistance: 150,
      preventOverlap: true,
    },
    dagre: {
      type: 'dagre',
      rankdir: 'TB',
      nodesep: 40,
      ranksep: 60,
    },
    concentric: {
      type: 'concentric',
      minNodeSpacing: 50,
      preventOverlap: true,
      sortBy: 'degree',
    },
  };
  return configs[type] || configs.circular;
};

// =============================================
// 数据加载
// =============================================

const fetchGraphData = async () => {
  loading.value = true;
  try {
    // 使用新的可视化 API，后端已根据 min_degree 过滤并关联节点和边
    // 默认只加载 500 个节点，保证流畅性
    const res = await getGraphVisualizationApi({
      tenant_code: 'default',
      min_degree: minDegree.value,
      limit: 500,
    });

    // 简化数据映射，只保留必要字段
    allNodes.value = res.nodes.map((item) => ({
      id: item.id,
      tenant_code: item.tenant_code,
      label: item.label,
      name: item.name,
      description: item.description,
      is_active: item.is_active,
      is_deleted: item.is_deleted,
    })) as any;

    allEdges.value = res.edges.map((item) => ({
      id: item.id,
      source_node_id: item.source_node_id,
      target_node_id: item.target_node_id,
      relation_type: item.relation_type,
      source_name: item.source_name,
      target_name: item.target_name,
      is_active: item.is_active,
      is_deleted: item.is_deleted,
      weight: item.meta_data?.weight || 1,
    })) as any;

    // 数据加载完成
  } catch (error) {
    console.error(error);
    message.error('加载图数据失败');
  } finally {
    loading.value = false;
  }
};

// =============================================
// 图操作
// =============================================
const initGraph = async () => {
  if (!containerRef.value) {
    console.warn('Graph container not ready');
    return;
  }

  await fetchGraphData();

  // 再次检查容器是否仍然存在（可能在 await 期间组件被卸载）
  if (!containerRef.value) {
    console.warn('Graph container destroyed during data fetch');
    return;
  }

  try {
    const { nodes, edges } = buildGraphData();

    // 如果没有数据，不初始化图
    if (nodes.length === 0) {
      console.warn('No nodes to display');
      return;
    }

    // 性能优化：根据数据量调整配置
    const isLargeDataset = nodes.length > 200;

    const graph = new Graph({
      container: containerRef.value,
      autoResize: true,
      data: { nodes, edges },
      layout: getLayoutConfig(selectedLayout.value) as any,
      node: {
        type: 'circle',
        style: { size: nodeSize.value },
        state: {
          selected: { lineWidth: 2 },
          highlight: { lineWidth: 2 },
        },
      },
      edge: {
        // 大数据量时使用直线（line）而非曲线（quadratic），性能更好
        type: isLargeDataset ? 'line' : 'quadratic',
        style: { endArrow: !isLargeDataset },
        state: {
          selected: { lineWidth: 2, opacity: 1 },
          highlight: { lineWidth: 2, opacity: 1 },
        },
      },
      behaviors: [
        'drag-canvas',
        'zoom-canvas',
        // 大数据量时禁用拖拽节点（性能开销大）
        ...(isLargeDataset ? [] : ['drag-element']),
        // 大数据量时禁用悬停高亮（性能开销大）
        ...(isLargeDataset
          ? []
          : [
              {
                type: 'hover-activate',
                degree: 1,
                state: 'highlight',
                inactiveState: 'dim',
              },
            ]),
        'click-select',
      ],
      plugins: [
        // 大数据量时禁用小地图
        ...(isLargeDataset
          ? []
          : [
              {
                type: 'minimap',
                size: [140, 90],
                position: 'right-bottom',
              },
            ]),
      ],
      // 大数据量时禁用动画
      animation: !isLargeDataset,
      background: isDarkMode.value ? '#0a0a0a' : '#f8f9fa',
    });

    // 节点点击事件
    graph.on('node:click', (evt: any) => {
      const nodeId = evt.target.id;
      const nodeData = allNodes.value.find((n) => n.id === nodeId);
      if (nodeData) {
        selectedNode.value = nodeData;
        selectedNodeEdges.value = {
          incoming: allEdges.value.filter(
            (e: any) => e.targetNodeId === nodeId && e.is_active === 1,
          ),
          outgoing: allEdges.value.filter(
            (e: any) => e.sourceNodeId === nodeId && e.is_active === 1,
          ),
        };
        drawerVisible.value = true;
      }
    });

    // 双击节点：高亮该节点及其直接关系
    graph.on('node:dblclick', (evt: any) => {
      const nodeId = evt.target.id;
      handleSingleNodeHighlight(nodeId);
    });

    await graph.render();
    graphInstance.value = graph;
  } catch (error) {
    console.error('Graph initialization error:', error);
    message.error('图渲染失败');
  }
};

const updateGraph = async () => {
  if (!graphInstance.value) {
    await initGraph();
    return;
  }

  loading.value = true;
  try {
    const { nodes, edges } = buildGraphData();
    graphInstance.value.setData({ nodes, edges });
    await graphInstance.value.draw();
  } finally {
    loading.value = false;
  }
};

const relayoutGraph = async () => {
  if (!graphInstance.value) return;
  loading.value = true;
  try {
    graphInstance.value.setLayout(getLayoutConfig(selectedLayout.value) as any);
    await graphInstance.value.layout();
  } finally {
    loading.value = false;
  }
};

// =============================================
// 高亮交互
// =============================================
const handleNodeTypeClick = (label: NodeLabel) => {
  // 清除单节点高亮
  highlightedSingleNodeId.value = null;

  if (highlightedNodeType.value === label) {
    // 取消高亮
    highlightedNodeType.value = null;
    highlightedRelationType.value = null;
    highlightMode.value = 'none';
  } else {
    // 高亮该类型（保留之前的关系类型，进入组合模式）
    highlightedNodeType.value = label;
    highlightMode.value = highlightedRelationType.value
      ? 'combined'
      : 'nodeType';
  }
  updateGraph();
};

const handleRelationTypeClick = (type: RelationType) => {
  if (
    highlightedRelationType.value === type &&
    highlightMode.value === 'combined'
  ) {
    // 取消关系高亮，回到纯节点类型高亮
    highlightedRelationType.value = null;
    highlightMode.value = 'nodeType';
  } else if (
    highlightedRelationType.value === type &&
    highlightMode.value === 'relationType'
  ) {
    // 取消高亮
    highlightedRelationType.value = null;
    highlightMode.value = 'none';
  } else if (highlightedNodeType.value) {
    // 已选中节点类型，进入组合模式
    highlightedRelationType.value = type;
    highlightMode.value = 'combined';
  } else {
    // 未选中节点类型，提示用户
    message.info('请先选择一个节点类型，再选择关系类型进行组合筛选');
    return;
  }
  updateGraph();
};

const handleSearchSelect = (nodeId: string) => {
  const node = allNodes.value.find((n) => n.id === nodeId);
  if (node && graphInstance.value) {
    // 聚焦到节点
    graphInstance.value.focusElement(nodeId, { padding: 100 } as any);

    // 高亮搜索模式
    highlightMode.value = 'search';
    highlightedNodeType.value = null;
    highlightedRelationType.value = null;
    highlightedSingleNodeId.value = null;
    updateGraph();

    // 显示详情
    selectedNode.value = node;
    selectedNodeEdges.value = {
      incoming: allEdges.value.filter(
        (e: any) => e.targetNodeId === nodeId && e.is_active === 1,
      ),
      outgoing: allEdges.value.filter(
        (e: any) => e.sourceNodeId === nodeId && e.is_active === 1,
      ),
    };
    drawerVisible.value = true;
  }
};

// 高亮单个节点及其直接关系
const handleSingleNodeHighlight = (nodeId: string) => {
  if (highlightedSingleNodeId.value === nodeId) {
    // 取消高亮
    highlightedSingleNodeId.value = null;
    highlightMode.value = 'none';
  } else {
    // 高亮该节点及其关系
    highlightedSingleNodeId.value = nodeId;
    highlightedNodeType.value = null;
    highlightedRelationType.value = null;
    highlightMode.value = 'singleNode';
  }
  updateGraph();
};

const clearHighlight = () => {
  highlightMode.value = 'none';
  highlightedNodeType.value = null;
  highlightedRelationType.value = null;
  highlightedSingleNodeId.value = null;
  searchKeyword.value = '';
  updateGraph();
};

// =============================================
// 工具操作
// =============================================
const handleZoomIn = () => graphInstance.value?.zoomBy(1.3);
const handleZoomOut = () => graphInstance.value?.zoomBy(0.7);
const handleFitView = () => graphInstance.value?.fitView();
const handleRefresh = () => {
  clearHighlight();
  relayoutGraph();
  message.success('已刷新');
};

const handleDownload = () => {
  graphInstance.value?.toDataURL({ type: 'image/png' }).then((dataUrl) => {
    const link = document.createElement('a');
    link.download = `knowledge-graph-${Date.now()}.png`;
    link.href = dataUrl;
    link.click();
    message.success('图片已下载');
  });
};

const toggleFullscreen = () => {
  isFullscreen.value = !isFullscreen.value;
  nextTick(() => {
    graphInstance.value?.fitView();
  });
};

const toggleDarkMode = () => {
  isDarkMode.value = !isDarkMode.value;
  if (graphInstance.value) {
    graphInstance.value.setOptions({
      background: isDarkMode.value ? '#0a0a0a' : '#f8f9fa',
    });
    updateGraph();
  }
};

// =============================================
// 监听器
// =============================================
watch(selectedLayout, relayoutGraph);
watch([showLabels, nodeSize], updateGraph);

// minDegree 变化时重新加载数据（后端过滤）- 使用防抖
let minDegreeTimer: null | ReturnType<typeof setTimeout> = null;
watch(minDegree, () => {
  if (minDegreeTimer) clearTimeout(minDegreeTimer);
  minDegreeTimer = setTimeout(async () => {
    await fetchGraphData();
    updateGraph();
  }, 500); // 500ms 防抖
});

watch(searchKeyword, (val) => {
  if (val) {
    highlightMode.value = 'search';
    highlightedNodeType.value = null;
    highlightedRelationType.value = null;
  } else if (highlightMode.value === 'search') {
    highlightMode.value = 'none';
  }
  updateGraph();
});

onMounted(async () => {
  await initGraph();
});
onUnmounted(() => graphInstance.value?.destroy());

// 辅助函数
// 默认节点配置（用于未定义的 label 类型）
const DEFAULT_LABEL_CONFIG = {
  label: 'UNKNOWN',
  displayName: '未知类型',
  description: '未定义的节点类型',
  color: '#8c8c8c',
  icon: 'QuestionOutlined',
};

const getLabelConfig = (label: NodeLabel | string) =>
  NODE_LABEL_CONFIG[label as NodeLabel] || DEFAULT_LABEL_CONFIG;
const getRelationConfig = (type: RelationType) => RELATION_TYPE_CONFIG[type];
</script>

<template>
  <div
    class="graph-view"
    :class="{ fullscreen: isFullscreen, dark: isDarkMode }"
  >
    <!-- 左侧控制面板 -->
    <div class="control-panel left-panel">
      <!-- 搜索框 -->
      <div class="panel-section">
        <div class="section-title"><SearchOutlined /> 搜索节点</div>
        <Input
          v-model:value="searchKeyword"
          placeholder="输入节点名称..."
          allow-clear
          size="small"
          class="search-input"
        >
          <template #prefix><SearchOutlined /></template>
        </Input>
        <div v-if="searchResults.length > 0" class="search-results">
          <div
            v-for="node in searchResults"
            :key="node.id"
            class="search-item"
            @click="handleSearchSelect(node.id)"
          >
            <span
              class="search-icon"
              :style="{ background: getLabelConfig(node.label).color }"
            >
              {{ getNodeIcon(node.label) }}
            </span>
            <span class="search-text">{{ node.name }}</span>
          </div>
        </div>
      </div>

      <!-- 节点类型 -->
      <div class="panel-section">
        <div class="section-title">
          <NodeIndexOutlined /> 节点类型
          <span class="section-hint">点击高亮</span>
        </div>
        <div class="type-list">
          <template v-for="(config, label) in NODE_LABEL_CONFIG" :key="label">
            <div
              v-if="label !== 'PERSONA_ROOT'"
              class="type-item"
              :class="{
                active: highlightedNodeType === label,
                dimmed:
                  highlightMode !== 'none' && highlightedNodeType !== label,
              }"
              @click="handleNodeTypeClick(label as NodeLabel)"
            >
              <span
                class="type-dot"
                :style="{ background: config.color }"
              ></span>
              <span class="type-name">{{ config.displayName }}</span>
              <Badge
                :count="nodeTypeStats[label as NodeLabel]?.count || 0"
                :number-style="{
                  backgroundColor:
                    highlightedNodeType === label ? config.color : '#666',
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

      <!-- 关系类型 -->
      <div class="panel-section">
        <div class="section-title">
          <BranchesOutlined /> 关系类型
          <span class="section-hint">点击高亮</span>
        </div>
        <div class="type-list relation-list">
          <div
            v-for="(config, type) in RELATION_TYPE_CONFIG"
            :key="type"
            class="type-item relation-item"
            :class="{
              active: highlightedRelationType === type,
              dimmed:
                highlightMode !== 'none' && highlightedRelationType !== type,
              conflict: type === 'CONFLICTS_WITH',
            }"
            @click="handleRelationTypeClick(type as RelationType)"
          >
            <span
              class="type-line"
              :style="{
                background: config.lineColor,
                borderStyle:
                  config.lineStyle === 'dashed' || type === 'CONFLICTS_WITH'
                    ? 'dashed'
                    : 'solid',
              }"
            ></span>
            <span class="type-name">{{ config.displayName }}</span>
            <Badge
              :count="relationTypeStats[type as RelationType]?.count || 0"
              :number-style="{
                backgroundColor:
                  highlightedRelationType === type ? config.lineColor : '#666',
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
      <div class="toolbar-left">
        <Select
          v-model:value="selectedLayout"
          :options="layoutOptions"
          style="width: 100px"
          size="small"
          :bordered="false"
        />
        <Divider type="vertical" />
        <span class="toolbar-label">标签</span>
        <Switch v-model:checked="showLabels" size="small" />
        <Divider type="vertical" />
        <span class="toolbar-label">节点</span>
        <Slider
          v-model:value="nodeSize"
          :min="24"
          :max="60"
          style="width: 60px"
          size="small"
        />
        <Divider type="vertical" />
        <Tooltip title="只展示边数 ≥ 该值的节点">
          <span class="toolbar-label">最小边数</span>
        </Tooltip>
        <Slider
          v-model:value="minDegree"
          :min="0"
          :max="20"
          style="width: 80px"
          size="small"
        />
        <span class="toolbar-value">{{ minDegree }}</span>
      </div>
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
        <Tooltip title="刷新布局">
          <Button type="text" size="small" @click="handleRefresh">
            <ReloadOutlined />
          </Button>
        </Tooltip>
        <Divider type="vertical" />
        <Tooltip title="切换主题">
          <Button type="text" size="small" @click="toggleDarkMode">
            <BgColorsOutlined />
          </Button>
        </Tooltip>
        <Tooltip title="下载图片">
          <Button type="text" size="small" @click="handleDownload">
            <DownloadOutlined />
          </Button>
        </Tooltip>
        <Tooltip :title="isFullscreen ? '退出全屏' : '全屏'">
          <Button type="text" size="small" @click="toggleFullscreen">
            <FullscreenExitOutlined v-if="isFullscreen" />
            <FullscreenOutlined v-else />
          </Button>
        </Tooltip>
      </div>
    </div>

    <!-- 高亮信息提示 -->
    <div v-if="highlightMode !== 'none'" class="highlight-info">
      <InfoCircleOutlined />
      <template
        v-if="highlightMode === 'singleNode' && highlightedSingleNodeId"
      >
        高亮显示: 节点「{{
          allNodes.find((n) => n.id === highlightedSingleNodeId)?.name
        }}」的直接关系
      </template>
      <template
        v-else-if="
          highlightMode === 'combined' &&
          highlightedNodeType &&
          highlightedRelationType
        "
      >
        高亮显示:
        <Tag :color="getLabelConfig(highlightedNodeType).color">
          {{ getLabelConfig(highlightedNodeType).displayName }}
        </Tag>
        +
        <Tag :color="getRelationConfig(highlightedRelationType).lineColor">
          {{ getRelationConfig(highlightedRelationType).displayName }}
        </Tag>
        组合筛选
      </template>
      <template v-else-if="highlightMode === 'nodeType' && highlightedNodeType">
        高亮显示:
        <Tag :color="getLabelConfig(highlightedNodeType).color">
          {{ getLabelConfig(highlightedNodeType).displayName }}
        </Tag>
        类型的 {{ nodeTypeStats[highlightedNodeType]?.count || 0 }} 个节点
        <span style="font-size: 12px; color: #888"
          >(可继续选择关系类型进行组合筛选)</span
        >
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
        搜索: "{{ searchKeyword }}" 匹配到 {{ searchResults.length }} 个节点
      </template>
      <Button type="link" size="small" @click="clearHighlight">清除</Button>
    </div>

    <!-- 图容器 -->
    <div ref="containerRef" class="graph-container">
      <div v-if="loading" class="loading-overlay">
        <div class="loading-spinner"></div>
        <div class="loading-text">渲染中...</div>
      </div>
    </div>

    <!-- 右下角统计信息 -->
    <div class="stats-panel">
      <div class="stats-item">
        <span class="stats-value">{{
          allNodes.filter((n: any) => n.is_active === 1).length
        }}</span>
        <span class="stats-label">节点</span>
      </div>
      <div class="stats-item">
        <span class="stats-value">{{
          allEdges.filter((e: any) => e.is_active === 1).length
        }}</span>
        <span class="stats-label">关系</span>
      </div>
    </div>

    <!-- 节点详情抽屉 -->
    <Drawer
      v-model:open="drawerVisible"
      title="节点详情"
      placement="right"
      :width="380"
      :header-style="{ background: isDarkMode ? '#1f1f1f' : '#fff' }"
      :body-style="{
        background: isDarkMode ? '#141414' : '#fff',
        padding: '16px',
      }"
      :class="{ 'dark-drawer': isDarkMode }"
    >
      <template v-if="selectedNode">
        <div class="node-detail-header">
          <div
            class="node-avatar"
            :style="{ background: getLabelConfig(selectedNode.label).color }"
          >
            {{ getNodeIcon(selectedNode.label) }}
          </div>
          <div class="node-info">
            <div class="node-name">{{ selectedNode.name }}</div>
            <Tag :color="getLabelConfig(selectedNode.label).color" size="small">
              {{ getLabelConfig(selectedNode.label).displayName }}
            </Tag>
          </div>
        </div>

        <div style="margin-top: 12px">
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
            <BranchesOutlined /> 高亮此节点的所有关系
          </Button>
        </div>

        <Divider style="margin: 16px 0" />

        <Descriptions :column="1" size="small" :label-style="{ color: '#888' }">
          <DescriptionsItem label="ID">
            <code class="code-text">{{ selectedNode.id }}</code>
          </DescriptionsItem>
          <DescriptionsItem label="状态">
            <Tag
              :color="
                (selectedNode as any).is_active === 1 ? 'green' : 'default'
              "
              size="small"
            >
              {{ (selectedNode as any).is_active === 1 ? '启用' : '禁用' }}
            </Tag>
          </DescriptionsItem>
        </Descriptions>

        <div class="section-divider">元数据</div>
        <pre class="meta-json">{{
          JSON.stringify(selectedNode.properties, null, 2)
        }}</pre>

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
            v-for="edge in selectedNodeEdges.outgoing"
            :key="`out-${edge.id}`"
            class="relation-item"
            :class="{ dark: isDarkMode }"
          >
            <div class="relation-item-content">
              <span class="relation-node-icon">📄</span>
              <span class="relation-node-name">{{ edge.targetName }}</span>
            </div>
            <span class="relation-type-tag">
              {{ edge.relationType }}
            </span>
          </div>

          <!-- 入边关联 -->
          <div
            v-for="edge in selectedNodeEdges.incoming"
            :key="`in-${edge.id}`"
            class="relation-item"
            :class="{ dark: isDarkMode }"
          >
            <div class="relation-item-content">
              <span class="relation-node-icon">📄</span>
              <span class="relation-node-name">{{ edge.sourceName }}</span>
            </div>
            <span class="relation-type-tag">
              {{ edge.relationType }}
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

.graph-view {
  position: relative;
  height: calc(100vh - 280px);
  min-height: 600px;
  overflow: hidden;
  background: #0a0a0a;
  border-radius: 12px;
  transition: all 0.3s ease;
}

.graph-view.fullscreen {
  position: fixed;
  inset: 0;
  z-index: 1000;
  height: 100vh;
  border-radius: 0;
}

.graph-view:not(.dark) {
  background: #f8f9fa;
}

/* =============================================
   左侧控制面板
   ============================================= */
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

.graph-view:not(.dark) .left-panel {
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

.graph-view:not(.dark) .section-title {
  color: #666;
}

/* 搜索框 */
.search-input {
  background: rgb(255 255 255 / 5%) !important;
  border-color: rgb(255 255 255 / 10%) !important;
  border-radius: 8px;
}

.search-input:focus,
.search-input:hover {
  border-color: #1890ff !important;
}

.graph-view:not(.dark) .search-input {
  background: rgb(0 0 0 / 2%) !important;
  border-color: rgb(0 0 0 / 10%) !important;
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

.graph-view:not(.dark) .search-item:hover {
  background: rgb(0 0 0 / 5%);
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

.graph-view:not(.dark) .search-text {
  color: #333;
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

.graph-view:not(.dark) .type-item:hover {
  background: rgb(0 0 0 / 4%);
}

.type-item.active {
  background: rgb(255 255 255 / 12%);
  border-color: rgb(255 255 255 / 20%);
}

.graph-view:not(.dark) .type-item.active {
  background: rgb(24 144 255 / 10%);
  border-color: rgb(24 144 255 / 30%);
}

.type-item.dimmed {
  opacity: 0.4;
}

.type-dot {
  flex-shrink: 0;
  width: 12px;
  height: 12px;
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

.graph-view:not(.dark) .type-name {
  color: #444;
}

.relation-item.conflict .type-name {
  color: #ff6b6b;
}

.clear-highlight {
  margin-top: 16px;
}

/* =============================================
   顶部工具栏
   ============================================= */
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

.graph-view:not(.dark) .top-toolbar {
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

/* =============================================
   高亮信息提示
   ============================================= */
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

/* =============================================
   图容器
   ============================================= */
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

/* =============================================
   统计面板
   ============================================= */
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

.graph-view:not(.dark) .stats-panel {
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

.graph-view:not(.dark) .stats-value {
  color: #1890ff;
}

.stats-label {
  margin-top: 4px;
  font-size: 11px;
  color: #666;
}

/* =============================================
   节点详情抽屉
   ============================================= */
.node-detail-header {
  display: flex;
  gap: 16px;
  align-items: center;
}

.node-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  font-size: 26px;
  border-radius: 14px;
  box-shadow: 0 4px 16px rgb(0 0 0 / 20%);
}

.node-info {
  flex: 1;
}

.node-name {
  margin-bottom: 8px;
  font-size: 18px;
  font-weight: 600;
  color: inherit;
}

.section-divider {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 16px 0 12px;
  font-size: 12px;
  font-weight: 600;
  color: #888;
}

.meta-json {
  max-height: 140px;
  padding: 12px;
  margin: 0;
  overflow: auto;
  font-family: Monaco, Menlo, monospace;
  font-size: 11px;
  color: #aaa;
  background: rgb(0 0 0 / 20%);
  border-radius: 8px;
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

.edge-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.edge-item {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 6px 8px;
  font-size: 12px;
  background: rgb(255 255 255 / 3%);
  border-radius: 6px;
}

.edge-arrow {
  color: #666;
}

.edge-source,
.edge-target {
  color: #aaa;
}

.code-text {
  padding: 2px 6px;
  font-family: Monaco, Menlo, monospace;
  font-size: 11px;
  background: rgb(0 0 0 / 20%);
  border-radius: 4px;
}

/* =============================================
   暗色抽屉样式覆盖
   ============================================= */
.dark-drawer :deep(.ant-drawer-header) {
  background: #1f1f1f;
  border-bottom-color: #333;
}

.dark-drawer :deep(.ant-drawer-title) {
  color: #fff;
}

.dark-drawer :deep(.ant-drawer-close) {
  color: #888;
}

.dark-drawer :deep(.ant-descriptions-item-label) {
  color: #888 !important;
}

.dark-drawer :deep(.ant-descriptions-item-content) {
  color: #ddd !important;
}

/* 小地图样式 */
.dark :deep(.g6-minimap) {
  background: rgb(0 0 0 / 60%) !important;
  border: 1px solid rgb(255 255 255 / 10%) !important;
  border-radius: 8px !important;
}

/* =============================================
   主容器
   ============================================= */
</style>
