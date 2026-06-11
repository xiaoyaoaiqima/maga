<!--
  内容丰富度散点图组件
  展示内容在六个维度上的评分分布
-->
<script setup lang="ts">
// @ts-nocheck
import type { EchartsUIType } from '@vben/plugins/echarts';

import { EchartsUI } from '@vben/plugins/echarts';

import { Card } from 'ant-design-vue';

// ==================== Types ====================

interface Props {
  /** 散点图 ref */
  scatterChartRef: { value: EchartsUIType | undefined };
  /** Loading 状态 */
  loading?: boolean;
}

withDefaults(defineProps<Props>(), {
  loading: false,
});

// 六个维度的图例配置
const DIMENSIONS = [
  { name: '营销说服性', color: '#3b82f6', shadow: 'rgb(59 130 246 / 80%)' },
  { name: '文章优雅性', color: '#10b981', shadow: 'rgb(16 185 129 / 80%)' },
  { name: '语法修饰', color: '#8b5cf6', shadow: 'rgb(139 92 246 / 80%)' },
  { name: '品牌匹配', color: '#f59e0b', shadow: 'rgb(245 158 11 / 80%)' },
  { name: '创造力', color: '#06b6d4', shadow: 'rgb(6 182 212 / 80%)' },
  { name: '人设真实感', color: '#ec4899', shadow: 'rgb(236 72 153 / 80%)' },
];
</script>

<template>
  <Card :bordered="false" class="scatter-cool-card">
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
        <div
          v-for="dim in DIMENSIONS"
          :key="dim.name"
          class="scatter-legend-item"
        >
          <span
            class="scatter-legend-dot"
            :style="{
              background: dim.color,
              boxShadow: `0 0 8px ${dim.shadow}`,
            }"
          ></span>
          {{ dim.name }}
        </div>
      </div>
    </div>

    <!-- 图表区域 -->
    <div class="scatter-chart-container">
      <div v-if="loading" class="scatter-loading-overlay">
        <div class="scatter-loading-text">Loading Visualization...</div>
      </div>
      <EchartsUI :ref="scatterChartRef" height="360px" width="100%" />
    </div>
  </Card>
</template>

<style scoped>
@keyframes orb-float {
  0%,
  100% {
    transform: translate(0, 0) scale(1);
  }

  33% {
    transform: translate(30px, -30px) scale(1.1);
  }

  66% {
    transform: translate(-20px, 20px) scale(0.9);
  }
}

@keyframes scan-line {
  0% {
    top: -50%;
  }

  100% {
    top: 150%;
  }
}

@keyframes particle-float {
  0% {
    opacity: 0;
    transform: translate(0, 0);
  }

  10% {
    opacity: 0.6;
  }

  90% {
    opacity: 0.6;
  }

  100% {
    opacity: 0;
    transform: translate(var(--tx, 100px), var(--ty, -100px));
  }
}

@keyframes border-flow {
  0% {
    transform: translateX(-100%);
  }

  100% {
    transform: translateX(100%);
  }
}

.scatter-cool-card {
  position: relative;
  margin-top: 1.5rem;
  overflow: hidden;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border) / 30%);
  border-radius: 12px;
}

/* ==================== 背景装饰 ==================== */

.scatter-bg-decoration {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}

.scatter-glow-orb {
  position: absolute;
  border-radius: 50%;
  opacity: 0.08;
  filter: blur(80px);
  animation: orb-float 10s ease-in-out infinite;
}

