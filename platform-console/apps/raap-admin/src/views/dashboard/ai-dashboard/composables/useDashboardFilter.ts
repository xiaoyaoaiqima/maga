/**
 * AI Dashboard 筛选器状态与操作
 *
 * 管理日期范围、筛选条件、筛选选项等
 */

import type { ActivityApi, AgentApi, TenantApi } from '#/api/core/business';

import { ref } from 'vue';

import dayjs from 'dayjs';

import {
  getActivitySimpleListApi,
  getAgentSimpleListApi,
  getTenantSimpleListApi,
} from '#/api/core/business';

// ==================== 类型定义 ====================

/** 筛选条件状态 */
export interface FilterState {
  activityId?: number[];
  agentCode?: string[];
  tenantId?: number[];
}

/** 筛选选项 */
export interface FilterOption {
  label: string;
  value: number | string;
}

/** 时间预设 */
export type DateRangePreset = Record<string, [dayjs.Dayjs, dayjs.Dayjs]>;

// ==================== 默认值 ====================

/** 默认时间范围（最近 30 天） */
export const DEFAULT_DATE_RANGE: [dayjs.Dayjs, dayjs.Dayjs] = [
  dayjs().subtract(29, 'day'),
  dayjs(),
];

/** 时间预设选项 */
export const DATE_RANGES_PRESETS: DateRangePreset = {
  '最近 7 天': [dayjs().subtract(6, 'day'), dayjs()],
  '最近 15 天': [dayjs().subtract(14, 'day'), dayjs()],
  '最近 30 天': [dayjs().subtract(29, 'day'), dayjs()],
  '最近 90 天': [dayjs().subtract(89, 'day'), dayjs()],
  '最近 1 年': [dayjs().subtract(1, 'year'), dayjs()],
};

// ==================== Composable ====================

export function useDashboardFilter() {
  // 日期范围
  const dateRange = ref<[dayjs.Dayjs, dayjs.Dayjs]>(DEFAULT_DATE_RANGE);

  // 筛选状态（UI绑定用）
  const filters = ref<FilterState>({
    activityId: undefined,
    agentCode: undefined,
    tenantId: undefined,
  });

  // 已确认的筛选状态（用于实际数据请求，防止定时刷新时使用未确认的筛选条件）
  const confirmedFilters = ref<FilterState>({
    activityId: undefined,
    agentCode: undefined,
    tenantId: undefined,
  });

  // 筛选选项
  const tenantOptions = ref<FilterOption[]>([]);
  const activityOptions = ref<FilterOption[]>([]);
  const agentOptions = ref<FilterOption[]>([]);

  /** 加载筛选选项 */
  async function loadFilterOptions(): Promise<void> {
    try {
      const tenants = await getTenantSimpleListApi();
      tenantOptions.value = tenants.map((t: TenantApi.SimpleItem) => ({
        label: `${t.tenant_name} (${t.tenant_code})`,
        value: t.id,
      }));

      const firstTenantId = filters.value.tenantId?.[0];
      const [activities, agents] = await Promise.all([
        getActivitySimpleListApi(firstTenantId),
        getAgentSimpleListApi(firstTenantId),
      ]);

      activityOptions.value = activities.map((a: ActivityApi.SimpleItem) => ({
        label: `${a.activity_name} (${a.activity_code})`,
        value: a.id,
      }));

      agentOptions.value = agents.map((a: AgentApi.SimpleItem) => ({
        label: `${a.agent_name} (${a.agent_code})`,
        value: a.agent_code,
      }));
    } catch (error: unknown) {
      console.error('加载筛选选项失败:', error);
    }
  }

  /** 构建请求参数（使用已确认的筛选条件） */
  function buildParams() {
    const [start, end] = dateRange.value;
    return {
      agent_code: confirmedFilters.value.agentCode,
      end_date: end.add(1, 'day').format('YYYY-MM-DD'),
      start_date: start.format('YYYY-MM-DD'),
      tenant_id: confirmedFilters.value.tenantId,
      activity_id: confirmedFilters.value.activityId,
    };
  }

  /** 确认筛选 - 同步筛选条件 */
  function handleSearch(): FilterState {
    confirmedFilters.value = {
      activityId: filters.value.activityId,
      agentCode: filters.value.agentCode,
      tenantId: filters.value.tenantId,
    };
    return confirmedFilters.value;
  }

  /** 重置筛选 - 恢复默认值 */
  function handleReset(): void {
    dateRange.value = DEFAULT_DATE_RANGE;
    filters.value = {
      activityId: undefined,
      agentCode: undefined,
      tenantId: undefined,
    };
    confirmedFilters.value = {
      activityId: undefined,
      agentCode: undefined,
      tenantId: undefined,
    };
  }

  return {
    // 状态
    dateRange,
    filters,
    confirmedFilters,
    tenantOptions,
    activityOptions,
    agentOptions,

    // 常量
    dateRangesPresets: DATE_RANGES_PRESETS,

    // 方法
    loadFilterOptions,
    buildParams,
    handleSearch,
    handleReset,
  };
}
