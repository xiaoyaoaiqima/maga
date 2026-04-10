<script setup lang="ts">
import type { UploadFile } from 'ant-design-vue/es/upload/interface';

import type { KnowledgeBaseFilesApi } from '#/api/core/file-documents';

import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import {
  DeleteOutlined,
  EditOutlined,
  FileTextOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue';
import {
  Button,
  Empty,
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Popconfirm,
  Select,
  Spin,
  Switch,
  Tag,
  Textarea,
  Tooltip,
  Upload,
} from 'ant-design-vue';

import {
  createKnowledgeBaseApi,
  deleteKnowledgeBaseApi,
  listKnowledgeBasesApi,
  toggleKnowledgeBaseEnabledApi,
  updateKnowledgeBaseApi,
  uploadKnowledgeBaseFileApi,
} from '#/api/core/file-documents';

const router = useRouter();

// ==================== 类型图标映射 ====================
// 预留供后续使用
// const fileTypeIcons: Record<FileDocumentsApi.DocType, typeof FilePdfOutlined> =
//   {
//     pdf: FilePdfOutlined,
//     word: FileWordOutlined,
//     ppt: FilePptOutlined,
//     excel: FileExcelOutlined,
//     unknown: FileTextOutlined,
//   };

// const fileTypeColors: Record<FileDocumentsApi.DocType, string> = {
//   pdf: 'red',
//   word: 'blue',
//   ppt: 'orange',
//   excel: 'green',
//   unknown: 'default',
// };

// ==================== 状态 ====================

const loading = ref(false);
const dataSource = ref<KnowledgeBaseFilesApi.KnowledgeBase[]>([]);

const filters = reactive({
  keyword: '',
  enabled: undefined as '0' | '1' | undefined,
});
const lastUpdateTime = ref('');

const enabledOptions = [
  { value: '1', label: '启用' },
  { value: '0', label: '禁用' },
];

// ==================== 表单弹窗 ====================

const modalVisible = ref(false);
const isSubmitting = ref(false);
const editing = ref<KnowledgeBaseFilesApi.KnowledgeBase | null>(null);

const formState = reactive<KnowledgeBaseFilesApi.CreateKnowledgeBaseRequest>({
  code: '',
  name: '',
  description: '',
  enabled: 1,
});

const modalTitle = computed(() =>
  editing.value ? '编辑知识库' : '新建知识库',
);

// ==================== 上传弹窗 ====================

const uploadModalVisible = ref(false);
const uploadPoolId = ref<number>();
// const uploadLoading = ref(false); // 预留供后续使用
const fileList = ref<UploadFile[]>([]);
const uploading = ref(false);

// ==================== API 调用 ====================

async function fetchList() {
  loading.value = true;
  try {
    let enabled: boolean | undefined;
    if (filters.enabled === '1') {
      enabled = true;
    } else if (filters.enabled === '0') {
      enabled = false;
    }
    const res = await listKnowledgeBasesApi({
      keyword: filters.keyword || undefined,
      enabled,
    });
    dataSource.value = res.items;
    // 更新时间
    lastUpdateTime.value = new Date().toLocaleString('zh-CN', {
      hour12: false,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch (error: unknown) {
    message.error((error as Error)?.message || '加载失败');
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  editing.value = null;
  Object.assign(formState, {
    code: '',
    name: '',
    description: '',
    enabled: 1,
  });
  modalVisible.value = true;
}

function openEdit(record: KnowledgeBaseFilesApi.KnowledgeBase, e: Event) {
  e.stopPropagation();
  editing.value = record;
  Object.assign(formState, {
    code: record.code,
    name: record.name,
    description: record.description || '',
    enabled: record.enabled,
  });
  modalVisible.value = true;
}

async function submit() {
  const name = formState.name.trim();

  if (!name) {
    message.warning('请输入知识库名称');
    return;
  }

  isSubmitting.value = true;
  try {
    if (editing.value) {
      await updateKnowledgeBaseApi(editing.value.id, {
        name,
        description: formState.description?.trim() || undefined,
        enabled: formState.enabled,
      });
      message.success('更新成功');
    } else {
      await createKnowledgeBaseApi({
        code: formState.code?.trim() || undefined,
        name,
        description: formState.description?.trim() || undefined,
        enabled: formState.enabled,
      });
      message.success('创建成功');
    }
    modalVisible.value = false;
    await fetchList();
  } catch (error: unknown) {
    message.error((error as Error)?.message || '提交失败');
  } finally {
    isSubmitting.value = false;
  }
}

async function toggleEnabled(
  record: KnowledgeBaseFilesApi.KnowledgeBase,
  e: Event,
) {
  e.stopPropagation();
  try {
    const updated = await toggleKnowledgeBaseEnabledApi(record.id);
    record.enabled = updated.enabled;
    message.success('已更新');
  } catch (error: unknown) {
    message.error((error as Error)?.message || '更新失败');
  }
}

async function remove(record: KnowledgeBaseFilesApi.KnowledgeBase, e: Event) {
  e.stopPropagation();
  try {
    await deleteKnowledgeBaseApi(record.id);
    message.success('删除成功');
    await fetchList();
  } catch (error: unknown) {
    message.error((error as Error)?.message || '删除失败');
  }
}

function goToDetail(record: KnowledgeBaseFilesApi.KnowledgeBase) {
  router.push(`/keyword_corpus/file_pools/${record.id}`);
}

function resetFilters() {
  filters.keyword = '';
  filters.enabled = undefined;
  fetchList();
}

// ==================== 上传相关 ====================

const acceptTypes =
  '.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-powerpoint,application/vnd.openxmlformats-officedocument.presentationml.presentation,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

function openUpload(
  knowledgeBase: KnowledgeBaseFilesApi.KnowledgeBase,
  e: Event,
) {
  e.stopPropagation();
  uploadPoolId.value = knowledgeBase.id;
  fileList.value = [];
  uploadModalVisible.value = true;
}

function beforeUpload(file: File) {
  const isValidType = acceptTypes
    .split(',')
    .some((type) => file.type.includes(type.replace('.', '')));
  if (!isValidType) {
    message.error('只支持上传 PDF、Word、PPT、Excel 文档');
    return Upload.LIST_IGNORE;
  }
  const isLt50M = file.size / 1024 / 1024 < 50;
  if (!isLt50M) {
    message.error('文件大小不能超过 50MB');
    return Upload.LIST_IGNORE;
  }
  return false;
}

async function handleUpload() {
  if (!uploadPoolId.value) {
    return;
  }

  const files = fileList.value
    .filter((f) => f.originFileObj)
    .map((f) => f.originFileObj as File);

  if (files.length === 0) {
    message.warning('请选择要上传的文件');
    return;
  }

  uploading.value = true;
  try {
    for (const file of files) {
      await uploadKnowledgeBaseFileApi(uploadPoolId.value, file);
    }
    message.success(`成功上传 ${files.length} 个文件`);
    uploadModalVisible.value = false;
    fileList.value = [];
    await fetchList();
  } catch (error: unknown) {
    message.error((error as Error)?.message || '上传失败');
  } finally {
    uploading.value = false;
  }
}

// ==================== 生命周期 ====================

// 防抖搜索
let searchTimer: null | ReturnType<typeof setTimeout> = null;
watch(
  () => filters.keyword,
  () => {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      fetchList();
    }, 300);
  },
);

watch(
  () => filters.enabled,
  () => {
    fetchList();
  },
);

onMounted(async () => {
  await fetchList();
});
</script>

<template>
  <div class="file-pools-page">
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
          知识库管理
        </span>
        <span v-if="lastUpdateTime" class="text-xs text-muted-foreground">
          数据更新时间：{{ lastUpdateTime }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <Space size="middle">
          <Input
            v-model:value="filters.keyword"
            allow-clear
            placeholder="搜索名称/编码"
            style="width: 200px"
          >
            <template #prefix>
              <SearchOutlined />
            </template>
          </Input>
          <Select
            v-model:value="filters.enabled"
            allow-clear
            :options="enabledOptions"
            placeholder="状态"
            style="width: 100px"
          />
          <Button @click="resetFilters">重置</Button>
        </Space>
        <div class="filter-actions">
          <Button variant="ghost" size="small" @click="fetchList">
            <template #icon><ReloadOutlined /></template>
            刷新
          </Button>
        </div>
      </div>
    </div>

    <!-- 知识库卡片网格 -->
    <Spin :spinning="loading">
      <div class="card-grid">
        <!-- 新建知识库卡片 -->
        <div class="pool-card create-card" @click="openCreate">
          <div class="create-card-content">
            <div class="create-icon">
              <PlusOutlined />
            </div>
            <div class="create-text">新建知识库</div>
            <div class="create-hint">创建一个新的知识库</div>
          </div>
        </div>
        <!-- 知识库列表 -->
        <div
          v-for="item in dataSource"
          :key="item.id"
          class="pool-card"
          @click="goToDetail(item)"
        >
          <div class="card-header">
            <div class="card-icon">
              <FileTextOutlined />
            </div>
            <div class="card-actions">
              <Tooltip title="上传文件">
                <Button
                  type="text"
                  size="small"
                  @click="(e: Event) => openUpload(item, e)"
                >
                  <template #icon><PlusOutlined /></template>
                </Button>
              </Tooltip>
              <Tooltip title="编辑">
                <Button
                  type="text"
                  size="small"
                  @click="(e: Event) => openEdit(item, e)"
                >
                  <template #icon><EditOutlined /></template>
                </Button>
              </Tooltip>
              <Popconfirm
                title="确定删除该知识库？"
                @confirm="(e: Event) => remove(item, e)"
              >
                <Tooltip title="删除">
                  <Button type="text" size="small" danger @click.stop>
                    <template #icon><DeleteOutlined /></template>
                  </Button>
                </Tooltip>
              </Popconfirm>
            </div>
          </div>

          <div class="card-body">
            <div class="card-title">{{ item.name }}</div>
            <div class="card-code">{{ item.code }}</div>
            <div v-if="item.description" class="card-desc">
              {{ item.description }}
            </div>
          </div>

          <div class="card-footer">
            <div class="card-meta">
              <Tag color="blue">{{ item.file_count }} 个文件</Tag>
            </div>
            <Switch
              :checked="item.enabled === 1"
              checked-children="启用"
              size="small"
              un-checked-children="禁用"
              @click.stop
              @change="
                (checked: boolean | string | number, e: Event) =>
                  toggleEnabled(item, e)
              "
            />
          </div>
        </div>
      </div>

      <Empty
        v-if="dataSource.length === 0"
        description="暂无知识库，点击左侧卡片创建"
      />
    </Spin>

    <!-- 新建/编辑弹窗 -->
    <Modal
      v-model:open="modalVisible"
      :confirm-loading="isSubmitting"
      :title="modalTitle"
      :width="520"
      @ok="submit"
    >
      <Form layout="vertical" class="modal-form">
        <FormItem v-if="!editing" label="编码">
          <Input v-model:value="formState.code" placeholder="留空自动生成" />
        </FormItem>
        <FormItem label="名称" required>
          <Input
            v-model:value="formState.name"
            placeholder="请输入知识库名称"
          />
        </FormItem>
        <FormItem label="描述">
          <Textarea
            v-model:value="formState.description"
            :rows="3"
            placeholder="可选，简要描述知识库用途"
          />
        </FormItem>
        <FormItem label="启用状态">
          <Switch
            :checked="formState.enabled === 1"
            checked-children="启用"
            un-checked-children="禁用"
            @change="
              (checked: boolean | string | number) =>
                (formState.enabled = checked ? 1 : 0)
            "
          />
        </FormItem>
      </Form>
    </Modal>

    <!-- 上传文件弹窗 -->
    <Modal
      v-model:open="uploadModalVisible"
      :confirm-loading="uploading"
      title="上传知识库文件"
      :width="520"
      @ok="handleUpload"
    >
      <div class="upload-modal-content">
        <p class="upload-tip">
          支持 PDF、Word、PPT、Excel 格式，单个文件不超过 50MB
        </p>
        <Upload
          v-model:file-list="fileList"
          :accept="acceptTypes"
          :before-upload="beforeUpload"
          drag
          multiple
        >
          <p class="ant-upload-drag-icon">
            <FileTextOutlined style="font-size: 48px; color: #d9d9d9" />
          </p>
          <p class="ant-upload-text">点击或拖拽文件到此区域上传</p>
          <p class="ant-upload-hint">
            支持批量上传，上传后可在列表中进行 AI 解析
          </p>
        </Upload>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.file-pools-page {
  min-height: 100%;
  padding: 16px;
  background: hsl(var(--background));
}

/* 按钮样式 */
.action-btn {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  font-size: 13px;
}

.btn-icon {
  font-size: 14px;
}

.btn-label {
  font-size: 13px;
}

/* 筛选器层 */
.filter-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 16px 20px;
  margin-bottom: 16px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
}

/* 筛选行 */
.filter-row {
  display: flex;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
}

.filter-actions {
  display: flex;
  gap: 8px;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}

.pool-card {
  display: flex;
  flex-direction: column;
  padding: 20px;
  cursor: pointer;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  transition: all 0.2s ease;
}

.pool-card:hover {
  border-color: hsl(var(--primary));
  box-shadow: 0 4px 12px hsl(var(--primary) / 15%);
  transform: translateY(-2px);
}

/* 新建文档池卡片 */
.pool-card.create-card {
  position: relative;
  align-items: center;
  justify-content: center;
  min-height: 180px;
  background: hsl(var(--card));
  border: 2px dashed hsl(var(--primary) / 30%);
}

.pool-card.create-card:hover {
  background: hsl(var(--primary) / 3%);
  border-color: hsl(var(--primary));
}

.create-card-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
  text-align: center;
}

.create-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  font-size: 28px;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 10%);
  border-radius: 50%;
}

.create-text {
  font-size: 16px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.create-hint {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
}

.card-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  font-size: 24px;
  color: hsl(217deg 91% 60%);
  background: hsl(217deg 91% 60% / 15%);
  border-radius: 12px;
}

.card-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}

.pool-card:hover .card-actions {
  opacity: 1;
}

.card-body {
  flex: 1;
  margin-bottom: 16px;
}

.card-title {
  margin-bottom: 4px;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.4;
  color: hsl(var(--foreground));
}

.card-code {
  margin-bottom: 8px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.card-desc {
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 2;
  font-size: 13px;
  line-height: 1.5;
  color: hsl(var(--muted-foreground));
  -webkit-box-orient: vertical;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 16px;
  border-top: 1px solid hsl(var(--border));
}

.card-meta {
  display: flex;
  gap: 12px;
  align-items: center;
}

.modal-form {
  padding-top: 12px;
}

.upload-modal-content {
  padding: 12px 0;
}

.upload-tip {
  margin-bottom: 16px;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}
</style>
