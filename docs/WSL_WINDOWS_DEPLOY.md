# Running the WeChat Automation on Windows (via WSL2)

The WeChat chatops stack is Linux-only: it drives the **native Linux WeChat
client** through an X virtual desktop and reads messages from WeChat's encrypted
SQLite database. None of that runs natively on Windows, so on Windows the
supported path is **WSL2 (Ubuntu)**. This runbook captures the full bring-up.

> Secrets are never committed. The DB encryption keys, account wxids, message
> table names, and any tokens live only under the gitignored
> `agentic_tools/wechat_gui_agent/.private/`. Placeholders below look like
> `<self-wxid>`.

## 0. Prerequisites on Windows

- WSL2 with an Ubuntu distro (`wsl --install -d Ubuntu`). Verified on Ubuntu
  24.04, systemd enabled.
- Run installs as root to avoid sudo prompts: `wsl -d Ubuntu -u root -- bash -lc '...'`.
- The repo can live on `/mnt/c/...`; WeChat itself stores its data in the Linux
  home (`~/xwechat_files/...`) on ext4, which is what matters for performance.

## 1. System dependencies (apt, as root)

```bash
apt-get update
apt-get install -y \
  python3-pip python3-venv python3-zstandard \
  xvfb x11vnc novnc websockify x11-utils \
  xdotool xclip imagemagick \
  tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-chi-tra \
  sqlite3 libpulse0
```

- `tesseract-ocr-chi-sim/chi-tra` are required — WeChat UI/OCR is Chinese.
- `libpulse0` is needed by the WeChat binary (`libpulse.so.0`).
- `python3-zstandard` lets the monitor decode compressed message rows.

## 2. Install the native Linux WeChat client

Official Tencent build (Linux support since Nov 2024):

```bash
cd /tmp
wget 'https://dldir1v6.qq.com/weixin/Universal/Linux/WeChatLinux_x86_64.deb' -O wechat.deb
apt-get install -y /tmp/wechat.deb     # installs /opt/wechat + /usr/bin/wechat symlink
```

## 3. AI backend: Claude Code (optionally via reclaude)

This fork makes the chatops AI backend pluggable (Codex *or* Claude Code) — see
[agent_backend.py](../agentic_tools/wechat_gui_agent/scripts/agent_backend.py).
Select it with `agent_backend` in the per-chat JSON, or `WECHAT_AGENT_BACKEND`
for the worker pane.

```bash
npm install -g @anthropic-ai/claude-code      # provides /usr/local/bin/claude
```

If you use **reclaude** (a relay that proxies Claude Code through a local
daemon):

```bash
curl -fsSL https://reclaude.ai/install.sh | bash
exec bash                 # reload PATH (installer writes ~/.bashrc)
reclaude login            # interactive browser device-flow
reclaude status           # confirm daemon_running + gateway_url populated
```

For head-less use the bot shells out to `claude -p`. Ensure the reclaude daemon
is running and, if required, export `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN`
(from `reclaude status` / config) in the supervisor env so `claude -p` routes
through the gateway without an interactive session.

## 4. Bring up the virtual desktop and log into WeChat

```bash
agentic_tools/wechat_gui_agent/scripts/wechat_virtual_desktop.sh
```

Then open the printed noVNC URL (`http://127.0.0.1:6107/vnc_lite.html?...`) in a
**Windows** browser (WSL2 forwards localhost). Scan the QR with your phone and
confirm. The green **Log In** button can be clicked headlessly:

```bash
DISPLAY=:97 XAUTHORITY= xdotool mousemove <x> <y> click 1
```

Sanity screenshot at any time:

```bash
DISPLAY=:97 XAUTHORITY= import -window root /tmp/wechat_screen.png
```

### WSL gotchas (already patched in the scripts)

- **CRLF line endings**: a Windows checkout gives `*.sh` CRLF, which breaks bash
  (`set: pipefail: invalid option name`). Fixed via `.gitattributes`
  (`*.sh text eol=lf`); convert an existing tree with
  `git ls-files '*.sh' -z | xargs -0 sed -i 's/\r$//'`.
- **WSLg/Wayland**: x11vnc and the Qt-based WeChat will grab the host Wayland
  display and fail/escape the Xvfb. The launch scripts now prefix them with
  `env -u WAYLAND_DISPLAY` (and `QT_QPA_PLATFORM=xcb` for WeChat).
