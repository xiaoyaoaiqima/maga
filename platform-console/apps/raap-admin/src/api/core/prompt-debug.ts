import { requestClient } from '#/api/request';

export namespace PromptDebugApi {
  export interface RunRequest {
    prompt: string;
    model_code: string;
    temperature?: number;
    max_tokens?: number;
    system_prompt?: string;
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
