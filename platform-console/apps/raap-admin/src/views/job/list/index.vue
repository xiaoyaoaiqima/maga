<script setup lang="ts">
import type { JobApi } from '#/api/core/job';

import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { VbenIconButton } from '@vben-core/shadcn-ui';

import {
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  ExperimentOutlined,
  EyeOutlined,
  RocketOutlined,
} from '@ant-design/icons-vue';
import {
  Badge,
  Button,
  Card,
  Divider,
  Dropdown,
  Form,
  FormItem,
  Input,
  InputNumber,
  Menu,
  MenuItem,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import {
  completeJobApi,
  copyJobApi,
  deleteJobApi,
  deployJobApi,
  getExpertConfigApi,
  getJobListApi,
  pauseJobApi,
  resumeJobApi,
  testJobApi,
  updateJobApi,
} from '#/api/core/job';
import ExpertDetailModal from '#/components/expert-detail-modal/index.vue';
import { commonCronShortcuts, getCronDescription } from '#/utils/cron';

const router = useRouter();
const route = useRoute();
const loading = ref(false);
const dataSource = ref<JobApi.Job[]>([]);
const searchText = ref('');
const statusFilter = ref<string | undefined>(undefined);
const enabledFilter = ref<string | undefined>(undefined);
const sortByUpdate = ref<string>('desc');

// 批量选择
const selectedRowKeys = ref<string[]>([]);
const batchDeleteLoading = ref(false);
const pagination = ref({
  current: 1,
  pageSize: 10,
  showSizeChanger: true,
  showQuickJumper: true,
  showTotal: (total: number) => `共 ${total} 条`,
});

// 复制任务弹窗
const copyModalVisible = ref(false);
const copyModalLoading = ref(false);
const copyJobName = ref('');
const sourceJob = ref<JobApi.Job | null>(null);

// 状态配置
const statusConfig: Record<
  JobApi.JobStatus,
  {
    color: string;
    label: string;
    status: 'default' | 'error' | 'processing' | 'success' | 'warning';
  }
> = {
  NOT_DEPLOYED: { label: '未部署', color: 'default', status: 'default' },
  DEPLOYED: { label: '已部署', color: 'blue', status: 'processing' },
  RUNNING: { label: '运行中', color: 'green', status: 'success' },
  PAUSED: { label: '已暂停', color: 'orange', status: 'warning' },
  COMPLETED: { label: '已完成', color: 'red', status: 'error' },
};

const statusOptions = [
  { label: '未部署', value: 'NOT_DEPLOYED' },
  { label: '已部署', value: 'DEPLOYED' },
  { label: '运行中', value: 'RUNNING' },
  { label: '已暂停', value: 'PAUSED' },
  { label: '已完成', value: 'COMPLETED' },
];

const enabledOptions = [
  { label: '启用', value: 'true' },
  { label: '禁用', value: 'false' },
];

const sortByOptions = [
  { label: '最新在前', value: 'desc' },
  { label: '最早在前', value: 'asc' },
  { label: '默认排序', value: 'none' },
];

// 统计数据
const statistics = computed(() => {
  const total = dataSource.value.length;
  const completed = dataSource.value.filter(
    (j) => j.status === 'COMPLETED',
  ).length;
  const deployed = dataSource.value.filter(
    (j) => j.status === 'DEPLOYED',
  ).length;
  const notDeployed = dataSource.value.filter(
    (j) => j.status === 'NOT_DEPLOYED',
  ).length;
  return { total, completed, deployed, notDeployed };
});

const columns = [
  {
    title: 'Job 名称',
    dataIndex: 'job_name',
    key: 'job_name',
    width: 200,
    ellipsis: true,
    fixed: 'left' as const,
  },
  {
    title: '活动',
    dataIndex: 'activity_name',
    key: 'activity_name',
    width: 150,
    ellipsis: true,
  },
  {
    title: 'Agent',
    dataIndex: 'agent_name',
    key: 'agent_name',
    width: 150,
    ellipsis: true,
  },
  {
    title: '描述',
    dataIndex: 'description',
    key: 'description',
    ellipsis: true,
  },
  {
    title: 'Expert 配置',
    dataIndex: 'expert_config_code_list',
    key: 'expert_config_code_list',
    width: 280,
  },
  {
    title: '目标篇数',
    dataIndex: 'article_count',
    key: 'article_count',
    width: 100,
    align: 'center' as const,
  },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    width: 110,
  },
  {
    title: '启用',
    dataIndex: 'enabled',
    key: 'enabled',
    width: 80,
    align: 'center' as const,
  },
  {
    title: '更新时间',
    dataIndex: 'update_time',
    key: 'update_time',
    width: 170,
  },
  { title: '操作', key: 'action', width: 280, fixed: 'right' as const },
];

