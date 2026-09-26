# Recovering An Unsent WeChat Draft

## Incident

A group image reached the ledger, was saved, and was analyzed. The immediate
acknowledgement hit a transient Windows helper timeout after its text had been
pasted but before a durable Enter intent existed. The completed answer then
hit the existing-draft guard. Bounded retries expired, while the health check
treated the terminal expired outbox as healthy. The result looked like an
ignored message even though analysis was complete.

The verified orphan acknowledgement was privately preserved and cleared. The
existing worker resend routine delivered the saved answer, with native local
and nonzero server receipt IDs and sent status. Analysis was not rerun, and no
duplicate acknowledgement, publication, or test message was sent.

## Persistent Recovery

The personal Windows WeChat sender now records one text-draft ownership entry
per exact chat in its ignored SQLite runtime, before the first paste. It binds
the full text, delivery key, chat, native message table, account sender, and
creation time. This is separate from the existing post-composition Enter
intent: a paste timeout is not proof that Send was attempted.

Before refusing a nonempty composer, both text and file delivery may recover
an owned text draft, but only when:

- The current exact conversation and account binding match the journal.
- Full native composer readback matches the recorded text.
- The copied composer contains no file attachment.
- No Enter intent exists for that draft's delivery key.
- Clearing the owned draft leaves a verified empty composer.

Rebuild the current reply after recovery. A completed result can therefore
replace its abandoned acknowledgement without sending the stale acknowledgement
first. Changed text, partial drafts, unknown drafts, cross-chat/account records,
and added attachments remain untouched. An existing submission intent requires
receipt reconciliation, never blind clearing or retrying. Existing sent-key,
pending-echo, and outgoing-row guards remain authoritative.

Recent `send_expired` tasks remain visible as delivery failures in queue health.
This is diagnostic only: expiry does not trigger an unbounded backlog replay.
The existing bounded alert window still excludes historical expired tasks.

## Verification

Regression tests simulate a timeout after accepted paste, recovery for the same
reply and a later answer, duplicate suppression, protected human edits, partial
drafts, account/chat mismatch, added files, malformed journals, and post-Enter
uncertainty. Separate health tests cover recent expiry, successful backfill,
and old backlog without modifying queue state.

A live unsent draft test used the existing Windows helper and serialized GUI
lock. Exact readback passed, the ownership routine cleared the draft, and the
composer was verified empty. Keep screenshots, draft text, task IDs, and native
receipts private; reusable code and these operational rules are the handoff.
