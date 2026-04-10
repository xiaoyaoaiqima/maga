/**
 * 统一日志工具
 *
 * 功能：
 * - 环境开关：生产环境自动关闭 debug 日志
 * - 日志级别：debug, info, warn, error
 * - 分类标记：API, Component, Composable 等
 * - 统一格式：[级别][分类] 消息
 *
 * @example
 * ```ts
 * import { logger } from '#/utils/logger';
 *
 * // 普通日志
 * logger.debug('变量值:', variable);
 * logger.warn('警告信息');
 * logger.error('错误:', error);
 *
 * // 带分类的日志
 * logger.api('GET /api/users', response);
 * logger.component('UserProfile', '组件已挂载');
 * logger.composable('useAuth', '用户已登录');
 * ```
 */

/** 日志级别 */
export enum LogLevel {
  DEBUG = 0,
  ERROR = 3,
  INFO = 1,
  WARN = 2,
}

/** 日志配置 */
interface LoggerConfig {
  level: LogLevel;
  enableInProduction: boolean;
  prefix: string;
}

/** 当前配置 */
let config: LoggerConfig = {
  level: LogLevel.DEBUG,
  enableInProduction: false,
  prefix: '[MAGA]',
};

/**
 * 设置日志配置
 */
export function setLoggerConfig(newConfig: Partial<LoggerConfig>) {
  config = { ...config, ...newConfig };
}

/**
 * 判断是否应该输出日志
 */
function shouldLog(level: LogLevel): boolean {
  // 生产环境检查
  if (import.meta.env.PROD && !config.enableInProduction) {
    return false;
  }
  // 级别检查
  return level >= config.level;
}

/**
 * 格式化日志前缀
 */
function formatPrefix(level: string, category?: string): string {
  const parts = [config.prefix, level];
  if (category) {
    parts.push(category);
  }
  return parts.join(' ');
}

/**
 * 核心日志函数
 */
function log(
  level: LogLevel,
  levelName: string,
  category: string | undefined,
  ...args: any[]
) {
  if (!shouldLog(level)) {
    return;
  }

  const prefix = formatPrefix(levelName, category);
  const timestamp = new Date().toLocaleTimeString('zh-CN', { hour12: false });

  // 根据级别选择 console 方法
  let consoleMethod: 'error' | 'log' | 'warn';
  if (level === LogLevel.ERROR) {
    consoleMethod = 'error';
  } else if (level === LogLevel.WARN) {
    consoleMethod = 'warn';
  } else {
    consoleMethod = 'log';
  }

  // 输出日志
  // eslint-disable-next-line no-console
  console[consoleMethod](`[${timestamp}]`, prefix, ...args);
}

/**
 * Logger 实例
 */
export const logger = {
  /**
   * DEBUG 级别日志（仅开发环境）
   */
  debug: (...args: any[]) => log(LogLevel.DEBUG, 'DEBUG', undefined, ...args),

  /**
   * INFO 级别日志
   */
  info: (...args: any[]) => log(LogLevel.INFO, 'INFO', undefined, ...args),

  /**
   * WARN 级别日志
   */
  warn: (...args: any[]) => log(LogLevel.WARN, 'WARN', undefined, ...args),

  /**
   * ERROR 级别日志
   */
  error: (...args: any[]) => log(LogLevel.ERROR, 'ERROR', undefined, ...args),

  /**
   * API 调用日志
   */
  api: (endpoint: string, ...args: any[]) =>
    log(LogLevel.INFO, 'API', `endpoint=${endpoint}`, ...args),

  /**
   * 组件日志
   */
  component: (componentName: string, ...args: any[]) =>
    log(LogLevel.DEBUG, 'Component', componentName, ...args),

  /**
   * Composable 日志
   */
  composable: (composableName: string, ...args: any[]) =>
    log(LogLevel.DEBUG, 'Composable', composableName, ...args),

  /**
   * 性能日志
   */
  performance: (label: string, duration: number) =>
    log(LogLevel.INFO, 'Performance', `${label}: ${duration}ms`),

  /**
   * 创建分类日志器
   */
  createCategory: (category: string) => ({
    debug: (...args: any[]) => log(LogLevel.DEBUG, 'DEBUG', category, ...args),
    info: (...args: any[]) => log(LogLevel.INFO, 'INFO', category, ...args),
    warn: (...args: any[]) => log(LogLevel.WARN, 'WARN', category, ...args),
    error: (...args: any[]) => log(LogLevel.ERROR, 'ERROR', category, ...args),
  }),
};

/**
 * 快捷导出：分类日志器
 */
export const apiLogger = logger.createCategory('API');
export const componentLogger = logger.createCategory('Component');
export const composableLogger = logger.createCategory('Composable');
export const storeLogger = logger.createCategory('Store');
export const routerLogger = logger.createCategory('Router');

export default logger;
