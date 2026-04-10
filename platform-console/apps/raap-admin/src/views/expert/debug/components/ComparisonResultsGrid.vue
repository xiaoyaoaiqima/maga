<script setup lang="ts">
import type { CompareGroup, DebugResponse, ModelRoute } from '../types';

/**
 * 对比结果网格组件
 */
import { Button, Card, Col, Row, Tag, Tooltip } from 'ant-design-vue';

import {
  calculateCost,
  formatExecutionTime,
  getDisplayContent,
  getEffectiveTokenUsage,
  hasVariableDiff,
} from '../utils';

interface Props {
  compareGroups: CompareGroup[];
  comparisonResults: Array<DebugResponse | null>;
  modelRoutes: ModelRoute[];
}

defineProps<Props>();

const emit = defineEmits<{
  viewDetail: [result: DebugResponse];
}>();
</script>

<template>
  <div class="comparison-section mt-4">
    <Row :gutter="[16, 16]">
      <Col
        v-for="(result, index) in comparisonResults"
        :key="index"
        :xs="24"
        :sm="12"
        :md="8"
        :xl="8"
      >
        <Card
          size="small"
          class="comparison-card"
          :class="{ 'result-card-fail': !result?.success }"
        >
          <template #title>
            <div class="flex items-center justify-between overflow-hidden">
              <span class="truncate" :title="compareGroups[index]?.name">
                {{ compareGroups[index]?.name }}
              </span>
              <Tag
                :color="result?.success ? 'success' : 'error'"
                class="ml-2 flex-shrink-0"
              >
                {{ result?.success ? '成功' : '失败' }}
              </Tag>
            </div>
          </template>
          <template #extra>
            <span class="text-xs text-muted-foreground">
              {{ formatExecutionTime(result?.execution_time_ms || 0) }}
            </span>
          </template>

          <div v-if="result" class="comparison-card-content">
            <!-- 元数据统计区 -->
            <div class="metrics-grid mb-3">
              <div class="metric-item">
                <span class="metric-label">模型</span>
                <span
                  class="metric-value w-full truncate text-center"
                  :title="result.model_code"
                  >{{ result.model_code || '-' }}</span
                >
              </div>
              <div class="metric-item">
                <span class="metric-label">Tokens</span>
                <span class="metric-value">
                  {{ getEffectiveTokenUsage(result).total_tokens }}
                  <Tooltip>
                    <template #title>
                      Prompt:
                      {{ getEffectiveTokenUsage(result).prompt_tokens }} |
                      Completion:
                      {{ getEffectiveTokenUsage(result).completion_tokens }}
                    </template>
                    <span class="info-icon">ⓘ</span>
                  </Tooltip>
                </span>
              </div>
              <div class="metric-item">
                <span class="metric-label">预估费用</span>
                <span class="metric-value text-primary">
                  ${{
                    calculateCost(result.model_code || '', modelRoutes, result)
                  }}
                </span>
              </div>
            </div>

            <!-- 差异参数简报 -->
            <div class="param-diff-box mb-3">
              <div class="mb-1 text-[11px] font-bold text-muted-foreground">
                差异参数:
              </div>
              <div class="param-diff-scroll">
                <div
                  v-if="index === 0"
                  class="text-xs italic text-muted-foreground"
                >
                  基准对照组
                </div>
                <div v-else class="flex flex-wrap gap-1">
                  <template
                    v-for="p in result.plugin_config_snapshot"
                    :key="p.plugin_code"
                  >
                    <template v-for="(v, k) in p.variable_mapping" :key="k">
                      <Tag
                        v-if="
                          v !==
                          comparisonResults[0]?.plugin_config_snapshot?.find(
                            (pc) => pc.plugin_code === p.plugin_code,
                          )?.variable_mapping[k]
                        "
                        size="small"
                        color="blue"
                        style="margin-right: 0"
                      >
                        {{ k }}: {{ v }}
                      </Tag>
                    </template>
                  </template>
                  <Tag
                    v-if="
                      result.model_code !== comparisonResults[0]?.model_code
                    "
                    size="small"
                    color="orange"
                    style="margin-right: 0"
                  >
                    模型: {{ result.model_code }}
                  </Tag>
                  <div
                    v-if="
                      index > 0 &&
                      result.model_code === comparisonResults[0]?.model_code &&
                      !hasVariableDiff(result, comparisonResults[0])
                    "
                    class="text-xs text-muted-foreground"
                  >
                    无配置差异
                  </div>
                </div>
              </div>
            </div>

            <!-- 文章内容 -->
            <div class="output-preview">
              <div class="output-title-bar">
                <span
                  v-if="result.expert_total_output?.title"
                  class="block w-full truncate font-bold"
                  :title="result.expert_total_output.title"
                >
                  {{ result.expert_total_output.title }}
                </span>
                <span v-else class="italic text-muted-foreground">无标题</span>
              </div>
              <div class="article-viewer-container">
                <div class="article-viewer-content">
                  {{ getDisplayContent(result) }}
                </div>
              </div>
              <div class="card-footer mt-2">
                <Button
                  size="small"
                  type="link"
                  block
                  @click="emit('viewDetail', result)"
                >
                  查看详情 & 调试
                </Button>
              </div>
            </div>
          </div>
          <div v-else class="empty-result py-8">等待执行...</div>
        </Card>
      </Col>
    </Row>
  </div>
</template>

<style scoped>
.comparison-section {
  padding-bottom: 32px;
}

.comparison-card {
  height: 100%;
}

.result-card-fail {
  border-color: hsl(var(--destructive) / 50%);
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  height: 64px;
  padding: 8px;
  background: hsl(var(--muted) / 50%);
  border-radius: 6px;
}

.metric-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.metric-label {
  margin-bottom: 2px;
  font-size: 10px;
  color: hsl(var(--muted-foreground));
}

.metric-value {
  font-size: 11px;
  font-weight: 600;
  line-height: 1.2;
}

.info-icon {
  margin-left: 2px;
  cursor: help;
  opacity: 0.6;
}

.param-diff-box {
  display: flex;
  flex-direction: column;
  height: 100px;
  padding: 8px;
  background: hsl(var(--warning) / 5%);
  border: 1px dashed hsl(var(--warning) / 30%);
  border-radius: 6px;
}

.param-diff-scroll {
  flex: 1;
  overflow-y: auto;
}

.output-title-bar {
  display: flex;
  align-items: center;
  height: 32px;
  padding: 0 4px;
  margin-bottom: 4px;
  border-bottom: 1px solid hsl(var(--border) / 50%);
}

.article-viewer-container {
  height: 400px;
  overflow-y: auto;
  background: hsl(var(--muted) / 20%);
  border: 1px solid hsl(var(--border));
  border-radius: 4px;
}

.article-viewer-content {
  padding: 12px;
  font-family: Monaco, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
  color: hsl(var(--foreground));
  word-break: break-all;
  white-space: pre-wrap;
}

.card-footer {
  height: 32px;
}

.empty-result {
  padding: 80px 0;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.mt-4 {
  margin-top: 16px;
}

.mt-2 {
  margin-top: 8px;
}

.mb-3 {
  margin-bottom: 12px;
}

.mb-1 {
  margin-bottom: 4px;
}
</style>
