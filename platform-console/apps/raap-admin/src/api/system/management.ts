import { requestClient } from '#/api/request';

export namespace ManagementApi {
  /** 成本回算请求 */
  export interface TraceCostRecalcRequest {
    start_time?: string;
    end_time?: string;
    batch_size?: number;
    last_id?: number;
    dry_run?: boolean;
    only_if_price_found?: boolean;
  }

  /** 回算结果摘要 */
  export interface TraceCostRecalcSummary {
    processed: number;
    updated: number;
    missing_price: number;
    next_last_id?: number;
    old_total_cost_sum: string;
    new_total_cost_sum: string;
    delta_total_cost_sum: string;
    missing_price_top: Record<string, number>;
  }

  /** 重建聚合请求 */
  export interface TraceDailyStatsRebuildRequest {
    start_date: string;
    end_date: string;
  }

  /** 重建聚合摘要 */
  export interface TraceDailyStatsRebuildSummary {
    start_date: string;
    end_date: string;
    days: number;
    total_rows_affected: number;
  }
}

/**
 * 管理：回算 trace 成本
 */
export async function recalcTraceCostApi(
  data: ManagementApi.TraceCostRecalcRequest,
) {
  return requestClient.post<ManagementApi.TraceCostRecalcSummary>(
    '/v1/traces/admin/recalc-cost',
    data,
  );
}

/**
 * 管理：重建日统计聚合
 */
export async function rebuildDailyStatsApi(
  data: ManagementApi.TraceDailyStatsRebuildRequest,
) {
  return requestClient.post<ManagementApi.TraceDailyStatsRebuildSummary>(
    '/v1/traces/admin/rebuild-daily-stats',
    data,
  );
}
