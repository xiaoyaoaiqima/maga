<script setup lang="ts">
import type { SelectValue } from 'ant-design-vue/es/select';

import type { TenantApi } from '#/api/core/business';
import type { LLMApi } from '#/api/core/llm';

import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useDebounceFn } from '@vueuse/core';
import {
  Badge,
  Button,
  Card,
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
  message,
  Modal,
  Select,
  SelectOption,
  Space,
  Table,
  Tag,
  Textarea,
  Timeline,
  TimelineItem,
} from 'ant-design-vue';

import { getTenantSimpleListApi } from '#/api/core/business';
import { getProviderListApi } from '#/api/core/llm';
import { checkCanModifyApi } from '#/api/core/publish';
import { requestClient } from '#/api/request';
import ModelSelect from '#/components/ModelSelect.vue';
import MonacoEditor from '#/components/MonacoEditor.vue';
import {
  checkCodeExists,
  checkNameExists,
  generateUniqueCode,
} from '#/utils/code_uniqueness';
import { use_page_persistence } from '#/utils/page_persistence';

// 快照相关接口
interface Snapshot {
  id: number;
  entity_type: string;
  entity_id: null | number;
  entity_code: string;
  snapshot_type: string;
  content: Record<string, any>;
  version: number;
  description: null | string;
  create_time: string;
  created_by: null | string;
}

interface ExpertConfig {
  id: number;
  expert_config_code: string;
  expert_config_name: string;
  description: null | string;
  tenant_code: null | string;
  expert_type: null | string;
  expert_app: null | string;
  expert_service: null | string;
  expert_func: null | string;
  model_code: null | string;
  model_config: null | Record<string, any>;
  plugin_config: null | Record<string, any>;
  prompt_template: null | string;
  enabled: boolean;
  is_deleted: boolean;
  remark: null | string;
  publish_status: 'DRAFT' | 'PUBLISHED';
  publish_time: null | string;
  publish_by: null | string;
  create_time: string;
  update_time: string;
}

// Plugin 和 PluginContext 相关接口
interface Plugin {
  id: number;
  plugin_code: string;
  plugin_name: string;
  plugin_type: null | string;
  variable_list: null | string[];
  context_template: null | string;
  enabled: boolean;
  publish_status: 'DRAFT' | 'PUBLISHED';
  publish_time: null | string;
  publish_by: null | string;
}

interface PluginContext {
  id: number;
  variable_name: null | string;
  context_name: null | string;
  context: null | string;
  publish_status: 'DRAFT' | 'PUBLISHED';
  publish_time: null | string;
  publish_by: null | string;
}

// 已选择的插件配置项
interface SelectedPlugin {
  plugin_code: string;
  plugin_name: string;
  context_template: null | string;
  variable_mapping: Record<string, string[]>; // variable_name -> context_name[] (多选)
}

const props = withDefaults(
  defineProps<{ initialCode?: string; pageMode?: boolean }>(),
  {
    initialCode: '',
    pageMode: false,
  },
);
const route = useRoute();
const router = useRouter();
const expertManagementPath = '/expert/calibration';
const isPageMode = computed(() => props.pageMode === true);
const initialExpertCode = computed(() => {
  if (props.initialCode) return props.initialCode;
  return typeof route.query.code === 'string' ? route.query.code : '';
});

const loading = ref(false);
const dataSource = ref<ExpertConfig[]>([]);
const searchText = ref('');
const modalVisible = ref(false);
const detailVisible = ref(false);
const editingConfig = ref<ExpertConfig | null>(null);
const viewingConfig = ref<ExpertConfig | null>(null);
const hasAutoOpened = ref(false);

// 筛选条件
const filterTenantCode = ref<string | undefined>(undefined);
const filterIsDeleted = ref<string | undefined>(undefined); // 是否删除筛选
const filterContextName = ref('');
const filterContextContent = ref('');
const sortOrder = ref<'asc' | 'desc'>('desc'); // 默认按更新时间降序

type PersistedExpertConfigPageStateV1 = {
  copy_form_state: { expert_config_code: string; expert_config_name: string };
  copy_modal_visible: boolean;
  copy_source_config_id: null | number;
  current_entity_code: string;
  detail_visible: boolean;
  editing_config_id: null | number;
  editing_plugin_index: null | number;
  form_state: {
    description: string;
    enabled: string;
    expert_app: string;
    expert_config_code: string;
    expert_config_name: string;
    expert_func: string;
    expert_service: string;
    expert_type: string;
    model_code: string;
    model_config: string;
    plugin_config: string;
    prompt_template: string;
  };
  modal_visible: boolean;
  plugin_config_step: 'mapping' | 'select';
  plugin_select_modal_visible: boolean;
  search_text: string;
  selected_plugin_code: null | string;
  selected_plugins: SelectedPlugin[];
  temp_variable_mapping: Record<string, string[]>;
  version_drawer_visible: boolean;
  viewing_config_id: null | number;
};

// 复制 ExpertConfig
const copyModalVisible = ref(false);
const copySourceConfig = ref<ExpertConfig | null>(null);
const copyFormRef = ref();
const copyFormState = ref({
  expert_config_code: '',
  expert_config_name: '',
});

const formRef = ref();
const formState = ref({
  expert_config_code: '',
  expert_config_name: '',
  description: '',
  tenant_code: undefined as string | undefined, // 租户编码（可选，NULL 表示全局共享）
  expert_type: 'GENERATION',
  expert_app: '',
  expert_service: '',
  expert_func: '',
  expert_func_name: '', // 显示名称（用于图表展示）
  model_code: '',
  model_config: '{\n  "temperature": 0,\n  "max_tokens": 2000\n}',
  plugin_config: '[]',
  prompt_template: '',
  enabled: 'true', // 字符串类型，提交时转换为 boolean
});

const selectedExpertCode = ref<string | undefined>(undefined);

const expertSelectOptions = computed(() =>
  dataSource.value.map((item) => ({
    label: `${item.expert_config_name} (${item.expert_config_code})`,
    value: item.expert_config_code,
  })),
);

// 租户列表
const tenantOptions = ref<TenantApi.SimpleItem[]>([]);

// 快照相关状态
const versionDrawerVisible = ref(false);
const versionHistory = ref<Snapshot[]>([]);
const versionLoading = ref(false);
const autoSaveStatus = ref<'error' | 'idle' | 'saved' | 'saving'>('idle');
const hasDraft = ref(false);
const isLoadingForm = ref(false); // 标记正在加载表单数据，防止触发自动保存
const initialFormState = ref<string>(''); // 存储表单初始状态的 JSON 字符串，用于对比是否有修改
const currentEntityCode = ref('');
const versionDetailVisible = ref(false);
const viewingVersion = ref<null | Snapshot>(null);

// 编码校验状态（V5+ 零报错体验）
const allowManualCodeEdit = ref(false);
const codeValidationStatus = ref<
  'checking' | 'error' | 'idle' | 'invalid' | 'valid'
