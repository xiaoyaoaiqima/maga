<script setup lang="ts">
// @ts-nocheck
import { onMounted, ref } from 'vue';

import { formatDateTime } from '@vben/utils';

import {
  Button,
  Card,
  Drawer,
  message,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import { ABTestApi } from '#/api/core/ab-test';

import ABTestDetail from './components/ABTestDetail.vue';

const { Option: SelectOption } = Select as { Option: unknown };

// 状态
const loading = ref(false);
const testList = ref<ABTestApi.ABTestResponse[]>([]);
const filterType = ref<ABTestApi.TestType>();
const filterStatus = ref<ABTestApi.TestStatus>();
const analyzing = ref<string>();

// 详情
const detailVisible = ref(false);
const currentTest = ref<ABTestApi.ABTestResponse>();

// 分页
const pagination = ref({
  current: 1,
  pageSize: 20,
  total: 0,
  showTotal: (total: number) => `共 ${total} 条`,
});

// 表格列
const columns = [
  {
    title: '测试名称',
    dataIndex: 'test_name',
    key: 'test_name',
    width: 250,
  },
  {
    title: '测试类型',
    dataIndex: 'test_type',
    key: 'test_type',
    width: 120,
  },
  {
    title: '对比组',
    key: 'groups_info',
    width: 280,
  },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    width: 100,
  },
  {
    title: '样本数量',
    key: 'sample_count',
    width: 140,
  },
  {
    title: '创建时间',
    dataIndex: 'create_time',
    key: 'create_time',
    width: 180,
  },
  {
    title: '操作',
    key: 'action',
    width: 180,
    fixed: 'right' as const,
  },
];

// 组颜色映射
const groupColors = ['blue', 'green', 'orange', 'purple', 'cyan', 'magenta'];

function getGroupColor(groupName: string): string {
  const index =
    groupName === 'control' ? 0 : ((groupName.codePointAt(0) ?? 0) % 5) + 1;
  return groupColors[index] || 'default';
}

// 获取总调试历史数量
function getTotalDebugHistories(record: ABTestApi.ABTestResponse): number {
  if (!record.debug_history_ids) return 0;
  return Object.values(record.debug_history_ids).reduce(
    (sum, ids) => sum + ids.length,
    0,
  );
}

// 获取总Job数量
function getTotalJobs(record: ABTestApi.ABTestResponse): number {
  if (!record.job_ids) return 0;
  return Object.keys(record.job_ids).length;
}

// 检查测试是否有数据（可以进行分析）
function hasTestData(record: ABTestApi.ABTestResponse): boolean {
  if (record.test_type === 'EXPERT_CONFIG') {
    return getTotalDebugHistories(record) > 0;
  }
  return getTotalJobs(record) > 0;
}

// 获取AB测试列表
async function fetchABTests() {
  loading.value = true;
  try {
    const res = await ABTestApi.listABTests({
      page: pagination.value.current,
      page_size: pagination.value.pageSize,
      test_type: filterType.value,
      status: filterStatus.value,
    });
    testList.value = res.items;
    pagination.value.total = res.total;
  } catch (error: unknown) {
    message.error((error as Error)?.message || '获取列表失败');
  } finally {
    loading.value = false;
  }
}

// 筛选变化
function handleFilterChange() {
  pagination.value.current = 1;
  fetchABTests();
}

// 表格变化
function handleTableChange(pag: { current: number; pageSize: number }) {
  pagination.value.current = pag.current;
  pagination.value.pageSize = pag.pageSize;
  fetchABTests();
}

// 查看详情
function viewDetail(testId: string) {
  const test = testList.value.find((t) => t.test_id === testId);
  if (test) {
    currentTest.value = test;
    detailVisible.value = true;
  }
}

// 分析测试
async function analyzeTest(testId: string) {
  analyzing.value = testId;
  try {
    await ABTestApi.analyzeTest(testId);
    message.success('分析已完成');
    await fetchABTests();
  } catch (error: unknown) {
    message.error((error as Error)?.message || '分析失败');
  } finally {
    analyzing.value = undefined;
  }
}

// 删除测试
async function deleteTest(testId: string) {
  try {
    await ABTestApi.deleteABTest(testId);
    message.success('删除成功');
    await fetchABTests();
  } catch (error: unknown) {
    message.error((error as Error)?.message || '删除失败');
  }
}

// 初始化
onMounted(() => {
  fetchABTests();
});
</script>

