<script setup lang="ts">
import type { TableColumnsType } from 'ant-design-vue';
import type { ECharts } from 'echarts/core';

import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';

import { formatDateTime } from '@vben/utils';

import {
  Card,
  Col,
  Collapse,
  CollapsePanel,
  Descriptions,
  DescriptionsItem,
  Row,
  Spin,
  Statistic,
  Table,
  Tag,
} from 'ant-design-vue';
import { LineChart } from 'echarts/charts';
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';

import { ABTestApi } from '#/api/core/ab-test';

const props = defineProps<{
  testId: string;
}>();

defineEmits<{
  (e: 'close'): void;
}>();

// 注册 ECharts 组件
echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CanvasRenderer,
]);

// 状态
const loading = ref(false);
const detail = ref<ABTestApi.ABTestDetailResponse>();

// 图表 refs
const passRateChartRef = ref<HTMLDivElement | null>(null);
const avgScoreChartRef = ref<HTMLDivElement | null>(null);
let passRateChart: ECharts | null = null;
let avgScoreChart: ECharts | null = null;

// 组颜色映射
const groupColorMap: Record<string, string> = {
  control: 'blue',
  experiment_1: 'green',
  experiment_2: 'orange',
  experiment_3: 'purple',
  experiment_4: 'cyan',
};

function getGroupColor(groupName: string): string {
  if (groupColorMap[groupName]) {
    return groupColorMap[groupName];
  }
  const colors = ['blue', 'green', 'orange', 'purple', 'cyan', 'magenta'];
  const index = (groupName.codePointAt(0) ?? 0) % colors.length;
  return colors[index] || 'default';
}

function getGroupBgColor(groupName: string): string {
  const colorToBg: Record<string, string> = {
    blue: 'linear-gradient(135deg, #e6f7ff 0%, #bae7ff 100%)',
    green: 'linear-gradient(135deg, #f6ffed 0%, #d9f7be 100%)',
    orange: 'linear-gradient(135deg, #fff7e6 0%, #ffd591 100%)',
    purple: 'linear-gradient(135deg, #f9f0ff 0%, #d3adf7 100%)',
    cyan: 'linear-gradient(135deg, #e6fffb 0%, #87e8de 100%)',
    magenta: 'linear-gradient(135deg, #fff0f6 0%, #ffadd2 100%)',
  };
  const color = getGroupColor(groupName);
  return colorToBg[color] || colorToBg.blue;
}

// 获取测试详情
async function fetchDetail() {
  loading.value = true;
  try {
    const res = await ABTestApi.getABTestDetail(props.testId);
    detail.value = res;
    // 渲染图表
    if (res.test.test_type === 'AGENT_JOB') {
      renderCriticCharts();
    }
  } catch (error: unknown) {
    console.error('获取详情失败:', error);
  } finally {
    loading.value = false;
  }
}

// 是否有 Critic 评分详情
const hasCriticDetails = computed(() => {
  if (!detail.value?.group_details) return false;
  return detail.value.group_details.some(
    (g) => g.critic_details && g.critic_details.length > 0,
  );
});

// Critic 评分对比表格列
const criticColumns = computed<TableColumnsType>(() => {
  if (!detail.value?.group_details) return [];

  const cols: TableColumnsType = [
    {
      title: 'Critic Expert',
      dataIndex: 'expert_func',
      key: 'expert_func',
      width: 180,
      fixed: 'left',
    },
  ];

  // 为每个组添加一列
  for (const group of detail.value.group_details) {
    cols.push({
      title:
        group.group_name + (group.description ? ` (${group.description})` : ''),
      key: `group_${group.group_name}`,
      width: 200,
      align: 'center',
    });
  }

  return cols;
});

// Critic 评分对比数据
interface CriticComparisonRow {
  expert_func: string;
  [key: string]: ABTestApi.CriticScoreDetail | string | undefined;
}

// 获取 expert_config_code 列表的顺序（用于排序 Critic 表格）
const expertConfigCodeOrder = computed<string[]>(() => {
  if (!detail.value?.test.groups) return [];

  // 从第一个组的 config_snapshot 中获取 expert_config_code 列表
  for (const group of detail.value.test.groups) {
    const snapshot = group.config_snapshot;
    if (snapshot && snapshot.expert_config_code_list) {
      const codeList = snapshot.expert_config_code_list;
      if (Array.isArray(codeList)) {
        return codeList as string[];
      }
    }
  }
  return [];
});

