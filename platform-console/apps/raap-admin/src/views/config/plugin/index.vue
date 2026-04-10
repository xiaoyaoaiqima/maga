<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import { useDebounceFn } from '@vueuse/core';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Collapse,
  CollapsePanel,
  Descriptions,
  DescriptionsItem,
  Drawer,
  Empty,
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Select,
  SelectOption,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Textarea,
  Timeline,
  TimelineItem,
  Tooltip,
} from 'ant-design-vue';

import { checkCanModifyApi } from '#/api/core/publish';
import { requestClient } from '#/api/request';
import CountTo from '#/components/CountTo.vue';
// 新增：动画组件
import EnhancedButton from '#/components/EnhancedButton.vue';
import MonacoEditor from '#/components/MonacoEditor.vue';
import SkeletonLoader from '#/components/SkeletonLoader.vue';
import { checkCodeExists, generateUniqueCode } from '#/utils/code_uniqueness';
import { use_page_persistence } from '#/utils/page_persistence';

// v2 新增：变量映射配置弹窗
import VariableMappingModal from './components/VariableMappingModal.vue';

// 快照接口定义
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

interface Plugin {
  id: number;
  plugin_code: string;
  plugin_name: string;
  plugin_type: null | string;
  variable_list: null | string[];
  context_template: null | string;
  enabled: boolean;
  remark: null | string;
  publish_status: 'DRAFT' | 'PUBLISHED';
  publish_time: null | string;
  publish_by: null | string;
  create_time: string;
  update_time: string;
  created_by: null | string;
  updated_by: null | string;
  // v2 新增字段
  strategy_id: null | number;
  variable_mappings: Array<{ label: string; variable_name: string }> | null;
  tenant_code: string;
}

const route = useRoute();

