// @vitest-environment happy-dom
import { describe, expect, it } from 'vitest';

import { overridesPreferences } from '#/preferences';

import { coreRoutes } from '../core';
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
  it('keeps the MVP sidebar to content, assets, reference extraction, keyword corpus, feedback, prompt optimization, and model management', () => {
    const paths = collectPaths(frontendTabRoutes);
    const titles = frontendTabRoutes.map((route) => route.meta?.title);

    expect(paths).toEqual([
      '/content-agent/workbench',
      '/assets/training',
      '/assets/reference-elements',
      '/keyword-corpus/template-variable-corpus',
      '/dashboard/rlhf',
      '/expert/prompt-optimizer',
      '/llm/provider',
    ]);
    expect(titles).toEqual([
      '内容生成',
      '资料训练',
      '例文抽取',
      '关键词语料',
      '反馈训练',
      '提示词优化',
      '模型管理',
    ]);
  });

  it('uses the frontend tab config as accessible routes', () => {
    expect(accessRoutes).toEqual(frontendTabRoutes);
  });

  it('defaults the console home to content generation', () => {
    expect(overridesPreferences.app?.defaultHomePath).toBe(
      '/content-agent/workbench',
    );
  });

  it('does not expose the legacy agent workbench in the MVP sidebar', () => {
    const paths = collectPaths(frontendTabRoutes);

    expect(paths).not.toContain('/agent/workbench');
  });

  it('does not expose legacy RAAP modules in the MVP sidebar', () => {
    const paths = collectPaths(frontendTabRoutes);

    expect(paths).not.toContain('/keyword_corpus/graph');
    expect(paths).not.toContain('/job/agent');
    expect(paths).not.toContain('/expert/calibration');
    expect(paths).not.toContain('/dashboard/ai-dashboard');
    expect(paths).not.toContain('/llm/routes');
    expect(paths).not.toContain('/llm/stats');
  });

  it('keeps direct legacy routes hidden from menus', () => {
    const rootRoute = coreRoutes.find((route) => route.path === '/');
    const legacyAgentWorkbench = rootRoute?.children?.find(
      (route) => route.path === 'agent/workbench',
    );
    const legacyDashboardPanel = rootRoute?.children?.find(
      (route) => route.path === 'dashboard/:panelId',
    );

    expect(legacyAgentWorkbench?.meta?.hideInMenu).toBe(true);
    expect(legacyDashboardPanel?.meta?.hideInMenu).toBe(true);
  });
});
