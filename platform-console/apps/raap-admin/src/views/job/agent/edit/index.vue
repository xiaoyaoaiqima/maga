<script setup lang="ts">
import type { AgentApi } from '#/api/core/business';
import type { JobApi } from '#/api/core/job';

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { VbenIconButton } from '@vben-core/shadcn-ui';

import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  CloseOutlined,
  MenuOutlined,
  QuestionCircleOutlined,
  VerticalAlignBottomOutlined,
  VerticalAlignTopOutlined,
} from '@ant-design/icons-vue';
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Divider,
  Form,
  FormItem,
  Input,
  message,
  Select,
  Switch,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import {
  getAgentApi,
  getAgentSimpleListApi,
  updateAgentApi,
} from '#/api/core/business';
import { getExpertConfigListApi } from '#/api/core/job';
import { checkNameExists } from '#/utils/code_uniqueness';

const router = useRouter();
const route = useRoute();

const submitting = ref(false);
const agentLoading = ref(false);
const detailLoading = ref(false);
const agentOptions = ref<AgentApi.SimpleItem[]>([]);
const selectedAgentCode = ref<string | undefined>(undefined);
const expertConfigOptions = ref<JobApi.ExpertConfigBrief[]>([]);

const agentTypeOptions = [
  { label: '批量文章生成', value: 'BATCH_GENERATION' },
  { label: '图片审核', value: 'REVIEW_IMAGE' },
  { label: '实时对话', value: 'REALTIME_CHAT' },
  { label: '报告分析', value: 'REPORT_ANALYSIS' },
];

const formState = ref<AgentApi.CreateParams>({
  agent_code: '',
  agent_name: '',
  agent_type: 'BATCH_GENERATION',
  expert_config_code_list: [],
  zero_score_invalid_expert_codes: undefined,
  default_model_code: '',
  description: '',
  tenant_id: 9,
  remark: '',
});

const expertSearchText = ref('');
const enableZeroScoreRule = ref(false);

const availableExperts = computed(() => {
  const search = expertSearchText.value.toLowerCase();
  return expertConfigOptions.value
    .filter((x) => x.enabled)
    .filter((x) => {
      if (!search) return true;
      return (
        x.expert_config_code.toLowerCase().includes(search) ||
        x.expert_config_name.toLowerCase().includes(search) ||
        (x.description || '').toLowerCase().includes(search) ||
        (x.expert_type || '').toLowerCase().includes(search)
      );
    });
});

const selectedExperts = computed(() => {
  return (formState.value.expert_config_code_list || []).map((code, index) => {
    const config = expertConfigOptions.value.find(
      (c) => c.expert_config_code === code,
    );
    return {
      order: index + 1,
      code,
      name: config?.expert_config_name || code,
      description: config?.description || '',
      type: config?.expert_type || '-',
      model: config?.model_code || '-',
    };
  });
});

const zeroScoreCandidateExperts = computed(() => {
  return selectedExperts.value.filter(
    (e) => String(e.type).toUpperCase() !== 'GENERATION',
  );
});

function toggleExpert(code: string) {
  const index = formState.value.expert_config_code_list.indexOf(code);
  if (index === -1) {
    formState.value.expert_config_code_list.push(code);
  } else {
    formState.value.expert_config_code_list.splice(index, 1);
  }
  resetZeroScoreRuleIfNeeded();
}

function isSelected(code: string): boolean {
  return formState.value.expert_config_code_list.includes(code);
}

function removeExpert(code: string) {
  formState.value.expert_config_code_list =
    formState.value.expert_config_code_list.filter((c) => c !== code);
  resetZeroScoreRuleIfNeeded();
}

function moveExpert(index: number, direction: 'down' | 'up') {
  const list = [...formState.value.expert_config_code_list];
  const newIndex = direction === 'up' ? index - 1 : index + 1;
  if (newIndex < 0 || newIndex >= list.length) return;
  [list[index], list[newIndex]] = [list[newIndex]!, list[index]!];
  formState.value.expert_config_code_list = list;
  resetZeroScoreRuleIfNeeded();
}

const dragIndex = ref<null | number>(null);
const dragOverIndex = ref<null | number>(null);
const dragOverPosition = ref<'bottom' | 'top' | null>(null);
const flowListRef = ref<HTMLElement | null>(null);
let autoScrollInterval: null | number = null;
let globalDragOverHandler: ((e: DragEvent) => void) | null = null;

