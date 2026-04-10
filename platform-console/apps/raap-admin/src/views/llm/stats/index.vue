<script setup lang="ts">
import type { LLMApi } from '#/api/core/llm';

import { onMounted, ref } from 'vue';

import {
  Button,
  Card,
  Col,
  DatePicker,
  Row,
  Select,
  SelectOption,
  Space,
  Statistic,
  Table,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import {
  getDailyStatsApi,
  getModelStatsApi,
  getProviderListApi,
  getProviderStatsApi,
} from '#/api/core/llm';

const { RangePicker } = DatePicker;

// 状态
const loading = ref(false);
const providers = ref<LLMApi.ProviderConfig[]>([]);
const providerStats = ref<LLMApi.ProviderStats[]>([]);
const modelStats = ref<LLMApi.ModelStats[]>([]);
const dailyStats = ref<LLMApi.DailyStats[]>([]);

// 筛选条件
const dateRange = ref<[dayjs.Dayjs, dayjs.Dayjs]>([
  dayjs().subtract(7, 'day'),
  dayjs(),
]);
const filterProviderCode = ref('');

// 概览数据
const overview = ref({
  totalCalls: 0,
  totalTokens: 0,
  totalCost: 0,
  avgLatency: 0,
});

const avgCostPerCall = ref(0);
const avgCostPer1kTokens = ref(0);
const topProvidersByCost = ref<LLMApi.ProviderStats[]>([]);
const topModelsByCost = ref<LLMApi.ModelStats[]>([]);

// Provider 统计表格列
const providerColumns = [
  {
    title: 'Provider',
    dataIndex: 'provider_code',
    key: 'provider_code',
    width: 150,
  },
  {
    title: '调用次数',
    dataIndex: 'total_calls',
    key: 'total_calls',
    width: 120,
  },
  {
    title: 'Token 总量',
    dataIndex: 'total_tokens',
    key: 'total_tokens',
    width: 150,
  },
  { title: '总成本', dataIndex: 'total_cost', key: 'total_cost', width: 120 },
  {
    title: '平均延迟',
    dataIndex: 'avg_latency_ms',
    key: 'avg_latency_ms',
    width: 120,
  },
  {
    title: '成功率',
    dataIndex: 'success_rate',
    key: 'success_rate',
    width: 100,
  },
];

// 模型统计表格列
const modelColumns = [
  { title: '模型', dataIndex: 'model_code', key: 'model_code', width: 150 },
  {
    title: '调用次数',
    dataIndex: 'total_calls',
    key: 'total_calls',
    width: 120,
  },
  {
    title: 'Token 总量',
    dataIndex: 'total_tokens',
    key: 'total_tokens',
    width: 150,
  },
  {
    title: '平均延迟',
    dataIndex: 'avg_latency_ms',
    key: 'avg_latency_ms',
    width: 120,
  },
];

// 日趋势表格列
const dailyColumns = [
  { title: '日期', dataIndex: 'date', key: 'date', width: 120 },
  {
    title: '调用次数',
    dataIndex: 'total_calls',
    key: 'total_calls',
    width: 120,
  },
  {
    title: 'Token 总量',
    dataIndex: 'total_tokens',
    key: 'total_tokens',
    width: 150,
  },
];

// 获取日期参数
function getDateParams() {
  const [start, end] = dateRange.value;
  return {
    start_date: start.format('YYYY-MM-DD'),
    end_date: end.format('YYYY-MM-DD'),
  };
}

// 获取 Provider 列表
async function fetchProviders() {
  try {
    const res = await getProviderListApi();
    providers.value = res?.items || [];
  } catch (error) {
    console.error('获取 Provider 列表失败:', error);
  }
}

// 获取统计数据
async function fetchStats() {
  loading.value = true;
  try {
    const dateParams = getDateParams();

    const [providerRes, modelRes, dailyRes] = await Promise.all([
      getProviderStatsApi(dateParams),
      getModelStatsApi(dateParams),
      getDailyStatsApi({
        ...dateParams,
        provider_code: filterProviderCode.value || undefined,
      }),
    ]);

    providerStats.value = providerRes || [];
    modelStats.value = modelRes || [];
    dailyStats.value = dailyRes || [];

    // 计算概览数据
    let totalCalls = 0;
    let totalTokens = 0;
    let totalCost = 0;
    let totalLatency = 0;
    let latencyCount = 0;

    for (const p of providerStats.value) {
      totalCalls += p.total_calls;
      totalTokens += p.total_tokens;
      totalCost += p.total_cost;
      if (p.avg_latency_ms > 0) {
        totalLatency += p.avg_latency_ms * p.total_calls;
        latencyCount += p.total_calls;
      }
    }

    overview.value = {
      totalCalls,
      totalTokens,
      totalCost,
      avgLatency: latencyCount > 0 ? totalLatency / latencyCount : 0,
    };

    avgCostPerCall.value = totalCalls > 0 ? totalCost / totalCalls : 0;
    avgCostPer1kTokens.value =
      totalTokens > 0 ? totalCost / (totalTokens / 1000) : 0;

    topProvidersByCost.value = [...providerStats.value]
      .toSorted((a, b) => b.total_cost - a.total_cost)
      .slice(0, 5);
    topModelsByCost.value = [...modelStats.value]
      .toSorted((a, b) => b.total_cost - a.total_cost)
      .slice(0, 5);
  } catch (error) {
    console.error('获取统计数据失败:', error);
  } finally {
    loading.value = false;
  }
}

// 格式化数字
function formatNumber(num: number): string {
  if (num >= 1_000_000) {
    return `${(num / 1_000_000).toFixed(2)}M`;
  }
  if (num >= 1000) {
    return `${(num / 1000).toFixed(2)}K`;
  }
  return num.toString();
}

// 格式化成本
function formatCost(cost: number): string {
  return `$${cost.toFixed(4)}`;
}

function exportCSV<T extends Record<string, any>>(rows: T[], filename: string) {
  if (!rows || rows.length === 0) return;
  const headers = Object.keys(rows[0] as Record<string, any>);
  const dataRows = rows.map((r) =>
    headers
      .map((h) => {
        const val = r[h];
        if (val === null || val === undefined) return '';
        const s = String(val).replaceAll('"', '""');
        return /[",\n]/.test(s) ? `"${s}"` : s;
      })
      .join(','),
  );
  const csv = [headers.join(','), ...dataRows].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// 格式化延迟
function formatLatency(ms: number): string {
  if (ms >= 1000) {
    return `${(ms / 1000).toFixed(2)}s`;
  }
  return `${Math.round(ms)}ms`;
}

// 格式化成功率
function formatSuccessRate(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

onMounted(() => {
  fetchProviders();
  fetchStats();
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
          模型成本统计
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">时间</span>
          <RangePicker
            v-model:value="dateRange"
            :allow-clear="false"
            @change="fetchStats"
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">快捷</span>
          <Space>
            <Button
              size="small"
              @click="
                dateRange = [dayjs().subtract(7, 'day'), dayjs()];
                fetchStats();
              "
            >
              近7天
            </Button>
            <Button
              size="small"
              @click="
                dateRange = [dayjs().subtract(30, 'day'), dayjs()];
                fetchStats();
              "
            >
              近30天
            </Button>
            <Button
              size="small"
              @click="
                dateRange = [dayjs().subtract(90, 'day'), dayjs()];
                fetchStats();
              "
            >
              近90天
            </Button>
          </Space>
        </div>
        <div class="filter-item">
          <span class="filter-label">Provider</span>
          <Select
            v-model:value="filterProviderCode"
            placeholder="筛选 Provider"
            style="width: 150px"
            allow-clear
            @change="fetchStats"
          >
            <SelectOption
              v-for="p in providers"
              :key="p.provider_code"
              :value="p.provider_code"
            >
              {{ p.provider_name }}
            </SelectOption>
          </Select>
        </div>
        <div class="filter-actions">
          <Button @click="fetchStats" :loading="loading">🔄 刷新</Button>
        </div>
      </div>
    </div>

    <!-- 概览卡片 -->
    <Row :gutter="16" class="mb-4">
      <Col :span="6">
        <Card :bordered="false">
          <Statistic
            title="总调用次数"
            :value="overview.totalCalls"
            :precision="0"
            :value-style="{ color: '#1890ff' }"
          >
            <template #prefix>📊</template>
          </Statistic>
        </Card>
      </Col>
      <Col :span="6">
        <Card :bordered="false">
          <Statistic
            title="Token 总量"
            :value="formatNumber(overview.totalTokens)"
            :value-style="{ color: '#52c41a' }"
          >
            <template #prefix>🔤</template>
          </Statistic>
        </Card>
      </Col>
      <Col :span="6">
        <Card :bordered="false">
          <Statistic
            title="总成本"
            :value="overview.totalCost"
            :precision="4"
            prefix="$"
            :value-style="{ color: '#faad14' }"
          />
        </Card>
      </Col>
      <Col :span="6">
        <Card :bordered="false">
          <Statistic
            title="平均延迟"
            :value="formatLatency(overview.avgLatency)"
            :value-style="{ color: '#722ed1' }"
          >
            <template #prefix>⏱️</template>
          </Statistic>
        </Card>
      </Col>
      <Col :span="6">
        <Card :bordered="false">
          <Statistic
            title="单次平均成本"
            :value="avgCostPerCall"
            :precision="4"
            prefix="$"
            :value-style="{ color: '#ff7875' }"
          />
        </Card>
      </Col>
      <Col :span="6">
        <Card :bordered="false">
          <Statistic
            title="每 1K Tokens 成本"
            :value="avgCostPer1kTokens"
            :precision="4"
            prefix="$"
            :value-style="{ color: '#13c2c2' }"
          />
        </Card>
      </Col>
    </Row>

    <!-- Provider 统计 -->
    <Card title="Provider 统计" :bordered="false" class="mb-4">
      <template #extra>
        <Space>
          <Button
            size="small"
            @click="exportCSV(providerStats, 'provider_stats.csv')"
          >
            导出CSV
          </Button>
        </Space>
      </template>
      <Table
        :columns="providerColumns"
        :data-source="providerStats"
        :loading="loading"
        :pagination="false"
        row-key="provider_code"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'total_tokens'">
            {{ formatNumber(record.total_tokens) }}
          </template>
          <template v-else-if="column.key === 'total_cost'">
            {{ formatCost(record.total_cost) }}
          </template>
          <template v-else-if="column.key === 'avg_latency_ms'">
            {{ formatLatency(record.avg_latency_ms) }}
          </template>
          <template v-else-if="column.key === 'success_rate'">
            <span
              :class="
                record.success_rate >= 0.95
                  ? 'text-green'
                  : record.success_rate >= 0.9
                    ? 'text-orange'
                    : 'text-red'
              "
            >
              {{ formatSuccessRate(record.success_rate) }}
            </span>
          </template>
        </template>
      </Table>
    </Card>

    <!-- 模型统计 -->
    <Card title="模型统计" :bordered="false" class="mb-4">
      <template #extra>
        <Space>
          <Button
            size="small"
            @click="exportCSV(modelStats, 'model_stats.csv')"
          >
            导出CSV
          </Button>
        </Space>
      </template>
      <Table
        :columns="modelColumns"
        :data-source="modelStats"
        :loading="loading"
        :pagination="false"
        row-key="model_code"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'total_tokens'">
            {{ formatNumber(record.total_tokens) }}
          </template>
          <template v-else-if="column.key === 'total_cost'">
            {{ formatCost(record.total_cost) }}
          </template>
          <template v-else-if="column.key === 'avg_latency_ms'">
            {{ formatLatency(record.avg_latency_ms) }}
          </template>
        </template>
      </Table>
    </Card>

    <!-- 日趋势 -->
    <Card title="日趋势" :bordered="false">
      <template #extra>
        <Space>
          <Button
            size="small"
            @click="exportCSV(dailyStats, 'daily_stats.csv')"
          >
            导出CSV
          </Button>
        </Space>
      </template>
      <Table
        :columns="dailyColumns"
        :data-source="dailyStats"
        :loading="loading"
        :pagination="false"
        row-key="date"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'total_tokens'">
            {{ formatNumber(record.total_tokens) }}
          </template>
          <template v-else-if="column.key === 'total_cost'">
            {{ formatCost(record.total_cost) }}
          </template>
        </template>
      </Table>
    </Card>

    <!-- 成本 Top5 -->
    <Row :gutter="16" class="mt-4">
      <Col :span="12">
        <Card title="成本 Top5 Provider" :bordered="false">
          <Table
            :columns="[
              {
                title: 'Provider',
                dataIndex: 'provider_code',
                key: 'provider_code',
                width: 160,
              },
              {
                title: '调用次数',
                dataIndex: 'total_calls',
                key: 'total_calls',
                width: 120,
              },
              {
                title: 'Token 总量',
                dataIndex: 'total_tokens',
                key: 'total_tokens',
                width: 140,
              },
              {
                title: '总成本',
                dataIndex: 'total_cost',
                key: 'total_cost',
                width: 120,
              },
            ]"
            :data-source="topProvidersByCost"
            :pagination="false"
            size="small"
            row-key="provider_code"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'total_tokens'">
                {{ formatNumber(record.total_tokens) }}
              </template>
              <template v-else-if="column.key === 'total_cost'">
                {{ formatCost(record.total_cost) }}
              </template>
            </template>
          </Table>
        </Card>
      </Col>
      <Col :span="12">
        <Card title="成本 Top5 模型" :bordered="false">
          <Table
            :columns="[
              {
                title: '模型',
                dataIndex: 'model_code',
                key: 'model_code',
                width: 160,
              },
              {
                title: '调用次数',
                dataIndex: 'total_calls',
                key: 'total_calls',
                width: 120,
              },
              {
                title: 'Token 总量',
                dataIndex: 'total_tokens',
                key: 'total_tokens',
                width: 140,
              },
              {
                title: '总成本',
                dataIndex: 'total_cost',
                key: 'total_cost',
                width: 120,
              },
            ]"
            :data-source="topModelsByCost"
            :pagination="false"
            size="small"
            row-key="model_code"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'total_tokens'">
                {{ formatNumber(record.total_tokens) }}
              </template>
              <template v-else-if="column.key === 'total_cost'">
                {{ formatCost(record.total_cost) }}
              </template>
            </template>
          </Table>
        </Card>
      </Col>
    </Row>
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

.mb-4 {
  margin-bottom: 16px;
}

.mt-4 {
  margin-top: 16px;
}

.text-green {
  color: #52c41a;
}

.text-orange {
  color: #faad14;
}

.text-red {
  color: #ff4d4f;
}
</style>
