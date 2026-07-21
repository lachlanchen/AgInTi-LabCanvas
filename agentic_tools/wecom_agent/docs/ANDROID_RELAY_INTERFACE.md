# Android WeCom Relay Interface

The Android relay uses an owner-authorized physical WeCom client as a guarded
transport for exact allowlisted external groups. It feeds the same per-chat
LabCanvas queue and worker as the official WebSocket/CLI transports. It does
not use personal-WeChat state and does not depend on the Wine desktop client.

## Lifecycle

```bash
PYTHONPATH=src python -m agenticapp wecom android init \
  --serial <ADB_SERIAL> --chat <CHAT_NAME> --force --json
PYTHONPATH=src python -m agenticapp wecom android start --json
PYTHONPATH=src python -m agenticapp wecom android status --json
```

Private configuration, cursors, delivery components, staged files, and the API
token stay under `agentic_tools/wecom_agent/.private/`. The localhost API
defaults to `127.0.0.1:19581`. The `labcanvas-wecom:android-relay` tmux window
and the user autostart service restore it after reboot. The phone noVNC URL is
reported by `status`; it remains bound to localhost.

The relay disables host MTP automount prompts, keeps the authorized phone awake
while connected, disables UI animations, and locks UI rotation to portrait.
It never bypasses Android's secure keyguard. If the device is locked or ADB is
not authorized, writes fail closed.

## Read And Send

```bash
PYTHONPATH=src python -m agenticapp wecom android messages \
  --chat <CHAT_NAME> --json

PYTHONPATH=src python -m agenticapp wecom android send \
  --chat <CHAT_NAME> \
  --mention '<SENDER_DISPLAY_NAME>' \
  --message '处理完成。' \
  --file output/report.pdf \
  --task-id <STABLE_TASK_ID> \
  --live --json
```

Without `--live`, `send` is a dry run. A stable task ID plus content/file hash
makes retries idempotent. Files are copied to a private staging directory,
pushed to `/sdcard/Download/LabCanvas`, selected by exact filename, and sent
only after the confirmation dialog contains both the exact target chat and
artifact name.

Idle polling reads only chats with native unread badges. First contact seeds
the visible tail instead of replaying old messages, preventing restart floods.
Inbound events retain the exact visible sender name and enter the normal WeCom
ingest/worker queue with same-chat isolation. The route agent's natural direct
reply or queued-task acknowledgement is checkpointed, then sent immediately
with the same native sender mention; long work continues independently.

## Native Mentions

For group replies, the worker passes `source.reply_mentions` to the Android
send API. The bridge types `@`, opens WeCom's native member picker, and selects
exactly one matching row. WeCom may display an external member as
`<SENDER_DISPLAY_NAME>@微信` while the message bubble exposes only
`<SENDER_DISPLAY_NAME>`; that single suffix is the only accepted normalization.
Matching remains case-sensitive. Ambiguous, absent, broadcast (`所有人`), or
more than four mentions are rejected before Send.

The bridge verifies that WeCom created a rich mention span, then appends the
agent response. It never relies on plain `@name` text. Scheduled system reports
do not mention a person unless they directly originated from a current human
message.

## Safety And Recovery

- Every write requires an allowlisted `gui:<CHAT_NAME>` ID.
- The visible native chat title is verified before compose, file confirmation,
  and commit.
- A non-empty human draft is never overwritten.
- Failed automation-created drafts are cleared before releasing the send lock.
- The API binds to localhost and requires the ignored bearer token.
- Worker delivery also checks `task.chat`, `source.chat`, and target chat.
- Desktop WeCom login loss does not stop a healthy mobile relay.

Inspect without exposing private content:

```bash
tmux list-windows -t labcanvas-wecom
curl -fsS http://127.0.0.1:19581/health
tail -n 100 output/wecom/$(date +%F)/android-relay.log
```
