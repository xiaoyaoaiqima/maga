<!--
  评分流程可视化组件
  展示从文章池 -> 专家评分 -> 分数分布的完整流程（水平布局）
-->
<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue';
import { Tooltip } from 'ant-design-vue';

import CountTo from '#/components/CountTo.vue';

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

interface ScoreRange {
  id: string;
  label: string;
  minScore: number;
  maxScore: number;
}

interface CriticContentStats {
  pending_count: number;
  total_input_count: number;
  rejected_count: number;
  rejected_rate: number;
}

interface Props {
  /** 内容统计数据 */
  contentStats: CriticContentStats;
  /** 评分专家列表 */
  scoringExperts: ScoringExpertMeta[];
  /** 分数区间配置 */
  scoreRanges: ScoreRange[];
  /** 获取专家区间百分比的函数 */
  getExpertRangePercent: (rangeId: string, expertFunc: string) => number;
  /** 当前激活的专家 */
  activeExperts: Record<string, boolean>;
  /** Loading 状态 */
  loading?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  activeExperts: () => ({}),
});

// ==================== Emits ====================

const emit = defineEmits<{
  (e: 'expert-click', expertFunc: string): void;
}>();

// ==================== Methods ====================

function triggerExpertScore(expertFunc: string) {
  emit('expert-click', expertFunc);
}
</script>

<template>
  <div class="scoring-flow-horizontal">
    <!-- 区域1: 左侧待评分文章池 -->
    <div class="flow-article-pool">
      <div class="pool-glow"></div>
      <div class="pool-content">
        <div class="pool-icon">📄</div>
        <div class="pool-label">待评分文章库</div>
        <div class="pool-value">
          <CountTo
            :end-value="contentStats.pending_count || 0"
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

    <!-- 连接线: 文章池 -> 专家 -->
    <svg
      class="connection-svg-left"
      viewBox="0 0 80 200"
      preserveAspectRatio="none"
    >
      <defs>
        <linearGradient id="flowGradLeft" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="hsl(var(--primary) / 60%)" />
          <stop offset="100%" stop-color="hsl(var(--primary) / 20%)" />
        </linearGradient>
      </defs>
      <!-- 从左侧中心点到右侧多条线 -->
      <path
        v-for="(_, index) in scoringExperts"
        :key="`path-left-${index}`"
        :d="`M0,100 L80,${30 + index * 35}`"
        fill="none"
        stroke="url(#flowGradLeft)"
        stroke-width="2"
        class="flow-line"
      />
      <!-- 流动粒子 -->
      <circle
        v-for="(_, index) in scoringExperts"
        :key="`circle-left-${index}`"
        r="3"
        fill="hsl(var(--primary))"
      >
        <animateMotion
          :dur="`${1.5 + index * 0.1}s`"
          repeatCount="indefinite"
          :path="`M0,100 L80,${30 + index * 35}`"
          :begin="`${index * 0.2}s`"
        />
      </circle>
    </svg>

    <!-- 区域2: 中间专家节点（水平排列） -->
    <div class="flow-experts-container">
      <div class="experts-border-box">
        <div class="experts-title">多维审核专家节点</div>
        <div class="experts-list-horizontal">
          <div
            v-for="expert in scoringExperts"
            :key="expert.expert_func"
            class="expert-node-horizontal"
            :class="{ 'expert-active': activeExperts[expert.expert_func] }"
            :style="{
              '--expert-color': expert.color,
              '--expert-bg': expert.bgColor,
            }"
            @click="triggerExpertScore(expert.expert_func)"
          >
            <div
              class="expert-icon"
              :style="{ backgroundColor: expert.bgColor }"
            >
              <span>{{ expert.icon }}</span>
            </div>
            <div class="expert-info">
              <div class="expert-name">{{ expert.expert_name }}</div>
              <div class="expert-status">
                <template v-if="activeExperts[expert.expert_func]">
                  <span class="status-active" :style="{ color: expert.color }">
                    <span class="status-dot-active"></span>
                    评审中
                  </span>
                </template>
                <template v-else>
                  <span class="status-idle">待机</span>
                </template>
              </div>
            </div>
            <Tooltip :title="expert.tooltip">
              <QuestionCircleOutlined class="expert-help" />
            </Tooltip>
          </div>
        </div>
      </div>
    </div>

    <!-- 连接线: 专家 -> 评分分布 -->
    <svg
      class="connection-svg-right"
      viewBox="0 0 80 200"
      preserveAspectRatio="none"
    >
      <defs>
        <linearGradient
          v-for="(expert, index) in scoringExperts"
          :id="`flowGradRight${index}`"
          :key="`grad-right-${expert.expert_func}`"
          x1="0%"
          y1="0%"
          x2="100%"
          y2="0%"
        >
          <stop offset="0%" :stop-color="expert.color" stop-opacity="0.6" />
          <stop offset="100%" :stop-color="expert.color" stop-opacity="0.2" />
        </linearGradient>
      </defs>
      <!-- 从每个专家到右侧分布区的连线 -->
      <path
        v-for="(_, index) in scoringExperts"
        :key="`path-right-${index}`"
        :d="`M0,${30 + index * 35} L80,100`"
        fill="none"
        :stroke="`url(#flowGradRight${index})`"
        stroke-width="2"
        stroke-dasharray="4,3"
        class="flow-line-dashed"
      />
      <!-- 流动粒子 -->
      <circle
        v-for="(expert, index) in scoringExperts"
        :key="`circle-right-${expert.expert_func}`"
        r="3"
        :fill="expert.color"
      >
        <animateMotion
          :dur="`${1.2 + index * 0.1}s`"
          repeatCount="indefinite"
          :path="`M0,${30 + index * 35} L80,100`"
          :begin="`${index * 0.15}s`"
        />
      </circle>
    </svg>

    <!-- 区域3: 右侧评分分布 -->
    <div class="flow-score-distribution">
      <div class="distribution-title">评分结果分布</div>
      <div class="distribution-content">
        <!-- 水平堆叠的分数条 -->
        <div
          v-for="range in scoreRanges"
          :key="range.id"
          class="score-range-row"
        >
          <div class="range-label">{{ range.label }}</div>
          <div class="range-bar-track">
            <div class="range-bar-segments">
              <Tooltip
                v-for="expert in scoringExperts"
                :key="expert.expert_func"
                placement="top"
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
                  class="range-segment"
                  :style="{
                    width: `${getExpertRangePercent(range.id, expert.expert_func)}%`,
                    backgroundColor: expert.color,
                  }"
                ></div>
              </Tooltip>
            </div>
          </div>
        </div>
      </div>

      <!-- 图例 -->
      <div class="distribution-legend">
        <div
          v-for="expert in scoringExperts"
          :key="expert.expert_func"
          class="legend-item"
        >
          <span
            class="legend-dot"
            :style="{ backgroundColor: expert.color }"
          ></span>
          <span class="legend-label">{{ expert.expert_name }}</span>
        </div>
      </div>
    </div>

    <!-- 箭头指向雷达图 -->
    <div class="flow-arrow">
      <svg width="40" height="40" viewBox="0 0 40 40">
        <defs>
          <linearGradient id="arrowGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stop-color="#3b82f6" />
            <stop offset="100%" stop-color="#8b5cf6" />
          </linearGradient>
        </defs>
        <polygon points="0,8 24,20 0,32" fill="url(#arrowGrad)" />
      </svg>
    </div>
  </div>
