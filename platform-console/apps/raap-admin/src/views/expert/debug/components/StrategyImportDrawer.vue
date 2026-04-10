<script setup lang="ts">
import type { ContentStrategyApi } from '#/api/core/content-strategy';

/**
 * 策略导入抽屉 - 从关键词策略导入变量组合
 */
import { computed, ref, watch } from 'vue';

import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Drawer,
  message,
  Row,
  Select,
  SelectOption,
  Spin,
  Tag,
} from 'ant-design-vue';

import {
  getCombinationsApi,
  getContentStrategiesApi,
} from '#/api/core/content-strategy';

import {
  clearStrategyCache,
  getCachedCombinations,
  getCachedStrategies,
  getCacheInfo,
  setCachedCombinations,
  setCachedStrategies,
} from '../utils/strategyCache';

// Props
interface ExpertVariable {
  plugin_code: string;
  plugin_name?: string;
  variable_name: string;
  options: Array<{ context_name: string; node_id?: string }>;
}

interface Props {
  open: boolean;
  expertVariables: ExpertVariable[];
  /** 目标插件 code，如果指定则只显示该插件的变量 */
  targetPluginCode?: string;
  /** 目标插件名称，用于显示 */
  targetPluginName?: string;
}

const props = defineProps<Props>();

// Emits
const emit = defineEmits<{
  apply: [
    snapshot: Array<{
      plugin_code: string;
      variable_mapping: Record<string, string>;
    }>,
    importedNodes?: ImportedNodeInfo[],
    strategyInfo?: { strategy_id: string; strategy_name: string },
  ];
  'update:open': [value: boolean];
}>();

// 过滤后的变量列表（如果指定了 targetPluginCode，只显示该插件的变量）
const filteredExpertVariables = computed(() => {
  if (!props.targetPluginCode) {
    return props.expertVariables;
  }
  return props.expertVariables.filter(
    (v) => v.plugin_code === props.targetPluginCode,
  );
});

// 导入的节点信息（用于显示节点名称）
interface ImportedNodeInfo {
  node_id: string;
  node_name: string;
}

// 状态
const loading = ref(false);
const strategyList = ref<ContentStrategyApi.ContentStrategy[]>([]);
const selectedStrategyId = ref<null | string>(null);
const variableMapping = ref<Record<string, string>>({});
const combinations = ref<ContentStrategyApi.CombinationItem[]>([]);
const generatingCombos = ref(false);
const selectedComboIndex = ref<null | number>(null);

// 计算属性
const selectedStrategy = computed(() => {
  if (!selectedStrategyId.value) return null;
  return strategyList.value.find((s) => s.id === selectedStrategyId.value);
});

// 从 node_pools 获取分类类型列表
const categoryTypes = computed(() => {
  const pools = selectedStrategy.value?.node_pools;
  if (!pools) return [];
  return Object.keys(pools);
});

// 策略选项列表（用于 Select 的 options prop）
const strategyOptions = computed(() => {
  return strategyList.value.map((s) => ({
    value: s.id,
    label: `${s.name} (${s.combinations_count || 0}个组合)`,
  }));
});

// 获取所有可用的变量列表（去重，基于过滤后的变量）
const availableVariables = computed(() => {
  const vars: Array<{ plugin_code: string; variable_name: string }> = [];
  const seen = new Set<string>();

  for (const plugin of filteredExpertVariables.value) {
    const key = `${plugin.plugin_code}:${plugin.variable_name}`;
    if (!seen.has(key)) {
      seen.add(key);
      vars.push({
        plugin_code: plugin.plugin_code,
        variable_name: plugin.variable_name,
      });
    }
  }

  return vars;
});

// 缓存状态
const cacheInfo = ref(getCacheInfo());
const usedCache = ref(false);

// 是否有匹配的策略
const hasMatchingStrategies = computed(() => strategyList.value.length > 0);

// 获取插件所需的变量名列表(用于提示)
const requiredVariableNames = computed(() => {
  return [...new Set(availableVariables.value.map((v) => v.variable_name))];
});

// 方法
/**
 * 过滤策略列表,优先显示包含插件所需变量的策略
 * 如果没有匹配的策略,显示所有策略
 */
