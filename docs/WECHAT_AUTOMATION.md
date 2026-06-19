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

`hold start` launches tmux session `labcanvas-wechat` with panes for the virtual
desktop, direct monitor, worker loop, and media sync loop. The monitor, worker,
and media panes run through a restart wrapper, so they come back after a crash
or transient failure.

For multiple group chats, put comma-separated direct configs in the ignored
`.private/wechat_supervisor.local.env` file:

```bash
WECHAT_DIRECT_CONFIGS='/path/to/group-a-direct.json,/path/to/group-b-direct.json'
```

The supervisor starts one fast monitor per config. Each config needs its own
`chat_name`, `message_table`, and `state_path`; optional `send_target` values
let replies open the correct group before sending.

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

## Fast And Worker Agents

The supervisor runs one decrypt refresh pane and one direct monitor pane per
group. Direct monitors normally use `--no-decrypt` and read the refreshed cache;
this avoids multiple monitors competing over the WeChat DB. The refresh pane
calls the LabCanvas backend wrapper in incremental mode and, by default, skips
decrypt work when the source DB/WAL timestamp has not changed. Idle polling is
local SQLite/file work and does not call Codex. A Codex call only happens when a
new message must be classified or answered.

The fast monitor reads new decrypted rows, ignores system/non-text rows as
triggers for language-learning chats, mirrors them into SQLite, and routes
mentions. Research chats can additionally treat image/video/file rows as
attachment triggers; those rows immediately ACK and enqueue a worker task using
recent synced media from `.private/downloads`. When a trigger is found, it also
loads recent full chat history from the decrypted message table, so a bare
`@name` can refer back to an earlier request such as "summarize this PDF". It
asks the low-reasoning router for one of four shapes:

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
upload. If the worker needs an important decision before continuing, it returns
`confirmation`, sends that question to chat, and marks the task
`waiting_confirmation`.

Each monitored group reuses two private Codex sessions: a `fast` session for
immediate routing/chat replies and a `worker` session for slower backend tasks.
The session registry lives under `.private/codex_sessions/`; public status
output shows only shortened thread IDs and role metadata. Set
`WECHAT_CODEX_REUSE_SESSIONS=0` before starting the supervisor to force fully
stateless `codex exec` calls.

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

Set `WECHAT_MEDIA_SOURCES` to a colon-separated override before `hold start` if
you want to add explicit folders. The default tmux media pane uses auto-source.
Copied files are organized as:

```text
agentic_tools/wechat_gui_agent/.private/downloads/<chat>/<wechat-profile>/<category>/<file>
```

This keeps files/images from different local WeChat profiles separate while
keeping them out of git.

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
  the header crop is unreliable.
- GUI sends are serialized by `.private/wechat_gui_send.lock`; do not bypass the
  sender helper with parallel raw `xdotool` scripts.
- Keep danger handling silent in chat; record only private mirror metadata if a
  blocked message must be audited.
