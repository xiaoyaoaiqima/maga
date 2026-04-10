import type { CorpusTemplate, TemplateFormData } from '../types';

import { ref } from 'vue';

import { message } from 'ant-design-vue';

import { requestClient } from '#/api/request';

export function useTemplates() {
  const loading = ref(false);
  const templates = ref<CorpusTemplate[]>([]);

  // 获取模板列表
  const fetchTemplates = async (tenantCode?: string) => {
    loading.value = true;
    try {
      const params: Record<string, string> = {};
      if (tenantCode) {
        params.tenant_code = tenantCode;
      }
      const res = await requestClient.get<{
        items: CorpusTemplate[];
        total: number;
      }>('/v1/keyword-corpus/corpus-templates', { params });
      templates.value = res?.items || [];
    } catch (error: unknown) {
      logger.error('获取模板列表失败:', error);
      message.error('获取模板列表失败');
    } finally {
      loading.value = false;
    }
  };

  // 创建模板
  const createTemplate = async (data: TemplateFormData) => {
    try {
      await requestClient.post('/v1/keyword-corpus/corpus-templates', data);
      message.success('模板创建成功');
      return true;
    } catch (error: unknown) {
      logger.error('创建模板失败:', error);

      // 提取错误详情
      let errorMsg = '创建模板失败';
      if (error && typeof error === 'object' && 'detail' in error) {
        errorMsg = String(error.detail);
      } else if (error && typeof error === 'object' && 'message' in error) {
        errorMsg = String(error.message);
      }

      // 对于"已存在"类错误，request.ts 已显示 warning，不再重复显示
      if (!errorMsg.includes('已存在')) {
        message.error(errorMsg);
      }
      return false;
    }
  };

  // 更新模板
  const updateTemplate = async (
    code: string,
    data: Omit<TemplateFormData, 'category_type' | 'code' | 'tenant_code'>,
  ) => {
    try {
      await requestClient.put(
        `/v1/keyword-corpus/corpus-templates/${code}`,
        data,
      );
      message.success('模板更新成功');
      return true;
    } catch (error) {
      logger.error('更新模板失败:', error);
      message.error('更新模板失败');
      return false;
    }
  };

  // 删除模板
  const deleteTemplate = async (code: string) => {
    try {
      await requestClient.delete(`/v1/keyword-corpus/corpus-templates/${code}`);
      message.success('模板删除成功');
      return true;
    } catch (error) {
      logger.error('删除模板失败:', error);
      message.error('删除模板失败');
      return false;
    }
  };

  return {
    loading,
    templates,
    fetchTemplates,
    createTemplate,
    updateTemplate,
    deleteTemplate,
  };
}
