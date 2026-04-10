<script setup lang="ts">
import type { VxeGridProps } from '#/adapter/vxe-table';
import type { AgentApi } from '#/api/core/business';
import type { JobSimpleItem } from '#/api/core/job';
import type { RLHFApi } from '#/api/core/rlhf';

import {
  computed,
  nextTick,
  onMounted,
  onUnmounted,
  reactive,
  ref,
  watch,
} from 'vue';
import { useRoute } from 'vue-router';

import { Page, useVbenModal } from '@vben/common-ui';
import { useUserStore } from '@vben/stores';

import {
  AppstoreOutlined,
  BarChartOutlined,
  BulbOutlined,
  CheckCircleOutlined,
  CheckOutlined,
  CloseCircleOutlined,
  CloseOutlined,
  CommentOutlined,
  DeleteOutlined,
  DislikeOutlined,
  DownOutlined,
  EditOutlined,
  ExportOutlined,
  LikeOutlined,
  LockOutlined,
  OrderedListOutlined,
  QuestionCircleOutlined,
  UpOutlined,
} from '@ant-design/icons-vue';
import { useDebounceFn } from '@vueuse/core';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Divider,
  Empty,
  Input,
  message,
  Modal,
  notification,
  Pagination,
  Popover,
  Progress,
  Select,
  Spin,
  Statistic,
  Switch,
  Tag,
  Tooltip,
} from 'ant-design-vue';
import * as XLSX from 'xlsx';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  getAgentSimpleListApi,
  getTenantSimpleListApi,
} from '#/api/core/business';
import { getContentExpertResultsApi } from '#/api/core/content';
import { getJobListApi } from '#/api/core/job';
import {
  batchLockContentsApi,
  batchUnlockContentsApi,
  getIssueTagsApi,
  getRandomRLHFContentsApi,
  getReviewersApi,
  getReviewStatusOptionsApi,
  getRLHFListApi,
  lockContentApi,
  refineContentApi,
  renewLocksApi,
  suggestRLHFTagsApi,
  summarizeRLHFCommentApi,
  unlockAllMyContentsApi,
  unlockContentApi,
  updateContentApi,
  updateReviewStatusApi,
} from '#/api/core/rlhf';
import { getGenerationContextApi } from '#/api/core/trace';
import DiffViewer from '#/components/DiffViewer.vue';
import MonacoEditor from '#/components/MonacoEditor.vue';
import ScoreRadarChart from '#/components/ScoreRadarChart.vue';

import ReviewDetail from './ReviewDetail.vue';

// ========== 差异显示控制 ==========
const showDiffHighlight = ref(true); // 默认开启差异高亮

// ========== 视图模式 ==========
type ViewMode = 'card' | 'table';
const viewMode = ref<ViewMode>('card');

const route = useRoute();
const userStore = useUserStore();

// ========== 搜索表单（默认筛选待审核） ==========
const searchForm = reactive({
  keyword: '',
  review_status: 'PENDING' as string | undefined, // 默认待审核
  tenant_id: undefined as number | undefined, // 租户筛选
  ge_expert_code: undefined as string | undefined, // 按生成专家（Agent）筛选
  job_id: undefined as string | undefined, // 任务筛选
  reviewer_id: undefined as string | undefined, // 审核人筛选
  onlyBanPassed: false, // 只显示合规通过的文章
});

// 状态选项（从后端加载）
const statusOptions = ref<Array<{ label: string; value: string }>>([]);

// 租户选项（从后端加载）
const tenantOptions = ref<Array<{ label: string; value: number }>>([]);

// Agent 筛选选项（从后端加载，包含所有租户下的 Agent）
const expertOptions = ref<Array<{ label: string; value: string }>>([]);
const expertOptionsLoading = ref(false);

// 任务筛选选项（从后端加载，需先选择租户和 Agent）
const jobOptions = ref<Array<{ label: string; value: string }>>([]);
const jobOptionsLoading = ref(false);

// 审核人筛选选项（从后端加载）
const reviewerOptions = ref<Array<{ label: string; value: string }>>([]);
const reviewerOptionsLoading = ref(false);

// 选中 Agent 的完整标签（用于 hover 显示）
const selectedAgentLabel = computed(() => {
  if (!searchForm.ge_expert_code) return '';
  const opt = expertOptions.value.find(
    (o) => o.value === searchForm.ge_expert_code,
  );
  return opt?.label || searchForm.ge_expert_code;
});

// ========== 卡片视图数据 ==========
const cardLoading = ref(false);
const cardList = ref<RLHFApi.RLHFFeedback[]>([]);
const cardPagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0,
});

// ========== 审核动画状态 ==========
interface ReviewedCard {
  id: number;
  status: 'DISLIKED' | 'LIKED';
  removing: boolean;
}
const reviewedCards = ref<Map<number, ReviewedCard>>(new Map());

// ========== 今日审核统计 ==========
const todayStats = reactive({
  total: 0,
  liked: 0,
  disliked: 0,
  pending: 0,
});

// ========== 当前聚焦的卡片索引（用于键盘导航） ==========
const focusedCardIndex = ref(0);

// ========== 评论展开状态 ==========
const expandedAnnotations = ref<Set<number>>(new Set());

function toggleAnnotations(id: number) {
  if (expandedAnnotations.value.has(id)) {
    expandedAnnotations.value.delete(id);
  } else {
    expandedAnnotations.value.add(id);
  }
}

function isAnnotationsExpanded(id: number) {
  return expandedAnnotations.value.has(id);
}

function getAnnotations(item: RLHFApi.RLHFFeedback): any[] {
  return (item as any).annotations || [];
}

// ========== 卡片修改意见 ==========
const cardComments = ref<Map<number, string>>(new Map());

function getCardComment(id: number): string {
  return cardComments.value.get(id) || '';
}

function setCardComment(id: number, value: string) {
  cardComments.value.set(id, value);
}

// ========== 卡片问题标签 ==========
const cardIssueTags = ref<Map<number, string[]>>(new Map());
const allIssueTags = ref<RLHFApi.RLHFIssueTag[]>([]);

function getCardIssueTags(id: number): string[] {
  return cardIssueTags.value.get(id) || [];
}

function setCardIssueTags(id: number, value: string[]) {
  cardIssueTags.value.set(id, value);
}

async function loadAllIssueTags() {
  try {
    allIssueTags.value = await getIssueTagsApi();
  } catch {
    // 静默失败，标签列表为空时仍可手动输入
  }
}

// ========== 原文精修 ==========
interface RefineState {
  editing: boolean;
  title: string;
  content: string;
  saving: boolean;
}

const cardRefineStates = ref<Map<number, RefineState>>(new Map());

function getCardRefineState(id: number): RefineState {
  if (!cardRefineStates.value.has(id)) {
    cardRefineStates.value.set(id, {
      editing: false,
      title: '',
      content: '',
      saving: false,
    });
  }
  return cardRefineStates.value.get(id)!;
}

function isRefineEditing(id: number): boolean {
  return getCardRefineState(id).editing;
}

function handleStartRefine(item: RLHFApi.RLHFFeedback) {
  // 创建新的 Map 实例并更新状态，确保响应式更新
  const newMap = new Map(cardRefineStates.value);
  newMap.set(item.id, {
    editing: true,
    // 预填充当前标题和内容（优先使用精修后的版本）
    title: item.modified_title || item.title || '',
    content: item.modified_content || item.content || '',
    saving: false,
  });
  cardRefineStates.value = newMap;
}

// 取消精修编辑
function handleCancelRefine(id: number) {
  const newMap = new Map(cardRefineStates.value);
  newMap.set(id, {
    editing: false,
    title: '',
    content: '',
    saving: false,
  });
  cardRefineStates.value = newMap;
}

// 防抖保存精修内容到服务器（每次键盘输入后 500ms 自动保存）
const debouncedSaveRefine = useDebounceFn(
  async (itemId: number) => {
    const state = getCardRefineState(itemId);
    if (!state.content.trim()) {
      return; // 内容为空时不保存
    }

    state.saving = true;
    try {
      const result = await refineContentApi(itemId, {
        refined_title: state.title || undefined,
        refined_content: state.content,
      });

      // 更新本地数据
      const idx = cardList.value.findIndex((c) => c.id === itemId);
      if (idx !== -1) {
        cardList.value[idx].modified_title = result.modified_title;
        cardList.value[idx].modified_content = result.modified_content;
      }
    } catch (error: unknown) {
      console.error('精修内容自动保存失败:', error);
      // 静默失败，不打扰用户
    } finally {
      state.saving = false;
    }
  },
  500,
  { maxWait: 2000 },
);

// 处理精修内容输入变化，触发防抖保存
function handleRefineInput(itemId: number) {
  debouncedSaveRefine(itemId);
}

// ========== AI 评价总结弹窗 ==========
interface AISummaryModalState {
  visible: boolean;
  loading: boolean;
  progress: number;
  record: null | RLHFApi.RLHFFeedback;
  reviewStatus: 'DISLIKED' | 'LIKED' | null;
  aiComment: string;
  aiTags: string[];
  error: string;
}

const aiSummaryModal = reactive<AISummaryModalState>({
  visible: false,
  loading: false,
  progress: 0,
  record: null,
  reviewStatus: null,
  aiComment: '',
  aiTags: [],
  error: '',
});

// 进度条动画定时器
let progressTimer: null | ReturnType<typeof setInterval> = null;

function startProgressAnimation() {
  aiSummaryModal.progress = 0;
  progressTimer = setInterval(() => {
    if (aiSummaryModal.progress < 90) {
      // 前90%逐渐变慢
      const increment = Math.max(1, (90 - aiSummaryModal.progress) / 10);
      aiSummaryModal.progress = Math.min(
        90,
        aiSummaryModal.progress + increment,
      );
    }
  }, 200);
}

function stopProgressAnimation() {
  if (progressTimer) {
    clearInterval(progressTimer);
    progressTimer = null;
  }
  aiSummaryModal.progress = 100;
}

async function openAISummaryModal(
  record: RLHFApi.RLHFFeedback,
  status: 'DISLIKED' | 'LIKED',
) {
  // 重置状态
  aiSummaryModal.visible = true;
  aiSummaryModal.loading = true;
  aiSummaryModal.progress = 0;
  aiSummaryModal.record = record;
  aiSummaryModal.reviewStatus = status;
  aiSummaryModal.aiComment = '';
  aiSummaryModal.aiTags = [];
  aiSummaryModal.error = '';

  // 开始进度动画
  startProgressAnimation();

  try {
    // 并行调用 AI 总结意见和标签
    const [commentRes, tagsRes] = await Promise.all([
      summarizeRLHFCommentApi(record.id),
      suggestRLHFTagsApi(record.id, { comment: getCardComment(record.id) }),
    ]);

    // 停止进度动画
    stopProgressAnimation();

    // 填充结果
    aiSummaryModal.aiComment = commentRes.comment || '';
    aiSummaryModal.aiTags = tagsRes.tags || [];
  } catch (error: unknown) {
    stopProgressAnimation();
    aiSummaryModal.error =
      error instanceof Error ? error.message : 'AI 总结失败';
  } finally {
    aiSummaryModal.loading = false;
  }
}

async function handleAISummaryRegenerate() {
  if (!aiSummaryModal.record) return;

  aiSummaryModal.loading = true;
  aiSummaryModal.error = '';
  startProgressAnimation();

  try {
    const [commentRes, tagsRes] = await Promise.all([
      summarizeRLHFCommentApi(aiSummaryModal.record.id),
      suggestRLHFTagsApi(aiSummaryModal.record.id, {
        comment: getCardComment(aiSummaryModal.record.id),
      }),
    ]);

    stopProgressAnimation();
    aiSummaryModal.aiComment = commentRes.comment || '';
    aiSummaryModal.aiTags = tagsRes.tags || [];
  } catch (error: unknown) {
    stopProgressAnimation();
    aiSummaryModal.error =
      error instanceof Error ? error.message : 'AI 总结失败';
  } finally {
    aiSummaryModal.loading = false;
  }
}

function handleAISummaryCancel() {
  stopProgressAnimation();
  aiSummaryModal.visible = false;
  aiSummaryModal.record = null;
  aiSummaryModal.reviewStatus = null;
}

async function handleAISummaryConfirm() {
  if (!aiSummaryModal.record || !aiSummaryModal.reviewStatus) return;

  const record = aiSummaryModal.record;
  const status = aiSummaryModal.reviewStatus;

  // 获取当前状态
  const currentLikeStatus = getLikeStatus(record);
  const wasLiked = currentLikeStatus === 1;
  const wasDisliked = currentLikeStatus === -1;

  // 使用弹窗中编辑后的意见和标签
  const comment = aiSummaryModal.aiComment;
  const issueTags = aiSummaryModal.aiTags;

  // 关闭弹窗
  aiSummaryModal.visible = false;

  try {
    // 0. 检查是否有精修内容需要保存
    const refineState = getCardRefineState(record.id);
    if (refineState.editing && refineState.content.trim()) {
      try {
        const result = await refineContentApi(record.id, {
          refined_title: refineState.title || undefined,
          refined_content: refineState.content,
        });

        // 更新本地数据
        const idx = cardList.value.findIndex((c) => c.id === record.id);
        if (idx !== -1) {
          cardList.value[idx].modified_title = result.modified_title;
          cardList.value[idx].modified_content = result.modified_content;
        }

        // 关闭编辑状态
        refineState.editing = false;
        refineState.title = '';
        refineState.content = '';
      } catch (refineError: unknown) {
        message.warning('精修内容保存失败，但继续提交审核');
        console.error('精修保存失败:', refineError);
      }
    }

    // 1. 调用API（附带修改意见和问题标签）
    await updateReviewStatusApi(record.id, {
      review_status: status,
      comment: comment || undefined,
      issue_tag_names: issueTags.length > 0 ? issueTags : undefined,
    });

    // 2. 更新统计（根据之前的状态调整）
    if (status === 'LIKED') {
      todayStats.liked++;
      if (wasDisliked) {
        todayStats.disliked = Math.max(0, todayStats.disliked - 1);
      } else if (!wasLiked) {
        todayStats.total++;
        todayStats.pending = Math.max(0, todayStats.pending - 1);
      }
    } else {
      todayStats.disliked++;
      if (wasLiked) {
        todayStats.liked = Math.max(0, todayStats.liked - 1);
      } else if (!wasDisliked) {
        todayStats.total++;
        todayStats.pending = Math.max(0, todayStats.pending - 1);
      }
    }

    // 3. 更新本地数据的 like_status
    record.like_status = status === 'LIKED' ? 1 : -1;

    // 4. 同步更新卡片的修改意见和标签（用于显示）
    setCardComment(record.id, comment);
    setCardIssueTags(record.id, issueTags);

    // 5. 显示成功提示
    if (wasLiked && status === 'DISLIKED') {
      message.success('已从喜欢改为不喜欢');
    } else if (wasDisliked && status === 'LIKED') {
      message.success('已从不喜欢改为喜欢');
    } else {
      message.success(status === 'LIKED' ? '已标记为喜欢' : '已标记为不喜欢');
    }

    // 6. 审核完成后自动解锁该文章
    if (lockedCardIds.value.includes(record.id)) {
      try {
        await unlockContentApi(record.id);
        lockedCardIds.value = lockedCardIds.value.filter(
          (id) => id !== record.id,
        );
      } catch {
        // 解锁失败不影响流程
      }
    }

    // 7. 标记卡片为已审核（显示成功状态）
    reviewedCards.value.set(record.id, {
      id: record.id,
      status,
      removing: false,
    });

    // 8. 延迟后开始移除动画
    setTimeout(() => {
      const card = reviewedCards.value.get(record.id);
      if (card) {
        card.removing = true;
        reviewedCards.value.set(record.id, { ...card });
      }
    }, 800);

    // 9. 动画结束后从列表移除
    setTimeout(() => {
      const idx = cardList.value.findIndex((c) => c.id === record.id);
      if (idx !== -1) {
        cardList.value.splice(idx, 1);
        cardPagination.total = Math.max(0, cardPagination.total - 1);

        if (focusedCardIndex.value >= cardList.value.length) {
          focusedCardIndex.value = Math.max(0, cardList.value.length - 1);
        }
      }
      reviewedCards.value.delete(record.id);

      if (cardList.value.length === 0 && cardPagination.total > 0) {
        loadCardData();
      }
    }, 1300);
  } catch (error: unknown) {
    message.error(error instanceof Error ? error.message : '操作失败');
  } finally {
    aiSummaryModal.record = null;
    aiSummaryModal.reviewStatus = null;
  }
}

