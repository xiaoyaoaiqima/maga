<!--
  多维度AI评论专家组主容器组件
  Compose all critic-related sub-components
-->
<script setup lang="ts">
import type { EchartsUIType } from '@vben/plugins/echarts';

import type {
  ActiveExperts,
  AgentPersonaHeatmapItem,
  CriticContentStats,
  CriticExpertStats,
  ScoreRange,
  ScoringExpertMeta,
  StatisticsExpertStats,
} from '../../types';

import { ref } from 'vue';

import { DownOutlined, RightOutlined } from '@ant-design/icons-vue';
import { Button, Card, Skeleton } from 'ant-design-vue';

import ContentRichnessScatter from './ContentRichnessScatter.vue';
import CriticExpertCards from './CriticExpertCards.vue';
import DiversityHeatmap from './DiversityHeatmap.vue';
import QualityRadarChart from './QualityRadarChart.vue';
import ScoringFlowVisualization from './ScoringFlowVisualization.vue';
import SecurityPlatformCards from './SecurityPlatformCards.vue';

// ==================== Props ====================

interface Props {
  /** Loading 状态 */
  loading?: boolean;
  /** 是否折叠 */
  collapsed?: boolean;
  /** 内容统计数据 */
  contentStats: CriticContentStats;
  /** 评论专家统计数据 */
  criticExpertStats: CriticExpertStats[];
  /** 评分专家元数据 */
  scoringExperts: ScoringExpertMeta[];
  /** 分数区间配置 */
  scoreRanges: ScoreRange[];
  /** 评分专家活跃状态 */
  activeExperts: ActiveExperts;
  /** 人群多样性热力图数据 */
  heatmapData: AgentPersonaHeatmapItem[];
  /** 统计学专家组统计 */
  statisticsStats: StatisticsExpertStats;
  /** 获取专家区间百分比的函数 */
  getExpertRangePercent: (rangeId: string, expertFunc: string) => number;
  /** 触发专家评分的函数 */
  onExpertClick: (expertFunc: string) => void;
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  collapsed: false,
});

// ==================== Emits ====================

const emit = defineEmits<{
  (e: 'toggle-collapse'): void;
}>();

// ==================== Refs ====================

const scoringExpertRadarChartRef = ref<EchartsUIType>();
const statisticsHeatmapChartRef = ref<EchartsUIType>();
const contentRichnessScatterChartRef = ref<EchartsUIType>();

// 暴露 ref 给父组件
defineExpose({
  scoringExpertRadarChartRef,
  statisticsHeatmapChartRef,
  contentRichnessScatterChartRef,
});

// ==================== Computed ====================

// 组装专家数据获取函数
function getCriticExpertData(expertCode: string) {
  const expert = props.criticExpertStats.find(
    (item) => item.expert_func === expertCode,
  );
  return {
    totalInput: expert?.total_input || 0,
    rejectedCount: expert?.rejected_count || 0,
  };
}
</script>

