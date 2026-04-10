/**
 * vis-network 配置文件
 * 节点/边颜色映射及物理引擎配置
 *
 * 【重要】颜色算法与 Graph3DView 保持一致！
 * 1. 优先使用 NODE_LABEL_CONFIG/RELATION_TYPE_CONFIG 中的预定义颜色
 * 2. 对于未定义的类型，使用动态颜色生成（hash 算法确保稳定性）
 */

import type { NodeLabel, RelationType } from './types';

import { NODE_LABEL_CONFIG, RELATION_TYPE_CONFIG } from './types';

// =============================================
// 动态颜色生成（与 Graph3DView 共享算法）
// =============================================

// 预定义的高对比度调色板（与 Graph3DView 一致）
const DYNAMIC_COLOR_PALETTE = [
  '#FF6B6B', // 珊瑚红
  '#4ECDC4', // 青绿色
  '#45B7D1', // 天蓝色
  '#96CEB4', // 薄荷绿
  '#FFEAA7', // 柠檬黄
  '#DDA0DD', // 梅红色
  '#98D8C8', // 薄荷青
  '#F7DC6F', // 金黄色
  '#BB8FCE', // 淡紫色
  '#85C1E9', // 浅蓝色
  '#F8B500', // 橙黄色
  '#00CED1', // 深青色
  '#FF7F50', // 珊瑚橙
  '#9370DB', // 中紫色
  '#20B2AA', // 浅海绿
  '#FFB6C1', // 浅粉红
  '#87CEEB', // 天蓝
  '#DEB887', // 实木色
  '#7FFFD4', // 碧绿色
  '#FFA07A', // 浅鲑鱼色
];

// 缓存已分配的颜色
const labelColorCache = new Map<string, string>();

/**
 * 根据 label 获取稳定的动态颜色（与 Graph3DView 算法一致）
 * 使用 hash 算法确保相同 label 总是得到相同颜色
 */
export function getDynamicColor(label: string): string {
  const cached = labelColorCache.get(label);
  if (cached) {
    return cached;
  }
  // 使用 label 字符串的 hash 来选择颜色
  let hash = 0;
  for (let i = 0; i < label.length; i++) {
    hash = Math.trunc((hash << 5) - hash + (label.codePointAt(i) ?? 0));
  }
  const colorIndex = Math.abs(hash) % DYNAMIC_COLOR_PALETTE.length;
  const color = DYNAMIC_COLOR_PALETTE[colorIndex] as string;
  labelColorCache.set(label, color);
  return color;
}

// =============================================
// vis-network 节点分组配置（基于现有 NODE_LABEL_CONFIG）
// =============================================
export const VIS_NODE_GROUPS = Object.fromEntries(
  Object.entries(NODE_LABEL_CONFIG).map(([label, config]) => [
    label,
    {
      color: {
        background: config.color,
        border: config.color,
        highlight: {
          background: config.color,
          border: '#ffffff',
        },
        hover: {
          background: config.color,
          border: '#ffffff',
        },
      },
      font: {
        color: '#ffffff',
      },
    },
  ]),
);

// 默认节点样式
export const DEFAULT_NODE_STYLE = {
  color: {
    background: '#8c8c8c',
    border: '#8c8c8c',
    highlight: {
      background: '#8c8c8c',
      border: '#ffffff',
    },
  },
  font: {
    color: '#ffffff',
  },
};

// =============================================
// vis-network 边颜色映射（基于现有 RELATION_TYPE_CONFIG）
// =============================================
export const VIS_EDGE_COLORS: Record<string, string> = Object.fromEntries(
  Object.entries(RELATION_TYPE_CONFIG).map(([type, config]) => [
    type,
    config.lineColor,
  ]),
);

// 默认边颜色
export const DEFAULT_EDGE_COLOR = '#636E72';

