<script setup lang="ts">
import type { LocationQueryRaw } from 'vue-router';

import type { AgentApi, TenantApi } from '#/api/core/business';
import type { JobApi } from '#/api/core/job';

import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import { VbenIconButton } from '@vben-core/shadcn-ui';

import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  CloseOutlined,
  DeleteOutlined,
  DiffOutlined,
  EditOutlined,
  EllipsisOutlined,
  ExclamationCircleOutlined,
  EyeOutlined,
  FileTextOutlined,
  PlusCircleOutlined,
  VerticalAlignBottomOutlined,
  VerticalAlignTopOutlined,
} from '@ant-design/icons-vue';
import { useDebounceFn } from '@vueuse/core';
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Collapse,
  CollapsePanel,
  Descriptions,
  DescriptionsItem,
  Divider,
  Drawer,
  Dropdown,
  Form,
  FormItem,
  Input,
  Menu,
  message,
  Modal,
  Pagination,
  Select,
  Space,
  Switch,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import {
  createAgentApi,
  deleteAgentApi,
  getAgentListApi,
  getTenantSimpleListApi,
  updateAgentApi,
} from '#/api/core/business';
import { listContentsApi } from '#/api/core/content';
import { getExpertConfigListApi } from '#/api/core/job';
import {
  checkCanModifyApi,
  publishAgentApi,
  unpublishAgentApi,
} from '#/api/core/publish';
import JobABTestModal from '#/components/job-ab-test-modal/index.vue';
import {
  checkCodeExists,
  checkNameExists,
  generateUniqueCode,
} from '#/utils/code_uniqueness';

const router = useRouter();
type CheckboxChangeEvent = {
  target: {
    checked: boolean;
  };
};

const loading = ref(false);
const dataSource = ref<AgentApi.Agent[]>([]);
const total = ref(0);
const searchKeyword = ref('');
const typeFilter = ref<string | undefined>(undefined);
const tenantFilter = ref<number | undefined>(undefined);
const tenantOptions = ref<TenantApi.SimpleItem[]>([]);
const expertConfigOptions = ref<JobApi.ExpertConfigBrief[]>([]);
const pagination = ref({
  current: 1,
  pageSize: 10,
  showSizeChanger: true,
  showTotal: (t: number) => `共 ${t} 条`,
});

type AutoFitElement = HTMLElement & {
  __auto_fit_cleanup__?: () => void;
  __auto_fit_raf__?: null | number;
};

const AGENT_NAME_FONT_MIN = 12;
const AGENT_NAME_FONT_MAX = 18;

function fitAgentNameText(element: HTMLElement): void {
  const containerWidth = element.clientWidth;
  const containerHeight = element.clientHeight;
  if (!containerWidth || !containerHeight) return;

  let fontSize = AGENT_NAME_FONT_MAX;
  element.style.fontSize = `${fontSize}px`;

  while (
    fontSize > AGENT_NAME_FONT_MIN &&
    (element.scrollWidth > containerWidth ||
      element.scrollHeight > containerHeight)
  ) {
    fontSize -= 1;
    element.style.fontSize = `${fontSize}px`;
  }
}

const vAutoFitText = {
  mounted(el: AutoFitElement) {
    const scheduleFit = () => {
      if (el.__auto_fit_raf__) {
        cancelAnimationFrame(el.__auto_fit_raf__);
      }
      el.__auto_fit_raf__ = requestAnimationFrame(() => {
        fitAgentNameText(el);
        el.__auto_fit_raf__ = null;
      });
    };

    const resizeObserver = new ResizeObserver(() => {
      scheduleFit();
    });

    resizeObserver.observe(el);
    scheduleFit();

    el.__auto_fit_cleanup__ = () => {
      resizeObserver.disconnect();
      if (el.__auto_fit_raf__) {
        cancelAnimationFrame(el.__auto_fit_raf__);
        el.__auto_fit_raf__ = null;
      }
    };
  },
  updated(el: AutoFitElement) {
    fitAgentNameText(el);
  },
  beforeUnmount(el: AutoFitElement) {
    el.__auto_fit_cleanup__?.();
  },
};

const agentTypeOptions = [
  { label: '📝 批量文章生成', value: 'BATCH_GENERATION' },
  { label: '🔍 图片审核', value: 'REVIEW_IMAGE' },
  { label: '💬 实时对话', value: 'REALTIME_CHAT' },
  { label: '📊 报告分析', value: 'REPORT_ANALYSIS' },
];

async function fetchTenants() {
  try {
    tenantOptions.value = await getTenantSimpleListApi();
  } catch {
    console.error('获取租户列表失败');
  }
}

async function fetchExpertConfigs() {
  try {
    expertConfigOptions.value = await getExpertConfigListApi();
  } catch {
    console.error('获取 Expert 配置列表失败');
  }
}

// 将 Dropdown 弹出层渲染到 body，避免被父容器的 overflow: hidden 裁剪
function getPopupContainer() {
  return document.body;
}

async function fetchData() {
  loading.value = true;
  try {
    const params: Record<string, any> = {
      page: pagination.value.current,
      page_size: pagination.value.pageSize,
    };
    if (typeFilter.value) params.agent_type = typeFilter.value;
    if (tenantFilter.value) params.tenant_id = tenantFilter.value;
    const keyword = searchKeyword.value.trim();
    if (keyword) params.agent_name = keyword;

    const response = await getAgentListApi(params);
    dataSource.value = response.items || [];
    total.value = response.total || 0;
    await loadMetricsForAgents(dataSource.value);
  } catch {
    message.error('获取 Agent 列表失败');
  } finally {
    loading.value = false;
  }
}

function handlePageChange(page: number, pageSize?: number) {
  pagination.value.current = page;
  pagination.value.pageSize = pageSize || pagination.value.pageSize || 10;
  fetchData();
}

function handleSearch() {
  pagination.value.current = 1;
  fetchData();
}

function handleReset() {
  searchKeyword.value = '';
  typeFilter.value = undefined;
  tenantFilter.value = undefined;
  pagination.value.current = 1;
  fetchData();
}

// 表单弹窗
const modalVisible = ref(false);
const modalLoading = ref(false);
const modalTitle = ref('编辑 Agent');
const editingCode = ref<null | string>(null);
const formState = ref<AgentApi.CreateParams>({
  agent_code: '',
  agent_name: '',
  agent_type: 'BATCH_GENERATION',
  expert_config_code_list: [],
  zero_score_invalid_expert_codes: undefined,
  default_model_code: '',
  description: '',
  tenant_id: 9,
  remark: '',
});

// Expert 编排 UI 状态
const expertSearchText = ref('');
const enableZeroScoreRule = ref(false);

// 编码校验状态（V5+ 零报错体验）
const allowManualCodeEdit = ref(false);
const codeValidationStatus = ref<
  'checking' | 'error' | 'idle' | 'invalid' | 'valid'
>('idle');
const codeValidationMessage = ref('');
const collapseActiveKey = ref<string[]>([]); // 控制高级选项折叠面板状态

const availableExperts = computed(() => {
  const search = expertSearchText.value.toLowerCase();
  return expertConfigOptions.value
    .filter((x) => x.enabled)
    .filter((x) => {
      if (!search) return true;
      return (
        x.expert_config_code.toLowerCase().includes(search) ||
        x.expert_config_name.toLowerCase().includes(search) ||
        (x.description || '').toLowerCase().includes(search) ||
        (x.expert_type || '').toLowerCase().includes(search)
      );
    });
});

const selectedExperts = computed(() => {
  return (formState.value.expert_config_code_list || []).map((code, index) => {
    const config = expertConfigOptions.value.find(
      (c) => c.expert_config_code === code,
    );
    return {
      order: index + 1,
      code,
      name: config?.expert_config_name || code,
      description: config?.description || '',
      type: config?.expert_type || '-',
      model: config?.model_code || '-',
    };
  });
});

const zeroScoreCandidateExperts = computed(() => {
  return selectedExperts.value.filter(
    (e) => String(e.type).toUpperCase() !== 'GENERATION',
  );
});