const loading = ref(false);
const dataSource = ref<Plugin[]>([]);
const searchText = ref('');
const modalVisible = ref(false);
const editingPlugin = ref<null | Plugin>(null);
const isSubmitting = ref(false);
const pagination = ref({
  current: 1,
  pageSize: 10,
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条`,
});

// 表单状态
const formState = reactive({
  plugin_code: '',
  plugin_name: '',
  plugin_type: '',
  variable_list: [] as string[],
  context_template: '',
  enabled: true,
  remark: '',
});

// 类型前缀映射
const pluginTypePrefixMap: Record<string, string> = {
  system_prompt: 'sp',
  user_prompt: 'up',
  context: 'ctx',
  template: 'tpl',
  other: 'oth',
};

// 变量输入
const newVariable = ref('');
// 手动添加的变量（不会被自动提取覆盖）
const manualVariables = ref<string[]>([]);

// 关联专家相关状态
interface RelatedExpert {
  id: number;
  expert_config_code: string;
  expert_config_name: string;
  expert_type: string;
  enabled: boolean;
  update_time: null | string;
  plugin_config_snapshot: null | Record<string, any>;
}

const relatedExperts = ref<RelatedExpert[]>([]);
const relatedExpertsLoading = ref(false);
const relatedExpertsTotal = ref(0);

// 统计数据
const stats = computed(() => {
  const allPlugins = dataSource.value;
  return {
    total: allPlugins.length,
    enabled: allPlugins.filter((p) => p.enabled).length,
    published: allPlugins.filter((p) => p.publish_status === 'PUBLISHED')
      .length,
    totalVariables: allPlugins.reduce(
      (sum, p) => sum + (p.variable_list?.length || 0),
      0,
    ),
  };
});

type PersistedPluginPageStateV1 = {
  current_entity_code: string;
  editing_plugin_id: null | number;
  form_state: {
    context_template: string;
    enabled: boolean;
    plugin_code: string;
    plugin_name: string;
    plugin_type: string;
    remark: string;
    variable_list: string[];
  };
  manual_variables: string[];
  modal_visible: boolean;
  pagination: { current: number; page_size: number };
  search_text: string;
  version_detail_visible: boolean;
  version_drawer_visible: boolean;
};

const page_persistence = use_page_persistence<PersistedPluginPageStateV1>({
  storage_key: 'raap_admin.config.plugin.persist.v1',
  version: 1,
  get_state: () => ({
    search_text: searchText.value || '',
    pagination: {
      current: pagination.value.current || 1,
      page_size: pagination.value.pageSize || 10,
    },
    modal_visible: !!modalVisible.value,
    editing_plugin_id: editingPlugin.value?.id ?? null,
    form_state: {
      plugin_code: formState.plugin_code || '',
      plugin_name: formState.plugin_name || '',
      plugin_type: formState.plugin_type || '',
      variable_list: formState.variable_list || [],
      context_template: formState.context_template || '',
      enabled: !!formState.enabled,
      remark: formState.remark || '',
    },
    manual_variables: manualVariables.value || [],
    version_drawer_visible: !!versionDrawerVisible.value,
    current_entity_code: currentEntityCode.value || '',
    version_detail_visible: !!versionDetailVisible.value,
  }),
  apply_state: async (persisted) => {
    searchText.value = persisted.search_text || '';
    pagination.value.current = persisted.pagination?.current || 1;
    pagination.value.pageSize = persisted.pagination?.page_size || 10;

    // 还原编辑弹窗 + 表单
    if (persisted.modal_visible) {
      const found =
        persisted.editing_plugin_id === null ||
        persisted.editing_plugin_id === undefined
          ? null
          : dataSource.value.find((x) => x.id === persisted.editing_plugin_id);
      editingPlugin.value = found || null;

      formState.plugin_code = persisted.form_state?.plugin_code || '';
      formState.plugin_name = persisted.form_state?.plugin_name || '';
      formState.plugin_type = persisted.form_state?.plugin_type || '';
      formState.variable_list = persisted.form_state?.variable_list || [];
      formState.context_template = persisted.form_state?.context_template || '';
      formState.enabled = persisted.form_state?.enabled ?? true;
      formState.remark = persisted.form_state?.remark || '';
      manualVariables.value = persisted.manual_variables || [];

      autoSaveStatus.value = 'idle';
      hasDraft.value = false;
      modalVisible.value = true;
    }

    // 还原版本抽屉
    currentEntityCode.value = persisted.current_entity_code || '';
    versionDrawerVisible.value = !!persisted.version_drawer_visible;
    versionDetailVisible.value = !!persisted.version_detail_visible;

    if (versionDrawerVisible.value && currentEntityCode.value) {
      await fetchVersionHistory(currentEntityCode.value);
    }
  },
});

// 快照相关状态
const versionDrawerVisible = ref(false);
const versionHistory = ref<Snapshot[]>([]);
const versionLoading = ref(false);
const autoSaveStatus = ref<'error' | 'idle' | 'saved' | 'saving'>('idle');
const hasDraft = ref(false);
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

// v2 新增：变量映射配置弹窗状态
const variableMappingModalOpen = ref(false);
const selectedPluginForMapping = ref<null | Plugin>(null);

// 打开变量映射配置弹窗
function handleOpenVariableMapping(record: Plugin) {
  selectedPluginForMapping.value = record;
  variableMappingModalOpen.value = true;
}

// 变量映射配置保存后刷新列表
function handleVariableMappingSaved() {
  fetchPlugins();
}

// 插件类型选项
const pluginTypeOptions = [
  { value: 'system_prompt', label: '系统 Prompt' },
  { value: 'user_prompt', label: '用户 Prompt' },
  { value: 'context', label: '上下文' },
  { value: 'template', label: '模板' },
  { value: 'other', label: '其他' },
];

const columns = [
  {
    title: 'Plugin 编码',
    dataIndex: 'plugin_code',
    key: 'plugin_code',
    width: 200,
  },
  {
    title: '名称',
    dataIndex: 'plugin_name',
    key: 'plugin_name',
    width: 200,
    ellipsis: true,
  },
  {
    title: '类型',
    dataIndex: 'plugin_type',
    key: 'plugin_type',
    width: 100,
  },
  {
    title: '变量',
    dataIndex: 'variable_list',
    key: 'variable_list',
    width: 200,
    ellipsis: true,
  },
  {
    title: '策略映射',
    dataIndex: 'strategy_id',
    key: 'strategy_binding',
    width: 120,
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
  { title: '操作', key: 'action', width: 320, fixed: 'right' as const },
];

// 关联专家表格列定义
const relatedExpertsColumns = [
  {
    title: '专家编码',
    dataIndex: 'expert_config_code',
    key: 'expert_config_code',
    width: 180,
  },
  {
    title: '专家名称',
    dataIndex: 'expert_config_name',
    key: 'expert_config_name',
    width: 180,
  },
  {
    title: '专家类型',
    dataIndex: 'expert_type',
    key: 'expert_type',
    width: 120,
  },
  { title: '状态', dataIndex: 'enabled', key: 'enabled', width: 80 },
  {
    title: '更新时间',
    dataIndex: 'update_time',
    key: 'update_time',
    width: 160,
  },
  { title: '操作', key: 'actions', width: 150, fixed: 'right' as const },
];

// 类型映射
const pluginTypeMap: Record<string, { color: string; label: string }> = {
  system_prompt: { label: '系统 Prompt', color: 'blue' },
  user_prompt: { label: '用户 Prompt', color: 'green' },
  context: { label: '上下文', color: 'orange' },
  template: { label: '模板', color: 'purple' },
  other: { label: '其他', color: 'default' },
};

// 模板内容 placeholder
const templatePlaceholder = `使用 {{变量名}} 定义变量，变量会自动提取

示例：
你是一个{{role}}，请帮助用户解决{{task}}相关的问题。

JSON 示例：
{"platform": "{{platform}}", "rules": "{{rules}}"}`;

// 获取 Plugin 列表
async function fetchPlugins() {
  loading.value = true;
  try {
    const response = await requestClient.get<Plugin[]>('/v1/plugins');
    dataSource.value = response || [];
  } catch (error) {
    console.error('获取 Plugin 列表失败:', error);
    message.error('获取 Plugin 列表失败');
  } finally {
    loading.value = false;
  }
}

// 重置表单
function resetForm() {
  formState.plugin_code = '';
  formState.plugin_name = '';
  formState.plugin_type = '';
  formState.variable_list = [];
  formState.context_template = '';
  formState.enabled = true;
  formState.remark = '';
  newVariable.value = '';
  manualVariables.value = [];
}

// 新增
async function handleAdd() {
  editingPlugin.value = null;
  resetForm();
  autoSaveStatus.value = 'idle';
  hasDraft.value = false;

  // ✅ 步骤1：打开弹窗时立即生成唯一编码（基于默认类型）
  const defaultType = 'context'; // 默认类型
  const existingCodes = dataSource.value.map((item) => item.plugin_code);
  const prefix = pluginTypePrefixMap[defaultType] || 'ctx';
  const generatedCode = generateUniqueCode(prefix, existingCodes);

  formState.plugin_code = generatedCode;
  formState.plugin_type = defaultType;

  // 重置校验状态
  allowManualCodeEdit.value = false;
  codeValidationStatus.value = 'valid';
  codeValidationMessage.value = '✓ 已自动生成唯一编码';

  // ✅ 重置折叠面板为收起状态
  collapseActiveKey.value = [];

  modalVisible.value = true;
}

// ========== 快照功能 ==========

// 自动保存草稿（debounce 2秒）
const autoSaveDraft = useDebounceFn(async () => {
  if (!modalVisible.value || !formState.plugin_code) return;
  if (page_persistence.is_restoring.value) return;

  autoSaveStatus.value = 'saving';
  try {
    await requestClient.post('/v1/snapshots/draft', {
      entity_type: 'plugin',
      entity_code: formState.plugin_code,
      entity_id: editingPlugin.value?.id || null,
      content: { ...formState },
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
    }>(`/v1/snapshots/draft/plugin/${entityCode}`);
    return response?.has_draft ? response.draft : null;
  } catch {
    return null;
  }
}

// 恢复草稿
function recoverDraft(snapshot: Snapshot) {
  const content = snapshot.content;
  formState.plugin_code = content.plugin_code || '';
  formState.plugin_name = content.plugin_name || '';
  formState.plugin_type = content.plugin_type || '';
  formState.variable_list = content.variable_list || [];
  formState.context_template = content.context_template || '';
  formState.enabled = content.enabled ?? true;
  formState.remark = content.remark || '';
  hasDraft.value = true;
  message.success('已恢复草稿');
}

// 获取版本历史
async function fetchVersionHistory(entityCode: string) {
  versionLoading.value = true;
  try {
    const response = await requestClient.get<{
      items: Snapshot[];
      total: number;
    }>(`/v1/snapshots/versions/plugin/${entityCode}`);
    versionHistory.value = response?.items || [];
  } catch (error) {
    console.error('获取版本历史失败:', error);
    message.error('获取版本历史失败');
  } finally {
    versionLoading.value = false;
  }
}

// 打开版本历史抽屉
async function handleShowVersions(record: Plugin) {
  currentEntityCode.value = record.plugin_code;
  versionDrawerVisible.value = true;
  await fetchVersionHistory(record.plugin_code);
}

// 查看版本详情
async function handleViewVersion(snapshot: Snapshot) {
  viewingVersion.value = snapshot;
  versionDetailVisible.value = true;

  // 获取关联的专家列表
  await fetchRelatedExperts(snapshot.entity_code);
}

// 获取关联专家列表
async function fetchRelatedExperts(pluginCode: string) {
  relatedExpertsLoading.value = true;
  try {
    const res = await requestClient.get<{
      items: RelatedExpert[];
      total: number;
    }>(`/v1/plugins/${pluginCode}/related-experts`, {
      params: { page: 1, page_size: 10 },
    });
    relatedExperts.value = res?.items || [];
    relatedExpertsTotal.value = res?.total || 0;
  } catch (error) {
    console.error('获取关联专家失败:', error);
    relatedExperts.value = [];
    relatedExpertsTotal.value = 0;
  } finally {
    relatedExpertsLoading.value = false;
  }
}

// 跳转到专家编辑页面（新窗口打开）
function goToExpertConfig(expertConfigCode: string) {
  // 在新标签页打开专家编辑页
  const url = `/config/expert-edit?code=${expertConfigCode}`;
  window.open(url, '_blank');
}

// 跳转到专家调试面板（新窗口打开）
function goToExpertDebug(expertConfigCode: string) {
  // 在新标签页打开专家调试面板
  const url = `/expert/debug?expert_config_code=${expertConfigCode}`;
  window.open(url, '_blank');
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
        await requestClient.put(`/v1/plugins/${content.id}`, {
          plugin_name: content.plugin_name,
          plugin_type: content.plugin_type,
          variable_list: content.variable_list,
          context_template: content.context_template,
          enabled: content.enabled,
          remark: content.remark,
        });
        message.success(`已恢复到版本 ${snapshot.version}`);
        versionDrawerVisible.value = false;
        versionDetailVisible.value = false;
        await fetchPlugins();
      } catch (error) {
        console.error('恢复版本失败:', error);
        message.error('恢复版本失败');
      }
    },
  });
}

// 监听表单变化，触发自动保存
watch(
  () => ({ ...formState }),
  () => {
    if (page_persistence.is_restoring.value) return;
    if (modalVisible.value && formState.plugin_code) {
      autoSaveDraft();
    }
  },
  { deep: true },
);

// 编辑
async function handleEdit(record: Plugin) {
  // 检查上线状态
  try {
    const checkResult = await checkCanModifyApi('Plugin', record.plugin_code);

    if (!checkResult.allowed) {
      if (checkResult.action === 'reject') {
        // 已上线，直接拒绝编辑
        message.error(checkResult.reason || '该插件已上线，不可编辑');
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
      message.error('该插件已上线，不可编辑');
      return;
    }
  }

  // 允许编辑
  await proceedEdit(record);
}

async function proceedEdit(record: Plugin) {
  editingPlugin.value = record;
  formState.plugin_code = record.plugin_code;
  formState.plugin_name = record.plugin_name;
  formState.plugin_type = record.plugin_type || '';
  formState.variable_list = record.variable_list || [];
  formState.context_template = record.context_template || '';
  formState.enabled = record.enabled;
  formState.remark = record.remark || '';
  newVariable.value = '';
  // 编辑时，保留原有变量中不在模板里的作为手动变量
  const templateVars = extractVariablesFromTemplate(
    record.context_template || '',
  );
  manualVariables.value = (record.variable_list || []).filter(
    (v) => !templateVars.includes(v),
  );
  autoSaveStatus.value = 'idle';
  hasDraft.value = false;

  // 编辑模式：重置校验状态
  allowManualCodeEdit.value = false;
  codeValidationStatus.value = 'idle';
  codeValidationMessage.value = '';

  modalVisible.value = true;

  // 检查是否有草稿
  const draft = await checkDraft(record.plugin_code);
  if (draft) {
    Modal.confirm({
      title: '发现草稿',
      content: '检测到有未保存的草稿，是否恢复？',
      okText: '恢复草稿',
      cancelText: '使用当前版本',
      onOk: () => {
        recoverDraft(draft);
      },
    });
  }
}

// ✅ 实时编码校验（防抖500ms）
const validatePluginCode = useDebounceFn(async (code: string) => {
  if (!code || code.trim() === '') {
    codeValidationStatus.value = 'idle';
    codeValidationMessage.value = '请输入编码或使用自动生成';
    return;
  }

  codeValidationStatus.value = 'checking';
  codeValidationMessage.value = '🔄 正在校验...';

  try {
    const exists = await checkCodeExists('plugin', code);
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
  () => formState.plugin_code,
  (newCode) => {
    if (allowManualCodeEdit.value && !editingPlugin.value) {
      validatePluginCode(newCode);
    }
  },
);

// 监听手动编辑开关
function onManualEditToggle(checked: boolean) {
  if (!checked && !editingPlugin.value) {
    // 取消手动编辑，重新生成编码
    const existingCodes = dataSource.value.map((item) => item.plugin_code);
    const prefix = pluginTypePrefixMap[formState.plugin_type] || 'ctx';
    formState.plugin_code = generateUniqueCode(prefix, existingCodes);
    codeValidationStatus.value = 'valid';
    codeValidationMessage.value = '✓ 已自动生成唯一编码';
  } else if (checked) {
    // 启用手动编辑，触发一次校验
    validatePluginCode(formState.plugin_code);
  }
}

// ✅ 保存按钮是否可用
const canSubmit = computed(() => {
  if (editingPlugin.value) {
    // 编辑模式：始终可提交
    return true;
  }
  // 新建模式：如果手动编辑了编码
  if (allowManualCodeEdit.value) {
    // 如果编码为空，允许提交（会自动生成）
    if (!formState.plugin_code || !formState.plugin_code.trim()) {
      return true;
    }
    // 编码不为空，需要校验通过才能提交
    return codeValidationStatus.value === 'valid';
  }
  // 使用自动生成的编码，可以提交
  return true;
});

// ✅ 自定义校验规则：编码校验
const pluginCodeValidator = (_rule: any, value: string) => {
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

// 删除
async function handleDelete(record: Plugin) {
  // 检查上线状态
  try {
    const checkResult = await checkCanModifyApi('Plugin', record.plugin_code);

    if (!checkResult.allowed) {
      if (checkResult.action === 'reject') {
        // 已上线，直接拒绝删除
        message.error(checkResult.reason || '该插件已上线，不可删除');
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
      message.error('该插件已上线，不可删除');
      return;
    }
  }

  // 允许删除
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除插件 "${record.plugin_name}" 吗？`,
    okText: '确定',
    cancelText: '取消',
    okButtonProps: { danger: true },
    onOk: async () => {
      await proceedDelete(record);
    },
  });
}