function handleDragStart(index: number, e: DragEvent) {
  dragIndex.value = index;
  dragOverIndex.value = null;
  dragOverPosition.value = null;
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.dropEffect = 'move';
  }

  if (!globalDragOverHandler) {
    globalDragOverHandler = (event: DragEvent) => {
      if (dragIndex.value === null || !flowListRef.value) {
        return;
      }
      checkAndStartAutoScroll(event);
    };
    document.addEventListener('dragover', globalDragOverHandler);
  }
}

function checkAndStartAutoScroll(e: DragEvent) {
  if (!flowListRef.value || dragIndex.value === null) {
    stopAutoScroll();
    return;
  }

  const containerRect = flowListRef.value.getBoundingClientRect();
  const mouseY = e.clientY;
  const scrollThreshold = 80;
  const extendedThreshold = 150;

  const mouseYRelative = mouseY - containerRect.top;
  const isAboveContainer = mouseY < containerRect.top;
  const isBelowContainer = mouseY > containerRect.bottom;
  const isInContainer =
    mouseY >= containerRect.top && mouseY <= containerRect.bottom;

  let scrollSpeed = 0;
  let shouldScrollUp = false;
  let shouldScrollDown = false;

  if (isAboveContainer && mouseY > containerRect.top - extendedThreshold) {
    const distance = containerRect.top - mouseY;
    scrollSpeed = Math.max(5, Math.min(20, (extendedThreshold - distance) / 5));
    shouldScrollUp = flowListRef.value.scrollTop > 0;
  } else if (isInContainer && mouseYRelative < scrollThreshold) {
    scrollSpeed = Math.max(
      8,
      Math.min(20, (scrollThreshold - mouseYRelative) / 3),
    );
    shouldScrollUp = flowListRef.value.scrollTop > 0;
  }

  if (isBelowContainer && mouseY < containerRect.bottom + extendedThreshold) {
    const distance = mouseY - containerRect.bottom;
    const maxScroll =
      flowListRef.value.scrollHeight - flowListRef.value.clientHeight;
    scrollSpeed = Math.max(5, Math.min(20, (extendedThreshold - distance) / 5));
    shouldScrollDown = flowListRef.value.scrollTop < maxScroll;
  } else if (
    isInContainer &&
    mouseYRelative > containerRect.height - scrollThreshold
  ) {
    const distance = mouseYRelative - (containerRect.height - scrollThreshold);
    const maxScroll =
      flowListRef.value.scrollHeight - flowListRef.value.clientHeight;
    scrollSpeed = Math.max(8, Math.min(20, distance / 3));
    shouldScrollDown = flowListRef.value.scrollTop < maxScroll;
  }

  if (shouldScrollUp) {
    startAutoScrollWithSpeed('up', scrollSpeed);
  } else if (shouldScrollDown) {
    startAutoScrollWithSpeed('down', scrollSpeed);
  } else {
    stopAutoScroll();
  }
}

function startAutoScrollWithSpeed(direction: 'down' | 'up', speed: number) {
  if (autoScrollInterval) {
    clearInterval(autoScrollInterval);
  }

  if (!flowListRef.value) return;

  autoScrollInterval = window.setInterval(() => {
    if (!flowListRef.value) return;

    flowListRef.value.scrollTop =
      direction === 'up'
        ? Math.max(0, flowListRef.value.scrollTop - speed)
        : Math.min(
            flowListRef.value.scrollHeight - flowListRef.value.clientHeight,
            flowListRef.value.scrollTop + speed,
          );
  }, 16);
}

function stopAutoScroll() {
  if (autoScrollInterval) {
    clearInterval(autoScrollInterval);
    autoScrollInterval = null;
  }
}

function removeGlobalDragOverHandler() {
  if (globalDragOverHandler) {
    document.removeEventListener('dragover', globalDragOverHandler);
    globalDragOverHandler = null;
  }
}

function handleDragOver(e: DragEvent, index: number) {
  e.preventDefault();
  if (dragIndex.value === null || dragIndex.value === index) {
    dragOverIndex.value = null;
    dragOverPosition.value = null;
    return;
  }

  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
  const mouseY = e.clientY;
  const elementCenter = rect.top + rect.height / 2;

  dragOverIndex.value = index;
  dragOverPosition.value = mouseY < elementCenter ? 'top' : 'bottom';

  if (e.dataTransfer) {
    e.dataTransfer.dropEffect = 'move';
  }

  checkAndStartAutoScroll(e);
}

