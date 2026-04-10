/**
 * 成本模块类型定义
 *
 * 包含 AI 算力成本相关的所有类型
 */

/** 注意：后端返回的 total_cost 是字符串类型 */
export interface AgentCostItem {
  agent_code: string;
  agent_name: null | string;
  currency: string;
  total_cost: number | string;
  job_count: number;
  content_count: number;
}

export interface JobCostItem {
  job_id: string;
  job_name: string;
  agent_code: string;
  agent_name: null | string;
  currency: string;
  total_cost: number | string;
  content_count: number;
  start_time: string;
  end_time: string;
}

export interface TotalCostItem {
  currency: string;
  total_cost: number | string;
  agent_count: number;
  job_count: number;
  content_count: number;
}
