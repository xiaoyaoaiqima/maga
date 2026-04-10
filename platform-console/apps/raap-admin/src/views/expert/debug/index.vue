<script setup lang="ts">
import type { SelectValue } from 'ant-design-vue/es/select';

import type {
  DebugResponse,
  ExpertConfig,
  ExpertPluginVariablesResponse,
  ModelRoute,
  PersistedDebugStateV1,
} from './types';

import type { ExpertDebugApi } from '#/api/core/expert-debug';
import type { GraphCorpusApi } from '#/api/core/graph-corpus';

/**
 * Expert 调试器
 * 功能：调试 Expert 配置，支持变量选择、Prompt 预览、执行对比、历史记录
 * @fixed Merge conflict cleanup - 2024-12-22
 */
import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue';
import { useRoute } from 'vue-router';

import { usePreferences } from '@vben/preferences';
import { formatDateTime } from '@vben/utils';

import { DownOutlined, UpOutlined } from '@ant-design/icons-vue';
import { DiffEditor } from '@guolao/vue-monaco-editor';
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Divider,
  Dropdown,
  Form,
  InputNumber,
  Menu,
  MenuDivider,
  MenuItem,
  message,
  Modal,
  Popover,
  Progress,
  Row,
  Select,
  Slider,
  Space,
  Spin,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import {
  batchDebugExpertApi,
  debugExpertApi,
  getBatchDebugTaskStatusApi,
  getDebugHistoryDetailApi,
  getPluginVariablesApi,
  listBatchDebugTasksApi,
} from '#/api/core/expert-debug';
import {
  batchGetKeywordsApi,
  listCorpusTemplatesApi,
} from '#/api/core/graph-corpus';
import { getRouteListApi } from '#/api/core/llm';
import { requestClient } from '#/api/request';
import ModelSelect from '#/components/ModelSelect.vue';
import MonacoEditor from '#/components/MonacoEditor.vue';
import { use_page_persistence } from '#/utils/page_persistence';

import {
  BatchEvalModal,
  BatchStrategyTestModal,
  ComparisonResultsGrid,
  HistoryDrawer,
  StrategyImportDrawer,
} from './components';
import ABTestModal from './components/ABTestModal.vue';
import {
  useBatchEval,
  useCompareGroups,
  useDebugHistory,
  usePromptEditor,
} from './composables';
import { getPluginColor } from './constants';
import {
  calculateCost,
  copyToClipboard,
  formatExecutionTime,
  getDisplayContent,
  getEffectiveTokenUsage,
  highlightProblems,
} from './utils';

const { Item: FormItem } = Form as any;

const { Panel: CollapsePanel } = Collapse as any;
const { Option: SelectOption } = Select as any;
const { TabPane } = Tabs as any;

// ==================== 路由 & 主题 ====================

const route = useRoute();
const { isDark } = usePreferences();
const editorTheme = computed(() => (isDark.value ? 'vs-dark' : 'vs'));

// ==================== Composables ====================

const {
  isCompareMode,
  compareGroups,
  activeGroupIndex,
  comparisonResults,
  selectedVariables,
  enableModelOverride,
  overrideModelCode,
  overrideTemperature,
  overrideMaxTokens,
  addCompareGroup,
  removeCompareGroup,
  getVariableValue,
  setVariableValue,
} = useCompareGroups();

const {
  historyVisible,
  historyLoading,
  historyList,
  historyPagination,
  selectedHistoryIds,
  fetchHistory,
  handleHistoryTableChange,
  showHistory,
  handleStarHistory,
  handleDeleteHistory,
  toggleHistorySelect,
  loadHistoryDetail,
} = useDebugHistory();

const {
  batchModalOpen,
  batchSubmitting,
  testSetOptions,
  batchForm,
  openBatchModal,
  submitBatchScore,
} = useBatchEval();

const {
  promptTemplate,
  renderedPrompt,
  promptOverride,
  usePromptOverride,
  pluginSegments,
  previewLoading,
  editedSegments,
  editingSegmentIndex,
  finalPrompt,
  hasEditedSegments,
  getSegmentContent,
  forcePreviewPrompt,
  startEditSegment,
  saveEditSegment,
  cancelEditSegment,
  resetAllEdits,
} = usePromptEditor();

/**
 * Popover 浮层容器：渲染到 Modal 内部而非 body
 * 避免位置计算相对于整个页面导致弹出在 Modal 可视区域外
 */
const getPopupContainer = (triggerNode?: HTMLElement) => {
  // 优先找到最近的 Modal body 容器
  const modalBody = triggerNode?.closest('.ant-modal-body');
  if (modalBody) return modalBody as HTMLElement;
  // 其次找到 Modal 内容区域
  const modalContent = triggerNode?.closest('.ant-modal-content');
  if (modalContent) return modalContent as HTMLElement;
  // 兜底到 body
  return document.body;
};

// ==================== 基础状态 ====================

const loading = ref(false);
const executing = ref(false);

// Expert 配置
const expertConfigs = ref<ExpertConfig[]>([]);
const selectedExpert = ref<string>('');

// 模型路由（用于费用计算）
const modelRoutes = ref<ModelRoute[]>([]);

// 变量选择面板
const pluginVariables = ref<ExpertPluginVariablesResponse | null>(null);
const activeCollapseKeys = ref<string[]>([]);

// 输入内容
const inputContent = ref('');

// 执行结果
const debugResult = ref<DebugResponse | null>(null);

// Diff 对比
const diffVisible = ref(false);
const diffOriginal = ref('');
const diffModified = ref('');
const diffTitle = ref('');

const importedStrategyByPlugin = reactive(
  new Map<string, { strategy_id: string; strategy_name: string }>(),
);

// ==================== 页面持久化 ====================

// ==================== 批量随机生成 ====================

const batchRandomModalOpen = ref(false);
const batchRandomExecuting = ref(false);
const batchRandomForm = ref({
  count: 5,
  include_current: false,
});
const batchRandomResults = ref<ExpertDebugApi.BatchDebugResultItem[]>([]);
const batchRandomSummary = ref<null | {
  failed_count: number;
  success_count: number;
  total: number;
  total_time_ms: number;
}>(null);
const batchRandomTaskId = ref<string>('');
const batchRandomStatus = ref<string>('');
let batchRandomPollingTimer: null | ReturnType<typeof setInterval> = null;

// ==================== 批量固定生成（固定参数生成多篇） ====================
const batchFixedModalOpen = ref(false);
const batchFixedExecuting = ref(false);
const batchFixedForm = ref({
  count: 5, // 生成篇数
});
const batchFixedResults = ref<ExpertDebugApi.BatchDebugResultItem[]>([]);
const batchFixedSummary = ref<null | {
  failed_count: number;
  success_count: number;
  total: number;
  total_time_ms: number;
}>(null);
const batchFixedTaskId = ref<string>('');
const batchFixedStatus = ref<string>('');
let batchFixedPollingTimer: null | ReturnType<typeof setInterval> = null;

// 批量历史记录
const batchHistoryModalOpen = ref(false);
const batchHistoryLoading = ref(false);
const batchHistoryList = ref<ExpertDebugApi.BatchDebugTaskListItem[]>([]);
const batchHistoryTotal = ref(0);
const batchHistoryPage = ref(1);
const batchHistoryPageSize = ref(20);

// 策略导入抽屉
const strategyImportDrawerOpen = ref(false);
const strategyImportTargetPluginCode = ref<string | undefined>(undefined);
const strategyImportTargetPluginName = ref<string | undefined>(undefined);

// 批量策略测试弹窗
const batchStrategyTestModalOpen = ref(false);

// AB测试弹窗
const abTestModalOpen = ref(false);

async function openBatchHistoryModal() {
  batchHistoryModalOpen.value = true;
  await fetchBatchHistory();
}

async function fetchBatchHistory() {
  batchHistoryLoading.value = true;
  try {
    const resp = await listBatchDebugTasksApi({
      expert_config_code: selectedExpert.value,
      page: batchHistoryPage.value,
      page_size: batchHistoryPageSize.value,
    });
    batchHistoryList.value = resp.items;
    batchHistoryTotal.value = resp.total;
  } catch (error: unknown) {
    message.error((error as Error)?.message || '获取批量历史失败');
  } finally {
    batchHistoryLoading.value = false;
  }
}

async function viewBatchTaskDetail(taskId: string) {
  try {
    const taskStatus = await getBatchDebugTaskStatusApi(taskId);

    // 关闭历史modal，打开批量测试modal显示结果
    batchHistoryModalOpen.value = false;
    batchRandomModalOpen.value = true;
    batchRandomResults.value = taskStatus.results;
    batchRandomSummary.value = {
      total: taskStatus.total,
      success_count: taskStatus.success_count,
      failed_count: taskStatus.failed_count,
      total_time_ms: 0,
    };
    batchRandomStatus.value = taskStatus.status;
    batchRandomTaskId.value = taskStatus.task_id;
  } catch (error: unknown) {
    message.error((error as Error)?.message || '查看任务详情失败');
  }
}

function openBatchRandomModal() {
  if (!selectedExpert.value) {
    message.warning('请先选择要调试的 Expert');
    return;
  }
  batchRandomResults.value = [];
  batchRandomSummary.value = null;
  batchRandomModalOpen.value = true;
}

// ==================== AB测试 ====================
function openABTestModal() {
  abTestModalOpen.value = true;
}

function handleABTestSuccess() {
  message.success('AB测试创建成功，可在"AB test记录"中查看');
  abTestModalOpen.value = false;
}

async function submitBatchRandomTest() {
  if (!selectedExpert.value) return;

  // 清除之前的轮询定时器
  if (batchRandomPollingTimer) {
    clearInterval(batchRandomPollingTimer);
    batchRandomPollingTimer = null;
  }

  batchRandomExecuting.value = true;
  batchRandomResults.value = [];
  batchRandomSummary.value = null;
  batchRandomStatus.value = 'pending';

  try {
    // 创建批量调试任务
    const resp = await batchDebugExpertApi({
      expert_config_code: selectedExpert.value,
      content: inputContent.value || '',
      count: batchRandomForm.value.count,
      include_current: batchRandomForm.value.include_current,
      current_plugin_config_snapshot: batchRandomForm.value.include_current
        ? selectedVariables.value
        : undefined,
      model_code: enableModelOverride.value
        ? overrideModelCode.value
        : undefined,
      model_config_override: enableModelOverride.value
        ? {
            temperature: overrideTemperature.value,
            max_tokens: overrideMaxTokens.value,
          }
        : undefined,
    });

    batchRandomTaskId.value = resp.task_id;
    batchRandomStatus.value = resp.status;

    message.success(`批量随机生成任务已创建，开始并行执行...`);

    // 启动轮询查询任务状态
    batchRandomPollingTimer = setInterval(async () => {
      try {
        const taskStatus = await getBatchDebugTaskStatusApi(
          batchRandomTaskId.value,
        );

        batchRandomStatus.value = taskStatus.status;
        batchRandomResults.value = taskStatus.results;
        batchRandomSummary.value = {
          total: taskStatus.total,
          success_count: taskStatus.success_count,
          failed_count: taskStatus.failed_count,
          total_time_ms: 0,
        };

        // 任务完成，停止轮询
        if (
          taskStatus.status === 'completed' ||
          taskStatus.status === 'failed'
        ) {
          if (batchRandomPollingTimer) {
            clearInterval(batchRandomPollingTimer);
            batchRandomPollingTimer = null;
          }
          batchRandomExecuting.value = false;

          if (taskStatus.status === 'completed') {
            message.success(
              `批量随机生成完成: 成功 ${taskStatus.success_count} 篇, 失败 ${taskStatus.failed_count} 篇`,
            );
          } else {
            message.error(
              `批量随机生成失败: ${taskStatus.error_message || '未知错误'}`,
            );
          }

          // 刷新历史记录
          await fetchHistory();
        }
      } catch (error) {
        console.error('[Polling] Error:', error);
        // 轮询出错不中断，继续尝试
      }
    }, 2000); // 每 2 秒轮询一次
  } catch (error: unknown) {
    message.error((error as Error)?.message || '批量随机生成失败');
    batchRandomExecuting.value = false;
  }
}

/**
 * 应用某条结果的变量到当前调试面板
 */
function applyBatchResultVariables(
  snapshot: ExpertDebugApi.PluginConfigSnapshotItem[] | undefined,
) {
  if (!snapshot || snapshot.length === 0) {
    message.warning('该结果没有变量快照');
    return;
  }

  // 更新 selectedVariables
  selectedVariables.value = snapshot.map((item) => ({
    plugin_code: item.plugin_code,
    variable_mapping: { ...item.variable_mapping },
  }));

  message.success('已应用变量到当前调试面板');

  // 关闭弹窗
  batchRandomModalOpen.value = false;
  // 注意:不需要手动调用 handlePreviewPrompt(),因为 watch(selectedVariables) 会自动触发
  // handlePreviewPrompt();
}

// ==================== 批量固定生成函数 ====================
function openBatchFixedModal() {
  if (!selectedExpert.value) {
    message.warning('请先选择要调试的 Expert');
    return;
  }
  if (selectedVariables.value.length === 0) {
    message.warning('请先选择变量配置');
    return;
  }
  batchFixedResults.value = [];
  batchFixedSummary.value = null;
  batchFixedModalOpen.value = true;
}

async function submitBatchFixedGenerate() {
  if (!selectedExpert.value) return;

  // 清除之前的轮询定时器
  if (batchFixedPollingTimer) {
    clearInterval(batchFixedPollingTimer);
    batchFixedPollingTimer = null;
  }

  batchFixedExecuting.value = true;
  batchFixedResults.value = [];
  batchFixedSummary.value = null;
  batchFixedStatus.value = 'pending';

  try {
    // 构建 prompt_override：优先使用手动编辑的提示词，其次使用分段编辑后的最终提示词
    let effectivePromptOverride: string | undefined;
    if (usePromptOverride.value && promptOverride.value) {
      effectivePromptOverride = promptOverride.value;
    } else if (hasEditedSegments.value) {
      effectivePromptOverride = finalPrompt.value;
    }

    // 创建批量固定生成任务（使用当前变量配置 + 编辑后的提示词）
    const resp =
      await requestClient.post<ExpertDebugApi.BatchDebugTaskResponse>(
        '/v1/expert-configs/debug-batch-fixed',
        {
          expert_config_code: selectedExpert.value,
          content: inputContent.value || '',
          count: batchFixedForm.value.count,
          plugin_config_snapshot: selectedVariables.value,
          prompt_override: effectivePromptOverride,
          model_code: enableModelOverride.value
            ? overrideModelCode.value
            : undefined,
          model_config_override: enableModelOverride.value
            ? {
                temperature: overrideTemperature.value,
                max_tokens: overrideMaxTokens.value,
              }
            : undefined,
        },
      );

    batchFixedTaskId.value = resp.task_id;
    batchFixedStatus.value = resp.status;

    message.success(`批量固定生成任务已创建，开始并行执行...`);

    // 启动轮询查询任务状态（使用批量固定生成专用的 API）
    batchFixedPollingTimer = setInterval(async () => {
      try {
        const taskStatus = await requestClient.get<{
          completed: number;
          error_message?: string;
          failed_count: number;
          results: ExpertDebugApi.BatchDebugResultItem[];
          status: string;
          success_count: number;
          task_id: string;
          total: number;
        }>(`/v1/expert-configs/debug-batch-fixed/${batchFixedTaskId.value}`);

        batchFixedStatus.value = taskStatus.status;
        batchFixedResults.value = taskStatus.results;
        batchFixedSummary.value = {
          total: taskStatus.total,
          success_count: taskStatus.success_count,
          failed_count: taskStatus.failed_count,
          total_time_ms: 0,
        };

        // 任务完成，停止轮询
        if (
          taskStatus.status === 'completed' ||
          taskStatus.status === 'failed'
        ) {
          if (batchFixedPollingTimer) {
            clearInterval(batchFixedPollingTimer);
            batchFixedPollingTimer = null;
          }
          batchFixedExecuting.value = false;

          if (taskStatus.status === 'completed') {
            message.success(
              `批量固定生成完成: 成功 ${taskStatus.success_count} 篇, 失败 ${taskStatus.failed_count} 篇`,
            );
          } else {
            message.error(
              `批量固定生成失败: ${taskStatus.error_message || '未知错误'}`,
            );
          }

          // 刷新历史记录
          await fetchHistory();
        }
      } catch (error) {
        console.error('[Polling] Error:', error);
      }
    }, 2000);
  } catch (error: unknown) {
    message.error((error as Error)?.message || '批量固定生成失败');
    batchFixedExecuting.value = false;
  }
}

