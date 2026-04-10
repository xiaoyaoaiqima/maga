<script setup lang="ts">
import type { EchartsUIType } from '@vben/plugins/echarts';

import type { AgentApi } from '#/api/core/business';
import type { BatchScoreTaskApi, ContentApi } from '#/api/core/content';
import type { ExpertConfigOptionItem } from '#/api/core/critic-scores';
import type {
  ContentCriticSummary,
  ContentDetail,
  ExpertBusinessResultDetail,
} from '#/api/core/job-execution';

import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { EchartsUI, useEcharts } from '@vben/plugins/echarts';
import { useUserStore } from '@vben/stores';
import { formatDateTime } from '@vben/utils';

import {
  CloseCircleOutlined,
  DeleteOutlined,
  DownloadOutlined,
  InfoCircleOutlined,
  PlusOutlined,
  SwapOutlined,
  UploadOutlined,
} from '@ant-design/icons-vue';
import {
  Alert,
  Badge,
  Button,
  Card,
  DatePicker,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  notification,
  Pagination,
  Popover,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Upload,
} from 'ant-design-vue';
import dayjs from 'dayjs';
import * as XLSX from 'xlsx';

import {
  getAgentApi,
  getAgentSimpleListApi,
  getTenantSimpleListApi,
} from '#/api/core/business';
import { createCalibrationTaskApi } from '#/api/core/calibration';
import {
  batchUpdateContentOnlineStatusApi,
  batchUpdateContentValidApi,
  createBatchScoreTaskApi,
  getBatchScoreTaskStatusApi,
  getContentExpertResultsApi,
  getContextStatsApi,
  importContentsApi,
  listContentsApi,
  transferContentsApi,
} from '#/api/core/content';
import { listExpertConfigOptionsApi } from '#/api/core/critic-scores';
import { getExpertConfigListApi, getJobListApi } from '#/api/core/job';
import ScoreRadarChart from '#/components/ScoreRadarChart.vue';

const { Item: FormItem } = Form;
const { Option: SelectOption } = Select;
const { RangePicker } = DatePicker;

// ==================== 路由 ====================

const route = useRoute();
const router = useRouter();

// ==================== 用户状态 ====================

const userStore = useUserStore();

// ==================== 状态 ====================

const loading = ref(false);

// 专家视角提示
const expertViewActive = ref(false);
const expertViewName = ref('');

// 业务文章池数据
const businessData = ref<ContentApi.ContentListResponse['items']>([]);
const businessTotal = ref(0);
const businessLoading = ref(false);

const businessParams = ref({
  page: 1, // 服务端分页页码
  page_size: 20, // 每页数量
  tenant_id: undefined as number | undefined,
  agent_code: undefined as string | undefined,
  expert_config_code: undefined as string | undefined,
  job_id: '',
  is_valid: undefined as number | undefined,
  is_test_case: undefined as number | undefined,
  online_status: undefined as string | undefined,
  keyword: '',
  create_time_start: undefined as string | undefined,
  create_time_end: undefined as string | undefined,
  order_by_create_time: 'desc' as 'asc' | 'desc' | undefined,
  // ID 范围筛选
  id_min: undefined as number | undefined,
  id_max: undefined as number | undefined,
});

/** 专家评分细化筛选 (UI 临时状态) */
const expertScoreFilters = ref<
  Array<{
    expert_config_code: string;
    max_score: number | undefined;
    min_score: number | undefined;
    passed: boolean | undefined; // BAN类型: true=通过, false=不通过
  }>
>([]);

// Agent 筛选选项
const filterAgentOptions = ref<Array<{ label: string; value: string }>>([]);
const filterAgentLoading = ref(false);

// 选中 Agent 的完整标签（用于 hover 显示）
const selectedAgentLabel = computed(() => {
  if (!businessParams.value.agent_code) return '';
  const opt = filterAgentOptions.value.find(
    (o) => o.value === businessParams.value.agent_code,
  );
  return opt?.label || businessParams.value.agent_code;
});

// 下拉选项
const tenantOptions = ref<Array<{ label: string; value: number }>>([]);
const jobOptions = ref<Array<{ label: string; value: string }>>([]);

// 专家筛选
interface ExpertOption {
  label: string;
  value: string;
  expert_config_name: string;
  expert_type: string;
  expert_func: string;
}

type CalibrationExpertType = 'BAN' | 'CRITIC';

interface CalibrationExpertPayload {
  name: string;
  expert_code: string;
  expert_type: CalibrationExpertType;
  expert_func: string;
}

interface CalibrationArticlePayload {
  id: number;
  title: string;
  content: string;
  critic_summary: ContentCriticSummary | null;
  job_id?: string;
  content_id?: string;
}

interface CalibrationPayload {
  experts: CalibrationExpertPayload[];
  articles: CalibrationArticlePayload[];
  source: 'article_pool';
  created_at: string;
}
const expertOptions = ref<ExpertOption[]>([]);
const expertOptionsLoading = ref(false);
const agentExpertCodes = ref<string[]>([]);

const filteredExpertOptions = computed(() => {
  // 方案二：废弃 Agent-专家关联校验，直接返回所有专家选项
  // 后端已改为基于 critic_score_record 表直接筛选，不再受 Agent 配置限制
  return expertOptions.value;
});

const expertFilterOption = (input: string, option: any) => {
  // 参考 Expert 管理页面的简洁实现：直接搜索 label
  return (option?.label ?? '')
    .toString()
    .toLowerCase()
    .includes(input.toLowerCase());
};

// 详情抽屉
const detailVisible = ref(false);
const detailLoading = ref(false);
const currentDetail = ref<ContentDetail | null>(null);

// Expert 结果（用于获取 CRITIC 审核结果）
const expertResults = ref<ExpertBusinessResultDetail[]>([]);
const expertResultsLoading = ref(false);

// ==================== 导入弹窗 ====================

const importModalVisible = ref(false);
const importLoading = ref(false);
const importForm = ref({
  tenant_id: undefined as number | undefined,
  agent_code: undefined as string | undefined,
  is_test_case: 0,
});
const importFile = ref<File | null>(null);
const agentOptions = ref<Array<{ label: string; value: string }>>([]);

// ==================== 批量评分（异步任务模式） ====================

/** 选中的文章行 */
const selectedRowKeys = ref<Array<number | string>>([]);
const selectedRows = ref<ContentApi.ContentListResponse['items']>([]);

const CALIBRATION_STORAGE_PREFIX = 'calibration-workbench:';

const normalize_expert_type = (value: string): CalibrationExpertType | null => {
  if (value === 'BAN' || value === 'CRITIC') return value;
  return null;
};

const build_calibration_payload = (): CalibrationPayload | null => {
  if (selectedRows.value.length === 0) {
    message.warning('请先选择要校准的文章');
    return null;
  }
  if (!businessParams.value.expert_config_code) {
    message.warning('请先选择专家');
    return null;
  }
  const expert = expertOptions.value.find(
    (opt) => opt.value === businessParams.value.expert_config_code,
  );
  if (!expert) {
    message.warning('未找到专家信息，请刷新后重试');
    return null;
  }
  const expert_type = normalize_expert_type(expert.expert_type);
  if (!expert_type) {
    message.warning('专家类型异常，请确认配置');
    return null;
  }
  const payload: CalibrationPayload = {
    experts: [
      {
        name: expert.expert_config_name || expert.value,
        expert_code: expert.value,
        expert_type,
        expert_func: expert.expert_func,
      },
    ],
    articles: selectedRows.value.map((item) => ({
      id: item.id,
      title: item.title ?? '',
      content: item.content ?? '',
      critic_summary: item.critic_summary ?? null,
      job_id: item.job_id,
      content_id: item.content_id,
    })),
    source: 'article_pool',
    created_at: new Date().toISOString(),
  };
  return payload;
};

const handle_go_calibration_workbench = async () => {
  const payload = build_calibration_payload();
  if (!payload) return;

  loading.value = true;
  try {
    // 1. 创建校准任务
    const expertName = payload.experts[0]?.name || '专家';
    const userName = userStore.userInfo?.realName || '未命名';
    const task_res = await createCalibrationTaskApi({
      task_name: `${expertName}-${userName}-${dayjs().format('MM-DD HH:mm')}校准任务`,
      remark: `来自文章池的校准申请, 共 ${payload.articles.length} 篇文章`,
    });

    if (!task_res?.id) {
      throw new Error('创建校准任务失败: 未返回任务 ID');
    }

    // 2. 缓存本地数据
    const key = `${CALIBRATION_STORAGE_PREFIX}${Date.now()}-${Math.random()
      .toString(36)
      .slice(2, 8)}`;
    sessionStorage.setItem(key, JSON.stringify(payload));

    // 3. 跳转带上 task_id
    router.push({
      path: '/expert/calibration-workbench',
      query: {
        calibration_key: key,
        calibration_task_id: task_res.id,
      },
    });
  } catch (error: unknown) {
    console.error('前往校准工作台失败:', error);
    message.error(
      error instanceof Error ? error.message : '校准准备失败，请稍后重试',
    );
  } finally {
    loading.value = false;
  }
};

/** 批量评分弹窗 */
const batchScoreModalVisible = ref(false);
const batchScoreSubmitting = ref(false); // 提交中状态（仅用于弹窗按钮）
const batchScoreForm = ref({
  expert_config_codes: [] as string[],
  concurrency: 3, // 并发数，默认3
});

/** 批量评分任务状态（支持多专家，每个专家一个任务） */
interface BatchScoreTaskState {
  task_id: string;
  expert_config_code: string;
  expert_config_name: string;
  status: 'completed' | 'failed' | 'pending' | 'running';
  total: number;
  completed: number;
  success_count: number;
  failed_count: number;
  results: BatchScoreTaskApi.TaskResultItem[];
  error_message: null | string;
}
const batchScoreTasks = ref<BatchScoreTaskState[]>([]);
const batchScoreStatus = ref<string>('');
const batchScoreResults = ref<BatchScoreTaskApi.TaskResultItem[]>([]);
const batchScoreSummary = ref<null | {
  completed: number;
  failed_count: number;
  success_count: number;
  total: number;
}>(null);
let batchScorePollingTimer: null | ReturnType<typeof setInterval> = null;

/** Expert 配置选项（用于批量评分选择） */
interface ExpertConfigOption {
  label: string;
  value: string;
  expert_type: string;
}
const expertConfigOptions = ref<ExpertConfigOption[]>([]);
const expertConfigLoading = ref(false);

/** 加载 Expert 配置列表 */
const loadExpertConfigs = async () => {
  expertConfigLoading.value = true;
  try {
    const list = await getExpertConfigListApi();
    // 只显示 CRITIC 和 BAN 类型的 Expert（用于评分）
    expertConfigOptions.value = (list || [])
      .filter((e) =>
        ['BAN', 'CRITIC'].includes(e.expert_type?.toUpperCase() || ''),
      )
      .map((e) => ({
        label: e.expert_config_name || e.expert_config_code,
        value: e.expert_config_code,
        expert_type: e.expert_type || '',
      }));
  } catch (error) {
    console.error('加载 Expert 配置失败:', error);
  } finally {
    expertConfigLoading.value = false;
  }
};

/** 表格行选择配置 */
const rowSelection = computed(() => ({
  selectedRowKeys: selectedRowKeys.value,
  onChange: (
    keys: Array<number | string>,
    rows: ContentApi.ContentListResponse['items'],
  ) => {
    selectedRowKeys.value = keys;
    selectedRows.value = rows;
  },
  // 点击表头全选时，仅全选当前页面的文章
  onSelectAll: (selected: boolean) => {
    if (selected) {
      // 全选当前页面
      const currentPageData = businessData.value;
      selectedRowKeys.value = currentPageData.map((item) => item.id);
      selectedRows.value = currentPageData;
      message.success(`已全选当前页 ${currentPageData.length} 篇文章`);
    } else {
      // 取消全选：清空选择
      selectedRowKeys.value = [];
      selectedRows.value = [];
    }
  },
}));

/** 打开批量评分弹窗 */
const openBatchScoreModal = () => {
  if (selectedRows.value.length === 0) {
    message.warning('请先选择要评分的文章');
    return;
  }
  batchScoreForm.value.expert_config_codes = [];
  batchScoreForm.value.concurrency = 3; // 重置并发数为默认值
  batchScoreTasks.value = [];
  batchScoreResults.value = [];
  batchScoreSummary.value = null;
  loadExpertConfigs();
  batchScoreModalVisible.value = true;
};

