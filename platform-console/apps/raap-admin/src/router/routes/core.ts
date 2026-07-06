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
      {
        name: 'ContentAgentWorkbench',
        path: 'content-agent/workbench',
        component: () => import('#/views/content-agent/workbench/index.vue'),
        meta: {
          title: '生成历史',
          icon: 'RobotOutlined',
          hideInMenu: true,
          order: -99,
          activeMenu: '/business-rules',
        },
      },
      {
        name: 'BusinessRuleManagement',
        path: 'business-rules',
        component: () => import('#/views/business-rules/index.vue'),
        meta: {
          title: '生产工作台',
          icon: 'DatabaseOutlined',
          activeMenu: '/business-rules',
        },
      },
      {
        name: 'ContentAgentFeedback',
        path: 'content-agent/feedback',
        component: () => import('#/views/content-agent/feedback/index.vue'),
        meta: {
          title: '评价反馈',
          icon: 'LineChartOutlined',
          activeMenu: '/content-agent/feedback',
          authority: ['admin'],
        },
      },
      {
        name: 'ContentAgentSystemPromptKeywords',
        path: 'content-agent/system-prompt-keywords',
        component: () =>
          import('#/views/content-agent/system-prompt-keywords/index.vue'),
        meta: {
          title: '表达扩散语料',
          hideInMenu: true,
          hideInTab: false,
          activeMenu: '/content-agent/system-prompt-keywords',
          authority: ['admin'],
        },
      },
      {
        name: 'ContentGenerationExperts',
        path: 'content-agent/experts',
        component: () => import('#/views/content-agent/experts/index.vue'),
        meta: {
          title: '生文 Expert',
          hideInMenu: true,
          hideInTab: false,
          activeMenu: '/content-agent/experts',
          authority: ['admin'],
        },
      },
      {
        name: 'SystemUserManagement',
        path: 'system/user',
        component: () => import('#/views/system/user/index.vue'),
        meta: {
          title: '用户管理',
          hideInMenu: true,
          hideInTab: false,
          activeMenu: '/system/user',
          authority: ['admin'],
        },
      },
      {
        name: 'MagaModelManagement',
        path: 'llm/provider',
        component: () => import('#/views/llm/provider/index.vue'),
        meta: {
          title: '模型配置',
          hideInMenu: true,
          hideInTab: false,
          activeMenu: '/llm/provider',
        },
      },
      {
        name: 'MagaModelRoutes',
        path: 'llm/routes',
        component: () => import('#/views/llm/routes/index.vue'),
        meta: {
          title: '模型路由',
          hideInMenu: true,
          hideInTab: false,
          activeMenu: '/llm/provider',
        },
      },
      {
        name: 'MagaModelStats',
        path: 'llm/stats',
        component: () => import('#/views/llm/stats/index.vue'),
        meta: {
          title: '模型统计',
          hideInMenu: true,
          hideInTab: false,
          activeMenu: '/llm/provider',
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
