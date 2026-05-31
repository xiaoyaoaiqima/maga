<script setup lang="ts">
import type { ContentStrategyApi } from '#/api/core/content-strategy';
import type { JobApi, JobVariantApi } from '#/api/core/job';

import { computed, h, nextTick, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { InfoCircleOutlined, RobotOutlined } from '@ant-design/icons-vue';
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Drawer,
  Form,
  FormItem,
  Input,
  InputNumber,
  InputSearch,
  message,
  Modal,
  Popconfirm,
  Radio,
  RadioButton,
  RadioGroup,
  Row,
  Select,
  SelectOption,
  Space,
  Spin,
  Statistic,
  Step,
  Steps,
  Table,
  Tag,
  Textarea,
  Tooltip,
} from 'ant-design-vue';

import {
  getAgentApi,
  getAgentSimpleListApi,
  getTenantSimpleListApi,
} from '#/api/core/business';
import {
  generateCombinationsApi,
  getContentStrategiesApi,
  mergeStrategyCombinationsApi,
} from '#/api/core/content-strategy';
import {
  createJobApi,
  createJobVariantApi,
  getJobApi,
  getJobVariantListApi,
  updateJobApi,
} from '#/api/core/job';
import { requestClient } from '#/api/request';
import StrategySmartSelector from '#/components/StrategySmartSelector.vue';
import { cloneReactive } from '#/utils/clone';

interface ExpertConfig {
  id: number;
  expert_config_code: string;
  expert_config_name: string;
  description: null | string;
  enabled: boolean;
  expert_type?: string;
  model_code?: null | string;
  plugin_config?: JobApi.ExpertPluginConfigItem[] | null;
}

const router = useRouter();
const route = useRoute();
const loading = ref(false);
const saving = ref(false);
const currentStep = ref(0);
const expertConfigs = ref<ExpertConfig[]>([]);
const guideDismissed = ref(false);
const isEdit = computed(() => !!route.query.id);

type JobCreateMode =
  | 'plan1_combinations'
  | 'plan2_rules'
  | 'plan3_variants'
  | 'plan4_strategy'
  | 'system_random';
type AllocationUnitMode = 'count' | 'ratio';

// 变量共享映射项
interface VariableShareMappingItem {
  expert_code: string;
  variable: string;
}

// 策略模式配置
interface StrategyModeConfig {
  strategy_id: null | string;
  variable_share_mapping: Record<string, VariableShareMappingItem[]>;
  strategy_overrides: Record<string, string[]>;
  preview_combinations: ContentStrategyApi.CombinationItem[];
}

// v3 新结构：多策略维度合并
interface MergedCombination {
  id: string;
  name: string;
  count: number;
  source_combos: Array<{ combo_id: string; strategy_id: string }>;
  merged_nodes: Record<string, ContentStrategyApi.NodeInfo>;
}

interface StrategyModeConfigV3 {
  selected_strategy_ids: string[];
  merged_dimensions: string[];
  merged_combinations: MergedCombination[];
  variable_share_mapping: Record<string, VariableShareMappingItem[]>;
  total_count: number;
  available_strategies: { id: number; name: string }[]; // 可用策略列表
}

// 业务选项数据
const tenantOptions = ref<{ label: string; value: number }[]>([]);
const agentOptions = ref<{ label: string; value: string }[]>([]);

const formState = ref({
  // 业务归属
  tenant_id: undefined as number | undefined,
  agent_code: undefined as string | undefined,

  job_name: '',
  description: '',
  enabled: true,
  article_count: 10,
  expert_config_code_list: [] as string[],
});

const prefilling = ref(false);

// 生成唯一任务ID（时间戳 + 随机数）
function generateJobId(): string {
  const timestamp = Date.now().toString(36); // 36进制时间戳
  const random = Math.random().toString(36).slice(2, 6); // 4位随机数
  return `${timestamp}${random}`.toUpperCase();
}

// 自动生成任务名称（仅在创建模式下）
watch(
  () => formState.value.agent_code,
  (newAgentCode) => {
    // 编辑模式下不自动生成 job_name
    if (isEdit.value) {
      return;
    }

    if (!newAgentCode) {
      formState.value.job_name = '';
      return;
    }

    // 查找agent的名称（从label中提取agent_name部分）
    const agent = agentOptions.value.find((a) => a.value === newAgentCode);
    // label格式："{agent_name} ({agent_code})"，需要提取agent_name
    const agentName = agent?.label?.split(' (')[0] || newAgentCode;

    // 生成任务名称：agent名称 + 唯一ID
    const uniqueId = generateJobId();
    formState.value.job_name = `${agentName}_${uniqueId}`;
  },
  { immediate: true },
);

const jobCreateMode = ref<JobCreateMode>('system_random');
const allocationUnitMode = ref<AllocationUnitMode>('ratio');
const previewTotalCount = computed(() => formState.value.article_count);

type CombinationRow = {
  count?: number;
  /**
   * 组合级参数配置（用于 job_generation_plan.plan_items[*].expert_param_config）
   * - key: expert_config_code
   * - value: plugin_config_snapshot（每个 plugin 的 variable_mapping 都是“确定的 context_name”）
   */
  expert_param_config?: Record<string, JobApi.PluginConfigSnapshotItem[]>;
  id: string;
  name: string;
  ratio: number;
};

type RuleCondition = {
  /** 变量名：直接取 plugin_config.variable_mapping 的 key */
  field: string;
  op: '=' | '≠';
  value?: string;
};

type RuleRow = {
  conditions: RuleCondition[];
  id: string;
  name: string;
  ratio: number;
};

type VariantRow = {
  id: string;
  name: string;
  ratio: number;
  tags: string[];
};

function genLocalId(prefix: string): string {
  return `${prefix}_${Math.random().toString(16).slice(2)}_${Date.now()}`;
}

const combinations = ref<CombinationRow[]>([]);
const selectedCombinationRowKeys = ref<string[]>([]);
const editingCombinationId = ref<null | string>(null);
const combinationDrawerOpen = computed(() => !!editingCombinationId.value);

type VariableCatalogEntry = {
  options: string[];
  plugin_codes: string[];
  variable_name: string;
};

const editingCombination = computed(
  () =>
    combinations.value.find((x) => x.id === editingCombinationId.value) ?? null,
);

// 组合编辑器：每个 Expert 的“变量 → 已选 context_name”（临时态，关闭抽屉即丢）
const combinationEditorSelections = ref<
  Record<string, Record<string, string | undefined>>
>({});

function initCombinationEditorSelections(combinationId: string) {
  const row = combinations.value.find((x) => x.id === combinationId);
  const next: Record<string, Record<string, string | undefined>> = {};

  for (const expert of selectedExperts.value) {
    next[expert.code] = {};
    const saved = row?.expert_param_config?.[expert.code];
    if (Array.isArray(saved)) {
      for (const pluginItem of saved) {
        const mapping = pluginItem?.variable_mapping || {};
        for (const [variableName, contextName] of Object.entries(mapping)) {
          if (typeof contextName === 'string' && contextName) {
            next[expert.code]![variableName] = contextName;
          }
        }
      }
    }
  }

  combinationEditorSelections.value = next;
}

function setCombinationSelection(
  expertCode: string,
  variableName: string,
  v: null | string | undefined,
) {
  if (!combinationEditorSelections.value[expertCode]) {
    combinationEditorSelections.value[expertCode] = {};
  }
  if (!v) {
    delete combinationEditorSelections.value[expertCode]![variableName];
    return;
  }
  combinationEditorSelections.value[expertCode]![variableName] = v;
}

const expertVariableCatalog = computed<Record<string, VariableCatalogEntry[]>>(
  () => {
    const result: Record<string, VariableCatalogEntry[]> = {};

    for (const expert of selectedExperts.value) {
      const pluginConfig = expert.plugin_config || [];

      // varName -> { sets: Set<string>[], plugin_codes: Set<string> }
      const occurrences: Record<
        string,
        { plugin_codes: Set<string>; sets: Array<Set<string>> }
      > = {};

      for (const pluginItem of pluginConfig) {
        const pluginCode = pluginItem?.plugin_code;
        if (!pluginCode) continue;

        const mapping = pluginItem?.variable_mapping || {};
        for (const [variableName, rawOptions] of Object.entries(mapping)) {
          const opts = normalizeContextOptions(rawOptions as any);

          if (!occurrences[variableName]) {
            occurrences[variableName] = {
              sets: [],
              plugin_codes: new Set<string>(),
            };
          }
          // 即使 opts.length === 0 也添加，允许后续通过关键词策略覆盖
          occurrences[variableName]!.sets.push(new Set(opts));
          occurrences[variableName]!.plugin_codes.add(pluginCode);
        }
      }

      const catalog: VariableCatalogEntry[] = [];
      for (const [variableName, entry] of Object.entries(occurrences)) {
        const sets = entry.sets;
        if (sets.length === 0) continue;

        // 计算交集：如果任何一个集合为空，最终交集为空
        let intersection: Set<string>;
        if (sets.some((set) => set.size === 0)) {
          // 如果有任意一个插件没有配置上下文，交集为空
          intersection = new Set();
        } else {
          intersection = new Set(sets[0]);
          for (let i = 1; i < sets.length; i++) {
            const nextSet = sets[i]!;
            intersection = new Set(
              [...intersection].filter((x) => nextSet.has(x)),
            );
          }
        }

        catalog.push({
          variable_name: variableName,
          options: [...intersection].toSorted(),
          plugin_codes: [...entry.plugin_codes].toSorted(),
        });
      }

      result[expert.code] = catalog.toSorted((a, b) =>
        a.variable_name.localeCompare(b.variable_name),
      );
    }

    return result;
  },
);

const plan2FieldOptions = computed(() => {
  const keys = new Set<string>();
  for (const expert of selectedExperts.value) {
    const pluginConfig = expert.plugin_config || [];
    for (const pluginItem of pluginConfig) {
      const mapping = pluginItem?.variable_mapping || {};
      for (const k of Object.keys(mapping)) {
        if (k) keys.add(k);
      }
    }
  }
  return [...keys].toSorted().map((x) => ({ label: x, value: x }));
});

function getDefaultRuleField(): string {
  return plan2FieldOptions.value[0]?.value ?? '内容框架';
}

const emptyIntersectionWarnings = computed(() => {
  const warnings: Array<{ expert_code: string; variable_name: string }> = [];
  for (const expert of selectedExperts.value) {
    const list = expertVariableCatalog.value[expert.code] || [];
    for (const v of list) {
      if (v.options.length === 0) {
        warnings.push({
          expert_code: expert.code,
          variable_name: v.variable_name,
        });
      }
    }
  }
  return warnings;
});

function saveCombinationEditor() {
  if (!editingCombinationId.value) return;
  const row = combinations.value.find(
    (x) => x.id === editingCombinationId.value,
  );
  if (!row) return;

  const nextExpertParamConfig: Record<
    string,
    JobApi.PluginConfigSnapshotItem[]
  > = {};

  for (const expert of selectedExperts.value) {
    const pluginConfig = expert.plugin_config || [];
    if (pluginConfig.length === 0) continue;

    const picked = combinationEditorSelections.value[expert.code] || {};
    const snapshot: JobApi.PluginConfigSnapshotItem[] = [];

    for (const pluginItem of pluginConfig) {
      const pluginCode = pluginItem?.plugin_code;
      if (!pluginCode) continue;

      const mapping = pluginItem?.variable_mapping || {};
      const pickedMapping: Record<string, string> = {};
      for (const variableName of Object.keys(mapping)) {
        const v = picked[variableName];
        if (typeof v === 'string' && v) {
          pickedMapping[variableName] = v;
        }
      }

      if (Object.keys(pickedMapping).length > 0) {
        snapshot.push({
          plugin_code: pluginCode,
          variable_mapping: pickedMapping,
        });
      }
    }

    if (snapshot.length > 0) {
      nextExpertParamConfig[expert.code] = snapshot;
    }
  }

  const hasAny = Object.keys(nextExpertParamConfig).length > 0;
  row.expert_param_config = hasAny ? nextExpertParamConfig : undefined;
  message.success('已保存组合变量配置（未选择的变量仍按随机处理）');
  closeCombinationEditor();
}

function resetCombinationEditor() {
  if (!editingCombinationId.value) return;
  initCombinationEditorSelections(editingCombinationId.value);
  // 清空所有选择 → 回到完全随机
  for (const expertCode of Object.keys(combinationEditorSelections.value)) {
    combinationEditorSelections.value[expertCode] = {};
  }
}

const rules = ref<RuleRow[]>([]);
const editingRuleId = ref<null | string>(null);
const ruleDrawerOpen = computed(() => !!editingRuleId.value);
const ruleDraft = ref<null | RuleRow>(null);

const variantLibraryLoading = ref(false);
const variantKeyword = ref('');
const variantLibrary = ref<JobVariantApi.JobVariant[]>([]);
const selectedVariants = ref<VariantRow[]>([]);
const variantPickerOpen = ref(false);

// 策略模式相关状态
const strategyList = ref<ContentStrategyApi.ContentStrategy[]>([]);
const strategyLoading = ref(false);

// 策略下拉选项（用于 Select 组件的 options 属性）
const strategySelectOptions = computed(() => {
  return strategyList.value.map((s) => ({
    label: `${s.name} (${s.combinations_count || 0}个组合)`,
    value: s.id,
  }));
});
const strategyConfig = ref<StrategyModeConfig>({
  strategy_id: null,
  variable_share_mapping: {},
  strategy_overrides: {},
  preview_combinations: [],
});

const useStrategyV3 = ref(false); // 是否使用 v3 模式（维度合并）
const useSmartSelector = ref(true); // 是否使用智能策略选择器（默认开启）

// ⚠️ strategy_v2 已废弃，保留空对象/变量避免引用错误
const useStrategyV2 = ref(false);
const strategyConfigV2 = ref({
  selected_strategy_ids: [],
  allocations: [],
  variable_share_mapping: {},
  total_count: 0,
});

// v3 策略配置（多策略维度合并）
const strategyConfigV3 = ref<StrategyModeConfigV3>({
  selected_strategy_ids: [],
  merged_dimensions: [],
  merged_combinations: [],
  variable_share_mapping: {},
  total_count: 0,
  available_strategies: [],
});
const mergedCombinationsLoading = ref(false);
const MERGE_PREVIEW_TARGET_COUNT_MAX = 2000;

// 组合搜索关键词
const comboSearchKeyword = ref('');

// 过滤后的组合列表
const filteredCombinations = computed(() => {
  if (!comboSearchKeyword.value) {
    return strategyConfigV3.value.merged_combinations;
  }
  const keyword = comboSearchKeyword.value.toLowerCase();
  return strategyConfigV3.value.merged_combinations.filter((combo) => {
    const nodeNames = Object.values(combo.merged_nodes || {})
      .map((node) => node.name?.toLowerCase() || '')
      .join(' ');
    return nodeNames.includes(keyword);
  });
});

// v3 策略采样配置
const strategySamplingConfig = ref({
  sample_mode: 'primary_strategy' as 'primary_strategy' | 'random', // 采样模式：主策略优先/全随机
  primary_strategy_id: undefined as number | undefined, // 主策略ID
});

// 监听采样模式变化
watch(
  () => strategySamplingConfig.value.sample_mode,
  (newMode, oldMode) => {
    // 如果有选中的策略，触发重新加载
    if (
      newMode !== oldMode &&
      strategyConfigV3.value.selected_strategy_ids.length > 0
    ) {
      debouncedReloadMergedCombinations();
    }
  },
  { immediate: true },
);

