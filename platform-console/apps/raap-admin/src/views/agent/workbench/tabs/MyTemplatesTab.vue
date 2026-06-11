<script setup lang="ts">
// @ts-nocheck
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import {
  DeleteOutlined,
  EditOutlined,
  FileTextOutlined,
  PlusOutlined,
  SaveOutlined,
} from '@ant-design/icons-vue';
import {
  Button,
  Card,
  Col,
  Empty,
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Row,
  Space,
} from 'ant-design-vue';

import {
  createTemplateApi,
  deleteTemplateApi,
  getMyTemplatesApi,
  updateTemplateApi,
} from '#/api/core/agent';

interface AgentTemplate {
  id: string;
  name: string;
  description: string;
  category: string;
  icon: string;
  defaultConfig: {
    experts?: Array<{ code: string; type: string }>;
    keywords?: Record<string, string[]>;
    strategies?: Array<{ id?: string; name: string }>;
  };
  created_by: string;
  created_at: string;
  usage_count: number;
}

interface Emits {
  (e: 'refresh'): void;
}

const emit = defineEmits<Emits>();

const router = useRouter();

// 状态
const loading = ref(false);
const templates = ref<AgentTemplate[]>([]);
const modalVisible = ref(false);
const modalLoading = ref(false);
const editingTemplate = ref<AgentTemplate | null>(null);

// 表单
const formState = ref({
  name: '',
  description: '',
  category: 'custom',
});

// 分类配置
const categoryOptions = [
  { label: '生文类', value: 'generation' },
  { label: '营销类', value: 'marketing' },
  { label: '分析类', value: 'analysis' },
  { label: '自定义', value: 'custom' },
];

const categoryLabels: Record<string, string> = {
  generation: '生文类',
  marketing: '营销类',
  analysis: '分析类',
  custom: '自定义',
};

// 加载模板列表
async function fetchTemplates() {
  loading.value = true;
  try {
    const data = await getMyTemplatesApi();
    templates.value = data;
  } catch {
    message.error('加载模板失败');
  } finally {
    loading.value = false;
  }
}

// 从 Agent 创建模板
function handleCreateFromAgent() {
  message.info('请从"我的 Agent"列表中选择一个 Agent，点击"另存为模板"');
}

// 打开创建对话框
function openCreateModal() {
  editingTemplate.value = null;
  formState.value = {
    name: '',
    description: '',
    category: 'custom',
  };
  modalVisible.value = true;
}

// 打开编辑对话框
function openEditModal(template: AgentTemplate) {
  editingTemplate.value = template;
  formState.value = {
    name: template.name,
    description: template.description,
    category: template.category,
  };
  modalVisible.value = true;
}

// 提交表单
async function handleSubmit() {
  if (!formState.value.name.trim()) {
    message.warning('请输入模板名称');
    return;
  }

  modalLoading.value = true;
  try {
    if (editingTemplate.value) {
      await updateTemplateApi(editingTemplate.value.id, {
        name: formState.value.name,
        description: formState.value.description,
        category: formState.value.category,
      });
      message.success('更新模板成功');
    } else {
      await createTemplateApi({
        name: formState.value.name,
        description: formState.value.description,
        category: formState.value.category,
        config: {
          keywords: {},
          strategies: [],
          experts: [],
        },
      });
      message.success('创建模板成功');
    }
    modalVisible.value = false;
    emit('refresh');
  } catch {
    message.error(editingTemplate.value ? '更新模板失败' : '创建模板失败');
  } finally {
    modalLoading.value = false;
  }
}

