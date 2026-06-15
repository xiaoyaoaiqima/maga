<script setup lang="ts">
// @ts-nocheck
import type { ContentGenerationExpertApi } from '#/api/core/content-generation-experts';
import type { LLMApi } from '#/api/core/llm';

import { computed, onMounted, reactive, ref, watch } from 'vue';

import { useUserStore } from '@vben/stores';

import {
  EyeOutlined,
  ReloadOutlined,
  SaveOutlined,
} from '@ant-design/icons-vue';
import {
  Alert,
  AutoComplete,
  Button,
  Card,
  Col,
  Descriptions,
  DescriptionsItem,
  Divider,
  Empty,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Modal,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Textarea,
  Tooltip,
} from 'ant-design-vue';

import {
  getContentGenerationExpertsApi,
  previewContentGenerationExpertApi,
  saveContentGenerationExpertApi,
  updateBusinessForbiddenTermStatusApi,
} from '#/api/core/content-generation-experts';
import { getProviderListApi, getRouteListApi } from '#/api/core/llm';

const userStore = useUserStore();
const loading = ref(false);
const saving = ref(false);
const previewLoading = ref(false);
const forbiddenTermUpdating = ref('');
const activeCode = ref('');
const experts = ref<ContentGenerationExpertApi.Expert[]>([]);
const auditFlow = ref<ContentGenerationExpertApi.AuditFlow | null>(null);
const providers = ref<LLMApi.ProviderConfig[]>([]);
const modelRoutes = ref<LLMApi.ModelRoute[]>([]);
const previewVisible = ref(false);
const previewPrompt = ref('');

const formState = reactive({
  description: '',
  enabled: true,
  expert_config_name: '',
  max_tokens: undefined as number | undefined,
  model_code: '',
  provider_code: '',
  prompt_template: '',
  system_prompt: '',
  temperature: undefined as number | undefined,
});

const activeExpert = computed(() =>
  experts.value.find((item) => item.expert_config_code === activeCode.value),
);

const providerOptions = computed(() => {
  const options = providers.value.map((provider) => ({
    label: `${provider.provider_name} (${provider.provider_code})`,
    value: provider.provider_code,
  }));
  const knownCodes = new Set(options.map((item) => item.value));
  for (const route of modelRoutes.value) {
    if (!knownCodes.has(route.provider_code)) {
      options.push({ label: route.provider_code, value: route.provider_code });
      knownCodes.add(route.provider_code);
    }
  }
  for (const option of optionFromValue(formState.provider_code)) {
    if (!knownCodes.has(option.value)) options.push(option);
  }
  return options;
});

const filteredModelRoutes = computed(() => {
  const providerCode = formState.provider_code.trim();
  return [...modelRoutes.value]
    .filter((route) => !providerCode || route.provider_code === providerCode)
    .toSorted((a, b) => {
      if (a.enabled !== b.enabled) return a.enabled ? -1 : 1;
      return `${a.provider_code}:${a.model_code}`.localeCompare(
        `${b.provider_code}:${b.model_code}`,
      );
    });
});

const modelOptions = computed(() =>
  uniqueOptions([
    ...filteredModelRoutes.value.map((route) => ({
      label: `${route.model_name || route.model_code} (${route.model_code})${
        route.enabled ? '' : ' · 停用'
      }`,
      value: route.model_code,
    })),
    ...optionFromValue(formState.model_code),
  ]),
);

const selectedRoute = computed(() =>
  findRoute(formState.provider_code, formState.model_code),
);

const tableColumns: any[] = [
  { title: '阶段', dataIndex: 'stage', key: 'stage', width: 96 },
  { title: 'Expert', key: 'expert' },
  { title: '能力', dataIndex: 'capability', key: 'capability', width: 150 },
  { title: '模型', key: 'model', width: 170 },
  { title: '来源', key: 'source', width: 96 },
  { title: '状态', key: 'enabled', width: 86 },
];

const businessForbiddenTermColumns: any[] = [
  { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 132 },
  { title: '违禁词', dataIndex: 'term', key: 'term', width: 94 },
  { title: '违禁原因', dataIndex: 'reason', key: 'reason' },
  { title: '状态', key: 'enabled', width: 84 },
  { title: '来源', dataIndex: 'source', key: 'source', width: 118 },
];

const operator = computed(
  () =>
    userStore.userInfo?.realName ||
    userStore.userInfo?.username ||
    'maga-operator',
);

function sourceColor(source: string) {
  return source === 'expert_config' ? 'green' : 'orange';
}

