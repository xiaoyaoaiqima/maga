import { defineBuildConfig } from 'unbuild';

export default defineBuildConfig({
  clean: true,
  declaration: true,
  entries: ['src/index'],
  externals: [
    '@pnpm/workspace.read-manifest',
    '@vben/node-utils',
    '@vitejs/plugin-vue',
    '@vitejs/plugin-vue-jsx',
    'dotenv',
    'rollup',
    'rollup-plugin-visualizer',
    'sass',
    'vite',
    'vite-plugin-compression',
    'vite-plugin-dts',
    'vite-plugin-html',
    'vite-plugin-lazy-import',
  ],
});
