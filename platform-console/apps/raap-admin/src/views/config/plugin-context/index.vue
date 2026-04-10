<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import { useDebounceFn } from '@vueuse/core';
import {
  AutoComplete,
  Button,
  Card,
  Descriptions,
  DescriptionsItem,
  Drawer,
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Space,
  Table,
  Tag,
  Textarea,
  Timeline,
  TimelineItem,
  Tooltip,
} from 'ant-design-vue';

import { checkCanModifyApi } from '#/api/core/publish';
import { requestClient } from '#/api/request';
import MonacoEditor from '#/components/MonacoEditor.vue';
import { use_page_persistence } from '#/utils/page_persistence';

// 快照接口定义
interface Snapshot {
  id: number;
  entity_type: string;
  entity_id: null | number;
  entity_code: string;
  snapshot_type: string;
  content: Record<string, any>;
  version: number;
  description: null | string;
  create_time: string;
  created_by: null | string;
}

interface PluginContext {
  id: number;
  variable_name: null | string;
  context_name: null | string;
  context: null | string;
  default_keywords: null | Record<string, any>;
  default_corpus: null | Record<string, any>;
  remark: null | string;
  publish_status: 'DRAFT' | 'PUBLISHED';
  publish_time: null | string;
  publish_by: null | string;
  create_time: string;
  update_time: string;
  created_by: null | string;
  updated_by: null | string;
}

// 获取所有 Plugin 的变量列表
interface Plugin {
  id: number;
  plugin_code: string;
  plugin_name: string;
  variable_list: null | string[];
}

const route = useRoute();

const loading = ref(false);
const dataSource = ref<PluginContext[]>([]);
const searchText = ref('');
const modalVisible = ref(false);
const editingContext = ref<null | PluginContext>(null);
const isSubmitting = ref(false);

// 分类筛选条件
const filterVariableName = ref('');
const filterContextName = ref('');
const filterContextContent = ref('');

type PersistedPluginContextPageStateV1 = {
  current_entity_code: string;
  detail_drawer_visible: boolean;
  editing_context_id: null | number;
  // 筛选条件缓存
  filter_context_content: string;
  filter_context_name: string;
  filter_variable_name: string;
  form_state: {
    context: string;
    context_name: string;
    default_corpus: string;
    default_keywords: string;
    remark: string;
    variable_name: string;
  };
  modal_visible: boolean;
  search_text: string;
  version_drawer_visible: boolean;
  viewing_context_id: null | number;
};

// 详情抽屉
const detailDrawerVisible = ref(false);
const viewingContext = ref<null | PluginContext>(null);

// 变量选项（从 Plugin 获取）
const variableOptions = ref<string[]>([]);

// 快照相关状态
const versionDrawerVisible = ref(false);
const versionHistory = ref<Snapshot[]>([]);
const versionLoading = ref(false);
const autoSaveStatus = ref<'error' | 'idle' | 'saved' | 'saving'>('idle');
const hasDraft = ref(false);
const currentEntityCode = ref('');
const versionDetailVisible = ref(false);
const viewingVersion = ref<null | Snapshot>(null);

// 表单状态
const formState = reactive({
  variable_name: '',
  context_name: '',
  context: '',
  default_keywords: '{}',
  default_corpus: '{}',
  remark: '',
});

const columns = [
  {
    title: '变量名',
    dataIndex: 'variable_name',
    key: 'variable_name',
    width: 150,
  },
  {
    title: '上下文名称',
    dataIndex: 'context_name',
    key: 'context_name',
    width: 180,
  },
  {
    title: '上下文内容',
    dataIndex: 'context',
    key: 'context',
    ellipsis: true,
  },
  {
    title: '默认关键词',
    dataIndex: 'default_keywords',
    key: 'default_keywords',
    width: 120,
  },
  {
    title: '默认语料',
    dataIndex: 'default_corpus',
    key: 'default_corpus',
    width: 120,
  },
  {
    title: '上线状态',
    dataIndex: 'publish_status',
    key: 'publish_status',
    width: 100,
  },
  {
    title: '更新时间',
    dataIndex: 'update_time',
    key: 'update_time',
    width: 180,
  },
  { title: '操作', key: 'action', width: 280, fixed: 'right' as const },
];

// 获取 PluginContext 列表
async function fetchContexts() {
  loading.value = true;
  try {
    const response = await requestClient.get<PluginContext[]>(
      '/v1/plugin-contexts',
    );
    dataSource.value = response || [];
  } catch (error) {
    console.error('获取 PluginContext 列表失败:', error);
    message.error('获取上下文列表失败');
  } finally {
    loading.value = false;
  }
}

// 获取 Plugin 变量列表
async function fetchVariableOptions() {
  try {
    const response = await requestClient.get<Plugin[]>('/v1/plugins');
    const allVars = new Set<string>();
    for (const plugin of response || []) {
      if (plugin.variable_list) {
        for (const v of plugin.variable_list) {
          allVars.add(v);
        }
      }
    }
    variableOptions.value = [...allVars].toSorted();
  } catch (error) {
    console.error('获取变量列表失败:', error);
  }
}

