<script setup lang="ts">
import type { AssetsApi } from '#/api/core/assets';

import { computed, onMounted, ref } from 'vue';

import { useUserStore } from '@vben/stores';

import {
  Alert,
  Button,
  Card,
  Descriptions,
  DescriptionsItem,
  Divider,
  Empty,
  InputNumber,
  List,
  ListItem,
  message,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  TypographyParagraph,
} from 'ant-design-vue';

import {
  extractReferenceElementsApi,
  getAssetSummariesApi,
} from '#/api/core/assets';

const loading = ref(false);
const assetKey = ref('yuanyue');
const limit = ref(10);
const persist = ref(false);
const summaries = ref<AssetsApi.AssetSummary[]>([]);
const result = ref<AssetsApi.ReferenceElementExtractResult | null>(null);
const selectedItem = ref<null | Record<string, any>>(null);
const userStore = useUserStore();

const currentOperator = computed(
  () =>
    userStore.userInfo?.realName ||
    userStore.userInfo?.username ||
    'maga-operator',
);

const assetKeyOptions = computed(() => {
  const referenceExampleKeys = [
    ...new Set(
      summaries.value
        .filter((item) => item.asset_type === 'reference_examples')
        .map((item) => item.asset_key),
    ),
  ];
  return referenceExampleKeys.length > 0 ? referenceExampleKeys : ['yuanyue'];
});

const items = computed(() => result.value?.items || []);

const columns = [
  {
    title: '例文',
    dataIndex: 'source_title',
    key: 'source_title',
    width: 220,
  },
  {
    title: '标题钩子',
    key: 'title_hook',
    width: 180,
  },
  {
    title: '叙事路径',
    key: 'narrative',
    width: 260,
  },
  {
    title: '可用场景',
    key: 'scene_atoms',
  },
  {
    title: '置信度',
    key: 'confidence',
    width: 100,
  },
];

async function loadAssetKeys() {
  try {
    summaries.value = await getAssetSummariesApi({
      asset_stage: 'production',
    });
  } catch (error) {
    console.error(error);
    message.warning('资产列表加载失败，可手动输入默认 asset_key');
  }
}

async function runExtraction() {
  loading.value = true;
  try {
    const data = await extractReferenceElementsApi({
      asset_key: assetKey.value,
      created_by: currentOperator.value,
      limit: limit.value,
      persist: persist.value,
    });
    result.value = data;
    selectedItem.value = data.items[0] || null;
    if (data.persisted_asset_id) {
      message.success(`已生成候选资产 v${data.persisted_asset_version}`);
    } else {
      message.success(`已预览 ${data.extracted_count} 条例文元素`);
    }
  } catch (error: any) {
    console.error(error);
    message.error(error?.message || '例文元素抽取失败');
  } finally {
    loading.value = false;
  }
}

function showItem(record: Record<string, any>) {
  selectedItem.value = record;
}

function valueList(value: any) {
  return Array.isArray(value) ? value.filter(Boolean) : [];
}

function painpointCategoryLabel(item: Record<string, any>) {
  const categories = valueList(item?.content_atoms?.painpoint_categories);
  return categories
    .map((category) => `${category.category_code} ${category.category_name}`)
    .join('、');
}

onMounted(() => {
  loadAssetKeys();
});
</script>