function filterStrategiesByVariables(
  strategies: ContentStrategyApi.ContentStrategy[],
): ContentStrategyApi.ContentStrategy[] {
  // 获取插件需要的所有变量名
  const requiredVariableNames = new Set(
    availableVariables.value.map((v) => v.variable_name),
  );

  // 如果没有变量需求,返回所有策略
  if (requiredVariableNames.size === 0) {
    return strategies;
  }

  // 先尝试找出匹配的策略
  const matchedStrategies = strategies.filter((strategy) => {
    if (!strategy.node_pools) return false;

    const strategyCategories = Object.keys(strategy.node_pools);

    // 检查策略的分类中是否包含插件需要的变量
    const hasMatch = strategyCategories.some((category) =>
      requiredVariableNames.has(category),
    );

    return hasMatch;
  });

  // 如果有匹配的策略,只返回匹配的
  if (matchedStrategies.length > 0) {
    return matchedStrategies;
  }

  // 如果没有匹配的策略,返回所有策略(可能需要用户手动创建)
  return strategies;
}

async function loadStrategies(forceRefresh = false) {
  // 生成缓存 key（基于插件 code 和变量名）
  const pluginCode = props.targetPluginCode;
  const variableNames = requiredVariableNames.value;

  // 优先使用缓存（缓存的是过滤后的策略列表）
  if (!forceRefresh) {
    const cached = getCachedStrategies(pluginCode, variableNames);
    if (cached && cached.length > 0) {
      // 缓存中已经是过滤后的策略，直接使用
      strategyList.value = cached;
      usedCache.value = true;
      cacheInfo.value = getCacheInfo();
      // console.error('[StrategyCache] 使用缓存的策略列表:', cached.length, '条');
      return;
    }
  }

  loading.value = true;
  usedCache.value = false;
  try {
    const res = await getContentStrategiesApi({
      is_active: 1,
      page_size: 100,
    });
    const allStrategies = res.items || [];

    // 过滤出包含插件变量的策略
    const filteredStrategies = filterStrategiesByVariables(allStrategies);
    strategyList.value = filteredStrategies;

    // 写入缓存（缓存过滤后的策略列表，按插件和变量分别缓存）
    setCachedStrategies(filteredStrategies, pluginCode, variableNames);
    cacheInfo.value = getCacheInfo();
    // console.error(
    //   '[StrategyCache] 已缓存策略列表:',
    //   strategyList.value.length,
    //   '条',
    // );
  } catch (error) {
    console.error('获取策略列表失败:', error);
    message.error('获取策略列表失败');
  } finally {
    loading.value = false;
  }
}

// 强制刷新缓存
async function refreshCache() {
  clearStrategyCache();
  combinations.value = [];
  selectedStrategyId.value = null;
  variableMapping.value = {};
  selectedComboIndex.value = null;
  await loadStrategies(true);
  message.success('缓存已刷新');
}

function onStrategyChange(strategyId: string) {
  selectedStrategyId.value = strategyId;
  // 重置映射和组合
  variableMapping.value = {};
  combinations.value = [];
  selectedComboIndex.value = null;

  // 自动初始化映射（尝试匹配同名变量）
  // 注意：只匹配当前插件的变量（如果指定了 targetPluginCode）
  const strategy = strategyList.value.find((s) => s.id === strategyId);
  if (strategy?.node_pools) {
    for (const categoryType of Object.keys(strategy.node_pools)) {
      // 尝试找到同名变量（优先匹配当前插件的变量）
      const matchingVar = filteredExpertVariables.value.find(
        (v) => v.variable_name === categoryType,
      );
      if (matchingVar) {
        variableMapping.value[categoryType] = matchingVar.variable_name;
      }
    }
  }
}

function setVariableMapping(dimensionType: string, variableName: string) {
  variableMapping.value[dimensionType] = variableName;
}

async function loadCombinations(forceRefresh = false) {
  if (!selectedStrategyId.value) {
    message.warning('请先选择策略');
    return;
  }

  const strategyId = selectedStrategyId.value;

  // 优先使用缓存
  if (!forceRefresh) {
    const cached = getCachedCombinations(strategyId);
    if (cached && cached.length > 0) {
      combinations.value = cached;
      if (combinations.value.length > 0) {
        selectedComboIndex.value = 0;
      }
      cacheInfo.value = getCacheInfo();
      // console.error('[StrategyCache] 使用缓存的组合:', cached.length, '条');
      message.success(`从缓存加载了 ${combinations.value.length} 个组合`);
      return;
    }
  }

  generatingCombos.value = true;
  try {
    // 使用 getCombinationsApi 获取策略的精确组合
    const res = await getCombinationsApi(strategyId, false);
    combinations.value = res.combinations || [];
    if (combinations.value.length > 0) {
      selectedComboIndex.value = 0;
    }

    // 写入缓存
    setCachedCombinations(strategyId, combinations.value);
    cacheInfo.value = getCacheInfo();

    message.success(`加载了 ${combinations.value.length} 个组合`);
  } catch (error) {
    console.error('加载组合失败:', error);
    message.error('加载组合失败');
  } finally {
    generatingCombos.value = false;
  }
}

