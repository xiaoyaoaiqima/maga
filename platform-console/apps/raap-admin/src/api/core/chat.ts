import { requestClient } from '#/api/request';

export interface ChatHistoryMessage {
  role: 'assistant' | 'user';
  content: string;
}

export interface ChatContext {
  page?: null | string;
  asset_key?: null | string;
  asset_type?: null | string;
  asset_version?: null | number | string;
  rule_id?: null | string;
  source_row_no?: null | number;
  business_rule?: null | string;
  corpus?: null | string;
  draft_corpus?: null | string;
  examples?: string[];
  supplements?: string[];
  test_report_summary?: null | Record<string, any>;
}

export interface ChatAction {
  type: 'fill_business_rule_draft' | 'fill_business_rule_examples';
  label: string;
  payload: Record<string, any>;
}

export interface SendChatMessageRequest {
  message: string;
  history: ChatHistoryMessage[];
  context?: ChatContext | null;
}

export interface SendChatMessageResponse {
  agent_code: string;
  agent_name: string;
  reply: string;
  actions: ChatAction[];
}

export async function sendChatMessageApi(data: SendChatMessageRequest) {
  return requestClient.post<SendChatMessageResponse>('/v1/chat/messages', data);
}
