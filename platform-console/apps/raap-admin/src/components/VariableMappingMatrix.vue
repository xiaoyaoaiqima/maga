<script setup lang="ts">
/**
 * 变量映射矩阵组件
 *
 * 可视化展示策略维度与 Expert 变量的映射关系
 * 支持交互式配置映射
 *
 * 矩阵布局：
 *     维度1   维度2   维度3   ...
 * Expert1.变量1   [X]    [ ]    [X]
 * Expert1.变量2   [ ]    [X]    [ ]
 * Expert2.变量1   [X]    [ ]    [ ]
 */

import { computed, ref } from 'vue';

import {
  CheckSquareOutlined,
  CloseCircleOutlined,
  InfoCircleOutlined,
  QuestionCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons-vue';
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Empty,
  Modal,
  Row,
  Space,
  Tag,
  Tooltip,
} from 'ant-design-vue';

// ==================== 类型定义 ====================

export interface ExpertVariable {
  expert_code: string;
  expert_name: string;
  variables: string[];
}

export interface DimensionInfo {
  dimension_type: string;
  dimension_name: string;
}

export interface VariableMappingItem {
  expert_code: string;
  variable: string;
}

export type MappingMatrix = Record<string, VariableMappingItem[]>;

// ==================== Props ====================

interface Props {
  // Expert 变量列表
  expertVariables: ExpertVariable[];
  // 策略维度列表
  dimensions: DimensionInfo[];
  // 当前的映射配置
  mappings: MappingMatrix;
  // 是否只读模式
  readonly?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  readonly: false,
});

// ==================== Emits ====================

const emit = defineEmits<{
  (e: 'update:mappings', value: MappingMatrix): void;
  (e: 'autoMap'): void;
}>();

// ==================== 状态 ====================

const showLegend = ref(false);
const showUnmappedOnly = ref(false);

// ==================== 计算属性 ====================

// 构建矩阵行：每个 Expert 的每个变量作为一行
const matrixRows = computed(() => {
  const rows: Array<{
    expert_code: string;
    expert_name: string;
    rowKey: string;
    variable: string;
  }> = [];

  for (const expert of props.expertVariables) {
    for (const variable of expert.variables) {
      rows.push({
        expert_code: expert.expert_code,
        expert_name: expert.expert_name,
        variable,
        rowKey: `${expert.expert_code}.${variable}`,
      });
    }
  }

  return rows;
});

// 筛选后的行（仅显示未映射的变量）
const filteredRows = computed(() => {
  if (!showUnmappedOnly.value) return matrixRows.value;

  // 检查变量是否已映射
  return matrixRows.value.filter((row) => {
    return !Object.values(props.mappings).some((mappingItems) =>
      mappingItems.some(
        (m) => m.expert_code === row.expert_code && m.variable === row.variable,
      ),
    );
  });
});

// 获取单元格状态
function getCellStatus(
  dimensionType: string,
  expertCode: string,
  variable: string,
): 'available' | 'mapped' | 'unavailable' {
  // 检查是否已映射
  const mappings = props.mappings[dimensionType] || [];
  const isMapped = mappings.some(
    (m) => m.expert_code === expertCode && m.variable === variable,
  );

  if (isMapped) return 'mapped';

  // 检查是否可以映射（变量名和维度名匹配）
  const dimLower = dimensionType.toLowerCase();
  const varLower = variable.toLowerCase();

  const canMap =
    varLower === dimLower ||
    varLower.includes(dimLower) ||
    dimLower.includes(varLower);

  return canMap ? 'available' : 'unavailable';
}

// 检查是否已映射
function isMapped(
  dimensionType: string,
  expertCode: string,
  variable: string,
): boolean {
  return getCellStatus(dimensionType, expertCode, variable) === 'mapped';
}

// 切换映射
function toggleMapping(
  dimensionType: string,
  expertCode: string,
  variable: string,
) {
  if (props.readonly) return;

  const newMappings = { ...props.mappings };

  if (!newMappings[dimensionType]) {
    newMappings[dimensionType] = [];
  }

  const mappings = newMappings[dimensionType];
  const index = mappings.findIndex(
    (m) => m.expert_code === expertCode && m.variable === variable,
  );

  newMappings[dimensionType] =
    index === -1
      ? [...mappings, { expert_code: expertCode, variable }]
      : mappings.filter(
          (m) => m.expert_code !== expertCode || m.variable !== variable,
        );

  emit('update:mappings', newMappings);
}

// 批量清除映射
function clearMappings() {
  emit('update:mappings', {});
}

// 智能推荐映射
function suggestMappings() {
  emit('autoMap');
}

