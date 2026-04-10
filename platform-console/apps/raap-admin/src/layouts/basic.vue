<script lang="ts" setup>
import type { NotificationItem } from '@vben/layouts';

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import { AuthenticationLoginExpiredModal } from '@vben/common-ui';
import { useWatermark } from '@vben/hooks';
import {
  BasicLayout,
  LockScreen,
  Notification,
  UserDropdown,
} from '@vben/layouts';
import { preferences } from '@vben/preferences';
import { useAccessStore, useUserStore } from '@vben/stores';

import {
  clearAllMessagesApi,
  getUnreadCountApi,
  listMessagesApi,
  markAllMessagesReadApi,
  markMessageReadApi,
  removeMessageApi,
} from '#/api';
import { $t } from '#/locales';
import { useAuthStore, useTokenExpiry } from '#/store';
import LoginForm from '#/views/_core/authentication/login.vue';

const notifications = ref<NotificationItem[]>([]);
const unreadCount = ref<number>(0);
const isLoadingNotifications = ref<boolean>(false);
let pollTimer: null | number = null;

const router = useRouter();
const userStore = useUserStore();
const authStore = useAuthStore();
const accessStore = useAccessStore();
const { destroyWatermark, updateWatermark } = useWatermark();

// Token 过期检查
const { formattedRemainingTime, isAboutToExpire, remainingMinutes } =
  useTokenExpiry({
    enabled: true,
    onExpired: () => {
      // Token 过期后执行登出
      handleLogout();
    },
  });

const appEnv = computed(() => authStore.appEnv || 'production');
const envName = computed(() => {
  switch (appEnv.value) {
    case 'development': {
      return '开发环境';
    }
    case 'test': {
      return '测试环境';
    }
    default: {
      return '';
    }
  }
});

const showDot = computed(() => unreadCount.value > 0);

const menus = computed(() => [
  {
    handler: () => {
      router.push({ name: 'Profile' });
    },
    icon: 'lucide:user',
    text: $t('page.auth.profile'),
  },
]);

const avatar = computed(() => {
  return userStore.userInfo?.avatar;
});

async function handleLogout() {
  await authStore.logout(false);
}

function get_notification_avatar(): string {
  // 使用本地静态资源，避免依赖外网
  return '/logo-128.png';
}

async function refresh_notifications(): Promise<void> {
  if (isLoadingNotifications.value) return;
  isLoadingNotifications.value = true;
  try {
    const [count, list] = await Promise.all([
      getUnreadCountApi(),
      listMessagesApi({ skip: 0, limit: 10 }),
    ]);
    unreadCount.value = count;
    notifications.value = list.items.map((item) => ({
      id: item.recipient_id,
      avatar: get_notification_avatar(),
      date: item.create_time ?? '',
      isRead: item.is_read,
      message: item.content,
      title: item.title,
      link: item.link,
    }));
  } finally {
    isLoadingNotifications.value = false;
  }
}

async function handleNoticeClear() {
  await clearAllMessagesApi();
  unreadCount.value = 0;
  notifications.value = [];
}

async function markRead(id: number | string) {
  if (typeof id !== 'number') return;
  await markMessageReadApi(id);
  const item = notifications.value.find((n) => n.id === id);
  if (item) item.isRead = true;
  await refresh_notifications();
}

async function remove(id: number | string) {
  if (typeof id !== 'number') return;
  await removeMessageApi(id);
  notifications.value = notifications.value.filter((n) => n.id !== id);
  await refresh_notifications();
}

async function handleMakeAll() {
  await markAllMessagesReadApi();
  notifications.value.forEach((item) => (item.isRead = true));
  await refresh_notifications();
}

function handleViewAll() {
  router.push({ path: '/message/center' });
}

onMounted(async () => {
  await refresh_notifications();
  pollTimer = window.setInterval(() => {
    refresh_notifications().catch(() => undefined);
  }, 30_000);
});

