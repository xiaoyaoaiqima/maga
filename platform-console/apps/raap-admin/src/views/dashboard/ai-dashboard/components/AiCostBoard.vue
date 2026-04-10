<!-- AI算力成本看板 -->
<script setup lang="ts">
import type { JobCostItem } from '../types';

import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue';

import { EchartsUI, useEcharts } from '@vben/plugins/echarts';

import { Card, Col, Empty, Row, Skeleton, Table } from 'ant-design-vue';
// 导入 dayjs
import dayjs from 'dayjs';

import CountTo from '#/components/CountTo.vue';

import {
  aggregateAgentCostData,
  createAgentCostPieChartOption,
  createEmptyCostChartOption,
} from '../charts';
import { useChartTheme } from '../composables';
import { USD_TO_CNY_RATE } from '../constants';

// ==================== Props ====================

interface Props {
  agentCount: number;
  jobCount: number;
  jobCostData: JobCostItem[];
  loading?: boolean;
  totalCostValue: number;
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
});

// ==================== Emits ====================

const emit = defineEmits<{
  costTableMouseEnter: [];
  costTableMouseLeave: [];
}>();

// ==================== 懒加载状态 ====================

// 表格是否显示（懒加载：先显示饼图，延迟显示表格）
const showTable = ref(false);
let tableLoadTimer: null | ReturnType<typeof setTimeout> = null;

// ==================== 虚拟滚动状态 ====================

const VISIBLE_ROW_COUNT = 20; // 可见区域显示的行数
const ROW_HEIGHT = 54; // 每行高度（middle size 的 Table 大约 54px）
const visibleData = ref<JobCostItem[]>([]); // 当前可见的数据
const scrollTop = ref(0); // 滚动位置
const tableContainerRef = ref<HTMLElement>(); // 表格容器引用

// ==================== 图表 Ref ====================

const agentPieChartRef = ref();
const { renderEcharts: renderAgentPieChart } = useEcharts(agentPieChartRef);

// ==================== 图表更新 ====================

function updatePieChart() {
  const pieData = aggregateAgentCostData(props.jobCostData);

  if (pieData.length === 0) {
    renderAgentPieChart(createEmptyCostChartOption());
    return;
  }

  renderAgentPieChart(createAgentCostPieChartOption(pieData));
}

// 监听数据变化，自动更新图表
watch(
  () => props.jobCostData,
  () => {
    updatePieChart();
  },
  { deep: true },
);

// ==================== 主题变化监听 ====================

// 监听主题变化，重新渲染图表以应用新的主题颜色
useChartTheme([updatePieChart]);

// ==================== 虚拟滚动逻辑 ====================

/** 更新可见数据（根据滚动位置切片） */
function updateVisibleData() {
  if (!props.jobCostData || props.jobCostData.length === 0) {
    visibleData.value = [];
    return;
  }

  // 如果正在自动滚动，显示全部数据（不使用虚拟滚动）
  if (isAutoScrolling) {
    visibleData.value = props.jobCostData;
    return;
  }

  // 计算起始索引（根据滚动位置）
  const startIndex = Math.floor(scrollTop.value / ROW_HEIGHT);
  // 计算结束索引（多渲染 5 行缓冲区，避免滚动时白屏）
  const endIndex = Math.min(
    startIndex + VISIBLE_ROW_COUNT + 5,
    props.jobCostData.length,
  );

  // 切片数据
  visibleData.value = props.jobCostData.slice(startIndex, endIndex);
}

/** 处理表格滚动事件 */
function handleTableScroll(e: Event) {
  const target = e.target as HTMLElement;
  if (!target) return;

  // 如果正在自动滚动，不执行虚拟滚动逻辑（避免冲突）
  if (isAutoScrolling) return;

  scrollTop.value = target.scrollTop;
  updateVisibleData();
}

// ==================== 懒加载逻辑 ====================

/** 启动表格懒加载（延迟显示） */
function startTableLazyLoad() {
  // 清除旧的定时器
  if (tableLoadTimer) {
    clearTimeout(tableLoadTimer);
  }

  // 延迟 300ms 显示表格（先让饼图渲染）
  tableLoadTimer = setTimeout(() => {
    showTable.value = true;
    // 表格显示后，初始化可见数据
    updateVisibleData();
  }, 300);
}

/** 停止表格懒加载 */
function stopTableLazyLoad() {
  if (tableLoadTimer) {
    clearTimeout(tableLoadTimer);
    tableLoadTimer = null;
  }
}

// ==================== 表格列配置 ====================

