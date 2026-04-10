/**
 * 调试历史记录 Composable
 */

import type { DebugResponse } from '../types';

import { ref } from 'vue';

import { message } from 'ant-design-vue';

import {
  deleteDebugHistoryApi,
  getDebugHistoryApi,
  getDebugHistoryDetailApi,
  starDebugHistoryApi,
} from '#/api/core/expert-debug';

export function useDebugHistory() {
  const historyVisible = ref(false);
  const historyLoading = ref(false);
  const historyList = ref<DebugResponse[]>([]);
  const historyPagination = ref({
    current: 1,
    pageSize: 20,
    total: 0,
    showSizeChanger: true,
    showTotal: (t: number) => `共 ${t} 条`,
  });

  // 选中对比的历史记录
  const selectedHistoryIds = ref<number[]>([]);

  async function fetchHistory(expertConfigCode?: string) {
    historyLoading.value = true;
    try {
      const response = await getDebugHistoryApi({
        expert_config_code: expertConfigCode || undefined,
        page: historyPagination.value.current,
        page_size: historyPagination.value.pageSize,
      });
      historyList.value = response.items;
      historyPagination.value.total = response.total;
    } catch {
      message.error('获取历史记录失败');
    } finally {
      historyLoading.value = false;
    }
  }

  function handleHistoryTableChange(pag: any, expertConfigCode?: string) {
    historyPagination.value.current = pag.current || 1;
    historyPagination.value.pageSize =
      pag.pageSize || historyPagination.value.pageSize;
    fetchHistory(expertConfigCode);
  }

  function showHistory(expertConfigCode?: string) {
    historyVisible.value = true;
    fetchHistory(expertConfigCode);
  }

  async function handleStarHistory(
    id: number,
    isStarred: boolean,
    expertConfigCode?: string,
  ) {
    try {
      await starDebugHistoryApi(id, isStarred);
      message.success(isStarred ? '已收藏' : '已取消收藏');
      await fetchHistory(expertConfigCode);
    } catch {
      message.error('操作失败');
    }
  }

  async function handleDeleteHistory(id: number, expertConfigCode?: string) {
    try {
      await deleteDebugHistoryApi(id);
      message.success('已删除');
      await fetchHistory(expertConfigCode);
    } catch {
      message.error('删除失败');
    }
  }

  function toggleHistorySelect(id: number) {
    const index = selectedHistoryIds.value.indexOf(id);
    if (index === -1) {
      if (selectedHistoryIds.value.length >= 2) {
        selectedHistoryIds.value.shift();
      }
      selectedHistoryIds.value.push(id);
    } else {
      selectedHistoryIds.value.splice(index, 1);
    }
  }

  async function loadHistoryDetail(historyId: number): Promise<DebugResponse> {
    return await getDebugHistoryDetailApi(historyId);
  }

  return {
    // 状态
    historyVisible,
    historyLoading,
    historyList,
    historyPagination,
    selectedHistoryIds,

    // 方法
    fetchHistory,
    handleHistoryTableChange,
    showHistory,
    handleStarHistory,
    handleDeleteHistory,
    toggleHistorySelect,
    loadHistoryDetail,
  };
}
