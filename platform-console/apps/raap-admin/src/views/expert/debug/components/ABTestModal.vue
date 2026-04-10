<script setup lang="ts">
import type { FormInstance } from 'ant-design-vue';

import { computed, reactive, ref, watch } from 'vue';

import {
  Alert,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Modal,
  Switch,
  Tag,
  Textarea,
} from 'ant-design-vue';

import { ABTestApi } from '#/api/core/ab-test';

interface CompareGroup {
  name?: string;
  config_code?: string;
  variables?: Array<Record<string, unknown>>;
  modelOverride?: {
    enabled?: boolean;
    max_tokens?: number;
    model_code?: string;
    temperature?: number;
  };
}

interface GroupConfig {
  group_name: string;
  config_code: string;
  config_name: string;
  model_code?: string;
  variables?: Array<Record<string, unknown>>;
  llm_config?: Record<string, unknown>;
}

const props = defineProps<{
  compareGroups: CompareGroup[];
  expertCode: string;
  inputContent: string;
  open?: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void;
  (e: 'success', testId: string): void;
}>();

const formRef = ref<FormInstance>();
const submitting = ref(false);

// 表单数据
const formData = ref({
  test_name: '',
  execution_count: 5,
  test_content: props.inputContent || '',
  auto_execute: true,
  remark: '',
  groups: [] as GroupConfig[],
});

// 流量分配
const trafficRatios = reactive<Record<string, number>>({});

// 弹窗显示控制
const visible = computed({
  get: () => props.open ?? false,
  set: (val) => emit('update:open', val),
});

// 颜色配置
const groupColors = ['blue', 'green', 'orange', 'purple', 'cyan', 'magenta'];
const groupColorHexes = [
  '#1890ff',
  '#52c41a',
  '#fa8c16',
  '#722ed1',
  '#13c2c2',
  '#eb2f96',
];

function getGroupColor(index: number): string {
  return groupColors[index % groupColors.length] || 'default';
}

function getGroupColorHex(index: number): string {
  return groupColorHexes[index % groupColorHexes.length] || '#1890ff';
}

// 初始化组数据
function initGroups() {
  const groups: GroupConfig[] = [];
  const ratios: Record<string, number> = {};

  props.compareGroups.forEach((group, index) => {
    const groupName = index === 0 ? 'control' : `experiment_${index}`;
    const configName =
      group.name || (index === 0 ? '对照组' : `实验组${index}`);

    groups.push({
      group_name: groupName,
      config_code: group.config_code || props.expertCode,
      config_name: configName,
      model_code: group.modelOverride?.model_code,
      variables: group.variables,
      llm_config: group.modelOverride?.enabled
        ? {
            temperature: group.modelOverride.temperature,
            max_tokens: group.modelOverride.max_tokens,
          }
        : undefined,
    });

    // 均分流量
    ratios[groupName] = Math.floor(100 / props.compareGroups.length);
  });

  // 确保流量总和为100
  const groupNames = Object.keys(ratios);
  if (groupNames.length > 0) {
    const total = Object.values(ratios).reduce((a, b) => a + b, 0);
    ratios[groupNames[groupNames.length - 1]] += 100 - total;
  }

  formData.value.groups = groups;
  Object.assign(trafficRatios, ratios);
}

// 处理流量变化
function handleTrafficChange(changedGroup: string) {
  const groupNames = formData.value.groups.map((g) => g.group_name);
  const total = groupNames.reduce(
    (sum, name) => sum + (trafficRatios[name] || 0),
    0,
  );

  // 如果超过100，调整最后一个组
  if (total > 100) {
    const otherGroups = groupNames.filter((name) => name !== changedGroup);
    if (otherGroups.length > 0) {
      const lastGroup = otherGroups[otherGroups.length - 1];
      const excess = total - 100;
      trafficRatios[lastGroup] = Math.max(
        0,
        (trafficRatios[lastGroup] || 0) - excess,
      );
    }
  }
}

// 执行计划预览
const executionPlan = computed(() => {
  if (!formData.value.execution_count || formData.value.groups.length === 0) {
    return null;
  }

  const total = formData.value.execution_count;
  const groupRuns: Record<string, number> = {};
  let allocated = 0;
  const groupNames = formData.value.groups.map((g) => g.group_name);

  groupNames.forEach((name, index) => {
    const ratio = trafficRatios[name] || 0;
    if (index === groupNames.length - 1) {
      groupRuns[name] = total - allocated;
    } else {
      const runs = Math.round((total * ratio) / 100);
      groupRuns[name] = runs;
      allocated += runs;
    }
  });

  return { total, groupRuns };
});

