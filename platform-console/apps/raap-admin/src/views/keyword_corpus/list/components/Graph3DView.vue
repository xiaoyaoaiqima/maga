<script setup lang="ts">
import type {
  CorpusItem,
  GraphEdge,
  GraphNode,
  NodeLabel,
  RelationType,
  StructuredCorpus,
} from '../types';

import { computed, onMounted, onUnmounted, ref, watch } from 'vue';

import { usePreferences } from '@vben/preferences';

import ForceGraph3D from '3d-force-graph';
import {
  AimOutlined,
  BranchesOutlined,
  CloseCircleOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  NodeIndexOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue';
import {
  Badge,
  Button,
  Divider,
  Drawer,
  Input,
  message,
  Tag,
  Tooltip,
} from 'ant-design-vue';
import { forceCollide } from 'd3-force-3d';
import * as THREE from 'three';
import SpriteText from 'three-spritetext';

import { getGraphVisualizationApi } from '#/api/core/graph-corpus';

import { NODE_LABEL_CONFIG, RELATION_TYPE_CONFIG } from '../types';

// =============================================
// 亮色/暗色双主题节点颜色配置
// =============================================
// 暗色模式：高饱和度、高亮度，在深色背景上醒目
const DARK_MODE_NODE_COLORS: Record<string, string> = {
  PERSONA_ROOT: '#a855f7', // 紫色
  DIM_IDENTITY: '#60a5fa', // 天蓝色
  DIM_EMOTION: '#fbbf24', // 琥珀色
  DIM_MOTIVE: '#4ade80', // 翠绿色
  DIM_LANG: '#2dd4bf', // 青色
  SCENE: '#f472b6', // 粉红色
  PAIN: '#f87171', // 珊瑚红
  FEATURE: '#facc15', // 金黄色
  FEATURE_CORPUS: '#a3e635', // 青柠色
};

// 亮色模式：稍低饱和度，在浅色背景上柔和但清晰
const LIGHT_MODE_NODE_COLORS: Record<string, string> = {
  PERSONA_ROOT: '#7c3aed', // 深紫色
  DIM_IDENTITY: '#2563eb', // 宝蓝色
  DIM_EMOTION: '#d97706', // 深琥珀
  DIM_MOTIVE: '#16a34a', // 森林绿
  DIM_LANG: '#0d9488', // 深青色
  SCENE: '#db2777', // 玫红色
  PAIN: '#dc2626', // 正红色
  FEATURE: '#ca8a04', // 深金色
  FEATURE_CORPUS: '#65a30d', // 橄榄绿
};

// 暗色模式动态调色板（用于未预定义的 label）
const DARK_DYNAMIC_PALETTE = [
  '#ff6b9d',
  '#67e8f9',
  '#a78bfa',
  '#86efac',
  '#fcd34d',
  '#f0abfc',
  '#6ee7b7',
  '#fca5a5',
  '#93c5fd',
  '#fdba74',
  '#c4b5fd',
  '#bef264',
];

// 亮色模式动态调色板
const LIGHT_DYNAMIC_PALETTE = [
  '#e11d48',
  '#0891b2',
  '#7c3aed',
  '#059669',
  '#ca8a04',
  '#c026d3',
  '#047857',
  '#dc2626',
  '#2563eb',
  '#ea580c',
  '#7c3aed',
  '#4d7c0f',
];

// 缓存已分配的动态颜色（按主题分开缓存）
const darkLabelColorCache = new Map<string, string>();
const lightLabelColorCache = new Map<string, string>();

// 根据 label 获取稳定的动态颜色
const getDynamicColor = (label: string, dark: boolean): string => {
  const cache = dark ? darkLabelColorCache : lightLabelColorCache;
  const palette = dark ? DARK_DYNAMIC_PALETTE : LIGHT_DYNAMIC_PALETTE;

  if (cache.has(label)) {
    return cache.get(label)!;
  }
  // 使用 label 字符串的 hash 来选择颜色，保证同一 label 总是得到相同颜色
  let hash = 0;
  for (let i = 0; i < label.length; i++) {
    hash = Math.trunc((hash << 5) - hash + (label.codePointAt(i) ?? 0));
  }
  const colorIndex = Math.abs(hash) % palette.length;
  const color = palette[colorIndex] as string;
  cache.set(label, color);
  return color;
};

// 暗色/亮色关系线颜色
const DARK_MODE_RELATION_COLORS: Record<string, string> = {
  INCLUDES: '#a78bfa',
  FITS_WITH: '#4ade80',
  CONFLICTS_WITH: '#f87171',
  ENCOUNTERS: '#f472b6',
  LEADS_TO: '#fbbf24',
  FIXES: '#60a5fa',
  SAYS_AS: '#2dd4bf',
};

const LIGHT_MODE_RELATION_COLORS: Record<string, string> = {
  INCLUDES: '#7c3aed',
  FITS_WITH: '#16a34a',
  CONFLICTS_WITH: '#dc2626',
  ENCOUNTERS: '#db2777',
  LEADS_TO: '#d97706',
  FIXES: '#2563eb',
  SAYS_AS: '#0d9488',
};

// =============================================
// 状态定义（需要先定义 isDark 才能在颜色函数中使用）
// =============================================
const containerRef = ref<HTMLDivElement | null>(null);
let graphInstance: any = null;
const isFullscreen = ref(false);
const { isDark } = usePreferences();
const showLabels = ref(true);
// 是否在 3D 图上常驻显示节点名称文本（非 hover 提示）
const showNodeLabelText = ref(true);
const nodeSize = ref(8);
const linkWidth = ref(1);
const isRotating = ref(false); // 默认关闭自动旋转，用户可自由拖动视角
const searchKeyword = ref('');
const loading = ref(false);
const isGraphReady = ref(false); // 图谱是否初始化完成
const webglError = ref<null | string>(null); // WebGL 错误信息

// =============================================
// 主题感知的颜色获取函数
// =============================================
// 获取节点颜色：根据当前主题返回对应颜色
const getNodeColor = (label: string): string => {
  const colorMap = isDark.value
    ? DARK_MODE_NODE_COLORS
    : LIGHT_MODE_NODE_COLORS;
  if (colorMap[label]) {
    return colorMap[label];
  }
  // 未预定义的 label 使用动态颜色
  return getDynamicColor(label, isDark.value);
};

// 获取关系颜色：根据当前主题返回对应颜色
const getRelationColor = (type: string): string => {
  const colorMap = isDark.value
    ? DARK_MODE_RELATION_COLORS
    : LIGHT_MODE_RELATION_COLORS;
  if (colorMap[type]) {
    return colorMap[type];
  }
  // 未预定义的关系类型使用动态颜色
  return getDynamicColor(type, isDark.value);
};

// 获取节点显示名称：优先使用预定义配置，否则使用原始 label
const getNodeDisplayName = (label: string): string => {
  const config = NODE_LABEL_CONFIG[label as NodeLabel];
  return config?.displayName || label;
};

// 获取节点图标：优先使用预定义配置，否则使用默认图标
const getNodeIcon = (label: string): string => {
  const config = NODE_LABEL_CONFIG[label as NodeLabel];
  return config?.icon || '📌';
};

// 获取关系显示名称：优先使用预定义配置，否则使用原始 type
const getRelationDisplayName = (type: string): string => {
  const config = RELATION_TYPE_CONFIG[type as RelationType];
  return config?.displayName || type;
};

// =============================================
// 语料展示辅助函数
// =============================================

// 判断是否为结构化语料（单个对象）
const isStructuredCorpus = (corpus: unknown): corpus is StructuredCorpus => {
  return (
    corpus !== null &&
    typeof corpus === 'object' &&
    !Array.isArray(corpus) &&
    'template_code' in (corpus as Record<string, unknown>) &&
    'fields' in (corpus as Record<string, unknown>)
  );
};

// 判断是否为结构化语料数组（数组中每个元素都是结构化语料）
const isStructuredCorpusArray = (
  corpus: unknown,
): corpus is StructuredCorpus[] => {
  return (
    Array.isArray(corpus) &&
    corpus.length > 0 &&
    typeof corpus[0] === 'object' &&
    'template_code' in (corpus[0] as Record<string, unknown>) &&
    'fields' in (corpus[0] as Record<string, unknown>)
  );
};

// 判断是否为传统语料列表（数组中每个元素有 text 字段）
const isCorpusItemArray = (corpus: unknown): corpus is CorpusItem[] => {
  return (
    Array.isArray(corpus) &&
    corpus.length > 0 &&
    typeof corpus[0] === 'object' &&
    'text' in (corpus[0] as Record<string, unknown>)
  );
};

// 检查节点是否有语料
const hasCorpus = (node: GraphNode | null): boolean => {
  if (!node?.corpus) return false;
  if (isStructuredCorpus(node.corpus)) return true;
  if (isStructuredCorpusArray(node.corpus)) return true;
  if (isCorpusItemArray(node.corpus)) return node.corpus.length > 0;
  return false;
};

// 检查节点是否有属性
const hasProperties = (node: GraphNode | null): boolean => {
  if (!node?.properties) return false;
  return Object.keys(node.properties).length > 0;
};

// 格式化属性值
const formatPropertyValue = (value: unknown): string => {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value);
};

// 判断是否为简单值（可以直接单行展示）
const isSimpleValue = (value: unknown): boolean => {
  if (value === null || value === undefined) return true;
  if (typeof value === 'boolean') return true;
  if (typeof value === 'number') return true;
  if (typeof value === 'string') return value.length < 30;
  return false;
};

// =============================================
// THREE.js 对象缓存（防止内存泄漏）
// =============================================
// 缓存几何体（按尺寸缓存）
const sphereGeometryCache = new Map<number, THREE.SphereGeometry>();
const ringGeometryCache = new Map<string, THREE.RingGeometry>();

// 缓存材质（按颜色+透明度缓存）
const materialCache = new Map<string, THREE.MeshBasicMaterial>();

// 【关键】缓存节点的 THREE.js 对象，避免重复创建
// key: nodeId, value: THREE.Group
const nodeThreeObjectCache = new Map<string, THREE.Group>();

// 【关键】缓存 SpriteText 纹理，避免 Canvas 纹理爆炸
const spriteTextCache = new Map<string, any>();

// 【关键】缓存“节点名称文本”的 SpriteMaterial（按文本复用贴图，避免每节点一张纹理）
const labelTextSpriteMaterialCache = new Map<string, THREE.SpriteMaterial>();

// 已创建的 THREE.js 对象列表（用于清理）
const createdObjects: THREE.Object3D[] = [];

function create_label_text_sprite_material(params: {
  isDark: boolean;
  text: string;
}): THREE.SpriteMaterial {
  const fontSize = 48;
  const paddingX = 22;
  const paddingY = 14;

  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  if (!ctx) {
    return new THREE.SpriteMaterial({ transparent: true, opacity: 0 });
  }

  ctx.font = `700 ${fontSize}px system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial`;
  const metrics = ctx.measureText(params.text);
  const textWidth = Math.ceil(metrics.width);
  const textHeight = Math.ceil(fontSize * 1.1);

  canvas.width = textWidth + paddingX * 2;
  canvas.height = textHeight + paddingY * 2;

  // resize 之后要重新设置
  ctx.font = `700 ${fontSize}px system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial`;
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'center';

  const w = canvas.width;
  const h = canvas.height;
  const radius = Math.min(18, Math.floor(h / 2));

  const bg = params.isDark ? 'rgba(0,0,0,0.55)' : 'rgba(0,0,0,0.50)';
  const stroke = params.isDark
    ? 'rgba(255,255,255,0.25)'
    : 'rgba(255,255,255,0.30)';
  const fg = '#ffffff';

  // rounded rect
  ctx.beginPath();
  ctx.moveTo(radius, 0);
  ctx.lineTo(w - radius, 0);
  ctx.quadraticCurveTo(w, 0, w, radius);
  ctx.lineTo(w, h - radius);
  ctx.quadraticCurveTo(w, h, w - radius, h);
  ctx.lineTo(radius, h);
  ctx.quadraticCurveTo(0, h, 0, h - radius);
  ctx.lineTo(0, radius);
  ctx.quadraticCurveTo(0, 0, radius, 0);
  ctx.closePath();

  ctx.fillStyle = bg;
  ctx.fill();
  ctx.strokeStyle = stroke;
  ctx.lineWidth = 4;
  ctx.stroke();

  ctx.fillStyle = fg;
  ctx.fillText(params.text, w / 2, h / 2);

  const texture = new THREE.CanvasTexture(canvas);
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;

  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthTest: false, // 文本优先可见
    depthWrite: false,
  });
  (material as any).userData = { isLabelTextMaterial: true, aspect: w / h };
  return material;
}