// ========== 卡片划选评论相关 ==========
interface CardEditorRef {
  getEditor: () =>
    | undefined
    | {
        getDomNode: () => HTMLElement | null;
        getModel: () => null | {
          getValueInRange: (range: {
            endColumn: number;
            endLineNumber: number;
            startColumn: number;
            startLineNumber: number;
          }) => string;
        };
        getScrolledVisiblePosition: (pos: {
          column: number;
          lineNumber: number;
        }) => null | { left: number; top: number };
        getSelection: () => {
          endColumn: number;
          endLineNumber: number;
          isEmpty: () => boolean;
          startColumn: number;
          startLineNumber: number;
        };
      };
  setDecorations: (
    decorations: Array<{
      options: {
        hoverMessage?: { value: string };
        inlineClassName: string;
      };
      range: {
        endColumn: number;
        endLineNumber: number;
        startColumn: number;
        startLineNumber: number;
      };
    }>,
  ) => void;
  clearSelection: () => void;
}

interface CardSelectionState {
  visible: boolean;
  x: number;
  y: number;
  range: null | {
    endColumn: number;
    endLineNumber: number;
    startColumn: number;
    startLineNumber: number;
  };
  text: string;
  comment: string;
  id: null | string;
  cardId: null | number;
  user_name: null | string; // 评论者姓名（编辑已有评论时使用）
}

interface AnnotationItem {
  id: string;
  range: {
    endColumn: number;
    endLineNumber: number;
    startColumn: number;
    startLineNumber: number;
  };
  selected_text: string;
  comment: string;
  user_name: string;
  create_time: string;
}

// 卡片编辑器引用管理
const cardEditorRefs = ref<Map<number, CardEditorRef>>(new Map());

// 卡片划选评论状态
const cardSelectionState = reactive<CardSelectionState>({
  visible: false,
  x: 0,
  y: 0,
  range: null,
  text: '',
  comment: '',
  id: null,
  cardId: null,
  user_name: null,
});

function setCardEditorRef(cardId: number, editorRef: CardEditorRef) {
  cardEditorRefs.value.set(cardId, editorRef);
  // 渲染已有的评论高亮
  nextTick(() => {
    renderCardAnnotations(cardId);
  });
}

/**
 * 计算编辑器高度（根据内容行数自适应）
 * @param content 文章内容
 * @returns 高度字符串（px）
 */
function calcEditorHeight(content: null | string | undefined): string {
  const MIN_HEIGHT = 150; // 最小高度
  const MAX_HEIGHT = 500; // 最大高度（约等于右侧雷达图区域高度）
  const LINE_HEIGHT = 20; // 每行高度
  const PADDING = 24; // 上下 padding

  if (!content) {
    return `${MIN_HEIGHT}px`;
  }

  // 计算行数（按换行符分割 + 考虑自动换行）
  // 中文字符宽度约为英文的 2 倍，编辑器宽度约能显示 35-40 个中文字符
  const lines = content.split('\n');
  let totalLines = 0;
  const charsPerLine = 35; // 中文每行约 35 个字符

  for (const line of lines) {
    // 空行算 1 行，非空行按字符数计算需要几行
    totalLines += line.length === 0 ? 1 : Math.ceil(line.length / charsPerLine);
  }

  const calculatedHeight = totalLines * LINE_HEIGHT + PADDING;
  const finalHeight = Math.min(
    MAX_HEIGHT,
    Math.max(MIN_HEIGHT, calculatedHeight),
  );

  return `${finalHeight}px`;
}

function handleCardEditorMouseUp(cardId: number, e: unknown) {
  const editorRef = cardEditorRefs.value.get(cardId);
  if (!editorRef) return;

  const editor = editorRef.getEditor();
  if (!editor) return;

  const selection = editor.getSelection();
  const model = editor.getModel();
  if (!model) return;

  // 1. 优先处理划选 (Selection is not empty)
  if (selection && !selection.isEmpty()) {
    const selectedText = model.getValueInRange(selection);
    if (!selectedText.trim()) return;

    // 获取位置
    const endPos = {
      lineNumber: selection.endLineNumber,
      column: selection.endColumn,
    };
    const coords = editor.getScrolledVisiblePosition(endPos);
    const editorDom = editor.getDomNode();

    if (coords && editorDom) {
      const rect = editorDom.getBoundingClientRect();
      cardSelectionState.x = rect.left + coords.left;
      cardSelectionState.y = rect.top + coords.top + 20;
      cardSelectionState.range = {
        startLineNumber: selection.startLineNumber,
        startColumn: selection.startColumn,
        endLineNumber: selection.endLineNumber,
        endColumn: selection.endColumn,
      };
      cardSelectionState.text = selectedText;
      cardSelectionState.comment = '';
      cardSelectionState.id = null;
      cardSelectionState.cardId = cardId;
      cardSelectionState.visible = true;
    }
    return;
  }

  // 2. 如果不是划选，检查是否是点击了已有高亮
  const mouseEvent = e as {
    target?: { position?: { column: number; lineNumber: number } };
  };
  const pos = mouseEvent.target?.position;
  if (pos) {
    const item = cardList.value.find((c) => c.id === cardId);
    const annotations = getAnnotations(
      item as RLHFApi.RLHFFeedback,
    ) as AnnotationItem[];
    const found = annotations.find((ann: AnnotationItem) => {
      const r = ann.range;
      return (
        pos.lineNumber >= r.startLineNumber &&
        pos.lineNumber <= r.endLineNumber &&
        (pos.lineNumber > r.startLineNumber || pos.column >= r.startColumn) &&
        (pos.lineNumber < r.endLineNumber || pos.column <= r.endColumn)
      );
    });

    if (found) {
      const coords = editor.getScrolledVisiblePosition({
        lineNumber: found.range.endLineNumber,
        column: found.range.endColumn,
      });
      const editorDom = editor.getDomNode();

      if (coords && editorDom) {
        const rect = editorDom.getBoundingClientRect();
        cardSelectionState.id = found.id;
        cardSelectionState.comment = found.comment;
        cardSelectionState.text = found.selected_text;
        cardSelectionState.range = found.range;
        cardSelectionState.user_name = found.user_name || null; // 保存评论者姓名
        cardSelectionState.x = rect.left + coords.left;
        cardSelectionState.y = rect.top + coords.top + 20;
        cardSelectionState.cardId = cardId;
        cardSelectionState.visible = true;
      }
      return;
    }
  }

  // 3. 既不是划选也不是点击高亮，只有在没有正在输入评论时才隐藏
  if (!cardSelectionState.comment.trim()) {
    cardSelectionState.visible = false;
    cardSelectionState.id = null;
    cardSelectionState.user_name = null;
    cardSelectionState.cardId = null;
  }
}

/** 处理标题划选（使用浏览器原生 Selection API） */
function handleTitleMouseUp(cardId: number, event: MouseEvent) {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed) return;

  const selectedText = selection.toString().trim();
  if (!selectedText) return;

  // 获取选区位置
  const range = selection.getRangeAt(0);
  const rect = range.getBoundingClientRect();

  // 使用特殊的 range 标记表示这是标题选区（行号为 0）
  cardSelectionState.range = {
    startLineNumber: 0,
    startColumn: 0,
    endLineNumber: 0,
    endColumn: selectedText.length,
  };
  cardSelectionState.text = selectedText;
  cardSelectionState.comment = '';
  cardSelectionState.id = null;
  cardSelectionState.cardId = cardId;
  cardSelectionState.x = rect.left + rect.width / 2;
  cardSelectionState.y = rect.bottom + 8;
  cardSelectionState.visible = true;

  // 阻止事件冒泡，避免触发卡片聚焦
  event.stopPropagation();
}

function handleCancelCardAnnotation() {
  cardSelectionState.visible = false;
  cardSelectionState.comment = '';
  cardSelectionState.id = null;
  cardSelectionState.user_name = null;
  if (cardSelectionState.cardId) {
    const editorRef = cardEditorRefs.value.get(cardSelectionState.cardId);
    editorRef?.clearSelection();
  }
  cardSelectionState.cardId = null;
}

async function saveCardAnnotation() {
  if (!cardSelectionState.comment.trim() || !cardSelectionState.cardId) {
    cardSelectionState.visible = false;
    return;
  }

  const cardId = cardSelectionState.cardId;
  const item = cardList.value.find((c) => c.id === cardId);
  if (!item) return;

  const currentAnnotations = getAnnotations(item) as AnnotationItem[];
  let newAnnotations: AnnotationItem[];

  if (cardSelectionState.id) {
    // 更新
    newAnnotations = currentAnnotations.map((ann: AnnotationItem) =>
      ann.id === cardSelectionState.id
        ? { ...ann, comment: cardSelectionState.comment }
        : ann,
    );
  } else {
    // 新建 - 使用当前登录用户的真实姓名
    const currentUserName =
      userStore.userInfo?.realName || userStore.userInfo?.username || '匿名';
    const newAnnotation: AnnotationItem = {
      id: crypto.randomUUID(),
      range: { ...cardSelectionState.range! },
      selected_text: cardSelectionState.text,
      comment: cardSelectionState.comment,
      user_name: currentUserName,
      create_time: new Date().toLocaleString(),
    };
    newAnnotations = [...currentAnnotations, newAnnotation];
  }

  try {
    await updateContentApi(cardId, {
      annotations: newAnnotations,
    });
    // 更新本地数据
    (item as unknown as { annotations: AnnotationItem[] }).annotations =
      newAnnotations;
    renderCardAnnotations(cardId);
    const editorRef = cardEditorRefs.value.get(cardId);
    editorRef?.clearSelection();
    message.success('评论已保存');
  } catch {
    message.error('保存评论失败');
  } finally {
    cardSelectionState.visible = false;
    cardSelectionState.comment = '';
    cardSelectionState.id = null;
    cardSelectionState.user_name = null;
    cardSelectionState.cardId = null;
  }
}

async function deleteCardAnnotation() {
  if (!cardSelectionState.id || !cardSelectionState.cardId) return;

  const cardId = cardSelectionState.cardId;
  const item = cardList.value.find((c) => c.id === cardId);
  if (!item) return;

  const currentAnnotations = getAnnotations(item) as AnnotationItem[];
  const newAnnotations = currentAnnotations.filter(
    (ann: AnnotationItem) => ann.id !== cardSelectionState.id,
  );

  try {
    await updateContentApi(cardId, {
      annotations: newAnnotations,
    });
    // 更新本地数据
    (item as unknown as { annotations: AnnotationItem[] }).annotations =
      newAnnotations;
    renderCardAnnotations(cardId);
    const editorRef = cardEditorRefs.value.get(cardId);
    editorRef?.clearSelection();
    message.success('评论已删除');
  } catch {
    message.error('删除评论失败');
  } finally {
    cardSelectionState.visible = false;
    cardSelectionState.comment = '';
    cardSelectionState.id = null;
    cardSelectionState.user_name = null;
    cardSelectionState.cardId = null;
  }
}

function renderCardAnnotations(cardId: number) {
  const editorRef = cardEditorRefs.value.get(cardId);
  if (!editorRef) return;

  const item = cardList.value.find((c) => c.id === cardId);
  if (!item) return;

  const annotations = getAnnotations(item) as AnnotationItem[];
  const decorations = annotations.map((ann: AnnotationItem) => ({
    range: ann.range,
    options: {
      inlineClassName: 'annotation-highlight',
      hoverMessage: { value: `评论: ${ann.comment}\nBy: ${ann.user_name}` },
    },
  }));

  editorRef.setDecorations(decorations);
}

// 审核状态配置（不包含喜欢/不喜欢）
const statusConfig: Record<string, { color: string; label: string }> = {
  PENDING: { label: '待审核', color: '' },
  IN_PROGRESS: { label: '审核中', color: 'orange' },
  COMPLETED: { label: '待抽检', color: '' },
  IN_INSPECTION: { label: '正在抽检', color: 'blue' },
  INSPECTION_PASSED: { label: '抽检通过', color: 'green' },
  INSPECTION_FAILED: { label: '抽检未通过', color: 'red' },
  // 兼容旧状态（如果后端返回）
  LIKED: { label: '已评价', color: 'cyan' },
  DISLIKED: { label: '已评价', color: 'cyan' },
};

function getStatusConfig(status: string) {
  return statusConfig[status] || { label: status, color: '' };
}

// 获取喜欢状态：优先使用 like_status 字段，兼容 review_status
function getLikeStatus(item: RLHFApi.RLHFFeedback): -1 | 0 | 1 {
  // 如果有 like_status 字段，直接使用
  if (item.like_status !== undefined && item.like_status !== 0) {
    return item.like_status;
  }
  // 兼容：如果 review_status 是 LIKED/DISLIKED，推断喜欢状态
  if (item.review_status === ('LIKED' as unknown)) {
    return 1;
  }
  if (item.review_status === ('DISLIKED' as unknown)) {
    return -1;
  }
  return 0;
}

// 判断是否已喜欢
function isLiked(item: RLHFApi.RLHFFeedback): boolean {
  return getLikeStatus(item) === 1;
}

// 判断是否已不喜欢
function isDisliked(item: RLHFApi.RLHFFeedback): boolean {
  return getLikeStatus(item) === -1;
}

async function loadStatusOptions() {
  try {
    statusOptions.value = await getReviewStatusOptionsApi();
  } catch {
    statusOptions.value = [
      { label: '待审核', value: 'PENDING' },
      { label: '审核中', value: 'IN_PROGRESS' },
      { label: '喜欢', value: 'LIKED' },
      { label: '不喜欢', value: 'DISLIKED' },
    ];
  }
}

/** 加载租户列表 */
async function loadTenantOptions() {
  try {
    const tenants = await getTenantSimpleListApi();
    tenantOptions.value = tenants.map((t) => ({
      label: t.tenant_name,
      value: t.id,
    }));
  } catch {
    tenantOptions.value = [];
  }
}

/** 加载 Agent 列表（所有租户） */
async function loadExpertOptions() {
  expertOptionsLoading.value = true;
  try {
    const agents = await getAgentSimpleListApi(); // 不传 tenantId，获取所有租户下的 Agent
    expertOptions.value = agents.map((a: AgentApi.SimpleItem) => ({
      label: `${a.agent_name} (${a.agent_code})`,
      value: a.agent_code,
    }));
  } catch {
    expertOptions.value = [];
  } finally {
    expertOptionsLoading.value = false;
  }
}

/** 加载任务列表（需先选择 Agent） */
async function loadJobOptions(agentCode: string | undefined) {
  jobOptions.value = [];
  if (!agentCode) return;

  jobOptionsLoading.value = true;
  try {
    const jobs = await getJobListApi({
      agent_code: agentCode,
    });
    jobOptions.value = jobs.map((j: JobSimpleItem) => ({
      label: j.job_name,
      value: j.job_id,
    }));
  } catch {
    jobOptions.value = [];
  } finally {
    jobOptionsLoading.value = false;
  }
}

/** 加载审核人列表 */
async function loadReviewerOptions() {
  reviewerOptionsLoading.value = true;
  try {
    reviewerOptions.value = await getReviewersApi();
  } catch {
    reviewerOptions.value = [];
  } finally {
    reviewerOptionsLoading.value = false;
  }
}

/** Agent 变更时的联动逻辑 */
function handleAgentChange(agentCode: string | undefined) {
  // 清空任务选择
  searchForm.job_id = undefined;
  // 重新加载该 Agent 下的任务列表
  loadJobOptions(agentCode);
  // 刷新数据
  refreshData();
}