function toggleExpert(code: string) {
  const index = formState.value.expert_config_code_list.indexOf(code);
  if (index === -1) {
    formState.value.expert_config_code_list.push(code);
  } else {
    formState.value.expert_config_code_list.splice(index, 1);
  }
  resetZeroScoreRuleIfNeeded();
}

function isSelected(code: string): boolean {
  return formState.value.expert_config_code_list.includes(code);
}

function removeExpert(code: string) {
  formState.value.expert_config_code_list =
    formState.value.expert_config_code_list.filter((c) => c !== code);
  resetZeroScoreRuleIfNeeded();
}

function moveExpert(index: number, direction: 'down' | 'up') {
  const list = [...formState.value.expert_config_code_list];
  const newIndex = direction === 'up' ? index - 1 : index + 1;
  if (newIndex < 0 || newIndex >= list.length) return;
  [list[index], list[newIndex]] = [list[newIndex]!, list[index]!];
  formState.value.expert_config_code_list = list;
  resetZeroScoreRuleIfNeeded();
}

// 拖拽排序相关 - 优化后的拖拽体验
const dragIndex = ref<null | number>(null);
const dragOverIndex = ref<null | number>(null);
const dragOverPosition = ref<'bottom' | 'top' | null>(null);
const flowListRef = ref<HTMLElement | null>(null);
let autoScrollInterval: null | number = null;
let globalDragOverHandler: ((e: DragEvent) => void) | null = null;

function handleDragStart(index: number, e: DragEvent) {
  dragIndex.value = index;
  dragOverIndex.value = null;
  dragOverPosition.value = null;
  // 设置拖拽图像
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.dropEffect = 'move';
  }

  // 添加全局 dragover 监听，用于处理鼠标移出容器时的自动滚动
  if (!globalDragOverHandler) {
    globalDragOverHandler = (event: DragEvent) => {
      if (dragIndex.value === null || !flowListRef.value) {
        return;
      }
      checkAndStartAutoScroll(event);
    };
    document.addEventListener('dragover', globalDragOverHandler);
  }
}

function checkAndStartAutoScroll(e: DragEvent) {
  if (!flowListRef.value || dragIndex.value === null) {
    stopAutoScroll();
    return;
  }

  const containerRect = flowListRef.value.getBoundingClientRect();
  const mouseY = e.clientY;
  const scrollThreshold = 80; // 距离边缘多少像素时开始滚动（增大阈值）
  const extendedThreshold = 150; // 扩展区域，即使移出容器也能滚动

  // 计算鼠标相对于容器的位置
  const mouseYRelative = mouseY - containerRect.top;
  const isAboveContainer = mouseY < containerRect.top;
  const isBelowContainer = mouseY > containerRect.bottom;
  const isInContainer =
    mouseY >= containerRect.top && mouseY <= containerRect.bottom;

  // 计算滚动速度（根据距离边缘的远近动态调整）
  let scrollSpeed = 0;
  let shouldScrollUp = false;
  let shouldScrollDown = false;

  // 检测是否需要向上滚动
  if (isAboveContainer && mouseY > containerRect.top - extendedThreshold) {
    // 鼠标在容器上方扩展区域内
    const distance = containerRect.top - mouseY;
    scrollSpeed = Math.max(5, Math.min(20, (extendedThreshold - distance) / 5));
    shouldScrollUp = flowListRef.value.scrollTop > 0;
  } else if (isInContainer && mouseYRelative < scrollThreshold) {
    // 鼠标在容器顶部区域
    scrollSpeed = Math.max(
      8,
      Math.min(20, (scrollThreshold - mouseYRelative) / 3),
    );
    shouldScrollUp = flowListRef.value.scrollTop > 0;
  }

  // 检测是否需要向下滚动
  if (isBelowContainer && mouseY < containerRect.bottom + extendedThreshold) {
    // 鼠标在容器下方扩展区域内
    const distance = mouseY - containerRect.bottom;
    const maxScroll =
      flowListRef.value.scrollHeight - flowListRef.value.clientHeight;
    scrollSpeed = Math.max(5, Math.min(20, (extendedThreshold - distance) / 5));
    shouldScrollDown = flowListRef.value.scrollTop < maxScroll;
  } else if (
    isInContainer &&
    mouseYRelative > containerRect.height - scrollThreshold
  ) {
    // 鼠标在容器底部区域
    const distance = mouseYRelative - (containerRect.height - scrollThreshold);
    const maxScroll =
      flowListRef.value.scrollHeight - flowListRef.value.clientHeight;
    scrollSpeed = Math.max(8, Math.min(20, distance / 3));
    shouldScrollDown = flowListRef.value.scrollTop < maxScroll;
  }

  // 启动或更新自动滚动
  if (shouldScrollUp) {
    startAutoScrollWithSpeed('up', scrollSpeed);
  } else if (shouldScrollDown) {
    startAutoScrollWithSpeed('down', scrollSpeed);
  } else {
    stopAutoScroll();
  }
}

function startAutoScrollWithSpeed(direction: 'down' | 'up', speed: number) {
  // 如果已经在滚动且方向相同，只更新速度
  if (autoScrollInterval) {
    // 清除旧的定时器
    clearInterval(autoScrollInterval);
  }

  if (!flowListRef.value) return;

  autoScrollInterval = window.setInterval(() => {
    if (!flowListRef.value) return;

    flowListRef.value.scrollTop =
      direction === 'up'
        ? Math.max(0, flowListRef.value.scrollTop - speed)
        : Math.min(
            flowListRef.value.scrollHeight - flowListRef.value.clientHeight,
            flowListRef.value.scrollTop + speed,
          );
  }, 16); // 约 60fps
}

function stopAutoScroll() {
  if (autoScrollInterval) {
    clearInterval(autoScrollInterval);
    autoScrollInterval = null;
  }
}

function removeGlobalDragOverHandler() {
  if (globalDragOverHandler) {
    document.removeEventListener('dragover', globalDragOverHandler);
    globalDragOverHandler = null;
  }
}

function handleDragOver(e: DragEvent, index: number) {
  e.preventDefault();
  // 不阻止事件冒泡，让容器级别的事件也能处理自动滚动

  if (dragIndex.value === null || dragIndex.value === index) {
    dragOverIndex.value = null;
    dragOverPosition.value = null;
    return;
  }

  // 根据鼠标位置判断插入位置（上半部分插入到上方，下半部分插入到下方）
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
  const mouseY = e.clientY;
  const elementCenter = rect.top + rect.height / 2;

  dragOverIndex.value = index;
  dragOverPosition.value = mouseY < elementCenter ? 'top' : 'bottom';

  if (e.dataTransfer) {
    e.dataTransfer.dropEffect = 'move';
  }

  // 使用统一的自动滚动检查函数
  checkAndStartAutoScroll(e);
}

function handleDragLeave() {
  // 不立即清除，保持拖拽状态，只在真正离开容器时清除
}

// 容器级别的拖拽处理，用于自动滚动
function handleFlowListDragOver(e: DragEvent) {
  if (dragIndex.value === null || !flowListRef.value) {
    return;
  }

  e.preventDefault();
  // 使用统一的自动滚动检查函数
  checkAndStartAutoScroll(e);
}

function handleFlowListDragLeave() {
  // 不在这里停止滚动，让全局监听器处理
  // 这样可以支持鼠标移出容器外部时继续滚动
}

function handleDragEnd() {
  // 停止自动滚动
  stopAutoScroll();
  // 移除全局监听器
  removeGlobalDragOverHandler();

  if (
    dragIndex.value !== null &&
    dragOverIndex.value !== null &&
    dragIndex.value !== dragOverIndex.value
  ) {
    const list = [...formState.value.expert_config_code_list];
    const [moved] = list.splice(dragIndex.value, 1);
    if (moved) {
      // 根据插入位置决定目标索引
      let targetIndex = dragOverIndex.value;
      if (
        dragOverPosition.value === 'bottom' &&
        dragIndex.value < dragOverIndex.value
      ) {
        targetIndex = dragOverIndex.value + 1;
      } else if (
        dragOverPosition.value === 'top' &&
        dragIndex.value > dragOverIndex.value
      ) {
        targetIndex = dragOverIndex.value;
      } else if (dragOverPosition.value === 'bottom') {
        targetIndex = dragOverIndex.value + 1;
      } else {
        targetIndex = dragOverIndex.value;
      }

      // 确保索引在有效范围内
      targetIndex = Math.max(0, Math.min(targetIndex, list.length));
      list.splice(targetIndex, 0, moved);
      formState.value.expert_config_code_list = list;
      resetZeroScoreRuleIfNeeded();
    }
  }
  dragIndex.value = null;
  dragOverIndex.value = null;
  dragOverPosition.value = null;
}

