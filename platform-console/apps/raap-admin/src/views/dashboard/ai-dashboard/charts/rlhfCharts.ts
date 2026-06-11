// @ts-nocheck
/**
 * RLHF 人工专家反馈报告图表配置
 *
 * 反馈标签柱状图、词云图、雷达图、对比雷达图
 */

import type { EchartsOption } from '@vben/plugins/echarts';

import type {
  RLHFIssueTagDistribution,
  RLHFIssueTagWordCloud,
  RLHFScoreDimension,
} from '../types';

import { getVbenColor } from '../utils';

// ==================== 颜色配置 ====================

const BAR_COLORS = [
  '#3b82f6',
  '#22c55e',
  '#f59e0b',
  '#ef4444',
  '#8b5cf6',
  '#06b6d4',
] as const;

const WORD_CLOUD_COLORS = [
  '#3b82f6',
  '#22c55e',
  '#f59e0b',
  '#ef4444',
  '#8b5cf6',
  '#06b6d4',
  '#ec4899',
  '#14b8a6',
] as const;

// ==================== 反馈标签柱状图 ====================

/**
 * 创建反馈标签分布柱状图配置
 */
export function createRLHFIssueBarChartOption(
  issueTagDistribution: RLHFIssueTagDistribution[],
): EchartsOption {
  if (issueTagDistribution.length === 0) {
    return {
      graphic: {
        type: 'text',
        left: 'center',
        top: 'middle',
        style: {
          text: '暂无数据',
          fill: getVbenColor('--muted-foreground'),
          fontSize: 14,
        },
      },
    };
  }

  // 按分类分组
  const categoryGroups: Record<string, RLHFIssueTagDistribution[]> = {};
  for (const item of issueTagDistribution) {
    if (!categoryGroups[item.tag_category]) {
      categoryGroups[item.tag_category] = [];
    }
    categoryGroups[item.tag_category].push(item);
  }

  const categories = Object.keys(categoryGroups);
  const topIssues = issueTagDistribution.slice(0, 10);

  return {
    grid: {
      left: '10%',
      right: '5%',
      bottom: '15%',
      top: '10%',
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params: { name: string; value: number }[]) => {
        return params.map((p) => `${p.name}: ${p.value} 次`).join('<br/>');
      },
    },
    xAxis: {
      type: 'category',
      data: topIssues.map((i) => i.tag_name),
      axisLabel: {
        color: getVbenColor('--foreground'),
        fontSize: 10,
        rotate: 30,
      },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        color: getVbenColor('--foreground'),
      },
      splitLine: {
        lineStyle: {
          color: getVbenColor('--border'),
        },
      },
    },
    series: [
      {
        type: 'bar',
        data: topIssues.map((item, index) => ({
          value: item.count,
          itemStyle: {
            color: BAR_COLORS[index % BAR_COLORS.length],
          },
        })),
        barWidth: '60%',
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
        },
      },
    ],
  };
}

// ==================== 反馈词词云图 ====================

/**
 * 创建反馈词词云图配置
 */
export function createRLHFWordCloudChartOption(
  wordCloudData: RLHFIssueTagWordCloud[],
): EchartsOption {
  if (wordCloudData.length === 0) {
    return {
      graphic: {
        type: 'text',
        left: 'center',
        top: 'middle',
        style: {
          text: '暂无数据',
          fill: getVbenColor('--muted-foreground'),
          fontSize: 14,
        },
      },
    };
  }

  return {
    grid: {
      left: '5%',
      right: '5%',
      bottom: '5%',
      top: '5%',
    },
    tooltip: {},
    series: [
      {
        type: 'wordCloud',
        gridSize: 8,
        sizeRange: [12, 32],
        rotationRange: [-45, 90],
        shape: 'circle',
        width: '100%',
        height: '100%',
        drawOutOfBound: false,
        textStyle: {
          fontFamily: 'sans-serif',
          fontWeight: 'bold',
        },
        emphasis: {
          textStyle: {
            textShadowColor: getVbenColor('--background'),
            textShadowBlur: 5,
          },
        },
        data: wordCloudData.map((item, index) => ({
          name: item.name,
          value: item.value,
          textStyle: {
            color: WORD_CLOUD_COLORS[index % WORD_CLOUD_COLORS.length],
          },
        })),
      },
    ],
  };
}

