<script setup lang="ts">
import type { SystemInfoApi } from '#/api/core/system-info';

import { computed, onMounted, ref } from 'vue';

import { Page } from '@vben/common-ui';
import { useAccessStore } from '@vben/stores';

import {
  Badge,
  Button,
  Card,
  Descriptions,
  DescriptionsItem,
  InputNumber,
  message,
  Select,
  Spin,
  Tag,
  Tooltip,
} from 'ant-design-vue';

import { getSystemInfoApi } from '#/api/core/system-info';

defineOptions({ name: 'SystemInfo' });

const loading = ref(false);
const info = ref<null | SystemInfoApi.SystemInfoResult>(null);
const accessStore = useAccessStore();

// Token 过期时间配置
const tokenExpiryMinutes = ref(accessStore.tokenExpiryMinutes);

// 预设选项
const presetOptions = [
  { label: '30 分钟', value: 30 },
  { label: '1 小时', value: 60 },
  { label: '2 小时', value: 120 },
  { label: '4 小时', value: 240 },
  { label: '8 小时（默认）', value: 480 },
  { label: '12 小时', value: 720 },
  { label: '24 小时', value: 1440 },
  { label: '自定义', value: -1 },
];

const selectedPreset = ref(
  presetOptions.some((opt) => opt.value === tokenExpiryMinutes.value)
    ? tokenExpiryMinutes.value
    : -1,
);

const isCustom = computed(() => selectedPreset.value === -1);

// Token 剩余时间
const tokenRemainingTime = computed(() => {
  if (!accessStore.tokenExpiresAt) return '未设置';
  const remaining = accessStore.getTokenRemainingTime();
  if (remaining <= 0) return '已过期';

  const hours = Math.floor(remaining / (1000 * 60 * 60));
  const minutes = Math.floor((remaining % (1000 * 60 * 60)) / (1000 * 60));

  if (hours > 0) {
    return `${hours}小时${minutes}分钟`;
  }
  return `${minutes}分钟`;
});

// 当选择预设时更新分钟数
function handlePresetChange(value: number) {
  selectedPreset.value = value;
  if (value !== -1) {
    tokenExpiryMinutes.value = value;
  }
}

// 保存设置
function saveTokenExpirySetting() {
  if (tokenExpiryMinutes.value < 5) {
    message.warning('过期时间不能小于 5 分钟');
    return;
  }
  if (tokenExpiryMinutes.value > 43_200) {
    // 30天
    message.warning('过期时间不能超过 30 天（43200 分钟）');
    return;
  }

  accessStore.setTokenExpiryMinutes(tokenExpiryMinutes.value);
  message.success(
    `Token 过期时间已设置为 ${formatMinutes(tokenExpiryMinutes.value)}，重新登录后生效`,
  );
}

