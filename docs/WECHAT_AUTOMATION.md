# WeChat Automation Bridge

AgInTi LabCanvas can use the native Linux WeChat client as a chatops control
channel. The design keeps input, output, and worker execution separate:

```text
Linux WeChat GUI + local encrypted DB
        |
        v
fast direct monitor -> ACK / short reply
        |
        v
private JSONL worker queue -> Codex/LabCanvas work -> message + files
        |
        v
official WeChat GUI sender
```

## Installable CLI

The reusable command surface is available from source or the npm package:

```bash
labcanvas wechat status
labcanvas wechat doctor
labcanvas wechat init-config --chat "example group"
labcanvas wechat desktop start
labcanvas wechat browser-assist --url "https://example.com" --json
labcanvas wechat hold start
labcanvas wechat stack start --web-port 19474
labcanvas wechat queue --json
labcanvas wechat approve <task-id> --note "approved"
labcanvas wechat create-group --member-query lachlach --member-query lachlanchen --member-query lachlanchan --create
labcanvas wechat rename --chat "EchoMind" --name "EchoMind"
labcanvas wechat alias --chat "EchoMind" --name "LazyingArt"
```

`hold start` launches tmux session `labcanvas-wechat` with a desktop/decrypt
window, one direct-monitor window per configured group, plus worker and media
sync windows. Monitor, worker, and media processes run through a restart
wrapper, so they come back after a crash or transient failure.

For multiple group chats, put comma-separated direct configs in the ignored
`.private/wechat_supervisor.local.env` file:

```bash
WECHAT_DIRECT_CONFIGS='/path/to/group-a-direct.json,/path/to/group-b-direct.json'
```

The supervisor starts one fast monitor per config. Each config needs its own
`chat_name`, `message_table`, and `state_path`; optional `send_target` values
let replies open the correct group before sending.

Configs can opt into structured memory capture with an ignored SQLite database:

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

The direct monitor backs up and tags messages before routing. It classifies
notes, memos, todos, groceries, calendar hints, beat-board/story ideas,
writing/language/money ideas, requests, attachments, rich media, web clips, and
inbox items into `source_messages`, `memory_items`, `tags`, and `item_tags`. If
`ack_on_save` is enabled and no worker task was triggered, the monitor sends a
short deterministic receipt without calling Codex. One database can be shared
across any number of groups because every row stores `chat_name`.

For a link/read-later group such as `鏈接`, set `chat_purpose` to
`web_clip_inbox`. Plain URLs, PDFs, images/screenshots, voice/audio, videos,
forwarded webpage cards, mini programs, archives, CAD/PCB files, YouTube links,
视频号/Shipinhao shares, Bilibili links, contact/location cards, and other
shared objects are stored as inbox items and can trigger an ACK plus worker task
for summary or extraction. Questions such as "summarize this link", "what is
this", or `这个链接讲什么？` also go through the fast router; slow page/PDF/media
inspection or export requests are acknowledged and sent to the worker queue.

For 视频号/Shipinhao/Finder shares, the worker should treat comments as optional
auxiliary evidence when they are accessible. Search visible or retrieved comments
for prompts such as `@元宝`, `腾讯元宝`, `英文全文`, `全文`, `总结`, `摘要`, `字幕`,
`转写`, `transcript`, and `summary`, because viewers often ask Yuanbao or other
AI accounts for the transcript or summary. Skim other high-signal comments for
quoted lines, timestamps, corrections, names, links, or context. Reading comments
is allowed; posting a comment or asking Yuanbao from the account requires an
explicit user request or confirmation. If the actual video, comments,
transcript, or a reliable public mirror are not accessible, do not produce a
"deep analysis" or imply the source was watched/read. Report the limitation and
ask for the video/comments/transcript or manual browser access if deeper
analysis is needed.

Inspect the private organizer without opening raw chat tables:

