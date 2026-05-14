<script setup lang="ts">
import type { UploadProps } from 'ant-design-vue';
import type { AssetsApi } from '#/api/core/assets';

import { computed, onMounted, ref } from 'vue';

import { useUserStore } from '@vben/stores';

import {
  Button,
  Card,
  Collapse,
  CollapsePanel,
  Descriptions,
  DescriptionsItem,
  message,
  Select,
  Space,
  Table,
  Tag,
  Upload,
} from 'ant-design-vue';

import {
  applyAssetChangeProposalApi,
  getAssetChangeRequestsApi,
  getAssetChangeProposalsApi,
  getAssetDetailApi,
  getAssetImportRunsApi,
  getAssetSummariesApi,
  importYuanyueTrainingRulesApi,
  proposeComplianceRuleApi,
} from '#/api/core/assets';

const loading = ref(false);
const importing = ref(false);
const assetKey = ref('yuanyue');
const assetStage = ref('');
const assets = ref<AssetsApi.AssetSummary[]>([]);
const importRuns = ref<AssetsApi.AssetImportRun[]>([]);
const changeRequests = ref<AssetsApi.AssetChangeRequest[]>([]);
const changeProposals = ref<AssetsApi.AssetChangeProposal[]>([]);
const selectedAsset = ref<AssetsApi.AssetRegistry | null>(null);
const selectedSummary = ref<AssetsApi.AssetSummary | null>(null);
const applyingProposalIds = ref<number[]>([]);
const proposingRequestIds = ref<number[]>([]);
const userStore = useUserStore();

const assetKeyOptions = computed(() => [
  ...new Set(['yuanyue', ...assets.value.map((item) => item.asset_key)]),
]);

const assetStageOptions = [
  { label: '全部阶段', value: '' },
  { label: '正式', value: 'production' },
  { label: '候选', value: 'candidate' },
];

const currentOperator = computed(
  () =>
    userStore.userInfo?.realName ||
    userStore.userInfo?.username ||
    'maga-operator',
);

const previewItems = computed(() => {
  const items = selectedAsset.value?.content_json?.items;
  return Array.isArray(items) ? items.slice(0, 20) : [];
});

const isPainpointExpressionAsset = computed(
  () => selectedAsset.value?.asset_type === 'painpoint_expression_candidates',
);

const isPersonaProfilesAsset = computed(
  () => selectedAsset.value?.asset_type === 'persona_profiles',
);

const isWritingPatternsAsset = computed(
  () => selectedAsset.value?.asset_type === 'reference_writing_patterns',
);

const personaProfileItems = computed(() => {
  const items = selectedAsset.value?.content_json?.items;
  if (!Array.isArray(items)) return [];
  return items
    .filter((item) => item && typeof item === 'object')
    .map((item, index) => ({
      ...item,
      row_key: item.persona_id || `${item.persona_name || 'persona'}-${index}`,
    }));
});

const writingPatternItems = computed(() => {
  const items = selectedAsset.value?.content_json?.items;
  if (!Array.isArray(items)) return [];
  return items
    .filter((item) => item && typeof item === 'object')
    .map((item, index) => ({
      ...item,
      row_key: item.pattern_id || `${item.source_example_id || 'pattern'}-${index}`,
    }));
});

const pendingChangeRequests = computed(
  () =>
    changeRequests.value.filter((request) => request.status === 'pending')
      .length,
);

const proposedChangeRequests = computed(
  () =>
    changeRequests.value.filter((request) => request.status === 'proposed')
      .length,
);

const proposedChangeProposals = computed(
  () =>
    changeProposals.value.filter((proposal) => proposal.status === 'proposed')
      .length,
);

