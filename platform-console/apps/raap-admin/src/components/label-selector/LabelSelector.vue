<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';

import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue';
import { Select, Tag } from 'ant-design-vue';

import { requestClient } from '#/api/request';

// ==================== 类型定义 ====================

export interface LabelValue {
  labels: Record<string, string[]>;
}

interface LabelTypeOption {
  value: string;
  label: string;
}

interface LabelType {
  key: string;
  name: string;
  icon: string;
  color: string;
  multi_select: boolean;
  options: LabelTypeOption[];
}

interface LabelTypesResponse {
  label_types: LabelType[];
}

// ==================== Props ====================

interface Props {
  modelValue: LabelValue;
  tenantCode?: string;
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: () => ({ labels: {} }),
  tenantCode: 'default',
});

const emit = defineEmits<{
  (e: 'update:modelValue', value: LabelValue): void;
}>();

// ==================== 状态 ====================

const labelTypes = ref<LabelType[]>([]);
const loading = ref(false);

// 添加标签的临时状态
const selectedTypeKey = ref<string | undefined>(undefined);
const selectedValues = ref<string[]>([]);

// ==================== 计算属性 ====================

// 已选择的标签（扁平显示）
const selectedLabels = computed(() => {
  const result: Array<{
    color: string;
    icon: string;
    key: string;
    name: string;
    values: string[];
  }> = [];

  for (const [key, values] of Object.entries(props.modelValue.labels || {})) {
    const type = labelTypes.value.find((t) => t.key === key);
    if (type && values.length > 0) {
      result.push({
        key,
        name: type.name,
        icon: type.icon,
        color: type.color,
        values,
      });
    }
  }

  return result;
});

// 当前选中类型的可选值
const currentTypeOptions = computed(() => {
  if (!selectedTypeKey.value) return [];
  const type = labelTypes.value.find((t) => t.key === selectedTypeKey.value);
  return type?.options || [];
});

// 当前选中类型是否支持多选
const currentTypeMulti = computed(() => {
  if (!selectedTypeKey.value) return true;
  const type = labelTypes.value.find((t) => t.key === selectedTypeKey.value);
  return type?.multi_select ?? true;
});

// ==================== 方法 ====================

// 获取标签类型
async function fetchLabelTypes() {
  loading.value = true;
  try {
    const res = await requestClient.get<LabelTypesResponse>(
      '/v1/keyword-corpus/metadata/label-types',
      {
        params: { tenant_code: props.tenantCode },
      },
    );
    labelTypes.value = res?.label_types || [];
  } catch {
    console.error('获取标签类型失败');
    labelTypes.value = [];
  } finally {
    loading.value = false;
  }
}

// 添加标签
function addLabel() {
  if (!selectedTypeKey.value || selectedValues.value.length === 0) {
    return;
  }

  const newLabels = { ...props.modelValue.labels };
  const key = selectedTypeKey.value;

  // 合并已有值和新选值
  const existing = newLabels[key] || [];
  const newValueSet = new Set([...existing, ...selectedValues.value]);
  newLabels[key] = [...newValueSet];

  emit('update:modelValue', { labels: newLabels });

  // 重置选择
  selectedValues.value = [];
}

// 删除某个标签类型的所有值
function removeLabelType(key: string) {
  const newLabels = { ...props.modelValue.labels };
  delete newLabels[key];
  emit('update:modelValue', { labels: newLabels });
}

// 删除某个标签类型的单个值
function removeLabelValue(key: string, value: string) {
  const newLabels = { ...props.modelValue.labels };
  if (newLabels[key]) {
    newLabels[key] = newLabels[key].filter((v) => v !== value);
    if (newLabels[key].length === 0) {
      delete newLabels[key];
    }
  }
  emit('update:modelValue', { labels: newLabels });
}

// 清空全部
function clearAll() {
  emit('update:modelValue', { labels: {} });
}

// 同步 modelValue
watch(
  () => props.modelValue,
  () => {
    // 当外部数据变化时，可以在这里做一些处理
  },
  { deep: true },
);

