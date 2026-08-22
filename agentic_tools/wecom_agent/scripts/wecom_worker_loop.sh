#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
TOOL_ROOT="$ROOT/agentic_tools/wecom_agent"
PRIVATE_ENV="${WECOM_ENV_FILE:-$TOOL_ROOT/.private/wecom.local.env}"
QUEUE="${WECOM_TASK_QUEUE:-$TOOL_ROOT/.private/wecom_task_queue.jsonl}"
LOG_DIR="$ROOT/output/wecom/$(date +%F)"

if [[ -f "$PRIVATE_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$PRIVATE_ENV"
  set +a
fi

mkdir -p "$LOG_DIR"

# The shared routine orchestrator is execution code, not a transport fallback.
export WECHAT_WORKER_ANDROID_TEXT_FALLBACK=0
export WECHAT_WORKER_DISABLE_GUI_FILE_DOWNLOAD=1
export WECHAT_WORKER_DISABLE_MEDIA_SYNC_PREFLIGHT=1
export WECHAT_WORKER_DISABLE_GUI_MEDIA_CACHE_PROBE=1
export WECHAT_WORKER_DISABLE_LOW_QUALITY_IMAGE_CACHE_PROBE=1
export WECHAT_WORKER_DISABLE_GUI_MEDIA_CLICK_PROBE=1
export WECHAT_WORKER_DISABLE_AUTOPUBLISH_PREFLIGHT=1
export WECHAT_WORKER_DISABLE_DETERMINISTIC_VIDEO_PUBLISH=1
export WECHAT_WORKER_DISABLE_GENERATED_VIDEO_LAZYEDIT=1
# WeCom uses low effort for ordinary chat and selects medium, high, or xhigh for
# durable work through the shared model policy. Daily research has no
# queue deadline; these generous per-turn watchdogs only reap a genuinely hung
# subprocess, while exact-task artifacts remain recoverable and resumable.
export WECHAT_WORKER_CODEX_MODEL="${WECHAT_WORKER_CODEX_MODEL:-gpt-5.6-sol}"
export WECHAT_WORKER_MIN_EFFORT="${WECHAT_WORKER_MIN_EFFORT:-low}"
export WECHAT_WORKER_MAX_EFFORT="${WECHAT_WORKER_MAX_EFFORT:-xhigh}"
export WECHAT_WORKER_TIMEOUT_LOW_SECONDS="${WECHAT_WORKER_TIMEOUT_LOW_SECONDS:-900}"
export WECHAT_WORKER_TIMEOUT_MEDIUM_SECONDS="${WECHAT_WORKER_TIMEOUT_MEDIUM_SECONDS:-3600}"
export WECHAT_WORKER_TIMEOUT_HIGH_SECONDS="${WECHAT_WORKER_TIMEOUT_HIGH_SECONDS:-21600}"
export WECHAT_WORKER_TIMEOUT_XHIGH_SECONDS="${WECHAT_WORKER_TIMEOUT_XHIGH_SECONDS:-43200}"
export WECHAT_WORKER_TIMEOUT_MAX_SECONDS="${WECHAT_WORKER_TIMEOUT_MAX_SECONDS:-64800}"
export WECHAT_WORKER_TIMEOUT_ULTRA_SECONDS="${WECHAT_WORKER_TIMEOUT_ULTRA_SECONDS:-86400}"
export WECHAT_WORKER_STALE_IN_PROGRESS_SECONDS="${WECHAT_WORKER_STALE_IN_PROGRESS_SECONDS:-0}"
export WECHAT_WORKER_ENV_FILE="$PRIVATE_ENV"

exec "$ROOT/agentic_tools/wechat_gui_agent/scripts/wechat_worker_guarded_loop.sh" \
  --queue "$QUEUE" \
  --chat wecom \
  --loop \
  --send
