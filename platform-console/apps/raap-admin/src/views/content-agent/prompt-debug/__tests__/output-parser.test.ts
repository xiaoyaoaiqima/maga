import { describe, expect, it } from 'vitest';

import { parsePromptDebugArticles } from '../output-parser';

describe('parsePromptDebugArticles', () => {
  it('parses one title/body article', () => {
    expect(
      parsePromptDebugArticles('{"title":"今晚多读了一本","body":"正文内容"}'),
    ).toEqual([{ title: '今晚多读了一本', body: '正文内容' }]);
  });

  it('parses fenced multi-article output', () => {
    const content = [
      '```json',
      '{"items":[{"title":"第一篇","body":"正文一"},{"title":"第二篇","body":"正文二"}]}',
      '```',
    ].join('\n');

    expect(parsePromptDebugArticles(content)).toEqual([
      { title: '第一篇', body: '正文一' },
      { title: '第二篇', body: '正文二' },
    ]);
  });

  it('falls back for plain text or unrelated JSON', () => {
    expect(parsePromptDebugArticles('普通文本结果')).toEqual([]);
    expect(parsePromptDebugArticles('{"content":"普通文本结果"}')).toEqual([]);
  });
});
