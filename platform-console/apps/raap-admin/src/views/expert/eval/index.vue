<script setup lang="ts">
// @ts-nocheck
import type { ExpertEvalApi } from '#/api/core/expert-debug';

import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import { formatDateTime } from '@vben/utils';

import * as Antd from 'ant-design-vue';

import {
  getEvalResultDetailApi,
  listEvalResultsApi,
  listEvalRunsApi,
  listTestSetOptionsApi,
} from '#/api/core/expert-debug';
import MonacoEditor from '#/components/MonacoEditor.vue';

const {
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Input,
  message,
  Row,
  Select,
  Table,
  Tag,
} = Antd as any;
const { Item: DescriptionsItem } = Descriptions as any;

const route = useRoute();

const loadingRuns = ref(false);
const loadingResults = ref(false);

// 测试集筛选
const testSetOptions = ref<ExpertEvalApi.TestSetOption[]>([]);
const selectedTestSetCode = ref<string | undefined>(undefined);

const runs = ref<ExpertEvalApi.EvalRunItem[]>([]);
const selectedRunId = ref<number | undefined>(undefined);
const pollTimer = ref<null | number>(null);

const resultPagination = ref({
  current: 1,
  pageSize: 20,
  total: 0,
  showSizeChanger: true,
  showTotal: (t: number) => `共 ${t} 条`,
});

const results = ref<ExpertEvalApi.EvalResultItem[]>([]);

const detailOpen = ref(false);
const detailLoading = ref(false);
const selectedResult = ref<ExpertEvalApi.EvalResultDetail | null>(null);

const runOptions = computed(() =>
  runs.value.map((r) => ({
    value: r.id,
    label: `${r.run_code} | ${r.expert_config_code} | ${r.status} | ${r.success_count}/${r.total_count}`,
  })),
);

const selectedRun = computed(() => {
  if (!selectedRunId.value) return null;
  return runs.value.find((r) => r.id === selectedRunId.value) || null;
});

function stopPolling() {
  if (pollTimer.value) {
    window.clearInterval(pollTimer.value);
    pollTimer.value = null;
  }
}

function startPollingIfNeeded() {
  stopPolling();
  if (!selectedRun.value) return;
  if (selectedRun.value.status !== 'running') return;

  pollTimer.value = window.setInterval(async () => {
    await fetchRuns();
    await fetchResults();
  }, 2000);
}

async function fetchTestSetOptions() {
  try {
    const resp = await listTestSetOptionsApi();
    testSetOptions.value = resp || [];
  } catch (error: any) {
    console.error('获取测试集选项失败', error);
  }
}

async function fetchRuns() {
  loadingRuns.value = true;
  try {
    const resp = await listEvalRunsApi({
      page: 1,
      page_size: 50,
      test_set_code: selectedTestSetCode.value || undefined,
    });
    runs.value = resp.items || [];
  } catch (error: any) {
    message.error(error?.message || '获取 run 列表失败');
  } finally {
    loadingRuns.value = false;
  }
}

async function fetchResults() {
  if (!selectedRunId.value) return;
  loadingResults.value = true;
  try {
    const resp = await listEvalResultsApi({
      run_id: selectedRunId.value,
      page: resultPagination.value.current,
      page_size: resultPagination.value.pageSize,
    });
    results.value = resp.items || [];
    resultPagination.value.total = resp.total || 0;
  } catch (error: any) {
    message.error(error?.message || '获取结果失败');
  } finally {
    loadingResults.value = false;
  }
}

async function openResultDetail(record: ExpertEvalApi.EvalResultItem) {
  detailOpen.value = true;
  detailLoading.value = true;
  selectedResult.value = null;
  try {
    const detail = await getEvalResultDetailApi(record.id);
    selectedResult.value = detail;
  } catch (error: any) {
    message.error(error?.message || '获取详情失败');
  } finally {
    detailLoading.value = false;
  }
}

async function copyText(text?: null | string) {
  try {
    await navigator.clipboard.writeText(text ?? '');
    message.success('已复制');
  } catch {
    message.error('复制失败（浏览器权限限制）');
  }
}

function handleResultTableChange(pag: any) {
  resultPagination.value.current = pag.current || 1;
  resultPagination.value.pageSize = pag.pageSize || 20;
  fetchResults();
}

const columns = [
  { title: '状态', key: 'success', width: 80 },
  { title: '分数', dataIndex: 'score', key: 'score', width: 70 },
  { title: '问题种类', key: 'problem_tags', width: 160 },
  { title: '原文摘录', key: 'problem_snippets', ellipsis: true },
  { title: '评语', dataIndex: 'reason', key: 'reason', ellipsis: true },
  { title: '耗时(ms)', dataIndex: 'latency_ms', key: 'latency_ms', width: 100 },
  {
    title: '模型',
    dataIndex: 'model_code',
    key: 'model_code',
    width: 120,
    ellipsis: true,
  },
  { title: '时间', dataIndex: 'create_time', key: 'create_time', width: 160 },
];

