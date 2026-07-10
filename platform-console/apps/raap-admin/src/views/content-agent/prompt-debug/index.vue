<script setup lang="ts">
import type { LLMApi } from '#/api/core/llm';
import type { PromptDebugApi } from '#/api/core/prompt-debug';

import { computed, h, onMounted, reactive, ref } from 'vue';

import {
  CopyOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue';
import {
  Button,
  Card,
  Col,
  Collapse,
  CollapsePanel,
  Form,
  FormItem,
  InputNumber,
  message,
  RadioButton,
  RadioGroup,
  Row,
  Select,
  Space,
  Tag,
  Textarea,
  Tooltip,
} from 'ant-design-vue';

import { getAvailableModelsApi } from '#/api/core/llm';
import { runPromptDebugApi } from '#/api/core/prompt-debug';

type PanelKey = 'left' | 'right';
type WorkbenchMode = 'compare' | 'single';

interface DebugPanelState {
  content: string;
  error_message: string;
  latency_ms?: null | number;
  loading: boolean;
  max_tokens: number;
  model_code: string;
  provider_code?: null | string;
  provider_model?: null | string;
  prompt: string;
  system_prompt: string;
  temperature: number;
  usage?: null | PromptDebugApi.TokenUsage;
}

const mode = ref<WorkbenchMode>('single');
const loadingModels = ref(false);
const models = ref<LLMApi.AvailableModel[]>([]);

const panels = reactive<Record<PanelKey, DebugPanelState>>({
  left: createPanelState(),
  right: createPanelState(),
});

const modelOptions = computed(() =>
  models.value.map((model) => ({
    label: `${model.model_name || model.model_code} (${model.model_code})`,
    value: model.model_code,
  })),
);

const visiblePanelKeys = computed<PanelKey[]>(() =>
  mode.value === 'compare' ? ['left', 'right'] : ['left'],
);

function createPanelState(): DebugPanelState {
  return {
    content: '',
    error_message: '',
    latency_ms: null,
    loading: false,
    max_tokens: 1500,
    model_code: '',
    provider_code: null,
    provider_model: null,
    prompt: '',
    system_prompt: '',
    temperature: 0.7,
    usage: null,
  };
}

function panelTitle(panelKey: PanelKey) {
  if (mode.value === 'single') return '调试组';
  return panelKey === 'left' ? '对照组 A' : '对照组 B';
}

function tokenText(usage?: null | PromptDebugApi.TokenUsage) {
  if (!usage) return 'token -';
  return `token ${usage.total_tokens} · in ${usage.input_tokens} · out ${usage.output_tokens}`;
}

function modelMetaText(panel: DebugPanelState) {
  const provider = panel.provider_code || 'provider -';
  const model = panel.provider_model || panel.model_code || 'model -';
  return `${provider} / ${model}`;
}

function applyDefaultModel() {
  const preferred =
    models.value.find((model) => model.model_code === 'deepseek-v4-flash') ||
    models.value[0];
  if (!preferred) return;
  for (const panel of Object.values(panels)) {
    if (!panel.model_code) panel.model_code = preferred.model_code;
  }
}

async function loadModels() {
  loadingModels.value = true;
  try {
    const result = await getAvailableModelsApi();
    models.value = result?.items || [];
    applyDefaultModel();
  } catch (error: any) {
    message.error(error?.message || '获取模型列表失败');
  } finally {
    loadingModels.value = false;
  }
}

function validatePanel(panel: DebugPanelState) {
  if (!panel.prompt.trim()) {
    message.warning('请输入 Prompt');
    return false;
  }
  if (!panel.model_code.trim()) {
    message.warning('请选择模型');
    return false;
  }
  return true;
}

function buildRequest(panel: DebugPanelState): PromptDebugApi.RunRequest {
  const data: PromptDebugApi.RunRequest = {
    max_tokens: panel.max_tokens,
    model_code: panel.model_code,
    prompt: panel.prompt,
    temperature: panel.temperature,
  };
  if (panel.system_prompt.trim()) {
    data.system_prompt = panel.system_prompt;
  }
  return data;
}

async function runPanel(panelKey: PanelKey) {
  const panel = panels[panelKey];
  if (!validatePanel(panel)) return;

  panel.loading = true;
  panel.content = '';
  panel.error_message = '';
  panel.usage = null;
  panel.latency_ms = null;
  panel.provider_code = null;
  panel.provider_model = null;

  try {
    const result = await runPromptDebugApi(buildRequest(panel));
    panel.content = result.content || '';
    panel.error_message = result.success ? '' : result.error_message || '调试失败';
    panel.usage = result.usage || null;
    panel.latency_ms = result.latency_ms ?? null;
    panel.provider_code = result.provider_code || null;
    panel.provider_model = result.provider_model || null;
    if (result.model_code) panel.model_code = result.model_code;
    if (result.success) {
      message.success(`${panelTitle(panelKey)}运行完成`);
    } else {
      message.error(panel.error_message);
    }
  } catch (error: any) {
    panel.error_message = error?.message || '调试失败';
    message.error(panel.error_message);
  } finally {
    panel.loading = false;
  }
}

async function runVisiblePanels() {
  await Promise.all(visiblePanelKeys.value.map((panelKey) => runPanel(panelKey)));
}

async function copyText(text: string) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    message.success('已复制');
  } catch {
    message.error('复制失败');
  }
}

