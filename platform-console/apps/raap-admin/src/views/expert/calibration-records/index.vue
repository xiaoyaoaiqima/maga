<script setup lang="ts">
import type {
  CalibrationRecordResponse,
  CalibrationTaskResponse,
} from '#/api/core/calibration';
import type { ExpertConfigOptionItem } from '#/api/core/critic-scores';
import type { ContentDetail } from '#/api/core/job-execution';

import { computed, onMounted, ref, watch } from 'vue';

import { Page } from '@vben/common-ui';
import { useUserStore } from '@vben/stores';

import {
  Empty,
  message,
  Select,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'ant-design-vue';

import {
  getCalibrationRecordsApi,
  getCalibrationTasksApi,
} from '#/api/core/calibration';
import { listExpertConfigOptionsApi } from '#/api/core/critic-scores';
import { getJobContentsApi } from '#/api/core/job-execution';

interface CombinedRecord extends CalibrationRecordResponse {
  article_title?: string;
  article_content?: string;
  ai_score?: number;
  ai_passed?: boolean;
}

const userStore = useUserStore();
const currentUserId = computed(() => userStore.userInfo?.userId);

const loading = ref(false);
const tasks = ref<CalibrationTaskResponse[]>([]);
const experts = ref<ExpertConfigOptionItem[]>([]);
const records = ref<CombinedRecord[]>([]);
const pageSize = ref(20);
const currentPage = ref(1);
const sortOrder = ref<'asc' | 'desc'>('desc');

// Expert 下拉框模糊搜索
const expertFilterOption = (input: string, option: any) => {
  return (option?.label ?? '')
    .toString()
    .toLowerCase()
    .includes(input.toLowerCase());
};

interface AssigneeOption {
  assignee_id: string;
  assignee_name: string;
}

const assignees = ref<AssigneeOption[]>([]);

const filter = ref({
  taskId: undefined as number | undefined,
  expertCode: undefined as string | undefined,
  assigneeId: undefined as string | undefined,
  resultType: 'all' as 'all' | 'consistent' | 'inconsistent',
  hasRemark: 'all' as 'all' | 'no' | 'yes',
});

const currentExpert = computed(() =>
  experts.value.find((e) => e.expert_config_code === filter.value.expertCode),
);

const resultOptions = computed(() => {
  if (!currentExpert.value) return [{ label: '全部', value: 'all' }];

  return currentExpert.value.expert_type === 'BAN'
    ? [
        { label: '全部', value: 'all' },
        { label: 'AI 正确', value: 'consistent' },
        { label: 'AI 不正确', value: 'inconsistent' },
      ]
    : [
        { label: '全部', value: 'all' },
        { label: '评分一致', value: 'consistent' },
        { label: '评分不一致', value: 'inconsistent' },
      ];
});

const columns = [
  {
    title: '文章信息',
    dataIndex: 'article',
    key: 'article',
    width: 400,
  },
  {
    title: 'AI 评分/结果',
    dataIndex: 'ai_result',
    key: 'ai_result',
    width: 120,
  },
  {
    title: '专家评分/结果',
    dataIndex: 'human_result',
    key: 'human_result',
    width: 120,
  },
  {
    title: '备注意见',
    dataIndex: 'remark',
    key: 'remark',
    width: 200,
  },
  {
    title: '校准人',
    dataIndex: 'reviewer_name',
    key: 'reviewer_name',
    width: 120,
  },
  {
    title: '校准时间',
    dataIndex: 'create_time',
    key: 'create_time',
    width: 180,
  },
];

const tasksLoading = ref(false);
const allTasksForAssignees = ref<CalibrationTaskResponse[]>([]);

const fetchInitialData = async () => {
  try {
    const expertsRes = await listExpertConfigOptionsApi();
    experts.value = expertsRes;
  } catch (error) {
    console.error('Failed to fetch initial data:', error);
    message.error('加载基础数据失败');
  }
};

const fetchTasksAndAssignees = async (expertCode: string) => {
  tasksLoading.value = true;
  try {
    // 获取该专家下所有用户的任务（不传 assignee_id）
    const tasksRes = await getCalibrationTasksApi({
      expert_config_code: expertCode,
      limit: 1000,
    });
    allTasksForAssignees.value = tasksRes;

    // 提取唯一的负责人列表
    const assigneeMap = new Map<string, string>();
    tasksRes.forEach((task) => {
      if (task.assignee_id) {
        const name = task.assignee_name || task.assignee_id;
        assigneeMap.set(task.assignee_id, name);
      }
    });

    assignees.value = [...assigneeMap.entries()].map(([id, name]) => ({
      assignee_id: id,
      assignee_name: name,
    }));

    // 设置默认值为当前用户
    if (currentUserId.value && assigneeMap.has(currentUserId.value)) {
      filter.value.assigneeId = currentUserId.value;
    }

    // 根据当前用户筛选任务
    await filterTasks();
  } catch (error) {
    console.error('Failed to fetch tasks:', error);
    message.error('加载校准任务失败');
  } finally {
    tasksLoading.value = false;
  }
};

const filterTasks = async () => {
  if (!filter.value.expertCode) return;

  try {
    const params: any = {
      expert_config_code: filter.value.expertCode,
      limit: 1000,
    };

    // 如果选择了具体用户（非全部），则筛选该用户的任务
    if (filter.value.assigneeId) {
      params.assignee_id = filter.value.assigneeId;
    }

    const tasksRes = await getCalibrationTasksApi(params);
    tasks.value = tasksRes;
  } catch (error) {
    console.error('Failed to filter tasks:', error);
    message.error('加载校准任务失败');
  }
};

const fetchRecords = async () => {
  if (!filter.value.expertCode) return;

  loading.value = true;
  try {
    const params: any = {
      limit: 5000,
    };
    if (filter.value.expertCode) {
      params.expert_config_codes = [filter.value.expertCode];
    }
    // 如果选择了具体任务,则只获取该任务的记录
    if (filter.value.taskId) {
      params.calibration_task_id = filter.value.taskId;
    }

    const res = await getCalibrationRecordsApi(params);

    // Group by job_id to fetch content details efficiently
    // 过滤出有 job_id 的记录
    const jobIds = [
      ...new Set(
        res
          .map((r) => r.job_id)
          .filter((jobId): jobId is string => typeof jobId === 'string'),
      ),
    ];
    const contentDetailsMap = new Map<string, ContentDetail>();

    await Promise.all(
      jobIds.map(async (jobId) => {
        try {
          const contents = await getJobContentsApi(jobId, {
            limit: 1000,
          });
          contents.forEach((c) => {
            contentDetailsMap.set(c.content_id, c);
          });
        } catch (error) {
          console.error(`Failed to fetch contents for job ${jobId}:`, error);
        }
      }),
    );

    records.value = res.map((record) => {
      const content = contentDetailsMap.get(record.content_id);

      // 优先使用后端返回的 AI 评分，如果没有则从 critic_summary 降级获取
      let aiScore = record.ai_score;
      let aiPassed = record.ai_passed;

      if (aiScore === undefined && aiPassed === undefined) {
        const aiScoreItem = content?.critic_summary?.scores?.find(
          (s) => s.expert_func === record.expert_func,
        );
        aiScore = aiScoreItem?.score;
        aiPassed = aiScoreItem?.passed;
      }

      return {
        ...record,
        article_title: content?.title,
        article_content: content?.content,
        ai_score: aiScore,
        ai_passed: aiPassed,
      };
    });
  } catch (error) {
    console.error('Failed to fetch records:', error);
    message.error('加载校准记录失败');
  } finally {
    loading.value = false;
  }
};

const sortedRecords = computed(() => {
  return records.value.toSorted((a, b) => {
    // 先按 content_id 分组,确保同一篇文章的记录在一起
    if (a.content_id !== b.content_id) {
      return sortOrder.value === 'desc'
        ? b.content_id.localeCompare(a.content_id)
        : a.content_id.localeCompare(b.content_id);
    }
    // 同一篇文章的记录按时间排序
    const timeA = new Date(a.create_time).getTime();
    const timeB = new Date(b.create_time).getTime();
    return sortOrder.value === 'desc' ? timeB - timeA : timeA - timeB;
  });
});

const duplicateContentIds = computed(() => {
  // 只有在未选择具体负责人时,才检测多校准人文章
  if (filter.value.assigneeId) {
    return new Set<string>();
  }

  const contentIdCount = new Map<string, number>();
  sortedRecords.value.forEach((record) => {
    const count = contentIdCount.get(record.content_id) || 0;
    contentIdCount.set(record.content_id, count + 1);
  });
  // 返回有多个校准人的文章 content_id
  return new Set(
    [...contentIdCount.entries()]
      .filter(([_, count]) => count > 1)
      .map(([contentId]) => contentId),
  );
});

const filteredRecords = computed(() => {
  return sortedRecords.value.filter((record) => {
    // 负责人筛选
    if (
      filter.value.assigneeId &&
      record.reviewer_id !== filter.value.assigneeId
    ) {
      return false;
    }

    // 结果类型筛选
    if (filter.value.resultType !== 'all') {
      if (record.expert_type === 'BAN') {
        const isConsistent = record.human_passed === record.ai_passed;
        if (
          filter.value.resultType === 'consistent'
            ? !isConsistent
            : isConsistent
        ) {
          return false;
        }
      } else {
        const hScore = record.human_score_value ?? 0;
        const aScore = record.ai_score ?? 0;
        const isConsistent = Math.abs(hScore - aScore) <= 40;
        if (
          filter.value.resultType === 'consistent'
            ? !isConsistent
            : isConsistent
        ) {
          return false;
        }
      }
    }

    // 备注筛选
    if (filter.value.hasRemark !== 'all') {
      const hasRemark = Boolean(record.remark?.trim());
      if (filter.value.hasRemark === 'yes' ? !hasRemark : hasRemark) {
        return false;
      }
    }

    return true;
  });
});

watch(
  () => filter.value.expertCode,
  (newCode) => {
    filter.value.taskId = undefined;
    filter.value.assigneeId = undefined;
    records.value = [];
    tasks.value = [];
    assignees.value = [];
    if (newCode) {
      fetchTasksAndAssignees(newCode);
      // 选择专家后自动获取所有任务的记录
      fetchRecords();
    }
  },
);

watch(
  () => filter.value.assigneeId,
  () => {
    filter.value.taskId = undefined;
    filterTasks();
  },
);

watch(
  () => filter.value.taskId,
  () => {
    fetchRecords();
  },
);

// 定义多校准人文章的颜色循环
const duplicateColors = [
  'duplicate-record-color-1', // 淡蓝色
  'duplicate-record-color-2', // 淡紫色
  'duplicate-record-color-3', // 淡黄色
  'duplicate-record-color-4', // 淡绿色
];

// 为每个有多校准人的 content_id 分配一个颜色索引
const duplicateContentColorIndex = computed(() => {
  const colorIndexMap = new Map<string, number>();
  let currentIndex = 0;

  duplicateContentIds.value.forEach((contentId) => {
    colorIndexMap.set(contentId, currentIndex % duplicateColors.length);
    currentIndex++;
  });

  return colorIndexMap;
});

const getRowClassName = (record: CombinedRecord) => {
  if (duplicateContentIds.value.has(record.content_id)) {
    const colorIndex =
      duplicateContentColorIndex.value.get(record.content_id) ?? 0;
    return duplicateColors[colorIndex];
  }
  return '';
};

onMounted(() => {
  fetchInitialData();
});

const getScoreClass = (score: number) => {
  if (score >= 80) return 'text-green-600';
  if (score <= 40) return 'text-red-600';
  return 'text-orange-500';
};
</script>

<template>
  <Page auto-content-height>
    <div class="flex h-full flex-col rounded-lg bg-card p-4 shadow-sm">
      <div class="mb-4 flex flex-wrap items-center gap-4">
        <div class="flex items-center gap-2">
          <span class="text-muted-foreground">专家维度:</span>
          <Select
            v-model:value="filter.expertCode"
            placeholder="请先选择专家"
            allow-clear
            show-search
            :filter-option="expertFilterOption"
            class="w-64"
            :options="
              experts.map((e) => ({
                label: e.expert_config_name || e.expert_config_code,
                value: e.expert_config_code,
              }))
            "
          />
        </div>

        <div class="flex items-center gap-2">
          <span class="text-muted-foreground">负责人:</span>
          <Select
            v-model:value="filter.assigneeId"
            placeholder="请选择负责人"
            allow-clear
            class="w-64"
            :loading="tasksLoading"
            :disabled="!filter.expertCode || tasksLoading"
            :options="[
              { label: '全部用户', value: undefined },
              ...assignees.map((a) => ({
                label: a.assignee_name,
                value: a.assignee_id,
              })),
            ]"
          />
        </div>

        <div class="flex items-center gap-2">
          <span class="text-muted-foreground">校准任务:</span>
          <Select
            v-model:value="filter.taskId"
            placeholder="全部任务"
            allow-clear
            class="w-64"
            :loading="tasksLoading"
            :disabled="!filter.expertCode || tasksLoading"
            :options="tasks.map((t) => ({ label: t.task_name, value: t.id }))"
          />
        </div>

        <div class="flex items-center gap-2">
          <span class="text-muted-foreground">时间排序:</span>
          <Select
            v-model:value="sortOrder"
            class="w-32"
            :disabled="!filter.expertCode"
            :options="[
              { label: '最新优先', value: 'desc' },
              { label: '最早优先', value: 'asc' },
            ]"
          />
        </div>

        <div class="flex items-center gap-2">
          <span class="text-muted-foreground">结果类型:</span>
          <Select
            v-model:value="filter.resultType"
            class="w-40"
            :disabled="!filter.expertCode"
            :options="resultOptions"
          />
        </div>

        <div class="flex items-center gap-2">
          <span class="text-muted-foreground">是否有备注:</span>
          <Select
            v-model:value="filter.hasRemark"
            class="w-40"
            :disabled="!filter.expertCode"
            :options="[
              { label: '全部', value: 'all' },
              { label: '有备注', value: 'yes' },
              { label: '无备注', value: 'no' },
            ]"
          />
        </div>
      </div>

      <div class="flex-1 overflow-hidden">
        <Table
          :columns="columns"
          :data-source="filteredRecords"
          :loading="loading"
          :pagination="{
            pageSize,
            current: currentPage,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
            pageSizeOptions: ['10', '20', '50', '100'],
          }"
          size="small"
          :scroll="{ y: 'calc(100vh - 350px)' }"
          :custom-row="(record) => ({ class: getRowClassName(record) })"
          row-key="id"
          @change="
            (pagination) => {
              currentPage = pagination.current;
              pageSize = pagination.pageSize;
            }
          "
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'article'">
              <div class="flex flex-col gap-1 py-2">
                <Typography.Text strong class="text-sm">
                  {{ record.article_title || '无标题' }}
                </Typography.Text>
                <Tooltip :title="record.article_content">
                  <Typography.Paragraph
                    :ellipsis="{ rows: 2 }"
                    class="mb-0 text-xs text-muted-foreground"
                  >
                    {{ record.article_content }}
                  </Typography.Paragraph>
                </Tooltip>
              </div>
            </template>

            <template v-else-if="column.key === 'ai_result'">
              <template v-if="record.expert_type === 'BAN'">
                <Tag :color="record.ai_passed ? 'success' : 'error'">
                  {{ record.ai_passed ? '通过' : '违规' }}
                </Tag>
              </template>
              <template v-else>
                <span
                  class="text-lg font-bold"
                  :class="getScoreClass(record.ai_score || 0)"
                >
                  {{ record.ai_score ?? '-' }}
                </span>
              </template>
            </template>

            <template v-else-if="column.key === 'human_result'">
              <template v-if="record.expert_type === 'BAN'">
                <Tag :color="record.human_passed ? 'success' : 'error'">
                  {{ record.human_passed ? '通过' : '违规' }}
                </Tag>
              </template>
              <template v-else>
                <span
                  class="text-lg font-bold"
                  :class="getScoreClass(record.human_score_value || 0)"
                >
                  {{ record.human_score_value ?? '-' }}
                </span>
              </template>
            </template>

            <template v-else-if="column.key === 'remark'">
              <span class="text-xs">{{ record.remark || '-' }}</span>
            </template>
          </template>
          <template #emptyText>
            <Empty description="暂无校准记录" />
          </template>
        </Table>
      </div>
    </div>
  </Page>
</template>

<style scoped>
:deep(.ant-table-wrapper) {
  height: 100%;
}

/* 淡蓝色 */
:deep(.duplicate-record-color-1) {
  background-color: #e6f7ff !important;
}

:deep(.duplicate-record-color-1:hover) {
  background-color: #bae7ff !important;
}

/* 淡紫色 */
:deep(.duplicate-record-color-2) {
  background-color: #f3e5f5 !important;
}

:deep(.duplicate-record-color-2:hover) {
  background-color: #e1bee7 !important;
}

/* 淡黄色 */
:deep(.duplicate-record-color-3) {
  background-color: #fffde7 !important;
}

:deep(.duplicate-record-color-3:hover) {
  background-color: #fff9c4 !important;
}

/* 淡绿色 */
:deep(.duplicate-record-color-4) {
  background-color: #e8f5e9 !important;
}

:deep(.duplicate-record-color-4:hover) {
  background-color: #c8e6c9 !important;
}
</style>
