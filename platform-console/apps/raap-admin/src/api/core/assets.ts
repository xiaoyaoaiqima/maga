// @ts-nocheck
import { requestClient } from '#/api/request';

export namespace AssetsApi {
  export interface AssetSummary {
    id: number;
    asset_type: string;
    asset_key: string;
    display_name?: null | string;
    version_no: number;
    status: string;
    asset_stage: string;
    source_name?: null | string;
    source_hash?: null | string;
    item_count?: null | number;
    hidden?: boolean;
    created_by?: null | string;
    create_time?: null | string;
    update_time?: null | string;
  }

  export interface AssetRegistry {
    id: number;
    asset_type: string;
    asset_key: string;
    display_name?: null | string;
    version_no: number;
    status: string;
    asset_stage: string;
    source_name?: null | string;
    source_uri?: null | string;
    source_hash?: null | string;
    content_json: Record<string, any>;
    metadata_json?: null | Record<string, any>;
    created_by?: null | string;
    create_time?: null | string;
    update_time?: null | string;
  }

  export interface AssetImportRun {
    id: number;
    source_name: string;
    source_uri?: null | string;
    source_hash?: null | string;
    status: string;
    imported_assets: number;
    summary_json?: null | Record<string, any>;
    created_by?: null | string;
    create_time?: null | string;
  }

  export interface AssetImportResult {
    import_run_id?: null | number;
    imported_assets: number;
    asset_keys: Array<[string, string]>;
    source_hash: string;
    summary_json?: null | Record<string, any>;
  }

  export interface AssetChangeRequest {
    id: number;
    source_text: string;
    requester?: null | string;
    context_json?: null | Record<string, any>;
    status: string;
    created_by?: null | string;
    create_time?: null | string;
    update_time?: null | string;
  }

  export interface AssetChangeProposal {
    id: number;
    request_id: number;
    risk_level: string;
    summary?: null | string;
    affected_assets_json?: null | Array<Record<string, any>>;
    proposed_changes_json: Record<string, any>;
    risk_notes_json?: null | string[];
    smoke_test_json?: null | Record<string, any>;
    status: string;
    applied_asset_ids_json?: null | number[];
    created_by?: null | string;
    applied_by?: null | string;
    create_time?: null | string;
    update_time?: null | string;
  }

  export interface AssetChangeProposalApplyResult {
    id: number;
    status: string;
    created_asset_ids: number[];
  }

  export interface CommentBusinessRuleDraft {
    id: number;
    status: string;
    asset_key: string;
    base_asset_id?: null | number;
    base_version_no?: null | number;
    rule_id?: null | string;
    source_row_no?: null | number;
    business_rule?: null | string;
    original_corpus?: null | string;
    draft_corpus: string;
    original_comment_prompt_bundle?: null | Record<string, any>;
    draft_comment_prompt_bundle?: null | Record<string, any>;
    created_by?: null | string;
    applied_by?: null | string;
    create_time?: null | string;
    update_time?: null | string;
  }

  export interface CommentBusinessRuleDraftPublishResult {
    draft: CommentBusinessRuleDraft;
    asset: AssetRegistry;
  }

  export interface BusinessRuleCopilotContext {
    asset: {
      id: number;
      asset_type: string;
      asset_key: string;
      display_name?: null | string;
      version_no: number;
      status: string;
      asset_stage: string;
      source_name?: null | string;
      created_by?: null | string;
      create_time?: null | string;
      update_time?: null | string;
    };
    content_type?: null | 'article' | 'comment';
    rule: {
      index: number;
      item_no: number;
      rule_id?: null | string;
      source_row_no?: null | number;
      business_rule?: null | string;
      corpus: string;
      examples: string[];
      supplements: string[];
      raw: Record<string, any>;
    };
    selected_draft?: null | CommentBusinessRuleDraft;
    drafts: CommentBusinessRuleDraft[];
    workflow: Record<string, any>;
  }

  export interface SystemPromptSubKeyword {
    keyword_code: string;
    keyword_name: string;
    enabled: boolean;
    weight: number;
    corpus: string[];
  }

  export interface SystemPromptKeywordCategory {
    applicable_content_types: string[];
    category_code: string;
    category_name: string;
    description?: string;
    enabled: boolean;
    required: boolean;
    selected_keyword_code?: string;
    selection_mode: string;
    sort_order: number;
    sub_keywords: SystemPromptSubKeyword[];
  }

  export interface SystemPromptKeywordContent {
    asset_type?: string;
    categories: SystemPromptKeywordCategory[];
    schema_version: string;
    selection_policy: Record<string, any>;
  }

