/**
 * AI Dashboard 格式化工具函数
 */

import dayjs from 'dayjs';

import { USD_TO_CNY_RATE } from '../constants';

// ==================== 数字格式化 ====================

/**
 * 格式化数字（千分位）
 * @param num 数字
 * @param decimals 小数位数（可选）
 * @returns 格式化后的字符串
 */
export function formatNumber(
  num: null | number | undefined,
  decimals?: number,
): string {
  const value = Number(num) || 0;
  if (decimals !== undefined) {
    return value.toLocaleString('zh-CN', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  }
  return value.toLocaleString('zh-CN');
}

// ==================== 成本格式化 ====================

/**
 * 格式化成本（统一转换为人民币）
 * @param cost 成本数值
 * @param currency 货币类型
 * @returns 格式化后的成本字符串
 */
export function formatCost(cost: number | string, currency: string): string {
  let costNum = Number(cost) || 0;
  // 非人民币按汇率转换为人民币
  if (currency !== 'CNY') {
    costNum = costNum * USD_TO_CNY_RATE;
  }
  return `${costNum.toFixed(2)}元`;
}

// ==================== 时间格式化 ====================

/**
 * 格式化耗时（智能显示秒/分/时）
 * @param startTime 开始时间
 * @param endTime 结束时间
 * @returns 格式化后的耗时字符串
 */
export function formatDuration(startTime: string, endTime: string): string {
  if (!startTime || !endTime) return '-';
  const start = dayjs(startTime);
  const end = dayjs(endTime);
  const diffSeconds = end.diff(start, 'second');

  if (diffSeconds < 0) return '-';
  if (diffSeconds < 60) return `${diffSeconds}秒`;
  if (diffSeconds < 3600) {
    const minutes = Math.floor(diffSeconds / 60);
    const seconds = diffSeconds % 60;
    return seconds > 0 ? `${minutes}分${seconds}秒` : `${minutes}分`;
  }
  const hours = Math.floor(diffSeconds / 3600);
  const minutes = Math.floor((diffSeconds % 3600) / 60);
  return minutes > 0 ? `${hours}时${minutes}分` : `${hours}时`;
}
