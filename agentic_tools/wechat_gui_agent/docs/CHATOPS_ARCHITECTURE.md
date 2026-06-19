# WeChat LabCanvas Chatops

This workflow uses two layers:

1. **Fast chat agent**: reads the local WeChat direct database stream, mirrors new
   messages into SQLite, detects mentions such as `@lachchen` or the in-group
   display name, loads recent chat history around the trigger, and sends quick
   acknowledgements or short replies.
2. **Worker agent**: handles slower jobs such as paper search, PDF download,
   GitHub/MCP work, file generation, and file/image return.

The visible GUI is still used for sending messages/files because it is the
least invasive reliable output path on Linux WeChat.

## Local Direct Source

The Linux client stores encrypted data under:

```text
~/Documents/xwechat_files/<wxid>/db_storage/
```

Important DBs:

- `session/session.db`: latest message summary per conversation.
- `message/message_0.db`: full text rows split into `Msg_*` tables.
- `message/message_resource.db`: resource metadata.
- `contact/contact.db`: contacts and chatroom metadata.

These are encrypted WCDB/SQLCipher files, not normal SQLite. The private
decryptor config, keys, and decrypted copies stay under:

```text
agentic_tools/wechat_gui_agent/.private/wechat_decrypt/
```

Do not commit `all_keys.json`, decrypted DBs, exported logs, screenshots, or
private target configs.

## Main Commands

Initialize direct backend config:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_direct_backend.py init-config
```

Extract local keys from the running WeChat process:

```bash
sudo agentic_tools/wechat_gui_agent/.private/wechat_decrypt/.venv/bin/python \
  agentic_tools/wechat_gui_agent/scripts/wechat_direct_backend.py find-keys
```

Decrypt DBs:

```bash
agentic_tools/wechat_gui_agent/.private/wechat_decrypt/.venv/bin/python \
  agentic_tools/wechat_gui_agent/.private/external/wechat-decrypt/decrypt_db.py
```

Run one direct chatops pass:

```bash
agentic_tools/wechat_gui_agent/.private/wechat_decrypt/.venv/bin/python \
  agentic_tools/wechat_gui_agent/scripts/wechat_direct_chatops.py \
  --config agentic_tools/wechat_gui_agent/.private/lazy-research-direct-chatops.local.json \
  --send
```

Run continuously in tmux:

```bash
agentic_tools/wechat_gui_agent/scripts/wechat_direct_chatops_tmux.sh
```

Run the full persistent supervisor in tmux:

```bash
agentic_tools/wechat_gui_agent/scripts/wechat_supervisor_tmux.sh start
```

For multi-group monitoring, store private shell settings in
`.private/wechat_supervisor.local.env`:

```bash
WECHAT_DIRECT_CONFIGS='/path/to/group-a-direct.json,/path/to/group-b-direct.json'
```

The supervisor creates one direct monitor pane per config. Use a unique
`state_path` per group so local IDs do not collide.

Run the complete operator stack, including the LabCanvas web control panel:

```bash
agentic_tools/wechat_gui_agent/scripts/wechat_stack_tmux.sh start
labcanvas wechat stack start --web-port 19474
```

The supervisor creates panes for:

- virtual desktop / Linux WeChat relaunch
- fast direct chat monitor
- slower worker queue processor
- optional media sync loop

## Files And PDFs

Send a message:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_chatops_bridge.py \
  --config agentic_tools/wechat_gui_agent/.private/lazy-research-chatops.local.json \
  --message "message text"
```

Send a PDF/image/file through the visible file picker:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_chatops_bridge.py \
  --config agentic_tools/wechat_gui_agent/.private/lazy-research-chatops.local.json \
  --file /absolute/path/to/file.pdf
```

Sync received downloads from known WeChat download folders:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_media_sync.py \
  --chat "懒人科研" \
  --auto-source \
  --since-minutes 60
```

The default destination layout is:

```text
.private/downloads/<chat>/<wechat-profile>/<category>/<relative-file>
```

## Worker Queue

The fast chat agent can enqueue slower work:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_task_worker.py \
  --enqueue "Find and send the public PDF for <paper title>"
```

Queued tasks should include recent chat history and recent synced file paths
from `.private/downloads`. This lets the worker resolve follow-up phrases such
as "this PDF", "the image above", or a bare group mention after a request.

Process one queued task and send the result:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_task_worker.py --once --send
```

Run it continuously:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_task_worker.py --loop --send
```

If a worker returns a `confirmation` field, the task is marked
`waiting_confirmation`. Approve or cancel it from the CLI or web panel:

```bash
labcanvas wechat approve <task-id> --note "approved settings"
labcanvas wechat reject <task-id> --note "manual review needed"
```

Worker output may be plain text or JSON:

```json
{
  "message": "Finished the paper download.",
  "files": ["/absolute/path/to/paper.pdf"]
}
```

Files are sent back through the visible WeChat file picker and recorded in the
mirror.

## Group Rename

Linux WeChat 4.x exposes the group-name editor as a blank field under the
`Group Name` row. The rename helper clicks that field, pastes the requested
name, presses Enter, and confirms the `Modify` dialog:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_group_admin.py \
  --chat "懒人科研" \
  --rename "懒人科研"
```

Use `--dry-run` to capture the field path without typing or confirming.

## Private Config Shape

Keep real IDs in ignored config files:

```json
{
  "chat_name": "<CHAT_NAME>",
  "chatroom_id": "<CHATROOM_ID>",
  "message_table": "<Msg_TABLE>",
  "self_wxid": "<SELF_WXID>",
  "trigger_prefixes": ["@lachchen", "＠lachchen", "@codex"],
  "mirror_db": "agentic_tools/wechat_gui_agent/.private/wechat_mirror.sqlite"
}
```

Use `labcanvas wechat init-config --chat "<CHAT_NAME>"` to create templates,
then fill in the table and account IDs discovered from the decrypted local DB.
