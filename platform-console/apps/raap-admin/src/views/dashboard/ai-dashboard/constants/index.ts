/**
 * AI Dashboard 常量定义
 *
 * 所有业务相关的常量集中在此文件
 */

import type { RLHFInspectionStats, ScoringExpertMeta } from '../types';

// ==================== 默认 RLHF 数据 ====================

// ==================== 成本模块 ====================

/** 美元兑人民币汇率 */
export const USD_TO_CNY_RATE = 7.5;

// ==================== 分数区间 ====================

/** 分数区间定义（从高到低排列，用于垂直渲染） */
export const SCORE_RANGES = [
  {
    id: 'r5',
    min: 80,
    max: 100,
    label: '80 - 100',
    colorClass: 'score-range-excellent',
  },
  {
    id: 'r4',
    min: 60,
    max: 79,
    label: '60 - 79',
    colorClass: 'score-range-good',
  },
  {
    id: 'r3',
    min: 40,
    max: 59,
    label: '40 - 59',
    colorClass: 'score-range-medium',
  },
  {
    id: 'r2',
    min: 20,
    max: 39,
    label: '20 - 39',
    colorClass: 'score-range-low',
  },
  {
    id: 'r1',
    min: 0,
    max: 19,
    label: '0 - 19',
    colorClass: 'score-range-poor',
  },
] as const;

// ==================== 专家样式预设 ====================

/** 专家样式预设配置 */
export const EXPERT_STYLE_PRESETS: Array<{
  bgColor: string;
  color: string;
  icon: string;
}> = [
  {
    color: '#3B82F6',
    bgColor: 'rgba(59, 130, 246, 0.15)',
    icon: '📝',
  },
  {
    color: '#8B5CF6',
    bgColor: 'rgba(139, 92, 246, 0.15)',
    icon: '💡',
  },
  {
    color: '#EF4444',
    bgColor: 'rgba(239, 68, 68, 0.15)',
    icon: '🛡️',
  },
  {
    color: '#F59E0B',
    bgColor: 'rgba(245, 158, 11, 0.15)',
    icon: '👤',
  },
  {
    color: '#10B981',
    bgColor: 'rgba(16, 185, 129, 0.15)',
    icon: '⚙️',
  },
  {
    color: '#EC4899',
    bgColor: 'rgba(236, 72, 153, 0.15)',
    icon: '✨',
  },
];

// ==================== RLHF 默认评分 ====================

/** RLHF 默认评分数据 */
export const HUMAN_RLHF_DEFAULT_SCORES = [78, 74, 81, 69, 76, 83] as const;

// ==================== 表格滚动配置 ====================

/** 滚动速度（像素/次） */
export const SCROLL_SPEED = 1;

/** 滚动间隔（毫秒） */
export const SCROLL_INTERVAL = 50;

/** 默认 RLHF 统计数据（mock） */
export const DEFAULT_RLHF_STATS: RLHFInspectionStats = {
  total_inspection_count: 0,
  like_count: 0,
  dislike_count: 0,
  like_rate: 0,
  dislike_rate: 0,
  like_edit_rate: 0,
  expert_count: 123,
  illegal_count: 20,
  non_compliant_count: 20,
  unreasonable_count: 20,
  off_purpose_count: 20,
};

// ==================== 辅助函数 ====================

/** 根据 index 获取默认人工评分 */
export function getDefaultHumanScore(index: number): number {
  if (HUMAN_RLHF_DEFAULT_SCORES.length === 0) return 76;
  return HUMAN_RLHF_DEFAULT_SCORES[index % HUMAN_RLHF_DEFAULT_SCORES.length];
}

/** 根据分数获取对应的分数区间 */
export function getScoreRange(score: number): (typeof SCORE_RANGES)[number] {
  return (
    SCORE_RANGES.find((range) => score >= range.min && score <= range.max) ||
    SCORE_RANGES[0]
  );
}

/** 构建专家元数据 */
export function buildScoringExpertMeta(
  expertFunc: string,
  expertName: string,
  index: number,
): ScoringExpertMeta {
  const style = EXPERT_STYLE_PRESETS[index % EXPERT_STYLE_PRESETS.length];
  return {
    expert_func: expertFunc,
    expert_name: expertName,
    color: style?.color || '#3B82F6',
    bgColor: style?.bgColor || 'rgba(59, 130, 246, 0.15)',
    icon: style?.icon || '✨',
    tooltip: `${expertName} 评分专家`,
  };
}
