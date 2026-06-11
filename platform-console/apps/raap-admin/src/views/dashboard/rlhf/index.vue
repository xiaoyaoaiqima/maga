<script setup lang="ts">
// @ts-nocheck
/* TODO: 逐步修复以下 lint 错误
- unused-vars: 删除更多未使用的类型、变量和函数
- unicorn/prefer-ternary: 将 if 语句改为三元表达式
- unicorn/no-nested-ternary: 重构嵌套三元表达式
- unicorn/no-array-sort: 将 Array#sort 改为 Array#toSorted
- vue/no-unused-vars: 删除模板中未使用的变量
- vue/no-unused-refs: 删除未使用的 ref
- prettier/prettier: 格式化问题
*/
import type { DefaultOptionType } from 'ant-design-vue/es/select';

import type { EchartsUIType } from '@vben/plugins/echarts';

import type { ActivityApi, AgentApi, TenantApi } from '#/api/core/business';

import { nextTick, onMounted, ref, watch } from 'vue';

import { EchartsUI, useEcharts } from '@vben/plugins/echarts';
import { usePreferences } from '@vben/preferences';

import {
  ClearOutlined,
  DownOutlined,
  QuestionCircleOutlined,
  RightOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue';
import {
  Button,
  Card,
  Col,
  Empty,
  Modal,
  RangePicker,
  Row,
  Select,
  Skeleton,
  Table,
  Tooltip,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import {
  getActivitySimpleListApi,
  getAgentSimpleListApi,
  getTenantSimpleListApi,
} from '#/api/core/business';
import { queryMetricApi, queryMetricPaginatedApi } from '#/api/core/dashboard';
import CountTo from '#/components/CountTo.vue';

// ==================== 类型定义 ====================

// RLHF 人工专家反馈报告数据类型
interface RLHFInspectionStats {
  total_inspection_count: number;
  like_count: number;
  dislike_count: number;
  like_rate: number;
  dislike_rate: number;
  like_edit_rate: number;
  // 新增字段
  expert_count?: number; // 人工专家总数
  illegal_count?: number; // 不合法
  non_compliant_count?: number; // 不合规
  unreasonable_count?: number; // 不合理
  off_purpose_count?: number; // 不合目的
}

// RLHF 雷达图评分维度
interface RLHFScoreDimension {
  name: string;
  value: number;
  modelScore?: number; // AI模型评分（用于对比图）
  inspectionScore?: number; // 抽检评分（用于对比图）
  diff?: number; // 差异百分比
}

interface RLHFIssueTagDistribution {
  tag_id: number;
  tag_name: string;
  tag_category: string;
  count: number;
}

interface RLHFIssueTagWordCloud {
  name: string;
  value: number;
}

// 反馈词文章列表项
interface FeedbackTagArticleItem {
  article_id: number;
  title: string;
  content_preview: string;
  create_time: string;
}

// RLHF 抽检详情数据类型
interface RLHFInspectionDetailItem {
  article_id: number;
  inspection_title: null | string;
  content_preview: null | string;
  inspection_result: string;
  inspector_name: null | string;
  inspection_time: null | string;
  modified_title: null | string;
  modified_content_preview: null | string;
}

// RLHF 改进点摘要数据类型
interface RLHFImprovementItem {
  feedback_id: number;
  selected_text: null | string;
  comment: null | string;
  user_name: null | string;
  create_time: null | string;
}

// ==================== 状态 ====================
const loading = ref(true);
const dataUpdateTime = ref(dayjs().format('YYYY-MM-DD HH:mm'));

// 模块折叠状态
const collapsedSections = ref<Record<string, boolean>>({
  rlhf: false, // 人工专家反馈
});

// 切换折叠状态
const toggleSection = (section: string) => {
  collapsedSections.value[section] = !collapsedSections.value[section];
};

// 日期范围（默认最近 30 天）
const dateRange = ref<[dayjs.Dayjs, dayjs.Dayjs]>([
  dayjs().subtract(29, 'day'),
  dayjs(),
]);

// 时间预设
const presets = [
  {
    label: '最近 7 天',
    value: [dayjs().subtract(6, 'day'), dayjs()] as [dayjs.Dayjs, dayjs.Dayjs],
  },
  {
    label: '最近 15 天',
    value: [dayjs().subtract(14, 'day'), dayjs()] as [dayjs.Dayjs, dayjs.Dayjs],
  },
  {
    label: '最近 30 天',
    value: [dayjs().subtract(29, 'day'), dayjs()] as [dayjs.Dayjs, dayjs.Dayjs],
  },
  {
    label: '最近 90 天',
    value: [dayjs().subtract(89, 'day'), dayjs()] as [dayjs.Dayjs, dayjs.Dayjs],
  },
  {
    label: '最近 1 年',
    value: [dayjs().subtract(1, 'year'), dayjs()] as [dayjs.Dayjs, dayjs.Dayjs],
  },
];

// 筛选状态（UI绑定用）
const filters = ref({
  activityId: undefined as number[] | undefined,
  agentCode: undefined as string[] | undefined,
  tenantId: undefined as number[] | undefined,
});

// 已确认的筛选状态（用于实际数据请求，防止定时刷新时使用未确认的筛选条件）
const confirmedFilters = ref({
  activityId: undefined as number[] | undefined,
  agentCode: undefined as string[] | undefined,
  tenantId: undefined as number[] | undefined,
});

// 筛选选项
const tenantOptions = ref<Array<{ label: string; value: number }>>([]);
const activityOptions = ref<Array<{ label: string; value: number }>>([]);
const agentOptions = ref<Array<{ label: string; value: string }>>([]);

// RLHF 人工专家反馈报告数据
const rlhfInspectionStats = ref<RLHFInspectionStats>({
  total_inspection_count: 0,
  like_count: 0,
  dislike_count: 0,
  like_rate: 0,
  dislike_rate: 0,
  like_edit_rate: 0,
  expert_count: 123, // mock
  illegal_count: 20, // mock
  non_compliant_count: 20, // mock
  unreasonable_count: 20, // mock
  off_purpose_count: 20, // mock
});
const rlhfIssueTagDistribution = ref<RLHFIssueTagDistribution[]>([]);
const rlhfIssueTagWordCloud = ref<RLHFIssueTagWordCloud[]>([]);

// 反馈词文章弹窗状态
const feedbackArticleModalVisible = ref(false);
const feedbackArticleModalLoading = ref(false);
const selectedFeedbackTag = ref<null | RLHFIssueTagDistribution>(null);
const feedbackTagArticleList = ref<FeedbackTagArticleItem[]>([]);
const feedbackArticlePagination = ref({
  current: 1,
  pageSize: 10,
  total: 0,
});

const HUMAN_RLHF_DEFAULT_SCORES = [78, 74, 81, 69, 76, 83];

function getDefaultHumanScore(index: number) {
  if (HUMAN_RLHF_DEFAULT_SCORES.length === 0) return 76;
  return HUMAN_RLHF_DEFAULT_SCORES[index % HUMAN_RLHF_DEFAULT_SCORES.length];
}

// RLHF 雷达图数据（暂时写死，名称随专家维度动态生成）
const rlhfRadarScores = ref<RLHFScoreDimension[]>([]);

const rlhfInspectionDetailList = ref<RLHFInspectionDetailItem[]>([]);
const rlhfDetailPagination = ref({
  current: 1,
  pageSize: 10,
  total: 0,
});

// RLHF 改进点摘要数据
const rlhfImprovementList = ref<RLHFImprovementItem[]>([]);
const rlhfImprovementPagination = ref({
  current: 1,
  pageSize: 10,
  total: 0,
});

// 图表 Ref
// RLHF 人工专家反馈报告图表 Ref
const rlhfIssueBarChartRef = ref<EchartsUIType>();
const { renderEcharts: renderRLHFIssueBarChart } =
  useEcharts(rlhfIssueBarChartRef);
const rlhfWordCloudChartRef = ref<EchartsUIType>();
const { renderEcharts: renderRLHFWordCloudChart } = useEcharts(
  rlhfWordCloudChartRef,
);

// RLHF 雷达图 Ref
const rlhfRadarChartRef = ref<EchartsUIType>();
const { renderEcharts: renderRLHFRadarChart } = useEcharts(rlhfRadarChartRef);
const rlhfRadarCompareChartRef = ref<EchartsUIType>();
const { renderEcharts: renderRLHFRadarCompareChart } = useEcharts(
  rlhfRadarCompareChartRef,
);

// ==================== 主题切换监听 ====================
const { isDark } = usePreferences();

// 监听主题变化，重新渲染所有 ECharts 图表
watch(isDark, async () => {
  // 等待 CSS 变量更新完成
  await nextTick();
  setTimeout(() => {
    // 重新渲染所有图表以应用新的主题颜色
    updateRLHFIssueBarChart();
    updateRLHFWordCloudChart();
    updateRLHFRadarChart();
    updateRLHFRadarCompareChart();
  }, 100);
});

// ==================== RLHF 雷达图专家 ====================
// RLHF 雷达图数据（暂时写死，使用默认专家维度）
const scoringExperts = ref<Array<{ expert_func: string; expert_name: string }>>(
  [
    { expert_func: 'marketing', expert_name: '营销性' },
    { expert_func: 'grace', expert_name: '优美性' },
    { expert_func: 'quality', expert_name: '质量性' },
    { expert_func: 'brand', expert_name: '品牌性' },
    { expert_func: 'creativity', expert_name: '创意性' },
    { expert_func: 'persona', expert_name: '人设性' },
  ],
);

function buildScoringExperts() {
  // RLHF 专家维度保持固定，不需要动态构建
}

function buildHumanRadarScores() {
  if (scoringExperts.value.length === 0) {
    rlhfRadarScores.value = [];
    return;
  }
  rlhfRadarScores.value = scoringExperts.value.map((expert, index) => ({
    name: expert.expert_name,
    value: getDefaultHumanScore(index),
  }));
}

// ==================== 常量定义 ====================

// ==================== 方法 ====================
const filterOption = (input: string, option: DefaultOptionType) => {
  return String(option.label ?? '')
    .toLowerCase()
    .includes(input.toLowerCase());
};

/** 获取 CSS 变量并解析为 ECharts 可用的颜色字符串 */
function getVbenColor(varName: string) {
  if (typeof window === 'undefined') return '';
  const style = getComputedStyle(document.documentElement);
  const value = style.getPropertyValue(varName).trim();
  if (!value) return '';
  return value.includes('(') ? value : `hsl(${value})`;
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

/** 构建请求参数（使用已确认的筛选条件） */
function buildParams() {
  const [start, end] = dateRange.value;
  return {
    agent_code: confirmedFilters.value.agentCode,
    end_date: end.add(1, 'day').format('YYYY-MM-DD'),
    start_date: start.format('YYYY-MM-DD'),
    tenant_id: confirmedFilters.value.tenantId,
    activity_id: confirmedFilters.value.activityId,
  };
}

/** 加载所有数据 */
async function fetchAllData() {
  loading.value = true;
  try {
    const params = buildParams();

    // 并行请求 RLHF 数据
    const [rlhfStatsRes, rlhfIssueDistRes, rlhfWordCloudRes] =
      await Promise.all([
        queryMetricApi<RLHFInspectionStats>({
          metric_key: 'rlhf_inspection_stats',
          ...params,
        }),
        queryMetricApi<RLHFIssueTagDistribution>({
          metric_key: 'rlhf_inspection_issue_tag_distribution',
          ...params,
        }),
        queryMetricApi<RLHFIssueTagWordCloud>({
          metric_key: 'rlhf_inspection_issue_tag_wordcloud',
          ...params,
        }),
      ]);

    // RLHF 人工专家反馈报告数据
    rlhfInspectionStats.value = rlhfStatsRes.data?.[0] || {
      total_inspection_count: 0,
      like_count: 0,
      dislike_count: 0,
      like_rate: 0,
      dislike_rate: 0,
      like_edit_rate: 0,
      expert_count: 0,
      illegal_count: 0,
      non_compliant_count: 0,
      unreasonable_count: 0,
      off_purpose_count: 0,
    };
    rlhfIssueTagDistribution.value = rlhfIssueDistRes.data || [];
    rlhfIssueTagWordCloud.value = rlhfWordCloudRes.data || [];

    buildScoringExperts();
    buildHumanRadarScores();

    // 并行加载分页数据
    await Promise.all([
      fetchRLHFInspectionDetailData(),
      fetchRLHFImprovementData(),
    ]);
  } catch (error: unknown) {
    logger.error('加载数据失败:', error);
  } finally {
    loading.value = false;
    dataUpdateTime.value = dayjs().format('YYYY-MM-DD HH:mm');
  }
}

// ==================== 后台静默刷新 ====================
// 刷新间隔（毫秒）- 10秒
const REFRESH_INTERVAL = 10 * 1000;
let refreshTimer: null | ReturnType<typeof setInterval> = null;

/** 静默刷新数据（不显示 loading 状态） */
async function silentRefreshData() {
  try {
    const params = buildParams();
    // 静默模式：不显示错误弹窗
    const silentOptions = { silentError: true };

    // 只刷新 RLHF 数据
    const rlhfStatsRes = await queryMetricApi<RLHFInspectionStats>(
      {
        metric_key: 'rlhf_inspection_stats',
        ...params,
      },
      silentOptions,
    );

    // 更新 RLHF 数据
    rlhfInspectionStats.value = rlhfStatsRes.data?.[0] || {
      total_inspection_count: 0,
      like_count: 0,
      dislike_count: 0,
      like_rate: 0,
      dislike_rate: 0,
      like_edit_rate: 0,
      expert_count: 0,
      illegal_count: 0,
      non_compliant_count: 0,
      unreasonable_count: 0,
      off_purpose_count: 0,
    };

    // 更新时间
    dataUpdateTime.value = dayjs().format('YYYY-MM-DD HH:mm');
  } catch (error) {
    console.error('静默刷新数据失败:', error);
  }
}

/** 启动定时刷新 */
function startAutoRefresh() {
  if (refreshTimer) return;
  refreshTimer = setInterval(silentRefreshData, REFRESH_INTERVAL);
}

/** 加载 RLHF 抽检详情（获取全部数据） */
async function fetchRLHFInspectionDetailData() {
  try {
    const params = buildParams();
    const res = await queryMetricPaginatedApi<RLHFInspectionDetailItem>({
      metric_key: 'rlhf_inspection_detail_list',
      ...params,
      page: 1,
      page_size: 500, // 获取全部数据
    });

    rlhfInspectionDetailList.value = res.data || [];
    rlhfDetailPagination.value.total = res.pagination?.total || 0;
  } catch (error: unknown) {
    console.error('加载 RLHF 抽检详情失败:', error);
  }
}

/** 加载 RLHF 改进点摘要（获取全部数据） */
async function fetchRLHFImprovementData() {
  try {
    const params = buildParams();
    const res = await queryMetricPaginatedApi<RLHFImprovementItem>({
      metric_key: 'rlhf_improvement_summary',
      ...params,
      page: 1,
      page_size: 500, // 获取全部数据
    });

    rlhfImprovementList.value = res.data || [];
    rlhfImprovementPagination.value.total = res.pagination?.total || 0;
  } catch (error: unknown) {
    console.error('加载 RLHF 改进点摘要失败:', error);
  }
}

/** 查看反馈词文章列表 */
async function handleViewFeedbackArticles(record: RLHFIssueTagDistribution) {
  selectedFeedbackTag.value = record;
  feedbackArticleModalVisible.value = true;
  feedbackArticleModalLoading.value = true;
  feedbackArticlePagination.value.current = 1;

  try {
    const params = buildParams();
    const res = await queryMetricPaginatedApi<FeedbackTagArticleItem>({
      metric_key: 'rlhf_feedback_tag_articles',
      ...params,
      tag_id: record.tag_id,
      page: 1,
      page_size: 500, // 获取全部数据
    });

    feedbackTagArticleList.value = res.data || [];
    feedbackArticlePagination.value.total = res.pagination?.total || 0;
  } catch (error: unknown) {
    console.error('加载反馈词文章列表失败:', error);
    feedbackTagArticleList.value = [];
  } finally {
    feedbackArticleModalLoading.value = false;
  }
}

/** 关闭反馈词文章弹窗 */
function handleCloseFeedbackArticleModal() {
  feedbackArticleModalVisible.value = false;
  selectedFeedbackTag.value = null;
  feedbackTagArticleList.value = [];
}

/** 更新 RLHF 问题标签柱状图 */
function updateRLHFIssueBarChart() {
  const data = rlhfIssueTagDistribution.value;

  if (data.length === 0) {
    renderRLHFIssueBarChart({
      graphic: {
        type: 'text',
        left: 'center',
        top: 'middle',
        style: {
          text: '暂无数据',
          fill: getVbenColor('--muted-foreground'),
          fontSize: 14,
        },
      },
    });
    return;
  }

  // 颜色配置 - 按分类
  const categoryColors: Record<string, string> = {
    CONTENT: '#3b82f6', // 蓝色 - 内容问题
    MODEL: '#22c55e', // 绿色 - 模型问题
    BRAND: '#f59e0b', // 橙色 - 品牌问题
    COMPLIANCE: '#ef4444', // 红色 - 合规问题
    OTHER: '#8b5cf6', // 紫色 - 其他
  };

  const xAxisData = data.map((item) => item.tag_name);
  const seriesData = data.map((item) => ({
    value: item.count,
    itemStyle: {
      color: categoryColors[item.tag_category] || '#8b5cf6',
    },
  }));

  renderRLHFIssueBarChart({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: Array<{ name: string; value: number }>) => {
        if (!params || params.length === 0) return '';
        const item = data.find((d) => d.tag_name === params[0].name);
        return `<b>${params[0].name}</b><br/>数量: ${params[0].value}<br/>分类: ${item?.tag_category || '-'}`;
      },
    },
    grid: {
      left: 60,
      right: 20,
      top: 20,
      bottom: 80,
    },
    xAxis: {
      type: 'category',
      data: xAxisData,
      axisLine: {
        lineStyle: { color: getVbenColor('--border') },
      },
      axisLabel: {
        color: getVbenColor('--muted-foreground'),
        fontSize: 10,
        rotate: 45,
        interval: 0,
      },
      axisTick: {
        alignWithLabel: true,
      },
    },
    yAxis: {
      type: 'value',
      axisLine: {
        lineStyle: { color: getVbenColor('--border') },
      },
      axisLabel: {
        color: getVbenColor('--muted-foreground'),
      },
      splitLine: {
        lineStyle: { color: getVbenColor('--border'), type: 'dashed' },
      },
    },
    series: [
      {
        type: 'bar',
        data: seriesData,
        barMaxWidth: 40,
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
        },
        label: {
          show: true,
          position: 'top',
          color: getVbenColor('--muted-foreground'),
          fontSize: 10,
        },
      },
    ],
  });
}