// 计算批量固定生成的总耗时（累加所有任务耗时）
const batchFixedTotalTime = computed(() => {
  if (batchFixedResults.value.length === 0) return 0;
  return batchFixedResults.value.reduce(
    (sum, item) => sum + (item.execution_time_ms || 0),
    0,
  );
});

const batchFixedResultColumns = [
  {
    title: '#',
    dataIndex: 'index',
    key: 'index',
    width: 50,
    align: 'center' as const,
  },
  {
    title: '状态',
    dataIndex: 'success',
    key: 'success',
    width: 90,
    align: 'center' as const,
  },
  {
    title: '标题',
    dataIndex: 'title',
    key: 'title',
    width: 200,
    ellipsis: true,
  },
  {
    title: '耗时',
    dataIndex: 'execution_time_ms',
    key: 'execution_time_ms',
    width: 80,
    align: 'center' as const,
  },
  {
    title: '输出预览',
    dataIndex: 'output_preview',
    key: 'output_preview',
    ellipsis: true,
  },
  {
    title: '操作',
    key: 'action',
    width: 80,
    align: 'center' as const,
  },
];

const batchRandomResultColumns = [
  {
    title: '序号',
    dataIndex: 'index',
    key: 'index',
    width: 60,
  },
  {
    title: '标题',
    dataIndex: 'title',
    key: 'title',
    width: 160,
    ellipsis: true,
  },
  {
    title: '变量组合',
    dataIndex: 'variable_summary',
    key: 'variable_summary',
    width: 200,
    ellipsis: true,
  },
  {
    title: '状态',
    dataIndex: 'success',
    key: 'success',
    width: 80,
  },
  {
    title: '耗时',
    dataIndex: 'execution_time_ms',
    key: 'execution_time_ms',
    width: 80,
  },
  {
    title: '输出预览',
    dataIndex: 'output_preview',
    key: 'output_preview',
    ellipsis: true,
  },
  {
    title: '操作',
    key: 'action',
    width: 120,
  },
];

const page_persistence = use_page_persistence<PersistedDebugStateV1>({
  storage_key: 'raap_admin.expert_debug.persist.v1',
  version: 1,
  get_state: () => ({
    selected_expert: selectedExpert.value || '',
    input_content: inputContent.value || '',
    use_prompt_override: !!usePromptOverride.value,
    prompt_override: promptOverride.value || '',
    edited_segments: editedSegments.value || {},
    last_debug_history_id: debugResult.value?.id ?? null,
    is_compare_mode: isCompareMode.value,
    compare_groups: compareGroups.value,
    active_group_index: activeGroupIndex.value,
  }),
  apply_state: async (persisted) => {
    selectedExpert.value = persisted.selected_expert || '';
    inputContent.value = persisted.input_content || '';
    usePromptOverride.value = !!persisted.use_prompt_override;
    promptOverride.value = persisted.prompt_override || '';
    editedSegments.value = persisted.edited_segments || {};
    editingSegmentIndex.value = null;
    isCompareMode.value = !!persisted.is_compare_mode;
    if (persisted.compare_groups?.length) {
      compareGroups.value = persisted.compare_groups;
    }
    activeGroupIndex.value = persisted.active_group_index || 0;

    if (!selectedExpert.value) return;

    // 恢复 prompt_template
    const expert = expertConfigs.value.find(
      (e) => e.expert_config_code === selectedExpert.value,
    );
    if (expert) {
      promptTemplate.value = expert.prompt_template || '';
    }

    // 恢复变量面板（关键：获取最新的变量选项并同步结构）
    try {
      const response = await getPluginVariablesApi(selectedExpert.value);
      pluginVariables.value = response;

      // 打印 plugin 对象结构，查看是否有 strategy_id
      console.warn('=== Plugin Structure Debug ===');
      response.plugins?.forEach((plugin: any) => {
        console.warn('Plugin:', plugin.plugin_code, {
          strategy_id: plugin.strategy_id,
          strategy_info: plugin.strategy_info,
          plugin_name: plugin.plugin_name,
          variables_count: plugin.variables?.length,
          first_variable: plugin.variables?.[0],
        });
      });

      // 同步 selectedVariables 结构，保留用户之前选择的值
      // 这是修复刷新页面后看不到新选项的关键逻辑
      const oldVarsMap = new Map<string, Record<string, string>>();
      for (const item of selectedVariables.value) {
        oldVarsMap.set(item.plugin_code, item.variable_mapping);
      }

      const newVars: Array<{
        plugin_code: string;
        variable_mapping: Record<string, string>;
      }> = [];
      for (const plugin of response.plugins) {
        const oldMapping = oldVarsMap.get(plugin.plugin_code) || {};
        const variableMapping: Record<string, string> = {};
        for (const variable of plugin.variables || []) {
          // 优先使用用户之前选择的值，否则使用 API 返回的默认值
          const previousValue = oldMapping[variable.variable_name];
          if (previousValue !== undefined) {
            variableMapping[variable.variable_name] = previousValue;
          } else if (variable.source === 'strategy' && variable.selected) {
            // 策略绑定模式
            variableMapping[variable.variable_name] =
              variable.selected.startsWith('node:')
                ? variable.selected
                : `node:${variable.selected}`;
          } else if (variable.source === 'user_profile' && variable.selected) {
            // 用户画像模式：直接使用 external_user_id（即 context_name）
            variableMapping[variable.variable_name] = variable.selected;
          } else {
            // 旧模式
            variableMapping[variable.variable_name] = variable.selected || '';
          }
        }
        newVars.push({
          plugin_code: plugin.plugin_code,
          variable_mapping: variableMapping,
        });
      }
      selectedVariables.value = newVars;
    } catch (error) {
      console.error('恢复变量面板失败:', error);
    }

    // 重新渲染 Prompt（强制执行）
    const savedEditedSegments = { ...editedSegments.value };
    await forcePreviewPrompt(selectedExpert.value, selectedVariables.value);
    if (Object.keys(savedEditedSegments).length > 0) {
      editedSegments.value = savedEditedSegments;
    }

    // 恢复最近一次执行结果
    if (persisted.last_debug_history_id) {
      try {
        debugResult.value = await loadHistoryDetail(
          persisted.last_debug_history_id,
        );
      } catch {
        // 忽略
      }
    }
  },
});

// ==================== 计算属性 ====================

const selectedExpertDetail = computed(() => {
  return expertConfigs.value.find(
    (e) => e.expert_config_code === selectedExpert.value,
  );
});

const expertPluginConfigList = computed(() => {
  const pluginConfig = selectedExpertDetail.value?.plugin_config;
  return Array.isArray(pluginConfig) ? pluginConfig : [];
});

const expertOptions = computed(() => {
  return expertConfigs.value.map((item) => ({
    value: item.expert_config_code,
    label: `${item.expert_config_name} (${item.expert_config_code})`,
  }));
});

// CRITIC 问题列表
const criticProblemList = computed(() => {
  if (!debugResult.value?.expert_total_output) return [];
  const output = debugResult.value.expert_total_output;
  // 优先使用 problem_snippets (新字段)
  if (output.problem_snippets && Array.isArray(output.problem_snippets)) {
    return output.problem_snippets as string[];
  }
  // 兼容旧字段 problem_context_list
  if (
    output.problem_context_list &&
    Array.isArray(output.problem_context_list)
  ) {
    return output.problem_context_list as string[];
  }
  return [];
});

const showCriticProblems = computed(() => {
  if (!selectedExpertDetail.value) return false;
  const type = selectedExpertDetail.value.expert_type?.toUpperCase() || '';
  // 兼容多种非生成类 Expert 类型
  const isNotGeneration = type !== 'GENERATION';
  return isNotGeneration && criticProblemList.value.length > 0;
});

// 判断是否为 GENERATION 类型专家
const isGenerationType = computed(() => {
  if (!selectedExpertDetail.value) return false;
  const type = selectedExpertDetail.value.expert_type?.toUpperCase() || '';
  return type === 'GENERATION';
});

// 批量评分按钮可见性：仅当选择 BAN/CRITIC 类型时显示
const showBatchScore = computed(() => {
  return selectedExpertDetail.value && !isGenerationType.value;
});

// 批量生成相关按钮可见性：仅当选择 GENERATION 类型时显示
const showBatchGeneration = computed(() => {
  return selectedExpertDetail.value && isGenerationType.value;
});

// ==================== 初始化 ====================

async function fetchExpertConfigs() {
  loading.value = true;
  try {
    const data = await requestClient.get<ExpertConfig[]>('/v1/expert-configs');
    expertConfigs.value = data || [];

    // 如果已经选择了 expert，重新加载插件变量以获取最新配置
    if (selectedExpert.value) {
      try {
        await loadPluginVariables(selectedExpert.value);
      } catch (error) {
        console.warn('刷新插件变量失败:', error);
        // 不显示错误提示，因为这只是刷新操作
      }
    }
  } catch {
    message.error('获取 ExpertConfig 列表失败');
  } finally {
    loading.value = false;
  }
}

async function fetchModelRoutes() {
  try {
    const res = await getRouteListApi({ enabled: true, limit: 1000 });
    modelRoutes.value = res?.items || [];
  } catch (error: unknown) {
    console.error('获取模型路由失败:', error);
  }
}

// ==================== Expert 变更处理 ====================

let previewToken = 0;
async function handlePreviewPrompt() {
  if (!selectedExpert.value || page_persistence.is_restoring.value) return;

  const myToken = ++previewToken;
  try {
    await forcePreviewPrompt(selectedExpert.value, selectedVariables.value);
  } catch {
    if (myToken === previewToken) {
      console.error('预览 Prompt 失败');
    }
  }
}

// 加载插件变量的通用逻辑（提取为独立函数，供 handleExpertChange 和 refreshPluginVariables 复用）
async function loadPluginVariables(expertCode: string) {
  try {
    const response = await getPluginVariablesApi(expertCode);
    pluginVariables.value = response;

    const vars: Array<{
      plugin_code: string;
      variable_mapping: Record<string, string>;
    }> = [];
    for (const plugin of response.plugins) {
      const variableMapping: Record<string, string> = {};
      for (const variable of plugin.variables || []) {
        // 策略绑定模式：selected 是 node_id，需要加前缀
        if (variable.source === 'strategy' && variable.selected) {
          variableMapping[variable.variable_name] =
            variable.selected.startsWith('node:')
              ? variable.selected
              : `node:${variable.selected}`;
        }
        // 用户画像模式：直接使用 external_user_id（即 context_name）
        else if (variable.source === 'user_profile' && variable.selected) {
          variableMapping[variable.variable_name] = variable.selected;
        }
        // 旧模式：直接使用
        else {
          variableMapping[variable.variable_name] = variable.selected || '';
        }
      }
      vars.push({
        plugin_code: plugin.plugin_code,
        variable_mapping: variableMapping,
      });
    }
    selectedVariables.value = vars;

    // 注意:不需要手动调用 handlePreviewPrompt(),因为 watch(selectedVariables) 会自动触发
    // await handlePreviewPrompt();
  } catch (error) {
    message.error('获取变量选项失败');
    throw error;
  }
}

async function handleExpertChange(code: SelectValue) {
  if (!code || typeof code !== 'string') {
    pluginVariables.value = null;
    selectedVariables.value = [];
    promptTemplate.value = '';
    renderedPrompt.value = '';
    selectedExpert.value = '';
    return;
  }

  // 更新 selectedExpert（处理从 URL 参数或代码直接调用的情况）
  selectedExpert.value = code;

  const expert = expertConfigs.value.find((e) => e.expert_config_code === code);
  if (expert) {
    promptTemplate.value = expert.prompt_template || '';
    overrideModelCode.value = expert.model_code || '';

    if (expert.model_config) {
      overrideTemperature.value = expert.model_config.temperature ?? 0.7;
      overrideMaxTokens.value = expert.model_config.max_tokens ?? 2048;
    }
  }

  // 获取 Plugin 变量选项
  await loadPluginVariables(code);
}

// 刷新当前选择的 Expert 的插件变量
async function refreshPluginVariables() {
  if (!selectedExpert.value) {
    message.warning('请先选择要调试的 Expert');
    return;
  }

  try {
    await loadPluginVariables(selectedExpert.value);
    message.success('插件变量已刷新');
  } catch {
    // loadPluginVariables 已经显示了错误消息
  }
}

// ==================== 执行调试 ====================

async function handleExecute() {
  if (!selectedExpert.value) {
    message.warning('请选择 Expert');
    return;
  }

  executing.value = true;
  debugResult.value = null;
  comparisonResults.value = [];

  try {
    if (isCompareMode.value) {
      // 对比模式：并行执行所有组
      const tasks = compareGroups.value.map(async (group, index) => {
        const request: any = {
          expert_config_code: selectedExpert.value,
          content: inputContent.value || '',
          plugin_config_snapshot: group.variables,
        };

        if (group.modelOverride.enabled) {
          request.model_code = group.modelOverride.model_code;
          request.model_config_override = {
            temperature: group.modelOverride.temperature,
            max_tokens: group.modelOverride.max_tokens,
          };
        }

        try {
          const resp = await debugExpertApi(request);
          return { index, resp };
        } catch (error: unknown) {
          return {
            index,
            resp: {
              success: false,
              error_message: (error as Error).message || '执行失败',
              expert_config_code: selectedExpert.value,
              execution_time_ms: 0,
              input_content: inputContent.value,
            } as DebugResponse,
          };
        }
      });

      const results = await Promise.all(tasks);
      const sortedResults: Array<DebugResponse | null> =
        Array.from<DebugResponse | null>({
          length: compareGroups.value.length,
        }).fill(null);
      results.forEach((r) => {
        sortedResults[r.index] = r.resp;
      });
      comparisonResults.value = sortedResults;
      debugResult.value = comparisonResults.value[0] || null;

      const successCount = results.filter((r) => r.resp.success).length;
      message.success(
        `对比执行完成：${successCount}/${compareGroups.value.length} 成功`,
      );
    } else {
      // 普通模式
      const request: any = {
        expert_config_code: selectedExpert.value,
        content: inputContent.value || '',
        plugin_config_snapshot: selectedVariables.value,
      };

      if (enableModelOverride.value) {
        request.model_code = overrideModelCode.value;
        request.model_config_override = {
          temperature: overrideTemperature.value,
          max_tokens: overrideMaxTokens.value,
        };
      }

      if (usePromptOverride.value && promptOverride.value) {
        request.prompt_override = promptOverride.value;
      } else if (hasEditedSegments.value) {
        request.prompt_override = finalPrompt.value;
      }

      const response = await debugExpertApi(request);
      debugResult.value = response;

      if (response.success) {
        message.success(
          `执行成功，耗时 ${formatExecutionTime(response.execution_time_ms)}`,
        );
      } else {
        message.error(response.error_message || '执行失败');
      }
    }

    await fetchHistory(selectedExpert.value);
  } catch (error: unknown) {
    message.error((error as Error).message || '执行失败');
  } finally {
    executing.value = false;
  }
}

