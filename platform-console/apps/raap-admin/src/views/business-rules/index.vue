<script setup lang="ts">
import type { UploadProps } from 'ant-design-vue';

import type { AssetsApi } from '#/api/core/assets';

import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { useUserStore } from '@vben/stores';

import {
  PlayCircleOutlined,
  ReloadOutlined,
  UploadOutlined,
} from '@ant-design/icons-vue';
import {
  Button,
  Card,
  Col,
  Descriptions,
  DescriptionsItem,
  Empty,
  Input,
  message,
  Modal,
  Row,
  Select,
  Space,
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
const router = useRouter();

const currentConfig = computed(() => rulePackageConfigs[packageType.value]);
const selectedItems = computed(() => {
  const items = selectedAsset.value?.content_json?.items;
  return Array.isArray(items) ? items.slice(0, 30) : [];
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

const rulePackageColumns: any[] = [
  { title: '规则包', dataIndex: 'display_name', key: 'display_name' },
  { title: '类型', dataIndex: 'asset_type', key: 'asset_type', width: 150 },
  { title: '版本', dataIndex: 'version_no', key: 'version_no', width: 80 },
  { title: '条数', dataIndex: 'item_count', key: 'item_count', width: 80 },
  { title: '来源', dataIndex: 'source_name', key: 'source_name', width: 220 },
  {
    title: '更新时间',
    dataIndex: 'update_time',
    key: 'update_time',
    width: 180,
  },
  { fixed: 'right', title: '操作', key: 'action', width: 150 },
];

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
    await router.push({
      path: '/content-agent/workbench',
      query: { batch_id: String(result.batch_id) },
    });
  } catch {
    message.error('生成失败，请检查规则包和 worker 状态');
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
});
</script>

<template>
  <div class="business-rule-page p-4">
    <Row :gutter="16">
      <Col :lg="8" :xs="24">
        <Card title="上传业务规则包" :bordered="false">
          <Space class="rule-form" direction="vertical">
            <div class="form-field">
              <div class="field-label">业务类型</div>
              <Select
                v-model:value="packageType"
                :disabled="importing"
                :options="packageTypeOptions"
                class="full-width"
              />
            </div>
            <Upload
              :accept="currentConfig.accept"
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
        </Card>
      </Col>

      <Col :lg="16" :xs="24">
        <Card title="业务规则包" :bordered="false">
          <template #extra>
            <Button size="small" @click="loadRuleAssets">
              <template #icon><ReloadOutlined /></template>
              刷新
            </Button>
          </template>
          <Table
            :columns="rulePackageColumns"
            :data-source="ruleAssets"
            :loading="loading"
            :pagination="{ pageSize: 6 }"
            :scroll="{ x: 960 }"
            row-key="id"
            size="small"
          >
            <template #bodyCell="{ column, record, text }">
              <template v-if="column.key === 'display_name'">
                {{ record.display_name || packageLabel(record.asset_type) }}
              </template>
              <template v-else-if="column.key === 'asset_type'">
                <Tag>{{ packageLabel(record.asset_type) }}</Tag>
              </template>
              <template v-else-if="column.key === 'version_no'">
                v{{ text }}
              </template>
              <template v-else-if="column.key === 'item_count'">
                {{ text ?? '-' }}
              </template>
              <template v-else-if="column.key === 'action'">
                <Space size="small">
                  <Button size="small" type="link" @click="openAsset(record)">
                    查看
                  </Button>
                  <Button
                    size="small"
                    type="link"
                    :loading="generating"
                    @click="generateFromRulePackage(record)"
                  >
                    生成
                  </Button>
                </Space>
              </template>
            </template>
          </Table>
        </Card>
      </Col>
    </Row>

    <Card class="mt-4" title="规则包详情" :bordered="false">
      <template #extra>
        <Button
          v-if="selectedAsset"
          type="primary"
          :loading="generating"
          @click="generateFromRulePackage(selectedAsset)"
        >
          <template #icon><PlayCircleOutlined /></template>
          按此规则包生成
        </Button>
      </template>
      <template v-if="selectedAsset">
        <Descriptions size="small" :column="4" bordered>
          <DescriptionsItem label="名称">
            {{ selectedAsset.display_name || '-' }}
          </DescriptionsItem>
          <DescriptionsItem label="类型">
            <Tag>{{ packageLabel(selectedAsset.asset_type) }}</Tag>
          </DescriptionsItem>
          <DescriptionsItem label="版本">
            v{{ selectedAsset.version_no }}
          </DescriptionsItem>
          <DescriptionsItem label="规则">
            {{ selectedRuleCount }}
          </DescriptionsItem>
          <DescriptionsItem label="示例">
            {{ selectedExampleCount }}
          </DescriptionsItem>
          <DescriptionsItem label="默认生成">
            {{ selectedDefaultGenerationCount }}
          </DescriptionsItem>
          <DescriptionsItem label="来源">
            {{ selectedAsset.source_name || '-' }}
          </DescriptionsItem>
          <DescriptionsItem label="上传人">
            {{ selectedAsset.created_by || '-' }}
          </DescriptionsItem>
        </Descriptions>

        <div v-if="selectedWarnings.length > 0" class="warning-row">
          <Tag
            v-for="warning in selectedWarnings"
            :key="warning"
            color="orange"
          >
            {{ warning }}
          </Tag>
        </div>

        <Table
          class="mt-4"
          :columns="previewColumns"
          :data-source="selectedItems"
          :pagination="{ pageSize: 8 }"
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
      <Empty v-else description="暂无业务规则包" />
    </Card>

    <Card class="mt-4" title="导入记录" :bordered="false">
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
        :pagination="{ pageSize: 8 }"
        :scroll="{ x: 1120 }"
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
          <div class="field-label">规则包名称</div>
          <Input
            v-model:value="displayName"
            :disabled="importing"
            placeholder="默认取文件名，可编辑"
          />
        </div>
      </Space>
    </Modal>
  </div>
</template>

<style scoped>
.business-rule-page {
  background: #f5f7fb;
  min-height: 100%;
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
  color: #595959;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 6px;
}

.confirm-file {
  align-items: center;
  background: #f5f7fb;
  border: 1px solid #edf0f5;
  border-radius: 8px;
  display: flex;
  gap: 12px;
  justify-content: space-between;
  padding: 10px 12px;
}

.confirm-file span {
  color: #8c8c8c;
}

.confirm-file strong {
  color: #262626;
  font-weight: 600;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.warning-row {
  margin-top: 12px;
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
  color: #8c8c8c;
  display: block;
  font-size: 12px;
  margin-top: 2px;
}
</style>