  export interface SystemPromptKeywordAsset {
    id?: null | number;
    asset_type: string;
    asset_key: string;
    display_name?: null | string;
    version_no?: null | number;
    status: string;
    asset_stage: string;
    source: string;
    source_hash?: null | string;
    content_json: SystemPromptKeywordContent;
    metadata_json?: null | Record<string, any>;
    created_by?: null | string;
    create_time?: null | string;
    update_time?: null | string;
  }

  export interface SystemPromptKeywordExportResult {
    asset_key: string;
    csv_text: string;
    filename: string;
    version_no?: null | number;
  }

  export interface SystemPromptKeywordPreviewResult {
    asset_key: string;
    content_type: string;
    expert: Record<string, any>;
    rendered_prompt: string;
    selected_keywords: Array<Record<string, any>>;
  }
}

export async function getAssetSummariesApi(params?: {
  asset_key?: string;
  asset_stage?: string;
  asset_type?: string;
  include_hidden?: boolean;
}) {
  return requestClient.get<AssetsApi.AssetSummary[]>('/v1/assets/summary', {
    params,
  });
}

export async function getAssetDetailApi(
  assetType: string,
  assetKey: string,
  params?: { asset_stage?: string },
) {
  return requestClient.get<AssetsApi.AssetRegistry>(
    `/v1/assets/${assetType}/${assetKey}`,
    { params },
  );
}

export async function updateAssetVisibilityApi(
  assetType: string,
  assetKey: string,
  payload: { hidden: boolean; reason?: string; updated_by?: string },
  params?: { asset_stage?: string },
) {
  return requestClient.patch<AssetsApi.AssetRegistry>(
    `/v1/assets/${assetType}/${assetKey}/visibility`,
    payload,
    { params },
  );
}

export async function getAssetImportRunsApi(params?: { limit?: number }) {
  return requestClient.get<AssetsApi.AssetImportRun[]>(
    '/v1/assets/import-runs',
    { params },
  );
}

export async function getAssetChangeRequestsApi(params?: {
  limit?: number;
  status?: string;
}) {
  return requestClient.get<AssetsApi.AssetChangeRequest[]>(
    '/v1/assets/change-requests',
    { params },
  );
}

export async function getAssetChangeProposalsApi(params?: {
  limit?: number;
  status?: string;
}) {
  return requestClient.get<AssetsApi.AssetChangeProposal[]>(
    '/v1/assets/change-proposals',
    { params },
  );
}

export async function proposeComplianceRuleApi(requestId: number) {
  return requestClient.post<AssetsApi.AssetChangeProposal>(
    `/v1/assets/change-requests/${requestId}/propose-compliance-rule`,
  );
}

export async function applyAssetChangeProposalApi(proposalId: number) {
  return requestClient.post<AssetsApi.AssetChangeProposalApplyResult>(
    `/v1/assets/change-proposals/${proposalId}/apply`,
  );
}

export async function getCommentBusinessRuleDraftsApi(params: {
  asset_key: string;
  limit?: number;
  rule_id?: string;
  source_row_no?: number;
}) {
  return requestClient.get<AssetsApi.CommentBusinessRuleDraft[]>(
    '/v1/assets/comment-business-rule-drafts',
    { params },
  );
}

export async function getBusinessRuleCopilotContextApi(params: {
  asset_key: string;
  draft_id?: number;
  limit?: number;
  rule_id?: string;
  source_row_no?: number;
}) {
  return requestClient.get<AssetsApi.BusinessRuleCopilotContext>(
    '/v1/assets/business-rule-copilot-context',
    { params },
  );
}

export async function saveCommentBusinessRuleDraftApi(data: {
  asset_key: string;
  created_by?: string;
  draft_corpus: string;
  comment_prompt_bundle?: {
    generation_instruction: string;
    content_direction: string;
    activity_material: string[];
    writing_requirements: string[];
    notes: string[];
  };
  rule_id?: string;
  source_row_no?: number;
}) {
  return requestClient.post<AssetsApi.CommentBusinessRuleDraft>(
    '/v1/assets/comment-business-rule-drafts',
    data,
  );
}

export async function publishCommentBusinessRuleDraftApi(
  draftId: number,
  data: { created_by?: string },
) {
  return requestClient.post<AssetsApi.CommentBusinessRuleDraftPublishResult>(
    `/v1/assets/comment-business-rule-drafts/${draftId}/publish`,
    data,
  );
}

