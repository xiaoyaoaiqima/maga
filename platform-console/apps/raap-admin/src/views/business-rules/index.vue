<script setup lang="ts">
import type { UploadProps } from 'ant-design-vue';

import type { AssetsApi } from '#/api/core/assets';
import type { ChatContext } from '#/api/core/chat';
import type { ContentAgentApi } from '#/api/core/content-agent';

import { computed, h, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import { useUserStore } from '@vben/stores';

import {
  CheckOutlined,
  EditOutlined,
  MessageOutlined,
  ReloadOutlined,
  SaveOutlined,
  UploadOutlined,
} from '@ant-design/icons-vue';
import {
  Button,
  Card,
  Col,
  Drawer,
  Empty,
  Input,
  InputNumber,
  message,
  Modal,
  Row,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Textarea,
  Upload,
} from 'ant-design-vue';

import {
  getAssetDetailApi,
  getAssetSummariesApi,
  getCommentAngleRuleDraftsApi,
  importCommentAngleRuleSetApi,
  importProductExperienceRuleSetApi,
  publishCommentAngleRuleDraftApi,
  saveCommentAngleRuleDraftApi,
} from '#/api/core/assets';
import {
  getContentBatchListApi,
  getContentBatchReportApi,
  preflightContentGenerationApi,
  startCommentBatchApi,
} from '#/api/core/content-agent';
import { useMagaChatStore } from '#/store';

type RulePackageType = 'comment_angle' | 'product_experience';

interface RulePackageConfig {
  accept: string;
  assetType: string;
  defaultAssetKey: string;
  defaultDisplayName: string;
  label: string;
}

const rulePackageConfigs: Record<RulePackageType, RulePackageConfig> = {
  comment_angle: {
    accept: '.csv,.xlsx',
    assetType: 'comment_angle_rule_set',
    defaultAssetKey: 'yuanyue_comment_activity',
    defaultDisplayName: '源悦-业务规则（评论切角）',
    label: '评论切角',
  },
  product_experience: {
    accept: '.csv,.xlsx',
    assetType: 'product_experience_rule_set',
    defaultAssetKey: 'yuanyue_product_experience',
    defaultDisplayName: '源悦-业务规则（产品使用体验）',
    label: '产品使用体验',
  },
};

const ruleAssetTypes = Object.values(rulePackageConfigs).map(
  (item) => item.assetType,
);
const ruleUploadAccept = [
  ...new Set(
    Object.values(rulePackageConfigs)
      .flatMap((item) => item.accept.split(','))
      .map((item) => item.trim())
      .filter(Boolean),
  ),
].join(',');

const loading = ref(false);
const importing = ref(false);
const generating = ref(false);
const packageType = ref<RulePackageType>('comment_angle');
const displayName = ref(rulePackageConfigs.comment_angle.defaultDisplayName);
const pendingFile = ref<File | null>(null);
const uploadConfirmOpen = ref(false);
const showHiddenRules = ref(false);
const ruleAssets = ref<AssetsApi.AssetSummary[]>([]);
const selectedSummary = ref<AssetsApi.AssetSummary | null>(null);
const selectedAsset = ref<AssetsApi.AssetRegistry | null>(null);
const userStore = useUserStore();
const chatStore = useMagaChatStore();
const route = useRoute();
const batchLoading = ref(false);
const reportLoading = ref(false);
const selectedReport = ref<ContentAgentApi.BatchReport | null>(null);
const batchList = ref<ContentAgentApi.BatchListItem[]>([]);
const batchTotal = ref(0);
const focusGenerateOpen = ref(false);
const focusGenerateForm = ref({
  rule_key: '',
  count: 10,
});
const draftEditorOpen = ref(false);
const draftSaving = ref(false);
const draftTesting = ref(false);
const draftPublishing = ref(false);
const selectedDraftRule = ref<Record<string, any> | null>(null);
const draftCorpus = ref('');
const latestDraft = ref<AssetsApi.CommentAngleRuleDraft | null>(null);
const hasUnsavedDraftChanges = computed(
  () =>
    Boolean(latestDraft.value) &&
    draftCorpus.value.trim() !== latestDraft.value?.draft_corpus.trim(),
);

const selectedRuleItems = computed(() => {
  const items = selectedAsset.value?.content_json?.items;
  return Array.isArray(items) ? items : [];
});
const selectedItems = computed(() => selectedRuleItems.value);
const selectedReportItems = computed(() => selectedReport.value?.items || []);
const selectedReportSummary = computed(
  () => selectedReport.value?.summary || null,
);
const isSelectedCommentRuleSet = computed(
  () => selectedAsset.value?.asset_type === 'comment_angle_rule_set',
);
const selectedCommentAngleOptions = computed(() => {
  return selectedRuleItems.value
    .filter((item) => String(item.comment_angle || '').trim())
    .map((item) => ({
      label: ruleDisplayName(item),
      value: ruleKey(item),
    }));
});

const currentOperator = computed(
  () =>
    userStore.userInfo?.realName ||
    userStore.userInfo?.username ||
    'maga-operator',
);

const packageTypeOptions = computed(() =>
  Object.entries(rulePackageConfigs).map(([value, config]) => ({
    label: config.defaultDisplayName,
    value,
  })),
);

const selectedMeta = computed(() => selectedAsset.value?.metadata_json || {});
const selectedRuleCount = computed(
  () => selectedMeta.value.rule_count ?? selectedItems.value.length,
);
const selectedExampleCount = computed(
  () =>
    selectedMeta.value.example_count ??
    selectedItems.value.reduce(
      (sum, item) => sum + ((item.examples || []).length || 0),
      0,
    ),
);
const selectedWarnings = computed(() =>
  Array.isArray(selectedMeta.value.warnings) ? selectedMeta.value.warnings : [],
);
const selectedDefaultGenerationCount = computed(
  () =>
    selectedMeta.value.default_generation_count ??
    selectedAsset.value?.content_json?.default_generation_count ??
    '-',
);

const selectedPackageName = computed(
  () =>
    selectedAsset.value?.display_name || selectedSummary.value?.display_name,
);
const selectedPackageTypeLabel = computed(() =>
  packageLabel(
    selectedAsset.value?.asset_type || selectedSummary.value?.asset_type,
  ),
);
const selectedSourceName = computed(
  () =>
    selectedAsset.value?.source_name ||
    selectedSummary.value?.source_name ||
    '-',
);
const selectedPackageUpdatedAt = computed(
  () =>
    selectedAsset.value?.update_time ||
    selectedSummary.value?.update_time ||
    '-',
);
const reportFailureCount = computed(() =>
  failedCountOf(selectedReportSummary.value),
);
const reportRiskCount = computed(() => {
  const summary = selectedReportSummary.value;
  if (!summary) return 0;
  return (
    reportFailureCount.value +
    (summary.forbidden_hit_count || 0) +
    (summary.remaining_rewrite_required_count || 0) +
    (summary.similarity_warning_count || 0)
  );
});

const batchDetailColumns: any[] = [
  { title: '序号', dataIndex: 'item_no', key: 'item_no', width: 72 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 110 },
  { title: '正文', dataIndex: 'body', key: 'body', minWidth: 320 },
  { title: '红线', dataIndex: 'hard_pass', key: 'hard_pass', width: 90 },
  { title: '风险', key: 'risk', width: 220 },
  { title: '字数', dataIndex: 'body_chars', key: 'body_chars', width: 80 },
];

const previewColumns = computed<any[]>(() => {
  if (selectedAsset.value?.asset_type === 'product_experience_rule_set') {
    return [
      {
        title: '产品使用体验',
        dataIndex: 'product_experience',
        key: 'product_experience',
        width: 230,
      },
      { title: '月龄', dataIndex: 'baby_stage', key: 'baby_stage', width: 120 },
      {
        title: '使用时间',
        dataIndex: 'use_duration',
        key: 'use_duration',
        width: 120,
      },
      { title: '主题', dataIndex: 'topic', key: 'topic', width: 130 },
      { title: '语料', dataIndex: 'corpus', key: 'corpus' },
      { title: '示例', key: 'examples', width: 80 },
    ];
  }
  return [
    {
      title: '评论切角',
      dataIndex: 'comment_angle',
      key: 'comment_angle',
      width: 240,
    },
    { title: '语料', dataIndex: 'corpus', key: 'corpus' },
    { title: '示例', key: 'examples', width: 80 },
    { title: '补充', key: 'supplements', width: 80 },
    { fixed: 'right', title: '操作', key: 'action', width: 240 },
  ];
});

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
  return 'default';
};