>('idle');
const codeValidationMessage = ref('');
const collapseActiveKey = ref<string[]>([]); // 控制高级选项折叠面板状态
const pagination = ref({
  current: 1,
  pageSize: 10,
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条`,
});

// 操作列固定区域会裁剪下拉框，单独挂载到 body
const getActionDropdownContainer = () => document.body;

// Expert 类型选项（含编码元数据）
const expertTypeOptions = [
  {
    value: 'GENERATION',
    label: '生成类型',
    codePrefix: 'ge',
    namePrefix: '生文',
  },
  {
    value: 'ANALYSIS',
    label: '分析类型',
    codePrefix: 'ana',
    namePrefix: '分析',
  },
  {
    value: 'CRITIC',
    label: '打分类型',
    codePrefix: 'critic',
    namePrefix: '评分',
  },
  {
    value: 'TRANSFORM',
    label: '转换类型',
    codePrefix: 'trans',
    namePrefix: '转换',
  },
  { value: 'BAN', label: '01型打分', codePrefix: 'ban', namePrefix: '01打分' },
];

// Plugin 配置相关状态
const selectedPlugins = ref<SelectedPlugin[]>([]);
const pluginSelectModalVisible = ref(false);
const allPlugins = ref<Plugin[]>([]);
const allPluginContexts = ref<PluginContext[]>([]);
const selectedPluginCode = ref<null | string>(null);
const tempVariableMapping = ref<Record<string, string[]>>({});
const pluginConfigStep = ref<'mapping' | 'select'>('select');
const editingPluginIndex = ref<null | number>(null); // 编辑插件的索引
const dragIndex = ref<null | number>(null);
const pluginSearchText = ref('');

// 快速创建插件相关状态
const quickCreatePluginVisible = ref(false);
const quickCreatePluginLoading = ref(false);
const quickCreatePluginForm = ref({
  plugin_code: '',
  plugin_name: '',
  context_template: '',
  variable_list: [] as string[],
});

// 根据搜索词过滤的插件列表
const filteredPlugins = computed(() => {
  if (!pluginSearchText.value) return allPlugins.value;
  const keyword = pluginSearchText.value.toLowerCase();
  return allPlugins.value.filter(
    (plugin) =>
      plugin.plugin_name.toLowerCase().includes(keyword) ||
      plugin.plugin_code.toLowerCase().includes(keyword),
  );
});

const page_persistence = use_page_persistence<PersistedExpertConfigPageStateV1>(
  {
    storage_key: 'raap_admin.config.expert_config.persist.v1',
    version: 1,
    get_state: () => ({
      search_text: searchText.value || '',
      modal_visible: !!modalVisible.value,
      detail_visible: !!detailVisible.value,
      editing_config_id: editingConfig.value?.id ?? null,
      viewing_config_id: viewingConfig.value?.id ?? null,
      form_state: { ...formState.value },
      copy_modal_visible: !!copyModalVisible.value,
      copy_source_config_id: copySourceConfig.value?.id ?? null,
      copy_form_state: { ...copyFormState.value },
      plugin_select_modal_visible: !!pluginSelectModalVisible.value,
      selected_plugins: selectedPlugins.value || [],
      selected_plugin_code: selectedPluginCode.value,
      temp_variable_mapping: tempVariableMapping.value || {},
      plugin_config_step: pluginConfigStep.value,
      editing_plugin_index: editingPluginIndex.value,
      version_drawer_visible: !!versionDrawerVisible.value,
      current_entity_code: currentEntityCode.value || '',
    }),
    apply_state: async (persisted) => {
      searchText.value = persisted.search_text || '';

      // 还原编辑/详情（依赖列表数据）
      editingConfig.value =
        persisted.editing_config_id === null ||
        persisted.editing_config_id === undefined
          ? null
          : dataSource.value.find(
              (x) => x.id === persisted.editing_config_id,
            ) || null;
      viewingConfig.value =
        persisted.viewing_config_id === null ||
        persisted.viewing_config_id === undefined
          ? null
          : dataSource.value.find(
              (x) => x.id === persisted.viewing_config_id,
            ) || null;
      modalVisible.value = !!persisted.modal_visible;
      detailVisible.value = !!persisted.detail_visible;

      // 还原主表单
      if (persisted.form_state) {
        formState.value = { ...formState.value, ...persisted.form_state };
      }

      // 还原复制弹窗
      copyModalVisible.value = !!persisted.copy_modal_visible;
      copySourceConfig.value =
        persisted.copy_source_config_id === null ||
        persisted.copy_source_config_id === undefined
          ? null
          : dataSource.value.find(
              (x) => x.id === persisted.copy_source_config_id,
            ) || null;
      if (persisted.copy_form_state) {
        copyFormState.value = {
          ...copyFormState.value,
          ...persisted.copy_form_state,
        };
      }

      // 还原插件配置 UI
      pluginSelectModalVisible.value = !!persisted.plugin_select_modal_visible;
      selectedPlugins.value = persisted.selected_plugins || [];
      selectedPluginCode.value = persisted.selected_plugin_code ?? null;
      tempVariableMapping.value = persisted.temp_variable_mapping || {};
      pluginConfigStep.value = persisted.plugin_config_step || 'select';
      editingPluginIndex.value = persisted.editing_plugin_index ?? null;

      // 还原版本抽屉
      currentEntityCode.value = persisted.current_entity_code || '';
      versionDrawerVisible.value = !!persisted.version_drawer_visible;
      if (versionDrawerVisible.value && currentEntityCode.value) {
        await fetchVersionHistory(currentEntityCode.value);
      }
    },
  },
);

// 根据 variable_name 分组的 context 列表
const contextsByVariable = computed(() => {
  const map: Record<string, PluginContext[]> = {};
  for (const ctx of allPluginContexts.value) {
    const varName = ctx.variable_name || '_default';
    if (!map[varName]) {
      map[varName] = [];
    }
    map[varName]?.push(ctx);
  }
  return map;
});

// 当前选择的插件信息
const currentPlugin = computed(() => {
  if (!selectedPluginCode.value) return null;
  return allPlugins.value.find(
    (p) => p.plugin_code === selectedPluginCode.value,
  );
});

// 插件弹窗标题
const pluginModalTitle = computed(() => {
  if (pluginConfigStep.value === 'select') {
    return '选择插件';
  }
  // mapping 步骤
  if (editingPluginIndex.value !== null) {
    return `编辑插件上下文 - ${currentPlugin.value?.plugin_name || ''}`;
  }
  return `配置变量映射 - ${currentPlugin.value?.plugin_name || ''}`;
});

// 根据插件配置生成 Prompt 模板（直接拼接 context_template）
function generatePromptTemplate() {
  if (selectedPlugins.value.length === 0) {
    return '';
  }
  const parts: string[] = [];
  for (const sp of selectedPlugins.value) {
    if (sp.context_template) {
      parts.push(sp.context_template);
    }
  }
  return parts.join('\n\n');
}

// 更新 Prompt 模板
function updatePromptTemplate() {
  const template = generatePromptTemplate();
  if (template) {
    formState.value.prompt_template = template;
  }
}

const columns = [
  {
    title: 'Config 编码',
    dataIndex: 'expert_config_code',
    key: 'expert_config_code',
    width: 180,
  },
  {
    title: '名称',
    dataIndex: 'expert_config_name',
    key: 'expert_config_name',
    width: 150,
  },
  {
    title: '租户',
    dataIndex: 'tenant_code',
    key: 'tenant_code',
    width: 100,
  },
  // { title: '类型', dataIndex: 'expert_type', key: 'expert_type', width: 100 }, // 隐藏类型列
  { title: '模型', dataIndex: 'model_code', key: 'model_code', width: 130 },
  {
    title: '描述',
    dataIndex: 'description',
    key: 'description',
    width: 180,
    ellipsis: true,
  },
  {
    title: '启用状态',
    dataIndex: 'enabled',
    key: 'enabled',
    width: 100,
  },
  {
    title: '上线状态',
    dataIndex: 'publish_status',
    key: 'publish_status',
    width: 100,
  },
  {
    title: '更新时间',
    dataIndex: 'update_time',
    key: 'update_time',
    width: 160,
  },
  { title: '操作', key: 'action', width: 200, fixed: 'right' as const },
];

// Provider 选项（用于 model_config 中的 provider_code）
const providerOptions = ref<{ label: string; value: string }[]>([]);

// 获取 Provider 列表
async function fetchProviderOptions() {
  try {
    const response = await getProviderListApi({ enabled: true });
    if (response?.items) {
      providerOptions.value = response.items.map(
        (provider: LLMApi.ProviderConfig) => ({
          value: provider.provider_code,
          label: `${provider.provider_name} (${provider.provider_code})`,
        }),
      );
    }
  } catch (error) {
    console.error('获取 Provider 列表失败:', error);
  }
}

// 获取租户列表（用于选择器）
async function fetchTenants() {
  try {
    const response = await getTenantSimpleListApi();
    tenantOptions.value = response || [];
  } catch (error) {
    console.error('获取租户列表失败:', error);
  }
}

async function fetchConfigs() {
  loading.value = true;
  try {
    const params: Record<string, boolean | number> = {};

    // 如果筛选条件中选择了"已删除",则传递 is_deleted=true
    if (filterIsDeleted.value !== undefined && filterIsDeleted.value !== '') {
      params.is_deleted = filterIsDeleted.value === 'true';
    }

    // requestClient 已经自动提取了 data 字段，response 直接就是数组
    const response = await requestClient.get<ExpertConfig[]>(
      '/v1/expert-configs',
      {
        params: Object.keys(params).length > 0 ? params : undefined,
      },
    );
    dataSource.value = response || [];
  } catch (error) {
    console.error('获取 ExpertConfig 列表失败:', error);
    message.error('获取 ExpertConfig 列表失败');
  } finally {
    loading.value = false;
  }
}

// 获取所有 Plugin
async function fetchPlugins() {
  try {
    const response = await requestClient.get<Plugin[]>('/v1/plugins');
    allPlugins.value = (response || []).filter((p) => p.enabled);
  } catch (error) {
    console.error('获取 Plugin 列表失败:', error);
  }
}

// 获取所有 PluginContext
async function fetchPluginContexts() {
  try {
    const response = await requestClient.get<PluginContext[]>(
      '/v1/plugin-contexts',
    );
    allPluginContexts.value = response || [];
  } catch (error) {
    console.error('获取 PluginContext 列表失败:', error);
  }
}

// 快速创建插件
function openQuickCreatePlugin() {
  quickCreatePluginForm.value = {
    plugin_code: '',
    plugin_name: '',
    context_template: '',
    variable_list: [],
  };
  quickCreatePluginVisible.value = true;
}

// 从模板提取变量
function extractVariablesFromTemplate(template: string): string[] {
  if (!template) return [];
  const regex = /\{\{([^{}]+)\}\}/g;
  const matches = template.matchAll(regex);
  const extracted = new Set<string>();
  for (const match of matches) {
    const varName = match[1]?.trim();
    if (varName) extracted.add(varName);
  }
  return [...extracted];
}

// 监听模板变化，自动提取变量
watch(
  () => quickCreatePluginForm.value.context_template,
  (newTemplate) => {
    quickCreatePluginForm.value.variable_list =
      extractVariablesFromTemplate(newTemplate);
  },
);

// 提交快速创建插件
async function submitQuickCreatePlugin() {
  const form = quickCreatePluginForm.value;

  if (!form.plugin_code.trim()) {
    message.error('请输入插件编码');
    return;
  }
  if (!form.plugin_name.trim()) {
    message.error('请输入插件名称');
    return;
  }

  quickCreatePluginLoading.value = true;
  try {
    const payload = {
      plugin_code: form.plugin_code.trim(),
      plugin_name: form.plugin_name.trim(),
      context_template: form.context_template.trim() || null,
      variable_list: form.variable_list.length > 0 ? form.variable_list : null,
      enabled: true, // 默认启用，这样可以立即使用
      remark: '通过 Expert 配置页面快速创建',
    };

    await requestClient.post('/v1/plugins', payload);
    message.success('插件创建成功');

    // 刷新插件列表
    await fetchPlugins();

    // 关闭创建弹窗
    quickCreatePluginVisible.value = false;

    // 自动选择新创建的插件
    handlePluginSelect(form.plugin_code.trim());
  } catch (error: any) {
    const errorMsg = error?.response?.data?.detail || '创建插件失败';
    message.error(errorMsg);
  } finally {
    quickCreatePluginLoading.value = false;
  }
}

// 打开插件选择弹窗
function openPluginSelectModal() {
  selectedPluginCode.value = null;
  tempVariableMapping.value = {};
  pluginConfigStep.value = 'select';
  editingPluginIndex.value = null; // 重置编辑模式
  pluginSearchText.value = '';
  pluginSelectModalVisible.value = true;
}

function handlePluginModalCancel() {
  pluginSelectModalVisible.value = false;
  editingPluginIndex.value = null;
}

// 选择插件后进入变量映射步骤
function handlePluginSelect(pluginCode: string) {
  selectedPluginCode.value = pluginCode;
  const plugin = allPlugins.value.find((p) => p.plugin_code === pluginCode);
  if (plugin && plugin.variable_list) {
    // 初始化变量映射，默认全选每个变量的所有上下文选项
    tempVariableMapping.value = {};
    for (const varName of plugin.variable_list) {
      // 获取该变量对应的上下文列表
      const contexts = contextsByVariable.value[varName] || [];
      // 默认全选所有上下文
      tempVariableMapping.value[varName] = contexts
        .map((ctx) => ctx.context_name)
        .filter((x): x is string => !!x);
    }
  }
  pluginConfigStep.value = 'mapping';
}

// 变量映射全选
function selectAllContexts() {
  if (!currentPlugin.value?.variable_list) return;
  for (const varName of currentPlugin.value.variable_list) {
    const contexts = contextsByVariable.value[varName] || [];
    tempVariableMapping.value[varName] = contexts
      .map((ctx) => ctx.context_name)
      .filter((x): x is string => !!x);
  }
}

// 变量映射全不选
function deselectAllContexts() {
  if (!currentPlugin.value?.variable_list) return;
  for (const varName of currentPlugin.value.variable_list) {
    tempVariableMapping.value[varName] = [];
  }
}

// 确认添加插件
function confirmAddPlugin() {
  if (!currentPlugin.value) return;

  const plugin = currentPlugin.value;
  const newPluginData = {
    plugin_code: plugin.plugin_code,
    plugin_name: plugin.plugin_name,
    context_template: plugin.context_template,
    variable_mapping: { ...tempVariableMapping.value },
  };

  // 编辑模式：更新已有插件
  if (editingPluginIndex.value === null) {
    // 添加模式：新增插件
    selectedPlugins.value.push(newPluginData);
  } else {
    selectedPlugins.value[editingPluginIndex.value] = newPluginData;
  }

  pluginSelectModalVisible.value = false;
  editingPluginIndex.value = null; // 重置编辑索引
  updatePluginConfigJson();
  updatePromptTemplate();
}

// 移除已选插件
function removePlugin(index: number) {
  selectedPlugins.value.splice(index, 1);
  updatePluginConfigJson();
  updatePromptTemplate();
}

// 上移插件
function movePluginUp(index: number) {
  if (index <= 0) return;
  const item = selectedPlugins.value[index];
  if (!item) return;
  selectedPlugins.value.splice(index, 1);
  selectedPlugins.value.splice(index - 1, 0, item);
  updatePluginConfigJson();
  updatePromptTemplate();
}

// 下移插件
function movePluginDown(index: number) {
  if (index >= selectedPlugins.value.length - 1) return;
  const item = selectedPlugins.value[index];
  if (!item) return;
  selectedPlugins.value.splice(index, 1);
  selectedPlugins.value.splice(index + 1, 0, item);
  updatePluginConfigJson();
  updatePromptTemplate();
}

// 拖拽排序
function handleDragStart(index: number) {
  dragIndex.value = index;
}

function handleDragOver(e: DragEvent, index: number) {
  e.preventDefault();
  if (dragIndex.value === null || dragIndex.value === index) return;

  const draggedItem = selectedPlugins.value[dragIndex.value];
  if (!draggedItem) return;
  selectedPlugins.value.splice(dragIndex.value, 1);
  selectedPlugins.value.splice(index, 0, draggedItem);
  dragIndex.value = index;
}

function handleDragEnd() {
  dragIndex.value = null;
  updatePluginConfigJson();
  updatePromptTemplate();
}

// 更新 plugin_config JSON 字符串
// 格式: [ { "plugin_code": "xxx", "variable_mapping": { "var": ["ctx"] } }, ... ]
function updatePluginConfigJson() {
  const config = selectedPlugins.value.map((sp) => ({
    plugin_code: sp.plugin_code,
    variable_mapping: sp.variable_mapping,
  }));
  formState.value.plugin_config = JSON.stringify(config, null, 2);
}

// 从 plugin_config JSON 解析为 selectedPlugins
// 支持新格式: [ { "plugin_code": "xxx", "variable_mapping": {...} }, ... ]
// 兼容旧格式: { "plugin_code": { "var": [...] } }
function parsePluginConfigToSelected(pluginConfig: any) {
  selectedPlugins.value = [];

  if (!pluginConfig) return;

  // 新格式: 数组
  if (Array.isArray(pluginConfig)) {
    for (const item of pluginConfig) {
      const plugin = allPlugins.value.find(
        (p) => p.plugin_code === item.plugin_code,
      );
      if (plugin) {
        const variableMapping = item.variable_mapping || {};
        const parsedMapping: Record<string, string[]> = {};

        // 解析变量配置
        for (const [varName, varConfig] of Object.entries(variableMapping)) {
          if (Array.isArray(varConfig)) {
            parsedMapping[varName] = varConfig;
          } else if (typeof varConfig === 'string') {
            parsedMapping[varName] = [varConfig];
          }
          // 忽略 keyword_tree 格式的旧配置
        }

        selectedPlugins.value.push({
          plugin_code: plugin.plugin_code,
          plugin_name: plugin.plugin_name,
          context_template: plugin.context_template,
          variable_mapping: parsedMapping,
        });
      }
    }
    return;
  }

  // 旧格式: 对象 { plugin_code: { var: [...] } }
  for (const [pluginCode, variableMapping] of Object.entries(pluginConfig)) {
    const plugin = allPlugins.value.find((p) => p.plugin_code === pluginCode);
    if (plugin) {
      selectedPlugins.value.push({
        plugin_code: plugin.plugin_code,
        plugin_name: plugin.plugin_name,
        context_template: plugin.context_template,
        variable_mapping: variableMapping as Record<string, string[]>,
      });
    }
  }
}

function handleAdd() {
  editingConfig.value = null;
  hasDraft.value = false;
  autoSaveStatus.value = 'idle';
  selectedPlugins.value = [];

  // ✅ 步骤1：打开弹窗时立即生成唯一编码
  const defaultType = 'GENERATION';
  const existingCodes = dataSource.value.map((item) => item.expert_config_code);
  const option = expertTypeOptions.find((o) => o.value === defaultType);
  const prefix = option?.codePrefix || 'ge';
  const generatedCode = generateUniqueCode(prefix, existingCodes);

  // 根据生成的编码创建名称
  const now = new Date();
  const dateStr = `${String(now.getFullYear()).slice(2)}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`;
  const randomPart = generatedCode.split('_').pop() || '';
  const generatedName = `${option?.namePrefix || '生文'}_${dateStr}_${randomPart}`;

  formState.value = {
    expert_config_code: generatedCode,
    expert_config_name: generatedName,
    description: '',
    tenant_code: undefined,
    expert_type: defaultType,
    expert_app: '',
    expert_service: '',
    expert_func: '',
    expert_func_name: '',
    model_code: '',
    model_config: '{\n  "temperature": 0,\n  "max_tokens": 2000\n}',
    plugin_config: '[]',
    prompt_template: '',
    enabled: 'true',
  };

  // 重置校验状态
  allowManualCodeEdit.value = false;
  codeValidationStatus.value = 'valid';
  codeValidationMessage.value = '✓ 已自动生成唯一编码';

  // ✅ 重置折叠面板为收起状态
  collapseActiveKey.value = [];

  modalVisible.value = true;
}

async function openEditorForCode(code?: string) {
  if (!code) {
    handleAdd();
    return;
  }
  const record = dataSource.value.find(
    (item) => item.expert_config_code === code,
  );
  if (!record) {
    message.error(`未找到 ExpertConfig：${code}`);
    return;
  }
  await handleEdit(record);
}

async function handleHeaderSelectChange(code: SelectValue) {
  if (!code || typeof code !== 'string') return;
  selectedExpertCode.value = code;
  await openEditorForCode(code);
  router.replace({
    path: route.path,
    query: { ...route.query, code },
  });
}

// 当选择 Expert 类型时，自动生成编码和名称
function onExpertTypeChange(expertType: SelectValue) {
  if (!expertType || typeof expertType !== 'string') return;

  // 只在新建时自动生成（编辑时不覆盖）
  if (editingConfig.value) return;

  // 只在未手动编辑编码时才重新生成
  if (allowManualCodeEdit.value) return;

  const existingCodes = dataSource.value.map((item) => item.expert_config_code);
  const option = expertTypeOptions.find((o) => o.value === expertType);
  const prefix = option?.codePrefix || 'ge';
  const generatedCode = generateUniqueCode(prefix, existingCodes);

  // 根据生成的编码创建名称
  const now = new Date();
  const dateStr = `${String(now.getFullYear()).slice(2)}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`;
  const randomPart = generatedCode.split('_').pop() || '';
  const generatedName = `${option?.namePrefix || '生文'}_${dateStr}_${randomPart}`;

  formState.value.expert_config_code = generatedCode;
  formState.value.expert_config_name = generatedName;

  // 重置校验状态
  codeValidationStatus.value = 'valid';
  codeValidationMessage.value = '✓ 已自动生成唯一编码';
}

async function handleEdit(record: ExpertConfig) {
  // 检查上线状态
  try {
    const checkResult = await checkCanModifyApi(
      'ExpertConfig',
      record.expert_config_code,
    );

    if (!checkResult.allowed) {
      if (checkResult.action === 'reject') {
        // 已上线，直接拒绝编辑
        message.error(checkResult.reason || '该配置已上线，不可编辑');
        return;
      } else if (checkResult.action === 'confirm') {
        // 有引用关系，需要确认
        Modal.confirm({
          title: '确认编辑',
          content: checkResult.reason,
          okText: '继续编辑',
          cancelText: '取消',
          onOk: async () => {
            await proceedEdit(record);
          },
        });
        return;
      }
    }
  } catch (error) {
    console.error('检查编辑权限失败:', error);
    // 检查失败时，为了安全起见，继续检查本地状态
    if (record.publish_status === 'PUBLISHED') {
      message.error('该配置已上线，不可编辑');
      return;
    }
  }

  // 允许编辑
  await proceedEdit(record);
}

function handleEditRoute(record: ExpertConfig) {
  router.push({
    path: '/config/expert-edit',
    query: { code: record.expert_config_code },
  });
}

async function handleBackToList() {
  // 页面模式下返回列表前，如果有修改则保存草稿
  const currentState = JSON.stringify(formState.value);
  const hasChanges =
    initialFormState.value && currentState !== initialFormState.value;
  if (hasChanges && formState.value.expert_config_code) {
    try {
      await requestClient.post('/v1/snapshots/draft', {
        entity_type: 'expert_config',
        entity_code: formState.value.expert_config_code,
        entity_id: editingConfig.value?.id || null,
        content: { ...formState.value },
      });
    } catch (error) {
      console.error('返回列表时保存草稿失败:', error);
    }
  }
  router.push(expertManagementPath);
}

async function proceedEdit(record: ExpertConfig) {
  editingConfig.value = record;
  hasDraft.value = false;
  autoSaveStatus.value = 'idle';

  // 检查是否有草稿
  const draft = await checkDraft(record.expert_config_code);
  if (draft) {
    Modal.confirm({
      title: '发现未保存的草稿',
      content: `上次编辑于 ${formatTime(draft.create_time)}，是否恢复草稿内容？`,
      okText: '恢复草稿',
      cancelText: '使用最新数据',
      onOk: () => {
        restoreDraftContent(draft);
        modalVisible.value = true;
      },
      onCancel: async () => {
        // 用户选择"使用最新数据"，删除旧草稿
        await deleteDraft(record.expert_config_code);
        loadRecordToForm(record);
        modalVisible.value = true;
      },
    });
  } else {
    loadRecordToForm(record);
    modalVisible.value = true;
  }
}

// 加载记录到表单
function loadRecordToForm(record: ExpertConfig) {
  // 标记正在加载表单数据，防止触发自动保存
  isLoadingForm.value = true;

  formState.value = {
    expert_config_code: record.expert_config_code,
    expert_config_name: record.expert_config_name,
    description: record.description || '',
    tenant_code: record.tenant_code || undefined,
    expert_type: record.expert_type || 'GENERATION',
    expert_app: record.expert_app || '',
    expert_service: record.expert_service || '',
    expert_func: record.expert_func || '',
    expert_func_name: (record as any).expert_func_name || '',
    model_code: record.model_code || '',
    model_config: JSON.stringify(record.model_config || {}, null, 2),
    plugin_config: JSON.stringify(record.plugin_config || [], null, 2),
    prompt_template: record.prompt_template || '',
    enabled: record.enabled ? 'true' : 'false',
  };
  // 解析 plugin_config 到 selectedPlugins
  parsePluginConfigToSelected(record.plugin_config);

  // 编辑模式：重置校验状态
  allowManualCodeEdit.value = false;
  codeValidationStatus.value = 'idle';
  codeValidationMessage.value = '';

  // 保存初始状态，用于后续对比是否有修改
  initialFormState.value = JSON.stringify(formState.value);

  // 延迟重置标志位，确保初始加载不触发自动保存
  // 注意：autoSaveDraft 有 2000ms 防抖，这里 500ms 足够安全
  setTimeout(() => {
    isLoadingForm.value = false;
  }, 500);
}

// ✅ 实时编码校验（防抖500ms）
const validateExpertCode = useDebounceFn(async (code: string) => {
  if (!code || code.trim() === '') {
    codeValidationStatus.value = 'idle';
    codeValidationMessage.value = '请输入编码或使用自动生成';
    return;
  }

  codeValidationStatus.value = 'checking';
  codeValidationMessage.value = '🔄 正在校验...';

  try {
    const exists = await checkCodeExists('expert_config', code);
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
  () => formState.value.expert_config_code,
  (newCode) => {
    if (allowManualCodeEdit.value && !editingConfig.value) {
      validateExpertCode(newCode);
    }
  },
);

// 监听手动编辑开关
function onManualEditToggle(event: { target: { checked: boolean } }) {
  const { checked } = event.target;
  if (!checked && !editingConfig.value) {
    // 取消手动编辑，重新生成编码
    const existingCodes = dataSource.value.map(
      (item) => item.expert_config_code,
    );
    const option = expertTypeOptions.find(
      (o) => o.value === formState.value.expert_type,
    );
    const prefix = option?.codePrefix || 'ge';
    const generatedCode = generateUniqueCode(prefix, existingCodes);

    const now = new Date();
    const dateStr = `${String(now.getFullYear()).slice(2)}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}`;
    const randomPart = generatedCode.split('_').pop() || '';
    const generatedName = `${option?.namePrefix || '生文'}_${dateStr}_${randomPart}`;

    formState.value.expert_config_code = generatedCode;
    formState.value.expert_config_name = generatedName;
    codeValidationStatus.value = 'valid';
    codeValidationMessage.value = '✓ 已自动生成唯一编码';
  } else if (checked) {
    // 启用手动编辑，触发一次校验
    validateExpertCode(formState.value.expert_config_code);
  }
}

// ✅ 保存按钮是否可用
const canSubmit = computed(() => {
  if (editingConfig.value) {
    // 编辑模式：始终可提交
    return true;
  }
  // 新建模式：如果手动编辑了编码
  if (allowManualCodeEdit.value) {
    // 如果编码为空，允许提交（会自动生成）
    if (
      !formState.value.expert_config_code ||
      !formState.value.expert_config_code.trim()
    ) {
      return true;
    }
    // 编码不为空，需要校验通过才能提交
    return codeValidationStatus.value === 'valid';
  }
  // 使用自动生成的编码，可以提交
  return true;
});

// ✅ 自定义校验规则：编码校验
const expertCodeValidator = (_rule: any, value: string) => {
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

function handleView(record: ExpertConfig) {
  viewingConfig.value = record;
  detailVisible.value = true;
}

async function handleDelete(record: ExpertConfig) {
  // 检查上线状态
  try {
    const checkResult = await checkCanModifyApi(
      'ExpertConfig',
      record.expert_config_code,
    );

    if (!checkResult.allowed) {
      if (checkResult.action === 'reject') {
        // 已上线，直接拒绝删除
        message.error(checkResult.reason || '该配置已上线，不可删除');
        return;
      } else if (checkResult.action === 'confirm') {
        // 有引用关系，需要确认
        Modal.confirm({
          title: '确认删除',
          content: `${checkResult.reason}\n\n是否继续删除？`,
          okText: '继续删除',
          cancelText: '取消',
          okButtonProps: { danger: true },
          onOk: async () => {
            await proceedDelete(record);
          },
        });
        return;
      }
    }
  } catch (error) {
    console.error('检查删除权限失败:', error);
    // 检查失败时，为了安全起见，继续检查本地状态
    if (record.publish_status === 'PUBLISHED') {
      message.error('该配置已上线，不可删除');
      return;
    }
  }

  // 允许删除
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除 ExpertConfig "${record.expert_config_name}" 吗？`,
    okText: '确定',
    cancelText: '取消',
    okButtonProps: { danger: true },
    onOk: async () => {
      await proceedDelete(record);
    },
  });
}

