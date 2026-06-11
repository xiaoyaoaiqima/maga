<script lang="ts" setup>
import { computed, ref } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { Button } from 'ant-design-vue';

import type { ChatAction, ChatContext } from '#/api';

interface ChatPanelMessage {
  id: string;
  role: 'assistant' | 'error' | 'user';
  content: string;
  actions?: ChatAction[];
  loading?: boolean;
}

const props = defineProps<{
  activeContext?: ChatContext | null;
  agentMissing: boolean;
  agentName: string;
  messages: ChatPanelMessage[];
  sending: boolean;
}>();

const emit = defineEmits<{
  chatAction: [action: ChatAction];
  close: [];
  send: [message: string];
}>();

const draft = ref('');
const commentAngleQuickPrompts = [
  '检查当前语料，指出太硬、AI味、同质化和越界风险',
  '基于当前规则改一版更像真人评论区的草稿',
  '把当前草稿放松一点，减少必须/只写/固定路径',
  '结合最近测试报告，给下一版草稿修改建议',
];

const canSend = computed(() => {
  return draft.value.trim().length > 0 && !props.sending && !props.agentMissing;
});
const isCommentAngleCopilot = computed(() => {
  return (
    props.activeContext?.page === 'business_rules' &&
    props.activeContext?.asset_type === 'comment_angle_rule_set'
  );
});
const contextTitle = computed(() => {
  if (!isCommentAngleCopilot.value) return '';
  const row = props.activeContext?.source_row_no
    ? `行 ${props.activeContext.source_row_no}`
    : '';
  return [props.activeContext?.comment_angle || '评论切角', row]
    .filter(Boolean)
    .join(' · ');
});

function send() {
  if (!canSend.value) return;
  const message = draft.value.trim();
  draft.value = '';
  emit('send', message);
}

function sendQuickPrompt(message: string) {
  if (props.sending || props.agentMissing) return;
  emit('send', message);
}
</script>

<template>
  <aside class="maga-chat-panel" aria-label="MAGA Chat">
    <header class="chat-header">
      <div class="chat-title">
        <span class="chat-title-icon">
          <IconifyIcon icon="lucide:messages-square" />
        </span>
        <div>
          <h2>Chat</h2>
          <p>{{ agentMissing ? '未配置实时聊天 Agent' : agentName }}</p>
        </div>
      </div>
      <button
        aria-label="关闭 Chat"
        class="chat-close"
        type="button"
        @click="emit('close')"
      >
        <IconifyIcon icon="lucide:x" />
      </button>
    </header>

    <div v-if="agentMissing" class="chat-alert">
      <IconifyIcon icon="lucide:circle-alert" />
      <span>未配置实时聊天 Agent，请先在 Agent 管理中启用 REALTIME_CHAT Agent。</span>
    </div>
    <div v-else-if="isCommentAngleCopilot" class="chat-context">
      <IconifyIcon icon="lucide:file-pen-line" />
      <span>{{ contextTitle }}</span>
    </div>

    <div class="chat-messages">
      <div v-if="messages.length === 0" class="chat-empty">
        <div class="empty-heading">
          <span>{{ isCommentAngleCopilot ? '评论切角副驾' : '开始对话' }}</span>
        </div>
        <div v-if="isCommentAngleCopilot" class="quick-prompts">
          <Button
            v-for="prompt in commentAngleQuickPrompts"
            :key="prompt"
            block
            size="small"
            @click="sendQuickPrompt(prompt)"
          >
            {{ prompt }}
          </Button>
        </div>
        <div v-else class="chat-empty-hint">
          输入问题，Chat 会基于当前会话回答；刷新页面后记录清空。
        </div>
      </div>

      <div
        v-for="message in messages"
        :key="message.id"
        class="chat-message"
        :class="[`is-${message.role}`, { 'is-loading': message.loading }]"
      >
        <div class="message-avatar">
          <IconifyIcon
            :icon="
              message.role === 'user'
                ? 'lucide:user'
                : message.role === 'error'
                  ? 'lucide:circle-alert'
                  : 'lucide:bot'
            "
          />
        </div>
        <div class="message-bubble">
          <span v-if="message.loading" class="loading-dot">生成中...</span>
          <template v-else>
            <span>{{ message.content }}</span>
            <div
              v-if="message.role === 'assistant' && message.actions?.length"
              class="message-actions"
            >
              <Button
                v-for="action in message.actions"
                :key="`${message.id}-${action.type}`"
                size="small"
                type="primary"
                @click="emit('chatAction', action)"
              >
                {{ action.label || '填入草稿' }}
              </Button>
            </div>
          </template>
        </div>
      </div>
    </div>

    <footer class="chat-input">
      <textarea
        v-model="draft"
        :disabled="sending || agentMissing"
        placeholder="输入问题，Ctrl+Enter 发送"
        rows="3"
        @keydown.ctrl.enter.prevent="send"
      ></textarea>
      <div class="chat-input-actions">
        <span v-if="agentMissing">未配置实时聊天 Agent</span>
        <span v-else>当前会话内保留，刷新后清空</span>
        <Button
          :disabled="!canSend"
          :loading="sending"
          type="primary"
          @click="send"
        >
          发送
        </Button>
      </div>
    </footer>
  </aside>
