// @vitest-environment happy-dom
import { describe, expect, it } from 'vitest';

import { frontendTabRoutes } from '../frontend-tabs';
import { accessRoutes } from '..';

function collectPaths(routes: typeof frontendTabRoutes): string[] {
  const paths: string[] = [];

  const walk = (items: typeof frontendTabRoutes) => {
    for (const item of items) {
      paths.push(item.path);
      if (item.children?.length) {
        walk(item.children as typeof frontendTabRoutes);
      }
    }
  };

  walk(routes);
  return paths;
}

describe('frontend controlled sidebar tabs', () => {
  it('includes the xhs-writer generation workbench tab', () => {
    const paths = collectPaths(frontendTabRoutes);

    expect(paths).toContain('/content-agent/workbench');
    expect(
      frontendTabRoutes.find((route) => route.path === '/content-agent/workbench')
        ?.meta?.title,
    ).toBe('xhs-writer 生文');
  });

  it('uses the frontend tab config as accessible routes', () => {
    expect(accessRoutes).toEqual(frontendTabRoutes);
  });
});
