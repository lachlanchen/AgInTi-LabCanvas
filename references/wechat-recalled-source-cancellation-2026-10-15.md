# Recalled WeChat Source Messages

## Observed Gap

A Channels card was withdrawn in personal WeChat while its worker task was
running. The native store replaced the original row in place: the local ID
and server ID were unchanged, but the message became type 10000 with
`<sysmsg type="revokemsg">`. A cursor that only watches new local IDs does not
see that mutation as a new event. The queued task still held the original XML.

## Shared Worker Rule

`wechat_task_worker.py` now checks the primary source's current native row:

- Match the exact database, allowlisted-format table, local ID and nonzero
  server ID. A source chat mismatch is rejected.
- Require a native system message type and an actual `revokemsg` XML event.
  Ordinary text mentioning recall, quoted XML, missing rows, another message,
  or an unavailable database is not proof of withdrawal.
- Check before starting work, before a backend retry, after source preflight,
  after backend completion, and before delivery. Recheck between outgoing files
  and text parts, and do not retry or fall back to Android after recall.
- Mark the exact unfinished task `canceled`, record private recall evidence,
  and increment its execution generation under the existing queue lock. Late
  worker writes cannot revive it or deliver stale artifacts.
- Leave other queued sources alone. Do not reply to the recall notification
  or ask the user to resend the withdrawn card.

The rule is shared by personal-WeChat source-backed worker tasks, not a
Channels-title keyword rule. WeCom remains separate and unchanged.

## Limits

An already-running network/model step may finish before the next checkpoint;
its result must not be delivered afterward. The rule cannot undo a message or
file already delivered, an already accepted external publication, or an action
that races with a recall not yet present in the local native store. It does
not delete local media, rewrite completed delivery receipts, or imply a remote
WeChat recall succeeded. Explicit deletion or removal of an existing public
post is a separate authorized action.

The live withdrawn Channels task was cancelled before any artifact delivery.
Its former worker later recorded `stale-generation-delivery-suppressed`, proving
that its old execution could not send or overwrite the cancellation. Other
source tasks continued independently. Private queue evidence retains exact
IDs; no recalled content is copied into this document.

Regression tests in `tests/test_wechat_source_recall.py` cover exact identity,
false recall text, missing databases, cross-chat/source mismatches, generation
invalidation, unrelated queued cards, completed-receipt preservation, backend
suppression, and withdrawal between delivery parts.
The nine recall-specific tests passed, along with the full local `npm test`
suite (2,342 tests, 16 skipped). Both idle personal-WeChat worker processes
were reloaded without restarting the native client or touching WeCom.
