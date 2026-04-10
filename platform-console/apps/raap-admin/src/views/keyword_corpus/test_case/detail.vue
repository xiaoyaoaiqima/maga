<script setup lang="ts">
import type { UploadChangeParam } from 'ant-design-vue';

import type { TestCaseApi } from '#/api/core/test-cases';
import type { TestSetApi } from '#/api/core/test-sets';

import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import {
  ArrowLeftOutlined,
  DeleteOutlined,
  EditOutlined,
  FileImageOutlined,
  FileTextOutlined,
  PlusOutlined,
  UploadOutlined,
} from '@ant-design/icons-vue';
import {
  Button,
  Card,
  Form,
  FormItem,
  Image,
  Input,
  message,
  Modal,
  Popconfirm,
  Space,
  Spin,
  Switch,
  Table,
  Tabs,
  Tag,
  Textarea,
  Tooltip,
  Upload,
} from 'ant-design-vue';

import { uploadImageApi, uploadImagesApi } from '#/api/core/files';
import {
  createTestCaseApi,
  deleteTestCaseApi,
  importTestCasesApi,
  listTestCasesApi,
  toggleTestCaseEnabledApi,
  updateTestCaseApi,
} from '#/api/core/test-cases';
import { getTestSetByCodeApi } from '#/api/core/test-sets';

const { TabPane } = Tabs as any;

const route = useRoute();
const router = useRouter();

// ==================== 状态 ====================

const testSetCode = computed(() => route.params.code as string);
const testSet = ref<null | TestSetApi.TestSetItem>(null);
const loading = ref(false);
const dataLoading = ref(false);
const dataSource = ref<TestCaseApi.TestCaseItem[]>([]);

const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0,
});

const filters = reactive({
  keyword: '',
});

// 根据测试集类型动态生成列
const columns = computed(() => {
  const isImage = testSet.value?.type === 'image';

  const baseCols = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      width: 200,
      ellipsis: true,
    },
  ];

  const contentCol = isImage
    ? {
        title: '图片',
        dataIndex: 'image_url',
        key: 'image_url',
        width: 120,
      }
    : {
        title: '内容预览',
        dataIndex: 'content',
        key: 'content',
        ellipsis: true,
      };

  return [
    ...baseCols,
    contentCol,
    { title: '启用', dataIndex: 'enabled', key: 'enabled', width: 90 },
    {
      title: '创建时间',
      dataIndex: 'create_time',
      key: 'create_time',
      width: 170,
    },
    { title: '操作', key: 'action', width: 150, fixed: 'right' as const },
  ];
});

// ==================== 表单弹窗 ====================

const modalVisible = ref(false);
const isSubmitting = ref(false);
const editing = ref<null | TestCaseApi.TestCaseItem>(null);

const formState = reactive<{
  content: string;
  enabled: number;
  image_url: string;
  title: string;
}>({
  title: '',
  content: '',
  image_url: '',
  enabled: 1,
});

const modalTitle = computed(() =>
  editing.value ? '编辑测试案例' : '新增测试案例',
);

// ==================== 导入弹窗 ====================

const importModalVisible = ref(false);
const importSubmitting = ref(false);
const importMode = ref<'file' | 'image' | 'json'>('json');
const importForm = reactive({
  enabled: 1,
  items: [] as TestCaseApi.ImportItem[],
});
const importJsonText = ref('');
const importPreview = ref('');

// 图片上传相关（批量导入）
const imageUploadList = ref<File[]>([]);
const imageUploading = ref(false);

// 单个图片上传（新增/编辑表单）
const formImageFile = ref<File | null>(null);
const formImagePreview = ref<string>('');
const formImageUploading = ref(false);

const importJsonPlaceholder = computed(() => {
  if (testSet.value?.type === 'image') {
    return `粘贴 JSON 数组，格式：
[{"title":"标题","image_url":"https://..."}, ...]
或简单数组：
["https://img1.jpg", "https://img2.jpg", ...]`;
  }
  return `粘贴 JSON 数组，格式：
[{"title":"标题","content":"内容"}, ...]
或简单字符串数组：
["内容1", "内容2", ...]`;
});

// ==================== API 调用 ====================

