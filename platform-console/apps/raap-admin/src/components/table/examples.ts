/**
 * 表格操作按钮使用示例
 *
 * 展示如何在不同场景下使用 TableActions 组件
 */

import type { TableAction } from './types';

import { computed, ref } from 'vue';

import {
  ExperimentOutlined,
  FolderOpenOutlined,
  FolderOutlined,
  MoreOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  RocketOutlined,
  StopOutlined,
} from '@ant-design/icons-vue';

import { actionFactories } from './useTableActions';

// ============== 示例 1: 基础 CRUD 操作 ==============

export function useBasicCrudExample() {
  const handleEdit = (record: any) => {
    console.error('编辑:', record);
  };

  const handleDelete = (id: number) => {
    console.error('删除:', id);
  };

  const getActions = (record: any): TableAction[] => [
    actionFactories.edit({
      onClick: () => handleEdit(record),
    }),
    actionFactories.delete({
      confirm: {
        title: `确定要删除 "${record.name}" 吗？`,
      },
      onClick: () => handleDelete(record.id),
    }),
  ];

  return { getActions };
}

// ============== 示例 2: 带状态的操作（Job 列表） ==============

export function useJobListExample() {
  const deployingId = ref<null | number>(null);
  const testingId = ref<null | number>(null);

  const handleViewExecution = (record: any) => {
    console.error('查看执行详情:', record);
  };

  const handleEdit = (record: any) => {
    console.error('编辑 Job:', record);
  };

  const handleTest = async (record: any) => {
    testingId.value = record.id;
    // 模拟异步操作
    await new Promise((resolve) => setTimeout(resolve, 2000));
    testingId.value = null;
    console.error('测试完成:', record);
  };

  const handleDeploy = async (record: any) => {
    deployingId.value = record.id;
    await new Promise((resolve) => setTimeout(resolve, 2000));
    deployingId.value = null;
    console.error('部署完成:', record);
  };

  const handleManageStatus = (record: any) => {
    console.error('管理状态:', record);
  };

  const handleCopy = (record: any) => {
    console.error('复制 Job:', record);
  };

  const handleDelete = (id: number) => {
    console.error('删除 Job:', id);
  };

  const getActions = (record: any): TableAction[] => {
    const actions: TableAction[] = [
      // 始终显示的操作
      actionFactories.view({
        onClick: () => handleViewExecution(record),
      }),
      actionFactories.edit({
        onClick: () => handleEdit(record),
      }),
      {
        key: 'test',
        label: '快速测试',
        icon: ExperimentOutlined,
        variant: 'info',
        loading: testingId.value === record.id,
        onClick: () => handleTest(record),
      },
    ];

    // 根据状态显示不同操作
    if (record.status === 'NOT_DEPLOYED') {
      actions.push({
        key: 'deploy',
        label: '部署',
        icon: RocketOutlined,
        variant: 'success',
        loading: deployingId.value === record.id,
        onClick: () => handleDeploy(record),
      });
    } else if (['DEPLOYED', 'PAUSED', 'RUNNING'].includes(record.status)) {
      // 这里可以用下拉菜单展开更多操作
      actions.push({
        key: 'manage-status',
        label: '管理状态',
        icon: MoreOutlined,
        tooltip: '已部署 (点击管理状态)',
        variant: 'success',
        onClick: () => handleManageStatus(record),
      });
    }

    // 更多操作（会自动放入下拉菜单）
    actions.push(
      actionFactories.copy({
        onClick: () => handleCopy(record),
      }),
      actionFactories.delete({
        confirm: {
          title: `确定要删除 Job "${record.job_name}" 吗？`,
        },
        onClick: () => handleDelete(record.id),
      }),
    );

    return actions;
  };

  return { getActions };
}

// ============== 示例 3: 带条件显示/禁用的操作 ==============

export function useConditionalActionsExample() {
  const hasEditPermission = computed(() => true);
  const hasDeletePermission = computed(() => false);

  const getActions = (record: any): TableAction[] => [
    actionFactories.edit({
      // 根据权限禁用
      disableIf: () => !hasEditPermission.value,
      // 根据状态隐藏
      visible: (record) => record.status !== 'LOCKED',
      onClick: () => console.error('编辑:', record),
    }),
    {
      key: 'archive',
      label: '归档',
      icon: FolderOutlined,
      // 动态显示
      visible: (record) => record.is_active === 1,
      onClick: () => console.error('归档:', record),
    },
    {
      key: 'unarchive',
      label: '取消归档',
      icon: FolderOpenOutlined,
      variant: 'success',
      // 动态显示
      visible: (record) => record.is_active === 0,
      onClick: () => console.error('取消归档:', record),
    },
    actionFactories.delete({
      // 根据权限禁用
      disableIf: () => !hasDeletePermission.value,
      confirm: {
        title: `确定要删除 "${record.name}" 吗？`,
      },
      onClick: () => console.error('删除:', record),
    }),
  ];

  return { getActions };
}

