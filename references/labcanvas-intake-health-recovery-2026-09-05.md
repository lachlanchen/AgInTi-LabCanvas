# LabCanvas Intake And Research Recovery

Date: 2026-09-05. Scope: personal WeChat source refresh, background chat
materialization, shared worker evidence gates, and production WeCom delivery.

## What Failed

Healthy monitor heartbeats and caught-up cursors did not prove live intake.
The decrypt refresher selected a different account directory by directory
modification time. Its keys did not match. The upstream decrypt CLI printed
database failures but exited with code zero, so the supervisor treated a stale
cache as refreshed. No new key extraction or login was necessary: the existing
private keys matched the database files opened by the running client.

Separately, a LabAgent inspiration response cited a normal Nature article URL.
The research evidence collector only recognized DOI/arXiv identifiers, and
rejected the answer as lacking fresh evidence. After DOI verification, another
overliteral gate rejected a natural statement that the causal evidence mainly
came from mice, followed by a falsifiable prediction.

Chat materialization had a third failure mode: an outer subprocess timeout
escaped before per-chat backoff was recorded. The same unavailable target was
then attempted repeatedly, taking time away from delivery.

## Implemented Changes

- `wechat_direct_backend.py` prefers an account whose database files are open
  in the current user's live WeChat process. It reads process metadata/file
  descriptor targets only; it does not control the app or inspect its memory.
  Multiple live stores require explicit `--db-dir`. The legacy discovery
  fallback remains only when no live store can be identified.
- The backend validates the upstream summary instead of trusting exit code
  zero. HMAC/decrypt failures, missing summaries, and missing required message,
  media, contact, or session keys fail closed. Optional payment/search/tip
  databases remain distinguishable from chat intake failures.
- A bounded, sanitized, atomic mode-0600 status file is written at
  `agentic_tools/wechat_gui_agent/.private/wechat_decrypt.refresh.status.json`.
  It contains counts and timestamps, not keys, account IDs, or message text.
- `wechat_decrypt_refresh_loop.sh` uses the same source selection, puts global
  `--db-dir` before the subcommand, and records success only on validated
  refresh. Successful logging is one compact summary instead of raw upstream
  diagnostics.
- `wechat_transport_stall_guard.py` checks source refresh independently of
  monitor heartbeats. Missing, invalid, failed, future-dated, or stale refresh
  evidence cannot be green just because a cursor reached the cache's end.
  Its aggregate status also propagates recent queue failures, unreadable queue
  records, and deferred file deliveries instead of reporting green while a
  child queue reports failure. This is observation, not permission to replay
  failed tasks or restart authenticated clients.
- `wechat_chat_sync_loop.py` records host timeouts as retryable failures and
  applies the same per-chat backoff as sender-reported timeouts. The timeout
  error does not dump the private command envelope into its log.
- `wechat_task_worker.py` normalizes Nature article URLs and explicit
  publisher `/doi/` URLs into DOI candidates. They still pass the existing live
  resolver; normalization does not establish that a claim is true or that the
  full paper was read. Host spoofing and unrelated paths are not Nature DOI
  matches. Candidate-aware caching permits recovery after normalization is
  improved without changing the response text.
- Research limitation checks accept falsifiability and naturally expressed
  evidence-scope limitations. The fresh-source requirement remains intact.

## Live Evidence And Limits

The recovered source cache exposed newer rows in Shares, EchoMind, and the
owner DM. The monitors subsequently advanced to those rows. Required chat
stores refreshed successfully; nine optional databases still lacked keys.
Do not describe optional database coverage as complete.

The affected LabAgent inspiration was repaired through the normal worker and
sender. The DOI resolved, the stored answer passed the corrected gates, and
WeCom recorded a verified text delivery with no files and no pending messages.
The final delivery repair did not invoke a model or repeat the research task.
Today's three WeCom daily tasks and the career/MEMO daily deliveries were
already complete; they were not replayed. EchoMind retained its six-hour
lesson interval and previous-day daily PDF schedule.

The recovered Shares request reached download/transcription, but its video
delivery encountered `WECHAT_FILE_CHOOSER_NOT_OPEN`. It remains explicitly
unresolved: deferred first, then `send_failed` after its bounded retries, never
complete. The visible client also failed a bounded chat-selection
input check. A temporary window-manager/repaint probe did not repair input and
was removed. No client restart, logout, key rescan, or phone manipulation was
used. Do not call this an all-green end-to-end WeChat audit until the guarded
sender verifies the remaining delivery. Keep this distinction when handing off.

## Recovery Procedure

1. Read queue and delivery records before touching processes. A completed
   schedule is not permission to replay its reports.
2. Check source-refresh evidence as well as monitor heartbeats. Match the
   live account through process metadata or an explicit private `--db-dir`;
   never choose a recent account folder blindly.
3. Use existing private keys. Do not print them or restart authenticated
   clients merely because decryption fails.
4. Reload only idle affected workers/background loops. Do not restart the
   GUI, Tiny11 VM, phone mirror, or another project's browser.
5. For a completed answer rejected by a corrected result contract, use
   `repair-result` on its exact queue/task ID before considering an agent rerun.
6. Verify `status=done`, coverage, sender evidence, and empty pending delivery
   lists. When delivery cannot be verified, retain a deferred record and state
   the precise blocker rather than sending repeated apologies or diagnostics.

```bash
PYTHONPATH=src python -m agenticapp wechat health --json
PYTHONPATH=src python -m agenticapp wecom gui status --json
PYTHONPATH=src python -m agenticapp wecom daily status --json

# Only for an exact pending delivery after its contract has been repaired:
PYTHONPATH=src python -m agenticapp wechat worker repair-result TASK_ID \
  --queue PRIVATE_QUEUE --send
```

`repair-result --send` is a real external send, not a diagnostic probe. Keep
the source task's authorization and existing idempotency record. Do not use it
to repeat an already delivered item.

## Regression Checks

```bash
PYTHONPATH=src python -m unittest discover -s tests -p test_wechat_direct_backend.py
PYTHONPATH=src python -m unittest discover -s tests -p test_wechat_chat_sync_loop.py
PYTHONPATH=src python -m unittest discover -s tests -p test_wechat_transport_stall_guard.py
PYTHONPATH=src python -m unittest discover -s tests -p test_wechat_task_worker.py
bash -n agentic_tools/wechat_gui_agent/scripts/wechat_decrypt_refresh_loop.sh
```

Tests cover live-account selection over unrelated directory modification times,
ambiguous stores, upstream zero-exit failure, missing required versus optional
keys, private status permissions, refresh freshness and malformed state,
timeout backoff, publisher DOI normalization, untrusted URL forms, recovery of
cached zero-candidate results, and natural research limitations.

Screenshots, exact source/task IDs, queue history, and delivery receipts stay
under ignored private/output paths. Never commit raw chat history, credentials,
source-account paths, or copied media as evidence for these fixes.

Validation: 677 targeted unit tests passed across the four suites above, plus
the complete LabCanvas worker self-test and shell syntax check. Only idle
background workers, the refresh loop, chat sync, and the health guard were
reloaded. Client authentication sessions were preserved.
