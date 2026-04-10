<script setup lang="ts">
import type { CorpusTemplate, TemplateFormData } from './types';

import { onMounted, ref } from 'vue';

import { Modal } from 'ant-design-vue';

import { getCorpusTemplateCategoryTypesApi } from '#/api/core/graph-corpus';

import TemplateFormModal from './components/TemplateFormModal.vue';
import TemplateList from './components/TemplateList.vue';
import { useTemplates } from './composables/useTemplates';

// 数据层
const {
  loading,
  templates,
  fetchTemplates,
  createTemplate,
  updateTemplate,
  deleteTemplate,
} = useTemplates();

// UI 状态
const selectedTenantCode = ref('default');
const modalVisible = ref(false);
const modalLoading = ref(false);
const isEditing = ref(false);
const currentTemplate = ref<CorpusTemplate>();

// 分类类型选项：从后端 API 获取
const categoryTypeOptions = ref<Array<{ label: string; value: string }>>([]);
const categoryTypesLoading = ref(false);

// 获取分类类型列表
const fetchCategoryTypes = async () => {
  categoryTypesLoading.value = true;
  try {
    const data = await getCorpusTemplateCategoryTypesApi({
      tenant_code: 'default',
    });
    categoryTypeOptions.value = (data || []).map((type: string) => ({
      value: type,
      label: type,
    }));
  } catch (error) {
    logger.error('获取分类类型失败:', error);
  } finally {
    categoryTypesLoading.value = false;
  }
};

// 新增模板
const handleAdd = () => {
  isEditing.value = false;
  currentTemplate.value = undefined;
  modalVisible.value = true;
};

// 编辑模板
const handleEdit = (record: CorpusTemplate) => {
  isEditing.value = true;
  currentTemplate.value = record;
  modalVisible.value = true;
};

// 提交表单
const handleSubmit = async ({
  isEditing: editing,
  formData,
}: {
  formData: TemplateFormData;
  isEditing: boolean;
}) => {
  modalLoading.value = true;
  try {
    let success = false;
    success = await (editing
      ? updateTemplate(formData.code, {
          name: formData.name,
          fields: formData.fields,
          description: formData.description,
        })
      : createTemplate(formData));

    if (success) {
      modalVisible.value = false;
      fetchTemplates(selectedTenantCode.value);
      // 新增模板后刷新分类类型列表
      if (!editing) {
        fetchCategoryTypes();
      }
    }
  } finally {
    modalLoading.value = false;
  }
};

// 删除模板
const handleDelete = async (code: string) => {
  const success = await deleteTemplate(code);
  if (success) {
    fetchTemplates(selectedTenantCode.value);
    fetchCategoryTypes();
  }
};

// 批量删除模板
const handleBatchDelete = async (codes: string[]) => {
  Modal.confirm({
    title: '确认批量删除',
    content: `确定要删除选中的 ${codes.length} 个模板吗？`,
    okText: '确定',
    cancelText: '取消',
    okButtonProps: { danger: true },
    onOk: async () => {
      // 逐个删除
      let successCount = 0;
      for (const code of codes) {
        const success = await deleteTemplate(code);
        if (success) {
          successCount++;
        }
      }
      if (successCount > 0) {
        fetchTemplates(selectedTenantCode.value);
        fetchCategoryTypes();
      }
    },
  });
};

// 初始化
onMounted(() => {
  fetchTemplates(selectedTenantCode.value);
  fetchCategoryTypes();
});
</script>

<template>
  <div class="template-management">
    <TemplateList
      :templates="templates"
      :loading="loading"
      :category-type-options="categoryTypeOptions"
      @refresh="fetchTemplates(selectedTenantCode)"
      @add="handleAdd"
      @edit="handleEdit"
      @delete="handleDelete"
      @batch-delete="handleBatchDelete"
    />

    <TemplateFormModal
      v-model:open="modalVisible"
      :is-editing="isEditing"
      :template="currentTemplate"
      :category-type-options="categoryTypeOptions"
      @submit="handleSubmit"
    />
  </div>
</template>

<style scoped>
.template-management {
  padding: 16px;
}

/* 移除内层组件的 padding，由页面头部统一管理 */
.template-management :deep(.template-list-page) {
  padding: 0;
}

.template-management :deep(.page-header) {
  margin-bottom: 20px;
}

.template-management :deep(.content-card) {
  min-height: calc(100vh - 220px);
}
</style>
