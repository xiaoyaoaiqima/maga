<script setup lang="ts">
/**
 * 变量映射配置弹窗
 *
 * 功能：
 * 1. 选择关键词策略
 * 2. 配置插件变量到策略维度的映射
 * 3. 预览映射结果
 */
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import {
  ApiOutlined,
  CheckCircleOutlined,
  InfoCircleOutlined,
  LinkOutlined,
  PlusOutlined,
  TagOutlined,
} from '@ant-design/icons-vue';
import {
  Alert,
  Button,
  Descriptions,
  DescriptionsItem,
  Empty,
  Form,
  FormItem,
  message,
  Modal,
  Select,
  SelectOption,
  Space,
  Spin,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import {
  createContentStrategyApi,
  getContentStrategiesApi,
} from '#/api/core/content-strategy';
import { requestClient } from '#/api/request';

// ==================== 类型定义 ====================

interface Plugin {
  id: number;
  plugin_code: string;
  plugin_name: string;
  variable_list: null | string[];
  strategy_id: null | number;
  variable_mappings: Array<{ label: string; variable_name: string }> | null;
  tenant_code: string;
}

// v3 节点池配置
interface NodePoolConfig {
  node_ids: string[];
  select_mode: 'multiple' | 'single';
}

interface ContentStrategy {
  id: string;
  name: string;
  // v3 新格式
  node_pools?: Record<string, NodePoolConfig | string[]>; // 兼容新旧格式
  // v1 旧格式（保留向后兼容）
  dimensions?: Array<{
    dimension_name: string;
    dimension_type: string;
    node_ids: string[];
  }>;
}

interface VariableMapping {
  variable_name: string;
  label: string;
}

// ==================== Props & Emits ====================

const props = defineProps<{
  open: boolean;
  plugin: null | Plugin;
}>();

const emit = defineEmits<{
  (e: 'saved'): void;
  (e: 'update:open', value: boolean): void;
}>();

// ==================== 状态 ====================

const router = useRouter();
const loading = ref(false);
const submitting = ref(false);

// 策略选择
const strategies = ref<ContentStrategy[]>([]);
const strategiesLoading = ref(false);
const selectedStrategyId = ref<string | undefined>(undefined);

// 变量映射
const variableMappings = ref<VariableMapping[]>([]);

// 快速创建策略
const quickCreateStrategyVisible = ref(false);
const quickCreateStrategyLoading = ref(false);
const quickCreateStrategyForm = ref({
  name: '',
  description: '',
});

// ==================== 计算属性 ====================

// 当前选中的策略
const selectedStrategy = computed(() => {
  if (!selectedStrategyId.value) return null;
  return strategies.value.find((s) => s.id === selectedStrategyId.value);
});

// 策略中可用的维度（label）
const availableDimensions = computed<string[]>(() => {
  if (!selectedStrategy.value) return [];

  // v2: 从 node_pools 获取
  if (selectedStrategy.value.node_pools) {
    return Object.keys(selectedStrategy.value.node_pools);
  }

  // 从 node_pools 获取维度
  const nodePools = selectedStrategy.value.node_pools;
  if (nodePools) {
    return Object.keys(nodePools);
  }

  return [];
});

// 插件的变量列表
const pluginVariables = computed(() => {
  return props.plugin?.variable_list || [];
});

// 是否可以保存
const canSave = computed(() => {
  // 必须选择策略
  if (!selectedStrategyId.value) return false;

  // 至少有一个映射
  return variableMappings.value.some((m) => m.label);
});

// ==================== 方法 ====================

// 加载策略列表
async function loadStrategies() {
  if (!props.plugin) return;

  strategiesLoading.value = true;
  try {
    const res = await getContentStrategiesApi({
      tenant_code: props.plugin.tenant_code || 'default',
      is_active: 1,
      page_size: 100,
    });
    strategies.value = res.items || [];
  } catch (error) {
    console.error('加载策略列表失败:', error);
    message.error('加载策略列表失败');
  } finally {
    strategiesLoading.value = false;
  }
}

// 初始化表单
function initForm() {
  if (!props.plugin) return;

  // 设置已选策略
  selectedStrategyId.value = props.plugin.strategy_id?.toString() || undefined;

  // 初始化变量映射
  const existingMappings = props.plugin.variable_mappings || [];
  const variables = props.plugin.variable_list || [];

  variableMappings.value = variables.map((varName) => {
    // 查找已有的映射
    const existing = existingMappings.find((m) => m.variable_name === varName);
    return {
      variable_name: varName,
      label: existing?.label || '',
    };
  });
}

// 保存配置
async function handleSave() {
  if (!props.plugin || !canSave.value) return;

  submitting.value = true;
  try {
    // 过滤出有效的映射
    const validMappings = variableMappings.value.filter((m) => m.label);

    await requestClient.put(`/v1/plugins/${props.plugin.id}`, {
      strategy_id: selectedStrategyId.value
        ? Number.parseInt(selectedStrategyId.value)
        : null,
      variable_mappings: validMappings,
    });

    message.success('变量映射配置保存成功');
    emit('saved');
    emit('update:open', false);
  } catch (error) {
    console.error('保存失败:', error);
    message.error('保存失败，请重试');
  } finally {
    submitting.value = false;
  }
}

// 解除绑定
async function handleUnbind() {
  if (!props.plugin) return;

  Modal.confirm({
    title: '确认解除映射',
    content: '解除映射后，该插件将不再使用策略中的关键词语料。确定继续吗？',
    okText: '确定解除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      submitting.value = true;
      try {
        await requestClient.put(`/v1/plugins/${props.plugin!.id}`, {
          strategy_id: null,
          variable_mappings: null,
        });

        message.success('已解除策略映射');
        emit('saved');
        emit('update:open', false);
      } catch (error) {
        console.error('解除映射失败:', error);
        message.error('解除映射失败');
      } finally {
        submitting.value = false;
      }
    },
  });
}