const criticComparisonData = computed<CriticComparisonRow[]>(() => {
  if (!detail.value?.group_details) return [];

  // 收集所有 expert_func
  const expertFuncs = new Set<string>();
  for (const group of detail.value.group_details) {
    if (group.critic_details) {
      for (const cd of group.critic_details) {
        expertFuncs.add(cd.expert_func);
      }
    }
  }

  // 构建对比数据
  const rows: CriticComparisonRow[] = [];
  for (const func of expertFuncs) {
    const row: CriticComparisonRow = { expert_func: func };
    for (const group of detail.value.group_details) {
      const cd = group.critic_details?.find((d) => d.expert_func === func);
      row[`group_${group.group_name}`] = cd;
    }
    rows.push(row);
  }

  // 按照 expert_config_code_list 的顺序排序
  const orderList = expertConfigCodeOrder.value;
  if (orderList.length > 0) {
    rows.sort((a, b) => {
      // 获取每行的 expert_config_code（从第一个有数据的组中获取）
      const getConfigCode = (row: CriticComparisonRow) => {
        for (const key of Object.keys(row)) {
          if (key.startsWith('group_') && row[key]) {
            const detail = row[key] as ABTestApi.CriticScoreDetail;
            return detail.expert_config_code;
          }
        }
        return '';
      };
      const aCode = getConfigCode(a);
      const bCode = getConfigCode(b);
      // 使用 expert_config_code 进行精确匹配
      const aIdx = orderList.indexOf(aCode);
      const bIdx = orderList.indexOf(bCode);
      // 如果找不到则放到最后
      const aOrder = aIdx === -1 ? 9999 : aIdx;
      const bOrder = bIdx === -1 ? 9999 : bIdx;
      return aOrder - bOrder;
    });
  }

  return rows;
});

// 图表颜色映射（与组颜色保持一致）
const chartColorMap: Record<string, string> = {
  control: '#1890ff',
  experiment_1: '#52c41a',
  experiment_2: '#fa8c16',
  experiment_3: '#722ed1',
  experiment_4: '#13c2c2',
};

function getChartColor(groupName: string): string {
  if (chartColorMap[groupName]) {
    return chartColorMap[groupName];
  }
  const colors = [
    '#1890ff',
    '#52c41a',
    '#fa8c16',
    '#722ed1',
    '#13c2c2',
    '#eb2f96',
  ];
  const index = (groupName.codePointAt(0) ?? 0) % colors.length;
  return colors[index] || '#1890ff';
}

// 渲染折线图
function renderCriticCharts() {
  if (!detail.value?.group_details || criticComparisonData.value.length === 0) {
    return;
  }

  nextTick(() => {
    // X轴数据（Critic Expert 名称）
    const xAxisData = criticComparisonData.value.map((row) => row.expert_func);

    // 获取所有组名
    const groupNames = detail.value!.group_details.map((g) => g.group_name);

    // 准备通过率数据系列
    const passRateSeries = groupNames.map((groupName) => ({
      name: groupName,
      type: 'line' as const,
      data: criticComparisonData.value.map((row) => {
        const cellData = row[`group_${groupName}`] as
          | ABTestApi.CriticScoreDetail
          | undefined;
        return cellData?.pass_rate ?? null;
      }),
      smooth: true,
      symbol: 'circle',
      symbolSize: 8,
      lineStyle: { width: 2 },
      itemStyle: { color: getChartColor(groupName) },
    }));

    // 准备平均分数据系列
    const avgScoreSeries = groupNames.map((groupName) => ({
      name: groupName,
      type: 'line' as const,
      data: criticComparisonData.value.map((row) => {
        const cellData = row[`group_${groupName}`] as
          | ABTestApi.CriticScoreDetail
          | undefined;
        return cellData?.avg_score ?? null;
      }),
      smooth: true,
      symbol: 'circle',
      symbolSize: 8,
      lineStyle: { width: 2 },
      itemStyle: { color: getChartColor(groupName) },
    }));

    // 通用图表配置
    const baseOption = {
      tooltip: {
        trigger: 'axis' as const,
        axisPointer: { type: 'cross' as const },
      },
      legend: {
        data: groupNames,
        bottom: 0,
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '15%',
        top: '10%',
        containLabel: true,
      },
      xAxis: {
        type: 'category' as const,
        boundaryGap: false,
        data: xAxisData,
        axisLabel: {
          rotate: 30,
          fontSize: 11,
          interval: 0,
        },
      },
    };

    // 渲染通过率图表
    if (passRateChartRef.value) {
      if (passRateChart) {
        passRateChart.dispose();
      }
      passRateChart = echarts.init(passRateChartRef.value);
      passRateChart.setOption({
        ...baseOption,
        yAxis: {
          type: 'value' as const,
          name: '通过率 (%)',
          min: 0,
          max: 100,
          axisLabel: { formatter: '{value}%' },
        },
        series: passRateSeries,
      });
    }

    // 渲染平均分图表
    if (avgScoreChartRef.value) {
      if (avgScoreChart) {
        avgScoreChart.dispose();
      }
      avgScoreChart = echarts.init(avgScoreChartRef.value);
      avgScoreChart.setOption({
        ...baseOption,
        yAxis: {
          type: 'value' as const,
          name: '平均分',
          min: 0,
          max: 100,
        },
        series: avgScoreSeries,
      });
    }
  });
}