</template>

<style scoped>
.maga-chat-panel {
  display: grid;
  grid-template-rows: auto auto 1fr auto;
  width: 380px;
  height: 100%;
  color: hsl(var(--foreground));
  background: hsl(var(--background));
  border-left: 1px solid hsl(var(--border));
  box-shadow: -12px 0 32px rgb(15 23 42 / 10%);
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 58px;
  padding: 12px 14px;
  border-bottom: 1px solid hsl(var(--border));
}

.chat-title {
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 0;
}

.chat-title-icon,
.message-avatar,
.chat-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.chat-title-icon {
  width: 34px;
  height: 34px;
  color: #0f766e;
  background: rgb(15 118 110 / 10%);
  border-radius: 8px;
}

.chat-title h2 {
  margin: 0;
  font-size: 16px;
  line-height: 1.3;
}

.chat-title p {
  max-width: 250px;
  margin: 2px 0 0;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.4;
  color: hsl(var(--muted-foreground));
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-close {
  width: 30px;
  height: 30px;
  color: hsl(var(--muted-foreground));
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: 6px;
}

.chat-close:hover {
  color: hsl(var(--foreground));
  background: hsl(var(--accent));
}

.chat-alert {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 10px 14px;
  font-size: 13px;
  line-height: 1.5;
  color: #b45309;
  background: #fffbeb;
  border-bottom: 1px solid #fde68a;
}

.chat-alert :deep(svg) {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  margin-top: 2px;
}

.chat-context {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 9px 14px;
  font-size: 13px;
  color: #0f766e;
  background: rgb(15 118 110 / 8%);
  border-bottom: 1px solid rgb(15 118 110 / 14%);
}

.chat-context :deep(svg) {
  flex-shrink: 0;
  width: 15px;
  height: 15px;
}

.chat-messages {
  min-height: 0;
  padding: 14px;
  overflow-y: auto;
}

.chat-empty {
  display: grid;
  gap: 12px;
}

.empty-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 600;
}

.quick-prompts {
  display: grid;
  gap: 8px;
}

.quick-prompts :deep(.ant-btn) {
  height: auto;
  min-height: 30px;
  padding: 5px 8px;
  overflow-wrap: anywhere;
  line-height: 1.35;
  text-align: left;
  white-space: normal;
}

.chat-empty-hint {
  padding: 10px;
  font-size: 13px;
  line-height: 1.5;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted) / 45%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.chat-message {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 8px;
  margin-bottom: 12px;
}

.chat-message.is-user {
  grid-template-columns: minmax(0, 1fr) 28px;
}

.chat-message.is-user .message-avatar {
  grid-column: 2;
  color: #1677ff;
  background: rgb(22 119 255 / 10%);
}

.chat-message.is-user .message-bubble {
  grid-column: 1;
  grid-row: 1;
  color: #fff;
  background: #1677ff;
}

.message-avatar {
  width: 28px;
  height: 28px;
  color: #0f766e;
  background: rgb(15 118 110 / 10%);
  border-radius: 50%;
}

.message-avatar :deep(svg) {
  width: 15px;
  height: 15px;
}

.message-bubble {
  padding: 9px 10px;
  overflow-wrap: anywhere;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  background: hsl(var(--muted) / 55%);
  border-radius: 8px;
}

.message-actions {
  display: flex;
  gap: 8px;
  padding-top: 8px;
  margin-top: 8px;
  border-top: 1px solid hsl(var(--border));
}

.chat-message.is-error .message-avatar {
  color: #dc2626;
  background: rgb(220 38 38 / 10%);
}

.chat-message.is-error .message-bubble {
  color: #b91c1c;
  background: #fef2f2;
}

.loading-dot {
  color: hsl(var(--muted-foreground));
}

.chat-input {
  display: grid;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid hsl(var(--border));
}

.chat-input textarea {
  width: 100%;
  min-height: 76px;
  max-height: 160px;
  padding: 9px 10px;
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
  background: hsl(var(--background));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  outline: none;
}

.chat-input textarea:focus {
  border-color: #1677ff;
  box-shadow: 0 0 0 2px rgb(22 119 255 / 12%);
}

.chat-input textarea:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}

.chat-input-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}

.chat-input-actions span {
  min-width: 0;
  overflow: hidden;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 768px) {
  .maga-chat-panel {
    width: 100vw;
    border-left: 0;
  }

  .chat-title p {
    max-width: calc(100vw - 120px);
  }
}
</style>
