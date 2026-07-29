# WeCom GUI Relay Interface

The GUI relay is a localhost-only transport for explicitly allowlisted external
WeCom groups when Tencent does not grant the tenant's official `wecom-cli msg`
permission. It controls only the isolated WeCom Wine client. It never reads or
sends through personal WeChat.

## Setup and Lifecycle

```bash
PYTHONPATH=src python -m agenticapp wecom client start --json
PYTHONPATH=src python -m agenticapp wecom gui init --chat LabAgent
PYTHONPATH=src python -m agenticapp wecom gui init --chat AgentTest --allow-search-fallback
PYTHONPATH=src python -m agenticapp wecom gui restart --json
PYTHONPATH=src python -m agenticapp wecom gui status --json
```

The ignored config is
`agentic_tools/wecom_agent/.private/wecom_gui_bridge.local.json`. It contains
the exact group allowlist, display, state paths, localhost port, and bearer
token. The client supervisor and relay run in the
`labcanvas-wecom:wecom-client` and `labcanvas-wecom:external-gui` tmux windows
and are restored by the normal WeCom launcher. The default viewer is:

```text
http://127.0.0.1:6192/vnc.html?host=127.0.0.1&port=6192&autoconnect=1&resize=scale
```

## Stable CLI

```bash
# List stable target IDs.
PYTHONPATH=src python -m agenticapp wecom gui chats --json

# Invite one exact group to send tasks. Repeating this is idempotent.
PYTHONPATH=src python -m agenticapp wecom gui guide \
  --chat LabAgent --live --json

# Read messages after a durable cursor.
PYTHONPATH=src python -m agenticapp wecom gui messages \
  --chat LabAgent --after 0 --limit 100 --json

# Dry-run unless --live is present.
PYTHONPATH=src python -m agenticapp wecom gui send \
  --chat LabAgent --message 'Research request received.' \
  --task-id task-20260719 --live --json

PYTHONPATH=src python -m agenticapp wecom gui send \
  --chat LabAgent --file output/report.pdf \
  --task-id task-20260719 --live --json
```

Use a stable `task_id` for retries. Repeating the same task and exact payload
returns success without sending a duplicate.

`--allow-search-fallback` permits only exact chat-name navigation when a group
is absent from the visible recent list. The opened title must still match
exactly before any read or send; this does not search message content or weaken
the allowlist.

## Local API

The API binds to `127.0.0.1` only. `/health` is redacted and unauthenticated;
all versioned endpoints require `Authorization: Bearer <private token>`.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Redacted readiness and capabilities |
| `GET` | `/v1/chats` | Stable allowlisted `gui:<name>` chat IDs |
| `GET` | `/v1/messages?chat_id=gui:LabAgent&after=0&limit=100` | Ordered cursor read |
| `POST` | `/v1/send` | Idempotent text and artifact delivery |

Send request:

```json
{
  "chat_id": "gui:LabAgent",
  "task_id": "task-20260719",
  "message": "The report is ready.",
  "files": ["/absolute/repo/output/report.pdf"]
}
```

Read responses contain `items`, `cursor`, and `has_more`. Each item includes a
monotonic cursor, message ID, observed time, text, ingest status, transport, and
chat ID. Advance the consumer cursor only after processing the returned items.

## Delivery Guarantees

The relay is a closed loop, not a fire-and-forget GUI macro:

```text
authenticated client -> exact-chat poll -> durable ingest -> isolated worker
-> verified compose -> verified send/history -> durable delivery ledger
```

`status` reports `closed_loop_state` as `login_required`,
`chat_verification_pending`, or `ready`. Only `ready` may recover an expired
outbox item or deliver worker output.

- Exact configured group names are matched; unknown or ambiguous targets fail.
- The first visible history is seeded, not replayed, after setup or recovery.
- Before every poll, the conversation is moved to its live tail so a scrolled
  history cannot be mistaken for new input.
- After all new records are durably ingested, persist the inbound viewport
  checkpoint before attempting any acknowledgement send. If WeCom accepts a
  message but GUI verification is uncertain, the next poll must not re-ingest
  the request or send the acknowledgement again.
- Incoming grey bubbles are located visually, then read with WeCom's native
  context-menu Copy action and `CF_UNICODETEXT` through the Wine clipboard.
  This preserves case and digit-bearing identifiers such as `col1a1` exactly.
- The sender label immediately above each inbound bubble is normalized into a
  private visual fingerprint. That fingerprint, rather than fallible OCR text,
  keeps per-member state such as accumulated `#daily` interests isolated.
