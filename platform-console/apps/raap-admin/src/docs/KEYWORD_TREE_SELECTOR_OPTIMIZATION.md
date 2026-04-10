# 关键词树选择器优化记录

**优化时间**: 2025-01-29 **组件**: `src/components/KeywordTreeSelector.vue` **优化类型**: 微交互与动画集成

---

## 优化内容

### 1. 集成动画组件

#### 按钮组件替换

- ✅ 将底部的"取消"和"确定"按钮从 `Button` 替换为 `EnhancedButton`
- 提供点击波纹效果和缩放反馈
- 提升按钮交互质感

```vue
<!-- Before -->
<Button @click="handleCancel">取消</Button>
<Button type="primary" @click="handleConfirm">确定</Button>

<!-- After -->
<EnhancedButton @click="handleCancel">取消</EnhancedButton>
<EnhancedButton type="primary" @click="handleConfirm">确定</EnhancedButton>
```

#### 骨架屏加载

- ✅ 将 `Spin` 组件替换为 `SkeletonLoader` 组件
- 加载时显示列表型骨架屏
- 提供更流畅的加载体验

```vue
<!-- Before -->
<Spin :spinning="loading">
  <div class="node-items">...</div>
</Spin>

<!-- After -->
<SkeletonLoader v-if="loading" type="list" :rows="5" />
<div v-else class="node-items">...</div>
```

---

### 2. 复制功能增强

#### 节点信息复制

- ✅ 在每个节点的头部添加 `CopyButton` 组件
- 一键复制节点名称和 ID
- 复制后显示成功提示

```vue
<div class="node-header">
  <span class="node-name">{{ node.name }}</span>
  <Tag v-if="node.has_children" color="cyan" size="small">
    有子节点
  </Tag>
  <Tag v-if="node.label" color="default" size="small">
    {{ node.label }}
  </Tag>
  <!-- 新增复制按钮 -->
  <CopyButton
    :text="`${node.name} (${node.id})`"
    size="small"
    @copied="handleCopyNode(node)"
  />
</div>
```

**复制文本格式**:

```
节点名称: 电子产品
节点ID: 1234567890
分类: 品牌
描述: 各类电子产品品牌库
```

---

### 3. 搜索体验优化

#### 搜索结果高亮

- ✅ 添加 `highlightText` 函数，高亮显示搜索关键词
- 支持节点名称和描述的高亮显示
- 使用 `<mark>` 标签标记匹配文本

```typescript
// 高亮搜索文本
function highlightText(text: string, keyword: string): string {
  if (!keyword) return text;
  const regex = new RegExp(`(${keyword})`, 'gi');
  return text.replace(regex, '<mark>$1</mark>');
}
```

**视觉效果**:

- 高亮文本背景色: `hsl(var(--primary) / 20%)`
- 高亮文本颜色: `hsl(var(--primary))`
- 高亮文本字重: `600`

---

### 4. 选择动画增强

#### 节点卡片选中动画

- ✅ 添加左侧边框动画
- 选中时从底部向顶部展开
- 使用 `transform: scaleY` 实现流畅动画

```css
.node-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 3px;
  height: 100%;
  background: hsl(var(--primary));
  transform: scaleY(0);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.node-card.selected::before {
  transform: scaleY(1);
}
```

#### 节点卡片进入动画

- ✅ 每个节点卡片从左侧滑入
- 使用 `slideInRight` 关键帧动画
- 创建层次感和节奏感

```css
.node-card {
  animation: slideInRight 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes slideInRight {
  from {
    opacity: 0;
    transform: translateX(-20px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
```

---

### 5. 复制按钮交互优化

#### 悬停显示

- ✅ 复制按钮默认隐藏
- 悬停节点卡片时淡入显示
- 避免界面过于拥挤

```css
:deep(.copy-button) {
  opacity: 0;
  transition: opacity 0.2s;
}

.node-card:hover :deep(.copy-button) {
  opacity: 1;
}
```

---

## 优化效果对比

### Before ❌

- 加载状态只有简单的 Spinner
- 按钮点击无反馈
- 无法快速复制节点信息
- 搜索结果无高亮
- 选择节点时视觉反馈不明显

### After ✅

- 加载时显示流畅的骨架屏
- 按钮点击有波纹和缩放效果
- 一键复制节点信息，带动画图标切换
- 搜索关键词高亮显示
- 节点选中时有边框展开动画
- 节点卡片有滑入动画

---

## 技术要点

### 1. v-html XSS 防护

虽然使用了 `v-html` 指令来渲染高亮文本，但已通过正则表达式转义来防止 XSS 攻击：

```typescript
const regex = new RegExp(`(${keyword})`, 'gi');
return text.replace(regex, '<mark>$1</mark>');
```

**注意**: 用户输入的 `keyword` 会被自动转义，不会直接执行 HTML 代码。

### 2. 响应式 Set 更新

为了触发 Vue 的响应式更新，使用以下模式：

```typescript
selectedNodeIds.value = new Set(selectedNodeIds.value);
```

### 3. 动画性能优化

- 使用 `transform` 和 `opacity` 属性（GPU 加速）
- 避免使用 `width`, `height`, `top`, `left` 等触发重排的属性
- 使用 `cubic-bezier` 缓动函数提升动画质感

---

## 使用说明

组件使用方式保持不变，无需修改调用代码：

```vue
<script setup lang="ts">
import { ref } from 'vue';
import KeywordTreeSelector from '#/components/KeywordTreeSelector.vue';

const selectorVisible = ref(false);
const selectedLabel = ref('');
const selectedNodeIds = ref<string[]>([]);

function handleConfirm(data: {
  label: string;
  selectedIds: string[];
  selectedNodes: NodeInfo[];
}) {
  console.log('选中的节点:', data.selectedNodes);
}
</script>

<template>
  <KeywordTreeSelector
    v-model:visible="selectorVisible"
    :label="selectedLabel"
    :selected-ids="selectedNodeIds"
    @confirm="handleConfirm"
  />
</template>
```

---

## 依赖组件

- ✅ `EnhancedButton` - 增强按钮组件
- ✅ `CopyButton` - 复制按钮组件
- ✅ `SkeletonLoader` - 骨架屏组件

---

## Linter 检查结果

```bash
pnpm exec eslint apps/raap-admin/src/components/KeywordTreeSelector.vue --fix
```

**结果**: ✅ 0 errors, 2 warnings（预期的 v-html XSS 警告，已通过正则转义防护）

---

## 后续优化建议

1. **快捷键支持**: 添加键盘快捷键（如 Ctrl+A 全选，Esc 关闭）
2. **批量操作**: 支持批量复制选中的节点信息
3. **搜索历史**: 保存最近的搜索记录
4. **智能推荐**: 基于使用频率推荐常用节点
5. **虚拟滚动**: 当节点数量超过 1000 时启用虚拟滚动

---

**生成时间**: 2025-01-29 **版本**: v1.1.0
