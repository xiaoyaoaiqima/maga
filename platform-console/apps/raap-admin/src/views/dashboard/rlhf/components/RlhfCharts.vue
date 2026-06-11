<script setup lang="ts">
// @ts-nocheck
import type { EchartsUIType } from '@vben/plugins/echarts';

import type { RLHFIssueTagDistribution, RLHFScoreDimension } from '../types';

import { computed, nextTick, onMounted, ref, watch } from 'vue';

import { EchartsUI } from '@vben/plugins/echarts';
import { usePreferences } from '@vben/preferences';

import { QuestionCircleOutlined } from '@ant-design/icons-vue';
import { Card as ACard, Col, Row, Skeleton, Tooltip } from 'ant-design-vue';

interface Props {
  scoreDimensions: RLHFScoreDimension[];
  issueTags: RLHFIssueTagDistribution[];
  loading: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  scoreDimensions: () => [],
  issueTags: () => [],
  loading: false,
});

const { isDark } = usePreferences();

const radarChartRef = ref<EchartsUIType>();
const wordCloudChartRef = ref<EchartsUIType>();

// 维度颜色
const dimensionColors = [
  '#3b82f6', // blue
  '#22c55e', // green
  '#f59e0b', // amber
  '#ef4444', // red
  '#8b5cf6', // violet
  '#ec4899', // pink
];

// 转换标签数据为词云格式
const wordCloudData = computed(() => {
  return props.issueTags.map((tag) => ({
    name: tag.tag_name || tag.tag,
    value: tag.count,
    category: tag.tag_category,
  }));
});

// 初始化雷达图
const initRadarChart = () => {
  if (!radarChartRef.value) return;

  const dimensions =
    props.scoreDimensions.length > 0
      ? props.scoreDimensions
      : [
          { dimension: '平台适应度', score: 85, full_score: 100 },
          { dimension: '整体内容质量', score: 78, full_score: 100 },
          { dimension: '品牌调性匹配', score: 82, full_score: 100 },
          { dimension: '内容创造力', score: 75, full_score: 100 },
          { dimension: '内容人设一致性', score: 88, full_score: 100 },
          { dimension: '语法正确性', score: 90, full_score: 100 },
        ];

  const indicator = dimensions.map((d, i) => ({
    name: d.dimension,
    max: d.full_score || 100,
    color: dimensionColors[i % dimensionColors.length],
  }));

  const values = dimensions.map((d) => d.score);

  radarChartRef.value.setOptions({
    backgroundColor: 'transparent',
    animationDuration: 2000,
    animationEasing: 'elasticOut',
    tooltip: {
      trigger: 'item',
      backgroundColor: isDark.value
        ? 'rgba(15, 23, 42, 0.95)'
        : 'rgba(255, 255, 255, 0.95)',
      borderColor: isDark.value
        ? 'rgba(102, 126, 234, 0.3)'
        : 'rgba(0, 0, 0, 0.1)',
      borderWidth: 1,
      borderRadius: 12,
      padding: [12, 16],
      textStyle: {
        color: isDark.value ? '#fff' : '#1e293b',
        fontSize: 12,
      },
      formatter: (_params: any) => {
        let result =
          '<div style="font-weight: 600; margin-bottom: 8px;">RLHF 评分详情</div>';
        dimensions.forEach((dim, i) => {
          const val = values[i];
          const color = dimensionColors[i % dimensionColors.length];
          const level =
            val >= 80
              ? '优秀'
              : val >= 60
                ? '良好'
                : val >= 40
                  ? '一般'
                  : '待提升';
          result += `<div style="margin: 6px 0; display: flex; justify-content: space-between;">
            <span style="display: flex; align-items: center; gap: 6px;">
              <span style="width: 8px; height: 8px; border-radius: 50%; background: ${color};"></span>
              ${dim.dimension}
            </span>
            <span style="color: ${color}; font-weight: 700;">${val} <span style="font-size: 10px; opacity: 0.8;">(${level})</span></span>
          </div>`;
        });
        return result;
      },
    },
    radar: {
      indicator,
      center: ['50%', '55%'],
      radius: '60%',
      splitNumber: 5,
      splitArea: {
        show: true,
        areaStyle: {
          color: isDark.value
            ? [
                'rgba(102, 126, 234, 0.05)',
                'rgba(102, 126, 234, 0.1)',
                'rgba(102, 126, 234, 0.15)',
                'rgba(102, 126, 234, 0.2)',
                'rgba(102, 126, 234, 0.25)',
              ]
            : [
                'rgba(59, 130, 246, 0.05)',
                'rgba(59, 130, 246, 0.1)',
                'rgba(59, 130, 246, 0.15)',
                'rgba(59, 130, 246, 0.2)',
                'rgba(59, 130, 246, 0.25)',
              ],
        },
      },
      splitLine: {
        lineStyle: {
          color: isDark.value
            ? 'rgba(102, 126, 234, 0.2)'
            : 'rgba(59, 130, 246, 0.2)',
          width: 1,
        },
      },
      axisLine: {
        lineStyle: {
          color: isDark.value
            ? 'rgba(102, 126, 234, 0.3)'
            : 'rgba(59, 130, 246, 0.3)',
          width: 1,
        },
      },
      axisName: {
        color: isDark.value ? '#cbd5e1' : '#475569',
        fontSize: 12,
        fontWeight: 500,
      },
    },
    series: [
      {
        type: 'radar',
        symbol: 'circle',
        symbolSize: 6,
        data: [
          {
            value: values,
            name: 'RLHF 评分',
            itemStyle: {
              color: '#3b82f6',
              borderColor: '#60a5fa',
              borderWidth: 2,
            },
            areaStyle: {
              color: 'rgba(59, 130, 246, 0.25)',
            },
            lineStyle: {
              color: '#3b82f6',
              width: 2,
            },
          },
        ],
      },
    ],
  });
};

