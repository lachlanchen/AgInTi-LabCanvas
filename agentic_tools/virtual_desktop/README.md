# Virtual Desktop Launcher

`launch_virtual_desktop.sh` starts a clean, isolated X11 desktop for GUI tools
that do not behave well inside an existing remote desktop. It uses:

- `Xvfb` for a dedicated virtual display.
- `x11vnc` bound to localhost for VNC access.
- `websockify`/noVNC for browser access.
- Optional app launch on that display.

## LabVIEW Example

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

Open:

```text
http://127.0.0.1:6099/vnc_lite.html?host=127.0.0.1&port=6099&autoconnect=1&resize=remote
```

## Why This Pattern Worked

LabVIEW Community failed on the active TigerVNC desktop because that desktop used
a 32-bit root window depth and caused X11 `BadMatch` errors. A fresh Xvfb display
with a `1920x1080x24` screen gives LabVIEW a predictable 24-bit X display while
still allowing remote viewing through noVNC.

## Stop Camera Viewers

Stop camera preview processes without closing the LabVIEW IDE:

```bash
ps -eo pid,ppid,stat,cmd | rg -i 'labview|ffplay|camera|v4l|/dev/video|MVCamCtrlDemo'
kill -TERM <ffplay-pid> <camera-sample-pid>
fuser -v /dev/video* 2>/dev/null || true
```

In the June 2026 LabVIEW test, this stopped `ffplay` on `/dev/video0` and the
`labview64 ... MVCamCtrlDemo/Main.vi` camera sample while leaving the main
LabVIEW IDE and noVNC server running.

## General Use

Use this launcher for KiCad, JLCEDA, LabVIEW, Blender GUI, FreeCAD, or any GUI
app that needs a stable remote X11 display. Keep ports localhost-only unless you
intentionally add SSH tunneling or another authenticated access layer.
