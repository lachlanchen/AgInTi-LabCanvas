# Verified Completion Repairs Must Supersede Failed Attempts

## Observed Failure

A personal WeChat research task timed out during its first backend attempt.
The completion checker then requested one corrective turn. That turn returned
a substantive answer and the second coverage audit confirmed that the request
was covered. Nevertheless, the worker sent a terminal failure notice instead
of the answer.

Two stale fields caused this:

- `merge_completion_results()` copied the first result's `private_failure`
  into the corrected result.
- The task retained `worker_result_exhausted=true` from the first attempt.

The final delivery stage correctly rejects failed results, but was receiving
failure state belonging to an older attempt. More retries, a new prompt, or a
WeChat restart would not address this state transition.

## Durable Fix

`agentic_tools/wechat_gui_agent/scripts/wechat_task_worker.py` now:

1. Rejects a completion correction that itself has a private failure.
2. Treats the corrective result's failure state as authoritative, just as its
   file list is authoritative. An earlier private failure cannot contaminate
   a usable replacement.
3. Clears exhausted/error state only after a usable correction passes complete
   coverage checks with no unresolved source items. It records the superseded
   failure in `worker_failure_recovery`; earlier attempt evidence remains.
4. Requires actual successful recovery evidence before recording
   `repair_succeeded`. An unavailable or incomplete audit is not success merely
   because its `missing` array is empty.
5. Applies the same failure-state cleanup to an explicitly requested stored
   result repair after its current response/artifact checks pass.

Incomplete coverage, rejected artifacts, no-reply results, and current backend
failures retain their guards. This does not authorize additional publication,
new research, or replay of historical queues.

## Recovery Procedure

For an identified failed task whose stored `result.raw` contains a completed
answer, use the existing routine:

```bash
PYTHONPATH=src python -m agenticapp wechat worker repair-result TASK_ID --send
```

This reapplies the current contract and reader-quality checks, then uses the
normal exact-chat sender. It does not invoke the model or repeat the original
research/tools. Verify both the task's stored repair receipt and native
outbound message rows. A second call with the same result must be a no-op.

Do not batch replay old failures. First inspect their exact source, current
task state, previous deliveries, and whether the requested work is still
relevant. Keep raw task records, chat text, and transport IDs private.

## Live Verification

- The affected answer was recovered through the routine and marked `done`.
- Native WeChat outbound rows verified delivery of two distinct text chunks;
  these were the two parts of one long answer, not duplicate answers.
- Calling the recovery again returned `same_repaired_result_already_sent`.
- No extra model turn, browser login, client restart, or phone control occurred.
- Only the two idle personal WeChat workers were reloaded. The WeChat client
  stayed logged in; WeCom remained paused and untouched.
- The post-recovery health check reported seven ready/caught-up personal chat
  monitors and no recent failed, blocked, or stale worker task.

## Regression Coverage

`tests/test_wechat_task_worker.py` covers timeout -> complete repair -> real
answer delivery, failed corrections, unavailable audits, incomplete artifact
coverage, current private failures, stored-result cleanup, and repeated-send
deduplication. The focused worker suite passed 620 tests. The full `npm test`
run passed 2,227 tests with 16 optional skips.

## Separate Remaining Limitation

This change fixes reply delivery, not every source retrieval problem. A recent
Channels card successfully reached native link extraction but its downstream
media resolver rejected the content. Preserve that exact card/link candidate
for bounded resolver recovery; do not describe it as a missing user message,
ask the user to resend the card, or claim an MP4 was downloaded without one.
