<!-- AIGC生成中心 -->
<script setup lang="ts">
// @ts-nocheck
import type {
  AgentContentTrend,
  AgentCostItem,
  AgentStat,
  JobTaskItem,
} from '../types';

import { computed, onMounted, onUnmounted, ref, watch } from 'vue';

import { EchartsUI, useEcharts } from '@vben/plugins/echarts';

import { LoadingOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue';
import {
  Card,
  Col,
  Empty,
  Pagination,
  Row,
  Skeleton,
  Table,
  Tabs,
  Tag,
  Tooltip,
} from 'ant-design-vue';
// 导入 dayjs
import dayjs from 'dayjs';

import CountTo from '#/components/CountTo.vue';

import {
  createAigcDonutChartOption,
  createEmptyAigcDonutChartOption,
  getContentCount,
} from '../charts/aigcCharts';
import { useChartTheme } from '../composables';
import { formatNumber } from '../utils';

// ==================== Props ====================

interface Props {
  agentCardPagination: { current: number; pageSize: number; total: number };
  agentCostData: AgentCostItem[];
  agentContentDailyTrend: AgentContentTrend[];
  agentStatsList: AgentStat[];
  jobTaskActiveTab: 'completed' | 'not_deployed' | 'running';
  jobTaskList: JobTaskItem[];
  loading?: boolean;
  selectedAgentCode?: null | string;
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  selectedAgentCode: null,
});

// ==================== Emits ====================

const emit = defineEmits<{
  agentCardPageChange: [page: number, pageSize: number];
  agentSelect: [agentCode: null | string];
  jobTaskTabChange: [activeKey: string];
  taskTableMouseEnter: [];
  taskTableMouseLeave: [];
}>();

// ==================== 图表 Ref ====================

const internalDonutChartRef = ref();
const {
  renderEcharts: renderDonutChart,
  getChartInstance: getDonutChartInstance,
} = useEcharts(internalDonutChartRef);

// ==================== 图表更新 ====================

function updateDonutChart() {
  if (props.agentStatsList.length === 0) {
    renderDonutChart(createEmptyAigcDonutChartOption());
    return;
  }
  renderDonutChart(createAigcDonutChartOption(props.agentStatsList));

  // 绑定点击事件 - 点击 Agent 扇区筛选任务列表
  const chartInstance = getDonutChartInstance();
  if (chartInstance) {
    chartInstance.off('click');
    chartInstance.on('click', (params: { data?: { agent_code?: string } }) => {
      const agentCode = params.data?.agent_code;
      if (agentCode) {
        // 切换选中状态：如果已选中则取消，否则选中
        emit(
          'agentSelect',
          props.selectedAgentCode === agentCode ? null : agentCode,
        );
      }
    });
  }
}

// 监听数据变化，自动更新图表
watch(
  () => props.agentStatsList,
  () => {
    updateDonutChart();
  },
  { deep: true },
);

// ==================== 主题变化监听 ====================

// 监听主题变化，重新渲染图表以应用新的主题颜色
useChartTheme([updateDonutChart]);

// ==================== 表格 Ref 和自动滚动 ====================

const internalJobTaskTableRef = ref();
const isTaskTableHoveredInternal = ref(false);
let taskAutoScrollTimer: null | ReturnType<typeof setInterval> = null;
let isResetting = false; // 标记是否正在重置滚动位置
const AUTO_SCROLL_INTERVAL = 1000;
const AUTO_SCROLL_STEP = 2;
const AUTO_SCROLL_RESET_DELAY = 100;

