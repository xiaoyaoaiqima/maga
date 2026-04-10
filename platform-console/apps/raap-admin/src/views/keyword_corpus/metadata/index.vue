<script setup lang="ts">
import type { MetadataApi } from '#/api/core/graph-corpus';

import { computed, onMounted, ref, watch } from 'vue';

import { Button, Card, Label, Separator, Textarea } from '@vben-core/shadcn-ui';

import {
  DeleteOutlined,
  DownOutlined,
  EditOutlined,
  PlusOutlined,
  SearchOutlined,
  UpOutlined,
} from '@ant-design/icons-vue';
import {
  Empty,
  Input,
  message,
  Modal,
  Popconfirm,
  Space,
  Spin,
} from 'ant-design-vue';

import {
  createMetadataItemApi,
  deleteMetadataItemApi,
  generateCodeApi,
  getMetadataTreeApi,
  updateMetadataItemApi,
} from '#/api/core/graph-corpus';

interface TreeNode extends MetadataApi.MetadataTreeNode {
  key: string;
  level?: number;
  category_type?: 'group' | 'item';
}

// 当前是否为编辑模式
const isEditMode = computed(() => !!formData.value.id);

// AI 生成编码状态
const isGeneratingCode = ref(false);

// 状态
const loading = ref(false);
const searchQuery = ref('');
const expandedItems = ref<Set<string>>(new Set());
const lastUpdateTime = ref('');

// 租户
const tenantCode = ref('default');

// 树形数据（合并后的统一标签树）
const treeData = ref<TreeNode[]>([]);

// 统计信息：总分组数和总标签数
const statsInfo = computed(() => {
  let groupCount = 0;
  let tagCount = 0;

  const traverse = (nodes: TreeNode[]) => {
    for (const node of nodes) {
      if (node.category_type === 'group') {
        groupCount++;
      } else {
        tagCount++;
      }
      if (node.children && node.children.length > 0) {
        traverse(node.children as TreeNode[]);
      }
    }
  };

  traverse(treeData.value);
  return { groupCount, tagCount };
});

// 弹窗
const modalVisible = ref(false);
const modalTitle = ref('');
const modalLoading = ref(false);
const formData = ref<{
  code: string;
  description: string;
  id?: string;
  item_type: string;
  name: string;
  parent_id?: string;
  sort_order: number;
}>({
  item_type: '',
  name: '',
  code: '',
  description: '',
  sort_order: 0,
});

// 计算属性：扁平化所有节点
const flatItems = computed(() => {
  const tree = treeData.value;
  const query = searchQuery.value.toLowerCase().trim();

  const flatten = (nodes: TreeNode[], level = 0): TreeNode[] => {
    const result: TreeNode[] = [];
    for (const node of nodes) {
      // 搜索过滤
      if (query && !node.name.toLowerCase().includes(query)) {
        const hasMatchingChild =
          node.children &&
          flatten(node.children as TreeNode[], level + 1).length > 0;
        if (!hasMatchingChild) continue;
      }

      result.push({ ...node, level });
      // 搜索时显示所有子节点，非搜索时只显示已展开节点的子节点
      if (
        node.children &&
        node.children.length > 0 &&
        (query || expandedItems.value.has(node.id))
      ) {
        result.push(...flatten(node.children as TreeNode[], level + 1));
      }
    }
    return result;
  };

  return flatten(tree);
});

