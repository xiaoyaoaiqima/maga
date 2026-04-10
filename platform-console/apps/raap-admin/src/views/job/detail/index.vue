<script setup lang="ts">
import type { JobApi } from '#/api/core/job';

import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import {
  Alert,
  Badge,
  Button,
  Card,
  Collapse,
  CollapsePanel,
  Descriptions,
  DescriptionsItem,
  Dropdown,
  Menu,
  MenuItem,
  message,
  Modal,
  Select,
  Space,
  Spin,
  Switch,
  Table,
  TabPane,
  Tabs,
  Tag,
  Timeline,
  TimelineItem,
  Tooltip,
} from 'ant-design-vue';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';

import {
  completeJobApi,
  deployJobApi,
  getExpertConfigApi,
  getJobApi,
  getJobExpertTasksApi,
  pauseJobApi,
  resumeJobApi,
  testJobApi,
  updateExpertTaskApi,
  updateJobApi,
} from '#/api/core/job';
import { requestClient } from '#/api/request';

import 'dayjs/locale/zh-cn';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

// PluginContext 选项接口
interface PluginContextOption {
  id: number;
  context_name: string;
  context_content: string;
  variable_name: string;
  plugin_code: string;
}

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

const router = useRouter();
const route = useRoute();
const loading = ref(false);
const job = ref<JobApi.Job | null>(null);
const expertTasks = ref<JobApi.ExpertTask[]>([]);
const expertConfigs = ref<Map<string, JobApi.ExpertConfigBrief>>(new Map());

// 测试相关
const testModalVisible = ref(false);
const testing = ref(false);
const testProgress = ref(0);
const currentTestingExpert = ref('');
const testResults = ref<Record<string, JobApi.ExpertTestResult>>({});
const testCompleted = ref(false);
const testExecutionCount = ref(1); // 新增：测试执行次数

// 配置覆盖相关
const enableConfigOverride = ref(false);
const pluginContextOptions = ref<Map<string, PluginContextOption[]>>(new Map());
const configOverride = ref<
  Record<string, Record<string, Record<string, string>>>
>({});
const loadingPluginContexts = ref(false);

// 获取所有 PluginContext 选项（按 variable_name 分组）
async function fetchPluginContextOptions() {
  if (pluginContextOptions.value.size > 0) return;

  loadingPluginContexts.value = true;
  try {
    const response = await requestClient.get<PluginContextOption[]>(
      '/v1/plugin-contexts',
    );
    const contexts = response || [];

    // 按 variable_name 分组
    const grouped = new Map<string, PluginContextOption[]>();
    contexts.forEach((ctx) => {
      const key = `${ctx.plugin_code}:${ctx.variable_name}`;
      if (!grouped.has(key)) {
        grouped.set(key, []);
      }
      grouped.get(key)!.push(ctx);
    });
    pluginContextOptions.value = grouped;
  } catch (error) {
    console.error('获取 PluginContext 失败:', error);
  } finally {
    loadingPluginContexts.value = false;
  }
}

// 获取某个 ExpertConfig 的 plugin_config 中的变量
function getExpertPluginVariables(expertCode: string): Array<{
  currentValue: string;
  pluginCode: string;
  variableName: string;
}> {
  const config = expertConfigs.value.get(expertCode);
  if (!config?.plugin_config) return [];

  const variables: Array<{
    currentValue: string;
    pluginCode: string;
    variableName: string;
  }> = [];

  Object.entries(config.plugin_config).forEach(([pluginCode, pluginVars]) => {
    Object.entries(pluginVars).forEach(([variableName, contextNames]) => {
      const currentValue = Array.isArray(contextNames)
        ? contextNames[0] || ''
        : '';
      variables.push({
        pluginCode,
        variableName,
        currentValue,
      });
    });
  });

  return variables;
}

// 获取变量的可选 context 列表
function getContextOptionsForVariable(
  pluginCode: string,
  variableName: string,
): PluginContextOption[] {
  const key = `${pluginCode}:${variableName}`;
  return pluginContextOptions.value.get(key) || [];
}

