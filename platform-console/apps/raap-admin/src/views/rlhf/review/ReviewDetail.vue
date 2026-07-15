<script setup lang="ts">
// @ts-nocheck
import type { RLHFApi } from '#/api/core/rlhf';
import type { TraceApi } from '#/api/core/trace';

import { computed, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';

import { useVbenModal } from '@vben/common-ui';
import { usePreferences } from '@vben/preferences';
import { useUserStore } from '@vben/stores';
import { formatDateTime } from '@vben/utils';

import {
  CheckOutlined,
  CloseOutlined,
  DeleteOutlined,
} from '@ant-design/icons-vue';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  DescriptionsItem,
  Divider,
  Empty,
  Input,
  message,
  Popover,
  Select,
  Space,
  Tabs,
  Tag,
  Timeline,
  Tooltip,
} from 'ant-design-vue';

import {
  getIssueTagsApi,
  getRLHFDetailApi,
  getRLHFHistoryApi,
  inspectionContentApi,
  updateContentApi,
} from '#/api/core/rlhf';
import { getGenerationContextApi } from '#/api/core/trace';
import MonacoEditor from '#/components/MonacoEditor.vue';

const emit = defineEmits(['close']);
const router = useRouter();
const userStore = useUserStore();

const { isDark } = usePreferences();
const editorTheme = computed(() => (isDark.value ? 'vs-dark' : 'vs'));

const data = reactive({
  id: 0,
});

const [ModalComponent, modalApi] = useVbenModal({
  onOpenChange(isOpen) {
    if (isOpen) {
      const { id } = modalApi.getData<any>() || {};
      if (id) {
        data.id = id;
        loadData();
      }
    } else {
      resetForm();
    }
  },
});

const loading = ref(false);
const submitting = ref(false);
const detail = ref<RLHFApi.RLHFFeedback>();
const history = ref<any[]>([]);
const genContext = ref<TraceApi.GenerationContextResponse>();

const formState = reactive({
  inspection_result: '' as '' | 'FAILED' | 'PASSED',
  inspection_comment: '',
  issue_tag_names: [] as string[],
});

const allTags = ref<RLHFApi.RLHFIssueTag[]>([]);

const activeTab = ref('inspection');

// --- Expert 执行详情相关 ---
const activeExpertNav = ref<'overview' | number>('overview');

