import { ref } from 'vue';

import { defineStore } from 'pinia';

import type { ChatContext, ChatAction } from '#/api';

export interface ChatDraftFillPayload {
  draft_corpus: string;
  request_id: string;
  rule_id?: null | string;
  source_row_no?: null | number;
}

export const useMagaChatStore = defineStore('maga-chat', () => {
  const open = ref(false);
  const context = ref<ChatContext | null>(null);
  const draftFillPayload = ref<ChatDraftFillPayload | null>(null);

  function setOpen(value: boolean) {
    open.value = value;
  }

  function openWithContext(nextContext: ChatContext) {
    context.value = nextContext;
    open.value = true;
  }

  function setContext(nextContext: ChatContext | null) {
    context.value = nextContext;
  }

  function clearContext() {
    context.value = null;
  }

  function requestDraftFill(action: ChatAction) {
    const draftCorpus = String(action.payload?.draft_corpus || '').trim();
    if (!draftCorpus) return;
    draftFillPayload.value = {
      draft_corpus: draftCorpus,
      request_id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      rule_id: action.payload?.rule_id ? String(action.payload.rule_id) : null,
      source_row_no:
        typeof action.payload?.source_row_no === 'number'
          ? action.payload.source_row_no
          : null,
    };
  }

  function clearDraftFillPayload(requestId?: string) {
    if (!requestId || draftFillPayload.value?.request_id === requestId) {
      draftFillPayload.value = null;
    }
  }

  return {
    open,
    context,
    draftFillPayload,
    setOpen,
    openWithContext,
    setContext,
    clearContext,
    requestDraftFill,
    clearDraftFillPayload,
  };
});
