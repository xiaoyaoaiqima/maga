<script setup lang="ts">
import type { ContentAgentApi } from '#/api/core/content-agent';

import { computed, h, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  DescriptionsItem,
  Divider,
  Empty,
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
  downloadContentBatchReportExcelApi,
  getContentBatchListApi,
  getContentBatchReportApi,
} from '#/api/core/content-agent';

import VersionComparePanel from '../components/version_compare_panel.vue';

const route = useRoute();
const router = useRouter();

const batchLoading = ref(false);
const reportLoading = ref(false);
const exportLoading = ref(false);
const selectedReport = ref<ContentAgentApi.BatchReport | null>(null);
const batchList = ref<ContentAgentApi.BatchListItem[]>([]);
const batchTotal = ref(0);

const selectedItems = computed(() => selectedReport.value?.items || []);
const selectedSummary = computed(() => selectedReport.value?.summary || null);

const statusLabel = (status?: string) => {
  if (status === 'approved') return '已通过';
  if (status === 'manual_edited') return '人工编辑';
  if (status === 'needs_revision') return '待修改';
  if (status === 'generated') return '已生成';
  if (status === 'failed') return '失败';
  if (status === 'running') return '生成中';
  if (status === 'partially_generated') return '部分生成';
  if (status === 'planned') return '待生成';
  return status || '未知';
};

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

const runtimeModeLabel = (runtimeMode?: string) => {
  if (runtimeMode === 'content_runtime') return '真实模型';
  if (runtimeMode === 'content_fake') return '模拟生成';
  if (runtimeMode === 'content_rewrite_runtime') return '模型改写';
  if (runtimeMode === 'content_rewrite_fake') return '模拟改写';
  return runtimeMode || '';
};

const passColor = (value?: boolean | null) => {
  if (value === true) return 'green';
  if (value === false) return 'red';
  return 'default';
};

const formatDuration = (durationMs?: null | number) => {
  if (durationMs === null || durationMs === undefined) return '-';
  if (durationMs < 1000) return `${durationMs}ms`;
  return `${(durationMs / 1000).toFixed(durationMs < 10_000 ? 2 : 1)}s`;
};

const failedCountOf = (
  summary?: ContentAgentApi.BatchReportSummary | null,
) => {
  if (!summary) return 0;
  return Math.max(0, summary.total_count - summary.generated_count);
};

const hasGeneratedContent = (item: ContentAgentApi.BatchReportItem) =>
  Boolean((item.title || '').trim() || (item.body || '').trim());

const qualityAvailable = (item: ContentAgentApi.BatchReportItem) =>
  item.quality && Object.keys(item.quality).length > 0;

const visibleTotalDurationMs = (item: ContentAgentApi.BatchReportItem) => {
  const total = item.total_duration_ms;
  if (total === null || total === undefined) return null;
  const generation = item.generation_duration_ms || 0;
  // 旧失败记录补写 finished_at 后会把等待修复的时间算进 Run 总耗时，
  // 失败卡片优先展示真实 stage 耗时，避免运营误读为 worker 执行了近一小时。
  if (item.status === 'failed' && total > 600_000 && generation < 120_000) {
    return null;
  }
  return total;
};

const displayErrorMessage = (message?: null | string) => {
  if (!message) return '';
  // 旧批次会保留 worker 的内部错误文案，列表页转成运营可理解的失败原因；
  // 原始错误仍保留在 Trace / 链路快照里，方便排障。
  if (message.includes('content.generate produced empty comment')) {
    return '模型没有返回可用正文，请重新从生产工作台生成新批次。';
  }
  return message;
};

const itemFailureMessage = (item: ContentAgentApi.BatchReportItem) => {
  const stageError = item.trace_stage_calls?.find(
    (stage) => stage.status === 'failed' && stage.error_message,
  )?.error_message;
  return (
    displayErrorMessage(item.error_message || stageError) ||
    '正文尚未生成，请查看执行链路。'
  );
};

