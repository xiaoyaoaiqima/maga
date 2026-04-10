/**
 * 评审专家模块图表配置
 *
 * 评分雷达图、人群多样性热力图、内容丰富度散点图
 */

import type { EchartsOption } from '@vben/plugins/echarts';

import type {
  AgentPersonaHeatmapItem,
  CriticExpertScoreDistribution10,
  QualityDimension,
} from '../types';

import { getVbenColor } from '../utils';

// ==================== 颜色配置 ====================

const HEATMAP_COLORS = [
  '#f0f9ff',
  '#cbebff',
  '#a1dbff',
  '#75c7ff',
  '#4badff',
  '#1e96ff',
] as const;

const SCATTER_COLORS = [
  '#3b82f6',
  '#22c55e',
  '#f59e0b',
  '#ef4444',
  '#8b5cf6',
  '#06b6d4',
  '#ec4899',
  '#14b8a6',
] as const;

// ==================== 评分雷达图 ====================

/**
 * 创建评分雷达图配置
 */
export function createScoringRadarChartOption(
  scoringExperts: QualityDimension[],
): EchartsOption {
  if (scoringExperts.length === 0) {
    return {
      graphic: {
        type: 'text',
        left: 'center',
        top: 'middle',
        style: {
          text: '暂无评分数据',
          fill: getVbenColor('--muted-foreground'),
          fontSize: 14,
        },
      },
    };
  }

  const indicators = scoringExperts.map((item) => ({
    name: item.expert_name,
    max: 100,
  }));

  const values = scoringExperts.map((item) => item.avg_score || 0);

  return {
    tooltip: {
      trigger: 'item',
      formatter: (params: { name: string }) => params.name,
    },
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
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
            { offset: 0, color: '#3b82f6' },
            { offset: 1, color: '#8b5cf6' },
          ]),
        },
        itemStyle: {
          color: '#3b82f6',
          borderColor: '#fff',
          borderWidth: 2,
        },
        areaStyle: {
          color: new echarts.graphic.RadialGradient(0.5, 0.5, 1, [
            { offset: 0, color: 'rgba(59, 130, 246, 0.3)' },
            { offset: 1, color: 'rgba(139, 92, 246, 0.1)' },
          ]),
        },
        data: [
          {
            value: values,
            name: '评分概览',
          },
        ],
      },
    ],
  };
}

// ==================== 人群多样性热力图 ====================

/**
 * 创建人群多样性热力图配置
 */
export function createStatisticsHeatmapChartOption(
  agentPersonaHeatmapData: AgentPersonaHeatmapItem[],
): EchartsOption {
  if (agentPersonaHeatmapData.length === 0) {
    return {
      backgroundColor: 'transparent',
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

  // 提取唯一的 Agent 和 Persona
  const agents = [
    ...new Set(
      agentPersonaHeatmapData.map((d) => d.agent_name || d.agent_code),
    ),
  ];
  const personas = [
    ...new Set(agentPersonaHeatmapData.map((d) => d.persona_name)),
  ].toSorted();

  // 构建热力图数据
  const data = agentPersonaHeatmapData.map((item) => {
    const agentIndex = agents.indexOf(item.agent_name || item.agent_code);
    const personaIndex = personas.indexOf(item.persona_name);
    return [agentIndex, personaIndex, item.content_count];
  });

  return {
    backgroundColor: 'transparent',
    tooltip: {
      position: 'top',
      formatter: (params: { data: (number | string)[] }) => {
        const agent = agents[params.data[0] as number];
        const persona = personas[params.data[1] as number];
        const count = params.data[2];
        return `${agent} × ${persona}<br/>内容数: ${count}`;
      },
    },
    grid: {
      height: '70%',
      top: '10%',
    },
    xAxis: {
      type: 'category',
      data: agents,
      splitArea: { show: true },
      axisLabel: {
        color: getVbenColor('--foreground'),
        fontSize: 10,
        rotate: agents.length > 5 ? 30 : 0,
      },
    },
    yAxis: {
      type: 'category',
      data: personas,
      splitArea: { show: true },
      axisLabel: {
        color: getVbenColor('--foreground'),
        fontSize: 10,
      },
    },
    visualMap: {
      min: 0,
      max: Math.max(...data.map((d) => d[2] as number)),
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: '0%',
      inRange: {
        color: HEATMAP_COLORS,
      },
      textStyle: {
        color: getVbenColor('--foreground'),
      },
    },
    series: [
      {
        type: 'heatmap',
        data: data as [number, number, number][],
        label: {
          show: true,
          formatter: (params: { data: (number | string)[] }) =>
            params.data[2] as string,
          color: getVbenColor('--background'),
          fontSize: 10,
        },
        itemStyle: {
          emphasis: {
            shadowBlur: 10,
            shadowColor: 'rgba(0, 0, 0, 0.5)',
          },
        },
      },
    ],
  };
}

// ==================== 内容丰富度散点图 ====================

/**
 * 创建内容丰富度散点图配置
 */
export function createContentRichnessScatterOption(
  criticExpertScoreDist10: CriticExpertScoreDistribution10[],
): EchartsOption {
  if (criticExpertScoreDist10.length === 0) {
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

  // 提取唯一的专家
  const experts = [
    ...new Set(criticExpertScoreDist10.map((d) => d.expert_name)),
  ];

  // 构建散点数据
  const scatterData = criticExpertScoreDist10.map((item, index) => ({
    value: [item.score_range + 5, item.content_count],
    itemStyle: {
      color:
        SCATTER_COLORS[
          experts.indexOf(item.expert_name) % SCATTER_COLORS.length
        ],
    },
    expert: item.expert_name,
  }));

  return {
    grid: {
      left: '10%',
      right: '5%',
      bottom: '10%',
      top: '10%',
    },
    tooltip: {
      trigger: 'item',
      formatter: (params: { data: { expert: string; value: number[] } }) => {
        const score = params.data.value[0];
        const count = params.data.value[1];
        const expert = params.data.expert;
        return `${expert}<br/>分数区间: ${score - 5}-${score + 4}<br/>文章数: ${count}`;
      },
    },
    xAxis: {
      name: '分数',
      type: 'category',
      data: Array.from({ length: 10 }, (_, i) => `${i * 10}-${i * 10 + 9}`),
      axisLabel: {
        color: getVbenColor('--foreground'),
        fontSize: 10,
      },
      nameTextStyle: {
        color: getVbenColor('--foreground'),
      },
    },
    yAxis: {
      name: '文章数',
      type: 'value',
      axisLabel: {
        color: getVbenColor('--foreground'),
      },
      nameTextStyle: {
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
        type: 'scatter',
        symbolSize: (data: number[]) =>
          Math.min(50, Math.max(10, Math.sqrt(data[1]) * 5)),
        data: scatterData,
      },
    ],
  };
}

// echarts 全局对象类型声明
declare const echarts: any;