// 重置表单
function resetForm() {
  formState.variable_name = '';
  formState.context_name = '';
  formState.context = '';
  formState.default_keywords = '{}';
  formState.default_corpus = '{}';
  formState.remark = '';
}

// 新增
async function handleAdd() {
  editingContext.value = null;
  resetForm();
  autoSaveStatus.value = 'idle';
  hasDraft.value = false;
  modalVisible.value = true;
}

// ========== 快照功能 ==========

// 自动保存草稿（debounce 2秒）
const autoSaveDraft = useDebounceFn(async () => {
  if (
    !modalVisible.value ||
    !formState.variable_name ||
    !formState.context_name
  )
    return;
  if (page_persistence.is_restoring.value) return;

  autoSaveStatus.value = 'saving';
  try {
    // 使用 variable_name:context_name 作为唯一标识
    const entityCode = `${formState.variable_name}:${formState.context_name}`;
    await requestClient.post('/v1/snapshots/draft', {
      entity_type: 'plugin_context',
      entity_code: entityCode,
      entity_id: editingContext.value?.id || null,
      content: { ...formState },
    });
    autoSaveStatus.value = 'saved';
    hasDraft.value = true;
    // 3秒后恢复空闲状态
    setTimeout(() => {
      if (autoSaveStatus.value === 'saved') {
        autoSaveStatus.value = 'idle';
      }
    }, 3000);
  } catch (error) {
    console.error('自动保存草稿失败:', error);
    autoSaveStatus.value = 'error';
  }
}, 2000);

// 检查是否有草稿
async function checkDraft(entityCode: string): Promise<null | Snapshot> {
  try {
    const response = await requestClient.get<{
      draft: null | Snapshot;
      has_draft: boolean;
    }>(`/v1/snapshots/draft/plugin_context/${entityCode}`);
    return response?.has_draft ? response.draft : null;
  } catch {
    return null;
  }
}

// 恢复草稿
function recoverDraft(snapshot: Snapshot) {
  const content = snapshot.content;
  formState.variable_name = content.variable_name || '';
  formState.context_name = content.context_name || '';
  formState.context = content.context || '';
  formState.default_keywords = content.default_keywords || '{}';
  formState.default_corpus = content.default_corpus || '{}';
  formState.remark = content.remark || '';
  hasDraft.value = true;
  message.success('已恢复草稿');
}

// 获取版本历史
async function fetchVersionHistory(entityCode: string) {
  versionLoading.value = true;
  try {
    const response = await requestClient.get<{
      items: Snapshot[];
      total: number;
    }>(`/v1/snapshots/versions/plugin_context/${entityCode}`);
    versionHistory.value = response?.items || [];
  } catch (error) {
    console.error('获取版本历史失败:', error);
    message.error('获取版本历史失败');
  } finally {
    versionLoading.value = false;
  }
}

// 打开版本历史抽屉
async function handleShowVersions(record: PluginContext) {
  if (!record.variable_name || !record.context_name) {
    message.warning('该记录缺少变量名或上下文名称，无法查看历史');
    return;
  }
  // 使用 variable_name:context_name 作为唯一标识
  const entityCode = `${record.variable_name}:${record.context_name}`;
  currentEntityCode.value = entityCode;
  versionDrawerVisible.value = true;
  await fetchVersionHistory(entityCode);
}

// 查看版本详情
function handleViewVersion(snapshot: Snapshot) {
  viewingVersion.value = snapshot;
  versionDetailVisible.value = true;
}

// 恢复到指定版本
async function handleRestoreVersion(snapshot: Snapshot) {
  Modal.confirm({
    title: '确认恢复',
    content: `确定要恢复到版本 ${snapshot.version} 吗？当前内容将被覆盖。`,
    okText: '确定',
    cancelText: '取消',
    onOk: async () => {
      try {
        const content = snapshot.content;
        // 解析 JSON 字段
        let defaultKeywords = null;
        let defaultCorpus = null;
        try {
          if (content.default_keywords) {
            defaultKeywords =
              typeof content.default_keywords === 'string'
                ? JSON.parse(content.default_keywords)
                : content.default_keywords;
          }
        } catch {
          defaultKeywords = null;
        }
        try {
          if (content.default_corpus) {
            defaultCorpus =
              typeof content.default_corpus === 'string'
                ? JSON.parse(content.default_corpus)
                : content.default_corpus;
          }
        } catch {
          defaultCorpus = null;
        }

        // 将快照内容提交到后端
        await requestClient.put(`/v1/plugin-contexts/${content.id}`, {
          variable_name: content.variable_name,
          context_name: content.context_name,
          context: content.context,
          default_keywords: defaultKeywords,
          default_corpus: defaultCorpus,
          remark: content.remark,
        });
        message.success(`已恢复到版本 ${snapshot.version}`);
        versionDrawerVisible.value = false;
        versionDetailVisible.value = false;
        await fetchContexts();
      } catch (error) {
        console.error('恢复版本失败:', error);
        message.error('恢复版本失败');
      }
    },
  });
}