// ============== 示例 4: 带权限控制的操作 ==============

export function usePermissionBasedActionsExample() {
  // 模拟权限检查函数
  const hasPermission = (code: string): boolean => {
    const permissions = ['user:edit', 'user:delete'];
    return permissions.includes(code);
  };

  const getActions = (record: any): TableAction[] => [
    actionFactories.edit({
      authCode: 'user:edit',
      onClick: () => console.error('编辑用户:', record),
    }),
    {
      key: 'reset-password',
      label: '重置密码',
      icon: ExperimentOutlined, // 或者用 KeyOutlined
      variant: 'warning',
      authCode: 'user:reset-password',
      onClick: () => console.error('重置密码:', record),
    },
    actionFactories.delete({
      authCode: 'user:delete',
      confirm: {
        title: `确定要删除用户 "${record.username}" 吗？`,
      },
      onClick: () => console.error('删除用户:', record),
    }),
  ];

  // 在组件中使用时，需要过滤权限
  const getFilteredActions = (record: any) => {
    import('./useTableActions').then(({ filterActionsByAuth }) => {
      return filterActionsByAuth(getActions(record), hasPermission);
    });
    return getActions(record);
  };

  return { getActions, getFilteredActions };
}

// ============== 示例 5: 完整的 Strategy（策略）操作 ==============

export function useStrategyActionsExample() {
  const copyLoading = ref(false);
  const archiveLoading = ref(false);

  const handleTest = (record: any) => {
    console.error('测试策略:', record);
  };

  const handleEdit = (record: any) => {
    console.error('编辑策略:', record);
  };

  const handleCopy = async (record: any) => {
    copyLoading.value = true;
    await new Promise((resolve) => setTimeout(resolve, 1500));
    copyLoading.value = false;
    console.error('复制策略:', record);
  };

  const handleArchive = async (record: any) => {
    archiveLoading.value = true;
    await new Promise((resolve) => setTimeout(resolve, 1500));
    archiveLoading.value = false;
    console.error('归档策略:', record);
  };

  const handleDelete = (id: number) => {
    console.error('删除策略:', id);
  };

  const getActions = (record: any): TableAction[] => [
    {
      key: 'test',
      label: '测试',
      icon: ExperimentOutlined,
      variant: 'info',
      onClick: () => handleTest(record),
    },
    actionFactories.edit({
      onClick: () => handleEdit(record),
    }),
    actionFactories.copy({
      loading: copyLoading.value,
      onClick: () => handleCopy(record),
    }),
    {
      key: 'archive',
      label: record.is_active === 1 ? '归档' : '取消归档',
      icon: record.is_active === 1 ? FolderOutlined : FolderOpenOutlined,
      variant: record.is_active === 1 ? 'default' : 'success',
      loading: archiveLoading.value,
      onClick: () => handleArchive(record),
    },
    actionFactories.delete({
      confirm: {
        title: '确定要删除这个策略吗？',
      },
      onClick: () => handleDelete(record.id),
    }),
  ];

  return { getActions };
}

// ============== 示例 6: 带启动/暂停/停止的操作 ==============

export function useProcessControlExample() {
  const processingId = ref<null | number>(null);

  const getActions = (record: any): TableAction[] => [
    {
      key: 'start',
      label: '启动',
      icon: PlayCircleOutlined,
      variant: 'success',
      visible: (record) => record.status === 'STOPPED',
      disableIf: (record) => !record.canStart,
      loading: processingId.value === record.id,
      onClick: () => console.error('启动:', record),
    },
    {
      key: 'pause',
      label: '暂停',
      icon: PauseCircleOutlined,
      variant: 'warning',
      visible: (record) => record.status === 'RUNNING',
      onClick: () => console.error('暂停:', record),
    },
    {
      key: 'stop',
      label: '停止',
      icon: StopOutlined,
      variant: 'danger',
      visible: (record) => ['PAUSED', 'RUNNING'].includes(record.status),
      confirm: {
        title: '确定要停止吗？',
      },
      onClick: () => console.error('停止:', record),
    },
    actionFactories.edit({
      visible: (record) => record.status !== 'RUNNING',
      onClick: () => console.error('编辑:', record),
    }),
  ];

  return { getActions };
}