async function showHistoryDetail(historyId: number) {
  try {
    const detail = await getDebugHistoryDetailApi(historyId);
    // 加载到主界面并关闭历史抽屉
    loadFromHistory(detail);
    historyVisible.value = false;
    message.success('已加载历史记录到调试面板');
  } catch {
    message.error('获取历史记录失败');
  } finally {
    historyLoading.value = false;
  }
}

function loadFromHistory(item: ExpertDebugApi.DebugResponse) {
  selectedExpert.value = item.expert_config_code;
  inputContent.value = item.input_content;
  debugResult.value = item;

  if (item.plugin_config_snapshot) {
    selectedVariables.value = item.plugin_config_snapshot;
  }
  if (item.rendered_prompt) {
    renderedPrompt.value = item.rendered_prompt;
  }

  historyVisible.value = false;
  message.success('已加载历史配置');
}

// ==================== 策略导入 ====================

// 为特定插件打开策略导入抽屉
function openStrategyImportForPlugin(plugin: {
  plugin_code: string;
  plugin_name?: string;
  strategy_id?: string;
}) {
  strategyImportTargetPluginCode.value = plugin.plugin_code;
  strategyImportTargetPluginName.value =
    plugin.plugin_name || plugin.plugin_code;
  strategyImportDrawerOpen.value = true;
}

// 将 pluginVariables 转换为 StrategyImportDrawer 需要的格式
const expertVariablesForStrategy = computed(() => {
  if (!pluginVariables.value) return [];

  const result: Array<{
    options: Array<{ context_name: string; node_id?: string }>;
    plugin_code: string;
    variable_name: string;
  }> = [];

  for (const plugin of pluginVariables.value.plugins) {
    for (const variable of plugin.variables || []) {
      result.push({
        plugin_code: plugin.plugin_code,
        variable_name: variable.variable_name,
        options: variable.options || [],
      });
    }
  }

  return result;
});

function openBatchStrategyTestModal() {
  if (!selectedExpert.value) {
    message.warning('请先选择要调试的 Expert');
    return;
  }
  batchStrategyTestModalOpen.value = true;
}

async function handleStrategyApply(
  snapshot: Array<{
    plugin_code: string;
    variable_mapping: Record<string, string>;
  }>,
  _importedNodes?: Array<{ node_id: string; node_name: string }>,
  strategyInfo?: { strategy_id: string; strategy_name: string },
) {
  // 合并策略导入的 snapshot 到当前 selectedVariables
  // 保留未被覆盖的变量值
  // 使用深拷贝确保每个 plugin 对象都是独立的，避免浅拷贝导致的响应式问题
  const newVariables = selectedVariables.value.map((v) => ({
    plugin_code: v.plugin_code,
    variable_mapping: { ...v.variable_mapping },
  }));

  for (const item of snapshot) {
    const existing = newVariables.find(
      (v) => v.plugin_code === item.plugin_code,
    );
    if (existing) {
      // 合并 variable_mapping
      existing.variable_mapping = {
        ...existing.variable_mapping,
        ...item.variable_mapping,
      };
    } else {
      // 对于新添加的插件，也需要深拷贝
      newVariables.push({
        plugin_code: item.plugin_code,
        variable_mapping: { ...item.variable_mapping },
      });
    }
  }

  selectedVariables.value = newVariables;

  if (strategyInfo) {
    snapshot.forEach((item) => {
      importedStrategyByPlugin.set(item.plugin_code, strategyInfo);
    });
  }

  // 注意:不需要手动调用 handlePreviewPrompt(),因为 watch(selectedVariables) 会自动触发
  // handlePreviewPrompt();
}

// 策略节点选项类型（扩展原有类型，添加 isExternal 和 select_mode 字段）
interface StrategyNodeOption {
  node_id: string;
  node_name: string;
  corpus_count?: number;
  corpus_preview?: string;
  isExternal?: boolean;
  select_mode?: 'multiple' | 'single'; // 节点选择模式：single-分开使用 / multiple-合在一起使用
}

const keywordNodeNameMap = reactive(new Map<string, string>());

// 语料列表缓存：Map<nodeId, CorpusItem[]>
interface CorpusItem {
  text?: string;
  fields?: Record<string, string>;
  template_code?: string;
}
const keywordNodeCorpusMap = reactive(new Map<string, CorpusItem[]>());

// 语料模板列表（用于按模板字段顺序展示）
const corpusTemplates = ref<GraphCorpusApi.CorpusTemplate[]>([]);

// 节点语料展开状态：Map<pluginCode:variableName, boolean>
const corpusExpandedState = reactive(new Map<string, boolean>());

const extractNodeIdsFromString = (value: string): string[] => {
  // 匹配 node:id 格式，支持多选模式下的逗号分隔
  // 例如: node:123:1 → 123, node:456 → 456, node:123,456,789 → [123, 456, 789]
  const matches = [...value.matchAll(/node:([\d,]+)(?::\d+)?/g)];
  const nodeIds: string[] = [];

  matches.forEach((match) => {
    const idsPart = match[1];
    if (idsPart) {
      // 处理逗号分隔的多个 ID
      const ids = idsPart
        .split(',')
        .map((id) => id.trim())
        .filter(Boolean);
      nodeIds.push(...ids);
    }
  });

  return nodeIds;
};

const extractNodeIdsFromSnapshot = (
  snapshot: Array<{ variable_mapping?: Record<string, unknown> }>,
): string[] => {
  const nodeIds: string[] = [];
  snapshot.forEach((item) => {
    const mapping = item.variable_mapping || {};
    Object.values(mapping).forEach((value) => {
      if (value === null || value === undefined) return;
      if (Array.isArray(value)) {
        value.forEach((entry) => {
          if (entry === null || entry === undefined) return;
          nodeIds.push(...extractNodeIdsFromString(String(entry)));
        });
        return;
      }
      nodeIds.push(...extractNodeIdsFromString(String(value)));
    });
  });
  return nodeIds;
};

const ensureKeywordNodeNames = async (nodeIds: string[]) => {
  const uniqueIds = [...new Set(nodeIds)].filter(Boolean);
  const missingIds = uniqueIds.filter((id) => !keywordNodeNameMap.has(id));

  if (missingIds.length === 0) {
    return;
  }

  try {
    const result = await batchGetKeywordsApi({
      node_ids: missingIds,
      include_children: false,
    });

    Object.entries(result || {}).forEach(([id, item]) => {
      if (item?.name) {
        keywordNodeNameMap.set(id, item.name);
      }
    });
  } catch (error) {
    console.error('Failed to fetch keyword node names:', error);
  }
};

const resolveKeywordNodeName = (nodeId: string): string => {
  return keywordNodeNameMap.get(nodeId) || `节点${nodeId}`;
};

/**
 * 获取节点的语料列表
 */
const ensureNodeCorpus = async (nodeId: string): Promise<CorpusItem[]> => {
  if (keywordNodeCorpusMap.has(nodeId)) {
    return keywordNodeCorpusMap.get(nodeId) || [];
  }

  try {
    const result = await batchGetKeywordsApi({
      node_ids: [nodeId],
      include_children: false,
    });
    const corpusList = (result?.[nodeId]?.corpus as CorpusItem[]) || [];
    keywordNodeCorpusMap.set(nodeId, corpusList);
    return corpusList;
  } catch (error) {
    console.warn('获取节点语料失败:', error);
    return [];
  }
};

/**
 * 格式化语料项为文本（按模板字段顺序展示）
 */
const formatCorpusItem = (item: CorpusItem): string => {
  if (item.fields) {
    // 结构化语料：按模板字段顺序展示
    const templateCode = item.template_code;
    if (templateCode) {
      const template = corpusTemplates.value.find(
        (t) => t.code === templateCode,
      );
      if (template && template.fields) {
        return template.fields
          .map((field) => {
            const value = item.fields?.[field.key];
            return value ? `【${field.label}】${value}` : '';
          })
          .filter(Boolean)
          .join('\n');
      }
    }
    // 没有找到模板，按原始顺序展示
    const parts = Object.entries(item.fields)
      .map(([k, v]) => `${k}: ${v}`)
      .join(' | ');
    return parts;
  }
  if (item.text) {
    return item.text;
  }
  return '(空语料)';
};

/**
 * 获取语料预览文本（截断）
 */
const getCorpusPreview = (item: CorpusItem, maxLength = 100): string => {
  const text = formatCorpusItem(item);
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
};

/**
 * 解析当前值中的节点 ID 和语料索引
 * 支持格式：
 * - 单选：node:123 或 node:123:0
 * - 多选：node:123,456 或 node:123,456:0
 */
const parseNodeValue = (
  value: string | undefined,
): {
  corpusIndex?: number;
  isMultiSelect: boolean;
  nodeId: string;
  nodeIds: string[];
} => {
  if (!value || !value.startsWith('node:')) {
    return { nodeId: '', nodeIds: [], isMultiSelect: false };
  }

  const rest = value.slice(5);

  // 检查是否有多选分隔符（逗号）
  const commaIndex = rest.indexOf(',');
  // 检查是否有 corpus_index（最后一个冒号）
  const lastColon = rest.lastIndexOf(':');

  // 判断是否有 corpus_index：最后一个冒号在所有逗号之后
  const hasCorpusIndex = lastColon > commaIndex;

  if (commaIndex !== -1) {
    // 多选模式：逗号分隔的多个 node_id
    let nodeIdsStr = rest;
    let corpusIndex;

    if (hasCorpusIndex) {
      // 格式：node:123,456:0
      nodeIdsStr = rest.slice(0, lastColon);
      corpusIndex = Number.parseInt(rest.slice(lastColon + 1), 10);
    }

    const nodeIds = nodeIdsStr
      .split(',')
      .map((id) => id.trim())
      .filter(Boolean);

    return {
      nodeId: nodeIds[0] || '', // 主节点（第一个）
      nodeIds,
      isMultiSelect: nodeIds.length > 1,
      corpusIndex,
    };
  }

  // 单选模式
  const colonIndex = rest.indexOf(':');
  let nodeId = rest;
  let corpusIndex;

  if (colonIndex !== -1) {
    // 格式：node:123:0
    nodeId = rest.slice(0, colonIndex);
    corpusIndex = Number.parseInt(rest.slice(colonIndex + 1), 10);
  }

  return {
    nodeId,
    nodeIds: nodeId ? [nodeId] : [],
    isMultiSelect: false,
    corpusIndex,
  };
};

/**
 * 获取当前选中的语料索引
 */
const getSelectedCorpusIndex = (value: string | undefined): number => {
  const { corpusIndex } = parseNodeValue(value);
  return corpusIndex ?? -1; // -1 表示随机选择
};

/**
 * 切换语料列表展开状态
 */
const toggleCorpusExpand = (pluginCode: string, variableName: string) => {
  const key = `${pluginCode}:${variableName}`;
  const currentState = corpusExpandedState.get(key) || false;
  corpusExpandedState.set(key, !currentState);
};

/**
 * 检查语料列表是否展开
 */
const isCorpusExpanded = (
  pluginCode: string,
  variableName: string,
): boolean => {
  const key = `${pluginCode}:${variableName}`;
  return corpusExpandedState.get(key) || false;
};

/**
 * 获取合并后的语料列表（支持多选模式）
 * 返回格式：{ nodeId, nodeName, corpusItems: [], nodeIndex?: number }[]
 */
const getMergedCorpusList = (
  value: string | undefined,
): Array<{
  corpusItems: Array<any[]>; // Array of combined corpus items
  nodeId: string;
  nodeIndex?: number;
  nodeName: string;
}> => {
  const parsed = parseNodeValue(value);

  // 单选模式：直接返回单个节点的语料
  if (!parsed.isMultiSelect) {
    const corpusItems = keywordNodeCorpusMap.get(parsed.nodeId) || [];
    return [
      {
        nodeId: parsed.nodeId,
        nodeName: resolveKeywordNodeName(parsed.nodeId),
        corpusItems: corpusItems.map((item) => [item]), // Wrap each item in array for consistency
        nodeIndex: 1,
      },
    ];
  }

  // 多选模式：生成所有节点语料的组合
  const allCorpusArrays = parsed.nodeIds.map(
    (nodeId) => keywordNodeCorpusMap.get(nodeId) || [],
  );
  const corpusCombinations = getCorpusCombinations(allCorpusArrays);

  // 创建一个组合组，包含所有可能的语料组合
  const nodeName = parsed.nodeIds
    .map((id) => resolveKeywordNodeName(id))
    .join(', ');

  return [
    {
      nodeId: parsed.nodeIds.join(','),
      nodeName,
      corpusItems: corpusCombinations, // Each item is an array representing one combination
      nodeIndex: 1,
    },
  ];
};

// 获取所有语料的组合
const getCorpusCombinations = (corpusArrays: any[][]): any[][] => {
  if (corpusArrays.length === 0) return [];
  if (corpusArrays.length === 1) return corpusArrays[0].map((item) => [item]);

  // 使用递归方式生成笛卡尔积
  const result: any[][] = [];

  const combine = (index: number, currentCombo: any[]) => {
    if (index === corpusArrays.length) {
      result.push([...currentCombo]);
      return;
    }

    for (const item of corpusArrays[index]) {
      currentCombo.push(item);
      combine(index + 1, currentCombo);
      currentCombo.pop();
    }
  };

  combine(0, []);
  return result;
};

// 显示组合语料项的预览
const getCombinedCorpusPreview = (
  combinedItems: any[],
  maxLength: number = 80,
): string => {
  if (!Array.isArray(combinedItems)) {
    return getCorpusPreview(combinedItems as any, maxLength);
  }

  // 将多个语料项组合成一个预览字符串
  const combinedText = combinedItems
    .map((item) =>
      getCorpusPreview(
        item as any,
        Math.floor(maxLength / combinedItems.length),
      ),
    )
    .join(' | ');

  return combinedText.length <= maxLength
    ? combinedText
    : `${combinedText.slice(0, Math.max(0, maxLength - 3))}...`;
};