// 监听主维度变化
watch(
  () => strategySamplingConfig.value.primary_strategy_id,
  (newDim, oldDim) => {
    // 智能切换：如果用户选择了主维度，自动切换到"合并维度"模式
    if (newDim && newDim !== oldDim) {
      if (strategySamplingConfig.value.sample_mode !== 'primary_strategy') {
        strategySamplingConfig.value.sample_mode = 'primary_strategy';
      }

      // 触发重新加载组合（使用防抖）
      debouncedReloadMergedCombinations();
    }
  },
  { immediate: true },
);

// 防抖重新加载组合（避免多次重复加载）
let reloadMergedCombinationsTimer: null | ReturnType<typeof setTimeout> = null;
function debouncedReloadMergedCombinations() {
  if (reloadMergedCombinationsTimer) {
    clearTimeout(reloadMergedCombinationsTimer);
  }
  reloadMergedCombinationsTimer = setTimeout(() => {
    loadMergedCombinations();
  }, 300); // 300ms 防抖
}

const strategyMappingDrawerOpen = ref(false);
const strategyPreviewLoading = ref(false);

const modeTips: Record<JobCreateMode, { desc: string; title: string }> = {
  system_random: {
    title: '默认方案：系统随机参数',
    desc: '系统将基于预设规则自动生成随机参数进行执行。',
  },
  plan1_combinations: {
    title: '方案1：组合清单（表格）',
    desc: '手动定义多组确定的参数配置，并为每组配置分配生成比例。',
  },
  plan2_rules: {
    title: '方案2：分流规则（条件→占比）',
    desc: '通过配置逻辑规则（如：当某个变量等于特定值时）来自动分配任务占比。',
  },
  plan3_variants: {
    title: '方案3：方案包 + 分配',
    desc: '从已有的方案库中直接引用预设好的参数方案，并进行占比分配。',
  },
  plan4_strategy: {
    title: '方案4：策略组合',
    desc: '需要先在关键词语料中心配置关键词策略，基于关键词策略自动生成关键词组合，支持跨 Expert 变量共享，确保生成和评分使用相同的关键词。',
  },
};

const plan1CombinationColumns = [
  { title: '组合名称', dataIndex: 'name', key: 'name' },
  { title: '占比(%)', dataIndex: 'ratio', key: 'ratio', width: 140 },
  { title: '预览篇数', dataIndex: 'count', key: 'count', width: 120 },
  { title: '操作', dataIndex: 'action', key: 'action', width: 260 },
];

const plan3VariantColumns = [
  { title: '方案包', dataIndex: 'name', key: 'name' },
  { title: '标签', dataIndex: 'tags', key: 'tags' },
  { title: '占比(%)', dataIndex: 'ratio', key: 'ratio', width: 140 },
  { title: '操作', dataIndex: 'action', key: 'action', width: 120 },
];

const steps = [
  { title: '业务配置', description: '选择智能体并设置参数' },
  { title: '创建方式与参数配置', description: '参数方案选择与确认' },
  { title: '确认配置', description: '确认并提交' },
];

// 确认未配置变量映射是否继续
const confirmNoMappingContinue = (): Promise<boolean> => {
  return new Promise((resolve) => {
    Modal.confirm({
      title: '变量映射未配置',
      content:
        '您尚未配置变量映射，策略变量将无法填充到 Expert 中，这可能导致生成的内容不符合预期。确定要继续吗？',
      okText: '继续创建',
      cancelText: '返回配置',
      type: 'warning',
      onOk: () => resolve(true),
      onCancel: () => resolve(false),
    });
  });
};

// 验证规则（异步，支持确认对话框）
const validateStep = async (step: number): Promise<boolean> => {
  switch (step) {
    case 0: {
      if (!formState.value.agent_code) {
        message.warning('请选择使用的智能体');
        return false;
      }
      // 确保tenant_id已设置（从agent获取或使用默认值）
      if (!formState.value.tenant_id) {
        // 如果agent已选择，从agent获取tenant_id
        if (formState.value.agent_code) {
          try {
            const agent = await getAgentApi(formState.value.agent_code);
            formState.value.tenant_id = agent.tenant_id || 9;
          } catch {
            formState.value.tenant_id = 9;
          }
        } else {
          formState.value.tenant_id = 9;
        }
      }

      break;
    }
    case 1: {
      if (formState.value.expert_config_code_list.length === 0) {
        message.warning('当前智能体未配置专家编排，请先完善智能体');
        return false;
      }
      if (!formState.value.article_count || formState.value.article_count < 1) {
        message.warning('请先设置文章数量');
        return false;
      }
      switch (jobCreateMode.value) {
        case 'plan1_combinations': {
          // 组合表格：占比/变量在前端直接生成 job_generation_plan
          if (combinations.value.length === 0) {
            message.warning('请至少添加一个组合');
            return false;
          }

          break;
        }
        case 'plan2_rules': {
          if (rules.value.length === 0) {
            message.warning('请至少添加一条分流规则');
            return false;
          }

          break;
        }
        case 'plan3_variants': {
          if (selectedVariants.value.length === 0) {
            message.warning('请至少选择一个方案包（Variant）');
            return false;
          }

          break;
        }
        case 'plan4_strategy': {
          if (useSmartSelector.value || useStrategyV3.value) {
            // 智能推荐模式 / v3 模式：检查是否选择了策略并分配了数量
            if (strategyConfigV3.value.selected_strategy_ids.length === 0) {
              message.warning('请选择至少一个关键词策略');
              return false;
            }
            if (strategyConfigV3.value.merged_combinations.length === 0) {
              message.warning('未生成合并组合，请检查策略配置');
              return false;
            }
            if (strategyConfigV3.value.total_count === 0) {
              message.warning('请为合并组合分配生成数量');
              return false;
            }
            // 智能推荐模式允许部分变量不映射，仅提示确认
            // v3 模式：检查变量映射是否配置（改为确认提示）
            if (!hasV3MappingConfigured.value) {
              const confirmed = await confirmNoMappingContinue();
              if (!confirmed) return false;
            }
          } else {
            // v1 模式
            if (!strategyConfig.value.strategy_id) {
              message.warning('请选择关键词策略');
              return false;
            }
            const hasMapping = Object.values(
              strategyConfig.value.variable_share_mapping,
            ).some((m) => m && m.length > 0);
            // v1 模式：检查变量映射是否配置（改为确认提示）
            if (!hasMapping) {
              const confirmed = await confirmNoMappingContinue();
              if (!confirmed) return false;
            }
          }
          break;
        }
        case 'system_random': {
          // 系统随机参数：不需要额外校验

          break;
        }
        // No default
      }
      break;
    }
    // No default
  }
  return true;
};

async function fetchExpertConfigs() {
  try {
    const response =
      await requestClient.get<ExpertConfig[]>('/v1/expert-configs');
    expertConfigs.value = response || [];
  } catch (error) {
    console.error('获取 ExpertConfig 列表失败:', error);
    message.error('获取 ExpertConfig 列表失败');
  }
}

// 加载租户列表
async function fetchTenants() {
  try {
    const data = await getTenantSimpleListApi();
    tenantOptions.value = data.map((item) => ({
      label: `${item.tenant_name} (${item.tenant_code})`,
      value: item.id,
    }));
  } catch (error) {
    console.error('获取租户列表失败:', error);
  }
}

// 加载所有租户下的 Agent 列表
async function fetchAllAgents() {
  try {
    const agents = await getAgentSimpleListApi(); // 不传tenantId，获取所有租户下的agent
    agentOptions.value = agents.map((item) => ({
      label: `${item.agent_name} (${item.agent_code})`,
      value: item.agent_code,
    }));
  } catch (error) {
    console.error('获取 Agent 列表失败:', error);
  }
}

async function prefillFromQuery() {
  if (isEdit.value) return;
  const qAgent = (route.query.agent_code as string | undefined) || undefined;
  const qTenantRaw = route.query.tenant_id as string | undefined;
  const qTenant = qTenantRaw ? Number(qTenantRaw) : undefined;

  prefilling.value = true;
  try {
    // 先加载所有agent列表
    await fetchAllAgents();

    // 如果从agent页面跳转过来，设置tenant_id和agent_code
    if (qAgent) {
      const agent = await getAgentApi(qAgent);
      // 使用agent对应的租户，如果没有则使用query中的tenant_id，都没有则使用默认值9
      formState.value.tenant_id = agent.tenant_id || qTenant || 9;
      formState.value.agent_code = qAgent;
    } else if (qTenant && !Number.isNaN(qTenant)) {
      // 如果只有tenant_id，设置它
      formState.value.tenant_id = qTenant;
    }
    // 如果直接打开页面，不设置tenant_id，agent下拉框会显示所有租户下的agent
  } finally {
    prefilling.value = false;
  }
}

// 监听 agent_code 变化，加载默认配置
watch(
  () => formState.value.agent_code,
  async (newVal) => {
    // 仅在创建模式或用户主动切换 Agent 时加载默认配置
    // 编辑模式初始加载时保留 Job 自身的配置
    if (newVal && !loading.value) {
      try {
        const agent = await getAgentApi(newVal);
        // 设置tenant_id（从agent获取，如果没有则使用默认值9）
        if (!formState.value.tenant_id) {
          formState.value.tenant_id = agent.tenant_id || 9;
        }
        // 如果当前没有配置 expert 列表（或者是刚切换过来），则使用 Agent 默认配置
        formState.value.expert_config_code_list =
          agent.expert_config_code_list || [];
        // 自动填充 Job 名称（仅在创建模式下且为空时）
        if (!isEdit.value && !formState.value.job_name) {
          const timestamp = Date.now().toString(36); // 36进制时间戳
          const random = Math.random().toString(36).slice(2, 6); // 4位随机数
          const uniqueId = `${timestamp}${random}`.toUpperCase();
          formState.value.job_name = `${agent.agent_name}_${uniqueId}`;
        }
        if (!formState.value.description) {
          formState.value.description = agent.description || '';
        }
      } catch (error) {
        console.error('获取 Agent 详情失败:', error);
      }
    }
  },
);

async function fetchJobDetail() {
  if (!route.query.id) return;
  loading.value = true;
  try {
    const job = await getJobApi(route.query.id as string);
    // 先赋值 tenant_id，触发 watch 加载下拉框
    formState.value.tenant_id = job.tenant_id ?? undefined;

    // 等待下拉框加载完成（简单处理，实际应优化为 Promise 链）
    await new Promise((resolve) => setTimeout(resolve, 500));

    formState.value = {
      tenant_id: job.tenant_id ?? undefined,
      agent_code: job.agent_code ?? undefined,
      job_name: job.job_name,
      description: job.description || '',
      enabled: job.enabled ?? true,
      article_count: job.article_count ?? 10,
      expert_config_code_list: job.expert_config_code_list || [],
    };

    // 同步更新目标组合数量
    if (job.article_count) {
      formState.value.article_count = job.article_count;
    }

    // 预填：如果 Job 已经有 job_generation_plan，则回填到方案1/2/3
    const plan = (job as any)?.job_generation_plan;
    if (plan && typeof plan === 'object') {
      const mode = (plan as any).mode;
      switch (mode) {
        case 'allocation_rules': {
          jobCreateMode.value = 'plan2_rules';
          break;
        }
        case 'explicit_combinations': {
          jobCreateMode.value = 'plan1_combinations';
          break;
        }
        case 'strategy_v3': {
          jobCreateMode.value = 'plan4_strategy';
          useStrategyV3.value = true;
          // 回填 v3 策略配置
          const strategySelections = (plan as Record<string, unknown>)
            .strategy_selections as
            | Array<{
                selected_combo_ids?: null | string[];
                strategy_id: string;
              }>
            | undefined;
          const mergedAllocations = (plan as Record<string, unknown>)
            .merged_allocations as Record<string, number> | undefined;
          const v3VariableShareMapping = (plan as Record<string, unknown>)
            .variable_share_mapping as
            | Record<string, VariableShareMappingItem[]>
            | undefined;

          if (strategySelections && strategySelections.length > 0) {
            const selectedIds = strategySelections.map((s) => s.strategy_id);
            strategyConfigV3.value.selected_strategy_ids = selectedIds;
            strategyConfigV3.value.variable_share_mapping =
              v3VariableShareMapping || {};

            // 先加载策略列表，确保 Select 组件能正确显示策略名称
            await loadStrategyList();

            // 加载合并组合并恢复分配
            await loadMergedCombinations();

            // 恢复分配数量
            if (mergedAllocations) {
              for (const combo of strategyConfigV3.value.merged_combinations) {
                combo.count = mergedAllocations[combo.id] || 0;
              }
              updateV3TotalCount();
            }
          }
          break;
        }
        case 'variants': {
          jobCreateMode.value = 'plan3_variants';
          break;
        }
        default: {
          jobCreateMode.value = 'system_random';
        }
      }

      const planItems = (plan as any).plan_items;
      if (Array.isArray(planItems)) {
        switch (mode) {
          case 'allocation_rules': {
            const nextRules = planItems
              .filter(
                (x: any) => x && typeof x === 'object' && x.type === 'rule',
              )
              .map((x: any, idx: number) => ({
                id: x.priority ? `rule_${x.priority}` : genLocalId('rule'),
                name: x.name || `规则 ${idx + 1}`,
                ratio: typeof x.ratio === 'number' ? x.ratio : 0,
                conditions:
                  x.condition &&
                  typeof x.condition === 'object' &&
                  Array.isArray(x.condition.and)
                    ? x.condition.and
                    : [],
              }));
            if (nextRules.length > 0) rules.value = nextRules as any;

            break;
          }
          case 'explicit_combinations': {
            const rows = planItems
              .filter(
                (x: any) => x && typeof x === 'object' && x.type === 'item',
              )
              .map((x: any, idx: number) => ({
                id: x.item_id || `item_${idx}`,
                name: x.name || `组合 ${idx + 1}`,
                ratio: typeof x.ratio === 'number' ? x.ratio : 0,
                count: typeof x.count === 'number' ? x.count : 0,
                expert_param_config:
                  x.expert_param_config &&
                  typeof x.expert_param_config === 'object'
                    ? x.expert_param_config
                    : undefined,
              }));
            if (rows.length > 0) combinations.value = rows as any;

            break;
          }
          case 'variants': {
            const nextVariants = planItems
              .filter(
                (x: any) => x && typeof x === 'object' && x.type === 'item',
              )
              .map((x: any) => ({
                id: x.item_id || (x.variant_ref?.id ?? genLocalId('variant')),
                name: x.name || (x.variant_ref?.name ?? '方案包'),
                tags: Array.isArray(x.variant_ref?.tags)
                  ? x.variant_ref.tags
                  : [],
                ratio: typeof x.ratio === 'number' ? x.ratio : 0,
              }));
            selectedVariants.value = nextVariants as any;

            break;
          }
          // No default
        }
      }
    } else {
      jobCreateMode.value = 'system_random';
    }
  } catch {
    message.error('获取任务详情失败');
    router.push('/job/list');
  } finally {
    loading.value = false;
  }
}