// ==================== RLHF 雷达图 ====================

/**
 * 创建 RLHF 雷达图配置
 */
export function createRLHFRadarChartOption(
  radarScores: RLHFScoreDimension[],
): EchartsOption {
  if (radarScores.length === 0) {
    return {
      graphic: {
        type: 'text',
        left: 'center',
        top: 'middle',
        style: {
          text: '暂无数据',
          fill: getVbenColor('--muted-foreground'),
          fontSize: 14,
        },
      },
    };
  }

  const indicators = radarScores.map((s) => ({
    name: s.name,
    max: 100,
  }));

  const values = radarScores.map((s) => s.value);

  return {
    radar: {
      center: ['50%', '50%'],
      radius: '65%',
      startAngle: 90,
      splitNumber: 5,
      axisName: {
        color: getVbenColor('--foreground'),
        fontSize: 11,
      },
      axisLine: {
        lineStyle: {
          color: getVbenColor('--border'),
        },
      },
      splitLine: {
        lineStyle: {
          color: getVbenColor('--border'),
        },
      },
      splitArea: {
        show: true,
        areaStyle: {
          color: [`${getVbenColor('--muted-foreground')}08`, 'transparent'],
        },
      },
      indicator: indicators,
    },
    series: [
      {
        type: 'radar',
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: {
          width: 2,
          color: '#22c55e',
        },
        itemStyle: {
          color: '#22c55e',
          borderColor: '#fff',
          borderWidth: 2,
        },
        areaStyle: {
          color: 'rgba(34, 197, 94, 0.2)',
        },
        data: [
          {
            value: values,
            name: '人工评分',
          },
        ],
      },
    ],
  };
}

// ==================== RLHF 对比雷达图 ====================

/**
 * 创建 RLHF 对比雷达图配置（AI vs 人工）
 */
export function createRLHFRadarCompareChartOption(
  radarScores: RLHFScoreDimension[],
): EchartsOption {
  if (radarScores.length === 0) {
    return {
      graphic: {
        type: 'text',
        left: 'center',
        top: 'middle',
        style: {
          text: '暂无数据',
          fill: getVbenColor('--muted-foreground'),
          fontSize: 14,
        },
      },
    };
  }

  const indicators = radarScores.map((s) => ({
    name: s.name,
    max: 100,
  }));

  const aiScores = radarScores.map((s) => s.modelScore ?? s.value);
  const humanScores = radarScores.map((s) => s.inspectionScore ?? s.value);

  return {
    legend: {
      data: ['AI模型评分', '人工抽检评分'],
      bottom: 0,
      textStyle: {
        color: getVbenColor('--foreground'),
      },
    },
    radar: {
      center: ['50%', '45%'],
      radius: '60%',
      startAngle: 90,
      splitNumber: 5,
      axisName: {
        color: getVbenColor('--foreground'),
        fontSize: 10,
      },
      axisLine: {
        lineStyle: {
          color: getVbenColor('--border'),
        },
      },
      splitLine: {
        lineStyle: {
          color: getVbenColor('--border'),
        },
      },
      splitArea: {
        show: true,
        areaStyle: {
          color: [`${getVbenColor('--muted-foreground')}08`, 'transparent'],
        },
      },
      indicator: indicators,
    },
    series: [
      {
        type: 'radar',
        symbol: 'circle',
        symbolSize: 5,
        lineStyle: {
          width: 2,
        },
        itemStyle: {
          borderColor: '#fff',
          borderWidth: 1,
        },
        areaStyle: { opacity: 0.2 },
        data: [
          {
            value: aiScores,
            name: 'AI模型评分',
            lineStyle: { color: '#3b82f6' },
            itemStyle: { color: '#3b82f6' },
            areaStyle: { color: 'rgba(59, 130, 246, 0.2)' },
          },
          {
            value: humanScores,
            name: '人工抽检评分',
            lineStyle: { color: '#22c55e' },
            itemStyle: { color: '#22c55e' },
            areaStyle: { color: 'rgba(34, 197, 94, 0.2)' },
          },
        ],
      },
    ],
  };
}