function handleDragLeave() {}

function handleFlowListDragOver(e: DragEvent) {
  if (dragIndex.value === null || !flowListRef.value) {
    return;
  }

  e.preventDefault();
  checkAndStartAutoScroll(e);
}

function handleFlowListDragLeave() {}

function handleDragEnd() {
  stopAutoScroll();
  removeGlobalDragOverHandler();

  if (
    dragIndex.value !== null &&
    dragOverIndex.value !== null &&
    dragIndex.value !== dragOverIndex.value
  ) {
    const list = [...formState.value.expert_config_code_list];
    const [moved] = list.splice(dragIndex.value, 1);
    if (moved) {
      let targetIndex = dragOverIndex.value;
      if (
        dragOverPosition.value === 'bottom' &&
        dragIndex.value < dragOverIndex.value
      ) {
        targetIndex = dragOverIndex.value + 1;
      } else if (
        dragOverPosition.value === 'top' &&
        dragIndex.value > dragOverIndex.value
      ) {
        targetIndex = dragOverIndex.value;
      } else if (dragOverPosition.value === 'bottom') {
        targetIndex = dragOverIndex.value + 1;
      } else {
        targetIndex = dragOverIndex.value;
      }

      targetIndex = Math.max(0, Math.min(targetIndex, list.length));
      list.splice(targetIndex, 0, moved);
      formState.value.expert_config_code_list = list;
      resetZeroScoreRuleIfNeeded();
    }
  }
  dragIndex.value = null;
  dragOverIndex.value = null;
  dragOverPosition.value = null;
}

function moveExpertToTop(index: number) {
  const list = [...formState.value.expert_config_code_list];
  const [moved] = list.splice(index, 1);
  if (moved) {
    list.unshift(moved);
    formState.value.expert_config_code_list = list;
    resetZeroScoreRuleIfNeeded();
  }
}

function moveExpertToBottom(index: number) {
  const list = [...formState.value.expert_config_code_list];
  const [moved] = list.splice(index, 1);
  if (moved) {
    list.push(moved);
    formState.value.expert_config_code_list = list;
    resetZeroScoreRuleIfNeeded();
  }
}

function toggleZeroScoreExpert(code: string) {
  const list = new Set(formState.value.zero_score_invalid_expert_codes || []);
  if (list.has(code)) list.delete(code);
  else list.add(code);
  formState.value.zero_score_invalid_expert_codes = [...list];
}

function isZeroScoreSelected(code: string): boolean {
  return (formState.value.zero_score_invalid_expert_codes || []).includes(code);
}

function resetZeroScoreRuleIfNeeded() {
  if (!enableZeroScoreRule.value) {
    formState.value.zero_score_invalid_expert_codes = undefined;
    return;
  }
  const selectedSet = new Set(formState.value.expert_config_code_list);
  const current = formState.value.zero_score_invalid_expert_codes || [];
  formState.value.zero_score_invalid_expert_codes = current.filter((c) =>
    selectedSet.has(c),
  );
}

watch(
  () => [...(formState.value.expert_config_code_list || [])],
  () => resetZeroScoreRuleIfNeeded(),
);
watch(
  () => enableZeroScoreRule.value,
  () => resetZeroScoreRuleIfNeeded(),
);

const agentSelectOptions = computed(() => {
  return agentOptions.value.map((item) => ({
    label: `${item.agent_name} (${item.agent_code})`,
    value: item.agent_code,
  }));
});

async function fetchExpertConfigs() {
  try {
    expertConfigOptions.value = await getExpertConfigListApi();
  } catch {
    message.error('获取 Expert 配置列表失败');
  }
}

async function fetchAgentOptions() {
  agentLoading.value = true;
  try {
    agentOptions.value = await getAgentSimpleListApi();
  } catch {
    message.error('获取 Agent 列表失败');
  } finally {
    agentLoading.value = false;
  }
}