// 快速创建策略
function openQuickCreateStrategy() {
  quickCreateStrategyForm.value = {
    name: '',
    description: '',
  };
  quickCreateStrategyVisible.value = true;
}

async function submitQuickCreateStrategy() {
  const form = quickCreateStrategyForm.value;

  if (!form.name.trim()) {
    message.error('请输入策略名称');
    return;
  }

  quickCreateStrategyLoading.value = true;
  try {
    const res = await createContentStrategyApi({
      name: form.name.trim(),
      description: form.description.trim() || undefined,
      tenant_code: props.plugin?.tenant_code || 'default',
      node_pools: {}, // 初始为空，稍后在策略管理页面配置
    });

    message.success({
      content: '策略创建成功！建议稍后在策略管理页面配置维度。',
      duration: 4,
    });

    // 刷新策略列表
    await loadStrategies();

    // 关闭创建弹窗
    quickCreateStrategyVisible.value = false;

    // 自动选中新创建的策略
    if (res?.id) {
      selectedStrategyId.value = res.id.toString();
    }
  } catch (error: any) {
    const errorMsg = error?.response?.data?.detail || '创建策略失败';
    message.error(errorMsg);
  } finally {
    quickCreateStrategyLoading.value = false;
  }
}

// 跳转到新链路配置页面
function goToStrategyManagement() {
  router.push('/content-agent/system-prompt-keywords');
}

// 获取策略中某维度的节点数量
function getDimensionNodeCount(label: string): number {
  if (!selectedStrategy.value) return 0;

  if (selectedStrategy.value.node_pools) {
    const pool = selectedStrategy.value.node_pools[label];
    if (!pool) return 0;
    // 兼容 v3 新格式（对象）和旧格式（数组）
    if (Array.isArray(pool)) {
      return pool.length;
    }
    // v3 格式: { node_ids: [...], select_mode: "..." }
    return pool.node_ids?.length || 0;
  }

  if (selectedStrategy.value.dimensions) {
    const dim = selectedStrategy.value.dimensions.find(
      (d) => d.dimension_type === label,
    );
    return dim?.node_ids?.length || 0;
  }

  return 0;
}