// 统计信息
const stats = computed(() => {
  let totalCells = 0;
  let mappedCells = 0;
  let availableCells = 0;

  for (const row of matrixRows.value) {
    for (const dim of props.dimensions) {
      totalCells++;
      const status = getCellStatus(
        dim.dimension_type,
        row.expert_code,
        row.variable,
      );
      if (status === 'mapped') mappedCells++;
      else if (status === 'available') availableCells++;
    }
  }

  // 统计每个变量的映射状态
  const mappedVariables = new Set<string>();
  const unmappedVariables: string[] = [];

  for (const row of matrixRows.value) {
    const isVarMapped = Object.values(props.mappings).some((mappingItems) =>
      mappingItems.some(
        (m) => m.expert_code === row.expert_code && m.variable === row.variable,
      ),
    );

    if (isVarMapped) {
      mappedVariables.add(row.rowKey);
    } else {
      unmappedVariables.push(row.rowKey);
    }
  }

  return {
    totalCells,
    mappedCells,
    availableCells,
    totalVariables: matrixRows.value.length,
    mappedVariables: mappedVariables.size,
    unmappedVariables: unmappedVariables.length,
  };
});

// 获取单元格样式类
function getCellClass(status: string): string {
  switch (status) {
    case 'available': {
      return 'cell-available';
    }
    case 'mapped': {
      return 'cell-mapped';
    }
    default: {
      return 'cell-unavailable';
    }
  }
}

// 获取单元格图标
function getCellIcon(status: string) {
  switch (status) {
    case 'available': {
      return null;
    }
    case 'mapped': {
      return CheckSquareOutlined;
    }
    default: {
      return CloseCircleOutlined;
    }
  }
}
</script>