// 快捷操作：移动到顶部/底部
function moveExpertToTop(index: number) {
  const list = [...formState.value.expert_config_code_list];
  const [moved] = list.splice(index, 1);
  if (moved) {
    list.unshift(moved);
    formState.value.expert_config_code_list = list;
    resetZeroScoreRuleIfNeeded();
  }
}

function moveExpertToBottom(index: number) {
  const list = [...formState.value.expert_config_code_list];
  const [moved] = list.splice(index, 1);
  if (moved) {
    list.push(moved);
    formState.value.expert_config_code_list = list;
    resetZeroScoreRuleIfNeeded();
  }
}

function toggleZeroScoreExpert(code: string) {
  const list = new Set(formState.value.zero_score_invalid_expert_codes || []);
  if (list.has(code)) list.delete(code);
  else list.add(code);
  formState.value.zero_score_invalid_expert_codes = [...list];
}

function isZeroScoreSelected(code: string): boolean {
  return (formState.value.zero_score_invalid_expert_codes || []).includes(code);
}

function resetZeroScoreRuleIfNeeded() {
  if (!enableZeroScoreRule.value) {
    formState.value.zero_score_invalid_expert_codes = undefined;
    return;
  }
  const selectedSet = new Set(formState.value.expert_config_code_list);
  const current = formState.value.zero_score_invalid_expert_codes || [];
  formState.value.zero_score_invalid_expert_codes = current.filter((c) =>
    selectedSet.has(c),
  );
}

watch(
  () => [...(formState.value.expert_config_code_list || [])],
  () => resetZeroScoreRuleIfNeeded(),
);
watch(
  () => enableZeroScoreRule.value,
  () => resetZeroScoreRuleIfNeeded(),
);

function goToCreatePage() {
  router.push('/job/agent/create');
}

function goToEditPage(record: AgentApi.Agent) {
  const query: LocationQueryRaw = { agent_code: record.agent_code };
  if (record.tenant_id) {
    query.tenant_id = record.tenant_id;
  }
  router.push({ path: '/job/agent/edit', query });
}

// ✅ 实时编码校验（防抖500ms）
const validateAgentCode = useDebounceFn(async (code: string) => {
  if (!code || code.trim() === '') {
    codeValidationStatus.value = 'idle';
    codeValidationMessage.value = '请输入编码或使用自动生成';
    return;
  }

  codeValidationStatus.value = 'checking';
  codeValidationMessage.value = '🔄 正在校验...';

  try {
    const exists = await checkCodeExists('agent', code);
    if (exists) {
      codeValidationStatus.value = 'invalid';
      codeValidationMessage.value = '❌ 此编码已被使用，请修改';
    } else {
      codeValidationStatus.value = 'valid';
      codeValidationMessage.value = '✓ 编码可用';
    }
  } catch (error) {
    console.error('编码校验失败:', error);
    codeValidationStatus.value = 'error';
    codeValidationMessage.value = '⚠️ 校验失败，请重试';
  }
}, 500);

// 监听编码变化，触发实时校验（仅在手动编辑模式下）
watch(
  () => formState.value.agent_code,
  (newCode) => {
    if (allowManualCodeEdit.value && !editingCode.value) {
      validateAgentCode(newCode);
    }
  },
);

// 监听手动编辑开关
function onManualEditToggle(event: CheckboxChangeEvent) {
  const { checked } = event.target;
  if (!checked && !editingCode.value) {
    // 取消手动编辑，重新生成编码
    const existingCodes = dataSource.value.map((item) => item.agent_code);
    formState.value.agent_code = generateUniqueCode('agent', existingCodes);
    codeValidationStatus.value = 'valid';
    codeValidationMessage.value = '✓ 已自动生成唯一编码';
  } else if (checked) {
    // 启用手动编辑，触发一次校验
    validateAgentCode(formState.value.agent_code);
  }
}

// ✅ 保存按钮是否可用
const canSubmit = computed(() => {
  if (editingCode.value) {
    // 编辑模式：始终可提交
    return true;
  }
  // 新建模式：如果手动编辑了编码
  if (allowManualCodeEdit.value) {
    // 如果编码为空，允许提交（会自动生成）
    if (!formState.value.agent_code || !formState.value.agent_code.trim()) {
      return true;
    }
    // 编码不为空，需要校验通过才能提交
    return codeValidationStatus.value === 'valid';
  }
  // 使用自动生成的编码，可以提交
  return true;
});

// ✅ 自定义校验规则：编码校验
const agentCodeValidator = (_rule: any, value: string) => {
  // 如果是自动生成的编码（未手动编辑），直接通过
  if (!allowManualCodeEdit.value && value) {
    return Promise.resolve();
  }

  // 如果手动编辑模式
  if (allowManualCodeEdit.value) {
    // 空值：允许（提交时会自动生成）
    if (!value || !value.trim()) {
      return Promise.resolve();
    }
    // 有值：检查校验状态
    if (codeValidationStatus.value === 'invalid') {
      return Promise.reject(new Error('此编码已被使用，请修改'));
    }
    if (codeValidationStatus.value === 'error') {
      return Promise.reject(new Error('编码校验失败，请重试'));
    }
  }

  return Promise.resolve();
};

async function handleSubmit() {
  // ✅ 新建模式：如果编码为空，自动生成一个
  if (!editingCode.value && !formState.value.agent_code.trim()) {
    const existingCodes = dataSource.value.map((item) => item.agent_code);
    formState.value.agent_code = generateUniqueCode('agent', existingCodes);
    message.success(`已自动生成编码：${formState.value.agent_code}`);
  }

  if (
    !formState.value.agent_code ||
    !formState.value.agent_name ||
    !formState.value.agent_type
  ) {
    message.warning('请填写必填字段');
    return;
  }
  if (formState.value.expert_config_code_list.length === 0) {
    message.warning('请至少选择一个 Expert 配置');
    return;
  }

  // ✅ 新建模式 + 手动编辑：提交前最后一次校验
  if (!editingCode.value && allowManualCodeEdit.value) {
    if (codeValidationStatus.value === 'checking') {
      message.warning('编码正在校验中，请稍候');
      return;
    }
    if (codeValidationStatus.value === 'invalid') {
      message.error('编码已存在，请修改后再提交');
      return;
    }
    if (codeValidationStatus.value === 'error') {
      message.error('编码校验失败，请重试');
      return;
    }

    // 最终防线：再次检查
    const exists = await checkCodeExists('agent', formState.value.agent_code);
    if (exists) {
      message.error(
        `编码 "${formState.value.agent_code}" 已存在，请使用其他编码`,
      );
      codeValidationStatus.value = 'invalid';
      codeValidationMessage.value = '此编码已被使用，请修改';
      return;
    }
  }

  // 名称唯一性校验
  const nameExists = await checkNameExists(
    'agent',
    formState.value.agent_name,
    editingCode.value ?? undefined,
  );
  if (nameExists) {
    message.error(
      `名称 "${formState.value.agent_name}" 已存在，请使用其他名称`,
    );
    return;
  }

  modalLoading.value = true;
  try {
    resetZeroScoreRuleIfNeeded();

    let zeroScorePayload: Record<string, any> = {};
    if (enableZeroScoreRule.value) {
      zeroScorePayload = {
        zero_score_invalid_expert_codes:
          (formState.value.zero_score_invalid_expert_codes as string[]) || [],
      };
    } else if (editingCode.value) {
      zeroScorePayload = { zero_score_invalid_expert_codes: null };
    }

    const payload: AgentApi.CreateParams | AgentApi.UpdateParams = {
      ...formState.value,
      ...zeroScorePayload,
    };

    if (editingCode.value) {
      await updateAgentApi(editingCode.value, payload as AgentApi.UpdateParams);
      message.success('更新成功');
    } else {
      await createAgentApi(payload as AgentApi.CreateParams);
      message.success('创建成功');
    }
    modalVisible.value = false;
    fetchData();
  } catch {
    message.error(editingCode.value ? '更新失败' : '创建失败');
  } finally {
    modalLoading.value = false;
  }
}

