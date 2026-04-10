<script setup lang="ts">
import { computed, onMounted } from 'vue';

import { QuestionCircleOutlined } from '@ant-design/icons-vue';
import { Tooltip } from 'ant-design-vue';

import { useMetricDefinitionStore } from '#/store/modules/metric-definition';

const props = defineProps<{
  /** 指标 Key */
  metricKey: string;
  /** 覆盖显示的 Title (可选) */
  title?: string;
}>();

const store = useMetricDefinitionStore();

// 自动加载（如果还没加载）
onMounted(() => {
  if (!store.isLoaded) {
    store.loadDefinitions();
  }
});

const definition = computed(() => store.getDefinition(props.metricKey));

// Tooltip 内容
const tooltipContent = computed(() => {
  const def = definition.value;
  if (!def) return props.title || props.metricKey;

  // 如果有 description，优先显示
  if (def.description) {
    return def.description;
  }
  return def.metric_name;
});

// 指标名称（用于显示在问号旁边，如果需要的话，或者仅作为 Tooltip 的标题）
// 这里我们假设组件只渲染一个小问号，或者包裹在 slot 里
// 根据需求："数据右上角都要支持展示小问号"，通常是 Label + <MetricHelp />
</script>

<template>
  <Tooltip :title="tooltipContent">
    <span
      class="metric-help-icon cursor-help text-gray-400 hover:text-gray-600"
    >
      <QuestionCircleOutlined />
    </span>
  </Tooltip>
</template>

<style scoped>
.metric-help-icon {
  display: inline-flex;
  align-items: center;
  margin-left: 4px;
  vertical-align: middle;
}
</style>
