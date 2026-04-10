<script setup lang="ts">
import type { TestSetApi } from '#/api/core/test-sets';

import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import { VbenButton as VButton } from '@vben-core/shadcn-ui';

import {
  DeleteOutlined,
  EditOutlined,
  FileImageOutlined,
  FileTextOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue';
import {
  Button,
  Empty,
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Textarea,
  Tooltip,
} from 'ant-design-vue';

import {
  createTestSetApi,
  deleteTestSetApi,
  listTestSetsApi,
  toggleTestSetEnabledApi,
  updateTestSetApi,
} from '#/api/core/test-sets';

const router = useRouter();

// ==================== 状态 ====================

const loading = ref(false);
const dataSource = ref<TestSetApi.TestSetItem[]>([]);

// 数据更新时间
const lastUpdateTime = ref<string>('');

// 格式化当前时间：YYYY-MM-DD HH:mm:ss
const formatCurrentTime = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
};

// 监听数据源变化更新时间
watch(
  dataSource,
  () => {
    if (dataSource.value.length > 0) {
      lastUpdateTime.value = formatCurrentTime(new Date());
    }
  },
  { immediate: true },
);

const pagination = reactive({
  current: 1,
  pageSize: 12,
  total: 0,
});

const filters = reactive({
  keyword: '',
  type: undefined as 'image' | 'text' | undefined,
  enabled: undefined as '0' | '1' | undefined,
});

const typeOptions = [
  { value: 'text', label: '文本' },
  { value: 'image', label: '图片' },
];

const enabledOptions = [
  { value: '1', label: '启用' },
  { value: '0', label: '禁用' },
];

// ==================== 表单弹窗 ====================

const modalVisible = ref(false);
const isSubmitting = ref(false);
const editing = ref<null | TestSetApi.TestSetItem>(null);

const formState = reactive<TestSetApi.CreateRequest>({
  code: '',
  name: '',
  type: 'text',
  description: '',
  enabled: 1,
});

const modalTitle = computed(() =>
  editing.value ? '编辑测试集' : '新建测试集',
);

// ==================== API 调用 ====================

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
    const res = await listTestSetsApi({
      page: pagination.current,
      page_size: pagination.pageSize,
      keyword: filters.keyword || undefined,
      type: filters.type || undefined,
      enabled,
    });
    dataSource.value = res.items;
    pagination.total = res.total;
  } catch (error: unknown) {
    message.error((error as Error)?.message || '加载失败');
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  editing.value = null;
  Object.assign(formState, {
    code: '',
    name: '',
    type: 'text',
    description: '',
    enabled: 1,
  });
  modalVisible.value = true;
}

function openEdit(record: TestSetApi.TestSetItem, e: Event) {
  e.stopPropagation();
  editing.value = record;
  Object.assign(formState, {
    code: record.code,
    name: record.name,
    type: record.type,
    description: record.description || '',
    enabled: record.enabled,
  });
  modalVisible.value = true;
}

async function submit() {
  const name = formState.name.trim();

  if (!name) {
    message.warning('请输入测试集名称');
    return;
  }

  isSubmitting.value = true;
  try {
    if (editing.value) {
      await updateTestSetApi(editing.value.id, {
        name,
        description: formState.description?.trim() || undefined,
        enabled: formState.enabled,
      });
      message.success('更新成功');
    } else {
      await createTestSetApi({
        code: formState.code?.trim() || undefined,
        name,
        type: formState.type,
        description: formState.description?.trim() || undefined,
        enabled: formState.enabled,
      });
      message.success('创建成功');
    }
    modalVisible.value = false;
    await fetchList();
  } catch (error: unknown) {
    message.error((error as Error)?.message || '提交失败');
  } finally {
    isSubmitting.value = false;
  }
}

async function toggleEnabled(record: TestSetApi.TestSetItem, e: Event) {
  e.stopPropagation();
  try {
    const updated = await toggleTestSetEnabledApi(record.id);
    record.enabled = updated.enabled;
    message.success('已更新');
  } catch (error: unknown) {
    message.error((error as Error)?.message || '更新失败');
  }
}

async function remove(record: TestSetApi.TestSetItem, e: Event) {
  e.stopPropagation();
  try {
    await deleteTestSetApi(record.id);
    message.success('删除成功');
    await fetchList();
  } catch (error: unknown) {
    message.error((error as Error)?.message || '删除失败');
  }
}

function goToDetail(record: TestSetApi.TestSetItem) {
  router.push(`/keyword_corpus/test_case/${record.code}`);
}

function resetFilters() {
  filters.keyword = '';
  filters.type = undefined;
  filters.enabled = undefined;
  pagination.current = 1;
  fetchList();
}

function onPageChange(page: number) {
  pagination.current = page;
  fetchList();
}

// ==================== 生命周期 ====================

// 防抖搜索
let searchTimer: null | ReturnType<typeof setTimeout> = null;
watch(
  () => filters.keyword,
  () => {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      pagination.current = 1;
      fetchList();
    }, 300);
  },
);

