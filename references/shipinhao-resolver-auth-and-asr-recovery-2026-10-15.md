# Channels Resolver Authentication and ASR Recovery

## Scope and Failure

This repair applies to the existing personal-WeChat Channels worker. It does
not enable WeCom, change model billing policy, authorize public publication,
restart WeChat, or require an Android controller. Preserve the exact source
chat, card identity, native share candidate and delivery ledger throughout.

The October 15 investigation found that native card selection and Copy Link
already worked. Expired embedded media URLs were followed by a separate
Yuanbao resolver request that returned HTTP 401. The old parse-only upstream
provider did not validate that response before calling Finder with missing
playback credentials, obscuring the cause as content temporarily unavailable.
WeChat itself was logged in. Asking for another card or another pasted link
could not repair this authentication failure.

The independent Yuanbao browser profile was preserved, but its CDP browser was
not running and the cached login was stale. The owner restored that login.
Authentication may expire again; no permanent-login guarantee is possible.

## Reusable Resolver

`agentic_tools/wechat_gui_agent/scripts/shipinhao_share_link_resolver.py` now
performs the same two-stage flow used by the inspected
[wx_channels_download implementation](https://github.com/ltaoo/wx_channels_download):

1. Read the existing Yuanbao browser cookies, falling back to the private cache.
2. POST the exact native share URL to Yuanbao's `get_parse_result` endpoint.
3. Validate HTTP status, application result, HTTPS Channels host, and nonempty
   playback token and export ID before calling Finder's `get_feed_info`.
4. Normalize the response through the existing complete-title-and-author gate.
5. Download the original only after the source identity is verified.

These are upstream application endpoints, not a promised stable public API.
Responses are bounded, requests have deadlines, redirects are rejected, and
Yuanbao cookies are not forwarded to Finder. Signed links, cookies and raw
responses remain private. An explicit legacy provider override remains
available for compatibility, but is not the default path.

Failures carry structured stage-specific error codes. In particular,
`yuanbao_login_required` is not a WeChat logout, deleted video, silent video,
or evidence that the user supplied a bad card. The native adapter preserves
this code. The worker avoids pointless public-mirror retries for this blocker
and gives the agent the actual cause, with instructions not to ask for the
same source again. The saved candidate is reused after login recovery.

## Existing Browser and Recovery

Use the existing owner profile at
`agentic_tools/wechat_gui_agent/.private/yuanbao-chrome`, CDP port `49245`.
The current login browser uses the existing WeChat project display `:97` and
noVNC `6107`; it does not create a second Xvfb/noVNC stack. Its tmux window is
`labcanvas-wechat:yuanbao-login`. The personal-WeChat Windows console remains
on port `6143` and is independent of this downloader login.

Inspect existing browser/process ownership before launching anything. Reuse
the profile and browser when present. Never delete the profile, restart the
Windows client, enable proxy interception, install a CA, or use screen/audio
capture as a substitute for an original download. Real authentication requires
the owner's normal login confirmation when no valid session remains.

After restoring authentication:

1. Retry the exact task's `windows-native-link/native-share-candidate.json`.
2. Verify complete title and author against `exact-source-card.txt`.
3. Download and probe the original MP4; inspect audio streams before ASR.
4. Reuse a verified transcript/cache when available.
5. Reprocess only the failed source task through `wechat_task_worker.py`.
6. Check native delivery receipts; do not replay completed tasks or the backlog.

For a completed answer with missing delivery, use the existing `repair-result`
command instead of rerunning source work. Keep original-video, transcript and
summary delivery idempotent and bound to the originating chat. None of this
authorizes social-platform publication.

## ASR Resource Recovery

The first verified download then encountered an NVML initialization failure;
`nvidia-smi` also reported a driver/library mismatch. This is not silent media
or a download failure. Do not reboot, reset the GPU, switch to a GPU occupied
by another project, or stop another project's workload as an ASR repair.

`wechat_voice_transcribe.py` now extends its existing CUDA OOM fallback to
recognized driver/NVML initialization errors. It retries the same Whisper
model on CPU with the existing bounded thread setting and records
`cuda_driver_unavailable`. It does not call CUDA cache cleanup for a broken
driver, swallow unrelated errors, or loop after a CPU failure. GPU 1 remains
the configured normal route. The host-wide driver mismatch is not repaired by
this application change and requires separate workstation maintenance.

## Verification

The isolated regression suites passed: resolver 11, native link 19, worker 622,
and Whisper fallback 4 tests, 656 total. Run them with
`WECHAT_TINY11_DISABLE=1 PYTHONPATH=src` so tests cannot adopt live GUI transport.
The complete `npm test` suite also passed: 2,333 tests, 16 skipped. Two existing
combined-image tests now explicitly enable their mocked vision call inside
the test context; the suite-wide live-vision disable remains in effect.
Clean GitHub CI also exposed session tests that had accidentally depended on
the workstation's private quota cache. Session/workspace test fixtures now
simulate account attempts and quota-rejection writes, while dedicated account
policy tests continue testing real selection logic with their own fixtures.
No production credit restriction or account policy was relaxed for CI.

Two previously failed sources were independently resolved and downloaded:

- 55.542 seconds, 1,807,828 bytes, H.264 720x1280 with AAC audio. Its SHA-256
  matched the original cached by the transcription pipeline. ASR produced 17
  timestamped segments. The successful retry reported CUDA, so this is not
  live proof of CPU fallback; CPU recovery is covered by injected-error tests.
- 28.467 seconds, 2,568,584 bytes, complete native title/author identity verified.

Private receipts live under each source task's `download-verification/`,
`shipinhao_media_transcript/`, and native-link directories. Do not commit raw
chat history, media, transcripts, signed URLs, cookies or login screenshots.
Download and transcription success alone do not prove chat delivery; verify
the normal worker's separate send receipts before reporting that stage done.

At 17:17 HKT the normal production worker completed the single reprocessed
source task. Its completion audit recorded `verified_source_delivery`, all
source-message coverage items were covered, and there were no send errors.
The original video, timestamped transcript and source-grounded summary were
delivered to the originating chat. No manual sender or public publisher was
used, and the older failed-source backlog was not replayed.
Native outbound records had nonzero server receipts; the video's receipt used
`native_video_row_and_exact_stream_hashes` to verify unchanged audio/video
streams, rather than treating a successful click as delivery proof.
