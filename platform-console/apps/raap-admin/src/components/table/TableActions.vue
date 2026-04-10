<!--
  表格操作列统一组件

  @example
  <template #bodyCell="{ column, record }">
    <TableActions
      :actions="getActions(record)"
      :record="record"
      :max-display="3"
      @click="handleActionClick"
    />
  </template>
-->
<script setup lang="ts">
import type { TableAction } from './types';

import { computed } from 'vue';

import { VbenIconButton } from '@vben-core/shadcn-ui';

import { MoreOutlined } from '@ant-design/icons-vue';
import { Dropdown, Modal, Space } from 'ant-design-vue';

import TableActionItem from './TableActionItem.vue';

/**
 * 表格操作组件属性
 */
export interface Props {
  /** 操作按钮列表 */
  actions: TableAction[];
  /** 当前行数据 */
  record?: any;
  /** 最多显示几个按钮，超出放入下拉菜单（默认 3） */
  maxDisplay?: number;
  /** 按钮间距（默认 4px） */
  spacing?: number;
  /** 是否紧凑模式（默认 false） */
  compact?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  maxDisplay: 3,
  spacing: 4,
  compact: false,
  record: undefined,
});

const emit = defineEmits<{
  click: [action: TableAction];
}>();

/** 显示的按钮（已绑定 record） */
const displayActions = computed(() => {
  return props.actions.slice(0, props.maxDisplay).map((action) => ({
    ...action,
    record: props.record,
  }));
});

/** 下拉菜单中的按钮（已绑定 record） */
const dropdownActions = computed(() => {
  return props.actions.slice(props.maxDisplay).map((action) => ({
    ...action,
    record: props.record,
  }));
});

/** 是否有下拉菜单 */
const hasDropdown = computed(() => dropdownActions.value.length > 0);

/** 处理按钮点击 */
const handleClick = async (action: TableAction) => {
  if (action.disabled) return;

  // 如果有确认配置，使用 Modal 确认
  if (action.confirm) {
    Modal.confirm({
      title: action.confirm.title || '确定执行此操作？',
      okText: action.confirm.okText || '确定',
      cancelText: action.confirm.cancelText || '取消',
      okType: action.danger ? 'danger' : undefined,
      onOk: async () => {
        // 如果配置了 onClick，执行它
        if (action.onClick) {
          await action.onClick();
        }
        emit('click', action);
      },
    });
    return;
  }

  // 如果配置了 onClick，优先执行
  if (action.onClick) {
    await action.onClick();
  }

  emit('click', action);
};
</script>

<template>
  <div class="table-actions">
    <Space :size="spacing" class="table-actions-visible">
      <TableActionItem
        v-for="action in displayActions"
        :key="action.key"
        :action="action"
        @click="handleClick(action)"
      />
    </Space>

    <!-- 更多操作下拉菜单 -->
    <Dropdown v-if="hasDropdown" :trigger="['click']">
      <template #overlay>
        <div class="dropdown-menu">
          <div
            v-for="action in dropdownActions"
            :key="action.key"
            class="dropdown-menu-item"
            :class="{
              'dropdown-menu-item-danger': action.danger,
              'dropdown-menu-item-disabled': action.disabled,
            }"
            @click="handleClick(action)"
          >
            <component :is="action.icon" class="dropdown-menu-item-icon" />
            <span>{{ action.label }}</span>
          </div>
        </div>
      </template>
      <VbenIconButton class="action-btn-more" tooltip="更多操作">
        <MoreOutlined />
      </VbenIconButton>
    </Dropdown>
  </div>
</template>

<style scoped>
.table-actions {
  display: flex;
  gap: 4px;
  align-items: center;
}

.table-actions-visible {
  display: flex;
  align-items: center;
}

.action-btn-more {
  font-size: 14px;
}

/* 下拉菜单样式 */
.dropdown-menu {
  min-width: 120px;
  padding: 4px 0;
  background: white;
  border-radius: 6px;
  box-shadow: 0 2px 8px rgb(0 0 0 / 15%);
}

.dropdown-menu-item {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  font-size: 14px;
  color: hsl(var(--foreground));
  cursor: pointer;
  transition: background-color 0.2s;
}

.dropdown-menu-item:hover:not(.dropdown-menu-item-disabled) {
  background-color: hsl(var(--accent) / 8%);
}

.dropdown-menu-item-icon {
  display: flex;
  align-items: center;
  font-size: 14px;
}

.dropdown-menu-item-danger {
  color: hsl(var(--destructive));
}

.dropdown-menu-item-danger:hover {
  background-color: hsl(var(--destructive) / 10%);
}

.dropdown-menu-item-disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
</style>
