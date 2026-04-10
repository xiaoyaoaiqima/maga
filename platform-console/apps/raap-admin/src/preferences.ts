import { defineOverridesPreferences } from '@vben/preferences';

/**
 * @description 项目配置文件
 * 只需要覆盖项目中的一部分配置，不需要的配置不用覆盖，会自动使用默认配置
 * !!! 更改配置后请清空缓存，否则可能不生效
 */
export const overridesPreferences = defineOverridesPreferences({
  // overrides
  app: {
    name: import.meta.env.VITE_APP_TITLE,
    // 启用混合模式：自动合并前端静态路由和后端动态菜单，无需手动切换模式
    accessMode: 'backend',
    // 默认首页
    defaultHomePath: '/dashboard/ai-dashboard',
    // 默认开启水印
    watermark: true,
  },
  // 导航配置
  navigation: {
    split: false, // 禁用菜单分割，防止核心路由（如个人中心）因找不到子菜单而导致侧边栏自动隐藏
  },
  // 侧边栏配置
  sidebar: {
    enable: true, // 确保侧边栏始终启用
    hidden: false, // 确保侧边栏不隐藏
  },
  // Logo 配置
  logo: {
    source: '/logo.png', // 亮色主题 logo (48x48)
    // sourceDark: '/logo.png', // 暗色主题 logo（当前使用相同 logo）
  },
  // 功能配置
  widget: {
    languageToggle: false, // 隐藏语言切换按钮
    timezone: false, // 隐藏时区切换按钮
  },
  // 主题配置
  theme: {
    mode: 'dark',
  },
});