/** 更新 RLHF 问题标签词云 */
function updateRLHFWordCloudChart() {
  const data = rlhfIssueTagWordCloud.value;

  if (data.length === 0) {
    renderRLHFWordCloudChart({
      graphic: {
        type: 'text',
        left: 'center',
        top: 'middle',
        style: {
          text: '暂无数据',
          fill: getVbenColor('--muted-foreground'),
          fontSize: 14,
        },
      },
    });
    return;
  }

  // 词云颜色数组 - 使用暖色系为主
  const wordCloudColors = [
    '#ef4444', // 红色
    '#f97316', // 橙色
    '#f59e0b', // 琥珀色
    '#84cc16', // 黄绿色
    '#22c55e', // 绿色
    '#14b8a6', // 青色
    '#06b6d4', // 天蓝色
    '#3b82f6', // 蓝色
    '#8b5cf6', // 紫色
    '#ec4899', // 粉色
  ];

  const wordCloudData = data.map((item, index) => ({
    name: item.name,
    value: item.value,
    textStyle: {
      color: wordCloudColors[index % wordCloudColors.length],
    },
  }));

  renderRLHFWordCloudChart({
    tooltip: {
      show: true,
      backgroundColor: 'rgba(30, 58, 95, 0.95)',
      borderColor: 'transparent',
      borderRadius: 8,
      padding: [8, 12],
      textStyle: { color: '#fff', fontSize: 12 },
      formatter: (params: { name: string; value: number }) => {
        return `<div style="font-weight: 500;">${params.name}: <span style="color: #60a5fa; font-weight: 700;">${params.value}</span> 次</div>`;
      },
    },
    series: [
      {
        type: 'wordCloud',
        shape: 'circle',
        left: 'center',
        top: 'center',
        width: '90%',
        height: '90%',
        sizeRange: [16, 65],
        rotationRange: [-45, 45],
        rotationStep: 15,
        gridSize: 10,
        drawOutOfBound: false,
        textStyle: {
          fontFamily: 'system-ui, -apple-system, sans-serif',
          fontWeight: 'bold',
        },
        emphasis: {
          focus: 'self',
          textStyle: {
            textShadowBlur: 15,
            textShadowColor: 'rgba(0, 0, 0, 0.4)',
          },
        },
        data: wordCloudData,
      },
    ],
  });
}

