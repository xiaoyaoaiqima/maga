<script setup lang="ts">
import type { ExpertConfig } from '../composables/useWizardState';

import { computed, onMounted, ref } from 'vue';

import { PlusOutlined } from '@ant-design/icons-vue';
import {
  Button,
  Card,
  Col,
  message,
  Row,
  Select,
  Space,
  Tag,
} from 'ant-design-vue';

import { logger } from '#/utils/logger';

interface Props {
  modelValue: ExpertConfig[];
}

interface Emits {
  (e: 'update:modelValue', value: ExpertConfig[]): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

// 状态
const loading = ref(false);
const expertOptions = ref<
  Array<{ code: string; description?: string; name: string; type: string }>
>([]);
const showExpertSelect = ref(false);
const selectedExpertType = ref<'CRITIC' | 'GENERATION' | 'SCORING'>();
const selectedExpertCode = ref<string>('');

// Expert 类型定义
const expertTypes = [
  {
    value: 'GENERATION',
    label: '生文专家',
    icon: '📝',
    required: true,
    description: '负责生成内容',
  },
  {
    value: 'CRITIC',
    label: '审核专家',
    icon: '🔍',
    required: true,
    description: '负责审核内容质量',
  },
  {
    value: 'SCORING',
    label: '打分专家',
    icon: '⭐',
    required: false,
    description: '负责对内容打分',
  },
  {
    value: 'ANALYSIS',
    label: '分析专家',
    icon: '📊',
    required: false,
    description: '负责分析内容',
  },
];

// 已添加的 Expert 按类型分组
const expertsByType = computed(() => {
  const grouped: Record<string, ExpertConfig[]> = {};
  props.modelValue.forEach((expert) => {
    if (!grouped[expert.type]) {
      grouped[expert.type] = [];
    }
    grouped[expert.type].push(expert);
  });
  return grouped;
});

// 当前类型可用的 Expert 选项
const availableExperts = computed(() => {
  if (!selectedExpertType.value) return [];
  return expertOptions.value.filter((e) => e.type === selectedExpertType.value);
});

// 是否已添加必需专家
const hasRequiredExperts = computed(() => {
  const hasGeneration = props.modelValue.some((e) => e.type === 'GENERATION');
  const hasCritic = props.modelValue.some((e) => e.type === 'CRITIC');
  return { hasGeneration, hasCritic };
});

// 缺少的必需专家
const missingRequiredExperts = computed(() => {
  const missing = [];
  if (!hasRequiredExperts.value.hasGeneration) {
    missing.push('生文专家');
  }
  if (!hasRequiredExperts.value.hasCritic) {
    missing.push('审核专家');
  }
  return missing;
});

/**
 * 加载 Expert 列表
 */
async function loadExperts() {
  loading.value = true;
  try {
    // TODO: 调用后端 API
    // const data = await getExpertConfigListApi();
    // expertOptions.value = data;

    // 模拟数据
    expertOptions.value = [
      // 生文专家
      {
        code: 'article-gen',
        name: '文章生成专家',
        type: 'GENERATION',
        description: '生成各类文章内容',
      },
      {
        code: 'copy-gen',
        name: '文案生成专家',
        type: 'GENERATION',
        description: '生成营销文案',
      },
      {
        code: 'social-gen',
        name: '社交媒体专家',
        type: 'GENERATION',
        description: '生成社交媒体内容',
      },
      // 审核专家
      {
        code: 'content-critic',
        name: '内容审核专家',
        type: 'CRITIC',
        description: '审核内容质量和合规性',
      },
      {
        code: 'compliance-critic',
        name: '合规审核专家',
        type: 'CRITIC',
        description: '审核内容合规性',
      },
      // 打分专家
      {
        code: 'quality-score',
        name: '质量打分专家',
        type: 'SCORING',
        description: '对内容质量打分',
      },
      {
        code: 'engagement-score',
        name: '互动打分专家',
        type: 'SCORING',
        description: '预测内容互动效果',
      },
      // 分析专家
      {
        code: 'content-analysis',
        name: '内容分析专家',
        type: 'ANALYSIS',
        description: '分析内容特征',
      },
    ];
  } catch (error) {
    logger.error('加载 Expert 列表失败:', error);
  } finally {
    loading.value = false;
  }
}

/**
 * 添加 Expert
 */
function addExpert() {
  if (!selectedExpertType.value) {
    message.warning('请选择专家类型');
    return;
  }
  if (!selectedExpertCode.value) {
    message.warning('请选择专家');
    return;
  }

  const expert = expertOptions.value.find(
    (e) => e.code === selectedExpertCode.value,
  );
  if (!expert) return;

  // 检查是否已添加
  if (props.modelValue.some((e) => e.code === expert.code)) {
    message.warning('该专家已添加');
    return;
  }

  emit('update:modelValue', [
    ...props.modelValue,
    {
      type: expert.type as any,
      code: expert.code,
      name: expert.name,
    },
  ]);

  // 重置选择
  selectedExpertType.value = undefined;
  selectedExpertCode.value = '';
  showExpertSelect.value = false;
}

/**
 * 移除 Expert
 */
function removeExpert(code: string) {
  emit(
    'update:modelValue',
    props.modelValue.filter((e) => e.code !== code),
  );
}

/**
 * 开始添加 Expert
 */
function startAddExpert(type: typeof selectedExpertType.value) {
  selectedExpertType.value = type;
  showExpertSelect.value = true;
}

/**
 * 取消添加
 */
function cancelAdd() {
  selectedExpertType.value = undefined;
  selectedExpertCode.value = '';
  showExpertSelect.value = false;
}

onMounted(() => {
  loadExperts();
});
</script>

<template>
  <div class="step-expert">
    <!-- 必需专家提示 -->
    <Card v-if="missingRequiredExperts.length > 0" class="required-hint">
      <template #title>
        <span class="hint-title">⚠️ 还需要添加以下必需专家：</span>
      </template>
      <Space>
        <Tag v-for="name in missingRequiredExperts" :key="name" color="orange">
          {{ name }}
        </Tag>
      </Space>
    </Card>

