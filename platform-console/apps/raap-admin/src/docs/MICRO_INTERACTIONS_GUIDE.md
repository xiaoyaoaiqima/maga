# 前端微交互组件 - 实战应用指南

## 📦 已创建的组件

### 1. CopyButton - 复制按钮组件

**文件**: `src/components/CopyButton.vue`

**功能**:

- ✨ 一键复制文本到剪贴板
- 🎉 复制成功动画反馈
- ⏱️ 自动重置状态
- 🎯 多种样式变体

**基础用法**:

```vue
<script setup lang="ts">
import { ref } from 'vue';
import { CopyButton } from '#/components/CopyButton.vue';

const code = ref('const hello = "world";');

function onCopied(text: string) {
  console.log('已复制:', text);
}
</script>

<template>
  <!-- 默认用法 -->
  <CopyButton :text="code" @copied="onCopied" />

  <!-- 自定义类型 -->
  <CopyButton
    :text="code"
    type="primary"
    size="middle"
    tooltip="点击复制代码"
  />

  <!-- 在代码块中使用 -->
  <pre><code>{{ code }} <CopyButton :text="code" /></code></pre>
</template>
```

---

### 2. UndoNotification - 撤销通知组件

**文件**: `src/components/UndoNotification.vue`

**功能**:

- 🔄 操作后提供撤销机会
- ⏱️ 自动消失倒计时
- ✅ 撤销成功/失败处理

**基础用法**:

```vue
<script setup lang="ts">
import { ref } from 'vue';
import { UndoNotification } from '#/components/UndoNotification.vue';

const showNotification = ref(false);
const deletedItems = ref([]);

function handleDelete(item: any) {
  // 执行删除
  deletedItems.value.push(item);

  // 显示撤销通知
  showNotification.value = true;
}

function handleUndo() {
  // 恢复删除
  const lastItem = deletedItems.value.pop();
  if (lastItem) {
    dataSource.value.push(lastItem);
  }
}

function onUndoSuccess() {
  console.log('撤销成功');
}
</script>

<template>
  <Button @click="handleDelete(item)">删除</Button>

  <!-- 撤销通知 -->
  <UndoNotification
    v-if="showNotification"
    title="已删除"
    :description="`已删除 "${item.name}"`"
    undo-text="撤销"
    :on-undo="handleUndo"
    :on-success="onUndoSuccess"
    :duration="5"
    type="warning"
  />
</template>
```

---

### 3. Toast 通知系统

**文件**: `src/utils/toast.ts`

**功能**:

- 🎨 美化的样式
- 📊 进度条显示
- 🔘 操作按钮支持
- 🎯 多种类型

**基础用法**:

```vue
<script setup lang="ts">
import {
  toast,
  showSuccess,
  showError,
  showWarning,
  showInfo,
} from '#/utils/toast';

// 方式 1: 使用 toast 实例
function handleSuccess() {
  toast.success({
    title: '操作成功',
    description: '数据已保存',
    duration: 3,
    showProgress: true,
  });
}

// 方式 2: 使用便捷方法
function handleError() {
  showError({
    title: '操作失败',
    description: '请检查网络连接后重试',
    action: {
      text: '重试',
      onClick: () => {
        console.log('重试...');
      },
      type: 'primary',
    },
  });
}

// 带操作按钮
function handleConfirm() {
  showWarning({
    title: '确认删除？',
    description: '此操作不可恢复',
    duration: 0, // 不自动关闭
    action: {
      text: '确认删除',
      type: 'danger',
      onClick: async () => {
        await deleteItem();
        showSuccess({ title: '删除成功' });
      },
    },
  });
}
</script>
```

---

## 🎯 实战应用示例

### 示例 1: 优化插件列表页

**文件**: `src/views/config/plugin/index.vue`

