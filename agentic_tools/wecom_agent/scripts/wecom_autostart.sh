#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
TOOL_ROOT="$ROOT/agentic_tools/wecom_agent"
TMUX_SUPERVISOR="$TOOL_ROOT/scripts/wecom_tmux.sh"
PRIVATE_ENV="${WECOM_ENV_FILE:-$TOOL_ROOT/.private/wecom.local.env}"
STATE_DIR="${WECOM_AUTOSTART_STATE_DIR:-$ROOT/output/wecom/autostart}"
STATUS_HASH="$STATE_DIR/last-status.sha256"
LOG_FILE="$STATE_DIR/supervisor.log"
INTERVAL="${WECOM_AUTOSTART_INTERVAL_SECONDS:-60}"
STARTUP_WAIT="${WECOM_AUTOSTART_STARTUP_WAIT_SECONDS:-300}"
REPAIR_TIMEOUT="${WECOM_AUTOSTART_REPAIR_TIMEOUT_SECONDS:-180}"
ACTION="${1:-supervise}"

mkdir -p "$STATE_DIR"

log() {
  printf '%s %s\n' "$(date --iso-8601=seconds)" "$*" >>"$LOG_FILE"
}

runtime_ready() {
  [[ -x "$TMUX_SUPERVISOR" ]] \
    && [[ -f "$PRIVATE_ENV" ]] \
    && command -v tmux >/dev/null 2>&1 \
    && command -v flock >/dev/null 2>&1
}

wait_for_runtime() {
  local deadline=$(( $(date +%s) + STARTUP_WAIT ))
  while ! runtime_ready; do
    if (( $(date +%s) >= deadline )); then
      log "runtime unavailable after ${STARTUP_WAIT}s; will retry"
      return 1
    fi
    sleep 10
  done
}

record_result() {
  local state="$1"
  local body="$2"
  local signature previous=""
  signature="$(printf '%s\n%s' "$state" "$body" | sha256sum | awk '{print $1}')"
  [[ -f "$STATUS_HASH" ]] && previous="$(cat "$STATUS_HASH")"
  if [[ "$signature" != "$previous" ]]; then
    log "state=$state"
    while IFS= read -r line; do
      [[ -z "$line" ]] || log "  $line"
    done <<<"$body"
    printf '%s\n' "$signature" >"$STATUS_HASH"
  fi
}

repair_once() {
  local output rc=0
  wait_for_runtime || return 1
  output="$(timeout --signal=TERM --kill-after=10 "$REPAIR_TIMEOUT" \
    "$TMUX_SUPERVISOR" start 2>&1)" || rc=$?
  if (( rc == 0 )); then
    record_result ready "$output"
    return 0
  fi
  record_result "repair-failed-$rc" "$output"
  return "$rc"
}

status() {
  local rc=0
  "$TMUX_SUPERVISOR" status || rc=$?
  "$TOOL_ROOT/scripts/wecom_windows_client.sh" status --json || rc=$?
  printf 'autostart_log=%s\n' "$LOG_FILE"
  return "$rc"
}

supervise() {
  local sleep_pid=""
  cleanup() {
    [[ -z "$sleep_pid" ]] || kill "$sleep_pid" 2>/dev/null || true
    log "supervisor stopped"
    exit 0
  }
  trap cleanup INT TERM
  log "supervisor started interval=${INTERVAL}s"
  while true; do
    repair_once || true
    sleep "$INTERVAL" &
    sleep_pid=$!
    wait "$sleep_pid" || true
    sleep_pid=""
  done
}

case "$ACTION" in
  once|repair|start)
    repair_once
    ;;
  supervise|loop)
    supervise
    ;;
  status)
    status
    ;;
  *)
    echo "Usage: wecom_autostart.sh supervise|once|repair|status" >&2
    exit 2
    ;;
esac
