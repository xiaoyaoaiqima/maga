import { requestClient } from '#/api/request';

export namespace TemplateVariableCorpusApi {
  export type CorpusStatus = 'active' | 'archived' | 'draft';

  export interface TemplateVariable {
    name: string;
    corpus_count: number;
    active_count: number;
    draft_count: number;
  }

  export interface VariableListResponse {
    template_path: string;
    variables: TemplateVariable[];
  }

  export interface CorpusItem {
    id: string;
    tenant_code: string;
    variable_name: string;
    name: string;
    markdown: string;
    tags: string[];
    status: CorpusStatus;
    source?: null | string;
    created_by?: null | string;
    updated_by?: null | string;
    created_at?: null | string;
    updated_at?: null | string;
  }

  export interface CorpusListResponse {
    items: CorpusItem[];
    page_info: {
      page: number;
      page_size: number;
      total: number;
      total_pages: number;
    };
  }

  export interface CorpusCreatePayload {
    variable_name: string;
    name: string;
    markdown: string;
    tags?: string[];
    status?: CorpusStatus;
    source?: string;
    tenant_code?: string;
    created_by?: string;
  }

  export interface CorpusUpdatePayload {
    name?: string;
    markdown?: string;
    tags?: string[];
    status?: CorpusStatus;
    source?: string;
    updated_by?: string;
  }

  export interface PromptPreviewPayload {
    tenant_code?: string;
    selected_item_ids?: Record<string, string>;
    draft_values?: Record<string, string>;
    fill_mode?: 'selected_only' | 'selected_or_first';
    missing_policy?: 'empty' | 'keep_placeholder';
  }

  export interface PromptPreviewResponse {
    template_path: string;
    rendered_prompt: string;
    used_items: Record<string, CorpusItem>;
    missing_variables: string[];
  }
}

export async function getTemplateVariablesApi(params?: {
  tenant_code?: string;
}) {
  return requestClient.get<TemplateVariableCorpusApi.VariableListResponse>(
    '/v1/keyword-corpus/template-variable-corpus/variables',
    { params },
  );
}

export async function listTemplateVariableCorpusApi(params?: {
  keyword?: string;
  page?: number;
  page_size?: number;
  status?: string;
  tenant_code?: string;
  variable_name?: string;
}) {
  return requestClient.get<TemplateVariableCorpusApi.CorpusListResponse>(
    '/v1/keyword-corpus/template-variable-corpus',
    { params },
  );
}

export async function createTemplateVariableCorpusApi(
  data: TemplateVariableCorpusApi.CorpusCreatePayload,
) {
  return requestClient.post<TemplateVariableCorpusApi.CorpusItem>(
    '/v1/keyword-corpus/template-variable-corpus',
    data,
  );
}

export async function updateTemplateVariableCorpusApi(
  itemId: string,
  data: TemplateVariableCorpusApi.CorpusUpdatePayload,
) {
  return requestClient.put<TemplateVariableCorpusApi.CorpusItem>(
    `/v1/keyword-corpus/template-variable-corpus/${itemId}`,
    data,
  );
}

export async function archiveTemplateVariableCorpusApi(itemId: string) {
  return requestClient.delete<{ archived: boolean }>(
    `/v1/keyword-corpus/template-variable-corpus/${itemId}`,
  );
}

export async function previewTemplatePromptApi(
  data: TemplateVariableCorpusApi.PromptPreviewPayload,
) {
  return requestClient.post<TemplateVariableCorpusApi.PromptPreviewResponse>(
    '/v1/keyword-corpus/template-variable-corpus/preview',
    data,
  );
}