// 更新配置覆盖
function updateConfigOverride(
  expertCode: string,
  pluginCode: string,
  variableName: string,
  contextName: string | undefined,
) {
  if (!configOverride.value[expertCode]) {
    configOverride.value[expertCode] = {};
  }
  if (!configOverride.value[expertCode]![pluginCode]) {
    configOverride.value[expertCode]![pluginCode] = {};
  }
  if (contextName) {
    configOverride.value[expertCode]![pluginCode]![variableName] = contextName;
  } else {
    delete configOverride.value[expertCode]![pluginCode]![variableName];
  }
}

// 初始化配置覆盖默认值
function initConfigOverride() {
  if (!job.value) return;

  configOverride.value = {};
  job.value.expert_config_code_list.forEach((expertCode) => {
    const variables = getExpertPluginVariables(expertCode);
    variables.forEach((v) => {
      updateConfigOverride(
        expertCode,
        v.pluginCode,
        v.variableName,
        v.currentValue,
      );
    });
  });
}

// 监听配置覆盖开关
watch(enableConfigOverride, async (enabled) => {
  if (enabled) {
    await fetchPluginContextOptions();
    initConfigOverride();
  }
});

// 获取 Job 详情
async function fetchJobDetail() {
  const jobId = route.params.id as string;
  if (!jobId) {
    message.error('缺少 Job ID');
    router.push('/job/list');
    return;
  }

  loading.value = true;
  try {
    const [jobData, tasksData] = await Promise.all([
      getJobApi(jobId),
      getJobExpertTasksApi(jobId),
    ]);
    job.value = jobData;
    expertTasks.value = tasksData || [];

    // 获取每个 ExpertConfig 的详细信息
    if (jobData.expert_config_code_list) {
      const configPromises = jobData.expert_config_code_list.map((code) =>
        getExpertConfigApi(code).catch(() => null),
      );
      const configs = await Promise.all(configPromises);
      configs.forEach((config, index) => {
        if (config) {
          expertConfigs.value.set(
            jobData.expert_config_code_list[index]!,
            config,
          );
        }
      });
    }
  } catch {
    message.error('获取 Job 详情失败');
    router.push('/job/list');
  } finally {
    loading.value = false;
  }
}

// 编辑
function handleEdit() {
  router.push(`/job/create?id=${route.params.id}`);
}

// 返回列表
function handleBack() {
  router.push('/job/list');
}

// 部署
async function handleDeploy() {
  if (!job.value) return;
  try {
    await deployJobApi(job.value.job_id, { task_configs: [] });
    message.success('部署成功');
    fetchJobDetail();
  } catch {
    message.error('部署失败');
  }
}

// 暂停 Job
async function handlePause() {
  if (!job.value) return;
  try {
    await pauseJobApi(job.value.job_id);
    message.success('已暂停 Job');
    fetchJobDetail();
  } catch (error: any) {
    message.error(`暂停失败: ${error.message || '未知错误'}`);
  }
}

// 恢复 Job
async function handleResume() {
  if (!job.value) return;
  try {
    await resumeJobApi(job.value.job_id);
    message.success('已恢复 Job');
    fetchJobDetail();
  } catch (error: any) {
    message.error(`恢复失败: ${error.message || '未知错误'}`);
  }
}

// 完成 Job
async function handleComplete() {
  if (!job.value) return;
  try {
    await completeJobApi(job.value.job_id);
    message.success('已完成 Job');
    fetchJobDetail();
  } catch (error: any) {
    message.error(`操作失败: ${error.message || '未知错误'}`);
  }
}

// 打开测试弹窗
function openTestModal() {
  testResults.value = {};
  testProgress.value = 0;
  currentTestingExpert.value = '';
  testCompleted.value = false;
  testExecutionCount.value = 1; // 重置次数
  testModalVisible.value = true;
}