// 初始化词云图
const initWordCloudChart = () => {
  if (!wordCloudChartRef.value) return;

  const data =
    wordCloudData.value.length > 0
      ? wordCloudData.value
      : [
          { name: '不合规', value: 15, category: 'non_compliant' },
          { name: '不合理', value: 12, category: 'unreasonable' },
          { name: '不合目的', value: 10, category: 'off_purpose' },
          { name: '逻辑问题', value: 8, category: 'other' },
          { name: '语法错误', value: 6, category: 'other' },
          { name: '人设不符', value: 5, category: 'other' },
        ];

  // 标签颜色映射
  const tagColorMap: Record<string, string> = {
    illegal: '#ef4444',
    non_compliant: '#f59e0b',
    unreasonable: '#ec4899',
    off_purpose: '#8b5cf6',
    other: '#6b7280',
  };

  wordCloudChartRef.value.setOptions({
    backgroundColor: 'transparent',
    tooltip: {
      backgroundColor: isDark.value
        ? 'rgba(15, 23, 42, 0.95)'
        : 'rgba(255, 255, 255, 0.95)',
      borderColor: isDark.value
        ? 'rgba(102, 126, 234, 0.3)'
        : 'rgba(0, 0, 0, 0.1)',
      borderWidth: 1,
      borderRadius: 8,
      padding: [8, 12],
      textStyle: {
        color: isDark.value ? '#fff' : '#1e293b',
        fontSize: 12,
      },
      formatter: (_params: any) => {
        return `${params.name}: ${params.value}条`;
      },
    },
    series: [
      {
        type: 'wordCloud',
        gridSize: 8,
        sizeRange: [12, 32],
        rotationRange: [-45, 45],
        rotationStep: 15,
        shape: 'circle',
        width: '100%',
        height: '100%',
        drawOutOfBound: false,
        textStyle: {
          fontFamily: 'sans-serif',
          fontWeight: 'bold',
          color: (params: any) => {
            const category = params.data?.category || 'other';
            return tagColorMap[category] || tagColorMap.other;
          },
        },
        emphasis: {
          focus: 'self',
          textStyle: {
            textShadowBlur: 10,
            textShadowColor: 'rgba(0, 0, 0, 0.3)',
          },
        },
        data,
      },
    ],
  });
};

