<script setup lang="ts">
/**
 * 智能策略选择器组件
 *
 * 核心功能：
 * 1. 根据已选 Expert 的变量需求，智能推荐匹配的策略
 * 2. 可视化展示策略维度与 Expert 变量的映射关系
 * 3. 实时检测漏选的变量
 * 4. 支持策略筛选和排序
 *
 * 数据流：
 * Expert 变量需求 → 策略维度供应 → 匹配度计算 → 智能推荐
 */

import type { ContentStrategyApi } from '#/api/core/content-strategy';
import type { MetadataApi } from '#/api/core/graph-corpus';

import { computed, ref, watch } from 'vue';

import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  FilterOutlined,
  PlusOutlined,
  StarOutlined,
} from '@ant-design/icons-vue';
import {
  Alert,
  Button,
  Card,
  Divider,
  Empty,
  Input,
  RadioButton,
  RadioGroup,
  Space,
  Spin,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import { getTagTreeApi } from '#/api/core/graph-corpus';

// ==================== 类型定义 ====================

export interface ExpertVariable {
  expert_code: string;
  expert_name: string;
  variables: string[];
}

export interface StrategyWithMatchInfo {
  strategy: ContentStrategyApi.ContentStrategy;
  dimensions: string[];
  matchInfo: {
    matchedDimensions: Array<{
      dimension: string;
      matchedVariables: Array<{
        expert_code: string;
        variable: string;
      }>;
    }>;
    score: number; // 匹配度 0-100
    unmatchedVariables: string[];
  };
}

export interface VariableMapping {
  dimension: string;
  expert_code: string;
  variable: string;
}

// ==================== Props ====================

interface Props {
  // Expert 变量需求列表
  expertVariables: ExpertVariable[];
  // 可选策略列表
  strategies: ContentStrategyApi.ContentStrategy[];
  // 已选策略 ID
  selectedStrategyIds: string[];
  // 当前的变量映射配置
  variableMappings: Record<
    string,
    Array<{ expert_code: string; variable: string }>
  >;
  // 租户编码（用于获取标签名称）
  tenantCode?: string;
  // 加载状态
  loading?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  tenantCode: 'default',
  loading: false,
});

// ==================== Emits ====================

const emit = defineEmits<{
  (e: 'update:selectedStrategyIds', value: string[]): void;
  (
    e: 'update:variableMappings',
    value: Record<string, Array<{ expert_code: string; variable: string }>>,
  ): void;
  (e: 'openMappingDrawer'): void;
}>();

// ==================== 状态 ====================

// 筛选模式
type FilterMode = 'all' | 'by-tag' | 'recommended' | 'unmapped';
const filterMode = ref<FilterMode>('recommended');
const searchKeyword = ref('');
const selectedTags = ref<string[]>([]);

// 标签树缓存（用于解析标签 ID 到名称）
const tagTreeMap = ref<Record<string, string>>({});
const tagTreeLoading = ref(false);

// ==================== 标签名称解析 ====================

// 加载标签树
async function loadTagTree() {
  if (!props.tenantCode) return;

  tagTreeLoading.value = true;
  try {
    const tree = await getTagTreeApi(props.tenantCode);
    const map: Record<string, string> = {};

    function buildMap(nodes: MetadataApi.MetadataTreeNode[]) {
      for (const node of nodes) {
        map[node.id] = node.name;
        map[node.key] = node.name; // 兼容 id 和 key
        if (node.children?.length) {
          buildMap(node.children);
        }
      }
    }

    buildMap(tree);
    tagTreeMap.value = map;
  } catch (error) {
    console.error('加载标签树失败:', error);
  } finally {
    tagTreeLoading.value = false;
  }
}

// 监听租户变化，重新加载标签树
watch(
  () => props.tenantCode,
  () => {
    loadTagTree();
  },
  { immediate: true },
);

// ==================== 计算属性 ====================

// 提取所有 Expert 变量（去重）
const allExpertVariables = computed(() => {
  const variableSet = new Set<string>();
  const variableExperts = new Map<string, Set<string>>();

  for (const expert of props.expertVariables) {
    for (const variable of expert.variables) {
      variableSet.add(variable);
      if (!variableExperts.has(variable)) {
        variableExperts.set(variable, new Set());
      }
      variableExperts.get(variable)!.add(expert.expert_code);
    }
  }

  return {
    variables: [...variableSet],
    variableExperts,
  };
});

