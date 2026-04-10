<script setup lang="ts">
import type {
  AgentConfig,
  ExpertConfig,
  KeywordSelection,
  StrategyConfig,
} from '../composables/useWizardState';

import { computed } from 'vue';

import { CheckCircleOutlined } from '@ant-design/icons-vue';
import {
  Alert,
  Card,
  Col,
  Descriptions,
  Input,
  Row,
  Space,
  Tag,
  Timeline,
} from 'ant-design-vue';

interface Props {
  keywords: KeywordSelection[];
  strategies: StrategyConfig[];
  experts: ExpertConfig[];
  modelValue: AgentConfig;
}

interface Emits {
  (e: 'update:modelValue', value: AgentConfig): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

// 更新 Agent 名称
function updateName(name: string) {
  emit('update:modelValue', { ...props.modelValue, name });
}

// 更新 Agent 描述
function updateDescription(description: string) {
  emit('update:modelValue', { ...props.modelValue, description });
}

// 配置完整性检查
const completenessCheck = computed(() => {
  const checks = [
    { label: '关键词配置', done: props.keywords.length > 0 },
    { label: '策略配置', done: props.strategies.length > 0 },
    {
      label: '生文专家',
      done: props.experts.some((e) => e.type === 'GENERATION'),
    },
    { label: '审核专家', done: props.experts.some((e) => e.type === 'CRITIC') },
    {
      label: '打分专家',
      done: props.experts.some((e) => e.type === 'SCORING'),
      optional: true,
    },
    { label: 'Agent 名称', done: props.modelValue.name.trim().length > 0 },
    {
      label: 'Agent 描述',
      done: props.modelValue.description.trim().length > 0,
    },
  ];
  return checks;
});

// 完成度
const completenessPercent = computed(() => {
  const required = completenessCheck.value.filter((c) => !c.optional);
  const completed = required.filter((c) => c.done);
  return Math.round((completed.length / required.length) * 100);
});

// Expert 类型映射
const expertTypeLabels: Record<string, string> = {
  GENERATION: '生文',
  CRITIC: '审核',
  SCORING: '打分',
  ANALYSIS: '分析',
  CUSTOM: '自定义',
};

// 专家颜色映射
const expertTypeColors: Record<string, string> = {
  GENERATION: 'blue',
  CRITIC: 'orange',
  SCORING: 'green',
  ANALYSIS: 'purple',
  CUSTOM: 'default',
};
</script>

<template>
  <div class="step-review">
    <Row :gutter="24">
      <!-- 左侧：配置预览 -->
      <Col :span="16">
        <!-- 完整度检查 -->
        <Card class="completeness-card" title="配置完整性">
          <div class="completeness-progress">
            <div class="progress-bar">
              <div
                class="progress-fill"
                :style="{ width: `${completenessPercent}%` }"
              ></div>
            </div>
            <div class="progress-text">完成度: {{ completenessPercent }}%</div>
          </div>

          <Timeline class="check-timeline">
            <Timeline.Item
              v-for="check in completenessCheck"
              :key="check.label"
              :color="check.done ? 'green' : 'gray'"
            >
              <Space>
                <CheckCircleOutlined v-if="check.done" style="color: #52c41a" />
                <span :class="{ done: check.done }">{{ check.label }}</span>
                <Tag v-if="check.optional" color="default">可选</Tag>
              </Space>
            </Timeline.Item>
          </Timeline>
        </Card>

        <!-- 关键词概览 -->
        <Card class="overview-card" title="关键词配置">
          <div v-if="keywords.length === 0" class="empty-hint">未配置</div>
          <div v-else class="keywords-grid">
            <div
              v-for="kw in keywords"
              :key="kw.dimensionId"
              class="keyword-item"
            >
              <div class="keyword-dim">{{ kw.dimensionName }}</div>
              <div class="keyword-values">
                <Tag v-for="val in kw.selectedKeywords.slice(0, 5)" :key="val">
                  {{ val }}
                </Tag>
                <span v-if="kw.selectedKeywords.length > 5" class="more-tag">
                  +{{ kw.selectedKeywords.length - 5 }}
                </span>
              </div>
            </div>
          </div>
        </Card>