const failedCountOf = (summary?: ContentAgentApi.BatchReportSummary | null) => {
  if (!summary) return 0;
  return Math.max(0, summary.total_count - summary.generated_count);
};

const passColor = (value?: boolean | null) => {
  if (value === true) return 'green';
  if (value === false) return 'red';
  return 'default';
};

const passLabel = (value?: boolean | null) => {
  if (value === true) return '通过';
  if (value === false) return '未通过';
  return '未知';
};

const displayErrorMessage = (value?: null | string) => {
  if (!value) return '';
  if (value.includes('content.generate produced empty comment')) {
    return '模型没有返回可用正文';
  }
  return value;
};

const itemFailureMessage = (item: ContentAgentApi.BatchReportItem | Record<string, any>) => {
  const stageError = item.trace_stage_calls?.find(
    (stage: Record<string, any>) => stage.status === 'failed' && stage.error_message,
  )?.error_message;
  return (
    displayErrorMessage(item.error_message || stageError) ||
    '正文尚未生成，请查看执行链路。'
  );
};

function riskTagsOf(item: ContentAgentApi.BatchReportItem | Record<string, any>) {
  const tags: Array<{ color: string; label: string }> = [];
  const forbiddenHits = item.forbidden_hits || [];
  if (forbiddenHits.length > 0) {
    tags.push({ color: 'red', label: `禁用词 ${forbiddenHits.join('、')}` });
  }
  if (item.rewrite_required) {
    tags.push({ color: 'orange', label: item.rewrite_reason || '需改写' });
  }
  if (item.similarity_warnings?.length) {
    tags.push({
      color: 'orange',
      label: `疑似趋同 ${item.similarity_warnings.length}`,
    });
  }
  if (item.reject_reasons?.length) {
    tags.push({ color: 'red', label: `拒绝 ${item.reject_reasons.length}` });
  }
  return tags;
}

function normalizeTextList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => String(item || '').trim())
    .filter(Boolean)
    .slice(0, 12);
}

function buildChatReportSummary() {
  const report = selectedReport.value;
  if (!report) return null;
  return {
    batch_id: report.batch_id,
    batch_code: report.batch_code || null,
    status: report.status,
    total_count: selectedReportSummary.value?.total_count ?? report.count,
    generated_count: selectedReportSummary.value?.generated_count ?? 0,
    failed_count: reportFailureCount.value,
    risk_count: reportRiskCount.value,
    samples: selectedReportItems.value.slice(0, 5).map((item) => ({
      item_no: item.item_no,
      body: item.body || itemFailureMessage(item),
      risks: riskTagsOf(item).map((tag) => tag.label),
    })),
  };
}

function buildDraftChatContext(): ChatContext | null {
  if (!selectedAsset.value || !selectedDraftRule.value || !isSelectedCommentRuleSet.value) {
    return null;
  }
  return {
    page: 'business_rules',
    asset_key: selectedAsset.value.asset_key,
    asset_type: selectedAsset.value.asset_type,
    asset_version:
      selectedAsset.value.version_no || latestDraft.value?.base_version_no || null,
    rule_id: String(selectedDraftRule.value.rule_id || ''),
    source_row_no:
      Number(selectedDraftRule.value.source_row_no || 0) || null,
    comment_angle: String(selectedDraftRule.value.comment_angle || ''),
    corpus: String(selectedDraftRule.value.corpus || ''),
    draft_corpus: draftCorpus.value,
    examples: normalizeTextList(selectedDraftRule.value.examples),
    supplements: normalizeTextList(selectedDraftRule.value.supplements),
    test_report_summary: buildChatReportSummary(),
  };
}

function syncDraftChatContext() {
  if (!draftEditorOpen.value) return;
  const context = buildDraftChatContext();
  if (context) chatStore.setContext(context);
}

async function loadRuleAssets() {
  loading.value = true;
  try {
    const groups = await Promise.all(
      ruleAssetTypes.map((assetType) =>
        getAssetSummariesApi({
          asset_stage: 'production',
          asset_type: assetType,
          include_hidden: showHiddenRules.value,
        }),
      ),
    );
    ruleAssets.value = groups.flat();
    const selectedStillVisible = ruleAssets.value.some(
      (asset) =>
        asset.id === selectedSummary.value?.id ||
        (asset.asset_type === selectedSummary.value?.asset_type &&
          asset.asset_key === selectedSummary.value?.asset_key),
    );
    if (!selectedStillVisible) {
      selectedSummary.value = null;
      selectedAsset.value = null;
    }
    const firstAsset = ruleAssets.value[0];
    if (!selectedSummary.value && firstAsset) {
      await openAsset(firstAsset);
    }
  } catch {
    message.error('获取业务规则失败');
  } finally {
    loading.value = false;
  }
}