```vue
<script setup lang="ts">
import { ref } from 'vue';
import { EnhancedButton } from '#/components/EnhancedButton.vue';
import { SkeletonLoader } from '#/components/SkeletonLoader.vue';
import { CopyButton } from '#/components/CopyButton.vue';
import { showSuccess, toast } from '#/utils/toast';

const loading = ref(false);
const dataSource = ref([]);

// 复制插件编码
function handleCopyCode(code: string) {
  showSuccess({
    title: '复制成功',
    description: `已复制插件编码: ${code}`,
    showProgress: true,
  });
}

// 删除插件（带撤销）
async function handleDelete(plugin: Plugin) {
  try {
    await deletePluginApi(plugin.id);

    // 显示撤销通知
    toast.warning({
      title: '已删除',
      description: `插件 "${plugin.plugin_name}" 已删除`,
      duration: 5,
      action: {
        text: '撤销',
        onClick: async () => {
          await restorePlugin(plugin);
          showSuccess({ title: '已恢复' });
        },
      },
    });
  } catch (error) {
    showError({
      title: '删除失败',
      description: error.message,
      action: {
        text: '重试',
        onClick: () => handleDelete(plugin),
      },
    });
  }
}
</script>

<template>
  <div class="plugin-page">
    <!-- 筛选栏 -->
    <div class="filter-bar">
      <Input v-model:value="searchText" placeholder="搜索插件..." />
      <EnhancedButton type="primary" @click="handleAdd">
        ➕ 新建插件
      </EnhancedButton>
      <EnhancedButton @click="fetchPlugins"> 🔄 刷新 </EnhancedButton>
    </div>

    <!-- 骨架屏加载 -->
    <SkeletonLoader v-if="loading" type="table" :rows="10" />

    <!-- 数据表格 -->
    <Table v-else :data-source="dataSource">
      <template #bodyCell="{ column, record }">
        <!-- Plugin 编码列 -->
        <template v-if="column.key === 'plugin_code'">
          <Space>
            <code>{{ record.plugin_code }}</code>
            <CopyButton
              :text="record.plugin_code"
              @copied="() => handleCopyCode(record.plugin_code)"
            />
          </Space>
        </template>

        <!-- 操作列 -->
        <template v-else-if="column.key === 'action'">
          <Space>
            <EnhancedButton
              size="small"
              type="link"
              @click="handleEdit(record)"
            >
              ✏️ 编辑
            </EnhancedButton>
            <EnhancedButton
              size="small"
              danger
              type="link"
              @click="handleDelete(record)"
            >
              🗑️ 删除
            </EnhancedButton>
          </Space>
        </template>
      </template>
    </Table>
  </div>
</template>
```

---

### 示例 2: 表单提交优化

```vue
<script setup lang="ts">
import { ref } from 'vue';
import { EnhancedButton } from '#/components/EnhancedButton.vue';
import { showSuccess, showError } from '#/utils/toast';

const formRef = ref();
const isSubmitting = ref(false);

async function handleSubmit() {
  try {
    isSubmitting.value = true;

    // 表单验证
    await formRef.value.validate();

    // 提交数据
    await submitFormApi(formState);

    // 成功提示
    showSuccess({
      title: '保存成功',
      description: '插件配置已保存',
      showProgress: true,
      action: {
        text: '继续编辑',
        onClick: () => {
          console.log('继续编辑...');
        },
      },
    });

    // 关闭弹窗
    modalVisible.value = false;
  } catch (error) {
    // 错误提示
    showError({
      title: '保存失败',
      description: error.message,
      action: {
        text: '重试',
        onClick: () => handleSubmit(),
      },
    });
  } finally {
    isSubmitting.value = false;
  }
}
</script>

<template>
  <Modal title="编辑插件">
    <Form ref="formRef" :model="formState">
      <!-- 表单字段 -->
      <FormItem label="插件名称" name="plugin_name">
        <Input v-model:value="formState.plugin_name" />
      </FormItem>
    </Form>

    <template #footer>
      <EnhancedButton @click="modalVisible = false"> 取消 </EnhancedButton>
      <EnhancedButton
        type="primary"
        :debounce="1000"
        :loading="isSubmitting"
        @click="handleSubmit"
      >
        保存
      </EnhancedButton>
    </template>
  </Modal>
</template>
```

