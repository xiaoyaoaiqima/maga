import { initPreferences } from '@vben/preferences';
import { unmountGlobalLoading } from '@vben/utils';

import { overridesPreferences } from './preferences';

function clear_namespaced_storage(namespace: string) {
  const prefixes = [`${namespace}-`, `${namespace}:`, `${namespace}_`];

  const clear = (storage: Storage) => {
    try {
      // 倒序删除，避免 key 索引变化导致漏删
      for (let i = storage.length - 1; i >= 0; i -= 1) {
        const key = storage.key(i);
        if (!key) continue;
        if (prefixes.some((p) => key.startsWith(p))) storage.removeItem(key);
      }
    } catch {
      // ignore
    }
  };

  clear(localStorage);
  clear(sessionStorage);
}

/**
 * 应用初始化完成之后再进行页面加载渲染
 */
async function initApplication() {
  // name用于指定项目唯一标识
  // 用于区分不同项目的偏好设置以及存储数据的key前缀以及其他一些需要隔离的数据
  const env = import.meta.env.PROD ? 'prod' : 'dev';
  const appVersion = import.meta.env.VITE_APP_VERSION;
  const namespace = `${import.meta.env.VITE_APP_NAMESPACE}-${appVersion}-${env}`;

  // 存储结构版本（用于自动清理旧缓存，避免“改了默认首页/路由注入逻辑但用户还在用旧值”）
  // 只要涉及菜单/权限/默认首页/路由注入等变更，就应该 bump 这个版本号。
  const storage_schema_version = '2026-05-10-frontend-tabs';
  const schema_key = `${namespace}-storage-schema-version`;
  const previous_version = localStorage.getItem(schema_key);
  if (previous_version !== storage_schema_version) {
    clear_namespaced_storage(namespace);
    localStorage.setItem(schema_key, storage_schema_version);
  }

  // app偏好设置初始化
  await initPreferences({
    namespace,
    overrides: overridesPreferences,
  });

  // 启动应用并挂载
  // vue应用主要逻辑及视图
  const { bootstrap } = await import('./bootstrap');
  await bootstrap(namespace);

  // 移除并销毁loading
  unmountGlobalLoading();
}

initApplication();
