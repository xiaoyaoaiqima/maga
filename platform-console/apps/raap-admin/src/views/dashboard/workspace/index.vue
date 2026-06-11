<script setup lang="ts">
// @ts-nocheck
import type { DefaultOptionType } from 'ant-design-vue/es/select';

import type { EchartsUIType } from '@vben/plugins/echarts';

import type { ActivityApi, AgentApi, TenantApi } from '#/api/core/business';
import type { DashboardApi } from '#/api/core/dashboard';

import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import { EchartsUI, useEcharts } from '@vben/plugins/echarts';
import { formatDateTime } from '@vben/utils';

import {
  AppstoreOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  DollarOutlined,
  FileTextOutlined,
  FireOutlined,
  LikeOutlined,
  LoadingOutlined,
  ReloadOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue';
import {
  Badge,
  Button,
  Card,
  Col,
  Empty,
  Input,
  List,
  ListItem,
  ListItemMeta,
  message,
  RangePicker,
  Row,
  Select,
  Skeleton,
  Space,
  Statistic,
  Table,
  TabPane,
  Tabs,
  Tag,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import {
  getActivitySimpleListApi,
  getAgentSimpleListApi,
  getTenantSimpleListApi,
} from '#/api/core/business';
import {
  getDashboardOverviewApi,
  getDashboardStatsApi,
  queryMetricApi,
} from '#/api/core/dashboard';
import MetricHelp from '#/components/MetricHelp/index.vue';

/** 接口定义 */
interface AgentStat {
  agent_code: string;
  running_count: number;
  total_calls: number;
}

interface AgentTrend {
  agent_code: string;
  call_count: number;
  date: string;
}

interface ExpertRank {
  expert_config_code: string;
  request_count: number;
  success_rate: number;
}

interface GenericMetric {
  [key: string]: unknown;
}

interface ModelCost {
  model_code: string;
  total_cost: number;
}

interface StageLatency {
  avg_latency_ms: number;
  stage: string;
}

interface IssueDist {
  issue_count: number;
  issue_type: string;
}

const router = useRouter();
const loading = ref(true);
const activeTab = ref('overview');

// 日期范围（默认最近 30 天）
const dateRange = ref<[dayjs.Dayjs, dayjs.Dayjs]>([
  dayjs().subtract(29, 'day'),
  dayjs(),
]);

// 时间预设
const ranges: Record<string, [dayjs.Dayjs, dayjs.Dayjs]> = {
  '最近 7 天': [dayjs().subtract(6, 'day'), dayjs()],
  '最近 15 天': [dayjs().subtract(14, 'day'), dayjs()],
  '最近 30 天': [dayjs().subtract(29, 'day'), dayjs()],
  '最近 90 天': [dayjs().subtract(89, 'day'), dayjs()],
  '最近 1 年': [dayjs().subtract(1, 'year'), dayjs()],
};

// 筛选状态
const filters = ref({
  activityId: undefined as number[] | undefined,
  agentCode: undefined as string[] | undefined,
  tenantId: undefined as number[] | undefined,
});

// 筛选选项
const tenantOptions = ref<Array<{ label: string; value: number }>>([]);
const activityOptions = ref<Array<{ label: string; value: number }>>([]);
const agentOptions = ref<Array<{ label: string; value: string }>>([]);

// 业务指标
const overviewStats = ref<
  DashboardApi.OverviewStats & { total_cost_detail?: string }
>({
  adopt_rate: 0,
  total_contents: 0,
  total_cost: 0,
  total_jobs: 0,
});

// RLHF & 质量指标
const rlhfStats = ref({
  adopt_rate: 0,
  dislike_rate: 0,
  edit_after_adopt_rate: 0,
  like_rate: 0,
});

// AG 治理指标
const agStats = ref({
  block_rate: 0,
  total_blocks: 0,
  total_checks: 0,
});

// AI 算力指标
const aiCostStats = ref({
  avg_cost_per_output: 0,
  governance_llm_cost: 0,
  total_llm_token_cost: 0,
  total_token_count: 0,
  // 多币种支持
  costs: {} as Record<string, number>,
  avg_costs: {} as Record<string, number>,
  gov_costs: {} as Record<string, number>,
});

// 系统指标 (旧 API)
const systemStats = ref({
  deployedJobs: 0,
  runningJobs: 0,
  successRate: 0,
  todayExecutions: 0,
  totalExpertConfigs: 0,
  totalJobs: 0,
  totalPlugins: 0,
});

const recentExecutions = ref<DashboardApi.RecentExecution[]>([]);
const systemStatus = ref({
  database: true,
  orchestrator: true,
  redis: true,
});

// 生成中心指标
const generationStats = ref({
  total_calls: 0,
});
const agentStatsList = ref<AgentStat[]>([]);
const agentDailyTrend = ref<AgentTrend[]>([]);
const expertRanking = ref<ExpertRank[]>([]);
const agentFilterText = ref('');

const filteredAgentStats = computed(() => {
  if (!agentFilterText.value) return agentStatsList.value;
  const lowerText = agentFilterText.value.toLowerCase();
  return agentStatsList.value.filter((item) =>
    (item.agent_code || '').toLowerCase().includes(lowerText),
  );
});

// 图表 Ref
const trendChartRef = ref<EchartsUIType>();
const { renderEcharts: renderTrendChart } = useEcharts(trendChartRef);

const agDistChartRef = ref<EchartsUIType>();
const { renderEcharts: renderAgDistChart } = useEcharts(agDistChartRef);

const aiModelCostChartRef = ref<EchartsUIType>();
const { renderEcharts: renderAiModelCostChart } =
  useEcharts(aiModelCostChartRef);

const aiStageLatencyChartRef = ref<EchartsUIType>();
const { renderEcharts: renderAiStageLatencyChart } = useEcharts(
  aiStageLatencyChartRef,
);

const agentDistChartRef = ref<EchartsUIType>();
const { renderEcharts: renderAgentDistChart } = useEcharts(agentDistChartRef);

const rlhfIssueChartRef = ref<EchartsUIType>();
const { renderEcharts: renderRlhfIssueChart } = useEcharts(rlhfIssueChartRef);

const filterOption = (input: string, option: DefaultOptionType) => {
  return String(option.label ?? '')
    .toLowerCase()
    .includes(input.toLowerCase());
};

function formatRelativeTime(dateStr: string): string {
  if (!dateStr) return '-';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMs / 3_360_000);
  const diffDays = Math.floor(diffMs / 86_400_000);

  if (diffMinutes < 1) return '刚刚';
  if (diffMinutes < 60) return `${diffMinutes}分钟前`;
  if (diffHours < 24) return `${diffHours}小时前`;
  if (diffDays < 7) return `${diffDays}天前`;
  return formatDateTime(dateStr);
}

/** 加载筛选选项 */
async function loadFilterOptions() {
  try {
    const tenants = await getTenantSimpleListApi();
    tenantOptions.value = tenants.map((t: TenantApi.SimpleItem) => ({
      label: `${t.tenant_name} (${t.tenant_code})`,
      value: t.id,
    }));

    const firstTenantId = filters.value.tenantId?.[0];
    const [activities, agents] = await Promise.all([
      getActivitySimpleListApi(firstTenantId),
      getAgentSimpleListApi(firstTenantId),
    ]);

    activityOptions.value = activities.map((a: ActivityApi.SimpleItem) => ({
      label: `${a.activity_name} (${a.activity_code})`,
      value: a.id,
    }));

    agentOptions.value = agents.map((a: AgentApi.SimpleItem) => ({
      label: `${a.agent_name} (${a.agent_code})`,
      value: a.agent_code,
    }));
  } catch (error: unknown) {
    logger.error('加载筛选选项失败:', error);
  }
}

async function fetchDashboardData() {
  loading.value = true;
  try {
    const [start, end] = dateRange.value;
    const params = {
      agent_code: filters.value.agentCode,
      end_date: end.add(1, 'day').format('YYYY-MM-DD'),
      start_date: start.format('YYYY-MM-DD'),
      tenant_id: filters.value.tenantId,
      activity_id: filters.value.activityId,
    };

    // 并行请求核心数据
    const [
      overviewData,
      agOverviewRes,
      agDistRes,
      genCalls,
      genAgentStats,
      genTrend,
      totalLlmCost,
      avgCost,
      govCost,
      modelCost,
      stageLatency,
      rlhfLike,
      rlhfAdopt,
      rlhfEdit,
      rlhfIssues,
      expertRankRes,
      statsData,
    ] = await Promise.all([
      getDashboardOverviewApi(params),
      queryMetricApi<GenericMetric>({
        metric_key: 'ag_governance_overview',
        ...params,
      }),
      queryMetricApi<GenericMetric>({
        metric_key: 'ag_reject_distribution',
        ...params,
      }),
      queryMetricApi<GenericMetric>({
        metric_key: 'generation_total_calls',
        ...params,
      }),
      queryMetricApi<AgentStat>({
        metric_key: 'generation_agent_stats',
        ...params,
      }),
      queryMetricApi<AgentTrend>({
        metric_key: 'generation_agent_daily_trend',
        ...params,
      }),
      queryMetricApi<GenericMetric>({
        metric_key: 'total_llm_token_cost',
        ...params,
      }),
      queryMetricApi<GenericMetric>({
        metric_key: 'avg_cost_per_output',
        ...params,
      }),
      queryMetricApi<GenericMetric>({
        metric_key: 'governance_llm_cost',
        ...params,
      }),
      queryMetricApi<ModelCost>({
        metric_key: 'llm_cost_by_model',
        ...params,
      }),
      queryMetricApi<StageLatency>({
        metric_key: 'stage_avg_latency',
        ...params,
      }),
      queryMetricApi<GenericMetric>({
        metric_key: 'rlhf_user_like_rate',
        ...params,
      }),
      queryMetricApi<GenericMetric>({
        metric_key: 'rlhf_adopt_rate',
        ...params,
      }),
      queryMetricApi<GenericMetric>({
        metric_key: 'rlhf_edit_after_adopt_rate',
        ...params,
      }),
      queryMetricApi<IssueDist>({
        metric_key: 'rlhf_issue_type_distribution',
        ...params,
      }),
      queryMetricApi<ExpertRank>({
        metric_key: 'ge_expert_request_count',
        ...params,
      }),
      getDashboardStatsApi(),
    ]);

    // 1. 业务总览
    overviewStats.value = {
      ...overviewData.overview,
      adopt_rate: overviewData.overview.adopt_rate ?? 0,
    };
    updateTrendChart(overviewData.trend);

    // 2. AG 治理
    agStats.value = agOverviewRes.data?.[0] || {
      total_checks: 0,
      total_blocks: 0,
      block_rate: 0,
    };
    updateAgDistChart(agDistRes.data);

    // 3. 生成中心
    generationStats.value.total_calls = genCalls.data?.[0]?.total_count || 0;
    agentStatsList.value = genAgentStats.data || [];
    agentDailyTrend.value = genTrend.data || [];
    updateAgentDistChart(agentStatsList.value);

    expertRanking.value = (expertRankRes.data || [])
      .toSorted((a, b) => b.request_count - a.request_count)
      .slice(0, 10);

    // 4. AI 算力
    const costData = totalLlmCost.data || [];
    const costsByCurrency: Record<string, number> = {};
    let totalTokenCount = 0;

    costData.forEach((item: any) => {
      const cur = item.currency || 'USD';
      costsByCurrency[cur] =
        (costsByCurrency[cur] || 0) + (Number(item.total_cost) || 0);
      totalTokenCount +=
        Number(item.total_input_tokens) + Number(item.total_output_tokens) || 0;
    });

    aiCostStats.value.costs = costsByCurrency;
    aiCostStats.value.total_llm_token_cost = costsByCurrency.USD || 0; // 默认显示 USD
    aiCostStats.value.total_token_count = totalTokenCount;

    // 单内容成本按币种分组
    const avgCostData = avgCost.data || [];
    const avgCostsByCurrency: Record<string, number> = {};
    avgCostData.forEach((item: any) => {
      avgCostsByCurrency[item.currency || 'USD'] = Number(item.avg_cost) || 0;
    });
    aiCostStats.value.avg_costs = avgCostsByCurrency;
    aiCostStats.value.avg_cost_per_output = avgCostsByCurrency.USD || 0;

    // 治理成本按币种分组
    const govCostData = govCost.data || [];
    const govCostsByCurrency: Record<string, number> = {};
    govCostData.forEach((item: any) => {
      const cur = item.currency || 'USD';
      govCostsByCurrency[cur] =
        (govCostsByCurrency[cur] || 0) + (Number(item.total_cost) || 0);
    });
    aiCostStats.value.gov_costs = govCostsByCurrency;
    aiCostStats.value.governance_llm_cost = govCostsByCurrency.USD || 0;

    updateAiModelCostChart(modelCost.data);
    updateAiStageLatencyChart(stageLatency.data);

    // 5. RLHF
    rlhfStats.value.like_rate = Number(rlhfLike.data?.[0]?.like_rate) || 0;
    rlhfStats.value.dislike_rate =
      Number(rlhfLike.data?.[0]?.dislike_rate) || 0;
    rlhfStats.value.adopt_rate = Number(rlhfAdopt.data?.[0]?.adopt_rate) || 0;
    rlhfStats.value.edit_after_adopt_rate =
      Number(rlhfEdit.data?.[0]?.edit_after_adopt_rate) || 0;
    updateRlhfIssueChart(rlhfIssues.data);

    // 6. 系统状态
    systemStats.value = {
      deployedJobs: statsData.stats.deployed_jobs,
      runningJobs: statsData.stats.running_jobs,
      successRate: statsData.stats.success_rate,
      todayExecutions: statsData.stats.today_executions,
      totalExpertConfigs: statsData.stats.total_expert_configs,
      totalJobs: statsData.stats.total_jobs,
      totalPlugins: statsData.stats.total_plugins,
    };
    systemStatus.value = statsData.system_status;
    recentExecutions.value = statsData.recent_executions;
  } catch (error: unknown) {
    logger.error('Dashboard data fetch failed:', error);
    message.error('获取数据失败，请重试');
  } finally {
    loading.value = false;
  }
}

// --- 图表渲染函数 ---

/** 获取 CSS 变量并解析为 ECharts 可用的颜色字符串 */
function getVbenColor(varName: string) {
  if (typeof window === 'undefined') return '';
  const style = getComputedStyle(document.documentElement);
  const value = style.getPropertyValue(varName).trim();
  if (!value) return '';
  return value.includes('(') ? value : `hsl(${value})`;
}

function updateTrendChart(trendData: DashboardApi.DailyTrendItem[]) {
  const dates = [...new Set(trendData.map((item) => item.date))].toSorted();
  // 提取币种列表
  const currencies = [
    ...new Set(trendData.map((item) => (item as any).currency || 'USD')),
  ];

  const series: any[] = [
    {
      name: '内容产量',
      type: 'bar',
      data: dates.map((d) => {
        const dayData = trendData.filter((i) => i.date === d);
        return dayData.reduce((sum, i) => sum + i.content_count, 0);
      }),
      itemStyle: { color: getVbenColor('--primary') },
    },
    {
      name: '平均耗时 (ms)',
      type: 'line',
      data: dates.map((d) => {
        const dayData = trendData.filter((i) => i.date === d);
        const count = dayData.length;
        return count > 0
          ? Math.round(
              dayData.reduce((sum, i) => sum + (i.avg_latency_ms || 0), 0) /
                count,
            )
          : 0;
      }),
      smooth: true,
      itemStyle: { color: getVbenColor('--warning') },
    },
  ];

  // 为每个币种添加一条成本线
  currencies.forEach((cur) => {
    series.push({
      name: `成本 (${cur})`,
      type: 'line',
      yAxisIndex: 1,
      data: dates.map((d) => {
        const dayCurData = trendData.find(
          (i) => i.date === d && ((i as any).currency || 'USD') === cur,
        );
        return dayCurData ? Number(dayCurData.daily_cost || 0).toFixed(2) : 0;
      }),
      smooth: true,
      // 如果是 CNY 用红色，USD 用不同的红色或者通过 getVbenColor 稍微区别
      itemStyle: { color: cur === 'CNY' ? '#ff4d4f' : '#ff7875' },
    });
  });

  renderTrendChart({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: {
      data: [
        '内容产量',
        ...currencies.map((cur) => `成本 (${cur})`),
        '平均耗时 (ms)',
      ],
      bottom: 0,
    },
    grid: { left: '3%', right: '4%', bottom: '10%', containLabel: true },
    xAxis: { type: 'category', data: dates },
    yAxis: [
      { type: 'value', name: '产量', minInterval: 1 },
      {
        type: 'value',
        name: '成本',
        position: 'right',
        axisLabel: { formatter: (val: number) => `${val}` },
      },
    ],
    series,
  });
}

function updateAgDistChart(data: any[]) {
  renderAgDistChart({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { orient: 'vertical', left: 'left' },
    color: [
      getVbenColor('--primary'),
      getVbenColor('--success'),
      getVbenColor('--warning'),
      getVbenColor('--destructive'),
      getVbenColor('--muted-foreground'),
    ],
    series: [
      {
        name: '拦截分布',
        type: 'pie',
        radius: '50%',
        data: (data || []).map((i) => ({
          name: i.stage,
          value: Number(i.block_count),
        })),
      },
    ],
  });
}

function updateAgentDistChart(data: any[]) {
  renderAgentDistChart({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    color: [
      getVbenColor('--primary'),
      getVbenColor('--success'),
      getVbenColor('--warning'),
      getVbenColor('--destructive'),
      getVbenColor('--muted-foreground'),
    ],
    series: [
      {
        name: '调用分布',
        type: 'pie',
        radius: ['40%', '70%'],
        itemStyle: {
          borderRadius: 8,
          borderColor: getVbenColor('--background'),
          borderWidth: 2,
        },
        label: { show: false },
        data: (data || []).map((i) => ({
          name: i.agent_code,
          value: Number(i.total_calls),
        })),
      },
    ],
  });
}

function updateAiModelCostChart(data: any[]) {
  renderAiModelCostChart({
    title: { text: '模型成本分布', left: 'center' },
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        const item = data[params.dataIndex];
        const symbol = item.currency === 'CNY' ? '¥' : '$';
        return `${params.name}: ${symbol}${params.value} (${params.percent}%)`;
      },
    },
    color: [
      getVbenColor('--primary'),
      getVbenColor('--success'),
      getVbenColor('--warning'),
      getVbenColor('--destructive'),
      getVbenColor('--muted-foreground'),
    ],
    series: [
      {
        name: '成本',
        type: 'pie',
        radius: ['40%', '70%'],
        data: (data || []).map((i) => ({
          name: `${i.model_code} (${i.currency || 'USD'})`,
          value: Number(i.total_cost),
        })),
      },
    ],
  });
}