async function proceedDelete(record: Plugin) {
  try {
    await requestClient.delete(`/v1/plugins/${record.id}`);
    message.success('删除成功');
    fetchPlugins();
  } catch {
    message.error('删除失败');
  }
}

// 复制 - 打开编辑弹窗预填数据
function handleCopy(record: Plugin) {
  // 清空编辑状态，表示新建
  editingPlugin.value = null;

  // 预填表单数据 - 复制模式：使用原类型，名称加"(副本)"
  formState.plugin_type = record.plugin_type || '';
  formState.plugin_code = ''; // 新建模式不直接使用此字段
  formState.plugin_name = `${record.plugin_name}(副本)`;
  formState.variable_list = [...(record.variable_list || [])];
  formState.context_template = record.context_template || '';
  formState.enabled = true; // 默认启用
  formState.remark = `复制自 ${record.plugin_code}`;

  // 处理手动变量
  newVariable.value = '';
  const templateVars = extractVariablesFromTemplate(
    record.context_template || '',
  );
  manualVariables.value = (record.variable_list || []).filter(
    (v) => !templateVars.includes(v),
  );

  // 打开弹窗
  modalVisible.value = true;
}

// 提交表单
async function handleSubmit() {
  // ✅ 新建模式：如果编码为空，自动生成一个
  if (!editingPlugin.value && !formState.plugin_code.trim()) {
    const existingCodes = dataSource.value.map((item) => item.plugin_code);
    const prefix = pluginTypePrefixMap[formState.plugin_type] || 'ctx';
    formState.plugin_code = generateUniqueCode(prefix, existingCodes);
    message.success(`已自动生成编码：${formState.plugin_code}`);
  }

  // 表单验证
  if (!formState.plugin_name.trim()) {
    message.error('请输入 Plugin 名称');
    return;
  }
  if (
    !editingPlugin.value && // 新建模式：验证类型
    !formState.plugin_type
  ) {
    message.error('请选择插件类型');
    return;
  }

  // ✅ 新建模式 + 手动编辑：提交前最后一次校验
  if (
    !editingPlugin.value &&
    allowManualCodeEdit.value &&
    formState.plugin_code.trim()
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
    const exists = await checkCodeExists('plugin', formState.plugin_code);
    if (exists) {
      message.error(`编码 "${formState.plugin_code}" 已存在，请使用其他编码`);
      codeValidationStatus.value = 'invalid';
      codeValidationMessage.value = '此编码已被使用，请修改';
      return;
    }
  }

  isSubmitting.value = true;
  try {
    // 新建模式使用 formState.plugin_code，编辑模式使用原 code
    const pluginCode = editingPlugin.value
      ? formState.plugin_code.trim()
      : formState.plugin_code.trim();

    if (!pluginCode) {
      message.error('请输入编码');
      return;
    }

    const payload = {
      plugin_code: pluginCode,
      plugin_name: formState.plugin_name.trim(),
      plugin_type: formState.plugin_type || null,
      variable_list:
        formState.variable_list.length > 0 ? formState.variable_list : null,
      context_template: formState.context_template.trim() || null,
      enabled: formState.enabled,
      remark: formState.remark.trim() || null,
    };

    if (editingPlugin.value) {
      // 更新时不包含 plugin_code
      const { plugin_code: _plugin_code, ...updatePayload } = payload;
      await requestClient.put(
        `/v1/plugins/${editingPlugin.value.id}`,
        updatePayload,
      );
      message.success('更新成功');
    } else {
      await requestClient.post('/v1/plugins', payload);
      message.success('创建成功');

      // 创建成功后提示用户配置策略映射
      Modal.confirm({
        title: '🎉 插件创建成功！',
        content:
          '是否立即配置关键词策略映射？\n\n配置策略映射可以将插件变量关联到关键词策略的维度，实现动态内容生成。',
        okText: '立即配置',
        cancelText: '稍后配置',
        icon: null,
        onOk: async () => {
          // 重新获取列表以确保拿到最新的插件数据
          await fetchPlugins();
          // 从列表中找到刚创建的插件（通过 plugin_code 定位）
          const newPlugin = dataSource.value.find(
            (p) => p.plugin_code === payload.plugin_code,
          );
          if (newPlugin) {
            selectedPluginForMapping.value = newPlugin;
            variableMappingModalOpen.value = true;
          } else {
            message.warning('未找到刚创建的插件，请手动点击"映射"按钮');
          }
        },
        onCancel: () => {
          // 用户选择稍后配置，不做任何操作
        },
      });
    }

    // 保存成功后草稿会被后端自动删除
    hasDraft.value = false;
    autoSaveStatus.value = 'idle';

    await fetchPlugins();
    modalVisible.value = false;
  } catch (error: any) {
    const errorMsg =
      error?.response?.data?.detail ||
      (editingPlugin.value ? '更新失败' : '创建失败');
    message.error(errorMsg);
  } finally {
    isSubmitting.value = false;
  }
}