/** 更新 RLHF 人工专家综合评分雷达图 */
function updateRLHFRadarChart() {
  const data = rlhfRadarScores.value;
  const values = data.map((item) => item.value);

  // 构建雷达图指标
  const indicator = data.map((item) => ({
    name: item.name,
    max: 100,
  }));

  renderRLHFRadarChart({
    animationDuration: 1800,
    animationEasing: 'elasticOut',
    tooltip: {
      show: true,
      trigger: 'item',
      confine: true,
      backgroundColor: 'rgba(30, 58, 95, 0.95)',
      borderColor: 'transparent',
      borderRadius: 8,
      padding: [10, 14],
      textStyle: { color: '#fff', fontSize: 12 },
      formatter: (params: { name: string; value: number[] }) => {
        if (!params || !params.value) return '';
        let result =
          '<div style="font-weight:600;margin-bottom:8px;border-bottom:1px solid rgba(255,255,255,0.2);padding-bottom:6px;">综合评分</div>';
        data.forEach((item, i) => {
          const val = params.value[i];
          let color;
          if (val >= 80) {
            color = '#22c55e';
          } else if (val >= 60) {
            color = '#f59e0b';
          } else {
            color = '#ef4444';
          }
          result += `<div style="margin:4px 0;">${item.name}: <span style="color:${color};font-weight:600;">${val}</span></div>`;
        });
        return result;
      },
    },
    radar: {
      indicator,
      center: ['50%', '50%'],
      radius: '60%',
      startAngle: 90,
      splitNumber: 5,
      shape: 'polygon',
      axisName: {
        color: getVbenColor('--foreground'),
        fontSize: 11,
        fontWeight: 500,
      },
      axisNameGap: 12,
      splitArea: {
        show: true,
        areaStyle: {
          color: [
            'rgba(59, 130, 246, 0.02)',
            'rgba(59, 130, 246, 0.05)',
            'rgba(59, 130, 246, 0.08)',
            'rgba(59, 130, 246, 0.12)',
            'rgba(59, 130, 246, 0.16)',
          ],
        },
      },
      splitLine: {
        show: true,
        lineStyle: {
          color: 'rgba(59, 130, 246, 0.2)',
          width: 1,
        },
      },
      axisLine: {
        show: true,
        lineStyle: {
          color: 'rgba(59, 130, 246, 0.3)',
          width: 1,
        },
      },
    },
    series: [
      {
        type: 'radar',
        symbol: 'circle',
        symbolSize: 8,
        data: [
          {
            value: values,
            name: '综合评分',
            areaStyle: {
              color: {
                type: 'linear',
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: 'rgba(59, 130, 246, 0.4)' },
                  { offset: 1, color: 'rgba(59, 130, 246, 0.1)' },
                ],
              },
            },
            lineStyle: {
              color: '#3b82f6',
              width: 3,
              shadowColor: 'rgba(59, 130, 246, 0.5)',
              shadowBlur: 10,
            },
            itemStyle: {
              color: '#3b82f6',
              borderColor: '#fff',
              borderWidth: 3,
              shadowColor: 'rgba(59, 130, 246, 0.5)',
              shadowBlur: 8,
            },
            emphasis: {
              itemStyle: {
                color: '#2563eb',
                borderWidth: 4,
                shadowBlur: 15,
              },
            },
            label: {
              show: true,
              formatter: (params: any) => {
                const val = Array.isArray(params.value)
                  ? params.value[0]
                  : params.value;
                return val === undefined
                  ? '0'
                  : Math.round(Number(val)).toString();
              },
              color: getVbenColor('--foreground'),
              fontSize: 12,
              fontWeight: 'bold',
            },
          },
        ],
        animationDuration: 2000,
        animationEasing: 'cubicInOut',
      },
    ],
  });
}

/** 更新 RLHF 人工专家评分与AI专家对比雷达图 */
function updateRLHFRadarCompareChart() {
  // 从 RLHF 雷达图数据获取人工专家评分（抽检评分）
  const humanScoreMap = new Map<string, number>();
  rlhfRadarScores.value.forEach((item) => {
    humanScoreMap.set(item.name, item.value);
  });

  // 构建对比数据
  const compareData = scoringExperts.value.map((expert, index) => {
    const inspectionScore =
      humanScoreMap.get(expert.expert_name) ??
      getDefaultHumanScore(index) ??
      85;
    // AI 模型评分暂无数据源，使用模拟值（人工评分的 85-95%）
    const modelScore = Math.round(
      inspectionScore * (0.85 + Math.random() * 0.1),
    );
    const diff =
      modelScore > 0 ? ((inspectionScore - modelScore) / modelScore) * 100 : 0;
    return {
      name: expert.expert_name,
      key: expert.expert_func,
      modelScore,
      inspectionScore,
      diff: Number(diff.toFixed(1)),
    };
  });

  const humanValues = compareData.map((item) => item.inspectionScore);
  const aiValues = compareData.map((item) => item.modelScore);

  // 构建雷达图指标
  const indicator = compareData.map((item) => ({
    name: item.name,
    max: 100,
  }));

  renderRLHFRadarCompareChart({
    tooltip: {
      show: true,
      trigger: 'item',
      confine: true,
      formatter: (params: any) => {
        if (!params || !params.value) return '';
        const seriesName = params.name || '评分';
        let result = `<div style="font-weight:bold;margin-bottom:6px;">${seriesName}</div>`;
        compareData.forEach((item, i) => {
          result += `<div style="margin-bottom:4px;">${item.name}: ${params.value[i]}</div>`;
        });
        return result;
      },
    },
    legend: {
      show: true,
      bottom: 10,
      data: ['模型评分', '人工评分'],
      textStyle: {
        color: getVbenColor('--foreground'),
      },
      formatter: (name: string) => {
        if (name === '模型评分') return '模型评分(虚线)';
        if (name === '人工评分') return '人工评分(实线)';
        return name;
      },
    },
    radar: {
      indicator,
      center: ['50%', '45%'],
      radius: '50%',
      startAngle: 90,
      splitNumber: 5,
      shape: 'polygon',
      axisName: {
        color: getVbenColor('--foreground'),
        fontSize: 10,
        formatter: (value?: string) => {
          if (!value) return '';
          const item = compareData.find((d) => d.name === value);
          if (!item) return value;
          const diffIcon = item.diff < 0 ? '▼' : '▲';
          const diffStyleKey = item.diff < 0 ? 'down' : 'up';
          return `{title|${value}}\n{label|模型评分(虚线) ${item.modelScore}}\n{label|人工评分(实线) ${item.inspectionScore}}\n{${diffStyleKey}|${diffIcon} ${Math.abs(item.diff)}%}`;
        },
        rich: {
          title: {
            color: getVbenColor('--foreground'),
            fontSize: 10,
            fontWeight: 'bold',
            lineHeight: 14,
          },
          label: {
            color: getVbenColor('--muted-foreground'),
            fontSize: 9,
            lineHeight: 12,
          },
          up: {
            color: '#22c55e',
            fontSize: 10,
            fontWeight: 'bold',
            lineHeight: 14,
          },
          down: {
            color: '#ef4444',
            fontSize: 10,
            fontWeight: 'bold',
            lineHeight: 14,
          },
        },
      },
      axisNameGap: 8,
      splitArea: {
        show: true,
        areaStyle: {
          color: ['rgba(128, 128, 128, 0.08)', 'rgba(128, 128, 128, 0.04)'],
        },
      },
      splitLine: {
        show: true,
        lineStyle: {
          color: 'rgba(128, 128, 128, 0.2)',
          width: 1,
        },
      },
      axisLine: {
        show: true,
        lineStyle: {
          color: 'rgba(128, 128, 128, 0.15)',
          width: 1,
        },
      },
    },
    series: [
      {
        type: 'radar',
        symbol: 'circle',
        symbolSize: 5,
        data: [
          {
            value: aiValues,
            name: '模型评分',
            areaStyle: {
              color: 'rgba(102, 126, 234, 0.2)',
            },
            lineStyle: {
              color: '#667eea',
              width: 2,
              type: 'dashed',
            },
            itemStyle: {
              color: '#667eea',
              borderColor: 'rgba(102, 126, 234, 0.5)',
              borderWidth: 2,
            },
          },
          {
            value: humanValues,
            name: '人工评分',
            areaStyle: {
              color: 'rgba(102, 126, 234, 0.35)',
            },
            lineStyle: {
              color: '#667eea',
              width: 2,
            },
            itemStyle: {
              color: '#667eea',
              borderColor: 'rgba(102, 126, 234, 0.5)',
              borderWidth: 2,
            },
          },
        ],
      },
    ],
  });
}

// ==================== 表格列配置 ====================
// RLHF 抽检详情表格列配置
const rlhfInspectionColumns = [
  {
    title: '文章ID',
    dataIndex: 'article_id',
    key: 'article_id',
    width: 100,
  },
  {
    title: '反馈标题',
    dataIndex: 'inspection_title',
    key: 'inspection_title',
    width: 150,
    ellipsis: true,
    customRender: ({ record }: { record: RLHFInspectionDetailItem }) =>
      record.inspection_title || '-',
  },
  {
    title: '正文内容',
    dataIndex: 'content_preview',
    key: 'content_preview',
    width: 200,
    ellipsis: true,
    customRender: ({ record }: { record: RLHFInspectionDetailItem }) =>
      record.content_preview || '-',
  },
  {
    title: '反馈结果',
    dataIndex: 'inspection_result',
    key: 'inspection_result',
    width: 100,
    align: 'center' as const,
  },
  {
    title: '反馈人',
    dataIndex: 'inspector_name',
    key: 'inspector_name',
    width: 100,
    customRender: ({ record }: { record: RLHFInspectionDetailItem }) =>
      record.inspector_name || '-',
  },
  {
    title: '反馈时间',
    dataIndex: 'inspection_time',
    key: 'inspection_time',
    width: 180,
    customRender: ({ record }: { record: RLHFInspectionDetailItem }) =>
      record.inspection_time
        ? dayjs(record.inspection_time).format('YYYY-MM-DD HH:mm:ss')
        : '-',
  },
  {
    title: '修改标题',
    dataIndex: 'modified_title',
    key: 'modified_title',
    width: 150,
    ellipsis: true,
    customRender: ({ record }: { record: RLHFInspectionDetailItem }) =>
      record.modified_title || '/',
  },
  {
    title: '修改正文',
    dataIndex: 'modified_content_preview',
    key: 'modified_content_preview',
    width: 200,
    ellipsis: true,
    customRender: ({ record }: { record: RLHFInspectionDetailItem }) =>
      record.modified_content_preview || '/',
  },
];

// 反馈词文章弹窗列配置
const feedbackArticleColumns = [
  {
    title: '文章ID',
    dataIndex: 'article_id',
    key: 'article_id',
    width: 100,
  },
  {
    title: '标题',
    dataIndex: 'title',
    key: 'title',
    width: 200,
    ellipsis: true,
    customRender: ({ record }: { record: FeedbackTagArticleItem }) =>
      record.title || '-',
  },
  {
    title: '内容预览',
    dataIndex: 'content_preview',
    key: 'content_preview',
    ellipsis: true,
    customRender: ({ record }: { record: FeedbackTagArticleItem }) =>
      record.content_preview || '-',
  },
  {
    title: '创建时间',
    dataIndex: 'create_time',
    key: 'create_time',
    width: 180,
    customRender: ({ record }: { record: FeedbackTagArticleItem }) =>
      record.create_time
        ? dayjs(record.create_time).format('YYYY-MM-DD HH:mm:ss')
        : '-',
  },
];

// ==================== 生命周期 ====================
onMounted(() => {
  loadFilterOptions();
  fetchAllData();
  // 启动后台静默刷新
  startAutoRefresh();
});

/** 确认筛选 - 同步筛选条件并触发数据刷新 */
function handleSearch() {
  // 将当前筛选条件同步到已确认的筛选条件
  confirmedFilters.value = {
    activityId: filters.value.activityId,
    agentCode: filters.value.agentCode,
    tenantId: filters.value.tenantId,
  };
  jobCostPagination.value.current = 1;
  fetchAllData();
}

/** 重置筛选 - 恢复默认值并刷新 */
function handleReset() {
  dateRange.value = [dayjs().subtract(29, 'day'), dayjs()];
  // 同时重置筛选状态和已确认的筛选状态
  filters.value = {
    activityId: undefined,
    agentCode: undefined,
    tenantId: undefined,
  };
  confirmedFilters.value = {
    activityId: undefined,
    agentCode: undefined,
    tenantId: undefined,
  };
  jobCostPagination.value.current = 1;
  fetchAllData();
}