// =============================================
// vis-network 物理引擎配置（优化性能版）
// =============================================
export const VIS_NETWORK_OPTIONS = {
  // 节点配置
  nodes: {
    shape: 'dot',
    size: 20,
    font: {
      size: 12,
      color: '#ffffff',
      face: 'SF Pro Display, -apple-system, BlinkMacSystemFont, sans-serif',
      strokeWidth: 1,
      strokeColor: 'rgba(0, 0, 0, 0.5)',
    },
    borderWidth: 2,
    shadow: {
      enabled: false, // 关闭阴影提升性能
    },
    scaling: {
      min: 10,
      max: 30,
      label: {
        enabled: true,
        min: 10,
        max: 16,
      },
    },
  },

  // 边配置
  edges: {
    width: 1,
    color: {
      color: DEFAULT_EDGE_COLOR,
      highlight: '#ffffff',
      hover: '#ffffff',
      opacity: 0.6,
    },
    font: {
      size: 0, // 默认隐藏边标签，减少渲染压力
      color: '#a0a0a0',
      strokeWidth: 0,
      align: 'middle' as const,
    },
    arrows: {
      to: {
        enabled: true,
        scaleFactor: 0.4,
        type: 'arrow' as const,
      },
    },
    smooth: {
      enabled: true,
      type: 'dynamic' as const, // 使用 dynamic 比 continuous 更快
      roundness: 0.5,
    },
    hoverWidth: 2,
    selectionWidth: 2,
  },

  // 物理引擎配置（力导向布局版）
  // 📌 优化目标：真正的力导向布局，节点有吸引力和斥力
  physics: {
    enabled: true,
    stabilization: {
      enabled: true,
      iterations: 300, // 增加迭代次数确保充分布局
      updateInterval: 25,
      onlyDynamicEdges: false,
      fit: true,
    },
    barnesHut: {
      gravitationalConstant: -8000, // 增强斥力，节点更分散
      centralGravity: 0.1, // 降低中心引力，节点更自由分布
      springLength: 200, // 增加弹簧长度，节点距离更远
      springConstant: 0.04, // 弹簧刚度
      damping: 0.09, // 降低阻尼，让节点有更多动态效果
      avoidOverlap: 0.8, // 增强防重叠
    },
    maxVelocity: 50,
    minVelocity: 0.1, // 降低阈值，让布局运行更久
    solver: 'barnesHut' as const,
    timestep: 0.5,
  },

  // 交互配置
  interaction: {
    hover: true,
    hoverConnectedEdges: true,
    selectConnectedEdges: true,
    tooltipDelay: 300, // 增加延迟减少 tooltip 渲染
    zoomView: true,
    dragView: true,
    dragNodes: true,
    multiselect: true,
    selectable: true,
    navigationButtons: false,
    keyboard: {
      enabled: true,
      speed: { x: 10, y: 10, zoom: 0.02 },
      bindToWindow: false,
    },
  },

  // 布局配置
  layout: {
    improvedLayout: false, // 关闭改进布局（会预先计算位置，大图慢）
    hierarchical: {
      enabled: false,
    },
  },

  // 分组配置
  groups: VIS_NODE_GROUPS,
};