function updateAiStageLatencyChart(data: any[]) {
  renderAiStageLatencyChart({
    title: { text: '阶段平均耗时', left: 'center' },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: (data || []).map((i) => i.stage) },
    yAxis: { type: 'value', name: 'ms' },
    series: [
      {
        name: '耗时',
        type: 'bar',
        data: (data || []).map((i) => Math.round(i.avg_latency_ms || 0)),
        itemStyle: { color: getVbenColor('--success') },
      },
    ],
  });
}

function updateRlhfIssueChart(data: any[]) {
  renderRlhfIssueChart({
    title: { text: '反馈问题分布', left: 'center' },
    tooltip: { trigger: 'item' },
    color: [
      getVbenColor('--destructive'),
      getVbenColor('--warning'),
      getVbenColor('--primary'),
      getVbenColor('--success'),
      getVbenColor('--muted-foreground'),
    ],
    series: [
      {
        name: '问题类型',
        type: 'pie',
        radius: '50%',
        data: (data || []).map((i) => ({
          name: i.issue_type,
          value: Number(i.issue_count),
        })),
      },
    ],
  });
}

function getAgentTrendPoints(agentCode: string) {
  const trends = agentDailyTrend.value.filter(
    (item) => item.agent_code === agentCode,
  );
  if (trends.length === 0) return '';
  const counts = trends.map((t) => Number(t.call_count));
  const max = Math.max(...counts, 1);
  const step = 100 / (counts.length - 1 || 1);
  return counts.map((v, i) => `${i * step},${30 - (v / max) * 30}`).join(' ');
}

