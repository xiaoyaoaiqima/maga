import { requestClient } from '#/api/request';

export namespace ContentAgentApi {
  export interface StartGenerationRequest {
    product_topic: string;
    target_audience?: null | string;
    persona_target?: null | string;
    style?: null | string;
    executor_code?: string;
    model_config?: null | {
      ae_model?: null | string;
      ge_model?: null | string;
    };
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
    product_topic?: null | string;
    target_audience?: null | string;
    persona_target?: null | string;
    style?: null | string;
    count?: number;
    executor_code?: string;
    model_config?: null | {
      ae_model?: null | string;
      ge_model?: null | string;
    };
    created_by?: null | string;
  }

  export interface CommentBatchStartRequest {
    asset_key?: string;
    executor_code?: string;
    created_by?: null | string;
  }

  export interface PreflightCheck {
    code: string;
    label: string;
    status: 'fail' | 'pass' | 'warning';
    message: string;
    detail: Record<string, any>;
  }

  export interface PreflightRequest {
    asset_key: string;
    asset_type?: null | string;
    executor_code?: string;
  }

  export interface PreflightResponse {
    passed: boolean;
    status: 'blocked' | 'ready' | 'warning';
    asset_key: string;
    asset_type?: null | string;
    content_type?: 'article' | 'comment' | null;
    executor_code: string;
    checks: PreflightCheck[];
    blocking_codes: string[];
    warning_codes: string[];
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

  export interface GenerationSnapshot {
    schema_version?: string;
    rule_type?: null | string;
    content_type?: null | string;
    capability?: null | string;
    output_fields?: string[];
    business_rule?: Record<string, any>;
    selected_keywords?: Array<Record<string, any>>;
    keyword_asset?: Record<string, any>;
    expert?: Record<string, any>;
    model_config?: Record<string, any>;
    model_route?: Record<string, any>;
    rendered_prompt?: null | string;
    forbidden_terms_review?: null | Record<string, any>;
    rewrite_records?: Array<Record<string, any>>;
    execution_stages?: Array<Record<string, any>>;
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
      code?: null | string;
      evidence: string[];
      message: string;
      risk_level?: null | string;
      source: string;
    }>;
    similarity_warnings: Array<{
      batch_code?: null | string;
      batch_id?: null | number;
      item_no: number;
      reason: string;
      scope?: string;
      score: number;
    }>;
    runtime_mode?: null | string;
    generation_duration_ms?: null | number;
    total_duration_ms?: null | number;
    trace_run_id?: null | number;
    trace_stage_calls: Array<{
      capability: string;
      duration_ms?: null | number;
      error_message?: null | string;
      sequence_no: number;
      stage_call_id: string;
      stats?: null | Record<string, any>;
      status: string;
    }>;
    opening_type?: null | string;
    structure_type?: null | string;
    content_angle?: null | string;
    persona_lens?: null | string;
    scene_type?: null | string;
    evidence_type?: null | string;
    asset_combo_key?: null | string;
    asset_reuse_reason?: null | string;
    generation_snapshot?: GenerationSnapshot | null;
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
    persona_target?: null | string;
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
    persona_target?: null | string;
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

  export interface TrainingFeedbackSample {
    feedback_id: number;
    batch_id?: null | number;
    batch_code?: null | string;
    item_id: number;
    item_no: number;
    version_id?: null | number;
    action: string;
    review_status: string;
    comment?: null | string;
    submitter?: null | string;
    title?: null | string;
    body_preview?: null | string;
    product_topic?: null | string;
    target_audience?: null | string;
    persona_target?: null | string;
    style?: null | string;
    asset_key?: null | string;
    metadata?: null | Record<string, any>;
    create_time?: null | string;
  }

  export interface TrainingFeedbackSampleListResponse {
    total: number;
    items: TrainingFeedbackSample[];
  }

  export interface AssetGenerationOptionsResponse {
    asset_key?: null | string;
    asset_keys: string[];
    product_topics: string[];
    target_audiences: string[];
    persona_profiles: string[];
    styles: string[];
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
    business_forbidden_terms?: string[];
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

export async function startCommentBatchApi(
  data: ContentAgentApi.CommentBatchStartRequest,
) {
  return requestClient.post<ContentAgentApi.BatchStartResponse>(
    '/v1/content-agent/comment-batches/start',
    data,
    { timeout: 300_000 },
  );
}

export async function preflightContentGenerationApi(
  data: ContentAgentApi.PreflightRequest,
) {
  return requestClient.post<ContentAgentApi.PreflightResponse>(
    '/v1/content-agent/preflight-check',
    data,
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

export async function getTrainingFeedbackSamplesApi(params?: {
  limit?: number;
  offset?: number;
  review_status?: string;
}) {
  return requestClient.get<ContentAgentApi.TrainingFeedbackSampleListResponse>(
    '/v1/content-agent/training/feedback-samples',
    { params },
  );
}

export async function getAssetGenerationOptionsApi(params?: {
  asset_key?: string;
}) {
  return requestClient.get<ContentAgentApi.AssetGenerationOptionsResponse>(
    '/v1/assets/generation-options',
    { params },
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