onMounted(loadModels);
</script>

<template>
  <div class="prompt-debug-page">
    <div class="page-header">
      <div>
        <h1>提示词调试</h1>
        <p>粘贴完整 Prompt，选择模型后直接运行，输出不进入生成任务和审核流程。</p>
      </div>
      <Space wrap>
        <RadioGroup v-model:value="mode" button-style="solid">
          <RadioButton value="single">单组</RadioButton>
          <RadioButton value="compare">对照组</RadioButton>
        </RadioGroup>
        <Button :icon="h(ReloadOutlined)" :loading="loadingModels" @click="loadModels">
          刷新模型
        </Button>
        <Button
          type="primary"
          :icon="h(PlayCircleOutlined)"
          :loading="visiblePanelKeys.some((key) => panels[key].loading)"
          @click="runVisiblePanels"
        >
          {{ mode === 'compare' ? '运行左右' : '运行' }}
        </Button>
      </Space>
    </div>

    <Row :gutter="[16, 16]">
      <Col
        v-for="panelKey in visiblePanelKeys"
        :key="panelKey"
        :xs="24"
        :lg="mode === 'compare' ? 12 : 24"
      >
        <Card class="debug-panel" :title="panelTitle(panelKey)">
          <template #extra>
            <Button
              size="small"
              type="primary"
              ghost
              :icon="h(PlayCircleOutlined)"
              :loading="panels[panelKey].loading"
              @click="runPanel(panelKey)"
            >
              运行
            </Button>
          </template>

          <Form layout="vertical" class="panel-form">
            <Row :gutter="12">
              <Col :xs="24" :md="14">
                <FormItem label="模型">
                  <Select
                    v-model:value="panels[panelKey].model_code"
                    show-search
                    :loading="loadingModels"
                    :options="modelOptions"
                    placeholder="选择模型"
                    option-filter-prop="label"
                  />
                </FormItem>
              </Col>
              <Col :xs="12" :md="5">
                <FormItem label="temperature">
                  <InputNumber
                    v-model:value="panels[panelKey].temperature"
                    :min="0"
                    :max="2"
                    :step="0.1"
                    class="full-width"
                  />
                </FormItem>
              </Col>
              <Col :xs="12" :md="5">
                <FormItem label="max_tokens">
                  <InputNumber
                    v-model:value="panels[panelKey].max_tokens"
                    :min="1"
                    :max="20_000"
                    class="full-width"
                  />
                </FormItem>
              </Col>
            </Row>

            <Collapse ghost class="system-prompt-collapse">
              <CollapsePanel key="system" header="system prompt">
                <Textarea
                  v-model:value="panels[panelKey].system_prompt"
                  :auto-size="{ minRows: 3, maxRows: 8 }"
                  placeholder="可选，不填则只发送用户 Prompt"
                />
              </CollapsePanel>
            </Collapse>

            <FormItem label="Prompt">
              <Textarea
                v-model:value="panels[panelKey].prompt"
                :auto-size="{ minRows: mode === 'compare' ? 16 : 20, maxRows: 36 }"
                placeholder="粘贴完整提示词"
              />
            </FormItem>
          </Form>

          <div class="result-toolbar">
            <Space wrap size="small">
              <Tag>{{ panels[panelKey].latency_ms ?? '-' }} ms</Tag>
              <Tag>{{ tokenText(panels[panelKey].usage) }}</Tag>
              <Tag>{{ modelMetaText(panels[panelKey]) }}</Tag>
            </Space>
            <Tooltip title="复制输出">
              <Button
                size="small"
                :icon="h(CopyOutlined)"
                :disabled="!panels[panelKey].content"
                @click="copyText(panels[panelKey].content)"
              />
            </Tooltip>
          </div>

          <div
            class="result-box"
            :class="{ 'result-box-error': panels[panelKey].error_message }"
          >
            <template v-if="panels[panelKey].loading">运行中...</template>
            <template v-else-if="panels[panelKey].error_message">
              {{ panels[panelKey].error_message }}
            </template>
            <template v-else-if="panels[panelKey].content">
              {{ panels[panelKey].content }}
            </template>
            <template v-else>等待运行</template>
          </div>
        </Card>
      </Col>
    </Row>
  </div>
</template>

<style scoped>
.prompt-debug-page {
  min-height: 100%;
  padding: 16px;
  background: #f6f8fb;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.page-header h1 {
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 650;
  color: #1f2937;
}

.page-header p {
  margin: 0;
  color: #64748b;
}

.debug-panel {
  border-radius: 8px;
}

.panel-form :deep(.ant-form-item) {
  margin-bottom: 12px;
}

.full-width {
  width: 100%;
}

.system-prompt-collapse {
  margin: -6px 0 8px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #ffffff;
}

.system-prompt-collapse :deep(.ant-collapse-header) {
  padding: 8px 12px !important;
  color: #475569;
}

.system-prompt-collapse :deep(.ant-collapse-content-box) {
  padding: 0 12px 12px !important;
}

.result-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 4px 0 8px;
}

.result-box {
  min-height: 180px;
  max-height: 420px;
  padding: 12px;
  overflow: auto;
  color: #111827;
  white-space: pre-wrap;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
}

.result-box-error {
  color: #991b1b;
  background: #fff1f2;
  border-color: #fecdd3;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
  }
}
</style>
