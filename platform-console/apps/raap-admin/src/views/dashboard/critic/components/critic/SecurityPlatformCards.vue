<!--
  三方外延专家组卡片组件
  展示腾讯云风控、阿里云风控、火山引擎内容审核三个平台的数据
-->
<script setup lang="ts">
import { computed } from 'vue';

import { Card } from 'ant-design-vue';

// ==================== Types ====================

interface PlatformData {
  name: string;
  englishName: string;
  theme: string;
  logoType: 'image' | 'svg' | 'text';
  logoSvg?: string;
  logoImage?: string;
  totalCount: number;
  rejectedCount: number;
  status: string;
}

interface Props {
  /** Loading 状态 */
  loading?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
});

// ==================== 平台数据 ====================

// 注意：这里的数据目前是写死的，因为主文件中也是写死的
// 未来应该从 API 获取真实数据
const platforms = computed<PlatformData[]>(() => [
  {
    name: '腾讯云风控',
    englishName: 'Tencent',
    theme: 'tencent-theme',
    logoType: 'text',
    totalCount: 1030,
    rejectedCount: 65,
    status: '运行中',
  },
  {
    name: '阿里云风控',
    englishName: 'Aliyun',
    theme: 'aliyun-theme',
    logoType: 'image',
    logoImage:
      'https://img.alicdn.com/tfs/TB1Ly5oS3HqK1RjSZFPXXcwapXa-238-54.png',
    totalCount: 1030,
    rejectedCount: 47,
    status: '运行中',
  },
  {
    name: '火山引擎内容审核',
    englishName: 'Volcengine',
    theme: 'volcengine-theme',
    logoType: 'svg',
    logoSvg: `<path fill="#00dcff" d="M34.82,28.93l-14.97,46.07h32.16l-14.97-46.07c-.35-1.08-1.88-1.08-2.23,0Z" />
<path fill="#006aff" d="M12.83,42.36c-.35-1.08-1.88-1.08-2.23,0L0,75h9.42l7.01-21.57-3.59-11.06Z" />
<path fill="#00dcff" d="M29.52,20c-.35-1.08-1.88-1.08-2.23,0l-17.87,55h10.43l13.77-42.37-4.1-12.63Z" />
<path fill="#00dcff" d="M71.73,36.43c-.35-1.08-1.88-1.08-2.23,0l-3.55,10.94,8.98,27.63h9.34l-12.53-38.57Z" />
<path fill="#006aff" d="M50.82.81c-.35-1.08-1.88-1.08-2.23,0l-10.34,31.82,13.77,42.37h22.9L50.82.81Z" />`,
    totalCount: 1030,
    rejectedCount: 57,
    status: '运行中',
  },
]);

// 计算拒绝率
const getRejectRate = (platform: PlatformData) => {
  if (platform.totalCount === 0) return 0;
  return ((platform.rejectedCount / platform.totalCount) * 100).toFixed(1);
};
</script>

<template>
  <div class="security-platform-grid">
    <Card
      v-for="platform in platforms"
      :key="platform.name"
      :bordered="false"
      class="security-platform-card-cool"
      :class="[platform.theme]"
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
            <span class="security-platform-title">{{ platform.name }}</span>
          </div>

          <!-- Logo 展示 -->
          <div v-if="platform.logoType === 'text'" class="security-logo-text">
            <span class="logo-en">{{ platform.englishName }}</span>
            <span v-if="platform.name.includes('腾讯')" class="logo-cn"
              >腾讯云</span
            >
            <span v-else-if="platform.name.includes('阿里')" class="logo-cn"
              >阿里云</span
            >
          </div>

          <img
            v-else-if="platform.logoType === 'image' && platform.logoImage"
            :src="platform.logoImage"
            :alt="platform.name"
            class="security-platform-logo"
          />

          <div
            v-else-if="platform.logoType === 'svg' && platform.logoSvg"
            class="volcengine-logo-wrapper"
          >
            <svg
              class="volcengine-icon"
              viewBox="0 0 88 75"
              xmlns="http://www.w3.org/2000/svg"
              v-html="platform.logoSvg"
            />
            <span class="volcengine-text">火山引擎</span>
          </div>
        </div>

        <div class="security-platform-stats">
          <div class="security-stat-row">
            <span class="security-stat-label">总审核文章数量</span>
            <span class="security-stat-value">
              <span class="stat-number">{{
                platform.totalCount.toLocaleString()
              }}</span>
            </span>
          </div>
          <div class="security-stat-row">
            <span class="security-stat-label">审核不通过数量</span>
            <span class="security-stat-value security-reject-value">
              <span class="stat-number reject">{{
                platform.rejectedCount
              }}</span>
            </span>
          </div>
        </div>

        <!-- 状态指示灯 -->
        <div class="security-status">
          <span class="status-dot"></span>
          <span class="status-text">{{ platform.status }}</span>
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

@keyframes border-flow {
  0% {
    transform: translateX(-100%);
  }

  100% {
    transform: translateX(100%);
  }
}

