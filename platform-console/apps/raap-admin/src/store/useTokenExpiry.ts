/**
 * Token 过期检查 composable
 * 用于定时检查 token 是否过期，过期时自动登出
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

import { useAccessStore } from '@vben/stores';

import { Modal, notification } from 'ant-design-vue';

/** 检查间隔（毫秒）- 每分钟检查一次 */
const CHECK_INTERVAL = 60 * 1000;

/** 提前警告时间（毫秒）- 提前 5 分钟警告 */
const WARNING_ADVANCE_TIME = 5 * 60 * 1000;

export function useTokenExpiry(options?: {
  /** 是否启用过期检查 */
  enabled?: boolean;
  /** 过期后的回调函数 */
  onExpired?: () => void;
  /** 即将过期时的警告回调 */
  onWarning?: (remainingMinutes: number) => void;
}) {
  const { enabled = true, onExpired, onWarning } = options ?? {};

  const accessStore = useAccessStore();
  const checkTimer = ref<null | ReturnType<typeof setInterval>>(null);
  const hasShownWarning = ref(false);

  /** Token 剩余时间（毫秒） */
  const remainingTime = ref(0);

  /** Token 剩余时间（分钟） */
  const remainingMinutes = computed(() =>
    Math.ceil(remainingTime.value / 60_000),
  );

  /** Token 是否已过期 */
  const isExpired = computed(
    () => accessStore.accessToken && accessStore.isTokenExpired(),
  );

  /** 是否即将过期（5分钟内） */
  const isAboutToExpire = computed(
    () =>
      remainingTime.value > 0 && remainingTime.value <= WARNING_ADVANCE_TIME,
  );

  /** 格式化剩余时间显示 */
  const formattedRemainingTime = computed(() => {
    const total = remainingTime.value;
    if (total <= 0) return '已过期';

    const hours = Math.floor(total / (1000 * 60 * 60));
    const minutes = Math.floor((total % (1000 * 60 * 60)) / (1000 * 60));

    if (hours > 0) {
      return `${hours}小时${minutes}分钟`;
    }
    return `${minutes}分钟`;
  });

  /** 执行过期检查 */
  function checkTokenExpiry() {
    if (!accessStore.accessToken) {
      remainingTime.value = 0;
      return;
    }

    remainingTime.value = accessStore.getTokenRemainingTime();

    // 检查是否已过期
    if (accessStore.isTokenExpired()) {
      handleExpired();
      return;
    }

    // 检查是否即将过期
    if (
      isAboutToExpire.value &&
      !hasShownWarning.value &&
      remainingMinutes.value > 0
    ) {
      hasShownWarning.value = true;
      handleWarning();
    }
  }

  /** 处理 token 过期 */
  function handleExpired() {
    stopChecking();

    notification.warning({
      message: '登录已过期',
      description: '您的登录会话已过期，请重新登录。',
      duration: 3,
    });

    if (onExpired) {
      onExpired();
    }
  }

  /** 处理即将过期警告 */
  function handleWarning() {
    if (onWarning) {
      onWarning(remainingMinutes.value);
    } else {
      // 默认显示模态框警告
      Modal.warning({
        title: '登录即将过期',
        content: `您的登录会话将在 ${remainingMinutes.value} 分钟后过期，请注意保存工作。`,
        okText: '知道了',
      });
    }
  }

  /** 开始定时检查 */
  function startChecking() {
    if (checkTimer.value) {
      return;
    }

    // 立即执行一次检查
    checkTokenExpiry();

    // 设置定时器
    checkTimer.value = setInterval(checkTokenExpiry, CHECK_INTERVAL);
  }

  /** 停止定时检查 */
  function stopChecking() {
    if (checkTimer.value) {
      clearInterval(checkTimer.value);
      checkTimer.value = null;
    }
  }

  /** 重置警告状态（用于重新登录后） */
  function resetWarning() {
    hasShownWarning.value = false;
  }

  // 监听 accessToken 变化
  watch(
    () => accessStore.accessToken,
    (newToken) => {
      if (newToken) {
        resetWarning();
        checkTokenExpiry();
      } else {
        remainingTime.value = 0;
      }
    },
  );

  // 组件挂载时启动检查
  onMounted(() => {
    if (enabled) {
      startChecking();
    }
  });

  // 组件卸载时停止检查
  onBeforeUnmount(() => {
    stopChecking();
  });

  return {
    /** 剩余时间（毫秒） */
    remainingTime,
    /** 剩余时间（分钟） */
    remainingMinutes,
    /** 是否已过期 */
    isExpired,
    /** 是否即将过期 */
    isAboutToExpire,
    /** 格式化的剩余时间 */
    formattedRemainingTime,
    /** 开始检查 */
    startChecking,
    /** 停止检查 */
    stopChecking,
    /** 手动检查一次 */
    checkTokenExpiry,
    /** 重置警告状态 */
    resetWarning,
  };
}
