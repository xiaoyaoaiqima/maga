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

import { IconifyIcon } from '@vben/icons';

import {
  clearAllMessagesApi,
  getUnreadCountApi,
  listMessagesApi,
  markAllMessagesReadApi,
  markMessageReadApi,
  removeMessageApi,
  sendChatMessageApi,
} from '#/api';
import type { ChatAction, ChatHistoryMessage } from '#/api';
import { $t } from '#/locales';
import { useAuthStore, useMagaChatStore, useTokenExpiry } from '#/store';
import LoginForm from '#/views/_core/authentication/login.vue';
import MagaChatPanel from './MagaChatPanel.vue';

interface ChatPanelMessage {
  id: string;
  role: 'assistant' | 'error' | 'user';
  content: string;
  actions?: ChatAction[];
  loading?: boolean;
}

const notifications = ref<NotificationItem[]>([]);
const unreadCount = ref<number>(0);
const isLoadingNotifications = ref<boolean>(false);
let pollTimer: null | number = null;

const router = useRouter();
const userStore = useUserStore();
const authStore = useAuthStore();
const chatStore = useMagaChatStore();
const accessStore = useAccessStore();
const { destroyWatermark, updateWatermark } = useWatermark();
const chatSending = ref(false);
const chatAgentMissing = ref(false);
const chatAgentName = ref('实时聊天 Agent');
const chatMessages = ref<ChatPanelMessage[]>([]);
const chatOpen = computed({
  get: () => chatStore.open,
  set: (value: boolean) => chatStore.setOpen(value),
});

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
// MAGA clean 部署不暴露旧 RAAP 消息中心 API，通知轮询默认关闭以避免全局控制台噪声。
const notificationsEnabled = computed(
  () => import.meta.env.VITE_ENABLE_LEGACY_NOTIFICATIONS === 'true',
);
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

const showDot = computed(
  () => notificationsEnabled.value && unreadCount.value > 0,
);

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

const isChatMobile = computed(() => preferences.app.isMobile);

async function handleLogout() {
  await authStore.logout(false);
}

function createChatMessage(
  role: ChatPanelMessage['role'],
  content: string,
  loading = false,
  actions: ChatAction[] = [],
): ChatPanelMessage {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role,
    content,
    actions,
    loading,
  };
}

function getChatHistory(): ChatHistoryMessage[] {
  return chatMessages.value
    .filter((item) => item.role === 'user' || item.role === 'assistant')
    .map((item) => ({
      role: item.role as 'assistant' | 'user',
      content: item.content,
    }));
}

async function sendChatMessage(message: string) {
  const trimmedMessage = message.trim();
  if (!trimmedMessage || chatSending.value || chatAgentMissing.value) return;

  const history = getChatHistory();
  chatMessages.value.push(createChatMessage('user', trimmedMessage));
  const loadingMessage = createChatMessage('assistant', '', true);
  chatMessages.value.push(loadingMessage);
  chatSending.value = true;

  try {
    const response = await sendChatMessageApi({
      message: trimmedMessage,
      // 聊天记录首版只存在当前前端会话内，刷新后自然清空，不写入后端表。
      history,
      context: chatStore.context,
    });
    chatAgentName.value = response.agent_name || '实时聊天 Agent';
    loadingMessage.content = response.reply || '模型没有返回内容。';
    loadingMessage.actions = response.actions || [];
    loadingMessage.loading = false;
  } catch (error: any) {
    chatMessages.value = chatMessages.value.filter(
      (item) => item.id !== loadingMessage.id,
    );
    const errorMessage =
      error?.response?.data?.detail ||
      error?.response?.data?.message ||
      error?.message ||
      '发送失败，请稍后重试';
    if (String(errorMessage).includes('未配置实时聊天 Agent')) {
      chatAgentMissing.value = true;
    }
    chatMessages.value.push(createChatMessage('error', String(errorMessage)));
  } finally {
    chatSending.value = false;
  }
}

function handleChatAction(action: ChatAction) {
  if (action.type === 'fill_comment_angle_draft') {
    chatStore.requestDraftFill(action);
  }
}

function get_notification_avatar(): string {
  // 使用本地静态资源，避免依赖外网
  return '/maga-logo.svg';
}

async function refresh_notifications(): Promise<void> {
  if (!notificationsEnabled.value) return;
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
  if (!notificationsEnabled.value) return;
  await clearAllMessagesApi();
  unreadCount.value = 0;
  notifications.value = [];
}

async function markRead(id: number | string) {
  if (!notificationsEnabled.value) return;
  if (typeof id !== 'number') return;
  await markMessageReadApi(id);
  const item = notifications.value.find((n) => n.id === id);
  if (item) item.isRead = true;
  await refresh_notifications();
}

async function remove(id: number | string) {
  if (!notificationsEnabled.value) return;
  if (typeof id !== 'number') return;
  await removeMessageApi(id);
  notifications.value = notifications.value.filter((n) => n.id !== id);
  await refresh_notifications();
}

