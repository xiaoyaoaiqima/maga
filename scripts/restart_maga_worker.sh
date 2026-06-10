#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-/Users/luxifa/maga}"
WORKER_PORT="${WORKER_PORT:-8765}"
WORKER_HOST="${WORKER_HOST:-127.0.0.1}"
WORKER_CODE_PATH="${WORKER_CODE_PATH:-$ROOT_DIR/worker}"
WORKER_WORKSPACE="${WORKER_WORKSPACE:-$ROOT_DIR/worker/profiles/maga-worker}"
MAGA_WORKER_OUTPUT_DIR="${MAGA_WORKER_OUTPUT_DIR:-$ROOT_DIR/.local/worker/outputs}"
WORKER_LOG="${WORKER_LOG:-$ROOT_DIR/.local/logs/maga-worker.log}"
WORKER_PID="${WORKER_PID:-$ROOT_DIR/.local/pids/maga-worker.pid}"
WORKER_ENV_FILE="${WORKER_ENV_FILE:-$ROOT_DIR/.env}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"

usage() {
  cat <<USAGE
Usage: $0 [restart|start|stop|status]

Defaults:
  worker: $WORKER_HOST:$WORKER_PORT
  code: $WORKER_CODE_PATH
  workspace: $WORKER_WORKSPACE
  outputs: $MAGA_WORKER_OUTPUT_DIR
  log: $WORKER_LOG
USAGE
}