async function openAsset(row: AssetsApi.AssetSummary | Record<string, any>) {
  selectedSummary.value = row as AssetsApi.AssetSummary;
  selectedAsset.value = await getAssetDetailApi(row.asset_type, row.asset_key, {
    asset_stage: row.asset_stage,
  });
}

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
    if (queryBatchId > 0 && !selectedReport.value) {
      await openReport(queryBatchId, false);
      return;
    }
    if (selectedReport.value?.batch_id) {
      await openReport(selectedReport.value.batch_id, false);
      return;
    }
    if (!selectedReport.value && batchList.value[0]) {
      await openReport(batchList.value[0].batch_id, false);
    }
  } finally {
    batchLoading.value = false;
  }
};

function openFocusGeneration() {
  if (!selectedAsset.value || !isSelectedCommentRuleSet.value) {
    message.warning('请先选择业务规则（评论切角）');
    return;
  }
  const firstRuleKey = selectedCommentAngleOptions.value[0]?.value;
  if (!firstRuleKey) {
    message.warning('当前业务规则没有可测试的评论切角');
    return;
  }
  focusGenerateForm.value = {
    rule_key: focusGenerateForm.value.rule_key || firstRuleKey,
    count: focusGenerateForm.value.count || 10,
  };
  focusGenerateOpen.value = true;
}

function openRuleGeneration(record: Record<string, any>) {
  if (!isSelectedCommentRuleSet.value) {
    message.warning('当前业务规则类型暂不支持单条测试');
    return;
  }
  focusGenerateForm.value = {
    rule_key: ruleKey(record),
    count: focusGenerateForm.value.count || 10,
  };
  focusGenerateOpen.value = true;
}

async function generateFocusedCommentAngle() {
  if (!selectedAsset.value?.asset_key) {
    message.warning('请先选择业务规则（评论切角）');
    return;
  }
  const targetRule = selectedRuleItems.value.find(
    (item) => ruleKey(item) === focusGenerateForm.value.rule_key,
  );
  const commentAngle = String(targetRule?.comment_angle || '').trim();
  if (!targetRule || !commentAngle) {
    message.warning('请选择一条业务规则');
    return;
  }
  generating.value = true;
  try {
    const preflight = await preflightContentGenerationApi({
      asset_key: selectedAsset.value.asset_key,
      asset_type: selectedAsset.value.asset_type,
    });
    if (!preflight.passed) {
      showPreflightFailure(preflight);
      return;
    }
    const result = await startCommentBatchApi({
      asset_key: selectedAsset.value.asset_key,
      comment_angle: commentAngle,
      count: Number(focusGenerateForm.value.count || 10),
      created_by: currentOperator.value,
      rule_id: String(targetRule.rule_id || ''),
      source_row_no: Number(targetRule.source_row_no || 0) || undefined,
    });
    message.success(
      `业务规则测试完成：${result.execution.generated_count}/${result.execution.requested_limit}`,
    );
    focusGenerateOpen.value = false;
    selectedReport.value = result.report;
    await loadBatches();
  } catch {
    message.error('业务规则测试失败，请检查业务规则内容和模型配置');
  } finally {
    generating.value = false;
  }
}

async function openDraftEditor(record: Record<string, any>) {
  if (!selectedAsset.value?.asset_key || !isSelectedCommentRuleSet.value) {
    message.warning('请先选择业务规则（评论切角）');
    return;
  }
  selectedDraftRule.value = record;
  draftCorpus.value = String(record.corpus || '');
  latestDraft.value = null;
  draftEditorOpen.value = true;
  await loadLatestDraft(record);
  syncDraftChatContext();
}

async function loadLatestDraft(record = selectedDraftRule.value) {
  if (!selectedAsset.value?.asset_key || !record) return;
  try {
    const drafts = await getCommentAngleRuleDraftsApi({
      asset_key: selectedAsset.value.asset_key,
      limit: 1,
      rule_id: String(record.rule_id || ''),
      source_row_no: Number(record.source_row_no || 0) || undefined,
    });
    latestDraft.value = drafts[0] || null;
    if (latestDraft.value?.draft_corpus) {
      draftCorpus.value = latestDraft.value.draft_corpus;
    }
  } catch {
    latestDraft.value = null;
  }
}

async function openRuleChatCopilot(record: Record<string, any>) {
  if (!selectedAsset.value?.asset_key || !isSelectedCommentRuleSet.value) {
    message.warning('请先选择业务规则（评论切角）');
    return;
  }
  selectedDraftRule.value = record;
  draftCorpus.value = String(record.corpus || '');
  latestDraft.value = null;
  await loadLatestDraft(record);
  const context = buildDraftChatContext();
  if (!context) {
    message.warning('当前业务规则上下文不可用');
    return;
  }
  chatStore.openWithContext(context);
}

async function saveRuleDraft() {
  if (!selectedAsset.value?.asset_key || !selectedDraftRule.value) {
    message.warning('请先选择一条业务规则');
    return;
  }
  if (!draftCorpus.value.trim()) {
    message.warning('草稿语料不能为空');
    return;
  }
  draftSaving.value = true;
  try {
    latestDraft.value = await saveCommentAngleRuleDraftApi({
      asset_key: selectedAsset.value.asset_key,
      created_by: currentOperator.value,
      draft_corpus: draftCorpus.value,
      rule_id: String(selectedDraftRule.value.rule_id || ''),
      source_row_no:
        Number(selectedDraftRule.value.source_row_no || 0) || undefined,
    });
    message.success(`草稿已保存 #${latestDraft.value.id}`);
  } catch (error: any) {
    message.error(error?.message || '保存草稿失败');
  } finally {
    draftSaving.value = false;
  }
}