async function fetchTestSet() {
  loading.value = true;
  try {
    testSet.value = await getTestSetByCodeApi(testSetCode.value);
  } catch (error: unknown) {
    message.error((error as Error)?.message || '加载测试集失败');
    router.push('/keyword_corpus/test_case');
  } finally {
    loading.value = false;
  }
}

async function fetchList() {
  dataLoading.value = true;
  try {
    const res = await listTestCasesApi({
      test_set_code: testSetCode.value,
      page: pagination.current,
      page_size: pagination.pageSize,
      keyword: filters.keyword || undefined,
    });
    dataSource.value = res.items;
    pagination.total = res.total;
  } catch (error: unknown) {
    message.error((error as Error)?.message || '加载失败');
  } finally {
    dataLoading.value = false;
  }
}

function goBack() {
  router.push('/keyword_corpus/test_case');
}

function openCreate() {
  editing.value = null;
  Object.assign(formState, {
    title: '',
    content: '',
    image_url: '',
    enabled: 1,
  });
  // 重置图片上传状态
  formImageFile.value = null;
  formImagePreview.value = '';
  modalVisible.value = true;
}

function openEdit(record: TestCaseApi.TestCaseItem) {
  editing.value = record;
  Object.assign(formState, {
    title: record.title || '',
    content: record.content || '',
    image_url: record.image_url || '',
    enabled: record.enabled,
  });
  // 重置图片上传状态，但保留已有图片预览
  formImageFile.value = null;
  formImagePreview.value = record.image_url || '';
  modalVisible.value = true;
}

// 表单中选择图片
function handleFormImageChange(info: UploadChangeParam) {
  const file = info.file.originFileObj;
  if (file) {
    formImageFile.value = file as unknown as File;
    // 生成预览
    const reader = new FileReader();
    reader.addEventListener('load', (e) => {
      formImagePreview.value = e.target?.result as string;
    });
    reader.readAsDataURL(file);
  }
}

// 移除已选图片
function removeFormImage() {
  formImageFile.value = null;
  formImagePreview.value = '';
  formState.image_url = '';
}

