<script lang="ts" setup>
import type {
  ContentDetail,
  ExpertBusinessResultDetail,
  JobExecutionStats,
  SubJobDetail,
} from '#/api/core/job-execution';

import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import { EchartsUI, useEcharts } from '@vben/plugins/echarts';

import * as Antd from 'ant-design-vue';
import * as DayjsLib from 'dayjs';

import {
  batchUpdateContentOnlineStatusApi,
  updateContentOnlineStatusApi,
} from '#/api/core/content';
import { batchGetKeywordsApi } from '#/api/core/graph-corpus';
import {
  getJobBusinessResultsApi,
  getJobContentsApi,
  getJobExecutionDetailApi,
  getJobSubJobsApi,
} from '#/api/core/job-execution';
import MonacoEditor from '#/components/MonacoEditor.vue';

const {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  message,
  Modal,
  Popconfirm,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tabs,
  Tag,
  Tooltip,
} = Antd as any;
const { Item: DescriptionsItem } = Descriptions as any;
const { Option: SelectOption } = Select as any;
const { TabPane } = Tabs as any;

const dayjs = ((DayjsLib as any).default ?? (DayjsLib as any)) as any;

const route = useRoute();
const jobId = route.params.id as string;

// 节点名称映射缓存
const nodeNameMap = ref<Record<string, string>>({});

type ContextEntry = { display: string; key: string; value?: string };

// 替换 node:id 或纯 UUID 为节点名称
const replaceNodeTokens = (value: string): string => {
  // 处理 node:xxx 格式
  if (value.includes('node:')) {
    return value.replaceAll(/node:([a-zA-Z0-9-]+)/g, (_, nodeId: string) => {
      return nodeNameMap.value[nodeId] || `node:${nodeId}`;
    });
  }
  // 处理纯 UUID 格式（如果存在于 nodeNameMap）
  if (nodeNameMap.value[value]) {
    return nodeNameMap.value[value];
  }
  return value;
};

const getContextEntries = (
  ctx: ContentDetail['context_list'],
): ContextEntry[] => {
  if (!ctx) return [];
  // Debug: 打印接收到的 context_list 数据
  console.warn('🔍 context_list 原始数据:', ctx);
  console.warn(
    '🔍 context_list 类型:',
    typeof ctx,
    Array.isArray(ctx) ? 'Array' : '',
  );
  if (Array.isArray(ctx)) {
    return ctx
      .filter((x) => x !== null && x !== undefined)
      .map((x) => {
        const key = String(x);
        return { key, display: replaceNodeTokens(key) };
      });
  }
  if (typeof ctx === 'object') {
    return Object.entries(ctx)
      .filter(([k]) => k !== null && k !== undefined && String(k).trim() !== '')
      .map(([k, v]) => {
        const valueStr = v === null || v === undefined ? '' : String(v);
        const displayValue = replaceNodeTokens(valueStr);

        return {
          key: String(k),
          value: valueStr,
          display:
            valueStr === '' || displayValue === ''
              ? String(k)
              : `${String(k)}: ${displayValue.slice(0, 16)}${displayValue.length > 16 ? '…' : ''}`,
        };
      });
  }
  return [{ key: String(ctx), display: replaceNodeTokens(String(ctx)) }];
};

// 状态
const loading = ref(false);
const stats = ref<JobExecutionStats | null>(null);
const activeTab = ref('sub_jobs');

// 自动刷新
const autoRefresh = ref(false);
const refreshInterval = ref(5); // 秒
let refreshTimer: null | ReturnType<typeof setInterval> = null;

function startAutoRefresh() {
  stopAutoRefresh();
  if (autoRefresh.value && refreshInterval.value > 0) {
    refreshTimer = setInterval(() => {
      fetchData();
    }, refreshInterval.value * 1000);
  }
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

watch(autoRefresh, (val) => {
  if (val) {
    startAutoRefresh();
  } else {
    stopAutoRefresh();
  }
});

watch(refreshInterval, () => {
  if (autoRefresh.value) {
    startAutoRefresh();
  }
});

// SubJob 相关
const subJobs = ref<SubJobDetail[]>([]);
const subJobsLoading = ref(false);
const subJobStatusFilter = ref<string>();
const subJobValidFilter = ref<number>();
const subJobTestFilter = ref<number>();
const subJobPagination = ref({ current: 1, pageSize: 20, total: 0 });

// Content 相关
const allContents = ref<ContentDetail[]>([]);
const contents = ref<ContentDetail[]>([]);
const contentsLoading = ref(false);
const contentValidFilter = ref<number>(1);
const contentTestFilter = ref<number>();
const contentContextKeyFilter = ref<string>();
const contentContextValueFilter = ref<string>();
const contentPagination = ref({ current: 1, pageSize: 20, total: 0 });

// 多选导出相关
const selectedRowKeys = ref<string[]>([]);
const selectedRows = ref<ContentDetail[]>([]);
const exportLoading = ref(false);

// 图表筛选状态
const chartValidFilter = ref<number>();
const chartTestFilter = ref<number>();

// ECharts 相关
const chartRef = ref<EchartsUIType>();
const { renderEcharts } = useEcharts(chartRef);

// 获取所有可用的 Context 变量名
const contextKeys = computed(() => {
  const keys = new Set<string>();
  allContents.value.forEach((content) => {
    const entries = getContextEntries(content.context_list);
    entries.forEach((entry) => {
      if (entry.key) keys.add(entry.key.trim());
    });
  });
  return [...keys].toSorted();
});

// 初始化默认选中的 Key
watch(contextKeys, (newKeys) => {
  if (newKeys.length > 0 && !contentContextKeyFilter.value) {
    contentContextKeyFilter.value = newKeys[0];
  }
});

// 根据选中的 Key 计算 Value 的分布
const contextStats = computed(() => {
  const selectedKey = contentContextKeyFilter.value;
  if (!selectedKey) return [];

  const statsMap: Record<string, number> = {};

  allContents.value.forEach((content) => {
    // 图表有效性筛选
    if (chartValidFilter.value !== undefined) {
      if (chartValidFilter.value === 2) {
        // 待确定
        if (content.is_valid !== null && content.is_valid !== undefined) return;
      } else if (content.is_valid !== chartValidFilter.value) {
        return;
      }
    }
    // 图表测试筛选
    if (
      chartTestFilter.value !== undefined &&
      content.is_test_case !== chartTestFilter.value
    )
      return;

    const entries = getContextEntries(content.context_list);
    entries.forEach((entry) => {
      if (entry.key?.trim() === selectedKey) {
        const value = entry.value?.trim() || '(空)';
        // 使用 replaceNodeTokens 将 node:id 替换为节点名称
        const displayValue = replaceNodeTokens(value);
        statsMap[displayValue] = (statsMap[displayValue] || 0) + 1;
      }
    });
  });

  return Object.entries(statsMap)
    .map(([name, value]) => ({ name, value }))
    .toSorted((a, b) => b.value - a.value);
});

const updateChart = async () => {
  const data = contextStats.value;

  const instance = await renderEcharts({
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)',
    },
    legend: {
      type: 'scroll',
      orient: 'vertical',
      right: 10,
      top: 20,
      bottom: 20,
      textStyle: {
        color: 'hsl(var(--muted-foreground))',
      },
    },
    series: [
      {
        name: contentContextKeyFilter.value || 'Context 分布',
        type: 'pie',
        radius: ['40%', '70%'],
        center: ['40%', '50%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: 'hsl(var(--card))',
          borderWidth: 2,
        },
        label: {
          show: false,
          position: 'center',
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 16,
            fontWeight: 'bold',
            color: 'hsl(var(--foreground))',
          },
        },
        labelLine: {
          show: false,
        },
        data,
      },
    ],
  });

  // 绑定点击事件
  if (instance) {
    instance.off('click');
    instance.on('click', (params: any) => {
      handleChartClick(params);
    });
  }
};

const handleChartClick = (params: any) => {
  const valueName = params.name;
  if (contentContextValueFilter.value === valueName) {
    contentContextValueFilter.value = undefined;
  } else {
    contentContextValueFilter.value = valueName;
    activeTab.value = 'contents';
  }
};

