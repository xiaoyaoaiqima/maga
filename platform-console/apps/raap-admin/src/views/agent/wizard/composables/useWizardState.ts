import type { AgentTemplate, TemplateConfig } from '../workbench/composables';

import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';

import { logger } from '#/utils/logger';

/**
 * 向导步骤
 */
export type WizardStep = 1 | 2 | 3 | 4 | 5;

/**
 * 步骤状态
 */
export interface StepStatus {
  /** 是否已完成 */
  completed: boolean;
  /** 是否可编辑 */
  editable: boolean;
  /** 是否有错误 */
  hasError: boolean;
}

/**
 * 关键词选择项
 */
export interface KeywordSelection {
  /** 维度 ID */
  dimensionId: string;
  /** 维度名称 */
  dimensionName: string;
  /** 选中的关键词列表 */
  selectedKeywords: string[];
}

/**
 * 策略配置项
 */
export interface StrategyConfig {
  /** 策略 ID */
  id?: string;
  /** 策略名称 */
  name: string;
  /** 关键词组合 */
  combinations: Array<Record<string, string>>;
  /** 策略类型 */
  strategyType?: string;
}

/**
 * Expert 配置项
 */
export interface ExpertConfig {
  /** Expert 类型 */
  type: 'ANALYSIS' | 'CRITIC' | 'CUSTOM' | 'GENERATION' | 'SCORING';
  /** Expert 编码 */
  code: string;
  /** Expert 名称 */
  name: string;
  /** 插件配置 */
  pluginConfig?: Record<string, unknown>;
  /** 模型编码（可选覆盖） */
  modelCode?: string;
  /** 温度（可选覆盖） */
  temperature?: number;
}

/**
 * Agent 配置
 */
export interface AgentConfig {
  /** Agent 编码 */
  code?: string;
  /** Agent 名称 */
  name: string;
  /** Agent 描述 */
  description: string;
  /** 关键词选择 */
  keywords: KeywordSelection[];
  /** 策略配置 */
  strategies: StrategyConfig[];
  /** Expert 配置 */
  experts: ExpertConfig[];
  /** 执行顺序 */
  executionOrder: string[];
}

/**
 * 向导状态
 */
export interface WizardState {
  /** 当前步骤 */
  currentStep: WizardStep;
  /** 选中的模板 */
  selectedTemplate: AgentTemplate | null;
  /** 是否为空白创建 */
  isBlankMode: boolean;
  /** 编辑的 Agent 编码 */
  editAgentCode?: string;
  /** 草稿 Agent 编码 */
  draftAgentCode?: string;
  /** Agent 配置 */
  agentConfig: AgentConfig;
  /** 步骤状态 */
  stepStatus: Record<WizardStep, StepStatus>;
}

/**
 * 创建默认 Agent 配置
 */
function createDefaultAgentConfig(): AgentConfig {
  return {
    name: '',
    description: '',
    keywords: [],
    strategies: [],
    experts: [],
    executionOrder: [],
  };
}

/**
 * 创建默认步骤状态
 */
function createDefaultStepStatus(): Record<WizardStep, StepStatus> {
  return {
    1: { completed: false, editable: true, hasError: false },
    2: { completed: false, editable: false, hasError: false },
    3: { completed: false, editable: false, hasError: false },
    4: { completed: false, editable: false, hasError: false },
    5: { completed: false, editable: false, hasError: false },
  };
}

/**
 * Agent 向导状态管理 Composable
 */