/** 批量下线（将选中文章状态改为无效） */
const batchOfflineLoading = ref(false);
const handleBatchOffline = async () => {
  if (selectedRows.value.length === 0) {
    message.warning('请先选择要下线的文章');
    return;
  }

  Modal.confirm({
    title: '确认批量下线',
    content: `确定要将选中的 ${selectedRows.value.length} 篇文章标记为无效吗？`,
    okText: '确认下线',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      batchOfflineLoading.value = true;
      try {
        const contentIds = selectedRows.value.map((row) => row.id);
        const result = await batchUpdateContentValidApi({
          content_ids: contentIds,
          is_valid: 0,
        });
        message.success(`成功下线 ${result.updated_count} 篇文章`);
        // 清空选择并刷新列表
        selectedRowKeys.value = [];
        selectedRows.value = [];
        fetchBusinessData();
        loadContextStats();
      } catch (error: unknown) {
        message.error((error as Error)?.message || '批量下线失败');
      } finally {
        batchOfflineLoading.value = false;
      }
    },
  });
};

/** 批量上线（将选中文章上线状态改为 ONLINE） */
const batchOnlineLoading = ref(false);
const handleBatchOnline = async () => {
  if (selectedRows.value.length === 0) {
    message.warning('请先选择要上线的文章');
    return;
  }

  Modal.confirm({
    title: '确认批量上线',
    content: `确定要将选中的 ${selectedRows.value.length} 篇文章上线吗？`,
    okText: '确认上线',
    okType: 'primary',
    cancelText: '取消',
    onOk: async () => {
      batchOnlineLoading.value = true;
      try {
        const contentIds = selectedRows.value.map((row) => row.id);
        const result = await batchUpdateContentOnlineStatusApi({
          content_ids: contentIds,
          online_status: 'ONLINE',
        });
        // 构建详细的成功消息
        const msgParts = [`成功上线 ${result.updated_count} 篇文章`];
        if (result.skipped_locked > 0) {
          msgParts.push(`跳过 ${result.skipped_locked} 篇已锁定`);
        }
        if (result.skipped_used > 0) {
          msgParts.push(`跳过 ${result.skipped_used} 篇已使用`);
        }
        message.success(msgParts.join('，'));
        // 清空选择并刷新列表
        selectedRowKeys.value = [];
        selectedRows.value = [];
        fetchBusinessData();
        loadContextStats();
      } catch (error: unknown) {
        message.error((error as Error)?.message || '批量上线失败');
      } finally {
        batchOnlineLoading.value = false;
      }
    },
  });
};

/** 导出选中文章为 XLSX */
const exportSelectedToXLSX = () => {
  if (selectedRows.value.length === 0) {
    message.warning('请先选择要导出的文章');
    return;
  }

  // 表头
  const headers = [
    'ID',
    'Content ID',
    '标题',
    '正文',
    '上下文变量(context_list)',
    '状态',
    '是否测试',
    '平均分',
    '评分通过数',
    '评分不通过数',
    '创建时间',
  ];

  // 转换数据为行
  const rows = selectedRows.value.map((row) => {
    const summary = row.critic_summary;
    // 处理 context_list：转为字符串
    let contextListStr = '';
    if (row.context_list) {
      contextListStr = Array.isArray(row.context_list)
        ? row.context_list.join('; ')
        : JSON.stringify(row.context_list);
    }
    // 处理状态显示
    let validStatus = '未知';
    if (row.is_valid === 1) {
      validStatus = '有效';
    } else if (row.is_valid === 0) {
      validStatus = '无效';
    }
    return [
      row.id,
      row.content_id || '',
      row.title || '',
      row.content || '',
      contextListStr,
      validStatus,
      row.is_test_case === 1 ? '是' : '否',
      summary?.avg_score?.toFixed(2) || '',
      summary?.passed_count || 0,
      summary?.failed_count || 0,
      row.create_time || '',
    ];
  });

  // 创建工作表数据（表头 + 数据行）
  const wsData = [headers, ...rows];

  // 创建工作簿和工作表
  const wb = XLSX.utils.book_new();
  const ws = XLSX.utils.aoa_to_sheet(wsData);

  // 设置列宽（可选，提升可读性）
  ws['!cols'] = [
    { wch: 8 }, // ID
    { wch: 20 }, // Content ID
    { wch: 30 }, // 标题
    { wch: 60 }, // 正文
    { wch: 30 }, // 上下文变量
    { wch: 8 }, // 状态
    { wch: 10 }, // 是否测试
    { wch: 10 }, // 平均分
    { wch: 12 }, // 评分通过数
    { wch: 12 }, // 评分不通过数
    { wch: 20 }, // 创建时间
  ];

  XLSX.utils.book_append_sheet(wb, ws, '文章池数据');

  // 导出文件
  const fileName = `文章池导出_${new Date().toISOString().slice(0, 10)}.xlsx`;
  XLSX.writeFile(wb, fileName);

  message.success(`成功导出 ${selectedRows.value.length} 篇文章`);
};

/** 执行批量评分（异步任务模式，支持多专家并行） */
const handleBatchScore = async () => {
  if (batchScoreForm.value.expert_config_codes.length === 0) {
    message.warning('请至少选择一个 Expert 配置');
    return;
  }
  if (selectedRows.value.length === 0) {
    message.warning('请选择要评分的文章');
    return;
  }

  const contentIds = selectedRows.value
    .map((row) => row.content_id)
    .filter((id): id is string => !!id);

  if (contentIds.length === 0) {
    message.warning('选中的文章没有有效的 content_id');
    return;
  }

  // 清除之前的轮询定时器
  if (batchScorePollingTimer) {
    clearInterval(batchScorePollingTimer);
    batchScorePollingTimer = null;
  }

  batchScoreSubmitting.value = true;
  batchScoreTasks.value = [];
  batchScoreResults.value = [];
  batchScoreSummary.value = null;
  batchScoreStatus.value = 'pending';

  try {
    // 创建批量评分任务（多专家）
    const resp = await createBatchScoreTaskApi({
      expert_config_codes: batchScoreForm.value.expert_config_codes,
      content_ids: contentIds,
      test_case_only: false,
      concurrency: batchScoreForm.value.concurrency,
    });

    // 初始化每个专家任务的状态
    batchScoreTasks.value = resp.tasks.map((t) => ({
      task_id: t.task_id,
      expert_config_code: t.expert_config_code,
      expert_config_name: t.expert_config_name,
      status: 'pending' as const,
      total: t.total,
      completed: 0,
      success_count: 0,
      failed_count: 0,
      results: [],
      error_message: null,
    }));

    message.success(
      `已创建 ${resp.total_experts} 个专家评分任务，后台并行执行中...`,
    );

    // 立即关闭弹窗，让任务在后台执行
    batchScoreModalVisible.value = false;
    batchScoreSubmitting.value = false;

    // 启动轮询查询所有任务状态（后台执行）
    batchScorePollingTimer = setInterval(async () => {
      try {
        // 并行查询所有未完成任务的状态
        const pendingTasks = batchScoreTasks.value.filter(
          (t) => t.status !== 'completed' && t.status !== 'failed',
        );

        if (pendingTasks.length === 0) {
          // 所有任务都已完成
          if (batchScorePollingTimer) {
            clearInterval(batchScorePollingTimer);
            batchScorePollingTimer = null;
          }
          batchScoreStatus.value = 'completed';

          // 汇总结果
          const summary = {
            total: 0,
            completed: 0,
            success_count: 0,
            failed_count: 0,
          };
          for (const t of batchScoreTasks.value) {
            summary.total += t.total;
            summary.completed += t.completed;
            summary.success_count += t.success_count;
            summary.failed_count += t.failed_count;
          }

          const hasFailedTask = batchScoreTasks.value.some(
            (t) => t.status === 'failed',
          );
          if (hasFailedTask) {
            notification.warning({
              message: '批量评分完成（部分失败）',
              description: `成功 ${summary.success_count} 篇，失败 ${summary.failed_count} 篇`,
              duration: 5,
            });
          } else {
            notification.success({
              message: '批量评分完成',
              description: `${batchScoreTasks.value.length} 个专家，成功 ${summary.success_count} 篇，失败 ${summary.failed_count} 篇`,
              duration: 5,
            });
          }
          // 清空选择并刷新列表
          selectedRowKeys.value = [];
          selectedRows.value = [];
          fetchBusinessData();
          return;
        }

        // 并行查询每个任务的状态
        const statusPromises = pendingTasks.map((t) =>
          getBatchScoreTaskStatusApi(t.task_id).catch((error) => {
            console.error(
              `[BatchScore Polling] Error for ${t.task_id}:`,
              error,
            );
            return null;
          }),
        );
        const statuses = await Promise.all(statusPromises);

        // 更新每个任务的状态
        for (const [i, pendingTask] of pendingTasks.entries()) {
          const taskStatus = statuses[i];
          if (!taskStatus) continue;

          const taskIndex = batchScoreTasks.value.findIndex(
            (t) => t.task_id === pendingTask.task_id,
          );
          if (taskIndex === -1) continue;

          batchScoreTasks.value[taskIndex] = {
            ...batchScoreTasks.value[taskIndex],
            status: taskStatus.status,
            completed: taskStatus.completed,
            success_count: taskStatus.success_count,
            failed_count: taskStatus.failed_count,
            results: taskStatus.results,
            error_message: taskStatus.error_message,
          };
        }

        // 更新汇总信息
        const updatedSummary = {
          total: 0,
          completed: 0,
          success_count: 0,
          failed_count: 0,
        };
        for (const t of batchScoreTasks.value) {
          updatedSummary.total += t.total;
          updatedSummary.completed += t.completed;
          updatedSummary.success_count += t.success_count;
          updatedSummary.failed_count += t.failed_count;
        }
        batchScoreSummary.value = updatedSummary;

        // 合并所有任务的结果
        batchScoreResults.value = batchScoreTasks.value.flatMap(
          (t) => t.results,
        );

        // 更新整体状态
        const allCompleted = batchScoreTasks.value.every(
          (t) => t.status === 'completed' || t.status === 'failed',
        );
        const anyRunning = batchScoreTasks.value.some(
          (t) => t.status === 'running',
        );
        if (allCompleted) {
          batchScoreStatus.value = 'completed';
        } else if (anyRunning) {
          batchScoreStatus.value = 'running';
        } else {
          batchScoreStatus.value = 'pending';
        }
      } catch (error) {
        console.error('[BatchScore Polling] Error:', error);
        // 轮询出错不中断，继续尝试
      }
    }, 2000); // 每 2 秒轮询一次
  } catch (error: unknown) {
    const errMsg =
      error instanceof Error ? error.message : '创建批量评分任务失败';
    message.error(errMsg);
    batchScoreSubmitting.value = false;
  }
};

// 从 Expert 结果中提取 CRITIC 违禁词检测信息
interface CriticInfo {
  reason: string;
  problemSnippets: string[];
  expertCode: string;
}
const criticInfoList = computed<CriticInfo[]>(() => {
  if (expertResults.value.length === 0) return [];

  const results: CriticInfo[] = [];
  for (const result of expertResults.value) {
    if (!result.business_result) continue;

    const br = result.business_result;
    const snippets = br.problem_snippets || br.problem_context_list || [];
    const hasProblems =
      (br.score === 0 || br.passed === 0) &&
      (br.reason || (Array.isArray(snippets) && snippets.length > 0));

    if (hasProblems) {
      results.push({
        reason: br.reason || '',
        problemSnippets: Array.isArray(snippets) ? snippets : [],
        expertCode: result.expert_config_code,
      });
    }
  }
  return results;
});

// 收集所有违禁词（用于高亮显示）
const allForbiddenWords = computed<string[]>(() => {
  const words: string[] = [];
  for (const info of criticInfoList.value) {
    words.push(...info.problemSnippets);
  }
  return [...new Set(words)].toSorted((a, b) => b.length - a.length);
});

