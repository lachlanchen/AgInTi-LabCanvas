# WeChat Shipinhao Audio Transcription Workflow

## Purpose

This workflow lets a LabCanvas worker read a WeChat Channels/Shipinhao share as
source material, transcribe its actual audio, summarize it with the chat's
resumed agent session, and return the answer to the originating chat. It is
read-only: opening the shared card and recording local playback does not like,
follow, comment, repost, or invoke Yuanbao.

## Evidence Pipeline

1. Resolve the exact current WeChat row and parse its `<finderFeed>` block.
2. Bind the task to `objectId`, title, author, nonce ID, and media URL hash.
3. Try the allowlisted Tencent media URL with bounded download and SSRF guards.
4. If the signed URL expired, open that exact card in native WeChat.
5. Run an identity-gated local capture. OCR must match distinctive title or
   author terms before recording, and recording stops after the terms disappear
   on consecutive polls.
6. Hash the trimmed source-only audio and write `verified-capture.json` below
   the private object-ID cache.
7. Transcribe with Whisper, write timestamped Markdown, and pass only the
   source-scoped transcript to the resumed per-chat worker agent.
8. Send the natural summary through the guarded same-chat sender and verify
   `sent`, `done-sent`, and `synced` mirror states.

## Native Capture

Leave the exact Channels player visible, then run:

```bash
python agentic_tools/wechat_gui_agent/scripts/shipinhao_gui_audio_capture.py \
  --object-id '<OBJECT_ID>' \
  --title '<EXACT_CARD_TITLE>' \
  --author '<EXACT_AUTHOR>' \
  --identity-term '<DISTINCTIVE_TITLE_TERM>' \
  --identity-term '<SECOND_TERM>' \
  --display :97 \
  --json
```

The helper:

- takes the serialized WeChat GUI lock;
- finds only a visible native `WeChat` Channels window;
- selects a PipeWire output whose process binary is `WeChatAppEx` on the same
  display;
- OCRs title and footer regions without navigating or posting;
- records with `pw-record` while identity remains visible;
- detects feed auto-advance, trims the next item, and stores hashes plus start/
  end screenshots in a private manifest.

Monitoring is local and does not poll Codex or consume model tokens.

## Transcription

Automatic workers discover the matching private manifest by object ID. Manual
verification is available with:

```bash
python agentic_tools/wechat_gui_agent/scripts/shipinhao_media_transcribe.py \
  --source-text-file '<TASK_DIR>/shipinhao_media_transcript/exact-source-card.txt' \
  --capture-manifest '<PRIVATE_CACHE>/<OBJECT_ID>/verified-capture.json' \
  --output-dir '<TASK_DIR>/shipinhao_media_transcript' \
  --model turbo \
  --json
```

`--captured-audio` remains an operator diagnostic input. Autonomous workers use
`--capture-manifest` because it validates object ID, title, author, private path,
identity terms, and SHA-256 before trusting audio. Every captured-audio cache
name includes the audio hash, preventing one capture from overwriting or
silently reusing another.

## Worker Reprocessing

After a verified capture becomes available, rerun the original source-scoped
task rather than creating a detached summary:

```bash
labcanvas wechat worker reprocess '<TASK_ID>' \
  'Verified Shipinhao capture is ready; transcribe and summarize the exact source' \
  --send
```

The worker writes `task.preflight.shipinhao_media_transcript`, resumes the exact
chat's agent session, and sends the selected response to the task's original
chat. Comments are a separate auxiliary source. Transcript and capture
manifests are not comment exports.

## Failure Rules

- Reject a capture if visual identity does not match before recording.
- Never reload the player after selecting a PipeWire stream; reload may replace
  the audio node and pair the visible card with a different stream.
- Never trust nominal card duration alone. Feed auto-advance is detected from
  visible identity loss and trimmed from the audio.
- Do not expose signed URLs, private chat rows, screenshots, audio, or full
  transcripts in git.
- If no exact media, verified capture, transcript, or reliable reconstruction
  exists, give an evidence-limited answer instead of claiming the video was
  watched.
- Posting a comment or Yuanbao prompt remains a separate explicit write action.

## Validation Record

The 2026-07-15 live validation recovered a roughly three-minute art lecture,
detected the following feed item, produced a source-only Whisper transcript,
ran the normal resumed worker agent, and verified the reply in the native chat
plus SQLite mirror. A deliberately mixed capture was rejected before delivery.

## Open-Source References

- `nobiyou/wx_channel`: Channels identity/comment API patterns.
- `qiye45/wechatVideoDownload`: official-client media interception reference.
- `lecepin/WeChatVideoDownloader`: Channels media download architecture
  reference.

These projects are references only. LabCanvas keeps its source binding, private
cache, transcription, worker routing, and delivery gates local.