function selectCombo(index: number) {
  selectedComboIndex.value = index;
}

function applySelectedCombo() {
  if (selectedComboIndex.value === null) {
    message.warning('请先选择一个组合');
    return;
  }

  const combo = combinations.value[selectedComboIndex.value];
  if (!combo) return;

  // 检查组合的 nodes 是否为空
  const hasNodes = combo.nodes && Object.keys(combo.nodes).length > 0;
  if (!hasNodes) {
    message.error(
      '该组合的节点数据为空，可能是节点已被删除。请检查策略中引用的节点是否存在，或重新配置策略。',
    );
    console.error(
      '[StrategyImportDrawer] 组合 nodes 为空:',
      combo,
      '请检查后端 _batch_get_nodes 是否能找到这些节点',
    );
    return;
  }

  // 将组合转换为 plugin_config_snapshot
  const snapshot = comboToSnapshot(combo);

  if (snapshot.length === 0) {
    // 提供更详细的错误信息
    const mappedDimensions = Object.entries(variableMapping.value)
      .filter(([_, v]) => v)
      .map(([k, _]) => k);
    const availableNodeDimensions = Object.keys(combo.nodes);
    const mappedVariables = Object.entries(variableMapping.value)
      .filter(([_, v]) => v)
      .map(([k, v]) => `${k} -> ${v}`);
    const availableVariables = filteredExpertVariables.value.map(
      (v) => v.variable_name,
    );

    console.error(
      '[StrategyImportDrawer] 变量映射失败:',
      '\n- 已配置映射的维度:',
      mappedDimensions,
      '\n- 组合中可用的维度:',
      availableNodeDimensions,
      '\n- 已配置的变量映射:',
      mappedVariables,
      '\n- Expert 中可用的变量:',
      availableVariables,
      '\n- 请确保：1) 映射的维度与组合中的维度一致；2) 映射的变量名在 Expert 中存在',
    );

    // 检查是维度不匹配还是变量不存在
    const dimensionMismatch = mappedDimensions.some(
      (d) => !availableNodeDimensions.includes(d),
    );
    const variableMismatch = mappedVariables.some((m) => {
      const variableName = m.split(' -> ')[1];
      return !availableVariables.includes(variableName);
    });

    let errorMsg = '无法生成变量配置：';
    if (dimensionMismatch) {
      errorMsg += `映射的维度 [${mappedDimensions.join(', ')}] 与组合中的维度 [${availableNodeDimensions.join(', ')}] 不匹配`;
    }
    if (variableMismatch) {
      if (dimensionMismatch) errorMsg += '；';
      const missingVars = mappedVariables
        .filter((m) => {
          const variableName = m.split(' -> ')[1];
          return !availableVariables.includes(variableName);
        })
        .map((m) => m.split(' -> ')[1]);
      errorMsg += `映射的变量 [${missingVars.join(', ')}] 在当前 Expert 中不存在`;
      if (props.targetPluginCode) {
        errorMsg += `（当前仅显示插件 ${props.targetPluginName || props.targetPluginCode} 的变量）`;
      }
    }
    if (!dimensionMismatch && !variableMismatch) {
      errorMsg += '未知错误，请检查控制台日志';
    }

    message.warning(errorMsg);
    return;
  }

  const strategyInfo = selectedStrategy.value
    ? {
        strategy_id: selectedStrategy.value.id,
        strategy_name: selectedStrategy.value.name,
      }
    : undefined;
  emit('apply', snapshot, undefined, strategyInfo);
  emit('update:open', false);
  message.success('已应用策略组合到变量配置');
}

