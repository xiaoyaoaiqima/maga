<script lang="ts" setup>
import type { JobExecutionStats } from '#/api/core/job-execution';

import { onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';

import {
  Button,
  Card,
  message,
  Progress,
  Space,
  Table,
  Tag,
  Tooltip,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import { getAllJobExecutionStatsApi } from '#/api/core/job-execution';

const route = useRoute();

// 状态
const jobStats = ref<JobExecutionStats[]>([]);
const loading = ref(false);
const pagination = ref({
  current: 1,
  pageSize: 20,
  total: 0,
});

// 表格列定义
const columns = [
  {
    title: 'Job 名称',
    dataIndex: 'job_name',
    key: 'job_name',
    width: 200,
  },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    width: 100,
  },
  {
    title: 'SubJob 统计',
    key: 'sub_job_stats',
    width: 200,
  },
  {
    title: '文章统计',
    key: 'content_stats',
    width: 220,
  },
  {
    title: '可用文章完成进度',
    key: 'progress',
    width: 200,
  },
  {
    title: '执行时间',
    key: 'time_range',
    width: 180,
  },
  {
    title: '操作',
    key: 'action',
    width: 150,
    fixed: 'right' as const,
  },
];

// 获取数据
const fetchData = async () => {
  loading.value = true;
  try {
    const res = await getAllJobExecutionStatsApi({
      page: pagination.value.current,
      page_size: pagination.value.pageSize,
    });
    // res 是 { total, items } 结构
    jobStats.value = res?.items || [];
    pagination.value.total = res?.total || 0;
  } catch (error) {
    message.error('获取数据失败');
    console.error('Failed to fetch job execution stats:', error);
  } finally {
    loading.value = false;
  }
};

// 表格变化处理
const handleTableChange = (pag: any) => {
  pagination.value.current = pag.current;
  pagination.value.pageSize = pag.pageSize;
  fetchData();
};

// 格式化日期时间
const formatDateTime = (dateStr: string) => {
  return dayjs(dateStr).format('MM/DD HH:mm');
};

// 获取状态颜色
const getStatusColor = (status?: string) => {
  switch (status) {
    case 'DEPLOYED': {
      return 'green';
    }
    case 'NOT_DEPLOYED': {
      return 'orange';
    }
    case 'PAUSED': {
      return 'gray';
    }
    default: {
      return 'default';
    }
  }
};

// 获取进度颜色
const getProgressColor = (percent?: number) => {
  if (!percent) return '#d9d9d9';
  if (percent >= 100) return '#52c41a';
  if (percent >= 50) return '#1890ff';
  return '#faad14';
};

// 初始化
onMounted(() => {
  fetchData();
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
      <div class="mb-2 flex items-center justify-between gap-3">
        <span
          class="bg-gradient-to-r from-[hsl(var(--primary))] to-[#22c55e] bg-clip-text text-xl font-bold text-transparent"
        >
          {{ route.meta.title || 'Job 执行追踪' }}
        </span>
        <Button type="primary" @click="fetchData">刷新</Button>
      </div>
    </div>

    <Card :bordered="false">
      <Table
        :columns="columns"
        :data-source="jobStats"
        :loading="loading"
        :pagination="pagination"
        row-key="job_id"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <!-- Job 名称 -->
          <template v-if="column.key === 'job_name'">
            <Tooltip
              :title="record.job_name || record.job_id"
              placement="topLeft"
            >
              <router-link :to="`/trace/job-execution/${record.job_id}`">
                <span class="job-name">{{
                  record.job_name || record.job_id
                }}</span>
              </router-link>
            </Tooltip>
          </template>

          <!-- 状态 -->
          <template v-else-if="column.key === 'status'">
            <Tag :color="getStatusColor(record.status)">
              {{ record.status || 'N/A' }}
            </Tag>
          </template>

          <!-- SubJob 统计 -->
          <template v-else-if="column.key === 'sub_job_stats'">
            <Space>
              <Tooltip title="运行中">
                <Tag color="processing">{{ record.running_sub_jobs }}</Tag>
              </Tooltip>
              <Tooltip title="已完成">
                <Tag color="success">{{ record.completed_sub_jobs }}</Tag>
              </Tooltip>
              <Tooltip title="失败">
                <Tag color="error">{{ record.failed_sub_jobs }}</Tag>
              </Tooltip>
              <span class="text-gray-400">/ {{ record.total_sub_jobs }}</span>
            </Space>
          </template>

          <!-- Content 统计 -->
          <template v-else-if="column.key === 'content_stats'">
            <Space>
              <Tooltip title="有效文章">
                <Tag color="green">✓ {{ record.valid_contents }}</Tag>
              </Tooltip>
              <Tooltip title="无效文章">
                <Tag color="red">✗ {{ record.invalid_contents }}</Tag>
              </Tooltip>
              <Tooltip title="测试数据">
                <Tag color="orange">⚡ {{ record.test_contents }}</Tag>
              </Tooltip>
              <span class="text-gray-400">/ {{ record.total_contents }}</span>
            </Space>
          </template>

          <!-- 进度 -->
          <template v-else-if="column.key === 'progress'">
            <div class="progress-cell">
              <Progress
                :percent="record.progress_percentage || 0"
                :stroke-color="getProgressColor(record.progress_percentage)"
                size="small"
                :show-info="false"
              />
              <span class="progress-text">
                {{ record.valid_contents }}/{{
                  record.target_article_count || '∞'
                }}
                ({{ (record.progress_percentage || 0).toFixed(1) }}%)
              </span>
            </div>
          </template>

          <!-- 时间 -->
          <template v-else-if="column.key === 'time_range'">
            <div v-if="record.first_sub_job_time" class="time-cell">
              <div>开始: {{ formatDateTime(record.first_sub_job_time) }}</div>
              <div
                v-if="record.last_sub_job_time !== record.first_sub_job_time"
              >
                最新: {{ formatDateTime(record.last_sub_job_time) }}
              </div>
            </div>
            <span v-else class="text-gray-400">暂无执行</span>
          </template>

          <!-- 操作 -->
          <template v-else-if="column.key === 'action'">
            <Space>
              <router-link :to="`/trace/job-execution/${record.job_id}`">
                <Button type="link" size="small">📋 详情</Button>
              </router-link>
            </Space>
          </template>
        </template>
      </Table>
    </Card>
  </div>
</template>

<style scoped>
.job-name {
  display: inline-block;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
  vertical-align: middle;
  color: hsl(var(--primary));
  white-space: nowrap;
}

.job-name:hover {
  text-decoration: underline;
}

.progress-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.progress-text {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.time-cell {
  font-size: 12px;
  line-height: 1.5;
}

.text-gray-400 {
  color: #9ca3af;
}
</style>
