<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';

import { PlusOutlined } from '@ant-design/icons-vue';
import { Card, Col, Empty, Row, Spin, Tag } from 'ant-design-vue';

import { useAgentTemplates } from '../composables';

const router = useRouter();

// Composables
const {
  filteredTemplates,
  loading,
  selectedCategory,
  setCategory,
  getCategories,
  getAgentTypeInfo,
  fetchTemplates,
} = useAgentTemplates();

// 分类列表
const categories = computed(() => getCategories());

// 选择模板开始创建 - 跳转到 Agent 管理页面并传递模板 ID
function handleSelectTemplate(template: any) {
  // 跳转到 Agent 管理页面，携带模板 ID 用于预填充
  router.push({
    path: '/job/agent',
    query: { templateId: template.id },
  });
}

// 从空白创建
function handleCreateBlank() {
  router.push('/job/agent');
}

// 获取标签颜色
function getTypeColor(agentType: string): string {
  const info = getAgentTypeInfo(agentType);
  const colorMap: Record<string, string> = {
    blue: 'blue',
    red: 'red',
    green: 'green',
  };
  return colorMap[info.color] ?? 'purple';
}

// 页面加载时获取模板列表
onMounted(() => {
  fetchTemplates();
});
</script>

<template>
  <div class="template-select-tab">
    <!-- 快速创建按钮 -->
    <div class="quick-create">
      <a class="create-blank-link" @click="handleCreateBlank">
        <PlusOutlined /> 从空白创建
      </a>
    </div>

    <!-- 分类筛选 -->
    <div class="category-tabs">
      <span
        v-for="cat in categories"
        :key="cat.key"
        class="category-tab"
        :class="[{ active: selectedCategory === cat.key }]"
        @click="setCategory(cat.key)"
      >
        {{ cat.label }}
      </span>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="loading-state">
      <Spin size="large" tip="加载 Agent 模板..." />
    </div>

    <!-- 模板列表 -->
    <Row v-else :gutter="16" class="template-list">
      <Col v-for="template in filteredTemplates" :key="template.id" :span="6">
        <Card
          :hoverable="true"
          class="template-card"
          @click="handleSelectTemplate(template)"
        >
          <!-- 类型标签 -->
          <Tag :color="getTypeColor(template.agentType)" class="type-tag">
            {{ getAgentTypeInfo(template.agentType).icon }}
            {{ getAgentTypeInfo(template.agentType).label }}
          </Tag>

          <!-- Agent 名称 -->
          <h3 class="template-name">{{ template.name }}</h3>

          <!-- Agent 描述 -->
          <p class="template-desc">{{ template.description || '暂无描述' }}</p>

          <!-- Expert 数量 -->
          <div class="template-meta">
            <span class="meta-item">
              {{ template.expertConfigCodeList?.length || 0 }} 个 Expert
            </span>
          </div>

          <!-- 创建按钮 -->
          <div class="create-hint">点击创建副本</div>
        </Card>
      </Col>
    </Row>

    <!-- 空状态 -->
    <div v-if="!loading && filteredTemplates.length === 0" class="empty-state">
      <Empty description="暂无 Agent 模板">
        <p class="empty-hint">
          请先在 Agent 管理页面创建 Agent，然后在这里作为模板使用
        </p>
        <a class="create-link" @click="handleCreateBlank">
          <PlusOutlined /> 前往创建 Agent
        </a>
      </Empty>
    </div>
  </div>
</template>

<style scoped>
.template-select-tab {
  padding: 8px 0;
}

.quick-create {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 16px;
}

.create-blank-link {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  padding: 8px 16px;
  color: #1890ff;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
}

.create-blank-link:hover {
  background: #e6f7ff;
}

.category-tabs {
  display: flex;
  gap: 8px;
  padding-bottom: 12px;
  margin-bottom: 16px;
  border-bottom: 1px solid #f0f0f0;
}

.category-tab {
  padding: 6px 16px;
  color: #666;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
}

.category-tab:hover {
  background: #f5f5f5;
}

.category-tab.active {
  color: #1890ff;
  background: #e6f7ff;
}

.loading-state {
  display: flex;
  justify-content: center;
  padding: 60px 0;
}

.template-list {
  margin-top: 16px;
}

.template-card {
  display: flex;
  flex-direction: column;
  height: 100%;
  cursor: pointer;
  transition: all 0.2s;
}

.template-card:hover {
  box-shadow: 0 4px 12px rgb(0 0 0 / 10%);
  transform: translateY(-2px);
}

.type-tag {
  align-self: flex-start;
  margin-bottom: 8px;
}

.template-name {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
}

.template-desc {
  display: -webkit-box;
  flex: 1;
  min-height: 40px;
  margin: 0 0 12px;
  overflow: hidden;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  font-size: 13px;
  color: #666;
  -webkit-box-orient: vertical;
}

.template-meta {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
  font-size: 12px;
  color: #999;
}

.meta-item {
  display: flex;
  gap: 4px;
  align-items: center;
}

.create-hint {
  padding-top: 12px;
  margin-top: auto;
  font-size: 12px;
  color: #1890ff;
  text-align: center;
}

.empty-state {
  padding: 60px 0;
  text-align: center;
}

.empty-hint {
  margin: 8px 0 16px;
  color: #999;
}

.create-link {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  color: #1890ff;
  cursor: pointer;
}
</style>
