<script setup lang="ts">
import type { LLMApi } from '#/api/core/llm';

import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';

import { formatDateTime } from '@vben/utils';

import { SearchOutlined } from '@ant-design/icons-vue';
import {
  Badge,
  Button,
  Card,
  Descriptions,
  DescriptionsItem,
  Drawer,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Modal,
  Popconfirm,
  Select,
  SelectOption,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Textarea,
  Tooltip,
} from 'ant-design-vue';

import {
  createProviderApi,
  deleteProviderApi,
  disableProviderApi,
  enableProviderApi,
  fetchRemoteModelsApi,
  getCircuitBreakersApi,
  getProviderListApi,
  getRemoteModelsApi,
  getRouteListApi,
  resetCircuitBreakerApi,
  syncModelsApi,
  testProviderApi,
  updateProviderApi,
} from '#/api/core/llm';

const route = useRoute();

// 状态
const loading = ref(false);
const dataSource = ref<LLMApi.ProviderConfig[]>([]);
const searchText = ref('');
const displayData = computed(() => {
  const s = searchText.value.trim().toLowerCase();
  if (!s) return dataSource.value;
  return dataSource.value.filter(
    (item) =>
      item.provider_code.toLowerCase().includes(s) ||
      item.provider_name.toLowerCase().includes(s) ||
      (item.default_model || '').toLowerCase().includes(s),
  );
});
const circuitBreakers = ref<Map<string, LLMApi.CircuitBreaker>>(new Map());
const modalVisible = ref(false);
const editingProvider = ref<LLMApi.ProviderConfig | null>(null);
const isSubmitting = ref(false);
const detailVisible = ref(false);
const viewingProvider = ref<LLMApi.ProviderConfig | null>(null);
const testingProvider = ref<null | string>(null);
const pagination = reactive({
  current: 1,
  pageSize: 10,
  showSizeChanger: true,
  pageSizeOptions: ['10', '20', '50', '100'],
  showTotal: (total: number) => `共 ${total} 条`,
});

// 远程模型相关状态
const remoteModelsVisible = ref(false);
const remoteModelsLoading = ref(false);
const remoteModelsProvider = ref<LLMApi.ProviderConfig | null>(null);
const remoteModels = ref<LLMApi.RemoteModelInfo[]>([]);
const drawerModelSearchText = ref('');
const drawerModelSortOrder = ref<'asc' | 'desc' | 'none'>('none');
const filteredDrawerModels = computed(() => {
  let list = [...remoteModels.value];
  const s = drawerModelSearchText.value.trim().toLowerCase();
  if (s) {
    list = list.filter(
      (m) =>
        m.model_id.toLowerCase().includes(s) ||
        (m.description || '').toLowerCase().includes(s),
    );
  }

  if (drawerModelSortOrder.value !== 'none') {
    list.sort((a, b) => {
      const priceA = a.cost_per_1k_input || 0;
      const priceB = b.cost_per_1k_input || 0;
      return drawerModelSortOrder.value === 'asc'
        ? priceA - priceB
        : priceB - priceA;
    });
  }

  return list;
});
const selectedModelIds = ref<string[]>([]);
const syncingModels = ref(false);

function toggleSortOrder() {
  if (drawerModelSortOrder.value === 'none') {
    drawerModelSortOrder.value = 'asc';
  } else if (drawerModelSortOrder.value === 'asc') {
    drawerModelSortOrder.value = 'desc';
  } else {
    drawerModelSortOrder.value = 'none';
  }
}

const testAfterSave = ref(false);
const _paramKey = ref('');
const _paramVal = ref('');

// 远程模型过滤
const remoteModelSearchText = ref('');
const filteredRemoteModels = computed(() => {
  const s = remoteModelSearchText.value.trim().toLowerCase();
  if (!s) return editRemoteModels.value;
  return editRemoteModels.value.filter((m) =>
    m.model_id.toLowerCase().includes(s),
  );
});

// 表单状态
const formState = reactive({
  provider_code: '',
  provider_name: '',
  provider_type: 'openai_compatible' as LLMApi.ProviderType,
  base_url: '',
  api_key: '',
  default_model: '',
  available_models: [] as string[],
  default_params: {} as Record<string, any>,
  rate_limit: undefined as number | undefined,
  timeout: 120,
  priority: 50,
  enabled: true,
  description: '',
});

// 编辑时获取远程模型
const editRemoteModels = ref<LLMApi.RemoteModelInfo[]>([]);
const editRemoteModelsLoading = ref(false);
const modelSource = ref<'local' | 'remote'>('remote');
const defaultModelOptions = computed(() => {
  const set = new Set<string>();
  for (const m of formState.available_models) set.add(m);
  for (const m of editRemoteModels.value || []) set.add(m.model_id);
  return [...set];
});

// Provider 类型选项
const providerTypeOptions = [
  { value: 'openai_compatible', label: 'OpenAI 兼容' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'azure_openai', label: 'Azure OpenAI' },
  { value: 'custom', label: '自定义' },
];

// 熔断状态颜色
type BadgeStatus = 'default' | 'error' | 'processing' | 'success' | 'warning';
const circuitStateColors: Record<LLMApi.CircuitState, BadgeStatus> = {
  closed: 'success',
  half_open: 'warning',
  open: 'error',
};

const circuitStateLabels: Record<LLMApi.CircuitState, string> = {
  closed: '正常',
  half_open: '半开',
  open: '熔断',
};