// 监听 loading 变化，在 Skeleton 隐藏后更新图表
watch(
  () => loading.value,
  async (newLoading) => {
    if (!newLoading) {
      await nextTick();
      setTimeout(() => {
        // RLHF 人工专家反馈报告图表
        updateRLHFIssueBarChart();
        updateRLHFWordCloudChart();
        updateRLHFRadarChart();
        updateRLHFRadarCompareChart();
      }, 200);
    }
  },
);
</script>

<template>
  <div class="p-3">
    <!-- 粘性筛选头部 -->
    <div
      class="sticky top-0 z-10 -mx-3 -mt-3 mb-3 bg-background/90 px-3 pb-4 pt-2 shadow-lg backdrop-blur-md"
      style="border-bottom: 1px solid hsl(var(--border) / 30%)"
    >
      <!-- 标题行 -->
      <div class="mb-2 flex items-center gap-3">
        <span
          class="bg-gradient-to-r from-[hsl(var(--primary))] to-[#22c55e] bg-clip-text text-xl font-bold text-transparent"
          >反馈训练</span
        >
        <span class="text-xs text-muted-foreground">
          数据更新时间：{{ dataUpdateTime }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="flex flex-wrap items-center gap-4">
        <div class="flex shrink-0 items-center gap-2">
          <span class="whitespace-nowrap font-medium text-foreground"
            >时间筛选</span
          >
          <RangePicker v-model:value="dateRange" :presets="presets" />
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <span class="whitespace-nowrap font-medium text-foreground"
            >内容能力筛选</span
          >
          <Select
            v-model:value="filters.agentCode"
            :filter-option="filterOption"
            :max-tag-count="2"
            :max-tag-text-length="8"
            :options="agentOptions"
            allow-clear
            class="agent-filter-select"
            mode="multiple"
            placeholder="全部内容能力"
            show-search
          />
        </div>
        <div class="ml-auto flex w-full shrink-0 items-center gap-2 xl:w-auto">
          <Button :loading="loading" type="primary" @click="handleSearch">
            <template #icon>
              <SearchOutlined />
            </template>
            确认筛选
          </Button>
          <Button :disabled="loading" @click="handleReset">
            <template #icon>
              <ClearOutlined />
            </template>
            重置筛选
          </Button>
        </div>
      </div>
    </div>

    <!-- ==================== 人工反馈训练报告 ==================== -->
    <div class="section-container rlhf-section mt-4">
      <!-- 流光边框装饰 -->
      <div class="section-glow-border">
        <div class="glow-border-top"></div>
        <div class="glow-border-right"></div>
        <div class="glow-border-bottom"></div>
        <div class="glow-border-left"></div>
      </div>
      <!-- 背景装饰层 -->
      <div class="section-bg-decoration">
        <div class="section-glow-orb orb-amber"></div>
        <div class="section-glow-orb orb-emerald"></div>
        <div class="section-grid-lines"></div>
        <!-- 数据流粒子 -->
        <div class="data-particles">
          <span class="data-particle p1"></span>
          <span class="data-particle p2"></span>
          <span class="data-particle p3"></span>
          <span class="data-particle p4"></span>
          <span class="data-particle p5"></span>
        </div>
      </div>
      <!-- 角落装饰 -->
      <div class="section-corner section-corner-tl"></div>
      <div class="section-corner section-corner-tr"></div>
      <div class="section-corner section-corner-bl"></div>
      <div class="section-corner section-corner-br"></div>
      <!-- 扫描线动画 -->
      <div class="section-scan-line"></div>

      <div class="section-header" @click="toggleSection('rlhf')">
        <span class="section-title glow-title rlhf-title"> 人工反馈 </span>
        <span class="section-collapse-btn">
          <RightOutlined v-if="collapsedSections.rlhf" class="collapse-icon" />
          <DownOutlined v-else class="collapse-icon" />
        </span>
      </div>

      <div v-show="!collapsedSections.rlhf" class="section-content">
        <!-- 顶部两个大数据卡片 -->
        <Skeleton :loading="loading" active :paragraph="{ rows: 1 }">
          <div class="mb-4 flex gap-4">
            <div class="rlhf-big-stat-card">
              <span class="text-sm tracking-wider text-muted-foreground"
                >反馈人员数</span
              >
              <div class="flex items-baseline gap-2">
                <span class="big-stat-value">
                  <CountTo
                    :end-value="rlhfInspectionStats.expert_count || 6"
                    :decimals="0"
                    :duration="1"
                    :use-grouping="true"
                  />
                </span>
                <span class="text-sm text-muted-foreground">人</span>
              </div>
            </div>
            <div class="rlhf-big-stat-card">
              <span class="text-sm tracking-wider text-muted-foreground"
                >人工反馈文章总数</span
              >
              <div class="flex items-baseline gap-2">
                <span class="big-stat-value">
                  <CountTo
                    :end-value="
                      rlhfInspectionStats.total_inspection_count || 1234
                    "
                    :decimals="0"
                    :duration="1"
                    :use-grouping="true"
                  />
                </span>
                <span class="text-sm text-muted-foreground">篇</span>
              </div>
            </div>
          </div>
        </Skeleton>

        <!-- 正负向反馈结果 -->
        <div class="mb-3 flex items-center gap-2">
          <span class="text-base font-semibold text-foreground"
            >正负向反馈结果</span
          >
        </div>
        <Skeleton :loading="loading" active :paragraph="{ rows: 1 }">
          <div class="flex flex-wrap gap-3">
            <div class="rlhf-feedback-tag-item tag-illegal">
              <span
                class="tag-name rounded-lg px-2 py-0.5 text-sm font-semibold transition-transform"
                >不合法</span
              >
              <span class="tag-count text-sm font-bold text-foreground">
                <CountTo
                  :end-value="rlhfInspectionStats.illegal_count || 0"
                  :decimals="0"
                  :duration="1"
                  :use-grouping="true"
                />条
              </span>
              <span class="tag-percent text-xs text-muted-foreground"
                >占反馈样本 0%</span
              >
            </div>
            <div class="rlhf-feedback-tag-item tag-non-compliant">
              <span
                class="tag-name rounded-lg px-2 py-0.5 text-sm font-semibold transition-transform"
                >不合规</span
              >
              <span class="tag-count text-sm font-bold text-foreground">
                <CountTo
                  :end-value="rlhfInspectionStats.non_compliant_count || 3"
                  :decimals="0"
                  :duration="1"
                  :use-grouping="true"
                />条
              </span>
              <span class="tag-percent text-xs text-muted-foreground"
                >占反馈样本 5.0%</span
              >
            </div>
            <div class="rlhf-feedback-tag-item tag-unreasonable">
              <span
                class="tag-name rounded-lg px-2 py-0.5 text-sm font-semibold transition-transform"
                >不合理</span
              >
              <span class="tag-count text-sm font-bold text-foreground">
                <CountTo
                  :end-value="rlhfInspectionStats.unreasonable_count || 4"
                  :decimals="0"
                  :duration="1"
                  :use-grouping="true"
                />条
              </span>
              <span class="tag-percent text-xs text-muted-foreground"
                >占反馈样本 6.7%</span
              >
            </div>
            <div class="rlhf-feedback-tag-item tag-off-purpose">
              <span
                class="tag-name rounded-lg px-2 py-0.5 text-sm font-semibold transition-transform"
                >不合目的</span
              >
              <span class="tag-count text-sm font-bold text-foreground">
                <CountTo
                  :end-value="rlhfInspectionStats.off_purpose_count || 6"
                  :decimals="0"
                  :duration="1"
                  :use-grouping="true"
                />条
              </span>
              <span class="tag-percent text-xs text-muted-foreground"
                >占反馈样本 10.0%</span
              >
            </div>
          </div>
        </Skeleton>

        <!-- 评分反馈结果 - 雷达图 -->
        <div class="mb-3 flex items-center gap-2">
          <span class="text-base font-semibold text-foreground"
            >评分反馈结果</span
          >
          <Tooltip placement="right">
            <template #title>
              <div class="max-w-[320px]">
                <div class="mb-2 leading-relaxed last:mb-0">
                  <b>平台适应度</b
                  >：评估内容是否符合目标平台的调性、风格和用户习惯，包括文案长度、表达方式、话题热度等
                </div>
                <div class="mb-2 leading-relaxed last:mb-0">
                  <b>整体内容质量</b
                  >：综合评估内容的完整性、逻辑性和可读性，包括结构清晰度、信息准确性等
                </div>
                <div class="mb-2 leading-relaxed last:mb-0">
                  <b>品牌调性匹配</b
                  >：评估内容是否与品牌形象、价值观和沟通风格保持一致
                </div>
                <div class="mb-2 leading-relaxed last:mb-0">
                  <b>内容创造力</b
                  >：评估内容的原创性、新颖度和吸引力，包括创意表达、独特视角等
                </div>
                <div class="mb-2 leading-relaxed last:mb-0">
                  <b>内容人设一致性</b
                  >：评估内容是否符合预设的人物设定，保持人设特征和说话风格的一致性
                </div>
                <div class="mb-2 leading-relaxed last:mb-0">
                  <b>语法正确性</b
                  >：评估内容的语法规范性、用词准确性和表达流畅度
                </div>
              </div>
            </template>
            <QuestionCircleOutlined
              class="cursor-pointer text-sm text-muted-foreground transition-colors hover:text-primary"
            />
          </Tooltip>
        </div>
        <Row :gutter="24" class="mt-2">
          <Col :span="12">
            <Card :bordered="false" class="rlhf-chart-card-cool">
              <!-- 背景装饰 -->
              <div class="rlhf-card-bg">
                <div class="rlhf-glow-orb orb-cyan"></div>
                <div class="rlhf-grid-lines"></div>
              </div>
              <!-- 流光边框 -->
              <div class="rlhf-border-glow"></div>
              <!-- 内容 -->
              <div class="rlhf-card-content">
                <div class="rlhf-chart-title">
                  <span class="rlhf-title-indicator"></span>
                  <span>人工反馈综合评分</span>
                </div>
                <div class="relative h-[320px]">
                  <div v-if="loading" class="rlhf-loading-overlay">
                    <div class="rlhf-loading-text">Loading...</div>
                  </div>
                  <EchartsUI
                    ref="rlhfRadarChartRef"
                    height="320px"
                    width="100%"
                  />
                </div>
              </div>
            </Card>
          </Col>
          <Col :span="12">
            <Card :bordered="false" class="rlhf-chart-card-cool">
              <!-- 背景装饰 -->
              <div class="rlhf-card-bg">
                <div class="rlhf-glow-orb orb-purple"></div>
                <div class="rlhf-grid-lines"></div>
              </div>
              <!-- 流光边框 -->
              <div class="rlhf-border-glow"></div>
              <!-- 内容 -->
              <div class="rlhf-card-content">
                <div class="rlhf-chart-title">
                  <span class="rlhf-title-indicator"></span>
                  <span>人工反馈与模型评分对比</span>
                </div>
                <div class="relative h-[320px]">
                  <div v-if="loading" class="rlhf-loading-overlay">
                    <div class="rlhf-loading-text">Loading...</div>
                  </div>
                  <EchartsUI
                    ref="rlhfRadarCompareChartRef"
                    height="320px"
                    width="100%"
                  />
                </div>
              </div>
            </Card>
          </Col>
        </Row>

        <!-- 喜欢采纳反馈 -->
        <div class="mb-3 flex items-center gap-2">
          <span class="text-base font-semibold text-foreground"
            >喜欢采纳反馈</span
          >
        </div>
        <Skeleton :loading="loading" :active="true" :paragraph="{ rows: 1 }">
          <div class="flex gap-4">
            <div class="rlhf-like-feedback-card">
              <div class="flex items-baseline gap-2">
                <span class="text-sm text-muted-foreground">喜欢数量</span>
                <span
                  class="like-feedback-value text-2xl font-extrabold text-foreground transition-transform"
                >
                  <CountTo
                    :end-value="rlhfInspectionStats.like_count || 0"
                    :decimals="0"
                    :duration="1"
                    :use-grouping="true"
                  />
                </span>
              </div>
              <div class="flex items-baseline gap-2">
                <span class="text-sm text-muted-foreground">喜欢率</span>
                <span class="like-feedback-rate like-rate">
                  <CountTo
                    :end-value="Number(rlhfInspectionStats.like_rate || 0)"
                    :decimals="1"
                    :duration="1"
                    suffix="%"
                    :use-grouping="false"
                  />
                </span>
              </div>
            </div>
            <div class="rlhf-like-feedback-card">
              <div class="flex items-baseline gap-2">
                <span class="text-sm text-muted-foreground">不喜欢数量</span>
                <span
                  class="like-feedback-value text-2xl font-extrabold text-foreground transition-transform"
                >
                  <CountTo
                    :end-value="rlhfInspectionStats.dislike_count || 0"
                    :decimals="0"
                    :duration="1"
                    :use-grouping="true"
                  />
                </span>
              </div>
              <div class="flex items-baseline gap-2">
                <span class="text-sm text-muted-foreground">不喜欢率</span>
                <span class="like-feedback-rate dislike-rate">
                  <CountTo
                    :end-value="Number(rlhfInspectionStats.dislike_rate || 0)"
                    :decimals="1"
                    :duration="1"
                    suffix="%"
                    :use-grouping="false"
                  />
                </span>
              </div>
            </div>
          </div>
        </Skeleton>

        <!-- 底部图表区域 - 反馈词分析 -->
        <Card :bordered="false" class="rlhf-chart-card mt-4">
          <div
            class="mb-2 flex items-center gap-2 pb-2 text-sm font-semibold text-foreground"
          >
            反馈词分析
          </div>
          <Row :gutter="24">
            <!-- 左侧：问题标签词云 -->
            <Col :span="10">
              <div class="relative h-[400px]">
                <div
                  v-if="loading"
                  class="absolute inset-0 z-10 flex items-center justify-center bg-background/50"
                >
                  <div class="text-muted-foreground">加载中...</div>
                </div>
                <EchartsUI
                  ref="rlhfWordCloudChartRef"
                  height="400px"
                  width="100%"
                />
              </div>
            </Col>

            <!-- 右侧：反馈词列表 -->
            <Col :span="14">
              <Skeleton :loading="loading" active :paragraph="{ rows: 8 }">
                <div class="relative">
                  <Table
                    :columns="[
                      {
                        title: '排序',
                        dataIndex: 'index',
                        key: 'index',
                        width: 70,
                        align: 'center' as const,
                      },
                      {
                        title: '反馈词',
                        dataIndex: 'tag_name',
                        key: 'tag_name',
                        ellipsis: true,
                      },
                      {
                        title: '反馈次数',
                        dataIndex: 'count',
                        key: 'count',
                        width: 100,
                        align: 'center' as const,
                      },
                      {
                        title: '反馈文章数',
                        dataIndex: 'article_count',
                        key: 'article_count',
                        width: 110,
                        align: 'center' as const,
                      },
                      {
                        title: '操作',
                        key: 'action',
                        width: 130,
                        align: 'center' as const,
                      },
                    ]"
                    :data-source="rlhfIssueTagDistribution"
                    :pagination="false"
                    :row-key="
                      (record: RLHFIssueTagDistribution) => record.tag_id
                    "
                    :scroll="{ y: 360 }"
                    bordered
                    size="small"
                  >
                    <template #bodyCell="{ column, record, index }">
                      <template v-if="column.key === 'index'">
                        {{ index + 1 }}
                      </template>
                      <template v-else-if="column.key === 'article_count'">
                        {{ record.count }}篇
                      </template>
                      <template v-else-if="column.key === 'action'">
                        <Button
                          type="link"
                          size="small"
                          @click="handleViewFeedbackArticles(record)"
                        >
                          查看文章列表
                        </Button>
                      </template>
                    </template>
                    <template #emptyText>
                      <Empty description="暂无反馈数据" />
                    </template>
                  </Table>
                </div>
              </Skeleton>
            </Col>
          </Row>
        </Card>

        <!-- 反馈改进点摘要 -->
        <Card
          :bordered="false"
          class="rlhf-detail-card mt-4"
          title="反馈改进点摘要"
        >
          <Skeleton :loading="loading" active :paragraph="{ rows: 6 }">
            <div v-if="rlhfImprovementList.length === 0" class="py-8">
              <Empty description="暂无改进点数据" />
            </div>
            <div v-else class="flex flex-col gap-4">
              <div
                v-for="item in rlhfImprovementList"
                :key="`${item.feedback_id}-${item.create_time}`"
                class="rounded-lg border border-border bg-muted/30 p-4"
              >
                <div
                  class="mb-3 flex items-center justify-between border-b border-border pb-2"
                >
                  <span
                    class="rounded bg-muted px-2 py-1 text-sm font-semibold text-foreground"
                    >{{ item.user_name || '未知用户' }}</span
                  >
                  <span class="text-xs text-muted-foreground">{{
                    item.create_time || '-'
                  }}</span>
                </div>
                <div class="flex flex-col gap-2">
                  <div
                    class="border-l-3 rounded-r border-l-primary bg-background px-3 py-2 text-sm leading-relaxed text-foreground"
                  >
                    {{ item.selected_text || '-' }}
                  </div>
                  <div class="text-sm leading-relaxed text-muted-foreground">
                    {{ item.comment || '-' }}
                  </div>
                </div>
              </div>
            </div>
          </Skeleton>
        </Card>

        <!-- 反馈明细表格 -->
        <Card :bordered="false" class="rlhf-detail-card mt-4" title="反馈明细">
          <Skeleton :loading="loading" active :paragraph="{ rows: 8 }">
            <div class="relative">
              <Table
                :columns="rlhfInspectionColumns"
                :data-source="rlhfInspectionDetailList"
                :pagination="false"
                :row-key="
                  (record: RLHFInspectionDetailItem) => record.article_id
                "
                :scroll="{ x: 1200, y: 450 }"
                bordered
                size="middle"
              >
                <template #emptyText>
                  <Empty description="暂无反馈明细" />
                </template>
              </Table>
            </div>
          </Skeleton>
        </Card>
      </div>
    </div>

    <!-- 反馈词文章列表弹窗 -->
    <Modal
      v-model:open="feedbackArticleModalVisible"
      :footer="null"
      :title="`反馈词「${selectedFeedbackTag?.tag_name || ''}」相关文章`"
      :width="900"
      @cancel="handleCloseFeedbackArticleModal"
    >
      <div class="min-h-[300px]">
        <Skeleton
          :loading="feedbackArticleModalLoading"
          active
          :paragraph="{ rows: 6 }"
        >
          <div class="relative">
            <Table
              :columns="feedbackArticleColumns"
              :data-source="feedbackTagArticleList"
              :pagination="false"
              :row-key="(record: FeedbackTagArticleItem) => record.article_id"
              :scroll="{ y: 450 }"
              bordered
              size="small"
            >
              <template #emptyText>
                <Empty description="暂无相关文章" />
              </template>
            </Table>
          </div>
        </Skeleton>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