/**
 * 选择具体的语料项
 */
const selectCorpusItem = async (
  pluginCode: string,
  variableName: string,
  nodeId: string, // This could be comma-separated node IDs in multi-select mode
  corpusIndex: number,
) => {
  // 解析当前值以判断是单选还是多选
  const currentValue = getVariableValue(pluginCode, variableName);
  const parsed = parseNodeValue(currentValue);

  if (parsed.isMultiSelect) {
    // 多选模式：选择特定的语料组合
    if (corpusIndex >= 0) {
      // 设置具体的语料组合索引
      const newValue = `node:${parsed.nodeIds.join(',')}:${corpusIndex}`;
      setVariableValue(pluginCode, variableName, newValue);
    } else {
      // 清除 corpus_index（恢复到随机选择状态）
      const newValue = `node:${parsed.nodeIds.join(',')}`;
      setVariableValue(pluginCode, variableName, newValue);
    }
  } else if (corpusIndex >= 0) {
    // 单选模式：设置具体的语料索引
    const newValue = `node:${nodeId}:${corpusIndex}`;
    setVariableValue(pluginCode, variableName, newValue);
  } else {
    // 单选模式：随机语料（corpusIndex = -1）
    const newValue = `node:${nodeId}`;
    setVariableValue(pluginCode, variableName, newValue);
  }

  // 注意:不需要手动调用 handlePreviewPrompt(),因为 watch(selectedVariables) 会自动触发
  // await handlePreviewPrompt();
};

const getImportedStrategyLabel = (pluginCode: string): string | undefined => {
  return importedStrategyByPlugin.get(pluginCode)?.strategy_name;
};

const getPluginDefaultStrategyName = (plugin: {
  variables?: Array<{ strategy_info?: { strategy_name?: string } }>;
}): string | undefined => {
  const names = new Set<string>();
  for (const variable of plugin.variables || []) {
    const strategyName = variable.strategy_info?.strategy_name;
    if (strategyName) names.add(strategyName);
  }
  if (names.size === 0) return undefined;
  if (names.size === 1) return [...names][0];
  return [...names].join(' / ');
};

// 获取插件的策略名称（综合判断）
const getStrategyNameForPlugin = (plugin: {
  plugin_code: string;
  strategy_id?: string;
  strategy_info?: { strategy_name?: string }; // 支持plugin直接包含strategy_info
  variables?: Array<{ strategy_info?: { strategy_name?: string } }>;
}): string | undefined => {
  // 优先级：导入 > strategy_info > 直接strategy_id > variables中的策略 > 默认
  if (getImportedStrategyLabel(plugin.plugin_code))
    return getImportedStrategyLabel(plugin.plugin_code);
  if (plugin.strategy_info?.strategy_name)
    return `策略：${plugin.strategy_info.strategy_name}`;
  if (plugin.strategy_id) return plugin.strategy_id;
  if (plugin.variables?.[0]?.strategy_info?.strategy_name)
    return `策略：${plugin.variables[0].strategy_info.strategy_name}`;
  return getPluginDefaultStrategyName(plugin);
};

const getPluginStrategyTagLabel = (plugin: {
  plugin_code: string;
  strategy_id?: string;
  strategy_info?: { strategy_name?: string };
  variables?: Array<{ strategy_info?: { strategy_name?: string } }>;
}): string => {
  const imported = getImportedStrategyLabel(plugin.plugin_code);
  if (imported) return `导入：${imported}`;

  // 优先级：导入 > strategy_info > 直接strategy_id > variables中的策略 > 默认
  if (plugin.strategy_info?.strategy_name)
    return `策略：${plugin.strategy_info.strategy_name}`;

  // 优先使用直接的 strategy_id 字段
  if (plugin.strategy_id) return `策略：${plugin.strategy_id}`;

  // 从 variables 中提取 strategy_id（插件级别的字段可能在 variables 里）
  const strategyIdFromVariables =
    plugin.variables?.[0]?.strategy_info?.strategy_id;

  // 再检查 variables 中的策略名称
  const defaultStrategy = getPluginDefaultStrategyName(plugin);
  if (strategyIdFromVariables) return `策略：${strategyIdFromVariables}`;
  if (defaultStrategy) return defaultStrategy;

  return '暂无关键词策略映射';
};

const getPluginStrategyTagColor = (plugin: {
  plugin_code: string;
  strategy_id?: string;
  variables?: Array<{ strategy_info?: { strategy_name?: string } }>;
}): string => {
  const imported = getImportedStrategyLabel(plugin.plugin_code);
  if (imported) return 'purple';
  const defaultStrategy = getPluginDefaultStrategyName(plugin);
  if (defaultStrategy) return 'blue';
  return 'default';
};

/**
 * 获取策略节点的完整选项列表
 * 根据后端返回的 select_mode 决定选项结构：
 * - multiple: 一个组合选项（逗号分隔的多个节点）
 * - single: 多个独立选项（每个节点一个）
 */
function getStrategyNodeOptions(
  currentValue: string | undefined,
  strategyNodes:
    | Array<{
        corpus_count?: number;
        corpus_preview?: string;
        node_id: string;
        node_name: string;
        select_mode?: 'multiple' | 'single';
      }>
    | undefined,
): StrategyNodeOption[] {
  if (!strategyNodes || strategyNodes.length === 0) {
    return [];
  }

  // 构建 node_id -> node 的映射，方便查找
  const nodeMap = new Map(strategyNodes.map((n) => [n.node_id, n]));

  // 获取第一个节点的 select_mode（整个维度共用）
  const dimensionSelectMode = strategyNodes[0]?.select_mode;

  // multiple 模式：创建一个组合选项（所有节点用逗号连接）
  if (dimensionSelectMode === 'multiple') {
    const allNodeIds = strategyNodes.map((n) => n.node_id);
    // 使用 resolveKeywordNodeName 获取节点名称（如果 node_name 是 id 则使用解析后的名称）
    const allNames = strategyNodes.map((n) => {
      const name = n.node_name;
      const id = n.node_id;
      // 如果 node_name 和 node_id 相同，说明后端返回的是 id，使用 resolveKeywordNodeName
      return name === id ? resolveKeywordNodeName(id) : name;
    });
    const combinedName = allNames.join(', ');
    const totalCorpusCount = strategyNodes.reduce(
      (sum, n) => sum + (n.corpus_count || 0),
      0,
    );

    const combinedOption: StrategyNodeOption = {
      node_id: `node:${allNodeIds.join(',')}`,
      node_name: combinedName,
      corpus_count: totalCorpusCount,
      corpus_preview: '',
      isExternal: false,
      select_mode: 'multiple',
    };

    // 如果当前值是多选格式（如 node:id1,id2），需要解析并检查是否匹配
    if (currentValue && currentValue.startsWith('node:')) {
      const parsed = parseNodeValue(currentValue);
      if (parsed.isMultiSelect) {
        // 当前值是多选，根据 node_id 获取对应的 node_name
        const currentNodeIds = parsed.nodeIds;
        // 使用 resolveKeywordNodeName 获取节点名称（和 getMergedCorpusList 保持一致）
        const currentNames = currentNodeIds
          .map((id) => {
            // 优先从 strategyNodes 中获取，如果没有则使用 resolveKeywordNodeName
            const node = nodeMap.get(id);
            return node?.node_name && node.node_name !== id
              ? node.node_name
              : resolveKeywordNodeName(id);
          })
          .join(', ');
        const currentCorpusCount = currentNodeIds.reduce(
          (sum, id) => sum + (nodeMap.get(id)?.corpus_count || 0),
          0,
        );

        return [
          {
            node_id: currentValue,
            node_name: currentNames,
            corpus_count: currentCorpusCount,
            corpus_preview: '',
            isExternal: false,
            select_mode: 'multiple',
          },
        ];
      }
    }

    return [combinedOption];
  }

  // single 模式：为每个节点创建独立选项
  const nodes: StrategyNodeOption[] = strategyNodes.map((node) => ({
    node_id: `node:${node.node_id}`,
    node_name: node.node_name,
    corpus_count: node.corpus_count || 0,
    corpus_preview: node.corpus_preview || '',
    isExternal: false,
    select_mode: 'single',
  }));

  return nodes;
}

/**
 * 获取策略节点的显示标签
 * 支持显示 corpus_index 信息（随机语料/具体语料）
 */
function getStrategyNodeLabel(
  node: StrategyNodeOption & { corpusIndex?: number },
): string {
  const { corpusIndex, isExternal, node_id, node_name } = node;

  // 如果 node_id 已经包含 node: 前缀，先解析出纯 node_id 和 corpus_index
  let baseNodeId = node_id;
  let actualCorpusIndex = corpusIndex;

  if (node_id.startsWith('node:')) {
    const parsed = parseNodeValue(node_id);
    baseNodeId = parsed.nodeId || node_id;
    if (parsed.corpusIndex !== undefined) {
      actualCorpusIndex = parsed.corpusIndex;
    }
  }

  // 如果指定了 corpus_index
  if (actualCorpusIndex !== undefined) {
    const nodeName = isExternal
      ? resolveKeywordNodeName(baseNodeId)
      : node_name;

    if (actualCorpusIndex === -1) {
      return `🎲 ${nodeName} (随机语料)`;
    }
    // 尝试获取具体语料内容
    const corpusList = keywordNodeCorpusMap.get(baseNodeId);
    if (
      corpusList &&
      actualCorpusIndex >= 0 &&
      actualCorpusIndex < corpusList.length
    ) {
      const corpusItem = corpusList[actualCorpusIndex];
      if (corpusItem) {
        const corpusPreview = formatCorpusItem(corpusItem);
        const previewText =
          corpusPreview.length > 20
            ? `${corpusPreview.slice(0, 20)}...`
            : corpusPreview;
        return `${nodeName} #${actualCorpusIndex + 1}: ${previewText}`;
      }
    }
    return `${nodeName} #${actualCorpusIndex + 1}`;
  }

  // 默认情况：根据 select_mode 判断如何处理（简化版本）
  const result = node_name;

  return result;
}

/**
 * 随机化所有变量值
 * 遍历所有 Plugin 的所有变量，从 options 中随机选择一个值
 */
async function randomizeAllVariables() {
  if (!pluginVariables.value || pluginVariables.value.plugins.length === 0) {
    message.warning('没有可随机的变量');
    return;
  }

  // 遍历所有 plugin 和变量，随机选择
  for (const plugin of pluginVariables.value.plugins) {
    for (const variable of plugin.variables || []) {
      // 策略绑定模式：使用 strategy_nodes
      if (
        variable.source === 'strategy' &&
        variable.strategy_nodes &&
        variable.strategy_nodes.length > 0
      ) {
        const randomIndex = Math.floor(
          Math.random() * variable.strategy_nodes.length,
        );
        const randomNode = variable.strategy_nodes[randomIndex];
        if (randomNode) {
          setVariableValue(
            plugin.plugin_code,
            variable.variable_name,
            `node:${randomNode.node_id}`,
          );
        }
      }
      // 用户画像和旧模式：使用 options
      else if (variable.options && variable.options.length > 0) {
        const randomIndex = Math.floor(Math.random() * variable.options.length);
        const randomOption = variable.options[randomIndex];
        if (randomOption) {
          setVariableValue(
            // 用户画像模式直接使用 context_name（即 external_user_id）
            plugin.plugin_code,
            variable.variable_name,
            randomOption.context_name,
          );
        }
      }
    }
  }

  message.success('已随机选择所有变量');

  // 注意:不需要手动调用 handlePreviewPrompt(),因为 watch(selectedVariables) 会自动触发
  // await handlePreviewPrompt();
}

// ==================== Diff 对比 ====================

function showInputOutputDiff() {
  if (!debugResult.value) return;

  diffOriginal.value = debugResult.value.input_content;
  diffModified.value = debugResult.value.output_content || '';
  diffTitle.value = '输入 vs 输出对比';
  diffVisible.value = true;
}

function showHistoryDiff() {
  if (selectedHistoryIds.value.length !== 2) {
    message.warning('请选择两条历史记录进行对比');
    return;
  }

  const [id1, id2] = selectedHistoryIds.value;
  const item1 = historyList.value.find((h) => h.id === id1);
  const item2 = historyList.value.find((h) => h.id === id2);

  if (!item1 || !item2) return;

  diffOriginal.value = item1.output_content || '';
  diffModified.value = item2.output_content || '';
  diffTitle.value = `#${id1} vs #${id2} 输出对比`;
  diffVisible.value = true;
}

// ==================== 对比结果查看详情 ====================

function handleViewComparisonDetail(result: DebugResponse) {
  debugResult.value = result;
  isCompareMode.value = false;
}

// ==================== 清理逻辑 ====================

onBeforeUnmount(() => {
  // 清除轮询定时器
  if (batchRandomPollingTimer) {
    clearInterval(batchRandomPollingTimer);
    batchRandomPollingTimer = null;
  }
  if (batchFixedPollingTimer) {
    clearInterval(batchFixedPollingTimer);
    batchFixedPollingTimer = null;
  }
});

// ==================== 清理逻辑 ====================

onBeforeUnmount(() => {
  // 清除轮询定时器
  if (batchRandomPollingTimer) {
    clearInterval(batchRandomPollingTimer);
    batchRandomPollingTimer = null;
  }
});

// ==================== 监听变量变化 ====================
// ==================== 监听 ====================

watch(
  () => pluginVariables.value,
  (val) => {
    if (val?.plugins) {
      activeCollapseKeys.value = val.plugins.map((p) => p.plugin_code);
    }
  },
  { immediate: true },
);

watch(
  selectedVariables,
  () => {
    if (page_persistence.is_restoring.value) return;
    if (selectedExpert.value) {
      handlePreviewPrompt();
    }
  },
  { deep: true },
);

watch(
  selectedVariables,
  (snapshot) => {
    const nodeIds = extractNodeIdsFromSnapshot(snapshot || []);
    void ensureKeywordNodeNames(nodeIds);
  },
  { deep: true },
);

watch(selectedExpert, () => {
  importedStrategyByPlugin.clear();
});

// 切换到 GENERATION 类型时清空测试内容
watch(isGenerationType, (newVal) => {
  if (newVal && inputContent.value) {
    inputContent.value = '';
  }
});

// ==================== 生命周期 ====================

const handleKeyDown = (e: KeyboardEvent) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    handleExecute();
  }
};