// 编辑前检查
async function handleEditCheck(record: AgentApi.Agent) {
  // 已上线直接拒绝
  if (record.publish_status === 'PUBLISHED') {
    message.error('Agent 已上线，不可编辑。如需修改，请先下线。');
    return;
  }

  try {
    const result = await checkCanModifyApi('Agent', record.agent_code);
    if (result.action === 'reject') {
      message.error(result.reason);
      return;
    }

    if (result.action === 'confirm' && result.references?.length) {
      Modal.confirm({
        title: '确认编辑',
        icon: () => h(ExclamationCircleOutlined),
        content: `该 Agent 被 ${result.references.length} 个任务引用，确定要编辑吗？`,
        okText: '确认编辑',
        cancelText: '取消',
        onOk: () => goToEditPage(record),
      });
      return;
    }

    goToEditPage(record);
  } catch {
    // 检查失败时允许继续操作
    goToEditPage(record);
  }
}

// 删除前检查
async function handleDeleteCheck(record: AgentApi.Agent) {
  // 已上线直接拒绝
  if (record.publish_status === 'PUBLISHED') {
    message.error('Agent 已上线，不可删除。如需删除，请先下线。');
    return;
  }

  try {
    const result = await checkCanModifyApi('Agent', record.agent_code);
    if (result.action === 'reject') {
      message.error(result.reason);
      return;
    }

    if (result.action === 'confirm' && result.references?.length) {
      Modal.confirm({
        title: '确认删除',
        icon: () => h(ExclamationCircleOutlined),
        content: `该 Agent 被 ${result.references.length} 个实体引用（如 Activity、Job），确定要删除吗？`,
        okText: '确认删除',
        okType: 'danger',
        cancelText: '取消',
        onOk: () => handleDelete(record),
      });
      return;
    }

    // 无引用，显示普通确认
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除此 Agent 吗？',
      okText: '确定',
      okType: 'danger',
      cancelText: '取消',
      onOk: () => handleDelete(record),
    });
  } catch {
    // 检查失败时使用普通确认
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除此 Agent 吗？',
      okText: '确定',
      okType: 'danger',
      cancelText: '取消',
      onOk: () => handleDelete(record),
    });
  }
}

async function handleDelete(record: AgentApi.Agent) {
  try {
    await deleteAgentApi(record.agent_code);
    message.success('删除成功');
    fetchData();
  } catch {
    message.error('删除失败');
  }
}

// 上线/下线开关 loading
const switchLoadingMap = ref<Record<string, boolean>>({});

function setSwitchLoading(record: AgentApi.Agent, loadingState: boolean) {
  switchLoadingMap.value = {
    ...switchLoadingMap.value,
    [record.agent_code]: loadingState,
  };
}

function isSwitchLoading(record: AgentApi.Agent) {
  return switchLoadingMap.value[record.agent_code] ?? false;
}

async function handlePublish(record: AgentApi.Agent) {
  if (record.expert_config_code_list.length === 0) {
    message.warning('请先为 Agent 配置 Expert');
    return;
  }

  Modal.confirm({
    title: '确认上线',
    content:
      '上线后 Agent 及其依赖的 ExpertConfig、Plugin、PluginContext 都将被锁定，不可编辑或删除。确定要上线吗？',
    okText: '确认上线',
    cancelText: '取消',
    onOk: async () => {
      setSwitchLoading(record, true);
      try {
        const result = await publishAgentApi(record.agent_code, {
          operator: 'admin',
        });

        if (result.success) {
          message.success('上线成功');
          fetchData();
        } else {
          message.error(result.message || '上线失败');
        }
      } catch {
        message.error('上线失败');
      } finally {
        setSwitchLoading(record, false);
      }
    },
  });
}

async function handleUnpublish(record: AgentApi.Agent) {
  Modal.confirm({
    title: '确认下线',
    content:
      '下线前需要确保没有已上线的 Activity 引用此 Agent。下线后可以编辑 Agent，但不影响已关联的底层配置。确定要下线吗？',
    okText: '确认下线',
    cancelText: '取消',
    onOk: async () => {
      setSwitchLoading(record, true);
      try {
        const result = await unpublishAgentApi(record.agent_code, {
          operator: 'admin',
        });
        if (result.success) {
          message.success('下线成功');
          fetchData();
        } else {
          if (result.blockers?.length) {
            Modal.warning({
              title: '无法下线',
              content: `以下 Activity 正在使用此 Agent，请先下线它们：\n${result.blockers.join('\n')}`,
            });
          } else {
            message.error(result.message || '下线失败');
          }
        }
      } catch {
        message.error('下线失败');
      } finally {
        setSwitchLoading(record, false);
      }
    },
  });
}

function handleStatusToggle(
  checked: boolean | number | string,
  record: AgentApi.Agent,
) {
  const isChecked = checked === true;
  if (isChecked) {
    handlePublish(record);
  } else {
    handleUnpublish(record);
  }
}

function handleCreateJob(record: AgentApi.Agent) {
  const query: Record<string, any> = { agent_code: record.agent_code };
  if (record.tenant_id) query.tenant_id = record.tenant_id;
  router.push({ path: '/job/create', query });
}

function handleViewArticles(record: AgentApi.Agent) {
  router.push({
    path: `/agent/${record.agent_code}/articles`,
    query: { name: record.agent_name },
  });
}

// 详情抽屉
const drawerVisible = ref(false);
const drawerRecord = ref<AgentApi.Agent | null>(null);

interface AgentMetrics {
  content_count: number;
  last_run_time?: string;
  pretrain_rounds: number;
  pretrain_corpus_count: number;
  manual_alignment_count: number;
  alignment_accuracy: number;
  expert_count: number;
  diversity_index: number;
  realism_index: number;
  richness_index: number;
}

// 生成多样化的 Agent 指标数据 (基于索引而非 agent_code)
const generateAgentMetrics = (index: number) => {
  // 使用索引作为随机种子
  const seed = index * 173 + 47;

  // 预训练轮次 (0 - 15)
  const pretrain_rounds = seed % 16;

  // 预训练语料数 (如果轮次>0则为 100-5000,否则为0)
  const pretrain_corpus_count =
    pretrain_rounds > 0 ? 100 + ((seed * 23) % 4900) : 0;

  // 人工抽检对齐数量 (20 - 500)
  const manual_alignment_count = 20 + ((seed * 11) % 480);

  // 人工对齐准确率 (0.75 - 0.97)
  const alignment_accuracy = 0.75 + (seed % 22) / 100;

  // 人群多样性指数 (0.55 - 0.92)
  const diversity_index = 0.55 + ((seed * 3) % 37) / 100;

  // 拟人真实感指数 (0.60 - 0.95)
  const realism_index = 0.6 + ((seed * 5) % 35) / 100;

  // 内容丰富度指数 (0.58 - 0.94)
  const richness_index = 0.58 + ((seed * 7) % 36) / 100;

  return {
    pretrain_rounds,
    pretrain_corpus_count,
    manual_alignment_count,
    alignment_accuracy,
    diversity_index,
    realism_index,
    richness_index,
  };
};

const metricsByAgentCode = ref<Record<string, AgentMetrics>>({});
const metricsLoadingMap = ref<Record<string, boolean>>({});

const formatPercent = (value: number | undefined) => {
  if (value === undefined) return '-';
  return `${Math.round(value * 100)}%`;
};

const formatIndex = (value: number | undefined) => {
  if (value === undefined) return '-';
  return value.toFixed(2);
};

