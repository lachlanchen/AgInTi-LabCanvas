# Windows WeChat Docked-Pane Delivery

## Failure Observed

On 2026-09-27 the native message database was fresh and all seven personal
WeChat monitors were caught up. Workers had completed replies, but delivery
reported an existing draft. The visible editor was empty.

A docked Channels player shortened the chat pane. The sender still inspected
pixels through the main window's right edge, including the dark player. This
was a geometry failure, not a logout, lost message, or backend model failure.
Title and history crops had the same full-window assumption.

## Persistent Repair

`wechat_tiny11_bridge.py` now owns the shared `native_docked_pane` detector.
It recognizes the native divider, including the white loading state, and uses
the dark player boundary as fallback. The sender derives the actual chat right
edge from the current screenshot for title, history, attachment-label and empty
composer checks. Channels link recovery reuses this geometry instead of keeping
a separate copy.

An empty text clipboard alone still cannot prove an empty editor. The existing
attachment-pixel guard remains, but its crop is bounded by the chat pane. Real
text drafts and file chips continue to block unrelated sends. Preserve exact
chat-title verification, pre-Enter send intents, and native outgoing receipts.
Do not clear a real draft, weaken identity checks, or restart a logged-in client
to work around this failure.

## Recovery Procedure

1. Check source freshness, per-chat cursor/heartbeat, queue state and sender
   evidence separately. A running monitor is not delivery proof.
2. Inspect one private screenshot under the existing serialized GUI lock.
   Compare the claimed draft against the actual chat pane and any docked view.
3. For a complete unsent answer, use the existing worker's exact-task resend.
   Its native intent/receipt ledger suppresses already-sent chunks. Do not
   rerun the agent or replay the whole chat to repair a sender-only failure.
4. Reprocess source tasks only when their content retrieval also failed. Keep
   the same task/chat/card identity and require resolved full title and author
   before accepting a Channels link. An old player's visible video is not the
   newly requested source.
5. Verify the outgoing native message row, not merely a click or a `done` label.
   Keep screenshots, message IDs, links and receipts in ignored private storage.

The MEMO recovery was verified through the existing sender without a client
restart. WeCom's operator pause and Android no-control policy were preserved.
The shared Windows console remains `http://127.0.0.1:6143/`.

## Forwarding and Disconnected Callers

During live recovery, helper health succeeded inside Windows and through a
fresh SSH direct channel, but the existing localhost forwarding process timed
out. Reconnecting only that tunnel restored communication without touching the
chat clients. A listening port and a live SSH process are not readiness proof.
The transport supervisor now recycles its own tunnel after three consecutive
failed helper probes, resetting that count after a successful probe. A logged-out
client with a responsive helper is still not a transport failure.

The Windows helper also previously exited when a disconnected HTTP caller
caused its response write to fail: the error handler tried to write a second
response to the same dead connection. It now catches that secondary failure,
closes the response and keeps accepting requests. Sender intent/receipt rules
remain authoritative; reconnecting never authorizes repeating an uncertain Send.

Pending tasks retain their existing short anti-backlog expiry. Explicit
reprocessing already assigns a fresh deadline; a long same-chat recovery can
still occupy the lane until a later pending request expires. Do not mistake
this for an original-timestamp bug or disable expiry globally. Recover exact
missed requests deliberately and do not bombard chats with historical replay.

## Existing Window Is Not Proof of Readiness

A later live probe found the native WeChat message loop hung while its window
and cached history remained visible. Clipboard writes succeeded, but clicks and
paste/readback did not change the editor. The previous helper called any visible
main window `ready`, hiding this condition.

`NativeWindows.IsResponding` now sends read-only `WM_NULL` with a two-second
`SendMessageTimeout` bound. Personal WeChat health reports `unresponsive` and
`input_ready=false` if the loop does not answer; input is refused before focus.
Native store sync also requires a ready, input-capable client before advertising
delivery readiness. A hung window is not a QR/login request, and it must not
trigger automatic account logout or restarting an inactive Ubuntu fallback.

Closing the verified personal Channels subprocess alone did not recover the
hung main window in this incident. Do not treat that operation as a proven
recovery recipe or add a recurring process killer. Preserve the account/profile
and obtain operator direction before restarting the main client when login
continuity is required. Keep unsent results and their receipt journals intact.

## Regression Coverage

- A docked player does not make an empty composer look occupied.
- History excludes the docked player.
- A genuine attachment chip or human text still blocks a send.
- Undocked chat geometry remains unchanged.
- Native mention fallback uses the chat boundary, not the docked tab controls.
- Repeated failed probes recycle only the owned tunnel; healthy probes reset
  the counter and a logged-out client does not cause a helper restart.
- A disconnected error-response write is contained inside the request loop.
- A visible but unresponsive client cannot claim readiness from a fresh database
  or cause a false request for login verification.

Run `npm test`; its test harness disables selection of the live Windows account.
Run one exact-task live recovery separately, and retain the native receipt.
