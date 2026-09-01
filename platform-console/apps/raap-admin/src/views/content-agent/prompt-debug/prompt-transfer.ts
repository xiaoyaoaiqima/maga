type PromptTransferStorage = Pick<Storage, 'getItem' | 'setItem'>;

const STORAGE_KEY = 'content-agent-prompt-debug:active';

export interface PromptDebugTransferPayload {
  max_tokens?: number;
  model_code?: string;
  prompt: string;
  system_prompt?: string;
  temperature?: number;
  thinking_mode?: 'default' | 'disabled' | 'enabled';
}

type PromptDebugTransferTarget = {
  max_tokens: number;
  model_code: string;
  prompt: string;
  system_prompt: string;
  temperature: number;
  thinking_mode: 'default' | 'disabled' | 'enabled';
};

export function applyPromptDebugTransfer(
  payload: PromptDebugTransferPayload,
  targets: PromptDebugTransferTarget[],
) {
  for (const target of targets) {
    target.prompt = payload.prompt;
    target.system_prompt = payload.system_prompt || '';
    if (payload.model_code) target.model_code = payload.model_code;
    if (typeof payload.temperature === 'number') {
      target.temperature = payload.temperature;
    }
    if (typeof payload.max_tokens === 'number') {
      target.max_tokens = payload.max_tokens;
    }
    if (payload.thinking_mode) {
      target.thinking_mode = payload.thinking_mode;
    }
  }
}

export function savePromptDebugTransfer(
  payload: PromptDebugTransferPayload,
  storage: PromptTransferStorage = sessionStorage,
) {
  storage.setItem(STORAGE_KEY, JSON.stringify(payload));
  return STORAGE_KEY;
}

export function loadPromptDebugTransfer(
  key: unknown,
  storage: PromptTransferStorage = sessionStorage,
) {
  if (key !== STORAGE_KEY) return null;
  const raw = storage.getItem(key);
  if (!raw) return null;
  try {
    const payload = JSON.parse(raw) as Partial<PromptDebugTransferPayload>;
    if (typeof payload.prompt !== 'string' || !payload.prompt) return null;
    return payload as PromptDebugTransferPayload;
  } catch {
    return null;
  }
}
