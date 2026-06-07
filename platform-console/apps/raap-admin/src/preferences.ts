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
    // 侧边栏菜单/Tab 由前端路由配置控制，避免依赖后端 sys_menu 漏配导致入口消失
    accessMode: 'frontend',
    // 默认首页
    defaultHomePath: '/business-rules',
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
  copyright: {
    companyName: 'MAGA',
    companySiteLink: '',
    date: '2026',
  },
  // Logo 配置
  logo: {
    source: '/maga-logo.svg',
    sourceDark: '/maga-logo.svg',
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
