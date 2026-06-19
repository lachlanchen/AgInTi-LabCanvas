#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
CHAT="${WECHAT_CHAT_NAME:-wechat-chat}"
INTERVAL="${WECHAT_MEDIA_SYNC_INTERVAL:-30}"
SINCE_MINUTES="${WECHAT_MEDIA_SINCE_MINUTES:-60}"

while true; do
  ARGS=(--auto-source)
  if [[ -n "${WECHAT_MEDIA_SOURCES:-}" ]]; then
    IFS=':' read -r -a SOURCES <<< "$WECHAT_MEDIA_SOURCES"
    for source in "${SOURCES[@]}"; do
      [[ -n "$source" ]] && ARGS+=(--source "$source")
    done
  fi
  python3 "$ROOT/agentic_tools/wechat_gui_agent/scripts/wechat_media_sync.py" \
    --chat "$CHAT" \
    "${ARGS[@]}" \
    --since-minutes "$SINCE_MINUTES" \
    --summary-only || true
  sleep "$INTERVAL"
done