/* ==================== 炫酷动画定义 ==================== */
@keyframes fade-in {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes slide-in-up {
  from {
    opacity: 0;
    transform: translateY(20px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.7;
  }
}

@keyframes shimmer {
  0% {
    background-position: -200% 0;
  }

  100% {
    background-position: 200% 0;
  }
}

@keyframes glow {
  0%,
  100% {
    box-shadow:
      0 0 5px hsl(var(--primary) / 20%),
      0 0 10px hsl(var(--primary) / 10%);
  }

  50% {
    box-shadow:
      0 0 15px hsl(var(--primary) / 40%),
      0 0 25px hsl(var(--primary) / 20%);
  }
}

@keyframes float {
  0%,
  100% {
    transform: translateY(0);
  }

  50% {
    transform: translateY(-5px);
  }
}

@keyframes border-glow {
  0%,
  100% {
    border-color: hsl(var(--primary) / 30%);
  }

  50% {
    border-color: hsl(var(--primary) / 60%);
  }
}

@keyframes critic-orb-pulse {
  0%,
  100% {
    opacity: 0.25;
    transform: scale(1);
  }

  50% {
    opacity: 0.45;
    transform: scale(1.3);
  }
}

@keyframes critic-pulse-expand {
  0% {
    opacity: 0.6;
    transform: translate(-50%, -50%) scale(0.5);
  }

  100% {
    opacity: 0;
    transform: translate(-50%, -50%) scale(2);
  }
}

@keyframes critic-border-slide {
  0% {
    left: -100%;
  }

  100% {
    left: 100%;
  }
}

@keyframes critic-icon-bounce {
  0%,
  100% {
    transform: translateY(0);
  }

  50% {
    transform: translateY(-3px);
  }
}

@keyframes critic-progress-glow {
  0%,
  100% {
    opacity: 0.8;
  }

  50% {
    opacity: 1;
  }
}

@keyframes rlhf-orb-float {
  0%,
  100% {
    opacity: 0.2;
    transform: translate(0, 0) scale(1);
  }

  50% {
    opacity: 0.35;
    transform: translate(-20px, 20px) scale(1.1);
  }
}

@keyframes rlhf-border-flow {
  0% {
    left: -100%;
  }

  100% {
    left: 100%;
  }
}

@keyframes rlhf-indicator-pulse {
  0%,
  100% {
    box-shadow: 0 0 10px hsl(var(--primary));
  }

  50% {
    box-shadow:
      0 0 20px hsl(var(--primary)),
      0 0 30px hsl(var(--primary) / 50%);
  }
}

@keyframes rlhf-loading-pulse {
  0%,
  100% {
    opacity: 0.5;
  }

  50% {
    opacity: 1;
  }
}

@keyframes scoring-indicator-pulse {
  0%,
  100% {
    box-shadow: 0 0 12px hsl(var(--primary));
  }

  50% {
    box-shadow:
      0 0 20px hsl(var(--primary)),
      0 0 30px hsl(var(--primary) / 50%);
  }
}

@keyframes pulse-glow {
  0%,
  100% {
    opacity: 0.15;
    transform: scale(1);
  }

  50% {
    opacity: 0.35;
    transform: scale(1.03);
  }
}

@keyframes ping {
  75%,
  100% {
    opacity: 0;
    transform: scale(2);
  }
}

@keyframes expert-pulse {
  0% {
    transform: scale(1);
  }

  30% {
    transform: scale(1.08) translateX(4px);
  }

  60% {
    transform: scale(1.03) translateX(2px);
  }

  100% {
    transform: scale(1.05) translateX(2px);
  }
}

@keyframes expert-glow {
  0%,
  100% {
    box-shadow:
      0 0 0 4px var(--expert-bg),
      0 0 30px var(--expert-color),
      0 0 60px var(--expert-color),
      0 8px 25px hsl(var(--foreground) / 20%);
  }

  50% {
    box-shadow:
      0 0 0 6px var(--expert-bg),
      0 0 45px var(--expert-color),
      0 0 80px var(--expert-color),
      0 10px 30px hsl(var(--foreground) / 25%);
  }
}

@keyframes shimmer {
  0% {
    transform: translateX(-100%);
  }

  100% {
    transform: translateX(100%);
  }
}

@keyframes icon-bounce {
  0% {
    transform: scale(1);
  }

  40% {
    transform: scale(1.3) rotate(-5deg);
  }

  70% {
    transform: scale(0.95) rotate(3deg);
  }

  100% {
    transform: scale(1.1) rotate(0deg);
  }
}

@keyframes dot-ping {
  0%,
  100% {
    box-shadow: 0 0 6px currentcolor;
    opacity: 1;
    transform: scale(1);
  }

  50% {
    box-shadow: 0 0 12px currentcolor;
    opacity: 0.6;
    transform: scale(1.5);
  }
}

@keyframes status-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }

  50% {
    opacity: 0.7;
    transform: scale(1.02);
  }
}