// 添加变量（手动添加）
function addVariable() {
  const v = newVariable.value.trim();
  if (!v) {
    message.warning('请输入变量名');
    return;
  }
  if (formState.variable_list.includes(v)) {
    message.warning('变量已存在');
    return;
  }
  // 添加到手动变量列表
  manualVariables.value.push(v);
  // 同时更新表单变量列表
  formState.variable_list = [...formState.variable_list, v];
  newVariable.value = '';
}

// 从模板自动提取变量
function extractVariablesFromTemplate(template: string): string[] {
  if (!template) return [];
  // 匹配 {{variable}} 格式，支持中英文变量名
  const regex = /\{\{([^{}]+)\}\}/g;
  const matches = template.matchAll(regex);
  const extracted = new Set<string>();
  for (const match of matches) {
    const varName = match[1]?.trim();
    if (varName) {
      extracted.add(varName);
    }
  }
  return [...extracted];
}

// 监听模板内容变化，自动提取变量
watch(
  () => formState.context_template,
  (newTemplate) => {
    if (page_persistence.is_restoring.value) return;
    const extractedVars = extractVariablesFromTemplate(newTemplate);
    // 合并自动提取的变量和手动添加的变量
    const allVars = [...new Set([...extractedVars, ...manualVariables.value])];
    formState.variable_list = allVars;
  },
);

// 搜索过滤
const filteredData = computed(() => {
  if (!searchText.value) return dataSource.value;
  const keyword = searchText.value.toLowerCase();
  return dataSource.value.filter(
    (item) =>
      item.plugin_code.toLowerCase().includes(keyword) ||
      item.plugin_name.toLowerCase().includes(keyword) ||
      (item.remark && item.remark.toLowerCase().includes(keyword)),
  );
});

// 格式化时间（直接显示，不做时区转换）
function formatTime(time: null | string) {
  if (!time) return '-';
  // 数据库存的是北京时间，直接格式化显示
  return time.replace('T', ' ').slice(0, 19);
}

