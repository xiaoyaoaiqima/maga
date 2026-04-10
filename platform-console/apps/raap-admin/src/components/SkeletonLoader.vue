<script setup lang="ts">
import { computed } from 'vue';

interface Props {
  // 骨架屏类型
  type?: 'card' | 'custom' | 'form' | 'list' | 'table';
  // 行数（用于 list/table）
  rows?: number;
  // 是否显示头像
  avatar?: boolean;
  // 是否显示标题
  title?: boolean;
  // 宽度
  width?: number | string;
  // 高度
  height?: number | string;
}

const props = withDefaults(defineProps<Props>(), {
  type: 'card',
  rows: 3,
  avatar: false,
  title: true,
  width: '100%',
  height: 'auto',
});

const skeletonStyle = computed(() => ({
  width: typeof props.width === 'number' ? `${props.width}px` : props.width,
  height: typeof props.height === 'number' ? `${props.height}px` : props.height,
}));
</script>

<template>
  <!-- 卡片骨架屏 -->
  <div v-if="type === 'card'" class="skeleton-card">
    <div
      v-if="title"
      class="skeleton skeleton-title"
      :style="skeletonStyle"
    ></div>
    <div class="skeleton-content">
      <div v-if="avatar" class="skeleton skeleton-avatar"></div>
      <div class="skeleton-lines">
        <div
          v-for="i in rows"
          :key="i"
          class="skeleton skeleton-line"
          :style="{ width: i === rows ? '60%' : '100%' }"
        ></div>
      </div>
    </div>
  </div>

  <!-- 列表骨架屏 -->
  <div v-else-if="type === 'list'" class="skeleton-list">
    <div
      v-for="i in rows"
      :key="i"
      class="skeleton-list-item"
      :style="{ animationDelay: `${i * 100}ms` }"
    >
      <div v-if="avatar" class="skeleton skeleton-avatar"></div>
      <div class="skeleton skeleton-line" style="width: 40%"></div>
      <div class="skeleton skeleton-line" style="width: 70%"></div>
    </div>
  </div>

  <!-- 表格骨架屏 -->
  <div v-else-if="type === 'table'" class="skeleton-table">
    <div class="skeleton-table-header">
      <div v-for="i in 5" :key="i" class="skeleton skeleton-header"></div>
    </div>
    <div class="skeleton-table-body">
      <div
        v-for="row in rows"
        :key="row"
        class="skeleton-table-row"
        :style="{ animationDelay: `${row * 50}ms` }"
      >
        <div v-for="i in 5" :key="i" class="skeleton skeleton-cell"></div>
      </div>
    </div>
  </div>

  <!-- 表单骨架屏 -->
  <div v-else-if="type === 'form'" class="skeleton-form">
    <div v-for="i in rows" :key="i" class="skeleton-form-item">
      <div class="skeleton skeleton-label"></div>
      <div class="skeleton skeleton-input"></div>
    </div>
  </div>

  <!-- 自定义骨架屏 -->
  <div v-else class="skeleton-custom">
    <div class="skeleton" :style="skeletonStyle"></div>
  </div>
</template>

<style scoped>
@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }

  100% {
    background-position: -200% 0;
  }
}

.skeleton {
  background: linear-gradient(
    90deg,
    hsl(var(--muted) / 20%) 0%,
    hsl(var(--muted) / 40%) 50%,
    hsl(var(--muted) / 20%) 100%
  );
  background-size: 200% 100%;
  border-radius: 4px;
  animation: shimmer 1.5s infinite;
}

/* 卡片骨架 */
.skeleton-card {
  padding: 20px;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.skeleton-title {
  width: 60%;
  height: 24px;
  margin-bottom: 16px;
}

.skeleton-content {
  display: flex;
  gap: 12px;
}

.skeleton-avatar {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 50%;
}

.skeleton-lines {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
}

.skeleton-line {
  height: 16px;
}

/* 列表骨架 */
.skeleton-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.skeleton-list-item {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 12px;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

/* 表格骨架 */
.skeleton-table {
  width: 100%;
}

.skeleton-table-header {
  display: flex;
  gap: 8px;
  padding: 12px;
  margin-bottom: 8px;
  background: hsl(var(--muted) / 30%);
  border-radius: 4px;
}

.skeleton-header {
  flex: 1;
  height: 20px;
}

.skeleton-table-row {
  display: flex;
  gap: 8px;
  padding: 12px;
  border-bottom: 1px solid hsl(var(--border));
}

.skeleton-cell {
  flex: 1;
  height: 16px;
}

/* 表单骨架 */
.skeleton-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.skeleton-form-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skeleton-label {
  width: 30%;
  height: 16px;
}

.skeleton-input {
  width: 100%;
  height: 32px;
}

/* 基础骨架样式 */
</style>
