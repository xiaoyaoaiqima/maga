import { requestClient } from '#/api/request';

export namespace ContentGenerationExpertApi {
  export interface Expert {
    id?: null | number;
    expert_config_code: string;
    expert_config_name: string;
    expert_type: string;
    stage: string;
    capability: string;
    content_type: string;
    description?: null | string;
    model_code?: null | string;
    model_config: Record<string, any>;
    prompt_template: string;
    enabled: boolean;
    source: string;
    variables: string[];
    update_time?: null | string;
  }

  export interface AuditFlow {
    source: string;
    max_rewrite_rounds: number;
    rewrite_capability: string;
    static_forbidden_terms: string[];
    business_forbidden_terms: string[];
  }

  export interface ExpertListResponse {
    items: Expert[];
    audit_flow: AuditFlow;
  }

  export interface ExpertUpsertRequest {
    expert_config_name: string;
    description?: null | string;
    model_code?: null | string;
    model_config: Record<string, any>;
    prompt_template: string;
    enabled: boolean;
    updated_by?: null | string;
  }

  export interface ExpertPreviewResponse {
    expert_config_code: string;
    rendered_prompt: string;
    model_config: Record<string, any>;
  }
}

export async function getContentGenerationExpertsApi() {
  return requestClient.get<ContentGenerationExpertApi.ExpertListResponse>(
    '/v1/content-agent/experts',
  );
}

export async function saveContentGenerationExpertApi(
  expertConfigCode: string,
  data: ContentGenerationExpertApi.ExpertUpsertRequest,
) {
  return requestClient.put<ContentGenerationExpertApi.Expert>(
    `/v1/content-agent/experts/${expertConfigCode}`,
    data,
  );
}

export async function previewContentGenerationExpertApi(
  expertConfigCode: string,
  data: {
    business_rule?: Record<string, any>;
    content_type?: string;
    forbidden_hits?: string[];
    previous_content?: Record<string, any>;
    selected_keywords?: Array<Record<string, any>>;
  },
) {
  return requestClient.post<ContentGenerationExpertApi.ExpertPreviewResponse>(
    `/v1/content-agent/experts/${expertConfigCode}/preview`,
    data,
  );
}
