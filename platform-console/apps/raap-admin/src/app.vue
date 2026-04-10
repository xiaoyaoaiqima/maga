<script lang="ts" setup>
import { computed } from 'vue';

import { useAntdDesignTokens } from '@vben/hooks';
import { preferences, usePreferences } from '@vben/preferences';

import { App, ConfigProvider, theme } from 'ant-design-vue';

import { antdLocale } from '#/locales';

defineOptions({ name: 'App' });

const { isDark } = usePreferences();
const { tokens } = useAntdDesignTokens();

const tokenTheme = computed(() => {
  const algorithm = isDark.value
    ? [theme.darkAlgorithm]
    : [theme.defaultAlgorithm];

  // antd 紧凑模式算法
  if (preferences.app.compact) {
    algorithm.push(theme.compactAlgorithm);
  }

  return {
    algorithm,
    token: tokens,
  };
});

// 全局配置下拉框挂载容器：挂载到最近的滚动容器
// 这样下拉框会跟随页面滚动，被 header 遮挡
const getPopupContainer = (triggerNode?: HTMLElement): HTMLElement => {
  if (!triggerNode) return document.body;

  // 优先挂载到 form 元素
  const form = triggerNode.closest('form');
  if (form) return form as HTMLElement;

  // 其次挂载到父元素
  if (triggerNode.parentElement) {
    return triggerNode.parentElement;
  }

  return document.body;
};
</script>

<template>
  <ConfigProvider
    :locale="antdLocale"
    :theme="tokenTheme"
    :get-popup-container="getPopupContainer"
  >
    <App>
      <RouterView />
    </App>
  </ConfigProvider>
</template>

<style>
/* 
 * 全局下拉框 z-index 层级管理
 * 
 * 层级设计（从高到低）：
 * - Header + Tabs: 200+ (最高层，固定定位)
 * - Sidebar: 199-201 (根据布局模式)
 * - Dropdown: 180 (比侧边栏高，但比 Header 低)
 * - Modal/Drawer: 1000+ (弹窗层)
 * - Modal/Drawer 内的 Dropdown: 1050+ (弹窗内的下拉框)
 * 
 * 效果：
 * 1. 页面滚动时，下拉框跟随触发元素一起被 Header 遮挡
 * 2. 下拉框显示在侧边栏上层
 * 3. Modal/Drawer 内的下拉框不会被 Header 遮挡
 */

/* ========== 页面内下拉框 ========== */

/* 所有页面内的下拉框统一 z-index，确保在侧边栏上层但在 Header 下层 */
.ant-select-dropdown,
.ant-tree-select-dropdown,
.ant-cascader-dropdown,
.ant-picker-dropdown,
.ant-dropdown {
  z-index: 180 !important;
}

/* ========== Modal/Drawer 内的下拉框 ========== */

/* 在 Modal/Drawer 容器内的下拉框需要更高的 z-index */
.ant-modal .ant-select-dropdown,
.ant-modal .ant-tree-select-dropdown,
.ant-modal .ant-cascader-dropdown,
.ant-modal .ant-picker-dropdown,
.ant-modal .ant-dropdown,
.ant-drawer .ant-select-dropdown,
.ant-drawer .ant-tree-select-dropdown,
.ant-drawer .ant-cascader-dropdown,
.ant-drawer .ant-picker-dropdown,
.ant-drawer .ant-dropdown {
  z-index: 1050 !important;
}

/* Modal/Drawer Header 使用更高的 z-index 和 sticky 定位 */
.ant-modal-header,
.ant-drawer-header {
  position: sticky;
  top: 0;
  z-index: 1060 !important;
  background: inherit;
}

/* Modal/Drawer Content 需要创建层叠上下文 */
.ant-modal-content,
.ant-drawer-content {
  position: relative;
  z-index: 0;
}

/* Modal/Drawer Body 设置为滚动容器 */
.ant-modal-body,
.ant-drawer-body {
  position: relative;
  z-index: 1;
}

/* ========== Tooltip 和 Popover ========== */

/* Tooltip 和 Popover 也需要适配 z-index */
.ant-tooltip {
  z-index: 180 !important;
}

.ant-popover {
  z-index: 180 !important;
}

/* Modal/Drawer 内的 Tooltip 和 Popover */
.ant-modal .ant-tooltip,
.ant-drawer .ant-tooltip,
.ant-modal .ant-popover,
.ant-drawer .ant-popover {
  z-index: 1060 !important;
}
</style>