function startTaskTableAutoScroll() {
  stopTaskTableAutoScroll();
  if (props.jobTaskList.length <= 5) return;

  taskAutoScrollTimer = setInterval(() => {
    if (document.hidden || isTaskTableHoveredInternal.value || isResetting) {
      return;
    }

    const tableEl =
      internalJobTaskTableRef.value?.$el?.querySelector('.ant-table-body');
    if (!tableEl) return;

    const scrollTop = tableEl.scrollTop;
    const scrollHeight = tableEl.scrollHeight;
    const clientHeight = tableEl.clientHeight;

    // 到达底部时，立即重置到顶部（不用 smooth，避免重复触发）
    if (scrollTop + clientHeight >= scrollHeight - 1) {
      isResetting = true;
      tableEl.scrollTop = 0; // 立即重置，不用动画
      setTimeout(() => {
        isResetting = false;
      }, AUTO_SCROLL_RESET_DELAY); // 短暂延迟后允许继续滚动
    } else {
      tableEl.scrollTop += AUTO_SCROLL_STEP; // 不用 smooth，避免动画延迟
    }
  }, AUTO_SCROLL_INTERVAL);
}

function stopTaskTableAutoScroll() {
  if (taskAutoScrollTimer) {
    clearInterval(taskAutoScrollTimer);
    taskAutoScrollTimer = null;
  }
}

// 数据变化时重启自动滚动
watch(
  () => props.jobTaskList,
  () => {
    startTaskTableAutoScroll();
  },
  { deep: true },
);

// 组件挂载时启动自动滚动
onMounted(() => {
  updateDonutChart();
  startTaskTableAutoScroll();
  document.addEventListener('visibilitychange', handleVisibilityChange);
});

// 组件卸载时清除定时器
onUnmounted(() => {
  stopTaskTableAutoScroll();
  document.removeEventListener('visibilitychange', handleVisibilityChange);
});

// ==================== 计算属性 ====================

/** 生成文章总数量 */
const totalContentCount = computed(() => {
  return props.agentStatsList.reduce(
    (sum, item) => sum + getContentCount(item),
    0,
  );
});

/** 当前页显示的 Agent 列表（分页） */
const pagedAgentStatsList = computed(() => {
  const { current, pageSize } = props.agentCardPagination;
  const start = (current - 1) * pageSize;
  const end = start + pageSize;
  return props.agentStatsList.slice(start, end);
});

// ==================== 辅助函数 ====================

/** 获取运行状态 */
function getIsRunning(agent: AgentStat): boolean {
  const isRunning = agent.is_running ?? agent.running_count;
  return Number(isRunning) > 0;
}

/** 获取 Agent 的 Job 数量 */
function getAgentJobCount(agentCode: string): number {
  const agentCost = props.agentCostData.find(
    (item) => item.agent_code === agentCode,
  );
  return agentCost?.job_count || 0;
}

/** 获取 Agent 每日生成文章数量趋势数据 */
function getAgentTrendData(agentCode: string): {
  nodes: Array<{ count: number; date: string; x: number; y: number }>;
  points: string;
} {
  const trends = props.agentContentDailyTrend.filter(
    (t) => t.agent_code === agentCode,
  );

  if (trends.length === 0) {
    return { nodes: [], points: '' };
  }

  const counts = trends.map((t) => t.content_count);
  const maxCount = Math.max(...counts, 1);
  const minCount = Math.min(...counts, 0);

  const svgWidth = 300;
  const svgHeight = 60;
  const paddingX = 15;
  const paddingY = 15;
  const graphWidth = svgWidth - paddingX * 2;
  const graphHeight = svgHeight - paddingY * 2;

  const nodes = trends.map((t, index) => {
    const x = paddingX + (index / (trends.length - 1 || 1)) * graphWidth;
    const y =
      paddingY +
      graphHeight -
      ((t.content_count - minCount) / (maxCount - minCount || 1)) * graphHeight;
    return {
      x,
      y,
      count: t.content_count,
      date: dayjs(t.date).format('MM-DD'),
    };
  });

  const points = nodes.map((n) => `${n.x},${n.y}`).join(' ');

  return { nodes, points };
}

// ==================== 任务列表表格列配置 ====================

