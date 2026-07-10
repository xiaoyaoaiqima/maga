<script setup lang="ts">
import type { UploadProps } from 'ant-design-vue';

import type { AssetsApi } from '#/api/core/assets';
import type { ChatContext } from '#/api/core/chat';
import type { ContentAgentApi } from '#/api/core/content-agent';

import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import { useUserStore } from '@vben/stores';

import {
  DownloadOutlined,
  EditOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MessageOutlined,
  ReloadOutlined,
  SaveOutlined,
  UploadOutlined,
} from '@ant-design/icons-vue';
import {
  Button,
  Card,
  Checkbox,
  Drawer,
  Empty,
  Input,
  InputNumber,
  message,
  Modal,
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
  importCommentBusinessRuleSetApi,
  importArticleBusinessRuleSetApi,
  publishCommentBusinessRuleDraftApi,
  saveCommentBusinessRuleDraftApi,
  updateBusinessRuleExamplesApi,
} from '#/api/core/assets';
import {
  getContentBatchListApi,
  getContentBatchReportApi,
  preflightContentGenerationApi,
  startContentBatchApi,
  startCommentBatchApi,
} from '#/api/core/content-agent';
import { useMagaChatStore } from '#/store';

type RulePackageType = 'comment_business' | 'article_business';
type BatchScope = 'asset' | 'rule';

const ARTICLE_TEST_ARTICLES_PER_RUN = 2;

interface RulePackageConfig {
  accept: string;
  assetType: string;
  defaultAssetKey: string;
  defaultDisplayName: string;
  label: string;
}

const rulePackageConfigs: Record<RulePackageType, RulePackageConfig> = {
  comment_business: {
    accept: '.csv,.xlsx',
    assetType: 'comment_business_rule_set',
    defaultAssetKey: 'yuanyue_comment_activity',
    defaultDisplayName: '源悦-评论业务规则',
    label: '评论业务规则',
  },
  article_business: {
    accept: '.csv,.xlsx',
    assetType: 'article_business_rule_set',
    defaultAssetKey: 'yuanyue_product_experience',
    defaultDisplayName: '源悦生文业务规则',
    label: '帖子/生文业务规则',
  },
};

const ruleAssetTypes = [
  ...new Set([
    ...Object.values(rulePackageConfigs).map((item) => item.assetType),
    'comment_business_rule_set',
  ]),
];
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
const packageType = ref<RulePackageType>('comment_business');
const displayName = ref(rulePackageConfigs.comment_business.defaultDisplayName);
const pendingFile = ref<File | null>(null);
const uploadAssetKeyOverride = ref('');
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
const batchScope = ref<BatchScope>('asset');
const compareBatchIds = ref<number[]>([]);
const compareDrawerOpen = ref(false);
const compareLoading = ref(false);
const contrastTesting = ref(false);
const compareReports = ref<ContentAgentApi.BatchReport[]>([]);
const compareReportLabels = ref<string[]>([]);
const ruleSearchText = ref('');
const selectedRuleKey = ref('');
const packagePaneCollapsed = ref(false);
const batchDetailOpen = ref(false);
const preflightResult = ref<ContentAgentApi.PreflightResponse | null>(null);
const preflightLoading = ref(false);
const packageSearchText = ref('');
const viewportHeight = ref(typeof window === 'undefined' ? 900 : window.innerHeight);
const focusGenerateOpen = ref(false);
const focusGenerateForm = ref({
  rule_key: '',
  count: 10,
});
const draftEditorOpen = ref(false);
const draftSaving = ref(false);
const draftTesting = ref(false);
const selectedDraftRule = ref<Record<string, any> | null>(null);
const draftCorpus = ref('');
const exampleSaving = ref(false);
const examplesText = ref('');
const hasUnsavedRuleChanges = computed(() => {
  if (!activeRule.value || selectedDraftRuleKey.value !== ruleKey(activeRule.value)) {
    return false;
  }
  return draftCorpus.value.trim() !== String(activeRule.value.corpus || '').trim();
});

const selectedRuleItems = computed(() => {
  const items = selectedAsset.value?.content_json?.items;
  return Array.isArray(items) ? items : [];
});
const selectedItems = computed(() => selectedRuleItems.value);
const filteredRuleAssets = computed(() => {
  const keyword = packageSearchText.value.trim().toLowerCase();
  if (!keyword) return ruleAssets.value;
  return ruleAssets.value.filter((asset) => {
    const haystack = [
      asset.display_name,
      asset.asset_key,
      asset.source_name,
      packageLabel(asset),
      asset.version_no ? `v${asset.version_no}` : '',
    ]
      .map((value) => String(value || '').toLowerCase())
      .join('\n');
    return haystack.includes(keyword);
  });
});
const filteredRuleItems = computed(() => {
  const keyword = ruleSearchText.value.trim().toLowerCase();
  if (!keyword) return selectedRuleItems.value;
  return selectedRuleItems.value.filter((item) => {
    const haystack = [
      item.business_rule,
      item.corpus,
      item.rule_id,
      item.source_row_no,
    ]
      .map((value) => String(value || '').toLowerCase())
      .join('\n');
    return haystack.includes(keyword);
  });
});
const activeRule = computed(() => {
  if (!selectedRuleKey.value) return filteredRuleItems.value[0] || null;
  return (
    selectedRuleItems.value.find((item) => ruleKey(item) === selectedRuleKey.value) ||
    filteredRuleItems.value[0] ||
    null
  );
});
const selectedDraftRuleKey = computed(() =>
  selectedDraftRule.value ? ruleKey(selectedDraftRule.value) : '',
);
const activeDraftReady = computed(
  () => Boolean(activeRule.value) && selectedDraftRuleKey.value === ruleKey(activeRule.value),
);
const selectedReportItems = computed(() => selectedReport.value?.items || []);
const currentBatchPreviewItems = computed(() => selectedReportItems.value.slice(0, 2));
const selectedReportSummary = computed(
  () => selectedReport.value?.summary || null,
);
const isSelectedCommentRuleSet = computed(
  () =>
    ['comment_business_rule_set'].includes(
      selectedAsset.value?.asset_type || '',
    ),
);
const isSelectedArticleBusinessRuleSet = computed(
  () =>
    ['article_business_rule_set'].includes(selectedAsset.value?.asset_type || ''),
);
const isSelectedBusinessRuleSet = computed(
  () => isSelectedCommentRuleSet.value || isSelectedArticleBusinessRuleSet.value,
);
const selectedRuleOptions = computed(() => {
  return selectedRuleItems.value
    .filter((item) => String(ruleDisplayName(item) || '').trim())
    .map((item) => ({
      label: ruleDisplayName(item),
      value: ruleKey(item),
    }));
});
const ruleTableScrollY = computed(() =>
  Math.max(420, Math.min(720, viewportHeight.value - 500)),
);

const currentOperator = computed(
  () =>
    userStore.userInfo?.realName ||
    userStore.userInfo?.username ||
    'maga-operator',
);

const packageTypeOptions = computed(() =>
  Object.entries(rulePackageConfigs)
    .map(([value, config]) => ({
      label: config.label,
      value,
    })),
);

const selectedMeta = computed(() => selectedAsset.value?.metadata_json || {});
const selectedWarnings = computed(() =>
  Array.isArray(selectedMeta.value.warnings)
    ? selectedMeta.value.warnings.filter(
        (warning: unknown) => !String(warning).includes('较硬约束'),
      )
    : [],
);

const selectedPackageName = computed(
  () =>
    selectedAsset.value?.display_name || selectedSummary.value?.display_name,
);
const uploadTargetAssetKey = computed(() => {
  if (packageType.value === 'article_business' && uploadAssetKeyOverride.value) {
    return uploadAssetKeyOverride.value;
  }
  const config = rulePackageConfigs[packageType.value];
  if (
    selectedAsset.value?.asset_type === config.assetType &&
    packageTypeOfAsset(selectedAsset.value) === packageType.value
  ) {
    return selectedAsset.value.asset_key;
  }
  return config.defaultAssetKey;
});
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
const selectedAssetBatches = computed(() => batchList.value);
const selectedAssetBatchTotal = computed(() => batchTotal.value);
const batchScopeTitle = computed(() =>
  batchScope.value === 'rule' ? '当前规则最近测试' : '规则包最近测试',
);
const batchScopeEmptyText = computed(() =>
  batchScope.value === 'rule'
    ? '当前规则暂无测试批次'
    : '当前规则包暂无测试批次',
);
const canUseRuleBatchScope = computed(() => Boolean(activeRule.value));
const inspectorReportTitle = computed(() => {
  if (!inspectorReport.value) return '';
  return inspectorReport.value.batch_code || `#${inspectorReport.value.batch_id}`;
});
const inspectorReport = computed(() => {
  if (!selectedAsset.value || !selectedReport.value) return null;
  return selectedReport.value.asset_key === selectedAsset.value.asset_key
    ? selectedReport.value
    : null;
});
const inspectorReportSummary = computed(() => inspectorReport.value?.summary || null);
const compareLeftReport = computed(() => compareReports.value[0] || null);
const compareRightReport = computed(() => compareReports.value[1] || null);
const compareLeftLabel = computed(() => compareReportLabels.value[0] || '基准批次');
const compareRightLabel = computed(() => compareReportLabels.value[1] || '对比批次');
const compareMetricRows = computed(() => {
  if (!compareLeftReport.value || !compareRightReport.value) return [];
  const left = compareLeftReport.value.summary;
  const right = compareRightReport.value.summary;
  return [
    {
      key: 'total',
      label: '总数',
      left: left.total_count,
      right: right.total_count,
      delta: right.total_count - left.total_count,
    },
    {
      key: 'generated',
      label: '生成',
      left: left.generated_count,
      right: right.generated_count,
      delta: right.generated_count - left.generated_count,
    },
    {
      key: 'failed',
      label: '失败',
      left: failedCountOf(left),
      right: failedCountOf(right),
      delta: failedCountOf(right) - failedCountOf(left),
    },
    {
      key: 'risk',
      label: '风险',
      left: batchRiskCount(left),
      right: batchRiskCount(right),
      delta: batchRiskCount(right) - batchRiskCount(left),
    },
    {
      key: 'hard_pass_rate',
      label: '红线通过率',
      left: hardPassRate(left),
      right: hardPassRate(right),
      delta: hardPassRate(right) - hardPassRate(left),
      percent: true,
    },
  ];
});
const batchDetailColumns: any[] = [
  { title: '序号', dataIndex: 'item_no', key: 'item_no', width: 72 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 110 },
  { title: '标题', dataIndex: 'title', key: 'title', width: 180 },
  { title: '正文', dataIndex: 'body', key: 'body', minWidth: 320 },
  { title: '抽中示例', key: 'selected_examples', width: 220 },
  { title: '红线', dataIndex: 'hard_pass', key: 'hard_pass', width: 90 },
  { title: '风险', key: 'risk', width: 220 },
  { title: '字数', dataIndex: 'body_chars', key: 'body_chars', width: 80 },
];