async function loadAgentDetail(agentCode: string) {
  detailLoading.value = true;
  try {
    const record = await getAgentApi(agentCode);
    const hasZeroScore =
      record.zero_score_invalid_expert_codes !== null &&
      record.zero_score_invalid_expert_codes !== undefined;

    formState.value = {
      agent_code: record.agent_code,
      agent_name: record.agent_name,
      agent_type: record.agent_type,
      expert_config_code_list: record.expert_config_code_list || [],
      zero_score_invalid_expert_codes: hasZeroScore
        ? (record.zero_score_invalid_expert_codes as string[])
        : undefined,
      default_model_code: record.default_model_code || '',
      description: record.description || '',
      tenant_id: record.tenant_id || 9,
      remark: record.remark || '',
    };
    enableZeroScoreRule.value = hasZeroScore;
    expertSearchText.value = '';
  } catch {
    message.error('获取 Agent 详情失败');
  } finally {
    detailLoading.value = false;
  }
}

watch(
  () => selectedAgentCode.value,
  (code) => {
    if (!code) return;
    router.replace({
      path: route.path,
      query: { ...route.query, agent_code: code },
    });
    loadAgentDetail(code);
  },
);

async function handleSubmit() {
  if (!selectedAgentCode.value) {
    message.warning('请选择 Agent');
    return;
  }
  if (!formState.value.agent_name || !formState.value.agent_type) {
    message.warning('请填写必填字段');
    return;
  }
  if (formState.value.expert_config_code_list.length === 0) {
    message.warning('请至少选择一个 Expert 配置');
    return;
  }

  // 名称唯一性校验
  const nameExists = await checkNameExists(
    'agent',
    formState.value.agent_name,
    selectedAgentCode.value,
  );
  if (nameExists) {
    message.error(
      `名称 "${formState.value.agent_name}" 已存在，请使用其他名称`,
    );
    return;
  }

  submitting.value = true;
  try {
    resetZeroScoreRuleIfNeeded();

    let zeroScorePayload: Record<string, unknown> = {};
    zeroScorePayload = enableZeroScoreRule.value
      ? {
          zero_score_invalid_expert_codes:
            (formState.value.zero_score_invalid_expert_codes as string[]) || [],
        }
      : { zero_score_invalid_expert_codes: null };

    const payload: AgentApi.UpdateParams = {
      ...formState.value,
      ...zeroScorePayload,
    };

    await updateAgentApi(selectedAgentCode.value, payload);
    message.success('更新成功');
    router.push('/job/agent');
  } catch {
    message.error('更新失败');
  } finally {
    submitting.value = false;
  }
}

function handleCancel() {
  router.push('/job/agent');
}

onMounted(async () => {
  await Promise.all([fetchAgentOptions(), fetchExpertConfigs()]);
  const queryCode =
    typeof route.query.agent_code === 'string'
      ? route.query.agent_code
      : undefined;
  if (queryCode) {
    selectedAgentCode.value = queryCode;
  }
});

onBeforeUnmount(() => {
  stopAutoScroll();
  removeGlobalDragOverHandler();
});
</script>

