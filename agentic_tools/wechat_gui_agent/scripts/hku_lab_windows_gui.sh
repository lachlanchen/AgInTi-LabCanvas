#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PRIVATE_DIR="$ROOT/agentic_tools/wechat_gui_agent/.private/remote_hosts/hku-lab-lachlan"
CONFIG_PATH="${HKU_LAB_GUI_CONFIG:-$PRIVATE_DIR/connection.env}"
RUNTIME_PATH="$PRIVATE_DIR/runtime.json"
SESSION_NAME="${HKU_LAB_GUI_TMUX_SESSION:-labcanvas-hku-lab-gui}"
TUNNEL_PORT="${HKU_LAB_GUI_TUNNEL_PORT:-15900}"
NOVNC_PORT="${HKU_LAB_GUI_NOVNC_PORT:-6142}"
NOVNC_WEB="${HKU_LAB_GUI_NOVNC_WEB:-/usr/share/novnc}"

load_config() {
  if [[ ! -f "$CONFIG_PATH" ]]; then
    printf 'Missing private host config: %s\n' "$CONFIG_PATH" >&2
    exit 1
  fi
  # shellcheck disable=SC1090
  source "$CONFIG_PATH"
  : "${HOST:?HOST is required in the private config}"
  : "${USER:?USER is required in the private config}"
  SSH_TARGET="$USER@$HOST"
  URL="http://127.0.0.1:${NOVNC_PORT}/vnc.html?host=127.0.0.1&port=${NOVNC_PORT}&autoconnect=1&resize=scale"
}

port_is_listening() {
  ss -ltnH | awk -v port=":$1" '$4 ~ port "$" { found=1 } END { exit !found }'
}

wait_for_port() {
  local port="$1" deadline=$((SECONDS + 15))
  until port_is_listening "$port"; do
    if (( SECONDS >= deadline )); then
      printf 'Timed out waiting for localhost port %s.\n' "$port" >&2
      return 1
    fi
    sleep 0.25
  done
}

write_runtime() {
  install -d -m 700 "$PRIVATE_DIR"
  local temporary
  temporary="$(mktemp "$PRIVATE_DIR/runtime.XXXXXX")"
  jq -n \
    --arg host "$HOST" \
    --arg user "$USER" \
    --arg session "$SESSION_NAME" \
    --arg url "$URL" \
    --argjson tunnel_port "$TUNNEL_PORT" \
    --argjson novnc_port "$NOVNC_PORT" \
    '{host:$host,user:$user,tmux_session:$session,tunnel_port:$tunnel_port,novnc_port:$novnc_port,url:$url}' \
    > "$temporary"
  chmod 600 "$temporary"
  mv -f "$temporary" "$RUNTIME_PATH"
}

remote_start_clients() {
  local script encoded
  script='$ErrorActionPreference="SilentlyContinue"
if(-not (Get-Process WeChat -ErrorAction SilentlyContinue)){Start-ScheduledTask -TaskName "LabCanvas-WeChat"}
if(-not (Get-Process WXWork -ErrorAction SilentlyContinue)){Start-ScheduledTask -TaskName "LabCanvas-WeCom"}'
  encoded="$(printf '%s' "$script" | iconv -f UTF-8 -t UTF-16LE | base64 -w0)"
  ssh -o BatchMode=yes -o ConnectTimeout=8 "$SSH_TARGET" \
    "powershell -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand $encoded" \
    >/dev/null
}

start_stack() {
  ssh -o BatchMode=yes -o ConnectTimeout=8 "$SSH_TARGET" exit
  remote_start_clients

  if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    if port_is_listening "$TUNNEL_PORT" && port_is_listening "$NOVNC_PORT"; then
      write_runtime
      printf 'Reusing %s\n%s\n' "$SESSION_NAME" "$URL"
      return
    fi
    tmux kill-session -t "$SESSION_NAME"
  fi
  if port_is_listening "$TUNNEL_PORT" || port_is_listening "$NOVNC_PORT"; then
    printf 'Refusing to replace non-owned listener on port %s or %s.\n' \
      "$TUNNEL_PORT" "$NOVNC_PORT" >&2
    exit 1
  fi
  if [[ ! -d "$NOVNC_WEB" ]]; then
    printf 'noVNC web root not found: %s\n' "$NOVNC_WEB" >&2
    exit 1
  fi

  tmux new-session -d -s "$SESSION_NAME" -n tunnel \
    "exec ssh -o BatchMode=yes -o ServerAliveInterval=20 -o ServerAliveCountMax=3 -N -L 127.0.0.1:${TUNNEL_PORT}:127.0.0.1:5900 '$SSH_TARGET'"
  wait_for_port "$TUNNEL_PORT"
  tmux new-window -t "$SESSION_NAME" -n novnc \
    "exec websockify --web='$NOVNC_WEB' 127.0.0.1:${NOVNC_PORT} 127.0.0.1:${TUNNEL_PORT}"
  wait_for_port "$NOVNC_PORT"
  write_runtime
  printf 'Started %s\n%s\n' "$SESSION_NAME" "$URL"
}

status_stack() {
  local running=false tunnel=false novnc=false
  tmux has-session -t "$SESSION_NAME" 2>/dev/null && running=true
  port_is_listening "$TUNNEL_PORT" && tunnel=true
  port_is_listening "$NOVNC_PORT" && novnc=true
  jq -n \
    --argjson running "$running" \
    --argjson tunnel "$tunnel" \
    --argjson novnc "$novnc" \
    --arg session "$SESSION_NAME" \
    --arg url "$URL" \
    '{ok:($running and $tunnel and $novnc),tmux_session:$session,tunnel_listening:$tunnel,novnc_listening:$novnc,url:$url}'
}

stop_stack() {
  if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    tmux kill-session -t "$SESSION_NAME"
  fi
  rm -f "$RUNTIME_PATH"
  printf 'Stopped %s\n' "$SESSION_NAME"
}

open_stack() {
  start_stack
  nohup firefox --new-tab "$URL" >/dev/null 2>&1 &
  disown || true
  printf 'Opened %s\n' "$URL"
}

load_config
case "${1:-status}" in
  start) start_stack ;;
  status) status_stack ;;
  stop) stop_stack ;;
  open) open_stack ;;
  url) printf '%s\n' "$URL" ;;
  *) printf 'usage: %s start|status|stop|open|url\n' "$0" >&2; exit 2 ;;
esac