// ========== 加载今日统计 ==========
async function loadTodayStats() {
  try {
    // 构建基础筛选条件（不包含 review_status，因为需要分别统计各状态）
    const baseFilter: Record<string, unknown> = {
      page: 1,
      page_size: 1,
    };
    // 带入当前的筛选条件（租户、Agent、任务、审核人、仅合规通过等）
    if (searchForm.tenant_id !== undefined) {
      baseFilter.tenant_id = searchForm.tenant_id;
    }
    if (searchForm.ge_expert_code !== undefined) {
      baseFilter.ge_expert_code = searchForm.ge_expert_code;
    }
    if (searchForm.job_id !== undefined) {
      baseFilter.job_id = searchForm.job_id;
    }
    if (searchForm.reviewer_id !== undefined) {
      baseFilter.reviewer_id = searchForm.reviewer_id;
    }
    if (searchForm.onlyBanPassed) {
      baseFilter.only_ban_passed = true;
    }
    if (searchForm.keyword) {
      baseFilter.keyword = searchForm.keyword;
    }

    // 获取各状态数量（简化：通过多次请求或使用专门的统计接口）
    const [pendingRes, likedRes, dislikedRes] = await Promise.all([
      getRLHFListApi({ ...baseFilter, review_status: 'PENDING' }),
      getRLHFListApi({ ...baseFilter, review_status: 'LIKED' }),
      getRLHFListApi({ ...baseFilter, review_status: 'DISLIKED' }),
    ]);
    todayStats.pending = pendingRes.total || 0;
    todayStats.liked = likedRes.total || 0;
    todayStats.disliked = dislikedRes.total || 0;
    todayStats.total = todayStats.liked + todayStats.disliked;
  } catch {
    // 忽略统计加载失败
  }
}

// ========== 卡片视图数据加载 ==========
// 记录当前锁定的文章 ID（用于页面切换时解锁）
const lockedCardIds = ref<number[]>([]);

// 检测筛选条件冲突：选择了审核人 + 待审核状态
const hasFilterConflict = computed(() => {
  if (!searchForm.reviewer_id) return false;
  const pendingStatuses = ['PENDING', 'IN_PROGRESS'];
  return (
    searchForm.review_status !== undefined &&
    pendingStatuses.includes(searchForm.review_status)
  );
});

// 判断当前筛选状态是否需要锁定文章（仅待审核状态需要锁定）
function shouldLockArticles(): boolean {
  // 如果选择了审核人，说明要查看已审核的文章，不需要锁定
  if (searchForm.reviewer_id) {
    return false;
  }
  // 如果未选择状态或选择了待审核/审核中，需要锁定
  const pendingStatuses = ['PENDING', 'IN_PROGRESS'];
  return (
    !searchForm.review_status ||
    pendingStatuses.includes(searchForm.review_status)
  );
}

async function loadCardData() {
  cardLoading.value = true;
  try {
    // 请求时排除其他用户锁定的文章
    // 【方案A】切换页面时，先解锁之前锁定的文章
    if (lockedCardIds.value.length > 0) {
      try {
        await batchUnlockContentsApi(lockedCardIds.value);
        lockedCardIds.value = [];
      } catch {
        // 解锁失败不影响后续操作
      }
    }

    // 请求时排除其他用户锁定的文章（仅在待审核状态下排除）
    const needLock = shouldLockArticles();
    // 构建请求参数（将前端驼峰命名转换为后端蛇形命名）
    const { onlyBanPassed, ...restSearchForm } = searchForm;
    const res = await getRLHFListApi({
      page: cardPagination.current,
      page_size: cardPagination.pageSize,
      exclude_locked: needLock, // 仅在待审核状态下排除其他用户锁定的文章
      only_ban_passed: onlyBanPassed, // 仅显示合规通过的文章（后端筛选）
      ...restSearchForm,
    });
    cardList.value = res.items || [];
    cardPagination.total = res.total || 0;
    // 重置聚焦索引
    focusedCardIndex.value = 0;

    // 初始化卡片的修改意见和问题标签（从 API 返回的数据中读取）
    (res.items || []).forEach((item: RLHFApi.RLHFFeedback) => {
      // 初始化修改意见（improvement_suggestion）
      if (item.improvement_suggestion) {
        setCardComment(item.id, item.improvement_suggestion);
      }

      // 初始化问题标签（issue_tag_ids 转换为标签名）
      if (
        item.issue_tag_ids &&
        Array.isArray(item.issue_tag_ids) &&
        item.issue_tag_ids.length > 0
      ) {
        const tagIdNumbers = new Set(item.issue_tag_ids.map(Number));
        const tagNames = allIssueTags.value
          .filter((tag) => tagIdNumbers.has(tag.id))
          .map((tag) => tag.tag_name);
        if (tagNames.length > 0) {
          setCardIssueTags(item.id, tagNames);
        }
      }
    });

    // 仅在待审核状态下自动批量锁定当前页的文章
    // 查看审核结果（喜欢/不喜欢）时不锁定
    if (needLock) {
      // 获取已经被当前用户锁定的文章（刷新页面后需要恢复锁定状态）
      const alreadyLockedIds = (res.items || [])
        .filter((item: RLHFApi.RLHFFeedback) => item.is_locked === 1)
        .map((item: RLHFApi.RLHFFeedback) => item.id);

      // 筛选出还没有被锁定的文章
      const idsToLock = (res.items || [])
        .filter((item: RLHFApi.RLHFFeedback) => item.is_locked !== 1)
        .map((item: RLHFApi.RLHFFeedback) => item.id);

      if (idsToLock.length > 0) {
        try {
          const lockRes = await batchLockContentsApi(idsToLock);
          // 合并已锁定的和新锁定成功的 ID
          lockedCardIds.value = [
            ...alreadyLockedIds,
            ...(lockRes.success_ids || []),
          ];
          // 如果有自动解锁的文章，显示有时限的浮窗提示
          if (lockRes.auto_unlocked_count && lockRes.auto_unlocked_count > 0) {
            notification.warning({
              message: '锁定数量超限',
              description: `当前锁定文章超过20篇，已自动解锁最早锁定的 ${lockRes.auto_unlocked_count} 篇文章`,
              duration: 5, // 5秒后自动关闭
              placement: 'topRight',
            });
          }
        } catch {
          // 锁定失败不影响页面显示，但仍然恢复已锁定的状态
          lockedCardIds.value = alreadyLockedIds;
        }
      } else {
        // 如果没有新文章需要锁定，恢复已锁定文章的状态
        lockedCardIds.value = alreadyLockedIds;
      }
    }
  } catch (error: unknown) {
    message.error(error instanceof Error ? error.message : '加载失败');
  } finally {
    cardLoading.value = false;
  }
}

function handleCardPageChange(page: number, pageSize: number) {
  cardPagination.current = page;
  cardPagination.pageSize = pageSize;
  loadCardData();
  // 切换页面后滚动到卡片列表顶部
  nextTick(() => {
    const cardView = document.querySelector('.card-view');
    if (cardView) {
      cardView.scrollTo({ top: 0, behavior: 'smooth' });
    }
  });
}

// 切换视图时加载数据
watch(viewMode, async (mode) => {
  // 如果切换到列表视图且不再需要锁定，先解锁之前锁定的文章
  const needLock = shouldLockArticles();
  if (mode === 'table' && !needLock && lockedCardIds.value.length > 0) {
    try {
      await batchUnlockContentsApi(lockedCardIds.value);
      lockedCardIds.value = [];
    } catch {
      // 解锁失败不影响后续操作
    }
  }
  if (mode === 'card') {
    loadCardData();
  }
});

// ========== 键盘快捷键处理 ==========
function handleKeydown(e: KeyboardEvent) {
  // 如果焦点在输入框中，不处理快捷键
  const target = e.target as HTMLElement;
  if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
    return;
  }

  // 只在卡片视图下生效
  if (viewMode.value !== 'card' || cardList.value.length === 0) {
    return;
  }

  const currentCard = cardList.value[focusedCardIndex.value];
  if (!currentCard) return;

  switch (e.key.toLowerCase()) {
    case ' ':
    case 'enter': {
      e.preventDefault();
      openDetail(currentCard);
      break;
    }
    case 'arrowdown':
    case 'j': {
      e.preventDefault();
      if (focusedCardIndex.value < cardList.value.length - 1) {
        focusedCardIndex.value++;
        scrollToFocusedCard();
      }
      break;
    }
    case 'arrowleft':
    case 'd': {
      e.preventDefault();
      handleReviewWithAnimation(currentCard, 'DISLIKED');
      break;
    }
    case 'arrowright':
    case 'l': {
      e.preventDefault();
      handleReviewWithAnimation(currentCard, 'LIKED');
      break;
    }
    case 'arrowup':
    case 'k': {
      e.preventDefault();
      if (focusedCardIndex.value > 0) {
        focusedCardIndex.value--;
        scrollToFocusedCard();
      }
      break;
    }
  }
}

function scrollToFocusedCard() {
  nextTick(() => {
    const card = document.querySelector(
      `.review-card[data-index="${focusedCardIndex.value}"]`,
    );
    card?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });
}

// ========== 心跳续锁机制 ==========
// 每 5 分钟续锁一次，防止锁定过期
const LOCK_HEARTBEAT_INTERVAL = 5 * 60 * 1000; // 5 分钟
let lockHeartbeatTimer: null | ReturnType<typeof setInterval> = null;

async function renewLocks() {
  if (lockedCardIds.value.length === 0) return;

  try {
    const res = await renewLocksApi(lockedCardIds.value);
    if (res.renewed_count < lockedCardIds.value.length) {
      // 部分续锁失败，可能是锁已过期，需要重新加载
      console.warn(
        `续锁部分失败: ${res.renewed_count}/${lockedCardIds.value.length}`,
      );
    }
  } catch {
    // 续锁失败，静默处理
    console.warn('心跳续锁失败');
  }
}

function startLockHeartbeat() {
  stopLockHeartbeat(); // 确保不重复启动
  lockHeartbeatTimer = setInterval(renewLocks, LOCK_HEARTBEAT_INTERVAL);
}

function stopLockHeartbeat() {
  if (lockHeartbeatTimer) {
    clearInterval(lockHeartbeatTimer);
    lockHeartbeatTimer = null;
  }
}

// ========== beforeunload 事件兜底解锁 ==========
// 浏览器关闭/刷新前尝试解锁（使用 sendBeacon 确保请求发送）
function handleBeforeUnload() {
  if (lockedCardIds.value.length > 0) {
    // 使用 sendBeacon 发送请求，不阻塞页面卸载
    // 注意：sendBeacon 只能发送 POST 请求，且 Content-Type 受限
    const url = '/api/v1/rlhf/contents/unlock-all';
    navigator.sendBeacon(url, JSON.stringify({}));
  }
}

onMounted(() => {
  loadStatusOptions();
  loadTenantOptions();
  loadExpertOptions(); // 加载所有租户下的 Agent
  loadReviewerOptions();
  loadTodayStats();
  loadAllIssueTags();
  if (viewMode.value === 'card') {
    loadCardData();
  }
  // 获取符合条件的总记录数（用于全选功能，两种视图都需要）
  fetchFilteredTotalCount();
  // 注册键盘事件
  window.addEventListener('keydown', handleKeydown);
  // 注册 beforeunload 事件（兜底解锁）
  window.addEventListener('beforeunload', handleBeforeUnload);
  // 启动心跳续锁
  startLockHeartbeat();
});

// 监听视图模式变化
watch(viewMode, () => {
  // 切换视图时重置全选状态
  isSelectAllRecords.value = false;
  selectedRows.value = [];
});

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown);
  window.removeEventListener('beforeunload', handleBeforeUnload);
  // 停止心跳续锁
  stopLockHeartbeat();
  // 离开页面时解锁当前用户锁定的所有文章
  unlockAllMyContentsApi().catch(() => {
    // 解锁失败不影响页面卸载
  });
});

const [ReviewDetailModal, reviewDetailModalApi] = useVbenModal({
  connectedComponent: ReviewDetail,
});

// ========== 表格多选与导出 ==========
const selectedRows = ref<RLHFApi.RLHFFeedback[]>([]);
// 是否选择了所有符合条件的记录（跨页全选）
const isSelectAllRecords = ref(false);
// 符合当前筛选条件的总记录数
const filteredTotalCount = ref(0);

function handleSelectionChange(data: { records: RLHFApi.RLHFFeedback[] }) {
  selectedRows.value = data.records;
  // 当用户手动改变选择时，重置"选择全部"状态
  isSelectAllRecords.value = false;
}

// 获取当前筛选条件下的总记录数
async function fetchFilteredTotalCount() {
  try {
    const { onlyBanPassed, ...restSearchForm } = searchForm;
    const res = await getRLHFListApi({
      page: 1,
      page_size: 1, // 只获取总数，不需要实际数据
      exclude_locked: shouldLockArticles(),
      only_ban_passed: onlyBanPassed,
      ...restSearchForm,
    });
    filteredTotalCount.value = res.total || 0;
  } catch {
    filteredTotalCount.value = 0;
  }
}

// 选择所有符合条件的记录
function handleSelectAllRecords() {
  isSelectAllRecords.value = true;
  message.success(`已选择全部 ${filteredTotalCount.value} 条符合条件的记录`);
}

// 取消选择所有
function handleCancelSelectAll() {
  isSelectAllRecords.value = false;
  // 清空表格选择
  const $grid = gridApi.grid;
  if ($grid) {
    $grid.clearCheckboxRow();
  }
  selectedRows.value = [];
}

// 全选当前页（表格视图）或全选所有文章（卡片视图）
function handleSelectCurrentPage() {
  if (viewMode.value === 'card') {
    // 卡片视图：直接全选所有符合条件的文章
    handleSelectAllRecords();
  } else {
    // 表格视图：全选当前页
    const $grid = gridApi.grid;
    if ($grid) {
      $grid.setAllCheckboxRow(true);
      // 获取当前页所有行数据
      const tableData = $grid.getTableData().fullData;
      selectedRows.value = tableData;
      isSelectAllRecords.value = false;
    }
  }
}

// 计算实际选择的记录数
const actualSelectedCount = computed(() => {
  if (isSelectAllRecords.value) {
    return filteredTotalCount.value;
  }
  return selectedRows.value.length;
});

// 是否显示"选择全部"提示
const showSelectAllHint = computed(() => {
  // 当选择了当前页的记录，且总数大于当前页选择数时显示
  return (
    selectedRows.value.length > 0 &&
    !isSelectAllRecords.value &&
    filteredTotalCount.value > selectedRows.value.length
  );
});

// 导出配置弹窗
const exportModalVisible = ref(false);
const exportLoading = ref(false);
const exportProgress = reactive({
  current: 0,
  total: 0,
  stage: '', // 当前阶段描述
});

// 导出字段配置
interface ExportFieldConfig {
  key: string;
  label: string;
  required?: boolean; // 必选字段
  needExtraRequest?: boolean; // 需要额外API请求
  description?: string;
}

