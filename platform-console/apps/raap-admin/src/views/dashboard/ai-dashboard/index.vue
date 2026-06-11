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

import type { FunnelStage } from './types';

import type { ActivityApi, AgentApi, TenantApi } from '#/api/core/business';

import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

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
import {
  queryDashboardSummaryApi,
  queryMetricPaginatedApi,
} from '#/api/core/dashboard';
import CountTo from '#/components/CountTo.vue';

import AiCostBoard from './components/AiCostBoard.vue';
import AigcCenter from './components/AigcCenter.vue';
import ConversionFunnel from './components/ConversionFunnel.vue';

// ==================== 类型定义 ====================
// 注意：后端返回的 total_cost 是字符串类型
interface AgentCostItem {
  agent_code: string;
  agent_name: null | string;
  currency: string;
  total_cost: number | string;
  job_count: number;
  content_count: number;
}

interface JobCostItem {
  job_id: string;
  job_name: string;
  agent_code: string;
  agent_name: null | string;
  currency: string;
  total_cost: number | string;
  content_count: number;
  start_time: string;
  end_time: string;
}

// AIGC生成中心任务列表数据类型
interface JobTaskItem {
  job_id: string;
  job_name: string;
  agent_code: string;
  agent_name: null | string;
  status: string;
  target_count: null | number;
  content_count: number;
  start_time: null | string;
  end_time: null | string;
}

interface TotalCostItem {
  currency: string;
  total_cost: number | string;
  agent_count: number;
  job_count: number;
  content_count: number;
}

// 生成中心数据类型（兼容新旧字段名）
interface AgentStat {
  agent_code: string;
  agent_name?: null | string;
  // 新字段名
  content_count?: number; // 生成数量（从 content 表统计）
  call_count?: number; // 调用次数（从 expert_call_trace 表统计）
  is_running?: number; // 是否运行中（0/1，从 job 表 DEPLOYED 状态判断）
  // 旧字段名（兼容）
  total_calls?: number; // 旧字段：调用次数
  running_count?: number | string; // 旧字段：运行中数量
}

interface AgentTrend {
  agent_code: string;
  call_count: number;
  date: string;
}

// 每日生成文章数量趋势
interface AgentContentTrend {
  agent_code: string;
  content_count: number;
  date: string;
}

// 多维度AI评论专家组数据类型
interface CriticContentStats {
  pending_count: number; // 待输入文章量
  total_input_count: number; // 总输入文章量
  rejected_count: number; // 总拒绝文章量
  rejected_rate: number; // 总拒绝比例
}

interface CriticExpertStats {
  expert_func: string; // 专家函数名
  expert_name: string; // 专家名称
  expert_type: 'ban' | 'critic'; // 专家类型：ban=正负向，critic=评分类
  total_input: number; // 总输入量
  rejected_count: number; // 拒绝量
}

// 文章质量六维度数据类型
interface QualityDimension {
  expert_func: string; // 专家函数名
  expert_name: string; // 专家名称
  avg_score: number; // 平均分
}

// 分数区间定义（从高到低排列，用于垂直渲染）
const SCORE_RANGES = [
  {
    id: 'r5',
    min: 80,
    max: 100,
    label: '80 - 100',
    colorClass: 'score-range-excellent',
  },
  {
    id: 'r4',
    min: 60,
    max: 79,
    label: '60 - 79',
    colorClass: 'score-range-good',
  },
  {
    id: 'r3',
    min: 40,
    max: 59,
    label: '40 - 59',
    colorClass: 'score-range-medium',
  },
  {
    id: 'r2',
    min: 20,
    max: 39,
    label: '20 - 39',
    colorClass: 'score-range-low',
  },
  {
    id: 'r1',
    min: 0,
    max: 19,
    label: '0 - 19',
    colorClass: 'score-range-poor',
  },
];

interface ScoringExpertMeta {
  expert_func: string;
  expert_name: string;
  color: string;
  bgColor: string;
  icon: string;
  tooltip: string;
}

const EXPERT_STYLE_PRESETS = [
  {
    color: '#3B82F6',
    bgColor: 'rgba(59, 130, 246, 0.15)',
    icon: '📝',
  },
  {
    color: '#8B5CF6',
    bgColor: 'rgba(139, 92, 246, 0.15)',
    icon: '💡',
  },
  {
    color: '#EF4444',
    bgColor: 'rgba(239, 68, 68, 0.15)',
    icon: '🛡️',
  },
  {
    color: '#F59E0B',
    bgColor: 'rgba(245, 158, 11, 0.15)',
    icon: '👤',
  },
  {
    color: '#10B981',
    bgColor: 'rgba(16, 185, 129, 0.15)',
    icon: '⚙️',
  },
  {
    color: '#EC4899',
    bgColor: 'rgba(236, 72, 153, 0.15)',
    icon: '✨',
  },
];

// 治理中心数据类型
interface PersonaStats {
  persona_count: number; // 人设数量
  with_persona_count: number; // 有人设的内容数
  total_count: number; // 总内容数
  persona_ratio: number; // 人设适配占比
}

// Agent六维评分数据类型
interface AgentQualityScore {
  agent_code: string;
  agent_name: null | string;
  marketing_score: null | number;
  grace_score: null | number;
  quality_score: null | number;
  brand_score: null | number;
  creativity_score: null | number;
  persona_score: null | number;
  avg_score: null | number;
  content_count: number;
}

// 评分专家分数区间分布数据类型（5区间版，用于评分结果分布条形图）
interface CriticExpertScoreDistribution {
  expert_func: string; // 专家函数名，如 CriticContentQuality
  expert_name: string; // 专家名称
  score_range: string; // 分数区间，如 r1, r2, r3, r4, r5
  content_count: number; // 该区间的文章数
}

// 评分专家分数区间分布数据类型（10区间版，用于内容丰富度气泡图）
interface CriticExpertScoreDistribution10 {
  expert_func: string; // 专家函数名，如 CriticContentQuality
  expert_name: string; // 专家名称
  score_range: number; // 分数区间起始值，如 0, 10, 20, ..., 90
  content_count: number; // 该区间的文章数
}

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

// 统计学专家组 - 人群多样性热力图数据类型
interface AgentPersonaHeatmapItem {
  agent_code: string;
  agent_name: null | string;
  persona_name: string;
  content_count: number;
}

// 统计学专家组统计
interface StatisticsExpertStats {
  total_reviewed_count: number; // 总审核文章数
}

// ==================== 状态 ====================
const loading = ref(true);
const dataUpdateTime = ref(dayjs().format('YYYY-MM-DD HH:mm:ss'));
const performanceMode = ref(true);

// 分批加载状态
const priorityLoading = ref(true);
const secondaryLoading = ref(true);

// 模块折叠状态
const collapsedSections = ref<Record<string, boolean>>({
  aiCost: false, // AI算力成本看板
  funnel: false, // 内容转化漏斗
  aigc: false, // AIGC生成中心
  critic: false, // 多维度AI专家反馈组
  governance: false, // 治理中心
  rlhf: false, // 人工专家反馈
});

// 切换折叠状态
const toggleSection = (section: string) => {
  collapsedSections.value[section] = !collapsedSections.value[section];
};

// 路由参数处理 - 用于定位到特定看板
const route = useRoute();
const criticSectionRef = ref<HTMLElement | null>(null);
const rlhfSectionRef = ref<HTMLElement | null>(null);

// 面板ID映射
const PANEL_MAPPING: Record<
  string,
  { ref: () => HTMLElement | null; sectionKey: string }
> = {
  '123': { sectionKey: 'critic', ref: () => criticSectionRef.value }, // 专家组评分分值分布
  '456': { sectionKey: 'rlhf', ref: () => rlhfSectionRef.value }, // 人工专家反馈
};

// 从路由中获取 panelId（支持多种方式）
function getPanelIdFromRoute(): string | undefined {
  // 1. 路由参数：/dashboard/:panelId（前端定义的动态路由）
  if (route.params.panelId) {
    return route.params.panelId as string;
  }
  // 2. 查询参数：?panel=xxx
  if (route.query.panel) {
    return route.query.panel as string;
  }
  // 3. 从路径中解析：/dashboard/123（后端菜单配置的精确路径）
  const match = route.path.match(/\/dashboard\/(\d+)$/);
  if (match) {
    return match[1];
  }
  return undefined;
}

// 滚动到指定面板的函数
function scrollToPanel(panelId: string | undefined) {
  if (panelId && PANEL_MAPPING[panelId]) {
    const panel = PANEL_MAPPING[panelId];
    // 展开对应的 section
    collapsedSections.value[panel.sectionKey] = false;

    // 执行滚动的函数
    const doScroll = () => {
      nextTick(() => {
        const sectionEl = panel.ref();
        if (sectionEl) {
          // 使用 instant 瞬间定位
          // CSS scroll-margin-top 会自动预留顶部粘性筛选栏的空间
          sectionEl.scrollIntoView({ behavior: 'instant', block: 'start' });
        }
      });
    };

    // 1. 立即滚动一次，让用户立即看到目标区域
    setTimeout(doScroll, 50);

    // 2. 数据加载完成后再次滚动，确保位置精确
    if (loading.value) {
      const unwatch = watch(
        () => loading.value,
        (isLoading) => {
          if (!isLoading) {
            unwatch(); // 取消监听
            setTimeout(doScroll, 100); // 等待 DOM 渲染后再次定位
          }
        },
      );
    }
  }
}

// 监听路由变化，实现动态滚动到对应面板
watch(
  () => [route.path, route.query.panel],
  () => {
    const panelId = getPanelIdFromRoute();
    scrollToPanel(panelId);
  },
);

