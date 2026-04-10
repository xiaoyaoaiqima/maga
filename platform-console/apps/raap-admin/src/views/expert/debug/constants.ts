/**
 * Expert Debug 常量定义
 */

import type { CompareGroup, PluginColor } from './types';

/** 插件颜色映射 */
export const PLUGIN_COLORS: PluginColor[] = [
  { bg: 'rgba(59, 130, 246, 0.15)', border: '#3b82f6', text: '#3b82f6' },
  { bg: 'rgba(16, 185, 129, 0.15)', border: '#10b981', text: '#10b981' },
  { bg: 'rgba(245, 158, 11, 0.15)', border: '#f59e0b', text: '#f59e0b' },
  { bg: 'rgba(239, 68, 68, 0.15)', border: '#ef4444', text: '#ef4444' },
  { bg: 'rgba(139, 92, 246, 0.15)', border: '#8b5cf6', text: '#8b5cf6' },
  { bg: 'rgba(236, 72, 153, 0.15)', border: '#ec4899', text: '#ec4899' },
  { bg: 'rgba(6, 182, 212, 0.15)', border: '#06b6d4', text: '#06b6d4' },
  { bg: 'rgba(132, 204, 22, 0.15)', border: '#84cc16', text: '#84cc16' },
];

/** 默认颜色（兜底） */
const DEFAULT_PLUGIN_COLOR: PluginColor = PLUGIN_COLORS[0];

/** 获取插件颜色 */
export function getPluginColor(index: number): PluginColor {
  return PLUGIN_COLORS[index % PLUGIN_COLORS.length] ?? DEFAULT_PLUGIN_COLOR;
}

/** 默认对比组 */
export function createDefaultCompareGroup(): CompareGroup {
  return {
    name: '对照组',
    variables: [],
    modelOverride: {
      enabled: false,
      model_code: '',
      temperature: 0.7,
      max_tokens: 2048,
    },
  };
}

/** 历史记录表格列定义 */
export const HISTORY_TABLE_COLUMNS = [
  {
    title: '选择',
    key: 'select',
    width: 60,
  },
  {
    title: '状态',
    dataIndex: 'success',
    key: 'success',
    width: 80,
  },
  {
    title: 'Expert',
    dataIndex: 'expert_config_code',
    key: 'expert_config_code',
    ellipsis: true,
  },
  {
    title: '耗时',
    dataIndex: 'execution_time_ms',
    key: 'execution_time_ms',
    width: 100,
  },
  {
    title: '时间',
    dataIndex: 'create_time',
    key: 'create_time',
    width: 160,
  },
  {
    title: '操作',
    key: 'action',
    width: 180,
  },
];
