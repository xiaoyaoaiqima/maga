<script setup lang="ts">
import { ref, watch } from 'vue';

interface Props {
  // 数据源
  items: any[];
  // 唯一键
  itemKey: string;
  // 是否启用 stagger 动画
  stagger?: boolean;
  // stagger 延迟（毫秒）
  staggerDelay?: number;
  // 是否启用悬停效果
  hoverable?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  stagger: true,
  staggerDelay: 100,
  hoverable: true,
});

// 用于触发动画的 key
const listKey = ref(0);

// 监听 items 变化，更新动画 key
watch(
  () => props.items,
  () => {
    listKey.value++;
  },
  { deep: true },
);

// 计算每个 item 的样式
const getItemStyle = (index: number) => {
  if (!props.stagger) return {};

  return {
    '--stagger-delay': `${index * props.staggerDelay}ms`,
  };
};
</script>

<template>
  <TransitionGroup :key="listKey" name="list" tag="div" class="animated-list">
    <div
      v-for="(item, index) in items"
      :key="item[itemKey]"
      class="list-item-staggered"
      :class="{ hoverable }"
      :style="getItemStyle(index)"
    >
      <slot name="item" :item="item" :index="index">
        {{ item }}
      </slot>
    </div>
  </TransitionGroup>
</template>

<style scoped>
@keyframes slide-in-up {
  from {
    opacity: 0;
    transform: translateY(30px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animated-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Stagger 渐入动画 */
.list-item-staggered {
  opacity: 0;
  transition: all 0.2s ease;
  animation: slide-in-up 0.5s cubic-bezier(0.4, 0, 0.2, 1) forwards;
  animation-delay: var(--stagger-delay, 0ms);
}

/* 悬停效果 */
.list-item-staggered.hoverable:hover {
  cursor: pointer;
  background: hsl(var(--accent) / 10%);
  box-shadow: 0 4px 12px rgb(0 0 0 / 10%);
  transform: translateX(8px) scale(1.01);
}

/* TransitionGroup 动画 */
.list-enter-active {
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.list-enter-from {
  opacity: 0;
  transform: translateY(20px);
}

.list-leave-active {
  transition: all 0.3s ease;
}

.list-leave-to {
  opacity: 0;
  transform: translateX(-30px);
}

.list-move {
  transition: transform 0.5s cubic-bezier(0.4, 0, 0.2, 1);
}
</style>
