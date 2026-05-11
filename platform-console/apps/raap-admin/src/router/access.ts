import type {
  ComponentRecordType,
  GenerateMenuAndRoutesOptions,
} from '@vben/types';

import { generateAccessible } from '@vben/access';

import { BasicLayout, IFrameView } from '#/layouts';

const forbiddenComponent = () => import('#/views/_core/fallback/forbidden.vue');

async function generateAccess(options: GenerateMenuAndRoutesOptions) {
  const pageMap: ComponentRecordType = import.meta.glob('../views/**/*.vue');

  const layoutMap: ComponentRecordType = {
    BasicLayout,
    IFrameView,
  };

  return await generateAccessible('frontend', {
    ...options,
    // 侧边栏 Tab 改为前端 routes/frontend-tabs.ts 显式控制；
    // 这里不能再读取可持久化的 preferences.app.accessMode，避免旧缓存里的 backend
    // 让 fetchMenuListAsync 返回空数组后生成空菜单。
    fetchMenuListAsync: async () => [],
    // 可以指定没有权限跳转403页面
    forbiddenComponent,
    // 如果 route.meta.menuVisibleWithForbidden = true
    layoutMap,
    pageMap,
  });
}

export { generateAccess };
