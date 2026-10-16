# Login-Aware WeChat Intake Recovery

## Incident and Evidence

The native personal-WeChat client displayed "For account security, log in
again." All seven receivers and both task workers were alive; the blocked
client prevented fresh intake and delivery. This was not the Channels-card
recall cancellation added the previous day. After the owner completed login,
the same client became input-ready and Shares intake advanced automatically.

A read-only Windows audit found one signed personal-WeChat root process, no
client crash or resource-exhaustion event in the preceding day, normal helper
memory, eleven native browser processes, and running Windows Time. The client
process was not restarted during the audit. These checks do not identify
Tencent's security trigger or prove that a future re-login cannot occur.
Private evidence is stored under the existing ignored environment-health
directory, mode 0600. No account, profile, vendor binary, security setting,
Android input, WeCom pause, or publication permission was changed.

## Concrete Gap

The store receiver exported the native database over SSH/SFTP before checking
client availability. Even on a verified login screen it repeated that work,
refreshed `last_sync_epoch` against an unchanged cache, and overwrote its
native-state observation. The ordinary log printed inserted rows/errors but
not login transitions, so the exact sign-out time was not retained.

## Shared Fix

`wechat_tiny11_bridge.py` now checks the selected native helper before export.
A verified login screen, missing client, unresponsive client, or unavailable
helper defers database work. The loop performs only its read-only readiness
probe every ten seconds in that state. It neither focuses the GUI nor clicks
login, re-extracts keys, restarts clients, or changes accounts.

`last_probe_epoch` is separate from `last_sync_epoch`: a fresh client check
cannot make an old database current. `wechat_transport_selection.py` requires
both freshness checks for readiness, while a fresh verified login observation
still identifies a human-action blocker even when the database is old. Legacy
state files remain readable through their existing timestamp field.

The existing private status file retains at most sixteen native state
transitions and the last transition time, not chat content. Repeated identical
blocked polls update the observation without growing history or log output.
Missing helper access clears current readiness rather than refreshing a cached
login diagnosis. This is private diagnostic evidence, not a group notification.

After login, the next poll resumes export with the existing cursors. Native
rows retain their exact identities and are upserted, not emitted as new rows.
The receiver checks readiness again after export to handle a login change
during the operation. Existing guarded delivery, task generations, receipt
reconciliation, recall checks, and bounded recovery remain authoritative.
This patch does not drain old task backlogs or resend completed artifacts.

## Verification and Deployment

Regression tests in `tests/test_wechat_login_recovery.py` cover deferred
remote work, unchanged cache/cursors, missing helper and wrong-app responses,
re-login without duplicate rows, login loss during export, independent
freshness, bounded private transition history, and log deduplication.

Use `npm test` for isolated tests; never point a test fixture at the production
mirror. `ingest_export` accepts an explicit database path, and the receiver
passes its current store path explicitly.

Reload only the store receiver and idle Python consumers after tests. Keep
active worker tasks running, preserve the client's process/profile, and leave
paused WeCom and passive phone mirrors unchanged. Verify both fresh native
readiness and cursor progress; a running process alone is not proof of chat
delivery. Do not deliberately sign out the live account to test recovery.

If the vendor prompt returns, preserve its actual category and timestamp,
compare the transition history with task operations, and follow
[the existing security investigation](wechat-wecom-security-root-cause-2026-10-01.md).
This fixes avoidable receiver work and missing diagnostics, not Tencent's
undocumented account-security decision.