async function proceedDelete(record: ExpertConfig) {
  try {
    await requestClient.delete(`/v1/expert-configs/${record.id}`);
    message.success('删除成功');
    fetchConfigs();
  } catch {
    message.error('删除失败');
  }
}

function handleDebug(record: ExpertConfig) {
  // 跳转到专家调试面板，并传递 expert_config_code
  router.push({
    path: '/expert/debug',
    query: {
      expert_config_code: record.expert_config_code,
    },
  });
}

function handleCopy(record: ExpertConfig) {
  copySourceConfig.value = record;
  copyFormState.value = {
    expert_config_code: `${record.expert_config_code}_copy`,
    expert_config_name: `${record.expert_config_name}_copy`,
  };
  copyModalVisible.value = true;
}

function goToPluginEdit(plugin: SelectedPlugin, index: number) {
  // 查找完整的 plugin 信息
  const fullPlugin = allPlugins.value.find(
    (p: Plugin) => p.plugin_code === plugin.plugin_code,
  );
  if (!fullPlugin) {
    message.warning('未找到插件信息');
    return;
  }

  // 设置编辑模式
  editingPluginIndex.value = index;
  selectedPluginCode.value = fullPlugin.plugin_code;

  // 预填充变量映射
  tempVariableMapping.value = { ...plugin.variable_mapping };

  // 直接跳到配置步骤
  pluginConfigStep.value = 'mapping';
  pluginSelectModalVisible.value = true;
}