watch(contextStats, () => {
  updateChart();
});

watch([chartValidFilter, chartTestFilter], () => {
  updateChart();
});

watch([contentContextKeyFilter, contentContextValueFilter], () => {
  contentPagination.value.current = 1;
  fetchContents();
});

// Modal 相关
const subJobDetailVisible = ref(false);
const currentSubJob = ref<null | SubJobDetail>(null);
const subJobExpertResults = ref<ExpertBusinessResultDetail[]>([]); // SubJob 详情弹窗的 Expert 结果
const subJobExpertLoading = ref(false);
const contentDetailVisible = ref(false);
const currentContent = ref<ContentDetail | null>(null);

// Expert 业务结果相关
const expertResultsVisible = ref(false);
const expertResultsLoading = ref(false);
const expertResults = ref<ExpertBusinessResultDetail[]>([]);
const currentContentForExpert = ref<ContentDetail | null>(null);
const monacoEditorRef = ref<any>(null); // MonacoEditor 组件引用

// Expert 详情导航状态
type ExpertNavItem = 'overview' | number; // 'overview' 或 Expert 结果索引
const activeExpertNav = ref<ExpertNavItem>('overview');

// 当前选中的 Expert 结果
const currentExpertResult = computed(() => {
  if (
    activeExpertNav.value === 'overview' ||
    typeof activeExpertNav.value !== 'number'
  ) {
    return null;
  }
  return expertResults.value[activeExpertNav.value] || null;
});

// 导航到指定 Expert
const navigateToExpert = (nav: ExpertNavItem) => {
  activeExpertNav.value = nav;

  // 等待 DOM 更新后，重置 Prompt 窗口和执行结果窗口的滚动位置
  nextTick(() => {
    // 重置 Prompt 窗口滚动位置
    const promptElement = document.querySelector('.result-prompt');
    if (promptElement) {
      promptElement.scrollTop = 0;
    }

    // 重置 MonacoEditor（执行结果窗口）滚动位置
    if (monacoEditorRef.value) {
      const editor = monacoEditorRef.value.getEditor();
      if (editor) {
        // Monaco Editor 滚动到顶部
        editor.setScrollTop(0);
        editor.setScrollLeft(0);
      }
    }
  });
};

// 获取 Expert 状态图标（根据业务结果判断）
const getExpertStatusIcon = (result: ExpertBusinessResultDetail) => {
  // 执行失败 → 感叹号
  if (result.status === 'FAILED') return '⚠️';
  // 执行成功但需要检查业务结果
  if (result.status === 'SUCCESS' && result.business_result) {
    const br = result.business_result;
    // 检查是否业务上不通过（score=0, passed=0, 或有问题片段）
    const hasProblems =
      br.score === 0 ||
      br.passed === 0 ||
      (Array.isArray(br.problem_snippets) && br.problem_snippets.length > 0) ||
      (Array.isArray(br.problem_context_list) &&
        br.problem_context_list.length > 0);
    if (hasProblems) return '❌'; // 审核不通过
    return '✅'; // 审核通过
  }
  if (result.status === 'SUCCESS') return '✅';
  return '⏳'; // 执行中或未知状态
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
    // 检查是否是 CRITIC 类型且有 business_result
    if (!result.business_result) continue;

    const br = result.business_result;
    // 检查是否包含 Critic 问题片段
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
  // 去重并按长度降序排序（先匹配长词）
  return [...new Set(words)].toSorted((a, b) => b.length - a.length);
});

// 获取文章完整内容（从多个来源）
const articleContent = computed<string>(() => {
  // 1. 首先尝试从 currentContentForExpert 获取
  if (currentContentForExpert.value?.content) {
    return currentContentForExpert.value.content;
  }
  // 2. 尝试从 GENERATION expert 的结果中获取 generated_content
  for (const result of expertResults.value) {
    if (result.business_result?.generated_content) {
      return result.business_result.generated_content;
    }
  }
  return '';
});