```bash
labcanvas wechat memory init
labcanvas wechat memory summary --chat "写作 外语 挣钱"
labcanvas wechat health --json
```

`stack start` keeps both the WeChat supervisor and the LabCanvas web control
panel alive. It starts `labcanvas-wechat` plus a web tmux session named
`labcanvas-web-wechat` by default. The web port is preferred, not fixed; if the
port is busy, the web app moves to the next free port and prints the actual URL.

Install user launchers:

```bash
labcanvas wechat install-user-scripts
~/scripts/labcanvas-wechat-hold.sh start
~/scripts/create-labcanvas-wechat-tmux.sh
~/scripts/create-labcanvas-wechat-stack.sh
```

## LabCanvas Worker Tools

Research groups such as `懒人科研` use the fast direct monitor only for routing.
Messages mentioning `aginti`, `image generation`, `figure grid`, `icons`,
`render`, `cad`, `pcb`, `kicad`, `gerber`, `step`, `stl`, `3d`, `blender`, or
`labcanvas` are acknowledged and pushed into the worker queue. The worker prompt
includes a LabCanvas tool playbook for:

```bash
PYTHONPATH=src python -m agenticapp studio figure-grid "microscopy icons 2x3" --storage-dir output/webapp --json
PYTHONPATH=src python -m agenticapp studio lab-task "prepare PCB/CAD render" --mode auto --execute --storage-dir output/webapp --json
PYTHONPATH=src python -m agenticapp scene-template experiment-setup --output output/wechat_worker/demo/scene.json
PYTHONPATH=src python -m agenticapp render-scene output/wechat_worker/demo/scene.json --output-dir output/wechat_worker/demo
PYTHONPATH=src python -m agenticapp studio dispatch blender "Prepare an editable setup render" --json
```

Worker replies should return generated artifacts in a JSON `files` array. The
sender accepts review artifacts such as AgInTi PNG/JPG/SVG figure outputs,
prompt/request/manifest files, PDF, STEP/STL/SCAD, Gerber ZIPs, KiCad project
files, and `.blend` files. It refuses private paths,
decrypted WeChat data, keys, cookies, browser profiles, chat logs, unsupported
suffixes, and oversized files before sending.

Worker tasks are source-isolated. A task may use only the current chat title,
the recorded `source.local_id`/`source.server_id`, the task context rows, and
the explicit source/reference rows embedded in the request plus media paths
listed from that same chat's download folder. This supports multi-message tasks
such as sending an image and then sending "change the two people to anime": the
text command is paired with recent same-chat image/file rows before it reaches
the worker. Before queueing a media task, the direct monitor runs a same-chat
media sync, extracts quoted image/file tokens such as MD5 values, and records
the sync attempt in the private mirror DB. If an image, PDF, video, or quoted
source cannot be matched exactly, the worker must ask for the source again
instead of using media from another group or an older task.

The background media sync is shared by every configured group and DM. If
`WECHAT_MEDIA_CHATS` is not set, the supervisor derives the chat list from
`WECHAT_DIRECT_CONFIGS`, so friends such as `<FRIEND_NAME>` and groups use the
same download and decode path. It scans `msg/file`, `msg/video`, `msg/attach`,
`cache`, `temp/ImageTemp`, and `temp/ImageUtils`, records all candidates in the private
`media_files` table, and decodes readable WeChat image blobs where possible.
Old XOR `.dat` images decode directly. WeChat V1/V2 image containers need a
private image key in `agentic_tools/wechat_gui_agent/.private/wechat_image_keys.local.json`
or `WECHAT_IMAGE_AES_KEY`; keep that file ignored and do not print the key. If
the key is missing, the worker receives only same-chat fallback thumbnails or
asks the user to resend the source.

## External Decrypt Backend

The second receive path is implemented as an optional private backend around
`ylytdeng/wechat-decrypt`. It does not replace the production GUI send path or
the existing group monitors.

