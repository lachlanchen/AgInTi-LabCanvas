# WeCom File Retry Loop Repair

## Incident And Cause

LabAgent repeatedly received daily PDFs after the transport recovered. This
was not intentional backfill or a model deciding to send more reports.

Three transport/queue problems combined:

1. Native Tiny11 history OCR used 72% of a conversation surface. In the tall
   1276 x 1392 WeCom window, this omitted the newest outgoing file cards above
   the composer. Incoming-message extraction used the same incorrect
   percentage assumption.
2. `WECOM_GUI_SEND_UNCERTAIN` became `gui_postcommit_uncertain` in the deferred
   queue. Although an existing test claimed uncertainty was not retried, it
   only tested classification. The next queue claim retried it without a cap.
   Daily research intentionally has no fixed execution deadline, so task TTL
   did not stop this loop. Some legacy retry counters exceeded 1,000; these
   counters include failed/blocked attempts and are not delivered-file counts.
3. GUI file receipts were only recorded after successful history OCR. There
   was no durable pre-Send attempt record. A failed receipt check therefore
   left the next caller free to send the same file again. Receipt keys also
   depended on file path, mtime, and array index.

## Corrected Contract

- `wechat_task_worker.py` records ambiguous post-Send delivery as
  `send_uncertain`, not a retryable transport outage. It retains the result and
  artifacts without marking them delivered or failed research.
- Normal claims and reconnect recovery hold legacy uncertain tasks. A
  delivery-status lookup can reconcile existing receipts, but uncertainty
  never authorizes another `/v1/send` call.
- `wecom_gui_bridge.py` commits `file_send_attempts` in SQLite before the Send
  input. If the process dies, input times out, or history verification fails,
  the attempt remains. Repeating the request returns uncertainty without
  clicking, staging, or sending again.
- New file keys bind exact chat, task, and SHA-256 of the file contents.
  Renaming, restaging, touching, or reordering the same file does not create
  another delivery. Existing verified legacy receipts remain readable.
- A newly requested send under a different task is separate. Content identity
  does not suppress a legitimate future request or leak between chats.
- Tiny11 history now extends to the fixed native footer rather than a fraction
  of the window height. Composer verification excludes chat history. These
  coordinates are for the dedicated console's verified 100% Windows DPI;
  changing DPI or manually resizing the composer requires checking the crops.

An attempt record is not a success receipt. Do not clear it on an error, infer
success merely from a counter, or rename the file to evade the hold. Verify
exact same-chat evidence before repairing a receipt. A truly unsent file needs
an explicit, evidence-based retry, not periodic blind replay.

## Recovery Without Sending

Preserve a private copy of the queue before migration, then run:

```bash
python3 agentic_tools/wechat_gui_agent/scripts/wechat_task_worker.py \
  --queue agentic_tools/wecom_agent/.private/wecom_task_queue.jsonl \
  --hold-uncertain-sends
```

This command sends nothing, holds only ambiguous send states, preserves
artifacts/results, and increments the task execution generation so a stale
worker cannot overwrite the hold. Repeating it is a no-op. It does not cancel
fresh human requests or disable future daily schedules.

Eleven legacy tasks were held during this incident. Their files remain local.
The native Windows clients were not restarted or logged out. Reload the host
GUI relay while holding its existing GUI lock; reload the worker only at an
idle task boundary. Do not reset private queues or delivery databases.

## Verification

Private before/after screenshots from a real failed receipt were reprocessed
without any new chat send. The old crop counted the file 1 before and 1 after;
the corrected crop counted 1 before and 2 after. This proves the missed tail
caused a false-negative receipt for that recorded send.

Regression coverage exercises:

- an uncertain send followed by repeated real queue claims;
- legacy daily tasks with high retry counts and no fixed deadline;
- idempotent migration and rejection of stale in-flight queue writes;
- durable attempt recording before the Send input;
- retry after process recreation and file rename, with zero further GUI input;
- exact-chat/task isolation and backward-compatible success receipts;
- history/composer crop boundaries in short and tall native windows.

Private evidence: `output/wecom-delivery-repair/20260913/`.
Do not commit raw queue backups, chat screenshots, tokens, or private files.
No diagnostic PDF or apology is sent to the group as part of this repair.