// JSON 语法高亮格式化
function formatJsonWithHighlight(template: null | string): string {
  if (!template) return '';

  try {
    // 尝试解析和格式化 JSON
    const parsed = JSON.parse(template);
    const formatted = JSON.stringify(parsed, null, 2);

    // 限制行数
    const lines = formatted.split('\n');
    const truncated =
      lines.length > 20
        ? `${lines.slice(0, 20).join('\n')}\n... (更多内容)`
        : formatted;

    // 添加语法高亮
    return (
      truncated
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        // 高亮 key（双引号内的字符串后跟冒号）
        .replaceAll(/"([^"]+)"(\s*:)/g, '<span class="json-key">"$1"</span>$2')
        // 高亮字符串值
        .replaceAll(/:\s*"([^"]*)"/g, ': <span class="json-string">"$1"</span>')
        // 高亮数字
        .replaceAll(/:\s*(\d+\.?\d*)/g, ': <span class="json-number">$1</span>')
        // 高亮布尔值
        .replaceAll(
          /:\s*(true|false)/g,
          ': <span class="json-boolean">$1</span>',
        )
        // 高亮 null
        .replaceAll(/:\s*(null)/g, ': <span class="json-null">$1</span>')
    );
  } catch {
    // 非 JSON，直接返回（转义 HTML）
    const escaped = template
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;');

    if (escaped.length > 500) {
      return `${escaped.slice(0, 500)}... (更多内容)`;
    }
    return escaped;
  }
}

// 截断变量名（用于列表页显示）
function truncateVar(v: string, maxLen = 5): string {
  if (v.length <= maxLen) return v;
  return `${v.slice(0, maxLen)}...`;
}

onMounted(async () => {
  await fetchPlugins();
  page_persistence.start_auto_persist();
  await page_persistence.restore();

  // 处理 URL 参数：如果有 id 和 action=edit，自动打开编辑弹窗
  const { id, action } = route.query;
  if (id && action === 'edit') {
    const pluginId = Number(id);
    const targetPlugin = dataSource.value.find((p) => p.id === pluginId);
    if (targetPlugin) {
      await handleEdit(targetPlugin);
    } else {
      message.warning('未找到对应的插件');
    }
  }
});

function handleTableChange(pag: any) {
  pagination.value.current = pag.current || 1;
  pagination.value.pageSize = pag.pageSize || pagination.value.pageSize;
}
</script>

