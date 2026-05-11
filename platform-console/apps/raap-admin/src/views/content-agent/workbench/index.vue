<script setup lang="ts">
import type { ContentAgentApi } from '#/api/core/content-agent';

import { computed, h, onMounted, reactive, ref } from 'vue';

import * as Antd from 'ant-design-vue';

import {
  getContentBatchListApi,
  getContentBatchReportApi,
  getTrainingFeedbackSamplesApi,
  startContentBatchApi,
  startContentGenerationApi,
  submitBatchItemFeedbackApi,
} from '#/api/core/content-agent';

const {
  Alert,
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
  List,
  ListItem,
  message,
  Modal,
  Radio,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Tag,
  Tabs,
} = Antd as any;
const { TextArea } = Input as any;
const { Group: RadioGroup, Button: RadioButton } = Radio as any;
const { Option: SelectOption } = Select as any;
const { TabPane } = Tabs as any;

type GenerationMode = 'batch' | 'single';
type WorkspaceTab = 'generation' | 'training';

const activeWorkspaceTab = ref<WorkspaceTab>('generation');
const generationMode = ref<GenerationMode>('batch');
const generating = ref(false);
const batchLoading = ref(false);
const reportLoading = ref(false);
const selectedReport = ref<ContentAgentApi.BatchReport | null>(null);
const singleResult = ref<ContentAgentApi.StartGenerationResponse | null>(null);
const batchList = ref<ContentAgentApi.BatchListItem[]>([]);
const batchTotal = ref(0);
const trainingFeedbackLoading = ref(false);
const trainingFeedbackSamples = ref<ContentAgentApi.TrainingFeedbackSample[]>(
  [],
);
const trainingFeedbackTotal = ref(0);

const formState = reactive({
  asset_key: 'yuanyue',
  product_topic: '宝宝便便不规律',
  target_audience: '新手妈妈',
  style: '经验老道型',
  count: 5,
  executor_code: 'hermes_maga_worker',
  created_by: 'ops',
});

const selectedItems = computed(() => selectedReport.value?.items || []);
const selectedSummary = computed(() => selectedReport.value?.summary || null);
const trainingItems = computed(() =>
  selectedItems.value.filter(
    (item) =>
      item.review_status ||
      item.human_feedback_text ||
      item.feedback_count ||
      item.similarity_warnings?.length ||
      item.reject_reasons?.length ||
      item.hard_pass === false ||
      item.rewrite_required,
  ),
);
const trainingSummary = computed(() => {
  const items = selectedItems.value;
  return {
    approved_count: items.filter((item) => item.review_status === 'approved')
      .length,
    feedback_count: selectedSummary.value?.feedback_count || 0,
    manual_edited_count: items.filter(
      (item) => item.review_status === 'manual_edited',
    ).length,
    needs_revision_count: items.filter(
      (item) => item.review_status === 'needs_revision',
    ).length,
    reject_reason_count: items.reduce(
      (total, item) => total + (item.reject_reasons?.length || 0),
      0,
    ),
    similarity_warning_count: items.filter(
      (item) => item.similarity_warnings?.length,
    ).length,
  };
});

const statusColor = (status?: string) => {
  if (status === 'approved') return 'green';
  if (status === 'manual_edited') return 'purple';
  if (status === 'needs_revision') return 'orange';
  if (status === 'generated') return 'green';
  if (status === 'failed') return 'red';
  if (status === 'running') return 'blue';
  if (status === 'partially_generated') return 'orange';
  if (status === 'planned') return 'default';
  return 'default';
};

const passColor = (value?: boolean | null) => {
  if (value === true) return 'green';
  if (value === false) return 'red';
  return 'default';
};

const feedbackDrafts = reactive<Record<number, string>>({});
const reviewingItemId = ref<null | number>(null);

const reviewStatusLabel = (status?: null | string) => {
  if (status === 'approved') return '已通过';
  if (status === 'needs_revision') return '待修改';
  if (status === 'manual_edited') return '人工编辑';
  return status || '未审核';
};

const formatDuration = (durationMs?: null | number) => {
  if (durationMs === null || durationMs === undefined) return '-';
  if (durationMs < 1000) return `${durationMs}ms`;
  return `${(durationMs / 1000).toFixed(durationMs < 10_000 ? 2 : 1)}s`;
};

const rejectSourceLabel = (source?: string) => {
  if (source === 'hard_review') return '硬性审核';
  if (source === 'failed_ae') return 'AE 审核';
  if (source === 'forbidden_term') return '禁用词';
  if (source === 'executor_error') return '执行失败';
  return source || '审核';
};

