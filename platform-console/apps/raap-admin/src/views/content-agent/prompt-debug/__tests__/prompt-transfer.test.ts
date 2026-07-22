import { describe, expect, it } from 'vitest';

import {
  loadPromptDebugTransfer,
  savePromptDebugTransfer,
} from '../prompt-transfer';

function createStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
  };
}

describe('prompt debug transfer', () => {
  it('stores and restores the complete prompt without putting it in the URL', () => {
    const storage = createStorage();
    const prompt = '系统要求\n\n完整生文 Prompt';

    const key = savePromptDebugTransfer(prompt, storage);

    expect(key).toMatch(/^content-agent-prompt-debug:/);
    expect(loadPromptDebugTransfer(key, storage)).toBe(prompt);
  });

  it('ignores missing or invalid transfer data', () => {
    const storage = createStorage();
    storage.setItem('content-agent-prompt-debug:broken', '{');

    expect(loadPromptDebugTransfer(undefined, storage)).toBe('');
    expect(loadPromptDebugTransfer('other-key', storage)).toBe('');
    expect(
      loadPromptDebugTransfer('content-agent-prompt-debug:broken', storage),
    ).toBe('');
  });
});
