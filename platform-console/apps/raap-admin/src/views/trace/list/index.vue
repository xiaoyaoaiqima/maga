<script setup lang="ts">
import type { TraceApi } from '#/api/core/trace';

import { onMounted, onUnmounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { formatDateTime } from '@vben/utils';

import {
  Badge,
  Button,
  Card,
  DatePicker,
  Input,
  message,
  Select,
  Table,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import { getTraceListApi } from '#/api/core/trace';

const router = useRouter();
const loading = ref(false);
const dataSource = ref<TraceApi.TraceSpan[]>([]);
const autoRefresh = ref(false);
const pagination = ref({
  current: 1,
  pageSize: 20,
  total: 0,
  showSizeChanger: true,
  showTotal: (t: number) => `共 ${t} 条`,
});
let refreshTimer: null | ReturnType<typeof setInterval> = null;

const filters = ref({
  job_id: '',
  sub_job_id: '',
  expert_config_code: '',
  status: undefined as string | undefined,
  stage: undefined as string | undefined,
  date_range: undefined as [any, any] | undefined,
});

const columns = [
  {
    title: 'Trace ID',
    dataIndex: 'trace_id',
    key: 'trace_id',
    width: 120,
    ellipsis: true,
  },
  {
    title: 'Span ID',
    dataIndex: 'span_id',
    key: 'span_id',
    width: 120,
    ellipsis: true,
  },
  {
    title: 'Job ID',
    dataIndex: 'job_id',
    key: 'job_id',
    width: 140,
    ellipsis: true,
  },
  {
    title: 'Sub Job ID',
    dataIndex: 'sub_job_id',
    key: 'sub_job_id',
    width: 150,
    ellipsis: true,
  },
  {
    title: 'Expert',
    dataIndex: 'expert_config_code',
    key: 'expert_config_code',
    width: 150,
    ellipsis: true,
  },
  { title: '阶段', dataIndex: 'stage', key: 'stage', width: 120 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 90 },
  { title: '开始时间', dataIndex: 'start_time', key: 'start_time', width: 170 },
  { title: '耗时', dataIndex: 'duration_ms', key: 'duration_ms', width: 100 },
  {
    title: 'Tokens',
    dataIndex: 'total_tokens',
    key: 'total_tokens',
    width: 100,
  },
  { title: '操作', key: 'action', width: 80, fixed: 'right' as const },
];

const statusOptions = [
  { value: 'pending', label: '待执行' },
  { value: 'running', label: '执行中' },
  { value: 'success', label: '成功' },
  { value: 'failed', label: '失败' },
  { value: 'timeout', label: '超时' },
];

const stageOptions = [
  { value: 'plugin_render', label: 'Plugin 渲染' },
  { value: 'prompt_render', label: 'Prompt 渲染' },
  { value: 'ge_generation', label: 'GE 生成' },
  { value: 'ag_ban', label: 'AG Ban' },
  { value: 'ag_critic', label: 'AG Critic' },
  { value: 'debug', label: '调试' },
  { value: 'expert_call', label: 'Expert 调用' },
];

const statusColorMap: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  success: 'success',
  failed: 'error',
  timeout: 'warning',
};

const statusTextMap: Record<string, string> = {
  pending: '待执行',
  running: '执行中',
  success: '成功',
  failed: '失败',
  timeout: '超时',
};

const stageTagColor: Record<string, string> = {
  plugin_render: 'blue',
  prompt_render: 'cyan',
  ge_generation: 'green',
  ag_ban: 'orange',
  ag_critic: 'purple',
  debug: 'default',
  expert_call: 'magenta',
};

const stageTextMap: Record<string, string> = {
  plugin_render: 'Plugin渲染',
  prompt_render: 'Prompt渲染',
  ge_generation: 'GE生成',
  ag_ban: 'AG Ban',
  ag_critic: 'AG Critic',
  debug: '调试',
  expert_call: 'Expert调用',
};

async function fetchTraces() {
  loading.value = true;
  try {
    const params: TraceApi.TraceListQuery = {
      page: pagination.value.current,
      page_size: pagination.value.pageSize,
    };

    if (filters.value.job_id) {
      params.job_id = filters.value.job_id;
    }
    if (filters.value.sub_job_id) {
      params.sub_job_id = filters.value.sub_job_id;
    }
    if (filters.value.expert_config_code) {
      params.expert_config_code = filters.value.expert_config_code;
    }
    if (filters.value.status) {
      params.status = filters.value.status;
    }
    if (filters.value.stage) {
      params.stage = filters.value.stage;
    }
    if (filters.value.date_range) {
      params.start_date = filters.value.date_range[0]?.format('YYYY-MM-DD');
      params.end_date = filters.value.date_range[1]?.format('YYYY-MM-DD');
    }

    const res = await getTraceListApi(params);
    dataSource.value = res.items || [];
    pagination.value.total = res.total || 0;
  } catch (error) {
    console.error('获取追踪列表失败:', error);
    message.error('获取调用记录失败');
  } finally {
    loading.value = false;
  }
}

function handleView(record: TraceApi.TraceSpan) {
  router.push(`/trace/detail/${record.trace_id}`);
}

function handleSearch() {
  pagination.value.current = 1;
  fetchTraces();
}

function handleReset() {
  filters.value = {
    job_id: '',
    sub_job_id: '',
    expert_config_code: '',
    status: undefined,
    stage: undefined,
    date_range: undefined,
  };
  pagination.value.current = 1;
  fetchTraces();
}

function handleTableChange(pag: any) {
  pagination.value.current = pag.current;
  pagination.value.pageSize = pag.pageSize;
  fetchTraces();
}

function toggleAutoRefresh() {
  autoRefresh.value = !autoRefresh.value;
  if (autoRefresh.value) {
    refreshTimer = setInterval(fetchTraces, 5000);
    message.success('已开启自动刷新（每5秒）');
  } else {
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
    message.info('已关闭自动刷新');
  }
}

function formatDuration(ms: number | undefined): string {
  if (!ms || ms <= 0) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

onMounted(() => {
  fetchTraces();
});

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer);
  }
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
          调用追踪
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">Job</span>
          <Input
            v-model:value="filters.job_id"
            placeholder="Job ID"
            allow-clear
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">Sub Job</span>
          <Input
            v-model:value="filters.sub_job_id"
            placeholder="Sub Job ID"
            allow-clear
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">Expert</span>
          <Input
            v-model:value="filters.expert_config_code"
            placeholder="Expert 编码"
            allow-clear
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">阶段</span>
          <Select
            v-model:value="filters.stage"
            :options="stageOptions"
            placeholder="阶段"
            allow-clear
            show-search
            :filter-option="true"
            style="width: 140px"
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">状态</span>
          <Select
            v-model:value="filters.status"
            :options="statusOptions"
            placeholder="状态"
            allow-clear
            show-search
            :filter-option="true"
            style="width: 120px"
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">时间</span>
          <DatePicker.RangePicker
            v-model:value="filters.date_range"
            style="width: 240px"
            :placeholder="['开始日期', '结束日期']"
          />
        </div>
        <div class="filter-actions">
          <Button type="primary" @click="handleSearch">搜索</Button>
          <Button @click="handleReset">重置</Button>
          <Button
            :type="autoRefresh ? 'primary' : 'default'"
            @click="toggleAutoRefresh"
          >
            {{ autoRefresh ? '⟳ 自动刷新中' : '⟲ 自动刷新' }}
          </Button>
          <Button @click="fetchTraces">刷新</Button>
        </div>
      </div>
    </div>

    <Card :bordered="false">
      <Table
        :columns="columns"
        :data-source="dataSource"
        :loading="loading"
        :pagination="pagination"
        :scroll="{ x: 1400 }"
        row-key="id"
        size="middle"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record: rawRecord }">
          <template v-if="column.key === 'trace_id'">
            <Tooltip :title="(rawRecord as TraceApi.TraceSpan).trace_id">
              <span
                class="cursor-pointer text-primary"
                @click="handleView(rawRecord as TraceApi.TraceSpan)"
              >
                {{ (rawRecord as TraceApi.TraceSpan).trace_id.slice(0, 12) }}...
              </span>
            </Tooltip>
          </template>
          <template v-else-if="column.key === 'span_id'">
            <Tooltip :title="(rawRecord as TraceApi.TraceSpan).span_id">
              <code>{{
                (rawRecord as TraceApi.TraceSpan).span_id
                  ? (rawRecord as TraceApi.TraceSpan).span_id.slice(0, 8)
                  : '-'
              }}</code>
            </Tooltip>
          </template>
          <template v-else-if="column.key === 'stage'">
            <Tag
              :color="
                stageTagColor[(rawRecord as TraceApi.TraceSpan).stage] ||
                'default'
              "
            >
              {{
                stageTextMap[(rawRecord as TraceApi.TraceSpan).stage] ||
                (rawRecord as TraceApi.TraceSpan).stage
              }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'status'">
            <Badge
              :status="
                statusColorMap[(rawRecord as TraceApi.TraceSpan).status] as any
              "
              :text="
                statusTextMap[(rawRecord as TraceApi.TraceSpan).status] ||
                (rawRecord as TraceApi.TraceSpan).status
              "
            />
          </template>
          <template v-else-if="column.key === 'start_time'">
            {{ formatDateTime((rawRecord as TraceApi.TraceSpan).start_time) }}
          </template>
          <template v-else-if="column.key === 'duration_ms'">
            <span
              :class="{
                'text-warning':
                  ((rawRecord as TraceApi.TraceSpan).duration_ms ?? 0) > 5000,
              }"
            >
              {{
                formatDuration((rawRecord as TraceApi.TraceSpan).duration_ms)
              }}
            </span>
          </template>
          <template v-else-if="column.key === 'total_tokens'">
            <span v-if="(rawRecord as TraceApi.TraceSpan).total_tokens > 0">
              {{
                (rawRecord as TraceApi.TraceSpan).total_tokens.toLocaleString()
              }}
            </span>
            <span v-else class="text-muted">-</span>
          </template>
          <template v-else-if="column.key === 'action'">
            <Tooltip title="查看详情">
              <Button
                type="link"
                size="small"
                @click="handleView(rawRecord as TraceApi.TraceSpan)"
              >
                👁️
              </Button>
            </Tooltip>
          </template>
        </template>
      </Table>
    </Card>
  </div>
</template>

<style scoped>
.p-4 {
  padding: 16px;
}

.mb-4 {
  margin-bottom: 16px;
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

.text-primary {
  color: hsl(var(--primary));
}

.text-warning {
  color: hsl(var(--warning));
}

.text-muted {
  color: hsl(var(--muted-foreground));
}

.cursor-pointer {
  cursor: pointer;
}
</style>
