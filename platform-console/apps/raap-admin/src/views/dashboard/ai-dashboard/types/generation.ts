/**
 * AIGC 生成中心类型定义
 *
 * 包含任务列表、Agent 统计、趋势等相关类型
 */

/** AIGC生成中心任务列表数据类型 */
export interface JobTaskItem {
  job_id: string;
  job_name: string;
  agent_code: string;
  agent_name: null | string;
  status: string;
  target_count: null | number;
  content_count: number;
  start_time: null | string;
  end_time: null | string;
}

/** 生成中心数据类型（兼容新旧字段名） */
export interface AgentStat {
  agent_code: string;
  agent_name?: null | string;
  /** 新字段名：生成数量（从 content 表统计） */
  content_count?: number;
  /** 新字段名：调用次数（从 expert_call_trace 表统计） */
  call_count?: number;
  /** 新字段名：是否运行中（0/1，从 job 表 DEPLOYED 状态判断） */
  is_running?: number;
  /** 旧字段名：调用次数 */
  total_calls?: number;
  /** 旧字段名：运行中数量 */
  running_count?: number | string;
}

export interface AgentTrend {
  agent_code: string;
  call_count: number;
  date: string;
}

/** 每日生成文章数量趋势 */
export interface AgentContentTrend {
  agent_code: string;
  content_count: number;
  date: string;
}