// 监听表单变化，触发自动保存
watch(
  () => ({ ...formState }),
  () => {
    if (page_persistence.is_restoring.value) return;
    if (
      modalVisible.value &&
      formState.variable_name &&
      formState.context_name
    ) {
      autoSaveDraft();
    }
  },
  { deep: true },
);

// 编辑
async function handleEdit(record: PluginContext) {
  // 检查上线状态
  try {
    const checkResult = await checkCanModifyApi(
      'PluginContext',
      record.context_name || String(record.id),
    );

    if (!checkResult.allowed) {
      if (checkResult.action === 'reject') {
        // 已上线，直接拒绝编辑
        message.error(checkResult.reason || '该上下文已上线，不可编辑');
        return;
      } else if (checkResult.action === 'confirm') {
        // 有引用关系，需要确认
        Modal.confirm({
          title: '确认编辑',
          content: checkResult.reason,
          okText: '继续编辑',
          cancelText: '取消',
          onOk: async () => {
            await proceedEdit(record);
          },
        });
        return;
      }
    }
  } catch (error) {
    console.error('检查编辑权限失败:', error);
    // 检查失败时，为了安全起见，继续检查本地状态
    if (record.publish_status === 'PUBLISHED') {
      message.error('该上下文已上线，不可编辑');
      return;
    }
  }

  // 允许编辑
  await proceedEdit(record);
}

async function proceedEdit(record: PluginContext) {
  editingContext.value = record;
  formState.variable_name = record.variable_name || '';
  formState.context_name = record.context_name || '';
  formState.context = record.context || '';
  formState.default_keywords = record.default_keywords
    ? JSON.stringify(record.default_keywords, null, 2)
    : '{}';
  formState.default_corpus = record.default_corpus
    ? JSON.stringify(record.default_corpus, null, 2)
    : '{}';
  formState.remark = record.remark || '';
  autoSaveStatus.value = 'idle';
  hasDraft.value = false;
  modalVisible.value = true;

  // 检查是否有草稿（使用 variable_name:context_name 作为唯一标识）
  if (record.variable_name && record.context_name) {
    const entityCode = `${record.variable_name}:${record.context_name}`;
    const draft = await checkDraft(entityCode);
    if (draft) {
      Modal.confirm({
        title: '发现草稿',
        content: '检测到有未保存的草稿，是否恢复？',
        okText: '恢复草稿',
        cancelText: '使用当前版本',
        onOk: () => {
          recoverDraft(draft);
        },
      });
    }
  }
}

// 查看详情
function handleView(record: PluginContext) {
  viewingContext.value = record;
  detailDrawerVisible.value = true;
}