async function handleSubmit() {
  saving.value = true;
  try {
    // 先验证步骤 1（任务名称和文章数量）
    const step1Valid = await validateStep(1);
    if (!step1Valid) {
      saving.value = false;
      return;
    }

    // 再验证步骤 2（策略配置）
    const step2Valid = await validateStep(2);
    if (!step2Valid) {
      saving.value = false;
      return;
    }

    const articleCount = formState.value.article_count;
    if (!articleCount || articleCount < 1) {
      message.warning('请输入目标组合数量（最小 1）');
      return;
    }
    // 确保tenant_id已设置（从agent获取或使用默认值9）
    let finalTenantId = formState.value.tenant_id;
    if (!finalTenantId && formState.value.agent_code) {
      try {
        const agent = await getAgentApi(formState.value.agent_code);
        finalTenantId = agent.tenant_id || 9;
      } catch {
        finalTenantId = 9;
      }
    } else if (!finalTenantId) {
      finalTenantId = 9;
    }
    const payload: JobApi.CreateParams | JobApi.UpdateParams = {
      tenant_id: finalTenantId,
      agent_code: formState.value.agent_code,
      job_name: formState.value.job_name,
      description: formState.value.description || undefined,
      article_count: articleCount,
      enabled: true,
      expert_config_code_list: formState.value.expert_config_code_list,
    };

    // 方案1/2/3：由前端直接生成 job_generation_plan；默认方案：清空 plan
    if (jobCreateMode.value === 'system_random') {
      (payload as any).job_generation_plan = null;
    } else {
      (payload as any).job_generation_plan =
        buildJobGenerationPlan(articleCount);
    }

    if (isEdit.value) {
      await updateJobApi(route.query.id as string, payload);
      message.success('更新成功');
    } else {
      await createJobApi(payload as JobApi.CreateParams);
      message.success('创建成功');
    }
    router.push('/job/list');
  } catch (error: any) {
    const detail =
      error?.response?.data?.detail ??
      error?.response?.data?.message ??
      error?.message ??
      '';
    message.error(
      `${isEdit.value ? '更新失败' : '创建失败'}${detail ? `：${detail}` : ''}`,
    );
  } finally {
    saving.value = false;
  }
}

function handlePrev() {
  currentStep.value--;
}

async function handleNext() {
  const isValid = await validateStep(currentStep.value);
  if (isValid) {
    currentStep.value++;
  }
}

function handleCancel() {
  router.push('/job/list');
}

// 处理步骤点击跳转
async function handleStepClick(targetStep: number) {
  // 如果点击的是当前步骤，不做处理
  if (targetStep === currentStep.value) return;

  // 如果点击的是后面的步骤，需要验证之前的所有步骤
  if (targetStep > currentStep.value) {
    // 验证从当前步骤到目标步骤之前的所有步骤
    for (let i = currentStep.value; i < targetStep; i++) {
      const isValid = await validateStep(i);
      if (!isValid) {
        // 验证失败，停留在当前步骤
        return;
      }
    }
  }

  // 跳转到目标步骤
  currentStep.value = targetStep;
}

// 获取已选择的 Expert 详情（只读展示）
const selectedExperts = computed(() => {
  return formState.value.expert_config_code_list.map((code, index) => {
    const config = expertConfigs.value.find(
      (c) => c.expert_config_code === code,
    );
    return {
      order: index + 1,
      code,
      name: config?.expert_config_name || code,
      description: config?.description || '',
      type: config?.expert_type || '-',
      model: config?.model_code || '-',
      plugin_config: config?.plugin_config || null,
    };
  });
});

function normalizeContextOptions(v: string | string[]): string[] {
  if (Array.isArray(v)) return v.filter((x): x is string => !!x);
  return v ? [v] : [];
}

function mapCreateModeToPlanMode(
  mode: JobCreateMode,
):
  | 'allocation_rules'
  | 'explicit_combinations'
  | 'strategy'
  | 'variants'
  | null {
  if (mode === 'plan1_combinations') return 'explicit_combinations';
  if (mode === 'plan2_rules') return 'allocation_rules';
  if (mode === 'plan3_variants') return 'variants';
  if (mode === 'plan4_strategy') return 'strategy';
  return null;
}

function buildJobGenerationPlan(
  totalCount: number,
): null | Record<string, any> {
  const planMode = mapCreateModeToPlanMode(jobCreateMode.value);
  if (!planMode) return null;

  const safeTotal = Math.max(0, Number.isFinite(totalCount) ? totalCount : 0);

  if (planMode === 'explicit_combinations') {
    const ratios = combinations.value.map((x) => x.ratio);
    const counts = allocateCountsByRatio(safeTotal, ratios);
    const planItems = combinations.value.map((row, idx) => ({
      type: 'item',
      index: idx,
      item_id: row.id,
      name: row.name,
      ratio: row.ratio,
      count: counts[idx] ?? 0,
      expert_param_config: row.expert_param_config,
    }));
    return { mode: planMode, total_count: safeTotal, plan_items: planItems };
  }

  if (planMode === 'allocation_rules') {
    const ratios = rules.value.map((r) => r.ratio);
    const counts = allocateCountsByRatio(safeTotal, ratios);
    const planItems = rules.value.map((r, idx) => ({
      type: 'rule',
      index: idx,
      priority: idx + 1,
      condition: { and: r.conditions },
      ratio: r.ratio,
      count: counts[idx] ?? 0,
      name: r.name,
    }));
    return {
      mode: 'allocation_rules',
      total_count: safeTotal,
      plan_items: planItems,
    };
  }

  if (
    planMode === 'strategy' && // 智能推荐模式使用 v3 的数据结构
    (useSmartSelector.value || useStrategyV3.value)
  ) {
    // 智能推荐模式 / v3 策略模式：多策略维度合并
    const strategySelections = strategyConfigV3.value.selected_strategy_ids.map(
      (id) => ({
        strategy_id: id,
        selected_combo_ids: null, // 使用全部组合
      }),
    );

    // strategy_v3 改为轻量配置：执行时由后端动态拉取合并组合并展开 plan_items
    const targetCount =
      strategyConfigV3.value.total_count > 0
        ? strategyConfigV3.value.total_count
        : safeTotal;

    return {
      mode: 'strategy_v3',
      strategy_selections: strategySelections,
      variable_share_mapping: strategyConfigV3.value.variable_share_mapping,
      total_count: targetCount, // 兼容旧逻辑
      target_count: targetCount,
      // ⭐ 保存采样模式配置（用于回退场景）
      sample_mode: strategySamplingConfig.value.sample_mode,
      primary_strategy_id:
        strategySamplingConfig.value.sample_mode === 'primary_strategy'
          ? strategySamplingConfig.value.primary_strategy_id
          : undefined,
    };
  }

  // variants
  const ratios = selectedVariants.value.map((v) => v.ratio);
  const counts = allocateCountsByRatio(safeTotal, ratios);
  const planItems = selectedVariants.value.map((v, idx) => ({
    type: 'item',
    index: idx,
    item_id: v.id,
    name: v.name,
    ratio: v.ratio,
    count: counts[idx] ?? 0,
    variant_ref: { id: v.id, name: v.name, tags: v.tags },
  }));
  return { mode: 'variants', total_count: safeTotal, plan_items: planItems };
}

function allocateCountsByRatio(total: number, ratios: number[]): number[] {
  const safeTotal = Math.max(0, Number.isFinite(total) ? total : 0);
  if (safeTotal === 0) return ratios.map(() => 0);
  const safeRatios = ratios.map((x) =>
    Number.isFinite(x) ? Math.max(0, x) : 0,
  );
  const sum = safeRatios.reduce((a, b) => a + b, 0);
  if (sum <= 0) return ratios.map(() => 0);

  const raw = safeRatios.map((r) => (safeTotal * r) / sum);
  const base = raw.map((x) => Math.floor(x));
  const remainder = raw.map((x, i) => ({ i, r: x - base[i]! }));
  let left = safeTotal - base.reduce((a, b) => a + b, 0);
  remainder.sort((a, b) => b.r - a.r);
  for (let k = 0; k < remainder.length && left > 0; k++) {
    base[remainder[k]!.i]! += 1;
    left--;
  }
  return base;
}

const plan1RatioSum = computed(() =>
  combinations.value.reduce(
    (acc, x) => acc + (Number.isFinite(x.ratio) ? x.ratio : 0),
    0,
  ),
);
const plan2RatioSum = computed(() =>
  rules.value.reduce(
    (acc, x) => acc + (Number.isFinite(x.ratio) ? x.ratio : 0),
    0,
  ),
);
const plan3RatioSum = computed(() =>
  selectedVariants.value.reduce(
    (acc, x) => acc + (Number.isFinite(x.ratio) ? x.ratio : 0),
    0,
  ),
);

// 方案4 的统计信息
const plan4Stats = computed(() => {
  const config = strategyConfigV3.value;

  const strategyCount = config.selected_strategy_ids?.length ?? 0;

  // 计算变量映射数量
  const mappingCount = config.variable_share_mapping
    ? Object.keys(config.variable_share_mapping).length
    : 0;

  return {
    strategyCount,
    mappingCount,
  };
});

const plan1Counts = computed(() => {
  if (allocationUnitMode.value !== 'ratio')
    return combinations.value.map(() => 0);
  return allocateCountsByRatio(
    previewTotalCount.value,
    combinations.value.map((x) => x.ratio),
  );
});

const plan2Counts = computed(() => {
  if (allocationUnitMode.value !== 'ratio') return rules.value.map(() => 0);
  return allocateCountsByRatio(
    previewTotalCount.value,
    rules.value.map((x) => x.ratio),
  );
});

function getRuleConditionValueOptions(field: RuleCondition['field']): string[] {
  const variableName = field;
  const sets: Array<Set<string>> = [];
  for (const expert of selectedExperts.value) {
    const entries = expertVariableCatalog.value[expert.code] || [];
    const entry = entries.find((x) => x.variable_name === variableName);
    if (!entry || entry.options.length === 0) continue;
    sets.push(new Set(entry.options));
  }
  if (sets.length === 0) return [];
  let intersection = new Set<string>(sets[0]);
  for (let i = 1; i < sets.length; i++) {
    const s = sets[i]!;
    intersection = new Set([...intersection].filter((x) => s.has(x)));
  }
  return [...intersection].toSorted();
}

watch(
  () => plan1Counts.value,
  (counts) => {
    // ⚠️ 避免递归更新：plan1Counts 每次计算都会返回新数组引用，
    // 如果这里无条件回写 combinations，会触发 plan1Counts 重新计算 → watch 再触发 → 死循环。
    const nextCounts = counts.map((x) => x ?? 0);
    const changed = combinations.value.some(
      (row, idx) => (row.count ?? 0) !== (nextCounts[idx] ?? 0),
    );
    if (!changed) return;
    combinations.value = combinations.value.map((x, idx) => ({
      ...x,
      count: nextCounts[idx] ?? 0,
    }));
  },
  { immediate: true },
);

function addCombination() {
  const id = genLocalId('comb');
  combinations.value.push({
    id,
    name: `组合 ${combinations.value.length + 1}`,
    ratio: 0,
  });
  if (allocationUnitMode.value === 'ratio') {
    const sum = combinations.value.reduce((a, b) => a + (b.ratio || 0), 0);
    if (sum < 100) {
      const last = combinations.value[combinations.value.length - 1]!;
      last.ratio += 100 - sum;
    }
  }
}

function copyCombination(id: string) {
  const src = combinations.value.find((x) => x.id === id);
  if (!src) return;
  const nextId = genLocalId('comb');
  combinations.value.push({
    ...src,
    id: nextId,
    name: `${src.name}-复制`,
  });
}

function deleteCombination(id: string) {
  combinations.value = combinations.value.filter((x) => x.id !== id);
  selectedCombinationRowKeys.value = selectedCombinationRowKeys.value.filter(
    (x) => x !== id,
  );
}

function evenSplitCombinations() {
  if (allocationUnitMode.value !== 'ratio') return;
  const n = combinations.value.length;
  if (n <= 0) return;
  const base = Math.floor(100 / n);
  const left = 100 - base * n;
  combinations.value = combinations.value.map((x, idx) => ({
    ...x,
    ratio: base + (idx === 0 ? left : 0),
  }));
}

function openCombinationEditor(id: string) {
  editingCombinationId.value = id;
  initCombinationEditorSelections(id);
}

function closeCombinationEditor() {
  editingCombinationId.value = null;
}

// 移除 job_param_config：组合编辑抽屉仅保留基础信息/预览（参数固定为随机）

function addRule() {
  const base: RuleRow = {
    id: genLocalId('rule'),
    name: `规则 ${rules.value.length + 1}`,
    ratio: 0,
    conditions: [],
  };
  ruleDraft.value = cloneReactive(base);
  editingRuleId.value = base.id;
}

function editRule(id: string) {
  const r = rules.value.find((x) => x.id === id);
  if (!r) return;
  ruleDraft.value = cloneReactive(r);
  editingRuleId.value = id;
}

function saveRuleDraft() {
  if (!ruleDraft.value || !editingRuleId.value) return;
  const name = ruleDraft.value.name?.trim?.() ?? '';
  if (!name) {
    message.warning('请输入规则名称');
    return;
  }
  const ratio = Number(ruleDraft.value.ratio);
  if (!Number.isFinite(ratio) || ratio < 0 || ratio > 100) {
    message.warning('占比(%) 需为 0~100 的数字');
    return;
  }

  const idx = rules.value.findIndex((x) => x.id === editingRuleId.value);
  const next = cloneReactive(ruleDraft.value);
  next.name = name;
  next.ratio = Math.round(ratio);
  // 清理空条件（未选择值/空字段）
  next.conditions = next.conditions.filter(
    (c) =>
      typeof c.field === 'string' &&
      c.field.trim().length > 0 &&
      typeof c.value === 'string' &&
      c.value.trim().length > 0,
  );
  if (idx === -1) {
    rules.value.push(next);
  } else {
    rules.value[idx] = next;
  }
  editingRuleId.value = null;
  ruleDraft.value = null;
  message.success('已保存分流规则');
}

function deleteRule(id: string) {
  rules.value = rules.value.filter((x) => x.id !== id);
}

function closeRuleEditor() {
  editingRuleId.value = null;
  ruleDraft.value = null;
}

async function loadVariantLibrary() {
  if (!formState.value.tenant_id || !formState.value.agent_code) {
    message.warning('请先选择租户与 Agent，再从方案库选择 Variant');
    return;
  }
  variantLibraryLoading.value = true;
  try {
    const list = await getJobVariantListApi({
      tenant_id: formState.value.tenant_id,
      agent_code: formState.value.agent_code,
      enabled: true,
      keyword: variantKeyword.value.trim() || undefined,
      limit: 200,
      skip: 0,
    });
    variantLibrary.value = list || [];
  } catch (error: any) {
    const detail =
      error?.response?.data?.detail ??
      error?.response?.data?.message ??
      error?.message ??
      '';
    message.error(`加载方案库失败${detail ? `：${detail}` : ''}`);
  } finally {
    variantLibraryLoading.value = false;
  }
}

function openVariantPicker() {
  variantPickerOpen.value = true;
  loadVariantLibrary();
}

function closeVariantPicker() {
  variantPickerOpen.value = false;
}

function toggleVariantPick(v: JobVariantApi.JobVariant) {
  const vid = v.variant_id;
  const exists = selectedVariants.value.some((x) => x.id === vid);
  if (exists) {
    selectedVariants.value = selectedVariants.value.filter((x) => x.id !== vid);
    return;
  }
  selectedVariants.value.push({
    id: vid,
    name: v.variant_name,
    tags: v.tags || [],
    ratio: 0,
  });
  if (
    selectedVariants.value.length === 1 &&
    allocationUnitMode.value === 'ratio'
  ) {
    selectedVariants.value[0]!.ratio = 100;
  }
}

function evenSplitVariants() {
  if (allocationUnitMode.value !== 'ratio') return;
  const n = selectedVariants.value.length;
  if (n <= 0) return;
  const base = Math.floor(100 / n);
  const left = 100 - base * n;
  selectedVariants.value = selectedVariants.value.map((x, idx) => ({
    ...x,
    ratio: base + (idx === 0 ? left : 0),
  }));
}

// ==================== 策略模式相关函数 ====================

async function loadStrategyList() {
  strategyLoading.value = true;
  try {
    const res = await getContentStrategiesApi({
      is_active: 1,
      page_size: 100,
    });
    strategyList.value = res.items || [];
  } catch (error) {
    console.error('获取策略列表失败:', error);
    message.error('获取策略列表失败');
  } finally {
    strategyLoading.value = false;
  }
}

function onStrategyChange(value: unknown) {
  const strategyId = value as string;
  strategyConfig.value.strategy_id = strategyId;
  // 清空之前的映射和预览
  strategyConfig.value.variable_share_mapping = {};
  strategyConfig.value.preview_combinations = [];
  // 获取策略详情并自动初始化变量映射
  initVariableMappingFromStrategy(strategyId);
}