// 窗口大小变化时重新调整图表
function handleResize() {
  passRateChart?.resize();
  avgScoreChart?.resize();
}

// 初始化
onMounted(() => {
  fetchDetail();
  window.addEventListener('resize', handleResize);
});

// 清理
onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  passRateChart?.dispose();
  avgScoreChart?.dispose();
});

// 监听 testId 变化，重新获取详情
watch(
  () => props.testId,
  (newId, oldId) => {
    if (newId && newId !== oldId) {
      fetchDetail();
    }
  },
);
</script>

<template>
  <div class="ab-test-detail">
    <Spin :spinning="loading">
      <template v-if="detail">
        <!-- 基本信息卡片 -->
        <Card title="测试信息" class="mb-4">
          <Descriptions :column="2" bordered>
            <DescriptionsItem label="测试名称">
              {{ detail.test.test_name }}
            </DescriptionsItem>
            <DescriptionsItem label="测试类型">
              <Tag
                v-if="detail.test.test_type === 'EXPERT_CONFIG'"
                color="blue"
              >
                Expert对比
              </Tag>
              <Tag v-else color="green">Job对比</Tag>
            </DescriptionsItem>
            <DescriptionsItem label="对比组数">
              {{ detail.test.groups.length }} 组
            </DescriptionsItem>
            <DescriptionsItem label="状态">
              <Tag v-if="detail.test.status === 'pending'" color="default">
                待执行
              </Tag>
              <Tag
                v-else-if="detail.test.status === 'running'"
                color="processing"
              >
                执行中
              </Tag>
              <Tag
                v-else-if="detail.test.status === 'analyzing'"
                color="processing"
              >
                分析中
              </Tag>
              <Tag
                v-else-if="detail.test.status === 'completed'"
                color="success"
              >
                已完成
              </Tag>
              <Tag v-else-if="detail.test.status === 'failed'" color="error">
                失败
              </Tag>
            </DescriptionsItem>
            <DescriptionsItem label="创建时间">
              {{ formatDateTime(detail.test.create_time) }}
            </DescriptionsItem>
            <DescriptionsItem label="创建人">
              {{ detail.test.created_by || '-' }}
            </DescriptionsItem>
            <DescriptionsItem v-if="detail.test.remark" label="备注" :span="2">
              {{ detail.test.remark }}
            </DescriptionsItem>
          </Descriptions>
        </Card>

        <!-- 对比组信息 -->
        <Card title="对比组配置" class="mb-4">
          <Row :gutter="16" class="group-row">
            <Col
              v-for="group in detail.test.groups"
              :key="group.group_name"
              :span="Math.floor(24 / detail.test.groups.length)"
              class="group-col"
            >
              <div class="group-card">
                <div
                  class="group-header"
                  :style="{ borderColor: getGroupColor(group.group_name) }"
                >
                  <div class="group-name-wrapper">
                    <Tag :color="getGroupColor(group.group_name)">
                      {{ group.group_name }}
                    </Tag>
                  </div>
                  <span v-if="group.description" class="group-description">
                    {{ group.description }}
                  </span>
                </div>
                <div class="group-body">
                  <!-- 配置快照 -->
                  <template v-if="group.config_snapshot">
                    <div
                      v-for="(value, key) in group.config_snapshot"
                      :key="key"
                      class="config-item"
                      :class="{ 'config-item-vertical': Array.isArray(value) }"
                    >
                      <span class="config-key">{{ key }}:</span>
                      <!-- 数组类型用 Tag 展示，垂直布局放下方 -->
                      <template v-if="Array.isArray(value)">
                        <div class="config-tags">
                          <Tag
                            v-for="(item, idx) in value"
                            :key="idx"
                            class="config-tag"
                          >
                            {{ item }}
                          </Tag>
                        </div>
                      </template>
                      <!-- 非数组类型也用 Tag 展示 -->
                      <template v-else>
                        <div class="config-tags">
                          <Tag class="config-tag config-value-tag">
                            {{ value }}
                          </Tag>
                        </div>
                      </template>
                    </div>
                  </template>
                  <!-- 样本数量 -->
                  <div class="sample-info">
                    <template v-if="detail.test.test_type === 'EXPERT_CONFIG'">
                      <span class="sample-count">
                        {{
                          detail.test.debug_history_ids?.[group.group_name]
                            ?.length || 0
                        }}
                        个调试记录
                      </span>
                    </template>
                    <template v-else>
                      <span class="sample-count">
                        Job:
                        {{ detail.test.job_ids?.[group.group_name] || '-' }}
                      </span>
                    </template>
                  </div>
                </div>
              </div>
            </Col>
          </Row>
        </Card>

        <!-- 统计指标 -->
        <Card
          v-if="detail.test.status === 'completed' && detail.group_details"
          title="统计指标"
          class="mb-4"
        >
          <Row :gutter="16" class="metrics-row">
            <Col
              v-for="groupDetail in detail.group_details"
              :key="groupDetail.group_name"
              :span="Math.floor(24 / detail.group_details.length)"
              class="metrics-col"
            >
              <div
                class="metrics-card"
                :style="{
                  borderColor: getGroupColor(groupDetail.group_name),
                  background: getGroupBgColor(groupDetail.group_name),
                }"
              >
                <div class="metrics-title">
                  <Tag :color="getGroupColor(groupDetail.group_name)">
                    {{ groupDetail.group_name }}
                  </Tag>
                  <span v-if="groupDetail.description" class="metrics-desc">
                    {{ groupDetail.description }}
                  </span>
                </div>
                <div class="metrics-content">
                  <div class="metric-item">
                    <Statistic
                      title="平均时间"
                      :value="groupDetail.metrics.avg_time_ms"
                      suffix="ms"
                    />
                  </div>
                  <div class="metric-item">
                    <Statistic
                      title="平均Token"
                      :value="groupDetail.metrics.avg_tokens"
                    />
                  </div>
                  <div class="metric-item">
                    <Statistic
                      title="平均费用"
                      :value="groupDetail.metrics.avg_cost"
                      :precision="6"
                      prefix="$"
                    />
                  </div>
                  <div class="metric-item">
                    <Statistic
                      title="成功率"
                      :value="groupDetail.metrics.success_rate"
                      suffix="%"
                    />
                  </div>
                  <div class="metric-item">
                    <Statistic
                      title="样本数"
                      :value="groupDetail.metrics.run_count"
                    />
                  </div>
                </div>
              </div>
            </Col>
          </Row>
        </Card>

        <!-- Critic 评分对比（仅 Job 类型） -->
        <Card
          v-if="detail.test.test_type === 'AGENT_JOB' && hasCriticDetails"
          title="Critic 评分对比"
          class="mb-4"
        >
          <Table
            :columns="criticColumns"
            :data-source="criticComparisonData"
            :pagination="false"
            :scroll="{ x: 800 }"
            size="small"
            bordered
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'expert_func'">
                <Tag color="purple">{{ record.expert_func }}</Tag>
              </template>
              <template v-else-if="column.key.startsWith('group_')">
                <div v-if="record[column.key]" class="critic-cell">
                  <div class="critic-score">
                    <span class="score-value">{{
                      record[column.key].avg_score
                    }}</span>
                    <span class="score-label">平均分</span>
                  </div>
                  <div class="critic-rate">
                    <span
                      class="rate-value"
                      :class="[
                        record[column.key].pass_rate >= 80
                          ? 'good'
                          : record[column.key].pass_rate >= 60
                            ? 'medium'
                            : 'poor',
                      ]"
                    >
                      {{ record[column.key].pass_rate }}%
                    </span>
                    <span class="rate-label">通过率</span>
                  </div>
                  <div class="critic-count">
                    <span class="count-pass">{{
                      record[column.key].pass_count
                    }}</span>
                    <span class="count-sep">/</span>
                    <span class="count-total">{{
                      record[column.key].total_count
                    }}</span>
                  </div>
                </div>
                <span v-else class="no-data">-</span>
              </template>
            </template>
          </Table>

          <!-- Critic 评分折线图 -->
          <div v-if="criticComparisonData.length > 0" class="critic-charts">
            <Row :gutter="16">
              <Col :span="12">
                <div class="chart-container">
                  <div class="chart-title">通过率对比</div>
                  <div ref="passRateChartRef" class="chart-content"></div>
                </div>
              </Col>
              <Col :span="12">
                <div class="chart-container">
                  <div class="chart-title">平均分对比</div>
                  <div ref="avgScoreChartRef" class="chart-content"></div>
                </div>
              </Col>
            </Row>
          </div>
        </Card>

        <!-- 样本列表 -->
        <Card title="样本详情">
          <Collapse>
            <CollapsePanel
              v-for="groupDetail in detail.group_details"
              :key="groupDetail.group_name"
              :header="`${groupDetail.group_name} - ${groupDetail.sample_ids.length} 个样本`"
            >
              <div class="sample-list">
                <Tag
                  v-for="sampleId in groupDetail.sample_ids"
                  :key="sampleId"
                  :color="getGroupColor(groupDetail.group_name)"
                >
                  {{ sampleId }}
                </Tag>
              </div>
            </CollapsePanel>
          </Collapse>
        </Card>
      </template>
    </Spin>
  </div>