const exportFieldGroups = [
  {
    title: '必选字段',
    fields: [
      { key: 'id', label: 'ID', required: true },
      { key: 'title', label: '标题', required: true },
      { key: 'content', label: '内容', required: true },
    ] as ExportFieldConfig[],
  },
  {
    title: '基础信息',
    fields: [
      { key: 'created_at', label: '创建时间' },
      { key: 'updated_at', label: '更新时间' },
      { key: 'ge_expert_code', label: 'Expert编码' },
      { key: 'model_code', label: '模型编码' },
      { key: 'job_id', label: '任务ID' },
      { key: 'content_id', label: '内容ID' },
    ] as ExportFieldConfig[],
  },
  {
    title: '审核信息',
    fields: [
      { key: 'review_status', label: '审核状态' },
      { key: 'review_user_name', label: '审核人' },
      { key: 'review_time', label: '审核时间' },
      { key: 'like_status', label: '喜欢/不喜欢' },
      { key: 'like_reason', label: '审核原因' },
      { key: 'improvement_suggestion', label: '修改意见/AI总结' },
      { key: 'issue_tags', label: '问题标签' },
    ] as ExportFieldConfig[],
  },
  {
    title: '附加信息',
    fields: [
      { key: 'annotations', label: '划词评论' },
      { key: 'context_list', label: '上下文变量' },
    ] as ExportFieldConfig[],
  },
  {
    title: 'AI评分与合规（需额外请求，导出较慢）',
    fields: [
      {
        key: 'critic_scores',
        label: 'AI评分',
        needExtraRequest: true,
        description: '包含多维度评分：人设真实感、品牌匹配、文章优雅性等',
      },
      {
        key: 'critic_prompts',
        label: 'AI评分/审核规则（分列）',
        needExtraRequest: true,
        description: '每个专家的评分/审核规则单独一列导出',
      },
      {
        key: 'ban_results',
        label: '合规审核结果',
        needExtraRequest: true,
        description: '各审核项的通过/不通过及原因',
      },
    ] as ExportFieldConfig[],
  },
  {
    title: '生成背景（需额外请求，导出较慢）',
    fields: [
      {
        key: 'rendered_prompt',
        label: '渲染后的Prompt',
        needExtraRequest: true,
        description: 'LLM接收到的完整输入',
      },
      {
        key: 'generation_info',
        label: '生成信息',
        needExtraRequest: true,
        description: '包含Token消耗、耗时、成本等',
      },
    ] as ExportFieldConfig[],
  },
];

// 用户选中的导出字段
const selectedExportFields = ref<string[]>([
  'id',
  'title',
  'content',
  'review_status',
  'review_user_name',
  'improvement_suggestion',
  'issue_tags',
]);

// 计算是否选择了需要额外请求的字段
const hasSlowFields = computed(() => {
  const slowFieldKeys = new Set(
    exportFieldGroups
      .flatMap((g) => g.fields)
      .filter((f) => f.needExtraRequest)
      .map((f) => f.key),
  );
  return selectedExportFields.value.some((k) => slowFieldKeys.has(k));
});

function openExportModal() {
  exportModalVisible.value = true;
}

function handleExportFieldChange(key: string, checked: boolean) {
  if (checked) {
    if (!selectedExportFields.value.includes(key)) {
      selectedExportFields.value.push(key);
    }
  } else {
    selectedExportFields.value = selectedExportFields.value.filter(
      (k) => k !== key,
    );
  }
}

// 全选/取消某分组
function toggleGroupFields(groupTitle: string, checked: boolean) {
  const group = exportFieldGroups.find((g) => g.title === groupTitle);
  if (!group) return;
  const fieldKeys = group.fields.filter((f) => !f.required).map((f) => f.key);
  if (checked) {
    fieldKeys.forEach((k) => {
      if (!selectedExportFields.value.includes(k)) {
        selectedExportFields.value.push(k);
      }
    });
  } else {
    selectedExportFields.value = selectedExportFields.value.filter(
      (k) => !fieldKeys.includes(k),
    );
  }
}

// 检查分组是否全选
function isGroupAllSelected(groupTitle: string): boolean {
  const group = exportFieldGroups.find((g) => g.title === groupTitle);
  if (!group) return false;
  const optionalFields = group.fields.filter((f) => !f.required);
  if (optionalFields.length === 0) return true;
  return optionalFields.every((f) =>
    selectedExportFields.value.includes(f.key),
  );
}

// 检查分组是否部分选中
function isGroupIndeterminate(groupTitle: string): boolean {
  const group = exportFieldGroups.find((g) => g.title === groupTitle);
  if (!group) return false;
  const optionalFields = group.fields.filter((f) => !f.required);
  if (optionalFields.length === 0) return false;
  const selectedCount = optionalFields.filter((f) =>
    selectedExportFields.value.includes(f.key),
  ).length;
  return selectedCount > 0 && selectedCount < optionalFields.length;
}

// 执行导出
async function handleExport() {
  if (actualSelectedCount.value === 0) {
    message.warning('请先选择要导出的文章');
    return;
  }

  const exportCount = actualSelectedCount.value;

  // 如果选择了需要额外请求的字段，弹出确认
  if (hasSlowFields.value) {
    Modal.confirm({
      title: '导出确认',
      content: `您选择了需要额外请求的字段（AI评分、合规结果或生成背景），导出 ${exportCount} 篇文章可能需要较长时间。是否继续？`,
      okText: '继续导出',
      cancelText: '取消',
      onOk: () => {
        doExport();
      },
    });
  } else {
    doExport();
  }
}

async function doExport() {
  exportLoading.value = true;
  exportProgress.current = 0;
  exportProgress.stage = '准备导出...';

  try {
    // 获取要导出的数据
    let rowsToExport: RLHFApi.RLHFFeedback[] = [];

    if (isSelectAllRecords.value) {
      // 如果选择了所有记录，需要分页获取全部数据
      exportProgress.stage = '正在获取全部数据...';
      const pageSize = 100; // 每页获取100条
      const totalPages = Math.ceil(filteredTotalCount.value / pageSize);
      const { onlyBanPassed, ...restSearchForm } = searchForm;

      for (let page = 1; page <= totalPages; page++) {
        exportProgress.stage = `正在获取数据 (${page}/${totalPages})...`;
        const res = await getRLHFListApi({
          page,
          page_size: pageSize,
          exclude_locked: false, // 导出时不排除锁定的
          only_ban_passed: onlyBanPassed,
          ...restSearchForm,
        });
        rowsToExport.push(...(res.items || []));
      }
    } else {
      // 使用当前选中的行
      rowsToExport = selectedRows.value;
    }

    exportProgress.total = rowsToExport.length;
    const exportData: Record<string, unknown>[] = [];

    // 收集所有专家规则的动态列（用于 critic_prompts）
    // key: expert_config_code, value: { name: 显示名称, type: 'CRITIC' | 'BAN' }
    const expertRuleColumns = new Map<string, { name: string; type: string }>();
    const needCollectRuleColumns =
      selectedExportFields.value.includes('critic_prompts');

    for (let i = 0; i < rowsToExport.length; i++) {
      const row = rowsToExport[i];
      exportProgress.current = i + 1;
      exportProgress.stage = `处理第 ${i + 1}/${rowsToExport.length} 篇文章...`;

      const rowData: Record<string, unknown> = {};

      // 基础字段直接取值
      for (const fieldKey of selectedExportFields.value) {
        switch (fieldKey) {
          case 'annotations': {
            // 划词评论
            rowData[fieldKey] =
              row.annotations && row.annotations.length > 0
                ? row.annotations
                    .map(
                      (a: {
                        comment?: string;
                        text?: string;
                        user_name?: string;
                      }) =>
                        `[${a.user_name || '匿名'}] ${a.text || ''}: ${a.comment || ''}`,
                    )
                    .join('\n')
                : '';
            break;
          }
          case 'ban_results':
          case 'critic_prompts':
          case 'critic_scores': {
            // 需要额外请求的字段
            if (row.job_id && row.content_id) {
              exportProgress.stage = `获取第 ${i + 1} 篇文章的AI评分数据...`;
              try {
                const expertResults = await getContentExpertResultsApi(
                  row.job_id,
                  row.content_id,
                );
                if (fieldKey === 'critic_scores') {
                  // 提取 CRITIC 类型评分
                  const criticResults = expertResults.filter(
                    (r) => r.expert_type === 'CRITIC',
                  );
                  rowData[fieldKey] =
                    criticResults.length > 0
                      ? criticResults
                          .map((r) => {
                            const result = r.business_result as
                              | Record<string, unknown>
                              | undefined;
                            const score = result?.score ?? '-';
                            return `${r.expert_config_name || r.expert_func}: ${score}分`;
                          })
                          .join('; ')
                      : '';
                } else if (fieldKey === 'critic_prompts') {
                  // 提取所有专家（CRITIC + BAN）的评分/审核规则，分列存储
                  // 筛选 CRITIC 和 BAN 类型的专家结果
                  const ruleResults = expertResults.filter(
                    (r) =>
                      r.expert_type === 'CRITIC' || r.expert_type === 'BAN',
                  );
                  for (const r of ruleResults) {
                    const configCode = r.expert_config_code;
                    const configName =
                      r.expert_config_name || r.expert_func || configCode;
                    const expertType = r.expert_type || 'UNKNOWN';
                    const prompt = r.prompt || '';

                    // 收集专家列信息
                    if (needCollectRuleColumns && configCode) {
                      expertRuleColumns.set(configCode, {
                        name: configName,
                        type: expertType,
                      });
                    }

                    // 使用动态 key 存储每个专家的规则
                    if (configCode) {
                      rowData[`rule_${configCode}`] = prompt;
                    }
                  }
                  // 标记已处理（不需要在主列存储）
                  rowData[fieldKey] = '';
                } else {
                  // 提取 BAN 类型结果
                  const banResults = expertResults.filter(
                    (r) => r.expert_type === 'BAN',
                  );
                  rowData[fieldKey] =
                    banResults.length > 0
                      ? banResults
                          .map((r) => {
                            const result = r.business_result as
                              | Record<string, unknown>
                              | undefined;
                            const passed = result?.passed ? '通过' : '不通过';
                            return `${r.expert_config_name || r.expert_func}: ${passed}`;
                          })
                          .join('; ')
                      : '';
                }
              } catch {
                rowData[fieldKey] = '获取失败';
              }
            } else {
              rowData[fieldKey] = '';
            }
            break;
          }
          case 'content': {
            // 优先使用精修后的内容，如果没有则使用原始内容
            rowData[fieldKey] = row.modified_content || row.content || '';
            break;
          }
          case 'content_id':
          case 'created_at':
          case 'ge_expert_code':
          case 'id':
          case 'improvement_suggestion':
          case 'job_id':
          case 'like_reason':
          case 'model_code':
          case 'review_time':
          case 'review_user_name':
          case 'updated_at': {
            rowData[fieldKey] =
              row[fieldKey as keyof RLHFApi.RLHFFeedback] ?? '';
            break;
          }
          case 'context_list': {
            // 上下文变量
            rowData[fieldKey] =
              row.context_list && Object.keys(row.context_list).length > 0
                ? Object.entries(row.context_list)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join('; ')
                : '';
            break;
          }
          case 'generation_info':
          case 'rendered_prompt': {
            // 需要额外请求生成背景
            if (row.content_id) {
              exportProgress.stage = `获取第 ${i + 1} 篇文章的生成背景...`;
              try {
                const genCtx = await getGenerationContextApi(row.content_id);
                if (fieldKey === 'rendered_prompt') {
                  rowData[fieldKey] = genCtx.generation?.rendered_prompt || '';
                } else {
                  const gen = genCtx.generation;
                  rowData[fieldKey] = gen
                    ? `模型: ${gen.model_code || '-'}, Token: ${gen.total_tokens || '-'}, 耗时: ${gen.duration_ms || '-'}ms, 成本: ${gen.total_cost || '-'}`
                    : '';
                }
              } catch {
                rowData[fieldKey] = '获取失败';
              }
            } else {
              rowData[fieldKey] = '';
            }
            break;
          }
          case 'issue_tags': {
            // 问题标签：通过 issue_tag_ids 转换为标签名
            // 使用 Number() 转换确保类型匹配（后端 JSON 可能返回字符串类型的数字）
            if (row.issue_tag_ids && row.issue_tag_ids.length > 0) {
              const tagIdNumbers = new Set(row.issue_tag_ids.map(Number));
              const tagNames = allIssueTags.value
                .filter((t) => tagIdNumbers.has(t.id))
                .map((t) => t.tag_name);
              rowData[fieldKey] = tagNames.join(', ');
            } else {
              rowData[fieldKey] = '';
            }
            break;
          }
          case 'like_status': {
            // 优先使用 like_status 字段，如果不存在则根据 review_status 推断
            if (row.like_status === 1 || row.review_status === 'LIKED') {
              rowData[fieldKey] = '喜欢';
            } else if (
              row.like_status === -1 ||
              row.review_status === 'DISLIKED'
            ) {
              rowData[fieldKey] = '不喜欢';
            } else {
              rowData[fieldKey] = '未评价';
            }
            break;
          }
          case 'review_status': {
            // 将审核状态转换为中文
            {
              const statusMap: Record<string, string> = {
                PENDING: '待审核',
                IN_PROGRESS: '审核中',
                LIKED: '已评价-喜欢',
                DISLIKED: '已评价-不喜欢',
                COMPLETED: '待抽检',
                IN_INSPECTION: '正在抽检',
                INSPECTION_PASSED: '抽检通过',
                INSPECTION_FAILED: '抽检未通过',
              };
              rowData[fieldKey] =
                statusMap[row.review_status] || row.review_status || '';
            }
            break;
          }
          case 'title': {
            // 优先使用精修后的标题，如果没有则使用原始标题
            rowData[fieldKey] = row.modified_title || row.title || '';
            break;
          }
        }
      }

      exportData.push(rowData);
    }

    exportProgress.stage = '正在生成文件...';

    // 构建最终的列列表（包含动态的专家规则列）
    const finalFieldKeys: string[] = [];
    const finalHeaders: string[] = [];

    for (const key of selectedExportFields.value) {
      if (key === 'critic_prompts') {
        // 跳过原始的 critic_prompts 列，用动态列替代
        // 按专家类型分组：先 CRITIC（评分），后 BAN（审核）
        const sortedExperts = [...expertRuleColumns.entries()].toSorted(
          (a, b) => {
            // CRITIC 类型排在前面
            if (a[1].type === 'CRITIC' && b[1].type !== 'CRITIC') return -1;
            if (a[1].type !== 'CRITIC' && b[1].type === 'CRITIC') return 1;
            // 同类型按名称排序
            return a[1].name.localeCompare(b[1].name);
          },
        );

        for (const [configCode, info] of sortedExperts) {
          const ruleKey = `rule_${configCode}`;
          const typeLabel = info.type === 'CRITIC' ? '评分规则' : '审核规则';
          finalFieldKeys.push(ruleKey);
          finalHeaders.push(`${typeLabel}-${info.name}`);
        }
      } else {
        finalFieldKeys.push(key);
        const field = exportFieldGroups
          .flatMap((g) => g.fields)
          .find((f) => f.key === key);
        finalHeaders.push(field?.label || key);
      }
    }

    // 生成数据行
    const rows = exportData.map((row) =>
      finalFieldKeys.map((key) => row[key] ?? ''),
    );

    // 创建工作表数据（表头 + 数据行）
    const wsData = [finalHeaders, ...rows];

    // 创建工作簿和工作表
    const wb = XLSX.utils.book_new();
    const ws = XLSX.utils.aoa_to_sheet(wsData);

    // 设置列宽（提升可读性）
    ws['!cols'] = finalFieldKeys.map((key) => {
      // 根据字段类型设置不同的列宽
      if (key === 'id') return { wch: 8 };
      if (key === 'title' || key === 'modified_title') return { wch: 30 };
      if (key === 'content' || key === 'modified_content') return { wch: 60 };
      if (key === 'comment' || key === 'rendered_prompt') return { wch: 50 };
      if (key.includes('time') || key.includes('_at')) return { wch: 18 };
      if (key.startsWith('rule_')) return { wch: 60 }; // 规则列宽一些
      return { wch: 15 };
    });

    XLSX.utils.book_append_sheet(wb, ws, '内容抽检数据');

    // 导出文件
    const fileName = `内容抽检导出_${new Date().toISOString().slice(0, 10)}.xlsx`;
    XLSX.writeFile(wb, fileName);

    message.success(`成功导出 ${exportData.length} 篇文章`);
    exportModalVisible.value = false;
  } catch (error: unknown) {
    message.error(error instanceof Error ? error.message : '导出失败');
  } finally {
    exportLoading.value = false;
    exportProgress.stage = '';
  }
}