// 策略搜索过滤
function filterStrategyOption(
  input: string,
  option?: { label?: unknown; value?: unknown },
) {
  return String(option?.label || '').toLowerCase().includes(input.toLowerCase());
}

// 切换策略选择（多选）
async function onStrategySelectionChange(value: unknown) {
  const selectedIds = (value as string[]) || [];
  strategyConfigV3.value.selected_strategy_ids = selectedIds;

  // 加载合并组合
  await loadMergedCombinations();
  // 自动平均分配篇数
  distributeEvenlyV3();
}

// v3 模式：加载合并组合
async function loadMergedCombinations() {
  const selectedIds = strategyConfigV3.value.selected_strategy_ids;
  if (selectedIds.length === 0) {
    strategyConfigV3.value.merged_combinations = [];
    strategyConfigV3.value.merged_dimensions = [];
    return;
  }

  // 填充 available_strategies（用于主策略选择）
  strategyConfigV3.value.available_strategies = strategyList.value
    .filter((s) => selectedIds.includes(s.id))
    .map((s) => ({
      id: Number.parseInt(s.id),
      name: s.name,
    }));

  mergedCombinationsLoading.value = true;
  try {
    // 仅用于前端配置预览，避免一次拉取过大数据导致接口校验失败或页面渲染压力过高
    const previewTargetCount = Math.min(
      formState.value.article_count,
      MERGE_PREVIEW_TARGET_COUNT_MAX,
    );

    // 构建请求：每个策略使用全部组合
    const strategySelections = selectedIds.map((id) => ({
      strategy_id: id,
      selected_combo_ids: null, // null 表示使用全部组合
    }));

    const result = await mergeStrategyCombinationsApi({
      strategy_selections: strategySelections,
      include_corpus: false,
      target_count: previewTargetCount,
      // 后端支持 'first', 'primary_strategy', 'random' 三种模式
      sample_mode: strategySamplingConfig.value.sample_mode,
      primary_strategy_id:
        strategySamplingConfig.value.sample_mode === 'primary_strategy'
          ? strategySamplingConfig.value.primary_strategy_id
          : undefined,
    });

    // ⚠️ 后端返回的是扁平化的组合列表（可能有重复）
    // 需要按 merged_nodes 分组统计，得到去重后的组合列表
    const comboCountMap = new Map<
      string,
      {
        count: number;
        id: string;
        merged_nodes: any;
        name: string;
        source_combos: any[];
      }
    >();

    for (const combo of result.merged_combinations || []) {
      // 生成唯一键（按 merged_nodes 序列化）
      const key = JSON.stringify(combo.merged_nodes);

      if (comboCountMap.has(key)) {
        // 已存在，增加计数
        const existing = comboCountMap.get(key)!;
        existing.count += 1;
      } else {
        // 新组合，初始化
        comboCountMap.set(key, {
          id: combo.id,
          name: combo.name,
          source_combos: combo.source_combos,
          merged_nodes: combo.merged_nodes,
          count: 1,
        });
      }
    }

    // 转换为数组
    const dedupedCombinations = [...comboCountMap.values()];

    strategyConfigV3.value.merged_dimensions = result.merged_dimensions;
    strategyConfigV3.value.merged_combinations = dedupedCombinations;

    // 🐛 调试日志：统计主维度分配情况
    if (strategySamplingConfig.value.sample_mode === 'primary_strategy') {
      const distribution = new Map<string, number>();
      for (const combo of result.merged_combinations) {
        // 找到主维度 combo_id
        const primarySource = combo.source_combos?.find(
          (sc: any) => sc.is_primary,
        );
        if (primarySource) {
          const primaryId = primarySource.combo_id;
          distribution.set(primaryId, (distribution.get(primaryId) || 0) + 1);
        }
      }
    }

    // 自动分配：根据采样模式自动调用对应的分配逻辑
    if (strategySamplingConfig.value.sample_mode === 'primary_strategy') {
      distributeEvenlyV3();
    } else if (strategySamplingConfig.value.sample_mode === 'random') {
      distributeRandomlyV3();
    } else {
      updateV3TotalCount();
    }
  } catch (error: any) {
    console.error('加载合并组合失败:', error);
    const errorMsg =
      error?.response?.data?.detail || error?.message || '加载合并组合失败';

    // 如果有维度冲突，显示详细的错误弹窗
    if (
      errorMsg.includes('维度冲突') ||
      errorMsg.includes('dimension') ||
      errorMsg.includes('不能重叠') ||
      errorMsg.includes('overlap')
    ) {
      Modal.warning({
        title: '⚠️ 策略维度冲突，无法合并',
        width: 600,
        content: h('div', {}, [
          h(
            'div',
            { style: 'margin-bottom: 12px; font-size: 14px;' },
            '您选择的多个策略包含相同的维度（例如"必带词"），无法在"维度合并模式"下工作。',
          ),
          h(
            'div',
            {
              style:
                'background: #fff1f0; border: 1px solid #ffccc7; padding: 12px; border-radius: 4px; margin-bottom: 16px; color: #cf1322; font-family: monospace; font-size: 13px;',
            },
            errorMsg,
          ),
          h(
            'div',
            { style: 'font-weight: 600; margin-bottom: 8px;' },
            '💡 解决方案：',
          ),
          h(
            'ul',
            { style: 'padding-left: 20px; margin: 0; line-height: 1.8;' },
            [
              h('li', {}, [
                h('b', {}, '切换到「并集模式」（推荐）：'),
                '各策略独立运行，互不干扰，结果取并集。',
              ]),
              h('li', {}, [
                h('b', {}, '调整策略选择：'),
                '只选择维度不重叠的策略进行合并。',
              ]),
            ],
          ),
          h(
            'div',
            { style: 'margin-top: 16px; color: #1890ff; font-weight: 500;' },
            '系统已为您自动切换到「并集模式」，您可以直接继续操作。',
          ),
        ]),
        okText: '我知道了',
      });
      // 自动切换到智能模式
      useStrategyV3.value = false;
      useSmartSelector.value = true;
    } else {
      message.error(errorMsg);
    }
  } finally {
    mergedCombinationsLoading.value = false;
  }
}

// 更新 v3 总数
function updateV3TotalCount() {
  let total = 0;
  for (const combo of strategyConfigV3.value.merged_combinations) {
    total += combo.count;
  }
  strategyConfigV3.value.total_count = total;
}

// v3 平均分配
function distributeEvenlyV3() {
  const total = formState.value.article_count;
  const comboCount = strategyConfigV3.value.merged_combinations.length;

  if (comboCount === 0) return;

  const perCombo = Math.floor(total / comboCount);
  let remainder = total % comboCount;

  for (const combo of strategyConfigV3.value.merged_combinations) {
    combo.count = perCombo + (remainder > 0 ? 1 : 0);
    if (remainder > 0) remainder--;
  }

  updateV3TotalCount();
}

// v3 随机分配（避免任务集中在前几种组合）
function distributeRandomlyV3() {
  const total = formState.value.article_count;
  const combos = strategyConfigV3.value.merged_combinations;

  if (combos.length === 0) return;

  // 先全部归零
  for (const combo of combos) {
    combo.count = 0;
  }

  // 随机分配 total 篇到各个组合
  for (let i = 0; i < total; i++) {
    const randomIndex = Math.floor(Math.random() * combos.length);
    const target = combos[randomIndex];
    if (target) {
      target.count++;
    }
  }

  updateV3TotalCount();
}

// 切换 v3 模式（已废弃，使用 handleStrategyModeChange 替代）
// async function toggleStrategyV3Mode(enabled: boolean) {
//   useStrategyV3.value = enabled;
//   if (enabled) {
//     // 切换到 v3，同步选中的策略
//     strategyConfigV3.value.selected_strategy_ids = [
//       ...strategyConfigV2.value.selected_strategy_ids,
//     ];
//     // 同步变量映射配置
//     strategyConfigV3.value.variable_share_mapping = {
//       ...strategyConfigV2.value.variable_share_mapping,
//     };
//     await loadMergedCombinations();
//   } else {
//     // 切换回 v2，同步选中的策略
//     strategyConfigV2.value.selected_strategy_ids = [
//       ...strategyConfigV3.value.selected_strategy_ids,
//     ];
//     // 同步变量映射配置
//     strategyConfigV2.value.variable_share_mapping = {
//       ...strategyConfigV3.value.variable_share_mapping,
//     };
//     await loadStrategyCombinations();
//   }
// }

// 处理策略模式切换
async function handleStrategyModeChange(mode: 'merge' | 'smart') {
  if (mode === 'smart') {
    useSmartSelector.value = true;
    useStrategyV3.value = false;
    // 先加载策略列表，确保智能选择器有数据
    await loadStrategyList();
    // 智能模式使用 v3 的数据结构
    await loadMergedCombinations();
  } else {
    // merge 模式
    useSmartSelector.value = false;
    useStrategyV3.value = true;
    await loadMergedCombinations();
  }
}

// 处理策略 ID 更新（来自智能选择器）
async function handleStrategyIdsUpdate(strategyIds: string[]) {
  strategyConfigV3.value.selected_strategy_ids = strategyIds;
  // 重新加载合并组合（使用防抖，确保使用最新的采样配置）
  debouncedReloadMergedCombinations();
}

// 处理变量映射更新（来自智能选择器）
function handleVariableMappingsUpdate(
  mappings: Record<string, Array<{ expert_code: string; variable: string }>>,
) {
  strategyConfigV3.value.variable_share_mapping = mappings;
}

// 检查 v3 模式是否配置了变量映射
const hasV3MappingConfigured = computed(() => {
  const mapping = strategyConfigV3.value.variable_share_mapping;
  return Object.values(mapping).some((arr) => arr && arr.length > 0);
});

// 当目标篇数变化时，自动重新分配（仅方案4策略组合模式）
watch(
  () => formState.value.article_count,
  () => {
    if (
      jobCreateMode.value === 'plan4_strategy' && // 如果已有分配数据，重新平均分配
      useStrategyV3.value &&
      strategyConfigV3.value.merged_combinations.length > 0
    ) {
      distributeEvenlyV3();
    }
  },
);

async function initVariableMappingFromStrategy(strategyId: string) {
  const strategy = strategyList.value.find((s) => s.id === strategyId);
  if (!strategy) return;

  // 根据策略的维度自动初始化变量映射
  // 默认将策略维度映射到同名的 Expert 变量
  const mapping: Record<string, VariableShareMappingItem[]> = {};

  // 从 node_pools 提取维度
  if (strategy.node_pools) {
    for (const dimType of Object.keys(strategy.node_pools)) {
      mapping[dimType] = [];
    }
  }
  // 从 defined_combinations 提取维度（fallback）
  else if (
    strategy.defined_combinations &&
    strategy.defined_combinations.length > 0
  ) {
    const firstCombo = strategy.defined_combinations[0];
    if (firstCombo?.nodes) {
      for (const dimType of Object.keys(firstCombo.nodes)) {
        mapping[dimType] = [];
      }
    }
  }

  strategyConfig.value.variable_share_mapping = mapping;
}

function openStrategyMappingDrawer() {
  if (!strategyConfig.value.strategy_id) {
    message.warning('请先选择关键词策略');
    return;
  }
  strategyMappingDrawerOpen.value = true;
  // 打开抽屉时自动执行映射
  nextTick(() => {
    autoMapVariablesToDimensions();
  });
}

function closeStrategyMappingDrawer() {
  strategyMappingDrawerOpen.value = false;
}

// 自动映射变量到维度
function autoMapVariablesToDimensions() {
  const dimensions = currentMappingDimensions.value;
  const experts = allExpertVariables.value;
  const mapping = getCurrentMapping();

  let mappedCount = 0;

  for (const dim of dimensions) {
    // 如果该维度已有映射，跳过（保留用户手动配置）
    const existingMappings = mapping[dim.dimension_type];
    if (existingMappings && existingMappings.length > 0) {
      continue;
    }

    // 初始化维度映射数组
    if (!mapping[dim.dimension_type]) {
      mapping[dim.dimension_type] = [];
    }

    // 遍历所有 Expert 的变量
    for (const expert of experts) {
      for (const variable of expert.variables) {
        // 检查是否已存在映射
        const exists = mapping[dim.dimension_type]!.some(
          (m) =>
            m.expert_code === expert.expert_code && m.variable === variable,
        );
        if (exists) {
          continue;
        }

        // 匹配规则：
        // 1. 精确匹配：变量名 === 维度名 或 变量名 === 维度类型
        // 2. 包含匹配：变量名包含维度名 或 维度名包含变量名
        const variableLower = variable.toLowerCase().trim();
        const dimNameLower = dim.dimension_name.toLowerCase().trim();
        const dimTypeLower = dim.dimension_type.toLowerCase().trim();

        let shouldMap = false;

        // 精确匹配（优先级最高）
        if (variableLower === dimNameLower || variableLower === dimTypeLower) {
          shouldMap = true;
        }
        // 包含匹配（优先级较低，但更灵活）
        else if (
          variableLower.includes(dimNameLower) ||
          dimNameLower.includes(variableLower) ||
          variableLower.includes(dimTypeLower) ||
          dimTypeLower.includes(variableLower)
        ) {
          shouldMap = true;
        }

        if (shouldMap) {
          mapping[dim.dimension_type]!.push({
            expert_code: expert.expert_code,
            variable,
          });
          mappedCount++;
        }
      }
    }
  }

  if (mappedCount > 0) {
    // console.log(`自动映射了 ${mappedCount} 个变量到维度`);
  }
}

// 获取当前使用的映射对象（根据 v1/v2/v3 模式）
function getCurrentMapping(): Record<string, VariableShareMappingItem[]> {
  if (useStrategyV3.value) {
    return strategyConfigV3.value.variable_share_mapping;
  }
  if (useStrategyV2.value) {
    return strategyConfigV2.value.variable_share_mapping;
  }
  return strategyConfig.value.variable_share_mapping;
}

// 检查变量是否已映射
function isVariableMapped(
  dimension: string,
  expertCode: string,
  variable: string,
): boolean {
  const mapping = getCurrentMapping();
  return (
    mapping[dimension]?.some(
      (m) => m.expert_code === expertCode && m.variable === variable,
    ) || false
  );
}

// 切换变量映射
function toggleVariableMapping(
  dimension: string,
  expertCode: string,
  variable: string,
) {
  if (isVariableMapped(dimension, expertCode, variable)) {
    removeVariableMapping(dimension, expertCode, variable);
  } else {
    addVariableMapping(dimension, expertCode, variable);
  }
}

function addVariableMapping(
  dimension: string,
  expertCode: string,
  variable: string,
) {
  const mapping = getCurrentMapping();
  if (!mapping[dimension]) {
    mapping[dimension] = [];
  }
  // 检查是否已存在
  const exists = mapping[dimension]!.some(
    (m) => m.expert_code === expertCode && m.variable === variable,
  );
  if (!exists) {
    mapping[dimension]!.push({
      expert_code: expertCode,
      variable,
    });
  }
}

function removeVariableMapping(
  dimension: string,
  expertCode: string,
  variable: string,
) {
  const mapping = getCurrentMapping();
  if (!mapping[dimension]) return;
  mapping[dimension] = mapping[dimension]!.filter(
    (m) => !(m.expert_code === expertCode && m.variable === variable),
  );
}

