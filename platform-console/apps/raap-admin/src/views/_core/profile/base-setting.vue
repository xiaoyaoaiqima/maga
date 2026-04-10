<script setup lang="ts">
import type { VbenFormSchema } from '#/adapter/form';

import { computed, onMounted, ref } from 'vue';

import { ProfileBaseSetting, z } from '@vben/common-ui';
import { useUserStore } from '@vben/stores';

import { message } from 'ant-design-vue';

import { getUserInfoApi, updateUserProfileApi } from '#/api';

const profileBaseSettingRef = ref();
const userStore = useUserStore();
const submitLoading = ref(false);

const formSchema = computed((): VbenFormSchema[] => {
  return [
    {
      fieldName: 'realName',
      component: 'Input',
      label: '姓名',
      rules: z.string().min(1, { message: '请输入姓名' }),
    },
    {
      fieldName: 'email',
      component: 'Input',
      label: '邮箱',
      rules: z.string().email({ message: '请输入有效的邮箱地址' }).optional(),
    },
    {
      fieldName: 'phone',
      component: 'Input',
      label: '手机号',
    },
  ];
});

async function handleSubmit(values: any) {
  try {
    submitLoading.value = true;
    await updateUserProfileApi({
      email: values.email,
      name: values.realName,
      phone: values.phone,
    });
    message.success('保存成功');
    const userInfo = await getUserInfoApi();
    userStore.setUserInfo(userInfo);
  } catch {
    // error handled by request interceptor
  } finally {
    submitLoading.value = false;
  }
}

onMounted(async () => {
  const data = await getUserInfoApi();
  profileBaseSettingRef.value.getFormApi().setValues(data);
});
</script>
<template>
  <ProfileBaseSetting
    ref="profileBaseSettingRef"
    :form-schema="formSchema"
    :submit-loading="submitLoading"
    @submit="handleSubmit"
  />
</template>
