<script setup lang="ts">
import { computed } from 'vue';

import { diffWords } from 'diff';

interface Props {
  /** 原文内容 */
  original: string;
  /** 修改后的内容 */
  modified: string;
  /** 是否显示差异高亮，false 时只显示修改后的内容 */
  showDiff?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  showDiff: true,
});

interface DiffPart {
  value: string;
  added?: boolean;
  removed?: boolean;
}

/**
 * 计算差异并生成 HTML
 */
const diffHtml = computed(() => {
  if (!props.showDiff) {
    // 不显示差异时，直接返回修改后的内容
    return escapeHtml(props.modified);
  }

  const original = props.original || '';
  const modified = props.modified || '';

  // 如果两者相同，直接返回
  if (original === modified) {
    return escapeHtml(modified);
  }

  // 使用 diffWords 进行单词级别的比较
  const changes: DiffPart[] = diffWords(original, modified);

  // 生成带高亮的 HTML
  return changes
    .map((part) => {
      const escapedValue = escapeHtml(part.value);
      if (part.added) {
        return `<span class="diff-added">${escapedValue}</span>`;
      }
      if (part.removed) {
        return `<span class="diff-removed">${escapedValue}</span>`;
      }
      return escapedValue;
    })
    .join('');
});

/**
 * 转义 HTML 特殊字符
 */
function escapeHtml(text: string): string {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
</script>

<template>
  <div class="diff-viewer">
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div class="diff-content" v-html="diffHtml"></div>
  </div>
</template>

<style scoped>
.diff-viewer {
  width: 100%;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.6;
}

.diff-content {
  padding: 12px;
  overflow-wrap: break-word;
  white-space: pre-wrap;
  background: hsl(var(--card));
  border-radius: 6px;
}

/* 新增的文字：绿色背景 */
.diff-content :deep(.diff-added) {
  padding: 1px 2px;
  background-color: hsl(var(--success) / 30%);
  border-radius: 2px;
}

/* 删除的文字：红色背景 + 删除线 */
.diff-content :deep(.diff-removed) {
  padding: 1px 2px;
  text-decoration: line-through;
  background-color: hsl(var(--destructive) / 30%);
  border-radius: 2px;
}
</style>
