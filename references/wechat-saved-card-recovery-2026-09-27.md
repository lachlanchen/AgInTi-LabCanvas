# Saved Channels Card Recovery

## Contract

An exact retained Channels/Finder card is a durable source, not missing input.
Use the original same-chat message or explicit quote, object ID, full caption,
author, private source file and verified cache. A timeout, expired embedded
media URL or failed native menu read does not require the user to reforward the
card, paste its link, reopen it or supply screenshots.

Use the active transport's established recovery routine. On Windows WeChat:

```bash
python agentic_tools/wechat_gui_agent/scripts/shipinhao_tiny11_share_link.py \
  --chat '<EXACT_CHAT>' --source-text-file '<PRIVATE_SOURCE_CARD>' \
  --output-dir '<TASK_DIR>/shipinhao_media_transcript/windows-native-link'
```

The worker calls this automatically after exact cached/direct media recovery
fails, then passes `--recovered-share-url` to the existing original-video
downloader/transcriber. Release the GUI lock before download and GPU 1 ASR.
Neither the agent nor this routine may restart WeChat, switch profiles, operate
inactive Android/Linux clients, bypass login gates or publish anything.

## Defects And Fixes

1. Read-only confirmation protection covered only `research_summary`. Cards
   routed as `file_download_or_save` could ask for a resend. The shared contract
   now covers identified read-only cards independently of that route choice
   and does not depend on a preflight record being present.
2. Deferred/stored delivery applied response policy but not that source guard.
   Response policy now applies the same guard before each actual send, so an
   older saved response cannot restore a resend confirmation.
3. OCR ran over a popup plus the video, subtitles and player controls behind
   it. The Windows helper now isolates light native popup rectangles before
   exact label matching. It never substitutes fuzzy matching for Copy Link.
4. Cleanup clicked an outdated fixed tab-close position and did not verify
   closure. It now dismisses the owned popup, locates a unique small X inside
   the dock tab header, and verifies the pane disappears. The app title bar
   is outside the search region. Existing user-owned panes are preserved.

Codex and AgInTi receive the same saved-source recovery instruction. Intent
interpretation stays with the agent; native mechanics and identity validation
stay with reusable routines. Genuine unidentified-source clarification and
public-publish/comment approval gates are not removed.

## Verification

- Regression tests cover the download route without preflight, stored-result
  delivery, unchanged publication/unknown-source gates, both backend prompts,
  popup isolation, native-coordinate offsets and owned-tab cleanup.
- A retained card that previously requested a resend was recovered from the
  existing Windows chat. The copied link passed full title and author checks.
- Its original 29.7-second video was downloaded and transcribed using the
  existing pipeline with GPU 1 selected. Private manifests retain exact object
  identity, media probing, source provenance and transcript evidence.
- Review found the sung classical-language clip's ASR unintelligible. The
  source-grounded agent can now return `transcript_usable=false`: keep the raw
  recognition private, return the verified original without a misleading text
  attachment, and retract that ASR from future knowledge retrieval without
  deleting the audit record. Do not infer transcript quality from media identity
  or successful process completion. The first original video was delivered
  through the normal sender with a verified native receipt, not republished.
- A second retained 39.8-second card also passed native link recovery, original
  download, English ASR and source-grounded synthesis. Its original MP4 and
  timestamped transcript were delivered by the normal sender with native
  receipts. No new card, pasted link, client restart or public publish was used.
- `npm test`: 2,219 tests passed (16 optional skips). The native GUI tests also
  passed in the installed OpenCV/Pillow environment, alongside these live runs.
- Screenshots, signed links, full captions, private chat IDs and source files
  stay in ignored task directories, never this document or git.

If recovery remains blocked, say what evidence is unavailable without claiming
the video is silent or watched. Keep the original task/source for retry; do not
promise automatic retry unless a durable retry is actually scheduled. Return
only newly recovered source-scoped artifacts through the existing sender and
verify native receipts before reporting delivery.