// 已映射的变量（基于当前 variableMappings）
const mappedVariables = computed(() => {
  const mapped = new Set<string>();
  for (const mappings of Object.values(props.variableMappings)) {
    for (const m of mappings) {
      mapped.add(m.variable);
    }
  }
  return mapped;
});

// 未映射的变量
const unmappedVariables = computed(() => {
  return allExpertVariables.value.variables.filter(
    (v) => !mappedVariables.value.has(v),
  );
});

// 计算策略匹配度
const strategiesWithMatch = computed((): StrategyWithMatchInfo[] => {
  const result: StrategyWithMatchInfo[] = [];

  for (const strategy of props.strategies) {
    // 提取策略维度
    const dimensions = extractStrategyDimensions(strategy);

    // 计算匹配信息
    const matchInfo = calculateMatchInfo(dimensions);

    result.push({
      strategy,
      dimensions,
      matchInfo,
    });
  }

  // 按匹配度排序
  return result.toSorted((a, b) => b.matchInfo.score - a.matchInfo.score);
});

// 提取策略维度
function extractStrategyDimensions(
  strategy: ContentStrategyApi.ContentStrategy,
): string[] {
  const dims = new Set<string>();

  // v3 新结构
  if (strategy.node_pools) {
    Object.keys(strategy.node_pools).forEach((dim) => dims.add(dim));
  }

  // v1 旧结构
  // 从 node_pools 提取维度
  if (strategy.node_pools) {
    Object.keys(strategy.node_pools).forEach((dim) => dims.add(dim));
  }

  // manual 模式从 defined_combinations 提取
  if (
    strategy.defined_combinations &&
    strategy.defined_combinations.length > 0
  ) {
    const firstCombo = strategy.defined_combinations[0];
    if (firstCombo?.nodes) {
      Object.keys(firstCombo.nodes).forEach((dim) => dims.add(dim));
    }
  }

  return [...dims];
}

// 计算匹配信息
function calculateMatchInfo(dimensions: string[]) {
  const matchedDimensions: Array<{
    dimension: string;
    matchedVariables: Array<{ expert_code: string; variable: string }>;
  }> = [];

  const matchedVariableSet = new Set<string>();

  // 尝试匹配每个维度到变量（只做精确匹配）
  for (const dimension of dimensions) {
    const matchedVars: Array<{ expert_code: string; variable: string }> = [];
    const dimLower = dimension.toLowerCase();

    for (const expert of props.expertVariables) {
      for (const variable of expert.variables) {
        // 如果这个变量已经被其他维度匹配了，跳过（避免重复匹配）
        if (matchedVariableSet.has(variable)) continue;

        const varLower = variable.toLowerCase();

        // 只保留精确匹配（策略维度和 Expert 变量名必须完全相同）
        if (varLower === dimLower) {
          matchedVars.push({ expert_code: expert.expert_code, variable });
          matchedVariableSet.add(variable);
        }
      }
    }

    if (matchedVars.length > 0) {
      matchedDimensions.push({
        dimension,
        matchedVariables: matchedVars,
      });
    }
  }

  // 计算未匹配的变量
  const unmatchedVariables = allExpertVariables.value.variables.filter(
    (v) => !matchedVariableSet.has(v) && !mappedVariables.value.has(v),
  );

  // 计算匹配分数 (0-100)
  const totalVariables = allExpertVariables.value.variables.length;
  const score =
    totalVariables > 0
      ? Math.round((matchedVariableSet.size / totalVariables) * 100)
      : 0;

  return {
    score,
    matchedDimensions,
    unmatchedVariables,
  };
}

// 筛选后的策略列表
const filteredStrategies = computed(() => {
  let result = strategiesWithMatch.value;

  // 关键词搜索（仅搜索策略名称）
  if (searchKeyword.value.trim()) {
    const keyword = searchKeyword.value.trim().toLowerCase();
    result = result.filter((s) =>
      s.strategy.name.toLowerCase().includes(keyword),
    );
  }

  // 模式筛选
  switch (filterMode.value) {
    case 'by-tag': {
      // 按标签筛选
      if (selectedTags.value.length > 0) {
        result = result.filter((s) =>
          s.strategy.tags?.some((tag) => selectedTags.value.includes(tag)),
        );
      }
      break;
    }
    case 'recommended': {
      // 只显示匹配度 > 0 或包含未映射变量的策略
      result = result.filter(
        (s) =>
          s.matchInfo.score > 0 ||
          s.matchInfo.unmatchedVariables.length <
            allExpertVariables.value.variables.length,
      );
      break;
    }
    case 'unmapped': {
      // 只显示能解决未映射变量的策略
      result = result.filter((s) =>
        s.matchInfo.matchedDimensions.some((dim) =>
          dim.matchedVariables.some((v) =>
            unmappedVariables.value.includes(v.variable),
          ),
        ),
      );
      break;
    }
  }

  return result;
});