</template>

<style scoped>
/* ==================== 动画定义 ==================== */
@keyframes pool-glow {
  0%,
  100% {
    opacity: 0.5;
  }

  50% {
    opacity: 1;
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

@keyframes active-dot-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }

  50% {
    opacity: 0.5;
    transform: scale(1.2);
  }
}

@keyframes line-pulse {
  0%,
  100% {
    opacity: 0.4;
  }

  50% {
    opacity: 0.8;
  }
}

@keyframes segment-twinkle {
  0%,
  100% {
    opacity: 0.85;
  }

  25% {
    opacity: 1;
  }

  50% {
    opacity: 0.9;
  }

  75% {
    opacity: 1;
  }
}

@keyframes legend-dot-pulse {
  0%,
  100% {
    opacity: 0.7;
    transform: scale(1);
  }

  50% {
    opacity: 1;
    transform: scale(1.2);
  }
}

@keyframes arrow-move {
  0%,
  100% {
    transform: translateX(0);
  }

  50% {
    transform: translateX(6px);
  }
}

/* ==================== 主容器 ==================== */

.scoring-flow-horizontal {
  position: relative;
  display: flex;
  gap: 0;
  align-items: stretch;
  width: 100%;
  height: 240px;
  padding: 1rem;
}

/* ==================== 左侧文章池 ==================== */

.flow-article-pool {
  position: relative;
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 140px;
  height: 100%;
}

.pool-glow {
  position: absolute;
  inset: 0;
  background: radial-gradient(
    circle,
    hsl(var(--primary) / 20%) 0%,
    transparent 70%
  );
  animation: pool-glow 3s ease-in-out infinite;
}

.pool-content {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  align-items: center;
  padding: 1.25rem 1rem;
  background: hsl(var(--card));
  border: 2px solid hsl(var(--primary) / 30%);
  border-radius: 16px;
  box-shadow: 0 8px 24px rgb(0 0 0 / 12%);
}

.pool-icon {
  font-size: 2rem;
}

.pool-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: hsl(var(--foreground));
  text-align: center;
}

.pool-value {
  font-size: 1.75rem;
  font-weight: 700;
  color: hsl(var(--primary));
}

.pool-status {
  display: flex;
  gap: 0.4rem;
  align-items: center;
  font-size: 0.7rem;
  color: hsl(var(--muted-foreground));
}

