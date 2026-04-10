<script setup lang="ts">
// 从 TanStack Table 导出的类型
// eslint-disable-next-line n/no-extraneous-import
import type { VisibilityState } from '@tanstack/table-core';
// eslint-disable-next-line n/no-extraneous-import
import type { ColumnDef } from '@tanstack/vue-table';

import type { CategoryTypeOption, CorpusTemplate } from '../types';

import type { TableAction } from '#/components/table';

import { computed, h, onMounted, ref, watch } from 'vue';

import { Badge, VbenButton as Button, Card } from '@vben-core/shadcn-ui';

import {
  DeleteOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue';
// eslint-disable-next-line n/no-extraneous-import -- TanStack Table is used
import { FlexRender, getCoreRowModel, useVueTable } from '@tanstack/vue-table';
import { Input, Skeleton, Space } from 'ant-design-vue';

import { actionFactories, TableActions } from '#/components/table';

interface Props {
  templates: CorpusTemplate[];
  loading: boolean;
  categoryTypeOptions: CategoryTypeOption[];
}

interface Emits {
  (e: 'refresh'): void;
  (e: 'add'): void;
  (e: 'edit', template: CorpusTemplate): void;
  (e: 'delete', code: string): void;
  (e: 'batchDelete', codes: string[]): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

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

// 监听模板数据变化，更新时间
const templates = computed(() => props.templates);
// 全局搜索关键词
const globalSearch = ref('');

// 初始化和监听数据更新
onMounted(() => {
  lastUpdateTime.value = formatCurrentTime(new Date());
});

// 监听 templates 变化更新时间
watch(
  templates,
  () => {
    if (templates.value.length > 0) {
      lastUpdateTime.value = formatCurrentTime(new Date());
    }
  },
  { immediate: true },
);

// 过滤后的数据（前端过滤）
const filteredData = computed(() => {
  if (!globalSearch.value) {
    return props.templates;
  }
  const keyword = globalSearch.value.toLowerCase();
  return props.templates.filter(
    (item) =>
      item.code.toLowerCase().includes(keyword) ||
      item.name.toLowerCase().includes(keyword) ||
      item.category_type.toLowerCase().includes(keyword) ||
      (item.description?.toLowerCase().includes(keyword) ?? false),
  );
});

// 列定义
const columns = computed<ColumnDef<CorpusTemplate, unknown>[]>(() => [
  // 选择列
  {
    id: 'select',
    header: (props) =>
      h('input', {
        type: 'checkbox',
        checked: props.table.getIsAllRowsSelected(),
        indeterminate: props.table.getIsSomeRowsSelected(),
        onChange: (e: Event) =>
          props.table.getToggleAllRowsSelectedHandler()(e),
      }),
    cell: (props) =>
      h('input', {
        type: 'checkbox',
        checked: props.row.getIsSelected(),
        onChange: (e: Event) => props.row.getToggleSelectedHandler()(e),
      }),
    size: 50,
    enableSorting: false,
    enableColumnFilter: false,
  },
  {
    accessorKey: 'code',
    header: '模板编码',
    size: 150,
  },
  {
    accessorKey: 'name',
    header: '模板名称',
    size: 150,
  },
  {
    accessorKey: 'category_type',
    header: '分类类型',
    size: 120,
  },
  {
    accessorKey: 'fields',
    header: '字段数量',
    size: 100,
    cell: ({ row }) => `${row.original.fields?.length || 0} 个字段`,
  },
  {
    accessorKey: 'node_count',
    header: '使用统计',
    size: 100,
    cell: ({ row }) => {
      const count = row.original.node_count || 0;
      return h(
        'span',
        {
          class:
            count > 0 ? 'text-primary font-semibold' : 'text-muted-foreground',
        },
        `${count} 个关键词`,
      );
    },
  },
  {
    accessorKey: 'update_time',
    header: '更新时间',
    size: 180,
    cell: ({ row }: { row: { original: CorpusTemplate } }) =>
      formatUpdateTime(row.original.update_time),
  },
  {
    accessorKey: 'description',
    header: '描述',
    size: 200,
  },
  {
    id: 'action',
    header: '操作',
    size: 150,
    enableColumnFilter: false, // 操作列不参与过滤
    enableRowSelection: false, // 操作列不参与行选择
  },
]);

// 获取分类类型标签
const getCategoryTypeLabel = (type: string) => {
  const option = props.categoryTypeOptions.find((o) => o.value === type);
  return option?.label || type;
};

// 统一时间格式：YYYY-MM-DD HH:mm:ss
const formatUpdateTime = (time: string | undefined) => {
  if (!time) return '-';
  const date = new Date(time);

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');

  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
};

// 获取模板操作按钮配置
const getTemplateActions = (record: CorpusTemplate): TableAction[] => {
  const isUsed = (record.node_count || 0) > 0;

  return [
    actionFactories.edit({
      onClick: () => emit('edit', record),
    }),
    actionFactories.delete({
      confirm: {
        title: isUsed
          ? `该模板被 ${record.node_count} 个节点使用，无法删除！请先移除使用该模板的所有节点后再删除。`
          : '确定删除该模板吗？',
      },
      disabled: isUsed, // 如果模板被使用，禁用删除按钮
      onClick: () => emit('delete', record.code),
      tooltip: isUsed
        ? `该模板被 ${record.node_count} 个节点使用，无法删除`
        : undefined,
    }),
  ];
};

// 列可见性状态
const columnVisibility = ref<VisibilityState>({});
const rowSelection = ref({});

// 创建 TanStack Table 实例，使用过滤后的数据
const table = useVueTable({
  get data() {
    return filteredData.value;
  },
  get columns() {
    return columns.value;
  },
  getCoreRowModel: getCoreRowModel(),
  // 启用多行选择
  enableMultiRowSelection: true,
  // 指定行 ID
  getRowId: (row) => row.code,
  state: {
    get columnVisibility() {
      return columnVisibility.value;
    },
    get rowSelection() {
      return rowSelection.value;
    },
  },
  onColumnVisibilityChange: (updaterOrValue) => {
    columnVisibility.value =
      typeof updaterOrValue === 'function'
        ? updaterOrValue(columnVisibility.value)
        : updaterOrValue;
  },
  onRowSelectionChange: (updaterOrValue) => {
    rowSelection.value =
      typeof updaterOrValue === 'function'
        ? updaterOrValue(rowSelection.value)
        : updaterOrValue;
  },
});

// 导出表格行数，用于显示空状态
const filteredRowCount = computed(() => table.getRowModel().rows.length);

// 获取选中的行
const selectedRows = computed(() => {
  const selectedRowIds = Object.keys(rowSelection.value);
  return filteredData.value.filter((row) => selectedRowIds.includes(row.code));
});

// 获取选中行的数量
const selectedCount = computed(() => selectedRows.value.length);

// 批量删除处理
const handleBatchDelete = () => {
  if (selectedCount.value === 0) return;
  const selectedCodes = selectedRows.value.map((row) => row.code);
  emit('batchDelete', selectedCodes);
};

// 清空选择
const clearSelection = () => {
  rowSelection.value = {};
};
</script>

<template>
  <div class="template-list-page">
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
          语料模板管理
        </span>
        <span v-if="lastUpdateTime" class="text-xs text-muted-foreground">
          数据更新时间：{{ lastUpdateTime }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <Space size="middle">
          <Input
            v-model:value="globalSearch"
            placeholder="搜索编码/名称/分类/描述"
            allow-clear
            style="width: 300px"
          >
            <template #prefix>
              <SearchOutlined />
            </template>
          </Input>
        </Space>
        <div class="filter-actions">
          <Button
            class="action-btn"
            variant="ghost"
            size="sm"
            @click="$emit('refresh')"
          >
            <ReloadOutlined class="btn-icon" />
            <span class="btn-label">刷新</span>
          </Button>
          <Button
            class="action-btn primary-action"
            size="sm"
            @click="$emit('add')"
          >
            <PlusOutlined class="btn-icon" />
            <span class="btn-label">新增模板</span>
          </Button>
        </div>
      </div>
    </div>

    <!-- 搜索结果提示 -->
    <div v-if="globalSearch" class="search-result">
      <span class="search-result-text">
        搜索 "<strong>{{ globalSearch }}</strong
        >" 找到
        <strong class="text-primary">{{ filteredRowCount }}</strong> 条结果
      </span>
      <Button
        variant="ghost"
        size="sm"
        class="clear-btn"
        @click="globalSearch = ''"
      >
        清除筛选
      </Button>
    </div>

    <!-- 批量操作栏 -->
    <div v-if="selectedCount > 0" class="batch-actions-bar">
      <span class="batch-actions-text">
        已选择 <strong>{{ selectedCount }}</strong> 项
      </span>
      <div class="batch-actions-buttons">
        <Button
          variant="ghost"
          size="sm"
          class="batch-action-btn"
          @click="clearSelection"
        >
          取消选择
        </Button>
        <Button
          variant="destructive"
          size="sm"
          class="batch-action-btn"
          @click="handleBatchDelete"
        >
          <DeleteOutlined />
          批量删除
        </Button>
      </div>
    </div>

    <!-- 内容卡片 -->
    <Card class="content-card">
      <!-- 加载状态：骨架屏 -->
      <div v-if="loading" class="skeleton-container">
        <div v-for="i in 5" :key="i" class="skeleton-row">
          <Skeleton :loading="true" active class="skeleton-cell" />
          <Skeleton :loading="true" active class="skeleton-cell" />
          <Skeleton :loading="true" active class="skeleton-cell" />
          <Skeleton :loading="true" active class="skeleton-cell" />
          <Skeleton :loading="true" active class="skeleton-cell short" />
          <Skeleton :loading="true" active class="skeleton-cell short" />
        </div>
      </div>

      <!-- 空状态 -->
      <div
        v-else-if="table.getRowModel().rows.length === 0"
        class="empty-state"
      >
        <div class="empty-illustration">
          <SearchOutlined class="empty-icon" />
        </div>
        <div class="empty-title">
          {{ globalSearch ? '未找到匹配的结果' : '暂无模板数据' }}
        </div>
        <div v-if="globalSearch" class="empty-description">
          请尝试使用其他关键词搜索，或清除筛选查看所有数据
        </div>
        <div v-else class="empty-description">
          点击右上角"新增模板"按钮创建您的第一个语料模板
        </div>
        <Button v-if="!globalSearch" class="empty-action" @click="$emit('add')">
          <PlusOutlined class="btn-icon" />
          创建第一个模板
        </Button>
      </div>

      <!-- 数据表格 -->
      <div v-else class="table-container">
        <table class="data-table">
          <thead>
            <tr
              v-for="headerGroup in table.getHeaderGroups()"
              :key="headerGroup.id"
            >
              <th
                v-for="header in headerGroup.headers"
                :key="header.id"
                :style="{
                  width: header.getSize() ? `${header.getSize()}px` : 'auto',
                }"
              >
                <!-- 复选框列头 -->
                <label
                  v-if="
                    header.column.getIsVisible() &&
                    header.column.id === '__select__'
                  "
                  class="checkbox-cell"
                >
                  <input
                    type="checkbox"
                    :checked="table.getIsAllRowsSelected()"
                    :indeterminate="table.getIsSomeRowsSelected()"
                    @change="table.getToggleAllRowsSelectedHandler()($event)"
                  />
                </label>
                <FlexRender
                  v-else-if="!header.isPlaceholder"
                  :render="header.column.columnDef.header"
                  :props="header.getContext()"
                />
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in table.getRowModel().rows" :key="row.id">
              <td v-for="cell in row.getVisibleCells()" :key="cell.id">
                <!-- 复选框列 -->
                <label
                  v-if="cell.column.id === '__select__'"
                  class="checkbox-cell"
                >
                  <input
                    type="checkbox"
                    :checked="row.getIsSelected()"
                    @change="row.getToggleSelectedHandler()($event)"
                  />
                </label>
                <!-- 分类类型列 -->
                <Badge
                  v-else-if="cell.column.id === 'category_type'"
                  variant="secondary"
                >
                  {{ getCategoryTypeLabel(row.original.category_type) }}
                </Badge>
                <!-- 字段数量列 -->
                <Badge
                  v-else-if="cell.column.id === 'fields'"
                  variant="outline"
                >
                  {{ row.original.fields?.length || 0 }} 个字段
                </Badge>
                <!-- 操作列 -->
                <TableActions
                  v-else-if="cell.column.id === 'action'"
                  :actions="getTemplateActions(row.original)"
                  :record="row.original"
                />
                <!-- 其他列 -->
                <FlexRender
                  v-else
                  :render="cell.column.columnDef.cell"
                  :props="cell.getContext()"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>
  </div>
</template>

<style scoped>
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

/* 统计卡片 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.stat-card {
  cursor: default;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.stat-card:hover {
  border-color: hsl(var(--primary) / 30%);
  box-shadow: 0 8px 16px hsl(var(--foreground) / 6%);
  transform: translateY(-2px);
}

.stat-content {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 16px;
}

.stat-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  font-size: 24px;
  color: hsl(var(--primary));
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 10%) 0%,
    hsl(var(--primary) / 20%) 100%
  );
  border-radius: 12px;
}

.stat-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1;
  color: hsl(var(--foreground));
}

.stat-label {
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
}

/* 批量操作栏 */
.batch-actions-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
  background: linear-gradient(
    135deg,
    hsl(var(--destructive) / 5%) 0%,
    hsl(var(--destructive) / 10%) 100%
  );
  border: 1px solid hsl(var(--destructive) / 15%);
  border-radius: 12px;
}

.batch-actions-text {
  display: flex;
  gap: 4px;
  align-items: center;
}

.batch-actions-text strong {
  font-weight: 600;
  color: hsl(var(--destructive));
}

.batch-actions-buttons {
  display: flex;
  gap: 8px;
}

.batch-action-btn {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

/* 复选框列 */
.data-table th:first-child,
.data-table td:first-child {
  width: 50px;
  text-align: center;
}

.checkbox-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  cursor: pointer;
}

.checkbox-cell input[type='checkbox'] {
  width: 16px;
  height: 16px;
  accent-color: hsl(var(--primary));
  cursor: pointer;
}

/* 搜索结果提示 */
.search-result {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 5%) 0%,
    hsl(var(--primary) / 10%) 100%
  );
  border: 1px solid hsl(var(--primary) / 15%);
  border-radius: 12px;
}

