#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
source "$ROOT/scripts/labcanvas_storage_gate.sh"

NAME="${1:-service}"
if [[ $# -lt 2 ]]; then
  echo "Usage: wechat_restart_loop.sh NAME command [args...]" >&2
  exit 2
fi
shift

DELAY="${WECHAT_RESTART_DELAY:-5}"

while true; do
  if ! labcanvas_storage_ready; then
    sleep "${LABCANVAS_STORAGE_RETRY_SECONDS:-60}"
    continue
  fi
  echo "[$(date --iso-8601=seconds)] starting $NAME: $*"
  set +e
  "$@"
  code=$?
  set -e
  echo "[$(date --iso-8601=seconds)] $NAME exited with code $code; restarting in ${DELAY}s"
  sleep "$DELAY"
done