// 执行测试
async function handleTest() {
  if (!job.value) return;

  try {
    // 构建测试请求参数
    const testRequest: JobApi.TestRequest = {};
    if (
      enableConfigOverride.value &&
      Object.keys(configOverride.value).length > 0
    ) {
      const snapshot: Record<string, JobApi.PluginConfigSnapshotItem[]> = {};
      Object.entries(configOverride.value).forEach(
        ([expertCode, pluginMap]) => {
          snapshot[expertCode] = Object.entries(pluginMap).map(
            ([pluginCode, varMap]) => ({
              plugin_code: pluginCode,
              variable_mapping: varMap,
            }),
          );
        },
      );
      testRequest.experts_plugin_config_snapshot = snapshot;
    }

    const count = testExecutionCount.value || 1;

    // 发起测试请求（后端已改为全异步后台执行）
    await testJobApi(job.value.job_id, {
      count,
      experts_plugin_config_snapshot:
        testRequest.experts_plugin_config_snapshot,
    });

    message.success(
      count > 1 ? `已成功启动 ${count} 次后台测试执行` : '测试任务已在后台启动',
    );

    // 立即跳转至追踪页，不再在弹窗内等待
    router.push(`/trace/job-execution/${job.value.job_id}`);
    testModalVisible.value = false;
  } catch (error: any) {
    message.error(`启动测试失败: ${error.message || '未知错误'}`);
  }
}

// 切换 Job 启用状态
async function handleToggleEnabled() {
  if (!job.value) return;
  try {
    await updateJobApi(job.value.job_id, { enabled: !job.value.enabled });
    message.success(job.value.enabled ? '已禁用' : '已启用');
    fetchJobDetail();
  } catch {
    message.error('操作失败');
  }
}

// Expert 表格列
const expertColumns = [
  {
    title: '执行顺序',
    key: 'order',
    width: 100,
    align: 'center' as const,
  },
  {
    title: 'Expert 编码',
    dataIndex: 'code',
    key: 'code',
    width: 180,
  },
  {
    title: 'Expert 名称',
    key: 'name',
    ellipsis: true,
  },
  {
    title: '类型',
    key: 'type',
    width: 120,
  },
  {
    title: '模型',
    key: 'model',
    width: 150,
  },
  {
    title: '状态',
    key: 'status',
    width: 80,
  },
];

// Expert 表格数据
const expertTableData = computed(() => {
  if (!job.value?.expert_config_code_list) return [];
  return job.value.expert_config_code_list.map((code, index) => {
    const config = expertConfigs.value.get(code);
    return {
      key: code,
      order: index + 1,
      code,
      name: config?.expert_config_name || '-',
      type: config?.expert_type || '-',
      model: config?.model_code || '-',
      enabled: config?.enabled ?? true,
      description: config?.description,
    };
  });
});

// ExpertTask 表格列
const taskColumns = [
  { title: 'ID', dataIndex: 'id', key: 'id', width: 80 },
  {
    title: 'Expert 编码',
    dataIndex: 'expert_config_code',
    key: 'expert_config_code',
  },
  {
    title: 'Cron 表达式',
    dataIndex: 'cron_expression',
    key: 'cron_expression',
  },
  { title: '状态', key: 'status', width: 120 },
  {
    title: '创建时间',
    dataIndex: 'create_time',
    key: 'create_time',
    width: 170,
  },
  { title: '操作', key: 'action', width: 120, fixed: 'right' as const },
];

// ExpertTask 状态配置
const taskStatusConfig: Record<number, { color: string; label: string }> = {
  0: { label: '待执行', color: 'default' },
  1: { label: '执行中', color: 'processing' },
  2: { label: '已暂停', color: 'warning' },
  3: { label: '已完成', color: 'success' },
};

// 切换 ExpertTask 状态
async function handleToggleTaskStatus(task: JobApi.ExpertTask) {
  // 0: 待执行 -> 1: 执行中, 1: 执行中 -> 2: 暂停, 2: 暂停 -> 1: 执行中
  const newStatus = task.status === 1 ? 2 : 1;
  try {
    await updateExpertTaskApi(task.id, { status: newStatus });
    message.success(newStatus === 1 ? '已启动任务' : '已暂停任务');
    fetchJobDetail();
  } catch {
    message.error('操作失败');
  }
}

