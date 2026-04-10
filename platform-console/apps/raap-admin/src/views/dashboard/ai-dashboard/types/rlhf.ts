/**
 * RLHF 人工专家反馈类型定义
 *
 * 包含抽检统计、问题标签、雷达图评分等相关类型
 */

/** RLHF 人工专家反馈报告数据类型 */
export interface RLHFInspectionStats {
  total_inspection_count: number;
  like_count: number;
  dislike_count: number;
  like_rate: number;
  dislike_rate: number;
  like_edit_rate: number;
  /** 人工专家总数 */
  expert_count?: number;
  /** 不合法 */
  illegal_count?: number;
  /** 不合规 */
  non_compliant_count?: number;
  /** 不合理 */
  unreasonable_count?: number;
  /** 不合目的 */
  off_purpose_count?: number;
}

/** RLHF 雷达图评分维度 */
export interface RLHFScoreDimension {
  name: string;
  value: number;
  /** AI模型评分（用于对比图） */
  modelScore?: number;
  /** 抽检评分（用于对比图） */
  inspectionScore?: number;
  /** 差异百分比 */
  diff?: number;
}

export interface RLHFIssueTagDistribution {
  tag_id: number;
  tag_name: string;
  tag_category: string;
  count: number;
}

export interface RLHFIssueTagWordCloud {
  name: string;
  value: number;
}

/** 反馈词文章列表项 */
export interface FeedbackTagArticleItem {
  article_id: number;
  title: string;
  content_preview: string;
  create_time: string;
}

/** RLHF 抽检详情数据类型 */
export interface RLHFInspectionDetailItem {
  article_id: number;
  inspection_title: null | string;
  content_preview: null | string;
  inspection_result: string;
  inspector_name: null | string;
  inspection_time: null | string;
  modified_title: null | string;
  modified_content_preview: null | string;
}

/** RLHF 改进点摘要数据类型 */
export interface RLHFImprovementItem {
  feedback_id: number;
  selected_text: null | string;
  comment: null | string;
  user_name: null | string;
  create_time: null | string;
}
