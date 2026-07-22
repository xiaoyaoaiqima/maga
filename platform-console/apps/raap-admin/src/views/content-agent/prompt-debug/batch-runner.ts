export const MAX_PROMPT_DEBUG_BATCH_SIZE = 20;

export function normalizePromptDebugBatchSize(size: number) {
  return Math.min(
    MAX_PROMPT_DEBUG_BATCH_SIZE,
    Math.max(1, Math.floor(size || 1)),
  );
}

export async function runPromptDebugBatch<T>(
  size: number,
  run: (index: number) => Promise<T>,
) {
  const batchSize = normalizePromptDebugBatchSize(size);
  return Promise.all(
    Array.from({ length: batchSize }, (_, index) => run(index)),
  );
}
