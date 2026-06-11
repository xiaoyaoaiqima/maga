<script setup lang="ts">
// @ts-nocheck
import type { ActivityApi, TenantApi } from '#/api/core/business';
import type { PublishApi } from '#/api/core/publish';

import { h, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';

import { ExclamationCircleOutlined, PlusOutlined } from '@ant-design/icons-vue';
import {
  Button,
  Card,
  Divider,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import {
  createActivityApi,
  deleteActivityApi,
  getActivityListApi,
  getAgentSimpleListApi,
  getTenantSimpleListApi,
  updateActivityApi,
  updateActivityStatusApi,
} from '#/api/core/business';
import {
  checkCanModifyApi,
  previewPublishActivityApi,
  publishActivityApi,
  unpublishActivityApi,
} from '#/api/core/publish';

const route = useRoute();

const loading = ref(false);
const dataSource = ref<ActivityApi.Activity[]>([]);
const total = ref(0);
const searchKeyword = ref('');
const statusFilter = ref<string | undefined>(undefined);
const tenantFilter = ref<number | undefined>(undefined);
const tenantOptions = ref<TenantApi.SimpleItem[]>([]);
const agentOptions = ref<Array<{ label: string; value: string }>>([]);
const pagination = ref({
  current: 1,
  pageSize: 10,
  showSizeChanger: true,
  showTotal: (t: number) => `共 ${t} 条`,
});

// 状态配置
const statusConfig: Record<
  ActivityApi.ActivityStatus,
  { color: string; label: string }
> = {
  DRAFT: { label: '草稿', color: 'default' },
  PENDING: { label: '待开始', color: 'processing' },
  RUNNING: { label: '进行中', color: 'success' },
  PAUSED: { label: '已暂停', color: 'warning' },
  COMPLETED: { label: '已完成', color: 'blue' },
  CANCELLED: { label: '已取消', color: 'error' },
};

const statusOptions = [
  { label: '草稿', value: 'DRAFT' },
  { label: '待开始', value: 'PENDING' },
  { label: '进行中', value: 'RUNNING' },
  { label: '已暂停', value: 'PAUSED' },
  { label: '已完成', value: 'COMPLETED' },
  { label: '已取消', value: 'CANCELLED' },
];

const channelOptions = [
  { label: '小红书', value: 'xiaohongshu' },
  { label: '抖音', value: 'douyin' },
  { label: '微信', value: 'wechat' },
  { label: '微博', value: 'weibo' },
  { label: '其他', value: 'other' },
];

// 上线状态配置
const publishStatusConfig: Record<
  ActivityApi.PublishStatus,
  { color: string; label: string }
> = {
  DRAFT: { label: '草稿', color: 'default' },
  PUBLISHED: { label: '已上线', color: 'success' },
};

const columns = [
  {
    title: '活动编码',
    dataIndex: 'activity_code',
    key: 'activity_code',
    width: 150,
  },
  {
    title: '活动名称',
    dataIndex: 'activity_name',
    key: 'activity_name',
    width: 200,
  },
  {
    title: '所属租户',
    dataIndex: 'tenant_name',
    key: 'tenant_name',
    width: 120,
  },
  { title: '渠道', dataIndex: 'channel', key: 'channel', width: 100 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 100 },
  {
    title: '上线状态',
    dataIndex: 'publish_status',
    key: 'publish_status',
    width: 100,
  },
  {
    title: '创建时间',
    dataIndex: 'create_time',
    key: 'create_time',
    width: 170,
  },
  { title: '操作', key: 'action', width: 280, fixed: 'right' as const },
];

// 问题选项表格列
const optionColumns = [
  {
    title: '小程序展示可替换标签',
    dataIndex: 'display_label',
    key: 'display_label',
    width: 200,
  },
  {
    title: 'AIGC对应标签',
    dataIndex: 'aigc_tag',
    key: 'aigc_tag',
    width: 140,
  },
  {
    title: '标签对应权重',
    dataIndex: 'weight',
    key: 'weight',
    width: 100,
  },
  {
    title: '',
    key: 'action',
    width: 100,
  },
];

async function fetchTenants() {
  try {
    tenantOptions.value = await getTenantSimpleListApi();
  } catch {
    console.error('获取租户列表失败');
  }
}

async function fetchData() {
  loading.value = true;
  try {
    const params: Record<string, any> = {
      skip: (pagination.value.current - 1) * pagination.value.pageSize,
      limit: pagination.value.pageSize,
    };
    if (statusFilter.value) params.status = statusFilter.value;
    if (tenantFilter.value) params.tenant_id = tenantFilter.value;
    if (searchKeyword.value) params.keyword = searchKeyword.value;

    const response = await getActivityListApi(params);
    dataSource.value = response.items || [];
    total.value = response.total || 0;
  } catch {
    message.error('获取活动列表失败');
  } finally {
    loading.value = false;
  }
}

function handleTableChange(pag: any) {
  pagination.value.current = pag.current || 1;
  pagination.value.pageSize = pag.pageSize || 10;
  fetchData();
}

function handleSearch() {
  pagination.value.current = 1;
  fetchData();
}

function handleReset() {
  searchKeyword.value = '';
  statusFilter.value = undefined;
  tenantFilter.value = undefined;
  pagination.value.current = 1;
  fetchData();
}

// 表单弹窗
const modalVisible = ref(false);
const modalLoading = ref(false);
const modalTitle = ref('创建活动');
const editingId = ref<null | number>(null);

// 表单状态（支持多选Agent和问题配置）
interface FormState {
  activity_code: string;
  activity_name: string;
  tenant_id: number | undefined;
  agent_code_list: string[];
  channel: string;
  target_audience: string;
  budget: number | undefined;
  status: ActivityApi.ActivityStatus;
  remark: string;
  questions: ActivityApi.Question[];
}

const formState = ref<FormState>({
  activity_code: '',
  activity_name: '',
  tenant_id: undefined,
  agent_code_list: [],
  channel: '',
  target_audience: '',
  budget: undefined,
  status: 'DRAFT',
  remark: '',
  questions: [],
});

// ==================== 问题配置相关 ====================
const questionModalVisible = ref(false);
const editingQuestionIndex = ref<null | number>(null);
const questionForm = ref<ActivityApi.Question>({
  question_text: '',
  min_select: 1,
  max_select: 1,
  sort_order: 0,
  options: [],
});

// 问题模板（预设的标准问题）
const questionTemplates = [
  {
    question_text: '生活里的你,更接近哪种类型?',
    options: [
      {
        display_label: '经常在路上,天天赶路,一路飞奔',
        aigc_tag: '通勤战士',
        weight: 0.5,
      },
      {
        display_label: '整点小美好,讲究生活,生活仪式感',
        aigc_tag: '生活美学家',
        weight: 0.5,
      },
      {
        display_label: '家里一把手,家庭管家,全能家务王',
        aigc_tag: '家庭CEO',
        weight: 0.5,
      },
      {
        display_label: '一心多用型,身兼数职,多线程妈妈',
        aigc_tag: '斜杠妈妈',
        weight: 0.5,
      },
      {
        display_label: '职场打工人,回归职场,复出上班族',
        aigc_tag: '职场回归妈妈',
        weight: 0.5,
      },
      {
        display_label: '节奏自由派,随性自由派,节奏松弛派',
        aigc_tag: '自由职业妈妈',
        weight: 0.5,
      },
    ],
  },
  {
    question_text: '你的表达风格更偏哪一派?',
    options: [
      {
        display_label: '朋友聊天,掏心窝子,知心朋友型',
        aigc_tag: '知心朋友型',
        weight: 0.2,
      },
      {
        display_label: '激情安利型,热情推荐,分享欲爆棚',
        aigc_tag: '激情安利型',
        weight: 0.2,
      },
      {
        display_label: '爱抛问题,喜欢互动,发问小天才',
        aigc_tag: '互动解谜型',
        weight: 0.2,
      },
      {
        display_label: '碎碎念叨,贴心唠叨,唠嗑碎碎念',
        aigc_tag: '亲切唠叨型',
        weight: 0.2,
      },
      {
        display_label: '直来直去,不绕弯子,有话直说型',
        aigc_tag: '言简意赅型',
        weight: 0.2,
      },
      {
        display_label: '知识密集,百科小达人,科普小能手',
        aigc_tag: '冷知识科普型',
        weight: 0.2,
      },
    ],
  },
  {
    question_text: '你印象最深的带娃场景是?',
    options: [
      {
        display_label: '宅家陪娃,窝家带娃,宅家陪玩',
        aigc_tag: '居家',
        weight: 0.9,
      },
      {
        display_label: '去公园玩,公园遛娃,公园放风',
        aigc_tag: '公园',
        weight: 0.9,
      },
      {
        display_label: '逛超市,超市采购,超市遛娃',
        aigc_tag: '超市',
        weight: 0.7,
      },
      {
        display_label: '逛母婴店,逛母婴店,逛母婴店',
        aigc_tag: '母婴店',
        weight: 0.7,
      },
      {
        display_label: '做体检,宝宝体检,带娃体检',
        aigc_tag: '体检',
        weight: 0.7,
      },
      {
        display_label: '出门玩耍,带娃出门,周末溜达',
        aigc_tag: '外出',
        weight: 0.9,
      },
    ],
  },
  {
    question_text: '你遇到过哪些带娃的"小困扰"?',
    options: [
      { display_label: '宝宝挑食,不爱吃饭', aigc_tag: '挑食', weight: 0.8 },
      { display_label: '睡眠不好,难哄睡', aigc_tag: '睡眠', weight: 0.8 },
      { display_label: '容易生病,体质弱', aigc_tag: '体质', weight: 0.8 },
      { display_label: '注意力不集中,坐不住', aigc_tag: '专注力', weight: 0.7 },
      { display_label: '情绪不稳定,爱哭闹', aigc_tag: '情绪', weight: 0.7 },
    ],
  },
];

// 获取选择类型文本
function getSelectTypeText(question: ActivityApi.Question) {
  const min = question.min_select ?? 1;
  const max = question.max_select ?? 1;
  if (min === 1 && max === 1) return '单选';
  if (max === null || max === undefined || max > 1) return '多选';
  return '单选';
}

// 打开添加问题弹窗
function openAddQuestionModal() {
  editingQuestionIndex.value = null;
  questionForm.value = {
    question_text: '',
    min_select: 1,
    max_select: 1,
    sort_order: formState.value.questions.length,
    options: [],
  };
  questionModalVisible.value = true;
}

// 打开编辑问题弹窗
function openEditQuestionModal(index: number) {
  editingQuestionIndex.value = index;
  const question = formState.value.questions[index];
  questionForm.value = {
    ...question,
    options: question.options?.map((o) => ({ ...o })) || [],
  };
  questionModalVisible.value = true;
}

// 删除问题
function handleDeleteQuestion(index: number) {
  formState.value.questions.splice(index, 1);
  // 重新排序
  formState.value.questions.forEach((q, i) => {
    q.sort_order = i;
  });
}

// 导入标准问题模板
function handleImportTemplate() {
  Modal.confirm({
    title: '选择问题模板',
    icon: null,
    width: 600,
    content: h(
      'div',
      { style: { maxHeight: '400px', overflowY: 'auto' } },
      questionTemplates.map((template, index) =>
        h(
          'div',
          {
            key: index,
            style: {
              padding: '12px',
              marginBottom: '8px',
              border: '1px solid #d9d9d9',
              borderRadius: '6px',
              cursor: 'pointer',
            },
            onClick: () => {
              questionForm.value = {
                question_text: template.question_text,
                min_select: 1,
                max_select: 1,
                sort_order: formState.value.questions.length,
                options: template.options.map((o, i) => ({
                  display_label: o.display_label,
                  aigc_tag: o.aigc_tag,
                  weight: o.weight,
                  sort_order: i,
                })),
              };
              Modal.destroyAll();
            },
          },
          [
            h(
              'div',
              { style: { fontWeight: 600, marginBottom: '8px' } },
              template.question_text,
            ),
            h(
              'div',
              { style: { display: 'flex', flexWrap: 'wrap', gap: '4px' } },
              template.options
                .slice(0, 3)
                .map((o) =>
                  h(Tag, { color: 'blue', key: o.aigc_tag }, () => o.aigc_tag),
                ),
            ),
            template.options.length > 3 &&
              h(
                'span',
                { style: { color: '#999', marginLeft: '4px' } },
                `+${template.options.length - 3} 更多`,
              ),
          ],
        ),
      ),
    ),
    okText: '取消',
    okType: 'default',
    cancelButtonProps: { style: { display: 'none' } },
  });
}

// 添加选项
function handleAddOption() {
  questionForm.value.options.push({
    display_label: '',
    aigc_tag: '',
    weight: 0.5,
    sort_order: questionForm.value.options.length,
  });
}

// 删除选项
function handleDeleteOption(index: number) {
  questionForm.value.options.splice(index, 1);
  questionForm.value.options.forEach((o, i) => {
    o.sort_order = i;
  });
}

// 切换选择类型
function handleSelectTypeChange(type: 'multiple' | 'single') {
  if (type === 'single') {
    questionForm.value.min_select = 1;
    questionForm.value.max_select = 1;
  } else {
    questionForm.value.min_select = 1;
    questionForm.value.max_select = null;
  }
}

// 保存问题
function handleSaveQuestion() {
  if (!questionForm.value.question_text.trim()) {
    message.warning('请输入问题内容');
    return;
  }
  if (questionForm.value.options.length === 0) {
    message.warning('请至少添加一个选项');
    return;
  }
  // 验证选项
  for (const opt of questionForm.value.options) {
    if (!opt.display_label.trim() || !opt.aigc_tag.trim()) {
      message.warning('请填写完整的选项信息');
      return;
    }
  }

  if (editingQuestionIndex.value === null) {
    // 新增模式
    formState.value.questions.push({ ...questionForm.value });
  } else {
    // 编辑模式
    formState.value.questions[editingQuestionIndex.value] = {
      ...questionForm.value,
    };
  }
  questionModalVisible.value = false;
}

async function fetchAgentsByTenant(tenantId: number) {
  try {
    const agents = await getAgentSimpleListApi(tenantId);
    agentOptions.value = agents.map((a) => ({
      label: `${a.agent_name} (${a.agent_code})`,
      value: a.agent_code,
    }));
  } catch {
    agentOptions.value = [];
  }
}

function handleModalTenantChange(val: number | undefined) {
  formState.value.agent_code_list = [];
  if (val) {
    fetchAgentsByTenant(val);
  } else {
    agentOptions.value = [];
  }
}

function openCreateModal() {
  editingId.value = null;
  modalTitle.value = '创建活动';
  formState.value = {
    activity_code: '',
    activity_name: '',
    tenant_id: undefined,
    agent_code_list: [],
    channel: '',
    target_audience: '',
    budget: undefined,
    status: 'DRAFT',
    remark: '',
    questions: [],
  };
  agentOptions.value = [];
  modalVisible.value = true;
}

function openEditModal(record: ActivityApi.Activity) {
  editingId.value = record.id;
  modalTitle.value = '编辑活动';
  formState.value = {
    activity_code: record.activity_code,
    activity_name: record.activity_name,
    tenant_id: record.tenant_id,
    agent_code_list: record.agent_code_list || [],
    channel: record.channel || '',
    target_audience: record.target_audience || '',
    budget: record.budget || undefined,
    status: record.status,
    remark: record.remark || '',
    questions:
      record.questions?.map((q) => ({
        ...q,
        options: q.options?.map((o) => ({ ...o })) || [],
      })) || [],
  };
  if (record.tenant_id) {
    fetchAgentsByTenant(record.tenant_id);
  }
  modalVisible.value = true;
}

async function handleSubmit() {
  if (
    !formState.value.activity_code ||
    !formState.value.activity_name ||
    !formState.value.tenant_id
  ) {
    message.warning('请填写必填字段');
    return;
  }

  // 验证问题数量（需要配置4个问题）
  if (
    formState.value.questions.length > 0 &&
    formState.value.questions.length < 4
  ) {
    message.warning('活动问题与标签需要配置4个问题哦~');
    return;
  }

  modalLoading.value = true;
  try {
    // 构建提交数据
    const submitData: ActivityApi.CreateParams = {
      activity_code: formState.value.activity_code,
      activity_name: formState.value.activity_name,
      tenant_id: formState.value.tenant_id,
      agent_code_list:
        formState.value.agent_code_list.length > 0
          ? formState.value.agent_code_list
          : undefined,
      channel: formState.value.channel || undefined,
      target_audience: formState.value.target_audience || undefined,
      budget: formState.value.budget,
      status: formState.value.status,
      remark: formState.value.remark || undefined,
      questions:
        formState.value.questions.length > 0
          ? formState.value.questions
          : undefined,
    };

    if (editingId.value) {
      await updateActivityApi(editingId.value, submitData);
      message.success('更新成功');
    } else {
      await createActivityApi(submitData);
      message.success('创建成功');
    }
    modalVisible.value = false;
    fetchData();
  } catch {
    message.error(editingId.value ? '更新失败' : '创建失败');
  } finally {
    modalLoading.value = false;
  }
}

async function handleStatusChange(
  record: ActivityApi.Activity,
  newStatus: ActivityApi.ActivityStatus,
) {
  try {
    await updateActivityStatusApi(record.id, newStatus);
    message.success('状态更新成功');
    fetchData();
  } catch {
    message.error('状态更新失败');
  }
}

// 编辑前检查
async function handleEditCheck(record: ActivityApi.Activity) {
  // 已上线直接拒绝
  if (record.publish_status === 'PUBLISHED') {
    message.warning('活动已上线，不可编辑。如需修改，请先下线。');
    return;
  }

  try {
    const result = await checkCanModifyApi('Activity', record.id);
    if (result.action === 'reject') {
      message.warning(result.reason);
      return;
    }

    if (result.action === 'confirm' && result.references?.length) {
      Modal.confirm({
        title: '确认编辑',
        icon: () => h(ExclamationCircleOutlined),
        content: `该活动被 ${result.references.length} 个实体引用，确定要编辑吗？`,
        okText: '确认编辑',
        cancelText: '取消',
        onOk: () => openEditModal(record),
      });
      return;
    }

    openEditModal(record);
  } catch {
    // 检查失败时允许继续操作
    openEditModal(record);
  }
}

// 删除前检查
async function handleDeleteCheck(record: ActivityApi.Activity) {
  // 已上线直接拒绝
  if (record.publish_status === 'PUBLISHED') {
    message.warning('活动已上线，不可删除。如需删除，请先下线。');
    return;
  }

  try {
    const result = await checkCanModifyApi('Activity', record.id);
    if (result.action === 'reject') {
      message.warning(result.reason);
      return;
    }

    if (result.action === 'confirm' && result.references?.length) {
      Modal.confirm({
        title: '确认删除',
        icon: () => h(ExclamationCircleOutlined),
        content: `该活动被 ${result.references.length} 个实体引用（如 Job），确定要删除吗？`,
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
      content: '确定要删除此活动吗？',
      okText: '确定',
      okType: 'danger',
      cancelText: '取消',
      onOk: () => handleDelete(record),
    });
  } catch {
    // 检查失败时使用普通确认
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除此活动吗？',
      okText: '确定',
      okType: 'danger',
      cancelText: '取消',
      onOk: () => handleDelete(record),
    });
  }
}

async function handleDelete(record: ActivityApi.Activity) {
  try {
    await deleteActivityApi(record.id);
    message.success('删除成功');
    fetchData();
  } catch {
    message.error('删除失败');
  }
}

// 上线操作
const publishLoading = ref(false);
const publishPreviewVisible = ref(false);
const publishPreviewData = ref<null | PublishApi.PreviewResult>(null);
const publishTargetId = ref<null | number>(null);

async function handlePublishPreview(record: ActivityApi.Activity) {
  if (!record.agent_code_list || record.agent_code_list.length === 0) {
    message.warning('请先为活动配置 Agent');
    return;
  }

  publishLoading.value = true;
  try {
    const result = await previewPublishActivityApi(record.id);
    publishPreviewData.value = result;
    publishTargetId.value = record.id;
    publishPreviewVisible.value = true;
  } catch {
    message.error('获取上线预检查信息失败');
  } finally {
    publishLoading.value = false;
  }
}

async function handlePublishConfirm() {
  if (!publishTargetId.value) return;

  publishLoading.value = true;
  try {
    const result = await publishActivityApi(publishTargetId.value, {
      operator: 'admin', // TODO: 获取当前用户
    });

    if (result.success) {
      message.success('上线成功');
      publishPreviewVisible.value = false;
      fetchData();
    } else {
      message.error(result.message || '上线失败');
    }
  } catch {
    message.error('上线失败');
  } finally {
    publishLoading.value = false;
  }
}

async function handleUnpublish(record: ActivityApi.Activity) {
  Modal.confirm({
    title: '确认下线',
    content: '下线后可以编辑活动，但不影响已关联的配置。确定要下线吗？',
    okText: '确认下线',
    cancelText: '取消',
    onOk: async () => {
      try {
        const result = await unpublishActivityApi(record.id, {
          operator: 'admin',
        });
        if (result.success) {
          message.success('下线成功');
          fetchData();
        } else {
          message.error(result.message || '下线失败');
        }
      } catch {
        message.error('下线失败');
      }
    },
  });
}

function getChannelLabel(value: null | string) {
  const opt = channelOptions.find((o) => o.value === value);
  return opt?.label || value || '-';
}

onMounted(() => {
  fetchTenants();
  fetchData();
});
</script>

<template>
  <div class="activity-page">
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
          {{ route.meta.title || '活动管理' }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">名称/编码</span>
          <Input
            v-model:value="searchKeyword"
            placeholder="搜索活动名称/编码"
            style="width: 180px"
            allow-clear
            @press-enter="handleSearch"
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">租户</span>
          <Select
            v-model:value="tenantFilter"
            placeholder="选择租户"
            style="width: 140px"
            allow-clear
            show-search
            :filter-option="true"
            :options="
              tenantOptions.map((t) => ({
                label: `${t.tenant_name} (${t.tenant_code})`,
                value: t.id,
              }))
            "
            @change="handleSearch"
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">状态</span>
          <Select
            v-model:value="statusFilter"
            :options="statusOptions"
            placeholder="状态筛选"
            style="width: 120px"
            allow-clear
            show-search
            :filter-option="true"
            @change="handleSearch"
          />
        </div>
        <div class="filter-actions">
          <Button @click="handleReset">重置</Button>
          <Button type="primary" @click="openCreateModal">➕ 创建活动</Button>
        </div>
      </div>
    </div>

    <Card :bordered="false">
      <Table
        :columns="columns"
        :data-source="dataSource"
        :loading="loading"
        :pagination="{ ...pagination, total }"
        :scroll="{ x: 1100 }"
        row-key="id"
        size="middle"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record: rawRecord }">
          <template v-if="column.key === 'tenant_name'">
            <span v-if="(rawRecord as ActivityApi.Activity).tenant_name">
              {{ (rawRecord as ActivityApi.Activity).tenant_name }}
              <span
                v-if="(rawRecord as ActivityApi.Activity).tenant_code"
                class="ml-1 text-muted-foreground"
              >
                ({{ (rawRecord as ActivityApi.Activity).tenant_code }})
              </span>
            </span>
            <span v-else class="text-muted-foreground">-</span>
          </template>
          <template v-else-if="column.key === 'channel'">
            <Tag color="blue">
              {{ getChannelLabel((rawRecord as ActivityApi.Activity).channel) }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'status'">
            <Select
              :value="(rawRecord as ActivityApi.Activity).status"
              :options="statusOptions"
              size="small"
              style="width: 100px"
              @change="
                (val: unknown) =>
                  handleStatusChange(
                    rawRecord as ActivityApi.Activity,
                    val as ActivityApi.ActivityStatus,
                  )
              "
            >
              <template #tagRender="{ label }">
                <Tag
                  :color="
                    statusConfig[(rawRecord as ActivityApi.Activity).status]
                      ?.color || 'default'
                  "
                >
                  {{ label }}
                </Tag>
              </template>
            </Select>
          </template>
          <template v-else-if="column.key === 'publish_status'">
            <Tag
              :color="
                publishStatusConfig[
                  (rawRecord as ActivityApi.Activity).publish_status || 'DRAFT'
                ]?.color || 'default'
              "
            >
              {{
                publishStatusConfig[
                  (rawRecord as ActivityApi.Activity).publish_status || 'DRAFT'
                ]?.label || '草稿'
              }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'action'">
            <Space :size="0">
              <!-- 上线/下线按钮 -->
              <Tooltip
                v-if="
                  (rawRecord as ActivityApi.Activity).publish_status !==
                  'PUBLISHED'
                "
                title="上线"
              >
                <Button
                  type="link"
                  size="small"
                  :loading="publishLoading"
                  @click="
                    handlePublishPreview(rawRecord as ActivityApi.Activity)
                  "
                >
                  🚀
                </Button>
              </Tooltip>
              <Tooltip v-else title="下线">
                <Button
                  type="link"
                  size="small"
                  @click="handleUnpublish(rawRecord as ActivityApi.Activity)"
                >
                  ⏸️
                </Button>
              </Tooltip>
              <Tooltip title="编辑">
                <Button
                  type="link"
                  size="small"
                  :disabled="
                    (rawRecord as ActivityApi.Activity).publish_status ===
                    'PUBLISHED'
                  "
                  @click="handleEditCheck(rawRecord as ActivityApi.Activity)"
                >
                  ✏️
                </Button>
              </Tooltip>
              <Tooltip title="删除">
                <Button
                  type="link"
                  danger
                  size="small"
                  :disabled="
                    (rawRecord as ActivityApi.Activity).publish_status ===
                    'PUBLISHED'
                  "
                  @click="handleDeleteCheck(rawRecord as ActivityApi.Activity)"
                >
                  🗑️
                </Button>
              </Tooltip>
            </Space>
          </template>
        </template>
      </Table>
    </Card>

    <!-- 上线预检查弹窗 -->
    <Modal
      v-model:open="publishPreviewVisible"
      title="上线确认"
      :confirm-loading="publishLoading"
      :width="600"
      ok-text="确认上线"
      cancel-text="取消"
      @ok="handlePublishConfirm"
    >
      <template v-if="publishPreviewData">
        <div v-if="!publishPreviewData.can_publish" class="publish-error">
          <Tag color="error">无法上线</Tag>
          <ul class="error-list">
            <li v-for="(err, idx) in publishPreviewData.errors" :key="idx">
              {{ err }}
            </li>
          </ul>
        </div>
        <div v-else class="publish-preview">
          <div class="preview-section">
            <div class="section-title">即将上线以下配置：</div>
            <div
              v-if="publishPreviewData.dependencies?.agent"
              class="dependency-item"
            >
              <Tag color="blue">Agent</Tag>
              <span>{{ publishPreviewData.dependencies.agent.name }}</span>
              <Tag
                v-if="
                  publishPreviewData.dependencies.agent.current_status ===
                  'PUBLISHED'
                "
                color="success"
                size="small"
              >
                已上线
              </Tag>
            </div>
            <div
              v-if="publishPreviewData.dependencies?.expert_configs?.length"
              class="dependency-item"
            >
              <Tag color="purple">ExpertConfig</Tag>
              <span
                >{{
                  publishPreviewData.dependencies.expert_configs.length
                }}
                个</span
              >
            </div>
            <div
              v-if="publishPreviewData.dependencies?.plugins?.length"
              class="dependency-item"
            >
              <Tag color="cyan">Plugin</Tag>
              <span
                >{{ publishPreviewData.dependencies.plugins.length }} 个</span
              >
            </div>
            <div
              v-if="publishPreviewData.dependencies?.plugin_contexts?.length"
              class="dependency-item"
            >
              <Tag color="orange">PluginContext</Tag>
              <span
                >{{
                  publishPreviewData.dependencies.plugin_contexts.length
                }}
                个</span
              >
            </div>
          </div>
          <div
            v-if="publishPreviewData.validation?.warnings?.length"
            class="preview-warnings"
          >
            <div class="section-title">⚠️ 警告：</div>
            <ul class="warning-list">
              <li
                v-for="(warn, idx) in publishPreviewData.validation.warnings"
                :key="idx"
              >
                {{ warn }}
              </li>
            </ul>
          </div>
          <div class="preview-notice">
            上线后，以上配置将被锁定，不可编辑或删除。
          </div>
        </div>
      </template>
    </Modal>

    <!-- 创建/编辑弹窗 -->
    <Modal
      v-model:open="modalVisible"
      :title="modalTitle"
      :confirm-loading="modalLoading"
      :width="550"
      @ok="handleSubmit"
    >
      <Form :label-col="{ span: 5 }" :wrapper-col="{ span: 18 }">
        <FormItem label="活动编码" required>
          <Input
            v-model:value="formState.activity_code"
            placeholder="请输入唯一编码"
            :disabled="!!editingId"
          />
        </FormItem>
        <FormItem label="活动名称" required>
          <Input
            v-model:value="formState.activity_name"
            placeholder="请输入活动名称"
          />
        </FormItem>
        <FormItem label="所属租户" required>
          <Select
            v-model:value="formState.tenant_id"
            placeholder="请选择租户"
            show-search
            :filter-option="true"
            :options="
              tenantOptions.map((t) => ({
                label: `${t.tenant_name} (${t.tenant_code})`,
                value: t.id,
              }))
            "
            :get-popup-container="(trigger) => trigger.parentElement"
            @change="
              (val: unknown) =>
                handleModalTenantChange(
                  val === undefined || val === null
                    ? undefined
                    : (val as number),
                )
            "
          />
        </FormItem>
        <FormItem label="使用 Agent">
          <Select
            v-model:value="formState.agent_code_list"
            placeholder="请选择 Agent（可选，支持多选）"
            mode="multiple"
            allow-clear
            :disabled="!formState.tenant_id"
            :options="agentOptions"
            show-search
            :max-tag-count="3"
            :get-popup-container="(trigger) => trigger.parentElement"
          />
        </FormItem>
        <FormItem label="渠道">
          <Select
            v-model:value="formState.channel"
            :options="channelOptions"
            placeholder="请选择渠道"
            allow-clear
            show-search
            :filter-option="true"
            :get-popup-container="(trigger) => trigger.parentElement"
          />
        </FormItem>
        <FormItem label="目标受众">
          <Input
            v-model:value="formState.target_audience"
            placeholder="请输入目标受众描述"
          />
        </FormItem>
        <FormItem label="预算">
          <InputNumber
            v-model:value="formState.budget"
            placeholder="请输入预算金额"
            style="width: 100%"
            :min="0"
            :precision="2"
          />
        </FormItem>
        <FormItem label="状态">
          <Select
            v-model:value="formState.status"
            :options="statusOptions"
            placeholder="请选择状态"
            show-search
            :filter-option="true"
            :get-popup-container="(trigger) => trigger.parentElement"
          />
        </FormItem>
        <FormItem label="备注">
          <Input.TextArea
            v-model:value="formState.remark"
            placeholder="请输入备注"
            :rows="2"
          />
        </FormItem>
      </Form>

      <!-- 活动问题与标签配置区域 -->
      <Divider orientation="left" style="margin: 16px 0 12px">
        活动问题与标签
      </Divider>
      <div class="questions-section">
        <div class="questions-header">
          <Button type="primary" size="small" @click="openAddQuestionModal">
            <PlusOutlined /> 增加问题
          </Button>
        </div>
        <div v-if="formState.questions.length === 0" class="questions-empty">
          暂无问题配置，点击上方按钮添加
        </div>
        <div v-else class="questions-list">
          <div
            v-for="(question, index) in formState.questions"
            :key="index"
            class="question-item"
          >
            <div class="question-header">
              <span class="question-title">
                {{ index + 1 }}. {{ question.question_text }}
              </span>
              <Tag color="blue" size="small">
                {{ getSelectTypeText(question) }}
              </Tag>
              <div class="question-actions">
                <Button
                  type="link"
                  size="small"
                  @click="openEditQuestionModal(index)"
                >
                  修 改
                </Button>
                <Popconfirm
                  title="确定删除此问题吗？"
                  @confirm="handleDeleteQuestion(index)"
                >
                  <Button type="link" danger size="small">删 除</Button>
                </Popconfirm>
              </div>
            </div>
            <div class="question-options">
              <Tag
                v-for="(opt, optIdx) in question.options"
                :key="optIdx"
                class="option-tag"
              >
                {{ opt.display_label.slice(0, 15)
                }}{{ opt.display_label.length > 15 ? '...' : '' }} |
                {{ opt.aigc_tag }}({{ opt.weight }})
              </Tag>
            </div>
          </div>
        </div>
      </div>
    </Modal>

    <!-- 问题编辑弹窗 -->
    <Modal
      v-model:open="questionModalVisible"
      :title="editingQuestionIndex !== null ? '编辑问题' : '活动问题与标签'"
      :width="700"
      :footer="null"
    >
      <div class="question-form">
        <div class="form-row">
          <div class="form-label">问题</div>
          <div class="form-control" style="display: flex; gap: 12px">
            <Input
              v-model:value="questionForm.question_text"
              placeholder="请输入问题内容"
              style="flex: 1"
            />
            <Button type="primary" @click="handleImportTemplate">
              导入标准问题模板
            </Button>
          </div>
        </div>

        <div class="form-row">
          <div class="form-label">选择类型</div>
          <div class="form-control">
            <div class="select-type-group">
              <Button
                :type="
                  (questionForm.max_select ?? 1) === 1 ? 'primary' : 'default'
                "
                @click="handleSelectTypeChange('single')"
              >
                单选
              </Button>
              <Button
                :type="
                  (questionForm.max_select ?? 1) !== 1 ? 'primary' : 'default'
                "
                @click="handleSelectTypeChange('multiple')"
              >
                多选
              </Button>
            </div>
          </div>
        </div>

        <div class="form-row">
          <div class="form-label">可选标签</div>
          <div class="form-control">
            <Table
              :columns="optionColumns"
              :data-source="questionForm.options"
              :pagination="false"
              size="small"
              row-key="sort_order"
            >
              <template #headerCell="{ column }">
                <template v-if="column.key === 'action'">
                  <Button type="primary" size="small" @click="handleAddOption">
                    新增标签
                  </Button>
                </template>
              </template>
              <template #bodyCell="{ column, record, index }">
                <template v-if="column.key === 'display_label'">
                  <Input
                    v-model:value="
                      (record as ActivityApi.QuestionOption).display_label
                    "
                    placeholder="小程序展示可替换标签"
                    size="small"
                  />
                </template>
                <template v-else-if="column.key === 'aigc_tag'">
                  <Input
                    v-model:value="
                      (record as ActivityApi.QuestionOption).aigc_tag
                    "
                    placeholder="AIGC标签"
                    size="small"
                  />
                </template>
                <template v-else-if="column.key === 'weight'">
                  <InputNumber
                    v-model:value="
                      (record as ActivityApi.QuestionOption).weight
                    "
                    :min="0"
                    :max="1"
                    :step="0.1"
                    :precision="1"
                    size="small"
                    style="width: 100%"
                  />
                </template>
                <template v-else-if="column.key === 'action'">
                  <Button
                    type="link"
                    danger
                    size="small"
                    @click="handleDeleteOption(index)"
                  >
                    删除
                  </Button>
                </template>
              </template>
            </Table>
          </div>
        </div>

        <div class="form-footer">
          <Button @click="questionModalVisible = false">取 消</Button>
          <Button type="primary" @click="handleSaveQuestion">确 定</Button>
        </div>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.activity-page {
  padding: 16px;
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

:deep(.ant-card-head) {
  border-bottom: 1px solid hsl(var(--border));
}

:deep(.ant-table-thead > tr > th) {
  background: hsl(var(--muted));
}

/* 上线预检查弹窗样式 */
.publish-error {
  padding: 16px;
  background: hsl(var(--destructive) / 10%);
  border-radius: 8px;
}

.error-list,
.warning-list {
  padding-left: 20px;
  margin: 8px 0 0;
}

.error-list li {
  color: hsl(var(--destructive));
}

.warning-list li {
  color: hsl(var(--warning));
}

.publish-preview {
  padding: 8px 0;
}

.preview-section {
  margin-bottom: 16px;
}

.section-title {
  margin-bottom: 8px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.dependency-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  margin-bottom: 8px;
  background: hsl(var(--muted) / 30%);
  border-radius: 6px;
}

.preview-warnings {
  padding: 12px;
  margin-bottom: 16px;
  background: hsl(var(--warning) / 10%);
  border-radius: 8px;
}

.preview-notice {
  padding: 12px;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted) / 30%);
  border-radius: 8px;
}

/* 问题配置样式 */
.questions-section {
  padding: 12px;
  background: hsl(var(--muted) / 20%);
  border-radius: 8px;
}

.questions-header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.questions-empty {
  padding: 32px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.questions-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.question-item {
  padding: 12px;
  background: hsl(var(--background));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.question-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.question-title {
  flex: 1;
  font-weight: 500;
}

.question-actions {
  display: flex;
  gap: 4px;
}

.question-options {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.option-tag {
  margin: 0 !important;
  font-size: 12px;
}

/* 问题编辑弹窗样式 */
.question-form {
  padding: 8px 0;
}

.form-row {
  margin-bottom: 16px;
}

.form-label {
  margin-bottom: 8px;
  font-weight: 500;
}

.form-control {
  width: 100%;
}

.select-type-group {
  display: flex;
  gap: 8px;
}

.form-footer {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  padding-top: 16px;
  margin-top: 24px;
  border-top: 1px solid hsl(var(--border));
}
</style>