.search-result-text {
  display: flex;
  flex: 1;
  gap: 4px;
  align-items: center;
}

.text-primary {
  font-weight: 600;
  color: hsl(var(--primary));
}

.clear-btn {
  flex-shrink: 0;
}

/* 内容卡片 */
.content-card {
  border-radius: 16px;
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  width: 280px;
}

.search-icon {
  position: absolute;
  right: 12px;
  z-index: 1;
  color: hsl(var(--muted-foreground));
  pointer-events: none;
}

.search-input {
  width: 100%;
}

.search-input :deep(input) {
  height: 38px;
  padding-right: 32px;
  border-radius: 10px;
}

/* 骨架屏 */
.skeleton-container {
  padding: 16px;
}

.skeleton-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 1fr 120px 120px;
  gap: 16px;
  padding: 16px 0;
  border-bottom: 1px solid hsl(var(--border));
}

.skeleton-row:last-child {
  border-bottom: none;
}

.skeleton-cell {
  height: 20px;
  border-radius: 4px;
}

.skeleton-cell.short {
  width: 80px;
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
}

.empty-illustration {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 120px;
  height: 120px;
  margin-bottom: 24px;
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 5%) 0%,
    hsl(var(--primary) / 10%) 100%
  );
  border-radius: 50%;
}

