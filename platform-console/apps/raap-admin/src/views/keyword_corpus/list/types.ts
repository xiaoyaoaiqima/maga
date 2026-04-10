// =============================================
// 图数据库核心类型定义（基于 plan.md 设计）
// =============================================

// 节点类型枚举
export type NodeLabel =
  | 'DIM_EMOTION' // 情绪维度（如：焦虑、暴躁、愧疚）
  | 'DIM_IDENTITY' // 人设（如：职场妈妈、全职妈妈）
  | 'DIM_LANG' // 语言表达（如：口语化、咆哮体、专业范）
  | 'DIM_MOTIVE' // 动机维度（如：求助、避雷、种草）
  | 'FEATURE' // 卖点（如：进阶保护力）
  | 'FEATURE_CORPUS' // 卖点语料
  | 'PAIN' // 痛点（如：体质弱、挑食）
  | 'PERSONA_ROOT' // 人设聚合点（如：皇3目标人群、泛焦虑妈妈群体）
  | 'SCENE'; // 场景（如：换季、入园、户外）

// 关系类型枚举（小学生都能懂的命名！）
export type RelationType =
  | 'CONFLICTS_WITH' // 维度 ↔ 维度：「不适合搭配」
  | 'ENCOUNTERS' // 身份 → 场景：「会遇到」
  | 'FITS_WITH' // 维度 ↔ 维度：「适合搭配」
  | 'FIXES' // 卖点 → 痛点：「解决」
  | 'INCLUDES' // 人设 → 维度：「包含」
  | 'LEADS_TO' // 场景 → 痛点：「导致」
  | 'SAYS_AS'; // 卖点 → 语料：「可以这样说」

// 节点类型元数据
export interface NodeLabelMeta {
  label: NodeLabel;
  displayName: string;
  description: string;
  color: string;
  icon: string;
}

// 关系类型元数据
export interface RelationLabelMeta {
  relationType: RelationType;
  displayName: string;
  description: string;
  sourceLabel: NodeLabel[];
  targetLabel: NodeLabel[];
  lineColor: string;
  lineStyle?: 'dashed' | 'solid';
}

// 语料项类型
export interface CorpusItem {
  text: string;
  weight?: number;
}

// 结构化语料类型
export interface StructuredCorpus {
  template_code: string;
  fields: Record<string, string>;
}

// 兼容新旧格式的语料类型
export type CorpusValue = CorpusItem[] | StructuredCorpus;

// 图节点
export interface GraphNode {
  id: string; // 后端序列化为字符串，避免 JS 大整数精度丢失
  tenantId: string;
  label: NodeLabel | string; // 兼容动态 label 类型
  name: string;
  description?: string;
  corpus?: CorpusValue; // 语料内容
  aiInstruction?: Record<string, unknown>;
  properties?: Record<string, unknown>;
  status: 0 | 1;
  isDeleted: 0 | 1;
  createdBy?: string;
  updatedBy?: string;
  createdAt: string;
  updatedAt: string;
}

// 图边
export interface GraphEdge {
  id: string; // 后端序列化为字符串，避免 JS 大整数精度丢失
  tenantId: string;
  sourceNodeId: string;
  targetNodeId: string;
  relationType: RelationType;
  explanation?: string;
  weight: number;
  priority: number;
  metaData?: Record<string, unknown>;
  status: 0 | 1;
  isDeleted: 0 | 1;
  createdBy?: string;
  updatedBy?: string;
  createdAt: string;
  updatedAt: string;
  // 冗余字段用于显示
  sourceName?: string;
  targetName?: string;
  sourceLabel?: NodeLabel;
  targetLabel?: NodeLabel;
}

// 类型定义已迁移到各子目录
// Persona -> ./persona/types.ts
// Scenario -> ./scenario/types.ts
// SellingPoint -> ./selling_point/types.ts

