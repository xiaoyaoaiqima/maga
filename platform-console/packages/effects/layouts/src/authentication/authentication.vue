<script setup lang="ts">
import type { ToolbarType } from './types';

import { computed } from 'vue';

import { preferences, usePreferences } from '@vben/preferences';

import { Copyright } from '../basic/copyright';
import AuthenticationFormView from './form.vue';
import SloganIcon from './icons/slogan.vue';
import Toolbar from './toolbar.vue';

interface Props {
  appName?: string;
  logo?: string;
  logoDark?: string;
  pageTitle?: string;
  pageDescription?: string;
  sloganImage?: string;
  toolbar?: boolean;
  copyright?: boolean;
  toolbarList?: ToolbarType[];
  clickLogo?: () => void;
}

const props = withDefaults(defineProps<Props>(), {
  appName: '',
  copyright: true,
  logo: '',
  logoDark: '',
  pageDescription: '',
  pageTitle: '',
  sloganImage: '',
  toolbar: true,
  toolbarList: () => ['color', 'language', 'layout', 'theme'],
  clickLogo: () => {},
});

const { authPanelCenter, authPanelLeft, authPanelRight, isDark } =
  usePreferences();

/**
 * @zh_CN 根据主题选择合适的 logo 图标
 */
const logoSrc = computed(() => {
  // 如果是暗色主题且提供了 logoDark，则使用暗色主题的 logo
  if (isDark.value && props.logoDark) {
    return props.logoDark;
  }
  // 否则使用默认的 logo
  return props.logo;
});
</script>

<template>
  <div
    :class="[isDark ? 'dark' : '']"
    class="auth-page-shell flex min-h-full flex-1 select-none overflow-x-hidden"
  >
    <template v-if="toolbar">
      <slot name="toolbar">
        <Toolbar :toolbar-list="toolbarList" />
      </slot>
    </template>
    <!-- 左侧认证面板 -->
    <AuthenticationFormView
      v-if="authPanelLeft"
      class="auth-form-panel min-h-full w-2/5 flex-1"
      data-side="left"
    >
      <template v-if="copyright" #copyright>
        <slot name="copyright">
          <Copyright
            v-if="preferences.copyright.enable"
            v-bind="preferences.copyright"
          />
        </slot>
      </template>
    </AuthenticationFormView>

    <slot name="logo">
      <!-- 头部 Logo 和应用名称 -->
      <div
        v-if="logoSrc || appName"
        class="auth-logo absolute left-0 top-0 z-10 flex flex-1"
        @click="clickLogo"
      >
        <div
          class="text-foreground lg:text-foreground ml-4 mt-4 flex flex-1 items-center sm:left-6 sm:top-6"
        >
          <img
            v-if="logoSrc"
            :key="logoSrc"
            :alt="appName"
            :src="logoSrc"
            class="mr-2"
            width="42"
          />
          <p v-if="appName" class="m-0 text-xl font-medium">
            {{ appName }}
          </p>
        </div>
      </div>
    </slot>

    <!-- 系统介绍 -->
    <div v-if="!authPanelCenter" class="relative hidden w-0 flex-1 lg:block">
      <div
        class="auth-visual-panel bg-background-deep absolute inset-0 h-full w-full"
      >
        <div class="login-background absolute left-0 top-0 size-full"></div>
        <div
          :key="authPanelLeft ? 'left' : authPanelRight ? 'right' : 'center'"
          class="flex-col-center mr-20 h-full"
          :class="{
            'enter-x': authPanelLeft,
            '-enter-x': authPanelRight,
          }"
        >
          <template v-if="sloganImage">
            <img
              :alt="appName"
              :src="sloganImage"
              class="auth-slogan-image animate-float"
            />
          </template>
          <SloganIcon
            v-else
            :alt="appName"
            class="auth-slogan-image animate-float"
          />
          <div
            class="auth-slogan-title text-1xl text-foreground mt-6 font-sans lg:text-2xl"
          >
            {{ pageTitle }}
          </div>
          <div class="auth-slogan-description dark:text-muted-foreground mt-2">
            {{ pageDescription }}
          </div>
        </div>
      </div>
    </div>

    <!-- 中心认证面板 -->
    <div v-if="authPanelCenter" class="flex-center relative w-full">
      <div class="login-background absolute left-0 top-0 size-full"></div>
      <AuthenticationFormView
        class="auth-form-panel md:bg-background shadow-primary/5 shadow-float w-full rounded-3xl pb-20 md:w-2/3 lg:w-1/2 xl:w-[36%]"
        data-side="bottom"
      >
        <template v-if="copyright" #copyright>
          <slot name="copyright">
            <Copyright
              v-if="preferences.copyright.enable"
              v-bind="preferences.copyright"
            />
          </slot>
        </template>
      </AuthenticationFormView>
    </div>

    <!-- 右侧认证面板 -->
    <AuthenticationFormView
      v-if="authPanelRight"
      class="auth-form-panel min-h-full w-2/5 flex-1"
      data-side="right"
    >
      <template v-if="copyright" #copyright>
        <slot name="copyright">
          <Copyright
            v-if="preferences.copyright.enable"
            v-bind="preferences.copyright"
          />
        </slot>
      </template>
    </AuthenticationFormView>
  </div>
