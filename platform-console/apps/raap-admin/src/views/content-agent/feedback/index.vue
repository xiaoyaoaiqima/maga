<script setup lang="ts">
import type { ContentAgentApi } from '#/api/core/content-agent';

import { computed, h, onMounted, reactive, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import { useUserStore } from '@vben/stores';

import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Input,
  List,
  ListItem,
  message,
  Modal,
  Row,
  Space,
  Spin,
  Statistic,
  Tag,
} from 'ant-design-vue';

import {
  getContentBatchFeedbackInsightsApi,
  getContentBatchListApi,
  getContentBatchReportApi,
  getFeedbackSamplesApi,
  submitBatchItemFeedbackApi,
} from '#/api/core/content-agent';

import VersionComparePanel from '../components/version_compare_panel.vue';

const { TextArea } = Input;

const route = useRoute();
const userStore = useUserStore();

const batchLoading = ref(false);
const feedbackInsightLoading = ref(false);
const reportLoading = ref(false);
const feedbackSamplesLoading = ref(false);
const reviewingItemId = ref<null | number>(null);
const selectedReport = ref<ContentAgentApi.BatchReport | null>(null);
const feedbackInsight = ref<ContentAgentApi.BatchFeedbackInsight | null>(null);
const batchList = ref<ContentAgentApi.BatchListItem[]>([]);
const batchTotal = ref(0);
const feedbackSamples = ref<ContentAgentApi.FeedbackSample[]>(
  [],
);
const feedbackSamplesTotal = ref(0);
const feedbackCategorySelections = reactive<Record<number, string[]>>({});
const feedbackDrafts = reactive<Record<number, string>>({});
const feedbackQuotedTexts = reactive<Record<number, string>>({});

const feedbackCategoryOptions = [
  { code: 'unnatural', label: '不自然' },
  { code: 'too_long', label: '太长' },
  { code: 'too_ad_like', label: '广告感' },
  { code: 'fact_issue', label: '信息不准' },
  { code: 'tone_mismatch', label: '语气不对' },
  { code: 'rule_mismatch', label: '不符规则' },
  { code: 'forbidden_term', label: '违禁词' },
];

const currentOperator = computed(
  () =>
    userStore.userInfo?.realName ||
    userStore.userInfo?.username ||
    'maga-operator',
);

const selectedItems = computed(() => selectedReport.value?.items || []);
const selectedSummary = computed(() => selectedReport.value?.summary || null);
const reviewItems = computed(() =>
  selectedItems.value.filter((item) => item.body || item.error_message),
);

