<script setup lang="ts">
// @ts-nocheck
import type { AssetsApi } from '#/api/core/assets';
import type { UploadProps } from 'ant-design-vue';

import { computed, h, onMounted, ref } from 'vue';

import {
  CheckOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  HistoryOutlined,
  PlusOutlined,
  ReloadOutlined,
  RollbackOutlined,
  SaveOutlined,
  UploadOutlined,
} from '@ant-design/icons-vue';
import { useUserStore } from '@vben/stores';

import {
  Button,
  Col,
  Descriptions,
  DescriptionsItem,
  Empty,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Textarea,
  Tooltip,
  Upload,
} from 'ant-design-vue';

import {
  exportContentGenerationKeywordsApi,
  getContentGenerationKeywordsApi,
  getContentGenerationKeywordVersionsApi,
  importContentGenerationKeywordsApi,
  previewContentGenerationKeywordsApi,
  rollbackContentGenerationKeywordsApi,
  saveContentGenerationKeywordsApi,
} from '#/api/core/assets';

type Category = AssetsApi.SystemPromptKeywordCategory;
type SubKeyword = AssetsApi.SystemPromptSubKeyword;

const defaultAssetKey = 'default_content_generation_keywords';
const assetKey = ref(defaultAssetKey);
const displayName = ref('表达扩散语料');
const loading = ref(false);
const saving = ref(false);
const source = ref('fallback');
const versionNo = ref<null | number>(null);
const updateTime = ref<null | string>(null);
const categories = ref<Category[]>([]);
const selectedCategoryCode = ref('');
const userStore = useUserStore();
const versionModalVisible = ref(false);
const versionLoading = ref(false);
const versions = ref<AssetsApi.AssetSummary[]>([]);
const previewModalVisible = ref(false);
const previewLoading = ref(false);
const previewContentType = ref<'article' | 'comment'>('comment');
const previewRuleText = ref('这里是本次业务规则里的语料，用于预览表达扩散语料会如何进入最终 prompt。');
const previewResult = ref<AssetsApi.SystemPromptKeywordPreviewResult | null>(null);

const selectedCategory = computed(() =>
  categories.value.find(
    (item) => item.category_code === selectedCategoryCode.value,
  ),
);

const selectedCategoryKeywordOptions = computed(() =>
  (selectedCategory.value?.sub_keywords || [])
    .filter((item) => item.enabled !== false)
    .map((item) => ({
      label: item.keyword_name,
      value: item.keyword_code,
    })),
);

const categoryRows = computed(() =>
  [...categories.value].sort(
    (a, b) =>
      (a.sort_order || 0) - (b.sort_order || 0) ||
      a.category_code.localeCompare(b.category_code),
  ),
);

const activeCategoryCount = computed(
  () => categories.value.filter((item) => item.enabled).length,
);

const subKeywordCount = computed(() =>
  categories.value.reduce(
    (sum, item) => sum + (item.sub_keywords?.length || 0),
    0,
  ),
);

const corpusCount = computed(() =>
  categories.value.reduce(
    (sum, item) =>
      sum +
      (item.sub_keywords || []).reduce(
        (subSum, sub) => subSum + (sub.corpus?.length || 0),
        0,
      ),
    0,
  ),
);

const operator = computed(
  () =>
    userStore.userInfo?.realName ||
    userStore.userInfo?.username ||
    'maga-operator',
);

const categoryColumns: any[] = [
  { title: '顺序', dataIndex: 'sort_order', key: 'sort_order', width: 76 },
  { title: '类别', key: 'category', width: 220 },
  { title: '适用', key: 'content_types', width: 130 },
  { title: '子关键词', key: 'sub_keywords', width: 90 },
  { title: '状态', key: 'enabled', width: 86 },
  { fixed: 'right', title: '操作', key: 'action', width: 84 },
];

const subKeywordColumns: any[] = [
  { title: 'Code', dataIndex: 'keyword_code', key: 'keyword_code', width: 180 },
  { title: '名称', dataIndex: 'keyword_name', key: 'keyword_name', width: 170 },
  { title: '权重', dataIndex: 'weight', key: 'weight', width: 86 },
  { title: '状态', key: 'enabled', width: 78 },
  { title: '语料', key: 'corpus' },
  { fixed: 'right', title: '操作', key: 'action', width: 76 },
];