</template>

<style scoped>
.ab-test-detail {
  padding: 16px;
}

/* 对比组配置样式 */
.group-row {
  display: flex;
  align-items: stretch;
}

.group-col {
  display: flex;
}

.group-card {
  display: flex;
  flex-direction: column;
  width: 100%;
  overflow: hidden;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.group-header {
  display: flex;
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  min-height: 72px;
  padding: 12px 16px;
  background: hsl(var(--muted));
  border-bottom: 2px solid hsl(var(--border));
}

.group-name-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 120px;
  min-height: 32px;
}

.group-name-wrapper :deep(.ant-tag) {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
}

.group-description {
  flex: 1;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.group-body {
  display: flex;
  flex: 1;
  flex-direction: column;
  padding: 12px 16px;
}

.config-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 0;
  font-size: 13px;
  border-bottom: 1px solid hsl(var(--border) / 50%);
}

.config-item:last-of-type {
  border-bottom: none;
}

/* 数组类型（如 expert_config_code_list）使用垂直布局 */
.config-item-vertical {
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
}

.config-key {
  flex-shrink: 0;
  min-width: 100px;
  font-weight: 500;
  line-height: 22px;
  color: hsl(var(--muted-foreground));
}

.config-value {
  font-family: Monaco, Consolas, monospace;
  color: hsl(var(--foreground));
  word-break: break-all;
}