async function testRuleDraft(count: number) {
  if (!selectedAsset.value?.asset_key || !selectedDraftRule.value) {
    message.warning('请先选择一条业务规则');
    return;
  }
  if (!draftCorpus.value.trim()) {
    message.warning('草稿语料不能为空');
    return;
  }
  draftTesting.value = true;
  generating.value = true;
  try {
    const result = await startCommentBatchApi({
      asset_key: selectedAsset.value.asset_key,
      count,
      created_by: currentOperator.value,
      draft_corpus: draftCorpus.value,
      draft_rule_id: String(selectedDraftRule.value.rule_id || ''),
      draft_source_row_no:
        Number(selectedDraftRule.value.source_row_no || 0) || undefined,
      rule_id: String(selectedDraftRule.value.rule_id || ''),
      source_row_no:
        Number(selectedDraftRule.value.source_row_no || 0) || undefined,
    });
    message.success(
      `草稿测试完成：${result.execution.generated_count}/${result.execution.requested_limit}`,
    );
    selectedReport.value = result.report;
    await loadBatches();
  } catch (error: any) {
    message.error(error?.message || '草稿测试失败');
  } finally {
    draftTesting.value = false;
    generating.value = false;
  }
}

async function publishRuleDraft() {
  if (!latestDraft.value) {
    message.warning('请先保存草稿');
    return;
  }
  if (hasUnsavedDraftChanges.value) {
    message.warning('当前草稿有未保存修改，请先保存草稿');
    return;
  }
  draftPublishing.value = true;
  try {
    const result = await publishCommentAngleRuleDraftApi(latestDraft.value.id, {
      created_by: currentOperator.value,
    });
    latestDraft.value = result.draft;
    message.success(`已发布为业务规则 v${result.asset.version_no}`);
    selectedSummary.value = null;
    selectedAsset.value = null;
    await loadRuleAssets();
    const summary = ruleAssets.value.find((asset) => asset.id === result.asset.id);
    await openAsset(summary || result.asset);
    draftEditorOpen.value = false;
  } catch (error: any) {
    message.error(error?.message || '发布草稿失败');
  } finally {
    draftPublishing.value = false;
  }
}

function showPreflightFailure(preflight: {
  checks: Array<{ label: string; message: string; status: string }>;
}) {
  const failures = preflight.checks.filter((item) => item.status === 'fail');
  Modal.warning({
    title: '生成前检查未通过',
    content:
      failures.map((item) => `${item.label}：${item.message}`).join('；') ||
      '请检查业务规则和生文配置。',
  });
}

const beforeUpload: UploadProps['beforeUpload'] = async (file) => {
  const name = file.name.toLowerCase();
  if (!name.endsWith('.csv') && !name.endsWith('.xlsx')) {
    message.warning('只支持 .csv 或 .xlsx 文件');
    return Upload.LIST_IGNORE;
  }

  pendingFile.value = file;
  packageType.value = inferPackageTypeFromFileName(file.name);
  displayName.value = displayNameFromFile(file.name);
  uploadConfirmOpen.value = true;
  return Upload.LIST_IGNORE;
};

async function confirmUpload() {
  if (!pendingFile.value) {
    message.warning('请先选择文件');
    return;
  }
  if (!displayName.value.trim()) {
    message.warning('请填写业务规则名称');
    return;
  }

  importing.value = true;
  try {
    const payload = {
      asset_key: assetKeyFromDisplayName(displayName.value, packageType.value),
      created_by: currentOperator.value,
      display_name: displayName.value.trim(),
      file: pendingFile.value,
    };
    const result =
      packageType.value === 'comment_angle'
        ? await importCommentAngleRuleSetApi(payload)
        : await importProductExperienceRuleSetApi(payload);
    message.success(`导入完成：${result.summary_json?.rule_count || 0} 条规则`);
    selectedSummary.value = null;
    selectedAsset.value = null;
    uploadConfirmOpen.value = false;
    pendingFile.value = null;
    await loadRuleAssets();
  } catch {
    message.error('导入失败，请检查文件格式');
  } finally {
    importing.value = false;
  }
}

function cancelUpload() {
  if (importing.value) return;
  uploadConfirmOpen.value = false;
  pendingFile.value = null;
}

function packageLabel(assetType?: string) {
  const config = Object.values(rulePackageConfigs).find(
    (item) => item.assetType === assetType,
  );
  return config?.label || assetType || '-';
}

function examplesCount(record: Record<string, any>) {
  return Array.isArray(record.examples) ? record.examples.length : 0;
}

function supplementsCount(record: Record<string, any>) {
  return Array.isArray(record.supplements) ? record.supplements.length : 0;
}

function ruleKey(record: Record<string, any>) {
  return [
    record.rule_id || '',
    record.source_row_no || '',
    record.comment_angle || '',
    record.product_experience || '',
  ].join('::');
}

