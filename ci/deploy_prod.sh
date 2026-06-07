#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_DIR="${MAGA_DEPLOY_DIR:-/home/ubuntu/maga}"
FRONTEND_DIR="${MAGA_FRONTEND_DIR:-/var/www/maga-console}"
LOCK_FILE="${MAGA_DEPLOY_LOCK_FILE:-/tmp/maga-deploy.lock}"
COMPOSE_FILE="${MAGA_COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${MAGA_ENV_FILE:-.env.prod}"
IMAGE_TAG="${MAGA_FRONTEND_IMAGE_TAG:-maga-console:deploy}"
FRONTEND_CONTAINER_ID=""
TMP_FRONTEND_DIR=""

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

cleanup_frontend_publish() {
  # EXIT trap 会在 main 返回后执行，清理状态必须放在局部作用域外。
  if [[ -n "${FRONTEND_CONTAINER_ID}" ]]; then
    sudo -n docker rm -f "${FRONTEND_CONTAINER_ID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${TMP_FRONTEND_DIR}" ]]; then
    rm -rf "${TMP_FRONTEND_DIR}"
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

  # 线上密钥、运营语料和临时数据可能没有进入 Git；代码同步不做 --delete，
  # 避免部署时误删服务器上的业务数据。前端静态产物发布阶段会单独 --delete。
  rsync -az \
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

  FRONTEND_CONTAINER_ID="$(sudo -n docker create "${IMAGE_TAG}")"
  TMP_FRONTEND_DIR="$(mktemp -d)"
  trap cleanup_frontend_publish EXIT

  sudo -n docker cp "${FRONTEND_CONTAINER_ID}:/usr/share/nginx/html/." "${TMP_FRONTEND_DIR}/"

  log "publishing frontend to ${FRONTEND_DIR}"
  mkdir -p "${FRONTEND_DIR}"
  rsync -az --delete "${TMP_FRONTEND_DIR}/" "${FRONTEND_DIR}/"

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
