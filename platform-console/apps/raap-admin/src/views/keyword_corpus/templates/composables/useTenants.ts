import type { TenantOption } from '../types';

import { computed, ref } from 'vue';

import { requestClient } from '#/api/request';

export function useTenants() {
  const loading = ref(false);
  const filterOptions = ref<TenantOption[]>([]);

  // 获取租户列表
  const fetchTenantOptions = async () => {
    loading.value = true;
    try {
      const res = await requestClient.get<
        Array<{ count: number; tenant_code: string; tenant_name: string }>
      >('/v1/keyword-corpus/categories/tenants');

      filterOptions.value = [
        { value: '', label: '全部租户' },
        ...(res || []).map((item) => ({
          value: item.tenant_code,
          label: item.tenant_name,
        })),
      ];
    } catch (error) {
      logger.error('获取租户列表失败:', error);
      // 降级使用默认值
      filterOptions.value = [
        { value: '', label: '全部租户' },
        { value: 'default', label: '默认' },
      ];
    } finally {
      loading.value = false;
    }
  };

  // 租户选项（表单用，过滤掉"全部租户"）
  const formOptions = computed(() => {
    return filterOptions.value.filter((item) => item.value !== '');
  });

  return {
    loading,
    filterOptions,
    formOptions,
    fetchTenantOptions,
  };
}
