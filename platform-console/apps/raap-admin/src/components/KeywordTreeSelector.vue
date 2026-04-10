<script setup lang="ts">
/**
 * 关键词树选择器组件
 *
 * 用于 Expert 配置时，从关键词树中选择节点绑定到变量
 * 支持树形展开，查看和选择子节点
 *
 * 使用方式：
 * <KeywordTreeSelector
 *   v-model:visible="selectorVisible"
 *   :label="selectedLabel"
 *   :selected-ids="selectedNodeIds"
 *   @confirm="handleConfirm"
 * />
 */
import { computed, onMounted, ref, watch } from 'vue';

import {
  DownOutlined,
  LoadingOutlined,
  RightOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue';
import {
  Checkbox,
  Empty,
  Input,
  message,
  Modal,
  Select,
  SelectOption,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import { requestClient } from '#/api/request';
import CopyButton from '#/components/CopyButton.vue';
// 引入增强组件
import EnhancedButton from '#/components/EnhancedButton.vue';
import SkeletonLoader from '#/components/SkeletonLoader.vue';

interface LabelInfo {
  label: string;
  count: number;
  description: string;
}

interface NodeInfo {
  id: string;
  name: string;
  label: string;
  description: null | string;
  keywords: Array<{ text: string; weight?: number }>;
  parent_path: string[];
  has_children: boolean;
  // 树形结构扩展字段
  children?: NodeInfo[];
  level?: number;
  isExpanded?: boolean;
  isLoading?: boolean;
}

const props = defineProps<{
  label?: string;
  selectedIds?: string[];
  /** 租户编码，用于筛选关键词 */
  tenantCode?: string;
  visible: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void;
  (
    e: 'confirm',
    data: { label: string; selectedIds: string[]; selectedNodes: NodeInfo[] },
  ): void;
}>();

// 状态
const loading = ref(false);
const labels = ref<LabelInfo[]>([]);
const nodes = ref<NodeInfo[]>([]);
const selectedLabel = ref<string>('');
const selectedNodeIds = ref<Set<string>>(new Set());
const searchText = ref('');

// 所有节点的平面映射（包括动态加载的子节点）
const allNodesMap = ref<Map<string, NodeInfo>>(new Map());

// 展开状态
const expandedNodeIds = ref<Set<string>>(new Set());
const loadingNodeIds = ref<Set<string>>(new Set());

// 计算属性：构建树形展示列表（带缩进）
const displayNodes = computed(() => {
  if (searchText.value) {
    // 搜索模式：扁平展示所有匹配的节点
    const keyword = searchText.value.toLowerCase();
    return [...allNodesMap.value.values()].filter(
      (node) =>
        node.name.toLowerCase().includes(keyword) ||
        (node.description && node.description.toLowerCase().includes(keyword)),
    );
  }

  // 树形模式：按展开状态构建列表
  const result: NodeInfo[] = [];
  const buildList = (nodeList: NodeInfo[], level: number) => {
    for (const node of nodeList) {
      result.push({ ...node, level });
      if (
        node.has_children &&
        expandedNodeIds.value.has(node.id) &&
        node.children &&
        node.children.length > 0
      ) {
        buildList(node.children, level + 1);
      }
    }
  };
  buildList(nodes.value, 0);
  return result;
});

const selectedCount = computed(() => selectedNodeIds.value.size);

// 获取所有 label 列表
async function fetchLabels() {
  try {
    const res = await requestClient.get<LabelInfo[]>(
      '/v1/keyword-corpus/categories/labels',
      {
        params: {
          tenant_code: props.tenantCode || 'default',
        },
      },
    );
    labels.value = res || [];
  } catch (error) {
    console.error('获取 labels 失败:', error);
    message.error('获取分类类型列表失败');
  }
}

// 按 label 获取顶层节点
async function fetchNodesByLabel(label: string) {
  if (!label) {
    nodes.value = [];
    allNodesMap.value.clear();
    return;
  }

  loading.value = true;
  try {
    const res = await requestClient.get<{ items: NodeInfo[]; total: number }>(
      `/v1/keyword-corpus/categories/by-label/${encodeURIComponent(label)}`,
      {
        params: {
          tenant_code: props.tenantCode || 'default',
          include_keywords: true,
          include_parent_path: true,
          page_size: 500,
        },
      },
    );
    const items = res?.items || [];
    nodes.value = items.map((node) => ({
      ...node,
      children: [],
      isExpanded: false,
      isLoading: false,
    }));

    // 更新节点映射
    allNodesMap.value.clear();
    for (const node of nodes.value) {
      allNodesMap.value.set(node.id, node);
    }
  } catch (error) {
    console.error('获取节点失败:', error);
    message.error('获取节点列表失败');
  } finally {
    loading.value = false;
  }
}

// 获取子节点
async function fetchChildren(nodeId: string) {
  const node = allNodesMap.value.get(nodeId);
  if (!node || !node.has_children) return;

  // 如果已加载过，直接返回
  if (node.children && node.children.length > 0) return;

  loadingNodeIds.value.add(nodeId);
  loadingNodeIds.value = new Set(loadingNodeIds.value);

  try {
    const res = await requestClient.get<NodeInfo[]>(
      `/v1/keyword-corpus/categories/${nodeId}/children`,
      {
        params: {
          tenant_code: props.tenantCode || 'default',
          include_keywords: true,
        },
      },
    );

    const children = (res || []).map((child: NodeInfo) => ({
      ...child,
      children: [],
      isExpanded: false,
      isLoading: false,
    }));

    // 更新节点的子节点
    node.children = children;

    // 添加到节点映射
    for (const child of children) {
      allNodesMap.value.set(child.id, child);
    }
  } catch (error) {
    console.error('获取子节点失败:', error);
    message.error('获取子节点失败');
  } finally {
    loadingNodeIds.value.delete(nodeId);
    loadingNodeIds.value = new Set(loadingNodeIds.value);
  }
}

// 切换展开状态
async function toggleExpand(nodeId: string) {
  const node = allNodesMap.value.get(nodeId);
  if (!node || !node.has_children) return;

  if (expandedNodeIds.value.has(nodeId)) {
    // 收起
    expandedNodeIds.value.delete(nodeId);
    expandedNodeIds.value = new Set(expandedNodeIds.value);
  } else {
    // 展开，先加载子节点
    await fetchChildren(nodeId);
    expandedNodeIds.value.add(nodeId);
    expandedNodeIds.value = new Set(expandedNodeIds.value);
  }
}

// 切换选择
function toggleNode(nodeId: string) {
  if (selectedNodeIds.value.has(nodeId)) {
    selectedNodeIds.value.delete(nodeId);
  } else {
    selectedNodeIds.value.add(nodeId);
  }
  // 触发响应式更新
  selectedNodeIds.value = new Set(selectedNodeIds.value);
}

// 全选/取消全选当前显示的节点
function toggleAll() {
  if (selectedNodeIds.value.size === displayNodes.value.length) {
    selectedNodeIds.value.clear();
  } else {
    displayNodes.value.forEach((node) => selectedNodeIds.value.add(node.id));
  }
  selectedNodeIds.value = new Set(selectedNodeIds.value);
}

// 确认选择
function handleConfirm() {
  const selectedNodes = [...allNodesMap.value.values()].filter((n) =>
    selectedNodeIds.value.has(n.id),
  );
  emit('confirm', {
    label: selectedLabel.value,
    selectedIds: [...selectedNodeIds.value],
    selectedNodes,
  });
  emit('update:visible', false);
}

// 取消
function handleCancel() {
  emit('update:visible', false);
}

// 获取关键词预览文本
function getKeywordPreview(node: NodeInfo): string {
  if (node.keywords && node.keywords.length > 0) {
    const text = node.keywords[0]?.text || '';
    return text.length > 50 ? `${text.slice(0, 50)}...` : text;
  }
  if (node.description) {
    return node.description.length > 50
      ? `${node.description.slice(0, 50)}...`
      : node.description;
  }
  return '无语料';
}

// 高亮搜索文本
function highlightText(text: string, keyword: string): string {
  if (!keyword) return text;
  const regex = new RegExp(`(${keyword})`, 'gi');
  return text.replace(regex, '<mark>$1</mark>');
}

// 复制节点信息
function handleCopyNode(node: NodeInfo) {
  const text = `节点名称: ${node.name}\n节点ID: ${node.id}\n分类: ${node.label}\n${node.description ? `描述: ${node.description}` : ''}`;
  navigator.clipboard.writeText(text);
  message.success('节点信息已复制');
}

// 监听 visible 变化
watch(
  () => props.visible,
  (val) => {
    if (val) {
      // 初始化选中状态
      selectedNodeIds.value = new Set(props.selectedIds || []);
      expandedNodeIds.value.clear();
      if (props.label) {
        selectedLabel.value = props.label;
        fetchNodesByLabel(props.label);
      }
      if (labels.value.length === 0) {
        fetchLabels();
      }
    }
  },
);

// 监听 label 变化
watch(selectedLabel, (val) => {
  if (val) {
    fetchNodesByLabel(val);
    expandedNodeIds.value.clear();
    // 清空已选择的节点
    selectedNodeIds.value.clear();
    selectedNodeIds.value = new Set(selectedNodeIds.value);
  }
});

onMounted(() => {
  fetchLabels();
});
</script>

<template>
  <Modal
    :open="visible"
    title="选择关键词节点"
    width="900px"
    :footer="null"
    @cancel="handleCancel"
  >
    <div class="selector-container">
      <!-- 顶部筛选 -->
      <div class="selector-header">
        <div class="label-select">
          <span class="label-text">绑定类型：</span>
          <Select
            v-model:value="selectedLabel"
            style="width: 200px"
            placeholder="选择分类类型"
          >
            <SelectOption
              v-for="item in labels"
              :key="item.label"
              :value="item.label"
            >
              {{ item.label }} ({{ item.count }})
            </SelectOption>
          </Select>
        </div>
        <div class="search-box">
          <Input
            v-model:value="searchText"
            placeholder="搜索节点名称/描述"
            style="width: 200px"
            allow-clear
          >
            <template #prefix>
              <SearchOutlined />
            </template>
          </Input>
        </div>
      </div>

      <!-- 提示信息 -->
      <div class="hint-bar">
        <Tag color="blue">💡 点击箭头展开子节点，选择需要绑定的节点</Tag>
      </div>

      <!-- 节点列表 -->
      <div class="node-list">
        <SkeletonLoader v-if="loading" type="list" :rows="5" />

        <div v-else-if="displayNodes.length === 0" class="empty-state">
          <Empty
            :description="selectedLabel ? '暂无节点' : '请先选择分类类型'"
          />
        </div>

        <div v-else class="node-items">
          <!-- 全选/取消全选 -->
          <div v-if="displayNodes.length > 0" class="select-all">
            <Checkbox
              :checked="
                selectedNodeIds.size === displayNodes.length &&
                displayNodes.length > 0
              "
              :indeterminate="
                selectedNodeIds.size > 0 &&
                selectedNodeIds.size < displayNodes.length
              "
              @change="toggleAll"
            >
              全选当前列表 ({{ selectedCount }}/{{ displayNodes.length }})
            </Checkbox>
          </div>

          <!-- 节点卡片 -->
          <div
            v-for="node in displayNodes"
            :key="node.id"
            class="node-card"
            :class="{ selected: selectedNodeIds.has(node.id) }"
            :style="{ marginLeft: `${(node.level || 0) * 24}px` }"
          >
            <!-- 展开/收起按钮 -->
            <div
              class="expand-btn"
              :class="{ 'has-children': node.has_children }"
              @click.stop="node.has_children && toggleExpand(node.id)"
            >
              <LoadingOutlined
                v-if="loadingNodeIds.has(node.id)"
                class="loading-icon"
              />
              <template v-else-if="node.has_children">
                <DownOutlined v-if="expandedNodeIds.has(node.id)" />
                <RightOutlined v-else />
              </template>
              <span v-else class="empty-icon"></span>
            </div>

            <!-- 复选框 -->
            <Checkbox
              :checked="selectedNodeIds.has(node.id)"
              @click.stop="toggleNode(node.id)"
            />

            <!-- 节点内容 -->
            <div class="node-content" @click="toggleNode(node.id)">
              <div class="node-header">
                <span
                  class="node-name"
                  v-html="
                    searchText
                      ? highlightText(node.name, searchText)
                      : node.name
                  "
                ></span>
                <Tag v-if="node.has_children" color="cyan" size="small">
                  有子节点
                </Tag>
                <Tag v-if="node.label" color="default" size="small">
                  {{ node.label }}
                </Tag>
                <CopyButton
                  :text="`${node.name} (${node.id})`"
                  size="small"
                  @copied="handleCopyNode(node)"
                />
              </div>
              <div
                v-if="!searchText && node.parent_path?.length"
                class="node-path"
              >
                {{ node.parent_path.join(' > ') }}
              </div>
              <div class="node-keyword">
                <Tooltip
                  :title="
                    node.keywords?.length
                      ? `共 ${node.keywords.length} 条语料`
                      : node.description || '无语料'
                  "
                >
                  <span
                    class="keyword-text"
                    v-html="
                      searchText && node.description
                        ? highlightText(getKeywordPreview(node), searchText)
                        : getKeywordPreview(node)
                    "
                  ></span>
                </Tooltip>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部操作 -->
      <div class="selector-footer">
        <div class="selected-info">
          已选择 <span class="count">{{ selectedCount }}</span> 个节点
        </div>
        <div class="actions">
          <EnhancedButton @click="handleCancel">取消</EnhancedButton>
          <EnhancedButton
            type="primary"
            :disabled="selectedCount === 0"
            @click="handleConfirm"
          >
            确定
          </EnhancedButton>
        </div>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
@keyframes spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

@keyframes slide-in-right {
  from {
    opacity: 0;
    transform: translateX(-20px);
  }

  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.selector-container {
  display: flex;
  flex-direction: column;
  height: 65vh;
}

.selector-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  margin-bottom: 12px;
  border-bottom: 1px solid hsl(var(--border));
}

.label-select {
  display: flex;
  gap: 8px;
  align-items: center;
}

.label-text {
  font-weight: 500;
  color: hsl(var(--foreground));
}

.hint-bar {
  margin-bottom: 12px;
}

.node-list {
  flex: 1;
  padding-right: 8px;
  overflow-y: auto;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
}

.node-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.select-all {
  padding: 8px 12px;
  margin-bottom: 8px;
  background: hsl(var(--muted));
  border-radius: 6px;
}

.node-card {
  position: relative;
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 10px 12px;
  overflow: hidden;
  cursor: pointer;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  transition: all 0.2s;
  animation: slide-in-right 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.node-card:hover {
  background: hsl(var(--accent));
  border-color: hsl(var(--primary));
}

.node-card.selected {
  background: hsl(var(--primary) / 10%);
  border-color: hsl(var(--primary));
}

.expand-btn {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  margin-top: 2px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  border-radius: 4px;
}

.expand-btn.has-children {
  cursor: pointer;
}

.expand-btn.has-children:hover {
  color: hsl(var(--primary));
  background: hsl(var(--muted));
}

.expand-btn .empty-icon {
  display: block;
  width: 12px;
}

.expand-btn .loading-icon {
  animation: spin 1s linear infinite;
}

.node-content {
  flex: 1;
  min-width: 0;
}

.node-header {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-bottom: 4px;
}

.node-name {
  font-weight: 500;
  color: hsl(var(--foreground));
}

.node-path {
  margin-bottom: 4px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.node-keyword {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.keyword-text {
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
}

.selector-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 12px;
  margin-top: 12px;
  border-top: 1px solid hsl(var(--border));
}

.selected-info {
  color: hsl(var(--muted-foreground));
}

.selected-info .count {
  font-weight: 600;
  color: hsl(var(--primary));
}

.actions {
  display: flex;
  gap: 8px;
}

/* 搜索高亮样式 */
:deep(mark) {
  padding: 0 2px;
  font-weight: 600;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 20%);
  border-radius: 2px;
}

/* 节点卡片选中动画 */
.node-card::before {
  position: absolute;
  top: 0;
  left: 0;
  width: 3px;
  height: 100%;
  content: '';
  background: hsl(var(--primary));
  transform: scaleY(0);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.node-card.selected::before {
  transform: scaleY(1);
}

/* 复制按钮样式调整 */
.node-header .copy-button {
  margin-left: auto;
}

/* 复制按钮容器样式 */
:deep(.copy-button) {
  opacity: 0;
  transition: opacity 0.2s;
}

.node-card:hover :deep(.copy-button) {
  opacity: 1;
}
</style>