// 工具函数：转义 HTML 特殊字符
function escapeHtml(text: string): string {
  const map: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;',
  };
  return text.replaceAll(/[&<>"']/g, (m) => map[m] || m);
}

// 工具函数：转义正则表达式特殊字符
function escapeRegExp(text: string): string {
  return text.replaceAll(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`);
}

// 生成高亮后的文章内容 HTML
const highlightedContent = computed<string>(() => {
  const content = (currentDetail.value?.content as string) || '';
  if (!content) return '';
  if (allForbiddenWords.value.length === 0) return escapeHtml(content);

  let result = escapeHtml(content);
  for (const word of allForbiddenWords.value) {
    const escapedWord = escapeHtml(word);
    const regex = new RegExp(escapeRegExp(escapedWord), 'gi');
    result = result.replace(
      regex,
      `<mark class="highlight-forbidden">${escapedWord}</mark>`,
    );
  }
  return result;
});

// 计算文章字数（去除空格和换行）
const contentCharCount = computed<number>(() => {
  const content =
    (currentDetail.value?.content as string) ||
    ((currentDetail.value as any)?.output_content as string) ||
    '';
  return content.replaceAll(/\s/g, '').length;
});

// ==================== Context 分布统计 ====================

const chartRef = ref<EchartsUIType>();
const { renderEcharts } = useEcharts(chartRef);

// 图表筛选状态
const chartTenantFilter = ref<number>();
const selectedContextKey = ref<string>();

// 统计数据
const contextKeys = ref<string[]>([]);
const contextDistribution = ref<ContentApi.ContextDistributionItem[]>([]);
const chartLoading = ref(false);
const chartQueried = ref(false);
const contextStatsMeta = ref<{
  is_sampled?: boolean;
  sample_count?: number;
  total_count?: number;
}>({});

// 加载 Context 统计数据
const loadContextStats = async () => {
  chartLoading.value = true;
  try {
    // 图表筛选条件优先使用图表自身的筛选器
    const params: ContentApi.ContextStatsParams = {
      tenant_id: chartTenantFilter.value,
      agent_code: businessParams.value.agent_code,
      job_id: undefined, // 图表不使用 job_id 筛选，减少数据量
      is_valid: businessParams.value.is_valid,
      is_test_case: businessParams.value.is_test_case,
      variable_name: selectedContextKey.value,
    };

    const res = await getContextStatsApi(params);
    contextKeys.value = res.keys || [];
    contextDistribution.value = res.distribution || [];
    contextStatsMeta.value = {
      sample_count: res.sample_count,
      total_count: res.total_count,
      is_sampled: res.is_sampled,
    };
  } catch (error) {
    console.error('Failed to load context stats:', error);
  } finally {
    chartLoading.value = false;
  }
};

// 饼图和柱状图颜色数组
const chartColors = [
  '#5470c6',
  '#91cc75',
  '#fac858',
  '#ee6666',
  '#73c0de',
  '#3ba272',
  '#fc8452',
  '#9a60b4',
  '#ea7ccc',
  '#6e7074',
];

// 更新图表 - 组合图表（左侧饼图 + 右侧柱状图）
const updateChart = async () => {
  if (contextDistribution.value.length === 0) {
    return;
  }

  // 按数值排序，取前 10 个
  const sortedData = contextDistribution.value.toSorted(
    (a, b) => (b.value as number) - (a.value as number),
  );
  const top10Data = sortedData.slice(0, 10);
  const categories = top10Data.map((item) => item.name);
  const values = top10Data.map((item) => item.value);

  await renderEcharts({
    color: chartColors,
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow',
      },
    },
    legend: {
      show: false,
    },
    series: [
      // 饼图系列
      {
        name: selectedContextKey.value || 'Context 分布',
        type: 'pie',
        radius: ['35%', '65%'],
        center: ['25%', '50%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 8,
          borderColor: '#fff',
          borderWidth: 2,
        },
        label: {
          show: true,
          position: 'outside',
          formatter: '{b}\n{d}%',
          fontSize: 11,
          color: '#666',
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 13,
            fontWeight: 'bold',
          },
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.5)',
          },
        },
        labelLine: {
          show: true,
          length: 10,
          length2: 10,
        },
        data: sortedData,
        tooltip: {
          trigger: 'item',
          formatter: '{b}: {c} ({d}%)',
        },
      },
      // 柱状图系列
      {
        name: '数值统计',
        type: 'bar',
        data: values,
        barWidth: '60%',
        xAxisIndex: 1,
        yAxisIndex: 1,
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: '#5470c6' },
              { offset: 1, color: '#91cc75' },
            ],
          },
        },
        label: {
          show: true,
          position: 'top',
          formatter: '{c}',
          fontSize: 11,
          color: '#666',
        },
        emphasis: {
          itemStyle: {
            color: '#5470c6',
          },
        },
        tooltip: {
          trigger: 'axis',
          formatter: '{b}: {c}',
        },
      },
    ],
    xAxis: [
      {
        show: false,
      },
      {
        type: 'category',
        data: categories,
        gridIndex: 1,
        axisLabel: {
          interval: 0,
          rotate: 30,
          fontSize: 10,
          color: '#666',
          formatter: (value: string) => {
            // 标签过长时截断
            return value.length > 8 ? `${value.slice(0, 8)}...` : value;
          },
        },
        axisLine: {
          lineStyle: {
            color: '#ddd',
          },
        },
      },
    ],
    yAxis: [
      {
        show: false,
      },
      {
        type: 'value',
        gridIndex: 1,
        splitLine: {
          lineStyle: {
            type: 'dashed',
            color: '#ddd',
          },
        },
        axisLabel: {
          fontSize: 10,
          color: '#666',
        },
      },
    ],
    grid: [
      {
        show: false,
      },
      {
        left: '52%',
        right: '5%',
        top: '15%',
        bottom: '15%',
      },
    ],
  });
};

// 监听变量名变化重新加载统计
// watch(selectedContextKey, () => {
//   if (selectedContextKey.value) {
//     loadContextStats();
//   }
// });

// 监听图表自身筛选条件变化
// watch([chartTenantFilter], () => {
//   loadContextStats();
// });

// 监听图表租户筛选变化，加载对应的 Agent 列表
watch(chartTenantFilter, async (newTenantId) => {
  // 加载该租户下的 Agent 列表
  if (newTenantId) {
    try {
      const agents = await getAgentSimpleListApi(newTenantId);
      filterAgentOptions.value = agents.map((a: AgentApi.SimpleItem) => ({
        label: `${a.agent_name} (${a.agent_code})`,
        value: a.agent_code,
      }));
    } catch (error) {
      console.error('加载图表 Agent 列表失败:', error);
      filterAgentOptions.value = [];
    }
  } else {
    filterAgentOptions.value = [];
  }
});

// 监听分布数据变化更新图表
watch(contextDistribution, () => {
  updateChart();
});

// 是否显示图表（有数据）
const showChart = computed(() => {
  return chartQueried.value && Boolean(selectedContextKey.value);
});

// ==================== 表格列定义 ====================

const businessColumns = [
  { title: 'ID', dataIndex: 'id', width: 80 },
  { title: 'Agent', dataIndex: 'agent_code', width: 150 },
  { title: '标题', dataIndex: 'title', ellipsis: true },
  { title: '状态', dataIndex: 'is_valid', width: 80 },
  { title: '审核', dataIndex: 'ban_scores', width: 100 }, // BAN类型：合法、腾讯等
  { title: '评分', dataIndex: 'critic_scores', width: 180 }, // CRITIC类型：营销、质量等
  { title: '业务入选', dataIndex: 'online_status', width: 90 },
  { title: '创建时间', dataIndex: 'create_time', width: 160 },
  { title: '操作', key: 'action', width: 80, fixed: 'right' as const },
];

// 分页显示的数据
// ==================== 方法 ====================

const fetchBusinessData = async () => {
  businessLoading.value = true;
  try {
    const params = buildContentListParams();
    // 直接使用分页参数
    params.page = businessParams.value.page;
    params.page_size = businessParams.value.page_size;

    const res = await listContentsApi(params);
    businessData.value = res.items;
    businessTotal.value = res.total;
  } finally {
    businessLoading.value = false;
  }
};

const handleSearch = () => {
  businessParams.value.page = 1;
  // 仅在选择变量名时刷新图表
  if (selectedContextKey.value) {
    chartQueried.value = true;
    loadContextStats();
  } else {
    chartQueried.value = false;
    contextDistribution.value = [];
    contextStatsMeta.value = {};
  }
  fetchBusinessData();
};

/** 分页变化处理 */
const handlePageChange = (page: number) => {
  businessParams.value.page = page;
  fetchBusinessData();
};

const handleExpertFilterChange = () => {
  const expertCode = businessParams.value.expert_config_code;
  if (expertCode) {
    const expert = expertOptions.value.find((opt) => opt.value === expertCode);
    if (expert?.expert_type === 'CRITIC') {
      businessParams.value.is_valid = 1;
    }
  }
};

/** 添加专家评分细化筛选 */
const addExpertScoreFilter = () => {
  expertScoreFilters.value.push({
    expert_config_code: '',
    min_score: undefined,
    max_score: undefined,
    passed: undefined,
  });
};

/** 移除专家评分细化筛选 */
const removeExpertScoreFilter = (index: number) => {
  expertScoreFilters.value.splice(index, 1);
};

const handleReset = () => {
  businessParams.value = {
    page: 1,
    page_size: 20,
    tenant_id: undefined,
    agent_code: undefined,
    expert_config_code: undefined,
    job_id: '',
    is_valid: undefined,
    is_test_case: undefined,
    online_status: undefined,
    keyword: '',
    create_time_start: undefined,
    create_time_end: undefined,
    order_by_create_time: 'desc',
    id_min: undefined,
    id_max: undefined,
  };
  expertScoreFilters.value = [];
  // 重置 Agent 筛选选项
  filterAgentOptions.value = [];
  // 重置任务选项
  jobOptions.value = [];
  // 重置专家筛选
  agentExpertCodes.value = [];
  selectedContextKey.value = undefined;
  chartQueried.value = false;
  contextDistribution.value = [];
  contextStatsMeta.value = {};
  handleSearch();
};

const showDetail = async (record: any) => {
  detailVisible.value = true;
  detailLoading.value = true;
  expertResults.value = [];

  try {
    currentDetail.value = record as ContentDetail;
    // 加载 Expert 业务结果（获取 CRITIC 审核信息）
    if (record.job_id && record.content_id) {
      expertResultsLoading.value = true;
      try {
        const results = await getContentExpertResultsApi(
          record.job_id as string,
          record.content_id as string,
        );
        expertResults.value = results || [];
      } catch (error) {
        console.error('Failed to fetch expert results:', error);
        expertResults.value = [];
      } finally {
        expertResultsLoading.value = false;
      }
    }
  } finally {
    detailLoading.value = false;
    // 递增雷达图 key，强制重新创建组件并触发渲染
    radarChartKey.value++;
  }
};

// ==================== 下拉加载 ====================

const loadTenants = async () => {
  try {
    const tenants = await getTenantSimpleListApi();
    tenantOptions.value = tenants.map((t) => ({
      label: t.tenant_name,
      value: t.id,
    }));
  } catch (error) {
    console.error('Failed to load tenants:', error);
  }
};

const loadJobs = async (tenantId?: number, agentCode?: string) => {
  try {
    const jobs = await getJobListApi({
      tenant_id: tenantId,
      agent_code: agentCode,
      limit: 100,
    });
    jobOptions.value = jobs.map((j) => ({
      label: j.job_name,
      value: j.job_id,
    }));
  } catch (error) {
    console.error('Failed to load jobs:', error);
  }
};

const loadOptions = async () => {
  // 只加载租户列表，任务列表需要先选择 Agent 后才加载
  await loadTenants();
};

// ==================== 联动逻辑 ====================

const handleTenantChange = async (value: any) => {
  businessParams.value.agent_code = undefined;
  agentExpertCodes.value = [];
  businessParams.value.job_id = '';
  // 清空任务选项（需要先选择 Agent 才能加载任务）
  jobOptions.value = [];
  // 加载该租户下的 Agent 列表用于筛选
  await loadFilterAgents(value as number | undefined);
};

/** Agent 变化时重新加载任务列表 */
const handleAgentChange = async (value: any) => {
  businessParams.value.job_id = '';
  // 根据当前租户和 Agent 加载任务列表
  await loadJobs(businessParams.value.tenant_id, value as string | undefined);
  await loadAgentExpertCodes(value as string | undefined);
  // 方案二：移除 Agent-专家关联校验，后端已改为基于 critic_score_record 表直接筛选
  // 用户选择的专家筛选不再受 Agent 配置限制
};

/** 加载筛选用的 Agent 列表 */
const loadFilterAgents = async (tenantId: number | undefined) => {
  filterAgentOptions.value = [];

  filterAgentLoading.value = true;
  try {
    // 不传 tenantId 时获取所有租户下的 Agent
    const agents = await getAgentSimpleListApi(tenantId);
    filterAgentOptions.value = agents.map((a: AgentApi.SimpleItem) => ({
      label: `${a.agent_name} (${a.agent_code})`,
      value: a.agent_code,
    }));
  } catch (error) {
    console.error('加载 Agent 列表失败:', error);
  } finally {
    filterAgentLoading.value = false;
  }
};

// ==================== 筛选持久化（URL 参数） ====================

/** 从 URL 参数初始化筛选条件 */
const initFiltersFromUrl = () => {
  const query = route.query;

  // 业务文章池筛选
  if (query.tenant_id) {
    businessParams.value.tenant_id = Number(query.tenant_id);
  }
  if (query.agent_code) {
    businessParams.value.agent_code = String(query.agent_code);
  }
  if (query.expert_config_code) {
    businessParams.value.expert_config_code = String(query.expert_config_code);
    const expertName =
      query.expert_config_name && String(query.expert_config_name).trim();
    if (expertName) {
      const exists = expertOptions.value.some(
        (opt) => opt.value === businessParams.value.expert_config_code,
      );
      if (!exists) {
        expertOptions.value = [
          ...expertOptions.value,
          {
            label: expertName,
            value: businessParams.value.expert_config_code,
            expert_config_name: expertName,
            expert_type: '',
            expert_func: '',
          },
        ];
      }
      // 激活专家视角提示
      expertViewActive.value = true;
      expertViewName.value = expertName;
    }
  }
  if (
    (query.is_valid === undefined || query.is_valid === '') &&
    businessParams.value.expert_config_code
  ) {
    const expert = expertOptions.value.find(
      (opt) => opt.value === businessParams.value.expert_config_code,
    );
    const expertType = expert?.expert_type
      ? normalize_expert_type(expert.expert_type)
      : null;
    if (expertType === 'CRITIC') {
      businessParams.value.is_valid = 1;
    }
  }
  if (query.job_id) {
    businessParams.value.job_id = String(query.job_id);
  }
  if (query.is_valid !== undefined && query.is_valid !== '') {
    businessParams.value.is_valid = Number(query.is_valid);
  }
  if (query.is_test_case !== undefined && query.is_test_case !== '') {
    businessParams.value.is_test_case = Number(query.is_test_case);
  }
  if (query.keyword) {
    businessParams.value.keyword = String(query.keyword);
  }
  if (query.page) {
    businessParams.value.page = Number(query.page);
  }
  if (query.page_size) {
    businessParams.value.page_size = Number(query.page_size);
  }
};

/** 退出专家视角 */
const exitExpertView = () => {
  expertViewActive.value = false;
  expertViewName.value = '';
  businessParams.value.expert_config_code = undefined;
  // 重新查询数据
  handleSearch();
};

// ==================== 生命周期 ====================

onMounted(async () => {
  // 先加载下拉选项
  await loadOptions();
  await loadExpertOptions();

  // 从 URL 初始化筛选条件
  initFiltersFromUrl();

  // 加载所有 Agent 列表（不依赖租户选择）
  await loadFilterAgents(businessParams.value.tenant_id);

  // 如果有 Agent，加载对应的任务列表
  if (businessParams.value.agent_code) {
    await loadJobs(
      businessParams.value.tenant_id,
      businessParams.value.agent_code,
    );
    await loadAgentExpertCodes(businessParams.value.agent_code);
  }

  // 加载数据
  fetchBusinessData();
  loadContextStats();
});

// ==================== 专家筛选逻辑 ====================

const loadExpertOptions = async () => {
  expertOptionsLoading.value = true;
  try {
    const list = await listExpertConfigOptionsApi();
    expertOptions.value = list.map((item: ExpertConfigOptionItem) => ({
      // 直接使用后端返回的 expert_config_name，如果没有则使用 expert_config_code
      label: item.expert_config_name || item.expert_config_code,
      value: item.expert_config_code,
      expert_config_name: item.expert_config_name || item.expert_config_code,
      expert_type: item.expert_type,
      expert_func: item.expert_func,
    }));
  } catch (error) {
    console.error('加载专家列表失败:', error);
    expertOptions.value = [];
  } finally {
    expertOptionsLoading.value = false;
  }
};

const loadAgentExpertCodes = async (agentCode?: string) => {
  agentExpertCodes.value = [];
  if (!agentCode) return;
  try {
    const agent = await getAgentApi(agentCode);
    agentExpertCodes.value = agent.expert_config_code_list || [];
  } catch (error) {
    console.error('加载 Agent 专家列表失败:', error);
    agentExpertCodes.value = [];
  }
};

const buildContentListParams = (): ContentApi.ContentListParams => {
  const params: ContentApi.ContentListParams = {
    page: businessParams.value.page,
    page_size: businessParams.value.page_size,
  };
  if (businessParams.value.tenant_id !== undefined) {
    params.tenant_id = businessParams.value.tenant_id;
  }
  if (businessParams.value.agent_code) {
    params.agent_code = businessParams.value.agent_code;
  }
  if (businessParams.value.expert_config_code) {
    params.expert_config_code = businessParams.value.expert_config_code;
  }
  if (businessParams.value.job_id) {
    params.job_id = businessParams.value.job_id;
  }
  if (businessParams.value.is_valid !== undefined) {
    params.is_valid = businessParams.value.is_valid;
  }
  if (businessParams.value.is_test_case !== undefined) {
    params.is_test_case = businessParams.value.is_test_case;
  }
  if (businessParams.value.online_status !== undefined) {
    params.online_status = businessParams.value.online_status;
  }
  if (businessParams.value.keyword) {
    params.keyword = businessParams.value.keyword;
  }
  if (businessParams.value.create_time_start) {
    params.create_time_start = businessParams.value.create_time_start;
  }
  if (businessParams.value.create_time_end) {
    params.create_time_end = businessParams.value.create_time_end;
  }
  if (businessParams.value.order_by_create_time) {
    params.order_by_create_time = businessParams.value.order_by_create_time;
  }
  // ID 范围筛选
  if (businessParams.value.id_min !== undefined) {
    params.id_min = businessParams.value.id_min;
  }
  if (businessParams.value.id_max !== undefined) {
    params.id_max = businessParams.value.id_max;
  }

  if (expertScoreFilters.value.length > 0) {
    // 过滤掉未选择专家的项
    const validFilters = expertScoreFilters.value.filter(
      (f) => f.expert_config_code,
    );
    if (validFilters.length > 0) {
      params.expert_score_filters = JSON.stringify(
        validFilters.map((f) => ({
          expert_config_code: f.expert_config_code,
          min_score: f.min_score,
          max_score: f.max_score,
          passed: f.passed,
        })),
      );
    }
  }

  return params;
};

/** 获取选中专家的类型 */
const getSelectedExpertType = (expertConfigCode: string) => {
  const expert = expertOptions.value.find(
    (opt) => opt.value === expertConfigCode,
  );
  return expert?.expert_type || 'CRITIC';
};

/** 判断是否为 BAN 类型专家 */
const isBanExpert = (expertConfigCode: string) => {
  return getSelectedExpertType(expertConfigCode) === 'BAN';
};

// ==================== 工具 ====================

const getValidColor = (val: unknown) => {
  if (val === 1) return 'success';
  if (val === 0) return 'error';
  return 'default';
};

const getValidText = (val: unknown) => {
  if (val === 1) return '有效';
  if (val === 0) return '无效';
  return '待定';
};

/** BAN 类型专家列表（评分为 0/1）- 作为 expert_type 字段缺失时的兜底 */
const banTypeExpertsFallback = new Set([
  'CriticCounterproductive',
  'CriticIllegal',
  'CriticKeywordFilter',
  'CriticTencent', // 腾讯风控审核
  'CriticUnreasonable',
]);

/** 判断是否为 ban 类型专家（优先使用 expert_type 字段，兜底使用 expert_func 名称） */
const isBanTypeExpert = (expertFunc: string, expertType?: string): boolean => {
  // 优先使用 expert_type 字段判断
  if (expertType) {
    return expertType.toUpperCase() === 'BAN';
  }
  // 兜底：使用 expert_func 名称判断（兼容旧数据）
  return banTypeExpertsFallback.has(expertFunc);
};

/** 根据评分和专家类型获取颜色 */
const getCriticScoreColor = (
  score: null | number | undefined,
  expertFunc?: string,
  expertType?: string,
) => {
  if (score === null || score === undefined) return 'default';

  // ban 类型：0/1，1 是通过（绿色），0 是不通过（红色）
  if (expertType === 'BAN') {
    return score === 1 ? 'success' : 'error';
  }
  if (expertFunc && isBanTypeExpert(expertFunc)) {
    return score === 1 ? 'success' : 'error';
  }

  // critic 类型：0-100 分
  if (score >= 80) return 'success';
  if (score >= 60) return 'warning';
  return 'error';
};

/** expert_func 转中文名称映射 */
const expertFuncNameMap: Record<string, string> = {
  // CRITIC 类型
  CriticContentQuality: '质量',
  CriticBrandAlign: '品牌',
  CriticCreativity: '创意',
  CriticPersonaAuth: '人设',
  CriticGrace: '优雅',
  CriticMarket: '营销',
  // BAN 类型
  CriticIllegal: '合法',
  CriticKeywordFilter: '违禁',
  CriticUnreasonable: '合理',
  CriticCounterproductive: '目的',
  CriticTencent: '腾讯',
};

/** 获取专家维度的中文简称 */
const getExpertFuncLabel = (expertFunc: string): string => {
  return expertFuncNameMap[expertFunc] || expertFunc.replace('Critic', '');
};

/** 从评分列表中筛选 BAN 类型的评分（合法、腾讯等） */
const filterBanScores = (
  scores: Array<{
    expert_func: string;
    expert_type?: string;
    reason?: string;
    score: number;
  }>,
) => {
  return scores.filter((s) => isBanTypeExpert(s.expert_func, s.expert_type));
};

/** 从评分列表中筛选 CRITIC 类型的评分（营销、质量、品牌等） */
const filterCriticScores = (
  scores: Array<{
    expert_func: string;
    expert_type?: string;
    reason?: string;
    score: number;
  }>,
) => {
  return scores.filter((s) => !isBanTypeExpert(s.expert_func, s.expert_type));
};

// ==================== 六维度评分雷达图 ====================

/** CRITIC 类型的六个维度 expert_func */
const criticDimensions = [
  'CriticContentQuality',
  'CriticBrandAlign',
  'CriticCreativity',
  'CriticPersonaAuth',
  'CriticGrace',
  'CriticMarket',
];

/** 雷达图的 key，每次打开详情时递增，强制重新创建组件 */
const radarChartKey = ref(0);

/** 获取 CRITIC 类型的六维度评分数据 */
const criticScoresForRadar = computed(() => {
  const summary = currentDetail.value?.critic_summary as
    | undefined
    | {
        scores?: Array<{ expert_func: string; reason?: string; score: number }>;
      };
  if (!summary?.scores) return null;

  // 筛选出 CRITIC 类型的六个维度评分（包含 reason）
  const scoreMap = new Map<string, { reason?: string; score: number }>();
  for (const item of summary.scores) {
    if (criticDimensions.includes(item.expert_func)) {
      scoreMap.set(item.expert_func, {
        score: item.score,
        reason: item.reason,
      });
    }
  }

  // 必须有至少1个维度评分才显示雷达图
  if (scoreMap.size === 0) return null;

  // 按固定顺序返回评分数据（包含 reason）
  return criticDimensions.map((dim) => ({
    dimension: dim,
    label: expertFuncNameMap[dim] || dim,
    score: scoreMap.get(dim)?.score ?? 0,
    hasScore: scoreMap.has(dim),
    reason: scoreMap.get(dim)?.reason,
  }));
});

/** 是否显示雷达图 */
const showRadarChart = computed(() => {
  return criticScoresForRadar.value !== null;
});

// ==================== 导入功能 ====================

const showImportModal = () => {
  importModalVisible.value = true;
  importForm.value = {
    tenant_id: undefined,
    agent_code: undefined,
    is_test_case: 0,
  };
  importFile.value = null;
  agentOptions.value = [];
};

const handleImportTenantChange = async (tenantId: any) => {
  importForm.value.agent_code = undefined;
  agentOptions.value = [];

  // 不传 tenantId 时获取所有租户下的 Agent
  try {
    const agents = await getAgentSimpleListApi(tenantId as number | undefined);
    agentOptions.value = agents.map((a: AgentApi.SimpleItem) => ({
      label: `${a.agent_name} (${a.agent_code})`,
      value: a.agent_code,
    }));
  } catch (error) {
    console.error('Failed to load agents:', error);
  }
};

const handleFileChange = (info: any) => {
  importFile.value = info.file;
};

const handleImportSubmit = async () => {
  // 验证
  if (!importForm.value.agent_code) {
    message.warning('请选择 Agent');
    return;
  }
  if (!importFile.value) {
    message.warning('请选择 CSV 文件');
    return;
  }

  importLoading.value = true;
  try {
    const result = await importContentsApi({
      file: importFile.value,
      tenant_id: importForm.value.tenant_id,
      agent_code: importForm.value.agent_code,
      is_test_case: importForm.value.is_test_case,
    });

    if (result.success_count > 0) {
      message.success(
        `导入成功！成功 ${result.success_count} 条${result.failed_count > 0 ? `，失败 ${result.failed_count} 条` : ''}`,
      );
      importModalVisible.value = false;
      // 刷新列表
      fetchBusinessData();
      loadContextStats();
    } else {
      message.error('导入失败，请检查 CSV 文件格式');
    }

    // 如果有错误信息，显示详情
    if (result.errors && result.errors.length > 0) {
      Modal.warning({
        title: '导入警告',
        content: result.errors.slice(0, 10).join('\n'),
        width: 500,
      });
    }
  } catch (error: unknown) {
    const errorMessage =
      error instanceof Error ? error.message : '导入失败，请稍后重试';
    message.error(errorMessage);
  } finally {
    importLoading.value = false;
  }
};

const handleImportCancel = () => {
  importModalVisible.value = false;
};

// ==================== 文章转移弹窗 ====================

const transferModalVisible = ref(false);
const transferLoading = ref(false);
const transferForm = ref({
  target_agent_code: undefined as string | undefined,
  skip_locked: true,
  skip_used: true,
});
const transferAgentOptions = ref<Array<{ label: string; value: string }>>([]);
// 从选中文章中提取的源 Agent 信息
const transferSourceAgent = ref<null | { code: string; name?: string }>(null);

/** 打开转移弹窗 */
const openTransferModal = async () => {
  if (selectedRows.value.length === 0) {
    message.warning('请先选择要转移的文章');
    return;
  }

  // 从选中文章中获取源 Agent
  // 检查是否所有文章来自同一个 Agent
  const uniqueAgents = new Set(
    selectedRows.value.map((row: any) => row.agent_code),
  );
  if (uniqueAgents.size > 1) {
    message.warning(
      `选中的文章来自 ${uniqueAgents.size} 个不同的 Agent，请分别选择同一 Agent 的文章进行转移`,
    );
    return;
  }

  const sourceAgentCode = selectedRows.value[0]?.agent_code;
  if (!sourceAgentCode) {
    message.warning('无法获取文章的 Agent 信息');
    return;
  }

  transferSourceAgent.value = {
    code: sourceAgentCode,
    name: (selectedRows.value[0] as any)?.agent_name,
  };

  // 加载目标 Agent 选项（排除源 Agent）
  try {
    const agents = await getAgentSimpleListApi();
    transferAgentOptions.value = agents
      .filter((a: AgentApi.SimpleItem) => a.agent_code !== sourceAgentCode)
      .map((a: AgentApi.SimpleItem) => ({
        label: `${a.agent_name} (${a.agent_code})`,
        value: a.agent_code,
      }));
  } catch (error) {
    console.error('Failed to load agents:', error);
  }
  transferModalVisible.value = true;
};

/** 提交转移 */
const handleTransferSubmit = async () => {
  if (!transferForm.value.target_agent_code) {
    message.warning('请选择目标 Agent');
    return;
  }

  if (!transferSourceAgent.value?.code) {
    message.warning('无法获取源 Agent 信息');
    return;
  }

  transferLoading.value = true;
  try {
    // 构建转移参数
    const params = {
      // 从选中行中提取 content_id（后端使用 content_id 而不是技术主键 id）
      content_ids: selectedRows.value.map((row: any) => row.content_id),
      skip_locked: transferForm.value.skip_locked,
      skip_used: transferForm.value.skip_used,
    };

    const result = await transferContentsApi(
      transferSourceAgent.value.code,
      transferForm.value.target_agent_code,
      params,
    );

    const msgParts = [`成功转移 ${result.success_count} 篇文章`];
    if (result.skipped_locked_count > 0) {
      msgParts.push(`跳过 ${result.skipped_locked_count} 篇已锁定`);
    }
    if (result.skipped_used_count > 0) {
      msgParts.push(`跳过 ${result.skipped_used_count} 篇已使用`);
    }

    message.success(msgParts.join('，'));
    transferModalVisible.value = false;
    transferSourceAgent.value = null;

    // 刷新列表
    await fetchBusinessData();
    // 清空选择
    selectedRowKeys.value = [];
    selectedRows.value = [];
  } catch (error: unknown) {
    const errorMessage =
      error instanceof Error ? error.message : '转移失败，请稍后重试';
    message.error(errorMessage);
  } finally {
    transferLoading.value = false;
  }
};

const handleTransferCancel = () => {
  transferModalVisible.value = false;
};
</script>

<template>
  <Page>
    <div
      class="sticky top-0 z-10 -mx-4 -mt-4 mb-3 bg-background/90 px-4 pb-4 pt-2 shadow-lg backdrop-blur-md"
      style="border-bottom: 1px solid hsl(var(--border) / 30%)"
    >
      <div class="mb-2 flex items-center gap-3">
        <span
          class="bg-gradient-to-r from-[hsl(var(--primary))] to-[#22c55e] bg-clip-text text-xl font-bold text-transparent"
        >
          {{ route.meta.title || '文章池' }}
        </span>
      </div>
    </div>

    <!-- 文章列表卡片 -->
    <Card>
      <!-- 专家视角提示条 -->
      <Alert
        v-if="expertViewActive"
        :message="`当前专家视角：${expertViewName} - 找到 ${businessTotal} 篇相关文章`"
        type="info"
        show-icon
        closable
        class="expert-view-alert mb-4"
        @close="exitExpertView"
      >
        <template #icon>
          <InfoCircleOutlined />
        </template>
        <template #description>
          <div class="flex items-center justify-between">
            <span class="text-sm text-muted-foreground">
              正在查看专家相关的文章。您可以点击右侧按钮退出专家视角。
            </span>
            <Button type="link" size="small" danger @click="exitExpertView">
              <CloseCircleOutlined />
              退出专家视角
            </Button>
          </div>
        </template>
      </Alert>

      <!-- 业务搜索 -->
      <Form layout="inline" class="mb-4">
        <FormItem v-if="false" label="租户">
          <Select
            v-model:value="businessParams.tenant_id"
            placeholder="请选择"
            style="width: 160px"
            allow-clear
            show-search
            :filter-option="true"
            @change="handleTenantChange"
          >
            <Select.Option
              v-for="opt in tenantOptions"
              :key="opt.value"
              :value="opt.value"
            >
              {{ opt.label }}
            </Select.Option>
          </Select>
        </FormItem>
        <FormItem label="Agent" :title="selectedAgentLabel">
          <Select
            v-model:value="businessParams.agent_code"
            placeholder="请选择"
            style="width: 180px"
            allow-clear
            :loading="filterAgentLoading"
            :disabled="false"
            show-search
            :filter-option="true"
            :title="selectedAgentLabel"
            @change="handleAgentChange"
          >
            <Select.Option
              v-for="opt in filterAgentOptions"
              :key="opt.value"
              :value="opt.value"
              :title="opt.label"
            >
              {{ opt.label }}
            </Select.Option>
          </Select>
        </FormItem>
        <FormItem label="Expert">
          <Select
            v-model:value="businessParams.expert_config_code"
            placeholder="请选择"
            style="width: 200px"
            allow-clear
            :loading="expertOptionsLoading"
            show-search
            :filter-option="expertFilterOption"
            :options="filteredExpertOptions"
            @change="handleExpertFilterChange"
          />
        </FormItem>
        <FormItem label="任务">
          <Select
            v-model:value="businessParams.job_id"
            :placeholder="
              businessParams.agent_code ? '请选择' : '请先选择Agent'
            "
            style="width: 180px"
            allow-clear
            :disabled="!businessParams.agent_code"
            show-search
            :filter-option="true"
          >
            <Select.Option
              v-for="opt in jobOptions"
              :key="opt.value"
              :value="opt.value"
            >
              {{ opt.label }}
            </Select.Option>
          </Select>
        </FormItem>
        <FormItem label="有效筛选">
          <Select
            v-model:value="businessParams.is_valid"
            placeholder="有效筛选"
            style="width: 120px"
            allow-clear
          >
            <Select.Option :value="1">有效</Select.Option>
            <Select.Option :value="0">无效</Select.Option>
          </Select>
        </FormItem>
        <FormItem label="是否入选">
          <Select
            v-model:value="businessParams.online_status"
            placeholder="是否入选"
            style="width: 120px"
            allow-clear
          >
            <Select.Option value="ONLINE">已入选</Select.Option>
            <Select.Option value="OFFLINE">未入选</Select.Option>
          </Select>
        </FormItem>
        <FormItem label="变量名">
          <Select
            v-model:value="selectedContextKey"
            style="min-width: 160px"
            placeholder="选择变量名"
            show-search
            :filter-option="true"
          >
            <SelectOption v-for="key in contextKeys" :key="key" :value="key">
              {{ key }}
            </SelectOption>
          </Select>
        </FormItem>
        <FormItem>
          <Button type="link" size="small" @click="addExpertScoreFilter">
            <PlusOutlined />
            添加专家评分筛选
          </Button>
        </FormItem>
        <FormItem label="关键词">
          <Input
            v-model:value="businessParams.keyword"
            placeholder="标题/正文"
            style="width: 200px"
            @press-enter="handleSearch"
          />
        </FormItem>
        <FormItem label="ID范围">
          <InputNumber
            v-model:value="businessParams.id_min"
            :min="1"
            placeholder="最小ID"
            style="width: 120px"
            :controls="false"
          />
          <span class="mx-2 text-muted">~</span>
          <InputNumber
            v-model:value="businessParams.id_max"
            :min="1"
            placeholder="最大ID"
            style="width: 120px"
            :controls="false"
          />
        </FormItem>
        <FormItem label="创建时间">
          <RangePicker
            :value="
              businessParams.create_time_start && businessParams.create_time_end
                ? [
                    dayjs(businessParams.create_time_start),
                    dayjs(businessParams.create_time_end),
                  ]
                : undefined
            "
            show-time
            format="YYYY-MM-DD HH:mm:ss"
            style="width: 400px"
            @change="
              (dates: any) => {
                if (dates && dates[0] && dates[1]) {
                  businessParams.create_time_start = dates[0].toISOString();
                  businessParams.create_time_end = dates[1].toISOString();
                } else {
                  businessParams.create_time_start = undefined;
                  businessParams.create_time_end = undefined;
                }
              }
            "
          />
        </FormItem>
        <FormItem label="时间排序">
          <Select
            v-model:value="businessParams.order_by_create_time"
            style="width: 120px"
          >
            <SelectOption value="desc">最新优先</SelectOption>
            <SelectOption value="asc">最早优先</SelectOption>
          </Select>
        </FormItem>

        <!-- 专家评分细化筛选面板 -->
        <div
          v-if="expertScoreFilters.length > 0"
          class="expert-score-filters-block mb-4 w-full rounded-md border border-dashed p-3"
          style="
            background-color: hsl(var(--card) / 50%);
            border-color: hsl(var(--border));
          "
        >
          <div class="mb-2 flex items-center justify-between">
            <span class="text-sm font-medium">专家评分细化筛选 (且关系)</span>
            <Button type="link" size="small" @click="addExpertScoreFilter">
              <PlusOutlined />
              继续添加
            </Button>
          </div>
          <div class="flex flex-wrap gap-x-6 gap-y-3">
            <div
              v-for="(filter, index) in expertScoreFilters"
              :key="index"
              class="flex items-center gap-2"
            >
              <span class="text-xs text-muted-foreground">专家:</span>
              <Select
                v-model:value="filter.expert_config_code"
                placeholder="选择专家"
                style="width: 220px"
                show-search
                allow-clear
                size="small"
                :filter-option="expertFilterOption"
                :options="filteredExpertOptions"
              />
              <!-- CRITIC类型: 显示分数范围 -->
              <template v-if="!isBanExpert(filter.expert_config_code)">
                <span class="ml-1 text-xs text-muted-foreground">评分:</span>
                <InputNumber
                  v-model:value="filter.min_score"
                  placeholder="最小"
                  size="small"
                  :min="0"
                  :max="100"
                  style="width: 70px"
                />
                <span class="text-muted-foreground">～</span>
                <InputNumber
                  v-model:value="filter.max_score"
                  placeholder="最大"
                  size="small"
                  :min="0"
                  :max="100"
                  style="width: 70px"
                />
              </template>
              <!-- BAN类型: 显示通过/不通过 -->
              <template v-else>
                <span class="ml-1 text-xs text-muted-foreground">状态:</span>
                <Select
                  v-model:value="filter.passed"
                  placeholder="全部"
                  size="small"
                  style="width: 100px"
                  allow-clear
                >
                  <SelectOption :value="true">通过</SelectOption>
                  <SelectOption :value="false">不通过</SelectOption>
                </Select>
              </template>
              <Button
                type="text"
                danger
                size="small"
                class="flex items-center justify-center p-0"
                @click="removeExpertScoreFilter(index)"
              >
                <DeleteOutlined />
              </Button>
            </div>
          </div>
        </div>

        <FormItem>
          <Space>
            <Button type="primary" @click="handleSearch">查询</Button>
            <Button @click="handleReset">重置</Button>
            <Button type="default" @click="showImportModal">
              <UploadOutlined />
              导入
            </Button>
          </Space>
        </FormItem>
      </Form>

      <!-- Context 分布统计卡片 -->
      <Card v-if="showChart" :bordered="false" class="mb-4">
        <Spin :spinning="chartLoading">
          <div v-if="contextDistribution.length > 0" class="h-[300px] w-full">
            <EchartsUI ref="chartRef" />
          </div>
          <Empty v-else description="暂无分布数据" class="py-8" />
        </Spin>
      </Card>

      <!-- 批量操作栏 -->
      <div v-if="selectedRowKeys.length > 0" class="batch-action-bar">
        <Space>
          <span class="text-muted">
            已选择 <strong>{{ selectedRowKeys.length }}</strong> 篇文章
          </span>
          <Button type="primary" @click="openBatchScoreModal">
            批量评分
          </Button>
          <Button type="primary" @click="handle_go_calibration_workbench">
            去校准
          </Button>
          <Button @click="openTransferModal">
            <SwapOutlined />
            转移文章
          </Button>
          <Button
            type="primary"
            :loading="batchOnlineLoading"
            @click="handleBatchOnline"
          >
            批量上线
          </Button>
          <Button
            danger
            :loading="batchOfflineLoading"
            @click="handleBatchOffline"
          >
            批量下线
          </Button>
          <Button @click="exportSelectedToXLSX">
            <DownloadOutlined />
            导出 XLSX
          </Button>
          <Button
            @click="
              selectedRowKeys = [];
              selectedRows = [];
            "
          >
            取消选择
          </Button>
        </Space>
      </div>

      <!-- 业务表格 -->
      <Table
        :columns="businessColumns"
        :data-source="businessData"
        :loading="businessLoading"
        :pagination="false"
        :row-selection="rowSelection"
        row-key="id"
        class="article-table"
      >
        <template #title>
          <div class="flex items-center justify-between">
            <span class="text-sm text-gray-500">
              共 {{ businessTotal }} 篇业务文章
            </span>
          </div>
        </template>
        <template #bodyCell="{ column, record }">
          <!-- 标题列：悬停预览 -->
          <template v-if="column.dataIndex === 'title'">
            <Popover
              placement="rightTop"
              trigger="hover"
              overlay-class-name="article-preview-popover"
            >
              <template #content>
                <div class="article-preview">
                  <div class="article-preview-title">
                    {{ record.title || '(无标题)' }}
                  </div>
                  <div class="article-preview-meta">
                    <Tag
                      :color="
                        record.is_valid === 1
                          ? 'green'
                          : record.is_valid === 0
                            ? 'red'
                            : 'default'
                      "
                      size="small"
                    >
                      {{
                        record.is_valid === 1
                          ? '有效'
                          : record.is_valid === 0
                            ? '无效'
                            : '待定'
                      }}
                    </Tag>
                    <Tag
                      :color="record.is_test_case === 1 ? 'orange' : 'blue'"
                      size="small"
                    >
                      {{ record.is_test_case === 1 ? '测试' : '业务' }}
                    </Tag>
                  </div>
                  <Divider class="my-2" />
                  <div class="article-preview-content">
                    {{
                      record.content
                        ? record.content.slice(0, 300) +
                          (record.content.length > 300 ? '...' : '')
                        : '(无内容)'
                    }}
                  </div>
                </div>
              </template>
              <span class="article-title-link">
                {{ record.title || '(无标题)' }}
              </span>
            </Popover>
          </template>
          <template v-else-if="column.dataIndex === 'is_valid'">
            <Badge
              :status="getValidColor(record.is_valid)"
              :text="getValidText(record.is_valid)"
            />
          </template>
          <!-- 审核列：显示 BAN 类型专家的评分（合法、腾讯等） -->
          <template v-else-if="column.dataIndex === 'ban_scores'">
            <template
              v-if="
                record.critic_summary?.scores &&
                filterBanScores(record.critic_summary.scores).length > 0
              "
            >
              <div class="score-list">
                <template
                  v-for="(scoreItem, idx) in filterBanScores(
                    record.critic_summary.scores,
                  )"
                  :key="idx"
                >
                  <!-- CriticKeywordFilter 仅在 score=0（有违禁词）时显示 -->
                  <Popover
                    v-if="
                      !(
                        scoreItem.expert_func === 'CriticKeywordFilter' &&
                        scoreItem.score === 1
                      )
                    "
                    placement="top"
                  >
                    <template #content>
                      <div class="score-popover">
                        <div class="font-medium">
                          {{ scoreItem.expert_func }}
                        </div>
                        <div
                          v-if="scoreItem.reason"
                          class="mt-1 text-xs text-muted"
                        >
                          {{ scoreItem.reason }}
                        </div>
                      </div>
                    </template>
                    <Tag
                      :color="
                        getCriticScoreColor(
                          scoreItem.score,
                          scoreItem.expert_func,
                          scoreItem.expert_type,
                        )
                      "
                      size="small"
                      class="score-tag-with-label"
                    >
                      <span class="score-label">
                        {{ getExpertFuncLabel(scoreItem.expert_func) }}
                      </span>
                      <span class="score-value">{{ scoreItem.score }}</span>
                    </Tag>
                  </Popover>
                </template>
              </div>
            </template>
            <span v-else class="text-muted">-</span>
          </template>
          <!-- 评分列：显示 CRITIC 类型专家的评分（营销、质量、品牌等） -->
          <template v-else-if="column.dataIndex === 'critic_scores'">
            <template
              v-if="
                record.critic_summary?.scores &&
                filterCriticScores(record.critic_summary.scores).length > 0
              "
            >
              <div class="score-list">
                <template
                  v-for="(scoreItem, idx) in filterCriticScores(
                    record.critic_summary.scores,
                  )"
                  :key="idx"
                >
                  <Popover placement="top">
                    <template #content>
                      <div class="score-popover">
                        <div class="font-medium">
                          {{ scoreItem.expert_func }}
                        </div>
                        <div
                          v-if="scoreItem.reason"
                          class="mt-1 text-xs text-muted"
                        >
                          {{ scoreItem.reason }}
                        </div>
                      </div>
                    </template>
                    <Tag
                      :color="
                        getCriticScoreColor(
                          scoreItem.score,
                          scoreItem.expert_func,
                          scoreItem.expert_type,
                        )
                      "
                      size="small"
                      class="score-tag-with-label"
                    >
                      <span class="score-label">
                        {{ getExpertFuncLabel(scoreItem.expert_func) }}
                      </span>
                      <span class="score-value">{{ scoreItem.score }}</span>
                    </Tag>
                  </Popover>
                </template>
              </div>
            </template>
            <span v-else class="text-muted">-</span>
          </template>
          <!-- Agent列 -->
          <template v-else-if="column.dataIndex === 'agent_code'">
            <div
              v-if="record.agent_name || record.agent_code"
              class="agent-capsule"
            >
              <span class="agent-label">{{
                record.agent_name || record.agent_code
              }}</span>
            </div>
            <span v-else class="text-muted">-</span>
          </template>
          <!-- 业务入选列 -->
          <template v-else-if="column.dataIndex === 'online_status'">
            <Tag
              v-if="record.online_status === 'ONLINE'"
              color="success"
              size="small"
            >
              已入选
            </Tag>
            <Tag
              v-else-if="record.online_status === 'OFFLINE'"
              color="default"
              size="small"
            >
              未入选
            </Tag>
            <span v-else class="text-muted">-</span>
          </template>
          <template v-else-if="column.dataIndex === 'create_time'">
            {{ formatDateTime(record.create_time) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <Button type="link" @click="showDetail(record)">详情</Button>
          </template>
        </template>
      </Table>

      <!-- 分页器 + 加载更多按钮 -->
      <div class="mt-4 flex items-center justify-between">
        <div class="flex items-center gap-4">
          <div class="sm text-muted">
            <span v-if="businessTotal > 0"> 共 {{ businessTotal }} 篇) </span>
            <span v-else>暂无数据</span>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <!-- 分页器 -->
          <Pagination
            v-model:current="businessParams.page"
            v-model:page-size="businessParams.page_size"
            :total="businessTotal"
            :show-size-changer="true"
            :page-size-options="['10', '20', '50', '100']"
            @change="handlePageChange"
          />
        </div>
      </div>
    </Card>

    <!-- 详情抽屉 -->
    <Drawer
      v-model:open="detailVisible"
      title="文章详情"
      width="900"
      placement="right"
      class="article-detail-drawer"
    >
      <div v-if="detailLoading" class="flex justify-center py-10">
        <Spin size="large" />
      </div>
      <div v-else-if="currentDetail">
        <Descriptions title="基本信息" bordered :column="2" size="small">
          <Descriptions.Item label="ID">
            {{ currentDetail?.id }}
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">
            {{ formatDateTime(currentDetail?.create_time as string) }}
          </Descriptions.Item>
          <Descriptions.Item label="Job ID" :span="2">
            {{ currentDetail?.job_id }}
          </Descriptions.Item>
          <Descriptions.Item label="内容 ID" :span="2">
            {{ currentDetail?.content_id }}
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag v-if="currentDetail?.is_valid === 1" color="green"> 有效 </Tag>
            <Tag v-else-if="currentDetail?.is_valid === 0" color="red">
              无效
            </Tag>
            <Tag v-else color="default">待定</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="测试/业务">
            <Tag :color="currentDetail?.is_test_case === 1 ? 'orange' : 'blue'">
              {{ currentDetail?.is_test_case === 1 ? '测试' : '业务' }}
            </Tag>
          </Descriptions.Item>
          <!-- Critic 评分汇总 -->
          <template v-if="currentDetail?.critic_summary">
            <Descriptions.Item label="评分汇总" :span="2">
              <Space :size="12" wrap>
                <span>
                  <span class="text-muted">平均分：</span>
                  <Tag
                    :color="
                      getCriticScoreColor(
                        currentDetail?.critic_summary?.avg_score,
                      )
                    "
                  >
                    {{
                      currentDetail?.critic_summary?.avg_score !== null
                        ? currentDetail?.critic_summary?.avg_score
                        : '-'
                    }}
                  </Tag>
                </span>
                <span>
                  <span class="text-muted">最低分：</span>
                  <Tag
                    :color="
                      getCriticScoreColor(
                        currentDetail?.critic_summary?.min_score,
                      )
                    "
                  >
                    {{
                      currentDetail?.critic_summary?.min_score !== null
                        ? currentDetail?.critic_summary?.min_score
                        : '-'
                    }}
                  </Tag>
                </span>
                <span>
                  <span class="text-muted">通过/总数：</span>
                  <span class="text-success">
                    {{ currentDetail?.critic_summary?.passed_count }}
                  </span>
                  /
                  {{ currentDetail?.critic_summary?.total_critics }}
                </span>
                <span v-if="currentDetail?.critic_summary?.has_ban_issue">
                  <Tag color="red">存在合规问题</Tag>
                </span>
                <span
                  v-if="(currentDetail?.critic_summary?.problem_count || 0) > 0"
                >
                  <span class="text-muted">问题数：</span>
                  <Tag color="warning">
                    {{ currentDetail?.critic_summary?.problem_count }}
                  </Tag>
                </span>
              </Space>
            </Descriptions.Item>
            <!-- 六维度评分雷达图 -->
            <Descriptions.Item v-if="showRadarChart" label="维度分布" :span="2">
              <div class="radar-chart-container">
                <ScoreRadarChart
                  :key="radarChartKey"
                  :scores="criticScoresForRadar || []"
                  width="280px"
                  height="220px"
                />
              </div>
            </Descriptions.Item>
          </template>
          <!-- CRITIC 违禁词检测结果（仅当无效时显示） -->
          <template v-if="currentDetail.is_valid === 0">
            <Descriptions.Item
              v-for="(info, idx) in criticInfoList"
              :key="idx"
              :label="`Reason (${info.expertCode})`"
              :span="2"
            >
              <span class="critic-reason">{{ info.reason || '-' }}</span>
            </Descriptions.Item>
            <Descriptions.Item
              v-for="(info, idx) in criticInfoList"
              :key="`snippet-${idx}`"
              :label="`违禁词 (${info.expertCode})`"
              :span="2"
            >
              <div
                v-if="info.problemSnippets.length > 0"
                class="forbidden-words"
              >
                <Tag
                  v-for="word in info.problemSnippets"
                  :key="word"
                  color="red"
                  class="forbidden-word-tag"
                >
                  {{ word }}
                </Tag>
              </div>
              <span v-else class="no-problems">-</span>
            </Descriptions.Item>
          </template>
        </Descriptions>

        <Divider />

        <!-- 文章正文（违禁词高亮） -->
        <div>
          <h4 class="mb-2 font-bold">文章详情</h4>
          <div v-if="currentDetail.title" class="mb-2 text-lg font-bold">
            {{ currentDetail.title }}
          </div>
          <div class="content-wrapper">
            <!-- eslint-disable vue/no-v-html -->
            <div
              v-if="allForbiddenWords.length > 0 && currentDetail.content"
              class="content-with-highlight"
              v-html="highlightedContent"
            ></div>
            <!-- eslint-enable vue/no-v-html -->
            <div
              v-else
              class="whitespace-pre-wrap rounded border p-4"
              style="
                background-color: hsl(var(--card));
                border-color: hsl(var(--border));
              "
            >
              {{
                currentDetail?.content ||
                (currentDetail as any)?.output_content ||
                '无内容'
              }}
            </div>
            <span
              v-if="
                currentDetail?.content || (currentDetail as any)?.output_content
              "
              class="char-count"
            >
              {{ contentCharCount }}字
            </span>
          </div>
        </div>

        <Divider />

        <!-- Expert 执行记录 -->
        <div>
          <h4 class="mb-2 font-bold">
            Expert 执行记录
            <span v-if="expertResultsLoading" class="ml-2">
              <Spin size="small" />
            </span>
            <span v-else class="text-sm font-normal text-gray-400">
              ({{ expertResults.length }})
            </span>
          </h4>
          <div
            v-if="expertResults.length === 0 && !expertResultsLoading"
            class="text-gray-400"
          >
            暂无 Expert 执行记录
          </div>
          <div v-else class="expert-results-list">
            <Card
              v-for="result in expertResults"
              :key="result.id"
              size="small"
              class="expert-result-card"
            >
              <template #title>
                <Space wrap>
                  <Tag color="blue">{{ result.expert_config_code }}</Tag>
                  <Tag v-if="result.model_code" color="cyan">
                    {{ result.model_code }}
                  </Tag>
                  <span v-if="result.expert_config_name" class="expert-name">
                    {{ result.expert_config_name }}
                  </span>
                  <Tag v-if="result.business_type" color="purple">
                    {{ result.business_type }}
                  </Tag>
                  <Tag
                    v-if="result.status"
                    :color="result.status === 'SUCCESS' ? 'green' : 'red'"
                  >
                    {{ result.status }}
                  </Tag>
                </Space>
              </template>
              <template #extra>
                <span class="result-time">
                  {{ formatDateTime(result.create_time) }}
                </span>
              </template>
              <!-- 评分结果快速预览 -->
              <div v-if="result.business_result" class="expert-result-summary">
                <Space :size="16" wrap>
                  <span
                    v-if="(result.business_result as any).score !== undefined"
                  >
                    <span class="text-muted">AI评分：</span>
                    <Tag
                      :color="
                        getCriticScoreColor(
                          (result.business_result as any).score,
                          result.expert_func,
                          result.expert_type,
                        )
                      "
                    >
                      {{ (result.business_result as any).score }}
                    </Tag>
                  </span>
                  <span
                    v-if="(result.business_result as any).passed !== undefined"
                  >
                    <Tag
                      :color="
                        (result.business_result as any).passed
                          ? 'success'
                          : 'error'
                      "
                    >
                      {{
                        (result.business_result as any).passed
                          ? '通过'
                          : '不通过'
                      }}
                    </Tag>
                  </span>
                  <span
                    v-if="
                      ((result.business_result as any).problem_tags?.length ||
                        0) > 0 ||
                      ((result.business_result as any).problem_snippets
                        ?.length || 0) > 0
                    "
                  >
                    <Tag color="warning">
                      {{
                        ((result.business_result as any).problem_tags?.length ||
                          0) +
                        ((result.business_result as any).problem_snippets
                          ?.length || 0)
                      }}
                      个问题
                    </Tag>
                  </span>
                </Space>
                <!-- AI评分理由 -->
                <div
                  v-if="(result.business_result as any).reason"
                  class="expert-result-reason"
                >
                  <span class="text-muted">AI理由：</span>
                  {{ (result.business_result as any).reason }}
                </div>
                <!-- 问题片段/违禁词 -->
                <div
                  v-if="
                    ((result.business_result as any).problem_snippets?.length ||
                      0) > 0
                  "
                  class="expert-result-snippets"
                >
                  <span class="text-muted">问题片段：</span>
                  <Tag
                    v-for="snippet in (result.business_result as any)
                      .problem_snippets"
                    :key="snippet"
                    color="red"
                    size="small"
                  >
                    {{ snippet }}
                  </Tag>
                </div>
                <!-- 精彩摘录（CRITIC 类专家） -->
                <div
                  v-if="(result.business_result as any).highlights"
                  class="expert-result-highlights"
                >
                  <span class="text-muted">精彩摘录：</span>
                  <span class="highlights-text">
                    {{ (result.business_result as any).highlights }}
                  </span>
                </div>
              </div>
              <div v-if="result.error_message" class="error-message">
                <Tag color="red">错误</Tag>
                {{ result.error_message }}
              </div>
            </Card>
          </div>
        </div>

        <template
          v-if="
            currentDetail?.prompt || (currentDetail as any)?.rendered_prompt
          "
        >
          <Divider />

          <div>
            <h4 class="mb-2 font-bold">渲染后的提示词 (Prompt)</h4>
            <div
              class="max-h-60 overflow-y-auto whitespace-pre-wrap rounded border p-3 text-sm"
              style="
                background-color: hsl(var(--muted));
                border-color: hsl(var(--border));
              "
            >
              {{
                currentDetail?.prompt || (currentDetail as any)?.rendered_prompt
              }}
            </div>
          </div>
        </template>

        <template
          v-if="
            currentDetail?.context_list ||
            (currentDetail as any)?.plugin_config_snapshot
          "
        >
          <Divider />

          <div>
            <h4 class="mb-2 font-bold">传入参数 / 上下文快照</h4>
            <div
              class="max-h-60 overflow-y-auto rounded border p-3 text-sm"
              style="
                background-color: hsl(var(--muted));
                border-color: hsl(var(--border));
              "
            >
              <pre>{{
                JSON.stringify(
                  currentDetail?.context_list ||
                    (currentDetail as any)?.plugin_config_snapshot,
                  null,
                  2,
                )
              }}</pre>
            </div>
          </div>
        </template>
      </div>
      <Empty v-else description="暂无详情数据" />
    </Drawer>

    <!-- 导入弹窗 -->
    <Modal
      v-model:open="importModalVisible"
      title="导入文章"
      :confirm-loading="importLoading"
      @ok="handleImportSubmit"
      @cancel="handleImportCancel"
    >
      <Form layout="vertical" class="import-form">
        <FormItem v-if="false" label="租户" required>
          <Select
            v-model:value="importForm.tenant_id"
            placeholder="请选择租户"
            style="width: 100%"
            :options="tenantOptions"
            show-search
            :filter-option="true"
            @change="handleImportTenantChange"
          />
        </FormItem>
        <FormItem label="Agent" required>
          <Select
            v-model:value="importForm.agent_code"
            placeholder="请选择Agent"
            style="width: 100%"
            :options="agentOptions"
            :disabled="false"
            show-search
            :filter-option="true"
          />
        </FormItem>
        <FormItem label="类型">
          <Select v-model:value="importForm.is_test_case" style="width: 100%">
            <SelectOption :value="0">业务数据</SelectOption>
            <SelectOption :value="1">测试数据</SelectOption>
          </Select>
        </FormItem>
        <FormItem label="CSV 文件" required>
          <Upload
            :before-upload="() => false"
            :max-count="1"
            accept=".csv"
            @change="handleFileChange"
          >
            <Button>
              <UploadOutlined />
              选择文件
            </Button>
          </Upload>
          <div class="import-tips">
            <p>CSV 文件格式要求：</p>
            <ul>
              <li>必须列：<code>content</code>（正文内容）</li>
              <li>
                可选列：<code>title</code>（标题）、<code>context_list</code>（JSON
                格式的上下文变量）
              </li>
            </ul>
          </div>
        </FormItem>
      </Form>
    </Modal>

    <!-- 批量评分弹窗 -->
    <Modal
      v-model:open="batchScoreModalVisible"
      title="批量评分"
      :confirm-loading="batchScoreSubmitting"
      :ok-text="batchScoreSubmitting ? '提交中...' : '开始评分'"
      @ok="handleBatchScore"
    >
      <Form layout="vertical">
        <FormItem label="已选择文章" class="mb-4">
          <div class="selected-articles-info">
            <Tag color="blue">{{ selectedRowKeys.length }} 篇</Tag>
            <span class="ml-2 text-muted">
              将对这些文章执行选定的 Expert 评分
            </span>
          </div>
        </FormItem>
        <FormItem label="选择 Expert（CRITIC/BAN 类型，支持多选）" required>
          <Select
            v-model:value="batchScoreForm.expert_config_codes"
            mode="multiple"
            placeholder="请选择要执行的 Expert（可多选）"
            style="width: 100%"
            :loading="expertConfigLoading"
            :disabled="batchScoreSubmitting"
            show-search
            :max-tag-count="3"
            :get-popup-container="(trigger) => trigger.parentElement"
            :filter-option="
              (input: string, option: any) =>
                (option?.label || '')
                  .toLowerCase()
                  .includes(input.toLowerCase())
            "
          >
            <SelectOption
              v-for="opt in expertConfigOptions"
              :key="opt.value"
              :value="opt.value"
              :label="opt.label"
            >
              <div class="expert-option">
                <span>{{ opt.label }}</span>
              </div>
            </SelectOption>
          </Select>
        </FormItem>
        <FormItem label="并发数">
          <InputNumber
            v-model:value="batchScoreForm.concurrency"
            :min="1"
            :max="20"
            style="width: 100%"
            :disabled="batchScoreSubmitting"
          />
          <div class="mt-1 text-xs text-muted-foreground">
            同时评分的文章数量，建议 3-5（1-20）
          </div>
        </FormItem>

        <div class="batch-score-tips">
          <p class="text-muted">
            提示：批量评分将对选中的文章并行执行所选 Expert
            的评分逻辑，每个专家独立运行，评分结果会更新到 critic_score_record
            表中。
          </p>
        </div>
      </Form>
    </Modal>

    <!-- 文章转移弹窗 -->
    <Modal
      v-model:open="transferModalVisible"
      title="转移文章"
      :confirm-loading="transferLoading"
      :ok-text="transferLoading ? '转移中...' : '确定转移'"
      :ok-button-props="{ disabled: transferLoading }"
      :closable="!transferLoading"
      :mask-closable="!transferLoading"
      width="520px"
      @ok="handleTransferSubmit"
      @cancel="handleTransferCancel"
    >
      <Form layout="vertical">
        <!-- 源 Agent 信息 -->
        <FormItem label="源 Agent">
          <div class="transfer-source-info">
            <Tag color="blue">
              {{
                transferSourceAgent?.name
                  ? `${transferSourceAgent.name} (${transferSourceAgent.code})`
                  : transferSourceAgent?.code || '未知'
              }}
            </Tag>
            <span class="ml-2 text-muted">
              将转移选中的 {{ selectedRowKeys.length }} 篇文章
            </span>
          </div>
        </FormItem>

        <!-- 目标 Agent 选择 -->
        <FormItem label="目标 Agent" required>
          <Select
            v-model:value="transferForm.target_agent_code"
            placeholder="请选择目标 Agent"
            style="width: 100%"
            :loading="transferLoading"
            :disabled="transferLoading"
            show-search
            :filter-option="
              (input: string, option: any) =>
                option?.label?.toLowerCase().includes(input.toLowerCase()) ||
                option?.value?.toLowerCase().includes(input.toLowerCase())
            "
          >
            <SelectOption
              v-for="opt in transferAgentOptions"
              :key="opt.value"
              :value="opt.value"
              :label="opt.label"
            >
              {{ opt.label }}
            </SelectOption>
          </Select>
        </FormItem>

        <!-- 转移选项 -->
        <FormItem label="转移选项">
          <Space direction="vertical" class="w-full">
            <div class="transfer-option-item">
              <span class="option-label">跳过已锁定文章</span>
              <span class="option-desc">已锁定的文章不会被转移</span>
            </div>
            <div class="transfer-option-item">
              <span class="option-label">跳过已使用文章</span>
              <span class="option-desc">已使用的文章不会被转移</span>
            </div>
          </Space>
        </FormItem>

        <!-- 提示信息 -->
        <div class="transfer-tips">
          <p class="text-muted">
            <strong>提示：</strong>转移操作会修改文章的 agent_code 字段，源
            Agent 将失去这些文章的控制权。转移后的文章会在备注中记录转移历史。
          </p>
        </div>
      </Form>
    </Modal>
  </Page>
</template>

<style scoped>
.mb-4 {
  margin-bottom: 16px;
}

.mt-4 {
  margin-top: 16px;
}

.my-2 {
  margin-top: 8px;
  margin-bottom: 8px;
}

/* 专家视角提示条样式 */
.expert-view-alert {
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 8%),
    hsl(var(--primary) / 12%)
  );
  border: 2px solid hsl(var(--primary) / 30%);
  border-radius: 8px;
  box-shadow: 0 2px 8px hsl(var(--primary) / 15%);
}

.expert-view-alert :deep(.ant-alert-message) {
  font-size: 15px;
  font-weight: 600;
  color: hsl(var(--primary));
}

.expert-view-alert :deep(.ant-alert-description) {
  margin-top: 4px;
}

.expert-view-alert :deep(.ant-alert-icon) {
  font-size: 18px;
  color: hsl(var(--primary));
}

.expert-view-alert :deep(.ant-alert-close-icon) {
  color: hsl(var(--muted-foreground));
}

.expert-view-alert :deep(.ant-alert-close-icon:hover) {
  color: hsl(var(--foreground));
}

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

/* 文章标题悬停预览 */
.article-title-link {
  color: hsl(var(--primary));
  cursor: pointer;
  transition: color 0.2s;
}

.article-title-link:hover {
  color: hsl(var(--primary) / 80%);
  text-decoration: underline;
}

.article-preview {
  width: 360px;
  max-height: 400px;
  overflow-y: auto;
}

.article-preview-title {
  margin-bottom: 8px;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.4;
  color: hsl(var(--foreground));
}

.article-preview-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.article-preview-content {
  font-size: 13px;
  line-height: 1.6;
  color: hsl(var(--muted-foreground));
  word-break: break-all;
  white-space: pre-wrap;
}

/* 文章预览弹窗：提高 z-index 避免被表格行遮挡 */
:deep(.article-preview-popover) {
  z-index: 1050 !important;
}

/* 确保弹窗所有子元素也有正确的层级 */
:deep(.article-preview-popover .ant-popover-inner) {
  z-index: 1050 !important;
}

/* 确保表格行不会创建新的层叠上下文 */
.article-table :deep(.ant-table-tbody > tr) {
  position: static !important;
}

/* CRITIC 违禁词相关样式 */
.critic-reason {
  color: hsl(var(--destructive));
  word-break: break-all;
}

.forbidden-words {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.forbidden-word-tag {
  margin: 0;
}

.no-problems {
  color: hsl(var(--muted-foreground));
}

/* 违禁词高亮内容 */
.content-with-highlight {
  max-height: 400px;
  padding: 16px;
  overflow-y: auto;
  line-height: 1.8;
  word-break: break-all;
  white-space: pre-wrap;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.content-with-highlight :deep(.highlight-forbidden) {
  padding: 2px 4px;
  font-weight: 600;
  color: hsl(var(--destructive));
  background: hsl(var(--destructive) / 15%);
  border: 1px solid hsl(var(--destructive) / 30%);
  border-radius: 4px;
}

/* 文章内容容器（用于定位字数统计） */
.content-wrapper {
  position: relative;
}

/* 字数统计标签 */
.char-count {
  position: absolute;
  right: 12px;
  bottom: 8px;
  padding: 4px 8px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  pointer-events: none;
  background: hsl(var(--background) / 90%);
  border: 1px solid hsl(var(--border));
  border-radius: 4px;
}

/* Expert 执行记录列表 */
.expert-results-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 400px;
  overflow-y: auto;
}

.expert-result-card {
  background: hsl(var(--muted));
  border: 1px solid hsl(var(--border));
}

.expert-name {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.result-time {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.result-json {
  max-height: 200px;
  padding: 12px;
  overflow-y: auto;
  font-size: 12px;
  background: hsl(var(--background));
  border-radius: 6px;
}

.result-json pre {
  margin: 0;
  word-break: break-all;
  white-space: pre-wrap;
}

/* Expert 结果结构化展示 */
.expert-result-summary {
  padding: 8px 0;
}

.expert-result-reason {
  padding: 8px 0;
  font-size: 13px;
  line-height: 1.6;
}

.expert-result-snippets {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  padding: 8px 0;
}

.expert-result-highlights {
  padding: 8px 0;
  font-size: 13px;
}

.highlights-text {
  padding: 4px 8px;
  font-style: italic;
  color: hsl(var(--success));
  background: hsl(var(--success) / 10%);
  border-radius: 4px;
}

.error-message {
  padding: 8px;
  margin-top: 8px;
  font-size: 13px;
  color: hsl(var(--destructive));
  background: hsl(var(--destructive) / 10%);
  border-radius: 4px;
}

.text-gray-400 {
  color: hsl(var(--muted-foreground));
}

/* 评分相关样式 */
.text-muted {
  color: hsl(var(--muted-foreground));
}

.text-success {
  color: hsl(var(--success));
}

.score-tag {
  cursor: pointer;
}

.score-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.score-tag-with-label {
  display: inline-flex;
  gap: 2px;
  align-items: center;
  cursor: pointer;
}

.score-label {
  font-size: 11px;
  opacity: 0.85;
}

.score-value {
  font-weight: 600;
}

.score-popover {
  max-width: 300px;
}

.score-popover .font-medium {
  font-weight: 500;
  color: hsl(var(--foreground));
}

/* 六维度评分雷达图 */
.radar-chart-container {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  padding: 8px 0;
}

.radar-chart {
  width: 280px;
  height: 220px;
}

/* 表格行间距增大 */
.article-table :deep(.ant-table-tbody > tr > td) {
  position: static !important;
  padding: 16px 12px;
}

.article-table :deep(.ant-table-thead > tr > th) {
  padding: 14px 12px;
}

/* 导入弹窗样式 */
.import-form {
  padding-top: 16px;
}

.import-tips {
  padding: 12px;
  margin-top: 12px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted));
  border-radius: 6px;
}

.import-tips p {
  margin: 0 0 8px;
  font-weight: 500;
}

.import-tips ul {
  padding-left: 20px;
  margin: 0;
}

.import-tips li {
  margin-bottom: 4px;
}

.import-tips code {
  padding: 2px 6px;
  font-family: monospace;
  background: hsl(var(--background));
  border-radius: 4px;
}

/* 批量操作栏样式 */
.batch-action-bar {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  margin-bottom: 16px;
  background: hsl(var(--primary) / 8%);
  border: 1px solid hsl(var(--primary) / 20%);
  border-radius: 8px;
}

.batch-action-bar .text-muted {
  color: hsl(var(--muted-foreground));
}

.batch-action-bar strong {
  color: hsl(var(--primary));
}

/* 批量评分弹窗样式 */
.selected-articles-info {
  display: flex;
  align-items: center;
}

.ml-2 {
  margin-left: 8px;
}

.batch-score-tips {
  padding: 12px;
  margin-top: 16px;
  background: hsl(var(--muted));
  border-radius: 6px;
}

/* 批量评分进度样式 */
.batch-score-progress {
  padding: 12px;
  margin-top: 12px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.batch-score-progress .progress-header {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 8px;
}

.batch-score-progress .progress-text {
  font-size: 14px;
  color: hsl(var(--foreground));
}

.batch-score-progress .progress-stats {
  display: flex;
  gap: 16px;
}

.batch-score-progress .stat-item {
  font-size: 13px;
}

.batch-score-progress .stat-item.success {
  color: hsl(var(--success));
}

.batch-score-progress .stat-item.failed {
  color: hsl(var(--destructive));
}

.batch-score-tips p {
  margin: 0;
  font-size: 13px;
}

.expert-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* 多专家任务进度 */
.expert-tasks-progress {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 200px;
  padding: 12px;
  overflow-y: auto;
  background: hsl(var(--muted));
  border-radius: 8px;
}

.expert-task-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: hsl(var(--card));
  border-radius: 6px;
}

.expert-task-item .task-header {
  display: flex;
  gap: 8px;
  align-items: center;
}

.expert-task-item .task-name {
  font-size: 13px;
  color: hsl(var(--foreground));
}

.expert-task-item .task-stats {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.expert-task-item .stat-success {
  color: hsl(var(--success));
}

.expert-task-item .stat-failed {
  color: hsl(var(--destructive));
}

.progress-summary {
  padding-top: 8px;
  font-size: 13px;
  border-top: 1px solid hsl(var(--border));
}

/* 文章转移弹窗样式 */
.transfer-source-info {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  background: hsl(var(--muted));
  border-radius: 6px;
}

.transfer-option-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 0;
}

.transfer-option-item .option-label {
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.transfer-option-item .option-desc {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.transfer-tips {
  padding: 12px;
  margin-top: 12px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--accent) / 10%);
  border: 1px solid hsl(var(--accent) / 20%);
  border-radius: 6px;
}

.transfer-tips p {
  margin: 0;
  line-height: 1.6;
}

.transfer-tips strong {
  color: hsl(var(--foreground));
}

/* Agent 胶囊样式 */
.agent-capsule {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  background: hsl(142deg 76% 35% / 8%);
  border: 1px solid hsl(142deg 76% 35% / 15%);
  border-radius: 16px;
  box-shadow: 0 1px 2px hsl(142deg 76% 90% / 30%);
}

.agent-label {
  max-width: 130px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  font-weight: 500;
  color: hsl(142deg 76% 45%);
  white-space: nowrap;
}
</style>
