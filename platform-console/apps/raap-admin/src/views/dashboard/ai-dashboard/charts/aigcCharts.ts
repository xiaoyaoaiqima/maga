// @ts-nocheck
/**
 * AIGC 生成中心图表配置
 *
 * AIGC 环形图、Agent 生成趋势图
 */

import type { EchartsOption } from '@vben/plugins/echarts';

import type { AgentContentTrend, AgentStat } from '../types';

// 导入 dayjs
import dayjs from 'dayjs';

import { getVbenColor } from '../utils';

// ==================== 图表颜色 ====================

const AIGC_CHART_COLORS = [
  '#3b82f6', // blue
  '#22c55e', // green
  '#f59e0b', // amber
  '#ef4444', // red
  '#8b5cf6', // violet
  '#06b6d4', // cyan
  '#ec4899', // pink
  '#14b8a6', // teal
  '#f97316', // orange
  '#6366f1', // indigo
] as const;

// ==================== 辅助函数 ====================

/**
 * 获取 Agent 的生成数量
 */
export function getContentCount(agent: AgentStat): number {
  return Number(agent.content_count ?? agent.total_calls ?? 0);
}

// ==================== AIGC 环形图 ====================

/**
 * 创建空 AIGC 环形图配置
 */
export function createEmptyAigcDonutChartOption(): EchartsOption {
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

/**
 * 创建 AIGC 环形图配置
 */
export function createAigcDonutChartOption(
  agentStatsList: AgentStat[],
): EchartsOption {
  const pieData = agentStatsList.map((agent, index) => ({
    name: agent.agent_name || agent.agent_code,
    value: getContentCount(agent),
    agent_code: agent.agent_code,
    itemStyle: { color: AIGC_CHART_COLORS[index % AIGC_CHART_COLORS.length] },
  }));

  return {
    tooltip: {
      trigger: 'item',
      formatter: (params: { name: string; percent: number; value: number }) => {
        return `${params.name}<br/>生成文章数量: ${params.value.toLocaleString()} (${params.percent}%)`;
      },
    },
    legend: {
      type: 'scroll',
      orient: 'horizontal',
      bottom: 0,
      left: 'center',
      width: '90%',
      textStyle: {
        color: getVbenColor('--foreground'),
        fontSize: 11,
        width: 80,
        overflow: 'truncate',
        ellipsis: '...',
      },
      tooltip: {
        show: true,
      },
      pageTextStyle: {
        color: getVbenColor('--foreground'),
      },
      pageIconColor: getVbenColor('--foreground'),
      pageIconInactiveColor: getVbenColor('--muted-foreground'),
      pageIconSize: 10,
      pageButtonGap: 5,
      itemWidth: 10,
      itemHeight: 10,
      itemGap: 6,
      formatter: (name: string) => {
        return name.length > 10 ? `${name.slice(0, 10)}...` : name;
      },
    },
    color: AIGC_CHART_COLORS,
    animationDuration: 1500,
    animationEasing: 'cubicOut',
    series: [
      {
        name: 'Agent分布',
        type: 'pie',
        radius: ['45%', '70%'],
        center: ['50%', '42%'],
        avoidLabelOverlap: true,
        roseType: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: getVbenColor('--background'),
          borderWidth: 3,
          shadowBlur: 15,
          shadowColor: 'rgba(0, 0, 0, 0.12)',
        },
        label: {
          show: false,
        },
        emphasis: {
          scale: true,
          scaleSize: 15,
          label: {
            show: true,
            fontSize: 13,
            fontWeight: 'bold',
            color: getVbenColor('--foreground'),
          },
          itemStyle: {
            shadowBlur: 25,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.25)',
          },
        },
        labelLine: {
          show: false,
        },
        data: pieData,
        selectedMode: 'single',
        animationType: 'scale',
        animationEasing: 'elasticOut',
        animationDelay: (idx: number) => idx * 80,
      },
    ],
  };
}

// ==================== Agent 趋势图 ====================

/** 趋势图节点 */
interface TrendNode {
  count: number;
  date: string;
  x: number;
  y: number;
}

/** 趋势图数据 */
export interface TrendData {
  nodes: TrendNode[];
  points: string;
}

/**
 * 获取 Agent 每日生成文章数量趋势数据
 */
export function getAgentTrendData(
  agentCode: string,
  agentContentDailyTrend: AgentContentTrend[],
): TrendData {
  const trends = agentContentDailyTrend.filter(
    (t) => t.agent_code === agentCode,
  );

  if (trends.length === 0) {
    return { nodes: [], points: '' };
  }

  // 计算数值范围
  const counts = trends.map((t) => t.content_count);
  const maxCount = Math.max(...counts, 1);
  const minCount = Math.min(...counts, 0);

  // SVG 尺寸
  const svgWidth = 300;
  const svgHeight = 60;
  const paddingX = 15;
  const paddingY = 15;
  const graphWidth = svgWidth - paddingX * 2;
  const graphHeight = svgHeight - paddingY * 2;

  // 生成节点坐标
  const nodes: TrendNode[] = trends.map((t, index) => {
    const x = paddingX + (index / (trends.length - 1 || 1)) * graphWidth;
    const y =
      paddingY +
      graphHeight -
      ((t.content_count - minCount) / (maxCount - minCount || 1)) * graphHeight;
    return {
      x,
      y,
      count: t.content_count,
      date: dayjs(t.date).format('MM-DD'),
    };
  });

  // 生成折线点
  const points = nodes.map((n) => `${n.x},${n.y}`).join(' ');

  return { nodes, points };
}
