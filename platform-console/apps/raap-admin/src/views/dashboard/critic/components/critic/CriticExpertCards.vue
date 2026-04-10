<!--
  评论专家卡片组件
  展示4个负面专家的统计数据（不合法、不合规、不合理、不合目的）
-->
<script setup lang="ts">
import { computed } from 'vue';

import { QuestionCircleOutlined } from '@ant-design/icons-vue';
import { Card, Tooltip } from 'ant-design-vue';

import CountTo from '#/components/CountTo.vue';

// ==================== Types ====================

interface CriticExpertData {
  totalInput: number;
  rejectedCount: number;
}

interface CriticExpertConfig {
  key: string;
  title: string;
  theme: string;
  description: string;
}

// ==================== Props ====================

interface Props {
  /** 获取专家数据的函数 */
  getExpertData: (expertCode: string) => CriticExpertData;
  /** Loading 状态 */
  loading?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
});

// ==================== 专家配置 ====================

const EXPERT_CONFIGS: CriticExpertConfig[] = [
  {
    key: 'CriticTencent',
    title: '不合法',
    theme: 'illegal-theme',
    description:
      '表示不符合国家法律法规，如违反《广告法》、《网络安全法》、《个人信息保护法》等，包括虚假宣传、侵权内容、违禁词汇等',
  },
  {
    key: 'CriticIllegal',
    title: '不合规',
    theme: 'irregular-theme',
    description:
      '表示不符合平台或品牌规定，如违反小红书、抖音等平台的社区规范，不符合品牌调性要求、品牌合规标准等',
  },
  {
    key: 'CriticUnreasonable',
    title: '不合理',
    theme: 'unreasonable-theme',
    description:
      '表示不符合常理逻辑，如违背人类正常活动规律、时间线混乱、因果关系矛盾、事实描述不合理、场景设定不符合现实等',
  },
  {
    key: 'CriticCounterproductive',
    title: '不合目的',
    theme: 'counterproductive-theme',
    description:
      '表示不符合文章预期目标，如内容偏离主题、未能传达核心信息、无法达成营销转化目的、与目标受众需求不匹配等',
  },
];

// ==================== 计算属性 ====================

const expertsWithData = computed(() => {
  return EXPERT_CONFIGS.map((config) => {
    const data = props.getExpertData(config.key);
    const percentage =
      data.totalInput > 0 ? (data.rejectedCount / data.totalInput) * 100 : 0;

    return {
      ...config,
      ...data,
      percentage,
    };
  });
});
</script>

<template>
  <div class="critic-expert-grid-cool">
    <Card
      v-for="expert in expertsWithData"
      :key="expert.key"
      :bordered="false"
      class="critic-card-cool"
      :class="[expert.theme]"
    >
      <!-- 背景装饰 -->
      <div class="critic-card-bg">
        <div class="critic-glow-orb"></div>
        <div class="critic-pulse-ring"></div>
      </div>

      <!-- 流光边框 -->
      <div class="critic-border-glow"></div>

      <!-- 卡片内容 -->
      <div class="critic-card-content">
        <!-- 标题区域 -->
        <div class="critic-header">
          <div class="critic-title-group">
            <span class="critic-title">{{ expert.title }}</span>
          </div>
          <Tooltip placement="top">
            <template #title>
              <div class="dimension-tooltip">{{ expert.description }}</div>
            </template>
            <QuestionCircleOutlined class="critic-help-icon" />
          </Tooltip>
        </div>

        <!-- 统计数据 -->
        <div class="critic-stats">
          <div class="critic-stat-item">
            <span class="critic-stat-label">总审核文章数量</span>
            <span class="critic-stat-value">
              <CountTo
                :end-value="expert.totalInput"
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
                :end-value="expert.rejectedCount"
                :decimals="0"
                :duration="1"
                :use-grouping="true"
              />
            </span>
          </div>
        </div>

        <!-- 进度条 -->
        <div class="critic-progress">
          <div
            class="progress-bar"
            :style="{ width: `${expert.percentage}%` }"
          ></div>
        </div>
      </div>
    </Card>
  </div>
</template>

<style scoped>
@keyframes orb-float {
  0%,
  100% {
    transform: translate(0, 0);
  }

  50% {
    transform: translate(-20px, 20px);
  }
}

@keyframes pulse-ring {
  0%,
  100% {
    opacity: 0;
    transform: scale(1);
  }

  50% {
    opacity: 0.3;
    transform: scale(1.05);
  }
}

@keyframes border-glow {
  0% {
    background-position: 0% 50%;
  }

  100% {
    background-position: 200% 50%;
  }
}

