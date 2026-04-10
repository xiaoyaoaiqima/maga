<script lang="ts" setup>
import type { EchartsUIType } from '@vben/plugins/echarts';

import type { ContentDetail } from '#/api/core/job-execution';

import { nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { EchartsUI, useEcharts } from '@vben/plugins/echarts';

import * as Antd from 'ant-design-vue';
import * as DayjsLib from 'dayjs';

import {
  getContentStatsApi,
  getContextStatsApi,
  listContentsApi,
} from '#/api/core/content';
import { batchGetKeywordsApi } from '#/api/core/graph-corpus';

const {
  Button,
  Card,
  Descriptions,
  DescriptionsItem,
  Divider,
  Input,
  message,
  Modal,
  Popover,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
} = Antd as any;
const { Option: SelectOption } = Select as any;
const { Search: InputSearch } = Input as any;

const dayjs = ((DayjsLib as any).default ?? (DayjsLib as any)) as any;

const route = useRoute();
const router = useRouter();
const agentCode = route.params.code as string;
const agentName = (route.query.name as string) || agentCode;

type ContextEntry = { display: string; key: string; value?: string };

const nodeNameMap = reactive(new Map<string, string>());

const extractNodeIdsFromString = (value: string): string[] => {
  const matches = [...value.matchAll(/node:(\d+)/g)];
  return matches.map((match) => match[1]).filter(Boolean);
};

const extractNodeIdsFromContext = (
  ctx: ContentDetail['context_list'],
): string[] => {
  if (!ctx) return [];
  const nodeIds: string[] = [];
  if (Array.isArray(ctx)) {
    ctx.forEach((item) => {
      if (item === null || item === undefined) return;
      const text = String(item);
      nodeIds.push(...extractNodeIdsFromString(text));
    });
    return nodeIds;
  }
  if (typeof ctx === 'object') {
    Object.values(ctx).forEach((value) => {
      if (value === null || value === undefined) return;
      if (Array.isArray(value)) {
        value.forEach((item) => {
          if (item === null || item === undefined) return;
          nodeIds.push(...extractNodeIdsFromString(String(item)));
        });
        return;
      }
      nodeIds.push(...extractNodeIdsFromString(String(value)));
    });
    return nodeIds;
  }
  return extractNodeIdsFromString(String(ctx));
};

const replaceNodeTokens = (value: string): string => {
  if (!value.includes('node:')) return value;
  return value.replaceAll(/node:(\d+)/g, (_, nodeId: string) => {
    return nodeNameMap.get(nodeId) || `node:${nodeId}`;
  });
};

const formatContextValue = (value: unknown): string => {
  if (value === null || value === undefined) return '';
  if (Array.isArray(value)) {
    const parts = value
      .map((item) => formatContextValue(item))
      .filter((item) => item.trim() !== '');
    return parts.join(', ');
  }
  return replaceNodeTokens(String(value));
};

const ensureNodeNames = async (nodeIds: string[]) => {
  const uniqueIds = [...new Set(nodeIds)].filter(Boolean);
  const missingIds = uniqueIds.filter((id) => !nodeNameMap.has(id));
  if (missingIds.length === 0) return;
  try {
    const result = await batchGetKeywordsApi({
      node_ids: missingIds,
      include_children: false,
    });
    Object.entries(result || {}).forEach(([id, item]) => {
      if (item?.name) nodeNameMap.set(id, item.name);
    });
  } catch (error) {
    console.warn('获取关键词节点名称失败:', error);
  }
};

const ensureNodeNamesForContents = async (contentList: ContentDetail[]) => {
  const nodeIds = contentList.flatMap((content) =>
    extractNodeIdsFromContext(content.context_list),
  );
  await ensureNodeNames(nodeIds);
};

// Context 变量排序配置
const CONTEXT_SORT_STORAGE_KEY = `context_sort_order_${agentCode}`;
const contextSortOrder = ref<string[]>([]);

// 从 localStorage 加载排序配置
const loadContextSortOrder = () => {
  try {
    const saved = localStorage.getItem(CONTEXT_SORT_STORAGE_KEY);
    if (saved) {
      contextSortOrder.value = JSON.parse(saved);
    }
  } catch (error) {
    console.warn('加载 Context 排序配置失败:', error);
  }
};

// 保存排序配置到 localStorage
const saveContextSortOrder = (order: string[]) => {
  try {
    localStorage.setItem(CONTEXT_SORT_STORAGE_KEY, JSON.stringify(order));
    contextSortOrder.value = order;
  } catch (error) {
    console.warn('保存 Context 排序配置失败:', error);
  }
};

// 生成排序键
const getSortKey = (entry: ContextEntry): string => {
  // 使用 key:value 作为排序键，如果没有 value 则只用 key
  return entry.value ? `${entry.key}:${entry.value}` : entry.key;
};

// 应用排序到 Context 条目
const applyContextSort = (entries: ContextEntry[]): ContextEntry[] => {
  if (contextSortOrder.value.length === 0) return entries;

  const sorted: (ContextEntry | null)[] = [];
  const unsorted: ContextEntry[] = [];
  const sortMap = new Map<string, number>();

  // 构建排序映射
  contextSortOrder.value.forEach((key, index) => {
    sortMap.set(key, index);
  });

  entries.forEach((entry) => {
    const sortKey = getSortKey(entry);
    const index = sortMap.get(sortKey);
    if (index === undefined) {
      unsorted.push(entry);
    } else {
      // 确保数组足够大
      while (sorted.length <= index) {
        sorted.push(null);
      }
      sorted[index] = entry;
    }
  });

  // 合并已排序和未排序的，过滤掉 null
  return [...sorted.filter((e): e is ContextEntry => e !== null), ...unsorted];
};

const getContextEntries = (
  ctx: ContentDetail['context_list'],
): ContextEntry[] => {
  if (!ctx) return [];
  let entries: ContextEntry[] = [];

  if (Array.isArray(ctx)) {
    entries = ctx
      .filter((x) => x !== null && x !== undefined)
      .map((x) => {
        const raw = String(x);
        const formatted = replaceNodeTokens(raw);
        return { key: raw, display: formatted };
      });
  } else if (typeof ctx === 'object') {
    entries = Object.entries(ctx)
      .filter(([k]) => k !== null && k !== undefined && String(k).trim() !== '')
      .map(([k, v]) => {
        const valueText = formatContextValue(v);
        const valueDisplay = valueText.trim();
        return {
          key: String(k),
          value: valueDisplay,
          display:
            valueDisplay === ''
              ? String(k)
              : `${String(k)}: ${valueDisplay.slice(0, 16)}${valueDisplay.length > 16 ? '…' : ''}`,
        };
      });
  } else {
    entries = [{ key: String(ctx), display: replaceNodeTokens(String(ctx)) }];
  }

  // 应用排序
  return applyContextSort(entries);
};

// 状态
const loading = ref(false);

// 文章详情 Modal 相关
const articleDetailVisible = ref(false);
const currentArticle = ref<ContentDetail | null>(null);

// 查看文章详情
const viewArticleDetail = (record: ContentDetail) => {
  currentArticle.value = record;
  articleDetailVisible.value = true;
};

// Content 相关
const contents = ref<ContentDetail[]>([]);
const contentsLoading = ref(false);
const contentValidFilter = ref<number>();
const contentTestFilter = ref<number>();
const contentOnlineFilter = ref<string>();
const contentTitleSearch = ref<string>();
const contentContextKeyFilter = ref<string>();
const contentContextValueFilter = ref<string>();
const contentPagination = ref({ current: 1, pageSize: 20, total: 0 });

// 图表筛选状态
const chartValidFilter = ref<number>();
const chartTestFilter = ref<number>();
const chartOnlineFilter = ref<string>();

// 统计数据（从 API 直接获取，不再基于 allContents 计算）
const stats = ref({
  total: 0,
  valid: 0,
  invalid: 0,
  pending: 0,
  test: 0,
  formal_valid: 0,
  online: 0,
  locked: 0,
  unlocked: 0,
  used: 0,
  unused: 0,
});

// ECharts 相关
const chartRef = ref<EchartsUIType>();
const { renderEcharts } = useEcharts(chartRef);

// Context 变量名列表（从 API 获取）
const contextKeys = ref<string[]>([]);

// Context 分布统计数据（从 API 获取）
const contextStats = ref<Array<{ name: string; value: number }>>([]);

// 获取 Context 变量名列表和分布统计
const fetchContextStats = async () => {
  try {
    const selectedKey = contentContextKeyFilter.value;

    // 构建筛选参数
    const params: any = {
      agent_code: agentCode,
    };

    // 图表筛选条件
    if (chartValidFilter.value !== undefined) {
      // 待确定 - context-stats 接口不支持这个，需要特殊处理
      // 暂时跳过，或者使用 null
      params.is_valid =
        chartValidFilter.value === 2 ? null : chartValidFilter.value;
    }
    if (chartTestFilter.value !== undefined) {
      params.is_test_case = chartTestFilter.value;
    }
    if (chartOnlineFilter.value) {
      // context-stats 接口不支持 online_status 筛选，需要在前端过滤
      // 暂时不传这个参数
    }

    // 如果选择了变量名，获取该变量的分布统计
    if (selectedKey) {
      params.variable_name = selectedKey;
    }

    const res = await getContextStatsApi(params);

    if (res) {
      // 更新变量名列表
      if (res.keys && res.keys.length > 0) {
        contextKeys.value = res.keys;
        // 如果还没有选中变量名，默认选择第一个
        if (!contentContextKeyFilter.value && res.keys.length > 0) {
          contentContextKeyFilter.value = res.keys[0];
        }
      }

      // 更新分布统计
      contextStats.value =
        selectedKey && res.distribution ? res.distribution : [];

      // 更新图表
      updateChart();
    }
  } catch (error) {
    console.error('Failed to fetch context stats:', error);
  }
};

// 初始化默认选中的 Key
watch(contextKeys, (newKeys) => {
  if (newKeys.length > 0 && !contentContextKeyFilter.value) {
    contentContextKeyFilter.value = newKeys[0];
    // 选中后需要重新获取统计
    fetchContextStats();
  }
});

const updateChart = async () => {
  const data = contextStats.value || [];

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
  contentContextValueFilter.value =
    contentContextValueFilter.value === valueName ? undefined : valueName;
};

// 当筛选条件变化时，重新获取统计
watch([chartValidFilter, chartTestFilter, chartOnlineFilter], () => {
  fetchContextStats();
});

// 当选中的变量名变化时，重新获取统计
watch(contentContextKeyFilter, () => {
  fetchContextStats();
});

// 当 contextStats 变化时，更新图表
watch(contextStats, () => {
  updateChart();
});

// 只有 Context Value 变化时才重新获取列表（Key 变化只影响图表）
watch(contentContextValueFilter, () => {
  contentPagination.value.current = 1;
  fetchContents();
});

// Content 列定义
const contentColumns = [
  { title: '标题', key: 'title', width: 250, ellipsis: true },
  { title: '有效性', key: 'is_valid', width: 80 },
  { title: '测试', key: 'is_test_case', width: 80 },
  { title: '上线状态', key: 'online_status', width: 100 },
  { title: 'Context', key: 'context_list', width: 200 },
  { title: '创建时间', key: 'create_time', width: 140 },
  { title: '操作', key: 'action', width: 200, fixed: 'right' as const },
];

// 获取统计数据（使用专门的统计接口，直接返回统计数据）
const fetchStatsData = async () => {
  try {
    // 获取统计数据（使用专门的统计接口，性能更好且数据准确）
    const statsRes = await getContentStatsApi({
      agent_code: agentCode,
    });
    if (statsRes) {
      stats.value = {
        total: statsRes.total || 0,
        valid: statsRes.valid || 0,
        invalid: statsRes.invalid || 0,
        pending: statsRes.pending || 0,
        test: statsRes.test || 0,
        formal_valid: statsRes.formal_valid || 0,
        online: statsRes.online || 0,
        locked: statsRes.locked || 0,
        unlocked: statsRes.unlocked || 0,
        used: statsRes.used || 0,
        unused: statsRes.unused || 0,
      };
    }
  } catch (error) {
    console.error('Failed to fetch stats data:', error);
    // 统计数据加载失败不影响列表展示
  }
};

// 获取全部数据（已优化：分离统计、图表和列表数据）
const fetchData = async () => {
  loading.value = true;
  try {
    // 1. 先获取列表数据（使用正常分页）
    await fetchContents();

    // 2. 并行获取统计数据和图表数据（不影响列表展示）
    fetchStatsData();
    fetchContextStats();
  } catch (error) {
    message.error('获取数据失败');
    console.error('Failed to fetch Agent contents:', error);
  } finally {
    loading.value = false;
  }
};

// 获取 Content 列表
const fetchContents = async () => {
  // 只有当用户明确选择了 Context Value 时，才进行 Context 筛选
  // contentContextKeyFilter 只用于图表显示，不应该触发列表筛选
  if (contentContextValueFilter.value) {
    // Context筛选需要本地筛选，所以需要获取全部数据
    // 但为了性能，我们限制最大获取数量
    const MAX_CONTEXT_FILTER_SIZE = 1000;
    contentsLoading.value = true;
    try {
      // 先获取用于筛选的数据（限制数量以提升性能）
      // 构建请求参数，只传递有值的参数
      const params: any = {
        agent_code: agentCode,
        page: 1,
        page_size: MAX_CONTEXT_FILTER_SIZE,
      };

      if (contentValidFilter.value !== undefined) {
        params.is_valid = contentValidFilter.value;
      }
      if (contentTestFilter.value !== undefined) {
        params.is_test_case = contentTestFilter.value;
      }
      if (contentOnlineFilter.value) {
        params.online_status = contentOnlineFilter.value;
      }
      if (contentTitleSearch.value) {
        params.keyword = contentTitleSearch.value;
      }

      const res = await listContentsApi(params);

      const allFilteredContents = res.items || [];

      // 执行本地Context筛选
      const filtered = allFilteredContents.filter((content) => {
        // Context 筛选：必须同时匹配 Key 和 Value
        if (contentContextKeyFilter.value && contentContextValueFilter.value) {
          const entries = getContextEntries(content.context_list);
          return entries.some((entry) => {
            const keyMatch =
              entry.key?.trim() === contentContextKeyFilter.value;
            const valueMatch =
              (entry.value?.trim() || '(空)') ===
              contentContextValueFilter.value;
            return keyMatch && valueMatch;
          });
        }
        return false;
      });

      // 设置总数（注意：如果数据超过MAX_CONTEXT_FILTER_SIZE，这里可能不准确）
      // 但为了性能，我们使用实际筛选后的数量
      contentPagination.value.total = filtered.length;
      const start =
        (contentPagination.value.current - 1) *
        contentPagination.value.pageSize;
      contents.value = filtered.slice(
        start,
        start + contentPagination.value.pageSize,
      );
      await ensureNodeNamesForContents(contents.value);
    } catch (error) {
      message.error('获取文章列表失败');
      console.error('Failed to fetch contents with context filter:', error);
    } finally {
      contentsLoading.value = false;
    }
    return;
  }

  // 无Context筛选时，使用正常的分页查询
  contentsLoading.value = true;
  try {
    // 构建请求参数，只传递有值的参数
    const params: any = {
      agent_code: agentCode,
      page: contentPagination.value.current,
      page_size: contentPagination.value.pageSize,
    };

    // 只传递有值的筛选条件
    if (contentValidFilter.value !== undefined) {
      params.is_valid = contentValidFilter.value;
    }
    if (contentTestFilter.value !== undefined) {
      params.is_test_case = contentTestFilter.value;
    }
    if (contentOnlineFilter.value) {
      params.online_status = contentOnlineFilter.value;
    }
    if (contentTitleSearch.value) {
      params.keyword = contentTitleSearch.value;
    }

    const res = await listContentsApi(params);
    contents.value = res.items || [];
    // 确保total与items数量一致（修复显示bug）
    contentPagination.value.total = res.total || 0;
    await ensureNodeNamesForContents(contents.value);
  } catch (error) {
    message.error('获取文章列表失败');
    console.error('Failed to fetch contents:', error);
  } finally {
    contentsLoading.value = false;
  }
};

// Content 表格变化
const handleContentTableChange = (pag: any) => {
  contentPagination.value.current = pag.current;
  contentPagination.value.pageSize = pag.pageSize;
  fetchContents();
};

// 格式化时间
const formatDateTime = (dateStr?: string) => {
  if (!dateStr) return '-';
  return dayjs(dateStr).format('YYYY/MM/DD HH:mm:ss');
};

// 跳转到任务执行详情
const goToJobExecution = (jobId: string) => {
  router.push(`/trace/job-execution/${jobId}`);
};

// 返回 Agent 列表
const goBack = () => {
  router.push('/job/agent');
};

// 拖拽排序相关 - 在文章详情 Modal 中拖拽
const contextDetailSortableRef = ref<HTMLElement | null>(null);
let sortableInstance: any = null;
let sortableModule: any = null;

// 动态加载 sortablejs
const loadSortable = async () => {
  if (sortableModule) return sortableModule;
  try {
    const mod = await import('sortablejs');
    sortableModule = mod;
    return mod;
  } catch (error) {
    console.error('Failed to load sortablejs:', error);
    return null;
  }
};

// 初始化文章详情 Modal 中的 Context 拖拽排序
const initContextDetailSortable = async () => {
  if (!contextDetailSortableRef.value || !articleDetailVisible.value) return;

  // 清理旧实例
  if (sortableInstance) {
    sortableInstance.destroy?.();
    sortableInstance = null;
  }

  const SortableLib = await loadSortable();
  if (!SortableLib?.default) return;

  await nextTick();

  try {
    sortableInstance = SortableLib.default.create(
      contextDetailSortableRef.value,
      {
        animation: 150,
        delay: 0,
        delayOnTouchOnly: false,
        forceFallback: true,
        fallbackTolerance: 5,
        handle: '.context-detail-tag',
        onEnd: async (evt: any) => {
          const { oldIndex, newIndex } = evt;
          if (
            oldIndex !== undefined &&
            newIndex !== undefined &&
            oldIndex !== newIndex &&
            currentArticle.value
          ) {
            // 使用已排序的列表（与显示一致）
            const entries = getContextEntries(
              currentArticle.value.context_list,
            );
            const newOrder = [...entries];
            const [moved] = newOrder.splice(oldIndex, 1);
            if (moved) {
              newOrder.splice(newIndex, 0, moved);

              // 更新排序配置：使用新顺序的键
              const sortKeys = newOrder.map((e) => getSortKey(e));

              // 合并到全局配置：保持新顺序，添加未包含的键
              const existingKeys = new Set(sortKeys);
              const newGlobalOrder = [...sortKeys];

              // 添加其他未在本次排序中的键
              contextSortOrder.value.forEach((key) => {
                if (!existingKeys.has(key)) {
                  newGlobalOrder.push(key);
                }
              });

              saveContextSortOrder(newGlobalOrder);
              message.success(
                'Context 排序已更新，已应用到该 Agent 下的所有文章',
              );

              // 强制更新当前 Modal 的显示（虽然已经自动应用，但确保 UI 刷新）
              await nextTick();
            }
          }
        },
      },
    );
  } catch (error) {
    console.warn('Failed to initialize context detail sortable:', error);
  }
};

// 监听 Modal 打开，初始化拖拽
watch(articleDetailVisible, async (visible) => {
  if (visible) {
    await nextTick();
    setTimeout(() => {
      initContextDetailSortable();
    }, 100);
  } else {
    // Modal 关闭时清理
    if (sortableInstance) {
      sortableInstance.destroy?.();
      sortableInstance = null;
    }
  }
});

// 清理
onUnmounted(() => {
  if (sortableInstance) {
    sortableInstance.destroy?.();
    sortableInstance = null;
  }
});

onMounted(() => {
  loadContextSortOrder();
  fetchData();
});
</script>

<template>
  <div class="p-4">
    <!-- 页面头部 -->
    <div class="overview-header mb-5">
      <div class="header-content">
        <div class="header-left">
          <Button type="text" class="back-btn" @click="goBack">
            <span class="back-icon">←</span>
            返回列表
          </Button>
          <div class="title-section">
            <h1 class="page-title">{{ agentName }}</h1>
            <Tag color="processing" class="agent-tag">{{ agentCode }}</Tag>
          </div>
        </div>
        <Button
          type="primary"
          :loading="loading"
          size="large"
          @click="fetchData"
        >
          🔄 刷新
        </Button>
      </div>
    </div>

    <!-- 统计概览区域 -->
    <Spin :spinning="loading">
      <div class="stats-overview mb-5">
        <!-- 主要指标 - 三个大卡片 -->
        <div class="main-stats">
          <!-- 文章总数卡片 -->
          <div class="stat-card-main total-card">
            <div class="stat-card-bg"></div>
            <div class="stat-content">
              <div class="stat-header">
                <span class="stat-icon">📊</span>
                <span class="stat-label">文章总数</span>
              </div>
              <div class="stat-value-main">{{ stats.total }}</div>
              <div class="stat-breakdown">
                <div class="breakdown-item valid">
                  <span class="breakdown-dot"></span>
                  <span class="breakdown-label">有效</span>
                  <span class="breakdown-value">{{ stats.valid }}</span>
                </div>
                <div class="breakdown-item invalid">
                  <span class="breakdown-dot"></span>
                  <span class="breakdown-label">无效</span>
                  <span class="breakdown-value">{{ stats.invalid }}</span>
                </div>
                <div class="breakdown-item pending">
                  <span class="breakdown-dot"></span>
                  <span class="breakdown-label">待定</span>
                  <span class="breakdown-value">{{ stats.pending }}</span>
                </div>
                <div class="breakdown-item test">
                  <span class="breakdown-dot"></span>
                  <span class="breakdown-label">测试</span>
                  <span class="breakdown-value">{{ stats.test }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 有效率卡片 -->
          <div class="stat-card-main rate-card">
            <div class="stat-card-bg"></div>
            <div class="stat-content">
              <div class="stat-header">
                <span class="stat-icon">📈</span>
                <span class="stat-label">有效率</span>
              </div>
              <div class="stat-value-main rate-value">
                {{
                  stats.total > 0
                    ? ((stats.valid / stats.total) * 100).toFixed(1)
                    : 0
                }}
                <span class="rate-suffix">%</span>
              </div>
              <div class="rate-progress">
                <div
                  class="rate-bar"
                  :style="{
                    width: `${stats.total > 0 ? (stats.valid / stats.total) * 100 : 0}%`,
                  }"
                ></div>
              </div>
            </div>
          </div>

          <!-- 正式有效文章卡片 -->
          <div class="stat-card-main formal-card">
            <div class="stat-card-bg"></div>
            <div class="stat-content">
              <div class="stat-header">
                <span class="stat-icon">✨</span>
                <span class="stat-label">正式有效文章</span>
              </div>
              <div class="stat-value-main">
                {{ stats.formal_valid }}
              </div>
              <div class="stat-sub-info">非测试的有效文章</div>
            </div>
          </div>
        </div>

        <!-- 次要指标 - 五个小卡片 -->
        <div class="secondary-stats">
          <div class="stat-card-mini online-card">
            <div class="mini-icon">🚀</div>
            <div class="mini-info">
              <span class="mini-label">上线文章数</span>
              <span class="mini-value online">{{ stats.online }}</span>
            </div>
          </div>
          <div class="stat-card-mini locked-card">
            <div class="mini-icon">🔒</div>
            <div class="mini-info">
              <span class="mini-label">锁定文章数</span>
              <span class="mini-value locked">{{ stats.locked }}</span>
            </div>
          </div>
          <div class="stat-card-mini unlocked-card">
            <div class="mini-icon">🔓</div>
            <div class="mini-info">
              <span class="mini-label">未被锁定文章数</span>
              <span class="mini-value unlocked">{{ stats.unlocked }}</span>
            </div>
          </div>
          <div class="stat-card-mini used-card">
            <div class="mini-icon">✅</div>
            <div class="mini-info">
              <span class="mini-label">被使用文章数</span>
              <span class="mini-value used">{{ stats.used }}</span>
            </div>
          </div>
          <div class="stat-card-mini unused-card">
            <div class="mini-icon">💤</div>
            <div class="mini-info">
              <span class="mini-label">未被使用文章数</span>
              <span class="mini-value unused">{{ stats.unused }}</span>
            </div>
          </div>
        </div>
      </div>
    </Spin>

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
            <Select
              v-model:value="chartOnlineFilter"
              placeholder="上线状态"
              allow-clear
              size="small"
              style="width: 100px"
            >
              <SelectOption value="ONLINE">已上线</SelectOption>
              <SelectOption value="OFFLINE">未上线</SelectOption>
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

    <!-- 文章列表 -->
    <Card :bordered="false">
      <template #title>
        <span>📄 文章列表</span>
      </template>
      <template #extra>
        <Button type="primary" @click="fetchData">🔄 刷新</Button>
      </template>

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
          <Select
            v-model:value="contentOnlineFilter"
            placeholder="上线状态"
            allow-clear
            style="width: 100px"
            @change="fetchContents"
          >
            <SelectOption value="ONLINE">已上线</SelectOption>
            <SelectOption value="OFFLINE">未上线</SelectOption>
          </Select>
          <InputSearch
            v-model:value="contentTitleSearch"
            placeholder="搜索标题..."
            style="width: 200px"
            allow-clear
            @search="fetchContents"
            @change="
              () => {
                contentPagination.current = 1;
              }
            "
          />
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

      <Table
        :columns="contentColumns"
        :data-source="contents"
        :loading="contentsLoading"
        :pagination="contentPagination"
        row-key="content_id"
        size="small"
        @change="handleContentTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'title'">
            <Popover
              v-if="record.content"
              placement="right"
              trigger="hover"
              :overlay-style="{ maxWidth: '500px', maxHeight: '400px' }"
            >
              <template #content>
                <div class="article-content-preview">
                  <div class="mb-2 text-xs font-medium text-gray-500">
                    {{ record.title || '(无标题)' }}
                  </div>
                  <div
                    class="max-h-[350px] overflow-y-auto text-sm leading-relaxed"
                  >
                    <pre class="whitespace-pre-wrap font-sans">{{
                      record.content
                    }}</pre>
                  </div>
                </div>
              </template>
              <span class="content-title cursor-pointer hover:text-primary">
                {{ record.title || '(无标题)' }}
              </span>
            </Popover>
            <span v-else class="content-title">
              {{ record.title || '(无标题)' }}
            </span>
          </template>

          <template v-else-if="column.key === 'is_valid'">
            <Tag v-if="record.is_valid === 1" color="green"> 有效 </Tag>
            <Tag v-else-if="record.is_valid === 0" color="red"> 无效 </Tag>
            <Tag v-else color="default"> 待确定 </Tag>
          </template>

          <template v-else-if="column.key === 'is_test_case'">
            <Tag :color="record.is_test_case === 1 ? 'orange' : 'default'">
              {{ record.is_test_case === 1 ? '是' : '否' }}
            </Tag>
          </template>

          <template v-else-if="column.key === 'online_status'">
            <Tag v-if="record.online_status === 'ONLINE'" color="blue">
              已上线
            </Tag>
            <Tag v-else color="default"> 未上线 </Tag>
          </template>

          <template v-else-if="column.key === 'context_list'">
            <template v-if="getContextEntries(record.context_list).length > 0">
              <div class="context-tags">
                <Tooltip
                  v-for="ctx in getContextEntries(record.context_list).slice(
                    0,
                    3,
                  )"
                  :key="getSortKey(ctx)"
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
                      .map((x) => (x.value ? `${x.key}: ${x.value}` : x.key))
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
                @click="viewArticleDetail(record as ContentDetail)"
              >
                查看文章详情
              </Button>
            </Space>
          </template>
        </template>
      </Table>
    </Card>

    <!-- 文章详情 Modal -->
    <Modal
      v-model:open="articleDetailVisible"
      title="📄 文章详情"
      width="800px"
      :footer="null"
    >
      <div v-if="currentArticle" class="article-detail">
        <!-- 基本信息 -->
        <Descriptions :column="2" bordered size="small" class="mb-4">
          <DescriptionsItem label="标题" :span="2">
            <span class="font-medium">
              {{ currentArticle.title || '(无标题)' }}
            </span>
          </DescriptionsItem>
          <DescriptionsItem label="文章ID">
            {{ currentArticle.content_id || '-' }}
          </DescriptionsItem>
          <DescriptionsItem label="任务ID">
            <a
              v-if="currentArticle.job_id"
              class="text-blue-500 hover:text-blue-600"
              @click="goToJobExecution(currentArticle.job_id)"
            >
              {{ currentArticle.job_id }}
            </a>
            <span v-else class="text-gray-400">-</span>
          </DescriptionsItem>
          <DescriptionsItem label="有效性">
            <Tag v-if="currentArticle.is_valid === 1" color="green"> 有效 </Tag>
            <Tag v-else-if="currentArticle.is_valid === 0" color="red">
              无效
            </Tag>
            <Tag v-else color="default"> 待确定 </Tag>
          </DescriptionsItem>
          <DescriptionsItem label="测试用例">
            <Tag
              :color="currentArticle.is_test_case === 1 ? 'orange' : 'default'"
            >
              {{ currentArticle.is_test_case === 1 ? '是' : '否' }}
            </Tag>
          </DescriptionsItem>
          <DescriptionsItem label="上线状态">
            <Tag v-if="currentArticle.online_status === 'ONLINE'" color="blue">
              已上线
            </Tag>
            <Tag v-else color="default"> 未上线 </Tag>
          </DescriptionsItem>
          <DescriptionsItem label="是否锁定">
            <Tag
              :color="currentArticle.is_locked === 1 ? 'warning' : 'default'"
            >
              {{ currentArticle.is_locked === 1 ? '已锁定' : '未锁定' }}
            </Tag>
          </DescriptionsItem>
          <DescriptionsItem label="创建时间">
            {{ formatDateTime(currentArticle.create_time) }}
          </DescriptionsItem>
          <DescriptionsItem label="更新时间">
            {{ formatDateTime(currentArticle.update_time) }}
          </DescriptionsItem>
        </Descriptions>

        <!-- 文章内容 -->
        <div v-if="currentArticle.content" class="mb-4">
          <div class="mb-2 font-medium text-gray-600">📝 文章内容</div>
          <div class="content-box article-content-box">
            <pre class="whitespace-pre-wrap">{{ currentArticle.content }}</pre>
          </div>
        </div>

        <!-- Context 信息 -->
        <div
          v-if="getContextEntries(currentArticle.context_list).length > 0"
          class="mb-4"
        >
          <div class="mb-2 font-medium text-gray-600">
            🎯 Context 信息
            <span class="ml-2 text-xs text-gray-400"
              >(长按拖拽可调整顺序，将应用到该 Agent 下所有文章)</span
            >
          </div>
          <div ref="contextDetailSortableRef" class="context-detail-tags">
            <Tag
              v-for="ctx in getContextEntries(currentArticle.context_list)"
              :key="getSortKey(ctx)"
              class="context-detail-tag"
              color="blue"
            >
              {{ ctx.display }}
            </Tag>
          </div>
        </div>

        <!-- Prompt -->
        <div v-if="currentArticle.prompt" class="mb-4">
          <div class="mb-2 font-medium text-gray-600">💬 Prompt</div>
          <div class="content-box prompt-box">
            {{ currentArticle.prompt }}
          </div>
        </div>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