<template>
  <div class="variable-mapping-matrix">
    <!-- 头部工具栏 -->
    <div class="matrix-toolbar">
      <Space>
        <Tooltip title="查看图例说明">
          <Button size="small" @click="showLegend = true">
            <InfoCircleOutlined />
            图例
          </Button>
        </Tooltip>
        <Button
          v-if="!readonly"
          size="small"
          @click="showUnmappedOnly = !showUnmappedOnly"
        >
          {{ showUnmappedOnly ? '显示全部' : '仅显示未映射' }}
        </Button>
        <Button v-if="!readonly" size="small" @click="suggestMappings">
          <SyncOutlined />
          智能推荐
        </Button>
        <Button
          v-if="!readonly && stats.mappedVariables > 0"
          size="small"
          danger
          @click="clearMappings"
        >
          清空映射
        </Button>
      </Space>

      <div class="matrix-stats">
        <Tag color="green">
          已映射: {{ stats.mappedVariables }}/{{ stats.totalVariables }}
        </Tag>
      </div>
    </div>

    <!-- 映射状态警告 -->
    <Alert
      v-if="stats.unmappedVariables > 0"
      type="warning"
      show-icon
      closable
      class="mapping-alert"
    >
      <template #message>
        有
        {{ stats.unmappedVariables }} 个变量尚未映射，可能导致生成内容不符合预期
      </template>
    </Alert>

    <!-- 矩阵主体 -->
    <Card size="small" class="matrix-card">
      <template v-if="matrixRows.length === 0 || dimensions.length === 0">
        <Empty description="暂无数据" />
      </template>

      <div v-else class="matrix-container">
        <Row class="matrix-header" :gutter="[4, 4]">
          <Col :span="6">
            <div class="header-cell header-row-label">Expert 变量</div>
          </Col>
          <Col
            v-for="dim in dimensions"
            :key="dim.dimension_type"
            :span="Math.floor(18 / dimensions.length)"
          >
            <div class="header-cell">
              <Tooltip :title="dim.dimension_name">
                <Tag color="purple" style="margin: 0">
                  {{ dim.dimension_name || dim.dimension_type }}
                </Tag>
              </Tooltip>
            </div>
          </Col>
        </Row>

        <div class="matrix-body">
          <Row
            v-for="row in filteredRows"
            :key="row.rowKey"
            class="matrix-row"
            :gutter="[4, 4]"
          >
            <Col :span="6">
              <div class="row-label">
                <div class="expert-code">{{ row.expert_name }}</div>
                <div class="variable-name">{{ row.variable }}</div>
              </div>
            </Col>
            <Col
              v-for="dim in dimensions"
              :key="dim.dimension_type"
              :span="Math.floor(18 / dimensions.length)"
            >
              <div
                class="matrix-cell"
                :class="[
                  getCellClass(
                    getCellStatus(
                      dim.dimension_type,
                      row.expert_code,
                      row.variable,
                    ),
                  ),
                ]"
                @click="
                  toggleMapping(
                    dim.dimension_type,
                    row.expert_code,
                    row.variable,
                  )
                "
              >
                <template v-if="readonly">
                  <component
                    :is="
                      getCellIcon(
                        getCellStatus(
                          dim.dimension_type,
                          row.expert_code,
                          row.variable,
                        ),
                      )
                    "
                    class="cell-icon"
                  />
                </template>
                <Checkbox
                  v-else
                  :checked="
                    isMapped(dim.dimension_type, row.expert_code, row.variable)
                  "
                  :disabled="
                    getCellStatus(
                      dim.dimension_type,
                      row.expert_code,
                      row.variable,
                    ) === 'unavailable'
                  "
                />
              </div>
            </Col>
          </Row>
        </div>
      </div>
    </Card>

    <!-- 图例弹窗 -->
    <Modal
      v-model:open="showLegend"
      title="矩阵图例说明"
      :footer="null"
      width="500"
    >
      <div class="legend-content">
        <div class="legend-item">
          <div class="legend-cell cell-mapped">
            <CheckSquareOutlined class="cell-icon" />
          </div>
          <div class="legend-text">
            <div class="legend-title">已映射</div>
            <div class="legend-desc">该变量已映射到此维度</div>
          </div>
        </div>
        <div class="legend-item">
          <div class="legend-cell cell-available">
            <Checkbox />
          </div>
          <div class="legend-text">
            <div class="legend-title">可映射</div>
            <div class="legend-desc">变量名与维度名匹配，可以建立映射</div>
          </div>
        </div>
        <div class="legend-item">
          <div class="legend-cell cell-unavailable">
            <CloseCircleOutlined class="cell-icon" />
          </div>
          <div class="legend-text">
            <div class="legend-title">不可映射</div>
            <div class="legend-desc">变量名与维度名不匹配，不建议建立映射</div>
          </div>
        </div>

        <div class="legend-tips">
          <div class="tips-title">
            <QuestionCircleOutlined />
            使用提示
          </div>
          <ul class="tips-list">
            <li>点击单元格可以切换映射状态</li>
            <li>一个变量只能映射到一个维度</li>
            <li>建议使用"智能推荐"自动匹配变量和维度</li>
            <li>绿色表示已建立映射，黄色表示可建立映射</li>
          </ul>
        </div>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.variable-mapping-matrix {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 工具栏 */
.matrix-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.matrix-stats {
  display: flex;
  gap: 8px;
}

.mapping-alert {
  margin: 0;
}

/* 矩阵卡片 */
.matrix-card {
  overflow: hidden;
}

.matrix-container {
  overflow-x: auto;
}

/* 表头 */
.matrix-header {
  padding-bottom: 8px;
  margin-bottom: 8px;
  border-bottom: 2px solid hsl(var(--border));
}

.header-cell {
  font-size: 13px;
  font-weight: 600;
  text-align: center;
}

.header-row-label {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

/* 表格行 */
.matrix-row {
  padding: 4px 0;
  border-bottom: 1px solid hsl(var(--border) / 50%);
}

.matrix-row:last-child {
  border-bottom: none;
}

.row-label {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px 8px;
}

.expert-code {
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.variable-name {
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

/* 单元格 */
.matrix-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 36px;
  aspect-ratio: 1;
  font-size: 16px;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s ease;
}

.matrix-cell:hover {
  opacity: 0.8;
  transform: scale(1.05);
}

.cell-mapped {
  color: hsl(var(--success));
  background: hsl(var(--success) / 15%);
}

.cell-available {
  color: hsl(var(--warning));
  background: hsl(var(--warning) / 10%);
}

.cell-available:hover {
  background: hsl(var(--warning) / 20%);
}

.cell-unavailable {
  color: hsl(var(--muted-foreground));
  cursor: not-allowed;
  background: hsl(var(--muted) / 50%);
}

.cell-unavailable:hover {
  transform: none;
}

.cell-icon {
  font-size: 14px;
}

/* 图例 */
.legend-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.legend-item {
  display: flex;
  gap: 12px;
  align-items: center;
}

.legend-cell {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 4px;
}

.legend-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.legend-title {
  font-size: 14px;
  font-weight: 600;
}

.legend-desc {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.legend-tips {
  padding: 12px;
  margin-top: 8px;
  background: hsl(var(--muted) / 30%);
  border-radius: 6px;
}

.tips-title {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}

.tips-list {
  padding-left: 20px;
  margin: 0;
  font-size: 13px;
  line-height: 1.8;
  color: hsl(var(--muted-foreground));
}

.tips-list li {
  margin: 0;
}
</style>