// 表格列定义
const columns = [
  {
    title: 'Provider',
    dataIndex: 'provider_code',
    key: 'provider_code',
    width: 150,
    sorter: (a: any, b: any) => a.provider_code.localeCompare(b.provider_code),
  },
  {
    title: '名称',
    dataIndex: 'provider_name',
    key: 'provider_name',
    width: 150,
    sorter: (a: any, b: any) => a.provider_name.localeCompare(b.provider_name),
  },
  {
    title: '类型',
    dataIndex: 'provider_type',
    key: 'provider_type',
    width: 120,
  },
  {
    title: '默认模型',
    dataIndex: 'default_model',
    key: 'default_model',
    width: 150,
    sorter: (a: any, b: any) =>
      (a.default_model || '').localeCompare(b.default_model || ''),
  },
  {
    title: '优先级',
    dataIndex: 'priority',
    key: 'priority',
    width: 80,
    sorter: (a: any, b: any) => a.priority - b.priority,
  },
  { title: '熔断状态', key: 'circuit_state', width: 100 },
  {
    title: '状态',
    dataIndex: 'enabled',
    key: 'enabled',
    width: 80,
    sorter: (a: any, b: any) => Number(a.enabled) - Number(b.enabled),
  },
  {
    title: '更新时间',
    dataIndex: 'update_time',
    key: 'update_time',
    width: 180,
    sorter: (a: any, b: any) =>
      (a.update_time || '').localeCompare(b.update_time || ''),
  },
  { title: '操作', key: 'action', width: 360 },
];

// 获取 Provider 列表
async function fetchProviders() {
  loading.value = true;
  try {
    const [providerRes, circuitRes] = await Promise.all([
      getProviderListApi(),
      getCircuitBreakersApi(),
    ]);
    dataSource.value = providerRes?.items || [];

    // 构建熔断状态 Map
    const cbMap = new Map<string, LLMApi.CircuitBreaker>();
    for (const cb of circuitRes?.items || []) {
      cbMap.set(cb.provider_code, cb);
    }
    circuitBreakers.value = cbMap;
  } catch (error) {
    console.error('获取 Provider 列表失败:', error);
    message.error('获取 Provider 列表失败');
  } finally {
    loading.value = false;
  }
}

// 获取熔断状态
function getCircuitBreaker(code: string): LLMApi.CircuitBreaker | undefined {
  return circuitBreakers.value.get(code);
}

// 重置表单
function resetForm() {
  formState.provider_code = '';
  formState.provider_name = '';
  formState.provider_type = 'openai_compatible';
  formState.base_url = '';
  formState.api_key = '';
  formState.default_model = '';
  formState.available_models = [];
  formState.default_params = {};
  formState.rate_limit = undefined;
  formState.timeout = 120;
  formState.priority = 50;
  formState.enabled = true;
  formState.description = '';
}

// 新增
function handleAdd() {
  editingProvider.value = null;
  resetForm();
  editRemoteModels.value = [];
  modelSource.value = 'remote';
  modalVisible.value = true;
}

// 编辑
function handleEdit(record: LLMApi.ProviderConfig) {
  editingProvider.value = record;
  formState.provider_code = record.provider_code;
  formState.provider_name = record.provider_name;
  formState.provider_type = record.provider_type;
  formState.base_url = record.base_url;
  formState.api_key = ''; // 不回显 API Key
  formState.default_model = record.default_model || '';
  formState.available_models = record.available_models || [];
  formState.default_params = record.default_params || {};
  formState.rate_limit = record.rate_limit || undefined;
  formState.timeout = record.timeout;
  formState.priority = record.priority;
  formState.enabled = record.enabled;
  formState.description = record.description || '';
  editRemoteModels.value = [];
  remoteModelSearchText.value = ''; // 重置搜索
  modalVisible.value = true;
  // 异步获取模型（默认本地）
  fetchModelsForProvider();
}

// 查看详情
function handleView(record: LLMApi.ProviderConfig) {
  viewingProvider.value = record;
  detailVisible.value = true;
}

// 删除
async function handleDelete(record: LLMApi.ProviderConfig) {
  try {
    await deleteProviderApi(record.provider_code);
    message.success('删除成功');
    fetchProviders();
  } catch {
    message.error('删除失败');
  }
}

// 启用/禁用
async function handleToggleEnabled(record: LLMApi.ProviderConfig) {
  try {
    if (record.enabled) {
      await disableProviderApi(record.provider_code);
      message.success('已禁用');
    } else {
      await enableProviderApi(record.provider_code);
      message.success('已启用');
    }
    fetchProviders();
  } catch {
    message.error('操作失败');
  }
}

// 测试连接
async function handleTest(record: LLMApi.ProviderConfig) {
  testingProvider.value = record.provider_code;
  try {
    const result = await testProviderApi(record.provider_code);
    if (result?.success) {
      message.success(`连接成功，延迟: ${result.latency_ms}ms`);
    } else {
      message.error(`连接失败: ${result?.error_message || '未知错误'}`);
    }
  } catch (error: any) {
    message.error(`测试失败: ${error?.message || '未知错误'}`);
  } finally {
    testingProvider.value = null;
  }
}

// 重置熔断器
async function handleResetCircuit(code: string) {
  try {
    await resetCircuitBreakerApi(code);
    message.success('熔断器已重置');
    fetchProviders();
  } catch {
    message.error('重置失败');
  }
}