- Native Copy always dismisses its context menu before releasing the GUI lock.
  Every outbound transaction also clears stale transient menus before touching
  the composer; otherwise a visible popup can intercept paste and Send clicks.
- OCR is a bounded fallback only. Mixed, Chinese, and identifier-oriented
  passes may recover a failed copy, but OCR-derived text is never allowed to
  overwrite a successful native copy.
- Unicode text is pasted through a native Wine clipboard helper, read back from
  the composer, and recorded only after the composer clears on Send. Composer
  select-all plus paste/copy are emitted in one X11 key command so Wine cannot
  drop focus between short-lived key processes.
- Use visible X11/VNC pointer navigation. The local Wine helper may emit normal
  SendInput keystrokes only for the focused composer; it does not post private
  messages into proprietary windows. Never send a blind `Escape`: it can close
  the main client or trigger another verification cycle. Context menus are
  dismissed with a neutral pointer click.
- If Wine recognizes a visible conversation row but ignores its pointer click,
  the relay locates the selected row from WeCom's blue highlight, locates the
  target row with OCR, and uses bounded normal `Up`/`Down` plus `Return`,
  followed by the same exact-title verification.
- Submit a verified composer with WeCom's `Alt+S` accelerator. The visible Send
  button is not used as the sole control because Wine can render it while
  ignoring an X11 click; empty-composer or exact-history verification remains
  mandatory before recording delivery.
- Detect login, QR, and abnormal-device security screens before any GUI input.
  While one is visible, report `security_verification_required`, leave the
  client process untouched, and defer all intake and delivery.
- The client supervisor treats every existing WeCom process as the sole owner
  of the persistent profile. Hidden/layered/security windows are not restart
  signals, and process crashes use bounded exponential relaunch backoff.
- Files must be regular, allowlisted artifacts inside this repository. One file
  is hard-linked or copied into a private one-file C-drive directory, selected
  through `More -> File -> Local File`, checked by a visible filename prefix in
  that isolated directory, and then checked by exact full-name readback from the
  picker's `File name` field. The Wine client truncates long composer/history
  labels, so the later checks combine the already-proven picker identity with a
  visible filename prefix and a newly appearing attachment card; they do not
  demand an impossible untruncated label. Typing a full path alone is not
  selection. The relay navigates to the directory, selects its sole row, clicks
  the picker's Send button to stage it, then separately clicks the composer's
  Send button and verifies a new chat-history item. Drag-and-drop is not a
  delivery fallback.
- Wine WeCom may ignore the X11 click that opens `More`. That single click uses
  the controlled `wecom_win32_input` `SendInput` helper. If an interrupted send
  left native pickers, document hosts, file-error `Reminder` windows, or the
  exact `SearchResultWindow2` or an accidentally retained `Start Group Chat`
  window behind, the same helper closes only those exact WeCom-process windows
  before polling or one send retry. This cleanup runs
  before every exact-chat verification, and never restarts or logs out the
  authenticated client. It does not treat Wine's unreliable wrapper
  `IsWindowEnabled` state as readiness; exact title OCR remains the fail-closed
  gate after cleanup.
- Legitimate short comments, thanks, reactions, and conversational follow-ups
  remain available to the exact-chat route session, but do not mechanically
  receive one reply per row. The route agent may answer, combine related
  fragments, retain a message as context, or stay silent while people talk.
  Every row keeps its sender identity. A different member may steer an active
  task only through an agent-selected relation bound to that exact task ID.
  Empty, duplicate, and proven self-output rows remain silent. Because GUI OCR
  may derive a different sender fingerprint for the same bubble on adjacent
  polls, exact same-chat text repeated within 90 seconds is suppressed before
  routing.
- GUI access is serialized with a process lock. Combined text/file requests stay
  in one critical section, so concurrent workers cannot switch the target chat.
- Read cursors and send ledgers are durable SQLite state under ignored
  `.private/`; screenshots and raw events also remain private.
- Each stable GUI member fingerprint owns an independent private knowledge
  partition. Exact inbound files are archived with provenance and checksums;
  completed reports, papers, figures, and structured ideas/insights are indexed
  by the `knowledge` tmux window. An unresolved OCR sender is not silently
  merged with another member, and same-text duplicate GUI bubbles inside the
  transport debounce window create only one event.
- Route and worker prompts receive only a bounded same-member/same-chat view.
  Operators may inspect it with `labcanvas wecom knowledge status` and
  `labcanvas wecom knowledge search --member-key ...`; private databases and
  exports never belong in git or outbound chat artifacts.
