# WeChat GUI Agent

This tool automates the native Linux WeChat client through a clean Xvfb/noVNC
desktop. It uses visible GUI control instead of private protocol hooks, records
evidence screenshots, and mirrors send/read events into a local SQLite database.

## Start The Desktop

Use the wrapper for the shared WeChat desktop:

```bash
agentic_tools/wechat_gui_agent/scripts/wechat_virtual_desktop.sh
# or, through the installed/source LabCanvas CLI:
labcanvas wechat desktop start
```

Manual launch:

```bash
agentic_tools/virtual_desktop/launch_virtual_desktop.sh \
  --name wechat \
  --display :97 \
  --screen 1920x1080x24 \
  --vnc-port 5917 \
  --novnc-port 6107 \
  --app-match /opt/wechat/wechat \
  -- /usr/bin/wechat
```

Open:

```text
http://127.0.0.1:6107/vnc_lite.html?host=127.0.0.1&port=6107&autoconnect=1&resize=remote
```

The Linux WeChat client is single-instance. If it is already running on another
desktop, close that instance before launching it on the virtual display.

## Persistent ChatOps

Create ignored private configs first:

```bash
labcanvas wechat init-config --chat "example group"
```

Fill the direct config under `.private/` with the decrypted message table and
self account ID. Then start the full supervisor:

```bash
labcanvas wechat hold start
labcanvas wechat stack start --web-port 19474
labcanvas wechat status
tmux attach -t labcanvas-wechat
```

The supervisor keeps four panes alive: virtual desktop, fast direct monitor,
worker queue, and media sync. Monitor/worker/media panes restart automatically
if they exit. Incoming mentions can get an immediate ACK while longer work is
queued for `wechat_task_worker.py`, which can send a final message plus
PDFs/images/files back through the official WeChat GUI.

The direct monitor uses recent full chat history, not just the newest polling
batch. A bare mention can therefore refer to the previous message, and queued
tasks include recent synced file paths so requests like "summarize this PDF"
can resolve to the latest downloaded PDF.

Install a reusable launcher:

```bash
labcanvas wechat install-user-scripts
~/scripts/labcanvas-wechat-hold.sh start
~/scripts/create-labcanvas-wechat-tmux.sh
~/scripts/create-labcanvas-wechat-stack.sh
```

`stack start` keeps the WeChat supervisor and the LabCanvas browser control
panel alive together. The default web session is `labcanvas-web-wechat` on port
`19474`; if that port is busy, the web app uses the next free port and prints
the actual URL.

## Send Messages

Prepare an ignored target file under `.private/`:

```json
{
  "message": "test",
  "targets": [
    {"name": "example group", "query": "example", "result_click": [180, 337]}
  ]
}
```

Open targets without composing:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_gui_send.py \
  --display :97 \
  --targets-file agentic_tools/wechat_gui_agent/.private/test-targets.local.json
```

Compose without pressing Enter:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_gui_send.py \
  --display :97 \
  --targets-file agentic_tools/wechat_gui_agent/.private/test-targets.local.json \
  --compose-dry-run
```

Send only after screenshots confirm the right chat is open:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_gui_send.py \
  --display :97 \
  --targets-file agentic_tools/wechat_gui_agent/.private/test-targets.local.json \
  --send
```

The script uses `xclip` for Unicode text, `xdotool` for focus/click/keystrokes,
and ImageMagick `import` plus optional `tesseract` for evidence screenshots.
It records screenshots under `output/wechat_gui_agent/YYYY-MM-DD/`.

## Message Mirror

Initialize and inspect the ignored local database:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_mirror.py init
python3 agentic_tools/wechat_gui_agent/scripts/wechat_mirror.py list --limit 20
python3 agentic_tools/wechat_gui_agent/scripts/wechat_mirror.py list-messages --limit 20
```

Capture the current visible chat screen with OCR:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_mirror.py capture-read \
  --display :97 \
  --chat "example group"
```

Export a private JSON snapshot:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_mirror.py export-json \
  --output agentic_tools/wechat_gui_agent/.private/wechat_mirror_export.json
```

See `docs/MIRROR_SCHEMA.md` for the database layout.

## Direct Monitor And Worker

Run one fast direct pass:

```bash
labcanvas wechat monitor once --send
```

Start only the direct monitor:

```bash
labcanvas wechat monitor start
```

Queue slower backend work:

```bash
labcanvas wechat worker enqueue "Download the public PDF for <paper title>"
labcanvas wechat worker once --send
labcanvas wechat queue --json
```

Approve or cancel work that is waiting on a confirmation:

```bash
labcanvas wechat approve <task-id> --note "continue with the default option"
labcanvas wechat reject <task-id> --note "do not submit this action"
```

Send a manual message or attachment to the currently visible chat:

```bash
labcanvas wechat send --message "Bridge online."
labcanvas wechat send --file /absolute/path/to/report.pdf
```

Sync recent downloaded files/images into the private workspace:

```bash
labcanvas wechat media-sync --chat "example group" \
  --auto-source \
  --since-minutes 60
```

Synced files are stored under
`.private/downloads/<chat>/<wechat-profile>/<category>/` so images, PDFs, and
videos from different profiles do not collide.

## Group Creation

Group creation is intentionally gated. First open the picker and capture a
screenshot:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_group_create.py \
  --display :97 \
  --plan agentic_tools/wechat_gui_agent/.private/group-create.local.json
```

Only pass `--create` after the selected members and Finish button position are
verified, because WeChat notifies real accounts when a group is created.

See `docs/GITHUB_OPTIONS.md` for the GitHub automation options checked before
choosing the visible Linux GUI route.
See `docs/RUNBOOK.md` for the repeatable operator workflow.

## Guardrails

- It does not bypass WeChat login; approve the desktop login from the phone first.
- It sends only when `--send` is supplied.
- It targets the visible WeChat desktop, so keep noVNC open for human inspection.
- It stores private target files and mirror data under `.private/`, which is ignored.
- It is intended for small, explicit sends such as test messages, not bulk spam.