function ruleDisplayName(record: Record<string, any>) {
  return (
    String(
      record.comment_angle ||
        record.product_experience ||
        record.topic ||
        record.rule_id ||
        '',
    ).trim() || `规则 ${record.source_row_no || ''}`.trim()
  );
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function displayNameFromFile(fileName: string) {
  return fileName.replace(/\.[^.]+$/, '').trim() || fileName;
}

function inferPackageTypeFromFileName(fileName: string): RulePackageType {
  const normalizedFileName = fileName.toLowerCase();
  if (normalizedFileName.includes('产品使用体验')) {
    return 'product_experience';
  }
  if (
    normalizedFileName.includes('评论切角') ||
    normalizedFileName.includes('评论')
  ) {
    return 'comment_angle';
  }
  return packageType.value;
}

function shortHash(text: string) {
  let hash = 0;
  for (const char of text) {
    hash = (hash * 31 + (char.codePointAt(0) ?? 0)) >>> 0;
  }
  return hash.toString(36);
}

function assetKeyFromDisplayName(name: string, type: RulePackageType) {
  const normalizedName = name.trim();
  const asciiSlug = normalizedName
    .normalize('NFKD')
    .replaceAll(/[\u0300-\u036F]/g, '')
    .toLowerCase()
    .replaceAll(/[^a-z0-9]+/g, '_')
    .replaceAll(/^_+|_+$/g, '')
    .slice(0, 48);
  // asset_key 是内部版本化资产标识，运营只维护名称；中文文件名用短 hash 保持稳定。
  const suffix = asciiSlug || shortHash(normalizedName);
  return `${rulePackageConfigs[type].defaultAssetKey}_${suffix}`.slice(0, 120);
}

onMounted(() => {
  loadRuleAssets();
  loadBatches();
});

watch(
  () => route.query.batch_id,
  () => {
    selectedReport.value = null;
    loadBatches();
  },
);

watch(showHiddenRules, () => {
  loadRuleAssets();
});

watch(
  () => [
    draftEditorOpen.value,
    draftCorpus.value,
    selectedDraftRule.value?.rule_id,
    selectedDraftRule.value?.source_row_no,
    selectedAsset.value?.id,
    selectedReport.value?.batch_id,
    selectedReportSummary.value?.generated_count,
    reportFailureCount.value,
    reportRiskCount.value,
  ],
  () => {
    if (draftEditorOpen.value) {
      syncDraftChatContext();
    }
  },
);

watch(
  () => chatStore.draftFillPayload,
  async (payload) => {
    if (!payload) return;
    let currentRuleId = String(selectedDraftRule.value?.rule_id || '');
    let currentSourceRowNo =
      Number(selectedDraftRule.value?.source_row_no || 0) || null;
    if (!selectedDraftRule.value || draftEditorOpen.value === false) {
      const targetRule = selectedRuleItems.value.find((item) => {
        const ruleMatches =
          !payload.rule_id || String(item.rule_id || '') === payload.rule_id;
        const sourceMatches =
          payload.source_row_no === null ||
          Number(item.source_row_no || 0) === payload.source_row_no;
        return ruleMatches && sourceMatches;
      });
      if (targetRule) {
        selectedDraftRule.value = targetRule;
        draftCorpus.value = String(targetRule.corpus || '');
        latestDraft.value = null;
        await loadLatestDraft(targetRule);
        draftEditorOpen.value = true;
        currentRuleId = String(targetRule.rule_id || '');
        currentSourceRowNo = Number(targetRule.source_row_no || 0) || null;
      }
    }
    const ruleMatches = !payload.rule_id || payload.rule_id === currentRuleId;
    const sourceMatches =
      payload.source_row_no === null || payload.source_row_no === currentSourceRowNo;
    if (!selectedDraftRule.value || !ruleMatches || !sourceMatches) {
      message.warning('Chat 返回的草稿不属于当前业务规则，已忽略');
      chatStore.clearDraftFillPayload(payload.request_id);
      return;
    }
    draftEditorOpen.value = true;
    draftCorpus.value = payload.draft_corpus;
    syncDraftChatContext();
    message.success('已填入草稿，请确认后再保存或试跑');
    chatStore.clearDraftFillPayload(payload.request_id);
  },
);
</script>

<template>
  <div class="business-rule-page production-workbench p-4">
    <div class="page-toolbar">
      <div class="page-title-block">
        <div class="eyebrow">MAGA CONTENT OPS</div>
        <h1>生产工作台</h1>
        <p>业务规则、生成、复盘集中处理。</p>
      </div>
      <Space wrap>
        <Button @click="loadBatches">
          <template #icon><ReloadOutlined /></template>
          刷新批次
        </Button>
        <Upload
          :accept="ruleUploadAccept"
          :before-upload="beforeUpload"
          :disabled="importing"
          :show-upload-list="false"
        >
          <Button type="primary" :loading="importing">
            <template #icon><UploadOutlined /></template>
            上传业务规则
          </Button>
        </Upload>
      </Space>
    </div>

    <div class="workbench-layout">
      <div class="workbench-sidebar">
        <Card class="selector-card" title="业务规则" :bordered="false">
          <template #extra>
            <Space>
              <span class="history-toggle-label">历史/调试</span>
              <Switch v-model:checked="showHiddenRules" size="small" />
              <Button size="small" @click="loadRuleAssets">
                <template #icon><ReloadOutlined /></template>
                刷新
              </Button>
            </Space>
          </template>
          <Space class="rule-form" direction="vertical">
            <Upload
              :accept="ruleUploadAccept"
              :before-upload="beforeUpload"
              :disabled="importing"
              :show-upload-list="false"
            >
              <Button block type="primary" :loading="importing">
                <template #icon><UploadOutlined /></template>
                上传文件
              </Button>
            </Upload>
          </Space>

          <Spin :spinning="loading">
            <Empty v-if="ruleAssets.length === 0" description="暂无业务规则" />
            <div v-else class="rule-package-list">
              <button
                v-for="asset in ruleAssets"
                :key="asset.id"
                class="rule-package-option"
                :class="{ active: selectedSummary?.id === asset.id }"
                type="button"
                @click="openAsset(asset)"
              >
                <span class="option-main">
                  <span class="option-title">
                    {{ asset.display_name || packageLabel(asset.asset_type) }}
                  </span>
                  <Tag>{{ packageLabel(asset.asset_type) }}</Tag>
                  <Tag v-if="asset.hidden" color="orange">历史/调试</Tag>
                </span>
                <span class="option-meta">
                  v{{ asset.version_no }} · {{ asset.item_count ?? '-' }} 条
                </span>
                <span class="option-meta">
                  {{ asset.source_name || '-' }}
                </span>
              </button>
            </div>
          </Spin>
        </Card>

        <Card class="history-card" title="历史批次" :bordered="false">
          <template #extra>
            <Button size="small" @click="loadBatches">
              <template #icon><ReloadOutlined /></template>
              刷新
            </Button>
          </template>
          <Spin :spinning="batchLoading">
            <Empty v-if="batchList.length === 0" description="暂无批次" />
            <div v-else class="batch-list">
              <button
                v-for="batch in batchList"
                :key="batch.batch_id"
                class="batch-list-item"
                :class="{ active: selectedReport?.batch_id === batch.batch_id }"
                type="button"
                @click="openReport(batch.batch_id)"
              >
                <span class="batch-title">
                  <span>{{ batch.product_topic }}</span>
                  <Tag :color="statusColor(batch.status)">
                    {{ statusLabel(batch.status) }}
                  </Tag>
                </span>
                <span class="batch-meta">
                  #{{ batch.batch_id }} · {{ batch.batch_code || '-' }}
                </span>
                <span class="batch-meta">
                  {{ batch.summary.generated_count }}/{{
                    batch.summary.total_count
                  }}
                  条 · 失败 {{ failedCountOf(batch.summary) }} · 红线通过
                  {{ batch.summary.hard_pass_count }}
                </span>
              </button>
            </div>
            <div v-if="batchTotal" class="batch-total">
              共 {{ batchTotal }} 个批次
            </div>
          </Spin>
        </Card>
      </div>

      <div class="workbench-primary">
        <Card class="control-card" :bordered="false">
          <template #title>
            <Space>
              <span>当前生产配置</span>
              <Tag v-if="selectedAsset">{{ selectedPackageTypeLabel }}</Tag>
            </Space>
          </template>
          <template #extra>
            <Space>
              <Button
                v-if="isSelectedCommentRuleSet"
                :disabled="!selectedAsset"
                :loading="generating"
                @click="openFocusGeneration"
              >
                选择一条业务规则进行测试
              </Button>
            </Space>
          </template>

          <template v-if="selectedAsset">
            <div class="config-summary">
              <div class="config-title">
                <strong>{{ selectedPackageName }}</strong>
                <span>{{ selectedSourceName }}</span>
              </div>
              <div class="config-meta-grid">
                <div class="metric-block">
                  <span>版本</span>
                  <strong>v{{ selectedAsset.version_no }}</strong>
                </div>
                <div class="metric-block">
                  <span>规则</span>
                  <strong>{{ selectedRuleCount }}</strong>
                </div>
                <div class="metric-block">
                  <span>示例</span>
                  <strong>{{ selectedExampleCount }}</strong>
                </div>
                <div class="metric-block">
                  <span>默认生成</span>
                  <strong>{{ selectedDefaultGenerationCount }}</strong>
                </div>
                <div class="metric-block">
                  <span>上传人</span>
                  <strong>{{ selectedAsset.created_by || '-' }}</strong>
                </div>
                <div class="metric-block">
                  <span>更新时间</span>
                  <strong>{{ selectedPackageUpdatedAt }}</strong>
                </div>
              </div>
            </div>

            <div class="preflight-strip">
              <div class="preflight-item ready">
                <span>业务规则</span>
                <strong>已选</strong>
              </div>
              <div class="preflight-item pending">
                <span>系统关键词</span>
                <strong>待校验</strong>
              </div>
              <div class="preflight-item pending">
                <span>Expert</span>
                <strong>待校验</strong>
              </div>
              <div class="preflight-item pending">
                <span>模型路由</span>
                <strong>待校验</strong>
              </div>
            </div>

            <div v-if="selectedWarnings.length > 0" class="warning-row">
              <Tag
                v-for="warning in selectedWarnings"
                :key="warning"
                color="orange"
              >
                {{ warning }}
              </Tag>
            </div>
          </template>
          <Empty v-else description="暂无当前业务规则" />
        </Card>

        <Card class="rule-list-card" title="业务规则列表" :bordered="false">
          <template #extra>
            <Space v-if="selectedAsset">
              <Tag>{{ selectedItems.length }} 条</Tag>
              <Tag v-if="isSelectedCommentRuleSet" color="blue">可单条测试</Tag>
            </Space>
          </template>
          <template v-if="selectedAsset">
            <Table
              :columns="previewColumns"
              :data-source="selectedItems"
              :pagination="false"
              :row-key="ruleKey"
              :scroll="{ x: 1120, y: 520 }"
              size="small"
            >
              <template #bodyCell="{ column, record, text }">
                <template v-if="column.key === 'corpus'">
                  <div class="corpus-cell">
                    {{ formatValue(text) }}
                  </div>
                </template>
                <template v-else-if="column.key === 'examples'">
                  {{ examplesCount(record) }}
                </template>
                <template v-else-if="column.key === 'supplements'">
                  {{ supplementsCount(record) }}
                </template>
                <template v-else-if="column.key === 'action'">
                  <Space>
                    <Button size="small" @click="openDraftEditor(record)">
                      <template #icon><EditOutlined /></template>
                      编辑
                    </Button>
                    <Button size="small" type="primary" @click="openRuleGeneration(record)">
                      测试
                    </Button>
                    <Button size="small" @click="openRuleChatCopilot(record)">
                      <template #icon><MessageOutlined /></template>
                      去 Chat
                    </Button>
                  </Space>
                </template>
              </template>
            </Table>
          </template>
          <Empty v-else description="暂无业务规则列表" />
        </Card>
      </div>
    </div>

    <Row class="diagnostics-row" :gutter="[16, 16]">
      <Col :xs="24">
        <Card class="batch-detail-card" :bordered="false">
          <template #title>
            <Space wrap>
              <span>批次明细</span>
              <Tag v-if="selectedReport">
                {{ selectedReport.batch_code || `#${selectedReport.batch_id}` }}
              </Tag>
              <Tag v-if="selectedReport" :color="statusColor(selectedReport.status)">
                {{ statusLabel(selectedReport.status) }}
              </Tag>
            </Space>
          </template>
          <template #extra>
            <Button
              size="small"
              :disabled="!selectedReport"
              :loading="reportLoading"
              @click="selectedReport && openReport(selectedReport.batch_id)"
            >
              <template #icon><ReloadOutlined /></template>
              刷新
            </Button>
          </template>
          <Spin :spinning="reportLoading">
            <template v-if="selectedReport">
              <div class="batch-detail-summary">
                <div class="metric-block">
                  <span>业务规则</span>
                  <strong>{{ selectedReport.asset_key }}</strong>
                </div>
                <div class="metric-block">
                  <span>总数</span>
                  <strong>{{ selectedReportSummary?.total_count ?? '-' }}</strong>
                </div>
                <div class="metric-block">
                  <span>已生成</span>
                  <strong>{{ selectedReportSummary?.generated_count ?? '-' }}</strong>
                </div>
                <div class="metric-block">
                  <span>失败</span>
                  <strong>{{ reportFailureCount }}</strong>
                </div>
                <div class="metric-block">
                  <span>红线通过</span>
                  <strong>{{ selectedReportSummary?.hard_pass_count ?? '-' }}</strong>
                </div>
                <div class="metric-block">
                  <span>待关注</span>
                  <strong>{{ reportRiskCount }}</strong>
                </div>
              </div>

              <Table
                class="batch-detail-table"
                :columns="batchDetailColumns"
                :data-source="selectedReportItems"
                :pagination="{ pageSize: 10, showSizeChanger: false }"
                :scroll="{ x: 980, y: 520 }"
                row-key="item_id"
                size="small"
              >
                <template #bodyCell="{ column, record, text }">
                  <template v-if="column.key === 'status'">
                    <Tag :color="statusColor(record.status)">
                      {{ statusLabel(record.status) }}
                    </Tag>
                  </template>
                  <template v-else-if="column.key === 'body'">
                    <div v-if="record.body" class="batch-body-cell">
                      {{ record.body }}
                    </div>
                    <div v-else class="batch-error-cell">
                      {{ itemFailureMessage(record) }}
                    </div>
                  </template>
                  <template v-else-if="column.key === 'hard_pass'">
                    <Tag :color="passColor(record.hard_pass)">
                      {{ passLabel(record.hard_pass) }}
                    </Tag>
                  </template>
                  <template v-else-if="column.key === 'risk'">
                    <Space v-if="riskTagsOf(record).length" wrap size="small">
                      <Tag
                        v-for="tag in riskTagsOf(record)"
                        :key="tag.label"
                        :color="tag.color"
                      >
                        {{ tag.label }}
                      </Tag>
                    </Space>
                    <span v-else class="muted">-</span>
                  </template>
                  <template v-else>
                    {{ formatValue(text) }}
                  </template>
                </template>
              </Table>
            </template>
            <Empty v-else description="请选择左侧历史批次查看明细" />
          </Spin>
        </Card>
      </Col>
    </Row>

    <Modal
      v-model:open="uploadConfirmOpen"
      title="确认上传"
      ok-text="上传"
      cancel-text="取消"
      :confirm-loading="importing"
      @ok="confirmUpload"
      @cancel="cancelUpload"
    >
      <Space class="confirm-form" direction="vertical">
        <div class="confirm-file">
          <span>文件</span>
          <strong>{{ pendingFile?.name || '-' }}</strong>
        </div>
        <div class="form-field">
          <div class="field-label">上传为</div>
          <Select
            v-model:value="packageType"
            :disabled="importing"
            :options="packageTypeOptions"
            class="full-width"
          />
        </div>
        <div class="form-field">
          <div class="field-label">业务规则名称</div>
          <Input
            v-model:value="displayName"
            :disabled="importing"
            placeholder="默认取文件名，可编辑"
          />
        </div>
      </Space>
    </Modal>

    <Modal
      v-model:open="focusGenerateOpen"
      title="选择一条业务规则进行测试"
      ok-text="开始生成"
      cancel-text="取消"
      :confirm-loading="generating"
      @ok="generateFocusedCommentAngle"
    >
      <Space class="confirm-form" direction="vertical">
        <div class="form-field">
          <div class="field-label">业务规则</div>
          <Select
            v-model:value="focusGenerateForm.rule_key"
            :disabled="generating"
            :options="selectedCommentAngleOptions"
            class="full-width"
            show-search
          />
        </div>
        <div class="form-field">
          <div class="field-label">生成数量</div>
          <InputNumber
            v-model:value="focusGenerateForm.count"
            :disabled="generating"
            :max="50"
            :min="1"
            class="full-width"
          />
        </div>
      </Space>
    </Modal>

    <Drawer
      v-model:open="draftEditorOpen"
      class="rule-draft-drawer"
      placement="right"
      title="单条规则草稿调试"
      width="720"
    >
      <template v-if="selectedDraftRule">
        <Space class="draft-meta" direction="vertical">
          <div>
            <Tag>{{ selectedDraftRule.rule_id || '-' }}</Tag>
            <Tag>行 {{ selectedDraftRule.source_row_no || '-' }}</Tag>
            <Tag v-if="latestDraft">草稿 #{{ latestDraft.id }}</Tag>
          </div>
          <div class="draft-title-row">
            <strong>{{ selectedDraftRule.comment_angle || '-' }}</strong>
          </div>
        </Space>

        <div class="draft-section">
          <div class="field-label">正式版本语料</div>
          <div class="readonly-corpus">
            {{ selectedDraftRule.corpus || '-' }}
          </div>
        </div>

        <div class="draft-section">
          <div class="field-label">草稿语料</div>
          <Textarea
            v-model:value="draftCorpus"
            :auto-size="{ minRows: 16, maxRows: 28 }"
            :disabled="draftSaving || draftTesting || draftPublishing"
            placeholder="在这里修改当前单条评论切角语料。保存草稿不会影响正式业务规则。"
          />
        </div>

        <div v-if="latestDraft" class="draft-hint">
          基于 v{{ latestDraft.base_version_no || '-' }} 保存，状态：
          {{ latestDraft.status }}
          <span v-if="hasUnsavedDraftChanges"> · 有未保存修改</span>
        </div>

        <Space class="draft-actions" wrap>
          <Button :icon="h(SaveOutlined)" :loading="draftSaving" @click="saveRuleDraft">
            保存草稿
          </Button>
          <Button :loading="draftTesting" @click="testRuleDraft(10)">
            用草稿跑10条
          </Button>
          <Button :loading="draftTesting" @click="testRuleDraft(50)">
            用草稿跑50条
          </Button>
          <Button
            danger
            type="primary"
            :disabled="!latestDraft || hasUnsavedDraftChanges"
            :icon="h(CheckOutlined)"
            :loading="draftPublishing"
            @click="publishRuleDraft"
          >
            发布为新版本
          </Button>
        </Space>
      </template>
      <Empty v-else description="请选择一条业务规则" />
    </Drawer>
  </div>
</template>

<style scoped>
.business-rule-page {
  background: var(--maga-page-bg, #f5f7fb);
  min-height: 100%;
}

.business-rule-page :deep(.ant-card) {
  background: var(--maga-surface, #fff);
  border: 1px solid var(--maga-border, #edf0f5);
  border-radius: 8px;
}

.business-rule-page :deep(.ant-card-head) {
  border-bottom-color: var(--maga-border, #edf0f5);
  min-height: 48px;
}

.business-rule-page :deep(.ant-card-head-title) {
  color: var(--maga-text, #1f2937);
  font-weight: 700;
}

.business-rule-page :deep(.ant-card-body) {
  padding: 16px;
}

.page-toolbar {
  align-items: flex-end;
  background: var(--maga-surface, #fff);
  border: 1px solid var(--maga-border, #edf0f5);
  border-radius: 8px;
  display: flex;
  gap: 16px;
  justify-content: space-between;
  margin-bottom: 16px;
  padding: 16px 18px;
}

.page-title-block {
  min-width: 0;
}

.eyebrow {
  color: var(--maga-text-faint, #8c8c8c);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
  margin-bottom: 4px;
}

.page-title-block h1 {
  color: var(--maga-text, #1f2937);
  font-size: 24px;
  font-weight: 700;
  line-height: 1.25;
  margin: 0;
}

.page-title-block p {
  color: var(--maga-text-muted, #667085);
  font-size: 13px;
  line-height: 1.7;
  margin: 6px 0 0;
}

.workbench-layout {
  display: grid;
  gap: 16px;
  grid-template-columns: minmax(280px, 336px) minmax(0, 1fr);
}

.workbench-sidebar,
.workbench-primary {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.selector-card,
.history-card {
  min-width: 0;
}

.rule-form,
.full-width {
  width: 100%;
}

.form-field,
.confirm-form {
  width: 100%;
}

.field-label {
  color: var(--maga-text-muted, #595959);
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 6px;
}

.rule-package-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 16px;
}

.rule-package-option,
.batch-list-item {
  background: var(--maga-surface-soft, #f8fafc);
  border: 1px solid var(--maga-border, #edf0f5);
  border-radius: 8px;
  color: inherit;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-height: 76px;
  padding: 10px 12px;
  text-align: left;
  transition:
    background 0.16s ease,
    border-color 0.16s ease,
    box-shadow 0.16s ease;
  width: 100%;
}

.rule-package-option:hover,
.batch-list-item:hover,
.rule-package-option.active,
.batch-list-item.active {
  background: var(--maga-surface-active, #f0f6ff);
  border-color: #1677ff;
  box-shadow: 0 0 0 1px rgb(22 119 255 / 8%);
}

.option-main,
.batch-title {
  align-items: flex-start;
  display: flex;
  font-weight: 600;
  gap: 8px;
  justify-content: space-between;
}

.option-title,
.batch-title span {
  color: var(--maga-text, #1f2937);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.option-meta,
.batch-meta,
.batch-total,
.content-meta {
  color: var(--maga-text-muted, #667085);
  display: block;
  font-size: 12px;
  line-height: 1.5;
}

.control-card {
  min-height: 234px;
}

.config-summary {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.config-title {
  align-items: baseline;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.config-title strong {
  color: var(--maga-text, #1f2937);
  font-size: 18px;
}

.config-title span {
  color: var(--maga-text-muted, #667085);
  font-size: 13px;
}

.config-meta-grid,
.preflight-strip {
  display: grid;
  gap: 10px;
}

.config-meta-grid {
  grid-template-columns: repeat(6, minmax(0, 1fr));
}

.metric-block,
.preflight-item {
  background: var(--maga-surface-soft, #f8fafc);
  border: 1px solid var(--maga-border, #edf0f5);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 60px;
  padding: 10px 12px;
}

.metric-block span,
.preflight-item span {
  color: var(--maga-text-muted, #667085);
  font-size: 12px;
}

.metric-block strong,
.preflight-item strong {
  color: var(--maga-text, #1f2937);
  font-size: 14px;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preflight-strip {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-top: 16px;
}

.preflight-item {
  min-height: 52px;
  position: relative;
}

.preflight-item::before {
  border-radius: 999px;
  content: '';
  height: 6px;
  position: absolute;
  right: 12px;
  top: 12px;
  width: 6px;
}

.preflight-item.ready::before {
  background: #16a34a;
}

.preflight-item.pending::before {
  background: #f59e0b;
}

.confirm-file {
  align-items: center;
  background: var(--maga-surface-soft, #f5f7fb);
  border: 1px solid var(--maga-border, #edf0f5);
  border-radius: 8px;
  display: flex;
  gap: 12px;
  justify-content: space-between;
  padding: 10px 12px;
}

.confirm-file span {
  color: var(--maga-text-muted, #8c8c8c);
}

.confirm-file strong {
  color: var(--maga-text, #262626);
  font-weight: 600;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.warning-row {
  margin-top: 12px;
}

.batch-list {
  display: flex;
  font-weight: 600;
  flex-direction: column;
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
  padding-right: 4px;
}

.batch-list-item {
  min-height: 92px;
}

.batch-total {
  margin-top: 10px;
}

.rule-list-card {
  min-height: 620px;
}

.diagnostics-row {
  margin-top: 16px;
}

.batch-detail-card {
  min-height: 420px;
}

.batch-detail-summary {
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(180px, 2fr) repeat(5, minmax(96px, 1fr));
  margin-bottom: 14px;
}

.batch-detail-table {
  margin-top: 4px;
}

.batch-body-cell {
  color: var(--maga-text, #1f2937);
  line-height: 1.65;
  max-height: 88px;
  overflow: auto;
  white-space: pre-wrap;
}

.batch-error-cell {
  color: var(--maga-error, #cf1322);
  line-height: 1.6;
  white-space: pre-wrap;
}

.corpus-cell {
  display: -webkit-box;
  line-height: 1.55;
  max-width: 520px;
  max-height: 66px;
  overflow: hidden;
  white-space: pre-line;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.draft-meta {
  background: var(--maga-surface-soft, #f8fafc);
  border: 1px solid var(--maga-border, #edf0f5);
  border-radius: 8px;
  margin-bottom: 16px;
  padding: 12px;
  width: 100%;
}

.draft-title-row {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.draft-title-row strong {
  min-width: 0;
  overflow-wrap: anywhere;
}

.draft-section {
  margin-top: 16px;
}

.readonly-corpus {
  background: var(--maga-surface-soft, #f8fafc);
  border: 1px solid var(--maga-border, #edf0f5);
  border-radius: 8px;
  color: var(--maga-text, #1f2937);
  line-height: 1.7;
  max-height: 180px;
  overflow: auto;
  padding: 12px;
  white-space: pre-wrap;
}

.draft-hint {
  color: var(--maga-text-muted, #667085);
  font-size: 12px;
  margin-top: 12px;
}

.draft-actions {
  border-top: 1px solid var(--maga-border, #edf0f5);
  margin-top: 18px;
  padding-top: 14px;
}

.muted {
  color: var(--maga-text-muted, #8c8c8c);
  display: block;
  font-size: 12px;
  margin-top: 2px;
}

.history-toggle-label {
  color: var(--maga-text-muted, #667085);
  font-size: 12px;
}

@media (prefers-color-scheme: dark) {
  .business-rule-page {
    --maga-page-bg: #060913;
    --maga-surface: #0b1020;
    --maga-surface-soft: #111827;
    --maga-surface-active: #0f2346;
    --maga-border: #223047;
    --maga-text: #eef2ff;
    --maga-text-muted: #9ca3af;
    --maga-text-faint: #6b7280;
    --maga-error-soft: #241416;
    --maga-error-border: #7f1d1d;
  }
}

@media (max-width: 768px) {
  .page-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .workbench-layout,
  .config-meta-grid,
  .preflight-strip {
    grid-template-columns: 1fr;
  }
}

@media (min-width: 769px) and (max-width: 1180px) {
  .config-meta-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .preflight-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