---

### 示例 3: 批量操作优化

```vue
<script setup lang="ts">
import { ref } from 'vue';
import { EnhancedButton } from '#/components/EnhancedButton.vue';
import { toast } from '#/utils/toast';

const selectedRows = ref([]);
const isBatchDeleting = ref(false);

async function handleBatchDelete() {
  if (selectedRows.value.length === 0) {
    showInfo({
      title: '请先选择要删除的项',
      duration: 2,
    });
    return;
  }

  try {
    isBatchDeleting.value = true;

    const deletedItems = [...selectedRows.value];
    await batchDeleteApi(selectedRows.value);

    // 显示撤销通知
    toast.success({
      title: '批量删除成功',
      description: `已删除 ${deletedItems.length} 个插件`,
      duration: 5,
      action: {
        text: '撤销全部',
        onClick: async () => {
          await restoreBatchApi(deletedItems);
          selectedRows.value = deletedItems;
          showSuccess({ title: '已恢复' });
        },
      },
    });

    selectedRows.value = [];
  } catch (error) {
    showError({
      title: '批量删除失败',
      description: error.message,
    });
  } finally {
    isBatchDeleting.value = false;
  }
}
</script>

<template>
  <div class="batch-actions">
    <span>已选择 {{ selectedRows.length }} 项</span>
    <EnhancedButton
      danger
      :loading="isBatchDeleting"
      :debounce="1000"
      @click="handleBatchDelete"
    >
      🗑️ 批量删除
    </EnhancedButton>
  </div>
</template>
```

---

### 示例 4: 代码复制功能

```vue
<script setup lang="ts">
import { ref } from 'vue';
import { CopyButton } from '#/components/CopyButton.vue';
import { MonacoEditor } from '#/components/MonacoEditor.vue';

const code = ref(`function hello() {
  console.log("Hello, World!");
}`);

function onCodeCopied(copiedCode: string) {
  console.log('代码已复制:', copiedCode);
}
</script>

<template>
  <div class="code-block">
    <div class="code-header">
      <span>Plugin Template</span>
      <CopyButton
        :text="code"
        type="primary"
        size="small"
        tooltip="复制代码"
        @copied="onCodeCopied"
      />
    </div>
    <MonacoEditor v-model="code" language="javascript" height="300px" />
  </div>
</template>

<style scoped>
.code-block {
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  overflow: hidden;
}

.code-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: hsl(var(--muted) / 0.3);
  border-bottom: 1px solid hsl(var(--border));
}
</style>
```

---

## 🎨 高级用法

### 1. 组合多个微交互

```vue
<script setup lang="ts">
import { ref } from 'vue';
import { EnhancedButton } from '#/components/EnhancedButton.vue';
import { CopyButton } from '#/components/CopyButton.vue';
import { showSuccess } from '#/utils/toast';

function handleCopyAndNotify(text: string) {
  // CopyButton 会自动处理复制
  // 这里只需要显示额外的通知
  showSuccess({
    title: '复制成功',
    description: `已复制到剪贴板: ${text.slice(0, 50)}...`,
    showProgress: true,
  });
}
</script>

<template>
  <div class="action-bar">
    <CopyButton :text="shareableLink" @copied="handleCopyAndNotify" />
    <EnhancedButton type="primary" @click="handleShare">
      分享链接
    </EnhancedButton>
  </div>
</template>
```

### 2. 异步操作反馈