const gridOptions: VxeGridProps = {
  height: 'auto',
  checkboxConfig: {
    highlight: true,
    range: true,
  },
  columns: [
    { type: 'checkbox', width: 50, fixed: 'left' },
    { field: 'id', title: 'ID', width: 70 },
    {
      field: 'title',
      title: '标题',
      minWidth: 180,
      showOverflow: true,
      slots: { default: 'title' },
    },
    {
      field: 'content',
      title: '内容预览',
      minWidth: 300,
      showOverflow: true,
      slots: { default: 'content' },
    },
    { field: 'ge_expert_code', title: 'Expert', width: 120 },
    {
      field: 'review_status',
      title: '状态',
      width: 100,
      slots: { default: 'review_status' },
    },
    {
      field: 'review_user_name',
      title: '审核人',
      width: 100,
      slots: { default: 'reviewer' },
    },
    { field: 'created_at', title: '创建时间', width: 140 },
    { title: '操作', width: 140, slots: { default: 'action' }, fixed: 'right' },
  ],
  pagerConfig: {},
  proxyConfig: {
    ajax: {
      query: async ({ page }) => {
        // 构建请求参数（将前端驼峰命名转换为后端蛇形命名）
        const { onlyBanPassed, ...restSearchForm } = searchForm;
        const res = await getRLHFListApi({
          page: page.currentPage,
          page_size: page.pageSize,
          exclude_locked: shouldLockArticles(), // 仅在待审核/审核中排除其他用户锁定的文章
          only_ban_passed: onlyBanPassed, // 仅显示合规通过的文章（后端筛选）
          ...restSearchForm,
        });
        // 同步更新符合条件的总记录数（用于全选功能）
        filteredTotalCount.value = res.total || 0;
        return res;
      },
    },
  },
};

const [Grid, gridApi] = useVbenVxeGrid({
  gridOptions: gridOptions as any,
  gridEvents: {
    checkboxChange: handleSelectionChange,
    checkboxAll: handleSelectionChange,
  },
});

// 统一刷新函数
async function refreshData() {
  // 如果不再需要锁定文章（例如从待审核切换到喜欢），先解锁之前锁定的文章
  const needLock = shouldLockArticles();
  if (!needLock && lockedCardIds.value.length > 0) {
    try {
      await batchUnlockContentsApi(lockedCardIds.value);
      lockedCardIds.value = [];
    } catch {
      // 解锁失败不影响后续操作
    }
  }

  if (viewMode.value === 'table') {
    gridApi.reload();
  } else {
    cardPagination.current = 1;
    loadCardData();
  }
  // 获取符合条件的总记录数（用于全选功能，两种视图都需要）
  fetchFilteredTotalCount();
  // 同时更新统计数据，确保筛选条件变化后统计数据也同步更新
  loadTodayStats();
  // 重置全选状态
  isSelectAllRecords.value = false;
}

// 防抖搜索（关键字输入时 300ms 防抖）
const debouncedSearch = useDebounceFn(() => {
  refreshData();
}, 300);

// 实时监听筛选条件变化
watch(
  () => searchForm.keyword,
  () => {
    debouncedSearch();
  },
);

watch(
  () => searchForm.review_status,
  () => {
    refreshData();
  },
);

watch(
  () => searchForm.ge_expert_code,
  () => {
    refreshData();
  },
);

watch(
  () => searchForm.onlyBanPassed,
  () => {
    refreshData();
  },
);

function handleReset() {
  searchForm.keyword = '';
  searchForm.review_status = undefined;
  searchForm.tenant_id = undefined;
  searchForm.ge_expert_code = undefined;
  searchForm.job_id = undefined;
  searchForm.reviewer_id = undefined;
  searchForm.onlyBanPassed = false;
  // 清空任务选项（Agent 选项保留，因为已经加载了所有租户下的 Agent）
  jobOptions.value = [];
  refreshData();
}

async function handleRandomReview() {
  try {
    const res = await getRandomRLHFContentsApi(1);
    const first = res?.[0];
    if (first) {
      openDetail(first);
      gridApi.reload();
    } else {
      message.info('暂无待审核内容');
    }
  } catch (error: unknown) {
    message.error(error instanceof Error ? error.message : '获取任务失败');
  }
}

async function openDetail(record: RLHFApi.RLHFFeedback) {
  // 如果是待抽检或抽检中，尝试锁定
  if (
    record.review_status === 'COMPLETED' ||
    record.review_status === 'IN_INSPECTION'
  ) {
    try {
      await lockContentApi(record.id);
    } catch {
      // 忽略锁定错误，可能是已被锁定
    }
  }

  reviewDetailModalApi.setData({ id: record.id });
  reviewDetailModalApi.open();
}

function onModalClose(changed: boolean) {
  if (changed) {
    gridApi.reload();
  }
}

// ========== 审核操作（带动画） ==========
async function handleReviewWithAnimation(
  record: RLHFApi.RLHFFeedback,
  status: 'DISLIKED' | 'LIKED',
) {
  // 如果已经在审核中，忽略
  if (reviewedCards.value.has(record.id)) {
    return;
  }

  // 打开 AI 总结弹窗
  openAISummaryModal(record, status);
}

// 表格视图的审核操作（无动画，直接刷新）
async function handleReview(record: RLHFApi.RLHFFeedback, status: string) {
  // 获取当前状态
  const currentLikeStatus = getLikeStatus(record);
  const wasLiked = currentLikeStatus === 1;
  const wasDisliked = currentLikeStatus === -1;

  try {
    await updateReviewStatusApi(record.id, { review_status: status });

    // 更新统计（根据之前的状态调整）
    if (status === 'LIKED') {
      todayStats.liked++;
      if (wasDisliked) {
        // 从不喜欢改为喜欢
        todayStats.disliked = Math.max(0, todayStats.disliked - 1);
        message.success('已从不喜欢改为喜欢');
      } else if (wasLiked) {
        // 已经是喜欢状态，不重复操作
        todayStats.liked--;
        message.info('已经是喜欢状态');
        return;
      } else {
        // 从待审核变为喜欢
        todayStats.total++;
        todayStats.pending = Math.max(0, todayStats.pending - 1);
        message.success('已标记为喜欢');
      }
    } else {
      todayStats.disliked++;
      if (wasLiked) {
        // 从喜欢改为不喜欢
        todayStats.liked = Math.max(0, todayStats.liked - 1);
        message.success('已从喜欢改为不喜欢');
      } else if (wasDisliked) {
        // 已经是不喜欢状态，不重复操作
        todayStats.disliked--;
        message.info('已经是不喜欢状态');
        return;
      } else {
        // 从待审核变为不喜欢
        todayStats.total++;
        todayStats.pending = Math.max(0, todayStats.pending - 1);
        message.success('已标记为不喜欢');
      }
    }

    refreshData();
  } catch (error: unknown) {
    message.error(error instanceof Error ? error.message : '操作失败');
  }
}

// 获取卡片的审核状态
function getCardReviewState(id: number) {
  return reviewedCards.value.get(id);
}

// 检查卡片是否是当前聚焦的
function isCardFocused(index: number) {
  return viewMode.value === 'card' && focusedCardIndex.value === index;
}

// 截取内容预览
function truncateContent(content: string | undefined, maxLen = 100): string {
  if (!content) return '';
  return content.length > maxLen ? `${content.slice(0, maxLen)}...` : content;
}

// ==================== 评分和 BAN 结果 ====================

/** BAN 结果项 */
interface BanResultItem {
  expertFunc: string;
  label: string;
  passed: boolean;
  reason?: string;
  /** AI 审核规则/提示词 */
  prompt?: string;
}

/** 卡片评分和 BAN 数据缓存 */
interface CardCriticData {
  loading: boolean;
  // CRITIC 类型评分（用于雷达图）
  scores: Array<{
    dimension: string;
    label: string;
    /** AI 评分规则/提示词 */
    prompt?: string;
    reason?: string;
    score: number;
  }>;
  hasScores: boolean;
  // BAN 类型结果（用于审核结果展示）
  banResults: BanResultItem[];
  hasBanIssue: boolean;
}
const cardCriticDataMap = ref<Map<number, CardCriticData>>(new Map());

// 注意："仅合规通过"筛选已改为后端实现，前端不再需要本地过滤
// 后端 API 参数 only_ban_passed 会排除有 BAN 问题的文章

/**
 * 根据 expert_type 字段动态分类专家结果
 * - BAN 类型：用于 AI 文章审核（合规检查）
 * - CRITIC 类型：用于评分雷达图
 */

/** 获取专家显示名称（优先使用 expert_config_name，fallback 到 expert_func） */
function getExpertDisplayName(
  expertConfigName?: string,
  expertFunc?: string,
): string {
  // 优先使用配置名称
  if (expertConfigName) {
    return expertConfigName;
  }
  // fallback: 从 expert_func 提取简化名称
  if (expertFunc) {
    // 移除 "Critic" 前缀
    return expertFunc.replace(/^Critic/, '') || expertFunc;
  }
  return '未知';
}

/** 加载卡片的评分和 BAN 数据（根据 expert_type 动态分类） */
async function loadCardCriticData(item: RLHFApi.RLHFFeedback) {
  if (!item.job_id || !item.content_id) return;

  // 如果已加载过，不重复加载
  if (cardCriticDataMap.value.has(item.id)) return;

  // 设置加载状态
  cardCriticDataMap.value.set(item.id, {
    loading: true,
    scores: [],
    hasScores: false,
    banResults: [],
    hasBanIssue: false,
  });

  try {
    const results = await getContentExpertResultsApi(
      item.job_id,
      item.content_id,
    );

    // 根据 expert_type 动态分类，使用 Map 去重（以 expertFunc 为唯一键）
    const scoresMap = new Map<
      string,
      {
        dimension: string;
        label: string;
        prompt?: string;
        reason?: string;
        score: number;
      }
    >();
    const banResultsMap = new Map<string, BanResultItem>();

    for (const result of results || []) {
      const expertType = result.expert_type?.toUpperCase();
      const expertFunc = result.expert_func || '';
      const expertConfigCode = result.expert_config_code || '';
      const expertConfigName = result.expert_config_name;
      const businessResult = result.business_result;

      // 使用 expert_config_code 作为唯一标识，允许 expert_func 为空
      if (!businessResult || !expertConfigCode) continue;

      // 获取显示名称
      const displayLabel = getExpertDisplayName(expertConfigName, expertFunc);

      // 根据 expert_type 分类（使用 expert_config_code 去重，避免相同 expert_func 的专家互相覆盖）
      if (expertType === 'CRITIC') {
        // CRITIC 类型：用于雷达图评分
        if (businessResult.score !== undefined) {
          scoresMap.set(expertConfigCode, {
            dimension: expertFunc || expertConfigCode, // 优先使用 expertFunc 作为维度标识
            label: displayLabel,
            score: Number(businessResult.score) || 0,
            reason: businessResult.reason as string | undefined,
            prompt: result.prompt, // 透传评分规则
          });
        }
      } else if (expertType === 'BAN') {
        // BAN 类型：用于 AI 文章审核
        // BAN 类型的 passed 可能是布尔值或 0/1
        const passed =
          businessResult.passed === true ||
          businessResult.passed === 1 ||
          businessResult.score === 1;
        banResultsMap.set(expertConfigCode, {
          expertFunc: expertFunc || expertConfigCode, // 保持 expertFunc 字段用于兼容
          label: displayLabel,
          passed,
          reason: businessResult.reason as string | undefined,
          prompt: result.prompt, // 透传审核规则
        });
      }
    }

    // 转换 Map 为数组
    const scores = [...scoresMap.values()];
    const banResults = [...banResultsMap.values()];

    const hasBanIssue = banResults.some((r) => !r.passed);

    cardCriticDataMap.value.set(item.id, {
      loading: false,
      scores,
      hasScores: scores.length > 0,
      banResults,
      hasBanIssue,
    });
  } catch (error) {
    console.error('加载评分数据失败:', error);
    cardCriticDataMap.value.set(item.id, {
      loading: false,
      scores: [],
      hasScores: false,
      banResults: [],
      hasBanIssue: false,
    });
  }
}

/** 获取卡片的评分和 BAN 数据 */
function getCardCriticData(id: number): CardCriticData {
  return (
    cardCriticDataMap.value.get(id) || {
      loading: false,
      scores: [],
      hasScores: false,
      banResults: [],
      hasBanIssue: false,
    }
  );
}