// 获取所有可用标签（从策略中提取）
const availableTags = computed(() => {
  // 使用 Set 去重并保持插入顺序
  const uniqueTags = new Set<string>();
  for (const s of props.strategies) {
    if (s.tags) {
      for (const tag of s.tags) {
        uniqueTags.add(tag);
      }
    }
  }

  // 转换为数组，使用 tagTreeMap 确保显示名称而不是 ID
  return [...uniqueTags].map((tagId) => ({
    id: tagId,
    name: tagTreeMap.value[tagId] || tagId,
  }));
});

// 按匹配度分组策略
const strategiesByMatchGroup = computed(() => {
  const groups: Record<
    string,
    { label: string; strategies: typeof filteredStrategies.value }
  > = {
    perfect: { label: '完美匹配', strategies: [] },
    partial: { label: '部分匹配', strategies: [] },
    none: { label: '不匹配', strategies: [] },
  };

  const totalVars = allExpertVariables.value.variables.length;

  for (const item of filteredStrategies.value) {
    // 去重计算实际匹配的变量数
    const uniqueMatched = new Set<string>();
    for (const dim of item.matchInfo.matchedDimensions) {
      for (const v of dim.matchedVariables) {
        uniqueMatched.add(v.variable);
      }
    }

    const matchRatio = totalVars > 0 ? uniqueMatched.size / totalVars : 0;

    if (matchRatio >= 1) {
      groups.perfect.strategies.push(item);
    } else if (matchRatio > 0) {
      groups.partial.strategies.push(item);
    } else {
      groups.none.strategies.push(item);
    }
  }

  // 按匹配度排序
  groups.perfect.strategies = [...groups.perfect.strategies].toSorted(
    (a, b) => b.matchInfo.score - a.matchInfo.score,
  );
  groups.partial.strategies = [...groups.partial.strategies].toSorted(
    (a, b) => b.matchInfo.score - a.matchInfo.score,
  );

  return groups;
});

// ==================== 方法 ====================

// 切换策略选择
function toggleStrategy(strategyId: string) {
  const isSelected = props.selectedStrategyIds.includes(strategyId);
  const newIds = isSelected
    ? props.selectedStrategyIds.filter((id) => id !== strategyId)
    : [...props.selectedStrategyIds, strategyId];

  emit('update:selectedStrategyIds', newIds);
}

// 切换标签筛选
function toggleTag(tagId: string) {
  const index = selectedTags.value.indexOf(tagId);
  if (index === -1) {
    selectedTags.value.push(tagId);
  } else {
    selectedTags.value.splice(index, 1);
  }
  // 切换到按标签筛选模式
  if (filterMode.value !== 'by-tag') {
    filterMode.value = 'by-tag';
  }
}

// 检查变量是否已映射
function isVariableMapped(variable: string): boolean {
  return mappedVariables.value.has(variable);
}

// 检查维度是否已映射到变量
function isDimensionMapped(dimension: string): boolean {
  return props.variableMappings[dimension]?.length > 0;
}

// 获取策略是否已选中
function isStrategySelected(strategyId: string): boolean {
  return props.selectedStrategyIds.includes(strategyId);
}

// 获取策略推荐等级
function getRecommendationLevel(score: number): 'high' | 'low' | 'medium' {
  if (score >= 70) return 'high';
  if (score >= 40) return 'medium';
  return 'low';
}

// 获取推荐等级颜色
function getRecommendationColor(level: string): string {
  switch (level) {
    case 'high': {
      return 'green';
    }
    case 'medium': {
      return 'orange';
    }
    default: {
      return 'default';
    }
  }
}

// 获取推荐等级文本
function getRecommendationText(level: string): string {
  switch (level) {
    case 'high': {
      return '强烈推荐';
    }
    case 'medium': {
      return '推荐';
    }
    default: {
      return '不推荐';
    }
  }
}

