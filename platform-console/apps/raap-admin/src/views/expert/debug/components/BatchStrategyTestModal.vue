<script setup lang="ts">
// @ts-nocheck
import type { ContentStrategyApi } from '#/api/core/content-strategy';

/**
 * 批量策略测试弹窗 - 使用关键词策略批量生成并测试
 */
import { computed, ref, watch } from 'vue';

import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Divider,
  Form,
  InputNumber,
  message,
  Modal,
  Progress,
  Row,
  Select,
  SelectOption,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
} from 'ant-design-vue';

import {
  generateCombinationsApi,
  getContentStrategiesApi,
} from '#/api/core/content-strategy';
import { debugExpertApi } from '#/api/core/expert-debug';

interface ExpertVariable {
  plugin_code: string;
  variable_name: string;
  options: Array<{ context_name: string; node_id?: string }>;
}

interface Props {
  open: boolean;
  expertCode: string;
  expertVariables: ExpertVariable[];
  expertPluginConfig: Array<{
    plugin_code: string;
    variable_mapping?: Record<string, { context_name?: string }>;
  }>;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  'update:open': [value: boolean];
}>();

const { Item: FormItem } = Form as any;
const { Panel: CollapsePanel } = Collapse;

// 状态
const loading = ref(false);
const strategyList = ref<ContentStrategyApi.ContentStrategy[]>([]);
const selectedStrategyId = ref<null | string>(null);
const variableMapping = ref<Record<string, string>>({});
const comboCount = ref(5);
const concurrency = ref(3);

const combinations = ref<ContentStrategyApi.CombinationItem[]>([]);
const generatingCombos = ref(false);

const executing = ref(false);
const executionProgress = ref(0);
const executionResults = ref<
  Array<{
    combo: ContentStrategyApi.CombinationItem;
    error?: string;
    execution_time?: number;
    index: number;
    output?: string;
    success: boolean;
    token_usage?: {
      input_tokens?: number;
      output_tokens?: number;
      total_tokens?: number;
    };
  }>
>([]);

// 计算属性
const modalOpen = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val),
});

const selectedStrategy = computed(() => {
  if (!selectedStrategyId.value) return null;
  return strategyList.value.find((s) => s.id === selectedStrategyId.value);
});

const strategyDimensions = computed(() => {
  // 从 node_pools 或 defined_combinations 提取维度
  const strategy = selectedStrategy.value;
  if (!strategy) return [];

  // 优先从 node_pools 获取
  if (strategy.node_pools) {
    return Object.keys(strategy.node_pools).map((dimType) => ({
      dimension_type: dimType,
      dimension_name: dimType, // 回退使用 dimension_type
    }));
  }

  // 从 defined_combinations 提取
  if (
    strategy.defined_combinations &&
    strategy.defined_combinations.length > 0
  ) {
    const firstCombo = strategy.defined_combinations[0];
    if (firstCombo?.nodes) {
      return Object.keys(firstCombo.nodes).map((dimType) => ({
        dimension_type: dimType,
        dimension_name: dimType,
      }));
    }
  }

  return [];
});