// =============================================
// vis-network 树形布局配置（hierarchical）
// =============================================
export const VIS_NETWORK_TREE_OPTIONS = {
  // 节点配置
  nodes: {
    shape: 'dot',
    size: 25,
    font: {
      size: 14,
      color: '#ffffff',
      face: 'SF Pro Display, -apple-system, BlinkMacSystemFont, sans-serif',
      strokeWidth: 2,
      strokeColor: 'rgba(0, 0, 0, 0.6)',
    },
    borderWidth: 3,
    shadow: {
      enabled: true,
      color: 'rgba(0, 0, 0, 0.3)',
      size: 8,
      x: 0,
      y: 0,
    },
  },

  // 边配置
  edges: {
    width: 2,
    color: {
      color: '#8c8c8c',
      highlight: '#ffffff',
      hover: '#ffffff',
      opacity: 0.9,
    },
    font: {
      size: 0, // 隐藏边标签
    },
    arrows: {
      to: {
        enabled: true,
        scaleFactor: 0.6,
        type: 'arrow' as const,
      },
    },
    smooth: {
      enabled: true,
      type: 'cubicBezier' as const,
      forceDirection: 'vertical' as const,
      roundness: 0.5,
    },
  },

  // 树形布局关键配置（美化版：增加间距，让树更立体）
  layout: {
    hierarchical: {
      enabled: true,
      direction: 'UD' as const, // 上到下 (Up-Down)
      sortMethod: 'directed' as const, // 按边方向排序
      levelSeparation: 180, // 层级间距（增大让树更高）
      nodeSpacing: 150, // 同层节点间距（增大让节点更舒展）
      treeSpacing: 250, // 树之间间距（增大让多棵树分开）
      blockShifting: true,
      edgeMinimization: true,
      parentCentralization: true,
    },
  },

  // 树形布局禁用物理引擎
  physics: {
    enabled: false,
  },

  // 交互配置
  interaction: {
    hover: true,
    hoverConnectedEdges: true,
    selectConnectedEdges: true,
    tooltipDelay: 300,
    zoomView: true,
    dragView: true,
    dragNodes: true,
    multiselect: false,
    selectable: true,
    navigationButtons: false,
    keyboard: {
      enabled: true,
      speed: { x: 10, y: 10, zoom: 0.02 },
      bindToWindow: false,
    },
  },

  // 分组配置
  groups: VIS_NODE_GROUPS,
};

// =============================================
// 风险等级配置
// =============================================
export const RISK_LEVELS = {
  0: { label: '安全', color: '#27AE60', icon: '🟢' },
  1: { label: '低风险', color: '#3498DB', icon: '🔵' },
  2: { label: '中风险', color: '#F39C12', icon: '🟠' },
  3: { label: '高风险', color: '#E74C3C', icon: '🔴' },
};

// =============================================
// 辅助函数（与 Graph3DView 颜色算法一致）
// =============================================

/**
 * 获取节点颜色：优先使用预定义配置，否则使用动态颜色
 */
export function getNodeColor(label: NodeLabel | string): string {
  const config = NODE_LABEL_CONFIG[label as NodeLabel];
  return config?.color || getDynamicColor(label);
}

/**
 * 获取边颜色：优先使用预定义配置，否则使用动态颜色
 */
export function getEdgeColor(relationType: RelationType | string): string {
  const config = RELATION_TYPE_CONFIG[relationType as RelationType];
  return config?.lineColor || getDynamicColor(relationType);
}

/**
 * 获取节点显示名称：优先使用预定义配置，否则返回原始 label
 */
export function getNodeDisplayName(label: NodeLabel | string): string {
  const config = NODE_LABEL_CONFIG[label as NodeLabel];
  return config?.displayName || label;
}

/**
 * 获取关系显示名称：优先使用预定义配置，否则返回原始 type
 */
export function getRelationDisplayName(type: RelationType | string): string {
  const config = RELATION_TYPE_CONFIG[type as RelationType];
  return config?.displayName || type;
}

/**
 * 获取节点图标
 */
export function getNodeIcon(label: NodeLabel | string): string {
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
  return iconMap[label] || '📌';
}

/**
 * 获取节点大小（基于类型）
 */
export function getNodeSize(label: NodeLabel | string): number {
  const baseSize = 20;
  switch (label) {
    case 'DIM_EMOTION':
    case 'DIM_LANG':
    case 'DIM_MOTIVE': {
      return baseSize * 1.1;
    }
    case 'DIM_IDENTITY': {
      return baseSize * 1.3;
    }
    case 'PERSONA_ROOT': {
      return baseSize * 1.5;
    }
    default: {
      return baseSize;
    }
  }
}
