<script setup lang="ts">
import type { BanTermApi } from '#/api/core/ban-terms';
import type { TenantApi } from '#/api/core/business';

import { computed, onMounted, reactive, ref } from 'vue';

import { VbenIconButton } from '@vben-core/shadcn-ui';

import { DeleteOutlined, EditOutlined } from '@ant-design/icons-vue';
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
  Switch,
  Table,
  Tag,
} from 'ant-design-vue';

import {
  createBanTermApi,
  deleteBanTermApi,
  getBanTermMetaApi,
  getBanTermOptionsApi,
  listBanTermsApi,
  publishBanTermsApi,
  updateBanTermApi,
} from '#/api/core/ban-terms';
import { getTenantSimpleListApi } from '#/api/core/business';

const loading = ref(false);
const publishing = ref(false);

const meta = ref<BanTermApi.Meta | null>(null);
const options = ref<BanTermApi.Options | null>(null);
const dataSource = ref<BanTermApi.TermItem[]>([]);
const tenantList = ref<TenantApi.SimpleItem[]>([]);

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0,
});

const filters = reactive({
  tenant_code: undefined as string | undefined,
  keyword: '',
  list_type: undefined as BanTermApi.ListType | undefined,
  category: undefined as string | undefined,
  enabled: undefined as '0' | '1' | undefined,
});

// 名单类型标签映射
const listTypeLabelMap: Record<string, string> = {
  WHITELIST: '白名单（安全词）',
  BLACKLIST: '黑名单（违禁词）',
};

// 分类标签映射（可根据需要扩展）
const categoryLabelMap: Record<string, string> = {
  global: '全局 (global)',
  medical: '医疗 (medical)',
  wangyue: '旺玥 (wangyue)',
};

// 动态生成租户选项（用于筛选条件，来自 ban_terms options）
const tenantOptions = computed(() => {
  if (!options.value?.tenant_codes?.length) {
    return [];
  }
  return options.value.tenant_codes.map((t) => ({
    value: t,
    label: t,
  }));
});

// Modal 中的租户选项（用于新建/编辑，来自 DAO 租户列表）
const modalTenantOptions = computed(() => {
  if (tenantList.value.length === 0) {
    return [{ value: 'default', label: 'default' }];
  }
  return tenantList.value.map((t) => ({
    value: t.tenant_code,
    label: `${t.tenant_name} (${t.tenant_code})`,
  }));
});

// 动态生成名单类型选项
const listTypeOptions = computed(() => {
  if (!options.value?.list_types?.length) {
    // 后端未返回时的默认值
    return [
      { value: 'WHITELIST', label: '白名单（安全词）' },
      { value: 'BLACKLIST', label: '黑名单（违禁词）' },
    ];
  }
  return options.value.list_types.map((t) => ({
    value: t,
    label: listTypeLabelMap[t] || t,
  }));
});

// 动态生成分类选项
const categoryOptions = computed(() => {
  if (!options.value?.categories?.length) {
    return [];
  }
  return options.value.categories.map((c) => ({
    value: c,
    label: categoryLabelMap[c] || c,
  }));
});

const enabledOptions = [
  { value: '1', label: '启用' },
  { value: '0', label: '禁用' },
];

const columns = [
  { title: 'ID', dataIndex: 'id', width: 80 },
  { title: '租户', dataIndex: 'tenant_code', key: 'tenant_code', width: 100 },
  { title: '词条', dataIndex: 'term', key: 'term', width: 240 },
  { title: '名单类型', dataIndex: 'list_type', key: 'list_type', width: 140 },
  { title: '分类', dataIndex: 'category', key: 'category', width: 120 },
  { title: '启用', dataIndex: 'enabled', key: 'enabled', width: 80 },
  { title: '创建者', dataIndex: 'created_by', key: 'created_by', width: 100 },
  { title: '修改者', dataIndex: 'updated_by', key: 'updated_by', width: 100 },
  {
    title: '创建时间',
    dataIndex: 'create_time',
    key: 'create_time',
    width: 170,
  },
  {
    title: '更新时间',
    dataIndex: 'update_time',
    key: 'update_time',
    width: 170,
  },
  { title: '操作', key: 'action', width: 140, fixed: 'right' as const },
];

const listTypeTag = (t: BanTermApi.ListType) =>
  t === 'WHITELIST'
    ? { color: 'green', label: '白名单' }
    : { color: 'red', label: '黑名单' };

const modalVisible = ref(false);
const isSubmitting = ref(false);
const editing = ref<BanTermApi.TermItem | null>(null);

const formState = reactive<BanTermApi.CreatePayload>({
  tenant_code: 'default',
  term: '',
  list_type: 'BLACKLIST',
  category: 'global',
  enabled: true,
});

const modalTitle = computed(() => (editing.value ? '编辑词条' : '新增词条'));

async function fetchMeta() {
  try {
    meta.value = await getBanTermMetaApi();
  } catch (error: any) {
    message.error(error?.message || '获取 meta 失败');
  }
}

async function fetchTenantList() {
  try {
    tenantList.value = await getTenantSimpleListApi();
  } catch (error: any) {
    message.error(error?.message || '获取租户列表失败');
  }
}

