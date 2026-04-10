<script setup lang="ts">
import { onMounted, ref } from 'vue';

import { notification } from 'ant-design-vue';

interface NotificationOptions {
  // 通知标题
  title: string;
  // 通知描述
  description?: string;
  // 撤销按钮文本
  undoText?: string;
  // 撤销回调
  onUndo: () => Promise<void> | void;
  // 成功回调
  onSuccess?: () => void;
  // 显示时长（毫秒），0 表示不自动关闭
  duration?: number;
  // 类型
  type?: 'error' | 'info' | 'success' | 'warning';
}

const props = withDefaults(defineProps<NotificationOptions>(), {
  description: undefined,
  undoText: '撤销',
  onSuccess: () => {},
  duration: 4.5,
  type: 'info',
});

const notificationKey = ref(`undo-${Date.now()}`);

onMounted(() => {
  showNotification();
});

function showNotification() {
  const { title, description, onSuccess, duration, type } = props;

  notification[type]({
    key: notificationKey.value,
    message: title,
    description,
    duration: duration === 0 ? 0 : duration / 1000,
    style: {
      marginBottom: '24px',
    },
    // 自定义内容
    onClose: () => {
      if (onSuccess) {
        onSuccess();
      }
    },
    // 自定义 footer，添加撤销按钮
    class: 'custom-notification',
  });

  // 延迟添加撤销按钮（等待通知渲染完成）
  setTimeout(() => {
    addUndoButton();
  }, 100);
}

function addUndoButton() {
  // 找到通知元素并添加撤销按钮
  const notificationElement = document.querySelector(
    `[data-notification-key="${notificationKey.value}"]`,
  );

  if (!notificationElement) {
    console.warn('Notification element not found');
    return;
  }

  // 查找通知的 description 区域
  const descriptionElement = notificationElement.querySelector(
    '.ant-notification-description',
  );

  if (!descriptionElement) {
    console.warn('Notification description not found');
    return;
  }

  // 创建撤销按钮容器
  const actionContainer = document.createElement('div');
  actionContainer.className = 'undo-action-container';
  actionContainer.style.cssText = `
    margin-top: 12px;
    display: flex;
    gap: 8px;
    align-items: center;
  `;

  // 创建撤销按钮
  const undoButton = document.createElement('button');
  undoButton.className = 'undo-button';
  undoButton.textContent = props.undoText;
  undoButton.style.cssText = `
    padding: 4px 12px;
    border: 1px solid hsl(var(--primary));
    background: transparent;
    color: hsl(var(--primary));
    border-radius: 4px;
    cursor: pointer;
    font-size: 13px;
    transition: all 0.2s ease;
  `;

  // 添加悬停效果
  undoButton.addEventListener('mouseenter', () => {
    undoButton.style.background = 'hsl(var(--primary) / 0.1)';
  });

  undoButton.addEventListener('mouseleave', () => {
    undoButton.style.background = 'transparent';
  });

  // 添加点击事件
  undoButton.addEventListener('click', async () => {
    try {
      await props.onUndo();
      // 关闭通知
      notification.close(notificationKey.value);
    } catch (error) {
      console.error('Undo failed:', error);
      notification.error({
        key: `undo-error-${Date.now()}`,
        message: '撤销失败',
        description: error instanceof Error ? error.message : '未知错误',
        duration: 3,
      });
    }
  });

  // 添加倒计时提示
  if (props.duration > 0) {
    const countdownElement = document.createElement('span');
    countdownElement.className = 'undo-countdown';
    countdownElement.style.cssText = `
      font-size: 12px;
      color: hsl(var(--muted-foreground));
    `;

    let remaining = props.duration / 1000;
    countdownElement.textContent = `${remaining.toFixed(1)} 秒后自动关闭`;

    const countdownInterval = setInterval(() => {
      remaining -= 0.1;
      if (remaining <= 0) {
        clearInterval(countdownInterval);
        return;
      }
      countdownElement.textContent = `${remaining.toFixed(1)} 秒后自动关闭`;
    }, 100);

    actionContainer.append(countdownElement);
  }

  actionContainer.append(undoButton);
  descriptionElement.append(actionContainer);
}

// 暴露方法供外部调用
defineExpose({
  close: () => {
    notification.close(notificationKey.value);
  },
});
</script>

<template>
  <!-- 此组件不需要渲染内容，仅用于触发通知 -->
  <div style="display: none"></div>
</template>

<style scoped>
/* 全局样式已注入到通知中 */
</style>

<style>
@keyframes slide-in-up {
  from {
    opacity: 0;
    transform: translateY(10px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.undo-notification {
  position: relative;
}

.undo-action-container {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 12px;
  animation: slideInUp 0.3s ease-out;
}

.undo-button {
  padding: 4px 12px;
  font-size: 13px;
  color: hsl(var(--primary));
  cursor: pointer;
  background: transparent;
  border: 1px solid hsl(var(--primary));
  border-radius: 4px;
  transition: all 0.2s ease;
}

.undo-button:hover {
  background: hsl(var(--primary) / 10%);
  transform: translateY(-1px);
}

.undo-button:active {
  transform: translateY(0);
}

.undo-countdown {
  margin-left: auto;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

/* 全局撤销通知样式（注入到 document） */
</style>