@keyframes status-pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.4;
  }
}

@media (max-width: 1024px) {
  .security-platform-grid {
    grid-template-columns: 1fr;
  }
}

.security-platform-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
}

/* ==================== 卡片基础样式 ==================== */

.security-platform-card-cool {
  position: relative;
  overflow: hidden;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border) / 30%);
  border-radius: 12px;
  transition: all 0.3s;
}

.security-platform-card-cool:hover {
  box-shadow: 0 8px 24px rgb(0 0 0 / 12%);
  transform: translateY(-2px);
}

/* ==================== 背景装饰 ==================== */

.security-card-bg {
  position: absolute;
  inset: 0;
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
  opacity: 0.1;
  filter: blur(60px);
  animation: orb-float 6s ease-in-out infinite;
}

.security-grid-lines {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(hsl(var(--border) / 8%) 1px, transparent 1px),
    linear-gradient(90deg, hsl(var(--border) / 8%) 1px, transparent 1px);
  background-size: 30px 30px;
  opacity: 0.5;
}

/* ==================== 流光边框 ==================== */

.security-border-glow {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.border-line {
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

.security-platform-card-cool:hover .border-line {
  opacity: 1;
}

.border-top,
.border-bottom {
  right: 0;
  left: 0;
  height: 1px;
}

.border-top {
  top: 0;
  animation: border-flow 3s linear infinite;
}

.border-bottom {
  bottom: 0;
  animation: border-flow 3s linear infinite 1.5s;
}

.border-left,
.border-right {
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

.border-left {
  left: 0;
}

.border-right {
  right: 0;
}

/* ==================== 角落装饰 ==================== */

.security-corner {
  position: absolute;
  width: 16px;
  height: 16px;
  border-color: hsl(var(--primary) / 30%);
  border-style: solid;
  transition: all 0.3s;
}

.security-platform-card-cool:hover .security-corner {
  width: 24px;
  height: 24px;
  border-color: hsl(var(--primary));
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

/* ==================== 卡片内容 ==================== */

.security-card-content {
  position: relative;
  z-index: 1;
  padding: 1.25rem;
}

.security-platform-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.25rem;
}

.security-title-group {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.security-title-indicator {
  width: 4px;
  height: 16px;
  background: hsl(var(--primary));
  border-radius: 2px;
}

.security-platform-title {
  font-size: 1rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

/* Logo 样式 */
.security-logo-text {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  font-size: 0.75rem;
}

.logo-en {
  font-weight: 600;
  color: hsl(var(--foreground));
}

.logo-cn {
  font-size: 0.625rem;
  color: hsl(var(--muted-foreground));
}

.tencent-text {
  color: #0052d9;
}

.security-platform-logo {
  width: auto;
  height: 24px;
}

.volcengine-logo-wrapper {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.volcengine-icon {
  width: 44px;
  height: 38px;
}

.volcengine-text {
  font-size: 0.75rem;
  font-weight: 600;
  color: #00dcff;
}

/* 统计数据 */
.security-platform-stats {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.security-stat-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.security-stat-label {
  font-size: 0.875rem;
  color: hsl(var(--muted-foreground));
}

.security-stat-value {
  font-size: 1rem;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.security-reject-value {
  color: #ef4444;
}

.stat-number {
  font-variant-numeric: tabular-nums;
}

.stat-number.reject {
  color: #ef4444;
}

/* 状态指示 */
.security-status {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  padding-top: 0.75rem;
  border-top: 1px solid hsl(var(--border) / 20%);
}

.status-dot {
  width: 8px;
  height: 8px;
  background: #22c55e;
  border-radius: 50%;
  animation: status-pulse 2s ease-in-out infinite;
}

.status-text {
  font-size: 0.75rem;
  color: hsl(var(--muted-foreground));
}

/* ==================== 主题样式 ==================== */

/* 腾讯云 - 蓝色主题 */
.security-platform-card-cool.tencent-theme {
  --local-color: #0052d9;
}

.security-platform-card-cool.tencent-theme .security-glow-orb {
  background: var(--local-color);
}

.security-platform-card-cool.tencent-theme .security-title-indicator {
  background: var(--local-color);
}

/* 阿里云 - 橙色主题 */
.security-platform-card-cool.aliyun-theme {
  --local-color: #ff6a00;
}

.security-platform-card-cool.aliyun-theme .security-glow-orb {
  background: var(--local-color);
}

.security-platform-card-cool.aliyun-theme .security-title-indicator {
  background: var(--local-color);
}

/* 火山引擎 - 青色主题 */
.security-platform-card-cool.volcengine-theme {
  --local-color: #00dcff;
}

.security-platform-card-cool.volcengine-theme .security-glow-orb {
  background: var(--local-color);
}

.security-platform-card-cool.volcengine-theme .security-title-indicator {
  background: var(--local-color);
}

/* ==================== 网格布局 ==================== */
</style>
