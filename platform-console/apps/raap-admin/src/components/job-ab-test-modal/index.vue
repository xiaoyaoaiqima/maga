<script setup lang="ts">
import type { JobApi } from '#/api/core/job';

import { computed, ref, watch } from 'vue';

import {
  Alert,
  Badge,
  Button,
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Select,
  Tag,
} from 'ant-design-vue';

import { ABTestApi } from '#/api/core/ab-test';
import { getJobListApi } from '#/api/core/job';

const props = defineProps<Props>();

const emit = defineEmits<{
  (e: 'success'): void;
}>();

const { Option: SelectOption } = Select as { Option: unknown };

interface Props {
  agentCode: string;
  agentName?: string;
}

const visible = defineModel<boolean>('open', { default: false });

// 状态
const loading = ref(false);
const submitting = ref(false);
const searchText = ref('');
const jobList = ref<JobApi.Job[]>([]);

// 表单状态
const formState = ref<{
  job_ids: Record<string, string>;
  remark: string;
  test_name: string;
}>({
  test_name: '',
  job_ids: {
    control: '',
    experiment_1: '',
  },
  remark: '',
});

// 组描述
const groupDescriptions = ref<Record<string, string>>({
  control: '',
  experiment_1: '',
});

// 可用的组名列表
const availableGroups = computed(() => {
  return Object.keys(formState.value.job_ids).filter(
    (g) => !formState.value.job_ids[g],
  );
});

// 过滤后的 Job 列表
const filteredJobs = computed(() => {
  if (!searchText.value) return jobList.value;
  const keyword = searchText.value.toLowerCase();
  return jobList.value.filter(
    (job) =>
      job.job_name.toLowerCase().includes(keyword) ||
      job.job_id.toLowerCase().includes(keyword),
  );
});

// 可用的 Job（未被分配的）
const availableJobs = computed(() => {
  const assignedIds = new Set(
    Object.values(formState.value.job_ids).filter(Boolean),
  );
  return jobList.value.filter((job) => !assignedIds.has(job.job_id));
});

// 检查 Job 是否已被分配
function isJobAssigned(jobId: string): boolean {
  return Object.values(formState.value.job_ids).includes(jobId);
}

// 获取 Job 名称
function getJobName(jobId: string): string {
  const job = jobList.value.find((j) => j.job_id === jobId);
  return job?.job_name || jobId;
}

// 分配 Job 到组
function assignJobToGroup(jobId: string, groupName: string) {
  if (groupName && !formState.value.job_ids[groupName]) {
    formState.value.job_ids[groupName] = jobId;
  }
}

// 从组中移除 Job
function unassignJob(groupName: string) {
  formState.value.job_ids[groupName] = '';
}

// 添加新组
function addGroup() {
  const existingNums = Object.keys(formState.value.job_ids)
    .filter((g) => g.startsWith('experiment_'))
    .map((g) => Number.parseInt(g.replace('experiment_', ''), 10));
  const nextNum = existingNums.length > 0 ? Math.max(...existingNums) + 1 : 1;
  const newGroupName = `experiment_${nextNum}`;
  formState.value.job_ids[newGroupName] = '';
  groupDescriptions.value[newGroupName] = '';
}

// 删除组
function removeGroup(groupName: string) {
  if (groupName === 'control') return;
  const { [groupName]: _removed1, ...restJobIds } = formState.value.job_ids;
  formState.value.job_ids = restJobIds;
  const { [groupName]: _removed2, ...restDescriptions } =
    groupDescriptions.value;
  groupDescriptions.value = restDescriptions;
}

// 状态颜色映射
const statusConfig: Record<string, { color: string; label: string }> = {
  NOT_DEPLOYED: { color: 'default', label: '未部署' },
  DEPLOYED: { color: 'blue', label: '已部署' },
  RUNNING: { color: 'green', label: '运行中' },
  PAUSED: { color: 'orange', label: '已暂停' },
  COMPLETED: { color: 'red', label: '已完成' },
};

function getStatusColor(status: string): string {
  return statusConfig[status]?.color || 'default';
}

function getStatusLabel(status: string): string {
  return statusConfig[status]?.label || status;
}

// 组颜色映射
const groupColors: Record<string, string> = {
  control: 'blue',
  experiment_1: 'green',
  experiment_2: 'orange',
  experiment_3: 'purple',
  experiment_4: 'cyan',
};

function getGroupColor(groupName: string): string {
  if (groupColors[groupName]) return groupColors[groupName];
  const colors = ['green', 'orange', 'purple', 'cyan', 'magenta'];
  const index =
    (groupName.codePointAt(groupName.length - 1) ?? 0) % colors.length;
  return colors[index] || 'default';
}