const actionLabel = (action?: string) => {
  if (action === 'approve') return '通过';
  if (action === 'manual_edit') return '人工改写';
  if (action === 'request_revision') return '要求修改';
  return action || '-';
};

const traceLines = (item: ContentAgentApi.BatchReportItem) => [
  `run_id: ${item.trace_run_id || item.run_id || '-'}`,
  `task_id: ${item.task_id || '-'}`,
  '',
  ...(item.trace_stage_calls || []).map((stage) =>
    `#${stage.sequence_no} ${stage.capability} ${stage.status} ${formatDuration(
      stage.duration_ms,
    )} ${stage.stage_call_id}`.trim(),
  ),
];

const feedbackDigestLines = computed(() => {
  if (!selectedReport.value) return [];
  return [
    `batch_id: ${selectedReport.value.batch_id}`,
    `asset_key: ${selectedReport.value.asset_key}`,
    `product_topic: ${selectedReport.value.product_topic}`,
    `target_audience: ${selectedReport.value.target_audience || '-'}`,
    `style: ${selectedReport.value.style || '-'}`,
    '',
    ...trainingItems.value.flatMap((item) => [
      `#${item.item_no} ${item.title || '未生成标题'}`,
      `review_status: ${reviewStatusLabel(item.review_status)}`,
      `hard_pass: ${
        item.hard_pass === true ? 'pass' : item.hard_pass === false ? 'fail' : '-'
      }`,
      `reject_reasons: ${
        item.reject_reasons?.length
          ? item.reject_reasons.map((reason) => reason.message).join('；')
          : '-'
      }`,
      `similarity_warnings: ${
        item.similarity_warnings?.length
          ? item.similarity_warnings
              .map(
                (warning) =>
                  `与第${warning.item_no}篇相似度 ${Math.round(
                    warning.score * 100,
                  )}%`,
              )
              .join('；')
          : '-'
      }`,
      `human_feedback: ${item.human_feedback_text || '-'}`,
      `runtime: ${item.runtime_mode || '-'} / generation ${formatDuration(
        item.generation_duration_ms,
      )}`,
      '',
    ]),
  ];
});

const showTrace = (item: ContentAgentApi.BatchReportItem) => {
  Modal.info({
    title: `第 ${item.item_no} 篇执行 Trace`,
    width: 820,
    content: h('div', { class: 'trace-modal' }, [
      h(
        Button,
        {
          size: 'small',
          onClick: () => copyText(traceLines(item).join('\n')),
        },
        () => '复制 Trace',
      ),
      h('p', `Run ID：${item.trace_run_id || item.run_id || '-'}`),
      h('p', `Task ID：${item.task_id || '-'}`),
      h(
        'p',
        `总耗时：${formatDuration(item.total_duration_ms)}；生文耗时：${formatDuration(
          item.generation_duration_ms,
        )}`,
      ),
      h(
        'div',
        { class: 'trace-modal-stages' },
        (item.trace_stage_calls || []).map((stage) =>
          h('div', { class: 'trace-modal-stage' }, [
            h(
              'strong',
              `#${stage.sequence_no} ${stage.capability} · ${stage.status}`,
            ),
            h('span', `耗时 ${formatDuration(stage.duration_ms)}`),
            h('code', stage.stage_call_id),
            stage.error_message
              ? h('span', `错误：${stage.error_message}`)
              : null,
          ]),
        ),
      ),
    ]),
    okText: '关闭',
  });
};

const feedbackActionLabel = (
  action: ContentAgentApi.BatchItemFeedbackAction,
) => {
  if (action === 'approve') return '通过';
  if (action === 'manual_edit') return '人工编辑保存';
  return '提交修改意见';
};

const loadBatches = async () => {
  batchLoading.value = true;
  try {
    const data = await getContentBatchListApi({ limit: 20, offset: 0 });
    batchList.value = data?.items || [];
    batchTotal.value = data?.total || 0;
    if (!selectedReport.value && batchList.value[0]) {
      await openReport(batchList.value[0].batch_id, false);
    }
  } finally {
    batchLoading.value = false;
  }
};

const loadTrainingFeedbackSamples = async () => {
  trainingFeedbackLoading.value = true;
  try {
    const data = await getTrainingFeedbackSamplesApi({ limit: 30, offset: 0 });
    trainingFeedbackSamples.value = data?.items || [];
    trainingFeedbackTotal.value = data?.total || 0;
  } finally {
    trainingFeedbackLoading.value = false;
  }
};

const copyFeedbackDigest = async () => {
  if (!trainingItems.value.length) {
    message.warning('当前批次暂无可复制的反馈摘要');
    return;
  }
  await copyText(feedbackDigestLines.value.join('\n'));
};