const feedbackSummary = computed(() => {
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
    pending_count: items.filter((item) => !item.review_status).length,
    risk_count: items.filter(
      (item) =>
        item.hard_pass === false ||
        item.rewrite_required ||
        item.forbidden_hits?.length ||
        item.similarity_warnings?.length,
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

const priorityColor = (priority?: string) => {
  if (priority === 'high') return 'red';
  if (priority === 'medium') return 'orange';
  return 'blue';
};

const reviewStatusLabel = (status?: null | string) => {
  if (status === 'approved') return '已通过';
  if (status === 'needs_revision') return '待修改';
  if (status === 'manual_edited') return '人工编辑';
  return status || '未审核';
};

const actionLabel = (action?: string) => {
  if (action === 'accept_rewrite') return '采纳改写';
  if (action === 'approve') return '通过';
  if (action === 'manual_edit') return '人工改写';
  if (action === 'reject_rewrite') return '不采纳改写';
  if (action === 'request_revision') return '要求修改';
  return action || '-';
};

const suggestionTypeLabel = (type?: string) => {
  if (type === 'business_forbidden_term') return '业务违禁词';
  if (type === 'business_rule') return '业务规则';
  if (type === 'expert_prompt') return 'Expert';
  if (type === 'system_keyword') return '系统关键词';
  return type || '-';
};

const formatDuration = (durationMs?: null | number) => {
  if (durationMs === null || durationMs === undefined) return '-';
  if (durationMs < 1000) return `${durationMs}ms`;
  return `${(durationMs / 1000).toFixed(durationMs < 10_000 ? 2 : 1)}s`;
};

const feedbackActionLabel = (
  action: ContentAgentApi.BatchItemFeedbackAction,
) => {
  if (action === 'accept_rewrite') return '采纳改写';
  if (action === 'approve') return '通过';
  if (action === 'manual_edit') return '人工编辑保存';
  if (action === 'reject_rewrite') return '不采纳改写';
  return '提交修改意见';
};

const defaultFeedbackText = (
  action: ContentAgentApi.BatchItemFeedbackAction,
) => {
  if (action === 'accept_rewrite') return '采纳系统改写版本';
  if (action === 'approve') return '可发布';
  if (action === 'reject_rewrite') return '不采纳系统改写，回到修改前版本';
  return undefined;
};

const hasPendingAutoRewrite = (item: ContentAgentApi.BatchReportItem) =>
  item.version_compare?.compare_type === 'auto_rewrite';

const selectedFeedbackCategories = (itemId: number) =>
  feedbackCategorySelections[itemId] || [];

const toggleFeedbackCategory = (itemId: number, code: string) => {
  const selected = selectedFeedbackCategories(itemId);
  feedbackCategorySelections[itemId] = selected.includes(code)
    ? selected.filter((item) => item !== code)
    : [...selected, code];
};

const rejectSourceLabel = (source?: string) => {
  if (source === 'hard_review') return '硬性审核';
  if (source === 'failed_ae') return 'AE 审核';
  if (source === 'forbidden_term') return '禁用词';
  if (source === 'executor_error') return '执行失败';
  return source || '审核';
};

const forbiddenReviewOf = (item: ContentAgentApi.BatchReportItem) => {
  const quality = item.quality || {};
  const reviewReport = quality.review_report || {};
  return (
    quality.forbidden_terms_review ||
    reviewReport.forbidden_terms_review ||
    null
  );
};

const forbiddenReviewHits = (
  item: ContentAgentApi.BatchReportItem,
  key: 'final_hits' | 'initial_hits',
) => {
  const review = forbiddenReviewOf(item);
  return Array.isArray(review?.[key]) ? review[key] : [];
};

const forbiddenRewriteMethodLabel = (method?: string) => {
  if (!method || method === 'none') return '未改写';
  if (method.includes('content.rewrite')) return '模型改写';
  if (method.includes('deterministic_sanitize')) return '兜底清理';
  return method;
};

const itemFailureMessage = (item: ContentAgentApi.BatchReportItem) => {
  const stageError = item.trace_stage_calls?.find(
    (stage) => stage.status === 'failed' && stage.error_message,
  )?.error_message;
  return item.error_message || stageError || '正文尚未生成，请查看执行链路。';
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

const copyText = async (text?: null | string) => {
  if (!text) return;
  await navigator.clipboard.writeText(text);
  message.success('已复制');
};

const showTrace = (item: ContentAgentApi.BatchReportItem) => {
  Modal.info({
    title: `第 ${item.item_no} 条执行 Trace`,
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

const showQuality = (item: ContentAgentApi.BatchReportItem) => {
  Modal.info({
    title: `第 ${item.item_no} 条质量报告`,
    width: 760,
    content: JSON.stringify(item.quality || {}, null, 2),
  });
};

const loadFeedbackInsights = async (batchId: number) => {
  feedbackInsightLoading.value = true;
  try {
    feedbackInsight.value = await getContentBatchFeedbackInsightsApi(batchId);
  } finally {
    feedbackInsightLoading.value = false;
  }
};

const openReport = async (batchId: number, showLoading = true) => {
  if (showLoading) reportLoading.value = true;
  try {
    selectedReport.value = await getContentBatchReportApi(batchId);
    await loadFeedbackInsights(batchId);
  } finally {
    if (showLoading) reportLoading.value = false;
  }
};

const loadBatches = async () => {
  batchLoading.value = true;
  try {
    const data = await getContentBatchListApi({ limit: 20, offset: 0 });
    batchList.value = data?.items || [];
    batchTotal.value = data?.total || 0;
    const queryBatchId = Number(route.query.batch_id || 0);
    if (queryBatchId > 0 && selectedReport.value?.batch_id !== queryBatchId) {
      await openReport(queryBatchId, false);
      return;
    }
    if (!selectedReport.value && batchList.value[0]) {
      await openReport(batchList.value[0].batch_id, false);
    }
  } finally {
    batchLoading.value = false;
  }
};

const loadFeedbackSamples = async () => {
  feedbackSamplesLoading.value = true;
  try {
    const data = await getFeedbackSamplesApi({ limit: 30, offset: 0 });
    feedbackSamples.value = data?.items || [];
    feedbackSamplesTotal.value = data?.total || 0;
  } finally {
    feedbackSamplesLoading.value = false;
  }
};

const replaceReportItem = (updated: ContentAgentApi.BatchReportItem) => {
  if (!selectedReport.value) return;
  selectedReport.value.items = selectedReport.value.items.map((item) =>
    item.item_id === updated.item_id ? updated : item,
  );
};

const refreshSelectedReport = async () => {
  if (!selectedReport.value) return;
  const batchId = selectedReport.value.batch_id;
  selectedReport.value = await getContentBatchReportApi(batchId);
  await loadFeedbackInsights(batchId);
};

const submitFeedback = async (
  item: ContentAgentApi.BatchReportItem,
  action: ContentAgentApi.BatchItemFeedbackAction,
  options: { autoRewrite?: boolean } = {},
) => {
  const feedbackText = feedbackDrafts[item.item_id] || '';
  const feedbackCategories = selectedFeedbackCategories(item.item_id);
  if (
    action === 'request_revision' &&
    !feedbackText.trim() &&
    feedbackCategories.length === 0
  ) {
    message.warning('请先填写修改意见，或选择一个问题类型');
    return;
  }

  reviewingItemId.value = item.item_id;
  try {
    const response = await submitBatchItemFeedbackApi(item.item_id, {
      action,
      title: item.title,
      body: item.body,
      feedback_text: feedbackText || defaultFeedbackText(action),
      feedback_categories: feedbackCategories,
      quoted_text: feedbackQuotedTexts[item.item_id],
      created_by: currentOperator.value,
      auto_rewrite: options.autoRewrite,
    });
    replaceReportItem(response.item);
    await refreshSelectedReport();
    await loadFeedbackSamples();
    message.success(
      options.autoRewrite
        ? '系统已自动改写一版'
        : `${feedbackActionLabel(action)}已保存`,
    );
  } finally {
    reviewingItemId.value = null;
  }
};

const selectedText = () => {
  const selection = window.getSelection?.();
  const value = selection?.toString().trim() || '';
  return value.length <= 200 ? value : value.slice(0, 200);
};

const captureSelectedQuote = (item: ContentAgentApi.BatchReportItem) => {
  const quote = selectedText();
  if (!quote) {
    message.warning('请先在正文里选中需要反馈的片段');
    return;
  }
  feedbackQuotedTexts[item.item_id] = quote;
  message.success('已带入选中片段');
};

const clearQuotedText = (itemId: number) => {
  delete feedbackQuotedTexts[itemId];
};

const openBusinessForbiddenTermModal = (
  item: ContentAgentApi.BatchReportItem,
) => {
  const state = reactive({
    term: selectedText(),
  });
  Modal.confirm({
    title: '加入业务违禁词',
    width: 520,
    okText: '加入',
    cancelText: '取消',
    content: () =>
      h('div', { class: 'business-forbidden-term-modal' }, [
        h(Input, {
          value: state.term,
          placeholder: '输入不希望后续内容再出现的词',
          maxlength: 100,
          allowClear: true,
          'onUpdate:value': (value: string) => {
            state.term = value;
          },
        }),
        h(
          'div',
          { class: 'business-forbidden-term-hint' },
          '会保存到当前业务规则的违禁词里，并刷新这篇内容的风险命中。',
        ),
      ]),
    async onOk() {
      const term = state.term.trim();
      if (!term) {
        message.warning('请先输入业务违禁词');
        throw new Error('empty business forbidden term');
      }
      reviewingItemId.value = item.item_id;
      try {
        const response = await submitBatchItemFeedbackApi(item.item_id, {
          action: 'request_revision',
          title: item.title,
          body: item.body,
          feedback_text: `加入业务违禁词：${term}`,
          business_forbidden_terms: [term],
          created_by: currentOperator.value,
        });
        replaceReportItem(response.item);
        await refreshSelectedReport();
        await loadFeedbackSamples();
        message.success(`已加入业务违禁词：${term}`);
      } finally {
        reviewingItemId.value = null;
      }
    },
  });
};

const openManualEdit = (item: ContentAgentApi.BatchReportItem) => {
  const state = reactive({
    title: item.title || '',
    body: item.body || '',
    feedback_text: feedbackDrafts[item.item_id] || '运营人工编辑保存',
  });
  Modal.confirm({
    title: `人工编辑第 ${item.item_no} 条`,
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
        throw new Error('empty manual edit');
      }
      reviewingItemId.value = item.item_id;
      try {
        const response = await submitBatchItemFeedbackApi(item.item_id, {
          action: 'manual_edit',
          title: state.title,
          body: state.body,
          feedback_text: state.feedback_text,
          created_by: currentOperator.value,
        });
        replaceReportItem(response.item);
        await refreshSelectedReport();
        await loadFeedbackSamples();
        message.success('人工编辑已保存');
      } finally {
        reviewingItemId.value = null;
      }
    },
  });
};

onMounted(() => {
  loadBatches();
  loadFeedbackSamples();
});

watch(
  () => route.query.batch_id,
  () => {
    loadBatches();
  },
);
</script>

<template>
  <div class="content-agent-feedback-page p-4">
    <Row :gutter="16">
      <Col :lg="7" :xs="24">
        <Card title="待评价批次" :bordered="false">
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
                  {{ batch.summary.feedback_count }} 条反馈 · 风险
                  {{
                    batch.summary.remaining_rewrite_required_count +
                    batch.summary.similarity_warning_count
                  }}
                </div>
              </div>
            </div>
            <div v-if="batchTotal" class="batch-total">
              共 {{ batchTotal }} 个批次
            </div>
          </Spin>
        </Card>

        <Card class="mt-4" title="最近反馈" :bordered="false">
          <template #extra>
            <Button
              size="small"
              :loading="feedbackSamplesLoading"
              @click="loadFeedbackSamples"
            >
              刷新
            </Button>
          </template>
          <Spin :spinning="feedbackSamplesLoading">
            <Empty
              v-if="feedbackSamples.length === 0"
              description="暂无反馈"
            />
            <div v-else class="sample-list">
              <div
                v-for="sample in feedbackSamples"
                :key="sample.feedback_id"
                class="sample-item"
              >
                <Space wrap>
                  <Tag :color="statusColor(sample.review_status)">
                    {{ reviewStatusLabel(sample.review_status) }}
                  </Tag>
                  <Tag>{{ actionLabel(sample.action) }}</Tag>
                  <span>{{ sample.title || '未生成标题' }}</span>
                </Space>
                <div class="batch-meta">
                  批次 #{{ sample.batch_id || '-' }} · 第
                  {{ sample.item_no }} 条 · {{ sample.submitter || 'unknown' }}
                </div>
                <div v-if="sample.comment" class="sample-comment">
                  {{ sample.comment }}
                </div>
              </div>
            </div>
            <div v-if="feedbackSamplesTotal" class="batch-total">
              共 {{ feedbackSamplesTotal }} 条反馈
            </div>
          </Spin>
        </Card>
      </Col>

      <Col :lg="17" :xs="24">
        <Spin :spinning="reportLoading">
          <Card v-if="selectedReport" :bordered="false">
            <template #title>
              <Space>
                <span>评价反馈</span>
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
              <Button size="small" @click="openReport(selectedReport.batch_id)">
                刷新报告
              </Button>
            </template>

            <Row :gutter="12">
              <Col :span="4">
                <Statistic
                  title="未评价"
                  :value="feedbackSummary.pending_count"
                />
              </Col>
              <Col :span="4">
                <Statistic
                  title="已通过"
                  :value="feedbackSummary.approved_count"
                />
              </Col>
              <Col :span="4">
                <Statistic
                  title="待修改"
                  :value="feedbackSummary.needs_revision_count"
                />
              </Col>
              <Col :span="4">
                <Statistic
                  title="人工编辑"
                  :value="feedbackSummary.manual_edited_count"
                />
              </Col>
              <Col :span="4">
                <Statistic title="风险项" :value="feedbackSummary.risk_count" />
              </Col>
              <Col :span="4">
                <Statistic
                  title="反馈数"
                  :value="feedbackSummary.feedback_count"
                />
              </Col>
            </Row>

            <Alert
              class="mt-4"
              message="逐条确认内容是否可用；不希望后续出现的词，直接加入业务违禁词。"
              show-icon
              type="info"
            />

            <div class="feedback-insight-panel mt-4">
              <div class="feedback-insight-header">
                <Space wrap>
                  <strong>本批次问题汇总</strong>
                  <Tag>只读建议</Tag>
                  <Tag v-if="feedbackInsight">
                    {{ feedbackInsight.total_feedback_count }} 条反馈
                  </Tag>
                </Space>
                <Button
                  size="small"
                  :loading="feedbackInsightLoading"
                  @click="loadFeedbackInsights(selectedReport.batch_id)"
                >
                  刷新建议
                </Button>
              </div>
              <Spin :spinning="feedbackInsightLoading">
                <Empty
                  v-if="
                    !feedbackInsight ||
                    feedbackInsight.total_feedback_count === 0
                  "
                  image="simple"
                  description="暂无反馈汇总"
                />
                <template v-else>
                  <div class="insight-stat-grid">
                    <div class="insight-stat-block">
                      <div class="insight-block-title">问题类型</div>
                      <Space wrap>
                        <Tag
                          v-for="stat in feedbackInsight.category_stats"
                          :key="stat.code"
                          color="blue"
                        >
                          {{ stat.label }} {{ stat.count }}
                        </Tag>
                        <span
                          v-if="feedbackInsight.category_stats.length === 0"
                          class="insight-empty-text"
                        >
                          暂无结构化问题
                        </span>
                      </Space>
                    </div>
                    <div class="insight-stat-block">
                      <div class="insight-block-title">处理动作</div>
                      <Space wrap>
                        <Tag
                          v-for="stat in feedbackInsight.action_stats"
                          :key="stat.code"
                        >
                          {{ stat.label }} {{ stat.count }}
                        </Tag>
                      </Space>
                    </div>
                    <div class="insight-stat-block">
                      <div class="insight-block-title">改写采纳</div>
                      <Space wrap>
                        <Tag
                          v-for="stat in feedbackInsight.rewrite_decision_stats"
                          :key="stat.code"
                          color="purple"
                        >
                          {{ stat.label }} {{ stat.count }}
                        </Tag>
                        <span
                          v-if="
                            feedbackInsight.rewrite_decision_stats.length === 0
                          "
                          class="insight-empty-text"
                        >
                          暂无改写决策
                        </span>
                      </Space>
                    </div>
                  </div>

                  <div
                    v-if="feedbackInsight.suggestions.length > 0"
                    class="suggestion-list mt-3"
                  >
                    <div
                      v-for="suggestion in feedbackInsight.suggestions"
                      :key="`${suggestion.suggestion_type}-${suggestion.target}`"
                      class="suggestion-item"
                    >
                      <div class="suggestion-title-row">
                        <Space wrap>
                          <Tag :color="priorityColor(suggestion.priority)">
                            {{ suggestion.priority }}
                          </Tag>
                          <Tag>
                            {{
                              suggestionTypeLabel(suggestion.suggestion_type)
                            }}
                          </Tag>
                          <strong>{{ suggestion.title }}</strong>
                        </Space>
                        <span class="suggestion-target">
                          {{ suggestion.target }}
                        </span>
                      </div>
                      <div class="suggestion-reason">
                        {{ suggestion.reason }}
                      </div>
                      <div
                        v-if="suggestion.evidence.length > 0"
                        class="suggestion-evidence"
                      >
                        <div
                          v-for="evidence in suggestion.evidence"
                          :key="evidence"
                        >
                          {{ evidence }}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div
                    v-if="feedbackInsight.samples.length > 0"
                    class="insight-sample-list mt-3"
                  >
                    <div class="insight-block-title">反馈样例</div>
                    <div
                      v-for="sample in feedbackInsight.samples"
                      :key="sample.feedback_id"
                      class="insight-sample-item"
                    >
                      <Space wrap>
                        <Tag>{{ actionLabel(sample.action) }}</Tag>
                        <span>第 {{ sample.item_no }} 条</span>
                        <Tag
                          v-for="category in sample.feedback_categories"
                          :key="category"
                        >
                          {{
                            feedbackCategoryOptions.find(
                              (option) => option.code === category,
                            )?.label || category
                          }}
                        </Tag>
                      </Space>
                      <div
                        v-if="sample.quoted_text"
                        class="insight-sample-text"
                      >
                        片段：{{ sample.quoted_text }}
                      </div>
                      <div v-if="sample.comment" class="insight-sample-text">
                        反馈：{{ sample.comment }}
                      </div>
                    </div>
                  </div>
                </template>
              </Spin>
            </div>

            <List
              class="mt-4"
              :data-source="reviewItems"
              item-layout="vertical"
            >
              <template #renderItem="{ item }">
                <ListItem :key="item.item_id">
                  <Card class="feedback-card" :bordered="true">
                    <template #title>
                      <Space wrap>
                        <span>第 {{ item.item_no }} 条</span>
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
                        <Tag :color="statusColor(item.review_status || '')">
                          {{ reviewStatusLabel(item.review_status) }}
                        </Tag>
                        <Tag v-if="item.forbidden_hits.length > 0" color="red">
                          禁用词 {{ item.forbidden_hits.join('、') }}
                        </Tag>
                        <Tag
                          v-if="item.similarity_warnings?.length"
                          color="orange"
                        >
                          疑似趋同 {{ item.similarity_warnings.length }}
                        </Tag>
                      </Space>
                    </template>
                    <template #extra>
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
                    </template>

                    <h3>{{ item.title || '未生成标题' }}</h3>
                    <div v-if="item.body" class="content-body">
                      {{ item.body }}
                    </div>
                    <Alert
                      v-else
                      :message="itemFailureMessage(item)"
                      type="error"
                    />

                    <Alert
                      v-if="item.reject_reasons?.length"
                      class="mt-3"
                      type="error"
                      show-icon
                    >
                      <template #message>
                        <div class="reason-list">
                          <div
                            v-for="reason in item.reject_reasons"
                            :key="`${reason.source}-${reason.code}-${reason.message}`"
                            class="inline-info-row"
                          >
                            <Tag color="red">
                              {{ rejectSourceLabel(reason.source) }}
                            </Tag>
                            <span>{{ reason.message }}</span>
                            <span v-if="reason.evidence?.length">
                              证据：{{ reason.evidence.join('；') }}
                            </span>
                          </div>
                        </div>
                      </template>
                    </Alert>

                    <Alert
                      v-if="forbiddenReviewOf(item)?.initial_hits?.length"
                      class="mt-3"
                      :type="
                        forbiddenReviewOf(item)?.pass ? 'success' : 'error'
                      "
                      show-icon
                    >
                      <template #message>
                        <div class="inline-info-row">
                          <Tag
                            :color="
                              forbiddenReviewOf(item)?.pass ? 'green' : 'red'
                            "
                          >
                            违禁词审核{{
                              forbiddenReviewOf(item)?.pass
                                ? '已通过'
                                : '未通过'
                            }}
                          </Tag>
                          <span>
                            初始命中：{{
                              forbiddenReviewHits(item, 'initial_hits').join(
                                '、',
                              )
                            }}
                          </span>
                          <span>
                            处理：{{
                              forbiddenRewriteMethodLabel(
                                forbiddenReviewOf(item)?.rewrite_method,
                              )
                            }}，{{
                              forbiddenReviewOf(item)?.rewrite_rounds || 0
                            }}
                            轮
                          </span>
                          <span
                            v-if="
                              forbiddenReviewHits(item, 'final_hits').length > 0
                            "
                          >
                            仍命中：{{
                              forbiddenReviewHits(item, 'final_hits').join('、')
                            }}
                          </span>
                        </div>
                      </template>
                    </Alert>

                    <Alert
                      v-if="item.human_feedback_text"
                      class="mt-3"
                      :message="`最近反馈：${item.human_feedback_text}`"
                      show-icon
                      type="success"
                    />

                    <VersionComparePanel
                      v-if="item.version_compare"
                      :item="item"
                    />
                    <Space
                      v-if="hasPendingAutoRewrite(item)"
                      class="rewrite-decision-actions mt-2"
                    >
                      <Button
                        size="small"
                        type="primary"
                        :loading="reviewingItemId === item.item_id"
                        @click="submitFeedback(item, 'accept_rewrite')"
                      >
                        采纳改写
                      </Button>
                      <Button
                        size="small"
                        :loading="reviewingItemId === item.item_id"
                        @click="submitFeedback(item, 'reject_rewrite')"
                      >
                        不采纳，回到修改前
                      </Button>
                      <Button
                        size="small"
                        :loading="reviewingItemId === item.item_id"
                        @click="
                          submitFeedback(item, 'request_revision', {
                            autoRewrite: true,
                          })
                        "
                      >
                        再改一版
                      </Button>
                    </Space>

                    <div class="feedback-tools mt-3">
                      <div class="feedback-tool-row">
                        <span class="feedback-tool-label">问题类型</span>
                        <Space wrap>
                          <Button
                            v-for="option in feedbackCategoryOptions"
                            :key="option.code"
                            size="small"
                            :type="
                              selectedFeedbackCategories(item.item_id).includes(
                                option.code,
                              )
                                ? 'primary'
                                : 'default'
                            "
                            @click="
                              toggleFeedbackCategory(item.item_id, option.code)
                            "
                          >
                            {{ option.label }}
                          </Button>
                        </Space>
                      </div>
                      <div class="feedback-tool-row">
                        <span class="feedback-tool-label">引用片段</span>
                        <Button
                          size="small"
                          @click="captureSelectedQuote(item)"
                        >
                          带入选中片段
                        </Button>
                        <Tag
                          v-if="feedbackQuotedTexts[item.item_id]"
                          closable
                          @close="clearQuotedText(item.item_id)"
                        >
                          {{ feedbackQuotedTexts[item.item_id] }}
                        </Tag>
                      </div>
                    </div>

                    <TextArea
                      v-model:value="feedbackDrafts[item.item_id]"
                      class="mt-3"
                      placeholder="填写修改意见，或说明为什么通过。"
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
                        @click="
                          submitFeedback(item, 'request_revision', {
                            autoRewrite: true,
                          })
                        "
                      >
                        提交并改写
                      </Button>
                      <Button
                        size="small"
                        :loading="reviewingItemId === item.item_id"
                        @click="openManualEdit(item)"
                      >
                        人工编辑保存
                      </Button>
                      <Button
                        v-if="item.body"
                        danger
                        size="small"
                        :loading="reviewingItemId === item.item_id"
                        @click="openBusinessForbiddenTermModal(item)"
                      >
                        加入业务违禁词
                      </Button>
                    </Space>
                  </Card>
                </ListItem>
              </template>
            </List>
          </Card>

          <Card v-else :bordered="false">
            <Empty description="暂无可评价批次，请先在生产工作台生成内容" />
          </Card>
        </Spin>
      </Col>
    </Row>
  </div>
</template>

<style scoped>
.content-agent-feedback-page {
  min-height: 100%;
}

.batch-list,
.sample-list,
.reason-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.batch-list-item,
.sample-item {
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
.batch-total {
  color: #666;
  font-size: 12px;
  margin-top: 4px;
}

.sample-comment {
  color: #444;
  margin-top: 6px;
}

.feedback-card {
  width: 100%;
}

.content-body {
  white-space: pre-wrap;
  line-height: 1.8;
  color: #262626;
}

.feedback-insight-panel {
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 12px;
  background: #fff;
}

.feedback-insight-header,
.suggestion-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.insight-stat-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 12px;
}

.insight-stat-block,
.suggestion-item,
.insight-sample-item {
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 10px;
  background: #fafafa;
}

.insight-block-title {
  margin-bottom: 8px;
  color: #595959;
  font-size: 12px;
  font-weight: 600;
}

.insight-empty-text,
.suggestion-target,
.suggestion-reason,
.suggestion-evidence,
.insight-sample-text {
  color: #595959;
  font-size: 12px;
}

.suggestion-list,
.insight-sample-list,
.suggestion-evidence {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.suggestion-reason {
  margin-top: 8px;
}

.suggestion-evidence {
  margin-top: 8px;
}

.insight-sample-text {
  margin-top: 6px;
}

.feedback-tools {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  background: #fafafa;
}

.feedback-tool-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.feedback-tool-label {
  flex: 0 0 64px;
  color: #8c8c8c;
  font-size: 12px;
}

.inline-info-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
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
  max-height: 320px;
  overflow: auto;
}

.trace-modal-stage {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 6px 12px;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 8px 10px;
}

@media (max-width: 960px) {
  .feedback-insight-header,
  .suggestion-title-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .insight-stat-grid {
    grid-template-columns: 1fr;
  }
}
</style>