async function fetchJobs() {
  loading.value = true;
  try {
    const params: Record<string, any> = {};
    if (statusFilter.value) {
      params.status = statusFilter.value;
    }
    if (enabledFilter.value) {
      params.enabled = enabledFilter.value === 'true';
    }
    const response = await getJobListApi(params);
    dataSource.value = response || [];
  } catch (error) {
    console.error('获取 Job 列表失败:', error);
    message.error('获取 Job 列表失败');
  } finally {
    loading.value = false;
  }
}

// 切换启用状态
async function handleToggleEnabled(record: JobApi.Job) {
  try {
    await updateJobApi(record.job_id, { enabled: !record.enabled });
    message.success(record.enabled ? '已禁用' : '已启用');
    fetchJobs();
  } catch {
    message.error('操作失败');
  }
}

function handleCreate() {
  router.push('/job/create');
}

function handleViewExecution(record: JobApi.Job) {
  router.push(`/trace/job-execution/${record.job_id}`);
}

function handleEdit(record: JobApi.Job) {
  router.push(`/job/create?id=${record.job_id}`);
}

// 部署弹窗相关
const deployModalVisible = ref(false);
const deployingJob = ref<JobApi.Job | null>(null);
const deploying = ref(false);

interface TaskConfigForm {
  expert_config_code: string;
  cron_expression: string;
  misfire_policy: number;
  concurrent: number;
}

const taskConfigs = ref<TaskConfigForm[]>([]);

const misfirePolicyOptions = [
  { label: '立即执行', value: 1 },
  { label: '执行一次', value: 2 },
  { label: '放弃执行', value: 3 },
];

const concurrentOptions = [
  { label: '允许并发', value: 0 },
  { label: '禁止并发', value: 1 },
];

function openDeployModal(record: JobApi.Job) {
  deployingJob.value = record;
  // 初始化每个 expert 的配置
  taskConfigs.value = (record.expert_config_code_list || []).map((code) => ({
    expert_config_code: code,
    cron_expression: '* * * * * *',
    misfire_policy: 1,
    concurrent: 0,
  }));
  deployModalVisible.value = true;
}

// Dropdown 挂载到 body，避免被表格行覆盖
const getPopupContainerBody = () => document.body;

function closeDeployModal() {
  if (!deploying.value) {
    deployModalVisible.value = false;
    deployingJob.value = null;
    taskConfigs.value = [];
  }
}

async function handleDeploy() {
  if (!deployingJob.value) return;

  deploying.value = true;
  try {
    await deployJobApi(deployingJob.value.job_id, {
      task_configs: taskConfigs.value,
    });
    message.success('部署成功');
    deployModalVisible.value = false;
    fetchJobs();
  } catch (error: any) {
    message.error(`部署失败: ${error.message || '未知错误'}`);
  } finally {
    deploying.value = false;
  }
}

async function handleDelete(record: JobApi.Job) {
  try {
    await deleteJobApi(record.job_id);
    message.success('删除成功');
    fetchJobs();
  } catch {
    message.error('删除失败');
  }
}

// 批量删除
async function handleBatchDelete() {
  if (selectedRowKeys.value.length === 0) {
    message.warning('请先选择要删除的 Job');
    return;
  }

  Modal.confirm({
    title: '确认批量删除',
    content: `确定要删除选中的 ${selectedRowKeys.value.length} 个 Job 吗?此操作不可恢复!`,
    okText: '确定',
    cancelText: '取消',
    okButtonProps: { danger: true },
    onOk: async () => {
      batchDeleteLoading.value = true;
      try {
        // 循环调用单个删除 API
        const deletePromises = selectedRowKeys.value.map((jobId) =>
          deleteJobApi(jobId),
        );
        await Promise.all(deletePromises);

        message.success(`成功删除 ${selectedRowKeys.value.length} 个 Job`);
        selectedRowKeys.value = [];
        fetchJobs();
      } catch {
        message.error('批量删除失败');
      } finally {
        batchDeleteLoading.value = false;
      }
    },
  });
}

function handleCopy(record: JobApi.Job) {
  // 自动生成名称：agent_name_随机ID（与创建页面格式一致）
  const timestamp = Date.now().toString(36); // 36进制时间戳
  const random = Math.random().toString(36).slice(2, 6); // 4位随机数
  const uniqueId = `${timestamp}${random}`.toUpperCase();

  sourceJob.value = record;
  copyJobName.value = `${record.agent_name}_${uniqueId}`;
  copyModalVisible.value = true;
}

async function handleCopyConfirm() {
  if (!sourceJob.value || !copyJobName.value.trim()) {
    message.warning('请输入任务名称');
    return;
  }

  copyModalLoading.value = true;
  try {
    await copyJobApi(sourceJob.value.job_id, copyJobName.value.trim());
    message.success('复制成功');
    copyModalVisible.value = false;
    fetchJobs();
  } catch {
    message.error('复制失败');
  } finally {
    copyModalLoading.value = false;
  }
}

