<script setup lang="ts">
/**
 * ConversionFunnel - 内容转化漏斗图组件
 * 展示从输入到最终输出的转化流程，带有流动感动画效果
 */

import { computed } from 'vue';

import { Tooltip } from 'ant-design-vue';

// ==================== 类型定义 ====================
interface FunnelStage {
  id: string;
  label: string;
  count: number;
  percentage: number;
  icon?: string;
  color: string;
  description?: string;
}

interface FunnelProps {
  data: FunnelStage[];
  title?: string;
  height?: string;
}

// ==================== Props ====================
const props = withDefaults(defineProps<FunnelProps>(), {
  title: '',
  height: '200px',
});

// ==================== 计算属性 ====================
// 计算每个阶段的宽度比例（基于第一个阶段的count，使递减更明显）
const stageWidths = computed(() => {
  const result: number[] = [];
  const baseCount = props.data[0]?.count || 1;
  for (let i = 0; i < props.data.length; i++) {
    const currentCount = props.data[i]?.count ?? 0;
    const width = (currentCount / baseCount) * 100;
    result.push(Math.max(width, 10)); // 最小宽度10%，使递减更明显
  }
  return result;
});

// 计算漏斗段的样式
const getStageStyle = (index: number) => {
  const stage = props.data[index];
  if (!stage) {
    return {};
  }

  const width = stageWidths.value[index] || 100;

  // 高度基于第一个阶段的count递减，使递减更明显
  const baseCount = props.data[0]?.count || 1;
  const baseHeight = 160;
  const heightRatio = stage.count / baseCount;
  const height = Math.max(baseHeight * heightRatio, 30); // 降低最小高度，使递减更明显

  return {
    '--stage-color': stage.color,
    '--stage-width': `${width}%`,
    '--stage-height': `${height}px`,
  };
};
</script>

<template>
  <div class="conversion-funnel-container">
    <!-- 标题 -->
    <div v-if="title" class="funnel-title">
      <span>{{ title }}</span>
      <div class="title-decoration"></div>
    </div>

    <!-- 漏斗图主体 -->
    <div class="funnel-wrapper">
      <!-- 连接线背景 -->
      <div class="flow-connections">
        <div
          v-for="(stage, index) in data"
          :key="`conn-${index}`"
          v-show="index < data.length - 1"
          class="connection-line"
          :style="{
            background: `linear-gradient(90deg, ${stage.color}33, ${data[index + 1]?.color || stage.color}33)`,
          }"
        ></div>
      </div>

      <!-- 阶段卡片 -->
      <div class="funnel-stages">
        <template v-for="(stage, index) in data" :key="stage.id">
          <!-- 块 -->
          <div class="funnel-stage" :style="getStageStyle(index)">
            <Tooltip :title="stage.description || stage.label">
              <div class="stage-content">
                <!-- 图标 -->
                <div v-if="stage.icon" class="stage-icon">{{ stage.icon }}</div>

                <!-- 标签 -->
                <div class="stage-label">{{ stage.label }}</div>

                <!-- 数量 -->
                <div class="stage-count">
                  {{ stage.count.toLocaleString() }} 篇
                </div>
              </div>
            </Tooltip>
          </div>

          <!-- 转化率（相邻块之间） -->
          <div
            v-if="index < data.length - 1"
            class="conversion-indicator"
            :style="{
              '--from-color': stage.color,
              '--to-color': data[index + 1]?.color,
            }"
          >
            <!-- 箭头容器 -->
            <div class="conversion-arrow-wrapper">
              <svg
                class="conversion-arrow-svg"
                viewBox="0 0 64 32"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <defs>
                  <linearGradient
                    :id="`arrow-gradient-${index}`"
                    x1="0%"
                    y1="0%"
                    x2="100%"
                    y2="0%"
                  >
                    <stop offset="0%" :stop-color="stage.color" />
                    <stop offset="100%" :stop-color="data[index + 1]?.color" />
                  </linearGradient>
                </defs>
                <!-- 箭头杆 -->
                <rect
                  x="2"
                  y="12"
                  width="44"
                  height="8"
                  rx="4"
                  :fill="`url(#arrow-gradient-${index})`"
                  class="arrow-shaft"
                />
                <!-- 箭头头部 -->
                <path
                  d="M56 6L62 16L56 26"
                  :stroke="`url(#arrow-gradient-${index})`"
                  stroke-width="5"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  class="arrow-head"
                />
              </svg>
            </div>
            <!-- 转化率徽章 -->
            <div class="conversion-badge">
              <span class="badge-value">{{
                stage.count === 0
                  ? '0%'
                  : `${(
                      ((data[index + 1]?.count ?? 0) / stage.count) *
                      100
                    ).toFixed(1)}%`
              }}</span>
            </div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
@keyframes pulse-line {
  0%,
  100% {
    opacity: 0.3;
  }

  50% {
    opacity: 0.6;
  }
}

/* 箭头动画 */
@keyframes arrow-pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.7;
  }
}