// 删除模板
function handleDelete(template: AgentTemplate) {
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除模板 "${template.name}" 吗？此操作不可恢复。`,
    onOk: async () => {
      try {
        await deleteTemplateApi(template.id);
        message.success('删除成功');
        fetchTemplates();
      } catch {
        message.error('删除失败');
      }
    },
  });
}

// 从模板创建 Agent - 跳转到现有的 Agent 管理页面
function handleCreateFromTemplate(_template: AgentTemplate) {
  // TODO: 未来可以传递模板配置到 Agent 管理页面进行预填充
  // 目前先跳转到 Agent 管理页面，用户手动配置
  router.push('/job/agent');
}

// 获取分类标签颜色
function getCategoryColor(category: string): string {
  const colorMap: Record<string, string> = {
    generation: 'blue',
    marketing: 'green',
    analysis: 'purple',
    custom: 'default',
  };
  return colorMap[category] || 'default';
}

// 页面加载
onMounted(() => {
  fetchTemplates();
});
</script>

<template>
  <div class="my-templates-tab">
    <!-- 工具栏 -->
    <div class="toolbar">
      <Space>
        <Button type="primary" @click="openCreateModal">
          <PlusOutlined /> 新建模板
        </Button>
        <Button @click="handleCreateFromAgent">
          <SaveOutlined /> 从 Agent 创建
        </Button>
        <Button @click="fetchTemplates">刷新</Button>
      </Space>
    </div>

    <!-- 模板网格 -->
    <div v-if="templates.length > 0" class="template-grid">
      <Row :gutter="16">
        <Col v-for="template in templates" :key="template.id" :span="6">
          <Card :hoverable="true" class="template-card">
            <!-- 卡片头部 -->
            <div class="card-header">
              <FileTextOutlined class="card-icon" />
              <Dropdown>
                <template #overlay>
                  <Space
                    split
                    size="0"
                    direction="vertical"
                    style="min-width: 120px"
                  >
                    <Button
                      type="link"
                      size="small"
                      @click="openEditModal(template)"
                    >
                      <EditOutlined /> 编辑
                    </Button>
                    <Button
                      type="link"
                      size="small"
                      danger
                      @click="handleDelete(template)"
                    >
                      <DeleteOutlined /> 删除
                    </Button>
                  </Space>
                </template>
                <Button type="text" size="small">•••</Button>
              </Dropdown>
            </div>

            <!-- 分类标签 -->
            <Tag
              :color="getCategoryColor(template.category)"
              class="category-tag"
            >
              {{ categoryLabels[template.category] || template.category }}
            </Tag>

            <!-- 模板名称 -->
            <h3 class="template-name">{{ template.name }}</h3>

            <!-- 模板描述 -->
            <p class="template-desc">{{ template.description }}</p>

            <!-- 使用统计 -->
            <div class="template-meta">
              <span class="meta-item">
                使用 {{ template.usage_count || 0 }} 次
              </span>
              <span class="meta-item">
                {{ template.created_by }}
              </span>
            </div>

            <!-- 创建按钮 -->
            <Button
              type="primary"
              block
              class="create-btn"
              @click="handleCreateFromTemplate(template)"
            >
              使用此模板
            </Button>
          </Card>
        </Col>
      </Row>
    </div>

    <!-- 空状态 -->
    <div v-else-if="!loading" class="empty-state">
      <Empty description="暂无自定义模板">
        <p class="empty-hint">
          您可以从"我的 Agent"中选择一个 Agent，点击"另存为模板"来创建模板
        </p>
        <Button type="primary" @click="openCreateModal">
          <PlusOutlined /> 新建空模板
        </Button>
      </Empty>
    </div>

    <!-- 编辑/创建对话框 -->
    <Modal
      v-model:open="modalVisible"
      :title="editingTemplate ? '编辑模板' : '新建模板'"
      :confirm-loading="modalLoading"
      @ok="handleSubmit"
    >
      <Form layout="vertical">
        <FormItem label="模板名称" required>
          <Input
            v-model:value="formState.name"
            placeholder="请输入模板名称"
            maxlength="50"
            show-count
          />
        </FormItem>
        <FormItem label="模板分类">
          <Select
            v-model:value="formState.category"
            :options="categoryOptions"
            show-search
            :filter-option="true"
          />
        </FormItem>
        <FormItem label="模板描述">
          <Input.TextArea
            v-model:value="formState.description"
            placeholder="请输入模板描述"
            :rows="3"
            maxlength="200"
            show-count
          />
        </FormItem>
      </Form>
    </Modal>
  </div>
</template>

<style scoped>
.my-templates-tab {
  padding: 8px 0;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.template-grid {
  margin-top: 16px;
}

.template-card {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.card-icon {
  font-size: 20px;
  color: #1890ff;
}

.category-tag {
  align-self: flex-start;
  margin-bottom: 8px;
}

.template-name {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
}

.template-desc {
  flex: 1;
  min-height: 40px;
  margin: 0 0 12px;
  font-size: 13px;
  color: #666;
}

.template-meta {
  display: flex;
  justify-content: space-between;
  margin-bottom: 16px;
  font-size: 12px;
  color: #999;
}

.create-btn {
  margin-top: auto;
}

.empty-state {
  padding: 60px 0;
  text-align: center;
}

.empty-hint {
  margin: 8px 0 16px;
  color: #999;
}
</style>
