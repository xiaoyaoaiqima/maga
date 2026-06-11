<script setup lang="ts">
import { Empty, Modal } from 'ant-design-vue';

defineProps<{
  label?: string;
  selectedIds?: string[];
  tenantCode?: string;
  visible: boolean;
}>();

const emit = defineEmits<{
  confirm: [
    data: {
      label: string;
      selectedIds: string[];
      selectedNodes: Array<{ id: string; name: string }>;
    },
  ];
  'update:visible': [visible: boolean];
}>();

function close() {
  emit('update:visible', false);
}
</script>

<template>
  <Modal
    :open="visible"
    title="关键词树已下线"
    :footer="null"
    width="520px"
    @cancel="close"
  >
    <Empty description="旧关键词树系统已下线，请使用业务规则和系统提示词关键词链路。" />
  </Modal>
</template>
