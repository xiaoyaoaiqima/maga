<script setup lang="ts">
import type { RLHFIssueTagDistribution } from '../types';

import { Skeleton } from 'ant-design-vue';

import CountTo from '#/components/CountTo.vue';

interface Props {
  issueTags?: RLHFIssueTagDistribution[];
  loading?: boolean;
  totalCount?: number;
  selectedTag?: null | string;
}

const props = withDefaults(defineProps<Props>(), {
  issueTags: () => [],
  loading: false,
  totalCount: 0,
  selectedTag: null,
});

const emit = defineEmits<{
  tagClick: [tagName: string];
}>();

// 标签样式映射
const tagStyleMap: Record<string, { bgClass: string; icon: string }> = {
  illegal: {
    bgClass: 'tag-illegal',
    icon: '⚠️',
  },
  non_compliant: {
    bgClass: 'tag-non-compliant',
    icon: '📋',
  },
  unreasonable: {
    bgClass: 'tag-unreasonable',
    icon: '🤔',
  },
  off_purpose: {
    bgClass: 'tag-off-purpose',
    icon: '🎯',
  },
  other: {
    bgClass: 'tag-other',
    icon: '🏷️',
  },
};

const getTagStyle = (category: string) => {
  return tagStyleMap[category] || tagStyleMap.other;
};

const percentage = (count: number) => {
  if (!props.totalCount) return '0.0%';
  return `${((count / props.totalCount) * 100).toFixed(1)}%`;
};

const handleTagClick = (tagName: string) => {
  emit('tagClick', tagName);
};
</script>

<template>
  <div class="rlhf-feedback-section">
    <div class="rlhf-section-subtitle">
      正负向反馈结果
      <span class="section-subtitle-hint">点击标签可筛选详情</span>
    </div>

    <Skeleton :loading="loading" active :paragraph="{ rows: 1 }">
      <div v-if="issueTags.length === 0" class="empty-state">
        <span>暂无数据</span>
      </div>
      <div v-else class="rlhf-feedback-tags">
        <div
          v-for="tag in issueTags"
          :key="tag.tag_id || tag.tag"
          class="rlhf-feedback-tag-item"
          :class="[
            getTagStyle(tag.tag_category).bgClass,
            { active: selectedTag === tag.tag_name || selectedTag === tag.tag },
          ]"
          @click="handleTagClick(tag.tag_name)"
        >
          <span class="tag-icon">{{ getTagStyle(tag.tag_category).icon }}</span>
          <span class="tag-name">{{ tag.tag_name }}</span>
          <span class="tag-count">
            <CountTo
              :end-value="tag.count"
              :duration="1"
              :use-grouping="true"
            />条
          </span>
          <span class="tag-percent">占{{ percentage(tag.count) }}</span>
        </div>
      </div>
    </Skeleton>
  </div>
</template>

<style scoped>
/* ==================== 反馈标签区域 ==================== */
.rlhf-feedback-section {
  margin-bottom: 24px;
}

.rlhf-section-subtitle {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 16px;
  font-size: 15px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.section-subtitle-hint {
  font-size: 12px;
  font-weight: 400;
  color: hsl(var(--muted-foreground));
}

.rlhf-feedback-tags {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.rlhf-feedback-tag-item {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  overflow: hidden;
  cursor: pointer;
  background: hsl(var(--card) / 60%);
  border: 1px solid hsl(var(--border) / 50%);
  border-radius: 12px;
  backdrop-filter: blur(10px);
  transition: all 0.3s ease;
}

.rlhf-feedback-tag-item::before {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 3px;
  content: '';
  background: var(--tag-color);
  transition: height 0.3s ease;
}

.rlhf-feedback-tag-item:hover {
  box-shadow: 0 8px 24px hsl(var(--tag-color) / 20%);
  transform: translateY(-2px);
}

.rlhf-feedback-tag-item:hover::before {
  height: 100%;
  opacity: 0.05;
}

.rlhf-feedback-tag-item.active {
  border-color: var(--tag-color);
  box-shadow: 0 0 0 2px hsl(var(--tag-color) / 30%);
}

/* 标签类型样式 */
.tag-illegal {
  --tag-color: #ef4444;
}

.tag-non-compliant {
  --tag-color: #f59e0b;
}

.tag-unreasonable {
  --tag-color: #ec4899;
}

.tag-off-purpose {
  --tag-color: #8b5cf6;
}

.tag-other {
  --tag-color: #6b7280;
}

.tag-icon {
  font-size: 16px;
}

.tag-name {
  font-size: 14px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.tag-count {
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
}

.tag-percent {
  font-size: 12px;
  font-weight: 600;
  color: hsl(var(--tag-color));
  text-align: left;
}

.empty-state {
  padding: 40px;
  font-size: 14px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}
</style>
