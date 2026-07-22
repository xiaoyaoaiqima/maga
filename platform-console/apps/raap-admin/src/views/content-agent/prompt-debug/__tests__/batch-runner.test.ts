import { describe, expect, it } from 'vitest';

import {
  normalizePromptDebugBatchSize,
  runPromptDebugBatch,
} from '../batch-runner';

describe('prompt debug batch runner', () => {
  it('starts every requested run concurrently and preserves result order', async () => {
    const started: number[] = [];
    let release: (() => void) | undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });

    const resultPromise = runPromptDebugBatch(3, async (index) => {
      started.push(index);
      await gate;
      return `result-${index}`;
    });

    await Promise.resolve();
    expect(started).toEqual([0, 1, 2]);

    release?.();
    await expect(resultPromise).resolves.toEqual([
      'result-0',
      'result-1',
      'result-2',
    ]);
  });

  it('keeps the batch size within the supported range', () => {
    expect(normalizePromptDebugBatchSize(0)).toBe(1);
    expect(normalizePromptDebugBatchSize(4.8)).toBe(4);
    expect(normalizePromptDebugBatchSize(100)).toBe(20);
  });
});