function comboToSnapshot(
  combo: ContentStrategyApi.CombinationItem,
): Array<{ plugin_code: string; variable_mapping: Record<string, string> }> {
  // 按 plugin_code 分组
  const pluginMappings: Record<string, Record<string, string>> = {};
  const missingVariables: string[] = [];

  // 如果指定了 targetPluginCode，只处理该插件的变量
  const targetPlugin = props.targetPluginCode;

  for (const [dimensionType, variableName] of Object.entries(
    variableMapping.value,
  )) {
    if (!variableName) continue;

    const node = combo.nodes[dimensionType];
    if (!node) {
      // 维度不匹配的情况已经在 applySelectedCombo 中处理了
      continue;
    }

    // 找到该变量所属的 plugin（使用过滤后的变量列表）
    let found = false;
    for (const plugin of filteredExpertVariables.value) {
      // 如果指定了 targetPluginCode，只匹配该插件的变量
      if (targetPlugin && plugin.plugin_code !== targetPlugin) {
        continue;
      }

      if (plugin.variable_name === variableName) {
        if (!pluginMappings[plugin.plugin_code]) {
          pluginMappings[plugin.plugin_code] = {};
        }
        // 使用 node:xxx 格式
        pluginMappings[plugin.plugin_code]![variableName] = `node:${node.id}`;
        found = true;
        break;
      }
    }

    // 如果找不到对应的变量，记录到缺失列表中
    if (!found) {
      missingVariables.push(`${dimensionType} -> ${variableName}`);
    }
  }

  // 如果有缺失的变量，记录到错误信息中
  if (missingVariables.length > 0) {
    console.warn(
      '[StrategyImportDrawer] 部分变量在 Expert 中不存在:',
      missingVariables,
      '\n- 可用的变量列表:',
      filteredExpertVariables.value.map((v) => v.variable_name),
    );
  }

  // 转换为数组格式
  // 如果指定了 targetPluginCode，只返回该插件的映射
  const result = Object.entries(pluginMappings).map(
    ([plugin_code, mapping]) => ({
      plugin_code,
      variable_mapping: mapping,
    }),
  );

  // 如果指定了 targetPluginCode，过滤出只包含该插件的映射
  if (targetPlugin) {
    return result.filter((item) => item.plugin_code === targetPlugin);
  }

  return result;
}

function handleClose() {
  emit('update:open', false);
}

// 监听抽屉打开和插件变化，重新加载策略
watch(
  () => [props.open, props.targetPluginCode, requiredVariableNames.value],
  (
    [newOpen, newPluginCode, newVariableNames],
    [oldOpen, oldPluginCode, oldVariableNames],
  ) => {
    if (newOpen) {
      // 重置状态
      selectedStrategyId.value = null;
      variableMapping.value = {};
      combinations.value = [];
      selectedComboIndex.value = null;

      // 如果插件或变量发生变化，或者之前没有打开过，重新加载策略
      const pluginChanged = newPluginCode !== oldPluginCode;
      const variablesChanged =
        JSON.stringify(newVariableNames) !== JSON.stringify(oldVariableNames);
      const wasClosed = !oldOpen;

      if (
        wasClosed ||
        pluginChanged ||
        variablesChanged ||
        strategyList.value.length === 0
      ) {
        loadStrategies();
      }
    }
  },
  { deep: true },
);
</script>

