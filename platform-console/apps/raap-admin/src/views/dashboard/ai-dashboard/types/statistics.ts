/**
 * 统计学专家组类型定义
 *
 * 包含人群多样性热力图等相关类型
 */

/** 统计学专家组 - 人群多样性热力图数据类型 */
export interface AgentPersonaHeatmapItem {
  agent_code: string;
  agent_name: null | string;
  persona_name: string;
  content_count: number;
}

/** 统计学专家组统计 */
export interface StatisticsExpertStats {
  /** 总审核文章数 */
  total_reviewed_count: number;
}