/** 卡片列表变化时加载评分数据 */
watch(
  cardList,
  (list) => {
    // 清除不在列表中的缓存
    const currentIds = new Set(list.map((item) => item.id));
    for (const id of cardCriticDataMap.value.keys()) {
      if (!currentIds.has(id)) {
        cardCriticDataMap.value.delete(id);
      }
    }
    // 加载新卡片的评分数据
    for (const item of list) {
      loadCardCriticData(item);
    }
  },
  { immediate: true },
);
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
          {{ route.meta.title || 'RLHF 审核台' }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">Agent</span>
          <Select
            v-model:value="searchForm.ge_expert_code"
            placeholder="Agent"
            style="width: 200px"
            allow-clear
            show-search
            :loading="expertOptionsLoading"
            :title="selectedAgentLabel"
            :filter-option="
              (input: string, option: { label: string }) =>
                option.label.toLowerCase().includes(input.toLowerCase())
            "
            @change="handleAgentChange"
          >
            <Select.Option
              v-for="opt in expertOptions"
              :key="opt.value"
              :value="opt.value"
              :title="opt.label"
            >
              {{ opt.label }}
            </Select.Option>
          </Select>
        </div>
        <div class="filter-item">
          <span class="filter-label">任务</span>
          <Select
            v-model:value="searchForm.job_id"
            :placeholder="
              searchForm.ge_expert_code ? '任务' : '任务(请先选择Agent)'
            "
            style="width: 180px"
            allow-clear
            show-search
            :loading="jobOptionsLoading"
            :disabled="!searchForm.ge_expert_code"
            :filter-option="
              (input: string, option: { label: string }) =>
                option.label.toLowerCase().includes(input.toLowerCase())
            "
            @change="refreshData"
          >
            <Select.Option
              v-for="opt in jobOptions"
              :key="opt.value"
              :value="opt.value"
              :title="opt.label"
            >
              {{ opt.label }}
            </Select.Option>
          </Select>
        </div>
        <div class="filter-item">
          <span class="filter-label">状态</span>
          <Select
            v-model:value="searchForm.review_status"
            placeholder="状态"
            style="width: 140px"
            allow-clear
            :options="statusOptions"
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">关键词</span>
          <Input
            v-model:value="searchForm.keyword"
            placeholder="搜索标题/内容/ID"
            style="width: 200px"
            allow-clear
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">审核人</span>
          <Select
            v-model:value="searchForm.reviewer_id"
            placeholder="审核人"
            style="width: 140px"
            allow-clear
            show-search
            :loading="reviewerOptionsLoading"
            :filter-option="
              (input: string, option: { label: string }) =>
                option.label.toLowerCase().includes(input.toLowerCase())
            "
            @change="refreshData"
          >
            <Select.Option
              v-for="opt in reviewerOptions"
              :key="opt.value"
              :value="opt.value"
            >
              {{ opt.label }}
            </Select.Option>
          </Select>
        </div>
        <div class="filter-item">
          <Tooltip title="只显示所有合规审核（BAN）都通过的文章">
            <div class="ban-filter-switch">
              <Switch v-model:checked="searchForm.onlyBanPassed" size="small" />
              <span class="switch-label">仅合规通过</span>
            </div>
          </Tooltip>
        </div>
        <div class="filter-actions">
          <Button @click="handleReset">重置</Button>
          <Button type="primary" @click="handleSelectCurrentPage">
            全选
          </Button>
        </div>
      </div>
    </div>

    <Card class="mb-4">
      <div class="toolbar-secondary">
        <!-- 今日审核统计 -->
        <div class="stats-panel">
          <Tooltip title="今日已审核">
            <div class="stat-item">
              <Statistic
                :value="todayStats.total"
                :value-style="{ fontSize: '16px', fontWeight: 600 }"
              >
                <template #prefix><BarChartOutlined /></template>
                <template #suffix>
                  <span class="stat-label">条</span>
                </template>
              </Statistic>
            </div>
          </Tooltip>
          <div class="stat-divider"></div>
          <Tooltip title="标记为喜欢">
            <div class="stat-item liked">
              <LikeOutlined />
              <span class="stat-value">{{ todayStats.liked }}</span>
            </div>
          </Tooltip>
          <Tooltip title="标记为不喜欢">
            <div class="stat-item disliked">
              <DislikeOutlined />
              <span class="stat-value">{{ todayStats.disliked }}</span>
            </div>
          </Tooltip>
          <div class="stat-divider"></div>
          <Tooltip title="待审核数量">
            <div class="stat-item pending">
              <span class="stat-value">{{ todayStats.pending }}</span>
              <span class="stat-label">待审</span>
            </div>
          </Tooltip>
          <div v-if="lockedCardIds.length > 0" class="stat-divider"></div>
          <Tooltip
            v-if="lockedCardIds.length > 0"
            title="当前页文章已被你锁定，其他用户不会看到这些文章"
          >
            <div class="stat-item locked">
              <LockOutlined />
              <span class="stat-value">{{ lockedCardIds.length }}</span>
              <span class="stat-label">已锁定</span>
            </div>
          </Tooltip>
        </div>

        <div class="toolbar-secondary-actions">
          <!-- 视图切换 -->
          <div class="view-switch">
            <Tooltip title="卡片视图 (支持快捷键)">
              <Button
                :type="viewMode === 'card' ? 'primary' : 'default'"
                @click="viewMode = 'card'"
              >
                <AppstoreOutlined />
              </Button>
            </Tooltip>
            <Tooltip title="表格视图">
              <Button
                :type="viewMode === 'table' ? 'primary' : 'default'"
                @click="viewMode = 'table'"
              >
                <OrderedListOutlined />
              </Button>
            </Tooltip>
          </div>

          <!-- 导出按钮（有选中文章时显示） -->
          <Button
            v-if="actualSelectedCount > 0"
            type="primary"
            @click="openExportModal"
          >
            <ExportOutlined />
            导出选中 ({{ actualSelectedCount }})
          </Button>

          <Button type="primary" ghost @click="handleRandomReview">
            随机抽检
          </Button>
        </div>
      </div>

      <!-- 筛选条件冲突提示 -->
      <Alert
        v-if="hasFilterConflict"
        type="warning"
        show-icon
        :message="`筛选条件冲突：选择了审核人「${reviewerOptions.find((o) => o.value === searchForm.reviewer_id)?.label || searchForm.reviewer_id}」的同时，状态为「待审核/审核中」。待审核的文章没有审核人，此筛选将返回空结果。`"
        style="margin-top: 12px"
        closable
      />

      <!-- 审核人筛选说明提示 -->
      <Alert
        v-if="
          searchForm.reviewer_id &&
          !hasFilterConflict &&
          !searchForm.review_status
        "
        type="info"
        show-icon
        message="已选择审核人，将显示该审核人审核过的所有文章（不区分状态）。文章锁定功能已自动关闭。"
        style="margin-top: 12px"
        closable
      />

      <!-- 快捷键提示（仅卡片视图） -->
      <div v-if="viewMode === 'card'" class="shortcuts-hint">
        <span>快捷键：</span>
        <Tag>L / →</Tag> 喜欢 <Tag>D / ←</Tag> 不喜欢 <Tag>空格</Tag> 详情
        <Tag>↑↓</Tag> 切换
        <span class="annotation-hint">| 💡 划选原文可添加评论</span>
      </div>
    </Card>

    <!-- 表格视图 -->
    <div v-if="viewMode === 'table'" class="h-[calc(100vh-280px)]">
      <!-- 全选提示栏 -->
      <div
        v-if="showSelectAllHint || isSelectAllRecords"
        class="select-all-hint"
      >
        <template v-if="isSelectAllRecords">
          <CheckCircleOutlined class="hint-icon success" />
          <span
            >已选择全部
            <strong>{{ filteredTotalCount }}</strong> 条符合条件的记录</span
          >
          <Button type="link" size="small" @click="handleCancelSelectAll">
            取消选择
          </Button>
        </template>
        <template v-else>
          <span
            >已选中当前页
            <strong>{{ selectedRows.length }}</strong> 条记录</span
          >
          <Button type="link" size="small" @click="handleSelectAllRecords">
            选择全部 {{ filteredTotalCount }} 条符合条件的记录
          </Button>
        </template>
      </div>

      <Grid>
        <template #title="{ row }">
          <Tooltip :title="row.modified_title || row.title">
            <span class="cursor-pointer hover:text-primary">
              {{ row.modified_title || row.title || '无标题' }}
            </span>
          </Tooltip>
        </template>
        <template #content="{ row }">
          <Tooltip
            :title="row.modified_content || row.content"
            placement="topLeft"
          >
            <span class="text-gray-500">
              {{ truncateContent(row.modified_content || row.content, 80) }}
            </span>
          </Tooltip>
        </template>
        <template #review_status="{ row }">
          <Tag :color="getStatusConfig(row.review_status).color">
            {{ getStatusConfig(row.review_status).label }}
          </Tag>
        </template>
        <template #reviewer="{ row }">
          <span v-if="row.review_user_name">{{ row.review_user_name }}</span>
          <span v-else class="text-gray-400">-</span>
        </template>
        <template #action="{ row }">
          <div class="flex items-center gap-1">
            <Tooltip :title="isLiked(row) ? '已喜欢（点击可取消）' : '喜欢'">
              <Button
                type="text"
                size="small"
                class="action-btn like"
                :class="{ 'is-liked': isLiked(row) }"
                @click="handleReview(row, 'LIKED')"
              >
                <LikeOutlined />
              </Button>
            </Tooltip>
            <Tooltip
              :title="isDisliked(row) ? '已不喜欢（点击可取消）' : '不喜欢'"
            >
              <Button
                type="text"
                size="small"
                class="action-btn dislike"
                :class="{ 'is-disliked': isDisliked(row) }"
                @click="handleReview(row, 'DISLIKED')"
              >
                <DislikeOutlined />
              </Button>
            </Tooltip>
            <Button type="link" size="small" @click="openDetail(row)">
              详情
            </Button>
          </div>
        </template>
      </Grid>
    </div>

    <!-- 卡片视图 -->
    <div v-else class="card-view">
      <!-- 卡片视图全选提示栏 -->
      <div v-if="isSelectAllRecords" class="select-all-hint">
        <CheckCircleOutlined class="hint-icon success" />
        <span
          >已选择全部
          <strong>{{ filteredTotalCount }}</strong> 条符合条件的记录</span
        >
        <Button type="link" size="small" @click="handleCancelSelectAll">
          取消选择
        </Button>
      </div>

      <Spin :spinning="cardLoading">
        <div v-if="cardList.length === 0 && !cardLoading" class="empty-state">
          <Empty description="暂无待审核内容 🎉" />
        </div>
        <div v-else class="card-list">
          <div
            v-for="(item, index) in cardList"
            :key="item.id"
            :data-index="index"
            class="review-card"
            :class="{
              'card-focused': isCardFocused(index),
              'card-reviewed': getCardReviewState(item.id),
              'card-reviewed-liked':
                getCardReviewState(item.id)?.status === 'LIKED',
              'card-reviewed-disliked':
                getCardReviewState(item.id)?.status === 'DISLIKED',
              'card-removing': getCardReviewState(item.id)?.removing,
            }"
            @click="focusedCardIndex = index"
          >
            <!-- 审核成功覆盖层 -->
            <div v-if="getCardReviewState(item.id)" class="review-overlay">
              <div class="review-result">
                <CheckCircleOutlined
                  v-if="getCardReviewState(item.id)?.status === 'LIKED'"
                  class="result-icon liked"
                />
                <CloseCircleOutlined v-else class="result-icon disliked" />
                <span class="result-text">
                  {{
                    getCardReviewState(item.id)?.status === 'LIKED'
                      ? '已标记为喜欢'
                      : '已标记为不喜欢'
                  }}
                </span>
              </div>
            </div>

            <div class="card-header">
              <div
                class="card-title selectable-title"
                @mouseup="(e: MouseEvent) => handleTitleMouseUp(item.id, e)"
              >
                {{ item.title || '无标题' }}
              </div>
            </div>

            <!-- 左右两栏布局：左侧内容，右侧审核结果和评分 -->
            <div class="card-body-layout">
              <!-- 左侧：文章内容 -->
              <div class="card-left">
                <!-- 原文内容编辑器（支持划选评论） -->
                <div class="card-content-section">
                  <div class="content-section-header">
                    <span class="section-label">📄 原文内容</span>
                  </div>
                  <div class="card-content-editor">
                    <MonacoEditor
                      :ref="
                        (el: unknown) =>
                          el && setCardEditorRef(item.id, el as CardEditorRef)
                      "
                      :model-value="item.content || ''"
                      language="plaintext"
                      :height="calcEditorHeight(item.content)"
                      :readonly="true"
                      :line-numbers="false"
                      :minimap="false"
                      @mouse-up="
                        (e: unknown) => handleCardEditorMouseUp(item.id, e)
                      "
                    />
                  </div>
                </div>

                <!-- 原文精修按钮 -->
                <div class="card-refine-actions">
                  <Button
                    v-if="!isRefineEditing(item.id)"
                    size="small"
                    type="dashed"
                    class="refine-btn"
                    :disabled="!!getCardReviewState(item.id)"
                    @click.stop="handleStartRefine(item)"
                  >
                    <template #icon><EditOutlined /></template>
                    原文精修
                  </Button>
                  <Tag
                    v-if="item.modified_content && !isRefineEditing(item.id)"
                    color="processing"
                    size="small"
                  >
                    已精修
                  </Tag>
                </div>

                <!-- 精修内容展示区域（非编辑状态，有精修内容时显示） -->
                <div
                  v-if="item.modified_content && !isRefineEditing(item.id)"
                  class="card-refined-content"
                >
                  <div class="refined-content-header">
                    <EditOutlined />
                    <span>精修内容</span>
                    <Tag color="processing" size="small">已保存</Tag>
                    <div class="diff-toggle">
                      <Switch
                        v-model:checked="showDiffHighlight"
                        size="small"
                      />
                      <span class="diff-toggle-label">显示差异</span>
                    </div>
                  </div>
                  <!-- 标题差异显示 -->
                  <div v-if="item.modified_title" class="refined-title">
                    <span class="refined-title-label">标题：</span>
                    <DiffViewer
                      v-if="
                        showDiffHighlight && item.title !== item.modified_title
                      "
                      class="refined-title-diff"
                      :original="item.title || ''"
                      :modified="item.modified_title"
                      :show-diff="showDiffHighlight"
                    />
                    <span v-else class="refined-title-text">{{
                      item.modified_title
                    }}</span>
                  </div>
                  <!-- 正文差异显示 -->
                  <div class="refined-content-body">
                    <DiffViewer
                      :original="item.content || ''"
                      :modified="item.modified_content || ''"
                      :show-diff="showDiffHighlight"
                    />
                  </div>
                </div>

                <!-- 精修编辑区域 -->
                <div v-if="isRefineEditing(item.id)" class="card-refine-editor">
                  <div class="refine-header">
                    <EditOutlined />
                    <span>原文精修</span>
                  </div>
                  <div class="refine-form">
                    <div class="refine-field">
                      <label class="refine-label">
                        标题
                        <span
                          v-if="getCardRefineState(item.id).saving"
                          class="saving-indicator"
                        >
                          保存中...
                        </span>
                      </label>
                      <Input
                        v-model:value="getCardRefineState(item.id).title"
                        placeholder="请输入精修后的标题"
                        @click.stop
                        @input="handleRefineInput(item.id)"
                      />
                    </div>
                    <div class="refine-field">
                      <label class="refine-label">
                        正文
                        <span
                          v-if="getCardRefineState(item.id).saving"
                          class="saving-indicator"
                        >
                          保存中...
                        </span>
                      </label>
                      <Input.TextArea
                        v-model:value="getCardRefineState(item.id).content"
                        placeholder="请输入精修后的正文内容"
                        :rows="8"
                        :show-count="true"
                        @click.stop
                        @input="handleRefineInput(item.id)"
                      />
                    </div>
                  </div>
                  <div class="refine-footer">
                    <span class="refine-hint">✓ 编辑时实时自动保存</span>
                    <Button
                      size="small"
                      danger
                      @click.stop="handleCancelRefine(item.id)"
                    >
                      <template #icon><CloseOutlined /></template>
                      取消编辑
                    </Button>
                  </div>
                </div>
              </div>

              <!-- 右侧：AI文章审核结果和评分雷达图 -->
              <div class="card-right">
                <!-- 右上：AI文章审核结果（合法性/合理性/目的性） -->
                <div class="card-ban-result">
                  <div class="ban-result-header">
                    <span class="result-label">AI文章审核</span>
                    <Tag
                      v-if="getCardCriticData(item.id).hasBanIssue"
                      color="error"
                      size="small"
                    >
                      存在问题
                    </Tag>
                    <Tag
                      v-else-if="
                        getCardCriticData(item.id).banResults.length > 0
                      "
                      color="success"
                      size="small"
                    >
                      全部通过
                    </Tag>
                  </div>
                  <div
                    v-if="getCardCriticData(item.id).loading"
                    class="ban-loading"
                  >
                    <Spin size="small" />
                  </div>
                  <div
                    v-else-if="getCardCriticData(item.id).banResults.length > 0"
                    class="ban-results-list"
                  >
                    <span
                      v-for="(banItem, idx) in getCardCriticData(item.id)
                        .banResults"
                      :key="banItem.expertFunc"
                      class="ban-result-item"
                    >
                      <span class="ban-label">{{ banItem.label }}</span>
                      <!-- 审核规则问号图标 -->
                      <Popover
                        v-if="banItem.prompt"
                        placement="top"
                        :overlay-style="{ maxWidth: '400px' }"
                      >
                        <template #content>
                          <div class="ban-rule-popover">
                            <div class="ban-rule-title">
                              {{ banItem.label }} - 审核规则
                            </div>
                            <div class="ban-rule-content">
                              {{ banItem.prompt }}
                            </div>
                          </div>
                        </template>
                        <QuestionCircleOutlined class="ban-rule-icon" />
                      </Popover>
                      <span class="ban-label-colon">：</span>
                      <!-- 通过/不通过标签（hover 显示理由） -->
                      <Popover
                        placement="top"
                        :overlay-style="{ maxWidth: '320px' }"
                      >
                        <template #content>
                          <div class="ban-reason-popover">
                            <div class="ban-reason-title">
                              {{ banItem.label }}
                              <Tag
                                :color="banItem.passed ? 'success' : 'error'"
                                size="small"
                              >
                                {{ banItem.passed ? '通过' : '不通过' }}
                              </Tag>
                            </div>
                            <div
                              v-if="banItem.reason"
                              class="ban-reason-content"
                            >
                              {{ banItem.reason }}
                            </div>
                            <div v-else class="ban-reason-empty">
                              暂无 AI 理由
                            </div>
                          </div>
                        </template>
                        <Tag
                          :color="banItem.passed ? 'success' : 'error'"
                          size="small"
                          class="ban-tag-hover"
                        >
                          {{ banItem.passed ? '通过' : '不通过' }}
                        </Tag>
                      </Popover>
                      <span
                        v-if="
                          idx < getCardCriticData(item.id).banResults.length - 1
                        "
                        class="ban-separator"
                      ></span>
                    </span>
                  </div>
                  <div v-else class="ban-empty">
                    <span class="empty-text">暂无合规数据</span>
                  </div>
                </div>

                <!-- 右下：评分雷达图 -->
                <div class="card-score-radar">
                  <div class="radar-header">
                    <span class="radar-label">AI 评分</span>
                    <span
                      v-if="getCardCriticData(item.id).hasScores"
                      class="radar-hint"
                    >
                      （悬浮问号查看AI评分规则）
                    </span>
                  </div>
                  <div
                    v-if="getCardCriticData(item.id).loading"
                    class="radar-loading"
                  >
                    <Spin size="small" />
                    <span>加载中...</span>
                  </div>
                  <div
                    v-else-if="getCardCriticData(item.id).hasScores"
                    class="radar-chart-wrapper"
                  >
                    <ScoreRadarChart
                      :scores="getCardCriticData(item.id).scores"
                      width="450px"
                      height="280px"
                      radius="50%"
                    />
                  </div>
                  <div v-else class="radar-empty">
                    <span class="empty-text">暂无评分数据</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 评论区域 -->
            <div
              v-if="getAnnotations(item).length > 0"
              class="card-annotations"
            >
              <div
                class="annotations-header"
                @click.stop="toggleAnnotations(item.id)"
              >
                <CommentOutlined />
                <span class="annotations-count">
                  {{ getAnnotations(item).length }} 条评论
                </span>
                <UpOutlined
                  v-if="isAnnotationsExpanded(item.id)"
                  class="expand-icon"
                />
                <DownOutlined v-else class="expand-icon" />
              </div>
              <div
                v-if="isAnnotationsExpanded(item.id)"
                class="annotations-list"
              >
                <div
                  v-for="(ann, idx) in getAnnotations(item)"
                  :key="ann.id || idx"
                  class="annotation-item"
                >
                  <div class="annotation-header">
                    <span class="annotation-author">{{
                      ann.user_name || '匿名'
                    }}</span>
                    <span class="annotation-time">{{ ann.create_time }}</span>
                  </div>
                  <div class="annotation-quote" v-if="ann.selected_text">
                    "{{
                      ann.selected_text.length > 50
                        ? `${ann.selected_text.slice(0, 50)}...`
                        : ann.selected_text
                    }}"
                  </div>
                  <div class="annotation-comment">{{ ann.comment }}</div>
                </div>
              </div>
            </div>

            <!-- 修改意见输入框 -->
            <div class="card-comment-input">
              <div class="card-comment-header">
                <span class="card-comment-label">修改意见/问题描述</span>
              </div>
              <Input.TextArea
                :value="getCardComment(item.id)"
                placeholder="请输入修改意见"
                :rows="2"
                :disabled="!!getCardReviewState(item.id)"
                @update:value="(val: string) => setCardComment(item.id, val)"
                @click.stop
              />
            </div>

            <!-- 问题标签 -->
            <div class="card-issue-tags">
              <div class="card-issue-tags-label">🏷️ 问题标签</div>
              <Select
                :value="getCardIssueTags(item.id)"
                mode="tags"
                style="width: 100%"
                placeholder="搜索、选择已有标签，或输入新标签按回车自动新增"
                :options="
                  allIssueTags.map((t) => ({
                    label: t.tag_name,
                    value: t.tag_name,
                  }))
                "
                :disabled="!!getCardReviewState(item.id)"
                allow-clear
                @update:value="
                  (val: string[]) => setCardIssueTags(item.id, val)
                "
                @click.stop
              />
            </div>

            <div class="card-actions">
              <Button
                type="primary"
                :ghost="!isLiked(item)"
                class="like-btn"
                :class="{ 'is-liked': isLiked(item) }"
                :disabled="!!getCardReviewState(item.id)"
                @click.stop="handleReviewWithAnimation(item, 'LIKED')"
              >
                <LikeOutlined /> {{ isLiked(item) ? '已喜欢' : '喜欢' }}
                <span
                  v-if="isCardFocused(index) && !isLiked(item)"
                  class="shortcut-hint"
                  >(L)</span
                >
              </Button>
              <Button
                type="primary"
                danger
                :ghost="!isDisliked(item)"
                class="dislike-btn"
                :class="{ 'is-disliked': isDisliked(item) }"
                :disabled="!!getCardReviewState(item.id)"
                @click.stop="handleReviewWithAnimation(item, 'DISLIKED')"
              >
                <DislikeOutlined />
                {{ isDisliked(item) ? '已不喜欢' : '不喜欢' }}
                <span
                  v-if="isCardFocused(index) && !isDisliked(item)"
                  class="shortcut-hint"
                  >(D)</span
                >
              </Button>
              <Button type="link" @click.stop="openDetail(item)">详情</Button>

              <!-- 审核人信息（优先显示 review_user_name，其次 like_user_name） -->
              <span
                v-if="item.review_user_name || item.like_user_name"
                class="reviewer-info"
              >
                审核人：{{ item.review_user_name || item.like_user_name }}
              </span>
            </div>
          </div>
        </div>
        <div v-if="cardList.length > 0" class="card-pagination">
          <Pagination
            v-model:current="cardPagination.current"
            v-model:page-size="cardPagination.pageSize"
            :total="cardPagination.total"
            show-size-changer
            show-quick-jumper
            :show-total="(total: number) => `共 ${total} 条`"
            @change="handleCardPageChange"
          />
        </div>
      </Spin>
    </div>

    <!-- 卡片划选评论浮窗 -->
    <div
      v-if="cardSelectionState.visible"
      class="fixed z-[2000]"
      :style="{
        left: `${cardSelectionState.x}px`,
        top: `${cardSelectionState.y}px`,
      }"
    >
      <Popover
        v-model:open="cardSelectionState.visible"
        trigger="click"
        placement="bottomRight"
      >
        <template #content>
          <div class="w-72 p-2">
            <div class="mb-2 flex items-center justify-between">
              <span class="text-xs font-bold">{{
                cardSelectionState.id ? '修改评论' : '添加评论'
              }}</span>
              <Button
                type="text"
                size="small"
                @click="handleCancelCardAnnotation"
              >
                <template #icon><CloseOutlined /></template>
              </Button>
            </div>
            <!-- 编辑已有评论时显示评论者信息 -->
            <div
              v-if="cardSelectionState.id && cardSelectionState.user_name"
              class="annotation-author-tag mb-2"
            >
              评论者：{{ cardSelectionState.user_name }}
            </div>
            <div
              class="mb-2 rounded bg-muted p-1 text-xs text-muted-foreground"
            >
              "{{
                cardSelectionState.text.length > 40
                  ? `${cardSelectionState.text.slice(0, 40)}...`
                  : cardSelectionState.text
              }}"
            </div>
            <Input.TextArea
              v-model:value="cardSelectionState.comment"
              :rows="3"
              auto-focus
              placeholder="请输入评论内容..."
            />
            <div class="mt-3 flex items-center justify-between">
              <Button
                v-if="cardSelectionState.id"
                danger
                size="small"
                type="text"
                @click="deleteCardAnnotation"
              >
                <template #icon><DeleteOutlined /></template>
                删除
              </Button>
              <div v-else></div>

              <div class="space-x-2">
                <Button size="small" @click="handleCancelCardAnnotation">
                  取消
                </Button>
                <Button type="primary" size="small" @click="saveCardAnnotation">
                  <template #icon><CheckOutlined /></template>
                  保存
                </Button>
              </div>
            </div>
          </div>
        </template>
        <div class="h-1 w-1"></div>
      </Popover>
    </div>

    <ReviewDetailModal @close="onModalClose" />

    <!-- AI 评价总结弹窗 -->
    <Modal
      v-model:open="aiSummaryModal.visible"
      :title="
        aiSummaryModal.reviewStatus === 'LIKED'
          ? '👍 AI 评价总结 - 喜欢'
          : '👎 AI 评价总结 - 不喜欢'
      "
      :width="600"
      :mask-closable="false"
      :keyboard="false"
      :footer="null"
      class="ai-summary-modal"
      @cancel="handleAISummaryCancel"
    >
      <div class="ai-summary-content">
        <!-- 加载状态 -->
        <div v-if="aiSummaryModal.loading" class="ai-summary-loading">
          <div class="loading-icon">
            <BulbOutlined :spin="true" />
          </div>
          <div class="loading-text">AI 正在努力总结您的评价...</div>
          <Progress
            :percent="Math.round(aiSummaryModal.progress)"
            :show-info="true"
            status="active"
            :stroke-color="{
              '0%': '#1677ff',
              '100%': '#52c41a',
            }"
          />
        </div>

        <!-- 错误状态 -->
        <div v-else-if="aiSummaryModal.error" class="ai-summary-error">
          <Alert type="error" :message="aiSummaryModal.error" show-icon />
        </div>

        <!-- 结果编辑区域 -->
        <div v-else class="ai-summary-result">
          <div class="result-section">
            <div class="result-section-label"><BulbOutlined /> AI 意见总结</div>
            <Input.TextArea
              v-model:value="aiSummaryModal.aiComment"
              :rows="5"
              placeholder="AI 生成的修改意见..."
              :maxlength="2000"
              show-count
            />
          </div>

          <div class="result-section">
            <div class="result-section-label">
              <AppstoreOutlined /> AI 总结标签
            </div>
            <Select
              v-model:value="aiSummaryModal.aiTags"
              mode="tags"
              style="width: 100%"
              placeholder="搜索、选择已有标签，或输入新标签按回车自动新增"
              :options="
                allIssueTags.map((t) => ({
                  label: t.tag_name,
                  value: t.tag_name,
                }))
              "
              allow-clear
            />
          </div>
        </div>

        <!-- 底部按钮 -->
        <div class="ai-summary-footer">
          <Button @click="handleAISummaryCancel">取消</Button>
          <Button
            :loading="aiSummaryModal.loading"
            :disabled="aiSummaryModal.loading"
            @click="handleAISummaryRegenerate"
          >
            <template #icon><BulbOutlined /></template>
            重新生成
          </Button>
          <Button
            type="primary"
            :disabled="aiSummaryModal.loading"
            @click="handleAISummaryConfirm"
          >
            <template #icon><CheckOutlined /></template>
            确认提交
          </Button>
        </div>
      </div>
    </Modal>

    <!-- 导出配置弹窗 -->
    <Modal
      v-model:open="exportModalVisible"
      title="导出配置"
      :width="700"
      :confirm-loading="exportLoading"
      ok-text="确认导出"
      cancel-text="取消"
      @ok="handleExport"
    >
      <div class="export-modal-content">
        <Alert
          v-if="hasSlowFields"
          type="warning"
          show-icon
          message="注意：您选择了需要额外请求的字段，导出大量文章时可能需要较长时间。"
          style="margin-bottom: 16px"
        />

        <div class="export-info">
          <Tag color="blue">
            已选择 {{ actualSelectedCount }} 篇文章
            <template v-if="isSelectAllRecords">（全部）</template>
          </Tag>
          <Tag>已选择 {{ selectedExportFields.length }} 个字段</Tag>
        </div>

        <Divider style="margin: 12px 0" />

        <div class="export-field-groups">
          <div
            v-for="group in exportFieldGroups"
            :key="group.title"
            class="export-field-group"
          >
            <div class="group-header">
              <Checkbox
                v-if="group.fields.some((f) => !f.required)"
                :checked="isGroupAllSelected(group.title)"
                :indeterminate="isGroupIndeterminate(group.title)"
                @change="
                  (e: { target: { checked: boolean } }) =>
                    toggleGroupFields(group.title, e.target.checked)
                "
              >
                <span class="group-title">{{ group.title }}</span>
              </Checkbox>
              <span v-else class="group-title">{{ group.title }}</span>
            </div>
            <div class="group-fields">
              <div
                v-for="field in group.fields"
                :key="field.key"
                class="field-item"
              >
                <Checkbox
                  :checked="
                    field.required || selectedExportFields.includes(field.key)
                  "
                  :disabled="field.required"
                  @change="
                    (e: { target: { checked: boolean } }) =>
                      handleExportFieldChange(field.key, e.target.checked)
                  "
                >
                  <span>{{ field.label }}</span>
                  <Tag v-if="field.required" size="small" color="green">
                    必选
                  </Tag>
                  <Tag
                    v-if="field.needExtraRequest"
                    size="small"
                    color="orange"
                  >
                    慢
                  </Tag>
                </Checkbox>
                <div v-if="field.description" class="field-desc">
                  {{ field.description }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 导出进度 -->
        <div v-if="exportLoading" class="export-progress">
          <Divider style="margin: 16px 0" />
          <div class="progress-stage">{{ exportProgress.stage }}</div>
          <Progress
            :percent="
              Math.round((exportProgress.current / exportProgress.total) * 100)
            "
            status="active"
          />
        </div>
      </div>
    </Modal>
  </Page>
</template>

<style scoped>
@keyframes card-fade-out {
  0% {
    max-height: 300px;
    padding: 16px 20px;
    margin-bottom: 0;
    opacity: 0.5;
    transform: scale(0.98);
  }

  100% {
    max-height: 0;
    padding: 0 20px;
    margin-bottom: -16px;
    opacity: 0;
    transform: scale(0.95);
  }
}

@keyframes overlay-fade-in {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}

@keyframes icon-bounce {
  0% {
    opacity: 0;
    transform: scale(0.5);
  }

  50% {
    transform: scale(1.2);
  }

  100% {
    opacity: 1;
    transform: scale(1);
  }
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }

  50% {
    opacity: 0.6;
    transform: scale(1.1);
  }
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.5;
  }
}

