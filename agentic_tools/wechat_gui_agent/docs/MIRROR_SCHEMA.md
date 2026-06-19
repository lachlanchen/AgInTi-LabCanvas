# WeChat Mirror Schema

The mirror database is local-only and ignored by git:

```text
agentic_tools/wechat_gui_agent/.private/wechat_mirror.sqlite
```

It is an evidence log, not a replacement for WeChat history. Screenshots remain
the source of truth when OCR or GUI targeting is uncertain.

## Tables

### `chats`

One row per chat/contact/group seen by the automation.

| Column | Meaning |
| --- | --- |
| `id` | Internal integer key. |
| `name` | Human-readable chat name used by the plan. |
| `query` | Search query used to find the chat, when available. |
| `created_at` | First time the mirror saw this chat. |
| `last_seen_at` | Last recorded automation event for this chat. |

### `events`

Raw automation actions and evidence.

| Column | Meaning |
| --- | --- |
| `action` | `open`, `send`, `read`, or `create_group`. |
| `direction` | `outbound`, `inbound`, or blank for non-message actions. |
| `message` | Explicit outgoing text, when applicable. |
| `status` | Action result such as `sent`, `dry-run-opened`, or `captured`. |
| `screenshot_path` | Evidence image under `output/wechat_gui_agent/`. |
| `ocr_text` | Page-level OCR from a read capture. |
| `metadata_json` | Target click offsets, plan data, or other context. |

### `messages`

Searchable text derived from events.

| Column | Meaning |
| --- | --- |
| `event_id` | Source event. |
| `direction` | `outbound` for sent text or `screen_ocr` for OCR captures. |
| `body` | Message text or page-level OCR text. |
| `status` | Source event status. |
| `screenshot_path` | Evidence image for the text. |
| `observed_at` | Time the source event was recorded. |

## Common Commands

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_mirror.py list --limit 20
python3 agentic_tools/wechat_gui_agent/scripts/wechat_mirror.py list-messages --limit 20
python3 agentic_tools/wechat_gui_agent/scripts/wechat_mirror.py backfill-messages
python3 agentic_tools/wechat_gui_agent/scripts/wechat_mirror.py export-json \
  --output agentic_tools/wechat_gui_agent/.private/wechat_mirror_export.json
```

Use `screen_ocr` rows for quick review only. For important reads, open the linked
screenshot and verify the text visually.
