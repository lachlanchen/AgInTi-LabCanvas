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
```

`hold start` launches tmux session `labcanvas-wechat` with panes for the virtual
desktop, direct monitor, worker loop, and optional media sync loop.

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
  "trigger_prefixes": ["@lachchen", "＠lachchen", "@codex"]
}
```

## Fast And Worker Agents

The fast monitor reads new decrypted rows, mirrors them into SQLite, and routes
mentions. It asks Codex for one of three shapes:

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
  "files": ["/absolute/path/to/report.pdf", "/absolute/path/to/preview.png"]
}
```

## Media Sync

Copy recent downloads into the private workspace:

```bash
labcanvas wechat media-sync --chat "example group" \
  --source "$HOME/Documents/xwechat_files/<WXID>/file" \
  --since-minutes 60
```

Set `WECHAT_MEDIA_SOURCES` to a colon-separated list before `hold start` to keep
sync running in tmux.

## Web App

The LabCanvas web app exposes a compact WeChat Ops card for:

- checking desktop/supervisor status
- starting and stopping the persistent tmux supervisor
- sending a short message to the currently visible chat

Run:

```bash
labcanvas webapp start --port 19473
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