async function handleCopySubmit() {
  if (!copySourceConfig.value) return;
  try {
    await copyFormRef.value?.validateFields();
    const payload = {
      expert_config_code: copyFormState.value.expert_config_code,
      expert_config_name: copyFormState.value.expert_config_name,
    };
    await requestClient.post(
      `/v1/expert-configs/${copySourceConfig.value.id}/copy`,
      payload,
    );
    message.success('复制成功');
    copyModalVisible.value = false;
    await fetchConfigs();
  } catch (error) {
    console.error('复制失败:', error);
    message.error('复制失败');
  }
}

async function handleSubmit() {
  try {
    // ✅ 新建模式：如果编码为空，自动生成一个
    if (!editingConfig.value && !formState.value.expert_config_code.trim()) {
      const existingCodes = dataSource.value.map(
        (item) => item.expert_config_code,
      );
      const option = expertTypeOptions.find(
        (o) => o.value === formState.value.expert_type,
      );
      const prefix = option?.codePrefix || 'ge';
      formState.value.expert_config_code = generateUniqueCode(
        prefix,
        existingCodes,
      );
      message.success(`已自动生成编码：${formState.value.expert_config_code}`);
    }

    // 表单校验
    await formRef.value?.validateFields();

    // ✅ 新建模式 + 手动编辑：提交前最后一次校验
    if (
      !editingConfig.value &&
      allowManualCodeEdit.value &&
      formState.value.expert_config_code.trim()
    ) {
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
      const exists = await checkCodeExists(
        'expert_config',
        formState.value.expert_config_code,
      );
      if (exists) {
        message.error(
          `编码 "${formState.value.expert_config_code}" 已存在，请使用其他编码`,
        );
        codeValidationStatus.value = 'invalid';
        codeValidationMessage.value = '此编码已被使用，请修改';
        return;
      }
    }

    // 名称唯一性校验
    const nameExists = await checkNameExists(
      'expert_config',
      formState.value.expert_config_name,
      editingConfig.value ? editingConfig.value.id : undefined,
    );
    if (nameExists) {
      message.error(
        `名称 "${formState.value.expert_config_name}" 已存在，请使用其他名称`,
      );
      return;
    }

    // 解析 JSON 字段
    let modelConfig, pluginConfig;
    try {
      modelConfig = JSON.parse(formState.value.model_config);
    } catch {
      message.error('模型配置 JSON 格式错误');
      return;
    }
    try {
      pluginConfig = JSON.parse(formState.value.plugin_config);
    } catch {
      message.error('Plugin 配置 JSON 格式错误');
      return;
    }

    const payload = {
      expert_config_code: formState.value.expert_config_code,
      expert_config_name: formState.value.expert_config_name,
      description: formState.value.description || null,
      tenant_code: formState.value.tenant_code || null,
      expert_type: formState.value.expert_type || null,
      expert_app: formState.value.expert_app || null,
      expert_service: formState.value.expert_service || null,
      expert_func: formState.value.expert_func || null,
      expert_func_name: formState.value.expert_func_name || null,
      model_code: formState.value.model_code || null,
      model_config: modelConfig,
      plugin_config: pluginConfig,
      prompt_template: formState.value.prompt_template || null,
      enabled: formState.value.enabled === 'true',
    };

    if (editingConfig.value) {
      await requestClient.put(
        `/v1/expert-configs/${editingConfig.value.id}`,
        payload,
      );
      message.success('更新成功');
    } else {
      await requestClient.post('/v1/expert-configs', payload);
      message.success('创建成功');
    }

    // 保存成功后删除草稿
    if (formState.value.expert_config_code) {
      await deleteDraft(formState.value.expert_config_code);
    }

    // 保存成功后更新 initialFormState，防止关闭时误判为"有修改"
    initialFormState.value = JSON.stringify(formState.value);

    // 先刷新数据，再关闭 Modal
    await fetchConfigs();
    modalVisible.value = false;
    if (isPageMode.value) {
      router.push(expertManagementPath);
    }
  } catch (error: any) {
    console.error('提交失败:', error);
    message.error(editingConfig.value ? '更新失败' : '创建失败');
  }
}

const filteredData = () => {
  let result = dataSource.value;

  // 关键词搜索（编码/名称）
  if (searchText.value) {
    const keyword = searchText.value.toLowerCase();
    result = result.filter(
      (item) =>
        item.expert_config_code.toLowerCase().includes(keyword) ||
        item.expert_config_name.toLowerCase().includes(keyword),
    );
  }

  // 租户筛选
  if (filterTenantCode.value) {
    result = result.filter(
      (item) => item.tenant_code === filterTenantCode.value,
    );
  }

  // 是否删除筛选
  if (filterIsDeleted.value !== undefined && filterIsDeleted.value !== '') {
    const isDeleted = filterIsDeleted.value === 'true';
    result = result.filter((item) => item.is_deleted === isDeleted);
  }

  // 上下文名称搜索（搜索 plugin_config 中的 variable_mapping 的 context_name）
  if (filterContextName.value) {
    const keyword = filterContextName.value.toLowerCase();
    result = result.filter((item) => {
      if (!item.plugin_config) return false;
      const pluginConfig = item.plugin_config;
      // 新格式：数组
      if (Array.isArray(pluginConfig)) {
        return pluginConfig.some((pc: any) => {
          if (!pc.variable_mapping) return false;
          return Object.values(pc.variable_mapping).some((ctxNames: any) =>
            (ctxNames as string[]).some((name) =>
              name.toLowerCase().includes(keyword),
            ),
          );
        });
      }
      // 旧格式：对象
      return Object.values(pluginConfig).some((mapping: any) =>
        Object.values(mapping).some((ctxNames: any) =>
          (ctxNames as string[]).some((name) =>
            name.toLowerCase().includes(keyword),
          ),
        ),
      );
    });
  }

  // 上下文内容搜索（搜索 prompt_template）
  if (filterContextContent.value) {
    const keyword = filterContextContent.value.toLowerCase();
    result = result.filter(
      (item) =>
        item.prompt_template &&
        item.prompt_template.toLowerCase().includes(keyword),
    );
  }

  // 按 update_time 排序
  result = [...result].toSorted((a, b) => {
    const timeA = new Date(a.update_time || a.create_time).getTime();
    const timeB = new Date(b.update_time || b.create_time).getTime();
    return sortOrder.value === 'desc' ? timeB - timeA : timeA - timeB;
  });

  return result;
};

// 重置筛选
function resetFilters() {
  searchText.value = '';
  filterTenantCode.value = undefined;
  filterIsDeleted.value = undefined;
  filterContextName.value = '';
  filterContextContent.value = '';
  sortOrder.value = 'desc';
}

// 格式化时间（直接显示，不做时区转换）
function formatTime(time: null | string) {
  if (!time) return '-';
  return time.replace('T', ' ').slice(0, 19);
}

// ========== 快照功能 ==========

// 自动保存草稿（debounce 2秒）
const autoSaveDraft = useDebounceFn(async () => {
  if (!modalVisible.value || !formState.value.expert_config_code) return;
  if (page_persistence.is_restoring.value) return;
  if (isLoadingForm.value) return; // 加载表单数据时不保存草稿

  // 只有表单内容与初始状态不同时才保存草稿
  const currentState = JSON.stringify(formState.value);
  if (initialFormState.value && currentState === initialFormState.value) return;

  autoSaveStatus.value = 'saving';
  try {
    await requestClient.post('/v1/snapshots/draft', {
      entity_type: 'expert_config',
      entity_code: formState.value.expert_config_code,
      entity_id: editingConfig.value?.id || null,
      content: { ...formState.value },
    });
    autoSaveStatus.value = 'saved';
    hasDraft.value = true;
    // 3秒后恢复空闲状态
    setTimeout(() => {
      if (autoSaveStatus.value === 'saved') {
        autoSaveStatus.value = 'idle';
      }
    }, 3000);
  } catch (error) {
    console.error('自动保存草稿失败:', error);
    autoSaveStatus.value = 'error';
  }
}, 2000);

// 检查是否有草稿
async function checkDraft(entityCode: string): Promise<null | Snapshot> {
  try {
    const response = await requestClient.get<{
      draft: null | Snapshot;
      has_draft: boolean;
    }>(`/v1/snapshots/draft/expert_config/${entityCode}`);
    if (response.has_draft && response.draft) {
      return response.draft;
    }
    return null;
  } catch {
    return null;
  }
}

// 删除草稿
async function deleteDraft(entityCode: string) {
  try {
    await requestClient.delete(
      `/v1/snapshots/draft/expert_config/${entityCode}`,
    );
    hasDraft.value = false;
  } catch (error) {
    console.error('删除草稿失败:', error);
  }
}

// 恢复草稿内容并保存到后端
async function restoreDraftContent(draft: Snapshot) {
  // 标记正在加载表单数据，防止触发自动保存
  isLoadingForm.value = true;

  const content = draft.content;
  formState.value = {
    expert_config_code: content.expert_config_code || '',
    expert_config_name: content.expert_config_name || '',
    description: content.description || '',
    tenant_code: content.tenant_code || undefined,
    expert_type: content.expert_type || 'GENERATION',
    expert_app: content.expert_app || '',
    expert_service: content.expert_service || '',
    expert_func: content.expert_func || '',
    expert_func_name: content.expert_func_name || '',
    model_code: content.model_code || '',
    model_config: content.model_config || '{}',
    plugin_config: content.plugin_config || '{}',
    prompt_template: content.prompt_template || '',
    enabled: content.enabled || 'true',
  };
  // 解析 plugin_config 到 selectedPlugins
  let pluginConfig = null;
  try {
    pluginConfig =
      typeof content.plugin_config === 'string'
        ? JSON.parse(content.plugin_config)
        : content.plugin_config;
  } catch {
    pluginConfig = null;
  }
  parsePluginConfigToSelected(pluginConfig);

  // 恢复草稿 = 接受草稿内容 = 自动保存到后端
  try {
    // 解析 JSON 字段
    let modelConfig, pluginConfigParsed;
    try {
      modelConfig =
        typeof formState.value.model_config === 'string'
          ? JSON.parse(formState.value.model_config)
          : formState.value.model_config;
    } catch {
      modelConfig = {};
    }
    try {
      pluginConfigParsed =
        typeof formState.value.plugin_config === 'string'
          ? JSON.parse(formState.value.plugin_config)
          : formState.value.plugin_config;
    } catch {
      pluginConfigParsed = [];
    }

    const payload = {
      expert_config_code: formState.value.expert_config_code,
      expert_config_name: formState.value.expert_config_name,
      description: formState.value.description || null,
      tenant_code: formState.value.tenant_code || null,
      expert_type: formState.value.expert_type || null,
      expert_app: formState.value.expert_app || null,
      expert_service: formState.value.expert_service || null,
      expert_func: formState.value.expert_func || null,
      expert_func_name: formState.value.expert_func_name || null,
      model_code: formState.value.model_code || null,
      model_config: modelConfig,
      plugin_config: pluginConfigParsed,
      prompt_template: formState.value.prompt_template || null,
      enabled: formState.value.enabled === 'true',
    };

    if (editingConfig.value) {
      await requestClient.put(
        `/v1/expert-configs/${editingConfig.value.id}`,
        payload,
      );
    }

    // 保存成功后删除草稿
    if (draft.entity_code) {
      await deleteDraft(draft.entity_code);
    }

    hasDraft.value = false;
    message.success('已恢复草稿并保存');
  } catch (error) {
    console.error('恢复草稿保存失败:', error);
    hasDraft.value = true;
    message.success('已恢复草稿');
  }

  // 恢复草稿后，将初始状态设为恢复后的表单状态
  initialFormState.value = JSON.stringify(formState.value);

  // 延迟重置标志位，确保初始加载不触发自动保存
  setTimeout(() => {
    isLoadingForm.value = false;
  }, 500);
}

// 获取版本历史
async function fetchVersionHistory(entityCode: string) {
  versionLoading.value = true;
  try {
    const response = await requestClient.get<{
      items: Snapshot[];
      total: number;
    }>(`/v1/snapshots/versions/expert_config/${entityCode}`);
    versionHistory.value = response?.items || [];
  } catch (error) {
    console.error('获取版本历史失败:', error);
    message.error('获取版本历史失败');
  } finally {
    versionLoading.value = false;
  }
}

