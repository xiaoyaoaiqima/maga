<script setup lang="ts">
import { Alert } from 'ant-design-vue';

export interface LabelValue {
  labels: Record<string, string[]>;
}

withDefaults(
  defineProps<{
    modelValue: LabelValue;
    tenantCode?: string;
  }>(),
  {
    modelValue: () => ({ labels: {} }),
    tenantCode: 'default',
  },
);
</script>

<template>
  <Alert
    message="旧标签选择器已下线"
    description="请使用业务规则和系统提示词关键词链路维护生成规则。"
    type="warning"
    show-icon
  />
</template>