// 获取 Expert 状态图标（根据业务结果判断，与 Job 执行详情保持一致）
const getExpertStatusIcon = (result: TraceApi.ExpertResultSummary) => {
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

// 获取当前选中的 Expert 结果
const currentExpertResult = computed(() => {
  if (
    typeof activeExpertNav.value === 'number' &&
    genContext.value?.expert_results
  ) {
    return genContext.value.expert_results[activeExpertNav.value];
  }
  return null;
});

// BAN 类型审核信息列表（只显示违禁审核，不显示 CRITIC 打分）
interface BanInfo {
  expertCode: string;
  expertName: string;
  reason: string;
  problemSnippets: string[];
}
const banInfoList = computed<BanInfo[]>(() => {
  if (!genContext.value?.expert_results) return [];

  const results: BanInfo[] = [];
  for (const result of genContext.value.expert_results) {
    // 只过滤 BAN 类型的专家
    if (result.business_type?.toUpperCase() !== 'BAN') continue;
    if (!result.business_result) continue;

    const br = result.business_result;
    // 检查是否有问题（score=0 或 passed=0）
    const snippets = br.problem_snippets || br.problem_context_list || [];
    const hasProblems =
      br.score === 0 ||
      br.passed === 0 ||
      (Array.isArray(snippets) && snippets.length > 0);

    if (hasProblems) {
      results.push({
        expertCode: result.expert_config_code,
        expertName: result.expert_config_name || result.expert_config_code,
        reason: br.reason || '',
        problemSnippets: Array.isArray(snippets) ? snippets : [],
      });
    }
  }
  return results;
});

// 收集所有违禁词（用于高亮显示）
const allForbiddenWords = computed<string[]>(() => {
  const words: string[] = [];
  for (const info of banInfoList.value) {
    words.push(...info.problemSnippets);
  }
  // 去重并按长度降序排序（先匹配长词）
  return [...new Set(words)].toSorted((a, b) => b.length - a.length);
});

// 生成高亮后的文章内容 HTML
const highlightedContent = computed<string>(() => {
  const content = detail.value?.content || '';
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

// 导航到指定 Expert
const navigateToExpert = (target: 'overview' | number) => {
  activeExpertNav.value = target;
};

// --- 划词评论相关 ---
const editorRef = ref<any>(null);
const annotations = ref<any[]>([]);
const selectionState = reactive({
  visible: false,
  x: 0,
  y: 0,
  range: null as any,
  text: '',
  comment: '',
  id: null as null | string,
});

function handleEditorMouseUp(e: any) {
  const editor = editorRef.value?.getEditor();
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
      selectionState.x = rect.left + coords.left;
      selectionState.y = rect.top + coords.top + 20;
      selectionState.range = {
        startLineNumber: selection.startLineNumber,
        startColumn: selection.startColumn,
        endLineNumber: selection.endLineNumber,
        endColumn: selection.endColumn,
      };
      selectionState.text = selectedText;
      selectionState.comment = '';
      selectionState.id = null; // 新建
      selectionState.visible = true;
    }
    return;
  }

  // 2. 如果不是划选，检查是否是点击了已有高亮
  const pos = e.target.position;
  if (pos) {
    const found = annotations.value.find((ann) => {
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
        selectionState.id = found.id;
        selectionState.comment = found.comment;
        selectionState.text = found.selected_text;
        selectionState.range = found.range;
        selectionState.x = rect.left + coords.left;
        selectionState.y = rect.top + coords.top + 20;
        selectionState.visible = true;
      }
      return;
    }
  }

  // 3. 既不是划选也不是点击高亮，只有在没有正在输入评论时才隐藏
  if (!selectionState.comment.trim()) {
    selectionState.visible = false;
    selectionState.id = null;
  }
}

function handleCancelAnnotation() {
  selectionState.visible = false;
  selectionState.comment = '';
  selectionState.id = null;
  editorRef.value?.clearSelection();
}

async function saveAnnotation() {
  if (!selectionState.comment.trim() || !detail.value) {
    selectionState.visible = false;
    return;
  }

  let newAnnotations;
  if (selectionState.id) {
    // 更新
    newAnnotations = annotations.value.map((ann) =>
      ann.id === selectionState.id
        ? { ...ann, comment: selectionState.comment }
        : ann,
    );
  } else {
    // 新建
    const currentUserName =
      userStore.userInfo?.realName || userStore.userInfo?.username || '匿名';
    const newAnnotation = {
      id: crypto.randomUUID(),
      range: { ...selectionState.range },
      selected_text: selectionState.text,
      comment: selectionState.comment,
      user_name: currentUserName,
      create_time: new Date().toLocaleString(),
    };
    newAnnotations = [...annotations.value, newAnnotation];
  }

  try {
    await updateContentApi(detail.value.id, {
      annotations: newAnnotations,
    });
    annotations.value = newAnnotations;
    renderAnnotations();
    editorRef.value?.clearSelection(); // 清除蓝色选区
    message.success('评论已保存');
  } catch {
    message.error('保存评论失败');
  } finally {
    selectionState.visible = false;
    selectionState.comment = '';
    selectionState.id = null;
  }
}

async function deleteAnnotation() {
  if (!selectionState.id || !detail.value) return;

  const newAnnotations = annotations.value.filter(
    (ann) => ann.id !== selectionState.id,
  );

  try {
    await updateContentApi(detail.value.id, {
      annotations: newAnnotations,
    });
    annotations.value = newAnnotations;
    renderAnnotations();
    editorRef.value?.clearSelection(); // 清除蓝色选区
    message.success('评论已删除');
  } catch {
    message.error('删除评论失败');
  } finally {
    selectionState.visible = false;
    selectionState.comment = '';
    selectionState.id = null;
  }
}

function renderAnnotations() {
  if (!editorRef.value) return;

  const decorations = annotations.value.map((ann) => ({
    range: ann.range,
    options: {
      inlineClassName: 'annotation-highlight',
      hoverMessage: { value: `评论: ${ann.comment}\nBy: ${ann.user_name}` },
    },
  }));

  editorRef.value.setDecorations(decorations);
}

async function loadData() {
  if (!data.id) return;
  loading.value = true;
  try {
    const [res, historyRes, tagsRes] = await Promise.all([
      getRLHFDetailApi(data.id),
      getRLHFHistoryApi(data.id),
      getIssueTagsApi(),
    ]);

    detail.value = res;
    history.value = historyRes;
    allTags.value = tagsRes;
    annotations.value = res.annotations || [];

    // 初始化抽检结果和意见
    formState.inspection_result = '';
    if (res.review_status === 'INSPECTION_PASSED') {
      formState.inspection_result = 'PASSED';
    } else if (res.review_status === 'INSPECTION_FAILED') {
      formState.inspection_result = 'FAILED';
    }

    // 读取修改意见：优先从 improvement_suggestion 读取（AI 生成的意见）
    // 注意：后端返回的值可能是 null，需要正确处理
    const improvement = res.improvement_suggestion ?? '';
    const inspection = res.inspection_comment ?? '';
    formState.inspection_comment = improvement || inspection;

    // 回填已有标签（通过 ID 找 Name）
    const tagIds = res.issue_tag_ids;
    if (tagIds && Array.isArray(tagIds) && tagIds.length > 0) {
      const tagIdNumbers = new Set(tagIds.map(Number));
      formState.issue_tag_names = tagsRes
        .filter((t) => tagIdNumbers.has(t.id))
        .map((t) => t.tag_name);
    } else {
      formState.issue_tag_names = [];
    }

    // 渲染高亮 (需等编辑器就绪)
    setTimeout(() => {
      renderAnnotations();
    }, 500);

    // 加载生成背景
    if (res.content_id) {
      try {
        genContext.value = await getGenerationContextApi(res.content_id);
      } catch (error) {
        console.error('Failed to load generation context:', error);
      }
    }
  } catch (error: unknown) {
    message.error(error instanceof Error ? error.message : '加载详情失败');
  } finally {
    loading.value = false;
  }
}

function resetForm() {
  detail.value = undefined;
  history.value = [];
  genContext.value = undefined;
  annotations.value = [];
  selectionState.visible = false;
  formState.inspection_result = '';
  formState.inspection_comment = '';
  formState.issue_tag_names = [];
  activeTab.value = 'inspection';
}

async function handleSubmitInspection(result: 'FAILED' | 'PASSED') {
  if (!detail.value) return;

  // 校验逻辑：检查是否有划词评论或精修内容
  const hasAnnotations = annotations.value.length > 0;
  const hasRefined = !!(
    detail.value.modified_content?.trim() &&
    detail.value.modified_content.trim() !== detail.value.content?.trim()
  );

  if (!hasAnnotations && !hasRefined) {
    message.warning('请先添加划词评论或进行原文精修');
    return;
  }

  if (!formState.inspection_comment?.trim()) {
    message.warning('请填写修改意见/问题描述');
    return;
  }

  submitting.value = true;
  try {
    await inspectionContentApi(detail.value.id, {
      result,
      comment: formState.inspection_comment || undefined,
      issue_tag_names: formState.issue_tag_names,
    });
    message.success(result === 'PASSED' ? '抽检通过' : '抽检未通过');
    modalApi.close();
    emit('close', true);
  } catch (error: unknown) {
    message.error(error instanceof Error ? error.message : '提交失败');
  } finally {
    submitting.value = false;
  }
}

function handleGoToDebug() {
  if (!detail.value) return;

  // 构建调试面板参数
  const params: Record<string, string> = {};

  // Expert
  if (detail.value.ge_expert_code) {
    params.expert = detail.value.ge_expert_code;
  }

  // 模型（从 genContext 获取）
  if (genContext.value?.generation?.model_code) {
    params.model = genContext.value.generation.model_code;
  } else if (detail.value.model_code) {
    params.model = detail.value.model_code;
  }

  // 温度（从 genContext 获取，如果有的话）
  // genContext.generation 中可能有 temperature 字段（在 result_summary 中）
  const resultSummary = genContext.value?.generation?.result_summary as any;
  if (resultSummary?.temperature !== undefined) {
    params.temperature = String(resultSummary.temperature);
  }

  // 上下文变量
  if (detail.value.context_list) {
    params.prefill = JSON.stringify(detail.value.context_list);
  }

  // 关闭当前 modal 并跳转
  modalApi.close();
  router.push({
    path: '/expert/debug',
    query: params,
  });
}
</script>

<template>
  <ModalComponent title="抽检详情" class="w-[1400px]">
    <template #footer>
      <Button @click="modalApi.close()">取消</Button>
      <Button
        danger
        :loading="submitting"
        @click="handleSubmitInspection('FAILED')"
      >
        👎 不喜欢
      </Button>
      <Button
        type="primary"
        :loading="submitting"
        @click="handleSubmitInspection('PASSED')"
      >
        👍 喜欢
      </Button>
    </template>

    <div v-if="detail" class="p-4">
      <div class="mb-4 flex items-center justify-between">
        <div class="text-sm text-muted-foreground">
          <span class="mr-4">ID: {{ detail.id }}</span>
          <span class="mr-4">Expert: {{ detail.ge_expert_code }}</span>
          <span>Model: {{ detail.model_code }}</span>
        </div>
        <Tag v-if="detail.review_status === 'INSPECTION_PASSED'" color="green">
          抽检通过
        </Tag>
        <Tag
          v-else-if="detail.review_status === 'INSPECTION_FAILED'"
          color="red"
        >
          抽检未通过
        </Tag>
        <Tag v-else-if="detail.review_status === 'IN_INSPECTION'" color="blue">
          正在抽检
        </Tag>
        <Tag v-else-if="detail.review_status === 'COMPLETED'">待抽检</Tag>
        <Tag v-else-if="detail.review_status === 'IN_PROGRESS'" color="orange">
          审核中
        </Tag>
        <Tag v-else>待审核</Tag>
      </div>

      <Tabs v-model:active-key="activeTab">
        <Tabs.TabPane key="inspection" tab="抽检审核">
          <!-- 上下文变量 -->
          <div
            v-if="
              detail.context_list && Object.keys(detail.context_list).length > 0
            "
            class="mb-6"
          >
            <div class="mb-2 text-base font-bold">📋 上下文变量</div>
            <div class="flex flex-wrap gap-2">
              <Tag
                v-for="(value, key) in detail.context_list"
                :key="key"
                color="blue"
              >
                {{ key }}: {{ value }}
              </Tag>
            </div>
          </div>

          <!-- 原文内容 -->
          <div class="mb-6">
            <div class="mb-2 text-base font-bold">📄 原文内容</div>
            <div
              class="mb-2 flex min-h-[32px] items-center rounded border border-border bg-card px-3 py-2 font-medium"
            >
              {{ detail.title || '无标题' }}
            </div>
            <div class="h-[300px] rounded border border-border bg-card">
              <MonacoEditor
                ref="editorRef"
                :model-value="detail.content || ''"
                language="plaintext"
                height="100%"
                :readonly="true"
                :theme="editorTheme"
                @mouse-up="handleEditorMouseUp"
              />
            </div>
          </div>

          <!-- 精修内容展示（如果有精修内容） -->
          <div v-if="detail.modified_content" class="mb-6">
            <div class="mb-2 flex items-center gap-2">
              <span class="text-base font-bold text-success">✏️ 精修内容</span>
              <Tag color="processing" size="small">已精修</Tag>
            </div>
            <div
              v-if="detail.modified_title"
              class="mb-2 flex min-h-[32px] items-center rounded border border-success/30 bg-success/5 px-3 py-2 font-medium"
            >
              {{ detail.modified_title }}
            </div>
            <div
              class="h-[300px] overflow-hidden rounded border border-success/30 bg-success/5"
            >
              <MonacoEditor
                :model-value="detail.modified_content || ''"
                language="plaintext"
                height="100%"
                :readonly="true"
                :theme="editorTheme"
              />
            </div>
          </div>

          <!-- 划词评论浮窗 -->
          <div
            v-if="selectionState.visible"
            class="fixed z-[2000]"
            :style="{
              left: `${selectionState.x}px`,
              top: `${selectionState.y}px`,
            }"
          >
            <Popover
              v-model:open="selectionState.visible"
              trigger="click"
              placement="bottomRight"
            >
              <template #content>
                <div class="w-72 p-2">
                  <div class="mb-2 flex items-center justify-between">
                    <span class="text-xs font-bold">{{
                      selectionState.id ? '修改评论' : '添加评论'
                    }}</span>
                    <Button
                      type="text"
                      size="small"
                      @click="handleCancelAnnotation"
                    >
                      <template #icon><CloseOutlined /></template>
                    </Button>
                  </div>
                  <div
                    class="mb-2 rounded bg-muted p-1 text-xs text-muted-foreground"
                  >
                    "{{
                      selectionState.text.length > 40
                        ? `${selectionState.text.slice(0, 40)}...`
                        : selectionState.text
                    }}"
                  </div>
                  <Input.TextArea
                    v-model:value="selectionState.comment"
                    :rows="3"
                    auto-focus
                    placeholder="请输入评论内容..."
                  />
                  <div class="mt-3 flex items-center justify-between">
                    <Button
                      v-if="selectionState.id"
                      danger
                      size="small"
                      type="text"
                      @click="deleteAnnotation"
                    >
                      <template #icon><DeleteOutlined /></template>
                      删除
                    </Button>
                    <div v-else></div>

                    <div class="space-x-2">
                      <Button size="small" @click="handleCancelAnnotation">
                        取消
                      </Button>
                      <Button
                        type="primary"
                        size="small"
                        @click="saveAnnotation"
                      >
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

          <!-- 修改意见 -->
          <div class="mb-4">
            <div class="mb-2 text-base font-bold">✏️ 修改意见/问题描述</div>
            <Input.TextArea
              v-model:value="formState.inspection_comment"
              :rows="4"
              placeholder="请输入修改意见或问题描述（必填）"
            />
          </div>

          <!-- 问题标签 -->
          <div class="mb-4">
            <div class="mb-2 text-base font-bold">🏷️ 问题标签</div>
            <Select
              v-model:value="formState.issue_tag_names"
              mode="tags"
              style="width: 100%"
              placeholder="搜索、选择已有标签，或输入新标签按回车自动新增"
              :options="
                allTags.map((t) => ({ label: t.tag_name, value: t.tag_name }))
              "
              allow-clear
              show-search
              :filter-option="true"
            />
          </div>
        </Tabs.TabPane>

        <Tabs.TabPane key="generation" tab="生成背景">
          <div v-if="genContext" class="generation-context-layout">
            <!-- 上半部分：业务信息 + Expert 详情 并列 -->
            <div class="generation-top-row">
              <!-- 左侧：业务信息（纵向单列） -->
              <div class="generation-info-panel">
                <Card size="small" title="业务信息" class="info-card">
                  <div class="info-list">
                    <div class="info-row">
                      <span class="info-label">任务</span>
                      <Tooltip :title="genContext.background.job_name">
                        <span class="info-value">{{
                          genContext.background.job_name
                        }}</span>
                      </Tooltip>
                    </div>
                    <div class="info-row">
                      <span class="info-label">Expert</span>
                      <Tooltip
                        v-if="genContext.generation?.expert_config_code"
                        :title="genContext.generation.expert_config_code"
                      >
                        <Tag color="orange" size="small" class="truncate-tag">
                          {{ genContext.generation.expert_config_code }}
                        </Tag>
                      </Tooltip>
                      <span v-else class="info-value">-</span>
                    </div>
                    <div class="info-row">
                      <span class="info-label">平台</span>
                      <span class="info-value">{{
                        genContext.background.platform_code || '-'
                      }}</span>
                    </div>
                    <div class="info-row">
                      <span class="info-label">耗时</span>
                      <span class="info-value"
                        >{{
                          genContext.generation?.duration_ms || '-'
                        }}
                        ms</span
                      >
                    </div>
                    <div class="info-row">
                      <span class="info-label">Agent</span>
                      <Tooltip :title="genContext.background.agent_code">
                        <Tag color="blue" size="small" class="truncate-tag">
                          {{ genContext.background.agent_code }}
                        </Tag>
                      </Tooltip>
                    </div>
                    <div class="info-row">
                      <span class="info-label">模型</span>
                      <Tooltip
                        :title="genContext.generation?.model_code || '-'"
                      >
                        <span class="info-value font-mono text-xs">{{
                          genContext.generation?.model_code || '-'
                        }}</span>
                      </Tooltip>
                    </div>
                    <div class="info-row">
                      <span class="info-label">Token</span>
                      <span class="info-value">{{
                        genContext.generation?.total_tokens || '-'
                      }}</span>
                    </div>
                    <div class="info-row">
                      <span class="info-label">成本</span>
                      <span class="info-value text-destructive">
                        {{
                          genContext.generation?.currency === 'CNY' ? '¥' : '$'
                        }}
                        {{
                          (
                            Number(genContext.generation?.total_cost) || 0
                          ).toFixed(4)
                        }}
                      </span>
                    </div>
                  </div>

                  <!-- 跳转调试面板按钮 -->
                  <div class="mt-3 border-t border-border pt-3">
                    <Button
                      type="primary"
                      size="small"
                      block
                      @click="handleGoToDebug"
                    >
                      🔧 跳转调试面板
                    </Button>
                  </div>
                </Card>
              </div>

              <!-- 右侧：Expert 执行详情（直接内嵌） -->
              <div class="expert-detail-panel">
                <div
                  v-if="genContext.expert_results"
                  class="expert-detail-layout-inline"
                >
                  <!-- 左侧导航目录 -->
                  <div class="expert-nav-sidebar">
                    <div class="nav-header">
                      <span class="nav-title">Expert 详情</span>
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
                      <div
                        v-if="genContext.expert_results.length > 0"
                        class="nav-section"
                      >
                        <div class="nav-section-title">执行记录</div>
                        <div
                          v-for="(result, idx) in genContext.expert_results"
                          :key="result.id"
                          class="nav-item"
                          :class="{ active: activeExpertNav === idx }"
                          @click="navigateToExpert(idx)"
                        >
                          <span class="nav-icon">{{
                            getExpertStatusIcon(result)
                          }}</span>
                          <span class="nav-text nav-expert-text">{{
                            result.expert_config_name ||
                            result.expert_config_code
                          }}</span>
                        </div>
                      </div>

                      <!-- 无执行记录 -->
                      <div v-else class="nav-empty">暂无执行记录</div>
                    </div>
                  </div>

                  <!-- 右侧详情内容 -->
                  <div class="expert-detail-content">
                    <!-- 总览视图 -->
                    <div
                      v-if="activeExpertNav === 'overview'"
                      class="overview-content"
                    >
                      <!-- 文章基本信息 -->
                      <div v-if="detail" class="article-info-section">
                        <Descriptions
                          :column="1"
                          size="small"
                          bordered
                          :label-style="{
                            width: '100px',
                            whiteSpace: 'nowrap',
                          }"
                        >
                          <DescriptionsItem label="文章标题">
                            {{ detail.title || '(无标题)' }}
                          </DescriptionsItem>
                          <DescriptionsItem label="文章详情">
                            <!-- eslint-disable vue/no-v-html -->
                            <div
                              class="content-with-highlight"
                              v-html="highlightedContent"
                            ></div>
                            <!-- eslint-enable vue/no-v-html -->
                          </DescriptionsItem>
                        </Descriptions>

                        <!-- Content ID 和有效性 -->
                        <Descriptions
                          :column="2"
                          size="small"
                          bordered
                          class="mt-3"
                          :label-style="{
                            width: '100px',
                            whiteSpace: 'nowrap',
                          }"
                        >
                          <DescriptionsItem label="Content ID">
                            <span class="text-xs text-muted-foreground">
                              {{ detail.content_id || '-' }}
                            </span>
                          </DescriptionsItem>
                          <DescriptionsItem label="有效性">
                            <Tag
                              v-if="genContext?.content_is_valid === 1"
                              color="green"
                            >
                              有效
                            </Tag>
                            <Tag
                              v-else-if="genContext?.content_is_valid === 0"
                              color="red"
                            >
                              无效
                            </Tag>
                            <Tag v-else color="default"> 待确定 </Tag>
                          </DescriptionsItem>
                        </Descriptions>
                      </div>

                      <!-- BAN 类型审核信息汇总（只显示违禁审核） -->
                      <Descriptions
                        v-if="banInfoList.length > 0"
                        :column="1"
                        size="small"
                        bordered
                        class="mt-3"
                        :label-style="{
                          width: '160px',
                          whiteSpace: 'nowrap',
                        }"
                      >
                        <template v-for="(info, idx) in banInfoList" :key="idx">
                          <DescriptionsItem
                            :label="`Reason (${info.expertName})`"
                          >
                            <span class="critic-reason">{{
                              info.reason || '-'
                            }}</span>
                          </DescriptionsItem>
                          <DescriptionsItem
                            :label="`违禁词 (${info.expertName})`"
                          >
                            <div
                              v-if="info.problemSnippets.length > 0"
                              class="forbidden-words"
                            >
                              <Tag
                                v-for="word in info.problemSnippets"
                                :key="word"
                                color="red"
                                class="mb-1 mr-1"
                              >
                                {{ word }}
                              </Tag>
                            </div>
                            <span v-else class="text-muted-foreground">-</span>
                          </DescriptionsItem>
                        </template>
                      </Descriptions>

                      <!-- Expert 执行记录汇总 -->
                      <Divider orientation="left" class="!my-3 !text-xs">
                        执行记录 ({{ genContext.expert_results.length }})
                      </Divider>

                      <div
                        v-if="genContext.expert_results.length === 0"
                        class="py-6 text-center text-muted-foreground"
                      >
                        暂无 Expert 执行记录
                      </div>

                      <div v-else class="expert-summary-list">
                        <div
                          v-for="(result, idx) in genContext.expert_results"
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
                            <span
                              v-if="result.expert_config_name"
                              class="summary-name"
                            >
                              {{ result.expert_config_name }}
                            </span>
                          </div>
                          <div class="summary-right">
                            <Tag
                              v-if="result.model_code"
                              color="cyan"
                              size="small"
                            >
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
                    <div
                      v-else-if="currentExpertResult"
                      class="expert-result-content"
                    >
                      <Card size="small" class="expert-result-card">
                        <template #title>
                          <Space>
                            <Tag color="blue">
                              {{ currentExpertResult.expert_config_code }}
                            </Tag>
                            <Tag
                              v-if="currentExpertResult.model_code"
                              color="cyan"
                            >
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
                          <span class="text-xs text-muted-foreground">{{
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
                                height="250px"
                                :minimap="false"
                                :theme="editorTheme"
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
                            typeof activeExpertNav === 'number' &&
                            activeExpertNav > 0
                          "
                          size="small"
                          @click="
                            navigateToExpert((activeExpertNav as number) - 1)
                          "
                        >
                          ← 上一个
                        </Button>
                        <Button
                          type="link"
                          size="small"
                          @click="navigateToExpert('overview')"
                        >
                          返回总览
                        </Button>
                        <Button
                          v-if="
                            typeof activeExpertNav === 'number' &&
                            genContext?.expert_results &&
                            activeExpertNav <
                              genContext.expert_results.length - 1
                          "
                          size="small"
                          @click="
                            navigateToExpert((activeExpertNav as number) + 1)
                          "
                        >
                          下一个 →
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
                <div v-else class="py-10 text-center">
                  <Empty description="暂无 Expert 执行记录" />
                </div>
              </div>
              <!-- 上半部分结束 -->
            </div>

            <!-- 下半部分：渲染后的 Prompt（全宽） -->
            <Card
              v-if="genContext.generation?.rendered_prompt"
              size="small"
              title="渲染后的 Prompt"
              class="prompt-card-fullwidth"
            >
              <template #extra>
                <span class="text-xs text-muted-foreground">LLM 最终输入</span>
              </template>
              <div class="prompt-editor-fullwidth">
                <MonacoEditor
                  :model-value="genContext.generation.rendered_prompt"
                  language="markdown"
                  height="100%"
                  :readonly="true"
                  :theme="editorTheme"
                />
              </div>
            </Card>
          </div>
          <div v-else class="py-20 text-center">
            <Empty description="正在加载生成背景..." />
          </div>
        </Tabs.TabPane>

        <Tabs.TabPane key="history" tab="审核历史">
          <Timeline v-if="history.length > 0" class="mt-4">
            <Timeline.Item v-for="op in history" :key="op.id">
              <div class="font-bold">
                {{ op.operation_type }} - {{ op.operator_name }}
              </div>
              <div class="text-xs text-muted-foreground">
                {{ formatDateTime(op.operation_time) }}
              </div>
              <div v-if="op.reason" class="mt-1">原因: {{ op.reason }}</div>
              <div
                v-if="op.improvement_suggestion"
                class="mt-1 text-destructive"
              >
                建议: {{ op.improvement_suggestion }}
              </div>
            </Timeline.Item>
          </Timeline>
          <Empty v-else description="暂无审核历史" class="py-10" />
        </Tabs.TabPane>
      </Tabs>
    </div>
  </ModalComponent>
</template>

<style scoped>
/* 生成背景标签页布局 */
.generation-context-layout {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: calc(100vh - 320px);
  min-height: 900px;
  padding: 16px;
}

/* 上半部分：业务信息 + Expert 详情 + 审核信息汇总 并列 */
.generation-top-row {
  display: flex;
  flex: 1;
  gap: 12px;
  min-height: 540px;
}

.generation-info-panel {
  flex-shrink: 0;
  width: 200px;
  overflow: hidden;
}

.info-card {
  height: 100%;
}

.info-card :deep(.ant-card-body) {
  padding: 12px;
}

/* 纵向单列布局 */
.info-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.info-row {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  padding: 4px 0;
  overflow: hidden;
  border-bottom: 1px dashed hsl(var(--border));
}

.info-row:last-child {
  border-bottom: none;
}

.info-row > *:last-child {
  display: flex;
  flex: 1;
  justify-content: flex-end;
  min-width: 0;
}

.info-label {
  flex-shrink: 0;
  width: 40px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.info-value {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  font-weight: 500;
  color: hsl(var(--foreground));
  text-align: right;
  white-space: nowrap;
}

.info-row :deep(.ant-tag) {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.truncate-tag {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
  white-space: nowrap;
}

.expert-detail-panel {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

/* 下半部分：渲染后的 Prompt 全宽 */
.prompt-card-fullwidth {
  flex-shrink: 0;
  height: 580px;
}

.prompt-card-fullwidth :deep(.ant-card-body) {
  height: calc(100% - 40px);
  padding: 8px;
}

.prompt-editor-fullwidth {
  height: 100%;
  overflow: hidden;
  border-radius: 4px;
}

/* 内嵌的 Expert 详情布局 */
.expert-detail-layout-inline {
  display: flex;
  gap: 0;
  height: 100%;
}

.expert-nav-sidebar {
  flex-shrink: 0;
  width: 220px;
  overflow-y: auto;
  background: hsl(var(--card));
  border-right: 1px solid hsl(var(--border));
}

.nav-header {
  padding: 16px;
  border-bottom: 1px solid hsl(var(--border));
}

.nav-title {
  font-size: 14px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.nav-list {
  padding: 8px 0;
}

.nav-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 10px 16px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.nav-item:hover {
  background: hsl(var(--primary) / 5%);
}

.nav-item.active {
  background: hsl(var(--primary) / 10%);
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

.content-preview {
  max-height: 80px;
  overflow: hidden;
  line-height: 1.6;
  color: hsl(var(--muted-foreground));
}

.critic-reason {
  color: hsl(var(--destructive));
  word-break: break-all;
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

.expert-name {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.result-json {
  max-height: 300px;
  overflow: hidden;
  border-radius: 6px;
}

.result-prompt {
  max-height: 200px;
  padding: 12px;
  overflow-y: auto;
  font-size: 13px;
  white-space: pre-wrap;
  background: hsl(var(--muted));
  border-radius: 6px;
}

.expert-nav-buttons {
  display: flex;
  gap: 16px;
  justify-content: center;
  padding-top: 16px;
  margin-top: 24px;
  border-top: 1px solid hsl(var(--border));
}

:deep(.annotation-highlight) {
  cursor: pointer;
  background-color: hsl(var(--warning) / 30%);
  border-bottom: 2px solid hsl(var(--warning));
  transition: background-color 0.2s;
}

:deep(.annotation-highlight:hover) {
  background-color: hsl(var(--warning) / 50%);
}

/* 文章信息区域 */
.article-info-section {
  margin-bottom: 12px;
}

/* 文章详情内容（带违禁词高亮） */
.content-with-highlight {
  max-height: 200px;
  overflow-y: auto;
  font-size: 13px;
  line-height: 1.6;
  overflow-wrap: break-word;
  white-space: pre-wrap;
}

/* 违禁词高亮样式 */
:deep(.highlight-forbidden) {
  padding: 1px 4px;
  font-weight: 600;
  color: hsl(var(--destructive));
  background-color: hsl(var(--destructive) / 20%);
  border-radius: 3px;
}

/* 违禁词标签容器 */
.forbidden-words {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
</style>
