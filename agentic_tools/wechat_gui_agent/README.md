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
The wrapper keeps the isolated X11 desktop awake with `xset`, so noVNC should
not blank during long-running monitoring. Apply or refresh this without
restarting WeChat:

```bash
labcanvas wechat desktop keep-awake
```

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
labcanvas wechat control-map --json
tmux attach -t labcanvas-wechat
```

The supervisor keeps a virtual desktop/decrypt window, one fast direct-monitor
window per configured group, plus worker and media-sync windows. Monitor,
worker, and media processes restart automatically if they exit. Incoming
mentions can get an immediate ACK while longer work is queued for
`wechat_task_worker.py`, which can send a final message plus PDFs/images/files
back through the official WeChat GUI.

Use `labcanvas wechat hold restart` or `labcanvas wechat hold reload-workers`
after code changes; these commands do not restart the WeChat desktop. Use
`restart-all` only if you intentionally want the official client to close and
reopen, which may require mobile confirmation. If the supervisor is not running,
reload fails instead of launching WeChat unexpectedly.

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
labcanvas wechat control-map --json
```

It reports each configured group, whether its monitor state has caught up to
the decrypted DB, and whether the self-message and title-guard protections are
enabled. It also shows poll timing, Codex model/reasoning settings, and the
last loop timing metrics. Private chatroom IDs, wxids, DB paths, and table
names are omitted.

`control-map` is the implementation guide for robust control. It lists the
supported surfaces: isolated GUI automation, direct receive/mirror state,
same-chat media sync, deterministic workers, event/screenshot observability, and
optional bridge APIs. It also lists blocked approaches: packet/TLS MITM,
private-protocol replay, session extraction, credential theft, login/CAPTCHA
bypass, and cross-chat media guessing. Use Wireshark-style tooling only for
coarse connectivity diagnostics, never for message content or credentials.

For organizer-style groups, enable the private memory sidecar in that group's
direct config:

```json
{
  "chat_purpose": "personal_organizer",
  "respond_to_all": true,
  "organizer": {
    "enabled": true,
    "db_path": "agentic_tools/wechat_gui_agent/.private/wechat_memory.sqlite",
    "capture_unclassified": true,
    "default_tags": ["writing", "foreign-language", "money"],
    "ack_on_save": true,
    "ack_saved_text": "已保存到收件箱。"
  }
}
```

The monitor backs up every new row, then classifies inbound messages into
`source_messages`, `memory_items`, `tags`, and `item_tags`. It can track notes,
memos, todos, groceries, calendar hints, beat-board ideas, writing/language
ideas, money ideas, requests, rich media, and attachments across any number of
groups. The router replies to actionable save/list/summarize/schedule/organize
requests, explicit mentions, and configured shared-object summaries. If
`ack_on_save` is enabled and no worker task was triggered, ordinary saved notes
get a short deterministic receipt without a Codex call.

Use `chat_purpose: "web_clip_inbox"` for a group such as `鏈接`, where the chat
is mainly a read-later stream. Plain URLs, PDFs, images/screenshots,
voice/audio, videos, forwarded webpage cards, mini programs, archives, CAD/PCB
files, YouTube links, 视频号/Shipinhao shares, Bilibili links, contact/location
cards, and other shared objects become records in the same private database,
partitioned by `chat_name`. These shares can also trigger an ACK plus worker
task to summarize or extract the content; summary/list/export requests use the
same fast-router and worker queue.

For 视频号/Shipinhao/Finder shares, the worker also treats comments as optional
summary evidence when accessible. It should look for viewer prompts such as
`@元宝`, `腾讯元宝`, `英文全文`, `全文`, `总结`, `摘要`, `字幕`, `转写`,
`transcript`, and `summary`, plus other comments with quoted lines, timestamps,
corrections, names, or links. Reading comments is acceptable; posting a comment
or asking Yuanbao from the account requires explicit user confirmation. If the
actual video, comments, transcript, or a reliable public mirror are unavailable,
the worker should not produce a deep analysis; it should report the limitation
and ask for the source material or manual browser access.

