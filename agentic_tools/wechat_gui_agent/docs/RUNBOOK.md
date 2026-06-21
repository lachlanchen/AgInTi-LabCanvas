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
The desktop launcher disables X11 blanking and disables DPMS when available. If
noVNC looks idle or blank but WeChat should stay logged in, refresh the
keep-awake daemon without restarting WeChat:

```bash
labcanvas wechat desktop keep-awake
```

## 2. Prepare Targets

Create an ignored plan under `.private/`:

```json
{
  "message": "test",
  "targets": [
    {
      "name": "example group",
      "query": "example",
      "expected_title": "example group",
      "result_click": [180, 337],
      "fallback_clicks": [[165, 100], [165, 170]]
    }
  ]
}
```

Use `query` for the search text and `result_click` for the row offset inside the
WeChat window after the search result appears. If a chat is already visible in
the left list, use `open_click` instead. Use `fallback_clicks` for alternate
search result rows; the sender OCR-checks the opened title after every attempt.

For multi-group monitors, confirm state and routing guards:

```bash
labcanvas wechat health --json
```

The fast monitor is tuned for immediate responses: idle polling is 0.8 seconds,
catch-up polling is 0.1 seconds when rows are waiting, the decrypt refresh loop
runs every 1 second, and the fast agent should use `gpt-5.5` with low reasoning.
Polling itself is local DB/file work; it only spends Codex tokens when a new
message needs a route decision or reply.

The worker loop chooses its effort separately. It uses low for simple follow-up
tasks, medium for paper/PDF/search/research/figure tasks, and high for CAD, PCB,
Blender/OpenSCAD, install, GitHub, ordering, and other execution-heavy tasks. A
clear failure or timeout escalates once to the next effort level.

Each group keeps two reusable Codex sessions by default: `fast` for immediate
router replies and `worker` for backend work. The ignored registry is
`.private/codex_sessions/sessions.local.json`. Session keys are hash-scoped to
the exact chat title; if status shows `legacy_key: true`, back up that registry
and restart the monitor so mixed pre-fix context cannot be resumed. Disable
reuse for debugging with:

```bash
WECHAT_CODEX_REUSE_SESSIONS=0 labcanvas wechat hold restart
```

This reloads monitor, worker, and media-sync windows while preserving the
WeChat desktop. Use `labcanvas wechat hold restart-all` only for a deliberate
GUI restart that may require phone confirmation. If the supervisor is not
running, reload fails closed instead of launching WeChat.

When a paper/download site needs login, CAPTCHA, consent, or manual file-save
confirmation, open a browser in the same virtual desktop:

```bash
labcanvas wechat browser-assist --url "https://example.com/download" --json
```

Use the printed noVNC URL to complete the manual step. The worker should wait
for approval before continuing the task.

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

## 7. External Decrypt Backend

Probe the optional second receive path:

```bash
labcanvas wechat backend probe --json
labcanvas wechat backend decrypt --incremental
```

For local Web UI/SSE inspection, bind the imported upstream monitor to localhost:

```bash
labcanvas wechat backend monitor-web --port 5679
labcanvas wechat backend api-history --port 5679 --json
```

Only run `labcanvas wechat backend find-keys` when keys are missing; it reads the
running WeChat process memory and requires root or `CAP_SYS_PTRACE`.

The persistent supervisor uses this same wrapper from its decrypt refresh pane.
It defaults to `WECHAT_DECRYPT_REFRESH_MODE=incremental` and
`WECHAT_DECRYPT_REFRESH_SMART=1`, so it avoids full decrypt passes while the
source DB/WAL files are unchanged. Use `labcanvas wechat health --json` to check
both external backend readiness and per-group catch-up.

## 8. Group Creation

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
- If OCR is empty, install the needed Tesseract language pack, increase
  `WECHAT_INITIAL_TITLE_WAIT`, or inspect the saved full-page OCR screenshot.
- If a worker result cannot be sent, inspect `send_failed` tasks in
  `.private/wechat_task_queue.jsonl`; the worker records the error instead of
  retrying forever.
- If a task is waiting for approval, use `labcanvas wechat approve` or
  `labcanvas wechat reject`; without a task id the newest waiting task is used.
- If the external decrypt backend reports missing keys, rerun key extraction only
  under explicit local authorization, then run `backend decrypt --incremental`.