```bash
labcanvas wechat backend install --skip-deps
labcanvas wechat backend status --json
labcanvas wechat backend probe --json
labcanvas wechat backend init-config --json
labcanvas wechat backend decrypt --incremental
labcanvas wechat backend monitor-web --port 5679
labcanvas wechat backend api-history --port 5679 --json
labcanvas wechat backend mcp-config
```

The external checkout, generated `config.json`, SQLCipher keys, and decrypted
DBs live under `agentic_tools/wechat_gui_agent/.private/`. Status and probe
commands redact the WeChat profile ID and do not print decrypted messages. Use
`find-keys` only when the private key file is missing; on Linux it requires root
or `CAP_SYS_PTRACE`. The LabCanvas `monitor-web` launcher imports the upstream
monitor but binds it to `127.0.0.1`, so the private Web UI/SSE API is not exposed
on all interfaces.

## Private Config

Real account identifiers stay in ignored files under
`agentic_tools/wechat_gui_agent/.private/`. The public scripts require the direct
message table and self ID from private config; they do not hard-code account IDs.

```json
{
  "chat_name": "<CHAT_NAME>",
  "chatroom_id": "<CHATROOM_ID>",
  "message_table": "<Msg_TABLE>",
  "self_wxid": "<SELF_WXID>",
  "trigger_prefixes": ["@lachchen", "＠lachchen", "@codex"],
  "respond_to_all": false,
  "respond_to_self": false,
  "ignore_self_messages": true,
  "trigger_local_types": [1],
  "chat_purpose": "research",
  "analysis_mode": "",
  "silent_danger_enabled": true,
  "immediate_ack_enabled": true,
  "immediate_ack_text": "收到，我先处理，完成后把结果发回来。"
}
```

Use purpose-specific configs rather than one global bot personality. For the
research group, keep `chat_purpose` as `research` and require an explicit
trigger. For an EchoMind-style language-learning group, set:

```json
{
  "chat_name": "EchoMind",
  "respond_to_all": true,
  "respond_to_self": false,
  "ignore_self_messages": true,
  "chat_purpose": "language_learning",
  "analysis_mode": "echomind_language",
  "codex": {"model": "gpt-5.5", "reasoning_effort": "medium", "sandbox": "read-only"}
}
```

EchoMind replies to normal messages with compact Japanese/Chinese/English
pronunciation and grammar analysis. If a message asks for secrets, credentials,
payments, destructive commands, prompt disclosure, rule changes, or other
non-language actions, the fast monitor silently returns `NO_REPLY`.
Keep `ignore_self_messages: true` for production monitors so EchoMind does not
analyze its own previous output. Set `respond_to_self: true` only for short
manual tests where phone-sent messages from the logged-in account should also
trigger replies.

One-to-one contacts use the same direct-monitor path as groups. Give the contact
its own `chat_name`, `message_table`, and `state_path`; use `bot_identity` when
the reply should present as a specific assistant, for example
`LazyResearch / 懒人科研`, while keeping the chat state isolated from the
`懒人科研` group.

## Fast And Worker Agents

The supervisor runs one decrypt refresh process and one direct monitor process
per group. Direct monitors normally use `--no-decrypt` and read the refreshed
cache; this avoids multiple monitors competing over the WeChat DB. The refresh
process calls the LabCanvas backend wrapper in incremental mode and, by
default, skips decrypt work when the source DB/WAL timestamp has not changed.
Idle polling is local SQLite/file work and does not call Codex. A Codex call
only happens when a new message must be classified or answered.