// 日期范围（默认 2026-01-01 到 2026-02-01）
const dateRange = ref<[dayjs.Dayjs, dayjs.Dayjs]>([
  dayjs('2026-01-01'),
  dayjs('2026-02-01'),
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

// 成本数据
const totalCostData = ref<TotalCostItem[]>([]);
const agentCostData = ref<AgentCostItem[]>([]);
const jobCostData = ref<JobCostItem[]>([]);

// 分页状态
const jobCostPagination = ref({
  current: 1,
  pageSize: 10,
  total: 0,
});

// 生成中心数据
const generationStats = ref({
  total_calls: 0,
});
const agentStatsList = ref<AgentStat[]>([]);
const agentDailyTrend = ref<AgentTrend[]>([]);
const agentContentDailyTrend = ref<AgentContentTrend[]>([]);

// 内容转化漏斗数据
const conversionFunnelData = ref<FunnelStage[]>([]);

// AIGC生成中心 - 任务列表
const jobTaskList = ref<JobTaskItem[]>([]);
const jobTaskActiveTab = ref<'completed' | 'not_deployed' | 'running'>(
  'completed',
);
const jobTaskPagination = ref({
  current: 1,
  pageSize: 6,
  total: 0,
});
// 环形图选中的 Agent（用于筛选任务列表）
const selectedChartAgentCode = ref<null | string>(null);
// Agent 卡片分页
const agentCardPagination = ref({
  current: 1,
  pageSize: 3,
  total: 0,
});

// 多维度AI评论专家组数据
const criticContentStats = ref<CriticContentStats>({
  pending_count: 0,
  total_input_count: 0,
  rejected_count: 0,
  rejected_rate: 0,
});
const criticExpertStats = ref<CriticExpertStats[]>([]);
const criticQualityDimensions = ref<QualityDimension[]>([]);

// ==================== 专家组评分流程图动画状态 ====================
// 粒子动画接口
interface ScoreParticle {
  id: number;
  expertKey: string;
  startX: number;
  startY: number;
  endX: number;
  endY: number;
  color: string;
  targetBucketId: string;
  score: number;
}

// 分数桶数据
const scoreBucketsData = ref<Record<string, number>>({
  r5: 0,
  r4: 0,
  r3: 0,
  r2: 0,
  r1: 0,
});

// 当前活跃的专家（用于动画高亮效果）
const activeExperts = ref<Record<string, boolean>>({});

// 粒子列表
const scoreParticles = ref<ScoreParticle[]>([]);

// 当前高亮的雷达图维度（用于联动）
const highlightedRadarDimension = ref<null | string>(null);

// 专家卡片和分数桶的DOM引用
const expertCardRefs = ref<Record<string, HTMLElement | null>>({});
const scoreBucketRefs = ref<Record<string, HTMLElement | null>>({});
const flowContainerRef = ref<HTMLElement | null>(null);

// 动画定时器
let flowAnimationTimer: null | ReturnType<typeof setInterval> = null;

// ==================== 表格自动滚动 ====================
let particleIdCounter = 0;

// 治理中心数据
const personaStats = ref<PersonaStats>({
  persona_count: 0,
  with_persona_count: 0,
  total_count: 0,
  persona_ratio: 0,
});
// 评分专家10区间分布数据（用于内容丰富度气泡图）
const criticExpertScoreDist10 = ref<CriticExpertScoreDistribution10[]>([]);

// 评分专家元数据（用于前端渲染）
const scoringExperts = ref<ScoringExpertMeta[]>([]);
// 柱状图点击选中的 Agent
const selectedAgentForDetail = ref<AgentQualityScore | null>(null);

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

// 统计学专家组 - 人群多样性热力图数据
const agentPersonaHeatmapData = ref<AgentPersonaHeatmapItem[]>([]);
const statisticsExpertStats = ref<StatisticsExpertStats>({
  total_reviewed_count: 0,
});

// 评分专家分数区间分布数据（5区间版）
const criticExpertScoreDist = ref<CriticExpertScoreDistribution[]>([]);

// 图表 Ref
const agentPieChartRef = ref<EchartsUIType>();
const { renderEcharts: renderAgentPieChart } = useEcharts(agentPieChartRef);

// 评分类专家组 - 雷达图 Ref
const scoringExpertRadarChartRef = ref<EchartsUIType>();
const { renderEcharts: renderScoringExpertRadarChart } = useEcharts(
  scoringExpertRadarChartRef,
);

// 治理中心图表 Ref
const qualityTrendChartRef = ref<EchartsUIType>();

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

// 统计学专家组 - 人群多样性热力图 Ref
const statisticsHeatmapChartRef = ref<EchartsUIType>();
const { renderEcharts: renderStatisticsHeatmapChart } = useEcharts(
  statisticsHeatmapChartRef,
);

// 统计学专家组 - 内容丰富度散点图 Ref
const contentRichnessScatterRef = ref<EchartsUIType>();
const { renderEcharts: renderContentRichnessScatter } = useEcharts(
  contentRichnessScatterRef,
);

// ==================== 主题切换监听 ====================
const { isDark } = usePreferences();

// ==================== 渐进式图表渲染 ====================
// 图表渲染状态
const chartRenderingState = ref({
  priority: false, // 首屏关键图表（成本看板、AIGC中心）
  secondary: false, // 次要图表（专家组反馈）
  tertiary: false, // 底部图表（RLHF、统计）
});

/** 渐进式渲染图表（按照页面从上到下的顺序） */
async function renderChartsProgressively() {
  // 第一阶段：立即渲染首屏关键图表（0ms）
  // 优先级1：AiCostBoard 成本饼图
  updateAgentPieChart();
  chartRenderingState.value.priority = true;

  // 第二阶段：渲染次要图表（100ms 延迟）
  await nextTick();
  setTimeout(() => {
    updateScoringExpertRadarChart();
    chartRenderingState.value.secondary = true;
  }, 100);

  // 第三阶段：渲染底部图表（200ms 延迟）
  setTimeout(() => {
    updateStatisticsHeatmapChart();
    updateContentRichnessScatter();
    chartRenderingState.value.tertiary = true;
  }, 200);

  // 第四阶段：渲染 RLHF 图表（300ms 延迟）
  setTimeout(() => {
    updateRLHFIssueBarChart();
    updateRLHFWordCloudChart();
    updateRLHFRadarChart();
    updateRLHFRadarCompareChart();
  }, 300);
}

// 监听主题变化，重新渲染所有 ECharts 图表
watch(isDark, async () => {
  // 等待 CSS 变量更新完成
  await nextTick();
  setTimeout(() => {
    renderChartsProgressively();
  }, 100);
});

// ==================== 评分专家元数据构建 ====================
const scoringExpertMetaMap = computed<Record<string, ScoringExpertMeta>>(() => {
  const map: Record<string, ScoringExpertMeta> = {};
  scoringExperts.value.forEach((expert) => {
    map[expert.expert_func] = expert;
  });
  return map;
});

function buildScoringExperts() {
  const source = [
    ...criticQualityDimensions.value,
    ...criticExpertScoreDist.value,
    ...criticExpertScoreDist10.value,
  ];
  const unique = new Map<string, string>();
  source.forEach((item) => {
    if (item.expert_func) {
      unique.set(item.expert_func, item.expert_name || item.expert_func);
    }
  });
  const entries = [...unique.entries()];
  scoringExperts.value = entries.map(([expert_func, expert_name], index) => {
    const style = EXPERT_STYLE_PRESETS[index % EXPERT_STYLE_PRESETS.length];
    return {
      expert_func,
      expert_name,
      color: style?.color || '#3B82F6',
      bgColor: style?.bgColor || 'rgba(59, 130, 246, 0.15)',
      icon: style?.icon || '✨',
      tooltip: `${expert_name} 评分专家`,
    };
  });

  activeExperts.value = Object.fromEntries(
    scoringExperts.value.map((expert) => [expert.expert_func, false]),
  );
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

/** 计算雷达图 SVG 顶点坐标（用于动态渲染线条和圆点） */
function getRadarSvgVertexPosition(
  index: number,
  total: number,
  centerX: number = 150,
  centerY: number = 150,
  radius: number = 120,
): { x: number; y: number } {
  // 从顶部（-90度/270度）开始，顺时针方向
  const angle = -Math.PI / 2 + (index * 2 * Math.PI) / total;
  const x = centerX + radius * Math.cos(angle);
  const y = centerY + radius * Math.sin(angle);
  return { x: Math.round(x), y: Math.round(y) };
}

// ==================== 常量定义 ====================
// 美元兑人民币汇率
const USD_TO_CNY_RATE = 7.5;

// Tooltip 弹出容器 - 渲染到 body 以避免 overflow 裁剪
const getPopupContainer = () => document.body;

// ==================== 计算属性 ====================
// 总成本数值（统一转换为人民币）
const totalCostValue = computed(() => {
  if (totalCostData.value.length === 0) return 0;
  // 将所有成本转换为人民币后汇总
  let totalCNY = 0;
  totalCostData.value.forEach((item) => {
    const cost = Number(item.total_cost) || 0;
    totalCNY += item.currency === 'CNY' ? cost : cost * USD_TO_CNY_RATE;
  });
  return totalCNY;
});

// 统计信息 - 从 cost_by_job 分页数据获取真实的 job 总数
const statsInfo = computed(() => {
  // agent_count 从 agentCostData 获取（已过滤 is_deleted 的 agent）
  const agentCount = agentCostData.value.length;
  // job_count 使用分页接口返回的 total（更准确）
  const jobCount = jobCostPagination.value.total;
  return { agentCount, jobCount };
});

// ==================== BAN 类型专家数据映射 ====================
/** 主题样式数组，根据索引循环使用 */
const BAN_EXPERT_THEMES = [
  'illegal-theme',
  'irregular-theme',
  'unreasonable-theme',
  'counterproductive-theme',
  'brand-theme',
];

/** BAN 类型专家列表（动态渲染） */
const banExpertStatsList = computed(() => {
  return criticExpertStats.value.map((stat, index) => {
    const theme = BAN_EXPERT_THEMES[index % BAN_EXPERT_THEMES.length];
    const rejectedRate =
      stat.total_input > 0 ? (stat.rejected_count / stat.total_input) * 100 : 0;

    return {
      ...stat,
      theme,
      rejectedRate,
      displayName: stat.expert_name || stat.expert_func,
      displayDescription:
        stat.description ||
        `${stat.expert_name || stat.expert_func} 专家审核统计`,
    };
  });
});

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

// ==================== 分批加载优化 ====================

/** 首屏核心数据（优先级1：成本、生成调用、内容漏斗、Critic 统计） */
async function fetchPriorityData() {
  priorityLoading.value = true;
  try {
    const params = buildParams();

    // 并行请求：Job 成本明细 + 首屏核心指标
    const [costByJobRes, summaryRes] = await Promise.all([
      // Job 成本明细（AiCostBoard 需要）- 必须单独请求（分页）
      queryMetricPaginatedApi<JobCostItem>({
        metric_key: 'cost_by_job',
        ...params,
        page: 1,
        page_size: 500,
      }),
      // 首屏核心指标（一次请求替代多个请求）
      queryDashboardSummaryApi(
        {
          metric_keys: [
            'cost_total_by_currency',
            'cost_by_agent',
            'generation_total_calls',
            'generation_agent_stats',
            'content_funnel',
            'critic_content_stats',
          ],
          ...params,
        },
        { use_cache: true },
      ),
    ]);

    // 成本数据
    totalCostData.value = summaryRes.results.cost_total_by_currency?.data || [];
    agentCostData.value = summaryRes.results.cost_by_agent?.data || [];
    jobCostData.value = costByJobRes.data || [];
    jobCostPagination.value.total = costByJobRes.pagination?.total || 0;

    // 生成中心数据
    generationStats.value.total_calls =
      summaryRes.results.generation_total_calls?.data?.[0]?.total_count || 0;
    agentStatsList.value =
      summaryRes.results.generation_agent_stats?.data || [];

    // Critic 统计
    criticContentStats.value = summaryRes.results.critic_content_stats
      ?.data?.[0] || {
      pending_count: 0,
      total_input_count: 0,
      rejected_count: 0,
      rejected_rate: 0,
    };

    // 内容转化漏斗数据
    const funnelRawData = summaryRes.results.content_funnel?.data?.[0] || {
      total_count: 0,
      valid_count: 0,
      online_count: 0,
      used_count: 0,
    };
    const totalCount = funnelRawData.total_count || 0;
    const validCount = funnelRawData.valid_count || 0;
    const onlineCount = funnelRawData.online_count || 0;
    const usedCount = funnelRawData.used_count || 0;

    conversionFunnelData.value = [
      {
        id: 'total',
        label: '全部生成',
        count: totalCount,
        percentage: 100,
        color: '#06b6d4',
        description: '',
      },
      {
        id: 'valid',
        label: '合规合法',
        count: validCount,
        percentage:
          totalCount > 0 ? Math.round((validCount / totalCount) * 100) : 0,
        color: '#8b5cf6',
        description: '',
      },
      {
        id: 'online',
        label: '已入业务选择',
        count: onlineCount,
        percentage:
          totalCount > 0 ? Math.round((onlineCount / totalCount) * 100) : 0,
        color: '#f59e0b',
        description: '',
      },
      {
        id: 'used',
        label: '业务已取用',
        count: usedCount,
        percentage:
          totalCount > 0 ? Math.round((usedCount / totalCount) * 100) : 0,
        color: '#10b981',
        description: '',
      },
    ];

    // 更新时间
    dataUpdateTime.value = dayjs().format('YYYY-MM-DD HH:mm:ss');
  } catch (error: unknown) {
    logger.error('加载首屏数据失败:', error);
  } finally {
    priorityLoading.value = false;
  }
}

// ==================== 次要数据分批加载 ====================

/** 次要数据批次1：生成中心趋势图 */
async function fetchSecondaryBatch1() {
  try {
    const params = buildParams();
    const summaryRes = await queryDashboardSummaryApi(
      {
        metric_keys: [
          'generation_agent_daily_trend',
          'generation_agent_content_daily_trend',
        ],
        ...params,
      },
      { use_cache: true },
    );
    agentDailyTrend.value =
      summaryRes.results.generation_agent_daily_trend?.data || [];
    agentContentDailyTrend.value =
      summaryRes.results.generation_agent_content_daily_trend?.data || [];
  } catch (error: unknown) {
    logger.error('加载次要数据批次1失败:', error);
  }
}

/** 次要数据批次2：RLHF 统计和标签分布 */
async function fetchSecondaryBatch2() {
  try {
    const params = buildParams();
    const summaryRes = await queryDashboardSummaryApi(
      {
        metric_keys: [
          'rlhf_inspection_stats',
          'rlhf_inspection_issue_tag_distribution',
          'rlhf_inspection_issue_tag_wordcloud',
        ],
        ...params,
      },
      { use_cache: true },
    );
    rlhfInspectionStats.value = summaryRes.results.rlhf_inspection_stats
      ?.data?.[0] || {
      total_inspection_count: 0,
      like_count: 0,
      dislike_count: 0,
      like_rate: 0,
      dislike_rate: 0,
      like_edit_rate: 0,
    };
    rlhfIssueTagDistribution.value =
      summaryRes.results.rlhf_inspection_issue_tag_distribution?.data || [];
    rlhfIssueTagWordCloud.value =
      summaryRes.results.rlhf_inspection_issue_tag_wordcloud?.data || [];
  } catch (error: unknown) {
    logger.error('加载次要数据批次2失败:', error);
  }
}

/** 次要数据批次3：统计学专家组热力图 */
async function fetchSecondaryBatch3() {
  try {
    const params = buildParams();
    const summaryRes = await queryDashboardSummaryApi(
      {
        metric_keys: [
          'statistics_agent_persona_heatmap',
          'statistics_expert_stats',
        ],
        ...params,
      },
      { use_cache: true },
    );
    agentPersonaHeatmapData.value =
      summaryRes.results.statistics_agent_persona_heatmap?.data || [];
    statisticsExpertStats.value = summaryRes.results.statistics_expert_stats
      ?.data?.[0] || {
      total_reviewed_count: 0,
    };
    await nextTick();
    updateStatisticsHeatmapChart();
    // buildHumanRadarScores() 移到 Batch 5，确保在 buildScoringExperts() 之后调用
  } catch (error: unknown) {
    logger.error('加载次要数据批次3失败:', error);
  }
}

/** 次要数据批次4：Critic 专家组 */
async function fetchSecondaryBatch4() {
  try {
    const params = buildParams();
    const summaryRes = await queryDashboardSummaryApi(
      {
        metric_keys: ['critic_expert_stats', 'critic_quality_dimensions'],
        ...params,
      },
      { use_cache: true },
    );
    criticExpertStats.value =
      summaryRes.results.critic_expert_stats?.data || [];
    criticQualityDimensions.value =
      summaryRes.results.critic_quality_dimensions?.data || [];
    await nextTick();
    updateScoringExpertRadarChart();
  } catch (error: unknown) {
    logger.error('加载次要数据批次4失败:', error);
  }
}

/** 次要数据批次5：Critic 分数分布 */
async function fetchSecondaryBatch5() {
  try {
    const params = buildParams();
    const summaryRes = await queryDashboardSummaryApi(
      {
        metric_keys: ['critic_expert_score_distribution'],
        ...params,
      },
      { use_cache: true },
    );
    criticExpertScoreDist.value =
      summaryRes.results.critic_expert_score_distribution?.data || [];
    buildScoringExperts();
    buildHumanRadarScores(); // ✅ 在 buildScoringExperts() 之后调用
    updateExpertRangeDistributionFromMetric(criticExpertScoreDist.value);
    await nextTick();
    updateRLHFRadarChart();
    updateScoringExpertRadarChart();
    updateRLHFRadarCompareChart();
  } catch (error: unknown) {
    logger.error('加载次要数据批次5失败:', error);
  }
}

/** 次要数据批次6：内容丰富度 + 分页详情（最后加载） */
async function fetchSecondaryBatch6() {
  try {
    const params = buildParams();

    // 并行加载内容丰富度和分页数据
    const [summaryRes] = await Promise.all([
      queryDashboardSummaryApi(
        {
          metric_keys: ['critic_expert_score_distribution_10'],
          ...params,
        },
        { use_cache: true },
      ),
      fetchJobTaskList(true),
      fetchRLHFInspectionDetailData(),
      fetchRLHFImprovementData(),
    ]);

    // 内容丰富度数据
    criticExpertScoreDist10.value =
      summaryRes.results.critic_expert_score_distribution_10?.data || [];

    // 更新 Agent 卡片分页 total
    agentCardPagination.value.total = agentStatsList.value.length;
    await nextTick();
    updateContentRichnessScatter();
  } catch (error: unknown) {
    logger.error('加载次要数据批次6失败:', error);
  } finally {
    secondaryLoading.value = false;
  }
}

/** 次要数据统一入口（调度各批次加载） */
async function fetchSecondaryData() {
  secondaryLoading.value = true;
  // 各批次依次加载，每批间隔 200ms
  setTimeout(() => fetchSecondaryBatch1(), 0);
  setTimeout(() => fetchSecondaryBatch2(), 200);
  setTimeout(() => fetchSecondaryBatch3(), 400);
  setTimeout(() => fetchSecondaryBatch4(), 600);
  setTimeout(() => fetchSecondaryBatch5(), 800);
  setTimeout(() => fetchSecondaryBatch6(), 1000);
}

/** 加载所有数据（两阶段加载） */
async function fetchAllData() {
  loading.value = true;
  try {
    // 阶段1：首屏核心数据（立即渲染）
    await fetchPriorityData();

    // 阶段2：次要数据（延迟加载，让首屏先显示）
    setTimeout(() => {
      fetchSecondaryData();
    }, 100);
  } catch (error: unknown) {
    logger.error('加载数据失败:', error);
  } finally {
    loading.value = false;
  }
}

// ==================== 后台静默刷新 ====================
// 刷新间隔（毫秒）- 30秒（性能优化：降低刷新频率）
const REFRESH_INTERVAL = 30 * 1000;
let refreshTimer: null | ReturnType<typeof setInterval> = null;

/** 静默刷新数据（不显示 loading 状态） */
async function silentRefreshData() {
  try {
    const params = buildParams();
    // 静默模式：不显示错误弹窗
    const silentOptions = { silentError: true };

    // 并行刷新所有关键统计数据
    const summaryRes = await queryDashboardSummaryApi(
      {
        metric_keys: [
          'cost_total_by_currency',
          'cost_by_agent',
          'generation_total_calls',
          'generation_agent_stats',
          'critic_content_stats',
          'critic_expert_stats',
          'statistics_expert_stats',
          'rlhf_inspection_stats',
        ],
        ...params,
      },
      { ...silentOptions, use_cache: true },
    );

    // 更新成本数据
    totalCostData.value = summaryRes.results.cost_total_by_currency?.data || [];
    agentCostData.value = summaryRes.results.cost_by_agent?.data || [];

    // 更新生成中心数据
    generationStats.value.total_calls =
      summaryRes.results.generation_total_calls?.data?.[0]?.total_count || 0;
    agentStatsList.value =
      summaryRes.results.generation_agent_stats?.data || [];

    // 更新多维度AI专家反馈组数据
    criticContentStats.value = summaryRes.results.critic_content_stats
      ?.data?.[0] || {
      pending_count: 0,
      total_input_count: 0,
      rejected_count: 0,
      rejected_rate: 0,
    };
    criticExpertStats.value =
      summaryRes.results.critic_expert_stats?.data || [];

    // 更新统计学专家组
    statisticsExpertStats.value = summaryRes.results.statistics_expert_stats
      ?.data?.[0] || {
      total_reviewed_count: 0,
    };

    // 更新 RLHF 数据
    rlhfInspectionStats.value = summaryRes.results.rlhf_inspection_stats
      ?.data?.[0] || {
      total_inspection_count: 0,
      like_count: 0,
      dislike_count: 0,
      like_rate: 0,
      dislike_rate: 0,
      like_edit_rate: 0,
    };

    // 更新时间
    dataUpdateTime.value = dayjs().format('YYYY-MM-DD HH:mm');

    // 渐进式渲染图表（静默刷新时不显示加载动画）
    nextTick(() => {
      renderChartsProgressively();
    });
  } catch (error) {
    logger.error('静默刷新数据失败:', error);
  }
}

/** 启动定时刷新 */
function startAutoRefresh() {
  if (refreshTimer) return;
  refreshTimer = setInterval(silentRefreshData, REFRESH_INTERVAL);
}

/** 停止定时刷新 */
function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

/** 处理页面可见性变化（性能优化） */
function handleVisibilityChange() {
  if (document.hidden) {
    // 页面隐藏时：停止刷新和动画，节省资源
    stopAutoRefresh();
    stopScoringFlowAnimation();
    logger.debug('[性能优化] 页面隐藏，已暂停刷新和动画');
  } else {
    // 页面显示时：恢复刷新和动画
    startAutoRefresh();
    startScoringFlowAnimation();
    // 立即刷新一次数据
    silentRefreshData();
    logger.debug('[性能优化] 页面显示，已恢复刷新和动画');
  }
}

/** 加载任务列表（使用 job_task_list 指标） */
async function fetchJobTaskList() {
  try {
    // 根据当前 Tab 确定要查询的状态
    let statusList: string[] = [];
    switch (jobTaskActiveTab.value) {
      case 'completed': {
        statusList = ['COMPLETED'];

        break;
      }
      case 'not_deployed': {
        statusList = ['NOT_DEPLOYED'];

        break;
      }
      case 'running': {
        statusList = ['DEPLOYED', 'PAUSED', 'RUNNING'];

        break;
      }
      // No default
    }

    // 优先使用环形图选中的 agent_code，否则使用筛选器的
    const agentCode = selectedChartAgentCode.value
      ? [selectedChartAgentCode.value]
      : confirmedFilters.value.agentCode;

    const params = buildParams();
    const res = await queryMetricPaginatedApi<JobTaskItem>({
      metric_key: 'job_task_list',
      ...params,
      agent_code: agentCode,
      status: statusList,
      page: 1,
      page_size: 500,
    });

    jobTaskList.value = res.data || [];
    jobTaskPagination.value.total = res.pagination?.total || 0;
  } catch (error: unknown) {
    logger.error('加载任务列表失败:', error);
    jobTaskList.value = [];
    jobTaskPagination.value.total = 0;
  }
}

/** 处理任务列表 Tab 切换 */
function handleJobTaskTabChange(activeKey: string) {
  jobTaskActiveTab.value = activeKey as
    | 'completed'
    | 'not_deployed'
    | 'running';
  jobTaskPagination.value.current = 1;
  fetchJobTaskList();
}

/** 处理 Agent 卡片分页变化 */
function handleAgentCardPageChange(page: number, pageSize: number) {
  agentCardPagination.value.current = page;
  agentCardPagination.value.pageSize = pageSize;
}

/** 处理环形图点击选择 Agent */
function handleAgentSelect(agentCode: null | string) {
  selectedChartAgentCode.value = agentCode;
  // 重置分页并刷新任务列表
  jobTaskPagination.value.current = 1;
  fetchJobTaskList();
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
    logger.error('加载 RLHF 抽检详情失败:', error);
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
    logger.error('加载 RLHF 改进点摘要失败:', error);
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
    logger.error('加载反馈词文章列表失败:', error);
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

/** 更新 Agent 成本扇形图 */
function updateAgentPieChart() {
  // 按 Agent 聚合（合并不同币种，统一转换为人民币）
  const agentMap = new Map<string, { name: string; value: number }>();
  agentCostData.value.forEach((item) => {
    const key = item.agent_code;
    const existing = agentMap.get(key);
    // 根据币种转换为人民币
    let cost = Number(item.total_cost) || 0;
    if (item.currency !== 'CNY') {
      cost = cost * USD_TO_CNY_RATE;
    }
    if (existing) {
      existing.value += cost;
    } else {
      agentMap.set(key, {
        name: item.agent_name || item.agent_code,
        value: cost,
      });
    }
  });

  const pieData = [...agentMap.values()];

  if (pieData.length === 0) {
    renderAgentPieChart({
      title: {
        text: '投入成本分布',
        left: 'center',
        textStyle: { color: getVbenColor('--foreground') },
      },
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

  renderAgentPieChart({
    title: {
      text: '投入成本分布',
      left: 'center',
      top: 0,
      textStyle: { color: getVbenColor('--foreground'), fontSize: 14 },
    },
    tooltip: {
      trigger: 'item',
      formatter: (params: { name: string; percent: number; value: number }) => {
        return `${params.name}: ${params.value.toFixed(2)}元 (${params.percent}%)`;
      },
    },
    legend: {
      type: 'scroll',
      orient: 'horizontal',
      bottom: 0,
      left: 'center',
      width: '90%',
      textStyle: {
        color: getVbenColor('--foreground'),
        fontSize: 11,
        width: 80,
        overflow: 'truncate',
        ellipsis: '...',
      },
      tooltip: {
        show: true,
      },
      pageTextStyle: {
        color: getVbenColor('--foreground'),
      },
      pageIconColor: getVbenColor('--foreground'),
      pageIconInactiveColor: getVbenColor('--muted-foreground'),
      pageIconSize: 10,
      pageButtonGap: 5,
      itemWidth: 10,
      itemHeight: 10,
      itemGap: 6,
      formatter: (name: string) => {
        return name.length > 10 ? `${name.slice(0, 10)}...` : name;
      },
    },
    color: [
      '#3b82f6', // blue
      '#22c55e', // green
      '#f59e0b', // amber
      '#ef4444', // red
      '#8b5cf6', // violet
      '#06b6d4', // cyan
      '#ec4899', // pink
      '#14b8a6', // teal
      '#f97316', // orange
      '#6366f1', // indigo
    ],
    animationDuration: 1500,
    animationEasing: 'cubicOut',
    series: [
      {
        name: '成本分布',
        type: 'pie',
        radius: ['35%', '60%'],
        center: ['50%', '45%'],
        avoidLabelOverlap: true,
        itemStyle: {
          borderRadius: 8,
          borderColor: getVbenColor('--background'),
          borderWidth: 3,
          shadowBlur: 10,
          shadowColor: 'rgba(0, 0, 0, 0.15)',
        },
        label: {
          show: false,
        },
        emphasis: {
          scale: true,
          scaleSize: 12,
          label: {
            show: true,
            fontSize: 13,
            fontWeight: 'bold',
          },
          itemStyle: {
            shadowBlur: 20,
            shadowColor: 'rgba(0, 0, 0, 0.3)',
          },
        },
        labelLine: {
          show: false,
        },
        data: pieData,
        animationType: 'scale',
        animationEasing: 'elasticOut',
        animationDelay: (idx: number) => idx * 100,
      },
    ],
  });
}

/** 更新评分类专家组 - 六维雷达图 */
function updateScoringExpertRadarChart() {
  // 使用真实数据 criticQualityDimensions
  const dataMap = new Map<string, number>();
  criticQualityDimensions.value.forEach((item) => {
    dataMap.set(item.expert_func, Number(item.avg_score || 0));
  });

  const dimensionOrder =
    scoringExperts.value.length > 0
      ? scoringExperts.value.map((expert) => ({
          key: expert.expert_func,
          name: expert.expert_name,
        }))
      : criticQualityDimensions.value.map((item) => ({
          key: item.expert_func,
          name: item.expert_name || item.expert_func,
        }));

  // 构建数据值 - 从真实数据获取
  const values = dimensionOrder.map((dim) => dataMap.get(dim.key) || 0);
  if (dimensionOrder.length === 0 || values.length === 0) return;

  const dimensionColors = dimensionOrder.map((_, index) => {
    const fallback =
      EXPERT_STYLE_PRESETS[index % EXPERT_STYLE_PRESETS.length]?.color ||
      '#3B82F6';
    return scoringExperts.value[index]?.color || fallback;
  });
  const radarAnimationDuration = performanceMode.value ? 0 : 2000;
  const radarAnimationDelay = performanceMode.value
    ? 0
    : (idx: number) => idx * 100;

  renderScoringExpertRadarChart({
    backgroundColor: 'transparent',
    animationDuration: radarAnimationDuration,
    animationEasing: 'elasticOut',
    animationDelay: radarAnimationDelay,
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(15, 23, 42, 0.95)',
      borderColor: 'rgba(102, 126, 234, 0.3)',
      borderWidth: 1,
      borderRadius: 12,
      padding: [12, 16],
      textStyle: {
        color: '#fff',
        fontSize: 12,
      },
      extraCssText: 'box-shadow: 0 8px 32px rgba(102, 126, 234, 0.3);',
      formatter: (params: { value: number[] }) => {
        let result =
          '<div style="font-weight: 600; margin-bottom: 8px; font-size: 14px; background: linear-gradient(90deg, #667eea, #764ba2); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">✨ 六维评分详情</div>';
        dimensionOrder.forEach((dim, i) => {
          const val = params.value[i];
          const color = dimensionColors[i];
          let level;
          if (val >= 80) {
            level = '优秀';
          } else if (val >= 60) {
            level = '良好';
          } else if (val >= 40) {
            level = '一般';
          } else {
            level = '待提升';
          }
          result += `<div style="margin: 6px 0; display: flex; justify-content: space-between; align-items: center;">
            <span style="display: flex; align-items: center; gap: 6px;">
              <span style="width: 8px; height: 8px; border-radius: 50%; background: ${color}; box-shadow: 0 0 8px ${color};"></span>
              ${dim.name}
            </span>
            <span style="color: ${color}; font-weight: 700; text-shadow: 0 0 10px ${color};">${val} <span style="font-size: 10px; opacity: 0.8;">(${level})</span></span>
          </div>`;
        });
        return result;
      },
    },
    radar: {
      indicator: dimensionOrder.map((dim, i) => ({
        name: '', // 隐藏标签
        max: 100,
        color: dimensionColors[i],
      })),
      center: ['50%', '52%'],
      radius: '55%',
      startAngle: 90,
      splitNumber: 5,
      shape: 'polygon',
      axisName: {
        show: false,
      },
      axisNameGap: 15,
      splitArea: {
        show: true,
        areaStyle: {
          color: [
            'rgba(102, 126, 234, 0.02)',
            'rgba(102, 126, 234, 0.04)',
            'rgba(102, 126, 234, 0.06)',
            'rgba(102, 126, 234, 0.08)',
            'rgba(102, 126, 234, 0.12)',
          ],
          shadowColor: 'rgba(102, 126, 234, 0.1)',
          shadowBlur: 20,
        },
      },
      splitLine: {
        show: true,
        lineStyle: {
          color: [
            'rgba(102, 126, 234, 0.1)',
            'rgba(102, 126, 234, 0.15)',
            'rgba(102, 126, 234, 0.2)',
            'rgba(102, 126, 234, 0.25)',
            'rgba(102, 126, 234, 0.3)',
          ],
          width: 1,
        },
      },
      axisLine: {
        show: true,
        lineStyle: {
          color: 'rgba(102, 126, 234, 0.25)',
          width: 1,
          type: 'dashed',
        },
      },
    },
    series: [
      // 外层发光效果层
      {
        type: 'radar',
        symbol: 'none',
        data: [
          {
            value: values.map((v) => Math.min(v + 5, 100)),
            name: '外层光晕',
            areaStyle: {
              color: {
                type: 'radial',
                x: 0.5,
                y: 0.5,
                r: 0.8,
                colorStops: [
                  { offset: 0, color: 'rgba(102, 126, 234, 0.01)' },
                  { offset: 0.7, color: 'rgba(102, 126, 234, 0.08)' },
                  { offset: 1, color: 'rgba(102, 126, 234, 0.15)' },
                ],
              },
            },
            lineStyle: {
              color: 'rgba(102, 126, 234, 0.2)',
              width: 1,
            },
          },
        ],
        z: 1,
      },
      // 主数据层
      {
        type: 'radar',
        symbol: 'circle',
        symbolSize: 10,
        data: [
          {
            value: values,
            name: '六维评分',
            areaStyle: {
              color: {
                type: 'radial',
                x: 0.5,
                y: 0.5,
                r: 0.8,
                colorStops: [
                  { offset: 0, color: 'rgba(102, 126, 234, 0.5)' },
                  { offset: 0.5, color: 'rgba(102, 126, 234, 0.3)' },
                  { offset: 1, color: 'rgba(102, 126, 234, 0.1)' },
                ],
              },
              shadowColor: 'rgba(102, 126, 234, 0.4)',
              shadowBlur: 20,
            },
            lineStyle: {
              color: {
                type: 'linear',
                x: 0,
                y: 0,
                x2: 1,
                y2: 1,
                colorStops: [
                  { offset: 0, color: '#667eea' },
                  { offset: 0.5, color: '#764ba2' },
                  { offset: 1, color: '#667eea' },
                ],
              },
              width: 3,
              shadowColor: 'rgba(102, 126, 234, 0.6)',
              shadowBlur: 15,
            },
            itemStyle: {
              color: (params: { dataIndex: number }) =>
                dimensionColors[params.dataIndex] || '#667eea',
              borderColor: '#fff',
              borderWidth: 2,
              shadowColor: 'rgba(102, 126, 234, 0.8)',
              shadowBlur: 12,
            },
            emphasis: {
              itemStyle: {
                borderWidth: 3,
                shadowBlur: 20,
                shadowColor: 'rgba(102, 126, 234, 1)',
              },
              lineStyle: {
                width: 4,
                shadowBlur: 25,
              },
              areaStyle: {
                color: {
                  type: 'radial',
                  x: 0.5,
                  y: 0.5,
                  r: 0.8,
                  colorStops: [
                    { offset: 0, color: 'rgba(102, 126, 234, 0.6)' },
                    { offset: 0.5, color: 'rgba(102, 126, 234, 0.4)' },
                    { offset: 1, color: 'rgba(102, 126, 234, 0.2)' },
                  ],
                },
              },
            },
            label: {
              show: true,
              formatter: (params: { value: number }) => {
                return Math.round(params.value).toString();
              },
              color: getVbenColor('--foreground'),
              fontSize: 11,
              fontWeight: 'bold',
              textShadowColor: 'hsl(var(--background) / 0.8)',
              textShadowBlur: 4,
            },
          },
        ],
        animationDuration: 2000,
        animationEasing: 'cubicInOut',
      },
    ],
  });
}

// ==================== 专家组评分流程图动画函数 ====================

/** 获取分数所在区间 */
function getScoreRange(score: number) {
  return SCORE_RANGES.find((r) => score >= r.min && score <= r.max);
}

/** 生成一个评分粒子 */
function createScoreParticle(expertKey: string) {
  const expert = scoringExpertMetaMap.value[expertKey];
  if (!expert) {
    console.warn('[AI-Dashboard] 未找到专家:', expertKey);
    return;
  }

  // 获取该专家的真实平均分数
  const qualityData = criticQualityDimensions.value.find(
    (item) => item.expert_func === expertKey,
  );

  // 确保 avg_score 是有效数字，否则使用默认值 70
  const rawScore = qualityData?.avg_score;
  let avgScore = 70;
  if (typeof rawScore === 'number' && !Number.isNaN(rawScore)) {
    avgScore = rawScore;
  } else if (typeof rawScore === 'string' && rawScore !== '') {
    avgScore = Number(rawScore);
  }

  // 基于平均分生成一个随机分数（在平均分附近浮动）
  const variance = 15; // 浮动范围
  const score = Math.max(
    0,
    Math.min(100, avgScore + (Math.random() * variance * 2 - variance)),
  );

  const targetRange = getScoreRange(score);
  if (!targetRange) return;

  // 激活专家动画效果
  activeExperts.value[expertKey] = true;
  highlightedRadarDimension.value = expertKey;

  setTimeout(() => {
    activeExperts.value[expertKey] = false;
  }, 600);

  setTimeout(() => {
    if (highlightedRadarDimension.value === expertKey) {
      highlightedRadarDimension.value = null;
    }
  }, 1200);

  // 创建粒子
  const particleId = ++particleIdCounter;
  const particle: ScoreParticle = {
    id: particleId,
    expertKey,
    startX: 0, // 将在动画开始时计算
    startY: 0,
    endX: 0,
    endY: 0,
    color: expert.color,
    targetBucketId: targetRange.id,
    score: Math.round(score),
  };

  scoreParticles.value.push(particle);

  // 粒子动画完成后更新分数桶
  setTimeout(() => {
    scoreParticles.value = scoreParticles.value.filter(
      (p) => p.id !== particleId,
    );
    scoreBucketsData.value[targetRange.id]++;
  }, 800);
}

/** 启动评分流程动画 */
function startScoringFlowAnimation() {
  // 先停止可能存在的旧定时器（处理 HMR 热更新场景）
  stopScoringFlowAnimation();
  if (performanceMode.value) {
    return;
  }

  // 初始化分数桶数据（基于真实数据的比例）
  initScoreBucketsFromRealData();

  flowAnimationTimer = setInterval(() => {
    // 优化：只产生单个评分粒子，降低动画频率（从1.5秒改为3秒）
    const expertKeys = scoringExperts.value.map((expert) => expert.expert_func);
    if (expertKeys.length === 0) return;
    const shuffledExperts = [...expertKeys].toSorted(() => 0.5 - Math.random());

    // 只取第一个专家，减少粒子数量
    createScoreParticle(shuffledExperts[0]!);
  }, 3000);
}

/** 停止评分流程动画 */
function stopScoringFlowAnimation() {
  if (flowAnimationTimer) {
    clearInterval(flowAnimationTimer);
    flowAnimationTimer = null;
  }
}

/** 基于真实数据初始化分数桶 */
function initScoreBucketsFromRealData() {
  // 根据各专家的平均分数，模拟初始分布
  const scores = criticQualityDimensions.value.map(
    (item) => item.avg_score || 0,
  );
  const avgScore =
    scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : 70;

  // 基于平均分生成合理的分布
  if (avgScore >= 80) {
    scoreBucketsData.value = { r5: 45, r4: 30, r3: 15, r2: 7, r1: 3 };
  } else if (avgScore >= 70) {
    scoreBucketsData.value = { r5: 25, r4: 40, r3: 20, r2: 10, r1: 5 };
  } else if (avgScore >= 60) {
    scoreBucketsData.value = { r5: 15, r4: 30, r3: 35, r2: 15, r1: 5 };
  } else {
    scoreBucketsData.value = { r5: 10, r4: 20, r3: 30, r2: 25, r1: 15 };
  }
}

// 每个专家在各分值区间的占比分布数据
const expertRangeDistribution = ref<Record<string, Record<string, number>>>({
  r5: {},
  r4: {},
  r3: {},
  r2: {},
  r1: {},
});

/** 获取某专家在某分值区间的占比百分比 */
function getExpertRangePercent(rangeId: string, expertKey: string): number {
  const rangeData = expertRangeDistribution.value[rangeId];
  if (!rangeData) return 16.67; // 默认平均分配

  const total = Object.values(rangeData).reduce((a, b) => a + b, 0);
  if (total === 0) return 16.67;

  return ((rangeData[expertKey] || 0) / total) * 100;
}

/** 从后端指标数据更新评分专家分数区间分布 */
function updateExpertRangeDistributionFromMetric(
  data: CriticExpertScoreDistribution[],
) {
  if (!data || data.length === 0) return;

  // 初始化新的分布数据结构
  const newDistribution: Record<string, Record<string, number>> = {
    r5: {},
    r4: {},
    r3: {},
    r2: {},
    r1: {},
  };

  // 初始化所有专家在所有区间的计数为0
  const expertKeys =
    scoringExperts.value.length > 0
      ? scoringExperts.value.map((expert) => expert.expert_func)
      : [...new Set(data.map((item) => item.expert_func))];
  expertKeys.forEach((expertKey) => {
    ['r5', 'r4', 'r3', 'r2', 'r1'].forEach((rangeId) => {
      newDistribution[rangeId][expertKey] = 0;
    });
  });

  // 遍历后端返回的数据，填充真实的文章数量
  data.forEach((item) => {
    const { expert_func, score_range, content_count } = item;
    // 只处理六维评分专家的数据
    if (expert_func && score_range && expertKeys.includes(expert_func)) {
      newDistribution[score_range][expert_func] = content_count;
    }
  });

  // 更新响应式数据
  expertRangeDistribution.value = newDistribution;
}

/** 手动触发专家评分（用于点击交互） */
function triggerExpertScore(expertKey: string) {
  createScoreParticle(expertKey);
}

/** 更新统计学专家组 - 人群多样性热力图（酷炫版） */
function updateStatisticsHeatmapChart() {
  const data = agentPersonaHeatmapData.value;

  // 如果没有数据，显示暂无数据提示
  if (data.length === 0) {
    renderStatisticsHeatmapChart({
      backgroundColor: 'transparent',
      graphic: {
        type: 'text',
        left: 'center',
        top: 'middle',
        style: {
          text: '暂无数据',
          fill: 'rgba(148, 163, 184, 0.8)',
          fontSize: 16,
          fontWeight: 500,
        },
      },
    });
    return;
  }

  // 提取所有唯一的 Agent 和 persona
  const agentSet = new Set<string>();
  const personaSet = new Set<string>();
  // 构建 agent_name 到 agent_code 的映射（用于数据查找）
  const nameToCodeMap = new Map<string, string>();

  data.forEach((item) => {
    // 过滤掉已删除的 agent（agent_name 为 null 表示 agent 已删除）
    if (!item.agent_name) return;

    const agentName = item.agent_name;
    agentSet.add(agentName);
    personaSet.add(item.persona_name);
    nameToCodeMap.set(agentName, item.agent_code);
  });

  const agents = [...agentSet];
  const personas = [...personaSet];

  // 构建热力图数据 [x, y, value]
  const heatmapData: [number, number, number][] = [];
  const valueMap = new Map<string, number>();

  data.forEach((item) => {
    // 过滤掉已删除的 agent
    if (!item.agent_name) return;

    const agentName = item.agent_name;
    const key = `${agentName}-${item.persona_name}`;
    valueMap.set(key, item.content_count);
  });

  // 构建热力图数据
  agents.forEach((agent, xIndex) => {
    personas.forEach((persona, yIndex) => {
      const key = `${agent}-${persona}`;
      const value = valueMap.get(key) || 0;
      heatmapData.push([xIndex, yIndex, value]);
    });
  });

  // 计算最大值用于颜色范围
  const maxValue = Math.max(...heatmapData.map((d) => d[2]), 1);

  // X轴标签使用 Agent 名称
  const agentLabels = agents;

  // 酷炫渐变色配色方案：极光科技感
  const colorScale = {
    zero: 'rgba(51, 65, 85, 0.5)', // 0篇 - 深灰蓝（暗色背景）
    low: '#10b981', // 1-10篇 - 翠绿色
    medium: '#06b6d4', // 11-50篇 - 青色
    high: '#a855f7', // >50篇 - 紫罗兰
  };

  // 获取主题色用于 ECharts
  const foregroundColor = getVbenColor('--foreground');
  const mutedFgColor = getVbenColor('--muted-foreground');
  const borderColor = getVbenColor('--border');
  const cardColor = getVbenColor('--card');

  renderStatisticsHeatmapChart({
    backgroundColor: 'transparent',
    animationDuration: 2000,
    animationEasing: 'elasticOut',
    animationDelay: (idx: number) => idx * 8,
    tooltip: {
      show: true,
      trigger: 'item',
      confine: true,
      backgroundColor: cardColor || 'rgba(15, 23, 42, 0.95)',
      borderColor: 'rgba(139, 92, 246, 0.5)',
      borderWidth: 1,
      borderRadius: 12,
      padding: [14, 18],
      extraCssText:
        'box-shadow: 0 8px 32px rgba(139, 92, 246, 0.3); backdrop-filter: blur(10px);',
      textStyle: {
        color: foregroundColor || '#f1f5f9',
        fontSize: 13,
      },
      formatter: (params: { data: [number, number, number] }) => {
        const [xIdx, yIdx, value] = params.data;
        const personaName = personas[yIdx];
        const agentName = agentLabels[xIdx];
        const agentCode = nameToCodeMap.get(agentName) || agentName;
        let valueColor;
        if (value > 50) {
          valueColor = '#a855f7';
        } else if (value > 10) {
          valueColor = '#06b6d4';
        } else if (value > 0) {
          valueColor = '#10b981';
        } else {
          valueColor = mutedFgColor || '#64748b';
        }
        const fgColor = foregroundColor || '#f1f5f9';
        const subColor = mutedFgColor || '#94a3b8';
        return `
          <div style="line-height: 1.8;">
            <div style="font-size: 14px; font-weight: 600; color: ${fgColor}; margin-bottom: 6px;">
              <span style="color: ${valueColor};">●</span> ${agentName}
            </div>
            <div style="color: ${subColor}; font-size: 12px;">${agentCode}</div>
            <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid ${borderColor || 'rgba(148, 163, 184, 0.2)'};">
              <span style="color: ${subColor};">人设：</span>
              <span style="color: ${fgColor}; font-weight: 500;">${personaName}</span>
            </div>
            <div style="margin-top: 6px;">
              <span style="color: ${subColor};">近7天产出：</span>
              <span style="color: ${valueColor}; font-size: 20px; font-weight: 700; text-shadow: 0 0 10px ${valueColor};">${value}</span>
              <span style="color: ${subColor}; font-size: 12px;"> 篇</span>
            </div>
          </div>
        `;
      },
    },
    grid: {
      top: 50,
      bottom: 30,
      left: 120,
      right: 30,
      containLabel: false,
    },
    xAxis: {
      type: 'category',
      data: agentLabels,
      position: 'top',
      axisLabel: {
        rotate: 45,
        fontSize: 11,
        color: mutedFgColor || '#94a3b8',
        fontWeight: 600,
        interval: 0,
      },
      axisLine: {
        show: true,
        lineStyle: {
          color: borderColor || 'rgba(148, 163, 184, 0.15)',
          width: 1,
        },
      },
      axisTick: { show: false },
      splitLine: {
        show: true,
        lineStyle: {
          color: borderColor || 'rgba(148, 163, 184, 0.08)',
          width: 1,
        },
      },
    },
    yAxis: {
      type: 'category',
      data: personas,
      axisLabel: {
        fontSize: 12,
        color: foregroundColor || '#cbd5e1',
        fontWeight: 500,
        padding: [0, 12, 0, 0],
      },
      axisLine: {
        show: true,
        lineStyle: {
          color: borderColor || 'rgba(148, 163, 184, 0.15)',
          width: 1,
        },
      },
      axisTick: { show: false },
      splitLine: {
        show: true,
        lineStyle: {
          color: borderColor || 'rgba(148, 163, 184, 0.08)',
          width: 1,
        },
      },
    },
    visualMap: {
      min: 0,
      max: Math.max(maxValue, 50),
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 15,
      itemWidth: 20,
      itemHeight: 12,
      itemGap: 20,
      textStyle: {
        fontSize: 11,
        color: mutedFgColor || '#94a3b8',
        fontWeight: 500,
      },
      pieces: [
        { value: 0, label: '0篇', color: colorScale.zero },
        { gte: 1, lte: 10, label: '1-10篇', color: colorScale.low },
        { gte: 11, lte: 50, label: '11-50篇', color: colorScale.medium },
        { gt: 50, label: '>50篇', color: colorScale.high },
      ],
      show: false, // 隐藏内置图例，使用自定义底部图例
      type: 'piecewise',
    },
    series: [
      {
        name: '文章数',
        type: 'heatmap',
        data: heatmapData,
        label: {
          show: true,
          fontSize: 10,
          fontWeight: 700,
          position: 'inside',
          formatter: (params: { data: [number, number, number] }) => {
            const value = params.data[2];
            if (value === 0) {
              return `{zero|${value}}`;
            }
            if (value > 10) {
              return `{glow|${value}}`;
            }
            return `{normal|${value}}`;
          },
          rich: {
            glow: {
              color: '#ffffff',
              fontSize: 11,
              fontWeight: 700,
              textShadowColor: 'rgba(255, 255, 255, 0.5)',
              textShadowBlur: 4,
            },
            normal: {
              color: foregroundColor || '#0f172a',
              fontSize: 10,
              fontWeight: 700,
            },
            zero: {
              color: mutedFgColor || 'rgba(148, 163, 184, 0.5)',
              fontSize: 10,
              fontWeight: 500,
            },
          },
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 20,
            shadowColor: 'rgba(139, 92, 246, 0.6)',
            borderColor: cardColor || '#fff',
            borderWidth: 2,
          },
          label: {
            fontSize: 13,
            fontWeight: 800,
          },
        },
        itemStyle: {
          borderColor: cardColor || 'rgba(15, 23, 42, 0.8)',
          borderWidth: 2,
          borderRadius: 6,
        },
      },
    ],
  });
}

/** 更新内容丰富度散点图 - 炫酷呼吸灯特效版 */
function updateContentRichnessScatter() {
  const data = criticExpertScoreDist10.value;

  // 评分维度（从后端返回的专家维度动态构建）
  const dimensions =
    scoringExperts.value.length > 0
      ? scoringExperts.value.map((expert, index) => ({
          key: expert.expert_func,
          name: expert.expert_name,
          color:
            EXPERT_STYLE_PRESETS[index % EXPERT_STYLE_PRESETS.length]?.color ||
            '#3b82f6',
        }))
      : [
          ...new Map(
            data.map((item) => [
              item.expert_func,
              item.expert_name || item.expert_func,
            ]),
          ).entries(),
        ].map(([key, name], index) => ({
          key,
          name,
          color:
            EXPERT_STYLE_PRESETS[index % EXPERT_STYLE_PRESETS.length]?.color ||
            '#3b82f6',
        }));

  if (data.length === 0) {
    renderContentRichnessScatter({
      backgroundColor: 'transparent',
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

  // 分数区间（0-100，每10分一个区间）
  const scoreRanges = [
    '0',
    '10',
    '20',
    '30',
    '40',
    '50',
    '60',
    '70',
    '80',
    '90',
    '100',
  ];

  // 从后端数据构建聚合数据结构
  const aggregatedData: Map<string, Map<string, number>> = new Map();
  scoreRanges.forEach((range) => {
    aggregatedData.set(range, new Map());
  });

  // 遍历后端返回的数据，填充到聚合数据结构
  data.forEach((item) => {
    const rangeKey = String(item.score_range); // 转为字符串，如 "0", "10", "20"...
    const dimMap = aggregatedData.get(rangeKey);
    if (dimMap) {
      dimMap.set(item.expert_func, item.content_count);
    }
  });

  // 收集所有散点数据，用于筛选 Top 数据
  interface ScatterDataItem {
    value: [number, number, number];
    itemStyle: {
      color: string;
      opacity: number;
      shadowBlur: number;
      shadowColor: string;
    };
    dimInfo: { key: string; name: string };
  }
  const allScatterData: ScatterDataItem[] = [];

  // 构建各维度的散点数据（普通散点层）
  const seriesData = dimensions.map((dim, dimIndex) => {
    const scatterData: Array<{
      itemStyle: {
        borderColor: string;
        borderWidth: number;
        color: string;
        opacity: number;
        shadowBlur: number;
        shadowColor: string;
      };
      value: [number, number, number];
    }> = [];

    scoreRanges.slice(0, -1).forEach((range, rangeIndex) => {
      const rangeData = aggregatedData.get(range);
      if (rangeData) {
        const count = rangeData.get(dim.key) || 0;
        if (count > 0) {
          const dataItem = {
            value: [rangeIndex, dimIndex, count] as [number, number, number],
            itemStyle: {
              color: dim.color,
              shadowBlur: 12,
              shadowColor: dim.color,
              opacity: 0.75,
              borderColor: 'rgba(255, 255, 255, 0.3)',
              borderWidth: 1,
            },
          };
          scatterData.push(dataItem);
          // 添加到全局数据用于筛选 Top
          allScatterData.push({
            ...dataItem,
            dimInfo: { name: dim.name, key: dim.key },
          });
        }
      }
    });

    return {
      name: dim.name,
      type: 'scatter' as const,
      data: scatterData,
      symbolSize: (val: [number, number, number]) => {
        return Math.min(55, Math.max(10, Math.sqrt(val[2]) * 6));
      },
      emphasis: {
        focus: 'series' as const,
        itemStyle: {
          opacity: 1,
          shadowBlur: 25,
          shadowColor: 'inherit',
          borderColor: '#fff',
          borderWidth: 2,
        },
      },
    };
  });

  // 筛选 Top 8 数据用于 EffectScatter (呼吸灯特效)
  const topData = allScatterData
    .toSorted((a, b) => b.value[2] - a.value[2])
    .slice(0, 8)
    .map((item) => ({
      value: item.value,
      itemStyle: {
        color: item.itemStyle.color,
        shadowBlur: 20,
        shadowColor: item.itemStyle.color,
      },
    }));

  // X轴标签显示分数区间
  const xAxisLabels = scoreRanges.slice(0, -1).map((v, i) => {
    const next = scoreRanges[i + 1];
    return i === 9 ? '90-100' : `${v}-${next}`;
  });

  renderContentRichnessScatter({
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      padding: 0,
      backgroundColor: 'transparent',
      borderColor: 'transparent',
      borderWidth: 0,
      extraCssText: 'box-shadow: none;',
      formatter: (params: {
        data: { value: [number, number, number] };
        seriesName: string;
      }) => {
        const val = params.data.value || params.data;
        const [rangeIdx, dimIdx, count] = val as [number, number, number];
        const range = xAxisLabels[rangeIdx] || '-';
        const dim = dimensions[dimIdx];
        const color = dim?.color || '#3b82f6';

        // 炫酷玻璃拟态 Tooltip
        return `
          <div style="
            background: rgba(15, 23, 42, 0.92);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(59, 130, 246, 0.25);
            border-radius: 10px;
            padding: 14px 16px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.1);
            min-width: 160px;
          ">
            <div style="
              font-weight: 600;
              color: #fff;
              font-size: 13px;
              margin-bottom: 10px;
              padding-bottom: 8px;
              border-bottom: 1px solid rgba(148, 163, 184, 0.15);
              display: flex;
              align-items: center;
              gap: 8px;
            ">
              <span style="
                display: inline-block;
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: ${color};
                box-shadow: 0 0 10px ${color};
              "></span>
              ${dim?.name || params.seriesName}
            </div>
            <div style="font-size: 12px; color: #94a3b8; line-height: 1.9;">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>分数区间</span>
                <span style="color: #f1f5f9; font-weight: 500;">${range}</span>
              </div>
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>内容数量</span>
                <span style="
                  color: ${color};
                  font-size: 16px;
                  font-weight: 700;
                  font-family: 'SF Mono', 'Monaco', monospace;
                  text-shadow: 0 0 10px ${color};
                ">${count.toLocaleString()}</span>
              </div>
            </div>
          </div>
        `;
      },
    },
    legend: {
      show: false, // 隐藏内置图例，使用自定义图例
    },
    grid: {
      left: 110,
      right: 40,
      top: 30,
      bottom: 20,
      containLabel: false,
    },
    xAxis: {
      name: '内容质量评分区间',
      nameTextStyle: { color: '#64748b', fontSize: 11, padding: [8, 0, 0, 0] },
      nameLocation: 'middle',
      nameGap: 28,
      type: 'category',
      data: xAxisLabels,
      axisLine: {
        lineStyle: { color: 'rgba(148, 163, 184, 0.15)' },
      },
      axisLabel: {
        color: '#64748b',
        fontSize: 10,
        fontFamily: 'Inter, sans-serif',
      },
      axisTick: { show: false },
      splitLine: {
        show: true,
        lineStyle: { color: 'rgba(148, 163, 184, 0.08)', type: 'dashed' },
      },
    },
    yAxis: {
      type: 'category',
      data: dimensions.map((d) => d.name),
      axisLine: { show: false },
      axisLabel: {
        color: '#94a3b8',
        fontSize: 12,
        fontWeight: 500,
        fontFamily: 'Inter, sans-serif',
      },
      axisTick: { show: false },
      splitLine: {
        show: true,
        lineStyle: { color: 'rgba(148, 163, 184, 0.06)' },
      },
    },
    series: [
      // 普通散点层
      ...seriesData,
      // 高亮呼吸灯层 (EffectScatter) - 仅用于 Top 数据
      {
        name: 'Top Highlights',
        type: 'effectScatter',
        data: topData,
        symbolSize: (val: [number, number, number]) => {
          return Math.min(55, Math.max(12, Math.sqrt(val[2]) * 6));
        },
        showEffectOn: 'render',
        rippleEffect: {
          brushType: 'stroke',
          scale: 3.5,
          period: 4,
        },
        zlevel: 1,
      },
    ],
  });
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
  if (indicator.length === 0 || values.length === 0) return;
  const radarAnimationDuration = performanceMode.value ? 0 : 1800;

  renderRLHFRadarChart({
    animationDuration: radarAnimationDuration,
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
              formatter: (params: { value: number }) => {
                return Math.round(params.value).toString();
              },
              color: getVbenColor('--foreground'),
              fontSize: 12,
              fontWeight: 'bold',
            },
          },
        ],
        animationDuration: performanceMode.value ? 0 : 2000,
        animationEasing: 'cubicInOut',
      },
    ],
  });
}

/** 更新 RLHF 人工专家评分与AI专家对比雷达图 */
function updateRLHFRadarCompareChart() {
  // 从评分类专家组获取模型评分数据
  const modelDataMap = new Map<string, number>();
  criticQualityDimensions.value.forEach((item) => {
    modelDataMap.set(item.expert_func, Number(item.avg_score || 0));
  });

  const dimensionOrder =
    scoringExperts.value.length > 0
      ? scoringExperts.value.map((expert) => ({
          key: expert.expert_func,
          name: expert.expert_name,
        }))
      : criticQualityDimensions.value.map((item) => ({
          key: item.expert_func,
          name: item.expert_name || item.expert_func,
        }));
  if (dimensionOrder.length === 0) return;

  // 从左边雷达图数据获取人工专家评分（抽检评分）
  const humanScoreMap = new Map<string, number>();
  rlhfRadarScores.value.forEach((item) => {
    humanScoreMap.set(item.name, item.value);
  });

  // 构建对比数据
  const compareData = dimensionOrder.map((dim, index) => {
    const modelScore = modelDataMap.get(dim.key) || 0;
    const inspectionScore =
      humanScoreMap.get(dim.name) ?? getDefaultHumanScore(index);
    const diff =
      modelScore > 0 ? ((inspectionScore - modelScore) / modelScore) * 100 : 0;
    return {
      name: dim.name,
      key: dim.key,
      modelScore: Math.round(modelScore),
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
  if (indicator.length === 0) return;

  renderRLHFRadarCompareChart({
    tooltip: {
      show: true,
      trigger: 'item',
      confine: true,
      formatter: (params: { name: string; value: number[] }) => {
        if (!params || !params.value) return '';
        // params.name 是 series.data[].name，即 '模型评分' 或 '抽检评分'
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
      data: ['模型评分', '抽检评分'],
      textStyle: {
        color: getVbenColor('--foreground'),
      },
      formatter: (name: string) => {
        if (name === '模型评分') return '模型评分(虚线)';
        if (name === '抽检评分') return '抽检评分(实线)';
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
        formatter: (value: string) => {
          const item = compareData.find((d) => d.name === value);
          if (!item) return value;
          const diffIcon = item.diff < 0 ? '▼' : '▲';
          const diffStyleKey = item.diff < 0 ? 'down' : 'up';
          return `{title|${value}}\n{label|模型评分(虚线) ${item.modelScore}}\n{label|抽检评分(实线) ${item.inspectionScore}}\n{${diffStyleKey}|${diffIcon} ${Math.abs(item.diff)}%}`;
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
            name: '抽检评分',
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

/** 格式化数字（千分位） */
function formatNumber(num: null | number | undefined): string {
  const value = Number(num) || 0;
  return value.toLocaleString('zh-CN');
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
    title: '抽检标题',
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
    title: '抽检结果',
    dataIndex: 'inspection_result',
    key: 'inspection_result',
    width: 100,
    align: 'center' as const,
  },
  {
    title: '抽检人',
    dataIndex: 'inspector_name',
    key: 'inspector_name',
    width: 100,
    customRender: ({ record }: { record: RLHFInspectionDetailItem }) =>
      record.inspector_name || '-',
  },
  {
    title: '抽检时间',
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
  // 启动专家组评分流程动画
  nextTick(() => {
    setTimeout(() => {
      startScoringFlowAnimation();
    }, 1000); // 等待数据加载后启动
  });

  // 性能优化：监听页面可见性，页面隐藏时停止刷新和动画
  document.addEventListener('visibilitychange', handleVisibilityChange);

  // 路由参数处理 - 根据 panelId 定位到特定看板
  // 支持三种方式：路由参数、查询参数、路径解析
  const panelId = getPanelIdFromRoute();
  scrollToPanel(panelId);
});

onUnmounted(() => {
  // 清除定时刷新器
  stopAutoRefresh();
  // 停止专家组评分流程动画
  stopScoringFlowAnimation();
  // 移除页面可见性监听器
  document.removeEventListener('visibilitychange', handleVisibilityChange);
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
  dateRange.value = [dayjs('2026-01-01'), dayjs('2026-02-01')];
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

// 监听 loading 变化，在 Skeleton 隐藏后渐进式渲染图表
watch(
  () => loading.value,
  async (newLoading) => {
    if (!newLoading) {
      await nextTick();
      // 使用渐进式渲染，从上到下依次加载图表
      setTimeout(() => {
        renderChartsProgressively();
      }, 200);
    }
  },
);
</script>

<template>
  <div class="p-3" :class="{ 'performance-mode': performanceMode }">
    <!-- 粘性筛选头部 -->
    <div
      class="sticky top-0 z-10 -mx-3 -mt-3 mb-3 bg-background/90 px-3 pb-4 pt-2 shadow-lg backdrop-blur-md"
      style="border-bottom: 1px solid hsl(var(--border) / 30%)"
    >
      <!-- 标题行 -->
      <div class="mb-2 flex items-center gap-3">
        <span
          class="bg-gradient-to-r from-[hsl(var(--primary))] to-[#22c55e] bg-clip-text text-xl font-bold text-transparent"
          >全局分析</span
        >
        <span class="text-xs text-muted-foreground">
          数据更新时间：{{ dataUpdateTime }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">时间筛选</span>
          <RangePicker v-model:value="dateRange" :presets="presets" />
        </div>
        <!-- Agent筛选暂时隐藏 -->
        <div v-if="false" class="filter-item">
          <span class="filter-label">Agent筛选</span>
          <Select
            v-model:value="filters.agentCode"
            :filter-option="filterOption"
            :max-tag-count="2"
            :max-tag-text-length="8"
            :options="agentOptions"
            allow-clear
            class="agent-filter-select"
            mode="multiple"
            placeholder="所有 Agent"
            show-search
          />
        </div>
        <div class="filter-actions">
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

    <!-- ==================== AI算力成本看板 ==================== -->
    <AiCostBoard
      :agent-count="statsInfo.agentCount"
      :job-count="statsInfo.jobCount"
      :job-cost-data="jobCostData"
      :loading="loading"
      :total-cost-value="totalCostValue"
    />

    <!-- ==================== 内容转化漏斗 ==================== -->
    <div class="section-container conversion-funnel-section mt-4">
      <div class="section-glow-border">
        <div class="glow-border-top"></div>
        <div class="glow-border-right"></div>
        <div class="glow-border-bottom"></div>
        <div class="glow-border-left"></div>
      </div>

      <div class="section-header" @click="toggleSection('funnel')">
        <span class="section-title glow-title"> 生文管理链路数据一览 </span>
        <span class="section-collapse-btn">
          <RightOutlined
            v-if="collapsedSections.funnel"
            class="collapse-icon"
          />
          <DownOutlined v-else class="collapse-icon" />
        </span>
      </div>

      <div v-show="!collapsedSections.funnel" class="section-content">
        <ConversionFunnel :data="conversionFunnelData" height="200px" />
      </div>
    </div>

    <!-- ==================== AIGC生成中心 ==================== -->
    <AigcCenter
      :agent-card-pagination="agentCardPagination"
      :agent-cost-data="agentCostData"
      :agent-content-daily-trend="agentContentDailyTrend"
      :agent-stats-list="agentStatsList"
      :job-task-active-tab="jobTaskActiveTab"
      :job-task-list="jobTaskList"
      :loading="loading"
      :selected-agent-code="selectedChartAgentCode"
      @agent-card-page-change="handleAgentCardPageChange"
      @agent-select="handleAgentSelect"
      @job-task-tab-change="handleJobTaskTabChange"
    />

    <!-- ==================== 多维度AI评论专家组 ==================== -->
    <div ref="criticSectionRef" class="section-container critic-section mt-4">
      <!-- 流光边框装饰 -->
      <div class="section-glow-border">
        <div class="glow-border-top"></div>
        <div class="glow-border-right"></div>
        <div class="glow-border-bottom"></div>
        <div class="glow-border-left"></div>
      </div>
      <!-- 背景装饰层 -->
      <div class="section-bg-decoration">
        <div class="section-glow-orb orb-violet"></div>
        <div class="section-glow-orb orb-rose"></div>
        <div class="section-grid-lines"></div>
      </div>
      <!-- 角落装饰 -->
      <div class="section-corner section-corner-tl"></div>
      <div class="section-corner section-corner-tr"></div>
      <div class="section-corner section-corner-bl"></div>
      <div class="section-corner section-corner-br"></div>

      <div class="section-header" @click="toggleSection('critic')">
        <span class="section-title glow-title critic-title">
          多维度AI Expert反馈组
        </span>
        <span class="section-collapse-btn">
          <RightOutlined
            v-if="collapsedSections.critic"
            class="collapse-icon"
          />
          <DownOutlined v-else class="collapse-icon" />
        </span>
      </div>

      <div v-show="!collapsedSections.critic" class="section-content">
        <!-- 顶部统计栏 - 新样式 -->
        <!-- <Skeleton :loading="loading" active :paragraph="{ rows: 1 }">
          <div class="critic-header-bar">
            <div class="critic-header-left">
              <Button type="primary" class="expert-group-btn">
                正负向专家组
              </Button>
            </div>
            <div class="critic-header-right">
              <div class="critic-summary-box">
                <span class="summary-label">总审核文章</span>
                <span class="summary-value">
                  <CountTo
                    :end-value="criticContentStats.total_input_count || 0"
                    :decimals="0"
                    :duration="1"
                    :use-grouping="true"
                  />
                </span>
              </div>
              <div class="critic-summary-box">
                <span class="summary-label">审核不通过数量</span>
                <span class="summary-value">
                  <CountTo
                    :end-value="criticContentStats.rejected_count || 0"
                    :decimals="0"
                    :duration="1"
                    :use-grouping="true"
                  />
                </span>
              </div>
            </div>
          </div>
        </Skeleton> -->

        <!-- 评论专家卡片 - 炫酷版 -->

        <Skeleton :loading="loading" active :paragraph="{ rows: 4 }">
          <div class="critic-expert-grid-cool">
            <Card
              v-for="expert in banExpertStatsList"
              :key="expert.expert_func"
              :bordered="false"
              class="critic-card-cool"
              :class="expert.theme"
            >
              <div class="critic-card-bg">
                <div class="critic-glow-orb"></div>
                <div class="critic-pulse-ring"></div>
              </div>
              <div class="critic-border-glow"></div>
              <div class="critic-card-content">
                <div class="critic-header">
                  <div class="critic-title-group">
                    <span class="critic-title">{{ expert.displayName }}</span>
                  </div>
                  <Tooltip placement="top">
                    <template #title>
                      <div class="dimension-tooltip">
                        {{ expert.displayDescription }}
                      </div>
                    </template>
                    <QuestionCircleOutlined class="critic-help-icon" />
                  </Tooltip>
                </div>
                <div class="critic-stats">
                  <div class="critic-stat-item">
                    <span class="critic-stat-label">总审核文章数量</span>
                    <span class="critic-stat-value">
                      <CountTo
                        :end-value="expert.total_input || 0"
                        :decimals="0"
                        :duration="1"
                        :use-grouping="true"
                      />
                    </span>
                  </div>
                  <div class="critic-stat-item reject">
                    <span class="critic-stat-label">审核不通过数量</span>
                    <span class="critic-stat-value">
                      <CountTo
                        :end-value="expert.rejected_count || 0"
                        :decimals="0"
                        :duration="1"
                        :use-grouping="true"
                      />
                    </span>
                  </div>
                </div>
                <div class="critic-progress">
                  <div
                    class="progress-bar"
                    :style="{
                      width: `${expert.rejectedRate}%`,
                    }"
                  ></div>
                </div>
              </div>
            </Card>
          </div>
        </Skeleton>

        <!-- 评分类专家组区块 -->
        <!-- <Skeleton :loading="loading" active :paragraph="{ rows: 1 }">
          <div class="scoring-expert-header-bar">
            <div class="scoring-expert-header-left">
              <Button type="primary" class="expert-group-btn">
                评分类专家组
              </Button>
            </div>
            <div class="scoring-expert-header-right">
              <div class="critic-summary-box">
                <span class="summary-label">总审核文章</span>
                <span class="summary-value">
                  <CountTo
                    :end-value="criticContentStats.total_input_count || 0"
                    :decimals="0"
                    :duration="1"
                    :use-grouping="true"
                  />
                </span>
              </div>
            </div>
          </div>
        </Skeleton> -->

        <!-- 专家组评分分值分布 & 文章六维评分结果 - 酷炫动画版 -->
        <Card :bordered="false" class="scoring-flow-card">
          <!-- 统一标题 - 左上角 -->
          <div class="scoring-flow-header">
            <div class="scoring-flow-title">
              <span class="scoring-title-indicator"></span>
              <span>Expert组评分分值分布</span>
              <Tooltip placement="right">
                <template #title>
                  <div class="dimension-tooltip">
                    <div class="tooltip-section-title">评分流程说明</div>
                    <div class="tooltip-item">
                      <b>待评分文章库</b>：等待专家组评分的文章数量
                    </div>
                    <div class="tooltip-item">
                      <b>多维审核专家</b
                      >：包含语法、创造力、品牌、人设、平台适应度等多个维度的评分专家
                    </div>
                    <div class="tooltip-item">
                      <b>评分结果分布</b>：展示各分数区间的文章数量分布
                    </div>
                    <div class="tooltip-divider"></div>
                    <div class="tooltip-section-title">六维评分维度</div>
                    <div class="tooltip-item">
                      <b>平台适应度</b
                      >：评估内容是否符合目标平台的调性、风格和用户习惯
                    </div>
                    <div class="tooltip-item">
                      <b>语法正确性</b
                      >：评估内容的语法规范性、用词准确性和表达流畅度
                    </div>
                    <div class="tooltip-item">
                      <b>品牌调性匹配</b
                      >：评估内容是否与品牌形象、价值观保持一致
                    </div>
                    <div class="tooltip-item">
                      <b>内容创造力</b>：评估内容的原创性、新颖度和吸引力
                    </div>
                    <div class="tooltip-item">
                      <b>内容人设一致性</b>：评估内容是否符合预设的人物设定
                    </div>
                    <div class="tooltip-item">
                      <b>整体内容质量</b>：综合评估内容的完整性、逻辑性和可读性
                    </div>
                  </div>
                </template>
                <QuestionCircleOutlined class="info-icon" />
              </Tooltip>
            </div>
          </div>
          <div ref="flowContainerRef" class="scoring-flow-visualization">
            <!-- 左侧区域容器 -->
            <div class="flow-left-section">
              <!-- 左侧内容区域 -->
              <div class="flow-left-content">
                <!-- 区域1: 左侧待评分文章池 -->
                <div class="flow-article-pool">
                  <div class="pool-glow"></div>
                  <div class="pool-content">
                    <div class="pool-icon">📄</div>
                    <div class="pool-label">待评分文章库</div>
                    <div class="pool-value">
                      <CountTo
                        :end-value="criticContentStats.pending_count || 0"
                        :decimals="0"
                        :duration="1"
                        :use-grouping="true"
                      />
                    </div>
                    <div class="pool-status">
                      <span class="status-dot"></span>
                      <span class="status-text">生成中...</span>
                    </div>
                  </div>
                </div>

                <!-- SVG 连接线层 (文章池 -> 专家) - 使用精确的坐标系 -->
                <svg
                  class="flow-connection-svg"
                  viewBox="0 0 100 360"
                  preserveAspectRatio="none"
                >
                  <defs>
                    <!-- 渐变定义 -->
                    <linearGradient
                      id="flowGrad1"
                      x1="0%"
                      y1="0%"
                      x2="100%"
                      y2="0%"
                    >
                      <stop
                        offset="0%"
                        stop-color="#3B82F6"
                        stop-opacity="0.9"
                      />
                      <stop
                        offset="100%"
                        stop-color="#3B82F6"
                        stop-opacity="0.4"
                      />
                    </linearGradient>
                    <linearGradient
                      id="flowGrad2"
                      x1="0%"
                      y1="0%"
                      x2="100%"
                      y2="0%"
                    >
                      <stop
                        offset="0%"
                        stop-color="#8B5CF6"
                        stop-opacity="0.9"
                      />
                      <stop
                        offset="100%"
                        stop-color="#8B5CF6"
                        stop-opacity="0.4"
                      />
                    </linearGradient>
                    <linearGradient
                      id="flowGrad3"
                      x1="0%"
                      y1="0%"
                      x2="100%"
                      y2="0%"
                    >
                      <stop
                        offset="0%"
                        stop-color="#EF4444"
                        stop-opacity="0.9"
                      />
                      <stop
                        offset="100%"
                        stop-color="#EF4444"
                        stop-opacity="0.4"
                      />
                    </linearGradient>
                    <linearGradient
                      id="flowGrad4"
                      x1="0%"
                      y1="0%"
                      x2="100%"
                      y2="0%"
                    >
                      <stop
                        offset="0%"
                        stop-color="#F59E0B"
                        stop-opacity="0.9"
                      />
                      <stop
                        offset="100%"
                        stop-color="#F59E0B"
                        stop-opacity="0.4"
                      />
                    </linearGradient>
                    <linearGradient
                      id="flowGrad5"
                      x1="0%"
                      y1="0%"
                      x2="100%"
                      y2="0%"
                    >
                      <stop
                        offset="0%"
                        stop-color="#10B981"
                        stop-opacity="0.9"
                      />
                      <stop
                        offset="100%"
                        stop-color="#10B981"
                        stop-opacity="0.4"
                      />
                    </linearGradient>
                    <linearGradient
                      id="flowGrad6"
                      x1="0%"
                      y1="0%"
                      x2="100%"
                      y2="0%"
                    >
                      <stop
                        offset="0%"
                        stop-color="#EC4899"
                        stop-opacity="0.9"
                      />
                      <stop
                        offset="100%"
                        stop-color="#EC4899"
                        stop-opacity="0.4"
                      />
                    </linearGradient>
                    <!-- 发光滤镜 -->
                    <filter
                      id="glow"
                      x="-50%"
                      y="-50%"
                      width="200%"
                      height="200%"
                    >
                      <feGaussianBlur stdDeviation="2" result="blur" />
                      <feMerge>
                        <feMergeNode in="blur" />
                        <feMergeNode in="SourceGraphic" />
                      </feMerge>
                    </filter>
                  </defs>
                  <!-- 6条连接线，从中心(0,180)分散到6个专家位置 -->
                  <!-- 使用三次贝塞尔曲线实现平滑的S形曲线 -->
                  <!-- 专家1: y=30, 专家2: y=90, 专家3: y=150, 专家4: y=210, 专家5: y=270, 专家6: y=330 -->
                  <path
                    d="M0,180 C35,180 65,30 100,30"
                    fill="none"
                    stroke="url(#flowGrad1)"
                    stroke-width="2.5"
                    class="flow-line"
                  />
                  <path
                    d="M0,180 C35,180 65,90 100,90"
                    fill="none"
                    stroke="url(#flowGrad2)"
                    stroke-width="2.5"
                    class="flow-line"
                  />
                  <path
                    d="M0,180 C35,180 65,150 100,150"
                    fill="none"
                    stroke="url(#flowGrad3)"
                    stroke-width="2.5"
                    class="flow-line"
                  />
                  <path
                    d="M0,180 C35,180 65,210 100,210"
                    fill="none"
                    stroke="url(#flowGrad4)"
                    stroke-width="2.5"
                    class="flow-line"
                  />
                  <path
                    d="M0,180 C35,180 65,270 100,270"
                    fill="none"
                    stroke="url(#flowGrad5)"
                    stroke-width="2.5"
                    class="flow-line"
                  />
                  <path
                    d="M0,180 C35,180 65,330 100,330"
                    fill="none"
                    stroke="url(#flowGrad6)"
                    stroke-width="2.5"
                    class="flow-line"
                  />
                  <!-- 流动粒子 - 沿路径移动 -->
                  <circle r="4" fill="#3B82F6" filter="url(#glow)">
                    <animateMotion
                      dur="1.8s"
                      repeatCount="indefinite"
                      path="M0,180 C35,180 65,30 100,30"
                    />
                  </circle>
                  <circle r="4" fill="#8B5CF6" filter="url(#glow)">
                    <animateMotion
                      dur="2s"
                      repeatCount="indefinite"
                      path="M0,180 C35,180 65,90 100,90"
                      begin="0.3s"
                    />
                  </circle>
                  <circle r="4" fill="#EF4444" filter="url(#glow)">
                    <animateMotion
                      dur="1.7s"
                      repeatCount="indefinite"
                      path="M0,180 C35,180 65,150 100,150"
                      begin="0.6s"
                    />
                  </circle>
                  <circle r="4" fill="#F59E0B" filter="url(#glow)">
                    <animateMotion
                      dur="1.9s"
                      repeatCount="indefinite"
                      path="M0,180 C35,180 65,210 100,210"
                      begin="0.2s"
                    />
                  </circle>
                  <circle r="4" fill="#10B981" filter="url(#glow)">
                    <animateMotion
                      dur="2.1s"
                      repeatCount="indefinite"
                      path="M0,180 C35,180 65,270 100,270"
                      begin="0.5s"
                    />
                  </circle>
                  <circle r="4" fill="#EC4899" filter="url(#glow)">
                    <animateMotion
                      dur="2.2s"
                      repeatCount="indefinite"
                      path="M0,180 C35,180 65,330 100,330"
                      begin="0.8s"
                    />
                  </circle>
                </svg>

                <!-- 区域2: 中间专家节点 -->
                <div class="flow-experts-column">
                  <div class="experts-title">多维审核专家节点</div>
                  <div class="experts-list">
                    <div
                      v-for="expert in scoringExperts"
                      :key="expert.expert_func"
                      :ref="
                        (el) => {
                          if (el)
                            expertCardRefs[expert.expert_func] =
                              el as HTMLElement;
                        }
                      "
                      class="expert-node"
                      :class="{
                        'expert-active': activeExperts[expert.expert_func],
                        'expert-processing': activeExperts[expert.expert_func],
                      }"
                      :style="{
                        '--expert-color': expert.color,
                        '--expert-bg': expert.bgColor,
                      }"
                      @click="triggerExpertScore(expert.expert_func)"
                    >
                      <!-- 左侧连接锚点 -->
                      <div
                        class="expert-anchor-left"
                        :style="{
                          backgroundColor: expert.color,
                        }"
                      ></div>
                      <div
                        class="expert-icon"
                        :style="{
                          backgroundColor: expert.bgColor,
                        }"
                      >
                        <span>{{ expert.icon }}</span>
                      </div>
                      <div class="expert-info">
                        <div class="expert-name">
                          {{ expert.expert_name }}
                        </div>
                        <div class="expert-status">
                          <template v-if="activeExperts[expert.expert_func]">
                            <span
                              class="status-active"
                              :style="{ color: expert.color }"
                            >
                              <span class="status-dot-active"></span>
                              正在评审
                            </span>
                          </template>
                          <template v-else>
                            <span class="status-idle">待机中</span>
                          </template>
                        </div>
                      </div>
                      <Tooltip :title="expert.tooltip">
                        <QuestionCircleOutlined class="expert-help" />
                      </Tooltip>
                      <!-- 右侧连接锚点 -->
                      <div
                        class="expert-anchor-right"
                        :style="{ backgroundColor: expert.color }"
                      ></div>
                    </div>
                  </div>
                </div>

                <!-- SVG 连接线层 (专家 -> 分数桶) - 水平平行虚线 + 流动粒子 -->
                <svg
                  class="flow-connection-svg-right"
                  viewBox="0 0 80 360"
                  preserveAspectRatio="none"
                >
                  <defs>
                    <!-- 渐变定义 -->
                    <linearGradient
                      id="flowGradRight1"
                      x1="0%"
                      y1="0%"
                      x2="100%"
                      y2="0%"
                    >
                      <stop
                        offset="0%"
                        stop-color="#3B82F6"
                        stop-opacity="0.6"
                      />
                      <stop
                        offset="100%"
                        stop-color="#3B82F6"
                        stop-opacity="0.3"
                      />
                    </linearGradient>
                    <linearGradient
                      id="flowGradRight2"
                      x1="0%"
                      y1="0%"
                      x2="100%"
                      y2="0%"
                    >
                      <stop
                        offset="0%"
                        stop-color="#8B5CF6"
                        stop-opacity="0.6"
                      />
                      <stop
                        offset="100%"
                        stop-color="#8B5CF6"
                        stop-opacity="0.3"
                      />
                    </linearGradient>
                    <linearGradient
                      id="flowGradRight3"
                      x1="0%"
                      y1="0%"
                      x2="100%"
                      y2="0%"
                    >
                      <stop
                        offset="0%"
                        stop-color="#EF4444"
                        stop-opacity="0.6"
                      />
                      <stop
                        offset="100%"
                        stop-color="#EF4444"
                        stop-opacity="0.3"
                      />
                    </linearGradient>
                    <linearGradient
                      id="flowGradRight4"
                      x1="0%"
                      y1="0%"
                      x2="100%"
                      y2="0%"
                    >
                      <stop
                        offset="0%"
                        stop-color="#F59E0B"
                        stop-opacity="0.6"
                      />
                      <stop
                        offset="100%"
                        stop-color="#F59E0B"
                        stop-opacity="0.3"
                      />
                    </linearGradient>
                    <linearGradient
                      id="flowGradRight5"
                      x1="0%"
                      y1="0%"
                      x2="100%"
                      y2="0%"
                    >
                      <stop
                        offset="0%"
                        stop-color="#10B981"
                        stop-opacity="0.6"
                      />
                      <stop
                        offset="100%"
                        stop-color="#10B981"
                        stop-opacity="0.3"
                      />
                    </linearGradient>
                    <linearGradient
                      id="flowGradRight6"
                      x1="0%"
                      y1="0%"
                      x2="100%"
                      y2="0%"
                    >
                      <stop
                        offset="0%"
                        stop-color="#EC4899"
                        stop-opacity="0.6"
                      />
                      <stop
                        offset="100%"
                        stop-color="#EC4899"
                        stop-opacity="0.3"
                      />
                    </linearGradient>
                    <!-- 发光滤镜 -->
                    <filter
                      id="glowRight"
                      x="-50%"
                      y="-50%"
                      width="200%"
                      height="200%"
                    >
                      <feGaussianBlur stdDeviation="1.5" result="blur" />
                      <feMerge>
                        <feMergeNode in="blur" />
                        <feMergeNode in="SourceGraphic" />
                      </feMerge>
                    </filter>
                  </defs>
                  <!-- 6条水平平行虚线 -->
                  <path
                    d="M0,30 L80,30"
                    fill="none"
                    stroke="url(#flowGradRight1)"
                    stroke-width="2"
                    stroke-dasharray="6,4"
                    class="flow-line-right"
                  />
                  <path
                    d="M0,90 L80,90"
                    fill="none"
                    stroke="url(#flowGradRight2)"
                    stroke-width="2"
                    stroke-dasharray="6,4"
                    class="flow-line-right"
                  />
                  <path
                    d="M0,150 L80,150"
                    fill="none"
                    stroke="url(#flowGradRight3)"
                    stroke-width="2"
                    stroke-dasharray="6,4"
                    class="flow-line-right"
                  />
                  <path
                    d="M0,210 L80,210"
                    fill="none"
                    stroke="url(#flowGradRight4)"
                    stroke-width="2"
                    stroke-dasharray="6,4"
                    class="flow-line-right"
                  />
                  <path
                    d="M0,270 L80,270"
                    fill="none"
                    stroke="url(#flowGradRight5)"
                    stroke-width="2"
                    stroke-dasharray="6,4"
                    class="flow-line-right"
                  />
                  <path
                    d="M0,330 L80,330"
                    fill="none"
                    stroke="url(#flowGradRight6)"
                    stroke-width="2"
                    stroke-dasharray="6,4"
                    class="flow-line-right"
                  />
                  <!-- 流动粒子 - 沿路径移动 -->
                  <circle r="3" fill="#3B82F6" filter="url(#glowRight)">
                    <animateMotion
                      dur="1.2s"
                      repeatCount="indefinite"
                      path="M0,30 L80,30"
                    />
                  </circle>
                  <circle r="3" fill="#8B5CF6" filter="url(#glowRight)">
                    <animateMotion
                      dur="1.3s"
                      repeatCount="indefinite"
                      path="M0,90 L80,90"
                      begin="0.2s"
                    />
                  </circle>
                  <circle r="3" fill="#EF4444" filter="url(#glowRight)">
                    <animateMotion
                      dur="1.1s"
                      repeatCount="indefinite"
                      path="M0,150 L80,150"
                      begin="0.4s"
                    />
                  </circle>
                  <circle r="3" fill="#F59E0B" filter="url(#glowRight)">
                    <animateMotion
                      dur="1.25s"
                      repeatCount="indefinite"
                      path="M0,210 L80,210"
                      begin="0.15s"
                    />
                  </circle>
                  <circle r="3" fill="#10B981" filter="url(#glowRight)">
                    <animateMotion
                      dur="1.35s"
                      repeatCount="indefinite"
                      path="M0,270 L80,270"
                      begin="0.35s"
                    />
                  </circle>
                  <circle r="3" fill="#EC4899" filter="url(#glowRight)">
                    <animateMotion
                      dur="1.4s"
                      repeatCount="indefinite"
                      path="M0,330 L80,330"
                      begin="0.5s"
                    />
                  </circle>
                </svg>

                <!-- 区域3: 右侧评分分布 - 六色条带版 -->
                <div class="flow-score-distribution">
                  <div class="distribution-title">评分结果分布</div>
                  <div class="distribution-bars">
                    <div
                      v-for="(range, rangeIndex) in SCORE_RANGES"
                      :key="range.id"
                      :ref="
                        (el) => {
                          if (el) scoreBucketRefs[range.id] = el as HTMLElement;
                        }
                      "
                      class="score-bar-row"
                    >
                      <!-- 左侧连接锚点 -->
                      <div class="bucket-anchor-left"></div>
                      <div class="score-label-left">{{ range.label }}</div>
                      <!-- 六色条带轨道 -->
                      <div class="score-bar-track rainbow-track">
                        <div class="rainbow-bar-container">
                          <!-- 六个专家颜色段 -->
                          <Tooltip
                            v-for="(expert, expertIndex) in scoringExperts"
                            :key="expert.expert_func"
                            placement="top"
                            :get-popup-container="getPopupContainer"
                          >
                            <template #title>
                              <div class="segment-tooltip">
                                <span
                                  class="tooltip-dot"
                                  :style="{ backgroundColor: expert.color }"
                                ></span>
                                <span>{{ expert.expert_name }}</span>
                                <span class="tooltip-percent"
                                  >{{
                                    getExpertRangePercent(
                                      range.id,
                                      expert.expert_func,
                                    ).toFixed(1)
                                  }}%</span
                                >
                              </div>
                            </template>
                            <div
                              class="rainbow-segment"
                              :class="`rainbow-segment-${expertIndex + 1}`"
                              :style="{
                                width: `${getExpertRangePercent(
                                  range.id,
                                  expert.expert_func,
                                )}%`,
                                backgroundColor: expert.color,
                                animationDelay: `${rangeIndex * 0.2 + expertIndex * 0.15}s`,
                              }"
                            >
                              <span
                                class="segment-glow"
                                :style="{ backgroundColor: expert.color }"
                              ></span>
                            </div>
                          </Tooltip>
                        </div>
                      </div>
                    </div>
                  </div>
                  <!-- 六色图例 -->
                  <div class="rainbow-legend">
                    <div
                      v-for="expert in scoringExperts"
                      :key="expert.expert_func"
                      class="legend-dot-item"
                    >
                      <span
                        class="legend-color-dot"
                        :style="{ backgroundColor: expert.color }"
                      ></span>
                    </div>
                  </div>
                </div>

                <!-- 箭头指向雷达图 -->
                <div class="flow-arrow-to-radar">
                  <svg width="50" height="40" viewBox="0 0 50 40">
                    <defs>
                      <linearGradient
                        id="arrowGrad"
                        x1="0%"
                        y1="0%"
                        x2="100%"
                        y2="0%"
                      >
                        <stop offset="0%" stop-color="#3b82f6" />
                        <stop offset="100%" stop-color="#8b5cf6" />
                      </linearGradient>
                    </defs>
                    <polygon points="0,5 30,20 0,35" fill="url(#arrowGrad)" />
                    <polygon
                      points="15,10 50,20 15,30"
                      fill="url(#arrowGrad)"
                      opacity="0.6"
                    />
                  </svg>
                </div>
              </div>
            </div>

            <!-- 区域4: 文章六维评分结果（雷达图） - 炫酷动效版 -->
            <div class="flow-radar-section">
              <!-- 雷达图炫酷容器 -->
              <div class="radar-chart-wrapper">
                <!-- 外层发光光环 -->
                <div class="radar-outer-glow"></div>
                <!-- 旋转光圈 -->
                <div class="radar-rotating-ring">
                  <svg viewBox="0 0 300 300" class="rotating-ring-svg">
                    <defs>
                      <linearGradient
                        id="radarRingGradient"
                        x1="0%"
                        y1="0%"
                        x2="100%"
                        y2="100%"
                      >
                        <stop
                          offset="0%"
                          stop-color="#3b82f6"
                          stop-opacity="1"
                        />
                        <stop
                          offset="25%"
                          stop-color="#8b5cf6"
                          stop-opacity="0.8"
                        />
                        <stop
                          offset="50%"
                          stop-color="#06b6d4"
                          stop-opacity="0.3"
                        />
                        <stop
                          offset="75%"
                          stop-color="#10b981"
                          stop-opacity="0.8"
                        />
                        <stop
                          offset="100%"
                          stop-color="#3b82f6"
                          stop-opacity="1"
                        />
                      </linearGradient>
                      <filter id="radarGlow">
                        <feGaussianBlur stdDeviation="3" result="blur" />
                        <feMerge>
                          <feMergeNode in="blur" />
                          <feMergeNode in="SourceGraphic" />
                        </feMerge>
                      </filter>
                    </defs>
                    <circle
                      cx="150"
                      cy="150"
                      r="140"
                      fill="none"
                      stroke="url(#radarRingGradient)"
                      stroke-width="2"
                      stroke-dasharray="30 10 15 10"
                      filter="url(#radarGlow)"
                    />
                  </svg>
                </div>

                <!-- 动态维度指示器连线（根据专家数量动态生成） -->
                <svg class="radar-dimension-lines" viewBox="0 0 300 300">
                  <defs>
                    <!-- 动态生成渐变定义 -->
                    <linearGradient
                      v-for="(expert, index) in scoringExperts"
                      :id="`dimLineGrad${index + 1}`"
                      :key="`grad-${expert.expert_func}`"
                      x1="0%"
                      y1="0%"
                      x2="100%"
                      y2="0%"
                    >
                      <stop
                        offset="0%"
                        :stop-color="expert.color"
                        stop-opacity="0"
                      />
                      <stop
                        offset="50%"
                        :stop-color="expert.color"
                        stop-opacity="0.8"
                      />
                      <stop
                        offset="100%"
                        :stop-color="expert.color"
                        stop-opacity="0"
                      />
                    </linearGradient>
                    <filter id="dimGlow">
                      <feGaussianBlur stdDeviation="2" result="blur" />
                      <feMerge>
                        <feMergeNode in="blur" />
                        <feMergeNode in="SourceGraphic" />
                      </feMerge>
                    </filter>
                  </defs>
                  <!-- 动态生成从中心向外辐射的脉冲线 -->
                  <line
                    v-for="(expert, index) in scoringExperts"
                    :key="`line-${expert.expert_func}`"
                    x1="150"
                    y1="150"
                    :x2="
                      getRadarSvgVertexPosition(index, scoringExperts.length).x
                    "
                    :y2="
                      getRadarSvgVertexPosition(index, scoringExperts.length).y
                    "
                    class="radar-pulse-line"
                    :style="`stroke: url(#dimLineGrad${index + 1})`"
                  />
                  <!-- 动态生成顶点的脉冲圆点 -->
                  <circle
                    v-for="(expert, index) in scoringExperts"
                    :key="`dot-${expert.expert_func}`"
                    :cx="
                      getRadarSvgVertexPosition(index, scoringExperts.length).x
                    "
                    :cy="
                      getRadarSvgVertexPosition(index, scoringExperts.length).y
                    "
                    r="6"
                    :fill="expert.color"
                    class="radar-vertex-pulse"
                    filter="url(#dimGlow)"
                    :style="`animation-delay: ${index * 0.3}s`"
                  />
                </svg>

                <!-- 脉冲波纹效果 -->
                <div class="radar-pulse-waves">
                  <div class="pulse-wave pulse-wave-1"></div>
                  <div class="pulse-wave pulse-wave-2"></div>
                  <div class="pulse-wave pulse-wave-3"></div>
                </div>

                <!-- 雷达图图表容器 -->
                <div class="radar-chart-container">
                  <div
                    v-if="loading"
                    class="absolute inset-0 z-10 flex items-center justify-center bg-background/50"
                  >
                    <div class="text-muted-foreground">加载中...</div>
                  </div>
                  <EchartsUI
                    ref="scoringExpertRadarChartRef"
                    height="380px"
                    width="100%"
                  />
                </div>

                <!-- 维度标签已移除，使用 ECharts 雷达图自带的标签显示 -->
              </div>
            </div>
          </div>
        </Card>

        <!-- 统计学专家组区块 -->
        <Skeleton :loading="loading" active :paragraph="{ rows: 1 }">
          <div class="statistics-expert-header-bar">
            <div class="statistics-expert-header-left">
              <Button type="primary" class="expert-group-btn">
                系统默认专家组
              </Button>
            </div>
            <div class="statistics-expert-header-right">
              <div class="critic-summary-box">
                <span class="summary-label">总审核文章</span>
                <span class="summary-value">
                  <CountTo
                    :end-value="statisticsExpertStats.total_reviewed_count || 0"
                    :decimals="0"
                    :duration="1"
                    :use-grouping="true"
                  />
                </span>
              </div>
            </div>
          </div>
        </Skeleton>

        <!-- 人群多样性热力图 - 酷炫版 -->
        <Card :bordered="false" class="diversity-heatmap-card">
          <!-- 背景装饰层 -->
          <div class="heatmap-bg-decoration">
            <div class="heatmap-glow-orb orb-1"></div>
            <div class="heatmap-glow-orb orb-2"></div>
            <div class="heatmap-glow-orb orb-3"></div>
            <div class="heatmap-grid-lines"></div>
          </div>

          <!-- 扫描线动画 -->
          <div class="heatmap-scan-line"></div>

          <!-- 标题区域 -->
          <div class="heatmap-header">
            <div class="heatmap-title-wrapper">
              <div class="heatmap-title-icon">
                <span class="icon-pulse"></span>
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <rect x="3" y="3" width="7" height="7" rx="1" />
                  <rect x="14" y="3" width="7" height="7" rx="1" />
                  <rect x="3" y="14" width="7" height="7" rx="1" />
                  <rect x="14" y="14" width="7" height="7" rx="1" />
                </svg>
              </div>
              <div class="heatmap-title-text">
                <span class="title-main">人群多样性</span>
              </div>
            </div>
            <div class="heatmap-status-badge">
              <span class="status-dot"></span>
              <span class="status-text">LIVE</span>
            </div>
          </div>

          <!-- 图表区域 -->
          <div class="heatmap-chart-container">
            <!-- 四角装饰 -->
            <div class="heatmap-corner corner-tl"></div>
            <div class="heatmap-corner corner-tr"></div>
            <div class="heatmap-corner corner-bl"></div>
            <div class="heatmap-corner corner-br"></div>

            <div v-if="loading" class="heatmap-loading-overlay">
              <div class="loading-spinner">
                <div class="spinner-ring"></div>
                <div class="spinner-ring"></div>
                <div class="spinner-ring"></div>
              </div>
              <div class="loading-text">数据加载中...</div>
            </div>
            <EchartsUI
              ref="statisticsHeatmapChartRef"
              height="460px"
              width="100%"
            />
          </div>

          <!-- 底部自定义图例 -->
          <div class="heatmap-custom-legend">
            <div class="legend-scale">
              <div class="scale-bar"></div>
              <div class="scale-labels">
                <span>0篇</span>
                <span>1-10篇</span>
                <span>11-50篇</span>
                <span>&gt;50篇</span>
              </div>
            </div>
            <div class="legend-stats">
              <div class="stat-item">
                <span class="stat-label">总Agent</span>
                <span class="stat-value">{{
                  agentPersonaHeatmapData.length > 0
                    ? new Set(agentPersonaHeatmapData.map((d) => d.agent_code))
                        .size
                    : 0
                }}</span>
              </div>
              <div class="stat-item">
                <span class="stat-label">总人设</span>
                <span class="stat-value">{{
                  agentPersonaHeatmapData.length > 0
                    ? new Set(
                        agentPersonaHeatmapData.map((d) => d.persona_name),
                      ).size
                    : 0
                }}</span>
              </div>
            </div>
          </div>
        </Card>

        <!-- 内容丰富度散点图 - 炫酷版 -->
        <Card :bordered="false" class="scatter-cool-card mt-4">
          <!-- 背景装饰层 -->
          <div class="scatter-bg-decoration">
            <div class="scatter-glow-orb orb-1"></div>
            <div class="scatter-glow-orb orb-2"></div>
            <div class="scatter-glow-orb orb-3"></div>
            <div class="scatter-grid-lines"></div>
            <!-- 扫描线动画 -->
            <div class="scatter-scan-line"></div>
            <!-- 流动粒子 -->
            <div class="scatter-particles">
              <span class="particle p1"></span>
              <span class="particle p2"></span>
              <span class="particle p3"></span>
              <span class="particle p4"></span>
              <span class="particle p5"></span>
            </div>
          </div>

          <!-- 四边流光边框 -->
          <div class="scatter-border-glow">
            <div class="scatter-border-top"></div>
            <div class="scatter-border-right"></div>
            <div class="scatter-border-bottom"></div>
            <div class="scatter-border-left"></div>
          </div>

          <!-- 角落装饰 -->
          <div class="scatter-corner scatter-corner-tl"></div>
          <div class="scatter-corner scatter-corner-tr"></div>
          <div class="scatter-corner scatter-corner-bl"></div>
          <div class="scatter-corner scatter-corner-br"></div>

          <!-- 标题栏 -->
          <div class="scatter-card-header">
            <div class="scatter-card-title">
              <span class="scatter-title-indicator"></span>
              <span>内容丰富度</span>
            </div>
            <!-- 图例 - 六维度 -->
            <div class="scatter-legend">
              <div class="scatter-legend-item">
                <span
                  class="scatter-legend-dot"
                  style="
                    background: #3b82f6;
                    box-shadow: 0 0 8px rgb(59 130 246 / 80%);
                  "
                ></span>
                营销说服性
              </div>
              <div class="scatter-legend-item">
                <span
                  class="scatter-legend-dot"
                  style="
                    background: #10b981;
                    box-shadow: 0 0 8px rgb(16 185 129 / 80%);
                  "
                ></span>
                文章优雅性
              </div>
              <div class="scatter-legend-item">
                <span
                  class="scatter-legend-dot"
                  style="
                    background: #8b5cf6;
                    box-shadow: 0 0 8px rgb(139 92 246 / 80%);
                  "
                ></span>
                语法修饰
              </div>
              <div class="scatter-legend-item">
                <span
                  class="scatter-legend-dot"
                  style="
                    background: #f59e0b;
                    box-shadow: 0 0 8px rgb(245 158 11 / 80%);
                  "
                ></span>
                品牌匹配
              </div>
              <div class="scatter-legend-item">
                <span
                  class="scatter-legend-dot"
                  style="
                    background: #06b6d4;
                    box-shadow: 0 0 8px rgb(6 182 212 / 80%);
                  "
                ></span>
                创造力
              </div>
              <div class="scatter-legend-item">
                <span
                  class="scatter-legend-dot"
                  style="
                    background: #ec4899;
                    box-shadow: 0 0 8px rgb(236 72 153 / 80%);
                  "
                ></span>
                人设真实感
              </div>
            </div>
          </div>

          <!-- 图表区域 -->
          <div class="scatter-chart-container">
            <div v-if="loading" class="scatter-loading-overlay">
              <div class="scatter-loading-text">Loading Visualization...</div>
            </div>
            <EchartsUI
              ref="contentRichnessScatterRef"
              height="360px"
              width="100%"
            />
          </div>
        </Card>

        <!-- 安全专家组区块 -->
        <Skeleton :loading="loading" active :paragraph="{ rows: 1 }">
          <div class="security-expert-header-bar">
            <div class="security-expert-header-left">
              <Button type="primary" class="expert-group-btn">
                三方外延专家组
              </Button>
            </div>
            <div class="security-expert-header-right">
              <div class="critic-summary-box">
                <span class="summary-label">总审核文章</span>
                <span class="summary-value">1,030</span>
              </div>
              <div class="critic-summary-box">
                <span class="summary-label">审核不通过数量</span>
                <span class="summary-value">65</span>
              </div>
            </div>
          </div>
        </Skeleton>

        <!-- 安全专家组 - 三大平台卡片 (炫酷版) -->
        <div class="security-platform-grid">
          <!-- 腾讯云风控 -->
          <Card
            :bordered="false"
            class="security-platform-card-cool tencent-theme"
          >
            <!-- 背景装饰 -->
            <div class="security-card-bg">
              <div class="security-glow-orb"></div>
              <div class="security-grid-lines"></div>
            </div>
            <!-- 流光边框 -->
            <div class="security-border-glow">
              <div class="border-line border-top"></div>
              <div class="border-line border-right"></div>
              <div class="border-line border-bottom"></div>
              <div class="border-line border-left"></div>
            </div>
            <!-- 角落装饰 -->
            <div class="security-corner corner-tl"></div>
            <div class="security-corner corner-tr"></div>
            <div class="security-corner corner-bl"></div>
            <div class="security-corner corner-br"></div>
            <!-- 内容 -->
            <div class="security-card-content">
              <div class="security-platform-header">
                <div class="security-title-group">
                  <span class="security-title-indicator"></span>
                  <span class="security-platform-title">腾讯云风控</span>
                </div>
                <span class="security-logo-text tencent-text"
                  >Tencent <span class="tencent-cn">腾讯云</span></span
                >
              </div>
              <div class="security-platform-stats">
                <div class="security-stat-row">
                  <span class="security-stat-label">总审核文章数量</span>
                  <span class="security-stat-value">
                    <span class="stat-number">1,030</span>
                  </span>
                </div>
                <div class="security-stat-row">
                  <span class="security-stat-label">审核不通过数量</span>
                  <span class="security-stat-value security-reject-value">
                    <span class="stat-number reject">65</span>
                  </span>
                </div>
              </div>
              <!-- 状态指示灯 -->
              <div class="security-status">
                <span class="status-dot"></span>
                <span class="status-text">运行中</span>
              </div>
            </div>
          </Card>

          <!-- 阿里云风控 -->
          <Card
            :bordered="false"
            class="security-platform-card-cool aliyun-theme"
          >
            <!-- 背景装饰 -->
            <div class="security-card-bg">
              <div class="security-glow-orb"></div>
              <div class="security-grid-lines"></div>
            </div>
            <!-- 流光边框 -->
            <div class="security-border-glow">
              <div class="border-line border-top"></div>
              <div class="border-line border-right"></div>
              <div class="border-line border-bottom"></div>
              <div class="border-line border-left"></div>
            </div>
            <!-- 角落装饰 -->
            <div class="security-corner corner-tl"></div>
            <div class="security-corner corner-tr"></div>
            <div class="security-corner corner-bl"></div>
            <div class="security-corner corner-br"></div>
            <!-- 内容 -->
            <div class="security-card-content">
              <div class="security-platform-header">
                <div class="security-title-group">
                  <span class="security-title-indicator"></span>
                  <span class="security-platform-title">阿里云风控</span>
                </div>
                <img
                  src="https://img.alicdn.com/tfs/TB1Ly5oS3HqK1RjSZFPXXcwapXa-238-54.png"
                  alt="阿里云"
                  class="security-platform-logo aliyun-logo"
                />
              </div>
              <div class="security-platform-stats">
                <div class="security-stat-row">
                  <span class="security-stat-label">总审核文章数量</span>
                  <span class="security-stat-value">
                    <span class="stat-number">1,030</span>
                  </span>
                </div>
                <div class="security-stat-row">
                  <span class="security-stat-label">审核不通过数量</span>
                  <span class="security-stat-value security-reject-value">
                    <span class="stat-number reject">47</span>
                  </span>
                </div>
              </div>
              <!-- 状态指示灯 -->
              <div class="security-status">
                <span class="status-dot"></span>
                <span class="status-text">运行中</span>
              </div>
            </div>
          </Card>

          <!-- 火山引擎内容审核 -->
          <Card
            :bordered="false"
            class="security-platform-card-cool volcengine-theme"
          >
            <!-- 背景装饰 -->
            <div class="security-card-bg">
              <div class="security-glow-orb"></div>
              <div class="security-grid-lines"></div>
            </div>
            <!-- 流光边框 -->
            <div class="security-border-glow">
              <div class="border-line border-top"></div>
              <div class="border-line border-right"></div>
              <div class="border-line border-bottom"></div>
              <div class="border-line border-left"></div>
            </div>
            <!-- 角落装饰 -->
            <div class="security-corner corner-tl"></div>
            <div class="security-corner corner-tr"></div>
            <div class="security-corner corner-bl"></div>
            <div class="security-corner corner-br"></div>
            <!-- 内容 -->
            <div class="security-card-content">
              <div class="security-platform-header">
                <div class="security-title-group">
                  <span class="security-title-indicator"></span>
                  <span class="security-platform-title">火山引擎内容审核</span>
                </div>
                <div class="volcengine-logo-wrapper">
                  <svg
                    class="volcengine-icon"
                    viewBox="0 0 88 75"
                    xmlns="http://www.w3.org/2000/svg"
                  >
                    <path
                      fill="#00dcff"
                      d="M34.82,28.93l-14.97,46.07h32.16l-14.97-46.07c-.35-1.08-1.88-1.08-2.23,0Z"
                    />
                    <path
                      fill="#00dcff"
                      d="M12.83,42.36c-.35-1.08-1.88-1.08-2.23,0L0,75h9.42l7.01-21.57-3.59-11.06Z"
                    />
                    <path
                      fill="#006aff"
                      d="M29.52,20c-.35-1.08-1.88-1.08-2.23,0l-17.87,55h10.43l13.77-42.37-4.1-12.63Z"
                    />
                    <path
                      fill="#00dcff"
                      d="M71.73,36.43c-.35-1.08-1.88-1.08-2.23,0l-3.55,10.94,8.98,27.63h9.34l-12.53-38.57Z"
                    />
                    <path
                      fill="#006aff"
                      d="M50.82.81c-.35-1.08-1.88-1.08-2.23,0l-10.34,31.82,13.77,42.37h22.9L50.82.81Z"
                    />
                  </svg>
                  <span class="volcengine-text">火山引擎</span>
                </div>
              </div>
              <div class="security-platform-stats">
                <div class="security-stat-row">
                  <span class="security-stat-label">总审核文章数量</span>
                  <span class="security-stat-value">
                    <span class="stat-number">1,030</span>
                  </span>
                </div>
                <div class="security-stat-row">
                  <span class="security-stat-label">审核不通过数量</span>
                  <span class="security-stat-value security-reject-value">
                    <span class="stat-number reject">57</span>
                  </span>
                </div>
              </div>
              <!-- 状态指示灯 -->
              <div class="security-status">
                <span class="status-dot"></span>
                <span class="status-text">运行中</span>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>

    <!-- ==================== 治理中心（暂时隐藏） ==================== -->
    <div v-if="false" class="section-container mt-6">
      <div class="section-header" @click="toggleSection('governance')">
        <span class="section-title">治理中心</span>
        <span class="section-collapse-btn">
          <RightOutlined
            v-if="collapsedSections.governance"
            class="collapse-icon"
          />
          <DownOutlined v-else class="collapse-icon" />
        </span>
      </div>

      <div v-show="!collapsedSections.governance" class="section-content">
        <!-- 图表不放在 Skeleton 内，避免被卸载 -->
        <div class="governance-grid">
          <!-- 人设多样性 - 参考图2布局 -->
          <Card :bordered="false" class="governance-card">
            <div class="governance-card-title">人设多样性</div>
            <div class="persona-stats-row">
              <span class="stat-label">当前人设数量</span>
              <Skeleton :loading="loading" active :paragraph="false">
                <span class="stat-value-large">{{
                  formatNumber(personaStats.persona_count)
                }}</span>
              </Skeleton>
            </div>
            <div class="persona-stats-row mb-4">
              <span class="stat-label">当前生文人设适配占比</span>
            </div>
            <div class="relative h-[260px]">
              <div
                v-if="loading"
                class="absolute inset-0 z-10 flex items-center justify-center bg-background/50"
              >
                <div class="text-muted-foreground">加载中...</div>
              </div>
              <EchartsUI height="260px" width="100%" />
            </div>
          </Card>

          <!-- 内容丰富度 - 柱状图 -->
          <Card :bordered="false" class="governance-card">
            <div class="governance-card-title">内容丰富度</div>
            <div class="governance-card-subtitle">各Agent六维评分平均值</div>
            <div class="relative h-[320px]">
              <div
                v-if="loading"
                class="absolute inset-0 z-10 flex items-center justify-center bg-background/50"
              >
                <div class="text-muted-foreground">加载中...</div>
              </div>
              <EchartsUI
                ref="qualityTrendChartRef"
                height="320px"
                width="100%"
              />
            </div>

            <!-- 点击反馈详情列表 -->
            <div v-if="selectedAgentForDetail" class="agent-detail-panel mt-4">
              <div class="detail-header">
                <span class="detail-title"
                  >{{
                    selectedAgentForDetail.agent_name ||
                    selectedAgentForDetail.agent_code
                  }}
                  六维评分详情</span
                >
                <Button
                  type="text"
                  size="small"
                  @click="selectedAgentForDetail = null"
                >
                  关闭
                </Button>
              </div>
              <div class="detail-content">
                <div class="detail-item">
                  <span class="detail-label">营销效果</span>
                  <span class="detail-value">{{
                    selectedAgentForDetail.marketing_score ?? '-'
                  }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">文章优雅性</span>
                  <span class="detail-value">{{
                    selectedAgentForDetail.grace_score ?? '-'
                  }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">内容质量</span>
                  <span class="detail-value">{{
                    selectedAgentForDetail.quality_score ?? '-'
                  }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">品牌匹配</span>
                  <span class="detail-value">{{
                    selectedAgentForDetail.brand_score ?? '-'
                  }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">创造力</span>
                  <span class="detail-value">{{
                    selectedAgentForDetail.creativity_score ?? '-'
                  }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">人设真实感</span>
                  <span class="detail-value">{{
                    selectedAgentForDetail.persona_score ?? '-'
                  }}</span>
                </div>
                <div class="detail-item detail-item-highlight">
                  <span class="detail-label">综合平均分</span>
                  <span class="detail-value text-primary">{{
                    selectedAgentForDetail.avg_score ?? '-'
                  }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">文章数量</span>
                  <span class="detail-value">{{
                    selectedAgentForDetail.content_count
                  }}</span>
                </div>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>

    <!-- ==================== 人工专家反馈（RLHF报告） ==================== -->
    <div ref="rlhfSectionRef" class="section-container rlhf-section mt-4">
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
        <span class="section-title glow-title rlhf-title"> 人工专家反馈 </span>
        <span class="section-collapse-btn">
          <RightOutlined v-if="collapsedSections.rlhf" class="collapse-icon" />
          <DownOutlined v-else class="collapse-icon" />
        </span>
      </div>

      <div v-show="!collapsedSections.rlhf" class="section-content">
        <!-- 顶部两个大数据卡片 -->
        <Skeleton :loading="loading" active :paragraph="{ rows: 1 }">
          <div class="rlhf-top-stats">
            <div class="rlhf-big-stat-card">
              <span class="big-stat-label">人工专家总数</span>
              <div class="big-stat-value-row">
                <span class="big-stat-value">
                  <CountTo
                    :end-value="rlhfInspectionStats.expert_count || 6"
                    :decimals="0"
                    :duration="1"
                    :use-grouping="true"
                  />
                </span>
                <span class="big-stat-unit">人</span>
              </div>
            </div>
            <div class="rlhf-big-stat-card">
              <span class="big-stat-label">人工反馈文章总数</span>
              <div class="big-stat-value-row">
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
                <span class="big-stat-unit">篇</span>
              </div>
            </div>
          </div>
        </Skeleton>

        <!-- 正负向反馈结果 -->
        <div class="rlhf-section-subtitle">正负向反馈结果</div>
        <Skeleton :loading="loading" active :paragraph="{ rows: 1 }">
          <div class="rlhf-feedback-tags">
            <div class="rlhf-feedback-tag-item tag-illegal">
              <span class="tag-name">不合法</span>
              <span class="tag-count">
                <CountTo
                  :end-value="rlhfInspectionStats.illegal_count || 0"
                  :decimals="0"
                  :duration="1"
                  :use-grouping="true"
                />条
              </span>
              <span class="tag-percent">占总抽检 0%</span>
            </div>
            <div class="rlhf-feedback-tag-item tag-non-compliant">
              <span class="tag-name">不合规</span>
              <span class="tag-count">
                <CountTo
                  :end-value="rlhfInspectionStats.non_compliant_count || 3"
                  :decimals="0"
                  :duration="1"
                  :use-grouping="true"
                />条
              </span>
              <span class="tag-percent">占总抽检 5.0%</span>
            </div>
            <div class="rlhf-feedback-tag-item tag-unreasonable">
              <span class="tag-name">不合理</span>
              <span class="tag-count">
                <CountTo
                  :end-value="rlhfInspectionStats.unreasonable_count || 4"
                  :decimals="0"
                  :duration="1"
                  :use-grouping="true"
                />条
              </span>
              <span class="tag-percent">占总抽检 6.7%</span>
            </div>
            <div class="rlhf-feedback-tag-item tag-off-purpose">
              <span class="tag-name">不合目的</span>
              <span class="tag-count">
                <CountTo
                  :end-value="rlhfInspectionStats.off_purpose_count || 6"
                  :decimals="0"
                  :duration="1"
                  :use-grouping="true"
                />条
              </span>
              <span class="tag-percent">占总抽检 10.0%</span>
            </div>
          </div>
        </Skeleton>

        <!-- 评分反馈结果 - 雷达图 -->
        <div class="rlhf-section-subtitle">
          评分反馈结果
          <Tooltip placement="right">
            <template #title>
              <div class="dimension-tooltip">
                <div class="tooltip-item">
                  <b>平台适应度</b
                  >：评估内容是否符合目标平台的调性、风格和用户习惯，包括文案长度、表达方式、话题热度等
                </div>
                <div class="tooltip-item">
                  <b>整体内容质量</b
                  >：综合评估内容的完整性、逻辑性和可读性，包括结构清晰度、信息准确性等
                </div>
                <div class="tooltip-item">
                  <b>品牌调性匹配</b
                  >：评估内容是否与品牌形象、价值观和沟通风格保持一致
                </div>
                <div class="tooltip-item">
                  <b>内容创造力</b
                  >：评估内容的原创性、新颖度和吸引力，包括创意表达、独特视角等
                </div>
                <div class="tooltip-item">
                  <b>内容人设一致性</b
                  >：评估内容是否符合预设的人物设定，保持人设特征和说话风格的一致性
                </div>
                <div class="tooltip-item">
                  <b>语法正确性</b
                  >：评估内容的语法规范性、用词准确性和表达流畅度
                </div>
              </div>
            </template>
            <QuestionCircleOutlined class="info-icon" />
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
                  <span>人工专家反馈综合评分</span>
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
                  <span>人工专家评分与AI专家对比</span>
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
        <div class="rlhf-section-subtitle">喜欢采纳反馈</div>
        <Skeleton :loading="loading" :active="true" :paragraph="{ rows: 1 }">
          <div class="rlhf-like-feedback-bar">
            <div class="rlhf-like-feedback-card">
              <div class="like-feedback-row">
                <span class="like-feedback-label">喜欢数量</span>
                <span class="like-feedback-value">
                  <CountTo
                    :end-value="rlhfInspectionStats.like_count || 0"
                    :decimals="0"
                    :duration="1"
                    :use-grouping="true"
                  />
                </span>
              </div>
              <div class="like-feedback-row">
                <span class="like-feedback-label">喜欢率</span>
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
              <div class="like-feedback-row">
                <span class="like-feedback-label">不喜欢数量</span>
                <span class="like-feedback-value">
                  <CountTo
                    :end-value="rlhfInspectionStats.dislike_count || 0"
                    :decimals="0"
                    :duration="1"
                    :use-grouping="true"
                  />
                </span>
              </div>
              <div class="like-feedback-row">
                <span class="like-feedback-label">不喜欢率</span>
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

        <!-- 底部图表区域 - 抽检反馈 -->
        <Card :bordered="false" class="rlhf-chart-card mt-4">
          <div class="chart-card-title">抽检反馈</div>
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
                <div class="table-scroll-container">
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

        <!-- RLHF改进点摘要 -->
        <Card
          :bordered="false"
          class="rlhf-detail-card mt-4"
          title="RLHF改进点摘要"
        >
          <Skeleton :loading="loading" active :paragraph="{ rows: 6 }">
            <div v-if="rlhfImprovementList.length === 0" class="py-8">
              <Empty description="暂无改进点数据" />
            </div>
            <div v-else class="rlhf-improvement-list">
              <div
                v-for="item in rlhfImprovementList"
                :key="`${item.feedback_id}-${item.create_time}`"
                class="rlhf-improvement-item"
              >
                <div class="improvement-header">
                  <span class="improvement-user">{{
                    item.user_name || '未知用户'
                  }}</span>
                  <span class="improvement-time">{{
                    item.create_time || '-'
                  }}</span>
                </div>
                <div class="improvement-content">
                  <div class="improvement-selected-text">
                    {{ item.selected_text || '-' }}
                  </div>
                  <div class="improvement-comment">
                    {{ item.comment || '-' }}
                  </div>
                </div>
              </div>
            </div>
          </Skeleton>
        </Card>

        <!-- 抽检详情表格 -->
        <Card :bordered="false" class="rlhf-detail-card mt-4" title="抽检详情">
          <Skeleton :loading="loading" active :paragraph="{ rows: 8 }">
            <div class="table-scroll-container">
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
                  <Empty description="暂无抽检数据" />
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
          <div class="table-scroll-container">
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

@keyframes data-flow-rotate {
  from {
    transform: translate(-50%, -50%) rotate(0deg);
  }

  to {
    transform: translate(-50%, -50%) rotate(360deg);
  }
}

@keyframes scatter-glow-slide {
  0%,
  100% {
    opacity: 0.6;
  }

  50% {
    opacity: 1;
  }
}

@keyframes scatter-orb-pulse {
  0%,
  100% {
    opacity: 0.3;
    transform: scale(1);
  }

  50% {
    opacity: 0.5;
    transform: scale(1.15);
  }
}

@keyframes scatter-indicator-pulse {
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

@keyframes scatter-loading-pulse {
  0%,
  100% {
    opacity: 0.5;
  }

  50% {
    opacity: 1;
  }
}

@keyframes scatter-scan {
  0% {
    top: 0;
    opacity: 0;
  }

  10% {
    opacity: 0.7;
  }

  90% {
    opacity: 0.7;
  }

  100% {
    top: 100%;
    opacity: 0;
  }
}

@keyframes scatter-particle-float {
  0% {
    bottom: -10px;
    opacity: 0;
    transform: translateX(0) scale(0.5);
  }

  10% {
    opacity: 0.8;
    transform: scale(1);
  }

  50% {
    transform: translateX(20px) scale(1.2);
  }

  90% {
    opacity: 0.8;
  }

  100% {
    bottom: 100%;
    opacity: 0;
    transform: translateX(-10px) scale(0.5);
  }
}

@keyframes scatter-border-flow-horizontal {
  0% {
    left: -100%;
  }

  100% {
    left: 100%;
  }
}

@keyframes scatter-border-flow-horizontal-reverse {
  0% {
    right: -100%;
  }

  100% {
    right: 100%;
  }
}

@keyframes scatter-border-flow-vertical {
  0% {
    top: -100%;
  }

  100% {
    top: 100%;
  }
}

@keyframes scatter-border-flow-vertical-reverse {
  0% {
    bottom: -100%;
  }

  100% {
    bottom: 100%;
  }
}

@keyframes scatter-corner-pulse {
  0%,
  100% {
    box-shadow: 0 0 8px hsl(var(--primary));
    opacity: 0.6;
  }

  50% {
    box-shadow:
      0 0 15px hsl(var(--primary)),
      0 0 25px hsl(var(--primary) / 50%);
    opacity: 1;
  }
}

@keyframes scatter-live-blink {
  0%,
  100% {
    box-shadow:
      0 0 8px #10b981,
      0 0 15px #10b981;
    opacity: 1;
  }

  50% {
    box-shadow: 0 0 4px #10b981;
    opacity: 0.4;
  }
}

@keyframes heatmap-float {
  0%,
  100% {
    transform: translate(0, 0);
  }

  50% {
    transform: translate(30px, 20px);
  }
}

@keyframes heatmap-scan {
  0% {
    top: 0%;
    opacity: 0;
  }

  10% {
    opacity: 0.8;
  }

  90% {
    opacity: 0.8;
  }

  100% {
    top: 100%;
    opacity: 0;
  }
}

@keyframes icon-pulse {
  0% {
    opacity: 0.6;
    transform: scale(0.95);
  }

  50% {
    opacity: 1;
    transform: scale(1.05);
  }

  100% {
    opacity: 0.6;
    transform: scale(0.95);
  }
}

@keyframes status-blink {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.4;
  }
}

@keyframes spinner-rotate {
  0% {
    transform: rotate(0deg);
  }

  100% {
    transform: rotate(360deg);
  }
}

@keyframes security-orb-pulse {
  0%,
  100% {
    opacity: 0.25;
    transform: scale(1);
  }

  50% {
    opacity: 0.4;
    transform: scale(1.2);
  }
}

@keyframes security-border-h {
  0% {
    left: -100%;
  }

  100% {
    left: 100%;
  }
}

@keyframes security-border-h-rev {
  0% {
    right: -100%;
  }

  100% {
    right: 100%;
  }
}

@keyframes security-border-v {
  0% {
    top: -100%;
  }

  100% {
    top: 100%;
  }
}

@keyframes security-border-v-rev {
  0% {
    bottom: -100%;
  }

  100% {
    bottom: 100%;
  }
}

@keyframes security-corner-pulse {
  0%,
  100% {
    opacity: 0.6;
  }

  50% {
    opacity: 1;
  }
}

@keyframes security-indicator-pulse {
  0%,
  100% {
    box-shadow: 0 0 10px currentcolor;
  }

  50% {
    box-shadow:
      0 0 20px currentcolor,
      0 0 30px currentcolor;
  }
}

@keyframes status-blink {
  0%,
  100% {
    box-shadow:
      0 0 10px #10b981,
      0 0 20px #10b981;
    opacity: 1;
  }

  50% {
    box-shadow: 0 0 5px #10b981;
    opacity: 0.5;
  }
}

@keyframes border-flow-horizontal {
  0% {
    left: -100%;
  }

  100% {
    left: 100%;
  }
}

@keyframes border-flow-horizontal-reverse {
  0% {
    right: -100%;
  }

  100% {
    right: 100%;
  }
}

@keyframes border-flow-vertical {
  0% {
    top: -100%;
  }

  100% {
    top: 100%;
  }
}

@keyframes border-flow-vertical-reverse {
  0% {
    bottom: -100%;
  }

  100% {
    bottom: 100%;
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

@media (max-width: 1024px) {
  .quality-charts-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 1200px) {
  .governance-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 1200px) {
  .detail-content {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 1400px) {
  .critic-expert-grid-cool {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .critic-expert-grid-cool {
    grid-template-columns: 1fr;
  }
}

/* 大屏幕适配 - 扩展各区域尺寸 */
@media (min-width: 1600px) {
  .scoring-flow-visualization {
    gap: 1rem;
  }

  .flow-article-pool {
    flex: 0 0 140px;
  }

  .flow-connection-svg {
    flex: 0 0 120px;
  }

  .flow-experts-column {
    flex: 0 0 240px;
  }

  .flow-connection-svg-right {
    flex: 0 0 90px;
  }

  .flow-score-distribution {
    min-width: 240px;
    max-width: 320px;
  }

  .flow-radar-section {
    min-width: 360px;
    max-width: 600px;
  }
}

@media (min-width: 1920px) {
  .scoring-flow-visualization {
    gap: 1.5rem;
  }

  .flow-article-pool {
    flex: 0 0 160px;
  }

  .flow-connection-svg {
    flex: 0 0 140px;
  }

  .flow-experts-column {
    flex: 0 0 260px;
  }

  .flow-connection-svg-right {
    flex: 0 0 100px;
  }

  .flow-score-distribution {
    min-width: 280px;
    max-width: 360px;
  }

  .flow-radar-section {
    min-width: 400px;
    max-width: 700px;
  }
}

/* 响应式适配 */
@media (max-width: 1400px) {
  @keyframes arrow-move-down {
    0%,
    100% {
      transform: rotate(90deg) translateX(0);
    }

    50% {
      transform: rotate(90deg) translateX(8px);
    }
  }

  .scoring-flow-visualization {
    flex-wrap: wrap;
    gap: 1rem;
    justify-content: center;
  }

  .flow-connection-svg,
  .flow-connection-svg-right {
    display: none;
  }

  .flow-article-pool,
  .flow-experts-column,
  .flow-score-distribution {
    flex: 0 0 auto;
  }

  .flow-arrow-to-radar {
    animation: arrow-move-down 1.2s ease-in-out infinite;
  }

  .flow-radar-section {
    width: 100%;
    max-width: 100%;
  }
}

@media (max-width: 768px) {
  .scoring-flow-visualization {
    flex-direction: column;
  }

  .flow-experts-column {
    width: 100%;
  }

  .flow-score-distribution {
    width: 100%;
  }
}

@media (max-width: 1024px) {
  .security-platform-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .security-platform-grid {
    grid-template-columns: 1fr;
  }

  .security-expert-header-bar {
    flex-direction: column;
    gap: 1rem;
    align-items: flex-start;
  }

  .security-expert-header-right {
    flex-wrap: wrap;
  }
}

/* 响应式：小屏幕时按钮组独占一行 */
@media (max-width: 1200px) {
  .filter-actions {
    width: 100%;
    margin-left: 0;
  }
}

/* 减少重绘：为动画元素启用 GPU 加速 */
.section-glow-border,
.section-glow-orb,
.section-corner,
.security-border-glow .border-line,
.security-corner,
.security-glow-orb,
.heatmap-corner,
.loading-spinner .spinner-ring,
.security-title-indicator,
.status-dot {
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

/* 表格滚动容器样式 */
.table-scroll-container {
  position: relative;
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

  /* 为锚点定位预留顶部粘性筛选栏的空间 */
  scroll-margin-top: 120px;
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

.cost-detail-card .table-scroll-container {
  flex: 1;
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

/* ==================== 多维度AI评论专家组样式 ==================== */

/* 新版顶部栏样式 - 炫酷版 */
.critic-header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 0;
  margin-bottom: 0.75rem;
}

.critic-header-left {
  display: flex;
  align-items: center;
}

.expert-group-btn {
  height: 36px;
  padding: 0 1.25rem;
  font-size: 0.8125rem;
  font-weight: 600;
  border-radius: 18px;
  box-shadow: 0 4px 12px hsl(var(--primary) / 25%);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.expert-group-btn:hover {
  box-shadow: 0 6px 16px hsl(var(--primary) / 35%);
  transform: translateY(-1px);
}

.critic-header-right {
  display: flex;
  gap: 0.75rem;
}

.critic-summary-box {
  position: relative;
  display: flex;
  gap: 0.5rem;
  align-items: center;
  padding: 0.5rem 1rem;
  overflow: hidden;
  background: linear-gradient(
    135deg,
    hsl(var(--card)) 0%,
    hsl(var(--muted) / 30%) 100%
  );
  border: 1px solid hsl(var(--border) / 60%);
  border-radius: 10px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.critic-summary-box::before {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 2px;
  content: '';
  background: linear-gradient(90deg, hsl(var(--primary) / 40%), transparent);
  opacity: 0;
  transition: opacity 0.3s ease;
}

.critic-summary-box:hover {
  border-color: hsl(var(--primary) / 30%);
  box-shadow: 0 4px 12px hsl(var(--foreground) / 8%);
  transform: translateY(-2px);
}

.critic-summary-box:hover::before {
  opacity: 1;
}

.critic-summary-box .summary-label {
  font-size: 0.8125rem;
  color: hsl(var(--muted-foreground));
}

.critic-summary-box .summary-value {
  font-size: 1rem;
  font-weight: 700;
  color: hsl(var(--foreground));
  transition: transform 0.2s ease;
}

.critic-summary-box:hover .summary-value {
  transform: scale(1.05);
}

.critic-summary-box-danger {
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  border-color: #fecaca;
}

.critic-summary-box-danger::before {
  background: linear-gradient(90deg, #ef4444, transparent);
}

.critic-summary-box-danger .summary-value {
  color: #ef4444;
}

/* 旧版顶部栏样式（保留用于兼容） */
.critic-stats-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 2rem;
  padding: 1rem 1.5rem;
  margin-bottom: 1.5rem;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.critic-stat-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.critic-stat-item .stat-label {
  font-size: 0.875rem;
  color: hsl(var(--muted-foreground));
}

.critic-stat-item .stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: hsl(var(--foreground));
}

.critic-expert-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
}

/* ==================== Critic 专家组卡片 - 炫酷版 ==================== */
.critic-expert-grid-cool {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1.25rem;
}

.critic-card-cool {
  position: relative;
  padding: 0;
  overflow: hidden;
  background: hsl(var(--card) / 50%);
  border: 1px solid hsl(var(--border) / 30%);
  border-radius: 14px;
  box-shadow: 0 10px 30px hsl(var(--background) / 25%);
  backdrop-filter: blur(16px);
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.critic-card-cool:hover {
  box-shadow: 0 20px 40px hsl(var(--background) / 35%);
  transform: translateY(-6px) scale(1.02);
}

/* 背景装饰 */
.critic-card-cool .critic-card-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
}

.critic-card-cool .critic-glow-orb {
  position: absolute;
  top: -40px;
  right: -40px;
  width: 150px;
  height: 150px;
  border-radius: 50%;
  opacity: 0.3;
  filter: blur(50px);
  animation: critic-orb-pulse 5s ease-in-out infinite;
}

.illegal-theme .critic-glow-orb {
  background: #ef4444;
}

.irregular-theme .critic-glow-orb {
  background: #f97316;
}

.unreasonable-theme .critic-glow-orb {
  background: #f59e0b;
}

.counterproductive-theme .critic-glow-orb {
  background: #d946ef;
}

.brand-theme .critic-glow-orb {
  background: #3b82f6;
}

/* 脉冲环 */
.critic-card-cool .critic-pulse-ring {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 80px;
  height: 80px;
  border: 2px solid;
  border-radius: 50%;
  opacity: 0;
  transform: translate(-50%, -50%);
  animation: critic-pulse-expand 3s ease-out infinite;
}

.illegal-theme .critic-pulse-ring {
  border-color: #ef4444;
}

.irregular-theme .critic-pulse-ring {
  border-color: #f97316;
}

.unreasonable-theme .critic-pulse-ring {
  border-color: #f59e0b;
}

.counterproductive-theme .critic-pulse-ring {
  border-color: #d946ef;
}

.brand-theme .critic-pulse-ring {
  border-color: #3b82f6;
}

/* 顶部边框流光 */
.critic-card-cool .critic-border-glow {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  z-index: 2;
  height: 2px;
  overflow: hidden;
}

.critic-card-cool .critic-border-glow::after {
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  content: '';
  animation: critic-border-slide 3s linear infinite;
}

.illegal-theme .critic-border-glow::after {
  background: linear-gradient(90deg, transparent, #ef4444, transparent);
}

.irregular-theme .critic-border-glow::after {
  background: linear-gradient(90deg, transparent, #f97316, transparent);
}

.unreasonable-theme .critic-border-glow::after {
  background: linear-gradient(90deg, transparent, #f59e0b, transparent);
}

.counterproductive-theme .critic-border-glow::after {
  background: linear-gradient(90deg, transparent, #d946ef, transparent);
}

.brand-theme .critic-border-glow::after {
  background: linear-gradient(90deg, transparent, #3b82f6, transparent);
}

/* 卡片内容 */
.critic-card-cool .critic-card-content {
  position: relative;
  z-index: 5;
  padding: 1.25rem;
}

.critic-card-cool .critic-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.critic-card-cool .critic-title-group {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.critic-card-cool .critic-icon {
  font-size: 1.25rem;
  animation: critic-icon-bounce 2s ease-in-out infinite;
}

.critic-card-cool .critic-title {
  font-size: 1rem;
  font-weight: 700;
}

.illegal-theme .critic-title {
  color: #ef4444;
  text-shadow: 0 0 10px rgb(239 68 68 / 50%);
}

.irregular-theme .critic-title {
  color: #f97316;
  text-shadow: 0 0 10px rgb(249 115 22 / 50%);
}

.unreasonable-theme .critic-title {
  color: #f59e0b;
  text-shadow: 0 0 10px rgb(245 158 11 / 50%);
}

.counterproductive-theme .critic-title {
  color: #d946ef;
  text-shadow: 0 0 10px rgb(217 70 239 / 50%);
}

.brand-theme .critic-title {
  color: #3b82f6;
  text-shadow: 0 0 10px rgb(59 130 246 / 50%);
}

.critic-card-cool .critic-help-icon {
  color: hsl(var(--muted-foreground));
  cursor: help;
  transition: color 0.2s;
}

.critic-card-cool:hover .critic-help-icon {
  color: hsl(var(--foreground));
}

/* 统计数据 */
.critic-card-cool .critic-stats {
  display: flex;
  gap: 1rem;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.critic-card-cool .critic-stat-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.critic-card-cool .critic-stat-label {
  font-size: 0.75rem;
  color: hsl(var(--muted-foreground));
}

.critic-card-cool .critic-stat-value {
  display: inline-block;
  min-width: 80px;
  font-size: 1.5rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: hsl(var(--foreground));
  text-align: right;
}

.critic-card-cool .critic-stat-item.reject .critic-stat-value {
  color: #ef4444;
  text-shadow: 0 0 8px rgb(239 68 68 / 40%);
}

/* 进度条 */
.critic-card-cool .critic-progress {
  height: 4px;
  overflow: hidden;
  background: hsl(var(--muted) / 30%);
  border-radius: 2px;
}

.critic-card-cool .critic-progress .progress-bar {
  height: 100%;
  border-radius: 2px;
  transition: width 1s ease-out;
  animation: critic-progress-glow 2s ease-in-out infinite;
}

.illegal-theme .progress-bar {
  background: linear-gradient(90deg, #ef4444, #f87171);
  box-shadow: 0 0 10px #ef4444;
}

.irregular-theme .progress-bar {
  background: linear-gradient(90deg, #f97316, #fb923c);
  box-shadow: 0 0 10px #f97316;
}

.unreasonable-theme .progress-bar {
  background: linear-gradient(90deg, #f59e0b, #fbbf24);
  box-shadow: 0 0 10px #f59e0b;
}

.counterproductive-theme .progress-bar {
  background: linear-gradient(90deg, #d946ef, #e879f9);
  box-shadow: 0 0 10px #d946ef;
}

.brand-theme .progress-bar {
  background: linear-gradient(90deg, #3b82f6, #60a5fa);
  box-shadow: 0 0 10px #3b82f6;
}

/* 悬停增强 */
.critic-card-cool:hover .critic-glow-orb {
  opacity: 0.5;
  animation-duration: 2.5s;
}

.critic-card-cool:hover .critic-border-glow::after {
  animation-duration: 1.5s;
}

/* 旧版卡片样式（保留用于兼容） */
.critic-expert-card {
  min-height: 280px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.expert-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 0.75rem;
  margin-bottom: 1rem;
  border-bottom: 1px solid hsl(var(--border));
}

.expert-title {
  font-size: 1.25rem;
  font-weight: 700;
}

.threshold-tag {
  font-size: 0.75rem;
}

.expert-stats {
  margin-bottom: 1rem;
}

.expert-stat-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 0.5rem 0;
}

.expert-stat-row .stat-label {
  font-size: 0.875rem;
  color: hsl(var(--muted-foreground));
}

.expert-stat-row .stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: hsl(var(--foreground));
}

.expert-reason {
  padding-top: 0.75rem;
  border-top: 1px solid hsl(var(--border));
}

.reason-title {
  margin-bottom: 0.5rem;
  font-size: 0.875rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.reason-placeholder {
  padding: 1rem;
  font-size: 0.875rem;
  color: hsl(var(--muted-foreground));
  text-align: center;
  background: hsl(var(--muted) / 50%);
  border-radius: 4px;
}

/* 新版简化卡片样式 - 炫酷版 */
.critic-expert-card-simple {
  position: relative;
  padding: 1rem;
  overflow: hidden;
  background: linear-gradient(
    145deg,
    hsl(var(--card)) 0%,
    hsl(var(--muted) / 20%) 100%
  );
  border: 1px solid hsl(var(--border) / 60%);
  border-radius: 12px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.critic-expert-card-simple::after {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 2px;
  content: '';
  background: linear-gradient(
    90deg,
    transparent,
    hsl(var(--primary) / 40%),
    transparent
  );
  opacity: 0;
  transition: opacity 0.3s ease;
}

.critic-expert-card-simple:hover {
  border-color: hsl(var(--primary) / 30%);
  box-shadow: 0 8px 20px hsl(var(--foreground) / 8%);
  transform: translateY(-3px);
}

.critic-expert-card-simple:hover::after {
  opacity: 1;
}

.expert-header-simple {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 0.5rem;
  margin-bottom: 0.75rem;
  border-bottom: 1px solid hsl(var(--border) / 50%);
}

.expert-stats-simple {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.expert-stat-row-simple {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.expert-stat-row-simple .stat-label {
  font-size: 0.8125rem;
  color: hsl(var(--muted-foreground));
}

.expert-stat-row-simple .stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: hsl(var(--foreground));
  transition: transform 0.2s ease;
}

.critic-expert-card-simple:hover .expert-stat-row-simple .stat-value {
  transform: scale(1.02);
}

.text-red-500 {
  color: #ef4444 !important;
}

/* 六维图 & 技术可用性布局 */
.quality-charts-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.5rem;
  margin-top: 1.5rem;
}

.quality-chart-card {
  padding: 1rem;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

/* 治理中心样式 */
.governance-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.5rem;
}

.governance-card {
  padding: 1.5rem;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.governance-card-title {
  margin-bottom: 0.5rem;
  font-size: 1rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.governance-card-subtitle {
  margin-bottom: 0.5rem;
  font-size: 0.75rem;
  color: hsl(var(--muted-foreground));
}

.governance-stats {
  margin-bottom: 1rem;
}

.governance-stat-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 0;
}

.governance-stat-row .stat-label {
  font-size: 0.875rem;
  color: hsl(var(--muted-foreground));
}

.governance-stat-row .stat-value {
  font-size: 1.5rem;
  font-weight: 700;
}

/* 人设多样性居中样式 */
.governance-stats-centered {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  align-items: center;
  margin-bottom: 1rem;
}

.governance-stat-item-centered {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  align-items: center;
}

.governance-stat-item-centered .stat-label {
  font-size: 0.875rem;
  color: hsl(var(--muted-foreground));
}

.stat-value-large {
  font-size: 2rem;
  font-weight: 700;
}

/* 人设多样性行布局（参考图2） */
.persona-stats-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 0;
}

.persona-stats-row .stat-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.persona-stats-row .stat-value-large {
  font-size: 1.75rem;
  font-weight: 700;
  color: hsl(var(--foreground));
}

/* Agent详情面板样式 */
.agent-detail-panel {
  padding: 1rem;
  background: hsl(var(--muted) / 30%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 0.5rem;
  margin-bottom: 1rem;
  border-bottom: 1px solid hsl(var(--border));
}

.detail-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.detail-content {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.75rem;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.5rem;
  background: hsl(var(--background));
  border-radius: 4px;
}

.detail-item-highlight {
  background: hsl(var(--primary) / 10%);
}

.detail-label {
  font-size: 0.75rem;
  color: hsl(var(--muted-foreground));
}

.detail-value {
  font-size: 1rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

/* ==================== RLHF 人工专家反馈报告样式 ==================== */

/* 顶部两个大数据卡片 - 炫酷版 */
.rlhf-top-stats {
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
}

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

.big-stat-label {
  font-size: 0.875rem;
  color: hsl(var(--muted-foreground));
  letter-spacing: 0.02em;
}

.big-stat-value-row {
  display: flex;
  gap: 0.5rem;
  align-items: baseline;
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

.big-stat-unit {
  font-size: 0.875rem;
  color: hsl(var(--muted-foreground));
}

/* 小节标题 */
.rlhf-section-subtitle {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin: 1.5rem 0 0.75rem;
  font-size: 1rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.info-icon {
  font-size: 14px;
  color: hsl(var(--muted-foreground));
  cursor: pointer;
  transition: color 0.2s;
}

.info-icon:hover {
  color: hsl(var(--primary));
}

.dimension-tooltip {
  max-width: 320px;
}

.dimension-tooltip .tooltip-item {
  margin-bottom: 8px;
  line-height: 1.5;
}

.dimension-tooltip .tooltip-item:last-child {
  margin-bottom: 0;
}

/* 正负向反馈标签 - 炫酷版 */
.rlhf-feedback-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.rlhf-feedback-tags > .rlhf-feedback-tag-item {
  flex: 1;
}

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

.rlhf-feedback-tag-item .tag-name {
  padding: 0.2rem 0.5rem;
  font-size: 0.875rem;
  font-weight: 600;
  border-radius: 6px;
  transition: transform 0.2s ease;
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

.rlhf-feedback-tag-item .tag-count {
  font-size: 0.875rem;
  font-weight: 700;
  color: hsl(var(--foreground));
}

.rlhf-feedback-tag-item .tag-percent {
  font-size: 0.6875rem;
  color: hsl(var(--muted-foreground));
}

/* 喜欢采纳反馈 - 炫酷版 */
.rlhf-like-feedback-bar {
  display: flex;
  gap: 1rem;
}

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

.like-feedback-row {
  display: flex;
  gap: 0.5rem;
  align-items: baseline;
}

.like-feedback-label {
  font-size: 0.875rem;
  color: hsl(var(--muted-foreground));
}

.like-feedback-value {
  font-size: 1.75rem;
  font-weight: 800;
  color: hsl(var(--foreground));
  transition: transform 0.2s ease;
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

.chart-card-title {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  padding-bottom: 0.5rem;
  margin-bottom: 0.5rem;
  font-size: 0.9375rem;
  font-weight: 600;
  color: hsl(var(--foreground));
  border-bottom: 1px solid hsl(var(--border) / 40%);
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

/* RLHF 改进点摘要样式 */
.rlhf-improvement-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-height: 500px;
  overflow-y: auto;
}

.rlhf-improvement-item {
  padding: 1rem;
  background: hsl(var(--muted) / 30%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.improvement-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 0.5rem;
  margin-bottom: 0.75rem;
  border-bottom: 1px solid hsl(var(--border));
}

.improvement-user {
  padding: 0.25rem 0.5rem;
  font-size: 0.875rem;
  font-weight: 600;
  color: hsl(var(--foreground));
  background: hsl(var(--muted));
  border-radius: 4px;
}

.improvement-time {
  font-size: 0.75rem;
  color: hsl(var(--muted-foreground));
}

.improvement-content {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.improvement-selected-text {
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  line-height: 1.6;
  color: hsl(var(--foreground));
  background: hsl(var(--background));
  border-left: 3px solid hsl(var(--primary));
  border-radius: 0 4px 4px 0;
}

.improvement-comment {
  font-size: 0.875rem;
  line-height: 1.6;
  color: hsl(var(--muted-foreground));
}

/* ==================== 评分类专家组样式 ==================== */
.scoring-expert-header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 0;
  margin-top: 1.5rem;
  margin-bottom: 1rem;
  border-top: 1px solid hsl(var(--border));
}

.scoring-expert-header-left {
  display: flex;
  align-items: center;
}

.scoring-expert-header-right {
  display: flex;
  gap: 1rem;
}

/* ==================== 专家组评分流程图 - 酷炫动画版样式 ==================== */
.scoring-flow-card {
  padding: 1.5rem;
  margin-top: 1rem;
  overflow: hidden;
  background: linear-gradient(
    145deg,
    hsl(var(--card)) 0%,
    hsl(var(--muted) / 30%) 100%
  );
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
}

/* 统一标题区域 - 与内容丰富度样式一致 */
.scoring-flow-header {
  padding-bottom: 1rem;
  margin-bottom: 1rem;
  border-bottom: 1px solid hsl(var(--border) / 20%);
}

.scoring-flow-title {
  display: flex;
  gap: 0.625rem;
  align-items: center;
  font-size: 1.15rem;
  font-weight: 700;
  color: hsl(var(--foreground));
  text-shadow: 0 0 20px hsl(var(--primary) / 40%);
}

.scoring-title-indicator {
  display: block;
  width: 4px;
  height: 1.25rem;
  background: hsl(var(--primary));
  border-radius: 2px;
  box-shadow: 0 0 12px hsl(var(--primary));
  animation: scoring-indicator-pulse 2s ease-in-out infinite;
}

.scoring-flow-title .info-icon {
  margin-left: 0.25rem;
  font-size: 0.85rem;
  color: hsl(var(--muted-foreground));
  cursor: help;
  transition: color 0.2s;
}

.scoring-flow-title .info-icon:hover {
  color: hsl(var(--primary));
}

/* Tooltip 分隔线和标题样式 */
.tooltip-section-title {
  margin-bottom: 0.5rem;
  font-size: 0.85rem;
  font-weight: 600;
  color: hsl(var(--primary));
}

.tooltip-divider {
  height: 1px;
  margin: 0.75rem 0;
  background: hsl(var(--border));
}

.scoring-flow-visualization {
  position: relative;
  display: flex;
  gap: 0;
  align-items: flex-start;
  justify-content: center;
  max-width: 1800px;
  min-height: 450px;
  padding: 1rem 0;
  margin: 0 auto;
}

/* 左侧区域容器 */
.flow-left-section {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  max-width: 800px;
}

.flow-left-title {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  height: 24px;
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.flow-left-content {
  display: flex;
  gap: 0;
  align-items: center;
  justify-content: center;
}

/* 左侧文章池 */
.flow-article-pool {
  position: relative;
  z-index: 10;
  display: flex;
  flex: 0 0 120px;
  align-items: center;
  justify-content: center;
  height: 360px; /* 与SVG高度一致 */
}

.pool-glow {
  position: absolute;
  inset: 80px -4px; /* 只包裹内容区域 */
  background: linear-gradient(135deg, #3b82f6 0%, #06b6d4 100%);
  border-radius: 16px;
  opacity: 0.2;
  filter: blur(10px);
  animation: pulse-glow 2.5s ease-in-out infinite;
}

.pool-content {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 180px;
  padding: 1rem;
  background: linear-gradient(
    145deg,
    hsl(var(--card)) 0%,
    hsl(var(--muted) / 40%) 100%
  );
  border: 2px solid hsl(var(--primary) / 50%);
  border-radius: 14px;
  box-shadow:
    0 4px 20px hsl(var(--primary) / 20%),
    inset 0 1px 0 hsl(var(--card));
}

.pool-icon {
  margin-bottom: 0.5rem;
  font-size: 2rem;
}

.pool-label {
  font-size: 0.75rem;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.pool-value {
  font-size: 1.5rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: hsl(var(--foreground));
}

.pool-status {
  display: flex;
  gap: 0.375rem;
  align-items: center;
  margin-top: 0.5rem;
}

.status-dot {
  width: 8px;
  height: 8px;
  background: #22c55e;
  border-radius: 50%;
  animation: ping 1.5s cubic-bezier(0, 0, 0.2, 1) infinite;
}

.status-text {
  font-size: 0.7rem;
  color: #22c55e;
}

/* SVG 连接线 */
.flow-connection-svg {
  flex: 0 0 100px;
  height: 360px; /* 与专家列表高度一致 */
  overflow: visible;
}

.flow-connection-svg-right {
  flex: 0 0 70px;
  height: 360px;
  overflow: visible;
}

.flow-line {
  filter: drop-shadow(0 0 2px currentcolor);
}

.flow-line-right {
  filter: drop-shadow(0 0 1.5px currentcolor);
}

/* 中间专家列 */
.flow-experts-column {
  z-index: 10;
  display: flex;
  flex: 0 0 200px;
  flex-direction: column;
  height: 360px; /* 与SVG viewBox高度一致 */
}

.experts-title {
  flex-shrink: 0;
  height: 0; /* 隐藏标题让专家节点完全占据360px */
  margin-bottom: 0;
  overflow: hidden;
  font-size: 0.75rem;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
  text-align: center;
  letter-spacing: 0.1em;
}

.experts-list {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  height: 100%;
  padding: 10px 0;
}

.expert-node {
  position: relative;
  display: flex;
  gap: 0.625rem;
  align-items: center;
  height: 48px;
  padding: 0.5rem 0.625rem;
  cursor: pointer;
  background: hsl(var(--card) / 95%);
  border: 2px solid hsl(var(--border) / 50%);
  border-radius: 8px;
  backdrop-filter: blur(8px);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.expert-node:hover {
  background: hsl(var(--muted) / 60%);
  border-color: var(--expert-color, hsl(var(--border)));
  box-shadow: 0 4px 12px hsl(var(--foreground) / 10%);
  transform: translateX(3px);
}

.expert-node.expert-active {
  background: var(--expert-bg, hsl(var(--muted) / 80%));
  border-color: var(--expert-color);
  border-width: 2px;
  box-shadow:
    0 0 0 4px var(--expert-bg),
    0 0 30px var(--expert-color),
    0 0 60px var(--expert-color),
    0 8px 25px hsl(var(--foreground) / 20%);
  transform: scale(1.05) translateX(2px);
  animation:
    expert-pulse 0.6s ease-out,
    expert-glow 1s ease-in-out infinite;
}

.expert-node.expert-processing {
  border-style: solid;
}

.expert-node.expert-processing::before {
  position: absolute;
  inset: -3px;
  content: '';
  background: linear-gradient(
    90deg,
    transparent,
    var(--expert-color),
    transparent
  );
  border-radius: 10px;
  opacity: 0.4;
  animation: shimmer 1.5s infinite;
}

/* 左侧连接锚点 */
.expert-anchor-left {
  position: absolute;
  top: 50%;
  left: -6px;
  width: 10px;
  height: 10px;
  border: 2px solid hsl(var(--card));
  border-radius: 50%;
  transform: translateY(-50%);
  transition: all 0.3s;
}

.expert-active .expert-anchor-left {
  box-shadow: 0 0 8px currentcolor;
  transform: translateY(-50%) scale(1.3);
}

.expert-icon {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  font-size: 1rem;
  border-radius: 6px;
  transition: all 0.3s;
}

.expert-active .expert-icon {
  transform: scale(1.1);
  animation: icon-bounce 0.5s ease-out;
}

.expert-info {
  flex: 1;
  min-width: 0;
}

.expert-name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 0.8rem;
  font-weight: 600;
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.expert-status {
  height: 1rem;
  margin-top: 1px;
  font-size: 0.7rem;
}

.status-active {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  font-weight: 600;
  text-shadow: 0 0 8px currentcolor;
  animation: status-pulse 0.6s ease-in-out infinite;
}

.status-dot-active {
  width: 6px;
  height: 6px;
  background-color: currentcolor;
  border-radius: 50%;
  box-shadow: 0 0 6px currentcolor;
  animation: dot-ping 1s ease-in-out infinite;
}

.status-idle {
  color: hsl(var(--muted-foreground));
  transition: all 0.3s ease;
}

.expert-help {
  flex-shrink: 0;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  cursor: help;
  opacity: 0.5;
  transition: opacity 0.2s;
}

.expert-node:hover .expert-help {
  opacity: 1;
}

/* 右侧连接锚点 */
.expert-anchor-right {
  position: absolute;
  top: 50%;
  right: -6px;
  width: 10px;
  height: 10px;
  border: 2px solid hsl(var(--card));
  border-radius: 50%;
  transform: translateY(-50%);
  transition: all 0.3s;
}

.expert-active .expert-anchor-right {
  box-shadow: 0 0 8px currentcolor;
  transform: translateY(-50%) scale(1.3);
}

/* 右侧评分分布 */
.flow-score-distribution {
  z-index: 10;
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  min-width: 200px;
  max-width: 280px;
  height: 360px; /* 与SVG高度一致 */
  padding: 0.75rem;
  background: linear-gradient(
    135deg,
    hsl(var(--card)) 0%,
    hsl(var(--muted) / 25%) 100%
  );
  border: 1.5px solid hsl(var(--border) / 60%);
  border-radius: 12px;
  box-shadow:
    0 2px 8px hsl(var(--foreground) / 5%),
    0 1px 2px hsl(var(--foreground) / 3%);
}

.distribution-title {
  flex-shrink: 0;
  margin-bottom: 0.5rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
  text-align: center;
  letter-spacing: 0.05em;
}

.distribution-count {
  font-weight: 600;
  color: hsl(var(--foreground));
}

.distribution-bars {
  display: flex;
  flex: 1;
  flex-direction: column;
  justify-content: space-between;
  padding: 8px 0;
}

.score-bar-row {
  position: relative;
  display: flex;
  gap: 0.5rem;
  align-items: center;
  height: 56px; /* 固定高度确保均匀分布 */
}

/* 左侧连接锚点 */
.bucket-anchor-left {
  position: absolute;
  top: 50%;
  left: -8px;
  width: 8px;
  height: 8px;
  background: hsl(var(--muted-foreground) / 30%);
  border: 1px solid hsl(var(--card));
  border-radius: 50%;
  transform: translateY(-50%);
}

.score-label-left {
  flex: 0 0 55px;
  font-family: ui-monospace, monospace;
  font-size: 0.7rem;
  color: hsl(var(--muted-foreground));
  text-align: right;
}

.score-bar-track {
  flex: 1;
  height: 32px;
  overflow: visible; /* 允许 Tooltip 显示 */
  background: hsl(var(--muted) / 35%);
  border-radius: 6px;
}

/* 六色条带轨道 */
.rainbow-track {
  position: relative;
  display: flex;
  align-items: center;
}

.rainbow-bar-container {
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
  border-radius: 6px;
}

/* 六色条带中的每一段 */
.rainbow-segment {
  position: relative;
  min-width: 2px;
  height: 100%;
  transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
  animation: segment-twinkle 3s ease-in-out infinite;
}

/* 段内发光效果 */
.segment-glow {
  position: absolute;
  inset: 0;
  opacity: 0;
  filter: blur(4px);
  animation: glow-flash 2.5s ease-in-out infinite;
}

/* 随机闪烁动画 - 为每个段设置不同的动画延迟 */
.rainbow-segment-1 {
  animation-delay: 0s;
}

.rainbow-segment-1 .segment-glow {
  animation-delay: 0.2s;
}

.rainbow-segment-2 {
  animation-delay: 0.4s;
}

.rainbow-segment-2 .segment-glow {
  animation-delay: 0.8s;
}

.rainbow-segment-3 {
  animation-delay: 0.8s;
}

.rainbow-segment-3 .segment-glow {
  animation-delay: 1.3s;
}

.rainbow-segment-4 {
  animation-delay: 1.2s;
}

.rainbow-segment-4 .segment-glow {
  animation-delay: 0.5s;
}

.rainbow-segment-5 {
  animation-delay: 1.6s;
}

.rainbow-segment-5 .segment-glow {
  animation-delay: 1.8s;
}

.rainbow-segment-6 {
  animation-delay: 2s;
}

.rainbow-segment-6 .segment-glow {
  animation-delay: 1s;
}

/* 悬停时增强效果 */
.score-bar-row:hover .rainbow-segment {
  animation-duration: 1s;
}

.score-bar-row:hover .segment-glow {
  animation-duration: 0.8s;
}

/* 颜色段 Tooltip 样式 */
.segment-tooltip {
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 12px;
  white-space: nowrap;
}

.segment-tooltip .tooltip-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.segment-tooltip .tooltip-percent {
  margin-left: 4px;
  font-weight: 700;
}

/* 六色图例 */
.rainbow-legend {
  display: flex;
  gap: 6px;
  justify-content: center;
  padding-top: 4px;
  margin-top: 4px;
}

.legend-dot-item {
  display: flex;
  align-items: center;
}

.legend-color-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  animation: legend-dot-pulse 2s ease-in-out infinite;
}

.legend-dot-item:nth-child(1) .legend-color-dot {
  animation-delay: 0s;
}

.legend-dot-item:nth-child(2) .legend-color-dot {
  animation-delay: 0.33s;
}

.legend-dot-item:nth-child(3) .legend-color-dot {
  animation-delay: 0.66s;
}

.legend-dot-item:nth-child(4) .legend-color-dot {
  animation-delay: 1s;
}

.legend-dot-item:nth-child(5) .legend-color-dot {
  animation-delay: 1.33s;
}

.legend-dot-item:nth-child(6) .legend-color-dot {
  animation-delay: 1.66s;
}

.score-bar-fill {
  display: flex;
  align-items: center;
  min-width: 20px;
  height: 100%;
  padding-left: 0.625rem;
  border-radius: 6px;
  transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}

.bar-value {
  font-size: 0.8rem;
  font-weight: 700;
  color: #fff;
  text-shadow: 0 1px 3px rgb(0 0 0 / 40%);
}

/* 分数区间颜色 */
.score-range-excellent {
  background: linear-gradient(90deg, #22c55e 0%, #16a34a 100%);
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 20%);
}

.score-range-good {
  background: linear-gradient(90deg, #34d399 0%, #10b981 100%);
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 20%);
}

.score-range-medium {
  background: linear-gradient(90deg, #facc15 0%, #eab308 100%);
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 20%);
}

.score-range-low {
  background: linear-gradient(90deg, #fb923c 0%, #f97316 100%);
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 20%);
}

.score-range-poor {
  background: linear-gradient(90deg, #f87171 0%, #ef4444 100%);
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 20%);
}

.distribution-legend {
  display: flex;
  flex-shrink: 0;
  justify-content: space-between;
  padding: 0 0.375rem;
  margin-top: 0.5rem;
  font-size: 0.625rem;
  color: hsl(var(--muted-foreground) / 50%);
}

/* 箭头指向雷达图 */
.flow-arrow-to-radar {
  z-index: 10;
  display: flex;
  flex: 0 0 50px;
  align-items: center;
  justify-content: center;
  height: 380px;
  margin-left: 25px;
  animation: arrow-move-right 1.2s ease-in-out infinite;
}

/* 雷达图区域 */
.flow-radar-section {
  z-index: 10;
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-width: 350px;
  max-width: 550px;
  overflow: visible; /* 允许标签显示在外面 */
}

.radar-title {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.radar-highlight-indicator {
  display: flex;
  justify-content: center;
  margin-bottom: 0.5rem;
}

.highlight-badge {
  display: inline-flex;
  gap: 0.375rem;
  align-items: center;
  padding: 0.375rem 0.75rem;
  font-size: 0.75rem;
  font-weight: 500;
  border: 1px solid;
  border-radius: 20px;
  animation: fade-in-scale 0.3s ease-out;
}

.radar-chart-container {
  position: relative;
  z-index: 10; /* 高于标签(5)，tooltip会显示在标签上面 */
  flex: 1;
  min-height: 380px;
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

/* 内部数据流动光效 - 沿着雷达图边缘 */
.radar-chart-wrapper::before {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 3;
  width: 220px;
  height: 220px;
  pointer-events: none;
  content: '';
  background: conic-gradient(
    from 0deg,
    transparent 0deg,
    rgb(102 126 234 / 30%) 60deg,
    transparent 120deg
  );
  border-radius: 50%;
  opacity: 0.5;
  transform: translate(-50%, -50%);
  animation: data-flow-rotate 6s linear infinite;
}

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

/* 底部图例 */
.flow-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
  justify-content: center;
  padding-top: 1rem;
  margin-top: 1.5rem;
  border-top: 1px solid hsl(var(--border) / 40%);
}

.legend-item {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.legend-line {
  width: 24px;
  height: 2px;
  border-top: 2px dashed hsl(var(--muted-foreground) / 50%);
}

.legend-text {
  font-size: 0.75rem;
  color: hsl(var(--muted-foreground));
}

/* ==================== 统计学专家组样式 ==================== */
.statistics-expert-header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 0;
  margin-top: 1.5rem;
  margin-bottom: 1rem;
  border-top: 1px solid hsl(var(--border));
}

.statistics-expert-header-left {
  display: flex;
  align-items: center;
}

.statistics-expert-header-right {
  display: flex;
  gap: 1rem;
}

.statistics-expert-card {
  padding: 1.5rem;
  margin-top: 1rem;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.statistics-card-title {
  padding-bottom: 0.5rem;
  margin-bottom: 1rem;
  font-size: 1.125rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

/* ==================== 内容丰富度散点图 - 炫酷版样式 ==================== */
.scatter-cool-card {
  position: relative;
  padding: 0;
  margin-top: 1rem;
  overflow: hidden;
  background: hsl(var(--card) / 50%);
  border: 1px solid hsl(var(--border) / 30%);
  border-radius: 16px;
  box-shadow:
    0 0 0 1px hsl(var(--foreground) / 5%),
    0 25px 60px hsl(var(--background) / 40%);
  backdrop-filter: blur(24px);
  transition: all 0.4s ease;
}

.scatter-cool-card:hover {
  box-shadow:
    0 0 0 1px hsl(var(--primary) / 20%),
    0 30px 70px hsl(var(--background) / 50%);
}

/* 顶部流光边框 */
.scatter-top-glow {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  z-index: 10;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    hsl(var(--primary) / 60%) 25%,
    hsl(var(--primary)) 50%,
    hsl(var(--primary) / 60%) 75%,
    transparent 100%
  );
  animation: scatter-glow-slide 3s ease-in-out infinite;
}

/* 背景装饰层 */
.scatter-bg-decoration {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
}

.scatter-glow-orb {
  position: absolute;
  border-radius: 50%;
  opacity: 0.35;
  filter: blur(80px);
  animation: scatter-orb-pulse 8s ease-in-out infinite;
}

.scatter-glow-orb.orb-1 {
  top: -80px;
  left: -80px;
  width: 300px;
  height: 300px;
  background: #3b82f6;
  animation-delay: 0s;
}

.scatter-glow-orb.orb-2 {
  right: -100px;
  bottom: -100px;
  width: 350px;
  height: 350px;
  background: #8b5cf6;
  animation-delay: 4s;
}

.scatter-glow-orb.orb-3 {
  top: 45%;
  left: 45%;
  width: 200px;
  height: 200px;
  background: #06b6d4;
  opacity: 0.2;
  animation-delay: 2s;
}

.scatter-grid-lines {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(hsl(var(--primary) / 4%) 1px, transparent 1px),
    linear-gradient(90deg, hsl(var(--primary) / 4%) 1px, transparent 1px);
  background-size: 50px 50px;
  opacity: 0.4;
}

/* 标题栏 */
.scatter-card-header {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.25rem 1.5rem;
  background: linear-gradient(
    180deg,
    hsl(var(--card) / 60%) 0%,
    transparent 100%
  );
  border-bottom: 1px solid hsl(var(--border) / 20%);
}

.scatter-card-title {
  display: flex;
  gap: 0.625rem;
  align-items: center;
  font-size: 1.15rem;
  font-weight: 700;
  color: hsl(var(--foreground));
  text-shadow: 0 0 20px hsl(var(--primary) / 40%);
}

.scatter-title-indicator {
  display: block;
  width: 4px;
  height: 1.25rem;
  background: hsl(var(--primary));
  border-radius: 2px;
  box-shadow: 0 0 12px hsl(var(--primary));
  animation: scatter-indicator-pulse 2s ease-in-out infinite;
}

/* 图例 */
.scatter-legend {
  display: flex;
  gap: 1.25rem;
  font-size: 0.75rem;
  color: hsl(var(--muted-foreground));
}

.scatter-legend-item {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.scatter-legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

/* 图表容器 */
.scatter-chart-container {
  position: relative;
  z-index: 10;
  flex: 1;
  width: 100%;
  padding: 0.5rem 1rem 1rem;
}

/* 加载遮罩 */
.scatter-loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  background: hsl(var(--background) / 80%);
  backdrop-filter: blur(4px);
  transition: opacity 0.5s;
}

.scatter-loading-text {
  font-weight: 600;
  color: hsl(var(--primary));
  animation: scatter-loading-pulse 1.5s ease-in-out infinite;
}

/* 扫描线动画 */
.scatter-scan-line {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  z-index: 5;
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    hsl(var(--primary) / 30%) 20%,
    hsl(var(--primary)) 50%,
    hsl(var(--primary) / 30%) 80%,
    transparent 100%
  );
  box-shadow:
    0 0 15px hsl(var(--primary)),
    0 0 30px hsl(var(--primary) / 50%);
  opacity: 0.7;
  animation: scatter-scan 4s ease-in-out infinite;
}

/* 流动粒子 */
.scatter-particles {
  position: absolute;
  inset: 0;
  z-index: 3;
  overflow: hidden;
  pointer-events: none;
}

.particle {
  position: absolute;
  width: 4px;
  height: 4px;
  background: hsl(var(--primary));
  border-radius: 50%;
  box-shadow:
    0 0 10px hsl(var(--primary)),
    0 0 20px hsl(var(--primary) / 50%);
  opacity: 0;
  animation: scatter-particle-float 8s ease-in-out infinite;
}

.particle.p1 {
  left: 10%;
  background: #3b82f6;
  box-shadow: 0 0 10px #3b82f6;
  animation-delay: 0s;
}

.particle.p2 {
  left: 30%;
  background: #8b5cf6;
  box-shadow: 0 0 10px #8b5cf6;
  animation-delay: 1.5s;
}

.particle.p3 {
  left: 50%;
  background: #06b6d4;
  box-shadow: 0 0 10px #06b6d4;
  animation-delay: 3s;
}

.particle.p4 {
  left: 70%;
  background: #10b981;
  box-shadow: 0 0 10px #10b981;
  animation-delay: 4.5s;
}

.particle.p5 {
  left: 90%;
  background: #f59e0b;
  box-shadow: 0 0 10px #f59e0b;
  animation-delay: 6s;
}

/* 四边流光边框 */
.scatter-border-glow {
  position: absolute;
  inset: 0;
  z-index: 6;
  overflow: hidden;
  pointer-events: none;
  border-radius: 16px;
}

.scatter-border-top,
.scatter-border-right,
.scatter-border-bottom,
.scatter-border-left {
  position: absolute;
  background: linear-gradient(
    90deg,
    transparent,
    hsl(var(--primary)),
    transparent
  );
}

.scatter-border-top {
  top: 0;
  left: -100%;
  width: 100%;
  height: 1px;
  animation: scatter-border-flow-horizontal 3s linear infinite;
}

.scatter-border-bottom {
  right: -100%;
  bottom: 0;
  width: 100%;
  height: 1px;
  animation: scatter-border-flow-horizontal-reverse 3s linear infinite;
}

.scatter-border-right {
  top: -100%;
  right: 0;
  width: 1px;
  height: 100%;
  background: linear-gradient(
    180deg,
    transparent,
    hsl(var(--primary)),
    transparent
  );
  animation: scatter-border-flow-vertical 3s linear infinite;
}

.scatter-border-left {
  bottom: -100%;
  left: 0;
  width: 1px;
  height: 100%;
  background: linear-gradient(
    180deg,
    transparent,
    hsl(var(--primary)),
    transparent
  );
  animation: scatter-border-flow-vertical-reverse 3s linear infinite;
}

/* 角落装饰 */
.scatter-corner {
  position: absolute;
  z-index: 7;
  width: 20px;
  height: 20px;
  pointer-events: none;
}

.scatter-corner::before,
.scatter-corner::after {
  position: absolute;
  content: '';
  background: hsl(var(--primary));
  box-shadow: 0 0 8px hsl(var(--primary));
  animation: scatter-corner-pulse 2s ease-in-out infinite;
}

.scatter-corner-tl {
  top: 0;
  left: 0;
}

.scatter-corner-tl::before {
  top: 0;
  left: 0;
  width: 20px;
  height: 2px;
  border-radius: 0 2px 2px 0;
}

.scatter-corner-tl::after {
  top: 0;
  left: 0;
  width: 2px;
  height: 20px;
  border-radius: 0 0 2px 2px;
}

.scatter-corner-tr {
  top: 0;
  right: 0;
}

.scatter-corner-tr::before {
  top: 0;
  right: 0;
  width: 20px;
  height: 2px;
  border-radius: 2px 0 0 2px;
}

.scatter-corner-tr::after {
  top: 0;
  right: 0;
  width: 2px;
  height: 20px;
  border-radius: 0 0 2px 2px;
}

.scatter-corner-bl {
  bottom: 0;
  left: 0;
}

.scatter-corner-bl::before {
  bottom: 0;
  left: 0;
  width: 20px;
  height: 2px;
  border-radius: 0 2px 2px 0;
}

.scatter-corner-bl::after {
  bottom: 0;
  left: 0;
  width: 2px;
  height: 20px;
  border-radius: 2px 2px 0 0;
}

.scatter-corner-br {
  right: 0;
  bottom: 0;
}

.scatter-corner-br::before {
  right: 0;
  bottom: 0;
  width: 20px;
  height: 2px;
  border-radius: 2px 0 0 2px;
}

.scatter-corner-br::after {
  right: 0;
  bottom: 0;
  width: 2px;
  height: 20px;
  border-radius: 2px 2px 0 0;
}

/* Live 指示灯动画 */
.scatter-live-badge {
  display: inline-flex;
  gap: 0.35rem;
  align-items: center;
  padding: 0.2rem 0.5rem;
  margin-left: 0.5rem;
  font-size: 0.65rem;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted) / 60%);
  border: 1px solid hsl(var(--border) / 50%);
  border-radius: 4px;
}

.live-dot {
  width: 6px;
  height: 6px;
  background: #10b981;
  border-radius: 50%;
  box-shadow: 0 0 8px #10b981;
  animation: scatter-live-blink 1.5s ease-in-out infinite;
}

/* 悬停增强效果 */
.scatter-cool-card:hover .scatter-glow-orb {
  opacity: 0.5;
  animation-duration: 4s;
}

.scatter-cool-card:hover .scatter-scan-line {
  animation-duration: 2.5s;
}

.scatter-cool-card:hover .scatter-corner::before,
.scatter-cool-card:hover .scatter-corner::after {
  animation-duration: 1s;
}

.scatter-cool-card:hover .scatter-border-top,
.scatter-cool-card:hover .scatter-border-right,
.scatter-cool-card:hover .scatter-border-bottom,
.scatter-cool-card:hover .scatter-border-left {
  animation-duration: 2s;
}

/* ==================== 人群多样性热力图 - 酷炫版样式（支持主题切换） ==================== */
.diversity-heatmap-card {
  position: relative;
  padding: 0;
  margin-top: 1rem;
  overflow: hidden;
  background: hsl(var(--card) / 40%);
  border: 1px solid hsl(var(--border) / 30%);
  border-radius: 16px;
  box-shadow:
    0 0 0 1px hsl(var(--foreground) / 5%),
    0 20px 50px hsl(var(--background) / 30%);
  backdrop-filter: blur(20px);
  transition: all 0.3s ease;
}

.diversity-heatmap-card::before {
  position: absolute;
  inset: 0;
  pointer-events: none;
  content: '';
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 5%) 0%,
    transparent 50%,
    hsl(var(--primary) / 3%) 100%
  );
}

/* 背景装饰层 */
.heatmap-bg-decoration {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
}

.heatmap-glow-orb {
  position: absolute;
  border-radius: 50%;
  opacity: 0.4;
  filter: blur(80px);
}

.heatmap-glow-orb.orb-1 {
  top: -100px;
  left: -100px;
  width: 300px;
  height: 300px;
  background: #10b981;
  animation: heatmap-float 10s ease-in-out infinite;
}

.heatmap-glow-orb.orb-2 {
  right: -50px;
  bottom: -50px;
  width: 250px;
  height: 250px;
  background: #06b6d4;
  animation: heatmap-float 12s ease-in-out infinite reverse;
}

.heatmap-glow-orb.orb-3 {
  top: 50%;
  right: 20%;
  width: 200px;
  height: 200px;
  background: #a855f7;
  animation: heatmap-float 8s ease-in-out infinite 2s;
}

.heatmap-grid-lines {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(hsl(var(--primary) / 5%) 1px, transparent 1px),
    linear-gradient(90deg, hsl(var(--primary) / 5%) 1px, transparent 1px);
  background-size: 40px 40px;
  opacity: 0.5;
}

/* 扫描线动画 */
.heatmap-scan-line {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  z-index: 2;
  height: 2px;
  pointer-events: none;
  background: linear-gradient(90deg, transparent, #06b6d4, transparent);
  box-shadow: 0 0 10px #06b6d4;
  opacity: 0.6;
  animation: heatmap-scan 4s linear infinite;
}

/* 标题区域 */
.heatmap-header {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.25rem 1.75rem;
  background: linear-gradient(90deg, hsl(var(--background) / 60%), transparent);
  border-bottom: 1px solid hsl(var(--border) / 30%);
}

.heatmap-title-wrapper {
  display: flex;
  gap: 1rem;
  align-items: center;
}

.heatmap-title-icon {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 10%);
  border: 1px solid hsl(var(--primary) / 30%);
  border-radius: 10px;
}

.heatmap-title-icon svg {
  z-index: 1;
  width: 20px;
  height: 20px;
}

.heatmap-title-icon .icon-pulse {
  position: absolute;
  inset: 0;
  background: hsl(var(--primary) / 20%);
  border-radius: inherit;
  animation: icon-pulse 2s infinite;
}

.heatmap-title-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.heatmap-title-text .title-main {
  font-size: 1.25rem;
  font-weight: 700;
  color: hsl(var(--foreground));
  letter-spacing: 0.02em;
  text-shadow: 0 0 10px hsl(var(--foreground) / 20%);
}

.heatmap-title-text .title-sub {
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 0.7rem;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

/* 状态徽章 */
.heatmap-status-badge {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 6px 12px;
  background: hsl(142deg 76% 36% / 10%);
  border: 1px solid hsl(142deg 76% 36% / 30%);
  border-radius: 20px;
}

.heatmap-status-badge .status-dot {
  width: 6px;
  height: 6px;
  background: #34d399;
  border-radius: 50%;
  box-shadow: 0 0 8px #34d399;
  animation: status-blink 2s infinite;
}

.heatmap-status-badge .status-text {
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 0.75rem;
  font-weight: 600;
  color: #34d399;
  letter-spacing: 0.05em;
}

/* 图表容器 */
.heatmap-chart-container {
  position: relative;
  z-index: 5;
  min-height: 460px;
  padding: 1rem;
}

/* 四角装饰 */
.heatmap-corner {
  position: absolute;
  z-index: 10;
  width: 15px;
  height: 15px;
  border: 2px solid hsl(var(--primary));
  opacity: 0.5;
  transition: all 0.3s ease;
}

.heatmap-chart-container:hover .heatmap-corner {
  width: 20px;
  height: 20px;
  box-shadow: 0 0 10px hsl(var(--primary));
  opacity: 1;
}

.heatmap-corner.corner-tl {
  top: 20px;
  left: 20px;
  border-right: none;
  border-bottom: none;
}

.heatmap-corner.corner-tr {
  top: 20px;
  right: 20px;
  border-bottom: none;
  border-left: none;
}

.heatmap-corner.corner-bl {
  bottom: 20px;
  left: 20px;
  border-top: none;
  border-right: none;
}

.heatmap-corner.corner-br {
  right: 20px;
  bottom: 20px;
  border-top: none;
  border-left: none;
}

/* 加载状态 */
.heatmap-loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: hsl(var(--background) / 70%);
  backdrop-filter: blur(8px);
}

.loading-spinner {
  position: relative;
  width: 60px;
  height: 60px;
  margin-bottom: 1rem;
}

.loading-spinner .spinner-ring {
  position: absolute;
  inset: 0;
  border: 2px solid transparent;
  border-radius: 50%;
}

.loading-spinner .spinner-ring:nth-child(1) {
  border-top-color: #3b82f6;
  animation: spinner-rotate 1s linear infinite;
}

.loading-spinner .spinner-ring:nth-child(2) {
  inset: 6px;
  border-right-color: #8b5cf6;
  animation: spinner-rotate 1.5s linear infinite reverse;
}

.loading-spinner .spinner-ring:nth-child(3) {
  inset: 12px;
  border-bottom-color: #f43f5e;
  animation: spinner-rotate 2s linear infinite;
}

.loading-text {
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 0.875rem;
  color: hsl(var(--muted-foreground));
}

/* 底部自定义图例 */
.heatmap-custom-legend {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 80px;
  padding: 0 2rem;
  background: hsl(var(--background) / 40%);
  border-top: 1px solid hsl(var(--border) / 30%);
}

.heatmap-custom-legend .legend-scale {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 300px;
}

.heatmap-custom-legend .scale-bar {
  height: 6px;
  background: linear-gradient(
    90deg,
    rgb(51 65 85 / 50%) 0%,
    #10b981 33%,
    #06b6d4 66%,
    #a855f7 100%
  );
  border-radius: 3px;
  box-shadow: 0 0 10px hsl(var(--primary) / 30%);
}

.heatmap-custom-legend .scale-labels {
  display: flex;
  justify-content: space-between;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 0.75rem;
  color: hsl(var(--muted-foreground));
}

.heatmap-custom-legend .legend-stats {
  display: flex;
  gap: 2rem;
}

.heatmap-custom-legend .stat-item {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.heatmap-custom-legend .stat-item .stat-label {
  margin-bottom: 2px;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 0.75rem;
  color: hsl(var(--muted-foreground) / 80%);
}

.heatmap-custom-legend .stat-item .stat-value {
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: 1.25rem;
  font-weight: 700;
  color: hsl(var(--foreground));
  text-shadow: 0 0 10px hsl(var(--primary) / 30%);
}

/* 卡片悬停效果 */
.diversity-heatmap-card:hover {
  border-color: hsl(var(--primary) / 40%);
  box-shadow:
    0 0 0 1px hsl(var(--primary) / 10%),
    0 25px 60px hsl(var(--background) / 40%);
}

/* ==================== 安全专家组样式 ==================== */
.security-expert-header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 0;
  margin-top: 1.5rem;
  margin-bottom: 1rem;
  border-top: 1px solid hsl(var(--border));
}

.security-expert-header-left {
  display: flex;
  align-items: center;
}

.security-expert-header-right {
  display: flex;
  gap: 1rem;
  align-items: center;
}

.security-reject-box {
  background: linear-gradient(135deg, #fff5f5 0%, #ffe3e3 100%);
  border: 1px solid #ffa8a8;
}

.security-reject-box .summary-label {
  color: #c92a2a;
}

.security-reject-box .summary-value {
  color: #e03131;
}

.security-platform-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.5rem;
  margin-top: 1rem;
}

/* ==================== 安全专家组卡片 - 炫酷版 ==================== */
.security-platform-card-cool {
  position: relative;
  padding: 0;
  overflow: hidden;
  background: hsl(var(--card) / 50%);
  border: 1px solid hsl(var(--border) / 30%);
  border-radius: 16px;
  box-shadow:
    0 0 0 1px hsl(var(--foreground) / 5%),
    0 20px 40px hsl(var(--background) / 30%);
  backdrop-filter: blur(20px);
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.security-platform-card-cool:hover {
  box-shadow:
    0 0 0 1px hsl(var(--primary) / 30%),
    0 25px 50px hsl(var(--background) / 40%);
  transform: translateY(-4px);
}

/* 背景装饰 */
.security-card-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
}

.security-glow-orb {
  position: absolute;
  top: -50px;
  right: -50px;
  width: 200px;
  height: 200px;
  border-radius: 50%;
  opacity: 0.3;
  filter: blur(60px);
  animation: security-orb-pulse 6s ease-in-out infinite;
}

.tencent-theme .security-glow-orb {
  background: #3b82f6;
}

.aliyun-theme .security-glow-orb {
  background: #f97316;
}

.volcengine-theme .security-glow-orb {
  background: #06b6d4;
}

.security-grid-lines {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(hsl(var(--primary) / 3%) 1px, transparent 1px),
    linear-gradient(90deg, hsl(var(--primary) / 3%) 1px, transparent 1px);
  background-size: 30px 30px;
  opacity: 0.5;
}

/* 流光边框 */
.security-border-glow {
  position: absolute;
  inset: 0;
  z-index: 2;
  overflow: hidden;
  pointer-events: none;
  border-radius: 16px;
}

.security-border-glow .border-line {
  position: absolute;
}

.security-border-glow .border-top {
  top: 0;
  left: -100%;
  width: 100%;
  height: 1px;
  animation: security-border-h 4s linear infinite;
}

.security-border-glow .border-bottom {
  right: -100%;
  bottom: 0;
  width: 100%;
  height: 1px;
  animation: security-border-h-rev 4s linear infinite;
}

.security-border-glow .border-right {
  top: -100%;
  right: 0;
  width: 1px;
  height: 100%;
  animation: security-border-v 4s linear infinite;
}

.security-border-glow .border-left {
  bottom: -100%;
  left: 0;
  width: 1px;
  height: 100%;
  animation: security-border-v-rev 4s linear infinite;
}

.tencent-theme .border-line {
  background: linear-gradient(90deg, transparent, #3b82f6, transparent);
}

.aliyun-theme .border-line {
  background: linear-gradient(90deg, transparent, #f97316, transparent);
}

.volcengine-theme .border-line {
  background: linear-gradient(90deg, transparent, #06b6d4, transparent);
}

.tencent-theme .border-right,
.tencent-theme .border-left {
  background: linear-gradient(180deg, transparent, #3b82f6, transparent);
}

.aliyun-theme .border-right,
.aliyun-theme .border-left {
  background: linear-gradient(180deg, transparent, #f97316, transparent);
}

.volcengine-theme .border-right,
.volcengine-theme .border-left {
  background: linear-gradient(180deg, transparent, #06b6d4, transparent);
}

/* 角落装饰 */
.security-corner {
  position: absolute;
  z-index: 3;
  width: 16px;
  height: 16px;
  pointer-events: none;
}

.security-corner::before,
.security-corner::after {
  position: absolute;
  content: '';
  animation: security-corner-pulse 2s ease-in-out infinite;
}

.tencent-theme .security-corner::before,
.tencent-theme .security-corner::after {
  background: #3b82f6;
  box-shadow: 0 0 8px #3b82f6;
}

.aliyun-theme .security-corner::before,
.aliyun-theme .security-corner::after {
  background: #f97316;
  box-shadow: 0 0 8px #f97316;
}

.volcengine-theme .security-corner::before,
.volcengine-theme .security-corner::after {
  background: #06b6d4;
  box-shadow: 0 0 8px #06b6d4;
}

.security-corner.corner-tl {
  top: 0;
  left: 0;
}

.security-corner.corner-tl::before {
  top: 0;
  left: 0;
  width: 16px;
  height: 2px;
  border-radius: 0 2px 2px 0;
}

.security-corner.corner-tl::after {
  top: 0;
  left: 0;
  width: 2px;
  height: 16px;
  border-radius: 0 0 2px 2px;
}

.security-corner.corner-tr {
  top: 0;
  right: 0;
}

.security-corner.corner-tr::before {
  top: 0;
  right: 0;
  width: 16px;
  height: 2px;
  border-radius: 2px 0 0 2px;
}

.security-corner.corner-tr::after {
  top: 0;
  right: 0;
  width: 2px;
  height: 16px;
  border-radius: 0 0 2px 2px;
}

.security-corner.corner-bl {
  bottom: 0;
  left: 0;
}

.security-corner.corner-bl::before {
  bottom: 0;
  left: 0;
  width: 16px;
  height: 2px;
  border-radius: 0 2px 2px 0;
}

.security-corner.corner-bl::after {
  bottom: 0;
  left: 0;
  width: 2px;
  height: 16px;
  border-radius: 2px 2px 0 0;
}

.security-corner.corner-br {
  right: 0;
  bottom: 0;
}

.security-corner.corner-br::before {
  right: 0;
  bottom: 0;
  width: 16px;
  height: 2px;
  border-radius: 2px 0 0 2px;
}

.security-corner.corner-br::after {
  right: 0;
  bottom: 0;
  width: 2px;
  height: 16px;
  border-radius: 2px 2px 0 0;
}

/* 卡片内容 */
.security-card-content {
  position: relative;
  z-index: 5;
  padding: 1.5rem;
}

.security-platform-card-cool .security-platform-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 1rem;
  margin-bottom: 1.25rem;
  border-bottom: 1px solid hsl(var(--border) / 20%);
}

.security-title-group {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.security-title-indicator {
  display: block;
  width: 3px;
  height: 1rem;
  border-radius: 2px;
  animation: security-indicator-pulse 2s ease-in-out infinite;
}

.tencent-theme .security-title-indicator {
  background: #3b82f6;
  box-shadow: 0 0 10px #3b82f6;
}

.aliyun-theme .security-title-indicator {
  background: #f97316;
  box-shadow: 0 0 10px #f97316;
}

.volcengine-theme .security-title-indicator {
  background: #06b6d4;
  box-shadow: 0 0 10px #06b6d4;
}

.security-platform-card-cool .security-platform-title {
  font-size: 1rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.security-platform-card-cool .security-platform-stats {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.security-platform-card-cool .security-stat-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.security-platform-card-cool .security-stat-label {
  font-size: 0.85rem;
  color: hsl(var(--muted-foreground));
}

.security-platform-card-cool .security-stat-value {
  display: flex;
  gap: 0.5rem;
  align-items: baseline;
}

.security-platform-card-cool .stat-number {
  font-size: 1.5rem;
  font-weight: 700;
  color: hsl(var(--foreground));
}

.security-platform-card-cool .stat-number.reject {
  color: #ef4444;
  text-shadow: 0 0 10px rgb(239 68 68 / 50%);
}

.security-platform-card-cool .stat-trend {
  padding: 0.125rem 0.375rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: #ef4444;
  background: rgb(239 68 68 / 10%);
  border-radius: 4px;
}

.security-platform-card-cool .stat-trend.down {
  color: #10b981;
  background: rgb(16 185 129 / 10%);
}

/* 状态指示灯 */
.security-status {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  padding-top: 1rem;
  margin-top: 1.25rem;
  border-top: 1px solid hsl(var(--border) / 15%);
}

.security-status .status-dot {
  width: 8px;
  height: 8px;
  background: #10b981;
  border-radius: 50%;
  box-shadow: 0 0 10px #10b981;
  animation: status-blink 1.5s ease-in-out infinite;
}

.security-status .status-text {
  font-size: 0.75rem;
  font-weight: 500;
  color: #10b981;
}

/* 悬停增强 */
.security-platform-card-cool:hover .security-glow-orb {
  opacity: 0.5;
  animation-duration: 3s;
}

.security-platform-card-cool:hover .border-line {
  animation-duration: 2s;
}

.security-platform-card-cool:hover .security-corner::before,
.security-platform-card-cool:hover .security-corner::after {
  animation-duration: 1s;
}

.security-platform-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 1rem;
  margin-bottom: 1.5rem;
  border-bottom: 1px solid hsl(var(--border));
}

.security-platform-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.security-platform-logo {
  height: 24px;
  object-fit: contain;
}

.aliyun-logo {
  height: 22px;
}

/* 文字logo样式 */
.security-logo-text {
  display: flex;
  align-items: center;
  font-weight: 600;
}

.tencent-text {
  gap: 0.25rem;
  font-size: 0.9rem;
  color: #0052d9;
}

.tencent-cn {
  font-weight: 700;
  color: #0052d9;
}

.volcengine-logo-wrapper {
  display: flex;
  gap: 6px;
  align-items: center;
}

.volcengine-icon {
  width: auto;
  height: 22px;
}

.volcengine-text {
  font-size: 17px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.security-platform-stats {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.security-stat-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.security-stat-label {
  font-size: 0.9rem;
  color: #64748b;
}

.security-stat-value {
  font-size: 1.75rem;
  font-weight: 700;
  color: hsl(var(--foreground));
}

.security-reject-value {
  color: #e03131;
}

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

/* ==================== AI算力成本看板 & 内容转化漏斗 & AIGC生成中心 - 炫酷效果样式 ==================== */

/* 通用section炫酷容器样式 */
.ai-cost-section,
.conversion-funnel-section,
.aigc-section {
  position: relative;
  padding: 1.5rem;
  overflow: hidden;
  background: hsl(var(--card) / 40%);
  border: 1px solid hsl(var(--border) / 30%);
  border-radius: 20px;
  box-shadow:
    0 0 0 1px hsl(var(--foreground) / 5%),
    0 25px 60px hsl(var(--background) / 30%);
  backdrop-filter: blur(20px);
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.ai-cost-section:hover,
.conversion-funnel-section:hover,
.aigc-section:hover {
  box-shadow:
    0 0 0 1px hsl(var(--primary) / 20%),
    0 30px 70px hsl(var(--background) / 40%),
    0 0 40px hsl(var(--primary) / 10%);
}

/* 流光边框容器 */
.section-glow-border {
  position: absolute;
  inset: 0;
  z-index: 1;
  overflow: hidden;
  pointer-events: none;
  border-radius: 20px;
}

/* 四边流光边框 */
.glow-border-top,
.glow-border-right,
.glow-border-bottom,
.glow-border-left {
  position: absolute;
  background: linear-gradient(
    90deg,
    transparent,
    hsl(var(--primary)),
    hsl(var(--primary) / 80%),
    transparent
  );
}

.glow-border-top {
  top: 0;
  left: -100%;
  width: 100%;
  height: 2px;
  box-shadow:
    0 0 15px hsl(var(--primary) / 60%),
    0 0 30px hsl(var(--primary) / 30%);
  animation: border-flow-horizontal 4s linear infinite;
}

.glow-border-bottom {
  right: -100%;
  bottom: 0;
  width: 100%;
  height: 2px;
  box-shadow:
    0 0 15px hsl(var(--primary) / 60%),
    0 0 30px hsl(var(--primary) / 30%);
  animation: border-flow-horizontal-reverse 4s linear infinite;
}

.glow-border-right {
  top: -100%;
  right: 0;
  width: 2px;
  height: 100%;
  background: linear-gradient(
    180deg,
    transparent,
    hsl(var(--primary)),
    hsl(var(--primary) / 80%),
    transparent
  );
  box-shadow:
    0 0 15px hsl(var(--primary) / 60%),
    0 0 30px hsl(var(--primary) / 30%);
  animation: border-flow-vertical 4s linear infinite;
}

.glow-border-left {
  bottom: -100%;
  left: 0;
  width: 2px;
  height: 100%;
  background: linear-gradient(
    180deg,
    transparent,
    hsl(var(--primary)),
    hsl(var(--primary) / 80%),
    transparent
  );
  box-shadow:
    0 0 15px hsl(var(--primary) / 60%),
    0 0 30px hsl(var(--primary) / 30%);
  animation: border-flow-vertical-reverse 4s linear infinite;
}

/* 背景装饰层 */
.section-bg-decoration {
  position: absolute;
  inset: 0;
  z-index: 0;
  overflow: hidden;
  pointer-events: none;
}

/* 背景光晕球 */
.section-glow-orb {
  position: absolute;
  border-radius: 50%;
  opacity: 0.25;
  filter: blur(100px);
  animation: orb-float 12s ease-in-out infinite;
}

.section-glow-orb.orb-blue {
  top: -100px;
  left: -100px;
  width: 350px;
  height: 350px;
  background: linear-gradient(135deg, #3b82f6, #60a5fa);
  animation-delay: 0s;
}

.section-glow-orb.orb-purple {
  right: -80px;
  bottom: -80px;
  width: 300px;
  height: 300px;
  background: linear-gradient(135deg, #8b5cf6, #a78bfa);
  animation-delay: 3s;
}

.section-glow-orb.orb-cyan {
  top: -100px;
  left: -100px;
  width: 350px;
  height: 350px;
  background: linear-gradient(135deg, #06b6d4, #22d3ee);
  animation-delay: 0s;
}

.section-glow-orb.orb-green {
  right: -80px;
  bottom: -80px;
  width: 300px;
  height: 300px;
  background: linear-gradient(135deg, #10b981, #34d399);
  animation-delay: 3s;
}

/* 背景网格线 */
.section-grid-lines {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(hsl(var(--primary) / 4%) 1px, transparent 1px),
    linear-gradient(90deg, hsl(var(--primary) / 4%) 1px, transparent 1px);
  background-size: 50px 50px;
  opacity: 0.5;
  animation: grid-pulse 4s ease-in-out infinite;
}

/* 角落装饰 */
.section-corner {
  position: absolute;
  z-index: 2;
  width: 24px;
  height: 24px;
  pointer-events: none;
}

.section-corner::before,
.section-corner::after {
  position: absolute;
  content: '';
  background: hsl(var(--primary));
  box-shadow:
    0 0 12px hsl(var(--primary)),
    0 0 24px hsl(var(--primary) / 50%);
  animation: corner-pulse 2.5s ease-in-out infinite;
}

.section-corner-tl {
  top: 0;
  left: 0;
}

.section-corner-tl::before {
  top: 0;
  left: 0;
  width: 24px;
  height: 3px;
  border-radius: 0 3px 3px 0;
}

.section-corner-tl::after {
  top: 0;
  left: 0;
  width: 3px;
  height: 24px;
  border-radius: 0 0 3px 3px;
}

.section-corner-tr {
  top: 0;
  right: 0;
}

.section-corner-tr::before {
  top: 0;
  right: 0;
  width: 24px;
  height: 3px;
  border-radius: 3px 0 0 3px;
}

.section-corner-tr::after {
  top: 0;
  right: 0;
  width: 3px;
  height: 24px;
  border-radius: 0 0 3px 3px;
}

.section-corner-bl {
  bottom: 0;
  left: 0;
}

.section-corner-bl::before {
  bottom: 0;
  left: 0;
  width: 24px;
  height: 3px;
  border-radius: 0 3px 3px 0;
}

.section-corner-bl::after {
  bottom: 0;
  left: 0;
  width: 3px;
  height: 24px;
  border-radius: 3px 3px 0 0;
}

.section-corner-br {
  right: 0;
  bottom: 0;
}

.section-corner-br::before {
  right: 0;
  bottom: 0;
  width: 24px;
  height: 3px;
  border-radius: 3px 0 0 3px;
}

.section-corner-br::after {
  right: 0;
  bottom: 0;
  width: 3px;
  height: 24px;
  border-radius: 3px 3px 0 0;
}

/* 扫描线动画 - AIGC专用 */
.section-scan-line {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  z-index: 3;
  height: 3px;
  pointer-events: none;
  background: linear-gradient(
    90deg,
    transparent 0%,
    hsl(var(--primary) / 30%) 20%,
    hsl(var(--primary)) 50%,
    hsl(var(--primary) / 30%) 80%,
    transparent 100%
  );
  box-shadow:
    0 0 20px hsl(var(--primary)),
    0 0 40px hsl(var(--primary) / 50%);
  opacity: 0;
  animation: scan-sweep 5s ease-in-out infinite;
}

/* 数据流粒子 - AIGC专用 */
.data-particles {
  position: absolute;
  inset: 0;
  z-index: 2;
  overflow: hidden;
  pointer-events: none;
}

.data-particle {
  position: absolute;
  width: 6px;
  height: 6px;
  background: hsl(var(--primary));
  border-radius: 50%;
  box-shadow:
    0 0 12px hsl(var(--primary)),
    0 0 24px hsl(var(--primary) / 50%);
  opacity: 0;
  animation: particle-rise 10s ease-in-out infinite;
}

.data-particle.p1 {
  left: 10%;
  background: #3b82f6;
  box-shadow:
    0 0 12px #3b82f6,
    0 0 24px rgb(59 130 246 / 50%);
  animation-delay: 0s;
}

.data-particle.p2 {
  left: 30%;
  background: #8b5cf6;
  box-shadow:
    0 0 12px #8b5cf6,
    0 0 24px rgb(139 92 246 / 50%);
  animation-delay: 2s;
}

.data-particle.p3 {
  left: 50%;
  background: #06b6d4;
  box-shadow:
    0 0 12px #06b6d4,
    0 0 24px rgb(6 182 212 / 50%);
  animation-delay: 4s;
}

.data-particle.p4 {
  left: 70%;
  background: #10b981;
  box-shadow:
    0 0 12px #10b981,
    0 0 24px rgb(16 185 129 / 50%);
  animation-delay: 6s;
}

.data-particle.p5 {
  left: 90%;
  background: #f59e0b;
  box-shadow:
    0 0 12px #f59e0b,
    0 0 24px rgb(245 158 11 / 50%);
  animation-delay: 8s;
}

/* 炫酷标题样式 */
.glow-title {
  position: relative;
  z-index: 10;
  display: flex;
  gap: 0.75rem;
  align-items: center;
  text-shadow: 0 0 20px hsl(var(--primary) / 40%);
}

.title-badge {
  display: inline-flex;
  gap: 0.35rem;
  align-items: center;
  padding: 0.2rem 0.6rem;
  font-size: 0.65rem;
  font-weight: 700;
  color: hsl(var(--primary-foreground));
  letter-spacing: 0.1em;
  background: linear-gradient(
    135deg,
    hsl(var(--primary)),
    hsl(var(--primary) / 80%)
  );
  border-radius: 6px;
  box-shadow: 0 0 15px hsl(var(--primary) / 50%);
  animation: badge-glow 2s ease-in-out infinite;
}

.title-badge.live-badge {
  background: linear-gradient(135deg, #10b981, #059669);
  box-shadow: 0 0 15px rgb(16 185 129 / 50%);
}

.title-badge .live-dot {
  width: 6px;
  height: 6px;
  background: #fff;
  border-radius: 50%;
  animation: live-blink 1.2s ease-in-out infinite;
}

/* AIGC标题特殊样式 */
.aigc-title {
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 20%) 0%,
    hsl(var(--primary) / 8%) 100%
  );
  border-left-color: #06b6d4;
}

/* AI算力成本看板特殊配色 */
.ai-cost-section .glow-border-top,
.ai-cost-section .glow-border-bottom {
  background: linear-gradient(
    90deg,
    transparent,
    #f59e0b,
    #fbbf24,
    transparent
  );
  box-shadow:
    0 0 15px rgb(245 158 11 / 60%),
    0 0 30px rgb(245 158 11 / 30%);
}

.ai-cost-section .glow-border-right,
.ai-cost-section .glow-border-left {
  background: linear-gradient(
    180deg,
    transparent,
    #f59e0b,
    #fbbf24,
    transparent
  );
  box-shadow:
    0 0 15px rgb(245 158 11 / 60%),
    0 0 30px rgb(245 158 11 / 30%);
}

.ai-cost-section .section-corner::before,
.ai-cost-section .section-corner::after {
  background: #f59e0b;
  box-shadow:
    0 0 12px #f59e0b,
    0 0 24px rgb(245 158 11 / 50%);
}

.ai-cost-section .glow-title {
  text-shadow: 0 0 20px rgb(245 158 11 / 40%);
}

.ai-cost-section .title-badge {
  background: linear-gradient(135deg, #f59e0b, #d97706);
  box-shadow: 0 0 15px rgb(245 158 11 / 50%);
}

/* 内容转化漏斗特殊配色 */
.conversion-funnel-section .glow-border-top,
.conversion-funnel-section .glow-border-bottom {
  background: linear-gradient(
    90deg,
    transparent,
    #8b5cf6,
    #a78bfa,
    transparent
  );
  box-shadow:
    0 0 15px rgb(139 92 246 / 60%),
    0 0 30px rgb(139 92 246 / 30%);
}

.conversion-funnel-section .glow-border-right,
.conversion-funnel-section .glow-border-left {
  background: linear-gradient(
    180deg,
    transparent,
    #8b5cf6,
    #a78bfa,
    transparent
  );
  box-shadow:
    0 0 15px rgb(139 92 246 / 60%),
    0 0 30px rgb(139 92 246 / 30%);
}

.conversion-funnel-section .section-corner::before,
.conversion-funnel-section .section-corner::after {
  background: #8b5cf6;
  box-shadow:
    0 0 12px #8b5cf6,
    0 0 24px rgb(139 92 246 / 50%);
}

.conversion-funnel-section .glow-title {
  text-shadow: 0 0 20px rgb(139 92 246 / 40%);
}

/* AIGC生成中心特殊配色 */
.aigc-section .glow-border-top,
.aigc-section .glow-border-bottom {
  background: linear-gradient(
    90deg,
    transparent,
    #06b6d4,
    #22d3ee,
    transparent
  );
  box-shadow:
    0 0 15px rgb(6 182 212 / 60%),
    0 0 30px rgb(6 182 212 / 30%);
}

.aigc-section .glow-border-right,
.aigc-section .glow-border-left {
  background: linear-gradient(
    180deg,
    transparent,
    #06b6d4,
    #22d3ee,
    transparent
  );
  box-shadow:
    0 0 15px rgb(6 182 212 / 60%),
    0 0 30px rgb(6 182 212 / 30%);
}

.aigc-section .section-corner::before,
.aigc-section .section-corner::after {
  background: #06b6d4;
  box-shadow:
    0 0 12px #06b6d4,
    0 0 24px rgb(6 182 212 / 50%);
}

.aigc-section .section-scan-line {
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgb(6 182 212 / 30%) 20%,
    #06b6d4 50%,
    rgb(6 182 212 / 30%) 80%,
    transparent 100%
  );
  box-shadow:
    0 0 20px #06b6d4,
    0 0 40px rgb(6 182 212 / 50%);
}

/* 悬停增强效果 */
.ai-cost-section:hover .section-glow-orb,
.conversion-funnel-section:hover .section-glow-orb,
.aigc-section:hover .section-glow-orb {
  opacity: 0.4;
  animation-duration: 6s;
}

.ai-cost-section:hover .glow-border-top,
.ai-cost-section:hover .glow-border-bottom,
.ai-cost-section:hover .glow-border-right,
.ai-cost-section:hover .glow-border-left,
.conversion-funnel-section:hover .glow-border-top,
.conversion-funnel-section:hover .glow-border-bottom,
.conversion-funnel-section:hover .glow-border-right,
.conversion-funnel-section:hover .glow-border-left,
.aigc-section:hover .glow-border-top,
.aigc-section:hover .glow-border-bottom,
.aigc-section:hover .glow-border-right,
.aigc-section:hover .glow-border-left {
  animation-duration: 2.5s;
}

.ai-cost-section:hover .section-corner::before,
.ai-cost-section:hover .section-corner::after,
.conversion-funnel-section:hover .section-corner::before,
.conversion-funnel-section:hover .section-corner::after,
.aigc-section:hover .section-corner::before,
.aigc-section:hover .section-corner::after {
  animation-duration: 1.5s;
}

.aigc-section:hover .section-scan-line {
  animation-duration: 3s;
}

.aigc-section:hover .data-particle {
  animation-duration: 6s;
}

/* section header z-index 调整 */
.ai-cost-section .section-header,
.conversion-funnel-section .section-header,
.aigc-section .section-header,
.critic-section .section-header,
.rlhf-section .section-header {
  position: relative;
  z-index: 10;
}

.ai-cost-section .section-content,
.conversion-funnel-section .section-content,
.aigc-section .section-content,
.critic-section .section-content,
.rlhf-section .section-content {
  position: relative;
  z-index: 10;
}

/* 多维度AI专家反馈组样式 */
.critic-section {
  position: relative;
  padding: 1.5rem;
  overflow: hidden;
  background: hsl(var(--card) / 40%);
  border: 1px solid hsl(var(--border) / 30%);
  border-radius: 20px;
  box-shadow:
    0 0 0 1px hsl(var(--foreground) / 5%),
    0 25px 60px hsl(var(--background) / 30%);
  backdrop-filter: blur(20px);
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.critic-section:hover {
  box-shadow:
    0 0 0 1px hsl(var(--primary) / 20%),
    0 30px 70px hsl(var(--background) / 40%),
    0 0 40px rgb(139 92 246 / 10%);
}

/* 多维度AI专家反馈组配色 - 紫色系 */
.section-glow-orb.orb-violet {
  top: -100px;
  left: -100px;
  width: 350px;
  height: 350px;
  background: linear-gradient(135deg, #8b5cf6, #a78bfa);
  animation-delay: 0s;
}

.section-glow-orb.orb-rose {
  right: -80px;
  bottom: -80px;
  width: 300px;
  height: 300px;
  background: linear-gradient(135deg, #ec4899, #f472b6);
  animation-delay: 3s;
}

.critic-section .glow-border-top,
.critic-section .glow-border-bottom {
  background: linear-gradient(
    90deg,
    transparent,
    #8b5cf6,
    #a78bfa,
    transparent
  );
  box-shadow:
    0 0 15px rgb(139 92 246 / 60%),
    0 0 30px rgb(139 92 246 / 30%);
}

.critic-section .glow-border-right,
.critic-section .glow-border-left {
  background: linear-gradient(
    180deg,
    transparent,
    #8b5cf6,
    #a78bfa,
    transparent
  );
  box-shadow:
    0 0 15px rgb(139 92 246 / 60%),
    0 0 30px rgb(139 92 246 / 30%);
}

.critic-section .section-corner::before,
.critic-section .section-corner::after {
  background: #8b5cf6;
  box-shadow:
    0 0 12px #8b5cf6,
    0 0 24px rgb(139 92 246 / 50%);
}

.critic-title {
  background: linear-gradient(
    135deg,
    rgb(139 92 246 / 20%) 0%,
    rgb(139 92 246 / 8%) 100%
  );
  border-left-color: #8b5cf6;
}

.critic-title .glow-title {
  text-shadow: 0 0 20px rgb(139 92 246 / 40%);
}

.title-badge.critic-badge {
  background: linear-gradient(135deg, #8b5cf6, #7c3aed);
  box-shadow: 0 0 15px rgb(139 92 246 / 50%);
}

/* 人工专家反馈（RLHF报告）样式 */
.rlhf-section {
  position: relative;
  padding: 1.5rem;
  overflow: hidden;
  background: hsl(var(--card) / 40%);
  border: 1px solid hsl(var(--border) / 30%);
  border-radius: 20px;
  box-shadow:
    0 0 0 1px hsl(var(--foreground) / 5%),
    0 25px 60px hsl(var(--background) / 30%);
  backdrop-filter: blur(20px);
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.rlhf-section:hover {
  box-shadow:
    0 0 0 1px hsl(var(--primary) / 20%),
    0 30px 70px hsl(var(--background) / 40%),
    0 0 40px rgb(16 185 129 / 10%);
}

/* RLHF配色 - 绿色/琥珀色系 */
.section-glow-orb.orb-amber {
  top: -100px;
  left: -100px;
  width: 350px;
  height: 350px;
  background: linear-gradient(135deg, #f59e0b, #fbbf24);
  animation-delay: 0s;
}

.section-glow-orb.orb-emerald {
  right: -80px;
  bottom: -80px;
  width: 300px;
  height: 300px;
  background: linear-gradient(135deg, #10b981, #34d399);
  animation-delay: 3s;
}

.rlhf-section .glow-border-top,
.rlhf-section .glow-border-bottom {
  background: linear-gradient(
    90deg,
    transparent,
    #10b981,
    #34d399,
    transparent
  );
  box-shadow:
    0 0 15px rgb(16 185 129 / 60%),
    0 0 30px rgb(16 185 129 / 30%);
}

.rlhf-section .glow-border-right,
.rlhf-section .glow-border-left {
  background: linear-gradient(
    180deg,
    transparent,
    #10b981,
    #34d399,
    transparent
  );
  box-shadow:
    0 0 15px rgb(16 185 129 / 60%),
    0 0 30px rgb(16 185 129 / 30%);
}

.rlhf-section .section-corner::before,
.rlhf-section .section-corner::after {
  background: #10b981;
  box-shadow:
    0 0 12px #10b981,
    0 0 24px rgb(16 185 129 / 50%);
}

.rlhf-section .section-scan-line {
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgb(16 185 129 / 30%) 20%,
    #10b981 50%,
    rgb(16 185 129 / 30%) 80%,
    transparent 100%
  );
  box-shadow:
    0 0 20px #10b981,
    0 0 40px rgb(16 185 129 / 50%);
}

.rlhf-title {
  background: linear-gradient(
    135deg,
    rgb(16 185 129 / 20%) 0%,
    rgb(16 185 129 / 8%) 100%
  );
  border-left-color: #10b981;
}

.rlhf-title .glow-title {
  text-shadow: 0 0 20px rgb(16 185 129 / 40%);
}

.title-badge.rlhf-badge {
  background: linear-gradient(135deg, #10b981, #059669);
  box-shadow: 0 0 15px rgb(16 185 129 / 50%);
}

/* 悬停增强效果 - 新增板块 */
.critic-section:hover .section-glow-orb,
.rlhf-section:hover .section-glow-orb {
  opacity: 0.4;
  animation-duration: 6s;
}

.critic-section:hover .glow-border-top,
.critic-section:hover .glow-border-bottom,
.critic-section:hover .glow-border-right,
.critic-section:hover .glow-border-left,
.rlhf-section:hover .glow-border-top,
.rlhf-section:hover .glow-border-bottom,
.rlhf-section:hover .glow-border-right,
.rlhf-section:hover .glow-border-left {
  animation-duration: 2.5s;
}

.critic-section:hover .section-corner::before,
.critic-section:hover .section-corner::after,
.rlhf-section:hover .section-corner::before,
.rlhf-section:hover .section-corner::after {
  animation-duration: 1.5s;
}

.rlhf-section:hover .section-scan-line {
  animation-duration: 3s;
}

.rlhf-section:hover .data-particle {
  animation-duration: 6s;
}

/* ==================== 性能优化 ==================== */

.performance-mode .section-glow-orb,
.performance-mode .section-grid-lines,
.performance-mode .section-scan-line,
.performance-mode .data-particle,
.performance-mode .glow-border-top,
.performance-mode .glow-border-bottom,
.performance-mode .glow-border-left,
.performance-mode .glow-border-right,
.performance-mode .radar-outer-glow,
.performance-mode .radar-rotating-ring,
.performance-mode .radar-pulse-line,
.performance-mode .radar-vertex-pulse,
.performance-mode .radar-pulse-waves,
.performance-mode .flow-arrow-to-radar,
.performance-mode .section-glow-border > div {
  animation: none !important;
}

.performance-mode .section-container:hover .section-corner,
.performance-mode .agent-card:hover {
  transform: none;
  transition: none;
}

/* ==================== 炫酷效果样式结束 ==================== */
</style>
