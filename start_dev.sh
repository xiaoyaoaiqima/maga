#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_DIR="$ROOT_DIR/.local"
LOG_DIR="$LOCAL_DIR/logs"
PID_DIR="$LOCAL_DIR/pids"

MYSQL_BIN="${MYSQL_BIN:-/opt/homebrew/opt/mysql@8.4/bin/mysqld}"
MYSQL_CLI="${MYSQL_CLI:-/opt/homebrew/opt/mysql@8.4/bin/mysql}"
MYSQLADMIN_BIN="${MYSQLADMIN_BIN:-/opt/homebrew/opt/mysql@8.4/bin/mysqladmin}"
MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-maga}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-maga123456}"
MYSQL_DATABASE="${MYSQL_DATABASE:-maga}"
MYSQL_DATA_DIR="${MYSQL_DATA_DIR:-$LOCAL_DIR/mysql8-data}"
MYSQL_RUN_DIR="${MYSQL_RUN_DIR:-$LOCAL_DIR/mysql8-run}"

REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"

BACKEND_PORT="${BACKEND_PORT:-5100}"
FRONTEND_PORT="${FRONTEND_PORT:-3100}"

BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"
MYSQL_PID_FILE="$MYSQL_RUN_DIR/mysql.pid"

mkdir -p "$LOG_DIR" "$PID_DIR" "$MYSQL_RUN_DIR"