    <!-- 专家类型卡片 -->
    <Row :gutter="16" class="expert-types">
      <Col v-for="typeInfo in expertTypes" :key="typeInfo.value" :span="6">
        <Card
          class="expert-type-card"
          :class="[{ required: typeInfo.required }]"
          :hoverable="true"
        >
          <div class="type-icon">{{ typeInfo.icon }}</div>
          <div class="type-info">
            <h3 class="type-name">{{ typeInfo.label }}</h3>
            <p class="type-desc">{{ typeInfo.description }}</p>
            <div v-if="typeInfo.required" class="type-required">必需</div>
          </div>

          <!-- 已添加的专家列表 -->
          <div
            v-if="expertsByType[typeInfo.value]?.length"
            class="added-experts"
          >
            <div
              v-for="expert in expertsByType[typeInfo.value]"
              :key="expert.code"
              class="added-expert-item"
            >
              <Tag closable @close="removeExpert(expert.code)">
                {{ expert.name }}
              </Tag>
            </div>
          </div>

          <Button
            v-else
            size="small"
            @click="startAddExpert(typeInfo.value as any)"
          >
            <PlusOutlined /> 添加
          </Button>
        </Card>
      </Col>
    </Row>

    <!-- 添加专家弹窗（内联） -->
    <Card v-if="showExpertSelect" class="add-expert-card">
      <template #title>
        添加
        {{ expertTypes.find((t) => t.value === selectedExpertType)?.label }}
      </template>
      <template #extra>
        <Button type="text" size="small" @click="cancelAdd">取消</Button>
      </template>

      <Space direction="vertical" style="width: 100%">
        <div>
          <div class="form-label">选择专家：</div>
          <Select
            v-model:value="selectedExpertCode"
            placeholder="请选择专家"
            style="width: 100%"
            show-search
            :filter-option="true"
            :options="
              availableExperts.map((e) => ({
                label: e.name,
                value: e.code,
                description: e.description,
              }))
            "
          >
            <template #option="{ label, description }">
              <div>
                <div>{{ label }}</div>
                <div v-if="description" class="option-desc">
                  {{ description }}
                </div>
              </div>
            </template>
          </Select>
        </div>
        <Button type="primary" @click="addExpert"> 确认添加 </Button>
      </Space>
    </Card>

    <!-- 已添加专家汇总 -->
    <Card v-if="modelValue.length > 0" class="expert-summary">
      <template #title>已添加专家 ({{ modelValue.length }})</template>
      <Space wrap>
        <div
          v-for="expert in modelValue"
          :key="expert.code"
          class="summary-expert-item"
        >
          <span class="expert-type-tag">
            {{ expertTypes.find((t) => t.value === expert.type)?.icon }}
          </span>
          <span class="expert-name">{{ expert.name }}</span>
          <Button
            type="text"
            size="small"
            danger
            @click="removeExpert(expert.code)"
          >
            删除
          </Button>
        </div>
      </Space>
    </Card>
  </div>
</template>

<style scoped>
.step-expert {
  padding: 8px 0;
}

.required-hint {
  margin-bottom: 16px;
  background: #fffbe6;
  border: 1px solid #faad14;
}

.hint-title {
  color: #fa8c16;
}

.expert-types {
  margin-bottom: 16px;
}

.expert-type-card {
  height: 100%;
  text-align: center;
}

.expert-type-card.required {
  border-color: #1890ff;
}

.type-icon {
  margin-bottom: 12px;
  font-size: 36px;
}

.type-name {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
}

.type-desc {
  min-height: 40px;
  margin: 0 0 8px;
  font-size: 13px;
  color: #666;
}

.type-required {
  display: inline-block;
  padding: 2px 8px;
  font-size: 12px;
  color: #ff4d4f;
  background: #fff1f0;
  border-radius: 4px;
}

.added-experts {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: center;
}

.add-expert-card {
  margin-bottom: 16px;
}

.form-label {
  margin-bottom: 8px;
  font-size: 13px;
  color: #666;
}

.option-desc {
  font-size: 12px;
  color: #999;
}

.expert-summary {
  background: #fafafa;
}

.summary-expert-item {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
}

.expert-type-tag {
  font-size: 16px;
}

.expert-name {
  font-weight: 500;
}
</style>