Direct contacts can be monitored with the same config shape as groups. Keep a
unique `chat_name`, `message_table`, and `state_path` for each contact. Set
`bot_identity`, such as `LazyResearch / 懒人科研`, when the contact should hear a
specific assistant persona while remaining separate from the group with the
same persona.

```bash
labcanvas wechat memory init
labcanvas wechat memory summary --chat "写作 外语 挣钱"
```

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
`labcanvas wechat stack restart` preserves the WeChat GUI and reloads only
worker-side processes plus the web panel. Use `stack restart-all` only for a
deliberate full restart.

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

Worker tasks default to `gpt-5.5` and pick effort from task difficulty. Queued
backend work starts at `medium`, uses `high` for CAD/PCB/Blender/file/video/tool
execution, and uses `xhigh` for full autonomous tasks such as installs, GitHub
commit/push, publishing, ordering, or "finish this end-to-end" requests. A
timeout, empty result, or clear model failure retries upward through allowed
effort levels up to `xhigh`. Missing exact sources, login/CAPTCHA, and user
confirmation blockers do not trigger blind retries. If GUI delivery fails, the
queue item is marked `send_failed` with the error instead of retrying
indefinitely.
Before work starts, a queue item is claimed as `in_progress` under a file lock.
This prevents a manual `worker once` and the persistent loop from handling the
same request twice. Stale claims are reclaimed after
`WECHAT_WORKER_STALE_IN_PROGRESS_SECONDS` (default: one hour).

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
videos from different profiles do not collide. The sync scanner includes
`temp/ImageUtils`, where the official WeChat client writes readable JPGs after
an image is opened.

Copy the newest mirrored video from a group or DM into the Nutstore
AutoPublish watcher:

```bash
labcanvas wechat autopublish-video --chat "example group" --sync --json
```

The import command writes through a temporary folder and atomically creates a
`*_COMPLETED` file under `/home/lachlan/Nutstore Files/AutoPublish/AutoPublish`
so the watcher does not see partial copies. Use `--list --json` to inspect
candidate videos and `--source /path/to/video.mp4` for an explicit file. If a
video message is visible in WeChat but no MP4 has been cached yet, use
`--sync --fetch-gui`; the tool opens the chat, clicks the latest visible video,
waits for the official client to cache the MP4, then copies the matched file.

## LazyEdit Platform Publishing

Full video publishing is documented in
`agentic_tools/wechat_gui_agent/skills/lazyedit-publish-workflow/SKILL.md`. Use
that workflow when a chat task asks to publish, re-publish, subtitle, monitor, or
send a WeChat video to Shipinhao, YouTube, or Instagram.

The normal path is:

```bash
PYTHONPATH=src python -m agenticapp wechat autopublish-video \
  --chat "example group" \
  --message-local-id VIDEO_LOCAL_ID \
  --sync \
  --fetch-gui \
  --since-minutes 720 \
  --json

cd /home/lachlan/DiskMech/Projects/lazyedit
source ~/miniconda3/etc/profile.d/conda.sh
conda activate lazyedit
python scripts/lazyedit_publish.py \
  --video-id VIDEO_ID \
  --use-current-settings \
  --platforms shipinhao,youtube,instagram \
  --guided-monitor \
  --wait \
  --poll-seconds 10
```

For context-sensitive videos, pass separate files with
`--correction-prompt-file` and `--metadata-prompt-file`. Use `--no-process` only
when reusing an already completed LazyEdit output. If Shipinhao or another
platform needs QR login or manual confirmation, open the isolated browser and
wait for the user rather than bypassing the page.

For an explicit publish request, `--no-publish` is only a quality gate. After
the MP4/ZIP is correct and no manual blocker appears, continue to exactly one
real publish for the requested platforms and report the job ids/status.

