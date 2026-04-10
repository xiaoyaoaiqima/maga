<script setup lang="ts">
import { computed, ref } from 'vue';

import { Button } from 'ant-design-vue';

interface Props {
  // 是否启用波纹效果
  ripple?: boolean;
  // 是否启用缩放效果
  scale?: boolean;
  // 防抖延迟（毫秒）
  debounce?: number;
}

const props = withDefaults(defineProps<Props>(), {
  ripple: true,
  scale: true,
  debounce: 0,
});

const emit = defineEmits<{
  click: [event: MouseEvent];
}>();

const isClicked = ref(false);
const isDisabled = ref(false);

const buttonClass = computed(() => ({
  'btn-enhanced': true,
  clicked: isClicked.value && props.scale,
}));

async function handleClick(event: MouseEvent) {
  if (isDisabled.value) return;

  // 防抖处理
  if (props.debounce > 0) {
    isDisabled.value = true;
    setTimeout(() => {
      isDisabled.value = false;
    }, props.debounce);
  }

  // 视觉反馈
  if (props.ripple || props.scale) {
    isClicked.value = true;
    setTimeout(() => {
      isClicked.value = false;
    }, 600);
  }

  emit('click', event);
}
</script>

<template>
  <Button
    v-bind="$attrs"
    :class="buttonClass"
    :disabled="isDisabled"
    @click="handleClick"
  >
    <slot></slot>
  </Button>
</template>

<style scoped>
.btn-enhanced {
  position: relative;
  overflow: hidden;
}

.btn-enhanced:active {
  transform: scale(0.95);
}

/* 波纹效果 */
.btn-enhanced::before {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 0;
  height: 0;
  pointer-events: none;
  content: '';
  background: rgb(255 255 255 / 50%);
  border-radius: 50%;
  transform: translate(-50%, -50%);
  transition:
    width 0.6s ease-out,
    height 0.6s ease-out;
}

.btn-enhanced.clicked::before {
  width: 300px;
  height: 300px;
}
</style>
