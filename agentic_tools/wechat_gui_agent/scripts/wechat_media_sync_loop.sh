#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
CHAT="${WECHAT_CHAT_NAME:-wechat-chat}"
CHATS="${WECHAT_MEDIA_CHATS:-$CHAT}"
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
  IFS=',' read -r -a CHAT_LIST <<< "$CHATS"
  for sync_chat in "${CHAT_LIST[@]}"; do
    sync_chat="$(echo "$sync_chat" | xargs)"
    [[ -n "$sync_chat" ]] || continue
    python3 "$ROOT/agentic_tools/wechat_gui_agent/scripts/wechat_media_sync.py" \
      --chat "$sync_chat" \
      "${ARGS[@]}" \
      --since-minutes "$SINCE_MINUTES" \
      --summary-only || true
  done
  sleep "$INTERVAL"
done
