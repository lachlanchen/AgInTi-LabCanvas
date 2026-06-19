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
batch. Prompt context labels the latest row and bot/self replies, so a bare
mention, repeated message, or fragment such as "same one" can refer to the
previous request without repeating the same answer. By default,
`coalesce_new_messages` makes a burst of incoming rows produce one reply to the
latest actionable turn while marking earlier actionable rows as `FOCUS`, so
EchoMind analyzes every sentence in the burst and research tasks include every
instruction. Queued tasks include recent synced file paths so requests like
"summarize this PDF" can resolve to the latest downloaded PDF.
WeChat quote/reply rows are decoded as `quote_reply`: the reply title is treated
as the current command and the referenced message is included as quoted context.

For low-latency chatops, the supervisor defaults to:

- `WECHAT_DIRECT_POLL_SECONDS=0.8` for idle direct DB polling.
- `WECHAT_DIRECT_CATCHUP_POLL_SECONDS=0.1` when rows are waiting.
- `WECHAT_DECRYPT_REFRESH_INTERVAL=1` for the shared decrypted cache refresh.
- `gpt-5.5` with `low` reasoning and a 60 second timeout for the fast agent.

To monitor multiple groups, create one ignored direct config per group and set
`WECHAT_DIRECT_CONFIGS` in `.private/wechat_supervisor.local.env`:

```bash
WECHAT_DIRECT_CONFIGS='/path/to/group-a-direct.json,/path/to/group-b-direct.json'
```

Each config should use a distinct `state_path`. Optional `send_target` values
let replies open the correct group before sending, instead of assuming the
visible chat is already correct. Use the health check after edits:

```bash
labcanvas wechat health --json
```

It reports each configured group, whether its monitor state has caught up to
the decrypted DB, and whether the self-message and title-guard protections are
enabled. It also shows poll timing, Codex model/reasoning settings, and the
last loop timing metrics. Private chatroom IDs, wxids, DB paths, and table
names are omitted.

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

Worker tasks pick model effort from task difficulty: low for simple follow-ups,
medium for paper/PDF/search/research/figure work, and high for CAD, PCB,
Blender/OpenSCAD, install, GitHub, ordering, or other execution-heavy tasks. A
clear failure escalates once. If GUI delivery fails, the queue item is marked
`send_failed` with the error instead of retrying indefinitely.

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

## External Decrypt Backend

The optional second solution uses `ylytdeng/wechat-decrypt` as a private receive
backend while keeping LabCanvas GUI sending unchanged:

```bash
labcanvas wechat backend install --skip-deps
labcanvas wechat backend status --json
labcanvas wechat backend probe --json
labcanvas wechat backend init-config --json
labcanvas wechat backend decrypt --incremental
labcanvas wechat backend monitor-web --port 5679
labcanvas wechat backend api-history --port 5679 --json
```

Use `find-keys` only when the private key file is missing; Linux key extraction
requires root or `CAP_SYS_PTRACE`. `monitor-web` runs through a LabCanvas
localhost-only launcher instead of exposing the upstream Web UI on all
interfaces. Status output redacts WeChat profile IDs and never prints keys or
decrypted message contents.

## Chat Purpose Modes

Keep one direct config per group. Research chats such as `懒人科研` should use
`chat_purpose: "research"` and explicit triggers. Language-learning chats such
as `EchoMind` can use:

```json
{
  "respond_to_all": true,
  "respond_to_self": false,
  "trigger_local_types": [1],
  "chat_purpose": "language_learning",
  "analysis_mode": "echomind_language",
  "codex": {"model": "gpt-5.5", "reasoning_effort": "medium"}
}
```

EchoMind replies to normal messages with Japanese furigana/romaji, Chinese
pinyin, grammar notes, and English glosses. The direct monitor silently ignores
messages that request secrets, credentials, payment/order actions, destructive
commands, prompt disclosure, or bot rule changes.
Keep `ignore_self_messages: true` so EchoMind does not analyze or repeat its own
previous output. Enable `respond_to_self` only for short manual tests where
phone-sent messages from the same logged-in account should trigger replies.

The tmux supervisor runs a single decrypt refresh pane and launches each direct
group monitor with `--no-decrypt`. This keeps `懒人科研`, `EchoMind`, and other
configured groups independent while avoiding concurrent decrypt stalls. The
refresh pane uses `labcanvas wechat backend decrypt --incremental` through the
same backend wrapper as the CLI, and skips decrypt work when the source DB/WAL
timestamp is unchanged. `labcanvas wechat health --json` reports the external
backend state next to per-group catch-up status and latest-row age. Research
configs can enable attachment triggers for image/video/file rows; EchoMind keeps
those disabled so it only responds to language-learning text.
Each group can keep two private Codex sessions, `fast` and `worker`, in
`.private/codex_sessions/`. Session keys include a short hash of the exact chat
title, so non-ASCII groups such as `懒人科研` and `鏈接` cannot collapse into the
same reusable thread. If `labcanvas wechat status --json` reports
`legacy_key: true`, back up and remove that old registry before restarting the
monitors. Set `WECHAT_CODEX_REUSE_SESSIONS=0` to force stateless turns.
Worker sessions use `danger-full-access` by default so downloads and external
tooling are not blocked by the shell sandbox; set
`WECHAT_WORKER_CODEX_SANDBOX=workspace` to downgrade for a restricted run.
For login/CAPTCHA/download blocks, open a browser in the same isolated noVNC
desktop with `labcanvas wechat browser-assist --url "<url>" --json`; the user
handles the manual step and the worker continues after approval.
Private send targets should include `expected_title`; before composing, the GUI
sender OCR-checks the opened chat header and fails closed if the wrong group is
visible. All GUI sends use `.private/wechat_gui_send.lock`; do not run parallel
raw click/paste senders against the same WeChat desktop. If WeChat opens a
small floating chat or search window, the sender closes secondary WeChat windows
and retries configured `fallback_clicks` before using Return.

## Group Creation

Group creation is intentionally gated. Prefer search-based selection by contact
alias/name, then set group settings with the guarded admin helper:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_group_create.py \
  --display :97 \
  --member-query lachlach \
  --member-query lachlanchen \
  --member-query lachlanchan
```

Only pass `--create` after the selected members are verified, because WeChat
notifies real accounts when a group is created:

```bash
labcanvas wechat create-group \
  --member-query lachlach \
  --member-query lachlanchen \
  --member-query lachlanchan \
  --create
```

Set the group name and this account's in-group alias through Settings:

```bash
labcanvas wechat rename --chat "EchoMind" --name "EchoMind"
labcanvas wechat alias --chat "EchoMind" --name "LazyingArt"
labcanvas wechat alias --chat "懒人科研" --name "LazyingArt"
```

The group admin helper edits the `Group Name` or `My Alias in Group` row,
captures screenshots, OCR-checks that the target row contains the requested
text, then clicks WeChat's `Modify` confirmation. Keep the OCR guard enabled
unless a human is watching noVNC.

See `docs/GITHUB_OPTIONS.md` for the GitHub automation options checked before
choosing the visible Linux GUI route.
See `docs/RUNBOOK.md` for the repeatable operator workflow.

## Guardrails

- It does not bypass WeChat login; approve the desktop login from the phone first.
- It sends only when `--send` is supplied.
- It targets the visible WeChat desktop, so keep noVNC open for human inspection.
- It stores private target files and mirror data under `.private/`, which is ignored.
- It is intended for small, explicit sends such as test messages, not bulk spam.
- Each monitored group needs its own `message_table`, `state_path`, and
  `send_target` so replies return to the correct chat.
