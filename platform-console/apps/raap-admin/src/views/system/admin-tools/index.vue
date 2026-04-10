<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';

import { Page } from '@vben/common-ui';

import {
  Button,
  Card,
  Descriptions,
  DescriptionsItem,
  Divider,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Modal,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Textarea,
} from 'ant-design-vue';

import { requestClient } from '#/api/request';

defineOptions({ name: 'SystemAdminTools' });

type TaskStatus = 'cancelled' | 'failed' | 'pending' | 'running' | 'success';

interface AdminToolTask {
  id: number;
  task_type: string;
  status: TaskStatus;
  progress: number;
  message?: null | string;
  params?: null | Record<string, any>;
  result?: null | Record<string, any>;
  error_message?: null | string;
  created_by?: null | string;
  started_at?: null | string;
  finished_at?: null | string;
  created_at?: null | string;
  updated_at?: null | string;
}

const loading = ref(false);
const tasks = ref<AdminToolTask[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);

const detailOpen = ref(false);
const selectedTask = ref<AdminToolTask | null>(null);

const activeTab = ref<
  | 'cost_backfill'
  | 'pricing_audit'
  | 'rebuild_daily_stats'
  | 'route_upsert_from_usage'
  | 'trace_field_repair'
  | 'verify_report'
>('pricing_audit');

const pricingAuditForm = reactive({
  start_date: '',
  end_date: '',
});

const fieldRepairForm = reactive({
  default_provider_code: 'aihubmix',
  default_model_code: 'gemini-2.5-flash',
});

const routeUpsertForm = reactive({
  fill_price: true,
  limit: 200,
});

const costBackfillForm = reactive({
  batch_size: 2000,
  start_time: '',
  end_time: '',
});

const rebuildDailyForm = reactive({
  start_date: '',
  end_date: '',
});

function statusColor(s: TaskStatus) {
  if (s === 'success') return 'green';
  if (s === 'failed') return 'red';
  if (s === 'running') return 'blue';
  if (s === 'pending') return 'orange';
  return 'default';
}

