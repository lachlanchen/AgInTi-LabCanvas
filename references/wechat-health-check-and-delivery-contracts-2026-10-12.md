# WeChat Health and Delivery Contracts

## Findings

A fresh client heartbeat and an empty active queue did not prove end-to-end
health. The Windows client was logged in, all seven receivers were polling, and
the career/MEMO daily PDFs had verified deliveries. Three other paths were wrong:

1. An explicit company cost-analysis request was silently skipped because the
   intake filter matched the bare word `token`. That word also names the normal
   unit of model usage. The agent never received the request.
2. EchoMind retained a September lesson for 89 delivery attempts. Windows had
   already sent it, but the scheduler expected a screenshot filename while the
   selected transport returned JSON. Duplicate suppression correctly prevented
   repeated messages, but returned an empty result, so the scheduler never
   completed that lesson. Backoff hid the stall from the health check.
3. A research preview PNG was sent as a native image row, not an ordinary file
   row. Receipt matching handled text, files and video, but omitted images.
   The original PNG MD5 exactly matched the server-confirmed outgoing image row.

## System Fixes

- Remove bare `token` and its Chinese equivalent from the silent intake filter,
  including legacy configuration lists. Agent reasoning handles their meaning;
  this does not grant access to secrets or authorize external actions. Explicit
  credential and destructive-command gates remain unchanged.
- A duplicate native text send now returns a verified durable-ledger receipt
  without GUI input or another outbound event. Never treat empty `ok=true` as
  delivery evidence.
- EchoMind accepts verified native receipts as well as the legacy existing
  screenshot-path contract. Errors, empty receipt lists and unverified entries
  fail closed. Recovery clears the pending lesson through the normal scheduler
  state transition; no cursor reset or historical lesson replay is needed.
- Native image receipts require the original file's exact MD5, the existing
  exact-chat/account binding, a post-intent row and a confirmed server ID.
  A visually similar thumbnail or nearby file is not proof.
- Repeated lesson backoff can no longer hide a pending item older than two
  configured intervals. Quiet hours and an active bounded send remain respected.
- Direct-chat unit tests explicitly disable the live Windows transport. A
  developer's private enabled configuration must not turn unit tests into sends.

## Recovery and Verification

Use existing exact-row replay and native receipt reconciliation routines. Do
not hand-edit the queue, regenerate completed artifacts or upload them again.
The missed question was replayed through the normal group agent using its exact
local row and an isolated recovery cursor; the live receiver cursor was not
rewound. Its acknowledgment was delivered and the worker resumed the task.

The old EchoMind lesson was reconciled from its durable delivery receipt with
no duplicate message. The previous image task was reconciled from its native
hash receipt and returned to `done`; no second image upload was needed.

The targeted suites cover native bridge/media/draft behavior, direct routing,
EchoMind scheduling and transport health. They passed 387 tests. Reload only
the changed monitors/workers and the lesson scheduler, retaining the logged-in
Windows client/profile. Leave paused WeCom and passive phone mirrors alone.

Private chat text, source IDs, task records and GUI evidence remain under the
ignored runtime directories. This note intentionally contains no chat payloads.
