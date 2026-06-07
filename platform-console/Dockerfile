FROM node:20-alpine AS builder

WORKDIR /workspace

RUN corepack enable

COPY . .

ARG VITE_APP_TITLE="MAGA Console"
ENV VITE_APP_TITLE=${VITE_APP_TITLE}

RUN pnpm install --frozen-lockfile
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
