/**
 * AI 成本模块图表配置
 *
 * Agent 成本分布饼图
 */

import type { EchartsOption } from '@vben/plugins/echarts';

import type { AgentCostItem, JobCostItem } from '../types';

import { USD_TO_CNY_RATE } from '../constants';
import { getVbenColor } from '../utils';

// ==================== 类型定义 ====================

/** 饼图数据项 */
interface PieDataItem {
  name: string;
  value: number;
}

// ==================== 图表颜色 ====================

const CHART_COLORS = [
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

// ==================== 数据处理 ====================

/**
 * 聚合 Agent 成本数据（按 Agent 合并不同币种）
 * 支持 JobCostItem[] 和 AgentCostItem[]
 */
export function aggregateAgentCostData(
  agentCostData: AgentCostItem[] | JobCostItem[],
): PieDataItem[] {
  const agentMap = new Map<string, PieDataItem>();

  agentCostData.forEach((item) => {
    const key = item.agent_code;
    const existing = agentMap.get(key);

    // 根据币种转换为人民币
    let cost = Number(item.total_cost) || 0;
    if (item.currency !== 'CNY') {
      cost = cost * USD_TO_CNY_RATE;
    }

    if (existing) {
      existing.value += cost;
    } else {
      agentMap.set(key, {
        name: item.agent_name || item.agent_code,
        value: cost,
      });
    }
  });

  return [...agentMap.values()];
}

// ==================== 图表配置 ====================

/**
 * 创建空数据图表配置
 */
export function createEmptyCostChartOption(): EchartsOption {
  return {
    title: {
      text: '投入成本分布',
      left: 'center',
      textStyle: { color: getVbenColor('--foreground') },
    },
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
 * 创建 Agent 成本分布饼图配置
 */
export function createAgentCostPieChartOption(
  pieData: PieDataItem[],
): EchartsOption {
  return {
    title: {
      text: '投入成本分布',
      left: 'center',
      top: 0,
      textStyle: { color: getVbenColor('--foreground'), fontSize: 14 },
    },
    tooltip: {
      trigger: 'item',
      formatter: (params: { name: string; percent: number; value: number }) => {
        return `${params.name}: ${params.value.toFixed(2)}元 (${params.percent}%)`;
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
    color: CHART_COLORS,
    animationDuration: 1500,
    animationEasing: 'cubicOut',
    series: [
      {
        name: '成本分布',
        type: 'pie',
        radius: ['35%', '60%'],
        center: ['50%', '45%'],
        avoidLabelOverlap: true,
        itemStyle: {
          borderRadius: 8,
          borderColor: getVbenColor('--background'),
          borderWidth: 3,
          shadowBlur: 10,
          shadowColor: 'rgba(0, 0, 0, 0.15)',
        },
        label: {
          show: false,
        },
        emphasis: {
          scale: true,
          scaleSize: 12,
          label: {
            show: true,
            fontSize: 13,
            fontWeight: 'bold',
            color: getVbenColor('--foreground'),
          },
          itemStyle: {
            shadowBlur: 20,
            shadowColor: 'rgba(0, 0, 0, 0.3)',
          },
        },
        labelLine: {
          show: false,
        },
        data: pieData,
        animationType: 'scale',
        animationEasing: 'elasticOut',
        animationDelay: (idx: number) => idx * 100,
      },
    ],
  };
}