watch(
  () => filters.type,
  () => {
    pagination.current = 1;
    fetchList();
  },
);

watch(
  () => filters.enabled,
  () => {
    pagination.current = 1;
    fetchList();
  },
);

onMounted(async () => {
  await fetchList();
});
</script>

<template>
  <div class="test-set-page">
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
          测试集管理
        </span>
        <span v-if="lastUpdateTime" class="text-xs text-muted-foreground">
          数据更新时间：{{ lastUpdateTime }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <Space size="middle">
          <Input
            v-model:value="filters.keyword"
            allow-clear
            placeholder="搜索名称/编码"
            style="width: 200px"
          >
            <template #prefix>
              <SearchOutlined />
            </template>
          </Input>
          <Select
            v-model:value="filters.type"
            allow-clear
            :options="typeOptions"
            placeholder="类型"
            style="width: 120px"
          />
          <Select
            v-model:value="filters.enabled"
            allow-clear
            :options="enabledOptions"
            placeholder="状态"
            style="width: 100px"
          />
          <Button @click="resetFilters">重置</Button>
        </Space>
        <div class="filter-actions">
          <VButton
            class="action-btn"
            variant="ghost"
            size="sm"
            @click="fetchList"
          >
            <ReloadOutlined class="btn-icon" />
            <span class="btn-label">刷新</span>
          </VButton>
          <VButton
            class="action-btn primary-action"
            size="sm"
            @click="openCreate"
          >
            <PlusOutlined class="btn-icon" />
            <span class="btn-label">新建测试集</span>
          </VButton>
        </div>
      </div>
    </div>

    <!-- 测试集卡片网格 -->
    <Spin :spinning="loading">
      <div class="card-grid">
        <!-- 新建测试集卡片 -->
        <div class="test-set-card create-card" @click="openCreate">
          <div class="create-card-content">
            <div class="create-icon">
              <PlusOutlined />
            </div>
            <div class="create-text">新建测试集</div>
            <div class="create-hint">创建一个新的测试集</div>
          </div>
        </div>

        <!-- 测试集列表 -->
        <div
          v-for="item in dataSource"
          :key="item.id"
          class="test-set-card"
          @click="goToDetail(item)"
        >
          <div class="card-header">
            <div class="card-icon" :class="item.type">
              <FileTextOutlined v-if="item.type === 'text'" />
              <FileImageOutlined v-else />
            </div>
            <div class="card-actions">
              <Tooltip title="编辑">
                <Button
                  type="text"
                  size="small"
                  @click="(e: Event) => openEdit(item, e)"
                >
                  <template #icon><EditOutlined /></template>
                </Button>
              </Tooltip>
              <Popconfirm
                title="确定删除该测试集？"
                @confirm="(e: Event) => remove(item, e)"
              >
                <Tooltip title="删除">
                  <Button type="text" size="small" danger @click.stop>
                    <template #icon><DeleteOutlined /></template>
                  </Button>
                </Tooltip>
              </Popconfirm>
            </div>
          </div>

          <div class="card-body">
            <div class="card-title">{{ item.name }}</div>
            <div class="card-code">{{ item.code }}</div>
            <div v-if="item.description" class="card-desc">
              {{ item.description }}
            </div>
          </div>

          <div class="card-footer">
            <div class="card-meta">
              <Tag :color="item.type === 'text' ? 'blue' : 'purple'">
                {{ item.type === 'text' ? '文本' : '图片' }}
              </Tag>
              <span class="case-count">{{ item.case_count }} 个案例</span>
            </div>
            <Switch
              :checked="item.enabled === 1"
              checked-children="启用"
              size="small"
              un-checked-children="禁用"
              @click.stop
              @change="
                (checked: boolean | string | number, e: Event) =>
                  toggleEnabled(item, e)
              "
            />
          </div>
        </div>
      </div>

      <Empty v-if="dataSource.length === 0" description="暂无测试集" />
    </Spin>

    <!-- 分页 -->
    <div v-if="pagination.total > pagination.pageSize" class="pagination-wrap">
      <div class="pagination-info">共 {{ pagination.total }} 个测试集</div>
      <div class="pagination-btns">
        <Button
          :disabled="pagination.current <= 1"
          @click="onPageChange(pagination.current - 1)"
        >
          上一页
        </Button>
        <span class="page-num">{{ pagination.current }}</span>
        <Button
          :disabled="
            pagination.current * pagination.pageSize >= pagination.total
          "
          @click="onPageChange(pagination.current + 1)"
        >
          下一页
        </Button>
      </div>
    </div>

    <!-- 新建/编辑弹窗 -->
    <Modal
      v-model:open="modalVisible"
      :confirm-loading="isSubmitting"
      :title="modalTitle"
      :width="520"
      @ok="submit"
    >
      <Form layout="vertical" class="modal-form">
        <FormItem v-if="!editing" label="编码">
          <Input v-model:value="formState.code" placeholder="留空自动生成" />
        </FormItem>
        <FormItem label="名称" required>
          <Input
            v-model:value="formState.name"
            placeholder="请输入测试集名称"
          />
        </FormItem>
        <FormItem v-if="!editing" label="类型" required>
          <div class="type-selector">
            <div
              class="type-option"
              :class="{ active: formState.type === 'text' }"
              @click="formState.type = 'text'"
            >
              <FileTextOutlined class="type-icon" />
              <span>文本</span>
            </div>
            <div
              class="type-option"
              :class="{ active: formState.type === 'image' }"
              @click="formState.type = 'image'"
            >
              <FileImageOutlined class="type-icon" />
              <span>图片</span>
            </div>
          </div>
        </FormItem>
        <FormItem label="描述">
          <Textarea
            v-model:value="formState.description"
            :rows="3"
            placeholder="可选，简要描述测试集用途"
          />
        </FormItem>
        <FormItem label="启用状态">
          <Switch
            :checked="formState.enabled === 1"
            checked-children="启用"
            un-checked-children="禁用"
            @change="
              (checked: boolean | string | number) =>
                (formState.enabled = checked ? 1 : 0)
            "
          />
        </FormItem>
      </Form>
    </Modal>
  </div>
</template>

<style scoped>
.test-set-page {
  min-height: 100%;
  padding: 16px;
  background: hsl(var(--background));
}

/* 按钮样式 */
.action-btn {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  height: 36px;
  padding: 0 14px;
  font-size: 13px;
  font-weight: 500;
  border-radius: 8px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.action-btn:hover {
  background-color: hsl(var(--accent) / 20%);
  transform: translateY(-1px);
}

.primary-action {
  color: white;
  background: linear-gradient(
    135deg,
    hsl(var(--primary)) 0%,
    hsl(var(--primary) / 85%) 100%
  );
  border-color: transparent;
  box-shadow: 0 2px 8px hsl(var(--primary) / 25%);
}

.primary-action:hover {
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 90%) 0%,
    hsl(var(--primary) / 75%) 100%
  );
  box-shadow: 0 4px 12px hsl(var(--primary) / 35%);
  transform: translateY(-1px);
}

