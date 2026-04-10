/**
 * MAGA Console - 优化的 Toast 通知系统
 *
 * 特性：
 * - 美化的样式
 * - 自动消失倒计时
 * - 操作按钮支持
 * - 进度条显示
 */

import { h } from 'vue';

import CheckCircleOutlined from '@ant-design/icons-vue/es/icons/CheckCircleOutlined';
import CloseCircleOutlined from '@ant-design/icons-vue/es/icons/CloseCircleOutlined';
import ExclamationCircleOutlined from '@ant-design/icons-vue/es/icons/ExclamationCircleOutlined';
import InfoCircleOutlined from '@ant-design/icons-vue/es/icons/InfoCircleOutlined';
import { notification } from 'ant-design-vue';

interface ToastOptions {
  // 标题
  title: string;
  // 描述
  description?: string;
  // 类型
  type?: 'error' | 'info' | 'success' | 'warning';
  // 显示时长（秒），0 表示不自动关闭
  duration?: number;
  // 是否显示进度条
  showProgress?: boolean;
  // 操作按钮
  action?: {
    onClick: () => Promise<void> | void;
    text: string;
    type?: 'danger' | 'default' | 'primary';
  };
  // 关闭回调
  onClose?: () => void;
}

class ToastManager {
  private activeToasts = new Map<string, NodeJS.Timeout>();

  /**
   * 关闭所有 Toast
   */
  closeAll(): void {
    notification.destroy();
    this.activeToasts.clear();
  }

  /**
   * 错误提示
   */
  error(options: Omit<ToastOptions, 'type'>): void {
    this.show({ ...options, type: 'error' });
  }

  /**
   * 信息提示
   */
  info(options: Omit<ToastOptions, 'type'>): void {
    this.show({ ...options, type: 'info' });
  }

  /**
   * 成功提示
   */
  success(options: Omit<ToastOptions, 'type'>): void {
    this.show({ ...options, type: 'success' });
  }

  /**
   * 警告提示
   */
  warning(options: Omit<ToastOptions, 'type'>): void {
    this.show({ ...options, type: 'warning' });
  }

  /**
   * 添加进度条
   */
  private addProgressBar(key: string, duration: number, color: string): void {
    const notificationElement = document.querySelector(
      `[data-notification-key="${key}"]`,
    );

    if (!notificationElement) return;

    // 创建进度条容器
    const progressContainer = document.createElement('div');
    progressContainer.className = 'toast-progress-container';
    progressContainer.style.cssText = `
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: ${color}20;
      overflow: hidden;
      border-radius: 0 0 8px 8px;
    `;

    // 创建进度条
    const progressBar = document.createElement('div');
    progressBar.className = 'toast-progress-bar';
    progressBar.style.cssText = `
      height: 100%;
      width: 100%;
      background: ${color};
      transform-origin: left;
      transition: transform linear;
      animation: toastProgress ${duration}s linear;
    `;

    progressContainer.append(progressBar);
    notificationElement.append(progressContainer);
  }

  /**
   * 显示 Toast
   */
  private show(options: ToastOptions): void {
    const {
      title,
      description,
      type = 'info',
      duration = 3,
      showProgress = false,
      action,
      onClose,
    } = options;

    const key = `toast-${Date.now()}-${Math.random()}`;

    // 图标映射
    const iconMap = {
      success: CheckCircleOutlined,
      error: CloseCircleOutlined,
      warning: ExclamationCircleOutlined,
      info: InfoCircleOutlined,
    };

    const IconComponent = iconMap[type];

    // 颜色映射
    const colorMap = {
      success: 'hsl(142 76% 36%)',
      error: 'hsl(0 84% 60%)',
      warning: 'hsl(38 92% 50%)',
      info: 'hsl(199 89% 48%)',
    };

    const themeColor = colorMap[type];

    notification.open({
      key,
      message: h('div', { class: 'toast-header' }, [
        h(IconComponent, {
          style: {
            color: themeColor,
            fontSize: '18px',
            marginRight: '8px',
          },
        }),
        h('span', { class: 'toast-title' }, title),
      ]),
      description: description
        ? h('div', { class: 'toast-description' }, description)
        : undefined,
      duration,
      class: `custom-toast custom-toast-${type}`,
      style: {
        borderRadius: '12px',
        padding: '16px 20px',
        boxShadow: `0 8px 24px -4px ${themeColor}20`,
        borderLeft: `4px solid ${themeColor}`,
      },
      onClose: () => {
        this.activeToasts.delete(key);
        if (onClose) onClose();
      },
      // 自定义操作按钮
      btn: action
        ? h(
            'button',
            {
              class: 'toast-action-button',
              style: {
                padding: '4px 12px',
                border: `1px solid ${themeColor}`,
                background: 'transparent',
                color: themeColor,
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '13px',
                transition: 'all 0.2s ease',
                marginTop: '8px',
              },
              onClick: async () => {
                try {
                  await action.onClick();
                  notification.close(key);
                } catch (error) {
                  console.error('Toast action failed:', error);
                }
              },
              onMouseenter: (e: Event) => {
                const target = e.target as HTMLElement;
                target.style.background = `${themeColor}10`;
              },
              onMouseleave: (e: Event) => {
                const target = e.target as HTMLElement;
                target.style.background = 'transparent';
              },
            },
            action.text,
          )
        : undefined,
    });

    // 进度条
    if (showProgress && duration > 0) {
      setTimeout(() => {
        this.addProgressBar(key, duration, themeColor);
      }, 100);
    }
  }
}

// 创建全局实例
export const toast = new ToastManager();

// 导出便捷方法
export const showToast = (options: ToastOptions) => toast.show(options);
export const showSuccess = (options: Omit<ToastOptions, 'type'>) =>
  toast.success(options);
export const showError = (options: Omit<ToastOptions, 'type'>) =>
  toast.error(options);
export const showWarning = (options: Omit<ToastOptions, 'type'>) =>
  toast.warning(options);
export const showInfo = (options: Omit<ToastOptions, 'type'>) =>
  toast.info(options);

// 添加全局样式
if (typeof document !== 'undefined') {
  const style = document.createElement('style');
  style.textContent = `
    @keyframes toastProgress {
      from { transform: scaleX(1); }
      to { transform: scaleX(0); }
    }

    .custom-toast {
      position: relative;
      overflow: hidden;
    }

    .toast-header {
      display: flex;
      align-items: center;
      font-weight: 500;
      font-size: 14px;
    }

    .toast-title {
      flex: 1;
    }

    .toast-description {
      margin-top: 8px;
      font-size: 13px;
      color: hsl(var(--muted-foreground));
      line-height: 1.5;
    }

    .toast-action-button:hover {
      transform: translateY(-1px);
    }

    .toast-action-button:active {
      transform: translateY(0);
    }

    /* 不同类型的 Toast 样式 */
    .custom-toast-success {
      background: linear-gradient(135deg, hsl(142 76% 96%) 0%, hsl(142 76% 98%) 100%);
    }

    .custom-toast-error {
      background: linear-gradient(135deg, hsl(0 84% 96%) 0%, hsl(0 84% 98%) 100%);
    }

    .custom-toast-warning {
      background: linear-gradient(135deg, hsl(38 92% 96%) 0%, hsl(38 92% 98%) 100%);
    }

    .custom-toast-info {
      background: linear-gradient(135deg, hsl(199 89% 96%) 0%, hsl(199 89% 98%) 100%);
    }
  `;
  document.head.append(style);
}