const painpointExpressionGroups = computed(() => {
  const items = selectedAsset.value?.content_json?.items;
  if (!Array.isArray(items)) return [];
  const normalizedItems = normalizePainpointExpressionItems(items);

  const topicMap = new Map<
    string,
    {
      aiCount: number;
      seedCount: number;
      symptomMap: Map<
        string,
        {
          aiCount: number;
          expressions: any[];
          seedCount: number;
        }
      >;
      total: number;
    }
  >();

  for (const [index, item] of normalizedItems.entries()) {
    if (!item || typeof item !== 'object') continue;
    const topic = String(item.topic || item.painpoint || '未归类主题');
    const symptom = String(
      item.symptom || item.manifestation || '自动归类表现',
    );
    const source = String(item.expression_source || item.source || '');
    const isAi = source.includes('ai') || source.includes('llm');

    if (!topicMap.has(topic)) {
      topicMap.set(topic, {
        aiCount: 0,
        seedCount: 0,
        symptomMap: new Map(),
        total: 0,
      });
    }
    const topicGroup = topicMap.get(topic)!;
    if (!topicGroup.symptomMap.has(symptom)) {
      topicGroup.symptomMap.set(symptom, {
        aiCount: 0,
        expressions: [],
        seedCount: 0,
      });
    }
    const symptomGroup = topicGroup.symptomMap.get(symptom)!;

    topicGroup.total += 1;
    symptomGroup.expressions.push({
      ...item,
      row_key: `${topic}-${symptom}-${index}`,
    });
    if (isAi) {
      topicGroup.aiCount += 1;
      symptomGroup.aiCount += 1;
    } else {
      topicGroup.seedCount += 1;
      symptomGroup.seedCount += 1;
    }
  }

  // 这里按资产语义重组展示：生成选项只看核心痛点，扩写内容落在表现和描述层。
  return [...topicMap.entries()].map(([topic, group]) => ({
    aiCount: group.aiCount,
    seedCount: group.seedCount,
    symptoms: [...group.symptomMap.entries()].map(
      ([symptom, symptomGroup]) => ({
        aiCount: symptomGroup.aiCount,
        expressions: symptomGroup.expressions,
        seedCount: symptomGroup.seedCount,
        symptom,
        total: symptomGroup.expressions.length,
      }),
    ),
    topic,
    total: group.total,
  }));
});

function normalizePainpointExpressionItems(items: any[]) {
  const normalizedItems = items
    .filter((item) => item && typeof item === 'object')
    .map((item) => ({ ...item }));
  const profiles = buildSymptomProfiles(normalizedItems);
  const offsets = new Map<string, number>();

  for (const item of normalizedItems) {
    if (item.symptom || item.manifestation) continue;
    const topic = String(item.topic || item.painpoint || '').trim();
    const expression = String(item.expression || item.description || '').trim();
    const symptom = inferSymptom(topic, expression, profiles, offsets);
    if (symptom) {
      // 前端兼容历史候选资产：旧 AI 扩写缺 symptom 时，展示层按已有种子表现归组。
      item.symptom = symptom;
      item.symptom_source = 'auto_inferred';
    }
  }
  return normalizedItems;
}

function buildSymptomProfiles(items: any[]) {
  const profiles = new Map<string, Map<string, string[]>>();
  for (const item of items) {
    const topic = String(item.topic || item.painpoint || '').trim();
    const symptom = String(item.symptom || item.manifestation || '').trim();
    if (!topic || !symptom) continue;
    if (!profiles.has(topic)) profiles.set(topic, new Map());
    const topicProfiles = profiles.get(topic)!;
    if (!topicProfiles.has(symptom)) topicProfiles.set(symptom, [symptom]);
    const texts = topicProfiles.get(symptom)!;
    for (const key of ['expression', 'description']) {
      const value = String(item[key] || '').trim();
      if (value) texts.push(value);
    }
  }
  return profiles;
}

function inferSymptom(
  topic: string,
  expression: string,
  profiles: Map<string, Map<string, string[]>>,
  offsets: Map<string, number>,
) {
  const topicProfiles = profiles.get(topic);
  if (!topicProfiles?.size) return '';
  const scored = [...topicProfiles.entries()]
    .map(([symptom, texts]) => ({
      score: similarityScore(expression, texts),
      symptom,
    }))
    .sort((left, right) => right.score - left.score);
  if (scored[0]?.score > 0) return scored[0].symptom;

  const symptoms = [...topicProfiles.keys()];
  const offset = offsets.get(topic) || 0;
  offsets.set(topic, offset + 1);
  return symptoms[offset % symptoms.length] || '';
}

function similarityScore(expression: string, profileTexts: string[]) {
  const expressionTerms = textTerms(expression);
  if (!expressionTerms.size) return 0;
  return profileTexts.reduce((best, text) => {
    const terms = textTerms(text);
    if (!terms.size) return best;
    const overlap = [...expressionTerms].filter((term) =>
      terms.has(term),
    ).length;
    if (overlap === 0) return best;
    const union = new Set([...expressionTerms, ...terms]).size;
    return Math.max(best, overlap / union);
  }, 0);
}

