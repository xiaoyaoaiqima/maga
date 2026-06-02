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

export async function importCommentAngleRuleSetApi(data: {
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
    '/v1/assets/imports/comment-angle-rule-set',
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 180_000,
    },
  );
}

export async function importProductExperienceRuleSetApi(data: {
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
    '/v1/assets/imports/product-experience-rule-set',
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