</template>

<style scoped>
.auth-page-shell {
  min-height: 100vh;
  background: #f8fafc;
}

.auth-page-shell.dark {
  background: #020617;
  color-scheme: dark;
}

.auth-logo {
  color: hsl(var(--foreground));
}

.auth-visual-panel {
  overflow: hidden;
  background: linear-gradient(
    120deg,
    rgba(241, 245, 249, 0.96) 0%,
    rgba(226, 232, 240, 0.9) 56%,
    rgba(238, 242, 255, 0.94) 100%
  );
}

.auth-visual-panel::before {
  position: absolute;
  inset: 0;
  pointer-events: none;
  content: '';
  background-image:
    linear-gradient(rgba(15, 23, 42, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15, 23, 42, 0.08) 1px, transparent 1px);
  background-size: 72px 72px;
  mask-image: linear-gradient(
    90deg,
    transparent,
    #000 18%,
    #000 82%,
    transparent
  );
  opacity: 0.32;
}

.auth-visual-panel::after {
  position: absolute;
  inset: 0;
  pointer-events: none;
  content: '';
  background:
    linear-gradient(
      112deg,
      transparent 8%,
      rgba(56, 189, 248, 0.14) 42%,
      transparent 54%
    ),
    linear-gradient(
      148deg,
      transparent 28%,
      rgba(244, 114, 182, 0.1) 64%,
      transparent 82%
    );
}

.login-background {
  background: linear-gradient(
    154deg,
    transparent 26%,
    hsl(var(--primary) / 22%) 48%,
    transparent 68%
  );
  opacity: 0.82;
  filter: blur(86px);
}

.auth-slogan-image {
  width: min(42%, 320px);
  height: auto;
  max-height: 300px;
  object-fit: contain;
  filter: drop-shadow(0 26px 42px rgba(15, 23, 42, 0.2));
}

.auth-slogan-title {
  font-weight: 650;
  letter-spacing: 0;
}

.auth-slogan-description {
  color: rgba(71, 85, 105, 0.82);
}

.auth-form-panel {
  background: hsl(var(--background));
}

.auth-form-panel :deep(.side-content) {
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

.auth-page-shell :deep(.auth-toolbar) {
  border: 1px solid rgba(148, 163, 184, 0.2);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.1);
}

