<!--
  质量六维度雷达图组件
  带旋转光圈、脉冲波纹、动态维度连线的炫酷雷达图
-->
<script setup lang="ts">
import type { EchartsUIType } from '@vben/plugins/echarts';

import { computed } from 'vue';

import { EchartsUI } from '@vben/plugins/echarts';

// ==================== Types ====================

interface ScoringExpertMeta {
  expert_func: string;
  expert_name: string;
  expert_code: string;
  icon: string;
  color: string;
  bgColor: string;
  tooltip: string;
}

interface Props {
  /** 雷达图 ref */
  radarChartRef: { value: EchartsUIType | undefined };
  /** 评分专家列表 */
  scoringExperts: ScoringExpertMeta[];
  /** Loading 状态 */
  loading?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
});

// ==================== 计算属性 ====================

// 雷达图 SVG 顶点位置计算（用于绘制维度线）
function getRadarSvgVertexPosition(index: number, total: number) {
  const centerX = 150;
  const centerY = 150;
  const radius = 120;

  // 从 -90 度（12点方向）开始，顺时针分布
  const startAngle = -90;
  const angleStep = 360 / total;
  const angle = ((startAngle + index * angleStep) * Math.PI) / 180;

  return {
    x: centerX + radius * Math.cos(angle),
    y: centerY + radius * Math.sin(angle),
  };
}

// 维度线的渐变 ID
const dimensionGradientIds = computed(() => {
  return props.scoringExperts.map((_, index) => `dimLineGrad${index + 1}`);
});
</script>

<template>
  <!-- 雷达图容器（无 Card 包裹，由父组件提供） -->
  <div class="flow-radar-section">
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
              <stop offset="0%" stop-color="#3b82f6" stop-opacity="1" />
              <stop offset="25%" stop-color="#8b5cf6" stop-opacity="0.8" />
              <stop offset="50%" stop-color="#06b6d4" stop-opacity="0.3" />
              <stop offset="75%" stop-color="#10b981" stop-opacity="0.8" />
              <stop offset="100%" stop-color="#3b82f6" stop-opacity="1" />
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

      <!-- 动态维度指示器连线 -->
      <svg class="radar-dimension-lines" viewBox="0 0 300 300">
        <defs>
          <!-- 动态生成渐变定义 -->
          <linearGradient
            v-for="(expert, index) in scoringExperts"
            :id="dimensionGradientIds[index]"
            :key="`grad-${expert.expert_func}`"
            x1="0%"
            y1="0%"
            x2="100%"
            y2="0%"
          >
            <stop offset="0%" :stop-color="expert.color" stop-opacity="0" />
            <stop offset="50%" :stop-color="expert.color" stop-opacity="0.8" />
            <stop offset="100%" :stop-color="expert.color" stop-opacity="0" />
          </linearGradient>
          <filter id="dimGlow">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <!-- 从中心向外辐射的脉冲线 -->
        <line
          v-for="(expert, index) in scoringExperts"
          :key="`line-${expert.expert_func}`"
          x1="150"
          y1="150"
          :x2="getRadarSvgVertexPosition(index, scoringExperts.length).x"
          :y2="getRadarSvgVertexPosition(index, scoringExperts.length).y"
          class="radar-pulse-line"
          :style="`stroke: url(#${dimensionGradientIds[index]})`"
        />

        <!-- 顶点的脉冲圆点 -->
        <circle
          v-for="(expert, index) in scoringExperts"
          :key="`dot-${expert.expert_func}`"
          :cx="getRadarSvgVertexPosition(index, scoringExperts.length).x"
          :cy="getRadarSvgVertexPosition(index, scoringExperts.length).y"
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
          class="bg-background-half-opacity absolute inset-0 z-10 flex items-center justify-center"
        >
          <div class="text-muted-foreground">加载中...</div>
        </div>
        <EchartsUI :ref="radarChartRef" height="380px" width="100%" />
      </div>
    </div>
  </div>
</template>

<style scoped>
@keyframes outer-glow {
  0%,
  100% {
    opacity: 0.5;
    transform: scale(1);
  }

  50% {
    opacity: 1;
    transform: scale(1.05);
  }
}

@keyframes rotate-ring {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

@keyframes pulse-line {
  0%,
  100% {
    opacity: 0.3;
  }

  50% {
    opacity: 1;
  }
}

@keyframes vertex-pulse {
  0%,
  100% {
    r: 6;
    opacity: 1;
  }

  50% {
    r: 10;
    opacity: 0.6;
  }
}

@keyframes pulse-wave {
  0% {
    opacity: 0.8;
    transform: scale(0.5);
  }

  100% {
    opacity: 0;
    transform: scale(1.5);
  }
}

.scoring-flow-card {
  position: relative;
  overflow: hidden;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border) / 30%);
  border-radius: 12px;
}

.scoring-flow-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid hsl(var(--border) / 20%);
}

.scoring-flow-title {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  font-size: 1rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.scoring-title-indicator {
  width: 4px;
  height: 18px;
  background: linear-gradient(180deg, #3b82f6, #8b5cf6);
  border-radius: 2px;
}

/* ==================== 雷达图区域 ==================== */

.flow-radar-section {
  display: flex;
  justify-content: center;
  padding: 2rem 1.5rem;
}

.radar-chart-wrapper {
  position: relative;
  width: 100%;
  max-width: 500px;
  aspect-ratio: 1;
}

/* 外层发光光环 */
.radar-outer-glow {
  position: absolute;
  inset: 0;
  background: radial-gradient(
    circle,
    hsl(var(--primary) / 10%) 0%,
    transparent 70%
  );
  border-radius: 50%;
  animation: outer-glow 4s ease-in-out infinite;
}

/* 旋转光圈 */
.radar-rotating-ring {
  position: absolute;
  inset: -20px;
  animation: rotate-ring 20s linear infinite;
}

.rotating-ring-svg {
  width: 100%;
  height: 100%;
}

/* 维度连线 SVG */
.radar-dimension-lines {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.radar-pulse-line {
  stroke-width: 2;
  stroke-linecap: round;
  animation: pulse-line 2s ease-in-out infinite;
}

.radar-vertex-pulse {
  animation: vertex-pulse 2s ease-in-out infinite;
}

/* 脉冲波纹 */
.radar-pulse-waves {
  position: absolute;
  inset: 50%;
  width: 200px;
  height: 200px;
  pointer-events: none;
  transform: translate(-50%, -50%);
}

.pulse-wave {
  position: absolute;
  inset: 0;
  border: 2px solid hsl(var(--primary) / 30%);
  border-radius: 50%;
  opacity: 0;
}

.pulse-wave-1 {
  animation: pulse-wave 3s ease-out infinite;
}

.pulse-wave-2 {
  animation: pulse-wave 3s ease-out infinite 1s;
}

.pulse-wave-3 {
  animation: pulse-wave 3s ease-out infinite 2s;
}

/* 雷达图容器 */
.radar-chart-container {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
}

.absolute {
  position: absolute;
}

.inset-0 {
  inset: 0;
}

.z-10 {
  z-index: 10;
}

.flex {
  display: flex;
}

.items-center {
  align-items: center;
}

.justify-center {
  justify-content: center;
}

.bg-background-half-opacity {
  background-color: hsl(var(--background) / 50%);
}

.text-muted-foreground {
  color: hsl(var(--muted-foreground));
}

/* ==================== 卡片样式 ==================== */
</style>
