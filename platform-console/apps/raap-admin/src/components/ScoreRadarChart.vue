<script setup lang="ts">
/**
 * 评分雷达图组件
 * 用于展示多维度评分数据，支持文章池和喜欢采纳面板复用
 * - hover 维度标签：查看 AI 评分理由（reason）
 * - hover 问号图标：查看 AI 评分规则（prompt）
 *
 * 性能优化：按需引入 ECharts，仅加载雷达图所需组件
 */
import type { EChartsOption } from 'echarts';

import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue';

import { QuestionCircleOutlined } from '@ant-design/icons-vue';
import { Popover } from 'ant-design-vue';
import { RadarChart } from 'echarts/charts';
import { TitleComponent, TooltipComponent } from 'echarts/components';
// 按需引入 ECharts 核心和雷达图组件
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';

const props = withDefaults(defineProps<Props>(), {
  width: '280px',
  height: '220px',
  maxScore: 100,
  seriesName: '维度评分',
  themeColor: '#6366f1',
  showLabel: true,
  radius: '65%',
});

// 注册必需的组件
echarts.use([RadarChart, TitleComponent, TooltipComponent, CanvasRenderer]);

/** 评分项 */
export interface ScoreItem {
  /** 维度标签（显示在雷达图轴上） */
  label: string;
  /** 分数（0-100） */
  score: number;
  /** 维度标识符（可选，用于数据追踪） */
  dimension?: string;
  /** 是否有实际评分（用于区分未评分项） */
  hasScore?: boolean;
  /** AI 评分理由（用于维度标签 hover 显示） */
  reason?: string;
  /** AI 评分规则/提示词（用于问号图标 hover 显示） */
  prompt?: string;
}

interface Props {
  /** 评分数据 */
  scores: ScoreItem[];
  /** 图表宽度 */
  width?: string;
  /** 图表高度 */
  height?: string;
  /** 最大分值 */
  maxScore?: number;
  /** 数据系列名称 */
  seriesName?: string;
  /** 主题色（用于雷达图填充和线条） */
  themeColor?: string;
  /** 是否显示分数标签 */
  showLabel?: boolean;
  /** 雷达图半径 */
  radius?: string;
}

// 使用 shallowRef 避免 ECharts 实例被 Vue 深度响应
const chartRef = ref<HTMLDivElement>();
const chartInstance = shallowRef<echarts.ECharts | null>(null);

