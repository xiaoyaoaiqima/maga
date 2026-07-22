type PromptTransferStorage = Pick<Storage, 'getItem' | 'setItem'>;

const STORAGE_PREFIX = 'content-agent-prompt-debug:';

export function savePromptDebugTransfer(
  prompt: string,
  storage: PromptTransferStorage = sessionStorage,
) {
  const key = `${STORAGE_PREFIX}${Date.now()}-${Math.random()
    .toString(36)
    .slice(2, 8)}`;
  storage.setItem(key, JSON.stringify({ prompt }));
  return key;
}

export function loadPromptDebugTransfer(
  key: unknown,
  storage: PromptTransferStorage = sessionStorage,
) {
  if (typeof key !== 'string' || !key.startsWith(STORAGE_PREFIX)) return '';
  const raw = storage.getItem(key);
  if (!raw) return '';
  try {
    const payload = JSON.parse(raw) as { prompt?: unknown };
    return typeof payload.prompt === 'string' ? payload.prompt : '';
  } catch {
    return '';
  }
}
