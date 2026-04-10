/**
 * 深拷贝工具函数
 *
 * 解决 Vue 3 响应式对象的深拷贝问题（BUG-002）
 * Vue 响应式对象不能直接使用 structuredClone，需要先 toRaw
 *
 * @example
 * ```ts
 * import { safeClone, cloneReactive } from '#/utils/clone';
 *
 * // 深拷贝普通对象
 * const copied = safeClone(originalData);
 *
 * // 深拷贝 Vue 响应式对象（推荐，自动 toRaw）
 * const copied = cloneReactive(reactiveData);
 * ```
 */

import { toRaw } from 'vue';

/**
 * 深拷贝函数 - 安全且高性能
 * 优先使用 structuredClone，降级到浅拷贝
 *
 * @param value - 要拷贝的值
 * @returns 深拷贝后的值
 */
export function safeClone<T>(value: T): T {
  // 如果是 null 或 undefined，直接返回
  if (value === null || value === undefined) {
    return value;
  }

  // 如果是原始类型（string, number, boolean, symbol, bigint），直接返回
  if (typeof value !== 'object') {
    return value;
  }

  // 优先使用 structuredClone（性能更好，支持更多类型）
  if (typeof globalThis.structuredClone === 'function') {
    try {
      return globalThis.structuredClone(value);
    } catch (error) {
      // structuredClone 可能失败（如包含函数、Symbol 等）
      // 降级到浅拷贝
      console.warn(
        'structuredClone failed, falling back to shallow copy:',
        error,
      );
    }
  }

  // 降级方案：浅拷贝（最后手段）
  // 注意：浅拷贝只处理第一层，嵌套对象仍然是引用
  return Array.isArray(value) ? ([...value] as T) : ({ ...value } as T);
}

/**
 * 深拷贝 Vue 响应式对象
 * 自动处理 toRaw 操作
 *
 * @param value - Vue 响应式对象
 * @returns 深拷贝后的普通对象
 */
export function cloneReactive<T>(value: T): T {
  // 检查是否是 Ref 对象
  if (
    value &&
    typeof value === 'object' &&
    '__v_isRef' in value &&
    (value as { __v_isRef: boolean }).__v_isRef === true
  ) {
    // 是 Ref，获取 .value 后 toRaw 再深拷贝
    const rawValue = toRaw((value as unknown as { value: T }).value);
    return safeClone(rawValue);
  }

  // 普通对象先用 toRaw 去除响应式，再深拷贝
  const rawValue = toRaw(value);
  return safeClone(rawValue);
}
