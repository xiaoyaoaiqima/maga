import { requestClient } from '#/api/request';

export namespace MetricDefinitionApi {
  export interface MetricDefinition {
    id: number;
    metric_key: string;
    metric_name: string;
    description: string;
    category: string;
    unit: null | string;
    display_format: null | string;
    display_order: number;
    create_time: string;
    update_time: string;
  }

  export interface UpdateParams {
    metric_name?: string;
    description?: string;
    category?: string;
    unit?: string;
    display_format?: string;
    display_order?: number;
  }
}

/** 获取所有指标定义 */
export async function getMetricDefinitionsApi() {
  return requestClient.get<MetricDefinitionApi.MetricDefinition[]>(
    '/v1/metric-definitions',
  );
}

/** 更新指标定义 */
export async function updateMetricDefinitionApi(
  metricKey: string,
  data: MetricDefinitionApi.UpdateParams,
) {
  return requestClient.put<MetricDefinitionApi.MetricDefinition>(
    `/v1/metric-definitions/${metricKey}`,
    data,
  );
}

/** 同步指标定义 */
export async function syncMetricDefinitionsApi() {
  return requestClient.post('/v1/metric-definitions/sync');
}