.config-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  width: 100%;
}

.config-tag {
  max-width: 100%;
  margin: 0 !important;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 11px;
  line-height: 1.4;
  white-space: nowrap;
}

.config-value-tag {
  font-family: Monaco, Consolas, monospace;
  font-size: 12px;
  word-break: break-all;
  white-space: normal;
}

.sample-info {
  padding-top: 12px;
  margin-top: auto;
  border-top: 1px dashed hsl(var(--border));
}

.sample-count {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

/* 统计指标样式 */
.metrics-row {
  display: flex;
  align-items: stretch;
}

.metrics-col {
  display: flex;
}

.metrics-card {
  display: flex;
  flex-direction: column;
  width: 100%;
  padding: 16px;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.metrics-title {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}

.metrics-desc {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.metrics-content {
  display: grid;
  flex: 1;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.metric-item {
  display: flex;
  align-items: flex-start;
}

.recommendation-section {
  margin-top: 16px;
}

.sample-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* Critic 评分对比样式 */
.critic-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 0;
}

.critic-score {
  display: flex;
  gap: 4px;
  align-items: baseline;
  justify-content: center;
}

.score-value {
  font-size: 18px;
  font-weight: 600;
  color: hsl(var(--primary));
}

.score-label {
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.critic-rate {
  display: flex;
  gap: 4px;
  align-items: baseline;
  justify-content: center;
}

.rate-value {
  font-size: 14px;
  font-weight: 500;
}

.rate-value.good {
  color: hsl(var(--success, 142 76% 36%));
}

.rate-value.medium {
  color: hsl(var(--warning, 38 92% 50%));
}

.rate-value.poor {
  color: hsl(var(--destructive, 0 84% 60%));
}

.rate-label {
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.critic-count {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.count-pass {
  color: hsl(var(--success, 142 76% 36%));
}

.count-sep {
  margin: 0 2px;
}

.count-total {
  color: hsl(var(--foreground));
}

.no-data {
  color: hsl(var(--muted-foreground));
}

/* 折线图样式 */
.critic-charts {
  padding-top: 24px;
  margin-top: 24px;
  border-top: 1px solid hsl(var(--border));
}

.chart-container {
  padding: 16px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.chart-title {
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 500;
  color: hsl(var(--foreground));
  text-align: center;
}

.chart-content {
  width: 100%;
  height: 300px;
}
</style>
