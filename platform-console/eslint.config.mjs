// @ts-check

import { defineConfig } from '@vben/eslint-config';

export default defineConfig([
  {
    // 忽略独立演示项目
    ignores: ['knowledge_graph/**'],
  },
  {
    rules: {
      'vue/html-closing-bracket-newline': 'off',
      // 与 Prettier（十六进制字面量会被格式化为小写）存在冲突，容易造成 --fix 循环
      'unicorn/number-literal-case': 'off',
    },
  },
]);
