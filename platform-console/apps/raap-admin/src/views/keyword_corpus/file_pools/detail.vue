<script setup lang="ts">
import type { UploadFile } from 'ant-design-vue/es/upload/interface';

import type { KnowledgeBaseFilesApi } from '#/api/core/file-documents';

import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import {
  DeleteOutlined,
  DownloadOutlined,
  FileExcelOutlined,
  FilePdfOutlined,
  FilePptOutlined,
  FileTextOutlined,
  FileWordOutlined,
  SearchOutlined,
  UploadOutlined,
} from '@ant-design/icons-vue';
import {
  Button,
  Card,
  Empty,
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
  Upload,
} from 'ant-design-vue';

import {
  deleteKnowledgeBaseFileApi,
  getKnowledgeBaseApi,
  listKnowledgeBaseFilesApi,
  uploadKnowledgeBaseFileApi,
} from '#/api/core/file-documents';

const route = useRoute();

// ==================== 类型图标映射 ====================

const fileTypeIcons: Record<
  KnowledgeBaseFilesApi.DocType,
  typeof FilePdfOutlined
> = {
  pdf: FilePdfOutlined,
  word: FileWordOutlined,
  ppt: FilePptOutlined,
  excel: FileExcelOutlined,
  unknown: FileTextOutlined,
};

const fileTypeColors: Record<KnowledgeBaseFilesApi.DocType, string> = {
  pdf: 'red',
  word: 'blue',
  ppt: 'orange',
  excel: 'green',
  unknown: 'default',
};

// ==================== 状态 ====================

const poolId = computed(() => Number(route.params.id));
const loading = ref(false);
const poolLoading = ref(false);
const poolInfo = ref<KnowledgeBaseFilesApi.KnowledgeBase>();
const dataSource = ref<KnowledgeBaseFilesApi.KnowledgeBaseFileItem[]>([]);

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0,
});

const filters = reactive({
  keyword: '',
  file_type: undefined as KnowledgeBaseFilesApi.DocType | undefined,
});

const fileTypeOptions = [
  { value: 'pdf', label: 'PDF' },
  { value: 'word', label: 'Word' },
  { value: 'ppt', label: 'PPT' },
  { value: 'excel', label: 'Excel' },
];

// ==================== 上传弹窗 ====================

const uploadModalVisible = ref(false);
const uploading = ref(false);
const fileList = ref<UploadFile[]>([]);

// ==================== API 调用 ====================

async function fetchPoolInfo() {
  poolLoading.value = true;
  try {
    poolInfo.value = await getKnowledgeBaseApi(poolId.value);
  } catch (error: unknown) {
    message.error((error as Error)?.message || '加载知识库信息失败');
  } finally {
    poolLoading.value = false;
  }
}

async function fetchList() {
  loading.value = true;
  try {
    const res = await listKnowledgeBaseFilesApi(poolId.value, {
      keyword: filters.keyword || undefined,
      file_type: filters.file_type || undefined,
      page: pagination.current,
      page_size: pagination.pageSize,
    });
    dataSource.value = res.items;
    pagination.total = res.total;
  } catch (error: unknown) {
    message.error((error as Error)?.message || '加载失败');
  } finally {
    loading.value = false;
  }
}

function resetFilters() {
  filters.keyword = '';
  filters.file_type = undefined;
  pagination.current = 1;
  fetchList();
}

function onPageChange(page: number) {
  pagination.current = page;
  fetchList();
}

// ==================== 上传相关 ====================

const acceptTypes =
  '.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-powerpoint,application/vnd.openxmlformats-officedocument.presentationml.presentation,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

function openUpload() {
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
      await uploadKnowledgeBaseFileApi(poolId.value, file);
    }
    message.success(`成功上传 ${files.length} 个文件`);
    uploadModalVisible.value = false;
    fileList.value = [];
    await fetchList();
    await fetchPoolInfo();
  } catch (error: unknown) {
    message.error((error as Error)?.message || '上传失败');
  } finally {
    uploading.value = false;
  }
}

// ==================== 下载相关 ====================

function handleDownload(record: KnowledgeBaseFilesApi.KnowledgeBaseFileItem) {
  // 构建 API 地址，添加 token
  const token = localStorage.getItem('access_token') || '';
  const url = `/v1/knowledge-base-files/${record.id}/download?token=${token}`;

  // 创建隐藏的 a 标签触发下载
  const link = document.createElement('a');
  link.href = url;
  link.download = record.file_name;
  document.body.append(link);
  link.click();
  link.remove();

  message.success('开始下载');
}

// ==================== 删除 ====================

async function handleDelete(
  record: KnowledgeBaseFilesApi.KnowledgeBaseFileItem,
) {
  try {
    await deleteKnowledgeBaseFileApi(record.id);
    message.success('删除成功');
    await fetchList();
    await fetchPoolInfo();
  } catch (error: unknown) {
    message.error((error as Error)?.message || '删除失败');
  }
}
//     selectedRows.value = rows;
//   },
// }));

// ==================== 生命周期 ====================

onMounted(async () => {
  await fetchPoolInfo();
  await fetchList();
});

watch(
  () => route.params.id,
  async (newId) => {
    if (newId) {
      await fetchPoolInfo();
      await fetchList();
    }
  },
);
</script>