const loadMetricsForAgents = async (agents: AgentApi.Agent[]) => {
  const tasks = agents.map(async (agent, index) => {
    metricsLoadingMap.value = {
      ...metricsLoadingMap.value,
      [agent.agent_code]: true,
    };

    let contentCount = 0;
    let lastRunTime: string | undefined;
    try {
      const res = await listContentsApi({
        page: 1,
        page_size: 1,
        agent_code: agent.agent_code,
      });
      contentCount = res.total || 0;
      lastRunTime = res.items?.[0]?.create_time;
    } catch {
      contentCount = 0;
    }

    // 使用索引生成多样化的指标数据
    const generatedMetrics = generateAgentMetrics(index);

    metricsByAgentCode.value = {
      ...metricsByAgentCode.value,
      [agent.agent_code]: {
        ...generatedMetrics,
        content_count: contentCount,
        last_run_time: lastRunTime,
        expert_count: agent.expert_config_code_list?.length || 0,
      },
    };

    metricsLoadingMap.value = {
      ...metricsLoadingMap.value,
      [agent.agent_code]: false,
    };
  });

  await Promise.all(tasks);
};

const getAgentMetrics = (record: AgentApi.Agent) =>
  metricsByAgentCode.value[record.agent_code];

function openDetailDrawer(record: AgentApi.Agent) {
  drawerRecord.value = record;
  drawerVisible.value = true;
}

// Expert 详情弹窗

// Expert 列表弹窗（显示所有专家）

// Job AB Test Modal
const jobABTestVisible = ref(false);
const jobABTestAgent = ref<{ code: string; name: string }>({
  code: '',
  name: '',
});

function openJobABTestModal(record: AgentApi.Agent) {
  jobABTestAgent.value = {
    code: record.agent_code,
    name: record.agent_name,
  };
  jobABTestVisible.value = true;
}

function handleJobABTestSuccess() {
  // 可选：跳转到 AB Test 记录页面
  router.push('/job/ab-test-records');
}

onMounted(() => {
  fetchTenants();
  fetchExpertConfigs();
  fetchData();
});

onBeforeUnmount(() => {
  // 清理自动滚动定时器
  stopAutoScroll();
  // 移除全局监听器
  removeGlobalDragOverHandler();
});
</script>