function sourceLabel(source: string) {
  return source === 'expert_config' ? '已保存' : '默认配置';
}

function formatTermTime(value?: string) {
  if (!value) return '-';
  return value.replace('T', ' ').replace(/\.\d+.*$/, '').replace(/\+00:00$/, '');
}

async function toggleBusinessForbiddenTerm(
  record: ContentGenerationExpertApi.BusinessForbiddenTermEntry,
  enabled: boolean,
) {
  forbiddenTermUpdating.value = record.term;
  try {
    await updateBusinessForbiddenTermStatusApi({
      asset_key: record.asset_key || 'a2_sentiment_comment_activity',
      enabled,
      term: record.term,
      updated_by: operator.value,
    });
    await loadExperts();
    message.success(enabled ? '已启用业务违禁词' : '已停用业务违禁词');
  } catch (error: any) {
    message.error(error?.message || '更新业务违禁词失败');
  } finally {
    forbiddenTermUpdating.value = '';
  }
}

function optionFromValue(value: string) {
  return value ? [{ label: value, value }] : [];
}

function uniqueOptions<T extends { value: string }>(options: T[]) {
  const seen = new Set<string>();
  return options.filter((item) => {
    if (!item.value || seen.has(item.value)) return false;
    seen.add(item.value);
    return true;
  });
}

function findRoute(providerCode: string, modelCode: string) {
  const normalizedModel = modelCode.trim();
  if (!normalizedModel) return null;
  const normalizedProvider = providerCode.trim();
  if (normalizedProvider) {
    return (
      modelRoutes.value.find(
        (route) =>
          route.provider_code === normalizedProvider &&
          route.model_code === normalizedModel,
      ) || null
    );
  }
  const matches = modelRoutes.value.filter(
    (route) => route.model_code === normalizedModel,
  );
  return matches.length === 1 ? matches[0] : null;
}

function getExpertProvider(expert: ContentGenerationExpertApi.Expert) {
  return (
    expert.model_config?.provider_code || expert.model_config?.provider || ''
  );
}

function getExpertModel(expert: ContentGenerationExpertApi.Expert) {
  return expert.model_code || expert.model_config?.model_code || '';
}

function getExpertRoute(expert: ContentGenerationExpertApi.Expert) {
  return findRoute(getExpertProvider(expert), getExpertModel(expert));
}

function routeStatusColor(route?: LLMApi.ModelRoute | null) {
  if (!route) return 'red';
  return route.enabled ? 'green' : 'orange';
}

function routeStatusText(route?: LLMApi.ModelRoute | null) {
  if (!route) return '未匹配路由';
  return route.enabled ? '路由启用' : '路由停用';
}

function formatRouteCost(route?: LLMApi.ModelRoute | null) {
  if (!route?.cost_per_1k_input && !route?.cost_per_1k_output) {
    return '成本未配置';
  }
  const symbol = route.currency === 'CNY' ? '¥' : '$';
  const input = route.cost_per_1k_input
    ? `${symbol}${route.cost_per_1k_input}`
    : '-';
  const output = route.cost_per_1k_output
    ? `${symbol}${route.cost_per_1k_output}`
    : '-';
  return `${input} / ${output}`;
}

function handleProviderChange() {
  if (!formState.provider_code || !formState.model_code) return;
  if (!findRoute(formState.provider_code, formState.model_code)) {
    formState.model_code = '';
  }
}

function handleModelSelect(modelCode: string) {
  if (formState.provider_code || !modelCode) return;
  const matches = modelRoutes.value.filter(
    (route) => route.model_code === modelCode && route.enabled,
  );
  if (matches.length === 1) {
    formState.provider_code = matches[0].provider_code;
  }
}

function loadExpertToForm(expert?: ContentGenerationExpertApi.Expert) {
  if (!expert) return;
  const config = expert.model_config || {};
  Object.assign(formState, {
    description: expert.description || '',
    enabled: expert.enabled,
    expert_config_name: expert.expert_config_name,
    max_tokens: config.max_tokens ?? undefined,
    model_code: expert.model_code || config.model_code || '',
    provider_code: config.provider_code || config.provider || '',
    prompt_template: expert.prompt_template || '',
    system_prompt: config.system_prompt || '',
    temperature: config.temperature ?? undefined,
  });
}