onBeforeUnmount(() => {
  if (pollTimer) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
});
watch(
  () => ({
    enable: preferences.app.watermark,
    content: preferences.app.watermarkContent,
    userInfo: userStore.userInfo,
  }),
  async ({ content, enable, userInfo }) => {
    if (enable) {
      let watermarkText =
        content ||
        (userInfo
          ? `${userInfo.username || ''} - ${userInfo.realName || ''}`
          : '');

      if (appEnv.value !== 'production' && envName.value) {
        watermarkText = `${watermarkText} [${envName.value}]`;
      }

      if (watermarkText) {
        await updateWatermark({
          content: watermarkText,
        });
      }
    } else {
      destroyWatermark();
    }
  },
  {
    immediate: true,
  },
);
</script>

<template>
  <div
    v-if="appEnv !== 'production' && envName"
    class="env-topbar"
    :class="[`env-${appEnv}`]"
    :title="envName"
  ></div>
  <BasicLayout @clear-preferences-and-logout="handleLogout">
    <template #user-dropdown>
      <div class="flex items-center gap-2">
        <!-- Token 过期倒计时提示 -->
        <div
          v-if="accessStore.accessToken"
          class="token-expiry-indicator"
          :class="{
            'is-warning': isAboutToExpire,
            'is-unset': !accessStore.tokenExpiresAt,
          }"
          :title="
            accessStore.tokenExpiresAt
              ? `会话剩余时间: ${formattedRemainingTime}`
              : '会话过期时间未设置，请前往系统信息页面配置'
          "
        >
          <span class="token-expiry-icon">⏱</span>
          <span v-if="isAboutToExpire" class="token-expiry-text">
            {{ remainingMinutes }}分钟
          </span>
          <span
            v-else-if="!accessStore.tokenExpiresAt"
            class="token-expiry-text"
          >
            未设置
          </span>
        </div>
        <UserDropdown
          :avatar
          :menus
          :text="userStore.userInfo?.realName"
          :description="
            userStore.userInfo?.email || userStore.userInfo?.username || ''
          "
          :tag-text="userStore.userInfo?.roles?.[0] || ''"
          @logout="handleLogout"
        />
      </div>
    </template>
    <template #notification>
      <Notification
        :dot="showDot"
        :notifications="notifications"
        @clear="handleNoticeClear"
        @read="(item) => item.id && markRead(item.id)"
        @remove="(item) => item.id && remove(item.id)"
        @make-all="handleMakeAll"
        @view-all="handleViewAll"
      />
    </template>
    <template #extra>
      <AuthenticationLoginExpiredModal
        v-model:open="accessStore.loginExpired"
        :avatar
      >
        <LoginForm />
      </AuthenticationLoginExpiredModal>
    </template>
    <template #lock-screen>
      <LockScreen :avatar @to-login="handleLogout" />
    </template>
  </BasicLayout>
</template>

<style scoped>
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.6;
  }
}

.env-topbar {
  position: fixed;
  top: 0;
  right: 0;
  left: 0;
  z-index: 10001;
  height: 4px;
  pointer-events: none;
  box-shadow: 0 1px 0 0 hsl(var(--border));
}

/* 根据环境显示不同颜色 */
.env-development {
  background: hsl(var(--warning));
}

.env-test {
  background: hsl(var(--primary));
}

.env-staging {
  background: hsl(var(--success));
}

/* Token 过期倒计时指示器 */
.token-expiry-indicator {
  display: flex;
  gap: 4px;
  align-items: center;
  padding: 4px 8px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  cursor: default;
  border-radius: 4px;
  transition: all 0.3s ease;
}

.token-expiry-indicator:hover {
  background: hsl(var(--accent));
}

.token-expiry-indicator.is-warning {
  color: hsl(var(--warning));
  background: hsl(var(--warning) / 10%);
  animation: pulse 2s infinite;
}

.token-expiry-indicator.is-unset {
  color: hsl(var(--muted-foreground));
  opacity: 0.7;
}

.token-expiry-icon {
  font-size: 14px;
}

.token-expiry-text {
  font-weight: 500;
}
</style>
