#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
CHAT="${WECHAT_CHAT_NAME:-wechat-chat}"
INTERVAL="${WECHAT_MEDIA_SYNC_INTERVAL:-30}"
SINCE_MINUTES="${WECHAT_MEDIA_SINCE_MINUTES:-1440}"

if [[ -z "${WECHAT_MEDIA_SOURCES:-}" ]]; then
  echo "WECHAT_MEDIA_SOURCES is empty; media sync loop is idle."
  echo "Set it to colon-separated WeChat download/cache folders."
  while true; do sleep "$INTERVAL"; done
fi

while true; do
  IFS=':' read -r -a SOURCES <<< "$WECHAT_MEDIA_SOURCES"
  ARGS=()
  for source in "${SOURCES[@]}"; do
    [[ -n "$source" ]] && ARGS+=(--source "$source")
  done
  if [[ ${#ARGS[@]} -gt 0 ]]; then
    python3 "$ROOT/agentic_tools/wechat_gui_agent/scripts/wechat_media_sync.py" \
      --chat "$CHAT" \
      "${ARGS[@]}" \
      --since-minutes "$SINCE_MINUTES" || true
  fi
  sleep "$INTERVAL"
done