@media (max-width: 1200px) {
  .critic-expert-grid-cool {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .critic-expert-grid-cool {
    grid-template-columns: 1fr;
  }
}

.critic-expert-grid-cool {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin-bottom: 1.5rem;
}

/* ==================== 卡片基础样式 ==================== */

.critic-card-cool {
  position: relative;
  overflow: hidden;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border) / 30%);
  border-radius: 12px;
  transition: all 0.3s;
}

.critic-card-cool:hover {
  border-color: hsl(var(--primary) / 50%);
  box-shadow: 0 8px 24px rgb(0 0 0 / 12%);
  transform: translateY(-2px);
}

/* ==================== 背景装饰 ==================== */

.critic-card-bg {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}

.critic-glow-orb {
  position: absolute;
  top: -50px;
  right: -50px;
  width: 150px;
  height: 150px;
  border-radius: 50%;
  opacity: 0.1;
  filter: blur(60px);
  animation: orb-float 6s ease-in-out infinite;
}

.critic-pulse-ring {
  position: absolute;
  inset: 0;
  border-radius: 12px;
  opacity: 0;
  animation: pulse-ring 3s ease-in-out infinite;
}

/* ==================== 流光边框 ==================== */

.critic-border-glow {
  position: absolute;
  inset: 0;
  pointer-events: none;
  border-radius: 12px;
}

.critic-border-glow::before {
  position: absolute;
  inset: -2px;
  padding: 2px;
  content: '';
  background: linear-gradient(
    45deg,
    transparent 30%,
    hsl(var(--primary) / 30%),
    transparent 70%
  );
  border-radius: 12px;
  opacity: 0;
  mask:
    linear-gradient(#fff 0 0) content-box,
    linear-gradient(#fff 0 0);
  mask-composite: exclude;
  transition: opacity 0.3s;
}

.critic-card-cool:hover .critic-border-glow::before {
  opacity: 1;
  animation: border-glow 3s linear infinite;
}

/* ==================== 卡片内容 ==================== */

.critic-card-content {
  position: relative;
  z-index: 1;
  padding: 1.25rem;
}

/* 标题区域 */
.critic-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.critic-title-group {
  display: flex;
  align-items: center;
}

.critic-title {
  font-size: 1rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.critic-help-icon {
  font-size: 14px;
  color: hsl(var(--muted-foreground));
  cursor: help;
  transition: color 0.2s;
}

.critic-help-icon:hover {
  color: hsl(var(--primary));
}

/* 统计数据 */
.critic-stats {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.critic-stat-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.critic-stat-label {
  font-size: 0.875rem;
  color: hsl(var(--muted-foreground));
}

.critic-stat-value {
  font-size: 1.25rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.critic-stat-item.reject .critic-stat-value {
  color: #ef4444;
}

/* 进度条 */
.critic-progress {
  width: 100%;
  height: 6px;
  overflow: hidden;
  background: hsl(var(--muted) / 30%);
  border-radius: 3px;
}

.progress-bar {
  height: 100%;
  background: hsl(var(--primary));
  border-radius: 3px;
  transition: width 0.6s ease-out;
}

/* ==================== 主题样式 ==================== */

/* 不合法 - 红色主题 */
.critic-card-cool.illegal-theme {
  --local-color: #ef4444;
}

.critic-card-cool.illegal-theme .critic-glow-orb {
  background: var(--local-color);
}

.critic-card-cool.illegal-theme .progress-bar {
  background: linear-gradient(90deg, var(--local-color), #f87171);
}

/* 不合规 - 橙色主题 */
.critic-card-cool.irregular-theme {
  --local-color: #f59e0b;
}

.critic-card-cool.irregular-theme .critic-glow-orb {
  background: var(--local-color);
}

.critic-card-cool.irregular-theme .progress-bar {
  background: linear-gradient(90deg, var(--local-color), #fbbf24);
}

/* 不合理 - 紫色主题 */
.critic-card-cool.unreasonable-theme {
  --local-color: #8b5cf6;
}

.critic-card-cool.unreasonable-theme .critic-glow-orb {
  background: var(--local-color);
}

.critic-card-cool.unreasonable-theme .progress-bar {
  background: linear-gradient(90deg, var(--local-color), #a78bfa);
}

/* 不合目的 - 粉色主题 */
.critic-card-cool.counterproductive-theme {
  --local-color: #ec4899;
}

.critic-card-cool.counterproductive-theme .critic-glow-orb {
  background: var(--local-color);
}

.critic-card-cool.counterproductive-theme .progress-bar {
  background: linear-gradient(90deg, var(--local-color), #f472b6);
}

/* ==================== Tooltip 样式 ==================== */

.dimension-tooltip {
  max-width: 300px;
  font-size: 0.875rem;
  line-height: 1.5;
  color: hsl(var(--foreground));
}

/* ==================== 网格布局 ==================== */
</style>