onMounted(() => {
  loadFilterOptions();
  fetchDashboardData();
});

watch(
  [
    dateRange,
    () => filters.value.tenantId,
    () => filters.value.activityId,
    () => filters.value.agentCode,
  ],
  () => {
    fetchDashboardData();
  },
);

const goTo = (path: string) => router.push(path);
</script>

<template>
  <div class="p-4">
    <!-- 粘性筛选头部 -->
    <div
      class="sticky top-0 z-10 -mx-4 -mt-4 mb-4 bg-background/80 p-4 shadow-sm backdrop-blur"
    >
      <div class="flex flex-wrap items-center justify-between gap-4">
        <Space wrap size="middle">
          <span class="text-xl font-bold">MAGA Console</span>
          <RangePicker v-model:value="dateRange" :ranges="ranges" />
          <Select
            v-model:value="filters.tenantId"
            :filter-option="filterOption"
            :options="tenantOptions"
            allow-clear
            class="w-48"
            mode="multiple"
            placeholder="所有租户"
            show-search
          />
          <Select
            v-model:value="filters.activityId"
            :filter-option="filterOption"
            :options="activityOptions"
            allow-clear
            class="w-48"
            mode="multiple"
            placeholder="所有活动"
            show-search
          />
          <Select
            v-model:value="filters.agentCode"
            :filter-option="filterOption"
            :options="agentOptions"
            allow-clear
            class="w-48"
            mode="multiple"
            placeholder="所有 Agent"
            show-search
          />
        </Space>
        <Space>
          <Button :loading="loading" type="primary" @click="fetchDashboardData">
            <template #icon>
              <ReloadOutlined />
            </template>
            刷新
          </Button>
        </Space>
      </div>
    </div>

    <!-- 核心 KPI -->
    <Row :gutter="16" class="mb-4">
      <Col
        v-for="(stat, index) in [
          {
            label: '任务总数',
            value: overviewStats.total_jobs,
            color: 'hsl(var(--primary))',
            icon: AppstoreOutlined,
            key: 'total_jobs',
          },
          {
            label: '内容产量',
            value: overviewStats.total_contents,
            color: 'hsl(var(--success))',
            icon: FileTextOutlined,
            key: 'total_contents',
          },
          {
            label: '总消耗',
            value: overviewStats.total_cost_detail
              ? overviewStats.total_cost_detail
                  .split('|')
                  .map((s) => {
                    const [cur, val] = s.split(':');
                    return `${cur === 'CNY' ? '¥' : '$'}${Number(val).toFixed(2)}`;
                  })
                  .join(' / ')
              : `$${(Number(overviewStats.total_cost) || 0).toFixed(2)}`,
            color: 'hsl(var(--destructive))',
            icon: DollarOutlined,
            key: 'total_cost',
            prefix: '',
            precision: undefined,
          },
          {
            label: '用户采纳率',
            value: overviewStats.adopt_rate,
            color: 'hsl(var(--primary))',
            icon: LikeOutlined,
            key: 'adopt_rate',
            suffix: '%',
          },
        ]"
        :key="index"
        :span="6"
      >
        <Card :bordered="false" class="h-full" hoverable>
          <Skeleton :loading="loading" :active="true" :paragraph="{ rows: 1 }">
            <Statistic
              :precision="stat.precision"
              :prefix="stat.prefix"
              :suffix="stat.suffix"
              :value="stat.value"
              :value-style="{ color: stat.color }"
            >
              <template #title>
                <span class="flex items-center">
                  <component :is="stat.icon" class="mr-2" />
                  {{ stat.label }}
                  <MetricHelp :metric-key="`dashboard_overview.${stat.key}`" />
                </span>
              </template>
            </Statistic>
          </Skeleton>
        </Card>
      </Col>
    </Row>

    <!-- 分域详情 Tabs -->
    <Tabs
      v-model:active-key="activeTab"
      class="mb-4 rounded-lg bg-card p-4 shadow-sm"
    >
      <!-- 1. 业务总览 -->
      <TabPane key="overview" tab="业务总览">
        <div class="mt-4 h-[450px] w-full">
          <EchartsUI ref="trendChartRef" />
        </div>
      </TabPane>

      <!-- 2. 生成分析 -->
      <TabPane key="ge" tab="生成分析">
        <Row :gutter="16" class="mt-4">
          <Col :span="12">
            <div class="mb-4 flex items-center justify-between">
              <Input.Search
                v-model:value="agentFilterText"
                allow-clear
                class="w-64"
                placeholder="搜索 Agent..."
              />
              <Statistic
                title="总调用量"
                :value="generationStats.total_calls"
              />
            </div>
            <div class="max-h-[500px] overflow-y-auto pr-2">
              <div class="grid grid-cols-2 gap-4">
                <Card
                  v-for="agent in filteredAgentStats"
                  :key="agent.agent_code"
                  :style="{
                    borderColor:
                      Number(agent.running_count) > 0
                        ? 'hsl(var(--primary))'
                        : 'hsl(var(--border))',
                  }"
                  class="border-l-4"
                  hoverable
                  size="small"
                >
                  <div class="mb-2 flex items-start justify-between">
                    <span
                      :title="agent.agent_code"
                      class="w-2/3 truncate font-bold"
                      >{{ agent.agent_code }}</span
                    >
                    <Tag
                      :color="
                        Number(agent.running_count) > 0
                          ? 'processing'
                          : 'default'
                      "
                    >
                      <template v-if="Number(agent.running_count) > 0" #icon>
                        <LoadingOutlined />
                      </template>
                      {{ Number(agent.running_count) > 0 ? '运行中' : '空闲' }}
                    </Tag>
                  </div>
                  <div class="mb-2 flex justify-between text-sm">
                    <span class="text-muted-foreground"
                      >今日调用: {{ agent.total_calls }}</span
                    >
                    <span class="font-medium text-blue-500"
                      >并发: {{ agent.running_count }}</span
                    >
                  </div>
                  <svg class="h-8 w-full">
                    <polyline
                      :points="getAgentTrendPoints(agent.agent_code)"
                      fill="none"
                      stroke="hsl(var(--primary))"
                      stroke-linecap="round"
                      stroke-width="2"
                    />
                  </svg>
                </Card>
                <Empty
                  v-if="filteredAgentStats.length === 0"
                  description="未找到匹配的 Agent"
                />
              </div>
            </div>
          </Col>
          <Col :span="12">
            <div class="border-l pl-4">
              <div class="mb-4 text-center font-bold">Expert 活跃排行 (P1)</div>
              <Table
                :columns="[
                  {
                    title: 'Expert Code',
                    dataIndex: 'expert_config_code',
                    key: 'code',
                  },
                  {
                    title: '调用量',
                    dataIndex: 'request_count',
                    key: 'count',
                    sorter: (a, b) => a.request_count - b.request_count,
                  },
                  {
                    title: '成功率',
                    dataIndex: 'success_rate',
                    key: 'rate',
                    customRender: ({ text }) => `${text}%`,
                  },
                ]"
                :data-source="expertRanking"
                :pagination="false"
                size="small"
              />
              <div class="mt-8 h-[300px] w-full">
                <div class="mb-4 text-center font-bold">Agent 调用分布</div>
                <EchartsUI ref="agentDistChartRef" />
              </div>
            </div>
          </Col>
        </Row>
      </TabPane>

      <!-- 3. 对齐与质量 -->
      <TabPane key="quality" tab="对齐与反馈">
        <Row :gutter="24" class="mt-4">
          <Col :span="12">
            <Card class="mb-4" size="small" title="AG 治理概览">
              <Row :gutter="16">
                <Col :span="8">
                  <Statistic title="审核数" :value="agStats.total_checks" />
                </Col>
                <Col :span="8">
                  <Statistic
                    title="拦截数"
                    :value="agStats.total_blocks"
                    value-style="color: hsl(var(--destructive))"
                  />
                </Col>
                <Col :span="8">
                  <Statistic
                    suffix="%"
                    title="拦截率"
                    :value="agStats.block_rate"
                  />
                </Col>
              </Row>
              <div class="mt-4 h-64"><EchartsUI ref="agDistChartRef" /></div>
            </Card>
          </Col>
          <Col :span="12">
            <Card size="small" title="RLHF 反馈分析">
              <Row :gutter="16">
                <Col :span="6">
                  <Statistic
                    suffix="%"
                    title="喜欢率"
                    :value="rlhfStats.like_rate"
                    value-style="color: hsl(var(--success))"
                  />
                </Col>
                <Col :span="6">
                  <Statistic
                    suffix="%"
                    title="不喜欢率"
                    :value="rlhfStats.dislike_rate"
                    value-style="color: hsl(var(--destructive))"
                  />
                </Col>
                <Col :span="6">
                  <Statistic
                    suffix="%"
                    title="采纳率"
                    :value="rlhfStats.adopt_rate"
                    value-style="color: hsl(var(--primary))"
                  />
                </Col>
                <Col :span="6">
                  <Statistic
                    suffix="%"
                    title="采纳后修改"
                    :value="rlhfStats.edit_after_adopt_rate"
                  />
                </Col>
              </Row>
              <div class="mt-4 h-64"><EchartsUI ref="rlhfIssueChartRef" /></div>
            </Card>
          </Col>
        </Row>
      </TabPane>

      <!-- 4. AI 算力分析 -->
      <TabPane key="cost" tab="效能与成本">
        <Row :gutter="16" class="mt-4">
          <Col :span="6">
            <Card class="mb-4 bg-muted/30" size="small">
              <div class="ant-statistic">
                <div class="ant-statistic-title">Token 总成本</div>
                <div class="ant-statistic-content">
                  <div
                    v-for="(val, cur) in aiCostStats.costs"
                    :key="cur"
                    class="text-lg font-bold"
                  >
                    {{ cur === 'CNY' ? '¥' : '$' }}{{ (val || 0).toFixed(2) }}
                  </div>
                  <div v-if="Object.keys(aiCostStats.costs).length === 0">
                    -
                  </div>
                </div>
              </div>
            </Card>
          </Col>
          <Col :span="6">
            <Card class="mb-4 bg-muted/30" size="small">
              <div class="ant-statistic">
                <div class="ant-statistic-title">单内容成本</div>
                <div class="ant-statistic-content">
                  <div
                    v-for="(val, cur) in aiCostStats.avg_costs"
                    :key="cur"
                    class="text-lg font-bold"
                  >
                    {{ cur === 'CNY' ? '¥' : '$' }}{{ (val || 0).toFixed(4) }}
                  </div>
                  <div v-if="Object.keys(aiCostStats.avg_costs).length === 0">
                    -
                  </div>
                </div>
              </div>
            </Card>
          </Col>
          <Col :span="6">
            <Card class="mb-4 bg-muted/30" size="small">
              <Statistic
                title="Token 总消耗"
                :value="aiCostStats.total_token_count"
                suffix=" tokens"
              />
            </Card>
          </Col>
          <Col :span="6">
            <Card class="mb-4 bg-muted/30" size="small">
              <div class="ant-statistic">
                <div class="ant-statistic-title">治理成本</div>
                <div class="ant-statistic-content">
                  <div
                    v-for="(val, cur) in aiCostStats.gov_costs"
                    :key="cur"
                    class="text-lg font-bold"
                  >
                    {{ cur === 'CNY' ? '¥' : '$' }}{{ (val || 0).toFixed(2) }}
                  </div>
                  <div v-if="Object.keys(aiCostStats.gov_costs).length === 0">
                    -
                  </div>
                </div>
              </div>
            </Card>
          </Col>
        </Row>
        <Row :gutter="16">
          <Col :span="12">
            <div class="h-80"><EchartsUI ref="aiModelCostChartRef" /></div>
          </Col>
          <Col :span="12">
            <div class="h-80"><EchartsUI ref="aiStageLatencyChartRef" /></div>
          </Col>
        </Row>
      </TabPane>
    </Tabs>

    <!-- 下方补充信息 -->
    <Row :gutter="16">
      <Col :span="16">
        <Card :bordered="false" size="small" title="最近执行记录">
          <template #extra>
            <Button type="link" @click="goTo('/trace/list')"> 查看全部 </Button>
          </template>
          <List :data-source="recentExecutions" :loading="loading" size="small">
            <template #renderItem="{ item }">
              <ListItem>
                <ListItemMeta
                  :description="`Expert: ${item.expert_config_code}`"
                  :title="item.job_name"
                />
                <template #actions>
                  <span class="text-xs text-muted-foreground">{{
                    formatRelativeTime(item.created_at)
                  }}</span>
                  <Tag v-if="item.status === 'success'" color="success">
                    <template #icon>
                      <CheckCircleOutlined />
                    </template>
                    成功
                  </Tag>
                  <Tag v-else-if="item.status === 'failed'" color="error">
                    <template #icon>
                      <CloseCircleOutlined />
                    </template>
                    失败
                  </Tag>
                  <Tag v-else color="processing">
                    <template #icon>
                      <LoadingOutlined />
                    </template>
                    执行中
                  </Tag>
                </template>
              </ListItem>
            </template>
          </List>
        </Card>
      </Col>
      <Col :span="8">
        <Card :bordered="false" class="mb-4" size="small" title="系统状态">
          <div class="space-y-3">
            <div
              v-for="(val, key) in systemStatus"
              :key="key"
              class="flex items-center justify-between capitalize"
            >
              <span>{{ key }}</span>
              <Badge
                :status="val ? 'success' : 'error'"
                :text="val ? '正常' : '异常'"
              />
            </div>
          </div>
        </Card>
        <Card :bordered="false" size="small" title="资源概览">
          <div class="grid grid-cols-2 gap-4 text-center">
            <div
              class="cursor-pointer rounded bg-muted/50 p-2 hover:bg-muted"
              @click="goTo('/config/plugin')"
            >
              <div class="mb-1 text-xl">
                <SettingOutlined />
              </div>
              <div class="text-xs">插件: {{ systemStats.totalPlugins }}</div>
            </div>
            <div
              class="cursor-pointer rounded bg-muted/50 p-2 hover:bg-muted"
              @click="goTo('/expert/calibration')"
            >
              <div class="mb-1 text-xl text-primary">
                <FireOutlined />
              </div>
              <div class="text-xs">
                配置: {{ systemStats.totalExpertConfigs }}
              </div>
            </div>
            <div
              class="cursor-pointer rounded bg-muted/50 p-2 hover:bg-muted"
              @click="goTo('/job/list')"
            >
              <div class="mb-1 text-xl">
                <AppstoreOutlined />
              </div>
              <div class="text-xs">已部署: {{ systemStats.deployedJobs }}</div>
            </div>
            <div
              class="cursor-pointer rounded bg-muted/50 p-2 hover:bg-muted"
              @click="goTo('/job/list')"
            >
              <div class="mb-1 text-xl text-destructive">
                <FireOutlined />
              </div>
              <div class="text-xs">今日: {{ systemStats.todayExecutions }}</div>
            </div>
          </div>
        </Card>
      </Col>
    </Row>
  </div>
</template>

<style scoped>
:deep(.ant-tabs-nav) {
  margin-bottom: 0;
}

:deep(.ant-statistic-title) {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

:deep(.ant-statistic-content) {
  font-weight: 600;
}

.bg-muted {
  background-color: hsl(var(--muted));
}

.text-muted-foreground {
  color: hsl(var(--muted-foreground));
}
</style>
