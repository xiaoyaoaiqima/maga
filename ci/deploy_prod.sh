#!/usr/bin/env bash
set -Eeuo pipefail

DEPLOY_DIR="${MAGA_DEPLOY_DIR:-/home/ubuntu/maga}"
FRONTEND_DIR="${MAGA_FRONTEND_DIR:-/var/www/maga-console}"
LOCK_FILE="${MAGA_DEPLOY_LOCK_FILE:-/tmp/maga-deploy.lock}"
COMPOSE_FILE="${MAGA_COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${MAGA_ENV_FILE:-.env.prod}"
IMAGE_TAG="${MAGA_FRONTEND_IMAGE_TAG:-maga-console:deploy}"
DEPLOY_SCOPE="${MAGA_DEPLOY_SCOPE:-auto}"
BUILD_BACKEND=1
BUILD_FRONTEND=1
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

is_zero_sha() {
  [[ "$1" =~ ^0+$ ]]
}

resolve_deploy_targets() {
  local scope="$1"

  case "${scope}" in
    all)
      BUILD_BACKEND=1
      BUILD_FRONTEND=1
      ;;
    backend)
      BUILD_BACKEND=1
      BUILD_FRONTEND=0
      ;;
    frontend)
      BUILD_BACKEND=0
      BUILD_FRONTEND=1
      ;;
    auto)
      BUILD_BACKEND=1
      BUILD_FRONTEND=1

      if [[ -z "${CI_COMMIT_BEFORE_SHA:-}" ]] ||
        [[ -z "${CI_COMMIT_SHA:-}" ]] ||
        is_zero_sha "${CI_COMMIT_BEFORE_SHA}" ||
        ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        log "auto scope falls back to full deploy"
      else
        BUILD_BACKEND=0
        BUILD_FRONTEND=0
        local changed_files
        changed_files="$(git diff --name-only "${CI_COMMIT_BEFORE_SHA}" "${CI_COMMIT_SHA}")"

        if [[ -z "${changed_files}" ]]; then
          log "auto scope found no changed files"
        else
          while IFS= read -r changed_file; do
            case "${changed_file}" in
              platform-console/*)
                BUILD_FRONTEND=1
                ;;
              platform-server/* | worker/* | docker-compose.prod.yml | .env.prod.example)
                BUILD_BACKEND=1
                ;;
              ci/deploy_prod.sh | .gitlab-ci.yml | docs/* | README.md | AGENTS.md)
                ;;
              *)
                # 未分类文件保守处理，避免漏部署共享运行时配置。
                BUILD_BACKEND=1
                BUILD_FRONTEND=1
                ;;
            esac
          done <<<"${changed_files}"
        fi
      fi
      ;;
    *)
      log "invalid MAGA_DEPLOY_SCOPE=${scope}; expected auto/all/backend/frontend"
      exit 1
      ;;
  esac

  log "deploy scope=${scope}; backend=${BUILD_BACKEND}; frontend=${BUILD_FRONTEND}"
}

cleanup_frontend_publish() {
  # EXIT trap 会在 main 返回后执行，清理状态必须放在局部作用域外。
  if [[ -n "${FRONTEND_CONTAINER_ID}" ]]; then
    sudo -n docker rm -f "${FRONTEND_CONTAINER_ID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${TMP_FRONTEND_DIR}" ]]; then
    sudo -n rm -rf "${TMP_FRONTEND_DIR}"
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
  resolve_deploy_targets "${DEPLOY_SCOPE}"

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

  if [[ "${BUILD_BACKEND}" == "1" ]]; then
    log "building and restarting backend/worker"
    run_compose up -d --build
  else
    log "skipping backend rebuild"
  fi

  if [[ "${BUILD_FRONTEND}" == "1" ]]; then
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
    # Nginx 以 www-data 读取静态目录，目录本身必须可进入，否则首页会变成 404。
    sudo -n install -d -m 0755 -o "$(id -u)" -g "$(id -g)" "${FRONTEND_DIR}"
    rsync -az --delete "${TMP_FRONTEND_DIR}/" "${FRONTEND_DIR}/"
    # rsync 会保留临时目录自身权限；mktemp 默认 0700，发布后必须重新开放目录进入权限给 nginx。
    sudo -n chmod 0755 "${FRONTEND_DIR}"
  else
    log "skipping frontend rebuild"
  fi

  log "checking backend readiness"
  for _ in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:5100/api/v1/health/ready >/dev/null; then
      break
    fi
    sleep 2
  done
  curl -fsS http://127.0.0.1:5100/api/v1/health/ready >/dev/null

  if [[ -n "$(run_compose ps -q maga-worker 2>/dev/null || true)" ]]; then
    log "checking worker health"
    run_compose exec -T maga-worker curl -fsS http://127.0.0.1:8765/health >/dev/null
  else
    log "skipping worker health check; maga-worker is not running"
  fi

  log "checking frontend publication"
  test -x "${FRONTEND_DIR}"
  test -r "${FRONTEND_DIR}/index.html"
  curl -fsSI http://127.0.0.1/ >/dev/null
  curl -fsSI http://127.0.0.1/content-agent/workbench >/dev/null

  log "deployment finished: ${CI_COMMIT_SHA:-local}"
}

main "$@"
