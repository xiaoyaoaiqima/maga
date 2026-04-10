# MAGA Console 前端动画优化 - 使用指南

本文档介绍如何使用新增的动画组件和样式。

## 📦 已添加的组件

### 1. EnhancedButton - 增强按钮组件

**文件位置**: `src/components/EnhancedButton.vue`

**特性**:

- ✨ 点击波纹效果
- 📏 按钮缩放反馈
- ⏱️ 可选防抖功能

**基础用法**:

```vue
<script setup lang="ts">
import { EnhancedButton } from '#/components/EnhancedButton.vue';

function handleClick() {
  console.log('按钮被点击');
}
</script>

<template>
  <!-- 默认启用波纹和缩放 -->
  <EnhancedButton type="primary" @click="handleClick"> 保存 </EnhancedButton>

  <!-- 仅波纹效果 -->
  <EnhancedButton :scale="false" @click="handleClick"> 仅波纹 </EnhancedButton>

  <!-- 带防抖（500ms） -->
  <EnhancedButton :debounce="500" type="primary" @click="handleClick">
    提交（防抖）
  </EnhancedButton>
</template>
```

**快捷使用 - 全局样式类**:

```vue
<!-- 任何 Ant Design 按钮都可以添加 `btn-enhanced` 类 -->
<template>
  <Button class="btn-enhanced" @click="handleClick"> 点击我 </Button>
</template>

<style scoped>
/* 通过 script 标记点击状态 */
const isClicked = ref(false);
function handleClick() {
  isClicked.value = true;
  setTimeout(() => isClicked.value = false, 600);
}
</style>
```

---

### 2. SkeletonLoader - 骨架屏组件

**文件位置**: `src/components/SkeletonLoader.vue`

**特性**:

- 🎨 多种预设样式（card/list/table/form）
- ⚡ 流畅的 shimmer 动画
- 🎯 可自定义尺寸

**基础用法**:

```vue
<script setup lang="ts">
import { SkeletonLoader } from '#/components/SkeletonLoader.vue';

const loading = ref(true);
</script>

<template>
  <!-- 卡片骨架 -->
  <SkeletonLoader v-if="loading" type="card" :rows="3" />

  <!-- 列表骨架 -->
  <SkeletonLoader v-if="loading" type="list" :rows="5" :avatar="true" />

  <!-- 表格骨架 -->
  <SkeletonLoader v-if="loading" type="table" :rows="10" />

  <!-- 表单骨架 -->
  <SkeletonLoader v-if="loading" type="form" :rows="4" />

  <!-- 自定义尺寸 -->
  <SkeletonLoader v-if="loading" type="custom" :width="200" :height="100" />
</template>
```

**实际应用示例**:

```vue
<!-- 插件列表页 -->
<template>
  <div>
    <!-- 加载中 -->
    <SkeletonLoader
      v-if="loading"
      type="list"
      :rows="pagination.pageSize"
      :avatar="false"
    />

    <!-- 数据展示 -->
    <Transition name="fade" mode="out-in">
      <Table v-else :data-source="dataSource" :columns="columns" />
    </Transition>
  </div>
</template>

<style scoped>
/* 添加淡入淡出过渡 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
```

---

### 3. AnimatedList - 动画列表组件

**文件位置**: `src/components/AnimatedList.vue`

**特性**:

- 🎬 Stagger 渐入动画（错落有致）
- 🎯 悬停效果
- 🔄 自动监听数据变化

**基础用法**:

```vue
<script setup lang="ts">
import { ref } from 'vue';
import { AnimatedList } from '#/components/AnimatedList.vue';

interface Item {
  id: number;
  name: string;
}

const items = ref<Item[]>([
  { id: 1, name: '项目 1' },
  { id: 2, name: '项目 2' },
  { id: 3, name: '项目 3' },
]);

function addItem() {
  items.value.push({
    id: Date.now(),
    name: `项目 ${items.value.length + 1}`,
  });
}
</script>

<template>
  <div>
    <EnhancedButton type="primary" @click="addItem"> 添加项目 </EnhancedButton>

    <!-- 使用 AnimatedList -->
    <AnimatedList
      :items="items"
      item-key="id"
      :stagger="true"
      :stagger-delay="100"
      :hoverable="true"
    >
      <template #item="{ item, index }">
        <div class="card">
          <h3>{{ item.name }}</h3>
          <p>索引: {{ index }}</p>
        </div>
      </template>
    </AnimatedList>
  </div>
</template>

<style scoped>
.card {
  padding: 16px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}
</style>
```