/** 将主题色转换为带透明度的颜色 */
const getColorWithAlpha = (color: string, alpha: number): string => {
  if (color.startsWith('#')) {
    const hex = color.slice(1);
    const r = Number.parseInt(hex.slice(0, 2), 16);
    const g = Number.parseInt(hex.slice(2, 4), 16);
    const b = Number.parseInt(hex.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  if (color.startsWith('rgb')) {
    const match = color.match(/\d+/g);
    if (match && match.length >= 3) {
      return `rgba(${match[0]}, ${match[1]}, ${match[2]}, ${alpha})`;
    }
  }
  return color;
};

/** 解析尺寸字符串为数字 */
const parseSize = (size: string): number => {
  const num = Number.parseInt(size, 10);
  return Number.isNaN(num) ? 220 : num;
};

/** 获取 CSS 变量并解析为 ECharts 可用的颜色字符串 */
const getVbenColor = (varName: string): string => {
  if (typeof window === 'undefined') return '';
  const style = getComputedStyle(document.documentElement);
  const value = style.getPropertyValue(varName).trim();
  if (!value) return '';
  return value.includes('(') ? value : `hsl(${value})`;
};

/** 判断标签是否在左侧区域（需要添加空格后缀） */
const isLeftSide = (index: number, count: number): boolean => {
  // ECharts 雷达图从顶部开始按逆时针方向排列标签
  const angle = -(index / count) * 2 * Math.PI - Math.PI / 2;
  return Math.cos(angle) < -0.3;
};

/** 生成带空格后缀的标签名（左侧标签添加空格为问号留位置） */
const getIndicatorName = (
  score: ScoreItem,
  index: number,
  count: number,
): string => {
  if (score.prompt && isLeftSide(index, count)) {
    return `${score.label}   `; // 左侧标签加3个空格
  }
  return score.label;
};

/** 计算维度标签的 DOM 位置（用于显示评分理由） */
const labelPositions = computed(() => {
  const width = parseSize(props.width);
  const height = parseSize(props.height);
  const centerX = width / 2;
  const centerY = height / 2;

  // 雷达图半径
  const radiusPercent = Number.parseInt(props.radius, 10) || 65;
  const radius = (Math.min(width, height) * (radiusPercent / 100)) / 2;

  // 标签位置在雷达图外围
  const labelRadius = radius + 20;

  const positions: Array<{
    height: number;
    score: ScoreItem;
    width: number;
    x: number;
    y: number;
  }> = [];

  const count = props.scores.length;
  props.scores.forEach((score, index) => {
    if (!score.reason) return; // 只为有 reason 的维度添加 hover 区域

    const angle = -(index / count) * 2 * Math.PI - Math.PI / 2;
    const anchorX = centerX + labelRadius * Math.cos(angle);
    const anchorY = centerY + labelRadius * Math.sin(angle);

    // 估算标签尺寸
    const labelWidth = score.label.length * 12 + 16;
    const labelHeight = 20;

    // 根据标签对齐方式计算 hover 区域位置
    const cosAngle = Math.cos(angle);
    let x = anchorX;

    if (Math.abs(cosAngle) < 0.3) {
      // 顶部或底部：标签居中对齐
      x -= labelWidth / 2;
    } else if (cosAngle > 0) {
      // 右侧：标签左对齐
      x -= 4;
    } else {
      // 左侧：标签右对齐
      x -= labelWidth + 4;
    }

    positions.push({
      score,
      x,
      y: anchorY - labelHeight / 2,
      width: labelWidth,
      height: labelHeight,
    });
  });

  return positions;
});

/** 计算每个有 prompt 的维度问号图标的 DOM 位置 */
const hintPositions = computed(() => {
  const width = parseSize(props.width);
  const height = parseSize(props.height);
  const centerX = width / 2;
  const centerY = height / 2;

  // 雷达图半径
  const radiusPercent = Number.parseInt(props.radius, 10) || 65;
  const radius = (Math.min(width, height) * (radiusPercent / 100)) / 2;

  // 标签位置在雷达图外围（ECharts 默认标签距离）
  const labelRadius = radius + 20;

  const positions: Array<{
    score: ScoreItem;
    x: number;
    y: number;
  }> = [];

  const count = props.scores.length;
  props.scores.forEach((score, index) => {
    if (!score.prompt) return; // 只为有 prompt（规则）的维度添加问号

    // 从顶部开始，逆时针方向（与 ECharts 雷达图一致）
    const angle = -(index / count) * 2 * Math.PI - Math.PI / 2;

    // 标签锚点位置
    const anchorX = centerX + labelRadius * Math.cos(angle);
    const anchorY = centerY + labelRadius * Math.sin(angle);

    // 估算标签宽度（中文字符约12px宽）
    const labelWidth = score.label.length * 12;

    // 根据 ECharts 标签对齐方式计算问号位置
    let x = anchorX;
    const y = anchorY;

    // ECharts 雷达图标签对齐规则：
    // - 顶部/底部区域（cos角度接近0）：center 对齐
    // - 右侧区域（cos > 0）：left 对齐（文字向右延伸）
    // - 左侧区域（cos < 0）：right 对齐（文字向左延伸，但我们加了空格）

    const cosAngle = Math.cos(angle);

    if (Math.abs(cosAngle) < 0.3) {
      // 顶部或底部：标签居中对齐，问号在标签右边缘
      x += labelWidth / 2 + 6;
    } else if (cosAngle > 0) {
      // 右侧：标签左对齐（从锚点向右），问号在标签末尾
      x += labelWidth + 6;
    } else {
      // 左侧：标签右对齐，但加了空格后缀，问号放在空格区域
      // 空格在锚点右侧，所以问号位置在锚点偏右
      x += 8;
    }

    positions.push({ x, y, score });
  });

  return positions;
});

/** 图表配置 */
const chartOptions = computed<EChartsOption>(() => ({
  radar: {
    indicator: props.scores.map((s, idx) => ({
      name: getIndicatorName(s, idx, props.scores.length),
      max: props.maxScore,
    })),
    radius: props.radius,
    splitNumber: 5,
    axisName: {
      fontSize: 12,
      color: getVbenColor('--foreground') || '#e5e7eb',
    },
    axisNameGap: 12,
    splitLine: {
      lineStyle: {
        color: 'rgba(128, 128, 128, 0.15)', // 淡化分隔线，不影响分值查看
        width: 1,
      },
    },
    splitArea: {
      show: true,
      areaStyle: {
        // 更淡的渐变色，突出数据区域
        color: [
          'rgba(99, 102, 241, 0.12)', // 最内层
          'rgba(99, 102, 241, 0.08)',
          'rgba(99, 102, 241, 0.05)',
          'rgba(99, 102, 241, 0.03)',
          'rgba(99, 102, 241, 0.01)', // 最外层
        ],
      },
    },
    axisLine: {
      lineStyle: {
        color: 'rgba(128, 128, 128, 0.12)', // 淡化轴线
        width: 1,
      },
    },
  },
  series: [
    {
      type: 'radar',
      data: [
        {
          value: props.scores.map((s) => s.score),
          name: props.seriesName,
          areaStyle: {
            color: getColorWithAlpha(props.themeColor, 0.3),
          },
          lineStyle: {
            color: props.themeColor,
            width: 2,
          },
          itemStyle: {
            color: props.themeColor,
          },
          label: {
            show: props.showLabel,
            formatter: (params: { value: number }) => {
              return params.value > 0 ? String(params.value) : '';
            },
            color: 'hsl(var(--muted-foreground))',
            fontSize: 11,
          },
        },
      ],
      symbolSize: 6,
    },
  ],
  tooltip: {
    show: false,
  },
}));

/** 渲染图表 */
const renderChart = () => {
  if (!chartRef.value || props.scores.length === 0) return;

  // 初始化图表实例
  if (!chartInstance.value) {
    chartInstance.value = echarts.init(chartRef.value);
  }

  // 设置配置
  chartInstance.value.setOption(chartOptions.value);
};

/** 销毁图表实例 */
const disposeChart = () => {
  if (chartInstance.value) {
    chartInstance.value.dispose();
    chartInstance.value = null;
  }
};

onMounted(() => {
  renderChart();
});

// 监听 scores 变化重新渲染
watch(
  () => props.scores,
  () => {
    renderChart();
  },
  { deep: true },
);

// 组件卸载时销毁图表实例
onUnmounted(() => {
  disposeChart();
});

// 监听宽度/高度变化，重新初始化图表
watch(
  () => [props.width, props.height],
  () => {
    disposeChart();
    renderChart();
  },
);
</script>

<template>
  <div
    class="score-radar-wrapper"
    :style="{ width: props.width, height: props.height }"
  >
    <div
      ref="chartRef"
      class="score-radar-chart"
      :style="{ width: props.width, height: props.height }"
    ></div>
    <!-- 维度标签 hover 区域（显示 AI 评分理由） -->
    <Popover
      v-for="(pos, idx) in labelPositions"
      :key="`label-${idx}`"
      placement="top"
      :overlay-style="{ maxWidth: '320px' }"
    >
      <template #content>
        <div class="reason-popover">
          <div class="popover-title">
            {{ pos.score.label }}：{{ pos.score.score }}分
          </div>
          <div class="popover-reason">
            {{ pos.score.reason }}
          </div>
        </div>
      </template>
      <span
        class="label-hover-area"
        :style="{
          left: `${pos.x}px`,
          top: `${pos.y}px`,
          width: `${pos.width}px`,
          height: `${pos.height}px`,
        }"
      ></span>
    </Popover>
    <!-- 问号图标覆盖层（显示 AI 评分规则） -->
    <Popover
      v-for="(pos, idx) in hintPositions"
      :key="`hint-${idx}`"
      placement="top"
      :overlay-style="{ maxWidth: '400px' }"
    >
      <template #content>
        <div class="rule-popover">
          <div class="popover-title">{{ pos.score.label }} - 评分规则</div>
          <div class="popover-prompt">
            {{ pos.score.prompt }}
          </div>
        </div>
      </template>
      <span
        class="hint-icon-wrapper"
        :style="{
          left: `${pos.x}px`,
          top: `${pos.y}px`,
        }"
      >
        <QuestionCircleOutlined class="hint-icon" />
      </span>
    </Popover>
  </div>