const openReport = async (batchId: number, showLoading = true) => {
  if (showLoading) reportLoading.value = true;
  try {
    selectedReport.value = await getContentBatchReportApi(batchId);
    singleResult.value = null;
  } finally {
    if (showLoading) reportLoading.value = false;
  }
};

const normalizeExecutorCode = (executorCode?: string) =>
  executorCode?.trim() || 'hermes_maga_worker';

const handleGenerate = async () => {
  if (!formState.product_topic.trim()) {
    message.warning('请先填写产品/主题');
    return;
  }
  generating.value = true;
  try {
    if (generationMode.value === 'single') {
      singleResult.value = await startContentGenerationApi({
        product_topic: formState.product_topic,
        target_audience: formState.target_audience,
        style: formState.style,
        executor_code: normalizeExecutorCode(formState.executor_code),
        created_by: formState.created_by,
      });
      selectedReport.value = null;
      message.success('单篇生成完成');
      return;
    }

    const result = await startContentBatchApi({
      asset_key: formState.asset_key,
      product_topic: formState.product_topic,
      target_audience: formState.target_audience,
      style: formState.style,
      count: formState.count,
      executor_code: normalizeExecutorCode(formState.executor_code),
      created_by: formState.created_by,
    });
    selectedReport.value = result.report;
    singleResult.value = null;
    message.success(
      `批量生成完成：${result.execution.generated_count}/${result.execution.requested_limit} 篇`,
    );
    await loadBatches();
  } finally {
    generating.value = false;
  }
};

const copyText = async (text?: null | string) => {
  if (!text) return;
  await navigator.clipboard.writeText(text);
  message.success('已复制');
};

const copyArticle = async (item: ContentAgentApi.BatchReportItem) => {
  await copyText(`${item.title || ''}\n\n${item.body || ''}`.trim());
};

const showQuality = (item: ContentAgentApi.BatchReportItem) => {
  Modal.info({
    title: `第 ${item.item_no} 篇质量报告`,
    width: 760,
    content: JSON.stringify(item.quality || {}, null, 2),
  });
};

const replaceReportItem = (updated: ContentAgentApi.BatchReportItem) => {
  if (!selectedReport.value) return;
  selectedReport.value.items = selectedReport.value.items.map((item) =>
    item.item_id === updated.item_id ? updated : item,
  );
};

const submitFeedback = async (
  item: ContentAgentApi.BatchReportItem,
  action: ContentAgentApi.BatchItemFeedbackAction,
) => {
  const feedbackText = feedbackDrafts[item.item_id] || '';
  if (action === 'request_revision' && !feedbackText.trim()) {
    message.warning('请先填写修改意见');
    return;
  }

  reviewingItemId.value = item.item_id;
  try {
    const response = await submitBatchItemFeedbackApi(item.item_id, {
      action,
      title: item.title,
      body: item.body,
      feedback_text:
        feedbackText || (action === 'approve' ? '可发布' : undefined),
      created_by: formState.created_by,
    });
    replaceReportItem(response.item);
    if (selectedReport.value) {
      selectedReport.value = await getContentBatchReportApi(
        selectedReport.value.batch_id,
      );
    }
    message.success(`${feedbackActionLabel(action)}已保存`);
  } finally {
    reviewingItemId.value = null;
  }
};

const openManualEdit = (item: ContentAgentApi.BatchReportItem) => {
  const state = reactive({
    title: item.title || '',
    body: item.body || '',
    feedback_text: feedbackDrafts[item.item_id] || '运营人工编辑保存',
  });
  Modal.confirm({
    title: `人工编辑第 ${item.item_no} 篇`,
    width: 820,
    content: () =>
      h('div', { class: 'manual-edit-modal' }, [
        h(Input, {
          value: state.title,
          placeholder: '标题',
          'onUpdate:value': (value: string) => {
            state.title = value;
          },
        }),
        h(TextArea, {
          value: state.body,
          placeholder: '正文',
          rows: 12,
          style: 'margin-top: 12px',
          'onUpdate:value': (value: string) => {
            state.body = value;
          },
        }),
        h(TextArea, {
          value: state.feedback_text,
          placeholder: '编辑说明',
          rows: 2,
          style: 'margin-top: 12px',
          'onUpdate:value': (value: string) => {
            state.feedback_text = value;
          },
        }),
      ]),
    async onOk() {
      if (!state.title.trim() || !state.body.trim()) {
        message.warning('标题和正文不能为空');
        return Promise.reject(new Error('empty manual edit'));
      }
      reviewingItemId.value = item.item_id;
      try {
        const response = await submitBatchItemFeedbackApi(item.item_id, {
          action: 'manual_edit',
          title: state.title,
          body: state.body,
          feedback_text: state.feedback_text,
          created_by: formState.created_by,
        });
        replaceReportItem(response.item);
        if (selectedReport.value) {
          selectedReport.value = await getContentBatchReportApi(
            selectedReport.value.batch_id,
          );
        }
        message.success('人工编辑已保存');
      } finally {
        reviewingItemId.value = null;
      }
    },
  });
};

