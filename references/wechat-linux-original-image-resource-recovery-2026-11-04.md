# Linux WeChat Original Image Recovery

## Failure

The Linux worker searched the media mirror using the image XML digest. The
native cache used a different filename supplied by `MessageResourceInfo`.
Consequently, the worker reported a missing original even though the full image
was already cached. The fallback agent decoded a 117 x 210 thumbnail and treated
that retrieval failure as a source-resolution limitation.

Opening or upscaling that thumbnail cannot recover the missing information.
The resource mapping, not a new upload or a different caption prompt, is needed.

## Current Path

`wechat_task_worker.prepare_media_resolution_preflight` selects the native image
reader for the active transport. Windows keeps `wechat_tiny11_image.py`; Linux
uses `wechat_linux_image.py`. Native image tasks do not fall through to a generic
recent-file scan or arbitrary GUI clicks.

The Linux reader:

1. Validates the configured chat, account, message shard, local ID, server ID,
   timestamp, and image type against the native message snapshot.
2. Joins the resource database on that exact chat/message identity. It accepts
   only one token in the known nested resource field, not an arbitrary hash.
3. Selects that resource's `_h.dat` or full `.dat` under the account/chat cache.
   `_t.dat`, bubble previews, neighbouring images, and symlink escapes are not
   source candidates.
4. Decodes V1/V2 or legacy XOR data. Account-scoped private keys are validated
   against the source and its exact thumbnail before reuse. Offline key
   provisioning is bounded to one CPU and never scans process memory or restarts
   the client. Native JPEG/PNG data is retained without resampling. WXGF/HEVC
   containers retain their original bytes and use the existing lossless PNG
   decoder at native dimensions.
5. Writes private source provenance and supplies the verified original to the
   existing vision, OCR, source-knowledge, agent, and guarded delivery stages.
   Current coalesced images remain ordered and deduplicated.

Vision uses the shared model policy instead of a stale hardcoded default. The
shared runner discovers pinned/AgentShell installations even when the service
PATH lacks `codex`. The account/quota gate remains in effect; LocalLLM vision remains its existing API
fallback. A failed analysis is no longer automatically described as a thumbnail
or low-resolution image.

`pycryptodome` is declared with the package runtime dependencies. Use the worker's
existing Python environment when diagnosing decoding; a separate interpreter
without the crypto package can otherwise make an encrypted original appear
unreadable.

## Verification And Recovery

The previously rejected source recovered as a readable 780 x 3084 JPEG from its
existing full cache. Neither a resend nor a WeChat restart was required. The
private task retains the original, decoded source, dimensions, resource binding,
checksums, and vision/OCR evidence. None belongs in git or the group reply.

For an already missed task, use the normal worker reprocessing entry point:

```bash
labcanvas wechat worker reprocess <TASK_ID> \
  'Read the verified native original and send one useful source-grounded answer.'
```

Only reload idle worker processes when installing a change. Preserve the client,
login, transport selection, unrelated jobs, and paused WeCom/EchoMind schedules.
Verify the resulting native chat delivery, not just the task's internal status.

Regression tests in `tests/test_wechat_linux_image.py` cover the differing XML
digest, exact resource binding, native dimensions, thumbnail rejection, account
and shard isolation, symlink rejection, coalesced image order, private key reuse,
WXGF preservation, worker routing, model policy, and false low-resolution replies.

## Limits

This reader cannot invent an original that the client has never cached, decode a
corrupt container, or make an intrinsically blurry source sharper. Those are
retrieval/decoding/source limitations with separate evidence; they must not be
confused with an unread original that is already available locally.