function textTerms(value: string) {
  const text = value.replaceAll(/\s+/g, '');
  const terms = new Set<string>();
  for (const match of text.matchAll(/[\u4e00-\u9fa5A-Za-z0-9]{2,}/g)) {
    terms.add(match[0]);
  }
  for (let index = 0; index < text.length - 1; index += 1) {
    terms.add(text.slice(index, index + 2));
  }
  return terms;
}

const assetColumns = [
  { title: '类型', dataIndex: 'asset_type', key: 'asset_type', width: 190 },
  { title: '阶段', dataIndex: 'asset_stage', key: 'asset_stage', width: 100 },
  { title: '版本', dataIndex: 'version_no', key: 'version_no', width: 80 },
  { title: '条数', dataIndex: 'item_count', key: 'item_count', width: 80 },
  { title: '来源', dataIndex: 'source_name', key: 'source_name' },
  { title: '创建人', dataIndex: 'created_by', key: 'created_by', width: 100 },
  { title: '操作', key: 'action', width: 90 },
];

const importColumns = [
  { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
  { title: '来源文件', dataIndex: 'source_name', key: 'source_name' },
  {
    title: '资产数',
    dataIndex: 'imported_assets',
    key: 'imported_assets',
    width: 90,
  },
  { title: '状态', dataIndex: 'status', key: 'status', width: 90 },
  { title: '创建人', dataIndex: 'created_by', key: 'created_by', width: 100 },
  { title: '时间', dataIndex: 'create_time', key: 'create_time', width: 180 },
];

const changeRequestColumns = [
  { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 90 },
  { title: '来源', dataIndex: 'requester', key: 'requester', width: 110 },
  { title: '变更需求', dataIndex: 'source_text', key: 'source_text' },
  { title: '时间', dataIndex: 'create_time', key: 'create_time', width: 180 },
  { fixed: 'right', title: '操作', key: 'action', width: 190 },
];

const changeProposalColumns = [
  { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
  { title: '请求ID', dataIndex: 'request_id', key: 'request_id', width: 80 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 90 },
  { title: '风险', dataIndex: 'risk_level', key: 'risk_level', width: 80 },
  { title: '摘要', dataIndex: 'summary', key: 'summary' },
  { title: '时间', dataIndex: 'create_time', key: 'create_time', width: 180 },
  { fixed: 'right', title: '操作', key: 'action', width: 190 },
];

const assetStageLabels: Record<string, { color: string; label: string }> = {
  candidate: { color: 'orange', label: '候选' },
  production: { color: 'green', label: '正式' },
};

const changeRequestStatusLabels: Record<
  string,
  { color: string; label: string }
> = {
  applied: { color: 'green', label: '已应用' },
  pending: { color: 'orange', label: '待处理' },
  proposed: { color: 'blue', label: '已有草案' },
};

const changeProposalStatusLabels: Record<
  string,
  { color: string; label: string }
> = {
  applied: { color: 'green', label: '已应用' },
  proposed: { color: 'orange', label: '待应用' },
};

const previewColumns = computed(() => {
  const keys = new Set<string>();
  for (const item of previewItems.value.slice(0, 5)) {
    if (!item || typeof item !== 'object') continue;
    Object.keys(item).forEach((key) => keys.add(key));
  }
  return [...keys].slice(0, 6).map((key) => ({
    title: key,
    dataIndex: key,
    key,
    ellipsis: true,
  }));
});

const expressionColumns = [
  { title: '描述', dataIndex: 'expression', key: 'expression' },
  {
    title: '来源',
    dataIndex: 'expression_source',
    key: 'expression_source',
    width: 120,
  },
  {
    title: '状态',
    dataIndex: 'review_status',
    key: 'review_status',
    width: 110,
  },
  {
    title: '原始列',
    dataIndex: 'source_column',
    key: 'source_column',
    width: 110,
  },
];

const personaColumns = [
  { title: '人设', dataIndex: 'persona_name', key: 'persona_name', width: 140 },
  { title: '稳定身份', dataIndex: 'persona_type', key: 'persona_type', width: 160 },
  { title: '语气特征', dataIndex: 'voice_traits', key: 'voice_traits' },
  { title: '适配主题', dataIndex: 'suitable_topics', key: 'suitable_topics' },
  {
    title: '适配人群',
    dataIndex: 'target_audience_fit',
    key: 'target_audience_fit',
  },
  {
    title: '场景触发',
    dataIndex: 'scene_triggers',
    key: 'scene_triggers',
  },
  {
    title: '状态',
    dataIndex: 'review_status',
    key: 'review_status',
    width: 100,
  },
];

const writingPatternColumns = [
  { title: '来源', dataIndex: 'source_title', key: 'source_title', width: 180 },
  {
    title: '开头方式',
    dataIndex: 'opening_pattern',
    key: 'opening_pattern',
  },
  { title: '叙事结构', dataIndex: 'story_arc', key: 'story_arc' },
  {
    title: '卖点植入',
    dataIndex: 'selling_point_placement',
    key: 'selling_point_placement',
  },
  { title: '证据方式', dataIndex: 'proof_style', key: 'proof_style', width: 160 },
  { title: '状态', dataIndex: 'review_status', key: 'review_status', width: 100 },
];

async function loadAssets() {
  loading.value = true;
  try {
    assets.value = await getAssetSummariesApi({
      asset_key: assetKey.value,
      asset_stage: assetStage.value,
    });
    if (!selectedSummary.value && assets.value.length) {
      await openAsset(assets.value[0]);
    }
  } catch {
    message.error('获取资料资产失败');
  } finally {
    loading.value = false;
  }
}

async function loadImportRuns() {
  try {
    importRuns.value = await getAssetImportRunsApi({ limit: 20 });
  } catch {
    message.error('获取导入记录失败');
  }
}

async function loadChangeRequests() {
  try {
    changeRequests.value = await getAssetChangeRequestsApi({ limit: 20 });
  } catch {
    message.error('获取资产变更请求失败');
  }
}

async function loadChangeProposals() {
  try {
    changeProposals.value = await getAssetChangeProposalsApi({ limit: 20 });
  } catch {
    message.error('获取资产变更草案失败');
  }
}

async function handleProposeComplianceRule(record: AssetsApi.AssetChangeRequest) {
  if (proposingRequestIds.value.includes(record.id)) return;
  proposingRequestIds.value = [...proposingRequestIds.value, record.id];
  try {
    await proposeComplianceRuleApi(record.id);
    message.success('已生成候选规则草案');
    await Promise.all([loadChangeRequests(), loadChangeProposals()]);
  } catch {
    message.error('生成规则草案失败');
  } finally {
    proposingRequestIds.value = proposingRequestIds.value.filter(
      (id) => id !== record.id,
    );
  }
}

async function handleApplyProposal(record: AssetsApi.AssetChangeProposal) {
  if (applyingProposalIds.value.includes(record.id)) return;
  applyingProposalIds.value = [...applyingProposalIds.value, record.id];
  try {
    await applyAssetChangeProposalApi(record.id);
    message.success('已应用为候选资产');
    await Promise.all([loadAssets(), loadChangeRequests(), loadChangeProposals()]);
  } catch {
    message.error('应用草案失败');
  } finally {
    applyingProposalIds.value = applyingProposalIds.value.filter(
      (id) => id !== record.id,
    );
  }
}

async function openAsset(row: AssetsApi.AssetSummary) {
  selectedSummary.value = row;
  selectedAsset.value = await getAssetDetailApi(row.asset_type, row.asset_key, {
    asset_stage: row.asset_stage,
  });
}

const beforeUpload: UploadProps['beforeUpload'] = async (file) => {
  if (!file.name.endsWith('.xlsx')) {
    message.warning('只支持 .xlsx 文件');
    return Upload.LIST_IGNORE;
  }
  importing.value = true;
  try {
    const result = await importYuanyueTrainingRulesApi({
      asset_key: assetKey.value,
      created_by: currentOperator.value,
      file,
    });
    message.success(`导入完成：${result.imported_assets} 类资产`);
    selectedAsset.value = null;
    selectedSummary.value = null;
    await Promise.all([loadAssets(), loadImportRuns()]);
  } catch {
    message.error('导入失败，请检查文件格式');
  } finally {
    importing.value = false;
  }
  return Upload.LIST_IGNORE;
};

function formatValue(value: any) {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function hasProposalForRequest(requestId: number) {
  return changeProposals.value.some((proposal) => proposal.request_id === requestId);
}

function isProposingRequest(requestId: number) {
  return proposingRequestIds.value.includes(requestId);
}

function isApplyingProposal(proposalId: number) {
  return applyingProposalIds.value.includes(proposalId);
}

onMounted(() => {
  loadAssets();
  loadImportRuns();
  loadChangeRequests();
  loadChangeProposals();
});
</script>

<template>
  <div class="asset-training-page">
    <div class="toolbar">
      <Space>
        <Select
          v-model:value="assetKey"
          class="asset-key-select"
          :options="assetKeyOptions.map((value) => ({ label: value, value }))"
          show-search
        />
        <Select
          v-model:value="assetStage"
          class="asset-stage-select"
          :options="assetStageOptions"
          @change="loadAssets"
        />
        <Button @click="loadAssets">刷新</Button>
        <Button @click="loadChangeRequests">刷新变更请求</Button>
        <Button @click="loadChangeProposals">刷新草案</Button>
        <Upload
          accept=".xlsx"
          :before-upload="beforeUpload"
          :show-upload-list="false"
        >
          <Button type="primary" :loading="importing">上传训练规则</Button>
        </Upload>
      </Space>
    </div>

    <div class="layout-grid">
      <Card title="资料资产" :bordered="false">
        <Table
          :columns="assetColumns"
          :data-source="assets"
          :loading="loading"
          :pagination="{ pageSize: 10 }"
          row-key="id"
          size="small"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'asset_type'">
              <Tag>{{ record.asset_type }}</Tag>
            </template>
            <template v-else-if="column.key === 'asset_stage'">
              <Tag
                :color="
                  assetStageLabels[record.asset_stage]?.color || 'default'
                "
              >
                {{
                  assetStageLabels[record.asset_stage]?.label ||
                  record.asset_stage
                }}
              </Tag>
            </template>
            <template v-else-if="column.key === 'item_count'">
              {{ record.item_count ?? '-' }}
            </template>
            <template v-else-if="column.key === 'action'">
              <Button size="small" type="link" @click="openAsset(record)"
                >查看</Button
              >
            </template>
          </template>
        </Table>
      </Card>

      <Card title="资产详情" :bordered="false">
        <template v-if="selectedAsset">
          <Descriptions size="small" :column="2" bordered>
            <DescriptionsItem label="类型">
              {{ selectedAsset.asset_type }}
            </DescriptionsItem>
            <DescriptionsItem label="版本">
              v{{ selectedAsset.version_no }}
            </DescriptionsItem>
            <DescriptionsItem label="阶段">
              <Tag
                :color="
                  assetStageLabels[selectedAsset.asset_stage]?.color ||
                  'default'
                "
              >
                {{
                  assetStageLabels[selectedAsset.asset_stage]?.label ||
                  selectedAsset.asset_stage
                }}
              </Tag>
            </DescriptionsItem>
            <DescriptionsItem label="来源">
              {{ selectedAsset.source_name || '-' }}
            </DescriptionsItem>
            <DescriptionsItem label="条数">
              {{ selectedSummary?.item_count ?? '-' }}
            </DescriptionsItem>
          </Descriptions>

          <div v-if="isPainpointExpressionAsset" class="hierarchy-view">
            <div class="hierarchy-summary">
              <Tag color="blue"
                >{{ painpointExpressionGroups.length }} 个主题</Tag
              >
              <Tag color="green">
                {{
                  painpointExpressionGroups.reduce(
                    (sum, group) => sum + group.symptoms.length,
                    0,
                  )
                }}
                个具体表现
              </Tag>
              <Tag color="purple">
                {{
                  painpointExpressionGroups.reduce(
                    (sum, group) => sum + group.total,
                    0,
                  )
                }}
                条描述
              </Tag>
            </div>

            <Collapse class="topic-collapse">
              <CollapsePanel
                v-for="group in painpointExpressionGroups"
                :key="group.topic"
              >
                <template #header>
                  <div class="topic-header">
                    <span class="topic-title">{{ group.topic }}</span>
                    <Space size="small">
                      <Tag>{{ group.symptoms.length }} 个表现</Tag>
                      <Tag color="green">种子 {{ group.seedCount }}</Tag>
                      <Tag color="orange">AI {{ group.aiCount }}</Tag>
                    </Space>
                  </div>
                </template>

                <div
                  v-for="symptomGroup in group.symptoms"
                  :key="`${group.topic}-${symptomGroup.symptom}`"
                  class="symptom-group"
                >
                  <div class="symptom-header">
                    <span class="symptom-title">{{
                      symptomGroup.symptom
                    }}</span>
                    <Space size="small">
                      <Tag>{{ symptomGroup.total }} 条描述</Tag>
                      <Tag color="green">种子 {{ symptomGroup.seedCount }}</Tag>
                      <Tag color="orange">AI {{ symptomGroup.aiCount }}</Tag>
                    </Space>
                  </div>
                  <Table
                    :columns="expressionColumns"
                    :data-source="symptomGroup.expressions"
                    :pagination="false"
                    row-key="row_key"
                    size="small"
                  >
                    <template #bodyCell="{ column, record, text }">
                      <template v-if="column.key === 'expression_source'">
                        <Tag
                          :color="
                            String(text || '').includes('ai')
                              ? 'orange'
                              : 'green'
                          "
                        >
                          {{ formatValue(text) }}
                        </Tag>
                      </template>
                      <template v-else-if="column.key === 'review_status'">
                        <Tag
                          :color="
                            record.review_status === 'approved'
                              ? 'green'
                              : 'default'
                          "
                        >
                          {{ formatValue(text) }}
                        </Tag>
                      </template>
                      <template v-else>
                        <span class="expression-text">{{
                          formatValue(text)
                        }}</span>
                      </template>
                    </template>
                  </Table>
                </div>
              </CollapsePanel>
            </Collapse>
          </div>

          <div v-else-if="isPersonaProfilesAsset" class="persona-view">
            <div class="hierarchy-summary">
              <Tag color="blue">{{ personaProfileItems.length }} 个人设</Tag>
              <Tag color="orange">
                {{
                  personaProfileItems.filter(
                    (item) => item.review_status === 'pending',
                  ).length
                }}
                个待审核
              </Tag>
              <Tag v-if="selectedAsset.content_json?.excluded_personas?.length">
                已排除
                {{ selectedAsset.content_json.excluded_personas.join('、') }}
              </Tag>
            </div>
            <Table
              :columns="personaColumns"
              :data-source="personaProfileItems"
              :pagination="{ pageSize: 6 }"
              row-key="row_key"
              size="small"
            >
              <template #bodyCell="{ column, record, text }">
                <template
                  v-if="
                    [
                      'voice_traits',
                      'suitable_topics',
                      'target_audience_fit',
                      'scene_triggers',
                    ].includes(String(column.key))
                  "
                >
                  <Space wrap size="small">
                    <Tag v-for="item in text || []" :key="item">
                      {{ item }}
                    </Tag>
                  </Space>
                </template>
                <template v-else-if="column.key === 'persona_name'">
                  <div class="persona-name">{{ formatValue(text) }}</div>
                  <div class="persona-tone">
                    {{ formatValue(record.sample_tone) }}
                  </div>
                </template>
                <template v-else-if="column.key === 'review_status'">
                  <Tag
                    :color="
                      record.review_status === 'approved'
                        ? 'green'
                        : 'orange'
                    "
                  >
                    {{ formatValue(text) }}
                  </Tag>
                </template>
                <template v-else>
                  <span class="cell-text">{{ formatValue(text) }}</span>
                </template>
              </template>
              <template #expandedRowRender="{ record }">
                <div class="persona-expanded">
                  <div>
                    <span class="expanded-label">开头方式：</span>
                    {{ (record.opening_patterns || []).join('；') || '-' }}
                  </div>
                  <div>
                    <span class="expanded-label">禁用表达：</span>
                    {{ (record.avoid_patterns || []).join('；') || '-' }}
                  </div>
                </div>
              </template>
            </Table>
          </div>

          <div v-else-if="isWritingPatternsAsset" class="writing-pattern-view">
            <div class="hierarchy-summary">
              <Tag color="blue">{{ writingPatternItems.length }} 条写法资产</Tag>
              <Tag color="orange">
                {{
                  writingPatternItems.filter(
                    (item) => item.review_status === 'pending',
                  ).length
                }}
                个待审核
              </Tag>
              <Tag>
                来源例文 {{ selectedAsset.content_json?.source_asset_id || '-' }}
              </Tag>
            </div>
            <Table
              :columns="writingPatternColumns"
              :data-source="writingPatternItems"
              :pagination="{ pageSize: 6 }"
              row-key="row_key"
              size="small"
            >
              <template #bodyCell="{ column, record, text }">
                <template v-if="column.key === 'source_title'">
                  <div class="persona-name">{{ formatValue(text) }}</div>
                  <div class="persona-tone">
                    {{ formatValue(record.source_example_id) }}
                  </div>
                </template>
                <template v-else-if="column.key === 'review_status'">
                  <Tag
                    :color="
                      record.review_status === 'approved'
                        ? 'green'
                        : 'orange'
                    "
                  >
                    {{ formatValue(text) }}
                  </Tag>
                </template>
                <template v-else>
                  <span class="pattern-text">{{ formatValue(text) }}</span>
                </template>
              </template>
              <template #expandedRowRender="{ record }">
                <div class="pattern-expanded">
                  <div>
                    <span class="expanded-label">适配主题：</span>
                    {{ (record.topic_fit || []).join('、') || '-' }}
                  </div>
                  <div>
                    <span class="expanded-label">适配人群：</span>
                    {{ (record.audience_fit || []).join('、') || '-' }}
                  </div>
                  <div>
                    <span class="expanded-label">语气特征：</span>
                    {{ (record.voice_traits || []).join('、') || '-' }}
                  </div>
                  <div>
                    <span class="expanded-label">禁复用短语：</span>
                    {{ (record.avoid_copy_phrases || []).join('；') || '-' }}
                  </div>
                  <div>
                    <span class="expanded-label">风险提示：</span>
                    {{ (record.risk_notes || []).join('；') || '-' }}
                  </div>
                </div>
              </template>
            </Table>
          </div>

          <Table
            v-else
            class="preview-table"
            :columns="previewColumns"
            :data-source="previewItems"
            :pagination="{ pageSize: 5 }"
            row-key="asset_steward_id"
            size="small"
          >
            <template #bodyCell="{ text }">
              <span class="cell-text">{{ formatValue(text) }}</span>
            </template>
          </Table>
        </template>
        <div v-else class="empty-state">请选择左侧资产查看内容。</div>
      </Card>
    </div>

    <Card class="mt-4" title="导入记录" :bordered="false">
      <Table
        :columns="importColumns"
        :data-source="importRuns"
        :pagination="{ pageSize: 5 }"
        row-key="id"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <Tag :color="record.status === 'succeeded' ? 'green' : 'red'">
              {{ record.status }}
            </Tag>
          </template>
        </template>
      </Table>
    </Card>

    <Card class="mt-4" :bordered="false">
      <template #title>
        <div class="section-title">
          <span>资产变更请求</span>
          <Space size="small">
            <Tag color="orange">待处理 {{ pendingChangeRequests }}</Tag>
            <Tag color="blue">已有草案 {{ proposedChangeRequests }}</Tag>
          </Space>
        </div>
      </template>
      <template #extra>
        <Button size="small" @click="loadChangeRequests">刷新</Button>
      </template>
      <div class="flow-hint">
        人工反馈会先进入这里；确认是事实/合规类问题后，先生成规则草案，再应用为候选资产。
      </div>
      <Table
        :columns="changeRequestColumns"
        :data-source="changeRequests"
        :pagination="{ pageSize: 5 }"
        row-key="id"
        :scroll="{ x: 1080 }"
        :locale="{
          emptyText:
            '暂无资产变更请求。文章反馈里提交事实/合规类修改意见后，会自动进入这里处理。',
        }"
        size="small"
      >
        <template #bodyCell="{ column, record, text }">
          <template v-if="column.key === 'status'">
            <Tag
              :color="
                changeRequestStatusLabels[record.status]?.color || 'default'
              "
            >
              {{ changeRequestStatusLabels[record.status]?.label || record.status }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'source_text'">
            <div class="change-request-text">
              {{ formatValue(text) }}
            </div>
            <div class="change-request-meta">
              {{
                record.context_json?.asset_key
                  ? `资料：${record.context_json.asset_key}`
                  : ''
              }}
              {{
                record.context_json?.item_no
                  ? ` · 第 ${record.context_json.item_no} 篇`
                  : ''
              }}
            </div>
          </template>
          <template v-else-if="column.key === 'action'">
            <Space size="small">
              <Button
                :disabled="
                  record.status === 'applied' || hasProposalForRequest(record.id)
                "
                :loading="isProposingRequest(record.id)"
                size="small"
                type="primary"
                @click="handleProposeComplianceRule(record)"
              >
                {{
                  hasProposalForRequest(record.id) ? '已生成草案' : '生成规则草案'
                }}
              </Button>
            </Space>
          </template>
        </template>
      </Table>
    </Card>

    <Card class="mt-4" :bordered="false">
      <template #title>
        <div class="section-title">
          <span>资产变更草案</span>
          <Tag color="orange">待应用 {{ proposedChangeProposals }}</Tag>
        </div>
      </template>
      <template #extra>
        <Button size="small" @click="loadChangeProposals">刷新</Button>
      </template>
      <div class="flow-hint">
        应用草案不会直接改正式资产，只会新增候选资产；候选资产确认后再进入正式生成链路。
      </div>
      <Table
        :columns="changeProposalColumns"
        :data-source="changeProposals"
        :pagination="{ pageSize: 5 }"
        row-key="id"
        :scroll="{ x: 1080 }"
        :locale="{
          emptyText:
            '暂无资产变更草案。先在上方请求列表点击“生成规则草案”。',
        }"
        size="small"
      >
        <template #bodyCell="{ column, record, text }">
          <template v-if="column.key === 'status'">
            <Tag
              :color="
                changeProposalStatusLabels[record.status]?.color || 'default'
              "
            >
              {{ changeProposalStatusLabels[record.status]?.label || record.status }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'risk_level'">
            <Tag :color="record.risk_level === 'high' ? 'red' : 'orange'">
              {{ record.risk_level }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'summary'">
            <div class="change-request-text">{{ formatValue(text) }}</div>
            <div class="change-request-meta">
              {{
                record.proposed_changes_json?.assets?.[0]?.asset_type
                  ? `资产：${record.proposed_changes_json.assets[0].asset_type}`
                  : ''
              }}
              {{
                record.proposed_changes_json?.assets?.[0]?.asset_stage
                  ? ` · 阶段：${record.proposed_changes_json.assets[0].asset_stage}`
                  : ''
              }}
            </div>
          </template>
          <template v-else-if="column.key === 'action'">
            <Button
              :disabled="record.status === 'applied'"
              :loading="isApplyingProposal(record.id)"
              size="small"
              type="primary"
              @click="handleApplyProposal(record)"
            >
              {{ record.status === 'applied' ? '已应用' : '应用为候选资产' }}
            </Button>
          </template>
        </template>
      </Table>
    </Card>
  </div>
</template>

<style scoped>
.asset-training-page {
  padding: 16px;
}

.toolbar {
  margin-bottom: 12px;
}

.asset-key-select {
  width: 180px;
}

.asset-stage-select {
  width: 120px;
}

.layout-grid {
  display: grid;
  grid-template-columns: minmax(420px, 1fr) minmax(420px, 1fr);
  gap: 12px;
}

.section-title {
  align-items: center;
  display: flex;
  gap: 12px;
}

.flow-hint {
  background: #fafafa;
  border: 1px solid #f0f0f0;
  color: #595959;
  font-size: 13px;
  line-height: 1.6;
  margin-bottom: 12px;
  padding: 8px 12px;
}

.preview-table {
  margin-top: 12px;
}

.hierarchy-view {
  margin-top: 12px;
}

.persona-view {
  margin-top: 12px;
}

.writing-pattern-view {
  margin-top: 12px;
}

.hierarchy-summary {
  margin-bottom: 12px;
}

.topic-collapse {
  background: #fff;
}

.topic-header {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
  width: 100%;
}

.topic-title {
  color: #1f1f1f;
  font-weight: 600;
}

.symptom-group {
  border-bottom: 1px solid #f0f0f0;
  padding: 12px 0;
}

.symptom-group:first-child {
  padding-top: 0;
}

.symptom-group:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

.symptom-header {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
  margin-bottom: 8px;
}

.symptom-title {
  color: #434343;
  font-weight: 500;
}

.cell-text {
  display: inline-block;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.change-request-text {
  color: #262626;
  max-width: 720px;
  white-space: pre-wrap;
}

.change-request-meta {
  color: #8c8c8c;
  font-size: 12px;
  margin-top: 4px;
}

.persona-name {
  color: #1f1f1f;
  font-weight: 600;
  margin-bottom: 4px;
}

.persona-tone {
  color: #595959;
  font-size: 12px;
  line-height: 1.5;
  white-space: normal;
}

.persona-expanded {
  color: #595959;
  display: grid;
  gap: 6px;
  line-height: 1.6;
}

.pattern-expanded {
  color: #595959;
  display: grid;
  gap: 6px;
  line-height: 1.6;
}

.expanded-label {
  color: #262626;
  font-weight: 500;
}

.expression-text {
  white-space: normal;
}

.pattern-text {
  display: inline-block;
  max-width: 320px;
  white-space: normal;
}

.empty-state {
  color: #8c8c8c;
  padding: 32px 0;
  text-align: center;
}

@media (max-width: 1100px) {
  .layout-grid {
    grid-template-columns: 1fr;
  }
}
</style>
