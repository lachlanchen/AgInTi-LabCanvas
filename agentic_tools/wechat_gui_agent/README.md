# WeChat GUI Agent

This tool automates the native Linux WeChat client through a clean Xvfb/noVNC
desktop. It uses visible GUI control instead of private protocol hooks, records
evidence screenshots, and mirrors send/read events into a local SQLite database.

## Start The Desktop

Use the wrapper for the shared WeChat desktop:

```bash
agentic_tools/wechat_gui_agent/scripts/wechat_virtual_desktop.sh
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