onMounted(() => {
  fetchLabelTypes();
});

// 暴露方法给父组件
defineExpose({
  refresh: fetchLabelTypes,
});
</script>

<template>
  <div class="label-selector">
    <!-- 添加标签区域 -->
    <div class="add-section">
      <div class="select-row">
        <Select
          v-model:value="selectedTypeKey"
          placeholder="选择标签类型"
          :loading="loading"
          :options="
            labelTypes.map((t) => ({
              label: `${t.icon} ${t.name}`,
              value: t.key,
            }))
          "
          style="width: 180px"
          allow-clear
          show-search
        />

        <Select
          v-model:value="selectedValues"
          placeholder="选择标签值"
          :disabled="!selectedTypeKey"
          :options="currentTypeOptions"
          :mode="currentTypeMulti ? 'multiple' : undefined"
          style="flex: 1; min-width: 200px"
          show-search
          allow-clear
        />

        <button class="add-btn" @click="addLabel">
          <PlusOutlined />
          <span>添加</span>
        </button>
      </div>
    </div>

    <!-- 已选标签区域 -->
    <div v-if="selectedLabels.length > 0" class="selected-section">
      <div class="selected-header">
        <span class="selected-title">已选标签</span>
        <button class="clear-btn" @click="clearAll">清空全部</button>
      </div>

      <div class="selected-list">
        <div
          v-for="item in selectedLabels"
          :key="item.key"
          class="selected-item"
          :style="{ '--color': item.color }"
        >
          <span class="item-icon">{{ item.icon }}</span>
          <span class="item-type">{{ item.name }}:</span>
          <Tag
            v-for="value in item.values"
            :key="value"
            closable
            @close="removeLabelValue(item.key, value)"
          >
            {{ value }}
          </Tag>
          <button
            v-if="item.values.length > 0"
            class="item-remove"
            @click="removeLabelType(item.key)"
          >
            <DeleteOutlined />
          </button>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else class="empty-state">
      <p>暂无标签，请从上方选择添加</p>
    </div>
  </div>
</template>

<style scoped>
.label-selector {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.add-section {
  padding: 12px;
  background: hsl(var(--accent) / 3%);
  border: 1px dashed hsl(var(--border));
  border-radius: 8px;
}

.select-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.add-btn {
  display: flex;
  gap: 4px;
  align-items: center;
  justify-content: center;
  padding: 6px 12px;
  font-size: 13px;
  color: white;
  white-space: nowrap;
  cursor: pointer;
  background: hsl(var(--primary));
  border: none;
  border-radius: 4px;
  transition: opacity 0.2s;
}

.add-btn:hover:not(:disabled) {
  opacity: 0.85;
}

.add-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.selected-section {
  overflow: hidden;
  border: 1px solid hsl(var(--border) / 60%);
  border-radius: 8px;
}

.selected-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: hsl(var(--muted) / 30%);
  border-bottom: 1px solid hsl(var(--border) / 50%);
}

.selected-title {
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.clear-btn {
  padding: 2px 8px;
  font-size: 12px;
  color: hsl(var(--destructive));
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: 4px;
}

.clear-btn:hover {
  background: hsl(var(--destructive) / 10%);
}

.selected-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
}

.selected-item {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 8px;
  background: hsl(var(--card) / 50%);
  border-radius: 6px;
  transition: background 0.2s;
}

.selected-item:hover {
  background: hsl(var(--accent) / 5%);
}

.item-icon {
  font-size: 14px;
}

.item-type {
  font-size: 13px;
  font-weight: 500;
  color: var(--color);
}

.selected-item :deep(.ant-tag) {
  padding: 2px 8px;
  margin: 0;
  font-size: 12px;
  background: hsl(var(--accent) / 10%);
  border-color: var(--color) / 0.3;
  border-radius: 4px;
}

.item-remove {
  padding: 2px 6px;
  margin-left: auto;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: 4px;
}

.item-remove:hover {
  color: hsl(var(--destructive));
  background: hsl(var(--destructive) / 10%);
}

.empty-state {
  padding: 24px;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}
</style>