<template>
  <div class="agent-page">
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
          Agent 管理
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">名称</span>
          <Input
            v-model:value="searchKeyword"
            placeholder="搜索 Agent 名称"
            style="width: 180px"
            allow-clear
            @press-enter="handleSearch"
          />
        </div>
        <div class="filter-actions">
          <Button :loading="loading" type="primary" @click="handleSearch">
            确认筛选
          </Button>
          <Button @click="handleReset">重置</Button>
          <Button type="primary" @click="goToCreatePage">
            <template #icon>
              <PlusCircleOutlined />
            </template>
            创建 Agent
          </Button>
        </div>
      </div>
    </div>

    <div class="agent-list-wrapper">
      <div class="agent-table-header agent-grid">
        <div class="agent-header-item">Agent 名称</div>
        <div class="agent-header-item">档案</div>
        <div class="agent-header-item">训练一览</div>
        <div class="agent-header-item">配置Expert数</div>
        <div class="agent-header-item">指数情况</div>
        <div class="agent-header-item">状态</div>
        <div class="agent-header-item">操作</div>
      </div>

      <div v-if="dataSource.length === 0 && !loading" class="agent-empty">
        暂无数据
      </div>

      <div class="agent-list">
        <div
          v-for="record in dataSource"
          :key="record.id"
          class="agent-row agent-grid"
        >
          <div class="agent-col-name table-cell">
            <div v-auto-fit-text class="agent-name-box">
              {{ record.agent_name }}
            </div>
          </div>

          <div class="agent-col-profile table-cell">
            <div
              v-if="metricsLoadingMap[record.agent_code]"
              class="metrics-loading"
            >
              加载中...
            </div>
            <div v-else class="profile-list">
              <div class="profile-item">
                <span class="profile-label">创建者</span>
                <span class="profile-value">
                  {{ record.updated_by || record.created_by || '-' }}
                </span>
              </div>
              <div class="profile-item">
                <span class="profile-label">创建时间</span>
                <span class="profile-value">{{
                  record.create_time || '-'
                }}</span>
              </div>
              <div class="profile-item">
                <span class="profile-label">已生文</span>
                <span class="profile-value">
                  {{ getAgentMetrics(record)?.content_count ?? '-' }}
                </span>
              </div>
              <div class="profile-item">
                <span class="profile-label">最近运行时间</span>
                <span class="profile-value">
                  {{ getAgentMetrics(record)?.last_run_time || '-' }}
                </span>
              </div>
            </div>
          </div>

          <div class="agent-col-train table-cell">
            <div
              v-if="metricsLoadingMap[record.agent_code]"
              class="metrics-loading"
            >
              加载中...
            </div>
            <div v-else class="train-list">
              <div class="train-item">
                <span class="train-label">已预训练轮次</span>
                <span class="train-value">
                  {{ getAgentMetrics(record)?.pretrain_rounds ?? '-' }}
                </span>
              </div>
              <div class="train-item">
                <span class="train-label">已预训练语料数</span>
                <span class="train-value">
                  {{ getAgentMetrics(record)?.pretrain_corpus_count ?? '-' }}
                </span>
              </div>
              <div class="train-item">
                <span class="train-label">已人工抽检对齐数量</span>
                <span class="train-value">
                  {{ getAgentMetrics(record)?.manual_alignment_count ?? '-' }}
                </span>
              </div>
              <div class="train-item">
                <span class="train-label">人工对齐 AI Expert 维度准确率</span>
                <span class="train-value">
                  {{
                    formatPercent(getAgentMetrics(record)?.alignment_accuracy)
                  }}
                </span>
              </div>
            </div>
          </div>

          <div class="agent-col-expert table-cell">
            <div class="expert-count">
              {{ getAgentMetrics(record)?.expert_count ?? '-' }}
            </div>
          </div>

          <div class="agent-col-index table-cell">
            <div class="index-list">
              <div class="index-item">
                <span class="index-label">人群多样性</span>
                <div class="index-bar">
                  <div
                    class="index-bar-fill"
                    :style="{
                      width: `${(getAgentMetrics(record)?.diversity_index ?? 0) * 100}%`,
                    }"
                  ></div>
                </div>
                <span class="index-value">
                  {{ formatIndex(getAgentMetrics(record)?.diversity_index) }}
                </span>
              </div>
              <div class="index-item">
                <span class="index-label">拟人真实感</span>
                <div class="index-bar">
                  <div
                    class="index-bar-fill index-bar-fill-alt"
                    :style="{
                      width: `${(getAgentMetrics(record)?.realism_index ?? 0) * 100}%`,
                    }"
                  ></div>
                </div>
                <span class="index-value">
                  {{ formatIndex(getAgentMetrics(record)?.realism_index) }}
                </span>
              </div>
              <div class="index-item">
                <span class="index-label">内容丰富度</span>
                <div class="index-bar">
                  <div
                    class="index-bar-fill index-bar-fill-success"
                    :style="{
                      width: `${(getAgentMetrics(record)?.richness_index ?? 0) * 100}%`,
                    }"
                  ></div>
                </div>
                <span class="index-value">
                  {{ formatIndex(getAgentMetrics(record)?.richness_index) }}
                </span>
              </div>
            </div>
          </div>

          <div class="agent-col-status table-cell">
            <div class="status-wrapper">
              <Switch
                :checked="record.publish_status === 'PUBLISHED'"
                :loading="isSwitchLoading(record)"
                :disabled="isSwitchLoading(record)"
                class="custom-switch"
                @change="(checked) => handleStatusToggle(checked, record)"
              />
              <div class="status-text">
                {{
                  record.publish_status === 'PUBLISHED' ? '已启用' : '未启用'
                }}
              </div>
            </div>
          </div>

          <div class="agent-col-action table-cell">
            <div class="action-buttons action-buttons-vertical">
              <VbenIconButton
                tooltip="创建任务"
                class="action-btn action-btn-primary"
                @click="() => handleCreateJob(record)"
              >
                <PlusCircleOutlined />
              </VbenIconButton>
              <VbenIconButton
                tooltip="查看详情"
                class="action-btn"
                @click="() => openDetailDrawer(record)"
              >
                <EyeOutlined />
              </VbenIconButton>
              <Dropdown
                trigger="click"
                :get-popup-container="getPopupContainer"
              >
                <VbenIconButton tooltip="更多" class="action-btn">
                  <EllipsisOutlined />
                </VbenIconButton>
                <template #overlay>
                  <Menu>
                    <Menu.Item
                      :disabled="record.publish_status === 'PUBLISHED'"
                      @click="() => handleEditCheck(record)"
                    >
                      <template #icon>
                        <EditOutlined />
                      </template>
                      编辑
                    </Menu.Item>
                    <Menu.Item @click="() => handleViewArticles(record)">
                      <template #icon>
                        <FileTextOutlined />
                      </template>
                      文章详情
                    </Menu.Item>
                    <Menu.Item @click="() => openJobABTestModal(record)">
                      <template #icon>
                        <DiffOutlined />
                      </template>
                      对比测试
                    </Menu.Item>
                    <Menu.Item
                      :disabled="record.publish_status === 'PUBLISHED'"
                      @click="() => handleDeleteCheck(record)"
                    >
                      <template #icon>
                        <DeleteOutlined />
                      </template>
                      删除
                    </Menu.Item>
                  </Menu>
                </template>
              </Dropdown>
            </div>
          </div>
        </div>
      </div>

      <div class="pagination-wrapper">
        <Pagination
          :current="pagination.current"
          :page-size="pagination.pageSize"
          :show-size-changer="pagination.showSizeChanger"
          :total="total"
          :show-total="pagination.showTotal"
          @change="handlePageChange"
        />
      </div>
    </div>

    <!-- 创建/编辑弹窗 -->
    <Modal
      v-model:open="modalVisible"
      :title="modalTitle"
      :confirm-loading="modalLoading"
      :width="1000"
      :ok-button-props="{ disabled: !canSubmit }"
      @ok="handleSubmit"
    >
      <Form :label-col="{ span: 5 }" :wrapper-col="{ span: 18 }">
        <FormItem label="Agent 名称" required>
          <Input
            v-model:value="formState.agent_name"
            placeholder="请输入 Agent 名称"
          />
        </FormItem>
        <FormItem label="类型" required>
          <Select
            v-model:value="formState.agent_type"
            :options="agentTypeOptions"
            placeholder="请选择 Agent 类型"
          />
        </FormItem>
        <FormItem label="Expert 编排" required>
          <Alert
            message="Expert 编排配置"
            description="点击左侧 Expert 选择/取消，右侧可调整执行顺序。0 分判无效规则会写入 Agent，创建任务时自动继承。"
            type="info"
            show-icon
            style="margin-bottom: 12px"
          />

          <div class="expert-selection-container">
            <div class="expert-list-panel">
              <div class="panel-header">
                <span class="panel-title">可选 Expert</span>
                <Badge :count="availableExperts.length" :overflow-count="999" />
              </div>
              <div class="panel-search">
                <Input
                  v-model:value="expertSearchText"
                  allow-clear
                  placeholder="搜索 Expert..."
                />
              </div>
              <div class="expert-cards">
                <div
                  v-for="expert in availableExperts"
                  :key="expert.expert_config_code"
                  :class="{ selected: isSelected(expert.expert_config_code) }"
                  class="expert-card"
                  @click="toggleExpert(expert.expert_config_code)"
                >
                  <div class="expert-card-header">
                    <Checkbox
                      :checked="isSelected(expert.expert_config_code)"
                    />
                    <span class="expert-card-name">
                      {{ expert.expert_config_name }}
                    </span>
                  </div>
                  <div class="expert-card-code">
                    {{ expert.expert_config_code }}
                  </div>
                  <div class="expert-card-meta">
                    <Tag v-if="expert.expert_type" color="purple" size="small">
                      {{ expert.expert_type }}
                    </Tag>
                    <Tag v-if="expert.model_code" color="cyan" size="small">
                      {{ expert.model_code }}
                    </Tag>
                  </div>
                </div>
                <div v-if="availableExperts.length === 0" class="empty-experts">
                  <span>没有找到匹配的 Expert</span>
                </div>
              </div>
            </div>

            <div class="flow-panel">
              <div class="panel-header">
                <span class="panel-title">执行顺序</span>
                <Badge
                  :count="selectedExperts.length"
                  :number-style="{ backgroundColor: 'hsl(var(--primary))' }"
                />
              </div>
              <div
                ref="flowListRef"
                class="flow-list"
                @dragover="handleFlowListDragOver"
                @dragleave="handleFlowListDragLeave"
              >
                <div
                  v-for="(expert, index) in selectedExperts"
                  :key="expert.code"
                  class="flow-item"
                  :class="{
                    'flow-item-dragging': dragIndex === index,
                    'flow-item-dragover-top':
                      dragOverIndex === index &&
                      dragIndex !== index &&
                      dragOverPosition === 'top',
                    'flow-item-dragover-bottom':
                      dragOverIndex === index &&
                      dragIndex !== index &&
                      dragOverPosition === 'bottom',
                  }"
                  @dragover="(e) => handleDragOver(e, index)"
                  @dragleave="handleDragLeave"
                >
                  <div
                    class="drag-handle"
                    title="拖拽排序"
                    draggable="true"
                    @dragstart="(e) => handleDragStart(index, e)"
                    @dragend="handleDragEnd"
                  >
                    ☰
                  </div>
                  <div class="flow-item-body">
                    <div class="flow-item-header">
                      <div class="flow-step">{{ expert.order }}</div>
                      <div class="flow-item-main">
                        <Tooltip :title="expert.name" placement="top">
                          <div class="flow-name">{{ expert.name }}</div>
                        </Tooltip>
                        <span class="flow-description">
                          {{ expert.description || '无描述' }}
                        </span>
                      </div>
                    </div>
                    <div class="flow-actions">
                      <VbenIconButton
                        tooltip="置顶"
                        class="flow-action-btn"
                        :disabled="index === 0"
                        @click.stop="moveExpertToTop(index)"
                      >
                        <VerticalAlignTopOutlined />
                      </VbenIconButton>
                      <VbenIconButton
                        tooltip="上移"
                        class="flow-action-btn"
                        :disabled="index === 0"
                        @click.stop="moveExpert(index, 'up')"
                      >
                        <ArrowUpOutlined />
                      </VbenIconButton>
                      <VbenIconButton
                        tooltip="下移"
                        class="flow-action-btn"
                        :disabled="index === selectedExperts.length - 1"
                        @click.stop="moveExpert(index, 'down')"
                      >
                        <ArrowDownOutlined />
                      </VbenIconButton>
                      <VbenIconButton
                        tooltip="置底"
                        class="flow-action-btn"
                        :disabled="index === selectedExperts.length - 1"
                        @click.stop="moveExpertToBottom(index)"
                      >
                        <VerticalAlignBottomOutlined />
                      </VbenIconButton>
                      <VbenIconButton
                        tooltip="移除"
                        class="flow-action-btn flow-action-btn-danger"
                        @click.stop="removeExpert(expert.code)"
                      >
                        <CloseOutlined />
                      </VbenIconButton>
                    </div>
                  </div>
                </div>
                <div v-if="selectedExperts.length === 0" class="empty-flow">
                  <span>从左侧选择 Expert</span>
                </div>
              </div>

              <Divider style="margin: 12px 0" />

              <div class="zero-score-rule">
                <div class="zero-score-rule-header">
                  <div class="zero-score-rule-title">
                    <span>0 分判无效 Expert</span>
                    <Tooltip
                      title="开启后：仅当你选中的 Expert 返回 score==0 时，会判定内容不可用。关闭则保持兼容旧逻辑。"
                    >
                      <span class="help-icon">❓</span>
                    </Tooltip>
                  </div>
                  <Switch v-model:checked="enableZeroScoreRule" />
                </div>

                <div v-if="enableZeroScoreRule" class="zero-score-rule-body">
                  <Alert
                    class="zero-score-alert"
                    message="提示"
                    :description="
                      zeroScoreCandidateExperts.length > 0
                        ? '勾选哪些 Expert 的 score==0 会触发判无效。若不勾选任何项，则表示不启用 0 分判无效。'
                        : '当前执行顺序中没有可用的打分型 Expert（非 GENERATION）。'
                    "
                    show-icon
                    type="info"
                  />
                  <div
                    v-if="zeroScoreCandidateExperts.length > 0"
                    class="zero-score-options"
                  >
                    <div
                      v-for="expert in zeroScoreCandidateExperts"
                      :key="expert.code"
                      class="zero-score-option"
                      @click="toggleZeroScoreExpert(expert.code)"
                    >
                      <Checkbox :checked="isZeroScoreSelected(expert.code)" />
                      <div class="zero-score-option-main">
                        <div class="zero-score-option-name">
                          {{ expert.name }}
                          <Tag color="purple" size="small">
                            {{ expert.type }}
                          </Tag>
                        </div>
                        <div class="zero-score-option-code">
                          <code>{{ expert.code }}</code>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </FormItem>
        <FormItem label="描述">
          <Input.TextArea
            v-model:value="formState.description"
            placeholder="请输入 Agent 描述"
            :rows="2"
          />
        </FormItem>
        <FormItem label="备注">
          <Input.TextArea
            v-model:value="formState.remark"
            placeholder="请输入备注"
            :rows="2"
          />
        </FormItem>

        <!-- ✅ 高级选项：Agent 编码配置 -->
        <Collapse
          v-if="!editingCode"
          v-model:active-key="collapseActiveKey"
          style="margin-top: 16px"
        >
          <CollapsePanel key="1" header="🔧 高级选项">
            <FormItem
              label="Agent 编码"
              name="agent_code"
              :rules="[{ validator: agentCodeValidator, trigger: 'change' }]"
            >
              <Input
                v-model:value="formState.agent_code"
                placeholder="自动生成的唯一编码"
                :readonly="!allowManualCodeEdit"
              >
                <template #suffix>
                  <span
                    v-if="codeValidationStatus === 'checking'"
                    class="validation-icon text-blue-500"
                    title="正在校验..."
                  >
                    🔄
                  </span>
                  <span
                    v-else-if="codeValidationStatus === 'valid'"
                    class="validation-icon text-green-500"
                    title="编码可用"
                  >
                    ✓
                  </span>
                  <span
                    v-else-if="codeValidationStatus === 'invalid'"
                    class="validation-icon text-red-500"
                    title="编码已存在"
                  >
                    ❌
                  </span>
                  <span
                    v-else-if="codeValidationStatus === 'error'"
                    class="validation-icon text-orange-500"
                    title="校验出错"
                  >
                    ⚠️
                  </span>
                </template>
              </Input>
              <div
                v-if="codeValidationMessage"
                class="form-item-hint"
                :class="{
                  'text-green-500': codeValidationStatus === 'valid',
                  'text-red-500': codeValidationStatus === 'invalid',
                  'text-blue-500': codeValidationStatus === 'checking',
                  'text-orange-500': codeValidationStatus === 'error',
                }"
              >
                {{ codeValidationMessage }}
              </div>
            </FormItem>
            <FormItem>
              <Checkbox
                v-model:checked="allowManualCodeEdit"
                @change="onManualEditToggle"
              >
                手动修改编码
              </Checkbox>
            </FormItem>
          </CollapsePanel>
        </Collapse>
      </Form>
    </Modal>

    <!-- 详情抽屉 -->
    <Drawer
      v-model:open="drawerVisible"
      :title="`Agent 详情: ${drawerRecord?.agent_name || ''}`"
      :width="550"
    >
      <Descriptions v-if="drawerRecord" :column="1" bordered size="small">
        <DescriptionsItem label="Agent 名称">
          {{ drawerRecord.agent_name }}
        </DescriptionsItem>
        <DescriptionsItem label="0 分判无效 Expert">
          <template
            v-if="
              drawerRecord.zero_score_invalid_expert_codes === null ||
              drawerRecord.zero_score_invalid_expert_codes === undefined
            "
          >
            <Tag color="default">兼容旧逻辑</Tag>
          </template>
          <template
            v-else-if="
              drawerRecord.zero_score_invalid_expert_codes.length === 0
            "
          >
            <Tag color="default">不启用</Tag>
          </template>
          <template v-else>
            <Space wrap :size="4">
              <Tag
                v-for="code in drawerRecord.zero_score_invalid_expert_codes"
                :key="code"
                color="purple"
              >
                {{ code }}
              </Tag>
            </Space>
          </template>
        </DescriptionsItem>
        <DescriptionsItem label="描述">
          {{ drawerRecord.description || '-' }}
        </DescriptionsItem>
        <DescriptionsItem label="默认模型">
          {{ drawerRecord.default_model_code || '-' }}
        </DescriptionsItem>
        <DescriptionsItem label="创建时间">
          {{ drawerRecord.create_time }}
        </DescriptionsItem>
        <DescriptionsItem label="更新时间">
          {{ drawerRecord.update_time }}
        </DescriptionsItem>
        <DescriptionsItem label="备注">
          {{ drawerRecord.remark || '-' }}
        </DescriptionsItem>
      </Descriptions>
    </Drawer>

    <!-- Job AB Test Modal -->
    <JobABTestModal
      v-model:open="jobABTestVisible"
      :agent-code="jobABTestAgent.code"
      :agent-name="jobABTestAgent.name"
      @success="handleJobABTestSuccess"
    />
  </div>