const jobTaskColumns = [
  {
    title: '任务名称',
    dataIndex: 'job_name',
    key: 'job_name',
    width: 150,
    ellipsis: true,
  },
  {
    title: '生成文章数量',
    dataIndex: 'content_count',
    key: 'content_count',
    width: 100,
    customRender: ({ record }: { record: JobTaskItem }) =>
      formatNumber(record.content_count),
  },
  {
    title: '完成耗时',
    key: 'duration',
    width: 100,
    customRender: ({ record }: { record: JobTaskItem }) =>
      record.start_time && record.end_time
        ? formatDuration(record.start_time, record.end_time)
        : '-',
  },
];

// ==================== 格式化函数 ====================

function formatDuration(startTime: string, endTime: string): string {
  if (!startTime || !endTime) return '-';
  const start = dayjs(startTime);
  const end = dayjs(endTime);
  const diffSeconds = end.diff(start, 'second');

  if (diffSeconds < 0) return '-';
  if (diffSeconds < 60) return `${diffSeconds}秒`;
  if (diffSeconds < 3600) {
    const minutes = Math.floor(diffSeconds / 60);
    const seconds = diffSeconds % 60;
    return seconds > 0 ? `${minutes}分${seconds}秒` : `${minutes}分`;
  }
  const hours = Math.floor(diffSeconds / 3600);
  const minutes = Math.floor((diffSeconds % 3600) / 60);
  return minutes > 0 ? `${hours}时${minutes}分` : `${hours}时`;
}

// ==================== 事件处理 ====================

function handleJobTaskTabChange(activeKey: string) {
  emit('jobTaskTabChange', activeKey);
}

function handleAgentCardPageChange(page: number, pageSize: number) {
  emit('agentCardPageChange', page, pageSize);
}

function handleTaskTableMouseEnter() {
  isTaskTableHoveredInternal.value = true;
  emit('taskTableMouseEnter');
}

function handleTaskTableMouseLeave() {
  isTaskTableHoveredInternal.value = false;
  emit('taskTableMouseLeave');
}

function handleVisibilityChange() {
  if (document.hidden) {
    stopTaskTableAutoScroll();
  } else {
    startTaskTableAutoScroll();
  }
}
</script>

