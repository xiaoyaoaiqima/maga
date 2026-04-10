/**
 * 对比组管理 Composable
 */

import type { CompareGroup, DebugResponse } from '../types';

import { computed, ref } from 'vue';

import { cloneReactive } from '#/utils/clone';

import { createDefaultCompareGroup } from '../constants';

export function useCompareGroups() {
  const isCompareMode = ref(false);
  const compareGroups = ref<CompareGroup[]>([createDefaultCompareGroup()]);
  const activeGroupIndex = ref(0);
  const comparisonResults = ref<Array<DebugResponse | null>>([]);

  // 当前选中的变量（快捷引用当前组）
  const selectedVariables = computed({
    get: () => compareGroups.value[activeGroupIndex.value]?.variables || [],
    set: (val) => {
      const group = compareGroups.value[activeGroupIndex.value];
      if (group) {
        group.variables = val;
      }
    },
  });

  // 参数覆盖（快捷引用当前组）
  const enableModelOverride = computed({
    get: () =>
      compareGroups.value[activeGroupIndex.value]?.modelOverride.enabled ||
      false,
    set: (val) => {
      const group = compareGroups.value[activeGroupIndex.value];
      if (group) {
        group.modelOverride.enabled = val;
      }
    },
  });

  const overrideModelCode = computed({
    get: () =>
      compareGroups.value[activeGroupIndex.value]?.modelOverride.model_code ||
      '',
    set: (val) => {
      const group = compareGroups.value[activeGroupIndex.value];
      if (group) {
        group.modelOverride.model_code = val;
      }
    },
  });

  const overrideTemperature = computed({
    get: () =>
      compareGroups.value[activeGroupIndex.value]?.modelOverride.temperature ??
      0.7,
    set: (val) => {
      const group = compareGroups.value[activeGroupIndex.value];
      if (group) {
        group.modelOverride.temperature = val;
      }
    },
  });

  const overrideMaxTokens = computed({
    get: () =>
      compareGroups.value[activeGroupIndex.value]?.modelOverride.max_tokens ??
      2048,
    set: (val) => {
      const group = compareGroups.value[activeGroupIndex.value];
      if (group) {
        group.modelOverride.max_tokens = val;
      }
    },
  });

  function addCompareGroup() {
    const currentGroup = compareGroups.value[activeGroupIndex.value];
    if (!currentGroup) return;

    const newGroup: CompareGroup = {
      name: `实验组 ${compareGroups.value.length}`,
      variables: cloneReactive(currentGroup.variables),
      modelOverride: cloneReactive(currentGroup.modelOverride),
    };

    compareGroups.value.push(newGroup);
    activeGroupIndex.value = compareGroups.value.length - 1;
  }

  function removeCompareGroup(index: number) {
    if (compareGroups.value.length <= 1) return;
    compareGroups.value.splice(index, 1);
    if (activeGroupIndex.value >= compareGroups.value.length) {
      activeGroupIndex.value = compareGroups.value.length - 1;
    }
  }

  function resetCompareGroups() {
    compareGroups.value = [createDefaultCompareGroup()];
    activeGroupIndex.value = 0;
    comparisonResults.value = [];
  }

  /**
   * 安全获取变量值
   */
  function getVariableValue(pluginCode: string, variableName: string): string {
    const plugin = selectedVariables.value.find(
      (p) => p.plugin_code === pluginCode,
    );
    if (!plugin) {
      selectedVariables.value.push({
        plugin_code: pluginCode,
        variable_mapping: {},
      });
      return '';
    }
    return plugin.variable_mapping[variableName] || '';
  }

  /**
   * 设置变量值
   */
  function setVariableValue(
    pluginCode: string,
    variableName: string,
    value: string,
  ) {
    let plugin = selectedVariables.value.find(
      (p) => p.plugin_code === pluginCode,
    );
    if (!plugin) {
      plugin = { plugin_code: pluginCode, variable_mapping: {} };
      selectedVariables.value.push(plugin);
    }
    plugin.variable_mapping[variableName] = value;
  }

  return {
    // 状态
    isCompareMode,
    compareGroups,
    activeGroupIndex,
    comparisonResults,

    // 计算属性
    selectedVariables,
    enableModelOverride,
    overrideModelCode,
    overrideTemperature,
    overrideMaxTokens,

    // 方法
    addCompareGroup,
    removeCompareGroup,
    resetCompareGroups,
    getVariableValue,
    setVariableValue,
  };
}
