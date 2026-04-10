<script setup lang="ts">
/**
 * 图谱可视化页面
 *
 * 性能优化：图表组件使用 defineAsyncComponent 懒加载
 * - Graph3DView (Three.js): ~789KB
 */
import { defineAsyncComponent, onMounted, ref } from 'vue';

import { VbenButton as Button } from '@vben-core/shadcn-ui';

import { ReloadOutlined } from '@ant-design/icons-vue';
import { Card, Spin } from 'ant-design-vue';

// 懒加载 3D 图谱组件
const Graph3DView = defineAsyncComponent({
  loader: () => import('../list/components/Graph3DView.vue'),
  loadingComponent: Spin,
  delay: 200,
});

// 刷新图谱（通过重新加载组件实现）
const refreshKey = ref(0);
const lastUpdateTime = ref<string>('');

// 格式化时间：YYYY-MM-DD HH:mm:ss
const formatUpdateTime = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
};

const handleRefresh = () => {
  refreshKey.value++;
  lastUpdateTime.value = formatUpdateTime(new Date());
};

// 初始化时记录加载时间
onMounted(() => {
  lastUpdateTime.value = formatUpdateTime(new Date());
});
</script>

<template>
  <div class="graph-corpus-container">
    <!-- 粘性筛选头部 -->
    <div
      class="sticky top-0 z-10 -mx-4 -mt-4 mb-3 bg-background/90 px-4 pb-4 pt-2 shadow-lg backdrop-blur-md"
      style="border-bottom: 1px solid hsl(var(--border) / 30%)"
    >
      <!-- 标题行 -->
      <div class="mb-2 flex items-center justify-between gap-3">
        <div class="flex items-center gap-3">
          <span
            class="bg-gradient-to-r from-[hsl(var(--primary))] to-[#22c55e] bg-clip-text text-xl font-bold text-transparent"
          >
            关键词图谱
          </span>
          <span v-if="lastUpdateTime" class="text-xs text-muted-foreground">
            数据更新时间：{{ lastUpdateTime }}
          </span>
        </div>
        <Button
          class="action-btn"
          variant="ghost"
          size="sm"
          @click="handleRefresh"
        >
          <ReloadOutlined class="btn-icon" />
          <span class="btn-label">刷新</span>
        </Button>
      </div>
    </div>

    <!-- 图谱卡片 -->
    <Card :bordered="false" class="graph-card">
      <Suspense>
        <template #default>
          <Graph3DView :key="refreshKey" />
        </template>
        <template #fallback>
          <div class="loading-container">
            <Spin size="large" tip="加载 3D 图谱中..." />
          </div>
        </template>
      </Suspense>
    </Card>
  </div>
</template>

<style scoped>
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }

  50% {
    opacity: 0.8;
    transform: scale(1.05);
  }
}

.graph-corpus-container {
  padding: 16px;
}

.action-btn {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  height: 36px;
  padding: 0 14px;
  font-size: 13px;
  font-weight: 500;
  border-radius: 8px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.action-btn:hover {
  background-color: hsl(var(--accent) / 20%);
  transform: translateY(-1px);
}

.btn-icon {
  font-size: 14px;
}

.btn-label {
  font-size: 13px;
}

/* 图谱卡片 */
.graph-card {
  min-height: calc(100vh - 250px);
  border-radius: 16px;
}

.loading-container {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 400px;
}
</style>
