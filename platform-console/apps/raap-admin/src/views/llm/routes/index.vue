<script setup lang="ts">
import type { LLMApi } from '#/api/core/llm';

import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';

import {
  Button,
  Card,
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
  Switch,
  Table,
  Tag,
} from 'ant-design-vue';

import {
  createRouteApi,
  deleteRouteApi,
  getProviderListApi,
  getRouteListApi,
  updateRouteApi,
} from '#/api/core/llm';

const route = useRoute();

// 状态
const loading = ref(false);
const dataSource = ref<LLMApi.ModelRoute[]>([]);
const providers = ref<LLMApi.ProviderConfig[]>([]);
const modalVisible = ref(false);
const editingRoute = ref<LLMApi.ModelRoute | null>(null);
const isSubmitting = ref(false);
const pagination = reactive({
  current: 1,
  pageSize: 15,
  showSizeChanger: true,
  pageSizeOptions: ['10', '15', '20', '50', '100'],
  showTotal: (total: number) => `共 ${total} 条`,
});

// 筛选
const filterModelCode = ref('');
const filterProviderCode = ref('');
function handleTableChange(pag: any) {
  pagination.current = pag.current || 1;
  pagination.pageSize = pag.pageSize || pagination.pageSize;
}

// 表单状态
const formState = reactive({
  model_code: '',
  model_name: '',
  provider_code: '',
  provider_model: '',
  priority: 100,
  enabled: true,
  max_context_length: undefined as number | undefined,
  features: {
    vision: false,
    json_mode: false,
    function_calling: false,
  },
  cost_per_1k_input: undefined as number | undefined,
  cost_per_1k_output: undefined as number | undefined,
  currency: 'USD',
  timeout_seconds: undefined as number | undefined,
  description: '',
});

// 表格列定义
const columns = [
  { title: '模型编码', dataIndex: 'model_code', key: 'model_code', width: 150 },
  { title: '模型名称', dataIndex: 'model_name', key: 'model_name', width: 150 },
  {
    title: 'Provider',
    dataIndex: 'provider_code',
    key: 'provider_code',
    width: 120,
  },
  {
    title: 'Provider 模型',
    dataIndex: 'provider_model',
    key: 'provider_model',
    width: 180,
  },
  { title: '优先级', dataIndex: 'priority', key: 'priority', width: 80 },
  { title: '成本', key: 'cost', width: 150 },
  { title: '特性', key: 'features', width: 180 },
  { title: '状态', dataIndex: 'enabled', key: 'enabled', width: 80 },
  { title: '操作', key: 'action', width: 180 },
];

// 获取路由列表
async function fetchRoutes() {
  loading.value = true;
  try {
    const res = await getRouteListApi({
      model_code: filterModelCode.value || undefined,
      provider_code: filterProviderCode.value || undefined,
    });
    dataSource.value = res?.items || [];
  } catch (error) {
    console.error('获取模型路由列表失败:', error);
    message.error('获取模型路由列表失败');
  } finally {
    loading.value = false;
  }
}

// 获取 Provider 列表
async function fetchProviders() {
  try {
    const res = await getProviderListApi({ enabled: true });
    providers.value = res?.items || [];
  } catch (error) {
    console.error('获取 Provider 列表失败:', error);
  }
}

// 重置表单
function resetForm() {
  formState.model_code = '';
  formState.model_name = '';
  formState.provider_code = '';
  formState.provider_model = '';
  formState.priority = 100;
  formState.enabled = true;
  formState.max_context_length = undefined;
  formState.features = {
    vision: false,
    json_mode: false,
    function_calling: false,
  };
  formState.cost_per_1k_input = undefined;
  formState.cost_per_1k_output = undefined;
  formState.currency = 'USD';
  formState.timeout_seconds = undefined;
  formState.description = '';
}

// 新增
function handleAdd() {
  editingRoute.value = null;
  resetForm();
  modalVisible.value = true;
}

// 编辑
function handleEdit(record: LLMApi.ModelRoute) {
  editingRoute.value = record;
  formState.model_code = record.model_code;
  formState.model_name = record.model_name;
  formState.provider_code = record.provider_code;
  formState.provider_model = record.provider_model;
  formState.priority = record.priority;
  formState.enabled = record.enabled;
  formState.max_context_length = record.max_context_length;
  formState.features = {
    vision: record.features?.vision || false,
    json_mode: record.features?.json_mode || false,
    function_calling: record.features?.function_calling || false,
  };
  formState.cost_per_1k_input = record.cost_per_1k_input
    ? Number.parseFloat(record.cost_per_1k_input)
    : undefined;
  formState.cost_per_1k_output = record.cost_per_1k_output
    ? Number.parseFloat(record.cost_per_1k_output)
    : undefined;
  formState.currency = record.currency || 'USD';
  formState.timeout_seconds = record.timeout_seconds;
  formState.description = record.description || '';
  modalVisible.value = true;
}

// 删除
async function handleDelete(record: LLMApi.ModelRoute) {
  try {
    await deleteRouteApi(record.id);
    message.success('删除成功');
    fetchRoutes();
  } catch {
    message.error('删除失败');
  }
}