// 生成高亮后的文章内容 HTML
const highlightedContent = computed<string>(() => {
  const content = articleContent.value;
  if (!content) return '';
  if (allForbiddenWords.value.length === 0) return escapeHtml(content);

  let result = escapeHtml(content);
  for (const word of allForbiddenWords.value) {
    const escapedWord = escapeHtml(word);
    // 使用正则全局替换，忽略大小写
    const regex = new RegExp(escapeRegExp(escapedWord), 'gi');
    result = result.replace(
      regex,
      `<mark class="highlight-forbidden">${escapedWord}</mark>`,
    );
  }
  return result;
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

// SubJob 列定义
const subJobColumns = [
  {
    title: 'SubJob ID',
    dataIndex: 'sub_job_id',
    key: 'sub_job_id',
    width: 180,
    ellipsis: true,
  },
  { title: '状态', key: 'status', width: 100 },
  { title: 'Expert 进度', key: 'expert_progress', width: 150 },
  { title: '文章信息', key: 'content_info', width: 200 },
  { title: '创建时间', key: 'create_time', width: 140 },
  { title: '操作', key: 'action', width: 180, fixed: 'right' as const },
];

// Content 列定义
const contentColumns = [
  { title: '标题', key: 'title', width: 250, ellipsis: true },
  { title: '有效性', key: 'is_valid', width: 80 },
  { title: '上线状态', key: 'online_status', width: 100 },
  { title: '锁定/使用', key: 'lock_use_status', width: 100 },
  { title: '测试', key: 'is_test_case', width: 80 },
  { title: 'SubJob 状态', key: 'sub_job_status', width: 100 },
  { title: 'Context', key: 'context_list', width: 200 },
  { title: '创建时间', key: 'create_time', width: 140 },
  { title: '操作', key: 'action', width: 220, fixed: 'right' as const },
];

const batchOnlineLoading = ref(false);
const singleOnlineLoading = ref<Record<number, boolean>>({});

// 批量上线/下线
const handleBatchOnline = async (status: 'OFFLINE' | 'ONLINE') => {
  const opName = status === 'ONLINE' ? '上线' : '下线';
  const confirmContent =
    status === 'OFFLINE'
      ? `是否确认将该任务下所有"有效且非测试"文章${opName}？\n注意：已锁定或已使用的文章将被跳过。`
      : `是否确认将该任务下所有"有效且非测试"文章${opName}？`;
  Modal.confirm({
    title: `确认${opName}`,
    content: confirmContent,
    onOk: async () => {
      batchOnlineLoading.value = true;
      try {
        const result = await batchUpdateContentOnlineStatusApi({
          job_id: jobId,
          online_status: status,
        });
        // 构建详细的成功消息
        const msgParts = [`成功${opName} ${result.updated_count} 篇文章`];
        if (result.skipped_locked > 0) {
          msgParts.push(`跳过 ${result.skipped_locked} 篇已锁定`);
        }
        if (result.skipped_used > 0) {
          msgParts.push(`跳过 ${result.skipped_used} 篇已使用`);
        }
        message.success(msgParts.join('，'));
        fetchData();
      } catch (error) {
        console.error(`Batch ${status} failed:`, error);
        message.error(`批量${opName}失败`);
      } finally {
        batchOnlineLoading.value = false;
      }
    },
  });
};

// 单篇文章上线/下线
const handleSingleOnline = async (
  record: ContentDetail,
  status: 'OFFLINE' | 'ONLINE',
) => {
  const opName = status === 'ONLINE' ? '上线' : '下线';
  singleOnlineLoading.value[record.id] = true;
  try {
    await updateContentOnlineStatusApi({
      content_id: record.id,
      online_status: status,
    });
    message.success(`${opName}成功`);
    fetchData();
  } catch (error) {
    console.error(`Update online status failed:`, error);
    message.error(`${opName}失败`);
  } finally {
    singleOnlineLoading.value[record.id] = false;
  }
};

// 解析内容列表中的节点名称（支持合并模式下的多个 ID）
const resolveNodeNamesForContents = async (contentList: ContentDetail[]) => {
  if (!contentList || contentList.length === 0) return;

  // 收集所有 context_list 中的节点 ID（支持 node: 前缀和纯 UUID 格式）
  const nodeIds = new Set<string>();
  contentList.forEach((content) => {
    if (content.context_list && typeof content.context_list === 'object') {
      Object.values(content.context_list).forEach((value) => {
        if (typeof value === 'string') {
          // 处理 node:xxx 格式
          if (value.includes('node:')) {
            const matches = [...value.matchAll(/node:([a-zA-Z0-9-]+)/g)];
            matches.forEach((match) => {
              const nodeId = match[1];
              if (nodeId && !nodeNameMap.value[nodeId]) {
                nodeIds.add(nodeId);
              }
            });
          }
          // 处理纯 UUID 格式的节点 ID（至少16位，字母数字组合）
          else if (
            value.length >= 16 &&
            /^[a-z0-9-]+$/i.test(value) &&
            !nodeNameMap.value[value]
          ) {
            nodeIds.add(value);
          }
        }
      });
    }
  });

  console.warn('🔍 需要解析的节点 IDs:', [...nodeIds]);

  if (nodeIds.size > 0) {
    try {
      const result = await batchGetKeywordsApi({
        node_ids: [...nodeIds],
        tenant_code: undefined,
      });
      console.warn('🔍 批量获取节点名称结果:', result);
      Object.entries(result).forEach(([nodeId, nodeInfo]) => {
        nodeNameMap.value[nodeId] = nodeInfo.name;
      });
      console.warn('🔍 nodeNameMap 更新后:', nodeNameMap.value);
    } catch (error) {
      console.error('Failed to resolve node names:', error);
    }
  }
};

// 获取全部数据
const fetchData = async () => {
  loading.value = true;
  try {
    const res = await getJobExecutionDetailApi(jobId, { include_test: true });
    // requestClient 已经提取了 data 字段
    stats.value = res.stats;
    subJobs.value = res.sub_jobs;
    allContents.value = res.contents;
    contents.value = res.contents;
    subJobPagination.value.total = res.sub_jobs.length;
    contentPagination.value.total = res.contents.length;

    // 解析节点名称
    await resolveNodeNamesForContents(res.contents);

    updateChart();
    // 如果有筛选，刷新筛选后的列表
    if (contentContextKeyFilter.value || contentContextValueFilter.value) {
      fetchContents();
    }
  } catch (error) {
    message.error('获取数据失败');
    console.error('Failed to fetch job execution detail:', error);
  } finally {
    loading.value = false;
  }
};

// 获取 SubJob 列表
const fetchSubJobs = async () => {
  subJobsLoading.value = true;
  try {
    const res = await getJobSubJobsApi(jobId, {
      status: subJobStatusFilter.value,
      is_valid: subJobValidFilter.value,
      is_test_case: subJobTestFilter.value,
      skip:
        (subJobPagination.value.current - 1) * subJobPagination.value.pageSize,
      limit: subJobPagination.value.pageSize,
    });
    subJobs.value = res || [];
  } catch {
    message.error('获取 SubJob 列表失败');
  } finally {
    subJobsLoading.value = false;
  }
};

// 获取 Content 列表
const fetchContents = async () => {
  // 如果有 Context 筛选，执行本地筛选
  if (contentContextKeyFilter.value || contentContextValueFilter.value) {
    contentsLoading.value = true;
    try {
      const filtered = allContents.value.filter((content) => {
        // 1. Context 筛选
        let matchesContext = true;
        if (contentContextKeyFilter.value || contentContextValueFilter.value) {
          const entries = getContextEntries(content.context_list);
          matchesContext = entries.some((entry) => {
            const keyMatch =
              !contentContextKeyFilter.value ||
              entry.key?.trim() === contentContextKeyFilter.value;
            const valueMatch =
              !contentContextValueFilter.value ||
              (entry.value?.trim() || '(空)') ===
                contentContextValueFilter.value;
            return keyMatch && valueMatch;
          });
        }

        // 2. 有效性筛选
        let matchesValid = true;
        if (contentValidFilter.value !== undefined) {
          matchesValid =
            contentValidFilter.value === 2
              ? content.is_valid === null || content.is_valid === undefined
              : content.is_valid === contentValidFilter.value;
        }

        // 3. 测试筛选
        const matchesTest =
          contentTestFilter.value === undefined ||
          content.is_test_case === contentTestFilter.value;

        return matchesContext && matchesValid && matchesTest;
      });

      contentPagination.value.total = filtered.length;
      const start =
        (contentPagination.value.current - 1) *
        contentPagination.value.pageSize;
      contents.value = filtered.slice(
        start,
        start + contentPagination.value.pageSize,
      );
    } finally {
      contentsLoading.value = false;
    }
    return;
  }

  contentsLoading.value = true;
  try {
    const res = await getJobContentsApi(jobId, {
      is_valid: contentValidFilter.value,
      is_test_case: contentTestFilter.value,
      skip:
        (contentPagination.value.current - 1) *
        contentPagination.value.pageSize,
      limit: contentPagination.value.pageSize,
    });
    contents.value = res || [];

    // 解析节点名称
    if (res && res.length > 0) {
      await resolveNodeNamesForContents(res);
    }
  } catch {
    message.error('获取文章列表失败');
  } finally {
    contentsLoading.value = false;
  }
};

// Tab 切换
const handleTabChange = (key: number | string) => {
  const tabKey = String(key);
  if (tabKey === 'sub_jobs') {
    fetchSubJobs();
  } else if (tabKey === 'contents') {
    fetchContents();
  }
};

// SubJob 表格变化
const handleSubJobTableChange = (pag: any) => {
  subJobPagination.value.current = pag.current;
  subJobPagination.value.pageSize = pag.pageSize;
  fetchSubJobs();
};

// Content 表格变化
const handleContentTableChange = (pag: any) => {
  contentPagination.value.current = pag.current;
  contentPagination.value.pageSize = pag.pageSize;
  fetchContents();
};

// 查看 SubJob 详情
const viewSubJobDetail = async (record: SubJobDetail) => {
  currentSubJob.value = record;
  subJobDetailVisible.value = true;
  subJobExpertResults.value = [];

  // 如果有 content_id，加载 Expert 业务结果以显示执行状态
  if (record.content_id) {
    subJobExpertLoading.value = true;
    try {
      const res = await getJobBusinessResultsApi(jobId, {
        content_id: record.content_id,
      });
      subJobExpertResults.value = res || [];
    } catch (error) {
      console.error('Failed to fetch expert results for SubJob:', error);
      subJobExpertResults.value = [];
    } finally {
      subJobExpertLoading.value = false;
    }
  }
};

// 获取 SubJob 中某个 Expert 的执行状态图标
const getSubJobExpertStatusIcon = (expertCode: string) => {
  const result = subJobExpertResults.value.find(
    (r) => r.expert_config_code === expertCode,
  );
  if (!result) return '⏳'; // 未执行或加载中

  // 执行失败 → 感叹号
  if (result.status === 'FAILED') return '⚠️';
  // 执行成功但需要检查业务结果
  if (result.status === 'SUCCESS' && result.business_result) {
    const br = result.business_result;
    // 检查是否业务上不通过（score=0, passed=0, 或有问题片段）
    const hasProblems =
      br.score === 0 ||
      br.passed === 0 ||
      (Array.isArray(br.problem_snippets) && br.problem_snippets.length > 0) ||
      (Array.isArray(br.problem_context_list) &&
        br.problem_context_list.length > 0);
    if (hasProblems) return '❌'; // 审核不通过
    return '✅'; // 审核通过
  }
  if (result.status === 'SUCCESS') return '✅';
  return '⏳'; // 执行中或未知状态
};

// 获取 SubJob 中某个 Expert 的标签颜色
const getSubJobExpertTagColor = (expertCode: string) => {
  const result = subJobExpertResults.value.find(
    (r) => r.expert_config_code === expertCode,
  );
  if (!result) return 'default'; // 未执行

  if (result.status === 'FAILED') return 'orange'; // 执行失败
  if (result.status === 'SUCCESS' && result.business_result) {
    const br = result.business_result;
    const hasProblems =
      br.score === 0 ||
      br.passed === 0 ||
      (Array.isArray(br.problem_snippets) && br.problem_snippets.length > 0) ||
      (Array.isArray(br.problem_context_list) &&
        br.problem_context_list.length > 0);
    if (hasProblems) return 'error'; // 业务不通过
    return 'success'; // 业务通过
  }
  if (result.status === 'SUCCESS') return 'success';
  return 'default';
};

// 查看 Content 详情
const viewContentDetail = (record: ContentDetail) => {
  currentContent.value = record;
  contentDetailVisible.value = true;
};

// 查看 Expert 执行详情
const viewExpertResults = async (record: ContentDetail) => {
  currentContentForExpert.value = record;
  expertResultsLoading.value = true;
  expertResultsVisible.value = true;
  activeExpertNav.value = 'overview'; // 重置导航到总览

  try {
    const res = await getJobBusinessResultsApi(jobId, {
      content_id: record.content_id,
    });
    expertResults.value = res || [];
  } catch (error) {
    message.error('获取 Expert 执行详情失败');
    console.error('Failed to fetch expert results:', error);
    expertResults.value = [];
  } finally {
    expertResultsLoading.value = false;
  }
};

// 通过 SubJob 查看 Expert 执行详情
const viewExpertResultsBySubJob = async (record: SubJobDetail) => {
  if (!record.content_id) {
    message.warning('该 SubJob 尚无关联的文章');
    return;
  }

  // 构造一个 ContentDetail 对象用于显示
  currentContentForExpert.value = {
    content_id: record.content_id,
    title: record.content_title || '',
    is_valid: record.content_is_valid ?? null,
  } as ContentDetail;

  expertResultsLoading.value = true;
  expertResultsVisible.value = true;
  activeExpertNav.value = 'overview'; // 重置导航到总览

  try {
    const res = await getJobBusinessResultsApi(jobId, {
      content_id: record.content_id,
    });
    expertResults.value = res || [];
  } catch (error) {
    message.error('获取 Expert 执行详情失败');
    console.error('Failed to fetch expert results:', error);
    expertResults.value = [];
  } finally {
    expertResultsLoading.value = false;
  }
};

// 复制 Job ID
const copyJobId = async () => {
  try {
    await navigator.clipboard.writeText(jobId);
    message.success('Job ID 已复制');
  } catch {
    message.error('复制失败');
  }
};

// 格式化时间
const formatDateTime = (dateStr?: string) => {
  if (!dateStr) return '-';
  return dayjs(dateStr).format('YYYY/MM/DD HH:mm:ss');
};

// 行选择配置
const rowSelection = computed(() => ({
  selectedRowKeys: selectedRowKeys.value,
  onChange: (keys: string[], rows: ContentDetail[]) => {
    selectedRowKeys.value = keys;
    selectedRows.value = rows;
  },
}));

// 导出 CSV
const exportToCsv = () => {
  if (selectedRows.value.length === 0) {
    message.warning('请先选择要导出的文章');
    return;
  }

  exportLoading.value = true;
  try {
    // 构建 CSV 内容
    const headers = ['title', 'content', 'context_list'];
    const rows = selectedRows.value.map((item) => {
      // 处理 context_list
      let contextStr = '';
      if (item.context_list) {
        if (Array.isArray(item.context_list)) {
          contextStr = item.context_list.join('; ');
        } else if (typeof item.context_list === 'object') {
          contextStr = Object.entries(item.context_list)
            .map(([k, v]) => `${k}: ${v ?? ''}`)
            .join('; ');
        } else {
          contextStr = String(item.context_list);
        }
      }

      return [
        escapeCsvField(item.title || ''),
        escapeCsvField(item.content || ''),
        escapeCsvField(contextStr),
      ];
    });

    // 生成 CSV 字符串（添加 BOM 以支持中文）
    const bom = '\uFEFF';
    const csvContent =
      bom + [headers.join(','), ...rows.map((row) => row.join(','))].join('\n');

    // 创建下载
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `articles_export_${dayjs().format('YYYYMMDD_HHmmss')}.csv`;
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);

    message.success(`成功导出 ${selectedRows.value.length} 篇文章`);
  } catch (error) {
    console.error('Export failed:', error);
    message.error('导出失败');
  } finally {
    exportLoading.value = false;
  }
};

// CSV 字段转义（处理逗号、换行、双引号）
const escapeCsvField = (field: string): string => {
  if (!field) return '""';
  // 如果包含逗号、换行或双引号，需要用双引号包裹，并将双引号转义为两个双引号
  if (field.includes(',') || field.includes('\n') || field.includes('"')) {
    return `"${field.replaceAll('"', '""')}"`;
  }
  return `"${field}"`;
};

// 全选当前页
const selectAllCurrentPage = () => {
  const keys = contents.value.map((item) => item.content_id);
  selectedRowKeys.value = keys;
  selectedRows.value = [...contents.value];
};

// 清除选择
const clearSelection = () => {
  selectedRowKeys.value = [];
  selectedRows.value = [];
};

// 获取状态颜色
const getStatusColor = (status?: string) => {
  switch (status) {
    case 'DEPLOYED': {
      return 'green';
    }
    case 'NOT_DEPLOYED': {
      return 'orange';
    }
    case 'PAUSED': {
      return 'gray';
    }
    default: {
      return 'default';
    }
  }
};

// 获取 SubJob 状态颜色
const getSubJobStatusColor = (status: string) => {
  switch (status) {
    case 'COMPLETED': {
      return 'success';
    }
    case 'FAILED': {
      return 'error';
    }
    case 'RUNNING': {
      return 'processing';
    }
    default: {
      return 'default';
    }
  }
};

// 获取进度颜色
const getProgressColor = (percent?: number) => {
  if (!percent) return '#d9d9d9';
  if (percent >= 100) return '#52c41a';
  if (percent >= 50) return '#1890ff';
  return '#faad14';
};

// 获取 Expert 进度百分比
const getExpertProgress = (record: SubJobDetail) => {
  const total = record.expert_list.length;
  const completed = (record.expert_complete_list || []).length;
  return total > 0 ? (completed / total) * 100 : 0;
};

// 检查 Expert 是否完成
const isExpertComplete = (record: SubJobDetail, expertCode: string) => {
  return (record.expert_complete_list || []).includes(expertCode);
};

// 初始化
onMounted(() => {
  fetchData();
});

// 清理
onUnmounted(() => {
  stopAutoRefresh();
});
</script>

<template>
  <div class="p-4">
    <!-- 粘性筛选头部 -->
    <div
      class="sticky top-0 z-10 -mx-4 -mt-4 mb-3 bg-background/90 px-4 pb-4 pt-2 shadow-lg backdrop-blur-md"
      style="border-bottom: 1px solid hsl(var(--border) / 30%)"
    >
      <div class="mb-2 flex items-center justify-between gap-3">
        <Space>
          <router-link to="/job/list">
            <Button type="text" size="small">返回列表</Button>
          </router-link>
          <span>{{ stats?.job_name || jobId }} 执行详情</span>
          <Tag v-if="stats?.status" :color="getStatusColor(stats.status)">
            {{ stats.status }}
          </Tag>
          <Tooltip title="点击复制 Job ID">
            <Tag color="default" class="job-id-tag" @click="copyJobId">
              ID: {{ jobId }}
            </Tag>
          </Tooltip>
        </Space>
        <Space>
          <span class="auto-refresh-label">自动刷新</span>
          <Select
            v-model:value="refreshInterval"
            size="small"
            style="width: 80px"
            :disabled="!autoRefresh"
          >
            <SelectOption :value="3">3秒</SelectOption>
            <SelectOption :value="5">5秒</SelectOption>
            <SelectOption :value="10">10秒</SelectOption>
            <SelectOption :value="30">30秒</SelectOption>
          </Select>
          <Antd.Switch
            v-model:checked="autoRefresh"
            checked-children="开"
            un-checked-children="关"
          />
          <Button type="primary" :loading="loading" @click="fetchData">
            刷新
          </Button>
        </Space>
      </div>
    </div>

    <!-- 统计概览卡片 -->
    <Card :bordered="false" class="mb-4">
      <Spin :spinning="loading">
        <Row :gutter="16" class="stats-row">
          <!-- SubJob 统计 -->
          <Col :span="8" class="stats-col">
            <Card class="stat-card" :bordered="true">
              <Statistic
                title="SubJob 总数"
                :value="stats?.total_sub_jobs || 0"
              >
                <template #suffix>
                  <Space class="stat-details">
                    <Tag color="processing">
                      运行 {{ stats?.running_sub_jobs || 0 }}
                    </Tag>
                    <Tag color="success">
                      完成 {{ stats?.completed_sub_jobs || 0 }}
                    </Tag>
                    <Tag color="error">
                      失败 {{ stats?.failed_sub_jobs || 0 }}
                    </Tag>
                  </Space>
                </template>
              </Statistic>
            </Card>
          </Col>

          <!-- Content 统计 -->
          <Col :span="8" class="stats-col">
            <Card class="stat-card" :bordered="true">
              <Statistic
                title="文章总数"
                :value="stats?.total_contents || 0"
                :value-style="{ color: '#1890ff' }"
              >
                <template #suffix>
                  <Space class="stat-details">
                    <Tag color="green">
                      有效 {{ stats?.valid_contents || 0 }}
                    </Tag>
                    <Tag color="red">
                      无效 {{ stats?.invalid_contents || 0 }}
                    </Tag>
                    <Tag color="default">
                      待定 {{ stats?.pending_contents || 0 }}
                    </Tag>
                    <Tag color="orange">
                      测试 {{ stats?.test_contents || 0 }}
                    </Tag>
                  </Space>
                </template>
              </Statistic>
            </Card>
          </Col>

          <!-- 可用文章完成进度 -->
          <Col :span="8" class="stats-col">
            <Card class="stat-card" :bordered="true">
              <div class="progress-stat">
                <div class="progress-header">
                  <span>可用文章完成进度</span>
                  <span class="progress-value">
                    {{ stats?.valid_contents || 0 }} /
                    {{ stats?.target_article_count || '∞' }}
                  </span>
                </div>
                <Progress
                  :percent="stats?.progress_percentage || 0"
                  :stroke-color="getProgressColor(stats?.progress_percentage)"
                  :show-info="true"
                />
                <div class="time-info">
                  <span v-if="stats?.first_sub_job_time">
                    开始: {{ formatDateTime(stats.first_sub_job_time) }}
                  </span>
                  <span v-if="stats?.last_sub_job_time">
                    最新: {{ formatDateTime(stats.last_sub_job_time) }}
                  </span>
                </div>
              </div>
            </Card>
          </Col>
        </Row>
      </Spin>
    </Card>

    <!-- Context 统计图表 -->
    <div v-if="contextKeys.length > 0" class="mb-4">
      <Card :bordered="false" class="mb-2">
        <div class="flex w-full items-center justify-between">
          <span class="text-base font-medium">🎯 Context 分布统计</span>
          <Space wrap>
            <Select
              v-model:value="chartValidFilter"
              placeholder="有效筛选"
              allow-clear
              size="small"
              style="width: 100px"
            >
              <SelectOption :value="1">有效</SelectOption>
              <SelectOption :value="0">无效</SelectOption>
              <SelectOption :value="2">待确定</SelectOption>
            </Select>
            <Select
              v-model:value="chartTestFilter"
              placeholder="测试筛选"
              allow-clear
              size="small"
              style="width: 100px"
            >
              <SelectOption :value="1">测试</SelectOption>
              <SelectOption :value="0">非测试</SelectOption>
            </Select>
            <Divider type="vertical" />
            <span class="text-sm font-normal text-gray-400">选择变量名:</span>
            <Select
              v-model:value="contentContextKeyFilter"
              style="min-width: 150px"
              size="small"
              placeholder="选择变量名"
            >
              <SelectOption v-for="key in contextKeys" :key="key" :value="key">
                {{ key }}
              </SelectOption>
            </Select>
          </Space>
        </div>
      </Card>
      <Card :bordered="false">
        <div class="h-[300px] w-full">
          <EchartsUI ref="chartRef" />
        </div>
      </Card>
    </div>

    <!-- Tabs: SubJob 列表 / Content 列表 -->
    <Card :bordered="false">
      <Tabs v-model:active-key="activeTab" @change="handleTabChange">
        <template #rightExtra>
          <Button type="primary" @click="fetchData">🔄 刷新</Button>
        </template>
        <!-- SubJob 列表 Tab -->
        <TabPane key="sub_jobs" tab="📦 SubJob 列表">
          <div class="filter-bar">
            <Space>
              <Select
                v-model:value="subJobStatusFilter"
                placeholder="状态筛选"
                allow-clear
                style="width: 120px"
                @change="fetchSubJobs"
              >
                <SelectOption value="RUNNING">运行中</SelectOption>
                <SelectOption value="COMPLETED">已完成</SelectOption>
                <SelectOption value="FAILED">失败</SelectOption>
              </Select>
              <Select
                v-model:value="subJobValidFilter"
                placeholder="有效筛选"
                allow-clear
                style="width: 100px"
                @change="fetchSubJobs"
              >
                <SelectOption :value="1">有效</SelectOption>
                <SelectOption :value="0">无效</SelectOption>
                <SelectOption :value="2">待确定</SelectOption>
              </Select>
              <Select
                v-model:value="subJobTestFilter"
                placeholder="测试筛选"
                allow-clear
                style="width: 100px"
                @change="fetchSubJobs"
              >
                <SelectOption :value="1">测试</SelectOption>
                <SelectOption :value="0">非测试</SelectOption>
              </Select>
            </Space>
          </div>

          <Table
            :columns="subJobColumns"
            :data-source="subJobs"
            :loading="subJobsLoading"
            :pagination="subJobPagination"
            row-key="sub_job_id"
            size="small"
            @change="handleSubJobTableChange"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'status'">
                <Tag :color="getSubJobStatusColor(record.status)">
                  {{ record.status }}
                </Tag>
              </template>

              <template v-else-if="column.key === 'expert_progress'">
                <div
                  class="expert-progress clickable"
                  @click="viewSubJobDetail(record as SubJobDetail)"
                >
                  <span>{{ (record.expert_complete_list || []).length }}</span>
                  <span class="text-gray-400">
                    / {{ record.expert_list.length }}</span
                  >
                  <Progress
                    :percent="getExpertProgress(record as SubJobDetail)"
                    size="small"
                    :show-info="false"
                    style="width: 60px; margin-left: 8px"
                  />
                </div>
              </template>

              <template v-else-if="column.key === 'content_info'">
                <Space direction="vertical" size="small">
                  <span v-if="record.content_title" class="content-title">
                    {{ record.content_title }}
                  </span>
                  <Space>
                    <Tag
                      v-if="record.content_is_valid === 1"
                      color="green"
                      size="small"
                    >
                      有效
                    </Tag>
                    <Tag
                      v-else-if="record.content_is_valid === 0"
                      color="red"
                      size="small"
                    >
                      无效
                    </Tag>
                    <Tag v-else color="default" size="small"> 待确定 </Tag>
                    <Tag
                      v-if="record.content_is_test === 1"
                      color="orange"
                      size="small"
                    >
                      测试
                    </Tag>
                  </Space>
                </Space>
              </template>

              <template v-else-if="column.key === 'create_time'">
                {{ formatDateTime(record.create_time) }}
              </template>

              <template v-else-if="column.key === 'action'">
                <Space>
                  <Button
                    v-if="record.content_id"
                    type="link"
                    size="small"
                    @click="viewExpertResultsBySubJob(record as SubJobDetail)"
                  >
                    Expert详情
                  </Button>
                </Space>
              </template>
            </template>
          </Table>
        </TabPane>

        <!-- Content 列表 Tab -->
        <TabPane key="contents" tab="📄 文章列表">
          <div class="filter-bar">
            <Space wrap>
              <Select
                v-model:value="contentValidFilter"
                placeholder="有效筛选"
                allow-clear
                style="width: 100px"
                @change="fetchContents"
              >
                <SelectOption :value="1">有效</SelectOption>
                <SelectOption :value="0">无效</SelectOption>
                <SelectOption :value="2">待确定</SelectOption>
              </Select>
              <Select
                v-model:value="contentTestFilter"
                placeholder="测试筛选"
                allow-clear
                style="width: 100px"
                @change="fetchContents"
              >
                <SelectOption :value="1">测试</SelectOption>
                <SelectOption :value="0">非测试</SelectOption>
              </Select>
              <Tag
                v-if="contentContextKeyFilter && contentContextValueFilter"
                color="blue"
                closable
                style="margin-left: 8px"
                @close="contentContextValueFilter = undefined"
              >
                Context: {{ contentContextKeyFilter }} =
                {{ contentContextValueFilter }}
              </Tag>
            </Space>
          </div>

          <div
            v-if="activeTab === 'contents'"
            class="mb-3 flex justify-between"
          >
            <Space>
              <span class="text-sm text-gray-400">
                已选 {{ selectedRowKeys.length }} 篇
              </span>
              <Button size="small" @click="selectAllCurrentPage">
                全选当前页
              </Button>
              <Button
                size="small"
                :disabled="selectedRowKeys.length === 0"
                @click="clearSelection"
              >
                清除选择
              </Button>
              <Button
                type="primary"
                :loading="exportLoading"
                :disabled="selectedRowKeys.length === 0"
                @click="exportToCsv"
              >
                📥 导出 CSV ({{ selectedRowKeys.length }})
              </Button>
            </Space>
            <Space>
              <Button
                :loading="batchOnlineLoading"
                type="primary"
                @click="handleBatchOnline('ONLINE')"
              >
                全部上线 (有效且非测试)
              </Button>
              <Popconfirm
                title="确认全部下线？"
                description="此操作将下线所有符合条件的内容，请谨慎操作！"
                ok-text="确认下线"
                cancel-text="取消"
                ok-type="danger"
                :overlay-style="{ minWidth: '280px' }"
                @confirm="handleBatchOnline('OFFLINE')"
              >
                <Button danger :loading="batchOnlineLoading">
                  ⚠️ 全部下线
                </Button>
              </Popconfirm>
            </Space>
          </div>

          <Table
            :columns="contentColumns"
            :data-source="contents"
            :loading="contentsLoading"
            :pagination="contentPagination"
            :row-selection="rowSelection"
            row-key="content_id"
            size="small"
            @change="handleContentTableChange"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'title'">
                <span class="content-title">
                  {{ record.title || '(无标题)' }}
                </span>
              </template>

              <template v-else-if="column.key === 'is_valid'">
                <Tag v-if="record.is_valid === 1" color="green"> 有效 </Tag>
                <Tag v-else-if="record.is_valid === 0" color="red"> 无效 </Tag>
                <Tag v-else color="default"> 待确定 </Tag>
              </template>

              <template v-else-if="column.key === 'online_status'">
                <Tag v-if="record.online_status === 'ONLINE'" color="blue">
                  已上线
                </Tag>
                <Tag v-else color="default"> 未上线 </Tag>
              </template>

              <template v-else-if="column.key === 'lock_use_status'">
                <Space :size="4">
                  <Tooltip
                    v-if="record.is_locked === 1"
                    title="文章已被锁定，无法下线"
                  >
                    <Tag color="warning">🔒 锁定</Tag>
                  </Tooltip>
                  <Tooltip
                    v-if="record.is_used === 1"
                    title="文章已被使用，无法下线"
                  >
                    <Tag color="success">✅ 已用</Tag>
                  </Tooltip>
                  <span
                    v-if="record.is_locked !== 1 && record.is_used !== 1"
                    class="text-gray-400"
                    >-</span
                  >
                </Space>
              </template>

              <template v-else-if="column.key === 'is_test_case'">
                <Tag :color="record.is_test_case === 1 ? 'orange' : 'default'">
                  {{ record.is_test_case === 1 ? '是' : '否' }}
                </Tag>
              </template>

              <template v-else-if="column.key === 'sub_job_status'">
                <Tag
                  v-if="record.sub_job_status"
                  :color="getSubJobStatusColor(record.sub_job_status)"
                >
                  {{ record.sub_job_status }}
                </Tag>
                <span v-else class="text-gray-400">-</span>
              </template>

              <template v-else-if="column.key === 'context_list'">
                <template
                  v-if="getContextEntries(record.context_list).length > 0"
                >
                  <div class="context-tags">
                    <Tooltip
                      v-for="ctx in getContextEntries(
                        record.context_list,
                      ).slice(0, 3)"
                      :key="ctx.key"
                      :title="ctx.value || ctx.key"
                    >
                      <Tag size="small">
                        {{ ctx.display }}
                      </Tag>
                    </Tooltip>
                    <Tooltip
                      v-if="getContextEntries(record.context_list).length > 3"
                      :title="
                        getContextEntries(record.context_list)
                          .slice(3)
                          .map((x) =>
                            x.value ? `${x.key}: ${x.value}` : x.key,
                          )
                          .join('\n')
                      "
                    >
                      <span class="text-gray-400">
                        +{{ getContextEntries(record.context_list).length - 3 }}
                      </span>
                    </Tooltip>
                  </div>
                </template>
                <span v-else class="text-gray-400">-</span>
              </template>

              <template v-else-if="column.key === 'create_time'">
                {{ formatDateTime(record.create_time) }}
              </template>

              <template v-else-if="column.key === 'action'">
                <Space>
                  <Button
                    type="link"
                    size="small"
                    @click="viewContentDetail(record as ContentDetail)"
                  >
                    查看
                  </Button>
                  <Button
                    type="link"
                    size="small"
                    @click="viewExpertResults(record as ContentDetail)"
                  >
                    Expert详情
                  </Button>
                  <Button
                    v-if="record.online_status !== 'ONLINE'"
                    :loading="singleOnlineLoading[record.id]"
                    type="link"
                    size="small"
                    @click="
                      handleSingleOnline(record as ContentDetail, 'ONLINE')
                    "
                  >
                    上线
                  </Button>
                  <Tooltip
                    v-else-if="record.is_locked === 1 || record.is_used === 1"
                    :title="
                      record.is_locked === 1
                        ? '文章已被锁定，无法下线'
                        : '文章已被使用，无法下线'
                    "
                  >
                    <Button type="link" danger size="small" disabled>
                      下线
                    </Button>
                  </Tooltip>
                  <Button
                    v-else
                    :loading="singleOnlineLoading[record.id]"
                    type="link"
                    danger
                    size="small"
                    @click="
                      handleSingleOnline(record as ContentDetail, 'OFFLINE')
                    "
                  >
                    下线
                  </Button>
                </Space>
              </template>
            </template>
          </Table>
        </TabPane>
      </Tabs>
    </Card>

    <!-- SubJob 详情 Modal -->
    <Modal
      v-model:open="subJobDetailVisible"
      title="SubJob 详情"
      width="700px"
      :footer="null"
    >
      <Descriptions v-if="currentSubJob" :column="2" bordered size="small">
        <DescriptionsItem label="SubJob ID" :span="2">
          {{ currentSubJob.sub_job_id }}
        </DescriptionsItem>
        <DescriptionsItem label="Content ID" :span="2">
          {{ currentSubJob.content_id }}
        </DescriptionsItem>
        <DescriptionsItem label="状态">
          <Tag :color="getSubJobStatusColor(currentSubJob.status)">
            {{ currentSubJob.status }}
          </Tag>
        </DescriptionsItem>
        <DescriptionsItem label="创建时间">
          {{ formatDateTime(currentSubJob.create_time) }}
        </DescriptionsItem>
        <DescriptionsItem label="Expert 列表" :span="2">
          <Spin :spinning="subJobExpertLoading" size="small">
            <div class="expert-list-detail">
              <div
                v-for="(expert, idx) in currentSubJob.expert_list"
                :key="expert"
                class="expert-item"
              >
                <Tag :color="getSubJobExpertTagColor(expert)">
                  {{ idx + 1 }}. {{ expert }}
                  <span v-if="isExpertComplete(currentSubJob, expert)">
                    {{ getSubJobExpertStatusIcon(expert) }}
                  </span>
                </Tag>
              </div>
            </div>
          </Spin>
        </DescriptionsItem>
        <DescriptionsItem
          v-if="currentSubJob.error_message"
          label="错误信息"
          :span="2"
        >
          <Alert type="error" :message="currentSubJob.error_message" />
        </DescriptionsItem>
      </Descriptions>
    </Modal>

    <!-- Content 详情 Modal -->
    <Modal
      v-model:open="contentDetailVisible"
      title="文章详情"
      width="800px"
      :footer="null"
    >
      <Descriptions v-if="currentContent" :column="2" bordered size="small">
        <DescriptionsItem label="Content ID" :span="2">
          {{ currentContent.content_id }}
        </DescriptionsItem>
        <DescriptionsItem label="标题" :span="2">
          {{ currentContent.title || '(无标题)' }}
        </DescriptionsItem>
        <DescriptionsItem label="有效性">
          <Tag v-if="currentContent.is_valid === 1" color="green"> 有效 </Tag>
          <Tag v-else-if="currentContent.is_valid === 0" color="red">
            无效
          </Tag>
          <Tag v-else color="default"> 待确定 </Tag>
        </DescriptionsItem>
        <DescriptionsItem label="是否测试">
          <Tag
            :color="currentContent.is_test_case === 1 ? 'orange' : 'default'"
          >
            {{ currentContent.is_test_case === 1 ? '测试' : '正式' }}
          </Tag>
        </DescriptionsItem>
        <DescriptionsItem label="创建时间" :span="2">
          {{ formatDateTime(currentContent.create_time) }}
        </DescriptionsItem>
        <DescriptionsItem
          v-if="getContextEntries(currentContent.context_list).length > 0"
          label="Context 列表"
          :span="2"
        >
          <Space wrap>
            <Tooltip
              v-for="ctx in getContextEntries(currentContent.context_list)"
              :key="ctx.key"
              :title="ctx.value || ctx.key"
            >
              <Tag>{{ ctx.display }}</Tag>
            </Tooltip>
          </Space>
        </DescriptionsItem>
      </Descriptions>

      <Divider>正文内容</Divider>
      <div class="content-body">
        {{ currentContent?.content || '(无内容)' }}
      </div>

      <Divider v-if="currentContent?.prompt">Prompt</Divider>
      <div v-if="currentContent?.prompt" class="prompt-body">
        {{ currentContent.prompt }}
      </div>
    </Modal>

    <!-- Expert 执行详情 Modal - 飞书文档式左右布局 -->
    <Modal
      v-model:open="expertResultsVisible"
      title="Expert 执行详情"
      width="1200px"
      :footer="null"
      class="expert-detail-modal"
    >
      <Spin :spinning="expertResultsLoading">
        <div class="expert-detail-layout">
          <!-- 左侧导航目录 -->
          <div class="expert-nav-sidebar">
            <div class="nav-header">
              <span class="nav-title">目录</span>
            </div>
            <div class="nav-list">
              <!-- 总览 -->
              <div
                class="nav-item"
                :class="{ active: activeExpertNav === 'overview' }"
                @click="navigateToExpert('overview')"
              >
                <span class="nav-icon">📋</span>
                <span class="nav-text">总览</span>
              </div>

              <!-- Expert 列表 -->
              <div v-if="expertResults.length > 0" class="nav-section">
                <div class="nav-section-title">Expert 执行记录</div>
                <div
                  v-for="(result, idx) in expertResults"
                  :key="result.id"
                  class="nav-item"
                  :class="{ active: activeExpertNav === idx }"
                  @click="navigateToExpert(idx)"
                >
                  <span class="nav-icon">{{
                    getExpertStatusIcon(result)
                  }}</span>
                  <span class="nav-text nav-expert-text">{{
                    result.expert_config_name || result.expert_config_code
                  }}</span>
                </div>
              </div>

              <!-- 无执行记录 -->
              <div v-else class="nav-empty">暂无 Expert 执行记录</div>
            </div>
          </div>

          <!-- 右侧详情内容 -->
          <div class="expert-detail-content">
            <!-- 总览视图 -->
            <div v-if="activeExpertNav === 'overview'" class="overview-content">
              <div v-if="currentContentForExpert" class="expert-result-header">
                <!-- 基本信息 -->
                <Descriptions
                  :column="1"
                  size="small"
                  bordered
                  :label-style="{ width: '120px', whiteSpace: 'nowrap' }"
                  :content-style="{ minWidth: 0 }"
                >
                  <DescriptionsItem label="文章标题">
                    {{ currentContentForExpert.title || '(无标题)' }}
                  </DescriptionsItem>
                  <!-- 文章详情（违禁词高亮）- 放在标题下面 -->
                  <DescriptionsItem v-if="articleContent" label="文章详情">
                    <!-- eslint-disable vue/no-v-html -->
                    <div
                      class="content-with-highlight"
                      v-html="highlightedContent"
                    ></div>
                    <!-- eslint-enable vue/no-v-html -->
                  </DescriptionsItem>
                </Descriptions>

                <!-- Content ID 和有效性单独一行，使用两列布局 -->
                <Descriptions
                  :column="2"
                  size="small"
                  bordered
                  class="mt-3"
                  :label-style="{ width: '100px', whiteSpace: 'nowrap' }"
                >
                  <DescriptionsItem label="Content ID">
                    <span class="content-id-text">{{
                      currentContentForExpert.content_id
                    }}</span>
                  </DescriptionsItem>
                  <DescriptionsItem label="有效性">
                    <Tag
                      v-if="currentContentForExpert.is_valid === 1"
                      color="green"
                    >
                      有效
                    </Tag>
                    <Tag
                      v-else-if="currentContentForExpert.is_valid === 0"
                      color="red"
                    >
                      无效
                    </Tag>
                    <Tag v-else color="default"> 待确定 </Tag>
                  </DescriptionsItem>
                </Descriptions>

                <!-- CRITIC 违禁词检测结果 -->
                <Descriptions
                  v-if="criticInfoList.length > 0"
                  :column="1"
                  size="small"
                  bordered
                  class="mt-3"
                  :label-style="{ width: '160px', whiteSpace: 'nowrap' }"
                >
                  <template v-for="(info, idx) in criticInfoList" :key="idx">
                    <DescriptionsItem :label="`Reason (${info.expertCode})`">
                      <span class="critic-reason">{{
                        info.reason || '-'
                      }}</span>
                    </DescriptionsItem>
                    <DescriptionsItem :label="`违禁词 (${info.expertCode})`">
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
                    </DescriptionsItem>
                  </template>
                </Descriptions>
              </div>

              <!-- Expert 执行记录汇总 -->
              <Divider>
                Expert 执行记录汇总 ({{ expertResults.length }})
              </Divider>

              <div v-if="expertResults.length === 0" class="empty-results">
                暂无 Expert 执行记录
              </div>

              <div v-else class="expert-summary-list">
                <div
                  v-for="(result, idx) in expertResults"
                  :key="result.id"
                  class="expert-summary-item"
                  @click="navigateToExpert(idx)"
                >
                  <div class="summary-left">
                    <span class="summary-icon">{{
                      getExpertStatusIcon(result)
                    }}</span>
                    <span class="summary-code">{{
                      result.expert_config_code
                    }}</span>
                    <span v-if="result.expert_config_name" class="summary-name">
                      {{ result.expert_config_name }}
                    </span>
                  </div>
                  <div class="summary-right">
                    <Tag v-if="result.model_code" color="cyan" size="small">
                      {{ result.model_code }}
                    </Tag>
                    <Tag
                      v-if="result.business_type"
                      color="purple"
                      size="small"
                    >
                      {{ result.business_type }}
                    </Tag>
                    <span class="summary-time">{{
                      formatDateTime(result.create_time)
                    }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Expert 详情视图 -->
            <div v-else-if="currentExpertResult" class="expert-result-content">
              <Card size="small" class="expert-result-card">
                <template #title>
                  <Space>
                    <Tag color="blue">
                      {{ currentExpertResult.expert_config_code }}
                    </Tag>
                    <Tag v-if="currentExpertResult.model_code" color="cyan">
                      {{ currentExpertResult.model_code }}
                    </Tag>
                    <span
                      v-if="currentExpertResult.expert_config_name"
                      class="expert-name"
                    >
                      {{ currentExpertResult.expert_config_name }}
                    </span>
                    <Tag
                      v-if="currentExpertResult.business_type"
                      color="purple"
                    >
                      {{ currentExpertResult.business_type }}
                    </Tag>
                    <Tag
                      v-if="currentExpertResult.status"
                      :color="
                        currentExpertResult.status === 'SUCCESS'
                          ? 'green'
                          : 'red'
                      "
                    >
                      {{ currentExpertResult.status }}
                    </Tag>
                  </Space>
                </template>
                <template #extra>
                  <span class="result-time">{{
                    formatDateTime(currentExpertResult.create_time)
                  }}</span>
                </template>

                <Descriptions :column="1" size="small" bordered>
                  <DescriptionsItem
                    v-if="currentExpertResult.error_message"
                    label="错误信息"
                  >
                    <Alert
                      type="error"
                      :message="currentExpertResult.error_message"
                      show-icon
                    />
                  </DescriptionsItem>
                  <DescriptionsItem
                    v-if="currentExpertResult.business_result"
                    label="执行结果"
                  >
                    <div class="result-json">
                      <MonacoEditor
                        ref="monacoEditorRef"
                        :model-value="
                          JSON.stringify(
                            currentExpertResult.business_result,
                            null,
                            2,
                          )
                        "
                        language="json"
                        readonly
                        :line-numbers="false"
                        height="300px"
                        :minimap="false"
                      />
                    </div>
                  </DescriptionsItem>
                  <DescriptionsItem
                    v-if="currentExpertResult.prompt"
                    label="使用的 Prompt"
                  >
                    <div class="result-prompt">
                      {{ currentExpertResult.prompt }}
                    </div>
                  </DescriptionsItem>
                </Descriptions>
              </Card>

              <!-- 快速导航按钮 -->
              <div class="expert-nav-buttons">
                <Button
                  v-if="
                    typeof activeExpertNav === 'number' && activeExpertNav > 0
                  "
                  @click="navigateToExpert(activeExpertNav - 1)"
                >
                  ← 上一个
                </Button>
                <Button type="link" @click="navigateToExpert('overview')">
                  返回总览
                </Button>
                <Button
                  v-if="
                    typeof activeExpertNav === 'number' &&
                    activeExpertNav < expertResults.length - 1
                  "
                  @click="navigateToExpert(activeExpertNav + 1)"
                >
                  下一个 →
                </Button>
              </div>
            </div>
          </div>
        </div>
      </Spin>
    </Modal>
  </div>
</template>

<style scoped>
.stats-row {
  display: flex;
  flex-wrap: wrap;
}

.stats-col {
  display: flex;
}

.stat-card {
  flex: 1;
  width: 100%;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border)) !important;
  border-radius: 8px;
}

