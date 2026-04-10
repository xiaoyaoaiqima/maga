<script setup lang="ts">
import type { TraceApi } from '#/api/core/trace';

import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { formatDateTime } from '@vben/utils';

import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  Descriptions,
  DescriptionsItem,
  Divider,
  Empty,
  message,
  Row,
  Spin,
  Statistic,
  TabPane,
  Tabs,
  Tag,
  Timeline,
  TimelineItem,
  Tooltip,
} from 'ant-design-vue';

import { getTraceDetailApi } from '#/api/core/trace';

const router = useRouter();
const route = useRoute();
const loading = ref(false);
const traceDetail = ref<null | TraceApi.TraceDetailResponse>(null);

const statusColorMap: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  success: 'success',
  failed: 'error',
  timeout: 'warning',
};

const statusTextMap: Record<string, string> = {
  pending: '待执行',
  running: '执行中',
  success: '成功',
  failed: '失败',
  timeout: '超时',
};

const stageTagColor: Record<string, string> = {
  plugin_render: 'blue',
  prompt_render: 'cyan',
  ge_generation: 'green',
  ag_ban: 'orange',
  ag_critic: 'purple',
  debug: 'default',
  expert_call: 'magenta',
  llm_call: 'geekblue',
  // RLHF 阶段
  rlhf_like: 'pink',
  rlhf_adopt: 'volcano',
  rlhf_score: 'gold',
  rlhf_tag: 'lime',
  rlhf_edit: 'cyan',
};

const stageTextMap: Record<string, string> = {
  plugin_render: 'Plugin 渲染',
  prompt_render: 'Prompt 渲染',
  ge_generation: 'GE 生成',
  ag_ban: 'AG Ban 检查',
  ag_critic: 'AG Critic 评分',
  debug: '调试',
  expert_call: 'Expert 调用',
  llm_call: 'LLM 调用',
  // RLHF 阶段
  rlhf_like: '喜欢操作',
  rlhf_adopt: '采纳操作',
  rlhf_score: 'RLHF 评分',
  rlhf_tag: '问题标签',
  rlhf_edit: '内容修改',
};

// RLHF 阶段列表
const RLHF_STAGES = new Set([
  'rlhf_adopt',
  'rlhf_edit',
  'rlhf_like',
  'rlhf_score',
  'rlhf_tag',
]);

// 判断是否为 RLHF 阶段
function isRlhfStage(stage: string): boolean {
  return RLHF_STAGES.has(stage);
}

// 跳转到 RLHF 审核详情
function goToRlhfReview(feedbackId: number | undefined) {
  if (feedbackId) {
    router.push(`/rlhf/review?id=${feedbackId}`);
  }
}

const mainTrace = computed(() => traceDetail.value?.trace);
const spans = computed(() => traceDetail.value?.spans || []);

// 构建执行时间线
const timeline = computed(() => {
  if (spans.value.length === 0) return [];

  return [...spans.value]
    .toSorted(
      (a, b) =>
        new Date(a.start_time).getTime() - new Date(b.start_time).getTime(),
    )
    .map((span, index) => ({
      span_id: span.span_id,
      stage: span.stage,
      status: span.status,
      start_time: span.start_time,
      end_time: span.end_time,
      duration_ms: span.duration_ms,
      expert_config_code: span.expert_config_code,
      error_message: span.error_message,
      isLast: index === spans.value.length - 1,
      // RLHF 扩展字段
      rlhf_feedback_id: span.rlhf_feedback_id,
      reviewer_id: span.reviewer_id,
      reviewer_name: span.reviewer_name,
      result_summary: span.result_summary,
    }));
});

async function fetchTraceDetail() {
  const traceId = route.params.id as string;
  if (!traceId) {
    message.error('缺少 Trace ID');
    router.push('/trace/list');
    return;
  }

  loading.value = true;
  try {
    const res = await getTraceDetailApi(traceId);
    traceDetail.value = res;
  } catch (error) {
    console.error('获取追踪详情失败:', error);
    message.error('获取调用详情失败');
    router.push('/trace/list');
  } finally {
    loading.value = false;
  }
}

function handleBack() {
  router.push('/trace/list');
}

