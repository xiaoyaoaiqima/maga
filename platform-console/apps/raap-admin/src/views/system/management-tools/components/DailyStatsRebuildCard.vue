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
  message,
  Typography,
} from 'ant-design-vue';

import { rebuildDailyStatsApi } from '#/api/system/management';

defineProps<{
  description: string;
  title: string;
}>();

const loading = ref(false);
const result = ref<ManagementApi.TraceDailyStatsRebuildSummary | null>(null);

const formState = reactive({
  dateRange: [] as any[],
});

async function handleSubmit() {
  if (!formState.dateRange?.length) {
    message.warning('请选择日期范围');
    return;
  }

  loading.value = true;
  try {
    const params: ManagementApi.TraceDailyStatsRebuildRequest = {
      end_date: formState.dateRange[1].format('YYYY-MM-DD'),
      start_date: formState.dateRange[0].format('YYYY-MM-DD'),
    };

    const data = await rebuildDailyStatsApi(params);
    result.value = data;
    message.success('统计重建任务执行成功');
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
      <FormItem label="日期范围" required>
        <DatePicker.RangePicker
          v-model:value="formState.dateRange"
          style="width: 100%"
        />
      </FormItem>

      <Button block :loading="loading" type="primary" @click="handleSubmit">
        开始重建统计
      </Button>
    </Form>

    <div v-if="result" class="mt-4 rounded border border-border bg-muted p-3">
      <Typography.Title :level="5">执行概要</Typography.Title>
      <div class="text-sm">
        <div>处理日期: {{ result.start_date }} 至 {{ result.end_date }}</div>
        <div>处理天数: {{ result.days }} 天</div>
        <div class="mt-1 font-bold text-primary">
          受影响行数: {{ result.total_rows_affected }}
        </div>
      </div>
    </div>
  </Card>
</template>
