<script setup lang="ts">
import type { RLHFInspectionDetailItem } from '../types';

import { computed, h } from 'vue';

import { VbenIconButton } from '@vben-core/shadcn-ui';

import { EyeOutlined } from '@ant-design/icons-vue';
import { Badge, Card, Empty, Skeleton, Table, Tag } from 'ant-design-vue';
import dayjs from 'dayjs';

interface Props {
  data?: RLHFInspectionDetailItem[];
  loading?: boolean;
  pagination?: {
    current: number;
    pageSize: number;
    total: number;
  };
}

const props = withDefaults(defineProps<Props>(), {
  data: () => [],
  loading: false,
  pagination: () => ({ current: 1, pageSize: 10, total: 0 }),
});

const emit = defineEmits<{
  pageChange: [page: number];
  viewArticle: [item: RLHFInspectionDetailItem];
}>();

// 表格列定义
const columns = computed(() => [
  {
    title: 'ID',
    dataIndex: 'id',
    key: 'id',
    width: 80,
    customRender: ({
      record,
    }: {
      index: number;
      record: RLHFInspectionDetailItem;
    }) => {
      return (
        (props.pagination.current - 1) * props.pagination.pageSize +
        record.index +
        1
      );
    },
  },
  {
    title: '内容标题',
    dataIndex: 'title',
    key: 'title',
    ellipsis: true,
    customRender: ({ record }: { record: RLHFInspectionDetailItem }) => {
      return record.title || '无标题';
    },
  },
  {
    title: '内容预览',
    dataIndex: 'content',
    key: 'content',
    ellipsis: true,
    width: 250,
    customRender: ({ record }: { record: RLHFInspectionDetailItem }) => {
      const preview = record.content || '';
      return preview.length > 50 ? `${preview.slice(0, 50)}...` : preview;
    },
  },
  {
    title: '评分',
    dataIndex: 'score',
    key: 'score',
    width: 100,
    customRender: ({ record }: { record: RLHFInspectionDetailItem }) => {
      const score = record.score || 0;
      let color = 'default';
      if (score >= 90) color = 'success';
      else if (score >= 80) color = 'processing';
      else if (score >= 60) color = 'warning';
      else color = 'error';

      return h(Tag, { color }, () => `${score}分`);
    },
  },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    width: 100,
    customRender: ({ record }: { record: RLHFInspectionDetailItem }) => {
      const isPassed = record.status === 'passed';
      return h(Badge, {
        status: isPassed ? 'success' : 'error',
        text: isPassed ? '通过' : '不通过',
      });
    },
  },
  {
    title: '审查员',
    dataIndex: 'inspector_name',
    key: 'inspector_name',
    width: 100,
    customRender: ({ record }: { record: RLHFInspectionDetailItem }) => {
      return record.inspector_name || '-';
    },
  },
  {
    title: '审查时间',
    dataIndex: 'inspected_at',
    key: 'inspected_at',
    width: 160,
    customRender: ({ record }: { record: RLHFInspectionDetailItem }) => {
      return record.inspected_at
        ? dayjs(record.inspected_at).format('YYYY-MM-DD HH:mm')
        : '-';
    },
  },
  {
    title: '操作',
    key: 'action',
    width: 80,
    fixed: 'right' as const,
    customRender: ({ record }: { record: RLHFInspectionDetailItem }) => {
      return h(
        VbenIconButton,
        {
          tooltip: { title: '查看详情' },
          onClick: () => emit('viewArticle', record),
        },
        () => h(EyeOutlined),
      );
    },
  },
]);

// 添加索引到数据
const tableData = computed(() => {
  return props.data.map((item, index) => ({ ...item, index }));
});

// 处理分页变化
const handleTableChange = (pagination: any) => {
  emit('pageChange', pagination.current);
};
</script>

<template>
  <div class="rlhf-table-section">
    <div class="rlhf-section-subtitle">审查详情记录</div>

    <Card :bordered="false" class="rlhf-table-card">
      <Skeleton :loading="loading" active :paragraph="{ rows: 8 }">
        <div v-if="data.length === 0" class="empty-state">
          <Empty
            description="暂无审查记录"
            :image="Empty.PRESENTED_IMAGE_SIMPLE"
          />
        </div>
        <Table
          v-else
          :columns="columns"
          :data-source="tableData"
          :pagination="{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: false,
            showQuickJumper: true,
            showTotal: (total: number) => `共 ${total} 条`,
          }"
          :scroll="{ x: 1000 }"
          row-key="id"
          @change="handleTableChange"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'title'">
              <span class="content-title">
                {{ record.title || '无标题' }}
              </span>
            </template>
            <template v-else-if="column.key === 'content'">
              <span class="content-preview">
                {{
                  record.content
                    ? record.content.length > 50
                      ? `${record.content.slice(0, 50)}...`
                      : record.content
                    : '-'
                }}
              </span>
            </template>
            <template v-else-if="column.key === 'score'">
              <Tag
                :color="
                  record.score >= 90
                    ? 'success'
                    : record.score >= 80
                      ? 'processing'
                      : record.score >= 60
                        ? 'warning'
                        : 'error'
                "
              >
                {{ record.score }}分
              </Tag>
            </template>
            <template v-else-if="column.key === 'status'">
              <Badge
                :status="record.status === 'passed' ? 'success' : 'error'"
                :text="record.status === 'passed' ? '通过' : '不通过'"
              />
            </template>
            <template v-else-if="column.key === 'action'">
              <VbenIconButton
                tooltip="查看详情"
                @click="emit('viewArticle', record)"
              >
                <EyeOutlined />
              </VbenIconButton>
            </template>
          </template>
        </Table>
      </Skeleton>
    </Card>
  </div>
</template>

<style scoped>
.rlhf-table-section {
  margin-bottom: 24px;
}

.rlhf-section-subtitle {
  margin-bottom: 16px;
  font-size: 15px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.rlhf-table-card {
  background: hsl(var(--card) / 60%);
  border: 1px solid hsl(var(--border) / 50%);
  border-radius: 16px;
  backdrop-filter: blur(10px);
}

.content-title {
  font-weight: 500;
  color: hsl(var(--foreground));
}

.content-preview {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.empty-state {
  padding: 40px 0;
  text-align: center;
}

:deep(.ant-table) {
  background: transparent;
}

:deep(.ant-table-thead > tr > th) {
  font-weight: 600;
  color: hsl(var(--foreground));
  background: hsl(var(--muted) / 30%);
  border-bottom: 1px solid hsl(var(--border));
}

:deep(.ant-table-tbody > tr > td) {
  border-bottom: 1px solid hsl(var(--border) / 50%);
}

:deep(.ant-table-tbody > tr:hover > td) {
  background: hsl(var(--muted) / 20%);
}
</style>
