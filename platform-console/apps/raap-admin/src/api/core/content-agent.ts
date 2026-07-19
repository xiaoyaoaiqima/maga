import { requestClient } from '#/api/request';

export namespace ContentAgentApi {
  export interface BatchStartRequest {
    asset_key?: string;
    keyword_asset_key?: null | string;
    prompt_mode?:
      | null
      | 'minimal_rule_prompt'
      | 'rule_as_prompt'
      | 'rule_corpus_as_prompt';
    rule_id?: null | string;
    source_row_no?: null | number;
    draft_corpus?: null | string;
    draft_selling_painpoint_group?: null | string;
    draft_rule_id?: null | string;
    draft_source_row_no?: null | number;
    product_topic?: null | string;
    target_audience?: null | string;
    persona_target?: null | string;
    style?: null | string;
    count?: number;
    articles_per_prompt?: number;
    postprocess_mode?: null | 'audit_only' | 'generate_only';
    executor_code?: string;
    model_config?: null | {
      ae_model?: null | string;
      ge_model?: null | string;
    };
    created_by?: null | string;
  }

  export interface CommentBatchStartRequest {
    asset_key?: string;
    business_rule?: null | string;
    count?: number;
    executor_code?: string;
    draft_corpus?: null | string;
    draft_comment_prompt_bundle?: null | {
      generation_instruction: string;
      content_direction: string;
      activity_material: string[];
      writing_requirements: string[];
      notes: string[];
    };
    draft_rule_id?: null | string;
    draft_source_row_no?: null | number;
    comment_prompt_slots?: null | Record<string, string[]>;
    comment_batch_variation_review?: null | Record<string, any>;
    comment_delivery_selection?: null | Record<string, any>;
    quality_guard_profile_key?: null | string;
    rule_id?: null | string;
    source_row_no?: null | number;
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
    batch_variation_warning_count: number;
    delivery_candidate_count: number;
    delivery_selected_count: number;
    delivery_shortfall_count: number;
    suggested_bulk_refill_count: number;
    audit_skipped_count: number;
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
    activity_quality_guard?: null | Record<string, any>;
    rewrite_records?: Array<Record<string, any>>;
    execution_stages?: Array<Record<string, any>>;
  }

  export interface TaskSnapshotResponse {
    task_id: number;
    run_id?: null | number;
    task_type: string;
    input: GenerationSnapshot;
    asset_refs: Record<string, any>;
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
    batch_variation_pass?: boolean | null;
    delivery_selected?: boolean | null;
    delivery_rank?: number | null;
    delivery_non_selection_reason?: null | string;
    audit_skipped: boolean;
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
    version_compare?: null | {
      after: {
        body?: null | string;
        create_time?: null | string;
        created_by?: null | string;
        feedback_text?: null | string;
        review_status?: null | string;
        source_action: string;
        title?: null | string;
        version_id?: null | number;
        version_no?: null | number;
      };
      before: {
        body?: null | string;
        create_time?: null | string;
        created_by?: null | string;
        feedback_text?: null | string;
        review_status?: null | string;
        source_action: string;
        title?: null | string;
        version_id?: null | number;
        version_no?: null | number;
      };
      body_after_chars: number;
      body_before_chars: number;
      body_changed: boolean;
      compare_type: string;
      title_changed: boolean;
    };
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

  export interface AssetGenerationOptionsResponse {
    asset_key?: null | string;
    asset_keys: string[];
    product_topics: string[];
    target_audiences: string[];
    persona_profiles: string[];
    styles: string[];
  }

  export type BatchItemFeedbackAction =
    | 'accept_rewrite'
    | 'approve'
    | 'manual_edit'
    | 'reject_rewrite'
    | 'request_revision';

  export interface BatchItemFeedbackRequest {
    action: BatchItemFeedbackAction;
    feedback_text?: null | string;
    feedback_categories?: string[];
    quoted_text?: null | string;
    title?: null | string;
    body?: null | string;
    created_by?: null | string;
    business_forbidden_terms?: string[];
    business_forbidden_term_entries?: Array<{
      reason?: null | string;
      replacement?: null | string;
      term: string;
    }>;
    auto_rewrite?: boolean;
  }

  export interface BatchItemFeedbackResponse {
    item_id: number;
    version_id: number;
    version_no: number;
    review_status: string;
    item: BatchReportItem;
  }
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
  asset_key?: string;
  limit?: number;
  offset?: number;
  rule_id?: null | string;
  source_row_no?: null | number;
}) {
  return requestClient.get<ContentAgentApi.BatchListResponse>(
    '/v1/content-agent/batches',
    { params },
  );
}

export async function getContentBatchReportApi(batchId: number) {
  return requestClient.get<ContentAgentApi.BatchReport>(
    `/v1/content-agent/batches/${batchId}/report`,
    { params: { full: true } },
  );
}

export async function getContentAgentTaskSnapshotApi(
  taskId: number,
  runId?: null | number,
) {
  return requestClient.get<ContentAgentApi.TaskSnapshotResponse>(
    `/v1/content-agent/tasks/${taskId}/snapshot`,
    { params: runId ? { run_id: runId } : undefined },
  );
}

export async function downloadContentBatchReportExcelApi(batchId: number) {
  return requestClient.download<Blob>(
    `/v1/content-agent/batches/${batchId}/export.xlsx`,
  );
}

export async function downloadContentBatchArticlePoolCsvApi(batchId: number) {
  return requestClient.download<Blob>(
    `/v1/content-agent/batches/${batchId}/export-article-pool.csv`,
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
