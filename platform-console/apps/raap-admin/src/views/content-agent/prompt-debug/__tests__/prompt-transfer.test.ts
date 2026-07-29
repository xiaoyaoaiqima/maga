import { describe, expect, it } from 'vitest';

import {
  applyPromptDebugTransfer,
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
    const payload = {
      max_tokens: 256,
      model_code: 'deepseek-v4-flash',
      prompt: '完整生文 Prompt',
      system_prompt: '系统要求',
      temperature: 0.85,
    };

    const key = savePromptDebugTransfer(payload, storage);

    expect(key).toBe('content-agent-prompt-debug:active');
    expect(loadPromptDebugTransfer(key, storage)).toEqual(payload);
  });

  it('ignores missing or invalid transfer data', () => {
    const storage = createStorage();
    storage.setItem('content-agent-prompt-debug:broken', '{');

    expect(loadPromptDebugTransfer(undefined, storage)).toBeNull();
    expect(loadPromptDebugTransfer('other-key', storage)).toBeNull();
    expect(
      loadPromptDebugTransfer('content-agent-prompt-debug:broken', storage),
    ).toBeNull();
  });

  it('applies the generation config to both comparison panels', () => {
    const panels = [
      {
        max_tokens: 1500,
        model_code: 'default-model',
        prompt: '',
        system_prompt: '',
        temperature: 0.9,
      },
      {
        max_tokens: 1500,
        model_code: 'default-model',
        prompt: '',
        system_prompt: '',
        temperature: 0.9,
      },
    ];

    applyPromptDebugTransfer(
      {
        max_tokens: 256,
        model_code: 'deepseek-v4-flash',
        prompt: '完整生文 Prompt',
        system_prompt: '系统要求',
        temperature: 0.85,
      },
      panels,
    );

    expect(panels).toEqual([
      {
        max_tokens: 256,
        model_code: 'deepseek-v4-flash',
        prompt: '完整生文 Prompt',
        system_prompt: '系统要求',
        temperature: 0.85,
      },
      {
        max_tokens: 256,
        model_code: 'deepseek-v4-flash',
        prompt: '完整生文 Prompt',
        system_prompt: '系统要求',
        temperature: 0.85,
      },
    ]);
  });
});
