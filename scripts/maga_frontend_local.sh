#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
LABEL="${MAGA_LOCAL_FRONTEND_LABEL:-com.luxifa.maga.frontend.local}"
FRONTEND_PORT="${FRONTEND_PORT:-3102}"
BACKEND_PORT="${BACKEND_PORT:-5100}"
FRONTEND_LOG="${FRONTEND_LOG:-$ROOT_DIR/.local/logs/frontend.log}"
NODE_BIN="${NODE_BIN:-$(command -v node)}"
VITE_BIN="$ROOT_DIR/platform-console/node_modules/vite/bin/vite.js"

ensure_dirs() {
  mkdir -p "$ROOT_DIR/.local/logs"
}

is_launchctl_running() {
  launchctl list | grep -Fq "$LABEL"
}

is_http_ready() {
  /usr/bin/curl -fsS "http://127.0.0.1:$FRONTEND_PORT/" >/dev/null 2>&1
}

start_frontend() {
  ensure_dirs
  [[ -x "$NODE_BIN" ]] || { echo "Node.js binary not found: $NODE_BIN" >&2; exit 1; }
  [[ -f "$VITE_BIN" ]] || { echo "Vite is not installed: $VITE_BIN" >&2; exit 1; }

  if lsof -nP -iTCP:"$FRONTEND_PORT" -sTCP:LISTEN >/dev/null 2>&1 && ! is_launchctl_running; then
    echo "Port $FRONTEND_PORT is already occupied by another process:" >&2
    lsof -nP -iTCP:"$FRONTEND_PORT" -sTCP:LISTEN >&2 || true
    exit 1
  fi
  if is_launchctl_running && is_http_ready; then
    echo "Local frontend is already reachable on http://127.0.0.1:$FRONTEND_PORT"
    return
  fi
  if is_launchctl_running; then
    launchctl remove "$LABEL" >/dev/null 2>&1 || true
    sleep 1
  fi

  : >"$FRONTEND_LOG"
  echo "Starting local frontend on http://127.0.0.1:$FRONTEND_PORT ..."
  launchctl submit -l "$LABEL" \
    -- /bin/bash -c "cd '$ROOT_DIR/platform-console/apps/raap-admin' && exec env \
      VITE_PORT='$FRONTEND_PORT' VITE_PROXY_TARGET='http://127.0.0.1:$BACKEND_PORT' \
      '$NODE_BIN' '$VITE_BIN' --mode development >>'$FRONTEND_LOG' 2>&1"

  for _ in {1..30}; do
    if is_http_ready; then
      echo "Local frontend is ready: http://127.0.0.1:$FRONTEND_PORT"
      echo "Log: $FRONTEND_LOG"
      return
    fi
    sleep 1
  done

  echo "Local frontend did not become ready. Last log lines:" >&2
  tail -80 "$FRONTEND_LOG" >&2 || true
  exit 1
}

stop_frontend() {
  if is_launchctl_running; then
    echo "Stopping local frontend job $LABEL..."
    launchctl remove "$LABEL"
  else
    echo "Local frontend launchctl job is not running."
  fi
}

status_frontend() {
  if is_launchctl_running; then
    echo "launchctl: running ($LABEL)"
    launchctl list | grep -F "$LABEL" || true
  else
    echo "launchctl: stopped ($LABEL)"
  fi
  if is_http_ready; then
    echo "http: ready http://127.0.0.1:$FRONTEND_PORT"
  else
    echo "http: not ready on http://127.0.0.1:$FRONTEND_PORT"
  fi
}

case "${1:-start}" in
  start) start_frontend ;;
  restart) stop_frontend; start_frontend ;;
  stop) stop_frontend ;;
  status) status_frontend ;;
  logs) ensure_dirs; touch "$FRONTEND_LOG"; tail -f "$FRONTEND_LOG" ;;
  *) echo "Usage: $0 [start|restart|stop|status|logs]" >&2; exit 2 ;;
esac
