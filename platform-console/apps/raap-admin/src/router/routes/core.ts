import type { RouteRecordRaw } from 'vue-router';

import { LOGIN_PATH } from '@vben/constants';
import { preferences } from '@vben/preferences';

import { $t } from '#/locales';

const BasicLayout = () => import('#/layouts/basic.vue');
const AuthPageLayout = () => import('#/layouts/auth.vue');
/** 全局404页面 */
const fallbackNotFoundRoute: RouteRecordRaw = {
  component: () => import('#/views/_core/fallback/not-found.vue'),
  meta: {
    hideInBreadcrumb: true,
    hideInMenu: true,
    hideInTab: true,
    title: '404',
  },
  name: 'FallbackNotFound',
  path: '/:path(.*)*',
};

/** 基本路由，这些路由是必须存在的 */
const coreRoutes: RouteRecordRaw[] = [
  /**
   * 根路由
   * 使用基础布局，作为所有页面的父级容器，子级就不必配置BasicLayout。
   * 此路由必须存在，且不应修改
   */
  {
    component: BasicLayout,
    meta: {
      hideInBreadcrumb: true,
      title: 'Root',
    },
    name: 'Root',
    path: '/',
    redirect: preferences.app.defaultHomePath,
    children: [
      {
        name: 'Profile',
        path: 'profile',
        component: () => import('#/views/_core/profile/index.vue'),
        meta: {
          title: $t('page.auth.profile'),
        },
      },
      // Legacy hidden routes: kept for direct debugging/backward compatibility,
      // but intentionally excluded from the MAGA MVP sidebar.
      {
        name: 'AgentWorkbench',
        path: 'agent/workbench',
        component: () => import('#/views/agent/workbench/index.vue'),
        meta: {
          title: 'Agent 工作台',
          icon: 'RobotOutlined',
          hideInMenu: true,
          order: -100,
          activeMenu: '/agent/workbench',
        },
      },
      {
        name: 'AgentArticles',
        path: 'agent/:code/articles',
        component: () => import('#/views/job/agent/articles.vue'),
        meta: {
          title: 'Agent 文章详情',
          hideInMenu: true,
          hideInTab: false,
          fullPathKey: false, // 使用 path 而不是 fullPath 作为 tab key
        },
      },
      {
        name: 'ContentAgentWorkbench',
        path: 'content-agent/workbench',
        component: () => import('#/views/content-agent/workbench/index.vue'),
        meta: {
          title: '内容生成',
          icon: 'RobotOutlined',
          order: -99,
          activeMenu: '/content-agent/workbench',
        },
      },
      {
        name: 'MagaAssetTraining',
        path: 'assets/training',
        component: () => import('#/views/assets/training/index.vue'),
        meta: {
          title: '资料训练',
          icon: 'DatabaseOutlined',
          activeMenu: '/assets/training',
        },
      },
      {
        name: 'BusinessRuleManagement',
        path: 'business-rules',
        component: () => import('#/views/business-rules/index.vue'),
        meta: {
          title: '业务规则',
          icon: 'DatabaseOutlined',
          activeMenu: '/business-rules',
        },
      },
      {
        name: 'SystemPromptKeywords',
        path: 'content-agent/system-prompt-keywords',
        component: () =>
          import('#/views/content-agent/system-prompt-keywords/index.vue'),
        meta: {
          title: '系统提示词关键词',
          icon: 'DatabaseOutlined',
          activeMenu: '/content-agent/system-prompt-keywords',
        },
      },
      {
        name: 'ReferenceElementExtractor',
        path: 'assets/reference-elements',
        component: () => import('#/views/assets/reference-elements/index.vue'),
        meta: {
          title: '例文抽取',
          icon: 'DatabaseOutlined',
          activeMenu: '/assets/reference-elements',
        },
      },
      {
        name: 'DashboardRlhf',
        path: 'dashboard/rlhf',
        component: () => import('#/views/dashboard/rlhf/index.vue'),
        meta: {
          title: '反馈训练',
          icon: 'LineChartOutlined',
          activeMenu: '/dashboard/rlhf',
        },
      },
      {
        name: 'ExpertPromptOptimizer',
        path: 'expert/prompt-optimizer',
        component: () => import('#/views/expert/prompt-optimizer/index.vue'),
        meta: {
          title: '提示词优化',
          icon: 'RobotOutlined',
          activeMenu: '/expert/prompt-optimizer',
        },
      },
      {
        name: 'MagaModelManagement',
        path: 'llm/provider',
        component: () => import('#/views/llm/provider/index.vue'),
        meta: {
          title: '模型管理',
          icon: 'RobotOutlined',
          activeMenu: '/llm/provider',
        },
      },
      {
        name: 'DashboardPanel',
        path: 'dashboard/:panelId',
        component: () => import('#/views/dashboard/ai-dashboard/index.vue'),
        meta: {
          title: 'AI 可视化',
          hideInMenu: true,
          hideInTab: false,
          activeMenu: '/dashboard/ai-dashboard',
        },
      },
      {
        name: 'AgentEdit',
        path: 'job/agent/edit',
        component: () => import('#/views/job/agent/edit/index.vue'),
        meta: {
          title: '修改 Agent',
          hideInMenu: true,
          hideInTab: false,
          fullPathKey: false,
        },
      },
    ],
  },
  {
    component: AuthPageLayout,
    meta: {
      hideInTab: true,
      title: 'Authentication',
    },
    name: 'Authentication',
    path: '/auth',
    redirect: LOGIN_PATH,
    children: [
      {
        name: 'Login',
        path: 'login',
        component: () => import('#/views/_core/authentication/login.vue'),
        meta: {
          title: $t('page.auth.login'),
        },
      },
      {
        name: 'CodeLogin',
        path: 'code-login',
        component: () => import('#/views/_core/authentication/code-login.vue'),
        meta: {
          title: $t('page.auth.codeLogin'),
        },
      },
      {
        name: 'QrCodeLogin',
        path: 'qrcode-login',
        component: () =>
          import('#/views/_core/authentication/qrcode-login.vue'),
        meta: {
          title: $t('page.auth.qrcodeLogin'),
        },
      },
      {
        name: 'ForgetPassword',
        path: 'forget-password',
        component: () =>
          import('#/views/_core/authentication/forget-password.vue'),
        meta: {
          title: $t('page.auth.forgetPassword'),
        },
      },
      {
        name: 'Register',
        path: 'register',
        component: () => import('#/views/_core/authentication/register.vue'),
        meta: {
          title: $t('page.auth.register'),
        },
      },
    ],
  },
];

export { coreRoutes, fallbackNotFoundRoute };