// 获取变量状态图标
function getVariableStatusIcon(
  variable: string,
):
  | typeof CheckCircleOutlined
  | typeof CloseCircleOutlined
  | typeof ExclamationCircleOutlined {
  if (mappedVariables.value.has(variable)) {
    return CheckCircleOutlined;
  }
  // 检查是否有策略能匹配这个变量
  const canMatch = strategiesWithMatch.value.some((s) =>
    s.matchInfo.matchedDimensions.some((dim) =>
      dim.matchedVariables.some((v) => v.variable === variable),
    ),
  );
  return canMatch ? ExclamationCircleOutlined : CloseCircleOutlined;
}

// 获取变量状态颜色
function getVariableStatusColor(variable: string): string {
  if (mappedVariables.value.has(variable)) return 'success';
  // 检查是否有策略能匹配这个变量
  const canMatch = strategiesWithMatch.value.some((s) =>
    s.matchInfo.matchedDimensions.some((dim) =>
      dim.matchedVariables.some((v) => v.variable === variable),
    ),
  );
  return canMatch ? 'warning' : 'error';
}

// 自动映射选中策略的变量
function autoMapSelectedStrategies() {
  const newMappings: Record<
    string,
    Array<{ expert_code: string; variable: string }>
  > = {
    ...props.variableMappings,
  };

  for (const strategyId of props.selectedStrategyIds) {
    const strategyWithMatch = strategiesWithMatch.value.find(
      (s) => s.strategy.id === strategyId,
    );
    if (!strategyWithMatch) continue;

    for (const dimMatch of strategyWithMatch.matchInfo.matchedDimensions) {
      const dimension = dimMatch.dimension;

      if (!newMappings[dimension]) {
        newMappings[dimension] = [];
      }

      for (const varMatch of dimMatch.matchedVariables) {
        // 检查是否已存在映射
        const exists = newMappings[dimension].some(
          (m) =>
            m.expert_code === varMatch.expert_code &&
            m.variable === varMatch.variable,
        );
        if (!exists) {
          newMappings[dimension].push({
            expert_code: varMatch.expert_code,
            variable: varMatch.variable,
          });
        }
      }
    }
  }

  emit('update:variableMappings', newMappings);
}

// 监听选中策略变化，自动映射
watch(
  () => props.selectedStrategyIds,
  () => {
    autoMapSelectedStrategies();
  },
  { deep: true },
);

// ==================== 统计信息 ====================

// 提取所有选中策略的维度
const allStrategyDimensions = computed(() => {
  const dims = new Set<string>();
  for (const strategyWithInfo of strategiesWithMatch.value) {
    for (const dim of strategyWithInfo.dimensions) {
      dims.add(dim.toLowerCase());
    }
  }
  return dims;
});

const stats = computed(() => {
  const allVars = allExpertVariables.value.variables;

  // 分类变量：策略变量 vs 非策略变量
  const strategyVars: string[] = [];
  const nonStrategyVars: string[] = [];

  for (const variable of allVars) {
    if (allStrategyDimensions.value.has(variable.toLowerCase())) {
      strategyVars.push(variable);
    } else {
      nonStrategyVars.push(variable);
    }
  }

  // 统计映射情况
  const strategyVarsMapped = strategyVars.filter((v) =>
    mappedVariables.value.has(v),
  ).length;
  const nonStrategyVarsMapped = nonStrategyVars.filter((v) =>
    mappedVariables.value.has(v),
  ).length;

  // 策略变量的进度（只计算策略变量的映射进度）
  const strategyProgress =
    strategyVars.length > 0
      ? Math.round((strategyVarsMapped / strategyVars.length) * 100)
      : 100;

  return {
    total: allVars.length,
    mapped: mappedVariables.value.size,
    unmapped: unmappedVariables.value.length,
    progress: strategyProgress,

    // 新增：策略变量统计
    strategyVars: {
      total: strategyVars.length,
      mapped: strategyVarsMapped,
      unmapped: strategyVars.length - strategyVarsMapped,
      list: strategyVars,
    },

    // 新增：非策略变量统计
    nonStrategyVars: {
      total: nonStrategyVars.length,
      mapped: nonStrategyVarsMapped,
      unmapped: nonStrategyVars.length - nonStrategyVarsMapped,
      list: nonStrategyVars,
    },
  };
});
</script>

