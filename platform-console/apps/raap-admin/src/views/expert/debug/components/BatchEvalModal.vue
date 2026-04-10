<script setup lang="ts">
import type { BatchEvalForm } from '../types';

/**
 * 批量评分弹窗组件
 */
import { computed } from 'vue';

import { Form, InputNumber, Modal, Select } from 'ant-design-vue';

const props = defineProps<Props>();

const emit = defineEmits<{
  submit: [];
  'update:form': [value: BatchEvalForm];
  'update:open': [value: boolean];
}>();

const { Item: FormItem } = Form as any;

interface Props {
  open: boolean;
  loading: boolean;
  testSetOptions: Array<{ label: string; value: string }>;
  form: BatchEvalForm;
}

const modalOpen = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val),
});

const formData = computed({
  get: () => props.form,
  set: (val) => emit('update:form', val),
});
</script>

<template>
  <Modal
    v-model:open="modalOpen"
    title="🧪 批量评分（从测试集抽样）"
    :confirm-loading="loading"
    ok-text="开始评分"
    cancel-text="取消"
    @ok="emit('submit')"
  >
    <Form layout="vertical">
      <FormItem label="测试集" required>
        <Select
          v-model:value="formData.test_set_code"
          :options="testSetOptions"
          placeholder="请选择测试集"
          show-search
          option-filter-prop="label"
          :get-popup-container="(trigger) => trigger.parentElement"
        />
      </FormItem>
      <FormItem label="抽样数量">
        <InputNumber
          v-model:value="formData.max_count"
          :min="1"
          :max="5000"
          style="width: 100%"
          placeholder="从测试集中抽取的文章数"
        />
        <div class="mt-1 text-xs text-muted-foreground">
          按最新创建时间排序，抽取前 N 篇文章进行评分
        </div>
      </FormItem>
      <FormItem label="并发数">
        <InputNumber
          v-model:value="formData.article_concurrency"
          :min="1"
          :max="20"
          style="width: 100%"
        />
        <div class="mt-1 text-xs text-muted-foreground">
          同时评分的文章数量，建议 3-5
        </div>
      </FormItem>
    </Form>
  </Modal>
</template>

<style scoped>
.mt-1 {
  margin-top: 4px;
}
</style>