const previewColumns = computed<any[]>(() => {
  if (isSelectedArticleBusinessRuleSet.value) {
    return [
      {
        title: '规则',
        key: 'rule_summary',
        minWidth: 280,
      },
      { title: '语料', dataIndex: 'corpus', key: 'corpus', minWidth: 320 },
      { title: '示例', key: 'counts', width: 90 },
    ];
  }
  return [
    {
      title: '规则',
      key: 'rule_summary',
      minWidth: 300,
    },
    { title: '操作', key: 'action', width: 230 },
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
  return summary.failed_count ?? Math.max(0, summary.total_count - summary.generated_count);
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

function batchItemPreviewText(item: ContentAgentApi.BatchReportItem | Record<string, any>) {
  return String(item.body || item.body_preview || itemFailureMessage(item) || '').trim();
}

function batchItemNote(item: ContentAgentApi.BatchReportItem | Record<string, any>) {
  if (item.status === 'failed') return itemFailureMessage(item);
  if (item.rewrite_required) return item.rewrite_reason || '需要改写';
  return '';
}

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
  if (!selectedAsset.value || !selectedDraftRule.value || !isSelectedBusinessRuleSet.value) {
    return null;
  }
  const examples = [
    ...normalizeTextList(selectedDraftRule.value.examples),
    ...normalizeTextList(selectedDraftRule.value.supplements),
  ];
  return {
    page: 'business_rules',
    asset_key: selectedAsset.value.asset_key,
    asset_type: selectedAsset.value.asset_type,
    asset_version: selectedAsset.value.version_no || null,
    rule_id: String(selectedDraftRule.value.rule_id || ''),
    source_row_no:
      Number(selectedDraftRule.value.source_row_no || 0) || null,
    business_rule: String(selectedDraftRule.value.business_rule || ''),
    corpus: String(selectedDraftRule.value.corpus || ''),
    draft_corpus: draftCorpus.value,
    examples,
    supplements: [],
    test_report_summary: buildChatReportSummary(),
  };
}

function syncDraftChatContext() {
  if (!draftEditorOpen.value) return;
  const context = buildDraftChatContext();
  if (context) chatStore.setContext(context);
}

function setInlineDraftRule(record: Record<string, any>) {
  selectedDraftRule.value = record;
  draftCorpus.value = String(record.corpus || '');
  syncExampleEditorFromRule(record);
  // 重要逻辑：编辑器内嵌到右侧 Inspector，保留这个状态只用于 Chat 上下文同步。
  draftEditorOpen.value = true;
}

function syncExampleEditorFromRule(record: Record<string, any> | null) {
  const examples = normalizeTextList(record?.examples);
  const supplements = normalizeTextList(record?.supplements);
  examplesText.value = [...examples, ...supplements].join('\n');
}

function textToLines(value: string) {
  return value
    .split(/\r?\n/)
    .map((item) => item.replace(/^[\s\-*•\d.、．]+/, '').trim())
    .filter(Boolean);
}

function focusInlineDraftEditor() {
  window.requestAnimationFrame(() => {
    const textarea = document.querySelector<HTMLTextAreaElement>(
      '.inline-draft-editor textarea',
    );
    textarea?.focus();
  });
}

function updateViewportHeight() {
  viewportHeight.value = window.innerHeight;
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
    ruleAssets.value = groups.flat().sort(compareRuleAssetsByUpdatedTime);
    const selectedStillVisible = ruleAssets.value.some(
      (asset) =>
        asset.id === selectedSummary.value?.id ||
        (asset.asset_type === selectedSummary.value?.asset_type &&
          asset.asset_key === selectedSummary.value?.asset_key),
    );
    if (!selectedStillVisible) {
      selectedSummary.value = null;
      selectedAsset.value = null;
    } else if (selectedSummary.value) {
      selectedSummary.value =
        ruleAssets.value.find((asset) => asset.id === selectedSummary.value?.id) ||
        ruleAssets.value.find(
          (asset) =>
            asset.asset_type === selectedSummary.value?.asset_type &&
            asset.asset_key === selectedSummary.value?.asset_key,
        ) ||
        selectedSummary.value;
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
  preflightResult.value = null;
  ruleSearchText.value = '';
  selectedRuleKey.value = selectedRuleItems.value[0]
    ? ruleKey(selectedRuleItems.value[0])
    : '';
  if (selectedRuleItems.value[0]) {
    setInlineDraftRule(selectedRuleItems.value[0]);
  }
  selectedReport.value = null;
  compareBatchIds.value = [];
  await loadBatches();
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
    const params: Parameters<typeof getContentBatchListApi>[0] = {
      asset_key: selectedAsset.value?.asset_key,
      limit: 20,
      offset: 0,
    };
    if (batchScope.value === 'rule' && activeRule.value) {
      params.rule_id = String(activeRule.value.rule_id || '') || null;
      params.source_row_no =
        Number(activeRule.value.source_row_no || 0) || null;
    }
    const data = await getContentBatchListApi(params);
    batchList.value = data?.items || [];
    batchTotal.value = data?.total || 0;
    compareBatchIds.value = compareBatchIds.value.filter((batchId) =>
      batchList.value.some((batch) => batch.batch_id === batchId),
    );

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
    await syncAssetRecentReport();
  } finally {
    batchLoading.value = false;
  }
};

async function syncAssetRecentReport() {
  const latestBatch = selectedAssetBatches.value[0];
  if (!latestBatch) return;
  if (selectedReport.value?.asset_key === selectedAsset.value?.asset_key) return;
  await openReport(latestBatch.batch_id, false);
}

function openFocusGeneration() {
  if (
    !selectedAsset.value ||
    (!isSelectedCommentRuleSet.value && !isSelectedArticleBusinessRuleSet.value)
  ) {
    message.warning('请先选择可测试的业务规则');
    return;
  }
  const firstRuleKey = selectedRuleOptions.value[0]?.value;
  if (!firstRuleKey) {
    message.warning('当前业务规则没有可测试的规则');
    return;
  }
  focusGenerateForm.value = {
    rule_key: focusGenerateForm.value.rule_key || firstRuleKey,
    count: focusGenerateForm.value.count || 10,
  };
  focusGenerateOpen.value = true;
}

function openRuleGeneration(record: Record<string, any>) {
  selectRule(record);
  if (!isSelectedCommentRuleSet.value && !isSelectedArticleBusinessRuleSet.value) {
    message.warning('当前业务规则类型暂不支持单条测试');
    return;
  }
  focusGenerateForm.value = {
    rule_key: ruleKey(record),
    count: focusGenerateForm.value.count || 10,
  };
  focusGenerateOpen.value = true;
}

async function generateFocusedRule() {
  if (!selectedAsset.value?.asset_key) {
    message.warning('请先选择业务规则');
    return;
  }
  const targetRule = selectedRuleItems.value.find(
    (item) => ruleKey(item) === focusGenerateForm.value.rule_key,
  );
  const businessRuleName = String(targetRule?.business_rule || '').trim();
  if (!targetRule) {
    message.warning('请选择一条业务规则');
    return;
  }
  generating.value = true;
  try {
    const preflight = await preflightContentGenerationApi({
      asset_key: selectedAsset.value.asset_key,
      asset_type: selectedAsset.value.asset_type,
    });
    preflightResult.value = preflight;
    if (!preflight.passed) {
      showPreflightFailure(preflight);
      return;
    }
    const result = isSelectedCommentRuleSet.value
      ? await startCommentBatchApi({
          asset_key: selectedAsset.value.asset_key,
          business_rule: businessRuleName || null,
          count: Number(focusGenerateForm.value.count || 10),
          created_by: currentOperator.value,
          rule_id: String(targetRule.rule_id || ''),
          source_row_no: Number(targetRule.source_row_no || 0) || undefined,
        })
      : await startContentBatchApi({
          asset_key: selectedAsset.value.asset_key,
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
  selectRule(record);
  if (!selectedAsset.value?.asset_key || !isSelectedBusinessRuleSet.value) {
    message.warning('请先选择业务规则');
    return;
  }
  setInlineDraftRule(record);
  syncDraftChatContext();
  focusInlineDraftEditor();
}

async function openRuleChatCopilot(record: Record<string, any>) {
  selectRule(record);
  if (!selectedAsset.value?.asset_key || !isSelectedBusinessRuleSet.value) {
    message.warning('请先选择业务规则');
    return;
  }
  setInlineDraftRule(record);
  const context = buildDraftChatContext();
  if (!context) {
    message.warning('当前业务规则上下文不可用');
    return;
  }
  chatStore.openWithContext(context);
}

async function saveRuleVersion() {
  if (!selectedAsset.value?.asset_key || !selectedDraftRule.value) {
    message.warning('请先选择一条业务规则');
    return;
  }
  if (!draftCorpus.value.trim()) {
    message.warning('规则语料不能为空');
    return;
  }
  const targetRuleKey = ruleKey(selectedDraftRule.value);
  draftSaving.value = true;
  try {
    const savedDraft = await saveCommentBusinessRuleDraftApi({
      asset_key: selectedAsset.value.asset_key,
      created_by: currentOperator.value,
      draft_corpus: draftCorpus.value,
      rule_id: String(selectedDraftRule.value.rule_id || ''),
      source_row_no:
        Number(selectedDraftRule.value.source_row_no || 0) || undefined,
    });
    const result = await publishCommentBusinessRuleDraftApi(savedDraft.id, {
      created_by: currentOperator.value,
    });
    selectedSummary.value = result.asset as unknown as AssetsApi.AssetSummary;
    selectedAsset.value = result.asset;
    selectedRuleKey.value = targetRuleKey;
    const updatedRule = selectedRuleItems.value.find(
      (item) => ruleKey(item) === targetRuleKey,
    );
    if (updatedRule) {
      setInlineDraftRule(updatedRule);
    }
    message.success(`已保存为业务规则 v${result.asset.version_no}`);
    await loadRuleAssets();
  } catch (error: any) {
    message.error(error?.message || '保存新版本失败');
  } finally {
    draftSaving.value = false;
  }
}

async function saveRuleExamples() {
  if (!selectedAsset.value?.asset_key || !activeRule.value) {
    message.warning('请先选择一条业务规则');
    return;
  }
  exampleSaving.value = true;
  try {
    const updatedAsset = await updateBusinessRuleExamplesApi({
      asset_key: selectedAsset.value.asset_key,
      asset_type: isSelectedArticleBusinessRuleSet.value ? 'article' : 'comment',
      created_by: currentOperator.value,
      examples: textToLines(examplesText.value),
      supplements: [],
      rule_id: String(activeRule.value.rule_id || ''),
      source_row_no: Number(activeRule.value.source_row_no || 0) || undefined,
    });
    selectedAsset.value = updatedAsset;
    const updatedRule = selectedRuleItems.value.find(
      (item) => ruleKey(item) === selectedRuleKey.value,
    );
    if (updatedRule) {
      setInlineDraftRule(updatedRule);
    }
    message.success('示例已保存为规则包新版本');
    await loadRuleAssets();
  } catch (error: any) {
    message.error(error?.message || '保存示例失败');
  } finally {
    exampleSaving.value = false;
  }
}

async function runPreflightCheck() {
  if (!selectedAsset.value?.asset_key) {
    message.warning('请先选择业务规则');
    return;
  }
  preflightLoading.value = true;
  try {
    preflightResult.value = await preflightContentGenerationApi({
      asset_key: selectedAsset.value.asset_key,
      asset_type: selectedAsset.value.asset_type,
    });
    if (preflightResult.value.passed) {
      message.success('生成前检查通过');
    } else {
      showPreflightFailure(preflightResult.value);
    }
  } catch {
    message.error('生成前检查失败');
  } finally {
    preflightLoading.value = false;
  }
}

async function openBatchDetail(batchId?: number) {
  const targetBatchId =
    batchId || inspectorReport.value?.batch_id || selectedAssetBatches.value[0]?.batch_id;
  if (!targetBatchId) {
    message.warning('暂无可查看的测试批次');
    return;
  }
  await openReport(targetBatchId);
  batchDetailOpen.value = true;
}

async function selectRecentBatch(batchId: number) {
  await openReport(batchId);
}

async function changeBatchScope(scope: BatchScope) {
  if (scope === 'rule' && !canUseRuleBatchScope.value) {
    message.warning('请先选择一条业务规则');
    return;
  }
  if (batchScope.value === scope) return;
  batchScope.value = scope;
  selectedReport.value = null;
  compareBatchIds.value = [];
  await loadBatches();
}

function isBatchSelectedForCompare(batchId: number) {
  return compareBatchIds.value.includes(batchId);
}

function toggleCompareBatch(batchId: number) {
  if (isBatchSelectedForCompare(batchId)) {
    compareBatchIds.value = compareBatchIds.value.filter((id) => id !== batchId);
    return;
  }
  if (compareBatchIds.value.length >= 2) {
    message.warning('最多选择两个批次对比');
    return;
  }
  compareBatchIds.value = [...compareBatchIds.value, batchId];
}

async function openBatchCompare() {
  if (compareBatchIds.value.length !== 2) {
    message.warning('请选择两个批次对比');
    return;
  }
  compareLoading.value = true;
  compareDrawerOpen.value = true;
  compareReportLabels.value = ['基准批次', '对比批次'];
  try {
    compareReports.value = await Promise.all(
      compareBatchIds.value.map((batchId) => getContentBatchReportApi(batchId)),
    );
  } finally {
    compareLoading.value = false;
  }
}

function buildRuleDraftTestPayload(
  count: number,
  draftText?: string,
  createdBySuffix?: string,
) {
  if (!selectedAsset.value?.asset_key || !selectedDraftRule.value) {
    return null;
  }
  const articleTestCount = isSelectedArticleBusinessRuleSet.value
    ? count * ARTICLE_TEST_ARTICLES_PER_RUN
    : count;
  const payload = {
    asset_key: selectedAsset.value.asset_key,
    count: articleTestCount,
    created_by: createdBySuffix
      ? `${currentOperator.value}-${createdBySuffix}`
      : currentOperator.value,
    rule_id: String(selectedDraftRule.value.rule_id || ''),
    source_row_no:
      Number(selectedDraftRule.value.source_row_no || 0) || undefined,
  };
  const normalizedDraftText = String(draftText || '').trim();
  if (!normalizedDraftText) {
    return payload;
  }
  return {
    ...payload,
    draft_corpus: normalizedDraftText,
    draft_rule_id: String(selectedDraftRule.value.rule_id || ''),
    draft_source_row_no:
      Number(selectedDraftRule.value.source_row_no || 0) || undefined,
  };
}

async function testRuleDraft(
  count: number,
  options: { postprocessMode?: 'generate_only' } = {},
) {
  if (!selectedAsset.value?.asset_key || !selectedDraftRule.value) {
    message.warning('请先选择一条业务规则');
    return;
  }
  if (!draftCorpus.value.trim()) {
    message.warning('规则语料不能为空');
    return;
  }
  draftTesting.value = true;
  generating.value = true;
  try {
    const isQuickTrial = options.postprocessMode === 'generate_only';
    const sharedPayload = buildRuleDraftTestPayload(count, draftCorpus.value);
    if (!sharedPayload) return;
    const result = isSelectedArticleBusinessRuleSet.value
      ? await startContentBatchApi({
          ...sharedPayload,
          articles_per_prompt: ARTICLE_TEST_ARTICLES_PER_RUN,
          postprocess_mode: options.postprocessMode,
        })
      : await startCommentBatchApi(sharedPayload);
    message.success(formatRuleTestSuccessMessage(result, count, isQuickTrial));
    selectedReport.value = result.report;
    await loadBatches();
  } catch (error: any) {
    message.error(error?.message || '规则测试失败');
  } finally {
    draftTesting.value = false;
    generating.value = false;
  }
}

async function runRuleDraftContrast() {
  if (!selectedAsset.value?.asset_key || !selectedDraftRule.value || !activeRule.value) {
    message.warning('请先选择一条业务规则');
    return;
  }
  if (!isSelectedArticleBusinessRuleSet.value) {
    message.warning('对照组先只支持帖子/生文业务规则');
    return;
  }
  if (!draftCorpus.value.trim()) {
    message.warning('规则语料不能为空');
    return;
  }
  if (!hasUnsavedRuleChanges.value) {
    message.warning('请先在编辑框里改出实验组语料');
    return;
  }
  const basePayload = buildRuleDraftTestPayload(1, undefined, 'contrast-base');
  const draftPayload = buildRuleDraftTestPayload(1, draftCorpus.value, 'contrast-draft');
  if (!basePayload || !draftPayload) return;

  contrastTesting.value = true;
  generating.value = true;
  compareLoading.value = true;
  compareDrawerOpen.value = true;
  compareReports.value = [];
  compareReportLabels.value = ['A 正式语料', 'B 编辑框语料'];
  try {
    const [baseResult, draftResult] = await Promise.all([
      startContentBatchApi({
        ...basePayload,
        articles_per_prompt: ARTICLE_TEST_ARTICLES_PER_RUN,
        postprocess_mode: 'generate_only',
      }),
      startContentBatchApi({
        ...draftPayload,
        articles_per_prompt: ARTICLE_TEST_ARTICLES_PER_RUN,
        postprocess_mode: 'generate_only',
      }),
    ]);
    compareBatchIds.value = [baseResult.batch_id, draftResult.batch_id];
    compareReports.value = [baseResult.report, draftResult.report];
    selectedReport.value = draftResult.report;
    message.success(
      `对照试跑完成：A #${baseResult.batch_id}，B #${draftResult.batch_id}`,
    );
    await loadBatches();
  } catch (error: any) {
    message.error(error?.message || '对照试跑失败');
  } finally {
    compareLoading.value = false;
    contrastTesting.value = false;
    generating.value = false;
  }
}

function formatRuleTestSuccessMessage(
  result: ContentAgentApi.BatchStartResponse,
  requestedRuns: number,
  isQuickTrial = false,
) {
  const summary = result.report?.summary;
  const generated = summary?.generated_count ?? result.execution.generated_count;
  const failed = summary ? failedCountOf(summary) : result.execution.failed_count;
  const hardPass = summary?.hard_pass_count ?? '-';
  const unit = isSelectedArticleBusinessRuleSet.value ? '篇' : '条';
  const runLabel = isSelectedArticleBusinessRuleSet.value
    ? `模型调用 ${requestedRuns} 次`
    : `跑 ${requestedRuns} 条`;
  if (isQuickTrial) {
    return `快速试跑完成 #${result.batch_id}：${runLabel}，原始生成 ${generated}${unit}，失败 ${failed}`;
  }
  return `测试完成 #${result.batch_id}：${runLabel}，生成 ${generated}${unit}，失败 ${failed}，红线通过 ${hardPass}`;
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
  const config = rulePackageConfigs[packageType.value];
  const inferredArticleTarget =
    packageType.value === 'article_business'
      ? inferArticleBusinessTargetFromFileName(file.name)
      : null;
  uploadAssetKeyOverride.value = inferredArticleTarget?.assetKey || '';
  displayName.value =
    inferredArticleTarget?.displayName ||
    (selectedAsset.value?.asset_type === config.assetType &&
    packageTypeOfAsset(selectedAsset.value) === packageType.value
      ? selectedPackageName.value || config.defaultDisplayName
      : config.defaultDisplayName || displayNameFromFile(file.name));
  uploadConfirmOpen.value = true;
  return Upload.LIST_IGNORE;
};

function downloadSimpleRuleTemplate() {
  const csv = [
    '业务规则名称,规则语料,示例',
    '"有货后先不急着转奶","写什么：妈妈问到、买到、等到或收到 a2 了，所以先继续喝 a2，转奶这事先放一放。\n怎么说：像评论区接一句或顺手报个信，可以很短；别写成官方补货通知、催别人囤货、库存焦虑或转奶教程。","刚问柜姐说有货了，立马去下单。\n能买到的话我还是先不换了\n转奶太麻烦了，买到就继续喝a2"',
  ].join('\n');
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = '业务规则_三列模板.csv';
  link.click();
  URL.revokeObjectURL(url);
}

function csvCell(value: unknown) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`;
}

function safeFilename(value: string) {
  return String(value || '业务规则包')
    .replace(/[\\/:*?"<>|]/g, '_')
    .replace(/\s+/g, '_')
    .slice(0, 80);
}

function downloadSelectedRulePackage() {
  if (!selectedAsset.value) {
    message.warning('请先选择一个业务规则包');
    return;
  }
  const items = selectedRuleItems.value;
  if (!items.length) {
    message.warning('当前规则包暂无可导出的规则');
    return;
  }
  const rows = [
    ['业务规则名称', '规则语料', '示例'],
    ...items.map((item) => [
      ruleDisplayName(item),
      item.corpus || '',
      [...normalizeTextList(item.examples), ...normalizeTextList(item.supplements)].join('\n'),
    ]),
  ];
  const csv = rows.map((row) => row.map(csvCell).join(',')).join('\n');
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${safeFilename(selectedPackageName.value || selectedAsset.value.asset_key)}_v${selectedAsset.value.version_no}_业务规则包.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

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
      // 重要逻辑：业务规则包导入应生成“同一包的新版本”，不能按文件名新建单条规则包。
      asset_key: uploadTargetAssetKey.value,
      created_by: currentOperator.value,
      display_name: displayName.value.trim(),
      file: pendingFile.value,
    };
    const result =
      packageType.value === 'comment_business'
        ? await importCommentBusinessRuleSetApi(payload)
        : await importArticleBusinessRuleSetApi(payload);
    message.success(`导入完成：${result.summary_json?.rule_count || 0} 条规则`);
    selectedSummary.value = null;
    selectedAsset.value = null;
    uploadConfirmOpen.value = false;
    pendingFile.value = null;
    uploadAssetKeyOverride.value = '';
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
  uploadAssetKeyOverride.value = '';
}

function packageTypeOfAsset(asset?: Pick<AssetsApi.AssetSummary, 'asset_key' | 'asset_type' | 'display_name' | 'source_name'> | null) {
  if (!asset?.asset_type) return null;
  if (asset.asset_type === 'comment_business_rule_set') return 'comment_business';
  if (asset.asset_type === 'article_business_rule_set') return 'article_business';
  return null;
}

function packageLabel(asset?: Pick<AssetsApi.AssetSummary, 'asset_key' | 'asset_type' | 'display_name' | 'source_name'> | string) {
  const assetType = typeof asset === 'string' ? asset : asset?.asset_type;
  const inferredType = typeof asset === 'string' ? null : packageTypeOfAsset(asset);
  if (inferredType) return rulePackageConfigs[inferredType].label;
  const config = Object.values(rulePackageConfigs).find(
    (item) => item.assetType === assetType,
  );
  return config?.label || assetType || '-';
}

function examplesCount(record: Record<string, any>) {
  return normalizeTextList(record.examples).length + normalizeTextList(record.supplements).length;
}

function supplementsCount(record: Record<string, any>) {
  return Array.isArray(record.supplements) ? record.supplements.length : 0;
}

function fullExamplePoolCount(record: Record<string, any>) {
  return examplesCount(record);
}

function defaultExampleSampleCount(_record: Record<string, any>) {
  return 3;
}

function selectedExamplesOf(record: Record<string, any>) {
  const businessRule = record.generation_snapshot?.business_rule || {};
  return Array.isArray(businessRule.examples)
    ? businessRule.examples.map((item: unknown) => String(item || '').trim()).filter(Boolean)
    : [];
}

function ruleKey(record: Record<string, any>) {
  return [
    record.rule_id || '',
    record.source_row_no || '',
    record.business_rule || '',
  ].join('::');
}

function selectRule(record: Record<string, any>) {
  selectedRuleKey.value = ruleKey(record);
  if (isSelectedBusinessRuleSet.value) {
    setInlineDraftRule(record);
  }
}

function isActiveRule(record: Record<string, any>) {
  return ruleKey(record) === selectedRuleKey.value;
}

function ruleDisplayName(record: Record<string, any>) {
  return (
    String(
      record.business_rule ||
        record.rule_id ||
        '',
    ).trim() || `规则 ${record.source_row_no || ''}`.trim()
  );
}

function batchRiskCount(summary?: ContentAgentApi.BatchReportSummary | null) {
  if (!summary) return 0;
  return (
    failedCountOf(summary) +
    (summary.forbidden_hit_count || 0) +
    (summary.remaining_rewrite_required_count || 0) +
    (summary.similarity_warning_count || 0)
  );
}

function hardPassRate(summary?: ContentAgentApi.BatchReportSummary | null) {
  if (!summary?.generated_count) return 0;
  return Math.round((summary.hard_pass_count / summary.generated_count) * 1000) / 10;
}

function compareValue(value: number, percent?: boolean) {
  return percent ? `${value}%` : String(value);
}

function compareDelta(value: number, percent?: boolean) {
  const normalized = percent ? Math.round(value * 10) / 10 : value;
  const prefix = normalized > 0 ? '+' : '';
  return `${prefix}${normalized}${percent ? '%' : ''}`;
}

function compareDeltaClass(value: number, key: string) {
  if (value === 0) return 'neutral';
  if (key === 'failed' || key === 'risk') return value > 0 ? 'negative' : 'positive';
  return value > 0 ? 'positive' : 'negative';
}

function riskSamplesOf(report?: ContentAgentApi.BatchReport | null, limit = 5) {
  return (report?.items || [])
    .filter(
      (item) =>
        item.status === 'failed' ||
        item.hard_pass === false ||
        riskTagsOf(item).length > 0,
    )
    .slice(0, limit);
}

function formatBatchTime(value?: null | string) {
  if (!value) return '-';
  return value.replace('T', ' ').slice(0, 16);
}

function assetTimeMs(value?: null | string) {
  if (!value) return 0;
  const time = Date.parse(value);
  return Number.isNaN(time) ? 0 : time;
}

function compareRuleAssetsByUpdatedTime(
  left: AssetsApi.AssetSummary,
  right: AssetsApi.AssetSummary,
) {
  const leftTime = assetTimeMs(left.update_time || left.create_time);
  const rightTime = assetTimeMs(right.update_time || right.create_time);
  if (leftTime !== rightTime) return rightTime - leftTime;
  return (right.id || 0) - (left.id || 0);
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
  if (normalizedFileName.includes('评论')) {
    return 'comment_business';
  }
  if (
    normalizedFileName.includes('帖子') ||
    normalizedFileName.includes('文章') ||
    normalizedFileName.includes('生文') ||
    normalizedFileName.includes('产品使用体验') ||
    normalizedFileName.includes('源悦') ||
    normalizedFileName.includes('旺玥') ||
    normalizedFileName.includes('a2')
  ) {
    return 'article_business';
  }
  return packageType.value;
}

function inferArticleBusinessTargetFromFileName(fileName: string) {
  const normalizedFileName = fileName.toLowerCase();
  if (
    normalizedFileName.includes('源悦') ||
    normalizedFileName.includes('产品使用体验') ||
    normalizedFileName.includes('生文')
  ) {
    return {
      assetKey: 'yuanyue_product_experience',
      displayName: '源悦生文业务规则',
    };
  }
  if (normalizedFileName.includes('旺玥')) {
    return {
      assetKey: 'wangyue_article_business_rules',
      displayName: '0705旺玥活动-UGC业务规则',
    };
  }
  if (normalizedFileName.includes('a2')) {
    return {
      assetKey: 'a2_sentiment_post_activity',
      displayName: 'A2舆情相关帖子业务规则',
    };
  }
  return null;
}

onMounted(() => {
  loadRuleAssets();
  updateViewportHeight();
  window.addEventListener('resize', updateViewportHeight);
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateViewportHeight);
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
  () => filteredRuleAssets.value.map((asset) => asset.id).join('|'),
  () => {
    if (!packageSearchText.value.trim() || filteredRuleAssets.value.length === 0) {
      return;
    }
    const selectedVisible = filteredRuleAssets.value.some(
      (asset) =>
        asset.id === selectedSummary.value?.id ||
        (asset.asset_type === selectedSummary.value?.asset_type &&
          asset.asset_key === selectedSummary.value?.asset_key),
    );
    if (!selectedVisible) {
      void openAsset(filteredRuleAssets.value[0]);
    }
  },
);

watch(
  () => filteredRuleItems.value.map((item) => ruleKey(item)).join('|'),
  () => {
    if (!filteredRuleItems.value.length) {
      selectedRuleKey.value = '';
      return;
    }
    const selectedVisible = filteredRuleItems.value.some(
      (item) => ruleKey(item) === selectedRuleKey.value,
    );
    if (!selectedVisible) {
      selectedRuleKey.value = ruleKey(filteredRuleItems.value[0]);
    }
  },
);

watch(
  () => selectedRuleKey.value,
  () => {
    if (batchScope.value !== 'rule') return;
    selectedReport.value = null;
    compareBatchIds.value = [];
    loadBatches();
  },
);

watch(
  () => [selectedAsset.value?.id, activeRule.value ? ruleKey(activeRule.value) : ''],
  () => {
    syncExampleEditorFromRule(activeRule.value);
  },
  { immediate: true },
);

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
    const matched = await ensureChatActionTargetRule(payload.rule_id, payload.source_row_no);
    if (!matched) {
      message.warning('Chat 返回的编辑内容不属于当前业务规则，已忽略');
      chatStore.clearDraftFillPayload(payload.request_id);
      return;
    }
    draftCorpus.value = payload.draft_corpus;
    syncDraftChatContext();
    focusInlineDraftEditor();
    message.success('已填入编辑框，请确认后再保存或测试');
    chatStore.clearDraftFillPayload(payload.request_id);
  },
);

watch(
  () => chatStore.examplesFillPayload,
  async (payload) => {
    if (!payload) return;
    const matched = await ensureChatActionTargetRule(payload.rule_id, payload.source_row_no);
    if (!matched) {
      message.warning('Chat 返回的示例不属于当前业务规则，已忽略');
      chatStore.clearExamplesFillPayload(payload.request_id);
      return;
    }
    examplesText.value = payload.examples.join('\n');
    syncDraftChatContext();
    message.success('已填入示例，请确认后再保存示例');
    chatStore.clearExamplesFillPayload(payload.request_id);
  },
);

async function ensureChatActionTargetRule(ruleId?: null | string, sourceRowNo?: null | number) {
  const targetRuleId = ruleId ? String(ruleId) : null;
  const targetSourceRowNo = typeof sourceRowNo === 'number' ? sourceRowNo : null;
  let currentRuleId = String(selectedDraftRule.value?.rule_id || '');
  let currentSourceRowNo = Number(selectedDraftRule.value?.source_row_no || 0) || null;
  if (!selectedDraftRule.value || draftEditorOpen.value === false) {
    const targetRule = selectedRuleItems.value.find((item) => {
      const ruleMatches = !targetRuleId || String(item.rule_id || '') === targetRuleId;
      const sourceMatches =
        targetSourceRowNo === null || Number(item.source_row_no || 0) === targetSourceRowNo;
      return ruleMatches && sourceMatches;
    });
    if (targetRule) {
      selectedRuleKey.value = ruleKey(targetRule);
      setInlineDraftRule(targetRule);
      currentRuleId = String(targetRule.rule_id || '');
      currentSourceRowNo = Number(targetRule.source_row_no || 0) || null;
    }
  }
  const ruleMatches = !targetRuleId || targetRuleId === currentRuleId;
  const sourceMatches = targetSourceRowNo === null || targetSourceRowNo === currentSourceRowNo;
  return Boolean(selectedDraftRule.value && ruleMatches && sourceMatches);
}
</script>

<template>
  <div class="business-rule-page production-workbench p-4">
    <div class="page-toolbar compact">
      <div class="page-title-block compact">
        <h1>业务规则工作台</h1>
        <span v-if="selectedAsset" class="toolbar-subtitle">
          {{ selectedPackageName }} · v{{ selectedAsset.version_no }}
        </span>
      </div>
      <Space wrap>
        <Button @click="loadRuleAssets">
          <template #icon><ReloadOutlined /></template>
          刷新规则
        </Button>
        <Button @click="loadBatches">
          <template #icon><ReloadOutlined /></template>
          刷新测试
        </Button>
        <Button @click="downloadSimpleRuleTemplate">
          下载规则模板
        </Button>
        <Button :disabled="!selectedAsset" @click="downloadSelectedRulePackage">
          <template #icon><DownloadOutlined /></template>
          导出规则包
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

    <div
      class="rule-workbench-shell"
      :class="{ 'package-pane-collapsed': packagePaneCollapsed }"
    >
      <aside class="rule-package-pane" :class="{ collapsed: packagePaneCollapsed }">
        <button
          v-if="packagePaneCollapsed"
          class="package-pane-expand"
          type="button"
          @click="packagePaneCollapsed = false"
        >
          <MenuUnfoldOutlined />
          <span>规则包</span>
        </button>

        <Card v-else class="pane-card fill-card" :bordered="false">
          <div class="pane-card-header">
            <div>
              <h2>业务规则包</h2>
              <span>
                {{ filteredRuleAssets.length }}/{{ ruleAssets.length }}
                个{{ showHiddenRules ? '规则包' : '可见规则包' }}
              </span>
            </div>
            <Space size="small">
              <span class="history-toggle-label">含隐藏</span>
              <Switch v-model:checked="showHiddenRules" size="small" />
              <Button
                size="small"
                type="text"
                title="收起规则包"
                @click="packagePaneCollapsed = true"
              >
                <template #icon><MenuFoldOutlined /></template>
              </Button>
            </Space>
          </div>

          <Spin :spinning="loading">
            <Empty v-if="ruleAssets.length === 0" description="暂无业务规则" />
            <template v-else>
              <Input
                v-model:value="packageSearchText"
                allow-clear
                class="package-search-input"
                placeholder="搜索规则包名称 / key / 文件名"
                size="small"
              />
              <Empty
                v-if="filteredRuleAssets.length === 0"
                description="没有匹配的规则包"
              />
              <div v-else class="rule-package-list">
                <button
                  v-for="asset in filteredRuleAssets"
                  :key="asset.id"
                  class="rule-package-option"
                  :class="{ active: selectedSummary?.id === asset.id }"
                  type="button"
                  @click="openAsset(asset)"
                >
                  <span class="option-main">
                    <span class="option-title">
                      {{ asset.display_name || packageLabel(asset) }}
                    </span>
                    <Tag>{{ packageLabel(asset) }}</Tag>
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
            </template>
          </Spin>
        </Card>
      </aside>

      <main class="rule-list-pane">
        <Card class="config-strip-card" :bordered="false">
          <template v-if="selectedAsset">
            <div class="config-strip">
              <div class="config-heading">
                <span>当前规则包</span>
                <strong>{{ selectedPackageName }}</strong>
                <span>v{{ selectedAsset.version_no }}</span>
              </div>
              <Space class="config-actions" size="small" wrap>
                <Button
                  size="small"
                  :disabled="!selectedAsset"
                  :loading="preflightLoading"
                  @click="runPreflightCheck"
                >
                  生成前检查
                </Button>
                <Tag
                  v-if="preflightResult"
                  :color="preflightResult.passed ? 'green' : 'orange'"
                >
                  {{ preflightResult.passed ? '检查通过' : '需处理' }}
                </Tag>
                <Tag v-for="warning in selectedWarnings" :key="warning" color="orange">
                  {{ warning }}
                </Tag>
              </Space>
            </div>
          </template>
          <Empty v-else description="暂无当前业务规则" />
        </Card>

        <Card class="rule-list-card fill-card" :bordered="false">
          <div class="list-card-header">
            <div>
              <h2>业务规则列表</h2>
              <span>
                {{ filteredRuleItems.length }}/{{ selectedItems.length }} 条
                <template v-if="isSelectedCommentRuleSet || isSelectedArticleBusinessRuleSet">
                  · 可单条测试
                </template>
              </span>
            </div>
            <Space>
              <Input
                v-model:value="ruleSearchText"
                allow-clear
                class="rule-search"
                placeholder="搜索业务规则、语料"
              />
                <Button
                  v-if="isSelectedCommentRuleSet || isSelectedArticleBusinessRuleSet"
                  :disabled="!selectedAsset"
                  :loading="generating"
                  @click="activeRule && openRuleGeneration(activeRule)"
                >
                用正式语料测试
                </Button>
            </Space>
          </div>

          <template v-if="selectedAsset">
            <Table
              class="rule-table"
              :columns="previewColumns"
              :custom-row="(record) => ({ onClick: () => selectRule(record) })"
              :data-source="filteredRuleItems"
              :pagination="false"
              :row-key="ruleKey"
              :row-class-name="(record) => (isActiveRule(record) ? 'active-rule-row' : '')"
              :scroll="{ x: isSelectedCommentRuleSet || isSelectedArticleBusinessRuleSet ? 560 : 720, y: ruleTableScrollY }"
              size="small"
            >
              <template #bodyCell="{ column, record, text }">
                <template v-if="column.key === 'rule_summary'">
                  <div class="rule-summary-cell">
                    <strong>{{ ruleDisplayName(record) }}</strong>
                    <p>{{ formatValue(record.corpus) }}</p>
                  </div>
                </template>
                <template v-else-if="column.key === 'corpus'">
                  <div class="corpus-cell">
                    {{ formatValue(text) }}
                  </div>
                </template>
                <template v-else-if="column.key === 'counts'">
                  <div class="count-cell">
                    <span>{{ examplesCount(record) }} 示例</span>
                    <small>生成时抽 {{ defaultExampleSampleCount(record) }} 条</small>
                  </div>
                </template>
                <template v-else-if="column.key === 'action'">
                  <Space>
                    <Button
                      v-if="isSelectedBusinessRuleSet"
                      size="small"
                      type="primary"
                      @click.stop="openRuleChatCopilot(record)"
                    >
                      <template #icon><MessageOutlined /></template>
                      去 Chat
                    </Button>
                    <Button v-if="isSelectedBusinessRuleSet" size="small" @click.stop="openDraftEditor(record)">
                      <template #icon><EditOutlined /></template>
                      编辑语料
                    </Button>
                    <Button size="small" @click.stop="openRuleGeneration(record)">
                      正式测试
                    </Button>
                  </Space>
                </template>
              </template>
            </Table>
          </template>
          <Empty v-else description="暂无业务规则列表" />
        </Card>
      </main>

      <aside class="rule-inspector-pane">
        <Card class="inspector-card fill-card" :bordered="false">
          <template v-if="activeRule">
              <div class="inspector-section">
                <div class="inspector-title">
                  <strong>{{ ruleDisplayName(activeRule) }}</strong>
                </div>
                <div class="inspector-meta">
                  <Tag>{{ activeRule.rule_id || '-' }}</Tag>
                  <Tag>
                    示例 {{ fullExamplePoolCount(activeRule) }} 条
                  </Tag>
                  <Tag>
                    生成时抽 {{ defaultExampleSampleCount(activeRule) }} 条/次
                  </Tag>
                </div>
              </div>

              <div v-if="isSelectedBusinessRuleSet" class="inspector-section">
                <div class="draft-workspace-header">
                  <div class="field-label">规则语料</div>
                  <Tag>当前 v{{ selectedAsset?.version_no || '-' }}</Tag>
                </div>
                <div class="inline-draft-editor">
                  <Textarea
                    v-model:value="draftCorpus"
                    :auto-size="{ minRows: 12, maxRows: 22 }"
                    :disabled="draftSaving || draftTesting"
                    placeholder="只写这条规则要表达什么、怎么说；示例在下方单独维护。"
                  />
                </div>

                <div class="draft-hint">
                  <template v-if="hasUnsavedRuleChanges">
                    有未保存修改。测试会直接使用当前框里的内容；保存会生成规则包新版本。
                  </template>
                  <template v-else>当前框内是规则包 v{{ selectedAsset?.version_no || '-' }} 的正式语料。</template>
                </div>

                <Space class="draft-actions inline-draft-actions" wrap>
                  <Button
                    :disabled="!hasUnsavedRuleChanges"
                    :icon="h(SaveOutlined)"
                    :loading="draftSaving"
                    type="primary"
                    @click="saveRuleVersion"
                  >
                    保存为新版本
                  </Button>
                  <Button
                    :disabled="!hasUnsavedRuleChanges"
                    :loading="contrastTesting"
                    @click="runRuleDraftContrast"
                    v-if="isSelectedArticleBusinessRuleSet"
                  >
                    快速对照 1 次
                  </Button>
                  <Button
                    :loading="draftTesting"
                    @click="testRuleDraft(1, { postprocessMode: 'generate_only' })"
                    v-if="isSelectedArticleBusinessRuleSet"
                  >
                    快速试跑 1 次
                  </Button>
                  <Button
                    :loading="draftTesting"
                    @click="testRuleDraft(1)"
                  >
                    {{ isSelectedArticleBusinessRuleSet ? '完整测试 1 次' : '测试 1 条' }}
                  </Button>
                  <Button
                    :loading="draftTesting"
                    @click="testRuleDraft(10)"
                  >
                    {{ isSelectedArticleBusinessRuleSet ? '完整测试 10 次并发' : '测试 10 条' }}
                  </Button>
                </Space>
              </div>

              <div v-if="isSelectedBusinessRuleSet" class="inspector-section">
                <div class="draft-workspace-header">
                  <div class="field-label">示例</div>
                  <Tag>{{ fullExamplePoolCount(activeRule) }} 条</Tag>
                </div>
                <Textarea
                  v-model:value="examplesText"
                  :auto-size="{ minRows: 8, maxRows: 16 }"
                  :disabled="exampleSaving"
                  placeholder="可为空，一行一条。生成时从这里随机抽 3 条作为 few-shot；示例只提供语气、场景颗粒和生活细节。"
                />
                <div class="draft-hint">
                  保存示例会生成规则包新版本；不会改动上方规则语料。
                </div>
                <Space class="draft-actions inline-draft-actions" wrap>
                  <Button :icon="h(SaveOutlined)" :loading="exampleSaving" @click="saveRuleExamples">
                    保存示例
                  </Button>
                </Space>
              </div>

              <div v-else class="inspector-section">
                <div class="field-label">正式语料</div>
                <div class="readonly-corpus inspector-corpus">
                  {{ activeRule.corpus || '-' }}
                </div>
              </div>
          </template>
          <Empty v-else description="请选择一条业务规则" />
        </Card>
      </aside>

      <Card class="recent-batches-card" :bordered="false">
        <Spin :spinning="batchLoading || reportLoading">
          <div class="recent-batches-layout">
            <div class="recent-batches-head">
              <div class="recent-batches-title-row">
                <div class="inspector-title">
                  <strong>{{ batchScopeTitle }}</strong>
                  <Tag>最近 {{ selectedAssetBatchTotal }} 个</Tag>
                </div>
                <div class="batch-scope-switch">
                  <Button
                    size="small"
                    :type="batchScope === 'asset' ? 'primary' : 'default'"
                    @click="changeBatchScope('asset')"
                  >
                    规则包
                  </Button>
                  <Button
                    size="small"
                    :disabled="!canUseRuleBatchScope"
                    :type="batchScope === 'rule' ? 'primary' : 'default'"
                    @click="changeBatchScope('rule')"
                  >
                    当前规则
                  </Button>
                </div>
              </div>
              <Space class="batch-footer-actions">
                <Button
                  :disabled="compareBatchIds.length !== 2"
                  @click="openBatchCompare"
                >
                  对比批次
                </Button>
                <Button
                  :disabled="!selectedAssetBatches.length"
                  @click="openBatchDetail()"
                >
                  查看完整明细
                </Button>
              </Space>
            </div>

            <template v-if="inspectorReport">
              <div class="recent-batch-summary">
                <div class="current-batch-strip">
                  <div class="current-batch-title">
                    <span>当前批次</span>
                    <strong>{{ inspectorReportTitle }}</strong>
                  </div>
                  <div class="current-batch-stats">
                    <Tag :color="statusColor(inspectorReport.status)">
                      {{ statusLabel(inspectorReport.status) }}
                    </Tag>
                    <span>
                      {{ inspectorReportSummary?.generated_count ?? '-' }}/{{
                        inspectorReportSummary?.total_count ?? '-'
                      }}
                      已生成
                    </span>
                    <span>失败 {{ failedCountOf(inspectorReportSummary) }}</span>
                    <span>风险 {{ batchRiskCount(inspectorReportSummary) }}</span>
                  </div>
                </div>
                <div v-if="currentBatchPreviewItems.length" class="current-batch-samples">
                  <div
                    v-for="item in currentBatchPreviewItems"
                    :key="item.item_id"
                    class="current-batch-sample"
                  >
                    <div class="current-batch-sample-head">
                      <Tag :color="statusColor(item.status)">
                        #{{ item.item_no }} · {{ statusLabel(item.status) }}
                      </Tag>
                      <strong>{{ item.title || '-' }}</strong>
                    </div>
                    <p>{{ batchItemPreviewText(item) }}</p>
                    <div v-if="batchItemNote(item)" class="current-batch-sample-note">
                      {{ batchItemNote(item) }}
                    </div>
                  </div>
                </div>
              </div>
            </template>

            <div v-if="selectedAssetBatches.length" class="batch-list compact-list">
              <button
                v-for="batch in selectedAssetBatches.slice(0, 6)"
                :key="batch.batch_id"
                class="batch-list-item compact"
                :class="{ active: inspectorReport?.batch_id === batch.batch_id }"
                type="button"
                @click="selectRecentBatch(batch.batch_id)"
              >
                <Checkbox
                  :checked="isBatchSelectedForCompare(batch.batch_id)"
                  @change="toggleCompareBatch(batch.batch_id)"
                  @click.stop
                />
                <span class="batch-title">
                  <span>#{{ batch.batch_id }}</span>
                  <Tag :color="statusColor(batch.status)">
                    {{ statusLabel(batch.status) }}
                  </Tag>
                </span>
                <span class="batch-meta">
                  {{ batch.summary.generated_count }}/{{ batch.summary.total_count }}
                  条 · 失败 {{ failedCountOf(batch.summary) }} · 风险
                  {{ batchRiskCount(batch.summary) }}
                </span>
                <span class="batch-time">
                  {{ formatBatchTime(batch.create_time) }}
                </span>
              </button>
            </div>
            <Empty v-else :description="batchScopeEmptyText" />
          </div>
        </Spin>
      </Card>
    </div>

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
        <div class="upload-format-hint">
          <strong>推荐格式：业务规则名称 / 规则语料 / 示例</strong>
          <span>
            示例可以为空；有示例时一行一条，生成时会从示例中抽 3 条作为 few-shot。
          </span>
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
          <div class="field-label">目标规则包</div>
          <Input :value="uploadTargetAssetKey" disabled />
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
      @ok="generateFocusedRule"
    >
      <Space class="confirm-form" direction="vertical">
        <div class="form-field">
          <div class="field-label">业务规则</div>
          <Select
            v-model:value="focusGenerateForm.rule_key"
            :disabled="generating"
            :options="selectedRuleOptions"
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
      v-model:open="batchDetailOpen"
      class="batch-detail-drawer"
      placement="right"
      title="批次明细"
      width="980"
    >
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
              <template v-else-if="column.key === 'selected_examples'">
                <div v-if="selectedExamplesOf(record).length" class="selected-examples-cell">
                  <p
                    v-for="example in selectedExamplesOf(record)"
                    :key="example"
                  >
                    {{ example }}
                  </p>
                </div>
                <span v-else class="muted">-</span>
              </template>
              <template v-else-if="column.key === 'title'">
                <span>{{ record.title || '-' }}</span>
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
        <Empty v-else description="请选择批次查看明细" />
      </Spin>
    </Drawer>

    <Drawer
      v-model:open="compareDrawerOpen"
      class="batch-compare-drawer"
      placement="right"
      title="批次对比"
      width="980"
    >
      <Spin :spinning="compareLoading">
        <template v-if="compareLeftReport && compareRightReport">
          <div class="batch-compare-head">
            <div>
              <span>基准批次</span>
              <Tag>{{ compareLeftLabel }}</Tag>
              <strong>
                {{ compareLeftReport.batch_code || `#${compareLeftReport.batch_id}` }}
              </strong>
            </div>
            <div>
              <span>对比批次</span>
              <Tag>{{ compareRightLabel }}</Tag>
              <strong>
                {{ compareRightReport.batch_code || `#${compareRightReport.batch_id}` }}
              </strong>
            </div>
          </div>

          <div class="batch-compare-grid">
            <div
              v-for="row in compareMetricRows"
              :key="row.key"
              class="compare-metric-card"
            >
              <span>{{ row.label }}</span>
              <strong>
                {{ compareValue(row.left, row.percent) }}
                <span>→</span>
                {{ compareValue(row.right, row.percent) }}
              </strong>
              <em :class="compareDeltaClass(row.delta, row.key)">
                {{ compareDelta(row.delta, row.percent) }}
              </em>
            </div>
          </div>

          <div class="compare-samples">
            <div class="compare-sample-column">
              <div class="compare-sample-title">
                <strong>基准失败/风险样例</strong>
                <Tag>{{ riskSamplesOf(compareLeftReport).length }} 条</Tag>
              </div>
              <div v-if="riskSamplesOf(compareLeftReport).length" class="risk-sample-list">
                <div
                  v-for="item in riskSamplesOf(compareLeftReport)"
                  :key="item.item_id"
                  class="risk-sample-card"
                >
                  <div class="risk-sample-title">
                    <Tag :color="statusColor(item.status)">
                      样例 {{ item.item_no }} · {{ statusLabel(item.status) }}
                    </Tag>
                    <Tag :color="passColor(item.hard_pass)">
                      {{ passLabel(item.hard_pass) }}
                    </Tag>
                  </div>
                  <p>{{ item.body || itemFailureMessage(item) }}</p>
                  <Space v-if="riskTagsOf(item).length" wrap size="small">
                    <Tag
                      v-for="tag in riskTagsOf(item)"
                      :key="tag.label"
                      :color="tag.color"
                    >
                      {{ tag.label }}
                    </Tag>
                  </Space>
                </div>
              </div>
              <Empty v-else description="暂无失败/风险样例" />
            </div>

            <div class="compare-sample-column">
              <div class="compare-sample-title">
                <strong>对比失败/风险样例</strong>
                <Tag>{{ riskSamplesOf(compareRightReport).length }} 条</Tag>
              </div>
              <div v-if="riskSamplesOf(compareRightReport).length" class="risk-sample-list">
                <div
                  v-for="item in riskSamplesOf(compareRightReport)"
                  :key="item.item_id"
                  class="risk-sample-card"
                >
                  <div class="risk-sample-title">
                    <Tag :color="statusColor(item.status)">
                      样例 {{ item.item_no }} · {{ statusLabel(item.status) }}
                    </Tag>
                    <Tag :color="passColor(item.hard_pass)">
                      {{ passLabel(item.hard_pass) }}
                    </Tag>
                  </div>
                  <p>{{ item.body || itemFailureMessage(item) }}</p>
                  <Space v-if="riskTagsOf(item).length" wrap size="small">
                    <Tag
                      v-for="tag in riskTagsOf(item)"
                      :key="tag.label"
                      :color="tag.color"
                    >
                      {{ tag.label }}
                    </Tag>
                  </Space>
                </div>
              </div>
              <Empty v-else description="暂无失败/风险样例" />
            </div>
          </div>
        </template>
        <Empty v-else description="请选择两个批次对比" />
      </Spin>
    </Drawer>

  </div>
</template>

<style scoped>
.business-rule-page {
  --maga-page-bg: hsl(var(--background));
  --maga-surface: hsl(var(--card));
  --maga-surface-soft: hsl(var(--muted) / 45%);
  --maga-surface-active: hsl(var(--primary) / 16%);
  --maga-border: hsl(var(--border));
  --maga-text: hsl(var(--foreground));
  --maga-text-muted: hsl(var(--muted-foreground));
  --maga-text-faint: hsl(var(--muted-foreground) / 72%);
  --maga-error: hsl(var(--destructive));

  background: var(--maga-page-bg);
  min-height: 100%;
}

.business-rule-page :deep(.ant-card) {
  background: var(--maga-surface);
  border: 1px solid var(--maga-border);
  border-radius: 8px;
}

.business-rule-page :deep(.ant-card-body) {
  padding: 14px;
}

.business-rule-page :deep(.ant-input),
.business-rule-page :deep(.ant-input-number),
.business-rule-page :deep(.ant-select-selector),
.business-rule-page :deep(textarea.ant-input) {
  background: var(--maga-surface-soft) !important;
  border-color: var(--maga-border) !important;
  color: var(--maga-text) !important;
}

.business-rule-page :deep(.ant-input::placeholder),
.business-rule-page :deep(textarea.ant-input::placeholder) {
  color: var(--maga-text-faint) !important;
}

.business-rule-page :deep(.ant-tag:not(.ant-tag-has-color)) {
  background: var(--maga-surface-soft);
  border-color: var(--maga-border);
  color: var(--maga-text);
}

.full-width {
  width: 100%;
}

.page-toolbar {
  align-items: center;
  background: var(--maga-surface);
  border: 1px solid var(--maga-border);
  border-radius: 8px;
  display: flex;
  gap: 16px;
  justify-content: space-between;
  margin-bottom: 12px;
  padding: 10px 14px;
}

.page-title-block {
  align-items: baseline;
  display: flex;
  gap: 10px;
  min-width: 0;
}

.page-title-block h1 {
  color: var(--maga-text);
  font-size: 18px;
  font-weight: 700;
  line-height: 1.3;
  margin: 0;
  white-space: nowrap;
}

.toolbar-subtitle {
  color: var(--maga-text-muted);
  font-size: 13px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rule-workbench-shell {
  display: grid;
  gap: 12px;
  grid-template-columns: 300px minmax(520px, 1fr) 360px;
  grid-template-rows: minmax(0, 1fr) auto;
  height: calc(100vh - 154px);
  min-height: 760px;
  overflow: hidden;
}

.rule-workbench-shell.package-pane-collapsed {
  grid-template-columns: 48px minmax(680px, 1fr) 360px;
}

.rule-package-pane,
.rule-list-pane,
.rule-inspector-pane,
.recent-batches-card {
  min-height: 0;
  min-width: 0;
}

.recent-batches-card {
  grid-column: 1 / -1;
}

.recent-batches-card :deep(.ant-card-body) {
  padding: 12px 14px;
}

.rule-package-pane.collapsed {
  align-items: stretch;
  display: flex;
}

.package-pane-expand {
  align-items: center;
  background: var(--maga-surface);
  border: 1px solid var(--maga-border);
  border-radius: 8px;
  color: var(--maga-text-muted);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  font-size: 12px;
  font-weight: 700;
  gap: 8px;
  justify-content: flex-start;
  min-height: 0;
  padding: 12px 6px;
  width: 100%;
}

.package-pane-expand:hover {
  background: var(--maga-surface-active);
  border-color: #1677ff;
  color: var(--maga-text);
}

.package-pane-expand span {
  line-height: 1.1;
  writing-mode: vertical-rl;
}

.rule-list-pane {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
  position: relative;
  z-index: 1;
}

.rule-inspector-pane {
  position: relative;
  z-index: 2;
}

.fill-card {
  height: 100%;
  min-height: 0;
}

.rule-package-pane .fill-card {
  overflow: hidden;
}

.fill-card :deep(.ant-card-body) {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.rule-package-pane .fill-card :deep(.ant-spin-nested-loading),
.rule-package-pane .fill-card :deep(.ant-spin-container) {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
}

.inspector-card :deep(.ant-card-body) {
  overflow-y: auto;
}

.pane-card-header,
.list-card-header,
.inspector-title {
  align-items: center;
  display: flex;
  gap: 10px;
  justify-content: space-between;
  min-width: 0;
}

.pane-card-header h2,
.list-card-header h2 {
  color: var(--maga-text);
  font-size: 16px;
  font-weight: 700;
  line-height: 1.35;
  margin: 0;
}

.pane-card-header span,
.list-card-header span,
.history-toggle-label {
  color: var(--maga-text-muted);
  font-size: 12px;
}

.rule-package-list,
.batch-list,
.risk-sample-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
  overflow-y: auto;
  padding-right: 2px;
}

.rule-package-list {
  flex: 1 1 auto;
  margin-top: 12px;
}

.package-search-input {
  flex: 0 0 auto;
  margin-top: 12px;
}

.rule-package-option,
.batch-list-item {
  background: var(--maga-surface-soft);
  border: 1px solid var(--maga-border);
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
  background: var(--maga-surface-active);
  border-color: #1677ff;
  box-shadow: 0 0 0 1px rgb(22 119 255 / 10%);
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
  color: var(--maga-text);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.option-meta,
.batch-meta {
  color: var(--maga-text-muted);
  display: block;
  font-size: 12px;
  line-height: 1.5;
}

.config-strip-card {
  flex: 0 0 auto;
}

.config-strip {
  align-items: center;
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(220px, 1fr) minmax(300px, 1.4fr) auto;
}

.config-heading {
  align-items: center;
  display: flex;
  gap: 8px;
  min-width: 0;
}

.config-heading span {
  color: var(--maga-text-muted);
  font-size: 12px;
  white-space: nowrap;
}

.config-heading strong {
  color: var(--maga-text);
  font-size: 15px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.config-actions {
  justify-content: flex-end;
}

.rule-list-card {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}

.rule-search {
  width: 240px;
}

.rule-table {
  flex: 1 1 auto;
  margin-top: 12px;
  min-height: 0;
}

.rule-table :deep(.ant-table),
.rule-table :deep(.ant-table-container),
.rule-table :deep(.ant-table-content) {
  background: var(--maga-surface);
}

.rule-table :deep(.ant-table-thead > tr > th) {
  background: var(--maga-surface-soft) !important;
  border-bottom-color: var(--maga-border) !important;
  color: var(--maga-text) !important;
}

.rule-table :deep(.ant-table-tbody > tr > td) {
  background: var(--maga-surface) !important;
  border-bottom-color: var(--maga-border) !important;
  color: var(--maga-text) !important;
}

.rule-table :deep(.ant-table-row) {
  cursor: pointer;
}

.rule-table :deep(.active-rule-row > td) {
  background: var(--maga-surface-active) !important;
}

.corpus-cell {
  display: -webkit-box;
  line-height: 1.55;
  max-width: 560px;
  max-height: 70px;
  overflow: hidden;
  white-space: pre-line;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.rule-summary-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 76px;
  min-width: 0;
}

.rule-summary-cell strong {
  color: var(--maga-text);
  font-size: 14px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rule-summary-cell p {
  color: var(--maga-text-muted);
  display: -webkit-box;
  font-size: 12px;
  line-height: 1.55;
  margin: 0;
  overflow: hidden;
  white-space: pre-line;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.count-cell {
  color: var(--maga-text-muted);
  display: flex;
  flex-direction: column;
  font-size: 12px;
  gap: 4px;
  white-space: nowrap;
}

.count-cell small {
  color: var(--maga-text-muted);
  font-size: 12px;
}

.selected-examples-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 120px;
  overflow: auto;
}

.selected-examples-cell p {
  color: var(--maga-text-muted);
  line-height: 1.5;
  margin: 0;
}

.inspector-section {
  margin-bottom: 14px;
  min-width: 0;
}

.inspector-title strong {
  color: var(--maga-text);
  font-size: 16px;
  min-width: 0;
  overflow-wrap: anywhere;
}

.inspector-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.field-label {
  color: var(--maga-text-muted);
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
}

.readonly-corpus {
  background: var(--maga-surface-soft);
  border: 1px solid var(--maga-border);
  border-radius: 8px;
  color: var(--maga-text);
  line-height: 1.7;
  max-height: 180px;
  overflow: auto;
  padding: 12px;
  white-space: pre-wrap;
}

.inspector-corpus {
  max-height: 320px;
}

.draft-workspace-header {
  align-items: center;
  display: flex;
  gap: 8px;
  justify-content: space-between;
  margin-bottom: 8px;
}

.draft-workspace-header .field-label {
  margin-bottom: 0;
}

.draft-compare-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.draft-compare-column {
  min-width: 0;
}

.inline-draft-editor :deep(textarea.ant-input) {
  line-height: 1.7;
}

.inline-draft-actions {
  margin-top: 12px;
}

.draft-status-box {
  align-items: center;
  background: var(--maga-surface-soft);
  border: 1px solid var(--maga-border);
  border-radius: 8px;
  display: flex;
  justify-content: space-between;
  padding: 10px 12px;
}

.draft-status-box span,
.draft-status-box strong {
  color: var(--maga-text);
}

.current-batch-title {
  align-items: center;
  display: flex;
  gap: 8px;
  min-width: 0;
}

.current-batch-title span {
  color: var(--maga-text-muted);
  font-size: 12px;
  white-space: nowrap;
}

.current-batch-title strong {
  color: var(--maga-text);
  font-size: 13px;
  min-width: 0;
  overflow-wrap: anywhere;
}

.batch-scope-switch {
  display: grid;
  gap: 8px;
  grid-template-columns: 1fr 1fr;
  margin-top: 10px;
}

.metric-block {
  background: var(--maga-surface-soft);
  border: 1px solid var(--maga-border);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding: 10px 12px;
}

.metric-block span {
  color: var(--maga-text-muted);
  font-size: 12px;
}

.metric-block strong {
  color: var(--maga-text);
  font-size: 14px;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.risk-sample-card {
  background: var(--maga-surface-soft);
  border: 1px solid var(--maga-border);
  border-radius: 8px;
  padding: 10px;
}

.risk-sample-title {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.risk-sample-card p {
  color: var(--maga-text);
  display: -webkit-box;
  line-height: 1.6;
  margin: 0 0 8px;
  overflow: hidden;
  white-space: pre-wrap;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.compact-list {
  margin-top: 12px;
  max-height: 260px;
}

.batch-list-item.compact {
  display: grid;
  gap: 4px 8px;
  grid-template-columns: auto minmax(0, 1fr);
  min-height: 74px;
}

.batch-list-item.compact :deep(.ant-checkbox-wrapper),
.batch-list-item.compact :deep(.ant-checkbox) {
  grid-row: 1 / span 3;
  margin-top: 2px;
}

.batch-list-item.compact .batch-title,
.batch-list-item.compact .batch-meta,
.batch-list-item.compact .batch-time {
  min-width: 0;
}

.recent-batches-layout {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.recent-batches-head {
  align-items: center;
  display: flex;
  gap: 16px;
  justify-content: space-between;
  min-width: 0;
}

.recent-batches-title-row {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  min-width: 0;
}

.recent-batch-summary {
  display: grid;
  gap: 10px;
}

.current-batch-samples {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
}

.current-batch-strip {
  align-items: center;
  background: var(--maga-surface-soft);
  border: 1px solid var(--maga-border);
  border-radius: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  justify-content: space-between;
  min-width: 0;
  padding: 8px 10px;
}

.current-batch-stats {
  align-items: center;
  color: var(--maga-text-muted);
  display: flex;
  flex-wrap: wrap;
  font-size: 12px;
  gap: 6px 10px;
}

.current-batch-sample {
  background: var(--maga-surface-soft);
  border: 1px solid var(--maga-border);
  border-radius: 8px;
  min-width: 0;
  padding: 10px 12px;
}

.current-batch-sample-head {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.current-batch-sample-head strong {
  color: var(--maga-text);
  flex: 1;
  font-size: 13px;
  min-width: 0;
  overflow-wrap: anywhere;
}

.current-batch-sample p {
  color: var(--maga-text);
  font-size: 12px;
  line-height: 1.6;
  margin: 8px 0 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.current-batch-sample-note {
  color: var(--maga-error);
  font-size: 12px;
  line-height: 1.5;
  margin-top: 6px;
  overflow-wrap: anywhere;
}

.recent-batches-card .compact-list {
  display: grid;
  grid-template-columns: repeat(6, minmax(150px, 1fr));
  margin-top: 0;
  max-height: none;
  overflow: visible;
  padding-right: 0;
}

.recent-batches-card .batch-footer-actions {
  margin-top: 0;
  width: auto;
}

.recent-batches-card .batch-footer-actions :deep(.ant-space-item) {
  width: auto;
}

.recent-batches-card .batch-scope-switch {
  display: flex;
  gap: 8px;
  margin-top: 0;
}

.recent-batches-card .batch-list-item.compact {
  min-height: 64px;
  padding: 8px 10px;
}

.batch-time {
  color: var(--maga-text-muted);
  font-size: 12px;
}

.batch-footer-actions {
  margin-top: 12px;
  width: 100%;
}

.batch-footer-actions :deep(.ant-space-item) {
  width: 100%;
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
  color: var(--maga-text);
  line-height: 1.65;
  max-height: 88px;
  overflow: auto;
  white-space: pre-wrap;
}

.batch-error-cell {
  color: var(--maga-error);
  line-height: 1.6;
  white-space: pre-wrap;
}

.batch-compare-head,
.batch-compare-grid,
.compare-samples {
  display: grid;
  gap: 12px;
}

.batch-compare-head {
  grid-template-columns: 1fr 1fr;
  margin-bottom: 12px;
}

.batch-compare-head > div,
.compare-metric-card,
.compare-sample-column {
  background: var(--maga-surface-soft);
  border: 1px solid var(--maga-border);
  border-radius: 8px;
  min-width: 0;
  padding: 12px;
}

.batch-compare-head span,
.compare-metric-card span {
  color: var(--maga-text-muted);
  display: block;
  font-size: 12px;
  margin-bottom: 4px;
}

.batch-compare-head strong,
.compare-metric-card strong,
.compare-sample-title strong {
  color: var(--maga-text);
}

.batch-compare-grid {
  grid-template-columns: repeat(5, minmax(0, 1fr));
  margin-bottom: 14px;
}

.compare-metric-card strong {
  display: block;
  font-size: 15px;
  margin-bottom: 4px;
}

.compare-metric-card strong span {
  display: inline;
  margin: 0 4px;
}

.compare-metric-card em {
  font-style: normal;
  font-weight: 700;
}

.compare-metric-card em.positive {
  color: #389e0d;
}

.compare-metric-card em.negative {
  color: #cf1322;
}

.compare-metric-card em.neutral {
  color: var(--maga-text-muted);
}

.compare-samples {
  grid-template-columns: 1fr 1fr;
}

.compare-sample-title {
  align-items: center;
  display: flex;
  justify-content: space-between;
  margin-bottom: 10px;
}

.confirm-form,
.form-field {
  width: 100%;
}

.confirm-file {
  align-items: center;
  background: var(--maga-surface-soft);
  border: 1px solid var(--maga-border);
  border-radius: 8px;
  display: flex;
  gap: 12px;
  justify-content: space-between;
  padding: 10px 12px;
}

.confirm-file span {
  color: var(--maga-text-muted);
}

.confirm-file strong {
  color: var(--maga-text);
  font-weight: 600;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-format-hint {
  background: var(--maga-surface-soft);
  border: 1px solid var(--maga-border);
  border-radius: 8px;
  color: var(--maga-text-muted);
  display: grid;
  gap: 4px;
  padding: 10px 12px;
}

.upload-format-hint strong {
  color: var(--maga-text);
  font-size: 13px;
  font-weight: 600;
}

.upload-format-hint span {
  font-size: 12px;
  line-height: 1.6;
}

.draft-meta {
  background: var(--maga-surface-soft);
  border: 1px solid var(--maga-border);
  border-radius: 8px;
  margin-bottom: 16px;
  padding: 12px;
  width: 100%;
}

.draft-title-row {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
}

.draft-title-row strong {
  min-width: 0;
  overflow-wrap: anywhere;
}

.draft-section {
  margin-top: 16px;
}

.draft-hint,
.muted {
  color: var(--maga-text-muted);
  font-size: 12px;
}

.draft-hint {
  margin-top: 12px;
}

.draft-actions {
  border-top: 1px solid var(--maga-border);
  margin-top: 18px;
  padding-top: 14px;
}

@media (max-width: 1180px) {
  .rule-workbench-shell {
    grid-template-columns: 280px minmax(480px, 1fr);
    height: auto;
    min-height: 0;
  }

  .rule-package-pane .fill-card {
    height: min(560px, calc(100vh - 180px));
  }

  .rule-workbench-shell.package-pane-collapsed {
    grid-template-columns: 48px minmax(520px, 1fr);
  }

  .rule-inspector-pane {
    grid-column: 1 / -1;
    min-height: 420px;
  }

  .recent-batch-summary {
    grid-template-columns: 1fr;
  }

  .recent-batches-card .compact-list {
    grid-template-columns: repeat(3, minmax(180px, 1fr));
  }
}

@media (max-width: 768px) {
  .business-rule-page {
    overflow: auto;
  }

  .page-toolbar,
  .page-title-block,
  .list-card-header,
  .config-strip {
    align-items: stretch;
    flex-direction: column;
  }

  .page-toolbar,
  .page-title-block {
    display: flex;
  }

  .rule-workbench-shell {
    display: flex;
    flex-direction: column;
    height: auto;
    min-height: 0;
  }

  .rule-package-pane,
  .rule-list-pane,
  .rule-inspector-pane,
  .recent-batches-card,
  .fill-card {
    height: auto;
  }

  .rule-package-pane .fill-card {
    height: min(560px, calc(100vh - 180px));
  }

  .package-pane-expand {
    flex-direction: row;
    justify-content: center;
    min-height: 44px;
  }

  .package-pane-expand span {
    writing-mode: horizontal-tb;
  }

  .rule-search {
    width: 100%;
  }

  .config-strip {
    display: flex;
  }

  .recent-batches-head {
    align-items: stretch;
    flex-direction: column;
  }

  .recent-batches-card .compact-list {
    grid-template-columns: 1fr;
  }

  .batch-detail-summary {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