.btn-icon {
  font-size: 14px;
}

.btn-label {
  font-size: 13px;
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

/* 卡片网格 */
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}

.test-set-card {
  display: flex;
  flex-direction: column;
  padding: 20px;
  cursor: pointer;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 16px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.test-set-card:hover {
  border-color: hsl(var(--primary));
  box-shadow: 0 8px 24px hsl(var(--primary) / 12%);
  transform: translateY(-4px);
}

/* 新建测试集卡片 */
.create-card {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 180px;
  background: hsl(var(--card));
  border: 2px dashed hsl(var(--primary) / 30%);
}

.create-card:hover {
  background: hsl(var(--primary) / 3%);
  border-color: hsl(var(--primary));
}

.create-card-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  text-align: center;
}

.create-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  font-size: 28px;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 10%);
  border-radius: 50%;
}

.create-text {
  font-size: 16px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.create-hint {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
}

.card-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  font-size: 24px;
  border-radius: 14px;
}

.card-icon.text {
  color: #1890ff;
  background: linear-gradient(135deg, #1890ff15 0%, #1890ff08 100%);
}

.card-icon.image {
  color: #722ed1;
  background: linear-gradient(135deg, #722ed115 0%, #722ed108 100%);
}

.card-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}

.test-set-card:hover .card-actions {
  opacity: 1;
}

.card-body {
  flex: 1;
  margin-bottom: 16px;
}

.card-title {
  margin-bottom: 4px;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.4;
  color: hsl(var(--foreground));
}

.card-code {
  margin-bottom: 8px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.card-desc {
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 2;
  font-size: 13px;
  line-height: 1.5;
  color: hsl(var(--muted-foreground));
  -webkit-box-orient: vertical;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 16px;
  border-top: 1px solid hsl(var(--border));
}

.card-meta {
  display: flex;
  gap: 12px;
  align-items: center;
}

.case-count {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.pagination-wrap {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 0;
  margin-top: 24px;
}

.pagination-info {
  font-size: 14px;
  color: hsl(var(--muted-foreground));
}

.pagination-btns {
  display: flex;
  gap: 12px;
  align-items: center;
}

.page-num {
  min-width: 32px;
  font-size: 14px;
  font-weight: 500;
  color: hsl(var(--foreground));
  text-align: center;
}

.modal-form {
  padding-top: 12px;
}

.type-selector {
  display: flex;
  gap: 16px;
}

.type-option {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  padding: 20px;
  cursor: pointer;
  border: 2px solid hsl(var(--border));
  border-radius: 14px;
  transition: all 0.2s;
}

.type-option:hover {
  border-color: hsl(var(--primary) / 50%);
}

.type-option.active {
  background: hsl(var(--primary) / 8%);
  border-color: hsl(var(--primary));
}

.type-icon {
  font-size: 32px;
  color: hsl(var(--muted-foreground));
}

.type-option.active .type-icon {
  color: hsl(var(--primary));
}
</style>