// 打开版本历史抽屉
async function handleShowVersions(record: ExpertConfig) {
  currentEntityCode.value = record.expert_config_code;
  versionDrawerVisible.value = true;
  await fetchVersionHistory(record.expert_config_code);
}

// 查看版本详情
function handleViewVersion(snapshot: Snapshot) {
  viewingVersion.value = snapshot;
  versionDetailVisible.value = true;
}

// 恢复到指定版本
async function handleRestoreVersion(snapshot: Snapshot) {
  Modal.confirm({
    title: '确认恢复',
    content: `确定要恢复到版本 ${snapshot.version} 吗？当前内容将被覆盖。`,
    okText: '确定',
    cancelText: '取消',
    onOk: async () => {
      try {
        const content = snapshot.content;
        // 将快照内容提交到后端
        await requestClient.put(`/v1/expert-configs/${content.id}`, {
          expert_config_code: content.expert_config_code,
          expert_config_name: content.expert_config_name,
          description: content.description,
          expert_type: content.expert_type,
          expert_app: content.expert_app,
          expert_service: content.expert_service,
          expert_func: content.expert_func,
          model_code: content.model_code,
          model_config: content.model_config,
          plugin_config: content.plugin_config,
          prompt_template: content.prompt_template,
          enabled: content.enabled,
        });
        message.success(`已恢复到版本 ${snapshot.version}`);
        versionDrawerVisible.value = false;
        await fetchConfigs();
      } catch (error) {
        console.error('恢复版本失败:', error);
        message.error('恢复版本失败');
      }
    },
  });
}

// 监听 Modal 关闭，清理验证状态并保存草稿
watch(modalVisible, async (newVal) => {
  if (!newVal) {
    // Modal 关闭时，如果有修改则立即保存草稿
    const currentState = JSON.stringify(formState.value);
    const hasChanges =
      initialFormState.value && currentState !== initialFormState.value;
    if (hasChanges && formState.value.expert_config_code) {
      try {
        await requestClient.post('/v1/snapshots/draft', {
          entity_type: 'expert_config',
          entity_code: formState.value.expert_config_code,
          entity_id: editingConfig.value?.id || null,
          content: { ...formState.value },
        });
      } catch (error) {
        console.error('关闭时保存草稿失败:', error);
      }
    }

    // Modal 关闭时只清除验证状态，不重置表单值
    formRef.value?.clearValidate();
    editingConfig.value = null;
    autoSaveStatus.value = 'idle';
  }
});

// 监听表单变化，触发自动保存
watch(
  formState,
  () => {
    // 页面恢复或加载表单数据时，不触发自动保存
    if (page_persistence.is_restoring.value) return;
    if (isLoadingForm.value) return;
    // 只有表单内容与初始状态不同时才保存草稿
    const currentState = JSON.stringify(formState.value);
    const hasChanges =
      initialFormState.value && currentState !== initialFormState.value;
    if (
      modalVisible.value &&
      formState.value.expert_config_code &&
      hasChanges
    ) {
      autoSaveDraft();
    }
  },
  { deep: true },
);

// 监听路由查询参数变化，自动更新搜索框
watch(
  () => route.query.search,
  (newSearch) => {
    if (newSearch && typeof newSearch === 'string') {
      searchText.value = newSearch;
    }
  },
);

// 监听是否删除筛选变化，自动重新获取数据
watch(filterIsDeleted, async () => {
  await fetchConfigs();
});

watch(
  () => [isPageMode.value, initialExpertCode.value, dataSource.value.length],
  async ([pageMode, code]) => {
    if (!pageMode) return;
    if (dataSource.value.length === 0) return;
    const targetCode = typeof code === 'string' ? code : '';
    selectedExpertCode.value = targetCode || undefined;
    if (hasAutoOpened.value) return;
    hasAutoOpened.value = true;
    await openEditorForCode(targetCode);
  },
);

onMounted(async () => {
  await Promise.all([
    fetchConfigs(),
    fetchProviderOptions(),
    fetchPlugins(),
    fetchPluginContexts(),
    fetchTenants(),
  ]);
  if (!isPageMode.value) {
    page_persistence.start_auto_persist();
    await page_persistence.restore();

    // 读取 URL 查询参数中的 search 值，自动填充搜索框
    if (route.query.search && typeof route.query.search === 'string') {
      searchText.value = route.query.search;
    }
    return;
  }

  if (!hasAutoOpened.value) {
    hasAutoOpened.value = true;
    await openEditorForCode(initialExpertCode.value);
  }
});

function handleTableChange(pag: any) {
  pagination.value.current = pag.current || 1;
  pagination.value.pageSize = pag.pageSize || pagination.value.pageSize;
}
</script>

