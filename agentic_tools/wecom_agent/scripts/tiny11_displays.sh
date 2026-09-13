#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
SESSION=labcanvas-tiny11-displays
PYTHON="${TINY11_DISPLAYS_PYTHON:-$HOME/.local/share/labcanvas/tiny11-displays-venv/bin/python}"
OUT="$ROOT/output/tiny11-dual-monitor"

window_alive() {
    [[ "$(tmux list-panes -t "$SESSION:$1" -F '#{pane_dead}' 2>/dev/null)" == 0 ]]
}

ensure_window() {
    local name="$1" command="$2"
    if window_alive "$name"; then return; fi
    # remain-on-exit can retain a dead pane after SSH or a reflector fails.
    if [[ "$(tmux list-panes -t "$SESSION:$name" -F '#{pane_dead}' 2>/dev/null)" == 1 ]]; then
        tmux respawn-window -t "$SESSION:$name" "$command"
        return
    fi
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        tmux new-window -d -t "$SESSION" -n "$name" "$command"
    else
        tmux new-session -d -s "$SESSION" -n "$name" "$command"
    fi
}

retire_legacy_wecom_reflector() {
    local pid command binary
    local -a args
    pid="$(tmux list-panes -t "$SESSION:wecom" -F '#{pane_pid}' 2>/dev/null)" || return 0
    if window_alive wecom; then
        mapfile -d '' -t args < "/proc/$pid/cmdline"
        binary="${args[0]:-}"
        command=" ${args[*]} "
        if [[ "${binary##*/}" != x11vnc || "$command" != *" -reflect 127.0.0.1:15943 "* || "$command" != *" -rfbport 5944 "* ]]; then
            printf 'Unexpected process in legacy WeCom pane; preserving it.\n' >&2
            return 1
        fi
    fi
    tmux kill-window -t "$SESSION:wecom"
}

case "${1:-status}" in
    supervise)
        trap 'bash "$0" stop; exit 0' TERM INT
        while true; do
            for name in tunnel wechat views; do
                if ! window_alive "$name"; then bash "$0" start || true; break; fi
            done
            sleep 30 & wait $! || true
        done
        ;;
    start)
        mkdir -p "$OUT"
        retire_legacy_wecom_reflector
        # Serve the QEMU console even while Windows SSH/secondary VNC recovers.
        # The web relay returns 503 and retries if an individual display is down.
        ensure_window views "exec '$PYTHON' '$ROOT/agentic_tools/wecom_agent/scripts/tiny11_display_views.py'"
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
        ensure_window wechat "exec x11vnc -reflect 127.0.0.1:15943 -clip 1280x800+1280+0 -rfbport 5945 -localhost -no6 -nopw -forever -shared -o '$OUT/wechat-reflect.log'"
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
