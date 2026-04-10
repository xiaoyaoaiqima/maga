/**
 * RLHF 数据类型定义
 */

/** RLHF 审查统计 */
export interface RLHFInspectionStats {
  total_inspection_count: number;
  passed_count: number;
  failed_count: number;
  pass_rate: number;
  avg_score: number;
  score_distribution: {
    excellent: number; // >= 90
    fair: number; // 60-79
    good: number; // 80-89
    poor: number; // < 60
  };
  // 专家统计
  expert_count?: number;
  // 问题标签统计
  illegal_count?: number;
  non_compliant_count?: number;
  unreasonable_count?: number;
  off_purpose_count?: number;
  // 喜欢采纳反馈
  like_count?: number;
  like_rate?: number;
  dislike_count?: number;
  dislike_rate?: number;
}

/** RLHF 评分维度（用于雷达图） */
export interface RLHFScoreDimension {
  dimension: string;
  score: number;
  full_score: number;
}

/** RLHF 问题标签分布 */
export interface RLHFIssueTagDistribution {
  tag_id?: number;
  tag: string;
  tag_name?: string;
  tag_category?:
    | 'illegal'
    | 'non_compliant'
    | 'off_purpose'
    | 'other'
    | 'unreasonable';
  count: number;
  percentage?: number;
  article_count?: number;
}

/** RLHF 审查详情记录 */
export interface RLHFInspectionDetailItem {
  id: string;
  content_id: string;
  title: string;
  content: string;
  score: number;
  status: 'failed' | 'passed';
  inspector_id?: string;
  inspector_name?: string;
  inspected_at?: string;
  tags: string[];
  feedback?: string;
  dimensions?: RLHFScoreDimension[];
}

/** RLHF 改进记录 */
export interface RLHFImprovementItem {
  id: string;
  issue: string;
  improvement_action: string;
  status: 'completed' | 'in_progress' | 'pending';
  created_at: string;
  updated_at?: string;
}

/** RLHF 查询参数 */
export interface RLHFQueryParams {
  tenant_code?: string;
  activity_id?: string;
  agent_id?: string;
  agent_code?: string;
  start_date?: string;
  end_date?: string;
  inspector_id?: string;
  status?: 'all' | 'failed' | 'passed';
  page?: number;
  page_size?: number;
}

/** RLHF 统计响应 */
export interface RLHFStatsResponse {
  stats: RLHFInspectionStats;
  dimensions: RLHFScoreDimension[];
  issue_tags: RLHFIssueTagDistribution[];
}

/** RLHF 列表响应 */
export interface RLHFListResponse {
  items: RLHFInspectionDetailItem[];
  total: number;
  page: number;
  page_size: number;
}