onMounted(async () => {
  await fetchTestSetOptions();
  await fetchRuns();

  const runIdFromQuery = route.query.run_id
    ? Number(route.query.run_id)
    : undefined;
  if (runIdFromQuery) {
    selectedRunId.value = runIdFromQuery;
    await fetchResults();
    startPollingIfNeeded();
  }
});

watch(selectedTestSetCode, async () => {
  selectedRunId.value = undefined;
  resultPagination.value.current = 1;
  results.value = [];
  await fetchRuns();
});

watch(selectedRunId, async () => {
  resultPagination.value.current = 1;
  await fetchResults();
  startPollingIfNeeded();
});

watch(
  () => selectedRun.value?.status,
  () => {
    startPollingIfNeeded();
  },
);

onUnmounted(() => stopPolling());
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
          {{ route.meta.title || '批量评分结果' }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">测试集</span>
          <Select
            v-model:value="selectedTestSetCode"
            :options="
              testSetOptions.map((t) => ({
                value: t.code,
                label: `${t.name} (${t.case_count ?? 0})`,
              }))
            "
            placeholder="按测试集筛选"
            style="width: 200px"
            allow-clear
            show-search
            option-filter-prop="label"
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">Run</span>
          <Select
            v-model:value="selectedRunId"
            :options="runOptions"
            placeholder="选择一个 run 查看结果"
            style="width: 560px"
            show-search
            option-filter-prop="label"
          />
        </div>
        <div class="filter-actions">
          <Button :loading="loadingRuns" @click="fetchRuns"> 刷新 </Button>
        </div>
      </div>
    </div>

    <Row :gutter="16">
      <Col :span="24">
        <Card size="small">
          <div v-if="selectedRun" class="mb-3 text-xs text-muted-foreground">
            当前状态：{{ selectedRun.status }}（{{
              selectedRun.success_count
            }}/{{ selectedRun.total_count }}）
            <span v-if="selectedRun.status === 'running'"
              >，每 2 秒自动刷新</span
            >
          </div>

          <Table
            :columns="columns"
            :data-source="results"
            :loading="loadingResults"
            :pagination="resultPagination"
            row-key="id"
            size="small"
            @change="handleResultTableChange"
            :custom-row="
              (record: any) => ({ onClick: () => openResultDetail(record) })
            "
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'success'">
                <Tag :color="record.success ? 'green' : 'red'">
                  {{ record.success ? '成功' : '失败' }}
                </Tag>
              </template>
              <template v-else-if="column.key === 'problem_tags'">
                <template v-if="record.problem_tags?.length">
                  <Tag
                    v-for="tag in record.problem_tags.slice(0, 3)"
                    :key="tag"
                    color="orange"
                    class="mb-1 mr-1"
                  >
                    {{ tag }}
                  </Tag>
                  <span
                    v-if="record.problem_tags.length > 3"
                    class="text-xs text-muted-foreground"
                  >
                    +{{ record.problem_tags.length - 3 }}
                  </span>
                </template>
                <span v-else class="text-muted-foreground">-</span>
              </template>
              <template v-else-if="column.key === 'problem_snippets'">
                <span
                  v-if="
                    record.problem_snippets?.length ||
                    record.problem_context_list?.length
                  "
                  class="truncate"
                >
                  {{
                    (
                      record.problem_snippets ||
                      record.problem_context_list ||
                      []
                    )
                      .slice(0, 3)
                      .join('、')
                  }}
                  <span
                    v-if="
                      (
                        record.problem_snippets ||
                        record.problem_context_list ||
                        []
                      ).length > 3
                    "
                    class="text-muted-foreground"
                  >
                    等{{
                      (
                        record.problem_snippets ||
                        record.problem_context_list ||
                        []
                      ).length
                    }}处
                  </span>
                </span>
                <span v-else class="text-muted-foreground">-</span>
              </template>
              <template v-else-if="column.key === 'create_time'">
                {{
                  record.create_time ? formatDateTime(record.create_time) : '-'
                }}
              </template>
            </template>
          </Table>
        </Card>
      </Col>
    </Row>

    <Drawer
      v-model:open="detailOpen"
      title="评测结果详情"
      width="920"
      :destroy-on-close="true"
    >
      <template v-if="detailLoading">
        <div class="py-6 text-center text-muted-foreground">加载中...</div>
      </template>

      <template v-else-if="selectedResult">
        <Descriptions bordered size="small" :column="1">
          <DescriptionsItem label="结果ID">
            {{ selectedResult.id }}
          </DescriptionsItem>
          <DescriptionsItem label="Run ID">
            {{ selectedResult.run_id }}
          </DescriptionsItem>
          <DescriptionsItem label="TestCase ID">
            {{ selectedResult.test_case_id }}
          </DescriptionsItem>
          <DescriptionsItem label="状态">
            <Tag :color="selectedResult.success ? 'green' : 'red'">
              {{ selectedResult.success ? '成功' : '失败' }}
            </Tag>
          </DescriptionsItem>
          <DescriptionsItem label="分数">
            {{ selectedResult.score ?? '-' }}
          </DescriptionsItem>
          <DescriptionsItem label="模型">
            {{ selectedResult.model_code ?? '-' }}
          </DescriptionsItem>
          <DescriptionsItem label="供应商">
            {{ selectedResult.provider_code ?? '-' }}
          </DescriptionsItem>
          <DescriptionsItem label="耗时(ms)">
            {{ selectedResult.latency_ms ?? '-' }}
          </DescriptionsItem>
          <DescriptionsItem label="Token消耗">
            <template v-if="selectedResult.token_usage">
              prompt: {{ selectedResult.token_usage.prompt_tokens ?? 0 }} |
              completion:
              {{ selectedResult.token_usage.completion_tokens ?? 0 }} | total:
              {{ selectedResult.token_usage.total_tokens ?? 0 }}
            </template>
            <span v-else>-</span>
          </DescriptionsItem>
          <DescriptionsItem label="trace_id">
            <div class="flex items-center gap-2">
              <span class="truncate">{{ selectedResult.trace_id ?? '-' }}</span>
              <Button
                size="small"
                type="link"
                @click="copyText(selectedResult.trace_id)"
              >
                复制
              </Button>
            </div>
          </DescriptionsItem>
        </Descriptions>

        <Card class="mt-3" size="small" title="评分结果">
          <div class="mb-3">
            <div class="mb-1 text-xs text-muted-foreground">问题种类</div>
            <div
              v-if="selectedResult.problem_tags?.length"
              class="flex flex-wrap gap-1"
            >
              <Tag
                v-for="tag in selectedResult.problem_tags"
                :key="tag"
                color="orange"
              >
                {{ tag }}
              </Tag>
            </div>
            <span v-else class="text-muted-foreground">无</span>
          </div>
          <div class="mb-3">
            <div class="mb-1 text-xs text-muted-foreground">原文摘录</div>
            <div
              v-if="
                selectedResult.problem_snippets?.length ||
                selectedResult.problem_context_list?.length
              "
              class="flex flex-wrap gap-1"
            >
              <Tag
                v-for="(snippet, idx) in selectedResult.problem_snippets ||
                selectedResult.problem_context_list"
                :key="idx"
                color="red"
              >
                {{ snippet }}
              </Tag>
            </div>
            <span v-else class="text-muted-foreground">无</span>
          </div>
          <div class="mb-2">
            <div class="mb-1 text-xs text-muted-foreground">评语</div>
            <Input.TextArea
              :value="selectedResult.reason ?? ''"
              :auto-size="{ minRows: 3, maxRows: 8 }"
              readonly
            />
          </div>
          <div v-if="selectedResult.error_message" class="mt-2">
            <div class="mb-1 text-xs text-muted-foreground">错误信息</div>
            <Input.TextArea
              :value="selectedResult.error_message"
              :auto-size="{ minRows: 2, maxRows: 6 }"
              readonly
            />
          </div>
        </Card>

        <Card class="mt-3" size="small" title="测试用例">
          <div class="mb-2 flex items-center justify-between">
            <div class="text-xs text-muted-foreground">
              dataset_code：{{ selectedResult.test_case?.dataset_code ?? '-' }}
            </div>
            <Button
              size="small"
              type="link"
              @click="copyText(selectedResult.test_case?.content)"
            >
              复制正文
            </Button>
          </div>
          <div class="mb-2" v-if="selectedResult.test_case?.title">
            <div class="mb-1 text-xs text-muted-foreground">标题</div>
            <Input :value="selectedResult.test_case?.title ?? ''" readonly />
          </div>
          <div>
            <div class="mb-1 text-xs text-muted-foreground">正文</div>
            <Input.TextArea
              :value="selectedResult.test_case?.content ?? ''"
              :auto-size="{ minRows: 6, maxRows: 16 }"
              readonly
            />
          </div>
        </Card>

        <Card class="mt-3" size="small" title="Rendered Prompt">
          <div class="mb-2 flex items-center justify-end">
            <Button
              size="small"
              type="link"
              @click="copyText(selectedResult.rendered_prompt)"
            >
              复制 Prompt
            </Button>
          </div>
          <Input.TextArea
            :value="selectedResult.rendered_prompt ?? ''"
            :auto-size="{ minRows: 8, maxRows: 18 }"
            readonly
          />
        </Card>

        <Card class="mt-3" size="small" title="Raw Output（JSON）">
          <div class="mb-2 flex items-center justify-end">
            <Button
              size="small"
              type="link"
              @click="
                copyText(
                  JSON.stringify(selectedResult.raw_output ?? {}, null, 2),
                )
              "
            >
              复制 JSON
            </Button>
          </div>
          <MonacoEditor
            :model-value="
              JSON.stringify(selectedResult.raw_output ?? {}, null, 2)
            "
            language="json"
            height="300px"
            readonly
            :line-numbers="true"
            :minimap="false"
          />
        </Card>
      </template>
      <template v-else>
        <div class="py-6 text-center text-muted-foreground">暂无数据</div>
      </template>
    </Drawer>
  </div>
</template>

<style scoped>
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
</style>