- The `/tmp/.X11-unix` permission warning from Xvfb is harmless; the display is
  still reachable (`xdpyinfo` returns OK) via the abstract socket.

## 5. Decrypt the WeChat database

The monitor reads decrypted copies at
`.private/wechat_decrypt/decrypted/message/message_0.db` and
`.../contact/contact.db`. Produce them with an open-source WeChat 4.x decryptor
(extracts the SQLCipher key from the **running** WeChat process memory):

```bash
cd agentic_tools/wechat_gui_agent/.private
git clone --depth 1 https://github.com/ylytdeng/wechat-decrypt external/wechat-decrypt
python3 -m venv wechat_decrypt/.venv
wechat_decrypt/.venv/bin/pip install pycryptodome zstandard tqdm
```

Create `external/wechat-decrypt/config.json` with **absolute** paths so output
lands where the monitor looks:

```json
{
  "db_dir": "/home/<user>/xwechat_files/<wxid_dir>/db_storage",
  "keys_file": "<repo>/agentic_tools/wechat_gui_agent/.private/wechat_decrypt/all_keys.json",
  "decrypted_dir": "<repo>/agentic_tools/wechat_gui_agent/.private/wechat_decrypt/decrypted",
  "wechat_process": "wechat"
}
```

Then (WeChat must be logged in and running so the key is in memory):

```bash
cd external/wechat-decrypt
export WECHAT_DECRYPT_NONINTERACTIVE=1
sudo ../../wechat_decrypt/.venv/bin/python find_all_keys.py   # key from memory -> all_keys.json
../../wechat_decrypt/.venv/bin/python decrypt_db.py           # -> decrypted/*
```

> Keys are per-login session. If WeChat restarts, re-run `find_all_keys.py`.
> The supervisor's `wechat_decrypt_refresh_loop.sh` only re-runs `decrypt_db.py`.

## 6. Discover the per-chat config values

From the decrypted DBs, find the identifiers for the chat you want to monitor:

```bash
D=.private/wechat_decrypt/decrypted
sqlite3 "$D/message/message_0.db" ".tables"          # Msg_<md5(peer-or-room-id)>
sqlite3 "$D/message/message_0.db" "SELECT rowid,user_name FROM Name2Id;"
sqlite3 "$D/contact/contact.db" \
  "SELECT username,nick_name,remark FROM contact;"   # map wxid -> display name
```

- The message table is `Msg_` + `md5(<chat user_name or chatroom id>)`
  (verify: `printf '<id>' | md5sum`).
- `self_wxid` is the account whose `db_storage` dir you decrypted.

Write these into `.private/lazy-research-direct-chatops.local.json`
(`chat_name`, `chatroom_id`, `message_table`, `self_wxid`, `agent_backend`,
`send_target`, …). See [WECHAT_AUTOMATION.md](WECHAT_AUTOMATION.md) for the full
schema.

## 7. Supervisor environment + start the stack

`.private/wechat_supervisor.local.env` (gitignored) is auto-sourced:

```bash
WECHAT_AGENT_BACKEND=claude
WECHAT_DIRECT_CONFIGS=<repo>/agentic_tools/wechat_gui_agent/.private/lazy-research-direct-chatops.local.json
# ANTHROPIC_BASE_URL=...   # if routing claude through reclaude headlessly
# ANTHROPIC_AUTH_TOKEN=...
```

Validate, then run:

```bash
WECHAT_AGENT_BACKEND=claude PYTHONPATH=src python3 -m agenticapp wechat doctor --json
labcanvas wechat stack start --web-port 19474   # or wechat_supervisor_tmux.sh start
labcanvas wechat status
```

The supervisor runs panes for: virtual desktop, decrypt-refresh loop, one direct
monitor per config (`--send --no-decrypt`), the worker, and media sync — each
wrapped in a restart loop.

## 8. Verify end-to-end

Send a message to the monitored chat from another device/account; the monitor
mirrors it, asks the configured AI backend for `CHAT/ACK/TASK/NO_REPLY`, and
sends the reply through the GUI sender (OCR-verifies the chat title first).

```bash
tail -f output/wechat_gui_agent/<date>/supervisor-direct-chatops-*.log
```

## Performance note

`decrypt_db.py` re-decrypts every DB each refresh. If the decrypted dir is on
`/mnt/c` (9p) this is slow; point `decrypted_dir` at an ext4 path (e.g. under
`~`) and symlink `.private/wechat_decrypt/decrypted` to it, and/or limit
decryption to the message DB.