export async function updateCommentBusinessRuleExamplesApi(data: {
  asset_key: string;
  created_by?: string;
  examples: string[];
  rule_id?: string;
  source_row_no?: number;
  supplements?: string[];
}) {
  return requestClient.post<AssetsApi.AssetRegistry>(
    '/v1/assets/comment-business-rule-examples',
    data,
  );
}

export async function updateBusinessRuleExamplesApi(data: {
  asset_key: string;
  asset_type?: 'article' | 'comment';
  created_by?: string;
  examples: string[];
  rule_id?: string;
  source_row_no?: number;
  supplements?: string[];
}) {
  const params = data.asset_type ? `?asset_type=${data.asset_type}` : '';
  const { asset_type: _assetType, ...payload } = data;
  return requestClient.post<AssetsApi.AssetRegistry>(
    `/v1/assets/business-rule-examples${params}`,
    payload,
  );
}

export async function importCommentBusinessRuleSetApi(data: {
  asset_key: string;
  created_by?: string;
  display_name?: string;
  file: File;
}) {
  const formData = new FormData();
  formData.append('file', data.file);
  formData.append('asset_key', data.asset_key);
  if (data.display_name) {
    formData.append('display_name', data.display_name);
  }
  formData.append('created_by', data.created_by || 'maga-operator');
  return requestClient.post<AssetsApi.AssetImportResult>(
    '/v1/assets/imports/comment-business-rule-set',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 180_000,
    },
  );
}

export async function importArticleBusinessRuleSetApi(data: {
  asset_key: string;
  created_by?: string;
  display_name?: string;
  file: File;
}) {
  const formData = new FormData();
  formData.append('file', data.file);
  formData.append('asset_key', data.asset_key);
  if (data.display_name) {
    formData.append('display_name', data.display_name);
  }
  formData.append('created_by', data.created_by || 'maga-operator');
  return requestClient.post<AssetsApi.AssetImportResult>(
    '/v1/assets/imports/article-business-rule-set',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 180_000,
    },
  );
}

export async function getContentGenerationKeywordsApi(params?: {
  asset_key?: string;
}) {
  return requestClient.get<AssetsApi.SystemPromptKeywordAsset>(
    '/v1/assets/content-generation-keywords',
    { params },
  );
}

export async function getContentGenerationKeywordVersionsApi(params?: {
  asset_key?: string;
  limit?: number;
}) {
  return requestClient.get<AssetsApi.AssetSummary[]>(
    '/v1/assets/content-generation-keywords/versions',
    { params },
  );
}

export async function saveContentGenerationKeywordsApi(data: {
  asset_key: string;
  categories: AssetsApi.SystemPromptKeywordCategory[];
  created_by?: string;
  display_name?: string;
  selection_policy?: Record<string, any>;
}) {
  return requestClient.put<AssetsApi.AssetRegistry>(
    '/v1/assets/content-generation-keywords',
    data,
  );
}

export async function rollbackContentGenerationKeywordsApi(data: {
  asset_key: string;
  created_by?: string;
  version_no: number;
}) {
  return requestClient.post<AssetsApi.AssetRegistry>(
    '/v1/assets/content-generation-keywords/rollback',
    data,
  );
}

export async function importContentGenerationKeywordsApi(data: {
  asset_key: string;
  created_by?: string;
  display_name?: string;
  file: File;
}) {
  const formData = new FormData();
  formData.append('file', data.file);
  formData.append('asset_key', data.asset_key);
  if (data.display_name) {
    formData.append('display_name', data.display_name);
  }
  formData.append('created_by', data.created_by || 'maga-operator');
  return requestClient.post<AssetsApi.AssetImportResult>(
    '/v1/assets/imports/content-generation-keywords',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 180_000,
    },
  );
}

export async function exportContentGenerationKeywordsApi(params?: {
  asset_key?: string;
}) {
  return requestClient.get<AssetsApi.SystemPromptKeywordExportResult>(
    '/v1/assets/exports/content-generation-keywords',
    { params },
  );
}

export async function previewContentGenerationKeywordsApi(data: {
  asset_key: string;
  business_rule?: Record<string, any>;
  categories?: AssetsApi.SystemPromptKeywordCategory[];
  content_type: string;
  expert_config_code?: string;
  item_no?: number;
  output_fields?: string[];
  selection_policy?: Record<string, any>;
}) {
  return requestClient.post<AssetsApi.SystemPromptKeywordPreviewResult>(
    '/v1/assets/content-generation-keywords/preview',
    data,
  );
}
