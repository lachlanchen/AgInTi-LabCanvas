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
`state_path` per group so local IDs do not collide. It also runs a single
decrypt refresh pane; direct monitors use `--no-decrypt` and read the shared
refreshed cache, which avoids concurrent decrypt stalls. The fast path should
run with `WECHAT_DIRECT_POLL_SECONDS=0.8`,
`WECHAT_DIRECT_CATCHUP_POLL_SECONDS=0.1`, and
`WECHAT_DECRYPT_REFRESH_INTERVAL=1`; each group config should use `gpt-5.5`
with low reasoning for immediate replies and leave heavier work to the worker
queue.
Private send targets should include `expected_title`; the GUI sender OCR-checks
the opened chat header before composing and fails closed if the wrong chat is
visible. Add `fallback_clicks` when WeChat search results appear at different
rows; each fallback is still protected by the same title guard. The sender waits
for the chat to finish loading, retries the title guard, and can use full-page
OCR when the header crop is too noisy.

Check the running multi-group setup with:

```bash
labcanvas wechat health --json
```

The health command compares each monitor state file against the latest local
message ID in the decrypted DB, verifies self-message guards, and reports the
active poll/Codex settings plus last-loop timings without printing chatroom IDs,
wxids, message-table names, or decrypted DB paths.

Use a purpose field in each private config. `懒人科研` is the research workflow
and should require an explicit trigger. `EchoMind` is the language-learning
workflow and can set `respond_to_all: true`,
`respond_to_self: false`,
`chat_purpose: "language_learning"`, and
`analysis_mode: "echomind_language"` so each normal message is analyzed for
Japanese furigana/romaji, Chinese pinyin, grammar, and English meaning.
Dangerous or off-purpose messages should return `NO_REPLY` silently.
Set `respond_to_self: true` only if phone-sent messages from the logged-in
account should trigger replies; exact sent replies are remembered and skipped to
avoid loops.

Run the complete operator stack, including the LabCanvas web control panel:

```bash
agentic_tools/wechat_gui_agent/scripts/wechat_stack_tmux.sh start
labcanvas wechat stack start --web-port 19474
```

The supervisor creates panes for:

- virtual desktop / Linux WeChat relaunch
- decrypt refresh loop
- one fast direct chat monitor per configured group
- slower worker queue processor
- optional media sync loop

The direct monitor is intentionally a lightweight router. Idle polling only
checks local decrypted rows and mirror state, so it does not spend model tokens.
Model calls happen when a new message needs a quick reply or a task must be
queued. Worker tasks choose `gpt-5.5` effort automatically: low for simple
follow-ups, medium for paper/PDF/search/research/figure work, and high for CAD,
PCB, Blender/OpenSCAD, install, GitHub, ordering, or other full execution work.
If a worker result is clearly failed, timed out, or too weak, the worker retries
once at the next effort level. GUI send failures are saved as `send_failed` so
the loop does not crash or resend duplicates indefinitely.

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
`Group Name` row and this account's in-group display name under
`My Alias in Group`. Use the guarded helpers instead of ad hoc clicks:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_group_admin.py \
  --chat "懒人科研" \
  --rename "懒人科研"
python3 agentic_tools/wechat_gui_agent/scripts/wechat_group_admin.py \
  --chat "懒人科研" \
  --my-alias "LazyingArt"
```

The helper opens Settings, focuses the requested row, replaces the row text,
captures screenshots, OCR-checks that the target row contains the requested
value, then clicks the `Modify` dialog. Use `--dry-run` to capture the row
without typing. Use `--skip-ocr-guard` only while watching the noVNC desktop.

Create groups by searched aliases rather than fixed contact rows:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_group_create.py \
  --display :97 \
  --member-query lachlach \
  --member-query lachlanchen \
  --member-query lachlanchan \
  --create
```

## Private Config Shape

Keep real IDs in ignored config files:

```json
{
  "chat_name": "<CHAT_NAME>",
  "chatroom_id": "<CHATROOM_ID>",
  "message_table": "<Msg_TABLE>",
  "self_wxid": "<SELF_WXID>",
  "trigger_prefixes": ["@lachchen", "＠lachchen", "@codex"],
  "respond_to_all": false,
  "chat_purpose": "research",
  "analysis_mode": "",
  "silent_danger_enabled": true,
  "mirror_db": "agentic_tools/wechat_gui_agent/.private/wechat_mirror.sqlite"
}
```

Use `labcanvas wechat init-config --chat "<CHAT_NAME>"` to create templates,
then fill in the table and account IDs discovered from the decrypted local DB.