.ban-filter-switch {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 4px 8px;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted) / 50%);
  border-radius: 6px;
}

.ban-filter-switch .switch-label {
  white-space: nowrap;
}

.stats-panel {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 4px 12px;
  background: hsl(var(--muted) / 50%);
  border-radius: 8px;
}

.stat-item {
  display: flex;
  gap: 4px;
  align-items: center;
  font-size: 14px;
}

.stat-item.liked {
  color: #52c41a;
}

.stat-item.disliked {
  color: #ff4d4f;
}

.stat-item.pending {
  color: hsl(var(--muted-foreground));
}

.stat-item.locked {
  color: hsl(var(--warning));
}

.stat-value {
  font-weight: 600;
}

.stat-label {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.stat-divider {
  width: 1px;
  height: 16px;
  background: hsl(var(--border));
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

.toolbar-secondary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.toolbar-secondary-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

/* ========== 快捷键提示 ========== */
.shortcuts-hint {
  display: flex;
  gap: 8px;
  align-items: center;
  padding-top: 12px;
  margin-top: 12px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  border-top: 1px dashed hsl(var(--border));
}

.shortcuts-hint .ant-tag {
  margin: 0;
  font-family: monospace;
}

.shortcuts-hint .annotation-hint {
  margin-left: 8px;
  color: hsl(var(--warning));
}

/* ========== 视图切换 ========== */
.view-switch {
  display: flex;
  gap: 4px;
}

.view-switch .ant-btn {
  padding: 4px 8px;
}

/* ========== 表格操作按钮 ========== */
.action-btn.like:hover {
  color: #52c41a;
}

.action-btn.dislike:hover {
  color: #ff4d4f;
}

/* 已喜欢状态 */
.action-btn.like.is-liked {
  color: #52c41a;
  cursor: default;
  background-color: hsl(142deg 76% 36% / 10%);
}

/* 已不喜欢状态 */
.action-btn.dislike.is-disliked {
  color: #ff4d4f;
  cursor: default;
  background-color: hsl(0deg 84% 60% / 10%);
}

/* ========== 卡片视图 ========== */
.card-view {
  min-height: calc(100vh - 320px);
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
}

.card-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.review-card {
  position: relative;
  padding: 16px 20px;
  overflow: hidden;
  background: hsl(var(--card));
  border: 2px solid hsl(var(--border));
  border-radius: 8px;
  transition: all 0.3s ease;
}

.review-card:hover {
  border-color: hsl(var(--primary) / 50%);
  box-shadow: 0 2px 8px hsl(var(--primary) / 10%);
}

/* 聚焦状态 */
.review-card.card-focused {
  border-color: hsl(var(--primary));
  box-shadow: 0 0 0 3px hsl(var(--primary) / 20%);
}

/* 已审核状态 */
.review-card.card-reviewed {
  pointer-events: none;
}

.review-card.card-reviewed-liked {
  background: hsl(142deg 76% 36% / 5%);
  border-color: #52c41a;
}

.review-card.card-reviewed-disliked {
  background: hsl(0deg 84% 60% / 5%);
  border-color: #ff4d4f;
}

/* 移除动画 */
.review-card.card-removing {
  animation: card-fade-out 0.5s ease forwards;
}

/* 审核结果覆盖层 */
.review-overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  background: hsl(var(--card) / 90%);
  animation: overlay-fade-in 0.3s ease;
}

.review-result {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
}

.result-icon {
  font-size: 48px;
  animation: icon-bounce 0.5s ease;
}

.result-icon.liked {
  color: #52c41a;
}

.result-icon.disliked {
  color: #ff4d4f;
}

.result-text {
  font-size: 14px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

/* ========== 卡片内容 ========== */
.card-header {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 12px;
}

.card-title {
  flex: 1;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.4;
  color: hsl(var(--foreground));
}

/* 标题可划选样式 */
.selectable-title {
  cursor: text;
  user-select: text;
}

.selectable-title::selection {
  background: hsl(var(--primary) / 30%);
}

.card-content {
  margin-bottom: 12px;
  font-size: 14px;
  line-height: 1.2;
  color: hsl(var(--foreground));
  overflow-wrap: break-word;
  white-space: pre-wrap;
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 16px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.card-meta .reviewer-info {
  padding: 2px 8px;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 10%);
  border-radius: 4px;
}

/* ========== 评论区域 ========== */
.card-annotations {
  margin-bottom: 12px;
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
}

.annotations-header {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  font-size: 13px;
  color: hsl(var(--primary));
  cursor: pointer;
  background: hsl(var(--muted) / 50%);
  border-radius: 6px;
  transition: background 0.2s;
}

.annotations-header:hover {
  background: hsl(var(--muted));
}

.annotations-count {
  flex: 1;
  font-weight: 500;
}

.expand-icon {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.annotations-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid hsl(var(--border));
}

.annotation-item {
  padding: 8px 12px;
  background: hsl(var(--muted) / 30%);
  border-left: 3px solid hsl(var(--primary));
  border-radius: 4px;
}

.annotation-header {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 6px;
  font-size: 12px;
}

.annotation-author {
  padding: 1px 8px;
  font-weight: 500;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 15%);
  border-radius: 3px;
}

.annotation-time {
  color: hsl(var(--muted-foreground));
}

.annotation-quote {
  padding: 4px 8px;
  margin-bottom: 6px;
  font-size: 12px;
  font-style: italic;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted) / 50%);
  border-radius: 3px;
}

