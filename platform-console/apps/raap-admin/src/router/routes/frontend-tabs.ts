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
    name: 'ContentAgentWorkbench',
    path: '/content-agent/workbench',
    component: () => import('#/views/content-agent/workbench/index.vue'),
    meta: {
      title: '生成历史',
      icon: 'lucide:history',
      order: -90,
      activeMenu: '/content-agent/workbench',
    },
  },
  {
    name: 'ContentAgentSystemPromptKeywords',
    path: '/content-agent/system-prompt-keywords',
    component: () =>
      import('#/views/content-agent/system-prompt-keywords/index.vue'),
    meta: {
      title: '表达扩散语料',
      icon: 'lucide:list-tree',
      order: -70,
      activeMenu: '/content-agent/system-prompt-keywords',
      authority: ['admin'],
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
      authority: ['admin'],
    },
  },
  {
    name: 'ContentAgentPromptDebug',
    path: '/content-agent/prompt-debug',
    component: () => import('#/views/content-agent/prompt-debug/index.vue'),
    meta: {
      title: '提示词调试',
      icon: 'lucide:flask-conical',
      order: -58,
      activeMenu: '/content-agent/prompt-debug',
      authority: ['admin'],
      fullPathKey: false,
    },
  },
  {
    name: 'SystemUserManagement',
    path: '/system/user',
    component: () => import('#/views/system/user/index.vue'),
    meta: {
      title: '用户管理',
      icon: 'lucide:users',
      order: -55,
      activeMenu: '/system/user',
      authority: ['admin'],
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