const availableVariables = computed(() => {
  const vars: Array<{ plugin_code: string; variable_name: string }> = [];
  const seen = new Set<string>();

  for (const plugin of props.expertVariables) {
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

const executionSummary = computed(() => {
  if (executionResults.value.length === 0) return null;

  const total = executionResults.value.length;
  const success = executionResults.value.filter((r) => r.success).length;
  const failed = total - success;
  const avgTime =
    executionResults.value
      .filter((r) => r.execution_time)
      .reduce((sum, r) => sum + (r.execution_time || 0), 0) / (success || 1);

  const totalTokens = executionResults.value.reduce(
    (sum, r) => sum + (r.token_usage?.total_tokens || 0),
    0,
  );

  return {
    total,
    success,
    failed,
    avgTime: Math.round(avgTime),
    totalTokens,
  };
});

const resultColumns = [
  {
    title: '#',
    dataIndex: 'index',
    key: 'index',
    width: 50,
  },
  {
    title: '组合',
    key: 'combo',
    width: 200,
  },
  {
    title: '状态',
    key: 'status',
    width: 80,
  },
  {
    title: '耗时',
    dataIndex: 'execution_time',
    key: 'execution_time',
    width: 80,
  },
  {
    title: 'Tokens',
    key: 'tokens',
    width: 100,
  },
  {
    title: '输出预览',
    key: 'output',
    ellipsis: true,
  },
];

// 方法
async function loadStrategies() {
  loading.value = true;
  try {
    const res = await getContentStrategiesApi({
      is_active: 1,
      page_size: 100,
    });
    strategyList.value = res.items || [];
  } catch (error) {
    console.error('获取策略列表失败:', error);
    message.error('获取策略列表失败');
  } finally {
    loading.value = false;
  }
}

function onStrategyChange(strategyId: string) {
  selectedStrategyId.value = strategyId;
  variableMapping.value = {};
  combinations.value = [];
  executionResults.value = [];

  // 自动匹配同名变量
  const strategy = strategyList.value.find((s) => s.id === strategyId);
  if (strategy) {
    // 从 node_pools 或 defined_combinations 提取维度
    const dimensions = strategyDimensions.value;

    for (const dim of dimensions) {
      const matchingVar = availableVariables.value.find(
        (v) =>
          v.variable_name === dim.dimension_name ||
          v.variable_name === dim.dimension_type,
      );
      if (matchingVar) {
        variableMapping.value[dim.dimension_type] = matchingVar.variable_name;
      }
    }
  }
}

async function generateCombinations() {
  if (!selectedStrategyId.value) {
    message.warning('请先选择策略');
    return;
  }

  generatingCombos.value = true;
  try {
    const res = await generateCombinationsApi(selectedStrategyId.value, {
      count: comboCount.value,
    });
    combinations.value = res.combinations || [];
    executionResults.value = [];
    message.success(`生成了 ${combinations.value.length} 个组合`);
  } catch (error) {
    console.error('生成组合失败:', error);
    message.error('生成组合失败');
  } finally {
    generatingCombos.value = false;
  }
}

function comboToSnapshot(
  combo: ContentStrategyApi.CombinationItem,
): Array<{ plugin_code: string; variable_mapping: Record<string, string> }> {
  const pluginMappings: Record<string, Record<string, string>> = {};

  for (const [dimensionType, variableName] of Object.entries(
    variableMapping.value,
  )) {
    if (!variableName) continue;

    const node = combo.nodes[dimensionType];
    if (!node) continue;

    for (const plugin of props.expertVariables) {
      if (plugin.variable_name === variableName) {
        if (!pluginMappings[plugin.plugin_code]) {
          pluginMappings[plugin.plugin_code] = {};
        }
        pluginMappings[plugin.plugin_code]![variableName] = `node:${node.id}`;
        break;
      }
    }
  }

  return Object.entries(pluginMappings).map(([plugin_code, mapping]) => ({
    plugin_code,
    variable_mapping: mapping,
  }));
}

async function executeTests() {
  if (combinations.value.length === 0) {
    message.warning('请先生成组合');
    return;
  }

  executing.value = true;
  executionProgress.value = 0;
  executionResults.value = [];

  const total = combinations.value.length;
  const batchSize = concurrency.value;

  // 分批执行
  for (let i = 0; i < total; i += batchSize) {
    const batch = combinations.value.slice(i, i + batchSize);
    const batchPromises = batch.map(async (combo, batchIdx) => {
      const index = i + batchIdx;
      const snapshot = comboToSnapshot(combo);

      try {
        const result = await debugExpertApi({
          expert_config_code: props.expertCode,
          content: '', // 生成类 Expert 不需要
          plugin_config_snapshot: snapshot,
        });

        return {
          index,
          combo,
          success: result.success,
          output: result.output_content || '',
          execution_time: result.execution_time_ms,
          token_usage: result.token_usage,
        };
      } catch (error: unknown) {
        const errMsg = error instanceof Error ? error.message : String(error);
        return {
          index,
          combo,
          success: false,
          error: errMsg,
        };
      }
    });

    const batchResults = await Promise.all(batchPromises);
    executionResults.value.push(...batchResults);
    executionProgress.value = Math.round(
      (executionResults.value.length / total) * 100,
    );
  }

  executing.value = false;
  message.success('批量测试完成');
}

function handleClose() {
  emit('update:open', false);
}

function getComboSummary(combo: ContentStrategyApi.CombinationItem): string {
  return Object.entries(combo.nodes)
    .map(([dim, node]) => `${node.label || dim}: ${node.name}`)
    .join(' | ');
}

// 监听打开
watch(
  () => props.open,
  (newVal) => {
    if (newVal && strategyList.value.length === 0) {
      loadStrategies();
    }
  },
);
</script>

<template>
  <Modal
    v-model:open="modalOpen"
    title="🔬 批量策略测试"
    :width="1100"
    :footer="null"
    @cancel="handleClose"
  >
    <Spin :spinning="loading">
      <div class="batch-strategy-content">
        <!-- 配置区 -->
        <Card size="small" title="📋 策略配置" class="mb-4">
          <Form layout="inline" class="config-form">
            <FormItem label="选择策略">
              <Select
                v-model:value="selectedStrategyId"
                placeholder="选择关键词策略"
                style="width: 200px"
                show-search
                option-filter-prop="label"
                :get-popup-container="(trigger) => trigger.parentElement"
                @change="onStrategyChange"
              >
                <SelectOption
                  v-for="s in strategyList"
                  :key="s.id"
                  :value="s.id"
                  :label="s.name"
                >
                  {{ s.name }}
                </SelectOption>
              </Select>
            </FormItem>

            <FormItem label="组合数量">
              <InputNumber
                v-model:value="comboCount"
                :min="1"
                :max="50"
                style="width: 100px"
              />
            </FormItem>

            <FormItem label="并发数">
              <InputNumber
                v-model:value="concurrency"
                :min="1"
                :max="10"
                style="width: 100px"
              />
            </FormItem>

            <FormItem>
              <Button
                type="primary"
                :loading="generatingCombos"
                :disabled="!selectedStrategyId"
                @click="generateCombinations"
              >
                生成组合
              </Button>
            </FormItem>
          </Form>
        </Card>

        <!-- 变量映射 -->
        <Collapse
          v-if="selectedStrategy"
          :default-active-key="['mapping']"
          class="mb-4"
        >
          <CollapsePanel key="mapping" header="🔗 变量映射配置">
            <Alert
              message="将策略维度映射到 Expert 变量，测试时会使用组合中的节点值"
              type="info"
              show-icon
              class="mb-3"
            />

            <Row :gutter="16">
              <Col
                v-for="dim in strategyDimensions"
                :key="dim.dimension_type"
                :span="8"
              >
                <div class="mapping-item">
                  <div class="dimension-label">
                    <Tag color="purple">{{ dim.dimension_name }}</Tag>
                  </div>
                  <Select
                    :value="variableMapping[dim.dimension_type]"
                    placeholder="映射到..."
                    style="width: 100%"
                    allow-clear
                    :get-popup-container="(trigger) => trigger.parentElement"
                    @change="
                      (v: string) => (variableMapping[dim.dimension_type] = v)
                    "
                  >
                    <SelectOption
                      v-for="v in availableVariables"
                      :key="`${v.plugin_code}:${v.variable_name}`"
                      :value="v.variable_name"
                    >
                      {{ v.variable_name }}
                    </SelectOption>
                  </Select>
                </div>
              </Col>
            </Row>
          </CollapsePanel>
        </Collapse>

        <!-- 组合预览和执行 -->
        <Card
          v-if="combinations.length > 0"
          size="small"
          title="🎯 测试组合"
          class="mb-4"
        >
          <template #extra>
            <Space>
              <Tag color="blue">{{ combinations.length }} 个组合</Tag>
              <Button type="primary" :loading="executing" @click="executeTests">
                {{ executing ? '测试中...' : '开始测试' }}
              </Button>
            </Space>
          </template>

          <div v-if="executing" class="progress-section">
            <Progress
              :percent="executionProgress"
              :status="executionProgress < 100 ? 'active' : 'success'"
            />
          </div>

          <div class="combo-preview-list">
            <Tag
              v-for="(combo, idx) in combinations.slice(0, 10)"
              :key="idx"
              class="combo-tag"
            >
              #{{ idx + 1 }}: {{ getComboSummary(combo) }}
            </Tag>
            <span v-if="combinations.length > 10" class="text-muted-foreground">
              ... 还有 {{ combinations.length - 10 }} 个
            </span>
          </div>
        </Card>

        <!-- 执行结果 -->
        <Card
          v-if="executionResults.length > 0"
          size="small"
          title="📊 执行结果"
        >
          <!-- 摘要统计 -->
          <div v-if="executionSummary" class="summary-section mb-4">
            <Row :gutter="16">
              <Col :span="4">
                <Statistic title="总执行" :value="executionSummary.total" />
              </Col>
              <Col :span="4">
                <Statistic
                  title="成功"
                  :value="executionSummary.success"
                  :value-style="{ color: '#52c41a' }"
                />
              </Col>
              <Col :span="4">
                <Statistic
                  title="失败"
                  :value="executionSummary.failed"
                  :value-style="{
                    color: executionSummary.failed > 0 ? '#ff4d4f' : undefined,
                  }"
                />
              </Col>
              <Col :span="6">
                <Statistic
                  title="平均耗时"
                  :value="executionSummary.avgTime"
                  suffix="ms"
                />
              </Col>
              <Col :span="6">
                <Statistic
                  title="总 Tokens"
                  :value="executionSummary.totalTokens"
                />
              </Col>
            </Row>
          </div>

          <Divider />

          <!-- 详细结果表格 -->
          <Table
            :columns="resultColumns"
            :data-source="executionResults"
            :pagination="{ pageSize: 10 }"
            row-key="index"
            size="small"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'combo'">
                <span class="combo-cell">{{
                  getComboSummary(record.combo)
                }}</span>
              </template>
              <template v-else-if="column.key === 'status'">
                <Tag :color="record.success ? 'green' : 'red'">
                  {{ record.success ? '成功' : '失败' }}
                </Tag>
              </template>
              <template v-else-if="column.key === 'execution_time'">
                <span v-if="record.execution_time">
                  {{ record.execution_time }}ms
                </span>
                <span v-else class="text-muted-foreground">-</span>
              </template>
              <template v-else-if="column.key === 'tokens'">
                <span v-if="record.token_usage?.total_tokens">
                  {{ record.token_usage.total_tokens }}
                </span>
                <span v-else class="text-muted-foreground">-</span>
              </template>
              <template v-else-if="column.key === 'output'">
                <span v-if="record.output" class="output-preview">
                  {{ record.output.slice(0, 100) }}...
                </span>
                <span v-else-if="record.error" class="error-text">
                  {{ record.error }}
                </span>
                <span v-else class="text-muted-foreground">-</span>
              </template>
            </template>
          </Table>
        </Card>
      </div>
    </Spin>
  </Modal>
</template>

<style scoped>
.batch-strategy-content {
  display: flex;
  flex-direction: column;
}

.mb-3 {
  margin-bottom: 12px;
}

.mb-4 {
  margin-bottom: 16px;
}

.config-form {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.mapping-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.dimension-label {
  font-size: 13px;
}

.progress-section {
  padding: 12px 0;
}

.combo-preview-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.combo-tag {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-section {
  padding: 16px;
  background: hsl(var(--muted) / 30%);
  border-radius: 8px;
}

.combo-cell {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  white-space: nowrap;
}

.output-preview {
  max-width: 250px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  white-space: nowrap;
}

.error-text {
  font-size: 12px;
  color: hsl(var(--destructive));
}
</style>