.dark {
  .auth-logo {
    color: #f8fafc;

    img {
      filter: drop-shadow(0 10px 22px rgba(14, 165, 233, 0.22));
    }
  }

  .auth-visual-panel {
    background: linear-gradient(126deg, #030712 0%, #071525 48%, #050719 100%);
  }

  .auth-visual-panel::before {
    background-image:
      linear-gradient(rgba(148, 163, 184, 0.1) 1px, transparent 1px),
      linear-gradient(90deg, rgba(148, 163, 184, 0.1) 1px, transparent 1px);
    opacity: 0.24;
  }

  .auth-visual-panel::after {
    background:
      linear-gradient(
        112deg,
        transparent 10%,
        rgba(34, 211, 238, 0.11) 42%,
        transparent 56%
      ),
      linear-gradient(
        148deg,
        transparent 26%,
        rgba(217, 70, 239, 0.08) 64%,
        transparent 84%
      );
  }

  .login-background {
    background: linear-gradient(
      154deg,
      transparent 26%,
      hsl(var(--primary) / 18%) 48%,
      transparent 70%
    );
    opacity: 0.72;
    filter: blur(90px);
  }

  .auth-slogan-image {
    filter:
      drop-shadow(0 30px 46px rgba(0, 0, 0, 0.4))
      drop-shadow(0 0 24px rgba(56, 189, 248, 0.14));
  }

  .auth-slogan-title {
    color: #f8fafc;
  }

  .auth-slogan-description {
    color: rgba(203, 213, 225, 0.76);
  }

  .auth-form-panel {
    background: linear-gradient(
      180deg,
      rgba(7, 12, 26, 0.98),
      rgba(3, 7, 18, 0.99)
    );
    border-left: 1px solid rgba(148, 163, 184, 0.16);
    box-shadow: inset 1px 0 0 rgba(255, 255, 255, 0.04);
  }

  .auth-form-panel :deep(.side-content) {
    padding: 32px;
    background: linear-gradient(
      180deg,
      rgba(15, 23, 42, 0.62),
      rgba(2, 6, 23, 0.22)
    );
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-radius: 8px;
    box-shadow: 0 30px 80px rgba(0, 0, 0, 0.24);
    backdrop-filter: blur(16px);
  }

  .auth-form-panel :deep(h1),
  .auth-form-panel :deep(h2),
  .auth-form-panel :deep(h3) {
    color: #f8fafc;
  }

  .auth-form-panel :deep(.text-muted-foreground) {
    color: rgba(203, 213, 225, 0.68);
  }

  .auth-form-panel :deep(input) {
    color: #f8fafc;
    background: rgba(2, 6, 23, 0.72);
    border-color: rgba(148, 163, 184, 0.24);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
  }

  .auth-form-panel :deep(input::placeholder) {
    color: rgba(203, 213, 225, 0.5);
  }

  .auth-form-panel :deep(input:hover) {
    border-color: rgba(148, 163, 184, 0.38);
  }

  .auth-form-panel :deep(input:focus-visible) {
    border-color: rgba(56, 189, 248, 0.64);
    box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.16);
  }

  .auth-form-panel :deep(button[aria-label='login']) {
    background: linear-gradient(90deg, #0f8bff, #2f6bff);
    box-shadow: 0 16px 34px rgba(37, 99, 235, 0.28);
  }

  .auth-form-panel :deep(button[aria-label='login']:hover) {
    background: linear-gradient(90deg, #2395ff, #3d76ff);
  }

  .auth-page-shell :deep(.auth-toolbar) {
    background: rgba(15, 23, 42, 0.74);
    border-color: rgba(148, 163, 184, 0.18);
    box-shadow: 0 18px 42px rgba(0, 0, 0, 0.28);
    backdrop-filter: blur(18px);
  }

  .auth-page-shell :deep(.auth-toolbar button) {
    color: rgba(226, 232, 240, 0.84);
  }

  .auth-page-shell :deep(.auth-toolbar button:hover) {
    color: #f8fafc;
    background: rgba(51, 65, 85, 0.72);
  }
}

@media (max-width: 1023px) {
  .dark {
    .auth-form-panel {
      border-left: 0;
    }

    .auth-form-panel :deep(.side-content) {
      padding: 28px 24px;
    }
  }
}
</style>