function get_or_create_label_text_material(text: string): THREE.SpriteMaterial {
  const safeText = String(text ?? '').trim() || '-';
  const key = `${safeText}__${isDark.value ? 'dark' : 'light'}`;
  const cached = labelTextSpriteMaterialCache.get(key);
  if (cached) return cached;
  const material = create_label_text_sprite_material({
    text: safeText,
    isDark: isDark.value,
  });
  labelTextSpriteMaterialCache.set(key, material);
  return material;
}

// 获取或创建球体几何体（缓存复用）
function getOrCreateSphereGeometry(size: number): THREE.SphereGeometry {
  // 将尺寸四舍五入到一位小数，减少缓存数量
  const key = Math.round(size * 10) / 10;
  let geometry = sphereGeometryCache.get(key);
  if (!geometry) {
    // 使用 8x8 分段数，大幅减少顶点数（原来是 16x16 = 256 顶点，现在是 8x8 = 64 顶点）
    geometry = new THREE.SphereGeometry(key, 8, 8);
    sphereGeometryCache.set(key, geometry);
  }
  return geometry;
}

// 获取或创建光环几何体
function getOrCreateRingGeometry(
  inner: number,
  outer: number,
): THREE.RingGeometry {
  const key = `${Math.round(inner * 10)}_${Math.round(outer * 10)}`;
  let geometry = ringGeometryCache.get(key);
  if (!geometry) {
    // 使用 16 分段（原来是 32）
    geometry = new THREE.RingGeometry(inner, outer, 16);
    ringGeometryCache.set(key, geometry);
  }
  return geometry;
}

// 获取或创建材质
function getOrCreateMaterial(
  colorHex: string,
  opacity: number,
  doubleSide = false,
): THREE.MeshBasicMaterial {
  const key = `${colorHex}_${Math.round(opacity * 100)}_${doubleSide}`;
  let material = materialCache.get(key);
  if (!material) {
    material = new THREE.MeshBasicMaterial({
      color: new THREE.Color(colorHex),
      transparent: true,
      opacity,
      side: doubleSide ? THREE.DoubleSide : THREE.FrontSide,
    });
    materialCache.set(key, material);
  }
  return material;
}

// 清理所有缓存的 THREE.js 对象
function disposeThreeResources() {
  // 清理几何体
  sphereGeometryCache.forEach((g) => g.dispose());
  sphereGeometryCache.clear();

  ringGeometryCache.forEach((g) => g.dispose());
  ringGeometryCache.clear();

  // 清理材质
  materialCache.forEach((m) => m.dispose());
  materialCache.clear();

  // 【关键】清理节点 THREE.js 对象缓存
  nodeThreeObjectCache.forEach((group) => {
    group.traverse((child) => {
      if (child instanceof THREE.Mesh) {
        // 不 dispose 几何体和材质，因为它们可能被缓存复用
      }
      // 清理 SpriteText 的纹理
      if ((child as any).material?.map) {
        (child as any).material.map.dispose();
      }
    });
  });
  nodeThreeObjectCache.clear();

  // 【关键】清理 SpriteText 缓存
  spriteTextCache.forEach((sprite) => {
    if (sprite?.material?.map) {
      sprite.material.map.dispose();
    }
    if (sprite?.material) {
      sprite.material.dispose();
    }
  });
  spriteTextCache.clear();

  // 【关键】清理“节点 label 文本”材质缓存
  labelTextSpriteMaterialCache.forEach((m) => {
    if (m.map) m.map.dispose();
    m.dispose();
  });
  labelTextSpriteMaterialCache.clear();

  // 清理已创建的对象
  createdObjects.forEach((obj) => {
    if (obj instanceof THREE.Mesh) {
      obj.geometry?.dispose();
      if (Array.isArray(obj.material)) {
        obj.material.forEach((m) => m.dispose());
      } else {
        obj.material?.dispose();
      }
    }
  });
  createdObjects.length = 0;
}

// 检测 WebGL 是否可用
function checkWebGLSupport(): { error?: string; supported: boolean } {
  try {
    const canvas = document.createElement('canvas');
    const gl =
      canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    if (!gl) {
      return {
        supported: false,
        error: 'WebGL 不可用。请检查浏览器设置或尝试其他浏览器。',
      };
    }
    return { supported: true };
  } catch {
    return {
      supported: false,
      error: 'WebGL 初始化失败。请尝试启用浏览器的硬件加速功能。',
    };
  }
}

// 数据状态
const allNodes = ref<GraphNode[]>([]);
const allEdges = ref<GraphEdge[]>([]);

// Hover 状态
const hoveredNodeId = ref<null | string>(null);

// 动画相关
let animationFrameId: null | number = null;

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

// =============================================
// 子图模式（聚焦探索）
// =============================================
const subgraphMode = ref(false); // 是否处于子图模式
const subgraphCenterNodeId = ref<null | string>(null); // 子图中心节点 ID
const subgraphHops = ref(1); // 显示几跳邻居（1-3）
const subgraphNodeIds = ref<Set<string>>(new Set()); // 子图中的节点 ID 集合

// 边及其关联节点信息
interface EdgeWithNode {
  edge: GraphEdge;
  node: GraphNode | null; // 关联的节点（出边：目标节点，入边：源节点）
}

// 节点详情抽屉
const drawerVisible = ref(false);
const selectedNode = ref<GraphNode | null>(null);
const selectedNodeEdges = ref<{
  incoming: EdgeWithNode[];
  outgoing: EdgeWithNode[];
}>({
  incoming: [],
  outgoing: [],
});

// =============================================
// 计算属性
// =============================================