```vue
<script setup lang="ts">
import { ref } from 'vue';
import { EnhancedButton } from '#/components/EnhancedButton.vue';
import { showSuccess, showError, toast } from '#/utils/toast';

const isPublishing = ref(false);

async function handlePublish() {
  try {
    isPublishing.value = true;

    // 显示处理中通知
    toast.info({
      title: '正在发布...',
      description: '请稍候',
      duration: 0,
    });

    await publishApi();

    // 关闭处理中通知
    toast.closeAll();

    // 显示成功通知
    showSuccess({
      title: '发布成功',
      description: '插件已上线',
      showProgress: true,
      action: {
        text: '查看',
        onClick: () => {
          // 跳转到详情页
          router.push(`/plugins/${pluginId}`);
        },
      },
    });
  } catch (error) {
    toast.closeAll();
    showError({
      title: '发布失败',
      description: error.message,
      action: {
        text: '重试',
        onClick: () => handlePublish(),
      },
    });
  } finally {
    isPublishing.value = false;
  }
}
</script>

<template>
  <EnhancedButton
    type="primary"
    :loading="isPublishing"
    :debounce="1000"
    @click="handlePublish"
  >
    🚀 发布
  </EnhancedButton>
</template>
```

---

## 📊 组件对比

### 传统方式 vs 优化后

| 场景 | 传统方式 | 优化后 |
| --- | --- | --- |
| **按钮** | `<Button>` | `<EnhancedButton>` - 波纹 + 缩放 + 防抖 |
| **加载** | `<Spin>` | `<SkeletonLoader>` - 多种样式 + 流畅动画 |
| **复制** | 手动实现 navigator.clipboard | `<CopyButton>` - 自动反馈 + 图标切换 |
| **通知** | `message.success()` | `toast.success()` - 美化样式 + 进度条 + 操作按钮 |
| **撤销** | 需手动实现 | `<UndoNotification>` - 自动倒计时 + 撤销处理 |

---

## 🔧 最佳实践

### 1. 按钮使用

```vue
<!-- ✅ 推荐：重要操作使用防抖 -->
<EnhancedButton type="primary" :debounce="1000" @click="handleSubmit">
  提交
</EnhancedButton>

<!-- ❌ 避免：频繁操作使用防抖 -->
<EnhancedButton :debounce="1000" @click="handleRefresh">
  刷新
</EnhancedButton>
```

### 2. Toast 使用

```vue
<!-- ✅ 推荐：重要操作带操作按钮 -->
showSuccess({ title: '保存成功', action: { text: '查看', onClick: () =>
navigateToDetail(), }, })

<!-- ✅ 推荐：长时间操作显示进度条 -->
showInfo({ title: '处理中...', showProgress: true, duration: 10, })

<!-- ❌ 避免：简单提示使用复杂配置 -->
showSuccess({ title: '成功', showProgress: true, action: { ... } })
```

### 3. 复制使用

```vue
<!-- ✅ 推荐：代码块中使用 -->
<pre><code>{{ code }} <CopyButton :text="code" /></code></pre>

<!-- ✅ 推荐：文本旁使用 -->
<Space>
  <span>{{ longText }}</span>
  <CopyButton :text="longText" size="small" />
</Space>

<!-- ❌ 避免：过短文本使用复制按钮（< 10 字符） -->
```

---

## 🚀 性能优化

1. **按需导入**

   ```typescript
   // ✅ 推荐：按需导入
   import { EnhancedButton } from '#/components/EnhancedButton.vue';

   // ❌ 避免：全局导入所有组件
   import * as Components from '#/components';
   ```

2. **防抖设置**

   ```typescript
   // 快速操作：无需防抖或短防抖
   <EnhancedButton :debounce="0" @click="handleToggle" />

   // 慢速操作：长防抖
   <EnhancedButton :debounce="2000" @click="handleSubmit" />
   ```

3. **Toast 清理**
   ```typescript
   // 页面卸载时清理所有通知
   onUnmounted(() => {
     toast.closeAll();
   });
   ```

---

**生成时间**: 2025-01-29 **版本**: v1.0.0
