<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';

import {
  CloseOutlined,
  LeftOutlined,
  RightOutlined,
  SaveOutlined,
} from '@ant-design/icons-vue';
import {
  Button,
  Drawer,
  message,
  Modal,
  Progress,
  Space,
} from 'ant-design-vue';

import { useWizardState } from './composables';
import {
  Step1Keywords,
  Step2Strategy,
  Step3Expert,
  Step4Review,
  Step5Success,
} from './steps';

// Composables
const {
  currentStep,
  agentConfig,
  stepStatus,
  saving,
  totalSteps,
  stepTitle,
  canNext,
  progressPercent,
  initWizard,
  nextStep,
  prevStep,
  goToStep,
  saveDraft,
  submitAgent,
  onCancel: navigateAway,
} = useWizardState();

// Drawer 可见性控制
const drawerVisible = ref(true);
const showExitConfirm = ref(false);

// 本地状态（用于各步骤的独立配置）
const keywordsConfig = computed({
  get: () => agentConfig.value.keywords,
  set: (val) => {
    agentConfig.value.keywords = val;
  },
});

const strategiesConfig = computed({
  get: () => agentConfig.value.strategies,
  set: (val) => {
    agentConfig.value.strategies = val;
  },
});

const expertsConfig = computed({
  get: () => agentConfig.value.experts,
  set: (val) => {
    agentConfig.value.experts = val;
  },
});

// 检查是否有未保存的内容
function hasUnsavedChanges(): boolean {
  return (
    agentConfig.value.keywords.length > 0 ||
    agentConfig.value.strategies.length > 0 ||
    agentConfig.value.experts.length > 0 ||
    agentConfig.value.name.trim().length > 0 ||
    agentConfig.value.description.trim().length > 0
  );
}

// 处理退出确认
function handleExitConfirm() {
  showExitConfirm.value = true;
}

// 直接退出（不保存）
function exitWithoutSave() {
  showExitConfirm.value = false;
  drawerVisible.value = false;
  // 延迟跳转，等待 Drawer 关闭动画
  setTimeout(() => {
    navigateAway();
  }, 300);
}

// 保存草稿后退出
async function saveAndExit() {
  showExitConfirm.value = false;
  try {
    await saveDraft();
    message.success('草稿已保存');
    drawerVisible.value = false;
    setTimeout(() => {
      navigateAway();
    }, 300);
  } catch {
    message.error('保存草稿失败');
  }
}

// 取消退出确认
function cancelExit() {
  showExitConfirm.value = false;
}

// 统一的取消处理（带确认）
function handleCancel() {
  if (hasUnsavedChanges()) {
    handleExitConfirm();
  } else {
    exitWithoutSave();
  }
}

// 保存草稿
async function handleSaveDraft() {
  try {
    await saveDraft();
    message.success('草稿已保存');
  } catch {
    message.error('保存草稿失败');
  }
}

// 提交创建
async function handleSubmit() {
  try {
    await submitAgent();
    // 创建成功，进入完成步骤
    nextStep();
    // 完成步骤显示 2 秒后关闭并跳转
    setTimeout(() => {
      drawerVisible.value = false;
      setTimeout(() => {
        navigateAway();
      }, 300);
    }, 2000);
  } catch {
    message.error('创建 Agent 失败');
  }
}

// 下一步
function handleNext() {
  if (canNext.value) {
    if (currentStep.value === 4) {
      handleSubmit();
    } else {
      nextStep();
    }
  }
}

// 初始化
onMounted(() => {
  initWizard();
});

// 监听步骤变化，更新步骤状态
watch(currentStep, (newStep) => {
  // 解锁当前步骤
  if (stepStatus.value[newStep]) {
    stepStatus.value[newStep].editable = true;
  }
});
</script>