function getGroupBorderColor(groupName: string): string {
  const colorMap: Record<string, string> = {
    blue: 'hsl(209, 100%, 50%)',
    green: 'hsl(142, 71%, 45%)',
    orange: 'hsl(24, 100%, 50%)',
    purple: 'hsl(270, 50%, 60%)',
    cyan: 'hsl(180, 100%, 40%)',
    magenta: 'hsl(300, 100%, 50%)',
  };
  const color = getGroupColor(groupName);
  return colorMap[color] || 'hsl(var(--border))';
}

// 获取 Agent 下的 Job 列表
async function fetchJobs() {
  loading.value = true;
  try {
    const jobs = await getJobListApi({ agent_code: props.agentCode });
    jobList.value = jobs || [];
  } catch (error: unknown) {
    console.error('获取 Job 列表失败:', error);
    message.error('获取 Job 列表失败');
  } finally {
    loading.value = false;
  }
}

// 重置表单
function resetForm() {
  formState.value = {
    test_name: '',
    job_ids: {
      control: '',
      experiment_1: '',
    },
    remark: '',
  };
  groupDescriptions.value = {
    control: '',
    experiment_1: '',
  };
  searchText.value = '';
}

// 提交
async function handleSubmit() {
  // 验证测试名称
  if (!formState.value.test_name.trim()) {
    message.warning('请输入测试名称');
    return;
  }

  // 验证至少有 2 个组被分配了 Job
  const assignedGroups = Object.entries(formState.value.job_ids).filter(
    ([_, jobId]) => jobId,
  );
  if (assignedGroups.length < 2) {
    message.warning('请至少选择 2 个 Job 分配到不同组');
    return;
  }

  submitting.value = true;
  try {
    // 构建请求数据
    const jobIds: Record<string, string> = {};
    const groups: ABTestApi.ABTestGroup[] = [];

    for (const [groupName, jobId] of assignedGroups) {
      jobIds[groupName] = jobId;
      const job = jobList.value.find((j) => j.job_id === jobId);
      groups.push({
        group_name: groupName,
        description: groupDescriptions.value[groupName] || job?.job_name,
        config_snapshot: {
          job_id: jobId,
          job_name: job?.job_name,
          article_count: job?.article_count,
          expert_config_code_list: job?.expert_config_code_list,
        },
      });
    }

    const request: ABTestApi.CreateJobTestRequest = {
      test_name: formState.value.test_name,
      job_ids: jobIds,
      groups,
      remark: formState.value.remark || undefined,
    };

    await ABTestApi.createJobTest(request);
    message.success('创建成功！请前往 AB 测试记录页面查看');
    emit('success');
    handleClose();
  } catch (error: unknown) {
    console.error('创建失败:', error);
    message.error((error as Error)?.message || '创建失败');
  } finally {
    submitting.value = false;
  }
}

// 关闭
function handleClose() {
  visible.value = false;
  resetForm();
}

// 监听打开状态
watch(visible, (newVal) => {
  if (newVal) {
    fetchJobs();
  }
});
</script>