.orb-1 {
  top: -50px;
  right: -50px;
  width: 250px;
  height: 250px;
  background: linear-gradient(135deg, #3b82f6, #8b5cf6);
  animation-delay: 0s;
}

.orb-2 {
  bottom: -80px;
  left: -50px;
  width: 300px;
  height: 300px;
  background: linear-gradient(135deg, #10b981, #06b6d4);
  animation-delay: 3s;
}

.orb-3 {
  top: 50%;
  left: 50%;
  width: 200px;
  height: 200px;
  background: linear-gradient(135deg, #f59e0b, #ec4899);
  transform: translate(-50%, -50%);
  animation-delay: 6s;
}

.scatter-grid-lines {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(hsl(var(--border) / 6%) 1px, transparent 1px),
    linear-gradient(90deg, hsl(var(--border) / 6%) 1px, transparent 1px);
  background-size: 40px 40px;
  opacity: 0.6;
}

/* 扫描线动画 */
.scatter-scan-line {
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent,
    hsl(var(--primary) / 30%),
    transparent
  );
  transform: rotate(45deg);
  animation: scan-line 8s linear infinite;
}

/* 流动粒子 */
.scatter-particles {
  position: absolute;
  inset: 0;
}

.particle {
  position: absolute;
  width: 4px;
  height: 4px;
  background: hsl(var(--primary));
  border-radius: 50%;
  opacity: 0.6;
  animation: particle-float 15s linear infinite;
}

.particle.p1 {
  top: 20%;
  left: 10%;
  animation-delay: 0s;
}

.particle.p2 {
  top: 60%;
  left: 80%;
  animation-delay: 3s;
}

.particle.p3 {
  top: 80%;
  left: 30%;
  animation-delay: 6s;
}

.particle.p4 {
  top: 30%;
  left: 70%;
  animation-delay: 9s;
}

.particle.p5 {
  top: 50%;
  left: 50%;
  animation-delay: 12s;
}

/* ==================== 流光边框 ==================== */

.scatter-border-glow {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.scatter-border-glow > div {
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

.scatter-cool-card:hover .scatter-border-glow > div {
  opacity: 1;
}

.scatter-border-top,
.scatter-border-bottom {
  right: 0;
  left: 0;
  height: 1px;
}

.scatter-border-top {
  top: 0;
  animation: border-flow 3s linear infinite;
}

.scatter-border-bottom {
  bottom: 0;
  animation: border-flow 3s linear infinite 1.5s;
}

.scatter-border-left,
.scatter-border-right {
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

.scatter-border-left {
  left: 0;
}

.scatter-border-right {
  right: 0;
}

/* ==================== 角落装饰 ==================== */

.scatter-corner {
  position: absolute;
  width: 20px;
  height: 20px;
  border-color: hsl(var(--primary) / 30%);
  border-style: solid;
  transition: all 0.3s;
}

.scatter-cool-card:hover .scatter-corner {
  width: 30px;
  height: 30px;
  border-color: hsl(var(--primary));
}

.scatter-corner-tl {
  top: 0;
  left: 0;
  border-width: 2px 0 0 2px;
  border-radius: 12px 0 0;
}

.scatter-corner-tr {
  top: 0;
  right: 0;
  border-width: 2px 2px 0 0;
  border-radius: 0 12px 0 0;
}

.scatter-corner-bl {
  bottom: 0;
  left: 0;
  border-width: 0 0 2px 2px;
  border-radius: 0 0 0 12px;
}

.scatter-corner-br {
  right: 0;
  bottom: 0;
  border-width: 0 2px 2px 0;
  border-radius: 0 0 12px;
}

/* ==================== 标题栏 ==================== */

.scatter-card-header {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid hsl(var(--border) / 20%);
}

.scatter-card-title {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  font-size: 1rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.scatter-title-indicator {
  width: 4px;
  height: 18px;
  background: linear-gradient(180deg, #3b82f6, #8b5cf6);
  border-radius: 2px;
}

/* 图例 */
.scatter-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
}

.scatter-legend-item {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  font-size: 0.75rem;
  color: hsl(var(--muted-foreground));
}

.scatter-legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

/* ==================== 图表区域 ==================== */

.scatter-chart-container {
  position: relative;
  padding: 1.5rem;
}

.scatter-loading-overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  background: hsl(var(--card) / 80%);
  backdrop-filter: blur(4px);
}

.scatter-loading-text {
  font-size: 0.875rem;
  color: hsl(var(--muted-foreground));
}

/* ==================== 卡片基础样式 ==================== */
</style>