async function handlePause(record: JobApi.Job) {
  try {
    await pauseJobApi(record.job_id);
    message.success('已暂停 Job');
    fetchJobs();
  } catch (error: any) {
    message.error(`暂停失败: ${error.message || '未知错误'}`);
  }
}

async function handleResume(record: JobApi.Job) {
  try {
    await resumeJobApi(record.job_id);
    message.success('已恢复 Job');
    fetchJobs();
  } catch (error: any) {
    message.error(`恢复失败: ${error.message || '未知错误'}`);
  }
}

async function handleComplete(record: JobApi.Job) {
  try {
    await completeJobApi(record.job_id);
    message.success('已完成 Job');
    fetchJobs();
  } catch (error: any) {
    message.error(`操作失败: ${error.message || '未知错误'}`);
  }
}

// 快速测试相关
const testModalVisible = ref(false);
const testingJob = ref<JobApi.Job | null>(null);
const testing = ref(false);
const testProgress = ref(0);
const testResults = ref<Record<string, any>>({});
const testCompleted = ref(false);

// 测试参数配置
const testExecutionCount = ref(1);
const testExpertsDetails = ref<JobApi.ExpertConfigBrief[]>([]);
const testExpertsLoading = ref(false);
const testSelections = ref<Record<string, Record<string, string>>>({}); // expertCode -> varName -> contextName

function normalizeContextOptions(v: any): string[] {
  if (Array.isArray(v)) return v;
  if (typeof v === 'string') return [v];
  return [];
}

function getExpertVariables(expert: JobApi.ExpertConfigBrief) {
  const vars: Record<string, string[]> = {};
  if (expert.plugin_config) {
    for (const plugin of expert.plugin_config) {
      for (const [varName, options] of Object.entries(
        plugin.variable_mapping,
      )) {
        const normalized = normalizeContextOptions(options);
        vars[varName] = vars[varName]
          ? vars[varName].filter((o) => normalized.includes(o))
          : normalized;
      }
    }
  }
  return vars;
}

async function openTestModal(record: JobApi.Job) {
  testingJob.value = record;
  testResults.value = {};
  testProgress.value = 0;
  testCompleted.value = false;
  testExecutionCount.value = 1;
  testModalVisible.value = true;

  // 加载 Expert 详情以获取变量映射
  testExpertsLoading.value = true;
  testExpertsDetails.value = [];
  testSelections.value = {};
  try {
    const codes = record.expert_config_code_list || [];
    const details = await Promise.all(
      codes.map((code) => getExpertConfigApi(code)),
    );
    testExpertsDetails.value = details;

    // 初始化选择
    details.forEach((detail) => {
      testSelections.value[detail.expert_config_code] = {};
    });
  } catch (error) {
    console.error('获取 Expert 详情失败:', error);
    message.error('获取 Expert 详情失败');
  } finally {
    testExpertsLoading.value = false;
  }
}

async function handleQuickTest() {
  if (!testingJob.value) return;

  try {
    // 构建 experts_plugin_config_snapshot
    const experts_plugin_config_snapshot: Record<string, any> = {};

    for (const expert of testExpertsDetails.value) {
      const selections = testSelections.value[expert.expert_config_code] || {};
      const snapshotItems: any[] = [];

      if (expert.plugin_config) {
        for (const plugin of expert.plugin_config) {
          const mapping: Record<string, string> = {};
          let hasSelection = false;

          for (const varName of Object.keys(plugin.variable_mapping)) {
            if (selections[varName]) {
              mapping[varName] = selections[varName];
              hasSelection = true;
            }
          }

          if (hasSelection) {
            snapshotItems.push({
              plugin_code: plugin.plugin_code,
              variable_mapping: mapping,
            });
          }
        }
      }

      if (snapshotItems.length > 0) {
        experts_plugin_config_snapshot[expert.expert_config_code] =
          snapshotItems;
      }
    }

    const count = testExecutionCount.value || 1;

    // 发起测试请求（后端已改为全异步后台执行）
    await testJobApi(testingJob.value.job_id, {
      count,
      experts_plugin_config_snapshot,
    });

    message.success(
      count > 1 ? `已成功启动 ${count} 次后台测试执行` : '测试任务已在后台启动',
    );

    // 立即跳转至追踪页，不再在弹窗内等待
    router.push(`/trace/job-execution/${testingJob.value.job_id}`);
    testModalVisible.value = false;
  } catch (error: any) {
    message.error(`启动测试失败: ${error.message || '未知错误'}`);
  }
}

function closeTestModal() {
  if (!testing.value) {
    testModalVisible.value = false;
    testingJob.value = null;
  }
}

