<script setup lang="ts">
import type { TemplateVariableCorpusApi } from '#/api/core/template-variable-corpus';

import { computed, onMounted, ref, watch } from 'vue';

import { useUserStore } from '@vben/stores';

import {
  EditOutlined,
  FileTextOutlined,
  InboxOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue';
import {
  Button,
  Card,
  Empty,
  Input,
  List,
  ListItem,
  message,
  Modal,
  Popconfirm,
  RadioGroup,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import {
  archiveTemplateVariableCorpusApi,
  createTemplateVariableCorpusApi,
  getTemplateVariablesApi,
  listTemplateVariableCorpusApi,
  previewTemplatePromptApi,
  updateTemplateVariableCorpusApi,
} from '#/api/core/template-variable-corpus';
import { logger } from '#/utils/logger';

type CorpusStatus = TemplateVariableCorpusApi.CorpusStatus;
type CorpusItem = TemplateVariableCorpusApi.CorpusItem;
type TemplateVariable = TemplateVariableCorpusApi.TemplateVariable;

const tenantCode = ref('default');
const variables = ref<TemplateVariable[]>([]);
const selectedVariable = ref('');
const corpusItems = ref<CorpusItem[]>([]);
const selectedItemId = ref('');
const selectedItemIds = ref<Record<string, string>>({});
const preview = ref<null | TemplateVariableCorpusApi.PromptPreviewResponse>(
  null,
);
const loadingVariables = ref(false);
const loadingCorpus = ref(false);
const saving = ref(false);
const previewLoading = ref(false);
const keyword = ref('');
const statusFilter = ref<'all' | CorpusStatus>('all');
const modalVisible = ref(false);
const isEditing = ref(false);
const userStore = useUserStore();

const form = ref<{
  id?: string;
  markdown: string;
  name: string;
  source: string;
  status: CorpusStatus;
  tagsText: string;
}>({
  name: '',
  markdown: '',
  tagsText: '',
  source: '',
  status: 'active',
});

const selectedVariableMeta = computed(() =>
  variables.value.find((item) => item.name === selectedVariable.value),
);

const currentOperator = computed(
  () =>
    userStore.userInfo?.realName ||
    userStore.userInfo?.username ||
    'maga-operator',
);

const statusOptions = [
  { label: '全部', value: 'all' },
  { label: '启用', value: 'active' },
  { label: '草稿', value: 'draft' },
  { label: '归档', value: 'archived' },
];

const formStatusOptions = [
  { label: '启用', value: 'active' },
  { label: '草稿', value: 'draft' },
];

async function fetchVariables() {
  loadingVariables.value = true;
  try {
    const data = await getTemplateVariablesApi({
      tenant_code: tenantCode.value,
    });
    variables.value = data.variables;
    if (!selectedVariable.value && data.variables.length > 0) {
      selectedVariable.value = data.variables[0]?.name || '';
    }
  } catch (error) {
    logger.error('获取模板变量失败:', error);
    message.error('模板变量加载失败');
  } finally {
    loadingVariables.value = false;
  }
}

async function fetchCorpus() {
  if (!selectedVariable.value) return;
  loadingCorpus.value = true;
  try {
    const data = await listTemplateVariableCorpusApi({
      tenant_code: tenantCode.value,
      variable_name: selectedVariable.value,
      keyword: keyword.value || undefined,
      status: statusFilter.value === 'all' ? undefined : statusFilter.value,
      page: 1,
      page_size: 100,
    });
    corpusItems.value = data.items;
    const rememberedId = selectedItemIds.value[selectedVariable.value];
    const nextSelected =
      data.items.find((item) => item.id === rememberedId) ||
      data.items.find((item) => item.status === 'active') ||
      data.items[0];
    selectedItemId.value = nextSelected?.id || '';
    if (nextSelected) {
      selectedItemIds.value[selectedVariable.value] = nextSelected.id;
    }
  } catch (error) {
    logger.error('获取变量语料失败:', error);
    message.error('语料加载失败');
  } finally {
    loadingCorpus.value = false;
  }
}

async function refreshAll() {
  await fetchVariables();
  await fetchCorpus();
  await renderPreview();
}

function selectVariable(variableName: string) {
  selectedVariable.value = variableName;
}

function selectCorpusItem(item: CorpusItem) {
  selectedItemId.value = item.id;
  selectedItemIds.value[item.variable_name] = item.id;
  renderPreview();
}

function openCreateModal() {
  isEditing.value = false;
  form.value = {
    name: '',
    markdown: '',
    tagsText: '',
    source: 'manual',
    status: 'active',
  };
  modalVisible.value = true;
}

function openEditModal(item: CorpusItem) {
  isEditing.value = true;
  form.value = {
    id: item.id,
    name: item.name,
    markdown: item.markdown,
    tagsText: item.tags.join(', '),
    source: item.source || '',
    status: item.status === 'archived' ? 'draft' : item.status,
  };
  modalVisible.value = true;
}

function parseTags(text: string) {
  return text
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

async function saveCorpus() {
  if (!selectedVariable.value) {
    message.warning('请先选择模板变量');
    return;
  }
  if (!form.value.name.trim() || !form.value.markdown.trim()) {
    message.warning('标题和 Markdown 语料不能为空');
    return;
  }

  saving.value = true;
  try {
    if (isEditing.value && form.value.id) {
      const item = await updateTemplateVariableCorpusApi(form.value.id, {
        name: form.value.name.trim(),
        markdown: form.value.markdown,
        tags: parseTags(form.value.tagsText),
        source: form.value.source || undefined,
        status: form.value.status,
        updated_by: currentOperator.value,
      });
      selectedItemIds.value[item.variable_name] = item.id;
      message.success('语料已更新');
    } else {
      const item = await createTemplateVariableCorpusApi({
        tenant_code: tenantCode.value,
        variable_name: selectedVariable.value,
        name: form.value.name.trim(),
        markdown: form.value.markdown,
        tags: parseTags(form.value.tagsText),
        source: form.value.source || undefined,
        status: form.value.status,
        created_by: currentOperator.value,
      });
      selectedItemIds.value[item.variable_name] = item.id;
      message.success('语料已创建');
    }
    modalVisible.value = false;
    await fetchVariables();
    await fetchCorpus();
    await renderPreview();
  } catch (error) {
    logger.error('保存变量语料失败:', error);
    message.error('保存失败');
  } finally {
    saving.value = false;
  }
}

async function archiveCorpus(item: CorpusItem) {
  try {
    await archiveTemplateVariableCorpusApi(item.id);
    message.success('语料已归档');
    if (selectedItemIds.value[item.variable_name] === item.id) {
      delete selectedItemIds.value[item.variable_name];
    }
    await fetchVariables();
    await fetchCorpus();
    await renderPreview();
  } catch (error) {
    logger.error('归档变量语料失败:', error);
    message.error('归档失败');
  }
}

async function renderPreview() {
  previewLoading.value = true;
  try {
    preview.value = await previewTemplatePromptApi({
      tenant_code: tenantCode.value,
      selected_item_ids: selectedItemIds.value,
      fill_mode: 'selected_or_first',
      missing_policy: 'keep_placeholder',
    });
  } catch (error) {
    logger.error('Prompt 预览失败:', error);
    preview.value = null;
  } finally {
    previewLoading.value = false;
  }
}

function statusColor(status: CorpusStatus) {
  if (status === 'active') return 'green';
  if (status === 'draft') return 'gold';
  return 'default';
}

function statusLabel(status: CorpusStatus) {
  if (status === 'active') return '启用';
  if (status === 'draft') return '草稿';
  return '归档';
}

watch(selectedVariable, async () => {
  await fetchCorpus();
  await renderPreview();
});

watch([keyword, statusFilter], () => {
  fetchCorpus();
});

onMounted(() => {
  refreshAll();
});
</script>

<template>
  <div class="template-variable-corpus-page">
    <div class="page-header">
      <div>
        <h1>关键词语料</h1>
        <p>按生文提示词变量管理普通文本 / Markdown 语料，并预览最终 Prompt。</p>
      </div>
      <Space>
        <Tooltip title="刷新">
          <Button :loading="loadingVariables" @click="refreshAll">
            <template #icon><ReloadOutlined /></template>
          </Button>
        </Tooltip>
        <Button type="primary" @click="openCreateModal">
          <template #icon><PlusOutlined /></template>
          新增语料
        </Button>
      </Space>
    </div>

    <div class="workspace-grid">
      <Card class="variable-panel" title="模板变量">
        <Spin :spinning="loadingVariables">
          <div class="variable-list">
            <button
              v-for="variable in variables"
              :key="variable.name"
              class="variable-item"
              :class="{ active: variable.name === selectedVariable }"
              @click="selectVariable(variable.name)"
            >
              <span>{{ variable.name }}</span>
              <Tag color="blue">{{ variable.active_count }}</Tag>
            </button>
          </div>
        </Spin>
      </Card>

      <Card class="corpus-panel">
        <template #title>
          <div class="panel-title">
            <span>{{ selectedVariable || '变量语料' }}</span>
            <Tag v-if="selectedVariableMeta">
              {{ selectedVariableMeta.corpus_count }} 条
            </Tag>
          </div>
        </template>
        <template #extra>
          <Space>
            <Input
              v-model:value="keyword"
              class="search-input"
              allow-clear
              placeholder="搜索语料"
            >
              <template #prefix><SearchOutlined /></template>
            </Input>
            <Select
              v-model:value="statusFilter"
              class="status-select"
              :options="statusOptions"
            />
          </Space>
        </template>

        <Spin :spinning="loadingCorpus">
          <List
            v-if="corpusItems.length > 0"
            :data-source="corpusItems"
            item-layout="vertical"
          >
            <template #renderItem="{ item }">
              <ListItem
                class="corpus-item"
                :class="{ selected: item.id === selectedItemId }"
                @click="selectCorpusItem(item)"
              >
                <div class="corpus-item-header">
                  <div>
                    <div class="corpus-name">{{ item.name }}</div>
                    <Space wrap class="corpus-tags">
                      <Tag :color="statusColor(item.status)">
                        {{ statusLabel(item.status) }}
                      </Tag>
                      <Tag v-for="tag in item.tags" :key="tag">{{ tag }}</Tag>
                    </Space>
                  </div>
                  <Space>
                    <Tooltip title="编辑">
                      <Button size="small" @click.stop="openEditModal(item)">
                        <template #icon><EditOutlined /></template>
                      </Button>
                    </Tooltip>
                    <Popconfirm
                      title="确认归档这条语料？"
                      ok-text="归档"
                      cancel-text="取消"
                      @confirm="archiveCorpus(item)"
                    >
                      <Tooltip title="归档">
                        <Button
                          size="small"
                          danger
                          :disabled="item.status === 'archived'"
                          @click.stop
                        >
                          <template #icon><InboxOutlined /></template>
                        </Button>
                      </Tooltip>
                    </Popconfirm>
                  </Space>
                </div>
                <pre class="markdown-preview">{{ item.markdown }}</pre>
              </ListItem>
            </template>
          </List>
          <Empty v-else description="这个变量还没有语料" />
        </Spin>
      </Card>

      <Card class="preview-panel">
        <template #title>
          <div class="panel-title">
            <span>Prompt 预览</span>
            <Tag v-if="preview?.missing_variables.length" color="gold">
              缺 {{ preview.missing_variables.length }}
            </Tag>
          </div>
        </template>
        <template #extra>
          <Tooltip title="重新生成预览">
            <Button :loading="previewLoading" @click="renderPreview">
              <template #icon><FileTextOutlined /></template>
            </Button>
          </Tooltip>
        </template>
        <Spin :spinning="previewLoading">
          <pre v-if="preview" class="prompt-preview">{{
            preview.rendered_prompt
          }}</pre>
          <Empty v-else description="暂无预览" />
        </Spin>
      </Card>
    </div>

    <Modal
      v-model:open="modalVisible"
      :title="isEditing ? '编辑变量语料' : '新增变量语料'"
      width="760px"
      :confirm-loading="saving"
      @ok="saveCorpus"
    >
      <div class="modal-form">
        <label>变量</label>
        <Input :value="selectedVariable" disabled />
        <label>标题</label>
        <Input v-model:value="form.name" placeholder="例如：转奶期便便观察" />
        <label>Markdown 语料</label>
        <Input.TextArea
          v-model:value="form.markdown"
          :rows="10"
          placeholder="直接粘贴普通文本或 Markdown"
        />
        <label>标签</label>
        <Input v-model:value="form.tagsText" placeholder="多个标签用逗号分隔" />
        <label>来源</label>
        <Input
          v-model:value="form.source"
          placeholder="manual / reference_example / extracted"
        />
        <label>状态</label>
        <RadioGroup v-model:value="form.status" :options="formStatusOptions" />
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.template-variable-corpus-page {
  min-height: 100%;
  padding: 24px;
  background: #f6f7f9;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.page-header h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 650;
  color: #172033;
}

.page-header p {
  margin: 6px 0 0;
  color: #657086;
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(180px, 240px) minmax(420px, 1fr) minmax(
      360px,
      0.9fr
    );
  gap: 16px;
  align-items: start;
}

.variable-panel,
.corpus-panel,
.preview-panel {
  border-radius: 8px;
}

.variable-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.variable-item {
  display: flex;
  width: 100%;
  min-height: 38px;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: #30394d;
  cursor: pointer;
}

.variable-item:hover,
.variable-item.active {
  border-color: #91caff;
  background: #e6f4ff;
  color: #0958d9;
}

.panel-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.search-input {
  width: 180px;
}

.status-select {
  width: 96px;
}

.corpus-item {
  padding: 14px;
  border: 1px solid #eef0f4;
  border-radius: 8px;
  margin-bottom: 10px;
  cursor: pointer;
}

.corpus-item.selected {
  border-color: #4096ff;
  background: #f0f7ff;
}

.corpus-item-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.corpus-name {
  margin-bottom: 6px;
  font-weight: 600;
  color: #172033;
}

.corpus-tags {
  margin-bottom: 8px;
}

.markdown-preview,
.prompt-preview {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-family:
    ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono',
    'Courier New', monospace;
  font-size: 13px;
  line-height: 1.65;
  color: #2d3748;
}

.markdown-preview {
  max-height: 150px;
  overflow: auto;
  padding: 10px;
  border-radius: 6px;
  background: #fff;
}

.prompt-preview {
  max-height: calc(100vh - 230px);
  overflow: auto;
  padding: 12px;
  border: 1px solid #eef0f4;
  border-radius: 6px;
  background: #fbfcfe;
}

.modal-form {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 12px;
  align-items: center;
}

.modal-form label {
  color: #4f5b70;
  font-weight: 500;
}

@media (max-width: 1180px) {
  .workspace-grid {
    grid-template-columns: 220px minmax(0, 1fr);
  }

  .preview-panel {
    grid-column: 1 / -1;
  }
}

@media (max-width: 760px) {
  .template-variable-corpus-page {
    padding: 16px;
  }

  .page-header {
    flex-direction: column;
  }

  .workspace-grid {
    grid-template-columns: 1fr;
  }

  .modal-form {
    grid-template-columns: 1fr;
  }
}
</style>
