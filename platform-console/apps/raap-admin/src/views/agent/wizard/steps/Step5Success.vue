<script setup lang="ts">
import type { AgentConfig, ExpertConfig } from '../composables/useWizardState';

import { useRouter } from 'vue-router';

import { CheckCircleOutlined, RocketOutlined } from '@ant-design/icons-vue';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Result,
  Row,
  Space,
  Statistic,
  Tag,
} from 'ant-design-vue';

interface Props {
  agentConfig: AgentConfig;
  experts: ExpertConfig[];
}

defineProps<Props>();

const router = useRouter();

// Expert 类型映射
const expertTypeLabels: Record<string, string> = {
  GENERATION: '生文',
  CRITIC: '审核',
  SCORING: '打分',
  ANALYSIS: '分析',
  CUSTOM: '自定义',
};

// 执行任务
function handleExecute() {
  router.push({
    path: '/job/create',
    query: { agent: 'new-agent' }, // TODO: 使用实际创建的 Agent 编码
  });
}

// 返回工作台
function handleBackToWorkbench() {
  router.push('/agent/workbench');
}

// 创建另一个 Agent
function handleCreateAnother() {
  router.push('/agent/workbench');
  // TODO: 可以预填充模板或配置
}
</script>

<template>
  <div class="step-success">
    <Result
      status="success"
      title="Agent 创建成功！"
      sub-title="您现在可以开始使用这个 Agent 执行任务了"
    >
      <template #extra>
        <Space>
          <Button type="primary" size="large" @click="handleExecute">
            <RocketOutlined /> 立即执行任务
          </Button>
          <Button size="large" @click="handleBackToWorkbench">
            返回工作台
          </Button>
        </Space>
      </template>
    </Result>

    <!-- Agent 信息摘要 -->
    <Card class="summary-card" title="Agent 信息">
      <Row :gutter="24">
        <Col :span="16">
          <Descriptions :column="2" bordered>
            <Descriptions.Item label="Agent 名称">
              {{ agentConfig.name }}
            </Descriptions.Item>
            <Descriptions.Item label="Agent 编码">
              {{ agentConfig.code || '自动生成' }}
            </Descriptions.Item>
            <Descriptions.Item label="描述" :span="2">
              {{ agentConfig.description }}
            </Descriptions.Item>
            <Descriptions.Item label="关键词维度">
              {{ agentConfig.keywords?.length || 0 }} 个
            </Descriptions.Item>
            <Descriptions.Item label="策略数量">
              {{ agentConfig.strategies?.length || 0 }} 个
            </Descriptions.Item>
          </Descriptions>
        </Col>
        <Col :span="8">
          <div class="stats">
            <Statistic
              title="包含 Expert"
              :value="experts.length"
              suffix="个"
            />
            <Statistic title="预估组合数" :value="100" suffix="+" />
          </div>
        </Col>
      </Row>
    </Card>

    <!-- Expert 流程预览 -->
    <Card class="flow-card" title="执行流程预览">
      <div class="flow-steps">
        <div
          v-for="(expert, idx) in experts"
          :key="expert.code"
          class="flow-step"
        >
          <div class="step-number">{{ idx + 1 }}</div>
          <div class="step-content">
            <Tag
              :color="
                expert.type === 'GENERATION'
                  ? 'blue'
                  : expert.type === 'CRITIC'
                    ? 'orange'
                    : 'green'
              "
            >
              {{ expertTypeLabels[expert.type] || expert.type }}
            </Tag>
            <span class="step-name">{{ expert.name }}</span>
          </div>
          <div v-if="idx < experts.length - 1" class="step-arrow">→</div>
        </div>
      </div>
    </Card>

    <!-- 下一步提示 -->
    <Alert
      type="info"
      show-icon
      message="接下来您可以"
      class="next-steps-alert"
    >
      <template #description>
        <ul class="next-steps-list">
          <li>立即执行任务，生成第一批内容</li>
          <li>回到工作台，创建更多 Agent</li>
          <li>配置定时任务，实现自动化执行</li>
          <li>查看执行追踪，监控任务进度</li>
        </ul>
      </template>
    </Alert>

    <!-- 快捷操作 -->
    <Card class="actions-card" title="快捷操作">
      <Row :gutter="16">
        <Col :span="6">
          <div class="action-item" @click="handleExecute">
            <RocketOutlined class="action-icon" />
            <div class="action-title">执行任务</div>
            <div class="action-desc">生成内容</div>
          </div>
        </Col>
        <Col :span="6">
          <div class="action-item" @click="handleCreateAnother">
            <CheckCircleOutlined class="action-icon" />
            <div class="action-title">创建 Agent</div>
            <div class="action-desc">新建另一个</div>
          </div>
        </Col>
        <Col :span="6">
          <div class="action-item" @click="() => router.push('/trace/list')">
            <CheckCircleOutlined class="action-icon" />
            <div class="action-title">执行追踪</div>
            <div class="action-desc">查看历史</div>
          </div>
        </Col>
        <Col :span="6">
          <div class="action-item" @click="handleBackToWorkbench">
            <CheckCircleOutlined class="action-icon" />
            <div class="action-title">工作台</div>
            <div class="action-desc">管理 Agent</div>
          </div>
        </Col>
      </Row>
    </Card>
  </div>
</template>

<style scoped>
.step-success {
  padding: 24px 0;
}

.summary-card {
  margin-bottom: 16px;
}

.stats {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  background: #fafafa;
  border-radius: 8px;
}

.flow-card {
  margin-bottom: 16px;
}

.flow-steps {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 16px 0;
  overflow-x: auto;
}

.flow-step {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
}

.step-number {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  background: #1890ff;
  border-radius: 50%;
}

.step-content {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  background: #f0f5ff;
  border-radius: 6px;
}

.step-name {
  font-weight: 500;
}

.step-arrow {
  margin: 0 8px;
  font-size: 18px;
  color: #d9d9d9;
}

.next-steps-alert {
  margin-bottom: 16px;
}

.next-steps-list {
  padding-left: 20px;
  margin: 8px 0 0;
}

.next-steps-list li {
  margin-bottom: 4px;
}

.actions-card {
  background: #fafafa;
}

.action-item {
  padding: 20px;
  text-align: center;
  cursor: pointer;
  background: #fff;
  border-radius: 8px;
  transition: all 0.2s;
}

.action-item:hover {
  box-shadow: 0 4px 12px rgb(0 0 0 / 10%);
  transform: translateY(-2px);
}

.action-icon {
  margin-bottom: 12px;
  font-size: 32px;
  color: #1890ff;
}

.action-title {
  margin-bottom: 4px;
  font-size: 16px;
  font-weight: 600;
}

.action-desc {
  font-size: 13px;
  color: #999;
}
</style>
