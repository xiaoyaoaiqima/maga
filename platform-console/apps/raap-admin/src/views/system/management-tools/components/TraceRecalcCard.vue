<script setup lang="ts">
// @ts-nocheck
import type { ManagementApi } from '#/api/system/management';

import { reactive, ref } from 'vue';

import {
  Button,
  Card,
  DatePicker,
  Form,
  FormItem,
  InputNumber,
  message,
  Space,
  Switch,
  Typography,
} from 'ant-design-vue';

import { recalcTraceCostApi } from '#/api/system/management';

defineProps<{
  description: string;
  title: string;
}>();

const loading = ref(false);
const result = ref<ManagementApi.TraceCostRecalcSummary | null>(null);

const formState = reactive({
  batch_size: 2000,
  dateRange: [] as any[],
  dry_run: false,
  last_id: 0,
  only_if_price_found: true,
});

async function handleSubmit() {
  loading.value = true;
  try {
    const params: ManagementApi.TraceCostRecalcRequest = {
      batch_size: formState.batch_size,
      dry_run: formState.dry_run,
      last_id: formState.last_id,
      only_if_price_found: formState.only_if_price_found,
    };

    if (formState.dateRange?.length === 2) {
      params.start_time = formState.dateRange[0].startOf('day').toISOString();
      params.end_time = formState.dateRange[1].endOf('day').toISOString();
    }

    const data = await recalcTraceCostApi(params);
    result.value = data;
    message.success(formState.dry_run ? '预演完成' : '回算成功');
  } catch (error: any) {
    message.error(error?.response?.data?.detail || '执行失败');
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <Card :title="title">
    <template #extra>
      <div class="text-xs text-muted-foreground">{{ description }}</div>
    </template>

    <Form layout="vertical">
      <FormItem label="时间范围">
        <DatePicker.RangePicker
          v-model:value="formState.dateRange"
          show-time
          style="width: 100%"
        />
      </FormItem>

      <div class="grid grid-cols-2 gap-4">
        <FormItem label="批次大小">
          <InputNumber
            v-model:value="formState.batch_size"
            :max="20000"
            :min="1"
            style="width: 100%"
          />
        </FormItem>
        <FormItem label="起始 ID (游标)">
          <InputNumber
            v-model:value="formState.last_id"
            :min="0"
            style="width: 100%"
          />
        </FormItem>
      </div>

      <Space class="mb-4" size="large">
        <FormItem label="仅当有定价时更新" label-align="left">
          <Switch v-model:checked="formState.only_if_price_found" />
        </FormItem>
        <FormItem label="仅预演 (Dry Run)" label-align="left">
          <Switch v-model:checked="formState.dry_run" />
        </FormItem>
      </Space>

      <Button block :loading="loading" type="primary" @click="handleSubmit">
        立即执行回算
      </Button>
    </Form>

    <div v-if="result" class="mt-4 rounded border border-border bg-muted p-3">
      <Typography.Title :level="5">执行概要</Typography.Title>
      <div class="grid grid-cols-2 gap-2 text-sm">
        <div>读取记录: {{ result.processed }}</div>
        <div>更新记录: {{ result.updated }}</div>
        <div>缺失定价: {{ result.missing_price }}</div>
        <div>下一批 ID: {{ result.next_last_id ?? '已完成' }}</div>
      </div>
      <div class="mt-2 text-xs text-muted-foreground">
        <div>旧总成本: {{ result.old_total_cost_sum }}</div>
        <div>新总成本: {{ result.new_total_cost_sum }}</div>
        <div class="font-bold text-primary">
          成本增量: {{ result.delta_total_cost_sum }}
        </div>
      </div>
    </div>
  </Card>
</template>
