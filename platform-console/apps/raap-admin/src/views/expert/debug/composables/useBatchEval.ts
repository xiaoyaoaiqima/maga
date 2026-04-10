/**
 * 批量评分 Composable
 */

import type { BatchEvalForm } from '../types';

import { ref } from 'vue';

import { message, notification } from 'ant-design-vue';

import {
  createEvalRunApi,
  listTestSetOptionsApi,
} from '#/api/core/expert-debug';

export function useBatchEval() {
  const batchModalOpen = ref(false);
  const batchSubmitting = ref(false);
  const testSetOptions = ref<Array<{ label: string; value: string }>>([]);

  const batchForm = ref<BatchEvalForm>({
    test_set_code: '',
    max_count: 50,
    article_concurrency: 3,
  });

  async function fetchTestSetOptions() {
    try {
      const items = await listTestSetOptionsApi();
      testSetOptions.value = (items || []).map((x) => ({
        value: x.code,
        label: `${x.name}（${x.case_count ?? 0} 条）`,
      }));
      if (!batchForm.value.test_set_code && testSetOptions.value.length > 0) {
        const firstOption = testSetOptions.value[0];
        if (firstOption) {
          batchForm.value.test_set_code = firstOption.value;
        }
      }
    } catch (error: any) {
      message.error(error?.message || '获取测试集列表失败');
    }
  }

  function openBatchModal(selectedExpert: string) {
    if (!selectedExpert) {
      message.warning('请先选择 Expert');
      return;
    }
    fetchTestSetOptions();
    batchModalOpen.value = true;
  }

  async function submitBatchScore(selectedExpert: string) {
    if (!selectedExpert) return;
    if (!batchForm.value.test_set_code) {
      message.warning('请选择测试集');
      return;
    }

    batchSubmitting.value = true;
    try {
      const resp = await createEvalRunApi({
        expert_config_code: selectedExpert,
        test_set_code: batchForm.value.test_set_code,
        max_count: Number(batchForm.value.max_count || 50) || 50,
        article_concurrency:
          Number(batchForm.value.article_concurrency || 3) || 3,
      });

      batchModalOpen.value = false;

      // 显示通知
      notification.success({
        message: '批量评分已开启',
        description: `任务 ${resp.run_code} 正在后台执行，可在「评分结果」页面查看进度`,
        duration: 4,
      });
    } catch (error: any) {
      message.error(error?.message || '发起批量评分失败');
    } finally {
      batchSubmitting.value = false;
    }
  }

  function resetBatchForm() {
    batchForm.value = {
      test_set_code: '',
      max_count: 50,
      article_concurrency: 3,
    };
  }

  return {
    // 状态
    batchModalOpen,
    batchSubmitting,
    testSetOptions,
    batchForm,

    // 方法
    fetchTestSetOptions,
    openBatchModal,
    submitBatchScore,
    resetBatchForm,
  };
}
