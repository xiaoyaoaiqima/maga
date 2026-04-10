<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';

import gsap from 'gsap';

interface Props {
  /** 起始值 */
  startValue?: number;
  /** 目标值 */
  endValue: number;
  /** 动画持续时间(秒) */
  duration?: number;
  /** 小数位数 */
  decimals?: number;
  /** 前缀 */
  prefix?: string;
  /** 后缀 */
  suffix?: string;
  /** 使用千位分隔符 */
  useGrouping?: boolean;
  /** 缓动函数 */
  ease?: string;
}

const props = withDefaults(defineProps<Props>(), {
  startValue: 0,
  duration: 1.5,
  decimals: 2,
  prefix: '',
  suffix: '',
  useGrouping: true,
  ease: 'power2.out',
});

const emit = defineEmits<{
  finished: [];
  started: [];
}>();

// 当前显示的数值
const currentValue = ref(props.startValue);
// 动画实例
let tweenInstance: gsap.core.Tween | null = null;

// 格式化显示
const displayValue = computed(() => {
  let value = currentValue.value.toFixed(props.decimals);

  if (props.useGrouping) {
    // 添加千位分隔符
    const parts = value.split('.');
    parts[0] = parts[0].replaceAll(/\B(?=(\d{3})+(?!\d))/g, ',');
    value = parts.join('.');
  }

  return `${props.prefix}${value}${props.suffix}`;
});

// 启动动画
function startAnimation(from: number, to: number) {
  // 停止之前的动画
  if (tweenInstance) {
    tweenInstance.kill();
  }

  emit('started');

  tweenInstance = gsap.to(currentValue, {
    value: to,
    duration: props.duration,
    ease: props.ease,
    onComplete: () => {
      emit('finished');
    },
  });
}

// 监听目标值变化
watch(
  () => props.endValue,
  (newVal) => {
    // 从当前显示值动画到新值
    startAnimation(currentValue.value, newVal);
  },
);

// 初始化时执行动画
onMounted(() => {
  startAnimation(props.startValue, props.endValue);
});

// 暴露方法供外部调用
defineExpose({
  restart: () => startAnimation(props.startValue, props.endValue),
});
</script>

<template>
  <span class="count-to">{{ displayValue }}</span>
</template>

<style scoped>
.count-to {
  font-variant-numeric: tabular-nums;
}
</style>
