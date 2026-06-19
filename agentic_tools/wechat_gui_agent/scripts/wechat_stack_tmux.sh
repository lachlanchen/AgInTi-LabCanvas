#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
WEB_SESSION="${WECHAT_WEB_SESSION:-labcanvas-web-wechat}"
WEB_HOST="${WECHAT_WEB_HOST:-127.0.0.1}"
WEB_PORT="${WECHAT_WEB_PORT:-19474}"
export PYTHONPATH="$ROOT/src:${PYTHONPATH:-}"

usage() {
  cat <<'EOF'
Usage:
  wechat_stack_tmux.sh start|stop|restart|status

Starts or stops the complete reusable WeChat chatops stack:
  - labcanvas-wechat tmux supervisor for WeChat desktop, fast monitor, worker, and media sync
  - labcanvas-web-wechat tmux web app session for the browser control panel

Environment:
  WECHAT_WEB_SESSION          tmux session name for web app, default labcanvas-web-wechat
  WECHAT_WEB_HOST             web app host, default 127.0.0.1
  WECHAT_WEB_PORT             web app port, default 19474
EOF
}

action="${1:-start}"
case "$action" in
  start)
    python3 -m agenticapp wechat hold start
    python3 -m agenticapp webapp start --host "$WEB_HOST" --port "$WEB_PORT" --session "$WEB_SESSION"
    echo "WeChat stack ready."
    python3 -m agenticapp wechat status
    ;;
  stop)
    python3 -m agenticapp wechat hold stop || true
    python3 -m agenticapp webapp stop --session "$WEB_SESSION" || true
    ;;
  restart)
    "$0" stop || true
    "$0" start
    ;;
  status)
    python3 -m agenticapp wechat status
    python3 -m agenticapp webapp status --session "$WEB_SESSION" || true
    ;;
  --help|-h|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
