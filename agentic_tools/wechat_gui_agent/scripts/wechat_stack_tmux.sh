#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
WEB_SESSION="${WECHAT_WEB_SESSION:-labcanvas-web-wechat}"
WEB_HOST="${WECHAT_WEB_HOST:-127.0.0.1}"
WEB_PORT="${WECHAT_WEB_PORT:-19474}"
CAREER_ENABLED="${WECHAT_STACK_START_CAREER:-1}"
CAREER_SESSION="${WECHAT_CAREER_SESSION:-labcanvas-career-daily}"
CAREER_SEND_CHAT="${WECHAT_CAREER_SEND_CHAT:-lachlanchan}"
CAREER_MORNING_TIME="${WECHAT_CAREER_MORNING_TIME:-08:30}"
CAREER_MODEL="${WECHAT_CAREER_AGENT_MODEL:-gpt-5.5}"
CAREER_EFFORT="${WECHAT_CAREER_AGENT_EFFORT:-xhigh}"
export PYTHONPATH="$ROOT/src:${PYTHONPATH:-}"

usage() {
  cat <<'EOF'
Usage:
  wechat_stack_tmux.sh start|stop|restart|restart-all|status

Starts or stops the complete reusable WeChat chatops stack:
  - labcanvas-wechat tmux supervisor for WeChat desktop, fast monitor, worker, and media sync
  - labcanvas-web-wechat tmux web app session for the browser control panel
  - labcanvas-career-daily tmux session for daily career/self-analysis reports

Normal restart preserves the official WeChat GUI and reloads only monitor,
worker, media-sync, web app, and daily scheduler processes. Use restart-all,
or stop then start, only when you intentionally want to restart the WeChat
client.

Environment:
  WECHAT_WEB_SESSION          tmux session name for web app, default labcanvas-web-wechat
  WECHAT_WEB_HOST             web app host, default 127.0.0.1
  WECHAT_WEB_PORT             web app port, default 19474
  WECHAT_STACK_START_CAREER   set 0 to leave daily scheduler unmanaged
  WECHAT_CAREER_SESSION       tmux session name for daily scheduler
  WECHAT_CAREER_SEND_CHAT     chat receiving daily report, default lachlanchan
  WECHAT_CAREER_MORNING_TIME  daily run time, default 08:30
  WECHAT_CAREER_AGENT_MODEL   default gpt-5.5
  WECHAT_CAREER_AGENT_EFFORT  default xhigh
EOF
}

start_career() {
  if [[ "$CAREER_ENABLED" == "0" ]]; then
    return 0
  fi
  python3 -m agenticapp wechat career-agent start \
    --send \
    --attach-report \
    --send-chat "$CAREER_SEND_CHAT" \
    --morning-time "$CAREER_MORNING_TIME" \
    --session "$CAREER_SESSION" \
    --model "$CAREER_MODEL" \
    --reasoning-effort "$CAREER_EFFORT"
}

restart_career() {
  if [[ "$CAREER_ENABLED" == "0" ]]; then
    return 0
  fi
  python3 -m agenticapp wechat career-agent restart \
    --send \
    --attach-report \
    --send-chat "$CAREER_SEND_CHAT" \
    --morning-time "$CAREER_MORNING_TIME" \
    --session "$CAREER_SESSION" \
    --model "$CAREER_MODEL" \
    --reasoning-effort "$CAREER_EFFORT"
}

stop_career() {
  if [[ "$CAREER_ENABLED" == "0" ]]; then
    return 0
  fi
  python3 -m agenticapp wechat career-agent stop --session "$CAREER_SESSION" || true
}

status_career() {
  if [[ "$CAREER_ENABLED" == "0" ]]; then
    echo "career scheduler: unmanaged"
    return 0
  fi
  python3 -m agenticapp wechat career-agent status --session "$CAREER_SESSION" || true
}

action="${1:-start}"
case "$action" in
  start)
    python3 -m agenticapp wechat hold start
    python3 -m agenticapp webapp start --host "$WEB_HOST" --port "$WEB_PORT" --session "$WEB_SESSION"
    start_career
    echo "WeChat stack ready."
    python3 -m agenticapp wechat status
    ;;
  stop)
    python3 -m agenticapp wechat hold stop || true
    python3 -m agenticapp webapp stop --session "$WEB_SESSION" || true
    stop_career
    ;;
  restart)
    python3 -m agenticapp wechat hold reload-workers
    python3 -m agenticapp webapp stop --session "$WEB_SESSION" || true
    python3 -m agenticapp webapp start --host "$WEB_HOST" --port "$WEB_PORT" --session "$WEB_SESSION"
    restart_career
    echo "WeChat stack reloaded without restarting the WeChat desktop."
    ;;
  restart-all)
    "$0" stop || true
    "$0" start
    ;;
  status)
    python3 -m agenticapp wechat status
    python3 -m agenticapp webapp status --session "$WEB_SESSION" || true
    status_career
    ;;
  --help|-h|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
