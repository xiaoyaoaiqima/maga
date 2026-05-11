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
      title: 'xhs-writer 生文',
      icon: 'lucide:pen-line',
      order: -100,
      activeMenu: '/content-agent/workbench',
    },
  },
  {
    name: 'DashboardRlhf',
    path: '/dashboard/rlhf',
    component: () => import('#/views/dashboard/rlhf/index.vue'),
    meta: {
      title: 'RLHF 分析',
      icon: 'lucide:line-chart',
      order: -80,
      activeMenu: '/dashboard/rlhf',
    },
  },
  {
    name: 'AgentWorkbench',
    path: '/agent/workbench',
    component: () => import('#/views/agent/workbench/index.vue'),
    meta: {
      title: 'Agent 工作台',
      icon: 'lucide:bot',
      order: -70,
      activeMenu: '/agent/workbench',
    },
  },
  {
    name: 'ExpertPromptOptimizer',
    path: '/expert/prompt-optimizer',
    component: () => import('#/views/expert/prompt-optimizer/index.vue'),
    meta: {
      title: '提示词优化工作台',
      icon: 'lucide:sparkles',
      order: -60,
      activeMenu: '/expert/prompt-optimizer',
    },
  },
];

export { frontendTabRoutes };
