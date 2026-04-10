<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';

import { Select, Tooltip } from 'ant-design-vue';

import { getTenantSimpleListApi } from '#/api/core/business';

interface Props {
  /** 当前选中的 tenant_code */
  value?: string;
  /** 是否显示"全部租户"选项 */
  showAll?: boolean;
  /** 宽度 */
  width?: number | string;
  /** 占位符 */
  placeholder?: string;
  /** 提示文字 */
  tooltip?: string;
  /** 是否有边框 */
  bordered?: boolean;
  /** 尺寸 */
  size?: 'large' | 'middle' | 'small';
  /** 是否禁用 */
  disabled?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  value: '',
  showAll: true,
  width: 140,
  placeholder: '选择租户',
  tooltip: '选择要查看的租户数据',
  bordered: false,
  size: 'small',
  disabled: false,
});

const emit = defineEmits<{
  change: [value: string];
  'update:value': [value: string];
}>();

interface TenantOption {
  label: string;
  value: string;
}

const selectedValue = ref<string>(props.value);
const options = ref<TenantOption[]>([]);
const loading = ref(false);

// 获取租户列表
async function fetchTenants() {
  loading.value = true;
  try {
    const tenants = await getTenantSimpleListApi();
    const tenantItems = tenants.map((t) => ({
      label: t.tenant_name,
      value: t.tenant_code,
    }));

    options.value = props.showAll
      ? [{ label: '全部租户', value: '' }, ...tenantItems]
      : tenantItems;

    // 如果没有默认值且有租户，自动选择第一个
    if (!selectedValue.value && tenantItems.length > 0 && !props.showAll) {
      selectedValue.value = tenantItems[0]!.value;
      emit('update:value', selectedValue.value);
      emit('change', selectedValue.value);
    }
  } catch (error) {
    console.error('获取租户列表失败', error);
  } finally {
    loading.value = false;
  }
}

// 处理选择变化
function handleChange(value: string) {
  selectedValue.value = value;
  emit('update:value', value);
  emit('change', value);
}

// 监听外部 value 变化
watch(
  () => props.value,
  (newVal) => {
    selectedValue.value = newVal;
  },
);

onMounted(() => {
  fetchTenants();
});

// 暴露刷新方法
defineExpose({
  refresh: fetchTenants,
});
</script>

<template>
  <Tooltip :title="tooltip">
    <Select
      :value="selectedValue"
      :options="options"
      :placeholder="placeholder"
      :style="{ width: typeof width === 'number' ? `${width}px` : width }"
      :size="size"
      :bordered="bordered"
      :disabled="disabled"
      :loading="loading"
      @change="handleChange"
    />
  </Tooltip>
</template>
