export interface PromptDebugArticle {
  body: string;
  title: string;
}

function unwrapJsonFence(content: string) {
  const trimmed = content.trim();
  const lines = trimmed.split('\n');
  const firstLine = lines[0]?.trim();
  const lastLine = lines.at(-1)?.trim();

  if (/^```(?:json)?$/i.test(firstLine || '') && lastLine === '```') {
    return lines.slice(1, -1).join('\n').trim();
  }

  return trimmed;
}

function toArticle(value: unknown): null | PromptDebugArticle {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;

  const candidate = value as Record<string, unknown>;
  if (
    typeof candidate.title !== 'string' ||
    typeof candidate.body !== 'string'
  ) {
    return null;
  }

  return {
    body: candidate.body,
    title: candidate.title,
  };
}

export function parsePromptDebugArticles(
  content: string,
): PromptDebugArticle[] {
  if (!content.trim()) return [];

  try {
    const parsed = JSON.parse(unwrapJsonFence(content)) as unknown;
    const singleArticle = toArticle(parsed);
    if (singleArticle) return [singleArticle];

    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return [];
    }

    const items = (parsed as Record<string, unknown>).items;
    if (!Array.isArray(items)) return [];

    return items
      .map((item) => toArticle(item))
      .filter((item): item is PromptDebugArticle => item !== null);
  } catch {
    return [];
  }
}