---

## 🎨 全局动画样式

**文件位置**: `src/styles/animations.css`

所有动画样式已自动引入，可直接使用类名：

### 列表项动画

```vue
<template>
  <TransitionGroup name="list" tag="div">
    <div v-for="item in items" :key="item.id" class="list-item-staggered">
      {{ item.name }}
    </div>
  </TransitionGroup>
</template>

<style scoped>
/* 添加 stagger 延迟 */
.list-item-staggered:nth-child(1) {
  --stagger-delay: 0ms;
}
.list-item-staggered:nth-child(2) {
  --stagger-delay: 100ms;
}
.list-item-staggered:nth-child(3) {
  --stagger-delay: 200ms;
}
</style>
```

### 表单验证 Shake 动画

```vue
<template>
  <Transition name="shake">
    <div v-if="errors.name" class="error-message">
      {{ errors.name }}
    </div>
  </Transition>
</template>

<style scoped>
.error-message {
  color: hsl(var(--destructive));
  font-size: 12px;
  margin-top: 4px;
}
</style>
```

### 页面过渡动画

```vue
<template>
  <router-view v-slot="{ Component }">
    <Transition name="page-fade" mode="out-in">
      <component :is="Component" />
    </Transition>
  </router-view>
</template>
```

---

## 🔧 在现有页面中应用

### 示例 1: 优化插件列表页

**文件**: `src/views/config/plugin/index.vue`

```vue
<script setup lang="ts">
import { SkeletonLoader } from '#/components/SkeletonLoader.vue';
import { AnimatedList } from '#/components/AnimatedList.vue';
import { EnhancedButton } from '#/components/EnhancedButton.vue';
</script>

<template>
  <div class="plugin-page">
    <!-- 筛选头部 -->
    <div class="filter-header">
      <Input v-model:value="searchText" placeholder="搜索插件..." />
      <EnhancedButton type="primary" @click="handleCreate">
        <PlusOutlined /> 新建插件
      </EnhancedButton>
    </div>

    <!-- 加载状态 -->
    <SkeletonLoader v-if="loading" type="list" :rows="pagination.pageSize" />

    <!-- 数据列表 -->
    <AnimatedList v-else :items="dataSource" item-key="id" :hoverable="true">
      <template #item="{ item }">
        <Card class="plugin-card">
          <div class="plugin-info">
            <h3>{{ item.plugin_name }}</h3>
            <p>{{ item.plugin_code }}</p>
          </div>
          <div class="plugin-actions">
            <EnhancedButton size="small" @click="handleEdit(item)">
              编辑
            </EnhancedButton>
            <EnhancedButton danger size="small" @click="handleDelete(item)">
              删除
            </EnhancedButton>
          </div>
        </Card>
      </template>
    </AnimatedList>
  </div>
</template>

<style scoped>
.plugin-card {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.plugin-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 24px -8px rgba(0, 0, 0, 0.15);
}
</style>
```

### 示例 2: 优化表单验证

**文件**: `src/views/config/plugin/components/PluginFormModal.vue`