onMounted(() => {
  loadBatches();
  loadTrainingFeedbackSamples();
});
</script>

<template>
  <div class="content-agent-workbench p-4">
    <Row :gutter="16">
      <Col :lg="8" :xs="24">
        <Card title="新内容生成" :bordered="false">
          <Alert
            class="mb-4"
            message="第一版工作台：运营填写 4 个字段，MAGA 调用 maga-worker 生成并返回批次报告。"
            show-icon
            type="info"
          />

          <Form layout="vertical">
            <FormItem label="生成模式">
              <RadioGroup v-model:value="generationMode" button-style="solid">
                <RadioButton value="batch">批量生成</RadioButton>
                <RadioButton value="single">单篇快速生成</RadioButton>
              </RadioGroup>
            </FormItem>
            <FormItem label="资产键 asset_key">
              <Select v-model:value="formState.asset_key">
                <SelectOption value="yuanyue">yuanyue / 源悦</SelectOption>
              </Select>
            </FormItem>
            <FormItem label="产品/主题 product_topic" required>
              <Input
                v-model:value="formState.product_topic"
                placeholder="例如：宝宝便便不规律"
              />
            </FormItem>
            <FormItem label="目标人群 target_audience">
              <Input
                v-model:value="formState.target_audience"
                placeholder="例如：新手妈妈"
              />
            </FormItem>
            <FormItem label="风格 style">
              <Input
                v-model:value="formState.style"
                placeholder="例如：经验老道型 / 情绪共情"
              />
            </FormItem>
            <FormItem v-if="generationMode === 'batch'" label="生成篇数 count">
              <InputNumber
                v-model:value="formState.count"
                :max="20"
                :min="1"
                class="w-full"
              />
            </FormItem>
            <FormItem label="执行器 executor_code">
              <Input
                v-model:value="formState.executor_code"
                placeholder="默认 hermes_maga_worker；留空也会使用默认执行器"
              />
            </FormItem>
            <Button
              block
              type="primary"
              :loading="generating"
              @click="handleGenerate"
            >
              {{
                generationMode === 'batch' ? '生成批次并查看报告' : '生成单篇'
              }}
            </Button>
          </Form>
        </Card>

        <Card class="mt-4" :bordered="false" title="历史批次">
          <template #extra>
            <Button size="small" @click="loadBatches">刷新</Button>
          </template>
          <Spin :spinning="batchLoading">
            <Empty v-if="batchList.length === 0" description="暂无批次" />
            <div v-else class="batch-list">
              <div
                v-for="batch in batchList"
                :key="batch.batch_id"
                class="batch-list-item"
                :class="{ active: selectedReport?.batch_id === batch.batch_id }"
                @click="openReport(batch.batch_id)"
              >
                <div class="batch-title">
                  <span>{{ batch.product_topic }}</span>
                  <Tag :color="statusColor(batch.status)">
                    {{ batch.status }}
                  </Tag>
                </div>
                <div class="batch-meta">
                  #{{ batch.batch_id }} · {{ batch.batch_code || '-' }}
                </div>
                <div class="batch-meta">
                  {{ batch.summary.generated_count }}/{{
                    batch.summary.total_count
                  }}
                  篇 · 红线通过 {{ batch.summary.hard_pass_count }} · 改写
                  {{ batch.summary.rewrite_item_count }}
                </div>
              </div>
            </div>
            <div v-if="batchTotal" class="batch-total">
              共 {{ batchTotal }} 个批次
            </div>
          </Spin>
        </Card>
      </Col>

      <Col :lg="16" :xs="24">
        <Spin :spinning="reportLoading">
          <Card v-if="singleResult" title="单篇生成结果" :bordered="false">
            <template #extra>
              <Button
                size="small"
                @click="
                  copyText(`${singleResult.title}\n\n${singleResult.body}`)
                "
              >
                复制全文
              </Button>
            </template>
            <h2>{{ singleResult.title }}</h2>
            <div class="article-body">{{ singleResult.body }}</div>
          </Card>

          <Card v-else-if="selectedReport" :bordered="false">
            <template #title>
              <Space>
                <span>批次报告</span>
                <Tag>
                  {{
                    selectedReport.batch_code || `#${selectedReport.batch_id}`
                  }}
                </Tag>
                <Tag :color="statusColor(selectedReport.status)">
                  {{ selectedReport.status }}
                </Tag>
              </Space>
            </template>
            <template #extra>
              <Space>
                <Button size="small" @click="loadBatches">刷新历史</Button>
                <Button
                  size="small"
                  @click="openReport(selectedReport.batch_id)"
                >
                  刷新报告
                </Button>
              </Space>
            </template>

            <Tabs v-model:active-key="activeWorkspaceTab" class="workspace-tabs">
              <TabPane key="generation" tab="实际产文">
                <Descriptions :column="2" size="small" bordered>
                  <DescriptionsItem label="主题">
                    {{ selectedReport.product_topic }}
                  </DescriptionsItem>
                  <DescriptionsItem label="人群">
                    {{ selectedReport.target_audience || '-' }}
                  </DescriptionsItem>
                  <DescriptionsItem label="风格">
                    {{ selectedReport.style || '-' }}
                  </DescriptionsItem>
                  <DescriptionsItem label="资产键">
                    {{ selectedReport.asset_key }}
                  </DescriptionsItem>
                </Descriptions>

                <Row v-if="selectedSummary" class="mt-4" :gutter="12">
                  <Col :span="4">
                    <Statistic
                      title="总篇数"
                      :value="selectedSummary.total_count"
                    />
                  </Col>
                  <Col :span="4">
                    <Statistic
                      title="已生成"
                      :value="selectedSummary.generated_count"
                    />
                  </Col>
                  <Col :span="4">
                    <Statistic
                      title="红线通过"
                      :value="selectedSummary.hard_pass_count"
                    />
                  </Col>
                  <Col :span="4">
                    <Statistic
                      title="自动改写"
                      :value="selectedSummary.rewrite_item_count"
                    />
                  </Col>
                  <Col :span="4">
                    <Statistic
                      title="待继续改"
                      :value="selectedSummary.remaining_rewrite_required_count"
                    />
                  </Col>
                  <Col :span="4">
                    <Statistic
                      title="禁用词命中"
                      :value="selectedSummary.forbidden_hit_count"
                    />
                  </Col>
                </Row>

                <Alert
                  v-if="
                    selectedSummary?.forbidden_hit_count ||
                    selectedSummary?.remaining_rewrite_required_count ||
                    selectedSummary?.similarity_warning_count
                  "
                  class="mt-4"
                  message="这批内容仍有风险项或相似内容，请优先查看标红和标橙文章。"
                  show-icon
                  type="warning"
                />

                <Divider />

                <List :data-source="selectedItems" item-layout="vertical">
                  <template #renderItem="{ item }">
                    <ListItem :key="item.item_id">
                      <Card class="article-card" :bordered="true">
                        <template #title>
                          <Space wrap>
                            <span>第 {{ item.item_no }} 篇</span>
                            <Tag :color="statusColor(item.status)">
                              {{ item.status }}
                            </Tag>
                            <Tag :color="passColor(item.hard_pass)">
                              红线{{
                                item.hard_pass === true
                                  ? '通过'
                                  : item.hard_pass === false
                                    ? '未通过'
                                    : '未知'
                              }}
                            </Tag>
                            <Tag
                              v-if="item.rewrite_rounds || item.rewrite_reason"
                              color="blue"
                            >
                              已自动改写
                            </Tag>
                            <Tag
                              v-if="item.forbidden_hits.length > 0"
                              color="red"
                            >
                              禁用词 {{ item.forbidden_hits.join('、') }}
                            </Tag>
                            <Tag
                              v-if="item.similarity_warnings?.length"
                              color="orange"
                            >
                              疑似趋同 {{ item.similarity_warnings.length }}
                            </Tag>
                            <Tag v-if="item.review_status" color="purple">
                              {{ reviewStatusLabel(item.review_status) }} · v{{
                                item.latest_version_no || 1
                              }}
                            </Tag>
                            <Tag v-if="item.runtime_mode" color="cyan">
                              {{ item.runtime_mode }}
                            </Tag>
                            <Tag v-if="item.generation_duration_ms">
                              生文
                              {{ formatDuration(item.generation_duration_ms) }}
                            </Tag>
                            <Tag v-if="item.total_duration_ms">
                              总耗时 {{ formatDuration(item.total_duration_ms) }}
                            </Tag>
                          </Space>
                        </template>
                        <template #extra>
                          <Space>
                            <Button size="small" @click="copyArticle(item)">
                              复制
                            </Button>
                            <Button
                              v-if="item.trace_run_id || item.run_id"
                              size="small"
                              @click="showTrace(item)"
                            >
                              Trace
                            </Button>
                            <Button size="small" @click="showQuality(item)">
                              质量报告
                            </Button>
                          </Space>
                        </template>

                        <h3>{{ item.title || '未生成标题' }}</h3>
                        <div v-if="item.body" class="article-body">
                          {{ item.body }}
                        </div>
                        <Alert
                          v-else
                          :message="item.error_message || '正文尚未生成'"
                          type="error"
                        />

                        <Alert
                          v-if="item.reject_reasons?.length"
                          class="mt-3"
                          type="error"
                          show-icon
                        >
                          <template #message>
                            <div class="reject-reasons">
                              <div
                                v-for="reason in item.reject_reasons"
                                :key="`${reason.source}-${reason.code}-${reason.message}`"
                                class="reject-reason-item"
                              >
                                <Tag color="red">
                                  {{ rejectSourceLabel(reason.source) }}
                                </Tag>
                                <span v-if="reason.code" class="reason-code">
                                  {{ reason.code }}
                                </span>
                                <span>{{ reason.message }}</span>
                                <span v-if="reason.evidence?.length">
                                  证据：{{ reason.evidence.join('；') }}
                                </span>
                              </div>
                            </div>
                          </template>
                        </Alert>

                        <Alert
                          v-if="item.similarity_warnings?.length"
                          class="mt-3"
                          type="warning"
                          show-icon
                        >
                          <template #message>
                            <div class="similarity-warnings">
                              <div
                                v-for="warning in item.similarity_warnings"
                                :key="`${item.item_id}-${warning.item_no}-${warning.score}`"
                                class="similarity-warning-item"
                              >
                                <Tag color="orange">疑似趋同</Tag>
                                <span>
                                  与第 {{ warning.item_no }} 篇正文相似度
                                  {{ Math.round(warning.score * 100) }}%
                                </span>
                                <span>{{ warning.reason }}</span>
                              </div>
                            </div>
                          </template>
                        </Alert>

                        <div class="article-meta mt-3">
                          <Tag v-if="item.opening_type">
                            {{ item.opening_type }}
                          </Tag>
                          <Tag v-if="item.structure_type">
                            {{ item.structure_type }}
                          </Tag>
                          <Tag>字数 {{ item.body_chars }}</Tag>
                          <Tag>建议 {{ item.suggestion_count }}</Tag>
                          <Tag>替换 {{ item.replacement_count }}</Tag>
                          <Tag v-if="item.trace_run_id || item.run_id">
                            Run #{{ item.trace_run_id || item.run_id }}
                          </Tag>
                        </div>

                        <div
                          v-if="item.trace_stage_calls?.length"
                          class="trace-stage-list"
                        >
                          <span>执行链路</span>
                          <Tag
                            v-for="stage in item.trace_stage_calls"
                            :key="stage.stage_call_id"
                            :color="
                              stage.status === 'succeeded'
                                ? 'green'
                                : stage.status === 'failed'
                                  ? 'red'
                                  : 'blue'
                            "
                          >
                            {{ stage.capability }} ·
                            {{ formatDuration(stage.duration_ms) }}
                          </Tag>
                        </div>

                        <Divider />
                        <div class="feedback-placeholder">
                          <Alert
                            v-if="item.human_feedback_text"
                            class="mb-2"
                            :message="`最近反馈：${item.human_feedback_text}`"
                            show-icon
                            type="success"
                          />
                          <TextArea
                            v-model:value="feedbackDrafts[item.item_id]"
                            placeholder="填写运营修改意见；点“提交修改意见”会记录待改状态，点“人工编辑保存”可直接改标题/正文。"
                            :rows="2"
                          />
                          <Space class="mt-2">
                            <Button
                              size="small"
                              type="primary"
                              :loading="reviewingItemId === item.item_id"
                              @click="submitFeedback(item, 'approve')"
                            >
                              通过
                            </Button>
                            <Button
                              size="small"
                              :loading="reviewingItemId === item.item_id"
                              @click="submitFeedback(item, 'request_revision')"
                            >
                              提交修改意见
                            </Button>
                            <Button
                              size="small"
                              :loading="reviewingItemId === item.item_id"
                              @click="openManualEdit(item)"
                            >
                              人工编辑保存
                            </Button>
                          </Space>
                        </div>
                      </Card>
                    </ListItem>
                  </template>
                </List>
              </TabPane>

              <TabPane key="training" tab="训练反馈">
                <div class="training-panel">
                  <Card
                    class="training-sample-card"
                    :bordered="true"
                    title="跨批次反馈样本池"
                  >
                    <template #extra>
                      <Space>
                        <span class="sample-total">
                          共 {{ trainingFeedbackTotal }} 条
                        </span>
                        <Button
                          size="small"
                          :loading="trainingFeedbackLoading"
                          @click="loadTrainingFeedbackSamples"
                        >
                          刷新
                        </Button>
                      </Space>
                    </template>
                    <Spin :spinning="trainingFeedbackLoading">
                      <Empty
                        v-if="trainingFeedbackSamples.length === 0"
                        description="暂无跨批次反馈样本"
                      />
                      <div v-else class="training-sample-list">
                        <div
                          v-for="sample in trainingFeedbackSamples"
                          :key="sample.feedback_id"
                          class="training-sample-item"
                        >
                          <div class="training-sample-header">
                            <Space wrap>
                              <Tag :color="statusColor(sample.review_status)">
                                {{ reviewStatusLabel(sample.review_status) }}
                              </Tag>
                              <Tag>{{ actionLabel(sample.action) }}</Tag>
                              <span class="training-sample-title">
                                {{ sample.title || '未生成标题' }}
                              </span>
                            </Space>
                            <span class="sample-time">
                              {{ sample.create_time || '-' }}
                            </span>
                          </div>
                          <div class="training-sample-meta">
                            批次 #{{ sample.batch_id || '-' }} · 第
                            {{ sample.item_no }} 篇 ·
                            {{ sample.product_topic || '-' }} ·
                            {{ sample.submitter || 'unknown' }}
                          </div>
                          <div v-if="sample.comment" class="sample-comment">
                            {{ sample.comment }}
                          </div>
                          <div
                            v-if="sample.body_preview"
                            class="sample-body-preview"
                          >
                            {{ sample.body_preview }}
                          </div>
                        </div>
                      </div>
                    </Spin>
                  </Card>

                  <Row :gutter="12">
                    <Col :span="4">
                      <Statistic
                        title="已通过"
                        :value="trainingSummary.approved_count"
                      />
                    </Col>
                    <Col :span="4">
                      <Statistic
                        title="待修改"
                        :value="trainingSummary.needs_revision_count"
                      />
                    </Col>
                    <Col :span="4">
                      <Statistic
                        title="人工编辑"
                        :value="trainingSummary.manual_edited_count"
                      />
                    </Col>
                    <Col :span="4">
                      <Statistic
                        title="反馈数"
                        :value="trainingSummary.feedback_count"
                      />
                    </Col>
                    <Col :span="4">
                      <Statistic
                        title="驳回原因"
                        :value="trainingSummary.reject_reason_count"
                      />
                    </Col>
                    <Col :span="4">
                      <Statistic
                        title="疑似趋同"
                        :value="trainingSummary.similarity_warning_count"
                      />
                    </Col>
                    <Col :span="4">
                      <Button block @click="copyFeedbackDigest">
                        复制反馈摘要
                      </Button>
                    </Col>
                  </Row>

                  <Empty
                    v-if="trainingItems.length === 0"
                    class="mt-4"
                    description="当前批次还没有审核反馈或驳回原因"
                  />

                  <div v-else class="training-list">
                    <div
                      v-for="item in trainingItems"
                      :key="item.item_id"
                      class="training-item"
                    >
                      <div class="training-item-header">
                        <Space wrap>
                          <strong>第 {{ item.item_no }} 篇</strong>
                          <Tag :color="passColor(item.hard_pass)">
                            红线{{
                              item.hard_pass === true
                                ? '通过'
                                : item.hard_pass === false
                                  ? '未通过'
                                  : '未知'
                            }}
                          </Tag>
                          <Tag v-if="item.review_status" color="purple">
                            {{ reviewStatusLabel(item.review_status) }}
                          </Tag>
                          <Tag v-if="item.feedback_count" color="geekblue">
                            反馈 {{ item.feedback_count }}
                          </Tag>
                          <Tag
                            v-if="item.similarity_warnings?.length"
                            color="orange"
                          >
                            疑似趋同 {{ item.similarity_warnings.length }}
                          </Tag>
                          <Tag v-if="item.generation_duration_ms">
                            生文 {{ formatDuration(item.generation_duration_ms) }}
                          </Tag>
                        </Space>
                        <Space>
                          <Button
                            v-if="item.trace_run_id || item.run_id"
                            size="small"
                            @click="showTrace(item)"
                          >
                            Trace
                          </Button>
                          <Button size="small" @click="showQuality(item)">
                            质量报告
                          </Button>
                        </Space>
                      </div>
                      <div class="training-title">
                        {{ item.title || '未生成标题' }}
                      </div>
                      <div v-if="item.reject_reasons?.length" class="mt-2">
                        <div
                          v-for="reason in item.reject_reasons"
                          :key="`${reason.source}-${reason.code}-${reason.message}`"
                          class="reject-reason-item"
                        >
                          <Tag color="red">
                            {{ rejectSourceLabel(reason.source) }}
                          </Tag>
                          <span v-if="reason.code" class="reason-code">
                            {{ reason.code }}
                          </span>
                          <span>{{ reason.message }}</span>
                          <span v-if="reason.evidence?.length">
                            证据：{{ reason.evidence.join('；') }}
                          </span>
                        </div>
                      </div>
                      <div v-if="item.similarity_warnings?.length" class="mt-2">
                        <div
                          v-for="warning in item.similarity_warnings"
                          :key="`${item.item_id}-${warning.item_no}-${warning.score}`"
                          class="similarity-warning-item"
                        >
                          <Tag color="orange">疑似趋同</Tag>
                          <span>
                            与第 {{ warning.item_no }} 篇正文相似度
                            {{ Math.round(warning.score * 100) }}%
                          </span>
                          <span>{{ warning.reason }}</span>
                        </div>
                      </div>
                      <Alert
                        v-if="item.human_feedback_text"
                        class="mt-2"
                        :message="`人工反馈：${item.human_feedback_text}`"
                        show-icon
                        type="success"
                      />
                      <TextArea
                        v-model:value="feedbackDrafts[item.item_id]"
                        class="mt-2"
                        placeholder="补充这篇为什么好/不好。"
                        :rows="2"
                      />
                      <Space class="mt-2">
                        <Button
                          size="small"
                          type="primary"
                          :loading="reviewingItemId === item.item_id"
                          @click="submitFeedback(item, 'approve')"
                        >
                          通过
                        </Button>
                        <Button
                          size="small"
                          :loading="reviewingItemId === item.item_id"
                          @click="submitFeedback(item, 'request_revision')"
                        >
                          提交修改意见
                        </Button>
                        <Button
                          size="small"
                          :loading="reviewingItemId === item.item_id"
                          @click="openManualEdit(item)"
                        >
                          人工编辑保存
                        </Button>
                      </Space>
                    </div>
                  </div>
                </div>
              </TabPane>
            </Tabs>
          </Card>

          <Card v-else :bordered="false">
            <Empty description="请选择历史批次，或先生成一个新批次" />
          </Card>
        </Spin>
      </Col>
    </Row>
  </div>