const rejectSourceLabel = (source?: string) => {
  if (source === 'hard_review') return '硬性审核';
  if (source === 'failed_ae') return 'AE 审核';
  if (source === 'forbidden_term') return '禁用词';
  if (source === 'executor_error') return '执行失败';
  return source || '审核';
};

const reviewStatusLabel = (status?: null | string) => {
  if (status === 'approved') return '已通过';
  if (status === 'needs_revision') return '待修改';
  if (status === 'manual_edited') return '人工编辑';
  return status || '未审核';
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

const copyArticle = async (item: ContentAgentApi.BatchReportItem) => {
  if (!hasGeneratedContent(item)) {
    message.warning('这条还没有可复制的生成内容');
    return;
  }
  await copyText(`${item.title || ''}\n\n${item.body || ''}`.trim());
};

const exportExcel = async () => {
  const report = selectedReport.value;
  if (!report) return;
  exportLoading.value = true;
  try {
    const blob = await downloadContentBatchReportExcelApi(report.batch_id);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    const code = report.batch_code || `batch_${report.batch_id}`;
    link.href = url;
    link.download = `生文结果_${code}.xlsx`;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    message.success('Excel 已导出');
  } finally {
    exportLoading.value = false;
  }
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

const showQuality = (item: ContentAgentApi.BatchReportItem) => {
  Modal.info({
    title: `第 ${item.item_no} 条质量报告`,
    width: 760,
    content: JSON.stringify(item.quality || {}, null, 2),
  });
};

const snapshotJson = (value: unknown) => JSON.stringify(value ?? {}, null, 2);

const isEmptySnapshotValue = (value: unknown) => {
  if (value === null || value === undefined || value === '') return true;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === 'object') return Object.keys(value).length === 0;
  return false;
};

const snapshotPre = (value: unknown, emptyText = '无') =>
  h(
    'pre',
    { class: 'snapshot-pre' },
    isEmptySnapshotValue(value) ? emptyText : snapshotJson(value),
  );

const snapshotTextPre = (value?: null | string, emptyText = '无') =>
  h('pre', { class: 'snapshot-pre snapshot-prompt' }, value || emptyText);

const snapshotSection = (title: string, children: any[]) =>
  h('section', { class: 'snapshot-section' }, [
    h('div', { class: 'snapshot-section-title' }, title),
    ...children,
  ]);

const snapshotLine = (label: string, value: unknown) =>
  h('div', { class: 'snapshot-line' }, [
    h('span', { class: 'snapshot-line-label' }, label),
    h('span', { class: 'snapshot-line-value' }, String(value || '-')),
  ]);

const snapshotKeywordNodes = (keywords?: Array<Record<string, any>>) => {
  if (!keywords?.length) return [h('span', { class: 'snapshot-empty' }, '无')];
  return [
    h(
      'div',
      { class: 'snapshot-keyword-list' },
      keywords.map((keyword) =>
        h('div', { class: 'snapshot-keyword' }, [
          h('div', { class: 'snapshot-keyword-head' }, [
            h(
              Tag,
              { color: 'blue' },
              () => keyword.category_name || keyword.category_code || '关键词',
            ),
            h(
              'strong',
              keyword.keyword_name || keyword.keyword_code || '未命名子关键词',
            ),
          ]),
          h(
            'div',
            { class: 'snapshot-keyword-corpus' },
            Array.isArray(keyword.corpus)
              ? keyword.corpus.join('\n')
              : keyword.corpus || '',
          ),
        ]),
      ),
    ),
  ];
};

const snapshotRewriteNodes = (records?: Array<Record<string, any>>) => {
  if (!records?.length)
    return [h('span', { class: 'snapshot-empty' }, '未触发模型改写')];
  return records.map((record) =>
    h('div', { class: 'snapshot-rewrite-record' }, [
      h('div', { class: 'snapshot-rewrite-head' }, [
        h(
          Tag,
          { color: record.status === 'succeeded' ? 'green' : 'red' },
          () => `${record.capability || 'rewrite'} · ${record.status || '-'}`,
        ),
        h(
          'span',
          `#${record.sequence_no || '-'} ${record.stage_call_id || ''}`,
        ),
      ]),
      snapshotLine('命中词', (record.forbidden_hits || []).join('、')),
      snapshotLine(
        '模型',
        record.model_config?.model_code || record.model_config?.ge_model,
      ),
      snapshotLine('耗时', formatDuration(record.duration_ms)),
      h('div', { class: 'snapshot-two-cols' }, [
        h('div', [h('strong', '改写前'), snapshotPre(record.before)]),
        h('div', [h('strong', '改写后'), snapshotPre(record.after)]),
      ]),
      record.rendered_prompt
        ? snapshotTextPre(record.rendered_prompt, '无改写 Prompt')
        : null,
    ]),
  );
};

const showGenerationSnapshot = (item: ContentAgentApi.BatchReportItem) => {
  const snapshot: ContentAgentApi.GenerationSnapshot =
    item.generation_snapshot || {};
  Modal.info({
    title: `第 ${item.item_no} 条链路快照`,
    width: 980,
    content: h('div', { class: 'snapshot-modal' }, [
      h(
        Button,
        {
          size: 'small',
          onClick: () => copyText(snapshotJson(snapshot)),
        },
        () => '复制快照',
      ),
      h('div', { class: 'snapshot-line-grid' }, [
        snapshotLine('规则类型', snapshot.rule_type),
        snapshotLine('内容类型', snapshot.content_type),
        snapshotLine('Capability', snapshot.capability),
        snapshotLine('运行模式', snapshot.model_route?.runtime_mode),
        snapshotLine('执行器', snapshot.model_route?.executor_code),
        snapshotLine('模型', snapshot.model_route?.model_code),
      ]),
      snapshotSection('业务规则', [snapshotPre(snapshot.business_rule)]),
      snapshotSection(
        '系统关键词',
        snapshotKeywordNodes(snapshot.selected_keywords),
      ),
      snapshotSection('Expert / 模型', [
        h('div', { class: 'snapshot-two-cols' }, [
          snapshotPre(snapshot.expert),
          snapshotPre(snapshot.model_config),
        ]),
      ]),
      snapshotSection('Prompt', [
        snapshotTextPre(snapshot.rendered_prompt, '无 Prompt 快照'),
      ]),
      snapshotSection('审核改写', [
        snapshotPre(snapshot.forbidden_terms_review, '无违禁词审核命中'),
        ...snapshotRewriteNodes(snapshot.rewrite_records),
      ]),
      snapshotSection('执行阶段', [snapshotPre(snapshot.execution_stages)]),
    ]),
    okText: '关闭',
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
    // 从生产工作台跳转过来时，优先打开刚生成的批次报告。
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

const goFeedback = () => {
  router.push({
    path: '/content-agent/feedback',
    query: selectedReport.value
      ? { batch_id: String(selectedReport.value.batch_id) }
      : {},
  });
};

const goBusinessRules = () => {
  router.push('/business-rules');
};

onMounted(() => {
  loadBatches();
});

watch(
  () => route.query.batch_id,
  () => {
    loadBatches();
  },
);
</script>

<template>
  <div class="content-agent-result-page p-4">
    <Row :gutter="16">
      <Col :lg="7" :xs="24">
        <Card title="历史批次" :bordered="false">
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
                    {{ statusLabel(batch.status) }}
                  </Tag>
                </div>
                <div class="batch-meta">
                  #{{ batch.batch_id }} · {{ batch.batch_code || '-' }}
                </div>
                <div class="batch-meta">
                  {{ batch.summary.generated_count }}/{{
                    batch.summary.total_count
                  }}
                  条 · 失败 {{ failedCountOf(batch.summary) }} · 红线通过
                  {{ batch.summary.hard_pass_count }} · 改写
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

      <Col :lg="17" :xs="24">
        <Spin :spinning="reportLoading">
          <Card v-if="selectedReport" :bordered="false">
            <template #title>
              <Space>
                <span>生成历史</span>
                <Tag>
                  {{
                    selectedReport.batch_code || `#${selectedReport.batch_id}`
                  }}
                </Tag>
                <Tag :color="statusColor(selectedReport.status)">
                  {{ statusLabel(selectedReport.status) }}
                </Tag>
              </Space>
            </template>
            <template #extra>
              <Space>
                <Button size="small" @click="goFeedback">去评价</Button>
                <Button
                  size="small"
                  :loading="exportLoading"
                  @click="exportExcel"
                >
                  导出 Excel
                </Button>
                <Button
                  size="small"
                  @click="openReport(selectedReport.batch_id)"
                >
                  刷新报告
                </Button>
              </Space>
            </template>

            <Descriptions :column="2" size="small" bordered>
              <DescriptionsItem label="主题">
                {{ selectedReport.product_topic }}
              </DescriptionsItem>
              <DescriptionsItem label="资料">
                {{ selectedReport.asset_key }}
              </DescriptionsItem>
              <DescriptionsItem label="人群">
                {{ selectedReport.target_audience || '-' }}
              </DescriptionsItem>
              <DescriptionsItem label="风格">
                {{ selectedReport.style || '-' }}
              </DescriptionsItem>
            </Descriptions>

            <Row v-if="selectedSummary" class="mt-4" :gutter="12">
              <Col :span="4">
                <Statistic title="总数" :value="selectedSummary.total_count" />
              </Col>
              <Col :span="4">
                <Statistic
                  title="已生成"
                  :value="selectedSummary.generated_count"
                />
              </Col>
              <Col :span="4">
                <Statistic title="失败" :value="failedCountOf(selectedSummary)" />
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
                  title="禁用词命中"
                  :value="selectedSummary.forbidden_hit_count"
                />
              </Col>
            </Row>

            <Alert
              v-if="
                selectedSummary?.forbidden_hit_count ||
                selectedSummary?.remaining_rewrite_required_count ||
                selectedSummary?.similarity_warning_count ||
                failedCountOf(selectedSummary)
              "
              class="mt-4"
              :message="
                failedCountOf(selectedSummary)
                  ? `这批内容有 ${failedCountOf(selectedSummary)} 条失败项，失败项不进入红线审核；建议重新从生产工作台生成新批次。`
                  : '这批内容仍有风险项或相似内容，请优先查看标红和标橙内容。'
              "
              show-icon
              type="warning"
            >
              <template v-if="failedCountOf(selectedSummary)" #action>
                <Button size="small" type="link" @click="goBusinessRules">
                  回生产工作台
                </Button>
              </template>
            </Alert>

            <Divider />

            <List :data-source="selectedItems" item-layout="vertical">
              <template #renderItem="{ item }">
                <ListItem :key="item.item_id">
                  <Card class="content-card" :bordered="true">
                    <template #title>
                      <Space wrap>
                        <span>第 {{ item.item_no }} 条</span>
                        <Tag :color="statusColor(item.status)">
                          {{ statusLabel(item.status) }}
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
                        <Tag v-if="item.forbidden_hits.length > 0" color="red">
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
                          {{ runtimeModeLabel(item.runtime_mode) }}
                        </Tag>
                        <Tag v-if="item.generation_duration_ms">
                          生文 {{ formatDuration(item.generation_duration_ms) }}
                        </Tag>
                        <Tag v-if="visibleTotalDurationMs(item)">
                          总耗时 {{ formatDuration(visibleTotalDurationMs(item)) }}
                        </Tag>
                      </Space>
                    </template>
                    <template #extra>
                      <Space>
                        <Button
                          size="small"
                          :disabled="!hasGeneratedContent(item)"
                          @click="copyArticle(item)"
                        >
                          复制
                        </Button>
                        <Button
                          v-if="item.trace_run_id || item.run_id"
                          size="small"
                          @click="showTrace(item)"
                        >
                          Trace
                        </Button>
                        <Button
                          v-if="item.generation_snapshot"
                          size="small"
                          @click="showGenerationSnapshot(item)"
                        >
                          链路快照
                        </Button>
                        <Button
                          v-if="qualityAvailable(item)"
                          size="small"
                          @click="showQuality(item)"
                        >
                          质量报告
                        </Button>
                      </Space>
                    </template>

                    <h3>
                      {{
                        item.title ||
                        (item.status === 'failed' ? '生成失败' : '未生成标题')
                      }}
                    </h3>
                    <div v-if="item.body" class="content-body">
                      {{ item.body }}
                    </div>
                    <Alert
                      v-else
                      :message="itemFailureMessage(item)"
                      type="error"
                    />

                    <VersionComparePanel
                      v-if="item.version_compare"
                      :item="item"
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
                            <span v-if="reason.code" class="reason-code">
                              {{ reason.code }}
                            </span>
                            <span>{{ displayErrorMessage(reason.message) }}</span>
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
                      v-if="item.similarity_warnings?.length"
                      class="mt-3"
                      type="warning"
                      show-icon
                    >
                      <template #message>
                        <div class="reason-list">
                          <div
                            v-for="warning in item.similarity_warnings"
                            :key="`${item.item_id}-${warning.item_no}-${warning.score}`"
                            class="inline-info-row"
                          >
                            <Tag color="orange">疑似趋同</Tag>
                            <span>
                              与{{
                                warning.scope === 'history' ? '历史批次' : ''
                              }}第 {{ warning.item_no }} 条正文相似度
                              {{ Math.round(warning.score * 100) }}%
                            </span>
                            <span v-if="warning.batch_code">
                              批次：{{ warning.batch_code }}
                            </span>
                            <span>{{ warning.reason }}</span>
                          </div>
                        </div>
                      </template>
                    </Alert>

                    <div class="content-meta mt-3">
                      <Tag v-if="item.opening_type">
                        {{ item.opening_type }}
                      </Tag>
                      <Tag v-if="item.structure_type">
                        {{ item.structure_type }}
                      </Tag>
                      <Tag v-if="item.content_angle">
                        {{ item.content_angle }}
                      </Tag>
                      <Tag v-if="item.scene_type">
                        {{ item.scene_type }}
                      </Tag>
                      <Tag v-if="item.evidence_type">
                        {{ item.evidence_type }}
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
                  </Card>
                </ListItem>
              </template>
            </List>
          </Card>

          <Card v-else :bordered="false">
            <Empty
              description="暂无生成结果，请先在生产工作台上传业务规则并生成"
            />
          </Card>
        </Spin>
      </Col>
    </Row>
  </div>
</template>

<style scoped>
.content-agent-result-page {
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
.content-meta {
  color: #666;
  font-size: 12px;
  margin-top: 4px;
}

.content-card {
  width: 100%;
}

.content-body {
  white-space: pre-wrap;
  line-height: 1.8;
  color: #262626;
}

.reason-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.inline-info-row {
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

.snapshot-modal {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 72vh;
  overflow: auto;
}

.snapshot-section {
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 10px 12px;
}

.snapshot-section-title {
  margin-bottom: 8px;
  color: #262626;
  font-weight: 600;
}

.snapshot-line-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 12px;
}

.snapshot-line {
  display: flex;
  gap: 8px;
  min-width: 0;
  color: #595959;
  font-size: 12px;
}

.snapshot-line-label {
  flex: 0 0 72px;
  color: #8c8c8c;
}

.snapshot-line-value {
  min-width: 0;
  overflow-wrap: anywhere;
}

.snapshot-pre {
  max-height: 260px;
  overflow: auto;
  margin: 0;
  padding: 8px;
  border-radius: 6px;
  background: #fafafa;
  color: #262626;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.snapshot-prompt {
  max-height: 360px;
}

.snapshot-keyword-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.snapshot-keyword {
  border: 1px solid #f5f5f5;
  border-radius: 6px;
  padding: 8px;
}

.snapshot-keyword-head,
.snapshot-rewrite-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.snapshot-keyword-corpus {
  color: #595959;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.snapshot-two-cols {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.snapshot-rewrite-record {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
}

.snapshot-empty {
  color: #8c8c8c;
}

@media (max-width: 768px) {
  .snapshot-line-grid,
  .snapshot-two-cols {
    grid-template-columns: 1fr;
  }
}
</style>
