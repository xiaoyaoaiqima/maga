<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';

interface Props {
  /** 目标值 */
  value: number;
  /** 小数位数 */
  decimals?: number;
  /** 前缀 */
  prefix?: string;
  /** 后缀 */
  suffix?: string;
  /** 动画持续时间(毫秒) */
  duration?: number;
  /** 使用千位分隔符 */
  useGrouping?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  decimals: 0,
  prefix: '',
  suffix: '',
  duration: 400,
  useGrouping: true,
});

// 当前显示的数字字符数组
const displayDigits = ref<string[]>([]);
// 上一次的数字字符数组
const prevDigits = ref<string[]>([]);
// 正在翻转的位置
const flippingIndices = ref<Set<number>>(new Set());

// 格式化数字为字符串
function formatNumber(num: number): string {
  let value = num.toFixed(props.decimals);

  if (props.useGrouping) {
    const parts = value.split('.');
    parts[0] = parts[0].replaceAll(/\B(?=(\d{3})+(?!\d))/g, ',');
    value = parts.join('.');
  }

  return value;
}

// 将格式化的数字转为字符数组
function toDigitArray(formattedNum: string): string[] {
  return [...formattedNum];
}

// 初始化
onMounted(() => {
  const initialValue = formatNumber(props.value);
  displayDigits.value = toDigitArray(initialValue);
  prevDigits.value = toDigitArray(initialValue);
});

// 监听值变化
watch(
  () => props.value,
  (newVal) => {
    const newFormatted = formatNumber(newVal);
    const newDigits = toDigitArray(newFormatted);
    const oldDigits = [...displayDigits.value];

    // 补齐长度
    while (oldDigits.length < newDigits.length) {
      oldDigits.unshift('');
    }
    while (newDigits.length < oldDigits.length) {
      newDigits.unshift('');
    }

    // 保存旧值
    prevDigits.value = oldDigits;

    // 找出变化的位置并触发翻转动画
    const changing = new Set<number>();
    for (const [i, newDigit] of newDigits.entries()) {
      if (newDigit !== oldDigits[i]) {
        changing.add(i);
      }
    }

    flippingIndices.value = changing;

    // 延迟更新显示值
    setTimeout(() => {
      displayDigits.value = newDigits;
    }, props.duration / 2);

    // 动画结束后清除翻转状态
    setTimeout(() => {
      flippingIndices.value = new Set();
    }, props.duration);
  },
  { immediate: false },
);

// 判断是否为分隔符
function isSeparator(char: string): boolean {
  return char === ',' || char === '.';
}
</script>

<template>
  <span class="flip-counter">
    <span v-if="prefix" class="flip-prefix">{{ prefix }}</span>
    <template v-for="(digit, index) in displayDigits" :key="index">
      <span
        class="flip-card"
        :class="{
          'is-flipping': flippingIndices.has(index),
          'is-separator': isSeparator(digit),
        }"
      >
        <span class="flip-card-inner">
          <span class="flip-card-front">{{ digit }}</span>
          <span class="flip-card-back">{{ prevDigits[index] || digit }}</span>
        </span>
        <span class="flip-card-shadow"></span>
      </span>
    </template>
    <span v-if="suffix" class="flip-suffix">{{ suffix }}</span>
  </span>
</template>

<style scoped>
@keyframes flip-animation {
  0% {
    transform: rotateX(0deg);
  }

  50% {
    transform: rotateX(-90deg);
  }

  100% {
    transform: rotateX(0deg);
  }
}

@keyframes glow {
  0% {
    opacity: 0.6;
  }

  100% {
    opacity: 0;
  }
}

.flip-counter {
  display: inline-flex;
  gap: 2px;
  align-items: center;
  font-family: 'SF Mono', Monaco, Consolas, monospace;
}

.flip-prefix {
  margin-right: 4px;
  font-size: 1.2em;
  font-weight: bold;
  color: hsl(var(--primary));
}

.flip-suffix {
  margin-left: 4px;
  font-size: 0.9em;
  color: hsl(var(--muted-foreground));
}

.flip-card {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.1em;
  height: 1.6em;
  font-size: inherit;
  font-weight: bold;
  perspective: 300px;
}

.flip-card.is-separator {
  width: 0.4em;
  background: transparent !important;
}

.flip-card.is-separator .flip-card-inner,
.flip-card.is-separator .flip-card-shadow {
  background: transparent !important;
  box-shadow: none !important;
}

/* 分隔符（小数点、逗号）使用前景色 */
.flip-card.is-separator .flip-card-front,
.flip-card.is-separator .flip-card-back {
  color: hsl(var(--foreground));
  text-shadow: none;
}

.flip-card-inner {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background: linear-gradient(
    180deg,
    hsl(var(--muted)) 0%,
    hsl(var(--accent)) 100%
  );
  border-radius: 6px;
  box-shadow:
    0 2px 8px hsl(var(--foreground) / 15%),
    inset 0 1px 0 hsl(var(--background) / 30%),
    inset 0 -1px 0 hsl(var(--foreground) / 10%);
  transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  transform-style: preserve-3d;
}

.flip-card-front,
.flip-card-back {
  position: absolute;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: hsl(var(--foreground));
  text-shadow: 0 1px 2px hsl(var(--background) / 30%);
  backface-visibility: hidden;
}

.flip-card-front {
  z-index: 2;
}

.flip-card-back {
  transform: rotateX(180deg);
}

.flip-card-shadow {
  position: absolute;
  top: 50%;
  right: 0;
  left: 0;
  z-index: 3;
  height: 2px;
  background: hsl(var(--foreground) / 15%);
}

/* 翻转动画 */
.flip-card.is-flipping .flip-card-inner {
  animation: flip-animation 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

/* 发光效果 */
.flip-card.is-flipping::after {
  position: absolute;
  inset: -2px;
  z-index: -1;
  content: '';
  background: linear-gradient(
    45deg,
    hsl(var(--primary)),
    hsl(var(--primary) / 70%),
    hsl(var(--primary))
  );
  border-radius: 8px;
  opacity: 0;
  animation: glow 0.4s ease-out;
}
</style>