// 从实际数据中动态获取节点类型统计（不依赖硬编码配置）
const nodeTypeStats = computed(() => {
  const stats: Record<
    string,
    { active: boolean; color: string; count: number; displayName: string }
  > = {};
  const activeNodes = allNodes.value.filter(
    (n) => n.isDeleted === 0 && n.status === 1,
  );

  // 从实际数据中收集所有 label
  for (const node of activeNodes) {
    const label = node.label;
    if (!stats[label]) {
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

// 从实际数据中动态获取关系类型统计（不依赖硬编码配置）
const relationTypeStats = computed(() => {
  const stats: Record<
    string,
    { active: boolean; color: string; count: number; displayName: string }
  > = {};
  const activeEdges = allEdges.value.filter(
    (e) => e.isDeleted === 0 && e.status === 1,
  );

  // 从实际数据中收集所有 relationType
  for (const edge of activeEdges) {
    const type = edge.relationType;
    if (!stats[type]) {
      stats[type] = {
        count: 0,
        active: highlightedRelationType.value === type,
        color: getRelationColor(type),
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

const searchResults = computed(() => {
  if (!searchKeyword.value) return [];
  const keyword = searchKeyword.value.toLowerCase();
  return allNodes.value
    .filter((n) => n.isDeleted === 0 && n.status === 1)
    .filter(
      (n) =>
        n.name.toLowerCase().includes(keyword) ||
        n.id.toLowerCase().includes(keyword),
    )
    .slice(0, 10);
});

// 计算节点度数（连接数）
const nodeDegreeMap = computed(() => {
  const map = new Map<string, number>();
  const activeEdges = allEdges.value.filter(
    (e) => e.isDeleted === 0 && e.status === 1,
  );
  for (const edge of activeEdges) {
    map.set(edge.sourceNodeId, (map.get(edge.sourceNodeId) || 0) + 1);
    map.set(edge.targetNodeId, (map.get(edge.targetNodeId) || 0) + 1);
  }
  return map;
});

// =============================================
// 子图计算（N 跳邻居）
// =============================================

/**
 * 计算从中心节点出发的 N 跳邻居节点集合
 * @param centerNodeId 中心节点 ID
 * @param hops 跳数（1-3）
 * @returns 包含中心节点及其 N 跳邻居的节点 ID 集合
 */
const computeNHopNeighbors = (
  centerNodeId: string,
  hops: number,
): Set<string> => {
  const result = new Set<string>([centerNodeId]);
  const activeEdges = allEdges.value.filter(
    (e) => e.isDeleted === 0 && e.status === 1,
  );

  // 构建邻接表
  const adjacency = new Map<string, Set<string>>();
  for (const edge of activeEdges) {
    if (!adjacency.has(edge.sourceNodeId)) {
      adjacency.set(edge.sourceNodeId, new Set());
    }
    if (!adjacency.has(edge.targetNodeId)) {
      adjacency.set(edge.targetNodeId, new Set());
    }
    adjacency.get(edge.sourceNodeId)!.add(edge.targetNodeId);
    adjacency.get(edge.targetNodeId)!.add(edge.sourceNodeId);
  }

  // BFS 遍历 N 跳
  let currentLevel = new Set<string>([centerNodeId]);
  for (let hop = 0; hop < hops; hop++) {
    const nextLevel = new Set<string>();
    for (const nodeId of currentLevel) {
      const neighbors = adjacency.get(nodeId);
      if (neighbors) {
        for (const neighbor of neighbors) {
          if (!result.has(neighbor)) {
            nextLevel.add(neighbor);
            result.add(neighbor);
          }
        }
      }
    }
    currentLevel = nextLevel;
    if (currentLevel.size === 0) break; // 没有更多邻居了
  }

  return result;
};

/**
 * 进入子图模式
 */
const enterSubgraphMode = (centerNodeId: string) => {
  subgraphMode.value = true;
  subgraphCenterNodeId.value = centerNodeId;
  subgraphNodeIds.value = computeNHopNeighbors(
    centerNodeId,
    subgraphHops.value,
  );
  updateGraph();

  // 延迟重置相机位置，等待图重建和力导向布局稳定
  setTimeout(() => {
    if (graphInstance) {
      // 重置相机到默认视角，让子图在视野中心
      graphInstance.cameraPosition(
        { x: 0, y: 0, z: 300 },
        { x: 0, y: 0, z: 0 },
        800,
      );
    }
  }, 100);
};

/**
 * 退出子图模式
 */
const exitSubgraphMode = () => {
  subgraphMode.value = false;
  subgraphCenterNodeId.value = null;
  subgraphNodeIds.value = new Set();
  clearHighlight();
  updateGraph();
};

/**
 * 更新子图跳数
 */
const updateSubgraphHops = (hops: number) => {
  subgraphHops.value = hops;
  if (subgraphMode.value && subgraphCenterNodeId.value) {
    subgraphNodeIds.value = computeNHopNeighbors(
      subgraphCenterNodeId.value,
      hops,
    );
    updateGraph();

    // 延迟重置相机位置
    setTimeout(() => {
      if (graphInstance) {
        graphInstance.cameraPosition(
          { x: 0, y: 0, z: 300 },
          { x: 0, y: 0, z: 0 },
          500,
        );
      }
    }, 100);
  }
};

// =============================================
// 高亮逻辑
// =============================================
const getNodeHighlightState = (node: GraphNode): boolean => {
  // 单个节点高亮模式：高亮选中的节点及其直接连接的节点
  if (highlightMode.value === 'singleNode' && highlightedSingleNodeId.value) {
    if (node.id === highlightedSingleNodeId.value) return true;
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
    if (node.label === highlightedNodeType.value) return true;
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

const getEdgeHighlightState = (edge: GraphEdge): boolean => {
  // 单个节点高亮模式
  if (highlightMode.value === 'singleNode' && highlightedSingleNodeId.value) {
    return (
      edge.sourceNodeId === highlightedSingleNodeId.value ||
      edge.targetNodeId === highlightedSingleNodeId.value
    );
  }

  // 组合模式
  if (
    highlightMode.value === 'combined' &&
    highlightedNodeType.value &&
    highlightedRelationType.value
  ) {
    if (edge.relationType !== highlightedRelationType.value) return false;
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

// 获取节点大小（基于度数 + 类型）
const getNodeSize3D = (nodeId: string, label: NodeLabel): number => {
  const base = nodeSize.value;
  const degree = nodeDegreeMap.value.get(nodeId) || 0;
  // 度数加成：最多增加 2 倍
  const degreeBonus = Math.min(degree * 0.15, 2);

  let typeMultiplier = 1;
  switch (label) {
    case 'DIM_EMOTION':
    case 'DIM_LANG':
    case 'DIM_MOTIVE': {
      typeMultiplier = 1.15;
      break;
    }
    case 'DIM_IDENTITY': {
      typeMultiplier = 1.4;
      break;
    }
    case 'PERSONA_ROOT': {
      typeMultiplier = 1.5;
      break;
    }
  }
  return base * typeMultiplier * (1 + degreeBonus);
};

// =============================================
// 数据加载
// =============================================
const fetchGraphData = async () => {
  loading.value = true;
  try {
    // 使用新的可视化 API，后端已根据 min_degree 过滤并关联节点和边
    const res = await getGraphVisualizationApi({
      tenant_code: 'default',
      min_degree: 0, // 显示所有节点（度数>=0）
      limit: 500, // 增加节点数量限制
    });

    // 数据映射，包含 corpus 和 properties 用于抽屉展示
    allNodes.value = res.nodes.map((item) => ({
      id: item.id,
      label: item.label as NodeLabel,
      name: item.name,
      description: item.description,
      corpus: item.corpus,
      properties: item.properties,
      tenantId: item.tenant_code,
      status: item.is_active as 0 | 1,
      isDeleted: item.is_deleted as 0 | 1,
      createdAt: '',
      updatedAt: '',
    }));

    allEdges.value = res.edges.map((item) => ({
      id: item.id,
      sourceNodeId: item.source_node_id,
      targetNodeId: item.target_node_id,
      relationType: item.relation_type as RelationType,
      tenantId: item.tenant_code,
      weight: Number(item.meta_data?.weight) || 1,
      priority: 0,
      status: item.is_active as 0 | 1,
      isDeleted: item.is_deleted as 0 | 1,
      createdAt: '',
      updatedAt: '',
    }));

    // 数据加载完成
  } catch (error) {
    console.error(error);
    message.error('加载图数据失败');
  } finally {
    loading.value = false;
  }
};

// =============================================
// 图数据构建
// =============================================
const buildGraphData = () => {
  // 过滤掉 PERSONA_ROOT 节点（不展示人设聚合点）
  let activeNodes = allNodes.value.filter(
    (n) => n.isDeleted === 0 && n.status === 1 && n.label !== 'PERSONA_ROOT',
  );
  let activeEdges = allEdges.value.filter(
    (e) => e.isDeleted === 0 && e.status === 1,
  );

  // 子图模式：只显示子图中的节点
  if (subgraphMode.value && subgraphNodeIds.value.size > 0) {
    activeNodes = activeNodes.filter((n) => subgraphNodeIds.value.has(n.id));
    activeEdges = activeEdges.filter(
      (e) =>
        subgraphNodeIds.value.has(e.sourceNodeId) &&
        subgraphNodeIds.value.has(e.targetNodeId),
    );
  }

  const nodeIdSet = new Set(activeNodes.map((n) => n.id));

  const nodes = activeNodes.map((node) => {
    const nodeLabel = node.label as NodeLabel;
    const isHighlighted = getNodeHighlightState(node);
    const isHovered = hoveredNodeId.value === node.id;
    const hasHighlight = highlightMode.value !== 'none';
    const degree = nodeDegreeMap.value.get(node.id) || 0;

    // 基于度数的节点大小
    const baseSize = getNodeSize3D(node.id, nodeLabel);

    // 使用统一的颜色获取函数
    const nodeColor = getNodeColor(node.label);

    // Hover 时放大
    let finalSize = baseSize;
    if (isHovered) finalSize = baseSize * 1.5;
    else if (isHighlighted) finalSize = baseSize * 1.3;

    return {
      id: node.id,
      name: node.name,
      label: nodeLabel,
      color: isHighlighted ? '#fff' : nodeColor,
      // 非高亮节点透明度提高到 0.7，让远处节点更清晰
      opacity: hasHighlight ? (isHighlighted ? 1 : 0.7) : 1,
      size: finalSize,
      degree,
      originalData: node,
    };
  });

  const links = activeEdges
    .filter(
      (e) => nodeIdSet.has(e.sourceNodeId) && nodeIdSet.has(e.targetNodeId),
    )
    .map((edge) => {
      const isHighlighted = getEdgeHighlightState(edge);
      const hasHighlight = highlightMode.value !== 'none';
      const isConflict = edge.relationType === 'CONFLICTS_WITH';

      // 基础透明度：提高到 0.75，让远处连线更清晰
      let opacity = 0.75;
      // 高亮模式下非高亮边透明度提高到 0.35
      if (hasHighlight) opacity = isHighlighted ? 0.95 : 0.35;
      else if (isConflict) opacity = 0.5;

      // 使用统一的颜色获取函数
      const edgeColor = getRelationColor(edge.relationType);

      return {
        source: edge.sourceNodeId,
        target: edge.targetNodeId,
        relationType: edge.relationType,
        color: isHighlighted ? '#fff' : edgeColor,
        opacity,
        width: isHighlighted ? linkWidth.value * 3 : linkWidth.value,
        curvature: isConflict ? 0.3 : 0,
        originalData: edge,
      };
    });

  return { nodes, links };
};

// =============================================
// 3D图初始化
// =============================================
const initGraph = async () => {
  if (!containerRef.value) {
    console.warn('3D Graph container not ready');
    return;
  }

  // 检测 WebGL 支持
  const webglCheck = checkWebGLSupport();
  if (!webglCheck.supported) {
    webglError.value = webglCheck.error || 'WebGL 不可用';
    console.error('WebGL not supported:', webglCheck.error);
    return;
  }

  await fetchGraphData();

  // 再次检查容器是否仍然存在（可能在 await 期间组件被卸载）
  if (!containerRef.value) {
    console.warn('3D Graph container destroyed during data fetch');
    return;
  }

  const graphData = buildGraphData();

  // 如果没有数据，不初始化图
  if (graphData.nodes.length === 0) {
    console.warn('No 3D nodes to display');
    return;
  }

  graphInstance = (ForceGraph3D as any)()(containerRef.value)
    .backgroundColor(isDark.value ? '#0a0a0f' : '#f0f2f5')
    .nodeLabel((node: any) =>
      showLabels.value
        ? `
      <div style="
        background: rgba(0,0,0,0.85);
        color: #fff;
        padding: 8px 12px;
        border-radius: 8px;
        font-size: 13px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        border: 1px solid ${node.color || '#666'};
      ">
        <div style="font-weight: bold; margin-bottom: 4px;">${node.name}</div>
        <div style="opacity: 0.7; font-size: 11px;">${NODE_LABEL_CONFIG[node.label as NodeLabel]?.displayName || node.label}</div>
        <div style="opacity: 0.55; font-size: 11px; margin-top: 2px;">label: ${node.label}</div>
      </div>
    `
        : '',
    )
    .nodeColor((node: any) => node.color)
    .nodeOpacity((node: any) => node.opacity)
    .nodeVal((node: any) => node.size)
    .nodeRelSize(5)
    .linkColor((link: any) => link.color)
    .linkOpacity((link: any) => link.opacity) // 固定透明度，不做动态计算
    .linkWidth((link: any) => link.width)
    .linkCurvature((link: any) => link.curvature)
    .linkDirectionalArrowLength(4)
    .linkDirectionalArrowRelPos(0.9)
    .linkDirectionalArrowColor((link: any) => link.color)
    // 【性能优化】禁用粒子系统，大幅减少 GPU 负载
    // 粒子会为每条边创建动画对象，边数多时会导致 WebGL 崩溃
    .linkDirectionalParticles(0)
    .onNodeClick((node: any) => {
      handleNodeClick(node.originalData);
    })
    .onNodeHover((node: any) => {
      if (containerRef.value) {
        containerRef.value.style.cursor = node ? 'pointer' : 'grab';
      }
      // 【优化】只更新 hover 状态，不触发 updateGraphVisuals
      // 这避免了重复调用 nodeThreeObject 导致的内存泄漏
      hoveredNodeId.value = node?.id || null;
    })
    // 【关键性能优化】自定义节点渲染 - 使用缓存避免重复创建
    .nodeThreeObject((node: any) => {
      // 【优化】检查缓存，避免重复创建
      const cacheKey = node.id;
      const cached = nodeThreeObjectCache.get(cacheKey);
      if (cached) {
        return cached;
      }

      const nodeColor = getNodeColor(node.label);
      const group = new THREE.Group();

      const isCenterNode =
        subgraphMode.value && subgraphCenterNodeId.value === node.id;

      // 【性能优化】使用缓存的几何体（8x8 分段）
      const sphereSize = node.size * 0.6;
      const sphereGeometry = getOrCreateSphereGeometry(sphereSize);

      // 【性能优化】使用缓存的材质
      const sphereColor = isCenterNode ? '#ffffff' : nodeColor;
      const sphereOpacity = node.opacity * 0.9;
      const sphereMaterial = getOrCreateMaterial(sphereColor, sphereOpacity);

      const sphere = new THREE.Mesh(sphereGeometry, sphereMaterial);
      group.add(sphere);

      // 中心节点添加光环效果（使用缓存）
      if (isCenterNode) {
        const ringGeometry = getOrCreateRingGeometry(
          node.size * 0.8,
          node.size,
        );
        const ringMaterial = getOrCreateMaterial(nodeColor, 0.6, true);
        const ring = new THREE.Mesh(ringGeometry, ringMaterial);
        group.add(ring);
      }

      // 【关键优化】大幅减少 SpriteText 使用 - 只为中心节点创建文字标签
      // SpriteText 创建 Canvas 纹理，大量使用会导致 WebGL 显存爆炸
      if (showLabels.value && isCenterNode) {
        const displayName =
          node.name.length > 8 ? `${node.name.slice(0, 8)}...` : node.name;
        const sprite = new SpriteText(displayName);
        sprite.color = '#ffffff';
        sprite.textHeight = 4;
        sprite.backgroundColor = 'rgba(255,107,107,0.9)';
        sprite.padding = 2;
        sprite.borderRadius = 3;
        (sprite as any).position.y = node.size * 1.5;
        group.add(sprite);
      }

      // 【常驻文本】在图上显示节点名称（可开关）
      if (showNodeLabelText.value) {
        const nameText = String(node.name ?? '').trim();
        if (nameText) {
          const material = get_or_create_label_text_material(nameText);
          const sprite = new THREE.Sprite(material);
          const aspect = Number((material as any).userData?.aspect ?? 1);
          const baseH = Math.max(10, node.size * 1.1);
          sprite.scale.set(baseH * aspect, baseH, 1);
          sprite.position.set(0, node.size * 1.6, 0);
          group.add(sprite);
        }
      }

      // 缓存节点对象
      nodeThreeObjectCache.set(cacheKey, group);

      return group;
    })
    .graphData(graphData);

  // =============================================
  // 力导向布局算法配置 (D3.js Force-Directed Layout)
  // =============================================
  //
  // 📖 算法原理：
  //   - 所有节点之间存在「斥力」(charge)，互相排斥
  //   - 有边连接的节点之间存在「引力」(link)，互相吸引
  //   - 当斥力和引力达到平衡时，图谱稳定
  //
  // 📐 力学公式：
  //   斥力: F = strength / distance²  (库仑定律)
  //   引力: F = k * (distance - targetDistance)  (弹簧力)
  //
  // ⚙️ 参数调节指南：
  // ┌─────────────────┬──────────┬───────────────────────────────────────┐
  // │ 参数            │ 当前值   │ 作用                                  │
  // ├─────────────────┼──────────┼───────────────────────────────────────┤
  // │ charge.strength │ 动态     │ 基础-80，高度节点额外增加斥力          │
  // │ charge.distMax  │ 300      │ 斥力作用最大距离，超过不计算           │
  // │ link.distance   │ 动态     │ 基础40，高度节点邻居间距更大           │
  // │ collide.radius  │ 动态     │ 节点碰撞半径，防止重叠                 │
  // │ d3AlphaDecay    │ 0.02     │ 模拟"温度"衰减，越小布局越精确但越慢   │
  // │ d3VelocityDecay │ 0.3      │ 速度衰减，越大节点停止越快             │
  // │ warmupTicks     │ 100      │ 初始化预计算迭代次数                   │
  // │ cooldownTicks   │ 0        │ 0=持续模拟，>0=迭代N次后停止           │
  // └─────────────────┴──────────┴───────────────────────────────────────┘
  //
  // 🔧 高度节点（Hub）优化：
  //   - 动态斥力：度数越高，斥力越强，自动"推开"周围节点
  //   - 动态链接距离：高度节点的邻居间距更大，分布更均匀
  //   - 碰撞检测：防止节点重叠，保持视觉清晰
  //   - 距离限制：distanceMax 限制斥力计算范围，提升性能
  //

  // 1. 动态斥力：高度节点斥力更强，自动推开周围聚集的节点
  const chargeForce = graphInstance.d3Force('charge');
  if (chargeForce) {
    chargeForce
      .strength((node: any) => {
        const degree = node.degree || 0;
        // 基础斥力 -80，每增加1度，增加 -6 斥力，最大 -300
        return Math.max(-80 - degree * 6, -300);
      })
      .distanceMax(300); // 限制斥力作用范围，提升性能
  }

  // 2. 动态链接距离：高度节点的邻居间距更大
  const linkForce = graphInstance.d3Force('link');
  if (linkForce) {
    linkForce.distance((link: any) => {
      const sourceDegree = link.source?.degree || 0;
      const targetDegree = link.target?.degree || 0;
      const maxDegree = Math.max(sourceDegree, targetDegree);
      // 基础距离 40，高度节点增加间距，最大 100
      return 40 + Math.min(maxDegree * 4, 60);
    });
  }

  // 3. 添加碰撞力：防止节点重叠
  graphInstance.d3Force(
    'collide',
    forceCollide()
      .radius((node: any) => (node.size || 5) * 1.5) // 碰撞半径 = 节点大小 * 1.5
      .strength(0.7) // 碰撞力强度，0.7 平衡性能和效果
      .iterations(2), // 每帧迭代次数，2次足够
  );

  graphInstance
    .d3AlphaDecay(0.02)
    .d3VelocityDecay(0.3)
    .warmupTicks(100) // 增加预热迭代，让布局更稳定
    .cooldownTicks(0);

  // =============================================
  // 添加深度雾效
  // =============================================
  const scene = graphInstance.scene();
  // 雾效密度：0.0006 让远处物体更清晰可见（原 0.0015 太浓）
  scene.fog = new THREE.FogExp2(isDark.value ? 0x0a_0a_0f : 0xf0_f2_f5, 0.0006);

  // =============================================
  // 【关键】监听 WebGL context 丢失事件
  // =============================================
  const renderer = graphInstance.renderer();
  if (renderer?.domElement) {
    renderer.domElement.addEventListener('webglcontextlost', (event: Event) => {
      event.preventDefault();
      webglError.value = 'WebGL 上下文丢失，请刷新页面重试。';
      console.error('[Graph3D] WebGL context lost');
    });

    renderer.domElement.addEventListener('webglcontextrestored', () => {
      webglError.value = null;
    });
  }

  // =============================================
  // 确保 OrbitControls 启用（拖动旋转视角）
  // =============================================
  const controls = graphInstance.controls();
  if (controls) {
    controls.enableRotate = true;
    controls.enablePan = true;
    controls.enableZoom = true;
    controls.autoRotate = false; // 禁用 controls 自带的自动旋转，我们用自己的

    // 当用户开始拖动时，暂停自动旋转
    controls.addEventListener('start', () => {
      if (isRotating.value) {
        isRotating.value = false;
      }
    });
  }

  // =============================================
  // 入场动画 + 相机动画
  // =============================================
  playEntranceAnimation();

  // 主动画循环（精简版）
  let angle = 0;
  const animate = () => {
    // 自动旋转（仅在 isRotating 为 true 时）
    if (isRotating.value && graphInstance && !highlightedSingleNodeId.value) {
      angle += 0.002;
      graphInstance.cameraPosition({
        x: 400 * Math.sin(angle),
        z: 400 * Math.cos(angle),
      });
    }

    animationFrameId = requestAnimationFrame(animate);
  };
  animate();

  // 标记图谱初始化完成（延迟以等待入场动画）
  setTimeout(() => {
    isGraphReady.value = true;
  }, 500);
};

// =============================================
// 动画效果函数
// =============================================

// 节点入场动画（简化版 - 只做相机动画，不固定节点位置）
const playEntranceAnimation = () => {
  if (!graphInstance) return;

  // 相机从近到远，让力导向布局自然展开
  graphInstance.cameraPosition({ x: 0, y: 0, z: 200 }, { x: 0, y: 0, z: 0 }, 0);

  setTimeout(() => {
    graphInstance?.cameraPosition(
      { x: 0, y: 0, z: 500 },
      { x: 0, y: 0, z: 0 },
      2000,
    );
  }, 500);
};

// 【性能优化】创建点击涟漪 - 简化版，只创建 1 个环
const createClickRipple = (position: THREE.Vector3, color: THREE.Color) => {
  if (!graphInstance) return;

  // 使用缓存的几何体和材质
  const ringGeometry = getOrCreateRingGeometry(1, 2);
  const ringMaterial = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: 0.6,
    side: THREE.DoubleSide,
  });

  const ring = new THREE.Mesh(ringGeometry, ringMaterial);
  ring.position.copy(position);
  graphInstance.scene().add(ring);

  const startTime = Date.now();
  const animateRipple = () => {
    const elapsed = Date.now() - startTime;
    if (elapsed > 600) {
      graphInstance?.scene().remove(ring);
      ringMaterial.dispose(); // 清理材质（几何体是缓存的，不清理）
      return;
    }

    const progress = elapsed / 600;
    const scale = 1 + progress * 15;
    ring.scale.set(scale, scale, 1);
    ringMaterial.opacity = 0.6 * (1 - progress);
    requestAnimationFrame(animateRipple);
  };
  animateRipple();
};

// 【性能优化】创建连线高亮波 - 限制最大脉冲数量，使用缓存几何体
const createEdgePulseWave = (nodeId: string) => {
  if (!graphInstance) return;

  const connectedEdges = allEdges.value.filter(
    (e) =>
      (e.sourceNodeId === nodeId || e.targetNodeId === nodeId) &&
      e.isDeleted === 0,
  );

  // 【性能优化】限制最大脉冲数量为 5，避免大量动画对象
  const maxPulses = 5;
  const edgesToAnimate = connectedEdges.slice(0, maxPulses);

  const links = graphInstance.graphData().links;

  // 使用缓存的几何体
  const pulseGeometry = getOrCreateSphereGeometry(2);

  edgesToAnimate.forEach((edge, index) => {
    const link = links.find(
      (l: any) =>
        (l.source?.id === edge.sourceNodeId &&
          l.target?.id === edge.targetNodeId) ||
        (l.source?.id === edge.targetNodeId &&
          l.target?.id === edge.sourceNodeId),
    );

    if (!link || !link.source?.x) return;

    setTimeout(() => {
      // 每个脉冲创建独立的材质（动画中会修改 opacity）
      const pulseMaterial = new THREE.MeshBasicMaterial({
        color: new THREE.Color(getRelationColor(edge.relationType)),
        transparent: true,
        opacity: 1,
      });
      const pulse = new THREE.Mesh(pulseGeometry, pulseMaterial);

      const startPos = link.source.id === nodeId ? link.source : link.target;
      const endPos = link.source.id === nodeId ? link.target : link.source;

      pulse.position.set(startPos.x, startPos.y, startPos.z);
      graphInstance?.scene().add(pulse);

      const startTime = Date.now();
      const duration = 600;

      const animatePulse = () => {
        const elapsed = Date.now() - startTime;
        const progress = Math.min(elapsed / duration, 1);

        pulse.position.set(
          startPos.x + (endPos.x - startPos.x) * progress,
          startPos.y + (endPos.y - startPos.y) * progress,
          startPos.z + (endPos.z - startPos.z) * progress,
        );

        pulseMaterial.opacity = 1 - progress * 0.7;
        const scale = 1 + progress * 0.5;
        pulse.scale.set(scale, scale, scale);

        if (progress < 1) {
          requestAnimationFrame(animatePulse);
        } else {
          graphInstance?.scene().remove(pulse);
          pulseMaterial.dispose(); // 清理材质
        }
      };
      animatePulse();
    }, index * 80); // 增加间隔，减少同时运行的动画数量
  });
};

// 【性能优化】更新图数据（完整重建，用于筛选等场景）- 带防抖
let updateGraphTimer: null | ReturnType<typeof setTimeout> = null;
let lastUpdateTime = 0;

const updateGraph = () => {
  if (!graphInstance) return;

  // 防抖：如果距离上次更新不足 100ms，则延迟执行
  const now = Date.now();
  if (now - lastUpdateTime < 100) {
    if (updateGraphTimer) clearTimeout(updateGraphTimer);
    updateGraphTimer = setTimeout(() => {
      doUpdateGraph();
    }, 100);
    return;
  }

  doUpdateGraph();
};

const doUpdateGraph = () => {
  if (!graphInstance) return;
  lastUpdateTime = Date.now();

  // 【关键】清理节点对象缓存，因为数据可能已变化
  nodeThreeObjectCache.forEach((group) => {
    group.traverse((child) => {
      const material = (child as any).material as
        | undefined
        | { map?: THREE.Texture; userData?: Record<string, unknown> };
      const isLabelTextMaterial = Boolean(
        material?.userData?.isLabelTextMaterial,
      );
      if (!isLabelTextMaterial && material?.map) material.map.dispose();
    });
  });
  nodeThreeObjectCache.clear();

  const graphData = buildGraphData();
  graphInstance.graphData(graphData);
};

// 轻量更新：只更新视觉属性，不触发力导向重计算
const updateGraphVisuals = () => {
  if (!graphInstance || !isGraphReady.value) return;

  // 获取当前图数据
  const currentData = graphInstance.graphData();
  const hasHighlight = highlightMode.value !== 'none';

  // 更新节点视觉属性
  currentData.nodes.forEach((node: any) => {
    const originalNode = node.originalData as GraphNode;
    if (!originalNode) return;

    const isHighlighted = getNodeHighlightState(originalNode);
    const isHovered = hoveredNodeId.value === node.id;
    const nodeColor = getNodeColor(originalNode.label);

    // 更新颜色
    node.color = isHighlighted ? '#fff' : nodeColor;
    // 更新透明度（非高亮节点保持 0.7 可见度）
    node.opacity = hasHighlight ? (isHighlighted ? 1 : 0.7) : 1;
    // 更新大小
    const baseSize = getNodeSize3D(node.id, originalNode.label as NodeLabel);
    if (isHovered) node.size = baseSize * 1.5;
    else if (isHighlighted) node.size = baseSize * 1.3;
    else node.size = baseSize;
  });

  // 更新边视觉属性
  currentData.links.forEach((link: any) => {
    const originalEdge = link.originalData as GraphEdge;
    if (!originalEdge) return;

    const isHighlighted = getEdgeHighlightState(originalEdge);
    const isConflict = originalEdge.relationType === 'CONFLICTS_WITH';
    const edgeColor = getRelationColor(originalEdge.relationType);

    // 更新颜色
    link.color = isHighlighted ? '#fff' : edgeColor;
    // 更新透明度（非高亮边保持 0.35 可见度）
    if (hasHighlight) link.opacity = isHighlighted ? 0.95 : 0.35;
    else if (isConflict) link.opacity = 0.5;
    else link.opacity = 0.75;
    // 更新宽度
    link.width = isHighlighted ? linkWidth.value * 3 : linkWidth.value;
  });

  // 刷新渲染：使用 nodeRelSize 触发视觉更新，不触发力导向重计算
  // 注意：不能用 nodeColor(nodeColor()) 因为会触发 nodeThreeObject 重建
  graphInstance
    .nodeRelSize(graphInstance.nodeRelSize())
    .linkWidth(graphInstance.linkWidth());
};

// =============================================
// 交互操作
// =============================================
const handleNodeClick = (node: GraphNode) => {
  selectedNode.value = node;

  // 1. 镜头聚焦动效（平滑推进）
  if (graphInstance) {
    const graphNode = graphInstance
      .graphData()
      .nodes.find((n: any) => n.id === node.id);
    if (graphNode && graphNode.x !== undefined) {
      // 获取当前相机位置
      const currentPos = graphInstance.cameraPosition();

      // 第一阶段：先稍微拉远（制造推进感）
      const pullBackDistance = 80;
      const midX = (currentPos.x + graphNode.x) / 2;
      const midY = (currentPos.y + graphNode.y) / 2 + pullBackDistance;
      const midZ = (currentPos.z + graphNode.z) / 2 + pullBackDistance;

      graphInstance.cameraPosition(
        { x: midX, y: midY, z: midZ },
        { x: graphNode.x, y: graphNode.y, z: graphNode.z },
        800, // 拉远阶段
      );

      // 第二阶段：平滑推进到节点前方
      setTimeout(() => {
        if (!graphInstance) return;
        const finalDistance = 250; // 调整距离，避免太近
        graphInstance.cameraPosition(
          {
            x: graphNode.x,
            y: graphNode.y + 50,
            z: graphNode.z + finalDistance,
          },
          { x: graphNode.x, y: graphNode.y, z: graphNode.z },
          1800, // 推进阶段更慢更平滑
        );
      }, 600);

      // 2. 创建点击涟漪
      const nodeColor = new THREE.Color(getNodeColor(node.label));
      createClickRipple(
        new THREE.Vector3(graphNode.x, graphNode.y, graphNode.z),
        nodeColor,
      );

      // 3. 创建连线高亮波
      createEdgePulseWave(node.id);
    }
  }

  // 5. 高亮该节点及其关系（使用轻量更新，避免力导向重计算导致抖动）
  highlightedSingleNodeId.value = node.id;
  highlightMode.value = 'singleNode';
  updateGraphVisuals();

  // 获取出边及其目标节点
  const outgoingEdges = allEdges.value.filter(
    (e) => e.sourceNodeId === node.id && e.isDeleted === 0,
  );
  const outgoingWithNodes: EdgeWithNode[] = outgoingEdges.map((edge) => ({
    edge,
    node: allNodes.value.find((n) => n.id === edge.targetNodeId) || null,
  }));

  // 获取入边及其源节点
  const incomingEdges = allEdges.value.filter(
    (e) => e.targetNodeId === node.id && e.isDeleted === 0,
  );
  const incomingWithNodes: EdgeWithNode[] = incomingEdges.map((edge) => ({
    edge,
    node: allNodes.value.find((n) => n.id === edge.sourceNodeId) || null,
  }));

  selectedNodeEdges.value = {
    incoming: incomingWithNodes,
    outgoing: outgoingWithNodes,
  };

  // 6. 延迟打开抽屉（等待推进动画完成）
  setTimeout(() => {
    drawerVisible.value = true;
  }, 1200);
};

const handleNodeTypeClick = (label: NodeLabel) => {
  // 清除单节点高亮
  highlightedSingleNodeId.value = null;

  if (highlightedNodeType.value === label) {
    highlightMode.value = 'none';
    highlightedNodeType.value = null;
    highlightedRelationType.value = null;
  } else {
    highlightedNodeType.value = label;
    highlightMode.value = highlightedRelationType.value
      ? 'combined'
      : 'nodeType';
  }
  updateGraphVisuals();
};

const handleRelationTypeClick = (type: RelationType) => {
  if (
    highlightedRelationType.value === type &&
    highlightMode.value === 'combined'
  ) {
    highlightedRelationType.value = null;
    highlightMode.value = 'nodeType';
  } else if (
    highlightedRelationType.value === type &&
    highlightMode.value === 'relationType'
  ) {
    highlightedRelationType.value = null;
    highlightMode.value = 'none';
  } else if (highlightedNodeType.value) {
    highlightedRelationType.value = type;
    highlightMode.value = 'combined';
  } else {
    message.info('请先选择一个节点类型，再选择关系类型进行组合筛选');
    return;
  }
  updateGraphVisuals();
};

// 高亮单个节点及其直接关系
const handleSingleNodeHighlight = (nodeId: string) => {
  if (highlightedSingleNodeId.value === nodeId) {
    highlightedSingleNodeId.value = null;
    highlightMode.value = 'none';
  } else {
    highlightedSingleNodeId.value = nodeId;
    highlightedNodeType.value = null;
    highlightedRelationType.value = null;
    highlightMode.value = 'singleNode';
  }
  updateGraphVisuals();
};

const clearHighlight = () => {
  highlightMode.value = 'none';
  highlightedNodeType.value = null;
  highlightedRelationType.value = null;
  highlightedSingleNodeId.value = null;
  searchKeyword.value = '';
  updateGraphVisuals();
};

const handleSearchResultClick = (node: GraphNode) => {
  // 进入子图模式，只显示该节点及其邻居
  enterSubgraphMode(node.id);
  searchKeyword.value = ''; // 清空搜索框

  // 延迟聚焦到节点（等待图重建）
  setTimeout(() => {
    if (graphInstance) {
      const graphNode = graphInstance
        .graphData()
        .nodes.find((n: any) => n.id === node.id);
      if (graphNode && graphNode.x !== undefined) {
        graphInstance.cameraPosition(
          { x: graphNode.x, y: graphNode.y + 50, z: graphNode.z + 250 },
          { x: graphNode.x, y: graphNode.y, z: graphNode.z },
          1000,
        );
      }
    }
  }, 300);
};

const toggleFullscreen = () => {
  isFullscreen.value = !isFullscreen.value;
  setTimeout(() => {
    if (containerRef.value && graphInstance) {
      const { width, height } = containerRef.value.getBoundingClientRect();
      graphInstance.width(width).height(height);
    }
  }, 100);
};

const resetCamera = () => {
  if (graphInstance) {
    graphInstance.cameraPosition(
      { x: 0, y: 0, z: 500 },
      { x: 0, y: 0, z: 0 },
      1000,
    );
  }
  // 同时清除高亮状态
  clearHighlight();
};

// =============================================
// 监听变化
// =============================================
watch(searchKeyword, (val) => {
  if (val) {
    highlightMode.value = 'search';
    highlightedNodeType.value = null;
    highlightedRelationType.value = null;
  } else if (highlightMode.value === 'search') {
    highlightMode.value = 'none';
  }
  updateGraphVisuals();
});

watch([nodeSize, linkWidth], () => {
  updateGraph();
});

watch(showNodeLabelText, () => {
  // 切换“常驻文本”需要重建 nodeThreeObject
  updateGraph();
});

// 监听主题变化，更新图表背景、雾效和节点颜色
watch(isDark, (dark) => {
  if (graphInstance) {
    graphInstance.backgroundColor(dark ? '#0a0a0f' : '#f0f2f5');
    // 更新雾效颜色
    const scene = graphInstance.scene();
    if (scene?.fog) {
      (scene.fog as THREE.FogExp2).color.setHex(dark ? 0x0a_0a_0f : 0xf0_f2_f5);
    }
    // 【关键】主题切换时重建图数据，应用新的颜色配置
    // 清理文本贴图缓存（因为文本背景颜色变了）
    labelTextSpriteMaterialCache.forEach((mat) => {
      if (mat.map) mat.map.dispose();
      mat.dispose();
    });
    labelTextSpriteMaterialCache.clear();
    // 重建图
    updateGraph();
  }
});

// =============================================
// 生命周期
// =============================================
onMounted(() => {
  initGraph();
});

onUnmounted(() => {
  // 重置初始化标志
  isGraphReady.value = false;

  // 取消动画循环
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId);
    animationFrameId = null;
  }

  // 清理防抖定时器
  if (updateGraphTimer) {
    clearTimeout(updateGraphTimer);
    updateGraphTimer = null;
  }

  // 【关键】清理所有缓存的 THREE.js 对象，防止内存泄漏
  disposeThreeResources();

  if (graphInstance) {
    // 获取 scene 并清理所有子对象
    try {
      const scene = graphInstance.scene();
      if (scene) {
        // 递归清理 scene 中的所有对象
        scene.traverse((obj: THREE.Object3D) => {
          if (obj instanceof THREE.Mesh) {
            obj.geometry?.dispose();
            if (Array.isArray(obj.material)) {
              obj.material.forEach((m: THREE.Material) => m.dispose());
            } else if (obj.material) {
              (obj.material as THREE.Material).dispose();
            }
          }
        });
        // 清空 scene
        while (scene.children.length > 0) {
          scene.remove(scene.children[0]);
        }
      }

      // 获取 renderer 并清理
      const renderer = graphInstance.renderer();
      if (renderer) {
        renderer.dispose();
        renderer.forceContextLoss();
      }
    } catch (error) {
      console.warn('[Graph3D] Error during cleanup:', error);
    }

    graphInstance._destructor?.();
    graphInstance = null;
  }
});
</script>

<template>
  <div
    class="graph-3d-container"
    :class="[{ fullscreen: isFullscreen, dark: isDark }]"
  >
    <!-- 左侧控制面板 -->
    <div class="control-panel left-panel">
      <div class="panel-header">
        <SearchOutlined />
        <span>关键词图谱</span>
      </div>

      <!-- 搜索 -->
      <div class="panel-section">
        <div class="section-title">🔍 搜索</div>
        <Input
          v-model:value="searchKeyword"
          placeholder="输入关键词..."
          allow-clear
          size="small"
        />
        <div v-if="searchResults.length > 0" class="search-results">
          <div
            v-for="node in searchResults"
            :key="node.id"
            class="search-item"
            @click="handleSearchResultClick(node)"
          >
            <span
              class="node-dot"
              :style="{
                background: getNodeColor(node.label),
              }"
            ></span>
            {{ node.name }}
          </div>
        </div>
      </div>

      <!-- 关键词类型 -->
      <div class="panel-section">
        <div class="section-title">
          <NodeIndexOutlined />
          关键词类型
        </div>
        <div class="type-list">
          <template v-for="(stats, label) in nodeTypeStats" :key="label">
            <div
              v-if="label !== 'PERSONA_ROOT'"
              class="type-item"
              :class="[{ active: stats.active }]"
              @click="handleNodeTypeClick(label as NodeLabel)"
            >
              <span
                class="type-dot"
                :style="{ background: stats.color }"
              ></span>
              <span class="type-name">{{ stats.displayName }}</span>
              <Badge
                :count="stats.count"
                :number-style="{
                  backgroundColor: stats.active ? '#fff' : stats.color,
                  fontSize: '10px',
                }"
              />
            </div>
          </template>
        </div>
      </div>

      <!-- 关系类型 -->
      <div class="panel-section">
        <div class="section-title">
          <BranchesOutlined />
          关系类型
        </div>
        <div class="type-list">
          <div
            v-for="(stats, type) in relationTypeStats"
            :key="type"
            class="type-item relation-item"
            :class="[
              { active: stats.active, conflict: type === 'CONFLICTS_WITH' },
            ]"
            @click="handleRelationTypeClick(type as RelationType)"
          >
            <span
              class="type-line"
              :style="{
                background: stats.color,
                borderStyle: type === 'CONFLICTS_WITH' ? 'dashed' : 'solid',
              }"
            ></span>
            <span class="type-name">{{ stats.displayName }}</span>
            <Badge
              :count="stats.count"
              :number-style="{
                backgroundColor: stats.active ? '#fff' : stats.color,
                fontSize: '10px',
              }"
            />
          </div>
        </div>
      </div>

      <!-- 清除高亮 -->
      <div class="panel-section" v-if="highlightMode !== 'none'">
        <Button type="primary" ghost block size="small" @click="clearHighlight">
          <CloseCircleOutlined />
          清除高亮
        </Button>
      </div>

      <!-- 子图模式控制 -->
      <div v-if="subgraphMode" class="panel-section subgraph-panel">
        <div class="section-title">🎯 子图探索模式</div>
        <div class="subgraph-info">
          <Tag color="blue">{{ subgraphNodeIds.size }} 个节点</Tag>
        </div>
        <div class="hops-control">
          <span class="hops-label">邻居跳数:</span>
          <div class="hops-buttons">
            <Button
              v-for="hop in [1, 2, 3]"
              :key="hop"
              :type="subgraphHops === hop ? 'primary' : 'default'"
              size="small"
              @click="updateSubgraphHops(hop)"
            >
              {{ hop }}跳
            </Button>
          </div>
        </div>
        <Button
          type="default"
          danger
          block
          size="small"
          class="exit-btn"
          @click="exitSubgraphMode"
        >
          <CloseCircleOutlined />
          退出子图模式
        </Button>
      </div>
    </div>

    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <div class="toolbar-group">
        <Divider type="vertical" />

        <Tooltip title="自动旋转">
          <Button
            :type="isRotating ? 'primary' : 'default'"
            shape="circle"
            size="small"
            @click="isRotating = !isRotating"
          >
            <template #icon>
              <PlayCircleOutlined v-if="!isRotating" />
              <PauseCircleOutlined v-else />
            </template>
          </Button>
        </Tooltip>

        <Tooltip title="重置视角">
          <Button shape="circle" size="small" @click="resetCamera">
            <template #icon><AimOutlined /></template>
          </Button>
        </Tooltip>

        <Divider type="vertical" />

        <!-- <div class="slider-group">
          <span class="slider-label">展示比例</span>
          <Slider
            v-model:value="nodeSize"
            :min="4"
            :max="20"
            :step="1"
            style="width: 80px"
          />
        </div> -->

        <!-- <div class="slider-group">
          <Tooltip title="在图上常驻显示关键词（关键词很多时可能更耗性能）">
            <span class="slider-label">关键词</span>
          </Tooltip>
          <Switch v-model:checked="showNodeLabelText" size="small" />
        </div>

        <div class="slider-group">
          <span class="slider-label">连线粗细</span>
          <Slider
            v-model:value="linkWidth"
            :min="0.5"
            :max="4"
            :step="0.5"
            style="width: 80px"
          />
        </div> -->

        <Divider type="vertical" />

        <Tooltip :title="isFullscreen ? '退出全屏' : '全屏'">
          <Button shape="circle" size="small" @click="toggleFullscreen">
            <template #icon>
              <FullscreenExitOutlined v-if="isFullscreen" />
              <FullscreenOutlined v-else />
            </template>
          </Button>
        </Tooltip>
      </div>
    </div>

    <!-- WebGL 错误提示 -->
    <div v-if="webglError" class="webgl-error">
      <div class="error-icon">🚫</div>
      <h3>3D 图谱无法加载</h3>
      <p>{{ webglError }}</p>
      <div class="error-solutions">
        <h4>可能的解决方案：</h4>
        <ul>
          <li>
            <strong>Chrome:</strong> 打开
            <code>chrome://settings/system</code>，启用「使用硬件加速模式」
          </li>
          <li>
            <strong>或者:</strong> 打开
            <code>chrome://flags/#ignore-gpu-blocklist</code>，设置为 Enabled
          </li>
          <li><strong>Safari/Firefox:</strong> 尝试使用其他浏览器</li>
          <li><strong>重启浏览器</strong> 后再试</li>
        </ul>
      </div>
      <p class="fallback-tip">
        💡 您可以切换到 <strong>vis-network 图谱</strong> 标签页使用 2D
        图谱作为替代方案
      </p>
    </div>

    <!-- 3D 画布 -->
    <div v-show="!webglError" ref="containerRef" class="graph-canvas"></div>

    <!-- 高亮提示 -->
    <div v-if="highlightMode !== 'none'" class="highlight-info">
      <template v-if="highlightMode === 'nodeType' && highlightedNodeType">
        🎯 高亮节点类型:
        <Tag :color="getNodeColor(highlightedNodeType)">
          {{ getNodeDisplayName(highlightedNodeType) }}
        </Tag>
      </template>
      <template
        v-else-if="highlightMode === 'relationType' && highlightedRelationType"
      >
        🔗 高亮关系类型:
        <Tag :color="getRelationColor(highlightedRelationType)">
          {{ getRelationDisplayName(highlightedRelationType) }}
        </Tag>
      </template>
      <template v-else-if="highlightMode === 'search'">
        🔍 搜索: "{{ searchKeyword }}" ({{ searchResults.length }} 个结果)
      </template>
    </div>

    <!-- 右下角统计 -->
    <div class="stats-panel">
      <div class="stat-item">
        <span class="stat-value">{{
          allNodes.filter((n) => n.isDeleted === 0).length
        }}</span>
        <span class="stat-label">节点</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{
          allEdges.filter((e) => e.isDeleted === 0).length
        }}</span>
        <span class="stat-label">关系</span>
      </div>
    </div>

    <!-- Loading 遮罩层 -->
    <Transition name="loading-fade">
      <div v-if="loading" class="loading-overlay">
        <div class="loading-content">
          <div class="loading-spinner">
            <div class="spinner-ring"></div>
            <div class="spinner-ring"></div>
            <div class="spinner-ring"></div>
          </div>
          <div class="loading-text">加载图谱数据中...</div>
          <div class="loading-hint">请稍候，正在处理节点关系</div>
        </div>
      </div>
    </Transition>

    <!-- 节点详情抽屉 -->
    <Drawer
      v-model:open="drawerVisible"
      title="节点详情"
      placement="right"
      :width="480"
      :body-style="{ padding: '0' }"
      class="node-detail-drawer"
    >
      <template v-if="selectedNode">
        <!-- 节点头部信息 -->
        <div class="drawer-header">
          <div class="node-type-badge">
            <span
              class="type-indicator"
              :style="{ background: getNodeColor(selectedNode.label) }"
            ></span>
            <span class="type-icon">{{ getNodeIcon(selectedNode.label) }}</span>
            <span class="type-text">{{
              getNodeDisplayName(selectedNode.label)
            }}</span>
          </div>
          <h2 class="node-title">{{ selectedNode.name }}</h2>
          <p v-if="selectedNode.description" class="node-description">
            {{ selectedNode.description }}
          </p>
          <div class="node-meta">
            <Tag :color="selectedNode.status === 1 ? 'success' : 'error'">
              {{ selectedNode.status === 1 ? '启用' : '禁用' }}
            </Tag>
            <span class="node-id">ID: {{ selectedNode.id }}</span>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="drawer-actions">
          <Button
            type="primary"
            ghost
            size="small"
            @click="
              handleSingleNodeHighlight(selectedNode.id);
              drawerVisible = false;
            "
          >
            <BranchesOutlined /> 高亮关系
          </Button>
          <Button
            type="primary"
            size="small"
            @click="
              enterSubgraphMode(selectedNode.id);
              drawerVisible = false;
            "
          >
            <AimOutlined /> 聚焦探索
          </Button>
        </div>

        <!-- 内容区域 -->
        <div class="drawer-content">
          <!-- 语料内容 -->
          <div v-if="hasCorpus(selectedNode)" class="content-section">
            <div class="section-header">
              <span class="section-icon">📝</span>
              <span class="section-title">语料内容</span>
            </div>
            <div class="section-body">
              <!-- 单个结构化语料对象 -->
              <template v-if="isStructuredCorpus(selectedNode.corpus)">
                <div class="structured-corpus">
                  <div class="template-badge">
                    <Tag color="blue">
                      {{ selectedNode.corpus.template_code }}
                    </Tag>
                  </div>
                  <div class="corpus-fields">
                    <div
                      v-for="(value, key) in selectedNode.corpus.fields"
                      :key="key"
                      class="field-item"
                    >
                      <span class="field-label">{{ key }}</span>
                      <span class="field-value">{{ value }}</span>
                    </div>
                  </div>
                </div>
              </template>
              <!-- 结构化语料数组 -->
              <template
                v-else-if="isStructuredCorpusArray(selectedNode.corpus)"
              >
                <div
                  v-for="(corpusItem, corpusIdx) in (
                    selectedNode.corpus as StructuredCorpus[]
                  ).slice(0, 5)"
                  :key="corpusIdx"
                  class="structured-corpus"
                  :class="{ 'mt-3': corpusIdx > 0 }"
                >
                  <div class="template-badge">
                    <Tag color="blue">{{ corpusItem.template_code }}</Tag>
                  </div>
                  <div class="corpus-fields">
                    <div
                      v-for="(value, key) in corpusItem.fields"
                      :key="`${corpusIdx}-${key}`"
                      class="field-item"
                    >
                      <span class="field-label">{{ key }}</span>
                      <span class="field-value">{{ value }}</span>
                    </div>
                  </div>
                </div>
                <div
                  v-if="(selectedNode.corpus as StructuredCorpus[]).length > 5"
                  class="corpus-more"
                >
                  还有
                  {{ (selectedNode.corpus as StructuredCorpus[]).length - 5 }}
                  条语料...
                </div>
              </template>
              <!-- 传统语料列表 -->
              <template v-else-if="isCorpusItemArray(selectedNode.corpus)">
                <div class="corpus-list">
                  <div
                    v-for="(item, index) in (
                      selectedNode.corpus as CorpusItem[]
                    ).slice(0, 10)"
                    :key="index"
                    class="corpus-item"
                  >
                    <span class="corpus-index">{{ index + 1 }}</span>
                    <span class="corpus-text">{{ item.text }}</span>
                    <span v-if="item.weight" class="corpus-weight">
                      {{ item.weight }}
                    </span>
                  </div>
                  <div
                    v-if="(selectedNode.corpus as CorpusItem[]).length > 10"
                    class="corpus-more"
                  >
                    还有
                    {{ (selectedNode.corpus as CorpusItem[]).length - 10 }}
                    条语料...
                  </div>
                </div>
              </template>
            </div>
          </div>

          <!-- 属性信息 -->
          <div v-if="hasProperties(selectedNode)" class="content-section">
            <div class="section-header">
              <span class="section-icon">⚙️</span>
              <span class="section-title">属性信息</span>
            </div>
            <div class="section-body">
              <div class="properties-container">
                <div
                  v-for="(value, key) in selectedNode.properties"
                  :key="String(key)"
                  class="property-card"
                >
                  <div class="property-header">
                    <span class="property-name">{{ String(key) }}</span>
                    <span
                      v-if="isSimpleValue(value)"
                      class="property-value-simple"
                    >
                      {{ formatPropertyValue(value) }}
                    </span>
                  </div>

                  <!-- 复杂值展示 -->
                  <div
                    v-if="!isSimpleValue(value)"
                    class="property-value-complex"
                  >
                    <!-- 特殊处理 path 字段 -->
                    <div
                      v-if="key === 'path' && Array.isArray(value)"
                      class="path-breadcrumb"
                    >
                      <template v-for="(p, idx) in value" :key="idx">
                        <Tag
                          :color="idx === value.length - 1 ? 'blue' : 'default'"
                        >
                          {{ p }}
                        </Tag>
                        <span
                          v-if="idx < value.length - 1"
                          class="breadcrumb-separator"
                        >
                          /
                        </span>
                      </template>
                    </div>
                    <!-- 其他复杂对象/长文本 -->
                    <div v-else class="json-value">
                      {{ formatPropertyValue(value) }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 关联关系 -->
          <div class="content-section">
            <div class="section-header">
              <span class="section-icon">🔗</span>
              <span class="section-title">关联关系</span>
              <span class="section-count">
                {{
                  selectedNodeEdges.outgoing.length +
                  selectedNodeEdges.incoming.length
                }}
              </span>
            </div>
            <div class="section-body">
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
                @click="item.node && handleNodeClick(item.node)"
              >
                <div class="relation-item-content">
                  <span class="relation-node-icon">{{
                    item.node ? getNodeIcon(item.node.label) : '📄'
                  }}</span>
                  <span class="relation-node-name">
                    {{ item.node?.name || item.edge.targetName || '未知节点' }}
                  </span>
                </div>
                <span class="relation-type-tag outgoing">
                  → {{ getRelationDisplayName(item.edge.relationType) }}
                </span>
              </div>

              <!-- 入边关联 -->
              <div
                v-for="item in selectedNodeEdges.incoming"
                :key="`in-${item.edge.id}`"
                class="relation-item"
                @click="item.node && handleNodeClick(item.node)"
              >
                <div class="relation-item-content">
                  <span class="relation-node-icon">{{
                    item.node ? getNodeIcon(item.node.label) : '📄'
                  }}</span>
                  <span class="relation-node-name">
                    {{ item.node?.name || item.edge.sourceName || '未知节点' }}
                  </span>
                </div>
                <span class="relation-type-tag incoming">
                  ← {{ getRelationDisplayName(item.edge.relationType) }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </template>
    </Drawer>
  </div>
</template>

<style scoped>
@keyframes spin {
  0% {
    transform: rotate(0deg);
  }

  100% {
    transform: rotate(360deg);
  }
}

@keyframes slide-up {
  from {
    opacity: 0;
    transform: translateY(20px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.graph-3d-container {
  position: relative;
  width: 100%;
  height: 700px;
  overflow: hidden;
  background: hsl(var(--background-deep));
  border-radius: 12px;
  transition: all 0.3s ease;
}

.graph-3d-container.fullscreen {
  position: fixed;
  inset: 0;
  z-index: 9999;
  width: 100vw;
  height: 100vh;
  border-radius: 0;
}

.graph-3d-container.dark {
  background: #0a0a0f;
}

.graph-3d-container:not(.dark) {
  background: #f0f2f5;
}

.graph-canvas {
  width: 100%;
  height: 100%;
}

/* WebGL 错误提示 */
.webgl-error {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 100;
  max-width: 600px;
  padding: 40px 60px;
  text-align: center;
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  border: 1px solid rgb(255 107 107 / 30%);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgb(0 0 0 / 50%);
  transform: translate(-50%, -50%);
}

.webgl-error .error-icon {
  margin-bottom: 16px;
  font-size: 64px;
}

.webgl-error h3 {
  margin-bottom: 12px;
  font-size: 24px;
  color: #ff6b6b;
}

.webgl-error p {
  margin-bottom: 24px;
  font-size: 16px;
  color: #a0a0a0;
}

.webgl-error .error-solutions {
  padding: 16px 20px;
  margin-bottom: 20px;
  text-align: left;
  background: rgb(255 255 255 / 5%);
  border-radius: 8px;
}

.webgl-error .error-solutions h4 {
  margin-bottom: 12px;
  font-size: 14px;
  color: #fff;
}

.webgl-error .error-solutions ul {
  padding: 0;
  margin: 0;
  list-style: none;
}

.webgl-error .error-solutions li {
  padding: 6px 0;
  font-size: 13px;
  color: #c0c0c0;
  border-bottom: 1px solid rgb(255 255 255 / 5%);
}

.webgl-error .error-solutions li:last-child {
  border-bottom: none;
}

.webgl-error .error-solutions code {
  padding: 2px 6px;
  font-size: 12px;
  color: #4ecdc4;
  background: rgb(78 205 196 / 20%);
  border-radius: 4px;
}

.webgl-error .fallback-tip {
  padding: 12px 16px;
  font-size: 14px;
  color: #4ecdc4;
  background: rgb(78 205 196 / 10%);
  border-radius: 8px;
}

/* 左侧控制面板 */
.control-panel.left-panel {
  position: absolute;
  top: 70px;
  left: 16px;
  z-index: 100;
  width: 220px;
  max-height: calc(100% - 100px);
  padding: 16px;
  overflow-y: auto;
  background: hsl(var(--card) / 90%);
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  backdrop-filter: blur(12px);
}

.dark .control-panel.left-panel {
  background: rgb(0 0 0 / 75%);
  border-color: rgb(255 255 255 / 10%);
}

.panel-header {
  display: flex;
  gap: 8px;
  align-items: center;
  padding-bottom: 12px;
  margin-bottom: 16px;
  font-size: 14px;
  font-weight: 600;
  color: hsl(var(--foreground));
  border-bottom: 1px solid hsl(var(--border));
}

.dark .panel-header {
  color: #fff;
  border-bottom-color: rgb(255 255 255 / 10%);
}

.panel-section {
  margin-bottom: 16px;
}

.section-title {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
}

.dark .section-title {
  color: rgb(255 255 255 / 70%);
}

.type-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.type-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 8px;
  cursor: pointer;
  background: hsl(var(--muted) / 30%);
  border-radius: 6px;
  transition: all 0.2s ease;
}

.dark .type-item {
  background: rgb(255 255 255 / 5%);
}

.type-item:hover {
  background: hsl(var(--muted) / 50%);
}

.dark .type-item:hover {
  background: rgb(255 255 255 / 15%);
}

.type-item.active {
  background: hsl(var(--primary) / 20%);
  box-shadow: 0 0 12px hsl(var(--primary) / 20%);
}

.dark .type-item.active {
  background: rgb(255 255 255 / 25%);
  box-shadow: 0 0 12px rgb(255 255 255 / 20%);
}

.type-dot {
  flex-shrink: 0;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.type-line {
  flex-shrink: 0;
  width: 16px;
  height: 3px;
  border-radius: 2px;
}

.type-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: hsl(var(--foreground) / 85%);
  white-space: nowrap;
}

.dark .type-name {
  color: rgb(255 255 255 / 85%);
}

.relation-item.conflict .type-name {
  color: #ff6b6b;
}

.search-results {
  max-height: 150px;
  margin-top: 8px;
  overflow-y: auto;
}

.search-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 8px;
  font-size: 12px;
  color: hsl(var(--foreground) / 85%);
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.2s;
}

.dark .search-item {
  color: rgb(255 255 255 / 85%);
}

.search-item:hover {
  background: hsl(var(--muted) / 50%);
}

.dark .search-item:hover {
  background: rgb(255 255 255 / 10%);
}

.node-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

/* 顶部工具栏 */
.toolbar {
  position: absolute;
  top: 16px;
  left: 50%;
  z-index: 100;
  padding: 8px 16px;
  background: hsl(var(--card) / 90%);
  border: 1px solid hsl(var(--border));
  border-radius: 24px;
  backdrop-filter: blur(12px);
  transform: translateX(-50%);
}

.dark .toolbar {
  background: rgb(0 0 0 / 75%);
  border-color: rgb(255 255 255 / 10%);
}

.toolbar-group {
  display: flex;
  gap: 8px;
  align-items: center;
}

.slider-group {
  display: flex;
  gap: 8px;
  align-items: center;
}

.slider-label {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
}

.dark .slider-label {
  color: rgb(255 255 255 / 70%);
}

/* 高亮提示 */
.highlight-info {
  position: absolute;
  bottom: 60px;
  left: 50%;
  z-index: 100;
  padding: 8px 20px;
  font-size: 13px;
  color: hsl(var(--foreground));
  background: hsl(var(--card) / 90%);
  border: 1px solid hsl(var(--border));
  border-radius: 20px;
  backdrop-filter: blur(8px);
  transform: translateX(-50%);
}

.dark .highlight-info {
  color: #fff;
  background: rgb(0 0 0 / 85%);
  border-color: rgb(255 255 255 / 10%);
}

/* 统计面板 */
.stats-panel {
  position: absolute;
  right: 16px;
  bottom: 16px;
  z-index: 100;
  display: flex;
  gap: 16px;
  padding: 12px 20px;
  background: hsl(var(--card) / 90%);
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  backdrop-filter: blur(12px);
}

.dark .stats-panel {
  background: rgb(0 0 0 / 75%);
  border-color: rgb(255 255 255 / 10%);
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-value {
  font-size: 24px;
  font-weight: bold;
  color: hsl(var(--foreground));
}

.dark .stat-value {
  color: #fff;
}

.stat-label {
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.dark .stat-label {
  color: rgb(255 255 255 / 50%);
}

/* 3D模式标签 */
.mode-badge {
  position: absolute;
  top: 16px;
  right: 16px;
  z-index: 100;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 20px;
  box-shadow: 0 4px 15px rgb(102 126 234 / 40%);
}

/* 边列表（旧样式，兼容保留） */
.edge-item {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 6px 0;
  font-size: 13px;
  color: hsl(var(--foreground));
  border-bottom: 1px dashed hsl(var(--border));
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
  color: hsl(var(--muted-foreground));
}

.dark .relation-section-title {
  color: #666;
}

.relation-empty {
  padding: 24px;
  font-size: 13px;
  color: #999;
  text-align: center;
  background: hsl(var(--muted) / 20%);
  border: 1px dashed hsl(var(--border));
  border-radius: 12px;
}

.dark .relation-empty {
  background: rgb(255 255 255 / 3%);
  border-color: rgb(255 255 255 / 10%);
}

.relation-item {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  margin-bottom: 8px;
  cursor: pointer;
  background: hsl(var(--muted) / 30%);
  border-radius: 12px;
  transition: all 0.2s ease;
}

.dark .relation-item {
  background: rgb(255 255 255 / 5%);
}

.relation-item:hover {
  background: hsl(var(--muted) / 50%);
  transform: translateX(4px);
}

.dark .relation-item:hover {
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
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.dark .relation-node-name {
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

/* 边详情卡片（新样式） */
.edge-detail-card {
  padding: 12px;
  margin-bottom: 12px;
  background: hsl(var(--muted) / 20%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  transition: all 0.2s ease;
}

.edge-detail-card:hover {
  background: hsl(var(--muted) / 30%);
  box-shadow: 0 2px 8px hsl(var(--primary) / 10%);
}

.dark .edge-detail-card {
  background: rgb(255 255 255 / 5%);
  border-color: rgb(255 255 255 / 10%);
}

.dark .edge-detail-card:hover {
  background: rgb(255 255 255 / 10%);
  box-shadow: 0 2px 8px rgb(255 255 255 / 5%);
}

.edge-relation {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
}

.edge-relation .arrow {
  font-weight: bold;
  color: hsl(var(--muted-foreground));
}

.target-node-info,
.source-node-info {
  padding: 8px;
  background: hsl(var(--card));
  border-radius: 6px;
}

.dark .target-node-info,
.dark .source-node-info {
  background: rgb(255 255 255 / 3%);
}

.node-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}

.node-icon {
  flex-shrink: 0;
  font-size: 16px;
}

.node-name {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.dark .node-name {
  color: rgb(255 255 255 / 90%);
}

.node-description {
  padding: 6px 8px;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.5;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted) / 20%);
  border-radius: 4px;
}

.dark .node-description {
  color: rgb(255 255 255 / 60%);
  background: rgb(255 255 255 / 5%);
}

.edge-explanation {
  padding: 6px 10px;
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.4;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 10%);
  border-left: 3px solid hsl(var(--primary));
  border-radius: 4px;
}

.dark .edge-explanation {
  color: rgb(255 255 255 / 80%);
  background: rgb(255 255 255 / 8%);
  border-left-color: hsl(var(--primary));
}

/* 深色模式下的输入框 */
.dark :deep(.ant-input) {
  color: #fff !important;
  background: rgb(255 255 255 / 10%) !important;
  border-color: rgb(255 255 255 / 20%) !important;
}

.dark :deep(.ant-input::placeholder) {
  color: rgb(255 255 255 / 40%) !important;
}

.dark :deep(.ant-input-clear-icon) {
  color: rgb(255 255 255 / 50%) !important;
}

.dark :deep(.ant-slider-rail) {
  background: rgb(255 255 255 / 20%) !important;
}

:deep(.ant-slider-track) {
  background: hsl(var(--primary)) !important;
}

:deep(.ant-slider-handle) {
  border-color: hsl(var(--primary)) !important;
}

.dark :deep(.ant-divider) {
  border-color: rgb(255 255 255 / 20%) !important;
}

/* Loading 遮罩层 */
.loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: hsl(var(--background) / 95%);
  backdrop-filter: blur(12px);
}

.dark .loading-overlay {
  background: rgb(10 10 15 / 95%);
}

.loading-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
  align-items: center;
  padding: 40px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 16px;
  box-shadow:
    0 20px 60px rgb(0 0 0 / 20%),
    0 0 0 1px rgb(255 255 255 / 5%);
}

.dark .loading-content {
  background: rgb(20 20 30 / 90%);
  border-color: rgb(255 255 255 / 10%);
}

/* Loading 旋转动画 */
.loading-spinner {
  position: relative;
  width: 80px;
  height: 80px;
}

.spinner-ring {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  border: 4px solid transparent;
  border-top-color: hsl(var(--primary));
  border-radius: 50%;
  animation: spin 1.2s cubic-bezier(0.5, 0, 0.5, 1) infinite;
}

.spinner-ring:nth-child(1) {
  border-top-color: hsl(var(--primary));
  animation-delay: -0.45s;
}

.spinner-ring:nth-child(2) {
  border-top-color: hsl(var(--primary) / 60%);
  animation-delay: -0.3s;
}

.spinner-ring:nth-child(3) {
  border-top-color: hsl(var(--primary) / 30%);
  animation-delay: -0.15s;
}

.loading-text {
  font-size: 16px;
  font-weight: 600;
  color: hsl(var(--foreground));
  text-align: center;
}

.dark .loading-text {
  color: rgb(255 255 255 / 90%);
}

.loading-hint {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.dark .loading-hint {
  color: rgb(255 255 255 / 50%);
}

/* Loading 淡入淡出动画 */
.loading-fade-enter-active {
  transition: all 0.3s ease-out;
}

.loading-fade-leave-active {
  transition: all 0.3s ease-in;
}

.loading-fade-enter-from {
  opacity: 0;
  transform: scale(0.95);
}

.loading-fade-leave-to {
  opacity: 0;
  transform: scale(1.05);
}

.loading-fade-enter-to,
.loading-fade-leave-from {
  opacity: 1;
  transform: scale(1);
}

/* Loading 内容子元素动画 */
.loading-fade-enter-active .loading-content {
  animation: slide-up 0.4s ease-out;
}

/* 子图模式面板 */
.subgraph-panel {
  padding: 12px;
  margin-top: 8px;
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 15%) 0%,
    hsl(var(--primary) / 5%) 100%
  );
  border: 1px solid hsl(var(--primary) / 30%);
  border-radius: 8px;
}

.dark .subgraph-panel {
  background: linear-gradient(
    135deg,
    rgb(102 126 234 / 20%) 0%,
    rgb(102 126 234 / 5%) 100%
  );
  border-color: rgb(102 126 234 / 30%);
}

.subgraph-info {
  margin-bottom: 12px;
}

.hops-control {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.hops-label {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.dark .hops-label {
  color: rgb(255 255 255 / 70%);
}

.hops-buttons {
  display: flex;
  gap: 6px;
}

.hops-buttons :deep(.ant-btn) {
  flex: 1;
  min-width: 0;
}

.exit-btn {
  margin-top: 8px;
}

/* =============================================
   节点详情抽屉样式
   ============================================= */

/* 抽屉头部 */
.drawer-header {
  padding: 20px 24px;
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 8%) 0%,
    hsl(var(--primary) / 3%) 100%
  );
  border-bottom: 1px solid hsl(var(--border));
}

.node-type-badge {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}

.type-indicator {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  box-shadow: 0 0 8px currentcolor;
}

.type-icon {
  font-size: 18px;
}

.type-text {
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
}

.node-title {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 600;
  line-height: 1.4;
  color: hsl(var(--foreground));
}

/* .node-description 已在前面定义，此处删除重复 */

/* 操作按钮区域 */
.drawer-actions {
  display: flex;
  gap: 12px;
  padding: 16px 24px;
  border-bottom: 1px solid hsl(var(--border));
}

.drawer-actions :deep(.ant-btn) {
  flex: 1;
}

/* 内容区域 */
.drawer-content {
  padding: 0;
  overflow-y: auto;
}

/* 内容分区 */
.content-section {
  border-bottom: 1px solid hsl(var(--border));
}

.content-section:last-child {
  border-bottom: none;
}

.section-header {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 16px 24px 12px;
  background: hsl(var(--muted) / 20%);
}

.section-icon {
  font-size: 16px;
}

/* .section-title 已在前面定义，此处删除重复 */

.section-count {
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 500;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 10%);
  border-radius: 10px;
}

.section-body {
  padding: 0 24px 16px;
}

/* 结构化语料 */
.structured-corpus {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.template-badge {
  padding-top: 8px;
}

.corpus-fields {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  background: hsl(var(--muted) / 30%);
  border-radius: 8px;
}

.field-label {
  font-size: 12px;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
}

.field-value {
  font-size: 14px;
  line-height: 1.6;
  color: hsl(var(--foreground));
  overflow-wrap: break-word;
  white-space: pre-wrap;
}

/* 传统语料列表 */
.corpus-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 8px;
}

.corpus-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 10px 12px;
  background: hsl(var(--muted) / 30%);
  border-radius: 8px;
  transition: background 0.2s;
}

.corpus-item:hover {
  background: hsl(var(--muted) / 50%);
}

.corpus-index {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  font-size: 11px;
  font-weight: 600;
  line-height: 20px;
  color: hsl(var(--primary));
  text-align: center;
  background: hsl(var(--primary) / 15%);
  border-radius: 50%;
}

.corpus-text {
  flex: 1;
  font-size: 14px;
  line-height: 1.5;
  color: hsl(var(--foreground));
  overflow-wrap: break-word;
}

.corpus-weight {
  flex-shrink: 0;
  padding: 2px 6px;
  font-size: 11px;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted) / 50%);
  border-radius: 4px;
}