<template>
  <div class="p-4">
    <Card
      v-if="!isPageMode"
      :title="route.meta.title || 'ExpertConfig 管理'"
      :bordered="false"
    >
      <!-- 筛选栏 -->
      <div class="filter-bar">
        <Space wrap :size="12">
          <Input
            v-model:value="searchText"
            placeholder="搜索编码/名称..."
            style="width: 180px"
            allow-clear
          >
            <template #prefix> 🔍 </template>
          </Input>
          <Select
            v-model:value="filterTenantCode"
            placeholder="租户筛选"
            style="width: 160px"
            allow-clear
            show-search
            :filter-option="
              (input: string, option: any) =>
                option.label?.toLowerCase().includes(input.toLowerCase()) ||
                option.value?.toLowerCase().includes(input.toLowerCase())
            "
          >
            <SelectOption value="" label="全部租户">全部租户</SelectOption>
            <SelectOption
              v-for="t in tenantOptions"
              :key="t.tenant_code"
              :value="t.tenant_code"
              :label="`${t.tenant_name} (${t.tenant_code})`"
            >
              {{ t.tenant_name }}
              <span class="ml-1 text-muted-foreground">
                ({{ t.tenant_code }})
              </span>
            </SelectOption>
          </Select>
          <Select
            v-model:value="filterIsDeleted"
            placeholder="是否删除"
            style="width: 120px"
            allow-clear
          >
            <SelectOption value="">全部</SelectOption>
            <SelectOption value="false">未删除</SelectOption>
            <SelectOption value="true">已删除</SelectOption>
          </Select>
          <Input
            v-model:value="filterContextName"
            placeholder="上下文名称搜索..."
            style="width: 160px"
            allow-clear
          />
          <Input
            v-model:value="filterContextContent"
            placeholder="Prompt 内容搜索..."
            style="width: 160px"
            allow-clear
          />
          <Select v-model:value="sortOrder" style="width: 130px">
            <SelectOption value="desc">更新时间 ↓</SelectOption>
            <SelectOption value="asc">更新时间 ↑</SelectOption>
          </Select>
          <Button @click="resetFilters">重置</Button>
          <Button type="primary" @click="handleAdd">
            ➕ 新增 ExpertConfig
          </Button>
        </Space>
      </div>

      <Table
        :columns="columns"
        :data-source="filteredData()"
        :loading="loading"
        :scroll="{ x: 1400 }"
        :pagination="{
          pageSize: 10,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
        }"
        row-key="id"
        size="middle"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'tenant_code'">
            <Tag v-if="record.tenant_code" color="cyan">
              {{ record.tenant_code }}
            </Tag>
            <Tag v-else color="default">全局</Tag>
          </template>
          <template v-else-if="column.key === 'enabled'">
            <Tag :color="record.enabled ? 'green' : 'red'">
              {{ record.enabled ? '启用' : '禁用' }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'publish_status'">
            <Tag
              :color="
                record.publish_status === 'PUBLISHED' ? 'blue' : 'default'
              "
            >
              {{ record.publish_status === 'PUBLISHED' ? '已发布' : '草稿' }}
            </Tag>
          </template>
          <!-- 隐藏类型列渲染 -->
          <!-- <template v-else-if="column.key === 'expert_type'">
            <Tag color="blue">{{ record.expert_type || '-' }}</Tag>
          </template> -->
          <template v-else-if="column.key === 'update_time'">
            {{ formatTime(record.update_time) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <Space>
              <Button
                type="link"
                size="small"
                :disabled="
                  (record as ExpertConfig).publish_status === 'PUBLISHED'
                "
                @click="handleEditRoute(record as ExpertConfig)"
              >
                ✏️ 编辑
              </Button>
              <Button
                type="link"
                size="small"
                @click="handleDebug(record as ExpertConfig)"
              >
                🔧 调试
              </Button>
              <Dropdown
                :trigger="['click']"
                :get-popup-container="getActionDropdownContainer"
              >
                <Button type="link" size="small">
                  更多
                  <span class="anticon-down">▼</span>
                </Button>
                <template #overlay>
                  <Space direction="vertical" :size="0" style="padding: 4px 0">
                    <Button
                      type="text"
                      size="small"
                      block
                      style="text-align: left"
                      @click.stop="handleView(record as ExpertConfig)"
                    >
                      👁️ 查看
                    </Button>
                    <Button
                      type="text"
                      size="small"
                      block
                      style="text-align: left"
                      @click.stop="handleCopy(record as ExpertConfig)"
                    >
                      📄 复制
                    </Button>
                    <Button
                      type="text"
                      size="small"
                      block
                      style="text-align: left"
                      @click.stop="handleShowVersions(record as ExpertConfig)"
                    >
                      📜 版本历史
                    </Button>
                    <Divider style="margin: 4px 0" />
                    <Button
                      type="text"
                      danger
                      size="small"
                      :disabled="
                        (record as ExpertConfig).publish_status === 'PUBLISHED'
                      "
                      block
                      style="text-align: left"
                      @click.stop="handleDelete(record as ExpertConfig)"
                    >
                      🗑️ 删除
                    </Button>
                  </Space>
                </template>
              </Dropdown>
            </Space>
          </template>
        </template>
      </Table>
    </Card>

    <!-- 复制弹窗 -->
    <Modal
      v-if="!isPageMode"
      v-model:open="copyModalVisible"
      title="复制 ExpertConfig"
      ok-text="复制"
      cancel-text="取消"
      @ok="handleCopySubmit"
    >
      <Form ref="copyFormRef" :model="copyFormState" layout="vertical">
        <FormItem
          label="新 Config 编码"
          name="expert_config_code"
          :rules="[{ required: true, message: '请输入新编码' }]"
        >
          <Input v-model:value="copyFormState.expert_config_code" />
        </FormItem>
        <FormItem
          label="新名称"
          name="expert_config_name"
          :rules="[{ required: true, message: '请输入新名称' }]"
        >
          <Input v-model:value="copyFormState.expert_config_name" />
        </FormItem>
      </Form>
    </Modal>

    <!-- 编辑弹窗/页面 -->
    <component
      :is="isPageMode ? 'div' : Modal"
      v-model:open="modalVisible"
      :title="!isPageMode ? null : undefined"
      :width="!isPageMode ? 1400 : undefined"
      :mask="!isPageMode"
      :mask-closable="!isPageMode"
      :keyboard="!isPageMode"
      :closable="!isPageMode"
      :footer="!isPageMode ? undefined : null"
      class="expert-config-modal"
      :class="[{ 'expert-config-modal-page': isPageMode }]"
      :ok-button-props="{ disabled: !canSubmit }"
      @ok="handleSubmit"
    >
      <div :class="isPageMode ? 'expert-edit-page' : ''">
        <div v-if="isPageMode" class="filter-bar">
          <div class="filter-title">
            <span class="title-text">编辑Expert</span>
            <span
              v-if="autoSaveStatus === 'saving'"
              class="auto-save-status saving"
            >
              <Badge status="processing" /> 保存中...
            </span>
            <span
              v-else-if="autoSaveStatus === 'saved'"
              class="auto-save-status saved"
            >
              <Badge status="success" /> 已自动保存
            </span>
            <span
              v-else-if="autoSaveStatus === 'error'"
              class="auto-save-status error"
            >
              <Badge status="error" /> 保存失败
            </span>
            <span v-else-if="hasDraft" class="auto-save-status draft">
              <Badge status="warning" /> 有草稿
            </span>
          </div>
          <div class="header-toolbar-row">
            <div class="header-selector-row">
              <div class="selector-label">Expert 选择</div>
              <Select
                v-model:value="selectedExpertCode"
                :options="expertSelectOptions"
                placeholder="请选择 Expert"
                show-search
                allow-clear
                class="selector-input"
                :filter-option="
                  (input: string, option: any) =>
                    option.label?.toLowerCase().includes(input.toLowerCase()) ||
                    option.value?.toLowerCase().includes(input.toLowerCase())
                "
                :get-popup-container="(trigger) => trigger.parentElement"
                @change="handleHeaderSelectChange"
              />
            </div>
            <div class="header-action-row">
              <Button @click="handleBackToList">返回</Button>
            </div>
          </div>
        </div>
        <div v-else class="modal-title-with-status">
          <span>{{
            editingConfig ? '编辑 ExpertConfig' : '新增 ExpertConfig'
          }}</span>
          <span
            v-if="autoSaveStatus === 'saving'"
            class="auto-save-status saving"
          >
            <Badge status="processing" /> 保存中...
          </span>
          <span
            v-else-if="autoSaveStatus === 'saved'"
            class="auto-save-status saved"
          >
            <Badge status="success" /> 已自动保存
          </span>
          <span
            v-else-if="autoSaveStatus === 'error'"
            class="auto-save-status error"
          >
            <Badge status="error" /> 保存失败
          </span>
          <span v-else-if="hasDraft" class="auto-save-status draft">
            <Badge status="warning" /> 有草稿
          </span>
        </div>
        <Form ref="formRef" :model="formState" layout="vertical">
          <div
            class="form-single-column"
            :class="[{ 'expert-edit-body': isPageMode }]"
          >
            <!-- 基本信息 -->
            <div class="form-section">
              <div class="form-section-title">基本信息</div>
              <div class="form-row">
                <FormItem
                  label="Expert 类型"
                  name="expert_type"
                  :rules="[{ required: true, message: '请先选择 Expert 类型' }]"
                  class="form-item-third"
                >
                  <Select
                    v-model:value="formState.expert_type"
                    :options="expertTypeOptions"
                    placeholder="请先选择类型"
                    show-search
                    :filter-option="true"
                    :get-popup-container="(trigger) => trigger.parentElement"
                    @change="onExpertTypeChange"
                  />
                </FormItem>
                <FormItem
                  label="名称"
                  name="expert_config_name"
                  :rules="[{ required: true, message: '请输入名称' }]"
                  class="form-item-third"
                >
                  <Input
                    v-model:value="formState.expert_config_name"
                    placeholder="选择类型后自动生成"
                  />
                </FormItem>
                <FormItem
                  label="启用状态"
                  name="enabled"
                  class="form-item-third"
                >
                  <Select
                    v-model:value="formState.enabled"
                    :options="[
                      { value: 'true', label: '启用' },
                      { value: 'false', label: '禁用' },
                    ]"
                    :get-popup-container="(trigger) => trigger.parentElement"
                  />
                </FormItem>
              </div>
              <FormItem label="描述" name="description">
                <Textarea
                  v-model:value="formState.description"
                  :rows="2"
                  placeholder="ExpertConfig 描述"
                />
              </FormItem>

              <!-- ✅ 高级选项：Config 编码配置 -->
              <Collapse
                v-if="!editingConfig"
                v-model:active-key="collapseActiveKey"
                style="margin-top: 16px"
              >
                <CollapsePanel key="1" header="🔧 高级选项">
                  <FormItem
                    label="Config 编码"
                    name="expert_config_code"
                    :rules="[
                      { validator: expertCodeValidator, trigger: 'change' },
                    ]"
                  >
                    <Input
                      v-model:value="formState.expert_config_code"
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
            </div>

            <!-- Plugin 配置 -->
            <div class="form-section">
              <div class="form-section-title">Plugin 配置</div>
              <div class="plugin-config-visual plugin-config-horizontal">
                <!-- 已选插件列表 -->
                <div class="plugin-list-horizontal">
                  <div
                    v-for="(sp, index) in selectedPlugins"
                    :key="`${sp.plugin_code}-${index}`"
                    class="plugin-item"
                    draggable="true"
                    @dragstart="handleDragStart(index)"
                    @dragover="(e) => handleDragOver(e, index)"
                    @dragend="handleDragEnd"
                  >
                    <div class="plugin-item-header">
                      <span class="drag-handle">☰</span>
                      <span class="plugin-order">{{ index + 1 }}</span>
                      <Tag color="blue">{{ sp.plugin_name }}</Tag>
                      <code class="plugin-code">{{ sp.plugin_code }}</code>
                      <div class="plugin-actions">
                        <Button
                          type="link"
                          size="small"
                          @click="goToPluginEdit(sp, index)"
                        >
                          编辑
                        </Button>
                        <Button
                          type="text"
                          size="small"
                          :disabled="index === 0"
                          @click="movePluginUp(index)"
                        >
                          ⬆️
                        </Button>
                        <Button
                          type="text"
                          size="small"
                          :disabled="index === selectedPlugins.length - 1"
                          @click="movePluginDown(index)"
                        >
                          ⬇️
                        </Button>
                        <Button
                          type="text"
                          danger
                          size="small"
                          @click="removePlugin(index)"
                        >
                          🗑️
                        </Button>
                      </div>
                    </div>
                    <div class="plugin-item-mapping">
                      <div
                        v-for="(ctxNames, varName) in sp.variable_mapping"
                        :key="varName"
                        class="mapping-row"
                      >
                        <code class="var-name">{{ varName }}</code>
                        <span class="mapping-arrow">→</span>
                        <Tag
                          v-for="ctx in ctxNames"
                          :key="ctx"
                          color="green"
                          size="small"
                        >
                          {{ ctx }}
                        </Tag>
                      </div>
                    </div>
                  </div>

                  <!-- 空状态 -->
                  <div
                    v-if="selectedPlugins.length === 0"
                    class="empty-plugins"
                  >
                    <span>暂无插件，点击右侧按钮添加</span>
                  </div>
                </div>

                <!-- 添加按钮 -->
                <Button
                  type="dashed"
                  class="add-plugin-btn-inline"
                  @click="openPluginSelectModal"
                >
                  ➕ 添加插件
                </Button>
              </div>
            </div>

            <!-- Prompt 模板 -->
            <div class="form-section">
              <div class="form-section-title">Prompt 模板</div>
              <FormItem label="Prompt 模板" name="prompt_template">
                <MonacoEditor
                  v-model:model-value="formState.prompt_template"
                  language="prompt"
                  height="280px"
                  placeholder="Expert 的提示词模板，使用 {{变量名}} 引用 Plugin 变量"
                />
              </FormItem>
            </div>

            <!-- 服务调用配置 和 模型配置 -->
            <div class="form-row-sections">
              <!-- 服务调用配置 -->
              <div class="form-section form-section-half">
                <div class="form-section-title">服务调用配置</div>
                <FormItem
                  label="Expert App"
                  name="expert_app"
                  :rules="[{ required: true, message: '请输入 Expert App' }]"
                >
                  <Input
                    v-model:value="formState.expert_app"
                    placeholder="如: content-executor"
                  />
                  <div class="form-item-hint">服务应用标识（Dapr App ID）</div>
                </FormItem>
                <FormItem
                  label="Expert Service"
                  name="expert_service"
                  :rules="[
                    { required: true, message: '请输入 Expert Service' },
                  ]"
                >
                  <Input
                    v-model:value="formState.expert_service"
                    placeholder="请输入 Expert service 名称"
                  />
                  <div class="form-item-hint">服务名称（HTTP 路由前缀）</div>
                </FormItem>
                <div class="form-row">
                  <FormItem
                    label="Expert Func"
                    name="expert_func"
                    :rules="[{ required: true, message: '请输入 Expert Func' }]"
                    class="form-item-half"
                  >
                    <Input
                      v-model:value="formState.expert_func"
                      placeholder="如: CriticContentQuality"
                    />
                  </FormItem>
                  <FormItem
                    label="显示名称"
                    name="expert_func_name"
                    class="form-item-half"
                  >
                    <Input
                      v-model:value="formState.expert_func_name"
                      placeholder="如: 内容质量（用于图表展示）"
                    />
                  </FormItem>
                </div>
              </div>

              <!-- 模型配置 -->
              <div class="form-section form-section-half">
                <div class="form-section-title">模型配置</div>
                <FormItem label="模型" name="model_code">
                  <ModelSelect
                    v-model:value="formState.model_code"
                    placeholder="选择模型（从 LLM Provider 获取）"
                    allow-clear
                  />
                  <div class="form-item-hint">
                    💡 模型列表从内部 LLM Provider 配置中动态获取
                  </div>
                </FormItem>
                <FormItem label="模型参数 (JSON)" name="model_config">
                  <MonacoEditor
                    v-model:model-value="formState.model_config"
                    language="json"
                    height="120px"
                    placeholder="输入 JSON 格式的模型配置"
                    :format-on-mount="true"
                  />
                </FormItem>
              </div>
            </div>
            <div v-if="isPageMode" class="page-form-footer">
              <Space>
                <Button @click="handleBackToList">返回列表</Button>
                <Button
                  type="primary"
                  :disabled="!canSubmit"
                  @click="handleSubmit"
                >
                  保存
                </Button>
              </Space>
            </div>
          </div>
        </Form>
      </div>
    </component>

    <!-- 插件选择弹窗 -->
    <Modal
      v-model:open="pluginSelectModalVisible"
      :title="pluginModalTitle"
      :width="600"
      :footer="null"
      @cancel="handlePluginModalCancel"
    >
      <!-- 步骤1: 选择插件 -->
      <div v-if="pluginConfigStep === 'select'" class="plugin-select-container">
        <div class="plugin-search-bar">
          <Input
            v-model:value="pluginSearchText"
            placeholder="搜索插件名称或编码..."
            allow-clear
            style="flex: 1"
          >
            <template #prefix> 🔍 </template>
          </Input>
          <Button type="primary" ghost @click="openQuickCreatePlugin">
            ➕ 新建插件
          </Button>
        </div>
        <div class="plugin-select-list">
          <div
            v-for="plugin in filteredPlugins"
            :key="plugin.plugin_code"
            class="plugin-select-item"
            @click="handlePluginSelect(plugin.plugin_code)"
          >
            <div class="plugin-select-header">
              <Tag color="blue">{{ plugin.plugin_name }}</Tag>
              <code>{{ plugin.plugin_code }}</code>
              <Tag
                v-if="
                  selectedPlugins.some(
                    (sp) => sp.plugin_code === plugin.plugin_code,
                  )
                "
                color="green"
              >
                已添加
                {{
                  selectedPlugins.filter(
                    (sp) => sp.plugin_code === plugin.plugin_code,
                  ).length
                }}
                次
              </Tag>
            </div>
            <div class="plugin-select-vars">
              <span>变量: </span>
              <Tag
                v-for="v in plugin.variable_list || []"
                :key="v"
                size="small"
              >
                {{ v }}
              </Tag>
              <span v-if="!plugin.variable_list?.length">无</span>
            </div>
          </div>
          <div v-if="filteredPlugins.length === 0" class="empty-hint">
            <div>
              {{ pluginSearchText ? '未找到匹配的插件' : '暂无可用插件' }}
            </div>
            <Button
              type="link"
              style="margin-top: 8px"
              @click="openQuickCreatePlugin"
            >
              ➕ 快速创建一个插件
            </Button>
          </div>
        </div>
      </div>

      <!-- 步骤2: 配置变量映射 -->
      <div v-else-if="pluginConfigStep === 'mapping'" class="variable-mapping">
        <div class="mapping-header">
          <Tag color="blue">{{ currentPlugin?.plugin_name }}</Tag>
          <Button size="small" @click="pluginConfigStep = 'select'">
            返回选择
          </Button>
        </div>

        <div v-if="currentPlugin?.variable_list?.length" class="mapping-form">
          <div class="mapping-hint-row">
            <span class="mapping-hint">请为每个变量选择对应的上下文：</span>
            <Space>
              <Button size="small" @click="selectAllContexts">全选</Button>
              <Button size="small" @click="deselectAllContexts">全不选</Button>
            </Space>
          </div>
          <div
            v-for="varName in currentPlugin.variable_list"
            :key="varName"
            class="mapping-field"
          >
            <code class="field-var">{{ varName }}</code>
            <span class="field-arrow">→</span>
            <Select
              v-model:value="tempVariableMapping[varName]"
              mode="multiple"
              placeholder="选择上下文（可多选）"
              style="width: 320px"
              :max-tag-count="3"
            >
              <SelectOption
                v-for="ctx in contextsByVariable[varName] || []"
                :key="ctx.context_name"
                :value="ctx.context_name"
              >
                {{ ctx.context_name }}
                <span v-if="ctx.context" class="ctx-hint">
                  ({{ ctx.context?.slice(0, 20) }}...)
                </span>
              </SelectOption>
            </Select>
          </div>
        </div>
        <div v-else class="no-vars-hint">该插件没有需要配置的变量</div>

        <div class="mapping-actions">
          <Button @click="handlePluginModalCancel">取消</Button>
          <Button type="primary" @click="confirmAddPlugin">
            {{ editingPluginIndex !== null ? '确认保存' : '确认添加' }}
          </Button>
        </div>
      </div>
    </Modal>

    <!-- 快速创建插件弹窗 -->
    <Modal
      v-model:open="quickCreatePluginVisible"
      title="快速创建插件"
      :width="600"
      :confirm-loading="quickCreatePluginLoading"
      @ok="submitQuickCreatePlugin"
      @cancel="quickCreatePluginVisible = false"
    >
      <Form layout="vertical" class="quick-create-plugin-form">
        <FormItem
          label="插件编码"
          required
          :validate-status="!quickCreatePluginForm.plugin_code ? 'error' : ''"
        >
          <Input
            v-model:value="quickCreatePluginForm.plugin_code"
            placeholder="如: my_new_plugin"
          />
          <div class="form-item-hint">唯一标识，建议使用英文下划线命名</div>
        </FormItem>

        <FormItem
          label="插件名称"
          required
          :validate-status="!quickCreatePluginForm.plugin_name ? 'error' : ''"
        >
          <Input
            v-model:value="quickCreatePluginForm.plugin_name"
            placeholder="如: 我的新插件"
          />
        </FormItem>

        <FormItem label="内容模板">
          <Textarea
            v-model:value="quickCreatePluginForm.context_template"
            placeholder="使用 {{变量名}} 定义变量，如：&#10;你是一个{{角色}}，正在{{场景}}中..."
            :rows="5"
          />
          <div class="form-item-hint">
            使用双花括号语法定义变量，变量会自动提取
          </div>
        </FormItem>

        <FormItem label="提取的变量">
          <div class="extracted-vars">
            <Tag
              v-for="v in quickCreatePluginForm.variable_list"
              :key="v"
              color="blue"
            >
              {{ v }}
            </Tag>
            <span
              v-if="quickCreatePluginForm.variable_list.length === 0"
              class="no-vars"
            >
              暂无变量，请在模板中使用双花括号语法
            </span>
          </div>
        </FormItem>
      </Form>
    </Modal>

    <!-- 详情抽屉 -->
    <Drawer
      v-if="!isPageMode"
      v-model:open="detailVisible"
      title="ExpertConfig 详情"
      :width="900"
    >
      <template v-if="viewingConfig">
        <Descriptions
          :column="2"
          bordered
          size="middle"
          class="detail-descriptions"
        >
          <DescriptionsItem label="编码" :span="2">
            <span class="code-value">{{
              viewingConfig.expert_config_code
            }}</span>
          </DescriptionsItem>
          <DescriptionsItem label="名称">
            <span class="text-value">{{
              viewingConfig.expert_config_name
            }}</span>
          </DescriptionsItem>
          <DescriptionsItem label="类型">
            <Tag color="blue">{{ viewingConfig.expert_type || '-' }}</Tag>
          </DescriptionsItem>
          <DescriptionsItem label="模型">
            <Tag color="purple">{{ viewingConfig.model_code || '-' }}</Tag>
          </DescriptionsItem>
          <DescriptionsItem label="状态">
            <Tag :color="viewingConfig.enabled ? 'green' : 'red'">
              {{ viewingConfig.enabled ? '启用' : '禁用' }}
            </Tag>
          </DescriptionsItem>
          <DescriptionsItem label="Expert App" :span="2">
            <span class="code-value">{{
              viewingConfig.expert_app || '-'
            }}</span>
          </DescriptionsItem>
          <DescriptionsItem label="Expert Service" :span="2">
            <span class="code-value">{{
              viewingConfig.expert_service || '-'
            }}</span>
          </DescriptionsItem>
          <DescriptionsItem label="Expert Func" :span="2">
            <span class="code-value">{{
              viewingConfig.expert_func || '-'
            }}</span>
          </DescriptionsItem>
          <DescriptionsItem label="描述" :span="2">
            <span class="text-value">{{
              viewingConfig.description || '-'
            }}</span>
          </DescriptionsItem>
          <DescriptionsItem label="创建时间">
            {{ formatTime(viewingConfig.create_time) }}
          </DescriptionsItem>
          <DescriptionsItem label="更新时间">
            {{ formatTime(viewingConfig.update_time) }}
          </DescriptionsItem>
        </Descriptions>

        <Card title="模型配置" size="small" class="mt-4">
          <pre class="config-json">{{
            JSON.stringify(viewingConfig.model_config, null, 2)
          }}</pre>
        </Card>

        <Card title="Plugin 配置" size="small" class="mt-4">
          <pre class="config-json">{{
            JSON.stringify(viewingConfig.plugin_config, null, 2)
          }}</pre>
        </Card>

        <Card title="Prompt 模板" size="small" class="mt-4">
          <pre class="config-json prompt-template">{{
            viewingConfig.prompt_template || '-'
          }}</pre>
        </Card>
      </template>
    </Drawer>

    <!-- 版本历史抽屉 -->
    <Drawer
      v-if="!isPageMode"
      v-model:open="versionDrawerVisible"
      title="版本历史"
      :width="600"
      class="version-drawer"
    >
      <div v-if="versionLoading" class="version-loading">加载中...</div>
      <div v-else-if="versionHistory.length === 0" class="version-empty">
        暂无版本历史
      </div>
      <Timeline v-else class="version-timeline">
        <TimelineItem
          v-for="snapshot in versionHistory"
          :key="snapshot.id"
          :color="snapshot.version === 1 ? 'green' : 'blue'"
        >
          <div class="version-item">
            <div class="version-header">
              <Tag :color="snapshot.version === 1 ? 'green' : 'blue'">
                版本 {{ snapshot.version }}
              </Tag>
              <span class="version-time">{{
                formatTime(snapshot.create_time)
              }}</span>
            </div>
            <div class="version-desc">
              {{ snapshot.description || '无描述' }}
            </div>
            <div class="version-actions">
              <Space>
                <Button
                  type="link"
                  size="small"
                  @click="handleViewVersion(snapshot)"
                >
                  👁️ 查看
                </Button>
                <Button
                  type="link"
                  size="small"
                  @click="handleRestoreVersion(snapshot)"
                >
                  🔄 恢复
                </Button>
              </Space>
            </div>
          </div>
        </TimelineItem>
      </Timeline>
    </Drawer>

    <!-- 版本详情抽屉 -->
    <Drawer
      v-if="!isPageMode"
      v-model:open="versionDetailVisible"
      :title="`版本 ${viewingVersion?.version} 详情`"
      :width="900"
      root-class-name="version-detail-drawer"
    >
      <template v-if="viewingVersion">
        <div class="version-detail-header">
          <Tag :color="viewingVersion.version === 1 ? 'green' : 'blue'">
            版本 {{ viewingVersion.version }}
          </Tag>
          <span class="version-detail-time">{{
            formatTime(viewingVersion.create_time)
          }}</span>
        </div>

        <Descriptions :column="2" bordered size="small" class="mt-4">
          <DescriptionsItem label="编码" :span="2">
            <code>{{ viewingVersion.content.expert_config_code }}</code>
          </DescriptionsItem>
          <DescriptionsItem label="名称">
            {{ viewingVersion.content.expert_config_name }}
          </DescriptionsItem>
          <DescriptionsItem label="类型">
            <Tag color="blue">
              {{ viewingVersion.content.expert_type || '-' }}
            </Tag>
          </DescriptionsItem>
          <DescriptionsItem label="模型">
            <Tag color="purple">
              {{ viewingVersion.content.model_code || '-' }}
            </Tag>
          </DescriptionsItem>
          <DescriptionsItem label="状态">
            <Tag :color="viewingVersion.content.enabled ? 'green' : 'red'">
              {{ viewingVersion.content.enabled ? '启用' : '禁用' }}
            </Tag>
          </DescriptionsItem>
          <DescriptionsItem label="Expert App" :span="2">
            <code>{{ viewingVersion.content.expert_app || '-' }}</code>
          </DescriptionsItem>
          <DescriptionsItem label="Expert Service" :span="2">
            <code>{{ viewingVersion.content.expert_service || '-' }}</code>
          </DescriptionsItem>
          <DescriptionsItem label="Expert Func" :span="2">
            <code>{{ viewingVersion.content.expert_func || '-' }}</code>
          </DescriptionsItem>
          <DescriptionsItem label="描述" :span="2">
            {{ viewingVersion.content.description || '-' }}
          </DescriptionsItem>
        </Descriptions>

        <Card title="模型配置" size="small" class="mt-4">
          <pre class="config-json">{{
            JSON.stringify(viewingVersion.content.model_config, null, 2)
          }}</pre>
        </Card>

        <Card title="Plugin 配置" size="small" class="mt-4">
          <pre class="config-json">{{
            JSON.stringify(viewingVersion.content.plugin_config, null, 2)
          }}</pre>
        </Card>

        <Card title="Prompt 模板" size="small" class="mt-4">
          <pre class="config-json prompt-template">{{
            viewingVersion.content.prompt_template || '-'
          }}</pre>
        </Card>

        <div class="version-detail-footer">
          <Button type="primary" @click="handleRestoreVersion(viewingVersion)">
            🔄 恢复到此版本
          </Button>
        </div>
      </template>
    </Drawer>
  </div>