function buildPayload(): ContentGenerationExpertApi.ExpertUpsertRequest {
  const modelConfig: Record<string, any> = {};
  if (formState.provider_code)
    modelConfig.provider_code = formState.provider_code;
  if (formState.temperature !== undefined)
    modelConfig.temperature = formState.temperature;
  if (formState.max_tokens !== undefined)
    modelConfig.max_tokens = formState.max_tokens;
  if (formState.system_prompt)
    modelConfig.system_prompt = formState.system_prompt;
  return {
    description: formState.description,
    enabled: formState.enabled,
    expert_config_name: formState.expert_config_name,
    model_code: formState.model_code || null,
    model_config: modelConfig,
    prompt_template: formState.prompt_template,
    updated_by: operator.value,
  };
}

async function loadExperts() {
  loading.value = true;
  try {
    const [expertResult, providerResult, routeResult] = await Promise.all([
      getContentGenerationExpertsApi(),
      getProviderListApi({ limit: 1000 }).catch(() => ({ items: [] })),
      getRouteListApi({ limit: 1000 }).catch(() => ({ items: [] })),
    ]);
    experts.value = expertResult.items || [];
    auditFlow.value = expertResult.audit_flow;
    providers.value = providerResult.items || [];
    modelRoutes.value = routeResult.items || [];
    activeCode.value =
      activeCode.value || experts.value[0]?.expert_config_code || '';
    loadExpertToForm(activeExpert.value);
  } catch {
    message.error('获取生文 Expert 失败');
  } finally {
    loading.value = false;
  }
}

async function handleSave() {
  const expert = activeExpert.value;
  if (!expert) return;
  if (!formState.expert_config_name.trim()) {
    message.warning('请输入 Expert 名称');
    return;
  }
  if (!formState.prompt_template.trim()) {
    message.warning('请输入 Prompt 模板');
    return;
  }
  if (!formState.provider_code || !formState.model_code) {
    message.warning('请选择 Provider 和模型路由');
    return;
  }
  if (!selectedRoute.value) {
    message.warning('当前 Provider 和模型没有匹配的模型路由');
    return;
  }
  if (!selectedRoute.value.enabled) {
    message.warning('当前模型路由已停用，请先启用后再保存');
    return;
  }
  saving.value = true;
  try {
    const saved = await saveContentGenerationExpertApi(
      expert.expert_config_code,
      buildPayload(),
    );
    const index = experts.value.findIndex(
      (item) => item.expert_config_code === saved.expert_config_code,
    );
    if (index !== -1) experts.value[index] = saved;
    loadExpertToForm(saved);
    message.success('已保存');
  } catch (error: any) {
    message.error(error?.message || '保存失败');
  } finally {
    saving.value = false;
  }
}

async function handlePreview() {
  const expert = activeExpert.value;
  if (!expert) return;
  previewLoading.value = true;
  try {
    const result = await previewContentGenerationExpertApi(
      expert.expert_config_code,
      {
        business_rule: {
          product_topic: '美素佳儿源悦活动',
          rule_type: expert.content_type.includes('comment')
            ? 'business_rule'
            : 'product_experience',
        },
        content_type:
          expert.content_type === 'article,comment'
            ? 'article'
            : expert.content_type,
        forbidden_hits: ['示例违禁词'],
        previous_content: {
          body: '这里是一段需要审核改写的示例正文。',
          title: '示例标题',
        },
        selected_keywords: [
          {
            category_name: '人设',
            corpus: ['像有真实带娃经验的妈妈表达，语气自然。'],
            keyword_name: '经验型妈妈',
          },
        ],
      },
    );
    previewPrompt.value = result.rendered_prompt;
    previewVisible.value = true;
  } catch (error: any) {
    message.error(error?.message || '预览失败');
  } finally {
    previewLoading.value = false;
  }
}

watch(activeExpert, (expert) => loadExpertToForm(expert));

onMounted(loadExperts);
</script>

