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
labcanvas wechat hold start
labcanvas wechat stack start --web-port 19474
labcanvas wechat queue --json
labcanvas wechat approve <task-id> --note "approved"
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
  "immediate_ack_enabled": true,
  "immediate_ack_text": "收到，我先处理，完成后把结果发回来。"
}
```

## Fast And Worker Agents

The fast monitor reads new decrypted rows, mirrors them into SQLite, and routes
mentions. When a trigger is found, it also loads recent full chat history from
the decrypted message table, so a bare `@name` can refer back to an earlier
request such as "summarize this PDF". It asks Codex for one of three shapes:

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

Approve or cancel confirmation tasks from the CLI:

```bash
labcanvas wechat approve <task-id> --note "use the cheaper material"
labcanvas wechat reject <task-id> --note "wait for manual review"
```

If no task id is supplied, the newest `waiting_confirmation` task is selected.
Approval returns the task to `pending` so the worker can continue with the note
attached.

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

Rename through the visible Linux client:

```bash
labcanvas wechat rename --chat "example group" --name "懒人科研"
```

The helper clicks the `Group Name` field, pastes the name, presses Enter, and
clicks the WeChat `Modify` confirmation. Add `--dry-run` if you only want
screenshots.

## Guardrails

- Keep `.private/`, decrypted DBs, keys, screenshots, and chat logs out of git.
- Use noVNC on `127.0.0.1` and approve login from the phone.
- Send only through explicit `--send` or web button actions.
- Verify file sends in the GUI when attachments are important.