.stat-card :deep(.ant-card) {
  border: 1px solid hsl(var(--border)) !important;
}

.stat-card :deep(.ant-card-body) {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-height: 120px;
}

.stat-details {
  display: block;
  margin-top: 8px;
}

.progress-stat {
  display: flex;
  flex-direction: column;
  justify-content: center;
  height: 100%;
  padding: 0;
}

.progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-size: 14px;
  color: hsl(var(--muted-foreground));
}

.progress-value {
  font-size: 20px;
  font-weight: 600;
  color: hsl(var(--primary));
}

.time-info {
  display: flex;
  justify-content: space-between;
  margin-top: 12px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.filter-bar {
  margin-bottom: 16px;
}

.content-title {
  font-weight: 500;
}

.text-gray-400 {
  color: #9ca3af;
}

.context-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.expert-progress {
  display: flex;
  align-items: center;
}

.expert-progress.clickable {
  cursor: pointer;
  transition: opacity 0.2s;
}

.expert-progress.clickable:hover {
  opacity: 0.7;
}

.expert-list-detail {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.expert-item {
  margin-bottom: 4px;
}

.content-body {
  max-height: 300px;
  padding: 16px;
  overflow-y: auto;
  line-height: 1.8;
  white-space: pre-wrap;
  background: hsl(var(--muted));
  border-radius: 8px;
}

.prompt-body {
  max-height: 200px;
  padding: 16px;
  overflow-y: auto;
  font-size: 13px;
  white-space: pre-wrap;
  background: hsl(var(--muted));
  border-radius: 8px;
}

.expert-result-header {
  margin-bottom: 16px;
}

.content-id-text {
  font-family: Monaco, Menlo, 'Ubuntu Mono', monospace;
  font-size: 13px;
  word-break: break-all;
}

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

.content-with-highlight {
  max-height: 300px;
  padding: 12px;
  overflow-y: auto;
  line-height: 1.8;
  word-break: break-all;
  white-space: pre-wrap;
  background: hsl(var(--muted));
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

.empty-results {
  padding: 32px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.expert-results-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 500px;
  overflow-y: auto;
}

.expert-result-card {
  background: hsl(var(--card));
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
  max-height: 250px;
  overflow: hidden;
  border-radius: 6px;
}

.result-json :deep(.monaco-editor-container) {
  border: none;
}

.result-prompt {
  max-height: 150px;
  padding: 12px;
  overflow-y: auto;
  font-size: 12px;
  white-space: pre-wrap;
  background: hsl(var(--muted));
  border-radius: 6px;
}

.auto-refresh-label {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.job-id-tag {
  font-family: Monaco, Menlo, 'Ubuntu Mono', monospace;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.job-id-tag:hover {
  color: hsl(var(--primary));
  border-color: hsl(var(--primary));
}

/* Expert 详情 Modal - 飞书文档式左右布局 */
.expert-detail-layout {
  display: flex;
  gap: 0;
  min-height: 500px;
  max-height: 70vh;
}

.expert-nav-sidebar {
  flex-shrink: 0;
  width: 220px;
  overflow-y: auto;
  background: hsl(var(--muted) / 50%);
  border-right: 1px solid hsl(var(--border));
  border-radius: 8px 0 0 8px;
}

.nav-header {
  position: sticky;
  top: 0;
  z-index: 10;
  padding: 12px 16px;
  background: hsl(var(--muted));
  border-bottom: 1px solid hsl(var(--border));
}

.nav-title {
  font-size: 13px;
  font-weight: 600;
  color: hsl(var(--muted-foreground));
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.nav-list {
  padding: 8px 0;
}

.nav-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 10px 16px;
  margin: 2px 8px;
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.2s ease;
}

.nav-item:hover {
  background: hsl(var(--primary) / 10%);
}

.nav-item.active {
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 15%);
  border-left: 3px solid hsl(var(--primary));
}

.nav-icon {
  flex-shrink: 0;
  font-size: 14px;
}

.nav-text {
  font-size: 14px;
  font-weight: 500;
}

.nav-section {
  margin-top: 8px;
}

.nav-section-title {
  padding: 8px 16px 4px;
  font-size: 11px;
  font-weight: 600;
  color: hsl(var(--muted-foreground));
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.nav-expert-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav-empty {
  padding: 24px 16px;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.expert-detail-content {
  flex: 1;
  min-width: 0;
  padding: 16px 20px;
  overflow-y: auto;
}

.overview-content {
  height: 100%;
}

/* Expert 汇总列表 - 扁平化设计 */
.expert-summary-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.expert-summary-item {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  cursor: pointer;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 4px;
  transition: all 0.15s ease;
}

.expert-summary-item:hover {
  background: hsl(var(--primary) / 5%);
  border-color: hsl(var(--primary) / 30%);
}

.summary-left {
  display: flex;
  flex: 1;
  gap: 8px;
  align-items: center;
  min-width: 0;
}

.summary-icon {
  flex-shrink: 0;
  font-size: 12px;
}

.summary-code {
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.summary-name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
}

.summary-right {
  display: flex;
  flex-shrink: 0;
  gap: 6px;
  align-items: center;
}

.summary-time {
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

/* Expert 详情内容 */
.expert-result-content {
  height: 100%;
}

.expert-nav-buttons {
  display: flex;
  gap: 16px;
  justify-content: center;
  padding-top: 16px;
  margin-top: 24px;
  border-top: 1px solid hsl(var(--border));
}
</style>