<template>
  <Drawer
    :open="open"
    :title="
      targetPluginName
        ? `从策略导入变量 - ${targetPluginName}`
        : '从策略导入变量组合'
    "
    :width="800"
    @close="handleClose"
  >
    <Spin :spinning="loading">
      <div class="strategy-import-content">
        <!-- 策略选择 -->
        <div class="section">
          <div class="section-header">
            <h4 class="section-title">1. 选择关键词策略</h4>
            <div class="cache-actions">
              <Tag v-if="usedCache" color="green" class="cache-tag">
                ⚡ 缓存
              </Tag>
              <Tag v-if="cacheInfo.strategiesAge !== null" class="cache-tag">
                {{ Math.floor(cacheInfo.strategiesAge / 60) }}分钟前
              </Tag>
              <Button size="small" type="link" @click="refreshCache">
                🔄 刷新
              </Button>
            </div>
          </div>

          <!-- 策略选择下拉框 -->
          <Select
            v-if="hasMatchingStrategies"
            v-model:value="selectedStrategyId"
            placeholder="选择一个关键词策略"
            style="width: 100%"
            show-search
            option-filter-prop="label"
            :options="strategyOptions"
            @change="onStrategyChange"
          />

          <!-- 无匹配策略时的提示 -->
          <Alert
            v-else-if="!loading && requiredVariableNames.length > 0"
            message="暂无匹配的关键词策略"
            type="warning"
            show-icon
          >
            <template #description>
              <div>
                当前插件需要以下关键词分类:
                <div class="mt-2">
                  <Tag
                    v-for="varName in requiredVariableNames"
                    :key="varName"
                    color="purple"
                  >
                    {{ varName }}
                  </Tag>
                </div>
                <div class="mt-2">
                  请在关键词策略中添加包含这些分类的策略,或点击刷新按钮重新加载。
                </div>
              </div>
            </template>
          </Alert>
        </div>

        <!-- 变量映射配置 -->
        <div v-if="selectedStrategy" class="section">
          <h4 class="section-title">2. 配置变量映射</h4>
          <Alert
            message="将关键词分类映射到 Expert 的变量。选择后，策略生成的关键词会填充到对应变量。"
            type="info"
            show-icon
            class="mb-3"
          />

          <div class="mapping-list">
            <Row
              v-for="categoryType in categoryTypes"
              :key="categoryType"
              :gutter="16"
              class="mapping-row"
            >
              <Col :span="8">
                <div class="category-label">
                  <Tag color="purple">{{ categoryType }}</Tag>
                </div>
              </Col>
              <Col :span="4" class="arrow-col">
                <span class="mapping-arrow">→</span>
              </Col>
              <Col :span="12">
                <Select
                  :value="variableMapping[categoryType]"
                  placeholder="选择 Expert 变量"
                  style="width: 100%"
                  allow-clear
                  show-search
                  :filter-option="true"
                  @change="(v: string) => setVariableMapping(categoryType, v)"
                >
                  <SelectOption
                    v-for="v in availableVariables"
                    :key="`${v.plugin_code}:${v.variable_name}`"
                    :value="v.variable_name"
                  >
                    {{ v.variable_name }}
                    <span class="text-xs text-muted-foreground">
                      ({{ v.plugin_code }})
                    </span>
                  </SelectOption>
                </Select>
              </Col>
            </Row>
          </div>

          <div class="mt-3">
            <Button
              type="primary"
              :loading="generatingCombos"
              @click="loadCombinations"
            >
              📥 加载组合
            </Button>
          </div>
        </div>

        <!-- 组合预览 -->
        <div v-if="combinations.length > 0" class="section">
          <h4 class="section-title">
            3. 选择要应用的组合 ({{ combinations.length }} 个)
          </h4>

          <div class="combo-grid">
            <Card
              v-for="(combo, idx) in combinations"
              :key="idx"
              size="small"
              class="combo-card"
              :class="{ selected: selectedComboIndex === idx }"
              @click="selectCombo(idx)"
            >
              <template #title>
                <div class="combo-header">
                  <span class="combo-index">#{{ idx + 1 }}</span>
                  <Tag v-if="selectedComboIndex === idx" color="green">
                    已选中
                  </Tag>
                </div>
              </template>
              <div class="combo-nodes">
                <!-- 如果有节点详情，显示分类+关键词 -->
                <template v-if="Object.keys(combo.nodes || {}).length > 0">
                  <div class="node-list">
                    <div
                      v-for="(node, dimType) in combo.nodes"
                      :key="dimType"
                      class="node-item"
                    >
                      <span class="node-dimension">{{
                        node.label || dimType
                      }}</span>
                      <span class="node-name">{{ node.name || dimType }}</span>
                    </div>
                  </div>
                </template>
                <!-- 如果节点详情为空，显示组合名称 -->
                <span v-else class="combo-name-fallback">
                  {{ combo.name }}
                </span>
              </div>
            </Card>
          </div>
        </div>

        <Divider />

        <!-- 操作按钮 -->
        <div class="action-bar">
          <Button @click="handleClose">取消</Button>
          <Button
            type="primary"
            :disabled="selectedComboIndex === null"
            @click="applySelectedCombo"
          >
            应用选中的组合
          </Button>
        </div>
      </div>
    </Spin>
  </Drawer>
</template>

<style scoped>
.strategy-import-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.section {
  padding: 16px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.section-header {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.cache-actions {
  display: flex;
  gap: 4px;
  align-items: center;
}

.cache-tag {
  margin: 0;
  font-size: 11px;
}

.mapping-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.mapping-row {
  align-items: center;
}

.category-label {
  display: flex;
  gap: 6px;
  align-items: center;
}

.arrow-col {
  text-align: center;
}

.mapping-arrow {
  font-size: 18px;
  color: hsl(var(--muted-foreground));
}

.combo-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  max-height: 300px;
  overflow-y: auto;
}

.combo-card {
  cursor: pointer;
  transition: all 0.2s;
}

.combo-card:hover {
  border-color: hsl(var(--primary) / 50%);
}

.combo-card.selected {
  background: hsl(var(--primary) / 8%);
  border-color: hsl(var(--primary));
}

.combo-header {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.combo-index {
  font-family: Monaco, Menlo, monospace;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.combo-nodes {
  padding: 4px 0;
}

.node-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.node-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.node-dimension {
  font-size: 11px;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
}

.node-name {
  font-size: 13px;
  color: hsl(var(--foreground));
}

.combo-name-fallback {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  word-break: break-all;
}

.action-bar {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.mb-3 {
  margin-bottom: 12px;
}

.mt-3 {
  margin-top: 12px;
}

.mode-hint {
  margin-left: 8px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}
</style>
