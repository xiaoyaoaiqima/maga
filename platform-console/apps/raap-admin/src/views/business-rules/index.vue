<script setup lang="ts">
import type { UploadProps } from 'ant-design-vue';
import type { AssetsApi } from '#/api/core/assets';

import { computed, onMounted, ref, watch } from 'vue';

import { ReloadOutlined, UploadOutlined } from '@ant-design/icons-vue';
import { useUserStore } from '@vben/stores';

import {
  Button,
  Card,
  Col,
  Descriptions,
  DescriptionsItem,
  Empty,
  Input,
  message,
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
const importRunsLoading = ref(false);
const packageType = ref<RulePackageType>('comment_angle');
const assetKey = ref(rulePackageConfigs.comment_angle.defaultAssetKey);
const displayName = ref(rulePackageConfigs.comment_angle.defaultDisplayName);
const ruleAssets = ref<AssetsApi.AssetSummary[]>([]);
const importRuns = ref<AssetsApi.AssetImportRun[]>([]);
const selectedSummary = ref<AssetsApi.AssetSummary | null>(null);
const selectedAsset = ref<AssetsApi.AssetRegistry | null>(null);
const userStore = useUserStore();

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

const rulePackageColumns: any[] = [
  { title: '规则包', dataIndex: 'display_name', key: 'display_name' },
  { title: '类型', dataIndex: 'asset_type', key: 'asset_type', width: 150 },
  { title: 'Key', dataIndex: 'asset_key', key: 'asset_key', width: 220 },
  { title: '版本', dataIndex: 'version_no', key: 'version_no', width: 80 },
  { title: '条数', dataIndex: 'item_count', key: 'item_count', width: 80 },
  { title: '来源', dataIndex: 'source_name', key: 'source_name', width: 220 },
  { title: '更新时间', dataIndex: 'update_time', key: 'update_time', width: 180 },
  { fixed: 'right', title: '操作', key: 'action', width: 90 },
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
      { title: '产品使用体验', dataIndex: 'product_experience', key: 'product_experience', width: 230 },
      { title: '月龄', dataIndex: 'baby_stage', key: 'baby_stage', width: 120 },
      { title: '使用时间', dataIndex: 'use_duration', key: 'use_duration', width: 120 },
      { title: '主题', dataIndex: 'topic', key: 'topic', width: 130 },
      { title: '语料', dataIndex: 'corpus', key: 'corpus' },
      { title: '示例', key: 'examples', width: 80 },
    ];
  }
  return [
    { title: '评论切角', dataIndex: 'comment_angle', key: 'comment_angle', width: 240 },
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
    if (!selectedSummary.value && ruleAssets.value.length) {
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

const beforeUpload: UploadProps['beforeUpload'] = async (file) => {
  const name = file.name.toLowerCase();
  if (!name.endsWith('.csv') && !name.endsWith('.xlsx')) {
    message.warning('只支持 .csv 或 .xlsx 文件');
    return Upload.LIST_IGNORE;
  }
  importing.value = true;
  try {
    const payload = {
      asset_key: assetKey.value,
      created_by: currentOperator.value,
      display_name: displayName.value,
      file,
    };
    const result =
      packageType.value === 'comment_angle'
        ? await importCommentAngleRuleSetApi(payload)
        : await importProductExperienceRuleSetApi(payload);
    message.success(
      `导入完成：${result.summary_json?.rule_count || 0} 条规则`,
    );
    selectedSummary.value = null;
    selectedAsset.value = null;
    await Promise.all([loadRuleAssets(), loadImportRuns()]);
  } catch {
    message.error('导入失败，请检查文件格式');
  } finally {
    importing.value = false;
  }
  return Upload.LIST_IGNORE;
};

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

function resetFormForType(type: RulePackageType) {
  const config = rulePackageConfigs[type];
  assetKey.value = config.defaultAssetKey;
  displayName.value = config.defaultDisplayName;
}

watch(packageType, resetFormForType);

onMounted(() => {
  loadRuleAssets();
  loadImportRuns();
});
</script>

<template>
  <div class="business-rule-page p-4">
    <Row :gutter="16">
      <Col :lg="8" :xs="24">
        <Card title="上传规则包" :bordered="false">
          <Space class="rule-form" direction="vertical">
            <Select
              v-model:value="packageType"
              :options="packageTypeOptions"
              class="full-width"
            />
            <Input v-model:value="displayName" placeholder="规则包名称" />
            <Input v-model:value="assetKey" placeholder="asset_key" />
            <Upload
              :accept="currentConfig.accept"
              :before-upload="beforeUpload"
              :disabled="importing"
              :show-upload-list="false"
            >
              <Button block type="primary" :loading="importing">
                <template #icon><UploadOutlined /></template>
                上传业务规则
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
            :scroll="{ x: 1180 }"
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
                <Button size="small" type="link" @click="openAsset(record)">
                  查看
                </Button>
              </template>
            </template>
          </Table>
        </Card>
      </Col>
    </Row>

    <Card class="mt-4" title="规则包详情" :bordered="false">
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
          <DescriptionsItem label="Key">
            {{ selectedAsset.asset_key }}
          </DescriptionsItem>
          <DescriptionsItem label="规则">
            {{ selectedRuleCount }}
          </DescriptionsItem>
          <DescriptionsItem label="示例">
            {{ selectedExampleCount }}
          </DescriptionsItem>
          <DescriptionsItem label="来源">
            {{ selectedAsset.source_name || '-' }}
          </DescriptionsItem>
          <DescriptionsItem label="上传人">
            {{ selectedAsset.created_by || '-' }}
          </DescriptionsItem>
        </Descriptions>

        <div v-if="selectedWarnings.length" class="warning-row">
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
            <span class="muted">{{ record.summary_json?.asset_key || '' }}</span>
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