The worker has a deterministic fast path for exact WeChat video rows. When
`autopublish-video --message-local-id` succeeds and the chat clearly asks to
publish, the worker waits for the LazyEdit import, runs
`scripts/lazyedit_publish.py` with the generated correction and metadata prompt
files, and monitors the local/remote publish queues before falling back to the
general Codex worker. Disable this path with
`WECHAT_WORKER_DISABLE_DETERMINISTIC_VIDEO_PUBLISH=1` when testing.

When the request comes from WeChat, keep the monitor's
`Video publish/subtitle context bundle` as the correction prompt. It preserves
the coalesced command, quoted message, same-chat media rows, recent context, and
visible metadata so subtitle correction can use the user's actual instructions.
Use a separate concise metadata brief for public title/description/hashtags.
Safe MP4/MOV/audio outputs can be returned in the worker JSON `files` array,
subject to the configured size limit.

For exact video-row tasks, pass `--message-local-id` so AutoPublish refuses to
copy a nearby older cached MP4. If an emoji-heavy group title is hard for OCR,
prefer `expected_title_aliases` such as the title without emoji. The relaxed
`allow_title_guard_fallback` path is for dry-run/review only; live sends still
fail closed unless `allow_live_title_guard_fallback` is deliberately set. Avoid
that live override for multi-chat monitors because it can post into the wrong
visible group.

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

The tmux supervisor runs a single decrypt refresh process and launches each
direct group monitor with `--no-decrypt`. This keeps `懒人科研`, `EchoMind`, and
other configured groups independent while avoiding concurrent decrypt stalls.
The refresh process uses `labcanvas wechat backend decrypt --incremental`
through the same backend wrapper as the CLI, and skips decrypt work when the
source DB/WAL timestamp is unchanged. `labcanvas wechat health --json` reports
the external backend state next to per-group catch-up status and latest-row age.
Research configs can enable attachment triggers for image/video/file rows, and
long or obviously multi-step research messages route directly to the worker
even without a known keyword. EchoMind keeps attachment triggers disabled so it
only responds to language-learning text.
Each group can keep two private Codex sessions, `fast` and `worker`, in
`.private/codex_sessions/`. Session keys include a short hash of the exact chat
title, so non-ASCII groups such as `懒人科研` and `鏈接` cannot collapse into the
same reusable thread. If `labcanvas wechat status --json` reports
`legacy_key: true`, back up and remove that old registry before restarting the
monitors. Set `WECHAT_CODEX_REUSE_SESSIONS=0` to force stateless turns.
Worker sessions use `gpt-5.5` and `danger-full-access` by default so downloads
and external tooling are not blocked by the shell sandbox; set
`WECHAT_WORKER_CODEX_SANDBOX=workspace` to downgrade for a restricted run.
Set `WECHAT_WORKER_MIN_EFFORT`, `WECHAT_WORKER_MAX_EFFORT`, or
`WECHAT_WORKER_MAX_CODEX_ATTEMPTS` to tune dynamic escalation. Spark worker
models are ignored unless `WECHAT_ALLOW_SPARK_WORKER=1` is set intentionally.
For login/CAPTCHA/download blocks, open a browser in the same isolated noVNC
desktop with `labcanvas wechat browser-assist --url "<url>" --json`; the user
handles the manual step and the worker continues after approval.
Private send targets should include `expected_title`; before composing, the GUI
sender OCR-checks the opened chat header and fails closed if the wrong group is
visible. All GUI sends use `.private/wechat_gui_send.lock`; do not run parallel
raw click/paste senders against the same WeChat desktop. If WeChat opens a
small floating chat or search window, the sender closes secondary WeChat windows
and retries configured `fallback_clicks` before using Return. If OCR repeatedly
misreads a group title, add `expected_title_aliases` for the observed OCR text.

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
