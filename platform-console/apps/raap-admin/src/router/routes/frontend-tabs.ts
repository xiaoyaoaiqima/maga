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
      title: '业务规则',
      icon: 'lucide:file-cog',
      order: -100,
      activeMenu: '/business-rules',
    },
  },
  {
    name: 'ContentAgentWorkbench',
    path: '/content-agent/workbench',
    component: () => import('#/views/content-agent/workbench/index.vue'),
    meta: {
      title: '生成结果',
      icon: 'lucide:pen-line',
      order: -90,
      activeMenu: '/content-agent/workbench',
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
];

export { frontendTabRoutes };