/* 响应式适配 */
@media (max-width: 1200px) {
  .main-stats {
    grid-template-columns: 1fr;
  }

  .secondary-stats {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 768px) {
  .secondary-stats {
    grid-template-columns: 1fr;
  }

  .header-content {
    flex-direction: column;
    gap: 16px;
    align-items: flex-start;
  }
}

.overview-header {
  padding: 20px 24px;
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 8%),
    hsl(var(--primary) / 2%)
  );
  border: 1px solid hsl(var(--border) / 50%);
  border-radius: 16px;
}

.header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-left {
  display: flex;
  gap: 16px;
  align-items: center;
}

.back-btn {
  padding: 4px 8px;
  font-size: 14px;
  color: hsl(var(--muted-foreground));
  transition: all 0.2s ease;
}

.back-btn:hover {
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 10%);
}

.back-icon {
  margin-right: 4px;
}

.title-section {
  display: flex;
  gap: 12px;
  align-items: center;
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  background: linear-gradient(
    135deg,
    hsl(var(--foreground)),
    hsl(var(--primary))
  );
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.agent-tag {
  padding: 2px 10px;
  font-size: 12px;
}

/* 统计概览区域 */
.stats-overview {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 主要统计卡片 */
.main-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.stat-card-main {
  position: relative;
  padding: 24px;
  overflow: hidden;
  border: 1px solid hsl(var(--border) / 30%);
  border-radius: 16px;
  transition:
    transform 0.3s ease,
    box-shadow 0.3s ease;
}

.stat-card-main:hover {
  box-shadow: 0 12px 24px -8px hsl(var(--foreground) / 10%);
  transform: translateY(-2px);
}

.stat-card-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  opacity: 0.9;
}

.stat-content {
  position: relative;
  z-index: 1;
}

/* 文章总数卡片 */
.total-card {
  background: linear-gradient(135deg, #1a73e8 0%, #4285f4 50%, #669df6 100%);
}

.total-card .stat-label,
.total-card .stat-value-main,
.total-card .breakdown-label {
  color: #fff;
}

.total-card .breakdown-value {
  font-weight: 600;
  color: rgb(255 255 255 / 95%);
}

/* 有效率卡片 */
.rate-card {
  background: linear-gradient(135deg, #0d9488 0%, #14b8a6 50%, #2dd4bf 100%);
}

.rate-card .stat-label,
.rate-card .stat-value-main {
  color: #fff;
}

/* 正式有效文章卡片 */
.formal-card {
  background: linear-gradient(135deg, #7c3aed 0%, #8b5cf6 50%, #a78bfa 100%);
}

.formal-card .stat-label,
.formal-card .stat-value-main,
.formal-card .stat-sub-info {
  color: #fff;
}

.stat-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}

.stat-icon {
  font-size: 20px;
}

.stat-label {
  font-size: 14px;
  font-weight: 500;
  opacity: 0.9;
}

.stat-value-main {
  margin-bottom: 16px;
  font-size: 42px;
  font-weight: 700;
  line-height: 1.1;
}

.rate-value {
  display: flex;
  gap: 4px;
  align-items: baseline;
}

.rate-suffix {
  font-size: 24px;
  font-weight: 500;
  opacity: 0.8;
}

.rate-progress {
  height: 8px;
  overflow: hidden;
  background: rgb(255 255 255 / 25%);
  border-radius: 4px;
}

.rate-bar {
  height: 100%;
  background: linear-gradient(
    90deg,
    rgb(255 255 255 / 90%),
    rgb(255 255 255 / 70%)
  );
  border-radius: 4px;
  transition: width 0.5s ease;
}

.stat-sub-info {
  font-size: 13px;
  opacity: 0.8;
}

/* 细分数据 */
.stat-breakdown {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
}

.breakdown-item {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 6px 10px;
  background: rgb(255 255 255 / 15%);
  border-radius: 8px;
  backdrop-filter: blur(4px);
}

.breakdown-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.breakdown-item.valid .breakdown-dot {
  background: #4ade80;
  box-shadow: 0 0 8px rgb(74 222 128 / 60%);
}

.breakdown-item.invalid .breakdown-dot {
  background: #f87171;
  box-shadow: 0 0 8px rgb(248 113 113 / 60%);
}

.breakdown-item.pending .breakdown-dot {
  background: #d1d5db;
  box-shadow: 0 0 8px rgb(209 213 219 / 60%);
}

.breakdown-item.test .breakdown-dot {
  background: #fbbf24;
  box-shadow: 0 0 8px rgb(251 191 36 / 60%);
}

.breakdown-label {
  flex: 1;
  font-size: 12px;
}

.breakdown-value {
  font-size: 14px;
}

/* 次要统计卡片 */
.secondary-stats {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
}

.stat-card-mini {
  display: flex;
  gap: 14px;
  align-items: center;
  padding: 16px 20px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border) / 50%);
  border-radius: 12px;
  transition: all 0.2s ease;
}

.stat-card-mini:hover {
  background: hsl(var(--primary) / 2%);
  border-color: hsl(var(--primary) / 30%);
}

.mini-icon {
  font-size: 28px;
  line-height: 1;
}

.mini-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mini-label {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.mini-value {
  font-size: 22px;
  font-weight: 700;
}

.mini-value.online {
  color: #1a73e8;
}

.mini-value.locked {
  color: #f59e0b;
}

.mini-value.unlocked {
  color: #22c55e;
}

.mini-value.used {
  color: #10b981;
}

.mini-value.unused {
  color: #9ca3af;
}

/* 其他样式保持不变 */
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

.article-detail {
  max-height: 70vh;
  overflow-y: auto;
}

.context-detail-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.context-detail-tag {
  cursor: grab;
  user-select: none;
  transition: all 0.2s;
}

.context-detail-tag:hover {
  box-shadow: 0 2px 4px hsl(var(--foreground) / 10%);
  transform: scale(1.05);
}

.context-detail-tag:active {
  cursor: grabbing;
}

.content-box {
  padding: 12px;
  font-size: 14px;
  line-height: 1.6;
  background: hsl(var(--muted) / 30%);
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
}

.prompt-box {
  font-style: italic;
  color: hsl(var(--muted-foreground));
}

.article-content-box {
  max-height: 400px;
  overflow-y: auto;
}

.article-content-box pre {
  margin: 0;
  font-family: inherit;
}

.article-content-preview {
  padding: 4px 0;
}

.article-content-preview pre {
  padding: 0;
  margin: 0;
  font-family: inherit;
  color: hsl(var(--foreground));
  word-wrap: break-word;
  white-space: pre-wrap;
}

/* 页面头部样式 */
</style>
