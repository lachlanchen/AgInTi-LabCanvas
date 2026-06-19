# WeChat GUI Agent Runbook

This workflow controls the native Linux WeChat client through an isolated
virtual desktop. Use it for explicit, small tasks where a human can inspect the
target before sending.

## 1. Launch

```bash
agentic_tools/wechat_gui_agent/scripts/wechat_virtual_desktop.sh
```

Open the printed noVNC URL. If WeChat shows a QR code, approve login on the
phone. Keep the browser visible while automating so screenshots can be checked.

For normal long-running operation, start the complete stack instead:

```bash
labcanvas wechat stack start --web-port 19474
```

This starts the isolated WeChat desktop, the direct monitor, the worker, media
sync, and the LabCanvas web panel in tmux-managed sessions.

## 2. Prepare Targets

Create an ignored plan under `.private/`:

```json
{
  "message": "test",
  "targets": [
    {"name": "example group", "query": "example", "result_click": [180, 337]}
  ]
}
```

Use `query` for the search text and `result_click` for the row offset inside the
WeChat window after the search result appears. If a chat is already visible in
the left list, use `open_click` instead.

## 3. Verify Before Sending

Open targets and record evidence without composing:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_gui_send.py \
  --display :97 \
  --targets-file agentic_tools/wechat_gui_agent/.private/test-targets.local.json
```

Inspect `*-opened.png` under the output directory. The chat title in the right
pane must match the intended target.

## 4. Send

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_gui_send.py \
  --display :97 \
  --targets-file agentic_tools/wechat_gui_agent/.private/test-targets.local.json \
  --send
```

Each send writes a `send_manifest.json`, screenshots, an `events` row, and a
searchable `messages` row.

## 5. Capture Reads

Open the chat, then capture the visible screen:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_mirror.py capture-read \
  --display :97 \
  --chat "example group"
```

This stores a screenshot and a `screen_ocr` message row. OCR is page-level and
may include sidebar text, so verify important reads from the screenshot.

## 6. Review The Database

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_mirror.py list --limit 20
python3 agentic_tools/wechat_gui_agent/scripts/wechat_mirror.py list-messages --limit 20
python3 agentic_tools/wechat_gui_agent/scripts/wechat_mirror.py export-json \
  --output agentic_tools/wechat_gui_agent/.private/wechat_mirror_export.json
```

## 7. Group Creation

Open the picker first:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_group_create.py \
  --display :97 \
  --plan agentic_tools/wechat_gui_agent/.private/group-create.local.json
```

Only run with `--create` after member checkboxes and the Finish button are
visually confirmed. Creating a group is a real WeChat action and notifies users.

## Troubleshooting

- If noVNC disappears, check whether the WeChat process exited; rerun
  `wechat_virtual_desktop.sh` to relaunch it on display `:97`.
- If RDP freezes, keep automation isolated on Xvfb and avoid controlling the
  physical desktop display.
- If search opens the wrong row, replace `result_click` with a verified
  `open_click` for the visible chat list or update the offset from a screenshot.
- If OCR is empty, install the needed Tesseract language pack or rely on the
  saved screenshot.
- If a task is waiting for approval, use `labcanvas wechat approve` or
  `labcanvas wechat reject`; without a task id the newest waiting task is used.