</template>

<style scoped>
.agent-page {
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

:deep(.ant-card-head) {
  border-bottom: 1px solid hsl(var(--border));
}

:deep(.ant-table-thead > tr > th) {
  background: hsl(var(--muted));
}

/* 操作按钮样式 - 使用 VbenIconButton */
.action-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.metrics-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.metrics-item {
  display: flex;
  gap: 8px;
  justify-content: space-between;
}

.metrics-label {
  color: hsl(var(--muted-foreground));
}

.metrics-value {
  font-weight: 500;
  color: hsl(var(--foreground));
}

.metrics-loading {
  color: hsl(var(--muted-foreground));
}

.agent-list-wrapper {
  max-width: 1400px;
  margin: 0 auto;
}

.agent-grid {
  display: grid;
  grid-template-columns:
    220px
    240px
    minmax(200px, 1fr)
    100px
    minmax(220px, 1fr)
    80px
    100px;
  gap: 0;
  align-items: center;
}

.agent-table-header {
  margin-bottom: 24px;
  overflow: hidden;
  border-radius: 8px;
  box-shadow:
    inset 0 0 0 1px hsl(var(--border)),
    0 4px 12px hsl(var(--background) / 20%);
}

.dark .agent-table-header {
  box-shadow:
    inset 0 0 0 1px hsl(var(--border)),
    0 4px 12px hsl(var(--background-deep) / 20%);
}

.agent-header-item {
  padding: 10px 0;
  font-size: 15px;
  font-weight: 600;
  color: hsl(var(--primary-foreground));
  text-align: center;
  background: hsl(var(--primary));
}

.dark .agent-header-item {
  color: hsl(var(--foreground));
  background: #000;
}

.agent-list {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.agent-row {
  align-items: stretch;
  overflow: hidden;
  background: hsl(var(--card));
  border-radius: 12px;
  box-shadow:
    0 2px 8px hsl(var(--background-deep) / 15%),
    0 0 0 1px hsl(var(--border));
  transition:
    box-shadow 0.3s cubic-bezier(0.25, 0.8, 0.25, 1),
    transform 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.agent-row:hover {
  box-shadow:
    0 15px 20px -12px hsl(var(--foreground) / 10%),
    0 0 15px 5px hsl(var(--foreground) / 5%);
  transform: translateY(-2px);
}

.agent-grid .table-cell {
  position: relative;
  display: flex;
  align-items: center;
  padding: 16px;
}

.agent-grid .table-cell > * {
  width: 100%;
}

.agent-grid .table-cell::after {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 1px;
  content: '';
  background: hsl(var(--border));
}

.agent-grid .table-cell:last-child::after {
  display: none;
}

.agent-col-name {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  justify-content: center;
}

.agent-name-box {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 180px;
  height: 60px;
  overflow: hidden;
  font-size: 18px;
  font-weight: 600;
  line-height: 1.2;
  color: hsl(var(--primary));
  text-align: center;
  overflow-wrap: anywhere;
  background: hsl(var(--primary) / 8%);
  border-radius: 12px;
  box-shadow: inset 0 0 0 1px hsl(var(--primary) / 15%);
}

.agent-col-profile,
.agent-col-train {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.profile-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.train-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.profile-item,
.train-item {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 8px;
  align-items: center;
  min-width: 0;
}

.profile-item {
  grid-template-columns: 84px 1fr;
  gap: 3px;
}

.profile-label,
.train-label {
  color: hsl(var(--muted-foreground));
}

.profile-value,
.train-value {
  font-weight: 500;
  color: hsl(var(--foreground));
}

.agent-col-expert,
.agent-col-index,
.agent-col-status,
.agent-col-action {
  display: flex;
  justify-content: center;
}

.expert-count {
  font-size: 26px;
  font-weight: 700;
  color: hsl(var(--primary));
}

.index-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.index-item {
  display: grid;
  grid-template-columns: 72px 1fr 36px;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.index-label {
  color: hsl(var(--muted-foreground));
}

.index-value {
  font-weight: 500;
  color: hsl(var(--foreground));
  text-align: right;
}

.index-bar {
  position: relative;
  height: 6px;
  overflow: hidden;
  background: hsl(var(--muted));
  border-radius: 999px;
}

.index-bar-fill {
  height: 100%;
  background: hsl(var(--primary));
}

.index-bar-fill-alt {
  background: hsl(var(--warning));
}

.index-bar-fill-success {
  background: hsl(var(--success));
}

.status-wrapper {
  text-align: center;
}

.status-text {
  margin-top: 8px;
  font-size: 12px;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
}

.action-buttons-vertical {
  flex-direction: column;
}

.agent-empty {
  padding: 24px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}

.action-btn {
  font-size: 15px;
  transition: all 0.2s ease;
}

/* VbenIconButton 颜色覆盖 */
.action-btn-primary {
  color: hsl(var(--primary)) !important;
}

.action-btn-primary:hover {
  background: hsl(var(--primary) / 15%) !important;
}

.action-btn-info {
  color: #1890ff !important;
}

.action-btn-info:hover {
  background: rgb(24 144 255 / 15%) !important;
}

.action-btn-danger {
  color: hsl(var(--destructive)) !important;
}

.action-btn-danger:hover {
  background: hsl(var(--destructive) / 15%) !important;
}

:deep(.ant-descriptions-bordered .ant-descriptions-item-label) {
  background: hsl(var(--muted) / 30%);
}

/* Expert 编排样式（复用 Job 创建页风格） */
.expert-selection-container {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  min-height: 360px;
}

.expert-list-panel,
.flow-panel {
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

.expert-cards {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  max-height: 280px;
  padding: 12px;
  overflow-y: auto;
}

.expert-card {
  padding: 10px 12px;
  cursor: pointer;
  background: hsl(var(--background));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  transition: all 0.2s;
}

.expert-card:hover {
  background: hsl(var(--muted) / 30%);
  border-color: hsl(var(--primary) / 50%);
}

.expert-card.selected {
  background: hsl(var(--primary) / 8%);
  border-color: hsl(var(--primary));
}

.expert-card-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}

.expert-card-name {
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.expert-card-code {
  margin-bottom: 6px;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.expert-card-meta {
  display: flex;
  gap: 6px;
}

.empty-experts,
.empty-flow {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 80px;
  color: hsl(var(--muted-foreground));
}

.flow-list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  max-height: 280px;
  padding: 12px;
  overflow-y: auto;
}

.flow-item {
  position: relative;
  display: flex;
  gap: 12px;
  align-items: stretch;
  min-height: 90px;
  padding: 10px 12px;
  background: hsl(var(--muted) / 25%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  transition: all 0.2s ease;
}

.flow-item:hover {
  background: hsl(var(--muted) / 35%);
  border-color: hsl(var(--primary) / 35%);
  box-shadow: 0 6px 18px rgb(0 0 0 / 6%);
}

.flow-item-body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  min-width: 0;
}

.flow-item-header {
  display: flex;
  gap: 12px;
  align-items: center;
  min-width: 0;
  overflow: hidden;
}

.flow-item-main {
  display: flex;
  flex: 1;
  gap: 8px;
  align-items: baseline;
  min-width: 0;
}

.flow-description {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
}

.drag-handle {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  font-size: 18px;
  color: hsl(var(--muted-foreground));
  cursor: grab;
  user-select: none;
  background: hsl(var(--muted) / 50%);
  border-radius: 6px;
  transition: all 0.2s;
}

.drag-handle:hover {
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 20%);
  transform: scale(1.05);
}

.drag-handle:active {
  cursor: grabbing;
  transform: scale(0.95);
}

/* 正在拖拽的元素 */
.flow-item-dragging {
  background: hsl(var(--muted) / 30%);
  border-style: dashed;
  opacity: 0.4;
  transform: scale(0.95);
}

/* 拖拽经过的目标位置 - 上方插入 */
.flow-item-dragover-top {
  background: hsl(var(--primary) / 8%);
  border-top: 3px solid hsl(var(--primary));
}

.flow-item-dragover-top::before {
  position: absolute;
  top: -2px;
  right: 0;
  left: 0;
  height: 2px;
  content: '';
  background: hsl(var(--primary));
  border-radius: 2px;
}

/* 拖拽经过的目标位置 - 下方插入 */
.flow-item-dragover-bottom {
  background: hsl(var(--primary) / 8%);
  border-bottom: 3px solid hsl(var(--primary));
}

.flow-item-dragover-bottom::after {
  position: absolute;
  right: 0;
  bottom: -2px;
  left: 0;
  height: 2px;
  content: '';
  background: hsl(var(--primary));
  border-radius: 2px;
}

.flow-step {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  font-size: 13px;
  font-weight: 600;
  color: hsl(var(--primary-foreground));
  background: hsl(var(--primary));
  border-radius: 50%;
}

.flow-name {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
  font-weight: 500;
  line-height: 1.4;
  color: hsl(var(--foreground));
  word-break: keep-all;
  overflow-wrap: normal;
  white-space: nowrap;
  cursor: default;
}

.flow-actions {
  display: flex;
  flex-wrap: nowrap;
  gap: 4px;
  align-items: center;
  justify-content: flex-end;
  min-width: 0;
  padding-left: 38px;
}

.flow-action-btn {
  font-size: 15px;
  color: hsl(var(--muted-foreground)) !important;
  transition: all 0.2s ease;
}

.flow-action-btn:hover {
  color: hsl(var(--foreground)) !important;
  background: hsl(var(--muted) / 35%) !important;
}

.flow-action-btn-danger {
  color: hsl(var(--destructive)) !important;
}

.flow-action-btn-danger:hover {
  background: hsl(var(--destructive) / 12%) !important;
}

.zero-score-rule {
  padding: 10px 12px 12px;
  background: hsl(var(--muted) / 10%);
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
}

.zero-score-rule-header {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.zero-score-rule-title {
  display: inline-flex;
  gap: 8px;
  align-items: center;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.help-icon {
  color: hsl(var(--muted-foreground));
  cursor: help;
}

.zero-score-rule-body {
  margin-top: 10px;
}

.zero-score-alert {
  margin-bottom: 10px;
}

.zero-score-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.zero-score-option {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 10px 12px;
  cursor: pointer;
  background: hsl(var(--background));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.zero-score-option:hover {
  background: hsl(var(--muted) / 30%);
  border-color: hsl(var(--primary) / 50%);
}

.zero-score-option-main {
  flex: 1;
  min-width: 0;
}

.zero-score-option-name {
  display: flex;
  gap: 8px;
  align-items: center;
  font-weight: 500;
}

.zero-score-option-code code {
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
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

/* 编码校验状态样式 */
.validation-icon {
  font-size: 16px;
  cursor: help;
}

.text-green-500 {
  color: #10b981 !important;
}

.text-red-500 {
  color: #ef4444 !important;
}

.text-blue-500 {
  color: #3b82f6 !important;
}

.text-orange-500 {
  color: #f97316 !important;
}

.form-item-hint {
  margin-top: 4px;
  font-size: 12px;
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
</style>