- A newly registered `#daily` interest creates one source-scoped immediate
  `research_summary` task and remains eligible for future scheduled reports.
  The source message and normalized topic form its idempotency key, so OCR
  retries and repeated interests cannot create extra initial runs.
- Scheduled reports start at 06:00 `Asia/Hong_Kong` by default. Each active
  member preference row becomes one job; that member's interests are combined,
  different members are not merged, and the single worker consumes the jobs in
  deterministic sequence.
- Immediate and scheduled daily tasks have no pending or deferred-send queue
  deadline, including old rows reprocessed under legacy-expiry settings. Their
  reports must be compiled with
  LaTeX using the Nature-style research header and returned with the Markdown
  and requested source papers. If an agent turn ends after writing a complete
  report but before returning JSON, the worker recovers only that exact task's
  substantive report, compiles it, and sends the artifacts once.
- Window size is not authentication evidence. After a disconnected/login
  period, the relay waits until the normal poll can open and title-verify the
  exact allowlisted chats. Only that successful poll triggers one bounded
  outbox recovery pass. A cached or half-authenticated full-size window leaves
  the reconnect edge armed and consumes no recovery budget. The pass requeues
  at most one `send_expired` WeCom result from the previous 12 hours, only when
  it had already reached a send state. The normal worker then sends it through
  the exact-chat and idempotency ledgers. Other transports, stale backlog, and
  ordinary unprocessed requests are never replayed.

The copied request is immutable transport evidence. `wecom_ingest.py` stores it
as both `request` and `original_request`; a route model may add an advisory
worker plan but cannot replace either field. The research worker resolves
scientific letter/digit ambiguities with live search and authoritative sources
before asking a clarification question. If native copy and bounded OCR both
fail, or if the viewport changes ambiguously, the relay refuses replay instead
of guessing. Exact-title search is disabled by default and can be enabled only
in ignored local configuration. The relay never falls back to the
personal-WeChat database, GUI, or sender.

Model roles are transport-specific. WeCom fast chat and routing use
`gpt-5.6-sol` with low reasoning. Requests promoted to the durable worker select
medium, high, or xhigh from current-task difficulty. Daily research and
demanding presentation/research requests may use xhigh. The worker launcher
reads ignored local overrides but
does not inherit the older personal-WeChat model default. It passes its own
private env through `WECHAT_WORKER_ENV_FILE` when entering the shared guarded
worker, preserving transport isolation even though both transports reuse the
same task orchestrator.

## Recovery

```bash
tmux capture-pane -pt labcanvas-wecom:external-gui -S -120
PYTHONPATH=src python -m agenticapp wecom gui status --json
PYTHONPATH=src python -m agenticapp wecom client status --json
PYTHONPATH=src python -m agenticapp wecom gui restart --json
```

If `client_visible` is false, restore the Wine client and login first. A true
`client_visible` value alone is not ready state; confirm that a GUI poll opens
and title-verifies every allowlisted chat before expecting reconnect recovery.
If the client keeps a `device_environment_abnormal` warning but native file
delivery still works, the bridge may use its verified file-only fallback when
`allow_verified_file_send_during_device_warning` is enabled. This does not
clear the quarantine: text sends and inbound polling remain blocked, while each
file must pass exact native-picker identity, composer filename, and new history
card verification. QR-login and explicit security-verification states never
use this fallback.
The
supervisor only starts the normal client against its persisted profile. It
never invokes account-switch mode: a hidden layered window or crash is not
proof that authentication expired, and switching can invalidate a reusable
session. If an operator intentionally needs a fresh QR window, run the explicit
`agentic_tools/wecom_agent/scripts/wecom_windows_client.sh login` action. If a
chat is not visible, place it in the conversation list or enable the exact-title
fallback above. A pre-Send composer verification
failure is safe to retry with the same `task_id`. A failure after clicking Send
is reported as uncertain and is not retried automatically, preventing duplicate
messages or files.

The reconnect recovery defaults can be narrowed or disabled in the ignored GUI
config with `recover_expired_on_reconnect`,
`reconnect_recovery_max_age_seconds`, and `reconnect_recovery_limit`. For an
operator audit without sending, run the shared worker action against a copied
queue:

```bash
PYTHONPATH=src python agentic_tools/wecom_agent/scripts/wecom_reconnect_outbox.py \
  --queue /path/to/copied-queue.jsonl \
  --max-age-seconds 43200 \
  --limit 1
```