// 获取统一的标签树
async function fetchMergedTree() {
  if (!tenantCode.value) return;
  loading.value = true;
  try {
    const res = await getMetadataTreeApi(tenantCode.value);
    treeData.value = (res || []).map((item) => ({
      ...item,
      key: item.id,
      // tag 类型的是子项，其他都是分组
      category_type: item.item_type === 'tag' ? 'item' : 'group',
    }));
    // 更新时间
    lastUpdateTime.value = new Date().toLocaleString('zh-CN', {
      hour12: false,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch (error) {
    logger.error('获取统一标签树失败:', error);
    treeData.value = [];
  } finally {
    loading.value = false;
  }
}

// 刷新数据
function refreshData() {
  fetchMergedTree();
}

// 展开/收起
function toggleExpand(id: string) {
  if (expandedItems.value.has(id)) {
    expandedItems.value.delete(id);
  } else {
    expandedItems.value.add(id);
  }
}

// 判断是否有子节点
function hasChildren(item: TreeNode): boolean {
  return !!(item.children && item.children.length > 0);
}

// ==================== 新增/编辑逻辑 ====================

// 新增分组
function openNewGroupModal() {
  modalTitle.value = '新建标签组';
  formData.value = {
    item_type: '',
    name: '',
    code: '',
    description: '',
    sort_order: 0,
    parent_id: undefined,
  };
  modalVisible.value = true;
}

// 新增标签（在分组下）
function openNewTagModal(parentId: string, parentName: string) {
  modalTitle.value = `在"${parentName}"下新建标签`;
  formData.value = {
    item_type: 'tag',
    name: '',
    code: '',
    description: '',
    sort_order: 0,
    parent_id: parentId,
  };
  modalVisible.value = true;
}

// 打开编辑弹窗
function openEditModal(node: TreeNode) {
  modalTitle.value = `编辑: ${node.name}`;
  formData.value = {
    id: node.id,
    item_type: node.item_type,
    name: node.name,
    code: node.code || '',
    description: node.description || '',
    sort_order: node.sort_order || 0,
  };
  modalVisible.value = true;
}

// 提交表单
async function handleSubmit() {
  if (!formData.value.name.trim()) {
    message.warning('请输入名称');
    return;
  }

  modalLoading.value = true;
  try {
    if (formData.value.id) {
      await updateMetadataItemApi(formData.value.id, {
        name: formData.value.name,
        code: formData.value.code || undefined,
        description: formData.value.description || undefined,
        sort_order: formData.value.sort_order,
      });
      message.success('更新成功');
    } else {
      // 新建时：分组固定为 tag_group，标签固定为 tag
      const itemType = formData.value.parent_id ? 'tag' : 'tag_group';
      // 如果 code 为空，使用简单兜底（实际会通过 AI 生成）
      const finalCode = formData.value.code || `tag_${Date.now().toString(36)}`;
      await createMetadataItemApi(tenantCode.value, {
        item_type: itemType,
        name: formData.value.name,
        code: finalCode,
        description: formData.value.description || undefined,
        sort_order: formData.value.sort_order,
        parent_id: formData.value.parent_id,
      });
      message.success('创建成功');
    }
    modalVisible.value = false;
    refreshData();
  } catch (error) {
    logger.error('操作失败:', error);
    message.error('操作失败');
  } finally {
    modalLoading.value = false;
  }
}

// AI 生成编码
async function regenerateCode() {
  const name = formData.value.name?.trim();
  if (!name) {
    message.warning('请先输入名称');
    return;
  }

  isGeneratingCode.value = true;
  try {
    const result = await generateCodeApi({ name });
    formData.value.code = result.code;
    message.success(`AI 生成编码: ${result.code}`);
  } catch (error) {
    logger.error('AI 生成失败:', error);
    message.error('AI 生成失败，请手动输入');
  } finally {
    isGeneratingCode.value = false;
  }
}

// 监听名称变化，自动生成 code（仅新建模式且 code 为空时）
watch(
  () => formData.value.name,
  (newName) => {
    if (!isEditMode.value && !formData.value.code && newName) {
      // 自动调用 AI 生成
      regenerateCode();
    }
  },
);

// 删除
async function handleDelete(node: TreeNode) {
  try {
    await deleteMetadataItemApi(node.id);
    message.success('删除成功');
    refreshData();
  } catch (error) {
    logger.error('删除失败:', error);
    message.error('删除失败');
  }
}

// 监听租户变化
watch(tenantCode, () => {
  refreshData();
});

onMounted(() => {
  refreshData();
});
</script>

<template>
  <div class="space-y-5 p-5">
    <!-- 粘性筛选头部 -->
    <div
      class="sticky top-0 z-10 -mx-4 -mt-4 mb-3 bg-background/90 px-4 pb-4 pt-2 shadow-lg backdrop-blur-md"
      style="border-bottom: 1px solid hsl(var(--border) / 30%)"
    >
      <!-- 标题行 -->
      <div class="mb-2 flex items-center gap-3">
        <span
          class="bg-gradient-to-r from-[hsl(var(--primary))] to-[#22c55e] bg-clip-text text-xl font-bold text-transparent"
          >统一标签管理</span
        >
        <span v-if="lastUpdateTime" class="text-xs text-muted-foreground">
          数据更新时间：{{ lastUpdateTime }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <Space size="middle">
          <Input
            v-model:value="searchQuery"
            placeholder="搜索标签名称..."
            allow-clear
            style="width: 200px"
          >
            <template #prefix>
              <SearchOutlined />
            </template>
          </Input>
        </Space>
        <div class="filter-actions">
          <Button
            class="bg-gradient-to-r from-primary to-green-500 transition-all hover:-translate-y-0.5 hover:shadow-lg"
            @click="openNewGroupModal()"
          >
            <template #icon><PlusOutlined /></template>
            新增分组
          </Button>
        </div>
      </div>
    </div>

    <!-- 统计 -->
    <div class="flex items-center gap-4 rounded-xl border bg-muted/30 p-4">
      <div class="flex items-baseline gap-1">
        <span class="text-2xl font-bold">{{ statsInfo.groupCount }}</span>
        <span class="text-sm text-muted-foreground">个分组</span>
      </div>
      <Separator orientation="vertical" class="h-8" />
      <div class="flex items-baseline gap-1">
        <span class="text-2xl font-bold">{{ statsInfo.tagCount }}</span>
        <span class="text-sm text-muted-foreground">个标签</span>
      </div>
    </div>

    <!-- 主卡片 -->
    <Card>
      <Spin :spinning="loading">
        <div v-if="flatItems.length === 0" class="py-15 text-center">
          <Empty :description="searchQuery ? '未找到匹配结果' : '暂无数据'" />
        </div>

        <div v-else class="divide-y">
          <div
            v-for="item in flatItems"
            :key="item.id"
            class="group -mx-3 flex items-center gap-2 rounded-md px-3 py-3 hover:bg-muted/30"
            :style="{ paddingLeft: `${(item.level || 0) * 24 + 12}px` }"
          >
            <!-- 展开/收起 -->
            <button
              v-if="hasChildren(item)"
              class="flex h-5 w-5 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted/50"
              @click="toggleExpand(item.id)"
            >
              <UpOutlined v-if="expandedItems.has(item.id)" />
              <DownOutlined v-else />
            </button>
            <div v-else class="w-5"></div>

            <!-- 内容 -->
            <div class="flex min-w-0 flex-1 items-center gap-2">
              <span class="truncate text-sm font-medium">{{ item.name }}</span>
              <span
                v-if="item.corpus_count > 0"
                class="whitespace-nowrap text-xs text-muted-foreground"
              >
                {{ item.corpus_count }} 语料
              </span>
            </div>

            <!-- 操作 -->
            <div
              class="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100"
            >
              <Button
                v-if="item.category_type === 'group'"
                variant="ghost"
                size="icon"
                class="h-8 w-8"
                @click.stop="openNewTagModal(item.id, item.name)"
              >
                <PlusOutlined />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                class="h-8 w-8"
                @click.stop="openEditModal(item)"
              >
                <EditOutlined />
              </Button>
              <Popconfirm
                title="确定删除？"
                :description="
                  hasChildren(item) ? '将同时删除所有子项' : undefined
                "
                :overlay-style="{ width: '180px' }"
                @confirm="handleDelete(item)"
              >
                <Button
                  variant="ghost"
                  size="icon"
                  class="h-8 w-8 text-destructive hover:bg-destructive/10"
                >
                  <DeleteOutlined />
                </Button>
              </Popconfirm>
            </div>
          </div>
        </div>
      </Spin>
    </Card>

    <!-- 弹窗 -->
    <Modal
      v-model:open="modalVisible"
      :title="modalTitle"
      :confirm-loading="modalLoading"
      @ok="handleSubmit"
    >
      <div class="space-y-4">
        <div class="space-y-2">
          <Label required>名称</Label>
          <Input
            v-model:value="formData.name"
            placeholder="请输入名称"
            :maxlength="100"
          />
        </div>
        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <Label>编码</Label>
            <button
              v-if="!isEditMode"
              type="button"
              class="flex items-center gap-1 text-xs text-primary hover:underline"
              :disabled="isGeneratingCode || !formData.name"
              @click="regenerateCode()"
            >
              <Spin v-if="isGeneratingCode" size="small" />
              {{ isGeneratingCode ? 'AI 生成中...' : 'AI 生成' }}
            </button>
          </div>
          <Input
            v-model:value="formData.code"
            :placeholder="isEditMode ? '编辑模式' : '输入名称后 AI 自动生成'"
            :readonly="false"
            :maxlength="50"
          />
          <p class="text-xs text-muted-foreground">
            <template v-if="isEditMode">
              编辑模式：修改编码可能影响已有数据关联
            </template>
            <template v-else>
              新建时根据名称自动生成，可手动修改或点击"AI 生成"重新生成
            </template>
          </p>
        </div>
        <div class="space-y-2">
          <Label>描述</Label>
          <Textarea
            v-model="formData.description"
            placeholder="请输入描述"
            :rows="3"
            :maxlength="500"
          />
        </div>
        <div class="space-y-2">
          <Label>排序</Label>
          <Input
            v-model:value="formData.sort_order"
            type="number"
            :min="0"
            :max="9999"
          />
          <p class="text-xs text-muted-foreground">数值越小排序越靠前</p>
        </div>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.filter-row {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
}

.filter-actions {
  display: flex;
  gap: 8px;
}
</style>
