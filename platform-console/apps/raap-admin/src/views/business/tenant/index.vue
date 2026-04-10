<script setup lang="ts">
import type { TenantApi } from '#/api/core/business';

import { onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';

import {
  Button,
  Card,
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import {
  createTenantApi,
  deleteTenantApi,
  getTenantListApi,
  updateTenantApi,
} from '#/api/core/business';

const route = useRoute();

const loading = ref(false);
const dataSource = ref<TenantApi.Tenant[]>([]);
const total = ref(0);
const searchKeyword = ref('');
const statusFilter = ref<string | undefined>(undefined);
const pagination = ref({
  current: 1,
  pageSize: 10,
  showSizeChanger: true,
  showTotal: (t: number) => `共 ${t} 条`,
});

// 状态配置
const statusConfig: Record<
  TenantApi.TenantStatus,
  { color: string; label: string }
> = {
  ACTIVE: { label: '正常', color: 'success' },
  INACTIVE: { label: '未激活', color: 'default' },
  SUSPENDED: { label: '已暂停', color: 'warning' },
};

const statusOptions = [
  { label: '正常', value: 'ACTIVE' },
  { label: '未激活', value: 'INACTIVE' },
  { label: '已暂停', value: 'SUSPENDED' },
];

const columns = [
  {
    title: '租户编码',
    dataIndex: 'tenant_code',
    key: 'tenant_code',
    width: 150,
  },
  {
    title: '租户名称',
    dataIndex: 'tenant_name',
    key: 'tenant_name',
    width: 180,
  },
  {
    title: '联系人',
    dataIndex: 'contact_name',
    key: 'contact_name',
    width: 100,
  },
  {
    title: '联系电话',
    dataIndex: 'contact_phone',
    key: 'contact_phone',
    width: 130,
  },
  {
    title: 'Access Key',
    dataIndex: 'access_key',
    key: 'access_key',
    width: 180,
    ellipsis: true,
  },
  { title: '状态', dataIndex: 'status', key: 'status', width: 100 },
  {
    title: '创建时间',
    dataIndex: 'create_time',
    key: 'create_time',
    width: 170,
  },
  { title: '操作', key: 'action', width: 150, fixed: 'right' as const },
];

async function fetchData() {
  loading.value = true;
  try {
    const params: Record<string, any> = {
      skip: (pagination.value.current - 1) * pagination.value.pageSize,
      limit: pagination.value.pageSize,
    };
    if (statusFilter.value) params.status = statusFilter.value;
    if (searchKeyword.value) params.keyword = searchKeyword.value;

    const response = await getTenantListApi(params);
    dataSource.value = response.items || [];
    total.value = response.total || 0;
  } catch {
    message.error('获取租户列表失败');
  } finally {
    loading.value = false;
  }
}

function handleTableChange(pag: any) {
  pagination.value.current = pag.current || 1;
  pagination.value.pageSize = pag.pageSize || 10;
  fetchData();
}

function handleSearch() {
  pagination.value.current = 1;
  fetchData();
}

function handleReset() {
  searchKeyword.value = '';
  statusFilter.value = undefined;
  pagination.value.current = 1;
  fetchData();
}

// 表单弹窗
const modalVisible = ref(false);
const modalLoading = ref(false);
const modalTitle = ref('创建租户');
const editingId = ref<null | number>(null);
const formState = ref<TenantApi.CreateParams>({
  tenant_code: '',
  tenant_name: '',
  contact_name: '',
  contact_phone: '',
  contact_email: '',
  status: 'ACTIVE',
  remark: '',
});

// 密钥弹窗
const keysModalVisible = ref(false);
const currentKeys = ref<{
  access_key: string;
  secret_key: string;
  tenant_name: string;
}>({
  tenant_name: '',
  access_key: '',
  secret_key: '',
});

function showKeys(record: TenantApi.Tenant) {
  currentKeys.value = {
    tenant_name: record.tenant_name,
    access_key: record.access_key || '',
    secret_key: record.secret_key || '',
  };
  keysModalVisible.value = true;
}

function handleCopy(text: string) {
  if (!text) return;
  navigator.clipboard
    .writeText(text)
    .then(() => {
      message.success('复制成功');
    })
    .catch(() => {
      message.error('复制失败');
    });
}

function openCreateModal() {
  editingId.value = null;
  modalTitle.value = '创建租户';
  formState.value = {
    tenant_code: '',
    tenant_name: '',
    contact_name: '',
    contact_phone: '',
    contact_email: '',
    status: 'ACTIVE',
    remark: '',
  };
  modalVisible.value = true;
}

function openEditModal(record: TenantApi.Tenant) {
  editingId.value = record.id;
  modalTitle.value = '编辑租户';
  formState.value = {
    tenant_code: record.tenant_code,
    tenant_name: record.tenant_name,
    contact_name: record.contact_name || '',
    contact_phone: record.contact_phone || '',
    contact_email: record.contact_email || '',
    status: record.status,
    remark: record.remark || '',
  };
  modalVisible.value = true;
}

async function handleSubmit() {
  if (!formState.value.tenant_code || !formState.value.tenant_name) {
    message.warning('请填写必填字段');
    return;
  }

  modalLoading.value = true;
  try {
    if (editingId.value) {
      await updateTenantApi(editingId.value, formState.value);
      message.success('更新成功');
    } else {
      await createTenantApi(formState.value);
      message.success('创建成功');
    }
    modalVisible.value = false;
    fetchData();
  } catch {
    message.error(editingId.value ? '更新失败' : '创建失败');
  } finally {
    modalLoading.value = false;
  }
}

async function handleDelete(record: TenantApi.Tenant) {
  try {
    await deleteTenantApi(record.id);
    message.success('删除成功');
    fetchData();
  } catch {
    message.error('删除失败');
  }
}

onMounted(() => {
  fetchData();
});
</script>

<template>
  <div class="tenant-page">
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
          {{ route.meta.title || '租户管理' }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">名称/编码</span>
          <Input
            v-model:value="searchKeyword"
            placeholder="搜索租户名称/编码"
            style="width: 180px"
            allow-clear
            @press-enter="handleSearch"
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">状态</span>
          <Select
            v-model:value="statusFilter"
            :options="statusOptions"
            placeholder="状态筛选"
            style="width: 120px"
            allow-clear
            @change="handleSearch"
          />
        </div>
        <div class="filter-actions">
          <Button @click="handleReset">重置</Button>
          <Button type="primary" @click="openCreateModal">➕ 创建租户</Button>
        </div>
      </div>
    </div>

    <Card :bordered="false">
      <Table
        :columns="columns"
        :data-source="dataSource"
        :loading="loading"
        :pagination="{ ...pagination, total }"
        :scroll="{ x: 1000 }"
        row-key="id"
        size="middle"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record: rawRecord }">
          <template v-if="column.key === 'status'">
            <Tag
              :color="
                statusConfig[(rawRecord as TenantApi.Tenant).status]?.color ||
                'default'
              "
            >
              {{
                statusConfig[(rawRecord as TenantApi.Tenant).status]?.label ||
                (rawRecord as TenantApi.Tenant).status
              }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'action'">
            <Space :size="0">
              <Tooltip title="查看密钥">
                <Button
                  type="link"
                  size="small"
                  @click="showKeys(rawRecord as TenantApi.Tenant)"
                >
                  🔑
                </Button>
              </Tooltip>
              <Tooltip title="编辑">
                <Button
                  type="link"
                  size="small"
                  @click="openEditModal(rawRecord as TenantApi.Tenant)"
                >
                  ✏️
                </Button>
              </Tooltip>
              <Popconfirm
                title="确定要删除此租户吗？"
                ok-text="确定"
                cancel-text="取消"
                @confirm="handleDelete(rawRecord as TenantApi.Tenant)"
              >
                <Tooltip title="删除">
                  <Button type="link" danger size="small"> 🗑️ </Button>
                </Tooltip>
              </Popconfirm>
            </Space>
          </template>
        </template>
      </Table>
    </Card>

    <!-- 密钥弹窗 -->
    <Modal
      v-model:open="keysModalVisible"
      :title="`租户密钥: ${currentKeys.tenant_name}`"
      :footer="null"
      :width="600"
    >
      <div style="padding: 16px">
        <div style="display: flex; align-items: center; margin-bottom: 16px">
          <span
            style="
              width: 100px;
              font-weight: bold;
              color: hsl(var(--foreground));
            "
            >Access Key:</span
          >
          <div
            style="
              display: flex;
              flex: 1;
              align-items: center;
              padding: 8px;
              background: hsl(var(--muted) / 30%);
              border: 1px solid hsl(var(--border));
              border-radius: 4px;
            "
          >
            <code
              style="
                flex: 1;
                margin-right: 8px;
                word-break: break-all;
                background: transparent;
                border: none;
              "
              >{{ currentKeys.access_key || '未配置' }}</code
            >
            <Button
              type="text"
              size="small"
              @click="handleCopy(currentKeys.access_key)"
            >
              📋
            </Button>
          </div>
        </div>
        <div style="display: flex; align-items: center; margin-bottom: 8px">
          <span
            style="
              width: 100px;
              font-weight: bold;
              color: hsl(var(--foreground));
            "
            >Secret Key:</span
          >
          <div
            style="
              display: flex;
              flex: 1;
              align-items: center;
              padding: 8px;
              background: hsl(var(--muted) / 30%);
              border: 1px solid hsl(var(--border));
              border-radius: 4px;
            "
          >
            <code
              style="
                flex: 1;
                margin-right: 8px;
                word-break: break-all;
                background: transparent;
                border: none;
              "
              >{{ currentKeys.secret_key || '未配置' }}</code
            >
            <Button
              type="text"
              size="small"
              @click="handleCopy(currentKeys.secret_key)"
            >
              📋
            </Button>
          </div>
        </div>
        <div
          style="
            margin-top: 16px;
            font-size: 12px;
            color: hsl(var(--muted-foreground));
          "
        >
          ⚠️ Secret Key 仅在此显示，请妥善保管。如需重置，请联系管理员。
        </div>
      </div>
    </Modal>

    <!-- 创建/编辑弹窗 -->
    <Modal
      v-model:open="modalVisible"
      :title="modalTitle"
      :confirm-loading="modalLoading"
      :width="500"
      @ok="handleSubmit"
    >
      <Form :label-col="{ span: 5 }" :wrapper-col="{ span: 18 }">
        <FormItem label="租户编码" required>
          <Input
            v-model:value="formState.tenant_code"
            placeholder="请输入唯一编码"
            :disabled="!!editingId"
          />
        </FormItem>
        <FormItem label="租户名称" required>
          <Input
            v-model:value="formState.tenant_name"
            placeholder="请输入租户名称"
          />
        </FormItem>
        <FormItem label="联系人">
          <Input
            v-model:value="formState.contact_name"
            placeholder="请输入联系人姓名"
          />
        </FormItem>
        <FormItem label="联系电话">
          <Input
            v-model:value="formState.contact_phone"
            placeholder="请输入联系电话"
          />
        </FormItem>
        <FormItem label="联系邮箱">
          <Input
            v-model:value="formState.contact_email"
            placeholder="请输入联系邮箱"
          />
        </FormItem>
        <FormItem label="状态">
          <Select
            v-model:value="formState.status"
            :options="statusOptions"
            placeholder="请选择状态"
            :get-popup-container="(trigger) => trigger.parentElement"
          />
        </FormItem>
        <FormItem label="备注">
          <Input.TextArea
            v-model:value="formState.remark"
            placeholder="请输入备注"
            :rows="2"
          />
        </FormItem>
      </Form>
    </Modal>
  </div>
</template>

<style scoped>
.tenant-page {
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

:deep(.ant-card-head) {
  border-bottom: 1px solid hsl(var(--border));
}

:deep(.ant-table-thead > tr > th) {
  background: hsl(var(--muted));
}
</style>