.corpus-more {
  padding: 8px 12px;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
  text-align: center;
  background: hsl(var(--muted) / 20%);
  border-radius: 8px;
}

/* 属性展示优化 */
.properties-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.property-card {
  display: flex;
  flex-direction: column;
  padding: 10px 12px;
  background: hsl(var(--muted) / 20%);
  border: 1px solid hsl(var(--border) / 50%);
  border-radius: 8px;
  transition: all 0.2s;
}

.property-card:hover {
  background: hsl(var(--muted) / 40%);
  border-color: hsl(var(--border));
}

.property-header {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  justify-content: space-between;
}

.property-name {
  flex-shrink: 0;
  padding: 2px 6px;
  font-size: 11px;
  font-weight: 600;
  color: hsl(var(--muted-foreground));
  text-transform: uppercase;
  letter-spacing: 0.5px;
  background: hsl(var(--background));
  border-radius: 4px;
}

.property-value-simple {
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--foreground));
  text-align: right;
  overflow-wrap: break-word;
}

.property-value-complex {
  padding-top: 10px;
  margin-top: 10px;
  border-top: 1px dashed hsl(var(--border) / 50%);
}

.path-breadcrumb {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.breadcrumb-separator {
  margin: 0 2px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.json-value {
  padding: 8px;
  margin: 0;
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
  color: hsl(var(--foreground));
  white-space: pre-wrap;
  background: hsl(var(--background));
  border-radius: 4px;
}

/* 关系项优化 */
.relation-type-tag.outgoing {
  color: #00d4aa;
  background: rgb(0 212 170 / 12%);
}

.relation-type-tag.incoming {
  color: #60a5fa;
  background: rgb(96 165 250 / 12%);
}

.relation-item:hover .relation-type-tag.outgoing {
  background: rgb(0 212 170 / 20%);
  box-shadow: 0 0 12px rgb(0 212 170 / 30%);
}

.relation-item:hover .relation-type-tag.incoming {
  background: rgb(96 165 250 / 20%);
  box-shadow: 0 0 12px rgb(96 165 250 / 30%);
}

/* 抽屉滚动条美化 */
.node-detail-drawer :deep(.ant-drawer-body) {
  overflow-y: auto;
}

.node-detail-drawer :deep(.ant-drawer-body::-webkit-scrollbar) {
  width: 6px;
}

.node-detail-drawer :deep(.ant-drawer-body::-webkit-scrollbar-track) {
  background: transparent;
}

.node-detail-drawer :deep(.ant-drawer-body::-webkit-scrollbar-thumb) {
  background: hsl(var(--muted-foreground) / 30%);
  border-radius: 3px;
}

.node-detail-drawer :deep(.ant-drawer-body::-webkit-scrollbar-thumb:hover) {
  background: hsl(var(--muted-foreground) / 50%);
}
</style>