<template>
  <div class="p-4">
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
          {{ route.meta.title || '专家插件管理' }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">编码/名称</span>
          <Input
            v-model:value="searchText"
            placeholder="搜索 Plugin 编码/名称..."
            style="width: 200px"
            allow-clear
          />
        </div>
        <div class="filter-actions">
          <EnhancedButton @click="fetchPlugins">🔄 刷新</EnhancedButton>
          <EnhancedButton type="primary" @click="handleAdd">
            ➕ 新增 Plugin
          </EnhancedButton>
        </div>
      </div>
    </div>

    <!-- 统计卡片区域 -->
    <div class="stats-grid">
      <Card class="stat-card" :bordered="false">
        <div class="stat-content">
          <div class="stat-icon">📦</div>
          <div class="stat-info">
            <div class="stat-label">Plugin 总数</div>
            <div class="stat-value">
              <CountTo
                :end-value="stats.total"
                :start-value="0"
                :duration="1.5"
                :decimals="0"
                suffix=" 个"
              />
            </div>
          </div>
        </div>
      </Card>

      <Card class="stat-card" :bordered="false">
        <div class="stat-content">
          <div class="stat-icon">✅</div>
          <div class="stat-info">
            <div class="stat-label">已启用</div>
            <div class="stat-value text-green-500">
              <CountTo
                :end-value="stats.enabled"
                :start-value="0"
                :duration="1.5"
                :decimals="0"
                suffix=" 个"
              />
            </div>
          </div>
        </div>
      </Card>

      <Card class="stat-card" :bordered="false">
        <div class="stat-content">
          <div class="stat-icon">🚀</div>
          <div class="stat-info">
            <div class="stat-label">已发布</div>
            <div class="stat-value text-blue-500">
              <CountTo
                :end-value="stats.published"
                :start-value="0"
                :duration="1.5"
                :decimals="0"
                suffix=" 个"
              />
            </div>
          </div>
        </div>
      </Card>

      <Card class="stat-card" :bordered="false">
        <div class="stat-content">
          <div class="stat-icon">📝</div>
          <div class="stat-info">
            <div class="stat-label">总变量数</div>
            <div class="stat-value text-purple-500">
              <CountTo
                :end-value="stats.totalVariables"
                :start-value="0"
                :duration="1.5"
                :decimals="0"
                suffix=" 个"
              />
            </div>
          </div>
        </div>
      </Card>
    </div>

    <Card :bordered="false" class="main-card">
      <!-- 骨架屏加载状态 -->
      <SkeletonLoader v-if="loading" type="table" :rows="pagination.pageSize" />

      <!-- 数据表格 -->
      <Table
        v-else
        :columns="columns"
        :data-source="filteredData"
        :scroll="{ x: 1500 }"
        :pagination="pagination"
        row-key="id"
        size="middle"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <!-- Plugin 编码列 - 悬停显示完整配置 -->
          <template v-if="column.key === 'plugin_code'">
            <Tooltip placement="right" :overlay-style="{ maxWidth: '600px' }">
              <template #title>
                <div class="plugin-detail-tooltip">
                  <div class="tooltip-header">
                    <span class="tooltip-icon">🧩</span>
                    <span class="tooltip-title">{{ record.plugin_name }}</span>
                    <Tag
                      :color="record.enabled ? 'success' : 'error'"
                      size="small"
                      class="tooltip-status"
                    >
                      {{ record.enabled ? '启用' : '禁用' }}
                    </Tag>
                  </div>

                  <div class="tooltip-section">
                    <div class="tooltip-row">
                      <span class="tooltip-label">编码</span>
                      <code class="tooltip-code">{{ record.plugin_code }}</code>
                    </div>
                    <div class="tooltip-row">
                      <span class="tooltip-label">类型</span>
                      <Tag
                        v-if="record.plugin_type"
                        :color="
                          pluginTypeMap[record.plugin_type]?.color || 'default'
                        "
                        size="small"
                      >
                        {{
                          pluginTypeMap[record.plugin_type]?.label ||
                          record.plugin_type
                        }}
                      </Tag>
                      <span v-else class="tooltip-empty">未设置</span>
                    </div>
                  </div>

                  <div
                    v-if="record.variable_list?.length"
                    class="tooltip-section"
                  >
                    <div class="tooltip-section-title">📦 变量列表</div>
                    <div class="tooltip-vars">
                      <Tag
                        v-for="v in record.variable_list"
                        :key="v"
                        color="processing"
                        size="small"
                      >
                        {{ v }}
                      </Tag>
                    </div>
                  </div>

                  <div v-if="record.context_template" class="tooltip-section">
                    <div class="tooltip-section-title">📄 模板内容</div>
                    <div class="tooltip-json-viewer">
                      <!-- eslint-disable vue/no-v-html -- 用户可控的模板内容，用于开发调试 -->
                      <pre
                        class="tooltip-template"
                        v-html="
                          formatJsonWithHighlight(record.context_template)
                        "
                      ></pre>
                      <!-- eslint-enable vue/no-v-html -->
                    </div>
                  </div>

                  <div class="tooltip-footer">
                    <span>更新: {{ formatTime(record.update_time) }}</span>
                  </div>
                </div>
              </template>
              <span class="plugin-code-cell">{{ record.plugin_code }}</span>
            </Tooltip>
          </template>
          <template v-else-if="column.key === 'plugin_type'">
            <Tag
              v-if="record.plugin_type"
              :color="pluginTypeMap[record.plugin_type]?.color || 'default'"
            >
              {{
                pluginTypeMap[record.plugin_type]?.label || record.plugin_type
              }}
            </Tag>
            <span v-else class="text-gray-400">-</span>
          </template>
          <template v-else-if="column.key === 'variable_list'">
            <template
              v-if="record.variable_list && record.variable_list.length > 0"
            >
              <Tooltip v-if="record.variable_list.length > 3" placement="top">
                <template #title>
                  <div class="var-tooltip">
                    <Tag
                      v-for="v in record.variable_list"
                      :key="v"
                      color="blue"
                      class="tooltip-tag"
                    >
                      {{ v }}
                    </Tag>
                  </div>
                </template>
                <div class="variable-cell">
                  <Tag
                    v-for="v in record.variable_list.slice(0, 3)"
                    :key="v"
                    color="blue"
                    class="variable-tag"
                  >
                    {{ truncateVar(v) }}
                  </Tag>
                  <Tag color="default" class="variable-tag">
                    +{{ record.variable_list.length - 3 }}
                  </Tag>
                </div>
              </Tooltip>
              <Tooltip v-else placement="top">
                <template #title>
                  <div class="var-tooltip">
                    <Tag
                      v-for="v in record.variable_list"
                      :key="v"
                      color="blue"
                      class="tooltip-tag"
                    >
                      {{ v }}
                    </Tag>
                  </div>
                </template>
                <div class="variable-cell">
                  <Tag
                    v-for="v in record.variable_list"
                    :key="v"
                    color="blue"
                    class="variable-tag"
                  >
                    {{ truncateVar(v) }}
                  </Tag>
                </div>
              </Tooltip>
            </template>
            <span v-else class="text-gray-400">-</span>
          </template>
          <!-- 策略绑定列 -->
          <template v-else-if="column.key === 'strategy_binding'">
            <Tag v-if="record.strategy_id" color="success"> ✓ 已映射 </Tag>
            <Tag v-else color="default"> 未映射 </Tag>
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
          <template v-else-if="column.key === 'update_time'">
            {{ formatTime(record.update_time) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <Space>
              <Button
                type="link"
                size="small"
                :disabled="(record as Plugin).publish_status === 'PUBLISHED'"
                @click="handleEdit(record as Plugin)"
              >
                ✏️ 编辑
              </Button>
              <Button
                type="link"
                size="small"
                @click="handleOpenVariableMapping(record as Plugin)"
              >
                🔗 映射
              </Button>
              <Button
                type="link"
                size="small"
                @click="handleCopy(record as Plugin)"
              >
                📋 复制
              </Button>
              <Button
                type="link"
                size="small"
                @click="handleShowVersions(record as Plugin)"
              >
                📜 历史
              </Button>
              <Button
                type="link"
                danger
                size="small"
                :disabled="(record as Plugin).publish_status === 'PUBLISHED'"
                @click="handleDelete(record as Plugin)"
              >
                🗑️ 删除
              </Button>
            </Space>
          </template>
        </template>
      </Table>
    </Card>

    <!-- Plugin 编辑弹窗 -->
    <Modal
      v-model:open="modalVisible"
      :width="750"
      :confirm-loading="isSubmitting"
      :ok-button-props="{ disabled: !canSubmit }"
      @ok="handleSubmit"
      @cancel="modalVisible = false"
    >
      <template #title>
        <Space>
          <span>{{ editingPlugin ? '编辑 Plugin' : '新增 Plugin' }}</span>
          <Tag v-if="autoSaveStatus === 'saving'" color="processing">
            💾 保存中...
          </Tag>
          <Tag v-else-if="autoSaveStatus === 'saved'" color="success">
            ✅ 已自动保存
          </Tag>
          <Tag v-else-if="autoSaveStatus === 'error'" color="error">
            ❌ 保存失败
          </Tag>
          <Tag v-else-if="hasDraft" color="warning">📝 有草稿</Tag>
        </Space>
      </template>
      <Form :model="formState" layout="vertical">
        <!-- 新建模式：类型 + 编码后缀 → 自动生成 plugin_code -->
        <div v-if="!editingPlugin" class="grid grid-cols-2 gap-4">
          <FormItem
            label="类型"
            name="plugin_type"
            :rules="[{ required: true, message: '请选择插件类型' }]"
          >
            <Select
              v-model:value="formState.plugin_type"
              placeholder="请先选择类型"
              show-search
              :filter-option="true"
              :get-popup-container="(trigger) => trigger.parentElement"
            >
              <SelectOption
                v-for="opt in pluginTypeOptions"
                :key="opt.value"
                :value="opt.value"
              >
                {{ opt.label }}
              </SelectOption>
            </Select>
          </FormItem>
          <FormItem
            label="名称"
            name="plugin_name"
            :rules="[{ required: true, message: '请输入名称' }]"
          >
            <Input
              v-model:value="formState.plugin_name"
              placeholder="如: 人设场景"
            />
          </FormItem>
        </div>

        <!-- 编辑模式：只读显示类型 -->
        <div v-if="editingPlugin" class="grid grid-cols-2 gap-4">
          <FormItem label="类型">
            <Select
              v-model:value="formState.plugin_type"
              disabled
              :get-popup-container="(trigger) => trigger.parentElement"
            >
              <SelectOption
                v-for="opt in pluginTypeOptions"
                :key="opt.value"
                :value="opt.value"
              >
                {{ opt.label }}
              </SelectOption>
            </Select>
          </FormItem>
          <FormItem
            label="名称"
            name="plugin_name"
            :rules="[{ required: true, message: '请输入名称' }]"
          >
            <Input
              v-model:value="formState.plugin_name"
              placeholder="如: 人设场景"
            />
          </FormItem>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <FormItem label="备注" name="remark">
            <Textarea
              v-model:value="formState.remark"
              :rows="1"
              placeholder="Plugin 描述/备注"
            />
          </FormItem>
          <FormItem label="状态" name="enabled">
            <Switch
              v-model:checked="formState.enabled"
              checked-children="启用"
              un-checked-children="禁用"
            />
          </FormItem>
        </div>

        <!-- ✅ 高级选项：Plugin 编码配置 -->
        <Collapse
          v-if="!editingPlugin"
          v-model:active-key="collapseActiveKey"
          style="margin-top: 16px; margin-bottom: 16px"
        >
          <CollapsePanel key="1" header="🔧 高级选项">
            <FormItem
              label="Plugin 编码"
              name="plugin_code"
              :rules="[{ validator: pluginCodeValidator, trigger: 'change' }]"
            >
              <Input
                v-model:value="formState.plugin_code"
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

        <FormItem label="模板内容" name="context_template">
          <MonacoEditor
            v-model:model-value="formState.context_template"
            language="plaintext"
            height="320px"
            :placeholder="templatePlaceholder"
          />
        </FormItem>

        <FormItem label="变量列表（自动提取）" name="variable_list">
          <div class="variable-list-box">
            <Space wrap v-if="formState.variable_list.length > 0">
              <Tag v-for="v in formState.variable_list" :key="v" color="blue">
                {{ v }}
              </Tag>
            </Space>
            <span v-else class="text-gray-400">
              在模板中使用 &#123;&#123;变量名&#125;&#125; 格式，变量将自动提取
            </span>
          </div>
          <div class="mt-2">
            <Space>
              <Input
                v-model:value="newVariable"
                placeholder="手动添加变量"
                style="width: 180px"
                size="small"
                @press-enter="addVariable"
              />
              <EnhancedButton type="primary" size="small" @click="addVariable">
                添加
              </EnhancedButton>
            </Space>
          </div>
        </FormItem>
      </Form>
    </Modal>

    <!-- 版本历史抽屉 -->
    <Drawer
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

    <!-- v2 新增：变量映射配置弹窗 -->
    <VariableMappingModal
      v-if="selectedPluginForMapping"
      v-model:open="variableMappingModalOpen"
      :plugin="selectedPluginForMapping"
      @saved="handleVariableMappingSaved"
    />

    <!-- 版本详情抽屉 -->
    <Drawer
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
            <code>{{ viewingVersion.content.plugin_code }}</code>
          </DescriptionsItem>
          <DescriptionsItem label="名称">
            {{ viewingVersion.content.plugin_name }}
          </DescriptionsItem>
          <DescriptionsItem label="类型">
            <Tag
              v-if="viewingVersion.content.plugin_type"
              :color="
                pluginTypeMap[viewingVersion.content.plugin_type]?.color ||
                'default'
              "
            >
              {{
                pluginTypeMap[viewingVersion.content.plugin_type]?.label ||
                viewingVersion.content.plugin_type
              }}
            </Tag>
            <span v-else>-</span>
          </DescriptionsItem>
          <DescriptionsItem label="状态">
            <Tag :color="viewingVersion.content.enabled ? 'green' : 'red'">
              {{ viewingVersion.content.enabled ? '启用' : '禁用' }}
            </Tag>
          </DescriptionsItem>
          <DescriptionsItem label="备注">
            {{ viewingVersion.content.remark || '-' }}
          </DescriptionsItem>
        </Descriptions>

        <Card title="变量列表" size="small" class="mt-4">
          <Space wrap v-if="viewingVersion.content.variable_list?.length">
            <Tag
              v-for="v in viewingVersion.content.variable_list"
              :key="v"
              color="blue"
            >
              {{ v }}
            </Tag>
          </Space>
          <span v-else class="text-gray-400">无变量</span>
        </Card>

        <Card title="模板内容" size="small" class="mt-4">
          <pre class="config-json">{{
            viewingVersion.content.context_template || '-'
          }}</pre>
        </Card>

        <!-- 被引用情况 -->
        <Card title="📊 被引用情况" size="small" class="mt-4">
          <Spin :spinning="relatedExpertsLoading">
            <div v-if="relatedExperts.length === 0" class="py-4 text-center">
              <Empty description="暂无专家配置引用此插件" />
            </div>
            <div v-else>
              <Alert
                type="warning"
                show-icon
                :message="`该插件被 ${relatedExpertsTotal} 个专家配置引用`"
                description="修改此插件可能影响以下专家的运行，建议在调试面板验证修改"
                style="margin-bottom: 16px"
              />

              <Table
                :columns="relatedExpertsColumns"
                :data-source="relatedExperts"
                :pagination="false"
                size="small"
                :scroll="{ x: 800 }"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'expert_type'">
                    <Tag color="blue">{{ record.expert_type }}</Tag>
                  </template>
                  <template v-else-if="column.key === 'enabled'">
                    <Tag :color="record.enabled ? 'green' : 'red'">
                      {{ record.enabled ? '启用' : '禁用' }}
                    </Tag>
                  </template>
                  <template v-else-if="column.key === 'update_time'">
                    {{ formatTime(record.update_time) }}
                  </template>
                  <template v-else-if="column.key === 'actions'">
                    <Space>
                      <Button
                        type="link"
                        size="small"
                        @click="goToExpertConfig(record.expert_config_code)"
                      >
                        查看详情
                      </Button>
                      <Button
                        type="link"
                        size="small"
                        @click="goToExpertDebug(record.expert_config_code)"
                      >
                        调试
                      </Button>
                    </Space>
                  </template>
                </template>
              </Table>
            </div>
          </Spin>
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
@keyframes float {
  0%,
  100% {
    transform: translateY(0);
  }

  50% {
    transform: translateY(-4px);
  }
}

@media (max-width: 1200px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
}

.p-4 {
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

/* 统计卡片网格 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

/* 统计卡片样式 */
.stat-card {
  position: relative;
  overflow: hidden;
  cursor: pointer;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  transition: all 0.3s ease;
}

.stat-card:hover {
  border-color: hsl(var(--primary));
  box-shadow: 0 8px 24px rgb(0 0 0 / 12%);
  transform: translateY(-4px);
}

.stat-card::before {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 3px;
  content: '';
  background: linear-gradient(
    90deg,
    hsl(var(--primary)),
    hsl(var(--primary) / 50%)
  );
  opacity: 0;
  transition: opacity 0.3s ease;
}

.stat-card:hover::before {
  opacity: 1;
}

.stat-content {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 20px;
}

.stat-icon {
  flex-shrink: 0;
  font-size: 36px;
  line-height: 1;
  filter: drop-shadow(0 2px 4px rgb(0 0 0 / 10%));
  animation: float 3s ease-in-out infinite;
}

.stat-info {
  flex: 1;
  min-width: 0;
}

.stat-label {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
  color: hsl(var(--foreground));
}

.stat-value :deep(.count-to) {
  font-variant-numeric: tabular-nums;
}

/* 主卡片上边距 */
.main-card {
  margin-top: 0;
}

.text-green-500 {
  color: #10b981;
}

.text-blue-500 {
  color: #3b82f6;
}

.text-purple-500 {
  color: #a855f7;
}

/* 亮色主题适配 */
:deep(.light) .stat-card {
  background: #fff;
  box-shadow: 0 1px 3px rgb(0 0 0 / 5%);
}

:deep(.light) .stat-card:hover {
  box-shadow: 0 8px 24px rgb(0 0 0 / 12%);
}

/* 暗色主题适配 */
:deep(.dark) .stat-card {
  background: hsl(var(--card));
  border-color: hsl(var(--border));
}

:deep(.dark) .stat-card:hover {
  box-shadow: 0 8px 24px rgb(0 0 0 / 30%);
}

.mb-2 {
  margin-bottom: 8px;
}

.mt-2 {
  margin-top: 8px;
}

.grid {
  display: grid;
}

.grid-cols-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.gap-4 {
  gap: 16px;
}

/* 让跨列的表单项真正占两列 */
.col-span-2 {
  grid-column: span 2 / span 2;
}

.template-textarea {
  font-family: 'Fira Code', Consolas, Monaco, monospace;
  font-size: 13px;
  line-height: 1.5;
}

.variable-list-box {
  min-height: 36px;
  padding: 8px 12px;
  background: rgb(0 0 0 / 2%);
  border-radius: 6px;
}

:deep(.dark) .variable-list-box {
  background: rgb(255 255 255 / 4%);
}

.var-tooltip {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  max-width: 300px;
}

/* 变量列容器 - 防止溢出 */
.variable-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  max-width: 100%;
  max-height: 48px; /* 限制高度，约两行 */
  overflow: hidden;
}

.variable-tag {
  flex-shrink: 0;
  max-width: 70px;
  height: 20px !important;
  padding: 0 4px !important;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  line-height: 18px !important;
  white-space: nowrap;
}

/* Plugin 详情 Tooltip 样式 */
.plugin-code-cell {
  color: #1890ff;
  cursor: pointer;
  transition: color 0.2s;
}

.plugin-code-cell:hover {
  color: #40a9ff;
  text-decoration: underline;
}

:global(.plugin-detail-tooltip) {
  max-width: 550px;
  padding: 4px;
}

:global(.tooltip-header) {
  display: flex;
  gap: 8px;
  align-items: center;
  padding-bottom: 10px;
  margin-bottom: 10px;
  border-bottom: 1px solid rgb(255 255 255 / 10%);
}

:global(.tooltip-icon) {
  font-size: 18px;
}

:global(.tooltip-title) {
  flex: 1;
  font-size: 15px;
  font-weight: 600;
  color: #fff;
}

:global(.tooltip-status) {
  margin-left: auto;
}

:global(.tooltip-section) {
  margin-bottom: 12px;
}

:global(.tooltip-section-title) {
  display: flex;
  gap: 4px;
  align-items: center;
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 500;
  color: rgb(255 255 255 / 85%);
}

:global(.tooltip-row) {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-bottom: 6px;
  font-size: 13px;
}

:global(.tooltip-label) {
  flex-shrink: 0;
  min-width: 40px;
  color: rgb(255 255 255 / 65%);
}

:global(.tooltip-value) {
  color: rgb(255 255 255 / 85%);
  word-break: break-all;
}

:global(.tooltip-code) {
  padding: 2px 6px;
  font-family: 'Fira Code', Consolas, monospace;
  font-size: 12px;
  color: #69c0ff;
  background: rgb(0 0 0 / 20%);
  border-radius: 4px;
}

:global(.tooltip-empty) {
  font-style: italic;
  color: rgb(255 255 255 / 45%);
}

:global(.tooltip-vars) {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

:global(.tooltip-template) {
  max-height: 200px;
  padding: 8px 10px;
  margin: 0;
  overflow-y: auto;
  font-family: 'Fira Code', Consolas, monospace;
  font-size: 11px;
  line-height: 1.4;
  color: rgb(255 255 255 / 85%);
  word-break: break-all;
  white-space: pre-wrap;
  background: rgb(0 0 0 / 25%);
  border-radius: 6px;
}

:global(.tooltip-json-viewer) {
  max-height: 250px;
  overflow-y: auto;
  background: rgb(0 0 0 / 25%);
  border-radius: 6px;
}

/* JSON 语法高亮颜色 */
:global(.tooltip-template .json-key) {
  color: #69c0ff;
}

:global(.tooltip-template .json-string) {
  color: #95de64;
}

:global(.tooltip-template .json-number) {
  color: #ffc069;
}

:global(.tooltip-template .json-boolean) {
  color: #ff85c0;
}

:global(.tooltip-template .json-null) {
  color: #ff7875;
}

:global(.tooltip-footer) {
  padding-top: 8px;
  margin-top: 8px;
  font-size: 11px;
  color: rgb(255 255 255 / 45%);
  text-align: right;
  border-top: 1px solid rgb(255 255 255 / 10%);
}

.tooltip-tag {
  margin: 2px !important;
}

/* 版本历史相关样式 - 使用 CSS 变量支持主题切换 */
.version-loading,
.version-empty {
  padding: 40px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.version-timeline {
  padding: 16px;
}

.version-item {
  padding-left: 8px;
}

.version-header {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 4px;
}

.version-time {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.version-desc {
  margin-bottom: 4px;
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

.config-json {
  max-height: 400px;
  padding: 16px;
  margin: 0;
  overflow-y: auto;
  font-family: 'Fira Code', Consolas, Monaco, monospace;
  font-size: 13px;
  line-height: 1.5;
  color: hsl(var(--foreground));
  overflow-wrap: break-word;
  white-space: pre-wrap;
  background: hsl(var(--muted));
  border-radius: 6px;
}

.mt-4 {
  margin-top: 16px;
}
</style>

<style>
/* Plugin 版本详情抽屉 - 全局样式支持主题切换 */
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

/* 被引用情况卡片样式 */
.py-4 {
  padding-top: 16px;
  padding-bottom: 16px;
}

.text-center {
  text-align: center;
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
</style>
