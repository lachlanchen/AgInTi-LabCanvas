#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
PRIVATE_ENV="$ROOT/agentic_tools/wechat_gui_agent/.private/wechat_supervisor.local.env"
LOG_DIR="$ROOT/output/wechat_gui_agent/$(date +%F)"
mkdir -p "$LOG_DIR"

if [[ -f "$PRIVATE_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$PRIVATE_ENV"
  set +a
fi

if [[ "${WECHAT_WORKER_SKIP_SELFTEST:-0}" != "1" ]]; then
  echo "[$(date -Is)] running worker selftest suite=all" >> "$LOG_DIR/supervisor-worker-selftest.log"
  PYTHONPATH="$ROOT/src:${PYTHONPATH:-}" python3 -m agenticapp wechat selftest --suite all --json \
    >> "$LOG_DIR/supervisor-worker-selftest.log" 2>&1
  echo "[$(date -Is)] worker selftest suite=all passed" >> "$LOG_DIR/supervisor-worker-selftest.log"
fi

exec python3 -u "$ROOT/agentic_tools/wechat_gui_agent/scripts/wechat_task_worker.py" "$@"
