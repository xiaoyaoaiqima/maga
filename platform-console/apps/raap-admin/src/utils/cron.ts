/**
 * Cron 表达式工具函数
 */

export const commonCronShortcuts = [
  { label: '每分钟', value: '0 * * * * *', desc: '任务每隔 1 分钟运行一次' },
  {
    label: '每 5 分钟',
    value: '0 */5 * * * *',
    desc: '任务每隔 5 分钟运行一次',
  },
  { label: '每小时', value: '0 0 * * * *', desc: '每小时整点运行一次' },
  { label: '每天零点', value: '0 0 0 * * *', desc: '每天凌晨 00:00 运行一次' },
  {
    label: '每周一零点',
    value: '0 0 0 * * 1',
    desc: '每周一凌晨 00:00 运行一次',
  },
];

/**
 * 将 Cron 表达式转换为业务语言描述
 * @param cron 6位 Cron 表达式 (秒 分 时 日 月 周)
 */
export function getCronDescription(cron: string): string {
  if (!cron || cron === '-') return '未设置';
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 6) return '表达式格式不正确（需要6位）';

  const [s, m, h, D, _M, W] = parts;

  // 1. 完全匹配常用模式
  if (cron === '0 * * * * *') return '每分钟运行一次';
  if (cron === '0 */5 * * * *') return '每隔 5 分钟运行一次';
  if (cron === '0 0 * * * *') return '每小时整点运行一次';
  if (cron === '0 0 0 * * *') return '每天凌晨 00:00 运行一次';
  if (cron === '0 0 0 * * 1') return '每周一凌晨 00:00 运行一次';

  // 2. 解析时间部分 (h, m, s)
  let timeDesc = '';
  const pad = (n: string) => n.padStart(2, '0');

  if (h === '*' && m === '*' && s === '*') {
    timeDesc = '每秒';
  } else if (h === '*' && m === '*') {
    timeDesc = `每分钟的第 ${s} 秒`;
  } else if (h === '*') {
    timeDesc =
      s === '0' || s === '00'
        ? `每小时的第 ${m} 分钟`
        : `每小时的 ${m} 分 ${s} 秒`;
  } else {
    // 固定小时
    const hourStr = h.includes(',') ? `[${h}]点` : `${pad(h)}:`;
    const minStr = m.includes(',') ? `[${m}]分` : `${pad(m)}:`;
    const secStr = s.includes(',') ? `[${s}]秒` : pad(s);

    timeDesc =
      !h.includes('*') && !m.includes('*') && !s.includes('*')
        ? `${pad(h)}:${pad(m)}:${pad(s)}`
        : `${hourStr}${minStr}${secStr}`;
  }

  // 3. 解析日期部分 (W, D)
  let dateDesc = '';
  if (W !== '*') {
    const weeks: Record<string, string> = {
      '0': '周日',
      '1': '周一',
      '2': '周二',
      '3': '周三',
      '4': '周四',
      '5': '周五',
      '6': '周六',
      '7': '周日',
    };
    dateDesc = `每周的 ${weeks[W] || W}`;
  } else if (D !== '*') {
    dateDesc = `每月的 ${D} 号`;
  } else if (h === '*') {
    dateDesc = ''; // 如果是每小时/每分钟，不显示“每天”
  } else {
    dateDesc = '每天';
  }

  // 4. 处理步进 (/)
  if (cron.includes('/')) {
    const match = cron.match(/(\d+)\/(\d+)/) || cron.match(/\*\/(\d+)/);
    if (match) {
      const val = match[match.length - 1];
      if (cron.startsWith(`*/${val} * * * * *`))
        return `每隔 ${val} 秒运行一次`;
      if (cron.startsWith(`0 */${val} * * * *`))
        return `每隔 ${val} 分钟运行一次`;
      if (cron.startsWith(`0 0 */${val} * * *`))
        return `每隔 ${val} 小时运行一次`;
    }
  }

  return `任务将在 ${dateDesc}${dateDesc ? ' ' : ''}${timeDesc} 执行`;
}