function prettyJson(v: any) {
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

async function fetchTasks() {
  loading.value = true;
  try {
    const resp = await requestClient.get<{
      items: AdminToolTask[];
      total: number;
    }>('/v1/system/admin-tools/tasks', {
      params: { page: page.value, page_size: pageSize.value },
    });
    tasks.value = resp.items || [];
    total.value = resp.total || 0;
  } catch (error) {
    console.error(error);
    message.error('获取任务列表失败');
  } finally {
    loading.value = false;
  }
}

async function createTask(
  task_type: string,
  params: null | Record<string, any>,
) {
  try {
    const task = await requestClient.post<AdminToolTask>(
      '/v1/system/admin-tools/tasks',
      {
        task_type,
        params,
      },
    );
    message.success(`任务已创建：#${task.id}`);
    await fetchTasks();
  } catch (error) {
    console.error(error);
    message.error('创建任务失败（请检查权限与参数）');
  }
}

async function handleSubmit() {
  switch (activeTab.value) {
    case 'cost_backfill': {
      await createTask('cost_backfill', {
        batch_size: Number(costBackfillForm.batch_size || 2000),
        start_time: costBackfillForm.start_time || null,
        end_time: costBackfillForm.end_time || null,
      });
      break;
    }
    case 'pricing_audit': {
      await createTask('pricing_audit', {
        start_date: pricingAuditForm.start_date || null,
        end_date: pricingAuditForm.end_date || null,
      });
      break;
    }
    case 'rebuild_daily_stats': {
      await createTask('rebuild_daily_stats', {
        start_date: rebuildDailyForm.start_date,
        end_date: rebuildDailyForm.end_date,
      });
      break;
    }
    case 'route_upsert_from_usage': {
      await createTask('route_upsert_from_usage', {
        fill_price: !!routeUpsertForm.fill_price,
        limit: Number(routeUpsertForm.limit || 200),
      });
      break;
    }
    case 'trace_field_repair': {
      await createTask('trace_field_repair', {
        default_provider_code: fieldRepairForm.default_provider_code || null,
        default_model_code: fieldRepairForm.default_model_code || null,
      });
      break;
    }
    case 'verify_report': {
      await createTask('verify_report', null);
      break;
    }
  }
}

function openDetail(row: AdminToolTask) {
  selectedTask.value = row;
  detailOpen.value = true;
}

const columns = [
  { title: 'ID', dataIndex: 'id', key: 'id', width: 80 },
  { title: '类型', dataIndex: 'task_type', key: 'task_type', width: 160 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 120 },
  { title: '进度', dataIndex: 'progress', key: 'progress', width: 100 },
  { title: '提示', dataIndex: 'message', key: 'message' },
  { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
  { title: '操作', key: 'action', width: 120 },
];

onMounted(() => {
  fetchTasks();
});
</script>

<template>
  <Page>
    <!-- 粘性筛选头部 -->
    <div
      class="sticky top-0 z-10 -mx-4 -mt-4 mb-3 bg-background/90 px-4 pb-4 pt-2 shadow-lg backdrop-blur-md"
      style="border-bottom: 1px solid hsl(var(--border) / 30%)"
    >
      <!-- 标题行 -->
      <div class="mb-2 flex items-center gap-3">
        <span
          class="bg-gradient-to-r from-[hsl(var(--primary))] to-[#22c55e] bg-clip-text text-xl font-bold text-transparent"
        >
          管理工具
        </span>
      </div>
    </div>
    <div class="mb-4 text-sm text-muted-foreground">
      表单提交后后台异步执行：盘点 / 修复 / 回刷 / 汇总 / 校验
    </div>

    <div class="flex flex-col gap-4">
      <Card title="创建任务">
        <Tabs v-model:active-key="activeTab">
          <Tabs.TabPane key="pricing_audit" tab="定价覆盖盘点">
            <Form layout="inline">
              <FormItem label="开始日期">
                <Input
                  v-model:value="pricingAuditForm.start_date"
                  placeholder="YYYY-MM-DD（可选）"
                />
              </FormItem>
              <FormItem label="结束日期">
                <Input
                  v-model:value="pricingAuditForm.end_date"
                  placeholder="YYYY-MM-DD（可选）"
                />
              </FormItem>
            </Form>
          </Tabs.TabPane>

          <Tabs.TabPane key="trace_field_repair" tab="Trace 字段补齐">
            <Form layout="inline">
              <FormItem label="默认 provider_code">
                <Input
                  v-model:value="fieldRepairForm.default_provider_code"
                  style="width: 240px"
                />
              </FormItem>
              <FormItem label="默认 model_code">
                <Input
                  v-model:value="fieldRepairForm.default_model_code"
                  style="width: 240px"
                />
              </FormItem>
            </Form>
            <Divider />
            <div class="text-xs text-muted-foreground">
              仅填充空值/空串；会影响历史口径，请谨慎在线上使用。
            </div>
          </Tabs.TabPane>

          <Tabs.TabPane key="route_upsert_from_usage" tab="从用量补齐路由">
            <Form layout="inline">
              <FormItem label="补齐价格">
                <Select
                  v-model:value="routeUpsertForm.fill_price"
                  style="width: 140px"
                  :options="[
                    { label: '是', value: true },
                    { label: '否', value: false },
                  ]"
                />
              </FormItem>
              <FormItem label="Top N">
                <InputNumber
                  v-model:value="routeUpsertForm.limit"
                  :min="1"
                  :max="1000"
                />
              </FormItem>
            </Form>
          </Tabs.TabPane>

          <Tabs.TabPane key="cost_backfill" tab="成本全量回算">
            <Form layout="inline">
              <FormItem label="batch_size">
                <InputNumber
                  v-model:value="costBackfillForm.batch_size"
                  :min="100"
                  :max="20000"
                />
              </FormItem>
              <FormItem label="start_time">
                <Input
                  v-model:value="costBackfillForm.start_time"
                  placeholder="ISO datetime（可选）"
                  style="width: 260px"
                />
              </FormItem>
              <FormItem label="end_time">
                <Input
                  v-model:value="costBackfillForm.end_time"
                  placeholder="ISO datetime（可选）"
                  style="width: 260px"
                />
              </FormItem>
            </Form>
          </Tabs.TabPane>

          <Tabs.TabPane key="rebuild_daily_stats" tab="重建日汇总">
            <Form layout="inline">
              <FormItem label="开始日期">
                <Input
                  v-model:value="rebuildDailyForm.start_date"
                  placeholder="YYYY-MM-DD"
                />
              </FormItem>
              <FormItem label="结束日期">
                <Input
                  v-model:value="rebuildDailyForm.end_date"
                  placeholder="YYYY-MM-DD"
                />
              </FormItem>
            </Form>
          </Tabs.TabPane>

          <Tabs.TabPane key="verify_report" tab="回刷校验报告">
            <div class="text-sm text-muted-foreground">
              输出明细总成本、日汇总总成本等对账信息。
            </div>
          </Tabs.TabPane>
        </Tabs>

        <Divider />
        <Space>
          <Button type="primary" @click="handleSubmit">提交并异步执行</Button>
          <Button @click="fetchTasks">刷新任务列表</Button>
        </Space>
      </Card>

      <Card title="任务列表">
        <Table
          :columns="columns"
          :data-source="tasks"
          :loading="loading"
          row-key="id"
          :pagination="{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (t: number) => `共 ${t} 条`,
            onChange: (p: number, ps: number) => {
              page = p;
              pageSize = ps;
              fetchTasks();
            },
          }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'status'">
              <Tag :color="statusColor(record.status)">{{ record.status }}</Tag>
            </template>
            <template v-else-if="column.key === 'action'">
              <Button size="small" @click="openDetail(record)">详情</Button>
            </template>
          </template>
        </Table>
      </Card>
    </div>

    <Modal
      v-model:open="detailOpen"
      title="任务详情"
      width="900px"
      :footer="null"
    >
      <div v-if="selectedTask" class="flex flex-col gap-3">
        <Descriptions :column="2" bordered size="small">
          <DescriptionsItem label="ID">{{ selectedTask.id }}</DescriptionsItem>
          <DescriptionsItem label="类型">
            {{ selectedTask.task_type }}
          </DescriptionsItem>
          <DescriptionsItem label="状态">
            <Tag :color="statusColor(selectedTask.status)">
              {{ selectedTask.status }}
            </Tag>
          </DescriptionsItem>
          <DescriptionsItem label="进度">
            {{ selectedTask.progress }}%
          </DescriptionsItem>
          <DescriptionsItem label="提示" :span="2">
            {{ selectedTask.message }}
          </DescriptionsItem>
        </Descriptions>

        <Card size="small" title="Params">
          <Textarea
            :value="prettyJson(selectedTask.params)"
            :rows="8"
            readonly
          />
        </Card>

        <Card size="small" title="Result">
          <Textarea
            :value="prettyJson(selectedTask.result)"
            :rows="12"
            readonly
          />
        </Card>

        <Card
          v-if="selectedTask.error_message"
          size="small"
          title="Error"
          class="border border-red-200"
        >
          <Textarea :value="selectedTask.error_message" :rows="10" readonly />
        </Card>
      </div>
    </Modal>
  </Page>
</template>