// 删除
async function handleDelete(record: PluginContext) {
  // 检查上线状态
  try {
    const checkResult = await checkCanModifyApi(
      'PluginContext',
      record.context_name || String(record.id),
    );

    if (!checkResult.allowed) {
      if (checkResult.action === 'reject') {
        // 已上线，直接拒绝删除
        message.error(checkResult.reason || '该上下文已上线，不可删除');
        return;
      } else if (checkResult.action === 'confirm') {
        // 有引用关系，需要确认
        Modal.confirm({
          title: '确认删除',
          content: `${checkResult.reason}\n\n是否继续删除？`,
          okText: '继续删除',
          cancelText: '取消',
          okButtonProps: { danger: true },
          onOk: async () => {
            await proceedDelete(record);
          },
        });
        return;
      }
    }
  } catch (error) {
    console.error('检查删除权限失败:', error);
    // 检查失败时，为了安全起见，继续检查本地状态
    if (record.publish_status === 'PUBLISHED') {
      message.error('该上下文已上线，不可删除');
      return;
    }
  }

  // 允许删除
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除上下文 "${record.context_name}" 吗？`,
    okText: '确定',
    cancelText: '取消',
    okButtonProps: { danger: true },
    onOk: async () => {
      await proceedDelete(record);
    },
  });
}

async function proceedDelete(record: PluginContext) {
  try {
    await requestClient.delete(`/v1/plugin-contexts/${record.id}`);
    message.success('删除成功');
    fetchContexts();
  } catch {
    message.error('删除失败');
  }
}

// 提交表单
async function handleSubmit() {
  // 表单验证
  if (!formState.variable_name.trim()) {
    message.error('请输入或选择变量名');
    return;
  }
  if (!formState.context_name.trim()) {
    message.error('请输入上下文名称');
    return;
  }

  // 验证 JSON 格式
  let defaultKeywords = null;
  let defaultCorpus = null;
  try {
    if (formState.default_keywords.trim()) {
      defaultKeywords = JSON.parse(formState.default_keywords);
    }
  } catch {
    message.error('默认关键词 JSON 格式错误');
    return;
  }
  try {
    if (formState.default_corpus.trim()) {
      defaultCorpus = JSON.parse(formState.default_corpus);
    }
  } catch {
    message.error('默认语料 JSON 格式错误');
    return;
  }

  isSubmitting.value = true;
  try {
    const payload = {
      variable_name: formState.variable_name.trim() || null,
      context_name: formState.context_name.trim() || null,
      context: formState.context.trim() || null,
      default_keywords: defaultKeywords,
      default_corpus: defaultCorpus,
      remark: formState.remark.trim() || null,
    };

    if (editingContext.value) {
      await requestClient.put(
        `/v1/plugin-contexts/${editingContext.value.id}`,
        payload,
      );
      message.success('更新成功');
    } else {
      await requestClient.post('/v1/plugin-contexts', payload);
      message.success('创建成功');
    }

    // 保存成功后草稿会被后端自动删除
    hasDraft.value = false;
    autoSaveStatus.value = 'idle';

    await fetchContexts();
    modalVisible.value = false;
  } catch (error: any) {
    const errorMsg =
      error?.response?.data?.detail ||
      (editingContext.value ? '更新失败' : '创建失败');
    message.error(errorMsg);
  } finally {
    isSubmitting.value = false;
  }
}

// 搜索过滤
const filteredData = computed(() => {
  let result = dataSource.value;

  // 综合搜索（编码/名称/备注）
  if (searchText.value) {
    const keyword = searchText.value.toLowerCase();
    result = result.filter(
      (item) =>
        (item.variable_name &&
          item.variable_name.toLowerCase().includes(keyword)) ||
        (item.context_name &&
          item.context_name.toLowerCase().includes(keyword)) ||
        (item.remark && item.remark.toLowerCase().includes(keyword)),
    );
  }

  // 变量名筛选
  if (filterVariableName.value) {
    const keyword = filterVariableName.value.toLowerCase();
    result = result.filter(
      (item) =>
        item.variable_name &&
        item.variable_name.toLowerCase().includes(keyword),
    );
  }

  // 上下文名称筛选
  if (filterContextName.value) {
    const keyword = filterContextName.value.toLowerCase();
    result = result.filter(
      (item) =>
        item.context_name && item.context_name.toLowerCase().includes(keyword),
    );
  }

  // 上下文内容筛选
  if (filterContextContent.value) {
    const keyword = filterContextContent.value.toLowerCase();
    result = result.filter(
      (item) => item.context && item.context.toLowerCase().includes(keyword),
    );
  }

  return result;
});

// 重置筛选
function resetFilters() {
  searchText.value = '';
  filterVariableName.value = '';
  filterContextName.value = '';
  filterContextContent.value = '';
}

// 格式化时间
function formatTime(time: null | string) {
  if (!time) return '-';
  return time.replace('T', ' ').slice(0, 19);
}

// JSON 格式化按钮
function formatKeywordsJson() {
  try {
    const parsed = JSON.parse(formState.default_keywords);
    formState.default_keywords = JSON.stringify(parsed, null, 2);
    message.success('格式化成功');
  } catch {
    message.error('JSON 格式错误');
  }
}

function formatCorpusJson() {
  try {
    const parsed = JSON.parse(formState.default_corpus);
    formState.default_corpus = JSON.stringify(parsed, null, 2);
    message.success('格式化成功');
  } catch {
    message.error('JSON 格式错误');
  }
}

// 截断文本
function truncateText(text: null | string, maxLen = 50): string {
  if (!text) return '-';
  return text.length > maxLen ? `${text.slice(0, maxLen)}...` : text;
}

const page_persistence =
  use_page_persistence<PersistedPluginContextPageStateV1>({
    storage_key: 'raap_admin.config.plugin_context.persist.v1',
    version: 1,
    get_state: () => ({
      search_text: searchText.value || '',
      // 筛选条件
      filter_variable_name: filterVariableName.value || '',
      filter_context_name: filterContextName.value || '',
      filter_context_content: filterContextContent.value || '',
      modal_visible: !!modalVisible.value,
      editing_context_id: editingContext.value?.id ?? null,
      form_state: {
        variable_name: formState.variable_name || '',
        context_name: formState.context_name || '',
        context: formState.context || '',
        default_keywords: formState.default_keywords || '{}',
        default_corpus: formState.default_corpus || '{}',
        remark: formState.remark || '',
      },
      detail_drawer_visible: !!detailDrawerVisible.value,
      viewing_context_id: viewingContext.value?.id ?? null,
      version_drawer_visible: !!versionDrawerVisible.value,
      current_entity_code: currentEntityCode.value || '',
    }),
    apply_state: async (persisted) => {
      // 还原搜索和筛选条件
      searchText.value = persisted.search_text || '';
      filterVariableName.value = persisted.filter_variable_name || '';
      filterContextName.value = persisted.filter_context_name || '';
      filterContextContent.value = persisted.filter_context_content || '';

      // 还原详情抽屉（优先）
      if (persisted.detail_drawer_visible && persisted.viewing_context_id) {
        const found = dataSource.value.find(
          (x) => x.id === persisted.viewing_context_id,
        );
        if (found) {
          viewingContext.value = found;
          detailDrawerVisible.value = true;
        }
      }

      // 还原编辑弹窗 + 表单（以本地为准，避免触发“发现草稿”弹窗）
      if (persisted.modal_visible) {
        const editing =
          persisted.editing_context_id === null ||
          persisted.editing_context_id === undefined
            ? null
            : dataSource.value.find(
                (x) => x.id === persisted.editing_context_id,
              );
        editingContext.value = editing || null;

        formState.variable_name = persisted.form_state?.variable_name || '';
        formState.context_name = persisted.form_state?.context_name || '';
        formState.context = persisted.form_state?.context || '';
        formState.default_keywords =
          persisted.form_state?.default_keywords || '{}';
        formState.default_corpus = persisted.form_state?.default_corpus || '{}';
        formState.remark = persisted.form_state?.remark || '';

        autoSaveStatus.value = 'idle';
        hasDraft.value = false;
        modalVisible.value = true;
      }

      // 还原版本历史抽屉（只恢复打开状态和 entityCode，再重新拉一次版本列表）
      currentEntityCode.value = persisted.current_entity_code || '';
      versionDrawerVisible.value = !!persisted.version_drawer_visible;
      if (versionDrawerVisible.value && currentEntityCode.value) {
        await fetchVersionHistory(currentEntityCode.value);
      }
    },
  });

onMounted(async () => {
  await Promise.all([fetchContexts(), fetchVariableOptions()]);
  page_persistence.start_auto_persist();
  await page_persistence.restore();
});
</script>

<template>
  <div class="p-4">
    <!-- 粘性筛选头部 -->
    <div
      class="sticky top-0 z-10 -mx-4 -mt-4 mb-3 bg-background/90 px-4 pb-4 pt-2 shadow-lg backdrop-blur-md"
      style="border-bottom: 1px solid hsl(var(--border) / 30%)"
    >
      <!-- 标题行 -->
      <div class="mb-2 flex items-center gap-3">
        <span
          class="bg-gradient-to-r from-[hsl(var(--primary))] to-[#22c55e] bg-clip-text text-xl font-bold text-transparent"
        >
          {{ route.meta.title || '专家插件上下文管理' }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">搜索</span>
          <Input
            v-model:value="searchText"
            placeholder="综合搜索..."
            style="width: 140px"
            allow-clear
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">变量名</span>
          <Input
            v-model:value="filterVariableName"
            placeholder="变量名筛选..."
            style="width: 140px"
            allow-clear
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">上下文名称</span>
          <Input
            v-model:value="filterContextName"
            placeholder="上下文名称筛选..."
            style="width: 160px"
            allow-clear
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">上下文内容</span>
          <Input
            v-model:value="filterContextContent"
            placeholder="上下文内容筛选..."
            style="width: 160px"
            allow-clear
          />
        </div>
        <div class="filter-actions">
          <Button @click="resetFilters">重置</Button>
          <Button @click="fetchContexts">刷新</Button>
          <Button type="primary" @click="handleAdd">新增上下文</Button>
        </div>
      </div>
    </div>

    <Card :bordered="false">
      <Table
        :columns="columns"
        :data-source="filteredData"
        :loading="loading"
        :pagination="{
          pageSize: 10,
          showSizeChanger: true,
          showTotal: (total: number) => `共 ${total} 条`,
        }"
        row-key="id"
        size="middle"
        :scroll="{ x: 1200 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'variable_name'">
            <Tag color="blue">{{ record.variable_name || '-' }}</Tag>
          </template>
          <template v-else-if="column.key === 'context_name'">
            <Tooltip :title="record.context_name">
              <code class="context-name-code">{{
                record.context_name || '-'
              }}</code>
            </Tooltip>
          </template>
          <template v-else-if="column.key === 'context'">
            <Tooltip placement="topLeft" :overlay-style="{ maxWidth: '500px' }">
              <template #title>
                <pre class="tooltip-content">{{ record.context || '-' }}</pre>
              </template>
              <span class="context-cell">{{
                truncateText(record.context, 60)
              }}</span>
            </Tooltip>
          </template>
          <template v-else-if="column.key === 'default_keywords'">
            <Tooltip
              v-if="
                record.default_keywords &&
                Object.keys(record.default_keywords).length > 0
              "
              placement="topLeft"
              :overlay-style="{ maxWidth: '400px' }"
            >
              <template #title>
                <pre class="tooltip-json">{{
                  JSON.stringify(record.default_keywords, null, 2)
                }}</pre>
              </template>
              <Tag color="processing">
                {{ Object.keys(record.default_keywords).length }} 项
              </Tag>
            </Tooltip>
            <span v-else class="text-gray-400">-</span>
          </template>
          <template v-else-if="column.key === 'default_corpus'">
            <Tooltip
              v-if="
                record.default_corpus &&
                Object.keys(record.default_corpus).length > 0
              "
              placement="topLeft"
              :overlay-style="{ maxWidth: '400px' }"
            >
              <template #title>
                <pre class="tooltip-json">{{
                  JSON.stringify(record.default_corpus, null, 2)
                }}</pre>
              </template>
              <Tag color="orange">
                {{ Object.keys(record.default_corpus).length }} 项
              </Tag>
            </Tooltip>
            <span v-else class="text-gray-400">-</span>
          </template>
          <template v-else-if="column.key === 'publish_status'">
            <Tag
              :color="
                record.publish_status === 'PUBLISHED' ? 'blue' : 'default'
              "
            >
              {{ record.publish_status === 'PUBLISHED' ? '已发布' : '草稿' }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'update_time'">
            {{ formatTime(record.update_time) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <Space>
              <Button
                type="link"
                size="small"
                @click="handleView(record as PluginContext)"
              >
                👁️ 查看
              </Button>
              <Button
                type="link"
                size="small"
                :disabled="
                  (record as PluginContext).publish_status === 'PUBLISHED'
                "
                @click="handleEdit(record as PluginContext)"
              >
                ✏️ 编辑
              </Button>
              <Button
                type="link"
                size="small"
                @click="handleShowVersions(record as PluginContext)"
              >
                📜 历史
              </Button>
              <Button
                type="link"
                danger
                size="small"
                :disabled="
                  (record as PluginContext).publish_status === 'PUBLISHED'
                "
                @click="handleDelete(record as PluginContext)"
              >
                🗑️ 删除
              </Button>
            </Space>
          </template>
        </template>
      </Table>
    </Card>

    <!-- PluginContext 编辑弹窗 -->
    <Modal
      v-model:open="modalVisible"
      :width="800"
      :confirm-loading="isSubmitting"
      @ok="handleSubmit"
      @cancel="modalVisible = false"
    >
      <template #title>
        <Space>
          <span>{{ editingContext ? '编辑上下文' : '新增上下文' }}</span>
          <Tag v-if="autoSaveStatus === 'saving'" color="processing">
            💾 保存中...
          </Tag>
          <Tag v-else-if="autoSaveStatus === 'saved'" color="success">
            ✅ 已自动保存
          </Tag>
          <Tag v-else-if="autoSaveStatus === 'error'" color="error">
            ❌ 保存失败
          </Tag>
          <Tag v-else-if="hasDraft" color="warning">📝 有草稿</Tag>
        </Space>
      </template>
      <Form :model="formState" layout="vertical">
        <div class="grid grid-cols-2 gap-4">
          <FormItem
            label="变量名"
            name="variable_name"
            :rules="[{ required: true, message: '请输入变量名' }]"
          >
            <AutoComplete
              v-model:value="formState.variable_name"
              placeholder="选择或输入变量名"
              allow-clear
              :options="variableOptions.map((v) => ({ value: v }))"
              :filter-option="
                (input: string, option: any) =>
                  option.value.toLowerCase().includes(input.toLowerCase())
              "
            />
            <div class="form-hint">
              与 Plugin 的 variable_list 中的变量对应，可手动输入自定义变量名
            </div>
          </FormItem>
          <FormItem
            label="上下文名称"
            name="context_name"
            :rules="[{ required: true, message: '请输入上下文名称' }]"
          >
            <Input
              v-model:value="formState.context_name"
              placeholder="如: platform_rules"
            />
            <div class="form-hint">用于在 plugin_config 中引用</div>
          </FormItem>
        </div>

        <FormItem label="上下文内容" name="context">
          <Textarea
            v-model:value="formState.context"
            :rows="15"
            placeholder="输入上下文的详细内容/解释..."
          />
        </FormItem>

        <FormItem label="默认关键词 (JSON)" name="default_keywords">
          <div class="mb-2">
            <Button size="small" @click="formatKeywordsJson">
              格式化 JSON
            </Button>
          </div>
          <MonacoEditor
            v-model:model-value="formState.default_keywords"
            language="json"
            height="150px"
            placeholder="{}"
            :format-on-mount="true"
          />
        </FormItem>

        <FormItem label="默认语料 (JSON)" name="default_corpus">
          <div class="mb-2">
            <Button size="small" @click="formatCorpusJson">
              格式化 JSON
            </Button>
          </div>
          <MonacoEditor
            v-model:model-value="formState.default_corpus"
            language="json"
            height="150px"
            placeholder="{}"
            :format-on-mount="true"
          />
        </FormItem>

        <FormItem label="备注" name="remark">
          <Textarea
            v-model:value="formState.remark"
            :rows="2"
            placeholder="上下文描述/备注"
          />
        </FormItem>
      </Form>
    </Modal>

    <!-- 详情抽屉 -->
    <Drawer
      v-model:open="detailDrawerVisible"
      title="上下文详情"
      :width="700"
      class="detail-drawer"
    >
      <template v-if="viewingContext">
        <div class="detail-section">
          <div class="detail-label">变量名</div>
          <div class="detail-value">
            <Tag color="blue">{{ viewingContext.variable_name || '-' }}</Tag>
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-label">上下文名称</div>
          <div class="detail-value">
            <code>{{ viewingContext.context_name || '-' }}</code>
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-label">上下文内容</div>
          <div class="detail-content">
            <pre class="content-pre">{{ viewingContext.context || '-' }}</pre>
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-label">默认关键词</div>
          <div class="detail-content">
            <pre class="json-pre">{{
              viewingContext.default_keywords
                ? JSON.stringify(viewingContext.default_keywords, null, 2)
                : '-'
            }}</pre>
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-label">默认语料</div>
          <div class="detail-content">
            <pre class="json-pre">{{
              viewingContext.default_corpus
                ? JSON.stringify(viewingContext.default_corpus, null, 2)
                : '-'
            }}</pre>
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-label">备注</div>
          <div class="detail-value">{{ viewingContext.remark || '-' }}</div>
        </div>

        <div class="detail-section">
          <div class="detail-label">更新时间</div>
          <div class="detail-value">
            {{ formatTime(viewingContext.update_time) }}
          </div>
        </div>

        <div class="detail-footer">
          <Button
            type="primary"
            @click="
              handleEdit(viewingContext);
              detailDrawerVisible = false;
            "
          >
            ✏️ 编辑
          </Button>
        </div>
      </template>
    </Drawer>

    <!-- 版本历史抽屉 -->
    <Drawer
      v-model:open="versionDrawerVisible"
      title="版本历史"
      :width="600"
      class="version-drawer"
    >
      <div v-if="versionLoading" class="version-loading">加载中...</div>
      <div v-else-if="versionHistory.length === 0" class="version-empty">
        暂无版本历史
      </div>
      <Timeline v-else class="version-timeline">
        <TimelineItem
          v-for="snapshot in versionHistory"
          :key="snapshot.id"
          :color="snapshot.version === 1 ? 'green' : 'blue'"
        >
          <div class="version-item">
            <div class="version-header">
              <Tag :color="snapshot.version === 1 ? 'green' : 'blue'">
                版本 {{ snapshot.version }}
              </Tag>
              <span class="version-time">{{
                formatTime(snapshot.create_time)
              }}</span>
            </div>
            <div class="version-desc">
              {{ snapshot.description || '无描述' }}
            </div>
            <div class="version-actions">
              <Space>
                <Button
                  type="link"
                  size="small"
                  @click="handleViewVersion(snapshot)"
                >
                  👁️ 查看
                </Button>
                <Button
                  type="link"
                  size="small"
                  @click="handleRestoreVersion(snapshot)"
                >
                  🔄 恢复
                </Button>
              </Space>
            </div>
          </div>
        </TimelineItem>
      </Timeline>
    </Drawer>

    <!-- 版本详情抽屉 -->
    <Drawer
      v-model:open="versionDetailVisible"
      :title="`版本 ${viewingVersion?.version} 详情`"
      :width="900"
      root-class-name="version-detail-drawer"
    >
      <template v-if="viewingVersion">
        <div class="version-detail-header">
          <Tag :color="viewingVersion.version === 1 ? 'green' : 'blue'">
            版本 {{ viewingVersion.version }}
          </Tag>
          <span class="version-detail-time">{{
            formatTime(viewingVersion.create_time)
          }}</span>
        </div>

        <Descriptions :column="2" bordered size="small" class="mt-4">
          <DescriptionsItem label="变量名">
            <Tag color="blue">
              {{ viewingVersion.content.variable_name || '-' }}
            </Tag>
          </DescriptionsItem>
          <DescriptionsItem label="上下文名称">
            <code>{{ viewingVersion.content.context_name || '-' }}</code>
          </DescriptionsItem>
          <DescriptionsItem label="备注" :span="2">
            {{ viewingVersion.content.remark || '-' }}
          </DescriptionsItem>
        </Descriptions>

        <Card title="上下文内容" size="small" class="mt-4">
          <pre class="config-json">{{
            viewingVersion.content.context || '-'
          }}</pre>
        </Card>

        <Card title="默认关键词" size="small" class="mt-4">
          <pre class="config-json">{{
            viewingVersion.content.default_keywords
              ? typeof viewingVersion.content.default_keywords === 'string'
                ? viewingVersion.content.default_keywords
                : JSON.stringify(
                    viewingVersion.content.default_keywords,
                    null,
                    2,
                  )
              : '-'
          }}</pre>
        </Card>

        <Card title="默认语料" size="small" class="mt-4">
          <pre class="config-json">{{
            viewingVersion.content.default_corpus
              ? typeof viewingVersion.content.default_corpus === 'string'
                ? viewingVersion.content.default_corpus
                : JSON.stringify(viewingVersion.content.default_corpus, null, 2)
              : '-'
          }}</pre>
        </Card>

        <div class="version-detail-footer">
          <Button type="primary" @click="handleRestoreVersion(viewingVersion)">
            🔄 恢复到此版本
          </Button>
        </div>
      </template>
    </Drawer>
  </div>
</template>

<style scoped>
.p-4 {
  padding: 16px;
}

/* 筛选行布局 */
.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
}

.filter-item {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
}

.filter-label {
  font-weight: 500;
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.filter-actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
  margin-left: auto;
}

.text-gray-400 {
  color: #9ca3af;
}

.mb-2 {
  margin-bottom: 8px;
}

.grid {
  display: grid;
}

.grid-cols-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.gap-4 {
  gap: 16px;
}

.context-name-code {
  padding: 2px 8px;
  font-family: 'Fira Code', Consolas, monospace;
  font-size: 13px;
  color: hsl(var(--primary));
  background: hsl(var(--muted));
  border-radius: 4px;
}

.context-cell {
  color: hsl(var(--muted-foreground));
  cursor: pointer;
}

.context-cell:hover {
  color: hsl(var(--primary));
}

.form-hint {
  margin-top: 4px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

/* Tooltip 样式 */
:global(.tooltip-content) {
  max-height: 300px;
  margin: 0;
  overflow-y: auto;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-all;
  white-space: pre-wrap;
}

:global(.tooltip-json) {
  max-height: 300px;
  margin: 0;
  overflow-y: auto;
  font-family: 'Fira Code', Consolas, monospace;
  font-size: 12px;
  line-height: 1.4;
  white-space: pre-wrap;
}

/* 详情抽屉样式 */
.detail-section {
  padding: 12px 0;
  border-bottom: 1px solid hsl(var(--border));
}

.detail-section:last-of-type {
  border-bottom: none;
}

.detail-label {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
}

.detail-value {
  font-size: 14px;
  color: hsl(var(--foreground));
}

.detail-value code {
  padding: 2px 8px;
  font-family: 'Fira Code', Consolas, monospace;
  font-size: 13px;
  color: hsl(var(--primary));
  background: hsl(var(--muted));
  border-radius: 4px;
}

.detail-content {
  margin-top: 4px;
}

.content-pre,
.json-pre {
  max-height: 200px;
  padding: 12px;
  margin: 0;
  overflow-y: auto;
  font-family: 'Fira Code', Consolas, monospace;
  font-size: 13px;
  line-height: 1.5;
  color: hsl(var(--foreground));
  word-break: break-all;
  white-space: pre-wrap;
  background: hsl(var(--muted));
  border-radius: 6px;
}

.detail-footer {
  padding-top: 16px;
  margin-top: 24px;
  text-align: right;
  border-top: 1px solid hsl(var(--border));
}

/* 版本历史相关样式 */
.version-loading,
.version-empty {
  padding: 40px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.version-timeline {
  padding: 16px;
}

.version-item {
  padding-left: 8px;
}

.version-header {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 4px;
}

.version-time {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.version-desc {
  margin-bottom: 4px;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.version-actions {
  padding-left: 4px;
}

/* 版本详情抽屉样式 */
.version-detail-header {
  display: flex;
  gap: 12px;
  align-items: center;
  padding-bottom: 16px;
  border-bottom: 1px solid hsl(var(--border));
}

.version-detail-time {
  font-size: 14px;
  color: hsl(var(--muted-foreground));
}

.version-detail-footer {
  padding-top: 16px;
  margin-top: 24px;
  text-align: right;
  border-top: 1px solid hsl(var(--border));
}

.config-json {
  max-height: 300px;
  padding: 16px;
  margin: 0;
  overflow-y: auto;
  font-family: 'Fira Code', Consolas, Monaco, monospace;
  font-size: 13px;
  line-height: 1.5;
  color: hsl(var(--foreground));
  overflow-wrap: break-word;
  white-space: pre-wrap;
  background: hsl(var(--muted));
  border-radius: 6px;
}

.mt-4 {
  margin-top: 16px;
}
</style>

<style>
/* 版本详情抽屉 - 全局样式支持主题切换 */
.version-detail-drawer .ant-drawer-content {
  background: hsl(var(--background-deep));
}

.version-detail-drawer .ant-drawer-header {
  background: hsl(var(--card));
  border-bottom: 1px solid hsl(var(--border));
}

.version-detail-drawer .ant-drawer-title {
  color: hsl(var(--foreground));
}

.version-detail-drawer .ant-drawer-close {
  color: hsl(var(--muted-foreground));
}

.version-detail-drawer .ant-drawer-close:hover {
  color: hsl(var(--foreground));
}

.version-detail-drawer .ant-drawer-body {
  background: hsl(var(--background-deep));
}

/* Descriptions 主题适配 */
.version-detail-drawer .ant-descriptions {
  overflow: hidden;
  background: hsl(var(--card));
  border-radius: 8px;
}

.version-detail-drawer .ant-descriptions-bordered .ant-descriptions-view {
  border: 1px solid hsl(var(--border));
}

.version-detail-drawer .ant-descriptions-bordered .ant-descriptions-item-label {
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted));
  border-color: hsl(var(--border));
}

.version-detail-drawer
  .ant-descriptions-bordered
  .ant-descriptions-item-content {
  color: hsl(var(--foreground));
  background: hsl(var(--card));
  border-color: hsl(var(--border));
}

.version-detail-drawer .ant-descriptions-bordered .ant-descriptions-row {
  border-color: hsl(var(--border));
}

/* Card 主题适配 */
.version-detail-drawer .ant-card {
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.version-detail-drawer .ant-card-head {
  color: hsl(var(--foreground));
  background: hsl(var(--muted));
  border-bottom: 1px solid hsl(var(--border));
}

.version-detail-drawer .ant-card-head-title {
  color: hsl(var(--primary));
}

.version-detail-drawer .ant-card-body {
  background: hsl(var(--card));
}

/* code 标签主题适配 */
.version-detail-drawer code {
  padding: 2px 8px;
  font-family: 'Fira Code', Consolas, monospace;
  font-size: 13px;
  color: hsl(var(--primary));
  background: hsl(var(--muted));
  border-radius: 4px;
}
</style>