<template>
  <div class="content-flow-experts">
    <div class="page-header">
      <div>
        <h1>生文 Expert</h1>
        <p>统一内容生成链路里的 Prompt 模板和模型参数。</p>
      </div>
      <Space>
        <Button :loading="loading" @click="loadExperts">
          <template #icon><ReloadOutlined /></template>
          刷新
        </Button>
        <Button
          type="primary"
          :loading="saving"
          :disabled="!activeExpert"
          @click="handleSave"
        >
          <template #icon><SaveOutlined /></template>
          保存配置
        </Button>
      </Space>
    </div>

    <Row :gutter="16">
      <Col :span="9">
        <Card class="flow-card" title="执行节点">
          <Table
            row-key="expert_config_code"
            :columns="tableColumns"
            :data-source="experts"
            :loading="loading"
            :pagination="false"
            size="small"
            :custom-row="
              (record) => ({
                class:
                  record.expert_config_code === activeCode ? 'active-row' : '',
                onClick: () => {
                  activeCode = record.expert_config_code;
                },
              })
            "
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'expert'">
                <div class="expert-name">{{ record.expert_config_name }}</div>
                <div class="expert-code">{{ record.expert_config_code }}</div>
              </template>
              <template v-else-if="column.key === 'model'">
                <div class="route-cell">
                  <div>{{ getExpertModel(record) || '-' }}</div>
                  <div class="route-meta">
                    {{ getExpertProvider(record) || '-' }}
                    <Tag :color="routeStatusColor(getExpertRoute(record))">
                      {{ routeStatusText(getExpertRoute(record)) }}
                    </Tag>
                  </div>
                </div>
              </template>
              <template v-else-if="column.key === 'source'">
                <Tag :color="sourceColor(record.source)">
                  {{ sourceLabel(record.source) }}
                </Tag>
              </template>
              <template v-else-if="column.key === 'enabled'">
                <Tag :color="record.enabled ? 'green' : 'red'">
                  {{ record.enabled ? '启用' : '停用' }}
                </Tag>
              </template>
            </template>
          </Table>
        </Card>

        <Card class="flow-card audit-card" title="审核流程">
          <Descriptions v-if="auditFlow" size="small" :column="1">
            <DescriptionsItem label="审核闸口">
              {{ auditFlow.source }}
            </DescriptionsItem>
            <DescriptionsItem label="改写能力">
              {{ auditFlow.rewrite_capability }}
            </DescriptionsItem>
            <DescriptionsItem label="最多改写">
              {{ auditFlow.max_rewrite_rounds }} 轮
            </DescriptionsItem>
          </Descriptions>
          <Divider />
          <div class="term-block">
            <div class="term-title">系统违禁词</div>
            <Space wrap>
              <Tag
                v-for="term in auditFlow?.static_forbidden_terms || []"
                :key="term"
                color="red"
              >
                {{ term }}
              </Tag>
            </Space>
          </div>
          <div class="term-block">
            <div class="term-title">业务违禁词</div>
            <Table
              v-if="auditFlow?.business_forbidden_term_entries?.length"
              row-key="term"
              :columns="businessForbiddenTermColumns"
              :data-source="auditFlow.business_forbidden_term_entries"
              :pagination="false"
              size="small"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'created_at'">
                  {{ formatTermTime(record.created_at) }}
                </template>
                <template v-else-if="column.key === 'term'">
                  <Tag color="volcano">{{ record.term }}</Tag>
                </template>
                <template v-else-if="column.key === 'reason'">
                  {{ record.reason || '-' }}
                </template>
                <template v-else-if="column.key === 'enabled'">
                  <Switch
                    size="small"
                    :checked="record.enabled"
                    :loading="forbiddenTermUpdating === record.term"
                    @change="
                      (checked) =>
                        toggleBusinessForbiddenTerm(record, Boolean(checked))
                    "
                  />
                </template>
                <template v-else-if="column.key === 'source'">
                  {{ record.source || '-' }}
                </template>
              </template>
            </Table>
            <Empty v-else image="simple" description="暂无业务违禁词" />
          </div>
        </Card>
      </Col>

      <Col :span="15">
        <Card v-if="activeExpert" class="flow-card editor-card">
          <template #title>
            <Space>
              <span>{{ activeExpert.stage }}</span>
              <Tag>{{ activeExpert.capability }}</Tag>
              <Tag>{{ activeExpert.content_type }}</Tag>
            </Space>
          </template>
          <template #extra>
            <Tooltip title="预览当前模板变量渲染结果">
              <Button :loading="previewLoading" @click="handlePreview">
                <template #icon><EyeOutlined /></template>
                预览
              </Button>
            </Tooltip>
          </template>

          <Alert
            v-if="activeExpert.source === 'fallback'"
            class="fallback-alert"
            type="warning"
            show-icon
            message="当前使用默认配置，保存后会写入正式 ExpertConfig。"
          />

          <Form layout="vertical">
            <Row :gutter="12">
              <Col :span="16">
                <FormItem label="Expert 名称">
                  <Input v-model:value="formState.expert_config_name" />
                </FormItem>
              </Col>
              <Col :span="8">
                <FormItem label="启用">
                  <Switch v-model:checked="formState.enabled" />
                </FormItem>
              </Col>
            </Row>
            <FormItem label="说明">
              <Input v-model:value="formState.description" />
            </FormItem>

            <Row :gutter="12">
              <Col :span="12">
                <FormItem label="Provider">
                  <Select
                    v-model:value="formState.provider_code"
                    allow-clear
                    show-search
                    placeholder="选择 provider_code"
                    :options="providerOptions"
                    @change="handleProviderChange"
                  />
                </FormItem>
              </Col>
              <Col :span="12">
                <FormItem label="模型路由">
                  <AutoComplete
                    v-model:value="formState.model_code"
                    allow-clear
                    placeholder="选择或输入 model_code"
                    :options="modelOptions"
                    @select="handleModelSelect"
                  />
                </FormItem>
              </Col>
            </Row>

            <div
              v-if="
                selectedRoute ||
                (formState.provider_code && formState.model_code)
              "
              class="route-hint"
            >
              <template v-if="selectedRoute">
                <Tag :color="routeStatusColor(selectedRoute)">
                  {{ routeStatusText(selectedRoute) }}
                </Tag>
                <span>{{ selectedRoute.provider_code }}</span>
                <span>{{ selectedRoute.provider_model }}</span>
                <span>优先级 {{ selectedRoute.priority }}</span>
                <span>{{ formatRouteCost(selectedRoute) }}</span>
              </template>
              <template v-else>
                <Tag color="red">未匹配路由</Tag>
                <span>请先在模型配置里为当前 Provider 生成或启用模型路由</span>
              </template>
            </div>

            <Row :gutter="12">
              <Col :span="8">
                <FormItem label="Temperature">
                  <InputNumber
                    v-model:value="formState.temperature"
                    :min="0"
                    :max="2"
                    :step="0.05"
                    class="full-width"
                  />
                </FormItem>
              </Col>
              <Col :span="8">
                <FormItem label="Max Tokens">
                  <InputNumber
                    v-model:value="formState.max_tokens"
                    :min="1"
                    :step="100"
                    class="full-width"
                  />
                </FormItem>
              </Col>
              <Col :span="8">
                <FormItem label="变量">
                  <Space wrap>
                    <Tag
                      v-for="variable in activeExpert.variables"
                      :key="variable"
                    >
                      {{ variable }}
                    </Tag>
                  </Space>
                </FormItem>
              </Col>
            </Row>

            <FormItem label="System Prompt">
              <Textarea
                v-model:value="formState.system_prompt"
                :auto-size="{ minRows: 2, maxRows: 4 }"
              />
            </FormItem>

            <FormItem label="Prompt 模板">
              <Textarea
                v-model:value="formState.prompt_template"
                class="prompt-template"
                :auto-size="{ minRows: 14, maxRows: 26 }"
              />
            </FormItem>
          </Form>
        </Card>
      </Col>
    </Row>

    <Modal
      v-model:open="previewVisible"
      title="Prompt 预览"
      width="860px"
      :footer="null"
    >
      <pre class="preview-box">{{ previewPrompt }}</pre>
    </Modal>
  </div>