async function previewStrategyCombinations() {
  if (!strategyConfig.value.strategy_id) {
    message.warning('请先选择关键词策略');
    return;
  }
  strategyPreviewLoading.value = true;
  try {
    const count = formState.value.article_count;
    const res = await generateCombinationsApi(
      strategyConfig.value.strategy_id,
      {
        count,
        overrides: strategyConfig.value.strategy_overrides,
      },
    );
    // 兼容旧版 API 响应格式（可能没有 id 和 name）
    strategyConfig.value.preview_combinations = (res.combinations || []).map(
      (c, idx) => ({
        id: (c as ContentStrategyApi.CombinationItem).id || `combo_${idx}`,
        name:
          (c as ContentStrategyApi.CombinationItem).name || `组合 ${idx + 1}`,
        nodes: c.nodes,
      }),
    );
    message.success(
      `预览生成 ${strategyConfig.value.preview_combinations.length} 个组合`,
    );
  } catch (error) {
    console.error('预览组合失败:', error);
    message.error('预览组合失败');
  } finally {
    strategyPreviewLoading.value = false;
  }
}

// 获取选中策略的维度列表（v1 模式）
const selectedStrategyDimensions = computed(() => {
  if (!strategyConfig.value.strategy_id) return [];
  const strategy = strategyList.value.find(
    (s) => s.id === strategyConfig.value.strategy_id,
  );
  return strategy?.dimensions || [];
});

// v3 合并维度列表
const v3MergedDimensions = computed(() => {
  return strategyConfigV3.value.merged_dimensions.map((dim) => ({
    dimension_type: dim,
    dimension_name: dim,
  }));
});

// 当前映射配置使用的维度列表（根据 v1/v2/v3 模式动态切换）
const currentMappingDimensions = computed(() => {
  if (useStrategyV3.value || useSmartSelector.value) {
    return v3MergedDimensions.value;
  }
  return selectedStrategyDimensions.value;
});

function prune_variable_share_mapping(args: {
  mapping: Record<string, VariableShareMappingItem[]>;
  valid_dimension_keys: string[];
  valid_expert_variables: Map<string, Set<string>>;
}): { removed_count: number } {
  const { mapping, valid_dimension_keys, valid_expert_variables } = args;

  let removedCount = 0;
  const validDimSet = new Set(valid_dimension_keys);

  for (const key of Object.keys(mapping)) {
    if (!validDimSet.has(key)) {
      removedCount += mapping[key]?.length || 0;
      delete mapping[key];
    }
  }

  for (const [dimKey, items] of Object.entries(mapping)) {
    if (!items || items.length === 0) continue;
    const nextItems = items.filter((m) => {
      const vars = valid_expert_variables.get(m.expert_code);
      return !!vars && vars.has(m.variable);
    });
    removedCount += items.length - nextItems.length;
    mapping[dimKey] = nextItems;
  }

  return { removed_count: removedCount };
}

function build_valid_expert_variables(): Map<string, Set<string>> {
  const m = new Map<string, Set<string>>();
  for (const expert of allExpertVariables.value) {
    m.set(expert.expert_code, new Set(expert.variables));
  }
  return m;
}

const mappingDimensionSignature = computed(() =>
  currentMappingDimensions.value
    .map((d) => d.dimension_type)
    .filter(Boolean)
    .join('|'),
);

watch(
  () => mappingDimensionSignature.value,
  (newSig, oldSig) => {
    // 首次初始化不提示；编辑/回填期间不提示
    if (!oldSig) return;
    if (loading.value || prefilling.value) return;
    if (newSig === oldSig) return;

    const mapping = getCurrentMapping();
    const { removed_count } = prune_variable_share_mapping({
      mapping,
      valid_dimension_keys: currentMappingDimensions.value.map(
        (d) => d.dimension_type,
      ),
      valid_expert_variables: build_valid_expert_variables(),
    });

    if (removed_count > 0) {
      message.warning(
        `检测到策略维度已变更，已自动移除 ${removed_count} 条无效映射，请检查变量映射`,
      );
    }
  },
);

// 获取所有 Expert 的变量列表（用于映射配置）
const allExpertVariables = computed(() => {
  const result: Array<{
    expert_code: string;
    expert_name: string;
    variables: string[];
  }> = [];
  for (const expert of selectedExperts.value) {
    const variables = new Set<string>();
    const catalog = expertVariableCatalog.value[expert.code] || [];
    for (const entry of catalog) {
      variables.add(entry.variable_name);
    }
    result.push({
      expert_code: expert.code,
      expert_name: expert.name,
      variables: [...variables].toSorted(),
    });
  }
  return result;
});

// 移除 job_param_config：不再维护"自定义参数"配置与编辑逻辑

watch(
  () => [...formState.value.expert_config_code_list],
  () => {},
);

// ==================== 保存组合为 Variant（方案库） ====================
const saveVariantModalOpen = ref(false);
const saveVariantTargetCombinationId = ref<null | string>(null);
const saveVariantForm = ref({
  variant_name: '',
  tags: [] as string[],
});

function openSaveVariantModal(combId: string) {
  saveVariantTargetCombinationId.value = combId;
  const row = combinations.value.find((x) => x.id === combId);
  saveVariantForm.value = {
    variant_name: row ? `${row.name}-方案包` : '',
    tags: [],
  };
  saveVariantModalOpen.value = true;
}

function closeSaveVariantModal() {
  saveVariantModalOpen.value = false;
  saveVariantTargetCombinationId.value = null;
}

async function submitSaveVariant() {
  const combId = saveVariantTargetCombinationId.value;
  if (!combId) return;
  if (!formState.value.tenant_id || !formState.value.agent_code) {
    message.warning('请先选择租户与 Agent');
    return;
  }
  const row = combinations.value.find((x) => x.id === combId);
  if (!row) {
    message.warning('组合不存在');
    return;
  }
  if (!saveVariantForm.value.variant_name.trim()) {
    message.warning('请输入方案包名称');
    return;
  }

  try {
    await createJobVariantApi({
      tenant_id: formState.value.tenant_id,
      agent_code: formState.value.agent_code,
      variant_name: saveVariantForm.value.variant_name.trim(),
      tags: saveVariantForm.value.tags,
      expert_config_code_list: formState.value.expert_config_code_list,
      expert_param_config: row.expert_param_config || {},
      enabled: true,
      remark: `从任务创建页组合“${row.name}”保存`,
    });
    message.success('已保存为方案包');
    closeSaveVariantModal();
  } catch (error: any) {
    const detail =
      error?.response?.data?.detail ??
      error?.response?.data?.message ??
      error?.message ??
      '';
    message.error(`保存失败${detail ? `：${detail}` : ''}`);
  }
}

onMounted(() => {
  fetchExpertConfigs();
  fetchTenants();
  // 预加载策略列表，确保智能推荐组件有数据可用
  loadStrategyList();
  // 加载所有agent列表（编辑和创建都需要）
  fetchAllAgents();
  if (isEdit.value) {
    fetchJobDetail();
    return;
  }
  // 直接打开页面时，预填充query参数
  prefillFromQuery();
  // 默认方案不创建 Draft；切到方案1/2/3时再懒创建
});

// 关键：同路由仅 query 变化时，组件不会重新挂载，需要监听 query 来重新预填
watch(
  () => [route.query.agent_code, route.query.tenant_id],
  () => {
    prefillFromQuery();
  },
);

// 切换创建方式不需要额外请求：job_generation_plan 由前端直接生成并保存
</script>