function formatDuration(ms: number | undefined): string {
  if (!ms || ms <= 0) return '-';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatTokens(tokens: number | undefined): string {
  if (!tokens) return '-';
  return tokens.toLocaleString();
}

function formatCost(
  cost: number | undefined,
  currency: string = 'USD',
): string {
  if (cost === undefined || cost === null) return '-';
  const symbol = currency === 'CNY' ? '¥' : '$';
  if (cost === 0) return `${symbol}0`;
  return `${symbol}${(Number(cost) || 0).toFixed(6)}`;
}

// JSON 语法高亮格式化
function formatJsonWithHighlight(
  data: null | Record<string, any> | undefined,
): string {
  if (!data) return '';

  try {
    const formatted = JSON.stringify(data, null, 2);

    // 添加语法高亮
    return (
      formatted
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
    return String(data);
  }
}

onMounted(() => {
  fetchTraceDetail();
});
</script>

<template>
  <div class="p-4">
    <Spin :spinning="loading">
      <Card :bordered="false">
        <template #title>
          <div class="flex items-center gap-2">
            <Button type="text" @click="handleBack"> ⬅️ </Button>
            <span>调用详情</span>
            <template v-if="mainTrace">
              <Divider type="vertical" />
              <Tag :color="stageTagColor[mainTrace.stage] || 'default'">
                {{ stageTextMap[mainTrace.stage] || mainTrace.stage }}
              </Tag>
              <Badge
                :status="statusColorMap[mainTrace.status] as any"
                :text="statusTextMap[mainTrace.status] || mainTrace.status"
              />
            </template>
          </div>
        </template>

        <template v-if="mainTrace">
          <!-- 基本信息 -->
          <Descriptions :column="3" bordered size="small">
            <DescriptionsItem label="Trace ID">
              <Tooltip :title="mainTrace.trace_id">
                <code>{{ mainTrace.trace_id }}</code>
              </Tooltip>
            </DescriptionsItem>
            <DescriptionsItem label="Span ID">
              <code>{{ mainTrace.span_id }}</code>
            </DescriptionsItem>
            <DescriptionsItem label="总耗时">
              <span
                :class="{ 'text-warning': (mainTrace.duration_ms || 0) > 5000 }"
              >
                {{ formatDuration(mainTrace.duration_ms) }}
              </span>
            </DescriptionsItem>

            <DescriptionsItem label="Job ID">
              <code>{{ mainTrace.job_id }}</code>
            </DescriptionsItem>
            <DescriptionsItem label="Sub Job ID">
              <code>{{ mainTrace.sub_job_id }}</code>
            </DescriptionsItem>
            <DescriptionsItem label="Content ID">
              <code v-if="mainTrace.content_id">{{
                mainTrace.content_id
              }}</code>
              <span v-else class="text-muted">-</span>
            </DescriptionsItem>

            <DescriptionsItem label="Expert">
              {{ mainTrace.expert_config_code || '-' }}
            </DescriptionsItem>
            <DescriptionsItem label="Expert 类型">
              {{ mainTrace.expert_type || '-' }}
            </DescriptionsItem>
            <DescriptionsItem label="模型">
              {{ mainTrace.model_code || '-' }}
            </DescriptionsItem>

            <DescriptionsItem label="目标服务">
              {{ mainTrace.service_app }}
            </DescriptionsItem>
            <DescriptionsItem label="调用方法">
              {{ mainTrace.service_method }}
            </DescriptionsItem>
            <DescriptionsItem label="调用来源">
              {{ mainTrace.caller_service || '-' }}
            </DescriptionsItem>

            <DescriptionsItem label="开始时间">
              {{ formatDateTime(mainTrace.start_time) }}
            </DescriptionsItem>
            <DescriptionsItem label="结束时间">
              {{
                mainTrace.end_time ? formatDateTime(mainTrace.end_time) : '-'
              }}
            </DescriptionsItem>
            <DescriptionsItem label="创建时间">
              {{ formatDateTime(mainTrace.created_at) }}
            </DescriptionsItem>
          </Descriptions>

          <!-- 错误信息 -->
          <Alert
            v-if="mainTrace.error_message"
            type="error"
            class="mt-4"
            show-icon
          >
            <template #message>
              <strong>{{ mainTrace.error_type || '错误' }}:</strong>
              {{ mainTrace.error_message }}
            </template>
          </Alert>

          <!-- 实验信息 -->
          <Card
            v-if="mainTrace.experiment_id"
            size="small"
            class="mt-4"
            title="🧪 A/B 实验信息"
          >
            <Descriptions :column="4" size="small">
              <DescriptionsItem label="实验 ID">
                {{ mainTrace.experiment_id }}
              </DescriptionsItem>
              <DescriptionsItem label="实验分组">
                <Tag color="blue">{{ mainTrace.experiment_group }}</Tag>
              </DescriptionsItem>
              <DescriptionsItem label="变体">
                {{ mainTrace.experiment_variant || '-' }}
              </DescriptionsItem>
              <DescriptionsItem label="来源">
                {{ mainTrace.experiment_source || '-' }}
              </DescriptionsItem>
            </Descriptions>
          </Card>

          <!-- 统计指标：时间 -->
          <Row :gutter="16" class="mt-4">
            <Col :span="8">
              <Card size="small" class="stat-card">
                <div class="custom-stat">
                  <div class="stat-title">排队时间</div>
                  <div class="stat-value">
                    {{ formatDuration(mainTrace.queue_time_ms) }}
                  </div>
                </div>
              </Card>
            </Col>
            <Col :span="8">
              <Card size="small" class="stat-card">
                <div class="custom-stat">
                  <div class="stat-title">渲染时间</div>
                  <div class="stat-value">
                    {{ formatDuration(mainTrace.render_time_ms) }}
                  </div>
                </div>
              </Card>
            </Col>
            <Col :span="8">
              <Card size="small" class="stat-card">
                <div class="custom-stat">
                  <div class="stat-title">模型耗时</div>
                  <div class="stat-value">
                    {{ formatDuration(mainTrace.model_time_ms) }}
                  </div>
                </div>
              </Card>
            </Col>
          </Row>

          <!-- 统计指标：Token 与 费用 -->
          <Row :gutter="16" class="mt-4">
            <Col :span="6">
              <Card size="small" class="stat-card">
                <Statistic
                  title="输入 Tokens"
                  :value="mainTrace.input_tokens || 0"
                />
              </Card>
            </Col>
            <Col :span="6">
              <Card size="small" class="stat-card">
                <Statistic
                  title="输出 Tokens"
                  :value="mainTrace.output_tokens || 0"
                />
              </Card>
            </Col>
            <Col :span="6">
              <Card size="small" class="stat-card">
                <Statistic
                  title="总 Tokens"
                  :value="mainTrace.total_tokens || 0"
                  :value-style="{
                    color:
                      mainTrace.total_tokens > 1000 ? '#cf1322' : undefined,
                  }"
                />
              </Card>
            </Col>
            <Col :span="6">
              <Card size="small" class="stat-card">
                <Statistic
                  title="模型费用"
                  :value="formatCost(mainTrace.total_cost, mainTrace.currency)"
                  :value-style="{ color: '#52c41a' }"
                />
              </Card>
            </Col>
          </Row>

          <!-- 详细内容 -->
          <Tabs class="mt-4">
            <TabPane key="prompt" tab="📝 渲染后的 Prompt">
              <div v-if="mainTrace.rendered_prompt" class="content-block">
                <pre>{{ mainTrace.rendered_prompt }}</pre>
              </div>
              <Empty v-else description="无 Prompt 数据" />
            </TabPane>

            <TabPane key="plugin" tab="🔌 Plugin 配置快照">
              <div
                v-if="mainTrace.plugin_config_snapshot"
                class="json-viewer-block"
              >
                <!-- eslint-disable vue/no-v-html -->
                <pre
                  class="json-viewer"
                  v-html="
                    formatJsonWithHighlight(mainTrace.plugin_config_snapshot)
                  "
                ></pre>
                <!-- eslint-enable vue/no-v-html -->
              </div>
              <Empty v-else description="无 Plugin 配置" />
            </TabPane>

            <TabPane key="result" tab="📊 结果摘要">
              <div v-if="mainTrace.result_summary" class="json-viewer-block">
                <!-- eslint-disable vue/no-v-html -->
                <pre
                  class="json-viewer"
                  v-html="formatJsonWithHighlight(mainTrace.result_summary)"
                ></pre>
                <!-- eslint-enable vue/no-v-html -->
              </div>
              <Empty v-else description="无结果摘要" />
            </TabPane>

            <TabPane key="timeline" tab="⏱️ 执行时间线">
              <Timeline v-if="timeline.length > 0" mode="left">
                <TimelineItem
                  v-for="item in timeline"
                  :key="item.span_id"
                  :color="
                    item.status === 'success'
                      ? 'green'
                      : item.status === 'failed'
                        ? 'red'
                        : 'blue'
                  "
                >
                  <div class="timeline-item">
                    <div class="timeline-header">
                      <Tag
                        :color="stageTagColor[item.stage] || 'default'"
                        size="small"
                      >
                        {{ stageTextMap[item.stage] || item.stage }}
                      </Tag>
                      <Badge
                        :status="statusColorMap[item.status] as any"
                        :text="statusTextMap[item.status]"
                      />
                      <span class="timeline-duration">
                        {{ formatDuration(item.duration_ms) }}
                      </span>
                      <!-- RLHF 阶段跳转链接 -->
                      <Button
                        v-if="isRlhfStage(item.stage) && item.rlhf_feedback_id"
                        type="link"
                        size="small"
                        @click="goToRlhfReview(item.rlhf_feedback_id)"
                      >
                        查看审核详情 →
                      </Button>
                    </div>
                    <div class="timeline-content">
                      <p><strong>Span:</strong> {{ item.span_id }}</p>
                      <p v-if="item.expert_config_code">
                        <strong>Expert:</strong> {{ item.expert_config_code }}
                      </p>
                      <!-- RLHF 审核人信息 -->
                      <p v-if="isRlhfStage(item.stage) && item.reviewer_name">
                        <strong>审核人:</strong>
                        <Tag color="blue" size="small">
                          {{ item.reviewer_name }}
                        </Tag>
                      </p>
                      <p>
                        <strong>时间:</strong>
                        {{ formatDateTime(item.start_time) }}
                        <span v-if="item.end_time">
                          → {{ formatDateTime(item.end_time) }}
                        </span>
                      </p>
                      <!-- RLHF 阶段结果摘要 -->
                      <div
                        v-if="isRlhfStage(item.stage) && item.result_summary"
                        class="rlhf-result"
                      >
                        <strong>操作结果:</strong>
                        <Tag
                          v-if="item.result_summary.operation"
                          :color="
                            item.result_summary.operation === 'LIKE' ||
                            item.result_summary.operation === 'ADOPT'
                              ? 'success'
                              : 'error'
                          "
                          size="small"
                        >
                          {{ item.result_summary.operation }}
                        </Tag>
                        <span
                          v-if="item.result_summary.content_score"
                          class="ml-2"
                        >
                          内容评分:
                          <strong>{{
                            item.result_summary.content_score
                          }}</strong>
                        </span>
                        <span
                          v-if="item.result_summary.model_score"
                          class="ml-2"
                        >
                          模型评分:
                          <strong>{{ item.result_summary.model_score }}</strong>
                        </span>
                      </div>
                      <p v-if="item.error_message" class="error-text">
                        <strong>错误:</strong> {{ item.error_message }}
                      </p>
                    </div>
                  </div>
                </TimelineItem>
              </Timeline>
              <Empty v-else description="无时间线数据" />
            </TabPane>

            <TabPane key="spans" tab="🔗 Span 列表">
              <div v-if="spans.length > 0">
                <Card
                  v-for="span in spans"
                  :key="span.span_id"
                  size="small"
                  class="span-card"
                  :class="{
                    'span-error': span.status === 'failed',
                    'span-rlhf': isRlhfStage(span.stage),
                  }"
                >
                  <template #title>
                    <div class="flex items-center gap-2">
                      <Tag
                        :color="stageTagColor[span.stage] || 'default'"
                        size="small"
                      >
                        {{ stageTextMap[span.stage] || span.stage }}
                      </Tag>
                      <code>{{ span.span_id }}</code>
                      <Badge
                        :status="statusColorMap[span.status] as any"
                        :text="statusTextMap[span.status]"
                      />
                      <!-- RLHF 跳转链接 -->
                      <Button
                        v-if="isRlhfStage(span.stage) && span.rlhf_feedback_id"
                        type="link"
                        size="small"
                        @click="goToRlhfReview(span.rlhf_feedback_id)"
                      >
                        查看审核 →
                      </Button>
                    </div>
                  </template>
                  <Descriptions :column="4" size="small">
                    <!-- RLHF 阶段显示审核人 -->
                    <template v-if="isRlhfStage(span.stage)">
                      <DescriptionsItem label="审核人">
                        <Tag
                          v-if="span.reviewer_name"
                          color="blue"
                          size="small"
                        >
                          {{ span.reviewer_name }}
                        </Tag>
                        <span v-else>-</span>
                      </DescriptionsItem>
                      <DescriptionsItem label="操作">
                        <Tag
                          v-if="span.result_summary?.operation"
                          :color="
                            span.result_summary.operation === 'LIKE' ||
                            span.result_summary.operation === 'ADOPT'
                              ? 'success'
                              : 'error'
                          "
                          size="small"
                        >
                          {{ span.result_summary.operation }}
                        </Tag>
                        <span v-else>-</span>
                      </DescriptionsItem>
                      <DescriptionsItem label="内容评分">
                        {{ span.result_summary?.content_score || '-' }}
                      </DescriptionsItem>
                      <DescriptionsItem label="模型评分">
                        {{ span.result_summary?.model_score || '-' }}
                      </DescriptionsItem>
                    </template>
                    <!-- 非 RLHF 阶段 -->
                    <template v-else>
                      <DescriptionsItem label="Expert">
                        {{ span.expert_config_code || '-' }}
                      </DescriptionsItem>
                      <DescriptionsItem label="耗时">
                        {{ formatDuration(span.duration_ms) }}
                      </DescriptionsItem>
                      <DescriptionsItem label="Tokens">
                        {{ formatTokens(span.total_tokens) }}
                      </DescriptionsItem>
                      <DescriptionsItem label="费用">
                        {{ formatCost(span.total_cost, span.currency) }}
                      </DescriptionsItem>
                      <DescriptionsItem label="模型">
                        {{ span.model_code || '-' }}
                      </DescriptionsItem>
                    </template>
                  </Descriptions>
                  <Alert
                    v-if="span.error_message"
                    type="error"
                    size="small"
                    :message="span.error_message"
                    class="mt-2"
                  />
                </Card>
              </div>
              <Empty v-else description="无 Span 数据" />
            </TabPane>
          </Tabs>
        </template>

        <Empty v-else-if="!loading" description="未找到追踪记录" />
      </Card>
    </Spin>
  </div>
