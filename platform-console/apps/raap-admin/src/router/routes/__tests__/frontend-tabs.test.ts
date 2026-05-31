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
  it('keeps the sidebar focused on content flow pages and generation configs', () => {
    const paths = collectPaths(frontendTabRoutes);
    const titles = frontendTabRoutes.map((route) => route.meta?.title);

    expect(paths).toEqual([
      '/business-rules',
      '/content-agent/workbench',
      '/content-agent/feedback',
      '/content-agent/system-prompt-keywords',
      '/content-agent/experts',
      '/llm/provider',
    ]);
    expect(titles).toEqual([
      '业务规则',
      '生成结果',
      '评价反馈',
      '系统关键词',
      '生文 Expert',
      '模型配置',
    ]);
  });

  it('uses the frontend tab config as accessible routes', () => {
    expect(accessRoutes).toEqual(frontendTabRoutes);
  });

  it('defaults the console home to business rules', () => {
    expect(overridesPreferences.app?.defaultHomePath).toBe('/business-rules');
  });

  it('does not expose the legacy agent workbench in the MVP sidebar', () => {
    const paths = collectPaths(frontendTabRoutes);

    expect(paths).not.toContain('/agent/workbench');
  });

  it('does not expose legacy RAAP modules in the MVP sidebar', () => {
    const paths = collectPaths(frontendTabRoutes);

    expect(paths).not.toContain('/job/agent');
    expect(paths).not.toContain('/assets/training');
    expect(paths).not.toContain('/assets/reference-elements');
    expect(paths).not.toContain('/dashboard/rlhf');
    expect(paths).not.toContain('/expert/prompt-optimizer');
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
    const systemPromptKeywords = rootRoute?.children?.find(
      (route) => route.path === 'content-agent/system-prompt-keywords',
    );
    const contentExperts = rootRoute?.children?.find(
      (route) => route.path === 'content-agent/experts',
    );
    const modelManagement = rootRoute?.children?.find(
      (route) => route.path === 'llm/provider',
    );
    const modelRoutes = rootRoute?.children?.find(
      (route) => route.path === 'llm/routes',
    );
    const modelStats = rootRoute?.children?.find(
      (route) => route.path === 'llm/stats',
    );
    const legacyDashboardPanel = rootRoute?.children?.find(
      (route) => route.path === 'dashboard/:panelId',
    );

    expect(legacyAgentWorkbench?.meta?.hideInMenu).toBe(true);
    expect(systemPromptKeywords?.meta?.hideInMenu).toBe(true);
    expect(contentExperts?.meta?.hideInMenu).toBe(true);
    expect(modelManagement?.meta?.hideInMenu).toBe(true);
    expect(modelRoutes?.meta?.hideInMenu).toBe(true);
    expect(modelStats?.meta?.hideInMenu).toBe(true);
    expect(legacyDashboardPanel?.meta?.hideInMenu).toBe(true);
  });
});