// 格式化分钟数为可读字符串
function formatMinutes(minutes: number): string {
  if (minutes < 60) {
    return `${minutes} 分钟`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (remainingMinutes === 0) {
    return `${hours} 小时`;
  }
  return `${hours} 小时 ${remainingMinutes} 分钟`;
}

async function fetchInfo() {
  loading.value = true;
  try {
    info.value = await getSystemInfoApi();
  } catch (error) {
    console.error('Failed to fetch system info:', error);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  fetchInfo();
});

function getStatusBadge(status: string) {
  if (status === 'healthy' || status === 'ready' || status === 'alive') {
    return 'success';
  }
  if (
    status.startsWith('error') ||
    status.startsWith('unhealthy') ||
    status.startsWith('unreachable')
  ) {
    return 'error';
  }
  return 'warning';
}

function getEnvTagColor(env: string) {
  switch (env) {
    case 'development': {
      return 'blue';
    }
    case 'production': {
      return 'red';
    }
    case 'staging': {
      return 'orange';
    }
    default: {
      return 'default';
    }
  }
}
</script>

<template>
  <Page>
    <!-- 粘性筛选头部 -->
    <div
      class="sticky top-0 z-10 -mx-4 -mt-4 mb-3 bg-background/90 px-4 pb-4 pt-2 shadow-lg backdrop-blur-md"
      style="border-bottom: 1px solid hsl(var(--border) / 30%)"
    >
      <!-- 标题行 -->
      <div class="mb-2 flex items-center gap-3">
        <span
          class="bg-gradient-to-r from-[hsl(var(--primary))] to-[#22c55e] bg-clip-text text-xl font-bold text-transparent"
        >
          系统信息
        </span>
      </div>
    </div>
    <div class="mb-4 text-sm text-muted-foreground">
      查看系统运行环境、基础设施连接及各服务健康状态
    </div>

    <Spin :spinning="loading">
      <div class="flex flex-col gap-4">
        <!-- 会话设置 -->
        <Card title="会话设置">
          <div class="flex flex-col gap-4">
            <Descriptions :column="2" bordered size="small">
              <DescriptionsItem label="当前会话状态">
                <Tag v-if="accessStore.accessToken" color="green">已登录</Tag>
                <Tag v-else color="red">未登录</Tag>
              </DescriptionsItem>
              <DescriptionsItem label="会话剩余时间">
                <Tooltip
                  title="当前登录会话的剩余有效时间（基于后端 Token 过期时间）"
                >
                  <span
                    :class="{
                      'text-warning':
                        accessStore.tokenExpiresAt &&
                        accessStore.getTokenRemainingTime() < 300000,
                    }"
                  >
                    {{ tokenRemainingTime }}
                  </span>
                </Tooltip>
              </DescriptionsItem>
            </Descriptions>

            <div class="flex items-center gap-4">
              <span class="text-sm font-medium">Token 过期时间：</span>
              <Select
                :value="selectedPreset"
                style="width: 180px"
                :options="presetOptions"
                show-search
                :filter-option="true"
                @change="handlePresetChange"
              />
              <InputNumber
                v-if="isCustom"
                v-model:value="tokenExpiryMinutes"
                :min="5"
                :max="43200"
                :step="5"
                style="width: 120px"
                addon-after="分钟"
              />
              <Button type="primary" @click="saveTokenExpirySetting">
                保存设置
              </Button>
            </div>

            <div class="text-xs text-muted-foreground">
              <p>
                <strong>说明：</strong>
                Token 过期时间决定了用户登录后会话的有效期。过期后需要重新登录。
              </p>
              <p>
                当前配置：<strong>{{
                  formatMinutes(accessStore.tokenExpiryMinutes)
                }}</strong>
              </p>
              <p class="mt-1 text-warning">
                提示：修改后<strong>需要重新登录</strong>才会生效，新的 Token
                将使用设定的过期时间。
              </p>
            </div>
          </div>
        </Card>

        <!-- 基础环境 -->
        <Card v-if="info" title="基础环境">
          <Descriptions :column="2" bordered>
            <DescriptionsItem label="运行环境">
              <Tag :color="getEnvTagColor(info.app_env)">
                {{ info.app_env.toUpperCase() }}
              </Tag>
            </DescriptionsItem>
            <DescriptionsItem label="命名空间">
              {{ info.k8s.namespace }}
            </DescriptionsItem>
            <DescriptionsItem label="Pod 名称">
              {{ info.k8s.pod_name }}
            </DescriptionsItem>
            <DescriptionsItem label="Node 名称">
              {{ info.k8s.node_name }}
            </DescriptionsItem>
          </Descriptions>
        </Card>

        <!-- 基础设施 -->
        <div v-if="info" class="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Card title="数据库信息 (MySQL)">
            <Descriptions :column="1" bordered size="small">
              <DescriptionsItem label="主机">
                {{ info.database.host }}
              </DescriptionsItem>
              <DescriptionsItem label="端口">
                {{ info.database.port }}
              </DescriptionsItem>
              <DescriptionsItem label="用户">
                {{ info.database.user }}
              </DescriptionsItem>
              <DescriptionsItem label="数据库">
                <div class="flex items-center justify-between">
                  <span>{{ info.database.database }}</span>
                  <a
                    v-if="info.database.adminer_url"
                    :href="info.database.adminer_url"
                    target="_blank"
                    class="ml-2 text-xs text-primary hover:underline"
                  >
                    管理工具
                  </a>
                </div>
              </DescriptionsItem>
            </Descriptions>
          </Card>

          <Card title="缓存信息 (Redis)">
            <Descriptions :column="1" bordered size="small">
              <DescriptionsItem label="主机">
                {{ info.redis.host }}
              </DescriptionsItem>
              <DescriptionsItem label="端口">
                {{ info.redis.port }}
              </DescriptionsItem>
              <DescriptionsItem label="DB 索引">
                <div class="flex items-center justify-between">
                  <span>{{ info.redis.db }}</span>
                  <a
                    v-if="info.redis.insight_url"
                    :href="info.redis.insight_url"
                    target="_blank"
                    class="ml-2 text-xs text-primary hover:underline"
                  >
                    管理工具
                  </a>
                </div>
              </DescriptionsItem>
            </Descriptions>
          </Card>
        </div>

        <!-- 服务健康状态 -->
        <Card v-if="info" title="微服务状态">
          <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Card
              v-for="(status, name) in info.services"
              :key="name"
              size="small"
              class="border-l-4"
              :class="[
                status.status === 'healthy'
                  ? 'border-l-green-500'
                  : 'border-l-red-500',
              ]"
            >
              <template #title>
                <div class="flex items-center justify-between">
                  <span class="font-bold uppercase">{{ name }}</span>
                  <Badge
                    :status="getStatusBadge(status.status)"
                    :text="status.status"
                  />
                </div>
              </template>
              <div class="mt-2 text-xs text-muted-foreground">
                <p v-if="status.version">版本: {{ status.version }}</p>
                <p v-if="status.last_check">
                  最后检查: {{ status.last_check }}
                </p>
              </div>
            </Card>
          </div>
        </Card>
      </div>
    </Spin>
  </Page>
</template>

<style scoped>
:deep(.ant-descriptions-item-label) {
  width: 120px;
}
</style>