const filteredData = computed(() => {
  let result = dataSource.value;

  // 文本搜索
  if (searchText.value) {
    const search = searchText.value.toLowerCase();
    result = result.filter(
      (item) =>
        item.job_name.toLowerCase().includes(search) ||
        (item.description || '').toLowerCase().includes(search) ||
        item.job_id.toLowerCase().includes(search),
    );
  }

  // 按更新时间排序
  if (sortByUpdate.value && sortByUpdate.value !== 'none') {
    result = result.toSorted((a, b) => {
      const timeA = new Date(a.update_time || 0).getTime();
      const timeB = new Date(b.update_time || 0).getTime();
      return sortByUpdate.value === 'desc' ? timeB - timeA : timeA - timeB;
    });
  }

  return result;
});

function handleSearch() {
  fetchJobs();
}

function handleReset() {
  searchText.value = '';
  statusFilter.value = undefined;
  enabledFilter.value = undefined;
  sortByUpdate.value = 'desc';
  fetchJobs();
}

function handleTableChange(pag: any) {
  pagination.value.current = pag.current || 1;
  pagination.value.pageSize = pag.pageSize || pagination.value.pageSize;
}

// Expert 详情弹窗
const expertDetailVisible = ref(false);
const selectedExpertCode = ref<null | string>(null);

// Expert 列表弹窗（显示所有专家）
const expertListVisible = ref(false);
const expertList = ref<string[]>([]);

function openExpertDetail(expertCode: string) {
  selectedExpertCode.value = expertCode;
  expertDetailVisible.value = true;
}

function openExpertList(expertCodes: string[]) {
  expertList.value = expertCodes;
  expertListVisible.value = true;
}

onMounted(() => {
  fetchJobs();
});
</script>

