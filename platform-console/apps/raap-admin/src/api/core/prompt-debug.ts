import { requestClient } from '#/api/request';

export namespace PromptDebugApi {
  export interface RunRequest {
    prompt: string;
    model_code: string;
    temperature?: number;
    max_tokens?: number;
    thinking_mode?: 'default' | 'disabled' | 'enabled';
    system_prompt?: string;
    run_group_id?: string;
    workbench_mode?: 'compare' | 'single';
    panel_key?: 'left' | 'right';
    item_index?: number;
    batch_size?: number;
  }

  export interface TokenUsage {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
  }

  export interface RunResponse {
    success: boolean;
    content?: null | string;
    model_code?: null | string;
    provider_code?: null | string;
    provider_model?: null | string;
    usage?: null | TokenUsage;
    latency_ms?: null | number;
    error_message?: null | string;
    history_id?: null | number;
    run_group_id?: null | string;
  }

  export interface HistoryItem {
    id: number;
    run_group_id: string;
    workbench_mode: 'compare' | 'single';
    panel_key: 'left' | 'right';
    item_index: number;
    batch_size: number;
    prompt: string;
    system_prompt?: null | string;
    requested_model_code: string;
    temperature: number;
    max_tokens: number;
    thinking_mode: 'default' | 'disabled' | 'enabled';
    success: boolean;
    content?: null | string;
    model_code?: null | string;
    provider_code?: null | string;
    provider_model?: null | string;
    token_usage?: null | TokenUsage;
    latency_ms?: null | number;
    error_message?: null | string;
    create_time?: null | string;
  }

  export interface HistoryGroupSummary {
    run_group_id: string;
    workbench_mode: 'compare' | 'single';
    create_time?: null | string;
    total_count: number;
    success_count: number;
    failed_count: number;
    panel_keys: Array<'left' | 'right'>;
    model_codes: string[];
    prompt_preview: string;
  }

  export interface HistoryListResponse {
    items: HistoryGroupSummary[];
  }

  export interface HistoryGroupDetail {
    run_group_id: string;
    workbench_mode: 'compare' | 'single';
    create_time?: null | string;
    records: HistoryItem[];
  }
}

export async function runPromptDebugApi(data: PromptDebugApi.RunRequest) {
  return requestClient.post<PromptDebugApi.RunResponse>(
    '/v1/content-agent/prompt-debug/run',
    data,
    {
      timeout: 180_000,
    },
  );
}

export async function getPromptDebugHistoryApi(limit = 30) {
  return requestClient.get<PromptDebugApi.HistoryListResponse>(
    '/v1/content-agent/prompt-debug/history',
    { params: { limit } },
  );
}

export async function getPromptDebugHistoryDetailApi(runGroupId: string) {
  return requestClient.get<PromptDebugApi.HistoryGroupDetail>(
    `/v1/content-agent/prompt-debug/history/${runGroupId}`,
  );
}