// ==================== 监听 ====================

watch(
  () => props.open,
  async (newVal) => {
    if (newVal) {
      loading.value = true;
      await loadStrategies();
      initForm();
      loading.value = false;
    }
  },
  { immediate: true },
);

// 自动映射同名变量到维度
function autoMapMatchingVariables() {
  if (!selectedStrategyId.value || availableDimensions.value.length === 0) {
    return;
  }

  let autoMappedCount = 0;

  for (const mapping of variableMappings.value) {
    // 如果变量已有映射，跳过
    if (mapping.label) continue;

    // 检查变量名是否与某个维度名完全匹配
    const matchedDimension = availableDimensions.value.find(
      (dim) => dim === mapping.variable_name,
    );

    if (matchedDimension) {
      mapping.label = matchedDimension;
      autoMappedCount++;
    }
  }

  // 如果有自动映射的，给用户一个提示
  if (autoMappedCount > 0) {
    message.success(`已自动映射 ${autoMappedCount} 个同名变量`);
  }
}

// 策略变更时重新检查映射
watch(selectedStrategyId, () => {
  // 清除不在新策略中的映射
  for (const mapping of variableMappings.value) {
    if (mapping.label && !availableDimensions.value.includes(mapping.label)) {
      mapping.label = '';
    }
  }

  // 自动映射同名变量
  autoMapMatchingVariables();
});
</script>