The fast monitor reads new decrypted rows, ignores system/non-text rows as
triggers for language-learning chats, mirrors them into SQLite, and routes
mentions. Research chats can additionally treat image/video/file rows as
attachment triggers; those rows immediately ACK and enqueue a worker task using
recent synced media from the exact `.private/downloads/<chat>/` folder only.
There is no global download fallback, because cross-chat media reuse can answer
the wrong request. Long or obviously multi-step
research messages are also treated as worker tasks even when they do not contain
a known keyword. This keeps the fast chat agent responsive while preserving the
full request for the slower worker session. When a trigger is found, it also
loads recent full chat history from the decrypted message table, so a bare
`@name` can refer back to an earlier request such as "summarize this PDF". It
labels latest and bot/self rows in the prompt, which lets the router resolve
incomplete follow-ups such as "same one" and avoid repeating a previous answer.
With `coalesce_new_messages` enabled, a burst of actionable rows is answered
once at the latest row while earlier actionable rows are marked `FOCUS`.
EchoMind must analyze every `FOCUS` plus `LATEST` sentence in the single reply;
LazyResearch must include every `FOCUS` plus `LATEST` instruction in the chat
reply or worker task. The router should chip in when the chat clearly asks for
help, shows confusion, mentions the bot, or needs a short expert note; otherwise
it should return `NO_REPLY` for ordinary side conversation. It asks the
low-reasoning router for one of four shapes:

For personal-organizer groups, the deterministic organizer runs before the
router. This keeps idle polling local and cheap: Codex is called only when the
message is an actionable save/list/summarize/schedule/organize request or when
the group explicitly mentions the bot. Plain notes are still backed up and
tagged silently.

Quoted/reply messages are split from packed WeChat message types by using the
low 32-bit base type and high 32-bit subtype. `base=49, subtype=57` is rendered
as `quote_reply`; the reply title is the current command and the referenced
message becomes quoted context. These rows are not treated as generic
attachments, because they can contain ordinary chat instructions.

```text
CHAT: <quick reply>
ACK: <short confirmation>
TASK: <slower backend task>
NO_REPLY
```

`TASK` rows are appended to `.private/wechat_task_queue.jsonl`. The worker loop
can send plain text or JSON with files:

```json
{
  "message": "Finished the export.",
  "files": ["/absolute/path/to/report.pdf", "/absolute/path/to/preview.png"],
  "confirmation": ""
}
```

For obvious slow work such as paper downloads, CAD/renders, figures, PCB jobs,
or file/image handling, the monitor can skip the fast Codex call, send the ACK
immediately, and enqueue the backend task directly. The queued task includes
recent chat history and recent synced WeChat file paths from `.private/downloads`
so the worker can resolve phrases like "this PDF" without asking for another
upload. For delayed follow-ups, the router also includes recent same-chat
attachment rows as source/reference rows, so "edit this image" can refer to an
image sent just before the text command. The worker prompt also checks recent
bot/self context before work so it returns only a delta/status when a request is
repeated. If the worker needs an important decision before continuing, it returns
`confirmation`, sends that question to chat, and marks the task
`waiting_confirmation`.

Each monitored group reuses two private Codex sessions: a `fast` session for
immediate routing/chat replies and a `worker` session for slower backend tasks.
The session registry lives under `.private/codex_sessions/`; public status
output shows only shortened thread IDs, role metadata, and whether an entry uses
the legacy key format. Current keys include a hash of the exact chat title to
keep Chinese, Japanese, emoji, and English group names independent. Back up and
remove legacy `wechat:*` or plain `<chat>:<role>` registry entries if context
ever crosses groups. Set `WECHAT_CODEX_REUSE_SESSIONS=0` before starting the
supervisor to force fully stateless `codex exec` calls.

The worker chooses its own Codex policy from task difficulty: low for simple
chat follow-ups, medium for paper/PDF/search/figure/research work, and high for
CAD, PCB, Blender/OpenSCAD, install, GitHub, ordering, or other full execution
tasks. If the first worker result is a timeout, empty/too-short answer, or clear
failure, it escalates one reasoning level once. GUI send failures are recorded
as `send_failed` instead of crashing the worker loop or repeatedly sending the
same task.

