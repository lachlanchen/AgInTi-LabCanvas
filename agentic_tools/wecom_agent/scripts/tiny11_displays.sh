#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
SESSION=labcanvas-tiny11-displays
PYTHON="${TINY11_DISPLAYS_PYTHON:-$HOME/.local/share/labcanvas/tiny11-displays-venv/bin/python}"
OUT="$ROOT/output/tiny11-dual-monitor"

ensure_window() {
    local name="$1" command="$2"
    if tmux list-windows -t "$SESSION" -F '#{window_name}' 2>/dev/null | grep -qx "$name"; then return; fi
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        tmux new-window -d -t "$SESSION" -n "$name" "$command"
    else
        tmux new-session -d -s "$SESSION" -n "$name" "$command"
    fi
}

case "${1:-status}" in
    supervise)
        trap 'bash "$0" stop; exit 0' TERM INT
        while true; do
            count="$(tmux list-windows -t "$SESSION" -F '#{window_name}' 2>/dev/null | grep -Ec '^(tunnel|wecom|wechat|views)$' || true)"
            if [[ "$count" != 4 ]]; then bash "$0" start || true; fi
            sleep 30 & wait $! || true
        done
        ;;
    start)
        mkdir -p "$OUT"
        # Never start/reboot another VM. The existing SSH endpoint must be ready.
        ssh -p 2290 -o BatchMode=yes -o ConnectTimeout=8 lachlan@127.0.0.1 whoami >/dev/null
        ensure_window tunnel 'exec ssh -N -p 2290 -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -L 127.0.0.1:15943:127.0.0.1:5900 lachlan@127.0.0.1'
        "$PYTHON" -c 'import socket,time
for n in range(30):
 try:
  with socket.create_connection(("127.0.0.1",15943),1) as s:
   if s.recv(12).startswith(b"RFB "): break
 except OSError: pass
 time.sleep(1)
else: raise SystemExit("Guest VNC tunnel is not ready")'
        for app in wecom wechat; do
            x=0; port=5944
            if [[ "$app" == wechat ]]; then x=1280; port=5945; fi
            ensure_window "$app" "exec x11vnc -reflect 127.0.0.1:15943 -clip 1280x800+$x+0 -rfbport $port -localhost -no6 -nopw -forever -shared -o '$OUT/$app-reflect.log'"
        done
        ensure_window views "exec '$PYTHON' '$ROOT/agentic_tools/wecom_agent/scripts/tiny11_display_views.py'"
        ;;
    stop)
        tmux kill-session -t "$SESSION" 2>/dev/null || true
        ;;
    status)
        tmux list-windows -t "$SESSION" -F '#{window_name}: #{pane_current_command}'
        curl -fsS -o /dev/null http://127.0.0.1:6144/wecom
        printf 'WeCom: http://127.0.0.1:6144/wecom\nWeChat: http://127.0.0.1:6144/wechat\n'
        ;;
    *) printf 'Usage: %s start|stop|status|supervise\n' "$0" >&2; exit 2 ;;
esac
