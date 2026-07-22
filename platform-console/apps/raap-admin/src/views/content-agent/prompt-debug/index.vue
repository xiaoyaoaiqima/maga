<script setup lang="ts">
import type { PromptDebugArticle } from './output-parser';

import type { LLMApi } from '#/api/core/llm';
import type { PromptDebugApi } from '#/api/core/prompt-debug';

import { computed, h, onMounted, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';

import {
  CopyOutlined,
  HistoryOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue';
import {
  Button,
  Card,
  Col,
  Collapse,
  CollapsePanel,
  Drawer,
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
import {
  getPromptDebugHistoryApi,
  getPromptDebugHistoryDetailApi,
  runPromptDebugApi,
} from '#/api/core/prompt-debug';

import {
  normalizePromptDebugBatchSize,
  runPromptDebugBatch,
} from './batch-runner';
import { parsePromptDebugArticles } from './output-parser';
import { loadPromptDebugTransfer } from './prompt-transfer';

type PanelKey = 'left' | 'right';
type WorkbenchMode = 'compare' | 'single';

const route = useRoute();

interface DebugRunState {
  articles: PromptDebugArticle[];
  content: string;
  error_message: string;
  history_id?: null | number;
  index: number;
  latency_ms?: null | number;
  loading: boolean;
  model_code?: null | string;
  provider_code?: null | string;
  provider_model?: null | string;
  success?: boolean | null;
  usage?: null | PromptDebugApi.TokenUsage;
}

interface DebugPanelState {
  batch_size: number;
  completed_count: number;
  loading: boolean;
  max_tokens: number;
  model_code: string;
  prompt: string;
  results: DebugRunState[];
  system_prompt: string;
  temperature: number;
}

const mode = ref<WorkbenchMode>('single');
const loadingModels = ref(false);
const models = ref<LLMApi.AvailableModel[]>([]);
const historyOpen = ref(false);
const historyLoading = ref(false);
const historyGroups = ref<PromptDebugApi.HistoryGroupSummary[]>([]);
const restoringGroupId = ref('');

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
    batch_size: 2,
    completed_count: 0,
    loading: false,
    max_tokens: 1500,
    model_code: '',
    prompt: '',
    results: [],
    system_prompt: '',
    temperature: 0.9,
  };
}

function createRunState(index: number): DebugRunState {
  return {
    articles: [],
    content: '',
    error_message: '',
    history_id: null,
    index,
    latency_ms: null,
    loading: true,
    model_code: null,
    provider_code: null,
    provider_model: null,
    success: null,
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

function modelMetaText(result: DebugRunState, panel: DebugPanelState) {
  const provider = result.provider_code || 'provider -';
  const model = result.provider_model || result.model_code || panel.model_code;
  return `${provider} / ${model}`;
}

function successfulRunCount(panel: DebugPanelState) {
  return panel.results.filter((result) => result.success).length;
}

function failedRunCount(panel: DebugPanelState) {
  return panel.results.filter((result) => result.success === false).length;
}

function resultCountText(panel: DebugPanelState) {
  return panel.results.length > 0 ? panel.results.length : '-';
}

function runButtonText(panel: DebugPanelState) {
  const batchSize = normalizePromptDebugBatchSize(panel.batch_size);
  return batchSize === 1 ? '运行' : `并发运行 ${batchSize} 篇`;
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

function buildRequest(
  panel: DebugPanelState,
  metadata: Pick<
    PromptDebugApi.RunRequest,
    'batch_size' | 'item_index' | 'panel_key' | 'run_group_id' | 'workbench_mode'
  >,
): PromptDebugApi.RunRequest {
  const data: PromptDebugApi.RunRequest = {
    max_tokens: panel.max_tokens,
    model_code: panel.model_code,
    prompt: panel.prompt,
    temperature: panel.temperature,
    ...metadata,
  };
  if (panel.system_prompt.trim()) {
    data.system_prompt = panel.system_prompt;
  }
  return data;
}

function createRunGroupId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID().replaceAll('-', '');
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

async function runPanel(panelKey: PanelKey, runGroupId: string) {
  const panel = panels[panelKey];
  if (!validatePanel(panel)) return;

  const batchSize = normalizePromptDebugBatchSize(panel.batch_size);
  panel.batch_size = batchSize;
  panel.loading = true;
  panel.completed_count = 0;
  panel.results = Array.from({ length: batchSize }, (_, index) =>
    createRunState(index),
  );

  try {
    await runPromptDebugBatch(batchSize, async (index) => {
      const runState = panel.results[index];
      try {
        const result = await runPromptDebugApi(
          buildRequest(panel, {
            batch_size: batchSize,
            item_index: index,
            panel_key: panelKey,
            run_group_id: runGroupId,
            workbench_mode: mode.value,
          }),
        );
        runState.content = result.content || '';
        runState.articles = parsePromptDebugArticles(runState.content);
        runState.error_message = result.success
          ? ''
          : result.error_message || '调试失败';
        runState.latency_ms = result.latency_ms ?? null;
        runState.history_id = result.history_id ?? null;
        runState.model_code = result.model_code || null;
        runState.provider_code = result.provider_code || null;
        runState.provider_model = result.provider_model || null;
        runState.success = result.success;
        runState.usage = result.usage || null;
        if (result.model_code) panel.model_code = result.model_code;
      } catch (error: any) {
        runState.error_message = error?.message || '调试失败';
        runState.success = false;
      } finally {
        runState.loading = false;
        panel.completed_count += 1;
      }
      return runState;
    });

    const successCount = successfulRunCount(panel);
    const failCount = failedRunCount(panel);
    if (failCount === 0) {
      message.success(`${panelTitle(panelKey)}完成：${successCount} 篇成功`);
    } else if (successCount > 0) {
      message.warning(
        `${panelTitle(panelKey)}完成：${successCount} 篇成功，${failCount} 篇失败`,
      );
    } else {
      message.error(`${panelTitle(panelKey)}运行失败`);
    }
  } finally {
    panel.loading = false;
  }
}

async function runVisiblePanels() {
  const runGroupId = createRunGroupId();
  await Promise.all(
    visiblePanelKeys.value.map((panelKey) => runPanel(panelKey, runGroupId)),
  );
  if (historyOpen.value) await loadHistory();
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

function copyAllResults(panel: DebugPanelState) {
  const output = panel.results
    .map((result, index) =>
      result.content ? `第 ${index + 1} 篇\n${result.content}` : '',
    )
    .filter(Boolean)
    .join('\n\n---\n\n');
  return copyText(output);
}

function formatHistoryTime(value?: null | string) {
  return value || '-';
}

function historyModeText(value: WorkbenchMode) {
  return value === 'compare' ? '左右对照' : '单组';
}

async function loadHistory() {
  historyLoading.value = true;
  try {
    const result = await getPromptDebugHistoryApi();
    historyGroups.value = result.items || [];
  } catch (error: any) {
    message.error(error?.message || '获取调试历史失败');
  } finally {
    historyLoading.value = false;
  }
}

async function openHistory() {
  historyOpen.value = true;
  await loadHistory();
}

function restorePanelFromHistory(
  panelKey: PanelKey,
  records: PromptDebugApi.HistoryItem[],
) {
  const panel = panels[panelKey];
  if (records.length === 0) {
    Object.assign(panel, createPanelState());
    applyDefaultModel();
    return;
  }
  const first = records[0];
  panel.batch_size = first.batch_size;
  panel.completed_count = records.length;
  panel.loading = false;
  panel.max_tokens = first.max_tokens;
  panel.model_code = first.requested_model_code;
  panel.prompt = first.prompt;
  panel.system_prompt = first.system_prompt || '';
  panel.temperature = first.temperature;
  panel.results = records.map((record) => ({
    articles: parsePromptDebugArticles(record.content || ''),
    content: record.content || '',
    error_message: record.error_message || '',
    history_id: record.id,
    index: record.item_index,
    latency_ms: record.latency_ms ?? null,
    loading: false,
    model_code: record.model_code || null,
    provider_code: record.provider_code || null,
    provider_model: record.provider_model || null,
    success: record.success,
    usage: record.token_usage || null,
  }));
}

async function restoreHistory(group: PromptDebugApi.HistoryGroupSummary) {
  restoringGroupId.value = group.run_group_id;
  try {
    const detail = await getPromptDebugHistoryDetailApi(group.run_group_id);
    mode.value = detail.workbench_mode;
    restorePanelFromHistory(
      'left',
      detail.records.filter((record) => record.panel_key === 'left'),
    );
    restorePanelFromHistory(
      'right',
      detail.records.filter((record) => record.panel_key === 'right'),
    );
    historyOpen.value = false;
    message.success('已载入调试历史');
  } catch (error: any) {
    message.error(error?.message || '载入调试历史失败');
  } finally {
    restoringGroupId.value = '';
  }
}

onMounted(() => {
  const promptKey = route.query.prompt_key;
  const transferredInput = loadPromptDebugTransfer(promptKey);
  if (transferredInput) {
    panels.left.prompt = transferredInput.prompt;
    panels.left.system_prompt = transferredInput.system_prompt || '';
    if (transferredInput.model_code) {
      panels.left.model_code = transferredInput.model_code;
    }
    if (typeof transferredInput.temperature === 'number') {
      panels.left.temperature = transferredInput.temperature;
    }
    if (typeof transferredInput.max_tokens === 'number') {
      panels.left.max_tokens = transferredInput.max_tokens;
    }
    message.success('已带入完整生成配置');
  } else if (promptKey) {
    message.warning('生成 Prompt 已失效，请从生成历史重新进入');
  }
  loadModels();
});
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
        <Button :icon="h(HistoryOutlined)" @click="openHistory">
          历史记录
        </Button>
        <Button :icon="h(ReloadOutlined)" :loading="loadingModels" @click="loadModels">
          刷新模型
        </Button>
        <Button
          type="primary"
          :icon="h(PlayCircleOutlined)"
          :loading="visiblePanelKeys.some((key) => panels[key].loading)"
          @click="runVisiblePanels"
        >
          {{ mode === 'compare' ? '运行左右' : runButtonText(panels.left) }}
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
          <Form layout="vertical" class="panel-form">
            <Row :gutter="12">
              <Col :xs="24" :md="10">
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
              <Col :xs="12" :md="4">
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
              <Col :xs="12" :md="5">
                <FormItem label="并发篇数">
                  <InputNumber
                    v-model:value="panels[panelKey].batch_size"
                    :min="1"
                    :max="20"
                    :precision="0"
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
              <Tag>
                共 {{ resultCountText(panels[panelKey]) }} 篇
              </Tag>
              <Tag v-if="panels[panelKey].loading" color="processing">
                完成 {{ panels[panelKey].completed_count }} /
                {{ panels[panelKey].results.length }}
              </Tag>
              <Tag
                v-if="successfulRunCount(panels[panelKey]) > 0"
                color="success"
              >
                成功 {{ successfulRunCount(panels[panelKey]) }}
              </Tag>
              <Tag v-if="failedRunCount(panels[panelKey]) > 0" color="error">
                失败 {{ failedRunCount(panels[panelKey]) }}
              </Tag>
            </Space>
            <Tooltip title="复制全部原始输出">
              <Button
                size="small"
                :icon="h(CopyOutlined)"
                :disabled="
                  !panels[panelKey].results.some((item) => item.content)
                "
                @click="copyAllResults(panels[panelKey])"
              />
            </Tooltip>
          </div>

          <div class="result-box">
            <div
              v-if="panels[panelKey].results.length > 0"
              class="batch-result-list"
            >
              <section
                v-for="result in panels[panelKey].results"
                :key="result.index"
                class="batch-result"
                :class="{ 'batch-result-error': result.error_message }"
              >
                <div class="batch-result-header">
                  <strong>第 {{ result.index + 1 }} 篇</strong>
                  <Space wrap size="small">
                    <Tag v-if="result.loading" color="processing">运行中</Tag>
                    <template v-else>
                      <Tag>{{ result.latency_ms ?? '-' }} ms</Tag>
                      <Tag>{{ tokenText(result.usage) }}</Tag>
                      <Tag>{{ modelMetaText(result, panels[panelKey]) }}</Tag>
                      <Tag v-if="result.articles.length > 0" color="blue">
                        JSON · 标题/正文
                      </Tag>
                      <Tooltip title="复制原始输出">
                        <Button
                          size="small"
                          :icon="h(CopyOutlined)"
                          :disabled="!result.content"
                          @click="copyText(result.content)"
                        />
                      </Tooltip>
                    </template>
                  </Space>
                </div>

                <div v-if="result.loading" class="batch-result-status">
                  等待模型返回...
                </div>
                <div
                  v-else-if="result.error_message"
                  class="batch-result-message"
                >
                  {{ result.error_message }}
                </div>
                <div
                  v-else-if="result.articles.length > 0"
                  class="article-result-list"
                >
                  <section
                    v-for="(article, articleIndex) in result.articles"
                    :key="articleIndex"
                    class="article-result"
                  >
                    <div
                      v-if="result.articles.length > 1"
                      class="article-result-index"
                    >
                      结果 {{ articleIndex + 1 }}
                    </div>
                    <div class="article-result-field">
                      <div class="article-result-label">标题</div>
                      <div class="article-result-title">
                        {{ article.title }}
                      </div>
                    </div>
                    <div class="article-result-field">
                      <div class="article-result-label">正文</div>
                      <div class="article-result-body">{{ article.body }}</div>
                    </div>
                  </section>
                </div>
                <div v-else-if="result.content" class="raw-result-content">
                  {{ result.content }}
                </div>
                <div v-else class="batch-result-status">模型未返回内容</div>
              </section>
            </div>
            <template v-else>等待运行</template>
          </div>
        </Card>
      </Col>
    </Row>

    <Drawer v-model:open="historyOpen" title="提示词调试历史" width="620">
      <div class="history-toolbar">
        <span>最近 {{ historyGroups.length }} 个执行组</span>
        <Button
          size="small"
          :icon="h(ReloadOutlined)"
          :loading="historyLoading"
          @click="loadHistory"
        >
          刷新
        </Button>
      </div>
      <div v-if="historyLoading && historyGroups.length === 0" class="history-empty">
        正在加载...
      </div>
      <div v-else-if="historyGroups.length === 0" class="history-empty">
        暂无调试历史
      </div>
      <div v-else class="history-list">
        <Card
          v-for="group in historyGroups"
          :key="group.run_group_id"
          size="small"
          class="history-card"
        >
          <div class="history-card-header">
            <Space wrap size="small">
              <strong>{{ formatHistoryTime(group.create_time) }}</strong>
              <Tag>{{ historyModeText(group.workbench_mode) }}</Tag>
              <Tag>共 {{ group.total_count }} 篇</Tag>
              <Tag color="success">成功 {{ group.success_count }}</Tag>
              <Tag v-if="group.failed_count > 0" color="error">
                失败 {{ group.failed_count }}
              </Tag>
            </Space>
            <Button
              size="small"
              type="primary"
              ghost
              :loading="restoringGroupId === group.run_group_id"
              @click="restoreHistory(group)"
            >
              载入
            </Button>
          </div>
          <div class="history-models">
            {{ group.model_codes.join(' / ') }}
          </div>
          <div class="history-prompt-preview">
            {{ group.prompt_preview || '无 Prompt 摘要' }}
          </div>
        </Card>
      </div>
    </Drawer>
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
  max-height: 620px;
  padding: 12px;
  overflow: auto;
  color: #111827;
  white-space: pre-wrap;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
}

.batch-result-list {
  display: grid;
  gap: 12px;
}

.batch-result {
  padding: 12px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
}

.batch-result-error {
  background: #fff7f7;
  border-color: #fecdd3;
}

.batch-result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 8px;
  margin-bottom: 10px;
  border-bottom: 1px solid #e2e8f0;
}

.batch-result-status {
  color: #64748b;
}

.batch-result-message {
  color: #991b1b;
}

.raw-result-content {
  line-height: 1.7;
}

.article-result-list {
  display: grid;
  gap: 12px;
}

.article-result {
  padding: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
}

.article-result-index {
  padding-bottom: 8px;
  margin-bottom: 10px;
  font-weight: 600;
  color: #475569;
  border-bottom: 1px solid #e2e8f0;
}

.article-result-field + .article-result-field {
  margin-top: 12px;
}

.article-result-label {
  margin-bottom: 4px;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
}

.article-result-title {
  font-size: 16px;
  font-weight: 600;
}

.article-result-body {
  line-height: 1.7;
}

.history-toolbar,
.history-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.history-toolbar {
  margin-bottom: 16px;
  color: #64748b;
}

.history-list {
  display: grid;
  gap: 12px;
}

.history-models {
  margin-top: 10px;
  font-size: 12px;
  color: #64748b;
}

.history-prompt-preview {
  margin-top: 6px;
  overflow: hidden;
  color: #334155;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-empty {
  padding: 48px 0;
  color: #94a3b8;
  text-align: center;
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
  }
}
</style>