<template>
  <div class="agent-edit-page">
    <div class="page-header">
      <div class="header-title-row">
        <span class="header-title">修改 Agent</span>
      </div>
      <div class="header-toolbar-row">
        <div class="header-selector-row">
          <div class="selector-label">Agent 选择</div>
          <Select
            v-model:value="selectedAgentCode"
            :options="agentSelectOptions"
            :loading="agentLoading"
            placeholder="请选择 Agent"
            show-search
            class="selector-input"
            :get-popup-container="(trigger) => trigger.parentElement"
          />
        </div>
        <div class="header-action-row">
          <Button @click="handleCancel">返回</Button>
          <Button
            type="primary"
            :loading="submitting"
            :disabled="detailLoading || !selectedAgentCode"
            @click="handleSubmit"
          >
            保存修改
          </Button>
        </div>
      </div>
    </div>

    <div class="form-card">
      <Form :label-col="{ span: 5 }" :wrapper-col="{ span: 18 }">
        <FormItem label="Agent 编码">
          <Input v-model:value="formState.agent_code" readonly />
        </FormItem>
        <FormItem label="Agent 名称" required>
          <Input
            v-model:value="formState.agent_name"
            placeholder="请输入 Agent 名称"
          />
        </FormItem>
        <FormItem label="类型" required>
          <Select
            v-model:value="formState.agent_type"
            :options="agentTypeOptions"
            placeholder="请选择 Agent 类型"
          />
        </FormItem>
        <FormItem label="Expert 编排" required>
          <Alert
            message="Expert 编排配置"
            description="点击左侧 Expert 选择/取消，右侧可调整执行顺序。0 分判无效规则会写入 Agent，创建任务时自动继承。"
            type="info"
            show-icon
            style="margin-bottom: 12px"
          />

          <div class="expert-selection-container">
            <div class="expert-list-panel">
              <div class="panel-header">
                <span class="panel-title">可选 Expert</span>
                <Badge :count="availableExperts.length" :overflow-count="999" />
              </div>
              <div class="panel-search">
                <Input
                  v-model:value="expertSearchText"
                  allow-clear
                  placeholder="搜索 Expert..."
                />
              </div>
              <div class="expert-cards">
                <div
                  v-for="expert in availableExperts"
                  :key="expert.expert_config_code"
                  :class="{ selected: isSelected(expert.expert_config_code) }"
                  class="expert-card"
                  @click="toggleExpert(expert.expert_config_code)"
                >
                  <div class="expert-card-header">
                    <Checkbox
                      :checked="isSelected(expert.expert_config_code)"
                    />
                    <span class="expert-card-name">
                      {{ expert.expert_config_name }}
                    </span>
                  </div>
                  <div class="expert-card-code">
                    {{ expert.expert_config_code }}
                  </div>
                  <div class="expert-card-meta">
                    <Tag v-if="expert.expert_type" color="purple" size="small">
                      {{ expert.expert_type }}
                    </Tag>
                    <Tag v-if="expert.model_code" color="cyan" size="small">
                      {{ expert.model_code }}
                    </Tag>
                  </div>
                </div>
                <div v-if="availableExperts.length === 0" class="empty-experts">
                  <span>没有找到匹配的 Expert</span>
                </div>
              </div>
            </div>

            <div class="flow-panel">
              <div class="panel-header">
                <span class="panel-title">执行顺序</span>
                <Badge
                  :count="selectedExperts.length"
                  :number-style="{ backgroundColor: 'hsl(var(--primary))' }"
                />
              </div>
              <div
                ref="flowListRef"
                class="flow-list"
                @dragover="handleFlowListDragOver"
                @dragleave="handleFlowListDragLeave"
              >
                <div
                  v-for="(expert, index) in selectedExperts"
                  :key="expert.code"
                  class="flow-item"
                  :class="{
                    'flow-item-dragging': dragIndex === index,
                    'flow-item-dragover-top':
                      dragOverIndex === index &&
                      dragIndex !== index &&
                      dragOverPosition === 'top',
                    'flow-item-dragover-bottom':
                      dragOverIndex === index &&
                      dragIndex !== index &&
                      dragOverPosition === 'bottom',
                  }"
                  @dragover="(e) => handleDragOver(e, index)"
                  @dragleave="handleDragLeave"
                >
                  <div
                    class="drag-handle"
                    title="拖拽排序"
                    draggable="true"
                    @dragstart="(e) => handleDragStart(index, e)"
                    @dragend="handleDragEnd"
                  >
                    <MenuOutlined />
                  </div>
                  <div class="flow-item-body">
                    <div class="flow-item-header">
                      <div class="flow-step">{{ expert.order }}</div>
                      <div class="flow-item-main">
                        <Tooltip :title="expert.name" placement="top">
                          <div class="flow-name">{{ expert.name }}</div>
                        </Tooltip>
                        <span class="flow-description">
                          {{ expert.description || '无描述' }}
                        </span>
                      </div>
                    </div>
                    <div class="flow-actions">
                      <VbenIconButton
                        tooltip="置顶"
                        class="flow-action-btn"
                        :disabled="index === 0"
                        @click.stop="moveExpertToTop(index)"
                      >
                        <VerticalAlignTopOutlined />
                      </VbenIconButton>
                      <VbenIconButton
                        tooltip="上移"
                        class="flow-action-btn"
                        :disabled="index === 0"
                        @click.stop="moveExpert(index, 'up')"
                      >
                        <ArrowUpOutlined />
                      </VbenIconButton>
                      <VbenIconButton
                        tooltip="下移"
                        class="flow-action-btn"
                        :disabled="index === selectedExperts.length - 1"
                        @click.stop="moveExpert(index, 'down')"
                      >
                        <ArrowDownOutlined />
                      </VbenIconButton>
                      <VbenIconButton
                        tooltip="置底"
                        class="flow-action-btn"
                        :disabled="index === selectedExperts.length - 1"
                        @click.stop="moveExpertToBottom(index)"
                      >
                        <VerticalAlignBottomOutlined />
                      </VbenIconButton>
                      <VbenIconButton
                        tooltip="移除"
                        class="flow-action-btn flow-action-btn-danger"
                        @click.stop="removeExpert(expert.code)"
                      >
                        <CloseOutlined />
                      </VbenIconButton>
                    </div>
                  </div>
                </div>
                <div v-if="selectedExperts.length === 0" class="empty-flow">
                  <span>从左侧选择 Expert</span>
                </div>
              </div>

              <Divider style="margin: 12px 0" />

              <div class="zero-score-rule">
                <div class="zero-score-rule-header">
                  <div class="zero-score-rule-title">
                    <span>0 分判无效 Expert</span>
                    <Tooltip
                      title="开启后：仅当你选中的 Expert 返回 score==0 时，会判定内容不可用。关闭则保持兼容旧逻辑。"
                    >
                      <QuestionCircleOutlined class="help-icon" />
                    </Tooltip>
                  </div>
                  <Switch v-model:checked="enableZeroScoreRule" />
                </div>

                <div v-if="enableZeroScoreRule" class="zero-score-rule-body">
                  <Alert
                    class="zero-score-alert"
                    message="提示"
                    :description="
                      zeroScoreCandidateExperts.length > 0
                        ? '勾选哪些 Expert 的 score==0 会触发判无效。若不勾选任何项，则表示不启用 0 分判无效。'
                        : '当前执行顺序中没有可用的打分型 Expert（非 GENERATION）。'
                    "
                    show-icon
                    type="info"
                  />
                  <div
                    v-if="zeroScoreCandidateExperts.length > 0"
                    class="zero-score-options"
                  >
                    <div
                      v-for="expert in zeroScoreCandidateExperts"
                      :key="expert.code"
                      class="zero-score-option"
                      @click="toggleZeroScoreExpert(expert.code)"
                    >
                      <Checkbox :checked="isZeroScoreSelected(expert.code)" />
                      <div class="zero-score-option-main">
                        <div class="zero-score-option-name">
                          {{ expert.name }}
                          <Tag color="purple" size="small">
                            {{ expert.type }}
                          </Tag>
                        </div>
                        <div class="zero-score-option-code">
                          <code>{{ expert.code }}</code>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </FormItem>
        <FormItem label="描述">
          <Input.TextArea
            v-model:value="formState.description"
            placeholder="请输入 Agent 描述"
            :rows="2"
          />
        </FormItem>
        <FormItem label="备注">
          <Input.TextArea
            v-model:value="formState.remark"
            placeholder="请输入备注"
            :rows="2"
          />
        </FormItem>
      </Form>
    </div>
  </div>
