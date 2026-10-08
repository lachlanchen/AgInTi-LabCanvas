# Native WeChat Search and Reply Stall Recovery

## Observed Failure

The Windows WeChat receiver and client heartbeat were healthy while replies
were not being delivered. Saved answers had reached `send_expired` after the
sender refused to overwrite existing composer text. Screenshots showed a chat
search query in one composer and a LabCanvas clipboard-probe marker in another.
Neither is proof of a successful response; a live process is not delivery proof.

An additional health-check fault classified a valid JSONL queue as corrupt.
Python `str.splitlines()` splits Unicode U+2028/U+2029 inside JSON strings.
The worker already had a local LF-only reader fix; the health readers now use
the same record boundary. Queue data must not be deleted to silence that alarm.

## Reusable Fix

- Native chat search opens from the sidebar. Before typing, the bridge verifies
  the focused search-field outline in the native header. It no longer assumes
  Ctrl+F moved focus out of the composer or a docked browser.
- Search-result coordinates follow the observed field. A native contact/group
  category and the exact final conversation title are still required. Web search
  suggestions do not authorize selecting or sending to a conversation.
- A complete owned draft can be recovered only with matching chat/account/table
  binding and no submission intent. The exact probe marker tied to that journal
  key can also be recovered, using a different verification sentinel to prevent
  an unchanged clipboard from passing. Unknown text, edits, attachments, and
  uncertain submitted content remain protected.
- Queue health, delivery health, and backend-failure inspection parse JSONL using
  literal LF boundaries, retaining Unicode line separators inside string values.
- A current login screen is an authentication blocker, not a stale-store fault.
  Report that blocker once; do not launch a repair agent for its dependent
  source-refresh failure. A genuinely stale or unavailable store still raises
  the normal critical fault.

## Recovery Order

1. Inspect receiver timestamps, task outcomes, and native client state. Do not
   restart or log out a healthy client as a generic repair.
2. Capture private evidence of the current composer. Recover journaled owned
   drafts only. Preserve unjournaled drafts before any operator-authorized clear.
3. For a completed but unsent answer, use the existing `resend_task_result` or
   CLI resend path with the original task identity. Do not rerun the agent,
   reset all cursors, or replay the historical queue.
4. Verify a native outbound row and the exact-chat mirror event. A completed
   command or disappearing composer alone is insufficient.
5. Reload only WeChat monitors/workers through `wechat_supervisor_tmux.sh
   reload-workers`. This keeps the Windows client and profile intact. Leave
   paused WeCom and passive Android mirrors unchanged.
6. If the client changes to `entry_required`, stop live input and report the
   existing noVNC login surface. Do not claim service is fully restored until
   login and an actual delivery are verified.

## Validation and Limits

The targeted native bridge/draft/image tests passed (72), the transport-health
tests passed (72), and the worker tests passed (621). A stored article reply was
recovered once and confirmed by the native outbound row and mirror ledger.
After that send, the existing Windows client changed to `entry_required` while
another group's draft was being inspected. No client restart, logout command,
account change, or profile replacement was performed. The cause of that login
transition is not established by this repair.

After the owner completed login, the live client reported `ready` and all seven
direct monitors were healthy with fresh heartbeats. The native source refreshed
normally; the queue had no invalid records or active/stale tasks, and the full
health snapshot had no issues. The exact stray search-query draft was privately
quarantined and cleared only after text and file-clipboard checks. The historical
expired replies were not replayed. WeCom GUI/Android transports and enrolled
daily groups remained disabled, and no phone input was performed.

The supervisor reloaded the changed shared health guard automatically. Login
recovery is verified for this incident, not a guarantee that the provider will
never request authentication again.

Private GUI evidence stays under the existing ignored Tiny11 runtime directory.
No private chat text, credentials, screenshots, or queue exports belong in git.
