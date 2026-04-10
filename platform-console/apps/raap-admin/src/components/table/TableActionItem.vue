<!--
  单个表格操作按钮组件
-->
<script setup lang="ts">
import type { TableAction } from './types';

import { computed } from 'vue';

import { VbenIconButton } from '@vben-core/shadcn-ui';

/**
 * 组件属性
 */
interface Props {
  /** 操作配置 */
  action: TableAction;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  click: [];
}>();

/** 按钮样式类 */
const buttonClass = computed(() => {
  const classes = ['action-btn'];

  if (props.action.variant) {
    classes.push(`action-btn-${props.action.variant}`);
  }

  return classes.join(' ');
});

/** 处理点击 */
const handleClick = () => {
  if (props.action.disabled) return;
  // 只负责转发事件，不执行业务逻辑
  emit('click');
};
</script>

<template>
  <VbenIconButton
    :class="buttonClass"
    :tooltip="action.tooltip || action.label"
    :disabled="action.disabled"
    :loading="action.loading"
    @click="handleClick"
  >
    <component :is="action.icon" />
  </VbenIconButton>
</template>

<style scoped>
/* 基础按钮样式 */
.action-btn {
  font-size: 15px;
  transition: all 0.2s;
}

/* 成功样式 */
.action-btn-success {
  color: #52c41a !important;
}

.action-btn-success:hover {
  background: hsl(142deg 76% 96% / 50%);
}

/* 信息样式 */
.action-btn-info {
  color: #1890ff !important;
}

.action-btn-info:hover {
  background: hsl(210deg 100% 96% / 50%);
}

/* 警告样式 */
.action-btn-warning {
  color: #faad14 !important;
}

.action-btn-warning:hover {
  background: hsl(38deg 92% 96% / 50%);
}

/* 危险样式 */
.action-btn-danger {
  color: hsl(var(--destructive)) !important;
}

.action-btn-danger:hover {
  background: hsl(var(--destructive) / 15%);
}

/* 主色样式 */
.action-btn-primary {
  color: hsl(var(--primary)) !important;
}

.action-btn-primary:hover {
  background: hsl(var(--primary) / 10%);
}
</style>
