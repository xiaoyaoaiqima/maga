import { requestClient } from '#/api/request';

export namespace MessageApi {
  export interface MessageListItem {
    recipient_id: number;
    message_id: number;
    title: string;
    content: string;
    message_type: string;
    link?: string;
    sender_name?: string;
    is_read: boolean;
    create_time?: string;
    update_time?: string;
  }

  export interface MessageListResponse {
    total: number;
    skip: number;
    limit: number;
    items: MessageListItem[];
  }

  export interface UnreadCountResponse {
    count: number;
  }
}

export async function getUnreadCountApi(): Promise<number> {
  const res = await requestClient.get<MessageApi.UnreadCountResponse>(
    '/v1/messages/unread-count',
  );
  return res.count;
}

export async function listMessagesApi(params: {
  is_read?: boolean;
  limit: number;
  skip: number;
}): Promise<MessageApi.MessageListResponse> {
  return await requestClient.get<MessageApi.MessageListResponse>(
    '/v1/messages',
    {
      params,
    },
  );
}

export async function markMessageReadApi(recipient_id: number): Promise<void> {
  await requestClient.post(`/v1/messages/${recipient_id}/read`);
}

export async function markAllMessagesReadApi(): Promise<void> {
  await requestClient.post('/v1/messages/read-all');
}

export async function removeMessageApi(recipient_id: number): Promise<void> {
  await requestClient.delete(`/v1/messages/${recipient_id}`);
}

export async function clearAllMessagesApi(): Promise<void> {
  await requestClient.delete('/v1/messages');
}
