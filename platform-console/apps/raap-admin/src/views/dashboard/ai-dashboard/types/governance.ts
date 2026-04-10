/**
 * 治理中心类型定义
 *
 * 包含人设统计、Agent 质量评分等相关类型
 */

/** 治理中心数据类型 */
export interface PersonaStats {
  /** 人设数量 */
  persona_count: number;
  /** 有人设的内容数 */
  with_persona_count: number;
  /** 总内容数 */
  total_count: number;
  /** 人设适配占比 */
  persona_ratio: number;
}

export interface PersonaDistribution {
  /** 人设名称 */
  persona_name: string;
  /** 内容数量 */
  content_count: number;
}

/** Agent六维评分数据类型 */
export interface AgentQualityScore {
  agent_code: string;
  agent_name: null | string;
  marketing_score: null | number;
  grace_score: null | number;
  quality_score: null | number;
  brand_score: null | number;
  creativity_score: null | number;
  persona_score: null | number;
  avg_score: null | number;
  content_count: number;
}