// 刷新图表
const refreshCharts = async () => {
  await nextTick();
  initRadarChart();
  initWordCloudChart();
};

// 监听数据变化
watch(
  () => [props.scoreDimensions, props.issueTags, isDark.value],
  () => {
    refreshCharts();
  },
  { deep: true },
);

onMounted(() => {
  refreshCharts();
});
</script>

<template>
  <div class="rlhf-charts-section">
    <div class="rlhf-section-subtitle">
      评分反馈结果
      <Tooltip placement="right">
        <template #title>
          <div class="dimension-tooltip">
            <div class="tooltip-item">
              <b>平台适应度</b>：评估内容是否符合目标平台的调性、风格和用户习惯
            </div>
            <div class="tooltip-item">
              <b>整体内容质量</b>：综合评估内容的完整性、逻辑性和可读性
            </div>
            <div class="tooltip-item">
              <b>品牌调性匹配</b
              >：评估内容是否与品牌形象、价值观和沟通风格保持一致
            </div>
            <div class="tooltip-item">
              <b>内容创造力</b>：评估内容的原创性、新颖度和吸引力
            </div>
            <div class="tooltip-item">
              <b>内容人设一致性</b>：评估内容是否符合预设的人物设定
            </div>
            <div class="tooltip-item">
              <b>语法正确性</b>：评估内容的语法规范性、用词准确性和表达流畅度
            </div>
          </div>
        </template>
        <QuestionCircleOutlined class="info-icon" />
      </Tooltip>
    </div>

    <Row :gutter="24" class="mt-2">
      <!-- 雷达图 -->
      <Col :span="12">
        <ACard :bordered="false" class="rlhf-chart-card">
          <Skeleton :loading="loading" active :paragraph="{ rows: 4 }">
            <div class="rlhf-card-content">
              <div class="rlhf-chart-title">
                <span class="rlhf-title-indicator indicator-blue"></span>
                <span>人工专家反馈综合评分</span>
              </div>
              <div class="h-[320px]">
                <EchartsUI ref="radarChartRef" height="320px" width="100%" />
              </div>
            </div>
          </Skeleton>
        </ACard>
      </Col>

      <!-- 词云图 -->
      <Col :span="12">
        <ACard :bordered="false" class="rlhf-chart-card">
          <Skeleton :loading="loading" active :paragraph="{ rows: 4 }">
            <div class="rlhf-card-content">
              <div class="rlhf-chart-title">
                <span class="rlhf-title-indicator indicator-purple"></span>
                <span>问题标签分布</span>
              </div>
              <div class="h-[320px]">
                <EchartsUI
                  ref="wordCloudChartRef"
                  height="320px"
                  width="100%"
                />
              </div>
            </div>
          </Skeleton>
        </ACard>
      </Col>
    </Row>
  </div>
</template>

<style scoped>
.rlhf-charts-section {
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

.info-icon {
  font-size: 14px;
  color: hsl(var(--muted-foreground));
  cursor: help;
}

.dimension-tooltip {
  max-width: 300px;
  font-size: 12px;
  line-height: 1.6;
}

.tooltip-item {
  margin-bottom: 8px;
}

.tooltip-item:last-child {
  margin-bottom: 0;
}

.rlhf-chart-card {
  overflow: hidden;
  background: hsl(var(--card) / 60%);
  border: 1px solid hsl(var(--border) / 50%);
  border-radius: 16px;
  box-shadow: 0 4px 12px hsl(var(--foreground) / 5%);
  backdrop-filter: blur(10px);
}

.rlhf-card-content {
  position: relative;
}

.rlhf-chart-title {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 16px;
  font-size: 14px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.rlhf-title-indicator {
  width: 4px;
  height: 16px;
  border-radius: 2px;
}

.indicator-blue {
  background: linear-gradient(180deg, #3b82f6, #22c55e);
}

.indicator-purple {
  background: linear-gradient(180deg, #8b5cf6, #ec4899);
}
</style>