const jobCostColumns = [
  {
    title: '生成任务',
    dataIndex: 'job_name',
    key: 'job_name',
    width: 200,
    ellipsis: true,
  },
  {
    title: 'Agent',
    dataIndex: 'agent_name',
    key: 'agent_name',
    width: 150,
    customRender: ({ record }: { record: JobCostItem }) =>
      record.agent_name || record.agent_code,
  },
  {
    title: '消耗资金',
    dataIndex: 'total_cost',
    key: 'total_cost',
    width: 100,
    align: 'right' as const,
    customRender: ({ record }: { record: JobCostItem }) => {
      let cost = Number(record.total_cost) || 0;
      if (record.currency !== 'CNY') {
        cost = cost * USD_TO_CNY_RATE;
      }
      return `${cost.toFixed(2)}元`;
    },
  },
  {
    title: '任务耗时',
    key: 'duration',
    width: 100,
    customRender: ({ record }: { record: JobCostItem }) => {
      if (!record.start_time || !record.end_time) return '-';
      const start = dayjs(record.start_time);
      const end = dayjs(record.end_time);
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
    },
  },
];

// ==================== 表格 Ref ====================

const jobCostTableRef = ref();
const isCostTableHovered = ref(false);
let autoScrollTimer: null | ReturnType<typeof setInterval> = null;
let isResetting = false; // 标记是否正在重置滚动位置
let isAutoScrolling = false; // 标记是否正在自动滚动（避免与虚拟滚动冲突）
const AUTO_SCROLL_INTERVAL = 1000;
const AUTO_SCROLL_STEP = 2;
const AUTO_SCROLL_RESET_DELAY = 100;

// ==================== 表格自动滚动（自下而上） ====================

function startTableAutoScroll() {
  stopTableAutoScroll(); // 先清除旧的定时器

  // 只有数据超过 VISIBLE_ROW_COUNT 时才启动自动滚动
  if (props.jobCostData.length <= VISIBLE_ROW_COUNT) return;

  // 等待 Table 渲染完成后启动滚动
  // 注意：由于懒加载延迟 300ms，这里需要更长的延迟 + nextTick
  setTimeout(() => {
    nextTick(() => {
      // 获取 Table 组件内部的滚动容器
      const tableEl =
        jobCostTableRef.value?.$el?.querySelector('.ant-table-body');
      if (!tableEl) {
        console.warn('[AiCostBoard] 未找到 Table 滚动容器');
        return;
      }

      console.warn('[AiCostBoard] 启动自动滚动');

      // 标记开始自动滚动
      isAutoScrolling = true;

      // 切换到显示全部数据
      updateVisibleData();

      // 初始化时先滚动到底部
      tableEl.scrollTop = tableEl.scrollHeight;

      autoScrollTimer = setInterval(() => {
        if (document.hidden || isCostTableHovered.value || isResetting) return;

        const scrollTop = tableEl.scrollTop;
        const scrollHeight = tableEl.scrollHeight;

        // 滚动到顶部时，立即重置到底部（不用 smooth，避免重复触发）
        if (scrollTop <= 0) {
          isResetting = true;
          tableEl.scrollTop = scrollHeight; // 立即重置到底部，不用动画
          setTimeout(() => {
            isResetting = false;
          }, AUTO_SCROLL_RESET_DELAY);
        } else {
          tableEl.scrollTop -= AUTO_SCROLL_STEP; // 向上滚动，不用 smooth，避免动画延迟
        }
      }, AUTO_SCROLL_INTERVAL);
    });
  }, 500); // 增加延迟到 500ms，确保懒加载完成后 Table 已渲染
}

function stopTableAutoScroll() {
  if (autoScrollTimer) {
    clearInterval(autoScrollTimer);
    autoScrollTimer = null;
    isAutoScrolling = false;
    // 恢复虚拟滚动
    updateVisibleData();
    console.warn('[AiCostBoard] 停止自动滚动');
  }
}

// ==================== 数据监听 ====================

// 数据变化时触发懒加载和自动滚动
watch(
  () => props.jobCostData,
  () => {
    // 启动表格懒加载（延迟显示表格）
    startTableLazyLoad();
    // 重启自动滚动
    startTableAutoScroll();
  },
  { deep: true },
);

// 组件挂载时启动懒加载和自动滚动
onMounted(() => {
  startTableLazyLoad();
  startTableAutoScroll();
  document.addEventListener('visibilitychange', handleVisibilityChange);
});

// 组件卸载时清除定时器
onUnmounted(() => {
  stopTableLazyLoad();
  stopTableAutoScroll();
  document.removeEventListener('visibilitychange', handleVisibilityChange);
});

// ==================== 事件处理 ====================

function handleCostTableMouseEnter() {
  isCostTableHovered.value = true;
  emit('costTableMouseEnter');
}

function handleCostTableMouseLeave() {
  isCostTableHovered.value = false;
  emit('costTableMouseLeave');
}

function handleVisibilityChange() {
  if (document.hidden) {
    stopTableAutoScroll();
  } else {
    startTableAutoScroll();
  }
}
</script>