async function handleMakeAll() {
  if (!notificationsEnabled.value) return;
  await markAllMessagesReadApi();
  notifications.value.forEach((item) => (item.isRead = true));
  await refresh_notifications();
}

function handleViewAll() {
  if (!notificationsEnabled.value) return;
  router.push({ path: '/message/center' });
}

onMounted(async () => {
  if (!notificationsEnabled.value) return;
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

watch(
  () => accessStore.accessToken,
  (token) => {
    if (!token) {
      chatOpen.value = false;
      chatMessages.value = [];
      chatAgentMissing.value = false;
      chatAgentName.value = '实时聊天 Agent';
      chatStore.clearContext();
    }
  },
);
</script>

<template>
  <div
    class="maga-chat-shell"
    :class="{ 'is-chat-mobile': isChatMobile, 'is-chat-open': chatOpen }"
  >
    <div
      v-if="appEnv !== 'production' && envName"
      class="env-topbar"
      :class="[`env-${appEnv}`]"
      :title="envName"
    ></div>
    <BasicLayout @clear-preferences-and-logout="handleLogout">
      <template #header-right-55>
        <button
          v-if="accessStore.accessToken"
          class="chat-toggle"
          :class="{ 'is-active': chatOpen }"
          title="Chat"
          type="button"
          @click="chatOpen = !chatOpen"
        >
          <IconifyIcon icon="lucide:messages-square" />
          <span>Chat</span>
        </button>
      </template>
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
          v-if="notificationsEnabled"
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
    <Transition name="chat-panel">
      <MagaChatPanel
        v-if="accessStore.accessToken && chatOpen"
        class="chat-panel-host"
        :agent-missing="chatAgentMissing"
        :agent-name="chatAgentName"
        :active-context="chatStore.context"
        :messages="chatMessages"
        :sending="chatSending"
        @close="chatOpen = false"
        @chat-action="handleChatAction"
        @send="sendChatMessage"
      />
    </Transition>
  </div>
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

.maga-chat-shell {
  min-height: 100%;
}

.chat-toggle {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  justify-content: center;
  height: 32px;
  padding: 0 10px;
  margin-right: 4px;
  font-size: 13px;
  font-weight: 600;
  color: hsl(var(--muted-foreground));
  cursor: pointer;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 8px;
}

.chat-toggle:hover,
.chat-toggle.is-active {
  color: #0f766e;
  background: rgb(15 118 110 / 10%);
  border-color: rgb(15 118 110 / 18%);
}

.chat-toggle :deep(svg) {
  width: 16px;
  height: 16px;
}

.chat-panel-host {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  /* Chat 可能从右侧业务规则 Drawer 内打开，层级必须高于 Ant Drawer 才不会看起来“没反应”。 */
  z-index: 1300;
}

.chat-panel-enter-active,
.chat-panel-leave-active {
  transition:
    transform 0.2s ease,
    opacity 0.2s ease;
}

.chat-panel-enter-from,
.chat-panel-leave-to {
  opacity: 0;
  transform: translateX(100%);
}

.maga-chat-shell:not(.is-chat-open) :global(#__vben_main_content) {
  /* Chat 关闭时工作台必须占满剩余空间，避免用户偏好的 compact 内容宽度把页面居中。 */
  width: auto !important;
  max-width: none !important;
  margin-right: 0 !important;
  margin-left: 0 !important;
}

.maga-chat-shell.is-chat-open:not(.is-chat-mobile)
  :global(#__vben_main_content) {
  width: calc(100% - 380px) !important;
  max-width: none !important;
  margin-right: 380px !important;
  margin-left: 0 !important;
  transition: margin-right 0.2s ease;
}

.maga-chat-shell.is-chat-open:not(.is-chat-mobile)
  :global(._scroll__fixed_) {
  right: 380px !important;
  width: auto !important;
}

.maga-chat-shell.is-chat-open:not(.is-chat-mobile)
  :global(.vben-layout-footer) {
  right: 380px;
}

.maga-chat-shell.is-chat-mobile .chat-panel-host {
  left: 0;
  z-index: 1300;
}

@media (max-width: 768px) {
  .chat-toggle span {
    display: none;
  }
}
</style>

<style>
.maga-chat-shell:not(.is-chat-open) #__vben_main_content {
  /* Vben compact 模式会给 main 写入 inline 居中宽度；Chat 关闭时必须还原为全宽工作台。 */
  width: auto !important;
  max-width: none !important;
  margin-right: 0 !important;
  margin-left: 0 !important;
}

.maga-chat-shell.is-chat-open:not(.is-chat-mobile) #__vben_main_content {
  width: calc(100% - 380px) !important;
  max-width: none !important;
  margin-right: 380px !important;
  margin-left: 0 !important;
}

.maga-chat-shell:not(.is-chat-open) ._scroll__fixed_ {
  /* 顶部 header/tabbar 是 fixed 独立层；Chat 关闭时也要恢复到右边界。 */
  right: 0 !important;
  width: auto !important;
}

.maga-chat-shell.is-chat-open:not(.is-chat-mobile) ._scroll__fixed_ {
  right: 380px !important;
  width: auto !important;
}
</style>
