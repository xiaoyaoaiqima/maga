<script setup lang="ts">
import type { TableColumnType } from 'ant-design-vue';

import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { message as antMessage, Button } from 'ant-design-vue';

import {
  clearAllMessagesApi,
  listMessagesApi,
  markAllMessagesReadApi,
  markMessageReadApi,
  removeMessageApi,
} from '../../api/core/messages';

interface MessageRow {
  recipient_id: number;
  title: string;
  content: string;
  sender_name?: string;
  create_time?: string;
  is_read: boolean;
  link?: string;
}

type FilterTab = 'all' | 'read' | 'unread';

const router = useRouter();
const activeTab = ref<FilterTab>('all');
const isLoading = ref<boolean>(false);
const total = ref<number>(0);
const page = ref<number>(1);
const pageSize = ref<number>(20);
const rows = ref<MessageRow[]>([]);

const isReadFilter = computed<boolean | undefined>(() => {
  if (activeTab.value === 'unread') return false;
  if (activeTab.value === 'read') return true;
  return undefined;
});

const columns = computed<TableColumnType<MessageRow>[]>(() => {
  return [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
    },
    {
      title: '内容',
      dataIndex: 'content',
      key: 'content',
      ellipsis: true,
    },
    {
      title: '发送人',
      dataIndex: 'sender_name',
      key: 'sender_name',
      width: 120,
    },
    {
      title: '时间',
      dataIndex: 'create_time',
      key: 'create_time',
      width: 180,
    },
    {
      title: '状态',
      key: 'is_read',
      width: 100,
      customRender: ({ record }) => (record.is_read ? '已读' : '未读'),
    },
    {
      title: '操作',
      key: 'action',
      width: 220,
    },
  ];
});

async function fetch_list(): Promise<void> {
  if (isLoading.value) return;
  isLoading.value = true;
  try {
    const skip = (page.value - 1) * pageSize.value;
    const res = await listMessagesApi({
      skip,
      limit: pageSize.value,
      is_read: isReadFilter.value,
    });
    total.value = res.total;
    rows.value = res.items.map((x) => ({
      recipient_id: x.recipient_id,
      title: x.title,
      content: x.content,
      sender_name: x.sender_name,
      create_time: x.create_time,
      is_read: x.is_read,
      link: x.link,
    }));
  } catch (error: unknown) {
    console.error('[消息中心] 拉取失败', error);
    antMessage.error('拉取消息失败，请稍后重试');
  } finally {
    isLoading.value = false;
  }
}

async function handle_tab_change(key: string): Promise<void> {
  activeTab.value = (key as FilterTab) || 'all';
  page.value = 1;
  await fetch_list();
}

async function handle_mark_all_read(): Promise<void> {
  try {
    await markAllMessagesReadApi();
    antMessage.success('已全部标记为已读');
    await fetch_list();
  } catch (error: unknown) {
    console.error('[消息中心] 全部已读失败', error);
    antMessage.error('操作失败，请稍后重试');
  }
}

async function handle_mark_read(recipient_id: number): Promise<void> {
  try {
    await markMessageReadApi(recipient_id);
    await fetch_list();
  } catch (error: unknown) {
    console.error('[消息中心] 标记已读失败', error);
    antMessage.error('标记已读失败');
  }
}

async function handle_remove(recipient_id: number): Promise<void> {
  try {
    await removeMessageApi(recipient_id);
    antMessage.success('已删除');
    await fetch_list();
  } catch (error: unknown) {
    console.error('[消息中心] 删除失败', error);
    antMessage.error('删除失败');
  }
}

async function handle_clear_all(): Promise<void> {
  try {
    await clearAllMessagesApi();
    antMessage.success('已清空');
    page.value = 1;
    await fetch_list();
  } catch (error: unknown) {
    console.error('[消息中心] 清空失败', error);
    antMessage.error('清空失败');
  }
}

function handle_open_link(link?: string): void {
  if (!link) return;
  if (link.startsWith('http://') || link.startsWith('https://')) {
    window.open(link, '_blank');
    return;
  }
  router.push({ path: link }).catch(() => undefined);
}

onMounted(async () => {
  await fetch_list();
});
</script>

<template>
  <div class="p-4">
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
          消息中心
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-actions">
          <Button size="small" shape="round" @click="fetch_list">刷新</Button>
          <Button
            size="small"
            shape="round"
            type="primary"
            ghost
            @click="handle_mark_all_read"
          >
            全部已读
          </Button>
          <Button
            size="small"
            shape="round"
            type="primary"
            danger
            @click="handle_clear_all"
          >
            清空
          </Button>
        </div>
      </div>
    </div>

    <div class="rounded border border-border bg-card p-4">
      <a-tabs :active-key="activeTab" @change="handle_tab_change">
        <a-tab-pane key="all" tab="全部" />
        <a-tab-pane key="unread" tab="未读" />
        <a-tab-pane key="read" tab="已读" />
      </a-tabs>

      <a-table
        :columns="columns"
        :data-source="rows"
        :loading="isLoading"
        :row-key="(r) => r.recipient_id"
        :pagination="{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => {
            page = p;
            pageSize = ps;
            fetch_list();
          },
        }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'action'">
            <div class="flex flex-wrap gap-2">
              <Button
                size="small"
                :disabled="record.is_read"
                @click="handle_mark_read(record.recipient_id)"
              >
                标记已读
              </Button>
              <Button
                size="small"
                type="link"
                :disabled="!record.link"
                @click="handle_open_link(record.link)"
              >
                打开
              </Button>
              <Button
                size="small"
                danger
                @click="handle_remove(record.recipient_id)"
              >
                删除
              </Button>
            </div>
          </template>
        </template>
      </a-table>
    </div>
  </div>
</template>

<style scoped>
.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
}

.filter-actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
  margin-left: auto;
}
</style>
