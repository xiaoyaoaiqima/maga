<script setup lang="ts">
import type { JobApi, SchedulerApi } from '#/api/core/job';

import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';

import {
  Badge,
  Button,
  Card,
  Descriptions,
  DescriptionsItem,
  Empty,
  message,
  Modal,
  Popconfirm,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import {
  executeTaskNowApi,
  getExpertTaskListApi,
  getScheduledJobsApi,
  pauseScheduledTaskApi,
  registerTaskToSchedulerApi,
  removeTaskFromSchedulerApi,
  resumeScheduledTaskApi,
} from '#/api/core/job';
import { getCronDescription } from '#/utils/cron';

const route = useRoute();

// 状态
const loading = ref(false);
const scheduledJobs = ref<SchedulerApi.ScheduledJob[]>([]);
const expertTasks = ref<JobApi.ExpertTask[]>([]);
const detailModalVisible = ref(false);
const selectedTask = ref<JobApi.ExpertTask | null>(null);
const executingTasks = ref<Set<number>>(new Set()); // 正在执行的任务 ID 集合

// 任务状态映射
const taskStatusMap: Record<number, { color: string; text: string }> = {
  0: { color: 'blue', text: '待执行' },
  1: { color: 'orange', text: '执行中' },
  2: { color: 'default', text: '已暂停' },
  3: { color: 'green', text: '已完成' },
};

// 提取任务 ID
const extractTaskId = (jobId: string): null | number => {
  const match = jobId.match(/expert_task_(\d+)/);
  return match ? Number.parseInt(match[1]!, 10) : null;
};

// 合并调度器任务和数据库任务信息
const mergedJobs = computed(() => {
  return scheduledJobs.value.map((job) => {
    const taskId = extractTaskId(job.id);
    const dbTask = expertTasks.value.find((t) => t.id === taskId);
    return {
      ...job,
      taskId,
      dbTask,
      expertConfigCode: dbTask?.expert_config_code || '-',
      jobId: dbTask?.job_id || '-',
      dbStatus: dbTask?.status ?? -1,
      cronExpression: dbTask?.cron_expression || '-',
    };
  });
});

// 加载数据
const loadData = async () => {
  loading.value = true;
  try {
    const [schedulerRes, tasksRes] = await Promise.all([
      getScheduledJobsApi(),
      getExpertTaskListApi({ limit: 1000 }),
    ]);
    scheduledJobs.value = schedulerRes || [];
    expertTasks.value = tasksRes || [];
  } catch (error: any) {
    message.error(`加载数据失败: ${error.message || '未知错误'}`);
  } finally {
    loading.value = false;
  }
};

// 暂停任务
const handlePause = async (taskId: number) => {
  try {
    await pauseScheduledTaskApi(taskId);
    message.success('任务已暂停');
    await loadData();
  } catch (error: any) {
    message.error(`暂停失败: ${error.message || '未知错误'}`);
  }
};

// 恢复任务
const handleResume = async (taskId: number) => {
  try {
    await resumeScheduledTaskApi(taskId);
    message.success('任务已恢复');
    await loadData();
  } catch (error: any) {
    message.error(`恢复失败: ${error.message || '未知错误'}`);
  }
};

// 移除任务
const handleRemove = async (taskId: number) => {
  try {
    await removeTaskFromSchedulerApi(taskId);
    message.success('任务已从调度器移除');
    await loadData();
  } catch (error: any) {
    message.error(`移除失败: ${error.message || '未知错误'}`);
  }
};

// 立即执行
const handleExecuteNow = async (taskId: number) => {
  // 防止同一个任务重复点击（不同任务可以并发执行）
  if (executingTasks.value.has(taskId)) {
    message.warning('该任务正在执行中，请勿重复点击');
    return;
  }

  executingTasks.value.add(taskId);
  try {
    await executeTaskNowApi(taskId);
    message.success('任务已触发执行');
    // 成功后快速移除，允许查看执行结果
    setTimeout(() => {
      executingTasks.value.delete(taskId);
    }, 500);
  } catch (error: any) {
    message.error(`执行失败: ${error.message || '未知错误'}`);
    // 失败后立即移除，允许重试
    executingTasks.value.delete(taskId);
  }
};

// 重新注册
const handleRegister = async (taskId: number) => {
  try {
    await registerTaskToSchedulerApi(taskId);
    message.success('任务已重新注册');
    await loadData();
  } catch (error: any) {
    message.error(`注册失败: ${error.message || '未知错误'}`);
  }
};

// 查看详情
const showDetail = (task: JobApi.ExpertTask) => {
  selectedTask.value = task;
  detailModalVisible.value = true;
};

// 格式化下次执行时间
const formatNextRunTime = (time: null | string) => {
  if (!time) return '未设置';
  const date = new Date(time);
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
};

// 解析 cron 触发器
const parseTrigger = (trigger: string) => {
  // 简化显示
  return trigger.replace(/cron\[(.*)\]/, '$1');
};

// 表格列定义
const columns = [
  {
    title: '任务 ID',
    dataIndex: 'id',
    key: 'id',
    width: 150,
  },
  {
    title: 'Job ID',
    dataIndex: 'jobId',
    key: 'jobId',
    width: 180,
  },
  {
    title: 'Expert 配置',
    dataIndex: 'expertConfigCode',
    key: 'expertConfigCode',
    width: 200,
  },
  {
    title: 'Cron 表达式',
    dataIndex: 'cronExpression',
    key: 'cronExpression',
    width: 150,
  },
  {
    title: '触发器',
    dataIndex: 'trigger',
    key: 'trigger',
    width: 300,
    customRender: ({ text }: { text: string }) => parseTrigger(text),
  },
  {
    title: '下次执行时间',
    dataIndex: 'next_run_time',
    key: 'next_run_time',
    width: 180,
  },
  {
    title: '数据库状态',
    dataIndex: 'dbStatus',
    key: 'dbStatus',
    width: 100,
  },
  {
    title: '操作',
    key: 'action',
    width: 280,
    fixed: 'right' as const,
  },
];

onMounted(() => {
  loadData();
});
</script>

<template>
  <div class="scheduler-page">
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
          {{ route.meta.title || '定时任务管理' }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-item">
          <Badge
            :count="scheduledJobs.length"
            :offset="[-5, 0]"
            color="#52c41a"
          >
            <span style="margin-right: 16px">已注册任务</span>
          </Badge>
        </div>
        <div class="filter-actions">
          <Button type="primary" @click="loadData" :loading="loading">
            刷新
          </Button>
        </div>
      </div>
    </div>

    <Card :bordered="false">
      <Spin :spinning="loading">
        <div v-if="mergedJobs.length > 0">
          <Table
            :data-source="mergedJobs"
            :columns="columns"
            :row-key="(record) => record.id"
            :pagination="{
              pageSize: 20,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 条`,
            }"
            :scroll="{ x: 1400 }"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'id'">
                <Tag color="blue">{{ record.id }}</Tag>
              </template>

              <template v-else-if="column.key === 'jobId'">
                <a
                  v-if="record.jobId !== '-'"
                  :href="`/job/detail/${record.jobId}`"
                  target="_blank"
                >
                  {{ record.jobId }}
                </a>
                <span v-else>-</span>
              </template>

              <template v-else-if="column.key === 'expertConfigCode'">
                <Tooltip :title="record.expertConfigCode">
                  <span class="ellipsis-text">{{
                    record.expertConfigCode
                  }}</span>
                </Tooltip>
              </template>

              <template v-else-if="column.key === 'cronExpression'">
                <Tooltip :title="getCronDescription(record.cronExpression)">
                  <Tag color="cyan">{{ record.cronExpression }}</Tag>
                </Tooltip>
              </template>

              <template v-else-if="column.key === 'next_run_time'">
                <Space>
                  <span>🕐</span>
                  <span>{{ formatNextRunTime(record.next_run_time) }}</span>
                </Space>
              </template>

              <template v-else-if="column.key === 'dbStatus'">
                <Tag
                  v-if="record.dbStatus >= 0"
                  :color="taskStatusMap[record.dbStatus]?.color || 'default'"
                >
                  {{ taskStatusMap[record.dbStatus]?.text || '未知' }}
                </Tag>
                <Tag v-else color="default">未关联</Tag>
              </template>

              <template v-else-if="column.key === 'action'">
                <Space>
                  <Tooltip title="立即执行一次">
                    <Popconfirm
                      title="确定要立即执行此任务吗？"
                      @confirm="handleExecuteNow(record.taskId)"
                      :disabled="
                        !record.taskId || executingTasks.has(record.taskId)
                      "
                    >
                      <Button
                        type="primary"
                        size="small"
                        :disabled="
                          !record.taskId || executingTasks.has(record.taskId)
                        "
                        :loading="executingTasks.has(record.taskId)"
                      >
                        ⚡ 执行
                      </Button>
                    </Popconfirm>
                  </Tooltip>

                  <Tooltip title="暂停任务">
                    <Button
                      size="small"
                      :disabled="!record.taskId"
                      @click="handlePause(record.taskId)"
                    >
                      ⏸️
                    </Button>
                  </Tooltip>

                  <Tooltip title="恢复任务">
                    <Button
                      size="small"
                      :disabled="!record.taskId"
                      @click="handleResume(record.taskId)"
                    >
                      ▶️
                    </Button>
                  </Tooltip>

                  <Tooltip title="查看详情">
                    <Button
                      size="small"
                      :disabled="!record.dbTask"
                      @click="showDetail(record.dbTask)"
                    >
                      ℹ️
                    </Button>
                  </Tooltip>

                  <Tooltip title="从调度器移除">
                    <Popconfirm
                      title="确定要从调度器移除此任务吗？"
                      @confirm="handleRemove(record.taskId)"
                      :disabled="!record.taskId"
                    >
                      <Button danger size="small" :disabled="!record.taskId">
                        🗑️
                      </Button>
                    </Popconfirm>
                  </Tooltip>
                </Space>
              </template>
            </template>
          </Table>
        </div>

        <Empty v-else description="暂无已注册的定时任务" />
      </Spin>
    </Card>

    <!-- 任务详情弹窗 -->
    <Modal
      v-model:open="detailModalVisible"
      title="任务详情"
      :footer="null"
      width="600px"
    >
      <Descriptions v-if="selectedTask" :column="2" bordered size="small">
        <DescriptionsItem label="任务 ID" :span="1">
          {{ selectedTask.id }}
        </DescriptionsItem>
        <DescriptionsItem label="Job ID" :span="1">
          {{ selectedTask.job_id }}
        </DescriptionsItem>
        <DescriptionsItem label="Expert 配置" :span="2">
          {{ selectedTask.expert_config_code }}
        </DescriptionsItem>
        <DescriptionsItem label="Cron 表达式" :span="1">
          <Tag color="blue">{{ selectedTask.cron_expression }}</Tag>
        </DescriptionsItem>
        <DescriptionsItem label="状态" :span="1">
          <Tag :color="taskStatusMap[selectedTask.status]?.color || 'default'">
            {{ taskStatusMap[selectedTask.status]?.text || '未知' }}
          </Tag>
        </DescriptionsItem>
        <DescriptionsItem label="错过策略" :span="1">
          {{
            selectedTask.misfire_policy === 1
              ? '立即执行'
              : selectedTask.misfire_policy === 2
                ? '执行一次'
                : '放弃执行'
          }}
        </DescriptionsItem>
        <DescriptionsItem label="并发执行" :span="1">
          {{ selectedTask.concurrent === 0 ? '允许' : '禁止' }}
        </DescriptionsItem>
        <DescriptionsItem label="创建时间" :span="1">
          {{ selectedTask.create_time }}
        </DescriptionsItem>
        <DescriptionsItem label="更新时间" :span="1">
          {{ selectedTask.update_time }}
        </DescriptionsItem>
        <DescriptionsItem label="备注" :span="2">
          {{ selectedTask.remark || '-' }}
        </DescriptionsItem>
      </Descriptions>

      <div style="margin-top: 16px; text-align: right">
        <Space>
          <Button @click="handleRegister(selectedTask!.id)" type="primary">
            重新注册到调度器
          </Button>
          <Button @click="detailModalVisible = false">关闭</Button>
        </Space>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.scheduler-page {
  padding: 16px;
}

/* 筛选行布局 */
.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
}

.filter-item {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
}

.filter-label {
  font-weight: 500;
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.filter-actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
  margin-left: auto;
}

.ellipsis-text {
  display: inline-block;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