</template>

<style scoped>
.p-4 {
  padding: 16px;
}

.mt-4 {
  margin-top: 16px;
}

.config-json {
  max-height: 400px;
  padding: 16px;
  margin: 0;
  overflow-y: auto;
  font-size: 13px;
  line-height: 1.5;
  color: hsl(var(--foreground));
  overflow-wrap: break-word;
  white-space: pre-wrap;
  background: hsl(var(--muted));
  border-radius: 6px;
}

.prompt-template {
  color: hsl(var(--foreground));
  background: hsl(var(--background-deep));
}

.form-section {
  max-width: 100%;
  padding: 16px 20px;
  margin-bottom: 20px;
  overflow: hidden;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.form-section-title {
  padding-left: 8px;
  margin-bottom: 16px;
  font-size: 14px;
  font-weight: 600;
  color: hsl(var(--primary));
  border-left: 3px solid hsl(var(--primary));
}

.form-row {
  display: flex;
  gap: 16px;
}

.form-item-half {
  flex: 1;
}

.form-item-third {
  flex: 1;
  min-width: 0;
}

/* 单列布局 */
.form-single-column {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 两个 section 并排 */
.form-row-sections {
  display: flex;
  gap: 24px;
}

.form-section-half {
  flex: 1;
  min-width: 0;
}

/* 四列表单行 */
.form-row-4 {
  display: flex;
  gap: 16px;
}

.form-item-quarter {
  flex: 1;
  min-width: 0;
}

/* Plugin 配置横向布局 */
.plugin-config-horizontal {
  flex-direction: column !important;
  gap: 12px;
  max-width: 100%;
  overflow: hidden;
}

.plugin-list-horizontal {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 100%;
  min-height: 40px;
  padding: 12px;
  overflow: hidden;
  background: hsl(var(--muted) / 20%);
  border-radius: 8px;
}

.plugin-list-horizontal .plugin-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  max-width: 100%;
  padding: 10px 12px;
  margin-bottom: 0;
  overflow: hidden;
}

.plugin-list-horizontal .plugin-item-header {
  display: flex;
  gap: 8px;
  align-items: center;
}

.plugin-list-horizontal .plugin-item-mapping {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  align-items: flex-start;
  width: 100%;
  max-width: 100%;
  padding-top: 8px;
  padding-left: 28px;
  margin-top: 0;
  overflow: hidden;
  border-top: none;
}

.plugin-list-horizontal .mapping-row {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  max-width: 100%;
  margin-bottom: 0;
}

/* 确保变量名和标签在同一行横向排列 */
.plugin-list-horizontal .mapping-row .ant-tag {
  flex-shrink: 0;
}

.plugin-list-horizontal .empty-plugins {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 40px;
  color: hsl(var(--muted-foreground));
}

.add-plugin-btn-inline {
  align-self: flex-start;
}

.form-section-full-height {
  display: flex;
  flex: 1;
  flex-direction: column;
}

.form-section-full-height .flex-grow-item {
  display: flex;
  flex: 1;
  flex-direction: column;
}

.form-section-full-height
  .flex-grow-item
  :deep(.ant-form-item-control-input-content) {
  display: flex;
  flex: 1;
}

.form-section-full-height .flex-grow-item :deep(textarea) {
  flex: 1;
  resize: none;
}

.form-section-full-height .flex-grow-item :deep(.monaco-editor-container) {
  flex: 1;
  min-height: 200px;
}

/* 代码输入框样式 */
.code-textarea {
  font-family: Monaco, Menlo, Consolas, monospace !important;
  font-size: 13px !important;
  line-height: 1.6 !important;
  color: hsl(var(--foreground)) !important;
  background: hsl(var(--muted)) !important;
  border: 1px solid hsl(var(--border)) !important;
  border-radius: 6px !important;
}

.code-textarea:focus {
  border-color: hsl(var(--primary)) !important;
  box-shadow: 0 0 0 2px hsl(var(--primary) / 20%) !important;
}

.code-textarea::placeholder {
  color: hsl(var(--muted-foreground)) !important;
}

.prompt-textarea {
  background: hsl(var(--background-deep)) !important;
}

/* Modal 整体样式优化 */
.expert-config-modal :deep(.ant-modal-body) {
  max-height: 70vh;
  padding: 24px;
  overflow-y: auto;
}

.expert-config-modal-page :deep(.ant-modal) {
  position: static;
  top: 0;
  width: 100% !important;
  max-width: 100%;
  padding-bottom: 0;
  margin: 0;
}

.expert-config-modal-page :deep(.ant-modal-content) {
  background: transparent;
  border-radius: 0;
  box-shadow: none;
}

.expert-config-modal-page :deep(.ant-modal-body) {
  max-height: none;
  padding: 0;
}

.expert-config-modal-page :deep(.ant-modal-header) {
  display: none;
}

.expert-config-modal-page :deep(.ant-modal-mask) {
  display: none;
}

.expert-config-modal-page :deep(.ant-modal-wrap) {
  position: static;
  overflow: visible;
}

.expert-edit-page {
  width: 100%;
  min-height: 100%;
  padding: 0;
  background: transparent;
}

.filter-bar {
  position: sticky;
  top: 0;
  z-index: 10;
  width: 100%;
  padding: 12px 24px 16px;
  margin: -12px -24px 24px;
  background: hsl(var(--background) / 92%);
  border-bottom: 1px solid hsl(var(--border));
  box-shadow:
    0 12px 24px hsl(var(--background) / 30%),
    0 1px 0 hsl(var(--border));
  backdrop-filter: blur(8px);
}

.expert-edit-body {
  padding: 12px 24px 32px;
}

.filter-title {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 0;
}

.title-text {
  font-size: 18px;
  font-weight: 700;
  color: transparent;
  background-image: linear-gradient(
    90deg,
    hsl(var(--primary)),
    hsl(var(--success))
  );
  background-clip: text;
}

.header-toolbar-row {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
}

.header-selector-row {
  display: flex;
  flex: 1;
  flex-wrap: nowrap;
  gap: 12px;
  align-items: center;
  min-width: 0;
  padding: 12px 14px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
}

.selector-label {
  font-weight: 600;
  color: hsl(var(--foreground));
}

.selector-input {
  flex: 1;
  min-width: 320px;
}

.header-action-row {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
}

.page-form-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 16px;
  margin-top: 8px;
  border-top: 1px solid hsl(var(--border));
}

