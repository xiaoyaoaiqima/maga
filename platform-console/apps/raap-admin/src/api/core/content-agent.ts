import { requestClient } from '#/api/request';

export namespace ContentAgentApi {
  export interface StartGenerationRequest {
    product_topic: string;
    target_audience?: null | string;
    style?: null | string;
    executor_code?: string;
    brief_type?: string;
    priority?: number;
    created_by?: null | string;
  }

  export interface StartGenerationResponse {
    task_id: number;
    run_id: number;
    title: string;
    body: string;
  }

  export interface BatchStartRequest {
    asset_key?: string;
    product_topic: string;
    target_audience?: null | string;
    style?: null | string;
    count?: number;
    executor_code?: string;
    created_by?: null | string;
  }

  export interface BatchReportSummary {
    total_count: number;
    generated_count: number;
    failed_count: number;
    hard_pass_count: number;
    rewrite_item_count: number;
    remaining_rewrite_required_count: number;
    forbidden_hit_count: number;
    feedback_count: number;
    avg_body_chars?: null | number;
    max_pairwise_jaccard_2gram: number;
    similarity_warning_count: number;
  }

  export interface BatchReportItem {
    item_id: number;
    item_no: number;
    status: string;
    task_id?: null | number;
    run_id?: null | number;
    title?: null | string;
    body?: null | string;
    body_preview?: null | string;
    body_chars: number;
    hard_pass?: boolean | null;
    rewrite_required?: boolean | null;
    rewrite_reason?: null | string;
    rewrite_rounds?: null | number;
    suggestion_count: number;
    replacement_count: number;
    forbidden_hits: string[];
    final_path?: null | string;
    debug_dir?: null | string;
    review_status?: null | string;
    latest_version_no?: null | number;
    human_feedback_text?: null | string;
    feedback_count: number;
    reject_reasons: Array<{
      source: string;
      code?: null | string;
      message: string;
      risk_level?: null | string;
      evidence: string[];
    }>;
    similarity_warnings: Array<{
      item_no: number;
      score: number;
      reason: string;
    }>;
    runtime_mode?: null | string;
    generation_duration_ms?: null | number;
    total_duration_ms?: null | number;
    trace_run_id?: null | number;
    trace_stage_calls: Array<{
      stage_call_id: string;
      sequence_no: number;
      capability: string;
      status: string;
      duration_ms?: null | number;
      error_message?: null | string;
      stats?: null | Record<string, any>;
    }>;
    opening_type?: null | string;
    structure_type?: null | string;
    diversity?: null | Record<string, any>;
    quality?: null | Record<string, any>;
    error_message?: null | string;
  }

  export interface BatchReport {
    batch_id: number;
    batch_code?: null | string;
    asset_key: string;
    product_topic: string;
    target_audience?: null | string;
    style?: null | string;
    status: string;
    count: number;
    summary: BatchReportSummary;
    items: BatchReportItem[];
  }

  export interface BatchExecutionSummary {
    requested_limit: number;
    generated_count: number;
    failed_count: number;
    item_ids: number[];
  }

  export interface BatchStartResponse {
    batch_id: number;
    batch_code?: null | string;
    execution: BatchExecutionSummary;
    report: BatchReport;
  }

  export interface BatchListItem {
    batch_id: number;
    batch_code?: null | string;
    asset_key: string;
    product_topic: string;
    target_audience?: null | string;
    style?: null | string;
    status: string;
    count: number;
    summary: BatchReportSummary;
    create_time?: null | string;
    update_time?: null | string;
  }

  export interface BatchListResponse {
    total: number;
    items: BatchListItem[];
  }

  export type BatchItemFeedbackAction =
    | 'approve'
    | 'manual_edit'
    | 'request_revision';

  export interface BatchItemFeedbackRequest {
    action: BatchItemFeedbackAction;
    feedback_text?: null | string;
    title?: null | string;
    body?: null | string;
    created_by?: null | string;
  }

  export interface BatchItemFeedbackResponse {
    item_id: number;
    version_id: number;
    version_no: number;
    review_status: string;
    item: BatchReportItem;
  }
}

export async function startContentGenerationApi(
  data: ContentAgentApi.StartGenerationRequest,
) {
  return requestClient.post<ContentAgentApi.StartGenerationResponse>(
    '/v1/content-agent/generation/start',
    data,
    { timeout: 180_000 },
  );
}

export async function startContentBatchApi(
  data: ContentAgentApi.BatchStartRequest,
) {
  return requestClient.post<ContentAgentApi.BatchStartResponse>(
    '/v1/content-agent/batches/start',
    data,
    { timeout: 300_000 },
  );
}

export async function getContentBatchListApi(params?: {
  limit?: number;
  offset?: number;
}) {
  return requestClient.get<ContentAgentApi.BatchListResponse>(
    '/v1/content-agent/batches',
    { params },
  );
}

export async function getContentBatchReportApi(batchId: number) {
  return requestClient.get<ContentAgentApi.BatchReport>(
    `/v1/content-agent/batches/${batchId}/report`,
  );
}

export async function submitBatchItemFeedbackApi(
  itemId: number,
  data: ContentAgentApi.BatchItemFeedbackRequest,
) {
  return requestClient.post<ContentAgentApi.BatchItemFeedbackResponse>(
    `/v1/content-agent/batch-items/${itemId}/feedback`,
    data,
  );
}
