/**
 * AI Dashboard SVG 工具函数
 */

// ==================== 雷达图坐标计算 ====================

/**
 * 计算雷达图 SVG 顶点坐标（用于动态渲染线条和圆点）
 * @param index 顶点索引
 * @param total 顶点总数
 * @param centerX 中心 X 坐标（默认 150）
 * @param centerY 中心 Y 坐标（默认 150）
 * @param radius 半径（默认 120）
 * @returns 顶点坐标 { x, y }
 */
export function getRadarSvgVertexPosition(
  index: number,
  total: number,
  centerX: number = 150,
  centerY: number = 150,
  radius: number = 120,
): { x: number; y: number } {
  // 从顶部（-90度/270度）开始，顺时针方向
  const angle = -Math.PI / 2 + (index * 2 * Math.PI) / total;
  const x = centerX + radius * Math.cos(angle);
  const y = centerY + radius * Math.sin(angle);
  return { x: Math.round(x), y: Math.round(y) };
}
