<script setup lang="ts">
import type { LLMApi } from '#/api/core/llm';

/**
 * 通用模型选择组件
 * 功能：按 Provider 分组展示可用模型，支持价格显示、快速搜索
 */
import { computed, h, onMounted, ref } from 'vue';

import { Select, Tag, Tooltip } from 'ant-design-vue';

import { getProviderListApi, getRouteListApi } from '#/api/core/llm';

interface Props {
  value?: string;
  placeholder?: string;
  size?: 'large' | 'middle' | 'small';
  style?: any;
  disabled?: boolean;
  allowClear?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  value: '',
  placeholder: '请选择模型',
  size: 'middle',
  style: () => ({ width: '100%' }),
  disabled: false,
  allowClear: false,
});

const emit = defineEmits(['update:value', 'change']);

// 状态
const loading = ref(false);
const modelRoutes = ref<LLMApi.ModelRoute[]>([]);
const providers = ref<LLMApi.ProviderConfig[]>([]);

// 内部使用的已选项对象（为了支持 rich label 显示）
const selectedOption = computed(() => {
  if (!props.value) return undefined;
  // 先从当前选项列表中找，找不到再从全量路由中找
  const route = modelRoutes.value.find((r) => r.model_code === props.value);

  if (!route) {
    return {
      value: props.value,
      label: props.value,
    };
  }

  const currentRoute = route;
  return {
    value: currentRoute.model_code,
    label: h(
      'div',
      { class: 'flex items-center gap-2', style: { width: '100%' } },
      [
        h(
          Tag,
          {
            color: 'orange',
            style: {
              height: '18px',
              padding: '0 4px',
              margin: 0,
              fontSize: '10px',
              lineHeight: '1.4',
            },
          },
          { default: () => currentRoute.provider_code },
        ),
        h('span', { class: 'truncate font-medium' }, currentRoute.model_name),
        (currentRoute.cost_per_1k_input || currentRoute.cost_per_1k_output) &&
          h(
            'span',
            {
              class:
                'ml-auto rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground',
            },
            [
              h('span', { class: 'opacity-60 mr-0.5' }, 'In:'),
              `${currentRoute.currency === 'CNY' ? '¥' : '$'}${currentRoute.cost_per_1k_input || '0'}`,
              h('span', { class: 'mx-1 opacity-20' }, '|'),
              h('span', { class: 'opacity-60 mr-0.5' }, 'Out:'),
              `${currentRoute.currency === 'CNY' ? '¥' : '$'}${currentRoute.cost_per_1k_output || '0'}`,
            ],
          ),
      ],
    ),
    provider_code: currentRoute.provider_code,
    cost_per_1k_input: currentRoute.cost_per_1k_input,
    cost_per_1k_output: currentRoute.cost_per_1k_output,
    currency: currentRoute.currency,
    description: currentRoute.description,
  };
});

// 获取数据
async function fetchData() {
  loading.value = true;
  try {
    const [routesRes, providersRes] = await Promise.all([
      getRouteListApi({ enabled: true, limit: 1000 }),
      getProviderListApi({ enabled: true, limit: 100 }),
    ]);
    modelRoutes.value = routesRes?.items || [];
    providers.value = providersRes?.items || [];
  } catch (error) {
    console.error('获取模型选择数据失败:', error);
  } finally {
    loading.value = false;
  }
}

// 分组逻辑
const modelOptions = computed(() => {
  const groupMap = new Map<string, any[]>();

  modelRoutes.value.forEach((route) => {
    const pCode = route.provider_code || 'Unknown';
    if (!groupMap.has(pCode)) {
      groupMap.set(pCode, []);
    }
    groupMap.get(pCode)!.push({
      value: route.model_code,
      label: route.model_name,
      provider_code: pCode,
      cost_per_1k_input: route.cost_per_1k_input,
      cost_per_1k_output: route.cost_per_1k_output,
      currency: route.currency,
      description: route.description,
    });
  });

  return [...groupMap.entries()]
    .map(([pCode, options]) => {
      const provider = providers.value.find((p) => p.provider_code === pCode);
      return {
        label: provider ? `${provider.provider_name} (${pCode})` : pCode,
        options: options.toSorted((a, b) => a.label.localeCompare(b.label)),
      };
    })
    .toSorted((a, b) => b.label.localeCompare(a.label)); // Provider 分组倒序排序
});

// 搜索过滤
const filterModelOption = (input: string, option: any) => {
  const searchStr = input.toLowerCase();
  // 注意：Ant Design Vue 分组模式下，option 指向的是具体的子项
  return (
    option.label?.toLowerCase().includes(searchStr) ||
    option.value?.toLowerCase().includes(searchStr) ||
    option.provider_code?.toLowerCase().includes(searchStr)
  );
};

function handleChange(val: any) {
  // 处理清空的情况：val 为 undefined 或 null
  const actualValue = val && typeof val === 'object' ? val.value : (val ?? '');
  emit('update:value', actualValue);
  emit('change', actualValue);
}

onMounted(() => {
  fetchData();
});
</script>

<template>
  <Select
    :value="selectedOption"
    :options="modelOptions"
    :placeholder="placeholder"
    :size="size"
    :style="style"
    :disabled="disabled"
    :loading="loading"
    :allow-clear="allowClear"
    show-search
    label-in-value
    option-filter-prop="label"
    :filter-option="filterModelOption"
    :dropdown-match-select-width="false"
    :list-height="400"
    @change="handleChange"
  >
    <!-- 下拉选项的展示 -->
    <template
      #option="{
        label,
        provider_code,
        cost_per_1k_input,
        cost_per_1k_output,
        currency,
        description,
      }"
    >
      <Tooltip :title="description" placement="right" :mouse-enter-delay="0.5">
        <div class="flex w-full min-w-[300px] items-center justify-between">
          <div class="flex items-center gap-2 overflow-hidden">
            <Tag
              color="orange"
              style="
                height: 18px;
                padding: 0 4px;
                margin-right: 0;
                font-size: 10px;
                line-height: 1.4;
              "
            >
              {{ provider_code }}
            </Tag>
            <span class="truncate font-medium" :title="label">{{ label }}</span>
          </div>
          <div class="ml-4 flex flex-shrink-0 items-center">
            <span
              v-if="cost_per_1k_input || cost_per_1k_output"
              class="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
            >
              <span class="mr-0.5 opacity-60">In:</span
              >{{ currency === 'CNY' ? '¥' : '$'
              }}{{ cost_per_1k_input || '0' }}
              <span class="mx-1 opacity-20">|</span>
              <span class="mr-0.5 opacity-60">Out:</span
              >{{ currency === 'CNY' ? '¥' : '$'
              }}{{ cost_per_1k_output || '0' }}
            </span>
          </div>
        </div>
      </Tooltip>
    </template>
  </Select>
</template>

<style scoped>
:deep(.ant-select-selector) {
  min-height: 36px !important;
  padding-top: 8px !important;
  padding-bottom: 8px !important;
}

:deep(.ant-select-selection-item) {
  display: flex !important;
  align-items: center !important;
}

:deep(.ant-select-item-group) {
  padding: 6px 12px;
  font-size: 11px;
  font-weight: 700;
  color: hsl(var(--primary));
  text-transform: uppercase;
  letter-spacing: 0.5px;
  background: hsl(var(--muted) / 30%);
}

.truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