Worker Codex turns default to `danger-full-access` because downloads, CAD/PCB
exports, browser automation, and file transfers often need access outside the
repo worktree. To restrict worker execution for a debugging run, set
`WECHAT_WORKER_CODEX_SANDBOX=workspace` or `read-only` before restarting the
supervisor. Fast router sessions remain read-only unless a group config
explicitly changes its `codex.sandbox`.

If a download is blocked by login, consent, CAPTCHA, or another manual check,
use the same isolated noVNC virtual desktop rather than bypassing the check:

```bash
labcanvas wechat browser-assist --url "https://example.com/download" --json
```

The helper opens a persistent browser profile under `.private/browser_assist/`
on display `:97` and prints the noVNC URL. The user can log in, click CAPTCHA,
approve a download, or save a file manually; the worker should then wait for
confirmation before continuing.

Approve or cancel confirmation tasks from the CLI:

```bash
labcanvas wechat approve <task-id> --note "use the cheaper material"
labcanvas wechat reject <task-id> --note "wait for manual review"
```

If no task id is supplied, the newest `waiting_confirmation` task is selected.
Approval returns the task to `pending` so the worker can continue with the note
attached.

Useful refresh tuning variables:

```bash
WECHAT_DECRYPT_REFRESH_INTERVAL=1
WECHAT_DECRYPT_REFRESH_MODE=incremental
WECHAT_DECRYPT_REFRESH_SMART=1
WECHAT_DECRYPT_HEARTBEAT_INTERVAL=30
```

## Media Sync

Copy recent downloads into the private workspace. Use `--auto-source` to scan
local `~/Documents/xwechat_files/*` media folders:

```bash
labcanvas wechat media-sync --chat "example group" \
  --auto-source \
  --since-minutes 60
```

For quoted or referenced files, pass a stable token from the message metadata,
such as an image MD5 or cached filename stem. Token matches are copied even when
the file is older than the mtime window:

```bash
labcanvas wechat media-sync --chat "example group" \
  --auto-source \
  --match-token cafed00d1234567890abcdef12345678 \
  --record-empty \
  --summary-only
```

Set `WECHAT_MEDIA_SOURCES` to a colon-separated override before `hold start` if
you want to add explicit folders. The default tmux media process uses
auto-source. By default, the supervisor derives `WECHAT_MEDIA_CHATS` from every
configured direct-monitor config, so the background loop mirrors media for all
groups and DMs such as `lachlanchan`. Override it with a comma-separated list
only when you need a narrower set.
Copied files are organized as:

```text
agentic_tools/wechat_gui_agent/.private/downloads/<chat>/<wechat-profile>/<category>/<file>
```

This keeps files/images from different local WeChat profiles separate while
keeping them out of git. The router reads only the configured chat's folder
(including the same sanitized folder name used by media sync) and never scans
the parent downloads directory.

The sync utility scans `msg/file`, `msg/video`, `msg/attach`, `cache`, and
`temp/ImageTemp`, and `temp/ImageUtils`. It detects common extensionless blobs by magic bytes and
mirrors them with usable suffixes such as `.jpg`, `.png`, `.webp`, `.pdf`,
`.mp4`, or `.zip`. It also decodes readable WeChat `.dat` image blobs:
legacy XOR images work directly; V1/V2 AES containers work when the private
image key is available through `wechat_image_keys.local.json`, the external
decryptor config, or `WECHAT_IMAGE_AES_KEY`. If full-size V2 decode is
unavailable, the worker still receives same-chat thumbnail or mid-temp images
from the matched message-time window.
When the official WeChat client opens an image, it may write a readable JPG to
`temp/ImageUtils`; media sync treats that folder as same-chat evidence only when
the filename/token or message-time window matches the source row.
Every copied, decoded, existing, dry-run, or error candidate is recorded in the
private `media_files` table with source path, mirrored path, status, size,
mtime, suffix, decode status, and match reason.

## Nutstore AutoPublish Import

Use the mirrored media database to send the newest WeChat video into the
Nutstore AutoPublish watcher folder:

```bash
labcanvas wechat autopublish-video --chat "example group" --sync --json
```