/* 闪烁动画 */
@keyframes segment-twinkle {
  0%,
  100% {
    opacity: 0.85;
    filter: brightness(1);
  }

  15% {
    opacity: 1;
    filter: brightness(1.3);
  }

  30% {
    opacity: 0.9;
    filter: brightness(1.1);
  }

  50% {
    opacity: 1;
    filter: brightness(1.4);
  }

  65% {
    opacity: 0.85;
    filter: brightness(1);
  }

  80% {
    opacity: 1;
    filter: brightness(1.2);
  }
}

/* 发光闪烁动画 */
@keyframes glow-flash {
  0%,
  100% {
    opacity: 0;
  }

  25% {
    opacity: 0.6;
  }

  50% {
    opacity: 0;
  }

  75% {
    opacity: 0.4;
  }
}

@keyframes legend-dot-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 currentcolor;
    opacity: 0.7;
    transform: scale(1);
  }

  50% {
    box-shadow: 0 0 8px 2px currentcolor;
    opacity: 1;
    transform: scale(1.3);
  }
}

@keyframes arrow-move-right {
  0%,
  100% {
    transform: translateX(0);
  }

  50% {
    transform: translateX(8px);
  }
}

@keyframes fade-in-scale {
  from {
    opacity: 0;
    transform: scale(0.9);
  }

  to {
    opacity: 1;
    transform: scale(1);
  }
}

@keyframes radar-glow-pulse {
  0%,
  100% {
    opacity: 0.6;
    transform: translate(-50%, -50%) scale(1);
  }

  50% {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1.05);
  }
}

@keyframes ring-rotate {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

@keyframes line-pulse {
  0%,
  100% {
    opacity: 0.3;
    stroke-width: 1.5;
  }

  50% {
    opacity: 0.8;
    stroke-width: 2.5;
  }
}

@keyframes vertex-pulse {
  0%,
  100% {
    r: 4;
    opacity: 0.6;
  }

  50% {
    r: 8;
    opacity: 1;
  }
}

@keyframes pulse-expand {
  0% {
    border-width: 2px;
    opacity: 0.8;
    transform: scale(0.8);
  }

  100% {
    border-width: 0.5px;
    opacity: 0;
    transform: scale(1.3);
  }
}

@keyframes label-float {
  0%,
  100% {
    transform: translateY(0) translateX(var(--tx, 0));
  }

  50% {
    transform: translateY(-3px) translateX(var(--tx, 0));
  }
}

@keyframes orb-float {
  0%,
  100% {
    opacity: 0.25;
    transform: translate(0, 0) scale(1);
  }

  25% {
    opacity: 0.35;
    transform: translate(30px, 20px) scale(1.1);
  }

  50% {
    opacity: 0.3;
    transform: translate(10px, 40px) scale(1.05);
  }

  75% {
    opacity: 0.25;
    transform: translate(-20px, 15px) scale(0.95);
  }
}

@keyframes grid-pulse {
  0%,
  100% {
    opacity: 0.4;
  }

  50% {
    opacity: 0.6;
  }
}

@keyframes corner-pulse {
  0%,
  100% {
    box-shadow:
      0 0 12px hsl(var(--primary)),
      0 0 24px hsl(var(--primary) / 50%);
    opacity: 0.7;
  }

  50% {
    box-shadow:
      0 0 20px hsl(var(--primary)),
      0 0 40px hsl(var(--primary) / 60%),
      0 0 60px hsl(var(--primary) / 30%);
    opacity: 1;
  }
}

@keyframes scan-sweep {
  0% {
    top: 0;
    opacity: 0;
  }

  5% {
    opacity: 0.9;
  }

  95% {
    opacity: 0.9;
  }

  100% {
    top: 100%;
    opacity: 0;
  }
}

@keyframes particle-rise {
  0% {
    bottom: -10px;
    opacity: 0;
    transform: translateX(0) scale(0.5);
  }

  10% {
    opacity: 0.9;
    transform: scale(1);
  }

  50% {
    transform: translateX(25px) scale(1.3);
  }

  90% {
    opacity: 0.9;
  }

  100% {
    bottom: 100%;
    opacity: 0;
    transform: translateX(-15px) scale(0.5);
  }
}

@keyframes badge-glow {
  0%,
  100% {
    box-shadow: 0 0 15px hsl(var(--primary) / 50%);
  }

  50% {
    box-shadow:
      0 0 25px hsl(var(--primary) / 70%),
      0 0 40px hsl(var(--primary) / 30%);
  }
}

@keyframes live-blink {
  0%,
  100% {
    box-shadow:
      0 0 8px #fff,
      0 0 15px #fff;
    opacity: 1;
  }

  50% {
    box-shadow: 0 0 4px #fff;
    opacity: 0.4;
  }
}

/* 用户偏好减少动画时，禁用所有动画效果 */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }

  .section-glow-border,
  .security-border-glow,
  .security-glow-orb,
  .section-glow-orb {
    opacity: 0.3 !important;
    animation: none !important;
  }
}

@media (max-width: 1200px) {
  .agent-cards-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .agent-cards-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 1400px) {
  .critic-expert-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .critic-expert-grid {
    grid-template-columns: 1fr;
  }
}

/* 减少重绘：为动画元素启用 GPU 加速 */
.section-glow-border,
.section-glow-orb,
.section-corner {
  transform: translateZ(0);
  will-change: transform, opacity;
  backface-visibility: hidden;
}

/* ==================== 翻牌数字容器 ==================== */
.flip-number-container {
  display: flex;
  align-items: center;
  padding: 8px 0;
  font-size: 2rem;
  font-weight: bold;
}

.flip-number-container :deep(.flip-number) {
  font-size: 2rem;
}

.flip-number-container :deep(.flip-digit) {
  width: 1.3em;
  height: 1.8em;
  margin: 0 2px;
  font-size: 1.5rem;
  line-height: 1.8em;
  border-radius: 6px;
  box-shadow:
    0 4px 12px hsl(var(--foreground) / 15%),
    inset 0 1px 0 hsl(var(--background) / 30%);
}

.flip-number-container :deep(.flip-digit.is-separator) {
  width: 0.5em;
}

.flip-number-container :deep(.flip-prefix) {
  margin-right: 4px;
  font-size: 1.5rem;
  color: hsl(var(--primary));
}

.text-muted-foreground {
  color: hsl(var(--muted-foreground));
}

.text-primary {
  color: hsl(var(--primary));
}

/* ==================== 模块容器样式 - 优化布局 ==================== */
.section-container {
  margin-bottom: 1rem;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 0.5rem;
  margin-bottom: 0.75rem;
  cursor: pointer;
  user-select: none;
  border-bottom: 2px solid transparent;
  border-image: linear-gradient(
      90deg,
      hsl(var(--primary)),
      hsl(var(--primary) / 40%),
      transparent
    )
    1;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.section-header:hover {
  transform: translateX(4px);
}

.section-title {
  position: relative;
  padding: 0.5rem 1.25rem;
  overflow: hidden;
  font-size: 1.25rem;
  font-weight: 800;
  color: hsl(var(--foreground));
  letter-spacing: 0.05em;
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 15%) 0%,
    hsl(var(--primary) / 5%) 100%
  );
  border-left: 4px solid hsl(var(--primary));
  border-radius: 0 8px 8px 0;
}

.section-title::before {
  position: absolute;
  inset: 0;
  pointer-events: none;
  content: '';
  background: linear-gradient(
    90deg,
    transparent,
    hsl(var(--primary) / 10%),
    transparent
  );
  background-size: 200% 100%;
  animation: shimmer 3s infinite;
}

.section-collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: linear-gradient(
    135deg,
    hsl(var(--card)) 0%,
    hsl(var(--muted) / 50%) 100%
  );
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  box-shadow: 0 2px 8px hsl(var(--foreground) / 5%);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.section-collapse-btn:hover {
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 20%) 0%,
    hsl(var(--primary) / 10%) 100%
  );
  border-color: hsl(var(--primary));
  box-shadow: 0 4px 12px hsl(var(--primary) / 20%);
  transform: scale(1.05);
}

.collapse-icon {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.section-collapse-btn:hover .collapse-icon {
  color: hsl(var(--primary));
}

.section-content {
  animation: slide-in-up 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

/* 玻璃拟态卡片 */
.dashboard-glass-card {
  position: relative;
  overflow: hidden;
  background: linear-gradient(
    145deg,
    hsl(var(--card) / 95%) 0%,
    hsl(var(--muted) / 40%) 100%
  ) !important;
  border: 1px solid hsl(var(--border) / 40%) !important;
  border-radius: 16px !important;
  box-shadow:
    0 4px 20px hsl(var(--foreground) / 5%),
    inset 0 1px 0 hsl(255deg 255 255 / 10%);
  backdrop-filter: blur(10px);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.dashboard-glass-card::before {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 1px;
  content: '';
  background: linear-gradient(
    90deg,
    transparent,
    hsl(var(--primary) / 30%),
    transparent
  );
}

.dashboard-glass-card:hover {
  border-color: hsl(var(--primary) / 30%) !important;
  box-shadow:
    0 8px 30px hsl(var(--foreground) / 8%),
    inset 0 1px 0 hsl(255deg 255 255 / 15%);
}

/* 扇形图卡片布局 - 固定高度，不受右侧内容影响 */
.pie-chart-card {
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  height: 520px !important;
}

.pie-chart-card :deep(.ant-card-body) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}

/* 成本明细卡片 - 高度与左侧扇形卡片对齐 */
.cost-detail-card {
  display: flex;
  flex-direction: column;
  height: 520px !important;
  overflow: hidden;
}

.cost-detail-card :deep(.ant-card-body) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}

.pie-chart-container {
  position: relative;
  flex: 1;
  min-height: 280px;
}

/* Agent 占比进度条 */
.agent-progress-bar {
  display: flex;
  height: 28px;
  overflow: hidden;
  background: hsl(var(--muted));
  border-radius: 4px;
}

.agent-progress-segment {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 2px;
  transition: width 0.3s ease;
}

.segment-label {
  font-size: 12px;
  font-weight: 500;
  color: #fff;
  white-space: nowrap;
  text-shadow: 0 1px 2px rgb(0 0 0 / 30%);
}

/* Agent 卡片网格 - 优化版 */
.agent-cards-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.75rem;
}

