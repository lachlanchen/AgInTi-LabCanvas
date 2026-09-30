# WeChat Client and Channels Recovery

## Incident and Evidence

The seven personal-WeChat monitor heartbeats were fresh, but the selected
Windows client's main process was absent. The VM, SSH tunnel, and native helper
were reachable. A readable cached message database did not establish live
reception. The available evidence does not establish why the client exited.

The existing saved-profile launch task was started once, after checking that
no personal-WeChat main process existed. The visible saved-account Enter
Weixin button restored the session without QR, profile changes, or a process
kill. Native health became ready and a retained Channels card entered the
normal worker queue automatically. WeCom remained paused; Android was not used.

Do not replay old login-click coordinates. Inspect the current entry window
and button first. Do not interpret a hidden or hung window as an absent process,
and do not launch another client to repair a hidden window. A future login or
security challenge remains a separate explicit blocker.

## Persistent Fixes

- `wechat_transport_selection.py` distinguishes a freshly observed missing
  client from a bridge failure or a login challenge. Stale observations cannot
  establish that the client is currently absent.
- `shipinhao_tiny11_share_link.py` re-reads the window bounds after closing its
  owned dock. Closing the dock shrinks WeChat; the old rectangle included black
  desktop pixels that were misclassified as a remaining player.
- Cleanup errors are recorded privately, but cannot erase a copied link or mask
  the original failure. Exact resolved title and author are still mandatory.
- Copied links are retained as private, source-chat/object/title/author-bound
  `native-share-candidate.json` records. These are explicitly unverified.
  A retry can validate the retained candidate without reopening the GUI;
  only successful identity validation creates `native-share-link.json`.
- Resolver failures propagate as `share_resolver`, with `native_link_copied`
  and `failure_origin`. Worker context distinguishes a download-service error
  from text observed in the native player. Never infer deletion, silence, a
  completed download, or a need to resend from that error.

## Remaining Service Limitation

During live verification the separate resolver returned a content-unavailable
error for both the new card and a previously verified card. Its logged-in CDP
endpoint was not listening; the resolver used its private cached credentials.
This suggests a resolver/session problem but does not prove the precise cause.
No browser was opened and no authentication state was reset. The fresh card's
candidate link is retained privately. Original-video delivery is not claimed.

## Verification and Reuse

- `npm test`: 2,224 tests passed, 16 optional skips.
- Native OpenCV/Pillow Channels suite: 18 tests passed.
- Session-preservation suite: 11 tests passed.
- Live native readiness and database intake recovered; the worker delivered
  its source-limited response to the original chat.
- Current shared console: `http://127.0.0.1:6143/`.
- Existing runtime: `labcanvas-wechat`, with personal worker loops and native
  store sync. Do not start a duplicate desktop, enable paused WeCom, or poll
  Android while repairing this transport.

Use `labcanvas wechat health --json` to distinguish monitor liveness, source
freshness, client readiness, queue execution, and verified delivery. Reload
only idle affected workers. Preserve source IDs, per-chat cursors, and outbound
receipts; do not mass-replay history or resend already delivered artifacts.
