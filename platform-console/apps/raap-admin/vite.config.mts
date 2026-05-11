import type { UserConfigExport } from 'vite';

import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { defineConfig } from '@vben/vite-config';

const project_dir = dirname(fileURLToPath(import.meta.url));

/**
 * 简单读取环境变量
 * 加载顺序: .env -> .env.local -> .env.{mode} -> .env.{mode}.local
 * 后者覆盖前者
 */
function loadProxyTarget(mode: string): string {
  const envProxyTarget = process.env.VITE_PROXY_TARGET?.trim();
  // make dev 会注入本地后端地址，命令行环境变量应优先于 .env 文件。
  if (envProxyTarget) {
    return envProxyTarget;
  }

  const cwd = process.cwd();
  const files = ['.env', '.env.local', `.env.${mode}`, `.env.${mode}.local`];
  let proxyTarget = 'http://localhost:5100'; // 默认值

  for (const file of files) {
    const filePath = join(cwd, file);
    if (existsSync(filePath)) {
      const content = readFileSync(filePath, 'utf8');
      const match = content.match(/^VITE_PROXY_TARGET=(.+)$/m);
      if (match && match[1]) {
        proxyTarget = match[1].trim();
      }
    }
  }
  return proxyTarget;
}

const vite_config: UserConfigExport = defineConfig(async () => {
  return {
    application: {},
    vite: {
      build: {
        rollupOptions: {
          output: {
            manualChunks(id: string) {
              // Vue 生态
              if (
                id.includes('node_modules/vue/') ||
                id.includes('node_modules/@vue/') ||
                id.includes('node_modules/pinia/') ||
                id.includes('node_modules/vue-router/')
              ) {
                return 'vue-vendor';
              }
              // Ant Design Vue
              if (
                id.includes('node_modules/ant-design-vue/') ||
                id.includes('node_modules/@ant-design/')
              ) {
                return 'antd-vendor';
              }
              // ECharts
              if (id.includes('node_modules/echarts/')) {
                return 'echarts';
              }
              if (id.includes('node_modules/echarts-wordcloud/')) {
                return 'echarts-wordcloud';
              }
              // 图可视化 - 按库拆分
              if (id.includes('node_modules/@antv/g6/')) {
                return 'g6';
              }
              if (id.includes('node_modules/vis-network/')) {
                return 'vis-network';
              }
              if (id.includes('node_modules/3d-force-graph/')) {
                return '3d-force-graph';
              }
              if (id.includes('node_modules/three/')) {
                return 'three';
              }
              if (id.includes('node_modules/three-spritetext/')) {
                return 'three-spritetext';
              }
              // VXE Table
              if (id.includes('node_modules/vxe-table/')) {
                return 'vxe-table';
              }
              // Vben 框架
              if (id.includes('node_modules/@vben/')) {
                return 'vben';
              }
              // 工具库
              if (
                id.includes('node_modules/xlsx/') ||
                id.includes('node_modules/gsap/') ||
                id.includes('node_modules/diff/') ||
                id.includes('node_modules/sortablejs/')
              ) {
                return 'utils';
              }
            },
          },
        },
      },
      optimizeDeps: {
        include: ['secure-ls', 'three', 'three-spritetext', '3d-force-graph'],
        // 强制 3d-force-graph 使用预构建，避免多个 Three.js 实例
        exclude: [],
        // 禁用 esbuild 对 three 的预构建，使用 rollup 预构建
        esbuildOptions: {
          target: 'es2020',
        },
      },
      resolve: {
        alias: [
          {
            find: /external\/vscode-uri\/lib\/esm\/index\.js$/,
            replacement: 'vscode-uri',
          },
          // 确保 three 只有一个实例
          {
            find: /^three$/,
            replacement: 'three',
          },
        ],
      },
      worker: {
        format: 'es',
      },
      server: {
        port: 3100,
        allowedHosts: ['raap.realshark.com', 'localhost', '.realshark.com'],
        proxy: {
          '/api': {
            changeOrigin: true,
            target: loadProxyTarget('development'),
            ws: true,
          },
        },
      },
    },
  };
});

export default vite_config;
