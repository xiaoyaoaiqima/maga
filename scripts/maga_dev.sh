#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-/Users/luxifa/maga}"
WORKER_PORT="${WORKER_PORT:-8765}"
WORKER_CODE_PATH="${WORKER_CODE_PATH:-$ROOT_DIR/worker}"
WORKER_WORKSPACE="${WORKER_WORKSPACE:-$ROOT_DIR/worker/profiles/maga-worker}"
MAGA_WORKER_OUTPUT_DIR="${MAGA_WORKER_OUTPUT_DIR:-$ROOT_DIR/.local/worker/outputs}"
WORKER_LOG="${WORKER_LOG:-$ROOT_DIR/.local/logs/maga-worker.log}"
WORKER_PID="${WORKER_PID:-$ROOT_DIR/.local/pids/maga-worker.pid}"
WORKER_ENV_FILE="${WORKER_ENV_FILE:-$ROOT_DIR/.env}"

usage() {
  cat <<USAGE
Usage: $0 [start|restart|stop|status|logs]

Commands:
  start    Start Docker MAGA stack, seed schema, start worker if absent.
  restart  Restart worker with latest local code, start Docker MAGA stack, and seed schema.
  stop     Stop worker and Docker MAGA stack.
  status   Show Docker and worker status.
  logs     Print log commands for Docker and worker.

Common env:
  WORKER_PORT=$WORKER_PORT
  WORKER_CODE_PATH=$WORKER_CODE_PATH
  WORKER_WORKSPACE=$WORKER_WORKSPACE
  MAGA_WORKER_OUTPUT_DIR=$MAGA_WORKER_OUTPUT_DIR
USAGE
}

cd "$ROOT_DIR"
mkdir -p .local/logs .local/pids

pid_alive() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

start_docker_stack() {
  docker compose up --build -d mysql redis backend
}

stop_docker_stack() {
  docker compose down
}

seed_schema() {
  make init-clean-schema
}

start_worker() {
  WORKER_PORT="$WORKER_PORT" \
    WORKER_CODE_PATH="$WORKER_CODE_PATH" \
    WORKER_WORKSPACE="$WORKER_WORKSPACE" \
    MAGA_WORKER_OUTPUT_DIR="$MAGA_WORKER_OUTPUT_DIR" \
    WORKER_LOG="$WORKER_LOG" \
    WORKER_PID="$WORKER_PID" \
    WORKER_ENV_FILE="$WORKER_ENV_FILE" \
    "$ROOT_DIR/scripts/restart_maga_worker.sh" start
}

restart_worker() {
  WORKER_PORT="$WORKER_PORT" \
    WORKER_CODE_PATH="$WORKER_CODE_PATH" \
    WORKER_WORKSPACE="$WORKER_WORKSPACE" \
    MAGA_WORKER_OUTPUT_DIR="$MAGA_WORKER_OUTPUT_DIR" \
    WORKER_LOG="$WORKER_LOG" \
    WORKER_PID="$WORKER_PID" \
    WORKER_ENV_FILE="$WORKER_ENV_FILE" \
    "$ROOT_DIR/scripts/restart_maga_worker.sh" restart
}

stop_worker() {
  WORKER_PORT="$WORKER_PORT" \
    WORKER_CODE_PATH="$WORKER_CODE_PATH" \
    WORKER_WORKSPACE="$WORKER_WORKSPACE" \
    MAGA_WORKER_OUTPUT_DIR="$MAGA_WORKER_OUTPUT_DIR" \
    WORKER_LOG="$WORKER_LOG" \
    WORKER_PID="$WORKER_PID" \
    WORKER_ENV_FILE="$WORKER_ENV_FILE" \
    "$ROOT_DIR/scripts/restart_maga_worker.sh" stop
}

status_worker() {
  WORKER_PORT="$WORKER_PORT" \
    WORKER_CODE_PATH="$WORKER_CODE_PATH" \
    WORKER_WORKSPACE="$WORKER_WORKSPACE" \
    MAGA_WORKER_OUTPUT_DIR="$MAGA_WORKER_OUTPUT_DIR" \
    WORKER_LOG="$WORKER_LOG" \
    WORKER_PID="$WORKER_PID" \
    WORKER_ENV_FILE="$WORKER_ENV_FILE" \
    "$ROOT_DIR/scripts/restart_maga_worker.sh" status || true
}

status_all() {
  docker compose ps
  status_worker
}

case "${1:-start}" in
  start)
    start_docker_stack
    seed_schema
    start_worker
    status_all
    ;;
  restart)
    stop_worker
    start_docker_stack
    seed_schema
    restart_worker
    status_all
    ;;
  stop)
    stop_worker
    stop_docker_stack
    ;;
  status)
    status_all
    ;;
  logs)
    echo "Docker logs:   docker compose logs -f"
    echo "Worker log:    tail -f $WORKER_LOG"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
