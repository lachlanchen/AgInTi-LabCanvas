# HKU Lab Windows WeChat/WeCom noVNC Handoff

This setup reuses the existing RealVNC Server on the Windows host. It does not
install a second VNC server or expose a new remote port. A localhost SSH tunnel
terminates on the AgenticApp workstation and one local noVNC bridge presents
the active Windows console desktop.

## Runtime Contract

- Remote host identity: private config under
  `agentic_tools/wechat_gui_agent/.private/remote_hosts/hku-lab-lachlan/`
- Remote VNC endpoint: `127.0.0.1:5900` through SSH only
- Local SSH tunnel: `127.0.0.1:15900`
- Local noVNC: `127.0.0.1:6142`
- tmux owner: `labcanvas-hku-lab-gui`
- noVNC client: full `vnc.html` with `resize=scale`

The Windows host has two interactive-at-logon tasks:

- `LabCanvas-WeChat`
- `LabCanvas-WeCom`

They launch the installed clients into the already logged-in console session.
The local wrapper also starts a missing client before opening noVNC.

## Commands

```bash
agentic_tools/wechat_gui_agent/scripts/hku_lab_windows_gui.sh start
agentic_tools/wechat_gui_agent/scripts/hku_lab_windows_gui.sh status
agentic_tools/wechat_gui_agent/scripts/hku_lab_windows_gui.sh open
agentic_tools/wechat_gui_agent/scripts/hku_lab_windows_gui.sh stop
```

The ignored private `runtime.json` records the current URL and owned tmux
session. `stop` terminates only this project's tunnel/noVNC session; it does not
stop the Windows clients or RealVNC service.

## Verification

```bash
curl -fsS -o /dev/null http://127.0.0.1:6142/vnc.html
timeout 3 nc 127.0.0.1 15900
tmux list-windows -t labcanvas-hku-lab-gui
```

The VNC protocol probe should begin with `RFB`. Keep credentials and VNC login
state out of git, logs, screenshots, and this handoff.
