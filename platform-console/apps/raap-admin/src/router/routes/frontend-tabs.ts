import type { RouteRecordRaw } from 'vue-router';

/**
 * 侧边栏 Tab 由前端显式控制。
 *
 * 这些 routes 会进入 accessRoutes，并由 generateMenus 生成侧边栏菜单；
 * 不再依赖后端 sys_menu / /v1/auth/menus 决定运营台展示哪些入口。
 */
const frontendTabRoutes: RouteRecordRaw[] = [
  {
    name: 'BusinessRuleManagement',
    path: '/business-rules',
    component: () => import('#/views/business-rules/index.vue'),
    meta: {
      title: '生产工作台',
      icon: 'lucide:factory',
      order: -100,
      activeMenu: '/business-rules',
    },
  },
  {
    name: 'ContentAgentFeedback',
    path: '/content-agent/feedback',
    component: () => import('#/views/content-agent/feedback/index.vue'),
    meta: {
      title: '评价反馈',
      icon: 'lucide:message-square-check',
      order: -80,
      activeMenu: '/content-agent/feedback',
    },
  },
  {
    name: 'ContentAgentSystemPromptKeywords',
    path: '/content-agent/system-prompt-keywords',
    component: () =>
      import('#/views/content-agent/system-prompt-keywords/index.vue'),
    meta: {
      title: '系统关键词',
      icon: 'lucide:list-tree',
      order: -70,
      activeMenu: '/content-agent/system-prompt-keywords',
    },
  },
  {
    name: 'ContentGenerationExperts',
    path: '/content-agent/experts',
    component: () => import('#/views/content-agent/experts/index.vue'),
    meta: {
      title: '生文 Expert',
      icon: 'lucide:bot',
      order: -60,
      activeMenu: '/content-agent/experts',
    },
  },
  {
    name: 'MagaModelManagement',
    path: '/llm/provider',
    component: () => import('#/views/llm/provider/index.vue'),
    meta: {
      title: '模型配置',
      icon: 'lucide:sliders-horizontal',
      order: -50,
      activeMenu: '/llm/provider',
    },
  },
];

export { frontendTabRoutes };