<template>
  <div class="strategy-smart-selector">
    <!-- 顶部概览：Expert 变量需求 -->
    <Card class="overview-card" size="small">
      <template #title>
        <div class="card-title">
          <span>变量需求概览</span>
          <Tag
            :color="
              stats.progress === 100
                ? 'green'
                : stats.progress > 50
                  ? 'orange'
                  : 'red'
            "
          >
            策略变量 {{ stats.strategyVars.mapped }}/{{
              stats.strategyVars.total
            }}
            ({{ stats.progress }}%)
          </Tag>
          <Tag v-if="stats.nonStrategyVars.total > 0" color="default">
            非策略变量 {{ stats.nonStrategyVars.mapped }}/{{
              stats.nonStrategyVars.total
            }}
          </Tag>
        </div>
      </template>

      <!-- 进度条（只显示策略变量的进度） -->
      <div class="progress-bar">
        <div
          class="progress-fill"
          :style="{ width: `${stats.progress}%` }"
        ></div>
      </div>

      <!-- 变量列表 -->
      <div class="variable-grid">
        <!-- 策略变量 -->
        <Tooltip
          v-for="variable in stats.strategyVars.list"
          :key="variable"
          :title="
            isVariableMapped(variable)
              ? '已映射（使用关键词策略）'
              : '未映射（使用关键词策略）'
          "
        >
          <Tag
            :color="getVariableStatusColor(variable)"
            class="variable-tag"
            :class="[{ mapped: isVariableMapped(variable) }]"
          >
            <component
              :is="getVariableStatusIcon(variable)"
              class="status-icon"
            />
            {{ variable }}
          </Tag>
        </Tooltip>

        <!-- 非策略变量（单独分组显示） -->
        <div
          v-if="stats.nonStrategyVars.list.length > 0"
          class="non-strategy-vars-divider"
        >
          <Divider
            style="
              margin: 16px 0 8px;
              font-size: 12px;
              color: hsl(var(--muted-foreground));
            "
          >
            其他变量
          </Divider>
        </div>

        <Tooltip
          v-for="variable in stats.nonStrategyVars.list"
          :key="`non-strategy-${variable}`"
          :title="
            isVariableMapped(variable)
              ? '已映射（其他变量）'
              : '未映射（其他变量）'
          "
        >
          <Tag
            :color="getVariableStatusColor(variable)"
            class="variable-tag non-strategy"
            :class="[{ mapped: isVariableMapped(variable) }]"
            style="opacity: 0.7"
          >
            <component
              :is="getVariableStatusIcon(variable)"
              class="status-icon"
            />
            {{ variable }}
          </Tag>
        </Tooltip>
      </div>

      <Alert
        v-if="stats.strategyVars.unmapped > 0"
        type="warning"
        show-icon
        class="unmapped-alert"
      >
        <template #message>
          有
          {{ stats.strategyVars.unmapped }}
          个策略变量尚未映射，请选择包含对应维度的策略
        </template>
      </Alert>
    </Card>

    <!-- 策略筛选和列表 -->
    <Card class="strategies-card" size="small">
      <template #title>
        <div class="card-title">
          <span>策略选择</span>
          <Tag color="blue">{{ filteredStrategies.length }} 个可用策略</Tag>
        </div>
      </template>

      <!-- 标签筛选区 -->
      <div v-if="availableTags.length > 0" class="tag-filter-section">
        <div class="tag-filter-header">
          <span class="filter-label">按业务标签筛选：</span>
          <Button
            v-if="selectedTags.length > 0"
            type="link"
            size="small"
            @click="selectedTags = []"
          >
            清除
          </Button>
        </div>
        <div class="tag-chips">
          <Tag
            v-for="tag in availableTags"
            :key="tag.id"
            :color="selectedTags.includes(tag.id) ? 'blue' : 'default'"
            class="clickable"
            @click="toggleTag(tag.id)"
          >
            {{ tag.name }}
          </Tag>
        </div>
      </div>

      <!-- 筛选模式切换 -->
      <div class="filter-mode-tabs">
        <RadioGroup
          v-model:value="filterMode"
          button-style="solid"
          size="small"
        >
          <RadioButton value="grouped">
            <StarOutlined />
            分组展示
          </RadioButton>
          <RadioButton value="recommended"> 智能推荐 </RadioButton>
          <RadioButton value="all"> 全部策略 </RadioButton>
          <RadioButton value="unmapped">
            <ExclamationCircleOutlined />
            解决漏选
          </RadioButton>
        </RadioGroup>

        <Input
          v-model:value="searchKeyword"
          placeholder="搜索策略名称..."
          allow-clear
          style="width: 200px"
        >
          <template #prefix>
            <FilterOutlined />
          </template>
        </Input>
      </div>

      <!-- 策略列表 -->
      <Spin :spinning="loading">
        <div v-if="filteredStrategies.length === 0" class="empty-state">
          <Empty description="没有找到匹配的策略">
            <template v-if="filterMode !== 'all'">
              <Button type="link" @click="filterMode = 'all'">
                查看全部策略
              </Button>
            </template>
          </Empty>
        </div>

        <!-- 分组展示模式 -->
        <template v-else-if="filterMode === 'grouped'">
          <div
            v-for="(group, groupKey) in strategiesByMatchGroup"
            :key="groupKey"
            class="match-group"
          >
            <div v-if="group.strategies.length > 0" class="match-group-header">
              <span class="group-label">{{ group.label }}</span>
              <Tag
                :color="
                  groupKey === 'perfect'
                    ? 'green'
                    : groupKey === 'partial'
                      ? 'orange'
                      : 'default'
                "
              >
                {{ group.strategies.length }} 个策略
              </Tag>
            </div>

            <div class="strategy-list">
              <div
                v-for="item in group.strategies"
                :key="item.strategy.id"
                class="strategy-card"
                :class="[{ selected: isStrategySelected(item.strategy.id) }]"
                @click="toggleStrategy(item.strategy.id)"
              >
                <!-- 策略头部 -->
                <div class="strategy-header">
                  <div class="strategy-title-row">
                    <div class="strategy-name">{{ item.strategy.name }}</div>
                    <Space :size="4">
                      <Tag
                        v-if="isStrategySelected(item.strategy.id)"
                        color="green"
                      >
                        <CheckCircleOutlined />
                        已选择
                      </Tag>
                      <Tag
                        v-for="tag in item.strategy.tags"
                        :key="tag"
                        color="blue"
                      >
                        {{ tagTreeMap[tag] || tag }}
                      </Tag>
                    </Space>
                  </div>

                  <div
                    v-if="item.strategy.description"
                    class="strategy-description"
                  >
                    {{ item.strategy.description }}
                  </div>
                </div>

                <!-- 匹配详情 - 简化版 -->
                <div class="match-summary">
                  <div class="matched-vars">
                    <template
                      v-for="dim in item.matchInfo.matchedDimensions"
                      :key="dim.dimension"
                    >
                      <Tag color="green" size="small">
                        {{ dim.dimension }}
                        <span class="var-count"
                          >({{ dim.matchedVariables.length }})</span
                        >
                      </Tag>
                    </template>
                    <template
                      v-if="item.matchInfo.unmatchedVariables.length > 0"
                    >
                      <Tag color="default" size="small">
                        +{{ item.matchInfo.unmatchedVariables.length }} 个变量
                      </Tag>
                    </template>
                  </div>
                  <div class="match-score-mini">
                    {{ item.matchInfo.score }}% 匹配
                  </div>
                </div>

                <!-- 快速选择按钮 -->
                <div class="strategy-action">
                  <Button
                    :type="
                      isStrategySelected(item.strategy.id)
                        ? 'primary'
                        : 'default'
                    "
                    size="small"
                  >
                    <template v-if="isStrategySelected(item.strategy.id)">
                      <CheckCircleOutlined />
                      已选择
                    </template>
                    <template v-else>
                      <PlusOutlined />
                      选择
                    </template>
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </template>

        <!-- 列表模式 -->
        <div v-else class="strategy-list">
          <div
            v-for="item in filteredStrategies"
            :key="item.strategy.id"
            class="strategy-card"
            :class="[{ selected: isStrategySelected(item.strategy.id) }]"
            @click="toggleStrategy(item.strategy.id)"
          >
            <!-- 策略头部 -->
            <div class="strategy-header">
              <div class="strategy-title-row">
                <div class="strategy-name">{{ item.strategy.name }}</div>
                <Space :size="4">
                  <Tag
                    :color="
                      getRecommendationColor(
                        getRecommendationLevel(item.matchInfo.score),
                      )
                    "
                  >
                    <StarOutlined
                      v-if="
                        getRecommendationLevel(item.matchInfo.score) === 'high'
                      "
                    />
                    {{
                      getRecommendationText(
                        getRecommendationLevel(item.matchInfo.score),
                      )
                    }}
                  </Tag>
                  <Tag
                    v-if="isStrategySelected(item.strategy.id)"
                    color="green"
                  >
                    <CheckCircleOutlined />
                    已选择
                  </Tag>
                  <Tag
                    v-for="tag in item.strategy.tags"
                    :key="tag"
                    color="blue"
                  >
                    {{ tagTreeMap[tag] || tag }}
                  </Tag>
                </Space>
              </div>

              <div
                v-if="item.strategy.description"
                class="strategy-description"
              >
                {{ item.strategy.description }}
              </div>
            </div>

            <!-- 匹配详情 -->
            <div class="match-details">
              <div class="match-score">
                <div class="score-label">匹配度</div>
                <div
                  class="score-value"
                  :class="getRecommendationLevel(item.matchInfo.score)"
                >
                  {{ item.matchInfo.score }}%
                </div>
              </div>

              <div class="dimension-list">
                <!-- 匹配的维度 -->
                <div
                  v-if="item.matchInfo.matchedDimensions.length > 0"
                  class="matched-dimensions"
                >
                  <div class="dimension-section-title">
                    <CheckCircleOutlined class="icon-success" />
                    <span
                      >可满足
                      {{
                        item.matchInfo.matchedDimensions.reduce(
                          (sum, dim) => sum + dim.matchedVariables.length,
                          0,
                        )
                      }}
                      个变量</span
                    >
                  </div>
                  <div class="dimension-tags">
                    <Tooltip
                      v-for="dim in item.matchInfo.matchedDimensions"
                      :key="dim.dimension"
                      :title="
                        dim.matchedVariables
                          .map((v) => `${v.expert_code}.${v.variable}`)
                          .join(', ')
                      "
                    >
                      <Tag
                        :color="
                          isDimensionMapped(dim.dimension) ? 'green' : 'blue'
                        "
                      >
                        {{ dim.dimension }}
                        <span class="variable-count"
                          >({{ dim.matchedVariables.length }})</span
                        >
                      </Tag>
                    </Tooltip>
                  </div>
                </div>

                <!-- 未满足的变量 -->
                <div
                  v-if="item.matchInfo.unmatchedVariables.length > 0"
                  class="unmatched-variables"
                >
                  <div class="dimension-section-title">
                    <ExclamationCircleOutlined class="icon-warning" />
                    <span
                      >缺少
                      {{ item.matchInfo.unmatchedVariables.length }}
                      个变量</span
                    >
                  </div>
                  <div class="variable-tags">
                    <Tag
                      v-for="v in item.matchInfo.unmatchedVariables"
                      :key="v"
                      color="default"
                    >
                      {{ v }}
                    </Tag>
                  </div>
                </div>
              </div>
            </div>

            <!-- 选择按钮 -->
            <div class="strategy-action">
              <Button
                :type="
                  isStrategySelected(item.strategy.id) ? 'primary' : 'default'
                "
                size="small"
              >
                <template v-if="isStrategySelected(item.strategy.id)">
                  <CheckCircleOutlined />
                  已选择
                </template>
                <template v-else>
                  <PlusOutlined />
                  选择此策略
                </template>
              </Button>
            </div>
          </div>
        </div>
      </Spin>
    </Card>

    <!-- 变量映射矩阵摘要 -->
    <Card
      v-if="Object.keys(variableMappings).length > 0"
      class="mapping-card"
      size="small"
    >
      <template #title>
        <div class="card-title">
          <span>变量映射摘要</span>
          <Button type="link" size="small" @click="$emit('openMappingDrawer')">
            详细配置
          </Button>
        </div>
      </template>

      <div class="mapping-matrix">
        <div
          v-for="(mappings, dimension) in variableMappings"
          :key="dimension"
          class="mapping-row"
        >
          <Tag color="purple" class="dimension-tag">{{ dimension }}</Tag>
          <span class="mapping-arrow">→</span>
          <Space size="small" wrap>
            <Tag
              v-for="m in mappings"
              :key="`${m.expert_code}-${m.variable}`"
              color="green"
            >
              {{ m.expert_code }}.{{ m.variable }}
            </Tag>
          </Space>
        </div>
      </div>
    </Card>
  </div>