@keyframes arrow-head-pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.85;
  }
}

/* ==================== 减少动画 ==================== */
@media (prefers-reduced-motion: reduce) {
  .connection-line,
  .funnel-stage,
  .stage-content {
    transition: none !important;
    animation: none !important;
  }
}

/* ==================== 响应式 ==================== */
@media (max-width: 768px) {
  .funnel-stages {
    flex-direction: column;
    gap: 16px;
  }

  .funnel-stage {
    max-width: 100%;
  }

  .flow-connections {
    display: none;
  }

  .conversion-indicator {
    flex-direction: row;
    gap: 8px;
  }
}

/* 减少动画偏好 */
@media (prefers-reduced-motion: reduce) {
  .arrow-shaft,
  .arrow-head,
  .conversion-badge {
    transition: none !important;
    animation: none !important;
  }
}

.conversion-funnel-container {
  position: relative;
  width: 100%;
  padding: 16px;
  overflow: hidden;
  background: hsl(var(--gradient-bg));
  border-radius: 12px;
}

/* ==================== 标题 ==================== */
.funnel-title {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 20px;
  font-size: 16px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.title-decoration {
  flex: 1;
  height: 2px;
  background: linear-gradient(90deg, hsl(var(--primary)) 0%, transparent 100%);
}

/* ==================== 漏斗包装器 ==================== */
.funnel-wrapper {
  position: relative;
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  /* stylelint-disable-next-line declaration-property-value-no-unknown */
  min-height: v-bind(height);
  padding: 20px 0;
}

/* ==================== 连接线 ==================== */
.flow-connections {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
}

.connection-line {
  position: absolute;
  top: 50%;
  height: 2px;
  opacity: 0.4;
  transform: translateY(-50%);
}

/* ==================== 阶段卡片 ==================== */
.funnel-stages {
  position: relative;
  z-index: 10;
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: center;
  width: 100%;
}

.funnel-stage {
  position: relative;
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  max-width: var(--stage-width, 100%);
  transition: all 0.3s ease-out;
}

.funnel-stage:hover {
  transform: translateY(-4px);
}

.funnel-stage:hover .stage-content {
  box-shadow:
    0 8px 24px var(--stage-color),
    0 0 0 2px var(--stage-color);
}

.stage-content {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-width: 80px;
  height: var(--stage-height, 100%);
  min-height: 120px;
  padding: 8px 6px;
  overflow: hidden;
  cursor: pointer;
  background: linear-gradient(
    135deg,
    hsl(var(--card-background)) 0%,
    hsl(var(--card-background)) 50%,
    var(--stage-color) 100%
  );
  background-position: 0% 0%;
  background-size: 200% 200%;
  border: 1px solid var(--stage-color);
  border-radius: 12px;
  transition: all 0.25s ease-out;
}

.stage-content::before {
  position: absolute;
  inset: 0;
  content: '';
  background: radial-gradient(
    circle at var(--mouse-x, 50%) var(--mouse-y, 50%),
    var(--stage-color) 0%,
    transparent 50%
  );
  opacity: 0;
  transition: opacity 0.25s ease;
}

.funnel-stage:hover .stage-content::before {
  opacity: 0.15;
}

/* ==================== 阶段内容 ==================== */
.stage-icon {
  margin-bottom: 2px;
  font-size: 16px;
  line-height: 1;
}

.stage-label {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
  font-weight: 600;
  color: hsl(var(--muted-foreground));
  text-align: center;
  white-space: nowrap;
}

.stage-count {
  font-size: 16px;
  font-weight: 700;
  line-height: 1.2;
  color: hsl(var(--foreground));
}

/* ==================== 转化率指示器 ==================== */
.conversion-indicator {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  justify-content: center;
  padding: 4px 8px;
}

/* 箭头容器 */
.conversion-arrow-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.conversion-arrow-svg {
  width: 64px;
  height: 32px;
  filter: drop-shadow(0 2px 4px hsl(var(--foreground) / 10%));
}

/* 箭头杆动画 */
.arrow-shaft {
  animation: arrow-pulse 2s ease-in-out infinite;
}

/* 箭头头部动画 */
.arrow-head {
  animation: arrow-head-pulse 2s ease-in-out infinite 0.3s;
}

/* 转化率徽章 */
.conversion-badge {
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
  padding: 6px 12px;
  background: hsl(var(--card-background));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  box-shadow:
    0 2px 8px hsl(var(--foreground) / 5%),
    inset 0 1px 0 hsl(var(--foreground) / 5%);
  transition: all 0.3s ease;
}

.conversion-badge:hover {
  border-color: var(--from-color);
  box-shadow:
    0 4px 12px hsl(var(--foreground) / 10%),
    0 0 0 2px var(--from-color) / 0.2;
  transform: translateY(-2px);
}

.badge-label {
  font-size: 10px;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.badge-value {
  font-size: 16px;
  font-weight: 700;
  line-height: 1;
  color: hsl(var(--primary));
}

/* ==================== 容器 ==================== */
</style>
