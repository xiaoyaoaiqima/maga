/**
 * Prompt 编辑器 Composable
 */

import type { PluginSegment } from '../types';

import { computed, ref } from 'vue';

import { previewPromptApi } from '#/api/core/expert-debug';

export function usePromptEditor() {
  // Prompt 相关
  const promptTemplate = ref('');
  const renderedPrompt = ref('');
  const promptOverride = ref('');
  const usePromptOverride = ref(false);
  const pluginSegments = ref<PluginSegment[]>([]);
  const previewLoading = ref(false);

  // 分段编辑相关
  const editedSegments = ref<Record<number, string>>({});
  const editingSegmentIndex = ref<null | number>(null);

  // 用于取消过期请求
  let currentPreviewToken = 0;

  // 获取段落内容（优先返回编辑后的内容）
  function getSegmentContent(index: number, originalContent: string): string {
    return editedSegments.value[index] ?? originalContent;
  }

  // 计算最终的 Prompt（合并所有编辑后的段落）
  const finalPrompt = computed(() => {
    if (pluginSegments.value.length === 0) {
      return renderedPrompt.value;
    }
    return pluginSegments.value
      .map((seg, idx) => getSegmentContent(idx, seg.content))
      .join('\n');
  });

  // 是否有编辑过的内容
  const hasEditedSegments = computed(
    () => Object.keys(editedSegments.value).length > 0,
  );

  async function handlePreviewPrompt(
    expertConfigCode: string,
    pluginConfigSnapshot: Array<{
      plugin_code: string;
      variable_mapping: Record<string, string>;
    }>,
    isRestoring = false,
  ) {
    if (!expertConfigCode) return;
    if (isRestoring) return;

    const myToken = ++currentPreviewToken;
    previewLoading.value = true;
    try {
      const response = await previewPromptApi({
        expert_config_code: expertConfigCode,
        plugin_config_snapshot: pluginConfigSnapshot,
      });

      if (myToken !== currentPreviewToken) return;

      renderedPrompt.value = response.rendered_prompt;
      pluginSegments.value = response.plugin_segments || [];
      // 清空之前的编辑内容
      editedSegments.value = {};
      editingSegmentIndex.value = null;
    } catch (error: any) {
      if (myToken === currentPreviewToken) {
        console.error('预览 Prompt 失败:', error);
      }
    } finally {
      if (myToken === currentPreviewToken) {
        previewLoading.value = false;
      }
    }
  }

  /**
   * 强制预览（用于恢复状态时）
   */
  async function forcePreviewPrompt(
    expertConfigCode: string,
    pluginConfigSnapshot: Array<{
      plugin_code: string;
      variable_mapping: Record<string, string>;
    }>,
  ) {
    if (!expertConfigCode) return;

    const myToken = ++currentPreviewToken;
    previewLoading.value = true;
    try {
      const response = await previewPromptApi({
        expert_config_code: expertConfigCode,
        plugin_config_snapshot: pluginConfigSnapshot,
      });

      if (myToken !== currentPreviewToken) return;

      renderedPrompt.value = response.rendered_prompt;
      pluginSegments.value = response.plugin_segments || [];
      editedSegments.value = {};
      editingSegmentIndex.value = null;
    } catch (error: any) {
      if (myToken === currentPreviewToken) {
        console.error('预览 Prompt 失败:', error);
      }
    } finally {
      if (myToken === currentPreviewToken) {
        previewLoading.value = false;
      }
    }
  }

  function startEditSegment(index: number) {
    if (editedSegments.value[index] === undefined) {
      editedSegments.value[index] = pluginSegments.value[index]?.content || '';
    }
    editingSegmentIndex.value = index;
  }

  function saveEditSegment() {
    editingSegmentIndex.value = null;
  }

  function cancelEditSegment(index: number) {
    const { [index]: _, ...rest } = editedSegments.value;
    editedSegments.value = rest;
    editingSegmentIndex.value = null;
  }

  function resetAllEdits() {
    editedSegments.value = {};
    editingSegmentIndex.value = null;
  }

  function resetPromptState() {
    promptTemplate.value = '';
    renderedPrompt.value = '';
    promptOverride.value = '';
    usePromptOverride.value = false;
    pluginSegments.value = [];
    editedSegments.value = {};
    editingSegmentIndex.value = null;
  }

  return {
    // 状态
    promptTemplate,
    renderedPrompt,
    promptOverride,
    usePromptOverride,
    pluginSegments,
    previewLoading,
    editedSegments,
    editingSegmentIndex,

    // 计算属性
    finalPrompt,
    hasEditedSegments,

    // 方法
    getSegmentContent,
    handlePreviewPrompt,
    forcePreviewPrompt,
    startEditSegment,
    saveEditSegment,
    cancelEditSegment,
    resetAllEdits,
    resetPromptState,
  };
}