```vue
<template>
  <Modal v-model:open="visible" title="插件配置">
    <Form ref="formRef" :model="formState">
      <FormItem label="插件名称" name="plugin_name">
        <Input v-model:value="formState.plugin_name" />
      </FormItem>

      <!-- 错误提示带 shake 动画 -->
      <Transition name="shake">
        <div v-if="errors.plugin_name" class="error-message">
          ❌ {{ errors.plugin_name }}
        </div>
      </Transition>

      <FormItem label="插件代码" name="plugin_code">
        <Input v-model:value="formState.plugin_code" />
      </FormItem>
    </Form>

    <template #footer>
      <EnhancedButton @click="visible = false">取消</EnhancedButton>
      <EnhancedButton type="primary" :debounce="1000" @click="handleSubmit">
        保存
      </EnhancedButton>
    </template>
  </Modal>
</template>

<style scoped>
.error-message {
  color: hsl(var(--destructive));
  font-size: 12px;
  margin-top: -12px;
  margin-bottom: 12px;
  padding-left: 2px;
}
</style>
```

### 示例 3: 优化表格加载

**文件**: `src/views/system/menu/index.vue`

```vue
<template>
  <div>
    <!-- 筛选栏 -->
    <div class="filter-bar">...</div>

    <!-- 加载状态 -->
    <div v-if="loading" class="table-skeleton">
      <SkeletonLoader type="table" :rows="10" />
    </div>

    <!-- 表格 -->
    <Table
      v-else
      :columns="columns"
      :data-source="dataSource"
      :scroll="{ x: 1400 }"
      :pagination="pagination"
    >
      <!-- 表格内容 -->
    </Table>
  </div>
</template>

<style scoped>
.table-skeleton {
  padding: 20px;
  background: hsl(var(--card));
  border-radius: 8px;
}
</style>
```

---

## 📊 动画效果对比

### Before ❌

- 按钮点击无反馈
- 列表加载瞬间出现
- 表单验证突兀
- 加载状态单调

### After ✅

- 按钮点击有波纹 + 缩放
- 列表项渐入动画
- 表单验证平滑抖动
- 加载状态流畅 shimmer

---

## 🎯 性能优化建议

1. **合理使用动画**
   - 仅在重要交互上使用动画
   - 避免过多元素同时动画
   - 移动端减少动画复杂度

2. **使用 CSS 动画而非 JS**
   - CSS 动画由浏览器优化
   - 不阻塞主线程
   - 自动硬件加速

3. **延迟加载非关键动画**

   ```vue
   <script setup>
   import { defineAsyncComponent } from 'vue';

   const AnimatedList = defineAsyncComponent(
     () => import('#/components/AnimatedList.vue'),
   );
   </script>
   ```

4. **减少重排重绘**
   - 使用 `transform` 和 `opacity`
   - 避免 `width`, `height`, `top`, `left`
   - 使用 `will-change` 提示浏览器

---

## 📝 API 参考

### EnhancedButton Props

| 属性     | 类型    | 默认值 | 说明             |
| -------- | ------- | ------ | ---------------- |
| ripple   | boolean | true   | 是否启用波纹效果 |
| scale    | boolean | true   | 是否启用缩放效果 |
| debounce | number  | 0      | 防抖延迟（毫秒） |

### SkeletonLoader Props

| 属性 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| type | 'card' \| 'list' \| 'table' \| 'form' \| 'custom' | 'card' | 骨架屏类型 |
| rows | number | 3 | 行数 |
| avatar | boolean | false | 是否显示头像 |
| title | boolean | true | 是否显示标题 |
| width | string \| number | '100%' | 宽度 |
| height | string \| number | 'auto' | 高度 |

### AnimatedList Props

| 属性         | 类型    | 默认值 | 说明                  |
| ------------ | ------- | ------ | --------------------- |
| items        | any[]   | []     | 数据源                |
| itemKey      | string  | -      | 唯一键                |
| stagger      | boolean | true   | 是否启用 stagger 动画 |
| staggerDelay | number  | 100    | stagger 延迟（毫秒）  |
| hoverable    | boolean | true   | 是否启用悬停效果      |

---

## 🚀 下一步计划

- [ ] 为不同页面定制主题动画
- [ ] 添加微交互反馈（复制成功、操作成功等）
- [ ] 优化页面过渡动画
- [ ] 添加 3D 动画效果（Three.js）

---

**生成时间**: 2025-01-29 **版本**: v1.0.0