load_env() {
  if [[ ! -f "$WORKER_ENV_FILE" ]]; then
    return
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    if [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
      export "$line"
    fi
  done <"$WORKER_ENV_FILE"
}

health_ok() {
  curl -fsS "http://$WORKER_HOST:$WORKER_PORT/health" >/dev/null 2>&1
}

pid_alive() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

stop_pid() {
  local pid="$1"
  if ! pid_alive "$pid"; then
    return
  fi
  echo "Stopping maga-worker pid $pid ..."
  kill "$pid" >/dev/null 2>&1 || true
  for _ in {1..30}; do
    if ! pid_alive "$pid"; then
      return
    fi
    sleep 0.2
  done
  echo "Force stopping maga-worker pid $pid ..."
  kill -9 "$pid" >/dev/null 2>&1 || true
}

stop_worker() {
  if [[ -f "$WORKER_PID" ]]; then
    stop_pid "$(cat "$WORKER_PID" 2>/dev/null || true)"
  fi

  # 端口占用可能来自旧进程或 pid 文件丢失的 worker；这里按端口兜底清掉，
  # 确保下一次启动一定加载当前磁盘上的最新代码。
  if command -v lsof >/dev/null 2>&1; then
    while IFS= read -r pid; do
      [[ -z "$pid" ]] && continue
      stop_pid "$pid"
    done < <(lsof -tiTCP:"$WORKER_PORT" -sTCP:LISTEN 2>/dev/null || true)
  fi

  rm -f "$WORKER_PID"
}

start_worker() {
  mkdir -p "$(dirname "$WORKER_LOG")" "$(dirname "$WORKER_PID")" "$MAGA_WORKER_OUTPUT_DIR"
  : >"$WORKER_LOG"
  load_env

  if health_ok; then
    echo "maga-worker already running on http://$WORKER_HOST:$WORKER_PORT"
    echo "worker code: $WORKER_CODE_PATH"
    echo "worker profile: $WORKER_WORKSPACE"
    echo "worker outputs: $MAGA_WORKER_OUTPUT_DIR"
    return
  fi

  echo "Worker code: $WORKER_CODE_PATH"
  echo "Worker profile: $WORKER_WORKSPACE"
  echo "Worker outputs: $MAGA_WORKER_OUTPUT_DIR"

  "$PYTHON_BIN" - "$ROOT_DIR" "$WORKER_CODE_PATH" "$WORKER_WORKSPACE" "$MAGA_WORKER_OUTPUT_DIR" "$WORKER_LOG" "$WORKER_PID" "$WORKER_HOST" "$WORKER_PORT" <<'PY'
import os
import pathlib
import subprocess
import sys

root_dir, worker_code_path, worker_workspace, worker_output_dir, worker_log, worker_pid, worker_host, worker_port = sys.argv[1:9]
env = os.environ.copy()
env.update(
    {
        "MAGA_WORKER_EXECUTOR_TOKEN": env.get("MAGA_WORKER_EXECUTOR_TOKEN", "test-token"),
        "MAGA_WORKER_EXECUTION_MODE": env.get("MAGA_WORKER_EXECUTION_MODE", "runtime_fast"),
        "MAGA_WORKER_RUNTIME_FAST_FAKE": env.get("MAGA_WORKER_RUNTIME_FAST_FAKE", "0"),
        "PYTHONPATH": worker_code_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""),
        "WORKER_WORKSPACE": worker_workspace,
        "MAGA_WORKER_OUTPUT_DIR": worker_output_dir,
        "XHS_RUNTIME_API_KEY": env.get("XHS_RUNTIME_API_KEY") or env.get("OPENAI_API_KEY", ""),
        "XHS_RUNTIME_BASE_URL": env.get("XHS_RUNTIME_BASE_URL") or env.get("OPENAI_BASE_URL", ""),
        "XHS_RUNTIME_MODEL_GE": env.get("XHS_RUNTIME_MODEL_GE") or env.get("DEEPSEEK_MODEL", "deepseek-v3.2"),
        "XHS_RUNTIME_MODEL_AE": env.get("XHS_RUNTIME_MODEL_AE") or env.get("DEEPSEEK_MODEL", "deepseek-v3.2"),
    }
)
log_path = pathlib.Path(worker_log)
log_file = log_path.open("ab")
process = subprocess.Popen(
    [
        os.path.join(root_dir, ".venv/bin/python"),
        "-m",
        "uvicorn",
        "maga_worker.executor_server:app",
        "--host",
        worker_host,
        "--port",
        worker_port,
    ],
    cwd=root_dir,
    env=env,
    stdout=log_file,
    stderr=subprocess.STDOUT,
    start_new_session=True,
)
pathlib.Path(worker_pid).write_text(str(process.pid), encoding="utf-8")
print(process.pid)
PY

  for _ in {1..40}; do
    if health_ok; then
      echo "maga-worker: running ($(cat "$WORKER_PID")) on http://$WORKER_HOST:$WORKER_PORT"
      echo "Worker log: $WORKER_LOG"
      return
    fi
    sleep 0.25
  done

  echo "maga-worker failed to start. Last log lines:" >&2
  tail -80 "$WORKER_LOG" >&2 || true
  exit 1
}

status_worker() {
  if health_ok; then
    if [[ -f "$WORKER_PID" ]] && pid_alive "$(cat "$WORKER_PID" 2>/dev/null || true)"; then
      echo "maga-worker: running ($(cat "$WORKER_PID")) on http://$WORKER_HOST:$WORKER_PORT"
      echo "worker code: $WORKER_CODE_PATH"
      echo "worker profile: $WORKER_WORKSPACE"
      echo "worker outputs: $MAGA_WORKER_OUTPUT_DIR"
    else
      echo "maga-worker: running on http://$WORKER_HOST:$WORKER_PORT (pid not tracked)"
      echo "worker code: $WORKER_CODE_PATH"
      echo "worker profile: $WORKER_WORKSPACE"
      echo "worker outputs: $MAGA_WORKER_OUTPUT_DIR"
    fi
  else
    echo "maga-worker: stopped"
    return 1
  fi
}

command="${1:-restart}"
case "$command" in
  restart)
    stop_worker
    start_worker
    ;;
  start)
    start_worker
    ;;
  stop)
    stop_worker
    echo "maga-worker: stopped"
    ;;
  status)
    status_worker
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
