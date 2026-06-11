FROM node:20-alpine AS builder

WORKDIR /workspace

RUN corepack enable

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
COPY apps/raap-admin/package.json apps/raap-admin/package.json
COPY internal/lint-configs/commitlint-config/package.json internal/lint-configs/commitlint-config/package.json
COPY internal/lint-configs/eslint-config/package.json internal/lint-configs/eslint-config/package.json
COPY internal/lint-configs/prettier-config/package.json internal/lint-configs/prettier-config/package.json
COPY internal/lint-configs/stylelint-config/package.json internal/lint-configs/stylelint-config/package.json
COPY internal/node-utils/package.json internal/node-utils/package.json
COPY internal/tailwind-config/package.json internal/tailwind-config/package.json
COPY internal/tsconfig/package.json internal/tsconfig/package.json
COPY internal/vite-config/package.json internal/vite-config/package.json
COPY packages/@core/base/design/package.json packages/@core/base/design/package.json
COPY packages/@core/base/icons/package.json packages/@core/base/icons/package.json
COPY packages/@core/base/shared/package.json packages/@core/base/shared/package.json
COPY packages/@core/base/typings/package.json packages/@core/base/typings/package.json
COPY packages/@core/composables/package.json packages/@core/composables/package.json
COPY packages/@core/preferences/package.json packages/@core/preferences/package.json
COPY packages/@core/ui-kit/form-ui/package.json packages/@core/ui-kit/form-ui/package.json
COPY packages/@core/ui-kit/layout-ui/package.json packages/@core/ui-kit/layout-ui/package.json
COPY packages/@core/ui-kit/menu-ui/package.json packages/@core/ui-kit/menu-ui/package.json
COPY packages/@core/ui-kit/popup-ui/package.json packages/@core/ui-kit/popup-ui/package.json
COPY packages/@core/ui-kit/shadcn-ui/package.json packages/@core/ui-kit/shadcn-ui/package.json
COPY packages/@core/ui-kit/tabs-ui/package.json packages/@core/ui-kit/tabs-ui/package.json
COPY packages/constants/package.json packages/constants/package.json
COPY packages/effects/access/package.json packages/effects/access/package.json
COPY packages/effects/common-ui/package.json packages/effects/common-ui/package.json
COPY packages/effects/hooks/package.json packages/effects/hooks/package.json
COPY packages/effects/layouts/package.json packages/effects/layouts/package.json
COPY packages/effects/plugins/package.json packages/effects/plugins/package.json
COPY packages/effects/request/package.json packages/effects/request/package.json
COPY packages/icons/package.json packages/icons/package.json
COPY packages/locales/package.json packages/locales/package.json
COPY packages/preferences/package.json packages/preferences/package.json
COPY packages/stores/package.json packages/stores/package.json
COPY packages/styles/package.json packages/styles/package.json
COPY packages/types/package.json packages/types/package.json
COPY packages/utils/package.json packages/utils/package.json
COPY scripts/turbo-run/package.json scripts/turbo-run/package.json
COPY scripts/vsh/package.json scripts/vsh/package.json

ARG VITE_APP_TITLE="MAGA Console"
ENV VITE_APP_TITLE=${VITE_APP_TITLE}

RUN pnpm install --frozen-lockfile --ignore-scripts

COPY . .

# 依赖安装层尽量稳定；workspace stub 需要源码，所以放到源码复制后执行。
RUN pnpm -r run stub --if-present
# Build package entrypoints that production Vite resolves through dist.
RUN pnpm -r \
  --filter @vben-core/shared \
  --filter @vben-core/typings \
  --filter @vben-core/icons \
  --filter @vben-core/composables \
  --filter @vben-core/form-ui \
  --filter @vben-core/layout-ui \
  --filter @vben-core/menu-ui \
  --filter @vben-core/popup-ui \
  --filter @vben-core/tabs-ui \
  run build
RUN pnpm build

FROM nginx:1.27-alpine

COPY apps/raap-admin/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /workspace/apps/raap-admin/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
