#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "${1:-start}" in
  start)
    make -C "$ROOT_DIR" dev
    ;;
  stop)
    make -C "$ROOT_DIR" dev-stop
    ;;
  restart)
    make -C "$ROOT_DIR" dev-restart
    ;;
  status)
    make -C "$ROOT_DIR" dev-status
    ;;
  logs)
    make -C "$ROOT_DIR" dev-logs
    ;;
  *)
    echo "Usage: $0 [start|stop|restart|status|logs]" >&2
    exit 1
    ;;
esac