const versionColumns: any[] = [
  { title: '版本', dataIndex: 'version_no', key: 'version_no', width: 80 },
  { title: '状态', key: 'status', width: 90 },
  { title: '来源', dataIndex: 'source_name', key: 'source_name' },
  { title: '创建人', dataIndex: 'created_by', key: 'created_by', width: 120 },
  { title: '时间', dataIndex: 'create_time', key: 'create_time', width: 180 },
  { fixed: 'right', title: '操作', key: 'action', width: 96 },
];

function cloneCategories(input: Category[]) {
  return JSON.parse(JSON.stringify(input || [])) as Category[];
}

function normalizeCode(value: string) {
  return value
    .trim()
    .replaceAll(/\s+/g, '_')
    .replaceAll(/[^\w-]/g, '')
    .toLowerCase();
}

function nextCategoryCode() {
  let index = categories.value.length + 1;
  let code = `custom_category_${index}`;
  while (categories.value.some((item) => item.category_code === code)) {
    index += 1;
    code = `custom_category_${index}`;
  }
  return code;
}

function nextSubKeywordCode(category: Category) {
  let index = (category.sub_keywords || []).length + 1;
  let code = `keyword_${index}`;
  while ((category.sub_keywords || []).some((item) => item.keyword_code === code)) {
    index += 1;
    code = `keyword_${index}`;
  }
  return code;
}

async function loadKeywords() {
  loading.value = true;
  try {
    const asset = await getContentGenerationKeywordsApi({
      asset_key: assetKey.value,
    });
    displayName.value = asset.display_name || '表达扩散语料';
    source.value = asset.source;
    versionNo.value = asset.version_no ?? null;
    updateTime.value = asset.update_time || null;
    categories.value = cloneCategories(asset.content_json.categories || []);
    selectedCategoryCode.value =
      categories.value[0]?.category_code || selectedCategoryCode.value;
  } catch {
    message.error('获取表达扩散语料失败');
  } finally {
    loading.value = false;
  }
}

function addCategory() {
  const sortOrder =
    Math.max(0, ...categories.value.map((item) => item.sort_order || 0)) + 10;
  const category: Category = {
    applicable_content_types: ['article', 'comment'],
    category_code: nextCategoryCode(),
    category_name: '新关键词类别',
    description: '',
    enabled: true,
    required: false,
    selected_keyword_code: '',
    selection_mode: 'one',
    sort_order: sortOrder,
    sub_keywords: [],
  };
  categories.value.push(category);
  selectedCategoryCode.value = category.category_code;
}

function removeCategory(category: Category) {
  categories.value = categories.value.filter(
    (item) => item.category_code !== category.category_code,
  );
  selectedCategoryCode.value = categories.value[0]?.category_code || '';
}

function categoryRowProps(record: Category) {
  return {
    class:
      record.category_code === selectedCategoryCode.value
        ? 'category-row selected-row'
        : 'category-row',
    onClick: () => {
      selectedCategoryCode.value = record.category_code;
    },
  };
}

function updateSelectedCategoryCode(value: string) {
  const category = selectedCategory.value;
  if (!category) return;
  category.category_code = value;
  selectedCategoryCode.value = value;
}

function addSubKeyword() {
  const category = selectedCategory.value;
  if (!category) return;
  const subKeyword: SubKeyword = {
    corpus: [''],
    enabled: true,
    keyword_code: nextSubKeywordCode(category),
    keyword_name: '新子关键词',
    weight: 1,
  };
  category.sub_keywords = [...(category.sub_keywords || []), subKeyword];
}

function removeSubKeyword(record: SubKeyword) {
  const category = selectedCategory.value;
  if (!category) return;
  category.sub_keywords = (category.sub_keywords || []).filter(
    (item) => item !== record,
  );
}

function addCorpus(record: SubKeyword) {
  record.corpus = [...(record.corpus || []), ''];
}

function removeCorpus(record: SubKeyword, index: number) {
  record.corpus = (record.corpus || []).filter((_, itemIndex) => itemIndex !== index);
}

