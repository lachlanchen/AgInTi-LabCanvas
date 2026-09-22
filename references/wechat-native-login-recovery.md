# Windows WeChat Login And Queue Recovery

## Failure Signature

A message can be received and queued successfully, yet have no visible reply:
the Windows client may lose its authenticated session before native card
retrieval or delivery. A readable decrypted cache, live process, and responding
SSH/helper endpoint do not establish that WeChat is logged in.

The September 2026 incident had two separate failures: source retrieval failed,
then reply delivery failed. A generic `Tiny11 helper unavailable: HTTPError`
hid the second failure. The console showed the account-security login prompt.
Do not infer a router/parser failure, silence in a video, or missing source
content from that transport failure.

## Persistent Contract

- The authenticated helper reports `helper_ready` independently of `ok`, which
  continues to mean a visible main client window exists. Supervisors do not
  restart a responsive helper just because a client needs login.
- For personal WeChat, `client_state` distinguishes `ready`, `window_hidden`,
  `entry_required`, `window_unavailable`, and `client_unavailable`. Login
  recognition requires the observed portrait Qt login surface and absence of
  a main window, including hidden main windows. An arbitrary missing window is
  not sufficient evidence of logout. Future client changes may need a new
  observed detector; do not relax this into guessing.
- Restore/input requests at that login surface return `WECHAT_ENTRY_REQUIRED`
  before any hotkey or click. HTTP errors preserve bounded JSON error details
  privately; raw HTML responses and the bridge token are not exposed.
- The native mirror records `client_state`. Only a fresh observation can
  request human login. The console is `http://127.0.0.1:6143/`.
- With Windows selected, deferred personal-WeChat deliveries use its readiness,
  not the old Ubuntu watchdog or Android connection. Login-deferred replies
  wait without spending send attempts until Windows is ready again. Existing
  delivery expiry and receipt/deduplication policies remain unchanged.
- These changes do not resume paused WeCom groups, launch another client,
  control Android, dismiss security prompts, or reset ingestion cursors.

## Recover One Task

1. Inspect the exact source message and task, separating reception, media
   retrieval, backend execution, and delivery evidence.
2. Check native health and the console. Let the account owner complete login
   when the client requires it. Preserve the client process and history.
3. If work completed and only delivery failed, use the existing deferred
   delivery/receipt reconciliation path. Do not regenerate completed work.
4. If media retrieval itself failed, retain the original failed task. After
   confirmed login, reprocess only that task using `wechat worker reprocess`.
   Do not send the old source-unavailable answer as if recovery succeeded.
5. Verify exact-card identity, the original downloaded media, transcript, and
   same-chat delivery receipts before marking success. Never bulk-replay old
   failures or successful schedules after login.

## Verification

Regression coverage lives in `test_wecom_tiny11_transport.py`,
`test_wechat_session_preservation.py`, and `test_wechat_task_worker.py`.
It covers login-error preservation, non-JSON error redaction, helper readiness
independent of client readiness, fresh versus stale login observations, and
delivery waiting without probing inactive Android. Run `npm test` for the
isolated full suite. A login-blocked live probe is not a successful end-to-end
media delivery test; verify that separately after login.
