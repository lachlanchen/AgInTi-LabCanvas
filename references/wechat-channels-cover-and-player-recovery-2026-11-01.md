# Channels Card Recovery: Cover Ordering And Player Readiness

## Symptoms And Cause

The native client was logged in and message intake was current, but Channels
tasks returned only the publisher's caption. The original download URL failed,
and native recovery reported `finder_card_not_found` even though the exact card
was visible in its own retained screenshot.

The first transcriber pass intentionally disabled public-mirror search to try
the original source first. Cover caching, however, existed only inside public
search. Native recovery therefore ran before its exact-card reference image
existed. Its OCR fallback could not reliably read the card's author/title.
Downloading the cover after the failed scan was too late.

A second failure appeared once the cover was available: the native Channels
browser could take longer than eight seconds to open and load. A bounded
40-second readiness wait recovered the exact player and its share link without
restarting or logging out WeChat.

Queue health also treated a delivered source-limited explanation as successful
completion. That hid the unsuccessful media retrieval from operators.

Recovery exposed a separate delivery blocker: the completion checker interpreted
"do not send raw debug paths, Markdown or PDFs" as a request for a PDF because
the negation was more than sixteen characters away. Both verified video tasks
then failed an unrelated PDF requirement.

## Persistent Changes

- `shipinhao_media_transcribe.cache_card_cover` caches the exact object's cover
  before native recovery, including when public search is disabled or the card
  has no usable embedded video URL. It reuses cached evidence, bounds downloads,
  and removes partial failed downloads. Public search reuses the same helper.
- The Linux GUI command uses `shipinhao_native_link_python`, the existing
  interpreter selector that checks OpenCV/Pillow availability. Lean CLI Python
  installations no longer silently lose the visual matching route.
- The native helper and worker default to a 40-second player readiness budget,
  configurable with `WECHAT_SHIPINHAO_PLAYER_OPEN_TIMEOUT_SECONDS`. Polling exits
  early when ready; this is not an unconditional sleep or an unbounded retry.
- `wechat health` flags recent `done` tasks whose Channels preflight still
  reports failed retrieval. It reports the native failure stage when available.
  It does not resend replies, rerun historical work, or alter queue status.
- The completion checker recognizes negated artifact lists within a clause,
  while preserving an explicit positive PDF request in a later clause.
  Recovery of a falsely blocked task removes only the proven erroneous
  requirement and uses `worker repair-result TASK_ID --send`, without another
  model turn or download.

## Recovery Procedure

1. Inspect the exact task's preflight and private native-scan screenshots.
   Check the cover file timestamp against the first scan timestamp.
2. Run the normal preflight/native helper for the retained same-chat card.
   Do not ask for a resend or substitute another card with a similar title.
3. Require the native identity check and exact Copy Link action. Pass the copied
   URL explicitly with `--recovered-share-url` to the existing transcriber.
4. Release the GUI before downloading and transcribing. Verify the original
   MP4 with `ffprobe`; use the configured GPU mapping and established CPU
   fallback without interfering with another project's GPU work.
5. Resume the exact task with its verified source artifacts. Deliver only the
   missing original, transcript and source-grounded response through the normal
   sender. Check native receipts, not only a process exit code.
   Reuse the canonical delivery files. Do not ask a recovery agent to create
   renamed transcript copies: different headers defeat byte-level deduplication
   even when the transcript body is unchanged.
6. Reload only idle worker processes to adopt worker-code changes. Leave the
   logged-in client, profile, paused WeCom and disabled EchoMind schedules alone.

## Regression Coverage

- Cover exists before returning a failed direct-media pass with public search off.
- Cover is also retained when the card contains no video URL.
- Cached cover reuse makes no extra network request; failed partials are removed.
- Linux native recovery selects the existing vision-capable interpreter.
- Worker and helper retain the bounded cold-start loading budget.
- Delivered failure explanations remain visible in health; verified recovery
  clears the flag and historical failures retain the existing attention horizon.
- Long negated English/Chinese artifact lists do not require a PDF; a separate
  affirmative PDF request still does.

## Live Verification

Two previously failed cards recovered their original MP4s through the exact
native Copy Link route. Probed durations were 85.263 and 31.254 seconds, both
with readable H.264 video and AAC audio. The normal worker transcribed the
originals, and stored-result repair delivered the videos, timestamped text and
source-grounded summaries to the originating chat. Native message history
confirmed both video messages, attachments and final summaries.

One recovery included a second, differently headed transcript copy. It did not
repeat the video. Future recovery instructions should reuse canonical artifacts
as described above rather than creating alternate copies. No public publication
was performed, and no client restart or login was needed.

The isolated staged snapshot passed `npm test`: 2,456 tests, 54 skipped for
unavailable optional dependencies or local fixtures. Both production worker
loops reloaded after their guarded self-test. The final health check showed
seven ready/caught-up monitors, no stale source groups and no recent blocked
deliveries. Verified transcripts and summaries were retained in source knowledge.

Private screenshots, signed URLs, chat records and source files stay ignored.
No screen or audio recording is an acceptable replacement for the original.