<template>
  <div class="reference-elements-page">
    <div class="page-header">
      <div>
        <h1>例文元素抽取</h1>
        <p>
          从 reference_examples 中提炼标题钩子、场景、痛点、叙事和安全约束。
        </p>
      </div>
      <Space>
        <Select
          v-model:value="assetKey"
          class="asset-select"
          :options="assetKeyOptions.map((value) => ({ label: value, value }))"
          show-search
        />
        <InputNumber v-model:value="limit" :min="1" :max="200" />
        <span class="switch-label">落候选资产</span>
        <Switch v-model:checked="persist" />
        <Button type="primary" :loading="loading" @click="runExtraction">
          开始抽取
        </Button>
      </Space>
    </div>

    <Alert
      class="hint"
      message="当前为规则版抽取，适合快速检查元素质量；后续可在同一接口接入模型精修。"
      type="info"
      show-icon
    />

    <div v-if="result" class="summary-grid">
      <Card>
        <Descriptions :column="4" size="small">
          <DescriptionsItem label="来源资产">
            #{{ result.source_asset_id }} / v{{ result.source_asset_version }}
          </DescriptionsItem>
          <DescriptionsItem label="来源条数">
            {{ result.source_item_count }}
          </DescriptionsItem>
          <DescriptionsItem label="抽取条数">
            {{ result.extracted_count }}
          </DescriptionsItem>
          <DescriptionsItem label="候选资产">
            <template v-if="result.persisted_asset_id">
              #{{ result.persisted_asset_id }} / v{{
                result.persisted_asset_version
              }}
            </template>
            <template v-else>仅预览</template>
          </DescriptionsItem>
        </Descriptions>
      </Card>
    </div>

    <div class="content-grid">
      <Card title="抽取结果" class="result-card">
        <Table
          v-if="items.length > 0"
          :columns="columns"
          :data-source="items"
          :pagination="{ pageSize: 8 }"
          :row-key="(record) => record.element_id"
          size="small"
          @row="(record) => ({ onClick: () => showItem(record) })"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'source_title'">
              <div class="source-title">
                {{ record.source_title || record.source_example_id }}
              </div>
            </template>
            <template v-else-if="column.key === 'title_hook'">
              <Space wrap>
                <Tag color="blue">{{ record.title_hook?.hook_type }}</Tag>
                <span>{{ record.title_hook?.title_formula }}</span>
              </Space>
            </template>
            <template v-else-if="column.key === 'narrative'">
              <div>{{ record.narrative?.story_arc }}</div>
              <div class="muted">{{ record.narrative?.ending_pattern }}</div>
            </template>
            <template v-else-if="column.key === 'scene_atoms'">
              <Space wrap>
                <Tag
                  v-for="scene in valueList(
                    record.content_atoms?.scene_atoms,
                  ).slice(0, 4)"
                  :key="scene"
                >
                  {{ scene }}
                </Tag>
              </Space>
            </template>
            <template v-else-if="column.key === 'confidence'">
              {{ Math.round((record.quality?.extract_confidence || 0) * 100) }}%
            </template>
          </template>
        </Table>
        <Empty v-else description="还没有抽取结果" />
      </Card>

      <Card title="元素详情" class="detail-card">
        <template v-if="selectedItem">
          <Descriptions :column="1" size="small" bordered>
            <DescriptionsItem label="标题钩子">
              <Space wrap>
                <Tag color="blue">{{ selectedItem.title_hook?.hook_type }}</Tag>
                <span>{{ selectedItem.title_hook?.rewrite_angle }}</span>
              </Space>
            </DescriptionsItem>
            <DescriptionsItem label="开头方式">
              {{ selectedItem.narrative?.opening_pattern }}
            </DescriptionsItem>
            <DescriptionsItem label="情绪曲线">
              <Space wrap>
                <Tag
                  v-for="emotion in valueList(
                    selectedItem.narrative?.emotion_curve,
                  )"
                  :key="emotion"
                  color="purple"
                >
                  {{ emotion }}
                </Tag>
              </Space>
            </DescriptionsItem>
            <DescriptionsItem label="痛点分类">
              {{ painpointCategoryLabel(selectedItem) || '未明显命中' }}
            </DescriptionsItem>
            <DescriptionsItem label="卖点植入">
              {{ selectedItem.writing_strategy?.selling_point_placement }}
            </DescriptionsItem>
            <DescriptionsItem label="证据方式">
              <Space wrap>
                <Tag
                  v-for="proof in valueList(
                    selectedItem.writing_strategy?.proof_styles,
                  )"
                  :key="proof"
                >
                  {{ proof }}
                </Tag>
              </Space>
            </DescriptionsItem>
          </Descriptions>

          <Divider />

          <List size="small" bordered>
            <ListItem>
              <strong>可用场景：</strong>
              <Space wrap>
                <Tag
                  v-for="scene in valueList(
                    selectedItem.content_atoms?.scene_atoms,
                  )"
                  :key="scene"
                >
                  {{ scene }}
                </Tag>
              </Space>
            </ListItem>
            <ListItem>
              <strong>人设信号：</strong>
              <Space wrap>
                <Tag
                  v-for="persona in valueList(
                    selectedItem.content_atoms?.persona_signals,
                  )"
                  :key="persona"
                  color="cyan"
                >
                  {{ persona }}
                </Tag>
              </Space>
            </ListItem>
            <ListItem>
              <strong>禁复用：</strong>
              <TypographyParagraph
                class="phrase-list"
                :ellipsis="{ rows: 3, expandable: true, symbol: '展开' }"
              >
                {{
                  valueList(selectedItem.safety?.avoid_copy_phrases).join(' / ')
                }}
              </TypographyParagraph>
            </ListItem>
            <ListItem>
              <strong>风险说明：</strong>
              <Space wrap>
                <Tag
                  v-for="risk in valueList(selectedItem.safety?.risk_notes)"
                  :key="risk"
                  color="orange"
                >
                  {{ risk }}
                </Tag>
              </Space>
            </ListItem>
          </List>
        </template>
        <Empty v-else description="点击左侧结果查看详情" />
      </Card>
    </div>
  </div>
</template>

<style scoped>
.reference-elements-page {
  padding: 20px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.page-header h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 650;
}

.page-header p {
  margin: 6px 0 0;
  color: #667085;
}

.asset-select {
  width: 180px;
}

.switch-label,
.muted {
  color: #667085;
}

.hint,
.summary-grid {
  margin-bottom: 16px;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(360px, 0.85fr);
  gap: 16px;
}

.result-card,
.detail-card {
  min-height: 560px;
}

.source-title {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.phrase-list {
  display: inline-block;
  max-width: 100%;
  margin-bottom: 0;
}

@media (max-width: 1080px) {
  .page-header {
    flex-direction: column;
  }

  .content-grid {
    grid-template-columns: 1fr;
  }
}
</style>