<template>
  <div class="ab-test-records-page">
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
          AB测试记录
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">测试类型</span>
          <Select
            v-model:value="filterType"
            placeholder="测试类型"
            style="width: 150px"
            allow-clear
            @change="handleFilterChange"
          >
            <SelectOption value="EXPERT_CONFIG">Expert对比</SelectOption>
            <SelectOption value="AGENT_JOB">Job对比</SelectOption>
          </Select>
        </div>
        <div class="filter-item">
          <span class="filter-label">状态</span>
          <Select
            v-model:value="filterStatus"
            placeholder="状态"
            style="width: 120px"
            allow-clear
            @change="handleFilterChange"
          >
            <SelectOption value="pending">待执行</SelectOption>
            <SelectOption value="running">执行中</SelectOption>
            <SelectOption value="analyzing">分析中</SelectOption>
            <SelectOption value="completed">已完成</SelectOption>
            <SelectOption value="failed">失败</SelectOption>
          </Select>
        </div>
        <div class="filter-actions">
          <Button @click="fetchABTests">刷新</Button>
        </div>
      </div>
    </div>

    <Card class="mb-4">
      <Table
        :columns="columns"
        :data-source="testList"
        :loading="loading"
        :pagination="pagination"
        :scroll="{ x: 1400 }"
        row-key="id"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'test_name'">
            <div class="test-name-cell">
              <a @click="viewDetail(record.test_id)">
                <strong>{{ record.test_name }}</strong>
              </a>
              <div class="test-id">{{ record.test_id }}</div>
            </div>
          </template>

          <template v-else-if="column.key === 'test_type'">
            <Tag v-if="record.test_type === 'EXPERT_CONFIG'" color="blue">
              Expert对比
            </Tag>
            <Tag v-else color="green">Job对比</Tag>
          </template>

          <template v-else-if="column.key === 'groups_info'">
            <div class="groups-info">
              <Tooltip
                v-for="group in record.groups"
                :key="group.group_name"
                :title="group.description"
                placement="top"
              >
                <Tag :color="getGroupColor(group.group_name)">
                  {{ group.group_name }}
                  <!-- Expert对比显示短描述，Job对比只显示组名 -->
                  <span
                    v-if="
                      group.description && record.test_type === 'EXPERT_CONFIG'
                    "
                    class="group-desc"
                  >
                    ({{ group.description }})
                  </span>
                </Tag>
              </Tooltip>
            </div>
          </template>

          <template v-else-if="column.key === 'status'">
            <Tag v-if="record.status === 'pending'" color="default">
              待执行
            </Tag>
            <Tag v-else-if="record.status === 'running'" color="processing">
              执行中
            </Tag>
            <Tag v-else-if="record.status === 'analyzing'" color="processing">
              分析中
            </Tag>
            <Tag v-else-if="record.status === 'completed'" color="success">
              已完成
            </Tag>
            <Tag v-else-if="record.status === 'failed'" color="error">
              失败
            </Tag>
          </template>

          <template v-else-if="column.key === 'sample_count'">
            <div class="sample-count">
              <template v-if="record.test_type === 'EXPERT_CONFIG'">
                {{ getTotalDebugHistories(record) }} 个调试记录
              </template>
              <template v-else> {{ getTotalJobs(record) }} 个Job </template>
            </div>
          </template>

          <template v-else-if="column.key === 'create_time'">
            {{ formatDateTime(record.create_time) }}
          </template>

          <template v-else-if="column.key === 'action'">
            <Space>
              <Button
                type="link"
                size="small"
                @click="viewDetail(record.test_id)"
              >
                查看详情
              </Button>
              <Button
                v-if="record.status === 'pending' && hasTestData(record)"
                type="link"
                size="small"
                :loading="analyzing === record.test_id"
                @click="analyzeTest(record.test_id)"
              >
                分析
              </Button>
              <Tag v-if="record.status === 'running'" color="processing">
                执行中...
              </Tag>
              <Popconfirm
                title="确定删除此测试吗？"
                @confirm="deleteTest(record.test_id)"
              >
                <Button type="link" size="small" danger>删除</Button>
              </Popconfirm>
            </Space>
          </template>
        </template>
      </Table>
    </Card>

    <!-- 详情抽屉 -->
    <Drawer
      v-model:open="detailVisible"
      title="AB测试详情"
      :width="1000"
      placement="right"
    >
      <ABTestDetail
        v-if="currentTest"
        :test-id="currentTest.test_id"
        @close="detailVisible = false"
      />
    </Drawer>
  </div>
</template>

<style scoped>
.ab-test-records-page {
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

.test-name-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.test-id {
  font-family: Monaco, Consolas, monospace;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.groups-info {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.group-desc {
  font-size: 11px;
  opacity: 0.8;
}

.sample-count {
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.text-muted {
  color: hsl(var(--muted-foreground));
}
</style>