// 获取远程模型列表
async function handleGetRemoteModels(record: LLMApi.ProviderConfig) {
  remoteModelsProvider.value = record;
  remoteModelsVisible.value = true;
  remoteModelsLoading.value = true;
  selectedModelIds.value = [];
  drawerModelSearchText.value = ''; // 重置搜索

  try {
    const result = await getRemoteModelsApi(record.provider_code, 'llm');
    remoteModels.value = result?.items || [];
  } catch (error: any) {
    message.error(`获取远程模型失败: ${error?.message || '未知错误'}`);
    remoteModels.value = [];
  } finally {
    remoteModelsLoading.value = false;
  }
}

// 同步选中的模型到路由表
async function handleSyncModels() {
  if (selectedModelIds.value.length === 0) {
    message.warning('请先选择要同步的模型');
    return;
  }
  if (!remoteModelsProvider.value) return;

  syncingModels.value = true;
  try {
    const result = await syncModelsApi(
      remoteModelsProvider.value.provider_code,
      {
        model_ids: selectedModelIds.value,
        overwrite: false,
      },
    );

    if (result) {
      message.success(
        `同步完成: ${result.synced_count} 个成功, ${result.skipped_count} 个跳过`,
      );
      if (result.failed_count > 0) {
        message.warning(`${result.failed_count} 个模型同步失败`);
      }
    }
    selectedModelIds.value = [];
  } catch (error: any) {
    message.error(`同步失败: ${error?.message || '未知错误'}`);
  } finally {
    syncingModels.value = false;
  }
}

// 同步所有模型
async function handleSyncAllModels() {
  if (!remoteModelsProvider.value) return;

  syncingModels.value = true;
  try {
    const result = await syncModelsApi(
      remoteModelsProvider.value.provider_code,
      {
        overwrite: false,
      },
    );

    if (result) {
      message.success(
        `同步完成: ${result.synced_count} 个成功, ${result.skipped_count} 个已存在跳过`,
      );
      if (result.failed_count > 0) {
        message.warning(`${result.failed_count} 个模型同步失败`);
      }
    }
  } catch (error: any) {
    message.error(`同步失败: ${error?.message || '未知错误'}`);
  } finally {
    syncingModels.value = false;
  }
}

// 选择/取消选择模型
function toggleModelSelection(modelId: string) {
  const index = selectedModelIds.value.indexOf(modelId);
  if (index === -1) {
    selectedModelIds.value.push(modelId);
  } else {
    selectedModelIds.value.splice(index, 1);
  }
}

// 全选/取消全选
function toggleSelectAll() {
  const currentModelIds = filteredDrawerModels.value.map((m) => m.model_id);
  const allSelected = currentModelIds.every((id) =>
    selectedModelIds.value.includes(id),
  );

  if (allSelected) {
    // 如果当前显示的都选中了，则取消选中当前显示的
    selectedModelIds.value = selectedModelIds.value.filter(
      (id) => !currentModelIds.includes(id),
    );
  } else {
    // 否则选中当前显示的所有
    const newSelected = new Set(selectedModelIds.value);
    currentModelIds.forEach((id) => newSelected.add(id));
    selectedModelIds.value = [...newSelected];
  }
}

// 提交表单
async function handleSubmit() {
  if (!formState.provider_code.trim()) {
    message.error('请输入 Provider 编码');
    return;
  }
  const code = formState.provider_code.trim();
  if (!/^[a-z0-9_-]+$/.test(code)) {
    message.error('Provider 编码只能包含小写字母、数字、下划线或短横线');
    return;
  }
  if (!formState.provider_name.trim()) {
    message.error('请输入 Provider 名称');
    return;
  }
  if (!formState.base_url.trim()) {
    message.error('请输入 Base URL');
    return;
  }
  try {
    const url = new URL(formState.base_url.trim());
    if (!url.protocol.startsWith('http')) {
      throw new Error('协议必须为 http/https');
    }
  } catch {
    message.error('Base URL 格式无效，请输入合法的 http/https 地址');
    return;
  }

  isSubmitting.value = true;
  try {
    if (editingProvider.value) {
      // 更新
      const updateData: LLMApi.ProviderUpdate = {
        provider_name: formState.provider_name.trim(),
        provider_type: formState.provider_type,
        base_url: formState.base_url.trim(),
        default_model: formState.default_model.trim() || undefined,
        available_models:
          formState.available_models.length > 0
            ? formState.available_models
            : undefined,
        default_params:
          Object.keys(formState.default_params).length > 0
            ? formState.default_params
            : undefined,
        rate_limit: formState.rate_limit,
        timeout: formState.timeout,
        priority: formState.priority,
        enabled: formState.enabled,
        description: formState.description.trim() || undefined,
      };
      // 只有填写了新 API Key 才更新
      if (formState.api_key.trim()) {
        updateData.api_key = formState.api_key.trim();
      }
      await updateProviderApi(editingProvider.value.provider_code, updateData);
      message.success('更新成功');
    } else {
      // 创建
      if (!formState.api_key.trim()) {
        message.error('请输入 API Key');
        isSubmitting.value = false;
        return;
      }
      await createProviderApi({
        provider_code: formState.provider_code.trim(),
        provider_name: formState.provider_name.trim(),
        provider_type: formState.provider_type,
        base_url: formState.base_url.trim(),
        api_key: formState.api_key.trim(),
        default_model: formState.default_model.trim() || undefined,
        available_models:
          formState.available_models.length > 0
            ? formState.available_models
            : undefined,
        default_params:
          Object.keys(formState.default_params).length > 0
            ? formState.default_params
            : undefined,
        rate_limit: formState.rate_limit,
        timeout: formState.timeout,
        priority: formState.priority,
        enabled: formState.enabled,
        description: formState.description.trim() || undefined,
      });
      message.success('创建成功');
    }
    await fetchProviders();
    try {
      if (testAfterSave.value) {
        const codeToTest =
          editingProvider.value?.provider_code ||
          formState.provider_code.trim();
        const result = await testProviderApi(codeToTest);
        if (result?.success) {
          message.success(`连接成功，延迟: ${result.latency_ms}ms`);
        } else {
          message.error(`连接失败: ${result?.error_message || '未知错误'}`);
        }
      }
    } catch (error: any) {
      message.error(`测试失败: ${error?.message || '未知错误'}`);
    }
    modalVisible.value = false;
  } catch (error: any) {
    const errorMsg =
      error?.response?.data?.detail ||
      (editingProvider.value ? '更新失败' : '创建失败');
    message.error(errorMsg);
  } finally {
    isSubmitting.value = false;
  }
}