.pool-status .status-dot {
  width: 6px;
  height: 6px;
  background: #22c55e;
  border-radius: 50%;
  animation: status-dot-pulse 2s ease-in-out infinite;
}

/* ==================== 连接线 SVG ==================== */

.connection-svg-left,
.connection-svg-right {
  position: absolute;
  top: 1rem;
  width: 80px;
  height: 200px;
  pointer-events: none;
}

.connection-svg-left {
  left: 140px;
}

.connection-svg-right {
  right: 300px;
}

.flow-line,
.flow-line-dashed {
  animation: line-pulse 2s ease-in-out infinite;
}

/* ==================== 中间专家区域 ==================== */

.flow-experts-container {
  position: relative;
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  justify-content: center;
  width: 320px;
  height: 100%;
  margin-left: 80px;
}

.experts-border-box {
  display: flex;
  flex-direction: column;
  height: 200px;
  padding: 1rem;
  background: hsl(var(--muted) / 20%);
  border: 1.5px dashed hsl(var(--border) / 50%);
  border-radius: 16px;
}

.experts-title {
  margin-bottom: 0.75rem;
  font-size: 0.8rem;
  font-weight: 600;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.experts-list-horizontal {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 0.35rem;
  justify-content: center;
}

.expert-node-horizontal {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  padding: 0.5rem 0.75rem;
  cursor: pointer;
  background: hsl(var(--card));
  border: 1.5px solid hsl(var(--border) / 30%);
  border-radius: 8px;
  transition: all 0.2s;
}

.expert-node-horizontal:hover {
  border-color: var(--expert-color);
  box-shadow: 0 2px 8px hsl(var(--expert-color) / 20%);
}

.expert-node-horizontal.expert-active {
  background: hsl(var(--expert-color) / 10%);
  border-color: var(--expert-color);
  box-shadow: 0 0 12px hsl(var(--expert-color) / 25%);
}

.expert-node-horizontal .expert-icon {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  font-size: 1rem;
  border-radius: 50%;
}

.expert-node-horizontal .expert-info {
  flex: 1;
  min-width: 0;
}

.expert-node-horizontal .expert-name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 0.8rem;
  font-weight: 600;
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.expert-node-horizontal .expert-status {
  font-size: 0.65rem;
}

.expert-node-horizontal .status-active {
  display: flex;
  gap: 0.2rem;
  align-items: center;
}

.expert-node-horizontal .status-dot-active {
  width: 5px;
  height: 5px;
  background: currentcolor;
  border-radius: 50%;
  animation: active-dot-pulse 1.5s ease-in-out infinite;
}

.expert-node-horizontal .status-idle {
  color: hsl(var(--muted-foreground));
}

.expert-node-horizontal .expert-help {
  flex-shrink: 0;
  font-size: 10px;
  color: hsl(var(--muted-foreground));
}

/* ==================== 右侧评分分布 ==================== */

.flow-score-distribution {
  position: relative;
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  width: 280px;
  height: 100%;
  margin-left: 80px;
}

.distribution-title {
  margin-bottom: 0.75rem;
  font-size: 0.85rem;
  font-weight: 600;
  color: hsl(var(--foreground));
  text-align: center;
}

.distribution-content {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 0.6rem;
  justify-content: center;
}

.score-range-row {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.range-label {
  font-size: 0.7rem;
  color: hsl(var(--muted-foreground));
}

.range-bar-track {
  width: 100%;
  height: 16px;
  overflow: hidden;
  background: hsl(var(--muted) / 30%);
  border-radius: 8px;
}

.range-bar-segments {
  display: flex;
  width: 100%;
  height: 100%;
}

.range-segment {
  height: 100%;
  cursor: pointer;
  transition: width 0.5s ease-out;
  animation: segment-twinkle 3s ease-in-out infinite;
}

.range-segment:hover {
  filter: brightness(1.15);
  animation: none;
}

/* ==================== 图例 ==================== */

.distribution-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  justify-content: center;
  padding-top: 0.5rem;
  margin-top: 0.75rem;
  border-top: 1px solid hsl(var(--border) / 20%);
}

.legend-item {
  display: flex;
  gap: 0.35rem;
  align-items: center;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  animation: legend-dot-pulse 2s ease-in-out infinite;
}

.legend-label {
  font-size: 0.7rem;
  color: hsl(var(--muted-foreground));
}

/* ==================== 箭头 ==================== */

.flow-arrow {
  position: absolute;
  top: 50%;
  right: -30px;
  transform: translateY(-50%);
  animation: arrow-move 2s ease-in-out infinite;
}

/* ==================== Tooltip ==================== */

.segment-tooltip {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  font-size: 0.8rem;
}

.tooltip-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.tooltip-percent {
  margin-left: auto;
  font-weight: 600;
  color: hsl(var(--foreground));
}
</style>
