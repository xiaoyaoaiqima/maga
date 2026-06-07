#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_DIR="${MAGA_DEPLOY_DIR:-/home/ubuntu/maga}"
FRONTEND_DIR="${MAGA_FRONTEND_DIR:-/var/www/maga-console}"
LOCK_FILE="${MAGA_DEPLOY_LOCK_FILE:-/tmp/maga-deploy.lock}"
COMPOSE_FILE="${MAGA_COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${MAGA_ENV_FILE:-.env.prod}"
IMAGE_TAG="${MAGA_FRONTEND_IMAGE_TAG:-maga-console:deploy}"

log() {
  printf '[maga-deploy] %s\n' "$*"
}

run_compose() {
  sudo -n docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" "$@"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "missing required command: $1"
    exit 1
  fi
}

main() {
  require_command rsync
  require_command flock
  require_command sudo
  require_command docker
  require_command curl

  exec 9>"${LOCK_FILE}"
  flock -n 9 || {
    log "another deployment is running"
    exit 1
  }

  local source_dir
  source_dir="$(pwd)"
  log "source: ${source_dir}"
  log "deploy dir: ${DEPLOY_DIR}"

  mkdir -p "${DEPLOY_DIR}"

  # 线上密钥、数据库卷、历史前端包都只保留在服务器，不随代码同步覆盖。
  rsync -az --delete \
    --exclude '.git/' \
    --exclude '.env' \
    --exclude '.env.local' \
    --exclude '.env.prod' \
    --exclude '.local/' \
    --exclude 'outputs/' \
    --exclude 'frontend-dist/' \
    --exclude 'node_modules/' \
    --exclude '**/node_modules/' \
    --exclude '.pnpm-store/' \
    "${source_dir}/" "${DEPLOY_DIR}/"

  cd "${DEPLOY_DIR}"

  if [[ ! -f "${ENV_FILE}" ]]; then
    log "missing ${DEPLOY_DIR}/${ENV_FILE}; create it from .env.prod.example first"
    exit 1
  fi

  log "building and restarting backend/worker"
  run_compose up -d --build

  log "building frontend image"
  sudo -n docker build \
    -f platform-console/Dockerfile \
    -t "${IMAGE_TAG}" \
    platform-console

  local container_id
  local tmp_frontend
  container_id="$(sudo -n docker create "${IMAGE_TAG}")"
  tmp_frontend="$(mktemp -d)"
  trap 'sudo -n docker rm -f "${container_id}" >/dev/null 2>&1 || true; rm -rf "${tmp_frontend}"' EXIT

  sudo -n docker cp "${container_id}:/usr/share/nginx/html/." "${tmp_frontend}/"

  log "publishing frontend to ${FRONTEND_DIR}"
  mkdir -p "${FRONTEND_DIR}"
  rsync -az --delete "${tmp_frontend}/" "${FRONTEND_DIR}/"

  log "checking backend readiness"
  for _ in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:5100/api/v1/health/ready >/dev/null; then
      break
    fi
    sleep 2
  done
  curl -fsS http://127.0.0.1:5100/api/v1/health/ready >/dev/null

  log "checking worker health"
  run_compose exec -T maga-worker curl -fsS http://127.0.0.1:8765/health >/dev/null

  log "deployment finished: ${CI_COMMIT_SHA:-local}"
}

main "$@"
