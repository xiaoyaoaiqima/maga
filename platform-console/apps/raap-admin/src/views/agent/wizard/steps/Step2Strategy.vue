<script setup lang="ts">
import type {
  KeywordSelection,
  StrategyConfig,
} from '../composables/useWizardState';

import { computed, h, ref, watch } from 'vue';

import { PlusOutlined } from '@ant-design/icons-vue';
import {
  Button,
  Card,
  Col,
  Empty,
  InputNumber,
  message,
  Row,
  Select,
  Space,
  Table,
  Tag,
} from 'ant-design-vue';

import { logger } from '#/utils/logger';

interface Props {
  keywords: KeywordSelection[];
  modelValue: StrategyConfig[];
}

interface Emits {
  (e: 'update:modelValue', value: StrategyConfig[]): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

// 状态
const showStrategySelect = ref(false);
const selectedStrategyId = ref<string>('');
const customCombinationCount = ref(1);

// 已有策略列表
const strategyList = ref<
  Array<{ description?: string; id: string; name: string }>
>([]);

// 加载策略列表
async function loadStrategies() {
  try {
    // TODO: 调用后端 API
    // const data = await getContentStrategiesApi();
    // strategyList.value = data;

    // 模拟数据
    strategyList.value = [
      { id: 's1', name: '全量组合策略', description: '所有维度全量组合' },
      { id: 's2', name: '推荐组合策略', description: '精选优质组合' },
      { id: 's3', name: '随机组合策略', description: '随机生成指定数量组合' },
    ];
  } catch (error) {
    logger.error('加载策略失败:', error);
  }
}

// 组合预览
const combinationPreview = computed(() => {
  if (props.modelValue.length === 0) {
    return { previews: [], total: 0 };
  }

  // 计算总组合数（估算）
  let total = 0;
  props.modelValue.forEach((strategy) => {
    if (strategy.combinations) {
      total += strategy.combinations.length;
    }
  });

  // 生成预览数据
  const previews: Array<{ dimension: string; values: string[] }> = [];

  props.keywords.forEach((kw) => {
    previews.push({
      dimension: kw.dimensionName,
      values: kw.selectedKeywords.slice(0, 5),
    });
  });

  return { previews, total };
});

// 添加现有策略
function addStrategy() {
  if (!selectedStrategyId.value) {
    message.warning('请选择策略');
    return;
  }

  const strategy = strategyList.value.find(
    (s) => s.id === selectedStrategyId.value,
  );
  if (!strategy) return;

  // 检查是否已添加
  if (props.modelValue.some((s) => s.id === strategy.id)) {
    message.warning('该策略已添加');
    return;
  }

  emit('update:modelValue', [
    ...props.modelValue,
    {
      id: strategy.id,
      name: strategy.name,
      combinations: [],
    },
  ]);

  selectedStrategyId.value = '';
  showStrategySelect.value = false;
}

// 添加自定义组合
function addCustomCombination() {
  if (props.keywords.length === 0) {
    message.warning('请先配置关键词');
    return;
  }

  const count = customCombinationCount.value;
  const newCombinations: Array<Record<string, string>> = [];

  for (let i = 0; i < count; i++) {
    const combination: Record<string, string> = {};
    props.keywords.forEach((kw) => {
      const randomKeyword =
        kw.selectedKeywords[
          Math.floor(Math.random() * kw.selectedKeywords.length)
        ];
      combination[kw.dimensionId] = randomKeyword;
    });
    newCombinations.push(combination);
  }

  emit('update:modelValue', [
    ...props.modelValue,
    {
      name: `自定义组合 ${props.modelValue.length + 1}`,
      combinations: newCombinations,
    },
  ]);
}

// 删除策略
function removeStrategy(index: number) {
  const newValue = [...props.modelValue];
  newValue.splice(index, 1);
  emit('update:modelValue', newValue);
}

// 表格列定义
const columns = [
  {
    title: '策略名称',
    dataIndex: 'name',
    key: 'name',
    width: 200,
  },
  {
    title: '组合数',
    dataIndex: 'combinations',
    key: 'combinations',
    width: 100,
    customRender: ({ record }: { record: StrategyConfig }) =>
      h('span', record.combinations?.length || 0),
  },
  {
    title: '操作',
    key: 'action',
    width: 100,
    customRender: ({ index }: { index: number }) =>
      h(
        Button,
        {
          type: 'link',
          danger: true,
          size: 'small',
          onClick: () => removeStrategy(index),
        },
        () => '删除',
      ),
  },
];

// 监听关键词变化，生成默认组合
watch(
  () => props.keywords,
  (newKeywords) => {
    if (newKeywords.length > 0 && props.modelValue.length === 0) {
      // 自动生成一个默认策略
      generateDefaultStrategy();
    }
  },
  { immediate: true },
);

// 生成默认策略（全量组合）
function generateDefaultStrategy() {
  if (props.keywords.length === 0) return;

  // 简化版：只生成前几个组合作为示例
  const combinations: Array<Record<string, string>> = [];

  const firstKeyword = props.keywords[0];
  if (firstKeyword) {
    firstKeyword.selectedKeywords.forEach((kw) => {
      const combo: Record<string, string> = { [firstKeyword.dimensionId]: kw };
      props.keywords.slice(1).forEach((dim) => {
        if (dim.selectedKeywords.length > 0) {
          combo[dim.dimensionId] = dim.selectedKeywords[0];
        }
      });
      combinations.push(combo);
    });
  }

  emit('update:modelValue', [
    {
      name: '默认组合策略',
      combinations,
    },
  ]);
}

// 初始化
loadStrategies();
</script>

<template>
  <div class="step-strategy">
    <Row :gutter="24">
      <!-- 左侧：关键词概览 -->
      <Col :span="8">
        <Card title="已选关键词" class="keywords-overview">
          <div v-if="keywords.length === 0" class="empty-state">
            <Empty
              description="请先配置关键词"
              :image-style="{ height: '60px' }"
            />
          </div>
          <div v-else class="keyword-dims">
            <div
              v-for="kw in keywords"
              :key="kw.dimensionId"
              class="keyword-dim-item"
            >
              <div class="dim-name">{{ kw.dimensionName }}</div>
              <div class="dim-values">
                <Tag v-for="val in kw.selectedKeywords" :key="val">
                  {{ val }}
                </Tag>
                <span v-if="kw.selectedKeywords.length > 5" class="more-tag">
                  +{{ kw.selectedKeywords.length - 5 }}
                </span>
              </div>
            </div>
          </div>