<template>
  <div class="section-container aigc-section mt-4">
    <!-- 流光边框装饰 -->
    <div class="section-glow-border">
      <div class="glow-border-top"></div>
      <div class="glow-border-right"></div>
      <div class="glow-border-bottom"></div>
      <div class="glow-border-left"></div>
    </div>
    <!-- 背景装饰层 -->
    <div class="section-bg-decoration">
      <div class="section-glow-orb orb-cyan"></div>
      <div class="section-glow-orb orb-green"></div>
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

    <div class="section-header">
      <span class="section-title glow-title aigc-title"> AIGC生成中心 </span>
    </div>

    <div class="section-content">
      <!-- 上半部分：左侧环形图 + 右侧任务列表 -->
      <Row :gutter="16" class="mb-4" type="flex" align="stretch">
        <!-- 左侧：生成文章数量 + 环形图 -->
        <Col :span="10" class="flex">
          <Card
            :bordered="false"
            class="dashboard-glass-card pie-chart-card flex-1"
          >
            <div class="mb-3 flex items-center gap-2">
              <span class="text-sm text-muted-foreground">生成文章数量</span>
              <Tooltip title="统计所有 Agent 生成的文章总数量">
                <QuestionCircleOutlined
                  class="cursor-help text-muted-foreground"
                />
              </Tooltip>
            </div>
            <Skeleton :loading="loading" active :paragraph="{ rows: 1 }">
              <div class="mb-4 text-4xl font-bold">
                {{ formatNumber(totalContentCount) }}
              </div>
            </Skeleton>

            <!-- 环形图 -->
            <div class="pie-chart-container">
              <div
                v-if="loading"
                class="absolute inset-0 z-10 flex items-center justify-center bg-background/50"
              >
                <div class="text-muted-foreground">加载中...</div>
              </div>
              <EchartsUI
                ref="internalDonutChartRef"
                height="100%"
                width="100%"
              />
            </div>
          </Card>
        </Col>

        <!-- 右侧：任务列表 -->
        <Col :span="14" class="flex">
          <Card :bordered="false" class="flex-1" title="任务列表">
            <Tabs
              :active-key="jobTaskActiveTab"
              size="small"
              @change="handleJobTaskTabChange"
            >
              <Tabs.TabPane key="not_deployed" tab="未开始" />
              <Tabs.TabPane key="running" tab="进行中" />
              <Tabs.TabPane key="completed" tab="已结束" />
            </Tabs>

            <Skeleton :loading="loading" active :paragraph="{ rows: 6 }">
              <div
                class="table-scroll-container"
                @mouseenter="handleTaskTableMouseEnter"
                @mouseleave="handleTaskTableMouseLeave"
              >
                <Table
                  ref="internalJobTaskTableRef"
                  :columns="jobTaskColumns"
                  :data-source="jobTaskList"
                  :pagination="false"
                  :row-key="(record: JobTaskItem) => record.job_id"
                  :scroll="{ y: 320 }"
                  bordered
                  size="small"
                >
                  <template #emptyText>
                    <Empty description="暂无任务数据" />
                  </template>
                </Table>
              </div>
            </Skeleton>
          </Card>
        </Col>
      </Row>

      <!-- 下半部分：Agent 卡片列表 -->
      <Skeleton :loading="loading" active :paragraph="{ rows: 6 }">
        <div class="agent-cards-grid">
          <Card
            v-for="agent in pagedAgentStatsList"
            :key="agent.agent_code"
            :bordered="false"
            class="agent-card"
            size="small"
          >
            <div class="mb-3 flex items-center justify-between">
              <span
                class="max-w-[70%] truncate text-lg font-bold"
                :title="agent.agent_name || agent.agent_code"
              >
                {{ agent.agent_name || agent.agent_code }}
              </span>
              <Tag
                :color="getIsRunning(agent) ? 'processing' : 'default'"
                class="status-tag"
              >
                <template v-if="getIsRunning(agent)" #icon>
                  <LoadingOutlined />
                </template>
                {{ getIsRunning(agent) ? '工作中' : '空闲' }}
              </Tag>
            </div>

            <div class="mb-2 flex items-baseline justify-between">
              <span class="text-sm text-muted-foreground">已执行生成任务</span>
              <div>
                <span class="text-3xl font-bold">
                  <CountTo
                    :end-value="getAgentJobCount(agent.agent_code)"
                    :decimals="0"
                    :duration="1"
                    :use-grouping="true"
                  />
                </span>
                <span class="ml-1 text-sm text-muted-foreground">个</span>
              </div>
            </div>

            <div class="mb-4 flex items-baseline justify-between">
              <span class="text-sm text-muted-foreground">总生成文章数量</span>
              <div>
                <span class="text-3xl font-bold">
                  <CountTo
                    :end-value="getContentCount(agent)"
                    :decimals="0"
                    :duration="1"
                    :use-grouping="true"
                  />
                </span>
                <span class="ml-1 text-sm text-muted-foreground">篇</span>
              </div>
            </div>

            <!-- 迷你趋势图 -->
            <div class="trend-chart">
              <div class="mb-1 text-xs text-muted-foreground">文章数</div>
              <svg
                class="w-full"
                viewBox="0 0 300 60"
                style="height: 75px"
                preserveAspectRatio="xMidYMid meet"
              >
                <defs>
                  <linearGradient
                    :id="`gradient-${agent.agent_code}`"
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop
                      offset="0%"
                      stop-color="hsl(var(--primary))"
                      stop-opacity="0.3"
                    />
                    <stop
                      offset="100%"
                      stop-color="hsl(var(--primary))"
                      stop-opacity="0.05"
                    />
                  </linearGradient>
                </defs>
                <polygon
                  v-if="getAgentTrendData(agent.agent_code).nodes.length > 0"
                  :points="`${getAgentTrendData(agent.agent_code).nodes[0]?.x || 15},45 ${getAgentTrendData(agent.agent_code).points} ${getAgentTrendData(agent.agent_code).nodes[getAgentTrendData(agent.agent_code).nodes.length - 1]?.x || 285},45`"
                  :fill="`url(#gradient-${agent.agent_code})`"
                />
                <polyline
                  :points="getAgentTrendData(agent.agent_code).points"
                  fill="none"
                  stroke="hsl(var(--primary))"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="1.5"
                />
                <template
                  v-for="(node, idx) in getAgentTrendData(agent.agent_code)
                    .nodes"
                  :key="idx"
                >
                  <circle
                    :cx="node.x"
                    :cy="node.y"
                    r="2"
                    fill="hsl(var(--primary))"
                  />
                  <text
                    :x="node.x"
                    :y="node.y - 3"
                    font-size="5"
                    fill="hsl(var(--primary))"
                    text-anchor="middle"
                  >
                    {{ node.count }}
                  </text>
                  <text
                    :x="node.x"
                    y="55"
                    font-size="4.5"
                    fill="currentColor"
                    text-anchor="middle"
                    class="text-muted-foreground"
                  >
                    {{ node.date }}
                  </text>
                </template>
              </svg>
            </div>
          </Card>

          <Empty
            v-if="agentStatsList.length === 0 && !loading"
            description="暂无 Agent 数据"
            class="col-span-full py-8"
          />
        </div>

        <!-- Agent 卡片分页 -->
        <div
          v-if="agentStatsList.length > 0"
          class="mt-4 flex items-center justify-end"
        >
          <Pagination
            :current="agentCardPagination.current"
            :page-size="agentCardPagination.pageSize"
            :page-size-options="['3', '6', '9']"
            :show-quick-jumper="true"
            :show-size-changer="true"
            :total="agentCardPagination.total"
            size="small"
            @change="handleAgentCardPageChange"
          />
        </div>
      </Skeleton>
    </div>
  </div>