export function useWizardState() {
  const router = useRouter();

  // 状态
  const currentStep = ref<WizardStep>(1);
  const selectedTemplate = ref<AgentTemplate | null>(null);
  const isBlankMode = ref(false);
  const editAgentCode = ref<string>();
  const draftAgentCode = ref<string>();
  const agentConfig = ref<AgentConfig>(createDefaultAgentConfig());
  const stepStatus = ref<Record<WizardStep, StepStatus>>(
    createDefaultStepStatus(),
  );

  const totalSteps = 5;
  const loading = ref(false);
  const saving = ref(false);

  // ========== 计算属性 ==========

  /**
   * 当前步骤的标题
   */
  const stepTitle = computed(() => {
    const titles: Record<WizardStep, string> = {
      1: '配置关键词',
      2: '组合策略',
      3: '配置 Expert',
      4: '组装预览',
      5: '完成',
    };
    return titles[currentStep.value];
  });

  /**
   * 是否可以下一步
   */
  const canNext = computed(() => {
    const step = currentStep.value;
    if (step === 1) {
      // 关键词：至少选择一个维度
      return agentConfig.value.keywords.some(
        (k) => k.selectedKeywords.length > 0,
      );
    }
    if (step === 2) {
      // 策略：至少有一个策略组合
      return agentConfig.value.strategies.length > 0;
    }
    if (step === 3) {
      // Expert：至少有生文和审核专家
      const hasGeneration = agentConfig.value.experts.some(
        (e) => e.type === 'GENERATION',
      );
      const hasCritic = agentConfig.value.experts.some(
        (e) => e.type === 'CRITIC',
      );
      return hasGeneration && hasCritic;
    }
    if (step === 4) {
      // 组装：填写名称和描述
      return (
        agentConfig.value.name.trim().length > 0 &&
        agentConfig.value.description.trim().length > 0
      );
    }
    return true;
  });

  /**
   * 进度百分比
   */
  const progressPercent = computed(() => {
    return ((currentStep.value - 1) / (totalSteps - 1)) * 100;
  });

  /**
   * 完成步骤数
   */
  const completedSteps = computed(() => {
    return Object.values(stepStatus.value).filter((s) => s.completed).length;
  });

  // ========== 方法 ==========

  /**
   * 初始化向导（从路由参数）
   */
  async function initWizard() {
    const query = router.currentRoute.value.query;

    // 模板模式
    if (query.template) {
      const templateId = query.template as string;
      // TODO: 从模板列表中获取模板
      // selectedTemplate.value = AGENT_TEMPLATES.find(t => t.id === templateId);
      // 应用模板默认配置
      if (selectedTemplate.value?.defaultConfig) {
        applyTemplateConfig(selectedTemplate.value.defaultConfig);
      }
    }
    // 空白模式
    else if (query.mode === 'blank') {
      isBlankMode.value = true;
    }
    // 编辑模式
    else if (query.edit) {
      editAgentCode.value = query.edit as string;
      await loadAgent(query.edit as string);
    }
    // 草稿模式
    else if (query.draft) {
      draftAgentCode.value = query.draft as string;
      await loadDraft(query.draft as string);
    }
  }

  /**
   * 应用模板配置
   */
  function applyTemplateConfig(config: TemplateConfig) {
    if (config.keywords) {
      agentConfig.value.keywords = Object.entries(config.keywords).map(
        ([dimension, keywords]) => ({
          dimensionId: dimension,
          dimensionName: dimension,
          selectedKeywords: keywords,
        }),
      );
    }
    if (config.strategies) {
      agentConfig.value.strategies = config.strategies.map((s) => ({
        ...s,
        combinations: [],
      }));
    }
    if (config.experts) {
      agentConfig.value.experts = config.experts.map((e) => ({
        type: e.type as any,
        code: e.code,
        name: e.code, // 临时使用 code 作为 name
      }));
    }
  }

  /**
   * 加载 Agent（编辑模式）
   */
  async function loadAgent(code: string) {
    loading.value = true;
    try {
      // TODO: 调用后端 API
    } catch (error) {
      logger.error('加载 Agent 失败:', error);
    } finally {
      loading.value = false;
    }
  }

  /**
   * 加载草稿
   */
  async function loadDraft(code: string) {
    loading.value = true;
    try {
      // TODO: 调用后端 API
      // const draft = await getAgentDraftApi(code);
      // agentConfig.value = draft;
    } catch (error) {
      logger.error('加载草稿失败:', error);
    } finally {
      loading.value = false;
    }
  }

  /**
   * 下一步
   */
  function nextStep() {
    if (currentStep.value < totalSteps && canNext.value) {
      // 标记当前步骤完成
      stepStatus.value[currentStep.value].completed = true;
      // 进入下一步
      currentStep.value++;
      // 解锁下一步
      if (currentStep.value < totalSteps) {
        stepStatus.value[currentStep.value].editable = true;
      }
    }
  }

  /**
   * 上一步
   */
  function prevStep() {
    if (currentStep.value > 1) {
      currentStep.value--;
    }
  }

  /**
   * 跳转到指定步骤
   */
  function goToStep(step: WizardStep) {
    if (stepStatus.value[step].editable || stepStatus.value[step].completed) {
      currentStep.value = step;
    }
  }

  /**
   * 保存草稿
   */
  async function saveDraft() {
    saving.value = true;
    try {
      // TODO: 调用后端 API
      // if (draftAgentCode.value) {
      //   await updateAgentDraftApi(draftAgentCode.value, agentConfig.value);
      // } else {
      //   const draft = await createAgentDraftApi(agentConfig.value);
      //   draftAgentCode.value = draft.code;
      // }
    } catch (error) {
      logger.error('保存草稿失败:', error);
      throw error;
    } finally {
      saving.value = false;
    }
  }

  /**
   * 提交创建 Agent
   */
  async function submitAgent() {
    saving.value = true;
    try {
      // TODO: 调用后端 API
      return agentConfig.value;
    } catch (error) {
      logger.error('创建 Agent 失败:', error);
      throw error;
    } finally {
      saving.value = false;
    }
  }

  /**
   * 完成后跳转
   */
  function onFinish() {
    router.push('/agent/workbench');
  }

  /**
   * 取消/关闭
   */
  function onCancel() {
    router.push('/agent/workbench');
  }

  /**
   * 重置状态
   */
  function reset() {
    currentStep.value = 1;
    selectedTemplate.value = null;
    isBlankMode.value = false;
    editAgentCode.value = undefined;
    draftAgentCode.value = undefined;
    agentConfig.value = createDefaultAgentConfig();
    stepStatus.value = createDefaultStepStatus();
  }

  return {
    // 状态
    currentStep,
    selectedTemplate,
    isBlankMode,
    editAgentCode,
    draftAgentCode,
    agentConfig,
    stepStatus,
    loading,
    saving,
    totalSteps,

    // 计算属性
    stepTitle,
    canNext,
    progressPercent,
    completedSteps,

    // 方法
    initWizard,
    applyTemplateConfig,
    loadAgent,
    loadDraft,
    nextStep,
    prevStep,
    goToStep,
    saveDraft,
    submitAgent,
    onFinish,
    onCancel,
    reset,
  };
}
