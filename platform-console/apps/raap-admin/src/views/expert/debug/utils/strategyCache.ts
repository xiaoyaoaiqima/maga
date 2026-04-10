/**
 * 策略数据缓存工具
 *
 * 使用 localStorage 缓存策略列表和组合数据，避免重复请求
 *
 * 缓存策略：
 * - 策略列表：缓存 30 分钟
 * - 组合数据：按 strategy_id 缓存，30 分钟过期
 */

import type { ContentStrategyApi } from '#/api/core/content-strategy';

const CACHE_KEY_STRATEGIES_PREFIX = 'raap:strategy:list:';
const CACHE_KEY_COMBINATIONS_PREFIX = 'raap:strategy:combinations:';
const CACHE_TTL_MS = 30 * 60 * 1000; // 30 分钟

/**
 * 生成策略列表的缓存 key（基于插件 code 和变量名）
 */
function getStrategiesCacheKey(
  pluginCode?: string,
  variableNames?: string[],
): string {
  if (!pluginCode && (!variableNames || variableNames.length === 0)) {
    return `${CACHE_KEY_STRATEGIES_PREFIX}all`;
  }

  // 如果有插件 code，使用插件 code 作为 key 的一部分
  if (pluginCode) {
    const varKey =
      variableNames && variableNames.length > 0
        ? `:${variableNames.toSorted().join(',')}`
        : '';
    return CACHE_KEY_STRATEGIES_PREFIX + pluginCode + varKey;
  }

  // 否则使用变量名组合
  const varKey =
    variableNames && variableNames.length > 0
      ? variableNames.toSorted().join(',')
      : 'all';
  return CACHE_KEY_STRATEGIES_PREFIX + varKey;
}

interface CacheItem<T> {
  data: T;
  timestamp: number;
}

/**
 * 通用缓存读取
 */
function getCache<T>(key: string): null | T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;

    const item: CacheItem<T> = JSON.parse(raw);
    const now = Date.now();

    // 检查是否过期
    if (now - item.timestamp > CACHE_TTL_MS) {
      localStorage.removeItem(key);
      return null;
    }

    return item.data;
  } catch {
    return null;
  }
}

/**
 * 通用缓存写入
 */
function setCache<T>(key: string, data: T): void {
  try {
    const item: CacheItem<T> = {
      data,
      timestamp: Date.now(),
    };
    localStorage.setItem(key, JSON.stringify(item));
  } catch (error) {
    // localStorage 可能满了，静默失败
    console.warn('策略缓存写入失败:', error);
  }
}

/**
 * 获取缓存的策略列表
 * @param pluginCode 插件 code（可选）
 * @param variableNames 变量名列表（可选）
 */
export function getCachedStrategies(
  pluginCode?: string,
  variableNames?: string[],
): ContentStrategyApi.ContentStrategy[] | null {
  const key = getStrategiesCacheKey(pluginCode, variableNames);
  return getCache<ContentStrategyApi.ContentStrategy[]>(key);
}

/**
 * 缓存策略列表
 * @param strategies 策略列表
 * @param pluginCode 插件 code（可选）
 * @param variableNames 变量名列表（可选）
 */
export function setCachedStrategies(
  strategies: ContentStrategyApi.ContentStrategy[],
  pluginCode?: string,
  variableNames?: string[],
): void {
  const key = getStrategiesCacheKey(pluginCode, variableNames);
  setCache(key, strategies);
}

/**
 * 获取缓存的组合数据
 */
export function getCachedCombinations(
  strategyId: string,
): ContentStrategyApi.CombinationItem[] | null {
  return getCache<ContentStrategyApi.CombinationItem[]>(
    CACHE_KEY_COMBINATIONS_PREFIX + strategyId,
  );
}

/**
 * 缓存组合数据
 */
export function setCachedCombinations(
  strategyId: string,
  combinations: ContentStrategyApi.CombinationItem[],
): void {
  setCache(CACHE_KEY_COMBINATIONS_PREFIX + strategyId, combinations);
}

/**
 * 清除所有策略缓存
 */
export function clearStrategyCache(): void {
  // 清除所有策略列表缓存
  const keysToRemove: string[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key?.startsWith(CACHE_KEY_STRATEGIES_PREFIX)) {
      keysToRemove.push(key);
    }
  }
  keysToRemove.forEach((key) => localStorage.removeItem(key));

  // 清除所有组合缓存
  const comboKeysToRemove: string[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key?.startsWith(CACHE_KEY_COMBINATIONS_PREFIX)) {
      comboKeysToRemove.push(key);
    }
  }
  comboKeysToRemove.forEach((key) => localStorage.removeItem(key));
}

/**
 * 获取缓存状态信息（用于调试/显示）
 */
export function getCacheInfo(): {
  combinationsCount: number;
  hasStrategies: boolean;
  strategiesAge: null | number;
  strategiesCount: number;
} {
  let strategiesAge: null | number = null;
  let hasStrategies = false;
  let strategiesCount = 0;

  // 统计所有策略缓存
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key?.startsWith(CACHE_KEY_STRATEGIES_PREFIX)) {
      strategiesCount++;
      if (!hasStrategies) {
        try {
          const raw = localStorage.getItem(key);
          if (raw) {
            const item: CacheItem<unknown> = JSON.parse(raw);
            hasStrategies = true;
            strategiesAge = Math.floor((Date.now() - item.timestamp) / 1000);
          }
        } catch {
          // ignore
        }
      }
    }
  }

  let combinationsCount = 0;
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key?.startsWith(CACHE_KEY_COMBINATIONS_PREFIX)) {
      combinationsCount++;
    }
  }

  return { hasStrategies, strategiesAge, combinationsCount, strategiesCount };
}
