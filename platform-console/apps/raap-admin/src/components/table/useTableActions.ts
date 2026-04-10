/**
 * 表格操作 Composable
 * 提供常用的操作配置和工具函数
 */

import type { TableAction } from './types';

import {
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  FolderOpenOutlined,
  FolderOutlined,
  RocketOutlined,
} from '@ant-design/icons-vue';

/**
 * 创建基础操作
 */
export function createBaseAction(config: Partial<TableAction>): TableAction {
  return {
    key: '',
    label: '',
    icon: EditOutlined,
    ...config,
  };
}

/**
 * 常用操作工厂函数
 */
export const actionFactories = {
  /** 查看操作 */
  view: (config?: Partial<TableAction>): TableAction => ({
    key: 'view',
    label: '查看',
    icon: EyeOutlined,
    tooltip: '查看详情',
    variant: 'info',
    ...config,
  }),

  /** 编辑操作 */
  edit: (config?: Partial<TableAction>): TableAction => ({
    key: 'edit',
    label: '编辑',
    icon: EditOutlined,
    tooltip: '编辑',
    variant: 'default',
    ...config,
  }),

  /** 删除操作 */
  delete: (config?: Partial<TableAction>): TableAction => ({
    key: 'delete',
    label: '删除',
    icon: DeleteOutlined,
    tooltip: '删除',
    variant: 'danger',
    danger: true,
    confirm: {
      title: '确定要删除吗？',
      okText: '确定',
      cancelText: '取消',
    },
    ...config,
  }),

  /** 复制操作 */
  copy: (config?: Partial<TableAction>): TableAction => ({
    key: 'copy',
    label: '复制',
    icon: CopyOutlined,
    tooltip: '复制',
    variant: 'info',
    ...config,
  }),

  /** 部署操作 */
  deploy: (config?: Partial<TableAction>): TableAction => ({
    key: 'deploy',
    label: '部署',
    icon: RocketOutlined,
    tooltip: '部署',
    variant: 'success',
    ...config,
  }),

  /** 归档操作 */
  archive: (config?: Partial<TableAction>): TableAction => ({
    key: 'archive',
    label: '归档',
    icon: FolderOutlined,
    tooltip: '归档',
    variant: 'default',
    ...config,
  }),

  /** 取消归档操作 */
  unarchive: (config?: Partial<TableAction>): TableAction => ({
    key: 'unarchive',
    label: '取消归档',
    icon: FolderOpenOutlined,
    tooltip: '取消归档',
    variant: 'success',
    ...config,
  }),
};

/**
 * 根据权限过滤操作
 */
export function filterActionsByAuth(
  actions: TableAction[],
  hasPermission: (code: string) => boolean,
): TableAction[] {
  return actions.filter((action) => {
    if (!action.authCode) return true;
    return hasPermission(action.authCode);
  });
}

/**
 * 根据条件过滤可见性
 */
export function filterActionsByVisible(
  actions: TableAction[],
  record: any,
): TableAction[] {
  return actions.filter((action) => {
    if (!action.visible) return true;
    return action.visible(record);
  });
}

/**
 * 应用禁用条件
 */
export function applyDisableConditions(
  actions: TableAction[],
  record: any,
): TableAction[] {
  return actions.map((action) => {
    if (!action.disableIf) return action;
    return {
      ...action,
      disabled: action.disableIf(record),
    };
  });
}