<template>
  <div class="job-list-page">
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
          {{ route.meta.title || '任务列表' }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">名称/描述</span>
          <Input
            v-model:value="searchText"
            placeholder="搜索名称/描述..."
            style="width: 180px"
            allow-clear
            @press-enter="handleSearch"
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">状态</span>
          <Select
            v-model:value="statusFilter"
            :options="statusOptions"
            placeholder="状态筛选"
            style="width: 120px"
            allow-clear
            @change="fetchJobs"
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">启用</span>
          <Select
            v-model:value="enabledFilter"
            :options="enabledOptions"
            placeholder="启用筛选"
            style="width: 100px"
            allow-clear
            @change="fetchJobs"
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">排序</span>
          <Select
            v-model:value="sortByUpdate"
            :options="sortByOptions"
            placeholder="更新时间排序"
            style="width: 120px"
          />
        </div>
        <div class="filter-actions">
          <Button
            v-if="selectedRowKeys.length > 0"
            danger
            :loading="batchDeleteLoading"
            @click="handleBatchDelete"
          >
            <span class="btn-icon">🗑️</span>
            批量删除 ({{ selectedRowKeys.length }})
          </Button>
          <Button @click="handleReset">重置</Button>
          <Button type="primary" @click="handleCreate">
            <span class="btn-icon">➕</span> 创建任务
          </Button>
        </div>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-row">
      <Card class="stat-card" :bordered="false">
        <Statistic title="任务总数" :value="statistics.total">
          <template #prefix>
            <span class="stat-icon">📋</span>
          </template>
        </Statistic>
      </Card>
      <Card class="stat-card" :bordered="false">
        <Statistic
          title="已完成"
          :value="statistics.completed"
          :value-style="{ color: 'hsl(var(--success))' }"
        >
          <template #prefix>
            <span class="stat-icon">✅</span>
          </template>
        </Statistic>
      </Card>
      <Card class="stat-card" :bordered="false">
        <Statistic
          title="已部署"
          :value="statistics.deployed"
          :value-style="{ color: 'hsl(var(--primary))' }"
        >
          <template #prefix>
            <span class="stat-icon">🚀</span>
          </template>
        </Statistic>
      </Card>
      <Card class="stat-card" :bordered="false">
        <Statistic
          title="待部署"
          :value="statistics.notDeployed"
          :value-style="{ color: 'hsl(var(--muted-foreground))' }"
        >
          <template #prefix>
            <span class="stat-icon">⏳</span>
          </template>
        </Statistic>
      </Card>
    </div>

    <Card :bordered="false">
      <Table
        :columns="columns"
        :data-source="filteredData"
        :loading="loading"
        :locale="{ emptyText: '暂无 Job 任务，点击右上角创建' }"
        :pagination="pagination"
        :row-selection="{
          selectedRowKeys,
          onChange: (keys: string[]) => {
            selectedRowKeys = keys;
          },
        }"
        :scroll="{ x: 1400 }"
        row-key="job_id"
        size="middle"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record: rawRecord }">
          <template v-if="column.key === 'job_name'">
            <Tooltip
              :title="(rawRecord as JobApi.Job).job_name"
              :overlay-style="{ maxWidth: '400px' }"
            >
              <a
                class="job-name-link"
                @click="handleViewExecution(rawRecord as JobApi.Job)"
              >
                {{ (rawRecord as JobApi.Job).job_name }}
              </a>
            </Tooltip>
          </template>
          <template v-else-if="column.key === 'expert_config_code_list'">
            <Space wrap :size="4">
              <Tag
                v-for="code in (
                  (rawRecord as JobApi.Job).expert_config_code_list || []
                ).slice(0, 3)"
                :key="code"
                color="blue"
                style="cursor: pointer"
                @click="openExpertDetail(code)"
              >
                {{ code }}
              </Tag>
              <Tag
                v-if="
                  ((rawRecord as JobApi.Job).expert_config_code_list || [])
                    .length > 3
                "
                color="default"
                style="cursor: pointer"
                @click="
                  openExpertList(
                    (rawRecord as JobApi.Job).expert_config_code_list || [],
                  )
                "
              >
                +{{
                  ((rawRecord as JobApi.Job).expert_config_code_list || [])
                    .length - 3
                }}
              </Tag>
            </Space>
          </template>
          <template v-else-if="column.key === 'article_count'">
            <span class="article-count">
              {{ (rawRecord as JobApi.Job).article_count ?? '-' }}
            </span>
          </template>
          <template v-else-if="column.key === 'status'">
            <Badge
              :status="
                statusConfig[(rawRecord as JobApi.Job).status]?.status ||
                'default'
              "
              :text="
                statusConfig[(rawRecord as JobApi.Job).status]?.label ||
                (rawRecord as JobApi.Job).status
              "
            />
          </template>
          <template v-else-if="column.key === 'enabled'">
            <Tooltip
              :title="
                (rawRecord as JobApi.Job).enabled ? '点击禁用' : '点击启用'
              "
            >
              <Tag
                :color="
                  (rawRecord as JobApi.Job).enabled ? 'success' : 'default'
                "
                class="toggle-tag"
                @click="handleToggleEnabled(rawRecord as JobApi.Job)"
              >
                {{ (rawRecord as JobApi.Job).enabled ? '启用' : '禁用' }}
              </Tag>
            </Tooltip>
          </template>
          <template v-else-if="column.key === 'action'">
            <div class="action-buttons">
              <VbenIconButton
                tooltip="查看执行详情"
                class="action-btn"
                @click="() => handleViewExecution(rawRecord as JobApi.Job)"
              >
                <EyeOutlined />
              </VbenIconButton>
              <VbenIconButton
                tooltip="编辑"
                class="action-btn"
                @click="() => handleEdit(rawRecord as JobApi.Job)"
              >
                <EditOutlined />
              </VbenIconButton>
              <VbenIconButton
                tooltip="快速测试"
                class="action-btn action-btn-info"
                @click="() => openTestModal(rawRecord as JobApi.Job)"
              >
                <ExperimentOutlined />
              </VbenIconButton>
              <template
                v-if="(rawRecord as JobApi.Job).status === 'NOT_DEPLOYED'"
              >
                <VbenIconButton
                  tooltip="部署"
                  class="action-btn action-btn-success"
                  @click="openDeployModal(rawRecord as JobApi.Job)"
                >
                  <RocketOutlined />
                </VbenIconButton>
              </template>
              <template
                v-else-if="
                  ['DEPLOYED', 'PAUSED', 'RUNNING'].includes(
                    (rawRecord as JobApi.Job).status,
                  )
                "
              >
                <Dropdown
                  :trigger="['click']"
                  placement="bottomLeft"
                  :get-popup-container="getPopupContainerBody"
                >
                  <VbenIconButton
                    class="action-btn action-btn-success"
                    tooltip="操作"
                  >
                    <RocketOutlined />
                  </VbenIconButton>
                  <template #overlay>
                    <Menu>
                      <MenuItem
                        v-if="(rawRecord as JobApi.Job).status === 'PAUSED'"
                        @click="handleResume(rawRecord as JobApi.Job)"
                      >
                        恢复
                      </MenuItem>
                      <MenuItem
                        v-else
                        @click="handlePause(rawRecord as JobApi.Job)"
                      >
                        暂停
                      </MenuItem>
                      <MenuItem
                        @click="handleComplete(rawRecord as JobApi.Job)"
                      >
                        完成
                      </MenuItem>
                    </Menu>
                  </template>
                </Dropdown>
              </template>
              <template v-else>
                <VbenIconButton
                  tooltip="已停止/已完成"
                  class="action-btn"
                  disabled
                >
                  <RocketOutlined />
                </VbenIconButton>
              </template>
              <VbenIconButton
                tooltip="复制"
                class="action-btn"
                @click="() => handleCopy(rawRecord as JobApi.Job)"
              >
                <CopyOutlined />
              </VbenIconButton>
              <Popconfirm
                title="确定要删除此 Job 吗？"
                ok-text="确定"
                cancel-text="取消"
                @confirm="handleDelete(rawRecord as JobApi.Job)"
                :get-popup-container="getPopupContainerBody"
              >
                <VbenIconButton
                  tooltip="删除"
                  class="action-btn action-btn-danger"
                >
                  <DeleteOutlined />
                </VbenIconButton>
              </Popconfirm>
            </div>
          </template>
        </template>
      </Table>
    </Card>

    <!-- 部署配置弹窗 -->
    <Modal
      v-model:open="deployModalVisible"
      :title="`🚀 部署配置: ${deployingJob?.job_name || ''}`"
      :width="700"
      :mask-closable="!deploying"
      :closable="!deploying"
      @cancel="closeDeployModal"
    >
      <div class="deploy-modal-content">
        <div class="deploy-info">
          <p class="deploy-tip">请为每个 Expert 配置调度参数：</p>
        </div>

        <div class="task-config-list">
          <div
            v-for="(config, index) in taskConfigs"
            :key="config.expert_config_code"
            class="task-config-item"
          >
            <div class="task-config-header">
              <Tag color="blue">{{ index + 1 }}</Tag>
              <code class="expert-code">{{ config.expert_config_code }}</code>
            </div>
            <Form layout="vertical" class="task-config-form">
              <div class="form-row">
                <FormItem label="执行频率 (Cron)" class="form-item-cron">
                  <div class="cron-input-wrapper">
                    <Input
                      v-model:value="config.cron_expression"
                      placeholder="例如: 0 0 0 * * *"
                      class="cron-input"
                    />
                    <div class="cron-shortcuts">
                      <Tag
                        v-for="item in commonCronShortcuts"
                        :key="item.value"
                        class="cron-shortcut-tag"
                        @click="config.cron_expression = item.value"
                      >
                        {{ item.label }}
                      </Tag>
                    </div>
                  </div>
                  <div class="form-hint cron-hint">
                    <div class="cron-desc">
                      {{ getCronDescription(config.cron_expression) }}
                    </div>
                    <div class="cron-format-guide">
                      格式: <code>秒 分 时 日 月 周</code> (支持6位)
                    </div>
                  </div>
                </FormItem>
              </div>
              <div class="form-row">
                <FormItem label="错误处理策略" class="form-item-half">
                  <Select
                    v-model:value="config.misfire_policy"
                    :options="misfirePolicyOptions"
                    style="width: 100%"
                    :get-popup-container="(trigger) => trigger.parentElement"
                  />
                </FormItem>
                <FormItem label="并发设置" class="form-item-half">
                  <Select
                    v-model:value="config.concurrent"
                    :options="concurrentOptions"
                    style="width: 100%"
                    :get-popup-container="(trigger) => trigger.parentElement"
                  />
                </FormItem>
              </div>
            </Form>
          </div>
        </div>
      </div>

      <template #footer>
        <Space>
          <Button :disabled="deploying" @click="closeDeployModal">取消</Button>
          <Button type="primary" :loading="deploying" @click="handleDeploy">
            {{ deploying ? '部署中...' : '确认部署' }}
          </Button>
        </Space>
      </template>
    </Modal>

    <!-- 快速测试弹窗 -->
    <Modal
      v-model:open="testModalVisible"
      :title="`🧪 测试: ${testingJob?.job_name || ''}`"
      :width="700"
      :footer="null"
      :mask-closable="!testing"
      :closable="!testing"
      @cancel="closeTestModal"
    >
      <div class="test-modal-content">
        <!-- 测试信息与参数配置 -->
        <div v-if="testingJob && !testCompleted" class="test-info">
          <div class="test-info-item">
            <span class="label">Job ID:</span>
            <code>{{ testingJob.job_id }}</code>
          </div>

          <div class="test-info-item" style="align-items: center">
            <span class="label">执行次数:</span>
            <InputNumber
              v-model:value="testExecutionCount"
              :min="1"
              :max="50"
              style="width: 120px"
            />
            <span class="execution-hint">
              (默认 1 次，执行后自动跳转至追踪页查看进度)
            </span>
          </div>

          <Divider dashed style="margin: 16px 0" />

          <div class="test-experts-config">
            <div
              v-if="testExpertsLoading"
              style="padding: 20px; text-align: center"
            >
              <Spin tip="加载 Expert 变量配置..." />
            </div>
            <div v-else class="expert-config-list">
              <div
                v-for="(expert, idx) in testExpertsDetails"
                :key="expert.expert_config_code"
                class="expert-config-item"
              >
                <div class="expert-config-header">
                  <Tag color="blue" class="expert-idx">{{ idx + 1 }}</Tag>
                  <span class="expert-name">{{
                    expert.expert_config_name
                  }}</span>
                  <code class="expert-code-text">{{
                    expert.expert_config_code
                  }}</code>
                  <Tag color="orange" v-if="expert.expert_type" size="small">
                    {{ expert.expert_type }}
                  </Tag>
                </div>

                <div class="expert-variables">
                  <div
                    v-if="
                      !expert.plugin_config || expert.plugin_config.length === 0
                    "
                    class="no-vars"
                  >
                    <span class="muted-text">无变量配置</span>
                  </div>
                  <div v-else class="variable-list">
                    <div
                      v-for="(options, varName) in getExpertVariables(expert)"
                      :key="varName"
                      class="variable-item"
                    >
                      <span class="var-name">{{ varName }}</span>
                      <Select
                        v-model:value="
                          testSelections[expert.expert_config_code][varName]
                        "
                        placeholder="不选=随机"
                        allow-clear
                        style="width: 100%"
                        size="small"
                      >
                        <Select.Option
                          v-for="opt in options"
                          :key="opt"
                          :value="opt"
                        >
                          {{ opt }}
                        </Select.Option>
                      </Select>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 执行按钮 -->
        <div v-if="!testing && !testCompleted" class="test-actions">
          <Button type="primary" size="large" @click="handleQuickTest">
            🚀 开始测试
          </Button>
        </div>
      </div>
    </Modal>

    <!-- 复制任务弹窗 -->
    <Modal
      v-model:open="copyModalVisible"
      title="复制任务"
      :width="400"
      :confirm-loading="copyModalLoading"
      @ok="handleCopyConfirm"
    >
      <div class="copy-modal-content">
        <FormItem label="原任务名称">
          <Input :value="sourceJob?.job_name" disabled />
        </FormItem>
        <FormItem label="新任务名称" required>
          <Input
            v-model:value="copyJobName"
            placeholder="请输入新任务名称"
            :maxlength="100"
            show-count
          />
        </FormItem>
      </div>
    </Modal>

    <!-- Expert 详情弹窗 -->
    <ExpertDetailModal
      v-model:open="expertDetailVisible"
      :expert-code="selectedExpertCode"
    />

    <!-- Expert 列表弹窗 -->
    <Modal
      v-model:open="expertListVisible"
      title="Expert 配置列表"
      :width="600"
      :footer="null"
    >
      <div class="expert-list-content">
        <div
          v-for="(code, index) in expertList"
          :key="code"
          class="expert-list-item"
        >
          <div class="expert-index">{{ index + 1 }}</div>
          <Tag
            color="blue"
            style="flex: 1; cursor: pointer"
            @click="
              expertListVisible = false;
              openExpertDetail(code);
            "
          >
            {{ code }}
          </Tag>
        </div>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.job-list-page {
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

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.stat-card {
  background: hsl(var(--card));
  border-radius: 12px;
  transition: all 0.2s;
}

.stat-card:hover {
  box-shadow: 0 4px 12px hsl(var(--foreground) / 8%);
}

.stat-icon {
  margin-right: 4px;
}

.search-icon {
  opacity: 0.6;
}

.btn-icon {
  margin-right: 4px;
}

.toggle-tag {
  cursor: pointer;
  transition: all 0.2s;
}

.toggle-tag:hover {
  transform: scale(1.05);
}

.job-name-link {
  font-weight: 500;
  color: hsl(var(--primary));
  cursor: pointer;
}

.job-name-link:hover {
  text-decoration: underline;
}

.article-count {
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-weight: 500;
}

:deep(.ant-table-thead > tr > th) {
  background: hsl(var(--muted));
}

:deep(.ant-card-head) {
  border-bottom: 1px solid hsl(var(--border));
}

/* 测试弹窗样式 */
.test-modal-content {
  padding: 8px 0;
}

.test-info {
  padding: 16px;
  margin-bottom: 16px;
  background: hsl(var(--muted) / 20%);
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
}

.test-info-item {
  display: flex;
  align-items: flex-start;
  margin-bottom: 12px;
}

.test-info-item:last-child {
  margin-bottom: 0;
}

.test-info-item .label {
  flex-shrink: 0;
  min-width: 80px;
  font-size: 14px;
  color: hsl(var(--muted-foreground));
}

.test-info-item code {
  padding: 2px 8px;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 13px;
  background: hsl(var(--muted));
  border-radius: 4px;
}

.execution-hint {
  margin-left: 12px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.test-experts-config {
  max-height: 400px;
  padding-right: 4px;
  overflow-y: auto;
}

.expert-config-item {
  padding: 12px;
  margin-bottom: 16px;
  background: hsl(var(--background));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.expert-config-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}

.expert-idx {
  font-weight: 600;
}

.expert-name {
  font-size: 14px;
  font-weight: 500;
}

.expert-code-text {
  padding: 1px 4px;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted));
  border-radius: 4px;
}