<template>
  <Modal
    :open="open"
    title="🔗 策略映射配置"
    width="680px"
    :confirm-loading="submitting"
    @update:open="emit('update:open', $event)"
    @cancel="emit('update:open', false)"
  >
    <template #footer>
      <div class="modal-footer">
        <div class="footer-left">
          <Button
            v-if="plugin?.strategy_id"
            type="text"
            danger
            :disabled="submitting"
            @click="handleUnbind"
          >
            解除映射
          </Button>
        </div>
        <div class="footer-right">
          <Button :disabled="submitting" @click="emit('update:open', false)">
            取消
          </Button>
          <Button
            type="primary"
            :disabled="!canSave"
            :loading="submitting"
            @click="handleSave"
          >
            保存配置
          </Button>
        </div>
      </div>
    </template>

    <Spin :spinning="loading">
      <div class="mapping-content">
        <!-- 插件信息 -->
        <div class="plugin-info">
          <Descriptions :column="2" size="small" bordered>
            <DescriptionsItem label="插件编码">
              <code>{{ plugin?.plugin_code }}</code>
            </DescriptionsItem>
            <DescriptionsItem label="插件名称">
              {{ plugin?.plugin_name }}
            </DescriptionsItem>
          </Descriptions>
        </div>

        <!-- 策略选择 -->
        <div class="section">
          <div class="section-title">
            <LinkOutlined />
            <span>选择关键词策略</span>
            <Button
              type="link"
              size="small"
              class="strategy-manage-link"
              @click="goToStrategyManagement"
            >
              策略管理 →
            </Button>
          </div>
          <div class="strategy-select-row">
            <Select
              v-model:value="selectedStrategyId"
              placeholder="请选择要映射的关键词策略"
              style="flex: 1"
              :loading="strategiesLoading"
              allow-clear
              show-search
              option-filter-prop="label"
              option-label-prop="label"
              :not-found-content="strategies.length === 0 ? undefined : null"
              :get-popup-container="(trigger) => trigger.parentElement"
            >
              <template #notFoundContent>
                <div class="strategy-empty">
                  <span>暂无可用策略</span>
                  <Button
                    type="link"
                    size="small"
                    @click="openQuickCreateStrategy"
                  >
                    <PlusOutlined /> 创建一个
                  </Button>
                </div>
              </template>
              <SelectOption
                v-for="strategy in strategies"
                :key="strategy.id"
                :value="strategy.id"
                :label="strategy.name"
              >
                <div class="strategy-option">
                  <span class="strategy-name">{{ strategy.name }}</span>
                  <span class="strategy-dims">
                    {{
                      strategy.node_pools
                        ? `${Object.keys(strategy.node_pools).length} 个维度`
                        : strategy.dimensions
                          ? `${strategy.dimensions.length} 个维度`
                          : '无维度'
                    }}
                  </span>
                </div>
              </SelectOption>
            </Select>
            <Tooltip title="快速创建策略">
              <Button type="primary" ghost @click="openQuickCreateStrategy">
                <PlusOutlined />
              </Button>
            </Tooltip>
          </div>
        </div>

        <!-- 策略信息预览 -->
        <div v-if="selectedStrategy" class="section strategy-preview">
          <div class="section-title">
            <InfoCircleOutlined />
            <span>策略维度</span>
          </div>
          <div class="dimensions-list">
            <Tag
              v-for="dim in availableDimensions"
              :key="dim"
              color="blue"
              class="dimension-tag"
            >
              {{ dim }}
              <span class="dim-count">({{ getDimensionNodeCount(dim) }})</span>
            </Tag>
          </div>
        </div>

        <!-- 变量映射配置 -->
        <div v-if="pluginVariables.length > 0" class="section">
          <div class="section-title">
            <ApiOutlined />
            <span>变量映射</span>
            <Tooltip
              title="将插件模板中的变量映射到策略的维度，运行时会从该维度的节点池中随机选择语料"
            >
              <InfoCircleOutlined class="help-icon" />
            </Tooltip>
          </div>

          <Alert
            v-if="!selectedStrategyId"
            type="info"
            message="请先选择关键词策略，然后配置变量映射"
            show-icon
            class="mapping-alert"
          />

          <div v-else class="mapping-list">
            <Form layout="vertical">
              <div
                v-for="mapping in variableMappings"
                :key="mapping.variable_name"
                class="mapping-item"
              >
                <div class="mapping-variable">
                  <TagOutlined class="var-icon" />
                  <code class="var-name">{{ mapping.variable_name }}</code>
                </div>
                <div class="mapping-arrow">→</div>
                <FormItem
                  class="mapping-select"
                  :validate-status="mapping.label ? 'success' : ''"
                >
                  <Select
                    v-model:value="mapping.label"
                    placeholder="选择维度"
                    style="width: 200px"
                    allow-clear
                    show-search
                    :filter-option="true"
                    :get-popup-container="(trigger) => trigger.parentElement"
                  >
                    <SelectOption
                      v-for="dim in availableDimensions"
                      :key="dim"
                      :value="dim"
                    >
                      {{ dim }}
                      <span class="dim-node-count">
                        ({{ getDimensionNodeCount(dim) }} 个节点)
                      </span>
                    </SelectOption>
                  </Select>
                </FormItem>
                <CheckCircleOutlined v-if="mapping.label" class="mapping-ok" />
              </div>
            </Form>
          </div>
        </div>

        <!-- 无变量提示 -->
        <Empty
          v-else
          description="该插件没有定义变量，无需配置映射"
          :image="Empty.PRESENTED_IMAGE_SIMPLE"
        />

        <!-- 配置预览 -->
        <div
          v-if="selectedStrategyId && variableMappings.some((m) => m.label)"
          class="section preview-section"
        >
          <div class="section-title">
            <CheckCircleOutlined />
            <span>配置预览</span>
          </div>
          <div class="preview-content">
            <div class="preview-item">
              <span class="preview-label">映射策略：</span>
              <Tag color="success">{{ selectedStrategy?.name }}</Tag>
            </div>
            <div class="preview-item">
              <span class="preview-label">变量映射：</span>
              <Space :size="4" wrap>
                <template
                  v-for="m in variableMappings.filter((x) => x.label)"
                  :key="m.variable_name"
                >
                  <Tag>
                    <code>{{ m.variable_name }}</code> → {{ m.label }}
                  </Tag>
                </template>
              </Space>
            </div>
          </div>
        </div>
      </div>
    </Spin>
  </Modal>

  <!-- 快速创建策略弹窗 -->
  <Modal
    v-model:open="quickCreateStrategyVisible"
    title="快速创建策略"
    :width="480"
    :confirm-loading="quickCreateStrategyLoading"
    @ok="submitQuickCreateStrategy"
    @cancel="quickCreateStrategyVisible = false"
  >
    <Form layout="vertical" class="quick-create-strategy-form">
      <FormItem
        label="策略名称"
        required
        :validate-status="!quickCreateStrategyForm.name ? 'error' : ''"
      >
        <input
          v-model="quickCreateStrategyForm.name"
          class="ant-input"
          placeholder="如: 双11皇家美素佳儿策略"
        />
      </FormItem>

      <FormItem label="描述（可选）">
        <textarea
          v-model="quickCreateStrategyForm.description"
          class="ant-input"
          placeholder="策略的用途说明..."
          :rows="3"
        ></textarea>
      </FormItem>

      <div class="quick-create-hint">
        <InfoCircleOutlined />
        <span>
          快速创建的策略不包含维度配置，创建后请在
          <Button type="link" size="small" @click="goToStrategyManagement">
            策略管理页面
          </Button>
          完善维度和节点池配置。
        </span>
      </div>
    </Form>
  </Modal>
