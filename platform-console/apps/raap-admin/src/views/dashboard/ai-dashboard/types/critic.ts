/**
 * 多维度 AI 评论专家组类型定义
 *
 * 包含评论专家、评分、分数区间分布等相关类型
 */

/** 多维度AI评论专家组数据类型 */
export interface CriticContentStats {
  /** 待输入文章量 */
  pending_count: number;
  /** 总输入文章量 */
  total_input_count: number;
  /** 总拒绝文章量 */
  rejected_count: number;
  /** 总拒绝比例 */
  rejected_rate: number;
}

export interface CriticExpertStats {
  /** 专家函数名 */
  expert_func: string;
  /** 专家名称 */
  expert_name?: string;
  /** 专家类型 */
  expert_type?: string;
  /** 专家描述 */
  description?: string;
  /** 总输入量 */
  total_input: number;
  /** 拒绝量 */
  rejected_count: number;
}

/** 文章质量六维度数据类型 */
export interface QualityDimension {
  /** 专家函数名 */
  expert_func: string;
  /** 专家名称 */
  expert_name: string;
  /** 平均分 */
  avg_score: number;
}

export interface ScoringExpertMeta {
  expert_func: string;
  expert_name: string;
  color: string;
  bgColor: string;
  icon: string;
  tooltip: string;
}

/** 评分专家分数区间分布数据类型（5区间版，用于评分结果分布条形图） */
export interface CriticExpertScoreDistribution {
  /** 专家函数名，如 CriticContentQuality */
  expert_func: string;
  /** 专家名称 */
  expert_name: string;
  /** 分数区间，如 r1, r2, r3, r4, r5 */
  score_range: string;
  /** 该区间的文章数 */
  content_count: number;
}

/** 评分专家分数区间分布数据类型（10区间版，用于内容丰富度气泡图） */
export interface CriticExpertScoreDistribution10 {
  /** 专家函数名，如 CriticContentQuality */
  expert_func: string;
  /** 专家名称 */
  expert_name: string;
  /** 分数区间起始值，如 0, 10, 20, ..., 90 */
  score_range: number;
  /** 该区间的文章数 */
  content_count: number;
}

/** 粒子动画接口 */
export interface ScoreParticle {
  id: number;
  expertKey: string;
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  color: string;
  targetBucketId: string;
  score: number;
}

/** 分数桶数据类型 */
export type ScoreBucketsData = Record<string, number>;

/** 专家卡片激活状态 */
export type ActiveExperts = Record<string, boolean>;