<template>
  <div class="agent-wizard">
    <Drawer
      :open="drawerVisible"
      :closable="true"
      :mask-closable="true"
      width="1200"
      placement="right"
      class="wizard-drawer"
      @close="handleCancel"
    >
      <!-- 头部 -->
      <template #title>
        <div class="wizard-header">
          <div class="header-title">创建 Agent</div>
          <div class="header-subtitle">{{ stepTitle }}</div>
        </div>
      </template>

      <!-- 关闭按钮 -->
      <template #extra>
        <Space>
          <Button v-if="currentStep < 5" type="text" @click="handleSaveDraft">
            <SaveOutlined /> 保存草稿
          </Button>
          <Button type="text" @click="handleCancel">
            <CloseOutlined />
          </Button>
        </Space>
      </template>

      <!-- 进度条 -->
      <div v-if="currentStep < 5" class="wizard-progress">
        <div class="progress-info">
          <span>步骤 {{ currentStep }} / {{ totalSteps - 1 }}</span>
          <span class="progress-percent"
            >{{ Math.round(progressPercent) }}%</span
          >
        </div>
        <Progress
          :percent="progressPercent"
          :show-info="false"
          :stroke-color="{
            '0%': '#108ee9',
            '100%': '#87d068',
          }"
        />
        <div class="step-dots">
          <div
            v-for="step in totalSteps - 1"
            :key="step"
            class="step-dot"
            :class="[
              {
                active: step === currentStep,
                completed: step < currentStep,
                clickable:
                  stepStatus[step]?.editable || stepStatus[step]?.completed,
              },
            ]"
            @click="goToStep(step as any)"
          >
            {{ step }}
          </div>
        </div>
      </div>

      <!-- 步骤内容 -->
      <div class="wizard-content">
        <!-- 步骤 1: 关键词配置 -->
        <Step1Keywords v-if="currentStep === 1" v-model="keywordsConfig" />

        <!-- 步骤 2: 策略组合 -->
        <Step2Strategy
          v-if="currentStep === 2"
          :keywords="keywordsConfig"
          v-model="strategiesConfig"
        />

        <!-- 步骤 3: Expert 配置 -->
        <Step3Expert v-if="currentStep === 3" v-model="expertsConfig" />

        <!-- 步骤 4: 组装预览 -->
        <Step4Review
          v-if="currentStep === 4"
          :keywords="keywordsConfig"
          :strategies="strategiesConfig"
          :experts="expertsConfig"
          v-model="agentConfig"
        />

        <!-- 步骤 5: 完成 -->
        <Step5Success
          v-if="currentStep === 5"
          :agent-config="agentConfig"
          :experts="expertsConfig"
        />
      </div>

      <!-- 底部操作栏 -->
      <template v-if="currentStep < 5" #footer>
        <div class="wizard-footer">
          <Space>
            <Button v-if="currentStep > 1" @click="prevStep">
              <LeftOutlined /> 上一步
            </Button>
            <Button
              v-if="currentStep < 4"
              type="primary"
              :disabled="!canNext"
              @click="handleNext"
            >
              下一步 <RightOutlined />
            </Button>
            <Button
              v-if="currentStep === 4"
              type="primary"
              :disabled="!canNext"
              :loading="saving"
              @click="handleSubmit"
            >
              创建 Agent
            </Button>
          </Space>

          <!-- 提示信息 -->
          <div class="footer-hint">
            <span v-if="!canNext && currentStep === 1" class="hint-error">
              请至少选择一个维度的关键词
            </span>
            <span v-else-if="!canNext && currentStep === 2" class="hint-error">
              请至少添加一个策略组合
            </span>
            <span v-else-if="!canNext && currentStep === 3" class="hint-error">
              需要至少配置生文专家和审核专家
            </span>
            <span v-else-if="!canNext && currentStep === 4" class="hint-error">
              请填写 Agent 名称和描述
            </span>
          </div>
        </div>
      </template>
    </Drawer>

    <!-- 退出确认对话框 -->
    <Modal
      v-model:open="showExitConfirm"
      title="确认退出"
      ok-text="保存草稿并退出"
      cancel-text="不保存直接退出"
      @ok="saveAndExit"
      @cancel="exitWithoutSave"
    >
      <p>您有未保存的内容，是否保存为草稿？</p>
      <p class="exit-hint">
        • 保存草稿：稍后可继续编辑<br />
        • 不保存：当前配置将丢失
      </p>
      <template #footer>
        <Button @click="cancelExit">取消</Button>
        <Button danger @click="exitWithoutSave">不保存直接退出</Button>
        <Button type="primary" @click="saveAndExit">保存草稿并退出</Button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.agent-wizard {
  position: fixed;
  inset: 0;
  z-index: 1000;
}

:deep(.wizard-drawer) {
  position: relative;
}

:deep(.wizard-drawer .ant-drawer-body) {
  padding: 0;
}

.wizard-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
}

.header-subtitle {
  font-size: 13px;
  color: #999;
}

.wizard-progress {
  padding: 16px 24px;
  border-bottom: 1px solid #f0f0f0;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
}

.progress-percent {
  font-weight: 600;
  color: #1890ff;
}

.step-dots {
  display: flex;
  gap: 8px;
  justify-content: center;
  margin-top: 12px;
}

.step-dot {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  font-size: 13px;
  color: #999;
  cursor: default;
  background: #f0f0f0;
  border-radius: 50%;
}

.step-dot.clickable {
  cursor: pointer;
}

.step-dot.clickable:hover {
  background: #e6f7ff;
}

.step-dot.active {
  color: #fff;
  background: #1890ff;
}

.step-dot.completed {
  color: #fff;
  background: #52c41a;
}

.wizard-content {
  min-height: calc(100vh - 250px);
  padding: 24px;
}

.wizard-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.footer-hint {
  font-size: 13px;
}

.hint-error {
  color: #ff4d4f;
}

.exit-hint {
  padding: 12px;
  margin-top: 12px;
  font-size: 13px;
  line-height: 1.8;
  color: #666;
  background: #f5f5f5;
  border-radius: 6px;
}
</style>
