<script setup lang="ts">
import type { VxeGridProps } from '#/adapter/vxe-table';

import { useRoute } from 'vue-router';

import { Page } from '@vben/common-ui';

import { Button, message, Popconfirm, Switch } from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  deleteIssueTagApi,
  getIssueTagsApi,
  updateIssueTagApi,
} from '#/api/core/rlhf';

const route = useRoute();

const gridOptions: VxeGridProps = {
  columns: [
    { field: 'tag_code', title: '编码', width: 150 },
    { field: 'tag_name', title: '名称', width: 150 },
    { field: 'tag_category', title: '分类', width: 120 },
    { field: 'description', title: '描述', minWidth: 200 },
    { field: 'sort_order', title: '排序', width: 80 },
    {
      field: 'enabled',
      title: '状态',
      width: 100,
      slots: { default: 'enabled' },
    },
    { title: '操作', width: 120, slots: { default: 'action' }, fixed: 'right' },
  ],
  toolbarConfig: {
    custom: true,
    buttons: [{ code: 'add', name: '新增标签', status: 'primary' }],
  },
  proxyConfig: {
    ajax: {
      query: async () => {
        const data = await getIssueTagsApi();
        return { items: data, total: data.length };
      },
    },
  },
};

const [Grid, gridApi] = useVbenVxeGrid({
  gridOptions: gridOptions as any,
  gridEvents: {
    toolbarButtonClick: ({ code }: { code: string }) => {
      if (code === 'add') {
        // TODO: Implement Add/Edit Dialog using VbenModal or simplified inline edit
        // For now, prompt user or use simple implementation
        message.info('Feature under construction (Edit Dialog)');
      }
    },
  },
});

async function handleDelete(row: any) {
  try {
    await deleteIssueTagApi(row.id);
    message.success('删除成功');
    gridApi.reload();
  } catch (error: any) {
    message.error(error.message || '删除失败');
  }
}

async function toggleEnabled(row: any) {
  try {
    await updateIssueTagApi(row.id, { enabled: row.enabled === 1 ? 0 : 1 });
    message.success('状态更新成功');
    gridApi.reload();
  } catch (error: any) {
    message.error(error.message || '更新失败');
  }
}
</script>

<template>
  <Page>
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
          {{ route.meta.title || '问题标签管理' }}
        </span>
      </div>
    </div>

    <div class="h-[600px]">
      <Grid>
        <template #enabled="{ row }">
          <Switch
            :checked="row.enabled === 1"
            checked-children="启用"
            un-checked-children="禁用"
            @change="() => toggleEnabled(row)"
          />
        </template>
        <template #action="{ row }">
          <Popconfirm title="确定删除吗？" @confirm="handleDelete(row)">
            <Button type="link" danger size="small">删除</Button>
          </Popconfirm>
        </template>
      </Grid>
    </div>
  </Page>
</template>

<style scoped></style>
