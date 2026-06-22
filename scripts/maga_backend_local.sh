#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
LABEL="${MAGA_LOCAL_BACKEND_LABEL:-com.luxifa.maga.backend.local}"
BACKEND_PORT="${BACKEND_PORT:-5100}"
BACKEND_LOG="${BACKEND_LOG:-$ROOT_DIR/.local/logs/backend-local.log}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"

MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-maga}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-maga123456}"
MYSQL_DATABASE="${MYSQL_DATABASE:-maga}"

MYSQL_ANALYTICS_HOST="${MYSQL_ANALYTICS_HOST:-$MYSQL_HOST}"
MYSQL_ANALYTICS_PORT="${MYSQL_ANALYTICS_PORT:-$MYSQL_PORT}"
MYSQL_ANALYTICS_USER="${MYSQL_ANALYTICS_USER:-$MYSQL_USER}"
MYSQL_ANALYTICS_PASSWORD="${MYSQL_ANALYTICS_PASSWORD:-$MYSQL_PASSWORD}"
MYSQL_ANALYTICS_DATABASE="${MYSQL_ANALYTICS_DATABASE:-$MYSQL_DATABASE}"

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"

usage() {
  cat <<USAGE
Usage: $0 [start|restart|stop|status|logs]

Commands:
  start    Start the MAGA backend locally on http://127.0.0.1:$BACKEND_PORT.
  restart  Stop and start the local backend.
  stop     Stop the local backend launchctl job.
  status   Show launchctl, port, and /docs health status.
  logs     Tail the local backend log.

Common env:
  BACKEND_PORT=$BACKEND_PORT
  MYSQL_HOST=$MYSQL_HOST
  MYSQL_PORT=$MYSQL_PORT
  MYSQL_USER=$MYSQL_USER
  MYSQL_DATABASE=$MYSQL_DATABASE
  REDIS_HOST=$REDIS_HOST
  REDIS_PORT=$REDIS_PORT
USAGE
}

ensure_dirs() {
  mkdir -p "$ROOT_DIR/.local/logs" "$ROOT_DIR/.local/pids"
}

stop_docker_backend_if_running() {
  if command -v docker >/dev/null 2>&1; then
    local container_id
    container_id="$(docker ps --filter 'name=^/maga-backend-1$' --format '{{.ID}}' 2>/dev/null || true)"
    if [[ -n "$container_id" ]]; then
      echo "Stopping Docker backend container maga-backend-1 to keep port $BACKEND_PORT local..."
      docker stop maga-backend-1 >/dev/null
    fi
  fi
}

is_launchctl_running() {
  launchctl list | grep -Fq "$LABEL"
}

is_http_ready() {
  /usr/bin/curl -fsS "http://127.0.0.1:$BACKEND_PORT/docs" >/dev/null 2>&1
}

start_backend() {
  ensure_dirs

  stop_docker_backend_if_running

  if is_http_ready; then
    echo "Local backend is already reachable on http://127.0.0.1:$BACKEND_PORT"
    return
  fi

  if is_launchctl_running; then
    echo "Removing stale launchctl job $LABEL..."
    launchctl remove "$LABEL" >/dev/null 2>&1 || true
    sleep 1
  fi

  : >"$BACKEND_LOG"
  echo "Starting local backend on http://127.0.0.1:$BACKEND_PORT ..."
  launchctl submit -l "$LABEL" \
    -- /bin/bash -lc "cd '$ROOT_DIR/platform-server' && exec env \
      APP_PORT='$BACKEND_PORT' \
      MYSQL_HOST='$MYSQL_HOST' MYSQL_PORT='$MYSQL_PORT' MYSQL_USER='$MYSQL_USER' MYSQL_PASSWORD='$MYSQL_PASSWORD' MYSQL_DATABASE='$MYSQL_DATABASE' \
      MYSQL_ANALYTICS_HOST='$MYSQL_ANALYTICS_HOST' MYSQL_ANALYTICS_PORT='$MYSQL_ANALYTICS_PORT' MYSQL_ANALYTICS_USER='$MYSQL_ANALYTICS_USER' MYSQL_ANALYTICS_PASSWORD='$MYSQL_ANALYTICS_PASSWORD' MYSQL_ANALYTICS_DATABASE='$MYSQL_ANALYTICS_DATABASE' \
      REDIS_HOST='$REDIS_HOST' REDIS_PORT='$REDIS_PORT' REDIS_PASSWORD='$REDIS_PASSWORD' \
      DAPR_HTTP_PORT='$BACKEND_PORT' \
      '$PYTHON_BIN' -m uvicorn app.main:app --host 0.0.0.0 --port '$BACKEND_PORT' >>'$BACKEND_LOG' 2>&1"

  for _ in {1..30}; do
    if is_http_ready; then
      echo "Local backend is ready: http://127.0.0.1:$BACKEND_PORT/docs"
      echo "Log: $BACKEND_LOG"
      return
    fi
    sleep 1
  done

  echo "Local backend did not become ready. Last log lines:" >&2
  tail -80 "$BACKEND_LOG" >&2 || true
  exit 1
}

stop_backend() {
  if is_launchctl_running; then
    echo "Stopping local backend job $LABEL..."
    launchctl remove "$LABEL"
  else
    echo "Local backend launchctl job is not running."
  fi
}

wait_until_stopped() {
  for _ in {1..15}; do
    if ! is_http_ready && ! lsof -nP -iTCP:"$BACKEND_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
      return
    fi
    sleep 1
  done

  echo "Local backend is still listening on port $BACKEND_PORT after stop." >&2
  lsof -nP -iTCP:"$BACKEND_PORT" -sTCP:LISTEN >&2 || true
  exit 1
}

status_backend() {
  if is_launchctl_running; then
    echo "launchctl: running ($LABEL)"
    launchctl list | grep -F "$LABEL" || true
  else
    echo "launchctl: stopped ($LABEL)"
  fi

  echo
  lsof -nP -iTCP:"$BACKEND_PORT" -sTCP:LISTEN || true

  echo
  if is_http_ready; then
    echo "http: ready http://127.0.0.1:$BACKEND_PORT/docs"
  else
    echo "http: not ready on http://127.0.0.1:$BACKEND_PORT/docs"
  fi
}

case "${1:-start}" in
  start)
    start_backend
    ;;
  restart)
    stop_backend
    wait_until_stopped
    start_backend
    ;;
  stop)
    stop_backend
    ;;
  status)
    status_backend
    ;;
  logs)
    ensure_dirs
    touch "$BACKEND_LOG"
    tail -f "$BACKEND_LOG"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