function addParam() {
  const key = _paramKey.value.trim();
  const rawVal = _paramVal.value.trim();
  if (!key) {
    message.warning('请输入参数名');
    return;
  }
  if (!rawVal) {
    message.warning('请输入参数值');
    return;
  }
  let val: any = rawVal;
  try {
    val = JSON.parse(rawVal);
  } catch {
    if (/^\d+(?:\.\d+)?$/.test(rawVal)) {
      val = Number(rawVal);
    } else if (
      rawVal.toLowerCase() === 'true' ||
      rawVal.toLowerCase() === 'false'
    ) {
      val = rawVal.toLowerCase() === 'true';
    }
  }
  formState.default_params[key] = val;
  _paramKey.value = '';
  _paramVal.value = '';
}

// 获取 Provider 可用的模型列表
async function fetchModelsForProvider(forceRemote = false) {
  editRemoteModelsLoading.value = true;
  try {
    if (editingProvider.value && !forceRemote) {
      // 编辑模式下，默认从已同步的路由表获取
      modelSource.value = 'local';
      const result = await getRouteListApi({
        provider_code: editingProvider.value.provider_code,
        limit: 1000,
      });
      // 适配接口，将本地路由信息转为 RemoteModelInfo 格式
      editRemoteModels.value = (result?.items || []).map((r) => ({
        model_id: r.provider_model,
        model_name: r.model_name,
        description: r.description,
        model_type: 'llm',
        features: Object.keys(r.features || {}),
        input_modalities: r.features?.vision ? ['image', 'text'] : ['text'],
      })) as LLMApi.RemoteModelInfo[];
    } else {
      // 新增模式，或编辑模式下强制刷新远程
      modelSource.value = 'remote';
      let result;
      if (editingProvider.value) {
        result = await getRemoteModelsApi(
          editingProvider.value.provider_code,
          'llm',
        );
      } else {
        // 新增模式下使用输入的 URL 和 Key
        if (!formState.base_url || !formState.api_key) {
          message.warning('请先填写 Base URL 和 API Key');
          return;
        }
        result = await fetchRemoteModelsApi({
          api_key: formState.api_key.trim(),
          base_url: formState.base_url.trim(),
          model_type: 'llm',
          provider_type: formState.provider_type,
        });
      }
      editRemoteModels.value = result?.items || [];
    }
  } catch (error: any) {
    console.error('获取模型列表失败:', error);
    message.error(`获取模型列表失败: ${error?.message || '未知错误'}`);
    editRemoteModels.value = [];
  } finally {
    editRemoteModelsLoading.value = false;
  }
}

// 从远程模型添加
function addRemoteModel(modelId: string) {
  if (formState.available_models.includes(modelId)) {
    message.warning('模型已存在');
    return;
  }
  formState.available_models.push(modelId);
}

// 添加所有过滤后的远程模型
function addAllFilteredModels() {
  const toAdd = filteredRemoteModels.value.map((m) => m.model_id);
  const current = new Set(formState.available_models);
  let addedCount = 0;
  toAdd.forEach((id) => {
    if (!current.has(id)) {
      current.add(id);
      addedCount++;
    }
  });
  formState.available_models = [...current];
  if (addedCount > 0) {
    message.success(`成功添加 ${addedCount} 个模型`);
  } else {
    message.info('所选模型已全部在列表中');
  }
}

function handleTableChange(pag: any) {
  pagination.current = pag.current || 1;
  pagination.pageSize = pag.pageSize || pagination.pageSize;
}

// 格式化时间
function formatTime(time: null | string) {
  if (!time) return '-';
  return formatDateTime(time);
}

