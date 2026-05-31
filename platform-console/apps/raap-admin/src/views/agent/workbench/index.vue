<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';

import {
  ApiOutlined,
  ArrowRightOutlined,
  ClusterOutlined,
  KeyOutlined,
  PlusOutlined,
  RobotOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue';
import { Button, Card, Modal, Tabs } from 'ant-design-vue';

import TemplateSelectTab from './tabs/TemplateSelectTab.vue';

const router = useRouter();
const activeTab = ref('template');
const showGuideModal = ref(false);

// Tab 切换事件
function handleTabChange(key: number | string) {
  activeTab.value = String(key);
}

// 快捷入口配置
const quickActions = [
  {
    key: 'keyword',
    title: '系统提示词关键词',
    description: '维护生成链路自动选取的提示词关键词',
    icon: KeyOutlined,
    path: '/content-agent/system-prompt-keywords',
    color: '#1890ff',
  },
  {
    key: 'strategy',
    title: '业务规则',
    description: '管理活动级业务规则包',
    icon: ThunderboltOutlined,
    path: '/business-rules',
    color: '#52c41a',
  },
  {
    key: 'expert',
    title: 'Expert 管理',
    description: '配置生成、审核、打分等 Expert',
    icon: ApiOutlined,
    path: '/expert/calibration',
    color: '#722ed1',
  },
  {
    key: 'agent',
    title: 'Agent 管理',
    description: '组合 Expert 创建完整 Agent',
    icon: RobotOutlined,
    path: '/job/agent',
    color: '#fa8c16',
  },
];

// 跳转到快捷入口
function goToQuickAction(action: (typeof quickActions)[0]) {
  router.push(action.path);
}

// 新建空白 Agent - 显示指导
function handleCreateBlank() {
  showGuideModal.value = true;
}

// 跳转到系统提示词关键词
function goToKeywords() {
  showGuideModal.value = false;
  router.push('/content-agent/system-prompt-keywords');
}

// 跳转到业务规则
function goToStrategy() {
  showGuideModal.value = false;
  router.push('/business-rules');
}

// 跳转到 Agent 模板
function goToTemplates() {
  showGuideModal.value = false;
  activeTab.value = 'template';
}

// 跳转到任务创建
function goToJobCreate() {
  showGuideModal.value = false;
  router.push('/job/create');
}
</script>

<template>
  <div class="agent-workbench">
    <!-- 粘性筛选头部 -->
    <div
      class="sticky top-0 z-10 -mx-4 -mt-4 mb-3 bg-background/90 px-4 pb-4 pt-2 shadow-lg backdrop-blur-md"
      style="border-bottom: 1px solid hsl(var(--border) / 30%)"
    >
      <!-- 标题行 -->
      <div class="mb-2 flex items-center justify-between gap-3">
        <span
          class="bg-gradient-to-r from-[hsl(var(--primary))] to-[#22c55e] bg-clip-text text-xl font-bold text-transparent"
        >
          Agent 工作台
        </span>
        <Button type="primary" @click="handleCreateBlank">
          <PlusOutlined /> 新建空白 Agent
        </Button>
      </div>
    </div>
    <div class="mb-4 text-sm text-muted-foreground">
      创建和管理您的 AI Agent，组合 Expert 完成复杂任务
    </div>

    <!-- 快捷入口卡片 -->
    <div class="quick-actions-section">
      <h3 class="section-title"><ClusterOutlined /> 快捷入口</h3>
      <div class="quick-actions-grid">
        <Card
          v-for="action in quickActions"
          :key="action.key"
          class="quick-action-card"
          hoverable
          @click="goToQuickAction(action)"
        >
          <div class="action-icon" :style="{ color: action.color }">
            <component :is="action.icon" />
          </div>
          <div class="action-content">
            <h4 class="action-title">{{ action.title }}</h4>
            <p class="action-description">{{ action.description }}</p>
          </div>
          <ArrowRightOutlined class="action-arrow" />
        </Card>
      </div>
    </div>

    <!-- 主内容区 -->
    <Card class="content-card">
      <Tabs
        v-model:active-key="activeTab"
        @change="handleTabChange"
        class="workbench-tabs"
      >
        <Tabs.TabPane key="template" tab="从模板创建">
          <TemplateSelectTab />
        </Tabs.TabPane>
      </Tabs>
    </Card>

    <!-- 新建指导弹窗 -->
    <Modal
      v-model:open="showGuideModal"
      title="新建 Agent 操作指南"
      :footer="null"
      width="600"
    >
      <div class="guide-content">
        <p class="guide-intro">创建一个新的 Agent 需要完成以下准备工作：</p>

        <div class="guide-steps">
          <div class="guide-step">
            <div class="step-number">1</div>
            <div class="step-content">
              <h4>准备关键词语料</h4>
              <p>在关键词语料中心，选择你想要的品牌、产品、标签等语料</p>
              <Button type="link" @click="goToKeywords">
                前往关键词语料 <ArrowRightOutlined />
              </Button>
            </div>
          </div>

          <div class="guide-step">
            <div class="step-number">2</div>
            <div class="step-content">
              <h4>配置关键词策略</h4>
              <p>设置内容生成策略，定义人设、风格、变量等</p>
              <Button type="link" @click="goToStrategy">
                前往策略配置 <ArrowRightOutlined />
              </Button>
            </div>
          </div>

          <div class="guide-step">
            <div class="step-number">3</div>
            <div class="step-content">
              <h4>选择 Agent 模板创建</h4>
              <p>从现有 Agent 模板中选择一个，快速创建副本</p>
              <Button type="link" @click="goToTemplates">
                前往模板选择 <ArrowRightOutlined />
              </Button>
            </div>
          </div>

          <div class="guide-step">
            <div class="step-number">4</div>
            <div class="step-content">
              <h4>启动任务</h4>
              <p>配置内容策略，选择 Expert，开始执行生文任务</p>
              <Button type="link" @click="goToJobCreate">
                前往创建任务 <ArrowRightOutlined />
              </Button>
            </div>
          </div>
        </div>

        <div class="guide-footer">
          <Button block @click="showGuideModal = false">
            我知道了，稍后操作
          </Button>
        </div>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
/* 响应式适配 */
@media (max-width: 1200px) {
  .quick-actions-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .quick-actions-grid {
    grid-template-columns: 1fr;
  }
}

.agent-workbench {
  padding: 16px;
}

/* 快捷入口区域 */
.quick-actions-section {
  margin-bottom: 24px;
}

.section-title {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.quick-actions-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.quick-action-card {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 16px;
  cursor: pointer;
  border: 1px solid #f0f0f0;
  transition: all 0.2s;
}

.quick-action-card:hover {
  border-color: #1890ff;
  box-shadow: 0 4px 12px rgb(0 0 0 / 8%);
  transform: translateY(-2px);
}

.action-icon {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  font-size: 20px;
  background: hsl(var(--muted));
  border-radius: 8px;
}

.action-content {
  flex: 1;
  min-width: 0;
}

.action-title {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.action-description {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: #999;
  white-space: nowrap;
}

.action-arrow {
  flex-shrink: 0;
  font-size: 12px;
  color: #bbb;
}

.quick-action-card:hover .action-arrow {
  color: #1890ff;
}

/* 主内容卡片 */
.content-card {
  min-height: 500px;
}

.workbench-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 24px;
}

.workbench-tabs :deep(.ant-tabs-tab) {
  padding: 12px 20px;
  font-size: 15px;
}

/* 指导弹窗样式 */
.guide-content {
  padding: 8px 0;
}

.guide-intro {
  margin: 0 0 20px;
  font-size: 14px;
  color: #666;
}

.guide-steps {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.guide-step {
  display: flex;
  gap: 12px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 8px;
}

.step-number {
  display: flex;
  flex-shrink: 0;
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
  flex: 1;
}

.step-content h4 {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 600;
  color: #333;
}

.step-content p {
  margin: 0 0 8px;
  font-size: 13px;
  color: #666;
}

.step-content :deep(.ant-btn-link) {
  padding: 0;
  font-size: 13px;
}

.guide-footer {
  padding-top: 16px;
  margin-top: 20px;
  border-top: 1px solid #f0f0f0;
}
</style>