<template>
  <div class="section-container ai-cost-section">
    <!-- 流光边框装饰 -->
    <div class="section-glow-border">
      <div class="glow-border-top"></div>
      <div class="glow-border-right"></div>
      <div class="glow-border-bottom"></div>
      <div class="glow-border-left"></div>
    </div>
    <!-- 背景装饰层 -->
    <div class="section-bg-decoration">
      <div class="section-glow-orb orb-blue"></div>
      <div class="section-glow-orb orb-purple"></div>
      <div class="section-grid-lines"></div>
    </div>
    <!-- 角落装饰 -->
    <div class="section-corner section-corner-tl"></div>
    <div class="section-corner section-corner-tr"></div>
    <div class="section-corner section-corner-bl"></div>
    <div class="section-corner section-corner-br"></div>

    <div class="section-header">
      <span class="section-title glow-title"> AI算力成本看板 </span>
    </div>

    <div class="section-content">
      <Row :gutter="16" type="flex" align="stretch">
        <!-- 左侧：总成本 + 扇形图 -->
        <Col :span="10" class="flex">
          <Card
            :bordered="false"
            class="dashboard-glass-card pie-chart-card flex-1"
          >
            <!-- 总成本统计 -->
            <div class="mb-4">
              <div class="mb-1 text-sm text-muted-foreground">
                已消耗资金额度（元）
              </div>
              <Skeleton :loading="loading" active :paragraph="{ rows: 1 }">
                <div class="mb-4 text-4xl font-bold">
                  {{ totalCostValue > 0 ? totalCostValue.toFixed(2) : '-' }}
                </div>
                <div class="mt-1 text-xs text-muted-foreground">
                  共
                  <CountTo
                    :end-value="agentCount"
                    :decimals="0"
                    :duration="1"
                    :use-grouping="false"
                  />
                  个 Agent，
                  <CountTo
                    :end-value="jobCount"
                    :decimals="0"
                    :duration="1"
                    :use-grouping="false"
                  />
                  个 生成任务
                </div>
              </Skeleton>
            </div>

            <!-- 扇形图（不放在 Skeleton 内，避免被卸载） -->
            <div class="pie-chart-container">
              <div
                v-if="loading"
                class="absolute inset-0 z-10 flex items-center justify-center bg-background/50"
              >
                <div class="text-muted-foreground">加载中...</div>
              </div>
              <EchartsUI ref="agentPieChartRef" height="100%" />
            </div>
          </Card>
        </Col>

        <!-- 右侧：成本明细表格（虚拟滚动 + 懒加载） -->
        <Col :span="14" class="flex">
          <Card
            :bordered="false"
            class="cost-detail-card flex-1"
            title="成本明细"
          >
            <Skeleton
              :loading="loading || !showTable"
              active
              :paragraph="{ rows: 8 }"
            >
              <div
                v-show="showTable"
                ref="tableContainerRef"
                class="table-scroll-container"
                @mouseenter="handleCostTableMouseEnter"
                @mouseleave="handleCostTableMouseLeave"
                @scroll="handleTableScroll"
              >
                <Table
                  ref="jobCostTableRef"
                  :columns="jobCostColumns"
                  :data-source="visibleData"
                  :pagination="false"
                  :row-key="(record: JobCostItem) => record.job_id"
                  :scroll="{ y: 340 }"
                  :scroll-x="1200"
                  bordered
                  size="middle"
                >
                  <template #emptyText>
                    <Empty description="暂无成本数据" />
                  </template>
                </Table>
              </div>
            </Skeleton>
          </Card>
        </Col>
      </Row>
    </div>
  </div>
</template>

<style scoped>
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

.glow-border-left {
  top: 0;
  bottom: 0;
  left: 0;
  width: 1px;
  background: linear-gradient(
    180deg,
    transparent,
    hsl(var(--primary) / 40%),
    transparent
  );
}

.glow-border-right {
  top: 0;
  right: 0;
  bottom: 0;
  width: 1px;
  background: linear-gradient(
    180deg,
    transparent,
    hsl(var(--primary) / 40%),
    transparent
  );
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
  cursor: pointer;
  user-select: none;
}

.section-title {
  font-size: 1rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.glow-title {
  text-shadow: 0 0 20px hsl(var(--primary) / 30%);
}

.section-content {
  position: relative;
  z-index: 1;
  padding: 0 1.5rem 1.5rem;
}

.pie-chart-card {
  background: hsl(var(--card) / 80%);
  backdrop-filter: blur(10px);
}

.cost-detail-card {
  background: hsl(var(--card) / 80%);
  backdrop-filter: blur(10px);
}

.dashboard-glass-card {
  background: hsl(var(--card) / 80%);
  border: 1px solid hsl(var(--border) / 30%);
  backdrop-filter: blur(10px);
}

.pie-chart-container {
  position: relative;
  height: 280px;
}

.table-scroll-container {
  position: relative;
}

/* 虚拟滚动提示样式 */
.virtual-scroll-hint {
  position: absolute;
  right: 8px;
  bottom: 8px;
  z-index: 10;
  padding: 4px 12px;
  font-size: 0.75rem;
  font-weight: 500;
  color: hsl(var(--primary-foreground));
  pointer-events: none;
  background: hsl(var(--primary) / 90%);
  border-radius: 12px;
  box-shadow: 0 2px 8px rgb(0 0 0 / 10%);
  backdrop-filter: blur(4px);
}
</style>
