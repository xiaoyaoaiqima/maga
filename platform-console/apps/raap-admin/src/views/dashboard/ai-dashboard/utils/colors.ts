/**
 * AI Dashboard 颜色工具函数
 */

// ==================== CSS 变量颜色 ====================

/**
 * 获取 CSS 变量并解析为 ECharts 可用的颜色字符串
 * @param varName CSS 变量名，如 '--foreground'
 * @returns ECharts 可用的颜色字符串
 */
export function getVbenColor(varName: string): string {
  if (typeof window === 'undefined') return '';
  const style = getComputedStyle(document.documentElement);
  const value = style.getPropertyValue(varName).trim();
  if (!value) return '';
  return value.includes('(') ? value : `hsl(${value})`;
}