function normalizeBeforeSave() {
  const seenCategories = new Set<string>();
  for (const category of categories.value) {
    category.category_code = normalizeCode(category.category_code);
    category.category_name = category.category_name?.trim();
    category.description = category.description?.trim() || '';
    category.selection_mode = category.selection_mode || 'one';
    category.selected_keyword_code =
      category.selection_mode === 'fixed'
        ? category.selected_keyword_code?.trim() || ''
        : '';
    category.applicable_content_types =
      category.applicable_content_types?.length > 0
        ? category.applicable_content_types
        : ['article', 'comment'];
    if (!category.category_code || !category.category_name) {
      throw new Error('关键词类别需要填写 Code 和名称');
    }
    if (seenCategories.has(category.category_code)) {
      throw new Error(`类别 Code 重复：${category.category_code}`);
    }
    seenCategories.add(category.category_code);
    const seenKeywords = new Set<string>();
    for (const sub of category.sub_keywords || []) {
      sub.keyword_code = normalizeCode(sub.keyword_code);
      sub.keyword_name = sub.keyword_name?.trim();
      sub.weight = Number(sub.weight || 1);
      sub.corpus = (sub.corpus || []).map((item) => item.trim()).filter(Boolean);
      if (!sub.keyword_code || !sub.keyword_name) {
        throw new Error(`类别「${category.category_name}」下的子关键词需要填写 Code 和名称`);
      }
      if (seenKeywords.has(sub.keyword_code)) {
        throw new Error(`类别「${category.category_name}」下子关键词 Code 重复：${sub.keyword_code}`);
      }
      if (sub.enabled && sub.corpus.length === 0) {
        throw new Error(`子关键词「${sub.keyword_name}」至少需要一条语料`);
      }
      seenKeywords.add(sub.keyword_code);
    }
    if (
      category.enabled &&
      !(category.sub_keywords || []).some((item) => item.enabled)
    ) {
      throw new Error(`启用的类别「${category.category_name}」至少需要一个启用的子关键词`);
    }
    if (category.enabled && category.selection_mode === 'fixed') {
      const fixedKeyword = (category.sub_keywords || []).find(
        (item) => item.keyword_code === category.selected_keyword_code && item.enabled !== false,
      );
      if (!fixedKeyword) {
        throw new Error(`类别「${category.category_name}」需要选择一个启用的固定子关键词`);
      }
    }
  }
}

async function saveKeywords() {
  saving.value = true;
  try {
    normalizeBeforeSave();
    const asset = await saveContentGenerationKeywordsApi({
      asset_key: assetKey.value,
      categories: categories.value,
      created_by: operator.value,
      display_name: displayName.value,
      selection_policy: {
        default_mode: 'one_per_enabled_category',
      },
    });
    message.success(`已保存为版本 ${asset.version_no}`);
    await loadKeywords();
  } catch (error: any) {
    message.error(error?.message || '保存表达扩散语料失败');
  } finally {
    saving.value = false;
  }
}

async function loadVersions() {
  versionLoading.value = true;
  try {
    versions.value = await getContentGenerationKeywordVersionsApi({
      asset_key: assetKey.value,
      limit: 50,
    });
  } catch {
    message.error('获取版本列表失败');
  } finally {
    versionLoading.value = false;
  }
}

async function openVersionModal() {
  versionModalVisible.value = true;
  await loadVersions();
}

async function rollbackVersion(record: AssetsApi.AssetSummary) {
  versionLoading.value = true;
  try {
    const asset = await rollbackContentGenerationKeywordsApi({
      asset_key: assetKey.value,
      created_by: operator.value,
      version_no: record.version_no,
    });
    message.success(`已回滚并保存为版本 ${asset.version_no}`);
    await loadKeywords();
    await loadVersions();
  } catch (error: any) {
    message.error(error?.message || '回滚失败');
  } finally {
    versionLoading.value = false;
  }
}