</template>

<style scoped>
.agent-edit-page {
  padding: 16px;
}

.page-header {
  position: sticky;
  top: 0;
  z-index: 10;
  padding: 12px 16px 16px;
  margin: -16px -16px 16px;
  background: hsl(var(--background) / 85%);
  border-bottom: 1px solid hsl(var(--border) / 30%);
  box-shadow: 0 12px 20px hsl(var(--background-deep) / 12%);
  backdrop-filter: blur(12px);
}

.header-title-row {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}

.header-title {
  font-size: 20px;
  font-weight: 700;
  color: transparent;
  background: linear-gradient(90deg, hsl(var(--primary)), hsl(var(--success)));
  background-clip: text;
}

.header-action-row {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
}

.header-toolbar-row {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.header-selector-row {
  display: flex;
  flex: 1;
  flex-wrap: nowrap;
  gap: 12px;
  align-items: center;
  min-width: 0;
  padding: 12px 14px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
}

.selector-label {
  font-weight: 600;
  color: hsl(var(--foreground));
}

.selector-input {
  flex: 1;
  min-width: 320px;
}

.form-card {
  padding: 20px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  box-shadow: 0 6px 16px hsl(var(--background-deep) / 20%);
}

.expert-selection-container {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  min-height: 360px;
}

.expert-list-panel,
.flow-panel {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  background: hsl(var(--muted) / 30%);
  border-bottom: 1px solid hsl(var(--border));
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.panel-search {
  padding: 10px 12px;
  border-bottom: 1px solid hsl(var(--border));
}

.expert-cards {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  max-height: 280px;
  padding: 12px;
  overflow-y: auto;
}

.expert-card {
  padding: 10px 12px;
  cursor: pointer;
  background: hsl(var(--background));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  transition: all 0.2s;
}

.expert-card:hover {
  background: hsl(var(--muted) / 30%);
  border-color: hsl(var(--primary) / 50%);
}

.expert-card.selected {
  background: hsl(var(--primary) / 8%);
  border-color: hsl(var(--primary));
}

.expert-card-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}

.expert-card-name {
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.expert-card-code {
  margin-bottom: 6px;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.expert-card-meta {
  display: flex;
  gap: 6px;
}

.empty-experts,
.empty-flow {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 80px;
  color: hsl(var(--muted-foreground));
}

.flow-list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  max-height: 280px;
  padding: 12px;
  overflow-y: auto;
}

.flow-item {
  position: relative;
  display: flex;
  gap: 12px;
  align-items: stretch;
  min-height: 90px;
  padding: 10px 12px;
  background: hsl(var(--muted) / 25%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  transition: all 0.2s ease;
}

.flow-item:hover {
  background: hsl(var(--muted) / 35%);
  border-color: hsl(var(--primary) / 35%);
  box-shadow: 0 6px 18px hsl(var(--foreground) / 6%);
}

.flow-item-body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  min-width: 0;
}

.flow-item-header {
  display: flex;
  gap: 12px;
  align-items: center;
  min-width: 0;
  overflow: hidden;
}

.flow-item-main {
  display: flex;
  flex: 1;
  gap: 8px;
  align-items: baseline;
  min-width: 0;
}

.flow-description {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
}

.drag-handle {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  font-size: 18px;
  color: hsl(var(--muted-foreground));
  cursor: grab;
  user-select: none;
  background: hsl(var(--muted) / 50%);
  border-radius: 6px;
  transition: all 0.2s;
}

.drag-handle:hover {
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 20%);
  transform: scale(1.05);
}

.drag-handle:active {
  cursor: grabbing;
  transform: scale(0.95);
}

.flow-item-dragging {
  background: hsl(var(--muted) / 30%);
  border-style: dashed;
  opacity: 0.4;
  transform: scale(0.95);
}

.flow-item-dragover-top {
  background: hsl(var(--primary) / 8%);
  border-top: 3px solid hsl(var(--primary));
}

.flow-item-dragover-top::before {
  position: absolute;
  top: -2px;
  right: 0;
  left: 0;
  height: 2px;
  content: '';
  background: hsl(var(--primary));
  border-radius: 2px;
}

.flow-item-dragover-bottom {
  background: hsl(var(--primary) / 8%);
  border-bottom: 3px solid hsl(var(--primary));
}

.flow-item-dragover-bottom::after {
  position: absolute;
  right: 0;
  bottom: -2px;
  left: 0;
  height: 2px;
  content: '';
  background: hsl(var(--primary));
  border-radius: 2px;
}

.flow-step {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  font-size: 13px;
  font-weight: 600;
  color: hsl(var(--primary-foreground));
  background: hsl(var(--primary));
  border-radius: 50%;
}

.flow-name {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
  font-weight: 500;
  line-height: 1.4;
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.flow-actions {
  display: flex;
  flex-wrap: nowrap;
  gap: 4px;
  align-items: center;
  justify-content: flex-end;
  min-width: 0;
  padding-left: 38px;
}

.flow-action-btn {
  font-size: 15px;
  color: hsl(var(--muted-foreground)) !important;
  transition: all 0.2s ease;
}

.flow-action-btn:hover {
  color: hsl(var(--foreground)) !important;
  background: hsl(var(--muted) / 35%) !important;
}

.flow-action-btn-danger {
  color: hsl(var(--destructive)) !important;
}

.flow-action-btn-danger:hover {
  background: hsl(var(--destructive) / 12%) !important;
}

.zero-score-rule {
  padding: 10px 12px 12px;
  background: hsl(var(--muted) / 10%);
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
}

.zero-score-rule-header {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.zero-score-rule-title {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.help-icon {
  color: hsl(var(--muted-foreground));
  cursor: help;
}

.zero-score-rule-body {
  margin-top: 10px;
}

.zero-score-alert {
  margin-bottom: 10px;
}

.zero-score-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.zero-score-option {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 10px 12px;
  cursor: pointer;
  background: hsl(var(--background));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.zero-score-option:hover {
  background: hsl(var(--muted) / 30%);
  border-color: hsl(var(--primary) / 50%);
}

.zero-score-option-main {
  flex: 1;
  min-width: 0;
}

.zero-score-option-name {
  display: flex;
  gap: 8px;
  align-items: center;
  font-weight: 500;
}

.zero-score-option-code code {
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}
</style>