</template>

<style scoped>
.content-agent-workbench {
  min-height: 100%;
}

.batch-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.batch-list-item {
  cursor: pointer;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 10px 12px;
  transition: all 0.16s ease;
}

.batch-list-item:hover,
.batch-list-item.active {
  border-color: #1677ff;
  background: #f0f6ff;
}

.batch-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-weight: 600;
}

.batch-meta,
.batch-total,
.article-meta {
  color: #666;
  font-size: 12px;
  margin-top: 4px;
}

.article-card {
  width: 100%;
}

.workspace-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 16px;
}

.article-body {
  white-space: pre-wrap;
  line-height: 1.8;
  color: #262626;
}

.feedback-placeholder {
  opacity: 0.8;
}

.reject-reasons {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.reject-reason-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.similarity-warnings {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.similarity-warning-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.reason-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  color: #a8071a;
}

.trace-stage-list {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  color: #666;
  font-size: 12px;
}

.trace-modal {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.trace-modal-stages {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 4px;
}

.trace-modal-stage {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) auto;
  gap: 4px 12px;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 8px 10px;
}

.trace-modal-stage code {
  grid-column: 1 / -1;
  white-space: pre-wrap;
  word-break: break-all;
}

.training-panel {
  min-height: 280px;
}

.training-sample-card {
  margin-bottom: 16px;
}

.training-sample-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 360px;
  overflow: auto;
}

.training-sample-item {
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 10px 12px;
  background: #fff;
}

.training-sample-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.training-sample-title {
  font-weight: 600;
}

.training-sample-meta,
.sample-total,
.sample-time,
.sample-body-preview {
  color: #666;
  font-size: 12px;
}

.sample-comment {
  margin-top: 8px;
  color: #262626;
}

.sample-body-preview {
  margin-top: 6px;
  line-height: 1.6;
}

.training-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}

.training-item {
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 14px;
  background: #fff;
}

.training-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.training-title {
  margin-top: 8px;
  color: #262626;
  font-weight: 600;
}
</style>