</template>

<style scoped>
.p-4 {
  padding: 16px;
}

.mt-2 {
  margin-top: 8px;
}

.mt-4 {
  margin-top: 16px;
}

.flex {
  display: flex;
}

.items-center {
  align-items: center;
}

.gap-2 {
  gap: 8px;
}

.text-warning {
  color: hsl(var(--warning));
}

.text-muted {
  color: hsl(var(--muted-foreground));
}

.stat-card {
  text-align: center;
}

.custom-stat {
  text-align: center;
}

.custom-stat .stat-title {
  margin-bottom: 4px;
  font-size: 14px;
  color: hsl(var(--muted-foreground));
}

.custom-stat .stat-value {
  font-size: 24px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.content-block {
  max-height: 500px;
  padding: 16px;
  overflow-y: auto;
  background: hsl(var(--muted));
  border-radius: 6px;
}

.content-block pre {
  margin: 0;
  font-size: 13px;
  color: hsl(var(--foreground));
  word-break: break-all;
  white-space: pre-wrap;
}

/* JSON Viewer 样式 */
.json-viewer-block {
  max-height: 500px;
  padding: 16px;
  overflow-y: auto;
  background: hsl(var(--muted));
  border-radius: 8px;
}

.json-viewer {
  margin: 0;
  font-family: 'Fira Code', Consolas, Monaco, monospace;
  font-size: 13px;
  line-height: 1.6;
  color: hsl(var(--foreground));
  word-break: break-all;
  white-space: pre-wrap;
}

/* JSON 语法高亮颜色 */
.json-viewer :deep(.json-key) {
  color: hsl(var(--primary));
}

.json-viewer :deep(.json-string) {
  color: #95de64;
}

.json-viewer :deep(.json-number) {
  color: #ffc069;
}

.json-viewer :deep(.json-boolean) {
  color: #ff85c0;
}

.json-viewer :deep(.json-null) {
  color: #ff7875;
}

.timeline-item {
  padding: 8px 0;
}

.timeline-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.timeline-duration {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.timeline-content {
  font-size: 13px;
}

.timeline-content p {
  margin: 4px 0;
}

.error-text {
  color: hsl(var(--destructive));
}

.span-card {
  margin-bottom: 12px;
}

.span-card.span-error {
  border-color: hsl(var(--destructive));
}

.span-card.span-rlhf {
  border-left: 3px solid hsl(var(--primary));
}

code {
  padding: 2px 6px;
  font-size: 12px;
  background: hsl(var(--muted));
  border-radius: 4px;
}

/* RLHF 结果样式 */
.rlhf-result {
  padding: 8px 12px;
  margin-top: 8px;
  background: hsl(var(--muted) / 50%);
  border-radius: 4px;
}

.ml-2 {
  margin-left: 8px;
}
</style>