// =============================================
// 节点类型配置（用于前端展示）
// =============================================
export const NODE_LABEL_CONFIG: Record<NodeLabel, NodeLabelMeta> = {
  PERSONA_ROOT: {
    label: 'PERSONA_ROOT',
    displayName: '人设聚合点',
    description: '目标人群的聚合定义，如：皇3目标人群、泛焦虑妈妈群体',
    color: '#722ed1',
    icon: 'TeamOutlined',
  },
  DIM_IDENTITY: {
    label: 'DIM_IDENTITY',
    displayName: '人设',
    description: '用户的身份标签，如：职场妈妈、全职妈妈、成分妈妈',
    color: '#1890ff',
    icon: 'UserOutlined',
  },
  DIM_EMOTION: {
    label: 'DIM_EMOTION',
    displayName: '情绪维度',
    description: '用户的情绪状态，如：焦虑无助、欣慰自豪、暴躁崩溃',
    color: '#fa8c16',
    icon: 'SmileOutlined',
  },
  DIM_MOTIVE: {
    label: 'DIM_MOTIVE',
    displayName: '动机维度',
    description: '用户的发帖动机，如：求助网友、种草分享、避坑指南',
    color: '#52c41a',
    icon: 'AimOutlined',
  },
  DIM_LANG: {
    label: 'DIM_LANG',
    displayName: '语言表达',
    description: '内容的语言风格，如：口语化、咆哮体、专业范、温柔叙事',
    color: '#13c2c2',
    icon: 'MessageOutlined',
  },
  SCENE: {
    label: 'SCENE',
    displayName: '场景',
    description: '触发内容的场景，如：换季、入园、户外活动',
    color: '#eb2f96',
    icon: 'EnvironmentOutlined',
  },
  PAIN: {
    label: 'PAIN',
    displayName: '痛点',
    description: '用户的核心痛点，如：体质弱易生病、挑食营养不均',
    color: '#f5222d',
    icon: 'ThunderboltOutlined',
  },
  FEATURE: {
    label: 'FEATURE',
    displayName: '卖点',
    description: '产品卖点，如：进阶保护力、眼脑双引擎',
    color: '#faad14',
    icon: 'StarOutlined',
  },
  FEATURE_CORPUS: {
    label: 'FEATURE_CORPUS',
    displayName: '卖点语料',
    description: '卖点的多种表达方式',
    color: '#a0d911',
    icon: 'FileTextOutlined',
  },
};

// =============================================
// 关系类型配置（超级直观版！）
// =============================================
export const RELATION_TYPE_CONFIG: Record<RelationType, RelationLabelMeta> = {
  INCLUDES: {
    relationType: 'INCLUDES',
    displayName: '包含',
    description: '这类人群有哪些特征',
    sourceLabel: ['PERSONA_ROOT'],
    targetLabel: ['DIM_IDENTITY', 'DIM_EMOTION', 'DIM_MOTIVE', 'DIM_LANG'],
    lineColor: '#722ed1',
  },
  FITS_WITH: {
    relationType: 'FITS_WITH',
    displayName: '适合搭配',
    description: '这两个特征可以一起用',
    sourceLabel: ['DIM_IDENTITY', 'DIM_EMOTION', 'DIM_MOTIVE', 'DIM_LANG'],
    targetLabel: ['DIM_IDENTITY', 'DIM_EMOTION', 'DIM_MOTIVE', 'DIM_LANG'],
    lineColor: '#52c41a',
  },
  CONFLICTS_WITH: {
    relationType: 'CONFLICTS_WITH',
    displayName: '不适合搭配',
    description: '这两个特征不能一起用',
    sourceLabel: ['DIM_IDENTITY', 'DIM_EMOTION', 'DIM_MOTIVE', 'DIM_LANG'],
    targetLabel: ['DIM_IDENTITY', 'DIM_EMOTION', 'DIM_MOTIVE', 'DIM_LANG'],
    lineColor: '#f5222d',
    lineStyle: 'dashed',
  },
  ENCOUNTERS: {
    relationType: 'ENCOUNTERS',
    displayName: '会遇到',
    description: '这类人常常遇到的场景',
    sourceLabel: ['DIM_IDENTITY'],
    targetLabel: ['SCENE'],
    lineColor: '#eb2f96',
  },
  LEADS_TO: {
    relationType: 'LEADS_TO',
    displayName: '导致',
    description: '这个场景会引发什么问题',
    sourceLabel: ['SCENE'],
    targetLabel: ['PAIN'],
    lineColor: '#ff7a45',
  },
  FIXES: {
    relationType: 'FIXES',
    displayName: '解决',
    description: '这个卖点能解决什么问题',
    sourceLabel: ['FEATURE'],
    targetLabel: ['PAIN'],
    lineColor: '#faad14',
  },
  SAYS_AS: {
    relationType: 'SAYS_AS',
    displayName: '可以这样说',
    description: '这个卖点可以怎么表达',
    sourceLabel: ['FEATURE'],
    targetLabel: ['FEATURE_CORPUS'],
    lineColor: '#a0d911',
  },
};