<template>
  <div class="document-detail-page">
    <!-- 头部信息 -->
    <Card :bordered="false" class="header-card">
      <Spin :spinning="poolLoading">
        <div v-if="poolInfo" class="pool-header">
          <div class="header-left">
            <div class="header-info">
              <div class="header-title">{{ poolInfo.name }}</div>
              <div class="header-code">{{ poolInfo.code }}</div>
              <div v-if="poolInfo.description" class="header-desc">
                {{ poolInfo.description }}
              </div>
            </div>
          </div>
          <div class="header-right">
            <Space>
              <Button @click="openUpload">
                <template #icon><UploadOutlined /></template>
                上传文件
              </Button>
            </Space>
          </div>
        </div>
      </Spin>
    </Card>

    <!-- 筛选和列表 -->
    <Card :bordered="false" class="list-card">
      <Form layout="inline" class="filter-form">
        <FormItem>
          <Input
            v-model:value="filters.keyword"
            allow-clear
            placeholder="搜索文件名"
            style="width: 200px"
            @press-enter="fetchList"
          >
            <template #prefix>
              <SearchOutlined />
            </template>
          </Input>
        </FormItem>
        <FormItem>
          <Select
            v-model:value="filters.file_type"
            allow-clear
            :options="fileTypeOptions"
            placeholder="文件类型"
            style="width: 120px"
            @change="fetchList"
          />
        </FormItem>
        <FormItem>
          <Space>
            <Button type="primary" @click="fetchList">查询</Button>
            <Button @click="resetFilters">重置</Button>
          </Space>
        </FormItem>
      </Form>

      <Spin :spinning="loading">
        <div v-if="dataSource.length > 0" class="document-list">
          <div v-for="item in dataSource" :key="item.id" class="document-item">
            <div class="doc-icon" :class="item.file_type">
              <component :is="fileTypeIcons[item.file_type]" />
            </div>
            <div class="doc-info">
              <div class="doc-name">{{ item.file_name }}</div>
              <div class="doc-meta">
                <Tag :color="fileTypeColors[item.file_type]" size="small">
                  {{ item.file_type.toUpperCase() }}
                </Tag>
                <span class="doc-size"
                  >{{ (item.file_size / 1024).toFixed(1) }} KB</span
                >
                <span class="doc-time">{{ item.create_time }}</span>
              </div>
            </div>
            <div class="doc-actions">
              <Tooltip title="下载文件">
                <Button type="link" size="small" @click="handleDownload(item)">
                  <template #icon><DownloadOutlined /></template>
                  下载
                </Button>
              </Tooltip>
              <Popconfirm
                title="确定删除该文件？"
                @confirm="handleDelete(item)"
              >
                <Button type="link" size="small" danger>
                  <template #icon><DeleteOutlined /></template>
                  删除
                </Button>
              </Popconfirm>
            </div>
          </div>
        </div>

        <Empty v-else description="暂无文件" />
      </Spin>

      <!-- 分页 -->
      <div
        v-if="pagination.total > pagination.pageSize"
        class="pagination-wrap"
      >
        <div class="pagination-info">共 {{ pagination.total }} 个文件</div>
        <div class="pagination-btns">
          <Button
            :disabled="pagination.current <= 1"
            @click="onPageChange(pagination.current - 1)"
          >
            上一页
          </Button>
          <span class="page-num">{{ pagination.current }}</span>
          <Button
            :disabled="
              pagination.current * pagination.pageSize >= pagination.total
            "
            @click="onPageChange(pagination.current + 1)"
          >
            下一页
          </Button>
        </div>
      </div>
    </Card>

    <!-- 上传弹窗 -->
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
          <p class="ant-upload-hint">支持批量上传</p>
        </Upload>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.document-detail-page {
  min-height: 100%;
  padding: 20px;
  background: hsl(var(--background));
}

.header-card {
  margin-bottom: 20px;
}

.pool-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-left {
  display: flex;
  gap: 16px;
  align-items: center;
}

.header-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.header-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.header-desc {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.list-card {
  min-height: calc(100vh - 240px);
}

.filter-form {
  margin-bottom: 20px;
}

.document-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.document-item {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 16px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  transition: all 0.2s;
}

.document-item:hover {
  border-color: hsl(var(--primary) / 30%);
}

.doc-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  font-size: 20px;
  border-radius: 8px;
}

.doc-icon.pdf {
  color: hsl(0deg 84% 60%);
  background: hsl(0deg 84% 60% / 15%);
}

.doc-icon.word {
  color: hsl(217deg 91% 60%);
  background: hsl(217deg 91% 60% / 15%);
}

.doc-icon.ppt {
  color: hsl(30deg 100% 50%);
  background: hsl(30deg 100% 50% / 15%);
}

.doc-icon.excel {
  color: hsl(142deg 76% 36%);
  background: hsl(142deg 76% 36% / 15%);
}

.doc-icon.unknown {
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted-foreground) / 15%);
}

.doc-info {
  flex: 1;
  min-width: 0;
}

.doc-name {
  margin-bottom: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
  font-weight: 500;
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.doc-meta {
  display: flex;
  gap: 12px;
  align-items: center;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.doc-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}

.document-item:hover .doc-actions {
  opacity: 1;
}

.pagination-wrap {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 0;
  margin-top: 24px;
}

.pagination-info {
  font-size: 14px;
  color: hsl(var(--muted-foreground));
}

.pagination-btns {
  display: flex;
  gap: 12px;
  align-items: center;
}

.page-num {
  min-width: 32px;
  font-size: 14px;
  font-weight: 500;
  color: hsl(var(--foreground));
  text-align: center;
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