/* 详情抽屉样式 */
.detail-descriptions :deep(.ant-descriptions-item-label) {
  width: 120px;
  font-weight: 500;
}

.code-value {
  display: inline-block;
  padding: 4px 12px;
  font-family: Monaco, Menlo, Consolas, monospace;
  font-size: 13px;
  line-height: 1.6;
  color: hsl(var(--foreground));
  word-break: break-all;
  background: hsl(var(--muted));
  border-radius: 4px;
}

.text-value {
  font-size: 14px;
  line-height: 1.6;
  color: hsl(var(--foreground));
}

code {
  padding: 2px 6px;
  font-family: Monaco, Menlo, monospace;
  font-size: 12px;
  color: hsl(var(--primary));
  background: hsl(var(--muted));
  border-radius: 4px;
}

/* Modal 标题带状态 */
.modal-title-with-status {
  display: flex;
  gap: 12px;
  align-items: center;
}

.auto-save-status {
  font-size: 12px;
  font-weight: normal;
}

.auto-save-status.saving {
  color: hsl(var(--primary));
}

.auto-save-status.saved {
  color: hsl(var(--success));
}

.auto-save-status.error {
  color: hsl(var(--destructive));
}

.auto-save-status.draft {
  color: hsl(var(--warning));
}

/* 版本历史抽屉样式 */
.version-loading,
.version-empty {
  padding: 40px 0;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.version-timeline {
  padding: 16px 0;
}

.version-item {
  padding: 8px 0;
}

.version-header {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 8px;
}

.version-time {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.version-desc {
  padding-left: 4px;
  margin-bottom: 8px;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.version-actions {
  padding-left: 4px;
}

/* 版本详情抽屉样式 */
.version-detail-header {
  display: flex;
  gap: 12px;
  align-items: center;
  padding-bottom: 16px;
  border-bottom: 1px solid hsl(var(--border));
}

.version-detail-time {
  font-size: 14px;
  color: hsl(var(--muted-foreground));
}

.version-detail-footer {
  padding-top: 16px;
  margin-top: 24px;
  text-align: right;
  border-top: 1px solid hsl(var(--border));
}

/* 模型选择器提示 */
.form-item-hint {
  margin-top: 4px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.form-item-hint a {
  color: hsl(var(--primary));
  text-decoration: none;
}

.form-item-hint a:hover {
  text-decoration: underline;
}

/* 编码校验状态样式 */
.validation-icon {
  font-size: 16px;
  cursor: help;
}

.text-green-500 {
  color: #10b981 !important;
}

.model-not-found {
  padding: 8px 16px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

/* Plugin 配置可视化样式 */
.plugin-config-visual {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.plugin-list {
  max-height: 300px;
  padding: 8px;
  overflow-y: auto;
  background: hsl(var(--background-deep));
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
}

.plugin-item {
  padding: 10px 12px;
  margin-bottom: 8px;
  cursor: grab;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
  transition: all 0.2s;
}

.plugin-item:hover {
  border-color: hsl(var(--primary));
  box-shadow: 0 2px 8px rgb(0 0 0 / 10%);
}

.plugin-item:active {
  cursor: grabbing;
}

.plugin-item:last-child {
  margin-bottom: 0;
}

.plugin-item-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.drag-handle {
  color: hsl(var(--foreground) / 40%);
  cursor: grab;
}

.plugin-order {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  font-size: 12px;
  font-weight: 600;
  color: white;
  background: hsl(var(--primary));
  border-radius: 50%;
}

.plugin-code {
  flex: 1;
  font-size: 12px;
  color: hsl(var(--foreground) / 60%);
}

.plugin-actions {
  display: flex;
  gap: 2px;
  align-items: center;
}

.plugin-actions .ant-btn {
  padding: 2px 6px;
  font-size: 12px;
}

.plugin-actions .ant-btn:disabled {
  opacity: 0.3;
}

.plugin-item-mapping {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-left: 28px;
}

.mapping-row {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  font-size: 12px;
}

.var-name {
  font-size: 11px;
  color: hsl(var(--primary));
}

.mapping-arrow {
  color: hsl(var(--foreground) / 40%);
}

.empty-plugins {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 80px;
  font-size: 14px;
  color: hsl(var(--foreground) / 40%);
}

.add-plugin-btn {
  margin-top: 4px;
}

.prompt-preview {
  max-height: 120px;
  overflow-y: auto;
  background: hsl(var(--background-deep));
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
}

.preview-title {
  padding: 6px 10px;
  font-size: 12px;
  font-weight: 500;
  color: hsl(var(--foreground) / 70%);
  background: hsl(var(--card));
  border-bottom: 1px solid hsl(var(--border));
}

.preview-content {
  padding: 8px 10px;
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: hsl(var(--foreground) / 80%);
  word-break: break-all;
  white-space: pre-wrap;
}

/* 插件选择弹窗样式 */
.plugin-select-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.plugin-search-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  padding-bottom: 8px;
  border-bottom: 1px solid hsl(var(--border));
}

.plugin-select-list {
  max-height: 350px;
  overflow-y: auto;
}

.plugin-select-item {
  padding: 12px;
  margin-bottom: 8px;
  cursor: pointer;
  border: 1px solid hsl(var(--border));
  border-radius: 6px;
  transition: all 0.2s;
}

.plugin-select-item:hover:not(.disabled) {
  background: hsl(var(--primary) / 5%);
  border-color: hsl(var(--primary));
}

.plugin-select-item.disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.plugin-select-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}

.plugin-select-vars {
  font-size: 12px;
  color: hsl(var(--foreground) / 60%);
}

.empty-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px;
  color: hsl(var(--foreground) / 40%);
  text-align: center;
}

/* 变量映射样式 */
.variable-mapping {
  padding: 8px 0;
}

.mapping-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.mapping-form {
  padding: 16px;
  background: hsl(var(--background-deep));
  border-radius: 6px;
}

.mapping-hint-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.mapping-hint {
  font-size: 13px;
  color: hsl(var(--foreground) / 70%);
}

.mapping-field {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}

.mapping-field:last-child {
  margin-bottom: 0;
}

.field-var {
  min-width: 120px;
  padding: 4px 8px;
  font-size: 13px;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 10%);
  border-radius: 4px;
}

.field-arrow {
  color: hsl(var(--foreground) / 40%);
}

.ctx-hint {
  font-size: 11px;
  color: hsl(var(--foreground) / 50%);
}

.no-vars-hint {
  padding: 30px;
  color: hsl(var(--foreground) / 50%);
  text-align: center;
}

.mapping-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  padding-top: 16px;
  margin-top: 20px;
  border-top: 1px solid hsl(var(--border));
}

/* 快速创建插件表单样式 */
.quick-create-plugin-form {
  padding: 8px 0;
}

.quick-create-plugin-form .form-item-hint {
  margin-top: 4px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.quick-create-plugin-form .form-item-hint code {
  padding: 2px 4px;
  font-family: monospace;
  font-size: 11px;
  background: hsl(var(--muted));
  border-radius: 3px;
}

.quick-create-plugin-form .extracted-vars {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 32px;
  padding: 8px;
  background: hsl(var(--muted));
  border-radius: 6px;
}

.quick-create-plugin-form .extracted-vars .no-vars {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}
</style>

<style>
/* 版本详情抽屉 - 使用 CSS 变量支持主题切换 */
.version-detail-drawer .ant-drawer-content {
  background: hsl(var(--background-deep));
}

.version-detail-drawer .ant-drawer-header {
  background: hsl(var(--card));
  border-bottom: 1px solid hsl(var(--border));
}

.version-detail-drawer .ant-drawer-title {
  color: hsl(var(--foreground));
}

.version-detail-drawer .ant-drawer-close {
  color: hsl(var(--muted-foreground));
}

.version-detail-drawer .ant-drawer-close:hover {
  color: hsl(var(--foreground));
}

.version-detail-drawer .ant-drawer-body {
  background: hsl(var(--background-deep));
}

/* Descriptions 主题适配 */
.version-detail-drawer .ant-descriptions {
  overflow: hidden;
  background: hsl(var(--card));
  border-radius: 8px;
}

.version-detail-drawer .ant-descriptions-bordered .ant-descriptions-view {
  border: 1px solid hsl(var(--border));
}

.version-detail-drawer .ant-descriptions-bordered .ant-descriptions-item-label {
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted));
  border-color: hsl(var(--border));
}

.version-detail-drawer
  .ant-descriptions-bordered
  .ant-descriptions-item-content {
  color: hsl(var(--foreground));
  background: hsl(var(--card));
  border-color: hsl(var(--border));
}

.version-detail-drawer .ant-descriptions-bordered .ant-descriptions-row {
  border-color: hsl(var(--border));
}

/* Card 主题适配 */
.version-detail-drawer .ant-card {
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.version-detail-drawer .ant-card-head {
  color: hsl(var(--foreground));
  background: hsl(var(--muted));
  border-bottom: 1px solid hsl(var(--border));
}

.version-detail-drawer .ant-card-head-title {
  color: hsl(var(--primary));
}

.version-detail-drawer .ant-card-body {
  background: hsl(var(--card));
}

/* code 标签主题适配 */
.version-detail-drawer code {
  padding: 2px 8px;
  font-family: 'Fira Code', Consolas, monospace;
  font-size: 13px;
  color: hsl(var(--primary));
  background: hsl(var(--muted));
  border-radius: 4px;
}

/* Dropdown 弹出层样式修复 */
:deep(.ant-dropdown) {
  z-index: 1050 !important;
}

:deep(.ant-dropdown-menu) {
  padding: 4px 0;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgb(0 0 0 / 15%);
}

:deep(.ant-dropdown .ant-space) {
  display: flex;
  flex-direction: column;
  width: 100%;
}

:deep(.ant-dropdown .ant-btn-text) {
  width: 100%;
  height: auto;
  padding: 8px 16px;
  line-height: 1.5;
  text-align: left;
  border-radius: 0;
}

:deep(.ant-dropdown .ant-btn-text:hover) {
  background: rgb(0 0 0 / 4%);
}
</style>