</template>

<style scoped>
.strategy-smart-selector {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 卡片标题 */
.card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* 进度条 */
.progress-bar {
  position: relative;
  height: 8px;
  margin-bottom: 16px;
  overflow: hidden;
  background: hsl(var(--muted));
  border-radius: 4px;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(
    90deg,
    hsl(var(--primary)) 0%,
    hsl(var(--success)) 100%
  );
  transition: width 0.3s ease;
}

/* 变量网格 */
.variable-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.variable-tag {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 4px 10px;
  font-size: 13px;
  cursor: default;
  border-radius: 4px;
}

.variable-tag .status-icon {
  font-size: 12px;
}

.variable-tag.mapped {
  opacity: 0.6;
}

.unmapped-alert {
  margin-top: 12px;
}

/* 筛选工具栏 */
.filter-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
  margin-bottom: 16px;
}

/* 标签筛选区 */
.tag-filter-section {
  padding: 12px 16px;
  margin-bottom: 16px;
  background: hsl(var(--muted) / 30%);
  border-radius: 8px;
}

.tag-filter-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.filter-label {
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.tag-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag-chips .clickable {
  cursor: pointer;
  transition: all 0.2s ease;
}

.tag-chips .clickable:hover {
  opacity: 0.8;
}

/* 筛选模式标签 */
.filter-mode-tabs {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 12px 16px;
  margin-bottom: 16px;
  background: hsl(var(--muted) / 30%);
  border-radius: 8px;
}

/* 分组标题 */
.match-group-header {
  display: flex;
  gap: 8px;
  align-items: center;
  padding-bottom: 8px;
  margin: 16px 0 12px;
  border-bottom: 1px solid hsl(var(--border) / 50%);
}

.group-label {
  font-size: 14px;
  font-weight: 600;
}

/* 匹配摘要（简化版） */
.match-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  margin-bottom: 12px;
  background: hsl(var(--muted) / 30%);
  border-radius: 6px;
}