</template>

<style scoped>
@keyframes float-particle {
  0%,
  100% {
    opacity: 0.6;
    transform: translateY(0);
  }

  50% {
    opacity: 0.3;
    transform: translateY(-20px);
  }
}

@keyframes scan {
  0% {
    top: 0;
  }

  50% {
    top: 100%;
  }

  100% {
    top: 0;
  }
}

.section-container {
  position: relative;
  margin-bottom: 1rem;
  overflow: hidden;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border) / 30%);
  border-radius: 12px;
}

.section-glow-border > div {
  position: absolute;
  background: linear-gradient(
    90deg,
    transparent,
    hsl(var(--primary) / 40%),
    transparent
  );
  opacity: 0;
  transition: opacity 0.3s;
}

.section-container:hover .section-glow-border > div {
  opacity: 1;
}

.glow-border-top,
.glow-border-bottom {
  right: 0;
  left: 0;
  height: 1px;
}

.glow-border-top {
  top: 0;
}

.glow-border-bottom {
  bottom: 0;
}

.glow-border-left,
.glow-border-right {
  top: 0;
  bottom: 0;
  width: 1px;
  background: linear-gradient(
    180deg,
    transparent,
    hsl(var(--primary) / 40%),
    transparent
  );
}

.glow-border-left {
  left: 0;
}

.glow-border-right {
  right: 0;
}

.section-bg-decoration {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}

.section-glow-orb {
  position: absolute;
  border-radius: 50%;
  opacity: 0.15;
  filter: blur(60px);
}

.orb-blue {
  top: -50px;
  right: -50px;
  width: 200px;
  height: 200px;
  background: hsl(var(--primary));
}

.orb-purple {
  bottom: -50px;
  left: -50px;
  width: 200px;
  height: 200px;
  background: #8b5cf6;
}

