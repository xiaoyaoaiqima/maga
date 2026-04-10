import type { MetricDefinitionApi } from '#/api/core/metric-definition';

import { ref } from 'vue';

import { defineStore } from 'pinia';

import { getMetricDefinitionsApi } from '#/api/core/metric-definition';

export const useMetricDefinitionStore = defineStore('metric-definition', () => {
  const definitions = ref<Record<string, MetricDefinitionApi.MetricDefinition>>(
    {},
  );
  const isLoaded = ref(false);

  /**
   * 初始化/加载指标定义
   * 如果已经加载过，默认不刷新，除非 force=true
   */
  async function loadDefinitions(force = false) {
    if (isLoaded.value && !force) {
      return;
    }

    try {
      const list = await getMetricDefinitionsApi();
      const map: Record<string, MetricDefinitionApi.MetricDefinition> = {};
      list.forEach((item) => {
        map[item.metric_key] = item;
      });
      definitions.value = map;
      isLoaded.value = true;
    } catch (error) {
      console.error('加载指标定义失败:', error);
    }
  }

  /**
   * 获取单个指标定义
   */
  function getDefinition(key: string) {
    return definitions.value[key];
  }

  /**
   * 重置 store 状态（setup 语法必须手动实现）
   */
  function $reset() {
    definitions.value = {};
    isLoaded.value = false;
  }

  return {
    definitions,
    isLoaded,
    loadDefinitions,
    getDefinition,
    $reset,
  };
});
