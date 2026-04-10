#!/bin/bash
# 批量添加 logger 导入的脚本
# 用法：在 apps/raap-admin 目录下运行

find src/views -type f \( -name "*.vue" -o -name "*.ts" \) -exec grep -l "console\." {} \; | while read file; do
  # 检查是否已有 logger 导入
  if ! grep -q "import.*logger.*from.*#/utils/logger" "$file"; then
    # 查找第一个 vue 或 ts 导入行，在其后添加 logger 导入
    if grep -q "^import.*from 'vue'" "$file"; then
      sed -i.bak "/^import.*from 'vue'/a\\
import { logger } from '#/utils/logger';
" "$file" && echo "✓ Added logger to $file"
    elif grep -q "^import.*from '@/" "$file"; then
      sed -i.bak "0,/^import.*from@\//s//import { logger } from '#\/utils\/logger';\\n&/" "$file" && echo "✓ Added logger to $file"
    fi
  fi
done

# 清理备份文件
find src/views -name "*.bak" -delete

echo "✅ Done adding logger imports"