onMounted(() => {
  fetchProviders();
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
          {{ route.meta.title || 'LLM Provider 配置' }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">搜索</span>
          <Input
            v-model:value="searchText"
            placeholder="搜索编码/名称/模型"
            style="width: 220px"
          />
        </div>
        <div class="filter-actions">
          <Button @click="fetchProviders">🔄 刷新</Button>
          <Button type="primary" @click="handleAdd">➕ 新增 Provider</Button>
        </div>
      </div>
    </div>

    <Card :bordered="false">
      <Table
        :columns="columns"
        :data-source="displayData"
        :loading="loading"
        :pagination="pagination"
        row-key="provider_code"
        size="middle"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'provider_code'">
            <a
              class="provider-code"
              @click="handleView(record as LLMApi.ProviderConfig)"
            >
              {{ record.provider_code }}
            </a>
          </template>
          <template v-else-if="column.key === 'provider_type'">
            <Tag color="blue">
              {{
                providerTypeOptions.find(
                  (o) => o.value === record.provider_type,
                )?.label || record.provider_type
              }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'circuit_state'">
            <template v-if="getCircuitBreaker(record.provider_code)">
              <Tooltip>
                <template #title>
                  <div>
                    <div>
                      失败次数:
                      {{
                        getCircuitBreaker(record.provider_code)?.failure_count
                      }}
                    </div>
                    <div>
                      成功次数:
                      {{
                        getCircuitBreaker(record.provider_code)?.success_count
                      }}
                    </div>
                  </div>
                </template>
                <Badge
                  :status="
                    circuitStateColors[
                      getCircuitBreaker(record.provider_code)!.state
                    ]
                  "
                  :text="
                    circuitStateLabels[
                      getCircuitBreaker(record.provider_code)!.state
                    ]
                  "
                />
              </Tooltip>
            </template>
            <span v-else class="text-muted-foreground">-</span>
          </template>
          <template v-else-if="column.key === 'enabled'">
            <Tag :color="record.enabled ? 'green' : 'red'">
              {{ record.enabled ? '启用' : '禁用' }}
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
                @click="handleEdit(record as LLMApi.ProviderConfig)"
              >
                ✏️ 编辑
              </Button>
              <Button
                type="link"
                size="small"
                :loading="testingProvider === record.provider_code"
                @click="handleTest(record as LLMApi.ProviderConfig)"
              >
                🔗 测试
              </Button>
              <Button
                type="link"
                size="small"
                @click="handleGetRemoteModels(record as LLMApi.ProviderConfig)"
              >
                📦 模型
              </Button>
              <Button
                type="link"
                size="small"
                @click="handleToggleEnabled(record as LLMApi.ProviderConfig)"
              >
                {{ record.enabled ? '🔒 禁用' : '🔓 启用' }}
              </Button>
              <Popconfirm
                v-if="getCircuitBreaker(record.provider_code)?.state === 'open'"
                title="确定要重置熔断器吗？"
                @confirm="handleResetCircuit(record.provider_code)"
              >
                <Button type="link" size="small" danger>⚡ 重置熔断</Button>
              </Popconfirm>
              <Popconfirm
                title="确定要删除此 Provider 吗？"
                description="删除后无法恢复"
                @confirm="handleDelete(record as LLMApi.ProviderConfig)"
              >
                <Button type="link" danger size="small">🗑️ 删除</Button>
              </Popconfirm>
            </Space>
          </template>
        </template>
      </Table>
    </Card>

    <!-- Provider 编辑弹窗 -->
    <Modal
      v-model:open="modalVisible"
      :title="editingProvider ? '编辑 Provider' : '新增 Provider'"
      :width="700"
      :confirm-loading="isSubmitting"
      @ok="handleSubmit"
      @cancel="modalVisible = false"
    >
      <Form :model="formState" layout="vertical">
        <div class="grid grid-cols-2 gap-4">
          <FormItem label="Provider 编码" :rules="[{ required: true }]">
            <Input
              v-model:value="formState.provider_code"
              placeholder="如: openai, aihubmix"
              :disabled="!!editingProvider"
            />
          </FormItem>
          <FormItem label="名称" :rules="[{ required: true }]">
            <Input
              v-model:value="formState.provider_name"
              placeholder="如: OpenAI 官方"
            />
          </FormItem>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <FormItem label="类型" :rules="[{ required: true }]">
            <Select v-model:value="formState.provider_type">
              <SelectOption
                v-for="opt in providerTypeOptions"
                :key="opt.value"
                :value="opt.value"
              >
                {{ opt.label }}
              </SelectOption>
            </Select>
          </FormItem>
          <FormItem label="优先级">
            <InputNumber
              v-model:value="formState.priority"
              :min="0"
              :max="100"
              style="width: 100%"
            />
          </FormItem>
        </div>

        <FormItem label="Base URL" :rules="[{ required: true }]">
          <Input
            v-model:value="formState.base_url"
            placeholder="https://api.openai.com/v1"
          />
          <div class="helper-text">
            {{
              formState.provider_type === 'openai_compatible'
                ? '示例: https://api.openai.com/v1'
                : formState.provider_type === 'anthropic'
                  ? '示例: https://api.anthropic.com/v1'
                  : formState.provider_type === 'azure_openai'
                    ? '示例: https://{resource}.openai.azure.com/openai/deployments/{deployment}/'
                    : '自定义 Provider，请确认接口兼容 /v1'
            }}
          </div>
        </FormItem>

        <FormItem
          :label="editingProvider ? 'API Key (留空保持不变)' : 'API Key'"
          :rules="editingProvider ? [] : [{ required: true }]"
        >
          <Input.Password
            v-model:value="formState.api_key"
            placeholder="sk-xxx..."
          />
        </FormItem>

        <FormItem label="默认参数">
          <div class="params-box">
            <div
              v-if="Object.keys(formState.default_params).length > 0"
              class="params-list"
            >
              <div
                v-for="(val, key) in formState.default_params"
                :key="key as string"
                class="param-item"
              >
                <code class="param-key">{{ key }}</code>
                <span class="param-sep">=</span>
                <code class="param-val">{{
                  typeof val === 'object' ? JSON.stringify(val) : String(val)
                }}</code>
                <Button
                  danger
                  type="link"
                  size="small"
                  @click="delete formState.default_params[key as string]"
                >
                  删除
                </Button>
              </div>
            </div>
            <div class="mt-2">
              <Space>
                <Input
                  v-model:value="_paramKey"
                  placeholder="参数名，如: temperature"
                  style="width: 180px"
                  size="small"
                />
                <Input
                  v-model:value="_paramVal"
                  placeholder="参数值，支持 JSON"
                  style="width: 240px"
                  size="small"
                />
                <Button size="small" @click="addParam">添加</Button>
              </Space>
            </div>
          </div>
        </FormItem>

        <FormItem label="保存后测试连接">
          <Switch
            v-model:checked="testAfterSave"
            checked-children="开启"
            un-checked-children="关闭"
          />
        </FormItem>

        <div class="grid grid-cols-2 gap-4">
          <FormItem label="默认模型">
            <Select
              v-model:value="formState.default_model"
              allow-clear
              show-search
              :options="
                defaultModelOptions.map((m) => ({ value: m, label: m }))
              "
              placeholder="选择或输入模型"
            />
          </FormItem>
          <FormItem label="超时时间 (秒)">
            <InputNumber
              v-model:value="formState.timeout"
              :min="10"
              :max="600"
              style="width: 100%"
            />
          </FormItem>
        </div>

        <FormItem label="可用模型">
          <Select
            v-model:value="formState.available_models"
            mode="tags"
            style="width: 100%"
            placeholder="手动输入或从下方点击添加"
            :token-separators="[',', ' ']"
            show-search
            :options="
              editRemoteModels.map((m) => ({
                value: m.model_id,
                label: m.model_id,
              }))
            "
          />

          <!-- 模型库面板 -->
          <div class="mt-4">
            <div class="remote-models-header flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="font-medium">模型库</span>
                <Tag
                  v-if="editRemoteModels.length > 0"
                  :color="modelSource === 'local' ? 'blue' : 'orange'"
                >
                  {{ modelSource === 'local' ? '本地已同步' : '远程实时获取' }}
                </Tag>
                <Input
                  v-model:value="remoteModelSearchText"
                  placeholder="搜索模型..."
                  size="small"
                  style="width: 160px"
                  allow-clear
                >
                  <template #prefix>
                    <SearchOutlined class="text-muted-foreground" />
                  </template>
                </Input>
                <Button
                  v-if="
                    editingProvider || (formState.base_url && formState.api_key)
                  "
                  type="link"
                  size="small"
                  :loading="editRemoteModelsLoading"
                  @click="fetchModelsForProvider(true)"
                >
                  {{ editRemoteModels.length === 0 ? '获取远程' : '刷新远程' }}
                </Button>
                <Spin v-if="editRemoteModelsLoading" size="small" />
              </div>
              <Button
                v-if="filteredRemoteModels.length > 0"
                type="link"
                size="small"
                @click="addAllFilteredModels"
              >
                添加全部过滤项
              </Button>
            </div>

            <div
              v-if="filteredRemoteModels.length > 0"
              class="remote-models-scroll-box mt-2"
            >
              <Tag
                v-for="m in filteredRemoteModels"
                :key="m.model_id"
                :color="
                  formState.available_models.includes(m.model_id)
                    ? 'green'
                    : 'default'
                "
                class="remote-model-tag"
                @click="addRemoteModel(m.model_id)"
              >
                {{ m.model_id }}
              </Tag>
            </div>
            <div
              v-else-if="!editRemoteModelsLoading"
              class="mt-2 text-center text-muted-foreground"
            >
              {{
                editRemoteModels.length === 0
                  ? editingProvider
                    ? '暂无同步模型，请尝试获取远程'
                    : '输入 URL 和 Key 后点击获取远程模型'
                  : '未找到匹配的模型'
              }}
            </div>
          </div>
        </FormItem>

        <div class="grid grid-cols-2 gap-4">
          <FormItem label="限流 (请求/分钟)">
            <InputNumber
              v-model:value="formState.rate_limit"
              :min="0"
              placeholder="不限制"
              style="width: 100%"
            />
          </FormItem>
          <FormItem label="状态">
            <Switch
              v-model:checked="formState.enabled"
              checked-children="启用"
              un-checked-children="禁用"
            />
          </FormItem>
        </div>

        <FormItem label="描述">
          <Textarea
            v-model:value="formState.description"
            :rows="2"
            placeholder="Provider 描述"
          />
        </FormItem>
      </Form>
    </Modal>

    <!-- Provider 详情抽屉 -->
    <Drawer
      v-model:open="detailVisible"
      :title="`Provider: ${viewingProvider?.provider_code}`"
      :width="600"
      root-class-name="provider-detail-drawer"
    >
      <template v-if="viewingProvider">
        <Descriptions :column="2" bordered size="small">
          <DescriptionsItem label="编码" :span="2">
            <code>{{ viewingProvider.provider_code }}</code>
          </DescriptionsItem>
          <DescriptionsItem label="名称">
            {{ viewingProvider.provider_name }}
          </DescriptionsItem>
          <DescriptionsItem label="类型">
            <Tag color="blue">
              {{
                providerTypeOptions.find(
                  (o) => o.value === viewingProvider!.provider_type,
                )?.label
              }}
            </Tag>
          </DescriptionsItem>
          <DescriptionsItem label="Base URL" :span="2">
            <code>{{ viewingProvider.base_url }}</code>
          </DescriptionsItem>
          <DescriptionsItem label="API Key" :span="2">
            <code>{{ viewingProvider.api_key_masked }}</code>
          </DescriptionsItem>
          <DescriptionsItem label="默认模型">
            {{ viewingProvider.default_model || '-' }}
          </DescriptionsItem>
          <DescriptionsItem label="超时">
            {{ viewingProvider.timeout }}s
          </DescriptionsItem>
          <DescriptionsItem label="优先级">
            {{ viewingProvider.priority }}
          </DescriptionsItem>
          <DescriptionsItem label="状态">
            <Tag :color="viewingProvider.enabled ? 'green' : 'red'">
              {{ viewingProvider.enabled ? '启用' : '禁用' }}
            </Tag>
          </DescriptionsItem>
        </Descriptions>

        <Card title="可用模型" size="small" class="mt-4">
          <Space wrap v-if="viewingProvider.available_models?.length">
            <Tag
              v-for="m in viewingProvider.available_models"
              :key="m"
              color="processing"
            >
              {{ m }}
            </Tag>
          </Space>
          <span v-else class="text-muted-foreground">未配置</span>
        </Card>

        <Card title="默认参数" size="small" class="mt-4">
          <pre
            v-if="
              viewingProvider.default_params &&
              Object.keys(viewingProvider.default_params).length > 0
            "
            class="config-json"
            >{{ JSON.stringify(viewingProvider.default_params, null, 2) }}</pre
          >
          <span v-else class="text-muted-foreground">未配置</span>
        </Card>

        <Card
          title="熔断状态"
          size="small"
          class="mt-4"
          v-if="getCircuitBreaker(viewingProvider.provider_code)"
        >
          <Descriptions :column="2" size="small">
            <DescriptionsItem label="状态">
              <Badge
                :status="
                  circuitStateColors[
                    getCircuitBreaker(viewingProvider.provider_code)!.state
                  ]
                "
                :text="
                  circuitStateLabels[
                    getCircuitBreaker(viewingProvider.provider_code)!.state
                  ]
                "
              />
            </DescriptionsItem>
            <DescriptionsItem label="失败次数">
              {{
                getCircuitBreaker(viewingProvider.provider_code)?.failure_count
              }}
            </DescriptionsItem>
            <DescriptionsItem label="成功次数">
              {{
                getCircuitBreaker(viewingProvider.provider_code)?.success_count
              }}
            </DescriptionsItem>
            <DescriptionsItem label="最后失败时间">
              {{
                formatTime(
                  getCircuitBreaker(viewingProvider.provider_code)
                    ?.last_failure_time || null,
                )
              }}
            </DescriptionsItem>
          </Descriptions>
        </Card>

        <div class="mt-4" v-if="viewingProvider.description">
          <Card title="描述" size="small">
            {{ viewingProvider.description }}
          </Card>
        </div>
      </template>
    </Drawer>

    <!-- 远程模型抽屉 -->
    <Drawer
      v-model:open="remoteModelsVisible"
      :title="`远程模型 - ${remoteModelsProvider?.provider_name}`"
      :width="800"
      root-class-name="remote-models-drawer"
    >
      <template v-if="remoteModelsProvider">
        <div class="remote-models-header">
          <div class="header-info flex items-center gap-4">
            <span>共 {{ remoteModels.length }} 个模型</span>
            <span v-if="drawerModelSearchText" class="text-primary">
              匹配 {{ filteredDrawerModels.length }} 个
            </span>
            <span v-if="selectedModelIds.length > 0">
              已选择 {{ selectedModelIds.length }} 个
            </span>
            <Input
              v-model:value="drawerModelSearchText"
              placeholder="搜索模型 ID 或描述..."
              size="small"
              style="width: 200px"
              allow-clear
            >
              <template #prefix>
                <SearchOutlined class="text-muted-foreground" />
              </template>
            </Input>
            <Button size="small" @click="toggleSortOrder">
              {{
                drawerModelSortOrder === 'none'
                  ? '💰 价格排序'
                  : drawerModelSortOrder === 'asc'
                    ? '💰 价格从低到高'
                    : '💰 价格从高到低'
              }}
            </Button>
          </div>
          <Space>
            <Button size="small" @click="toggleSelectAll">
              {{
                filteredDrawerModels.length > 0 &&
                filteredDrawerModels.every((m) =>
                  selectedModelIds.includes(m.model_id),
                )
                  ? '取消全选'
                  : '全选'
              }}
            </Button>
            <Button
              type="primary"
              size="small"
              :loading="syncingModels"
              :disabled="selectedModelIds.length === 0"
              @click="handleSyncModels"
            >
              同步选中 ({{ selectedModelIds.length }})
            </Button>
            <Popconfirm
              title="确定要同步所有模型吗？"
              description="已存在的模型将被跳过"
              @confirm="handleSyncAllModels"
            >
              <Button size="small" :loading="syncingModels"> 同步全部 </Button>
            </Popconfirm>
          </Space>
        </div>

        <Spin :spinning="remoteModelsLoading">
          <div
            v-if="filteredDrawerModels.length === 0 && !remoteModelsLoading"
            class="empty-tip"
          >
            {{ drawerModelSearchText ? '未找到匹配的模型' : '暂无可用模型' }}
          </div>
          <div v-else class="models-grid">
            <div
              v-for="model in filteredDrawerModels"
              :key="model.model_id"
              class="model-card"
              :class="{ selected: selectedModelIds.includes(model.model_id) }"
              @click="toggleModelSelection(model.model_id)"
            >
              <div class="model-header">
                <div class="model-name">{{ model.model_id }}</div>
                <Tag v-if="model.model_type" color="blue" class="model-type">
                  {{ model.model_type }}
                </Tag>
              </div>
              <div v-if="model.description" class="model-desc">
                {{ model.description.slice(0, 100)
                }}{{ model.description.length > 100 ? '...' : '' }}
              </div>
              <div class="model-meta">
                <span v-if="model.context_length" class="meta-item">
                  📏 {{ (model.context_length / 1000).toFixed(0) }}K
                </span>
                <span v-if="model.max_output" class="meta-item">
                  📤 {{ (model.max_output / 1000).toFixed(0) }}K
                </span>
                <span
                  v-if="model.cost_per_1k_input || model.cost_per_1k_output"
                  class="meta-item"
                >
                  💰 {{ model.currency === 'CNY' ? '¥' : '$'
                  }}{{ model.cost_per_1k_input || '-' }} /
                  {{ model.cost_per_1k_output || '-' }} / 1K
                </span>
              </div>
              <div
                v-if="model.features && model.features.length > 0"
                class="model-features"
              >
                <Tag
                  v-for="f in model.features.slice(0, 4)"
                  :key="f"
                  size="small"
                >
                  {{ f }}
                </Tag>
                <span v-if="model.features.length > 4" class="more-features">
                  +{{ model.features.length - 4 }}
                </span>
              </div>
            </div>
          </div>
        </Spin>
      </template>
    </Drawer>
  </div>
</template>

<style scoped>
.p-4 {
  padding: 16px;
}

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
  color: hsl(var(--muted-foreground));
}

.text-muted-foreground {
  color: hsl(var(--muted-foreground));
}

.mt-2 {
  margin-top: 8px;
}

.mt-4 {
  margin-top: 16px;
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

.provider-code {
  color: hsl(var(--primary));
  cursor: pointer;
}

.provider-code:hover {
  text-decoration: underline;
}

.models-box {
  min-height: 36px;
  padding: 8px 12px;
  background: hsl(var(--muted));
  border-radius: 6px;
}

.remote-models-title {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.remote-models-select {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.remote-models-scroll-box {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-content: flex-start;
  align-items: flex-start;
  max-height: 160px;
  padding: 10px;
  overflow-y: auto;
  background: hsl(var(--background-deep) / 30%);
  border: 1px dashed hsl(var(--border));
  border-radius: 6px;
}

.remote-model-tag {
  cursor: pointer;
  transition: all 0.2s;
}

.remote-model-tag:hover {
  border-color: hsl(var(--primary));
}

.config-json {
  max-height: 200px;
  padding: 12px;
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

.helper-text {
  margin-top: 6px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.params-box {
  padding: 8px 12px;
  background: hsl(var(--muted));
  border-radius: 6px;
}

.params-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.param-item {
  display: flex;
  gap: 8px;
  align-items: center;
}

.param-key {
  color: hsl(var(--primary));
}

.param-sep {
  color: hsl(var(--muted-foreground));
}

.param-val {
  color: hsl(var(--foreground));
}
</style>

<style>
/* Provider 详情抽屉主题适配 */
.provider-detail-drawer .ant-drawer-content {
  background: hsl(var(--background-deep));
}

.provider-detail-drawer .ant-drawer-header {
  background: hsl(var(--card));
  border-bottom: 1px solid hsl(var(--border));
}

.provider-detail-drawer .ant-drawer-title {
  color: hsl(var(--foreground));
}

.provider-detail-drawer .ant-drawer-body {
  background: hsl(var(--background-deep));
}

.provider-detail-drawer
  .ant-descriptions-bordered
  .ant-descriptions-item-label {
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted));
  border-color: hsl(var(--border));
}

.provider-detail-drawer
  .ant-descriptions-bordered
  .ant-descriptions-item-content {
  color: hsl(var(--foreground));
  background: hsl(var(--card));
  border-color: hsl(var(--border));
}

.provider-detail-drawer .ant-card {
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
}

.provider-detail-drawer .ant-card-head {
  background: hsl(var(--muted));
  border-bottom: 1px solid hsl(var(--border));
}

.provider-detail-drawer code {
  padding: 2px 8px;
  font-family: 'Fira Code', Consolas, monospace;
  font-size: 13px;
  color: hsl(var(--primary));
  background: hsl(var(--muted));
  border-radius: 4px;
}

/* 远程模型抽屉样式 */
.remote-models-drawer .ant-drawer-content {
  background: hsl(var(--background-deep));
}

.remote-models-drawer .ant-drawer-header {
  background: hsl(var(--card));
  border-bottom: 1px solid hsl(var(--border));
}

.remote-models-drawer .ant-drawer-title {
  color: hsl(var(--foreground));
}

.remote-models-drawer .ant-drawer-body {
  background: hsl(var(--background-deep));
}

.remote-models-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  margin-bottom: 16px;
  border-bottom: 1px solid hsl(var(--border));
}

.header-info {
  font-size: 14px;
  color: hsl(var(--muted-foreground));
}

.ml-4 {
  margin-left: 16px;
  color: hsl(var(--primary));
}

.empty-tip {
  padding: 40px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 12px;
}

.model-card {
  padding: 14px;
  cursor: pointer;
  background: hsl(var(--card));
  border: 2px solid hsl(var(--border));
  border-radius: 8px;
  transition: all 0.2s ease;
}

.model-card:hover {
  border-color: hsl(var(--primary) / 50%);
}

.model-card.selected {
  background: hsl(var(--primary) / 5%);
  border-color: hsl(var(--primary));
}

.model-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.model-name {
  font-size: 14px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.model-type {
  font-size: 11px;
}

.model-desc {
  margin-bottom: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: hsl(var(--muted-foreground));
}

.model-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 8px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.meta-item {
  display: flex;
  gap: 4px;
  align-items: center;
}

.model-features {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.more-features {
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}
</style>