The command copies to
`/home/lachlan/Nutstore Files/AutoPublish/AutoPublish` by default, writes through
`/home/lachlan/Nutstore Files/AutoPublish/.tmp_autopub_copy`, then atomically
renames the final file to a `*_COMPLETED.mp4`/`.MOV` style name. This prevents
AutoPublish from reading a partial copy. Useful variants:

```bash
labcanvas wechat autopublish-video --chat "example group" --list --json
labcanvas wechat autopublish-video --source /path/to/video.mp4 --title "paper demo"
labcanvas wechat autopublish-video --chat "example group" --since-minutes 720 --replace
labcanvas wechat autopublish-video --chat "example group" --sync --fetch-gui --json
```

Set `LABCANVAS_AUTOPUBLISH_DIR` or pass `--dest` if the Nutstore folder moves.
Use `--dry-run` to inspect the exact target filename without copying. Use
`--fetch-gui` when a WeChat video message exists but only the thumbnail is
cached: the tool opens the chat in the isolated WeChat desktop, clicks the
latest visible video, waits for WeChat to write the MP4 under `msg/video`, runs
media sync again, then copies the matched video to AutoPublish.

## Web App

The LabCanvas web app exposes a compact WeChat Ops card for:

- starting the complete WeChat + web stack
- checking desktop/supervisor status
- starting and stopping the persistent tmux supervisor
- opening the noVNC desktop
- viewing pending queue count, recent mirrored messages, and media sources
- approving or rejecting the newest waiting confirmation task
- processing one queued worker task manually
- sending a short message to the currently visible chat

The card auto-refreshes status every 10 seconds.

Run:

```bash
labcanvas wechat stack start --web-port 19474
```

## Group Rename

Create or update groups through the visible Linux client. Group creation is
search based, so it is more stable than selecting contacts by a stale row
number:

```bash
labcanvas wechat create-group \
  --member-query lachlach \
  --member-query lachlanchen \
  --member-query lachlanchan \
  --create
```

Then set the group name and the current account's in-group alias:

```bash
labcanvas wechat rename --chat "example group" --name "懒人科研"
labcanvas wechat alias --chat "example group" --name "LazyingArt"
```

The helper opens Settings, edits the `Group Name` or `My Alias in Group` row,
uses screenshots/OCR to verify the intended row contains the target text, then
clicks WeChat's `Modify` confirmation. Add `--dry-run` to capture screenshots
without typing. Use `--skip-ocr-guard` only under direct human supervision.

For the EchoMind setup used here:

```bash
labcanvas wechat create-group \
  --member-query lachlach \
  --member-query lachlanchen \
  --member-query lachlanchan \
  --create
labcanvas wechat rename --chat "EchoMind" --name "EchoMind"
labcanvas wechat alias --chat "EchoMind" --name "LazyingArt"
labcanvas wechat alias --chat "懒人科研" --name "LazyingArt"
```

## Guardrails

- Keep `.private/`, decrypted DBs, keys, screenshots, and chat logs out of git.
- Use noVNC on `127.0.0.1` and approve login from the phone.
- Send only through explicit `--send` or web button actions.
- Verify file sends in the GUI when attachments are important.
- Use a distinct `send_target`, `message_table`, and `state_path` for each group
  so replies go back to the group that produced the trigger.
- Include `expected_title` in each private send target. The GUI sender OCR-checks
  the opened chat title before composing and fails closed if the wrong group is
  visible. It retries during WeChat loading and falls back to full-page OCR when
  the header crop is unreliable. If OCR consistently misreads a group name, add
  `expected_title_aliases` for the observed OCR text plus stable
  `fallback_clicks`.
- GUI sends are serialized by `.private/wechat_gui_send.lock`; do not bypass the
  sender helper with parallel raw `xdotool` scripts.
- Keep danger handling silent in chat; record only private mirror metadata if a
  blocked message must be audited.
