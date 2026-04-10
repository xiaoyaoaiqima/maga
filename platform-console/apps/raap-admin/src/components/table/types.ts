/**
 * 表格操作类型定义
 */

import type { Component } from 'vue';

/**
 * 表格操作配置
 */
export interface TableAction {
  /** 唯一标识 */
  key: string;
  /** 显示文本 */
  label: string;
  /** 图标组件 */
  icon: Component;
  /** 提示文本（默认使用 label） */
  tooltip?: string;
  /** 样式变体 */
  variant?: 'danger' | 'default' | 'info' | 'primary' | 'success' | 'warning';
  /** 是否禁用 */
  disabled?: boolean;
  /** 是否加载中 */
  loading?: boolean;
  /** 是否危险操作 */
  danger?: boolean;
  /** 确认配置 */
  confirm?: {
    cancelText?: string;
    okText?: string;
    title?: string;
  };
  /** 点击事件处理函数 */
  onClick?: () => Promise<void> | void;
  /** 附加数据（如 record） */
  record?: any;
  /** 权限码（可选，用于权限控制） */
  authCode?: string;
  /** 显示条件函数 */
  visible?: (record: any) => boolean;
  /** 禁用条件函数 */
  disableIf?: (record: any) => boolean;
}

/**
 * 表格操作组配置
 */
export interface TableActionGroup {
  /** 分组标题 */
  title?: string;
  /** 操作列表 */
  actions: TableAction[];
}