.orb-cyan {
  top: -30px;
  right: -30px;
  width: 150px;
  height: 150px;
  background: #06b6d4;
}

.orb-green {
  bottom: -30px;
  left: -30px;
  width: 150px;
  height: 150px;
  background: #22c55e;
}

.section-grid-lines {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(hsl(var(--border) / 10%) 1px, transparent 1px),
    linear-gradient(90deg, hsl(var(--border) / 10%) 1px, transparent 1px);
  background-size: 40px 40px;
  opacity: 0.3;
}

.section-corner {
  position: absolute;
  width: 20px;
  height: 20px;
  border-color: hsl(var(--primary) / 30%);
  border-style: solid;
  transition: all 0.3s;
}

.section-container:hover .section-corner {
  width: 30px;
  height: 30px;
  border-color: hsl(var(--primary));
}

.section-corner-tl {
  top: 0;
  left: 0;
  border-width: 2px 0 0 2px;
  border-radius: 12px 0 0;
}

.section-corner-tr {
  top: 0;
  right: 0;
  border-width: 2px 2px 0 0;
  border-radius: 0 12px 0 0;
}

.section-corner-bl {
  bottom: 0;
  left: 0;
  border-width: 0 0 2px 2px;
  border-radius: 0 0 0 12px;
}

.section-corner-br {
  right: 0;
  bottom: 0;
  border-width: 0 2px 2px 0;
  border-radius: 0 0 12px;
}

.section-header {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
}

.section-title {
  font-size: 1rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.glow-title {
  text-shadow: 0 0 20px hsl(var(--primary) / 30%);
}

.section-collapse-btn {
  transition: transform 0.3s;
}

.collapse-icon {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.section-content {
  position: relative;
  z-index: 1;
  padding: 0 1.5rem 1.5rem;
}

.dashboard-glass-card {
  background: hsl(var(--card) / 80%);
  border: 1px solid hsl(var(--border) / 30%);
  backdrop-filter: blur(10px);
}

.pie-chart-card {
  background: hsl(var(--card) / 80%);
  backdrop-filter: blur(10px);
}

.pie-chart-container {
  position: relative;
  height: 280px;
}

.table-scroll-container {
  position: relative;
}

/* AIGC 特有样式 */
.aigc-title {
  background: linear-gradient(135deg, #06b6d4, #22c55e);
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.data-particles {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.data-particle {
  position: absolute;
  width: 4px;
  height: 4px;
  background: hsl(var(--primary));
  border-radius: 50%;
  opacity: 0.6;
  animation: float-particle 3s infinite ease-in-out;
}

.data-particle.p1 {
  top: 20%;
  left: 10%;
  animation-delay: 0s;
}

.data-particle.p2 {
  top: 60%;
  left: 30%;
  animation-delay: 0.5s;
}

.data-particle.p3 {
  top: 40%;
  right: 20%;
  animation-delay: 1s;
}

.data-particle.p4 {
  bottom: 30%;
  left: 60%;
  animation-delay: 1.5s;
}

.data-particle.p5 {
  top: 80%;
  right: 40%;
  animation-delay: 2s;
}

.section-scan-line {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent,
    hsl(var(--primary)),
    transparent
  );
  opacity: 0.5;
  animation: scan 3s infinite;
}

.agent-cards-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
}

.agent-card {
  background: hsl(var(--card) / 60%);
  border: 1px solid hsl(var(--border) / 30%);
  backdrop-filter: blur(10px);
  transition: all 0.3s;
}

.agent-card:hover {
  border-color: hsl(var(--primary) / 50%);
  box-shadow: 0 8px 25px rgb(0 0 0 / 15%);
  transform: translateY(-2px);
}

.status-tag {
  font-size: 12px;
}

.trend-chart {
  padding: 0.5rem;
  background: hsl(var(--muted) / 30%);
  border-radius: 8px;
}

/* 共享样式（后续可抽离） */
</style>
