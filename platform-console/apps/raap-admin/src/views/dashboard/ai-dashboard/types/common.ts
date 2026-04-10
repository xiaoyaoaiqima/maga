/**
 * 通用类型定义
 *
 * 包含跨模块使用的通用类型
 */

/** 内容转化漏斗数据 */
export interface FunnelStage {
  id: string;
  label: string;
  count: number;
  percentage: number;
  icon?: string;
  color: string;
  description?: string;
}
