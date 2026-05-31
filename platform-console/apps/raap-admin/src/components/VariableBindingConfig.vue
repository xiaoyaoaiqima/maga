<script setup lang="ts">
/**
 * 变量绑定配置组件
 *
 * 用于 Expert 配置页面，管理变量与关键词树的绑定关系
 *
 * 使用方式：
 * <VariableBindingConfig
 *   :variables="pluginVariables"
 *   v-model:binding="variableBinding"
 * />
 *
 * 数据格式（输出）：
 * {
 *   "写者": {
 *     "source": "keyword_tree",
 *     "bind_label": "小人设",
 *     "selected_node_ids": ["1001003001", "1001003002"],
 *     "strategy": "random"
 *   }
 * }
 */
import { ref, watch } from 'vue';

import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
} from '@ant-design/icons-vue';
import {
  Button,
  Card,
  Empty,
  Select,
  SelectOption,
  Space,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import KeywordTreeSelector from './KeywordTreeSelector.vue';

interface VariableBindingValue {
  source: 'keyword_tree' | 'plugin_context';
  bind_label?: string;
  selected_node_ids?: string[];
  selected_node_names?: string[];
  strategy?: 'all' | 'random' | 'weighted';
  // 旧模式兼容
  context_names?: string[];
}

interface Props {
  // 插件定义的变量列表
  variables: string[];
  // 当前绑定配置
  binding: Record<string, string | string[] | VariableBindingValue>;
  // 租户编码，用于筛选关键词
  tenantCode?: string;
}

const props = defineProps<Props>();

const emit = defineEmits<{
  (e: 'update:binding', value: Record<string, VariableBindingValue>): void;
}>();

// 状态
const selectorVisible = ref(false);
const editingVariable = ref<null | string>(null);
const editingLabel = ref<string>('');
const editingSelectedIds = ref<string[]>([]);

// 内部绑定状态
const internalBinding = ref<Record<string, VariableBindingValue>>({});

// 初始化
watch(
  () => props.binding,
  (val) => {
    if (!val) {
      internalBinding.value = {};
      return;
    }

    // 转换旧格式为新格式
    const converted: Record<string, VariableBindingValue> = {};
    for (const [varName, config] of Object.entries(val)) {
      if (typeof config === 'string') {
        // 旧模式：单个 context_name
        converted[varName] = {
          source: 'plugin_context',
          context_names: [config],
        };
      } else if (Array.isArray(config)) {
        // 旧模式：context_name 数组
        converted[varName] = {
          source: 'plugin_context',
          context_names: config,
        };
      } else if (typeof config === 'object') {
        // 新模式
        converted[varName] = config as VariableBindingValue;
      }
    }
    internalBinding.value = converted;
  },
  { immediate: true, deep: true },
);

// 获取变量的绑定状态
function getBindingStatus(
  varName: string,
): 'keyword_tree' | 'none' | 'plugin_context' {
  const config = internalBinding.value[varName];
  if (!config) return 'none';
  return config.source || 'plugin_context';
}

// 打开选择器编辑变量
function openSelector(varName: string) {
  editingVariable.value = varName;
  const config = internalBinding.value[varName];

  if (config?.source === 'keyword_tree') {
    editingLabel.value = config.bind_label || '';
    editingSelectedIds.value = config.selected_node_ids || [];
  } else {
    editingLabel.value = '';
    editingSelectedIds.value = [];
  }

  selectorVisible.value = true;
}

// 确认选择
function handleSelectorConfirm(data: {
  label: string;
  selectedIds: string[];
  selectedNodes: Array<{ id: string; name: string }>;
}) {
  if (!editingVariable.value) return;

  internalBinding.value[editingVariable.value] = {
    source: 'keyword_tree',
    bind_label: data.label,
    selected_node_ids: data.selectedIds,
    selected_node_names: data.selectedNodes.map((n) => n.name),
    strategy: 'random',
  };

  emit('update:binding', internalBinding.value);
  editingVariable.value = null;
}

// 清除绑定
function clearBinding(varName: string) {
  delete internalBinding.value[varName];
  emit('update:binding', { ...internalBinding.value });
}

// 更新策略
function updateStrategy(
  varName: string,
  strategy: 'all' | 'random' | 'weighted',
) {
  const config = internalBinding.value[varName];
  if (config) {
    config.strategy = strategy;
    emit('update:binding', { ...internalBinding.value });
  }
}

// 获取已选节点名称列表
function getSelectedNodeNames(varName: string): string[] {
  const config = internalBinding.value[varName];
  if (config?.source === 'keyword_tree') {
    return config.selected_node_names || [];
  }
  return [];
}
</script>

<template>
  <div class="variable-binding-config">
    <div v-if="variables.length === 0" class="empty-state">
      <Empty description="当前 Expert 没有配置变量" />
    </div>

    <div v-else class="variable-list">
      <Card
        v-for="varName in variables"
        :key="varName"
        size="small"
        class="variable-card"
      >
        <template #title>
          <div class="card-header">
            <span class="variable-name">{{ varName }}</span>
            <Tag
              :color="
                getBindingStatus(varName) === 'keyword_tree'
                  ? 'green'
                  : getBindingStatus(varName) === 'plugin_context'
                    ? 'blue'
                    : 'default'
              "
            >
              {{
                getBindingStatus(varName) === 'keyword_tree'
                  ? '关键词树'
                  : getBindingStatus(varName) === 'plugin_context'
                    ? '旧模式'
                    : '未绑定'
              }}
            </Tag>
          </div>
        </template>

        <template #extra>
          <Space>
            <Button size="small" type="link" @click="openSelector(varName)">
              <template #icon><EditOutlined /></template>
              {{ getBindingStatus(varName) === 'none' ? '配置' : '编辑' }}
            </Button>
            <Button
              v-if="getBindingStatus(varName) !== 'none'"
              size="small"
              type="link"
              danger
              @click="clearBinding(varName)"
            >
              <template #icon><DeleteOutlined /></template>
              清除
            </Button>
          </Space>
        </template>

        <div class="binding-content">
          <template v-if="getBindingStatus(varName) === 'none'">
            <div class="empty-binding">
              <Button type="dashed" @click="openSelector(varName)">
                <template #icon><PlusOutlined /></template>
                绑定关键词
              </Button>
            </div>
          </template>

          <template v-else-if="getBindingStatus(varName) === 'keyword_tree'">
            <div class="binding-info">
              <div class="info-row">
                <span class="label">绑定类型：</span>
                <span class="value">{{
                  internalBinding[varName]?.bind_label
                }}</span>
              </div>
              <div class="info-row">
                <span class="label">采集策略：</span>
                <Select
                  :value="internalBinding[varName]?.strategy || 'random'"
                  size="small"
                  style="width: 100px"
                  @change="
                    (val) =>
                      updateStrategy(
                        varName,
                        String(val || 'random') as 'all' | 'random' | 'weighted',
                      )
                  "
                >
                  <SelectOption value="random">随机</SelectOption>
                  <SelectOption value="weighted">权重</SelectOption>
                  <SelectOption value="all">全部</SelectOption>
                </Select>
              </div>
              <div class="info-row nodes">
                <span class="label">已选节点：</span>
                <div class="node-tags">
                  <Tooltip
                    v-for="name in getSelectedNodeNames(varName).slice(0, 5)"
                    :key="name"
                    :title="name"
                  >
                    <Tag>
                      {{ name.length > 10 ? `${name.slice(0, 10)}...` : name }}
                    </Tag>
                  </Tooltip>
                  <Tag
                    v-if="getSelectedNodeNames(varName).length > 5"
                    color="blue"
                  >
                    +{{ getSelectedNodeNames(varName).length - 5 }} 更多
                  </Tag>
                </div>
              </div>
            </div>
          </template>

          <template v-else>
            <div class="legacy-mode">
              <Tag color="orange">使用旧版 PluginContext 模式</Tag>
              <div class="hint">建议迁移到关键词树模式</div>
            </div>
          </template>
        </div>
      </Card>
    </div>

    <!-- 关键词选择器弹窗 -->
    <KeywordTreeSelector
      v-model:visible="selectorVisible"
      :label="editingLabel"
      :selected-ids="editingSelectedIds"
      :tenant-code="tenantCode"
      @confirm="handleSelectorConfirm"
    />
  </div>
</template>

<style scoped>
.variable-binding-config {
  padding: 8px 0;
}

.empty-state {
  padding: 40px 0;
}

.variable-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.variable-card {
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.card-header {
  display: flex;
  gap: 8px;
  align-items: center;
}

.variable-name {
  font-weight: 600;
  color: hsl(var(--foreground));
}

.binding-content {
  min-height: 60px;
}

.empty-binding {
  display: flex;
  justify-content: center;
  padding: 16px 0;
}

.binding-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.info-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.info-row .label {
  flex-shrink: 0;
  min-width: 80px;
  color: hsl(var(--muted-foreground));
}

.info-row .value {
  color: hsl(var(--foreground));
}

.info-row.nodes {
  flex-wrap: wrap;
}

.node-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.legacy-mode {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  padding: 16px 0;
}

.legacy-mode .hint {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}
</style>