.agent-card {
  position: relative;
  overflow: hidden;
  background: linear-gradient(
    145deg,
    hsl(var(--card)) 0%,
    hsl(var(--muted) / 30%) 100%
  );
  border: 1px solid hsl(var(--border) / 60%);
  border-radius: 12px;
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.agent-card::before {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 3px;
  content: '';
  background: linear-gradient(
    90deg,
    hsl(var(--primary)),
    hsl(217deg 91% 60%),
    hsl(280deg 87% 65%)
  );
  opacity: 0;
  transition: opacity 0.3s ease;
}

.agent-card:hover {
  border-color: hsl(var(--primary) / 40%);
  box-shadow:
    0 8px 24px hsl(var(--foreground) / 8%),
    0 0 0 1px hsl(var(--primary) / 10%),
    inset 0 1px 0 hsl(255deg 255 255 / 10%);
  transform: translateY(-4px);
}

.agent-card:hover::before {
  opacity: 1;
}

.status-tag {
  flex-shrink: 0;
  animation: pulse 2s infinite;
}

.trend-chart {
  padding: 0.5rem;
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 8%) 0%,
    hsl(var(--primary) / 2%) 100%
  );
  border: 1px solid hsl(var(--primary) / 10%);
  border-radius: 8px;
}

/* ==================== 炫酷表格样式 ==================== */

/* 表格容器 - 玻璃拟态效果 */
:deep(.ant-table-wrapper) {
  overflow: hidden;
  border-radius: 16px;
}

:deep(.ant-table) {
  overflow: hidden;
  color: hsl(var(--foreground)) !important;
  background: transparent !important;
  border-radius: 16px;
}

:deep(.ant-table-container) {
  background: linear-gradient(
    135deg,
    hsl(var(--card) / 90%) 0%,
    hsl(var(--card) / 70%) 100%
  ) !important;
  border: 1px solid hsl(var(--border) / 50%);
  border-radius: 16px;
  box-shadow:
    0 8px 32px hsl(var(--foreground) / 8%),
    inset 0 1px 0 hsl(255deg 255 255 / 10%);
  backdrop-filter: blur(20px);
}

:deep(.ant-table-bordered > .ant-table-container) {
  border: 1px solid hsl(var(--border) / 50%);
  border-radius: 16px;
}

/* 表头样式 - 渐变背景 + 毛玻璃 */
:deep(.ant-table-thead > tr > th) {
  position: relative;
  padding: 14px 16px;
  overflow: hidden;
  font-size: 13px;
  font-weight: 600;
  color: hsl(var(--foreground)) !important;
  text-transform: none;
  letter-spacing: 0.025em;
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 15%) 0%,
    hsl(var(--primary) / 8%) 100%
  ) !important;
  border-bottom: 2px solid hsl(var(--primary) / 30%) !important;
  backdrop-filter: blur(12px);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

:deep(.ant-table-thead > tr > th::before) {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 1px;
  content: '';
  background: linear-gradient(
    90deg,
    transparent 0%,
    hsl(var(--primary) / 40%) 50%,
    transparent 100%
  );
}

:deep(.ant-table-thead > tr > th:hover) {
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 22%) 0%,
    hsl(var(--primary) / 12%) 100%
  ) !important;
}

/* 表体行样式 - 斑马纹 + 悬浮高亮 */
:deep(.ant-table-tbody > tr) {
  position: relative;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

:deep(.ant-table-tbody > tr > td) {
  padding: 12px 16px;
  font-size: 13px;
  color: hsl(var(--foreground) / 90%) !important;
  background: transparent !important;
  border-bottom: 1px solid hsl(var(--border) / 30%);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

/* 斑马纹效果 */
:deep(.ant-table-tbody > tr:nth-child(even) > td) {
  background: hsl(var(--muted) / 20%) !important;
}

:deep(.ant-table-tbody > tr:nth-child(odd) > td) {
  background: transparent !important;
}

/* 行悬浮效果 - 发光高亮 */
:deep(.ant-table-tbody > tr:hover > td) {
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 12%) 0%,
    hsl(var(--primary) / 6%) 100%
  ) !important;
}

:deep(.ant-table-tbody > tr:hover > td:first-child) {
  box-shadow: inset 3px 0 0 hsl(var(--primary));
}

/* 单元格内文字效果 */
:deep(.ant-table-cell) {
  position: relative;
}

/* 数值列高亮 */
:deep(.ant-table-cell .highlight-value) {
  font-weight: 600;
  color: hsl(var(--primary));
  text-shadow: 0 0 20px hsl(var(--primary) / 30%);
}

/* 滚动条美化 */
:deep(.ant-table-body::-webkit-scrollbar) {
  width: 6px;
  height: 6px;
}

:deep(.ant-table-body::-webkit-scrollbar-track) {
  background: hsl(var(--muted) / 30%);
  border-radius: 3px;
}

:deep(.ant-table-body::-webkit-scrollbar-thumb) {
  background: linear-gradient(
    180deg,
    hsl(var(--primary) / 60%) 0%,
    hsl(var(--primary) / 40%) 100%
  );
  border-radius: 3px;
  transition: background 0.3s;
}

:deep(.ant-table-body::-webkit-scrollbar-thumb:hover) {
  background: linear-gradient(
    180deg,
    hsl(var(--primary) / 80%) 0%,
    hsl(var(--primary) / 60%) 100%
  );
}

/* 空状态美化 */
:deep(.ant-empty) {
  padding: 40px 20px;
}

:deep(.ant-empty-description) {
  font-size: 14px;
  color: hsl(var(--muted-foreground));
}

/* 固定列阴影效果 */
:deep(.ant-table-cell-fix-left),
:deep(.ant-table-cell-fix-right) {
  background: hsl(var(--card)) !important;
}

:deep(.ant-table-cell-fix-left-last::after) {
  box-shadow: inset 10px 0 8px -8px hsl(var(--foreground) / 10%) !important;
}

:deep(.ant-table-cell-fix-right-first::after) {
  box-shadow: inset -10px 0 8px -8px hsl(var(--foreground) / 10%) !important;
}

/* 选中行效果 */
:deep(.ant-table-tbody > tr.ant-table-row-selected > td) {
  background: hsl(var(--primary) / 15%) !important;
}

/* 加载状态动画 */
:deep(.ant-table-loading .ant-spin-dot-item) {
  background-color: hsl(var(--primary));
}

/* 卡片头部样式 */
:deep(.ant-card-head) {
  background: linear-gradient(
    135deg,
    hsl(var(--card)) 0%,
    hsl(var(--muted) / 30%) 100%
  );
  border-bottom: 1px solid hsl(var(--border) / 50%);
}

:deep(.ant-card-head-title) {
  font-weight: 600;
  color: hsl(var(--foreground)) !important;
  letter-spacing: 0.015em;
}

/* ==================== RLHF 人工专家反馈报告样式 ==================== */

