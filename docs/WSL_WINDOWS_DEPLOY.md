# Windows and WSL WeChat Automation Notes

This runbook documents the selective merge from:

- PR #1 `wechat-claude-backend-wsl` by ChutianWong, with the Claude backend commit authored by Haitao-Nie.
- PR #2 `windows-codex` by ChutianWong.
- Fork branch `Haitao-Nie/AgInTi-LabCanvas:wechat-claude-backend-wsl`.

The Ubuntu path remains the default. Do not replace the current WeChat router,
queue, media resolver, artifact delivery, or Codex session registry when adding
Windows/WSL support.

## Supported Topology

Run the automation inside WSL2 Ubuntu. The official Linux WeChat client, Xvfb,
x11vnc, noVNC, decrypt refresh loop, direct monitors, media sync, and worker all
remain Linux processes. Windows is only the host desktop and browser.

The repository may live on `/mnt/c/...`, but WeChat profile data and decrypted
DB output should stay under the WSL ext4 filesystem for speed.

## Backend Selection

Codex is still default:

```json
{
  "agent_backend": "codex"
}
```

Claude Code is opt-in per direct monitor config or by supervisor environment:

```json
{
  "agent_backend": "claude",
  "claude": {
    "model": "",
    "permission_mode": "bypassPermissions",
    "timeout_seconds": 60
  }
}
```

For one supervisor run:

```bash
WECHAT_AGENT_BACKEND=claude labcanvas wechat hold restart
```

The backend adapter preserves the current `run_codex_session` call shape for
tests and existing scripts. For Claude, prompts are passed on stdin to avoid
Windows command-line length limits. Read-only route/fast turns hard-block
mutating Claude tools; worker turns are only writable when the chat/task opts
into the Claude backend.

## WSL Display Fixes

Shell scripts are forced to LF through `.gitattributes`, preventing CRLF bash
failures after Windows checkouts. The virtual desktop launchers unset
`WAYLAND_DISPLAY`, and the WeChat launcher sets `QT_QPA_PLATFORM=xcb`, so x11vnc
and WeChat attach to the Xvfb display instead of escaping into WSLg Wayland.

Start the desktop:

```bash
agentic_tools/wechat_gui_agent/scripts/wechat_virtual_desktop.sh
```

Open the printed noVNC URL in a Windows or WSL browser, scan the QR code, and
confirm login on the phone if needed.

## Validation

Use these checks before enabling a Windows/WSL machine:

```bash
PYTHONPATH=src python -m agenticapp wechat doctor --json
npm test
```

`doctor` checks `codex` by default and checks `claude` only when
`agent_backend=claude` or `WECHAT_AGENT_BACKEND=claude` is active. `npm test`
uses `scripts/run-python-tests.js` so `PYTHONPATH` works on Windows path
separators.