</template>

<style scoped>
.content-flow-experts {
  padding: 18px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.page-header h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 650;
}

.page-header p {
  margin: 6px 0 0;
  color: #5d667a;
}

.flow-card {
  margin-bottom: 16px;
  border-radius: 8px;
}

.expert-name {
  font-weight: 600;
  color: #202735;
}

.expert-code {
  margin-top: 2px;
  font-size: 12px;
  color: #6b7280;
}

.route-cell {
  line-height: 1.45;
}

.route-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
  font-size: 12px;
  color: #6b7280;
}

:deep(.active-row td) {
  background: #eef6ff !important;
}

:deep(.ant-table-row) {
  cursor: pointer;
}

.fallback-alert {
  margin-bottom: 16px;
}

.route-hint {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  padding: 8px 10px;
  margin: -2px 0 14px;
  font-size: 12px;
  color: #5d667a;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
}

.full-width {
  width: 100%;
}

.prompt-template {
  font-family:
    ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono',
    monospace;
}

.term-block + .term-block {
  margin-top: 16px;
}

.term-title {
  margin-bottom: 8px;
  font-weight: 600;
  color: #2e3442;
}

.preview-box {
  max-height: 620px;
  padding: 14px;
  overflow: auto;
  white-space: pre-wrap;
  background: #f6f8fb;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}
</style>