// 提交表单
async function handleSubmit() {
  try {
    await formRef.value?.validate();

    if (formData.value.groups.length < 2) {
      message.error('至少需要 2 个对比组');
      return;
    }

    // 验证流量分配
    const totalRatio = Object.values(trafficRatios).reduce((a, b) => a + b, 0);
    if (totalRatio !== 100) {
      message.error(`流量分配总和必须为100%，当前为${totalRatio}%`);
      return;
    }

    submitting.value = true;

    // 构建请求数据
    const configs: ABTestApi.ABTestGroupConfig[] = formData.value.groups.map(
      (g) => ({
        group_name: g.group_name,
        config_code: g.config_code,
        config_name: g.config_name,
        model_code: g.model_code,
        variables: g.variables,
        llm_config: g.llm_config,
      }),
    );

    const trafficAllocation: Record<string, number> = {};
    formData.value.groups.forEach((g) => {
      trafficAllocation[g.group_name] = trafficRatios[g.group_name] || 0;
    });

    // 调用执行 API
    const result = await ABTestApi.executeExpertTest({
      test_name: formData.value.test_name,
      configs,
      traffic_allocation: trafficAllocation,
      test_content: formData.value.test_content,
      execution_count: formData.value.execution_count,
      auto_execute: formData.value.auto_execute,
      remark: formData.value.remark,
    });

    message.success(
      formData.value.auto_execute ? 'AB测试已创建并开始执行' : 'AB测试已创建',
    );
    visible.value = false;
    emit('success', result.test_id);
  } catch (error: unknown) {
    console.error('创建AB测试失败:', error);
    message.error((error as Error)?.message || '创建失败');
  } finally {
    submitting.value = false;
  }
}

// 监听 compareGroups 变化
watch(
  () => props.compareGroups,
  () => {
    initGroups();
  },
  { immediate: true, deep: true },
);

// 监听输入内容变化
watch(
  () => props.inputContent,
  (val) => {
    formData.value.test_content = val || '';
  },
);

// 重置表单
watch(visible, (val) => {
  if (val) {
    formData.value.test_name = '';
    formData.value.execution_count = 5;
    formData.value.auto_execute = true;
    formData.value.remark = '';
    formData.value.test_content = props.inputContent || '';
    initGroups();
  }
});
</script>

<template>
  <Modal
    v-model:open="visible"
    title="创建AB测试"
    :width="800"
    :confirm-loading="submitting"
    @ok="handleSubmit"
  >
    <Form
      ref="formRef"
      :model="formData"
      :label-col="{ span: 6 }"
      :wrapper-col="{ span: 18 }"
    >
      <FormItem label="测试名称" name="test_name" :rules="[{ required: true }]">
        <Input
          v-model:value="formData.test_name"
          placeholder="请输入测试名称，如：Prompt V1 vs V2对比测试"
        />
      </FormItem>

      <FormItem label="执行次数" name="execution_count">
        <InputNumber
          v-model:value="formData.execution_count"
          :min="1"
          :max="50"
          style="width: 100%"
        />
        <div class="form-hint">执行次数越多，统计结果越准确（建议至少5次）</div>
      </FormItem>

      <FormItem label="流量分配">
        <div class="traffic-allocation">
          <div
            v-for="(group, index) in formData.groups"
            :key="group.group_name"
            class="allocation-row"
          >
            <Tag :color="getGroupColor(index)">{{ group.group_name }}</Tag>
            <span class="config-name">{{ group.config_name }}</span>
            <InputNumber
              v-model:value="trafficRatios[group.group_name]"
              :min="0"
              :max="100"
              :precision="0"
              style="width: 100px"
              :formatter="(value: number | string) => `${value}%`"
              :parser="(value: string) => Number(value.replace('%', ''))"
              @change="() => handleTrafficChange(group.group_name)"
            />
          </div>
        </div>
        <div class="form-hint">
          流量分配决定各配置组的执行次数比例，总和需为100%
        </div>
      </FormItem>

      <FormItem label="配置预览">
        <div class="configs-preview">
          <div
            v-for="(group, index) in formData.groups"
            :key="group.group_name"
            class="config-card"
          >
            <div
              class="config-header"
              :style="{ borderLeftColor: getGroupColorHex(index) }"
            >
              <Tag :color="getGroupColor(index)">{{ group.group_name }}</Tag>
              <span>{{ group.config_name }}</span>
            </div>
            <div class="config-body">
              <div><strong>编码:</strong> {{ group.config_code }}</div>
              <div v-if="group.model_code">
                <strong>模型:</strong> {{ group.model_code }}
              </div>
            </div>
          </div>
        </div>
      </FormItem>

      <FormItem label="测试内容" name="test_content">
        <Textarea
          v-model:value="formData.test_content"
          :rows="4"
          placeholder="输入测试内容（可选）"
        />
      </FormItem>

      <FormItem label="立即执行">
        <Switch
          v-model:checked="formData.auto_execute"
          checked-children="是"
          un-checked-children="否"
        />
        <div class="form-hint">开启后将立即执行测试，否则仅创建测试任务</div>
      </FormItem>

      <FormItem label="备注" name="remark">
        <Textarea
          v-model:value="formData.remark"
          :rows="2"
          placeholder="测试备注（可选）"
        />
      </FormItem>
    </Form>

    <!-- 预览执行计划 -->
    <div v-if="executionPlan" class="execution-plan">
      <Alert message="执行计划预览" type="info" show-icon>
        <template #description>
          <div>总执行次数: {{ executionPlan.total }}</div>
          <div
            v-for="(runs, groupName) in executionPlan.groupRuns"
            :key="groupName"
          >
            {{ groupName }}: {{ runs }} 次
          </div>
        </template>
      </Alert>
    </div>
  </Modal>
</template>

<style scoped>
.form-hint {
  margin-top: 4px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.traffic-allocation {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.allocation-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

.config-name {
  flex: 1;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.configs-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.config-card {
  flex: 1;
  min-width: 200px;
  overflow: hidden;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.config-header {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  background: hsl(var(--muted));
  border-left: 3px solid;
}

.config-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  font-size: 13px;
}

.execution-plan {
  margin-top: 16px;
}
</style>