onMounted(async () => {
  // 加载语料模板（用于按模板字段顺序展示语料）
  try {
    const res = await listCorpusTemplatesApi();
    corpusTemplates.value = res.items || [];
  } catch (error) {
    console.warn('加载语料模板失败:', error);
  }

  await Promise.all([fetchExpertConfigs(), fetchModelRoutes()]);
  page_persistence.start_auto_persist();
  await page_persistence.restore();
  window.addEventListener('keydown', handleKeyDown);

  // 处理 URL 参数预填（从 RLHF 审核页跳转过来）
  const query = route.query;
  let prefillData: null | Record<string, string> = null;

  if (query.prefill && typeof query.prefill === 'string') {
    try {
      prefillData = JSON.parse(query.prefill) as Record<string, string>;
    } catch {
      console.warn('Failed to parse prefill data:', query.prefill);
    }
  }

  // 支持两种参数名：expert 和 expert_config_code
  const expertCode = query.expert || query.expert_config_code;
  if (expertCode && typeof expertCode === 'string') {
    // 预填 Expert 并触发变量加载
    await handleExpertChange(expertCode);

    // 加载完变量后预填变量值
    if (prefillData && pluginVariables.value) {
      for (const plugin of pluginVariables.value.plugins) {
        for (const variable of plugin.variables || []) {
          const prefillValue = prefillData[variable.variable_name];
          if (prefillValue !== undefined) {
            setVariableValue(
              plugin.plugin_code,
              variable.variable_name,
              prefillValue,
            );
          }
        }
      }
    }
  }

  if (query.model && typeof query.model === 'string') {
    // 预填模型
    enableModelOverride.value = true;
    overrideModelCode.value = query.model;
  }
  if (query.temperature && typeof query.temperature === 'string') {
    // 预填温度
    enableModelOverride.value = true;
    overrideTemperature.value = Number.parseFloat(query.temperature);
  }
});

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeyDown);
});

// ==================== 复制操作包装 ====================

function handleCopy(text: string) {
  copyToClipboard(text);
  message.success('已复制到剪贴板');
}

function handleResetEdits() {
  resetAllEdits();
  message.success('已恢复原始 Prompt');
}
</script>