          <!-- 预估组合数 -->
          <div v-if="keywords.length > 0" class="combination-hint">
            <div class="hint-title">预估组合数</div>
            <div class="hint-value">{{ combinationPreview.total }}+</div>
          </div>
        </Card>
      </Col>

      <!-- 右侧：策略配置 -->
      <Col :span="16">
        <Card title="策略配置" class="strategy-config">
          <template #extra>
            <Space>
              <Button
                v-if="!showStrategySelect"
                type="primary"
                size="small"
                @click="showStrategySelect = true"
              >
                <PlusOutlined /> 添加策略
              </Button>
            </Space>
          </template>

          <!-- 添加策略表单 -->
          <div v-if="showStrategySelect" class="add-strategy-form">
            <Space direction="vertical" style="width: 100%">
              <div>
                <div class="form-label">选择现有策略：</div>
                <Select
                  v-model:value="selectedStrategyId"
                  placeholder="选择策略"
                  style="width: 100%"
                  show-search
                  :filter-option="true"
                  :options="
                    strategyList.map((s) => ({
                      label: s.name,
                      value: s.id,
                      description: s.description,
                    }))
                  "
                />
              </div>
              <div>
                <div class="form-label">或 自定义组合数量：</div>
                <InputNumber
                  v-model:value="customCombinationCount"
                  :min="1"
                  :max="1000"
                  style="width: 100%"
                />
              </div>
              <Space>
                <Button type="primary" @click="addStrategy"> 添加策略 </Button>
                <Button @click="addCustomCombination"> 生成自定义组合 </Button>
                <Button @click="showStrategySelect = false"> 取消 </Button>
              </Space>
            </Space>
          </div>

          <!-- 策略列表 -->
          <div v-if="modelValue.length === 0" class="empty-state">
            <Empty description="暂无策略，请添加" />
          </div>

          <Table
            v-else
            :columns="columns"
            :data-source="modelValue"
            :pagination="false"
            size="small"
            class="strategy-table"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'name'">
                <div>
                  <div class="strategy-name">{{ record.name }}</div>
                  <div class="strategy-desc" v-if="record.id">系统策略</div>
                  <div class="strategy-desc" v-else>自定义组合</div>
                </div>
              </template>
            </template>
          </Table>

          <!-- 组合预览 -->
          <div v-if="modelValue.length > 0" class="combination-preview">
            <div class="preview-title">组合示例（前3个）</div>
            <div class="preview-list">
              <div
                v-for="(combo, idx) in modelValue[0].combinations?.slice(0, 3)"
                :key="idx"
                class="preview-item"
              >
                <span
                  v-for="(val, key) in combo"
                  :key="key"
                  class="preview-tag"
                >
                  {{
                    keywords.find((k) => k.dimensionId === key)?.dimensionName
                  }}:
                  {{ val }}
                </span>
              </div>
            </div>
          </div>
        </Card>
      </Col>
    </Row>
  </div>
</template>

<style scoped>
.step-strategy {
  padding: 8px 0;
}

.keywords-overview {
  min-height: 300px;
}

.keyword-dims {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.keyword-dim-item {
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
}

.keyword-dim-item:last-child {
  border-bottom: none;
}

.dim-name {
  margin-bottom: 8px;
  font-weight: 500;
}

.dim-values {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.more-tag {
  padding: 2px 6px;
  font-size: 12px;
  color: #999;
}

.combination-hint {
  padding: 16px;
  margin-top: 20px;
  text-align: center;
  background: #f0f5ff;
  border-radius: 8px;
}

.hint-title {
  margin-bottom: 8px;
  font-size: 13px;
  color: #666;
}

.hint-value {
  font-size: 24px;
  font-weight: 600;
  color: #1890ff;
}

.strategy-config {
  min-height: 400px;
}

.add-strategy-form {
  padding: 16px;
  margin-bottom: 16px;
  background: #f5f5f5;
  border-radius: 8px;
}

.form-label {
  margin-bottom: 8px;
  font-size: 13px;
  color: #666;
}

.strategy-table {
  margin-bottom: 16px;
}

.strategy-name {
  font-weight: 500;
}

.strategy-desc {
  margin-top: 4px;
  font-size: 12px;
  color: #999;
}

.combination-preview {
  padding: 16px;
  background: #fafafa;
  border-radius: 8px;
}

.preview-title {
  margin-bottom: 12px;
  font-size: 13px;
  color: #666;
}

.preview-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.preview-item {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px;
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 4px;
}

.preview-tag {
  padding: 2px 8px;
  font-size: 12px;
  color: #1890ff;
  background: #e6f7ff;
  border-radius: 2px;
}

.empty-state {
  padding: 40px 0;
  text-align: center;
}
</style>
