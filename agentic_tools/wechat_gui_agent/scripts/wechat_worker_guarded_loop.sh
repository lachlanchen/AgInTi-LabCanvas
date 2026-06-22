#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
LOG_DIR="$ROOT/output/wechat_gui_agent/$(date +%F)"
mkdir -p "$LOG_DIR"

if [[ "${WECHAT_WORKER_SKIP_SELFTEST:-0}" != "1" ]]; then
  echo "[$(date -Is)] running publish-poststage selftest" >> "$LOG_DIR/supervisor-worker-selftest.log"
  PYTHONPATH="$ROOT/src:${PYTHONPATH:-}" python3 -m agenticapp wechat selftest --suite publish-poststage --json \
    >> "$LOG_DIR/supervisor-worker-selftest.log" 2>&1
  echo "[$(date -Is)] publish-poststage selftest passed" >> "$LOG_DIR/supervisor-worker-selftest.log"
fi

exec python3 -u "$ROOT/agentic_tools/wechat_gui_agent/scripts/wechat_task_worker.py" "$@"
