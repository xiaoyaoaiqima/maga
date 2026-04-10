/**
 * 编码/名称唯一性检查工具
 *
 * 用于确保 ExpertConfig、Plugin、Agent 等编码与名称的唯一性
 * 提供自动生成唯一编码、实时校验、防止重复提交等功能
 */

import { message } from 'ant-design-vue';

import { requestClient } from '#/api/request';

/**
 * 生成唯一编码（带随机后缀）
 * @param prefix 编码前缀，如 "ge", "sp", "agent"
 * @param existingCodes 已存在的编码列表，用于探测重复
 * @returns 唯一的编码
 */
export function generateUniqueCode(
  prefix: string,
  existingCodes: string[],
): string {
  const now = new Date();
  const dateStr = `${String(now.getFullYear()).slice(2)}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`;

  // 生成随机4位字符串（字母+数字）
  function randomStr(length = 4): string {
    const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
    let result = '';
    for (let i = 0; i < length; i++) {
      result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
  }

  // 最多尝试10次生成唯一编码
  let attempts = 0;
  while (attempts < 10) {
    const code = `${prefix}_${dateStr}_${randomStr()}`;
    if (!existingCodes.includes(code)) {
      return code;
    }
    attempts++;
  }

  // 如果10次都失败，使用时间戳确保唯一
  return `${prefix}_${dateStr}_${Date.now().toString(36)}`;
}

/**
 * 检查编码是否已存在（后端API）
 * @param entityType 实体类型：'expert_config' | 'plugin' | 'agent'
 * @param code 要检查的编码
 * @returns true 表示编码已存在，false 表示可用
 */
export async function checkCodeExists(
  entityType: 'agent' | 'expert_config' | 'plugin',
  code: string,
): Promise<boolean> {
  if (!code || code.trim() === '') {
    return false;
  }

  try {
    // 根据不同实体类型调用不同的API
    let endpoint = '';
    let params: Record<string, any> = {};

    switch (entityType) {
      case 'agent': {
        endpoint = '/v1/agents';
        params = { code_filter: code };
        break;
      }
      case 'expert_config': {
        endpoint = '/v1/expert-configs';
        params = { code_filter: code };
        break;
      }
      case 'plugin': {
        endpoint = '/v1/plugins';
        params = { code_filter: code };
        break;
      }
      default: {
        return false;
      }
    }

    // 调用API检查
    const response = await requestClient.get<any>(endpoint, { params });

    // 如果返回的列表中有匹配的编码，说明已存在
    if (Array.isArray(response)) {
      return response.some(
        (item: any) =>
          item.expert_config_code === code ||
          item.plugin_code === code ||
          item.agent_code === code,
      );
    }
    if (response?.items && Array.isArray(response.items)) {
      return response.items.some(
        (item: any) =>
          item.expert_config_code === code ||
          item.plugin_code === code ||
          item.agent_code === code,
      );
    }

    return false;
  } catch (error) {
    console.error(`检查编码唯一性失败 (${entityType}):`, error);
    // 检查失败时，为安全起见，假设不存在（允许用户继续）
    return false;
  }
}

/**
 * 检查名称是否已存在（后端 API）
 * @param entityType 实体类型：'expert_config' | 'agent'
 * @param name 要检查的名称
 * @param excludeId 排除的 ID（编辑时传入当前记录：expert_config 传 number，agent 传 string 即 agent_code）
 * @returns true 表示名称已存在，false 表示可用
 */
export async function checkNameExists(
  entityType: 'agent' | 'expert_config',
  name: string,
  excludeId?: number | string,
): Promise<boolean> {
  const trimmed = (name || '').trim();
  if (!trimmed) return false;

  try {
    if (entityType === 'expert_config') {
      const params: Record<string, number | string> = {
        expert_config_name: trimmed,
      };
      if (excludeId !== undefined && typeof excludeId === 'number') {
        params.exclude_id = excludeId;
      }
      const res = await requestClient.get<{
        data?: { exists?: boolean };
        exists?: boolean;
      }>('/v1/expert-configs/exists', { params });
      return (res?.data?.exists ?? res?.exists) === true;
    }
    if (entityType === 'agent') {
      const params: Record<string, string> = { agent_name: trimmed };
      if (excludeId !== undefined && typeof excludeId === 'string') {
        params.exclude_code = excludeId;
      }
      const res = await requestClient.get<{
        data?: { exists?: boolean };
        exists?: boolean;
      }>('/v1/agents/exists', { params });
      return (res?.data?.exists ?? res?.exists) === true;
    }
    return false;
  } catch (error) {
    console.error(`检查名称唯一性失败 (${entityType}):`, error);
    return false;
  }
}

/**
 * 防抖包装器（用于实时校验）
 * @param fn 要防抖的函数
 * @param delay 延迟时间（毫秒）
 * @returns 防抖后的函数
 */
export function debounce<T extends (...args: any[]) => any>(
  fn: T,
  delay: number,
): (...args: Parameters<T>) => void {
  let timeoutId: null | ReturnType<typeof setTimeout> = null;

  return function (this: any, ...args: Parameters<T>) {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
    timeoutId = setTimeout(() => {
      fn.apply(this, args);
    }, delay);
  };
}

/**
 * 编码校验状态
 */
export type CodeValidationStatus =
  | 'checking' // 校验中
  | 'error' // 校验出错
  | 'idle' // 初始状态
  | 'invalid' // 已存在/不可用
  | 'valid'; // 可用

/**
 * 创建编码校验器（响应式）
 * 用于在Vue组件中进行实时编码校验
 */
export class CodeValidator {
  public message: string = '';
  public status: CodeValidationStatus = 'idle';

  /**
   * 校验编码（防抖500ms）
   */
  public validate = debounce(async (code: string) => {
    if (!code || code.trim() === '') {
      this.updateStatus('idle', '');
      return;
    }

    this.updateStatus('checking', '正在校验...');

    try {
      const exists = await checkCodeExists(this.entityType, code);
      if (exists) {
        this.updateStatus('invalid', '此编码已被使用，请修改');
      } else {
        this.updateStatus('valid', '编码可用');
      }
    } catch (error) {
      console.error('编码校验失败:', error);
      this.updateStatus('error', '校验失败，请重试');
    }
  }, 500);
  private entityType: 'agent' | 'expert_config' | 'plugin';

  private onStatusChange?: (
    status: CodeValidationStatus,
    message: string,
  ) => void;

  constructor(
    entityType: 'agent' | 'expert_config' | 'plugin',
    onStatusChange?: (status: CodeValidationStatus, message: string) => void,
  ) {
    this.entityType = entityType;
    this.onStatusChange = onStatusChange;
  }

  /**
   * 重置校验状态
   */
  public reset() {
    this.updateStatus('idle', '');
  }

  private updateStatus(status: CodeValidationStatus, msg: string) {
    this.status = status;
    this.message = msg;
    this.onStatusChange?.(status, msg);
  }
}

/**
 * 表单提交前的编码唯一性检查（最终防线）
 * @param entityType 实体类型
 * @param code 编码
 * @returns true 表示可以提交，false 表示不能提交
 */
export async function validateCodeBeforeSubmit(
  entityType: 'agent' | 'expert_config' | 'plugin',
  code: string,
): Promise<boolean> {
  if (!code || code.trim() === '') {
    message.error('请输入编码');
    return false;
  }

  const exists = await checkCodeExists(entityType, code);
  if (exists) {
    message.error(`编码 "${code}" 已存在，请使用其他编码`);
    return false;
  }

  return true;
}