<template>
  <Modal
    v-model:open="visible"
    title="创建 Job 对比测试"
    :width="900"
    :confirm-loading="submitting"
    @ok="handleSubmit"
    @cancel="handleClose"
  >
    <Form :label-col="{ span: 5 }" :wrapper-col="{ span: 18 }">
      <!-- 测试名称 -->
      <FormItem label="测试名称" required>
        <Input
          v-model:value="formState.test_name"
          placeholder="请输入测试名称（如：文章生成策略对比）"
        />
      </FormItem>

      <!-- Agent 信息 -->
      <FormItem label="所属 Agent">
        <Tag color="blue">{{ agentCode }}</Tag>
        <span v-if="agentName" class="ml-2 text-muted">{{ agentName }}</span>
      </FormItem>

      <!-- Job 选择与分组 -->
      <FormItem label="Job 分组" required>
        <Alert
          message="请将 Job 分配到不同的对比组（至少 2 个组，每组 1 个 Job）"
          type="info"
          show-icon
          class="mb-4"
        />

        <div class="job-groups-container">
          <!-- 可选 Job 列表 -->
          <div class="job-pool">
            <div class="panel-header">
              <span class="panel-title">可选 Job</span>
              <Badge :count="availableJobs.length" />
            </div>
            <div class="panel-search">
              <Input
                v-model:value="searchText"
                placeholder="搜索 Job..."
                allow-clear
              />
            </div>
            <div class="job-cards">
              <div
                v-for="job in filteredJobs"
                :key="job.job_id"
                class="job-card"
                :class="{ disabled: isJobAssigned(job.job_id) }"
              >
                <div class="job-card-header">
                  <span class="job-card-name">{{ job.job_name }}</span>
                  <Tag :color="getStatusColor(job.status)" size="small">
                    {{ getStatusLabel(job.status) }}
                  </Tag>
                </div>
                <div class="job-card-meta">
                  <code>{{ job.job_id }}</code>
                </div>
                <div class="job-card-info">
                  <span>目标: {{ job.article_count ?? '-' }} 篇</span>
                </div>
                <div class="job-card-actions">
                  <Select
                    v-if="!isJobAssigned(job.job_id)"
                    :value="undefined"
                    placeholder="分配到组"
                    size="small"
                    style="width: 120px"
                    @change="(val: string) => assignJobToGroup(job.job_id, val)"
                  >
                    <SelectOption
                      v-for="group in availableGroups"
                      :key="group"
                      :value="group"
                    >
                      {{ group }}
                    </SelectOption>
                  </Select>
                  <Tag v-else color="green" size="small"> 已分配 </Tag>
                </div>
              </div>
              <div v-if="filteredJobs.length === 0" class="empty-state">
                <span v-if="loading">加载中...</span>
                <span v-else-if="searchText">没有匹配的 Job</span>
                <span v-else>该 Agent 下没有 Job</span>
              </div>
            </div>
          </div>

          <!-- 已分组的 Job -->
          <div class="assigned-groups">
            <div class="panel-header">
              <span class="panel-title">对比组配置</span>
              <Button type="link" size="small" @click="addGroup">
                + 添加组
              </Button>
            </div>
            <div class="groups-list">
              <div
                v-for="(jobId, groupName) in formState.job_ids"
                :key="groupName"
                class="group-item"
                :style="{ borderColor: getGroupBorderColor(groupName) }"
              >
                <div class="group-header">
                  <Tag :color="getGroupColor(groupName)">
                    {{ groupName }}
                  </Tag>
                  <Button
                    v-if="groupName !== 'control'"
                    type="text"
                    size="small"
                    danger
                    @click="removeGroup(groupName)"
                  >
                    删除组
                  </Button>
                </div>
                <div v-if="jobId" class="group-job">
                  <div class="assigned-job">
                    <span class="job-name">{{ getJobName(jobId) }}</span>
                    <code class="job-id">{{ jobId }}</code>
                    <Button
                      type="text"
                      size="small"
                      danger
                      @click="unassignJob(groupName)"
                    >
                      移除
                    </Button>
                  </div>
                </div>
                <div v-else class="group-empty">
                  <span class="placeholder">请从左侧选择 Job</span>
                </div>
                <!-- 组描述输入 -->
                <div class="group-description">
                  <Input
                    v-model:value="groupDescriptions[groupName]"
                    placeholder="组描述（可选）"
                    size="small"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </FormItem>

      <!-- 备注 -->
      <FormItem label="备注">
        <Input.TextArea
          v-model:value="formState.remark"
          placeholder="请输入备注"
          :rows="2"
        />
      </FormItem>
    </Form>
  </Modal>
</template>

<style scoped>
.job-groups-container {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  min-height: 360px;
}

.job-pool,
.assigned-groups {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  background: hsl(var(--muted) / 30%);
  border-bottom: 1px solid hsl(var(--border));
}

.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.panel-search {
  padding: 10px 12px;
  border-bottom: 1px solid hsl(var(--border));
}

.job-cards {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  max-height: 320px;
  padding: 12px;
  overflow-y: auto;
}

.job-card {
  padding: 10px 12px;
  background: hsl(var(--background));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  transition: all 0.2s;
}

.job-card:hover:not(.disabled) {
  background: hsl(var(--muted) / 30%);
  border-color: hsl(var(--primary) / 50%);
}

.job-card.disabled {
  background: hsl(var(--muted) / 20%);
  opacity: 0.5;
}

.job-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.job-card-name {
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.job-card-meta {
  margin-bottom: 6px;
}

.job-card-meta code {
  padding: 2px 6px;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted));
  border-radius: 4px;
}

.job-card-info {
  margin-bottom: 8px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.job-card-actions {
  display: flex;
  justify-content: flex-end;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 80px;
  color: hsl(var(--muted-foreground));
}

.groups-list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 12px;
  max-height: 380px;
  padding: 12px;
  overflow-y: auto;
}

.group-item {
  padding: 12px;
  background: hsl(var(--background));
  border: 2px solid hsl(var(--border));
  border-left-width: 4px;
  border-radius: 10px;
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.group-job {
  margin-bottom: 10px;
}

.assigned-job {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  background: hsl(var(--muted) / 30%);
  border-radius: 6px;
}

.assigned-job .job-name {
  flex: 1;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.assigned-job .job-id {
  padding: 2px 6px;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted));
  border-radius: 4px;
}

.group-empty {
  padding: 16px;
  margin-bottom: 10px;
  text-align: center;
  background: hsl(var(--muted) / 15%);
  border: 1px dashed hsl(var(--border));
  border-radius: 6px;
}

.group-empty .placeholder {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.group-description {
  margin-top: 8px;
}

.text-muted {
  color: hsl(var(--muted-foreground));
}

.ml-2 {
  margin-left: 8px;
}

.mb-4 {
  margin-bottom: 16px;
}
</style>
