import { requestClient } from '#/api/request';

export namespace PromptOptimizerApi {
  export type OptimizerMode =
    | 'batch_patch'
    | 'critic_patch'
    | 'global_refactor'
    | 'local_patch';

  export interface Patch {
    id: number;
    run_id: number;
    patch_index: number;
    operation: 'delete' | 'insert_after' | 'insert_before' | 'replace';
    old_text: string;
    new_text?: null | string;
    reason?: null | string;
    status: 'accepted' | 'edited' | 'pending' | 'rejected';
    edited_new_text?: null | string;
    review_comment?: null | string;
  }

  export interface Run {
    id: number;
    prompt_id: number;
    prompt_version_id: number;
    issue_id?: null | number;
    mode: OptimizerMode;
    model?: null | string;
    base_url?: null | string;
    temperature?: null | string;
    max_tokens?: null | number;
    status: 'failed' | 'pending' | 'running' | 'succeeded';
    input_snapshot?: null | Record<string, any>;
    raw_output?: null | string;
    parsed_output?: null | Record<string, any>;
    error_message?: null | string;
    patches: Patch[];
    create_time?: null | string;
    update_time?: null | string;
  }

  export interface CreateRunRequest {
    mode: OptimizerMode;
    problem_text: string;
    prompt_content?: string;
    prompt_name?: string;
    prompt_id?: number;
    prompt_version_id?: number;
    prompt_type?: 'critic' | 'generation' | 'other';
    generated_content?: string;
    generated_title?: string;
    model?: string;
    base_url?: string;
    temperature?: number;
    max_tokens?: number;
    timeout?: number;
    json_mode?: boolean;
    include_revised_prompt?: boolean;
  }

  export interface UpdatePatchRequest {
    status?: 'accepted' | 'edited' | 'pending' | 'rejected';
    edited_new_text?: string;
    review_comment?: string;
  }

  export interface ApplyPatchesRequest {
    patch_ids?: number[];
    change_summary?: string;
    created_by?: string;
    save_version?: boolean;
  }

  export interface ApplyPatchesResponse {
    applied_patch_ids: number[];
    conflicts: { patch_id: number; reason: string }[];
    candidate_content: string;
    new_version?: null | {
      id: number;
      prompt_id: number;
      version_no: number;
      content: string;
    };
  }
}

export async function createPromptOptimizerRunApi(
  data: PromptOptimizerApi.CreateRunRequest,
) {
  return requestClient.post<PromptOptimizerApi.Run>(
    '/v1/prompt-optimizer/runs',
    data,
  );
}

export async function updatePromptPatchApi(
  patchId: number,
  data: PromptOptimizerApi.UpdatePatchRequest,
) {
  return (requestClient as any).request(`/v1/prompt-optimizer/patches/${patchId}`, {
    data,
    method: 'PATCH',
  }) as Promise<PromptOptimizerApi.Patch>;
}

export async function applyPromptPatchesApi(
  runId: number,
  data: PromptOptimizerApi.ApplyPatchesRequest,
) {
  return requestClient.post<PromptOptimizerApi.ApplyPatchesResponse>(
    `/v1/prompt-optimizer/runs/${runId}/apply`,
    data,
  );
}