</template>

<style scoped>
.score-radar-wrapper {
  position: relative;
  display: inline-block;
}

.score-radar-chart {
  min-width: 200px;
  min-height: 180px;
}

/* 问号图标包装器 */
.hint-icon-wrapper {
  position: absolute;
  z-index: 10;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  cursor: pointer;
  transform: translate(-50%, -50%);
}

.hint-icon {
  font-size: 12px;
  color: hsl(var(--primary));
  opacity: 0.7;
  transition: all 0.2s;
}

.hint-icon-wrapper:hover .hint-icon {
  opacity: 1;
  transform: scale(1.2);
}

/* Popover 内容样式 - 规则展示 */
.rule-popover {
  max-width: 380px;
  max-height: 300px;
  overflow-y: auto;
}

.popover-title {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.popover-prompt {
  font-size: 12px;
  line-height: 1.6;
  color: hsl(var(--muted-foreground));
  overflow-wrap: break-word;
  white-space: pre-wrap;
}

/* 维度标签 hover 区域 */
.label-hover-area {
  position: absolute;
  z-index: 5;
  cursor: pointer;
  background: transparent;
}

.label-hover-area:hover {
  background: hsl(var(--primary) / 8%);
  border-radius: 4px;
}

/* Popover 内容样式 - 理由展示 */
.reason-popover {
  max-width: 300px;
}

.popover-reason {
  font-size: 12px;
  line-height: 1.5;
  color: hsl(var(--muted-foreground));
  white-space: pre-wrap;
}
</style>
