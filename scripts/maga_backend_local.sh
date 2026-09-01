#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
LABEL="${MAGA_LOCAL_BACKEND_LABEL:-com.luxifa.maga.backend.local}"
BACKEND_PORT="${BACKEND_PORT:-5100}"
BACKEND_LOG="${BACKEND_LOG:-$ROOT_DIR/.local/logs/backend-local.log}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:///$ROOT_DIR/.local/maga.sqlite3}"

load_root_env() {
  [[ -f "$ROOT_DIR/.env" ]] || return
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" || "$line" == \#* || ! "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] && continue
    local key="${line%%=*}"
    if [[ -z "${!key+x}" ]]; then
      export "$line"
    fi
  done <"$ROOT_DIR/.env"
}

load_root_env

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
  DATABASE_URL=$DATABASE_URL
USAGE
}

ensure_dirs() {
  mkdir -p "$ROOT_DIR/.local/logs" "$ROOT_DIR/.local/pids"
}

is_launchctl_running() {
  launchctl list | grep -Fq "$LABEL"
}

is_http_ready() {
  /usr/bin/curl -fsS "http://127.0.0.1:$BACKEND_PORT/docs" >/dev/null 2>&1
}

start_backend() {
  ensure_dirs

  if lsof -nP -iTCP:"$BACKEND_PORT" -sTCP:LISTEN >/dev/null 2>&1 && ! is_launchctl_running; then
    echo "Port $BACKEND_PORT is already occupied by another process:" >&2
    lsof -nP -iTCP:"$BACKEND_PORT" -sTCP:LISTEN >&2 || true
    exit 1
  fi

  if is_launchctl_running && is_http_ready; then
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
      APP_ENV='development' MAGA_APP_MODE='clean' DATABASE_URL='$DATABASE_URL' MYSQL_ANALYTICS_ENABLED='false' \
      REDIS_ENABLED='false' RATE_LIMIT_ENABLED='false' DASHBOARD_CACHE_ENABLED='false' CACHE_WARMUP_ON_STARTUP='false' \
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