function downloadCsv(filename: string, text: string) {
  const blob = new Blob([`\uFEFF${text}`], {
    type: 'text/csv;charset=utf-8',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

async function exportKeywords() {
  try {
    const result = await exportContentGenerationKeywordsApi({
      asset_key: assetKey.value,
    });
    downloadCsv(result.filename, result.csv_text);
  } catch {
    message.error('导出失败');
  }
}

async function importKeywordsFile(file: File) {
  saving.value = true;
  try {
    const result = await importContentGenerationKeywordsApi({
      asset_key: assetKey.value,
      created_by: operator.value,
      display_name: displayName.value,
      file,
    });
    message.success(`导入成功：${result.summary_json?.category_count || 0} 个类别`);
    await loadKeywords();
  } catch (error: any) {
    message.error(error?.message || '导入失败');
  } finally {
    saving.value = false;
  }
}

const beforeUploadKeywordFile: UploadProps['beforeUpload'] = (file) => {
  void importKeywordsFile(file as File);
  return false;
};

async function runPreview() {
  previewLoading.value = true;
  try {
    normalizeBeforeSave();
    previewResult.value = await previewContentGenerationKeywordsApi({
      asset_key: assetKey.value,
      business_rule: {
        rule_type: 'business_rule',
        business_rule: '预览业务规则',
        corpus: previewRuleText.value,
      },
      categories: categories.value,
      content_type: previewContentType.value,
      item_no: 1,
      output_fields:
        previewContentType.value === 'comment' ? ['comment'] : ['title', 'body'],
      selection_policy: {
        default_mode: 'one_per_enabled_category',
      },
    });
  } catch (error: any) {
    message.error(error?.message || '预览失败');
  } finally {
    previewLoading.value = false;
  }
}

async function openPreviewModal() {
  previewModalVisible.value = true;
  await runPreview();
}

onMounted(loadKeywords);
</script>

<template>
  <div class="system-prompt-keywords-page p-4">
    <div class="page-toolbar">
      <Space wrap>
        <Input v-model:value="assetKey" class="asset-key-input" />
        <Input v-model:value="displayName" class="display-name-input" />
        <Tooltip title="刷新">
          <Button :icon="h(ReloadOutlined)" :loading="loading" @click="loadKeywords" />
        </Tooltip>
        <Upload
          accept=".csv,.xlsx"
          :before-upload="beforeUploadKeywordFile"
          :show-upload-list="false"
        >
          <Button :icon="h(UploadOutlined)" :loading="saving">
            导入
          </Button>
        </Upload>
        <Button :icon="h(DownloadOutlined)" @click="exportKeywords">
          导出
        </Button>
        <Button :icon="h(HistoryOutlined)" @click="openVersionModal">
          版本
        </Button>
        <Button :icon="h(EyeOutlined)" @click="openPreviewModal">
          预览 Prompt
        </Button>
        <Button
          type="primary"
          :icon="h(SaveOutlined)"
          :loading="saving"
          @click="saveKeywords"
        >
          保存新版本
        </Button>
      </Space>
    </div>

    <Descriptions bordered size="small" class="summary-strip">
      <DescriptionsItem label="来源">
        <Tag :color="source === 'fallback' ? 'orange' : 'green'">
          {{ source === 'fallback' ? '默认种子' : '资产版本' }}
        </Tag>
      </DescriptionsItem>
      <DescriptionsItem label="版本">{{ versionNo || '-' }}</DescriptionsItem>
      <DescriptionsItem label="启用类别">{{ activeCategoryCount }}</DescriptionsItem>
      <DescriptionsItem label="子关键词">{{ subKeywordCount }}</DescriptionsItem>
      <DescriptionsItem label="语料">{{ corpusCount }}</DescriptionsItem>
      <DescriptionsItem label="更新时间">{{ updateTime || '-' }}</DescriptionsItem>
    </Descriptions>

    <Row :gutter="16" class="main-grid">
      <Col :lg="10" :xs="24">
        <div class="panel">
          <div class="panel-toolbar">
            <span class="panel-title">关键词类别</span>
            <Button size="small" :icon="h(PlusOutlined)" @click="addCategory">
              新增类别
            </Button>
          </div>
          <Table
            row-key="category_code"
            size="small"
            :columns="categoryColumns"
            :custom-row="categoryRowProps"
            :data-source="categoryRows"
            :loading="loading"
            :pagination="false"
            :scroll="{ x: 760 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'category'">
                <div class="table-main">{{ record.category_name }}</div>
                <div class="table-sub">{{ record.category_code }}</div>
              </template>
              <template v-else-if="column.key === 'content_types'">
                <Space size="small" wrap>
                  <Tag v-for="item in record.applicable_content_types" :key="item">
                    {{ item }}
                  </Tag>
                </Space>
              </template>
              <template v-else-if="column.key === 'sub_keywords'">
                {{ record.sub_keywords?.length || 0 }}
              </template>
              <template v-else-if="column.key === 'enabled'">
                <Tag :color="record.enabled ? 'green' : 'default'">
                  {{ record.enabled ? '启用' : '停用' }}
                </Tag>
              </template>
              <template v-else-if="column.key === 'action'">
                <Popconfirm title="删除这个类别？" @confirm="removeCategory(record)">
                  <Button size="small" danger :icon="h(DeleteOutlined)" />
                </Popconfirm>
              </template>
            </template>
          </Table>
        </div>
      </Col>

      <Col :lg="14" :xs="24">
        <div v-if="selectedCategory" class="panel">
          <div class="panel-toolbar">
            <span class="panel-title">类别配置</span>
            <Space>
              <Switch
                v-model:checked="selectedCategory.enabled"
                checked-children="启用"
                un-checked-children="停用"
              />
              <Button size="small" :icon="h(PlusOutlined)" @click="addSubKeyword">
                新增子关键词
              </Button>
            </Space>
          </div>

          <Form layout="vertical" class="category-form">
            <Row :gutter="12">
              <Col :lg="8" :xs="24">
                <FormItem label="类别 Code">
                  <Input
                    :value="selectedCategory.category_code"
                    @update:value="updateSelectedCategoryCode"
                  />
                </FormItem>
              </Col>
              <Col :lg="8" :xs="24">
                <FormItem label="类别名称">
                  <Input v-model:value="selectedCategory.category_name" />
                </FormItem>
              </Col>
              <Col :lg="8" :xs="24">
                <FormItem label="顺序">
                  <InputNumber
                    v-model:value="selectedCategory.sort_order"
                    class="full-width"
                    :min="0"
                  />
                </FormItem>
              </Col>
              <Col :lg="8" :xs="24">
                <FormItem label="适用内容">
                  <Select
                    v-model:value="selectedCategory.applicable_content_types"
                    mode="multiple"
                    :options="[
                      { label: '文章', value: 'article' },
                      { label: '评论', value: 'comment' },
                    ]"
                  />
                </FormItem>
              </Col>
              <Col :lg="8" :xs="24">
                <FormItem label="选择模式">
                  <Select
                    v-model:value="selectedCategory.selection_mode"
                    :options="[
                      { label: '自动轮换', value: 'one' },
                      { label: '固定选择', value: 'fixed' },
                    ]"
                  />
                </FormItem>
              </Col>
              <Col v-if="selectedCategory.selection_mode === 'fixed'" :lg="8" :xs="24">
                <FormItem label="固定子关键词">
                  <Select
                    v-model:value="selectedCategory.selected_keyword_code"
                    :options="selectedCategoryKeywordOptions"
                    placeholder="选择一个子关键词"
                  />
                </FormItem>
              </Col>
              <Col :lg="8" :xs="24">
                <FormItem label="必选">
                  <Switch
                    v-model:checked="selectedCategory.required"
                    checked-children="是"
                    un-checked-children="否"
                  />
                </FormItem>
              </Col>
              <Col :span="24">
                <FormItem label="说明">
                  <Input v-model:value="selectedCategory.description" />
                </FormItem>
              </Col>
            </Row>
          </Form>

          <Table
            row-key="keyword_code"
            size="small"
            :columns="subKeywordColumns"
            :data-source="selectedCategory.sub_keywords"
            :pagination="false"
            :scroll="{ x: 960 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'keyword_code'">
                <Input v-model:value="record.keyword_code" />
              </template>
              <template v-else-if="column.key === 'keyword_name'">
                <Input v-model:value="record.keyword_name" />
              </template>
              <template v-else-if="column.key === 'weight'">
                <InputNumber v-model:value="record.weight" class="weight-input" :min="1" />
              </template>
              <template v-else-if="column.key === 'enabled'">
                <Switch v-model:checked="record.enabled" size="small" />
              </template>
              <template v-else-if="column.key === 'corpus'">
                <div class="corpus-list">
                  <div
                    v-for="(_, index) in record.corpus"
                    :key="`${record.keyword_code}-${index}`"
                    class="corpus-row"
                  >
                    <Textarea
                      v-model:value="record.corpus[index]"
                      :auto-size="{ minRows: 1, maxRows: 4 }"
                    />
                    <Button
                      size="small"
                      danger
                      :icon="h(DeleteOutlined)"
                      @click="removeCorpus(record, index)"
                    />
                  </div>
                  <Button size="small" :icon="h(PlusOutlined)" @click="addCorpus(record)">
                    添加语料
                  </Button>
                </div>
              </template>
              <template v-else-if="column.key === 'action'">
                <Popconfirm title="删除这个子关键词？" @confirm="removeSubKeyword(record)">
                  <Button size="small" danger :icon="h(DeleteOutlined)" />
                </Popconfirm>
              </template>
            </template>
          </Table>
        </div>

        <div v-else class="empty-panel">
          <Empty description="暂无关键词类别" />
          <Button type="primary" :icon="h(PlusOutlined)" @click="addCategory">
            新增类别
          </Button>
        </div>
      </Col>
    </Row>

    <div class="save-bar">
      <Space>
        <Tag color="blue">
          <CheckOutlined />
          生成时会按启用类别自动选取子关键词
        </Tag>
        <Button type="primary" :icon="h(SaveOutlined)" :loading="saving" @click="saveKeywords">
          保存新版本
        </Button>
      </Space>
    </div>

    <Modal
      v-model:open="versionModalVisible"
      title="版本管理"
      width="840px"
      :footer="null"
      @cancel="versionModalVisible = false"
    >
      <Table
        row-key="id"
        size="small"
        :columns="versionColumns"
        :data-source="versions"
        :loading="versionLoading"
        :pagination="false"
        :scroll="{ x: 760 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <Tag :color="record.status === 'active' ? 'green' : 'default'">
              {{ record.status === 'active' ? '当前' : '归档' }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'action'">
            <Popconfirm
              title="将这个版本复制为新的当前版本？"
              @confirm="rollbackVersion(record)"
            >
              <Button
                size="small"
                :disabled="record.status === 'active'"
                :icon="h(RollbackOutlined)"
              >
                回滚
              </Button>
            </Popconfirm>
          </template>
        </template>
      </Table>
    </Modal>

    <Modal
      v-model:open="previewModalVisible"
      title="最终 Prompt 预览"
      width="920px"
      :confirm-loading="previewLoading"
      ok-text="重新预览"
      cancel-text="关闭"
      @ok="runPreview"
    >
      <Space direction="vertical" class="preview-panel" size="middle">
        <Space>
          <Select
            v-model:value="previewContentType"
            style="width: 120px"
            :options="[
              { label: '评论', value: 'comment' },
              { label: '文章', value: 'article' },
            ]"
          />
          <Button :loading="previewLoading" :icon="h(EyeOutlined)" @click="runPreview">
            生成预览
          </Button>
        </Space>
        <Textarea
          v-model:value="previewRuleText"
          :auto-size="{ minRows: 3, maxRows: 6 }"
        />
        <div v-if="previewResult" class="preview-keywords">
          <Tag
            v-for="item in previewResult.selected_keywords"
            :key="`${item.category_code}-${item.keyword_code}`"
            color="blue"
          >
            {{ item.category_name }} / {{ item.keyword_name }}
          </Tag>
        </div>
        <Textarea
          :value="previewResult?.rendered_prompt || ''"
          readonly
          :auto-size="{ minRows: 14, maxRows: 24 }"
        />
      </Space>
    </Modal>
  </div>
</template>

<style scoped>
.system-prompt-keywords-page {
  background: #f6f7f9;
  min-height: 100%;
}

.page-toolbar,
.panel,
.empty-panel,
.save-bar {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.page-toolbar {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
  padding: 12px;
}

.asset-key-input {
  width: 280px;
}

.display-name-input {
  width: 220px;
}

.summary-strip {
  margin-bottom: 12px;
}

.main-grid {
  align-items: flex-start;
}

.panel {
  padding: 12px;
}

.panel-toolbar {
  align-items: center;
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
}

.panel-title {
  color: #111827;
  font-size: 15px;
  font-weight: 600;
}

.table-main {
  color: #111827;
  font-weight: 600;
}

.table-sub {
  color: #6b7280;
  font-size: 12px;
  margin-top: 2px;
}

.category-form {
  margin-bottom: 12px;
}

.full-width {
  width: 100%;
}

.weight-input {
  width: 64px;
}

.corpus-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.corpus-row {
  align-items: flex-start;
  display: grid;
  gap: 8px;
  grid-template-columns: minmax(220px, 1fr) 32px;
}

.preview-panel {
  width: 100%;
}

.preview-keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.empty-panel {
  align-items: center;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 320px;
  padding: 48px 12px;
}

.save-bar {
  bottom: 0;
  margin-top: 12px;
  padding: 10px 12px;
  position: sticky;
  text-align: right;
}

:deep(.selected-row td) {
  background: #e6f4ff !important;
}

:deep(.category-row) {
  cursor: pointer;
}

@media (max-width: 768px) {
  .page-toolbar {
    display: block;
  }

  .asset-key-input,
  .display-name-input {
    width: 100%;
  }

  .save-bar {
    text-align: left;
  }
}
</style>
