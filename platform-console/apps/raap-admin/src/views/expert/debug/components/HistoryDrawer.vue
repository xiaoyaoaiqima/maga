<script setup lang="ts">
import type { DebugResponse } from '../types';

/**
 * 调试历史抽屉组件
 */
import { computed } from 'vue';

import { formatDateTime } from '@vben/utils';

import { Button, Drawer, Popconfirm, Space, Table, Tag } from 'ant-design-vue';

import { HISTORY_TABLE_COLUMNS } from '../constants';
import { formatExecutionTime } from '../utils';

interface Props {
  visible: boolean;
  loading: boolean;
  historyList: DebugResponse[];
  pagination: any;
  selectedIds: number[];
}

const props = defineProps<Props>();

const emit = defineEmits<{
  delete: [id: number];
  load: [item: DebugResponse];
  refresh: [];
  showDiff: [];
  star: [id: number, isStarred: boolean];
  tableChange: [pagination: any];
  toggleSelect: [id: number];
  'update:visible': [value: boolean];
}>();

const drawerVisible = computed({
  get: () => props.visible,
  set: (val) => emit('update:visible', val),
});
</script>

<template>
  <Drawer
    v-model:open="drawerVisible"
    title="📜 调试历史"
    :width="800"
    placement="right"
  >
    <div class="history-toolbar mb-4">
      <Space>
        <Button :disabled="selectedIds.length !== 2" @click="emit('showDiff')">
          🔀 对比选中 ({{ selectedIds.length }}/2)
        </Button>
        <Button @click="emit('refresh')">🔄 刷新</Button>
      </Space>
    </div>

    <Table
      :columns="HISTORY_TABLE_COLUMNS"
      :data-source="historyList"
      :loading="loading"
      :pagination="pagination"
      row-key="id"
      size="small"
      @change="(pag: any) => emit('tableChange', pag)"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'select'">
          <input
            type="checkbox"
            :checked="selectedIds.includes(record.id)"
            @change="emit('toggleSelect', record.id)"
          />
        </template>
        <template v-else-if="column.key === 'success'">
          <Tag :color="record.success ? 'green' : 'red'">
            {{ record.success ? '成功' : '失败' }}
          </Tag>
        </template>
        <template v-else-if="column.key === 'execution_time_ms'">
          {{ formatExecutionTime(record.execution_time_ms) }}
        </template>
        <template v-else-if="column.key === 'create_time'">
          {{ formatDateTime(record.create_time) }}
        </template>
        <template v-else-if="column.key === 'action'">
          <Space>
            <Button
              size="small"
              type="link"
              @click="emit('load', record as DebugResponse)"
            >
              加载
            </Button>
            <Button
              size="small"
              type="link"
              @click="emit('star', record.id, !record.is_starred)"
            >
              {{ record.is_starred ? '⭐' : '☆' }}
            </Button>
            <Popconfirm title="确定删除?" @confirm="emit('delete', record.id)">
              <Button size="small" type="link" danger>删除</Button>
            </Popconfirm>
          </Space>
        </template>
      </template>
    </Table>
  </Drawer>
</template>

<style scoped>
.history-toolbar {
  display: flex;
  justify-content: space-between;
}

.mb-4 {
  margin-bottom: 16px;
}
</style>
