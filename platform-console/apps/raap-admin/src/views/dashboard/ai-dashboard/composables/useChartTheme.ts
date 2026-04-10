/**
 * AI Dashboard 图表主题切换
 *
 * 监听主题变化并触发图表重新渲染
 */

import { nextTick, watch } from 'vue';

import { usePreferences } from '@vben/preferences';

// ==================== 类型定义 ====================

/** 图表更新函数类型 */
export type ChartUpdateFunction = () => Promise<void> | void;

// ==================== Composable ====================

export function useChartTheme(updateCharts: ChartUpdateFunction[]) {
  const { isDark } = usePreferences();

  // 监听主题变化，重新渲染所有 ECharts 图表
  watch(isDark, async () => {
    // 等待 CSS 变量更新完成
    await nextTick();
    setTimeout(() => {
      // 重新渲染所有图表以应用新的主题颜色
      updateCharts.forEach((fn) => {
        try {
          fn();
        } catch (error) {
          console.error('图表更新失败:', error);
        }
      });
    }, 100);
  });

  return {
    isDark,
  };
}
