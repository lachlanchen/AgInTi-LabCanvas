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
pushed to the Android `/sdcard/Download` root, selected by exact filename, and
sent only after the confirmation dialog contains both the exact target chat
and artifact name. Long names are shortened deterministically to at most 36
characters with an eight-character content digest; the ledger retains the
original path, size, and full SHA-256. Before committing, the bridge records a
`committing` component. Confirmation accepts a stable full or middle-ellipsized
same-chat file card, preventing a successful upload from being retried merely
because WeCom truncated its visible name. Artifact-only recovery may reconcile
that exact visible digest card without uploading it again.

`POST /v1/delivery-status` reads the text/file component ledger without
opening or changing the phone UI. The worker calls it before every retry with
the stable task ID and complete desired batch. `POST /v1/send` may return an
HTTP 200 response with `ok: false` when an earlier component was committed but
a later one failed. That is a valid partial result: persist `sent_messages` and
`sent_files`, restore the exact chat composer from any stale picker or
confirmation overlay, and retry only `pending_messages`/`pending_files`. Never
repeat the entire batch after a timeout or partial response.

For WeCom research tasks, send the polished PDF by default. Keep Markdown,
LaTeX, BibTeX, evidence papers, and render audits in the private task folder
unless the current request explicitly asks for those source files. The
execution contract limits which artifact suffixes are mandatory; a PDF-only
contract must not become a Markdown/TeX delivery requirement.

Idle polling uses native unread badges for the fast path and reconciles every
allowlisted chat at a bounded interval (20 seconds by default). Opening a chat
manually or for diagnostics can clear its unread badge, but cannot permanently
hide the message from the relay. First contact still seeds the visible tail
instead of replaying old messages, preventing restart floods. Snapshot overlap,
the ingest history, and delivery component hashes suppress duplicate work and
replies. A failure in one allowlisted chat does not block reconciliation of the
others.

Inbound events retain the exact visible sender name and enter the normal WeCom
ingest/worker queue with same-chat isolation. The route agent's natural direct
reply or queued-task acknowledgement is checkpointed, then sent immediately
with the same native sender mention; long work continues independently. Visible
quote-preview text is preserved separately from the current message body and
included in the same task packet. Sender labels, timestamps, and read receipts
are excluded from quote text.

Scientifically valuable ideas use two tracks. The route agent sends a concise,
evidence-qualified preliminary answer immediately, then creates a durable deep
research task. Mechanism, hypothesis, experimental-design, literature-comparison,
roadmap, and quoted scientific follow-up questions normally require a polished
LaTeX PDF. The task contract records that PDF as required: completion needs a
verified same-chat file component, a durable deferred state, or an explicit
transport blocker. Existing exact-task reports can be delivered later through
artifact-only supplemental recovery without repeating the research.

## Group Inspiration

LabAgent can maintain a low-frequency group inspiration routine. The routine
waits until the group has been quiet for three hours, then queues one concise
agent-written knowledge point or useful connection. It uses the accumulated
same-group discussion, active member `#daily` interests, explicit group
interests, and prior inspiration outputs; it does not send a canned heartbeat.
The first point is queued immediately when a group explicitly changes focus.

```text
#interest organoids; biomanufacturing; speculative design
#interest replace event cameras; scientific imaging
#interest status
#interest off
#interest on
```

The default interval is three hours and can be changed locally with
`WECOM_INSPIRATION_INTERVAL_SECONDS`. A pending or running inspiration task is
never duplicated. Inspiration also yields whenever that exact group has active
interactive work, research, confirmation, or artifact delivery; it does not
create a delayed chat burst. Group interests are public group-scoped settings;
they do not merge private member records or authorize public posting.

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