async function fetchOptions() {
  try {
    options.value = await getBanTermOptionsApi();
  } catch (error: any) {
    message.error(error?.message || '获取筛选选项失败');
  }
}

async function fetchList() {
  loading.value = true;
  try {
    let enabled: boolean | undefined;
    if (filters.enabled === '1') {
      enabled = true;
    } else if (filters.enabled === '0') {
      enabled = false;
    } else {
      enabled = undefined;
    }
    const res = await listBanTermsApi({
      page: pagination.current,
      page_size: pagination.pageSize,
      tenant_code: filters.tenant_code || undefined,
      keyword: filters.keyword || undefined,
      list_type: filters.list_type,
      category: filters.category || undefined,
      enabled,
    });
    dataSource.value = res.items;
    pagination.total = res.page_info.total;
  } catch (error: any) {
    message.error(error?.message || '加载失败');
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  editing.value = null;
  Object.assign(formState, {
    tenant_code: filters.tenant_code || 'default',
    term: '',
    list_type: 'BLACKLIST',
    category: 'global',
    enabled: true,
  });
  modalVisible.value = true;
}

function openEdit(record: any) {
  const r = record as BanTermApi.TermItem;
  editing.value = r;
  Object.assign(formState, {
    tenant_code: r.tenant_code,
    term: r.term,
    list_type: r.list_type,
    category: r.category,
    enabled: r.enabled,
  });
  modalVisible.value = true;
}

async function submit() {
  const term = formState.term.trim();
  if (!term) {
    message.warning('请输入词条');
    return;
  }
  if (!formState.category.trim()) {
    message.warning('请输入分类');
    return;
  }

  isSubmitting.value = true;
  try {
    if (editing.value) {
      await updateBanTermApi(editing.value.id, {
        tenant_code: formState.tenant_code.trim(),
        term,
        list_type: formState.list_type,
        category: formState.category.trim(),
        enabled: formState.enabled,
      });
      message.success('更新成功');
    } else {
      await createBanTermApi({
        tenant_code: formState.tenant_code.trim(),
        term,
        list_type: formState.list_type,
        category: formState.category.trim(),
        enabled: formState.enabled,
      });
      message.success('创建成功');
    }
    modalVisible.value = false;
    await Promise.all([fetchMeta(), fetchOptions()]);
    await fetchList();
  } catch (error: any) {
    message.error(
      error?.response?.data?.message || error?.message || '提交失败',
    );
  } finally {
    isSubmitting.value = false;
  }
}

async function toggleEnabled(record: any, enabled: boolean) {
  const r = record as BanTermApi.TermItem;
  try {
    await updateBanTermApi(r.id, { enabled });
    r.enabled = enabled;
    message.success('已更新');
    await fetchMeta();
  } catch (error: any) {
    message.error(error?.message || '更新失败');
  }
}

async function remove(record: any) {
  const r = record as BanTermApi.TermItem;
  try {
    await deleteBanTermApi(r.id);
    message.success('删除成功');
    await fetchMeta();
    await fetchList();
  } catch (error: any) {
    message.error(error?.message || '删除失败');
  }
}

async function publish() {
  publishing.value = true;
  try {
    await publishBanTermsApi();
    message.success('已发布生效（active_version 已递增）');
    await fetchMeta();
  } catch (error: any) {
    message.error(error?.message || '发布失败');
  } finally {
    publishing.value = false;
  }
}

function onTableChange(p: any) {
  pagination.current = p.current;
  pagination.pageSize = p.pageSize;
  fetchList();
}

function resetFilters() {
  filters.tenant_code = undefined;
  filters.keyword = '';
  filters.list_type = undefined;
  filters.category = undefined;
  filters.enabled = undefined;
  pagination.current = 1;
  fetchList();
}

function onEnabledFilterChange(v: any) {
  filters.enabled = (v as '0' | '1' | undefined) ?? undefined;
  fetchList();
}

function onSwitchChange(record: any, checked: any) {
  toggleEnabled(record, Boolean(checked));
}

onMounted(async () => {
  await Promise.all([fetchMeta(), fetchOptions(), fetchTenantList()]);
  await fetchList();
});
</script>

<template>
  <div class="ban-terms-page">
    <Card :bordered="false" style="margin-bottom: 16px">
      <div class="meta-row">
        <div class="meta-item">
          <div class="meta-title">active_version</div>
          <div class="meta-value">{{ meta?.active_version ?? '-' }}</div>
        </div>
        <div class="meta-item">
          <div class="meta-title">白名单数量</div>
          <div class="meta-value">{{ meta?.whitelist_count ?? '-' }}</div>
        </div>
        <div class="meta-item">
          <div class="meta-title">黑名单数量</div>
          <div class="meta-value">{{ meta?.blacklist_count ?? '-' }}</div>
        </div>
        <div class="meta-actions">
          <Button type="primary" :loading="publishing" @click="publish">
            发布生效
          </Button>
        </div>
      </div>
    </Card>

    <Card :bordered="false">
      <Form layout="inline" style="margin-bottom: 12px">
        <FormItem label="租户">
          <Select
            v-model:value="filters.tenant_code"
            allow-clear
            :options="tenantOptions"
            placeholder="全部"
            show-search
            :filter-option="true"
            style="width: 140px"
            @change="fetchList"
          />
        </FormItem>
        <FormItem label="关键词">
          <Input
            v-model:value="filters.keyword"
            allow-clear
            placeholder="按词条模糊搜索"
            style="width: 180px"
            @press-enter="fetchList"
          />
        </FormItem>
        <FormItem label="名单类型">
          <Select
            v-model:value="filters.list_type"
            allow-clear
            :options="listTypeOptions"
            placeholder="全部"
            show-search
            :filter-option="true"
            style="width: 180px"
            @change="fetchList"
          />
        </FormItem>
        <FormItem label="分类">
          <Select
            v-model:value="filters.category"
            allow-clear
            :options="categoryOptions"
            placeholder="全部"
            show-search
            :filter-option="true"
            style="width: 180px"
            @change="fetchList"
          />
        </FormItem>
        <FormItem label="启用">
          <Select
            v-model:value="filters.enabled"
            allow-clear
            :options="enabledOptions"
            placeholder="全部"
            style="width: 120px"
            @change="onEnabledFilterChange"
          />
        </FormItem>
        <FormItem>
          <Space>
            <Button type="primary" @click="fetchList">查询</Button>
            <Button @click="resetFilters">重置</Button>
            <Button type="dashed" @click="openCreate">新增词条</Button>
          </Space>
        </FormItem>
      </Form>

      <Table
        :columns="columns"
        :data-source="dataSource"
        :loading="loading"
        row-key="id"
        :scroll="{ x: 1600 }"
        :pagination="{
          current: pagination.current,
          pageSize: pagination.pageSize,
          total: pagination.total,
          showSizeChanger: true,
          showTotal: (t: number) => `共 ${t} 条`,
        }"
        @change="onTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'list_type'">
            <Tag :color="listTypeTag(record.list_type).color">
              {{ listTypeTag(record.list_type).label }}
            </Tag>
            <span style="margin-left: 6px; color: hsl(var(--muted-foreground))">
              {{ record.list_type }}
            </span>
          </template>
          <template v-else-if="column.key === 'enabled'">
            <Switch
              :checked="record.enabled"
              checked-children="启用"
              un-checked-children="禁用"
              @change="(checked: any) => onSwitchChange(record, checked)"
            />
          </template>
          <template v-else-if="column.key === 'action'">
            <div class="action-buttons">
              <VbenIconButton
                tooltip="编辑"
                class="action-btn"
                @click="() => openEdit(record)"
              >
                <EditOutlined />
              </VbenIconButton>
              <Popconfirm title="确定删除该词条？" @confirm="remove(record)">
                <VbenIconButton
                  tooltip="删除"
                  class="action-btn action-btn-danger"
                >
                  <DeleteOutlined />
                </VbenIconButton>
              </Popconfirm>
            </div>
          </template>
        </template>
      </Table>
    </Card>

    <Modal
      v-model:open="modalVisible"
      :confirm-loading="isSubmitting"
      :title="modalTitle"
      @ok="submit"
    >
      <Form layout="vertical">
        <FormItem label="租户">
          <Select
            v-model:value="formState.tenant_code"
            :options="modalTenantOptions"
            placeholder="请选择租户"
            show-search
            :filter-option="true"
            style="width: 100%"
            :get-popup-container="(trigger) => trigger.parentElement"
          />
        </FormItem>
        <FormItem label="词条">
          <Input v-model:value="formState.term" placeholder="例如：免疫力" />
        </FormItem>
        <FormItem label="名单类型">
          <Select
            v-model:value="formState.list_type"
            :options="listTypeOptions"
            show-search
            :filter-option="true"
            :get-popup-container="(trigger) => trigger.parentElement"
          />
        </FormItem>
        <FormItem label="分类">
          <Select
            v-model:value="formState.category"
            :options="categoryOptions"
            placeholder="请选择分类"
            show-search
            :filter-option="true"
            style="width: 100%"
            :get-popup-container="(trigger) => trigger.parentElement"
          />
        </FormItem>
        <FormItem label="启用">
          <Switch
            v-model:checked="formState.enabled"
            checked-children="启用"
            un-checked-children="禁用"
          />
        </FormItem>
      </Form>
    </Modal>
  </div>
</template>

<style scoped>
.ban-terms-page {
  padding: 16px;
}

.meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
}

.meta-item {
  min-width: 160px;
  padding: 12px 14px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.meta-title {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.meta-value {
  margin-top: 4px;
  font-size: 18px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.meta-actions {
  margin-left: auto;
}

/* 操作按钮样式 - 使用 VbenIconButton */
.action-buttons {
  display: flex;
  gap: 4px;
}

.action-btn {
  font-size: 15px;
}

.action-btn-danger {
  color: hsl(var(--destructive)) !important;
}

.action-btn-danger:hover {
  background: hsl(var(--destructive) / 15%) !important;
}
</style>
