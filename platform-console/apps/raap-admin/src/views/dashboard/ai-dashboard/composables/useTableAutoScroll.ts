/**
 * AI Dashboard 表格自动滚动
 *
 * 管理表格自动滚动功能，支持鼠标悬停暂停
 */

import type { Table } from 'ant-design-vue';

import { nextTick, onUnmounted, ref } from 'vue';

import { SCROLL_INTERVAL, SCROLL_SPEED } from '../constants';

// ==================== 类型定义 ====================

/** 表格引用类型 */
export type TableRef = InstanceType<typeof Table> | null;

/** 鼠标悬停状态 */
export type HoverState = { value: boolean };

/** 定时器设置回调 */
type TimerSetter = (timer: null | ReturnType<typeof setInterval>) => void;

// ==================== 内部函数 ====================

/**
 * 获取 Ant Design Table 的滚动容器
 */
function getTableScrollContainer(tableRef: TableRef): HTMLElement | null {
  if (!tableRef) return null;
  const tableEl = (tableRef as any)?.$el as HTMLElement | undefined;
  if (!tableEl) return null;
  return tableEl.querySelector('.ant-table-body') as HTMLElement | null;
}

/**
 * 启动单个表格的自动滚动
 */
function startTableAutoScroll(
  tableRef: TableRef,
  isHovered: HoverState,
  setTimer: TimerSetter,
): void {
  const container = getTableScrollContainer(tableRef);
  if (!container) return;

  const timer = setInterval(() => {
    // 鼠标悬停时暂停滚动
    if (isHovered.value) return;

    const { scrollTop, scrollHeight, clientHeight } = container;
    const maxScroll = scrollHeight - clientHeight;

    if (maxScroll <= 0) return; // 内容不足，无需滚动

    // 滚动到底部后回到顶部
    if (scrollTop >= maxScroll - 1) {
      container.scrollTop = 0;
    } else {
      container.scrollTop += SCROLL_SPEED;
    }
  }, SCROLL_INTERVAL);

  setTimer(timer);
}

// ==================== Composable ====================

/**
 * 表格自动滚动管理
 * @returns 滚动控制方法和状态
 */
export function useTableAutoScroll() {
  // 表格引用
  const tableRef = ref<TableRef>(null);
  // 鼠标悬停状态
  const isHovered = ref(false);
  // 定时器
  let scrollTimer: null | ReturnType<typeof setInterval> = null;

  /** 启动自动滚动 */
  function start(): void {
    stop(); // 先停止之前的
    startTableAutoScroll(tableRef.value, isHovered, (timer) => {
      scrollTimer = timer;
    });
  }

  /** 停止自动滚动 */
  function stop(): void {
    if (scrollTimer) {
      clearInterval(scrollTimer);
      scrollTimer = null;
    }
  }

  /** 处理鼠标进入 */
  function handleMouseEnter(): void {
    isHovered.value = true;
  }

  /** 处理鼠标离开 */
  function handleMouseLeave(): void {
    isHovered.value = false;
  }

  // 组件卸载时清理
  onUnmounted(() => {
    stop();
  });

  return {
    tableRef,
    isHovered,
    start,
    stop,
    handleMouseEnter,
    handleMouseLeave,
  };
}

/**
 * 多表格自动滚动管理
 * @param count 表格数量
 * @returns 滚动控制方法
 */
export function useMultiTableAutoScroll(count: number) {
  const tables = Array.from({ length: count }, () => useTableAutoScroll());

  /** 启动所有表格自动滚动 */
  function startAll(): void {
    nextTick(() => {
      tables.forEach((table) => table.start());
    });
  }

  /** 停止所有表格自动滚动 */
  function stopAll(): void {
    tables.forEach((table) => table.stop());
  }

  return {
    tables,
    startAll,
    stopAll,
  };
}