<template>
  <div class="job-create-page">
    <!-- 粘性筛选头部 -->
    <div
      class="sticky top-0 z-10 -mx-4 -mt-4 mb-3 bg-background/90 px-4 pb-4 pt-2 shadow-lg backdrop-blur-md"
      style="border-bottom: 1px solid hsl(var(--border) / 30%)"
    >
      <!-- 标题行 -->
      <div class="mb-2 flex items-center justify-between gap-3">
        <span
          class="bg-gradient-to-r from-[hsl(var(--primary))] to-[#22c55e] bg-clip-text text-xl font-bold text-transparent"
        >
          {{ isEdit ? '编辑生文任务' : '生成文章' }}
        </span>
        <Button type="text" @click="handleCancel">
          <span>⬅️ 返回列表</span>
        </Button>
      </div>
    </div>
    <Card :bordered="false" :loading="loading">
      <!-- 生文任务操作指南 -->
      <Alert
        v-if="!guideDismissed"
        :description="null"
        class="guide-alert"
        type="info"
        closable
        @close="guideDismissed = true"
      >
        <template #message>
          <span>📋 生文任务操作指南</span>
        </template>
        <template #default>
          <div class="guide-content">
            <p>创建生文任务的完整流程如下：</p>
            <ol class="guide-steps">
              <li><strong>上传业务规则</strong> - 在业务规则页上传活动规则包</li>
              <li>
                <strong>创建 Agent</strong> - 选择一个 Agent 模板，创建或复制
                Agent
              </li>
              <li>
                <strong>启动任务</strong> - 配置内容策略，选择
                Expert，开始执行生文
              </li>
            </ol>
            <div class="guide-actions">
              <Space>
                <Button
                  size="small"
                  @click="router.push('/business-rules')"
                >
                  前往业务规则
                </Button>
                <Button size="small" @click="router.push('/agent/workbench')">
                  前往 Agent 工作台
                </Button>
              </Space>
            </div>
          </div>
        </template>
      </Alert>

      <Steps :current="currentStep" class="steps-container">
        <Step
          v-for="(step, index) in steps"
          :key="step.title"
          :description="step.description"
          :title="step.title"
          clickable
          @click="handleStepClick(index)"
        />
      </Steps>

      <div class="form-container">
        <Form :model="formState" layout="vertical">
          <!-- Step 0: 业务配置 -->
          <div v-show="currentStep === 0" class="step-content">
            <Alert
              class="alert-info"
              description="选择智能体后，将自动加载其默认的专家模块编排配置。"
              message="业务配置"
              show-icon
              type="info"
            />
            <FormItem
              :rules="[{ required: true, message: '请选择使用的智能体' }]"
              label="使用智能体 (产品模板)"
              name="agent_code"
            >
              <Select
                v-model:value="formState.agent_code"
                :options="agentOptions"
                placeholder="请选择智能体"
                show-search
              />
              <div v-if="formState.agent_code" class="form-tip">
                💡
                选择智能体后，将自动加载其默认的专家模块编排配置；后续可在"任务参数配置"中选择随机或自定义参数。
              </div>
            </FormItem>

            <!-- 自动生成的任务名称 -->
            <FormItem label="任务名称（自动生成）">
              <Input
                :value="formState.job_name"
                disabled
                placeholder="选择智能体后自动生成"
                style="color: hsl(var(--muted-foreground))"
              />
            </FormItem>

            <FormItem label="描述" name="description">
              <Textarea
                v-model:value="formState.description"
                :maxlength="500"
                :rows="4"
                placeholder="任务的功能描述..."
                show-count
              />
            </FormItem>

            <FormItem
              :rules="[
                {
                  required: true,
                  type: 'number',
                  message: '请输入目标文章篇数',
                },
              ]"
              label="目标文章篇数"
              name="article_count"
            >
              <Space :size="12">
                <InputNumber
                  v-model:value="formState.article_count"
                  :max="10000"
                  :min="1"
                  placeholder="请输入目标文章篇数（最小 1）"
                  style="width: 120px"
                />
                <Button size="small" @click="formState.article_count = 10">
                  10篇
                </Button>
                <Button size="small" @click="formState.article_count = 30">
                  30篇
                </Button>
                <Button size="small" @click="formState.article_count = 100">
                  100篇
                </Button>
              </Space>
              <div v-if="jobCreateMode === 'plan4_strategy'" class="form-tip">
                💡 策略组合模式下，策略中配置的数量将覆盖此值
              </div>
            </FormItem>
          </div>

          <!-- Step 1: 任务参数配置 -->
          <div v-show="currentStep === 1" class="step-content">
            <Alert
              class="alert-info"
              :description="modeTips[jobCreateMode].desc"
              :message="modeTips[jobCreateMode].title"
              show-icon
              type="info"
            />

            <div class="create-mode-header">
              <FormItem label="创建方式" name="job_create_mode">
                <RadioGroup v-model:value="jobCreateMode">
                  <Radio value="system_random">默认方案：系统随机参数</Radio>
                  <Radio value="plan1_combinations">方案1：组合表格</Radio>
                  <Radio value="plan2_rules">方案2：分流规则</Radio>
                  <Radio value="plan3_variants">方案3：方案包</Radio>
                  <Radio value="plan4_strategy">方案4：策略组合</Radio>
                </RadioGroup>
              </FormItem>

              <FormItem
                v-if="jobCreateMode !== 'system_random'"
                label="分配单位"
                name="allocation_unit_mode"
              >
                <RadioGroup v-model:value="allocationUnitMode">
                  <Radio value="ratio">按占比</Radio>
                  <Radio value="count" disabled>按篇数（后续支持）</Radio>
                </RadioGroup>
                <div class="form-tip">
                  💡 预览分配总篇数：{{ previewTotalCount }}
                </div>
              </FormItem>
            </div>

            <!-- 默认方案：系统随机参数 -->
            <div v-if="jobCreateMode === 'system_random'"></div>

            <!-- 方案1：组合表格 -->
            <div v-else-if="jobCreateMode === 'plan1_combinations'">
              <div class="plan-toolbar">
                <Space>
                  <Button type="primary" @click="addCombination">
                    + 新增组合
                  </Button>
                  <Button
                    @click="evenSplitCombinations"
                    :disabled="combinations.length === 0"
                  >
                    占比均分
                  </Button>
                </Space>
                <Space>
                  <Tag :color="plan1RatioSum === 100 ? 'green' : 'orange'">
                    占比合计：{{ plan1RatioSum }}%
                  </Tag>
                  <Tag color="blue">预览总篇数：{{ previewTotalCount }}</Tag>
                </Space>
              </div>

              <div v-if="combinations.length === 0" class="empty-flow">
                <span>尚未添加组合，点击“+ 新增组合”开始。</span>
              </div>

              <Table
                v-else
                :data-source="combinations"
                :columns="plan1CombinationColumns"
                :pagination="false"
                row-key="id"
                size="middle"
                :row-selection="{
                  selectedRowKeys: selectedCombinationRowKeys,
                  onChange: (keys: any[]) =>
                    (selectedCombinationRowKeys = keys as string[]),
                }"
              >
                <template #bodyCell="{ column, record, index }">
                  <template v-if="column.key === 'ratio'">
                    <InputNumber
                      v-model:value="record.ratio"
                      :max="100"
                      :min="0"
                      :precision="0"
                      style="width: 120px"
                    />
                  </template>
                  <template v-else-if="column.key === 'count'">
                    <Tag color="blue">
                      {{ plan1Counts[index] ?? record.count ?? 0 }}
                    </Tag>
                  </template>
                  <template v-else-if="column.key === 'action'">
                    <Space>
                      <Button
                        type="link"
                        @click="openCombinationEditor(record.id)"
                      >
                        编辑
                      </Button>
                      <Button type="link" @click="copyCombination(record.id)">
                        复制
                      </Button>
                      <Button
                        type="link"
                        @click="openSaveVariantModal(record.id)"
                      >
                        保存为方案包
                      </Button>
                      <Popconfirm
                        title="确认删除该组合？"
                        ok-text="确定"
                        cancel-text="取消"
                        @confirm="deleteCombination(record.id)"
                      >
                        <Button
                          type="link"
                          danger
                          :disabled="record.id === 'default'"
                        >
                          删除
                        </Button>
                      </Popconfirm>
                      <Tag v-if="record.id === 'default'" color="purple">
                        可提交
                      </Tag>
                      <Tag v-if="record.expert_param_config" color="green">
                        已配置变量
                      </Tag>
                    </Space>
                  </template>
                </template>
              </Table>

              <Drawer
                :open="combinationDrawerOpen"
                :title="`编辑组合详情：${editingCombination?.name ?? ''}`"
                width="720"
                @close="closeCombinationEditor"
              >
                <Alert
                  class="alert-info"
                  message="说明"
                  description="这里配置的是“组合级变量选择”。未选择的变量将保持随机；仅对当前组合生效。"
                  show-icon
                  type="info"
                />

                <Alert
                  v-if="emptyIntersectionWarnings.length > 0"
                  class="alert-warning"
                  message="存在无交集变量"
                  :description="`以下变量在同名跨多个插件时候选值交集为空：${emptyIntersectionWarnings
                    .slice(0, 8)
                    .map((x) => `${x.expert_code}.${x.variable_name}`)
                    .join(
                      '、',
                    )}${emptyIntersectionWarnings.length > 8 ? '…' : ''}。该变量将无法随机/无法选择，请检查专家模块的插件配置（variable_mapping）是否正确。`"
                  show-icon
                  type="warning"
                />

                <div class="combination-editor">
                  <div
                    v-for="expert in selectedExperts"
                    :key="expert.code"
                    class="expert-card"
                  >
                    <div class="expert-card-header">
                      <div class="expert-title">
                        <span class="expert-name"
                          >{{ expert.order }}. {{ expert.name }}</span
                        >
                        <Tag color="blue">{{ expert.code }}</Tag>
                      </div>
                      <div class="expert-meta text-muted-foreground">
                        <span>{{ expert.type }}</span>
                        <span v-if="expert.model"> · {{ expert.model }}</span>
                      </div>
                    </div>

                    <Divider style="margin: 10px 0" />

                    <div
                      v-if="
                        (expertVariableCatalog[expert.code]?.length ?? 0) === 0
                      "
                      class="empty-flow"
                    >
                      <span class="text-muted-foreground"
                        >该专家模块未配置变量（插件配置为空或无变量映射）。</span
                      >
                    </div>

                    <div v-else class="vars">
                      <div
                        v-for="v in expertVariableCatalog[expert.code]"
                        :key="`${expert.code}-${v.variable_name}`"
                        class="var-row"
                      >
                        <div class="var-name">
                          <span class="var-key">{{ v.variable_name }}</span>
                          <Tag v-if="v.plugin_codes.length > 1" color="purple">
                            跨 {{ v.plugin_codes.length }} 个插件
                          </Tag>
                          <Tag v-if="v.options.length === 0" color="red">
                            无交集
                          </Tag>
                        </div>

                        <div class="var-select">
                          <Select
                            :value="
                              combinationEditorSelections[expert.code]?.[
                                v.variable_name
                              ]
                            "
                            :options="
                              v.options.map((x) => ({ label: x, value: x }))
                            "
                            :disabled="v.options.length === 0"
                            allow-clear
                            placeholder="不选=随机"
                            show-search
                            :filter-option="true"
                            style="width: 420px"
                            @update:value="
                              (val) =>
                                setCombinationSelection(
                                  expert.code,
                                  v.variable_name,
                                  val as any,
                                )
                            "
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="drawer-footer">
                  <Space>
                    <Button @click="resetCombinationEditor">
                      清空选择（回到随机）
                    </Button>
                  </Space>
                  <Space>
                    <Button @click="closeCombinationEditor">取消</Button>
                    <Button type="primary" @click="saveCombinationEditor">
                      保存
                    </Button>
                  </Space>
                </div>
              </Drawer>
            </div>

            <!-- 方案2：分流规则 -->
            <div v-else-if="jobCreateMode === 'plan2_rules'">
              <div class="plan-toolbar">
                <Space>
                  <Button type="primary" @click="addRule">+ 新增规则</Button>
                </Space>
                <Space>
                  <Tag :color="plan2RatioSum === 100 ? 'green' : 'orange'">
                    占比合计：{{ plan2RatioSum }}%
                  </Tag>
                  <Tag color="blue">预览总篇数：{{ previewTotalCount }}</Tag>
                </Space>
              </div>

              <div v-if="rules.length === 0" class="empty-flow">
                <span>尚未添加规则，点击“+ 新增规则”开始。</span>
              </div>

              <div class="rules-list">
                <div v-for="r in rules" :key="r.id" class="rule-card">
                  <div class="rule-card-header">
                    <div class="rule-card-title">
                      <span class="rule-card-name">{{ r.name }}</span>
                      <Tag color="purple">{{ r.ratio }}%</Tag>
                      <Tag color="blue">
                        {{
                          plan2Counts[rules.findIndex((x) => x.id === r.id)] ??
                          0
                        }}篇
                      </Tag>
                    </div>
                    <Space>
                      <Button type="link" @click="editRule(r.id)">编辑</Button>
                      <Popconfirm
                        title="确认删除该规则？"
                        ok-text="确定"
                        cancel-text="取消"
                        @confirm="deleteRule(r.id)"
                      >
                        <Button type="link" danger>删除</Button>
                      </Popconfirm>
                    </Space>
                  </div>
                  <div class="rule-conditions">
                    <template v-if="r.conditions.length > 0">
                      <Tag
                        v-for="(c, idx) in r.conditions"
                        :key="`${r.id}-${idx}`"
                        color="blue"
                      >
                        {{ c.field }} {{ c.op }} {{ c.value || '-' }}
                      </Tag>
                    </template>
                    <span v-else class="text-muted-foreground">
                      未配置条件
                    </span>
                  </div>
                  <div class="rule-preview">
                    <span class="text-muted-foreground">
                      命中预览：后端校验后返回“命中组合数/冲突/抽样示例”
                    </span>
                  </div>
                </div>
              </div>

              <Drawer
                :open="ruleDrawerOpen"
                title="编辑分流规则"
                width="640"
                @close="closeRuleEditor"
              >
                <Alert
                  class="alert-info"
                  message="说明"
                  description="当前规则编辑仅支持简单条件（且关系），命中预览为预留功能。后续将接入更完善的校验机制。"
                  show-icon
                  type="info"
                />

                <div v-if="ruleDraft" class="rule-editor">
                  <Form layout="vertical">
                    <FormItem label="规则名称">
                      <Input
                        v-model:value="ruleDraft.name"
                        placeholder="如：体验型占比"
                      />
                    </FormItem>
                    <FormItem label="占比(%)">
                      <InputNumber
                        v-model:value="ruleDraft.ratio"
                        :min="0"
                        :max="100"
                        :precision="0"
                        style="width: 200px"
                      />
                    </FormItem>
                    <Divider />
                    <FormItem label="条件（且）">
                      <div class="cond-list">
                        <div
                          v-for="(c, idx) in ruleDraft.conditions"
                          :key="`cond-${idx}`"
                          class="cond-row"
                        >
                          <Select
                            v-model:value="c.field"
                            style="width: 120px"
                            :options="plan2FieldOptions"
                            show-search
                            :filter-option="true"
                          />
                          <Select
                            v-model:value="c.op"
                            style="width: 80px"
                            :options="[
                              { label: '=', value: '=' },
                              { label: '≠', value: '≠' },
                            ]"
                          />
                          <Select
                            v-model:value="c.value"
                            style="width: 100%"
                            :options="
                              getRuleConditionValueOptions(c.field).map(
                                (x) => ({
                                  label: x,
                                  value: x,
                                }),
                              )
                            "
                            allow-clear
                            show-search
                            placeholder="选择变量取值（下拉仅展示交集）"
                          />
                          <Button
                            danger
                            @click="ruleDraft.conditions.splice(idx, 1)"
                            style="min-width: 64px"
                          >
                            删除
                          </Button>
                        </div>
                        <Button
                          type="dashed"
                          style="width: 100%"
                          @click="
                            ruleDraft.conditions.push({
                              field: getDefaultRuleField(),
                              op: '=',
                              value: undefined,
                            })
                          "
                        >
                          + 添加条件
                        </Button>
                      </div>
                    </FormItem>
                    <Divider />
                    <Space>
                      <Button @click="closeRuleEditor">取消</Button>
                      <Button type="primary" @click="saveRuleDraft">
                        保存
                      </Button>
                    </Space>
                  </Form>
                </div>
              </Drawer>
            </div>

            <!-- 方案4：策略组合 -->
            <div v-else-if="jobCreateMode === 'plan4_strategy'">
              <!-- 策略选择模式切换 -->
              <div class="strategy-mode-switch">
                <Space wrap>
                  <span>选择模式：</span>
                  <RadioGroup
                    :value="useSmartSelector ? 'smart' : 'merge'"
                    button-style="solid"
                    size="small"
                    @change="
                      (e: any) => handleStrategyModeChange(e.target.value)
                    "
                  >
                    <Radio.Button value="smart">
                      <span style="color: hsl(var(--primary))">✨</span>
                      智能推荐
                    </Radio.Button>
                  </RadioGroup>
                </Space>
              </div>

              <!-- 智能策略选择器 -->
              <div v-if="useSmartSelector" class="smart-selector-section">
                <StrategySmartSelector
                  :expert-variables="allExpertVariables"
                  :strategies="strategyList"
                  :selected-strategy-ids="
                    strategyConfigV3.selected_strategy_ids
                  "
                  :variable-mappings="strategyConfigV3.variable_share_mapping"
                  :tenant-code="String(formState.tenant_id || '')"
                  :loading="strategyLoading"
                  @update:selected-strategy-ids="handleStrategyIdsUpdate"
                  @update:variable-mappings="handleVariableMappingsUpdate"
                  @open-mapping-drawer="openStrategyMappingDrawer"
                />

                <!-- 采样配置卡片 -->
                <Card size="small" class="sampling-config-card">
                  <template #title>
                    <div class="card-title">
                      <span>🎲 采样配置</span>
                      <Tag color="blue">智能控制</Tag>
                    </div>
                  </template>

                  <Space direction="vertical" style="width: 100%" size="middle">
                    <!-- 采样模式选择 -->
                    <div>
                      <div class="config-label">采样模式</div>
                      <RadioGroup
                        v-model:value="strategySamplingConfig.sample_mode"
                        button-style="solid"
                      >
                        <RadioButton value="primary_strategy">
                          <Tooltip
                            title="主策略优先：主策略的每个组合都会被均匀使用"
                          >
                            <span style="color: hsl(var(--primary))">
                              🌟 主策略优先
                            </span>
                          </Tooltip>
                        </RadioButton>
                        <RadioButton value="random">
                          <Tooltip title="全随机：完全随机分配到各个组合">
                            <span>🎲 全随机</span>
                          </Tooltip>
                        </RadioButton>
                      </RadioGroup>
                    </div>

                    <!-- 主策略选择（仅当选择主策略优先模式时显示） -->
                    <div
                      v-if="
                        strategySamplingConfig.sample_mode ===
                        'primary_strategy'
                      "
                    >
                      <div class="config-label">
                        选择主策略
                        <Tag
                          color="orange"
                          size="small"
                          style="margin-left: 8px"
                        >
                          必填
                        </Tag>
                      </div>
                      <Select
                        v-model:value="
                          strategySamplingConfig.primary_strategy_id
                        "
                        placeholder="请选择主策略"
                        style="width: 100%"
                        :options="
                          strategyConfigV3.available_strategies.map((s) => ({
                            label: s.name,
                            value: s.id,
                          }))
                        "
                        :filter-option="
                          (input: string, option?: { label?: unknown }) =>
                            String(option?.label || '')
                              .toLowerCase()
                              .includes(input.toLowerCase())
                        "
                        show-search
                        allow-clear
                      >
                        <template #suffixIcon>
                          <Tooltip title="主策略的每个组合都会被均匀使用">
                            <InfoCircleOutlined
                              style="color: hsl(var(--muted-foreground))"
                            />
                          </Tooltip>
                        </template>
                      </Select>
                      <div
                        v-if="strategySamplingConfig.primary_strategy_id"
                        class="hint-text"
                      >
                        {{
                          strategyConfigV3.available_strategies.find(
                            (s) =>
                              s.id ===
                              strategySamplingConfig.primary_strategy_id,
                          )?.name
                        }}
                        的每个组合都会被均匀使用
                      </div>
                    </div>
                  </Space>
                </Card>
              </div>

              <!-- v3 多策略维度合并模式 -->
              <div v-else-if="useStrategyV3" class="strategy-v3-section">
                <!-- 策略模式说明 -->
                <Alert type="success" show-icon class="strategy-mode-hint">
                  <template #message>
                    <span class="hint-title">🔀 维度合并模式</span>
                  </template>
                  <template #description>
                    <div class="hint-content">
                      <div class="hint-item">
                        <Tag color="green">合并维度</Tag>
                        <span>多个策略的维度合并到一篇文章中（笛卡尔积）</span>
                      </div>
                      <div class="hint-item">
                        <Tag color="orange">注意</Tag>
                        <span>各策略的维度不能重叠，否则会报错</span>
                      </div>
                    </div>
                  </template>
                </Alert>

                <!-- 变量映射配置卡片 -->
                <Card
                  v-if="strategyConfigV3.selected_strategy_ids.length > 0"
                  size="small"
                  class="mapping-config-card"
                >
                  <template #title>
                    <div class="mapping-card-header">
                      <span>🔗 变量映射配置</span>
                      <Button
                        type="link"
                        size="small"
                        @click="openStrategyMappingDrawer"
                      >
                        详细配置
                      </Button>
                    </div>
                  </template>

                  <!-- 合并维度展示 -->
                  <div class="merged-dimensions">
                    <span class="label">合并维度：</span>
                    <Space wrap size="small">
                      <Tag
                        v-for="dim in strategyConfigV3.merged_dimensions"
                        :key="dim"
                        color="purple"
                      >
                        {{ dim }}
                      </Tag>
                    </Space>
                  </div>

                  <!-- 已配置的映射摘要 -->
                  <div v-if="hasV3MappingConfigured" class="mapping-summary">
                    <div
                      v-for="(
                        mappings, dimType
                      ) in strategyConfigV3.variable_share_mapping"
                      :key="dimType"
                      class="mapping-summary-item"
                    >
                      <Tag color="purple">{{ dimType }}</Tag>
                      <span class="mapping-arrow">→</span>
                      <Space wrap size="small">
                        <Tag
                          v-for="m in mappings"
                          :key="`${m.expert_code}-${m.variable}`"
                          color="blue"
                        >
                          {{ m.expert_code }}.{{ m.variable }}
                        </Tag>
                      </Space>
                    </div>
                  </div>
                  <div v-else class="mapping-empty">
                    <span class="text-muted-foreground">
                      ⚠️ 未配置变量映射，策略变量将无法生效。
                      <a href="javascript:;" @click="openStrategyMappingDrawer"
                        >点击配置</a
                      >
                    </span>
                  </div>
                </Card>

                <div class="plan-toolbar">
                  <Space>
                    <Select
                      v-model:value="strategyConfigV3.selected_strategy_ids"
                      mode="multiple"
                      :loading="strategyLoading"
                      placeholder="选择关键词策略（可多选）"
                      style="width: 400px"
                      :options="strategySelectOptions"
                      :field-names="{ label: 'label', value: 'value' }"
                      :filter-option="filterStrategyOption"
                      show-search
                      @change="onStrategySelectionChange"
                      @focus="loadStrategyList"
                    />
                  </Space>
                  <Space>
                    <Tag color="green">
                      已分配：{{ strategyConfigV3.total_count }} 篇
                    </Tag>
                  </Space>
                </div>

                <!-- 合并组合分配 -->
                <Spin :spinning="mergedCombinationsLoading">
                  <div
                    v-if="strategyConfigV3.merged_combinations.length === 0"
                    class="empty-flow"
                  >
                    <span
                      >请先选择关键词策略，系统将自动合并各策略的维度。</span
                    >
                  </div>

                  <div v-else class="combo-list-container">
                    <!-- 统计卡片 -->
                    <div class="combo-stats">
                      <Row :gutter="16">
                        <Col :span="6">
                          <Statistic
                            title="总组合数"
                            :value="strategyConfigV3.merged_combinations.length"
                          />
                        </Col>
                        <Col :span="6">
                          <Statistic
                            title="已分配"
                            :value="strategyConfigV3.total_count"
                            suffix="篇"
                          />
                        </Col>
                        <Col :span="6">
                          <Statistic
                            title="平均每组合"
                            :value="
                              (
                                strategyConfigV3.total_count /
                                  strategyConfigV3.merged_combinations.length ||
                                0
                              ).toFixed(1)
                            "
                            suffix="篇"
                          />
                        </Col>
                        <Col :span="6">
                          <InputSearch
                            v-model:value="comboSearchKeyword"
                            placeholder="搜索组合关键词..."
                            allow-clear
                            size="small"
                          />
                        </Col>
                      </Row>
                    </div>

                    <!-- 虚拟滚动 Table -->
                    <Table
                      :data-source="filteredCombinations"
                      :pagination="false"
                      :scroll="{ y: 400 }"
                      size="small"
                      row-key="id"
                    >
                      <Table.Column
                        title="合并组合"
                        data-index="name"
                        key="name"
                      >
                        <template #default="{ record }">
                          <Space wrap size="small">
                            <template
                              v-for="([dimType, node], idx) in Object.entries(
                                record.merged_nodes || {},
                              )"
                              :key="dimType"
                            >
                              <span v-if="idx > 0" class="combo-plus">+</span>
                              <Tag color="purple" size="small">
                                {{ (node as any)?.name || dimType }}
                              </Tag>
                            </template>
                          </Space>
                        </template>
                      </Table.Column>
                      <Table.Column
                        title="生成数量"
                        data-index="count"
                        key="count"
                        width="160"
                      >
                        <template #default="{ record }">
                          <InputNumber
                            v-model:value="record.count"
                            :min="0"
                            size="small"
                            style="width: 100px"
                            @change="updateV3TotalCount"
                          />
                        </template>
                      </Table.Column>
                    </Table>
                  </div>
                </Spin>
              </div>

              <!-- v1 原有模式（保留） - 仅在非智能推荐、非 v3 模式下显示 -->
              <div
                v-else-if="
                  !useSmartSelector && !useStrategyV2 && !useStrategyV3
                "
                class="plan-toolbar"
              >
                <Space>
                  <Select
                    :value="strategyConfig.strategy_id || undefined"
                    :loading="strategyLoading"
                    placeholder="选择关键词策略"
                    style="width: 280px"
                    show-search
                    @change="onStrategyChange"
                    @focus="loadStrategyList"
                  >
                    <SelectOption
                      v-for="s in strategyList"
                      :key="s.id"
                      :value="s.id"
                    >
                      {{ s.name }}
                    </SelectOption>
                  </Select>
                  <Button
                    :disabled="!strategyConfig.strategy_id"
                    @click="openStrategyMappingDrawer"
                  >
                    配置变量映射
                  </Button>
                  <Button
                    :disabled="!strategyConfig.strategy_id"
                    :loading="strategyPreviewLoading"
                    @click="previewStrategyCombinations"
                  >
                    预览组合
                  </Button>
                </Space>
                <Space>
                  <Tag color="blue">
                    预览总篇数：{{ formState.article_count || 10 }}
                  </Tag>
                </Space>
              </div>

              <!-- v1 模式下的策略预览 - 仅在非智能推荐、非 v2 模式下显示 -->
              <template v-if="!useSmartSelector && !useStrategyV2">
                <div v-if="!strategyConfig.strategy_id" class="empty-flow">
                  <span>请先选择关键词策略，然后配置变量映射。</span>
                </div>

                <div v-else>
                  <!-- 已配置的变量映射摘要 -->
                  <div class="strategy-mapping-summary">
                    <h4>变量共享映射</h4>
                    <div
                      v-for="dim in selectedStrategyDimensions"
                      :key="dim.dimension_type"
                      class="mapping-dimension"
                    >
                      <Tag color="purple">{{ dim.dimension_name }}</Tag>
                      <span class="mapping-arrow">→</span>
                      <Space wrap>
                        <Tag
                          v-for="m in strategyConfig.variable_share_mapping[
                            dim.dimension_type
                          ] || []"
                          :key="`${m.expert_code}-${m.variable}`"
                          color="blue"
                        >
                          {{ m.expert_code }}.{{ m.variable }}
                        </Tag>
                        <span
                          v-if="
                            !strategyConfig.variable_share_mapping[
                              dim.dimension_type
                            ]?.length
                          "
                          class="text-muted-foreground"
                        >
                          未配置
                        </span>
                      </Space>
                    </div>
                  </div>

                  <!-- 预览组合 -->
                  <div
                    v-if="strategyConfig.preview_combinations.length > 0"
                    class="strategy-preview"
                  >
                    <h4>
                      预览组合（{{ strategyConfig.preview_combinations.length }}
                      个）
                    </h4>
                    <div class="preview-list">
                      <div
                        v-for="(
                          combo, idx
                        ) in strategyConfig.preview_combinations.slice(0, 5)"
                        :key="idx"
                        class="preview-item"
                      >
                        <Tag color="default">{{ idx + 1 }}</Tag>
                        <Space wrap>
                          <Tag
                            v-for="(node, dimType) in combo.nodes"
                            :key="dimType"
                            color="green"
                          >
                            {{ dimType }}: {{ node.name }}
                          </Tag>
                        </Space>
                      </div>
                      <div
                        v-if="strategyConfig.preview_combinations.length > 5"
                        class="text-muted-foreground"
                      >
                        ... 还有
                        {{ strategyConfig.preview_combinations.length - 5 }}
                        个组合
                      </div>
                    </div>
                  </div>
                </div>
              </template>

              <!-- 变量映射配置抽屉（v1 和 v2 共用）-->
              <Drawer
                :open="strategyMappingDrawerOpen"
                title="配置变量共享映射"
                width="780"
                @close="closeStrategyMappingDrawer"
              >
                <!-- 概念说明 -->
                <div class="mapping-concepts">
                  <div class="concept-item">
                    <div class="concept-label">
                      <Tag color="purple">策略维度</Tag>
                    </div>
                    <div class="concept-desc">
                      关键词策略中定义的关键词分类（如"场景"、"人设"），执行时会从该维度抽取关键词
                    </div>
                  </div>
                  <div class="concept-item">
                    <div class="concept-label">
                      <Tag color="default">变量</Tag>
                    </div>
                    <div class="concept-desc">
                      Expert
                      插件中的参数占位符（如"人设"、"场景"），执行时会被替换为实际的关键词值
                    </div>
                  </div>
                </div>

                <!-- 操作引导卡片 -->
                <div class="mapping-guide">
                  <div class="guide-header">
                    <span class="guide-icon">🎯</span>
                    <span class="guide-title">如何配置</span>
                  </div>
                  <div class="guide-steps">
                    <div class="guide-step">
                      <span class="step-num">1</span>
                      <span class="step-text">
                        每个
                        <Tag color="purple" size="small">紫色标签</Tag>
                        是一个策略维度
                      </span>
                    </div>
                    <div class="guide-step">
                      <span class="step-num">2</span>
                      <span class="step-text">
                        <strong>点击变量标签</strong>
                        将其映射到该维度 →
                        <Tag color="green" size="small">变绿 ✓</Tag>
                        表示已映射
                      </span>
                    </div>
                    <div class="guide-step">
                      <span class="step-num">3</span>
                      <span class="step-text">
                        执行时：维度关键词 → 替换到映射的变量 → Expert
                        使用该值生成内容
                      </span>
                    </div>
                  </div>
                </div>

                <div class="mapping-editor">
                  <div
                    v-for="dim in currentMappingDimensions"
                    :key="dim.dimension_type"
                    class="mapping-section"
                  >
                    <div class="mapping-section-header">
                      <div class="dimension-info">
                        <Tag color="purple" size="large">
                          {{ dim.dimension_name }}
                        </Tag>
                        <span class="text-muted-foreground">
                          ({{ dim.dimension_type }})
                        </span>
                      </div>
                      <span class="mapping-hint">
                        ✨ 已自动映射匹配的变量，可手动调整
                      </span>
                    </div>

                    <div class="mapping-targets">
                      <div
                        v-for="expert in allExpertVariables"
                        :key="expert.expert_code"
                        class="expert-variables"
                      >
                        <div class="expert-label">
                          <span class="expert-icon">
                            <RobotOutlined />
                          </span>
                          {{ expert.expert_name }}
                        </div>
                        <div class="variables-list">
                          <Tag
                            v-for="variable in expert.variables"
                            :key="variable"
                            class="variable-tag"
                            :class="{
                              'variable-tag-mapped': isVariableMapped(
                                dim.dimension_type,
                                expert.expert_code,
                                variable,
                              ),
                            }"
                            :color="
                              isVariableMapped(
                                dim.dimension_type,
                                expert.expert_code,
                                variable,
                              )
                                ? 'green'
                                : 'default'
                            "
                            @click="
                              toggleVariableMapping(
                                dim.dimension_type,
                                expert.expert_code,
                                variable,
                              )
                            "
                          >
                            {{ variable }}
                            <span
                              v-if="
                                isVariableMapped(
                                  dim.dimension_type,
                                  expert.expert_code,
                                  variable,
                                )
                              "
                              class="mapped-check"
                              >✓</span
                            >
                          </Tag>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div class="drawer-footer">
                  <Button type="primary" @click="closeStrategyMappingDrawer">
                    完成配置
                  </Button>
                </div>
              </Drawer>
            </div>

            <!-- 方案3：方案包 -->
            <div v-else>
              <div class="plan-toolbar">
                <Space>
                  <Button type="primary" @click="openVariantPicker">
                    从方案库选择
                  </Button>
                  <Button
                    @click="evenSplitVariants"
                    :disabled="selectedVariants.length === 0"
                  >
                    占比均分
                  </Button>
                </Space>
                <Space>
                  <Tag :color="plan3RatioSum === 100 ? 'green' : 'orange'">
                    占比合计：{{ plan3RatioSum }}%
                  </Tag>
                  <Tag color="blue">预览总篇数：{{ previewTotalCount }}</Tag>
                </Space>
              </div>

              <div v-if="selectedVariants.length === 0" class="empty-flow">
                <span>尚未选择方案包，点击“从方案库选择”开始。</span>
              </div>

              <div v-else>
                <Table
                  :data-source="selectedVariants"
                  :columns="plan3VariantColumns"
                  :pagination="false"
                  row-key="id"
                  size="middle"
                >
                  <template #bodyCell="{ column, record }">
                    <template v-if="column.key === 'tags'">
                      <Space wrap>
                        <Tag v-for="t in record.tags" :key="t" color="blue">
                          {{ t }}
                        </Tag>
                      </Space>
                    </template>
                    <template v-else-if="column.key === 'ratio'">
                      <InputNumber
                        v-model:value="record.ratio"
                        :max="100"
                        :min="0"
                        :precision="0"
                        style="width: 120px"
                      />
                    </template>
                    <template v-else-if="column.key === 'action'">
                      <Button
                        type="link"
                        danger
                        @click="
                          selectedVariants = selectedVariants.filter(
                            (x) => x.id !== record.id,
                          )
                        "
                      >
                        移除
                      </Button>
                    </template>
                  </template>
                </Table>

                <div class="variant-preview-tip text-muted-foreground">
                  覆盖编辑（功能预留）：后续支持对方案包的少量字段在本任务内进行覆盖。
                </div>
              </div>

              <Drawer
                :open="variantPickerOpen"
                title="选择方案包（方案库）"
                width="720"
                @close="closeVariantPicker"
              >
                <Alert
                  class="alert-info"
                  message="说明"
                  description="当前已对接后端方案库（仅展示启用项）；支持按关键字筛选并选择复用到任务。"
                  show-icon
                  type="info"
                />
                <div class="plan-toolbar" style="margin-bottom: 12px">
                  <Space>
                    <Input
                      v-model:value="variantKeyword"
                      placeholder="关键字（名称/备注）"
                      style="width: 280px"
                      allow-clear
                    />
                    <Button
                      :loading="variantLibraryLoading"
                      @click="loadVariantLibrary"
                    >
                      查询
                    </Button>
                  </Space>
                </div>
                <div class="variant-lib">
                  <div
                    v-for="v in variantLibrary"
                    :key="v.variant_id"
                    class="variant-card"
                    :class="{
                      selected: selectedVariants.some(
                        (x) => x.id === v.variant_id,
                      ),
                    }"
                    @click="toggleVariantPick(v)"
                  >
                    <div class="variant-card-title">
                      <span class="variant-name">{{ v.variant_name }}</span>
                      <Tag
                        :color="
                          selectedVariants.some((x) => x.id === v.variant_id)
                            ? 'green'
                            : 'default'
                        "
                      >
                        {{
                          selectedVariants.some((x) => x.id === v.variant_id)
                            ? '已选择'
                            : '未选择'
                        }}
                      </Tag>
                    </div>
                    <div class="variant-tags">
                      <Tag v-for="t in v.tags" :key="t" color="blue">
                        {{ t }}
                      </Tag>
                    </div>
                    <div class="variant-desc text-muted-foreground">
                      点击卡片切换选择状态。
                    </div>
                  </div>
                </div>
                <Divider />
                <Space>
                  <Button @click="closeVariantPicker">完成</Button>
                </Space>
              </Drawer>
            </div>
          </div>

          <!-- Step 2: 确认配置 -->
          <div v-show="currentStep === 2" class="step-content">
            <Alert
              class="alert-info"
              message="请确认以下配置信息"
              show-icon
              type="success"
            />

            <div class="confirm-section">
              <h4 class="section-title">业务归属</h4>
              <div class="confirm-grid">
                <div class="confirm-item full">
                  <span class="confirm-label">智能体：</span>
                  <span class="confirm-value">
                    {{
                      agentOptions.find((a) => a.value === formState.agent_code)
                        ?.label || formState.agent_code
                    }}
                  </span>
                </div>
              </div>
            </div>

            <div class="confirm-section">
              <h4 class="section-title">基本信息</h4>
              <div class="confirm-grid">
                <div class="confirm-item">
                  <span class="confirm-label">任务名称：</span>
                  <span class="confirm-value">{{ formState.job_name }}</span>
                </div>
                <div class="confirm-item">
                  <span class="confirm-label">启用状态：</span>
                  <span class="confirm-value">
                    {{ formState.enabled ? '✅ 启用' : '❌ 禁用' }}
                  </span>
                </div>
                <div class="confirm-item">
                  <span class="confirm-label">目标篇数：</span>
                  <span class="confirm-value">
                    {{ formState.article_count ?? '-' }}
                  </span>
                </div>
                <div v-if="formState.description" class="confirm-item full">
                  <span class="confirm-label">描述：</span>
                  <span class="confirm-value">{{ formState.description }}</span>
                </div>
              </div>
            </div>

            <div class="confirm-section">
              <h4 class="section-title">
                专家模块执行顺序 ({{ selectedExperts.length }} 个)
              </h4>
              <div class="confirm-flow">
                <div
                  v-for="(expert, index) in selectedExperts"
                  :key="expert.code"
                  class="confirm-flow-item"
                >
                  <span class="confirm-flow-step">{{ expert.order }}</span>
                  <span class="confirm-flow-name">{{ expert.name }}</span>
                  <span
                    v-if="index < selectedExperts.length - 1"
                    class="confirm-flow-arrow"
                  >
                    →
                  </span>
                </div>
              </div>
            </div>

            <div class="confirm-section">
              <h4 class="section-title">创建方式</h4>
              <div class="confirm-grid">
                <div class="confirm-item full">
                  <span class="confirm-label">方式：</span>
                  <span class="confirm-value">{{
                    modeTips[jobCreateMode].title
                  }}</span>
                </div>
                <div class="confirm-item">
                  <span class="confirm-label">预览总篇数：</span>
                  <span class="confirm-value">{{ previewTotalCount }}</span>
                </div>
                <template v-if="jobCreateMode === 'plan4_strategy'">
                  <div class="confirm-item">
                    <span class="confirm-label">策略数量：</span>
                    <span class="confirm-value"
                      >{{ plan4Stats.strategyCount }} 个</span
                    >
                  </div>
                  <div v-if="plan4Stats.mappingCount > 0" class="confirm-item">
                    <span class="confirm-label">变量映射：</span>
                    <span class="confirm-value"
                      >{{ plan4Stats.mappingCount }} 个变量</span
                    >
                  </div>
                </template>
                <div v-else class="confirm-item">
                  <span class="confirm-label">占比合计：</span>
                  <span class="confirm-value">
                    {{
                      jobCreateMode === 'system_random'
                        ? '-'
                        : jobCreateMode === 'plan1_combinations'
                          ? `${plan1RatioSum}%`
                          : jobCreateMode === 'plan2_rules'
                            ? `${plan2RatioSum}%`
                            : jobCreateMode === 'plan3_variants'
                              ? `${plan3RatioSum}%`
                              : '-'
                    }}
                  </span>
                </div>
              </div>
              <div class="form-tip" style="margin-top: 8px">
                💡 方案1/2/3
                会生成并保存到任务的生成方案配置；默认方案会清空配置并回退到随机参数。
              </div>
            </div>
          </div>

          <!-- 操作按钮 -->
          <Divider />
          <div class="form-actions">
            <Button @click="handleCancel">取消</Button>
            <Space>
              <Button v-if="currentStep > 0" @click="handlePrev">
                上一步
              </Button>
              <Button
                v-if="currentStep < steps.length - 1"
                type="primary"
                @click="handleNext"
              >
                下一步
              </Button>
              <Button
                v-if="currentStep === steps.length - 1"
                :loading="saving"
                type="primary"
                @click="handleSubmit"
              >
                {{ isEdit ? '保存修改' : '创建任务' }}
              </Button>
            </Space>
          </div>
        </Form>
      </div>
    </Card>

    <Modal
      v-model:open="saveVariantModalOpen"
      title="保存为方案包"
      ok-text="确定"
      cancel-text="取消"
      @ok="submitSaveVariant"
      @cancel="closeSaveVariantModal"
    >
      <Alert
        class="alert-info"
        type="info"
        show-icon
        message="说明"
        description="将当前组合的专家参数配置保存到方案库，后续可在创建任务（方案3）直接选择并分配占比。"
      />
      <Form layout="vertical">
        <FormItem label="方案包名称">
          <Input
            v-model:value="saveVariantForm.variant_name"
            placeholder="如：创业妈妈·体验型"
          />
        </FormItem>
        <FormItem label="标签">
          <Select
            v-model:value="saveVariantForm.tags"
            mode="tags"
            placeholder="输入后回车添加"
          />
        </FormItem>
      </Form>
    </Modal>
  </div>
</template>

<style scoped>
@keyframes pulse-hint {
  0%,
  100% {
    opacity: 0.6;
  }

  50% {
    opacity: 1;
  }
}

@keyframes mapped-glow {
  0% {
    transform: scale(1);
  }

  50% {
    transform: scale(1.05);
  }

  100% {
    transform: scale(1);
  }
}

.job-create-page {
  padding: 16px;
}

.steps-container {
  padding: 0 40px;
  margin-bottom: 32px;
}

.form-container {
  max-width: 1000px;
  margin: 0 auto;
}

.step-content {
  min-height: 300px;
}

.alert-info {
  margin-bottom: 24px;
}

/* 操作指南样式 */
.guide-alert {
  margin-bottom: 24px;
}

.guide-alert :deep(.ant-alert-message) {
  font-weight: 600;
}

.guide-content p {
  margin: 0 0 12px;
}

.guide-actions {
  padding-top: 12px;
  margin-top: 12px;
  border-top: 1px solid hsl(var(--border));
}

.alert-warning {
  margin-bottom: 16px;
}

.combination-editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 12px;
}

.combination-editor .expert-card {
  cursor: default;
  background: hsl(var(--card));
}

.combination-editor .expert-card:hover {
  background: hsl(var(--card));
  border-color: hsl(var(--border));
}

.combination-editor .vars {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.combination-editor .var-row {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.combination-editor .var-name {
  display: flex;
  gap: 8px;
  align-items: center;
  min-width: 200px;
}

.combination-editor .var-key {
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 13px;
  color: hsl(var(--foreground));
}

.drawer-footer {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding-top: 12px;
  margin-top: 16px;
  border-top: 1px solid hsl(var(--border));
}

.create-mode-header {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-items: start;
  margin-bottom: 8px;
}

.plan-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

/* 策略模式切换 */
.strategy-mode-switch {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 12px 16px;
  margin-bottom: 16px;
  background: hsl(var(--muted) / 30%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.strategy-mode-switch .mode-hint {
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

/* v3 策略合并样式 */
.strategy-v3-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 智能选择器样式 */
.smart-selector-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.smart-selector-section .allocation-card {
  margin-top: 8px;
}

.smart-selector-section .sampling-config-card {
  margin-top: 8px;
  background: hsl(var(--background) / 50%);
  border: 1px solid hsl(var(--primary) / 20%);
}

.smart-selector-section .config-label {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.smart-selector-section .hint-text {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: hsl(var(--muted-foreground));
}

.smart-selector-section .card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.merged-dimensions {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.merged-dimensions .label {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.merged-combinations {
  padding: 16px;
  background: hsl(var(--muted) / 30%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

/* v2 策略分配样式 */
.strategy-v2-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.strategy-allocations {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.allocation-group {
  padding: 16px;
  background: hsl(var(--muted) / 30%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.allocation-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}

.allocation-title {
  font-size: 15px;
  font-weight: 600;
}

.combo-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.combo-name {
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.combo-plus {
  font-weight: 500;
  color: hsl(var(--muted-foreground));
}

/* 策略模式提示样式 */
.strategy-mode-hint {
  margin-bottom: 16px;
}

.hint-title {
  font-weight: 600;
}

.hint-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 4px;
}

.hint-item {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 变量映射配置卡片 */
.mapping-config-card {
  margin-bottom: 16px;
}

.mapping-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.mapping-summary {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mapping-summary-item {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: flex-start;
}

.mapping-arrow {
  color: hsl(var(--muted-foreground));
}

.mapping-empty {
  padding: 12px;
  text-align: center;
  background: hsl(var(--muted) / 30%);
  border-radius: 4px;
}

.rules-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.rule-card {
  padding: 12px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
}

.rule-card-header {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.rule-card-title {
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 0;
}

.rule-card-name {
  font-weight: 600;
  color: hsl(var(--foreground));
}

.rule-conditions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.rule-preview {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.rule-editor .cond-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.rule-editor .cond-row {
  display: grid;
  grid-template-columns: 120px 80px 1fr 72px;
  gap: 10px;
  align-items: center;
}

.variant-lib {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.variant-card {
  padding: 12px;
  cursor: pointer;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
  transition: all 0.2s;
}

.variant-card:hover {
  background: hsl(var(--muted) / 20%);
  border-color: hsl(var(--primary) / 50%);
}

.variant-card.selected {
  background: hsl(var(--primary) / 8%);
  border-color: hsl(var(--primary));
}

.variant-card-title {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.variant-name {
  font-weight: 600;
  color: hsl(var(--foreground));
}

.variant-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 6px;
}

.variant-desc {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.variant-preview-tip {
  margin-top: 10px;
  font-size: 12px;
}

.form-tip {
  margin-top: 4px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.switch-label {
  margin-left: 8px;
  color: hsl(var(--muted-foreground));
}

.expert-option {
  padding: 4px 0;
}

.expert-option-label {
  font-weight: 500;
}

.expert-option-desc {
  margin-top: 2px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.flow-section {
  margin-top: 24px;
}

.flow-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.flow-item {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  background: hsl(var(--muted) / 30%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  transition: all 0.2s;
}

.flow-item:hover {
  background: hsl(var(--muted) / 50%);
  border-color: hsl(var(--primary) / 50%);
}

.flow-step {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  margin-right: 12px;
  font-size: 14px;
  font-weight: 600;
  color: hsl(var(--primary-foreground));
  background: hsl(var(--primary));
  border-radius: 50%;
}

.flow-content {
  flex: 1;
  min-width: 0;
}

.flow-name {
  font-weight: 500;
  color: hsl(var(--foreground));
}

.flow-code {
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.flow-actions {
  display: flex;
  gap: 4px;
}

.confirm-section {
  padding: 16px;
  margin-bottom: 24px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.section-title {
  padding-bottom: 8px;
  margin: 0 0 16px;
  font-size: 15px;
  color: hsl(var(--foreground));
  border-bottom: 1px solid hsl(var(--border));
}

.confirm-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.confirm-item {
  display: flex;
  align-items: flex-start;
}

.confirm-item.full {
  grid-column: span 2;
}

.confirm-label {
  flex-shrink: 0;
  min-width: 80px;
  color: hsl(var(--muted-foreground));
}

.confirm-value {
  font-weight: 500;
  color: hsl(var(--foreground));
}

.confirm-flow {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.confirm-flow-item {
  display: flex;
  gap: 8px;
  align-items: center;
}

.confirm-flow-step {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  font-size: 12px;
  font-weight: 600;
  color: hsl(var(--primary-foreground));
  background: hsl(var(--primary));
  border-radius: 50%;
}

.confirm-flow-name {
  padding: 4px 12px;
  font-size: 13px;
  background: hsl(var(--muted));
  border-radius: 4px;
}

.confirm-flow-arrow {
  font-size: 18px;
  color: hsl(var(--muted-foreground));
}

.form-actions {
  display: flex;
  justify-content: space-between;
}

:deep(.ant-card-head) {
  border-bottom: 1px solid hsl(var(--border));
}

:deep(.ant-steps-item-title) {
  font-weight: 500;
}

/* Expert 选择容器样式 */
.expert-selection-container {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  min-height: 400px;
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
  padding: 16px;
  background: hsl(var(--muted) / 30%);
  border-bottom: 1px solid hsl(var(--border));
}

.panel-title {
  font-size: 15px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.panel-search {
  padding: 12px 16px;
  border-bottom: 1px solid hsl(var(--border));
}

.expert-cards {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 8px;
  max-height: 350px;
  padding: 12px;
  overflow-y: auto;
}

.expert-card {
  padding: 12px 16px;
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
  font-size: 14px;
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
  margin-bottom: 6px;
}

.expert-card-desc {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  line-height: 1.4;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
}

.empty-experts {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100px;
  font-size: 14px;
  color: hsl(var(--muted-foreground));
}

.empty-flow {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100px;
  font-size: 14px;
  color: hsl(var(--muted-foreground));
}

.zero-score-rule {
  padding: 12px 16px 16px;
  background: hsl(var(--muted) / 10%);
  border-top: 1px solid hsl(var(--border));
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
  margin-top: 12px;
}

.zero-score-alert {
  margin-bottom: 12px;
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

.flow-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 4px;
}

.flow-meta code {
  padding: 2px 6px;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted));
  border-radius: 4px;
}

.flow-type {
  padding: 2px 6px;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted));
  border-radius: 4px;
}

/* Job 参数配置 */
.job-param-config-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 12px;
}

.job-param-expert {
  padding: 12px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
}

.job-param-expert-header {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 10px;
  margin-bottom: 10px;
  border-bottom: 1px solid hsl(var(--border));
}

.job-param-expert-title {
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 0;
}

.job-param-expert-order {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  font-size: 12px;
  font-weight: 600;
  color: hsl(var(--primary-foreground));
  background: hsl(var(--primary));
  border-radius: 50%;
}

.job-param-expert-name {
  font-weight: 600;
  color: hsl(var(--foreground));
}

.job-param-expert-code {
  padding: 2px 6px;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted));
  border-radius: 4px;
}

.job-param-expert-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.job-param-empty {
  padding: 8px 0;
}

.job-param-plugins {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.job-param-plugin {
  padding: 10px 12px;
  background: hsl(var(--muted) / 20%);
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
}

.job-param-plugin-title {
  margin-bottom: 10px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.job-param-plugin-title code {
  padding: 2px 6px;
  margin-left: 6px;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 12px;
  color: hsl(var(--primary));
  background: hsl(var(--muted));
  border-radius: 4px;
}

.job-param-row {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
}

.job-param-row:last-child {
  margin-bottom: 0;
}

/* 策略模式样式 */
.strategy-mapping-summary {
  padding: 16px;
  margin-bottom: 16px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
}

.strategy-mapping-summary h4 {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.mapping-dimension {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 8px;
}

.mapping-dimension:last-child {
  margin-bottom: 0;
}

.strategy-preview {
  padding: 16px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
}

.strategy-preview h4 {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.preview-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.preview-item {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 8px 12px;
  background: hsl(var(--muted) / 20%);
  border-radius: 6px;
}

.mapping-editor {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-top: 16px;
}

.mapping-section {
  padding: 16px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
}

.mapping-section-header {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  margin-bottom: 16px;
  border-bottom: 1px dashed hsl(var(--border));
}

.mapping-section-header .dimension-info {
  display: flex;
  gap: 8px;
  align-items: center;
}

.mapping-hint {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
  animation: pulse-hint 2s ease-in-out infinite;
}

/* 概念说明区域 */
.mapping-concepts {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}

.concept-item {
  display: flex;
  flex: 1;
  gap: 10px;
  align-items: flex-start;
  padding: 12px 16px;
  background: hsl(var(--muted) / 30%);
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
}

.concept-label {
  flex-shrink: 0;
}

.concept-desc {
  font-size: 13px;
  line-height: 1.5;
  color: hsl(var(--muted-foreground));
}

/* 操作引导卡片 */
.mapping-guide {
  padding: 16px 20px;
  margin-bottom: 20px;
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 8%) 0%,
    hsl(var(--accent) / 12%) 100%
  );
  border: 1px solid hsl(var(--primary) / 20%);
  border-radius: 12px;
}

.guide-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}

.guide-icon {
  font-size: 20px;
}

.guide-title {
  font-size: 15px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.guide-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.guide-step {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.step-num {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  font-size: 12px;
  font-weight: 600;
  color: white;
  background: linear-gradient(135deg, hsl(var(--primary)) 0%, #6366f1 100%);
  border-radius: 50%;
}

.step-text {
  font-size: 13px;
  line-height: 22px;
  color: hsl(var(--muted-foreground));
}

.step-text strong {
  color: hsl(var(--primary));
}

/* 变量标签交互样式 */
.variable-tag {
  cursor: pointer;
  transition: all 0.2s ease;
}

.variable-tag:hover {
  box-shadow: 0 4px 12px hsl(var(--primary) / 20%);
  transform: translateY(-2px);
}

.variable-tag-mapped {
  animation: mapped-glow 0.3s ease;
}

.mapped-check {
  margin-left: 4px;
  font-weight: bold;
}

.mapping-targets {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.expert-variables {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.expert-label {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
  min-width: 140px;
  padding: 6px 12px;
  font-weight: 500;
  color: hsl(var(--foreground));
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 8%) 0%,
    hsl(var(--accent) / 5%) 100%
  );
  border: 1px solid hsl(var(--primary) / 15%);
  border-radius: 8px;
}

.expert-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  font-size: 14px;
  color: hsl(var(--primary));
  background: linear-gradient(
    135deg,
    hsl(var(--primary) / 20%) 0%,
    hsl(var(--primary) / 35%) 100%
  );
  border-radius: 6px;
  box-shadow: 0 2px 4px hsl(var(--primary) / 15%);
}

.variables-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.job-param-var {
  min-width: 120px;
  padding: 2px 8px;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 12px;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 10%);
  border-radius: 4px;
}

.job-param-arrow {
  color: hsl(var(--muted-foreground));
}

/* 组合列表容器 */
.combo-list-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 统计卡片 */
.combo-stats {
  padding: 16px;
  margin-bottom: 8px;
  background: hsl(var(--b2));
  border-radius: 8px;
}
</style>