.empty-icon {
  font-size: 48px;
  color: hsl(var(--muted-foreground));
}

.empty-title {
  margin-bottom: 8px;
  font-size: 18px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.empty-description {
  max-width: 400px;
  margin-bottom: 24px;
  font-size: 14px;
  color: hsl(var(--muted-foreground));
}

.empty-action {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  height: 40px;
  padding: 0 20px;
  font-size: 14px;
}

/* 表格 */
.table-container {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  font-size: 14px;
  border-collapse: collapse;
}

.data-table th {
  padding: 14px 16px;
  font-weight: 600;
  color: hsl(var(--foreground));
  text-align: left;
  white-space: nowrap;
  background-color: hsl(var(--muted) / 40%);
  border-bottom: 2px solid hsl(var(--border));
}

.data-table td {
  padding: 14px 16px;
  border-bottom: 1px solid hsl(var(--border));
  transition: background-color 0.15s ease;
}

.data-table tr:hover td {
  background-color: hsl(var(--muted) / 50%);
}

.data-table tr:last-child td {
  border-bottom: none;
}

.text-center {
  text-align: center;
}

.py-8 {
  padding-top: 2rem;
  padding-bottom: 2rem;
}

.text-muted-foreground {
  color: hsl(var(--muted-foreground));
}
</style>
