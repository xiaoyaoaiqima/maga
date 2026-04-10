import { requestClient } from '#/api/request';

export namespace SystemInfoApi {
  export interface K8sInfo {
    pod_name: string;
    node_name: string;
    namespace: string;
  }

  export interface DatabaseInfo {
    host: string;
    port: number;
    user: string;
    database: string;
  }

  export interface RedisInfo {
    host: string;
    port: number;
    db: number;
    insight_url?: string;
  }

  export interface ServiceHealth {
    status: string;
    version?: string;
    last_check?: string;
  }

  export interface SystemInfoResult {
    app_env: string;
    k8s: K8sInfo;
    database: DatabaseInfo;
    redis: RedisInfo;
    services: Record<string, ServiceHealth>;
  }
}

/**
 * 获取系统信息
 */
export async function getSystemInfoApi() {
  return requestClient.get<SystemInfoApi.SystemInfoResult>('/v1/system/info');
}