async function submit() {
  const isImage = testSet.value?.type === 'image';
  const content = formState.content.trim();

  // 图片类型：需要已上传的图片或新选择的图片
  if (isImage) {
    if (!formImageFile.value && !formState.image_url) {
      message.warning('请上传图片');
      return;
    }
  } else if (!content) {
    message.warning('请输入测试内容');
    return;
  }

  isSubmitting.value = true;
  try {
    let imageUrl = formState.image_url;

    // 如果有新选择的图片，先上传
    if (isImage && formImageFile.value) {
      formImageUploading.value = true;
      try {
        const res = await uploadImageApi(formImageFile.value);
        const data = res as unknown as { url: string };
        imageUrl = data.url;
      } catch {
        message.error('图片上传失败');
        return;
      } finally {
        formImageUploading.value = false;
      }
    }

    if (editing.value) {
      await updateTestCaseApi(editing.value.id, {
        title: formState.title?.trim() || undefined,
        content: isImage ? undefined : content,
        image_url: isImage ? imageUrl : undefined,
        enabled: formState.enabled,
      });
      message.success('更新成功');
    } else {
      await createTestCaseApi({
        test_set_code: testSetCode.value,
        title: formState.title?.trim() || undefined,
        content: isImage ? undefined : content,
        image_url: isImage ? imageUrl : undefined,
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

async function toggleEnabled(record: TestCaseApi.TestCaseItem) {
  try {
    const updated = await toggleTestCaseEnabledApi(record.id);
    record.enabled = updated.enabled;
    message.success('已更新');
  } catch (error: unknown) {
    message.error((error as Error)?.message || '更新失败');
  }
}

async function remove(record: TestCaseApi.TestCaseItem) {
  try {
    await deleteTestCaseApi(record.id);
    message.success('删除成功');
    await fetchList();
  } catch (error: unknown) {
    message.error((error as Error)?.message || '删除失败');
  }
}

function onTableChange(p: { current?: number; pageSize?: number }) {
  pagination.current = p.current ?? 1;
  pagination.pageSize = p.pageSize ?? 20;
  fetchList();
}

function resetFilters() {
  filters.keyword = '';
  pagination.current = 1;
  fetchList();
}

// ==================== 导入功能 ====================

function openImportModal() {
  importForm.enabled = 1;
  importForm.items = [];
  importJsonText.value = '';
  importPreview.value = '';
  imageUploadList.value = [];
  // 图片类型默认使用图片上传模式
  importMode.value = testSet.value?.type === 'image' ? 'image' : 'json';
  importModalVisible.value = true;
}

// 图片上传处理
function handleImageUploadChange(info: UploadChangeParam) {
  const fileList = info.fileList || [];
  const files: File[] = [];
  for (const f of fileList) {
    if (f.originFileObj) {
      files.push(f.originFileObj as unknown as File);
    }
  }
  imageUploadList.value = files;
  importPreview.value = files.length > 0 ? `已选择 ${files.length} 张图片` : '';
}

async function uploadImages() {
  if (imageUploadList.value.length === 0) {
    message.warning('请先选择图片');
    return;
  }

  imageUploading.value = true;
  try {
    const res = await uploadImagesApi(imageUploadList.value);
    const data = res as unknown as {
      error_count: number;
      results: { filename: string; url: string }[];
      success_count: number;
    };

    if (data.success_count > 0) {
      // 将上传成功的图片转换为导入项
      importForm.items = data.results.map(
        (r: { filename: string; url: string }) => ({
          title: r.filename || '',
          image_url: r.url,
          content: '',
        }),
      );
      importPreview.value = `已上传 ${data.success_count} 张图片`;
      message.success(`成功上传 ${data.success_count} 张图片`);
    }

    if (data.error_count > 0) {
      message.warning(`${data.error_count} 张图片上传失败`);
    }
  } catch (error) {
    message.error('图片上传失败');
    console.error(error);
  } finally {
    imageUploading.value = false;
  }
}

function parseJsonText() {
  const text = importJsonText.value.trim();
  if (!text) {
    message.warning('请输入 JSON 内容');
    return;
  }

  const isImage = testSet.value?.type === 'image';

  try {
    const data = JSON.parse(text);
    const items = Array.isArray(data) ? data : [data];

    importForm.items = items.map(
      (
        item: string | { content?: string; image_url?: string; title?: string },
      ) => {
        if (typeof item === 'string') {
          return isImage
            ? { title: '', image_url: item }
            : { title: '', content: item };
        }
        return {
          title: item.title || '',
          content: item.content || '',
          image_url: item.image_url || '',
        };
      },
    );

    // 过滤空内容
    importForm.items = importForm.items.filter((item) =>
      isImage ? item.image_url?.trim() : item.content?.trim(),
    );

    if (importForm.items.length === 0) {
      message.warning('没有解析到有效的测试案例');
      return;
    }

    importPreview.value = `已解析 ${importForm.items.length} 条测试案例`;
    message.success(`成功解析 ${importForm.items.length} 条`);
  } catch {
    message.error('JSON 格式错误，请检查');
  }
}

async function handleFileChange(info: UploadChangeParam) {
  const file = info.file.originFileObj;
  if (!file) return;

  const isImage = testSet.value?.type === 'image';

  try {
    const text = await file.text();
    const fileName = file.name.toLowerCase();

    if (fileName.endsWith('.json')) {
      const data = JSON.parse(text);
      const items = Array.isArray(data) ? data : [data];
      importForm.items = items.map(
        (item: { content?: string; image_url?: string; title?: string }) => ({
          title: item.title || '',
          content: item.content || '',
          image_url: item.image_url || '',
        }),
      );
    } else if (fileName.endsWith('.csv') || fileName.endsWith('.txt')) {
      const lines = text
        .split('\n')
        .map((l) => l.trim())
        .filter(Boolean);
      importForm.items = lines.map((line) =>
        isImage ? { title: '', image_url: line } : { title: '', content: line },
      );
    } else {
      message.warning('请上传 .json / .csv / .txt 文件');
      return;
    }

    importPreview.value = `已解析 ${importForm.items.length} 条测试案例`;
  } catch {
    message.error('文件解析失败，请检查格式');
  }
}

async function submitImport() {
  if (importForm.items.length === 0) {
    message.warning('请先解析数据');
    return;
  }

  const isImage = testSet.value?.type === 'image';
  const validItems = importForm.items.filter((item) =>
    isImage ? item.image_url?.trim() : item.content?.trim(),
  );

  if (validItems.length === 0) {
    message.warning('没有有效的测试案例');
    return;
  }

  importSubmitting.value = true;
  try {
    const res = await importTestCasesApi({
      test_set_code: testSetCode.value,
      items: validItems,
      enabled: importForm.enabled,
    });
    message.success(
      `导入完成：成功 ${res.success_count} 条，跳过重复 ${res.skip_count} 条`,
    );
    importModalVisible.value = false;
    await fetchList();
  } catch (error: unknown) {
    message.error((error as Error)?.message || '导入失败');
  } finally {
    importSubmitting.value = false;
  }
}

// ==================== 生命周期 ====================

watch(testSetCode, async () => {
  if (testSetCode.value) {
    await fetchTestSet();
    await fetchList();
  }
});

onMounted(async () => {
  if (testSetCode.value) {
    await fetchTestSet();
    await fetchList();
  }
});
</script>

<template>
  <div class="test-case-detail-page">
    <Spin :spinning="loading">
      <!-- 顶部信息栏 -->
      <Card :bordered="false" class="header-card">
        <div class="header-content">
          <div class="header-left">
            <Button type="text" class="back-btn" @click="goBack">
              <template #icon><ArrowLeftOutlined /></template>
              返回
            </Button>
            <div v-if="testSet" class="test-set-info">
              <div class="info-icon" :class="testSet.type">
                <FileTextOutlined v-if="testSet.type === 'text'" />
                <FileImageOutlined v-else />
              </div>
              <div class="info-text">
                <div class="info-name">{{ testSet.name }}</div>
                <div class="info-meta">
                  <Tag :color="testSet.type === 'text' ? 'blue' : 'purple'">
                    {{ testSet.type === 'text' ? '文本' : '图片' }}
                  </Tag>
                  <span class="info-code">{{ testSet.code }}</span>
                  <span v-if="testSet.description" class="info-desc">
                    {{ testSet.description }}
                  </span>
                </div>
              </div>
            </div>
          </div>
          <div class="header-actions">
            <Space>
              <Button type="primary" @click="openCreate">
                <template #icon><PlusOutlined /></template>
                新增案例
              </Button>
              <Button @click="openImportModal">
                <template #icon><UploadOutlined /></template>
                批量导入
              </Button>
            </Space>
          </div>
        </div>
      </Card>

      <!-- 列表 -->
      <Card :bordered="false">
        <Form layout="inline" style="margin-bottom: 12px">
          <FormItem label="搜索">
            <Input
              v-model:value="filters.keyword"
              allow-clear
              placeholder="支持标题/内容搜索"
              style="width: 200px"
              @press-enter="fetchList"
            />
          </FormItem>
          <FormItem>
            <Space>
              <Button type="primary" @click="fetchList">查询</Button>
              <Button @click="resetFilters">重置</Button>
            </Space>
          </FormItem>
        </Form>

        <Table
          :columns="columns"
          :data-source="dataSource"
          :loading="dataLoading"
          row-key="id"
          :scroll="{ x: 1000 }"
          :pagination="{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
            showTotal: (t: number) => `共 ${t} 条`,
          }"
          @change="onTableChange"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'image_url'">
              <Image
                v-if="record.image_url"
                :src="record.image_url"
                :width="60"
                :height="60"
                style="object-fit: cover; border-radius: 4px"
                :preview="{ src: record.image_url }"
              />
              <span v-else class="text-muted">-</span>
            </template>
            <template v-else-if="column.key === 'content'">
              <Tooltip :title="record.content" placement="topLeft">
                <span class="content-preview">
                  {{ (record.content || '').slice(0, 80)
                  }}{{ (record.content || '').length > 80 ? '...' : '' }}
                </span>
              </Tooltip>
            </template>
            <template v-else-if="column.key === 'enabled'">
              <Switch
                :checked="record.enabled === 1"
                checked-children="启用"
                un-checked-children="禁用"
                @change="
                  () => toggleEnabled(record as TestCaseApi.TestCaseItem)
                "
              />
            </template>
            <template v-else-if="column.key === 'action'">
              <Space>
                <Button
                  size="small"
                  @click="openEdit(record as TestCaseApi.TestCaseItem)"
                >
                  <template #icon><EditOutlined /></template>
                </Button>
                <Popconfirm
                  title="确定删除该测试案例？"
                  @confirm="remove(record as TestCaseApi.TestCaseItem)"
                >
                  <Button danger size="small">
                    <template #icon><DeleteOutlined /></template>
                  </Button>
                </Popconfirm>
              </Space>
            </template>
          </template>
        </Table>
      </Card>
    </Spin>

    <!-- 新增/编辑弹窗 -->
    <Modal
      v-model:open="modalVisible"
      :confirm-loading="isSubmitting || formImageUploading"
      :title="modalTitle"
      :width="640"
      @ok="submit"
    >
      <Form layout="vertical">
        <FormItem label="标题">
          <Input
            v-model:value="formState.title"
            placeholder="可选，用于标识测试案例"
          />
        </FormItem>
        <FormItem v-if="testSet?.type === 'image'" label="上传图片" required>
          <div class="form-image-upload">
            <!-- 已有图片预览 -->
            <div v-if="formImagePreview" class="form-image-preview">
              <Image
                :src="formImagePreview"
                :width="120"
                :height="120"
                style="object-fit: cover; border-radius: 8px"
              />
              <Button
                class="remove-image-btn"
                danger
                size="small"
                type="text"
                @click="removeFormImage"
              >
                <template #icon><DeleteOutlined /></template>
                移除
              </Button>
            </div>
            <!-- 上传按钮 -->
            <Upload
              v-else
              :before-upload="() => false"
              :max-count="1"
              :show-upload-list="false"
              accept="image/*"
              @change="handleFormImageChange"
            >
              <div class="form-upload-trigger">
                <PlusOutlined style="font-size: 24px; color: #999" />
                <div style="margin-top: 8px; color: #666">点击上传图片</div>
              </div>
            </Upload>
            <div class="upload-hint">支持 jpg、png、gif、webp，最大 10MB</div>
          </div>
        </FormItem>
        <FormItem v-else label="测试内容" required>
          <Textarea
            v-model:value="formState.content"
            :rows="8"
            placeholder="输入需要测试的文本内容..."
          />
        </FormItem>
        <FormItem label="启用">
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

    <!-- 批量导入弹窗 -->
    <Modal
      v-model:open="importModalVisible"
      :confirm-loading="importSubmitting"
      title="批量导入测试案例"
      :width="700"
      @ok="submitImport"
    >
      <Form layout="vertical">
        <FormItem label="启用状态">
          <Switch
            :checked="importForm.enabled === 1"
            checked-children="启用"
            un-checked-children="禁用"
            @change="
              (checked: boolean | string | number) =>
                (importForm.enabled = checked ? 1 : 0)
            "
          />
        </FormItem>

        <Tabs v-model:active-key="importMode" class="import-tabs">
          <!-- 图片上传 Tab（仅图片类型测试集显示） -->
          <TabPane v-if="testSet?.type === 'image'" key="image" tab="图片上传">
            <div class="image-upload-section">
              <Upload
                :before-upload="() => false"
                :max-count="20"
                :multiple="true"
                accept="image/*"
                list-type="picture-card"
                @change="handleImageUploadChange"
              >
                <div>
                  <PlusOutlined />
                  <div style="margin-top: 8px">选择图片</div>
                </div>
              </Upload>
              <div class="upload-hint">
                支持 jpg、png、gif、webp 格式，单张最大 10MB，最多 20 张
              </div>
              <Button
                type="primary"
                :loading="imageUploading"
                :disabled="imageUploadList.length === 0"
                class="upload-btn"
                @click="uploadImages"
              >
                <template #icon><UploadOutlined /></template>
                上传到云存储
              </Button>
            </div>
          </TabPane>

          <TabPane key="json" tab="JSON 文本">
            <div class="json-input-section">
              <Textarea
                v-model:value="importJsonText"
                :rows="10"
                :placeholder="importJsonPlaceholder"
              />
              <Button type="primary" class="parse-btn" @click="parseJsonText">
                解析 JSON
              </Button>
            </div>
          </TabPane>

          <TabPane key="file" tab="文件上传">
            <Upload
              :before-upload="() => false"
              :max-count="1"
              accept=".json,.csv,.txt"
              @change="handleFileChange"
            >
              <Button>
                <template #icon><UploadOutlined /></template>
                选择文件
              </Button>
            </Upload>
            <div class="upload-hint">支持 JSON / CSV / TXT 格式</div>
          </TabPane>
        </Tabs>

        <FormItem v-if="importPreview" label="解析结果" class="mt-4">
          <Tag color="green">{{ importPreview }}</Tag>
        </FormItem>
        <FormItem v-if="importForm.items.length > 0" label="预览前 5 条">
          <div class="import-preview-list">
            <div
              v-for="(item, index) in importForm.items.slice(0, 5)"
              :key="index"
              class="preview-item"
            >
              <span class="preview-index">#{{ index + 1 }}</span>
              <span v-if="testSet?.type === 'image'" class="preview-content">
                {{ (item.image_url || '').slice(0, 50) }}...
              </span>
              <span v-else class="preview-content">
                {{ (item.content || '').slice(0, 60)
                }}{{ (item.content || '').length > 60 ? '...' : '' }}
              </span>
            </div>
            <div v-if="importForm.items.length > 5" class="preview-more">
              ... 还有 {{ importForm.items.length - 5 }} 条
            </div>
          </div>
        </FormItem>
      </Form>
    </Modal>
  </div>
</template>

<style scoped>
.test-case-detail-page {
  min-height: 100%;
  padding: 20px;
  background: hsl(var(--background));
}

.header-card {
  margin-bottom: 20px;
}

.header-content {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
  justify-content: space-between;
}

.header-left {
  display: flex;
  gap: 16px;
  align-items: center;
}

.back-btn {
  color: hsl(var(--muted-foreground));
}

.test-set-info {
  display: flex;
  gap: 16px;
  align-items: center;
  padding-left: 16px;
  border-left: 1px solid hsl(var(--border));
}

.info-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  font-size: 24px;
  border-radius: 12px;
}

.info-icon.text {
  color: hsl(217deg 91% 60%);
  background: hsl(217deg 91% 60% / 15%);
}

.info-icon.image {
  color: hsl(270deg 70% 60%);
  background: hsl(270deg 70% 60% / 15%);
}

.info-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-name {
  font-size: 18px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.info-meta {
  display: flex;
  gap: 12px;
  align-items: center;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.info-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, monospace;
}

.info-desc {
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.content-preview {
  display: block;
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.text-muted {
  color: hsl(var(--muted-foreground));
}

.upload-hint {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.6;
  color: hsl(var(--muted-foreground));
}

.import-preview-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 200px;
  overflow-y: auto;
}

.preview-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 8px 12px;
  background: hsl(var(--muted) / 50%);
  border-radius: 6px;
}

.preview-index {
  flex-shrink: 0;
  font-family: monospace;
  font-weight: 600;
  color: hsl(var(--primary));
}

.preview-content {
  font-size: 13px;
  line-height: 1.4;
  color: hsl(var(--foreground));
  word-break: break-all;
}

.preview-more {
  padding: 8px 12px;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.import-tabs {
  margin-top: 8px;
}

.json-input-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.parse-btn {
  align-self: flex-start;
}

.mt-4 {
  margin-top: 16px;
}

.preview-wrap {
  margin-top: 8px;
}

.image-upload-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.upload-btn {
  align-self: flex-start;
  margin-top: 8px;
}

.image-upload-section :deep(.ant-upload-list-picture-card) {
  max-height: 300px;
  overflow-y: auto;
}

.form-image-upload {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-image-preview {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
}

.remove-image-btn {
  padding: 0;
}

.form-upload-trigger {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 120px;
  height: 120px;
  cursor: pointer;
  border: 1px dashed hsl(var(--border));
  border-radius: 8px;
  transition: border-color 0.2s;
}

.form-upload-trigger:hover {
  border-color: hsl(var(--primary));
}
</style>