        <!-- 策略概览 -->
        <Card class="overview-card" title="策略配置">
          <div v-if="strategies.length === 0" class="empty-hint">未配置</div>
          <Descriptions v-else :column="1" bordered size="small">
            <Descriptions.Item
              v-for="(strategy, idx) in strategies"
              :key="idx"
              :label="strategy.name"
            >
              {{ strategy.combinations?.length || 0 }} 个组合
            </Descriptions.Item>
          </Descriptions>
        </Card>

        <!-- Expert 概览 -->
        <Card class="overview-card" title="Expert 配置">
          <div v-if="experts.length === 0" class="empty-hint">未配置</div>
          <Space v-else wrap>
            <Tag
              v-for="expert in experts"
              :key="expert.code"
              :color="expertTypeColors[expert.type]"
              class="expert-tag"
            >
              [{{ expertTypeLabels[expert.type] || expert.type }}]
              {{ expert.name }}
            </Tag>
          </Space>
        </Card>
      </Col>

      <!-- 右侧：基本信息 -->
      <Col :span="8">
        <Card class="info-card" title="Agent 基本信息">
          <Space direction="vertical" style="width: 100%">
            <div>
              <div class="form-label required">Agent 名称</div>
              <Input
                :value="modelValue.name"
                placeholder="请输入 Agent 名称"
                @update:value="updateName"
              />
              <div v-if="!modelValue.name" class="form-hint">请输入名称</div>
            </div>

            <div>
              <div class="form-label required">Agent 描述</div>
              <Input.TextArea
                :value="modelValue.description"
                placeholder="请描述这个 Agent 的用途"
                :rows="4"
                @update:value="updateDescription"
              />
              <div v-if="!modelValue.description" class="form-hint">
                请输入描述
              </div>
            </div>

            <Alert type="info" message="提示" show-icon>
              Agent 名称将显示在列表中，描述可以帮助其他用户理解这个 Agent
              的用途。
            </Alert>
          </Space>
        </Card>

        <!-- 预估执行量 -->
        <Card class="estimate-card" title="预估执行量">
          <div class="estimate-item">
            <div class="estimate-label">单次执行</div>
            <div class="estimate-value">
              {{
                strategies.reduce(
                  (sum, s) => sum + (s.combinations?.length || 0),
                  0,
                )
              }}
              篇
            </div>
          </div>
          <div class="estimate-item">
            <div class="estimate-label">Expert 调用</div>
            <div class="estimate-value">
              {{
                strategies.reduce(
                  (sum, s) => sum + (s.combinations?.length || 0),
                  0,
                ) * experts.length
              }}
              次
            </div>
          </div>
        </Card>
      </Col>
    </Row>
  </div>
</template>

<style scoped>
.step-review {
  padding: 8px 0;
}

.completeness-card {
  margin-bottom: 16px;
}

.completeness-progress {
  margin-bottom: 16px;
}

.progress-bar {
  height: 8px;
  margin-bottom: 8px;
  overflow: hidden;
  background: #f0f0f0;
  border-radius: 4px;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #1890ff, #52c41a);
  border-radius: 4px;
  transition: width 0.3s;
}

.progress-text {
  font-size: 13px;
  color: #666;
}

.check-timeline {
  margin-top: 16px;
}

.check-timeline .done {
  font-weight: 500;
  color: #52c41a;
}

.overview-card {
  margin-bottom: 16px;
}

.empty-hint {
  padding: 20px 0;
  color: #999;
  text-align: center;
}

.keywords-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.keyword-item {
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
}

.keyword-dim {
  margin-bottom: 8px;
  font-weight: 500;
}

.keyword-values {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.more-tag {
  padding: 2px 6px;
  font-size: 12px;
  color: #999;
}

.info-card {
  margin-bottom: 16px;
}

.form-label {
  margin-bottom: 8px;
  font-size: 13px;
  color: #666;
}

.form-label.required::after {
  color: #ff4d4f;
  content: ' *';
}

.form-hint {
  margin-top: 4px;
  font-size: 12px;
  color: #ff4d4f;
}

.estimate-card {
  background: #f0f5ff;
  border-color: #adc6ff;
}

.estimate-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
}

.estimate-label {
  font-size: 13px;
  color: #666;
}

.estimate-value {
  font-size: 18px;
  font-weight: 600;
  color: #1890ff;
}

.expert-tag {
  padding: 4px 8px;
  font-size: 13px;
  border-radius: 4px;
}
</style>