// 复制到剪贴板
async function copyToClipboard(text: string, label = '内容') {
  try {
    await navigator.clipboard.writeText(text);
    message.success(`${label}已复制`);
  } catch {
    message.error('复制失败');
  }
}

// 格式化时间（带相对时间）
function formatTimeWithRelative(time: string | undefined) {
  if (!time) return { display: '-', relative: '' };
  const d = dayjs(time);
  return {
    display: d.format('YYYY-MM-DD HH:mm:ss'),
    relative: d.fromNow(),
  };
}

onMounted(() => {
  fetchJobDetail();
});
</script>

<template>
  <div class="job-detail-page">
    <Spin :spinning="loading">
      <Card :bordered="false">
        <template #title>
          <Space>
            <Button type="text" @click="handleBack">
              <span class="back-icon">⬅️</span>
            </Button>
            <span class="page-title">任务详情</span>
            <Badge
              v-if="job"
              :status="statusConfig[job.status]?.status || 'default'"
              :text="statusConfig[job.status]?.label || job.status"
            />
          </Space>
        </template>
        <template #extra>
          <Space>
            <Tooltip :title="job?.enabled ? '点击禁用' : '点击启用'">
              <Button
                :type="job?.enabled ? 'default' : 'primary'"
                :danger="job?.enabled"
                ghost
                @click="handleToggleEnabled"
              >
                {{ job?.enabled ? '⏸️ 禁用' : '▶️ 启用' }}
              </Button>
            </Tooltip>
            <Button type="primary" ghost @click="openTestModal">
              🧪 测试运行
            </Button>
            <Button @click="handleEdit"> ✏️ 编辑 </Button>
            <template v-if="job?.status === 'NOT_DEPLOYED'">
              <Button type="primary" @click="handleDeploy"> 🚀 部署 </Button>
            </template>
            <template
              v-else-if="
                ['DEPLOYED', 'PAUSED', 'RUNNING'].includes(job?.status || '')
              "
            >
              <Dropdown>
                <Button type="primary"> 🚀 已部署 </Button>
                <template #overlay>
                  <Menu>
                    <MenuItem
                      v-if="job?.status === 'PAUSED'"
                      @click="handleResume"
                    >
                      ▶️ 恢复
                    </MenuItem>
                    <MenuItem v-else @click="handlePause"> ⏸️ 暂停 </MenuItem>
                    <MenuItem @click="handleComplete"> ✅ 完成 </MenuItem>
                  </Menu>
                </template>
              </Dropdown>
            </template>
            <template v-else>
              <Button type="primary" disabled> 🚀 已停止/已完成 </Button>
            </template>
          </Space>
        </template>

        <template v-if="job">
          <!-- 基本信息 -->
          <Descriptions :column="3" bordered size="small" class="info-section">
            <DescriptionsItem label="Job ID" :span="1">
              <Tooltip title="点击复制">
                <code
                  class="job-id copyable"
                  @click="copyToClipboard(job.job_id, 'Job ID')"
                >
                  {{ job.job_id }}
                </code>
              </Tooltip>
            </DescriptionsItem>
            <DescriptionsItem label="Job 名称" :span="2">
              <Tooltip :title="job.job_name" placement="topLeft">
                <span class="job-name text-ellipsis">{{ job.job_name }}</span>
              </Tooltip>
              <Tooltip title="复制名称">
                <Button
                  type="text"
                  size="small"
                  class="copy-btn"
                  @click="copyToClipboard(job.job_name, 'Job 名称')"
                >
                  📋
                </Button>
              </Tooltip>
            </DescriptionsItem>
            <DescriptionsItem label="启用状态">
              <Tag :color="job.enabled ? 'success' : 'default'">
                {{ job.enabled ? '✅ 启用' : '❌ 禁用' }}
              </Tag>
            </DescriptionsItem>
            <DescriptionsItem label="目标篇数">
              <span class="article-count">
                {{ job.article_count ?? '不限制' }}
              </span>
            </DescriptionsItem>
            <DescriptionsItem label="Expert 数量">
              <Tag color="blue">
                {{ job.expert_config_code_list?.length || 0 }} 个
              </Tag>
            </DescriptionsItem>
            <DescriptionsItem label="创建时间">
              <Tooltip
                :title="formatTimeWithRelative(job.create_time).relative"
              >
                <span class="time-text">
                  {{ formatTimeWithRelative(job.create_time).display }}
                </span>
              </Tooltip>
            </DescriptionsItem>
            <DescriptionsItem label="更新时间">
              <Tooltip
                :title="formatTimeWithRelative(job.update_time).relative"
              >
                <span class="time-text">
                  {{ formatTimeWithRelative(job.update_time).display }}
                </span>
              </Tooltip>
            </DescriptionsItem>
            <DescriptionsItem label="创建人">
              {{ job.created_by || '-' }}
            </DescriptionsItem>
            <DescriptionsItem label="描述" :span="3">
              <template v-if="job.description">
                <Tooltip
                  v-if="job.description.length > 100"
                  :title="job.description"
                  placement="topLeft"
                  :overlay-style="{ maxWidth: '500px' }"
                >
                  <span class="description-text text-ellipsis-2">
                    {{ job.description }}
                  </span>
                </Tooltip>
                <span v-else class="description-text">
                  {{ job.description }}
                </span>
              </template>
              <span v-else class="empty-text">-</span>
            </DescriptionsItem>
            <DescriptionsItem v-if="job.remark" label="备注" :span="3">
              <Tooltip
                v-if="job.remark.length > 100"
                :title="job.remark"
                placement="topLeft"
                :overlay-style="{ maxWidth: '500px' }"
              >
                <span class="remark-text text-ellipsis-2">
                  {{ job.remark }}
                </span>
              </Tooltip>
              <span v-else class="remark-text">{{ job.remark }}</span>
            </DescriptionsItem>
          </Descriptions>

          <!-- Tab 面板 -->
          <Tabs class="detail-tabs">
            <!-- Expert 执行流程 -->
            <TabPane key="flow" tab="📊 执行流程">
              <div class="flow-section">
                <Alert
                  message="Expert 将按以下顺序依次执行，前一个 Expert 的输出将作为后一个的输入"
                  type="info"
                  show-icon
                  class="flow-alert"
                />
                <div class="flow-timeline">
                  <Timeline mode="left">
                    <TimelineItem
                      v-for="(item, index) in expertTableData"
                      :key="item.code"
                      :color="item.enabled ? 'blue' : 'gray'"
                    >
                      <template #dot>
                        <div class="timeline-dot">{{ index + 1 }}</div>
                      </template>
                      <div class="timeline-card">
                        <div class="timeline-header">
                          <span class="expert-name">{{ item.name }}</span>
                          <Tag
                            :color="item.enabled ? 'success' : 'default'"
                            size="small"
                          >
                            {{ item.enabled ? '启用' : '禁用' }}
                          </Tag>
                        </div>
                        <div class="timeline-meta">
                          <code>{{ item.code }}</code>
                          <span class="meta-divider">|</span>
                          <span class="expert-type">{{ item.type }}</span>
                          <span v-if="item.model" class="meta-divider">|</span>
                          <span v-if="item.model" class="model-code">
                            {{ item.model }}
                          </span>
                        </div>
                        <div v-if="item.description" class="timeline-desc">
                          {{ item.description }}
                        </div>
                      </div>
                    </TimelineItem>
                  </Timeline>
                </div>
              </div>
            </TabPane>

            <!-- Expert 配置列表 -->
            <TabPane key="experts" tab="⚙️ Expert 配置">
              <Table
                :columns="expertColumns"
                :data-source="expertTableData"
                :pagination="false"
                size="small"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'order'">
                    <div class="order-badge">{{ record.order }}</div>
                  </template>
                  <template v-else-if="column.key === 'code'">
                    <code class="expert-code">{{ record.code }}</code>
                  </template>
                  <template v-else-if="column.key === 'type'">
                    <Tag color="purple">{{ record.type }}</Tag>
                  </template>
                  <template v-else-if="column.key === 'model'">
                    <Tooltip v-if="record.model !== '-'" :title="record.model">
                      <Tag color="cyan">{{ record.model }}</Tag>
                    </Tooltip>
                    <span v-else>-</span>
                  </template>
                  <template v-else-if="column.key === 'status'">
                    <Tag :color="record.enabled ? 'success' : 'default'">
                      {{ record.enabled ? '启用' : '禁用' }}
                    </Tag>
                  </template>
                </template>
              </Table>
            </TabPane>

            <!-- 调度任务 -->
            <TabPane key="tasks" tab="📅 调度任务">
              <Alert
                v-if="expertTasks.length === 0"
                message="暂无调度任务"
                description="部署 Job 后将自动创建调度任务"
                type="info"
                show-icon
              />
              <Table
                v-else
                :columns="taskColumns"
                :data-source="expertTasks"
                :pagination="false"
                size="small"
                row-key="id"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'status'">
                    <Badge
                      :status="
                        record.status === 1
                          ? 'processing'
                          : record.status === 2
                            ? 'warning'
                            : record.status === 3
                              ? 'success'
                              : 'default'
                      "
                      :text="
                        taskStatusConfig[record.status as number]?.label ||
                        '未知'
                      "
                    />
                  </template>
                  <template v-else-if="column.key === 'action'">
                    <Space :size="4">
                      <Tooltip v-if="record.status !== 1" title="启动任务">
                        <Button
                          type="link"
                          size="small"
                          @click="
                            handleToggleTaskStatus(record as JobApi.ExpertTask)
                          "
                        >
                          ▶️
                        </Button>
                      </Tooltip>
                      <Tooltip v-if="record.status === 1" title="暂停任务">
                        <Button
                          type="link"
                          size="small"
                          @click="
                            handleToggleTaskStatus(record as JobApi.ExpertTask)
                          "
                        >
                          ⏸️
                        </Button>
                      </Tooltip>
                    </Space>
                  </template>
                </template>
              </Table>
            </TabPane>
          </Tabs>
        </template>
      </Card>
    </Spin>

    <!-- 测试弹窗 -->
    <Modal
      v-model:open="testModalVisible"
      title="🧪 测试运行 Job"
      :width="1000"
      :footer="null"
      :mask-closable="!testing"
      :closable="!testing"
      class="test-modal"
    >
      <div class="test-content">
        <!-- 测试信息 -->
        <div v-if="job && !testCompleted" class="test-info">
          <Alert
            :message="`将测试 Job: ${job.job_name}`"
            :description="`共 ${job.expert_config_code_list?.length || 0} 个 Expert 将按顺序执行`"
            type="info"
            show-icon
          />

          <!-- 新增：执行次数配置 -->
          <div class="execution-count-section">
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

          <!-- 配置覆盖开关 -->
          <div class="config-override-section">
            <div class="config-override-header">
              <Switch
                v-model:checked="enableConfigOverride"
                :disabled="testing"
              />
              <span class="config-override-label">使用自定义配置</span>
              <Tooltip
                title="开启后可以覆盖 Expert 的 Plugin 配置，用于测试不同的参数组合"
              >
                <span class="help-icon">❓</span>
              </Tooltip>
            </div>

            <!-- 配置覆盖编辑器 -->
            <div v-if="enableConfigOverride" class="config-override-editor">
              <Spin :spinning="loadingPluginContexts">
                <Collapse
                  v-if="job.expert_config_code_list.length > 0"
                  accordion
                >
                  <CollapsePanel
                    v-for="expertCode in job.expert_config_code_list"
                    :key="expertCode"
                  >
                    <template #header>
                      <Space>
                        <span class="expert-badge">⚙️</span>
                        <code>{{ expertCode }}</code>
                        <span class="expert-config-name">
                          {{
                            expertConfigs.get(expertCode)?.expert_config_name ||
                            ''
                          }}
                        </span>
                      </Space>
                    </template>
                    <div class="config-vars">
                      <div
                        v-for="variable in getExpertPluginVariables(expertCode)"
                        :key="`${variable.pluginCode}-${variable.variableName}`"
                        class="config-var-item"
                      >
                        <div class="var-label">
                          <Tag color="purple" size="small">
                            {{ variable.pluginCode }}
                          </Tag>
                          <span class="var-name">{{
                            variable.variableName
                          }}</span>
                        </div>
                        <Select
                          :value="
                            configOverride[expertCode]?.[variable.pluginCode]?.[
                              variable.variableName
                            ]
                          "
                          style="width: 100%"
                          placeholder="选择 Context"
                          allow-clear
                          show-search
                          :get-popup-container="
                            (trigger) => trigger.parentElement
                          "
                          @change="
                            (val: any) =>
                              updateConfigOverride(
                                expertCode,
                                variable.pluginCode,
                                variable.variableName,
                                val,
                              )
                          "
                        >
                          <Select.Option
                            v-for="ctx in getContextOptionsForVariable(
                              variable.pluginCode,
                              variable.variableName,
                            )"
                            :key="ctx.id"
                            :value="ctx.context_name"
                          >
                            <div class="context-option">
                              <span class="context-name">{{
                                ctx.context_name
                              }}</span>
                              <Tooltip :title="ctx.context_content">
                                <span class="context-preview">
                                  {{ ctx.context_content?.slice(0, 50) }}...
                                </span>
                              </Tooltip>
                            </div>
                          </Select.Option>
                        </Select>
                      </div>
                      <div
                        v-if="getExpertPluginVariables(expertCode).length === 0"
                        class="no-vars"
                      >
                        此 Expert 没有可配置的 Plugin 变量
                      </div>
                    </div>
                  </CollapsePanel>
                </Collapse>
              </Spin>
            </div>
          </div>
        </div>

        <!-- 执行按钮 -->
        <div v-if="!testing && !testCompleted" class="test-actions">
          <Button type="primary" size="large" @click="handleTest">
            🚀 开始测试
          </Button>
        </div>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.job-detail-page {
  padding: 16px;
}

