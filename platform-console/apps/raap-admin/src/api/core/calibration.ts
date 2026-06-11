// @ts-nocheck
import { requestClient } from '#/api/request';

export interface CalibrationRecordCreate {
  calibration_task_id: number;
  content_row_id: number;
  content_id: string;
  job_id?: string;
  sub_job_id?: string;
  expert_config_code: string;
  expert_func: string;
  expert_type: 'BAN' | 'CRITIC';
  human_score_value?: number;
  human_passed?: boolean;
  remark?: string;
}

export interface CalibrationRecordResponse {
  id: number;
  calibration_task_id: number;
  content_row_id: number;
  content_id: string;
  job_id?: string;
  sub_job_id?: string;
  expert_config_code: string;
  expert_func: string;
  expert_type: 'BAN' | 'CRITIC';
  human_score_value?: number;
  human_passed?: boolean;
  remark?: string;
  reviewer_id: string;
  reviewer_name?: string;
  create_time?: string;
  ai_score?: number;
  ai_passed?: boolean;
}

export function createCalibrationRecordsApi(
  records: CalibrationRecordCreate[],
) {
  return requestClient.post<CalibrationRecordResponse[]>(
    '/v1/calibration-records',
    {
      records,
    },
  );
}

export interface CalibrationTaskCreate {
  task_code?: string;
  task_name?: string;
  assignee_id?: string;
  due_time?: string;
  remark?: string;
}

export interface CalibrationTaskResponse {
  id: number;
  task_code?: string;
  task_name: string;
  status: 'CANCELLED' | 'DONE' | 'IN_PROGRESS' | 'PENDING';
  assignee_id?: string;
  assignee_name?: string;
  start_time?: string;
  finish_time?: string;
  due_time?: string;
  remark?: string;
  created_by?: string;
  created_name?: string;
  create_time?: string;
  update_time?: string;
}

export function createCalibrationTaskApi(payload: CalibrationTaskCreate) {
  return requestClient.post<CalibrationTaskResponse>(
    '/v1/calibration-tasks',
    payload,
  );
}

export function updateCalibrationTaskApi(
  id: number,
  payload: Partial<Omit<CalibrationTaskResponse, 'id'>>,
) {
  return requestClient.patch<CalibrationTaskResponse>(
    `/v1/calibration-tasks/${id}`,
    payload,
  );
}

export function getCalibrationTasksApi(params: {
  assignee_id?: string;
  expert_config_code?: string;
  limit?: number;
  skip?: number;
  status?: CalibrationTaskResponse['status'];
}) {
  return requestClient.get<CalibrationTaskResponse[]>('/v1/calibration-tasks', {
    params,
  });
}
export function getCalibrationRecordsApi(params: {
  calibration_task_id?: number;
  content_ids?: string[];
  expert_config_codes?: string[];
  limit?: number;
  reviewer_id?: string;
  skip?: number;
}) {
  // 处理数组参数序列化
  const processedParams: Record<string, any> = { ...params };

  // 将 expert_config_codes 数组转换为逗号分隔的字符串
  if (params.expert_config_codes) {
    processedParams.expert_config_codes = params.expert_config_codes.join(',');
  }

  // 将 content_ids 数组转换为逗号分隔的字符串
  if (params.content_ids) {
    processedParams.content_ids = params.content_ids.join(',');
  }

  return requestClient.get<CalibrationRecordResponse[]>(
    '/v1/calibration-records',
    {
      params: processedParams,
    },
  );
}
