type PromptTransferStorage = Pick<Storage, 'getItem' | 'setItem'>;

const STORAGE_PREFIX = 'content-agent-prompt-debug:';

export interface PromptDebugTransferPayload {
  max_tokens?: number;
  model_code?: string;
  prompt: string;
  system_prompt?: string;
  temperature?: number;
}

export function savePromptDebugTransfer(
  payload: PromptDebugTransferPayload,
  storage: PromptTransferStorage = sessionStorage,
) {
  const key = `${STORAGE_PREFIX}${Date.now()}-${Math.random()
    .toString(36)
    .slice(2, 8)}`;
  storage.setItem(key, JSON.stringify(payload));
  return key;
}

export function loadPromptDebugTransfer(
  key: unknown,
  storage: PromptTransferStorage = sessionStorage,
) {
  if (typeof key !== 'string' || !key.startsWith(STORAGE_PREFIX)) return null;
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