// 快速切换启用状态
async function handleToggleEnabled(record: LLMApi.ModelRoute) {
  try {
    await updateRouteApi(record.id, { enabled: !record.enabled });
    message.success(record.enabled ? '已禁用' : '已启用');
    fetchRoutes();
  } catch {
    message.error('操作失败');
  }
}

// 提交表单
async function handleSubmit() {
  if (!formState.model_code.trim()) {
    message.error('请输入模型编码');
    return;
  }
  if (!formState.model_name.trim()) {
    message.error('请输入模型名称');
    return;
  }
  if (!formState.provider_code) {
    message.error('请选择 Provider');
    return;
  }
  if (!formState.provider_model.trim()) {
    message.error('请输入 Provider 模型');
    return;
  }

  isSubmitting.value = true;
  try {
    const features = {
      vision: formState.features.vision,
      json_mode: formState.features.json_mode,
      function_calling: formState.features.function_calling,
    };

    if (editingRoute.value) {
      // 更新
      await updateRouteApi(editingRoute.value.id, {
        model_name: formState.model_name.trim(),
        provider_model: formState.provider_model.trim(),
        priority: formState.priority,
        enabled: formState.enabled,
        max_context_length: formState.max_context_length,
        features,
        cost_per_1k_input: formState.cost_per_1k_input,
        cost_per_1k_output: formState.cost_per_1k_output,
        currency: formState.currency,
        timeout_seconds: formState.timeout_seconds,
        description: formState.description.trim() || undefined,
      });
      message.success('更新成功');
    } else {
      // 创建
      await createRouteApi({
        model_code: formState.model_code.trim(),
        model_name: formState.model_name.trim(),
        provider_code: formState.provider_code,
        provider_model: formState.provider_model.trim(),
        priority: formState.priority,
        enabled: formState.enabled,
        max_context_length: formState.max_context_length,
        features,
        cost_per_1k_input: formState.cost_per_1k_input,
        cost_per_1k_output: formState.cost_per_1k_output,
        currency: formState.currency,
        timeout_seconds: formState.timeout_seconds,
        description: formState.description.trim() || undefined,
      });
      message.success('创建成功');
    }
    await fetchRoutes();
    modalVisible.value = false;
  } catch (error: any) {
    const errorMsg =
      error?.response?.data?.detail ||
      (editingRoute.value ? '更新失败' : '创建失败');
    message.error(errorMsg);
  } finally {
    isSubmitting.value = false;
  }
}

// 格式化成本
function formatCost(
  input: string | undefined,
  output: string | undefined,
  currency: string = 'USD',
): string {
  if (!input && !output) return '-';
  const symbol = currency === 'CNY' ? '¥' : '$';
  const i = input ? `${symbol}${input}` : '-';
  const o = output ? `${symbol}${output}` : '-';
  return `${i} / ${o}`;
}

// 获取唯一模型编码列表（用于筛选）
const modelCodeOptions = computed(() => {
  const codes = new Set(dataSource.value.map((r) => r.model_code));
  return [...codes].map((code) => ({ value: code, label: code }));
});

// Provider 选项
const providerOptions = computed(() => {
  return providers.value.map((p) => ({
    value: p.provider_code,
    label: `${p.provider_name} (${p.provider_code})`,
  }));
});

