# Remote Virtual Desktop and noVNC Runbook

This records the clean virtual desktop pattern used for LabVIEW Community on the
remote Ubuntu machine. The same approach is reusable for other GUI-heavy tools
such as KiCad, JLCEDA, FreeCAD, Blender GUI, or vendor configuration apps.

## Working LabVIEW Layout

| Role | Value |
| --- | --- |
| X display | `:98` |
| Xvfb screen | `1920x1080x24` |
| LabVIEW binary | `/usr/local/natinst/LabVIEW-2026-64/labview` |
| VNC bridge | `x11vnc -display :98 -localhost -nopw -forever -shared -rfbport 5908` |
| Browser bridge | `websockify --web=/usr/share/novnc 127.0.0.1:6099 127.0.0.1:5908` |
| noVNC URL | `http://127.0.0.1:6099/vnc_lite.html?host=127.0.0.1&port=6099&autoconnect=1&resize=remote` |
| Logs | `output/labview_local_server/YYYY-MM-DD/` |

This worked because LabVIEW needed a predictable 24-bit X display. The existing
remote desktop on `:10` used a 32-bit root-window depth and triggered X11
`BadMatch` errors.

## Start LabVIEW Desktop

Repo-specific LabVIEW launcher:

```bash
agentic_tools/labview_mcp_agent/scripts/start_labview_local_server.sh
```

Generic reusable launcher:

```bash
agentic_tools/virtual_desktop/launch_virtual_desktop.sh \
  --name labview \
  --display :98 \
  --screen 1920x1080x24 \
  --vnc-port 5908 \
  --novnc-port 6099 \
  --app-match /usr/local/natinst/LabVIEW-2026-64/labview \
  --open-browser \
  -- /usr/local/natinst/LabVIEW-2026-64/labview
```

Keep `x11vnc` and noVNC bound to `127.0.0.1`. If access from another machine is
needed, prefer SSH tunneling over opening the VNC port publicly.

## Verify State

```bash
DISPLAY=:98 XAUTHORITY= xdpyinfo | rg 'dimensions|depth of root window'
DISPLAY=:98 XAUTHORITY= xwininfo -root -tree | rg 'LabVIEW|Activation|Context Help'
ss -ltnp | rg ':5908|:6099|:3363|:23520|:36987'
```

Expected LabVIEW ports:

- `23520`: NI activation callback while Community activation is pending.
- `3363`: LabVIEW VI Server after preferences are written and LabVIEW is ready.
- `36987`: LabVIEW MCP VI HTTP endpoint after the MCP VI is running.

## Stop Camera Without Closing Desktop

When a camera preview is running inside or beside LabVIEW, stop only the camera
processes:

```bash
ps -eo pid,ppid,stat,cmd | rg -i 'labview|ffplay|camera|v4l|/dev/video|MVCamCtrlDemo'
fuser -v /dev/video* 2>/dev/null || true
kill -TERM <ffplay-pid> <camera-sample-pid>
fuser -v /dev/video* 2>/dev/null || true
```

On 2026-06-15, the processes stopped were:

- `ffplay ... -f v4l2 ... /dev/video0`
- `labview64 ... MVCamCtrlDemo/Main.vi`

The main LabVIEW IDE, Xvfb, x11vnc, websockify, and browser noVNC viewer were
left running.

## General Pattern

1. Pick a high, unused display and ports, for example `:98`, VNC `5908`, noVNC
   `6099`.
2. Start Xvfb with explicit 24-bit depth: `Xvfb :98 -screen 0 1920x1080x24 -ac`.
3. Launch the app with `DISPLAY=:98 XAUTHORITY=`.
4. Start `x11vnc` with `-localhost -forever -shared`.
5. Start `websockify` with noVNC web root.
6. Open noVNC through a browser app window or SSH tunnel.
7. Stop only task-specific child processes when cleaning up cameras or test
   programs; keep the desktop service up if the GUI session is still useful.

## Troubleshooting

- If the display socket exists but `xdpyinfo` fails, remove stale
  `/tmp/.X11-unix/XN` and `/tmp/.XN-lock` only when no matching Xvfb process is
  running.
- If noVNC connects but does not repaint, check `x11vnc` logs and try
  reconnecting the web viewer.
- If a camera cannot open, run `fuser -v /dev/video*` and stop stale preview
  processes.
- If LabVIEW opens only an activation dialog, finish official NI activation
  before expecting VI Server or LabVIEWCLI automation to work.