<template>
  <div class="expert-debugger">
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
          {{ route.meta.title || '专家调试面板' }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">Expert选择</span>
          <Select
            v-model:value="selectedExpert"
            :options="expertOptions"
            placeholder="选择要调试的 Expert"
            style="width: 350px"
            show-search
            option-filter-prop="label"
            :loading="loading"
            @change="handleExpertChange"
          />
        </div>

        <!-- 操作按钮区 -->
        <div class="filter-actions toolbar-actions">
          <!-- 主操作 -->
          <div class="action-group primary-actions">
            <Button
              type="primary"
              size="large"
              :loading="executing"
              :disabled="!selectedExpert"
              @click="handleExecute"
            >
              执行调试
            </Button>
          </div>

          <Divider type="vertical" class="toolbar-divider" />

          <!-- 批量操作 -->
          <div class="action-group batch-actions">
            <Dropdown :disabled="!selectedExpert">
              <Button :disabled="!selectedExpert">
                批量操作
                <DownOutlined />
              </Button>
              <template #overlay>
                <Menu>
                  <!-- GENERATION 类型专用 -->
                  <MenuItem
                    v-if="showBatchGeneration"
                    key="random"
                    @click="openBatchRandomModal"
                  >
                    <span>批量随机生成</span>
                  </MenuItem>
                  <MenuItem
                    v-if="showBatchGeneration"
                    key="fixed"
                    @click="openBatchFixedModal"
                  >
                    <span>批量固定生成</span>
                  </MenuItem>
                  <MenuItem
                    v-if="showBatchGeneration"
                    key="strategy"
                    @click="openBatchStrategyTestModal"
                  >
                    <span>批量策略测试</span>
                  </MenuItem>
                  <!-- BAN/CRITIC 类型专用 -->
                  <MenuItem
                    v-if="showBatchScore"
                    key="score"
                    @click="openBatchModal(selectedExpert)"
                  >
                    <span>批量评分</span>
                  </MenuItem>
                  <!-- GENERATION 类型专用 -->
                  <MenuDivider v-if="showBatchGeneration" />
                  <MenuItem
                    v-if="showBatchGeneration"
                    key="history"
                    @click="openBatchHistoryModal"
                  >
                    <span>批量历史</span>
                  </MenuItem>
                </Menu>
              </template>
            </Dropdown>
          </div>

          <Divider type="vertical" class="toolbar-divider" />

          <!-- 辅助操作 -->
          <div class="action-group secondary-actions">
            <Button @click="showHistory(selectedExpert)"> 历史记录 </Button>
            <Switch
              v-model:checked="isCompareMode"
              checked-children="对比模式"
              un-checked-children="对比模式"
              class="compare-switch"
            />
            <Button
              type="text"
              @click="fetchExpertConfigs"
              title="刷新配置列表"
            >
              刷新
            </Button>
          </div>
        </div>
      </div>
    </div>

    <!-- 第一行：配置摘要 + 测试内容 -->
    <Row v-if="selectedExpert" :gutter="16" class="mb-4" type="flex">
      <Col :span="12">
        <Card
          v-if="selectedExpertDetail"
          title="📋 配置摘要"
          size="small"
          class="equal-height-card"
        >
          <template v-if="isCompareMode" #extra>
            <Space>
              <Button
                v-if="compareGroups.length >= 2"
                type="primary"
                size="small"
                @click="openABTestModal"
              >
                🧪 创建AB测试
              </Button>
              <Tabs
                v-model:active-key="activeGroupIndex"
                type="editable-card"
                size="small"
                class="group-tabs"
                @edit="
                  (targetKey: any, action: string) =>
                    action === 'add'
                      ? addCompareGroup()
                      : removeCompareGroup(Number(targetKey))
                "
              >
                <TabPane
                  v-for="(group, index) in compareGroups"
                  :key="index"
                  :tab="group.name"
                  :closable="compareGroups.length > 1"
                />
              </Tabs>
            </Space>
          </template>
          <Space direction="vertical" style="width: 100%">
            <div class="config-row">
              <span class="config-label">模型:</span>
              <Tag color="blue">
                {{ selectedExpertDetail.model_code || '未配置' }}
              </Tag>
            </div>
            <div class="config-row">
              <span class="config-label">类型:</span>
              <Tag>{{ selectedExpertDetail.expert_type }}</Tag>
            </div>
            <div class="config-row">
              <span class="config-label">Plugin 数:</span>
              <Tag color="green">
                {{
                  Object.keys(selectedExpertDetail.plugin_config || {}).length
                }}
              </Tag>
            </div>
          </Space>

          <!-- 参数覆盖 -->
          <div class="mt-4">
            <div class="config-row">
              <span class="config-label">覆盖参数:</span>
              <Switch v-model:checked="enableModelOverride" size="small" />
            </div>
            <div v-if="enableModelOverride" class="override-panel mt-2">
              <div class="config-row">
                <span class="config-label">模型:</span>
                <ModelSelect
                  v-model:value="overrideModelCode"
                  size="small"
                  style="width: 100%"
                />
              </div>
              <div class="config-row mt-2">
                <span class="config-label">Temperature:</span>
                <Slider
                  v-model:value="overrideTemperature"
                  :min="0"
                  :max="2"
                  :step="0.1"
                  style="width: 150px"
                />
                <span class="ml-2">{{ overrideTemperature }}</span>
              </div>
              <div class="config-row mt-2">
                <span class="config-label">Max Tokens:</span>
                <Slider
                  v-model:value="overrideMaxTokens"
                  :min="100"
                  :max="8000"
                  :step="100"
                  style="width: 150px"
                />
                <span class="ml-2">{{ overrideMaxTokens }}</span>
              </div>
            </div>
          </div>
        </Card>
      </Col>

      <Col :span="12">
        <Card
          :title="
            isGenerationType
              ? '📄 测试内容（GENERATION类型无需输入）'
              : '📄 测试内容（CRITIC/BAN类型专用）'
          "
          size="small"
          class="equal-height-card"
          :class="{ 'disabled-card': isGenerationType }"
        >
          <template v-if="isGenerationType">
            <div class="disabled-content-placeholder">
              <span class="placeholder-icon">🚫</span>
              <p class="placeholder-text">
                GENERATION 类型专家无需输入测试内容
              </p>
              <p class="placeholder-hint">
                生成类专家会根据变量配置自动生成内容
              </p>
            </div>
          </template>
          <MonacoEditor
            v-else
            v-model:model-value="inputContent"
            language="plaintext"
            height="180px"
            placeholder="输入需要处理的文本内容（用于 CRITIC/BAN 类型专家评估）..."
          />
        </Card>
      </Col>
    </Row>

    <!-- 第二行：变量选择 + Prompt 预览 -->
    <Row v-if="selectedExpert" :gutter="16" class="main-content" type="flex">
      <Col :span="12" class="left-panel">
        <Card
          v-if="pluginVariables && pluginVariables.plugins.length > 0"
          title="🏷️ 变量选择"
          size="small"
          class="variable-select-card"
        >
          <template #extra>
            <Space>
              <Button
                size="small"
                @click="refreshPluginVariables"
                title="刷新插件变量"
              >
                🔄
              </Button>
              <Button size="small" @click="randomizeAllVariables">
                🎲 随机
              </Button>
            </Space>
          </template>
          <Spin :spinning="previewLoading">
            <Collapse v-model:active-key="activeCollapseKeys">
              <CollapsePanel
                v-for="(plugin, pluginIndex) in pluginVariables.plugins"
                :key="plugin.plugin_code"
              >
                <template #header>
                  <div class="plugin-header-with-color">
                    <span
                      class="plugin-color-indicator"
                      :style="{
                        backgroundColor: getPluginColor(pluginIndex).border,
                      }"
                    ></span>
                    <span>{{
                      `${plugin.plugin_name || plugin.plugin_code} (${plugin.variables.length} 个变量)`
                    }}</span>
                    <!-- 显示策略名称 -->
                    <span v-if="plugin.strategy_id" class="plugin-strategy-id">
                      策略：{{ getStrategyNameForPlugin(plugin) }}
                    </span>
                  </div>
                </template>
                <template #extra>
                  <Tag
                    size="small"
                    :color="getPluginStrategyTagColor(plugin)"
                    class="mr-2"
                  >
                    {{ getPluginStrategyTagLabel(plugin) }}
                  </Tag>
                  <Button
                    size="small"
                    type="link"
                    @click.stop="openStrategyImportForPlugin(plugin)"
                  >
                    📋 导入策略
                  </Button>
                </template>
                <div
                  v-for="variable in plugin.variables"
                  :key="variable.variable_name"
                  class="variable-item"
                >
                  <!-- eslint-disable vue/html-closing-bracket-newline -->
                  <div class="variable-name">
                    &#123;&#123;{{ variable.variable_name }}&#125;&#125;
                    <Tag
                      v-if="variable.source === 'user_profile'"
                      color="purple"
                      size="small"
                      class="ml-1"
                    >
                      👤 用户画像
                    </Tag>
                  </div>
                  <!-- eslint-enable vue/html-closing-bracket-newline -->

                  <!-- 策略绑定模式：使用 strategy_nodes -->
                  <Select
                    v-if="variable.source === 'strategy'"
                    :value="
                      getVariableValue(
                        plugin.plugin_code,
                        variable.variable_name,
                      )
                    "
                    class="variable-select"
                    size="small"
                    :dropdown-match-select-width="false"
                    :dropdown-style="{ minWidth: '400px', maxWidth: '600px' }"
                    option-label-prop="label"
                    show-search
                    :filter-option="true"
                    :get-popup-container="(trigger) => trigger.parentElement"
                    @change="
                      (v: SelectValue) => {
                        // 日志：检查选中的值
                        console.warn(
                          '[Select change] plugin:',
                          plugin.plugin_code,
                          'variable:',
                          variable.variable_name,
                          'value:',
                          v,
                        );
                        setVariableValue(
                          plugin.plugin_code,
                          variable.variable_name,
                          String(v || ''),
                        );
                      }
                    "
                    @dropdown-visible-change="
                      (open) => {
                        if (open) {
                          // 日志：下拉框打开时检查 strategy_nodes 原始数据
                          console.warn(
                            '[Select dropdown open] plugin:',
                            plugin.plugin_code,
                            'variable:',
                            variable.variable_name,
                            {
                              strategy_nodes: variable.strategy_nodes?.map(
                                (n) => ({
                                  node_id: n.node_id,
                                  node_name: n.node_name,
                                }),
                              ),
                              currentValue: getVariableValue(
                                plugin.plugin_code,
                                variable.variable_name,
                              ),
                            },
                          );
                        }
                      }
                    "
                  >
                    <SelectOption
                      v-for="node in getStrategyNodeOptions(
                        getVariableValue(
                          plugin.plugin_code,
                          variable.variable_name,
                        ),
                        variable.strategy_nodes,
                      )"
                      :key="node.node_id"
                      :value="node.node_id"
                      :label="node.node_name"
                    >
                      <div class="strategy-node-option">
                        <span class="node-name">{{
                          getStrategyNodeLabel(node)
                        }}</span>
                        <Tag
                          v-if="node.isExternal"
                          size="small"
                          color="orange"
                          class="corpus-count"
                        >
                          外部导入
                        </Tag>
                        <Tag
                          v-else
                          size="small"
                          color="default"
                          class="corpus-count"
                        >
                          {{ node.corpus_count }}条语料
                        </Tag>
                      </div>
                      <div
                        v-if="node.corpus_preview"
                        class="corpus-preview"
                        :title="node.corpus_preview"
                      >
                        {{ node.corpus_preview }}
                      </div>
                    </SelectOption>
                  </Select>
                  <!-- TODO: 语料列表展开区域（仅策略模式） -->
                  <!-- 用户画像、旧模式 plugin_context：使用 options -->
                  <Select
                    v-else
                    :value="
                      getVariableValue(
                        plugin.plugin_code,
                        variable.variable_name,
                      )
                    "
                    class="variable-select"
                    size="small"
                    :dropdown-match-select-width="false"
                    :dropdown-style="{ minWidth: '300px', maxWidth: '500px' }"
                    option-label-prop="label"
                    show-search
                    :filter-option="true"
                    :get-popup-container="(trigger) => trigger.parentElement"
                    @change="
                      (v: SelectValue) =>
                        setVariableValue(
                          plugin.plugin_code,
                          variable.variable_name,
                          String(v || ''),
                        )
                    "
                  >
                    <SelectOption
                      v-for="opt in variable.options"
                      :key="opt.context_name"
                      :value="opt.context_name"
                      :label="opt.context_name"
                    >
                      <Tooltip :title="opt.context_preview" placement="right">
                        <span class="select-option-text">{{
                          opt.context_name
                        }}</span>
                      </Tooltip>
                    </SelectOption>
                  </Select>

                  <!-- 语料列表展开区域（仅策略模式） -->
                  <div
                    v-if="
                      variable.source === 'strategy' &&
                      isCorpusExpanded(
                        plugin.plugin_code,
                        variable.variable_name,
                      )
                    "
                    class="corpus-list-container"
                  >
                    <div class="corpus-list-header">
                      <span class="corpus-list-title">选择具体语料</span>
                      <Button
                        type="link"
                        size="small"
                        @click="
                          () => {
                            const currentValue = getVariableValue(
                              plugin.plugin_code,
                              variable.variable_name,
                            );
                            const parsed = parseNodeValue(currentValue);
                            // 多选模式：随机语料清空具体选择，单选模式：清空 corpus_index
                            if (parsed.isMultiSelect) {
                              const newValue = `node:${parsed.nodeIds.join(',')}`;
                              setVariableValue(
                                plugin.plugin_code,
                                variable.variable_name,
                                newValue,
                              );
                            } else {
                              const newValue = `node:${parsed.nodeId}`;
                              setVariableValue(
                                plugin.plugin_code,
                                variable.variable_name,
                                newValue,
                              );
                            }
                          }
                        "
                      >
                        随机语料
                      </Button>
                    </div>
                    <div class="corpus-list">
                      <template
                        v-for="(nodeGroup, groupIndex) in getMergedCorpusList(
                          getVariableValue(
                            plugin.plugin_code,
                            variable.variable_name,
                          ),
                        )"
                        :key="nodeGroup.nodeId"
                      >
                        <!-- 多选模式：只在有语料时显示节点分组标题 -->
                        <div
                          v-if="
                            nodeGroup.nodeId && nodeGroup.corpusItems.length > 0
                          "
                          class="corpus-node-group-header"
                        >
                          <Tag size="small" color="blue">
                            {{ nodeGroup.nodeName }}
                          </Tag>
                          <span class="corpus-count-text"
                            >({{ nodeGroup.corpusItems.length }}条)</span
                          >
                        </div>

                        <!-- 每个节点的语料列表 -->
                        <div
                          v-for="(item, index) in nodeGroup.corpusItems"
                          :key="`${nodeGroup.nodeId}-${index}`"
                          class="corpus-item"
                          :class="{
                            'corpus-item-selected':
                              getSelectedCorpusIndex(
                                getVariableValue(
                                  plugin.plugin_code,
                                  variable.variable_name,
                                ),
                              ) === index && groupIndex === 0,
                          }"
                          @click="
                            () => {
                              const currentValue = getVariableValue(
                                plugin.plugin_code,
                                variable.variable_name,
                              );
                              const { nodeIds } = parseNodeValue(currentValue);
                              if (nodeIds.length > 0) {
                                selectCorpusItem(
                                  plugin.plugin_code,
                                  variable.variable_name,
                                  nodeGroup.nodeId,
                                  index,
                                );
                              }
                            }
                          "
                        >
                          <div class="corpus-item-header">
                            <Tag
                              size="small"
                              :color="index % 2 === 0 ? 'blue' : 'green'"
                            >
                              #{{ index + 1 }}
                            </Tag>
                            <span class="corpus-item-preview">
                              {{
                                Array.isArray(item)
                                  ? getCombinedCorpusPreview(item as any, 80)
                                  : getCorpusPreview(item as any, 80)
                              }}
                            </span>
                          </div>
                        </div>
                      </template>

                      <!-- 语料为空时的提示 -->
                      <div
                        v-if="
                          getMergedCorpusList(
                            getVariableValue(
                              plugin.plugin_code,
                              variable.variable_name,
                            ),
                          ).every((group) => group.corpusItems.length === 0)
                        "
                        class="corpus-empty"
                      >
                        暂无语料
                      </div>
                    </div>
                  </div>

                  <!-- 语料展开按钮（仅策略模式） -->
                  <div
                    v-if="variable.source === 'strategy'"
                    class="corpus-expand-btn"
                  >
                    <Button
                      v-if="
                        parseNodeValue(
                          getVariableValue(
                            plugin.plugin_code,
                            variable.variable_name,
                          ),
                        ).nodeId
                      "
                      type="link"
                      size="small"
                      @click="
                        async () => {
                          const currentValue = getVariableValue(
                            plugin.plugin_code,
                            variable.variable_name,
                          );
                          const parsed = parseNodeValue(currentValue);
                          if (
                            parsed &&
                            parsed.nodeId &&
                            !isCorpusExpanded(
                              plugin.plugin_code,
                              variable.variable_name,
                            )
                          ) {
                            // 加载所有节点的语料（多选模式）
                            if (
                              parsed.isMultiSelect &&
                              Array.isArray(parsed.nodeIds) &&
                              parsed.nodeIds.length > 0
                            ) {
                              // 确保获取所有节点的名称
                              await ensureKeywordNodeNames(parsed.nodeIds);

                              // 使用 for...of 循环代替 Promise.all，避免兼容性问题
                              for (const id of parsed.nodeIds) {
                                await ensureNodeCorpus(id);
                              }
                            } else if (parsed.nodeId) {
                              // 确保获取单个节点的名称
                              await ensureKeywordNodeNames([parsed.nodeId]);
                              await ensureNodeCorpus(parsed.nodeId);
                            }
                          }
                          toggleCorpusExpand(
                            plugin.plugin_code,
                            variable.variable_name,
                          );
                        }
                      "
                    >
                      <template #icon>
                        <DownOutlined
                          v-if="
                            !isCorpusExpanded(
                              plugin.plugin_code,
                              variable.variable_name,
                            )
                          "
                        />
                        <UpOutlined v-else />
                      </template>
                      {{
                        isCorpusExpanded(
                          plugin.plugin_code,
                          variable.variable_name,
                        )
                          ? '收起语料'
                          : '展开语料'
                      }}
                    </Button>
                  </div>
                </div>
              </CollapsePanel>
            </Collapse>
          </Spin>
        </Card>
      </Col>

      <!-- 右侧面板 - Prompt 预览 -->
      <Col :span="12" class="right-panel">
        <Card title="💻 Prompt 预览" size="small" class="prompt-preview-card">
          <template #extra>
            <Space>
              <Button
                v-if="hasEditedSegments && !usePromptOverride"
                size="small"
                type="link"
                danger
                @click="handleResetEdits"
              >
                🔄 恢复原始
              </Button>
              <Tag
                v-if="hasEditedSegments && !usePromptOverride"
                color="warning"
              >
                已编辑
              </Tag>
              <Switch
                v-model:checked="usePromptOverride"
                checked-children="手动编辑"
                un-checked-children="自动渲染"
                size="small"
              />
              <Button size="small" @click="handleCopy(finalPrompt)">
                📋 复制
              </Button>
            </Space>
          </template>
          <div class="prompt-editor-container">
            <!-- 分段显示模式 -->
            <div
              v-if="!usePromptOverride && pluginSegments.length > 0"
              class="prompt-segments"
            >
              <div
                v-for="(segment, index) in pluginSegments"
                :key="`${segment.plugin_code}-${index}`"
                class="prompt-segment"
                :class="{
                  'segment-edited': editedSegments[index] !== undefined,
                }"
                :style="{
                  borderLeftColor: getPluginColor(index).border,
                  backgroundColor: getPluginColor(index).bg,
                }"
              >
                <div
                  class="segment-header"
                  :style="{ color: getPluginColor(index).text }"
                >
                  <div class="segment-title">
                    <span class="segment-icon">🔌</span>
                    <span class="segment-plugin-name">{{
                      segment.plugin_name || segment.plugin_code
                    }}</span>
                    <Tag
                      v-if="editedSegments[index] !== undefined"
                      size="small"
                      color="warning"
                    >
                      已修改
                    </Tag>
                  </div>
                  <div class="segment-actions">
                    <Button
                      v-if="editingSegmentIndex !== index"
                      size="small"
                      type="link"
                      @click="startEditSegment(index)"
                    >
                      ✏️ 编辑
                    </Button>
                    <template v-else>
                      <Button size="small" type="link" @click="saveEditSegment">
                        ✅ 完成
                      </Button>
                      <Button
                        size="small"
                        type="link"
                        danger
                        @click="cancelEditSegment(index)"
                      >
                        ↩️ 撤销
                      </Button>
                    </template>
                  </div>
                </div>
                <textarea
                  v-if="editingSegmentIndex === index"
                  v-model="editedSegments[index]"
                  class="segment-editor"
                  :style="{ borderColor: getPluginColor(index).border }"
                ></textarea>
                <pre v-else class="segment-content">{{
                  getSegmentContent(index, segment.content)
                }}</pre>
              </div>
            </div>
            <MonacoEditor
              v-else-if="!usePromptOverride"
              :model-value="renderedPrompt"
              language="prompt"
              height="100%"
              :readonly="true"
              placeholder="选择 Expert 后自动渲染 Prompt..."
            />
            <MonacoEditor
              v-else
              v-model:model-value="promptOverride"
              language="prompt"
              height="100%"
              placeholder="手动编辑 Prompt..."
            />
          </div>
        </Card>
      </Col>
    </Row>

    <!-- 对比结果展示区 -->
    <ComparisonResultsGrid
      v-if="isCompareMode && comparisonResults.length > 0"
      :compare-groups="compareGroups"
      :comparison-results="comparisonResults"
      :model-routes="modelRoutes"
      @view-detail="handleViewComparisonDetail"
    />

    <!-- 底部执行结果 -->
    <Card
      v-if="!isCompareMode || comparisonResults.length === 0"
      title="📊 执行结果"
      size="small"
      class="result-section"
    >
      <Spin :spinning="executing" tip="执行中...">
        <template v-if="debugResult">
          <Row :gutter="16" class="mb-4">
            <Col :span="6">
              <Statistic
                title="状态"
                :value="debugResult.success ? '成功' : '失败'"
                :value-style="{
                  color: debugResult.success ? '#52c41a' : '#ff4d4f',
                  fontSize: '20px',
                }"
              />
            </Col>
            <Col :span="6">
              <Statistic title="耗时" :value-style="{ fontSize: '20px' }">
                <template #formatter>
                  {{ formatExecutionTime(debugResult.execution_time_ms) }}
                </template>
              </Statistic>
            </Col>
            <Col :span="6">
              <Statistic
                title="Tokens"
                :value="getEffectiveTokenUsage(debugResult).total_tokens"
                :value-style="{ fontSize: '20px' }"
              >
                <template #suffix>
                  <Tooltip>
                    <template #title>
                      Prompt:
                      {{ getEffectiveTokenUsage(debugResult).prompt_tokens }} |
                      Completion:
                      {{
                        getEffectiveTokenUsage(debugResult).completion_tokens
                      }}
                    </template>
                    <span class="info-icon" style="font-size: 14px">ⓘ</span>
                  </Tooltip>
                </template>
              </Statistic>
            </Col>
            <Col :span="6">
              <Statistic
                title="预估费用"
                :value="
                  calculateCost(
                    debugResult.model_code || '',
                    modelRoutes,
                    debugResult,
                  )
                "
                :value-style="{
                  fontSize: '20px',
                  color: 'hsl(var(--primary))',
                }"
                prefix="$"
              />
            </Col>
          </Row>

          <Alert
            v-if="debugResult.error_message"
            type="error"
            :message="debugResult.error_message"
            show-icon
            class="mb-4"
          />

          <Tabs
            :default-active-key="
              showCriticProblems ? 'critic_problems' : 'output'
            "
          >
            <TabPane
              v-if="showCriticProblems"
              key="critic_problems"
              tab="🔍 CRITIC问题"
            >
              <div class="critic-problems-section">
                <div class="problem-list-summary">
                  <Tag color="error">
                    发现 {{ criticProblemList.length }} 个问题词
                  </Tag>
                  <div class="problem-tags">
                    <Tag
                      v-for="(problem, idx) in criticProblemList"
                      :key="idx"
                      color="warning"
                    >
                      {{ problem }}
                    </Tag>
                  </div>
                </div>
                <Divider orientation="left" style="margin: 12px 0">
                  测试内容问题高亮
                </Divider>
                <!-- eslint-disable vue/no-v-html -->
                <div
                  class="highlighted-content"
                  v-html="
                    highlightProblems(
                      debugResult.input_content || '',
                      criticProblemList,
                    )
                  "
                ></div>
                <!-- eslint-enable vue/no-v-html -->
              </div>
            </TabPane>

            <TabPane key="output" tab="📄 输出结果">
              <div class="result-actions mb-2">
                <Space>
                  <Button size="small" @click="showInputOutputDiff">
                    🔀 对比输入/输出
                  </Button>
                  <Button
                    size="small"
                    @click="handleCopy(debugResult.output_content || '')"
                  >
                    📋 复制
                  </Button>
                </Space>
              </div>
              <div
                v-if="debugResult.expert_total_output?.title"
                class="output-title-section mb-3"
              >
                <span class="output-title-label">📌 标题：</span>
                <span class="output-title-text">{{
                  debugResult.expert_total_output.title
                }}</span>
              </div>
              <MonacoEditor
                :model-value="getDisplayContent(debugResult)"
                language="plaintext"
                height="300px"
                :readonly="true"
              />
            </TabPane>

            <TabPane key="detail" tab="📊 详细信息">
              <Collapse :default-active-key="['prompt']">
                <CollapsePanel key="prompt" header="💻 使用的 Prompt">
                  <MonacoEditor
                    :model-value="
                      debugResult.rendered_prompt ||
                      debugResult.prompt_override ||
                      ''
                    "
                    language="prompt"
                    height="280px"
                    :readonly="true"
                  />
                </CollapsePanel>
                <CollapsePanel key="token" header="Token 使用详情">
                  <p>
                    Prompt Tokens:
                    {{ getEffectiveTokenUsage(debugResult).prompt_tokens }}
                  </p>
                  <p>
                    Completion Tokens:
                    {{ getEffectiveTokenUsage(debugResult).completion_tokens }}
                  </p>
                  <p>
                    Total Tokens:
                    {{ getEffectiveTokenUsage(debugResult).total_tokens }}
                  </p>
                </CollapsePanel>
                <CollapsePanel key="config" header="模型配置">
                  <MonacoEditor
                    :model-value="
                      JSON.stringify(debugResult.model_config_used, null, 2)
                    "
                    language="json"
                    height="180px"
                    readonly
                    :line-numbers="false"
                    :minimap="false"
                  />
                </CollapsePanel>
                <CollapsePanel key="snapshot" header="变量快照">
                  <MonacoEditor
                    :model-value="
                      JSON.stringify(
                        debugResult.plugin_config_snapshot,
                        null,
                        2,
                      )
                    "
                    language="json"
                    height="180px"
                    readonly
                    :line-numbers="false"
                    :minimap="false"
                  />
                </CollapsePanel>
              </Collapse>
            </TabPane>

            <TabPane key="full_output" tab="📦 完整返回">
              <div class="result-actions mb-2">
                <Space>
                  <Button
                    size="small"
                    @click="
                      handleCopy(
                        JSON.stringify(
                          debugResult.expert_total_output,
                          null,
                          2,
                        ) || '',
                      )
                    "
                  >
                    📋 复制 JSON
                  </Button>
                </Space>
              </div>
              <div class="full-output-container">
                <MonacoEditor
                  :model-value="
                    JSON.stringify(debugResult.expert_total_output, null, 2)
                  "
                  language="json"
                  height="400px"
                  readonly
                  :line-numbers="true"
                  :minimap="false"
                />
              </div>
            </TabPane>
          </Tabs>
        </template>

        <template v-else>
          <div class="empty-result">
            <p>选择 Expert 并输入内容后，点击"执行调试"查看结果</p>
          </div>
        </template>
      </Spin>
    </Card>

    <!-- 历史记录抽屉 -->
    <HistoryDrawer
      v-model:visible="historyVisible"
      :loading="historyLoading"
      :history-list="historyList"
      :pagination="historyPagination"
      :selected-ids="selectedHistoryIds"
      @refresh="fetchHistory(selectedExpert)"
      @table-change="(pag) => handleHistoryTableChange(pag, selectedExpert)"
      @load="loadFromHistory"
      @star="(id, starred) => handleStarHistory(id, starred, selectedExpert)"
      @delete="(id) => handleDeleteHistory(id, selectedExpert)"
      @toggle-select="toggleHistorySelect"
      @show-diff="showHistoryDiff"
    />

    <!-- Diff 对比 Modal -->
    <Modal
      v-model:open="diffVisible"
      :title="diffTitle"
      :width="1200"
      :footer="null"
    >
      <DiffEditor
        :original="diffOriginal"
        :modified="diffModified"
        :theme="editorTheme"
        height="500px"
        :options="{
          readOnly: true,
          renderSideBySide: true,
          minimap: { enabled: false },
        }"
      />
    </Modal>

    <!-- 批量评分弹窗 -->
    <BatchEvalModal
      v-model:open="batchModalOpen"
      v-model:form="batchForm"
      :loading="batchSubmitting"
      :test-set-options="testSetOptions"
      @submit="submitBatchScore(selectedExpert)"
    />

    <!-- 批量随机生成弹窗 -->
    <Modal
      v-model:open="batchRandomModalOpen"
      title="🎯 批量随机生成"
      :width="900"
      :confirm-loading="batchRandomExecuting"
      :ok-text="batchRandomResults.length > 0 ? '重新测试' : '开始测试'"
      cancel-text="关闭"
      @ok="submitBatchRandomTest"
    >
      <!-- 配置表单 -->
      <Form layout="inline" class="mb-4">
        <FormItem label="执行次数">
          <InputNumber
            v-model:value="batchRandomForm.count"
            :min="1"
            :max="20"
            style="width: 100px"
          />
        </FormItem>
        <FormItem>
          <Switch
            v-model:checked="batchRandomForm.include_current"
            checked-children="包含当前变量"
            un-checked-children="全部随机"
          />
        </FormItem>
      </Form>

      <!-- 执行进度/摘要 -->
      <div v-if="batchRandomExecuting" class="mb-4 text-center">
        <Spin
          :tip="`正在并行执行批量随机生成... (${batchRandomResults.length}/${batchRandomForm.count})`"
        />
      </div>

      <div v-if="batchRandomSummary" class="mb-4">
        <Row :gutter="16">
          <Col :span="6">
            <Statistic title="总执行次数" :value="batchRandomSummary.total" />
          </Col>
          <Col :span="6">
            <Statistic
              title="成功"
              :value="batchRandomSummary.success_count"
              :value-style="{ color: '#52c41a' }"
            />
          </Col>
          <Col :span="6">
            <Statistic
              title="失败"
              :value="batchRandomSummary.failed_count"
              :value-style="{
                color:
                  batchRandomSummary.failed_count > 0 ? '#ff4d4f' : undefined,
              }"
            />
          </Col>
          <Col :span="6">
            <Statistic
              title="总耗时"
              :value="formatExecutionTime(batchRandomSummary.total_time_ms)"
            />
          </Col>
        </Row>
      </div>

      <!-- 结果表格 -->
      <Table
        v-if="batchRandomResults.length > 0"
        :columns="batchRandomResultColumns"
        :data-source="batchRandomResults"
        :pagination="false"
        :scroll="{ y: 400 }"
        row-key="index"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <!-- 标题列：hover 显示完整标题 -->
          <template v-if="column.key === 'title'">
            <Tooltip v-if="record.title" placement="topLeft">
              <template #title>{{ record.title }}</template>
              <span class="cursor-default">{{ record.title }}</span>
            </Tooltip>
            <span v-else class="text-muted-foreground">-</span>
          </template>
          <!-- 变量组合列：hover 显示完整变量信息 -->
          <template v-else-if="column.key === 'variable_summary'">
            <Popover
              v-if="
                record.plugin_config_snapshot &&
                record.plugin_config_snapshot.length > 0
              "
              placement="right"
              trigger="hover"
              :overlay-style="{ maxWidth: '500px' }"
            >
              <template #content>
                <div class="variable-detail-popover">
                  <div class="popover-header mb-2">
                    <span class="font-medium">📋 变量详情</span>
                  </div>
                  <div class="variable-list space-y-2">
                    <div
                      v-for="(item, idx) in record.plugin_config_snapshot"
                      :key="idx"
                      class="variable-item rounded border border-border bg-muted/50 p-2"
                    >
                      <div
                        class="variable-name mb-1 text-xs font-medium text-primary"
                      >
                        {{ item.plugin_code }}
                      </div>
                      <div
                        v-for="(value, varName) in item.variable_mapping"
                        :key="varName"
                        class="variable-mapping-item mt-1"
                      >
                        <span class="text-xs text-muted-foreground">
                          {{ varName }}:
                        </span>
                        <span class="ml-1 text-sm text-foreground">
                          {{ value || '-' }}
                        </span>
                      </div>
                      <div
                        v-if="
                          !item.variable_mapping ||
                          Object.keys(item.variable_mapping).length === 0
                        "
                        class="text-sm text-muted-foreground"
                      >
                        -
                      </div>
                    </div>
                  </div>
                </div>
              </template>
              <span class="cursor-pointer hover:text-primary">
                {{ record.variable_summary || '-' }}
              </span>
            </Popover>
            <span v-else>{{ record.variable_summary || '-' }}</span>
          </template>
          <template v-else-if="column.key === 'success'">
            <Tag :color="record.success ? 'success' : 'error'">
              {{ record.success ? '成功' : '失败' }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'execution_time_ms'">
            {{ formatExecutionTime(record.execution_time_ms) }}
          </template>
          <template v-else-if="column.key === 'output_preview'">
            <div v-if="record.output_content" class="output-preview-cell">
              <Popover
                placement="topRight"
                trigger="hover"
                :get-popup-container="getPopupContainer"
                :overlay-style="{ maxWidth: '600px' }"
                :auto-adjust-overflow="true"
              >
                <template #content>
                  <div class="batch-output-popover">
                    <div class="popover-header">
                      <span class="popover-title">📄 完整内容</span>
                      <Button
                        size="small"
                        type="text"
                        @click="copyToClipboard(record.output_content)"
                      >
                        📋 复制
                      </Button>
                    </div>
                    <div class="popover-content">
                      {{ record.output_content }}
                    </div>
                  </div>
                </template>
                <span
                  class="output-preview-text cursor-pointer hover:text-primary"
                >
                  {{ record.output_preview || record.output_content }}
                </span>
              </Popover>
            </div>
            <span v-else-if="record.error_message" class="text-destructive">
              {{ record.error_message }}
            </span>
            <span v-else class="text-muted-foreground">-</span>
          </template>
          <template v-else-if="column.key === 'action'">
            <Space>
              <Button
                size="small"
                type="link"
                :disabled="!record.plugin_config_snapshot"
                @click="
                  applyBatchResultVariables(record.plugin_config_snapshot)
                "
              >
                应用变量
              </Button>
              <Button
                v-if="record.history_id"
                size="small"
                type="link"
                @click="
                  () => {
                    batchRandomModalOpen = false;
                    showHistoryDetail(record.history_id);
                  }
                "
              >
                详情
              </Button>
            </Space>
          </template>
        </template>
      </Table>

      <!-- 空状态 -->
      <div
        v-if="!batchRandomExecuting && batchRandomResults.length === 0"
        class="py-8 text-center text-muted-foreground"
      >
        <p>配置执行次数后点击"开始测试"</p>
        <p class="mt-2 text-xs">
          随机选择变量组合并行生成多篇内容，适合快速验证生文效果
        </p>
      </div>
    </Modal>

    <!-- 批量固定生成弹窗 -->
    <Modal
      v-model:open="batchFixedModalOpen"
      :width="1000"
      :footer="null"
      :body-style="{ padding: '20px 24px' }"
      class="batch-fixed-modal"
    >
      <template #title>
        <div class="flex items-center gap-2">
          <span class="text-lg font-medium">📝 批量固定生成</span>
          <Tag color="blue" class="ml-2">并行执行</Tag>
        </div>
      </template>

      <!-- 顶部配置区域 -->
      <div class="mb-5 rounded-lg border border-border bg-card/50 p-4">
        <div class="flex items-center justify-between">
          <!-- 左侧：生成篇数 -->
          <div class="flex items-center gap-6">
            <div class="flex items-center gap-3">
              <span class="text-sm text-muted-foreground">生成篇数</span>
              <InputNumber
                v-model:value="batchFixedForm.count"
                :min="1"
                :max="20"
                :disabled="batchFixedExecuting"
                style="width: 80px"
                size="small"
              />
            </div>

            <!-- 变量配置展示 -->
            <div class="flex items-center gap-2">
              <span class="text-sm text-muted-foreground">变量配置</span>
              <div
                v-if="selectedVariables.length > 0"
                class="flex items-center gap-1"
              >
                <Tag
                  v-for="item in selectedVariables.slice(0, 3)"
                  :key="item.plugin_code"
                  color="processing"
                  class="m-0"
                >
                  {{ item.plugin_code.replace('plugin_', '').slice(0, 12) }}
                </Tag>
                <Popover
                  v-if="selectedVariables.length > 3"
                  placement="bottom"
                  trigger="hover"
                >
                  <template #content>
                    <div class="max-w-xs">
                      <div
                        v-for="item in selectedVariables"
                        :key="item.plugin_code"
                        class="mb-1 text-sm"
                      >
                        <span class="font-medium">{{ item.plugin_code }}</span>
                      </div>
                    </div>
                  </template>
                  <Tag color="default" class="m-0 cursor-pointer">
                    +{{ selectedVariables.length - 3 }}
                  </Tag>
                </Popover>
              </div>
              <span v-else class="text-sm text-muted-foreground/60">
                未配置变量
              </span>
            </div>
          </div>

          <!-- 右侧：操作按钮 -->
          <div class="flex items-center gap-2">
            <Button
              type="primary"
              :loading="batchFixedExecuting"
              :disabled="batchFixedExecuting"
              @click="submitBatchFixedGenerate"
            >
              {{ batchFixedResults.length > 0 ? '🔄 重新生成' : '🚀 开始生成' }}
            </Button>
            <Button @click="batchFixedModalOpen = false">关闭</Button>
          </div>
        </div>
      </div>

      <!-- 执行进度条 -->
      <div
        v-if="batchFixedExecuting || batchFixedResults.length > 0"
        class="mb-5"
      >
        <div class="mb-2 flex items-center justify-between text-sm">
          <span class="text-muted-foreground">
            {{ batchFixedExecuting ? '正在并行生成...' : '生成完成' }}
          </span>
          <span class="font-medium">
            {{ batchFixedResults.length }} / {{ batchFixedForm.count }}
          </span>
        </div>
        <Progress
          :percent="
            Math.round((batchFixedResults.length / batchFixedForm.count) * 100)
          "
          :status="
            batchFixedExecuting
              ? 'active'
              : (batchFixedSummary?.failed_count || 0) > 0
                ? 'exception'
                : 'success'
          "
          :stroke-color="
            batchFixedExecuting
              ? undefined
              : { '0%': '#52c41a', '100%': '#87d068' }
          "
        />
      </div>

      <!-- 统计卡片 -->
      <div v-if="batchFixedSummary" class="mb-5">
        <Row :gutter="16">
          <Col :span="6">
            <div class="rounded-lg bg-muted/30 p-4 text-center">
              <div class="mb-1 text-2xl font-bold text-foreground">
                {{ batchFixedSummary.total }}
              </div>
              <div class="text-sm text-muted-foreground">📊 总篇数</div>
            </div>
          </Col>
          <Col :span="6">
            <div class="rounded-lg bg-green-500/10 p-4 text-center">
              <div class="mb-1 text-2xl font-bold text-green-500">
                {{ batchFixedSummary.success_count }}
              </div>
              <div class="text-sm text-muted-foreground">✅ 成功</div>
            </div>
          </Col>
          <Col :span="6">
            <div
              class="rounded-lg p-4 text-center"
              :class="
                batchFixedSummary.failed_count > 0
                  ? 'bg-red-500/10'
                  : 'bg-muted/30'
              "
            >
              <div
                class="mb-1 text-2xl font-bold"
                :class="
                  batchFixedSummary.failed_count > 0
                    ? 'text-red-500'
                    : 'text-foreground'
                "
              >
                {{ batchFixedSummary.failed_count }}
              </div>
              <div class="text-sm text-muted-foreground">❌ 失败</div>
            </div>
          </Col>
          <Col :span="6">
            <div class="rounded-lg bg-blue-500/10 p-4 text-center">
              <div class="mb-1 text-2xl font-bold text-blue-500">
                {{ formatExecutionTime(batchFixedTotalTime) }}
              </div>
              <div class="text-sm text-muted-foreground">⏱️ 总耗时</div>
            </div>
          </Col>
        </Row>
      </div>

      <!-- 结果表格 -->
      <div
        v-if="batchFixedResults.length > 0"
        class="batch-fixed-table-wrapper rounded-lg border border-border"
      >
        <Table
          :columns="batchFixedResultColumns"
          :data-source="batchFixedResults"
          :pagination="false"
          :scroll="{ y: 320 }"
          row-key="index"
          size="small"
          class="batch-fixed-table"
          :custom-row="() => ({ style: { overflow: 'visible' } })"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'index'">
              <span class="font-mono text-muted-foreground">
                #{{ record.index }}
              </span>
            </template>
            <template v-else-if="column.key === 'success'">
              <Tag :color="record.success ? 'success' : 'error'" class="m-0">
                {{ record.success ? '✓ 成功' : '✗ 失败' }}
              </Tag>
            </template>
            <template v-else-if="column.key === 'title'">
              <Tooltip v-if="record.title" :title="record.title">
                <span class="cursor-pointer">{{ record.title }}</span>
              </Tooltip>
              <span v-else class="text-muted-foreground">-</span>
            </template>
            <template v-else-if="column.key === 'execution_time_ms'">
              <span class="font-mono text-sm">
                {{ formatExecutionTime(record.execution_time_ms) }}
              </span>
            </template>
            <template v-else-if="column.key === 'output_preview'">
              <div v-if="record.output_content" class="output-preview-cell">
                <Popover
                  placement="topRight"
                  trigger="hover"
                  :get-popup-container="getPopupContainer"
                  :overlay-style="{ maxWidth: '400px' }"
                  :auto-adjust-overflow="true"
                >
                  <template #content>
                    <div
                      style="
                        display: flex;
                        flex-direction: column;
                        gap: 8px;
                        width: 300px;
                      "
                    >
                      <div style="display: flex; justify-content: flex-end">
                        <Button
                          size="small"
                          type="text"
                          @click="copyToClipboard(record.output_content)"
                        >
                          📋 复制
                        </Button>
                      </div>
                      <div
                        style="
                          max-height: 300px;
                          padding: 12px;
                          overflow-y: auto;
                          font-size: 13px;
                          line-height: 1.6;
                          overflow-wrap: break-word;
                          white-space: pre-wrap;
                          background: hsl(var(--muted) / 30%);
                          border-radius: 6px;
                        "
                      >
                        {{ record.output_content }}
                      </div>
                    </div>
                  </template>
                  <div
                    class="line-clamp-2 cursor-pointer text-sm leading-relaxed hover:text-primary"
                  >
                    {{ record.output_preview || record.output_content }}
                  </div>
                </Popover>
              </div>
              <div
                v-else-if="record.error_message"
                class="text-sm text-destructive"
              >
                {{ record.error_message }}
              </div>
              <span v-else class="text-muted-foreground">-</span>
            </template>
            <template v-else-if="column.key === 'action'">
              <div class="flex items-center gap-1">
                <Tooltip v-if="record.history_id" title="查看详情">
                  <Button
                    type="text"
                    size="small"
                    class="action-btn"
                    @click="
                      () => {
                        batchFixedModalOpen = false;
                        showHistoryDetail(record.history_id);
                      }
                    "
                  >
                    👁️
                  </Button>
                </Tooltip>
                <Tooltip v-if="record.output_content" title="复制内容">
                  <Button
                    type="text"
                    size="small"
                    class="action-btn"
                    @click="copyToClipboard(record.output_content)"
                  >
                    📋
                  </Button>
                </Tooltip>
              </div>
            </template>
          </template>
        </Table>
      </div>

      <!-- 空状态 -->
      <div
        v-if="!batchFixedExecuting && batchFixedResults.length === 0"
        class="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-16"
      >
        <div class="mb-3 text-4xl">📝</div>
        <p class="mb-1 text-foreground">配置生成篇数后点击"开始生成"</p>
        <p class="text-sm text-muted-foreground">
          使用固定参数并行生成多篇内容，适合批量产出
        </p>
      </div>
    </Modal>

    <!-- 批量历史记录 Modal -->
    <Modal
      v-model:open="batchHistoryModalOpen"
      title="📊 批量随机生成历史"
      :width="1200"
      :footer="null"
    >
      <Table
        :columns="[
          {
            title: '任务ID',
            dataIndex: 'task_id',
            key: 'task_id',
            width: 200,
            ellipsis: true,
          },
          {
            title: 'Expert',
            dataIndex: 'expert_config_name',
            key: 'expert_config_name',
            width: 200,
            ellipsis: true,
          },
          { title: '状态', dataIndex: 'status', key: 'status', width: 100 },
          { title: '总数', dataIndex: 'total', key: 'total', width: 80 },
          {
            title: '成功',
            dataIndex: 'success_count',
            key: 'success_count',
            width: 80,
          },
          {
            title: '失败',
            dataIndex: 'failed_count',
            key: 'failed_count',
            width: 80,
          },
          {
            title: '创建时间',
            dataIndex: 'create_time',
            key: 'create_time',
            width: 180,
          },
          { title: '操作', key: 'action', width: 120 },
        ]"
        :data-source="batchHistoryList"
        :loading="batchHistoryLoading"
        :pagination="{
          current: batchHistoryPage,
          pageSize: batchHistoryPageSize,
          total: batchHistoryTotal,
          showTotal: (total: number) => `共 ${total} 条`,
          onChange: (page: number) => {
            batchHistoryPage = page;
            fetchBatchHistory();
          },
        }"
        row-key="id"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <Tag v-if="record.status === 'completed'" color="success">
              已完成
            </Tag>
            <Tag v-else-if="record.status === 'failed'" color="error">失败</Tag>
            <Tag v-else-if="record.status === 'running'" color="processing">
              执行中
            </Tag>
            <Tag v-else color="default">待执行</Tag>
          </template>
          <template v-else-if="column.key === 'create_time'">
            {{ formatDateTime(record.create_time) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <Button
              type="link"
              size="small"
              @click="viewBatchTaskDetail(record.task_id)"
            >
              查看结果
            </Button>
          </template>
        </template>
      </Table>
    </Modal>

    <!-- 策略导入抽屉 -->
    <StrategyImportDrawer
      v-model:open="strategyImportDrawerOpen"
      :expert-variables="expertVariablesForStrategy"
      :target-plugin-code="strategyImportTargetPluginCode"
      :target-plugin-name="strategyImportTargetPluginName"
      @apply="handleStrategyApply"
    />

    <!-- 批量策略测试弹窗 -->
    <BatchStrategyTestModal
      v-model:open="batchStrategyTestModalOpen"
      :expert-code="selectedExpert || ''"
      :expert-variables="expertVariablesForStrategy"
      :expert-plugin-config="expertPluginConfigList"
    />

    <!-- AB测试弹窗 -->
    <ABTestModal
      v-if="selectedExpert"
      v-model:open="abTestModalOpen"
      :compare-groups="compareGroups"
      :input-content="inputContent"
      :expert-code="selectedExpert"
      @success="handleABTestSuccess"
    />
  </div>
</template>

<style scoped>
.expert-debugger {
  display: flex;
  flex-direction: column;
  height: 100%;
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

.toolbar-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.action-group {
  display: flex;
  gap: 8px;
  align-items: center;
}

.toolbar-divider {
  height: 24px;
  margin: 0 4px;
  border-color: hsl(var(--border));
}

.primary-actions :deep(.ant-btn-primary) {
  font-weight: 600;
  box-shadow: 0 2px 8px hsl(var(--primary) / 30%);
}

.primary-actions :deep(.ant-btn-primary:hover:not(:disabled)) {
  box-shadow: 0 4px 12px hsl(var(--primary) / 40%);
  transform: translateY(-1px);
}

.btn-icon {
  margin-right: 4px;
}

.compare-switch {
  margin-left: 4px;
}

.batch-actions :deep(.ant-dropdown-trigger) {
  display: flex;
  gap: 4px;
  align-items: center;
}

.secondary-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.main-content {
  display: flex;
  align-items: stretch;
  margin-bottom: 16px;
}

.left-panel,
.right-panel {
  display: flex;
  flex-direction: column;
}

.equal-height-card {
  height: 100%;
}

.disabled-card {
  opacity: 0.7;
}

.disabled-card :deep(.ant-card-head-title) {
  color: hsl(var(--muted-foreground));
}

.disabled-content-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 180px;
  padding: 24px;
  text-align: center;
  background: linear-gradient(
    135deg,
    hsl(var(--muted) / 30%) 0%,
    hsl(var(--muted) / 10%) 100%
  );
  border: 2px dashed hsl(var(--border));
  border-radius: 8px;
}

.placeholder-icon {
  margin-bottom: 12px;
  font-size: 32px;
  opacity: 0.6;
}

.placeholder-text {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
}

.placeholder-hint {
  margin: 0;
  font-size: 12px;
  color: hsl(var(--muted-foreground) / 70%);
}

.variable-select-card {
  display: flex;
  flex: 1;
  flex-direction: column;
}

.variable-select-card :deep(.ant-card-body) {
  flex: 1;
  overflow-y: auto;
}

.prompt-preview-card {
  display: flex;
  flex: 1;
  flex-direction: column;
  width: 100%;
}

.prompt-preview-card :deep(.ant-card-body) {
  display: flex;
  flex: 1;
  flex-direction: column;
}

.prompt-editor-container {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 300px;
}

.prompt-segments {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
}

.prompt-segment {
  padding: 12px 16px;
  border-left: 4px solid;
  border-radius: 0 8px 8px 0;
  transition: all 0.2s ease;
}

.prompt-segment:hover {
  transform: translateX(4px);
}

.segment-header {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}

.segment-title {
  display: flex;
  gap: 8px;
  align-items: center;
}

.segment-actions {
  display: flex;
  gap: 4px;
}

.segment-icon {
  font-size: 14px;
}

.segment-plugin-name {
  font-family: Monaco, Menlo, Consolas, monospace;
}

.segment-content {
  max-height: 300px;
  padding: 0;
  margin: 0;
  overflow-y: auto;
  font-family: Monaco, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  color: hsl(var(--foreground));
  word-break: break-all;
  overflow-wrap: break-word;
  white-space: pre-wrap;
}

.segment-edited {
  box-shadow: 0 0 0 2px rgb(250 173 20 / 30%);
}

.segment-editor {
  width: 100%;
  min-height: 150px;
  max-height: 400px;
  padding: 12px;
  font-family: Monaco, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  color: hsl(var(--foreground));
  resize: vertical;
  background: hsl(var(--background));
  border: 2px solid;
  border-radius: 6px;
}

.segment-editor:focus {
  outline: none;
  box-shadow: 0 0 0 3px rgb(59 130 246 / 30%);
}

.result-section {
  margin-top: 16px;
}

.mb-4 {
  margin-bottom: 16px;
}

.mb-3 {
  margin-bottom: 12px;
}

.mb-2 {
  margin-bottom: 8px;
}

.mt-2 {
  margin-top: 8px;
}

.mt-4 {
  margin-top: 16px;
}

.ml-2 {
  margin-left: 8px;
}

.config-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.config-label {
  width: 80px;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.override-panel {
  padding: 12px;
  background: hsl(var(--muted));
  border-radius: 6px;
}

.plugin-header-with-color {
  display: flex;
  gap: 8px;
  align-items: center;
}

.plugin-color-indicator {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 3px;
}

.plugin-strategy-id {
  margin-left: auto;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.variable-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 0;
  border-bottom: 1px solid hsl(var(--border));
}

.variable-item:last-child {
  border-bottom: none;
}

.variable-name {
  font-family: Monaco, Menlo, Consolas, monospace;
  font-size: 13px;
  color: hsl(var(--primary));
  word-break: break-all;
}

.variable-select {
  width: 100%;
}

.select-option-text {
  display: block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 策略节点选项样式 */
.strategy-node-option {
  display: flex;
  gap: 8px;
  align-items: center;
}

.strategy-node-option .node-name {
  font-weight: 500;
}

.strategy-node-option .corpus-count {
  margin-left: auto;
  font-size: 11px;
}

.corpus-preview {
  max-width: 350px;
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
}

/* 语料列表展开区域 */
.corpus-expand-btn {
  margin-top: 8px;
  text-align: left;
}

.corpus-list-container {
  padding: 8px;
  margin-top: 8px;
  background: hsl(var(--muted) / 20%);
  border: 1px solid hsl(var(--border));
  border-radius: 4px;
}

.corpus-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.corpus-list-title {
  font-size: 12px;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
}

.corpus-list {
  max-height: 240px;
  overflow-y: auto;
}

.corpus-item {
  padding: 8px 12px;
  margin-bottom: 4px;
  cursor: pointer;
  background: hsl(var(--background));
  border: 1px solid hsl(var(--border));
  border-radius: 4px;
  transition: all 0.2s;
}

.corpus-item:hover {
  background: hsl(var(--primary) / 5%);
  border-color: hsl(var(--primary) / 50%);
}

.corpus-item-selected {
  background: hsl(var(--primary) / 10%);
  border-color: hsl(var(--primary));
}

.corpus-item-header {
  display: flex;
  gap: 8px;
  align-items: center;
}

.corpus-item-preview {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.corpus-empty {
  padding: 16px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

/* 节点分组标题（多选模式） */
.corpus-node-group-header {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  margin-bottom: 8px;
  background: hsl(var(--muted) / 30%);
  border-radius: 4px;
}

.corpus-count-text {
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.result-actions {
  display: flex;
  justify-content: flex-end;
}

.output-title-section {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 10%) 0%,
    hsl(var(--primary) / 5%) 100%
  );
  border: 1px solid hsl(var(--primary) / 20%);
  border-radius: 8px;
}

.output-title-label {
  font-size: 14px;
  font-weight: 500;
  color: hsl(var(--primary));
}

.output-title-text {
  font-size: 15px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.full-output-container {
  overflow: hidden;
  border-radius: 8px;
}

.critic-problems-section {
  padding: 16px;
}

.problem-list-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}

.problem-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.highlighted-content {
  max-height: 400px;
  padding: 16px;
  overflow-y: auto;
  font-size: 14px;
  line-height: 1.8;
  color: hsl(var(--foreground));
  word-break: break-all;
  overflow-wrap: break-word;
  white-space: pre-wrap;
  background: hsl(var(--muted) / 30%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.highlighted-content :deep(.problem-highlight) {
  padding: 2px 4px;
  font-weight: 600;
  color: #d32f2f;
  background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%);
  border-radius: 4px;
  box-shadow: 0 1px 3px rgb(211 47 47 / 30%);
}

.empty-result {
  padding: 80px 0;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.info-icon {
  margin-left: 2px;
  cursor: help;
  opacity: 0.6;
}

.group-tabs {
  margin-top: -12px;
  margin-bottom: -13px;
}

.group-tabs :deep(.ant-tabs-nav) {
  margin-bottom: 0 !important;
}

.group-tabs :deep(.ant-tabs-nav::before) {
  display: none;
}

.group-tabs :deep(.ant-tabs-tab) {
  padding: 4px 12px !important;
  background: transparent !important;
  border: 1px solid transparent !important;
  transition: all 0.2s;
}

.group-tabs :deep(.ant-tabs-tab-active) {
  background: hsl(var(--card)) !important;
  border-color: hsl(var(--border)) !important;
  border-bottom-color: hsl(var(--card)) !important;
}

.group-tabs :deep(.ant-tabs-nav-add) {
  min-width: 32px !important;
  height: 28px !important;
  padding: 0 !important;
  margin-left: 4px !important;
  line-height: 28px !important;
  background: hsl(var(--muted) / 50%) !important;
  border: 1px solid hsl(var(--border)) !important;
  border-radius: 4px !important;
}

.group-tabs :deep(.ant-tabs-nav-add:hover) {
  color: hsl(var(--primary));
  background: hsl(var(--muted)) !important;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  height: 64px;
  padding: 8px;
  background: hsl(var(--muted) / 50%);
  border-radius: 6px;
}

.metric-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.4;
  color: hsl(var(--muted-foreground));
}

/* 批量固定生成弹窗样式 */
.batch-fixed-modal :deep(.ant-modal-header) {
  padding-bottom: 12px;
  border-bottom: 1px solid hsl(var(--border));
}

/* 表格包装器：保留圆角但不裁剪 Popover */
.batch-fixed-table-wrapper {
  position: relative;
}

.batch-fixed-table-wrapper :deep(.ant-table) {
  border-radius: 8px;
}

.batch-fixed-table :deep(.ant-table-thead > tr > th) {
  font-weight: 500;
  background: hsl(var(--muted));
}

.batch-fixed-table :deep(.ant-table-tbody > tr:hover > td) {
  background: hsl(var(--muted) / 30%);
}

.output-preview-cell {
  max-width: 100%;
}

.line-clamp-2 {
  display: -webkit-box;
  overflow: hidden;
  text-overflow: ellipsis;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border-radius: 4px;
}

.action-btn:hover {
  background: hsl(var(--muted));
}

/* 变量详情 Popover 样式 */
.variable-detail-popover {
  max-width: 500px;
  max-height: 400px;
  overflow-y: auto;
}

.variable-detail-popover .variable-item {
  transition: background-color 0.2s;
}

.variable-detail-popover .variable-item:hover {
  background: hsl(var(--muted));
}

.variable-detail-popover .variable-name {
  font-weight: 500;
}

.variable-detail-popover .variable-mapping-item {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  padding: 2px 0;
}

.variable-detail-popover .variable-mapping-item span:last-child {
  word-break: break-all;
  white-space: pre-wrap;
}

.output-preview-cell:hover .line-clamp-2 {
  color: hsl(var(--primary));
}
</style>