onMounted(() => {
  fetchRoutes();
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
          {{ route.meta.title || '模型路由配置' }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">模型</span>
          <Select
            v-model:value="filterModelCode"
            placeholder="筛选模型"
            style="width: 200px"
            allow-clear
            show-search
            :options="modelCodeOptions"
            @change="fetchRoutes"
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">Provider</span>
          <Select
            v-model:value="filterProviderCode"
            placeholder="筛选 Provider"
            style="width: 200px"
            allow-clear
            show-search
            :options="providerOptions"
            @change="fetchRoutes"
          />
        </div>
        <div class="filter-actions">
          <Button @click="fetchRoutes">🔄 刷新</Button>
          <Button type="primary" @click="handleAdd">➕ 新增路由</Button>
        </div>
      </div>
    </div>

    <Card :bordered="false">
      <Table
        :columns="columns"
        :data-source="dataSource"
        :loading="loading"
        :pagination="pagination"
        row-key="id"
        size="middle"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'model_code'">
            <Tag color="blue">{{ record.model_code }}</Tag>
          </template>
          <template v-else-if="column.key === 'provider_code'">
            <Tag color="purple">{{ record.provider_code }}</Tag>
          </template>
          <template v-else-if="column.key === 'cost'">
            <span class="cost-text">
              {{
                formatCost(
                  record.cost_per_1k_input,
                  record.cost_per_1k_output,
                  record.currency,
                )
              }}
            </span>
          </template>
          <template v-else-if="column.key === 'features'">
            <Space size="small">
              <Tag v-if="record.features?.vision" color="cyan">视觉</Tag>
              <Tag v-if="record.features?.json_mode" color="orange">JSON</Tag>
              <Tag v-if="record.features?.function_calling" color="geekblue">
                函数调用
              </Tag>
              <span
                v-if="
                  !record.features?.vision &&
                  !record.features?.json_mode &&
                  !record.features?.function_calling
                "
                class="text-gray-400"
                >-</span
              >
            </Space>
          </template>
          <template v-else-if="column.key === 'enabled'">
            <Tag :color="record.enabled ? 'green' : 'red'">
              {{ record.enabled ? '启用' : '禁用' }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'action'">
            <Space>
              <Button
                type="link"
                size="small"
                @click="handleEdit(record as LLMApi.ModelRoute)"
              >
                ✏️ 编辑
              </Button>
              <Button
                type="link"
                size="small"
                @click="handleToggleEnabled(record as LLMApi.ModelRoute)"
              >
                {{ record.enabled ? '🔒 禁用' : '🔓 启用' }}
              </Button>
              <Popconfirm
                title="确定要删除此路由吗？"
                description="删除后无法恢复"
                @confirm="handleDelete(record as LLMApi.ModelRoute)"
              >
                <Button type="link" danger size="small">🗑️ 删除</Button>
              </Popconfirm>
            </Space>
          </template>
        </template>
      </Table>
    </Card>

    <!-- 路由编辑弹窗 -->
    <Modal
      v-model:open="modalVisible"
      :title="editingRoute ? '编辑模型路由' : '新增模型路由'"
      :width="700"
      :confirm-loading="isSubmitting"
      @ok="handleSubmit"
      @cancel="modalVisible = false"
    >
      <Form :model="formState" layout="vertical">
        <div class="grid grid-cols-2 gap-4">
          <FormItem label="模型编码" :rules="[{ required: true }]">
            <Input
              v-model:value="formState.model_code"
              placeholder="如: deepseek-v4-flash"
              :disabled="!!editingRoute"
            />
          </FormItem>
          <FormItem label="模型名称" :rules="[{ required: true }]">
            <Input
              v-model:value="formState.model_name"
              placeholder="如: DeepSeek V4 Flash"
            />
          </FormItem>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <FormItem label="Provider" :rules="[{ required: true }]">
            <Select
              v-model:value="formState.provider_code"
              placeholder="选择 Provider"
              :disabled="!!editingRoute"
              show-search
              :options="providerOptions"
            />
          </FormItem>
          <FormItem label="Provider 模型" :rules="[{ required: true }]">
            <Input
              v-model:value="formState.provider_model"
              placeholder="Provider 实际模型名"
            />
          </FormItem>
        </div>

        <div class="grid grid-cols-3 gap-4">
          <FormItem label="优先级">
            <InputNumber
              v-model:value="formState.priority"
              :min="0"
              :max="100"
              style="width: 100%"
            />
          </FormItem>
          <FormItem label="上下文长度">
            <InputNumber
              v-model:value="formState.max_context_length"
              :min="1000"
              placeholder="如: 128000"
              style="width: 100%"
            />
          </FormItem>
          <FormItem label="超时 (秒)">
            <InputNumber
              v-model:value="formState.timeout_seconds"
              :min="10"
              :max="600"
              style="width: 100%"
            />
          </FormItem>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <FormItem label="币种">
            <Select v-model:value="formState.currency" placeholder="选择币种">
              <SelectOption value="USD">USD ($)</SelectOption>
              <SelectOption value="CNY">CNY (¥)</SelectOption>
            </Select>
          </FormItem>
          <div class="grid grid-cols-2 gap-4">
            <FormItem
              :label="`输入成本 (${formState.currency}/1K)`"
              class="mb-0"
            >
              <InputNumber
                v-model:value="formState.cost_per_1k_input"
                :min="0"
                :step="0.0001"
                :precision="6"
                style="width: 100%"
              />
            </FormItem>
            <FormItem
              :label="`输出成本 (${formState.currency}/1K)`"
              class="mb-0"
            >
              <InputNumber
                v-model:value="formState.cost_per_1k_output"
                :min="0"
                :step="0.0001"
                :precision="6"
                style="width: 100%"
              />
            </FormItem>
          </div>
        </div>

        <FormItem label="模型特性">
          <Space size="large">
            <Switch
              v-model:checked="formState.features.vision"
              checked-children="视觉"
              un-checked-children="视觉"
            />
            <Switch
              v-model:checked="formState.features.json_mode"
              checked-children="JSON模式"
              un-checked-children="JSON模式"
            />
            <Switch
              v-model:checked="formState.features.function_calling"
              checked-children="函数调用"
              un-checked-children="函数调用"
            />
          </Space>
        </FormItem>

        <div class="grid grid-cols-2 gap-4">
          <FormItem label="状态">
            <Switch
              v-model:checked="formState.enabled"
              checked-children="启用"
              un-checked-children="禁用"
            />
          </FormItem>
        </div>

        <FormItem label="描述">
          <Input v-model:value="formState.description" placeholder="路由描述" />
        </FormItem>
      </Form>
    </Modal>
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
  color: #9ca3af;
}

.grid {
  display: grid;
}

.grid-cols-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.grid-cols-3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.gap-4 {
  gap: 16px;
}

.cost-text {
  font-family: 'Fira Code', Consolas, monospace;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}
</style>
