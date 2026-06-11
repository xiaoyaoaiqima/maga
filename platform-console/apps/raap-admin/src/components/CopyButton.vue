<script setup lang="ts">
// @ts-nocheck
import { ref, watch } from 'vue';

import { useClipboard } from '@vueuse/core';
import { message } from 'ant-design-vue';

interface Props {
  // 要复制的文本
  text: string;
  // 提示文本
  tooltip?: string;
  // 按钮类型
  type?: 'default' | 'link' | 'primary' | 'text';
  // 按钮 size
  size?: 'large' | 'middle' | 'small';
}

const props = withDefaults(defineProps<Props>(), {
  tooltip: '复制',
  type: 'text',
  size: 'small',
});

const emit = defineEmits<{
  copied: [text: string];
}>;

const { copy, isSupported } = useClipboard({ source: props.text });
const isJustCopied = ref(false);

let copyTimer: null | ReturnType<typeof setTimeout> = null;

async function handleCopy() {
  if (!isSupported.value) {
    message.error('当前浏览器不支持复制功能');
    return;
  }

  try {
    await copy(props.text);

    // 清除之前的定时器
    if (copyTimer) {
      clearTimeout(copyTimer);
    }

    // 显示复制成功状态
    isJustCopied.value = true;
    copyTimer = setTimeout(() => {
      isJustCopied.value = false;
    }, 2000);

    // 显示提示
    message.success(
      `已复制: ${props.text.slice(0, 30)}${props.text.length > 30 ? '...' : ''}`,
    );

    // 触发事件
    emit('copied', props.text);
  } catch (error) {
    message.error('复制失败');
    console.error('Copy failed:', error);
  }
}

// 监听 props.text 变化
watch(
  () => props.text,
  () => {
    // 重置状态
    isJustCopied.value = false;
  },
);
</script>

<template>
  <div class="copy-button-container">
    <button
      class="copy-button"
      :class="[
        `copy-button--${type}`,
        `copy-button--${size}`,
        { 'copy-button--copied': isJustCopied },
      ]"
      :title="tooltip"
      @click="handleCopy"
    >
      <Transition name="icon-switch" mode="out-in">
        <svg
          v-if="!isJustCopied"
          key="copy"
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="copy-icon"
        >
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
        </svg>

        <svg
          v-else
          key="check"
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
          class="check-icon"
        >
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </Transition>
    </button>
  </div>
</template>

<style scoped>
@keyframes check-success {
  0% {
    opacity: 0;
    transform: scale(0);
  }

  50% {
    transform: scale(1.2);
  }

  100% {
    opacity: 1;
    transform: scale(1);
  }
}

.copy-button-container {
  display: inline-block;
}

.copy-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 8px;
  color: hsl(var(--primary));
  cursor: pointer;
  outline: none;
  background: transparent;
  border: none;
  border-radius: 4px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.copy-button:hover {
  background: hsl(var(--primary) / 10%);
  transform: scale(1.05);
}

.copy-button:active {
  transform: scale(0.95);
}

.copy-button--copied {
  color: hsl(142deg 76% 36%);
  background: hsl(142deg 76% 96%);
}

.copy-button--copied:hover {
  background: hsl(142deg 76% 90%);
}

.copy-button--text {
  color: hsl(var(--foreground) / 60%);
}

.copy-button--primary {
  color: hsl(var(--primary));
}

/* 尺寸变体 */
.copy-button--small {
  padding: 2px 6px;
}

.copy-button--small svg {
  width: 12px;
  height: 12px;
}

.copy-button--middle {
  padding: 6px 12px;
}

.copy-button--middle svg {
  width: 16px;
  height: 16px;
}

.copy-button--large {
  padding: 8px 16px;
}

.copy-button--large svg {
  width: 18px;
  height: 18px;
}

/* 图标切换动画 */
.icon-switch-enter-active,
.icon-switch-leave-active {
  transition: all 0.3s cubic-bezier(0.68, -0.55, 0.27, 1.55);
}

.icon-switch-enter-from {
  opacity: 0;
  transform: scale(0) rotate(-180deg);
}

.icon-switch-leave-to {
  opacity: 0;
  transform: scale(0) rotate(180deg);
}

/* 成功对勾动画 */
.check-icon {
  animation: checkSuccess 0.4s cubic-bezier(0.68, -0.55, 0.27, 1.55);
}

/* 可访问性 */
.copy-button:focus-visible {
  outline: 2px solid hsl(var(--primary));
  outline-offset: 2px;
}
</style>