</template>

<style scoped>
.mapping-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 8px 0;
}

.plugin-info {
  margin-bottom: 8px;
}

.section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-title {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 14px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.help-icon {
  color: hsl(var(--muted-foreground));
  cursor: help;
}

.strategy-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.strategy-name {
  font-weight: 500;
}

.strategy-dims {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.strategy-preview {
  padding: 12px 16px;
  background: hsl(var(--muted) / 50%);
  border-radius: 8px;
}

.dimensions-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.dimension-tag {
  font-size: 13px;
}

.dim-count {
  margin-left: 4px;
  font-size: 11px;
  opacity: 0.7;
}

.mapping-alert {
  margin-bottom: 0;
}

.mapping-list {
  max-height: 400px;
  padding: 16px;
  overflow-y: auto;
  background: hsl(var(--muted) / 30%);
  border-radius: 8px;
}

.mapping-item {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 8px 0;
}

.mapping-item:not(:last-child) {
  border-bottom: 1px dashed hsl(var(--border));
}

.mapping-variable {
  display: flex;
  gap: 6px;
  align-items: center;
  min-width: 140px;
}

.var-icon {
  color: hsl(var(--primary));
}

.var-name {
  padding: 2px 8px;
  font-size: 13px;
  background: hsl(var(--muted));
  border-radius: 4px;
}

.mapping-arrow {
  font-size: 16px;
  color: hsl(var(--muted-foreground));
}

.mapping-select {
  flex: 1;
  margin-bottom: 0 !important;
}

.mapping-ok {
  font-size: 16px;
  color: #52c41a;
}

.dim-node-count {
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.preview-section {
  padding: 16px;
  background: hsl(var(--success) / 10%);
  border: 1px solid hsl(var(--success) / 30%);
  border-radius: 8px;
}

.preview-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.preview-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.preview-label {
  flex-shrink: 0;
  min-width: 80px;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.modal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.footer-left {
  flex-shrink: 0;
}

.footer-right {
  display: flex;
  gap: 8px;
}

/* Descriptions 适配 */
:deep(.ant-descriptions-item-label) {
  width: 80px;
}

:deep(.ant-descriptions-item-content code) {
  padding: 2px 6px;
  font-size: 12px;
  background: hsl(var(--muted));
  border-radius: 4px;
}

/* 策略选择增强 */
.strategy-select-row {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.strategy-manage-link {
  padding: 0;
  margin-left: auto;
  font-size: 12px;
}

.strategy-empty {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
  padding: 8px;
  color: hsl(var(--muted-foreground));
}

/* 快速创建策略表单 */
.quick-create-strategy-form {
  padding: 8px 0;
}

.quick-create-hint {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 12px;
  margin-top: 8px;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--warning) / 10%);
  border: 1px solid hsl(var(--warning) / 30%);
  border-radius: 6px;
}

.quick-create-hint .anticon {
  margin-top: 2px;
  color: hsl(var(--warning));
}
</style>