.variable-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.variable-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.var-name {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.no-vars {
  padding: 8px;
  text-align: center;
}

.muted-text {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.test-actions {
  display: flex;
  justify-content: center;
  padding: 16px 0 8px;
}

.test-progress {
  padding: 24px;
  background: hsl(var(--muted) / 30%);
  border-radius: 8px;
}

.progress-header {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
}

.progress-text {
  font-size: 14px;
  color: hsl(var(--foreground));
}

.test-results {
  margin-top: 16px;
}

.results-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-bottom: 16px;
  margin-bottom: 16px;
  border-bottom: 1px solid hsl(var(--border));
}

.result-tag {
  font-size: 13px;
}

.results-detail {
  max-height: 300px;
  overflow-y: auto;
}

.result-item {
  padding: 12px;
  margin-bottom: 8px;
  background: hsl(var(--muted) / 30%);
  border-radius: 8px;
}

.result-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.result-header code {
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 12px;
}

.success-icon {
  color: hsl(var(--success));
}

.error-icon {
  color: hsl(var(--destructive));
}

.result-error {
  padding: 8px 12px;
  font-size: 13px;
  color: hsl(var(--destructive));
  background: hsl(var(--destructive) / 10%);
  border-radius: 4px;
}

.result-content {
  max-height: 400px;
  overflow-y: auto;
  border-radius: 4px;
}

.result-json {
  padding: 12px;
  margin: 0;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 12px;
  line-height: 1.5;
  color: hsl(var(--foreground));
  word-break: break-all;
  overflow-wrap: break-word;
  white-space: pre-wrap;
  background: hsl(var(--muted) / 30%);
  border-radius: 4px;
}

.results-actions {
  display: flex;
  justify-content: flex-end;
  padding-top: 16px;
  margin-top: 16px;
  border-top: 1px solid hsl(var(--border));
}

/* 部署弹窗样式 */
.deploy-modal-content {
  padding: 8px 0;
}

.deploy-info {
  margin-bottom: 16px;
}

.deploy-tip {
  margin: 0;
  font-size: 14px;
  color: hsl(var(--muted-foreground));
}

.task-config-list {
  max-height: 400px;
  overflow-y: auto;
}

.task-config-item {
  padding: 16px;
  margin-bottom: 12px;
  background: hsl(var(--muted) / 30%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.task-config-item:last-child {
  margin-bottom: 0;
}

.task-config-header {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
}

.expert-code {
  padding: 4px 8px;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 13px;
  background: hsl(var(--muted));
  border-radius: 4px;
}

.task-config-form {
  margin-bottom: 0;
}

.form-row {
  display: flex;
  gap: 16px;
}

.form-item-cron {
  flex: 1;
}

.cron-input-wrapper {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cron-shortcuts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.cron-shortcut-tag {
  cursor: pointer;
  transition: all 0.2s;
}

.cron-shortcut-tag:hover {
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 10%);
  border-color: hsl(var(--primary));
}

.cron-hint {
  padding: 8px 12px;
  margin-top: 8px;
  background: hsl(var(--card));
  border: 1px dashed hsl(var(--border));
  border-radius: 6px;
}

.cron-desc {
  margin-bottom: 4px;
  font-weight: 500;
  color: hsl(var(--primary));
}

.cron-format-guide {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.cron-format-guide code {
  padding: 2px 4px;
  background: hsl(var(--muted));
  border-radius: 3px;
}

.form-item-half {
  flex: 1;
}

.form-hint {
  margin-top: 4px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

:deep(.task-config-form .ant-form-item) {
  margin-bottom: 12px;
}

:deep(.task-config-form .ant-form-item:last-child) {
  margin-bottom: 0;
}

.copy-modal-content {
  padding: 16px 0;
}

.copy-tip {
  margin-bottom: 12px;
  font-size: 14px;
  color: hsl(var(--foreground));
}

/* Expert 列表弹窗样式 */
.expert-list-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 400px;
  overflow-y: auto;
}

.expert-list-item {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 8px 12px;
  background: hsl(var(--muted) / 20%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  transition: all 0.2s;
}

.expert-list-item:hover {
  background: hsl(var(--muted) / 30%);
  border-color: hsl(var(--primary) / 50%);
}

.expert-index {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  font-size: 13px;
  font-weight: 600;
  color: hsl(var(--primary-foreground));
  background: hsl(var(--primary));
  border-radius: 50%;
}

/* 操作按钮样式 */
.action-buttons {
  display: flex;
  gap: 4px;
}

.action-btn {
  font-size: 15px;
}

.action-btn-success {
  color: #52c41a !important;
}

.action-btn-info {
  color: #1890ff !important;
}

.action-btn-danger {
  color: hsl(var(--destructive)) !important;
}

.action-btn-danger:hover {
  background: hsl(var(--destructive) / 15%) !important;
}

.rocket-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  font-size: 15px;
  cursor: pointer;
  border-radius: 50%;
  transition: all 0.2s;
}

.rocket-trigger:hover {
  background: hsl(var(--accent));
}
</style>