.annotation-comment {
  font-size: 13px;
  line-height: 1.4;
  color: hsl(var(--foreground));
}

/* ========== 修改意见输入框 ========== */
.card-comment-input {
  margin-bottom: 12px;
}

.card-comment-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}

.card-comment-label {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.ai-summarize-btn.ant-btn {
  height: 22px !important;
  padding: 0 10px !important;
  font-size: 11px !important;
  font-weight: 500 !important;
  line-height: 20px !important;
  color: #fff !important;
  background: #1677ff !important;
  border: none !important;
  border-radius: 4px !important;
  box-shadow: 0 1px 3px rgb(22 119 255 / 40%) !important;
}

.ai-summarize-btn.ant-btn:hover:not(:disabled) {
  color: #fff !important;
  background: #4096ff !important;
  box-shadow: 0 2px 6px rgb(22 119 255 / 50%) !important;
}

.ai-summarize-btn.ant-btn:disabled {
  color: #999 !important;
  cursor: not-allowed !important;
  background: #d9d9d9 !important;
  box-shadow: none !important;
}

.ai-summarize-hint {
  margin-left: 8px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.card-comment-input :deep(.ant-input) {
  font-size: 13px;
  background: hsl(var(--muted) / 30%);
  border-color: hsl(var(--border));
}

.card-comment-input :deep(.ant-input:focus) {
  border-color: hsl(var(--primary));
  box-shadow: 0 0 0 2px hsl(var(--primary) / 10%);
}

.card-comment-input :deep(.ant-input::placeholder) {
  color: hsl(var(--muted-foreground));
}

/* ========== 问题标签 ========== */
.card-issue-tags {
  margin-bottom: 12px;
}

.card-issue-tags-label {
  margin-bottom: 6px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.card-issue-tags :deep(.ant-select) {
  font-size: 13px;
}

.card-issue-tags :deep(.ant-select-selector) {
  min-height: 32px;
  background: hsl(var(--muted) / 30%) !important;
  border-color: hsl(var(--border)) !important;
}

.card-issue-tags :deep(.ant-select-focused .ant-select-selector) {
  border-color: hsl(var(--primary)) !important;
  box-shadow: 0 0 0 2px hsl(var(--primary) / 10%) !important;
}

.card-issue-tags :deep(.ant-select-selection-item) {
  background: hsl(var(--primary) / 15%);
  border-color: hsl(var(--primary) / 30%);
}

.card-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid hsl(var(--border));
}

.card-actions .reviewer-info {
  padding: 2px 10px;
  font-size: 12px;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 10%);
  border-radius: 4px;
}

/* 评论浮窗中的评论者标签 */
.annotation-author-tag {
  padding: 3px 10px;
  font-size: 12px;
  font-weight: 500;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 12%);
  border-radius: 4px;
}

.card-actions .like-btn:hover:not(.is-liked) {
  color: #52c41a;
  border-color: #52c41a;
}

.card-actions .dislike-btn:hover:not(.is-disliked) {
  color: #ff4d4f;
  border-color: #ff4d4f;
}

/* 卡片视图 - 已喜欢按钮 */
.card-actions .like-btn.is-liked {
  color: #fff !important;
  background-color: #52c41a !important;
  border-color: #52c41a !important;
}

.card-actions .like-btn.is-liked:hover {
  color: #fff !important;
  background-color: #73d13d !important;
  border-color: #73d13d !important;
}

/* 卡片视图 - 已不喜欢按钮 */
.card-actions .dislike-btn.is-disliked {
  color: #fff !important;
  background-color: #ff4d4f !important;
  border-color: #ff4d4f !important;
}

.card-actions .dislike-btn.is-disliked:hover {
  color: #fff !important;
  background-color: #ff7875 !important;
  border-color: #ff7875 !important;
}

.shortcut-hint {
  margin-left: 4px;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.card-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 0;
}

/* ========== 卡片内容编辑器 ========== */
.card-content-editor {
  flex-shrink: 0;
  overflow: hidden;
  border-radius: 6px;
}

.card-content-editor :deep(.monaco-editor-container) {
  border: 1px solid hsl(var(--border));
}

.card-content-editor :deep(.monaco-editor) {
  cursor: text;
}

/* ========== 原文内容区域 ========== */
.card-content-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.content-section-header {
  display: flex;
  gap: 6px;
  align-items: center;
}

.section-label {
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

/* ========== 原文精修 ========== */
.card-refine-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.refine-btn {
  color: hsl(var(--primary));
  border-color: hsl(var(--primary) / 50%);
}

.refine-btn:hover:not(:disabled) {
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 10%);
  border-color: hsl(var(--primary));
}

/* ========== 精修内容展示区域 ========== */
.card-refined-content {
  padding: 12px;
  margin-top: 8px;
  background: hsl(var(--success) / 8%);
  border: 1px solid hsl(var(--success) / 30%);
  border-radius: 8px;
}

.refined-content-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 500;
  color: hsl(var(--success));
}

.refined-content-header :deep(.ant-tag) {
  margin: 0;
}

.refined-title {
  display: flex;
  gap: 4px;
  align-items: flex-start;
  padding: 8px 12px;
  margin-bottom: 8px;
  font-size: 13px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
}

.refined-title-label {
  flex-shrink: 0;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
}

.refined-title-text {
  flex: 1;
  color: hsl(var(--foreground));
}

.refined-title-diff {
  flex: 1;
}

.refined-title-diff :deep(.diff-content) {
  padding: 0;
  background: transparent;
}

.refined-content-body {
  overflow: hidden;
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
}

/* ========== 差异显示切换 ========== */
.diff-toggle {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-left: auto;
}

.diff-toggle-label {
  font-size: 12px;
  font-weight: normal;
  color: hsl(var(--muted-foreground));
}

.card-refine-editor {
  padding: 12px;
  background: hsl(var(--muted) / 30%);
  border: 1px solid hsl(var(--primary) / 30%);
  border-radius: 8px;
}

.refine-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 500;
  color: hsl(var(--primary));
}

.refine-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.refine-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.refine-label {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
}

.saving-indicator {
  font-size: 11px;
  font-weight: normal;
  color: hsl(var(--primary));
  animation: pulse 1s ease-in-out infinite;
}

.refine-footer {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: flex-end;
  margin-top: 12px;
}

.refine-hint {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

/* ========== 划选评论高亮 ========== */
:deep(.annotation-highlight) {
  cursor: pointer;
  background-color: hsl(var(--warning) / 30%);
  border-bottom: 2px solid hsl(var(--warning));
  transition: background-color 0.2s;
}

:deep(.annotation-highlight:hover) {
  background-color: hsl(var(--warning) / 50%);
}

/* ========== 统计面板 ========== */

/* ========== 左右两栏布局 ========== */
.card-body-layout {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.card-left {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.card-right {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 12px;
  min-width: 500px;
}

/* 右上：BAN 审核结果 */
.card-ban-result {
  flex-shrink: 0;
  padding: 10px;
  overflow: hidden;
  background: hsl(var(--muted) / 30%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.ban-result-header {
  display: flex;
  gap: 6px;
  align-items: center;
  padding-bottom: 6px;
  margin-bottom: 6px;
  border-bottom: 1px solid hsl(var(--border));
}

.ban-result-header :deep(.ant-tag) {
  margin: 0;
  font-size: 11px;
}

.result-label {
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.ban-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
}

.ban-results-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  align-items: center;
}

.ban-result-item {
  display: inline-flex;
  gap: 2px;
  align-items: center;
  white-space: nowrap;
}

.ban-separator {
  display: none;
}

.ban-label {
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.ban-result-item :deep(.ant-tag) {
  padding: 0 4px;
  margin: 0;
  font-size: 11px;
  line-height: 18px;
}

.ban-tag-hover {
  cursor: pointer;
  transition: opacity 0.2s;
}

.ban-tag-hover:hover {
  opacity: 0.8;
}

/* BAN 理由 Popover */
.ban-reason-popover {
  max-width: 300px;
}

.ban-reason-title {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 6px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.ban-reason-content {
  font-size: 12px;
  line-height: 1.5;
  color: hsl(var(--muted-foreground));
  white-space: pre-wrap;
}

.ban-reason-empty {
  font-size: 12px;
  font-style: italic;
  color: hsl(var(--muted-foreground));
}

/* 审核规则问号图标 */
.ban-rule-icon {
  margin-left: 2px;
  font-size: 12px;
  color: hsl(var(--primary));
  cursor: pointer;
  opacity: 0.7;
  transition: all 0.2s;
}

.ban-rule-icon:hover {
  opacity: 1;
  transform: scale(1.1);
}

.ban-label-colon {
  margin-right: 2px;
}

/* 审核规则 Popover 样式 */
.ban-rule-popover {
  max-width: 380px;
  max-height: 300px;
  overflow-y: auto;
}

.ban-rule-title {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.ban-rule-content {
  font-size: 12px;
  line-height: 1.6;
  color: hsl(var(--muted-foreground));
  overflow-wrap: break-word;
  white-space: pre-wrap;
}

.ban-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
}

/* 右下：评分雷达图 */
.card-score-radar {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 480px;
  padding: 12px;
  background: hsl(var(--muted) / 30%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.radar-header {
  display: flex;
  gap: 2px;
  align-items: center;
  padding-bottom: 8px;
  margin-bottom: 8px;
  border-bottom: 1px solid hsl(var(--border));
}

.radar-label {
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.radar-hint {
  font-size: 10px;
  color: hsl(var(--primary));
  opacity: 0.8;
}

.radar-loading {
  display: flex;
  flex: 1;
  gap: 8px;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.radar-chart-wrapper {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  overflow: visible;
}

.radar-empty {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
}

.empty-text {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

/* ========== 全选提示栏样式 ========== */
.select-all-hint {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 10px 16px;
  margin-bottom: 8px;
  font-size: 13px;
  color: hsl(var(--foreground));
  background: hsl(var(--primary) / 8%);
  border: 1px solid hsl(var(--primary) / 20%);
  border-radius: 6px;
}

.select-all-hint strong {
  font-weight: 600;
  color: hsl(var(--primary));
}

.select-all-hint .hint-icon {
  font-size: 16px;
}

.select-all-hint .hint-icon.success {
  color: hsl(var(--success));
}

.select-all-hint :deep(.ant-btn-link) {
  padding: 0;
  font-size: 13px;
}

/* ========== 导出弹窗样式 ========== */
.export-modal-content {
  max-height: 60vh;
  overflow-y: auto;
}

.export-info {
  display: flex;
  gap: 8px;
  align-items: center;
}

.export-field-groups {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.export-field-group {
  padding: 12px;
  background: hsl(var(--muted) / 30%);
  border-radius: 8px;
}

.group-header {
  margin-bottom: 8px;
  font-weight: 500;
}

.group-title {
  font-size: 14px;
  color: hsl(var(--foreground));
}

.group-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  padding-left: 24px;
}

.field-item {
  display: flex;
  flex-direction: column;
  min-width: 180px;
}

.field-desc {
  padding-left: 24px;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.export-progress {
  padding-top: 8px;
}

.progress-stage {
  margin-bottom: 8px;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

/* ========== AI 评价总结弹窗样式 ========== */
.ai-summary-content {
  padding: 8px 0;
}

.ai-summary-loading {
  display: flex;
  flex-direction: column;
  gap: 16px;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  padding: 24px;
}

.ai-summary-loading .loading-icon {
  font-size: 48px;
  color: hsl(var(--primary));
  animation: pulse 1.5s ease-in-out infinite;
}

.ai-summary-loading .loading-text {
  font-size: 16px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.ai-summary-error {
  padding: 16px 0;
}

.ai-summary-result {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.result-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.result-section-label {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 14px;
}

.result-section-label :deep(.anticon) {
  color: hsl(var(--primary));
}

.ai-summary-footer {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  padding-top: 20px;
  margin-top: 16px;
  border-top: 1px solid hsl(var(--border));
}

/* AI 总结弹窗深色主题适配 */
:deep(.ai-summary-modal .ant-modal-content) {
  background: hsl(var(--background));
}

:deep(.ai-summary-modal .ant-modal-header) {
  background: hsl(var(--background));
  border-bottom: 1px solid hsl(var(--border));
}

:deep(.ai-summary-modal .ant-modal-title) {
  color: hsl(var(--foreground));
}

:deep(.ai-summary-modal .ant-modal-close-x) {
  color: hsl(var(--muted-foreground));
}

:deep(.ai-summary-modal .ant-input),
:deep(.ai-summary-modal .ant-select-selector) {
  background: hsl(var(--muted) / 30%) !important;
  border-color: hsl(var(--border)) !important;
}

:deep(.ai-summary-modal .ant-input:focus),
:deep(.ai-summary-modal .ant-select-focused .ant-select-selector) {
  border-color: hsl(var(--primary)) !important;
  box-shadow: 0 0 0 2px hsl(var(--primary) / 10%) !important;
}

:deep(.ai-summary-modal .ant-input::placeholder) {
  color: hsl(var(--muted-foreground));
}

:deep(.ai-summary-modal .ant-input-textarea-show-count::after) {
  color: hsl(var(--muted-foreground));
}

:deep(.ai-summary-modal .ant-select-selection-item) {
  background: hsl(var(--primary) / 15%);
  border-color: hsl(var(--primary) / 30%);
}

:deep(.ai-summary-modal .ant-progress-text) {
  color: hsl(var(--foreground));
}
</style>
