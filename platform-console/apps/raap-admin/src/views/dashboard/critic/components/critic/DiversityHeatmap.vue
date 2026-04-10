<!--
  人群多样性热力图组件
  展示不同 Agent 和人设组合的内容数量分布
-->
<script setup lang="ts">
import type { EchartsUIType } from '@vben/plugins/echarts';

import { computed } from 'vue';

import { EchartsUI } from '@vben/plugins/echarts';

import { Card } from 'ant-design-vue';

// ==================== Types ====================

interface AgentPersonaHeatmapItem {
  agent_code: string;
  agent_name: null | string;
  persona_name: string;
  content_count: number;
}

interface StatisticsExpertStats {
  total_reviewed_count: number;
}

interface Props {
  /** 热力图 ref */
  heatmapChartRef: { value: EchartsUIType | undefined };
  /** 热力图数据 */
  heatmapData: AgentPersonaHeatmapItem[];
  /** 统计数据 */
  stats: StatisticsExpertStats;
  /** Loading 状态 */
  loading?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
});

// ==================== 计算属性 ====================

// 计算唯一的 Agent 数量
const uniqueAgentCount = computed(() => {
  if (props.heatmapData.length === 0) return 0;
  return new Set(props.heatmapData.map((d) => d.agent_code)).size;
});

// 计算唯一的人设数量
const uniquePersonaCount = computed(() => {
  if (props.heatmapData.length === 0) return 0;
  return new Set(props.heatmapData.map((d) => d.persona_name)).size;
});
</script>

<template>
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
      <EchartsUI :ref="heatmapChartRef" height="460px" width="100%" />
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
          <span class="stat-value">{{ uniqueAgentCount }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">总人设</span>
          <span class="stat-value">{{ uniquePersonaCount }}</span>
        </div>
      </div>
    </div>
  </Card>
</template>

<style scoped>
@keyframes orb-float {
  0%,
  100% {
    transform: translate(0, 0) scale(1);
  }

  50% {
    transform: translate(30px, -30px) scale(1.1);
  }
}

@keyframes scan-line {
  0% {
    left: -100%;
  }

  100% {
    left: 100%;
  }
}

@keyframes icon-pulse {
  0%,
  100% {
    opacity: 0.5;
    transform: scale(1);
  }

  50% {
    opacity: 0;
    transform: scale(1.3);
  }
}

@keyframes status-dot-pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.4;
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.diversity-heatmap-card {
  position: relative;
  margin-bottom: 1.5rem;
  overflow: hidden;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border) / 30%);
  border-radius: 12px;
}

/* ==================== 背景装饰 ==================== */

.heatmap-bg-decoration {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}

.heatmap-glow-orb {
  position: absolute;
  border-radius: 50%;
  opacity: 0.1;
  filter: blur(60px);
  animation: orb-float 8s ease-in-out infinite;
}

.orb-1 {
  top: -30px;
  left: -30px;
  width: 150px;
  height: 150px;
  background: #3b82f6;
  animation-delay: 0s;
}

.orb-2 {
  top: 50%;
  right: -50px;
  width: 200px;
  height: 200px;
  background: #8b5cf6;
  animation-delay: 2s;
}

.orb-3 {
  bottom: -30px;
  left: 30%;
  width: 180px;
  height: 180px;
  background: #06b6d4;
  animation-delay: 4s;
}

.heatmap-grid-lines {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(hsl(var(--border) / 8%) 1px, transparent 1px),
    linear-gradient(90deg, hsl(var(--border) / 8%) 1px, transparent 1px);
  background-size: 30px 30px;
  opacity: 0.5;
}

/* 扫描线动画 */
.heatmap-scan-line {
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent,
    hsl(var(--primary) / 50%),
    transparent
  );
  animation: scan-line 4s linear infinite;
}

/* ==================== 标题区域 ==================== */

.heatmap-header {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid hsl(var(--border) / 20%);
}

.heatmap-title-wrapper {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

.heatmap-title-icon {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  color: hsl(var(--primary));
}

.heatmap-title-icon svg {
  width: 20px;
  height: 20px;
}

.icon-pulse {
  position: absolute;
  inset: 0;
  background: hsl(var(--primary) / 20%);
  border-radius: 50%;
  animation: icon-pulse 2s ease-in-out infinite;
}

.heatmap-title-text {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.title-main {
  font-size: 1rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.heatmap-status-badge {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  padding: 0.25rem 0.75rem;
  font-size: 0.75rem;
  background: hsl(var(--primary) / 10%);
  border: 1px solid hsl(var(--primary) / 30%);
  border-radius: 20px;
}

.status-dot {
  width: 6px;
  height: 6px;
  background: #22c55e;
  border-radius: 50%;
  animation: status-dot-pulse 2s ease-in-out infinite;
}

.status-text {
  font-weight: 600;
  color: hsl(var(--primary));
}

/* ==================== 图表区域 ==================== */

.heatmap-chart-container {
  position: relative;
  padding: 1.5rem;
}

.heatmap-corner {
  position: absolute;
  width: 16px;
  height: 16px;
  pointer-events: none;
  border-color: hsl(var(--primary) / 40%);
  border-style: solid;
}

.corner-tl {
  top: 0;
  left: 0;
  border-width: 2px 0 0 2px;
  border-radius: 12px 0 0;
}

.corner-tr {
  top: 0;
  right: 0;
  border-width: 2px 2px 0 0;
  border-radius: 0 12px 0 0;
}

.corner-bl {
  bottom: 0;
  left: 0;
  border-width: 0 0 2px 2px;
  border-radius: 0 0 0 12px;
}

.corner-br {
  right: 0;
  bottom: 0;
  border-width: 0 2px 2px 0;
  border-radius: 0 0 12px;
}

/* 加载状态 */
.heatmap-loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  align-items: center;
  justify-content: center;
  background: hsl(var(--card) / 80%);
  backdrop-filter: blur(4px);
}

.loading-spinner {
  display: flex;
  gap: 0.5rem;
}

.spinner-ring {
  width: 40px;
  height: 40px;
  border: 3px solid hsl(var(--primary) / 20%);
  border-top-color: hsl(var(--primary));
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

.spinner-ring:nth-child(2) {
  animation-delay: 0.15s;
}

.spinner-ring:nth-child(3) {
  animation-delay: 0.3s;
}

.loading-text {
  font-size: 0.875rem;
  color: hsl(var(--muted-foreground));
}

/* ==================== 自定义图例 ==================== */

.heatmap-custom-legend {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  border-top: 1px solid hsl(var(--border) / 20%);
}

.legend-scale {
  flex: 1;
}

.scale-bar {
  height: 8px;
  margin-bottom: 0.5rem;
  background: linear-gradient(
    90deg,
    hsl(var(--muted) / 30%),
    #22c55e,
    #fbbf24,
    #ef4444
  );
  border-radius: 4px;
}

.scale-labels {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: hsl(var(--muted-foreground));
}

.legend-stats {
  display: flex;
  gap: 2rem;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.stat-label {
  font-size: 0.75rem;
  color: hsl(var(--muted-foreground));
}

.stat-value {
  font-size: 1.125rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

/* ==================== 卡片基础样式 ==================== */
</style>
