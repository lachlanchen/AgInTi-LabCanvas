# Native WeChat Delivery Verification

## Incident And Boundary

A user supplied a URL after an unrelated, failed Shipinhao card request. The
URL entered the per-chat queue, its original video and transcript were produced,
and its source knowledge was retained. It did not fail at intake or download.
The sender could not verify the native file chooser, so required-file delivery failed.
The final message claimed attachments were included; the files-first gate
correctly withheld that message. Queue expiry was not transport recovery.

Separate investigation found false positive text receipts: the sender's mirror
recorded `sent`, but neither the exact native chat history nor the visible chat
contained the reply. The old check copied the composer without first replacing
the clipboard. If WeChat ignored Ctrl+C, the earlier pasted text could pass the
comparison. Hash differences between full-screen PNGs also did not prove a
message was composed or sent: unrelated redraws and image metadata can change.

An additional worker problem classified a useful short, structured reply to
ordinary notes as failure because a fallback research route imposed an
80-character minimum. A reply should not become longer just to pass validation.

## System Changes

- `wechat_gui_send.py` owns a fresh random clipboard probe before Ctrl+C. It
  verifies that ownership, then requires a new exact composer copy. The probe
  is never pasted or sent. The temporary foreground xclip process is cleaned up.
- `wechat_native_text_delivery.py` resolves the exact configured chat and self
  identity. Before Enter it captures per-shard native local-ID boundaries and
  time, then persists a private pending receipt atomically with mode `0600`.
- After Enter, the sender waits briefly for an exact self-authored text row in
  that chat's native database, beyond those boundaries, with a server ID and
  sent status. Another chat, another sender, an older identical reply, a failed
  row, and a screenshot change cannot satisfy this check.
- A missing receipt is `WECHAT_GUI_SEND_UNCERTAIN`, not success. A retry checks
  the saved receipt before any GUI interaction. It recovers a late native echo
  without another send, or stays uncertain without pressing Enter again.
  An operator must reconcile an unresolved intent before allowing a resend.
- The direct monitor and worker retain compose failures and uncertain sends
  using their existing deferred-delivery contracts. They do not regenerate the
  answer or immediately retry the GUI in a loop.
- Structured short answers no longer require arbitrary padding. Existing
  requested-artifact, source-evidence, explicit-failure, and coverage checks
  remain authoritative.
- Health keeps file-picker failures visible after queue expiry for the current
  client lifetime, until a later successful file send or client replacement.
  This diagnostic does not authorize reopening or logging out an account.

These text receipts are native client/server-history evidence, not proof that a
human read a message. They depend on the existing fresh decrypted DB workflow.
Legacy mirror records without this verification must not be treated as proof
when auditing reported missing replies. Do not indiscriminately replay them.
The file sender still has its separate attachment/picker checks; this change
does not claim to repair an unresponsive client's file picker.

## Validation

Focused tests cover nonce freshness and clipboard-owner races, same-chat/self
native evidence, old-message exclusion, multiline Unicode, pending receipt
permissions, crash recovery without resend, screenshot-only false positives,
short structured answers, research gates, and persistent picker diagnostics.

```bash
python -m unittest discover -s tests -p test_wechat_native_text_delivery.py
python -m unittest discover -s tests -p test_wechat_gui_send.py
python -m unittest discover -s tests -p test_wechat_direct_chatops.py
python -m unittest discover -s tests -p test_wechat_task_worker.py
python -m unittest discover -s tests -p test_wechat_transport_stall_guard.py
PYTHONPATH=src python -m agenticapp wechat selftest --suite all
```

Live read-only validation resolved all six configured native chat bindings.
A no-paste/no-send clipboard probe correctly rejected the non-copying composer.
The native verifier accepted a known real outgoing message, including decoding
its full multilingual text, and rejected the earlier false-positive link ACK.
All 923 focused tests and the complete WeChat self-test suite passed. The six
idle personal-WeChat monitors and two idle workers were reloaded; native
WeChat and WeCom process identities remained unchanged.
The independent WeCom Tiny11 health endpoint reported ready. Neither client was
restarted, logged out, or switched, and no phone control was used.

At that verification point, personal WeChat GUI delivery was still blocked.
Downloaded originals, transcripts, queue evidence, and private knowledge remain
local. Do not claim delivery, restart the abandoned card task, or replay expired
queues merely because these code tests pass.

## Owner-Approved Restart And Overlay Correction

The owner subsequently authorized a client-only restart and suggested an
overlay, rather than a frozen application. The saved account reopened without
switching accounts or clearing its profile; WeCom and the phone were untouched.
The exact Shares chat then opened normally. A file send reproduced the reported
failure while a real Qt file chooser was visibly open at the top-left.

This confirmed a detector defect, not evidence that the chooser failed to open:

- The chooser's title is simply `Open`, with `WM_CLASS` set to `wechat` and
  `WM_TRANSIENT_FOR` pointing to the exact main WeChat window.
- The old detector recognized names such as `Open File`, but not this dialog.
- `xdotool getwindowclassname` was unsupported on this installation and
  silently yielded an empty class because the read was non-raising.
- Without a window manager, `getactivewindow` can be unavailable even when a
  dialog has input focus.

The sender now reads `WM_CLASS` and `WM_TRANSIENT_FOR` through `xprop`, accepts
the short `Open` title only for the native WeChat dialog attached to the guarded
parent, and falls back to X input focus when there is no active-window manager.
Tests reject an unrelated application's Open dialog, a wrong parent, and a
missing parent. Do not widen this to any window named Open.

For future diagnosis, inspect the full desktop and native window tree before
calling an app unresponsive. `WECHAT_FILE_CHOOSER_NOT_OPEN` means the automation
did not verify a chooser; the error alone cannot establish that no dialog exists.
Do not perform another restart when a recoverable modal dialog is the cause.

After this fix, the existing LabCanvas deferred-delivery worker returned the
stored original MP4, transcript, and one summary to the exact source chat.
All three appeared in native history as self-authored messages with server IDs
and sent status. The summary's native receipt arrived after the bounded wait;
the existing exact-task resend entrypoint reconciled that saved receipt without
another GUI send. The task finished `done`, with two sent files, one text part,
and no send errors. No new model turn or download was needed. The abandoned
card task was not restarted. The picker regression suite passed 71 tests, and
the full WeChat self-test suite passed again.