.back-icon {
  font-size: 16px;
}

.page-title {
  font-size: 16px;
  font-weight: 600;
}

.info-section {
  margin-bottom: 24px;
}

.job-id {
  padding: 2px 8px;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 13px;
  background: hsl(var(--muted));
  border-radius: 4px;
}

.job-id.copyable {
  cursor: pointer;
  transition: all 0.2s;
}

.job-id.copyable:hover {
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 15%);
}

.job-name {
  font-size: 15px;
  font-weight: 600;
}

.text-ellipsis {
  display: inline-block;
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
  white-space: nowrap;
}

.text-ellipsis-2 {
  display: -webkit-box;
  overflow: hidden;
  text-overflow: ellipsis;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.copy-btn {
  margin-left: 4px;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.copy-btn:hover {
  opacity: 1;
}

.time-text {
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 13px;
  cursor: help;
}

.description-text,
.remark-text {
  font-size: 14px;
  line-height: 1.6;
  color: hsl(var(--foreground));
}

.empty-text {
  color: hsl(var(--muted-foreground));
}

.article-count {
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-weight: 500;
}

.detail-tabs {
  margin-top: 24px;
}

/* 执行流程样式 */
.flow-section {
  padding: 16px 0;
}

.flow-alert {
  margin-bottom: 24px;
}

.flow-timeline {
  padding-left: 24px;
}

.timeline-dot {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  font-size: 14px;
  font-weight: 600;
  color: hsl(var(--primary-foreground));
  background: hsl(var(--primary));
  border-radius: 50%;
}

.timeline-card {
  padding: 12px 16px;
  margin-left: 12px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.timeline-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.expert-name {
  font-size: 15px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.timeline-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.timeline-meta code {
  padding: 2px 6px;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 12px;
  background: hsl(var(--muted));
  border-radius: 4px;
}

.meta-divider {
  color: hsl(var(--border));
}

.expert-type {
  padding: 2px 8px;
  font-size: 12px;
  background: hsl(var(--muted));
  border-radius: 4px;
}

.model-code {
  color: hsl(var(--primary));
}

.timeline-desc {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.5;
  color: hsl(var(--muted-foreground));
}

/* 表格样式 */
.order-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  margin: 0 auto;
  font-size: 12px;
  font-weight: 600;
  color: hsl(var(--primary-foreground));
  background: hsl(var(--primary));
  border-radius: 50%;
}

.expert-code {
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 12px;
}

/* 测试弹窗样式 */
.test-content {
  padding: 16px 0;
}

.test-info {
  margin-bottom: 24px;
}

.execution-count-section {
  display: flex;
  align-items: center;
  padding: 12px;
  margin-top: 16px;
  background: hsl(var(--background));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.execution-count-section .label {
  margin-right: 12px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.execution-hint {
  margin-left: 12px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

/* 配置覆盖样式 */
.config-override-section {
  padding: 16px;
  margin-top: 16px;
  background: hsl(var(--muted) / 30%);
  border-radius: 8px;
}

.config-override-header {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
}

.config-override-label {
  font-weight: 500;
  color: hsl(var(--foreground));
}

.help-icon {
  cursor: help;
  opacity: 0.6;
}

.config-override-editor {
  margin-top: 12px;
}

.expert-badge {
  font-size: 14px;
}

.expert-config-name {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.config-vars {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.config-var-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.var-label {
  display: flex;
  gap: 8px;
  align-items: center;
}

.var-name {
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 13px;
  color: hsl(var(--foreground));
}

.context-option {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.context-name {
  font-weight: 500;
}

.context-preview {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
}

.no-vars {
  padding: 16px;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.test-actions {
  display: flex;
  justify-content: center;
  padding: 32px 0;
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
}

.progress-text code {
  padding: 2px 8px;
  margin-left: 4px;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  background: hsl(var(--muted));
  border-radius: 4px;
}

.test-results {
  margin-top: 16px;
}

.result-success {
  color: hsl(var(--success));
}

.result-error {
  color: hsl(var(--destructive));
}

.expert-result-name {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.result-content {
  padding: 8px 0;
}

.generated-content {
  margin-bottom: 16px;
}

.content-label {
  margin-bottom: 8px;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.content-text {
  max-height: 200px;
  padding: 12px;
  overflow-y: auto;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  background: hsl(var(--muted) / 30%);
  border-radius: 8px;
}

.raw-response {
  margin-top: 16px;
}

.response-json {
  max-height: 300px;
  padding: 12px;
  margin: 0;
  overflow: auto;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 12px;
  word-break: break-all;
  white-space: pre-wrap;
  background: hsl(var(--muted) / 50%);
  border-radius: 8px;
}

.retest-actions {
  display: flex;
  justify-content: center;
  padding-top: 16px;
  margin-top: 24px;
  border-top: 1px solid hsl(var(--border));
}

/* 结果摘要卡片 */
.results-summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}

.result-summary-card {
  padding: 12px 16px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  transition: all 0.2s;
}

.result-summary-card.success {
  border-left: 3px solid hsl(var(--success));
}

.result-summary-card.error {
  border-left: 3px solid hsl(var(--destructive));
}

.result-card-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.result-icon {
  font-size: 16px;
}

.result-expert-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
  font-weight: 500;
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.result-card-preview {
  font-size: 12px;
  line-height: 1.5;
}

.error-preview {
  color: hsl(var(--destructive));
}

.content-preview {
  color: hsl(var(--muted-foreground));
}

.results-collapse {
  margin-top: 16px;
}

/* Ant Design 覆盖 */
:deep(.ant-descriptions-bordered .ant-descriptions-item-label) {
  background: hsl(var(--muted) / 30%);
}

:deep(.ant-table-thead > tr > th) {
  background: hsl(var(--muted));
}

:deep(.ant-timeline-item-content) {
  min-height: auto;
}

:deep(.ant-collapse-header) {
  font-size: 14px !important;
}

:deep(.ant-card-head) {
  border-bottom: 1px solid hsl(var(--border));
}
</style>
