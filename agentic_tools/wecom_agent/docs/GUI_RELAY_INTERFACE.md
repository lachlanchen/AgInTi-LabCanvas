# WeCom GUI Relay Interface

The GUI relay is a localhost-only transport for explicitly allowlisted external
WeCom groups when Tencent does not grant the tenant's official `wecom-cli msg`
permission. It controls only the isolated WeCom Wine client. It never reads or
sends through personal WeChat.

## Setup and Lifecycle

```bash
PYTHONPATH=src python -m agenticapp wecom client start --json
PYTHONPATH=src python -m agenticapp wecom gui init --chat LabAgent
PYTHONPATH=src python -m agenticapp wecom gui restart --json
PYTHONPATH=src python -m agenticapp wecom gui status --json
```

The ignored config is
`agentic_tools/wecom_agent/.private/wecom_gui_bridge.local.json`. It contains
the exact group allowlist, display, state paths, localhost port, and bearer
token. The relay runs in the `labcanvas-wecom:external-gui` tmux window and is
restored by the normal WeCom tmux launcher. The default viewer is:

```text
http://127.0.0.1:6192/vnc.html?host=127.0.0.1&port=6192&autoconnect=1&resize=scale
```

## Stable CLI

```bash
# List stable target IDs.
PYTHONPATH=src python -m agenticapp wecom gui chats --json

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

- Exact configured group names are matched; unknown or ambiguous targets fail.
- The first visible history is seeded, not replayed, after setup or recovery.
- Before every poll, the conversation is moved to its live tail so a scrolled
  history cannot be mistaken for new input.
- Incoming grey bubbles are located visually, then read with WeCom's native
  context-menu Copy action and `CF_UNICODETEXT` through the Wine clipboard.
  This preserves case and digit-bearing identifiers such as `col1a1` exactly.
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
- Files must be regular, allowlisted artifacts inside this repository. One file
  is staged at a time, dragged from an isolated Wine Explorer window, checked by
  filename in the composer, and checked again in chat history before delivery is
  recorded.
- GUI access is serialized with a process lock. Combined text/file requests stay
  in one critical section, so concurrent workers cannot switch the target chat.
- Read cursors and send ledgers are durable SQLite state under ignored
  `.private/`; screenshots and raw events also remain private.

The copied request is immutable transport evidence. `wecom_ingest.py` stores it
as both `request` and `original_request`; a route model may add an advisory
worker plan but cannot replace either field. The research worker resolves
scientific letter/digit ambiguities with live search and authoritative sources
before asking a clarification question. If native copy and bounded OCR both
fail, or if the viewport changes ambiguously, the relay refuses replay instead
of guessing. It does not search for chats by default and never falls back to
the personal-WeChat database, GUI, or sender.

## Recovery

```bash
tmux capture-pane -pt labcanvas-wecom:external-gui -S -120
PYTHONPATH=src python -m agenticapp wecom gui status --json
PYTHONPATH=src python -m agenticapp wecom client status --json
PYTHONPATH=src python -m agenticapp wecom gui restart --json
```

If `client_visible` is false, restore the Wine client and login first. If a chat
is not visible, place it in the conversation list; search remains disabled by
default to avoid opening the wrong group. A pre-Send composer verification
failure is safe to retry with the same `task_id`. A failure after clicking Send
is reported as uncertain and is not retried automatically, preventing duplicate
messages or files.
