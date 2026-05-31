import type { RouteRecordRaw } from 'vue-router';

/**
 * 侧边栏 Tab 由前端显式控制。
 *
 * 这些 routes 会进入 accessRoutes，并由 generateMenus 生成侧边栏菜单；
 * 不再依赖后端 sys_menu / /v1/auth/menus 决定运营台展示哪些入口。
 */
const frontendTabRoutes: RouteRecordRaw[] = [
  {
    name: 'ContentAgentWorkbench',
    path: '/content-agent/workbench',
    component: () => import('#/views/content-agent/workbench/index.vue'),
    meta: {
      title: '内容生成',
      icon: 'lucide:pen-line',
      order: -100,
      activeMenu: '/content-agent/workbench',
    },
  },
  {
    name: 'MagaAssetTraining',
    path: '/assets/training',
    component: () => import('#/views/assets/training/index.vue'),
    meta: {
      title: '资料训练',
      icon: 'lucide:database',
      order: -90,
      activeMenu: '/assets/training',
    },
  },
  {
    name: 'BusinessRuleManagement',
    path: '/business-rules',
    component: () => import('#/views/business-rules/index.vue'),
    meta: {
      title: '业务规则',
      icon: 'lucide:file-cog',
      order: -88,
      activeMenu: '/business-rules',
    },
  },
  {
    name: 'SystemPromptKeywords',
    path: '/content-agent/system-prompt-keywords',
    component: () =>
      import('#/views/content-agent/system-prompt-keywords/index.vue'),
    meta: {
      title: '系统提示词关键词',
      icon: 'lucide:list-plus',
      order: -86,
      activeMenu: '/content-agent/system-prompt-keywords',
    },
  },
  {
    name: 'ReferenceElementExtractor',
    path: '/assets/reference-elements',
    component: () => import('#/views/assets/reference-elements/index.vue'),
    meta: {
      title: '例文抽取',
      icon: 'lucide:scan-text',
      order: -85,
      activeMenu: '/assets/reference-elements',
    },
  },
  {
    name: 'DashboardRlhf',
    path: '/dashboard/rlhf',
    component: () => import('#/views/dashboard/rlhf/index.vue'),
    meta: {
      title: '反馈训练',
      icon: 'lucide:line-chart',
      order: -80,
      activeMenu: '/dashboard/rlhf',
    },
  },
  {
    name: 'ExpertPromptOptimizer',
    path: '/expert/prompt-optimizer',
    component: () => import('#/views/expert/prompt-optimizer/index.vue'),
    meta: {
      title: '提示词优化',
      icon: 'lucide:sparkles',
      order: -60,
      activeMenu: '/expert/prompt-optimizer',
    },
  },
  {
    name: 'MagaModelManagement',
    path: '/llm/provider',
    component: () => import('#/views/llm/provider/index.vue'),
    meta: {
      title: '模型管理',
      icon: 'lucide:cpu',
      order: -40,
      activeMenu: '/llm/provider',
    },
  },
];

export { frontendTabRoutes };
