#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
PRIVATE="$ROOT/agentic_tools/wechat_gui_agent/.private"
PY="$PRIVATE/wechat_decrypt/.venv/bin/python"
DECRYPT="$PRIVATE/external/wechat-decrypt/decrypt_db.py"
LOCK="$PRIVATE/wechat_decrypt.refresh.lock"
INTERVAL="${WECHAT_DECRYPT_REFRESH_INTERVAL:-4}"
TIMEOUT="${WECHAT_DECRYPT_TIMEOUT:-45}"

if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

while true; do
  start="$(date --iso-8601=seconds)"
  echo "[$start] refreshing decrypted WeChat cache"
  tmp="$(mktemp)"
  set +e
  flock -w "$TIMEOUT" "$LOCK" timeout "$TIMEOUT" "$PY" "$DECRYPT" >"$tmp" 2>&1
  code=$?
  set -e
  if [[ "$code" -eq 0 ]]; then
    grep -E '结果:|解密文件在:' "$tmp" | tail -n 2 || true
  else
    tail -n 80 "$tmp" || true
  fi
  rm -f "$tmp"
  echo "[$(date --iso-8601=seconds)] refresh exited with code $code"
  sleep "$INTERVAL"
done
