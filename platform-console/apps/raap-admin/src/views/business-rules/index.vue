<script setup lang="ts">
import type { UploadProps } from 'ant-design-vue';

import type { AssetsApi } from '#/api/core/assets';
import type { ContentAgentApi } from '#/api/core/content-agent';

import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useUserStore } from '@vben/stores';

import {
  PlayCircleOutlined,
  ReloadOutlined,
  UploadOutlined,
} from '@ant-design/icons-vue';
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Input,
  InputNumber,
  List,
  ListItem,
  message,
  Modal,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Upload,
} from 'ant-design-vue';

import {
  getAssetDetailApi,
  getAssetImportRunsApi,
  getAssetSummariesApi,
  importCommentAngleRuleSetApi,
  importProductExperienceRuleSetApi,
} from '#/api/core/assets';
import {
  getContentBatchListApi,
  getContentBatchReportApi,
  preflightContentGenerationApi,
  startCommentBatchApi,
  startContentBatchApi,
} from '#/api/core/content-agent';

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
    defaultDisplayName: '源悦-评论（评论切角）',
    label: '源悦-评论',
  },
  product_experience: {
    accept: '.csv,.xlsx',
    assetType: 'product_experience_rule_set',
    defaultAssetKey: 'yuanyue_product_experience',
    defaultDisplayName: '源悦-生文（产品使用体验）',
    label: '源悦-生文',
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
const importRunsLoading = ref(false);
const packageType = ref<RulePackageType>('comment_angle');
const displayName = ref(rulePackageConfigs.comment_angle.defaultDisplayName);
const pendingFile = ref<File | null>(null);
const uploadConfirmOpen = ref(false);
const ruleAssets = ref<AssetsApi.AssetSummary[]>([]);
const importRuns = ref<AssetsApi.AssetImportRun[]>([]);
const selectedSummary = ref<AssetsApi.AssetSummary | null>(null);
const selectedAsset = ref<AssetsApi.AssetRegistry | null>(null);
const userStore = useUserStore();
const route = useRoute();
const router = useRouter();
const batchLoading = ref(false);
const reportLoading = ref(false);
const selectedReport = ref<ContentAgentApi.BatchReport | null>(null);
const batchList = ref<ContentAgentApi.BatchListItem[]>([]);
const batchTotal = ref(0);
const focusGenerateOpen = ref(false);
const focusGenerateForm = ref({
  comment_angle: '',
  count: 20,
});

const selectedRuleItems = computed(() => {
  const items = selectedAsset.value?.content_json?.items;
  return Array.isArray(items) ? items : [];
});
const selectedItems = computed(() => selectedRuleItems.value.slice(0, 30));
const selectedReportItems = computed(() => selectedReport.value?.items || []);
const selectedReportSummary = computed(
  () => selectedReport.value?.summary || null,
);
const isSelectedCommentRuleSet = computed(
  () => selectedAsset.value?.asset_type === 'comment_angle_rule_set',
);
const selectedCommentAngleOptions = computed(() => {
  const seen = new Set<string>();
  return selectedRuleItems.value
    .map((item) => String(item.comment_angle || '').trim())
    .filter((value) => {
      if (!value || seen.has(value)) return false;
      seen.add(value);
      return true;
    })
    .map((value) => ({ label: value, value }));
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
const reportAlertMessage = computed(() => {
  const summary = selectedReportSummary.value;
  if (!summary) return '';
  if (reportFailureCount.value > 0) {
    return `失败 ${reportFailureCount.value} 条，失败项不进入红线审核。`;
  }
  if (
    summary.forbidden_hit_count ||
    summary.remaining_rewrite_required_count ||
    summary.similarity_warning_count
  ) {
    return '仍有风险项或相似内容，请优先处理标红和标橙内容。';
  }
  return '';
});

const importRunColumns: any[] = [
  { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
  { title: '来源文件', dataIndex: 'source_name', key: 'source_name' },
  { title: '规则包', key: 'rule_package', width: 230 },
  { title: '条数', key: 'rule_count', width: 90 },
  { title: '示例', key: 'example_count', width: 90 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 100 },
  { title: '上传人', dataIndex: 'created_by', key: 'created_by', width: 120 },
  { title: '时间', dataIndex: 'create_time', key: 'create_time', width: 180 },
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
  ];
});

const filteredImportRuns = computed(() =>
  importRuns.value.filter((run) => {
    const assetType = run.summary_json?.asset_type;
    if (assetType && ruleAssetTypes.includes(assetType)) return true;
    const assetKeys = run.summary_json?.asset_keys;
    return Array.isArray(assetKeys)
      ? assetKeys.some((item) => ruleAssetTypes.includes(item?.[0]))
      : false;
  }),
);

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

const passColor = (value?: boolean | null) => {
  if (value === true) return 'green';
  if (value === false) return 'red';
  return 'default';
};

const failedCountOf = (summary?: ContentAgentApi.BatchReportSummary | null) => {
  if (!summary) return 0;
  return Math.max(0, summary.total_count - summary.generated_count);
};

const hasGeneratedContent = (item: ContentAgentApi.BatchReportItem) =>
  Boolean((item.title || '').trim() || (item.body || '').trim());

const displayErrorMessage = (value?: null | string) => {
  if (!value) return '';
  if (value.includes('content.generate produced empty comment')) {
    return '模型没有返回可用正文，请重新从生产工作台生成新批次。';
  }
  return value;
};

const itemFailureMessage = (item: ContentAgentApi.BatchReportItem) => {
  const stageError = item.trace_stage_calls?.find(
    (stage) => stage.status === 'failed' && stage.error_message,
  )?.error_message;
  return (
    displayErrorMessage(item.error_message || stageError) ||
    '正文尚未生成，请查看完整报告里的执行链路。'
  );
};

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

async function loadRuleAssets() {
  loading.value = true;
  try {
    const groups = await Promise.all(
      ruleAssetTypes.map((assetType) =>
        getAssetSummariesApi({
          asset_stage: 'production',
          asset_type: assetType,
        }),
      ),
    );
    ruleAssets.value = groups.flat();
    if (!selectedSummary.value && ruleAssets.value.length > 0) {
      const firstAsset = ruleAssets.value[0];
      if (firstAsset) {
        await openAsset(firstAsset);
      }
    }
  } catch {
    message.error('获取业务规则包失败');
  } finally {
    loading.value = false;
  }
}

async function loadImportRuns() {
  importRunsLoading.value = true;
  try {
    importRuns.value = await getAssetImportRunsApi({ limit: 50 });
  } catch {
    message.error('获取导入记录失败');
  } finally {
    importRunsLoading.value = false;
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

const openFullReport = () => {
  if (!selectedReport.value) return;
  router.push({
    path: '/content-agent/workbench',
    query: { batch_id: String(selectedReport.value.batch_id) },
  });
};

// 运营在规则包管理页直接触发生成，入口按规则包类型分流到统一生文/评论批量接口。
async function generateFromRulePackage(
  row: AssetsApi.AssetRegistry | AssetsApi.AssetSummary | Record<string, any>,
) {
  if (!row?.asset_key || !row?.asset_type) {
    message.warning('请先选择一个业务规则包');
    return;
  }
  generating.value = true;
  try {
    const preflight = await preflightContentGenerationApi({
      asset_key: row.asset_key,
      asset_type: row.asset_type,
    });
    if (!preflight.passed) {
      showPreflightFailure(preflight);
      return;
    }
    if (preflight.warning_codes.length > 0) {
      message.warning(
        `生成前检查有 ${preflight.warning_codes.length} 项提示，已继续生成`,
      );
    }
    const payload = {
      asset_key: row.asset_key,
      created_by: currentOperator.value,
    };
    let result = null;
    if (row.asset_type === 'comment_angle_rule_set') {
      result = await startCommentBatchApi(payload);
    } else if (row.asset_type === 'product_experience_rule_set') {
      result = await startContentBatchApi(payload);
    }
    if (!result) {
      message.warning('当前规则包类型暂不支持一键生成');
      return;
    }
    message.success(
      `生成完成：${result.execution.generated_count}/${result.execution.requested_limit}`,
    );
    selectedReport.value = result.report;
    await loadBatches();
  } catch {
    message.error('生成失败，请检查规则包和 worker 状态');
  } finally {
    generating.value = false;
  }
}

function openFocusGeneration() {
  if (!selectedAsset.value || !isSelectedCommentRuleSet.value) {
    message.warning('请先选择评论切角规则包');
    return;
  }
  const firstAngle = selectedCommentAngleOptions.value[0]?.value;
  if (!firstAngle) {
    message.warning('当前评论规则包没有可测试的评论切角');
    return;
  }
  focusGenerateForm.value = {
    comment_angle: focusGenerateForm.value.comment_angle || firstAngle,
    count: focusGenerateForm.value.count || 20,
  };
  focusGenerateOpen.value = true;
}

async function generateFocusedCommentAngle() {
  if (!selectedAsset.value?.asset_key) {
    message.warning('请先选择评论切角规则包');
    return;
  }
  const commentAngle = focusGenerateForm.value.comment_angle.trim();
  if (!commentAngle) {
    message.warning('请选择评论切角');
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
      count: Number(focusGenerateForm.value.count || 20),
      created_by: currentOperator.value,
    });
    message.success(
      `切角测试完成：${result.execution.generated_count}/${result.execution.requested_limit}`,
    );
    focusGenerateOpen.value = false;
    selectedReport.value = result.report;
    await loadBatches();
  } catch {
    message.error('切角测试失败，请检查规则包、切角和 worker 状态');
  } finally {
    generating.value = false;
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
      '请检查业务规则包和生文配置。',
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
    message.warning('请填写规则包名称');
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
    await Promise.all([loadRuleAssets(), loadImportRuns()]);
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
  loadImportRuns();
  loadBatches();
});

watch(
  () => route.query.batch_id,
  () => {
    selectedReport.value = null;
    loadBatches();
  },
);
</script>

<template>
  <div class="business-rule-page production-workbench p-4">
    <div class="page-toolbar">
      <div class="page-title-block">
        <div class="eyebrow">MAGA CONTENT OPS</div>
        <h1>生产工作台</h1>
        <p>规则包、生成、复盘集中处理。</p>
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
            上传规则包
          </Button>
        </Upload>
      </Space>
    </div>

    <div class="workbench-layout">
      <div class="workbench-sidebar">
        <Card class="selector-card" title="规则包" :bordered="false">
          <template #extra>
            <Button size="small" @click="loadRuleAssets">
              <template #icon><ReloadOutlined /></template>
              刷新
            </Button>
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
            <Empty v-if="ruleAssets.length === 0" description="暂无规则包" />
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
                切角测试
              </Button>
              <Button
                type="primary"
                :disabled="!selectedAsset"
                :loading="generating"
                @click="selectedAsset && generateFromRulePackage(selectedAsset)"
              >
                <template #icon><PlayCircleOutlined /></template>
                生成一批
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
                <span>规则包</span>
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
                <span>Worker</span>
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
          <Empty v-else description="暂无当前规则包" />
        </Card>

        <Spin :spinning="reportLoading">
          <Card class="result-card" :bordered="false">
            <template #title>
              <Space>
                <span>最新生成结果</span>
                <Tag v-if="selectedReport">
                  {{
                    selectedReport.batch_code || `#${selectedReport.batch_id}`
                  }}
                </Tag>
                <Tag
                  v-if="selectedReport"
                  :color="statusColor(selectedReport.status)"
                >
                  {{ statusLabel(selectedReport.status) }}
                </Tag>
              </Space>
            </template>
            <template #extra>
              <Space v-if="selectedReport">
                <Button size="small" @click="goFeedback">去评价</Button>
                <Button size="small" @click="openFullReport">完整报告</Button>
                <Button
                  size="small"
                  @click="openReport(selectedReport.batch_id)"
                >
                  刷新
                </Button>
              </Space>
            </template>

            <template v-if="selectedReport">
              <div class="result-heading">
                <div>
                  <div class="result-topic">
                    {{ selectedReport.product_topic }}
                  </div>
                  <div class="result-subtitle">
                    {{ selectedReport.asset_key }}
                  </div>
                </div>
                <Tag v-if="reportRiskCount > 0" color="orange">
                  待处理 {{ reportRiskCount }}
                </Tag>
                <Tag v-else color="green">无阻塞风险</Tag>
              </div>

              <Row v-if="selectedReportSummary" class="metric-row" :gutter="12">
                <Col :md="4" :sm="8" :xs="12">
                  <Statistic
                    title="总数"
                    :value="selectedReportSummary.total_count"
                  />
                </Col>
                <Col :md="4" :sm="8" :xs="12">
                  <Statistic
                    title="已生成"
                    :value="selectedReportSummary.generated_count"
                  />
                </Col>
                <Col :md="4" :sm="8" :xs="12">
                  <Statistic title="失败" :value="reportFailureCount" />
                </Col>
                <Col :md="4" :sm="8" :xs="12">
                  <Statistic
                    title="红线通过"
                    :value="selectedReportSummary.hard_pass_count"
                  />
                </Col>
                <Col :md="4" :sm="8" :xs="12">
                  <Statistic
                    title="自动改写"
                    :value="selectedReportSummary.rewrite_item_count"
                  />
                </Col>
                <Col :md="4" :sm="8" :xs="12">
                  <Statistic
                    title="禁用词"
                    :value="selectedReportSummary.forbidden_hit_count"
                  />
                </Col>
              </Row>

              <Alert
                v-if="reportAlertMessage"
                class="mt-4"
                :message="reportAlertMessage"
                show-icon
                type="warning"
              />

              <List
                class="result-list"
                :data-source="selectedReportItems"
                item-layout="vertical"
              >
                <template #renderItem="{ item }">
                  <ListItem :key="item.item_id" class="content-list-item">
                    <div
                      class="content-item"
                      :class="{ failed: !hasGeneratedContent(item) }"
                    >
                      <div class="content-item-header">
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
                        </Space>
                        <Button
                          size="small"
                          :disabled="!hasGeneratedContent(item)"
                          @click="copyArticle(item)"
                        >
                          复制
                        </Button>
                      </div>

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
                        <Tag>字数 {{ item.body_chars }}</Tag>
                        <Tag>建议 {{ item.suggestion_count }}</Tag>
                        <Tag>替换 {{ item.replacement_count }}</Tag>
                        <Tag v-if="item.trace_run_id || item.run_id">
                          Run #{{ item.trace_run_id || item.run_id }}
                        </Tag>
                      </div>
                    </div>
                  </ListItem>
                </template>
              </List>
            </template>

            <Empty v-else description="暂无生成结果" />
          </Card>
        </Spin>
      </div>
    </div>

    <Row class="diagnostics-row" :gutter="[16, 16]">
      <Col :xl="15" :xs="24">
        <Card title="规则详情" :bordered="false">
          <template v-if="selectedAsset">
            <Table
              :columns="previewColumns"
              :data-source="selectedItems"
              :pagination="{ pageSize: 6 }"
              :scroll="{ x: 1120 }"
              row-key="rule_id"
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
              </template>
            </Table>
          </template>
          <Empty v-else description="暂无规则详情" />
        </Card>
      </Col>

      <Col :xl="9" :xs="24">
        <Card title="导入记录" :bordered="false">
          <template #extra>
            <Button size="small" @click="loadImportRuns">
              <template #icon><ReloadOutlined /></template>
              刷新
            </Button>
          </template>
          <Table
            :columns="importRunColumns"
            :data-source="filteredImportRuns"
            :loading="importRunsLoading"
            :pagination="{ pageSize: 5 }"
            :scroll="{ x: 900 }"
            row-key="id"
            size="small"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'rule_package'">
                {{ packageLabel(record.summary_json?.asset_type) }}
                <span class="muted">{{
                  record.summary_json?.asset_key || ''
                }}</span>
              </template>
              <template v-else-if="column.key === 'rule_count'">
                {{ record.summary_json?.rule_count ?? '-' }}
              </template>
              <template v-else-if="column.key === 'example_count'">
                {{ record.summary_json?.example_count ?? '-' }}
              </template>
              <template v-else-if="column.key === 'status'">
                <Tag :color="record.status === 'succeeded' ? 'green' : 'red'">
                  {{ record.status }}
                </Tag>
              </template>
            </template>
          </Table>
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
          <div class="field-label">规则包名称</div>
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
      title="评论切角测试"
      ok-text="开始生成"
      cancel-text="取消"
      :confirm-loading="generating"
      @ok="generateFocusedCommentAngle"
    >
      <Space class="confirm-form" direction="vertical">
        <div class="form-field">
          <div class="field-label">评论切角</div>
          <Select
            v-model:value="focusGenerateForm.comment_angle"
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
}

.batch-list-item {
  min-height: 92px;
}

.batch-total {
  margin-top: 10px;
}

.result-card {
  min-height: 520px;
}

.result-heading {
  align-items: flex-start;
  display: flex;
  gap: 12px;
  justify-content: space-between;
  margin-bottom: 16px;
}

.result-topic {
  color: var(--maga-text, #1f2937);
  font-size: 18px;
  font-weight: 700;
  line-height: 1.45;
}

.result-subtitle {
  color: var(--maga-text-muted, #667085);
  font-size: 12px;
  margin-top: 4px;
}

.metric-row {
  margin-top: 0;
}

.metric-row :deep(.ant-statistic) {
  background: var(--maga-surface-soft, #f8fafc);
  border: 1px solid var(--maga-border, #edf0f5);
  border-radius: 8px;
  padding: 10px 12px;
}

.metric-row :deep(.ant-statistic-title) {
  color: var(--maga-text-muted, #667085);
  font-size: 12px;
  margin-bottom: 4px;
}

.metric-row :deep(.ant-statistic-content) {
  color: var(--maga-text, #1f2937);
  font-size: 20px;
  line-height: 1.35;
}

.result-list {
  margin-top: 16px;
}

.content-list-item {
  padding: 0 0 12px;
}

.content-item {
  border: 1px solid var(--maga-border, #edf0f5);
  border-radius: 8px;
  padding: 14px 16px;
  width: 100%;
}

.content-item.failed {
  background: var(--maga-error-soft, #fff7f7);
  border-color: var(--maga-error-border, #ffd6d6);
}

.content-item-header {
  align-items: flex-start;
  display: flex;
  gap: 12px;
  justify-content: space-between;
  margin-bottom: 10px;
}

.content-item h3 {
  color: var(--maga-text, #262626);
  font-size: 16px;
  line-height: 1.5;
  margin: 0 0 8px;
}

.content-body {
  color: var(--maga-text, #262626);
  line-height: 1.8;
  white-space: pre-wrap;
}

.diagnostics-row {
  margin-top: 16px;
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

.muted {
  color: var(--maga-text-muted, #8c8c8c);
  display: block;
  font-size: 12px;
  margin-top: 2px;
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
  .page-toolbar,
  .result-heading,
  .content-item-header {
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
