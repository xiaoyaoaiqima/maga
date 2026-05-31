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
  getContentBatchListApi,
  getContentBatchReportApi,
  getTrainingFeedbackSamplesApi,
  submitBatchItemFeedbackApi,
} from '#/api/core/content-agent';

import VersionComparePanel from '../components/version_compare_panel.vue';

const { TextArea } = Input;

const route = useRoute();
const userStore = useUserStore();

const batchLoading = ref(false);
const reportLoading = ref(false);
const trainingFeedbackLoading = ref(false);
const reviewingItemId = ref<null | number>(null);
const selectedReport = ref<ContentAgentApi.BatchReport | null>(null);
const batchList = ref<ContentAgentApi.BatchListItem[]>([]);
const batchTotal = ref(0);
const trainingFeedbackSamples = ref<ContentAgentApi.TrainingFeedbackSample[]>(
  [],
);
const trainingFeedbackTotal = ref(0);
const feedbackDrafts = reactive<Record<number, string>>({});

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

const reviewStatusLabel = (status?: null | string) => {
  if (status === 'approved') return '已通过';
  if (status === 'needs_revision') return '待修改';
  if (status === 'manual_edited') return '人工编辑';
  return status || '未审核';
};

const actionLabel = (action?: string) => {
  if (action === 'approve') return '通过';
  if (action === 'manual_edit') return '人工改写';
  if (action === 'request_revision') return '要求修改';
  return action || '-';
};

const formatDuration = (durationMs?: null | number) => {
  if (durationMs === null || durationMs === undefined) return '-';
  if (durationMs < 1000) return `${durationMs}ms`;
  return `${(durationMs / 1000).toFixed(durationMs < 10_000 ? 2 : 1)}s`;
};

const feedbackActionLabel = (
  action: ContentAgentApi.BatchItemFeedbackAction,
) => {
  if (action === 'approve') return '通过';
  if (action === 'manual_edit') return '人工编辑保存';
  return '提交修改意见';
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

const openReport = async (batchId: number, showLoading = true) => {
  if (showLoading) reportLoading.value = true;
  try {
    selectedReport.value = await getContentBatchReportApi(batchId);
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

const replaceReportItem = (updated: ContentAgentApi.BatchReportItem) => {
  if (!selectedReport.value) return;
  selectedReport.value.items = selectedReport.value.items.map((item) =>
    item.item_id === updated.item_id ? updated : item,
  );
};

const refreshSelectedReport = async () => {
  if (!selectedReport.value) return;
  selectedReport.value = await getContentBatchReportApi(
    selectedReport.value.batch_id,
  );
};

const submitFeedback = async (
  item: ContentAgentApi.BatchReportItem,
  action: ContentAgentApi.BatchItemFeedbackAction,
  options: { autoRewrite?: boolean } = {},
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
      created_by: currentOperator.value,
      auto_rewrite: options.autoRewrite,
    });
    replaceReportItem(response.item);
    await refreshSelectedReport();
    await loadTrainingFeedbackSamples();
    message.success(
      options.autoRewrite
        ? '修改意见已提交，系统已自动改写一版'
        : `${feedbackActionLabel(action)}已保存`,
    );
  } finally {
    reviewingItemId.value = null;
  }
};

const selectedText = () => {
  const selection = window.getSelection?.();
  const value = selection?.toString().trim() || '';
  return value.length <= 100 ? value : '';
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
          '会保存到当前业务规则包的违禁词里，并刷新这篇内容的风险命中。',
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
        await loadTrainingFeedbackSamples();
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
        await loadTrainingFeedbackSamples();
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
              :loading="trainingFeedbackLoading"
              @click="loadTrainingFeedbackSamples"
            >
              刷新
            </Button>
          </template>
          <Spin :spinning="trainingFeedbackLoading">
            <Empty
              v-if="trainingFeedbackSamples.length === 0"
              description="暂无反馈"
            />
            <div v-else class="sample-list">
              <div
                v-for="sample in trainingFeedbackSamples"
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
            <div v-if="trainingFeedbackTotal" class="batch-total">
              共 {{ trainingFeedbackTotal }} 条反馈
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
            <Empty description="暂无可评价批次，请先在业务规则页生成内容" />
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
</style>