.matched-vars {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.match-score-mini {
  font-size: 12px;
  font-weight: 600;
  color: hsl(var(--muted-foreground));
}

.var-count {
  font-size: 11px;
  opacity: 0.6;
}

/* 策略列表 */
.strategy-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.strategy-card {
  padding: 12px;
  cursor: pointer;
  background: hsl(var(--background));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  transition: all 0.2s ease;
}

.strategy-card:hover {
  border-color: hsl(var(--primary));
  box-shadow: 0 2px 8px rgb(0 0 0 / 8%);
}

.strategy-card.selected {
  background: hsl(var(--primary) / 5%);
  border-color: hsl(var(--primary));
}

/* 策略头部 */
.strategy-header {
  margin-bottom: 12px;
}

.strategy-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 6px;
}

.strategy-name {
  font-size: 15px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.strategy-description {
  font-size: 13px;
  line-height: 1.5;
  color: hsl(var(--muted-foreground));
}

/* 匹配详情 */
.match-details {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
}

.match-score {
  flex-shrink: 0;
  width: 70px;
  padding: 8px;
  text-align: center;
  background: hsl(var(--muted));
  border-radius: 8px;
}

.score-label {
  margin-bottom: 4px;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.score-value {
  font-size: 20px;
  font-weight: 700;
}

.score-value.high {
  color: hsl(var(--success));
}

.score-value.medium {
  color: hsl(var(--warning));
}

.score-value.low {
  color: hsl(var(--error));
}

.dimension-list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
}

.dimension-section-title {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 6px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.dimension-tags,
.variable-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.variable-count {
  font-size: 11px;
  opacity: 0.6;
}

/* 策略操作 */
.strategy-action {
  display: flex;
  justify-content: flex-end;
  padding-top: 8px;
  border-top: 1px solid hsl(var(--border) / 50%);
}

/* 空状态 */
.empty-state {
  padding: 40px 0;
}

/* 映射矩阵 */
.mapping-matrix {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mapping-row {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 0;
}

.mapping-arrow {
  color: hsl(var(--muted-foreground));
}

.icon-success {
  color: hsl(var(--success));
}

.icon-warning {
  color: hsl(var(--warning));
}
</style>