<template>
  <div class="section-container critic-section mt-4">
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

    <!-- Section Header -->
    <div class="section-header" @click="emit('toggle-collapse')">
      <span class="section-title glow-title critic-title">
        多维度AI Expert反馈组
      </span>
      <span class="section-collapse-btn">
        <RightOutlined v-if="collapsed" class="collapse-icon" />
        <DownOutlined v-else class="collapse-icon" />
      </span>
    </div>

    <!-- Section Content -->
    <div v-show="!collapsed" class="section-content">
      <!-- 顶部统计栏 -->
      <Skeleton :loading="loading" active :paragraph="{ rows: 1 }">
        <div class="critic-header-bar">
          <div class="critic-header-left">
            <Button type="primary" class="expert-group-btn">
              正负向专家组
            </Button>
          </div>
          <div class="critic-header-right">
            <div class="critic-summary-box">
              <span class="summary-label">总审核文章</span>
              <span class="summary-value">{{
                contentStats.total_input_count || 0
              }}</span>
            </div>
            <div class="critic-summary-box">
              <span class="summary-label">审核不通过数量</span>
              <span class="summary-value">{{
                contentStats.rejected_count || 0
              }}</span>
            </div>
          </div>
        </div>
      </Skeleton>

      <!-- 评论专家卡片 -->
      <Skeleton :loading="loading" active :paragraph="{ rows: 4 }">
        <CriticExpertCards
          :get-expert-data="getCriticExpertData"
          :loading="loading"
        />
      </Skeleton>

      <!-- 评分类专家组区块 -->
      <Skeleton :loading="loading" active :paragraph="{ rows: 1 }">
        <div class="scoring-expert-header-bar">
          <div class="scoring-expert-header-left">
            <Button type="primary" class="expert-group-btn">
              评分类专家组
            </Button>
          </div>
          <div class="scoring-expert-header-right">
            <div class="critic-summary-box">
              <span class="summary-label">总审核文章</span>
              <span class="summary-value">{{
                contentStats.total_input_count || 0
              }}</span>
            </div>
          </div>
        </div>
      </Skeleton>

      <!-- 专家组评分分值分布 & 文章六维评分结果 - 左右排列 -->
      <Card :bordered="false" class="scoring-flow-card">
        <!-- 统一标题 -->
        <div class="scoring-flow-header">
          <div class="scoring-flow-title">
            <span class="scoring-title-indicator"></span>
            <span>Expert组评分分值分布</span>
          </div>
        </div>

        <!-- 左右排列的容器 -->
        <div class="scoring-flow-visualization">
          <!-- 左侧：评分流程可视化 -->
          <div class="flow-left-section">
            <ScoringFlowVisualization
              :content-stats="contentStats"
              :scoring-experts="scoringExperts"
              :score-ranges="scoreRanges"
              :get-expert-range-percent="getExpertRangePercent"
              :active-experts="activeExperts"
              :loading="loading"
              @expert-click="onExpertClick"
            />
          </div>

          <!-- 右侧：雷达图 -->
          <div class="flow-radar-section">
            <QualityRadarChart
              :radar-chart-ref="{ value: scoringExpertRadarChartRef }"
              :scoring-experts="scoringExperts"
              :loading="loading"
            />
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
              <span class="summary-value">{{
                statisticsStats.total_reviewed_count || 0
              }}</span>
            </div>
          </div>
        </div>
      </Skeleton>

      <!-- 人群多样性热力图 -->
      <DiversityHeatmap
        :heatmap-chart-ref="{ value: statisticsHeatmapChartRef }"
        :heatmap-data="heatmapData"
        :stats="statisticsStats"
        :loading="loading"
      />

      <!-- 内容丰富度散点图 -->
      <ContentRichnessScatter
        :scatter-chart-ref="{ value: contentRichnessScatterChartRef }"
        :loading="loading"
      />

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

      <!-- 三方平台卡片 -->
      <SecurityPlatformCards :loading="loading" />
    </div>
  </div>
</template>

<style scoped>
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

.orb-violet {
  top: -50px;
  right: -50px;
  width: 200px;
  height: 200px;
  background: #8b5cf6;
}

.orb-rose {
  bottom: -50px;
  left: -50px;
  width: 200px;
  height: 200px;
  background: #ec4899;
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

/* ==================== Header ==================== */

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

.critic-title {
  background: linear-gradient(135deg, #8b5cf6, #ec4899);
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.section-collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  color: hsl(var(--muted-foreground));
  transition: all 0.2s;
}

.section-header:hover .section-collapse-btn {
  color: hsl(var(--primary));
}

.collapse-icon {
  font-size: 12px;
}

/* ==================== Content ==================== */

.section-content {
  position: relative;
  z-index: 1;
  padding: 0 1.5rem 1.5rem;
}

/* ==================== Header Bars ==================== */

.critic-header-bar,
.scoring-expert-header-bar,
.statistics-expert-header-bar,
.security-expert-header-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
  background: hsl(var(--muted) / 20%);
  border: 1px solid hsl(var(--border) / 20%);
  border-radius: 8px;
}

.critic-header-left,
.scoring-expert-header-left,
.statistics-expert-header-left,
.security-expert-header-left {
  display: flex;
  gap: 0.5rem;
}

.expert-group-btn {
  font-size: 0.875rem;
}

.critic-header-right,
.scoring-expert-header-right,
.security-expert-header-right {
  display: flex;
  gap: 1rem;
}

.critic-summary-box {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.summary-label {
  font-size: 0.75rem;
  color: hsl(var(--muted-foreground));
}

.summary-value {
  font-size: 1rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

/* ==================== 评分流程可视化容器样式 ==================== */

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

/* 左侧区域 - 评分流程可视化 */
.flow-left-section {
  display: flex;
  flex: 1 1 auto;
  max-width: 800px;
}

/* 右侧区域 - 雷达图 */
.flow-radar-section {
  z-index: 10;
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-width: 350px;
  max-width: 550px;
  overflow: visible;
}

/* ==================== Section 容器样式 ==================== */
</style>