/* 顶部两个大数据卡片 - 炫酷版 */
.rlhf-big-stat-card {
  position: relative;
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 0.25rem;
  padding: 1.25rem 1.5rem;
  overflow: hidden;
  background: linear-gradient(
    135deg,
    hsl(var(--card)) 0%,
    hsl(var(--primary) / 5%) 100%
  );
  border: 1px solid hsl(var(--border) / 60%);
  border-radius: 16px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.rlhf-big-stat-card::before {
  position: absolute;
  top: -50%;
  right: -50%;
  width: 100%;
  height: 100%;
  pointer-events: none;
  content: '';
  background: radial-gradient(
    circle,
    hsl(var(--primary) / 8%) 0%,
    transparent 70%
  );
}

.rlhf-big-stat-card:hover {
  border-color: hsl(var(--primary) / 30%);
  box-shadow: 0 8px 24px hsl(var(--primary) / 10%);
  transform: translateY(-2px);
}

.big-stat-value {
  font-size: 2.25rem;
  font-weight: 800;
  background: linear-gradient(
    135deg,
    hsl(var(--foreground)) 0%,
    hsl(var(--primary)) 100%
  );
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* 正负向反馈标签 - 炫酷版 */
.rlhf-feedback-tag-item {
  position: relative;
  display: flex;
  gap: 0.75rem;
  align-items: center;
  min-width: 160px;
  padding: 0.625rem 1rem;
  overflow: hidden;
  background: linear-gradient(
    135deg,
    hsl(var(--card)) 0%,
    hsl(var(--muted) / 20%) 100%
  );
  border: 1px solid hsl(var(--border) / 60%);
  border-radius: 12px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.rlhf-feedback-tag-item::before {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 3px;
  content: '';
  border-radius: 3px 0 0 3px;
  transition: width 0.3s ease;
}

.rlhf-feedback-tag-item:hover {
  box-shadow: 0 6px 16px hsl(var(--foreground) / 8%);
  transform: translateY(-2px) scale(1.02);
}

.rlhf-feedback-tag-item:hover::before {
  width: 4px;
}

.rlhf-feedback-tag-item:hover .tag-name {
  transform: scale(1.05);
}

.rlhf-feedback-tag-item.tag-illegal::before {
  background: #ef4444;
}

.rlhf-feedback-tag-item.tag-illegal .tag-name {
  color: #ef4444;
  background: rgb(239 68 68 / 12%);
}

.rlhf-feedback-tag-item.tag-non-compliant::before {
  background: #f97316;
}

.rlhf-feedback-tag-item.tag-non-compliant .tag-name {
  color: #f97316;
  background: rgb(249 115 22 / 12%);
}

.rlhf-feedback-tag-item.tag-unreasonable::before {
  background: #f59e0b;
}

.rlhf-feedback-tag-item.tag-unreasonable .tag-name {
  color: #f59e0b;
  background: rgb(245 158 11 / 12%);
}

.rlhf-feedback-tag-item.tag-off-purpose::before {
  background: #d946ef;
}

.rlhf-feedback-tag-item.tag-off-purpose .tag-name {
  color: #d946ef;
  background: rgb(217 70 239 / 12%);
}

/* 喜欢采纳反馈 - 炫酷版 */
.rlhf-like-feedback-card {
  position: relative;
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: space-around;
  padding: 1rem 1.5rem;
  overflow: hidden;
  background: linear-gradient(
    145deg,
    hsl(var(--card)) 0%,
    hsl(var(--muted) / 20%) 100%
  );
  border: 1px solid hsl(var(--border) / 60%);
  border-radius: 16px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.rlhf-like-feedback-card::before {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 2px;
  content: '';
  background: linear-gradient(
    90deg,
    hsl(var(--primary)),
    hsl(var(--primary) / 40%),
    transparent
  );
  opacity: 0;
  transition: opacity 0.3s ease;
}

.rlhf-like-feedback-card:hover {
  border-color: hsl(var(--primary) / 30%);
  box-shadow: 0 8px 20px hsl(var(--foreground) / 8%);
  transform: translateY(-3px);
}

.rlhf-like-feedback-card:hover::before {
  opacity: 1;
}

.rlhf-like-feedback-card:hover .like-feedback-value {
  transform: scale(1.05);
}

.like-feedback-rate {
  font-size: 1.75rem;
  font-weight: 800;
  transition: transform 0.2s ease;
}

.rlhf-like-feedback-card:hover .like-feedback-rate {
  transform: scale(1.05);
}

.like-feedback-rate.like-rate {
  background: linear-gradient(135deg, hsl(var(--primary)) 0%, #22c55e 100%);
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.like-feedback-rate.dislike-rate {
  color: hsl(var(--foreground));
}

/* 旧样式保留兼容 */
.rlhf-stats-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 2rem;
  align-items: center;
  padding: 1rem 1.5rem;
  margin-bottom: 0.5rem;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.rlhf-stat-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.rlhf-stat-item .stat-label {
  font-size: 0.875rem;
  color: hsl(var(--muted-foreground));
}

.rlhf-stat-item .stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: hsl(var(--foreground));
}

.rlhf-stat-divider {
  width: 1px;
  height: 40px;
  background: hsl(var(--border));
}

.rlhf-rate-bar {
  display: flex;
  gap: 1rem;
  padding: 0.75rem 0;
}

.rlhf-rate-item {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  padding: 1rem;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.rlhf-rate-item .rate-label {
  margin-bottom: 0.5rem;
  font-size: 0.875rem;
  color: hsl(var(--muted-foreground));
}

.rlhf-rate-item .rate-value {
  font-size: 1.75rem;
  font-weight: 700;
  color: hsl(var(--foreground));
}

.rlhf-rate-item .rate-value-highlight {
  color: hsl(var(--primary));
}

.rlhf-rate-item .rate-sub {
  margin-top: 0.25rem;
  font-size: 0.875rem;
  color: hsl(var(--muted-foreground));
}

.rlhf-chart-card {
  position: relative;
  padding: 1rem;
  overflow: hidden;
  background: linear-gradient(
    145deg,
    hsl(var(--card)) 0%,
    hsl(var(--muted) / 20%) 100%
  );
  border: 1px solid hsl(var(--border) / 50%);
  border-radius: 16px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.rlhf-chart-card::before {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 1px;
  content: '';
  background: linear-gradient(
    90deg,
    transparent,
    hsl(var(--primary) / 30%),
    transparent
  );
}

.rlhf-chart-card:hover {
  border-color: hsl(var(--primary) / 30%);
  box-shadow: 0 8px 24px hsl(var(--foreground) / 6%);
}

/* ==================== RLHF 图表卡片 - 炫酷版 ==================== */
.rlhf-chart-card-cool {
  position: relative;
  padding: 0;
  overflow: hidden;
  background: hsl(var(--card) / 50%);
  border: 1px solid hsl(var(--border) / 30%);
  border-radius: 16px;
  box-shadow:
    0 0 0 1px hsl(var(--foreground) / 5%),
    0 20px 50px hsl(var(--background) / 30%);
  backdrop-filter: blur(20px);
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.rlhf-chart-card-cool:hover {
  box-shadow:
    0 0 0 1px hsl(var(--primary) / 25%),
    0 25px 60px hsl(var(--background) / 40%);
  transform: translateY(-4px);
}

/* 背景装饰 */
.rlhf-card-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
}

.rlhf-glow-orb {
  position: absolute;
  width: 250px;
  height: 250px;
  border-radius: 50%;
  opacity: 0.25;
  filter: blur(70px);
  animation: rlhf-orb-float 8s ease-in-out infinite;
}

.rlhf-glow-orb.orb-cyan {
  top: -60px;
  right: -60px;
  background: #06b6d4;
}

.rlhf-glow-orb.orb-purple {
  top: -60px;
  right: -60px;
  background: #8b5cf6;
  animation-delay: 2s;
}

.rlhf-grid-lines {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(hsl(var(--primary) / 3%) 1px, transparent 1px),
    linear-gradient(90deg, hsl(var(--primary) / 3%) 1px, transparent 1px);
  background-size: 40px 40px;
  opacity: 0.4;
}

/* 流光边框 */
.rlhf-border-glow {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  z-index: 2;
  height: 2px;
  overflow: hidden;
}

.rlhf-border-glow::after {
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  content: '';
  background: linear-gradient(
    90deg,
    transparent,
    hsl(var(--primary)),
    transparent
  );
  animation: rlhf-border-flow 4s linear infinite;
}

/* 卡片内容 */
.rlhf-card-content {
  position: relative;
  z-index: 5;
  padding: 1.25rem;
}

.rlhf-chart-title {
  display: flex;
  gap: 0.625rem;
  align-items: center;
  padding-bottom: 0.75rem;
  margin-bottom: 0.5rem;
  font-size: 1rem;
  font-weight: 600;
  color: hsl(var(--foreground));
  border-bottom: 1px solid hsl(var(--border) / 25%);
}

.rlhf-title-indicator {
  display: block;
  width: 4px;
  height: 1.125rem;
  background: hsl(var(--primary));
  border-radius: 2px;
  box-shadow: 0 0 10px hsl(var(--primary));
  animation: rlhf-indicator-pulse 2s ease-in-out infinite;
}

/* 加载动画 */
.rlhf-loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  background: hsl(var(--background) / 70%);
  backdrop-filter: blur(4px);
}

.rlhf-loading-text {
  font-weight: 600;
  color: hsl(var(--primary));
  animation: rlhf-loading-pulse 1.5s ease-in-out infinite;
}

/* 悬停增强 */
.rlhf-chart-card-cool:hover .rlhf-glow-orb {
  opacity: 0.4;
  animation-duration: 4s;
}

.rlhf-chart-card-cool:hover .rlhf-border-glow::after {
  animation-duration: 2s;
}

/* RLHF 抽检详情表格样式 */
.rlhf-detail-card {
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.rlhf-detail-card :deep(.ant-card-head) {
  padding: 0 1rem;
  border-bottom: 1px solid hsl(var(--border));
}

.rlhf-detail-card :deep(.ant-card-head-title) {
  font-size: 1rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.rlhf-detail-card :deep(.ant-card-body) {
  padding: 1rem;
}

/* ==================== 雷达图炫酷动效样式 ==================== */

/* 雷达图炫酷容器 */
.radar-chart-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 400px;
  overflow: visible; /* 允许标签和装饰元素显示在外面 */
}

/* 外层发光光环 */
.radar-outer-glow {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 320px;
  height: 320px;
  pointer-events: none;
  background: radial-gradient(
    circle,
    rgb(102 126 234 / 15%) 0%,
    rgb(102 126 234 / 8%) 40%,
    rgb(102 126 234 / 2%) 70%,
    transparent 100%
  );
  border-radius: 50%;
  transform: translate(-50%, -50%);
  animation: radar-glow-pulse 3s ease-in-out infinite;
}

/* 旋转光圈 */
.radar-rotating-ring {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 1;
  width: 300px;
  height: 300px;
  pointer-events: none;
  transform: translate(-50%, -50%);
}

.rotating-ring-svg {
  width: 100%;
  height: 100%;
  animation: ring-rotate 20s linear infinite;
}

/* 六维度指示线 */
.radar-dimension-lines {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 2;
  width: 300px;
  height: 300px;
  pointer-events: none;
  transform: translate(-50%, -50%);
}

.radar-pulse-line {
  opacity: 0.6;
  stroke-width: 2;
  animation: line-pulse 2s ease-in-out infinite;
}

.radar-pulse-line:nth-child(1) {
  animation-delay: 0s;
}

.radar-pulse-line:nth-child(2) {
  animation-delay: 0.33s;
}

.radar-pulse-line:nth-child(3) {
  animation-delay: 0.66s;
}

.radar-pulse-line:nth-child(4) {
  animation-delay: 1s;
}

.radar-pulse-line:nth-child(5) {
  animation-delay: 1.33s;
}

.radar-pulse-line:nth-child(6) {
  animation-delay: 1.66s;
}

/* 顶点脉冲圆点 */
.radar-vertex-pulse {
  animation: vertex-pulse 2s ease-in-out infinite;
}

/* 脉冲波纹效果 */
.radar-pulse-waves {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 0;
  width: 280px;
  height: 280px;
  pointer-events: none;
  transform: translate(-50%, -50%);
}

.pulse-wave {
  position: absolute;
  inset: 0;
  border: 1px solid rgb(102 126 234 / 40%);
  border-radius: 50%;
  animation: pulse-expand 4s ease-out infinite;
}

.pulse-wave-1 {
  animation-delay: 0s;
}

.pulse-wave-2 {
  animation-delay: 1.33s;
}

.pulse-wave-3 {
  animation-delay: 2.66s;
}

/* 维度标签已移除，使用 ECharts 雷达图自带标签 */

/* 悬停增强效果 */
.radar-chart-wrapper:hover .radar-outer-glow {
  background: radial-gradient(
    circle,
    rgb(102 126 234 / 25%) 0%,
    rgb(102 126 234 / 12%) 40%,
    rgb(102 126 234 / 4%) 70%,
    transparent 100%
  );
  animation-duration: 1.5s;
}

.radar-chart-wrapper:hover .rotating-ring-svg {
  animation-duration: 10s;
}

.radar-chart-wrapper:hover .dim-label {
  background: hsl(var(--card));
  box-shadow: 0 4px 12px rgb(102 126 234 / 20%);
}

/* ==================== 雷达图炫酷动效样式结束 ==================== */

/* ==================== 分页组件样式 ==================== */
:deep(.ant-pagination) {
  display: flex;
  gap: 4px;
  align-items: center;
}

:deep(.ant-pagination-item) {
  min-width: 32px;
  height: 32px;
  line-height: 30px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
  transition: all 0.2s ease;
}

:deep(.ant-pagination-item:hover) {
  color: hsl(var(--primary));
  border-color: hsl(var(--primary));
}

:deep(.ant-pagination-item-active) {
  background: hsl(var(--primary));
  border-color: hsl(var(--primary));
}

:deep(.ant-pagination-item-active a) {
  color: white;
}

:deep(.ant-pagination-prev),
:deep(.ant-pagination-next) {
  min-width: 32px;
  height: 32px;
  line-height: 30px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
  transition: all 0.2s ease;
}

:deep(.ant-pagination-prev:hover),
:deep(.ant-pagination-next:hover) {
  color: hsl(var(--primary));
  border-color: hsl(var(--primary));
}

:deep(.ant-pagination-disabled) {
  opacity: 0.4;
}

:deep(.ant-select-selector) {
  height: 32px !important;
  background: hsl(var(--card)) !important;
  border: 1px solid hsl(var(--border)) !important;
  border-radius: 6px !important;
}

:deep(.ant-pagination-options-quick-jumper input) {
  width: 50px;
  height: 32px;
  text-align: center;
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
}

/* Agent筛选下拉框样式 - 固定宽度，防止标签换行 */
.agent-filter-select {
  width: 380px;
}

.agent-filter-select :deep(.ant-select-selector) {
  flex-wrap: nowrap !important;
  height: auto !important;
  min-height: 32px !important;
  max-height: 32px !important;
  overflow: hidden !important;
}

.agent-filter-select :deep(.ant-select-selection-overflow) {
  flex-wrap: nowrap !important;
  overflow: hidden !important;
}

.agent-filter-select :deep(.ant-select-selection-overflow-item) {
  flex-shrink: 0;
}

.agent-filter-select :deep(.ant-select-selection-item) {
  max-width: 140px;
}

/* ==================== 性能优化 ==================== */

/* ==================== 炫酷效果样式结束 ==================== */
</style>