load_env() {
  if [[ -f "$ROOT_DIR/.env" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      line="${line%$'\r'}"
      [[ -z "$line" || "$line" == \#* ]] && continue
      if [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
        export "$line"
      fi
    done <"$ROOT_DIR/.env"
  fi

  export MYSQL_HOST="127.0.0.1"
  export MYSQL_PORT="$MYSQL_PORT"
  export MYSQL_USER="$MYSQL_USER"
  export MYSQL_PASSWORD="$MYSQL_PASSWORD"
  export MYSQL_DATABASE="$MYSQL_DATABASE"
  export REDIS_HOST="127.0.0.1"
  export REDIS_PORT="$REDIS_PORT"
}

is_pid_running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" >/dev/null 2>&1
}

stop_pid() {
  local name="$1"
  local pid_file="$2"

  if is_pid_running "$pid_file"; then
    local pid
    pid="$(cat "$pid_file")"
    echo "Stopping $name ($pid)..."
    kill "$pid" >/dev/null 2>&1 || true
    for _ in {1..20}; do
      kill -0 "$pid" >/dev/null 2>&1 || break
      sleep 0.2
    done
    kill -9 "$pid" >/dev/null 2>&1 || true
  fi
  rm -f "$pid_file"
}

mysql_alive() {
  "$MYSQLADMIN_BIN" -h "$MYSQL_HOST" -P "$MYSQL_PORT" -uroot ping >/dev/null 2>&1
}

redis_alive() {
  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping >/dev/null 2>&1
}

start_redis() {
  if redis_alive; then
    echo "Redis is already running on $REDIS_HOST:$REDIS_PORT"
    return
  fi

  if command -v brew >/dev/null 2>&1; then
    echo "Starting Redis via Homebrew..."
    brew services start redis >/dev/null
  elif command -v redis-server >/dev/null 2>&1; then
    echo "Starting Redis via redis-server..."
    redis-server --daemonize yes --port "$REDIS_PORT"
  else
    echo "redis-server or Homebrew is required to start Redis." >&2
    exit 1
  fi

  for _ in {1..30}; do
    redis_alive && {
      echo "Redis is ready on $REDIS_HOST:$REDIS_PORT"
      return
    }
    sleep 0.5
  done

  echo "Redis did not become ready. Check Homebrew service logs." >&2
  exit 1
}

initialize_mysql_if_needed() {
  if [[ -d "$MYSQL_DATA_DIR/mysql" ]]; then
    return
  fi

  if [[ ! -x "$MYSQL_BIN" ]]; then
    echo "MySQL binary not found: $MYSQL_BIN" >&2
    echo "Install mysql@8.4 with Homebrew or set MYSQL_BIN/MYSQL_CLI/MYSQLADMIN_BIN." >&2
    exit 1
  fi

  echo "Initializing project MySQL data directory: $MYSQL_DATA_DIR"
  mkdir -p "$MYSQL_DATA_DIR"
  "$MYSQL_BIN" --initialize-insecure --datadir="$MYSQL_DATA_DIR"
}

start_mysql() {
  if mysql_alive; then
    echo "MySQL is already running on $MYSQL_HOST:$MYSQL_PORT"
  else
    initialize_mysql_if_needed
    echo "Starting project MySQL on $MYSQL_HOST:$MYSQL_PORT..."
    "$MYSQL_BIN" \
      --daemonize \
      --datadir="$MYSQL_DATA_DIR" \
      --port="$MYSQL_PORT" \
      --bind-address="$MYSQL_HOST" \
      --socket="$MYSQL_RUN_DIR/mysql.sock" \
      --pid-file="$MYSQL_PID_FILE" \
      --log-error="$MYSQL_RUN_DIR/mysql.err"
  fi

  for _ in {1..40}; do
    mysql_alive && break
    sleep 0.5
  done

  if ! mysql_alive; then
    echo "MySQL did not become ready. See $MYSQL_RUN_DIR/mysql.err" >&2
    exit 1
  fi

  "$MYSQL_CLI" -h "$MYSQL_HOST" -P "$MYSQL_PORT" -uroot >/dev/null <<SQL
CREATE DATABASE IF NOT EXISTS $MYSQL_DATABASE CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$MYSQL_USER'@'localhost' IDENTIFIED BY '$MYSQL_PASSWORD';
CREATE USER IF NOT EXISTS '$MYSQL_USER'@'127.0.0.1' IDENTIFIED BY '$MYSQL_PASSWORD';
GRANT ALL PRIVILEGES ON $MYSQL_DATABASE.* TO '$MYSQL_USER'@'localhost';
GRANT ALL PRIVILEGES ON $MYSQL_DATABASE.* TO '$MYSQL_USER'@'127.0.0.1';
FLUSH PRIVILEGES;
SQL

  echo "MySQL is ready on $MYSQL_HOST:$MYSQL_PORT, database=$MYSQL_DATABASE"
}

start_backend() {
  stop_pid "backend" "$BACKEND_PID_FILE"
  echo "Starting backend on http://localhost:$BACKEND_PORT ..."

  (
    cd "$ROOT_DIR/platform-server"
    env \
      MYSQL_HOST="$MYSQL_HOST" \
      MYSQL_PORT="$MYSQL_PORT" \
      MYSQL_USER="$MYSQL_USER" \
      MYSQL_PASSWORD="$MYSQL_PASSWORD" \
      MYSQL_DATABASE="$MYSQL_DATABASE" \
      REDIS_HOST="$REDIS_HOST" \
      REDIS_PORT="$REDIS_PORT" \
      APP_PORT="$BACKEND_PORT" \
      PYTHONPATH=. \
      python app/main.py
  ) >"$LOG_DIR/backend.log" 2>&1 &

  echo $! >"$BACKEND_PID_FILE"
}

start_frontend() {
  stop_pid "frontend" "$FRONTEND_PID_FILE"
  echo "Starting frontend on http://localhost:$FRONTEND_PORT ..."

  (
    cd "$ROOT_DIR/platform-console"
    env \
      VITE_PORT="$FRONTEND_PORT" \
      VITE_PROXY_TARGET="http://localhost:$BACKEND_PORT" \
      pnpm dev
  ) >"$LOG_DIR/frontend.log" 2>&1 &

  echo $! >"$FRONTEND_PID_FILE"
}

start_all() {
  load_env
  start_mysql
  start_redis
  start_backend
  start_frontend

  echo
  echo "Development services started."
  echo "Backend:  http://localhost:$BACKEND_PORT"
  echo "Frontend: http://localhost:$FRONTEND_PORT"
  echo "Prompt optimizer: http://localhost:$FRONTEND_PORT/#/expert/prompt-optimizer"
  echo
  echo "Logs:"
  echo "  tail -f $LOG_DIR/backend.log"
  echo "  tail -f $LOG_DIR/frontend.log"
}

stop_all() {
  stop_pid "frontend" "$FRONTEND_PID_FILE"
  stop_pid "backend" "$BACKEND_PID_FILE"

  if is_pid_running "$MYSQL_PID_FILE"; then
    stop_pid "project mysql" "$MYSQL_PID_FILE"
  else
    rm -f "$MYSQL_PID_FILE"
  fi

  echo "Stopped frontend, backend, and project MySQL. Redis is left running."
}

status_all() {
  load_env
  if is_pid_running "$BACKEND_PID_FILE"; then
    echo "backend:  running ($(cat "$BACKEND_PID_FILE"))"
  else
    echo "backend:  stopped"
  fi

  if is_pid_running "$FRONTEND_PID_FILE"; then
    echo "frontend: running ($(cat "$FRONTEND_PID_FILE"))"
  else
    echo "frontend: stopped"
  fi

  if mysql_alive; then
    echo "mysql:    ready on $MYSQL_HOST:$MYSQL_PORT"
  else
    echo "mysql:    stopped"
  fi

  if redis_alive; then
    echo "redis:    ready on $REDIS_HOST:$REDIS_PORT"
  else
    echo "redis:    stopped"
  fi
}

logs_all() {
  mkdir -p "$LOG_DIR"
  touch "$LOG_DIR/backend.log" "$LOG_DIR/frontend.log"
  tail -f "$LOG_DIR/backend.log" "$LOG_DIR/frontend.log"
}

case "${1:-start}" in
  start)
    start_all
    ;;
  stop)
    stop_all
    ;;
  restart)
    stop_all
    start_all
    ;;
  status)
    status_all
    ;;
  logs)
    logs_all
    ;;
  *)
    echo "Usage: $0 [start|stop|restart|status|logs]" >&2
    exit 1
    ;;
esac
