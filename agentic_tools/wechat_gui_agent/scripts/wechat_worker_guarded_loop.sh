#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
PRIVATE_ENV="${WECHAT_WORKER_ENV_FILE:-$ROOT/agentic_tools/wechat_gui_agent/.private/wechat_supervisor.local.env}"
LOG_DIR="$ROOT/output/wechat_gui_agent/$(date +%F)"
SELFTEST_STATE_DIR="${WECHAT_WORKER_SELFTEST_STATE_DIR:-$ROOT/output/wechat_gui_agent/runtime}"
SELFTEST_LOCK="$SELFTEST_STATE_DIR/worker-selftest.lock"
SELFTEST_STAMP="$SELFTEST_STATE_DIR/worker-selftest-passed.sha256"
mkdir -p "$LOG_DIR"

if [[ -f "$PRIVATE_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$PRIVATE_ENV"
  set +a
fi

if [[ "${WECHAT_WORKER_SKIP_SELFTEST:-0}" != "1" ]]; then
  mkdir -p "$SELFTEST_STATE_DIR"
  exec 9>"$SELFTEST_LOCK"
  flock 9
  SELFTEST_SIGNATURE="$({
    git -C "$ROOT" rev-parse HEAD
    git -C "$ROOT" diff --no-ext-diff --binary -- \
      agentic_tools/wechat_gui_agent/scripts src tests configs/model-policy.json
  } | sha256sum | awk '{print $1}')"
  LAST_PASSED_SIGNATURE=""
  [[ ! -f "$SELFTEST_STAMP" ]] || LAST_PASSED_SIGNATURE="$(head -n 1 "$SELFTEST_STAMP")"
  if [[ "$LAST_PASSED_SIGNATURE" != "$SELFTEST_SIGNATURE" ]]; then
    echo "[$(date -Is)] running worker selftest suite=all signature=$SELFTEST_SIGNATURE" >> "$LOG_DIR/supervisor-worker-selftest.log"
    env \
      -u WECHAT_AGENT_BACKEND \
      -u WECHAT_AGENT_FORCE_BACKEND \
      -u WECHAT_AGENT_FORCE_DISABLE_AGINTI \
      -u WECHAT_AGENT_FALLBACK_TO_AGINTI \
      -u WECHAT_AGENT_FALLBACK_ON_TIMEOUT \
      -u WECHAT_WORKER_CODEX_MODEL \
      -u WECHAT_WORKER_DISABLE_GUI_FILE_DOWNLOAD \
      -u WECHAT_WORKER_DISABLE_MEDIA_SYNC_PREFLIGHT \
      -u WECHAT_WORKER_DISABLE_GUI_MEDIA_CACHE_PROBE \
      -u WECHAT_WORKER_DISABLE_LOW_QUALITY_IMAGE_CACHE_PROBE \
      -u WECHAT_WORKER_DISABLE_GUI_MEDIA_CLICK_PROBE \
      -u WECHAT_WORKER_DISABLE_AUTOPUBLISH_PREFLIGHT \
      -u WECHAT_WORKER_DISABLE_DETERMINISTIC_VIDEO_PUBLISH \
      -u WECHAT_WORKER_DISABLE_GENERATED_VIDEO_LAZYEDIT \
      WECHAT_WORKER_EXPIRE_LEGACY_QUEUE=0 \
      PYTHONPATH="$ROOT/src:${PYTHONPATH:-}" \
      python3 -m agenticapp wechat selftest --suite all --json \
      >> "$LOG_DIR/supervisor-worker-selftest.log" 2>&1
    printf '%s\n' "$SELFTEST_SIGNATURE" > "$SELFTEST_STAMP.tmp.$$"
    mv -f "$SELFTEST_STAMP.tmp.$$" "$SELFTEST_STAMP"
    echo "[$(date -Is)] worker selftest suite=all passed signature=$SELFTEST_SIGNATURE" >> "$LOG_DIR/supervisor-worker-selftest.log"
  else
    echo "[$(date -Is)] reusing passed worker selftest signature=$SELFTEST_SIGNATURE" >> "$LOG_DIR/supervisor-worker-selftest.log"
  fi
  flock -u 9
fi

export WECHAT_WORKER_EXPIRE_LEGACY_QUEUE="${WECHAT_WORKER_EXPIRE_LEGACY_QUEUE:-1}"
export WECHAT_WORKER_COMPACT_STDOUT="${WECHAT_WORKER_COMPACT_STDOUT:-1}"
exec python3 -u "$ROOT/agentic_tools/wechat_gui_agent/scripts/wechat_task_worker.py" "$@"
